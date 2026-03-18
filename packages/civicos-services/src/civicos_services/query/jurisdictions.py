"""
Jurisdiction resolution for cross-jurisdiction queries.

Reads parent_jurisdictions from config/registry.json to expand
a base jurisdiction into parents, children, siblings, or combinations.

Tier model (from cross-jurisdiction-query-spec.md):
  self: the queried jurisdiction itself
  child: cities/counties under a parent jurisdiction
  parent: county, state, federal above the base
  sibling: cities sharing same parent county
  cross_county: different county (Phase B)
"""

import functools
import json
import logging
import os
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# Tier weights for relevance boosting
TIER_WEIGHTS = {
    "self": 1.0,
    "child": 1.0,
    "parent": 1.0,
    "sibling": 0.8,
    "cross_county": 0.5,
}


@functools.lru_cache(maxsize=1)
def _load_registry() -> str:
    """Load config/registry.json from the repo root. Cached for process lifetime."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))))
    registry_path = os.path.join(root, "config", "registry.json")
    try:
        with open(registry_path) as f:
            return f.read()
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Could not load registry.json: {e}")
        return "{}"


def _get_registry() -> Dict:
    """Parse cached registry JSON."""
    try:
        return json.loads(_load_registry())
    except json.JSONDecodeError:
        return {}


def resolve_jurisdictions(
    base_jurisdiction: str,
    include_parents: bool = False,
    include_siblings: bool = False,
) -> List[str]:
    """
    Expand a jurisdiction into a list based on parent/sibling flags.

    Supports both upward and downward traversal:
    - A city with include_siblings → adds sibling cities in same county
    - A city with include_parents → adds county, state, federal
    - A county with include_siblings → adds all child cities (downward)
    - A state/federal with include_siblings → adds all child jurisdictions

    Returns deduplicated list preserving insertion order.
    Base jurisdiction is always first.
    """
    result = [base_jurisdiction]

    if not include_parents and not include_siblings:
        return result

    registry = _get_registry()
    all_jurisdictions = registry.get("jurisdictions", {})
    entry = all_jurisdictions.get(base_jurisdiction, {})

    if include_parents:
        for parent in entry.get("parent_jurisdictions", []):
            if parent not in result:
                result.append(parent)

    if include_siblings:
        # Downward resolution: if base is a county/state/federal,
        # find all jurisdictions that list it as a parent
        children = _find_children(base_jurisdiction, all_jurisdictions)
        if children:
            for child in children:
                if child not in result:
                    result.append(child)
        else:
            # Sideways resolution: find cities sharing same parent county
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


def _find_children(jurisdiction: str, all_jurisdictions: Dict) -> List[str]:
    """Find all jurisdictions that list this one as a direct parent."""
    children = []
    for jid, entry in all_jurisdictions.items():
        if jid == jurisdiction:
            continue
        if jurisdiction in entry.get("parent_jurisdictions", []):
            children.append(jid)
    return children


def get_jurisdiction_tier(base_jurisdiction: str, target_jurisdiction: str) -> str:
    """
    Determine the tier relationship between two jurisdictions.

    Returns: "self", "child", "parent", "sibling", or "cross_county"
    """
    if base_jurisdiction == target_jurisdiction:
        return "self"

    registry = _get_registry()
    all_jurisdictions = registry.get("jurisdictions", {})

    base_entry = all_jurisdictions.get(base_jurisdiction, {})
    base_parents = base_entry.get("parent_jurisdictions", [])

    # Target is a parent of base (upward)
    if target_jurisdiction in base_parents:
        return "parent"

    # Target is a child of base (downward)
    target_entry = all_jurisdictions.get(target_jurisdiction, {})
    target_parents = target_entry.get("parent_jurisdictions", [])
    if base_jurisdiction in target_parents:
        return "child"

    # Check if sibling (shares a parent county)
    base_counties = {p for p in base_parents if p.startswith("county-")}
    target_counties = {p for p in target_parents if p.startswith("county-")}

    if base_counties & target_counties:
        return "sibling"

    return "cross_county"


def validate_jurisdiction_ids(jids: List[str]) -> List[str]:
    """Return any jurisdiction IDs not found in the registry."""
    registry = _get_registry()
    all_jurisdictions = registry.get("jurisdictions", {})
    return [jid for jid in jids if jid not in all_jurisdictions]


def get_tier_weight(base_jurisdiction: str, target_jurisdiction: str) -> float:
    """Get the relevance weight for a jurisdiction based on its tier."""
    tier = get_jurisdiction_tier(base_jurisdiction, target_jurisdiction)
    return TIER_WEIGHTS.get(tier, 0.5)
