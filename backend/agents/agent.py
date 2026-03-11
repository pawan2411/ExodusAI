"""Root agent definition: system prompt, tool declarations, and tool dispatcher."""

import os

from agents.vision_agent import VISION_ANALYSIS_PROMPT
from agents.route_agent import ROUTE_PLANNING_PROMPT
from agents.report_agent import REPORT_PROMPT


def get_system_prompt() -> str:
    """Return the full EvacuAI system instruction."""
    return f"""You are EvacuAI, an AI-powered emergency evacuation assistant. You are the calm voice in chaos.

PERSONA:
- Speak with a calm, clear, and authoritative tone at all times.
- Never sound panicked, even when describing urgent hazards.
- Be concise but thorough. Keep voice responses under 30 seconds.
- Use a reassuring yet decisive communication style.

CORE BEHAVIOR:
1. Always provide step-by-step numbered directions.
2. Use cardinal directions (north, south, east, west) and landmarks when giving directions.
3. Never guess or assume — always verify information using your tools before making recommendations.
4. When conditions change (new hazard detected, route blocked), proactively interrupt with updated guidance.
5. If the user interrupts you (barge-in), stop immediately and listen. Their new information may be critical.

VISION INTEGRATION:
{VISION_ANALYSIS_PROMPT}

ROUTE PLANNING:
{ROUTE_PLANNING_PROMPT}

TOOL USAGE:
- Use get_traffic_status to check road conditions BEFORE recommending any outdoor evacuation route.
- Use get_weather_alerts to check for floods, storms, or extreme weather that may affect routes.
- Use get_building_layout to understand indoor navigation paths, exits, stairwells, and current hazards.
- Use generate_situation_report when you detect a widespread emergency pattern or when the user or responders request a status update.

REPORT GENERATION:
{REPORT_PROMPT}

SAFETY RULES:
- Never recommend elevators during a fire emergency.
- Always prioritize routes away from detected hazards.
- If all known exits are compromised, instruct the user to shelter in place and call emergency services.
- For mobility-impaired individuals, only suggest accessible routes (ground-level exits, ramps, elevators ONLY if not a fire).

EXAMPLE INTERACTION:
User: "Where should I go?"
You: "Based on what I can see, I recommend the following route:
1. Head south down the main corridor.
2. Take the stairwell on your left — that's Stairwell B.
3. Exit through the south door onto Oak Avenue.
4. Turn right and proceed 200 meters to the assembly point at Cedar Park.
Traffic on Oak Avenue is currently clear. Let me know if you encounter any obstacles."
"""


TOOL_DECLARATIONS = [
    {
        "name": "get_traffic_status",
        "description": "Get real-time traffic conditions between two points. Use this before recommending any outdoor evacuation route to ensure the route is clear.",
        "parameters": {
            "type": "object",
            "properties": {
                "origin_lat": {
                    "type": "number",
                    "description": "Latitude of the starting point"
                },
                "origin_lng": {
                    "type": "number",
                    "description": "Longitude of the starting point"
                },
                "dest_lat": {
                    "type": "number",
                    "description": "Latitude of the destination"
                },
                "dest_lng": {
                    "type": "number",
                    "description": "Longitude of the destination"
                }
            },
            "required": ["origin_lat", "origin_lng", "dest_lat", "dest_lng"]
        }
    },
    {
        "name": "get_weather_alerts",
        "description": "Fetch active weather alerts for a location. Use this to check for floods, storms, or extreme weather that may affect evacuation routes.",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Latitude of the location"
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude of the location"
                }
            },
            "required": ["latitude", "longitude"]
        }
    },
    {
        "name": "get_building_layout",
        "description": "Get the floor plan and layout of a building, including rooms, exits, stairwells, and current hazard status. Use this for indoor navigation.",
        "parameters": {
            "type": "object",
            "properties": {
                "building_id": {
                    "type": "string",
                    "description": "The building identifier"
                },
                "floor": {
                    "type": "string",
                    "description": "Specific floor to query (optional, returns all floors if omitted)"
                }
            },
            "required": ["building_id"]
        }
    },
    {
        "name": "generate_situation_report",
        "description": "Generate a structured situation report for emergency responders. Use this when you detect a widespread emergency or when explicitly requested.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_type": {
                    "type": "string",
                    "description": "Type of incident (e.g., structure_fire, flood, earthquake, active_threat)"
                },
                "location": {
                    "type": "string",
                    "description": "Location description of the incident"
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Severity level of the incident"
                },
                "observations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of observations from video analysis and user reports"
                }
            },
            "required": ["incident_type", "location", "severity", "observations"]
        }
    }
]


def get_tool_declarations() -> list:
    """Return tool declarations for the Gemini Live API config."""
    return TOOL_DECLARATIONS


async def execute_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call to the appropriate handler."""
    from tools import traffic, weather, building
    from agents import report_agent

    if name == "get_traffic_status":
        return await traffic.get_traffic_status(**args)
    elif name == "get_weather_alerts":
        return await weather.get_weather_alerts(**args)
    elif name == "get_building_layout":
        return building.get_building_layout(**args)
    elif name == "generate_situation_report":
        return report_agent.generate_report(**args)
    else:
        return {"error": f"Unknown tool: {name}"}
