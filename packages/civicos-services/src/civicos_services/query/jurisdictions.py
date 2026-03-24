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

import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

# Tier weights for relevance boosting.
# Parent tiers are level-aware: county (1 hop) > state (2 hops) > federal (3 hops).
TIER_WEIGHTS = {
    "self": 1.0,
    "child": 1.0,
    "parent": 0.7,            # fallback for unrecognized parent level
    "parent_county": 0.9,     # one level up
    "parent_state": 0.7,      # two levels up
    "parent_federal": 0.5,    # three levels up
    "sibling": 0.8,
    "cross_county": 0.5,
}

# Maps jurisdiction ID prefix to parent tier name
_PARENT_TIER_BY_PREFIX = {
    "county-": "parent_county",
    "state-": "parent_state",
    "country-": "parent_federal",
}


def _get_registry() -> Dict:
    """Load registry via civicos.registry (handles all search paths + caching)."""
    try:
        from civicos.registry import _load_registry
        return _load_registry()
    except Exception:
        logger.warning("Could not load registry.json via civicos.registry")
        return {}


MAX_DOWNWARD_FANOUT = 20


def resolve_jurisdictions(
    base_jurisdiction: str,
    include_parents: bool = False,
    include_siblings: bool = False,
    max_children: int = MAX_DOWNWARD_FANOUT,
) -> List[str]:
    """
    Expand a jurisdiction into a list based on parent/sibling flags.

    Supports both upward and downward traversal:
    - A city with include_siblings → adds sibling cities in same county
    - A city with include_parents → adds county, state, federal
    - A county with include_siblings → adds all child cities (downward)
    - A state/federal with include_siblings → adds all child jurisdictions

    Downward resolution is capped at max_children to prevent fan-out
    explosion when querying state/county-level with many child jurisdictions.

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
            added = 0
            for child in children:
                if child not in result:
                    result.append(child)
                    added += 1
                    if added >= max_children:
                        logger.warning(
                            f"Downward fan-out capped at {max_children} for "
                            f"{base_jurisdiction} ({len(children)} children total)"
                        )
                        break
        else:
            # Sideways resolution: find cities sharing same parent county
            parent_counties: Set[str] = set()
            for parent in entry.get("parent_jurisdictions", []):
                if parent.startswith("county-"):
                    parent_counties.add(parent)

            added = 0
            for other_jid, other_entry in all_jurisdictions.items():
                if other_jid in result:
                    continue
                other_parents = other_entry.get("parent_jurisdictions", [])
                if any(p in parent_counties for p in other_parents):
                    result.append(other_jid)
                    added += 1
                    if added >= max_children:
                        logger.warning(
                            f"Sibling fan-out capped at {max_children} for "
                            f"{base_jurisdiction}"
                        )
                        break

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

    Returns: "self", "child", "parent_county", "parent_state", "parent_federal",
    "parent" (fallback), "sibling", or "cross_county"
    """
    if base_jurisdiction == target_jurisdiction:
        return "self"

    registry = _get_registry()
    all_jurisdictions = registry.get("jurisdictions", {})

    base_entry = all_jurisdictions.get(base_jurisdiction, {})
    base_parents = base_entry.get("parent_jurisdictions", [])

    # Target is a parent of base (upward) — return level-specific tier
    if target_jurisdiction in base_parents:
        for prefix, tier in _PARENT_TIER_BY_PREFIX.items():
            if target_jurisdiction.startswith(prefix):
                return tier
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
