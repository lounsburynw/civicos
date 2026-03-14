"""
Jurisdiction resolution for cross-jurisdiction queries.

Reads parent_jurisdictions from config/registry.json to expand
a base jurisdiction into parents, siblings, or both.

Tier model (from cross-jurisdiction-query-spec.md):
  Tier 1 (parent): county, state, federal — always relevant
  Tier 2 (sibling): cities sharing same parent county — sometimes relevant
  Tier 3 (cross-county): different county — rarely relevant (Phase B)
"""

import json
import logging
import os
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Tier weights for relevance boosting (from spec)
TIER_WEIGHTS = {
    "self": 1.0,
    "parent": 1.0,
    "sibling": 0.8,
    "cross_county": 0.5,
}


def _load_registry() -> Dict:
    """Load config/registry.json from the repo root."""
    # Walk up from this file to find repo root
    # This file: packages/civicos-services/src/civicos_services/query/jurisdictions.py
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))))
    registry_path = os.path.join(root, "config", "registry.json")
    try:
        with open(registry_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load registry.json: {e}")
        return {}


def resolve_jurisdictions(
    base_jurisdiction: str,
    include_parents: bool = False,
    include_siblings: bool = False,
) -> List[str]:
    """
    Expand a jurisdiction into a list based on parent/sibling flags.

    Returns deduplicated list preserving insertion order.
    Base jurisdiction is always first.
    """
    result = [base_jurisdiction]

    if not include_parents and not include_siblings:
        return result

    registry = _load_registry()
    all_jurisdictions = registry.get("jurisdictions", {})

    if include_parents:
        entry = all_jurisdictions.get(base_jurisdiction, {})
        for parent in entry.get("parent_jurisdictions", []):
            if parent not in result:
                result.append(parent)

    if include_siblings:
        # Find parent counties, then find all cities sharing them
        entry = all_jurisdictions.get(base_jurisdiction, {})
        parent_counties: Set[str] = set()
        for parent in entry.get("parent_jurisdictions", []):
            if parent.startswith("county-"):
                parent_counties.add(parent)

        for other_jid, other_entry in all_jurisdictions.items():
            if other_jid in result:
                continue
            other_parents = other_entry.get("parent_jurisdictions", [])
            if any(p in parent_counties for p in other_parents):
                result.append(other_jid)

    return result


def get_jurisdiction_tier(base_jurisdiction: str, target_jurisdiction: str) -> str:
    """
    Determine the tier relationship between two jurisdictions.

    Returns: "self", "parent", "sibling", or "cross_county"
    """
    if base_jurisdiction == target_jurisdiction:
        return "self"

    registry = _load_registry()
    all_jurisdictions = registry.get("jurisdictions", {})

    base_entry = all_jurisdictions.get(base_jurisdiction, {})
    base_parents = base_entry.get("parent_jurisdictions", [])

    if target_jurisdiction in base_parents:
        return "parent"

    # Check if sibling (shares a parent county)
    base_counties = {p for p in base_parents if p.startswith("county-")}
    target_entry = all_jurisdictions.get(target_jurisdiction, {})
    target_parents = target_entry.get("parent_jurisdictions", [])
    target_counties = {p for p in target_parents if p.startswith("county-")}

    if base_counties & target_counties:
        return "sibling"

    return "cross_county"


def get_tier_weight(base_jurisdiction: str, target_jurisdiction: str) -> float:
    """Get the relevance weight for a jurisdiction based on its tier."""
    tier = get_jurisdiction_tier(base_jurisdiction, target_jurisdiction)
    return TIER_WEIGHTS.get(tier, 0.5)
