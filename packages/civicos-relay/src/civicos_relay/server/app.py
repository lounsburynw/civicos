"""FastAPI application for relay server."""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from civicos_relay.identity import RelayIdentity, RelayConfig
from civicos_relay.voice.models import Voice, Stance, VoiceCount, Action, ActionType, ActionCount, Comment, CommentCount, CivicActionEvent, CivicActionType, CivicCommitment, CivicCompletion, CivicActionProgress, EvidenceType
from civicos_relay.voice.service import VoiceService
from civicos_relay.voice.action_service import ActionService
from civicos_relay.voice.civic_action_service import CivicActionService
from civicos_relay.voice.crypto import KeyPair, sign_voice, verify_comment, verify_commitment, verify_completion, verify_withdrawal, verify_action_event, verify_initiative
from civicos_relay.relay.models import Initiative, InitiativeStatus
from civicos_relay.relay.models import Subscription, MatchCriteria, DeliveryConfig, DeliveryMethod
from civicos_relay.relay.service import RelayService
from civicos_relay.provenance.models import KeyProvenance
from civicos_relay.provenance.service import ProvenanceService
from civicos_relay.sync.protocol import SyncRequest, VoiceSyncResponse, VoiceImportRequest, VoiceImportResponse
from civicos_relay.sync.service import SyncService
from civicos_relay.storage import InMemoryStorage, PostgresStorage
from civicos_relay.delivery import EmailDelivery, EmailConfig
from civicos_relay.attestation.service import AttestationService
from civicos_relay.attestation.signer_client import SignerError
from civicos_relay.server.acceptance import AcceptancePolicy
from civicos_relay.server.ip_rate_limit import IPRateLimitMiddleware, DEFAULT_IP_RATE_LIMIT, DEFAULT_IP_RATE_WINDOW

logger = logging.getLogger(__name__)


# Request/Response models for API
class CastVoiceRequest(BaseModel):
    """Request to cast a voice (signed Nostr event fields)."""
    entity: str
    stance: Stance
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction code for Nostr tag reconstruction")
    attestation_proof: Optional[dict] = None
    payment_proof: Optional[dict] = None
    event_id: Optional[str] = Field(default=None, description="Nostr event ID for NIP-13 proof-of-work verification")


class CommitActionRequest(BaseModel):
    """Request to commit to an action."""
    action_id: str
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")


class CompleteActionRequest(BaseModel):
    """Request to mark an action as completed."""
    action_id: str
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    evidence_url: Optional[str] = None


class CreateInitiativeRequest(BaseModel):
    """Request to create an initiative."""
    jurisdiction: str
    topic: str
    title: str
    description: str
    location: Optional[str] = None
    coordination_url: Optional[str] = None
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    attestation_proof: Optional[dict] = None
    payment_proof: Optional[dict] = None


class CreateCivicActionRequest(BaseModel):
    """Request to create a civic action (Kind 30810)."""
    initiative_id: str
    action_type: str
    description: str
    target: Optional[str] = None
    deadline: Optional[str] = None
    template: Optional[str] = None
    target_count: Optional[int] = None
    coordination_url: Optional[str] = None
    deadline_context: Optional[str] = None
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")


class CivicCommitRequest(BaseModel):
    """Request to commit to a civic action (Kind 30811)."""
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    jurisdiction: str = Field(description="Jurisdiction code for Nostr tag reconstruction")


class CivicCompleteRequest(BaseModel):
    """Request to complete a civic action (Kind 30812)."""
    public_key: str
    signature: str
    evidence_type: str = "self_report"
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    jurisdiction: str = Field(description="Jurisdiction code for Nostr tag reconstruction")


class CivicWithdrawRequest(BaseModel):
    """Request to withdraw a civic action commitment."""
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")


class SubmitCommentRequest(BaseModel):
    """Request to submit a public comment."""
    entity: str
    comment_text: str
    public_key: str
    signature: str
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    jurisdiction: Optional[str] = None
    stance: Optional[str] = None
    attestation_proof: Optional[dict] = None
    payment_proof: Optional[dict] = None
    event_id: Optional[str] = Field(default=None, description="Nostr event ID for NIP-13 proof-of-work verification")


class SubscribeRequest(BaseModel):
    """Request to create a subscription."""
    jurisdiction: str
    topics: Optional[list[str]] = None
    event_types: Optional[list[str]] = None
    email: Optional[str] = None
    webhook_url: Optional[str] = None


class RedeemCodeRequest(BaseModel):
    """Request to redeem an attestation code."""
    code: str = Field(description="Attestation code (e.g., SR-2026-02-A7K9)")
    subject_pubkey: str = Field(description="Resident's public key (hex)")
    signature: str = Field(description="Kind-24242 signature proving pubkey ownership")
    created_at: int = Field(description="Unix timestamp from signed event")


class CodeBatchRequest(BaseModel):
    """Issuer-signed batch of attestation codes."""
    signed_event: dict = Field(description="Kind-30851 Nostr event signed by issuer")


class RegisterIssuerRequest(BaseModel):
    """Request to register a trusted issuer."""
    issuer_pubkey: str = Field(description="Issuer's public key (64-char hex)")
    jurisdiction: str
    organization: str
    signing_url: str = Field(description="URL of the issuer's signing service")
    bearer_token: str = Field(description="Shared secret for authenticating with signer")
    allowed_types: list[str] = Field(default=["physical"])


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


def get_action_service() -> ActionService:
    return _relay_state["action_service"]


def get_comment_storage():
    return _relay_state["comment_storage"]


def get_initiative_storage():
    return _relay_state["initiative_storage"]


def get_civic_action_service() -> CivicActionService:
    return _relay_state["civic_action_service"]


def get_identity() -> RelayIdentity:
    return _relay_state["identity"]


def get_attestation_service() -> AttestationService:
    return _relay_state["attestation_service"]


def get_acceptance_policy() -> Optional[AcceptancePolicy]:
    return _relay_state.get("acceptance_policy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    config = RelayConfig.from_env()
    identity = RelayIdentity.load_or_generate(
        config.relay_id,
        config.private_key_path,
    )

    # RELAY_DATABASE_URL overrides DATABASE_URL (for separate relay DB)
    relay_db_url = os.environ.get("RELAY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if relay_db_url:
        storage = PostgresStorage(relay_db_url)
        logger.info("Relay storage: PostgreSQL")
    else:
        storage = InMemoryStorage()
        logger.info("Relay storage: in-memory (set RELAY_DATABASE_URL for persistence)")

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
    _relay_state["action_service"] = ActionService(storage.actions)
    _relay_state["relay_service"] = RelayService(storage.subscriptions, email_delivery)
    _relay_state["provenance_service"] = ProvenanceService(storage.provenance)
    _relay_state["sync_service"] = SyncService(identity, storage.sync, config.peers)
    _relay_state["comment_storage"] = storage.comments
    _relay_state["initiative_storage"] = storage.initiatives
    _relay_state["attestation_service"] = AttestationService(
        attestation_storage=storage.attestations,
        issuer_storage=storage.issuers,
    )
    _relay_state["civic_action_service"] = CivicActionService(
        action_storage=storage.civic_action_events,
        commitment_storage=storage.civic_commitments,
        completion_storage=storage.civic_completions,
        outcome_storage=getattr(storage, 'outcomes', None),
        attribution_storage=getattr(storage, 'attributions', None),
    )

    # Initialize acceptance policy if enabled
    if config.acceptance_policy_enabled:
        issuer_storage = storage.issuers

        def issuer_lookup(jurisdiction: str) -> Optional[str]:
            """Look up trusted issuer pubkey for a jurisdiction."""
            issuers = issuer_storage.get_issuers_for_jurisdiction(jurisdiction)
            for issuer in issuers:
                if issuer.get("verified") and not issuer.get("revoked"):
                    return issuer["issuer_pubkey"]
            return None

        policy = AcceptancePolicy(
            connection_url=relay_db_url,
            issuer_lookup=issuer_lookup,
        )
        policy.cleanup_old_limits()
        _relay_state["acceptance_policy"] = policy
        logger.info("Acceptance policy enabled (with attestation verification)")

    if config.sync_enabled:
        await _relay_state["sync_service"].start()

    logger.info(f"Relay started: {identity.relay_id}")

    yield

    # Shutdown
    await _relay_state["sync_service"].stop()
    logger.info("Relay stopped")


_CLOCK_SKEW_TOLERANCE = 300  # 5 minutes


def _check_created_at(created_at: int) -> None:
    """Reject writes with timestamps too far from server time (clock skew protection)."""
    now = int(time.time())
    drift = abs(now - created_at)
    if drift > _CLOCK_SKEW_TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail=f"created_at timestamp is {drift}s from server time (max {_CLOCK_SKEW_TOLERANCE}s)",
        )


def _check_acceptance(event_type: str, public_key: str, entity: str,
                      attestation_proof=None, payment_proof=None,
                      event_id: Optional[str] = None):
    """Check acceptance policy for a write event. No-op if policy is disabled."""
    policy = get_acceptance_policy()
    if policy is None:
        return
    result = policy.check(event_type, public_key, attestation_proof, payment_proof, event_id=event_id)
    if not result.accepted:
        raise HTTPException(status_code=402, detail=result.to_dict())
    policy._record_metadata(public_key, entity, result.tier)


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="CivicOS Relay",
        description="Federation-ready civic coordination relay",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # HTTP-level per-IP rate limiting (runs before crypto verification)
    # Clamp to sane bounds: 10-1000 requests, 60s-1h window
    ip_limit = max(10, min(1000, int(os.environ.get("RELAY_IP_RATE_LIMIT", str(DEFAULT_IP_RATE_LIMIT)))))
    ip_window = max(60, min(3600, int(os.environ.get("RELAY_IP_RATE_WINDOW", str(DEFAULT_IP_RATE_WINDOW)))))
    app.add_middleware(IPRateLimitMiddleware, max_requests=ip_limit, window_seconds=ip_window)

    # Health on root (not behind /coordination)
    @app.get("/health", response_model=HealthResponse)
    async def health(identity: RelayIdentity = Depends(get_identity)):
        return HealthResponse(status="healthy", relay_id=identity.relay_id)

    # All coordination endpoints under /coordination prefix
    router = APIRouter(prefix="/coordination")

    @router.post("/voice", response_model=Voice)
    async def cast_voice(
        request: CastVoiceRequest,
        voice_service: VoiceService = Depends(get_voice_service),
        provenance_service: ProvenanceService = Depends(get_provenance_service),
    ):
        """Cast a voice on an entity."""
        _check_created_at(request.created_at)

        # Create voice from signed Nostr event fields
        voice = Voice(
            entity=request.entity,
            stance=request.stance,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
            jurisdiction=request.jurisdiction,
        )

        # Verify and store
        if not voice_service.verify(voice):
            raise HTTPException(status_code=400, detail="Invalid voice signature")

        _check_acceptance("voice", request.public_key, request.entity,
                          request.attestation_proof, request.payment_proof,
                          event_id=request.event_id)

        # Check for existing voice and handle
        existing = voice_service._storage.get_voice(request.public_key, request.entity)
        if existing and not existing.revoked:
            voice_service._storage.revoke_voice(request.public_key, request.entity)

        voice_service._storage.save_voice(voice)

        # Update provenance
        provenance_service.record_voice(voice)

        return voice

    @router.get("/voice/counts/{entity:path}", response_model=VoiceCount)
    async def get_voice_counts(
        entity: str,
        voice_service: VoiceService = Depends(get_voice_service),
    ):
        """Get voice counts for an entity."""
        return voice_service.get_counts(entity)

    @router.get("/voice/{entity:path}", response_model=list[Voice])
    async def list_voices(
        entity: str,
        voice_service: VoiceService = Depends(get_voice_service),
    ):
        """List all voices for an entity."""
        return voice_service._storage.get_voices_for_entity(entity)

    # Action endpoints (commitments and completions)
    @router.post("/action/commit", response_model=Action)
    async def commit_action(
        request: CommitActionRequest,
        action_service: ActionService = Depends(get_action_service),
    ):
        """Commit to taking a civic action."""
        _check_created_at(request.created_at)

        # Create action from request
        action = Action(
            action_id=request.action_id,
            action_type=ActionType.COMMITMENT,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
        )

        # Verify signature
        if not action_service.verify(action):
            raise HTTPException(status_code=400, detail="Invalid action signature")

        # Record commitment
        return action_service.record_commitment(
            action_id=request.action_id,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
        )

    @router.post("/action/complete", response_model=Action)
    async def complete_action(
        request: CompleteActionRequest,
        action_service: ActionService = Depends(get_action_service),
    ):
        """Mark a civic action as completed."""
        _check_created_at(request.created_at)

        # Create action from request
        action = Action(
            action_id=request.action_id,
            action_type=ActionType.COMPLETION,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
            evidence_url=request.evidence_url,
        )

        # Verify signature
        if not action_service.verify(action):
            raise HTTPException(status_code=400, detail="Invalid action signature")

        # Record completion
        return action_service.record_completion(
            action_id=request.action_id,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
            evidence_url=request.evidence_url,
        )

    @router.get("/action/counts/{action_id:path}", response_model=ActionCount)
    async def get_action_counts(
        action_id: str,
        target: Optional[int] = None,
        action_service: ActionService = Depends(get_action_service),
    ):
        """Get commitment and completion counts for an action."""
        return action_service.get_counts(action_id, target)

    @router.get("/action/commitments/{action_id:path}", response_model=list[Action])
    async def list_commitments(
        action_id: str,
        action_service: ActionService = Depends(get_action_service),
    ):
        """List all commitments for an action."""
        return action_service.get_commitments(action_id)

    @router.get("/action/completions/{action_id:path}", response_model=list[Action])
    async def list_completions(
        action_id: str,
        action_service: ActionService = Depends(get_action_service),
    ):
        """List all completions for an action."""
        return action_service.get_completions(action_id)

    # Comment endpoints (public comment board)
    @router.post("/comment", response_model=Comment)
    async def submit_comment(
        request: SubmitCommentRequest,
        comment_storage=Depends(get_comment_storage),
    ):
        """Submit a signed public comment on an entity."""
        _check_created_at(request.created_at)

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

        _check_acceptance("comment", request.public_key, request.entity,
                          request.attestation_proof, request.payment_proof,
                          event_id=request.event_id)

        comment_storage.save_comment(comment)
        return comment

    @router.get("/comments/{entity:path}", response_model=list[Comment])
    async def list_comments(
        entity: str,
        comment_storage=Depends(get_comment_storage),
    ):
        """List non-deleted comments for an entity."""
        return comment_storage.get_comments_for_entity(entity)

    @router.get("/comment/counts/{entity:path}", response_model=CommentCount)
    async def get_comment_counts(
        entity: str,
        comment_storage=Depends(get_comment_storage),
    ):
        """Get comment count for an entity."""
        count = comment_storage.get_comment_count(entity)
        return CommentCount(entity=entity, count=count)

    # Subscription endpoints
    @router.post("/subscribe", response_model=Subscription)
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

    @router.delete("/subscribe/{subscription_id}")
    async def unsubscribe(
        subscription_id: str,
        relay_service: RelayService = Depends(get_relay_service),
    ):
        """Unsubscribe from notifications."""
        if not relay_service.unsubscribe(subscription_id):
            raise HTTPException(status_code=404, detail="Subscription not found")
        return {"status": "unsubscribed"}

    # Provenance endpoints
    @router.get("/provenance/{public_key}", response_model=Optional[KeyProvenance])
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
    @router.get("/sync/voices", response_model=VoiceSyncResponse)
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

    @router.post("/sync/voices", response_model=VoiceImportResponse)
    async def import_voices(
        request: VoiceImportRequest,
        sync_service: SyncService = Depends(get_sync_service),
    ):
        """Import voices from a peer relay."""
        return sync_service.import_voices(request)

    # Initiative endpoints
    @router.post("/initiative", response_model=Initiative)
    async def create_initiative(
        request: CreateInitiativeRequest,
        initiative_storage=Depends(get_initiative_storage),
    ):
        """Create a community initiative (signed by creator)."""
        _check_created_at(request.created_at)

        import hashlib
        from datetime import datetime

        if not verify_initiative(
            request.public_key, request.signature,
            request.jurisdiction, request.topic, request.created_at,
        ):
            raise HTTPException(status_code=400, detail="Invalid initiative signature")

        _check_acceptance("initiative", request.public_key,
                          f"initiative:{request.jurisdiction}:{request.topic}",
                          request.attestation_proof, request.payment_proof)

        # Generate initiative ID
        desc_hash = hashlib.sha256(request.description.encode()).hexdigest()[:8]
        date_str = datetime.utcnow().strftime("%Y%m%d")
        initiative_id = f"initiative:{request.jurisdiction}:{date_str}:{desc_hash}"

        initiative = Initiative(
            id=initiative_id,
            jurisdiction=request.jurisdiction,
            topic=request.topic,
            title=request.title,
            description=request.description,
            location=request.location,
            coordination_url=request.coordination_url,
            public_key=request.public_key,
            signature=request.signature,
        )

        initiative_storage.save_initiative(initiative)
        return initiative

    @router.get("/initiatives/{jurisdiction}")
    async def list_initiatives(
        jurisdiction: str,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        initiative_storage=Depends(get_initiative_storage),
    ):
        """List initiatives for a jurisdiction."""
        initiatives = initiative_storage.get_initiatives_for_jurisdiction(
            jurisdiction, topic=topic, status=status, limit=limit
        )
        return {"initiatives": initiatives}

    @router.get("/initiative/{initiative_id:path}")
    async def get_initiative(
        initiative_id: str,
        initiative_storage=Depends(get_initiative_storage),
    ):
        """Get initiative details."""
        initiative = initiative_storage.get_initiative(initiative_id)
        if not initiative:
            raise HTTPException(status_code=404, detail="Initiative not found")
        return initiative

    # Civic Action endpoints (Kind 30810/30811/30812)
    @router.post("/civic-action", response_model=CivicActionEvent)
    async def create_civic_action(
        request: CreateCivicActionRequest,
        civic_service: CivicActionService = Depends(get_civic_action_service),
    ):
        """Create a civic action (Kind 30810)."""
        _check_created_at(request.created_at)

        from datetime import datetime

        if not verify_action_event(
            request.public_key, request.signature,
            request.initiative_id, request.action_type, request.created_at,
        ):
            raise HTTPException(status_code=403, detail="Invalid action event signature")

        _check_acceptance("action_create", request.public_key,
                          f"action:{request.initiative_id}:{request.action_type}")

        deadline = None
        if request.deadline:
            try:
                deadline = datetime.fromisoformat(request.deadline)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid deadline format")

        action = civic_service.create_action(
            initiative_id=request.initiative_id,
            action_type=CivicActionType(request.action_type),
            description=request.description,
            public_key=request.public_key,
            signature=request.signature,
            target=request.target,
            deadline=deadline,
            template=request.template,
            target_count=request.target_count,
            deadline_context=request.deadline_context,
            coordination_url=request.coordination_url,
        )
        return action

    @router.get("/civic-actions/{initiative_id:path}")
    async def list_civic_actions(
        initiative_id: str,
        civic_service: CivicActionService = Depends(get_civic_action_service),
    ):
        """List civic actions for an initiative."""
        actions = civic_service.get_actions_for_initiative(initiative_id)
        return {"actions": actions}

    @router.get("/civic-action/{action_id:path}/progress", response_model=CivicActionProgress)
    async def get_civic_action_progress(
        action_id: str,
        civic_service: CivicActionService = Depends(get_civic_action_service),
    ):
        """Get progress for a civic action."""
        return civic_service.get_action_progress(action_id)

    @router.post("/civic-action/{action_id:path}/commit")
    async def commit_civic_action(
        action_id: str,
        request: CivicCommitRequest,
        civic_service: CivicActionService = Depends(get_civic_action_service),
    ):
        """Commit to a civic action (Kind 30811)."""
        _check_created_at(request.created_at)

        if not verify_commitment(
            request.public_key, request.signature,
            action_id, request.jurisdiction, request.created_at,
        ):
            raise HTTPException(status_code=403, detail="Invalid commitment signature")

        _check_acceptance("action_commit", request.public_key, action_id)

        try:
            commitment = civic_service.commit_to_action(
                action_id=action_id,
                public_key=request.public_key,
                signature=request.signature,
            )
            return commitment
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/civic-action/{action_id:path}/complete")
    async def complete_civic_action(
        action_id: str,
        request: CivicCompleteRequest,
        civic_service: CivicActionService = Depends(get_civic_action_service),
    ):
        """Complete a civic action (Kind 30812)."""
        _check_created_at(request.created_at)

        if not verify_completion(
            request.public_key, request.signature,
            action_id, request.jurisdiction, request.created_at,
        ):
            raise HTTPException(status_code=403, detail="Invalid completion signature")

        _check_acceptance("action_complete", request.public_key, action_id)

        try:
            completion = civic_service.complete_action(
                action_id=action_id,
                public_key=request.public_key,
                signature=request.signature,
                evidence_type=EvidenceType(request.evidence_type),
            )
            return completion
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/civic-action/{action_id:path}/withdraw")
    async def withdraw_civic_action(
        action_id: str,
        request: CivicWithdrawRequest,
        civic_service: CivicActionService = Depends(get_civic_action_service),
    ):
        """Withdraw commitment to a civic action."""
        _check_created_at(request.created_at)

        if not verify_withdrawal(
            request.public_key, request.signature,
            action_id, request.created_at,
        ):
            raise HTTPException(status_code=403, detail="Invalid withdrawal signature")

        _check_acceptance("action_complete", request.public_key, action_id)

        success = civic_service.withdraw_commitment(action_id, request.public_key)
        if not success:
            raise HTTPException(status_code=404, detail="Commitment not found")
        return {"status": "withdrawn"}

    # --- Attestation endpoints ---

    def _verify_relay_api_key(authorization: str):
        """Verify relay admin API key from Authorization header."""
        relay_api_key = os.environ.get("CIVICOS_RELAY_API_KEY", "")
        provided = authorization.removeprefix("Bearer ").strip() if authorization else ""
        if not provided or provided != relay_api_key:
            raise HTTPException(status_code=401, detail="Invalid relay API key")

    @router.post("/attestation/redeem")
    async def redeem_attestation_code(
        request: RedeemCodeRequest,
        attestation_service: AttestationService = Depends(get_attestation_service),
    ):
        """Redeem an attestation code."""
        _check_created_at(request.created_at)

        try:
            attestation_event = attestation_service.redeem_code(
                code=request.code,
                subject_pubkey=request.subject_pubkey,
                signature=request.signature,
                created_at=request.created_at,
            )
            return {"attestation_event": attestation_event}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except SignerError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @router.post("/codes/batch")
    async def accept_code_batch(
        request: CodeBatchRequest,
        attestation_service: AttestationService = Depends(get_attestation_service),
    ):
        """Accept a batch of issuer-signed attestation codes.

        No admin API key required — authorization is cryptographic.
        The signed_event must be a valid kind-30851 Nostr event signed by
        a registered and verified issuer's private key.
        """
        try:
            result = attestation_service.accept_code_batch(request.signed_event)
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/issuers/register")
    async def register_issuer(
        request: RegisterIssuerRequest,
        authorization: str = Header(default=""),
    ):
        """Register a trusted issuer for a jurisdiction."""
        _verify_relay_api_key(authorization)
        attestation_service = get_attestation_service()
        try:
            result = attestation_service.register_issuer(request.model_dump())
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    app.include_router(router)
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
