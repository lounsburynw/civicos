"""
Tests for civic_socketio_server.py — WebSocket server for coordination threads.

Tests the rate limiter, thread membership verification, connection lifecycle,
message handling, typing indicators, and health check endpoint. External
dependencies (storage, socketio) are mocked; all logic under test runs for real.

To run:
    pytest packages/civicos-services/tests/test_civic_socketio_server.py -q --override-ini="addopts="
"""

import sys
import pytest
from unittest.mock import patch, MagicMock
from time import time

# Pre-populate sys.modules with mocks for optional runtime dependencies
# that aren't available in the test environment. This must happen before
# importing the module under test.
_mock_socketio = MagicMock()
# Make the @sio.event decorator pass through the function unchanged
_mock_socketio.Server.return_value.event = lambda fn: fn
_mock_socketio.WSGIApp.return_value = MagicMock()

_mock_eventlet = MagicMock()

sys.modules.setdefault("socketio", _mock_socketio)
sys.modules.setdefault("eventlet", _mock_eventlet)

# Also mock CommunityStorage so module-level instantiation doesn't hit the DB
with patch("civicos_services.storage.issue_storage.CommunityStorage"):
    from civicos_services.servers.civic_socketio_server import (
        check_message_rate_limit,
        verify_user_in_thread,
        connect,
        disconnect,
        join_thread,
        leave_thread,
        new_message,
        typing,
        stop_typing,
        health_check,
        app_with_health,
        MESSAGE_RATE_LIMIT,
        MESSAGE_RATE_WINDOW,
        user_sessions,
        thread_sessions,
        message_rate_limiter,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_global_state():
    """Reset all module-level mutable state between tests."""
    user_sessions.clear()
    thread_sessions.clear()
    message_rate_limiter.clear()
    yield
    user_sessions.clear()
    thread_sessions.clear()
    message_rate_limiter.clear()


@pytest.fixture
def mock_storage():
    """Mock the storage module-level instance."""
    with patch("civicos_services.servers.civic_socketio_server.storage") as mock:
        yield mock


@pytest.fixture
def mock_sio():
    """Mock the socketio Server instance."""
    with patch("civicos_services.servers.civic_socketio_server.sio") as mock:
        yield mock


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

class TestCheckMessageRateLimit:
    def test_allows_first_message(self):
        result = check_message_rate_limit("user-1")
        assert result is True

    def test_allows_messages_up_to_limit(self):
        for i in range(MESSAGE_RATE_LIMIT):
            result = check_message_rate_limit("user-2")
            assert result is True

    def test_blocks_message_beyond_limit(self):
        for _ in range(MESSAGE_RATE_LIMIT):
            check_message_rate_limit("user-3")
        result = check_message_rate_limit("user-3")
        assert result is False

    def test_blocks_at_exactly_limit_plus_one(self):
        """Verify the boundary: 10th message allowed, 11th blocked."""
        results = [check_message_rate_limit("user-exact") for _ in range(MESSAGE_RATE_LIMIT + 1)]
        assert results[:MESSAGE_RATE_LIMIT] == [True] * MESSAGE_RATE_LIMIT
        assert results[MESSAGE_RATE_LIMIT] is False

    def test_different_users_have_independent_limits(self):
        for _ in range(MESSAGE_RATE_LIMIT):
            check_message_rate_limit("user-a")
        assert check_message_rate_limit("user-b") is True
        assert check_message_rate_limit("user-a") is False

    def test_expired_timestamps_are_pruned(self):
        user_id = "user-prune"
        old_time = time() - MESSAGE_RATE_WINDOW - 10
        message_rate_limiter[user_id] = [old_time] * MESSAGE_RATE_LIMIT
        result = check_message_rate_limit(user_id)
        assert result is True
        # Old timestamps removed, only the new one remains
        assert len(message_rate_limiter[user_id]) == 1

    def test_records_timestamp_on_allowed_message(self):
        before = time()
        check_message_rate_limit("user-ts")
        after = time()
        assert len(message_rate_limiter["user-ts"]) == 1
        recorded = message_rate_limiter["user-ts"][0]
        assert before <= recorded <= after


# ---------------------------------------------------------------------------
# Thread Membership Verification
# ---------------------------------------------------------------------------

class TestVerifyUserInThread:
    def test_returns_true_when_user_is_participant(self, mock_storage):
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice", "role": "member"},
            {"user_id": "bob", "role": "member"},
        ]
        assert verify_user_in_thread("alice", "thread-1") is True

    def test_returns_true_for_second_participant(self, mock_storage):
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice", "role": "member"},
            {"user_id": "bob", "role": "member"},
        ]
        assert verify_user_in_thread("bob", "thread-1") is True

    def test_returns_false_when_user_is_not_participant(self, mock_storage):
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice", "role": "member"},
        ]
        assert verify_user_in_thread("charlie", "thread-1") is False

    def test_returns_false_for_empty_participants(self, mock_storage):
        mock_storage.get_thread_participants.return_value = []
        assert verify_user_in_thread("alice", "empty-thread") is False

    def test_queries_correct_thread_id(self, mock_storage):
        mock_storage.get_thread_participants.return_value = []
        result = verify_user_in_thread("alice", "thread-99")
        assert result is False
        mock_storage.get_thread_participants.assert_called_once_with("thread-99")


# ---------------------------------------------------------------------------
# Connection Lifecycle
# ---------------------------------------------------------------------------

class TestConnect:
    def test_rejects_none_auth(self, mock_sio):
        with pytest.raises(ConnectionRefusedError, match="user_id missing"):
            connect("sid-1", {}, None)

    def test_rejects_auth_without_user_id_key(self, mock_sio):
        with pytest.raises(ConnectionRefusedError, match="user_id missing"):
            connect("sid-2", {}, {"token": "abc"})

    def test_rejects_empty_string_user_id(self, mock_sio):
        with pytest.raises(ConnectionRefusedError, match="invalid user_id"):
            connect("sid-3", {}, {"user_id": ""})

    def test_rejects_non_string_user_id(self, mock_sio):
        with pytest.raises(ConnectionRefusedError, match="invalid user_id"):
            connect("sid-4", {}, {"user_id": 12345})

    def test_stores_session_on_valid_auth(self, mock_sio):
        connect("sid-5", {}, {"user_id": "alice"})
        assert user_sessions["sid-5"] == "alice"

    def test_emits_welcome_message(self, mock_sio):
        connect("sid-6", {}, {"user_id": "bob"})
        assert user_sessions["sid-6"] == "bob"
        mock_sio.emit.assert_called_once_with(
            "connected",
            {"message": "Connected to Civic Coordination Server"},
            room="sid-6",
        )

    def test_does_not_store_session_on_rejection(self, mock_sio):
        with pytest.raises(ConnectionRefusedError):
            connect("sid-7", {}, None)
        assert "sid-7" not in user_sessions


class TestDisconnect:
    def test_cleans_up_user_session(self, mock_sio):
        user_sessions["sid-d1"] = "alice"
        disconnect("sid-d1")
        assert "sid-d1" not in user_sessions

    def test_leaves_thread_room_on_disconnect(self, mock_sio):
        user_sessions["sid-d2"] = "bob"
        thread_sessions["sid-d2"] = "thread-100"
        disconnect("sid-d2")
        mock_sio.leave_room.assert_called_once_with("sid-d2", "thread_thread-100")
        assert "sid-d2" not in thread_sessions
        assert "sid-d2" not in user_sessions

    def test_notifies_others_when_leaving_thread(self, mock_sio):
        user_sessions["sid-d3"] = "charlie"
        thread_sessions["sid-d3"] = "thread-200"
        disconnect("sid-d3")
        assert "sid-d3" not in user_sessions
        mock_sio.emit.assert_called_once_with(
            "user_left",
            {"user_id": "charlie"},
            room="thread_thread-200",
            skip_sid="sid-d3",
        )

    def test_handles_unknown_sid(self, mock_sio):
        disconnect("sid-unknown")
        assert "sid-unknown" not in user_sessions
        mock_sio.leave_room.assert_not_called()

    def test_no_thread_cleanup_when_not_in_thread(self, mock_sio):
        user_sessions["sid-d5"] = "alice"
        disconnect("sid-d5")
        assert "sid-d5" not in user_sessions
        mock_sio.leave_room.assert_not_called()
        mock_sio.emit.assert_not_called()


# ---------------------------------------------------------------------------
# Join Thread
# ---------------------------------------------------------------------------

class TestJoinThread:
    def test_returns_error_when_not_authenticated(self, mock_sio, mock_storage):
        result = join_thread("sid-j1", {"thread_id": "thread-1"})
        assert result == {"error": "Not authenticated"}

    def test_returns_error_when_missing_thread_id(self, mock_sio, mock_storage):
        user_sessions["sid-j2"] = "alice"
        result = join_thread("sid-j2", {})
        assert result == {"error": "thread_id required"}

    def test_returns_error_when_not_authorized(self, mock_sio, mock_storage):
        user_sessions["sid-j3"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "bob", "role": "member"}
        ]
        result = join_thread("sid-j3", {"thread_id": "thread-1"})
        assert result == {"error": "Not authorized to join this thread"}

    def test_joins_room_and_tracks_session(self, mock_sio, mock_storage):
        user_sessions["sid-j4"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice", "role": "member"}
        ]
        result = join_thread("sid-j4", {"thread_id": "thread-5"})
        assert result == {"success": True, "thread_id": "thread-5"}
        assert thread_sessions["sid-j4"] == "thread-5"
        mock_sio.enter_room.assert_called_once_with("sid-j4", "thread_thread-5")

    def test_notifies_other_participants_on_join(self, mock_sio, mock_storage):
        user_sessions["sid-j5"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice", "role": "member"}
        ]
        result = join_thread("sid-j5", {"thread_id": "thread-6"})
        assert result == {"success": True, "thread_id": "thread-6"}
        mock_sio.emit.assert_called_once_with(
            "user_joined",
            {"user_id": "alice"},
            room="thread_thread-6",
            skip_sid="sid-j5",
        )

    def test_does_not_track_session_when_unauthorized(self, mock_sio, mock_storage):
        user_sessions["sid-j6"] = "alice"
        mock_storage.get_thread_participants.return_value = []
        join_thread("sid-j6", {"thread_id": "thread-7"})
        assert "sid-j6" not in thread_sessions


# ---------------------------------------------------------------------------
# Leave Thread
# ---------------------------------------------------------------------------

class TestLeaveThread:
    def test_returns_error_when_not_authenticated(self, mock_sio):
        result = leave_thread("sid-l1", {"thread_id": "thread-1"})
        assert result == {"error": "Not authenticated"}

    def test_returns_error_when_missing_thread_id(self, mock_sio):
        user_sessions["sid-l2"] = "alice"
        result = leave_thread("sid-l2", {})
        assert result == {"error": "thread_id required"}

    def test_leaves_room_and_cleans_up_session(self, mock_sio):
        user_sessions["sid-l3"] = "alice"
        thread_sessions["sid-l3"] = "thread-10"
        result = leave_thread("sid-l3", {"thread_id": "thread-10"})
        assert result == {"success": True}
        assert "sid-l3" not in thread_sessions
        mock_sio.leave_room.assert_called_once_with("sid-l3", "thread_thread-10")

    def test_notifies_others_on_leave(self, mock_sio):
        user_sessions["sid-l4"] = "bob"
        thread_sessions["sid-l4"] = "thread-11"
        result = leave_thread("sid-l4", {"thread_id": "thread-11"})
        assert result == {"success": True}
        mock_sio.emit.assert_called_once_with(
            "user_left",
            {"user_id": "bob"},
            room="thread_thread-11",
            skip_sid="sid-l4",
        )

    def test_leave_without_prior_join_succeeds(self, mock_sio):
        user_sessions["sid-l5"] = "alice"
        # Not in thread_sessions — should still work
        result = leave_thread("sid-l5", {"thread_id": "thread-99"})
        assert result == {"success": True}


# ---------------------------------------------------------------------------
# New Message
# ---------------------------------------------------------------------------

class TestNewMessage:
    def test_returns_error_when_not_authenticated(self, mock_sio, mock_storage):
        result = new_message("sid-m1", {"thread_id": "t1", "content": "hi"})
        assert result == {"error": "Not authenticated"}

    def test_returns_error_when_missing_thread_id(self, mock_sio, mock_storage):
        user_sessions["sid-m2"] = "alice"
        result = new_message("sid-m2", {"content": "hi"})
        assert result == {"error": "thread_id and content required"}

    def test_returns_error_when_missing_content(self, mock_sio, mock_storage):
        user_sessions["sid-m3"] = "alice"
        result = new_message("sid-m3", {"thread_id": "t1"})
        assert result == {"error": "thread_id and content required"}

    def test_returns_error_when_content_is_empty_string(self, mock_sio, mock_storage):
        user_sessions["sid-m9"] = "alice"
        result = new_message("sid-m9", {"thread_id": "t1", "content": ""})
        assert result == {"error": "thread_id and content required"}

    def test_returns_error_when_rate_limited(self, mock_sio, mock_storage):
        user_sessions["sid-m4"] = "rate-user"
        now = time()
        message_rate_limiter["rate-user"] = [now] * MESSAGE_RATE_LIMIT
        result = new_message("sid-m4", {"thread_id": "t1", "content": "hi"})
        assert result == {
            "error": "Rate limit exceeded. Please wait before sending more messages."
        }

    def test_returns_error_when_not_authorized(self, mock_sio, mock_storage):
        user_sessions["sid-m5"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "bob"}
        ]
        result = new_message("sid-m5", {"thread_id": "t1", "content": "hi"})
        assert result == {"error": "Not authorized to send messages in this thread"}

    def test_creates_and_broadcasts_message(self, mock_sio, mock_storage):
        user_sessions["sid-m6"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice"}
        ]
        saved_message = {
            "id": "msg-1",
            "thread_id": "t1",
            "user_id": "alice",
            "content": "Hello!",
            "created_at": "2025-11-18T12:00:00",
        }
        mock_storage.create_message.return_value = saved_message

        result = new_message("sid-m6", {"thread_id": "t1", "content": "Hello!"})

        assert result == {"success": True, "message": saved_message}
        mock_storage.create_message.assert_called_once_with(
            "t1", "alice", "Hello!", None
        )
        mock_sio.emit.assert_called_once_with(
            "message", saved_message, room="thread_t1"
        )

    def test_passes_parent_message_id_for_replies(self, mock_sio, mock_storage):
        user_sessions["sid-m7"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice"}
        ]
        reply_msg = {"id": "msg-reply", "parent_message_id": "msg-parent"}
        mock_storage.create_message.return_value = reply_msg

        result = new_message("sid-m7", {
            "thread_id": "t1",
            "content": "Reply!",
            "parent_message_id": "msg-parent",
        })

        assert result == {"success": True, "message": reply_msg}
        mock_storage.create_message.assert_called_once_with(
            "t1", "alice", "Reply!", "msg-parent"
        )

    def test_returns_generic_error_on_database_failure(self, mock_sio, mock_storage):
        user_sessions["sid-m8"] = "alice"
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "alice"}
        ]
        mock_storage.create_message.side_effect = RuntimeError("DB connection lost")

        result = new_message("sid-m8", {"thread_id": "t1", "content": "hi"})

        # Must NOT leak internal error details to the client
        assert result == {"error": "Failed to save message"}

    def test_rate_limit_not_consumed_when_unauthorized(self, mock_sio, mock_storage):
        """Rate limit check runs before authorization — verify the ordering."""
        user_sessions["sid-m10"] = "limited-user"
        now = time()
        # Fill rate limit for this user
        message_rate_limiter["limited-user"] = [now] * MESSAGE_RATE_LIMIT
        # Even though user is authorized, rate limit blocks first
        mock_storage.get_thread_participants.return_value = [
            {"user_id": "limited-user"}
        ]
        result = new_message("sid-m10", {"thread_id": "t1", "content": "hi"})
        assert "Rate limit" in result["error"]
        # Storage should NOT have been called for authorization
        mock_storage.get_thread_participants.assert_not_called()


# ---------------------------------------------------------------------------
# Typing Indicators
# ---------------------------------------------------------------------------

class TestTyping:
    def test_broadcasts_typing_to_thread(self, mock_sio):
        user_sessions["sid-t1"] = "alice"
        typing("sid-t1", {"thread_id": "thread-99"})
        mock_sio.emit.assert_called_once_with(
            "user_typing",
            {"user_id": "alice", "thread_id": "thread-99"},
            room="thread_thread-99",
            skip_sid="sid-t1",
        )

    def test_no_broadcast_when_not_authenticated(self, mock_sio):
        typing("sid-t2", {"thread_id": "thread-99"})
        mock_sio.emit.assert_not_called()

    def test_no_broadcast_when_missing_thread_id(self, mock_sio):
        user_sessions["sid-t3"] = "alice"
        typing("sid-t3", {})
        mock_sio.emit.assert_not_called()


class TestStopTyping:
    def test_broadcasts_stop_typing_to_thread(self, mock_sio):
        user_sessions["sid-st1"] = "bob"
        stop_typing("sid-st1", {"thread_id": "thread-50"})
        mock_sio.emit.assert_called_once_with(
            "user_stop_typing",
            {"user_id": "bob", "thread_id": "thread-50"},
            room="thread_thread-50",
            skip_sid="sid-st1",
        )

    def test_no_broadcast_when_not_authenticated(self, mock_sio):
        stop_typing("sid-st2", {"thread_id": "thread-50"})
        mock_sio.emit.assert_not_called()

    def test_no_broadcast_when_missing_thread_id(self, mock_sio):
        user_sessions["sid-st3"] = "bob"
        stop_typing("sid-st3", {})
        mock_sio.emit.assert_not_called()


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_healthy_json_for_health_path(self):
        responses = []

        def capture_start_response(status, headers):
            responses.append((status, dict(headers)))

        result = health_check({"PATH_INFO": "/health"}, capture_start_response)

        expected_body = b'{"status": "healthy", "service": "civic-websocket"}'
        assert result == [expected_body]
        assert responses[0][0] == "200 OK"
        assert responses[0][1]["Content-Type"] == "application/json"
        assert int(responses[0][1]["Content-Length"]) == len(expected_body)

    def test_returns_none_for_non_health_path(self):
        result = health_check({"PATH_INFO": "/socket.io/"}, lambda s, h: None)
        assert result is None

    def test_returns_none_for_root_path(self):
        result = health_check({"PATH_INFO": "/"}, lambda s, h: None)
        assert result is None

    def test_returns_none_when_path_info_absent(self):
        result = health_check({}, lambda s, h: None)
        assert result is None


class TestAppWithHealth:
    def test_returns_health_response_for_health_path(self):
        responses = []

        def capture_start_response(status, headers):
            responses.append(status)

        result = app_with_health({"PATH_INFO": "/health"}, capture_start_response)
        assert result == [b'{"status": "healthy", "service": "civic-websocket"}']

    @patch("civicos_services.servers.civic_socketio_server.socketio_app")
    def test_delegates_to_socketio_for_non_health_path(self, mock_socketio_app):
        mock_socketio_app.return_value = [b"socketio response"]
        environ = {"PATH_INFO": "/socket.io/"}
        start_response = MagicMock()

        result = app_with_health(environ, start_response)

        assert result == [b"socketio response"]
        mock_socketio_app.assert_called_once_with(environ, start_response)


# ---------------------------------------------------------------------------
# Module Constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_rate_limit_is_10_messages(self):
        assert MESSAGE_RATE_LIMIT == 10

    def test_rate_window_is_60_seconds(self):
        assert MESSAGE_RATE_WINDOW == 60
