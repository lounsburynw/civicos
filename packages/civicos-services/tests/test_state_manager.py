"""
Tests for state_manager.py — StateManager temporal versioning, query filters,
operation tracking, and SeeClickFix import.

Uses a real SQLite database in a temp directory. No mocks — the module
is pure DB logic with no external dependencies to mock.

To run:
    pytest packages/civicos-services/tests/test_state_manager.py -q --override-ini="addopts="
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from civicos_services.storage.state_manager import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return a temp DB path for a fresh StateManager."""
    return str(tmp_path / "test_state.db")


@pytest.fixture
def mgr(db_path):
    """StateManager backed by a temp SQLite DB."""
    return StateManager(db_path)


SAMPLE_MEETINGS = [
    {
        "id": "mtg-001",
        "title": "City Council Regular Meeting",
        "meeting_datetime": "2025-11-18T18:00:00",
        "meeting_type": "city_council",
        "status": "scheduled",
        "location": "City Hall",
        "source_platform": "legistar",
    },
    {
        "id": "mtg-002",
        "title": "Planning Commission",
        "meeting_datetime": "2025-11-20T19:00:00",
        "meeting_type": "planning_commission",
        "status": "scheduled",
        "location": "City Hall Room 2",
        "source_platform": "legistar",
    },
]


# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------

class TestSchemaCreation:
    def test_creates_all_tables(self, db_path):
        StateManager(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "city_states" in tables
        assert "meetings" in tables
        assert "agenda_items" in tables
        assert "issues" in tables
        assert "operations" in tables

    def test_creates_indexes(self, db_path):
        StateManager(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_meetings_jurisdiction" in indexes
        assert "idx_meetings_datetime" in indexes
        assert "idx_meetings_temporal" in indexes
        assert "idx_agenda_items_meeting" in indexes
        assert "idx_issues_jurisdiction" in indexes
        assert "idx_operations_status" in indexes

    def test_idempotent_schema_creation(self, db_path):
        """Creating StateManager twice on same DB does not error."""
        StateManager(db_path)
        mgr2 = StateManager(db_path)
        # Verify it still works after double init
        stats = mgr2.get_stats("nonexistent")
        assert stats["current_meetings"] == 0


# ---------------------------------------------------------------------------
# update_meetings
# ---------------------------------------------------------------------------

class TestUpdateMeetings:
    def test_inserts_meetings_and_returns_count(self, mgr):
        count = mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS)
        assert count == 2

    def test_creates_city_state_on_first_insert(self, mgr):
        as_of = datetime(2025, 11, 1, 12, 0, 0)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=as_of)

        conn = sqlite3.connect(mgr.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM city_states WHERE jurisdiction_id = 'city-berkeley'"
        )
        row = cursor.fetchone()
        conn.close()

        assert row["jurisdiction_name"] == "City Berkeley"
        assert row["jurisdiction_id"] == "city-berkeley"

    def test_meeting_data_persisted_correctly(self, mgr):
        as_of = datetime(2025, 11, 1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=as_of)

        conn = sqlite3.connect(mgr.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM meetings WHERE id = 'mtg-001' AND valid_to IS NULL"
        )
        row = cursor.fetchone()
        conn.close()

        assert row["title"] == "City Council Regular Meeting"
        assert row["meeting_type"] == "city_council"
        assert row["location"] == "City Hall"
        assert row["source_platform"] == "legistar"
        assert row["jurisdiction_id"] == "city-berkeley"

    def test_temporal_versioning_closes_old_records(self, mgr):
        t1 = datetime(2025, 11, 1)
        t2 = datetime(2025, 11, 2)

        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=t1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS[:1], as_of=t2)

        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()

        # Old versions should have valid_to set to t2
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE jurisdiction_id='city-berkeley' AND valid_to IS NOT NULL"
        )
        closed = cursor.fetchone()[0]

        # New version should have valid_to IS NULL
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE jurisdiction_id='city-berkeley' AND valid_to IS NULL"
        )
        current = cursor.fetchone()[0]
        conn.close()

        assert closed == 2  # Both original meetings closed
        assert current == 1  # Only mtg-001 in second batch

    def test_empty_meetings_list_closes_all(self, mgr):
        t1 = datetime(2025, 11, 1)
        t2 = datetime(2025, 11, 2)

        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=t1)
        count = mgr.update_meetings("city-berkeley", [], as_of=t2)

        assert count == 0

        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE jurisdiction_id='city-berkeley' AND valid_to IS NULL"
        )
        current = cursor.fetchone()[0]
        conn.close()

        assert current == 0

    def test_full_data_stored_as_json(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS)

        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT full_data FROM meetings WHERE id='mtg-001' AND valid_to IS NULL"
        )
        raw = cursor.fetchone()[0]
        conn.close()

        parsed = json.loads(raw)
        assert parsed["title"] == "City Council Regular Meeting"
        assert parsed["meeting_type"] == "city_council"

    def test_default_source_platform_when_missing(self, mgr):
        meetings = [{"id": "mtg-x", "title": "Test", "meeting_datetime": "2025-01-01"}]
        mgr.update_meetings("city-test", meetings)

        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source_platform FROM meetings WHERE id='mtg-x' AND valid_to IS NULL"
        )
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "unknown"


# ---------------------------------------------------------------------------
# get_city_state
# ---------------------------------------------------------------------------

class TestGetCityState:
    def test_returns_error_for_unknown_jurisdiction(self, mgr):
        state = mgr.get_city_state("city-nonexistent")
        assert state["error"] == "No data for city-nonexistent"
        assert state["jurisdiction_id"] == "city-nonexistent"

    def test_returns_meetings_for_known_jurisdiction(self, mgr):
        as_of = datetime(2025, 11, 1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=as_of)

        state = mgr.get_city_state("city-berkeley", as_of=datetime(2025, 11, 5))
        assert state["jurisdiction_id"] == "city-berkeley"
        assert state["jurisdiction_name"] == "City Berkeley"
        assert len(state["meetings"]) == 2
        assert state["meetings"][0]["title"] == "City Council Regular Meeting"
        assert state["meetings"][1]["title"] == "Planning Commission"

    def test_temporal_query_sees_only_active_version(self, mgr):
        t1 = datetime(2025, 11, 1)
        t2 = datetime(2025, 11, 5)

        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=t1)

        updated = [{"id": "mtg-003", "title": "New Meeting", "meeting_datetime": "2025-11-25T18:00:00", "source_platform": "legistar"}]
        mgr.update_meetings("city-berkeley", updated, as_of=t2)

        # Query at t1 + 1 day: should see original 2 meetings
        state_early = mgr.get_city_state("city-berkeley", as_of=datetime(2025, 11, 3))
        assert len(state_early["meetings"]) == 2

        # Query at t2 + 1 day: should see only new meeting
        state_late = mgr.get_city_state("city-berkeley", as_of=datetime(2025, 11, 6))
        assert len(state_late["meetings"]) == 1
        assert state_late["meetings"][0]["title"] == "New Meeting"

    def test_full_data_json_parsed_in_meetings(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        state = mgr.get_city_state("city-berkeley", as_of=datetime(2025, 11, 5))

        full_data = state["meetings"][0]["full_data"]
        assert full_data["id"] == "mtg-001"
        assert full_data["title"] == "City Council Regular Meeting"

    def test_returns_default_metric_values(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        state = mgr.get_city_state("city-berkeley", as_of=datetime(2025, 11, 5))

        assert state["active_residents"] == 0
        assert state["pending_comments"] == 0
        assert state["completeness_score"] == 0.0


# ---------------------------------------------------------------------------
# query_meetings
# ---------------------------------------------------------------------------

class TestQueryMeetings:
    def test_returns_all_current_meetings(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        results = mgr.query_meetings("city-berkeley", as_of=datetime(2025, 11, 5))
        assert len(results) == 2

    def test_filters_by_date_from(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        results = mgr.query_meetings(
            "city-berkeley",
            date_from=datetime(2025, 11, 19),
            as_of=datetime(2025, 11, 25),
        )
        assert len(results) == 1
        assert results[0]["title"] == "Planning Commission"

    def test_filters_by_date_to(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        results = mgr.query_meetings(
            "city-berkeley",
            date_to=datetime(2025, 11, 19),
            as_of=datetime(2025, 11, 25),
        )
        assert len(results) == 1
        assert results[0]["title"] == "City Council Regular Meeting"

    def test_date_range_returns_empty_when_none_match(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        results = mgr.query_meetings(
            "city-berkeley",
            date_from=datetime(2026, 1, 1),
            date_to=datetime(2026, 2, 1),
            as_of=datetime(2026, 3, 1),
        )
        assert results == []

    def test_empty_jurisdiction_returns_empty_list(self, mgr):
        results = mgr.query_meetings("city-nonexistent")
        assert results == []

    def test_project_type_filter_with_agenda_items(self, mgr):
        as_of = datetime(2025, 11, 1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=as_of)

        # Insert an agenda item for mtg-001 with project_type "housing"
        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agenda_items (id, meeting_id, title, project_type, valid_from)
            VALUES ('ai-001', 'mtg-001', 'Housing Plan', 'housing', ?)
        """, (as_of.isoformat(),))
        conn.commit()
        conn.close()

        results = mgr.query_meetings(
            "city-berkeley",
            project_type="housing",
            as_of=datetime(2025, 11, 5),
        )
        assert len(results) == 1
        assert results[0]["id"] == "mtg-001"

    def test_project_type_filter_excludes_non_matching(self, mgr):
        as_of = datetime(2025, 11, 1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=as_of)

        # Insert an agenda item with a different type
        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agenda_items (id, meeting_id, title, project_type, valid_from)
            VALUES ('ai-001', 'mtg-001', 'Parks Plan', 'parks', ?)
        """, (as_of.isoformat(),))
        conn.commit()
        conn.close()

        results = mgr.query_meetings(
            "city-berkeley",
            project_type="housing",
            as_of=datetime(2025, 11, 5),
        )
        assert results == []


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_empty_jurisdiction_returns_zeros(self, mgr):
        stats = mgr.get_stats("city-empty")
        assert stats["jurisdiction_id"] == "city-empty"
        assert stats["current_meetings"] == 0
        assert stats["historical_versions"] == 0
        assert stats["current_agenda_items"] == 0
        assert stats["date_range"]["earliest"] is None
        assert stats["date_range"]["latest"] is None

    def test_counts_current_and_historical(self, mgr):
        t1 = datetime(2025, 11, 1)
        t2 = datetime(2025, 11, 5)

        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=t1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS[:1], as_of=t2)

        stats = mgr.get_stats("city-berkeley")
        assert stats["current_meetings"] == 1
        assert stats["historical_versions"] == 2  # 2 closed from t1

    def test_date_range_reflects_meetings(self, mgr):
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=datetime(2025, 11, 1))
        stats = mgr.get_stats("city-berkeley")

        assert stats["date_range"]["earliest"] == "2025-11-18T18:00:00"
        assert stats["date_range"]["latest"] == "2025-11-20T19:00:00"

    def test_counts_agenda_items(self, mgr):
        as_of = datetime(2025, 11, 1)
        mgr.update_meetings("city-berkeley", SAMPLE_MEETINGS, as_of=as_of)

        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agenda_items (id, meeting_id, title, valid_from)
            VALUES ('ai-1', 'mtg-001', 'Item 1', ?),
                   ('ai-2', 'mtg-001', 'Item 2', ?)
        """, (as_of.isoformat(), as_of.isoformat()))
        conn.commit()
        conn.close()

        stats = mgr.get_stats("city-berkeley")
        assert stats["current_agenda_items"] == 2


# ---------------------------------------------------------------------------
# query_issues
# ---------------------------------------------------------------------------

class TestQueryIssues:
    @pytest.fixture(autouse=True)
    def _seed_issues(self, mgr):
        """Insert test issues directly into the DB."""
        conn = sqlite3.connect(mgr.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
            VALUES ('city-test', 'Test City', '2025-11-01')
        """)
        issues = [
            ("iss-1", "city-test", "scf", "Pothole on Main St", "pothole", "123 Main St", "open", "2025-11-01"),
            ("iss-2", "city-test", "scf", "Graffiti on Oak Ave", "graffiti", "456 Oak Ave", "open", "2025-11-02"),
            ("iss-3", "city-test", "scf", "Pothole on Oak Ave", "pothole", "789 Oak Ave", "closed", "2025-10-15"),
        ]
        for iss_id, jid, src, title, itype, addr, status, created in issues:
            cursor.execute("""
                INSERT INTO issues (id, jurisdiction_id, source, title, issue_type, address, status, created_at, valid_from)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (iss_id, jid, src, title, itype, addr, status, created))
        conn.commit()
        conn.close()

    def test_returns_all_current_issues(self, mgr):
        results = mgr.query_issues("city-test")
        assert len(results) == 3

    def test_filters_by_status(self, mgr):
        results = mgr.query_issues("city-test", status="open")
        assert len(results) == 2
        assert all(r["status"] == "open" for r in results)

    def test_filters_by_issue_type(self, mgr):
        results = mgr.query_issues("city-test", issue_type="pothole")
        assert len(results) == 2
        assert all(r["issue_type"] == "pothole" for r in results)

    def test_filters_by_street_partial_match(self, mgr):
        results = mgr.query_issues("city-test", street="Oak")
        assert len(results) == 2
        assert all("Oak" in r["address"] for r in results)

    def test_combined_filters(self, mgr):
        results = mgr.query_issues("city-test", status="open", issue_type="pothole")
        assert len(results) == 1
        assert results[0]["title"] == "Pothole on Main St"

    def test_limit_restricts_results(self, mgr):
        results = mgr.query_issues("city-test", limit=1)
        assert len(results) == 1

    def test_empty_jurisdiction_returns_empty(self, mgr):
        results = mgr.query_issues("city-nonexistent")
        assert results == []

    def test_ordered_by_created_at_descending(self, mgr):
        results = mgr.query_issues("city-test", status="open")
        dates = [r["created_at"] for r in results]
        assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# import_seeclickfix_json
# ---------------------------------------------------------------------------

class TestImportSeeclickfixJson:
    def test_imports_flat_list_format(self, mgr, tmp_path):
        data = [
            {"id": 100, "summary": "Broken sidewalk", "status": "open", "category": "sidewalk"},
            {"id": 101, "summary": "Fallen tree", "status": "open", "category": "tree"},
        ]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        count = mgr.import_seeclickfix_json(str(json_file), "city-test")
        assert count == 2

        results = mgr.query_issues("city-test")
        titles = {r["title"] for r in results}
        assert "Broken sidewalk" in titles
        assert "Fallen tree" in titles

    def test_imports_dict_with_issues_key(self, mgr, tmp_path):
        data = {"issues": [{"id": 200, "summary": "Pothole", "status": "open"}]}
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        count = mgr.import_seeclickfix_json(str(json_file), "city-test")
        assert count == 1

    def test_extracts_nested_request_type(self, mgr, tmp_path):
        data = [{"id": 300, "summary": "Test", "request_type": {"title": "Graffiti"}}]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["issue_type"] == "Graffiti"

    def test_extracts_nested_location(self, mgr, tmp_path):
        data = [
            {
                "id": 400,
                "summary": "Pothole",
                "location": {"address": "1 Main St", "lat": 37.9, "lng": -122.5},
            }
        ]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["address"] == "1 Main St"
        assert results[0]["latitude"] == 37.9
        assert results[0]["longitude"] == -122.5

    def test_extracts_flat_location(self, mgr, tmp_path):
        data = [
            {
                "id": 500,
                "summary": "Flat loc",
                "address": "2 Oak Ave",
                "lat": 38.0,
                "lng": -122.0,
                "location": "not a dict",
            }
        ]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["address"] == "2 Oak Ave"
        assert results[0]["latitude"] == 38.0

    def test_uses_title_fallback_when_no_summary(self, mgr, tmp_path):
        data = [{"id": 600, "title": "My Title"}]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["title"] == "My Title"

    def test_uses_unknown_fallback_when_no_title_or_summary(self, mgr, tmp_path):
        data = [{"id": 700}]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["title"] == "Unknown Issue"

    def test_issue_id_format(self, mgr, tmp_path):
        data = [{"id": 999, "summary": "Test"}]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["id"] == "scf-999"
        assert results[0]["source"] == "seeclickfix"

    def test_issue_type_from_issue_type_field(self, mgr, tmp_path):
        data = [{"id": 800, "summary": "Test", "issue_type": "noise"}]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))

        mgr.import_seeclickfix_json(str(json_file), "city-test")
        results = mgr.query_issues("city-test")
        assert results[0]["issue_type"] == "noise"

    def test_empty_list_imports_zero(self, mgr, tmp_path):
        json_file = tmp_path / "empty.json"
        json_file.write_text("[]")

        count = mgr.import_seeclickfix_json(str(json_file), "city-test")
        assert count == 0


# ---------------------------------------------------------------------------
# get_issue_stats
# ---------------------------------------------------------------------------

class TestGetIssueStats:
    def test_empty_jurisdiction_returns_zero_total(self, mgr):
        stats = mgr.get_issue_stats("city-empty")
        assert stats["jurisdiction_id"] == "city-empty"
        assert stats["total_issues"] == 0
        assert stats["by_status"] == {}
        assert stats["top_types"] == []

    def test_counts_by_status(self, mgr, tmp_path):
        data = [
            {"id": 1, "summary": "A", "status": "open"},
            {"id": 2, "summary": "B", "status": "open"},
            {"id": 3, "summary": "C", "status": "closed"},
        ]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))
        mgr.import_seeclickfix_json(str(json_file), "city-test")

        stats = mgr.get_issue_stats("city-test")
        assert stats["total_issues"] == 3
        assert stats["by_status"]["open"] == 2
        assert stats["by_status"]["closed"] == 1

    def test_top_types_sorted_by_count(self, mgr, tmp_path):
        data = [
            {"id": 1, "summary": "A", "category": "pothole"},
            {"id": 2, "summary": "B", "category": "pothole"},
            {"id": 3, "summary": "C", "category": "graffiti"},
        ]
        json_file = tmp_path / "issues.json"
        json_file.write_text(json.dumps(data))
        mgr.import_seeclickfix_json(str(json_file), "city-test")

        stats = mgr.get_issue_stats("city-test")
        assert stats["top_types"][0] == ("pothole", 2)
        assert stats["top_types"][1] == ("graffiti", 1)


# ---------------------------------------------------------------------------
# Operation Tracking
# ---------------------------------------------------------------------------

class TestCreateOperation:
    def test_returns_operation_dict(self, mgr):
        op = mgr.create_operation("op-1", "city-test", "fetch_meetings")
        assert op["id"] == "op-1"
        assert op["jurisdiction_id"] == "city-test"
        assert op["name"] == "fetch_meetings"
        assert op["status"] == "pending"
        assert op["progress_percent"] == 0
        assert op["items_processed"] == 0
        assert op["items_total"] == 0

    def test_operation_persisted_in_db(self, mgr):
        mgr.create_operation("op-2", "city-test", "discover_videos")
        op = mgr.get_operation("op-2")
        assert op["name"] == "discover_videos"
        assert op["status"] == "pending"


class TestUpdateOperationStatus:
    def test_updates_status_and_progress(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        result = mgr.update_operation_status(
            "op-1",
            status="running",
            current_step="Downloading page 2",
            progress_percent=50.0,
            items_processed=5,
            items_total=10,
        )
        assert result is True

        op = mgr.get_operation("op-1")
        assert op["status"] == "running"
        assert op["current_step"] == "Downloading page 2"
        assert op["progress_percent"] == 50.0
        assert op["items_processed"] == 5
        assert op["items_total"] == 10

    def test_updates_only_status_when_optionals_omitted(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        mgr.update_operation_status("op-1", status="running")

        op = mgr.get_operation("op-1")
        assert op["status"] == "running"
        assert op["progress_percent"] == 0  # unchanged from create default

    def test_returns_false_for_nonexistent_operation(self, mgr):
        result = mgr.update_operation_status("op-nonexistent", status="running")
        assert result is False


class TestCompleteOperation:
    def test_marks_success(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        result = mgr.complete_operation("op-1", result={"meetings_found": 5})
        assert result is True

        op = mgr.get_operation("op-1")
        assert op["status"] == "completed"
        assert op["progress_percent"] == 100
        assert op["result"]["meetings_found"] == 5
        assert op["error"] is None
        assert op["completed_at"] is not None
        assert op["duration_seconds"] is not None
        assert op["duration_seconds"] >= 0

    def test_marks_failure_with_error(self, mgr):
        mgr.create_operation("op-2", "city-test", "fetch")
        result = mgr.complete_operation("op-2", result={}, error="Connection timeout")
        assert result is True

        op = mgr.get_operation("op-2")
        assert op["status"] == "failed"
        assert op["error"] == "Connection timeout"

    def test_returns_false_for_nonexistent_operation(self, mgr):
        result = mgr.complete_operation("op-nonexistent", result={})
        assert result is False


class TestGetOperation:
    def test_returns_none_for_nonexistent(self, mgr):
        assert mgr.get_operation("op-nope") is None

    def test_parses_result_json(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        mgr.complete_operation("op-1", result={"count": 42})

        op = mgr.get_operation("op-1")
        assert op["result"] == {"count": 42}

    def test_result_none_when_no_result_json(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        op = mgr.get_operation("op-1")
        assert op["result"] is None


class TestGetOperations:
    @pytest.fixture(autouse=True)
    def _seed_operations(self, mgr):
        mgr.create_operation("op-1", "city-a", "fetch")
        mgr.create_operation("op-2", "city-a", "discover")
        mgr.create_operation("op-3", "city-b", "fetch")
        mgr.update_operation_status("op-2", status="running")
        mgr.complete_operation("op-3", result={"ok": True})

    def test_returns_all_operations(self, mgr):
        ops = mgr.get_operations()
        assert len(ops) == 3

    def test_filters_by_jurisdiction(self, mgr):
        ops = mgr.get_operations(jurisdiction_id="city-a")
        assert len(ops) == 2
        assert all(op["jurisdiction_id"] == "city-a" for op in ops)

    def test_filters_by_status(self, mgr):
        ops = mgr.get_operations(status="completed")
        assert len(ops) == 1
        assert ops[0]["id"] == "op-3"

    def test_limit_restricts_count(self, mgr):
        ops = mgr.get_operations(limit=1)
        assert len(ops) == 1

    def test_results_parsed_for_completed(self, mgr):
        ops = mgr.get_operations(status="completed")
        assert ops[0]["result"] == {"ok": True}

    def test_result_none_for_pending(self, mgr):
        ops = mgr.get_operations(status="pending")
        assert all(op["result"] is None for op in ops)


class TestGetCurrentOperation:
    def test_returns_none_when_no_active_ops(self, mgr):
        assert mgr.get_current_operation("city-test") is None

    def test_returns_running_operation(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        mgr.update_operation_status("op-1", status="running")

        current = mgr.get_current_operation("city-test")
        assert current["id"] == "op-1"
        assert current["status"] == "running"

    def test_returns_pending_operation(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")

        current = mgr.get_current_operation("city-test")
        assert current["id"] == "op-1"
        assert current["status"] == "pending"

    def test_ignores_completed_operations(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        mgr.complete_operation("op-1", result={})

        assert mgr.get_current_operation("city-test") is None

    def test_returns_most_recent_when_multiple(self, mgr):
        mgr.create_operation("op-1", "city-test", "fetch")
        mgr.create_operation("op-2", "city-test", "discover")

        # Force distinct started_at so ORDER BY is deterministic
        conn = sqlite3.connect(mgr.db_path)
        conn.execute(
            "UPDATE operations SET started_at = '2025-11-01T10:00:00' WHERE id = 'op-1'"
        )
        conn.execute(
            "UPDATE operations SET started_at = '2025-11-01T11:00:00' WHERE id = 'op-2'"
        )
        conn.commit()
        conn.close()

        current = mgr.get_current_operation("city-test")
        assert current["id"] == "op-2"  # op-2 has the later started_at


class TestCleanupOldOperations:
    def test_deletes_old_completed_operations(self, mgr):
        mgr.create_operation("op-old", "city-test", "fetch")

        # Manually set completed_at to 60 days ago
        conn = sqlite3.connect(mgr.db_path)
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        conn.execute(
            "UPDATE operations SET status='completed', completed_at=? WHERE id='op-old'",
            (old_date,),
        )
        conn.commit()
        conn.close()

        deleted = mgr.cleanup_old_operations(days=30)
        assert deleted == 1
        assert mgr.get_operation("op-old") is None

    def test_preserves_recent_completed(self, mgr):
        mgr.create_operation("op-new", "city-test", "fetch")
        mgr.complete_operation("op-new", result={})

        deleted = mgr.cleanup_old_operations(days=30)
        assert deleted == 0
        assert mgr.get_operation("op-new") is not None

    def test_preserves_pending_operations(self, mgr):
        mgr.create_operation("op-pending", "city-test", "fetch")

        # Even if we set a very short cutoff, pending ops have no completed_at
        deleted = mgr.cleanup_old_operations(days=0)
        assert deleted == 0

    def test_deletes_old_failed_operations(self, mgr):
        mgr.create_operation("op-fail", "city-test", "fetch")

        conn = sqlite3.connect(mgr.db_path)
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        conn.execute(
            "UPDATE operations SET status='failed', completed_at=? WHERE id='op-fail'",
            (old_date,),
        )
        conn.commit()
        conn.close()

        deleted = mgr.cleanup_old_operations(days=30)
        assert deleted == 1

    def test_returns_zero_when_nothing_to_delete(self, mgr):
        deleted = mgr.cleanup_old_operations(days=30)
        assert deleted == 0
