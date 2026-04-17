"""
Tests for PostgresBackend implementation of StorageBackend protocol.

Validates that PostgresBackend correctly implements the StorageBackend protocol
and integrates with the 4-stage pipeline (discover -> ingest -> store -> index).

These tests require a PostgreSQL database. Set CIVICOS_TEST_POSTGRES_URL env var
to run: export CIVICOS_TEST_POSTGRES_URL="postgresql://user:pass@localhost:5432/civic_test"

Tests are skipped if PostgreSQL is unavailable.
"""

import os
from datetime import datetime

import pytest

from civicos.storage import (
    StorageBackend,
    StorageStats,
    StorageValidationResult,
)

# Check if psycopg2 is available
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False

# Check if PostgresBackend can be imported (requires psycopg2)
try:
    from civicos.storage import PostgresBackend
    POSTGRES_BACKEND_AVAILABLE = True
except ImportError:
    PostgresBackend = None  # type: ignore
    POSTGRES_BACKEND_AVAILABLE = False


# Get test database URL from environment
POSTGRES_URL = os.environ.get("CIVICOS_TEST_POSTGRES_URL")

# Determine if we can run Postgres tests
CAN_RUN_POSTGRES_TESTS = (
    PSYCOPG2_AVAILABLE
    and POSTGRES_BACKEND_AVAILABLE
    and POSTGRES_URL is not None
)

# Skip reason message
SKIP_REASON = (
    "PostgreSQL tests skipped: "
    + ("psycopg2 not installed" if not PSYCOPG2_AVAILABLE
       else "PostgresBackend not available" if not POSTGRES_BACKEND_AVAILABLE
       else "CIVICOS_TEST_POSTGRES_URL not set")
)

# Skip all tests in this module if Postgres is not available
pytestmark = pytest.mark.skipif(
    not CAN_RUN_POSTGRES_TESTS,
    reason=SKIP_REASON
)


@pytest.fixture(scope="function")
def clean_db():
    """
    Clean up test tables before/after each test.

    Creates a fresh schema for each test to ensure isolation.
    """
    if not CAN_RUN_POSTGRES_TESTS:
        pytest.skip(SKIP_REASON)

    conn = psycopg2.connect(POSTGRES_URL)
    cursor = conn.cursor()

    # Drop and recreate test tables for clean state
    cursor.execute("DROP TABLE IF EXISTS agenda_items CASCADE")
    cursor.execute("DROP TABLE IF EXISTS meetings CASCADE")
    cursor.execute("DROP TABLE IF EXISTS city_states CASCADE")
    conn.commit()

    yield POSTGRES_URL

    # Cleanup after test
    cursor.execute("DROP TABLE IF EXISTS agenda_items CASCADE")
    cursor.execute("DROP TABLE IF EXISTS meetings CASCADE")
    cursor.execute("DROP TABLE IF EXISTS city_states CASCADE")
    conn.commit()
    conn.close()


@pytest.fixture
def backend(clean_db):
    """Create a PostgresBackend instance for testing."""
    return PostgresBackend(clean_db)


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


class TestPostgresBackendProtocol:
    """Tests for StorageBackend protocol compliance."""

    def test_backend_type_returns_postgres(self, backend):
        """backend_type should return 'postgres'."""
        assert backend.backend_type == "postgres"

    def test_implements_storage_backend_protocol(self, backend):
        """PostgresBackend should implement StorageBackend protocol."""
        # Verify required methods are callable
        assert callable(backend.validate)
        assert callable(backend.store_meetings)
        assert callable(backend.get_meetings)
        assert callable(backend.get_stats)
        assert callable(backend.delete_meetings)
        # backend_type should return a non-empty string
        assert isinstance(backend.backend_type, str)
        assert len(backend.backend_type) > 0

    def test_isinstance_storage_backend(self, backend):
        """PostgresBackend should pass isinstance check for StorageBackend."""
        assert isinstance(backend, StorageBackend)


class TestPostgresBackendValidation:
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
        """Validation should track non-zero check duration."""
        result = backend.validate()
        assert result.check_duration_ms > 0  # Real DB validation takes measurable time


class TestPostgresBackendStoreMeetings:
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

    def test_store_meetings_idempotent(self, backend):
        """Storing identical meetings multiple times should not create duplicates.

        This is a regression test for the bug fixed in Session 471 where
        store_meetings was closing all meetings before inserting, causing
        duplicate historical versions on each run.
        """
        meeting = {
            "id": "mtg-idempotent",
            "title": "Idempotent Test",
            "meeting_datetime": "2025-12-15T18:00:00",
            "status": "scheduled",
            "location": None,
            "agenda_url": "https://example.com/agenda",
            "minutes_url": None,
            "video_url": None,
            "virtual_url": None,
            "source_platform": "test",
        }

        # Store three times with identical data
        backend.store_meetings("city-idempotent", [meeting])
        backend.store_meetings("city-idempotent", [meeting])
        backend.store_meetings("city-idempotent", [meeting])

        # Should have exactly 1 current row (valid_to IS NULL)
        result = backend.get_meetings("city-idempotent")
        assert len(result) == 1
        assert result[0]["title"] == "Idempotent Test"

        # Verify no historical versions were created (check raw table)
        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE id = 'mtg-idempotent'"
        )
        total_rows = cursor.fetchone()[0]
        conn.close()

        assert total_rows == 1, f"Expected 1 row, got {total_rows} (idempotency failed)"

    def test_store_meetings_idempotent_timezone_mismatch(self, backend):
        """Timezone-aware and naive datetimes should be treated as identical.

        Regression test: CivicPlus sends "2026-04-07T00:00:00+00:00" but Postgres
        stores as naive "2026-04-07T00:00:00". Without normalization, every cron run
        detected a phantom change and created a new version. See commit 7e42ca84.
        """
        meeting_naive = {
            "id": "mtg-tz-test",
            "title": "TZ Test",
            "meeting_datetime": "2026-04-07T00:00:00",
            "status": "scheduled",
            "agenda_url": "https://example.com/agenda",
            "minutes_url": None,
            "video_url": None,
            "virtual_url": None,
            "location": None,
            "source_platform": "test",
        }
        meeting_tz_aware = {
            **meeting_naive,
            "meeting_datetime": "2026-04-07T00:00:00+00:00",
        }
        meeting_z_suffix = {
            **meeting_naive,
            "meeting_datetime": "2026-04-07T00:00:00Z",
        }

        # Store naive, then re-store with +00:00, then with Z
        backend.store_meetings("city-tz-test", [meeting_naive])
        backend.store_meetings("city-tz-test", [meeting_tz_aware])
        backend.store_meetings("city-tz-test", [meeting_z_suffix])

        # Should still be exactly 1 row — no phantom versions
        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE id = 'mtg-tz-test'"
        )
        total_rows = cursor.fetchone()[0]
        conn.close()

        assert total_rows == 1, (
            f"Expected 1 row, got {total_rows} "
            "(timezone normalization failed — phantom versions created)"
        )

    def test_store_meetings_idempotent_none_vs_empty_string(self, backend):
        """None and empty string URL fields should be treated as identical."""
        meeting_none = {
            "id": "mtg-norm-test",
            "title": "Norm Test",
            "meeting_datetime": "2026-05-01T18:00:00",
            "status": "scheduled",
            "agenda_url": None,
            "minutes_url": None,
            "video_url": None,
            "virtual_url": None,
            "location": None,
            "source_platform": "test",
        }
        meeting_empty = {
            **meeting_none,
            "agenda_url": "",
            "location": "",
        }

        backend.store_meetings("city-norm-test", [meeting_none])
        backend.store_meetings("city-norm-test", [meeting_empty])

        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE id = 'mtg-norm-test'"
        )
        total_rows = cursor.fetchone()[0]
        conn.close()

        assert total_rows == 1, (
            f"Expected 1 row, got {total_rows} "
            "(None vs empty string normalization failed)"
        )

    def test_store_meetings_updates_meeting_type_on_change(self, backend):
        """meeting_type change should create a new version with the updated value.

        Regression: when archive config keys are renamed (e.g., city-berkeley
        view_2 -> zoning_adjustments_board), existing rows must pick up the new
        meeting_type. has_changes previously omitted meeting_type, so renames
        only took effect for brand-new meeting_ids.
        """
        base = {
            "id": "mtg-type-test",
            "title": "Type Test",
            "meeting_datetime": "2026-05-01T18:00:00",
            "status": "scheduled",
            "agenda_url": None,
            "minutes_url": None,
            "video_url": None,
            "virtual_url": None,
            "location": None,
            "source_platform": "test",
        }
        v1 = {**base, "meeting_type": "view_2"}
        v2 = {**base, "meeting_type": "zoning_adjustments_board"}

        backend.store_meetings("city-type-test", [v1])
        backend.store_meetings("city-type-test", [v2])

        current = backend.get_meetings("city-type-test")
        assert len(current) == 1
        assert current[0]["meeting_type"] == "zoning_adjustments_board"

        conn = psycopg2.connect(POSTGRES_URL)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM meetings WHERE id = 'mtg-type-test'"
        )
        total_rows = cursor.fetchone()[0]
        conn.close()

        assert total_rows == 2, (
            f"Expected 2 rows (v1 closed, v2 current), got {total_rows}"
        )

    def test_store_meetings_multiple_jurisdictions(self, backend, sample_meetings):
        """Meetings should be stored separately per jurisdiction."""
        backend.store_meetings("city-a", sample_meetings[:1])
        backend.store_meetings("city-b", sample_meetings[1:])

        meetings_a = backend.get_meetings("city-a")
        meetings_b = backend.get_meetings("city-b")

        assert len(meetings_a) == 1
        assert len(meetings_b) == 2


class TestPostgresBackendGetMeetings:
    """Tests for get_meetings() method."""

    def test_get_meetings_returns_list(self, backend, sample_meetings):
        """get_meetings should return list of meeting dicts with expected content."""
        backend.store_meetings("city-test", sample_meetings)
        result = backend.get_meetings("city-test")
        assert len(result) == 3
        titles = [m["title"] for m in result]
        assert "City Council Meeting" in titles
        assert "Planning Commission" in titles
        assert "Budget Workshop" in titles

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


class TestPostgresBackendGetStats:
    """Tests for get_stats() method."""

    def test_get_stats_returns_storage_stats(self, backend, sample_meetings):
        """get_stats should return StorageStats with correct jurisdiction."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert isinstance(stats, StorageStats)
        assert stats.jurisdiction_id == "city-test"
        assert stats.meeting_count >= 1

    def test_get_stats_meeting_count(self, backend, sample_meetings):
        """get_stats should report correct meeting count."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert stats.meeting_count == 3

    def test_get_stats_date_range(self, backend, sample_meetings):
        """get_stats should report correct date range matching stored meetings."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        # Sample meetings span Dec 1 to Dec 20, 2025
        assert stats.earliest_meeting is not None
        assert stats.latest_meeting is not None
        assert "2025-12-01" in str(stats.earliest_meeting)
        assert "2025-12-20" in str(stats.latest_meeting)
        assert stats.earliest_meeting < stats.latest_meeting

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

    def test_get_stats_includes_backend_type(self, backend, sample_meetings):
        """get_stats should include backend_type in metadata."""
        backend.store_meetings("city-test", sample_meetings)
        stats = backend.get_stats("city-test")
        assert stats.metadata.get("backend_type") == "postgres"


class TestPostgresBackendDeleteMeetings:
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


class TestPostgresBackendIntegration:
    """Integration tests for PostgresBackend."""

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


class TestExtractionVersioning:
    """Tests for extraction_version column population."""

    def test_store_meetings_with_extraction_version(self, backend):
        """Meetings with extraction_version should persist the value."""
        meetings = [
            {
                "id": "mtg-versioned-001",
                "title": "Versioned Meeting",
                "meeting_datetime": "2025-12-01T18:00:00",
                "meeting_type": "city_council",
                "source_platform": "legistar",
                "extraction_version": "0.1.0",
            }
        ]
        backend.store_meetings("city-version-test", meetings)

        # Verify the extraction_version was stored
        conn = backend._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT extraction_version FROM meetings
            WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
        """, ("mtg-versioned-001", "city-version-test"))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "0.1.0"

    def test_store_meetings_without_extraction_version(self, backend):
        """Meetings without extraction_version should store NULL."""
        meetings = [
            {
                "id": "mtg-no-version-001",
                "title": "No Version Meeting",
                "meeting_datetime": "2025-12-01T18:00:00",
                "meeting_type": "city_council",
                "source_platform": "legistar",
            }
        ]
        backend.store_meetings("city-version-test", meetings)

        # Verify extraction_version is NULL
        conn = backend._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT extraction_version FROM meetings
            WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
        """, ("mtg-no-version-001", "city-version-test"))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] is None

    def test_store_chunks_with_extraction_version(self, backend):
        """Chunks with extraction_version should persist the value."""
        chunks = [
            {
                "id": "chunk-versioned-001",
                "meeting_id": "mtg-001",
                "text": "Test chunk text",
                "source_file": "test.pdf",
                "extraction_version": "0.2.0",
            }
        ]
        backend.store_chunks("city-version-test", chunks)

        # Verify the extraction_version was stored
        conn = backend._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT extraction_version FROM chunks
            WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
        """, ("chunk-versioned-001", "city-version-test"))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "0.2.0"

    def test_store_decisions_with_extraction_version(self, backend):
        """Decisions with extraction_version should persist the value."""
        decisions = [
            {
                "id": "dec-versioned-001",
                "meeting_date": "2025-12-01",
                "agenda_item": "5A",
                "title": "Versioned Decision",
                "outcome": "approved",
                "extraction_version": "0.3.0",
            }
        ]
        backend.store_decisions("city-version-test", decisions)

        # Verify the extraction_version was stored
        conn = backend._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT extraction_version FROM decisions
            WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
        """, ("dec-versioned-001", "city-version-test"))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "0.3.0"

    def test_store_issues_with_extraction_version(self, backend):
        """Issues with extraction_version should persist the value."""
        issues = [
            {
                "id": "issue-versioned-001",
                "provider": "seeclickfix",
                "external_id": "12345",
                "title": "Versioned Issue",
                "status": "open",
                "extraction_version": "0.4.0",
            }
        ]
        backend.store_issues("city-version-test", issues)

        # Verify the extraction_version was stored
        conn = backend._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT extraction_version FROM issues
            WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL
        """, ("issue-versioned-001", "city-version-test"))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "0.4.0"

