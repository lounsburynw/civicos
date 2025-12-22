"""
Tests for SQLiteBackend implementation of StorageBackend protocol.

Validates that SQLiteBackend correctly implements the StorageBackend protocol
and integrates with the 4-stage pipeline (discover -> ingest -> store -> index).
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from civic.storage import (
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
        # Check all required methods exist
        assert hasattr(backend, "backend_type")
        assert hasattr(backend, "validate")
        assert hasattr(backend, "store_meetings")
        assert hasattr(backend, "get_meetings")
        assert hasattr(backend, "get_stats")
        assert hasattr(backend, "delete_meetings")


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
        assert result.check_duration_ms >= 0


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
        """get_meetings should return list of dictionaries."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.get_meetings("city-test")
        assert isinstance(result, list)
        assert all(isinstance(m, dict) for m in result)

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
        """get_stats should return StorageStats instance."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert isinstance(stats, StorageStats)

    def test_get_stats_meeting_count(self, backend, sample_meetings):
        """get_stats should report correct meeting count."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert stats.meeting_count == 3

    def test_get_stats_date_range(self, backend, sample_meetings):
        """get_stats should report date range of meetings."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert stats.earliest_meeting is not None
        assert stats.latest_meeting is not None
        assert stats.earliest_meeting <= stats.latest_meeting

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

    def test_pipeline_integration(self, temp_db, sample_meetings):
        """Test SQLiteBackend integration with Pipeline."""
        from civic_extraction.pipeline import Pipeline, StageState

        # Create mock source
        class MockSource:
            source_id = "mock-source"

            def health(self):
                class Health:
                    available_count = 3
                    errors = []

                    def to_dict(self):
                        return {"available_count": 3}

                return Health()

            def get_meetings(self, days_ahead=90, days_past=30):
                return sample_meetings

        # Create pipeline with storage
        storage = SQLiteBackend(temp_db)
        pipeline = Pipeline(
            source=MockSource(),
            jurisdiction_id="city-test",
            storage_target=storage,
        )

        # Run pipeline
        result = pipeline.run()

        # Verify all stages completed
        assert result.success
        assert result.stages["discover"].state == StageState.COMPLETED
        assert result.stages["ingest"].state == StageState.COMPLETED
        assert result.stages["store"].state == StageState.COMPLETED
        assert result.stages["index"].state == StageState.COMPLETED

        # Verify data persisted
        assert result.stages["store"].items_processed == 3
        stored = storage.get_meetings("city-test")
        assert len(stored) == 3
