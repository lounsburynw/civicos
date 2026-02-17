"""
Modal deployment for CivicOS Coordination Relay.

Hosts the coordination endpoints (voice, subscriptions, initiatives, sync)
as a publicly reachable service. The frontend posts to this relay for
voice casting and counts.

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
    )
    .add_local_python_source("civicos_relay")
    # The coordination router lives in civicos_services but has zero
    # internal civicos_services imports — it only needs civicos_relay,
    # fastapi, and pydantic. We mount the single file directly.
    .add_local_file(
        "packages/civicos-services/src/civicos_services/servers/routers/coordination.py",
        remote_path="/app/coordination.py",
    )
)


@app.cls(
    image=relay_image,
    secrets=[
        modal.Secret.from_name("civicos-env"),
        modal.Secret.from_name("civicos-attestation"),
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

        # Make the mounted coordination module importable
        sys.path.insert(0, "/app")

        self.logger.info("CivicOS Relay initializing on Modal...")

        # Verify relay DB is configured
        import os
        relay_url = os.environ.get("RELAY_DATABASE_URL")
        if relay_url:
            self.logger.info("RELAY_DATABASE_URL configured")
        else:
            self.logger.warning("RELAY_DATABASE_URL not set — coordination endpoints will return 503")

    @modal.asgi_app()
    def relay_endpoint(self):
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        # Import the coordination router (mounted as /app/coordination.py)
        from coordination import router as coordination_router

        fastapi_app = FastAPI(
            title="CivicOS Coordination Relay",
            version="1.0.0",
        )

        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Mount coordination router — paths are already prefixed with /coordination/
        fastapi_app.include_router(coordination_router)

        @fastapi_app.get("/health")
        async def health():
            import os
            return {
                "status": "healthy",
                "service": "civicos-relay",
                "platform": "modal",
                "relay_db_configured": bool(os.environ.get("RELAY_DATABASE_URL")),
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
