"""FastAPI application for relay server."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field

from civicos_relay.identity import RelayIdentity, RelayConfig
from civicos_relay.voice.models import Voice, Stance, VoiceCount
from civicos_relay.voice.service import VoiceService
from civicos_relay.voice.crypto import KeyPair, sign_voice
from civicos_relay.relay.models import Subscription, MatchCriteria, DeliveryConfig, DeliveryMethod
from civicos_relay.relay.service import RelayService
from civicos_relay.provenance.models import KeyProvenance
from civicos_relay.provenance.service import ProvenanceService
from civicos_relay.sync.protocol import SyncRequest, VoiceSyncResponse, VoiceImportRequest, VoiceImportResponse
from civicos_relay.sync.service import SyncService
from civicos_relay.storage import InMemoryStorage
from civicos_relay.delivery import EmailDelivery, EmailConfig

logger = logging.getLogger(__name__)


# Request/Response models for API
class CastVoiceRequest(BaseModel):
    """Request to cast a voice."""
    entity: str
    stance: Stance
    public_key: str
    signature: str


class SubscribeRequest(BaseModel):
    """Request to create a subscription."""
    jurisdiction: str
    topics: Optional[list[str]] = None
    event_types: Optional[list[str]] = None
    email: Optional[str] = None
    webhook_url: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    relay_id: str
    version: str = "0.1.0"


# Global state (will be replaced with proper DI)
_relay_state = {}


def get_voice_service() -> VoiceService:
    return _relay_state["voice_service"]


def get_relay_service() -> RelayService:
    return _relay_state["relay_service"]


def get_provenance_service() -> ProvenanceService:
    return _relay_state["provenance_service"]


def get_sync_service() -> SyncService:
    return _relay_state["sync_service"]


def get_identity() -> RelayIdentity:
    return _relay_state["identity"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    config = RelayConfig.from_env()
    identity = RelayIdentity.load_or_generate(
        config.relay_id,
        config.private_key_path,
    )

    # Use in-memory storage for now (swap for Postgres in production)
    storage = InMemoryStorage()

    # Initialize email delivery if configured
    email_delivery = None
    if os.environ.get("SMTP_HOST"):
        email_config = EmailConfig.from_env()
        email_delivery = EmailDelivery(email_config)
        logger.info(f"Email delivery enabled: {email_config.smtp_host}:{email_config.smtp_port}")
    else:
        logger.info("Email delivery disabled (SMTP_HOST not set)")

    _relay_state["identity"] = identity
    _relay_state["voice_service"] = VoiceService(storage.voices)
    _relay_state["relay_service"] = RelayService(storage.subscriptions, email_delivery)
    _relay_state["provenance_service"] = ProvenanceService(storage.provenance)
    _relay_state["sync_service"] = SyncService(identity, storage.sync, config.peers)

    if config.sync_enabled:
        await _relay_state["sync_service"].start()

    logger.info(f"Relay started: {identity.relay_id}")

    yield

    # Shutdown
    await _relay_state["sync_service"].stop()
    logger.info("Relay stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="CivicOS Relay",
        description="Federation-ready civic coordination relay",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Health endpoints
    @app.get("/health", response_model=HealthResponse)
    async def health(identity: RelayIdentity = Depends(get_identity)):
        return HealthResponse(status="healthy", relay_id=identity.relay_id)

    # Voice endpoints
    @app.post("/voice", response_model=Voice)
    async def cast_voice(
        request: CastVoiceRequest,
        voice_service: VoiceService = Depends(get_voice_service),
        provenance_service: ProvenanceService = Depends(get_provenance_service),
    ):
        """Cast a voice on an entity."""
        # Create voice from signed request
        voice = Voice(
            entity=request.entity,
            stance=request.stance,
            public_key=request.public_key,
            signature=request.signature,
        )

        # Verify and store
        if not voice_service.verify(voice):
            raise HTTPException(status_code=400, detail="Invalid voice signature")

        # Check for existing voice and handle
        existing = voice_service._storage.get_voice(request.public_key, request.entity)
        if existing and not existing.revoked:
            voice_service._storage.revoke_voice(request.public_key, request.entity)

        voice_service._storage.save_voice(voice)

        # Update provenance
        provenance_service.record_voice(voice)

        return voice

    @app.get("/voice/counts/{entity:path}", response_model=VoiceCount)
    async def get_voice_counts(
        entity: str,
        voice_service: VoiceService = Depends(get_voice_service),
    ):
        """Get voice counts for an entity."""
        return voice_service.get_counts(entity)

    @app.get("/voice/{entity:path}", response_model=list[Voice])
    async def list_voices(
        entity: str,
        voice_service: VoiceService = Depends(get_voice_service),
    ):
        """List all voices for an entity."""
        return voice_service._storage.get_voices_for_entity(entity)

    # Subscription endpoints
    @app.post("/subscribe", response_model=Subscription)
    async def subscribe(
        request: SubscribeRequest,
        relay_service: RelayService = Depends(get_relay_service),
    ):
        """Create a subscription for event notifications."""
        if request.email:
            delivery = DeliveryConfig(method=DeliveryMethod.EMAIL, address=request.email)
        elif request.webhook_url:
            delivery = DeliveryConfig(method=DeliveryMethod.WEBHOOK, address=request.webhook_url)
        else:
            raise HTTPException(status_code=400, detail="Must provide email or webhook_url")

        match = MatchCriteria(topics=request.topics)

        return relay_service.subscribe(
            jurisdiction=request.jurisdiction,
            match=match,
            delivery=delivery,
        )

    @app.delete("/subscribe/{subscription_id}")
    async def unsubscribe(
        subscription_id: str,
        relay_service: RelayService = Depends(get_relay_service),
    ):
        """Unsubscribe from notifications."""
        if not relay_service.unsubscribe(subscription_id):
            raise HTTPException(status_code=404, detail="Subscription not found")
        return {"status": "unsubscribed"}

    # Provenance endpoints
    @app.get("/provenance/{public_key}", response_model=Optional[KeyProvenance])
    async def get_provenance(
        public_key: str,
        provenance_service: ProvenanceService = Depends(get_provenance_service),
    ):
        """Get provenance for a public key."""
        provenance = provenance_service.get_for_key(public_key)
        if not provenance:
            raise HTTPException(status_code=404, detail="Key not found")
        return provenance

    # Sync endpoints (federation)
    @app.get("/sync/voices", response_model=VoiceSyncResponse)
    async def export_voices(
        since: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        sync_service: SyncService = Depends(get_sync_service),
    ):
        """Export voices for peer sync."""
        from datetime import datetime
        request = SyncRequest(
            since=datetime.fromisoformat(since) if since else None,
            namespace=namespace,
            limit=min(limit, 1000),
            cursor=cursor,
        )
        return sync_service.export_voices(request)

    @app.post("/sync/voices", response_model=VoiceImportResponse)
    async def import_voices(
        request: VoiceImportRequest,
        sync_service: SyncService = Depends(get_sync_service),
    ):
        """Import voices from a peer relay."""
        return sync_service.import_voices(request)

    return app


def main():
    """Run the relay server."""
    import uvicorn
    import os

    host = os.environ.get("RELAY_HOST", "0.0.0.0")
    port = int(os.environ.get("RELAY_PORT", "8003"))

    uvicorn.run(
        "civicos_relay.server:create_app",
        factory=True,
        host=host,
        port=port,
        reload=os.environ.get("RELAY_DEV", "false").lower() == "true",
    )


# For direct import
app = create_app()
