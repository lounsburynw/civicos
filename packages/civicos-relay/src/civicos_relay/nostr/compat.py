"""
REST API compatibility layer for Nostr migration.

Provides REST endpoints that internally use Nostr events.
This allows existing clients to continue working while we migrate to Nostr.

Endpoints map as follows:
- POST /voice -> Create CivicVoiceEvent (kind 30800)
- GET /voice/counts/{entity} -> Query voice counts from storage
- GET /voice/{entity} -> Query voice events from storage

All responses include deprecation headers encouraging migration to WebSocket.
"""

import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from civicos_relay.nostr.models import (
    CivicVoiceEvent,
    NostrEvent,
    Stance,
)
from civicos_relay.nostr.kinds import CIVIC_VOICE
from civicos_relay.nostr.storage import NostrEventStorage, EventFilter, VoiceCounts
from civicos_relay.nostr.crypto import NostrKeyPair

logger = logging.getLogger(__name__)


# =============================================================================
# REST Request/Response Models (matching old API)
# =============================================================================


class LegacyVoiceRequest(BaseModel):
    """Legacy voice request format."""

    entity: str
    stance: str  # "support", "oppose", "watching"
    public_key: str
    signature: str


class LegacyVoice(BaseModel):
    """Legacy voice response format."""

    entity: str
    stance: str
    public_key: str
    signature: str
    timestamp: datetime
    revoked: bool = False


class LegacyVoiceCount(BaseModel):
    """Legacy voice count response format."""

    entity: str
    support: int
    oppose: int
    watching: int
    total: int


# =============================================================================
# Compatibility Adapter
# =============================================================================


class NostrCompatAdapter:
    """
    Adapter that translates REST requests to Nostr events.

    This allows existing clients to continue working during migration.
    """

    def __init__(
        self,
        storage: NostrEventStorage,
        jurisdiction: str = "city-san-rafael",  # Default jurisdiction
    ):
        self._storage = storage
        self._default_jurisdiction = jurisdiction

    def cast_voice(self, request: LegacyVoiceRequest) -> LegacyVoice:
        """
        Cast a voice via REST, storing as Nostr event.

        Note: This endpoint cannot verify the signature since we're translating
        from the old SECP256R1 format. It accepts the request and creates a
        Nostr event with the relay's signature, noting the original signer
        in metadata.

        For proper Nostr signing, clients should use the WebSocket endpoint.
        """
        # Parse stance
        try:
            stance = Stance(request.stance.lower())
        except ValueError:
            raise ValueError(f"Invalid stance: {request.stance}")

        # Extract entity info for tags
        entity_id = request.entity
        parts = entity_id.split(":")
        if len(parts) >= 2:
            jurisdiction = parts[1] if len(parts) > 1 else self._default_jurisdiction
        else:
            jurisdiction = self._default_jurisdiction

        # For REST compatibility, we need to create a Nostr event
        # The challenge is the old API used SECP256R1 signatures
        #
        # Options:
        # 1. Reject REST voice requests (breaking change)
        # 2. Store with a relay-generated signature (loses provenance)
        # 3. Store as "legacy" event type (complexity)
        #
        # For now, we'll store with metadata indicating legacy origin
        # Real Nostr clients should use WebSocket

        created_at = int(datetime.utcnow().timestamp())

        # We can't create a proper Nostr event without the user's Nostr key
        # Return error suggesting WebSocket migration
        raise NotImplementedError(
            "REST voice casting requires migration to Nostr. "
            "Use WebSocket endpoint wss://relay.civicos.org with a Nostr client."
        )

    def get_voice_counts(self, entity: str) -> LegacyVoiceCount:
        """Get voice counts for an entity in legacy format."""
        counts = self._storage.get_voice_counts(entity)

        if counts is None:
            return LegacyVoiceCount(
                entity=entity,
                support=0,
                oppose=0,
                watching=0,
                total=0,
            )

        return LegacyVoiceCount(
            entity=entity,
            support=counts.support_count,
            oppose=counts.oppose_count,
            watching=counts.watching_count,
            total=counts.total_count,
        )

    def list_voices(self, entity: str) -> list[LegacyVoice]:
        """List all voices for an entity in legacy format."""
        events = self._storage.get_voices_for_entity(entity)

        voices = []
        for event in events:
            # Convert Nostr event to legacy format
            voices.append(
                LegacyVoice(
                    entity=event.entity_id,
                    stance=event.stance.value,
                    public_key=event.pubkey,
                    signature=event.sig,
                    timestamp=datetime.fromtimestamp(event.created_at),
                    revoked=event.is_revoked,
                )
            )

        return voices


# =============================================================================
# FastAPI Router Factory
# =============================================================================


def create_compat_router(storage: NostrEventStorage):
    """
    Create a FastAPI router with legacy REST endpoints.

    Usage:
        router = create_compat_router(storage)
        app.include_router(router, prefix="/v1")
    """
    from fastapi import APIRouter, HTTPException, Response

    router = APIRouter(tags=["Legacy API (Deprecated)"])
    adapter = NostrCompatAdapter(storage)

    def add_deprecation_headers(response: Response) -> Response:
        """Add deprecation headers to response."""
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2026-06-01"
        response.headers["Link"] = (
            '<wss://relay.civicos.org>; rel="successor-version"; '
            'title="Nostr WebSocket API"'
        )
        response.headers["X-Migration-Guide"] = (
            "https://docs.civicos.org/nostr-migration"
        )
        return response

    @router.post("/voice", response_model=LegacyVoice, deprecated=True)
    async def cast_voice_legacy(
        request: LegacyVoiceRequest,
        response: Response,
    ):
        """
        Cast a voice (DEPRECATED - use WebSocket).

        This endpoint is deprecated and will be removed in Q2 2026.
        Please migrate to the Nostr WebSocket API at wss://relay.civicos.org

        Migration guide: https://docs.civicos.org/nostr-migration
        """
        add_deprecation_headers(response)
        try:
            return adapter.cast_voice(request)
        except NotImplementedError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
                headers={"X-Migration-Required": "true"},
            )

    @router.get(
        "/voice/counts/{entity:path}",
        response_model=LegacyVoiceCount,
        deprecated=True,
    )
    async def get_voice_counts_legacy(entity: str, response: Response):
        """
        Get voice counts (DEPRECATED - use WebSocket REQ).

        This endpoint is deprecated. Use Nostr WebSocket with:
        ["REQ", "counts", {"kinds": [30800], "#d": ["<entity>"]}]
        """
        add_deprecation_headers(response)
        return adapter.get_voice_counts(entity)

    @router.get(
        "/voice/{entity:path}",
        response_model=list[LegacyVoice],
        deprecated=True,
    )
    async def list_voices_legacy(entity: str, response: Response):
        """
        List voices for entity (DEPRECATED - use WebSocket REQ).

        This endpoint is deprecated. Use Nostr WebSocket with:
        ["REQ", "voices", {"kinds": [30800], "#d": ["<entity>"]}]
        """
        add_deprecation_headers(response)
        return adapter.list_voices(entity)

    return router


# =============================================================================
# Response Helpers
# =============================================================================


def nostr_event_to_legacy_voice(event: CivicVoiceEvent) -> dict[str, Any]:
    """Convert a Nostr voice event to legacy API format."""
    return {
        "entity": event.entity_id,
        "stance": event.stance.value,
        "public_key": event.pubkey,
        "signature": event.sig,
        "timestamp": datetime.fromtimestamp(event.created_at).isoformat(),
        "revoked": event.is_revoked,
    }


def legacy_voice_to_nostr_tags(
    entity: str,
    stance: str,
    jurisdiction: str,
    topics: list[str] | None = None,
) -> list[list[str]]:
    """Convert legacy voice parameters to Nostr tags."""
    tags = [
        ["d", entity],
        ["j", jurisdiction],
        ["stance", stance],
    ]
    if topics:
        for topic in topics:
            tags.append(["t", topic])
    return tags
