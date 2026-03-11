"""Vision analysis prompt module for Gemini's native video frame analysis."""

VISION_ANALYSIS_PROMPT = """When you receive video frames, analyze them carefully for the following hazards:
- SMOKE: Look for haze, reduced visibility, gray/white clouds. Estimate opacity (light/moderate/heavy).
- FIRE: Look for visible flames, orange/red glow, intense light sources. Note location within the frame.
- BLOCKED EXITS: Look for debris, fallen objects, locked doors, or any obstruction blocking a path.
- CROWD DENSITY: Estimate the number of people visible. Note if there is crowding, stampede risk, or orderly movement.
- WATER/FLOODING: Look for standing water, flowing water, or wet surfaces that indicate flooding.
- STRUCTURAL DAMAGE: Look for cracked walls, collapsed ceilings, broken glass, or tilted structures.

When you detect any hazard:
1. Immediately warn the user with the hazard type and location.
2. Assess whether current evacuation routes are affected.
3. If a route is compromised, suggest an alternative before the user asks.
4. Update your internal understanding of which areas are safe vs. hazardous.

If you are unsure about what you see, say so honestly. Never fabricate hazard detections."""


def format_vision_context(observations: list[dict]) -> str:
    """Format vision observations into natural language for reports."""
    if not observations:
        return "No visual hazards currently detected."

    lines = []
    for obs in observations:
        hazard_type = obs.get("type", "unknown")
        severity = obs.get("severity", "unknown")
        location = obs.get("location", "unspecified area")
        lines.append(f"- {hazard_type.upper()} ({severity} severity) detected in {location}")

    return "Visual hazard observations:\n" + "\n".join(lines)
