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
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Jurisdiction code (e.g., 'city-san-rafael') for Nostr event tag reconstruction"
    )
    created_at: Optional[int] = Field(
        default=None,
        description="Unix timestamp from the signed Nostr event (for signature verification)"
    )
    attestation_proof: Optional[dict] = Field(
        default=None,
        description="Full kind-30850 Nostr event signed by the jurisdiction issuer"
    )
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


class Comment(BaseModel):
    """
    A public comment on a civic entity.

    Comments are signed records associating a keypair with text on an entity.
    One key can post one comment per entity (can be updated or soft-deleted).
    """

    entity: str = Field(
        description="Namespaced entity identifier (e.g., 'agenda-item:123')"
    )
    comment_text: str = Field(description="The comment text")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    jurisdiction: Optional[str] = Field(default=None)
    stance: Optional[str] = Field(default=None)
    created_at: Optional[int] = Field(
        default=None,
        description="Unix timestamp from the signed Nostr event"
    )
    attestation_proof: Optional[dict] = Field(
        default=None,
        description="Full kind-30850 Nostr event signed by the jurisdiction issuer"
    )
    deleted: bool = Field(default=False)

    model_config = {"frozen": True}


class Feedback(BaseModel):
    """
    User feedback on the platform.

    Feedback is a regular Nostr event (kind 1804) that allows multiple
    submissions per user. Not addressable — users can submit many feedback items.
    """

    feedback_type: str = Field(description="Type: bug, feature, or general")
    content: str = Field(description="Free-text feedback body")
    public_key: str = Field(description="Public key (hex-encoded)")
    signature: str = Field(description="Signature (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    jurisdiction: Optional[str] = Field(default=None)
    created_at: Optional[int] = Field(
        default=None,
        description="Unix timestamp from the signed Nostr event"
    )

    model_config = {"frozen": True}


class CommentCount(BaseModel):
    """Aggregated comment count for an entity."""

    entity: str
    count: int = 0


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


# ============================================================================
# Full Nostr Action Event Specification (Kinds 30810, 30811, 30812)
# ============================================================================


class CivicActionType(str, Enum):
    """Type of civic action that can be taken."""

    WRITTEN_COMMENT = "written_comment"
    ATTEND_MEETING = "attend_meeting"
    PUBLIC_COMMENT = "public_comment"
    CONTACT_OFFICIAL = "contact_official"
    SIGNATURE = "signature"
    SHARE = "share"
    CUSTOM = "custom"


class CommitmentStatus(str, Enum):
    """Status of a commitment to an action."""

    COMMITTED = "committed"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class EvidenceType(str, Enum):
    """Type of evidence provided for action completion."""

    SELF_REPORT = "self_report"
    EMAIL_CONFIRMATION = "email_confirmation"
    ATTENDANCE_CHECK = "attendance_check"
    VERIFIED = "verified"


class CivicActionEvent(BaseModel):
    """
    Kind 30810: Addressable action event.

    Defines a civic action that users can commit to and complete.
    Actions are first-class Nostr events that can be reused across
    initiatives and federated to other relays.

    d-tag format: action:{initiative}:{type}:{hash}
    """

    id: str = Field(
        description="Unique action event ID (d-tag format: action:{initiative}:{type}:{hash})"
    )
    initiative_id: str = Field(
        description="ID of the initiative this action belongs to"
    )
    action_type: CivicActionType = Field(
        description="Type of action (written_comment, attend_meeting, etc.)"
    )
    description: str = Field(
        description="Human-readable description of the action"
    )
    target: Optional[str] = Field(
        default=None,
        description="Target of the action (e.g., email address, meeting room)"
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Deadline for completing the action"
    )
    template: Optional[str] = Field(
        default=None,
        description="Template text for the action (e.g., comment template)"
    )
    target_count: Optional[int] = Field(
        default=None,
        description="Target number of completions needed"
    )
    deadline_context: Optional[str] = Field(
        default=None,
        description="Why this deadline matters (e.g., 'Comment period closes March 1')"
    )
    coordination_url: Optional[str] = Field(
        default=None,
        description="Link to coordination channel (Signal, SimpleX, Matrix)"
    )
    public_key: str = Field(description="Creator's public key (hex-encoded)")
    signature: str = Field(description="Signature of action data (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    revoked: bool = Field(default=False)

    model_config = {"frozen": True}


class CivicCommitment(BaseModel):
    """
    Kind 30811: User commitment to an action.

    Records a user's commitment to take a civic action.
    References the action via an a-tag (30810:{pubkey}:{d-tag}).

    d-tag format: commit:{pubkey}:{action-d-tag}
    """

    id: str = Field(
        description="Unique commitment ID (d-tag format: commit:{pubkey}:{action-d-tag})"
    )
    action_ref: str = Field(
        description="Reference to action event (a-tag format: 30810:{pubkey}:{d-tag})"
    )
    status: CommitmentStatus = Field(
        default=CommitmentStatus.COMMITTED,
        description="Current status of the commitment"
    )
    public_key: str = Field(description="Committer's public key (hex-encoded)")
    signature: str = Field(description="Signature of commitment data (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    revoked: bool = Field(default=False)

    model_config = {"frozen": True}


class CivicCompletion(BaseModel):
    """
    Kind 30812: Action completion with evidence.

    Records a user's completion of a civic action with optional evidence.
    References the action via an a-tag (30810:{pubkey}:{d-tag}).

    d-tag format: complete:{pubkey}:{action-d-tag}
    """

    id: str = Field(
        description="Unique completion ID (d-tag format: complete:{pubkey}:{action-d-tag})"
    )
    action_ref: str = Field(
        description="Reference to action event (a-tag format: 30810:{pubkey}:{d-tag})"
    )
    evidence_type: EvidenceType = Field(
        description="Type of evidence provided"
    )
    evidence_content: Optional[str] = Field(
        default=None,
        description="Evidence content (URL, confirmation code, etc.)"
    )
    completed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the action was completed"
    )
    public_key: str = Field(description="Completer's public key (hex-encoded)")
    signature: str = Field(description="Signature of completion data (hex-encoded)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    revoked: bool = Field(default=False)

    model_config = {"frozen": True}


class CivicActionProgress(BaseModel):
    """Aggregated progress for a civic action event."""

    action_id: str
    commitment_count: int = 0
    completion_count: int = 0
    target_count: Optional[int] = None

    @property
    def progress_percent(self) -> Optional[float]:
        if self.target_count and self.target_count > 0:
            return min(100.0, (self.completion_count / self.target_count) * 100)
        return None


# ============================================================================
# Outcome & Attribution Models
# ============================================================================


class OutcomeType(str, Enum):
    """Result of a civic initiative."""

    PASSED = "passed"
    FAILED = "failed"
    CONTINUED = "continued"
    MODIFIED = "modified"
    PARTIAL = "partial"


class ContributionType(str, Enum):
    """How a user contributed to an outcome."""

    COMMITMENT = "commitment"
    COMPLETION = "completion"


class InitiativeOutcome(BaseModel):
    """
    Recorded outcome of a civic initiative.

    Links an initiative to its decision result, enabling attribution
    for users who took action.
    """

    id: str = Field(description="Unique outcome ID")
    initiative_id: str = Field(description="ID of the initiative")
    outcome: OutcomeType = Field(description="Result of the initiative")
    notes: Optional[str] = Field(default=None, description="Additional context about the outcome")
    vote_breakdown: Optional[dict] = Field(
        default=None,
        description="Vote details (e.g., {'yes': 4, 'no': 1})"
    )
    decision_reference: Optional[str] = Field(
        default=None,
        description="Reference to civic data decision (e.g., decision ID)"
    )
    recorded_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"frozen": True}


class Attribution(BaseModel):
    """
    Links a user's action to an initiative outcome or activity milestone.

    Two types:
    - **Outcome-based**: Generated when an initiative reaches a decision.
      "Your comment helped influence this 4-1 vote."
    - **Activity-based**: Generated immediately on action completion.
      "You submitted a written comment (3 of 10 target)."
      outcome_id is None for activity-based attributions.
    """

    id: str = Field(description="Unique attribution ID")
    outcome_id: Optional[str] = Field(
        default=None,
        description="Reference to the outcome (None for activity-based attributions)"
    )
    action_id: str = Field(description="Reference to the action event")
    public_key: str = Field(description="User's public key (hex-encoded)")
    contribution_type: ContributionType = Field(
        description="How the user contributed (commitment or completion)"
    )
    message: Optional[str] = Field(
        default=None,
        description="Personalized attribution message"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"frozen": True}

    @property
    def is_activity_based(self) -> bool:
        return self.outcome_id is None
