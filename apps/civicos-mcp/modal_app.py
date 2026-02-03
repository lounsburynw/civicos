"""
Modal deployment for San Rafael City MCP Server.

Primary user-facing MCP server with all 38 tools.
Part of the federated MCP architecture.

Tools (38):
    - All city, state, and federal tools
    - Coordination tools (voice, initiatives)

Endpoint:
    san-rafael.civicosproject.org/mcp

Deploy:
    modal deploy apps/civicos-mcp/modal_app.py

Federated Architecture:
    This is the primary city-level server. For reference implementations:
    - Federal: modal deploy apps/civicos-mcp/modal_federal.py
    - California: modal deploy apps/civicos-mcp/modal_california.py
"""

import modal
from modal_base import mcp_image, MCPServerMixin

app = modal.App("civicos-mcp")


@app.cls(
    image=mcp_image,
    secrets=[
        modal.Secret.from_name("civicos-env"),
        modal.Secret.from_name("civic-google"),  # GOOGLE_MAPS_API_KEY for geocoding
    ],
    memory=4096,
    timeout=300,
    min_containers=1,  # Primary server - keep warm
)
@modal.concurrent(max_inputs=20)
class MCPServer(MCPServerMixin):
    """San Rafael city-level MCP server (38 tools)."""
    pass


@app.local_entrypoint()
def main():
    """Local entrypoint."""
    print("CivicOS San Rafael MCP Server")
    print()
    print("This is the primary city-level server with all 38 tools.")
    print()
    print("Deploy: modal deploy apps/civicos-mcp/modal_app.py")
    print("Endpoint: san-rafael.civicosproject.org/mcp")
    print()
    print("Federated servers:")
    print("  Federal:    modal deploy apps/civicos-mcp/modal_federal.py")
    print("  California: modal deploy apps/civicos-mcp/modal_california.py")
