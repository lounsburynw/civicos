"""
Service Registry — Single source of truth for CivicOS service URLs.

Loads config/registry.json and provides URL lookups for jurisdictions,
relay, and Modal deployment. Environment variables override registry defaults.

Search paths for registry.json:
    1. CIVICOS_REGISTRY_PATH (explicit override)
    2. /app/registry.json (Modal deployment)
    3. config/registry.json (local development, relative to cwd)
    4. {project_root}/config/registry.json (fallback)

Usage:
    from civicos.registry import get_jurisdiction_url, get_relay_url

    url = get_jurisdiction_url("city-san-rafael")
    # -> "https://san-rafael.civicosproject.org"

    relay = get_relay_url()
    # -> "https://san-rafael.civicosproject.org/relay"

Environment variable overrides (highest priority):
    JURISDICTION_MCP_URL  — overrides jurisdiction URL lookup
    CIVICOS_RELAY_URL     — overrides relay URL
    CIVICOS_API_URL       — fallback relay URL override
"""

import json
import os
from pathlib import Path
from typing import Optional


_registry: Optional[dict] = None

# Defensive cap on region-member recursion depth. A misconfigured
# registry with deeply nested regions should not cause unbounded
# expansion (the cycle detector catches true cycles; this catches
# pathological tree depth before it becomes a performance issue).
_MAX_REGION_RECURSION_DEPTH = 16

# Search paths for registry.json, tried in order
_SEARCH_PATHS = [
    "/app/registry.json",                    # Modal deployment
    "config/registry.json",                  # Local dev (relative to cwd)
]


def _find_registry_path() -> Optional[Path]:
    """Find registry.json using search paths."""
    # Explicit override
    explicit = os.environ.get("CIVICOS_REGISTRY_PATH")
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p

    for path_str in _SEARCH_PATHS:
        p = Path(path_str)
        if p.exists():
            return p

    # Try relative to this file's project root
    try:
        project_root = Path(__file__).resolve().parents[4]  # src/civicos -> packages/civicos -> packages -> project root
        fallback = project_root / "config" / "registry.json"
        if fallback.exists():
            return fallback
    except IndexError:
        pass

    return None


def _load_registry() -> dict:
    """Load and cache registry.json."""
    global _registry
    if _registry is not None:
        return _registry

    path = _find_registry_path()
    if path is None:
        # Return minimal defaults so apps don't crash
        _registry = {
            "modal_workspace": "civicos",
            "jurisdictions": {},
            "relay": {},
        }
        return _registry

    with open(path) as f:
        _registry = json.load(f)
    return _registry


def reset_registry() -> None:
    """Reset cached registry (for testing)."""
    global _registry
    _registry = None


def get_registry() -> dict:
    """Get the full registry dict."""
    return _load_registry()


# ---------------------------------------------------------------------------
# Regions
#
# A region is a named set of jurisdiction IDs declared under the
# ``regions`` top-level key in ``config/registry.json``. Regions
# exist to support scope walks like "what's happening across Marin
# County cities" — a question the parent-chain and sibling walks
# cannot answer cleanly because county-marin has non-municipal
# children (school districts) that a user asking about "Marin" does
# not mean.
#
# A region's ``members`` list may contain either:
#   - concrete jurisdiction IDs (e.g. ``city-san-rafael``), or
#   - names of other regions (e.g. ``marin`` inside ``bay-area``),
#     which are expanded recursively at lookup time.
#
# There is no prefix convention to distinguish jurisdiction IDs from
# region names — the resolver checks the ``regions`` dict first and
# falls through to treating the member as a concrete jurisdiction.
# Jurisdictions use prefixes like ``city-``, ``county-``, ``state-``,
# and ``country-``; regions use short names, so collision is not a
# practical concern for current data.
# ---------------------------------------------------------------------------


def get_regions() -> dict:
    """Return the ``regions`` dict from registry.json, or ``{}``.

    A missing ``regions`` key is not an error — older registries
    predate the concept and should continue to work. Callers that
    depend on a specific region being present should handle ``None``
    from :func:`get_region`.
    """
    reg = _load_registry()
    return reg.get("regions", {}) or {}


def get_region(name: str) -> Optional[dict]:
    """Return a single region's entry by name, or ``None``."""
    return get_regions().get(name)


def resolve_region_members(
    name: str,
    _seen: Optional[set] = None,
    _depth: int = 0,
) -> list:
    """Expand a region to its concrete jurisdiction-ID members.

    Recursive: if a member name matches another region, the other
    region is expanded in-place and its members are spliced into
    the result list (deduplicated, order preserved).

    Args:
        name: Region name to resolve (e.g. ``"marin"``).
        _seen: Internal cycle-detection set. Callers should not
            pass this — it's threaded through recursive calls so
            ``A → B → A`` raises cleanly instead of stack-overflowing.
        _depth: Internal recursion-depth counter. Guards against
            pathological tree depth in case the cycle detector is
            somehow bypassed.

    Returns:
        Deduplicated list of concrete jurisdiction IDs, in the
        order they first appear during recursive expansion.

    Raises:
        ValueError: If the region name is unknown, if a cycle is
            detected, or if recursion exceeds
            ``_MAX_REGION_RECURSION_DEPTH``.
    """
    if _depth > _MAX_REGION_RECURSION_DEPTH:
        raise ValueError(
            f"Region expansion exceeded max depth "
            f"{_MAX_REGION_RECURSION_DEPTH} at region '{name}' "
            f"— check config/registry.json for pathological nesting"
        )

    if _seen is None:
        _seen = set()
    if name in _seen:
        raise ValueError(
            f"Region cycle detected: '{name}' appears twice in "
            f"its own expansion chain (seen: {sorted(_seen)})"
        )
    _seen = _seen | {name}

    region = get_region(name)
    if region is None:
        raise ValueError(f"Unknown region: '{name}'")

    regions_index = get_regions()
    out: list = []
    seen_members: set = set()
    for member in region.get("members", []) or []:
        if member in regions_index:
            # Recurse into nested region.
            for nested in resolve_region_members(
                member, _seen=_seen, _depth=_depth + 1
            ):
                if nested not in seen_members:
                    seen_members.add(nested)
                    out.append(nested)
        else:
            if member not in seen_members:
                seen_members.add(member)
                out.append(member)
    return out


def find_region_for_jurisdiction(jurisdiction: str) -> Optional[str]:
    """Find the first region that contains ``jurisdiction`` (direct or nested).

    Used by the MCP scope walker to answer "what region does this
    server's primary jurisdiction belong to?" when resolving
    ``Scope.REGION`` / ``Scope.PRIMARY_PLUS_REGION``.

    Returns the region *name* (not the dict). If no region in the
    registry contains the jurisdiction, returns ``None`` — the
    scope walker will then degrade to primary-only behavior.

    A ``region-*`` jurisdiction IS its own region: ``region-marin``
    maps directly to the ``"marin"`` region. This enables regional
    servers to resolve their own membership without being listed as
    a member of the region they represent.

    If multiple regions match, the first in iteration order wins.
    This is deterministic because ``config/registry.json`` is a
    dict literal preserving insertion order, but callers should
    still avoid overlapping region definitions when possible.

    Malformed regions (cycles, unknown nested names) are skipped
    silently — a single bad region should not break lookup for the
    others.
    """
    # A region-level primary IS the region it represents.
    if jurisdiction.startswith("region-"):
        region_name = jurisdiction[len("region-"):]
        regions = get_regions()
        if region_name in regions:
            return region_name

    regions = get_regions()
    for name in regions:
        try:
            if jurisdiction in resolve_region_members(name):
                return name
        except ValueError:
            # Cycle or unknown nested region — skip this region
            # and try the next one. The resolver still raises for
            # direct callers; we only swallow the error here to
            # protect the lookup path from one bad entry.
            continue
    return None


def get_jurisdiction_url(jurisdiction: str) -> str:
    """Get the stable public URL for a jurisdiction.

    Priority:
        1. JURISDICTION_MCP_URL env var (if set)
        2. Registry domain lookup
        3. Modal workspace URL fallback
    """
    env_url = os.environ.get("JURISDICTION_MCP_URL")
    if env_url:
        return env_url.rstrip("/")

    reg = _load_registry()
    jur = reg.get("jurisdictions", {}).get(jurisdiction)
    if jur and jur.get("domain"):
        return f"https://{jur['domain']}"

    # Fallback: derive from Modal workspace
    workspace = reg.get("modal_workspace", os.environ.get("MODAL_WORKSPACE", "civicos"))
    app_name = get_modal_app_name(jurisdiction)
    return f"https://{workspace}--{app_name}-mcpserver-mcp-endpoint.modal.run"


def get_default_jurisdiction() -> str:
    """Get the default jurisdiction ID from registry."""
    env = os.environ.get("CIVICOS_JURISDICTION")
    if env:
        return env
    reg = _load_registry()
    return reg.get("default_jurisdiction", "city-san-rafael")


def get_default_jurisdiction_url() -> str:
    """Get the URL for the default jurisdiction (from registry, not hardcoded)."""
    return get_jurisdiction_url(get_default_jurisdiction())


def get_jurisdiction_domain(jurisdiction: str) -> Optional[str]:
    """Get just the domain for a jurisdiction, or None."""
    reg = _load_registry()
    jur = reg.get("jurisdictions", {}).get(jurisdiction)
    if jur:
        return jur.get("domain")
    return None


def get_relay_url(jurisdiction: Optional[str] = None) -> str:
    """Get the relay/coordination service URL.

    Priority:
        1. CIVICOS_RELAY_URL env var
        2. CIVICOS_API_URL env var (legacy)
        3. Derived from jurisdiction domain ({domain}/relay)
        4. Default relay URL
    """
    env_url = os.environ.get("CIVICOS_RELAY_URL") or os.environ.get("CIVICOS_API_URL")
    if env_url:
        return env_url.rstrip("/")

    # Derive from jurisdiction domain if available
    if jurisdiction:
        domain = get_jurisdiction_domain(jurisdiction)
        if domain:
            return f"https://{domain}/relay"

    # Try default jurisdiction
    default_jur = get_default_jurisdiction()
    domain = get_jurisdiction_domain(default_jur)
    if domain:
        return f"https://{domain}/relay"

    return "https://san-rafael.civicosproject.org/relay"


def get_deployment_config(jurisdiction: str) -> dict:
    """Get deployment config for a jurisdiction from registry.

    Returns a dict with:
        - ``modal_secret``: Modal secret name for DATABASE_URL (default: ``"civicos-env"``)
        - ``min_containers``: containers to keep warm (default: ``0``)

    Values come from the jurisdiction's registry entry, falling back to
    sensible defaults. This replaces hardcoded if/elif chains in
    ``modal_mcp.py`` — adding a new jurisdiction with custom deployment
    config only requires editing ``config/registry.json``.
    """
    reg = _load_registry()
    entry = reg.get("jurisdictions", {}).get(jurisdiction, {})
    return {
        "modal_secret": entry.get("modal_secret", "civicos-env"),
        "min_containers": entry.get("min_containers", 0),
    }


def get_modal_workspace() -> str:
    """Get the Modal workspace name."""
    env = os.environ.get("MODAL_WORKSPACE")
    if env:
        return env
    reg = _load_registry()
    return reg.get("modal_workspace", "civicos")


def get_modal_app_name(jurisdiction: str) -> str:
    """Derive Modal app name from jurisdiction ID."""
    # Check registry first
    reg = _load_registry()
    jur = reg.get("jurisdictions", {}).get(jurisdiction)
    if jur and jur.get("modal_app_name"):
        return jur["modal_app_name"]

    # Derive from jurisdiction ID
    if jurisdiction == "country-united-states":
        return "civicos-federal"
    for prefix in ["city-", "county-", "state-", "country-"]:
        if jurisdiction.startswith(prefix):
            return f"civicos-{jurisdiction[len(prefix):]}"
    return f"civicos-{jurisdiction}"


def get_local_dev_url(service: str) -> Optional[str]:
    """Get local development URL for a service (relay, mcp, ws)."""
    reg = _load_registry()
    local = reg.get("local_dev", {})
    return local.get(f"{service}_url")
