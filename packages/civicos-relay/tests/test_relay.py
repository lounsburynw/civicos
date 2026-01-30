"""Tests for relay module."""

import pytest
from datetime import datetime

from civicos_relay.relay.models import (
    Event,
    EventType,
    Subscription,
    MatchCriteria,
    DeliveryConfig,
    DeliveryMethod,
)
from civicos_relay.relay.service import RelayService


class MockSubscriptionStorage:
    """In-memory subscription storage for testing."""

    def __init__(self):
        self._subscriptions: dict[str, Subscription] = {}

    def save_subscription(self, subscription: Subscription) -> None:
        self._subscriptions[subscription.id] = subscription

    def get_subscription(self, subscription_id: str):
        return self._subscriptions.get(subscription_id)

    def get_subscriptions_for_jurisdiction(self, jurisdiction: str):
        return [
            s for s in self._subscriptions.values()
            if s.jurisdiction == jurisdiction and s.active
        ]

    def deactivate_subscription(self, subscription_id: str) -> bool:
        if subscription_id in self._subscriptions:
            sub = self._subscriptions[subscription_id]
            self._subscriptions[subscription_id] = Subscription(
                id=sub.id,
                jurisdiction=sub.jurisdiction,
                match=sub.match,
                delivery=sub.delivery,
                created_at=sub.created_at,
                active=False,
                public_key=sub.public_key,
            )
            return True
        return False


class MockEventDelivery:
    """Mock delivery that tracks calls."""

    def __init__(self):
        self.deliveries: list[tuple[Event, Subscription]] = []

    def deliver(self, event: Event, subscription: Subscription) -> bool:
        self.deliveries.append((event, subscription))
        return True


class TestRelayService:
    """Tests for relay service."""

    def test_subscribe(self):
        """Can create a subscription."""
        storage = MockSubscriptionStorage()
        delivery = MockEventDelivery()
        relay = RelayService(storage, delivery)

        sub = relay.subscribe(
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )

        assert sub.id.startswith("sub_")
        assert sub.jurisdiction == "city-san-rafael"
        assert sub.active is True

    def test_emit_matches_topic(self):
        """Events are delivered to matching subscriptions."""
        storage = MockSubscriptionStorage()
        delivery = MockEventDelivery()
        relay = RelayService(storage, delivery)

        # Create subscription for housing
        relay.subscribe(
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )

        # Emit housing event
        event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction="city-san-rafael",
            entity="agenda:2026-02-03",
            data={"topics": ["housing", "zoning"]},
        )

        delivered = relay.emit(event)

        assert delivered == 1
        assert len(delivery.deliveries) == 1

    def test_emit_no_match(self):
        """Events not matching criteria are not delivered."""
        storage = MockSubscriptionStorage()
        delivery = MockEventDelivery()
        relay = RelayService(storage, delivery)

        # Subscribe to housing
        relay.subscribe(
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )

        # Emit transportation event
        event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction="city-san-rafael",
            entity="agenda:2026-02-03",
            data={"topics": ["transportation"]},
        )

        delivered = relay.emit(event)

        assert delivered == 0
        assert len(delivery.deliveries) == 0

    def test_unsubscribe(self):
        """Can deactivate a subscription."""
        storage = MockSubscriptionStorage()
        delivery = MockEventDelivery()
        relay = RelayService(storage, delivery)

        sub = relay.subscribe(
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )

        result = relay.unsubscribe(sub.id)
        assert result is True

        # Event should not be delivered
        event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction="city-san-rafael",
            entity="agenda:2026-02-03",
            data={"topics": ["housing"]},
        )

        delivered = relay.emit(event)
        assert delivered == 0
