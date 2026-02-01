"""Event emission service - emits events and routes to subscribers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from civicos_relay.relay.models import Event, EventType


class EventStorage(Protocol):
    """Protocol for event persistence."""

    def save_event(self, event: Event) -> int:
        """Store an event. Returns the event ID."""
        ...

    def update_delivery_counts(
        self, event_id: int, attempted: int, succeeded: int
    ) -> None:
        """Update delivery counts for an event."""
        ...


class SubscriptionStorage(Protocol):
    """Protocol for subscription queries."""

    def get_subscriptions_for_jurisdiction(self, jurisdiction: str) -> list:
        """Get all active subscriptions for a jurisdiction."""
        ...


class EventDelivery(Protocol):
    """Protocol for delivering events to subscribers."""

    def deliver(self, event: Event, subscription) -> bool:
        """Deliver an event to a subscriber. Returns True on success."""
        ...


@dataclass(frozen=True)
class EmissionResult:
    """Result of emitting an event."""

    event_id: int
    matched: int
    delivered: int


class EventEmitter:
    """
    Service for emitting civic events.

    Orchestrates:
    1. Save event to storage (coordination_events_log)
    2. Find matching subscriptions
    3. Deliver to subscribers (or queue for batch delivery)
    4. Update delivery counts

    Usage:
        emitter = EventEmitter(event_storage, subscription_storage, delivery)
        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing", "zoning"],
            title="Approved ADU Development",
        )
        print(f"Delivered to {result.delivered} subscribers")
    """

    def __init__(
        self,
        event_storage: EventStorage,
        subscription_storage: SubscriptionStorage,
        delivery: Optional[EventDelivery] = None,
    ):
        self._event_storage = event_storage
        self._subscription_storage = subscription_storage
        self._delivery = delivery
        self._pending_deliveries: list[tuple[Event, object]] = []

    def emit(self, event: Event) -> EmissionResult:
        """
        Emit a raw event.

        Saves to storage, matches subscriptions, and queues/delivers.
        """
        # 1. Save event to storage
        event_id = self._event_storage.save_event(event)

        # 2. Find matching subscriptions
        subscriptions = self._subscription_storage.get_subscriptions_for_jurisdiction(
            event.jurisdiction
        )
        matched = []
        for sub in subscriptions:
            if not sub.active:
                continue
            if self._matches(event, sub.match):
                matched.append(sub)

        # 3. Deliver or queue
        delivered = 0
        if self._delivery:
            for sub in matched:
                if self._delivery.deliver(event, sub):
                    delivered += 1
        else:
            # Queue for batch delivery
            for sub in matched:
                self._pending_deliveries.append((event, sub))

        # 4. Update delivery counts
        self._event_storage.update_delivery_counts(
            event_id, attempted=len(matched), succeeded=delivered
        )

        return EmissionResult(
            event_id=event_id,
            matched=len(matched),
            delivered=delivered,
        )

    def _matches(self, event: Event, criteria) -> bool:
        """Check if an event matches subscription criteria."""
        # Event type filter
        if criteria.event_types:
            if event.type not in criteria.event_types:
                return False

        # Topic filter
        if criteria.topics:
            event_topics = event.data.get("topics", [])
            if not any(t in event_topics for t in criteria.topics):
                return False

        # Entity filter
        if criteria.entities:
            if event.entity not in criteria.entities:
                return False

        # Geography filter
        if criteria.geography:
            event_location = event.data.get("location")
            if event_location:
                if not self._within_radius(event_location, criteria.geography):
                    return False

        # Voice threshold
        if criteria.voice_threshold:
            if event.type == EventType.VOICE_THRESHOLD_REACHED:
                voice_count = event.data.get("voice_count", 0)
                if voice_count < criteria.voice_threshold:
                    return False

        return True

    def _within_radius(self, location: dict, geo_filter: dict) -> bool:
        """Check if location is within radius using Haversine formula."""
        import math

        lat1, lng1 = location.get("lat"), location.get("lng")
        lat2, lng2 = geo_filter.get("lat"), geo_filter.get("lng")
        radius = geo_filter.get("radius_miles", 1.0)

        if not all([lat1, lng1, lat2, lng2]):
            return True

        R = 3959  # Earth radius in miles
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlng / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        return distance <= radius

    def get_pending_deliveries(self) -> list[tuple[Event, object]]:
        """Get pending deliveries for batch processing."""
        return list(self._pending_deliveries)

    def clear_pending_deliveries(self) -> int:
        """Clear pending deliveries. Returns count cleared."""
        count = len(self._pending_deliveries)
        self._pending_deliveries.clear()
        return count

    # Convenience methods for common event types

    def emit_agenda_published(
        self,
        jurisdiction: str,
        entity: str,
        topics: Optional[list[str]] = None,
        title: Optional[str] = None,
        meeting_date: Optional[datetime] = None,
        location: Optional[dict] = None,
    ) -> EmissionResult:
        """Emit an AGENDA_PUBLISHED event."""
        data = {}
        if topics:
            data["topics"] = topics
        if title:
            data["title"] = title
        if meeting_date:
            data["meeting_date"] = meeting_date.isoformat()
        if location:
            data["location"] = location

        event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)

    def emit_decision_made(
        self,
        jurisdiction: str,
        entity: str,
        topics: Optional[list[str]] = None,
        title: Optional[str] = None,
        outcome: Optional[str] = None,
        location: Optional[dict] = None,
    ) -> EmissionResult:
        """Emit a DECISION_MADE event."""
        data = {}
        if topics:
            data["topics"] = topics
        if title:
            data["title"] = title
        if outcome:
            data["outcome"] = outcome
        if location:
            data["location"] = location

        event = Event(
            type=EventType.DECISION_MADE,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)

    def emit_meeting_scheduled(
        self,
        jurisdiction: str,
        entity: str,
        title: Optional[str] = None,
        meeting_date: Optional[datetime] = None,
        location: Optional[dict] = None,
    ) -> EmissionResult:
        """Emit a MEETING_SCHEDULED event."""
        data = {}
        if title:
            data["title"] = title
        if meeting_date:
            data["meeting_date"] = meeting_date.isoformat()
        if location:
            data["location"] = location

        event = Event(
            type=EventType.MEETING_SCHEDULED,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)

    def emit_initiative_created(
        self,
        jurisdiction: str,
        entity: str,
        topic: str,
        title: str,
        description: Optional[str] = None,
        location: Optional[dict] = None,
    ) -> EmissionResult:
        """Emit an INITIATIVE_CREATED event."""
        data = {
            "topics": [topic],
            "title": title,
        }
        if description:
            data["description"] = description
        if location:
            data["location"] = location

        event = Event(
            type=EventType.INITIATIVE_CREATED,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)

    def emit_voice_threshold_reached(
        self,
        jurisdiction: str,
        entity: str,
        voice_count: int,
        threshold: int,
        topic: Optional[str] = None,
    ) -> EmissionResult:
        """Emit a VOICE_THRESHOLD_REACHED event."""
        data = {
            "voice_count": voice_count,
            "threshold": threshold,
        }
        if topic:
            data["topics"] = [topic]

        event = Event(
            type=EventType.VOICE_THRESHOLD_REACHED,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)

    def emit_public_comment_opened(
        self,
        jurisdiction: str,
        entity: str,
        title: Optional[str] = None,
        deadline: Optional[datetime] = None,
        topics: Optional[list[str]] = None,
    ) -> EmissionResult:
        """Emit a PUBLIC_COMMENT_OPENED event."""
        data = {}
        if title:
            data["title"] = title
        if deadline:
            data["deadline"] = deadline.isoformat()
        if topics:
            data["topics"] = topics

        event = Event(
            type=EventType.PUBLIC_COMMENT_OPENED,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)

    def emit_public_comment_closing(
        self,
        jurisdiction: str,
        entity: str,
        title: Optional[str] = None,
        deadline: Optional[datetime] = None,
        topics: Optional[list[str]] = None,
    ) -> EmissionResult:
        """Emit a PUBLIC_COMMENT_CLOSING event."""
        data = {}
        if title:
            data["title"] = title
        if deadline:
            data["deadline"] = deadline.isoformat()
        if topics:
            data["topics"] = topics

        event = Event(
            type=EventType.PUBLIC_COMMENT_CLOSING,
            jurisdiction=jurisdiction,
            entity=entity,
            data=data,
        )
        return self.emit(event)
