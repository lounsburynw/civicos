"""
Tests for SQLiteBackend implementation of StorageBackend protocol.

Validates that SQLiteBackend correctly implements the StorageBackend protocol
and integrates with the 4-stage pipeline (discover -> ingest -> store -> index).
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from civicos.storage import (
    SQLiteBackend,
    StorageBackend,
    StorageStats,
    StorageValidationResult,
)


@pytest.fixture
def temp_db():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def backend(temp_db):
    """Create a SQLiteBackend instance for testing."""
    return SQLiteBackend(temp_db)


@pytest.fixture
def sample_meetings():
    """Sample meeting data for testing."""
    return [
        {
            "id": "mtg-001",
            "title": "City Council Meeting",
            "meeting_datetime": "2025-12-01T18:00:00",
            "meeting_type": "city_council",
            "status": "scheduled",
            "location": "City Hall",
            "source_platform": "legistar",
        },
        {
            "id": "mtg-002",
            "title": "Planning Commission",
            "meeting_datetime": "2025-12-15T19:00:00",
            "meeting_type": "planning_commission",
            "status": "scheduled",
            "location": "Planning Office",
            "source_platform": "proudcity",
        },
        {
            "id": "mtg-003",
            "title": "Budget Workshop",
            "meeting_datetime": "2025-12-20T14:00:00",
            "meeting_type": "workshop",
            "status": "tentative",
            "source_platform": "manual",
        },
    ]


class TestSQLiteBackendProtocol:
    """Tests for StorageBackend protocol compliance."""

    def test_backend_type_returns_sqlite(self, backend):
        """backend_type should return 'sqlite'."""
        assert backend.backend_type == "sqlite"

    def test_implements_storage_backend_protocol(self, backend):
        """SQLiteBackend should implement StorageBackend protocol."""
        # StorageBackend is @runtime_checkable — use isinstance
        assert isinstance(backend, StorageBackend)
        assert isinstance(backend.backend_type, str)


class TestSQLiteBackendValidation:
    """Tests for validate() method."""

    def test_validate_new_database(self, backend):
        """Validation on new database should pass with warnings."""
        result = backend.validate()
        assert isinstance(result, StorageValidationResult)
        assert result.connected is True
        # Schema doesn't exist yet, but that's a warning not an error
        assert result.is_valid is True

    def test_validate_after_store(self, backend, sample_meetings):
        """Validation after storing data should pass fully."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.validate()
        assert result.is_valid is True
        assert result.connected is True
        assert result.schema_valid is True
        assert len(result.errors) == 0

    def test_validate_includes_duration(self, backend):
        """Validation should track check duration."""
        result = backend.validate()
        assert isinstance(result.check_duration_ms, float)
        assert 0 <= result.check_duration_ms < 5000  # Bounded, not tautological


class TestSQLiteBackendStoreMeetings:
    """Tests for store_meetings() method."""

    def test_store_meetings_returns_count(self, backend, sample_meetings):
        """store_meetings should return count of stored meetings."""
        count = backend.store_meetings("city-test", sample_meetings)
        assert count == 3

    def test_store_meetings_persists_data(self, backend, sample_meetings):
        """Stored meetings should be retrievable."""
        backend.store_meetings("city-test", sample_meetings)
        retrieved = backend.get_meetings("city-test")
        assert len(retrieved) == 3

    def test_store_meetings_with_custom_as_of(self, backend, sample_meetings):
        """store_meetings should accept custom as_of timestamp."""
        as_of = datetime(2025, 11, 1, 12, 0, 0)
        count = backend.store_meetings("city-test", sample_meetings, as_of=as_of)
        assert count == 3

    def test_store_meetings_temporal_versioning(self, backend):
        """Storing meetings twice should create temporal versions."""
        meetings_v1 = [{"id": "mtg-001", "title": "V1", "meeting_datetime": "2025-12-01T18:00:00", "source_platform": "test"}]
        meetings_v2 = [{"id": "mtg-001", "title": "V2", "meeting_datetime": "2025-12-01T18:00:00", "source_platform": "test"}]

        # Store V1
        backend.store_meetings("city-test", meetings_v1)
        result1 = backend.get_meetings("city-test")
        assert len(result1) == 1
        assert result1[0]["title"] == "V1"

        # Store V2 (should replace V1 for current queries)
        backend.store_meetings("city-test", meetings_v2)
        result2 = backend.get_meetings("city-test")
        assert len(result2) == 1
        assert result2[0]["title"] == "V2"

    def test_store_meetings_multiple_jurisdictions(self, backend, sample_meetings):
        """Meetings should be stored separately per jurisdiction."""
        backend.store_meetings("city-a", sample_meetings[:1])
        backend.store_meetings("city-b", sample_meetings[1:])

        meetings_a = backend.get_meetings("city-a")
        meetings_b = backend.get_meetings("city-b")

        assert len(meetings_a) == 1
        assert len(meetings_b) == 2


class TestSQLiteBackendGetMeetings:
    """Tests for get_meetings() method."""

    def test_get_meetings_returns_list(self, backend, sample_meetings):
        """get_meetings should return list of dictionaries with correct content."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.get_meetings("city-test")
        assert len(result) == 3
        ids = {m["id"] for m in result}
        assert ids == {"mtg-001", "mtg-002", "mtg-003"}

    def test_get_meetings_empty_jurisdiction(self, backend):
        """get_meetings for non-existent jurisdiction returns empty list."""
        result = backend.get_meetings("non-existent")
        assert result == []

    def test_get_meetings_with_limit(self, backend, sample_meetings):
        """get_meetings should respect limit parameter."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.get_meetings("city-test", limit=2)
        assert len(result) == 2

    def test_get_meetings_with_since_filter(self, backend, sample_meetings):
        """get_meetings should filter by since datetime."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.get_meetings("city-test", since=datetime(2025, 12, 10))
        # Should only include meetings on or after Dec 10
        assert len(result) == 2

    def test_get_meetings_with_until_filter(self, backend, sample_meetings):
        """get_meetings should filter by until datetime."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.get_meetings("city-test", until=datetime(2025, 12, 10))
        # Should only include meetings on or before Dec 10
        assert len(result) == 1

    def test_get_meetings_ordered_by_datetime(self, backend, sample_meetings):
        """get_meetings should return meetings ordered by datetime."""
        # Store in non-chronological order
        backend.store_meetings("city-test", [sample_meetings[2], sample_meetings[0], sample_meetings[1]])
        result = backend.get_meetings("city-test")

        # Verify chronological order
        datetimes = [m["meeting_datetime"] for m in result]
        assert datetimes == sorted(datetimes)


class TestSQLiteBackendGetStats:
    """Tests for get_stats() method."""

    def test_get_stats_returns_storage_stats(self, backend, sample_meetings):
        """get_stats should return StorageStats with correct jurisdiction."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert isinstance(stats, StorageStats)
        assert stats.jurisdiction_id == "city-test"

    def test_get_stats_meeting_count(self, backend, sample_meetings):
        """get_stats should report correct meeting count."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert stats.meeting_count == 3

    def test_get_stats_date_range(self, backend, sample_meetings):
        """get_stats should report date range matching stored meetings."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        # Sample meetings: Dec 1, Dec 15, Dec 20
        assert stats.earliest_meeting.year == 2025
        assert stats.earliest_meeting.month == 12
        assert stats.earliest_meeting.day == 1
        assert stats.latest_meeting.year == 2025
        assert stats.latest_meeting.month == 12
        assert stats.latest_meeting.day == 20

    def test_get_stats_empty_jurisdiction(self, backend):
        """get_stats for empty jurisdiction should return zero counts."""
        stats = backend.get_stats("non-existent")
        assert stats.meeting_count == 0
        assert stats.agenda_item_count == 0

    def test_get_stats_to_dict(self, backend, sample_meetings):
        """StorageStats.to_dict should serialize properly."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        stats_dict = stats.to_dict()

        assert "jurisdiction_id" in stats_dict
        assert "meeting_count" in stats_dict
        assert stats_dict["meeting_count"] == 3


class TestSQLiteBackendDeleteMeetings:
    """Tests for delete_meetings() method."""

    def test_delete_all_meetings(self, backend, sample_meetings):
        """delete_meetings without IDs should soft-delete all."""
        backend.store_meetings("city-test", sample_meetings)
        deleted = backend.delete_meetings("city-test")
        assert deleted == 3

        # Verify they're no longer visible
        remaining = backend.get_meetings("city-test")
        assert len(remaining) == 0

    def test_delete_specific_meetings(self, backend, sample_meetings):
        """delete_meetings with IDs should only delete specified."""
        backend.store_meetings("city-test", sample_meetings)
        deleted = backend.delete_meetings("city-test", meeting_ids=["mtg-001", "mtg-002"])
        assert deleted == 2

        remaining = backend.get_meetings("city-test")
        assert len(remaining) == 1
        assert remaining[0]["id"] == "mtg-003"

    def test_delete_returns_count(self, backend, sample_meetings):
        """delete_meetings should return count of deleted."""
        backend.store_meetings("city-test", sample_meetings)
        deleted = backend.delete_meetings("city-test", meeting_ids=["mtg-001"])
        assert deleted == 1


class TestSQLiteBackendIntegration:
    """Integration tests for SQLiteBackend."""

    def test_full_workflow(self, backend, sample_meetings):
        """Test complete store-retrieve-delete workflow."""
        # Store
        stored = backend.store_meetings("city-test", sample_meetings)
        assert stored == 3

        # Validate
        validation = backend.validate()
        assert validation.is_valid

        # Retrieve
        meetings = backend.get_meetings("city-test")
        assert len(meetings) == 3

        # Stats
        stats = backend.get_stats("city-test")
        assert stats.meeting_count == 3

        # Delete one
        backend.delete_meetings("city-test", meeting_ids=["mtg-001"])
        remaining = backend.get_meetings("city-test")
        assert len(remaining) == 2

        # Stats update
        stats = backend.get_stats("city-test")
        assert stats.meeting_count == 2


class TestSQLiteBackendOperations:
    """Tests for operation tracking methods."""

    def test_create_operation(self, backend):
        """create_operation should create pending operation."""
        # Need to initialize schema first
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])

        result = backend.create_operation("op-123", "city-test", "fetch_meetings")

        assert result["id"] == "op-123"
        assert result["jurisdiction_id"] == "city-test"
        assert result["name"] == "fetch_meetings"
        assert result["status"] == "pending"
        assert result["progress_percent"] == 0
        assert result["items_processed"] == 0
        assert result["items_total"] == 0
        assert "started_at" in result

    def test_get_operation(self, backend):
        """get_operation should retrieve operation by ID."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-456", "city-test", "discover_videos")

        op = backend.get_operation("op-456")

        assert op is not None
        assert op["id"] == "op-456"
        assert op["name"] == "discover_videos"
        assert op["status"] == "pending"

    def test_get_operation_not_found(self, backend):
        """get_operation should return None for non-existent ID."""
        op = backend.get_operation("non-existent")
        assert op is None

    def test_update_operation_status(self, backend):
        """update_operation_status should update operation fields."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-789", "city-test", "fetch_meetings")

        updated = backend.update_operation_status(
            "op-789",
            status="running",
            current_step="Fetching page 2",
            progress_percent=50.0,
            items_processed=10,
            items_total=20
        )

        assert updated is True

        op = backend.get_operation("op-789")
        assert op["status"] == "running"
        assert op["current_step"] == "Fetching page 2"
        assert op["progress_percent"] == 50.0
        assert op["items_processed"] == 10
        assert op["items_total"] == 20

    def test_update_operation_status_partial(self, backend):
        """update_operation_status with partial updates."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-partial", "city-test", "fetch_meetings")

        # Only update status
        updated = backend.update_operation_status("op-partial", status="running")
        assert updated is True

        op = backend.get_operation("op-partial")
        assert op["status"] == "running"
        assert op["current_step"] is None

    def test_update_operation_status_not_found(self, backend):
        """update_operation_status should return False for non-existent ID."""
        updated = backend.update_operation_status("non-existent", status="running")
        assert updated is False

    def test_complete_operation_success(self, backend):
        """complete_operation should mark as completed with result."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-success", "city-test", "fetch_meetings")

        result_data = {"meetings_fetched": 5, "errors": []}
        completed = backend.complete_operation("op-success", result=result_data)

        assert completed is True

        op = backend.get_operation("op-success")
        assert op["status"] == "completed"
        assert op["progress_percent"] == 100
        assert op["result"] == result_data
        assert op["error"] is None
        assert op["duration_seconds"] is not None
        assert op["completed_at"] is not None

    def test_complete_operation_failure(self, backend):
        """complete_operation with error should mark as failed."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-failure", "city-test", "fetch_meetings")

        result_data = {"meetings_fetched": 0}
        completed = backend.complete_operation(
            "op-failure",
            result=result_data,
            error="Connection timeout"
        )

        assert completed is True

        op = backend.get_operation("op-failure")
        assert op["status"] == "failed"
        assert op["error"] == "Connection timeout"
        assert op["result"] == result_data

    def test_get_operations_all(self, backend):
        """get_operations should return all operations."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-1", "city-test", "fetch_meetings")
        backend.create_operation("op-2", "city-test", "discover_videos")
        backend.create_operation("op-3", "city-test", "extract_text")

        ops = backend.get_operations()

        assert len(ops) == 3
        # Most recent first
        assert ops[0]["id"] == "op-3"
        assert ops[1]["id"] == "op-2"
        assert ops[2]["id"] == "op-1"

    def test_get_operations_by_jurisdiction(self, backend):
        """get_operations should filter by jurisdiction."""
        backend.store_meetings("city-a", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.store_meetings("city-b", [{"id": "m2", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])

        backend.create_operation("op-a1", "city-a", "fetch_meetings")
        backend.create_operation("op-b1", "city-b", "fetch_meetings")
        backend.create_operation("op-a2", "city-a", "discover_videos")

        ops = backend.get_operations(jurisdiction_id="city-a")

        assert len(ops) == 2
        assert all(op["jurisdiction_id"] == "city-a" for op in ops)

    def test_get_operations_by_status(self, backend):
        """get_operations should filter by status."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        backend.create_operation("op-pending", "city-test", "fetch_meetings")
        backend.create_operation("op-running", "city-test", "discover_videos")
        backend.update_operation_status("op-running", status="running")

        ops = backend.get_operations(status="running")

        assert len(ops) == 1
        assert ops[0]["id"] == "op-running"

    def test_get_operations_with_limit(self, backend):
        """get_operations should respect limit."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])
        for i in range(5):
            backend.create_operation(f"op-{i}", "city-test", "fetch_meetings")

        ops = backend.get_operations(limit=3)

        assert len(ops) == 3

    def test_operations_workflow(self, backend):
        """Test complete operation lifecycle."""
        backend.store_meetings("city-test", [{"id": "m1", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}])

        # Create
        op = backend.create_operation("op-wf", "city-test", "fetch_meetings")
        assert op["status"] == "pending"

        # Start running
        backend.update_operation_status(
            "op-wf",
            status="running",
            items_total=10
        )
        op = backend.get_operation("op-wf")
        assert op["status"] == "running"

        # Progress updates
        backend.update_operation_status(
            "op-wf",
            status="running",
            progress_percent=50,
            items_processed=5
        )
        op = backend.get_operation("op-wf")
        assert op["progress_percent"] == 50

        # Complete
        backend.complete_operation("op-wf", result={"count": 10})
        op = backend.get_operation("op-wf")
        assert op["status"] == "completed"
        assert op["progress_percent"] == 100


class TestPagination:
    """Tests for limit/offset pagination on get_*() methods."""

    @pytest.fixture
    def backend_with_meetings(self, backend):
        """Backend with 10 meetings for pagination testing."""
        meetings = [
            {
                "id": f"mtg-{i:03d}",
                "title": f"Meeting {i}",
                "meeting_datetime": f"2025-12-{i:02d}T18:00:00",
                "meeting_type": "city_council",
                "status": "scheduled",
                "source_platform": "test",
            }
            for i in range(1, 11)
        ]
        backend.store_meetings("city-test", meetings)
        return backend

    def test_limit_returns_exact_count(self, backend_with_meetings):
        """limit=5 should return exactly 5 results."""
        results = backend_with_meetings.get_meetings("city-test", limit=5)
        assert len(results) == 5

    def test_limit_none_returns_all(self, backend_with_meetings):
        """limit=None should return all results (backward compat)."""
        results = backend_with_meetings.get_meetings("city-test", limit=None)
        assert len(results) == 10

    def test_offset_skips_results(self, backend_with_meetings):
        """offset=5 with limit=5 should return the second page."""
        page1 = backend_with_meetings.get_meetings("city-test", limit=5, offset=0)
        page2 = backend_with_meetings.get_meetings("city-test", limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        # Pages should not overlap
        page1_ids = {m["id"] for m in page1}
        page2_ids = {m["id"] for m in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_offset_beyond_results_returns_empty(self, backend_with_meetings):
        """offset beyond result count should return empty list."""
        results = backend_with_meetings.get_meetings("city-test", limit=5, offset=100)
        assert results == []

    def test_offset_zero_is_default(self, backend_with_meetings):
        """offset=0 should behave same as no offset."""
        with_offset = backend_with_meetings.get_meetings("city-test", limit=5, offset=0)
        without_offset = backend_with_meetings.get_meetings("city-test", limit=5)
        assert len(with_offset) == len(without_offset)
        assert [m["id"] for m in with_offset] == [m["id"] for m in without_offset]

    def test_pagination_covers_all_results(self, backend_with_meetings):
        """Paginating through all results should cover every item."""
        all_ids = set()
        offset = 0
        page_size = 3
        while True:
            page = backend_with_meetings.get_meetings(
                "city-test", limit=page_size, offset=offset
            )
            if not page:
                break
            all_ids.update(m["id"] for m in page)
            offset += page_size
        assert len(all_ids) == 10

    def test_decisions_pagination(self, backend):
        """Pagination works on get_decisions()."""
        decisions = [
            {
                "id": f"dec-{i:03d}",
                "title": f"Decision {i}",
                "meeting_date": f"2025-12-{i:02d}",
                "agenda_item": f"item-{i}",
                "outcome": "approved",
            }
            for i in range(1, 6)
        ]
        backend.store_decisions("city-test", decisions)
        page1 = backend.get_decisions("city-test", limit=2, offset=0)
        page2 = backend.get_decisions("city-test", limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]

    def test_operations_pagination(self, backend):
        """Pagination works on get_operations()."""
        # Create multiple operations
        for i in range(5):
            backend.store_meetings("city-test", [
                {"id": f"m-{i}", "title": "T", "meeting_datetime": "2025-01-01", "source_platform": "test"}
            ])
            backend.create_operation(f"op-{i}", "city-test", "test_op")
        page1 = backend.get_operations(limit=2, offset=0)
        page2 = backend.get_operations(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]


# ========== Store/Get Methods — Mutation Kill Targets ==========


class TestStoreDecisions:
    """Tests for store_decisions + get_decisions + get_decision_count."""

    @pytest.fixture
    def sample_decisions(self):
        return [
            {
                "id": "dec-001",
                "title": "Approve Housing Element",
                "meeting_date": "2025-12-01",
                "agenda_item": "item-6a",
                "outcome": "approved",
                "vote_summary": "5-0",
                "topic": "housing",
            },
            {
                "id": "dec-002",
                "title": "Deny Variance Request",
                "meeting_date": "2025-12-01",
                "agenda_item": "item-7b",
                "outcome": "denied",
                "vote_summary": "3-2",
                "topic": "zoning",
            },
        ]

    def test_store_returns_count(self, backend, sample_decisions):
        count = backend.store_decisions("city-test", sample_decisions)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_decisions):
        backend.store_decisions("city-test", sample_decisions)
        results = backend.get_decisions("city-test")
        assert len(results) == 2
        titles = [d["title"] for d in results]
        assert "Approve Housing Element" in titles
        assert "Deny Variance Request" in titles

    def test_decision_fields_preserved(self, backend, sample_decisions):
        backend.store_decisions("city-test", sample_decisions)
        results = backend.get_decisions("city-test")
        # ID is auto-generated as decision:{jurisdiction}:{date}:{item}
        dec = next(d for d in results if d["agenda_item"] == "item-6a")
        assert dec["outcome"] == "approved"
        assert dec["title"] == "Approve Housing Element"
        assert dec["meeting_date"] == "2025-12-01"

    def test_get_decision_count(self, backend, sample_decisions):
        assert backend.get_decision_count("city-test") == 0
        backend.store_decisions("city-test", sample_decisions)
        assert backend.get_decision_count("city-test") == 2

    def test_upsert_updates_existing(self, backend, sample_decisions):
        backend.store_decisions("city-test", sample_decisions)
        # Re-store with updated title — same meeting_date + agenda_item = same auto-ID
        updated = [{"title": "Updated Title", "meeting_date": "2025-12-01",
                     "agenda_item": "item-6a", "outcome": "approved"}]
        backend.store_decisions("city-test", updated)
        results = backend.get_decisions("city-test")
        dec = next(d for d in results if d["agenda_item"] == "item-6a")
        assert dec["title"] == "Updated Title"

    def test_jurisdiction_isolation(self, backend, sample_decisions):
        backend.store_decisions("city-a", sample_decisions)
        backend.store_decisions("city-b", [sample_decisions[0]])
        assert len(backend.get_decisions("city-a")) == 2
        assert len(backend.get_decisions("city-b")) == 1
        assert backend.get_decision_count("city-a") == 2

    def test_empty_list_stores_nothing(self, backend):
        count = backend.store_decisions("city-test", [])
        assert count == 0
        assert backend.get_decision_count("city-test") == 0


class TestStoreIssues:
    """Tests for store_issues + get_issues + get_issue_count."""

    @pytest.fixture
    def sample_issues(self):
        return [
            {
                "id": "issue-001",
                "title": "Pothole on 4th Street",
                "issue_type": "Pothole",
                "address": "123 4th St",
                "status": "open",
                "provider": "seeclickfix",
                "external_id": "scf-12345",
                "created_at": "2025-11-15T10:00:00",
            },
            {
                "id": "issue-002",
                "title": "Graffiti on bridge",
                "issue_type": "Graffiti",
                "address": "Main St Bridge",
                "status": "closed",
                "provider": "seeclickfix",
                "external_id": "scf-12346",
                "created_at": "2025-11-10T09:00:00",
            },
        ]

    def test_store_returns_count(self, backend, sample_issues):
        count = backend.store_issues("city-test", sample_issues)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_issues):
        backend.store_issues("city-test", sample_issues)
        results = backend.get_issues("city-test")
        assert len(results) == 2

    def test_issue_fields_preserved(self, backend, sample_issues):
        backend.store_issues("city-test", sample_issues)
        results = backend.get_issues("city-test")
        pothole = next(i for i in results if i.get("title") == "Pothole on 4th Street"
                       or i.get("id") == "issue-001")
        assert pothole["issue_type"] == "Pothole"
        assert pothole["status"] == "open"

    def test_get_issue_count(self, backend, sample_issues):
        assert backend.get_issue_count("city-test") == 0
        backend.store_issues("city-test", sample_issues)
        assert backend.get_issue_count("city-test") == 2

    def test_jurisdiction_isolation(self, backend, sample_issues):
        backend.store_issues("city-a", sample_issues)
        backend.store_issues("city-b", [sample_issues[0]])
        assert backend.get_issue_count("city-a") == 2
        assert backend.get_issue_count("city-b") == 1

    def test_upsert_by_external_id(self, backend, sample_issues):
        backend.store_issues("city-test", sample_issues)
        updated = [{
            "id": "issue-001-updated",
            "title": "Pothole FIXED",
            "status": "closed",
            "provider": "seeclickfix",
            "external_id": "scf-12345",
        }]
        backend.store_issues("city-test", updated)
        # Count should not increase — upsert on external_id
        assert backend.get_issue_count("city-test") == 2


class TestStoreAgendaItems:
    """Tests for store_agenda_items + get_agenda_items + get_agenda_item_count."""

    @pytest.fixture
    def sample_items(self):
        return [
            {
                "id": "ai-001",
                "item_number": "6.a",
                "title": "Housing Element Update",
                "description": "Review and approve housing element amendments",
                "project_type": "housing",
            },
            {
                "id": "ai-002",
                "item_number": "7.b",
                "title": "Budget Amendment",
                "description": "FY26 mid-year budget adjustment",
                "project_type": "budget",
            },
        ]

    def test_store_returns_count(self, backend, sample_items):
        # First need a meeting to attach items to
        backend.store_meetings("city-test", [{
            "id": "mtg-001", "title": "Council", "meeting_datetime": "2025-12-01",
            "source_platform": "test",
        }])
        count = backend.store_agenda_items("mtg-001", sample_items)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_items):
        backend.store_meetings("city-test", [{
            "id": "mtg-001", "title": "Council", "meeting_datetime": "2025-12-01",
            "source_platform": "test",
        }])
        backend.store_agenda_items("mtg-001", sample_items)
        results = backend.get_agenda_items("mtg-001")
        assert len(results) == 2

    def test_item_fields_preserved(self, backend, sample_items):
        backend.store_meetings("city-test", [{
            "id": "mtg-001", "title": "Council", "meeting_datetime": "2025-12-01",
            "source_platform": "test",
        }])
        backend.store_agenda_items("mtg-001", sample_items)
        results = backend.get_agenda_items("mtg-001")
        housing = next(i for i in results if i.get("id") == "ai-001")
        assert housing["title"] == "Housing Element Update"
        assert housing["item_number"] == "6.a"
        assert housing["project_type"] == "housing"

    def test_get_agenda_item_count(self, backend, sample_items):
        backend.store_meetings("city-test", [{
            "id": "mtg-001", "title": "Council", "meeting_datetime": "2025-12-01",
            "source_platform": "test",
        }])
        backend.store_agenda_items("mtg-001", sample_items)
        assert backend.get_agenda_item_count("city-test") == 2


class TestStoreChunks:
    """Tests for store_chunks + get_chunks + get_chunk_count."""

    @pytest.fixture
    def sample_chunks(self):
        return [
            {
                "meeting_id": "mtg-001",
                "agenda_item": "6.a",
                "agenda_title": "Housing Element",
                "text": "The city council discussed the housing element update.",
                "page_start": 5,
                "page_end": 8,
                "chunk_index": 0,
                "total_chunks": 2,
                "source_file": "packet.pdf",
                "source_type": "agenda_packet",
            },
            {
                "meeting_id": "mtg-001",
                "agenda_item": "7.b",
                "agenda_title": "Budget",
                "text": "Budget allocation for infrastructure improvements.",
                "page_start": 12,
                "page_end": 15,
                "chunk_index": 0,
                "total_chunks": 1,
                "source_file": "packet.pdf",
                "source_type": "agenda_packet",
            },
        ]

    def test_store_returns_count(self, backend, sample_chunks):
        count = backend.store_chunks("city-test", sample_chunks)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_chunks):
        backend.store_chunks("city-test", sample_chunks)
        results = backend.get_chunks("city-test")
        assert len(results) == 2

    def test_chunk_text_preserved(self, backend, sample_chunks):
        backend.store_chunks("city-test", sample_chunks)
        results = backend.get_chunks("city-test")
        texts = [c["text"] for c in results]
        assert any("housing element" in t for t in texts)
        assert any("infrastructure" in t for t in texts)

    def test_chunk_metadata_preserved(self, backend, sample_chunks):
        backend.store_chunks("city-test", sample_chunks)
        results = backend.get_chunks("city-test")
        chunk = next(c for c in results if "housing" in c["text"])
        assert chunk["agenda_item"] == "6.a"
        assert chunk["agenda_title"] == "Housing Element"
        assert chunk["page_start"] == 5

    def test_get_chunk_count(self, backend, sample_chunks):
        assert backend.get_chunk_count("city-test") == 0
        backend.store_chunks("city-test", sample_chunks)
        assert backend.get_chunk_count("city-test") == 2

    def test_jurisdiction_isolation(self, backend, sample_chunks):
        backend.store_chunks("city-a", sample_chunks)
        backend.store_chunks("city-b", [sample_chunks[0]])
        assert backend.get_chunk_count("city-a") == 2
        assert backend.get_chunk_count("city-b") == 1


class TestStubMethods:
    """Verify stub methods return 0 (Postgres-only features)."""

    def test_store_municipal_code_is_stub(self, backend):
        result = backend.store_municipal_code("city-test", [{"id": "mc-1"}])
        assert result == 0

    def test_store_videos_is_stub(self, backend):
        result = backend.store_videos("city-test", [{"id": "v-1"}])
        assert result == 0

    def test_store_transcripts_is_stub(self, backend):
        result = backend.store_transcripts("city-test", [{"id": "t-1"}])
        assert result == 0


class TestStoreElections:
    """Tests for store_elections + get_elections."""

    @pytest.fixture
    def sample_elections(self):
        return [
            {
                "id": "election-2026-general",
                "name": "2026 General Election",
                "election_date": "2026-11-03",
                "election_type": "general",
                "source": "registrar",
            },
            {
                "id": "election-2026-primary",
                "name": "2026 Primary Election",
                "election_date": "2026-06-02",
                "election_type": "primary",
                "source": "registrar",
            },
        ]

    def test_store_returns_count(self, backend, sample_elections):
        count = backend.store_elections("city-test", sample_elections)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_elections):
        backend.store_elections("city-test", sample_elections)
        results = backend.get_elections("city-test", include_past=True)
        assert len(results) == 2

    def test_election_fields_preserved(self, backend, sample_elections):
        backend.store_elections("city-test", sample_elections)
        results = backend.get_elections("city-test", include_past=True)
        general = next(e for e in results if e["election_type"] == "general")
        assert general["name"] == "2026 General Election"
        assert general["election_date"] == "2026-11-03"
        assert general["source"] == "registrar"

    def test_filter_by_election_type(self, backend, sample_elections):
        backend.store_elections("city-test", sample_elections)
        primaries = backend.get_elections("city-test", election_type="primary", include_past=True)
        assert len(primaries) == 1
        assert primaries[0]["election_type"] == "primary"

    def test_jurisdiction_isolation(self, backend, sample_elections):
        backend.store_elections("city-a", sample_elections)
        backend.store_elections("city-b", [sample_elections[0]])
        assert len(backend.get_elections("city-a", include_past=True)) == 2
        assert len(backend.get_elections("city-b", include_past=True)) == 1

    def test_empty_list(self, backend):
        count = backend.store_elections("city-test", [])
        assert count == 0


class TestStoreElectionContests:
    """Tests for store_election_contests."""

    def test_store_returns_count(self, backend):
        backend.store_elections("city-test", [{
            "id": "election-2026",
            "name": "2026 General",
            "election_date": "2026-11-03",
            "election_type": "general",
        }])
        contests = [
            {
                "id": "contest-house-2",
                "office_type": "us_house",
                "contest_type": "federal_house",
                "title": "US House District 2",
                "district": 2,
            },
            {
                "id": "contest-governor",
                "office_type": "state_governor",
                "contest_type": "state_governor",
                "title": "Governor",
            },
        ]
        count = backend.store_election_contests("election-2026", contests)
        assert count == 2


class TestStoreElectedOfficials:
    """Tests for store_elected_officials + get_elected_officials + get_official_by_name."""

    @pytest.fixture
    def sample_officials(self):
        return [
            {
                "id": "official-001",
                "name": "Kate Colin",
                "seat": "Mayor",
                "term_start": "2023-01-01",
                "term_end": "2026-12-31",
                "name_variations": '["Kate Colin", "K. Colin"]',
            },
            {
                "id": "official-002",
                "name": "Maribeth Bushey",
                "seat": "Council Member",
                "term_start": "2023-01-01",
                "term_end": "2026-12-31",
            },
        ]

    def test_store_returns_count(self, backend, sample_officials):
        count = backend.store_elected_officials("city-test", sample_officials)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_officials):
        backend.store_elected_officials("city-test", sample_officials)
        results = backend.get_elected_officials("city-test", current_only=False)
        assert len(results) == 2

    def test_official_fields_preserved(self, backend, sample_officials):
        backend.store_elected_officials("city-test", sample_officials)
        results = backend.get_elected_officials("city-test", current_only=False)
        mayor = next(o for o in results if o["seat"] == "Mayor")
        assert mayor["name"] == "Kate Colin"
        assert mayor["term_start"] == "2023-01-01"

    def test_get_official_by_name(self, backend, sample_officials):
        backend.store_elected_officials("city-test", sample_officials)
        result = backend.get_official_by_name("city-test", "Kate Colin")
        assert result is not None
        assert result["seat"] == "Mayor"

    def test_get_official_by_name_not_found(self, backend, sample_officials):
        backend.store_elected_officials("city-test", sample_officials)
        result = backend.get_official_by_name("city-test", "Nonexistent Person")
        assert result is None

    def test_jurisdiction_isolation(self, backend, sample_officials):
        backend.store_elected_officials("city-a", sample_officials)
        # current_only=True filters by term_end IS NULL, so use current_only=False
        assert len(backend.get_elected_officials("city-a", current_only=False)) == 2
        assert len(backend.get_elected_officials("city-b", current_only=False)) == 0

    def test_current_only_filters_by_term_end(self, backend):
        officials = [
            {"id": "o-current", "name": "Current Official", "seat": "Mayor", "term_start": "2023-01-01"},
            {"id": "o-past", "name": "Past Official", "seat": "Mayor", "term_start": "2020-01-01", "term_end": "2024-12-31"},
        ]
        backend.store_elected_officials("city-test", officials)
        current = backend.get_elected_officials("city-test", current_only=True)
        all_officials = backend.get_elected_officials("city-test", current_only=False)
        assert len(current) == 1
        assert current[0]["name"] == "Current Official"
        assert len(all_officials) == 2


class TestStoreFederalAwards:
    """Tests for store_federal_awards + get_federal_awards."""

    @pytest.fixture
    def sample_awards(self):
        return [
            {
                "award_id": "award-001",
                "cfda_number": "14.218",
                "recipient_name": "City of San Rafael",
                "recipient_uei": "UEI123",
                "amount_cents": 500_000_00,
                "period_start": "2025-07-01",
                "period_end": "2026-06-30",
                "program_name": "CDBG",
                "awarding_agency": "HUD",
                "funding_agency": "HUD",
                "award_type": "grant",
            },
            {
                "award_id": "award-002",
                "cfda_number": "20.205",
                "recipient_name": "City of San Rafael",
                "amount_cents": 200_000_00,
                "period_start": "2025-10-01",
                "period_end": "2026-09-30",
                "program_name": "Highway Planning",
                "awarding_agency": "DOT",
                "award_type": "grant",
            },
        ]

    def test_store_returns_count(self, backend, sample_awards):
        count = backend.store_federal_awards("city-test", sample_awards)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_awards):
        backend.store_federal_awards("city-test", sample_awards)
        results = backend.get_federal_awards("city-test")
        assert len(results) == 2

    def test_award_fields_preserved(self, backend, sample_awards):
        backend.store_federal_awards("city-test", sample_awards)
        results = backend.get_federal_awards("city-test")
        cdbg = next(a for a in results if a["cfda_number"] == "14.218")
        assert cdbg["program_name"] == "CDBG"
        assert cdbg["amount_cents"] == 500_000_00
        assert cdbg["awarding_agency"] == "HUD"

    def test_filter_by_cfda_number(self, backend, sample_awards):
        backend.store_federal_awards("city-test", sample_awards)
        results = backend.get_federal_awards("city-test", cfda_number="14.218")
        assert len(results) == 1
        assert results[0]["program_name"] == "CDBG"

    def test_jurisdiction_isolation(self, backend, sample_awards):
        backend.store_federal_awards("city-a", sample_awards)
        assert len(backend.get_federal_awards("city-a")) == 2
        assert len(backend.get_federal_awards("city-b")) == 0

    def test_empty_list(self, backend):
        count = backend.store_federal_awards("city-test", [])
        assert count == 0


class TestStoreBudgetFundingLinks:
    """Tests for store_budget_funding_links + get_budget_funding_links."""

    @pytest.fixture
    def sample_links(self):
        return [
            {
                "link_id": "link-001",
                "budget_item_id": "budget-housing",
                "federal_cfda_number": "14.218",
                "fiscal_year": "FY2026",
                "match_type": "confirmed",
                "confidence": 0.95,
                "budget_amount_cents": 500_000_00,
                "federal_amount_cents": 450_000_00,
            },
            {
                "link_id": "link-002",
                "budget_item_id": "budget-transport",
                "federal_cfda_number": "20.205",
                "fiscal_year": "FY2026",
                "match_type": "inferred",
                "confidence": 0.7,
            },
        ]

    def test_store_returns_count(self, backend, sample_links):
        count = backend.store_budget_funding_links("city-test", sample_links)
        assert count == 2

    def test_store_and_retrieve(self, backend, sample_links):
        backend.store_budget_funding_links("city-test", sample_links)
        results = backend.get_budget_funding_links("city-test")
        assert len(results) == 2

    def test_link_fields_preserved(self, backend, sample_links):
        backend.store_budget_funding_links("city-test", sample_links)
        results = backend.get_budget_funding_links("city-test")
        confirmed = next(l for l in results if l.get("match_type") == "confirmed")
        assert confirmed["federal_cfda_number"] == "14.218"
        assert confirmed["budget_item_id"] == "budget-housing"
        assert confirmed["link_id"] == "link-001"

    def test_filter_by_cfda(self, backend, sample_links):
        backend.store_budget_funding_links("city-test", sample_links)
        results = backend.get_budget_funding_links("city-test", federal_cfda_number="14.218")
        assert len(results) == 1

    def test_filter_confirmed_only(self, backend, sample_links):
        backend.store_budget_funding_links("city-test", sample_links)
        results = backend.get_budget_funding_links("city-test", confirmed_only=True)
        assert all(r.get("match_type") == "confirmed" for r in results)


class TestStoreStatePassthroughFunds:
    """Tests for store_state_passthrough_funds + get_state_passthrough_funds."""

    @pytest.fixture
    def sample_passthroughs(self):
        return [
            {
                "passthrough_id": "pt-001",
                "state_agency": "Caltrans",
                "federal_cfda_number": "20.205",
                "federal_award_id": "award-002",
                "amount_cents": 150_000_00,
                "federal_fiscal_year": 2026,
                "program_name": "Highway Planning (State Pass-Through)",
            },
        ]

    def test_store_returns_count(self, backend, sample_passthroughs):
        count = backend.store_state_passthrough_funds("city-test", sample_passthroughs)
        assert count == 1

    def test_store_and_retrieve(self, backend, sample_passthroughs):
        backend.store_state_passthrough_funds("city-test", sample_passthroughs)
        results = backend.get_state_passthrough_funds("city-test")
        assert len(results) == 1

    def test_fields_preserved(self, backend, sample_passthroughs):
        backend.store_state_passthrough_funds("city-test", sample_passthroughs)
        results = backend.get_state_passthrough_funds("city-test")
        assert results[0]["state_agency"] == "Caltrans"
        assert results[0]["federal_cfda_number"] == "20.205"
        assert results[0]["passthrough_id"] == "pt-001"

    def test_filter_by_state_agency(self, backend, sample_passthroughs):
        backend.store_state_passthrough_funds("city-test", sample_passthroughs)
        results = backend.get_state_passthrough_funds("city-test", state_agency="Caltrans")
        assert len(results) == 1
        results = backend.get_state_passthrough_funds("city-test", state_agency="Nonexistent")
        assert len(results) == 0


class TestUpdateMeeting:
    """Tests for update_meeting."""

    def test_update_returns_true(self, backend, sample_meetings):
        backend.store_meetings("city-test", sample_meetings)
        result = backend.update_meeting("city-test", "mtg-001", {"status": "completed"})
        assert result is True

    def test_update_changes_field(self, backend, sample_meetings):
        backend.store_meetings("city-test", sample_meetings)
        backend.update_meeting("city-test", "mtg-001", {"status": "completed"})
        meetings = backend.get_meetings("city-test")
        updated = next(m for m in meetings if m["id"] == "mtg-001")
        assert updated["status"] == "completed"

    def test_update_nonexistent_returns_false(self, backend, sample_meetings):
        # Store something first to ensure schema exists
        backend.store_meetings("city-test", sample_meetings)
        result = backend.update_meeting("city-test", "nonexistent-id", {"status": "x"})
        assert result is False

    def test_update_preserves_other_fields(self, backend, sample_meetings):
        backend.store_meetings("city-test", sample_meetings)
        backend.update_meeting("city-test", "mtg-001", {"status": "completed"})
        meetings = backend.get_meetings("city-test")
        updated = next(m for m in meetings if m["id"] == "mtg-001")
        assert updated["title"] == "City Council Meeting"  # Unchanged
        assert updated["status"] == "completed"  # Changed


# ========== Field-Level Round-Trip Assertions ==========
# Kill mutants that alter individual column values in INSERT statements


class TestMeetingFieldRoundTrip:
    """Assert every field survives store → get round-trip."""

    def test_all_meeting_fields(self, backend):
        meeting = {
            "id": "mtg-full",
            "title": "Full Field Test Meeting",
            "meeting_datetime": "2025-12-01T18:30:00",
            "meeting_type": "city_council",
            "status": "completed",
            "location": "City Hall, 1400 Fifth Ave",
            "source_platform": "legistar",
            "source_url": "https://legistar.example.com/mtg/123",
            "video_url": "https://youtube.com/watch?v=abc",
            "agenda_url": "https://example.com/agenda.pdf",
            "minutes_url": "https://example.com/minutes.pdf",
        }
        backend.store_meetings("city-test", [meeting])
        results = backend.get_meetings("city-test")
        assert len(results) == 1
        m = results[0]
        assert m["id"] == "mtg-full"
        assert m["title"] == "Full Field Test Meeting"
        assert m["meeting_datetime"] == "2025-12-01T18:30:00"
        assert m["meeting_type"] == "city_council"
        assert m["status"] == "completed"
        assert m["location"] == "City Hall, 1400 Fifth Ave"
        assert m["source_platform"] == "legistar"

    def test_meeting_valid_from_set(self, backend, sample_meetings):
        as_of = datetime(2025, 11, 15, 12, 0, 0)
        backend.store_meetings("city-test", sample_meetings, as_of=as_of)
        results = backend.get_meetings("city-test")
        for m in results:
            assert m.get("valid_from") == "2025-11-15T12:00:00"

    def test_meeting_valid_to_null_for_current(self, backend, sample_meetings):
        backend.store_meetings("city-test", sample_meetings)
        results = backend.get_meetings("city-test")
        for m in results:
            assert m.get("valid_to") is None


class TestDecisionFieldRoundTrip:
    """Assert decision fields survive store → get round-trip."""

    def test_all_decision_fields(self, backend):
        decision = {
            "title": "Approve Zoning Amendment ZA-2025-001",
            "meeting_date": "2025-12-01",
            "agenda_item": "item-8a",
            "outcome": "approved",
            "vote_summary": "4-1",
            "summary": "Council approved the zoning amendment for mixed-use.",
        }
        backend.store_decisions("city-test", [decision])
        results = backend.get_decisions("city-test")
        assert len(results) == 1
        d = results[0]
        assert d["title"] == "Approve Zoning Amendment ZA-2025-001"
        assert d["meeting_date"] == "2025-12-01"
        assert d["agenda_item"] == "item-8a"
        assert d["outcome"] == "approved"

    def test_decision_valid_from_set(self, backend):
        as_of = datetime(2025, 11, 15, 12, 0, 0)
        backend.store_decisions("city-test", [{
            "title": "Test", "meeting_date": "2025-12-01", "agenda_item": "item-1",
        }], as_of=as_of)
        results = backend.get_decisions("city-test")
        assert results[0]["valid_from"] == "2025-11-15T12:00:00"

    def test_decisions_multiple_in_batch(self, backend):
        decisions = [
            {"title": f"Decision {i}", "meeting_date": "2025-12-01",
             "agenda_item": f"item-{i}", "outcome": "approved"}
            for i in range(5)
        ]
        count = backend.store_decisions("city-test", decisions)
        assert count == 5
        results = backend.get_decisions("city-test")
        assert len(results) == 5
        titles = {d["title"] for d in results}
        assert titles == {f"Decision {i}" for i in range(5)}


class TestIssueFieldRoundTrip:
    """Assert issue fields survive store → get round-trip."""

    def test_all_issue_fields(self, backend):
        issue = {
            "id": "issue-full",
            "title": "Broken sidewalk near school",
            "issue_type": "Sidewalk",
            "address": "456 Oak Ave",
            "status": "acknowledged",
            "provider": "seeclickfix",
            "external_id": "scf-99999",
            "latitude": 37.97,
            "longitude": -122.53,
            "created_at": "2025-11-20T14:30:00",
        }
        backend.store_issues("city-test", [issue])
        results = backend.get_issues("city-test")
        assert len(results) == 1
        i = results[0]
        assert i["title"] == "Broken sidewalk near school"
        assert i["issue_type"] == "Sidewalk"
        assert i["address"] == "456 Oak Ave"
        assert i["status"] == "acknowledged"
        assert i["external_id"] == "scf-99999"

    def test_issue_provider_count_filter(self, backend):
        issues = [
            {"id": "i1", "title": "A", "provider": "seeclickfix", "external_id": "e1"},
            {"id": "i2", "title": "B", "provider": "native", "external_id": "e2"},
        ]
        backend.store_issues("city-test", issues)
        total = backend.get_issue_count("city-test")
        scf = backend.get_issue_count("city-test", provider="seeclickfix")
        assert total == 2
        assert scf == 1


class TestAgendaItemFieldRoundTrip:
    """Assert agenda item fields survive store → get round-trip."""

    def test_all_agenda_item_fields(self, backend):
        backend.store_meetings("city-test", [{
            "id": "mtg-x", "title": "Test", "meeting_datetime": "2025-12-01",
            "source_platform": "test",
        }])
        items = [{
            "id": "ai-full",
            "item_number": "9.c",
            "title": "Wildfire Preparedness Plan",
            "description": "Review and adopt the updated wildfire preparedness plan",
            "project_type": "public_safety",
            "actionability": "high",
            "impact_level": "significant",
        }]
        backend.store_agenda_items("mtg-x", items)
        results = backend.get_agenda_items("mtg-x")
        assert len(results) == 1
        a = results[0]
        assert a["title"] == "Wildfire Preparedness Plan"
        assert a["item_number"] == "9.c"
        assert a["project_type"] == "public_safety"

    def test_agenda_items_multiple_per_meeting(self, backend):
        backend.store_meetings("city-test", [{
            "id": "mtg-x", "title": "Test", "meeting_datetime": "2025-12-01",
            "source_platform": "test",
        }])
        items = [
            {"id": f"ai-{i}", "item_number": f"{i}.a", "title": f"Item {i}"}
            for i in range(10)
        ]
        count = backend.store_agenda_items("mtg-x", items)
        assert count == 10
        results = backend.get_agenda_items("mtg-x")
        assert len(results) == 10


class TestChunkFieldRoundTrip:
    """Assert chunk fields survive store → get round-trip."""

    def test_all_chunk_fields(self, backend):
        chunks = [{
            "meeting_id": "mtg-x",
            "agenda_item": "6.a",
            "agenda_title": "Housing Element Update",
            "text": "The planning commission recommends approval of the housing element.",
            "page_start": 15,
            "page_end": 22,
            "chunk_index": 3,
            "total_chunks": 8,
            "source_file": "agenda_packet_2025-12-01.pdf",
            "source_type": "agenda_packet",
        }]
        backend.store_chunks("city-test", chunks)
        results = backend.get_chunks("city-test")
        assert len(results) == 1
        c = results[0]
        assert c["text"] == "The planning commission recommends approval of the housing element."
        assert c["agenda_item"] == "6.a"
        assert c["agenda_title"] == "Housing Element Update"
        assert c["page_start"] == 15
        assert c["page_end"] == 22
        assert c["chunk_index"] == 3
        assert c["total_chunks"] == 8
        assert c["source_file"] == "agenda_packet_2025-12-01.pdf"

    def test_chunks_valid_from_set(self, backend):
        as_of = datetime(2025, 11, 15, 12, 0, 0)
        backend.store_chunks("city-test", [{
            "meeting_id": "mtg-x", "text": "Test chunk", "agenda_item": "1",
        }], as_of=as_of)
        results = backend.get_chunks("city-test")
        assert results[0]["valid_from"] == "2025-11-15T12:00:00"


class TestFederalAwardFieldRoundTrip:
    """Assert federal award fields survive store → get round-trip."""

    def test_all_award_fields(self, backend):
        awards = [{
            "award_id": "award-full",
            "cfda_number": "14.218",
            "recipient_name": "City of San Rafael",
            "recipient_uei": "UEI-ABC-123",
            "amount_cents": 750_000_00,
            "period_start": "2025-07-01",
            "period_end": "2026-06-30",
            "program_name": "Community Development Block Grant",
            "awarding_agency": "Department of Housing and Urban Development",
            "funding_agency": "HUD",
            "award_type": "grant",
        }]
        backend.store_federal_awards("city-test", awards)
        results = backend.get_federal_awards("city-test")
        assert len(results) == 1
        a = results[0]
        assert a["cfda_number"] == "14.218"
        assert a["recipient_name"] == "City of San Rafael"
        assert a["recipient_uei"] == "UEI-ABC-123"
        assert a["amount_cents"] == 750_000_00
        assert a["period_start"] == "2025-07-01"
        assert a["period_end"] == "2026-06-30"
        assert a["program_name"] == "Community Development Block Grant"
        assert a["awarding_agency"] == "Department of Housing and Urban Development"
        assert a["award_type"] == "grant"

    def test_award_period_filter(self, backend):
        awards = [
            {"award_id": "a1", "cfda_number": "14.218", "period_start": "2025-07-01", "period_end": "2026-06-30",
             "recipient_name": "City", "amount_cents": 100},
            {"award_id": "a2", "cfda_number": "20.205", "period_start": "2024-01-01", "period_end": "2024-12-31",
             "recipient_name": "City", "amount_cents": 200},
        ]
        backend.store_federal_awards("city-test", awards)
        results = backend.get_federal_awards("city-test", period_start="2025-01-01")
        assert len(results) == 1
        assert results[0]["cfda_number"] == "14.218"

