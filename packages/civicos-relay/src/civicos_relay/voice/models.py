"""Voice and Action data models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Stance(str, Enum):
    """Position on a civic entity."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    WATCHING = "watching"


class ActionType(str, Enum):
    """Type of civic action."""

    COMMITMENT = "commitment"  # Promise to take action
    COMPLETION = "completion"  # Report action completed


class Voice(BaseModel):
    """
    A public expression of civic interest.

    A voice is a signed record associating a keypair with a stance on an entity.
    One key can cast one voice per entity (can be revoked and re-cast).
    """

    entity: str = Field(
        description="Namespaced entity identifier (e.g., 'decision:city-san-rafael:2026-02-03:item-6a')"
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


class Action(BaseModel):
    """
    A civic action commitment or completion.

    Actions track user commitments to civic participation:
    - Commitment (kind 30801): User promises to take action (e.g., submit comment)
    - Completion (kind 30802): User reports action completed with evidence

    Nostr event kinds:
    - 30801: Commitment
    - 30802: Completion
    """

    action_id: str = Field(
        description="Action identifier (e.g., 'action:city-san-rafael:initiative-123:comment')"
    )
    action_type: ActionType = Field(description="commitment or completion")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # For completions: evidence of action taken
    evidence_url: Optional[str] = Field(
        default=None,
        description="URL to evidence (e.g., public comment submission confirmation)"
    )
    revoked: bool = Field(default=False)

    model_config = {"frozen": True}


class ActionCount(BaseModel):
    """Aggregated action counts for an action item."""

    action_id: str
    commitments: int = 0
    completions: int = 0
    target: Optional[int] = Field(
        default=None,
        description="Target number of actions needed (from initiative)"
    )

    @property
    def total_committed(self) -> int:
        return self.commitments

    @property
    def progress_percent(self) -> Optional[float]:
        if self.target and self.target > 0:
            return min(100.0, (self.completions / self.target) * 100)
        return None
