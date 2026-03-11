"""Situation report generator for emergency responders."""

from datetime import datetime, timezone

REPORT_PROMPT = """When you detect a widespread emergency pattern, or when a user or responder requests it, generate a situation report using the generate_situation_report tool. Include:
- The type of incident (fire, flood, earthquake, etc.)
- The specific location
- Severity assessment (low, medium, high, critical)
- All observations from video analysis and user reports
This creates a structured report that can be shared with emergency services."""


def generate_report(
    incident_type: str,
    location: str,
    severity: str,
    observations: list[str],
) -> dict:
    """Generate a structured situation report."""
    severity_actions = {
        "low": [
            "Monitor the situation",
            "Prepare for possible evacuation",
        ],
        "medium": [
            "Begin orderly evacuation of affected areas",
            "Alert emergency services",
            "Activate building alarm system",
        ],
        "high": [
            "Immediate evacuation of all floors",
            "Emergency services en route",
            "Seal off hazardous areas",
            "Account for all personnel",
        ],
        "critical": [
            "Full building evacuation NOW",
            "Multiple emergency units required",
            "Establish incident command post",
            "Begin search and rescue protocols",
            "Set up triage area at assembly point",
        ],
    }

    resource_estimates = {
        "structure_fire": ["Fire engines (2-4)", "Ambulances (1-2)", "Fire investigation unit"],
        "flood": ["Swift water rescue team", "Pumping equipment", "Evacuation buses"],
        "earthquake": ["Search and rescue teams", "Structural engineers", "Ambulances (multiple)"],
        "active_threat": ["Law enforcement tactical units", "Ambulances (multiple)", "Crisis negotiators"],
        "chemical_spill": ["HazMat team", "Decontamination unit", "Ambulances (multiple)"],
    }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incident_type": incident_type,
        "location": location,
        "severity": severity,
        "observations": observations,
        "recommended_actions": severity_actions.get(severity, severity_actions["medium"]),
        "resources_needed": resource_estimates.get(incident_type, ["Emergency services"]),
        "status": "active",
    }


def format_report_for_display(report: dict) -> dict:
    """Format report for frontend HTML rendering."""
    return {
        "title": f"Situation Report - {report['incident_type'].replace('_', ' ').title()}",
        "timestamp": report["timestamp"],
        "severity": report["severity"],
        "severity_color": {
            "low": "#4CAF50",
            "medium": "#FF9800",
            "high": "#f44336",
            "critical": "#9C27B0",
        }.get(report["severity"], "#FF9800"),
        "sections": [
            {
                "heading": "Location",
                "content": report["location"],
            },
            {
                "heading": "Observations",
                "content": report["observations"],
                "type": "list",
            },
            {
                "heading": "Recommended Actions",
                "content": report["recommended_actions"],
                "type": "list",
            },
            {
                "heading": "Resources Needed",
                "content": report["resources_needed"],
                "type": "list",
            },
        ],
    }
