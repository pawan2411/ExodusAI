"""Scripted mock traffic data for demo/simulation mode."""

import math

# Pre-defined route data for the demo scenario area (Riverside, CA area)
MOCK_ROUTES = {
    "main_street_north": {
        "summary": "Via Main St heading north",
        "duration": "15 mins",
        "duration_seconds": 900,
        "distance_meters": 4800,
        "distance_miles": 3.0,
        "traffic_condition": "heavy",
        "delay_minutes": 12,
        "steps": [
            {"instruction": "Head north on Main St", "distance_meters": 800},
            {"instruction": "Turn right onto Highway 91 on-ramp", "distance_meters": 400},
            {"instruction": "Merge onto Highway 91 East", "distance_meters": 2400},
            {"instruction": "Take exit toward Safe Zone A", "distance_meters": 1200},
        ],
        "polyline": "",
    },
    "oak_avenue_south": {
        "summary": "Via Oak Ave heading south",
        "duration": "6 mins",
        "duration_seconds": 360,
        "distance_meters": 2400,
        "distance_miles": 1.5,
        "traffic_condition": "light",
        "delay_minutes": 0,
        "steps": [
            {"instruction": "Head south on Oak Ave", "distance_meters": 800},
            {"instruction": "Continue past Cedar Park on your right", "distance_meters": 600},
            {"instruction": "Turn left onto Riverside Dr", "distance_meters": 600},
            {"instruction": "Arrive at Emergency Assembly Point", "distance_meters": 400},
        ],
        "polyline": "",
    },
    "elm_street_east": {
        "summary": "Via Elm St heading east to Parking Lot B",
        "duration": "3 mins",
        "duration_seconds": 180,
        "distance_meters": 800,
        "distance_miles": 0.5,
        "traffic_condition": "normal",
        "delay_minutes": 0,
        "steps": [
            {"instruction": "Exit building via East door", "distance_meters": 100},
            {"instruction": "Cross Elm St to Parking Lot B", "distance_meters": 200},
            {"instruction": "Proceed to the northeast corner of the lot", "distance_meters": 500},
        ],
        "polyline": "",
    },
}

MOCK_TRAFFIC_INCIDENTS = [
    {
        "type": "road_closure",
        "location": "Main St between 1st and 3rd Ave",
        "reason": "Emergency vehicle staging area",
        "severity": "high",
    },
    {
        "type": "congestion",
        "location": "Highway 91 westbound",
        "reason": "Evacuation traffic",
        "severity": "medium",
    },
]


def get_mock_traffic(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict:
    """Return mock traffic data based on approximate direction of travel.

    Selects the most relevant mock route based on the bearing
    from origin to destination.
    """
    bearing = _calculate_bearing(origin_lat, origin_lng, dest_lat, dest_lng)

    # Select route based on general direction
    if 315 <= bearing or bearing < 45:
        route = MOCK_ROUTES["main_street_north"]
    elif 135 <= bearing < 225:
        route = MOCK_ROUTES["oak_avenue_south"]
    else:
        route = MOCK_ROUTES["elm_street_east"]

    return {
        **route,
        "incidents_nearby": MOCK_TRAFFIC_INCIDENTS,
    }


def _calculate_bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the bearing from point 1 to point 2 in degrees (0-360)."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    d_lng = math.radians(lng2 - lng1)

    x = math.sin(d_lng) * math.cos(lat2_r)
    y = (math.cos(lat1_r) * math.sin(lat2_r) -
         math.sin(lat1_r) * math.cos(lat2_r) * math.cos(d_lng))

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360
