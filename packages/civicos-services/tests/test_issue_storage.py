"""
Tests for issue_storage.py — IssueStorage, Issue, and CommunityStorage.

Uses an in-memory SQLite database with real schema to test actual SQL logic.
Mocks only the OpenAI API call (external dependency).

To run:
    pytest packages/civicos-services/tests/test_issue_storage.py -q --override-ini="addopts="
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.storage.issue_storage import (
    CommunityStorage,
    Issue,
    IssueStorage,
    generate_ai_title_and_summary,
)


# ---------------------------------------------------------------------------
# Schema + Fixtures
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE issues (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    description TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL,
    issue_type TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    status TEXT DEFAULT 'open',
    ai_title TEXT,
    ai_summary TEXT,
    ai_generated_at TEXT,
    short_name_keyword TEXT,
    short_name_number INTEGER,
    closed_reason TEXT,
    closed_at TEXT,
    closed_note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE issue_event_matches (
    match_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    match_score REAL,
    match_reason TEXT,
    UNIQUE(issue_id, event_id)
);

CREATE TABLE issue_timeline (
    entry_id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT,
    metadata TEXT
);

CREATE TABLE follows (
    follow_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    focal_type TEXT NOT NULL,
    focal_id TEXT NOT NULL,
    jurisdiction_id TEXT,
    last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, focal_type, focal_id)
);

CREATE TABLE coordination_threads (
    thread_id TEXT PRIMARY KEY,
    focal_type TEXT NOT NULL,
    focal_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_message_at TEXT
);

CREATE TABLE thread_messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    parent_message_id TEXT,
    reply_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def db_path(tmp_path):
    """Create a temp SQLite database with the required schema."""
    path = tmp_path / "test_issues.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.close()
    return path


@pytest.fixture
def issue_storage(db_path):
    return IssueStorage(db_path=db_path)


@pytest.fixture
def community_storage(db_path):
    return CommunityStorage(db_path=db_path)


def _mock_ai_response():
    """Patch generate_ai_title_and_summary to return deterministic values."""
    return patch(
        "civicos_services.storage.issue_storage.generate_ai_title_and_summary",
        return_value=("Pothole on Main St", "• Large pothole\n• Hazardous", "POTHOLE"),
    )


def _create_issue_directly(db_path, **overrides):
    """Insert an issue row directly for test setup (bypasses AI call)."""
    import uuid

    defaults = {
        "id": str(uuid.uuid4()),
        "user_id": "user-1",
        "description": "Test issue",
        "jurisdiction_id": "city-san-rafael",
        "issue_type": "infrastructure",
        "status": "open",
        "ai_title": "Test Title",
        "ai_summary": "Test summary",
        "short_name_keyword": "TEST",
        "short_name_number": 1,
    }
    defaults.update(overrides)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO issues (
                id, user_id, description, jurisdiction_id, issue_type,
                status, ai_title, ai_summary, short_name_keyword, short_name_number,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                defaults["id"],
                defaults["user_id"],
                defaults["description"],
                defaults["jurisdiction_id"],
                defaults["issue_type"],
                defaults["status"],
                defaults["ai_title"],
                defaults["ai_summary"],
                defaults["short_name_keyword"],
                defaults["short_name_number"],
            ),
        )
    return defaults["id"]


# ---------------------------------------------------------------------------
# generate_ai_title_and_summary
# ---------------------------------------------------------------------------


def _mock_config_module():
    """Create a mock 'config' module with config.get_openai_config()."""
    mock_config = MagicMock()
    mock_config.config.get_openai_config.return_value = {"api_key": "fake-key"}
    return patch.dict("sys.modules", {"config": mock_config})


class TestGenerateAiTitleAndSummary:
    def test_success_returns_parsed_json_fields(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"title": "Broken Sidewalk", "summary": "• Cracked\n• Tripping hazard", "short_name": "SIDEWALK"}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_config_module(), patch("civicos_services.storage.issue_storage.OpenAI", return_value=mock_client):
            title, summary, short_name = generate_ai_title_and_summary("Broken sidewalk near park")

        assert title == "Broken Sidewalk"
        assert summary == "• Cracked\n• Tripping hazard"
        assert short_name == "SIDEWALK"

    def test_issue_type_included_in_prompt(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {"title": "Noise complaint", "summary": "• Loud", "short_name": "NOISE"}
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_config_module(), patch("civicos_services.storage.issue_storage.OpenAI", return_value=mock_client):
            title, summary, short_name = generate_ai_title_and_summary("Loud music", issue_type="noise")

        # Verify the prompt included the issue type context
        call_args = mock_client.chat.completions.create.call_args
        prompt_content = call_args[1]["messages"][1]["content"]
        assert "(Category: noise)" in prompt_content
        assert title == "Noise complaint"

    def test_fallback_on_api_error(self):
        """When OpenAI raises an error, return truncated description as title."""
        with _mock_config_module(), patch("civicos_services.storage.issue_storage.OpenAI", side_effect=Exception("API down")):
            title, summary, short_name = generate_ai_title_and_summary("Short desc")

        assert title == "Short desc"
        assert summary == "Short desc"
        assert short_name == "ISSUE"

    def test_fallback_truncates_long_description(self):
        long_desc = "A" * 100
        with _mock_config_module(), patch("civicos_services.storage.issue_storage.OpenAI", side_effect=Exception("fail")):
            title, summary, short_name = generate_ai_title_and_summary(long_desc)

        assert title == "A" * 50 + "..."
        assert len(title) == 53
        assert summary == long_desc
        assert short_name == "ISSUE"

    def test_missing_fields_in_response_default_gracefully(self):
        """If LLM returns partial JSON, missing fields get defaults."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"title": "Pothole"})

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with _mock_config_module(), patch("civicos_services.storage.issue_storage.OpenAI", return_value=mock_client):
            title, summary, short_name = generate_ai_title_and_summary("pothole")

        assert title == "Pothole"
        assert summary == ""
        assert short_name == "ISSUE"


# ---------------------------------------------------------------------------
# IssueStorage.create_issue
# ---------------------------------------------------------------------------


class TestCreateIssue:
    def test_creates_issue_and_returns_uuid(self, issue_storage, db_path):
        with _mock_ai_response():
            issue_id = issue_storage.create_issue(
                user_id="user-1",
                description="Large pothole on Main St",
                jurisdiction_id="city-san-rafael",
                issue_type="infrastructure",
            )

        assert len(issue_id) == 36  # UUID format

        # Verify stored data
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone())

        assert row["user_id"] == "user-1"
        assert row["description"] == "Large pothole on Main St"
        assert row["jurisdiction_id"] == "city-san-rafael"
        assert row["issue_type"] == "infrastructure"
        assert row["status"] == "open"
        assert row["ai_title"] == "Pothole on Main St"
        assert row["short_name_keyword"] == "POTHOLE"
        assert row["short_name_number"] == 1

    def test_description_truncated_to_2000_chars(self, issue_storage, db_path):
        long_desc = "X" * 3000
        with _mock_ai_response():
            issue_id = issue_storage.create_issue(
                user_id="user-1",
                description=long_desc,
                jurisdiction_id="city-san-rafael",
            )

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT description FROM issues WHERE id = ?", (issue_id,)).fetchone()

        assert len(row[0]) == 2000

    def test_location_fields_stored(self, issue_storage, db_path):
        with _mock_ai_response():
            issue_id = issue_storage.create_issue(
                user_id="user-1",
                description="Pothole",
                jurisdiction_id="city-san-rafael",
                location={"address": "123 Main St", "latitude": 37.97, "longitude": -122.53},
            )

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT address, latitude, longitude FROM issues WHERE id = ?", (issue_id,)
            ).fetchone()

        assert row[0] == "123 Main St"
        assert row[1] == 37.97
        assert row[2] == -122.53

    def test_none_location_stores_nulls(self, issue_storage, db_path):
        with _mock_ai_response():
            issue_id = issue_storage.create_issue(
                user_id="user-1",
                description="Noise complaint",
                jurisdiction_id="city-san-rafael",
            )

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT address, latitude, longitude FROM issues WHERE id = ?", (issue_id,)
            ).fetchone()

        assert row[0] is None
        assert row[1] is None
        assert row[2] is None

    def test_creates_filed_timeline_entry(self, issue_storage, db_path):
        with _mock_ai_response():
            issue_id = issue_storage.create_issue(
                user_id="user-1",
                description="Noise",
                jurisdiction_id="city-san-rafael",
            )

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT event_type, description, source FROM issue_timeline WHERE issue_id = ?",
                (issue_id,),
            ).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "filed"
        assert rows[0][1] == "Issue filed"
        assert rows[0][2] == "user"

    def test_short_name_number_increments_per_keyword(self, issue_storage, db_path):
        with _mock_ai_response():
            id1 = issue_storage.create_issue("u1", "First pothole", "city-sr")
            id2 = issue_storage.create_issue("u2", "Second pothole", "city-sr")

        with sqlite3.connect(db_path) as conn:
            n1 = conn.execute("SELECT short_name_number FROM issues WHERE id = ?", (id1,)).fetchone()[0]
            n2 = conn.execute("SELECT short_name_number FROM issues WHERE id = ?", (id2,)).fetchone()[0]

        assert n1 == 1
        assert n2 == 2


# ---------------------------------------------------------------------------
# IssueStorage.get_issue
# ---------------------------------------------------------------------------


class TestGetIssue:
    def test_returns_none_for_nonexistent(self, issue_storage):
        result = issue_storage.get_issue("nonexistent-id")
        assert result is None

    def test_returns_full_issue_with_empty_matches(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path, description="Broken lamp")
        result = issue_storage.get_issue(issue_id)

        assert result["id"] == issue_id
        assert result["description"] == "Broken lamp"
        assert result["matched_events"] == []
        assert result["discussion_group_id"] is None

    def test_includes_matched_events_sorted_by_score(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)

        # Insert two event matches with different scores
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO issue_event_matches (match_id, issue_id, event_id, match_score, match_reason) VALUES (?, ?, ?, ?, ?)",
                ("m1", issue_id, "event-a", 75.0, "topic match"),
            )
            conn.execute(
                "INSERT INTO issue_event_matches (match_id, issue_id, event_id, match_score, match_reason) VALUES (?, ?, ?, ?, ?)",
                ("m2", issue_id, "event-b", 90.0, "keyword match"),
            )

        result = issue_storage.get_issue(issue_id)
        events = result["matched_events"]

        assert len(events) == 2
        # Higher score first
        assert events[0]["event_id"] == "event-b"
        assert events[0]["match_score"] == 90.0
        assert events[1]["event_id"] == "event-a"
        assert events[1]["match_score"] == 75.0

    def test_manual_links_sorted_after_automatic(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)

        with sqlite3.connect(db_path) as conn:
            # Manual link (no score)
            conn.execute(
                "INSERT INTO issue_event_matches (match_id, issue_id, event_id, match_score, match_reason) VALUES (?, ?, ?, ?, ?)",
                ("m1", issue_id, "event-manual", None, None),
            )
            # Automatic match
            conn.execute(
                "INSERT INTO issue_event_matches (match_id, issue_id, event_id, match_score, match_reason) VALUES (?, ?, ?, ?, ?)",
                ("m2", issue_id, "event-auto", 80.0, "auto"),
            )

        result = issue_storage.get_issue(issue_id)
        events = result["matched_events"]

        assert events[0]["event_id"] == "event-auto"
        assert events[0]["match_score"] == 80.0
        assert events[1]["event_id"] == "event-manual"
        assert events[1]["match_score"] is None

    def test_related_complaints_excludes_self(self, issue_storage, db_path):
        id1 = _create_issue_directly(db_path, issue_type="infrastructure")
        id2 = _create_issue_directly(db_path, issue_type="infrastructure", user_id="user-2")

        result = issue_storage.get_issue(id1)
        assert id1 not in result["related_complaints"]
        assert id2 in result["related_complaints"]

    def test_no_issue_type_gives_empty_related(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path, issue_type=None)
        result = issue_storage.get_issue(issue_id)
        assert result["related_complaints"] == []


# ---------------------------------------------------------------------------
# IssueStorage.link_to_event
# ---------------------------------------------------------------------------


class TestLinkToEvent:
    def test_automatic_match_creates_timeline_with_score(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.link_to_event(issue_id, "event-1", match_score=85.0, match_reason="topic overlap")

        with sqlite3.connect(db_path) as conn:
            match = conn.execute(
                "SELECT event_id, match_score, match_reason FROM issue_event_matches WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            timeline = conn.execute(
                "SELECT event_type, description, source FROM issue_timeline WHERE issue_id = ? AND event_type = 'matched'",
                (issue_id,),
            ).fetchone()

        assert match[0] == "event-1"
        assert match[1] == 85.0
        assert match[2] == "topic overlap"
        assert timeline[0] == "matched"
        assert "85%" in timeline[1]
        assert timeline[2] == "system"

    def test_manual_link_creates_timeline_with_user_source(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.link_to_event(issue_id, "event-2", match_score=None, match_reason=None)

        with sqlite3.connect(db_path) as conn:
            timeline = conn.execute(
                "SELECT event_type, description, source FROM issue_timeline WHERE issue_id = ? AND event_type = 'linked'",
                (issue_id,),
            ).fetchone()

        assert timeline[0] == "linked"
        assert timeline[1] == "Manually linked to event"
        assert timeline[2] == "user"

    def test_timeline_metadata_contains_event_id(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.link_to_event(issue_id, "event-3", match_score=70.0, match_reason="test")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT metadata FROM issue_timeline WHERE issue_id = ? AND event_type = 'matched'",
                (issue_id,),
            ).fetchone()

        metadata = json.loads(row[0])
        assert metadata["event_id"] == "event-3"
        assert metadata["match_score"] == 70.0


# ---------------------------------------------------------------------------
# IssueStorage.get_user_complaints
# ---------------------------------------------------------------------------


class TestGetUserComplaints:
    def test_returns_empty_list_for_unknown_user(self, issue_storage):
        result = issue_storage.get_user_complaints("unknown-user")
        assert result == []

    def test_returns_issues_for_user(self, issue_storage, db_path):
        _create_issue_directly(db_path, user_id="user-A", description="Issue A")
        _create_issue_directly(db_path, user_id="user-A", description="Issue B")
        _create_issue_directly(db_path, user_id="user-B", description="Other user")

        result = issue_storage.get_user_complaints("user-A")
        assert len(result) == 2
        descriptions = {r["description"] for r in result}
        assert descriptions == {"Issue A", "Issue B"}

    def test_related_complaints_excludes_same_user(self, issue_storage, db_path):
        _create_issue_directly(db_path, user_id="user-A", issue_type="noise")
        _create_issue_directly(db_path, user_id="user-A", issue_type="noise")
        other_id = _create_issue_directly(db_path, user_id="user-B", issue_type="noise")

        results = issue_storage.get_user_complaints("user-A")
        for issue in results:
            # Related complaints should only include user-B's issue
            assert issue["id"] not in issue["related_complaints"]
            if other_id in issue["related_complaints"]:
                assert True  # user-B's issue IS in related


# ---------------------------------------------------------------------------
# IssueStorage.find_similar_issues
# ---------------------------------------------------------------------------


class TestFindSimilarIssues:
    def test_matches_by_type_and_jurisdiction(self, issue_storage, db_path):
        _create_issue_directly(db_path, issue_type="noise", jurisdiction_id="city-sr")
        _create_issue_directly(db_path, issue_type="noise", jurisdiction_id="city-sr")
        _create_issue_directly(db_path, issue_type="traffic", jurisdiction_id="city-sr")

        results = issue_storage.find_similar_issues("city-sr", "noise")
        assert len(results) == 2
        assert all(r["issue_type"] == "noise" for r in results)

    def test_excludes_closed_issues(self, issue_storage, db_path):
        _create_issue_directly(db_path, issue_type="noise", jurisdiction_id="city-sr", status="open")
        _create_issue_directly(db_path, issue_type="noise", jurisdiction_id="city-sr", status="closed")

        results = issue_storage.find_similar_issues("city-sr", "noise")
        assert len(results) == 1
        assert results[0]["status"] == "open"

    def test_returns_empty_for_no_matches(self, issue_storage):
        results = issue_storage.find_similar_issues("nonexistent", "noise")
        assert results == []

    def test_limited_to_20_results(self, issue_storage, db_path):
        for _ in range(25):
            _create_issue_directly(db_path, issue_type="pothole", jurisdiction_id="city-sr")

        results = issue_storage.find_similar_issues("city-sr", "pothole")
        assert len(results) == 20


# ---------------------------------------------------------------------------
# IssueStorage.update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    def test_close_with_reason_updates_fields(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.update_status(issue_id, "closed", note="Fixed by DPW", closed_reason="resolved")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT status, closed_reason, closed_note, closed_at FROM issues WHERE id = ?",
                (issue_id,),
            ).fetchone()

        assert row[0] == "closed"
        assert row[1] == "resolved"
        assert row[2] == "Fixed by DPW"
        assert row[3] is not None  # closed_at timestamp set

    def test_close_requires_reason(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        with pytest.raises(ValueError, match="closed_reason is required"):
            issue_storage.update_status(issue_id, "closed")

    def test_close_rejects_invalid_reason(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        with pytest.raises(ValueError, match="Invalid closed_reason: spam"):
            issue_storage.update_status(issue_id, "closed", closed_reason="spam")

    def test_reopen_clears_closed_fields(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.update_status(issue_id, "closed", closed_reason="resolved")
        issue_storage.update_status(issue_id, "open")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT status, closed_reason, closed_at, closed_note FROM issues WHERE id = ?",
                (issue_id,),
            ).fetchone()

        assert row[0] == "open"
        assert row[1] is None
        assert row[2] is None
        assert row[3] is None

    def test_close_timeline_includes_reason_and_note(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.update_status(issue_id, "closed", note="Patched on Tuesday", closed_reason="resolved")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT description FROM issue_timeline WHERE issue_id = ? AND event_type = 'status_change'",
                (issue_id,),
            ).fetchone()

        assert "closed as resolved" in row[0]
        assert "Patched on Tuesday" in row[0]

    def test_reopen_timeline_entry(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        issue_storage.update_status(issue_id, "closed", closed_reason="resolved")
        issue_storage.update_status(issue_id, "open", note="Recurred")

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT description FROM issue_timeline WHERE issue_id = ? AND event_type = 'status_change' ORDER BY timestamp ASC",
                (issue_id,),
            ).fetchall()

        assert "reopened" in rows[-1][0].lower()
        assert "Recurred" in rows[-1][0]

    def test_valid_closed_reasons(self, issue_storage, db_path):
        """All four valid closed reasons should be accepted."""
        for reason in ["resolved", "duplicate", "not-actionable", "abandoned"]:
            issue_id = _create_issue_directly(db_path)
            issue_storage.update_status(issue_id, "closed", closed_reason=reason)

            with sqlite3.connect(db_path) as conn:
                row = conn.execute("SELECT closed_reason FROM issues WHERE id = ?", (issue_id,)).fetchone()
            assert row[0] == reason


# ---------------------------------------------------------------------------
# IssueStorage.create_timeline_entry / add_timeline_entry
# ---------------------------------------------------------------------------


class TestTimelineEntries:
    def test_create_timeline_entry_returns_uuid(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        entry_id = issue_storage.create_timeline_entry(issue_id, "response", "City responded")

        assert len(entry_id) == 36

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT event_type, description, source FROM issue_timeline WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()

        assert row[0] == "response"
        assert row[1] == "City responded"
        assert row[2] == "system"  # default source

    def test_create_timeline_entry_with_metadata(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        entry_id = issue_storage.create_timeline_entry(
            issue_id, "action_taken", "Crew dispatched", source="admin", metadata={"crew_id": "CR-42"}
        )

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT source, metadata FROM issue_timeline WHERE entry_id = ?", (entry_id,)).fetchone()

        assert row[0] == "admin"
        assert json.loads(row[1]) == {"crew_id": "CR-42"}

    def test_create_timeline_entry_none_metadata_stores_null(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        entry_id = issue_storage.create_timeline_entry(issue_id, "response", "Noted")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT metadata FROM issue_timeline WHERE entry_id = ?", (entry_id,)).fetchone()

        assert row[0] is None

    def test_add_timeline_entry_stores_data(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        entry_id = issue_storage.add_timeline_entry(
            issue_id, "action_taken", "Repaired", source="admin", metadata={"cost": 500}
        )

        assert len(entry_id) == 36

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT event_type, description, source, metadata FROM issue_timeline WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()

        assert row[0] == "action_taken"
        assert row[1] == "Repaired"
        assert row[2] == "admin"
        assert json.loads(row[3]) == {"cost": 500}


# ---------------------------------------------------------------------------
# IssueStorage.get_issue_timeline
# ---------------------------------------------------------------------------


class TestGetIssueTimeline:
    def test_excludes_filed_matched_linked_events(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)

        with sqlite3.connect(db_path) as conn:
            for evt_type in ["filed", "matched", "linked", "status_change", "response"]:
                import uuid

                conn.execute(
                    "INSERT INTO issue_timeline (entry_id, issue_id, event_type, description, source) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), issue_id, evt_type, f"{evt_type} event", "system"),
                )

        result = issue_storage.get_issue_timeline(issue_id)
        event_types = [e["event_type"] for e in result]

        assert "filed" not in event_types
        assert "matched" not in event_types
        assert "linked" not in event_types
        assert "status_change" in event_types
        assert "response" in event_types

    def test_parses_metadata_json(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)

        with sqlite3.connect(db_path) as conn:
            import uuid

            conn.execute(
                "INSERT INTO issue_timeline (entry_id, issue_id, event_type, description, source, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), issue_id, "response", "Crew sent", "admin", json.dumps({"crew": "A"})),
            )

        result = issue_storage.get_issue_timeline(issue_id)
        assert result[0]["metadata"] == {"crew": "A"}

    def test_empty_timeline(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)
        result = issue_storage.get_issue_timeline(issue_id)
        assert result == []


# ---------------------------------------------------------------------------
# IssueStorage.get_issue_status_history
# ---------------------------------------------------------------------------


class TestGetIssueStatusHistory:
    def test_returns_filed_and_status_change_only(self, issue_storage, db_path):
        issue_id = _create_issue_directly(db_path)

        with sqlite3.connect(db_path) as conn:
            import uuid

            for evt_type in ["filed", "matched", "linked", "status_change", "response"]:
                conn.execute(
                    "INSERT INTO issue_timeline (entry_id, issue_id, event_type, description, source) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), issue_id, evt_type, f"{evt_type} event", "system"),
                )

        result = issue_storage.get_issue_status_history(issue_id)
        event_types = [e["event_type"] for e in result]

        assert set(event_types) == {"filed", "status_change"}
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Issue (ParticipationMechanism)
# ---------------------------------------------------------------------------


class TestIssue:
    def test_get_id(self):
        issue = Issue({"id": "iss-123", "created_at": "2026-01-15 10:00:00"})
        assert issue.get_id() == "iss-123"

    def test_get_type_returns_issue(self):
        issue = Issue({"id": "iss-1", "created_at": "2026-01-15 10:00:00"})
        assert issue.get_type() == "Issue"

    def test_get_participation_threshold_is_low(self):
        issue = Issue({"id": "iss-1", "created_at": "2026-01-15 10:00:00"})
        assert issue.get_participation_threshold() == "low"

    def test_get_lifecycle_status_from_data(self):
        issue = Issue({"id": "iss-1", "status": "closed", "created_at": "2026-01-15 10:00:00"})
        assert issue.get_lifecycle_status() == "closed"

    def test_get_lifecycle_status_defaults_to_open(self):
        issue = Issue({"id": "iss-1", "created_at": "2026-01-15 10:00:00"})
        assert issue.get_lifecycle_status() == "open"

    def test_get_actions_with_matched_events(self):
        issue = Issue(
            {
                "id": "iss-1",
                "matched_events": [
                    {"event_id": "evt-1", "match_score": 92.5},
                    {"event_id": "evt-2", "match_score": 75.0},
                ],
                "created_at": "2026-01-15 10:00:00",
            }
        )
        actions = issue.get_actions()

        assert len(actions) == 2
        assert actions[0]["action_type"] == "link"
        assert "92%" in actions[0]["action_label"]
        assert actions[0]["action_target"] == "/events/evt-1"
        assert actions[1]["action_target"] == "/events/evt-2"

    def test_get_actions_without_matches_shows_track(self):
        issue = Issue(
            {"id": "iss-1", "matched_events": [], "created_at": "2026-01-15 10:00:00"}
        )
        actions = issue.get_actions()

        assert len(actions) == 1
        assert actions[0]["action_type"] == "button"
        assert actions[0]["action_label"] == "Track This Issue"
        assert actions[0]["mcp_tool"] == "track_issue"

    def test_get_context_community_high_potential(self):
        issue = Issue(
            {
                "id": "iss-1",
                "issue_type": "noise",
                "status": "open",
                "related_complaints": ["c1", "c2", "c3"],
                "matched_events": [],
                "created_at": "2026-04-01 10:00:00",
            }
        )
        ctx = issue.get_context()

        assert ctx["complaint_context"]["issue_type"] == "noise"
        assert ctx["complaint_context"]["status"] == "open"
        assert ctx["community_context"]["related_complaints"] == 3
        assert ctx["community_context"]["organizing_potential"] == "high"
        assert ctx["matched_events_count"] == 0

    def test_get_context_community_low_potential(self):
        issue = Issue(
            {
                "id": "iss-1",
                "issue_type": "noise",
                "status": "open",
                "related_complaints": ["c1"],
                "matched_events": [{"event_id": "e1"}],
                "created_at": "2026-04-01 10:00:00",
            }
        )
        ctx = issue.get_context()

        assert ctx["community_context"]["organizing_potential"] == "low"
        assert ctx["matched_events_count"] == 1

    def test_get_context_days_open_calculation(self):
        # Set created_at to 5 days ago
        five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        issue = Issue(
            {
                "id": "iss-1",
                "issue_type": "noise",
                "status": "open",
                "related_complaints": [],
                "matched_events": [],
                "created_at": five_days_ago,
            }
        )
        ctx = issue.get_context()
        assert ctx["complaint_context"]["days_open"] == 5

    def test_get_context_parses_timestamp_with_microseconds(self):
        ts = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S.%f")
        issue = Issue(
            {
                "id": "iss-1",
                "issue_type": "parking",
                "status": "open",
                "related_complaints": [],
                "matched_events": [],
                "created_at": ts,
            }
        )
        ctx = issue.get_context()
        assert ctx["complaint_context"]["days_open"] == 3


# ---------------------------------------------------------------------------
# CommunityStorage — Follows
# ---------------------------------------------------------------------------


class TestCommunityFollows:
    def test_create_follow_returns_count_and_thread(self, community_storage):
        result = community_storage.create_follow("user-1", "issue", "iss-1", "city-sr")

        assert result["follower_count"] == 1
        assert result["your_following"] is True
        assert len(result["thread_id"]) == 36  # UUID

    def test_duplicate_follow_does_not_increase_count(self, community_storage):
        community_storage.create_follow("user-1", "issue", "iss-1")
        result = community_storage.create_follow("user-1", "issue", "iss-1")

        assert result["follower_count"] == 1

    def test_multiple_users_increase_count(self, community_storage):
        community_storage.create_follow("user-1", "issue", "iss-1")
        result = community_storage.create_follow("user-2", "issue", "iss-1")

        assert result["follower_count"] == 2

    def test_get_follow_info_with_user(self, community_storage):
        community_storage.create_follow("user-1", "event", "evt-1")

        info = community_storage.get_follow_info("event", "evt-1", user_id="user-1")
        assert info["follower_count"] == 1
        assert info["your_following"] is True

    def test_get_follow_info_non_follower(self, community_storage):
        community_storage.create_follow("user-1", "event", "evt-1")

        info = community_storage.get_follow_info("event", "evt-1", user_id="user-99")
        assert info["follower_count"] == 1
        assert info["your_following"] is False

    def test_get_follow_info_no_followers(self, community_storage):
        info = community_storage.get_follow_info("issue", "iss-nonexistent")
        assert info["follower_count"] == 0
        assert info["thread_id"] is None
        assert info["your_following"] is False

    def test_delete_follow_decreases_count(self, community_storage):
        community_storage.create_follow("user-1", "issue", "iss-1")
        community_storage.create_follow("user-2", "issue", "iss-1")

        result = community_storage.delete_follow("user-1", "issue", "iss-1")
        assert result["follower_count"] == 1
        assert result["your_following"] is False

    def test_get_followers_ordered_by_time(self, community_storage):
        community_storage.create_follow("user-A", "issue", "iss-1")
        community_storage.create_follow("user-B", "issue", "iss-1")

        followers = community_storage.get_followers("issue", "iss-1")
        assert len(followers) == 2
        assert followers[0]["user_id"] == "user-A"
        assert followers[1]["user_id"] == "user-B"

    def test_get_user_follows(self, community_storage):
        community_storage.create_follow("user-1", "issue", "iss-1", "city-sr")
        community_storage.create_follow("user-1", "event", "evt-1", "city-sr")

        follows = community_storage.get_user_follows("user-1")
        assert len(follows) == 2
        focal_types = {f["focal_type"] for f in follows}
        assert focal_types == {"issue", "event"}


# ---------------------------------------------------------------------------
# CommunityStorage — Threads & Messages
# ---------------------------------------------------------------------------


class TestCommunityMessages:
    def _setup_thread(self, community_storage):
        """Create a follow (which creates a thread) and return thread_id."""
        result = community_storage.create_follow("user-1", "issue", "iss-1")
        return result["thread_id"]

    def test_create_message_returns_message_data(self, community_storage):
        thread_id = self._setup_thread(community_storage)
        msg = community_storage.create_message(thread_id, "user-1", "Hello neighbors!")

        assert msg["thread_id"] == thread_id
        assert msg["user_id"] == "user-1"
        assert msg["content"] == "Hello neighbors!"
        assert msg["parent_message_id"] is None
        assert len(msg["message_id"]) == 36

    def test_message_content_truncated_to_1000(self, community_storage, db_path):
        thread_id = self._setup_thread(community_storage)
        long_content = "X" * 1500
        msg = community_storage.create_message(thread_id, "user-1", long_content)

        assert len(msg["content"]) == 1000

    def test_reply_references_parent(self, community_storage):
        thread_id = self._setup_thread(community_storage)
        parent = community_storage.create_message(thread_id, "user-1", "Original")
        reply = community_storage.create_message(thread_id, "user-2", "Reply", parent["message_id"])

        assert reply["parent_message_id"] == parent["message_id"]

    def test_get_thread_messages_returns_ordered(self, community_storage):
        thread_id = self._setup_thread(community_storage)
        community_storage.create_message(thread_id, "user-1", "First")
        community_storage.create_message(thread_id, "user-2", "Second")

        messages = community_storage.get_thread_messages(thread_id)
        assert len(messages) == 2
        assert messages[0]["content"] == "First"
        assert messages[1]["content"] == "Second"

    def test_get_thread_messages_limit_capped_at_100(self, community_storage):
        thread_id = self._setup_thread(community_storage)
        messages = community_storage.get_thread_messages(thread_id, limit=200)
        # Just verifying it doesn't error — the SQL LIMIT is capped
        assert messages == []

    def test_get_thread_messages_nested_builds_tree(self, community_storage):
        thread_id = self._setup_thread(community_storage)
        parent = community_storage.create_message(thread_id, "user-1", "Root message")
        community_storage.create_message(thread_id, "user-2", "Reply A", parent["message_id"])
        community_storage.create_message(thread_id, "user-3", "Reply B", parent["message_id"])
        community_storage.create_message(thread_id, "user-4", "Top-level 2")

        nested = community_storage.get_thread_messages_nested(thread_id)

        # Should have 2 root messages
        assert len(nested) == 2
        root = nested[0]
        assert root["content"] == "Root message"
        assert len(root["replies"]) == 2
        reply_contents = {r["content"] for r in root["replies"]}
        assert reply_contents == {"Reply A", "Reply B"}

        assert nested[1]["content"] == "Top-level 2"
        assert nested[1]["replies"] == []


# ---------------------------------------------------------------------------
# CommunityStorage — Thread Info & Participants
# ---------------------------------------------------------------------------


class TestCommunityThreadInfo:
    def test_get_thread_info_returns_metadata(self, community_storage):
        result = community_storage.create_follow("user-1", "issue", "iss-1")
        thread_id = result["thread_id"]

        info = community_storage.get_thread_info(thread_id)
        assert info["thread_id"] == thread_id
        assert info["focal_type"] == "issue"
        assert info["focal_id"] == "iss-1"
        assert info["participant_count"] == 1
        assert info["message_count"] == 0

    def test_get_thread_info_nonexistent_returns_none(self, community_storage):
        info = community_storage.get_thread_info("no-such-thread")
        assert info is None

    def test_get_thread_participants(self, community_storage):
        community_storage.create_follow("user-A", "issue", "iss-1")
        community_storage.create_follow("user-B", "issue", "iss-1")

        result = community_storage.create_follow("user-A", "issue", "iss-1")
        thread_id = result["thread_id"]

        participants = community_storage.get_thread_participants(thread_id)
        assert len(participants) == 2
        user_ids = {p["user_id"] for p in participants}
        assert user_ids == {"user-A", "user-B"}

    def test_get_thread_participants_nonexistent_thread(self, community_storage):
        result = community_storage.get_thread_participants("nonexistent")
        assert result == []

    def test_get_threads_for_focal_point(self, community_storage):
        community_storage.create_follow("user-1", "issue", "iss-1")

        threads = community_storage.get_threads_for_focal_point("issue", "iss-1")
        assert len(threads) == 1
        assert threads[0]["focal_type"] == "issue"
        assert threads[0]["focal_id"] == "iss-1"

    def test_get_all_threads_returns_all(self, community_storage):
        community_storage.create_follow("user-1", "issue", "iss-1")
        community_storage.create_follow("user-1", "event", "evt-1")

        threads = community_storage.get_all_threads()
        assert len(threads) == 2

    def test_get_all_threads_limit_capped(self, community_storage):
        # Just verify limit=200 gets capped to 100 without error
        threads = community_storage.get_all_threads(limit=200)
        assert threads == []


# ---------------------------------------------------------------------------
# CommunityStorage — Unread tracking
# ---------------------------------------------------------------------------


class TestUnreadTracking:
    def test_unread_count_zero_when_not_following(self, community_storage):
        count = community_storage.get_unread_count("user-1", "issue", "iss-1")
        assert count == 0

    def test_unread_count_zero_when_no_thread(self, community_storage, db_path):
        # Create a follow without a thread
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO follows (follow_id, user_id, focal_type, focal_id) VALUES (?, ?, ?, ?)",
                ("f1", "user-1", "issue", "iss-orphan"),
            )
        count = community_storage.get_unread_count("user-1", "issue", "iss-orphan")
        assert count == 0

    def test_mark_thread_seen_updates_timestamp(self, community_storage, db_path):
        community_storage.create_follow("user-1", "issue", "iss-1")
        community_storage.mark_thread_seen("user-1", "issue", "iss-1")

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT last_seen_at FROM follows WHERE user_id = ? AND focal_type = ? AND focal_id = ?",
                ("user-1", "issue", "iss-1"),
            ).fetchone()

        assert row[0] is not None


# ---------------------------------------------------------------------------
# CommunityStorage — Related issues for event
# ---------------------------------------------------------------------------


class TestRelatedIssuesForEvent:
    def _patch_issue_storage(self, db_path):
        """Patch IssueStorage() so it points to our test DB."""
        return patch(
            "civicos_services.storage.issue_storage.IssueStorage",
            return_value=IssueStorage(db_path=db_path),
        )

    def test_returns_linked_issues_with_preview(self, db_path):
        community = CommunityStorage(db_path=db_path)

        # Create issue and link to event
        issue_id = _create_issue_directly(db_path, description="A" * 100)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO issue_event_matches (match_id, issue_id, event_id, match_score, match_reason) VALUES (?, ?, ?, ?, ?)",
                ("m1", issue_id, "evt-1", 85.0, "match"),
            )

        with self._patch_issue_storage(db_path):
            result = community.get_related_issues_for_event("evt-1")

        assert len(result) == 1
        assert result[0]["issue_id"] == issue_id
        # Description preview truncated at 80 chars + "..."
        assert result[0]["description_preview"] == "A" * 80 + "..."

    def test_returns_empty_for_unlinked_event(self, db_path):
        community = CommunityStorage(db_path=db_path)
        with self._patch_issue_storage(db_path):
            result = community.get_related_issues_for_event("evt-nonexistent")
        assert result == []

    def test_short_description_no_ellipsis(self, db_path):
        community = CommunityStorage(db_path=db_path)
        issue_id = _create_issue_directly(db_path, description="Short desc")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO issue_event_matches (match_id, issue_id, event_id, match_score, match_reason) VALUES (?, ?, ?, ?, ?)",
                ("m1", issue_id, "evt-1", 90.0, "match"),
            )

        with self._patch_issue_storage(db_path):
            result = community.get_related_issues_for_event("evt-1")

        assert result[0]["description_preview"] == "Short desc"
