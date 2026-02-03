"""
Modal deployment for California State MCP Server.

Reference implementation for state-level data (CA legislation, State Controller).
Part of the federated MCP architecture.

Tools (4):
    - get_federal_expenditures: FAC Single Audit data (inherited)
    - get_funding_flow: Federal funding traces (inherited)
    - get_intergovernmental_revenue: CA State Controller data
    - search_regulatory_stack: CA + federal legislation

Endpoint:
    california.civicosproject.org/mcp

Deploy:
    modal deploy apps/civicos-mcp/modal_california.py
"""

import modal

app = modal.App("civicos-california")

# Build image with all MCP dependencies
mcp_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc", "curl")
    .pip_install(
        # MCP server
        "mcp[cli]>=1.13.1",
        "fastmcp>=0.1.0",
        # Database
        "psycopg2-binary>=2.9.0",
        # Embeddings (for vector search)
        "fastembed>=0.3.0",
        "numpy<2",
        # HTTP/async
        "fastapi[standard]>=0.100.0",
        "httpx>=0.24.0",
        "uvicorn>=0.30.0",
        "starlette>=0.38.0",
        # Utils
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "pyyaml>=6.0.0",
        # LangGraph (for coordination workflows)
        "langgraph>=0.2.0",
        "langchain-core>=0.3.0",
        "langchain-anthropic>=0.3.0",
    )
    # Pre-download embedding model during image build
    .run_commands(
        "python -c \"from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')\""
    )
    # Add local packages
    .add_local_python_source("civicos")
    .add_local_python_source("civicos_config")
    .add_local_python_source("civicos_relay")
    # Add MCP server code
    .add_local_dir("apps/civicos-mcp", remote_path="/app/civicos-mcp")
    .add_local_file("apps/civicos_input_validator.py", remote_path="/app/civicos_input_validator.py")
)


@app.cls(
    image=mcp_image,
    secrets=[modal.Secret.from_name("civicos-california-env")],
    memory=4096,
    timeout=300,
    min_containers=0,  # Reference implementation - no min containers
)
@modal.concurrent(max_inputs=20)
class CaliforniaMCPServer:
    """California state-level MCP server (4 tools)."""

    @modal.enter()
    def initialize(self):
        """Initialize on container startup."""
        import os
        import sys
        import logging
        import time

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("civicos-mcp-california")

        # Add paths for imports
        sys.path.insert(0, "/app")
        sys.path.insert(0, "/app/civicos-mcp")

        self.logger.info("Initializing CivicOS California MCP Server on Modal...")

        # Import CivicOS and initialize
        from civicos import CivicOS
        from handlers.loader import load_jurisdiction_config

        self.jurisdiction = os.getenv("CIVICOS_JURISDICTION", "state-california")
        self.jurisdiction_config = load_jurisdiction_config(self.jurisdiction)

        self.logger.info(
            f"Jurisdiction: {self.jurisdiction_config.display_name} "
            f"(level: {self.jurisdiction_config.level})"
        )

        start = time.time()
        self.civic = CivicOS(self.jurisdiction)
        init_time = time.time() - start
        self.logger.info(
            f"CivicOS initialized for {self.jurisdiction} "
            f"(storage: {type(self.civic._storage).__name__}, {init_time:.1f}s)"
        )

        # Pre-warm embedding model
        if self.civic._vectors is not None:
            self.logger.info("Pre-warming embedding model...")
            start = time.time()
            provider = self.civic._vectors._embedding_provider
            _ = provider.encode(["warmup query"])
            warmup_time = time.time() - start
            self.logger.info(f"Embedding model ready ({provider.model_name}, {warmup_time:.1f}s)")

        # Import the input validator
        from civicos_input_validator import validate_civic_input
        self.validate_input = validate_civic_input

        # Import shared tool registry and handlers
        from tools.registry import ToolRegistry
        from tools import handlers

        # Create tool registry and bind handlers
        self.registry = ToolRegistry()
        self._bind_handlers(handlers)

        self.logger.info(
            f"MCP Server ready with {len(self.registry)} tools "
            f"(level: {self.jurisdiction_config.level})"
        )

    def _bind_handlers(self, handlers):
        """Bind handler functions for state-level tools."""
        enabled_tools = self.jurisdiction_config.get_enabled_tools()
        self.logger.info(f"Enabled tools for state level: {len(enabled_tools)}")

        handler_map = {
            "search_regulatory_stack": handlers.search_regulatory_stack,
            "get_funding_flow": handlers.get_funding_flow,
            "get_federal_expenditures": handlers.get_federal_expenditures,
            "get_intergovernmental_revenue": handlers.get_intergovernmental_revenue,
            "list_relays": handlers.list_relays,
        }

        for name, handler_fn in handler_map.items():
            if name in enabled_tools:
                try:
                    wrapped = self._wrap_handler(handler_fn)
                    self.registry.bind_handler(name, wrapped)
                except ValueError as e:
                    self.logger.warning(f"Could not bind handler {name}: {e}")

    def _wrap_handler(self, handler_fn):
        """Wrap a handler function to provide context."""
        def wrapped(args: dict) -> str:
            result = handler_fn(
                self.civic,
                self.jurisdiction,
                self.validate_input,
                self.logger,
                args,
            )
            if isinstance(result, dict):
                import json
                return json.dumps(result, indent=2, default=str)
            return result
        return wrapped

    @modal.fastapi_endpoint(method="POST", docs=True)
    def mcp_endpoint(self, request: dict) -> dict:
        """MCP JSON-RPC endpoint."""
        try:
            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id", 1)

            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": f"CivicOS California MCP Server",
                            "version": "1.0.0",
                        },
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"listChanged": False},
                        },
                    },
                    "id": request_id,
                }

            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "result": {"tools": self.registry.list_tools()},
                    "id": request_id,
                }

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})

                try:
                    result = self.registry.call_tool(tool_name, tool_args)
                except ValueError as e:
                    return {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": str(e)},
                        "id": request_id,
                    }

                if isinstance(result, dict):
                    import json
                    result_text = json.dumps(result, indent=2, default=str)
                elif isinstance(result, list):
                    result_text = "\n\n".join(str(item) for item in result[:20])
                else:
                    result_text = str(result)

                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
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
            self.logger.error(f"MCP endpoint error: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e),
                    "data": traceback.format_exc(),
                },
                "id": request.get("id", 1),
            }

    @modal.fastapi_endpoint(method="GET", docs=True)
    def health(self) -> dict:
        """Health check endpoint."""
        bound_tools = [t["name"] for t in self.registry.list_tools()]
        return {
            "status": "healthy",
            "service": "civicos-mcp-california",
            "jurisdiction": self.jurisdiction,
            "jurisdiction_level": self.jurisdiction_config.level,
            "display_name": self.jurisdiction_config.display_name,
            "platform": "modal",
            "tools_count": len(bound_tools),
            "tools": bound_tools,
        }


@app.local_entrypoint()
def main():
    """Local entrypoint."""
    print("CivicOS California MCP Server")
    print()
    print("Tools: get_federal_expenditures, get_funding_flow,")
    print("       get_intergovernmental_revenue, search_regulatory_stack")
    print()
    print("Deploy: modal deploy apps/civicos-mcp/modal_california.py")
    print("Endpoint: california.civicosproject.org/mcp")
