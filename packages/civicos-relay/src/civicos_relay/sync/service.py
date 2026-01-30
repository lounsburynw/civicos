"""Sync service - manages synchronization with peer relays."""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Optional, Protocol

import httpx

from civicos_relay.identity import RelayIdentity, PeerConfig
from civicos_relay.voice.models import Voice
from civicos_relay.voice.crypto import verify_voice
from civicos_relay.sync.protocol import (
    SyncRequest,
    VoiceSyncResponse,
    VoiceImportRequest,
    VoiceImportResponse,
    SyncProtocol,
)

logger = logging.getLogger(__name__)


class SyncStorage(Protocol):
    """Protocol for sync state persistence."""

    def get_sync_cursor(self, peer_url: str) -> Optional[str]:
        """Get last sync cursor for a peer."""
        ...

    def set_sync_cursor(self, peer_url: str, cursor: str) -> None:
        """Update sync cursor for a peer."""
        ...

    def get_voices_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Voice], Optional[str]]:
        """Get voices for export. Returns (voices, next_cursor)."""
        ...

    def import_voice(self, voice: Voice) -> str:
        """Import a voice. Returns 'accepted', 'rejected', or 'duplicate'."""
        ...


class SyncService:
    """
    Service for synchronizing voices and events with peer relays.

    Handles both export (serving to peers) and import (fetching from peers).
    """

    def __init__(
        self,
        identity: RelayIdentity,
        storage: SyncStorage,
        peers: list[PeerConfig],
    ):
        self._identity = identity
        self._storage = storage
        self._peers = {p.url: p for p in peers}
        self._client = httpx.AsyncClient(timeout=30.0)
        self._running = False

    async def start(self) -> None:
        """Start background sync tasks."""
        self._running = True
        for peer in self._peers.values():
            if peer.enabled:
                asyncio.create_task(self._sync_loop(peer))

    async def stop(self) -> None:
        """Stop background sync tasks."""
        self._running = False
        await self._client.aclose()

    async def _sync_loop(self, peer: PeerConfig) -> None:
        """Background loop for syncing with a peer."""
        while self._running:
            try:
                await self.sync_from_peer(peer)
            except Exception as e:
                logger.error(f"Sync error with {peer.url}: {e}")

            await asyncio.sleep(peer.sync_interval)

    async def sync_from_peer(self, peer: PeerConfig) -> VoiceImportResponse:
        """Pull voices from a peer relay."""
        cursor = self._storage.get_sync_cursor(peer.url)

        total_accepted = 0
        total_rejected = 0
        total_duplicates = 0

        while True:
            # Request voices from peer
            request = SyncRequest(
                since=None,  # Use cursor instead
                namespace=peer.namespaces[0] if peer.namespaces else None,
                cursor=cursor,
            )

            response = await self._client.get(
                f"{peer.url}/sync/voices",
                params=request.model_dump(exclude_none=True),
            )
            response.raise_for_status()

            data = VoiceSyncResponse(**response.json())

            # Verify response signature if peer public key known
            if peer.public_key:
                # TODO: Implement signature verification
                pass

            # Import voices
            for voice in data.voices:
                result = self._import_voice(voice)
                if result == "accepted":
                    total_accepted += 1
                elif result == "rejected":
                    total_rejected += 1
                else:
                    total_duplicates += 1

            # Update cursor
            if data.cursor:
                self._storage.set_sync_cursor(peer.url, data.cursor)
                cursor = data.cursor
            else:
                break  # No more pages

        return VoiceImportResponse(
            accepted=total_accepted,
            rejected=total_rejected,
            duplicates=total_duplicates,
        )

    def _import_voice(self, voice: Voice) -> str:
        """Import a single voice with verification."""
        # Verify voice signature
        if not verify_voice(voice):
            logger.warning(f"Rejected voice with invalid signature: {voice.public_key[:16]}...")
            return "rejected"

        return self._storage.import_voice(voice)

    def export_voices(self, request: SyncRequest) -> VoiceSyncResponse:
        """Export voices for a peer to sync."""
        voices, cursor = self._storage.get_voices_since(
            since=request.since or datetime.min,
            namespace=request.namespace,
            limit=request.limit,
        )

        # Sign the response
        data_hash = hashlib.sha256(
            b"".join(v.signature.encode() for v in voices)
        ).hexdigest()[:16]

        signature = self._identity.sign_sync_response(
            data_hash, cursor or "end"
        )

        return VoiceSyncResponse(
            voices=voices,
            cursor=cursor,
            relay_id=self._identity.relay_id,
            relay_signature=signature,
        )

    def import_voices(self, request: VoiceImportRequest) -> VoiceImportResponse:
        """Import voices pushed by a peer."""
        accepted = 0
        rejected = 0
        duplicates = 0

        for voice in request.voices:
            result = self._import_voice(voice)
            if result == "accepted":
                accepted += 1
            elif result == "rejected":
                rejected += 1
            else:
                duplicates += 1

        return VoiceImportResponse(
            accepted=accepted,
            rejected=rejected,
            duplicates=duplicates,
        )

    def add_peer(self, peer: PeerConfig) -> None:
        """Add a peer relay for syncing."""
        self._peers[peer.url] = peer
        if self._running and peer.enabled:
            asyncio.create_task(self._sync_loop(peer))

    def remove_peer(self, peer_url: str) -> bool:
        """Remove a peer relay."""
        if peer_url in self._peers:
            del self._peers[peer_url]
            return True
        return False

    def list_peers(self) -> list[PeerConfig]:
        """List all configured peers."""
        return list(self._peers.values())
