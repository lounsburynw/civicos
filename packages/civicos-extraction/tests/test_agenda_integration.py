"""Tests for agenda integration processing module.

Tests the AgendaItem dataclass, AgendaIntegrator logic (URL safety, JSON parsing,
keyword extraction, freshness validation, cancellation detection, metadata-based
discovery), and the enhance_event_with_agenda orchestration pipeline.

External I/O (HTTP, LLM) is mocked; logic under test runs for real.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from civicos_extraction.processing.agenda_integration import (
    AgendaItem,
    AgendaIntegrator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_integrator(cost_calculator=None):
    """Create an AgendaIntegrator with a mock LLM provider."""
    provider = MagicMock()
    provider.default_model = "test-model"
    return AgendaIntegrator(provider=provider, cost_calculator=cost_calculator)


def _make_event(**overrides):
    """Build a minimal event dict, merging overrides."""
    base = {
        "title": "City Council Meeting",
        "when": "2025-10-15T18:30:00",
        "when_human": "October 15, 2025 6:30 PM",
        "source_url": "https://example.gov/meetings",
        "jurisdiction": {"id": "city-example"},
    }
    base.update(overrides)
    return base


# ===========================================================================
# AgendaItem dataclass
# ===========================================================================

class TestAgendaItem:

    def test_defaults_populated_on_init(self):
        item = AgendaItem(item_ref="1A", title="Approve minutes")
        assert item.participation_mechanisms == []
        assert item.project_types == ["governance"]
        assert item.related_agenda_items == []
        assert item.addresses_issues == []
        assert item.policy_chain == []

    def test_explicit_values_not_overwritten(self):
        item = AgendaItem(
            item_ref="2B",
            title="Housing",
            project_types=["housing", "development"],
            participation_mechanisms=[{"type": "email"}],
        )
        assert item.project_types == ["housing", "development"]
        assert item.participation_mechanisms == [{"type": "email"}]

    def test_actionable_defaults_false(self):
        item = AgendaItem(item_ref="3", title="Roll call")
        assert item.actionable is False
        assert item.actionable_reason == ""

    def test_description_defaults_empty(self):
        item = AgendaItem(item_ref="4", title="Budget hearing")
        assert item.description == ""

    def test_follows_from_defaults_none(self):
        item = AgendaItem(item_ref="5", title="Continued hearing")
        assert item.follows_from is None


# ===========================================================================
# AgendaIntegrator.__init__
# ===========================================================================

class TestAgendaIntegratorInit:

    def test_raises_on_none_provider(self):
        with pytest.raises(ValueError, match="requires a provider"):
            AgendaIntegrator(provider=None)

    def test_stores_injected_provider(self):
        provider = MagicMock()
        provider.default_model = "test-model"
        integrator = AgendaIntegrator(provider=provider)
        assert integrator.provider is provider

    def test_model_name_from_provider_default(self):
        integrator = _make_integrator()
        assert integrator._model_name == "test-model"

    def test_model_name_override(self):
        provider = MagicMock()
        provider.default_model = "default"
        integrator = AgendaIntegrator(provider=provider, model_name="custom-model")
        assert integrator._model_name == "custom-model"

    def test_cost_tracking_starts_at_zero(self):
        integrator = _make_integrator()
        assert integrator.total_cost == 0.0
        assert integrator.total_tokens == 0


# ===========================================================================
# _is_safe_url
# ===========================================================================

class TestIsSafeUrl:

    def test_allows_https(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("https://example.gov/agenda.pdf") is True

    def test_allows_http(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("http://example.gov/agenda.pdf") is True

    def test_blocks_ftp(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("ftp://files.gov/agenda.pdf") is False

    def test_blocks_file_scheme(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("file:///etc/passwd") is False

    def test_blocks_javascript_scheme(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("javascript:alert(1)") is False

    def test_blocks_localhost(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("http://localhost:8080/admin") is False

    def test_blocks_127_0_0_1(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("http://127.0.0.1/admin") is False

    def test_blocks_0_0_0_0(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("http://0.0.0.0/admin") is False

    def test_blocks_192_168_x(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("http://192.168.1.100/admin") is False

    def test_blocks_10_x(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("http://10.0.0.5/admin") is False

    def test_returns_false_on_empty_string(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("") is False

    def test_returns_false_on_garbage(self):
        integrator = _make_integrator()
        assert integrator._is_safe_url("not-a-url") is False


# ===========================================================================
# _safe_json_parse
# ===========================================================================

class TestSafeJsonParse:

    def test_parses_clean_json(self):
        integrator = _make_integrator()
        result = integrator._safe_json_parse('{"items": [{"title": "A"}]}')
        assert result is not None
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "A"

    def test_strips_markdown_code_fence(self):
        integrator = _make_integrator()
        raw = '```json\n{"items": [{"title": "B"}]}\n```'
        result = integrator._safe_json_parse(raw)
        assert result is not None
        assert result["items"][0]["title"] == "B"

    def test_strips_plain_code_fence(self):
        integrator = _make_integrator()
        raw = '```\n{"items": []}\n```'
        result = integrator._safe_json_parse(raw)
        assert result is not None
        assert result["items"] == []

    def test_adds_empty_items_when_key_missing(self):
        integrator = _make_integrator()
        result = integrator._safe_json_parse('{"agenda_url": "https://x.gov"}')
        assert result is not None
        assert result["items"] == []
        assert result["agenda_url"] == "https://x.gov"

    def test_returns_none_on_empty_string(self):
        integrator = _make_integrator()
        result = integrator._safe_json_parse("")
        assert result is None
        assert integrator._last_parse_error == "LLM returned empty response"

    def test_returns_none_on_whitespace_only(self):
        integrator = _make_integrator()
        result = integrator._safe_json_parse("   \n  ")
        assert result is None

    def test_returns_none_on_invalid_json(self):
        integrator = _make_integrator()
        result = integrator._safe_json_parse("{not valid json}")
        assert result is None
        assert "JSON decode error" in integrator._last_parse_error

    def test_returns_none_on_non_dict(self):
        integrator = _make_integrator()
        result = integrator._safe_json_parse("[1, 2, 3]")
        assert result is None
        assert "Expected dict" in integrator._last_parse_error

    def test_truncates_long_string_values(self):
        integrator = _make_integrator()
        long_val = "x" * 3000
        result = integrator._safe_json_parse(json.dumps({"items": [], "note": long_val}))
        assert result is not None
        assert len(result["note"]) == 2000

    def test_handles_extra_data_after_json(self):
        integrator = _make_integrator()
        raw = '{"items": [{"title": "C"}]}\nHere is my explanation...'
        result = integrator._safe_json_parse(raw)
        assert result is not None
        assert result["items"][0]["title"] == "C"

    def test_resets_last_parse_error_on_success(self):
        integrator = _make_integrator()
        # First a failure
        integrator._safe_json_parse("bad")
        assert integrator._last_parse_error is not None
        # Then success
        integrator._safe_json_parse('{"items": []}')
        assert integrator._last_parse_error is None


# ===========================================================================
# _get_meeting_keywords
# ===========================================================================

class TestGetMeetingKeywords:

    def test_planning_commission(self):
        integrator = _make_integrator()
        kw = integrator._get_meeting_keywords("planning_commission", "Planning Commission Special")
        assert "planning" in kw
        assert "commission" in kw
        assert "special" in kw  # len("special") > 3

    def test_city_council(self):
        integrator = _make_integrator()
        kw = integrator._get_meeting_keywords("city_council", "Regular Council Session")
        assert "council" in kw
        assert "city" in kw
        assert "regular" in kw
        assert "session" in kw

    def test_short_words_excluded(self):
        integrator = _make_integrator()
        kw = integrator._get_meeting_keywords("board", "The Big Test")
        # "The" and "Big" are <= 3 chars, "Test" is > 3 chars
        assert "the" not in kw
        assert "big" not in kw
        assert "test" in kw

    def test_unknown_meeting_type_uses_title_only(self):
        integrator = _make_integrator()
        kw = integrator._get_meeting_keywords("unknown_type", "Housing Review Board")
        assert "housing" in kw
        assert "review" in kw
        assert "board" in kw

    def test_empty_title_returns_type_keywords(self):
        integrator = _make_integrator()
        kw = integrator._get_meeting_keywords("advisory_committee", "")
        assert "committee" in kw
        assert "advisory" in kw

    def test_no_duplicates(self):
        integrator = _make_integrator()
        kw = integrator._get_meeting_keywords("city_council", "Council Meeting City")
        # "council" and "city" appear in both title and type_keywords
        assert kw.count("council") == 1
        assert kw.count("city") == 1


# ===========================================================================
# _validate_agenda_freshness
# ===========================================================================

class TestValidateAgendaFreshness:

    def test_not_stale_when_fiscal_year_matches(self):
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "FY 2025-26 Budget Summary"
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False
        assert reason == ""

    def test_stale_when_fiscal_year_is_old(self):
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "FY 2020 Revenue Report"
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is True
        assert "2020" in reason
        assert "5 years" in reason

    def test_stale_when_header_has_old_month_day_year(self):
        """Regex requires MONTH DAY, YEAR format (e.g. 'JUNE 15, 2020')."""
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "CITY COUNCIL REGULAR MEETING\nJUNE 15, 2020\nAgenda items below..."
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is True
        assert "JUNE" in reason
        assert "2020" in reason

    def test_not_stale_when_header_month_year_without_day(self):
        """Pattern requires a day number; 'JUNE 2020' alone should not trigger."""
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "CITY COUNCIL REGULAR MEETING\nJUNE 2020\nItems..."
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_not_stale_when_header_date_within_two_years(self):
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "MEETING AGENDA\nOCTOBER 2024\nItems..."
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_not_stale_without_date(self):
        integrator = _make_integrator()
        event = _make_event(when="")
        text = "FY 2019 ancient budget"
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False
        assert reason == ""

    def test_not_stale_with_unparseable_date(self):
        integrator = _make_integrator()
        event = _make_event(when="not-a-date")
        text = "FY 2019 old content"
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_boundary_two_years_old_not_stale(self):
        """FY exactly 2 years old should NOT be flagged."""
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "FY 2023 Budget Adopted"
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_boundary_three_years_old_is_stale(self):
        """FY 3 years old should be flagged."""
        integrator = _make_integrator()
        event = _make_event(when="2025-10-15T18:30:00")
        text = "FY 2022 Budget Adopted"
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is True
        assert "3 years" in reason


# ===========================================================================
# _detect_cancellation
# ===========================================================================

class TestDetectCancellation:

    def test_detects_cancelled(self):
        integrator = _make_integrator()
        text = "MEETING CANCELLED\nDue to lack of quorum"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True
        assert "CANCELLED" in reason.upper()

    def test_detects_canceled_american_spelling(self):
        integrator = _make_integrator()
        text = "CANCELED\nThe October meeting has been canceled."
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True

    def test_detects_notice_of_cancellation(self):
        integrator = _make_integrator()
        text = "NOTICE OF CANCELLATION\nPlanning Commission"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True
        assert "CANCELLATION" in reason.upper()

    def test_detects_postponed(self):
        integrator = _make_integrator()
        text = "POSTPONED\nThis meeting has been rescheduled to November."
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True

    def test_detects_rescheduled(self):
        integrator = _make_integrator()
        text = "RESCHEDULED\nNew date: November 5, 2025"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True

    def test_detects_no_meeting(self):
        integrator = _make_integrator()
        text = "NO MEETING\nDue to holiday schedule"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True

    def test_not_cancelled_for_normal_agenda(self):
        integrator = _make_integrator()
        text = "REGULAR MEETING AGENDA\n1. Call to Order\n2. Roll Call"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is False
        assert reason == ""

    def test_not_cancelled_when_cancelled_appears_deep_in_text(self):
        """Cancellation patterns only check first 1000 chars."""
        integrator = _make_integrator()
        # Pad with 1200 chars before the keyword
        text = "A" * 1200 + "\nMEETING CANCELLED"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is False

    def test_extracts_reason_context(self):
        integrator = _make_integrator()
        text = "MEETING HAS BEEN CANCELLED\nDue to inclement weather\nContact clerk for details"
        event = _make_event()
        is_cancelled, reason = integrator._detect_cancellation(text, event)
        assert is_cancelled is True
        assert "inclement weather" in reason.lower() or "CANCELLED" in reason.upper()


# ===========================================================================
# _discover_from_legistar_api
# ===========================================================================

class TestDiscoverFromLegistarApi:

    def test_returns_agenda_url_from_top_level(self):
        integrator = _make_integrator()
        event = {
            "_legistar_metadata": {"body_name": "Council"},
            "agenda_url": "https://legistar.gov/agenda/123",
        }
        url, available = integrator._discover_from_legistar_api(event)
        assert url == "https://legistar.gov/agenda/123"
        assert available is True

    def test_returns_url_from_agenda_expansion(self):
        integrator = _make_integrator()
        event = {
            "_legistar_metadata": {"body_name": "Council"},
            "agenda_expansion": {"source_url": "https://legistar.gov/agenda/456"},
        }
        url, available = integrator._discover_from_legistar_api(event)
        assert url == "https://legistar.gov/agenda/456"
        assert available is True

    def test_returns_none_when_metadata_empty(self):
        integrator = _make_integrator()
        event = {"_legistar_metadata": {}}
        url, available = integrator._discover_from_legistar_api(event)
        assert url is None
        assert available is False

    def test_returns_none_when_no_metadata_key(self):
        integrator = _make_integrator()
        event = {}
        url, available = integrator._discover_from_legistar_api(event)
        assert url is None
        assert available is False

    def test_prefers_top_level_over_expansion(self):
        integrator = _make_integrator()
        event = {
            "_legistar_metadata": {"body_name": "Council"},
            "agenda_url": "https://legistar.gov/top",
            "agenda_expansion": {"source_url": "https://legistar.gov/expansion"},
        }
        url, _ = integrator._discover_from_legistar_api(event)
        assert url == "https://legistar.gov/top"


# ===========================================================================
# _discover_from_granicus
# ===========================================================================

class TestDiscoverFromGranicus:

    def test_returns_agenda_url(self):
        integrator = _make_integrator()
        event = {
            "_granicus_metadata": {
                "agenda_url": "https://granicus.com/AgendaViewer/123",
            },
        }
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://granicus.com/AgendaViewer/123"
        assert available is True

    def test_falls_back_to_packet_url(self):
        integrator = _make_integrator()
        event = {
            "_granicus_metadata": {
                "packet_url": "https://granicus.com/packet.pdf",
            },
        }
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://granicus.com/packet.pdf"
        assert available is True

    def test_falls_back_to_top_level_agenda_url(self):
        integrator = _make_integrator()
        event = {
            "_granicus_metadata": {"clip_id": "999"},
            "agenda_url": "https://example.gov/agenda.pdf",
        }
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://example.gov/agenda.pdf"
        assert available is True

    def test_returns_none_when_metadata_empty(self):
        integrator = _make_integrator()
        event = {"_granicus_metadata": {}}
        url, available = integrator._discover_from_granicus(event)
        assert url is None
        assert available is False

    def test_prefers_agenda_url_over_packet_url(self):
        integrator = _make_integrator()
        event = {
            "_granicus_metadata": {
                "agenda_url": "https://granicus.com/viewer",
                "packet_url": "https://granicus.com/packet.pdf",
            },
        }
        url, _ = integrator._discover_from_granicus(event)
        assert url == "https://granicus.com/viewer"


# ===========================================================================
# _try_structured_api_discovery (routing)
# ===========================================================================

class TestTryStructuredApiDiscovery:

    def test_routes_to_legistar_on_metadata(self):
        integrator = _make_integrator()
        event = {
            "_legistar_metadata": {"body": "council"},
            "agenda_url": "https://legistar.gov/agenda/789",
            "source_url": "",
            "jurisdiction": {"id": "city-test"},
        }
        url, available = integrator._try_structured_api_discovery(event)
        assert url == "https://legistar.gov/agenda/789"
        assert available is True

    def test_routes_to_granicus_on_metadata(self):
        integrator = _make_integrator()
        event = {
            "_granicus_metadata": {"agenda_url": "https://gran.com/a"},
            "source_url": "",
            "jurisdiction": {"id": "city-test"},
        }
        url, available = integrator._try_structured_api_discovery(event)
        assert url == "https://gran.com/a"
        assert available is True

    def test_returns_none_for_unknown_event(self):
        integrator = _make_integrator()
        event = {
            "source_url": "https://random-site.com/events",
            "jurisdiction": {"id": "city-unknown"},
        }
        url, available = integrator._try_structured_api_discovery(event)
        assert url is None
        assert available is False

    def test_legistar_takes_priority_over_granicus(self):
        """When event has both metadata types, Legistar wins."""
        integrator = _make_integrator()
        event = {
            "_legistar_metadata": {"body": "council"},
            "_granicus_metadata": {"agenda_url": "https://gran.com/a"},
            "agenda_url": "https://legistar.gov/agenda/999",
            "source_url": "",
            "jurisdiction": {"id": "city-test"},
        }
        url, _ = integrator._try_structured_api_discovery(event)
        assert "legistar" in url


# ===========================================================================
# Cost tracking
# ===========================================================================

class TestCostTracking:

    def test_cost_accumulates(self):
        def calc(model, usage):
            return usage.get("total_tokens", 0) * 0.001
        integrator = _make_integrator(cost_calculator=calc)

        # Simulate a provider response
        mock_response = MagicMock()
        mock_response.content = '{"items": []}'
        mock_response.usage = {"total_tokens": 500}
        integrator.provider.complete.return_value = mock_response

        integrator._call_llm("test prompt")
        assert integrator.total_cost == pytest.approx(0.5)
        assert integrator.total_tokens == 500

    def test_cost_accumulates_across_calls(self):
        def calc(model, usage):
            return usage.get("total_tokens", 0) * 0.001
        integrator = _make_integrator(cost_calculator=calc)

        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.usage = {"total_tokens": 100}
        integrator.provider.complete.return_value = mock_response

        integrator._call_llm("prompt1")
        integrator._call_llm("prompt2")
        assert integrator.total_cost == pytest.approx(0.2)
        assert integrator.total_tokens == 200

    def test_reset_zeroes_counters(self):
        def calc(model, usage):
            return 1.0
        integrator = _make_integrator(cost_calculator=calc)

        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.usage = {"total_tokens": 50}
        integrator.provider.complete.return_value = mock_response

        integrator._call_llm("test")
        assert integrator.total_cost == 1.0
        assert integrator.total_tokens == 50

        integrator.reset_cost_tracking()
        assert integrator.total_cost == 0.0
        assert integrator.total_tokens == 0

    def test_no_cost_calculator_still_tracks_tokens(self):
        integrator = _make_integrator(cost_calculator=None)

        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.usage = {"total_tokens": 300}
        integrator.provider.complete.return_value = mock_response

        integrator._call_llm("prompt")
        assert integrator.total_cost == 0.0
        assert integrator.total_tokens == 300


# ===========================================================================
# _call_llm
# ===========================================================================

class TestCallLlm:

    def test_sends_system_and_user_messages(self):
        integrator = _make_integrator()
        mock_response = MagicMock()
        mock_response.content = "response text"
        mock_response.usage = {"total_tokens": 10}
        integrator.provider.complete.return_value = mock_response

        result = integrator._call_llm("analyze this")
        assert result == "response text"

        call_kwargs = integrator.provider.complete.call_args
        messages = call_kwargs.kwargs.get("messages", call_kwargs[1].get("messages"))
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "analyze this"

    def test_uses_zero_temperature(self):
        integrator = _make_integrator()
        mock_response = MagicMock()
        mock_response.content = "ok"
        mock_response.usage = {"total_tokens": 5}
        integrator.provider.complete.return_value = mock_response

        integrator._call_llm("prompt", max_tokens=500)
        call_kwargs = integrator.provider.complete.call_args
        assert call_kwargs.kwargs.get("temperature", call_kwargs[1].get("temperature")) == 0
        assert call_kwargs.kwargs.get("max_tokens", call_kwargs[1].get("max_tokens")) == 500

    def test_raises_on_provider_failure(self):
        integrator = _make_integrator()
        integrator.provider.complete.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError, match="API down"):
            integrator._call_llm("test")


# ===========================================================================
# enhance_event_with_agenda (orchestration)
# ===========================================================================

class TestEnhanceEventWithAgenda:

    def test_discovers_and_sets_agenda_url(self):
        integrator = _make_integrator()
        event = _make_event()

        # Mock the discovery and parse chain
        integrator.discover_agenda_url = MagicMock(
            return_value=("https://example.gov/agenda.pdf", True)
        )
        integrator.parse_agenda_content = MagicMock(return_value=[
            AgendaItem(item_ref="1", title="Housing Hearing", actionable=True,
                       actionable_reason="Public hearing")
        ])

        result = integrator.enhance_event_with_agenda(event)
        assert result["agenda_url"] == "https://example.gov/agenda.pdf"
        assert result["agenda_available"] is True
        assert result["agenda_expansion"]["available"] is True
        assert len(result["agenda_expansion"]["actionable_items"]) == 1
        assert result["agenda_expansion"]["actionable_items"][0]["title"] == "Housing Hearing"
        assert result["agenda_expansion"]["actionable_items"][0]["actionable_because"] == "Public hearing"

    def test_skips_discovery_when_agenda_url_present(self):
        integrator = _make_integrator()
        event = _make_event(agenda_url="https://preexisting.gov/agenda.pdf")

        integrator.discover_agenda_url = MagicMock()
        integrator.parse_agenda_content = MagicMock(return_value=[])

        result = integrator.enhance_event_with_agenda(event)

        # Should NOT call discover since agenda_url was already set
        integrator.discover_agenda_url.assert_not_called()
        assert result["agenda_url"] == "https://preexisting.gov/agenda.pdf"

    def test_handles_no_agenda_found(self):
        integrator = _make_integrator()
        event = _make_event()

        integrator.discover_agenda_url = MagicMock(return_value=(None, False))

        result = integrator.enhance_event_with_agenda(event)
        assert result["agenda_expansion"]["available"] is False
        assert result["agenda_expansion"]["unavailable_reason"] == "No published agenda found"
        assert result["agenda_expansion"]["actionable_items"] == []

    def test_cancellation_sets_status_and_engagement_info(self):
        integrator = _make_integrator()
        event = _make_event()

        integrator.discover_agenda_url = MagicMock(
            return_value=("https://example.gov/cancel.pdf", True)
        )
        integrator.parse_agenda_content = MagicMock(return_value=[
            AgendaItem(
                item_ref="CANCELLATION_NOTICE",
                title="Meeting Cancelled",
                description="Due to lack of quorum",
                actionable=False,
                actionable_reason="This meeting has been cancelled",
            )
        ])

        result = integrator.enhance_event_with_agenda(event)
        assert result["status"] == "cancelled"
        assert "CANCELLED" in result["engagement_info"]
        assert result["agenda_expansion"]["cancellation_notice"]["cancelled"] is True
        assert result["agenda_expansion"]["cancellation_notice"]["reason"] == "Due to lack of quorum"
        # Cancellation item should NOT appear in actionable_items
        assert result["agenda_expansion"]["actionable_items"] == []

    def test_non_actionable_items_excluded_from_expansion(self):
        integrator = _make_integrator()
        event = _make_event()

        integrator.discover_agenda_url = MagicMock(
            return_value=("https://example.gov/agenda.pdf", True)
        )
        integrator.parse_agenda_content = MagicMock(return_value=[
            AgendaItem(item_ref="1", title="Roll Call", actionable=False),
            AgendaItem(item_ref="2", title="Budget Vote", actionable=True,
                       actionable_reason="Public can comment"),
        ])

        result = integrator.enhance_event_with_agenda(event)
        items = result["agenda_expansion"]["actionable_items"]
        assert len(items) == 1
        assert items[0]["item_ref"] == "2"
        assert items[0]["title"] == "Budget Vote"

    def test_does_not_mutate_original_event(self):
        integrator = _make_integrator()
        event = _make_event()
        original_keys = set(event.keys())

        integrator.discover_agenda_url = MagicMock(return_value=(None, False))
        integrator.enhance_event_with_agenda(event)

        # Original event should not have new keys
        assert set(event.keys()) == original_keys

    def test_agenda_available_but_no_items_sets_parse_failure(self):
        integrator = _make_integrator()
        event = _make_event()

        integrator.discover_agenda_url = MagicMock(
            return_value=("https://example.gov/agenda.pdf", True)
        )
        integrator.parse_agenda_content = MagicMock(return_value=[])

        result = integrator.enhance_event_with_agenda(event)
        assert result["agenda_expansion"]["available"] is True
        assert result["agenda_expansion"]["parsed"] is False
        assert isinstance(result["agenda_expansion"]["parse_failure_reason"], str)
        assert len(result["agenda_expansion"]["parse_failure_reason"]) > 0


# ===========================================================================
# _extract_pdf_text
# ===========================================================================

class TestExtractPdfText:

    def test_skips_preamble_when_consent_calendar_found(self):
        """When CONSENT CALENDAR is found, text starts near that section."""
        integrator = _make_integrator()

        mock_page = MagicMock()
        preamble = "A" * 2000
        body = "CONSENT CALENDAR\n1. Approve Minutes\n2. Budget Report"
        mock_page.extract_text.return_value = preamble + body

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("civicos_extraction.processing.agenda_integration.PdfReader",
                    return_value=mock_reader, create=True):
            # Patch the dynamic import inside _extract_pdf_text
            import types
            fake_pypdf = types.ModuleType("pypdf")
            fake_pypdf.PdfReader = MagicMock(return_value=mock_reader)
            with patch.dict("sys.modules", {"pypdf": fake_pypdf}):
                result = integrator._extract_pdf_text(b"fake pdf bytes")
                # Text should start near CONSENT CALENDAR, not at the preamble start
                assert "CONSENT CALENDAR" in result
                assert "Approve Minutes" in result
                # Preamble should be mostly skipped (only ~500 chars before CONSENT kept)
                assert result.count("A" * 500) <= 1

    def test_returns_fallback_message_when_no_pdf_library(self):
        """When neither pypdf nor PyPDF2 is available, returns fallback text."""
        integrator = _make_integrator()
        content = b"fake pdf content"

        # Patch both pypdf and PyPDF2 to be unavailable
        with patch.dict("sys.modules", {"pypdf": None, "PyPDF2": None}):
            result = integrator._extract_pdf_text(content)
            assert "PyPDF2 not available" in result
            assert str(len(content)) in result  # Includes content length


# ===========================================================================
# parse_agenda_content — empty/null input guard
# ===========================================================================

class TestParseAgendaContentGuards:

    def test_returns_empty_list_for_none_url(self):
        integrator = _make_integrator()
        result = integrator.parse_agenda_content(None, _make_event())
        assert result == []

    def test_returns_empty_list_for_empty_url(self):
        integrator = _make_integrator()
        result = integrator.parse_agenda_content("", _make_event())
        assert result == []


# ===========================================================================
# discover_agenda_url (tier orchestration)
# ===========================================================================

class TestDiscoverAgendaUrl:

    def test_returns_tier1_when_found(self):
        integrator = _make_integrator()
        integrator._try_structured_api_discovery = MagicMock(
            return_value=("https://api.gov/agenda", True)
        )
        integrator._try_llm_discovery = MagicMock()
        integrator._try_pattern_fallback = MagicMock()

        url, available = integrator.discover_agenda_url(_make_event())
        assert url == "https://api.gov/agenda"
        assert available is True
        # LLM and pattern should not be called
        integrator._try_llm_discovery.assert_not_called()
        integrator._try_pattern_fallback.assert_not_called()

    def test_falls_through_to_tier2(self):
        integrator = _make_integrator()
        integrator._try_structured_api_discovery = MagicMock(
            return_value=(None, False)
        )
        integrator._try_llm_discovery = MagicMock(
            return_value=("https://llm-found.gov/agenda", True)
        )
        integrator._try_pattern_fallback = MagicMock()

        url, available = integrator.discover_agenda_url(_make_event())
        assert url == "https://llm-found.gov/agenda"
        assert available is True
        integrator._try_pattern_fallback.assert_not_called()

    def test_falls_through_to_tier3(self):
        integrator = _make_integrator()
        integrator._try_structured_api_discovery = MagicMock(
            return_value=(None, False)
        )
        integrator._try_llm_discovery = MagicMock(
            return_value=(None, False)
        )
        integrator._try_pattern_fallback = MagicMock(
            return_value=("https://pattern.gov/agenda.pdf", True)
        )

        url, available = integrator.discover_agenda_url(_make_event())
        assert url == "https://pattern.gov/agenda.pdf"
        assert available is True

    def test_returns_none_when_all_tiers_fail(self):
        integrator = _make_integrator()
        integrator._try_structured_api_discovery = MagicMock(
            return_value=(None, False)
        )
        integrator._try_llm_discovery = MagicMock(
            return_value=(None, False)
        )
        integrator._try_pattern_fallback = MagicMock(
            return_value=(None, False)
        )

        url, available = integrator.discover_agenda_url(_make_event())
        assert url is None
        assert available is False


# ===========================================================================
# Project-type handling in parse_agenda_content
# ===========================================================================

class TestProjectTypeNormalization:

    def _run_parse(self, integrator, items_data):
        """Helper: mock LLM + HTTP, call parse_agenda_content, return results."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({"items": items_data})
        mock_response.usage = {"total_tokens": 10}
        integrator.provider.complete.return_value = mock_response

        # Mock HTTP fetch for the agenda URL
        mock_http = MagicMock()
        mock_http.status_code = 200
        mock_http.headers = {"content-type": "text/html", "content-length": "100"}
        mock_http.iter_content = MagicMock(return_value=[b"<html>Agenda content</html>"])
        integrator.session.get = MagicMock(return_value=mock_http)

        return integrator.parse_agenda_content("https://example.gov/agenda.html", _make_event())

    def test_string_project_type_converted_to_list(self):
        integrator = _make_integrator()
        items = self._run_parse(integrator, [
            {"item_ref": "1", "title": "Housing", "actionable": True,
             "project_type": "housing"}
        ])
        assert len(items) == 1
        assert items[0].project_types == ["housing"]

    def test_list_project_types_preserved(self):
        integrator = _make_integrator()
        items = self._run_parse(integrator, [
            {"item_ref": "2", "title": "Dev", "actionable": True,
             "project_types": ["development", "budget"]}
        ])
        assert items[0].project_types == ["development", "budget"]

    def test_missing_project_type_defaults_to_governance(self):
        integrator = _make_integrator()
        items = self._run_parse(integrator, [
            {"item_ref": "3", "title": "Procedural", "actionable": False}
        ])
        assert items[0].project_types == ["governance"]

    def test_participation_mechanisms_enhanced_with_deadline(self):
        integrator = _make_integrator()
        event = _make_event(participation_mechanisms=[{"type": "email", "address": "clerk@gov"}])
        items_data = [
            {"item_ref": "4", "title": "Hearing", "actionable": True,
             "participation_deadline": "October 14, 2025",
             "public_comment_info": "Email clerk"}
        ]

        mock_response = MagicMock()
        mock_response.content = json.dumps({"items": items_data})
        mock_response.usage = {"total_tokens": 10}
        integrator.provider.complete.return_value = mock_response

        mock_http = MagicMock()
        mock_http.status_code = 200
        mock_http.headers = {"content-type": "text/html", "content-length": "100"}
        mock_http.iter_content = MagicMock(return_value=[b"<html>Agenda</html>"])
        integrator.session.get = MagicMock(return_value=mock_http)

        items = integrator.parse_agenda_content("https://example.gov/agenda.html", event)
        assert len(items) == 1
        assert items[0].participation_mechanisms[0]["deadline"] == "October 14, 2025"
        assert items[0].participation_mechanisms[0]["type"] == "email"
