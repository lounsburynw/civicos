"""
Modal deployment for CivicOS Coordination Relay.

Hosts the coordination endpoints (voice, subscriptions, initiatives, sync)
and AI proxy endpoints (draft, chat) as a publicly reachable service.

Usage:
    modal deploy apps/civicos-relay/modal_relay.py
    curl https://civicos--civicos-relay-relayserver-relay-endpoint.modal.run/health
"""

import modal

app = modal.App("civicos-relay")

relay_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "fastapi[standard]>=0.100.0",
        "uvicorn>=0.30.0",
        "pydantic>=2.0.0",
        "coincurve>=18.0.0",
        "cryptography>=41.0.0",
        "python-dotenv>=1.0.0",
        # AI proxy dependencies
        "anthropic>=0.39.0",
        "httpx>=0.24.0",
    )
    .add_local_python_source("civicos_relay")
    # The coordination router lives in civicos_services but has zero
    # internal civicos_services imports — it only needs civicos_relay,
    # fastapi, and pydantic. We mount the single file directly.
    .add_local_file(
        "packages/civicos-services/src/civicos_services/servers/routers/coordination.py",
        remote_path="/app/coordination.py",
    )
    # AI proxy router — same pattern: self-contained, only needs
    # civicos_relay (for crypto), anthropic, httpx, fastapi, pydantic.
    .add_local_file(
        "packages/civicos-services/src/civicos_services/servers/routers/ai_proxy.py",
        remote_path="/app/ai_proxy.py",
    )
    # Registry config — jurisdiction → MCP endpoint mapping
    .add_local_file(
        "config/registry.json",
        remote_path="/app/registry.json",
    )
    # API key store — usage logging only (no key validation on relay).
    # Self-contained: only depends on psycopg2 (already in image).
    .add_local_file(
        "packages/civicos-services/src/civicos_services/core/api_keys.py",
        remote_path="/app/api_keys.py",
    )
)


@app.cls(
    image=relay_image,
    secrets=[
        modal.Secret.from_name("civicos-env"),
        modal.Secret.from_name("civicos-attestation"),
        modal.Secret.from_name("civic-anthropic"),
        modal.Secret.from_name("civicos-platform"),  # PLATFORM_DATABASE_URL for usage logging
    ],
    timeout=300,
    min_containers=0,
)
@modal.concurrent(max_inputs=20)
class RelayServer:
    @modal.enter()
    def initialize(self):
        import sys
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger("civicos-relay")

        # Make the mounted modules importable
        sys.path.insert(0, "/app")

        self.logger.info("CivicOS Relay initializing on Modal...")

        # Verify relay DB is configured
        import os
        relay_url = os.environ.get("RELAY_DATABASE_URL")
        if relay_url:
            self.logger.info("RELAY_DATABASE_URL configured")
        else:
            self.logger.warning("RELAY_DATABASE_URL not set — coordination endpoints will return 503")

        # Verify MCP URL for AI proxy tool calls
        mcp_url = os.environ.get("CIVICOS_MCP_URL")
        if mcp_url:
            self.logger.info("CIVICOS_MCP_URL configured: %s", mcp_url)
        else:
            self.logger.warning("CIVICOS_MCP_URL not set — /ai/chat will return 503")

    @modal.asgi_app()
    def relay_endpoint(self):
        import os
        import time as _time
        import asyncio as _asyncio
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.types import ASGIApp, Receive, Scope, Send

        # Import the coordination router (mounted as /app/coordination.py)
        from coordination import router as coordination_router

        # Import the AI proxy router (mounted as /app/ai_proxy.py)
        from ai_proxy import router as ai_proxy_router, configure_ai_proxy

        # Build attestation checker using relay's direct DB access
        def check_attestation(public_key: str, jurisdiction: str) -> bool:
            try:
                from civicos_relay.storage.postgres import PostgresAttestationStorage
                relay_url = os.environ.get("RELAY_DATABASE_URL") or os.environ.get("DATABASE_URL")
                if not relay_url:
                    return False
                storage = PostgresAttestationStorage(relay_url)
                return storage.get_attestation(public_key, jurisdiction) is not None
            except Exception:
                return False

        # Build jurisdiction → MCP endpoint map from registry.json
        import json as _json
        jurisdiction_endpoints: dict[str, str] = {}
        try:
            with open("/app/registry.json") as f:
                reg = _json.load(f)
            for jid, config in reg.get("jurisdictions", {}).items():
                domain = config.get("domain", "")
                if domain:
                    jurisdiction_endpoints[jid] = f"https://{domain}"
        except Exception:
            pass  # Fall back to CIVICOS_MCP_URL only

        # Configure AI proxy with jurisdiction routing
        jurisdiction = os.environ.get("CIVICOS_JURISDICTION", "city-san-rafael")
        mcp_url = os.environ.get("CIVICOS_MCP_URL", "")
        if mcp_url or jurisdiction_endpoints:
            configure_ai_proxy(
                mcp_base_url=mcp_url or jurisdiction_endpoints.get(jurisdiction, ""),
                jurisdiction=jurisdiction,
                attestation_checker=check_attestation,
                jurisdiction_endpoints=jurisdiction_endpoints,
            )

        fastapi_app = FastAPI(
            title="CivicOS Coordination Relay",
            version="1.0.0",
        )

        # Usage logging middleware — fire-and-forget, never blocks responses.
        # Relay has no API key auth (uses Nostr signatures), so key_id is always None.
        _usage_jurisdiction = jurisdiction  # capture for closure

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

                async def send_wrapper(message):
                    nonlocal status_code
                    if message["type"] == "http.response.start":
                        status_code = message.get("status")
                    await send(message)

                await self.app(scope, receive, send_wrapper)

                duration_ms = int((_time.time() - start) * 1000)
                method = scope.get("method", "GET")

                # Fire-and-forget usage log
                try:
                    from api_keys import get_api_key_store
                    store = get_api_key_store()
                    if store and store.available:
                        _asyncio.get_event_loop().call_soon(
                            store.log_usage,
                            None,  # key_id — relay uses Nostr signatures, not API keys
                            path,
                            method,
                            status_code,
                            duration_ms,
                            _usage_jurisdiction,
                        )
                except Exception:
                    pass  # Never block response for usage logging

        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Usage logging — outermost middleware, runs after CORS
        # Middleware chain (outermost→innermost):
        #   UsageLogging → CORS → route handler
        fastapi_app.add_middleware(UsageLoggingMiddleware)

        # Mount coordination router — paths are already prefixed with /coordination/
        fastapi_app.include_router(coordination_router)

        # Mount AI proxy router at /api prefix
        fastapi_app.include_router(ai_proxy_router, prefix="/api", tags=["AI Proxy"])

        @fastapi_app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "service": "civicos-relay",
                "platform": "modal",
                "relay_db_configured": bool(os.environ.get("RELAY_DATABASE_URL")),
                "mcp_url_configured": bool(os.environ.get("CIVICOS_MCP_URL")),
                "ai_proxy": True,
            }

        return fastapi_app


@app.local_entrypoint()
def main():
    print("CivicOS Coordination Relay")
    print()
    print("Deploy:")
    print("  modal deploy apps/civicos-relay/modal_relay.py")
    print()
    print("Endpoints:")
    print("  GET  /health")
    print("  POST /coordination/voice")
    print("  GET  /coordination/voice/counts/{entity}")
    print("  GET  /coordination/voice/{entity}")
    print("  POST /coordination/subscribe")
    print("  POST /coordination/initiative")
    print("  GET  /coordination/initiatives/{jurisdiction}")
    print("  POST /api/ai/draft")
    print("  POST /api/ai/chat")
