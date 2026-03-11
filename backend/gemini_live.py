"""Gemini Live API session wrapper — text-mode simulation agent.

Uses Google Cloud Vertex AI as the backend for Gemini model access,
providing enterprise-grade authentication via service accounts and
integration with GCP's AI platform.
"""

import asyncio
import logging
import os
from typing import Callable, Optional

from google import genai
from google.genai import types

from agents.evac_agent import get_system_prompt, get_tool_declarations

logger = logging.getLogger(__name__)

# Text-mode model for Live API
DEFAULT_MODEL = "gemini-2.0-flash-live-001"


class GeminiLiveSession:
    """Manages a single Gemini Live API session via Vertex AI (text in, text out + tools)."""

    def __init__(self, simulation_state: Optional[dict] = None):
        # Vertex AI requires GCP project and location
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        if not project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT environment variable is required. "
                "Set it to your GCP project ID for Vertex AI access."
            )

        # Initialize the GenAI client with Vertex AI backend
        # Authentication uses Application Default Credentials (ADC):
        #   - Local dev: `gcloud auth application-default login`
        #   - Cloud Run:  attached service account (automatic)
        self.client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options={"api_version": "v1alpha"},
        )
        self.model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.session = None
        self._closed = False
        # Mutable dict holding {"simulation": CityBlock | None}
        self.simulation_state = simulation_state or {}
        logger.info(
            f"Vertex AI client initialized (project={project}, location={location})"
        )

    async def connect(self):
        """Establish the Live API session in text mode."""
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            system_instruction=types.Content(
                parts=[types.Part(text=get_system_prompt())]
            ),
            tools=[{"function_declarations": get_tool_declarations()}],
        )
        logger.info(f"Connecting to Gemini Live API (text mode): {self.model}")
        self.session = await self.client.aio.live.connect(
            model=self.model, config=config
        )
        logger.info("Gemini Live session established")

    async def send_video_frame(self, jpeg_bytes: bytes):
        """Send a JPEG frame of the simulation to the Live API."""
        if not self.session or self._closed:
            return
        try:
            await self.session.send_realtime_input(
                media=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
            )
        except Exception as e:
            logger.error(f"Error sending video frame: {e}")

    async def send_text(self, text: str):
        """Send a text message to the Live API."""
        if not self.session or self._closed:
            return
        try:
            await self.session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=text)],
                )
            )
        except Exception as e:
            logger.error(f"Error sending text: {e}")

    async def receive_responses(
        self,
        on_text: Callable[[str], None],
        on_action: Callable[[dict], None],
    ):
        """Stream responses from Gemini.

        Args:
            on_text: Called with text decisions from Gemini.
            on_action: Called with action result dicts when tools are executed.
        """
        if not self.session:
            return
        try:
            async for response in self.session.receive():
                if self._closed:
                    break

                # Text content
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.text and part.text.strip():
                            await on_text(part.text.strip())

                # Tool calls
                if response.tool_call:
                    await self._handle_tool_calls(response.tool_call, on_action)

        except Exception as e:
            if not self._closed:
                logger.error(f"Receive loop error: {e}")
                raise

    async def _handle_tool_calls(self, tool_call, on_action: Callable):
        """Execute simulation tool calls and respond to the model."""
        function_responses = []
        sim = self.simulation_state.get("simulation")

        for fc in tool_call.function_calls:
            logger.info(f"Tool: {fc.name}({fc.args})")
            result = await self._execute_tool(fc.name, dict(fc.args), sim)

            # Notify frontend of the action
            await on_action({
                "tool": fc.name,
                "args": dict(fc.args),
                "result": result,
            })

            function_responses.append(
                types.FunctionResponse(name=fc.name, response={"result": result})
            )

        if function_responses and self.session and not self._closed:
            try:
                await self.session.send_tool_response(function_responses=function_responses)
            except Exception as e:
                logger.error(f"Error sending tool responses: {e}")

    async def _execute_tool(self, name: str, args: dict, sim) -> dict:
        """Dispatch tool call to the simulation."""
        if sim is None:
            return {"error": "Simulation not running"}

        if name == "control_exit":
            return sim.set_exit_status(args.get("exit_id", ""), args.get("action", "open"))

        elif name == "control_highway":
            action = args.get("action", "")
            if action in ("increase_outbound", "decrease_outbound"):
                capacity = args.get("capacity")
                if capacity is None:
                    current = sim.highway.outbound_capacity
                    capacity = current + 20 if action == "increase_outbound" else max(5, current - 10)
                return sim.set_highway_capacity(int(capacity))
            elif action == "block_inbound":
                return sim.block_highway_inbound(True)
            elif action == "unblock_inbound":
                return sim.block_highway_inbound(False)
            return {"error": f"Unknown highway action: {action}"}

        elif name == "redirect_building":
            return sim.redirect_building(
                args.get("building_id", ""),
                args.get("exit_id", ""),
            )

        elif name == "get_status":
            return sim.to_dict()["stats"] | {
                "exits": [
                    {"id": e.id, "status": e.status, "queue": e.queue_length}
                    for e in sim.exits
                ],
                "highway_congestion": sim.highway.congestion_level,
            }

        return {"error": f"Unknown tool: {name}"}

    async def close(self):
        self._closed = True
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                logger.debug(f"Session close error: {e}")
            self.session = None
        logger.info("Gemini Live session closed")
