"""
Tests for NIP-01 WebSocket relay.

Verifies:
- Message parsing and handling (EVENT, REQ, CLOSE)
- Subscription management and filtering
- Event broadcasting
- Rate limiting
- Connection lifecycle
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from civicos_relay.nostr import (
    NostrKeyPair,
    CivicVoiceEvent,
    Stance,
    CIVIC_VOICE,
    CIVIC_ENTITY,
    EventFilter,
)
from civicos_relay.nostr.relay import (
    NostrRelay,
    Connection,
    Subscription,
)


@pytest.fixture
def mock_storage():
    """Create a mock storage for testing."""
    storage = MagicMock()
    storage.save_event.return_value = (True, "accepted")
    storage.query_events.return_value = []
    storage.count_events.return_value = 0
    return storage


@pytest.fixture
def relay(mock_storage):
    """Create a relay with mock storage."""
    return NostrRelay(mock_storage)


class TestConnection:
    """Tests for Connection dataclass."""

    def test_connection_creation(self):
        """Can create a connection."""
        conn = Connection(id="test-conn")
        assert conn.id == "test-conn"
        assert len(conn.subscriptions) == 0

    def test_add_subscription(self):
        """Can add subscriptions."""
        conn = Connection(id="test-conn")
        filters = [EventFilter(kinds=[CIVIC_VOICE])]
        conn.add_subscription("sub1", filters)

        assert "sub1" in conn.subscriptions
        assert conn.subscriptions["sub1"].filters == filters

    def test_replace_subscription(self):
        """Adding same sub_id replaces existing."""
        conn = Connection(id="test-conn")
        conn.add_subscription("sub1", [EventFilter(kinds=[1])])
        conn.add_subscription("sub1", [EventFilter(kinds=[2])])

        assert len(conn.subscriptions) == 1
        assert conn.subscriptions["sub1"].filters[0].kinds == [2]

    def test_remove_subscription(self):
        """Can remove subscriptions."""
        conn = Connection(id="test-conn")
        conn.add_subscription("sub1", [])

        assert conn.remove_subscription("sub1")
        assert "sub1" not in conn.subscriptions
        assert not conn.remove_subscription("sub1")  # Already removed


class TestRelayEventHandling:
    """Tests for EVENT message handling."""

    @pytest.mark.asyncio
    async def test_handle_valid_event(self, relay, mock_storage):
        """Relay accepts valid events."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        send = AsyncMock()
        message = json.dumps(["EVENT", voice.to_dict()])

        await relay.handle_message("conn1", message, send)

        # Should send OK
        send.assert_called_once()
        response = json.loads(send.call_args[0][0])
        assert response[0] == "OK"
        assert response[1] == voice.id
        assert response[2] is True  # success

        # Should save event
        mock_storage.save_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self, relay):
        """Relay handles invalid JSON."""
        send = AsyncMock()

        await relay.handle_message("conn1", "not json", send)

        send.assert_called_once()
        response = json.loads(send.call_args[0][0])
        assert response[0] == "NOTICE"
        assert "Invalid JSON" in response[1]

    @pytest.mark.asyncio
    async def test_handle_invalid_message_format(self, relay):
        """Relay handles invalid message format."""
        send = AsyncMock()

        await relay.handle_message("conn1", json.dumps("not an array"), send)

        send.assert_called_once()
        response = json.loads(send.call_args[0][0])
        assert response[0] == "NOTICE"

    @pytest.mark.asyncio
    async def test_handle_event_rejected(self, relay, mock_storage):
        """Relay rejects events that fail storage."""
        mock_storage.save_event.return_value = (False, "rejected:invalid_signature")

        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        send = AsyncMock()
        message = json.dumps(["EVENT", voice.to_dict()])

        await relay.handle_message("conn1", message, send)

        response = json.loads(send.call_args[0][0])
        assert response[0] == "OK"
        assert response[2] is False  # rejected
        assert "invalid_signature" in response[3]

    @pytest.mark.asyncio
    async def test_rate_limiting(self, relay, mock_storage):
        """Relay enforces rate limits."""
        relay._rate_limit = 5  # 5 events per second

        kp = NostrKeyPair.generate()
        send = AsyncMock()

        # Send more than rate limit
        for i in range(10):
            voice = CivicVoiceEvent.create(
                keypair=kp,
                entity_id=f"test-entity-{i}",
                jurisdiction="test-j",
                stance=Stance.SUPPORT,
            )
            message = json.dumps(["EVENT", voice.to_dict()])
            await relay.handle_message("conn1", message, send)

        # Some should be rate limited
        calls = send.call_args_list
        ok_responses = [
            json.loads(c[0][0])
            for c in calls
            if json.loads(c[0][0])[0] == "OK"
        ]

        rejected = [r for r in ok_responses if not r[2]]
        assert len(rejected) > 0
        assert any("rate-limited" in r[3] for r in rejected)


class TestRelaySubscriptions:
    """Tests for REQ/CLOSE message handling."""

    @pytest.mark.asyncio
    async def test_handle_req_creates_subscription(self, relay):
        """REQ creates a subscription."""
        send = AsyncMock()
        message = json.dumps([
            "REQ",
            "sub1",
            {"kinds": [CIVIC_VOICE], "#j": ["city-san-rafael"]}
        ])

        await relay.handle_message("conn1", message, send)

        # Should send EOSE (no stored events)
        response = json.loads(send.call_args[0][0])
        assert response[0] == "EOSE"
        assert response[1] == "sub1"

        # Subscription should be stored
        conn = relay._connections["conn1"]
        assert "sub1" in conn.subscriptions

    @pytest.mark.asyncio
    async def test_handle_req_sends_stored_events(self, relay, mock_storage):
        """REQ sends matching stored events."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )
        mock_storage.query_events.return_value = [voice]

        send = AsyncMock()
        message = json.dumps(["REQ", "sub1", {"kinds": [CIVIC_VOICE]}])

        await relay.handle_message("conn1", message, send)

        # Should send EVENT then EOSE
        assert send.call_count == 2

        event_call = json.loads(send.call_args_list[0][0][0])
        assert event_call[0] == "EVENT"
        assert event_call[1] == "sub1"
        assert event_call[2]["id"] == voice.id

        eose_call = json.loads(send.call_args_list[1][0][0])
        assert eose_call[0] == "EOSE"

    @pytest.mark.asyncio
    async def test_handle_close(self, relay):
        """CLOSE removes subscription."""
        send = AsyncMock()

        # First create subscription
        await relay.handle_message(
            "conn1",
            json.dumps(["REQ", "sub1", {"kinds": [1]}]),
            send,
        )

        # Then close it
        send.reset_mock()
        await relay.handle_message(
            "conn1",
            json.dumps(["CLOSE", "sub1"]),
            send,
        )

        response = json.loads(send.call_args[0][0])
        assert response[0] == "CLOSED"
        assert response[1] == "sub1"

        conn = relay._connections["conn1"]
        assert "sub1" not in conn.subscriptions

    @pytest.mark.asyncio
    async def test_subscription_limit(self, relay):
        """Relay enforces subscription limits."""
        relay._max_subscriptions = 3

        send = AsyncMock()

        # Create max subscriptions
        for i in range(3):
            await relay.handle_message(
                "conn1",
                json.dumps(["REQ", f"sub{i}", {"kinds": [1]}]),
                send,
            )

        # Fourth should be rejected
        send.reset_mock()
        await relay.handle_message(
            "conn1",
            json.dumps(["REQ", "sub_extra", {"kinds": [1]}]),
            send,
        )

        response = json.loads(send.call_args[0][0])
        assert response[0] == "NOTICE"
        assert "Too many subscriptions" in response[1]


class TestRelayEventBroadcast:
    """Tests for event broadcasting to subscribers."""

    @pytest.mark.asyncio
    async def test_broadcast_to_matching_subscriptions(self, relay, mock_storage):
        """Events are broadcast to matching subscriptions."""
        # Set up two connections with different subscriptions
        send1 = AsyncMock()
        send2 = AsyncMock()

        # Connection 1 subscribes to voices
        await relay.handle_message(
            "conn1",
            json.dumps(["REQ", "voices", {"kinds": [CIVIC_VOICE]}]),
            send1,
        )

        # Connection 2 subscribes to entities
        await relay.handle_message(
            "conn2",
            json.dumps(["REQ", "entities", {"kinds": [CIVIC_ENTITY]}]),
            send2,
        )

        send1.reset_mock()
        send2.reset_mock()

        # Publish a voice event from conn3
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        send3 = AsyncMock()
        await relay.handle_message(
            "conn3",
            json.dumps(["EVENT", voice.to_dict()]),
            send3,
        )

        # conn1 should receive broadcast (matches voices)
        # Wait for async broadcast
        await asyncio.sleep(0.01)

        # Check conn1 received the event
        calls1 = [c for c in send1.call_args_list
                  if "EVENT" in c[0][0]]
        assert len(calls1) == 1

        # conn2 should NOT receive (doesn't match entities filter)
        calls2 = [c for c in send2.call_args_list
                  if "EVENT" in c[0][0]]
        assert len(calls2) == 0

    @pytest.mark.asyncio
    async def test_no_self_broadcast(self, relay, mock_storage):
        """Publisher doesn't receive their own event broadcast."""
        send1 = AsyncMock()

        # Subscribe
        await relay.handle_message(
            "conn1",
            json.dumps(["REQ", "all", {"kinds": [CIVIC_VOICE]}]),
            send1,
        )

        send1.reset_mock()

        # Publish from same connection
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        await relay.handle_message(
            "conn1",
            json.dumps(["EVENT", voice.to_dict()]),
            send1,
        )

        # Should only receive OK, not EVENT broadcast
        calls = send1.call_args_list
        messages = [json.loads(c[0][0]) for c in calls]

        ok_messages = [m for m in messages if m[0] == "OK"]
        event_broadcasts = [m for m in messages if m[0] == "EVENT"]

        assert len(ok_messages) == 1
        assert len(event_broadcasts) == 0


class TestRelayFilterMatching:
    """Tests for subscription filter matching."""

    @pytest.mark.asyncio
    async def test_filter_by_kind(self, relay):
        """Filter matches by kind."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        filter_match = EventFilter(kinds=[CIVIC_VOICE])
        filter_no_match = EventFilter(kinds=[CIVIC_ENTITY])

        assert relay._event_matches_filter(voice, filter_match)
        assert not relay._event_matches_filter(voice, filter_no_match)

    @pytest.mark.asyncio
    async def test_filter_by_author(self, relay):
        """Filter matches by author pubkey."""
        kp1 = NostrKeyPair.generate()
        kp2 = NostrKeyPair.generate()

        voice = CivicVoiceEvent.create(
            keypair=kp1,
            entity_id="test",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        filter_match = EventFilter(authors=[kp1.public_key_hex])
        filter_no_match = EventFilter(authors=[kp2.public_key_hex])

        assert relay._event_matches_filter(voice, filter_match)
        assert not relay._event_matches_filter(voice, filter_no_match)

    @pytest.mark.asyncio
    async def test_filter_by_tag(self, relay):
        """Filter matches by tag values."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="city-san-rafael",
            stance=Stance.SUPPORT,
            topics=["housing"],
        )

        filter_j_match = EventFilter(tag_filters={"j": ["city-san-rafael"]})
        filter_j_no_match = EventFilter(tag_filters={"j": ["city-other"]})
        filter_t_match = EventFilter(tag_filters={"t": ["housing"]})

        assert relay._event_matches_filter(voice, filter_j_match)
        assert not relay._event_matches_filter(voice, filter_j_no_match)
        assert relay._event_matches_filter(voice, filter_t_match)

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self, relay):
        """Filter matches by time range."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
            created_at=1500,
        )

        filter_in_range = EventFilter(since=1000, until=2000)
        filter_before = EventFilter(until=1000)
        filter_after = EventFilter(since=2000)

        assert relay._event_matches_filter(voice, filter_in_range)
        assert not relay._event_matches_filter(voice, filter_before)
        assert not relay._event_matches_filter(voice, filter_after)

    @pytest.mark.asyncio
    async def test_filter_combined(self, relay):
        """Filter with multiple criteria requires all to match."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test",
            jurisdiction="city-san-rafael",
            stance=Stance.SUPPORT,
            created_at=1500,
        )

        # All criteria match
        filter_all_match = EventFilter(
            kinds=[CIVIC_VOICE],
            authors=[kp.public_key_hex],
            tag_filters={"j": ["city-san-rafael"]},
            since=1000,
            until=2000,
        )
        assert relay._event_matches_filter(voice, filter_all_match)

        # One criterion doesn't match
        filter_kind_wrong = EventFilter(
            kinds=[CIVIC_ENTITY],  # Wrong kind
            authors=[kp.public_key_hex],
        )
        assert not relay._event_matches_filter(voice, filter_kind_wrong)


class TestRelayLifecycle:
    """Tests for connection lifecycle management."""

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self, relay):
        """Disconnect cleans up connection state."""
        send = AsyncMock()

        # Create connection and subscription
        await relay.handle_message(
            "conn1",
            json.dumps(["REQ", "sub1", {"kinds": [1]}]),
            send,
        )

        assert "conn1" in relay._connections

        # Disconnect
        relay.disconnect("conn1")

        assert "conn1" not in relay._connections
        assert "conn1" not in relay._connection_senders

    @pytest.mark.asyncio
    async def test_get_stats(self, relay, mock_storage):
        """Can get relay statistics."""
        send1 = AsyncMock()
        send2 = AsyncMock()

        # Create connections with subscriptions
        await relay.handle_message(
            "conn1",
            json.dumps(["REQ", "sub1", {"kinds": [1]}]),
            send1,
        )
        await relay.handle_message(
            "conn2",
            json.dumps(["REQ", "sub2", {"kinds": [2]}]),
            send2,
        )

        stats = relay.get_stats()

        assert stats["connections"] == 2
        assert stats["subscriptions"] == 2


class TestVoiceEventCallback:
    """Tests for civic-specific voice event processing."""

    @pytest.mark.asyncio
    async def test_voice_callback_triggered(self, mock_storage):
        """Voice event callback is triggered on voice events."""
        callback = AsyncMock()
        relay = NostrRelay(mock_storage, on_voice_event=callback)

        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        send = AsyncMock()
        await relay.handle_message(
            "conn1",
            json.dumps(["EVENT", voice.to_dict()]),
            send,
        )

        callback.assert_called_once()
        called_event = callback.call_args[0][0]
        assert called_event.id == voice.id

    @pytest.mark.asyncio
    async def test_callback_not_triggered_for_non_voice(self, mock_storage):
        """Voice callback not triggered for non-voice events."""
        callback = AsyncMock()
        relay = NostrRelay(mock_storage, on_voice_event=callback)

        # Create a non-voice event (regular note)
        from civicos_relay.nostr.crypto import sign_event
        from civicos_relay.nostr.models import NostrEvent

        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(kp, 1000, 1, [], "Hello")

        event = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=1,  # Regular note, not voice
            tags=[],
            content="Hello",
            sig=sig,
        )

        send = AsyncMock()
        await relay.handle_message(
            "conn1",
            json.dumps(["EVENT", event.to_dict()]),
            send,
        )

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_error_doesnt_break_relay(self, mock_storage):
        """Callback errors don't prevent event storage."""
        callback = AsyncMock(side_effect=Exception("Callback error"))
        relay = NostrRelay(mock_storage, on_voice_event=callback)

        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        send = AsyncMock()
        await relay.handle_message(
            "conn1",
            json.dumps(["EVENT", voice.to_dict()]),
            send,
        )

        # Event should still be accepted
        response = json.loads(send.call_args[0][0])
        assert response[0] == "OK"
        assert response[2] is True
