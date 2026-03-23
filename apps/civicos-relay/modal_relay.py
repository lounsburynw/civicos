"""
Modal deployment for CivicOS Coordination Relay.

Hosts the coordination endpoints (voice, subscriptions, initiatives, sync)
and AI proxy endpoints (draft, chat) as a publicly reachable service.

Parameterized by jurisdiction — the same code deploys separate relay instances
for each jurisdiction, enabling federation testing.

Usage:
    # Deploy San Rafael relay (default)
    modal deploy apps/civicos-relay/modal_relay.py

    # Deploy Mill Valley relay
    CIVICOS_JURISDICTION=city-mill-valley modal deploy apps/civicos-relay/modal_relay.py

    # Deploy San Anselmo relay
    CIVICOS_JURISDICTION=city-san-anselmo modal deploy apps/civicos-relay/modal_relay.py

Naming convention:
    city-san-rafael   -> App: civicos-relay (default, backward-compatible)
    city-mill-valley  -> App: civicos-relay-mill-valley
    city-san-anselmo  -> App: civicos-relay-san-anselmo
"""

import logging
import os
import modal

# ─────────── JURISDICTION CONFIGURATION ───────────

JURISDICTION = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")


def get_relay_app_name(jurisdiction: str) -> str:
    """Derive Modal app name for relay from jurisdiction ID.

    The default relay (San Rafael) keeps the name 'civicos-relay' for
    backward compatibility. Other jurisdictions get 'civicos-relay-{city}'.
    """
    if jurisdiction == "city-san-rafael":
        return "civicos-relay"
    # Strip the level prefix (city-, county-, etc.) for the suffix
    parts = jurisdiction.split("-", 1)
    suffix = parts[1] if len(parts) > 1 else jurisdiction
    return f"civicos-relay-{suffix}"


def get_relay_secrets(jurisdiction: str) -> list[str]:
    """Get list of Modal secret names for this relay instance."""
    secrets = ["civicos-env"]  # Shared DB credentials (RELAY_DATABASE_URL, DATABASE_URL)
    secrets.append("civicos-attestation")  # Attestation keypair
    secrets.append("civic-anthropic")  # AI proxy
    secrets.append("civicos-platform")  # PLATFORM_DATABASE_URL for usage logging
    secrets.append("civicos-token-issuer")  # Token issuer blind signature keys
    return secrets


APP_NAME = get_relay_app_name(JURISDICTION)
SECRETS = get_relay_secrets(JURISDICTION)

app = modal.App(APP_NAME)

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
    # AI proxy router — self-contained, only needs
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
    secrets=[modal.Secret.from_name(s) for s in SECRETS],
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
        from starlette.types import ASGIApp, Receive, Scope, Send

        # Use the relay package's own create_app() — includes all coordination
        # endpoints, lifespan, middleware, and health check.
        from civicos_relay.server.app import create_app
        fastapi_app = create_app()

        # Override health endpoint to include Modal-specific fields
        jurisdiction = os.environ.get("CIVICOS_JURISDICTION", "city-san-rafael")

        @fastapi_app.get("/health", tags=["Health"])
        async def health():
            return {
                "status": "healthy",
                "service": "civicos-relay",
                "jurisdiction": jurisdiction,
                "platform": "modal",
                "relay_db_configured": bool(os.environ.get("RELAY_DATABASE_URL")),
                "mcp_url_configured": bool(os.environ.get("CIVICOS_MCP_URL")),
                "ai_proxy": True,
            }

        # --- AI proxy (Modal-only addition) ---

        from ai_proxy import router as ai_proxy_router, configure_ai_proxy

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
            pass

        mcp_url = os.environ.get("CIVICOS_MCP_URL", "")
        if mcp_url or jurisdiction_endpoints:
            configure_ai_proxy(
                mcp_base_url=mcp_url or jurisdiction_endpoints.get(jurisdiction, ""),
                jurisdiction=jurisdiction,
                attestation_checker=check_attestation,
                jurisdiction_endpoints=jurisdiction_endpoints,
            )

        fastapi_app.include_router(ai_proxy_router, prefix="/api", tags=["AI Proxy"])

        # --- Usage logging middleware (Modal-only addition) ---

        _usage_jurisdiction = jurisdiction

        class UsageLoggingMiddleware:
            """Log API usage to Platform DB. Fire-and-forget, never blocks."""
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

                try:
                    from api_keys import get_api_key_store
                    store = get_api_key_store()
                    if store and store.available:
                        _asyncio.get_event_loop().run_in_executor(
                            None,
                            store.log_usage,
                            None,
                            path,
                            method,
                            status_code,
                            duration_ms,
                            _usage_jurisdiction,
                        )
                except Exception as e:
                    logging.getLogger("civicos-relay").debug("Usage logging failed: %s", e)

        fastapi_app.add_middleware(UsageLoggingMiddleware)

        return fastapi_app


@app.local_entrypoint()
def main():
    print("CivicOS Coordination Relay - Parameterized Deployment")
    print()
    print(f"Current configuration:")
    print(f"  Jurisdiction: {JURISDICTION}")
    print(f"  App name:     {APP_NAME}")
    print(f"  Secrets:      {', '.join(SECRETS)}")
    print()
    print("Deploy commands:")
    print("  # San Rafael (default)")
    print("  modal deploy apps/civicos-relay/modal_relay.py")
    print()
    print("  # Mill Valley")
    print("  CIVICOS_JURISDICTION=city-mill-valley modal deploy apps/civicos-relay/modal_relay.py")
    print()
    print("  # San Anselmo")
    print("  CIVICOS_JURISDICTION=city-san-anselmo modal deploy apps/civicos-relay/modal_relay.py")
    print()
    print("Endpoints:")
    print("  GET  /health")
    print("  POST /coordination/voice")
    print("  GET  /coordination/voice/counts/{entity}")
    print("  GET  /coordination/voice/{entity}")
    print("  POST /coordination/subscribe")
    print("  POST /coordination/initiative")
    print("  GET  /coordination/initiatives/{jurisdiction}")
    print("  GET  /coordination/tokens/info")
    print("  POST /coordination/tokens/session")
    print("  POST /coordination/tokens/sign")
    print("  POST /api/ai/draft")
    print("  POST /api/ai/chat")
