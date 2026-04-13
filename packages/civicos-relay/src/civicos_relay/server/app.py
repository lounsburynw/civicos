"""FastAPI application for relay server.

This module handles app lifecycle (storage init, sync, acceptance policy)
and mounts the coordination router which provides all /coordination/* endpoints.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from civicos_relay.identity import RelayIdentity, RelayConfig
from civicos_relay.voice.service import VoiceService
from civicos_relay.voice.action_service import ActionService
from civicos_relay.voice.civic_action_service import CivicActionService
from civicos_relay.relay.service import RelayService
from civicos_relay.provenance.service import ProvenanceService
from civicos_relay.sync.service import SyncService
from civicos_relay.storage import InMemoryStorage, PostgresStorage
from civicos_relay.delivery import EmailDelivery, EmailConfig
from civicos_relay.attestation.service import AttestationService
from civicos_relay.server.acceptance import AcceptancePolicy
from civicos_relay.server.ip_rate_limit import IPRateLimitMiddleware, DEFAULT_IP_RATE_LIMIT, DEFAULT_IP_RATE_WINDOW
from civicos_relay.server.token_issuer import TokenIssuer, TooManyConcurrentSessions, InvalidSession

logger = logging.getLogger(__name__)


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


def get_token_issuer() -> Optional[TokenIssuer]:
    return _relay_state.get("token_issuer")


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

        def issuer_lookup(jurisdiction: str) -> list[str]:
            """Look up all trusted issuer pubkeys for a jurisdiction."""
            issuers = issuer_storage.get_issuers_for_jurisdiction(jurisdiction)
            return [
                issuer["issuer_pubkey"]
                for issuer in issuers
                if issuer.get("verified") and not issuer.get("revoked")
            ]

        # Token issuer pubkeys for blind signature payment verification
        token_issuer_pubkeys_str = os.environ.get("TOKEN_ISSUER_PUBKEYS", "")
        known_token_issuers = {
            pk.strip() for pk in token_issuer_pubkeys_str.split(",") if pk.strip()
        } or None  # None = accept any issuer (empty set in AcceptancePolicy)

        policy = AcceptancePolicy(
            connection_url=relay_db_url,
            issuer_lookup=issuer_lookup,
            jurisdiction_id=config.jurisdiction_id,
            spent_token_storage=storage.spent_tokens,
            known_token_issuers=known_token_issuers,
        )
        policy.cleanup_old_limits()
        policy.cleanup_old_logs()
        _relay_state["acceptance_policy"] = policy
        if known_token_issuers:
            logger.info(
                "Acceptance policy enabled (attestation + %d token issuer(s))",
                len(known_token_issuers),
            )
        else:
            logger.info("Acceptance policy enabled (attestation verification, tokens accept any issuer)")

    # Initialize token issuer if secret is configured
    token_issuer_secret = os.environ.get("TOKEN_ISSUER_SECRET")
    if token_issuer_secret:
        max_sessions = int(os.environ.get("TOKEN_ISSUER_MAX_SESSIONS", "5"))
        session_ttl = float(os.environ.get("TOKEN_ISSUER_SESSION_TTL", "300"))
        issuer = TokenIssuer(
            issuer_secret=bytes.fromhex(token_issuer_secret),
            max_concurrent_sessions=max_sessions,
            session_ttl_seconds=session_ttl,
        )
        _relay_state["token_issuer"] = issuer
        logger.info("Token issuer enabled (pubkey=%s)", issuer.public_key_hex[:16] + "...")

    # Initialize voucher gate if shared secret is configured
    voucher_secret = os.environ.get("VOUCHER_HMAC_SECRET")
    if voucher_secret:
        from civicos_relay.server.voucher import VoucherTracker

        _relay_state["voucher_hmac_secret"] = voucher_secret.encode()
        _relay_state["voucher_tracker"] = VoucherTracker()
        logger.info("Voucher gate enabled — token issuance requires valid voucher")

    if config.sync_enabled:
        await _relay_state["sync_service"].start()

    logger.info(f"Relay started: {identity.relay_id}")

    yield

    # Shutdown
    await _relay_state["sync_service"].stop()
    logger.info("Relay stopped")



def create_app() -> FastAPI:
    """Create the FastAPI application.

    Mounts the coordination router which provides all /coordination/* endpoints.
    The router is self-contained — it manages its own storage connections from
    RELAY_DATABASE_URL. The lifespan here handles sync service and acceptance policy.
    """
    app = FastAPI(
        title="CivicOS Relay",
        description="Federation-ready civic coordination relay",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # HTTP-level per-IP rate limiting (runs before crypto verification)
    ip_limit = max(10, min(1000, int(os.environ.get("RELAY_IP_RATE_LIMIT", str(DEFAULT_IP_RATE_LIMIT)))))
    ip_window = max(60, min(3600, int(os.environ.get("RELAY_IP_RATE_WINDOW", str(DEFAULT_IP_RATE_WINDOW)))))
    app.add_middleware(IPRateLimitMiddleware, max_requests=ip_limit, window_seconds=ip_window)

    # Health on root (not behind /coordination)
    @app.get("/health", response_model=HealthResponse)
    async def health(identity: RelayIdentity = Depends(get_identity)):
        return HealthResponse(status="healthy", relay_id=identity.relay_id)

    # Mount the coordination router (all /coordination/* endpoints)
    from civicos_relay.server.coordination import router as coordination_router
    app.include_router(coordination_router)

    # --- Token issuance endpoints ---

    class TokenInfoResponse(BaseModel):
        enabled: bool
        issuer_pubkey: Optional[str] = None

    class NonceSessionRequest(BaseModel):
        count: int = 1

    class NonceSessionResponse(BaseModel):
        session_id: str
        nonce_point: str

    class SignRequest(BaseModel):
        session_id: str
        blinded_challenge: str

    class SignResponse(BaseModel):
        blind_signature: str

    @app.get("/coordination/tokens/info", response_model=TokenInfoResponse)
    async def token_info():
        issuer = get_token_issuer()
        if not issuer:
            return TokenInfoResponse(enabled=False)
        return TokenInfoResponse(enabled=True, issuer_pubkey=issuer.public_key_hex)

    @app.post("/coordination/tokens/session", response_model=NonceSessionResponse)
    async def token_session(
        req: NonceSessionRequest,
        authorization: Optional[str] = Header(None),
    ):
        issuer = get_token_issuer()
        if not issuer:
            raise HTTPException(status_code=503, detail="Token issuance not enabled")

        # Voucher gate: if VOUCHER_HMAC_SECRET is configured, require valid voucher
        hmac_secret = _relay_state.get("voucher_hmac_secret")
        if hmac_secret:
            from civicos_relay.server.voucher import verify_voucher

            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Voucher required for token issuance")
            voucher_token = authorization[7:]
            try:
                claims = verify_voucher(voucher_token, hmac_secret)
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e))

            tracker = _relay_state.get("voucher_tracker")
            if not tracker or not tracker.try_decrement(claims.session_id, claims.token_count):
                raise HTTPException(status_code=403, detail="Token allowance exhausted")

        try:
            session_id, nonce_point = issuer.create_nonce_session()
            return NonceSessionResponse(
                session_id=session_id,
                nonce_point=nonce_point.hex(),
            )
        except TooManyConcurrentSessions as e:
            raise HTTPException(status_code=429, detail=str(e))

    @app.post("/coordination/tokens/sign", response_model=SignResponse)
    async def token_sign(req: SignRequest):
        issuer = get_token_issuer()
        if not issuer:
            raise HTTPException(status_code=503, detail="Token issuance not enabled")
        try:
            blind_sig = issuer.sign(req.session_id, bytes.fromhex(req.blinded_challenge))
            return SignResponse(blind_signature=blind_sig.hex())
        except InvalidSession as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
