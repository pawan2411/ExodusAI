"""Route planning logic: combines traffic, weather, and building data."""

ROUTE_PLANNING_PROMPT = """When planning evacuation routes, follow this process:
1. Check the building layout to identify all available exits and stairwells.
2. Eliminate any routes that pass through areas with detected hazards (from video analysis).
3. For outdoor routes, check traffic conditions to avoid congested roads.
4. Check weather alerts — avoid low-lying routes during flood warnings, avoid open areas during tornado warnings.
5. Prioritize routes by: (a) safety (away from hazards), (b) speed (least congested), (c) accessibility.
6. Always provide a primary route AND an alternate route when possible.
7. Give directions as numbered steps with cardinal directions and landmarks."""


def plan_evacuation_route(
    traffic_data: dict | None = None,
    weather_data: dict | None = None,
    building_data: dict | None = None,
    hazards: list[dict] | None = None,
) -> dict:
    """Combine data sources to produce a structured evacuation plan."""
    plan = {
        "primary_route": None,
        "alternate_route": None,
        "warnings": [],
        "blocked_areas": [],
    }

    # Identify blocked areas from hazards
    if hazards:
        for hazard in hazards:
            plan["blocked_areas"].append({
                "location": hazard.get("location", "unknown"),
                "reason": hazard.get("type", "hazard detected"),
            })

    # Check weather warnings
    if weather_data and weather_data.get("alerts"):
        for alert in weather_data["alerts"]:
            plan["warnings"].append(
                f"Weather: {alert.get('event', 'Unknown')} - {alert.get('headline', '')}"
            )

    # Check traffic conditions
    if traffic_data:
        condition = traffic_data.get("traffic_condition", "unknown")
        if condition in ("heavy", "stopped"):
            plan["warnings"].append(
                f"Traffic: {condition} congestion on recommended route. "
                f"Estimated delay: {traffic_data.get('delay_minutes', '?')} minutes."
            )

    # Build primary route from building data
    if building_data:
        exits = []
        for floor_data in building_data.get("floors", {}).values():
            for exit_info in floor_data.get("exits", []):
                blocked = any(
                    b["location"] == exit_info.get("id")
                    for b in plan["blocked_areas"]
                )
                if not blocked:
                    exits.append(exit_info)

        if exits:
            primary_exit = exits[0]
            plan["primary_route"] = {
                "exit": primary_exit["id"],
                "exit_type": primary_exit.get("type", "emergency"),
                "direction": primary_exit.get("location", ""),
            }
            if len(exits) > 1:
                alt_exit = exits[1]
                plan["alternate_route"] = {
                    "exit": alt_exit["id"],
                    "exit_type": alt_exit.get("type", "emergency"),
                    "direction": alt_exit.get("location", ""),
                }

    return plan


def format_route_for_speech(route_plan: dict) -> str:
    """Convert route plan to spoken directions."""
    parts = []

    if route_plan.get("warnings"):
        parts.append("Important warnings: " + ". ".join(route_plan["warnings"]))

    primary = route_plan.get("primary_route")
    if primary:
        parts.append(
            f"I recommend heading to {primary['exit']}, "
            f"located to the {primary['direction']}. "
            f"This is a {primary['exit_type']} exit."
        )

    alternate = route_plan.get("alternate_route")
    if alternate:
        parts.append(
            f"As a backup, you can use {alternate['exit']}, "
            f"located to the {alternate['direction']}."
        )

    if route_plan.get("blocked_areas"):
        blocked = ", ".join(b["location"] for b in route_plan["blocked_areas"])
        parts.append(f"Avoid these areas: {blocked}.")

    return " ".join(parts) if parts else "I'm assessing the situation. Please stand by."


def format_route_for_map(route_plan: dict) -> dict:
    """Convert route plan to Google Maps marker/polyline data for the frontend."""
    markers = []
    if route_plan.get("primary_route"):
        markers.append({
            "id": route_plan["primary_route"]["exit"],
            "type": "primary_exit",
            "label": f"Primary: {route_plan['primary_route']['exit']}",
        })
    if route_plan.get("alternate_route"):
        markers.append({
            "id": route_plan["alternate_route"]["exit"],
            "type": "alternate_exit",
            "label": f"Alternate: {route_plan['alternate_route']['exit']}",
        })
    for blocked in route_plan.get("blocked_areas", []):
        markers.append({
            "id": blocked["location"],
            "type": "hazard",
            "label": f"BLOCKED: {blocked['reason']}",
        })

    return {"markers": markers, "routes": []}
