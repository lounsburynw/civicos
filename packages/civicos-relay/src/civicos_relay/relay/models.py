"""Relay data models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of civic events the relay can emit."""

    AGENDA_PUBLISHED = "agenda_published"
    DECISION_MADE = "decision_made"
    MEETING_SCHEDULED = "meeting_scheduled"
    PUBLIC_COMMENT_OPENED = "public_comment_opened"
    PUBLIC_COMMENT_CLOSING = "public_comment_closing"
    VOICE_THRESHOLD_REACHED = "voice_threshold_reached"
    INITIATIVE_CREATED = "initiative_created"


class Event(BaseModel):
    """
    A civic event emitted by the relay.

    Events are triggered by civic activity (agendas published, decisions made, etc.)
    and routed to matching subscriptions.
    """

    type: EventType
    jurisdiction: str = Field(description="e.g., 'city-san-rafael'")
    entity: str = Field(description="Entity identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict = Field(default_factory=dict, description="Event-specific payload")

    model_config = {"frozen": True}


class DeliveryMethod(str, Enum):
    """How to deliver events to subscribers."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    # Future: SMS, NTFY, MCP


class MatchCriteria(BaseModel):
    """Criteria for matching events to subscriptions."""

    topics: Optional[list[str]] = Field(
        default=None, description="Match events with any of these topics"
    )
    event_types: Optional[list[EventType]] = Field(
        default=None, description="Match specific event types"
    )
    entities: Optional[list[str]] = Field(
        default=None, description="Match specific entities"
    )
    geography: Optional[dict] = Field(
        default=None, description="Geographic filter (lat, lng, radius_miles)"
    )
    voice_threshold: Optional[int] = Field(
        default=None, description="Minimum voice count to trigger"
    )


class DeliveryConfig(BaseModel):
    """Configuration for event delivery."""

    method: DeliveryMethod
    address: str = Field(description="Email address or webhook URL")


class Subscription(BaseModel):
    """
    A subscription to civic events.

    Subscriptions define what events a user wants to receive and how to deliver them.
    """

    id: str = Field(description="Unique subscription ID")
    jurisdiction: str
    match: MatchCriteria
    delivery: DeliveryConfig
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)
    # Link to key for voice-related notifications (optional)
    public_key: Optional[str] = Field(default=None)
