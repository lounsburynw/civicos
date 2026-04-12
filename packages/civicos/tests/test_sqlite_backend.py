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

