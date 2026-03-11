"""ExodusAI — Streamlit version for local testing."""

import asyncio
import os
import queue
import sys
import threading
import time

import numpy as np
import streamlit as st
from PIL import Image

# ── Path: reuse backend code ────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from simulation.city_block import CityBlock
from simulation.renderer import render_frame
from simulation.maps_renderer import render_maps_frame
from agents.evac_agent import get_system_prompt, get_tool_declarations

# ── Page config ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ExodusAI",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Dark theme tweaks */
.main { background: #0d0f1a; }
section[data-testid="stSidebar"] { background: #111320; }

/* Decision cards */
.dec-card {
    padding: 8px 12px;
    margin-bottom: 6px;
    border-radius: 6px;
    font-size: 0.82rem;
    line-height: 1.45;
    border-left: 3px solid #4a9eff;
    background: #1a1e2e;
}
.dec-card.action  { border-left-color: #f4a922; }
.dec-card.alert   { border-left-color: #e84545; }
.dec-card.system  { border-left-color: #3a3f5c; color: #888; font-style: italic; }
.dec-card.error   { border-left-color: #e84545; background: #2a1a1a; }
.dec-time { font-size: 0.68rem; color: #666; margin-top: 2px; }

/* Header banner */
.exodus-header {
    background: linear-gradient(90deg, #0d0f1a 0%, #151c35 100%);
    border-bottom: 1px solid #2a2e45;
    padding: 8px 0 4px 0;
    margin-bottom: 12px;
}
.exodus-title { font-size: 1.6rem; font-weight: 800; letter-spacing: 1px; }
.exodus-title span { color: #4a9eff; }

/* Status badge */
.status-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.badge-running  { background: rgba(232,69,69,0.2);  color: #e84545; border: 1px solid #e84545; }
.badge-complete { background: rgba(63,203,110,0.2); color: #3fcb6e; border: 1px solid #3fcb6e; }
.badge-paused   { background: rgba(244,169,34,0.2); color: #f4a922; border: 1px solid #f4a922; }
.badge-ready    { background: rgba(80,80,100,0.2);  color: #888;    border: 1px solid #444; }

/* Metric override */
[data-testid="stMetric"] { background: #151825; border-radius: 8px; padding: 10px 14px; }
[data-testid="stMetricLabel"] { font-size: 0.75rem !important; color: #888 !important; }
[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ───────────────────────────────────────────────
def init_state():
    defaults = {
        "api_key":       "",
        "sim":           None,
        "running":       False,
        "paused":        False,
        "decisions":     [],
        "config":        {"buildings": 5, "exits": 3, "avg_pop": 50, "highway_out": 20},
        "time_scale":    60,    # sim seconds → real minutes multiplier
        "sim_speed":     1,     # ticks per rerun
        "gemini_thread": None,
        "frame_q":       None,
        "text_q":        None,
        "decision_q":    None,
        "action_q":      None,
        "stop_event":    None,
        "sim_ref":       {},
        "tick_counter":  0,
        "last_maps_tick": -1,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── Helpers ──────────────────────────────────────────────────────────────

def _jpeg_to_pil(jpeg_bytes: bytes) -> Image.Image:
    import cv2
    arr = np.frombuffer(jpeg_bytes, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _sim_time_display(elapsed_seconds: float, time_scale: int) -> str:
    """Convert sim seconds to real-world equivalent string."""
    real_seconds = elapsed_seconds * time_scale
    if real_seconds < 60:
        return f"{real_seconds:.0f}s"
    mins = int(real_seconds // 60)
    secs = int(real_seconds % 60)
    return f"{mins}m {secs:02d}s"


def _decision_html(decisions: list) -> str:
    parts = []
    for d in reversed(decisions[-40:]):
        t    = d.get("type", "system")
        text = d.get("text", "")
        ts   = d.get("ts", "")
        safe = text.replace("<", "&lt;").replace(">", "&gt;")
        parts.append(
            f'<div class="dec-card {t}">'
            f'{safe}'
            f'<div class="dec-time">{ts}</div>'
            f'</div>'
        )
    return "\n".join(parts)


def _add_decision(dtype: str, text: str):
    ts = time.strftime("%H:%M:%S")
    st.session_state.decisions.append({"type": dtype, "text": text, "ts": ts})
    if len(st.session_state.decisions) > 100:
        st.session_state.decisions = st.session_state.decisions[-100:]


# ── Gemini background worker ─────────────────────────────────────────────

def gemini_worker(api_key, sim_ref, frame_q, text_q, decision_q, action_q, stop_event):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _gemini_async(api_key, sim_ref, frame_q, text_q, decision_q, action_q, stop_event)
        )
    except Exception as e:
        decision_q.put({"type": "error", "text": f"Gemini error: {e}"})
    finally:
        loop.close()


async def _gemini_async(api_key, sim_ref, frame_q, text_q, decision_q, action_q, stop_event):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
    model  = "gemini-2.0-flash-live-001"

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.TEXT],
        system_instruction=types.Content(parts=[types.Part(text=get_system_prompt())]),
        tools=[{"function_declarations": get_tool_declarations()}],
    )

    async with client.aio.live.connect(model=model, config=config) as session:
        decision_q.put({"type": "system", "text": f"✅ Gemini Live connected ({model})"})

        async def _sender():
            while not stop_event.is_set():
                try:
                    jpeg = frame_q.get_nowait()
                    await session.send_realtime_input(
                        media=types.Blob(data=jpeg, mime_type="image/jpeg")
                    )
                except queue.Empty:
                    pass
                try:
                    text = text_q.get_nowait()
                    await session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=text)])
                    )
                except queue.Empty:
                    pass
                await asyncio.sleep(0.05)

        async def _receiver():
            async for response in session.receive():
                if stop_event.is_set():
                    break
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text and part.text.strip():
                            decision_q.put({"type": "decision", "text": part.text.strip()})
                if response.tool_call:
                    fn_responses = []
                    sim = sim_ref.get("sim")
                    for fc in response.tool_call.function_calls:
                        result = _execute_tool(fc.name, dict(fc.args), sim)
                        action_q.put({"tool": fc.name, "args": dict(fc.args), "result": result})
                        fn_responses.append(
                            types.FunctionResponse(name=fc.name, response={"result": result})
                        )
                    if fn_responses:
                        await session.send_tool_response(function_responses=fn_responses)

        await asyncio.gather(_sender(), _receiver())


def _execute_tool(name, args, sim):
    if sim is None:
        return {"error": "No simulation running"}
    if name == "control_exit":
        return sim.set_exit_status(args.get("exit_id", ""), args.get("action", "open"))
    elif name == "control_highway":
        action = args.get("action", "")
        if "outbound" in action:
            cap = args.get("capacity")
            if cap is None:
                cap = sim.highway.outbound_capacity + (20 if "increase" in action else -10)
            return sim.set_highway_capacity(int(cap))
        return sim.block_highway_inbound(action == "block_inbound")
    elif name == "redirect_building":
        return sim.redirect_building(args.get("building_id", ""), args.get("exit_id", ""))
    elif name == "get_status":
        return sim.to_dict()["stats"] | {
            "exits": [{"id": e.id, "status": e.status, "queue": e.queue_length} for e in sim.exits],
            "highway_congestion": sim.highway.congestion_level,
        }
    return {"error": f"Unknown tool: {name}"}


def start_gemini(sim: CityBlock):
    frame_q    = queue.Queue(maxsize=20)
    text_q     = queue.Queue(maxsize=20)
    decision_q = queue.Queue()
    action_q   = queue.Queue()
    stop_event = threading.Event()
    sim_ref    = {"sim": sim}

    for k, v in [("frame_q", frame_q), ("text_q", text_q),
                 ("decision_q", decision_q), ("action_q", action_q),
                 ("stop_event", stop_event), ("sim_ref", sim_ref)]:
        st.session_state[k] = v

    t = threading.Thread(
        target=gemini_worker,
        args=(st.session_state.api_key, sim_ref,
              frame_q, text_q, decision_q, action_q, stop_event),
        daemon=True,
    )
    t.start()
    st.session_state.gemini_thread = t

    exits_info = ", ".join(f"{e.id}({e.name})" for e in sim.exits)
    builds_info = ", ".join(f"{b.id}({b.total_population}ppl)" for b in sim.buildings)
    text_q.put(
        f"EVACUATION STARTED — evacuate all {len(sim.persons)} people ASAP.\n"
        f"Buildings: {builds_info}\nExits: {exits_info}\n"
        f"Highway capacity: {sim.highway.outbound_capacity} ppl/sec\n"
        f"Take action NOW: call get_status, issue redirect_building and control_highway commands."
    )


def stop_gemini():
    ev = st.session_state.get("stop_event")
    if ev:
        ev.set()
    st.session_state.gemini_thread = None


def drain_queues():
    dq = st.session_state.get("decision_q")
    aq = st.session_state.get("action_q")
    sim_ref = st.session_state.get("sim_ref", {})

    if dq:
        while not dq.empty():
            try:
                d = dq.get_nowait()
                _add_decision(d.get("type", "system"), d.get("text", ""))
            except queue.Empty:
                break

    if aq:
        while not aq.empty():
            try:
                act = aq.get_nowait()
                tool, args, res = act["tool"], act["args"], act["result"]
                if tool == "control_exit":
                    icon = "🟢" if args.get("action") == "open" else "🔴"
                    text = f"{icon} {args.get('action','').upper()} {args.get('exit_id','')} — {args.get('reason','')}"
                elif tool == "control_highway":
                    cap = args.get("capacity", "")
                    text = f"🛣 Highway {args.get('action','')} {f'→ {cap}/s' if cap else ''} — {args.get('reason','')}"
                elif tool == "redirect_building":
                    text = f"↗ Redirect {args.get('building_id','')} → {args.get('exit_id','')} — {args.get('reason','')}"
                elif tool == "get_status":
                    text = f"📊 Status check: {res.get('percent_complete','?')}% evacuated"
                else:
                    text = f"⚙ {tool}"
                if res.get("error"):
                    text += f" ⚠ {res['error']}"
                _add_decision("action", text)
                # Keep sim_ref current
                if st.session_state.sim:
                    sim_ref["sim"] = st.session_state.sim
            except queue.Empty:
                break


# ── Sidebar ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🚨 ExodusAI")
    st.caption("Gemini Live AI evacuation commander")
    st.divider()

    with st.expander("⚙️ Settings", expanded=not bool(st.session_state.api_key)):
        key_input = st.text_input("Gemini API Key", value=st.session_state.api_key,
                                  type="password", help="https://aistudio.google.com")
        if key_input != st.session_state.api_key:
            st.session_state.api_key = key_input
        if st.session_state.api_key:
            st.success("API key saved ✅")
        else:
            st.warning("API key required ⚠️")

    st.divider()
    st.markdown("### 🏙 Simulation")

    buildings   = st.slider("Buildings",              2,  10, st.session_state.config["buildings"])
    exits       = st.slider("Exits",                  1,   6, st.session_state.config["exits"])
    avg_pop     = st.slider("Population / Building", 10, 500, st.session_state.config["avg_pop"],     step=10)
    highway_out = st.slider("Highway Capacity (ppl/s)", 5, 100, st.session_state.config["highway_out"], step=5)

    st.divider()
    st.markdown("### ⏱ Time & Speed")
    time_scale = st.slider(
        "Time Scale (1 sim-sec = X real-min)", 1, 120,
        st.session_state.time_scale,
        help="Converts fast simulation time to realistic real-world minutes"
    )
    sim_speed = st.slider(
        "Simulation Speed (ticks/frame)", 1, 8,
        st.session_state.sim_speed,
        help="Higher = faster visual playback"
    )
    st.session_state.time_scale = time_scale
    st.session_state.sim_speed  = sim_speed

    st.divider()

    if st.button("🎲 Randomize", width="stretch"):
        import random
        buildings   = random.randint(2, 10)
        exits       = random.randint(2, 6)
        avg_pop     = random.randint(2, 50) * 10
        highway_out = random.randint(1, 20) * 5
        st.rerun()

    cfg = {"buildings": buildings, "exits": exits, "avg_pop": avg_pop, "highway_out": highway_out}
    st.session_state.config = cfg

    apply_btn = st.button("📋 Apply Config",    width="stretch", type="secondary")
    start_btn = st.button("▶ Start Evacuation", width="stretch", type="primary",
                          disabled=st.session_state.running)
    pause_btn = st.button("⏸ Pause / Resume",  width="stretch",
                          disabled=not st.session_state.running)
    reset_btn = st.button("↺ Reset",            width="stretch")

    st.divider()
    st.markdown("### 💬 Ask Gemini")
    ask_text = st.text_input("Question", placeholder="Why is E2 congested?",
                             label_visibility="hidden")
    ask_btn  = st.button("Ask", width="stretch")


# ── Button logic ──────────────────────────────────────────────────────────

if apply_btn or st.session_state.sim is None:
    stop_gemini()
    st.session_state.sim          = CityBlock(cfg)
    st.session_state.running      = False
    st.session_state.paused       = False
    st.session_state.decisions    = []
    st.session_state.tick_counter = 0
    _add_decision("system", f"Config applied — {cfg['buildings']} buildings, "
                  f"{cfg['exits']} exits, {cfg['avg_pop']} ppl/bldg, "
                  f"{cfg['highway_out']} ppl/s highway")

if start_btn and st.session_state.sim and not st.session_state.running:
    st.session_state.sim.start_evacuation()
    st.session_state.running      = True
    st.session_state.paused       = False
    st.session_state.tick_counter = 0
    if st.session_state.api_key:
        start_gemini(st.session_state.sim)
    else:
        _add_decision("alert", "⚠ No API key — running simulation without Gemini")

if pause_btn and st.session_state.running:
    st.session_state.paused = not st.session_state.paused

if reset_btn:
    stop_gemini()
    st.session_state.sim          = CityBlock(cfg)
    st.session_state.running      = False
    st.session_state.paused       = False
    st.session_state.tick_counter = 0
    st.session_state.decisions    = []
    _add_decision("system", "Simulation reset.")

if ask_btn and ask_text.strip():
    tq = st.session_state.get("text_q")
    if tq:
        tq.put(ask_text.strip())
    _add_decision("system", f"You: {ask_text.strip()}")


# ── Header ────────────────────────────────────────────────────────────────

sim: CityBlock | None = st.session_state.sim

st.markdown("""
<div class="exodus-header">
<span class="exodus-title">Exodus<span>AI</span></span>
&nbsp;&nbsp;
<span style="color:#666;font-size:0.85rem">Gemini Live-commanded emergency evacuation</span>
</div>
""", unsafe_allow_html=True)

# ── Main layout ───────────────────────────────────────────────────────────

left_col, right_col = st.columns([3, 2], gap="medium")

with left_col:
    sim_img_slot  = st.empty()
    maps_img_slot = st.empty()

with right_col:
    # ── Status badge ──
    status_slot = st.empty()

    # ── Metrics row ──
    m1, m2, m3 = st.columns(3)
    metric_time    = m1.empty()
    metric_evac    = m2.empty()
    metric_highway = m3.empty()

    m4, m5, m6 = st.columns(3)
    metric_pct     = m4.empty()
    metric_transit = m5.empty()
    metric_speed   = m6.empty()

    # ── Progress bar ──
    st.markdown("**Evacuation Progress**")
    progress_slot = st.empty()

    # ── Decisions ──
    st.markdown("---")
    st.markdown("#### 🤖 Gemini Commander")
    decisions_slot = st.empty()


# ── Simulation tick loop ──────────────────────────────────────────────────

GEMINI_FRAME_EVERY  = 3
GEMINI_MAPS_EVERY   = 20
MAPS_DISPLAY_EVERY  = 15

if sim:
    # Advance simulation
    if st.session_state.running and not st.session_state.paused:
        for _ in range(st.session_state.sim_speed):
            if sim.running:
                sim.step()
                st.session_state.tick_counter += 1
                tc = st.session_state.tick_counter

                sim_dict = sim.to_dict()

                # Feed frames to Gemini
                if tc % GEMINI_FRAME_EVERY == 0:
                    fq = st.session_state.get("frame_q")
                    if fq:
                        try:
                            fq.put_nowait(render_frame(sim_dict))
                        except queue.Full:
                            pass

                if tc % GEMINI_MAPS_EVERY == 0:
                    fq = st.session_state.get("frame_q")
                    tq = st.session_state.get("text_q")
                    if fq:
                        try:
                            fq.put_nowait(render_maps_frame(sim_dict))
                        except queue.Full:
                            pass
                    if tq:
                        try:
                            tq.put_nowait(f"[TRAFFIC MAP] {sim.summary_text()} | roads: {sim.get_road_traffic()}")
                        except queue.Full:
                            pass

                # Congestion alerts
                for alert in sim.get_new_alerts():
                    _add_decision("alert", f"⚠ {alert['message']}")
                    tq = st.session_state.get("text_q")
                    if tq:
                        try:
                            tq.put_nowait(f"ALERT: {alert['message']}. {sim.summary_text()}")
                        except queue.Full:
                            pass

                # Milestones
                for m in sim.get_new_milestones():
                    _add_decision("alert", f"✅ {m}")
                    tq = st.session_state.get("text_q")
                    if tq:
                        try:
                            tq.put_nowait(f"MILESTONE: {m}")
                        except queue.Full:
                            pass

        if not sim.running:
            st.session_state.running = False
            stop_gemini()

    drain_queues()

    sim_dict = sim.to_dict()
    stats    = sim_dict["stats"]
    hw       = sim_dict["highway"]
    pct      = stats["percent_complete"]
    elapsed  = stats["elapsed_seconds"]
    total    = stats["total"]
    evac     = stats["evacuated"]
    ts       = st.session_state.time_scale
    cong     = hw.get("congestion", "clear").upper()

    real_time_str = _sim_time_display(elapsed, ts)

    # ── Status badge ──
    if not sim.running and evac == total and total > 0:
        badge = '<span class="status-badge badge-complete">✅ COMPLETE</span>'
    elif st.session_state.paused:
        badge = '<span class="status-badge badge-paused">⏸ PAUSED</span>'
    elif st.session_state.running:
        badge = '<span class="status-badge badge-running">🔴 EVACUATING</span>'
    else:
        badge = '<span class="status-badge badge-ready">⚪ READY</span>'

    status_slot.markdown(badge, unsafe_allow_html=True)

    # ── Metrics ──
    metric_time.metric("⏱ Equiv. Real Time",
                       real_time_str,
                       help=f"1 sim-sec = {ts} real min ({elapsed:.1f} sim-sec)")
    metric_evac.metric("👥 Evacuated", f"{evac}/{total}")
    metric_highway.metric("🛣 Highway", cong, delta=f"Q:{hw['queue']}")
    metric_pct.metric("📊 Progress", f"{pct:.1f}%")
    metric_transit.metric("🚶 In Transit", stats.get("in_transit", 0))
    metric_speed.metric("⚡ Sim Speed", f"{st.session_state.sim_speed}×")

    # ── Progress bar ──
    progress_slot.progress(min(pct / 100, 1.0))

    # ── Render images ──
    with left_col:
        sim_jpeg = render_frame(sim_dict)
        sim_img_slot.image(_jpeg_to_pil(sim_jpeg), caption="🏙 Simulation View", width="stretch")

        tc = st.session_state.tick_counter
        if tc % MAPS_DISPLAY_EVERY == 0 or tc == 0 or not st.session_state.running:
            maps_jpeg = render_maps_frame(sim_dict)
            maps_img_slot.image(_jpeg_to_pil(maps_jpeg), caption="🗺 Traffic Map (Simulated)", width="stretch")

    # ── Decisions log ──
    decisions_slot.markdown(
        _decision_html(st.session_state.decisions),
        unsafe_allow_html=True,
    )

# ── Auto-rerun while running ──────────────────────────────────────────────
if st.session_state.running and not st.session_state.paused:
    time.sleep(0.10)
    st.rerun()
