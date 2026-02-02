"""
NIP-01 WebSocket relay for Nostr events.

Implements the core Nostr relay protocol:
- EVENT: Receive and store events
- REQ: Subscribe to events matching filters
- CLOSE: Unsubscribe from a subscription

References:
- NIP-01: https://github.com/nostr-protocol/nips/blob/master/01.md
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from collections import defaultdict
from weakref import WeakSet

from civicos_relay.nostr.models import NostrEvent, parse_event
from civicos_relay.nostr.storage import NostrEventStorage, EventFilter
from civicos_relay.nostr.kinds import CIVIC_VOICE, is_civic_kind

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """A client subscription with filters."""

    sub_id: str
    filters: list[EventFilter]
    created_at: float = field(default_factory=time.time)


@dataclass
class Connection:
    """A WebSocket connection with its subscriptions."""

    id: str
    subscriptions: dict[str, Subscription] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_event_at: float = field(default_factory=time.time)
    event_count: int = 0

    def add_subscription(self, sub_id: str, filters: list[EventFilter]) -> None:
        """Add or replace a subscription."""
        self.subscriptions[sub_id] = Subscription(sub_id=sub_id, filters=filters)

    def remove_subscription(self, sub_id: str) -> bool:
        """Remove a subscription. Returns True if it existed."""
        if sub_id in self.subscriptions:
            del self.subscriptions[sub_id]
            return True
        return False


class NostrRelay:
    """
    NIP-01 compliant Nostr relay with civic extensions.

    Handles WebSocket connections, event storage, and subscription matching.
    """

    def __init__(
        self,
        storage: NostrEventStorage,
        max_subscriptions_per_connection: int = 20,
        max_filters_per_subscription: int = 10,
        max_events_per_second: int = 100,
        on_voice_event: Callable[[NostrEvent], Awaitable[None]] | None = None,
    ):
        self._storage = storage
        self._max_subscriptions = max_subscriptions_per_connection
        self._max_filters = max_filters_per_subscription
        self._rate_limit = max_events_per_second

        # Connection tracking
        self._connections: dict[str, Connection] = {}
        self._connection_senders: dict[str, Callable[[str], Awaitable[None]]] = {}

        # Event callback for civic-specific processing
        self._on_voice_event = on_voice_event

        # Rate limiting
        self._event_counts: dict[str, list[float]] = defaultdict(list)

    async def handle_message(
        self,
        connection_id: str,
        message: str,
        send: Callable[[str], Awaitable[None]],
    ) -> None:
        """
        Handle an incoming WebSocket message.

        NIP-01 message types:
        - ["EVENT", <event>]: Publish an event
        - ["REQ", <sub_id>, <filters>...]: Subscribe to events
        - ["CLOSE", <sub_id>]: Unsubscribe
        """
        # Ensure connection is tracked
        if connection_id not in self._connections:
            self._connections[connection_id] = Connection(id=connection_id)
            self._connection_senders[connection_id] = send

        try:
            data = json.loads(message)
            if not isinstance(data, list) or len(data) < 2:
                await send(json.dumps(["NOTICE", "Invalid message format"]))
                return

            msg_type = data[0]

            if msg_type == "EVENT":
                await self._handle_event(connection_id, data, send)
            elif msg_type == "REQ":
                await self._handle_req(connection_id, data, send)
            elif msg_type == "CLOSE":
                await self._handle_close(connection_id, data, send)
            else:
                await send(json.dumps(["NOTICE", f"Unknown message type: {msg_type}"]))

        except json.JSONDecodeError:
            await send(json.dumps(["NOTICE", "Invalid JSON"]))
        except Exception as e:
            logger.exception(f"Error handling message from {connection_id}")
            await send(json.dumps(["NOTICE", f"Internal error: {str(e)}"]))

    async def _handle_event(
        self,
        connection_id: str,
        data: list,
        send: Callable[[str], Awaitable[None]],
    ) -> None:
        """Handle EVENT message - store and broadcast event."""
        if len(data) < 2:
            await send(json.dumps(["NOTICE", "EVENT requires event object"]))
            return

        event_data = data[1]
        if not isinstance(event_data, dict):
            await send(json.dumps(["NOTICE", "Event must be an object"]))
            return

        # Rate limiting
        if not self._check_rate_limit(connection_id):
            event_id = event_data.get("id", "unknown")
            await send(json.dumps(["OK", event_id, False, "rate-limited: slow down"]))
            return

        try:
            # Parse and validate event
            event = parse_event(event_data)

            # Store event
            success, message = self._storage.save_event(event)

            if success:
                # Send OK
                await send(json.dumps(["OK", event.id, True, ""]))

                # Broadcast to matching subscriptions
                await self._broadcast_event(event, exclude_connection=connection_id)

                # Trigger civic-specific processing
                if self._on_voice_event and event.kind == CIVIC_VOICE:
                    try:
                        await self._on_voice_event(event)
                    except Exception as e:
                        logger.exception(f"Error in voice event callback: {e}")

                # Update connection stats
                conn = self._connections.get(connection_id)
                if conn:
                    conn.event_count += 1
                    conn.last_event_at = time.time()
            else:
                # Send rejection
                reason = message.replace("rejected:", "")
                await send(json.dumps(["OK", event.id, False, reason]))

        except ValueError as e:
            event_id = event_data.get("id", "unknown")
            await send(json.dumps(["OK", event_id, False, f"invalid: {str(e)}"]))

    async def _handle_req(
        self,
        connection_id: str,
        data: list,
        send: Callable[[str], Awaitable[None]],
    ) -> None:
        """Handle REQ message - subscribe to events."""
        if len(data) < 3:
            await send(json.dumps(["NOTICE", "REQ requires subscription_id and filters"]))
            return

        sub_id = data[1]
        if not isinstance(sub_id, str):
            await send(json.dumps(["NOTICE", "Subscription ID must be a string"]))
            return

        conn = self._connections.get(connection_id)
        if not conn:
            return

        # Check subscription limits
        if len(conn.subscriptions) >= self._max_subscriptions and sub_id not in conn.subscriptions:
            await send(json.dumps(["NOTICE", "Too many subscriptions"]))
            return

        # Parse filters (all remaining array elements)
        filters = []
        for i, filter_data in enumerate(data[2:]):
            if i >= self._max_filters:
                await send(json.dumps(["NOTICE", "Too many filters in subscription"]))
                return

            if not isinstance(filter_data, dict):
                await send(json.dumps(["NOTICE", "Filter must be an object"]))
                return

            filters.append(EventFilter.from_dict(filter_data))

        # Store subscription
        conn.add_subscription(sub_id, filters)

        # Send matching stored events
        for filter in filters:
            events = self._storage.query_events(filter)
            for event in events:
                await send(json.dumps(["EVENT", sub_id, event.to_dict()]))

        # Send EOSE (End Of Stored Events)
        await send(json.dumps(["EOSE", sub_id]))

    async def _handle_close(
        self,
        connection_id: str,
        data: list,
        send: Callable[[str], Awaitable[None]],
    ) -> None:
        """Handle CLOSE message - unsubscribe."""
        if len(data) < 2:
            await send(json.dumps(["NOTICE", "CLOSE requires subscription_id"]))
            return

        sub_id = data[1]
        conn = self._connections.get(connection_id)
        if conn:
            conn.remove_subscription(sub_id)

        await send(json.dumps(["CLOSED", sub_id, ""]))

    async def _broadcast_event(
        self,
        event: NostrEvent,
        exclude_connection: str | None = None,
    ) -> None:
        """Broadcast an event to all matching subscriptions."""
        for conn_id, conn in list(self._connections.items()):
            if conn_id == exclude_connection:
                continue

            send = self._connection_senders.get(conn_id)
            if not send:
                continue

            for sub in conn.subscriptions.values():
                if self._event_matches_subscription(event, sub):
                    try:
                        await send(json.dumps(["EVENT", sub.sub_id, event.to_dict()]))
                    except Exception:
                        # Connection may be closed
                        pass
                    break  # Only send once per connection

    def _event_matches_subscription(
        self, event: NostrEvent, subscription: Subscription
    ) -> bool:
        """Check if an event matches any filter in a subscription."""
        for filter in subscription.filters:
            if self._event_matches_filter(event, filter):
                return True
        return False

    def _event_matches_filter(self, event: NostrEvent, filter: EventFilter) -> bool:
        """Check if an event matches a single filter."""
        # Check IDs
        if filter.ids and event.id not in filter.ids:
            return False

        # Check authors
        if filter.authors and event.pubkey not in filter.authors:
            return False

        # Check kinds
        if filter.kinds and event.kind not in filter.kinds:
            return False

        # Check time range
        if filter.since and event.created_at < filter.since:
            return False
        if filter.until and event.created_at > filter.until:
            return False

        # Check tag filters
        if filter.tag_filters:
            for tag_name, values in filter.tag_filters.items():
                event_values = event.get_tags(tag_name)
                if not event_values:
                    # Also check denormalized fields
                    if tag_name == "d":
                        d_tag = event.get_d_tag()
                        if d_tag and d_tag in values:
                            continue
                    return False
                if not any(v in values for v in event_values):
                    return False

        return True

    def _check_rate_limit(self, connection_id: str) -> bool:
        """Check if connection is within rate limits."""
        now = time.time()
        window = 1.0  # 1 second window

        # Get timestamps within window
        timestamps = self._event_counts[connection_id]
        timestamps = [t for t in timestamps if now - t < window]
        self._event_counts[connection_id] = timestamps

        if len(timestamps) >= self._rate_limit:
            return False

        timestamps.append(now)
        return True

    def disconnect(self, connection_id: str) -> None:
        """Handle connection disconnect."""
        if connection_id in self._connections:
            del self._connections[connection_id]
        if connection_id in self._connection_senders:
            del self._connection_senders[connection_id]
        if connection_id in self._event_counts:
            del self._event_counts[connection_id]

    def get_stats(self) -> dict[str, Any]:
        """Get relay statistics."""
        total_subs = sum(
            len(c.subscriptions) for c in self._connections.values()
        )
        return {
            "connections": len(self._connections),
            "subscriptions": total_subs,
            "events_stored": self._storage.count_events(),
        }


# =============================================================================
# FastAPI WebSocket Integration
# =============================================================================


def create_websocket_handler(relay: NostrRelay):
    """
    Create a FastAPI WebSocket endpoint handler.

    Usage:
        relay = NostrRelay(storage)
        ws_handler = create_websocket_handler(relay)

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await ws_handler(websocket)
    """

    async def handler(websocket):
        """Handle a WebSocket connection."""
        from fastapi import WebSocket, WebSocketDisconnect

        await websocket.accept()
        connection_id = str(id(websocket))

        async def send(message: str):
            await websocket.send_text(message)

        try:
            while True:
                message = await websocket.receive_text()
                await relay.handle_message(connection_id, message, send)
        except WebSocketDisconnect:
            relay.disconnect(connection_id)
        except Exception:
            relay.disconnect(connection_id)
            raise

    return handler
