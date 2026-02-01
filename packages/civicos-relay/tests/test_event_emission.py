"""Tests for event emission service."""

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
from civicos_relay.relay.event_emission import EventEmitter, EmissionResult
from civicos_relay.storage.memory import (
    InMemoryEventStorage,
    InMemorySubscriptionStorage,
)


class MockEventStorage:
    """Mock event storage that tracks saves."""

    def __init__(self):
        self._events: list[Event] = []
        self._delivery_counts: dict[int, tuple[int, int]] = {}
        self._next_id = 1

    def save_event(self, event: Event) -> int:
        self._events.append(event)
        event_id = self._next_id
        self._next_id += 1
        return event_id

    def update_delivery_counts(
        self, event_id: int, attempted: int, succeeded: int
    ) -> None:
        self._delivery_counts[event_id] = (attempted, succeeded)


class MockDelivery:
    """Mock delivery that tracks calls."""

    def __init__(self, success: bool = True):
        self.deliveries: list[tuple[Event, Subscription]] = []
        self._success = success

    def deliver(self, event: Event, subscription: Subscription) -> bool:
        self.deliveries.append((event, subscription))
        return self._success


class TestEventEmitter:
    """Tests for EventEmitter."""

    def test_emit_saves_event(self):
        """Emitting saves the event to storage."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing"],
            title="Approved ADU Development",
        )

        assert result.event_id == 1
        assert len(event_storage._events) == 1
        assert event_storage._events[0].type == EventType.DECISION_MADE
        assert event_storage._events[0].jurisdiction == "city-san-rafael"

    def test_emit_matches_subscriptions(self):
        """Emitting matches and delivers to subscriptions."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Create subscription for housing topics
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing", "zoning"],
            title="Approved ADU Development",
        )

        assert result.matched == 1
        assert result.delivered == 1
        assert len(delivery.deliveries) == 1

    def test_emit_no_match(self):
        """Events not matching criteria are not delivered."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Subscribe to housing
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        # Emit transportation event
        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:456",
            topics=["transportation"],
            title="Bus Route Change",
        )

        assert result.matched == 0
        assert result.delivered == 0
        assert len(delivery.deliveries) == 0

    def test_emit_queues_without_delivery(self):
        """Without delivery handler, events are queued."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage, delivery=None)

        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing"],
            title="Approved ADU Development",
        )

        assert result.matched == 1
        assert result.delivered == 0  # No delivery without handler
        assert len(emitter.get_pending_deliveries()) == 1

    def test_clear_pending_deliveries(self):
        """Can clear pending deliveries."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage, delivery=None)

        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing"],
            title="Test",
        )

        count = emitter.clear_pending_deliveries()
        assert count == 1
        assert len(emitter.get_pending_deliveries()) == 0

    def test_emit_updates_delivery_counts(self):
        """Emitting updates delivery counts in storage."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery(success=True)
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing"],
            title="Test",
        )

        assert result.event_id in event_storage._delivery_counts
        attempted, succeeded = event_storage._delivery_counts[result.event_id]
        assert attempted == 1
        assert succeeded == 1

    def test_delivery_failure_tracked(self):
        """Failed deliveries are tracked correctly."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery(success=False)
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        result = emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing"],
            title="Test",
        )

        assert result.matched == 1
        assert result.delivered == 0  # Delivery failed
        attempted, succeeded = event_storage._delivery_counts[result.event_id]
        assert attempted == 1
        assert succeeded == 0


class TestEventTypes:
    """Tests for each event type convenience method."""

    def test_emit_agenda_published(self):
        """Can emit agenda_published event."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_agenda_published(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:agenda:2026-02-03",
            topics=["housing", "budget"],
            title="City Council Regular Meeting",
            meeting_date=datetime(2026, 2, 3, 19, 0),
        )

        assert result.event_id == 1
        event = event_storage._events[0]
        assert event.type == EventType.AGENDA_PUBLISHED
        assert event.data["topics"] == ["housing", "budget"]
        assert event.data["title"] == "City Council Regular Meeting"
        assert "meeting_date" in event.data

    def test_emit_meeting_scheduled(self):
        """Can emit meeting_scheduled event."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_meeting_scheduled(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:meeting:2026-02-10",
            title="Planning Commission",
            meeting_date=datetime(2026, 2, 10, 18, 30),
        )

        assert result.event_id == 1
        event = event_storage._events[0]
        assert event.type == EventType.MEETING_SCHEDULED

    def test_emit_initiative_created(self):
        """Can emit initiative_created event."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_initiative_created(
            jurisdiction="city-san-rafael",
            entity="initiative:city-san-rafael:2026-01:abc123",
            topic="traffic safety",
            title="Add crosswalk on 4th Street",
            description="Requesting a new crosswalk at 4th and B Street.",
        )

        assert result.event_id == 1
        event = event_storage._events[0]
        assert event.type == EventType.INITIATIVE_CREATED
        assert event.data["topics"] == ["traffic safety"]
        assert event.data["title"] == "Add crosswalk on 4th Street"

    def test_emit_voice_threshold_reached(self):
        """Can emit voice_threshold_reached event."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_voice_threshold_reached(
            jurisdiction="city-san-rafael",
            entity="initiative:city-san-rafael:2026-01:abc123",
            voice_count=100,
            threshold=100,
            topic="traffic safety",
        )

        assert result.event_id == 1
        event = event_storage._events[0]
        assert event.type == EventType.VOICE_THRESHOLD_REACHED
        assert event.data["voice_count"] == 100
        assert event.data["threshold"] == 100

    def test_emit_public_comment_opened(self):
        """Can emit public_comment_opened event."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_public_comment_opened(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:item:2026-02-03:12",
            title="Proposed Zoning Amendment",
            deadline=datetime(2026, 2, 10, 17, 0),
            topics=["zoning"],
        )

        assert result.event_id == 1
        event = event_storage._events[0]
        assert event.type == EventType.PUBLIC_COMMENT_OPENED

    def test_emit_public_comment_closing(self):
        """Can emit public_comment_closing event."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        emitter = EventEmitter(event_storage, sub_storage)

        result = emitter.emit_public_comment_closing(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:item:2026-02-03:12",
            title="Proposed Zoning Amendment",
            deadline=datetime(2026, 2, 10, 17, 0),
            topics=["zoning"],
        )

        assert result.event_id == 1
        event = event_storage._events[0]
        assert event.type == EventType.PUBLIC_COMMENT_CLOSING


class TestSubscriptionMatching:
    """Tests for subscription matching logic."""

    def test_match_event_type(self):
        """Matches by event type."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Subscribe only to decision events
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(event_types=[EventType.DECISION_MADE]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        # Emit agenda event (should not match)
        emitter.emit_agenda_published(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:agenda:2026-02-03",
        )

        assert len(delivery.deliveries) == 0

        # Emit decision event (should match)
        emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
        )

        assert len(delivery.deliveries) == 1

    def test_match_entity(self):
        """Matches by entity."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Subscribe to specific entity
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(
                entities=["city-san-rafael:initiative:abc123"]
            ),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        # Emit event for different entity (should not match)
        emitter.emit_voice_threshold_reached(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:initiative:xyz789",
            voice_count=50,
            threshold=50,
        )

        assert len(delivery.deliveries) == 0

        # Emit event for matching entity
        emitter.emit_voice_threshold_reached(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:initiative:abc123",
            voice_count=100,
            threshold=100,
        )

        assert len(delivery.deliveries) == 1

    def test_match_voice_threshold(self):
        """Matches by voice threshold."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Subscribe with minimum voice threshold
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(voice_threshold=100),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        # Emit with voice count below threshold
        emitter.emit_voice_threshold_reached(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:initiative:abc123",
            voice_count=50,
            threshold=50,
        )

        assert len(delivery.deliveries) == 0

        # Emit with voice count meeting threshold
        emitter.emit_voice_threshold_reached(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:initiative:abc123",
            voice_count=100,
            threshold=100,
        )

        assert len(delivery.deliveries) == 1

    def test_match_geography(self):
        """Matches by geographic proximity."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Subscribe with geographic filter (San Rafael downtown)
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(
                geography={"lat": 37.9735, "lng": -122.5311, "radius_miles": 1.0}
            ),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )
        sub_storage.save_subscription(sub)

        # Emit event far away (should not match)
        emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            location={"lat": 37.7749, "lng": -122.4194},  # SF
        )

        assert len(delivery.deliveries) == 0

        # Emit event nearby (should match)
        emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:456",
            location={"lat": 37.9740, "lng": -122.5300},  # Near downtown SR
        )

        assert len(delivery.deliveries) == 1

    def test_inactive_subscription_not_matched(self):
        """Inactive subscriptions are not matched."""
        event_storage = MockEventStorage()
        sub_storage = InMemorySubscriptionStorage()
        delivery = MockDelivery()
        emitter = EventEmitter(event_storage, sub_storage, delivery)

        # Create inactive subscription
        sub = Subscription(
            id="sub_001",
            jurisdiction="city-san-rafael",
            match=MatchCriteria(topics=["housing"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
            active=False,
        )
        sub_storage.save_subscription(sub)

        emitter.emit_decision_made(
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-01-15:123",
            topics=["housing"],
        )

        assert len(delivery.deliveries) == 0


class TestInMemoryEventStorage:
    """Tests for InMemoryEventStorage (used in testing)."""

    def test_save_and_get_events(self):
        """Can save and retrieve events."""
        storage = InMemoryEventStorage()

        event = Event(
            type=EventType.DECISION_MADE,
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:123",
            data={"topics": ["housing"]},
        )
        storage.save_event(event)

        events, cursor = storage.get_events_since(
            since=datetime(2020, 1, 1),
            namespace=None,
            limit=10,
        )

        assert len(events) == 1
        assert events[0].type == EventType.DECISION_MADE

    def test_import_event_duplicate(self):
        """Import detects duplicates."""
        storage = InMemoryEventStorage()

        event = Event(
            type=EventType.DECISION_MADE,
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:123",
            timestamp=datetime(2026, 1, 15, 12, 0),
        )

        # First import
        result = storage.import_event(event)
        assert result == "accepted"

        # Duplicate import
        result = storage.import_event(event)
        assert result == "duplicate"
