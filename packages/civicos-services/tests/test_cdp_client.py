"""
Tests for cdp_client.py — Council Data Project integration client.

Tests pure-logic methods: text cleaning, datetime normalization, civic relevance
filtering, participation method extraction, comment deadline calculation,
data completeness scoring, cross-reference matching, and failover recommendation.
CDP database access is mocked; all normalization and filtering logic runs for real.

To run:
    pytest packages/civicos-services/tests/test_cdp_client.py -q --override-ini="addopts="
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from civicos_services.clients.cdp_client import (
    CDPClient,
    CDPJurisdictionConfig,
    KNOWN_CDP_JURISDICTIONS,
    create_cdp_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> CDPJurisdictionConfig:
    defaults = dict(
        jurisdiction_id="city-oakland",
        jurisdiction_name="Oakland",
        timezone="America/Los_Angeles",
        project_id=None,
    )
    defaults.update(overrides)
    return CDPJurisdictionConfig(**defaults)


def _make_client(**config_overrides) -> CDPClient:
    """Create a CDPClient with CDP imports disabled to skip Firestore init."""
    config = _make_config(**config_overrides)
    with patch("civicos_services.clients.cdp_client.CDP_AVAILABLE", False):
        client = CDPClient(config)
    return client


def _make_fake_event(**kwargs) -> SimpleNamespace:
    """Minimal mock CDP event with controllable attributes."""
    defaults = dict(
        id="evt_1",
        external_source_id="ext_1",
        event_datetime=None,
        body_ref=None,
        agenda_uri=None,
        minutes_uri=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# CDPJurisdictionConfig
# ---------------------------------------------------------------------------


class TestCDPJurisdictionConfig:
    def test_defaults(self):
        cfg = CDPJurisdictionConfig(
            jurisdiction_id="city-test",
            jurisdiction_name="Test",
            timezone="UTC",
        )
        assert cfg.cdp_endpoint is None
        assert cfg.project_id is None
        assert cfg.firestore_collection == "events"

    def test_custom_fields_preserved(self):
        cfg = CDPJurisdictionConfig(
            jurisdiction_id="city-x",
            jurisdiction_name="X",
            timezone="US/Eastern",
            project_id="cdp-x-abc123",
            firestore_collection="sessions",
        )
        assert cfg.project_id == "cdp-x-abc123"
        assert cfg.firestore_collection == "sessions"


# ---------------------------------------------------------------------------
# CDPClient.__init__
# ---------------------------------------------------------------------------


class TestCDPClientInit:
    def test_stores_config_fields(self):
        client = _make_client(
            jurisdiction_id="city-seattle",
            jurisdiction_name="Seattle",
            timezone="America/Los_Angeles",
        )
        assert client.jurisdiction_id == "city-seattle"
        assert client.jurisdiction_name == "Seattle"
        assert client.timezone == "America/Los_Angeles"

    def test_cdp_unavailable_sets_flag_false(self):
        client = _make_client()
        assert client.cdp_available is False
        assert client.connection is None

    def test_throttle_defaults(self):
        client = _make_client()
        assert client.last_request_time == 0
        assert client.min_request_interval == 0.2


# ---------------------------------------------------------------------------
# _clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_empty_and_none(self):
        client = _make_client()
        assert client._clean_text("") == ""
        assert client._clean_text(None) == ""

    def test_strips_whitespace(self):
        client = _make_client()
        assert client._clean_text("  hello  ") == "hello"

    def test_replaces_en_dash(self):
        client = _make_client()
        assert client._clean_text("Jan\u2013Feb") == "Jan-Feb"

    def test_replaces_em_dash(self):
        client = _make_client()
        assert client._clean_text("A\u2014B") == "A--B"

    def test_strips_html_tags(self):
        client = _make_client()
        assert client._clean_text("<b>Bold</b> text") == "Bold text"
        assert client._clean_text("<a href='x'>link</a>") == "link"

    def test_combined_cleaning(self):
        client = _make_client()
        result = client._clean_text("  <p>A\u2013B</p>  ")
        assert result == "A-B"


# ---------------------------------------------------------------------------
# _normalize_datetime
# ---------------------------------------------------------------------------


class TestNormalizeDatetime:
    def test_none_returns_empty(self):
        client = _make_client()
        assert client._normalize_datetime(None) == ""

    def test_empty_string_returns_empty(self):
        client = _make_client()
        assert client._normalize_datetime("") == ""

    def test_utc_z_suffix(self):
        client = _make_client()
        result = client._normalize_datetime("2025-06-15T10:00:00Z")
        assert result == "2025-06-15T10:00:00+00:00"

    def test_explicit_offset_preserved(self):
        client = _make_client()
        result = client._normalize_datetime("2025-06-15T10:00:00-07:00")
        assert result == "2025-06-15T10:00:00-07:00"

    def test_naive_datetime_gets_localized_when_pytz_available(self):
        """When pytz is importable, naive datetimes get jurisdiction tz applied."""
        import importlib
        pytz_spec = importlib.util.find_spec("pytz")
        if pytz_spec is None:
            pytest.skip("pytz not installed")
        client = _make_client(timezone="America/New_York")
        result = client._normalize_datetime("2025-06-15T10:00:00")
        # Eastern = -04:00 in summer (EDT)
        assert result == "2025-06-15T10:00:00-04:00"

    def test_naive_datetime_returns_empty_when_pytz_missing(self):
        """Without pytz, naive datetimes can't be localized → returns ''."""
        with patch.dict("sys.modules", {"pytz": None}):
            client = _make_client(timezone="America/New_York")
            result = client._normalize_datetime("2025-06-15T10:00:00")
            assert result == ""

    def test_invalid_string_returns_empty(self):
        client = _make_client()
        assert client._normalize_datetime("not-a-date") == ""


# ---------------------------------------------------------------------------
# _is_civic_relevant
# ---------------------------------------------------------------------------


class TestIsCivicRelevant:
    def test_city_council_is_relevant(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "City Council Meeting", "status": "scheduled"}) is True

    def test_planning_is_relevant(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "Planning Commission", "status": "scheduled"}) is True

    def test_budget_hearing_is_relevant(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "Budget Workshop", "status": "scheduled"}) is True

    def test_board_meeting_is_relevant(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "Board of Supervisors", "status": "scheduled"}) is True

    def test_cancelled_is_not_relevant(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "City Council Meeting", "status": "cancelled"}) is False

    def test_canceled_american_spelling_not_relevant(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "City Council Meeting", "status": "canceled"}) is False

    def test_irrelevant_title_excluded(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "Staff Retreat", "status": "scheduled"}) is False

    def test_empty_title_excluded(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "", "status": "scheduled"}) is False

    def test_keyword_case_insensitive(self):
        client = _make_client()
        assert client._is_civic_relevant({"title": "PUBLIC HEARING ON ZONING", "status": "scheduled"}) is True

    def test_missing_fields_treated_as_empty(self):
        client = _make_client()
        assert client._is_civic_relevant({}) is False


# ---------------------------------------------------------------------------
# _extract_participation_methods
# ---------------------------------------------------------------------------


class TestExtractParticipationMethods:
    def test_always_includes_public_comment_and_virtual(self):
        client = _make_client()
        event = _make_fake_event()
        methods = client._extract_participation_methods(event)
        assert "public_comment" in methods
        assert "virtual_attendance" in methods

    def test_with_agenda_uri_includes_agenda_review(self):
        client = _make_client()
        event = _make_fake_event(agenda_uri="https://example.com/agenda.pdf")
        methods = client._extract_participation_methods(event)
        assert "agenda_review" in methods
        assert len(methods) == 3

    def test_without_agenda_uri_excludes_agenda_review(self):
        client = _make_client()
        event = _make_fake_event(agenda_uri=None)
        methods = client._extract_participation_methods(event)
        assert "agenda_review" not in methods
        assert len(methods) == 2


# ---------------------------------------------------------------------------
# _extract_comment_deadline
# ---------------------------------------------------------------------------


class TestExtractCommentDeadline:
    def test_returns_none_when_no_datetime(self):
        client = _make_client()
        event = _make_fake_event(event_datetime=None)
        assert client._extract_comment_deadline(event) is None

    def test_datetime_object_minus_24h(self):
        client = _make_client()
        meeting_dt = datetime(2025, 8, 10, 18, 0, 0, tzinfo=timezone.utc)
        event = _make_fake_event(event_datetime=meeting_dt)
        deadline = client._extract_comment_deadline(event)
        expected = (meeting_dt - timedelta(hours=24)).isoformat()
        assert deadline == expected

    def test_string_datetime_minus_24h(self):
        client = _make_client()
        event = _make_fake_event(event_datetime="2025-08-10T18:00:00Z")
        deadline = client._extract_comment_deadline(event)
        assert deadline == "2025-08-09T18:00:00+00:00"

    def test_string_without_z(self):
        client = _make_client()
        event = _make_fake_event(event_datetime="2025-08-10T18:00:00+00:00")
        deadline = client._extract_comment_deadline(event)
        assert deadline == "2025-08-09T18:00:00+00:00"


# ---------------------------------------------------------------------------
# _assess_data_completeness
# ---------------------------------------------------------------------------


class TestAssessDataCompleteness:
    def test_empty_events_returns_zero_score(self):
        client = _make_client()
        result = client._assess_data_completeness([])
        assert result["score"] == 0.0
        assert "no_events_available" in result["issues"]

    def test_fully_complete_event_scores_high(self):
        client = _make_client()
        event = {
            "title": "City Council",
            "meeting_datetime": "2025-08-10T18:00:00Z",
            "status": "scheduled",
            "agenda_uri": "https://example.com/agenda.pdf",
            "location": "City Hall",
            "video_uri": "https://youtube.com/watch?v=abc",
        }
        result = client._assess_data_completeness([event])
        assert result["score"] == 1.0
        assert result["total_events"] == 1

    def test_only_required_fields_scores_0_7(self):
        client = _make_client()
        event = {
            "title": "Meeting",
            "meeting_datetime": "2025-08-10T18:00:00Z",
            "status": "scheduled",
        }
        result = client._assess_data_completeness([event])
        assert result["score"] == 0.7

    def test_partial_fields_scores_between(self):
        client = _make_client()
        event = {
            "title": "Meeting",
            "meeting_datetime": "2025-08-10T18:00:00Z",
            "status": "scheduled",
            "agenda_uri": "https://example.com/agenda.pdf",
            # location and video_uri missing
        }
        result = client._assess_data_completeness([event])
        # 0.7 (all required) + 0.1 (1 of 3 optional)
        assert result["score"] == 0.8

    def test_multiple_events_averaged(self):
        client = _make_client()
        full = {
            "title": "A",
            "meeting_datetime": "2025-08-10",
            "status": "x",
            "agenda_uri": "y",
            "location": "z",
            "video_uri": "v",
        }
        empty = {}
        result = client._assess_data_completeness([full, empty])
        # (1.0 + 0.0) / 2 = 0.5
        assert result["score"] == 0.5
        assert result["total_events"] == 2


# ---------------------------------------------------------------------------
# _find_cross_references
# ---------------------------------------------------------------------------


class TestFindCrossReferences:
    def test_empty_lists_return_zero_matches(self):
        client = _make_client()
        result = client._find_cross_references([], [])
        assert result["total_matches"] == 0
        assert result["match_rate"] == 0.0

    def test_matching_title_and_date(self):
        client = _make_client()
        cdp = [{"title": "City Council Meeting", "meeting_datetime": "2025-08-10T18:00:00"}]
        leg = [{"title": "City Council Regular Session", "meeting_datetime": "2025-08-10T19:00:00", "date": "2025-08-10"}]
        result = client._find_cross_references(cdp, leg)
        assert result["total_matches"] == 1
        assert result["matches"][0]["date"] == "2025-08-10"
        assert result["matches"][0]["confidence"] == 0.8

    def test_same_title_different_date_no_match(self):
        client = _make_client()
        cdp = [{"title": "City Council Meeting", "meeting_datetime": "2025-08-10T18:00:00"}]
        leg = [{"title": "City Council Meeting", "date": "2025-08-11"}]
        result = client._find_cross_references(cdp, leg)
        assert result["total_matches"] == 0

    def test_same_date_unrelated_title_no_match(self):
        client = _make_client()
        cdp = [{"title": "City Council Meeting", "meeting_datetime": "2025-08-10T18:00:00"}]
        leg = [{"title": "Staff Retreat", "date": "2025-08-10"}]
        result = client._find_cross_references(cdp, leg)
        assert result["total_matches"] == 0

    def test_match_rate_calculated_from_larger_list(self):
        client = _make_client()
        cdp = [
            {"title": "Planning Commission", "meeting_datetime": "2025-08-10T18:00:00"},
            {"title": "City Council Meeting", "meeting_datetime": "2025-08-11T18:00:00"},
        ]
        leg = [{"title": "Planning Commission Hearing", "date": "2025-08-10"}]
        result = client._find_cross_references(cdp, leg)
        assert result["total_matches"] == 1
        # match_rate = 1 / max(2, 1) = 0.5
        assert result["match_rate"] == 0.5

    def test_short_words_excluded_from_title_matching(self):
        """Words with len <= 3 are not used for title similarity."""
        client = _make_client()
        cdp = [{"title": "The A B C", "meeting_datetime": "2025-08-10T18:00:00"}]
        leg = [{"title": "The A B C meeting", "date": "2025-08-10"}]
        result = client._find_cross_references(cdp, leg)
        # All words in cdp title are <= 3 chars, so title_similar = False
        assert result["total_matches"] == 0

    def test_results_capped_at_five(self):
        client = _make_client()
        cdp = [
            {"title": f"Council Meeting {i}", "meeting_datetime": "2025-08-10T18:00:00"}
            for i in range(10)
        ]
        leg = [{"title": "Council Meeting General", "date": "2025-08-10"}]
        result = client._find_cross_references(cdp, leg)
        assert len(result["matches"]) <= 5


# ---------------------------------------------------------------------------
# _recommend_failover_strategy
# ---------------------------------------------------------------------------


class TestRecommendFailoverStrategy:
    def test_cdp_higher_quality_becomes_primary(self):
        client = _make_client()
        cdp_events = [
            {"title": "A", "meeting_datetime": "2025-08-10", "status": "x", "agenda_uri": "y", "location": "z", "video_uri": "v"},
        ]
        leg_events = [{"title": "B"}]
        result = client._recommend_failover_strategy(cdp_events, leg_events)
        assert result["primary"] == "cdp"
        assert result["fallback"] == "legistar_api"

    def test_legistar_decent_quality_becomes_primary(self):
        client = _make_client()
        cdp_events = [{"title": "A"}]  # Low quality
        leg_events = [
            {"title": "B", "meeting_datetime": "2025-08-10", "status": "scheduled", "agenda_uri": "y"},
        ]
        result = client._recommend_failover_strategy(cdp_events, leg_events)
        assert result["primary"] == "legistar_api"
        assert result["fallback"] == "cdp"

    def test_both_low_quality_falls_back_to_html(self):
        client = _make_client()
        result = client._recommend_failover_strategy([], [])
        assert result["primary"] == "html_parsing"
        assert result["fallback"] == "user_contributions"

    def test_equal_quality_legistar_wins_when_above_threshold(self):
        """When cdp == legistar and both > 0.5, legistar wins because
        the first branch requires cdp > legistar (strict)."""
        client = _make_client()
        event = {"title": "A", "meeting_datetime": "2025-08-10", "status": "x", "agenda_uri": "y"}
        result = client._recommend_failover_strategy([event], [event])
        # cdp_quality == leg_quality, first branch (cdp > leg) is False
        # second branch checks leg > 0.5 → True
        assert result["primary"] == "legistar_api"


# ---------------------------------------------------------------------------
# normalize_to_civic_schema
# ---------------------------------------------------------------------------


class TestNormalizeToCivicSchema:
    def test_empty_list_returns_empty(self):
        client = _make_client()
        assert client.normalize_to_civic_schema([]) == []

    def test_event_with_relevant_body_name_included(self):
        client = _make_client()
        event = _make_fake_event(
            id="evt_42",
            event_datetime=datetime(2025, 8, 10, 18, 0, tzinfo=timezone.utc),
            agenda_uri="https://example.com/agenda.pdf",
            minutes_uri="https://example.com/minutes.pdf",
        )
        # Simulate body_ref that returns a body with .name
        body_obj = SimpleNamespace(name="City Council Meeting")
        event.body_ref = SimpleNamespace(get=lambda: body_obj)

        result = client.normalize_to_civic_schema([event])
        assert len(result) == 1
        normalized = result[0]
        assert normalized["id"] == "evt_42"
        assert normalized["title"] == "City Council Meeting"
        assert normalized["jurisdiction"] == "Oakland"
        assert normalized["agenda_uri"] == "https://example.com/agenda.pdf"
        assert normalized["minutes_uri"] == "https://example.com/minutes.pdf"
        assert normalized["source_platform"] == "cdp"
        assert normalized["data_source"] == "cdp_city-oakland"
        assert normalized["public_comment_allowed"] is True

    def test_event_without_body_ref_uses_default_title(self):
        client = _make_client()
        # "Unknown Meeting" should be filtered out by _is_civic_relevant
        event = _make_fake_event(
            id="evt_99",
            event_datetime=datetime(2025, 8, 10, 18, 0, tzinfo=timezone.utc),
        )
        result = client.normalize_to_civic_schema([event])
        # "Unknown Meeting" doesn't match any civic keyword → filtered out
        assert len(result) == 0

    def test_irrelevant_body_name_filtered_out(self):
        client = _make_client()
        event = _make_fake_event(
            id="evt_7",
            event_datetime=datetime(2025, 8, 10, 18, 0, tzinfo=timezone.utc),
        )
        body_obj = SimpleNamespace(name="Internal Staff Retreat")
        event.body_ref = SimpleNamespace(get=lambda: body_obj)

        result = client.normalize_to_civic_schema([event])
        assert len(result) == 0

    def test_body_ref_access_failure_uses_default(self):
        """If body_ref.get() raises, falls back to 'Unknown Meeting'."""
        client = _make_client()
        event = _make_fake_event(
            id="evt_10",
            event_datetime=datetime(2025, 8, 10, 18, 0, tzinfo=timezone.utc),
        )

        def explode():
            raise RuntimeError("Firestore offline")

        event.body_ref = SimpleNamespace(get=explode)
        result = client.normalize_to_civic_schema([event])
        # "Unknown Meeting" isn't civic-relevant → filtered out
        assert len(result) == 0

    def test_id_falls_back_to_external_source_id(self):
        client = _make_client()
        event = _make_fake_event(
            id="",
            external_source_id="ext_abc",
            event_datetime=datetime(2025, 8, 10, 18, 0, tzinfo=timezone.utc),
        )
        body_obj = SimpleNamespace(name="Public Hearing on Rezoning")
        event.body_ref = SimpleNamespace(get=lambda: body_obj)

        result = client.normalize_to_civic_schema([event])
        assert len(result) == 1
        assert result[0]["id"] == "ext_abc"

    def test_participation_methods_and_deadline_populated(self):
        client = _make_client()
        meeting_dt = datetime(2025, 8, 10, 18, 0, tzinfo=timezone.utc)
        event = _make_fake_event(
            id="evt_55",
            event_datetime=meeting_dt,
            agenda_uri="https://example.com/agenda.pdf",
        )
        body_obj = SimpleNamespace(name="Planning Commission")
        event.body_ref = SimpleNamespace(get=lambda: body_obj)

        result = client.normalize_to_civic_schema([event])
        assert len(result) == 1
        assert "public_comment" in result[0]["participation_methods"]
        assert "agenda_review" in result[0]["participation_methods"]
        expected_deadline = (meeting_dt - timedelta(hours=24)).isoformat()
        assert result[0]["comment_deadline"] == expected_deadline


# ---------------------------------------------------------------------------
# get_civic_events (integration boundary)
# ---------------------------------------------------------------------------


class TestGetCivicEvents:
    def test_cdp_unavailable_returns_empty(self):
        """When CDP libs aren't installed, fallback returns []."""
        client = _make_client()
        assert client.cdp_available is False
        result = client.get_civic_events()
        assert result == []

    def test_no_connection_returns_empty(self):
        """When CDP is 'available' but no connection was established."""
        client = _make_client()
        # Manually set cdp_available without a real connection
        client.cdp_available = True
        client.connection = None
        result = client.get_civic_events()
        assert result == []


# ---------------------------------------------------------------------------
# create_cdp_client (factory function)
# ---------------------------------------------------------------------------


class TestCreateCdpClient:
    def test_known_jurisdiction_returns_client(self):
        with patch("civicos_services.clients.cdp_client.CDP_AVAILABLE", False):
            client = create_cdp_client("oakland")
        assert client.jurisdiction_name == "Oakland"
        assert client.jurisdiction_id == "city-oakland"

    def test_case_insensitive_lookup(self):
        with patch("civicos_services.clients.cdp_client.CDP_AVAILABLE", False):
            client = create_cdp_client("OAKLAND")
        assert client.jurisdiction_name == "Oakland"

    def test_unknown_jurisdiction_returns_none(self):
        result = create_cdp_client("atlantis")
        assert result is None

    def test_seattle_config(self):
        with patch("civicos_services.clients.cdp_client.CDP_AVAILABLE", False):
            client = create_cdp_client("seattle")
        assert client.jurisdiction_id == "city-seattle"
        assert client.timezone == "America/Los_Angeles"


# ---------------------------------------------------------------------------
# KNOWN_CDP_JURISDICTIONS registry
# ---------------------------------------------------------------------------


class TestKnownJurisdictions:
    def test_oakland_config_fields(self):
        cfg = KNOWN_CDP_JURISDICTIONS["oakland"]
        assert cfg.jurisdiction_id == "city-oakland"
        assert cfg.project_id == "cdp-oakland-ba81c097"
        assert cfg.timezone == "America/Los_Angeles"

    def test_seattle_config_fields(self):
        cfg = KNOWN_CDP_JURISDICTIONS["seattle"]
        assert cfg.jurisdiction_id == "city-seattle"
        assert cfg.project_id == "cdp-seattle-21723dcf"

    def test_san_jose_config_fields(self):
        cfg = KNOWN_CDP_JURISDICTIONS["san-jose"]
        assert cfg.jurisdiction_id == "city-san-jose"
        assert cfg.jurisdiction_name == "San Jose"

    def test_registry_has_three_entries(self):
        assert len(KNOWN_CDP_JURISDICTIONS) == 3


# ---------------------------------------------------------------------------
# _throttle_request
# ---------------------------------------------------------------------------


class TestThrottleRequest:
    def test_first_call_does_not_sleep(self):
        client = _make_client()
        client.last_request_time = 0
        with patch("civicos_services.clients.cdp_client.time.sleep") as mock_sleep:
            client._throttle_request()
            mock_sleep.assert_not_called()
        # last_request_time should be updated
        assert client.last_request_time > 0

    def test_rapid_call_triggers_sleep(self):
        client = _make_client()
        import time as _time
        client.last_request_time = _time.time()  # Just now
        with patch("civicos_services.clients.cdp_client.time.sleep") as mock_sleep:
            client._throttle_request()
            mock_sleep.assert_called_once_with(0.2)
        # Verify last_request_time was updated after throttle
        assert client.last_request_time > 0


# ---------------------------------------------------------------------------
# validate_against_legistar (integration boundary)
# ---------------------------------------------------------------------------


class TestValidateAgainstLegistar:
    def test_both_empty_sources(self):
        client = _make_client()
        result = client.validate_against_legistar([])
        assert result["jurisdiction"] == "Oakland"
        assert result["cdp_events_count"] == 0
        assert result["legistar_events_count"] == 0
        assert result["data_sources"]["cdp_available"] is False
        assert result["data_sources"]["legistar_available"] is False
        assert result["data_sources"]["dual_source_capable"] is False
        assert result["failover_recommendation"]["primary"] == "html_parsing"
        assert "timestamp" in result

    def test_legistar_only(self):
        client = _make_client()
        leg_events = [
            {"title": "Council", "meeting_datetime": "2025-08-10", "status": "scheduled", "date": "2025-08-10"},
        ]
        result = client.validate_against_legistar(leg_events)
        assert result["legistar_events_count"] == 1
        assert result["data_sources"]["legistar_available"] is True
        assert result["quality_metrics"]["legistar_completeness"]["total_events"] == 1
