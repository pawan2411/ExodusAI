"""Building floor plan data provider."""

import copy
import logging

logger = logging.getLogger(__name__)

# Sample building layout as a JSON graph structure.
# In production, this would be loaded from a database or configuration file.
BUILDING_DATA = {
    "building_001": {
        "name": "Riverside Office Complex",
        "address": "123 Main St, Riverside",
        "coordinates": {"lat": 33.9806, "lng": -117.3755},
        "floors": {
            "1": {
                "name": "Ground Floor",
                "rooms": ["lobby", "cafeteria", "mailroom", "security_office"],
                "exits": [
                    {
                        "id": "exit_a_north",
                        "type": "main_entrance",
                        "location": "north",
                        "accessible": True,
                        "leads_to": "Main Street",
                    },
                    {
                        "id": "exit_b_south",
                        "type": "emergency",
                        "location": "south",
                        "accessible": True,
                        "leads_to": "Oak Avenue",
                    },
                    {
                        "id": "exit_c_east",
                        "type": "emergency",
                        "location": "east",
                        "accessible": True,
                        "leads_to": "Parking Lot B",
                    },
                ],
                "stairwells": [
                    {"id": "stair_a", "location": "northwest"},
                    {"id": "stair_b", "location": "southeast"},
                ],
                "elevators": [
                    {"id": "elev_1", "location": "center", "note": "DO NOT USE during fire"},
                    {"id": "elev_2", "location": "center", "note": "DO NOT USE during fire"},
                ],
                "corridors": ["main_corridor", "north_corridor", "south_corridor"],
            },
            "2": {
                "name": "Second Floor",
                "rooms": ["office_201", "office_202", "conference_room_a", "break_room"],
                "exits": [],
                "stairwells": [
                    {"id": "stair_a", "location": "northwest"},
                    {"id": "stair_b", "location": "southeast"},
                ],
                "elevators": [
                    {"id": "elev_1", "location": "center"},
                    {"id": "elev_2", "location": "center"},
                ],
                "corridors": ["east_wing_corridor", "west_wing_corridor"],
            },
            "3": {
                "name": "Third Floor",
                "rooms": ["office_301", "office_302", "server_room", "executive_suite"],
                "exits": [],
                "stairwells": [
                    {"id": "stair_a", "location": "northwest"},
                    {"id": "stair_b", "location": "southeast"},
                ],
                "elevators": [
                    {"id": "elev_1", "location": "center"},
                    {"id": "elev_2", "location": "center"},
                ],
                "corridors": ["main_corridor_3f", "north_corridor_3f"],
            },
        },
        "connections": {
            "stair_a": {
                "connects_floors": ["1", "2", "3"],
                "location": "northwest corner",
                "width": "standard",
            },
            "stair_b": {
                "connects_floors": ["1", "2", "3"],
                "location": "southeast corner",
                "width": "wide",
            },
        },
        "assembly_points": [
            {
                "id": "assembly_a",
                "name": "Cedar Park",
                "location": "200m south on Oak Avenue",
                "coordinates": {"lat": 33.9790, "lng": -117.3755},
            },
            {
                "id": "assembly_b",
                "name": "Parking Lot B",
                "location": "East side of building",
                "coordinates": {"lat": 33.9806, "lng": -117.3740},
            },
        ],
        "hazards": {},  # Updated in real-time by vision analysis
    }
}


def get_building_layout(building_id: str, floor: str | None = None) -> dict:
    """Get the layout for a specific building and optionally a specific floor."""
    building = BUILDING_DATA.get(building_id)
    if not building:
        available = list(BUILDING_DATA.keys())
        return {
            "error": f"Building '{building_id}' not found",
            "available_buildings": available,
        }

    result = copy.deepcopy(building)

    if floor:
        floor_data = result["floors"].get(floor)
        if not floor_data:
            return {
                "error": f"Floor '{floor}' not found in {building_id}",
                "available_floors": list(result["floors"].keys()),
            }
        result["floors"] = {floor: floor_data}

    # Inject current hazard status into floor data
    for floor_id, floor_data in result["floors"].items():
        floor_hazards = result["hazards"].get(floor_id, {})
        floor_data["active_hazards"] = floor_hazards

    return result


def update_hazard(building_id: str, floor: str, location: str, hazard: dict) -> bool:
    """Mark an area as hazardous based on vision analysis."""
    building = BUILDING_DATA.get(building_id)
    if not building:
        return False

    if floor not in building["floors"]:
        return False

    if floor not in building["hazards"]:
        building["hazards"][floor] = {}

    building["hazards"][floor][location] = {
        "status": hazard.get("status", "blocked"),
        "reason": hazard.get("reason", "hazard detected"),
        "severity": hazard.get("severity", "medium"),
    }

    logger.info(
        f"Hazard updated: {building_id} floor {floor} "
        f"location {location}: {hazard}"
    )
    return True


def clear_hazard(building_id: str, floor: str, location: str) -> bool:
    """Remove a hazard marking from a location."""
    building = BUILDING_DATA.get(building_id)
    if not building:
        return False

    floor_hazards = building["hazards"].get(floor, {})
    if location in floor_hazards:
        del floor_hazards[location]
        return True
    return False
