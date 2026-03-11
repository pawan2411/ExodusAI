"""Simulated Google Maps-style traffic image renderer.

Generates a bird's-eye traffic view using simulation state,
styled to look like Google Maps dark-mode with traffic overlay.
"""

import cv2
import numpy as np
import math

# Canvas size
W, H = 520, 420

# ── Google Maps dark-theme palette (BGR) ──────────────────────────────
BG          = (32, 34, 40)      # Very dark base
LAND        = (40, 42, 50)      # Land fill
BLOCK_FILL  = (52, 56, 70)      # City block highlight
BLOCK_BDR   = (80, 85, 105)
PARK        = (38, 54, 42)      # Park green
BUILDING    = (55, 58, 72)      # Surrounding buildings (grey squares)
ROAD_LOCAL  = (62, 66, 80)      # Local street fill
ROAD_BDR    = (90, 95, 115)     # Road border/outline
HIGHWAY_BG  = (55, 62, 85)      # Highway fill
TEXT_WHITE  = (235, 240, 250)
TEXT_GRAY   = (130, 138, 160)
TEXT_ROAD   = (210, 218, 235)   # Road labels
LABEL_BG    = (42, 45, 58)      # Label pill background
ACCENT      = (100, 150, 255)   # EvacuAI pin accent

# ── Traffic colors (BGR) ────────────────────────────────────────────
T_CLEAR    = (60, 200, 80)      # Green
T_MODERATE = (30, 170, 230)     # Amber/yellow
T_HEAVY    = (40, 55, 220)      # Red
T_BLOCKED  = (25, 28, 160)      # Dark red

# ── Pin colors ───────────────────────────────────────────────────────
PIN_OPEN      = (50, 210, 70)
PIN_CLOSED    = (40, 45, 215)
PIN_CONGESTED = (35, 145, 225)

FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SMALL = cv2.FONT_HERSHEY_SIMPLEX

# ── Fixed map layout (pixels) ────────────────────────────────────────
# City block sits in center-left
BLK_X1, BLK_Y1 = 160, 90
BLK_X2, BLK_Y2 = 360, 280
BLK_W = BLK_X2 - BLK_X1   # 200
BLK_H = BLK_Y2 - BLK_Y1   # 190

# Roads around the block
STREET_L = 120     # Left N-S arterial x
STREET_R = 400     # Right N-S arterial x
STREET_T = 55      # Top E-W arterial y
STREET_B = 320     # Bottom E-W road y (feeds highway)

# Highway at bottom
HW_Y1, HW_Y2 = 355, 390
HW_CY = (HW_Y1 + HW_Y2) // 2
HW_LANE_W = 8   # each lane width for traffic coloring


def _traffic_color(level: str) -> tuple:
    return {
        "clear":    T_CLEAR,
        "moderate": T_MODERATE,
        "heavy":    T_HEAVY,
        "blocked":  T_BLOCKED,
    }.get(level, T_CLEAR)


def _road_label(frame, text: str, cx: int, cy: int, angle: float = 0):
    """Draw a Google Maps-style road label pill."""
    (tw, th), _ = cv2.getTextSize(text, FONT_SMALL, 0.38, 1)
    pad = 3
    x1 = cx - tw // 2 - pad
    y1 = cy - th // 2 - pad
    x2 = cx + tw // 2 + pad
    y2 = cy + th // 2 + pad
    cv2.rectangle(frame, (x1, y1), (x2, y2), LABEL_BG, -1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), ROAD_BDR, 1)
    cv2.putText(frame, text, (cx - tw // 2, cy + th // 2 - 1), FONT_SMALL, 0.38, TEXT_ROAD, 1)


def _draw_traffic_band(frame, pt1, pt2, level: str, width: int = 5):
    """Draw a traffic-colored band along a road segment."""
    color = _traffic_color(level)
    cv2.line(frame, pt1, pt2, color, width)


def _draw_pin(frame, x: int, y: int, label: str, color: tuple):
    """Draw a Google Maps-style location pin."""
    # Circle with stem
    cv2.circle(frame, (x, y - 12), 10, color, -1)
    cv2.circle(frame, (x, y - 12), 10, TEXT_WHITE, 1)
    cv2.line(frame, (x, y - 2), (x, y + 4), color, 3)
    # Label
    (tw, _), _ = cv2.getTextSize(label, FONT_SMALL, 0.35, 1)
    cv2.putText(frame, label, (x - tw // 2, y - 8), FONT_SMALL, 0.35, TEXT_WHITE, 1)


def _exit_map_pos(exit_dict: dict, sim_block_bounds: dict) -> tuple:
    """Map a simulation exit position to maps canvas coordinates."""
    sx1 = sim_block_bounds["x1"]
    sy1 = sim_block_bounds["y1"]
    sw  = sim_block_bounds["w"]
    sh  = sim_block_bounds["h"]

    fx = (exit_dict["x"] - sx1) / sw   # 0.0-1.0
    fy = (exit_dict["y"] - sy1) / sh   # 0.0-1.0

    mx = int(BLK_X1 + fx * BLK_W)
    my = int(BLK_Y1 + fy * BLK_H)

    # Clamp to block boundary
    mx = max(BLK_X1 - 5, min(BLK_X2 + 5, mx))
    my = max(BLK_Y1 - 5, min(BLK_Y2 + 5, my))
    return (mx, my)


def render_maps_frame(state: dict) -> bytes:
    """Render a Google Maps-style traffic view from simulation state."""
    frame = np.full((H, W, 3), BG, dtype=np.uint8)

    exits  = state.get("exits", [])
    hw     = state.get("highway", {})
    stats  = state.get("stats", {})
    builds = state.get("buildings", [])

    road_traffic = _compute_road_traffic(exits, hw)

    _draw_surroundings(frame)
    _draw_local_streets(frame, road_traffic)
    _draw_highway(frame, hw, road_traffic)
    _draw_city_block(frame, builds, stats)
    _draw_exits(frame, exits, state)
    _draw_hud(frame, stats, hw)

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return buf.tobytes()


def _compute_road_traffic(exits: list, hw: dict) -> dict:
    """Derive road traffic levels from simulation state."""
    # Start with highway
    traffic = {
        "highway":       hw.get("congestion", "clear"),
        "highway_inbound": "blocked" if hw.get("inbound_blocked") else "clear",
        "north":  "clear",
        "south":  "clear",
        "east":   "clear",
        "west":   "clear",
        "south_approach": "clear",   # road feeding into highway
    }

    # Exits drive approach road traffic
    for e in exits:
        name = e.get("name", "")
        q = e.get("queue", 0)
        congested = e.get("congested", False)
        level = "heavy" if congested else ("moderate" if q > 5 else "clear")
        if "(N)" in name:
            traffic["north"] = _worse(traffic["north"], level)
        elif "(S)" in name:
            traffic["south"] = _worse(traffic["south"], level)
            traffic["south_approach"] = _worse(traffic["south_approach"], level)
        elif "(E)" in name:
            traffic["east"] = _worse(traffic["east"], level)
        elif "(W)" in name:
            traffic["west"] = _worse(traffic["west"], level)

    # Highway inbound congestion spills into south approach
    if hw.get("congestion") == "heavy":
        traffic["south_approach"] = _worse(traffic["south_approach"], "moderate")

    return traffic


def _worse(a: str, b: str) -> str:
    order = {"clear": 0, "moderate": 1, "heavy": 2, "blocked": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def _draw_surroundings(frame):
    """Draw surrounding city blocks, parks, etc. for context."""
    # Base land
    cv2.rectangle(frame, (0, 0), (W, H), LAND, -1)

    # Surrounding "buildings" (grey blobs)
    surrounding_rects = [
        (10, 10,  90, 45), (10, 55,  60, 85), (10, 95,  90, 130),
        (10, 145, 70, 180), (10, 200, 90, 240), (10, 250, 60, 280),
        (10, 295, 90, 330),
        (430, 10, 510, 45), (440, 60, 510, 95), (430, 110, 510, 150),
        (440, 170, 510, 210), (430, 225, 510, 270), (440, 295, 510, 340),
        (170, 10, 210, 45), (240, 10, 290, 48), (320, 10, 370, 48), (400, 10, 450, 48),
        (170, 295, 210, 340), (240, 295, 290, 340), (320, 295, 370, 340),
    ]
    for r in surrounding_rects:
        cv2.rectangle(frame, (r[0], r[1]), (r[2], r[3]), BUILDING, -1)

    # Small park (green)
    cv2.rectangle(frame, (440, 120), (510, 200), PARK, -1)
    cv2.putText(frame, "Park", (450, 165), FONT_SMALL, 0.38, (80, 140, 80), 1)


def _draw_local_streets(frame, road_traffic: dict):
    """Draw local streets and arterials with traffic colors."""
    road_w = 12    # Arterial width
    local_w = 8    # Local street

    # ── Draw road fill (dark) ──
    # Left N-S arterial
    cv2.line(frame, (STREET_L, 0), (STREET_L, HW_Y1), ROAD_LOCAL, road_w + 4)
    # Right N-S arterial
    cv2.line(frame, (STREET_R, 0), (STREET_R, HW_Y1), ROAD_LOCAL, road_w + 4)
    # Top E-W
    cv2.line(frame, (0, STREET_T), (W, STREET_T), ROAD_LOCAL, road_w + 4)
    # Bottom E-W (feeds highway)
    cv2.line(frame, (0, STREET_B), (W, STREET_B), ROAD_LOCAL, road_w + 4)

    # ── Traffic color overlays ──
    # North approach (above block)
    north_seg = ((BLK_X1 + BLK_X2) // 2, STREET_T), ((BLK_X1 + BLK_X2) // 2, BLK_Y1)
    _draw_traffic_band(frame, north_seg[0], north_seg[1], road_traffic["north"], 7)

    # South approach (block → bottom street)
    south_cx = (BLK_X1 + BLK_X2) // 2
    _draw_traffic_band(frame, (south_cx, BLK_Y2), (south_cx, STREET_B), road_traffic["south"], 7)

    # East approach
    _draw_traffic_band(frame, (BLK_X2, (BLK_Y1 + BLK_Y2) // 2), (STREET_R, (BLK_Y1 + BLK_Y2) // 2), road_traffic["east"], 7)
    # West approach
    _draw_traffic_band(frame, (STREET_L, (BLK_Y1 + BLK_Y2) // 2), (BLK_X1, (BLK_Y1 + BLK_Y2) // 2), road_traffic["west"], 7)

    # Bottom road → highway connection (south approach)
    _draw_traffic_band(frame, (0, STREET_B), (W, STREET_B), road_traffic["south_approach"], 6)

    # Road labels
    _road_label(frame, "Oak Ave",    STREET_L,              200)
    _road_label(frame, "Pine St",    STREET_R,              200)
    _road_label(frame, "Main St",    (BLK_X1 + BLK_X2)//2, STREET_T - 5)
    _road_label(frame, "Elm St",     (BLK_X1 + BLK_X2)//2, STREET_B + 12)


def _draw_highway(frame, hw: dict, road_traffic: dict):
    """Draw the highway strip with traffic coloring."""
    # Highway body
    cv2.rectangle(frame, (0, HW_Y1), (W, HW_Y2), HIGHWAY_BG, -1)
    cv2.line(frame, (0, HW_Y1), (W, HW_Y1), ROAD_BDR, 1)
    cv2.line(frame, (0, HW_Y2), (W, HW_Y2), ROAD_BDR, 1)

    # Outbound lanes (lower half)
    out_color = _traffic_color(road_traffic["highway"])
    out_y = HW_Y1 + (HW_Y2 - HW_Y1) // 2
    cv2.line(frame, (0, out_y), (W, out_y), out_color, HW_LANE_W)

    # Inbound lanes (upper half)
    in_color = _traffic_color(road_traffic["highway_inbound"])
    in_y = HW_Y1 + (HW_Y2 - HW_Y1) // 4
    cv2.line(frame, (0, in_y), (W, in_y), in_color, HW_LANE_W)

    # Center divider dashes
    for x in range(0, W, 40):
        cv2.line(frame, (x, HW_CY), (x + 20, HW_CY), ROAD_BDR, 1)

    # Traffic flow arrows
    for x in range(40, W - 40, 80):
        # Outbound →
        cv2.arrowedLine(frame, (x, out_y), (x + 22, out_y), (180, 185, 200), 1, tipLength=0.4)
        # Inbound ←
        cv2.arrowedLine(frame, (x + 22, in_y), (x, in_y), (180, 185, 200), 1, tipLength=0.4)

    # Highway queue bar
    queue_len = hw.get("queue", 0)
    evac_total = hw.get("evacuated", 0)
    q_bar_w = min(queue_len * 3, W - 20)
    if q_bar_w > 0:
        cv2.rectangle(frame, (10, HW_Y2 - 8), (10 + q_bar_w, HW_Y2 - 2), out_color, -1)

    # Inbound blocked banner
    if hw.get("inbound_blocked"):
        cv2.rectangle(frame, (0, in_y - 6), (W, in_y + 6), T_BLOCKED, -1)
        cv2.putText(frame, "INBOUND CLOSED", (W // 2 - 65, in_y + 4), FONT_SMALL, 0.38, TEXT_WHITE, 1)

    # Highway label
    _road_label(frame, "I-9 EXPRESSWAY", W // 2, HW_CY)

    # Queue / evacuated info
    cap = hw.get("outbound_capacity", 0)
    cong = hw.get("congestion", "clear").upper()
    cv2.putText(frame, f"Outbound: {cong}  Q:{queue_len}  Cap:{cap}/s  Evac:{evac_total}",
                (8, H - 8), FONT_SMALL, 0.38, TEXT_GRAY, 1)


def _draw_city_block(frame, buildings: list, stats: dict):
    """Draw the evacuation zone (city block)."""
    # Block fill
    cv2.rectangle(frame, (BLK_X1, BLK_Y1), (BLK_X2, BLK_Y2), BLOCK_FILL, -1)
    cv2.rectangle(frame, (BLK_X1, BLK_Y1), (BLK_X2, BLK_Y2), BLOCK_BDR, 2)

    # Evacuation zone label
    pct = stats.get("percent_complete", 0)
    label_color = T_CLEAR if pct > 80 else (T_MODERATE if pct > 40 else T_HEAVY)
    cv2.putText(frame, "EVACUATION ZONE", (BLK_X1 + 12, BLK_Y1 + 20), FONT_SMALL, 0.42, label_color, 1)
    cv2.putText(frame, f"{pct:.0f}% cleared", (BLK_X1 + 12, BLK_Y1 + 36), FONT_SMALL, 0.38, TEXT_GRAY, 1)

    # Mini building markers inside block
    if buildings:
        for b in buildings:
            # Normalize sim coords to block coords
            pass   # Buildings are just shown via the main canvas; maps shows zone only


def _draw_exits(frame, exits: list, state: dict):
    """Draw exit pins on the block boundary."""
    # We need sim block bounds to map exit coords
    from simulation.city_block import BLOCK_X1 as SX1, BLOCK_X2 as SX2, BLOCK_Y1 as SY1, BLOCK_Y2 as SY2, BLOCK_W as SW, BLOCK_H as SH

    sim_bounds = {"x1": SX1, "y1": SY1, "w": SW, "h": SH}

    for e in exits:
        mx, my = _exit_map_pos(e, sim_bounds)
        status = e.get("status", "open")
        congested = e.get("congested", False)
        q = e.get("queue", 0)

        if status == "closed":
            color = PIN_CLOSED
        elif congested:
            color = PIN_CONGESTED
        else:
            color = PIN_OPEN

        _draw_pin(frame, mx, my, e["id"], color)

        # Queue bubble
        if q > 0 and status == "open":
            cv2.circle(frame, (mx + 12, my - 20), 9, color, -1)
            cv2.putText(frame, str(q), (mx + 9 if q < 10 else mx + 6, my - 16), FONT_SMALL, 0.35, TEXT_WHITE, 1)


def _draw_hud(frame, stats: dict, hw: dict):
    """Draw the HUD overlay (top-left info box + compass + EvacuAI badge)."""
    # ── Top-right: EvacuAI badge ──
    badge_x, badge_y = W - 115, 10
    cv2.rectangle(frame, (badge_x, badge_y), (W - 8, badge_y + 32), (22, 24, 35), -1)
    cv2.rectangle(frame, (badge_x, badge_y), (W - 8, badge_y + 32), BLOCK_BDR, 1)
    cv2.putText(frame, "Evacu", (badge_x + 5, badge_y + 14), FONT_SMALL, 0.45, TEXT_WHITE, 1)
    cv2.putText(frame, "AI",    (badge_x + 53, badge_y + 14), FONT_SMALL, 0.45, ACCENT, 1)
    cv2.putText(frame, "Traffic View", (badge_x + 5, badge_y + 27), FONT_SMALL, 0.33, TEXT_GRAY, 1)

    # ── Compass (bottom-right) ──
    cx, cy = W - 28, H - HW_Y2 // 2 - 28
    cv2.circle(frame, (cx, cy), 16, (38, 40, 50), -1)
    cv2.circle(frame, (cx, cy), 16, ROAD_BDR, 1)
    cv2.putText(frame, "N", (cx - 4, cy - 6), FONT_SMALL, 0.4, TEXT_WHITE, 1)
    cv2.arrowedLine(frame, (cx, cy + 2), (cx, cy - 12), TEXT_WHITE, 1, tipLength=0.5)

    # ── Traffic legend (top-left) ──
    lx, ly = 8, 10
    cv2.rectangle(frame, (lx, ly), (lx + 108, ly + 68), (22, 24, 35), -1)
    cv2.rectangle(frame, (lx, ly), (lx + 108, ly + 68), BLOCK_BDR, 1)
    cv2.putText(frame, "Traffic", (lx + 4, ly + 14), FONT_SMALL, 0.4, TEXT_WHITE, 1)
    for i, (label, color) in enumerate([("Clear", T_CLEAR), ("Moderate", T_MODERATE), ("Heavy", T_HEAVY)]):
        y = ly + 28 + i * 14
        cv2.rectangle(frame, (lx + 4, y - 5), (lx + 20, y + 3), color, -1)
        cv2.putText(frame, label, (lx + 24, y + 2), FONT_SMALL, 0.35, TEXT_GRAY, 1)
