"""
DEPRECATED: Use modal_mcp.py instead.

This file is kept for backward compatibility. The unified deployment
in modal_mcp.py supports all jurisdictions with a single codebase.

Migration:
    # Old (San Rafael only)
    modal deploy apps/civicos-mcp/modal_app.py

    # New (any jurisdiction)
    modal deploy apps/civicos-mcp/modal_mcp.py                                    # San Rafael (default)
    CIVICOS_JURISDICTION=state-california modal deploy apps/civicos-mcp/modal_mcp.py
    CIVICOS_JURISDICTION=country-united-states modal deploy apps/civicos-mcp/modal_mcp.py

See modal_mcp.py for full documentation.
"""

# Re-export from unified deployment for backward compatibility
import os
os.environ.setdefault("CIVICOS_JURISDICTION", "city-san-rafael")

from modal_mcp import app, MCPServer, mcp_image

__all__ = ["app", "MCPServer", "mcp_image"]
