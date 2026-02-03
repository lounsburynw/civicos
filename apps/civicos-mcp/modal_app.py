"""
Modal deployment for CivicOS MCP Server.

Deploys the complete MCP server (30 tools) as a serverless web endpoint on Modal,
proxied through Cloudflare for the production domain.

Production URL:
    https://san-rafael.civicosproject.org/mcp

Architecture:
    Claude.ai/ChatGPT -> Cloudflare Worker -> Modal -> Supabase

Key features:
    - Serverless scaling (0 to N instances based on traffic)
    - min_containers=1 prevents cold starts
    - Same platform as relay worker and vector indexer (consolidation)
    - Cloudflare proxy provides custom domain without Modal Team plan

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal token new
    3. Create secret with required env vars:
       modal secret create civicos-env \
           DATABASE_URL="postgresql://..." \
           RELAY_DATABASE_URL="postgresql://..." \
           CIVICOS_JURISDICTION="city-san-rafael"
    4. Deploy: modal deploy apps/civicos-mcp/modal_app.py

Usage:
    # Local testing
    modal serve apps/civicos-mcp/modal_app.py

    # Deploy to production
    modal deploy apps/civicos-mcp/modal_app.py

Endpoints:
    Production: https://san-rafael.civicosproject.org/mcp
    Health:     https://san-rafael.civicosproject.org/health
    Modal direct: https://lounsburynw--civicos-mcp-mcpserver-mcp-endpoint.modal.run
"""

import modal

# ─────────── MODAL APP DEFINITION ───────────

app = modal.App("civicos-mcp")

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


# ─────────── MCP SERVER CLASS ───────────

@app.cls(
    image=mcp_image,
    secrets=[modal.Secret.from_name("civicos-env")],
    memory=4096,
    timeout=300,
    min_containers=1,
)
@modal.concurrent(max_inputs=20)
class MCPServer:
    """
    Modal-deployed MCP server using shared tool definitions.

    Tools are defined in tools/registry.py and handlers in tools/handlers.py.
    This class just provides the Modal infrastructure and binds handlers.

    Supports jurisdiction-specific deployments via CIVICOS_JURISDICTION env var.
    Each jurisdiction level (federal, state, city) gets different tools.
    """

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
        self.logger = logging.getLogger("civicos-mcp-modal")

        # Add paths for imports
        sys.path.insert(0, "/app")
        sys.path.insert(0, "/app/civicos-mcp")

        self.logger.info("Initializing CivicOS MCP Server on Modal...")

        # Import CivicOS and initialize
        from civicos import CivicOS

        # Load jurisdiction config
        from handlers.loader import load_jurisdiction_config

        self.jurisdiction = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")
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
        """Bind handler functions from the shared handlers module."""
        # Import config-driven handlers for engagement tools
        from handlers.jurisdiction import engagement as config_handlers

        # Get enabled tools for this jurisdiction level
        enabled_tools = self.jurisdiction_config.get_enabled_tools()
        self.logger.info(f"Enabled tools for {self.jurisdiction_config.level} level: {len(enabled_tools)}")

        # Map tools to handlers (with config-driven replacements where available)
        config_driven = {
            "compose_public_comment": config_handlers.compose_public_comment,
            "get_comment_guidelines": config_handlers.get_comment_guidelines,
            "get_comment_template": config_handlers.get_comment_template,
        }

        handler_map = {
            # Core Civic Tools
            "search_meeting_history": handlers.search_meeting_history,
            "get_upcoming_meetings": handlers.get_upcoming_meetings,
            "find_similar_issues": handlers.find_similar_issues,
            "search_regulatory_stack": handlers.search_regulatory_stack,
            "compose_public_comment": config_driven["compose_public_comment"],
            "city_pulse": handlers.city_pulse,
            "get_issue_analytics": handlers.get_issue_analytics,
            "get_issue_trends": handlers.get_issue_trends,
            "geo_search_issues": handlers.geo_search_issues,
            "search_budget": handlers.search_budget,
            "get_public_testimony": handlers.get_public_testimony,
            "search_agenda_packets": handlers.search_agenda_packets,
            "get_comment_guidelines": config_driven["get_comment_guidelines"],
            "get_started": handlers.get_started,
            # 311 Analysis Tools
            "query_issue_data": handlers.query_issue_data,
            "get_issue_resolution_stats": handlers.get_issue_resolution_stats,
            "detect_trends": handlers.detect_trends,
            "get_issue_sample": handlers.get_issue_sample,
            "find_issues_near_address": handlers.find_issues_near_address,
            "find_repeat_issues": handlers.find_repeat_issues,
            "get_seasonal_patterns": handlers.get_seasonal_patterns,
            "compare_zip_codes": handlers.compare_zip_codes,
            "neighborhood_report": handlers.neighborhood_report,
            # Council/Voting Tools
            "get_voting_record": handlers.get_voting_record,
            "get_decision_context": handlers.get_decision_context,
            # Financial Tools
            "get_funding_flow": handlers.get_funding_flow,
            "get_federal_expenditures": handlers.get_federal_expenditures,
            "get_intergovernmental_revenue": handlers.get_intergovernmental_revenue,
            # Action Tools
            "get_comment_template": config_driven["get_comment_template"],
            "prepare_for_meeting": handlers.prepare_for_meeting,
            # Coordination Tools
            "get_voice_counts": handlers.get_voice_counts,
            "subscribe_to_topic": handlers.subscribe_to_topic,
            "prepare_voice": handlers.prepare_voice,
            "broadcast_voice": handlers.broadcast_voice,
            "list_relays": handlers.list_relays,
            # Initiative Tools
            "prepare_initiative": handlers.prepare_initiative,
            "broadcast_initiative": handlers.broadcast_initiative,
            "list_initiatives": handlers.list_initiatives,
        }

        # Only bind handlers for tools enabled at this jurisdiction level
        bound_count = 0
        for name, handler_fn in handler_map.items():
            if name in enabled_tools:
                try:
                    wrapped = self._wrap_handler(handler_fn)
                    self.registry.bind_handler(name, wrapped)
                    bound_count += 1
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
            # Convert dict results to string for MCP
            if isinstance(result, dict):
                import json
                return json.dumps(result, indent=2, default=str)
            return result
        return wrapped

    # ─────────── MCP Protocol Handler ───────────

    @modal.fastapi_endpoint(method="POST", docs=True)
    def mcp_endpoint(self, request: dict) -> dict:
        """MCP JSON-RPC endpoint for Claude.ai and ChatGPT."""
        try:
            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id", 1)

            self.logger.debug(f"MCP request: {method}")

            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "CivicOS MCP Server",
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

                # Format result for MCP
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

            elif method == "resources/list":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "resources": [
                            {
                                "uri": f"civicos://{self.jurisdiction}/meetings",
                                "name": "Upcoming Meetings",
                                "description": "City council meetings and agendas",
                            },
                            {
                                "uri": f"civicos://{self.jurisdiction}/decisions",
                                "name": "Recent Decisions",
                                "description": "Recent council decisions and outcomes",
                            },
                        ]
                    },
                    "id": request_id,
                }

            elif method == "prompts/list":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "prompts": [
                            {
                                "name": "research_topic",
                                "description": "Research a civic topic thoroughly",
                                "arguments": [
                                    {"name": "topic", "description": "The topic to research", "required": True}
                                ],
                            },
                            {
                                "name": "meeting_prep",
                                "description": "Prepare for an upcoming council meeting",
                                "arguments": [
                                    {"name": "meeting_description", "description": "Meeting or agenda item", "required": True}
                                ],
                            },
                        ]
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
        return {
            "status": "healthy",
            "service": "civicos-mcp",
            "jurisdiction": self.jurisdiction,
            "jurisdiction_level": self.jurisdiction_config.level,
            "display_name": self.jurisdiction_config.display_name,
            "platform": "modal",
            "tools_count": len(self.registry),
            "tools": [name for name, _ in self.registry],
        }


# ─────────── LOCAL ENTRYPOINT ───────────

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
    print("After deployment, endpoints will be available at:")
    print("  MCP:    https://san-rafael.civicosproject.org/mcp")
    print("  Health: https://san-rafael.civicosproject.org/health")
