"""Google Routes API integration for real-time traffic data."""

import os
import logging

import httpx

logger = logging.getLogger(__name__)


async def get_traffic_status(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict:
    """Get real-time traffic conditions between two points.

    Uses Google Routes API in live mode, falls back to mock data
    when TRAFFIC_MODE=mock.
    """
    traffic_mode = os.getenv("TRAFFIC_MODE", "mock")

    if traffic_mode == "mock":
        from simulation.mock_traffic import get_mock_traffic
        return get_mock_traffic(origin_lat, origin_lng, dest_lat, dest_lng)

    return await _fetch_live_traffic(origin_lat, origin_lng, dest_lat, dest_lng)


async def _fetch_live_traffic(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict:
    """Call the Google Routes API for real traffic data."""
    api_key = os.getenv("ROUTES_API_KEY")
    if not api_key:
        logger.warning("ROUTES_API_KEY not set, returning empty traffic data")
        return {"error": "Routes API key not configured", "traffic_condition": "unknown"}

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "routes.duration,routes.distanceMeters,"
            "routes.travelAdvisory,routes.legs.steps,"
            "routes.polyline.encodedPolyline"
        ),
        "Content-Type": "application/json",
    }
    body = {
        "origin": {
            "location": {
                "latLng": {"latitude": origin_lat, "longitude": origin_lng}
            }
        },
        "destination": {
            "location": {
                "latLng": {"latitude": dest_lat, "longitude": dest_lng}
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "extraComputations": ["TRAFFIC_ON_POLYLINE"],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return _parse_routes_response(resp.json())
    except httpx.HTTPError as e:
        logger.error(f"Routes API error: {e}")
        return {"error": str(e), "traffic_condition": "unknown"}


def _parse_routes_response(data: dict) -> dict:
    """Extract relevant fields from the Routes API response."""
    routes = data.get("routes", [])
    if not routes:
        return {"error": "No routes found", "traffic_condition": "unknown"}

    route = routes[0]
    duration = route.get("duration", "0s")
    distance_m = route.get("distanceMeters", 0)

    # Parse travel advisory for congestion info
    advisory = route.get("travelAdvisory", {})
    speed_reading = advisory.get("speedReadingIntervals", [])

    congestion_level = "normal"
    if speed_reading:
        slow_segments = sum(
            1 for s in speed_reading if s.get("speed") in ("SLOW", "TRAFFIC_JAM")
        )
        total_segments = len(speed_reading)
        if total_segments > 0:
            ratio = slow_segments / total_segments
            if ratio > 0.5:
                congestion_level = "heavy"
            elif ratio > 0.2:
                congestion_level = "moderate"

    # Extract steps
    steps = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            instruction = step.get("navigationInstruction", {})
            steps.append({
                "instruction": instruction.get("instructions", ""),
                "distance_meters": step.get("distanceMeters", 0),
            })

    return {
        "duration": duration,
        "distance_meters": distance_m,
        "distance_miles": round(distance_m * 0.000621371, 1),
        "traffic_condition": congestion_level,
        "polyline": route.get("polyline", {}).get("encodedPolyline", ""),
        "steps": steps,
    }
