"""
Tests for session_manager.py — in-memory conversation session management.

The real ConversationSession / SessionManager are exercised end-to-end. The
only mocked boundary is the shared `config` singleton: the source imports it
via `from ..config import config`, which resolves to `civicos_services.config`.
We pre-seed `sys.modules` with a stub module that carries a tunable
`_FakeConfig` instance BEFORE importing session_manager, so the import
succeeds and tests can mutate the config values through `_fake_config.values`.

Time is pinned via monkeypatch on `session_manager.time.time` where the
behavior depends on a clock read; otherwise sessions use real time.

To run:
    pytest packages/civicos-services/tests/test_session_manager.py -q --override-ini="addopts="
"""

import json
import sys
import types
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Fake config, installed BEFORE importing session_manager.
# ---------------------------------------------------------------------------


class _FakeConfig:
    """Tunable stand-in for the global config singleton."""

    def __init__(self):
        self.values = {
            "max_sessions": 1000,
            "session_timeout_minutes": 60,
            "cleanup_interval_minutes": 15,
            "max_conversation_size_kb": 100,
        }

    def get_session_config(self):
        # Return a copy so in-place mutations don't leak between reads.
        return dict(self.values)


_fake_config = _FakeConfig()
_fake_config_module = types.ModuleType("civicos_services.config")
_fake_config_module.config = _fake_config
sys.modules["civicos_services.config"] = _fake_config_module


import civicos_services.utils.session_manager as sm_mod  # noqa: E402
from civicos_services.utils.session_manager import (  # noqa: E402
    ConversationSession,
    SessionManager,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_fake_config():
    """Reset fake config to defaults before each test."""
    _fake_config.values = {
        "max_sessions": 1000,
        "session_timeout_minutes": 60,
        "cleanup_interval_minutes": 15,
        "max_conversation_size_kb": 100,
    }
    yield


@pytest.fixture
def manager():
    """A SessionManager whose background cleanup thread is stopped afterwards."""
    m = SessionManager()
    try:
        yield m
    finally:
        m.stop_cleanup_thread()


@pytest.fixture
def frozen_time(monkeypatch):
    """Pin sm_mod.time.time to a mutable value."""
    state = {"now": 1_000_000.0}

    def _now():
        return state["now"]

    monkeypatch.setattr(sm_mod.time, "time", _now)
    return state


def _expected_message_bytes(
    role: str, content: str, timestamp: float, metadata: Optional[dict] = None
) -> int:
    """Compute the exact byte count add_message uses for size tracking."""
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "metadata": metadata or {},
    }
    return len(json.dumps(message, ensure_ascii=False).encode())


# ---------------------------------------------------------------------------
# ConversationSession.__init__
# ---------------------------------------------------------------------------


class TestConversationSessionInit:
    def test_stores_session_id_and_user_id(self):
        s = ConversationSession("sess-abc", user_id="user-42")
        assert s.session_id == "sess-abc"
        assert s.user_id == "user-42"

    def test_user_id_defaults_to_none(self):
        s = ConversationSession("sess-abc")
        assert s.user_id is None

    def test_created_at_equals_frozen_time(self, frozen_time):
        frozen_time["now"] = 12345.0
        s = ConversationSession("sess-abc")
        assert s.created_at == 12345.0

    def test_last_activity_equals_frozen_time(self, frozen_time):
        frozen_time["now"] = 12345.0
        s = ConversationSession("sess-abc")
        assert s.last_activity == 12345.0

    def test_messages_starts_empty(self):
        s = ConversationSession("sess-abc")
        assert len(s.messages) == 0
        assert list(s.messages) == []

    def test_messages_has_maxlen_of_100(self):
        s = ConversationSession("sess-abc")
        assert s.messages.maxlen == 100

    def test_metadata_starts_empty_dict(self):
        s = ConversationSession("sess-abc")
        assert s.metadata == {}

    def test_size_bytes_starts_at_zero(self):
        s = ConversationSession("sess-abc")
        assert s.get_size_bytes() == 0


# ---------------------------------------------------------------------------
# ConversationSession.add_message — basic behavior
# ---------------------------------------------------------------------------


class TestAddMessage:
    def test_single_message_contains_all_fields(self, frozen_time):
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        s.add_message("user", "hello")
        msgs = list(s.messages)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[0]["timestamp"] == 1000.0
        assert msgs[0]["metadata"] == {}

    def test_metadata_passes_through_unchanged(self):
        s = ConversationSession("sess-1")
        s.add_message("assistant", "hi", metadata={"source": "llm", "tokens": 42})
        msg = list(s.messages)[0]
        assert msg["metadata"] == {"source": "llm", "tokens": 42}

    def test_none_metadata_becomes_empty_dict(self):
        s = ConversationSession("sess-1")
        s.add_message("user", "content", metadata=None)
        msg = list(s.messages)[0]
        assert msg["metadata"] == {}

    def test_size_bytes_matches_json_byte_length(self, frozen_time):
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        s.add_message("user", "hello")
        expected = _expected_message_bytes("user", "hello", 1000.0, {})
        assert s.get_size_bytes() == expected

    def test_size_accumulates_across_messages(self, frozen_time):
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        s.add_message("user", "first message")
        s.add_message("assistant", "second message")
        expected = _expected_message_bytes(
            "user", "first message", 1000.0, {}
        ) + _expected_message_bytes("assistant", "second message", 1000.0, {})
        assert s.get_size_bytes() == expected

    def test_last_activity_advances_to_current_time(self, frozen_time):
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        frozen_time["now"] = 2000.0
        s.add_message("user", "hi")
        assert s.last_activity == 2000.0

    def test_messages_appended_in_insertion_order(self):
        s = ConversationSession("sess-1")
        s.add_message("user", "first")
        s.add_message("assistant", "second")
        s.add_message("user", "third")
        contents = [m["content"] for m in s.messages]
        assert contents == ["first", "second", "third"]

    def test_deque_maxlen_drops_oldest_after_100_adds(self):
        s = ConversationSession("sess-1")
        for i in range(150):
            s.add_message("user", f"msg-{i}")
        assert len(s.messages) == 100
        messages = list(s.messages)
        assert messages[0]["content"] == "msg-50"
        assert messages[-1]["content"] == "msg-149"


# ---------------------------------------------------------------------------
# ConversationSession.add_message — size-based eviction
# ---------------------------------------------------------------------------


class TestAddMessageSizeEviction:
    def test_small_message_within_budget_is_not_evicted(self, frozen_time):
        frozen_time["now"] = 1000.0
        _fake_config.values["max_conversation_size_kb"] = 1  # 1024 bytes
        s = ConversationSession("sess-1")
        s.add_message("user", "short")
        assert len(s.messages) == 1
        assert list(s.messages)[0]["content"] == "short"

    def test_oversize_total_evicts_oldest_until_fits(self, frozen_time):
        frozen_time["now"] = 1000.0
        _fake_config.values["max_conversation_size_kb"] = 1  # 1024 bytes
        s = ConversationSession("sess-1")
        # Each message is exactly 270 bytes of JSON under frozen time.
        # 4 messages would be 1080 bytes, so the 4th add must evict msg 0.
        big = "A" * 200
        for i in range(4):
            s.add_message("user", f"{i}-{big}")
        # Three messages retained: #1, #2, #3 (#0 evicted).
        assert len(s.messages) == 3
        assert s.get_size_bytes() == 3 * _expected_message_bytes(
            "user", f"0-{big}", 1000.0, {}
        )
        assert [m["content"] for m in s.messages] == [
            f"1-{big}",
            f"2-{big}",
            f"3-{big}",
        ]

    def test_tracked_size_equals_live_message_sizes_after_eviction(
        self, frozen_time
    ):
        frozen_time["now"] = 1000.0
        _fake_config.values["max_conversation_size_kb"] = 1
        s = ConversationSession("sess-1")
        # Each message is exactly 318 bytes. After 10 adds the budget holds
        # 3 messages (3 * 318 = 954 < 1024 < 4 * 318 = 1272).
        for i in range(10):
            s.add_message("user", "C" * 250)
        assert len(s.messages) == 3
        expected = 3 * _expected_message_bytes("user", "C" * 250, 1000.0, {})
        assert s.get_size_bytes() == expected
        # Size tracker must match what's actually in the deque, byte-for-byte.
        live_size = sum(
            len(json.dumps(m, ensure_ascii=False).encode()) for m in s.messages
        )
        assert s.get_size_bytes() == live_size

    def test_repeated_adds_stay_within_configured_budget(self, frozen_time):
        frozen_time["now"] = 1000.0
        _fake_config.values["max_conversation_size_kb"] = 1  # 1024 bytes
        s = ConversationSession("sess-1")
        # Each 368-byte message means only 2 fit (2*368=736 < 1024 < 3*368=1104).
        for i in range(20):
            s.add_message("user", "B" * 300)
        assert len(s.messages) == 2
        assert s.get_size_bytes() == 2 * _expected_message_bytes(
            "user", "B" * 300, 1000.0, {}
        )
        # Only the two most recent messages survive the steady-state eviction.
        # All messages share the same content, so retained content is identical.
        retained = [m["content"] for m in s.messages]
        assert retained == ["B" * 300, "B" * 300]


# ---------------------------------------------------------------------------
# ConversationSession.get_recent_messages
# ---------------------------------------------------------------------------


class TestGetRecentMessages:
    def test_empty_session_returns_empty_list(self):
        s = ConversationSession("sess-1")
        assert s.get_recent_messages() == []

    def test_default_limit_returns_last_10_messages(self):
        s = ConversationSession("sess-1")
        for i in range(15):
            s.add_message("user", f"msg-{i}")
        result = s.get_recent_messages()
        assert len(result) == 10
        assert [m["content"] for m in result] == [f"msg-{i}" for i in range(5, 15)]

    def test_custom_limit_returns_only_that_many(self):
        s = ConversationSession("sess-1")
        for i in range(10):
            s.add_message("user", f"msg-{i}")
        result = s.get_recent_messages(limit=3)
        assert len(result) == 3
        assert [m["content"] for m in result] == ["msg-7", "msg-8", "msg-9"]

    def test_limit_larger_than_available_returns_all(self):
        s = ConversationSession("sess-1")
        for i in range(5):
            s.add_message("user", f"msg-{i}")
        result = s.get_recent_messages(limit=100)
        assert len(result) == 5
        assert [m["content"] for m in result] == [f"msg-{i}" for i in range(5)]

    def test_limit_zero_returns_full_list(self):
        s = ConversationSession("sess-1")
        for i in range(4):
            s.add_message("user", f"msg-{i}")
        result = s.get_recent_messages(limit=0)
        assert len(result) == 4
        assert [m["content"] for m in result] == ["msg-0", "msg-1", "msg-2", "msg-3"]

    def test_negative_limit_returns_full_list(self):
        s = ConversationSession("sess-1")
        for i in range(4):
            s.add_message("user", f"msg-{i}")
        result = s.get_recent_messages(limit=-1)
        assert len(result) == 4
        assert [m["content"] for m in result] == ["msg-0", "msg-1", "msg-2", "msg-3"]

    def test_returned_list_is_snapshot_not_live_view(self):
        s = ConversationSession("sess-1")
        s.add_message("user", "first")
        snapshot = s.get_recent_messages()
        s.add_message("user", "second")
        assert len(snapshot) == 1
        assert snapshot[0]["content"] == "first"


# ---------------------------------------------------------------------------
# ConversationSession.is_expired
# ---------------------------------------------------------------------------


class TestIsExpired:
    def test_fresh_session_is_not_expired(self, frozen_time):
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        assert s.is_expired() is False

    def test_expired_after_timeout_passes(self, frozen_time):
        _fake_config.values["session_timeout_minutes"] = 60
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        frozen_time["now"] = 1000.0 + 60 * 60 + 1  # 1 second past timeout
        assert s.is_expired() is True

    def test_exactly_at_timeout_boundary_is_not_expired(self, frozen_time):
        """is_expired uses strict `>`, so equality is NOT expired."""
        _fake_config.values["session_timeout_minutes"] = 60
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        frozen_time["now"] = 1000.0 + 60 * 60
        assert s.is_expired() is False

    def test_just_before_timeout_not_expired(self, frozen_time):
        _fake_config.values["session_timeout_minutes"] = 60
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        frozen_time["now"] = 1000.0 + 60 * 60 - 1
        assert s.is_expired() is False

    def test_custom_timeout_respected(self, frozen_time):
        _fake_config.values["session_timeout_minutes"] = 5
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        frozen_time["now"] = 1000.0 + 5 * 60 + 1
        assert s.is_expired() is True

    def test_add_message_refreshes_expiry(self, frozen_time):
        _fake_config.values["session_timeout_minutes"] = 60
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        # Advance to 10 seconds before expiry, then add a message.
        frozen_time["now"] = 1000.0 + 60 * 60 - 10
        s.add_message("user", "ping")
        # Advance another full timeout minus 1 second — still not expired
        # because last_activity was just reset.
        frozen_time["now"] = s.last_activity + 60 * 60 - 1
        assert s.is_expired() is False


# ---------------------------------------------------------------------------
# ConversationSession.clear_old_messages
# ---------------------------------------------------------------------------


class TestClearOldMessages:
    def test_noop_when_below_keep_recent(self):
        s = ConversationSession("sess-1")
        s.add_message("user", "a")
        s.add_message("user", "b")
        s.clear_old_messages(keep_recent=10)
        assert len(s.messages) == 2
        assert [m["content"] for m in s.messages] == ["a", "b"]

    def test_noop_when_equal_to_keep_recent(self):
        """Guard uses strict `>`, so len == keep_recent is a no-op."""
        s = ConversationSession("sess-1")
        for i in range(5):
            s.add_message("user", f"msg-{i}")
        original_size = s.get_size_bytes()
        s.clear_old_messages(keep_recent=5)
        assert len(s.messages) == 5
        assert s.get_size_bytes() == original_size

    def test_keeps_only_most_recent_n(self):
        s = ConversationSession("sess-1")
        for i in range(10):
            s.add_message("user", f"msg-{i}")
        s.clear_old_messages(keep_recent=3)
        assert len(s.messages) == 3
        assert [m["content"] for m in s.messages] == ["msg-7", "msg-8", "msg-9"]

    def test_size_is_recalculated_from_retained_messages(self, frozen_time):
        frozen_time["now"] = 1000.0
        s = ConversationSession("sess-1")
        for i in range(10):
            s.add_message("user", f"msg-{i}")
        s.clear_old_messages(keep_recent=2)
        expected = _expected_message_bytes(
            "user", "msg-8", 1000.0, {}
        ) + _expected_message_bytes("user", "msg-9", 1000.0, {})
        assert s.get_size_bytes() == expected

    def test_default_keep_recent_is_10(self):
        s = ConversationSession("sess-1")
        for i in range(15):
            s.add_message("user", f"msg-{i}")
        s.clear_old_messages()
        assert len(s.messages) == 10
        assert [m["content"] for m in s.messages] == [
            f"msg-{i}" for i in range(5, 15)
        ]

    def test_compact_down_to_single_message(self):
        s = ConversationSession("sess-1")
        for i in range(5):
            s.add_message("user", f"msg-{i}")
        s.clear_old_messages(keep_recent=1)
        assert len(s.messages) == 1
        assert list(s.messages)[0]["content"] == "msg-4"


# ---------------------------------------------------------------------------
# SessionManager.__init__ and thread lifecycle
# ---------------------------------------------------------------------------


class TestSessionManagerInit:
    def test_starts_with_no_sessions(self, manager):
        assert manager.sessions == {}

    def test_config_snapshot_taken_at_init(self, manager):
        assert manager.config["max_sessions"] == 1000
        assert manager.config["session_timeout_minutes"] == 60
        assert manager.config["cleanup_interval_minutes"] == 15
        assert manager.config["max_conversation_size_kb"] == 100

    def test_cleanup_thread_is_running_after_init(self, manager):
        assert manager._cleanup_thread is not None
        assert manager._cleanup_thread.is_alive() is True
        assert manager._cleanup_thread.daemon is True

    def test_stop_cleanup_thread_sets_stop_event(self, manager):
        assert manager._stop_cleanup.is_set() is False
        manager.stop_cleanup_thread()
        assert manager._stop_cleanup.is_set() is True

    def test_stop_cleanup_thread_terminates_thread_when_loop_checks_event(self):
        # Use a zero-length cleanup interval so the background loop spins
        # fast and reaches the event check almost immediately.
        _fake_config.values["cleanup_interval_minutes"] = 0
        m = SessionManager()
        assert m._cleanup_thread.is_alive() is True
        m.stop_cleanup_thread()
        m._cleanup_thread.join(timeout=3)
        assert m._cleanup_thread.is_alive() is False

    def test_start_cleanup_thread_is_idempotent_when_alive(self, manager):
        first_thread = manager._cleanup_thread
        manager.start_cleanup_thread()
        assert manager._cleanup_thread is first_thread


# ---------------------------------------------------------------------------
# SessionManager.get_or_create_session
# ---------------------------------------------------------------------------


class TestGetOrCreateSession:
    def test_creates_new_session_when_id_unknown(self, manager):
        s = manager.get_or_create_session("new-sess")
        assert isinstance(s, ConversationSession)
        assert s.session_id == "new-sess"
        assert s.user_id is None
        assert "new-sess" in manager.sessions

    def test_returns_same_session_on_repeat_call(self, manager):
        first = manager.get_or_create_session("sess-1")
        second = manager.get_or_create_session("sess-1")
        assert first is second

    def test_passes_user_id_through_on_create(self, manager):
        s = manager.get_or_create_session("sess-1", user_id="u-7")
        assert s.user_id == "u-7"

    def test_existing_session_user_id_is_not_overwritten(self, manager):
        first = manager.get_or_create_session("sess-1", user_id="u-1")
        second = manager.get_or_create_session("sess-1", user_id="u-2")
        assert first is second
        assert first.user_id == "u-1"

    def test_cleanup_runs_when_at_max_sessions(self):
        _fake_config.values["max_sessions"] = 3
        m = SessionManager()
        try:
            a = m.get_or_create_session("a")
            b = m.get_or_create_session("b")
            c = m.get_or_create_session("c")
            a.last_activity = 100.0
            b.last_activity = 200.0
            c.last_activity = 300.0
            # Adding a 4th triggers _cleanup_oldest_sessions(). With default
            # keep_count = max_sessions - 10 = -7, all existing sessions are
            # dropped before the new session is inserted.
            m.get_or_create_session("d")
            assert "d" in m.sessions
            assert "a" not in m.sessions
            assert "b" not in m.sessions
            assert "c" not in m.sessions
        finally:
            m.stop_cleanup_thread()

    def test_no_cleanup_below_max(self, manager):
        manager.get_or_create_session("a")
        manager.get_or_create_session("b")
        assert set(manager.sessions) == {"a", "b"}


# ---------------------------------------------------------------------------
# SessionManager.get_session
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_returns_none_for_unknown_id(self, manager):
        assert manager.get_session("nope") is None

    def test_returns_existing_session(self, manager):
        created = manager.get_or_create_session("sess-1")
        fetched = manager.get_session("sess-1")
        assert fetched is created

    def test_get_session_does_not_create(self, manager):
        manager.get_session("does-not-exist")
        assert "does-not-exist" not in manager.sessions


# ---------------------------------------------------------------------------
# SessionManager.remove_session
# ---------------------------------------------------------------------------


class TestRemoveSession:
    def test_returns_true_when_session_removed(self, manager):
        manager.get_or_create_session("sess-1")
        assert manager.remove_session("sess-1") is True
        assert "sess-1" not in manager.sessions

    def test_returns_false_when_session_missing(self, manager):
        assert manager.remove_session("nope") is False

    def test_removes_only_target_session(self, manager):
        manager.get_or_create_session("keep")
        manager.get_or_create_session("drop")
        manager.remove_session("drop")
        assert "keep" in manager.sessions
        assert "drop" not in manager.sessions


# ---------------------------------------------------------------------------
# SessionManager.cleanup_expired_sessions
# ---------------------------------------------------------------------------


class TestCleanupExpiredSessions:
    def test_returns_zero_when_no_sessions(self, manager):
        assert manager.cleanup_expired_sessions() == 0

    def test_returns_zero_when_none_expired(self, manager):
        manager.get_or_create_session("fresh")
        assert manager.cleanup_expired_sessions() == 0
        assert "fresh" in manager.sessions

    def test_removes_expired_and_returns_count(self, manager, frozen_time):
        _fake_config.values["session_timeout_minutes"] = 60
        frozen_time["now"] = 1000.0
        manager.get_or_create_session("old1")
        manager.get_or_create_session("old2")
        manager.get_or_create_session("new")
        manager.sessions["old1"].last_activity = 1000.0 - 60 * 60 - 1
        manager.sessions["old2"].last_activity = 1000.0 - 60 * 60 - 1
        manager.sessions["new"].last_activity = 1000.0
        removed = manager.cleanup_expired_sessions()
        assert removed == 2
        assert "new" in manager.sessions
        assert "old1" not in manager.sessions
        assert "old2" not in manager.sessions

    def test_leaves_fresh_sessions_alone(self, manager, frozen_time):
        frozen_time["now"] = 1000.0
        manager.get_or_create_session("a")
        manager.get_or_create_session("b")
        removed = manager.cleanup_expired_sessions()
        assert removed == 0
        assert set(manager.sessions) == {"a", "b"}


# ---------------------------------------------------------------------------
# SessionManager._cleanup_oldest_sessions
# ---------------------------------------------------------------------------


class TestCleanupOldestSessions:
    def test_noop_when_below_keep_count(self, manager):
        manager.get_or_create_session("a")
        manager.get_or_create_session("b")
        manager._cleanup_oldest_sessions(keep_count=5)
        assert set(manager.sessions) == {"a", "b"}

    def test_removes_oldest_by_last_activity(self, manager):
        for name, activity in [
            ("oldest", 100.0),
            ("middle", 200.0),
            ("newest", 300.0),
        ]:
            s = manager.get_or_create_session(name)
            s.last_activity = activity
        manager._cleanup_oldest_sessions(keep_count=2)
        assert "oldest" not in manager.sessions
        assert "middle" in manager.sessions
        assert "newest" in manager.sessions

    def test_removes_multiple_oldest_when_over_limit(self, manager):
        for i in range(6):
            s = manager.get_or_create_session(f"sess-{i}")
            s.last_activity = float(i)
        manager._cleanup_oldest_sessions(keep_count=2)
        assert len(manager.sessions) == 2
        assert "sess-4" in manager.sessions
        assert "sess-5" in manager.sessions

    def test_equal_to_keep_count_is_noop(self, manager):
        """len <= keep_count returns early — equality should also be no-op."""
        for name in ["a", "b", "c"]:
            manager.get_or_create_session(name)
        manager._cleanup_oldest_sessions(keep_count=3)
        assert set(manager.sessions) == {"a", "b", "c"}

    def test_default_keep_count_is_max_sessions_minus_10(self):
        _fake_config.values["max_sessions"] = 15
        m = SessionManager()
        try:
            for i in range(20):
                s = ConversationSession(f"sess-{i}")
                s.last_activity = float(i)
                m.sessions[f"sess-{i}"] = s
            m._cleanup_oldest_sessions()  # keep_count defaults to 15 - 10 = 5
            assert len(m.sessions) == 5
            assert set(m.sessions) == {f"sess-{i}" for i in range(15, 20)}
        finally:
            m.stop_cleanup_thread()


# ---------------------------------------------------------------------------
# SessionManager.get_session_stats
# ---------------------------------------------------------------------------


class TestGetSessionStats:
    def test_empty_manager_stats(self, manager):
        stats = manager.get_session_stats()
        assert stats["total_sessions"] == 0
        assert stats["active_sessions"] == 0
        assert stats["total_messages"] == 0
        assert stats["total_size_mb"] == 0.0
        assert stats["max_sessions"] == 1000

    def test_total_sessions_counts_all(self, manager):
        manager.get_or_create_session("a")
        manager.get_or_create_session("b")
        manager.get_or_create_session("c")
        stats = manager.get_session_stats()
        assert stats["total_sessions"] == 3

    def test_total_messages_sums_across_sessions(self, manager):
        a = manager.get_or_create_session("a")
        b = manager.get_or_create_session("b")
        a.add_message("user", "hi")
        a.add_message("assistant", "hello")
        b.add_message("user", "ping")
        stats = manager.get_session_stats()
        assert stats["total_messages"] == 3

    def test_active_sessions_counts_recent_activity(self, manager, frozen_time):
        frozen_time["now"] = 1000.0
        active = manager.get_or_create_session("active")
        idle = manager.get_or_create_session("idle")
        active.last_activity = 1000.0  # 0 seconds ago
        idle.last_activity = 1000.0 - 301  # past the 5-minute window
        stats = manager.get_session_stats()
        assert stats["active_sessions"] == 1
        assert stats["total_sessions"] == 2

    def test_active_boundary_at_300_seconds(self, manager, frozen_time):
        """`< 300` is strict, so exactly 300s ago is NOT active."""
        frozen_time["now"] = 1000.0
        on_edge = manager.get_or_create_session("edge")
        inside = manager.get_or_create_session("inside")
        on_edge.last_activity = 1000.0 - 300
        inside.last_activity = 1000.0 - 299
        stats = manager.get_session_stats()
        assert stats["active_sessions"] == 1

    def test_total_size_mb_is_rounded_to_2_decimals(self, manager):
        s = manager.get_or_create_session("sess-1")
        s._size_bytes = 1_572_864  # exactly 1.5 MB
        stats = manager.get_session_stats()
        assert stats["total_size_mb"] == 1.5

    def test_total_size_mb_rounds_fractional(self, manager):
        s = manager.get_or_create_session("sess-1")
        s._size_bytes = 1_234_567
        # 1234567 / (1024*1024) ≈ 1.1774 → 1.18
        stats = manager.get_session_stats()
        assert stats["total_size_mb"] == 1.18

    def test_total_size_mb_sums_across_sessions(self, manager):
        a = manager.get_or_create_session("a")
        b = manager.get_or_create_session("b")
        a._size_bytes = 524_288   # 0.5 MB
        b._size_bytes = 1_048_576  # 1.0 MB
        stats = manager.get_session_stats()
        assert stats["total_size_mb"] == 1.5

    def test_max_sessions_reflects_init_snapshot(self):
        _fake_config.values["max_sessions"] = 42
        m = SessionManager()
        try:
            stats = m.get_session_stats()
            assert stats["max_sessions"] == 42
        finally:
            m.stop_cleanup_thread()


# ---------------------------------------------------------------------------
# SessionManager.compact_all_sessions
# ---------------------------------------------------------------------------


class TestCompactAllSessions:
    def test_compacts_every_session_to_keep_recent(self, manager):
        a = manager.get_or_create_session("a")
        b = manager.get_or_create_session("b")
        for i in range(15):
            a.add_message("user", f"a-{i}")
            b.add_message("user", f"b-{i}")
        manager.compact_all_sessions(keep_recent=5)
        assert len(a.messages) == 5
        assert len(b.messages) == 5
        assert [m["content"] for m in a.messages] == [f"a-{i}" for i in range(10, 15)]
        assert [m["content"] for m in b.messages] == [f"b-{i}" for i in range(10, 15)]

    def test_default_keep_recent_is_10(self, manager):
        a = manager.get_or_create_session("a")
        for i in range(20):
            a.add_message("user", f"msg-{i}")
        manager.compact_all_sessions()
        assert len(a.messages) == 10
        assert [m["content"] for m in a.messages] == [
            f"msg-{i}" for i in range(10, 20)
        ]

    def test_noop_when_sessions_below_threshold(self, manager):
        a = manager.get_or_create_session("a")
        a.add_message("user", "only one")
        manager.compact_all_sessions(keep_recent=10)
        assert len(a.messages) == 1
        assert list(a.messages)[0]["content"] == "only one"

    def test_empty_manager_compacts_without_error(self, manager):
        manager.compact_all_sessions(keep_recent=10)
        assert manager.sessions == {}
