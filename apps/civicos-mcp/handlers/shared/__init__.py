"""
Shared handlers for federal/state/coordination tools.

These handlers work across all jurisdictions:
- Federal tools query shared federal datasets
- State tools query shared state datasets
- Coordination tools use the relay network

Most of these handlers don't need modification since they
don't have hardcoded jurisdiction-specific values.
"""

# Re-export from the original handlers.py for now
# These handlers don't have hardcoded values and work as-is
from ..loader import FEDERAL_TOOLS, STATE_TOOLS, COORDINATION_TOOLS, CROSS_LEVEL_TOOLS

__all__ = [
    "FEDERAL_TOOLS",
    "STATE_TOOLS",
    "COORDINATION_TOOLS",
    "CROSS_LEVEL_TOOLS",
]
