"""
311 issue type taxonomy for Civic.

Defines a jurisdiction-agnostic taxonomy of issue types for classifying
311/SeeClickFix community reports. The taxonomy constants are domain knowledge
that lives in core; the LLM-based classification service lives in
civicos_services.issues.classifier.

Usage:
    from civicos.issues.classify import ISSUE_TYPE_TAXONOMY, VALID_ISSUE_TYPES
"""

from typing import Dict

# Jurisdiction-agnostic taxonomy of 311 issue types.
# Keys are stored in the database; values are human-readable descriptions
# sent to the LLM for classification context.
ISSUE_TYPE_TAXONOMY: Dict[str, str] = {
    "pothole": "Potholes, road surface damage, pavement deterioration",
    "traffic_signal": "Traffic signals, stop signs, road signs, lane markings, crosswalk signals",
    "sidewalk": "Sidewalk cracks, damage, trip hazards, ADA accessibility",
    "streetlight": "Streetlight outages, broken lights, lighting issues",
    "stormwater": "Storm drains, flooding, drainage problems, clogged gutters",
    "graffiti": "Graffiti on public or private property, tagging, vandalism",
    "illegal_dumping": "Illegal dumping, litter, abandoned trash, debris",
    "parking": "Parking violations, broken meters, abandoned vehicles, towing",
    "parks": "Parks, playgrounds, recreation facilities, sports fields, benches",
    "trees_vegetation": "Trees, landscaping, overgrown vegetation, medians, roadside plants",
    "street_cleaning": "Street sweeping, road debris, general cleanliness",
    "water_sewer": "Water main breaks, sewer issues, utility infrastructure, manhole covers",
    "noise": "Noise complaints, construction noise, loud music",
    "fire_hazard": "Vegetation fire hazards, fire prevention, campsite hazards",
    "animal_control": "Stray animals, wildlife, animal-related complaints",
    "property_maintenance": "Blight, code violations, unmaintained property, building issues",
    "public_safety": "General safety hazards, dangerous conditions, crime-related",
    "other": "Issues that do not clearly fit any other category",
}

# All valid issue type keys
VALID_ISSUE_TYPES = set(ISSUE_TYPE_TAXONOMY.keys())


def _build_taxonomy_text() -> str:
    """Format taxonomy for LLM context."""
    lines = ["Issue type taxonomy:"]
    for key, desc in ISSUE_TYPE_TAXONOMY.items():
        lines.append(f"- {key}: {desc}")
    return "\n".join(lines)
