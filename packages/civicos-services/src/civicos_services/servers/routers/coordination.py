"""
Coordination router: voice, subscriptions, provenance, sync.

Exposes civicos-relay storage via REST API for:
- Voice casting (signed, cryptographically verified)
- Voice counts per entity
- Subscription management
- Key provenance tracking
- Relay-to-relay sync

Endpoints:
- POST /coordination/voice - Cast a voice
- GET /coordination/voice/counts/{entity} - Get voice counts
- GET /coordination/voice/{entity} - List voices for entity
- POST /coordination/subscribe - Create subscription
- DELETE /coordination/subscribe/{subscription_id} - Deactivate subscription
- GET /coordination/provenance/{public_key} - Get key provenance
- GET /coordination/sync/voices - Export voices for peer sync
- POST /coordination/sync/voices - Import voices from peer
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
    created_at: Optional[int] = Field(default=None, description="Unix timestamp from the signed Nostr event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction code for Nostr event reconstruction")


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


class CreateInitiativeRequest(BaseModel):
    """Request to create an initiative (signed by creator)."""
    jurisdiction: str = Field(description="e.g., 'city-san-rafael'")
    topic: str = Field(description="Topic area, e.g., 'traffic safety'")
    title: str = Field(description="Short title for the initiative")
    description: str = Field(description="Full description")
    location: Optional[str] = Field(default=None, description="Optional physical location")
    public_key: str = Field(description="Creator's public key (hex-encoded)")
    signature: str = Field(description="Signature of initiative data (hex-encoded)")


class InitiativeResponse(BaseModel):
    """Initiative record response."""
    id: str
    jurisdiction: str
    topic: str
    title: str
    description: str
    location: Optional[str] = None
    public_key: str
    timestamp: str
    status: str
    voice_count: int = 0


# === Action Request/Response Models ===

class CommitActionRequest(BaseModel):
    """Request to commit to an action (signed by client)."""
    action_id: str = Field(description="Action identifier")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of action commitment (hex-encoded)")


class CompleteActionRequest(BaseModel):
    """Request to mark an action complete (signed by client)."""
    action_id: str = Field(description="Action identifier")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of action completion (hex-encoded)")
    evidence_url: Optional[str] = Field(default=None, description="URL to evidence")


class ActionResponse(BaseModel):
    """Action record response."""
    action_id: str
    action_type: str  # "commitment" or "completion"
    public_key: str
    signature: str
    timestamp: str
    evidence_url: Optional[str] = None
    revoked: bool = False


class ActionCountResponse(BaseModel):
    """Action counts for an action ID."""
    action_id: str
    commitments: int = 0
    completions: int = 0
    target: Optional[int] = None


# === Civic Action Event Request/Response Models (Kind 30810/30811/30812) ===


class CreateCivicActionEventRequest(BaseModel):
    """Request to create a civic action event (Kind 30810)."""
    initiative_id: str = Field(description="ID of the parent initiative")
    action_type: str = Field(description="Action type: written_comment, attend_meeting, etc.")
    description: str = Field(description="Human-readable description of the action")
    public_key: str = Field(description="Creator's public key (hex-encoded)")
    signature: str = Field(description="Signature of action data (hex-encoded)")
    target: Optional[str] = Field(default=None, description="Target of action")
    deadline: Optional[str] = Field(default=None, description="Deadline ISO 8601")
    template: Optional[str] = Field(default=None, description="Template text for action")
    target_count: Optional[int] = Field(default=None, description="Target number of completions")


class CivicActionEventResponse(BaseModel):
    """Civic action event response (Kind 30810)."""
    id: str
    initiative_id: str
    action_type: str
    description: str
    target: Optional[str] = None
    deadline: Optional[str] = None
    template: Optional[str] = None
    target_count: Optional[int] = None
    public_key: str
    timestamp: str
    revoked: bool = False


class CivicCommitmentRequest(BaseModel):
    """Request to commit to a civic action (Kind 30811)."""
    action_id: str = Field(description="ID of the action event")
    public_key: str = Field(description="Committer's public key (hex-encoded)")
    signature: str = Field(description="Signature of commitment (hex-encoded)")


class CivicCommitmentResponse(BaseModel):
    """Civic commitment response (Kind 30811)."""
    id: str
    action_ref: str
    status: str
    public_key: str
    timestamp: str
    revoked: bool = False


class CivicCompletionRequest(BaseModel):
    """Request to complete a civic action (Kind 30812)."""
    action_id: str = Field(description="ID of the action event")
    public_key: str = Field(description="Completer's public key (hex-encoded)")
    signature: str = Field(description="Signature of completion (hex-encoded)")
    evidence_type: str = Field(description="Type of evidence: self_report, email_confirmation, etc.")
    evidence_content: Optional[str] = Field(default=None, description="Evidence URL or content")


class CivicCompletionResponse(BaseModel):
    """Civic completion response (Kind 30812)."""
    id: str
    action_ref: str
    evidence_type: str
    evidence_content: Optional[str] = None
    completed_at: str
    public_key: str
    timestamp: str
    revoked: bool = False


# === Comment Request/Response Models ===


class SubmitCommentRequest(BaseModel):
    """Request to submit a public comment."""
    entity: str
    comment_text: str
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    jurisdiction: Optional[str] = None
    stance: Optional[str] = None


class CommentResponse(BaseModel):
    """Comment record response."""
    entity: str
    comment_text: str
    public_key: str
    signature: str
    timestamp: str
    jurisdiction: Optional[str] = None
    stance: Optional[str] = None
    deleted: bool = False


class CommentCountResponse(BaseModel):
    """Comment count for an entity."""
    entity: str
    count: int = 0


class CivicActionProgressResponse(BaseModel):
    """Progress for a civic action event."""
    action_id: str
    commitment_count: int = 0
    completion_count: int = 0
    target_count: Optional[int] = None
    progress_percent: Optional[float] = None


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


def _get_initiative_storage():
    """Get or create initiative storage instance."""
    url = _get_relay_url()
    if not url:
        return None

    if "initiative" not in _storage_instances:
        try:
            from civicos_relay.storage.postgres import PostgresInitiativeStorage
            _storage_instances["initiative"] = PostgresInitiativeStorage(url)
        except ImportError:
            logger.warning("civicos-relay not available")
            return None
    return _storage_instances["initiative"]


def _get_sync_storage():
    """Get or create sync storage instance."""
    # Check if already set (for testing)
    if "sync" in _storage_instances:
        return _storage_instances["sync"]

    url = _get_relay_url()
    if not url:
        return None

    try:
        from civicos_relay.storage.postgres import PostgresSyncStorage
        _storage_instances["sync"] = PostgresSyncStorage(url)
    except ImportError:
        logger.warning("civicos-relay not available")
        return None
    return _storage_instances["sync"]


def _get_relay_identity():
    """Get or create relay identity for signing sync responses."""
    # Check if already set (for testing)
    if "identity" in _storage_instances:
        return _storage_instances["identity"]

    try:
        from civicos_relay.identity import RelayIdentity
        relay_id = os.environ.get("RELAY_ID", "relay.civicos.local")
        private_key_path = os.environ.get("RELAY_PRIVATE_KEY_PATH")
        _storage_instances["identity"] = RelayIdentity.load_or_generate(
            relay_id, private_key_path
        )
    except ImportError:
        logger.warning("civicos-relay not available")
        return None
    return _storage_instances["identity"]


def _get_action_storage():
    """Get or create action storage instance.

    Uses PostgresActionStorage when RELAY_DATABASE_URL is set,
    falls back to in-memory storage for testing.
    """
    if "action" not in _storage_instances:
        url = _get_relay_url()
        if url:
            try:
                from civicos_relay.storage.postgres import PostgresActionStorage
                _storage_instances["action"] = PostgresActionStorage(url)
                logger.info("Using PostgresActionStorage for actions")
            except ImportError:
                logger.warning("civicos-relay postgres not available, falling back to in-memory")
                from civicos_relay.storage.memory import InMemoryActionStorage
                _storage_instances["action"] = InMemoryActionStorage()
        else:
            try:
                from civicos_relay.storage.memory import InMemoryActionStorage
                _storage_instances["action"] = InMemoryActionStorage()
            except ImportError:
                logger.warning("civicos-relay not available")
                return None
    return _storage_instances["action"]


def _get_comment_storage():
    """Get or create comment storage instance."""
    if "comment" not in _storage_instances:
        url = _get_relay_url()
        if url:
            try:
                from civicos_relay.storage.postgres import PostgresCommentStorage
                _storage_instances["comment"] = PostgresCommentStorage(url)
                logger.info("Using PostgresCommentStorage for comments")
            except ImportError:
                logger.warning("civicos-relay postgres not available for comments")
                return None
        else:
            try:
                from civicos_relay.storage.memory import InMemoryCommentStorage
                _storage_instances["comment"] = InMemoryCommentStorage()
            except ImportError:
                logger.warning("civicos-relay not available for comments")
                return None
    return _storage_instances["comment"]


def _get_civic_action_service():
    """Get or create civic action service (Kind 30810/30811/30812).

    Uses PostgreSQL storage when RELAY_DATABASE_URL is set,
    falls back to in-memory storage for testing.
    """
    if "civic_action_service" not in _storage_instances:
        url = _get_relay_url()
        try:
            from civicos_relay.voice.civic_action_service import CivicActionService

            if url:
                from civicos_relay.storage.postgres import (
                    PostgresCivicActionEventStorage,
                    PostgresCivicCommitmentStorage,
                    PostgresCivicCompletionStorage,
                )
                _storage_instances["civic_action_events"] = PostgresCivicActionEventStorage(url)
                _storage_instances["civic_commitments"] = PostgresCivicCommitmentStorage(url)
                _storage_instances["civic_completions"] = PostgresCivicCompletionStorage(url)
                logger.info("Using PostgreSQL storage for civic actions")
            else:
                from civicos_relay.storage.memory import (
                    InMemoryCivicActionEventStorage,
                    InMemoryCivicCommitmentStorage,
                    InMemoryCivicCompletionStorage,
                )
                _storage_instances["civic_action_events"] = InMemoryCivicActionEventStorage()
                _storage_instances["civic_commitments"] = InMemoryCivicCommitmentStorage()
                _storage_instances["civic_completions"] = InMemoryCivicCompletionStorage()

            _storage_instances["civic_action_service"] = CivicActionService(
                _storage_instances["civic_action_events"],
                _storage_instances["civic_commitments"],
                _storage_instances["civic_completions"],
            )
        except ImportError as e:
            logger.warning(f"civicos-relay not available: {e}")
            return None
    return _storage_instances["civic_action_service"]


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
            created_at=request.created_at,
            jurisdiction=request.jurisdiction,
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


# === Initiative Endpoints ===


def _generate_initiative_id(jurisdiction: str, title: str) -> str:
    """Generate deterministic initiative ID from jurisdiction + title + timestamp."""
    import hashlib
    from datetime import date

    # Use date + title hash for uniqueness
    today = date.today().isoformat()
    title_hash = hashlib.sha256(title.encode()).hexdigest()[:8]
    return f"initiative:{jurisdiction}:{today}:{title_hash}"


def _create_initiative_message(
    initiative_id: str, topic: str, title: str, timestamp: str
) -> str:
    """Create the message that must be signed for initiative creation."""
    import hashlib

    title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
    return f"civicos:initiative:v1:{initiative_id}:{topic}:{title_hash}:{timestamp}"


def _verify_initiative_signature(
    public_key: str, signature: str, message: str
) -> bool:
    """Verify initiative signature using ECDSA P-256."""
    try:
        from civicos_relay.voice.crypto import verify_signature
        return verify_signature(public_key, signature, message)
    except ImportError:
        logger.error("civicos-relay crypto module not available")
        return False


@router.post("/coordination/initiative", response_model=InitiativeResponse)
async def create_initiative(request: CreateInitiativeRequest):
    """
    Create a new initiative (focal point for coordination).

    Initiative must be cryptographically signed by the creator. The signature
    verifies the initiative data is authorized by the public key.

    Returns the created initiative with its generated ID.
    """
    storage = _get_initiative_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.relay.models import Initiative, InitiativeStatus

        # Generate initiative ID
        initiative_id = _generate_initiative_id(request.jurisdiction, request.title)
        timestamp = datetime.utcnow()

        # Create the message that should have been signed
        message = _create_initiative_message(
            initiative_id,
            request.topic,
            request.title,
            timestamp.isoformat(),
        )

        # Verify signature
        if not _verify_initiative_signature(
            request.public_key, request.signature, message
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid initiative signature"
            )

        # Check if initiative already exists
        existing = storage.get_initiative(initiative_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Initiative already exists: {initiative_id}"
            )

        # Create initiative
        initiative = Initiative(
            id=initiative_id,
            jurisdiction=request.jurisdiction,
            topic=request.topic,
            title=request.title,
            description=request.description,
            location=request.location,
            public_key=request.public_key,
            signature=request.signature,
            timestamp=timestamp,
            status=InitiativeStatus.ACTIVE,
            voice_count=0,
        )

        storage.save_initiative(initiative)

        logger.info(f"Initiative created: {initiative_id} by {request.public_key[:16]}...")

        return InitiativeResponse(
            id=initiative.id,
            jurisdiction=initiative.jurisdiction,
            topic=initiative.topic,
            title=initiative.title,
            description=initiative.description,
            location=initiative.location,
            public_key=initiative.public_key,
            timestamp=initiative.timestamp.isoformat(),
            status=initiative.status.value,
            voice_count=initiative.voice_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating initiative: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/initiatives/{jurisdiction}",
    response_model=list[InitiativeResponse],
)
async def list_initiatives(
    jurisdiction: str,
    topic: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
):
    """
    List initiatives for a jurisdiction.

    Optional filters:
    - topic: Filter by topic (e.g., "traffic safety")
    - status: Filter by status ("active", "completed", "failed")
    - limit: Maximum results (default 100)

    Results are ordered by voice_count (descending), then timestamp (descending).
    """
    storage = _get_initiative_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    try:
        from civicos_relay.relay.models import InitiativeStatus as StatusEnum

        # Parse status filter if provided
        status_filter = None
        if status:
            try:
                status_filter = StatusEnum(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be active, completed, or failed"
                )

        initiatives = storage.get_initiatives_for_jurisdiction(
            jurisdiction=jurisdiction,
            topic=topic,
            status=status_filter,
            limit=min(limit, 1000),  # Cap at 1000
        )

        return [
            InitiativeResponse(
                id=i.id,
                jurisdiction=i.jurisdiction,
                topic=i.topic,
                title=i.title,
                description=i.description,
                location=i.location,
                public_key=i.public_key,
                timestamp=i.timestamp.isoformat(),
                status=i.status.value,
                voice_count=i.voice_count,
            )
            for i in initiatives
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing initiatives: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/initiative/{initiative_id:path}", response_model=InitiativeResponse)
async def get_initiative(initiative_id: str):
    """
    Get a specific initiative by ID.

    Returns 404 if initiative not found.
    """
    storage = _get_initiative_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured"
        )

    try:
        initiative = storage.get_initiative(initiative_id)

        if not initiative:
            raise HTTPException(
                status_code=404,
                detail="Initiative not found"
            )

        return InitiativeResponse(
            id=initiative.id,
            jurisdiction=initiative.jurisdiction,
            topic=initiative.topic,
            title=initiative.title,
            description=initiative.description,
            location=initiative.location,
            public_key=initiative.public_key,
            timestamp=initiative.timestamp.isoformat(),
            status=initiative.status.value,
            voice_count=initiative.voice_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting initiative: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Sync Endpoints ===


class VoiceSyncResponseAPI(BaseModel):
    """Response containing voices for peer sync."""
    voices: list[VoiceResponse]
    cursor: Optional[str] = None
    relay_id: str
    relay_signature: str


class VoiceImportRequestAPI(BaseModel):
    """Request to import voices from a peer."""
    voices: list[VoiceResponse]
    source_relay: str
    signature: str


class VoiceImportResponseAPI(BaseModel):
    """Response after importing voices."""
    accepted: int
    rejected: int
    duplicates: int


@router.get("/coordination/sync/voices", response_model=VoiceSyncResponseAPI)
async def export_voices(
    since: Optional[str] = None,
    namespace: Optional[str] = None,
    limit: int = 100,
    cursor: Optional[str] = None,
):
    """
    Export voices for peer relay sync.

    Parameters:
    - since: ISO timestamp, only return voices after this time
    - namespace: Filter by entity namespace prefix (e.g., "city-san-rafael:*")
    - limit: Max results per page (1-1000, default 100)
    - cursor: Pagination cursor from previous response

    Returns signed response for peer verification.
    """
    storage = _get_sync_storage()
    identity = _get_relay_identity()
    if not storage or not identity:
        raise HTTPException(
            status_code=503,
            detail="Sync service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.sync import SyncService
        from civicos_relay.sync.protocol import SyncRequest

        # Create sync service
        sync_service = SyncService(identity, storage, [])

        # Parse since timestamp - use cursor if provided, otherwise since param
        since_dt = None
        if cursor:
            since_dt = datetime.fromisoformat(cursor)
        elif since:
            since_dt = datetime.fromisoformat(since)

        # Build request
        request = SyncRequest(
            since=since_dt,
            namespace=namespace,
            limit=min(limit, 1000),
            cursor=cursor,
        )

        # Export voices
        response = sync_service.export_voices(request)

        return VoiceSyncResponseAPI(
            voices=[
                VoiceResponse(
                    entity=v.entity,
                    stance=v.stance.value,
                    public_key=v.public_key,
                    signature=v.signature,
                    timestamp=v.timestamp.isoformat(),
                    revoked=v.revoked,
                )
                for v in response.voices
            ],
            cursor=response.cursor,
            relay_id=response.relay_id,
            relay_signature=response.relay_signature,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Error exporting voices: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/sync/voices", response_model=VoiceImportResponseAPI)
async def import_voices(request: VoiceImportRequestAPI):
    """
    Import voices from a peer relay.

    Voices are verified for valid signatures before import.
    Duplicates (same public_key+entity with newer timestamp) are skipped.

    Returns counts of accepted, rejected, and duplicate voices.
    """
    storage = _get_sync_storage()
    identity = _get_relay_identity()
    if not storage or not identity:
        raise HTTPException(
            status_code=503,
            detail="Sync service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.sync import SyncService
        from civicos_relay.sync.protocol import VoiceImportRequest
        from civicos_relay.voice.models import Voice, Stance

        # Create sync service
        sync_service = SyncService(identity, storage, [])

        # Convert API voices to internal format
        voices = [
            Voice(
                entity=v.entity,
                stance=Stance(v.stance),
                public_key=v.public_key,
                signature=v.signature,
                timestamp=datetime.fromisoformat(v.timestamp),
                revoked=v.revoked,
            )
            for v in request.voices
        ]

        # Build import request
        import_request = VoiceImportRequest(
            voices=voices,
            source_relay=request.source_relay,
            signature=request.signature,
        )

        # Import voices
        response = sync_service.import_voices(import_request)

        logger.info(
            f"Voice import from {request.source_relay}: "
            f"{response.accepted} accepted, {response.rejected} rejected, "
            f"{response.duplicates} duplicates"
        )

        return VoiceImportResponseAPI(
            accepted=response.accepted,
            rejected=response.rejected,
            duplicates=response.duplicates,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid voice data: {str(e)}")
    except Exception as e:
        logger.error(f"Error importing voices: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Event Sync Endpoints ===


class EventResponseAPI(BaseModel):
    """API representation of an event."""
    type: str
    jurisdiction: str
    entity: str
    timestamp: str
    data: dict


class EventSyncResponseAPI(BaseModel):
    """Response containing events for peer sync."""
    events: list[EventResponseAPI]
    cursor: Optional[str] = None
    relay_id: str
    relay_signature: str


class EventImportRequestAPI(BaseModel):
    """Request to import events from a peer."""
    events: list[EventResponseAPI]
    source_relay: str
    signature: str


class EventImportResponseAPI(BaseModel):
    """Response after importing events."""
    accepted: int
    rejected: int
    duplicates: int


@router.get("/coordination/sync/events", response_model=EventSyncResponseAPI)
async def export_events(
    since: Optional[str] = None,
    namespace: Optional[str] = None,
    limit: int = 100,
    cursor: Optional[str] = None,
):
    """
    Export events for peer relay sync.

    Parameters:
    - since: ISO timestamp, only return events after this time
    - namespace: Filter by jurisdiction prefix (e.g., "city-san-rafael")
    - limit: Max results per page (1-1000, default 100)
    - cursor: Pagination cursor from previous response

    Returns signed response for peer verification.
    """
    storage = _get_sync_storage()
    identity = _get_relay_identity()
    if not storage or not identity:
        raise HTTPException(
            status_code=503,
            detail="Sync service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.sync import SyncService
        from civicos_relay.sync.protocol import SyncRequest

        # Create sync service
        sync_service = SyncService(identity, storage, [])

        # Parse since timestamp - use cursor if provided, otherwise since param
        since_dt = None
        if cursor:
            since_dt = datetime.fromisoformat(cursor)
        elif since:
            since_dt = datetime.fromisoformat(since)

        # Build request
        request = SyncRequest(
            since=since_dt,
            namespace=namespace,
            limit=min(limit, 1000),
            cursor=cursor,
        )

        # Export events
        response = sync_service.export_events(request)

        return EventSyncResponseAPI(
            events=[
                EventResponseAPI(
                    type=e.type.value,
                    jurisdiction=e.jurisdiction,
                    entity=e.entity,
                    timestamp=e.timestamp.isoformat(),
                    data=e.data,
                )
                for e in response.events
            ],
            cursor=response.cursor,
            relay_id=response.relay_id,
            relay_signature=response.relay_signature,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Error exporting events: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/sync/events", response_model=EventImportResponseAPI)
async def import_events(request: EventImportRequestAPI):
    """
    Import events from a peer relay.

    Events are verified before import.
    Duplicates (same type+entity+timestamp) are skipped.

    Returns counts of accepted, rejected, and duplicate events.
    """
    storage = _get_sync_storage()
    identity = _get_relay_identity()
    if not storage or not identity:
        raise HTTPException(
            status_code=503,
            detail="Sync service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.sync import SyncService
        from civicos_relay.sync.protocol import EventImportRequest
        from civicos_relay.relay.models import Event, EventType

        # Create sync service
        sync_service = SyncService(identity, storage, [])

        # Convert API events to internal format
        events = [
            Event(
                type=EventType(e.type),
                jurisdiction=e.jurisdiction,
                entity=e.entity,
                timestamp=datetime.fromisoformat(e.timestamp),
                data=e.data,
            )
            for e in request.events
        ]

        # Build import request
        import_request = EventImportRequest(
            events=events,
            source_relay=request.source_relay,
            signature=request.signature,
        )

        # Import events
        response = sync_service.import_events(import_request)

        logger.info(
            f"Event import from {request.source_relay}: "
            f"{response.accepted} accepted, {response.rejected} rejected, "
            f"{response.duplicates} duplicates"
        )

        return EventImportResponseAPI(
            accepted=response.accepted,
            rejected=response.rejected,
            duplicates=response.duplicates,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid event data: {str(e)}")
    except Exception as e:
        logger.error(f"Error importing events: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Action Endpoints ===


@router.post("/coordination/action/commit", response_model=ActionResponse)
async def commit_action(request: CommitActionRequest):
    """
    Commit to a civic action.

    The commitment must be cryptographically signed by the client.
    If the key has already committed to this action, the old commitment
    is revoked and replaced.
    """
    storage = _get_action_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Action service not configured"
        )

    try:
        from civicos_relay.voice.action_service import ActionService
        from civicos_relay.voice.crypto import verify_signature

        # Verify signature
        message = f"civicos:action:v1:{request.action_id}:commitment"
        if not verify_signature(request.public_key, request.signature, message):
            raise HTTPException(
                status_code=400,
                detail="Invalid commitment signature"
            )

        service = ActionService(storage)
        action = service.record_commitment(
            action_id=request.action_id,
            public_key=request.public_key,
            signature=request.signature,
        )

        return ActionResponse(
            action_id=action.action_id,
            action_type=action.action_type.value,
            public_key=action.public_key,
            signature=action.signature,
            timestamp=action.timestamp.isoformat(),
            revoked=action.revoked,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error committing action: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/action/complete", response_model=ActionResponse)
async def complete_action(request: CompleteActionRequest):
    """
    Mark a civic action as complete.

    The completion must be cryptographically signed by the client.
    Optionally includes evidence_url to prove completion.
    """
    storage = _get_action_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Action service not configured"
        )

    try:
        from civicos_relay.voice.action_service import ActionService
        from civicos_relay.voice.crypto import verify_signature

        # Verify signature
        message = f"civicos:action:v1:{request.action_id}:completion"
        if not verify_signature(request.public_key, request.signature, message):
            raise HTTPException(
                status_code=400,
                detail="Invalid completion signature"
            )

        service = ActionService(storage)
        action = service.record_completion(
            action_id=request.action_id,
            public_key=request.public_key,
            signature=request.signature,
            evidence_url=request.evidence_url,
        )

        return ActionResponse(
            action_id=action.action_id,
            action_type=action.action_type.value,
            public_key=action.public_key,
            signature=action.signature,
            timestamp=action.timestamp.isoformat(),
            evidence_url=action.evidence_url,
            revoked=action.revoked,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing action: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/action/counts/{action_id:path}", response_model=ActionCountResponse)
async def get_action_counts(action_id: str, target: Optional[int] = None):
    """
    Get action counts for an action ID.

    Returns commitment and completion counts. Optionally specify a target
    to calculate progress.
    """
    storage = _get_action_storage()
    if not storage:
        # Return zeros if service not configured (graceful degradation)
        return ActionCountResponse(
            action_id=action_id,
            commitments=0,
            completions=0,
            target=target,
        )

    try:
        from civicos_relay.voice.action_service import ActionService

        service = ActionService(storage)
        counts = service.get_counts(action_id, target=target)

        return ActionCountResponse(
            action_id=counts.action_id,
            commitments=counts.commitments,
            completions=counts.completions,
            target=counts.target,
        )

    except Exception as e:
        logger.error(f"Error getting action counts: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/action/commitments/{action_id:path}", response_model=list[ActionResponse])
async def list_commitments(action_id: str):
    """
    List all commitments for an action.

    Returns non-revoked commitments only.
    """
    storage = _get_action_storage()
    if not storage:
        return []

    try:
        from civicos_relay.voice.action_service import ActionService

        service = ActionService(storage)
        commitments = service.get_commitments(action_id)

        return [
            ActionResponse(
                action_id=c.action_id,
                action_type=c.action_type.value,
                public_key=c.public_key,
                signature=c.signature,
                timestamp=c.timestamp.isoformat(),
                revoked=c.revoked,
            )
            for c in commitments
        ]

    except Exception as e:
        logger.error(f"Error listing commitments: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/action/completions/{action_id:path}", response_model=list[ActionResponse])
async def list_completions(action_id: str):
    """
    List all completions for an action.

    Returns non-revoked completions only.
    """
    storage = _get_action_storage()
    if not storage:
        return []

    try:
        from civicos_relay.voice.action_service import ActionService

        service = ActionService(storage)
        completions = service.get_completions(action_id)

        return [
            ActionResponse(
                action_id=c.action_id,
                action_type=c.action_type.value,
                public_key=c.public_key,
                signature=c.signature,
                timestamp=c.timestamp.isoformat(),
                evidence_url=c.evidence_url,
                revoked=c.revoked,
            )
            for c in completions
        ]

    except Exception as e:
        logger.error(f"Error listing completions: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Civic Action Event Endpoints (Kind 30810/30811/30812) ===


@router.post("/coordination/civic-action", response_model=CivicActionEventResponse)
async def create_civic_action_event(request: CreateCivicActionEventRequest):
    """
    Create a new civic action event (Kind 30810).

    Action events define reusable actions that users can commit to and complete.
    They are addressable Nostr events that can be federated to other relays.

    The action must be cryptographically signed by the creator.
    """
    service = _get_civic_action_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Civic action service not configured"
        )

    try:
        from civicos_relay.voice.models import CivicActionType

        # Validate action type
        try:
            action_type = CivicActionType(request.action_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action_type: {request.action_type}. Must be one of: "
                       "written_comment, attend_meeting, public_comment, contact_official, "
                       "signature, share, custom"
            )

        # Parse deadline if provided
        deadline = None
        if request.deadline:
            deadline = datetime.fromisoformat(request.deadline)

        action = service.create_action(
            initiative_id=request.initiative_id,
            action_type=action_type,
            description=request.description,
            public_key=request.public_key,
            signature=request.signature,
            target=request.target,
            deadline=deadline,
            template=request.template,
            target_count=request.target_count,
        )

        logger.info(f"Civic action created: {action.id} for initiative {request.initiative_id}")

        return CivicActionEventResponse(
            id=action.id,
            initiative_id=action.initiative_id,
            action_type=action.action_type.value,
            description=action.description,
            target=action.target,
            deadline=action.deadline.isoformat() if action.deadline else None,
            template=action.template,
            target_count=action.target_count,
            public_key=action.public_key,
            timestamp=action.timestamp.isoformat(),
            revoked=action.revoked,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating civic action: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/civic-actions/{initiative_id:path}",
    response_model=list[CivicActionEventResponse],
)
async def list_civic_actions_for_initiative(initiative_id: str):
    """
    List all civic action events for an initiative.

    Returns non-revoked actions only.
    """
    service = _get_civic_action_service()
    if not service:
        return []

    try:
        actions = service.get_actions_for_initiative(initiative_id)

        return [
            CivicActionEventResponse(
                id=a.id,
                initiative_id=a.initiative_id,
                action_type=a.action_type.value,
                description=a.description,
                target=a.target,
                deadline=a.deadline.isoformat() if a.deadline else None,
                template=a.template,
                target_count=a.target_count,
                public_key=a.public_key,
                timestamp=a.timestamp.isoformat(),
                revoked=a.revoked,
            )
            for a in actions
        ]

    except Exception as e:
        logger.error(f"Error listing civic actions: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/civic-action/{action_id:path}",
    response_model=CivicActionEventResponse,
)
async def get_civic_action_event(action_id: str):
    """
    Get a specific civic action event by ID.

    Returns 404 if action not found.
    """
    service = _get_civic_action_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Civic action service not configured"
        )

    try:
        action = service.get_action(action_id)

        if not action:
            raise HTTPException(status_code=404, detail="Action not found")

        return CivicActionEventResponse(
            id=action.id,
            initiative_id=action.initiative_id,
            action_type=action.action_type.value,
            description=action.description,
            target=action.target,
            deadline=action.deadline.isoformat() if action.deadline else None,
            template=action.template,
            target_count=action.target_count,
            public_key=action.public_key,
            timestamp=action.timestamp.isoformat(),
            revoked=action.revoked,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting civic action: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/civic-action/{action_id:path}/progress",
    response_model=CivicActionProgressResponse,
)
async def get_civic_action_progress(action_id: str):
    """
    Get progress (commitments, completions, target) for a civic action.
    """
    service = _get_civic_action_service()
    if not service:
        # Graceful degradation
        return CivicActionProgressResponse(
            action_id=action_id,
            commitment_count=0,
            completion_count=0,
        )

    try:
        progress = service.get_action_progress(action_id)

        return CivicActionProgressResponse(
            action_id=progress.action_id,
            commitment_count=progress.commitment_count,
            completion_count=progress.completion_count,
            target_count=progress.target_count,
            progress_percent=progress.progress_percent,
        )

    except Exception as e:
        logger.error(f"Error getting civic action progress: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post(
    "/coordination/civic-action/{action_id:path}/commit",
    response_model=CivicCommitmentResponse,
)
async def commit_to_civic_action(action_id: str, request: CivicCommitmentRequest):
    """
    Commit to a civic action (Kind 30811).

    Records the user's commitment to take the specified action.
    If the user has already committed, the old commitment is replaced.

    The commitment must be cryptographically signed.
    """
    service = _get_civic_action_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Civic action service not configured"
        )

    try:
        from civicos_relay.voice.crypto import verify_signature

        # Verify signature
        message = f"civicos:commitment:v1:{action_id}"
        if not verify_signature(request.public_key, request.signature, message):
            raise HTTPException(
                status_code=400,
                detail="Invalid commitment signature"
            )

        commitment = service.commit_to_action(
            action_id=action_id,
            public_key=request.public_key,
            signature=request.signature,
        )

        logger.info(f"Commitment created for action {action_id} by {request.public_key[:16]}...")

        return CivicCommitmentResponse(
            id=commitment.id,
            action_ref=commitment.action_ref,
            status=commitment.status.value,
            public_key=commitment.public_key,
            timestamp=commitment.timestamp.isoformat(),
            revoked=commitment.revoked,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error committing to civic action: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post(
    "/coordination/civic-action/{action_id:path}/complete",
    response_model=CivicCompletionResponse,
)
async def complete_civic_action(action_id: str, request: CivicCompletionRequest):
    """
    Complete a civic action with evidence (Kind 30812).

    Records the user's completion of the action with optional evidence.
    If the user has already completed, the old completion is replaced.
    Also updates the commitment status to COMPLETED if one exists.

    The completion must be cryptographically signed.
    """
    service = _get_civic_action_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Civic action service not configured"
        )

    try:
        from civicos_relay.voice.crypto import verify_signature
        from civicos_relay.voice.models import EvidenceType

        # Validate evidence type
        try:
            evidence_type = EvidenceType(request.evidence_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid evidence_type: {request.evidence_type}. Must be one of: "
                       "self_report, email_confirmation, attendance_check, verified"
            )

        # Verify signature
        message = f"civicos:completion:v1:{action_id}:{evidence_type.value}"
        if not verify_signature(request.public_key, request.signature, message):
            raise HTTPException(
                status_code=400,
                detail="Invalid completion signature"
            )

        completion = service.complete_action(
            action_id=action_id,
            public_key=request.public_key,
            signature=request.signature,
            evidence_type=evidence_type,
            evidence_content=request.evidence_content,
        )

        logger.info(f"Completion created for action {action_id} by {request.public_key[:16]}...")

        return CivicCompletionResponse(
            id=completion.id,
            action_ref=completion.action_ref,
            evidence_type=completion.evidence_type.value,
            evidence_content=completion.evidence_content,
            completed_at=completion.completed_at.isoformat(),
            public_key=completion.public_key,
            timestamp=completion.timestamp.isoformat(),
            revoked=completion.revoked,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error completing civic action: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/civic-action/{action_id:path}/commitments",
    response_model=list[CivicCommitmentResponse],
)
async def list_civic_action_commitments(action_id: str):
    """
    List all commitments for a civic action.

    Returns non-revoked commitments only.
    """
    service = _get_civic_action_service()
    if not service:
        return []

    try:
        commitments = service.get_commitments_for_action(action_id)

        return [
            CivicCommitmentResponse(
                id=c.id,
                action_ref=c.action_ref,
                status=c.status.value,
                public_key=c.public_key,
                timestamp=c.timestamp.isoformat(),
                revoked=c.revoked,
            )
            for c in commitments
        ]

    except Exception as e:
        logger.error(f"Error listing civic action commitments: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/civic-action/{action_id:path}/completions",
    response_model=list[CivicCompletionResponse],
)
async def list_civic_action_completions(action_id: str):
    """
    List all completions for a civic action.

    Returns non-revoked completions only.
    """
    service = _get_civic_action_service()
    if not service:
        return []

    try:
        completions = service.get_completions_for_action(action_id)

        return [
            CivicCompletionResponse(
                id=c.id,
                action_ref=c.action_ref,
                evidence_type=c.evidence_type.value,
                evidence_content=c.evidence_content,
                completed_at=c.completed_at.isoformat(),
                public_key=c.public_key,
                timestamp=c.timestamp.isoformat(),
                revoked=c.revoked,
            )
            for c in completions
        ]

    except Exception as e:
        logger.error(f"Error listing civic action completions: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Comment Endpoints (Kind 30803) ===


@router.post("/coordination/comment", response_model=CommentResponse)
async def submit_comment(request: SubmitCommentRequest):
    """
    Submit a signed public comment on a civic entity.

    Comments are Nostr Kind 30803 events. The comment text is the event content.
    One comment per public_key per entity (upsert).
    """
    storage = _get_comment_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Comment service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        from civicos_relay.voice.models import Comment
        from civicos_relay.voice.crypto import verify_comment

        comment = Comment(
            entity=request.entity,
            comment_text=request.comment_text,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
            jurisdiction=request.jurisdiction,
            stance=request.stance,
        )

        if not verify_comment(comment):
            raise HTTPException(status_code=400, detail="Invalid comment signature")

        storage.save_comment(comment)

        return CommentResponse(
            entity=comment.entity,
            comment_text=comment.comment_text,
            public_key=comment.public_key,
            signature=comment.signature,
            timestamp=comment.timestamp.isoformat(),
            jurisdiction=comment.jurisdiction,
            stance=comment.stance,
            deleted=comment.deleted,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting comment: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/comments/{entity:path}", response_model=list[CommentResponse])
async def list_comments(entity: str):
    """
    List non-deleted comments for an entity, newest first.
    """
    storage = _get_comment_storage()
    if not storage:
        return []

    try:
        comments = storage.get_comments_for_entity(entity)
        return [
            CommentResponse(
                entity=c.entity,
                comment_text=c.comment_text,
                public_key=c.public_key,
                signature=c.signature,
                timestamp=c.timestamp.isoformat(),
                jurisdiction=c.jurisdiction,
                stance=c.stance,
                deleted=c.deleted,
            )
            for c in comments
        ]

    except Exception as e:
        logger.error(f"Error listing comments: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/comment/counts/{entity:path}", response_model=CommentCountResponse)
async def get_comment_counts(entity: str):
    """
    Get comment count for an entity.
    """
    storage = _get_comment_storage()
    if not storage:
        return CommentCountResponse(entity=entity, count=0)

    try:
        count = storage.get_comment_count(entity)
        return CommentCountResponse(entity=entity, count=count)

    except Exception as e:
        logger.error(f"Error getting comment counts: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
