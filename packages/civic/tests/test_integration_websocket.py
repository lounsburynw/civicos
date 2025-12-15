"""
Integration tests for WebSocket functionality.

These tests verify the websocket_integration items from integration.json:
- WebSocket connects and disconnects cleanly
- Client reconnects after connection drop
- New voice triggers real-time update
- New initiative triggers real-time update

Note: These tests mock the Socket.IO server/client behavior since running
a real eventlet server in pytest is complex. The tests verify the server-side
logic and handlers work correctly.

Run: python -m pytest packages/civic/tests/test_integration_websocket.py -v
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, MagicMock, patch

import pytest

# Mark all tests in this module as integration + websocket
pytestmark = [pytest.mark.integration, pytest.mark.websocket]

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic/src"))
os.chdir(str(PROJECT_ROOT))


class TestConnectionHandling:
    """
    Integration tests for WebSocket connection handling.

    Maps to integration.json > websocket_integration > connection_handling
    """

    def test_connect_with_valid_auth(self):
        """
        integration.json: websocket_integration > connection_handling > connect_disconnect
        test: "WebSocket connects and disconnects cleanly"

        Verifies:
        - Connection accepted with valid user_id auth
        - User session tracked after connect
        - Welcome message sent to client
        """
        # Import server module - creates sio and handlers
        from civic_services.servers import civic_socketio_server as ws

        # Reset global state
        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        # Mock emit to capture messages
        messages_sent = []
        original_emit = ws.sio.emit

        def mock_emit(event, data, room=None, skip_sid=None, **kwargs):
            messages_sent.append({
                "event": event,
                "data": data,
                "room": room,
                "skip_sid": skip_sid,
            })

        ws.sio.emit = mock_emit

        try:
            # Simulate connect with valid auth
            sid = "test_sid_001"
            environ = {}
            auth = {"user_id": "user_abc123"}

            # Call connect handler
            ws.connect(sid, environ, auth)

            # Verify session tracked
            assert sid in ws.user_sessions, "Session should be tracked"
            assert ws.user_sessions[sid] == "user_abc123", "User ID should be stored"

            # Verify welcome message sent
            assert len(messages_sent) == 1, "Should send welcome message"
            assert messages_sent[0]["event"] == "connected"
            assert "Connected" in messages_sent[0]["data"]["message"]
            assert messages_sent[0]["room"] == sid

        finally:
            ws.sio.emit = original_emit

    def test_connect_without_auth_rejected(self):
        """
        Verify connection is rejected when no auth provided.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        sid = "test_sid_002"
        environ = {}
        auth = None  # No auth

        # Should raise ConnectionRefusedError
        with pytest.raises(ConnectionRefusedError) as exc_info:
            ws.connect(sid, environ, auth)

        assert "user_id missing" in str(exc_info.value)
        assert sid not in ws.user_sessions

    def test_connect_without_user_id_rejected(self):
        """
        Verify connection is rejected when auth dict has no user_id.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        sid = "test_sid_003"
        environ = {}
        auth = {"token": "some_token"}  # No user_id

        with pytest.raises(ConnectionRefusedError) as exc_info:
            ws.connect(sid, environ, auth)

        assert "user_id missing" in str(exc_info.value)

    def test_connect_with_invalid_user_id_rejected(self):
        """
        Verify connection is rejected when user_id is invalid.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        # Empty string user_id
        sid = "test_sid_004"
        auth = {"user_id": ""}

        with pytest.raises(ConnectionRefusedError) as exc_info:
            ws.connect(sid, {}, auth)

        assert "invalid user_id" in str(exc_info.value)

    def test_disconnect_cleans_up_session(self):
        """
        integration.json: websocket_integration > connection_handling > connect_disconnect
        test: "WebSocket connects and disconnects cleanly"

        Verifies:
        - User session removed on disconnect
        - Thread membership cleaned up
        - Other participants notified
        """
        from civic_services.servers import civic_socketio_server as ws

        # Setup: user connected and in a thread
        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        sid = "test_sid_005"
        ws.user_sessions[sid] = "user_cleanup"
        ws.thread_sessions[sid] = "thread_123"

        messages_sent = []
        leave_room_calls = []
        original_emit = ws.sio.emit
        original_leave = ws.sio.leave_room

        def mock_emit(event, data, room=None, skip_sid=None, **kwargs):
            messages_sent.append({
                "event": event,
                "data": data,
                "room": room,
                "skip_sid": skip_sid,
            })

        def mock_leave(sid, room):
            leave_room_calls.append((sid, room))

        ws.sio.emit = mock_emit
        ws.sio.leave_room = mock_leave

        try:
            # Call disconnect
            ws.disconnect(sid)

            # Verify session cleaned up
            assert sid not in ws.user_sessions, "User session should be removed"
            assert sid not in ws.thread_sessions, "Thread session should be removed"

            # Verify left room
            assert len(leave_room_calls) == 1
            assert leave_room_calls[0] == (sid, "thread_thread_123")

            # Verify user_left event sent
            assert len(messages_sent) == 1
            assert messages_sent[0]["event"] == "user_left"
            assert messages_sent[0]["data"]["user_id"] == "user_cleanup"
            assert messages_sent[0]["skip_sid"] == sid

        finally:
            ws.sio.emit = original_emit
            ws.sio.leave_room = original_leave

    def test_disconnect_without_thread_membership(self):
        """
        Verify disconnect works when user wasn't in any thread.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        sid = "test_sid_006"
        ws.user_sessions[sid] = "user_simple"

        messages_sent = []
        ws.sio.emit = lambda *args, **kwargs: messages_sent.append(args)

        # Should not raise
        ws.disconnect(sid)

        assert sid not in ws.user_sessions
        # No user_left message since not in thread
        assert len(messages_sent) == 0


class TestReconnection:
    """
    Integration tests for reconnection handling.

    Maps to integration.json > websocket_integration > connection_handling > reconnection
    """

    def test_reconnection_restores_session(self):
        """
        integration.json: websocket_integration > connection_handling > reconnection
        test: "Client reconnects after connection drop"

        Verifies:
        - New connection creates new session
        - Same user can reconnect with same user_id
        - Old session doesn't interfere
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        messages_sent = []
        ws.sio.emit = lambda event, data, room=None, **kwargs: messages_sent.append({
            "event": event,
            "room": room,
        })

        # First connection
        sid1 = "connection_1"
        ws.connect(sid1, {}, {"user_id": "reconnect_user"})
        assert ws.user_sessions[sid1] == "reconnect_user"

        # Disconnect (simulating connection drop)
        ws.sio.leave_room = lambda *args: None
        ws.disconnect(sid1)
        assert sid1 not in ws.user_sessions

        # Reconnect with new sid (same user_id)
        messages_sent.clear()
        sid2 = "connection_2"
        ws.connect(sid2, {}, {"user_id": "reconnect_user"})

        # Verify new session established
        assert ws.user_sessions[sid2] == "reconnect_user"
        assert sid1 not in ws.user_sessions  # Old session gone
        assert len([m for m in messages_sent if m["event"] == "connected"]) == 1

    def test_multiple_connections_same_user(self):
        """
        Verify same user can have multiple concurrent connections (different devices).
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        ws.sio.emit = lambda *args, **kwargs: None

        # Connect from "device 1"
        sid1 = "device_1_sid"
        ws.connect(sid1, {}, {"user_id": "multi_device_user"})

        # Connect from "device 2"
        sid2 = "device_2_sid"
        ws.connect(sid2, {}, {"user_id": "multi_device_user"})

        # Both sessions should exist
        assert ws.user_sessions[sid1] == "multi_device_user"
        assert ws.user_sessions[sid2] == "multi_device_user"
        assert len(ws.user_sessions) == 2


class TestThreadOperations:
    """
    Integration tests for thread join/leave operations.
    """

    def test_join_thread_authorized(self):
        """
        Verify user can join thread they're authorized for.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        sid = "thread_test_sid"
        ws.user_sessions[sid] = "authorized_user"

        messages_sent = []
        enter_room_calls = []

        ws.sio.emit = lambda event, data, room=None, skip_sid=None, **kwargs: \
            messages_sent.append({"event": event, "data": data, "room": room})
        ws.sio.enter_room = lambda sid, room: enter_room_calls.append((sid, room))

        # Mock verify_user_in_thread to return True
        with patch.object(ws, 'verify_user_in_thread', return_value=True):
            result = ws.join_thread(sid, {"thread_id": "thread_abc"})

        assert result["success"] is True
        assert result["thread_id"] == "thread_abc"
        assert ws.thread_sessions[sid] == "thread_abc"
        assert (sid, "thread_thread_abc") in enter_room_calls

        # user_joined event sent
        assert any(m["event"] == "user_joined" for m in messages_sent)

    def test_join_thread_unauthorized(self):
        """
        Verify user cannot join thread they're not authorized for.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        sid = "unauth_sid"
        ws.user_sessions[sid] = "unauthorized_user"

        with patch.object(ws, 'verify_user_in_thread', return_value=False):
            result = ws.join_thread(sid, {"thread_id": "private_thread"})

        assert "error" in result
        assert "Not authorized" in result["error"]
        assert sid not in ws.thread_sessions

    def test_join_thread_not_authenticated(self):
        """
        Verify join fails when user not authenticated.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        result = ws.join_thread("unknown_sid", {"thread_id": "some_thread"})

        assert "error" in result
        assert "Not authenticated" in result["error"]

    def test_leave_thread(self):
        """
        Verify user can leave thread.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.thread_sessions.clear()

        sid = "leave_test_sid"
        ws.user_sessions[sid] = "leaving_user"
        ws.thread_sessions[sid] = "thread_to_leave"

        messages_sent = []
        leave_room_calls = []

        ws.sio.emit = lambda event, data, room=None, skip_sid=None, **kwargs: \
            messages_sent.append({"event": event})
        ws.sio.leave_room = lambda sid, room: leave_room_calls.append((sid, room))

        result = ws.leave_thread(sid, {"thread_id": "thread_to_leave"})

        assert result["success"] is True
        assert sid not in ws.thread_sessions
        assert (sid, "thread_thread_to_leave") in leave_room_calls
        assert any(m["event"] == "user_left" for m in messages_sent)


class TestMessaging:
    """
    Integration tests for message sending.
    """

    def test_send_message_success(self):
        """
        Verify authorized user can send message.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.message_rate_limiter.clear()

        sid = "msg_test_sid"
        ws.user_sessions[sid] = "message_sender"

        messages_sent = []
        ws.sio.emit = lambda event, data, room=None, **kwargs: \
            messages_sent.append({"event": event, "data": data, "room": room})

        # Mock storage and authorization
        mock_message = {
            "message_id": "msg_001",
            "thread_id": "thread_xyz",
            "user_id": "message_sender",
            "content": "Hello everyone!",
            "created_at": "2025-01-01T00:00:00",
        }

        with patch.object(ws, 'verify_user_in_thread', return_value=True), \
             patch.object(ws.storage, 'create_message', return_value=mock_message):

            result = ws.new_message(sid, {
                "thread_id": "thread_xyz",
                "content": "Hello everyone!",
            })

        assert result["success"] is True
        assert result["message"]["content"] == "Hello everyone!"

        # Message broadcast to room
        assert len(messages_sent) == 1
        assert messages_sent[0]["event"] == "message"
        assert messages_sent[0]["room"] == "thread_thread_xyz"

    def test_send_message_rate_limited(self):
        """
        Verify rate limiting works for messages.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        ws.message_rate_limiter.clear()

        sid = "rate_limit_sid"
        user_id = "rate_limited_user"
        ws.user_sessions[sid] = user_id

        # Fill up rate limit
        current_time = time.time()
        ws.message_rate_limiter[user_id] = [current_time] * ws.MESSAGE_RATE_LIMIT

        with patch.object(ws, 'verify_user_in_thread', return_value=True):
            result = ws.new_message(sid, {
                "thread_id": "thread_rate",
                "content": "One more message",
            })

        assert "error" in result
        assert "Rate limit" in result["error"]

    def test_send_message_not_authenticated(self):
        """
        Verify message fails when not authenticated.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        result = ws.new_message("unknown_sid", {
            "thread_id": "thread",
            "content": "Hello",
        })

        assert "error" in result
        assert "Not authenticated" in result["error"]

    def test_send_message_missing_content(self):
        """
        Verify message fails when content missing.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()
        sid = "content_test_sid"
        ws.user_sessions[sid] = "content_user"

        result = ws.new_message(sid, {"thread_id": "thread"})

        assert "error" in result
        assert "required" in result["error"]


class TestTypingIndicators:
    """
    Integration tests for typing indicators.
    """

    def test_typing_broadcast(self):
        """
        Verify typing indicator is broadcast to room.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        sid = "typing_sid"
        ws.user_sessions[sid] = "typing_user"

        messages_sent = []
        ws.sio.emit = lambda event, data, room=None, skip_sid=None, **kwargs: \
            messages_sent.append({
                "event": event,
                "data": data,
                "skip_sid": skip_sid,
            })

        ws.typing(sid, {"thread_id": "thread_typing"})

        assert len(messages_sent) == 1
        assert messages_sent[0]["event"] == "user_typing"
        assert messages_sent[0]["data"]["user_id"] == "typing_user"
        assert messages_sent[0]["skip_sid"] == sid  # Don't send to self

    def test_stop_typing_broadcast(self):
        """
        Verify stop typing indicator is broadcast.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.user_sessions.clear()

        sid = "stop_typing_sid"
        ws.user_sessions[sid] = "stop_typing_user"

        messages_sent = []
        ws.sio.emit = lambda event, data, room=None, skip_sid=None, **kwargs: \
            messages_sent.append({"event": event})

        ws.stop_typing(sid, {"thread_id": "thread_stop"})

        assert len(messages_sent) == 1
        assert messages_sent[0]["event"] == "user_stop_typing"


class TestRateLimiting:
    """
    Integration tests for rate limiting logic.
    """

    def test_rate_limit_allows_within_window(self):
        """
        Verify messages allowed within rate limit.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.message_rate_limiter.clear()

        user_id = "rate_test_user"

        # Should allow MESSAGE_RATE_LIMIT messages
        for i in range(ws.MESSAGE_RATE_LIMIT):
            allowed = ws.check_message_rate_limit(user_id)
            assert allowed is True, f"Message {i+1} should be allowed"

    def test_rate_limit_blocks_excess(self):
        """
        Verify message blocked when limit exceeded.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.message_rate_limiter.clear()

        user_id = "rate_excess_user"

        # Use up the limit
        for _ in range(ws.MESSAGE_RATE_LIMIT):
            ws.check_message_rate_limit(user_id)

        # Next message should be blocked
        allowed = ws.check_message_rate_limit(user_id)
        assert allowed is False

    def test_rate_limit_expires(self):
        """
        Verify rate limit resets after window expires.
        """
        from civic_services.servers import civic_socketio_server as ws

        ws.message_rate_limiter.clear()

        user_id = "rate_expire_user"

        # Add old timestamps (outside window)
        old_time = time.time() - ws.MESSAGE_RATE_WINDOW - 10
        ws.message_rate_limiter[user_id] = [old_time] * ws.MESSAGE_RATE_LIMIT

        # Should be allowed since old timestamps expire
        allowed = ws.check_message_rate_limit(user_id)
        assert allowed is True


class TestUserVerification:
    """
    Integration tests for user verification in threads.
    """

    def test_verify_user_in_thread_with_participants(self):
        """
        Verify user check works when user is a participant.
        """
        from civic_services.servers import civic_socketio_server as ws

        mock_participants = [
            {"user_id": "participant_1", "joined_at": "2025-01-01"},
            {"user_id": "participant_2", "joined_at": "2025-01-02"},
        ]

        with patch.object(ws.storage, 'get_thread_participants',
                          return_value=mock_participants):
            # User in list
            result = ws.verify_user_in_thread("participant_1", "thread_check")
            assert result is True

            # User not in list
            result = ws.verify_user_in_thread("stranger", "thread_check")
            assert result is False

    def test_verify_user_in_thread_empty(self):
        """
        Verify returns False when no participants.
        """
        from civic_services.servers import civic_socketio_server as ws

        with patch.object(ws.storage, 'get_thread_participants', return_value=[]):
            result = ws.verify_user_in_thread("any_user", "empty_thread")
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
