"""Sync protocol definitions."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from civicos_relay.voice.models import Voice
from civicos_relay.relay.models import Event


class SyncRequest(BaseModel):
    """Request for syncing voices or events from a peer."""

    since: Optional[datetime] = Field(
        default=None, description="Only return items after this timestamp"
    )
    namespace: Optional[str] = Field(
        default=None, description="Filter by entity namespace prefix"
    )
    limit: int = Field(default=100, le=1000)
    cursor: Optional[str] = Field(
        default=None, description="Pagination cursor from previous response"
    )


class VoiceSyncResponse(BaseModel):
    """Response containing voices for sync."""

    voices: list[Voice]
    cursor: Optional[str] = Field(
        default=None, description="Cursor for next page, None if no more"
    )
    relay_id: str
    relay_signature: str = Field(description="Signature for response verification")


class EventSyncResponse(BaseModel):
    """Response containing events for sync."""

    events: list[Event]
    cursor: Optional[str] = Field(default=None)
    relay_id: str
    relay_signature: str


class VoiceImportRequest(BaseModel):
    """Request to import voices from a peer."""

    voices: list[Voice]
    source_relay: str
    signature: str


class VoiceImportResponse(BaseModel):
    """Response after importing voices."""

    accepted: int = Field(description="Voices successfully imported")
    rejected: int = Field(description="Voices rejected (invalid signature)")
    duplicates: int = Field(description="Voices already present")


class SyncResponse(BaseModel):
    """Generic sync response wrapper."""

    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None


class SyncProtocol:
    """
    Protocol constants and versioning.

    Voice signature format: civicos:voice:v1:{entity}:{stance}
    Event signature format: civicos:event:v1:{relay_id}:{type}:{entity}:{timestamp}
    Sync signature format:  civicos:sync:v1:{relay_id}:{data_hash}:{cursor}
    """

    VERSION = "v1"
    VOICE_PREFIX = f"civicos:voice:{VERSION}"
    EVENT_PREFIX = f"civicos:event:{VERSION}"
    SYNC_PREFIX = f"civicos:sync:{VERSION}"

    @staticmethod
    def voice_message(entity: str, stance: str) -> bytes:
        """Create the message that gets signed for a voice."""
        return f"{SyncProtocol.VOICE_PREFIX}:{entity}:{stance}".encode("utf-8")

    @staticmethod
    def event_message(
        relay_id: str, event_type: str, entity: str, timestamp: datetime
    ) -> bytes:
        """Create the message that gets signed for an event."""
        return f"{SyncProtocol.EVENT_PREFIX}:{relay_id}:{event_type}:{entity}:{timestamp.isoformat()}".encode(
            "utf-8"
        )

    @staticmethod
    def sync_message(relay_id: str, data_hash: str, cursor: str) -> bytes:
        """Create the message that gets signed for a sync response."""
        return f"{SyncProtocol.SYNC_PREFIX}:{relay_id}:{data_hash}:{cursor}".encode(
            "utf-8"
        )
