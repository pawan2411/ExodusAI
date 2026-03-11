"""ExodusAI Backend — FastAPI server with simulation engine and Gemini Live API."""

import asyncio
import base64
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from gemini_live import GeminiLiveSession
from simulation.city_block import CityBlock
from simulation.renderer import render_frame
from simulation.maps_renderer import render_maps_frame

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "info").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("exodusai")

app = FastAPI(title="ExodusAI", version="2.0.0")

SIM_TICK_INTERVAL = 0.10    # 10 ticks/second

# Feed rates (in ticks)
GEMINI_SIM_INTERVAL  = 3    # Send simulation frame to Gemini every 3 ticks (~3 fps)
GEMINI_MAPS_INTERVAL = 20   # Send traffic map to Gemini every 20 ticks (~2 s)
MAPS_CLIENT_INTERVAL = 15   # Send maps view to browser every 15 ticks (~1.5 s)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "exodusai-backend", "version": "2.0.0"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")

    state = {
        "simulation": None,
        "sim_config": None,
        "paused": False,
        "started": False,
    }

    gemini = GeminiLiveSession(simulation_state=state)

    try:
        await gemini.connect()
        await _send(websocket, {
            "type": "status",
            "data": {"connected": True, "model": gemini.model},
        })

        await asyncio.gather(
            _recv_from_client(websocket, state, gemini),
            _send_from_gemini(gemini, websocket),
            _sim_runner(state, gemini, websocket),
            return_exceptions=False,
        )

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Session error: {e}", exc_info=True)
        try:
            await _send(websocket, {"type": "error", "data": {"message": str(e)}})
        except Exception:
            pass
    finally:
        await gemini.close()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("Session cleaned up")


# ── Receive from browser ────────────────────────────────────────────────

async def _recv_from_client(websocket: WebSocket, state: dict, gemini: GeminiLiveSession):
    while True:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
        msg_type = msg.get("type")
        data = msg.get("data", {})

        if msg_type == "config":
            state["sim_config"] = data
            state["simulation"] = CityBlock(data)
            state["started"] = False
            state["paused"] = False
            sim = state["simulation"]
            sim_dict = sim.to_dict()
            await _send(websocket, {"type": "sim_state", "data": sim_dict})
            # Send both initial views immediately
            await _send(websocket, {
                "type": "sim_frame",
                "data": base64.b64encode(render_frame(sim_dict)).decode("ascii"),
            })
            await _send(websocket, {
                "type": "maps_frame",
                "data": base64.b64encode(render_maps_frame(sim_dict)).decode("ascii"),
            })
            logger.info(f"Sim configured: {data}")

        elif msg_type == "start":
            sim = state.get("simulation")
            if sim and not state["started"]:
                sim.start_evacuation()
                state["started"] = True
                state["paused"] = False
                # Brief Gemini with context (both view types explained)
                exits_info = ", ".join(f"{e.id}({e.name})" for e in sim.exits)
                buildings_info = ", ".join(
                    f"{b.id}({b.total_population}ppl)" for b in sim.buildings
                )
                await gemini.send_text(
                    f"EVACUATION STARTED — your goal: evacuate all {len(sim.persons)} people "
                    f"in the shortest possible time.\n"
                    f"Buildings: {buildings_info}\n"
                    f"Exits: {exits_info}\n"
                    f"Highway outbound capacity: {sim.highway.outbound_capacity} ppl/sec\n"
                    f"Current state: {sim.summary_text()}\n\n"
                    f"You will receive continuous live video frames (simulation view + traffic map). "
                    f"Take action NOW: call get_status, then issue redirect_building commands to "
                    f"distribute load across exits, and increase highway capacity if needed. "
                    f"Do not wait — every second counts."
                )
                # Send the initial frame immediately so Gemini can act
                await gemini.send_video_frame(render_frame(sim.to_dict()))
                await gemini.send_video_frame(render_maps_frame(sim.to_dict()))
                logger.info("Evacuation started")

        elif msg_type == "pause":
            if state["started"]:
                state["paused"] = not state["paused"]
                action = "paused" if state["paused"] else "resumed"
                await _send(websocket, {"type": "alert", "data": {"message": f"Simulation {action}"}})

        elif msg_type == "reset":
            config = state.get("sim_config") or {}
            state["simulation"] = CityBlock(config)
            state["started"] = False
            state["paused"] = False
            sim = state["simulation"]
            sim_dict = sim.to_dict()
            await _send(websocket, {"type": "sim_state", "data": sim_dict})
            await _send(websocket, {
                "type": "maps_frame",
                "data": base64.b64encode(render_maps_frame(sim_dict)).decode("ascii"),
            })
            logger.info("Simulation reset")

        elif msg_type == "text":
            if isinstance(data, str) and data.strip():
                await gemini.send_text(data.strip())


# ── Gemini → browser ────────────────────────────────────────────────────

async def _send_from_gemini(gemini: GeminiLiveSession, websocket: WebSocket):
    async def on_text(text: str):
        await _send(websocket, {"type": "decision", "data": {"text": text}})

    async def on_action(action_dict: dict):
        await _send(websocket, {"type": "action", "data": action_dict})

    await gemini.receive_responses(on_text, on_action)


# ── Simulation runner ────────────────────────────────────────────────────

async def _sim_runner(state: dict, gemini: GeminiLiveSession, websocket: WebSocket):
    tick_counter = 0

    while True:
        await asyncio.sleep(SIM_TICK_INTERVAL)

        sim: CityBlock | None = state.get("simulation")
        if sim is None or not state["started"] or state["paused"]:
            continue

        sim.step()
        tick_counter += 1
        sim_dict = sim.to_dict()

        # ── Render simulation frame ──
        sim_jpeg = render_frame(sim_dict)
        sim_b64 = base64.b64encode(sim_jpeg).decode("ascii")
        await _send(websocket, {"type": "sim_frame", "data": sim_b64})
        await _send(websocket, {"type": "sim_state", "data": sim_dict})

        # ── Stream simulation frames to Gemini as live video (3 fps) ──
        if tick_counter % GEMINI_SIM_INTERVAL == 0:
            await gemini.send_video_frame(sim_jpeg)

        # ── Generate + send traffic maps view ──
        if tick_counter % MAPS_CLIENT_INTERVAL == 0:
            maps_jpeg = render_maps_frame(sim_dict)
            maps_b64 = base64.b64encode(maps_jpeg).decode("ascii")
            await _send(websocket, {"type": "maps_frame", "data": maps_b64})

            # Also send maps frame to Gemini (interleaved with sim frames)
            if tick_counter % GEMINI_MAPS_INTERVAL == 0:
                await gemini.send_text(
                    f"[TRAFFIC MAP UPDATE] {sim.summary_text()} | "
                    f"Road traffic: {sim.get_road_traffic()}"
                )
                await gemini.send_video_frame(maps_jpeg)

        # ── Congestion alerts → notify Gemini ──
        for alert in sim.get_new_alerts():
            msg = alert["message"]
            await _send(websocket, {"type": "alert", "data": {"message": msg}})
            await gemini.send_text(
                f"ALERT: {msg}. Traffic map: {sim.get_road_traffic()}. "
                f"State: {sim.summary_text()}"
            )

        # ── Milestones ──
        for milestone in sim.get_new_milestones():
            await _send(websocket, {"type": "alert", "data": {"message": milestone}})
            await gemini.send_text(f"MILESTONE: {milestone}")

        # ── Detect completion ──
        if not sim.running and state["started"]:
            state["started"] = False


# ── Utility ──────────────────────────────────────────────────────────────

async def _send(websocket: WebSocket, data: dict):
    try:
        await websocket.send_text(json.dumps(data))
    except Exception:
        pass


# ── Static files ─────────────────────────────────────────────────────────

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    app.mount("/static", StaticFiles(directory=frontend_dir), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
