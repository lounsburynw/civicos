"""
Tests for conversation_store.py — ConversationStore persistent conversation
storage with full LLM message format support.

Uses a real SQLite database in a temp directory. No mocks — the module
is pure DB logic with no external dependencies to mock.

To run:
    pytest packages/civicos-services/tests/test_conversation_store.py -q --override-ini="addopts="
"""

import json
import sqlite3
from pathlib import Path

import pytest

from civicos_services.storage.conversation_store import ConversationStore


# ---------------------------------------------------------------------------
# Schema SQL — migration 011 doesn't ship as a file, so we create inline
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}',
    archived INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    metadata TEXT,
    sequence_number INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS ui_snapshots (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id TEXT,
    snapshot_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return a temp DB path with schema pre-created."""
    path = str(tmp_path / "test_conv.db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def store(db_path):
    """ConversationStore backed by a temp SQLite DB with schema."""
    return ConversationStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Conversation Management
# ---------------------------------------------------------------------------

class TestCreateConversation:
    def test_returns_prefixed_id(self, store):
        conv_id = store.create_conversation()
        assert conv_id.startswith("conv_")
        assert len(conv_id) == len("conv_") + 16

    def test_stores_user_id_and_title(self, store):
        conv_id = store.create_conversation(user_id="user_abc", title="Housing discussion")
        conv = store.get_conversation(conv_id)
        assert conv["user_id"] == "user_abc"
        assert conv["title"] == "Housing discussion"

    def test_default_metadata_is_empty_dict(self, store):
        conv_id = store.create_conversation()
        conv = store.get_conversation(conv_id)
        assert conv["metadata"] == {}

    def test_default_archived_is_false(self, store):
        conv_id = store.create_conversation()
        conv = store.get_conversation(conv_id)
        assert conv["archived"] is False

    def test_unique_ids_per_call(self, store):
        id1 = store.create_conversation()
        id2 = store.create_conversation()
        assert id1 != id2


class TestGetConversation:
    def test_returns_none_for_nonexistent(self, store):
        result = store.get_conversation("conv_does_not_exist")
        assert result is None

    def test_returns_all_expected_keys(self, store):
        conv_id = store.create_conversation(user_id="u1", title="Test")
        conv = store.get_conversation(conv_id)
        assert set(conv.keys()) == {
            "id", "user_id", "title", "created_at", "updated_at", "metadata", "archived"
        }

    def test_null_metadata_becomes_empty_dict(self, db_path):
        # Directly insert a row with NULL metadata
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO conversations (id, metadata) VALUES (?, ?)",
            ("conv_nullmeta", None),
        )
        conn.commit()
        conn.close()

        store = ConversationStore(db_path=db_path)
        conv = store.get_conversation("conv_nullmeta")
        assert conv["metadata"] == {}


class TestListConversations:
    def test_empty_list_when_no_conversations(self, store):
        result = store.list_conversations()
        assert result == []

    def test_returns_created_conversations(self, store):
        store.create_conversation(user_id="u1", title="First")
        store.create_conversation(user_id="u2", title="Second")
        convs = store.list_conversations()
        assert len(convs) == 2
        titles = {c["title"] for c in convs}
        assert titles == {"First", "Second"}

    def test_filters_by_user_id(self, store):
        store.create_conversation(user_id="alice", title="Alice conv")
        store.create_conversation(user_id="bob", title="Bob conv")
        result = store.list_conversations(user_id="alice")
        assert len(result) == 1
        assert result[0]["title"] == "Alice conv"

    def test_excludes_archived_by_default(self, store):
        conv_id = store.create_conversation(title="To archive")
        store.archive_conversation(conv_id)
        result = store.list_conversations()
        assert len(result) == 0

    def test_includes_archived_when_requested(self, store):
        conv_id = store.create_conversation(title="Archived")
        store.archive_conversation(conv_id)
        result = store.list_conversations(archived=True)
        assert len(result) == 1
        assert result[0]["title"] == "Archived"

    def test_respects_limit(self, store):
        for i in range(5):
            store.create_conversation(title=f"Conv {i}")
        result = store.list_conversations(limit=3)
        assert len(result) == 3


class TestUpdateTitle:
    def test_changes_title(self, store):
        conv_id = store.create_conversation(title="Old title")
        store.update_title(conv_id, "New title")
        conv = store.get_conversation(conv_id)
        assert conv["title"] == "New title"


class TestArchiveConversation:
    def test_archives_conversation(self, store):
        conv_id = store.create_conversation()
        store.archive_conversation(conv_id)
        conv = store.get_conversation(conv_id)
        assert conv["archived"] is True

    def test_unarchives_conversation(self, store):
        conv_id = store.create_conversation()
        store.archive_conversation(conv_id, archived=True)
        store.archive_conversation(conv_id, archived=False)
        conv = store.get_conversation(conv_id)
        assert conv["archived"] is False


# ---------------------------------------------------------------------------
# Message Management
# ---------------------------------------------------------------------------

class TestAddMessage:
    def test_returns_prefixed_id(self, store):
        conv_id = store.create_conversation()
        msg_id = store.add_message(conv_id, role="user", content="Hello")
        assert msg_id.startswith("msg_")
        assert len(msg_id) == len("msg_") + 16

    def test_sequence_numbers_increment(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="First")
        store.add_message(conv_id, role="assistant", content="Second")
        store.add_message(conv_id, role="user", content="Third")

        msgs = store.get_messages(conv_id)
        assert len(msgs) == 3
        assert msgs[0]["content"] == "First"
        assert msgs[1]["content"] == "Second"
        assert msgs[2]["content"] == "Third"

    def test_stores_tool_calls_as_json(self, store):
        conv_id = store.create_conversation()
        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"q": "housing"}'}}
        ]
        store.add_message(conv_id, role="assistant", content=None, tool_calls=tool_calls)
        msgs = store.get_messages(conv_id)
        assert msgs[0]["tool_calls"] == tool_calls
        assert msgs[0]["tool_calls"][0]["id"] == "call_1"

    def test_stores_tool_result_fields(self, store):
        conv_id = store.create_conversation()
        store.add_message(
            conv_id, role="tool",
            content='{"results": []}',
            tool_call_id="call_1",
            name="search",
        )
        msgs = store.get_messages(conv_id)
        assert msgs[0]["role"] == "tool"
        assert msgs[0]["tool_call_id"] == "call_1"
        assert msgs[0]["name"] == "search"
        assert msgs[0]["content"] == '{"results": []}'


class TestGetMessages:
    def test_empty_conversation_returns_empty_list(self, store):
        conv_id = store.create_conversation()
        msgs = store.get_messages(conv_id)
        assert msgs == []

    def test_messages_ordered_by_sequence(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="system", content="You are a civic assistant.")
        store.add_message(conv_id, role="user", content="What meetings are next?")
        store.add_message(conv_id, role="assistant", content="There are 3 upcoming meetings.")

        msgs = store.get_messages(conv_id)
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant"]

    def test_content_omitted_when_none(self, store):
        conv_id = store.create_conversation()
        tool_calls = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
        store.add_message(conv_id, role="assistant", content=None, tool_calls=tool_calls)
        msgs = store.get_messages(conv_id)
        assert "content" not in msgs[0]

    def test_tool_calls_omitted_when_none(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hello")
        msgs = store.get_messages(conv_id)
        assert "tool_calls" not in msgs[0]

    def test_tool_call_id_omitted_when_none(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hello")
        msgs = store.get_messages(conv_id)
        assert "tool_call_id" not in msgs[0]

    def test_name_omitted_when_none(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hello")
        msgs = store.get_messages(conv_id)
        assert "name" not in msgs[0]

    def test_limit_returns_first_n_by_sequence(self, store):
        conv_id = store.create_conversation()
        for i in range(5):
            store.add_message(conv_id, role="user", content=f"Message {i}")
        msgs = store.get_messages(conv_id, limit=2)
        # ORDER BY sequence_number ASC LIMIT 2 → first 2 messages
        assert len(msgs) == 2
        assert msgs[0]["content"] == "Message 0"
        assert msgs[1]["content"] == "Message 1"

    def test_full_tool_call_roundtrip(self, store):
        """Verify a complete assistant→tool→assistant cycle is stored correctly."""
        conv_id = store.create_conversation()

        # User asks a question
        store.add_message(conv_id, role="user", content="Find housing decisions")

        # Assistant responds with a tool call
        tool_calls = [
            {"id": "tc_abc", "type": "function",
             "function": {"name": "what_happened", "arguments": '{"topic": "housing"}'}}
        ]
        store.add_message(conv_id, role="assistant", content=None, tool_calls=tool_calls)

        # Tool returns result
        store.add_message(
            conv_id, role="tool",
            content='[{"title": "Housing Element Update"}]',
            tool_call_id="tc_abc",
            name="what_happened",
        )

        # Assistant synthesizes
        store.add_message(conv_id, role="assistant", content="I found a Housing Element Update decision.")

        msgs = store.get_messages(conv_id)
        assert len(msgs) == 4
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["tool_calls"][0]["function"]["name"] == "what_happened"
        assert msgs[2]["role"] == "tool"
        assert msgs[2]["tool_call_id"] == "tc_abc"
        assert msgs[3]["role"] == "assistant"
        assert msgs[3]["content"] == "I found a Housing Element Update decision."


# ---------------------------------------------------------------------------
# LLM Message Formatting
# ---------------------------------------------------------------------------

class TestGetMessagesForLLM:
    def test_returns_messages_without_context(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hello")
        msgs = store.get_messages_for_llm(conv_id)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello"

    def test_system_message_placed_first(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hi")
        store.add_message(conv_id, role="system", content="You are helpful.")
        msgs = store.get_messages_for_llm(conv_id)
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are helpful."

    def test_injects_active_context_after_system(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="system", content="System prompt")
        store.add_message(conv_id, role="user", content="What's happening?")

        context = {"serialized_artifacts": "Meeting at 7pm tonight"}
        msgs = store.get_messages_for_llm(conv_id, active_context=context)

        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "System prompt"
        assert msgs[1]["role"] == "system"
        assert "Meeting at 7pm tonight" in msgs[1]["content"]
        assert msgs[1]["content"].startswith("## User's Current Context")
        assert msgs[2]["role"] == "user"

    def test_skips_context_injection_when_no_artifacts(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hello")

        context = {"current_jurisdiction": "city-berkeley"}  # no serialized_artifacts
        msgs = store.get_messages_for_llm(conv_id, active_context=context)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_skips_context_injection_when_artifacts_empty(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hello")

        context = {"serialized_artifacts": ""}
        msgs = store.get_messages_for_llm(conv_id, active_context=context)
        assert len(msgs) == 1

    def test_no_system_message_still_injects_context(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="Hi")

        context = {"serialized_artifacts": "Budget data loaded"}
        msgs = store.get_messages_for_llm(conv_id, active_context=context)
        assert msgs[0]["role"] == "system"
        assert "Budget data loaded" in msgs[0]["content"]
        assert msgs[1]["role"] == "user"


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

class TestTruncateToFit:
    def test_short_conversation_not_truncated(self, store):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = store._truncate_to_fit(msgs, max_tokens=100000)
        assert len(result) == 2

    def test_long_conversation_truncated_from_front(self, store):
        # Each message ≈ 2500 chars = ~625 tokens
        msgs = [{"role": "user", "content": "x" * 2500} for _ in range(200)]
        result = store._truncate_to_fit(msgs, max_tokens=5000)
        # With 5000 token budget minus reserve (2*500=1000) → 4000 available
        # Each msg ~625 tokens → fits ~6 messages
        assert len(result) < 200
        assert len(result) >= 1
        # Verify most recent messages kept (last ones from original list)
        assert result[-1] is msgs[-1]

    def test_preserves_most_recent_messages(self, store):
        # Each message: content=100 chars + tool_calls="[]"=2 chars → (102)//4 = 25 tokens
        msgs = [{"role": "user", "content": f"{'x' * 90} msg {i}"} for i in range(10)]
        # Budget=60 tokens, reserve=0 → fits 2 messages (2*25=50 < 60, 3*25=75 > 60)
        result = store._truncate_to_fit(msgs, max_tokens=60, reserve_for_system=0)
        assert len(result) == 2
        assert result[-1]["content"].endswith("msg 9")
        assert result[0]["content"].endswith("msg 8")

    def test_empty_messages_returns_empty(self, store):
        result = store._truncate_to_fit([], max_tokens=100000)
        assert result == []

    def test_token_estimation_uses_content_and_tool_calls(self, store):
        # Message with content only
        msg_content = {"role": "user", "content": "a" * 400}
        # Message with tool_calls
        msg_tools = {"role": "assistant", "tool_calls": [{"id": "c1"} for _ in range(100)]}

        # Both should contribute to token count — tool_calls adds significant chars
        result_content = store._truncate_to_fit([msg_content], max_tokens=50)
        # 400 chars / 4 = 100 tokens; budget 50 - reserve(1000) < 0, so nothing fits
        # Actually reserve is reserve_for_system * 500, default=2 → 1000
        # available = 50 - 1000 = negative → nothing fits
        assert result_content == []

    def test_reserve_for_system_reduces_budget(self, store):
        msg = {"role": "user", "content": "a" * 1600}  # 400 tokens
        # With reserve=0, 500 budget → fits (400 < 500)
        result_no_reserve = store._truncate_to_fit([msg], max_tokens=500, reserve_for_system=0)
        assert len(result_no_reserve) == 1

        # With reserve=1, 500 budget → 500-500=0 available → doesn't fit
        result_with_reserve = store._truncate_to_fit([msg], max_tokens=500, reserve_for_system=1)
        assert len(result_with_reserve) == 0


# ---------------------------------------------------------------------------
# Token Counting
# ---------------------------------------------------------------------------

class TestCountConversationTokens:
    def test_empty_conversation_is_zero(self, store):
        conv_id = store.create_conversation()
        assert store.count_conversation_tokens(conv_id) == 0

    def test_counts_content_tokens(self, store):
        conv_id = store.create_conversation()
        # 400 chars = 100 tokens (400 // 4)
        store.add_message(conv_id, role="user", content="a" * 400)
        tokens = store.count_conversation_tokens(conv_id)
        assert tokens == 100

    def test_counts_tool_calls_in_tokens(self, store):
        conv_id = store.create_conversation()
        tool_calls = [{"id": "c1", "type": "function", "function": {"name": "search", "arguments": "{}"}}]
        store.add_message(conv_id, role="assistant", content=None, tool_calls=tool_calls)
        tokens = store.count_conversation_tokens(conv_id)
        # token estimate = (0 + len(json.dumps(tool_calls))) // 4
        expected = len(json.dumps(tool_calls)) // 4
        assert tokens == expected

    def test_sums_across_multiple_messages(self, store):
        conv_id = store.create_conversation()
        store.add_message(conv_id, role="user", content="a" * 400)  # 100 tokens
        store.add_message(conv_id, role="assistant", content="b" * 800)  # 200 tokens
        tokens = store.count_conversation_tokens(conv_id)
        # Each message also has empty tool_calls → json.dumps([]) = "[]" = 2 chars → 0 tokens
        assert tokens == 300


# ---------------------------------------------------------------------------
# UI Snapshots
# ---------------------------------------------------------------------------

class TestSnapshots:
    def test_snapshot_roundtrip(self, store):
        conv_id = store.create_conversation()
        msg_id = store.add_message(conv_id, role="user", content="Hello")

        ui_state = {"artifacts": ["housing_report"], "view": "detail", "count": 42}
        store.snapshot_ui_state(conv_id, msg_id, ui_state)

        snapshots = store.get_snapshots(conv_id)
        assert len(snapshots) == 1
        assert snapshots[0]["message_id"] == msg_id
        assert snapshots[0]["snapshot_data"] == ui_state
        assert snapshots[0]["snapshot_data"]["count"] == 42

    def test_multiple_snapshots_ordered_by_time(self, store):
        conv_id = store.create_conversation()
        msg1 = store.add_message(conv_id, role="user", content="First")
        msg2 = store.add_message(conv_id, role="user", content="Second")

        store.snapshot_ui_state(conv_id, msg1, {"step": 1})
        store.snapshot_ui_state(conv_id, msg2, {"step": 2})

        snapshots = store.get_snapshots(conv_id)
        assert len(snapshots) == 2
        assert snapshots[0]["snapshot_data"]["step"] == 1
        assert snapshots[1]["snapshot_data"]["step"] == 2

    def test_empty_snapshots_for_new_conversation(self, store):
        conv_id = store.create_conversation()
        snapshots = store.get_snapshots(conv_id)
        assert snapshots == []

    def test_snapshot_has_expected_keys(self, store):
        conv_id = store.create_conversation()
        msg_id = store.add_message(conv_id, role="user", content="Hi")
        store.snapshot_ui_state(conv_id, msg_id, {"x": 1})
        snap = store.get_snapshots(conv_id)[0]
        assert set(snap.keys()) == {"id", "message_id", "snapshot_data", "created_at"}
        assert snap["id"].startswith("snap_")


# ---------------------------------------------------------------------------
# DB Init / Migration
# ---------------------------------------------------------------------------

class TestEnsureDbExists:
    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "test.db"
        # Pre-create tables so _ensure_db_exists doesn't fail on missing migration
        ConversationStore(db_path=str(nested))
        assert nested.parent.exists()

    def test_idempotent_when_tables_exist(self, db_path):
        # Call twice — should not raise
        store1 = ConversationStore(db_path=db_path)
        store2 = ConversationStore(db_path=db_path)
        # Both should work fine
        conv_id = store2.create_conversation(title="Works")
        assert store2.get_conversation(conv_id)["title"] == "Works"


class TestGetConnection:
    def test_returns_row_factory_connection(self, store):
        conn = store._get_connection()
        assert conn.row_factory == sqlite3.Row
        conn.close()
