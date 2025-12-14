"""
Civic - Unified Civic Engagement Platform

The main entry point for civic engagement.

Usage:
    from civic import Civic

    c = Civic("san-rafael-ca")

    # Query (Learn)
    c.what_applies("housing")
    c.whats_next(["transportation"])

    # Action (Act)
    c.start_something(topic="traffic", title="Protected bike lane")
    c.add_voice("agenda_item", "item_123", "support", "As a cyclist...")

    # AI Orchestration
    c.coordinate("init_123", "plan_testimony")
"""

__version__ = "0.1.0"

# Main class
from civic.civic import Civic

# Result types (for type hints)
from civic.civic import (
    RegulatoryStack,
    Decision,
    TranscriptExcerpt,
    Meeting,
    Community,
    Initiative,
    Voice,
    Subscription,
    Preparation,
    Suggestion,
    CoordinationPlan,
    Outcome,
)

# Optional MCP support - lazy import to avoid circular dependencies
MCP_AVAILABLE = False
mcp_server = None
serve_mcp = None

def _load_mcp():
    """Lazy-load MCP components."""
    global MCP_AVAILABLE, mcp_server, serve_mcp
    try:
        from civic.mcp import create_mcp_server, main
        MCP_AVAILABLE = True
        mcp_server = create_mcp_server
        serve_mcp = main
    except ImportError:
        pass

# Don't auto-load MCP - let users call _load_mcp() or import directly

__all__ = [
    # Version
    "__version__",
    # Main class
    "Civic",
    # Result types
    "RegulatoryStack",
    "Decision",
    "TranscriptExcerpt",
    "Meeting",
    "Community",
    "Initiative",
    "Voice",
    "Subscription",
    "Preparation",
    "Suggestion",
    "CoordinationPlan",
    "Outcome",
    # MCP
    "MCP_AVAILABLE",
    "mcp_server",
    "serve_mcp",
]
