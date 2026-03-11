"""OpenCV-based visual overlays for simulating hazards on video frames."""

import cv2
import numpy as np


def apply_smoke_overlay(
    frame: np.ndarray,
    intensity: float = 0.4,
    region: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Add translucent gray/white haze to simulate smoke.

    Args:
        frame: Input BGR frame.
        intensity: Opacity of smoke (0.0 to 1.0).
        region: Optional (x1, y1, x2, y2) to limit smoke area. None = full frame.
    """
    h, w = frame.shape[:2]
    noise = np.random.normal(200, 40, frame.shape).clip(0, 255).astype(np.uint8)
    smoke = cv2.GaussianBlur(noise, (99, 99), 30)

    if region:
        x1, y1, x2, y2 = region
        mask = np.zeros_like(frame, dtype=np.float32)
        mask[y1:y2, x1:x2] = intensity
        # Feather the edges
        mask = cv2.GaussianBlur(mask, (51, 51), 20)
        result = frame.astype(np.float32) * (1 - mask) + smoke.astype(np.float32) * mask
        return result.clip(0, 255).astype(np.uint8)

    return cv2.addWeighted(frame, 1 - intensity, smoke, intensity, 0)


def apply_fire_glow(
    frame: np.ndarray,
    position: tuple[int, int] = (300, 200),
    size: tuple[int, int] = (100, 150),
    intensity: float = 0.5,
) -> np.ndarray:
    """Add orange/red glow effect at a specified position.

    Args:
        frame: Input BGR frame.
        position: (x, y) center of fire glow.
        size: (width, height) of glow area.
        intensity: Brightness of the glow (0.0 to 1.0).
    """
    overlay = frame.copy()
    cx, cy = position
    w, h = size

    x1 = max(0, cx - w // 2)
    y1 = max(0, cy - h // 2)
    x2 = min(frame.shape[1], cx + w // 2)
    y2 = min(frame.shape[0], cy + h // 2)

    # Create flickering fire color (orange-red)
    fire_color = (
        int(np.random.uniform(0, 50)),     # B
        int(np.random.uniform(60, 120)),    # G
        int(np.random.uniform(200, 255)),   # R
    )

    cv2.rectangle(overlay, (x1, y1), (x2, y2), fire_color, -1)

    # Add a gradient glow around the fire
    glow_overlay = np.zeros_like(frame, dtype=np.float32)
    cv2.circle(glow_overlay, (cx, cy), max(w, h),
               (0.1, 0.3, 0.8), -1)
    glow_overlay = cv2.GaussianBlur(glow_overlay, (99, 99), 40)

    result = cv2.addWeighted(frame, 1 - intensity, overlay, intensity, 0)
    result = (result.astype(np.float32) + glow_overlay * 100).clip(0, 255).astype(np.uint8)
    return result


def apply_crowd_markers(
    frame: np.ndarray,
    count: int = 30,
    region: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Draw colored dots to indicate crowd density.

    Args:
        frame: Input BGR frame.
        count: Number of person markers to draw.
        region: Optional (x1, y1, x2, y2) to limit crowd area.
    """
    result = frame.copy()
    h, w = frame.shape[:2]

    if region:
        x1, y1, x2, y2 = region
    else:
        x1, y1, x2, y2 = 0, h // 3, w, h

    for _ in range(count):
        x = np.random.randint(x1, x2)
        y = np.random.randint(y1, y2)
        # Draw a small colored circle for each person
        color = (0, 0, 255) if count > 40 else (0, 165, 255)  # Red if dense, orange otherwise
        cv2.circle(result, (x, y), 4, color, -1)
        cv2.circle(result, (x, y), 4, (255, 255, 255), 1)

    return result


def apply_blocked_exit_marker(
    frame: np.ndarray,
    position: tuple[int, int] = (320, 240),
    label: str = "EXIT BLOCKED",
) -> np.ndarray:
    """Draw a red X and label at an exit location.

    Args:
        frame: Input BGR frame.
        position: (x, y) center of the blocked exit.
        label: Text label to display.
    """
    result = frame.copy()
    cx, cy = position
    size = 40

    # Draw red X
    cv2.line(result, (cx - size, cy - size), (cx + size, cy + size), (0, 0, 255), 4)
    cv2.line(result, (cx + size, cy - size), (cx - size, cy + size), (0, 0, 255), 4)

    # Draw label with background
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.7
    thickness = 2
    (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)

    tx = cx - tw // 2
    ty = cy + size + th + 10

    cv2.rectangle(result, (tx - 5, ty - th - 5), (tx + tw + 5, ty + 5), (0, 0, 180), -1)
    cv2.putText(result, label, (tx, ty), font, scale, (255, 255, 255), thickness)

    return result


def apply_status_bar(
    frame: np.ndarray,
    text: str,
    position: str = "bottom",
) -> np.ndarray:
    """Draw a semi-transparent status bar with text.

    Args:
        frame: Input BGR frame.
        text: Status text to display.
        position: "top" or "bottom".
    """
    result = frame.copy()
    h, w = frame.shape[:2]
    bar_height = 40

    if position == "top":
        y1, y2 = 0, bar_height
    else:
        y1, y2 = h - bar_height, h

    # Semi-transparent dark bar
    overlay = result.copy()
    cv2.rectangle(overlay, (0, y1), (w, y2), (0, 0, 0), -1)
    result = cv2.addWeighted(result, 0.6, overlay, 0.4, 0)

    # Text
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(result, text, (10, y2 - 12), font, 0.6, (255, 255, 255), 1)

    return result
