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
