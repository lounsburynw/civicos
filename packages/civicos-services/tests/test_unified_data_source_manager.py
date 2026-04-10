"""
Tests for unified_data_source_manager.py — multi-source failover, data archival,
quality scoring, vendor independence calculation, and resilience reporting.

Mocks external I/O (CDP client, Legistar client, SQLite archive on disk).
Tests real logic: failover ordering, quality assessment, comment deadline
calculation, Legistar normalization, vendor risk scoring, and resilience
recommendation generation.

To run:
    pytest packages/civicos-services/tests/test_unified_data_source_manager.py -q --override-ini="addopts="
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.monitoring.unified_data_source_manager import (
    CivicDataArchive,
    DataSourceConfig,
    UnifiedDataSourceManager,
    create_unified_manager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    """Create a DataSourceConfig with sensible defaults."""
    defaults = dict(
        jurisdiction_id="city-testville",
        jurisdiction_name="Testville",
        timezone="America/Los_Angeles",
        cdp_available=False,
        legistar_available=False,
        civic_scraper_available=False,
        html_parsing_available=False,
        archive_enabled=False,
    )
    defaults.update(overrides)
    return DataSourceConfig(**defaults)


def _make_archive(tmp_path):
    """Create a CivicDataArchive backed by a temp directory."""
    return CivicDataArchive(archive_path=str(tmp_path / "test_archive.db"))


def _sample_event(event_id="evt-1", title="City Council Meeting", **overrides):
    """Return a civic event dict with required fields."""
    base = {
        "id": event_id,
        "title": title,
        "meeting_datetime": "2026-05-01T18:00:00+00:00",
        "status": "scheduled",
        "meeting_type": "regular",
        "location": "City Hall",
        "agenda_uri": "https://example.com/agenda.pdf",
        "minutes_uri": "",
        "video_uri": "",
        "source_uri": "https://example.com/events/1",
        "participation_methods": ["public_comment"],
        "comment_deadline": "2026-04-30T18:00:00+00:00",
    }
    base.update(overrides)
    return base


def _sample_legistar_event(event_id=123, **overrides):
    """Return a Legistar-format event dict."""
    base = {
        "event_id": event_id,
        "title": "Planning Commission",
        "meeting_datetime": "2026-05-15T19:00:00+00:00",
        "status": "Scheduled",
        "meeting_type": "regular",
        "location": "Council Chambers",
        "agenda_url": "https://legistar.com/agenda/123",
        "minutes_url": "",
        "video_url": "https://legistar.com/video/123",
        "date": "2026-05-15T19:00:00+00:00",
    }
    base.update(overrides)
    return base


def _make_manager(tmp_path, config=None, **config_overrides):
    """Create a UnifiedDataSourceManager with archive in tmp_path."""
    if config is None:
        config = _make_config(**config_overrides)
    with patch(
        "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
    ) as MockArchive:
        archive = _make_archive(tmp_path)
        MockArchive.return_value = archive
        manager = UnifiedDataSourceManager(config)
        manager.archive = archive
    return manager


# ---------------------------------------------------------------------------
# DataSourceConfig defaults
# ---------------------------------------------------------------------------


class TestDataSourceConfig:
    def test_default_primary_source_is_auto(self):
        cfg = _make_config()
        assert cfg.primary_source == "auto"

    def test_default_failover_enabled(self):
        cfg = _make_config()
        assert cfg.failover_enabled is True

    def test_default_archive_disabled(self):
        cfg = _make_config()
        assert cfg.archive_enabled is False

    def test_optional_fields_default_to_none(self):
        cfg = _make_config()
        assert cfg.legistar_client_name is None
        assert cfg.cdp_config is None
        assert cfg.civic_scraper_urls is None
        assert cfg.html_parsing_urls is None

    def test_custom_values_stored(self):
        cfg = _make_config(
            jurisdiction_id="city-oakland",
            jurisdiction_name="Oakland",
            legistar_client_name="oakland",
            legistar_available=True,
        )
        assert cfg.jurisdiction_id == "city-oakland"
        assert cfg.jurisdiction_name == "Oakland"
        assert cfg.legistar_client_name == "oakland"
        assert cfg.legistar_available is True


# ---------------------------------------------------------------------------
# CivicDataArchive — SQLite archival
# ---------------------------------------------------------------------------


class TestCivicDataArchive:
    def test_creates_tables_on_init(self, tmp_path):
        archive = _make_archive(tmp_path)
        conn = sqlite3.connect(archive.archive_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = sorted(row[0] for row in cursor.fetchall())
        conn.close()
        assert "civic_events" in tables
        assert "source_reliability" in tables
        assert "vendor_dependency" in tables

    def test_archive_events_stores_and_retrieves(self, tmp_path):
        archive = _make_archive(tmp_path)
        events = [_sample_event()]
        archive.archive_events(events, "legistar_api", "city-testville", 0.85)

        retrieved = archive.get_archived_events("city-testville", days_forward=365)
        assert len(retrieved) == 1
        assert retrieved[0]["title"] == "City Council Meeting"
        assert retrieved[0]["jurisdiction"] == "city-testville"
        assert retrieved[0]["source_platform"] == "legistar_api"
        assert retrieved[0]["data_quality_score"] == 0.85

    def test_archive_events_empty_list_is_noop(self, tmp_path):
        archive = _make_archive(tmp_path)
        archive.archive_events([], "legistar_api", "city-testville", 0.0)
        retrieved = archive.get_archived_events("city-testville")
        assert len(retrieved) == 0

    def test_archive_events_stores_participation_methods_as_json(self, tmp_path):
        archive = _make_archive(tmp_path)
        events = [_sample_event(participation_methods=["public_comment", "written"])]
        archive.archive_events(events, "cdp", "city-testville", 0.9)

        retrieved = archive.get_archived_events("city-testville", days_forward=365)
        assert retrieved[0]["participation_methods"] == ["public_comment", "written"]

    def test_archive_events_upserts_on_duplicate_id(self, tmp_path):
        archive = _make_archive(tmp_path)
        events_v1 = [_sample_event(title="Original Title")]
        archive.archive_events(events_v1, "legistar_api", "city-testville", 0.7)

        events_v2 = [_sample_event(title="Updated Title")]
        archive.archive_events(events_v2, "legistar_api", "city-testville", 0.9)

        retrieved = archive.get_archived_events("city-testville", days_forward=365)
        assert len(retrieved) == 1
        assert retrieved[0]["title"] == "Updated Title"
        assert retrieved[0]["data_quality_score"] == 0.9

    def test_get_archived_events_filters_by_jurisdiction(self, tmp_path):
        archive = _make_archive(tmp_path)
        archive.archive_events(
            [_sample_event(event_id="a1")], "cdp", "city-alpha", 0.8
        )
        archive.archive_events(
            [_sample_event(event_id="b1")], "cdp", "city-beta", 0.8
        )

        alpha_events = archive.get_archived_events("city-alpha", days_forward=365)
        assert len(alpha_events) == 1
        assert alpha_events[0]["id"] == "a1"

    def test_update_source_reliability_calculates_success_rate(self, tmp_path):
        archive = _make_archive(tmp_path)
        # 0 errors → success_rate = 1.0
        archive.update_source_reliability("city-testville", "cdp", 5, 0.9, 200, 0)
        # 2 errors → success_rate = 1.0 - 0.4 = 0.6
        archive.update_source_reliability(
            "city-testville", "legistar_api", 3, 0.7, 500, 2
        )

        conn = sqlite3.connect(archive.archive_path)
        rows = conn.execute(
            "SELECT source_platform, success_rate FROM source_reliability "
            "WHERE jurisdiction = 'city-testville' ORDER BY source_platform"
        ).fetchall()
        conn.close()

        rates = {row[0]: row[1] for row in rows}
        assert rates["cdp"] == 1.0
        assert rates["legistar_api"] == pytest.approx(0.6, abs=0.01)

    def test_update_source_reliability_clamps_at_zero(self, tmp_path):
        archive = _make_archive(tmp_path)
        # 10 errors → max(0, 1 - 2.0) = 0.0
        archive.update_source_reliability("city-testville", "html", 0, 0.1, 3000, 10)

        conn = sqlite3.connect(archive.archive_path)
        row = conn.execute(
            "SELECT success_rate FROM source_reliability "
            "WHERE jurisdiction = 'city-testville' AND source_platform = 'html'"
        ).fetchone()
        conn.close()
        assert row[0] == 0.0

    def test_archive_multiple_events_stores_all(self, tmp_path):
        archive = _make_archive(tmp_path)
        events = [
            _sample_event(event_id="e1", title="Budget Workshop"),
            _sample_event(event_id="e2", title="Zoning Hearing"),
            _sample_event(event_id="e3", title="Parks Commission"),
        ]
        archive.archive_events(events, "cdp", "city-testville", 0.85)

        retrieved = archive.get_archived_events("city-testville", days_forward=365)
        assert len(retrieved) == 3
        titles = {e["title"] for e in retrieved}
        assert titles == {"Budget Workshop", "Zoning Hearing", "Parks Commission"}


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------


class TestQualityScoring:
    def test_empty_events_scores_zero(self, tmp_path):
        manager = _make_manager(tmp_path)
        assert manager._assess_quality_score([]) == 0.0

    def test_full_event_scores_near_one(self, tmp_path):
        manager = _make_manager(tmp_path)
        event = _sample_event()  # has title, meeting_datetime, status, agenda_uri, location, participation_methods
        score = manager._assess_quality_score([event])
        # All required (0.7) + all desirable (0.3) = 1.0
        assert score == pytest.approx(1.0, abs=0.01)

    def test_required_fields_only_scores_seventy_percent(self, tmp_path):
        manager = _make_manager(tmp_path)
        event = {
            "title": "Meeting",
            "meeting_datetime": "2026-05-01",
            "status": "scheduled",
            # No desirable fields
        }
        score = manager._assess_quality_score([event])
        assert score == pytest.approx(0.7, abs=0.01)

    def test_partial_required_scores_proportionally(self, tmp_path):
        manager = _make_manager(tmp_path)
        event = {
            "title": "Meeting",
            # missing meeting_datetime and status
        }
        score = manager._assess_quality_score([event])
        # 1/3 required fields = 0.7/3 ≈ 0.233
        assert score == pytest.approx(0.7 / 3, abs=0.01)

    def test_average_across_multiple_events(self, tmp_path):
        manager = _make_manager(tmp_path)
        full_event = _sample_event()  # score ~1.0
        empty_event = {}  # score 0.0
        score = manager._assess_quality_score([full_event, empty_event])
        assert score == pytest.approx(0.5, abs=0.05)

    def test_desirable_fields_only_scores_thirty_percent(self, tmp_path):
        manager = _make_manager(tmp_path)
        event = {
            "agenda_uri": "https://example.com/agenda",
            "location": "City Hall",
            "participation_methods": ["public_comment"],
            # No required fields
        }
        score = manager._assess_quality_score([event])
        assert score == pytest.approx(0.3, abs=0.01)


# ---------------------------------------------------------------------------
# Comment deadline calculation
# ---------------------------------------------------------------------------


class TestCommentDeadline:
    def test_valid_datetime_returns_24h_before(self, tmp_path):
        manager = _make_manager(tmp_path)
        meeting = "2026-06-15T19:00:00+00:00"
        deadline = manager._calculate_comment_deadline(meeting)
        expected = datetime(2026, 6, 14, 19, 0, tzinfo=timezone.utc)
        assert deadline == expected.isoformat()

    def test_empty_string_returns_empty(self, tmp_path):
        manager = _make_manager(tmp_path)
        assert manager._calculate_comment_deadline("") == ""

    def test_invalid_format_returns_empty(self, tmp_path):
        manager = _make_manager(tmp_path)
        assert manager._calculate_comment_deadline("not-a-date") == ""

    def test_z_suffix_parsed_correctly(self, tmp_path):
        manager = _make_manager(tmp_path)
        deadline = manager._calculate_comment_deadline("2026-06-15T19:00:00Z")
        assert "2026-06-14" in deadline


# ---------------------------------------------------------------------------
# Legistar normalization
# ---------------------------------------------------------------------------


class TestLegistarNormalization:
    def test_normalizes_event_id_with_prefix(self, tmp_path):
        config = _make_config(
            legistar_available=False,
            legistar_client_name="testcity",
        )
        manager = _make_manager(tmp_path, config=config)
        events = [_sample_legistar_event(event_id=456)]
        normalized = manager._normalize_legistar_to_schema(events)

        assert len(normalized) == 1
        assert normalized[0]["id"] == "legistar_456"

    def test_normalizes_status_to_lowercase(self, tmp_path):
        manager = _make_manager(tmp_path, legistar_client_name="testcity")
        events = [_sample_legistar_event(status="SCHEDULED")]
        normalized = manager._normalize_legistar_to_schema(events)
        assert normalized[0]["status"] == "scheduled"

    def test_sets_source_platform(self, tmp_path):
        manager = _make_manager(tmp_path, legistar_client_name="testcity")
        normalized = manager._normalize_legistar_to_schema([_sample_legistar_event()])
        assert normalized[0]["source_platform"] == "legistar_api"

    def test_includes_participation_methods(self, tmp_path):
        manager = _make_manager(tmp_path, legistar_client_name="testcity")
        normalized = manager._normalize_legistar_to_schema([_sample_legistar_event()])
        assert "public_comment" in normalized[0]["participation_methods"]
        assert "in_person_attendance" in normalized[0]["participation_methods"]

    def test_constructs_source_uri(self, tmp_path):
        config = _make_config(legistar_client_name="oakland")
        manager = _make_manager(tmp_path, config=config)
        normalized = manager._normalize_legistar_to_schema(
            [_sample_legistar_event(event_id=789)]
        )
        assert normalized[0]["source_uri"] == (
            "https://webapi.legistar.com/v1/oakland/events/789"
        )

    def test_preserves_agenda_url(self, tmp_path):
        manager = _make_manager(tmp_path, legistar_client_name="testcity")
        normalized = manager._normalize_legistar_to_schema(
            [_sample_legistar_event(agenda_url="https://agenda.example.com")]
        )
        assert normalized[0]["agenda_uri"] == "https://agenda.example.com"

    def test_calculates_comment_deadline(self, tmp_path):
        manager = _make_manager(tmp_path, legistar_client_name="testcity")
        normalized = manager._normalize_legistar_to_schema(
            [_sample_legistar_event(date="2026-06-10T18:00:00+00:00")]
        )
        # 24 hours before meeting
        assert "2026-06-09" in normalized[0]["comment_deadline"]

    def test_empty_input_returns_empty(self, tmp_path):
        manager = _make_manager(tmp_path, legistar_client_name="testcity")
        assert manager._normalize_legistar_to_schema([]) == []


# ---------------------------------------------------------------------------
# Source priority ordering
# ---------------------------------------------------------------------------


class TestSourcePriority:
    def test_no_sources_yields_empty_priority(self, tmp_path):
        manager = _make_manager(tmp_path)
        assert manager.source_priority == []

    def test_civic_scraper_and_html_in_order(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        names = [s[0] for s in manager.source_priority]
        assert names == ["civic_scraper", "html_parsing"]

    def test_archive_appended_when_enabled(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            html_parsing_available=True,
            archive_enabled=True,
        )
        names = [s[0] for s in manager.source_priority]
        assert names == ["html_parsing", "archived"]

    def test_archive_excluded_when_disabled(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            html_parsing_available=True,
            archive_enabled=False,
        )
        names = [s[0] for s in manager.source_priority]
        assert names == ["html_parsing"]
        assert "archived" not in names


# ---------------------------------------------------------------------------
# Vendor independence
# ---------------------------------------------------------------------------


class TestVendorIndependence:
    def test_no_legistar_yields_full_independence(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        vi = manager._calculate_vendor_independence()
        assert vi["independence_score"] == 1.0
        assert vi["granicus_dependency"] is False
        assert vi["vendor_risk_level"] == "low"

    def test_legistar_only_yields_zero_independence(self, tmp_path):
        """When legistar is the only source, independence is 0.0 → high risk."""
        config = _make_config(legistar_available=True, legistar_client_name="test")
        with patch(
            "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
        ) as MockArchive:
            MockArchive.return_value = _make_archive(tmp_path)
            with patch(
                "civicos_services.monitoring.unified_data_source_manager.LegistarClient"
            ) as MockLegistar:
                MockLegistar.return_value = MagicMock()
                manager = UnifiedDataSourceManager(config)
                manager.archive = MockArchive.return_value

        vi = manager._calculate_vendor_independence()
        assert vi["independence_score"] == 0.0
        assert vi["granicus_dependency"] is True
        assert vi["vendor_risk_level"] == "high"

    def test_mixed_sources_yields_medium_risk(self, tmp_path):
        """Legistar + two other sources → total_sources=2, independence 0.5 → medium."""
        config = _make_config(
            legistar_available=True,
            legistar_client_name="test",
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        with patch(
            "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
        ) as MockArchive:
            MockArchive.return_value = _make_archive(tmp_path)
            with patch(
                "civicos_services.monitoring.unified_data_source_manager.LegistarClient"
            ) as MockLegistar:
                MockLegistar.return_value = MagicMock()
                manager = UnifiedDataSourceManager(config)
                manager.archive = MockArchive.return_value

        vi = manager._calculate_vendor_independence()
        # 3 sources - 1 = 2; 1 granicus dep → 1 - 1/2 = 0.5
        assert vi["independence_score"] == 0.5
        assert vi["vendor_risk_level"] == "medium"

    def test_no_sources_avoids_division_by_zero(self, tmp_path):
        manager = _make_manager(tmp_path)
        vi = manager._calculate_vendor_independence()
        # total_sources = -1, max(-1, 1) = 1 → independence = 1.0
        assert vi["total_sources"] == -1
        assert vi["vendor_risk_level"] == "low"


# ---------------------------------------------------------------------------
# get_civic_opportunities failover
# ---------------------------------------------------------------------------


class TestGetCivicOpportunities:
    def test_returns_events_from_first_successful_source(self, tmp_path):
        """civic_scraper returns empty, html_parsing returns events."""
        config = _make_config(
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        manager = _make_manager(tmp_path, config=config)

        # Patch html parsing to return events
        event = _sample_event()
        with patch.object(
            manager, "_get_html_parsing_events", return_value=[event]
        ):
            events, source, metadata = manager.get_civic_opportunities()

        assert len(events) == 1
        assert source == "html_parsing"
        assert metadata["events_count"] == 1
        assert metadata["quality_score"] == pytest.approx(1.0, abs=0.01)

    def test_all_sources_fail_returns_empty(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        # Both return empty (civic_scraper and html_parsing default to [])
        events, source, metadata = manager.get_civic_opportunities()
        assert events == []
        assert source == "none"
        assert metadata["events_count"] == 0

    def test_exception_in_source_triggers_failover(self, tmp_path):
        config = _make_config(
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        manager = _make_manager(tmp_path, config=config)

        # civic_scraper raises, html_parsing succeeds
        with patch.object(
            manager,
            "_get_civic_scraper_events",
            side_effect=RuntimeError("scraper down"),
        ):
            with patch.object(
                manager,
                "_get_html_parsing_events",
                return_value=[_sample_event()],
            ):
                events, source, metadata = manager.get_civic_opportunities()

        assert source == "html_parsing"
        assert len(events) == 1

    def test_failover_level_reflects_source_index(self, tmp_path):
        config = _make_config(
            civic_scraper_available=True,
            html_parsing_available=True,
        )
        manager = _make_manager(tmp_path, config=config)

        with patch.object(
            manager,
            "_get_html_parsing_events",
            return_value=[_sample_event()],
        ):
            _, _, metadata = manager.get_civic_opportunities()

        # html_parsing is index 1 (after civic_scraper at 0)
        assert metadata["failover_level"] == 1

    def test_all_exceptions_returns_last_error(self, tmp_path):
        config = _make_config(civic_scraper_available=True)
        manager = _make_manager(tmp_path, config=config)

        with patch.object(
            manager,
            "_get_civic_scraper_events",
            side_effect=ValueError("bad data"),
        ):
            events, source, metadata = manager.get_civic_opportunities()

        assert events == []
        assert source == "none"
        assert "bad data" in metadata["error"]

    def test_successful_source_archives_events(self, tmp_path):
        config = _make_config(html_parsing_available=True)
        manager = _make_manager(tmp_path, config=config)

        event = _sample_event()
        with patch.object(
            manager, "_get_html_parsing_events", return_value=[event]
        ):
            manager.get_civic_opportunities()

        # Verify archived
        archived = manager.archive.get_archived_events("city-testville", days_forward=365)
        assert len(archived) == 1
        assert archived[0]["title"] == "City Council Meeting"

    def test_archived_source_does_not_re_archive(self, tmp_path):
        config = _make_config(archive_enabled=True)
        manager = _make_manager(tmp_path, config=config)

        # Use a past date so it falls within get_archived_events window
        past_event = _sample_event(meeting_datetime="2026-04-05T18:00:00+00:00")
        manager.archive.archive_events(
            [past_event], "legistar_api", "city-testville", 0.8
        )

        events, source, metadata = manager.get_civic_opportunities()
        assert source == "archived"
        assert len(events) == 1

        # Verify no duplicate archiving — still just 1 event
        conn = sqlite3.connect(manager.archive.archive_path)
        count = conn.execute("SELECT COUNT(*) FROM civic_events").fetchone()[0]
        conn.close()
        assert count == 1

    def test_metadata_includes_vendor_independence(self, tmp_path):
        config = _make_config(html_parsing_available=True)
        manager = _make_manager(tmp_path, config=config)

        with patch.object(
            manager, "_get_html_parsing_events", return_value=[_sample_event()]
        ):
            _, _, metadata = manager.get_civic_opportunities()

        vi = metadata["vendor_independence"]
        assert vi["independence_score"] == 1.0
        assert vi["granicus_dependency"] is False

    def test_metadata_includes_timestamp(self, tmp_path):
        config = _make_config(html_parsing_available=True)
        manager = _make_manager(tmp_path, config=config)

        with patch.object(
            manager, "_get_html_parsing_events", return_value=[_sample_event()]
        ):
            _, _, metadata = manager.get_civic_opportunities()

        assert "timestamp" in metadata
        # Should be a parseable ISO timestamp
        parsed = datetime.fromisoformat(metadata["timestamp"])
        assert parsed.year == 2026


# ---------------------------------------------------------------------------
# Resilience report
# ---------------------------------------------------------------------------


class TestResilienceReport:
    def test_report_structure_and_jurisdiction(self, tmp_path):
        manager = _make_manager(
            tmp_path, civic_scraper_available=True, html_parsing_available=True
        )
        report = manager.generate_resilience_report()

        assert report["jurisdiction"] == "Testville"
        assert report["resilience_metrics"]["available_sources"] == 1  # 2 sources - 1
        assert report["vendor_risk_assessment"]["vendor_risk_level"] == "low"
        assert len(report["recommendations"]) >= 1
        # Timestamp should be parseable UTC
        ts = datetime.fromisoformat(report["assessment_timestamp"])
        assert ts.tzinfo == timezone.utc

    def test_available_sources_excludes_archive(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            civic_scraper_available=True,
            html_parsing_available=True,
            archive_enabled=True,
        )
        report = manager.generate_resilience_report()
        # 2 real sources (civic_scraper, html_parsing), archive excluded from count
        assert report["resilience_metrics"]["available_sources"] == 2

    def test_failover_capable_with_more_than_two_sources(self, tmp_path):
        manager = _make_manager(
            tmp_path,
            civic_scraper_available=True,
            html_parsing_available=True,
            archive_enabled=True,
        )
        report = manager.generate_resilience_report()
        # 3 entries in source_priority (civic_scraper, html_parsing, archived) → True
        assert report["resilience_metrics"]["failover_capable"] is True

    def test_not_failover_capable_with_two_or_fewer_sources(self, tmp_path):
        manager = _make_manager(tmp_path, html_parsing_available=True)
        report = manager.generate_resilience_report()
        assert report["resilience_metrics"]["failover_capable"] is False

    def test_empty_archive_stats(self, tmp_path):
        manager = _make_manager(tmp_path)
        report = manager.generate_resilience_report()
        sovereignty = report["resilience_metrics"]["data_sovereignty"]
        assert sovereignty["total_archived_events"] == 0
        assert sovereignty["unique_source_coverage"] == 0

    def test_populated_archive_reflected_in_report(self, tmp_path):
        manager = _make_manager(tmp_path, html_parsing_available=True)
        manager.archive.archive_events(
            [_sample_event(event_id="r1"), _sample_event(event_id="r2")],
            "html_parsing",
            "city-testville",
            0.8,
        )
        report = manager.generate_resilience_report()
        sovereignty = report["resilience_metrics"]["data_sovereignty"]
        assert sovereignty["total_archived_events"] == 2
        assert sovereignty["unique_source_coverage"] == 1


# ---------------------------------------------------------------------------
# Resilience recommendations
# ---------------------------------------------------------------------------


class TestResilienceRecommendations:
    def test_high_risk_produces_diversify_recommendation(self, tmp_path):
        """With only legistar, vendor risk is high → diversify recommendation."""
        config = _make_config(legistar_available=True, legistar_client_name="test")
        with patch(
            "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
        ) as MockArchive:
            MockArchive.return_value = _make_archive(tmp_path)
            with patch(
                "civicos_services.monitoring.unified_data_source_manager.LegistarClient"
            ) as MockLegistar:
                MockLegistar.return_value = MagicMock()
                manager = UnifiedDataSourceManager(config)
                manager.archive = MockArchive.return_value

        recs = manager._generate_resilience_recommendations({})
        assert any("Diversify" in r for r in recs)

    def test_empty_reliability_produces_baseline_recommendation(self, tmp_path):
        manager = _make_manager(tmp_path, html_parsing_available=True)
        recs = manager._generate_resilience_recommendations({})
        assert any("baseline" in r.lower() for r in recs)

    def test_no_cdp_produces_cdp_recommendation(self, tmp_path):
        manager = _make_manager(tmp_path, html_parsing_available=True)
        recs = manager._generate_resilience_recommendations(
            {"html_parsing": {"success_rate": 0.95}}
        )
        assert any("CDP" in r for r in recs)

    def test_few_working_sources_produces_redundancy_recommendation(self, tmp_path):
        manager = _make_manager(
            tmp_path, civic_scraper_available=True, html_parsing_available=True
        )
        # Only 1 source with success_rate > 0.8
        reliability = {"html_parsing": {"success_rate": 0.9}}
        recs = manager._generate_resilience_recommendations(reliability)
        assert any("redundancy" in r.lower() for r in recs)

    def test_excellent_posture_when_no_issues(self, tmp_path):
        """Multiple working sources + no CDP gap + not high risk → excellent."""
        manager = _make_manager(
            tmp_path, civic_scraper_available=True, html_parsing_available=True
        )
        # Give the manager a fake CDP client to suppress CDP recommendation
        manager.cdp_client = MagicMock()

        reliability = {
            "civic_scraper": {"success_rate": 0.95},
            "html_parsing": {"success_rate": 0.92},
        }
        recs = manager._generate_resilience_recommendations(reliability)
        assert any("Excellent" in r for r in recs)


# ---------------------------------------------------------------------------
# create_unified_manager factory
# ---------------------------------------------------------------------------


class TestCreateUnifiedManager:
    @patch(
        "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
    )
    @patch(
        "civicos_services.monitoring.unified_data_source_manager.LegistarClient"
    )
    def test_oakland_has_legistar_and_civic_scraper(
        self, MockLegistar, MockArchive, tmp_path
    ):
        MockLegistar.return_value = MagicMock()
        MockArchive.return_value = _make_archive(tmp_path)

        manager = create_unified_manager("oakland")
        assert manager is not None
        assert manager.config.jurisdiction_id == "city-oakland"
        assert manager.config.legistar_available is True
        assert manager.config.civic_scraper_available is True
        assert manager.config.html_parsing_available is True

    @patch(
        "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
    )
    def test_berkeley_has_no_legistar(self, MockArchive, tmp_path):
        MockArchive.return_value = _make_archive(tmp_path)

        manager = create_unified_manager("berkeley")
        assert manager is not None
        assert manager.config.jurisdiction_id == "city-berkeley"
        assert manager.config.legistar_available is False
        assert manager.config.cdp_available is False

    @patch(
        "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
    )
    def test_san_rafael_html_parsing_only(self, MockArchive, tmp_path):
        MockArchive.return_value = _make_archive(tmp_path)

        manager = create_unified_manager("san-rafael")
        assert manager is not None
        assert manager.config.jurisdiction_id == "city-san-rafael"
        assert manager.config.html_parsing_available is True
        assert manager.config.civic_scraper_available is False

    def test_unknown_jurisdiction_returns_none(self):
        result = create_unified_manager("atlantis")
        assert result is None

    @patch(
        "civicos_services.monitoring.unified_data_source_manager.CivicDataArchive"
    )
    def test_case_insensitive_lookup(self, MockArchive, tmp_path):
        MockArchive.return_value = _make_archive(tmp_path)
        manager = create_unified_manager("Berkeley")
        assert manager is not None
        assert manager.config.jurisdiction_name == "Berkeley"


# ---------------------------------------------------------------------------
# Placeholder source methods
# ---------------------------------------------------------------------------


class TestPlaceholderSources:
    def test_civic_scraper_returns_empty(self, tmp_path):
        manager = _make_manager(tmp_path, civic_scraper_available=True)
        events = manager._get_civic_scraper_events(14, 7)
        assert events == []

    def test_html_parsing_returns_empty(self, tmp_path):
        manager = _make_manager(tmp_path, html_parsing_available=True)
        events = manager._get_html_parsing_events(14, 7)
        assert events == []
