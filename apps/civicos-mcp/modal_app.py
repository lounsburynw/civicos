"""
Modal deployment for CivicOS MCP Server.

Deploys the MCP server as a serverless web endpoint on Modal, enabling
AI clients (Claude.ai, ChatGPT) to query civic data.

Architecture:
    Claude.ai/ChatGPT -> Modal (MCP endpoint) -> Supabase (civic data)

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal token new
    3. Create secret with required env vars:
       modal secret create civicos-env \\
           DATABASE_URL="postgresql://..." \\
           RELAY_DATABASE_URL="postgresql://..." \\
           CIVICOS_JURISDICTION="city-san-rafael"
    4. Deploy: modal deploy apps/civicos-mcp/modal_app.py

Usage:
    # Deploy to Modal
    modal deploy apps/civicos-mcp/modal_app.py

    # Get the endpoint URL from Modal dashboard
    # Example: https://civicos--mcp-server.modal.run/mcp

    # Connect from Claude.ai or ChatGPT using the URL
"""

import modal

# Define the Modal app
app = modal.App("civicos-mcp")

# Build image with MCP dependencies
mcp_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies
    .apt_install("libpq-dev", "gcc")
    # Python dependencies
    .pip_install(
        # MCP server
        "mcp>=1.0.0",
        "fastmcp>=0.1.0",
        # Database
        "psycopg2-binary>=2.9.0",
        # Embeddings (for vector search)
        "fastembed>=0.3.0",
        "numpy<2",
        # HTTP/async
        "httpx>=0.24.0",
        "uvicorn>=0.30.0",
        "starlette>=0.38.0",
        # Utils
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
    )
    # Pre-download embedding model during image build
    .run_commands(
        "python -c \"from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')\""
    )
    # Add local packages (same pattern as modal_vectors.py)
    .add_local_python_source("civicos")
    .add_local_python_source("civicos_config")
    .add_local_python_source("civicos_relay")
)

# Mount the apps directory for MCP server code
apps_mount = modal.Mount.from_local_dir(
    "apps/civicos-mcp",
    remote_path="/app/civicos-mcp",
)


@app.function(
    image=mcp_image,
    mounts=[apps_mount],
    secrets=[modal.Secret.from_name("civicos-env")],
    memory=4096,  # 4GB for embedding model
    timeout=120,  # 2 min timeout for complex queries
    keep_warm=1,  # Always keep 1 instance ready (no cold starts)
    allow_concurrent_inputs=10,  # Handle multiple requests
)
@modal.web_endpoint(method="POST", docs=True)
async def mcp_endpoint(request: dict) -> dict:
    """
    MCP endpoint for CivicOS.

    Handles MCP protocol requests from Claude.ai and ChatGPT.
    Uses the CivicOS API directly for civic data queries.

    Request format (MCP JSON-RPC):
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_meeting_history", "arguments": {"query": "housing"}},
            "id": 1
        }
    """
    import os
    import sys

    # Add mounted apps directory to path
    sys.path.insert(0, "/app/civicos-mcp")

    # Import CivicOS
    from civicos import CivicOS

    # Initialize client
    jurisdiction = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")
    civic = CivicOS(jurisdiction)

    # Define available tools with their handlers
    tools = {
        "search_meeting_history": {
            "description": "Search past city council meetings and decisions",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "handler": lambda args: civic.what_happened(args.get("query", "")),
        },
        "get_upcoming_meetings": {
            "description": "Get upcoming city council meetings and agenda items",
            "parameters": {"type": "object", "properties": {"days": {"type": "integer", "default": 30}}},
            "handler": lambda args: civic.whats_next(days=args.get("days", 30)),
        },
        "find_similar_issues": {
            "description": "Find community issues similar to a topic",
            "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
            "handler": lambda args: civic.whos_with_me(args.get("topic", "")),
        },
        "search_regulatory_stack": {
            "description": "Search relevant laws and regulations",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "handler": lambda args: civic.what_applies(args.get("query", "")),
        },
    }

    try:
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id", 1)

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "CivicOS MCP Server", "version": "1.0.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
                "id": request_id,
            }

        elif method == "tools/list":
            tool_list = [
                {"name": name, "description": info["description"], "inputSchema": info["parameters"]}
                for name, info in tools.items()
            ]
            return {"jsonrpc": "2.0", "result": {"tools": tool_list}, "id": request_id}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            if tool_name not in tools:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
                    "id": request_id,
                }

            result = tools[tool_name]["handler"](tool_args)
            # Format result as string for MCP
            if isinstance(result, list):
                result_text = "\n\n".join(str(item) for item in result[:10])
            else:
                result_text = str(result)

            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": result_text}], "isError": False},
                "id": request_id,
            }

        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id,
            }

    except Exception as e:
        import traceback
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": str(e), "data": traceback.format_exc()},
            "id": request.get("id", 1),
        }


@app.function(
    image=mcp_image,
    secrets=[modal.Secret.from_name("civicos-env")],
    memory=1024,
    timeout=30,
)
@modal.web_endpoint(method="GET", docs=True)
async def health() -> dict:
    """Health check endpoint."""
    import os
    return {
        "status": "healthy",
        "service": "civicos-mcp",
        "jurisdiction": os.getenv("CIVICOS_JURISDICTION", "city-san-rafael"),
        "platform": "modal",
        "tools": ["search_meeting_history", "get_upcoming_meetings", "find_similar_issues", "search_regulatory_stack"],
    }


@app.local_entrypoint()
def main():
    """Local entrypoint for testing."""
    print("CivicOS MCP Server (Modal)")
    print()
    print("Deploy:")
    print("  modal deploy apps/civicos-mcp/modal_app.py")
    print()
    print("Test locally:")
    print("  modal serve apps/civicos-mcp/modal_app.py")
    print()
    print("After deployment, get your endpoint URL from Modal dashboard.")
    print("Example: https://civicos--mcp-endpoint.modal.run")
    print()
    print("Connect from Claude.ai/ChatGPT using the MCP endpoint URL.")
