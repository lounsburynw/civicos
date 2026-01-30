"""
Coordination router: voice, subscriptions, provenance.

Exposes civicos-relay storage via REST API for:
- Voice casting (signed, cryptographically verified)
- Voice counts per entity
- Subscription management
- Key provenance tracking

Endpoints:
- POST /coordination/voice - Cast a voice
- GET /coordination/voice/counts/{entity} - Get voice counts
- GET /coordination/voice/{entity} - List voices for entity
- POST /coordination/subscribe - Create subscription
- DELETE /coordination/subscribe/{subscription_id} - Deactivate subscription
- GET /coordination/provenance/{public_key} - Get key provenance
"""

import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# === Pydantic Request/Response Models ===

class CastVoiceRequest(BaseModel):
    """Request to cast a voice (signed by client)."""
    entity: str = Field(description="Namespaced entity identifier")
    stance: str = Field(description="Position: support, oppose, or watching")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of entity+stance (hex-encoded)")


class VoiceResponse(BaseModel):
    """Voice record response."""
    entity: str
    stance: str
    public_key: str
    signature: str
    timestamp: str
    revoked: bool = False


class VoiceCountResponse(BaseModel):
    """Voice counts for an entity."""
    entity: str
    support: int = 0
    oppose: int = 0
    watching: int = 0
    total: int = 0


class SubscribeRequest(BaseModel):
    """Request to create a subscription."""
    jurisdiction: str
    topics: Optional[list[str]] = None
    event_types: Optional[list[str]] = None
    email: Optional[str] = None
    webhook_url: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Subscription record response."""
    id: str
    jurisdiction: str
    delivery_method: str
    delivery_address: str
    created_at: str
    active: bool


class ProvenanceResponse(BaseModel):
    """Key provenance response."""
    public_key: str
    created_at: str
    total_voices: int
    entities_touched: int
    first_voice_at: Optional[str] = None
    last_voice_at: Optional[str] = None
    jurisdictions: list[str] = []


# === Storage Helpers ===

_storage_instances = {}


def _get_relay_url() -> Optional[str]:
    """Get relay database URL from environment."""
    return os.environ.get("RELAY_DATABASE_URL")


def _get_voice_storage():
    """Get or create voice storage instance."""
    url = _get_relay_url()
    if not url:
        return None

    if "voice" not in _storage_instances:
        try:
            from civicos_relay.storage.postgres import PostgresVoiceStorage
            _storage_instances["voice"] = PostgresVoiceStorage(url)
        except ImportError:
            logger.warning("civicos-relay not available")
            return None
    return _storage_instances["voice"]


def _get_subscription_storage():
    """Get or create subscription storage instance."""
    url = _get_relay_url()
    if not url:
        return None

    if "subscription" not in _storage_instances:
        try:
            from civicos_relay.storage.postgres import PostgresSubscriptionStorage
            _storage_instances["subscription"] = PostgresSubscriptionStorage(url)
        except ImportError:
            logger.warning("civicos-relay not available")
            return None
    return _storage_instances["subscription"]


def _get_provenance_storage():
    """Get or create provenance storage instance."""
    url = _get_relay_url()
    if not url:
        return None

    if "provenance" not in _storage_instances:
        try:
            from civicos_relay.storage.postgres import PostgresProvenanceStorage
            _storage_instances["provenance"] = PostgresProvenanceStorage(url)
        except ImportError:
            logger.warning("civicos-relay not available")
            return None
    return _storage_instances["provenance"]


# === Endpoints ===

@router.post("/coordination/voice", response_model=VoiceResponse)
async def cast_voice(request: CastVoiceRequest):
    """
    Cast a voice on a civic entity.

    Voice must be cryptographically signed by the client. The signature
    verifies the entity+stance combination is authorized by the public key.

    If the key has already voiced on this entity, the old voice is revoked
    and replaced.
    """
    storage = _get_voice_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.voice.models import Voice, Stance
        from civicos_relay.voice.crypto import verify_voice

        # Validate stance
        try:
            stance = Stance(request.stance)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stance: {request.stance}. Must be support, oppose, or watching"
            )

        # Create voice from request
        voice = Voice(
            entity=request.entity,
            stance=stance,
            public_key=request.public_key,
            signature=request.signature,
            timestamp=datetime.utcnow(),
        )

        # Verify signature
        if not verify_voice(voice):
            raise HTTPException(
                status_code=400,
                detail="Invalid voice signature"
            )

        # Check for existing voice and revoke if present
        existing = storage.get_voice(request.public_key, request.entity)
        if existing and not existing.revoked:
            storage.revoke_voice(request.public_key, request.entity)

        # Save new voice
        storage.save_voice(voice)

        # Update provenance
        provenance_storage = _get_provenance_storage()
        if provenance_storage:
            try:
                from civicos_relay.provenance.service import ProvenanceService
                provenance_service = ProvenanceService(provenance_storage)
                provenance_service.record_voice(voice)
            except Exception as e:
                logger.warning(f"Failed to update provenance: {e}")

        return VoiceResponse(
            entity=voice.entity,
            stance=voice.stance.value,
            public_key=voice.public_key,
            signature=voice.signature,
            timestamp=voice.timestamp.isoformat(),
            revoked=voice.revoked,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error casting voice: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/voice/counts/{entity:path}", response_model=VoiceCountResponse)
async def get_voice_counts(entity: str):
    """
    Get voice counts for an entity.

    Returns support, oppose, watching, and total counts.
    """
    storage = _get_voice_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    try:
        from civicos_relay.voice.service import VoiceService

        service = VoiceService(storage)
        counts = service.get_counts(entity)

        return VoiceCountResponse(
            entity=counts.entity,
            support=counts.support,
            oppose=counts.oppose,
            watching=counts.watching,
            total=counts.total,
        )

    except Exception as e:
        logger.error(f"Error getting voice counts: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/voice/{entity:path}", response_model=list[VoiceResponse])
async def list_voices(entity: str):
    """
    List all active voices for an entity.

    Returns all non-revoked voices.
    """
    storage = _get_voice_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    try:
        voices = storage.get_voices_for_entity(entity)

        return [
            VoiceResponse(
                entity=v.entity,
                stance=v.stance.value,
                public_key=v.public_key,
                signature=v.signature,
                timestamp=v.timestamp.isoformat(),
                revoked=v.revoked,
            )
            for v in voices
        ]

    except Exception as e:
        logger.error(f"Error listing voices: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/subscribe", response_model=SubscriptionResponse)
async def subscribe(request: SubscribeRequest):
    """
    Create a subscription for event notifications.

    Must provide either email or webhook_url for delivery.
    """
    storage = _get_subscription_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    if not request.email and not request.webhook_url:
        raise HTTPException(
            status_code=400,
            detail="Must provide either email or webhook_url"
        )

    try:
        from civicos_relay.relay.models import (
            Subscription, MatchCriteria, DeliveryConfig, DeliveryMethod
        )
        import uuid

        # Build delivery config
        if request.email:
            delivery = DeliveryConfig(method=DeliveryMethod.EMAIL, address=request.email)
        else:
            delivery = DeliveryConfig(method=DeliveryMethod.WEBHOOK, address=request.webhook_url)

        # Build match criteria
        match = MatchCriteria(topics=request.topics)

        # Create subscription
        subscription = Subscription(
            id=f"sub_{uuid.uuid4().hex[:12]}",
            jurisdiction=request.jurisdiction,
            match=match,
            delivery=delivery,
            created_at=datetime.utcnow(),
            active=True,
        )

        storage.save_subscription(subscription)

        return SubscriptionResponse(
            id=subscription.id,
            jurisdiction=subscription.jurisdiction,
            delivery_method=subscription.delivery.method.value,
            delivery_address=subscription.delivery.address,
            created_at=subscription.created_at.isoformat(),
            active=subscription.active,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.delete("/coordination/subscribe/{subscription_id}")
async def unsubscribe(subscription_id: str):
    """
    Deactivate a subscription.

    Returns 404 if subscription not found.
    """
    storage = _get_subscription_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    try:
        if not storage.deactivate_subscription(subscription_id):
            raise HTTPException(
                status_code=404,
                detail="Subscription not found"
            )

        return {"status": "unsubscribed", "subscription_id": subscription_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/provenance/{public_key}", response_model=ProvenanceResponse)
async def get_provenance(public_key: str):
    """
    Get provenance for a public key.

    Returns 404 if key has no provenance record.
    """
    storage = _get_provenance_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    try:
        provenance = storage.get_provenance(public_key)

        if not provenance:
            raise HTTPException(
                status_code=404,
                detail="Key not found"
            )

        return ProvenanceResponse(
            public_key=provenance.public_key,
            created_at=provenance.created_at.isoformat(),
            total_voices=provenance.total_voices,
            entities_touched=provenance.entities_touched,
            first_voice_at=provenance.first_voice_at.isoformat() if provenance.first_voice_at else None,
            last_voice_at=provenance.last_voice_at.isoformat() if provenance.last_voice_at else None,
            jurisdictions=provenance.jurisdictions,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting provenance: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
