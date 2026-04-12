"""
Unified Modal deployment for CivicOS MCP Servers.

Single parameterized deployment that works for any jurisdiction level
(federal, state, county, city, region). The jurisdiction is determined
by environment variable, allowing the same code to deploy multiple servers.

Usage:
    # Deploy San Rafael (city) - default
    modal deploy apps/civicos-mcp/modal_mcp.py

    # Deploy Marin regional server
    CIVICOS_JURISDICTION=region-marin modal deploy apps/civicos-mcp/modal_mcp.py

    # Deploy Federal
    CIVICOS_JURISDICTION=country-united-states modal deploy apps/civicos-mcp/modal_mcp.py

    # Deploy California
    CIVICOS_JURISDICTION=state-california modal deploy apps/civicos-mcp/modal_mcp.py

    # Deploy any jurisdiction
    CIVICOS_JURISDICTION=city-berkeley modal deploy apps/civicos-mcp/modal_mcp.py

Naming convention:
    Jurisdiction: city-san-rafael -> App: civicos-san-rafael
    Jurisdiction: region-marin   -> App: civicos-marin
    Jurisdiction: state-california -> App: civicos-california
    Jurisdiction: country-united-states -> App: civicos-federal

Endpoints (via Cloudflare proxy):
    san-rafael.civicosproject.org/mcp
    marin.civicosproject.org/mcp
    california.civicosproject.org/mcp
    federal.civicosproject.org/mcp
"""

import logging
import os
import modal

# ─────────── JURISDICTION CONFIGURATION ───────────

# Get jurisdiction from environment (set before `modal deploy`)
JURISDICTION = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")

# URL and app name resolution uses civicos.registry (loaded from config/registry.json)
from civicos.registry import get_modal_app_name as get_app_name, get_deployment_config

def get_secrets(jurisdiction: str) -> list[str]:
    """Get list of Modal secret names for this jurisdiction.

    Order matters: Modal merges env vars left-to-right, so later secrets
    override earlier ones for the same key.  The primary jurisdiction secret
    is loaded LAST so its DATABASE_URL always wins.

    Secret selection is config-driven: ``modal_secret`` in each
    jurisdiction's ``config/registry.json`` entry overrides the default
    ``civicos-env``. Geocoding secrets are added for any jurisdiction
    below state level (cities, counties, regions, schools).
    """
    config = get_deployment_config(jurisdiction)
    secrets = []

    # Shared secrets first (lower precedence)
    secrets.append("civicos-attestation")  # CIVICOS_ATTESTATION_PRIVATE_KEY
    secrets.append("civicos-platform")  # PLATFORM_DATABASE_URL

    # Geocoding secret for jurisdictions with geographic data.
    # Federal and state levels don't need address geocoding;
    # everything else (city, county, region, school) does.
    if not jurisdiction.startswith(("country-", "state-")):
        secrets.append("civic-google")  # GOOGLE_MAPS_API_KEY for geocoding

    # Primary secret LAST so its DATABASE_URL takes precedence.
    # Reads modal_secret from registry entry (default: civicos-env).
    secrets.append(config["modal_secret"])

    return secrets

def get_min_containers(jurisdiction: str) -> int:
    """Containers to keep warm — reads min_containers from registry (default: 0)."""
    return get_deployment_config(jurisdiction)["min_containers"]

APP_NAME = get_app_name(JURISDICTION)
SECRETS = get_secrets(JURISDICTION)
MIN_CONTAINERS = get_min_containers(JURISDICTION)

# ─────────── MODAL APP DEFINITION ───────────

app = modal.App(APP_NAME)

# Build image with all MCP dependencies
mcp_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc", "curl")
    .pip_install(
        # MCP server
        "mcp[cli]>=1.13.1",
        "fastmcp>=3.1.0",
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
        # Form parsing for OAuth endpoints (/authorize, /token)
        "python-multipart>=0.0.6",
        # Crypto (BIP-340 Schnorr signature verification)
        "coincurve>=21.0.0",
        # Utils
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "pyyaml>=6.0.0",
        # Extraction dependencies (for civicos_extraction)
        "beautifulsoup4>=4.12.0",
        "google-api-python-client>=2.0.0",
    )
    # Pre-download embedding model during image build
    .run_commands(
        "python -c \"from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')\""
    )
    # Environment variables for civicos_config.paths (avoid phase.json lookup)
    .env({
        "CIVICOS_EXTRACTION_DIR": "/app/data/extraction",
        "CIVICOS_CONFIG_DIR": "/app/data/extraction",
        "CIVICOS_JURISDICTIONS_DIR": "/app/data/jurisdictions",
    })
    # Add local packages
    .add_local_python_source("civicos")
    .add_local_python_source("civicos_config")
    .add_local_python_source("civicos_relay")
    .add_local_python_source("civicos_extraction")
    .add_local_python_source("civicos_services")
    # Add data directories (needed by civicos_config.paths)
    .add_local_dir("data/extraction", remote_path="/app/data/extraction")
    .add_local_dir("data/jurisdictions", remote_path="/app/data/jurisdictions")
    # Add MCP server code
    .add_local_dir("apps/civicos-mcp", remote_path="/app/civicos-mcp")
    .add_local_file("apps/civicos_input_validator.py", remote_path="/app/civicos_input_validator.py")
    # Service registry (URL config)
    .add_local_file("config/registry.json", remote_path="/app/registry.json")
    # Jurisdiction rosters (speaker resolution)
    .add_local_dir("config/rosters", remote_path="/app/config/rosters")
)


# ─────────── MCP SERVER CLASS ───────────

import contextvars
# Tier context for MCP Streamable HTTP requests (set by BearerAuthMiddleware)
_mcp_request_tier: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_mcp_request_tier", default="open"
)
# Key ID context for usage logging (set by BearerAuthMiddleware)
_mcp_request_key_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_mcp_request_key_id", default=None
)
# Resolved scope context for the in-flight tool call. Declared in
# tools/scope.py so that both the producer (this module's
# _wrap_handler) and the consumers (tools/handlers.py) can share a
# single binding without importing each other. Re-exported here for
# backwards compatibility with any external caller that imported it
# from modal_mcp before the move.
from tools.scope import _mcp_request_scope  # noqa: E402

@app.cls(
    image=mcp_image,
    secrets=[modal.Secret.from_name(s) for s in SECRETS],
    memory=4096,
    timeout=300,
    min_containers=MIN_CONTAINERS,
)
@modal.concurrent(max_inputs=20)
class MCPServer:
    """
    Unified MCP server for any jurisdiction level.

    The jurisdiction is determined by CIVICOS_JURISDICTION environment variable
    in the Modal secret. Tool availability is automatically filtered based on
    the jurisdiction level (federal, state, city).
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
        self.logger = logging.getLogger("civicos-mcp")

        # Add paths for imports
        sys.path.insert(0, "/app")
        sys.path.insert(0, "/app/civicos-mcp")

        self.logger.info("Initializing CivicOS MCP Server on Modal...")

        # Import CivicOS and initialize
        from civicos import CivicOS
        from handlers.loader import load_jurisdiction_config, get_tools_for_level

        # Get jurisdiction from environment (set in Modal secret)
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
            f"(storage: {type(self.civic.storage).__name__}, {init_time:.1f}s)"
        )

        # Pre-warm embedding model
        if self.civic.vectors is not None:
            self.logger.info("Pre-warming embedding model...")
            start = time.time()
            provider = self.civic.vectors._embedding_provider
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
        """Bind handler functions based on jurisdiction level."""
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

        # Complete handler map - all tools across all levels
        handler_map = {
            # Core Civic Tools (city level)
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
            # 311 Analysis Tools (city level)
            "query_issue_data": handlers.query_issue_data,
            "get_issue_resolution_stats": handlers.get_issue_resolution_stats,
            "detect_trends": handlers.detect_trends,
            "get_issue_sample": handlers.get_issue_sample,
            "find_issues_near_address": handlers.find_issues_near_address,
            "find_repeat_issues": handlers.find_repeat_issues,
            "get_seasonal_patterns": handlers.get_seasonal_patterns,
            "compare_zip_codes": handlers.compare_zip_codes,
            "neighborhood_report": handlers.neighborhood_report,
            # Council/Voting Tools (city level)
            "get_voting_record": handlers.get_voting_record,
            "get_congressional_votes": handlers.get_congressional_votes,
            "get_decision_context": handlers.get_decision_context,
            "decision_detail": handlers.decision_detail,
            # Legislation & Executive Order Tools (federal/state/city)
            "search_legislation": handlers.search_legislation,
            "get_bill_detail": handlers.get_bill_detail,
            "get_leverage_points": handlers.get_leverage_points,
            "search_executive_orders": handlers.search_executive_orders,
            "get_recent_executive_orders": handlers.get_recent_executive_orders,
            "get_open_comment_periods": handlers.get_open_comment_periods,
            "search_federal_rules": handlers.search_federal_rules,
            "get_congressional_hearings": handlers.get_congressional_hearings,
            # Financial Tools (federal/state/city)
            "get_funding_flow": handlers.get_funding_flow,
            "get_federal_expenditures": handlers.get_federal_expenditures,
            "get_intergovernmental_revenue": handlers.get_intergovernmental_revenue,
            # Action Tools (city level)
            "get_comment_template": config_driven["get_comment_template"],
            "prepare_for_meeting": handlers.prepare_for_meeting,
            "draft_federal_comment": handlers.draft_federal_comment,
            "prepare_federal_comment": handlers.prepare_federal_comment,
            # Coordination Tools (city level)
            "get_voice_counts": handlers.get_voice_counts,
            "subscribe_to_topic": handlers.subscribe_to_topic,
            "prepare_voice": handlers.prepare_voice,
            "broadcast_voice": handlers.broadcast_voice,
            "list_relays": handlers.list_relays,
            # Initiative Tools (city level)
            "prepare_initiative": handlers.prepare_initiative,
            "broadcast_initiative": handlers.broadcast_initiative,
            "list_initiatives": handlers.list_initiatives,
            # Context Assembly (city level)
            "get_item_context": handlers.get_item_context,
            # Admin Tools (all levels)
            "admin_data_status": handlers.admin_data_status,
            "admin_vector_coverage": handlers.admin_vector_coverage,
            "admin_system_health": handlers.admin_system_health,
            "admin_cost_dashboard": handlers.admin_cost_dashboard,
            "manage_api_keys": handlers.manage_api_keys,
            "query_feedback": handlers.query_feedback,
        }

        # Verify every tool in handler_map declares a scope policy BEFORE
        # binding. This is a hard failure at startup: a tool that reaches
        # _bind_handlers without a row in tools/scope.py is a correctness
        # hole (the wrapper below will KeyError at call time). See
        # docs/public/decisions/tool_scope_and_federation.md for the
        # authoritative policy table.
        from tools.scope import SCOPE_POLICIES
        missing_scope = [name for name in handler_map if name not in SCOPE_POLICIES]
        if missing_scope:
            raise RuntimeError(
                "Tools bound without a scope policy: "
                f"{sorted(missing_scope)}. Add rows to "
                "apps/civicos-mcp/tools/scope.py and the ADR at "
                "docs/public/decisions/tool_scope_and_federation.md."
            )

        # Only bind handlers for tools enabled at this jurisdiction level
        for name, handler_fn in handler_map.items():
            if name in enabled_tools:
                try:
                    wrapped = self._wrap_handler(handler_fn, tool_name=name)
                    self.registry.bind_handler(name, wrapped)
                except ValueError as e:
                    self.logger.warning(f"Could not bind handler {name}: {e}")

    def _wrap_handler(self, handler_fn, tool_name=None):
        """Wrap a handler function to provide context, admin auth, and tier enforcement."""
        def wrapped(args: dict) -> str:
            import json

            # Admin auth check (unchanged — admin tools use _admin_token)
            if tool_name:
                from tools.registry import TOOL_DEFINITIONS
                tool_def = TOOL_DEFINITIONS.get(tool_name, {})
                if tool_def.get("requires_admin"):
                    admin_token = args.pop("_admin_token", None)
                    expected = os.getenv("CIVICOS_ADMIN_TOKEN")
                    if not expected or admin_token != expected:
                        return json.dumps({"error": "Unauthorized"})

            # Tier-based access check for MCP Streamable HTTP requests
            if tool_name:
                from civicos_services.core.api_keys import get_allowed_tools, min_tier_for_tool
                tier = _mcp_request_tier.get("open")
                allowed = get_allowed_tools(tier)
                if tool_name not in allowed:
                    required = min_tier_for_tool(tool_name)
                    return json.dumps({
                        "error": f"Tool '{tool_name}' requires '{required}' tier (current: '{tier}'). "
                                 f"Pass Authorization: Bearer <api-key> or register at POST /api/register"
                    })

            # Per-session rate limiting for OAuth free tier
            key_id = _mcp_request_key_id.get(None)
            if key_id and key_id.startswith("oauth:"):
                from api_key_middleware import (
                    check_oauth_rate_limit, OAUTH_DAILY_QUOTA, OAUTH_PER_MINUTE,
                )
                rl = check_oauth_rate_limit(key_id)
                if not rl["allowed"]:
                    if rl["error"] == "daily_quota_exceeded":
                        msg = (
                            f"Daily query limit reached ({OAUTH_DAILY_QUOTA}/day). "
                            f"Resets at midnight UTC. "
                            f"For higher limits, register for an API key at POST /api/register."
                        )
                    else:
                        msg = (
                            f"Too many requests ({OAUTH_PER_MINUTE}/min). "
                            f"Please wait before retrying."
                        )
                    return json.dumps({
                        "error": rl["error"],
                        "message": msg,
                        "retry_after": rl["retry_after"],
                    })

            # Publish the resolved scope policy on the request contextvar so
            # downstream code (the v2 API call path, result formatting) can
            # observe it without plumbing an explicit argument. The binding
            # assertion above guarantees this lookup never raises for a bound
            # tool. Passive in this P0; consumed in scope_policy_passthrough.
            if tool_name:
                from tools.scope import get_scope_policy
                _mcp_request_scope.set(get_scope_policy(tool_name))

            result = handler_fn(
                self.civic,
                self.jurisdiction,
                self.validate_input,
                self.logger,
                args,
            )
            if isinstance(result, dict):
                return json.dumps(result, indent=2, default=str)
            return result
        return wrapped

    # ─────────── FastAPI App for all endpoints ───────────

    @modal.asgi_app()
    def mcp_endpoint(self):  # noqa: C901
        """
        Full FastAPI app with MCP and REST endpoints.

        Endpoints:
        - /mcp : MCP Streamable HTTP endpoint (for Claude.ai, ChatGPT)
        - GET /health : Health check
        - /api/tools/* : REST endpoints (for Open WebUI OpenAPI mode)
        """
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastmcp_bridge import create_fastmcp_server

        # Build the server URL for OpenAPI spec (stable Cloudflare domain)
        from civicos.registry import get_jurisdiction_url
        server_url = get_jurisdiction_url(self.jurisdiction)

        # MCP tools are public (no auth required for basic access).
        # OAuth provides optional free-tier auth for Claude.ai Connectors.
        # API keys (cvk_live_*) provide tiered access for registered users.
        mcp = create_fastmcp_server(self.registry, self.jurisdiction_config)
        mcp_app = mcp.http_app(path="/", transport="streamable-http", stateless_http=True)

        app = FastAPI(
            title=f"CivicOS MCP Server ({self.jurisdiction_config.display_name})",
            description="Civic data API for AI assistants. Supports both MCP (Streamable HTTP) and REST endpoints.",
            version="1.0.0",
            servers=[
                {"url": server_url, "description": "Modal deployment"},
            ],
            lifespan=mcp_app.lifespan,
        )

        # Set jurisdiction on app state for middleware access
        app.state.jurisdiction = self.jurisdiction

        # Raw ASGI middleware definitions
        from starlette.types import ASGIApp, Receive, Scope, Send
        import time as _time
        import asyncio as _asyncio

        # Usage logging middleware — fire-and-forget, never blocks responses
        _usage_jurisdiction = self.jurisdiction  # capture for closure

        class UsageLoggingMiddleware:
            """Log API usage to Platform DB. Captures status code from response headers."""
            SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

            def __init__(self, app: ASGIApp):
                self.app = app

            async def __call__(self, scope: Scope, receive: Receive, send: Send):
                if scope["type"] != "http":
                    await self.app(scope, receive, send)
                    return

                path = scope.get("path", "")
                if path in self.SKIP_PATHS:
                    await self.app(scope, receive, send)
                    return

                start = _time.time()
                status_code = None
                key_id = None

                async def send_wrapper(message):
                    nonlocal status_code, key_id
                    if message["type"] == "http.response.start":
                        status_code = message.get("status")
                        # Capture key_id now, while BearerAuth context is still active
                        key_id = _mcp_request_key_id.get(None)
                    await send(message)

                await self.app(scope, receive, send_wrapper)

                duration_ms = int((_time.time() - start) * 1000)
                method = scope.get("method", "GET")

                # Fire-and-forget usage log
                try:
                    from civicos_services.core.api_keys import get_api_key_store
                    store = get_api_key_store()
                    if store and store.available:
                        _asyncio.get_event_loop().run_in_executor(
                            None,
                            store.log_usage,
                            key_id,
                            path,
                            method,
                            status_code,
                            duration_ms,
                            _usage_jurisdiction,
                        )
                except Exception as e:
                    logging.getLogger("civicos-mcp").debug("Usage logging failed: %s", e)

        # Rewrite /mcp → /mcp/ internally to avoid Starlette's 307 redirect.
        # Without this, Cloudflare proxy gets a 307 pointing at Modal's host
        # (not the Cloudflare domain), causing error 1101.
        # Uses raw ASGI middleware (not BaseHTTPMiddleware) to avoid scope issues.

        class TrailingSlashMiddleware:
            def __init__(self, app: ASGIApp):
                self.app = app
            async def __call__(self, scope: Scope, receive: Receive, send: Send):
                if scope["type"] == "http" and scope.get("path") == "/mcp":
                    scope = dict(scope)
                    scope["path"] = "/mcp/"
                await self.app(scope, receive, send)

        app.add_middleware(TrailingSlashMiddleware)

        # Bearer auth middleware for MCP Streamable HTTP requests.
        #
        # Returns 401 + RFC 6750 WWW-Authenticate on /mcp/* when:
        #   (a) no Authorization header (forces Claude.ai to discover OAuth
        #       via resource_metadata, otherwise the connector UI treats
        #       OAuth as optional and shows manual fallback fields); or
        #   (b) a recognizable-but-invalid cos_* OAuth token (stale/expired
        #       — tells the client to re-run OAuth rather than silently
        #       downgrading to the 'open' tier).
        #
        # Supports both API keys (cvk_live_*) and OAuth tokens (cos_*) as
        # valid credentials. Non-/mcp/* paths (health, OAuth endpoints,
        # REST API) are unaffected — they always proceed without auth.
        #
        # resource_metadata in the WWW-Authenticate challenge uses the
        # static server_url from registry.json rather than the Host
        # header, because Cloudflare Workers proxying via fetch() set
        # Host to the Modal internal URL.
        _oauth_challenge = (
            'Bearer realm="mcp", '
            'resource_metadata="{0}/.well-known/oauth-protected-resource"'
        ).format(server_url)

        async def _send_401(send: Send, *, error: str, description: str):
            challenge = (
                f'{_oauth_challenge}, error="{error}", '
                f'error_description="{description}"'
            )
            body = (
                f'{{"error":"{error}","error_description":"{description}"}}'
            ).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", challenge.encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})

        class BearerAuthMiddleware:
            def __init__(self, app: ASGIApp):
                self.app = app
            async def __call__(self, scope: Scope, receive: Receive, send: Send):
                if scope["type"] != "http":
                    await self.app(scope, receive, send)
                    return

                path = scope.get("path", "")
                is_mcp_path = path.startswith("/mcp")
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode()

                if auth.startswith("Bearer "):
                    raw_token = auth[7:].strip()

                    # API key authentication (cvk_live_*)
                    if raw_token.startswith("cvk_live_"):
                        from civicos_services.core.api_keys import get_api_key_store, resolve_tier
                        store = get_api_key_store()
                        if store and store.available:
                            key_info = store.validate_key(raw_token)
                            if key_info:
                                tier_token = _mcp_request_tier.set(resolve_tier(key_info.tier))
                                key_token = _mcp_request_key_id.set(key_info.key_id)
                                try:
                                    await self.app(scope, receive, send)
                                finally:
                                    _mcp_request_tier.reset(tier_token)
                                    _mcp_request_key_id.reset(key_token)
                                return
                        # Invalid API key — fall through. cvk_live_* keys
                        # are used by Open WebUI and other non-MCP clients;
                        # we don't 401 them here to preserve existing behavior.

                    # OAuth token authentication (cos_*)
                    elif raw_token.startswith("cos_"):
                        from oauth import verify_oauth_token
                        token_info = verify_oauth_token(raw_token)
                        if token_info:
                            tier_token = _mcp_request_tier.set("free")
                            key_token = _mcp_request_key_id.set(
                                f"oauth:{token_info['client_id']}"
                            )
                            try:
                                await self.app(scope, receive, send)
                            finally:
                                _mcp_request_tier.reset(tier_token)
                                _mcp_request_key_id.reset(key_token)
                            return

                        # Invalid/stale OAuth token on /mcp/* → 401 to
                        # trigger re-auth in the MCP client.
                        if is_mcp_path:
                            await _send_401(
                                send,
                                error="invalid_token",
                                description="OAuth access token is invalid or expired",
                            )
                            return

                # No Authorization header (or Bearer with unrecognized prefix).
                # On /mcp/* paths, force the OAuth discovery flow by
                # returning 401. Claude.ai's connector UI relies on this
                # to find the protected-resource metadata and auto-run DCR.
                # Non-MCP paths (health, REST API, OAuth endpoints) stay
                # unauthenticated as before.
                if is_mcp_path:
                    await _send_401(
                        send,
                        error="unauthorized",
                        description="Authentication required for MCP endpoint",
                    )
                    return

                await self.app(scope, receive, send)

        app.add_middleware(BearerAuthMiddleware)

        # CORS for Open WebUI and other clients
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Usage logging — outermost middleware, runs after auth sets key_id context
        # Middleware chain (outermost→innermost):
        #   UsageLogging → CORS → BearerAuth → TrailingSlash → route handler
        app.add_middleware(UsageLoggingMiddleware)

        # Mount OAuth router (/.well-known/*, /authorize, /token, /register)
        from oauth import create_oauth_router
        oauth_router = create_oauth_router(
            server_url=server_url,
            display_name=self.jurisdiction_config.display_name,
        )
        app.include_router(oauth_router)

        # Mount REST API router
        from rest_api import create_rest_router, create_keys_router, create_register_router
        rest_router = create_rest_router(
            self.registry,
            self.civic,
            self.jurisdiction,
            self.validate_input,
            self.logger
        )
        app.include_router(rest_router)

        # Mount API key provisioning routers
        keys_router = create_keys_router(self.logger)
        app.include_router(keys_router)

        # POST /api/register alias (spec-referenced path)
        register_router = create_register_router(self.logger)
        app.include_router(register_router)

        # Mount v2 query interface
        try:
            from civicos_services.query import create_v2_router
            v2_router = create_v2_router(
                self.civic, self.jurisdiction,
                registry=self.registry, logger_override=self.logger,
            )
            app.include_router(v2_router)
            self.logger.info("v2 query interface mounted at /api/v2/civic/")
        except Exception as e:
            self.logger.warning(f"Could not mount v2 query interface: {e}")

        # FastMCP Streamable HTTP at /mcp
        app.mount("/mcp", mcp_app, name="mcp")

        # Health endpoint
        @app.get("/health", tags=["Health"])
        async def health() -> dict:
            return self._health_response()

        return app

    def _health_response(self) -> dict:
        """Generate health check response."""
        bound_tools = [t["name"] for t in self.registry.list_tools()]
        return {
            "status": "healthy",
            "service": "civicos-mcp",
            "jurisdiction": self.jurisdiction,
            "jurisdiction_level": self.jurisdiction_config.level,
            "display_name": self.jurisdiction_config.display_name,
            "platform": "modal",
            "tools_count": len(bound_tools),
            "tools": bound_tools,
            "auth": "oauth2_or_api_key",
            "endpoints": {
                "mcp": "/mcp/",
                "health": "GET /health",
                "rest_api": "/api/tools/*",
                "create_key": "POST /api/keys/",
                "register": "POST /api/register",
                "openapi_spec": "/openapi.json",
                "oauth_metadata": "GET /.well-known/oauth-authorization-server",
                "oauth_authorize": "GET /authorize",
                "oauth_token": "POST /token",
                "oauth_register": "POST /register",
            }
        }


# ─────────── LOCAL ENTRYPOINT ───────────

@app.local_entrypoint()
def main():
    """Local entrypoint showing deployment info."""
    print(f"CivicOS MCP Server - Unified Deployment")
    print()
    print(f"Current configuration:")
    print(f"  Jurisdiction: {JURISDICTION}")
    print(f"  App name:     {APP_NAME}")
    print(f"  Secrets:      {', '.join(SECRETS)}")
    print(f"  Min containers: {MIN_CONTAINERS}")
    print()
    print("Deploy commands:")
    print("  # San Rafael (default)")
    print("  modal deploy apps/civicos-mcp/modal_mcp.py")
    print()
    print("  # Federal")
    print("  CIVICOS_JURISDICTION=country-united-states modal deploy apps/civicos-mcp/modal_mcp.py")
    print()
    print("  # California")
    print("  CIVICOS_JURISDICTION=state-california modal deploy apps/civicos-mcp/modal_mcp.py")
    print()
    print("  # Any other jurisdiction")
    print("  CIVICOS_JURISDICTION=city-berkeley modal deploy apps/civicos-mcp/modal_mcp.py")
