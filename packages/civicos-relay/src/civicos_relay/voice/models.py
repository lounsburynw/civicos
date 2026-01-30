"""Voice data models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Stance(str, Enum):
    """Position on a civic entity."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    WATCHING = "watching"


class Voice(BaseModel):
    """
    A public expression of civic interest.

    A voice is a signed record associating a keypair with a stance on an entity.
    One key can cast one voice per entity (can be revoked and re-cast).
    """

    entity: str = Field(
        description="Entity identifier (e.g., 'agenda:2026-02-03:item-6a')"
    )
    stance: Stance = Field(description="Position on the entity")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature of entity+stance (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    revoked: bool = Field(default=False)

    model_config = {"frozen": True}


class VoiceCount(BaseModel):
    """Aggregated voice counts for an entity."""

    entity: str
    support: int = 0
    oppose: int = 0
    watching: int = 0

    @property
    def total(self) -> int:
        return self.support + self.oppose + self.watching
