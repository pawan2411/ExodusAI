"""Video simulation timeline controller.

Plays pre-recorded video with hazard injection at specified timestamps.
Falls back to synthetic frames when the video file is missing.
"""

import asyncio
import logging
import time

import cv2
import numpy as np

from simulation.hazard_overlays import (
    apply_smoke_overlay,
    apply_fire_glow,
    apply_crowd_markers,
    apply_blocked_exit_marker,
    apply_status_bar,
)

logger = logging.getLogger(__name__)

# Default scenario timeline: timestamp (seconds) -> event
DEFAULT_TIMELINE = [
    {"time": 0,   "event": "normal",         "description": "All clear - normal operations"},
    {"time": 30,  "event": "smoke_detected",  "description": "Smoke detected in north corridor",
     "overlay": "smoke", "intensity": 0.3},
    {"time": 60,  "event": "smoke_increasing", "description": "Smoke intensity increasing",
     "overlay": "smoke", "intensity": 0.6},
    {"time": 90,  "event": "fire_visible",    "description": "Fire visible in east wing",
     "overlay": "fire", "position": (400, 250)},
    {"time": 120, "event": "exit_blocked",    "description": "North exit blocked by debris",
     "overlay": "blocked", "position": (320, 200)},
    {"time": 150, "event": "crowd_gathering", "description": "Crowd gathering at south exit",
     "overlay": "crowd", "count": 50},
    {"time": 180, "event": "evacuation_complete", "description": "Evacuation routes clear"},
]


class VideoSimulator:
    """Plays video frames with hazard overlays on a timeline."""

    def __init__(
        self,
        video_path: str | None = None,
        timeline: list[dict] | None = None,
        target_fps: float = 1.0,
        frame_size: tuple[int, int] = (768, 768),
    ):
        self.video_path = video_path
        self.timeline = timeline or DEFAULT_TIMELINE
        self.target_fps = target_fps
        self.frame_size = frame_size
        self.cap = None
        self.start_time = None
        self.frame_count = 0
        self._use_synthetic = False

        self._init_video()

    def _init_video(self):
        """Initialize video capture or fall back to synthetic frames."""
        if self.video_path:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                logger.warning(
                    f"Could not open video: {self.video_path}. "
                    "Falling back to synthetic frames."
                )
                self.cap = None
                self._use_synthetic = True
            else:
                logger.info(f"Video loaded: {self.video_path}")
        else:
            self._use_synthetic = True
            logger.info("No video path provided. Using synthetic frames.")

    def _generate_synthetic_frame(self, elapsed: float) -> np.ndarray:
        """Generate a synthetic frame with status text."""
        w, h = self.frame_size
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Dark blue-gray background
        frame[:] = (40, 35, 30)

        # Grid lines for a "building floor plan" look
        for x in range(0, w, 80):
            cv2.line(frame, (x, 0), (x, h), (60, 55, 50), 1)
        for y in range(0, h, 80):
            cv2.line(frame, (0, y), (w, y), (60, 55, 50), 1)

        # Title
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, "ExodusAI - Simulation Mode", (50, 60),
                    font, 1.0, (200, 200, 200), 2)

        # Floor plan outline
        cv2.rectangle(frame, (100, 100), (w - 100, h - 100), (100, 100, 100), 2)

        # Exits
        cv2.rectangle(frame, (w // 2 - 30, 95), (w // 2 + 30, 105), (0, 255, 0), -1)
        cv2.putText(frame, "EXIT A (N)", (w // 2 - 60, 88), font, 0.5, (0, 255, 0), 1)

        cv2.rectangle(frame, (w // 2 - 30, h - 105), (w // 2 + 30, h - 95), (0, 255, 0), -1)
        cv2.putText(frame, "EXIT B (S)", (w // 2 - 60, h - 75), font, 0.5, (0, 255, 0), 1)

        cv2.rectangle(frame, (w - 105, h // 2 - 30), (w - 95, h // 2 + 30), (0, 255, 0), -1)
        cv2.putText(frame, "EXIT C (E)", (w - 160, h // 2 - 40), font, 0.5, (0, 255, 0), 1)

        # Corridors
        cv2.rectangle(frame, (150, h // 2 - 20), (w - 150, h // 2 + 20), (80, 80, 80), -1)
        cv2.rectangle(frame, (w // 2 - 20, 150), (w // 2 + 20, h - 150), (80, 80, 80), -1)

        # Time display
        cv2.putText(frame, f"Time: {int(elapsed)}s", (50, h - 30),
                    font, 0.6, (150, 150, 150), 1)

        return frame

    def get_current_event(self, elapsed: float) -> dict | None:
        """Get the active event at the given timestamp."""
        current = None
        for event in self.timeline:
            if elapsed >= event["time"]:
                current = event
            else:
                break
        return current

    def _apply_overlays(self, frame: np.ndarray, event: dict) -> np.ndarray:
        """Apply hazard overlays based on the current event."""
        overlay_type = event.get("overlay")
        if not overlay_type:
            return frame

        if overlay_type == "smoke":
            frame = apply_smoke_overlay(frame, intensity=event.get("intensity", 0.4))
        elif overlay_type == "fire":
            pos = event.get("position", (300, 200))
            frame = apply_fire_glow(frame, position=pos, intensity=event.get("intensity", 0.5))
        elif overlay_type == "blocked":
            pos = event.get("position", (320, 240))
            frame = apply_blocked_exit_marker(frame, position=pos)
        elif overlay_type == "crowd":
            count = event.get("count", 30)
            frame = apply_crowd_markers(frame, count=count)

        return frame

    async def get_frame(self) -> tuple[bytes, dict | None]:
        """Get the next frame as JPEG bytes and the current event.

        Returns:
            Tuple of (jpeg_bytes, current_event_dict_or_None).
        """
        if self.start_time is None:
            self.start_time = time.time()

        elapsed = time.time() - self.start_time

        # Get the raw frame
        if self._use_synthetic:
            frame = self._generate_synthetic_frame(elapsed)
        else:
            ret, frame = self.cap.read()
            if not ret:
                # Loop the video
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if not ret:
                    frame = self._generate_synthetic_frame(elapsed)

        # Resize to target dimensions
        frame = cv2.resize(frame, self.frame_size)

        # Apply event overlays
        event = self.get_current_event(elapsed)
        if event:
            frame = self._apply_overlays(frame, event)
            frame = apply_status_bar(frame, f"EVENT: {event['description']}")

        # Encode as JPEG
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        jpeg_bytes = buffer.tobytes()

        self.frame_count += 1
        return jpeg_bytes, event

    def reset(self):
        """Reset the simulation to the beginning."""
        self.start_time = None
        self.frame_count = 0
        if self.cap:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def close(self):
        """Release video resources."""
        if self.cap:
            self.cap.release()
