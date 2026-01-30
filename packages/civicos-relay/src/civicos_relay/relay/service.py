"""Relay service - event routing and subscription management."""

import uuid
from typing import Optional, Protocol

from civicos_relay.relay.models import (
    Event,
    EventType,
    Subscription,
    MatchCriteria,
    DeliveryConfig,
)


class SubscriptionStorage(Protocol):
    """Protocol for subscription persistence."""

    def save_subscription(self, subscription: Subscription) -> None:
        """Store a subscription."""
        ...

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get a subscription by ID."""
        ...

    def get_subscriptions_for_jurisdiction(
        self, jurisdiction: str
    ) -> list[Subscription]:
        """Get all active subscriptions for a jurisdiction."""
        ...

    def deactivate_subscription(self, subscription_id: str) -> bool:
        """Deactivate a subscription. Returns True if it existed."""
        ...


class EventDelivery(Protocol):
    """Protocol for delivering events to subscribers."""

    def deliver(self, event: Event, subscription: Subscription) -> bool:
        """Deliver an event. Returns True on success."""
        ...


class RelayService:
    """
    Service for managing civic event relay.

    Handles subscription management and event routing.
    """

    def __init__(self, storage: SubscriptionStorage, delivery: EventDelivery):
        self._storage = storage
        self._delivery = delivery

    def subscribe(
        self,
        jurisdiction: str,
        match: MatchCriteria,
        delivery: DeliveryConfig,
        public_key: Optional[str] = None,
    ) -> Subscription:
        """Create a new subscription."""
        subscription = Subscription(
            id=f"sub_{uuid.uuid4().hex[:12]}",
            jurisdiction=jurisdiction,
            match=match,
            delivery=delivery,
            public_key=public_key,
        )
        self._storage.save_subscription(subscription)
        return subscription

    def unsubscribe(self, subscription_id: str) -> bool:
        """Deactivate a subscription."""
        return self._storage.deactivate_subscription(subscription_id)

    def emit(self, event: Event) -> int:
        """
        Emit an event to all matching subscribers.

        Returns the number of successful deliveries.
        """
        subscriptions = self._storage.get_subscriptions_for_jurisdiction(
            event.jurisdiction
        )
        delivered = 0

        for sub in subscriptions:
            if not sub.active:
                continue
            if self._matches(event, sub.match):
                if self._delivery.deliver(event, sub):
                    delivered += 1

        return delivered

    def _matches(self, event: Event, criteria: MatchCriteria) -> bool:
        """Check if an event matches subscription criteria."""
        # Event type filter
        if criteria.event_types:
            if event.type not in criteria.event_types:
                return False

        # Topic filter (check event data for topics)
        if criteria.topics:
            event_topics = event.data.get("topics", [])
            if not any(t in event_topics for t in criteria.topics):
                return False

        # Entity filter
        if criteria.entities:
            if event.entity not in criteria.entities:
                return False

        # Geography filter (MVP: simple radius check)
        if criteria.geography:
            event_location = event.data.get("location")
            if event_location:
                if not self._within_radius(event_location, criteria.geography):
                    return False

        # Voice threshold (only for threshold events)
        if criteria.voice_threshold:
            if event.type == EventType.VOICE_THRESHOLD_REACHED:
                voice_count = event.data.get("voice_count", 0)
                if voice_count < criteria.voice_threshold:
                    return False

        return True

    def _within_radius(self, location: dict, geo_filter: dict) -> bool:
        """Check if location is within radius. MVP: simple distance calc."""
        import math

        lat1, lng1 = location.get("lat"), location.get("lng")
        lat2, lng2 = geo_filter.get("lat"), geo_filter.get("lng")
        radius = geo_filter.get("radius_miles", 1.0)

        if not all([lat1, lng1, lat2, lng2]):
            return True  # No location data, don't filter

        # Haversine formula (approximate)
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
