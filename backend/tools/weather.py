"""NWS Weather API integration for weather alerts."""

import logging

import httpx

logger = logging.getLogger(__name__)

NWS_USER_AGENT = "EvacuAI/1.0 (evacuation-assistant)"


async def get_weather_alerts(latitude: float, longitude: float) -> dict:
    """Fetch active weather alerts for a location from the NWS API.

    The NWS API is free and requires no API key.
    Only works for US locations.
    """
    url = f"https://api.weather.gov/alerts/active?point={latitude},{longitude}"
    headers = {
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return _parse_alerts(resp.json())
    except httpx.HTTPError as e:
        logger.error(f"NWS API error: {e}")
        return {
            "alerts": [],
            "alert_count": 0,
            "error": f"Weather API unavailable: {e}",
        }


def _parse_alerts(data: dict) -> dict:
    """Extract relevant alert information from NWS response."""
    features = data.get("features", [])
    alerts = []

    for feature in features:
        props = feature.get("properties", {})
        alerts.append({
            "event": props.get("event", "Unknown"),
            "severity": props.get("severity", "Unknown"),
            "urgency": props.get("urgency", "Unknown"),
            "headline": props.get("headline", ""),
            "description": props.get("description", ""),
            "instruction": props.get("instruction", ""),
            "areas": props.get("areaDesc", ""),
            "onset": props.get("onset"),
            "expires": props.get("expires"),
        })

    return {
        "alerts": alerts,
        "alert_count": len(alerts),
    }
