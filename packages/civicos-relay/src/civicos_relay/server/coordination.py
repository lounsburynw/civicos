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
- POST /coordination/feedback - Submit feedback (signed, rate-limited)
- GET /coordination/feedback - Query feedback (admin only)
"""

import os
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from civicos_relay.voice.crypto import (
    verify_action_event,
    verify_comment,
    verify_commitment,
    verify_completion,
    verify_feedback,
    verify_initiative,
    verify_signature,
    verify_voice,
    verify_withdrawal,
    verify_attestation_proof,
    verify_attestation_request,
    sign_attestation_event,
    KeyPair,
    _compute_nostr_event_id,
    _schnorr_verify,
)
from civicos_relay.voice.models import (
    CivicActionType,
    Comment,
    EvidenceType,
    Feedback,
    OutcomeType,
    Stance,
    Voice,
)

logger = logging.getLogger(__name__)

_CLOCK_SKEW_TOLERANCE = 300  # 5 minutes


def _default_jurisdiction() -> str:
    """Get default jurisdiction from environment. Never hardcode a specific city."""
    return os.environ.get("CIVICOS_JURISDICTION", "city-san-rafael")


def _check_created_at(created_at: int) -> None:
    """Reject writes with timestamps too far from server time (clock skew protection)."""
    now = int(time.time())
    drift = abs(now - created_at)
    if drift > _CLOCK_SKEW_TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail=f"created_at timestamp is {drift}s from server time (max {_CLOCK_SKEW_TOLERANCE}s)",
        )

router = APIRouter()


# === Pydantic Request/Response Models ===

class CastVoiceRequest(BaseModel):
    """Request to cast a voice (signed by client)."""
    entity: str = Field(description="Namespaced entity identifier")
    stance: str = Field(description="Position: support, oppose, or watching")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of entity+stance (hex-encoded)")
    created_at: int = Field(description="Unix timestamp from the signed Nostr event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction code for Nostr event reconstruction")
    attestation_proof: Optional[dict] = Field(default=None, description="Full kind-30850 Nostr event signed by jurisdiction issuer")
    payment_proof: Optional[dict] = Field(default=None, description="Blinded token {message, signature, issuer_pubkey}")


class VoiceResponse(BaseModel):
    """Voice record response."""
    entity: str
    stance: str
    public_key: str
    signature: str
    timestamp: str
    revoked: bool = False
    created_at: Optional[int] = None
    jurisdiction: Optional[str] = None
    attestation_proof: Optional[dict] = None


class VoiceCountResponse(BaseModel):
    """Voice counts for an entity."""
    entity: str
    support: int = 0
    oppose: int = 0
    watching: int = 0
    total: int = 0
    attested: Optional[int] = None
    unattested: Optional[int] = None


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
    coordination_url: Optional[str] = Field(default=None, description="Optional link to coordination channel (Signal, SimpleX, Matrix)")
    public_key: str = Field(description="Creator's public key (hex-encoded)")
    signature: str = Field(description="Signature of initiative data (hex-encoded)")
    created_at: int = Field(description="Unix timestamp from signed message")


class InitiativeResponse(BaseModel):
    """Initiative record response."""
    id: str
    jurisdiction: str
    topic: str
    title: str
    description: str
    location: Optional[str] = None
    coordination_url: Optional[str] = None
    public_key: str
    timestamp: str
    status: str
    voice_count: int = 0
    creator_attested: Optional[bool] = None
    attested_voice_count: Optional[int] = None


# === Action Request/Response Models ===

class CommitActionRequest(BaseModel):
    """Request to commit to an action (signed by client)."""
    action_id: str = Field(description="Action identifier")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of action commitment (hex-encoded)")
    created_at: int = Field(description="Unix timestamp from signed event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction for signature verification")


class CompleteActionRequest(BaseModel):
    """Request to mark an action complete (signed by client)."""
    action_id: str = Field(description="Action identifier")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of action completion (hex-encoded)")
    evidence_url: Optional[str] = Field(default=None, description="URL to evidence")
    created_at: int = Field(description="Unix timestamp from signed event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction for signature verification")


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
    deadline_context: Optional[str] = Field(default=None, description="Why this deadline matters")
    coordination_url: Optional[str] = Field(default=None, description="Link to coordination channel (Signal, SimpleX, Matrix)")
    created_at: int = Field(description="Unix timestamp when the action was created (required for signature verification)")


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
    deadline_context: Optional[str] = None
    coordination_url: Optional[str] = None
    public_key: str
    timestamp: str
    revoked: bool = False


class CivicCommitmentRequest(BaseModel):
    """Request to commit to a civic action (Kind 30811)."""
    action_id: str = Field(default="", description="ID of the action event (may also come from URL path)")
    public_key: str = Field(description="Committer's public key (hex-encoded)")
    signature: str = Field(description="Signature of commitment (hex-encoded)")
    created_at: int = Field(description="Unix timestamp from signed event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction for signature verification")


class CivicCommitmentResponse(BaseModel):
    """Civic commitment response (Kind 30811)."""
    id: str
    action_ref: str
    status: str
    public_key: str
    timestamp: str
    revoked: bool = False


class CivicWithdrawRequest(BaseModel):
    """Request to withdraw a commitment to a civic action."""
    public_key: str = Field(description="Committer's public key (hex-encoded)")
    signature: str = Field(description="Signature of withdrawal (hex-encoded)")
    created_at: int = Field(description="Unix timestamp from signed event")


class CivicCompletionRequest(BaseModel):
    """Request to complete a civic action (Kind 30812)."""
    action_id: str = Field(default="", description="ID of the action event (may also come from URL path)")
    public_key: str = Field(description="Completer's public key (hex-encoded)")
    signature: str = Field(description="Signature of completion (hex-encoded)")
    evidence_type: str = Field(description="Type of evidence: self_report, email_confirmation, etc.")
    evidence_content: Optional[str] = Field(default=None, description="Evidence URL or content")
    created_at: int = Field(description="Unix timestamp from signed event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction for signature verification")


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


# === Outcome & Attribution Request/Response Models ===


class ReportOutcomeRequest(BaseModel):
    """Request to report an initiative outcome."""
    outcome: str = Field(description="Result: passed, failed, continued, modified, partial")
    notes: Optional[str] = Field(default=None, description="Additional context")
    vote_breakdown: Optional[dict] = Field(default=None, description="Vote details (e.g., {'yes': 4, 'no': 1})")
    decision_reference: Optional[str] = Field(default=None, description="Reference to civic data decision")


class OutcomeResponse(BaseModel):
    """Initiative outcome response."""
    id: str
    initiative_id: str
    outcome: str
    notes: Optional[str] = None
    vote_breakdown: Optional[dict] = None
    decision_reference: Optional[str] = None
    recorded_at: str
    attribution_count: int = 0


class AttributionResponse(BaseModel):
    """Attribution record response."""
    id: str
    outcome_id: Optional[str] = None
    action_id: str
    public_key: str
    contribution_type: str
    message: Optional[str] = None
    created_at: str


class UserImpactResponse(BaseModel):
    """User impact summary — attributions with optional outcome context."""
    attribution: AttributionResponse
    outcome: Optional[OutcomeResponse] = None


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
    attestation_proof: Optional[dict] = Field(default=None, description="Full kind-30850 Nostr event signed by jurisdiction issuer")


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
    attested: Optional[bool] = None


class CommentCountResponse(BaseModel):
    """Comment count for an entity."""
    entity: str
    count: int = 0
    attested: Optional[int] = None
    unattested: Optional[int] = None


# === Attestation Request/Response Models ===


class RedeemAttestationRequest(BaseModel):
    """Request to redeem an attestation code."""
    code: str = Field(description="Single-use attestation code")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Nostr kind-24242 signature proving pubkey ownership")
    created_at: int = Field(description="Unix timestamp from the signed event")


class AttestationResponse(BaseModel):
    """Attestation status response."""
    attested: bool
    attestation_event: Optional[dict] = None
    attested_at: Optional[str] = None


class AttestationStatsResponse(BaseModel):
    """Attestation stats for a jurisdiction."""
    total_attested: int = 0
    total_codes_issued: int = 0
    total_codes_redeemed: int = 0


class RegisterIssuerRequest(BaseModel):
    """Request to register an attestation issuer."""
    issuer_pubkey: str = Field(description="Issuer's public key (64-char hex)")
    jurisdiction: str = Field(description="Jurisdiction code (e.g. city-mill-valley)")
    organization: str = Field(description="Organization name")
    signing_url: str = Field(description="URL of issuer's signing service")
    bearer_token: str = Field(description="Bearer token for the signing service")
    allowed_types: list[str] = Field(default=["physical"], description="Allowed attestation types")


class RegisterIssuerResponse(BaseModel):
    """Response after registering an issuer."""
    issuer_id: str
    status: str
    organization: str
    jurisdiction: str


class CodeBatchRequest(BaseModel):
    """Request to submit a batch of issuer-signed attestation codes."""
    signed_event: dict = Field(description="Kind-30851 Nostr event with signed code batch")


class CodeBatchResponse(BaseModel):
    """Response after accepting a code batch."""
    count: int
    total_submitted: int
    batch_id: str
    jurisdiction: str
    issuer_id: str


class IssuerListResponse(BaseModel):
    """List of issuers for a jurisdiction."""
    issuers: list[dict]


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


def _get_attestation_storage():
    """Get or create attestation storage instance."""
    if "attestation" not in _storage_instances:
        url = _get_relay_url()
        if url:
            try:
                from civicos_relay.storage.postgres import PostgresAttestationStorage
                _storage_instances["attestation"] = PostgresAttestationStorage(url)
                logger.info("Using PostgresAttestationStorage for attestations")
            except ImportError:
                logger.warning("civicos-relay postgres not available for attestations")
                return None
        else:
            try:
                from civicos_relay.storage.memory import InMemoryAttestationStorage
                _storage_instances["attestation"] = InMemoryAttestationStorage()
            except ImportError:
                logger.warning("civicos-relay not available for attestations")
                return None
    return _storage_instances["attestation"]


def _get_attestation_issuer_keypair():
    """Get the attestation issuer keypair from environment."""
    if "attestation_keypair" not in _storage_instances:
        private_key_hex = os.environ.get("CIVICOS_ATTESTATION_PRIVATE_KEY")
        if not private_key_hex:
            logger.warning("CIVICOS_ATTESTATION_PRIVATE_KEY not set")
            return None
        try:
            from coincurve import PublicKeyXOnly
            xonly_pk = PublicKeyXOnly.from_valid_secret(bytes.fromhex(private_key_hex))
            _storage_instances["attestation_keypair"] = KeyPair(
                public_key_hex=xonly_pk.format().hex(),
                private_key_hex=private_key_hex,
            )
        except Exception as e:
            logger.error(f"Failed to load attestation keypair: {e}")
            return None
    return _storage_instances["attestation_keypair"]


def _get_issuer_storage():
    """Get or create issuer registry storage instance."""
    if "issuer_registry" not in _storage_instances:
        url = _get_relay_url()
        if url:
            try:
                from civicos_relay.storage.postgres import PostgresIssuerRegistryStorage
                _storage_instances["issuer_registry"] = PostgresIssuerRegistryStorage(url)
                logger.info("Using PostgresIssuerRegistryStorage for issuer registry")
            except ImportError:
                logger.warning("civicos-relay postgres not available for issuer registry")
                return None
        else:
            try:
                from civicos_relay.storage.memory import InMemoryIssuerRegistryStorage
                _storage_instances["issuer_registry"] = InMemoryIssuerRegistryStorage()
            except ImportError:
                logger.warning("civicos-relay not available for issuer registry")
                return None
    return _storage_instances["issuer_registry"]


def _get_attestation_service():
    """Get or create AttestationService instance."""
    if "attestation_service" not in _storage_instances:
        attestation_storage = _get_attestation_storage()
        issuer_storage = _get_issuer_storage()
        if not attestation_storage or not issuer_storage:
            return None
        from civicos_relay.attestation.service import AttestationService
        _storage_instances["attestation_service"] = AttestationService(
            attestation_storage, issuer_storage
        )
    return _storage_instances["attestation_service"]


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
                    PostgresOutcomeStorage,
                    PostgresAttributionStorage,
                )
                _storage_instances["civic_action_events"] = PostgresCivicActionEventStorage(url)
                _storage_instances["civic_commitments"] = PostgresCivicCommitmentStorage(url)
                _storage_instances["civic_completions"] = PostgresCivicCompletionStorage(url)
                _storage_instances["outcomes"] = PostgresOutcomeStorage(url)
                _storage_instances["attributions"] = PostgresAttributionStorage(url)
                logger.info("Using PostgreSQL storage for civic actions")
            else:
                from civicos_relay.storage.memory import (
                    InMemoryCivicActionEventStorage,
                    InMemoryCivicCommitmentStorage,
                    InMemoryCivicCompletionStorage,
                    InMemoryOutcomeStorage,
                    InMemoryAttributionStorage,
                )
                _storage_instances["civic_action_events"] = InMemoryCivicActionEventStorage()
                _storage_instances["civic_commitments"] = InMemoryCivicCommitmentStorage()
                _storage_instances["civic_completions"] = InMemoryCivicCompletionStorage()
                _storage_instances["outcomes"] = InMemoryOutcomeStorage()
                _storage_instances["attributions"] = InMemoryAttributionStorage()

            _storage_instances["civic_action_service"] = CivicActionService(
                _storage_instances["civic_action_events"],
                _storage_instances["civic_commitments"],
                _storage_instances["civic_completions"],
                outcome_storage=_storage_instances["outcomes"],
                attribution_storage=_storage_instances["attributions"],
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

    _check_created_at(request.created_at)

    try:
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
            attestation_proof=request.attestation_proof,
            payment_proof=request.payment_proof,
        )

        # Verify signature
        if not verify_voice(voice):
            raise HTTPException(
                status_code=400,
                detail="Invalid voice signature"
            )

        # Hard gate: attestation_proof or payment_proof required
        if not request.attestation_proof and not request.payment_proof:
            raise HTTPException(
                status_code=403,
                detail="attestation_proof or payment_proof required"
            )

        # Verify attestation proof if provided
        if request.attestation_proof:
            issuer_keypair = _get_attestation_issuer_keypair()
            if not issuer_keypair:
                raise HTTPException(status_code=503, detail="Attestation issuer not configured")
            if not verify_attestation_proof(
                request.attestation_proof,
                subject_pubkey=request.public_key,
                jurisdiction=request.jurisdiction or "",
                issuer_pubkey=issuer_keypair.public_key_hex,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid attestation_proof"
                )

        # Verify payment proof (blinded token) if provided
        if request.payment_proof and not request.attestation_proof:
            from civicos_relay.voice.blind import SpendableToken, verify_token, compute_token_hash
            from civicos_relay.server.app import get_acceptance_policy

            try:
                token = SpendableToken.from_dict(request.payment_proof)
                if not verify_token(token):
                    raise HTTPException(status_code=400, detail="Invalid payment token signature")

                # Check double-spend via acceptance policy's spent token storage
                policy = get_acceptance_policy()
                if policy and policy._spent_token_storage:
                    token_hash = compute_token_hash(token)
                    if not policy._spent_token_storage.check_and_mark_spent(token_hash, voice.entity):
                        raise HTTPException(status_code=409, detail="Token already spent")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail="Malformed payment_proof")

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


class RevokeVoiceRequest(BaseModel):
    """Request to revoke a voice (signed by client)."""
    entity: str = Field(description="Namespaced entity identifier")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature proving ownership of the key")
    created_at: int = Field(description="Unix timestamp from signed event")


@router.post("/coordination/voice/revoke")
async def revoke_voice(request: RevokeVoiceRequest):
    """
    Revoke a voice on a civic entity.

    Requires a signed proof to verify the caller owns the public key.
    The client signs a Nostr event with content "civicos:voice:v1:{entity}:revoke:{created_at}".
    """
    storage = _get_voice_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured (missing RELAY_DATABASE_URL)"
        )

    try:
        if not request.public_key or not request.signature:
            raise HTTPException(status_code=400, detail="Missing required fields")

        _check_created_at(request.created_at)

        # Verify signature: client signed a revoke event (kind 30800)
        tags = [["d", request.entity]]
        content = f"civicos:voice:v1:{request.entity}:revoke:{request.created_at}"
        event_id = _compute_nostr_event_id(
            request.public_key, request.created_at, 30800, tags, content
        )
        if not _schnorr_verify(request.public_key, request.signature, event_id):
            raise HTTPException(status_code=400, detail="Invalid revocation signature")

        existing = storage.get_voice(request.public_key, request.entity)
        if existing and not existing.revoked:
            storage.revoke_voice(request.public_key, request.entity)
            return {"status": "revoked", "entity": request.entity}
        else:
            return {"status": "no_voice", "entity": request.entity}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking voice: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/voice/counts/{entity:path}", response_model=VoiceCountResponse)
async def get_voice_counts(entity: str, jurisdiction: Optional[str] = None):
    """
    Get voice counts for an entity.

    Returns support, oppose, watching, and total counts.
    Includes attested/unattested breakdown when jurisdiction is provided
    and attestation storage is available.
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

        # Count attested voices from embedded attestation_proof (no JOIN needed)
        attested = None
        unattested = None
        if jurisdiction:
            try:
                voices = storage.get_voices_for_entity(entity)
                attested = sum(1 for v in voices if v.attestation_proof is not None)
                unattested = len(voices) - attested
            except Exception as e:
                logger.debug(f"Attestation counts unavailable: {e}")

        return VoiceCountResponse(
            entity=counts.entity,
            support=counts.support,
            oppose=counts.oppose,
            watching=counts.watching,
            total=counts.total,
            attested=attested,
            unattested=unattested,
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
    """Generate deterministic initiative ID from jurisdiction + title + date (UTC)."""
    import hashlib

    # Use UTC date to match frontend's new Date().toISOString().slice(0, 10)
    today = datetime.utcnow().date().isoformat()
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
        timestamp = datetime.utcfromtimestamp(request.created_at)

        _check_created_at(request.created_at)

        if not verify_initiative(
            request.public_key, request.signature,
            request.jurisdiction, request.topic, request.created_at,
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

        # Validate coordination_url if provided
        coordination_url = request.coordination_url
        if coordination_url:
            from urllib.parse import urlparse
            parsed = urlparse(coordination_url)
            if parsed.scheme not in ('https', 'http', 'mailto'):
                raise HTTPException(status_code=400, detail="coordination_url must use https, http, or mailto scheme")

        # Create initiative
        initiative = Initiative(
            id=initiative_id,
            jurisdiction=request.jurisdiction,
            topic=request.topic,
            title=request.title,
            description=request.description,
            location=request.location,
            coordination_url=coordination_url,
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
            coordination_url=initiative.coordination_url,
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

        # Batch-check attestation for creators and voice counts
        att_storage = _get_attestation_storage()
        attested_creators: set[str] | None = None
        attested_voice_counts: dict[str, int] | None = None
        if att_storage:
            try:
                unique_keys = {i.public_key for i in initiatives}
                attested_creators = {
                    pk for pk in unique_keys
                    if att_storage.is_attested(pk, jurisdiction)
                }
                attested_voice_counts = {}
                for i in initiatives:
                    if i.voice_count > 0:
                        try:
                            att = att_storage.count_attested_voices(i.id, jurisdiction)
                            attested_voice_counts[i.id] = att["attested"]
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Initiative attestation lookup unavailable: {e}")

        return [
            InitiativeResponse(
                id=i.id,
                jurisdiction=i.jurisdiction,
                topic=i.topic,
                title=i.title,
                description=i.description,
                location=i.location,
                coordination_url=i.coordination_url,
                public_key=i.public_key,
                timestamp=i.timestamp.isoformat(),
                status=i.status.value,
                voice_count=i.voice_count,
                creator_attested=i.public_key in attested_creators if attested_creators is not None else None,
                attested_voice_count=attested_voice_counts.get(i.id) if attested_voice_counts is not None else None,
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

        creator_attested = None
        attested_voice_count = None
        att_storage = _get_attestation_storage()
        if att_storage:
            try:
                creator_attested = att_storage.is_attested(initiative.public_key, initiative.jurisdiction)
                if initiative.voice_count > 0:
                    att = att_storage.count_attested_voices(initiative.id, initiative.jurisdiction)
                    attested_voice_count = att["attested"]
            except Exception as e:
                logger.debug(f"Initiative attestation lookup unavailable: {e}")

        return InitiativeResponse(
            id=initiative.id,
            jurisdiction=initiative.jurisdiction,
            topic=initiative.topic,
            title=initiative.title,
            description=initiative.description,
            location=initiative.location,
            coordination_url=initiative.coordination_url,
            public_key=initiative.public_key,
            timestamp=initiative.timestamp.isoformat(),
            status=initiative.status.value,
            voice_count=initiative.voice_count,
            creator_attested=creator_attested,
            attested_voice_count=attested_voice_count,
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


@router.post("/coordination/sync/trigger")
async def trigger_sync(
    api_key: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    """
    Admin: trigger an immediate sync from all configured peers.

    Returns sync results per peer. Requires admin API key.
    """
    _require_admin_key(api_key, authorization)

    try:
        from civicos_relay.server.app import get_sync_service
        sync_service = get_sync_service()
    except (ImportError, KeyError):
        raise HTTPException(status_code=503, detail="Sync service not available")

    results = {}
    for url, peer in sync_service._peers.items():
        if not peer.enabled:
            results[url] = {"status": "disabled"}
            continue
        try:
            result = await sync_service.sync_from_peer(peer)
            results[url] = {
                "status": "ok",
                "accepted": result.accepted,
                "rejected": result.rejected,
                "duplicates": result.duplicates,
            }
        except Exception as e:
            results[url] = {"status": "error", "detail": str(e)}

    return {"peers": results}


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
                    created_at=v.created_at,
                    jurisdiction=v.jurisdiction,
                    attestation_proof=v.attestation_proof,
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

        # Verify Nostr event signature
        _check_created_at(request.created_at)
        if not verify_commitment(
            request.public_key, request.signature,
            request.action_id, request.jurisdiction or _default_jurisdiction(), request.created_at,
        ):
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

        # Verify Nostr event signature
        _check_created_at(request.created_at)
        if not verify_completion(
            request.public_key, request.signature,
            request.action_id, request.jurisdiction or _default_jurisdiction(), request.created_at,
            request.evidence_url,
        ):
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

    _check_created_at(request.created_at)

    try:
        # Verify signature before doing anything else
        if not verify_action_event(
            request.public_key, request.signature,
            request.initiative_id, request.action_type, request.created_at,
        ):
            raise HTTPException(status_code=403, detail="Invalid action event signature")

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

        # Validate coordination_url if provided
        coordination_url = request.coordination_url
        if coordination_url:
            from urllib.parse import urlparse
            parsed = urlparse(coordination_url)
            if parsed.scheme not in ('https', 'http', 'mailto'):
                raise HTTPException(status_code=400, detail="coordination_url must use https, http, or mailto scheme")

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
            deadline_context=request.deadline_context,
            coordination_url=coordination_url,
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
            deadline_context=action.deadline_context,
            coordination_url=action.coordination_url,
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
                deadline_context=a.deadline_context,
                coordination_url=a.coordination_url,
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
            deadline_context=action.deadline_context,
            coordination_url=action.coordination_url,
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
        # Verify Nostr event signature
        _check_created_at(request.created_at)
        if not verify_commitment(
            request.public_key, request.signature,
            action_id, request.jurisdiction or _default_jurisdiction(), request.created_at,
        ):
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
    "/coordination/civic-action/{action_id:path}/withdraw",
)
async def withdraw_civic_action_commitment(action_id: str, request: CivicWithdrawRequest):
    """
    Withdraw a commitment to a civic action.

    Only the original committer can withdraw their commitment.
    """
    service = _get_civic_action_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Civic action service not configured"
        )

    _check_created_at(request.created_at)

    try:
        # Verify withdrawal signature (must match relay's verify_withdrawal)
        if not verify_withdrawal(
            request.public_key, request.signature,
            action_id, request.created_at,
        ):
            raise HTTPException(
                status_code=403,
                detail="Invalid withdrawal signature"
            )

        success = service.withdraw_commitment(
            action_id=action_id,
            public_key=request.public_key,
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="No commitment found to withdraw"
            )

        logger.info(f"Commitment withdrawn for action {action_id} by {request.public_key[:16]}...")

        # Refresh progress
        progress = service.get_action_progress(action_id)
        return {
            "status": "withdrawn",
            "action_id": action_id,
            "commitment_count": progress.commitment_count,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error withdrawing civic action commitment: {e}")
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
        # Validate evidence type
        try:
            evidence_type = EvidenceType(request.evidence_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid evidence_type: {request.evidence_type}. Must be one of: "
                       "self_report, email_confirmation, attendance_check, verified"
            )

        # Verify Nostr event signature
        _check_created_at(request.created_at)
        if not verify_completion(
            request.public_key, request.signature,
            action_id, request.jurisdiction or _default_jurisdiction(), request.created_at,
            request.evidence_content,
        ):
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


# === Outcome & Attribution Endpoints ===


@router.post(
    "/coordination/initiative/{initiative_id}/outcome",
    response_model=OutcomeResponse,
)
async def report_initiative_outcome(initiative_id: str, request: ReportOutcomeRequest):
    """
    Record the outcome of a civic initiative.

    Auto-generates attributions for all users who committed to or completed
    actions for this initiative. This closes the feedback loop.
    """
    service = _get_civic_action_service()
    if not service:
        raise HTTPException(status_code=503, detail="Action service not available")

    try:
        try:
            outcome_type = OutcomeType(request.outcome)
        except ValueError:
            valid = [t.value for t in OutcomeType]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid outcome '{request.outcome}'. Must be one of: {valid}"
            )

        outcome = service.record_outcome(
            initiative_id=initiative_id,
            outcome=outcome_type,
            notes=request.notes,
            vote_breakdown=request.vote_breakdown,
            decision_reference=request.decision_reference,
        )

        attributions = service.get_attributions_for_outcome(outcome.id)

        return OutcomeResponse(
            id=outcome.id,
            initiative_id=outcome.initiative_id,
            outcome=outcome.outcome.value,
            notes=outcome.notes,
            vote_breakdown=outcome.vote_breakdown,
            decision_reference=outcome.decision_reference,
            recorded_at=outcome.recorded_at.isoformat(),
            attribution_count=len(attributions),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording initiative outcome: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/initiative/{initiative_id}/outcome",
    response_model=list[OutcomeResponse],
)
async def get_initiative_outcomes(initiative_id: str):
    """Get all outcomes for an initiative."""
    service = _get_civic_action_service()
    if not service:
        return []

    try:
        outcomes = service.get_outcomes_for_initiative(initiative_id)
        result = []
        for o in outcomes:
            attributions = service.get_attributions_for_outcome(o.id)
            result.append(OutcomeResponse(
                id=o.id,
                initiative_id=o.initiative_id,
                outcome=o.outcome.value,
                notes=o.notes,
                vote_breakdown=o.vote_breakdown,
                decision_reference=o.decision_reference,
                recorded_at=o.recorded_at.isoformat(),
                attribution_count=len(attributions),
            ))
        return result

    except Exception as e:
        logger.error(f"Error getting initiative outcomes: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/initiative/{initiative_id}/outcome/{outcome_id}/attributions",
    response_model=list[AttributionResponse],
)
async def get_outcome_attributions(initiative_id: str, outcome_id: str):
    """Get all attributions for a specific outcome."""
    service = _get_civic_action_service()
    if not service:
        return []

    try:
        attributions = service.get_attributions_for_outcome(outcome_id)
        return [
            AttributionResponse(
                id=a.id,
                outcome_id=a.outcome_id,
                action_id=a.action_id,
                public_key=a.public_key,
                contribution_type=a.contribution_type.value,
                message=a.message,
                created_at=a.created_at.isoformat(),
            )
            for a in attributions
        ]

    except Exception as e:
        logger.error(f"Error getting outcome attributions: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get(
    "/coordination/attribution/{public_key}",
    response_model=list[UserImpactResponse],
)
async def get_user_impact(public_key: str):
    """
    Get a user's impact history — both activity completions and outcome attributions.

    Returns two types of attributions:
    - Activity-based (outcome=None): "You completed: Submit written comment (3 of 10)"
    - Outcome-based (outcome set): "Your comment contributed to outcome: passed (4-1)"
    """
    service = _get_civic_action_service()
    if not service:
        return []

    try:
        attributions = service.get_attributions_for_user(public_key)

        result = []
        outcome_cache: dict[str, OutcomeResponse] = {}

        for a in attributions:
            outcome_response = None

            if a.outcome_id is not None:
                # Outcome-based attribution — look up outcome details
                if a.outcome_id not in outcome_cache:
                    outcome = service.get_outcome(a.outcome_id)
                    if not outcome:
                        continue
                    attr_count = len(service.get_attributions_for_outcome(a.outcome_id))
                    outcome_cache[a.outcome_id] = OutcomeResponse(
                        id=outcome.id,
                        initiative_id=outcome.initiative_id,
                        outcome=outcome.outcome.value,
                        notes=outcome.notes,
                        vote_breakdown=outcome.vote_breakdown,
                        decision_reference=outcome.decision_reference,
                        recorded_at=outcome.recorded_at.isoformat(),
                        attribution_count=attr_count,
                    )
                outcome_response = outcome_cache[a.outcome_id]

            result.append(UserImpactResponse(
                attribution=AttributionResponse(
                    id=a.id,
                    outcome_id=a.outcome_id,
                    action_id=a.action_id,
                    public_key=a.public_key,
                    contribution_type=a.contribution_type.value,
                    message=a.message,
                    created_at=a.created_at.isoformat(),
                ),
                outcome=outcome_response,
            ))

        return result

    except Exception as e:
        logger.error(f"Error getting user impact: {e}")
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

    _check_created_at(request.created_at)

    try:
        comment = Comment(
            entity=request.entity,
            comment_text=request.comment_text,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
            jurisdiction=request.jurisdiction,
            stance=request.stance,
            attestation_proof=request.attestation_proof,
        )

        if not verify_comment(comment):
            raise HTTPException(status_code=400, detail="Invalid comment signature")

        # Hard gate: attestation_proof required
        if not request.attestation_proof:
            raise HTTPException(
                status_code=403,
                detail="attestation_proof required"
            )

        issuer_keypair = _get_attestation_issuer_keypair()
        if not issuer_keypair:
            raise HTTPException(status_code=503, detail="Attestation issuer not configured")
        if not verify_attestation_proof(
            request.attestation_proof,
            subject_pubkey=request.public_key,
            jurisdiction=request.jurisdiction or "",
            issuer_pubkey=issuer_keypair.public_key_hex,
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid attestation_proof"
            )

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
async def list_comments(entity: str, jurisdiction: Optional[str] = None):
    """
    List non-deleted comments for an entity, newest first.

    When jurisdiction is provided, each comment is annotated with
    whether its author has a valid attestation.
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
                attested=c.attestation_proof is not None if jurisdiction else None,
            )
            for c in comments
        ]

    except Exception as e:
        logger.error(f"Error listing comments: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/comment/counts/{entity:path}", response_model=CommentCountResponse)
async def get_comment_counts(entity: str, jurisdiction: Optional[str] = None):
    """
    Get comment count for an entity.

    Includes attested/unattested breakdown when jurisdiction is provided.
    """
    storage = _get_comment_storage()
    if not storage:
        return CommentCountResponse(entity=entity, count=0)

    try:
        count = storage.get_comment_count(entity)

        # Count attested comments from embedded attestation_proof (no JOIN needed)
        attested = None
        unattested = None
        if jurisdiction:
            try:
                comments = storage.get_comments_for_entity(entity)
                attested = sum(1 for c in comments if c.attestation_proof is not None)
                unattested = len(comments) - attested
            except Exception as e:
                logger.debug(f"Comment attestation counts unavailable: {e}")

        return CommentCountResponse(
            entity=entity, count=count, attested=attested, unattested=unattested
        )

    except Exception as e:
        logger.error(f"Error getting comment counts: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Attestation Endpoints ===


@router.post("/coordination/attest")
async def redeem_attestation(request: RedeemAttestationRequest):
    """
    Redeem an attestation code to prove physical presence.

    1. Verify Nostr signature (kind 24242 auth event)
    2. Replay protection (5-min window)
    3. Check code exists and is unredeemed
    4. Check pubkey not already attested for this jurisdiction
    5. Redeem code (atomic)
    6. Sign kind-30850 attestation event with CivicOS issuer keypair
    7. Store attestation record
    """
    import time

    storage = _get_attestation_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Attestation service not configured")

    issuer_keypair = _get_attestation_issuer_keypair()
    if not issuer_keypair:
        raise HTTPException(status_code=503, detail="Attestation issuer not configured")

    # 1. Verify signature
    try:
        if not verify_attestation_request(
            request.public_key, request.signature, request.code, request.created_at
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        raise HTTPException(status_code=401, detail="Signature verification failed")

    # 2. Replay protection (5-min window)
    now = int(time.time())
    if abs(now - request.created_at) > 300:
        raise HTTPException(status_code=400, detail="Request expired (>5 min)")

    # 3. Check code exists and is unredeemed
    code_record = storage.get_code(request.code)
    if not code_record:
        raise HTTPException(status_code=404, detail="Invalid attestation code")
    if code_record.get("redeemed_by"):
        raise HTTPException(status_code=409, detail="Code already redeemed")

    # Check expiry
    from datetime import timezone
    if code_record.get("expires_at") and code_record["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Attestation code has expired")

    jurisdiction = code_record["jurisdiction"]

    # 4. Check pubkey not already attested
    if storage.is_attested(request.public_key, jurisdiction):
        raise HTTPException(status_code=409, detail="Already attested for this jurisdiction")

    # 5. Redeem code (atomic)
    if not storage.redeem_code(request.code, request.public_key):
        raise HTTPException(status_code=409, detail="Code already redeemed")

    # 6. Sign attestation event
    try:
        attestation_event = sign_attestation_event(
            issuer_keypair, request.public_key, jurisdiction
        )
    except Exception as e:
        logger.error(f"Failed to sign attestation event: {e}")
        raise HTTPException(status_code=500, detail="Failed to sign attestation")

    # 7. Store attestation record
    attestation_id = f"attest:{jurisdiction}:{request.public_key}"
    storage.save_attestation({
        "id": attestation_id,
        "public_key": request.public_key,
        "jurisdiction": jurisdiction,
        "attestation_type": "physical",
        "code_used": request.code,
        "nostr_event": attestation_event,
    })

    logger.info(f"Attestation issued: {request.public_key[:16]}... for {jurisdiction}")

    return {"success": True, "attestation_event": attestation_event}


@router.get("/coordination/attestation/{public_key}", response_model=AttestationResponse)
async def get_attestation_status(public_key: str, jurisdiction: Optional[str] = None):
    """
    Check attestation status for a pubkey.
    """
    jurisdiction = jurisdiction or _default_jurisdiction()
    storage = _get_attestation_storage()
    if not storage:
        return AttestationResponse(attested=False)

    try:
        attestation = storage.get_attestation(public_key, jurisdiction)
        if attestation:
            return AttestationResponse(
                attested=True,
                attestation_event=attestation.get("nostr_event"),
                attested_at=attestation["created_at"].isoformat()
                if hasattr(attestation.get("created_at"), "isoformat")
                else str(attestation.get("created_at")),
            )
        return AttestationResponse(attested=False)

    except Exception as e:
        logger.error(f"Error getting attestation status: {e}")
        return AttestationResponse(attested=False)


@router.get("/coordination/attestation/stats/{jurisdiction}", response_model=AttestationStatsResponse)
async def get_attestation_stats(jurisdiction: str):
    """
    Get attestation stats for a jurisdiction.
    """
    storage = _get_attestation_storage()
    if not storage:
        return AttestationStatsResponse()

    try:
        attested_count = storage.get_attested_count(jurisdiction)
        code_stats = storage.get_code_stats(jurisdiction)
        return AttestationStatsResponse(
            total_attested=attested_count,
            total_codes_issued=code_stats["total_issued"],
            total_codes_redeemed=code_stats["total_redeemed"],
        )

    except Exception as e:
        logger.error(f"Error getting attestation stats: {e}")
        return AttestationStatsResponse()


# === Issuer Registry Endpoints ===


def _require_admin_key(api_key: Optional[str] = None, authorization: Optional[str] = None):
    """Validate admin API key from query param or Authorization header. Raises 403 if invalid."""
    expected = os.environ.get("CIVICOS_ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=403, detail="Admin API key required")

    # Check query param first, then Authorization: Bearer header
    provided = api_key
    if not provided and authorization and authorization.startswith("Bearer "):
        provided = authorization[7:]

    if provided != expected:
        raise HTTPException(status_code=403, detail="Admin API key required")


@router.post("/coordination/issuers/register", response_model=RegisterIssuerResponse)
async def register_issuer(
    request: RegisterIssuerRequest,
    api_key: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    """
    Register a new attestation issuer with the relay.

    Requires admin API key (query param or Authorization: Bearer header).
    Issuer starts as unverified — must be explicitly verified via the admin
    endpoint before codes can be accepted.
    """
    _require_admin_key(api_key, authorization)

    service = _get_attestation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Attestation service not configured")

    try:
        result = service.register_issuer(request.model_dump())
        return RegisterIssuerResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering issuer: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/issuers/{jurisdiction}", response_model=IssuerListResponse)
async def list_issuers(jurisdiction: str):
    """List all non-revoked issuers for a jurisdiction."""
    service = _get_attestation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Attestation service not configured")

    try:
        issuers = service.list_issuers(jurisdiction)
        return IssuerListResponse(issuers=issuers)
    except Exception as e:
        logger.error(f"Error listing issuers: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/admin/issuer/{issuer_id}/verify")
async def verify_issuer(
    issuer_id: str,
    api_key: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    """Admin: mark an issuer as verified (trusted to issue codes)."""
    _require_admin_key(api_key, authorization)

    service = _get_attestation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Attestation service not configured")

    try:
        success = service.verify_issuer(issuer_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Issuer not found: {issuer_id}")
        return {"success": True, "issuer_id": issuer_id, "status": "verified"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying issuer: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/admin/issuer/{issuer_id}/revoke")
async def revoke_issuer(
    issuer_id: str,
    api_key: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    """Admin: revoke an issuer (codes from this issuer will no longer be accepted)."""
    _require_admin_key(api_key, authorization)

    service = _get_attestation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Attestation service not configured")

    try:
        success = service.revoke_issuer(issuer_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Issuer not found: {issuer_id}")
        return {"success": True, "issuer_id": issuer_id, "status": "revoked"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking issuer: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/coordination/codes/batch", response_model=CodeBatchResponse)
async def accept_code_batch(
    request: CodeBatchRequest,
    api_key: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    """
    Accept a batch of issuer-signed attestation codes.

    The signed_event is a kind-30851 Nostr event containing codes signed
    by a registered issuer. The issuer must be verified before codes are accepted.

    Requires admin API key (query param or Authorization: Bearer header).
    """
    _require_admin_key(api_key, authorization)

    service = _get_attestation_service()
    if not service:
        raise HTTPException(status_code=503, detail="Attestation service not configured")

    try:
        result = service.accept_code_batch(request.signed_event)
        return CodeBatchResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error accepting code batch: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# === Feedback Endpoints ===


class SubmitFeedbackRequest(BaseModel):
    """Request to submit feedback (signed by client)."""
    feedback_type: str = Field(description="Type: bug, feature, or general")
    content: str = Field(description="Free-text feedback body")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature (hex-encoded)")
    created_at: int = Field(description="Unix timestamp from signed event")
    jurisdiction: Optional[str] = Field(default=None, description="Jurisdiction code")


class FeedbackResponse(BaseModel):
    """Feedback submission response."""
    id: int
    received_at: str


class FeedbackListResponse(BaseModel):
    """Feedback query response."""
    feedback: list[dict]
    total: int


def _get_feedback_storage():
    """Get or create feedback storage instance."""
    url = _get_relay_url()
    if not url:
        return None

    if "feedback" not in _storage_instances:
        try:
            from civicos_relay.storage.postgres import PostgresFeedbackStorage
            _storage_instances["feedback"] = PostgresFeedbackStorage(url)
        except ImportError:
            logger.warning("civicos-relay not available")
            return None
    return _storage_instances["feedback"]


@router.post("/coordination/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(request: SubmitFeedbackRequest):
    """
    Submit user feedback.

    Feedback is cryptographically signed by the client. The signature
    verifies the content is authorized by the public key. Rate limited
    to 10 submissions per hour per pubkey.
    """
    storage = _get_feedback_storage()
    if not storage:
        raise HTTPException(
            status_code=503,
            detail="Coordination service not configured (missing RELAY_DATABASE_URL)"
        )

    _check_created_at(request.created_at)

    try:
        from civicos_relay.nostr.kinds import VALID_FEEDBACK_TYPES

        # Validate feedback type
        if request.feedback_type not in VALID_FEEDBACK_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid feedback_type: {request.feedback_type}. Must be bug, feature, or general"
            )

        # Validate content length
        content = request.content.strip()
        if len(content) < 10:
            raise HTTPException(status_code=400, detail="Feedback content must be at least 10 characters")
        if len(content) > 2000:
            raise HTTPException(status_code=400, detail="Feedback content must be at most 2000 characters")

        # Rate limit check
        if not storage.check_rate_limit(request.public_key):
            raise HTTPException(status_code=429, detail="Rate limit exceeded (10 per hour)")

        # Create feedback model
        feedback = Feedback(
            feedback_type=request.feedback_type,
            content=content,
            public_key=request.public_key,
            signature=request.signature,
            created_at=request.created_at,
            jurisdiction=request.jurisdiction,
        )

        # Verify signature
        if not verify_feedback(feedback):
            raise HTTPException(status_code=400, detail="Invalid feedback signature")

        # Save
        feedback_id = storage.save_feedback(feedback)

        return FeedbackResponse(
            id=feedback_id,
            received_at=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/coordination/feedback", response_model=FeedbackListResponse)
async def get_feedback(
    jurisdiction: str,
    feedback_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    api_key: Optional[str] = None,
):
    """
    Query feedback for a jurisdiction. Requires admin API key.
    """
    # Admin auth check
    expected_key = os.environ.get("CIVICOS_ADMIN_API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=403, detail="Admin API key required")

    storage = _get_feedback_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Coordination service not configured")

    try:
        items = storage.get_feedback(jurisdiction, feedback_type, limit, offset)
        total = storage.get_feedback_count(jurisdiction, feedback_type)
        return FeedbackListResponse(feedback=items, total=total)
    except Exception as e:
        logger.error(f"Error querying feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
