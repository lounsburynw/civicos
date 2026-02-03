"""
Handler modules for CivicOS MCP server.

Handlers are organized by jurisdiction level:
- shared/: Federal, state, and coordination tools (work globally)
- jurisdiction/: City-specific tools (filtered by jurisdiction_id)

The tool_loader module provides functions to load and filter tools
based on the deployment jurisdiction.
"""

from .loader import (
    JurisdictionConfig,
    load_jurisdiction_config,
    get_tools_for_level,
    TOOL_LEVELS,
    FEDERAL_TOOLS,
    STATE_TOOLS,
    CITY_TOOLS,
    COORDINATION_TOOLS,
)

__all__ = [
    "JurisdictionConfig",
    "load_jurisdiction_config",
    "get_tools_for_level",
    "TOOL_LEVELS",
    "FEDERAL_TOOLS",
    "STATE_TOOLS",
    "CITY_TOOLS",
    "COORDINATION_TOOLS",
]
