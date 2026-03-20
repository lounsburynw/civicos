"""
Local relevance scoring for federal rules.

Heuristic-based scoring (no LLM) that computes how relevant a federal rule
is to a specific jurisdiction. Three signal types:

1. Agency-to-topic mapping — federal agencies mapped to local policy areas
2. Geographic text matching — mentions of state/county/city in title/abstract
3. CFR part matching — regulation IDs matching locally relevant CFR titles
"""

import re
from typing import Any

# Weight allocation (sums to 1.0)
AGENCY_WEIGHT = 0.4
GEO_WEIGHT = 0.3
CFR_WEIGHT = 0.3

# Federal agency → local policy topic mapping
# Keys are substrings matched case-insensitively against agency_names
AGENCY_TOPIC_MAP: dict[str, list[str]] = {
    "Environmental Protection Agency": ["environment", "water", "climate"],
    "Housing and Urban Development": ["housing", "zoning"],
    "Department of Transportation": ["transportation", "infrastructure"],
    "Federal Emergency Management": ["public_safety", "climate"],
    "Department of Education": ["education"],
    "Department of Health and Human Services": ["public_safety", "health"],
    "Department of Agriculture": ["environment", "climate", "water"],
    "National Oceanic and Atmospheric": ["water", "environment", "climate"],
    "Department of the Interior": ["environment", "land_use"],
    "Department of Energy": ["climate", "infrastructure"],
    "Department of Labor": ["labor"],
    "Federal Communications Commission": ["infrastructure"],
    "Federal Housing Finance": ["housing"],
    "Small Business Administration": ["budget"],
    "Corps of Engineers": ["water", "environment", "infrastructure"],
    "Fish and Wildlife": ["environment"],
    "Bureau of Land Management": ["land_use", "environment"],
    "Forest Service": ["environment", "climate"],
    "Coast Guard": ["water", "public_safety"],
    "Federal Aviation": ["transportation"],
    "Federal Highway": ["transportation", "infrastructure"],
    "Federal Transit": ["transportation"],
    "Pipeline and Hazardous Materials": ["public_safety", "environment"],
    "Occupational Safety": ["labor", "public_safety"],
}

# CFR titles relevant to local government
# Maps CFR title number to topic categories
RELEVANT_CFR_TITLES: dict[int, list[str]] = {
    7: ["environment", "water"],          # Agriculture
    10: ["infrastructure"],                # Energy
    14: ["transportation"],                # Aeronautics
    23: ["transportation", "infrastructure"],  # Highways
    24: ["housing", "zoning"],             # Housing and Urban Development
    29: ["labor"],                         # Labor
    30: ["environment"],                   # Mineral Resources
    33: ["water", "environment"],          # Navigation and Navigable Waters
    36: ["land_use", "environment"],       # Parks, Forests, Public Property
    40: ["environment", "water", "climate"],  # Protection of Environment
    42: ["public_safety", "health"],       # Public Health
    44: ["public_safety"],                 # Emergency Management
    45: ["education"],                     # Public Welfare
    49: ["transportation", "public_safety"],  # Transportation
}

# Pattern to extract CFR title numbers from regulation_id_numbers
CFR_PATTERN = re.compile(r"(\d+)\s*CFR", re.IGNORECASE)


def build_jurisdiction_config(jurisdiction_id: str) -> dict[str, Any]:
    """Build jurisdiction-specific config for relevance scoring.

    For now, returns San Rafael / Marin County / California config.
    Can be extended per-jurisdiction later.
    """
    # Active local policy areas (topics the jurisdiction actively legislates on)
    active_topics = {
        "housing", "zoning", "land_use", "transportation", "climate",
        "environment", "water", "public_safety", "education", "budget",
        "infrastructure", "health", "labor",
    }

    # Geographic terms to match (ordered by specificity — more specific = higher score)
    # Each entry: (pattern, weight, label for reason string)
    geo_terms = [
        # Tier 1: Direct local mentions (full score)
        (r"\bSan\s+Rafael\b", 1.0, "San Rafael"),
        (r"\bMarin\s+County\b", 1.0, "Marin County"),
        (r"\bMarin\b", 0.9, "Marin"),
        # Tier 2: Regional (partial score)
        (r"\bBay\s+Area\b", 0.6, "Bay Area"),
        (r"\bNorthern\s+California\b", 0.5, "Northern California"),
        # Tier 3: State-level (lower score)
        (r"\bCalifornia\b", 0.3, "California"),
        (r"\bCA\b", 0.2, "CA"),
    ]

    return {
        "jurisdiction_id": jurisdiction_id,
        "active_topics": active_topics,
        "geo_terms": [(re.compile(pat, re.IGNORECASE), weight, label) for pat, weight, label in geo_terms],
    }


def score_agency_relevance(
    agency_names: list[str],
    active_topics: set[str],
) -> tuple[float, list[str]]:
    """Score based on agency-to-topic mapping.

    Returns (score 0-1, list of reason strings).
    """
    if not agency_names:
        return 0.0, []

    matched_topics: set[str] = set()
    matched_agencies: list[str] = []

    agencies_str = " ".join(agency_names).lower()

    for agency_pattern, topics in AGENCY_TOPIC_MAP.items():
        if agency_pattern.lower() in agencies_str:
            local_topics = [t for t in topics if t in active_topics]
            if local_topics:
                matched_topics.update(local_topics)
                matched_agencies.append(agency_pattern.split()[-1])  # Short name

    if not matched_topics:
        return 0.0, []

    # More matched topics = higher score, capped at 1.0
    score = min(len(matched_topics) / 3.0, 1.0)
    reasons = [f"agency_topic:{t}" for t in sorted(matched_topics)]
    return score, reasons


def score_geographic_relevance(
    title: str,
    abstract: str,
    geo_terms: list[tuple[re.Pattern, float]],
) -> tuple[float, list[str]]:
    """Score based on geographic text matching.

    Returns (score 0-1, list of reason strings).
    """
    text = f"{title or ''} {abstract or ''}"
    if not text.strip():
        return 0.0, []

    best_score = 0.0
    reasons: list[str] = []

    for pattern, weight, label in geo_terms:
        if pattern.search(text):
            if weight > best_score:
                best_score = weight
            reasons.append(f"geo:{label}")

    # Bonus for multiple tiers of geographic mention
    if len(reasons) >= 2:
        best_score = min(best_score * 1.2, 1.0)

    return best_score, reasons


def score_cfr_relevance(
    regulation_id_numbers: list[str],
    active_topics: set[str],
) -> tuple[float, list[str]]:
    """Score based on CFR title matching.

    Returns (score 0-1, list of reason strings).
    """
    if not regulation_id_numbers:
        return 0.0, []

    matched_topics: set[str] = set()
    reasons: list[str] = []

    for reg_id in regulation_id_numbers:
        if not isinstance(reg_id, str):
            continue
        matches = CFR_PATTERN.findall(reg_id)
        for title_num_str in matches:
            title_num = int(title_num_str)
            if title_num in RELEVANT_CFR_TITLES:
                topics = RELEVANT_CFR_TITLES[title_num]
                local_topics = [t for t in topics if t in active_topics]
                if local_topics:
                    matched_topics.update(local_topics)
                    reasons.append(f"cfr:{title_num}")

    if not matched_topics:
        return 0.0, []

    score = min(len(matched_topics) / 2.0, 1.0)
    return score, reasons


def score_federal_rule(
    rule: dict[str, Any],
    jurisdiction_config: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    """Compute local relevance score for a federal rule.

    Args:
        rule: Federal rule dict (from storage backend).
        jurisdiction_config: Output of build_jurisdiction_config().
            If None, uses San Rafael defaults.

    Returns:
        (score: float 0.0-1.0, reasons: list[str])
    """
    if jurisdiction_config is None:
        jurisdiction_config = build_jurisdiction_config("city-san-rafael")

    active_topics = jurisdiction_config["active_topics"]
    geo_terms = jurisdiction_config["geo_terms"]

    # Parse fields
    agency_names = rule.get("agency_names") or []
    if isinstance(agency_names, str):
        agency_names = [agency_names]

    regulation_ids = rule.get("regulation_id_numbers") or []
    if isinstance(regulation_ids, str):
        regulation_ids = [regulation_ids]

    title = rule.get("title") or ""
    abstract = rule.get("abstract") or ""

    # Score each signal
    agency_score, agency_reasons = score_agency_relevance(agency_names, active_topics)
    geo_score, geo_reasons = score_geographic_relevance(title, abstract, geo_terms)
    cfr_score, cfr_reasons = score_cfr_relevance(regulation_ids, active_topics)

    # Weighted combination
    total = (
        AGENCY_WEIGHT * agency_score
        + GEO_WEIGHT * geo_score
        + CFR_WEIGHT * cfr_score
    )

    reasons = agency_reasons + geo_reasons + cfr_reasons

    return round(total, 3), reasons
