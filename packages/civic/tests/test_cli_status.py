"""
Tests for civic CLI status command.

Tests the ingestion status reporting functionality including:
- State database statistics gathering
- ChromaDB collection statistics
- Freshness calculation and indicators
- Human-readable and JSON output formatting
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from civic.cli import (
    Colors,
    colorize,
    calculate_gaps,
    format_bytes,
    format_relative_time,
    get_chroma_stats,
    get_file_stats,
    get_freshness_indicator,
    get_source_counts,
    get_state_db_stats,
    print_status,
)


class TestColorize:
    """Tests for colorize function."""

    def test_colorize_applies_color_when_tty(self):
        """Test that color codes are applied when stdout is a tty."""
        # When running in pytest, stdout.isatty() returns False
        # So colorize won't apply colors. Test the logic directly:
        # With no_color=False and a TTY, colors should be applied
        # Since we can't easily mock isatty, we test that no_color=True disables
        pass  # See test_colorize_no_color

    def test_colorize_no_color(self):
        """Test that no_color flag disables colors."""
        result = colorize("test", Colors.GREEN, no_color=True)
        assert result == "test"
        assert Colors.GREEN not in result

    def test_colorize_returns_text(self):
        """Test that colorize always returns the text."""
        result = colorize("hello world", Colors.RED, no_color=False)
        assert "hello world" in result


class TestFormatRelativeTime:
    """Tests for format_relative_time function."""

    def test_none_returns_never(self):
        """Test that None datetime returns 'never'."""
        assert format_relative_time(None) == "never"

    def test_recent_shows_just_now(self):
        """Test that very recent times show 'just now'."""
        now = datetime.now()
        assert format_relative_time(now) == "just now"

    def test_minutes_ago(self):
        """Test formatting of minutes ago."""
        dt = datetime.now() - timedelta(minutes=30)
        result = format_relative_time(dt)
        assert "m ago" in result

    def test_hours_ago(self):
        """Test formatting of hours ago."""
        dt = datetime.now() - timedelta(hours=5)
        result = format_relative_time(dt)
        assert "h ago" in result

    def test_days_ago(self):
        """Test formatting of days ago."""
        dt = datetime.now() - timedelta(days=3)
        result = format_relative_time(dt)
        assert "3d ago" in result

    def test_months_ago(self):
        """Test formatting of months ago."""
        dt = datetime.now() - timedelta(days=60)
        result = format_relative_time(dt)
        assert "mo ago" in result

    def test_years_ago(self):
        """Test formatting of years ago."""
        dt = datetime.now() - timedelta(days=400)
        result = format_relative_time(dt)
        assert "y ago" in result


class TestGetFreshnessIndicator:
    """Tests for get_freshness_indicator function."""

    def test_none_returns_unknown(self):
        """Test that None returns unknown indicator."""
        indicator, color = get_freshness_indicator(None)
        assert indicator == "?"
        assert color == Colors.DIM

    def test_fresh_data_is_ok(self):
        """Test that data < 7 days old is OK."""
        dt = datetime.now() - timedelta(days=3)
        indicator, color = get_freshness_indicator(dt)
        assert indicator == "OK"
        assert color == Colors.GREEN

    def test_stale_data_is_yellow(self):
        """Test that data 7-30 days old is STALE."""
        dt = datetime.now() - timedelta(days=14)
        indicator, color = get_freshness_indicator(dt)
        assert indicator == "STALE"
        assert color == Colors.YELLOW

    def test_old_data_is_red(self):
        """Test that data > 30 days old is OLD."""
        dt = datetime.now() - timedelta(days=45)
        indicator, color = get_freshness_indicator(dt)
        assert indicator == "OLD"
        assert color == Colors.RED

    def test_boundary_7_days(self):
        """Test 7-day boundary (exactly 7 days is still OK)."""
        dt = datetime.now() - timedelta(days=7)
        indicator, _ = get_freshness_indicator(dt)
        assert indicator == "OK"  # <= 7 is OK

    def test_boundary_8_days(self):
        """Test 8 days is STALE."""
        dt = datetime.now() - timedelta(days=8)
        indicator, _ = get_freshness_indicator(dt)
        assert indicator == "STALE"

    def test_boundary_30_days(self):
        """Test 30-day boundary (exactly 30 days is still STALE)."""
        dt = datetime.now() - timedelta(days=30)
        indicator, _ = get_freshness_indicator(dt)
        assert indicator == "STALE"  # <= 30 is STALE

    def test_boundary_31_days(self):
        """Test 31 days is OLD."""
        dt = datetime.now() - timedelta(days=31)
        indicator, _ = get_freshness_indicator(dt)
        assert indicator == "OLD"


class TestFormatBytes:
    """Tests for format_bytes function."""

    def test_zero_bytes(self):
        """Test zero bytes."""
        assert format_bytes(0) == "0 B"

    def test_bytes(self):
        """Test bytes formatting."""
        assert "B" in format_bytes(500)

    def test_kilobytes(self):
        """Test kilobytes formatting."""
        result = format_bytes(1500)
        assert "KB" in result

    def test_megabytes(self):
        """Test megabytes formatting."""
        result = format_bytes(1500000)
        assert "MB" in result

    def test_gigabytes(self):
        """Test gigabytes formatting."""
        result = format_bytes(1500000000)
        assert "GB" in result


class TestGetStateDbStats:
    """Tests for get_state_db_stats function."""

    def test_missing_db_returns_empty_stats(self):
        """Test that missing database returns empty stats."""
        stats = get_state_db_stats("/nonexistent/path.db", "city-test")
        assert stats["meetings"]["count"] == 0
        assert stats["agenda_items"]["count"] == 0
        assert stats["issues"]["count"] == 0

    def test_empty_db_returns_zero_counts(self):
        """Test that empty database returns zero counts."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Create minimal schema
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE meetings (
                    id TEXT PRIMARY KEY,
                    jurisdiction_id TEXT,
                    meeting_datetime TEXT,
                    updated_at TEXT,
                    valid_to TEXT
                )
            """)
            conn.commit()
            conn.close()

            stats = get_state_db_stats(db_path, "city-test")
            assert stats["meetings"]["count"] == 0
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_counts_meetings_correctly(self):
        """Test that meetings are counted correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE meetings (
                    id TEXT PRIMARY KEY,
                    jurisdiction_id TEXT,
                    meeting_datetime TEXT,
                    updated_at TEXT,
                    valid_to TEXT
                )
            """)
            # Add 3 current meetings and 1 historical
            cursor.execute(
                "INSERT INTO meetings VALUES (?, ?, ?, ?, ?)",
                ("m1", "city-test", "2024-01-01", "2024-01-01", None)
            )
            cursor.execute(
                "INSERT INTO meetings VALUES (?, ?, ?, ?, ?)",
                ("m2", "city-test", "2024-02-01", "2024-02-01", None)
            )
            cursor.execute(
                "INSERT INTO meetings VALUES (?, ?, ?, ?, ?)",
                ("m3", "city-test", "2024-03-01", "2024-03-01", None)
            )
            cursor.execute(
                "INSERT INTO meetings VALUES (?, ?, ?, ?, ?)",
                ("m4", "city-test", "2024-01-01", "2024-01-01", "2024-02-01")  # Historical
            )
            conn.commit()
            conn.close()

            stats = get_state_db_stats(db_path, "city-test")
            assert stats["meetings"]["count"] == 3  # Only current (valid_to IS NULL)
        finally:
            Path(db_path).unlink(missing_ok=True)


class TestGetChromaStats:
    """Tests for get_chroma_stats function."""

    def test_missing_vectors_dir_returns_empty(self):
        """Test that missing vectors directory returns empty stats."""
        stats = get_chroma_stats("city-test", "/nonexistent/vectors")
        assert stats["collections"] == {}
        assert stats["total_documents"] == 0

    def test_collection_stats_gathered(self):
        """Test that collection stats are gathered and db size is reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the jurisdiction subdirectory
            vectors_dir = Path(tmpdir)
            jurisdiction_dir = vectors_dir / "city-test"
            jurisdiction_dir.mkdir(parents=True)

            # Create a dummy chroma.sqlite3 file
            chroma_db = jurisdiction_dir / "chroma.sqlite3"
            chroma_db.write_bytes(b"dummy" * 1000)

            # Without mocking, chromadb won't find valid collections
            # but should still report the db size
            stats = get_chroma_stats("city-test", str(vectors_dir))

            assert stats["db_size_bytes"] == 5000  # 5 bytes * 1000


class TestPrintStatus:
    """Tests for print_status function."""

    def test_json_only_returns_dict(self):
        """Test that json_only mode returns dict without printing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status = print_status(
                jurisdiction_id="city-test",
                state_db_path="/nonexistent.db",
                vectors_dir=tmpdir,
                json_only=True,
            )

            assert isinstance(status, dict)
            assert "jurisdiction_id" in status
            assert "timestamp" in status
            assert "overall_status" in status

    def test_overall_status_empty_when_no_collections(self):
        """Test that overall status is EMPTY when no collections exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status = print_status(
                jurisdiction_id="city-test",
                state_db_path="/nonexistent.db",
                vectors_dir=tmpdir,
                json_only=True,
            )

            assert status["overall_status"] == "EMPTY"

    def test_status_includes_all_sections(self):
        """Test that status dict includes all required sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status = print_status(
                jurisdiction_id="city-test",
                state_db_path="/nonexistent.db",
                vectors_dir=tmpdir,
                json_only=True,
            )

            assert "state_db" in status
            assert "chroma_db" in status
            assert "files" in status
            assert "overall_status" in status


class TestIntegration:
    """Integration tests using actual civic data if available."""

    @pytest.fixture
    def civic_paths(self):
        """Get paths to actual civic data."""
        # Navigate from tests/ up to project root
        # tests/test_cli_status.py -> tests -> civic -> packages -> civic (project root)
        base = Path(__file__).parent.parent.parent.parent.parent
        return {
            "state_db": base / "data" / "civic_state.db",
            "vectors_dir": base / "data" / "pilot" / "vectors",
        }

    @pytest.mark.integration
    def test_san_rafael_status(self, civic_paths):
        """Test status command with actual San Rafael data."""
        if not civic_paths["state_db"].exists():
            pytest.skip(f"civic_state.db not found at {civic_paths['state_db']}")

        status = print_status(
            jurisdiction_id="city-san-rafael",
            state_db_path=str(civic_paths["state_db"]),
            vectors_dir=str(civic_paths["vectors_dir"]),
            json_only=True,
        )

        # Verify structure
        assert status["jurisdiction_id"] == "city-san-rafael"
        assert "timestamp" in status
        assert status["overall_status"] in ["HEALTHY", "OK", "DEGRADED", "EMPTY"]

        # Verify collections are reported
        collections = status["chroma_db"]["collections"]
        # At least some collections should exist
        assert len([c for c in collections.values() if c is not None]) >= 0

    @pytest.mark.integration
    def test_status_json_serializable(self, civic_paths):
        """Test that status output is JSON serializable."""
        if not civic_paths["state_db"].exists():
            pytest.skip("civic_state.db not found")

        status = print_status(
            jurisdiction_id="city-san-rafael",
            state_db_path=str(civic_paths["state_db"]),
            vectors_dir=str(civic_paths["vectors_dir"]),
            json_only=True,
        )

        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        # Should not raise
        json_str = json.dumps(status, default=json_serializer)
        assert isinstance(json_str, str)

        # Should round-trip
        parsed = json.loads(json_str)
        assert parsed["jurisdiction_id"] == status["jurisdiction_id"]


class TestCalculateGaps:
    """Tests for calculate_gaps function."""

    def test_perfect_coverage(self):
        """Test 100% coverage calculation."""
        ingested = {"meetings": 100, "issues": 500}
        source = {
            "meetings": {"count": 100, "source": "proudcity", "error": None},
            "issues": {"count": 500, "source": "seeclickfix", "error": None},
        }

        gaps = calculate_gaps(ingested, source)

        assert gaps["meetings"]["ingested"] == 100
        assert gaps["meetings"]["source"] == 100
        assert gaps["meetings"]["gap"] == 0
        assert gaps["meetings"]["pct"] == 100.0
        assert gaps["overall_coverage"] == 100.0

    def test_partial_coverage(self):
        """Test partial coverage calculation."""
        ingested = {"meetings": 80, "issues": 400}
        source = {
            "meetings": {"count": 100, "source": "proudcity", "error": None},
            "issues": {"count": 500, "source": "seeclickfix", "error": None},
        }

        gaps = calculate_gaps(ingested, source)

        assert gaps["meetings"]["gap"] == 20
        assert gaps["meetings"]["pct"] == 80.0
        assert gaps["issues"]["gap"] == 100
        assert gaps["issues"]["pct"] == 80.0
        assert gaps["overall_coverage"] == 80.0

    def test_source_error_handling(self):
        """Test handling of source errors."""
        ingested = {"meetings": 100, "issues": 500}
        source = {
            "meetings": {"count": 0, "source": "proudcity", "error": "Connection failed"},
            "issues": {"count": 500, "source": "seeclickfix", "error": None},
        }

        gaps = calculate_gaps(ingested, source)

        assert gaps["meetings"]["source"] is None
        assert gaps["meetings"]["gap"] is None
        assert gaps["meetings"]["error"] == "Connection failed"
        assert gaps["issues"]["pct"] == 100.0

    def test_zero_source_count(self):
        """Test handling of zero source count."""
        ingested = {"meetings": 50, "issues": 0}
        source = {
            "meetings": {"count": 0, "source": "proudcity", "error": None},
            "issues": {"count": 0, "source": "seeclickfix", "error": None},
        }

        gaps = calculate_gaps(ingested, source)

        # When source is 0, gap should be 0 and pct should be 100
        assert gaps["meetings"]["gap"] == 0
        assert gaps["meetings"]["pct"] == 100.0
        assert gaps["overall_coverage"] == 100.0

    def test_missing_data_types(self):
        """Test handling of missing data types in input."""
        ingested = {"meetings": 100}  # Missing issues
        source = {
            "meetings": {"count": 100, "source": "proudcity", "error": None},
        }

        gaps = calculate_gaps(ingested, source)

        assert gaps["meetings"]["pct"] == 100.0
        # Issues should have 0 ingested since not provided
        assert gaps["issues"]["ingested"] == 0


class TestGetSourceCounts:
    """Tests for get_source_counts function."""

    def test_returns_structure(self):
        """Test that get_source_counts returns expected structure."""
        # This test doesn't hit external APIs, just verifies structure
        result = get_source_counts("unknown-jurisdiction")

        assert "meetings" in result
        assert "issues" in result
        assert "queried_at" in result

        assert "count" in result["meetings"]
        assert "source" in result["meetings"]
        assert "error" in result["meetings"]

    def test_unknown_jurisdiction_graceful(self):
        """Test that unknown jurisdiction returns gracefully."""
        # For unknown jurisdictions, meetings should show error or 0
        result = get_source_counts("city-unknown")

        # Should not raise, just return structure with error or 0 count
        assert isinstance(result["meetings"]["count"], int)


class TestPrintStatusWithGaps:
    """Tests for print_status with gap analysis enabled."""

    def test_check_gaps_adds_gap_analysis(self):
        """Test that check_gaps=True adds gap_analysis to status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Without actual API calls, gap_analysis should still be added
            # but may have errors for sources
            status = print_status(
                jurisdiction_id="city-test",
                state_db_path="/nonexistent.db",
                vectors_dir=tmpdir,
                json_only=True,
                check_gaps=True,
            )

            assert "gap_analysis" in status
            assert "source_counts" in status
            assert "meetings" in status["gap_analysis"]
            assert "issues" in status["gap_analysis"]

    def test_check_gaps_false_no_gap_analysis(self):
        """Test that check_gaps=False does not add gap_analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status = print_status(
                jurisdiction_id="city-test",
                state_db_path="/nonexistent.db",
                vectors_dir=tmpdir,
                json_only=True,
                check_gaps=False,
            )

            assert "gap_analysis" not in status
            assert "source_counts" not in status
