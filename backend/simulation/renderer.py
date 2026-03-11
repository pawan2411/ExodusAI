"""OpenCV renderer: converts simulation state dict → JPEG bytes."""

import cv2
import numpy as np

from simulation.city_block import (
    CANVAS_W, CANVAS_H, BLOCK_X1, BLOCK_X2, BLOCK_Y1, BLOCK_Y2,
    STATS_H, HIGHWAY_H, BLOCK_W, BLOCK_H,
)

# BGR color palette
BG            = (22, 22, 32)
ROAD          = (42, 44, 54)
BLOCK_BORDER  = (70, 75, 100)
BUILDING_FILL = (48, 58, 88)
BUILDING_BDR  = (90, 110, 160)
EXIT_OPEN     = (40, 200, 60)
EXIT_CLOSED   = (40, 50, 210)
EXIT_CONGESTED= (30, 140, 220)
EXIT_TEXT     = (240, 240, 255)
AGENT_MOVING  = (40, 210, 190)   # teal
AGENT_QUEUED  = (40, 110, 230)   # orange-ish
HIGHWAY_BG    = (18, 28, 40)
HIGHWAY_QUEUE = (30, 150, 230)
HIGHWAY_EVAC  = (40, 200, 80)
STATS_BG      = (12, 12, 22)
STATS_TEXT    = (200, 210, 230)
ACCENT        = (120, 160, 255)
FONT          = cv2.FONT_HERSHEY_SIMPLEX


def render_frame(state: dict) -> bytes:
    """Render a simulation state dict to JPEG bytes."""
    frame = np.full((CANVAS_H, CANVAS_W, 3), BG, dtype=np.uint8)

    _draw_stats_bar(frame, state)
    _draw_highway(frame, state)
    _draw_city_block(frame)
    _draw_buildings(frame, state)
    _draw_agents(frame, state)
    _draw_exits(frame, state)

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes()


# ── Drawing helpers ──────────────────────────────────────────────────────

def _draw_stats_bar(frame, state):
    cv2.rectangle(frame, (0, 0), (CANVAS_W, STATS_H), STATS_BG, -1)
    cv2.line(frame, (0, STATS_H), (CANVAS_W, STATS_H), BLOCK_BORDER, 1)

    stats = state.get("stats", {})
    pct = stats.get("percent_complete", 0.0)
    total = stats.get("total", 0)
    evacuated = stats.get("evacuated", 0)
    elapsed = stats.get("elapsed_seconds", 0)
    running = state.get("running", False)

    # Title
    cv2.putText(frame, "EvacuAI", (16, 36), FONT, 0.85, ACCENT, 2)

    # Status label
    if running:
        status_label, status_color = "EVACUATING", (40, 200, 220)
    elif evacuated == total and total > 0:
        status_label, status_color = "COMPLETE", (40, 210, 80)
    else:
        status_label, status_color = "READY", (130, 130, 150)

    cv2.putText(frame, f"| {status_label}  People: {evacuated}/{total}  Time: {int(elapsed)}s",
                (120, 36), FONT, 0.5, status_color, 1)

    # Progress bar (right side)
    bar_w, bar_h = 280, 18
    bar_x = CANVAS_W - bar_w - 20
    bar_y = (STATS_H - bar_h) // 2
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (40, 42, 55), -1)
    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), BLOCK_BORDER, 1)
    fill = int(bar_w * pct / 100)
    if fill > 0:
        bar_color = (40, 210, 80) if pct > 80 else (40, 180, 220) if pct > 40 else (40, 120, 240)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill, bar_y + bar_h), bar_color, -1)
    cv2.putText(frame, f"{pct:.0f}%", (bar_x + bar_w + 6, bar_y + 14), FONT, 0.5, STATS_TEXT, 1)


def _draw_highway(frame, state):
    hw_y1, hw_y2 = BLOCK_Y2, CANVAS_H
    cv2.rectangle(frame, (0, hw_y1), (CANVAS_W, hw_y2), HIGHWAY_BG, -1)
    cv2.line(frame, (0, hw_y1), (CANVAS_W, hw_y1), BLOCK_BORDER, 1)

    # Road markings
    for x in range(0, CANVAS_W, 60):
        cv2.line(frame, (x, hw_y1 + 40), (x + 30, hw_y1 + 40), (60, 65, 80), 2)

    hw = state.get("highway", {})
    q = hw.get("queue", 0)
    evac = hw.get("evacuated", 0)
    cap = hw.get("outbound_capacity", 20)
    cong = hw.get("congestion", "clear")
    inbound_blocked = hw.get("inbound_blocked", False)

    # Queue dots (up to 72)
    for i in range(min(q, 72)):
        dx = 80 + (i % 36) * 18
        dy = hw_y1 + 12 + (i // 36) * 18
        cv2.circle(frame, (dx, dy), 4, HIGHWAY_QUEUE, -1)

    cong_color = {
        "clear":    (40, 200, 80),
        "moderate": (30, 170, 220),
        "heavy":    (40, 50, 220),
    }.get(cong, STATS_TEXT)

    info = (
        f"HIGHWAY  |  Queue: {q}  |  Evacuated: {evac}  "
        f"|  Capacity: {cap}/s  |  {cong.upper()}"
        + ("  |  INBOUND BLOCKED" if inbound_blocked else "")
    )
    cv2.putText(frame, info, (8, hw_y2 - 10), FONT, 0.42, cong_color, 1)


def _draw_city_block(frame):
    cv2.rectangle(frame, (BLOCK_X1, BLOCK_Y1), (BLOCK_X2, BLOCK_Y2), ROAD, -1)
    cv2.rectangle(frame, (BLOCK_X1, BLOCK_Y1), (BLOCK_X2, BLOCK_Y2), BLOCK_BORDER, 2)


def _draw_buildings(frame, state):
    for b in state.get("buildings", []):
        x, y, w, h = int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"])
        x1, y1, x2, y2 = x - w // 2, y - h // 2, x + w // 2, y + h // 2

        cv2.rectangle(frame, (x1, y1), (x2, y2), BUILDING_FILL, -1)
        cv2.rectangle(frame, (x1, y1), (x2, y2), BUILDING_BDR, 2)

        # Building ID
        cv2.putText(frame, b["id"], (x - 13, y - 6), FONT, 0.45, (180, 200, 225), 1)

        # Remaining count
        remaining = b.get("remaining", 0)
        rem_color = (40, 210, 80) if remaining == 0 else (40, 170, 230)
        cv2.putText(frame, str(remaining), (x - 8, y + 14), FONT, 0.55, rem_color, 1)


def _draw_agents(frame, state):
    for ag in state.get("agents", []):
        ax, ay = int(ag["x"]), int(ag["y"])
        status = ag["status"]
        if ax < 0 or ay < 0 or ax >= CANVAS_W or ay >= CANVAS_H:
            continue
        color = AGENT_MOVING if status == "evacuating" else AGENT_QUEUED
        cv2.circle(frame, (ax, ay), 2, color, -1)


def _draw_exits(frame, state):
    for e in state.get("exits", []):
        ex, ey = int(e["x"]), int(e["y"])
        status = e["status"]
        congested = e.get("congested", False)
        queue = e.get("queue", 0)

        if status == "closed":
            color = EXIT_CLOSED
        elif congested:
            color = EXIT_CONGESTED
        else:
            color = EXIT_OPEN

        cv2.circle(frame, (ex, ey), 15, color, -1)
        cv2.circle(frame, (ex, ey), 15, (220, 225, 255), 1)

        # Label inside circle
        eid = e["id"]
        cv2.putText(frame, eid, (ex - 12, ey + 5), FONT, 0.38, EXIT_TEXT, 1)

        # Status below exit
        label = "CLOSED" if status == "closed" else f"Q:{queue}"
        label_color = EXIT_CLOSED if status == "closed" else (EXIT_CONGESTED if congested else EXIT_OPEN)
        cv2.putText(frame, label, (ex - 16, ey + 28), FONT, 0.38, label_color, 1)
