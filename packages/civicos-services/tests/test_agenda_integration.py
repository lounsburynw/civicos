"""
Tests for agenda_integration.py — agenda discovery, parsing, and enhancement pipeline.

Covers pure-logic methods (URL safety, JSON parsing, keyword extraction, freshness
validation, cancellation detection) and orchestration paths (discovery routing,
event enhancement) with mocked HTTP/LLM dependencies.

To run:
    pytest packages/civicos-services/tests/test_agenda_integration.py -q --override-ini="addopts="
"""

import json
import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from civicos_services.processing.agenda_integration import (
    AgendaIntegrator,
    AgendaItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def integrator():
    """Create AgendaIntegrator with mocked LLM provider (avoids real API calls)."""
    with patch(
        "civicos_services.processing.agenda_integration.AgendaIntegrator._init_structured_clients"
    ):
        with patch(
            "civicos_services.core.llm_provider.get_model_for_task"
        ) as mock_get:
            mock_provider = MagicMock()
            mock_provider.default_model = "test-model"
            mock_get.return_value = mock_provider
            ai = AgendaIntegrator()
            ai.legistar_clients = {}
            ai.civicclerk_jurisdictions = {
                "city-el-cerrito": "elcerritoca",
            }
    return ai


# ---------------------------------------------------------------------------
# AgendaItem dataclass defaults
# ---------------------------------------------------------------------------


class TestAgendaItemDefaults:
    def test_default_project_types_is_governance(self):
        item = AgendaItem(item_ref="1", title="Test")
        assert item.project_types == ["governance"]

    def test_default_lists_are_empty(self):
        item = AgendaItem(item_ref="1", title="Test")
        assert item.participation_mechanisms == []
        assert item.related_agenda_items == []
        assert item.addresses_issues == []
        assert item.policy_chain == []

    def test_explicit_values_not_overwritten(self):
        item = AgendaItem(
            item_ref="A",
            title="Housing Hearing",
            description="Desc",
            actionable=True,
            actionable_reason="Public hearing",
            project_types=["housing", "development"],
            participation_mechanisms=[{"type": "email"}],
            related_agenda_items=["B"],
            addresses_issues=["parking"],
            policy_chain=["GP-2030"],
        )
        assert item.project_types == ["housing", "development"]
        assert item.participation_mechanisms == [{"type": "email"}]
        assert item.related_agenda_items == ["B"]
        assert item.addresses_issues == ["parking"]
        assert item.policy_chain == ["GP-2030"]
        assert item.actionable is True
        assert item.actionable_reason == "Public hearing"

    def test_none_fields_get_defaults(self):
        item = AgendaItem(
            item_ref="1",
            title="Test",
            project_types=None,
            participation_mechanisms=None,
            related_agenda_items=None,
            addresses_issues=None,
            policy_chain=None,
        )
        assert item.project_types == ["governance"]
        assert item.participation_mechanisms == []

    def test_follows_from_default_is_none(self):
        item = AgendaItem(item_ref="1", title="Test")
        assert item.follows_from is None


# ---------------------------------------------------------------------------
# _is_safe_url
# ---------------------------------------------------------------------------


class TestIsSafeUrl:
    def test_https_url_is_safe(self, integrator):
        assert integrator._is_safe_url("https://example.gov/agenda") is True

    def test_http_url_is_safe(self, integrator):
        assert integrator._is_safe_url("http://example.gov/agenda") is True

    def test_ftp_url_is_unsafe(self, integrator):
        assert integrator._is_safe_url("ftp://files.example.gov/doc") is False

    def test_file_url_is_unsafe(self, integrator):
        assert integrator._is_safe_url("file:///etc/passwd") is False

    def test_javascript_url_is_unsafe(self, integrator):
        assert integrator._is_safe_url("javascript:alert(1)") is False

    def test_localhost_is_unsafe(self, integrator):
        assert integrator._is_safe_url("http://localhost:8080/api") is False

    def test_127_0_0_1_is_unsafe(self, integrator):
        assert integrator._is_safe_url("http://127.0.0.1/admin") is False

    def test_0_0_0_0_is_unsafe(self, integrator):
        assert integrator._is_safe_url("http://0.0.0.0:5000/") is False

    def test_private_192_168_is_unsafe(self, integrator):
        assert integrator._is_safe_url("http://192.168.1.1/config") is False

    def test_private_10_x_is_unsafe(self, integrator):
        assert integrator._is_safe_url("http://10.0.0.1/internal") is False

    def test_empty_string_is_unsafe(self, integrator):
        assert integrator._is_safe_url("") is False

    def test_garbage_string_is_unsafe(self, integrator):
        assert integrator._is_safe_url("not-a-url-at-all") is False


# ---------------------------------------------------------------------------
# _safe_json_parse
# ---------------------------------------------------------------------------


class TestSafeJsonParse:
    def test_valid_json_dict(self, integrator):
        result = integrator._safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced_json(self, integrator):
        text = '```json\n{"agenda_url": "https://example.gov/a.pdf", "available": true}\n```'
        result = integrator._safe_json_parse(text)
        assert result["agenda_url"] == "https://example.gov/a.pdf"
        assert result["available"] is True

    def test_whitespace_around_json(self, integrator):
        result = integrator._safe_json_parse('  \n {"x": 1} \n  ')
        assert result == {"x": 1}

    def test_non_dict_returns_none(self, integrator):
        assert integrator._safe_json_parse("[1, 2, 3]") is None

    def test_invalid_json_returns_none(self, integrator):
        assert integrator._safe_json_parse("not json at all") is None

    def test_empty_string_returns_none(self, integrator):
        assert integrator._safe_json_parse("") is None

    def test_long_string_values_truncated_to_2000(self, integrator):
        long_val = "x" * 3000
        text = json.dumps({"content": long_val})
        result = integrator._safe_json_parse(text)
        assert len(result["content"]) == 2000

    def test_short_string_values_not_truncated(self, integrator):
        text = json.dumps({"content": "short"})
        result = integrator._safe_json_parse(text)
        assert result["content"] == "short"

    def test_nested_dict_preserved(self, integrator):
        text = '{"items": [{"title": "Housing"}]}'
        result = integrator._safe_json_parse(text)
        assert result["items"][0]["title"] == "Housing"


# ---------------------------------------------------------------------------
# _get_meeting_keywords
# ---------------------------------------------------------------------------


class TestGetMeetingKeywords:
    def test_title_words_longer_than_3_chars(self, integrator):
        keywords = integrator._get_meeting_keywords("", "City Council Meeting")
        assert "city" in keywords
        assert "council" in keywords
        assert "meeting" in keywords

    def test_short_title_words_excluded(self, integrator):
        keywords = integrator._get_meeting_keywords("", "An OK Day")
        # "An", "OK", "Day" are all <=3 chars
        assert "an" not in keywords
        assert "ok" not in keywords
        assert "day" not in keywords

    def test_planning_commission_type_adds_keywords(self, integrator):
        keywords = integrator._get_meeting_keywords("planning_commission", "")
        assert "planning" in keywords
        assert "commission" in keywords

    def test_city_council_type_adds_keywords(self, integrator):
        keywords = integrator._get_meeting_keywords("city_council", "")
        assert "council" in keywords
        assert "city" in keywords

    def test_unknown_type_returns_only_title_words(self, integrator):
        keywords = integrator._get_meeting_keywords("unknown_type", "Budget Review")
        assert "budget" in keywords
        assert "review" in keywords
        # No type-specific keywords added
        assert "unknown_type" not in keywords

    def test_deduplicates_keywords(self, integrator):
        # "council" appears in both title and type keywords
        keywords = integrator._get_meeting_keywords("city_council", "City Council Session")
        assert keywords.count("council") == 1

    def test_empty_title_and_unknown_type(self, integrator):
        keywords = integrator._get_meeting_keywords("", "")
        assert keywords == []

    def test_zoning_administrator_adds_zoning(self, integrator):
        keywords = integrator._get_meeting_keywords("zoning_administrator", "")
        assert "zoning" in keywords


# ---------------------------------------------------------------------------
# _validate_agenda_freshness
# ---------------------------------------------------------------------------


class TestValidateAgendaFreshness:
    def test_recent_fy_not_stale(self, integrator):
        text = "FY 2025-26 Budget Appropriation"
        event = {"when": "2025-10-15T18:00:00Z"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False
        assert reason == ""

    def test_old_fy_flagged_as_stale(self, integrator):
        text = "FY 2020-21 Budget Review"
        event = {"when": "2025-10-15T18:00:00Z"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is True
        assert "FY 2020" in reason
        assert "5 years old" in reason

    def test_fy_exactly_2_years_old_not_stale(self, integrator):
        text = "FY 2023 appropriation"
        event = {"when": "2025-06-15T18:00:00Z"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_fy_3_years_old_is_stale(self, integrator):
        text = "FY 2022 budget"
        event = {"when": "2025-06-15T18:00:00Z"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is True
        assert "3 years old" in reason

    def test_old_month_year_header_flagged(self, integrator):
        # Regex expects "MONTH DAY, YEAR" format (day number required)
        text = "JUNE 15, 2020 REGULAR MEETING AGENDA\nItem 1: Approve Minutes"
        event = {"when": "2025-10-15T18:00:00Z"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is True
        assert "JUNE" in reason
        assert "2020" in reason

    def test_recent_month_year_header_not_stale(self, integrator):
        text = "OCTOBER 2025 PLANNING COMMISSION\nItem 1: Zone Change"
        event = {"when": "2025-10-15T18:00:00Z"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_no_date_in_event_returns_not_stale(self, integrator):
        text = "FY 2018 ancient budget"
        event = {"when": ""}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False

    def test_unparseable_event_date_returns_not_stale(self, integrator):
        text = "FY 2018 ancient budget"
        event = {"when": "not-a-date"}
        is_stale, reason = integrator._validate_agenda_freshness(text, event)
        assert is_stale is False


# ---------------------------------------------------------------------------
# _detect_cancellation
# ---------------------------------------------------------------------------


class TestDetectCancellation:
    def test_cancelled_in_header(self, integrator):
        text = "CANCELLED\nThe regular meeting has been cancelled due to lack of quorum."
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True
        assert "CANCELLED" in reason.upper() or "cancelled" in reason.lower()

    def test_canceled_american_spelling(self, integrator):
        text = "MEETING CANCELED\nNo business will be conducted."
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True

    def test_notice_of_cancellation(self, integrator):
        text = "NOTICE OF CANCELLATION\nThe Planning Commission meeting is cancelled."
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True
        assert "CANCELLATION" in reason.upper() or "cancelled" in reason.lower()

    def test_postponed_detected(self, integrator):
        text = "POSTPONED\nThis meeting has been postponed to November 5."
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True

    def test_rescheduled_detected(self, integrator):
        text = "RESCHEDULED\nThis meeting has been rescheduled to next Tuesday."
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True

    def test_no_meeting_detected(self, integrator):
        text = "NO MEETING\nThere will be no meeting this month."
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True

    def test_normal_agenda_not_cancelled(self, integrator):
        text = "REGULAR MEETING AGENDA\nCity Council\nOctober 15, 2025\n1. Call to Order"
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is False
        assert reason == ""

    def test_cancel_word_deep_in_text_not_detected(self, integrator):
        # Cancellation keywords only checked in first 1000 chars
        text = "REGULAR AGENDA\n" + ("x" * 1100) + "\nCANCELLED"
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is False

    def test_meeting_has_been_cancelled_pattern(self, integrator):
        text = "THE MEETING HAS BEEN CANCELLED DUE TO HOLIDAY"
        is_cancelled, reason = integrator._detect_cancellation(text, {})
        assert is_cancelled is True
        assert "HOLIDAY" in reason.upper()


# ---------------------------------------------------------------------------
# _try_structured_api_discovery — routing logic
# ---------------------------------------------------------------------------


class TestTryStructuredApiDiscovery:
    def test_legistar_metadata_takes_priority(self, integrator):
        event = {
            "source_url": "https://example.gov",
            "jurisdiction": {"id": "city-test"},
            "_legistar_metadata": {"id": "123"},
            "agenda_url": "https://legistar.gov/agenda.pdf",
        }
        url, available = integrator._try_structured_api_discovery(event)
        assert url == "https://legistar.gov/agenda.pdf"
        assert available is True

    def test_granicus_metadata_used_when_no_legistar(self, integrator):
        event = {
            "source_url": "https://example.gov",
            "jurisdiction": {"id": "city-test"},
            "_granicus_metadata": {"agenda_url": "https://granicus.gov/viewer/123"},
        }
        url, available = integrator._try_structured_api_discovery(event)
        assert url == "https://granicus.gov/viewer/123"
        assert available is True

    def test_no_metadata_returns_false(self, integrator):
        event = {
            "source_url": "https://example.gov",
            "jurisdiction": {"id": "city-unknown"},
        }
        url, available = integrator._try_structured_api_discovery(event)
        assert url is None
        assert available is False

    def test_legistar_source_url_pattern_triggers_discovery(self, integrator):
        event = {
            "source_url": "https://legistar.granicus.com/events/12345",
            "jurisdiction": {"id": "city-test"},
            "agenda_url": "https://legistar.granicus.com/agenda.pdf",
            "_legistar_metadata": {},
        }
        # _legistar_metadata is present but empty → falls through to source_url check
        # But actually empty dict is falsy, so it returns None, False from _discover_from_legistar_api
        # Then source_url check triggers _discover_from_legistar_api again
        # This time it tries event-level agenda_url
        url, available = integrator._try_structured_api_discovery(event)
        # Empty legistar_metadata → first try returns (None, False)
        # Then source_url pattern matches → tries again, still empty metadata → (None, False)
        assert available is False

    def test_civicclerk_metadata_routes_to_civicclerk_discovery(self, integrator):
        """When _civicclerk_metadata is present, _discover_from_civicclerk is called."""
        event = {
            "source_url": "https://example.gov",
            "jurisdiction": {"id": "city-el-cerrito"},
            "_civicclerk_metadata": {"id": "456"},
            "when": "2025-10-15T18:00:00Z",
            "title": "City Council",
        }
        # Mock the CivicClerk discovery to avoid real HTTP
        with patch.object(
            integrator, "_discover_from_civicclerk", return_value=("https://civicclerk.com/agenda.pdf", True)
        ) as mock_discover:
            url, available = integrator._try_structured_api_discovery(event)
        mock_discover.assert_called_once_with(event)
        assert url == "https://civicclerk.com/agenda.pdf"
        assert available is True

    def test_exception_returns_none_false(self, integrator):
        # Trigger an exception by passing None event
        url, available = integrator._try_structured_api_discovery(None)
        assert url is None
        assert available is False


# ---------------------------------------------------------------------------
# _discover_from_legistar_api
# ---------------------------------------------------------------------------


class TestDiscoverFromLegistarApi:
    def test_agenda_url_from_event_metadata(self, integrator):
        event = {
            "_legistar_metadata": {"event_id": 123},
            "agenda_url": "https://legistar.gov/agenda.pdf",
        }
        url, available = integrator._discover_from_legistar_api(event)
        assert url == "https://legistar.gov/agenda.pdf"
        assert available is True

    def test_agenda_url_from_agenda_expansion(self, integrator):
        event = {
            "_legistar_metadata": {"event_id": 123},
            "agenda_expansion": {"source_url": "https://legistar.gov/expansion.pdf"},
        }
        url, available = integrator._discover_from_legistar_api(event)
        assert url == "https://legistar.gov/expansion.pdf"
        assert available is True

    def test_no_agenda_url_anywhere(self, integrator):
        event = {"_legistar_metadata": {"event_id": 123}}
        url, available = integrator._discover_from_legistar_api(event)
        assert url is None
        assert available is False

    def test_empty_legistar_metadata_returns_false(self, integrator):
        event = {"_legistar_metadata": {}}
        url, available = integrator._discover_from_legistar_api(event)
        assert url is None
        assert available is False

    def test_event_agenda_url_takes_priority_over_expansion(self, integrator):
        event = {
            "_legistar_metadata": {"event_id": 123},
            "agenda_url": "https://legistar.gov/direct.pdf",
            "agenda_expansion": {"source_url": "https://legistar.gov/expansion.pdf"},
        }
        url, available = integrator._discover_from_legistar_api(event)
        assert url == "https://legistar.gov/direct.pdf"
        assert available is True


# ---------------------------------------------------------------------------
# _discover_from_granicus
# ---------------------------------------------------------------------------


class TestDiscoverFromGranicus:
    def test_agenda_url_from_metadata(self, integrator):
        event = {"_granicus_metadata": {"agenda_url": "https://granicus.gov/viewer"}}
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://granicus.gov/viewer"
        assert available is True

    def test_packet_url_fallback(self, integrator):
        event = {"_granicus_metadata": {"packet_url": "https://granicus.gov/packet.pdf"}}
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://granicus.gov/packet.pdf"
        assert available is True

    def test_top_level_agenda_url_fallback(self, integrator):
        event = {
            "_granicus_metadata": {"event_id": 1},  # no agenda_url or packet_url
            "agenda_url": "https://granicus.gov/top-level.pdf",
        }
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://granicus.gov/top-level.pdf"
        assert available is True

    def test_empty_metadata_returns_false(self, integrator):
        event = {"_granicus_metadata": {}}
        url, available = integrator._discover_from_granicus(event)
        assert url is None
        assert available is False

    def test_agenda_url_takes_priority_over_packet(self, integrator):
        event = {
            "_granicus_metadata": {
                "agenda_url": "https://granicus.gov/viewer",
                "packet_url": "https://granicus.gov/packet.pdf",
            }
        }
        url, available = integrator._discover_from_granicus(event)
        assert url == "https://granicus.gov/viewer"
        assert available is True


# ---------------------------------------------------------------------------
# discover_agenda_url — tiered orchestration
# ---------------------------------------------------------------------------


class TestDiscoverAgendaUrl:
    def test_structured_api_hit_skips_llm_and_pattern(self, integrator):
        event = {
            "source_url": "https://example.gov",
            "jurisdiction": {"id": "city-test"},
            "_legistar_metadata": {"id": "1"},
            "agenda_url": "https://legistar.gov/found.pdf",
        }
        url, available = integrator.discover_agenda_url(event)
        assert url == "https://legistar.gov/found.pdf"
        assert available is True

    def test_all_tiers_fail_returns_none_false(self, integrator):
        event = {
            "source_url": "",  # empty → LLM discovery won't try
            "jurisdiction": {"id": "city-nobody"},
        }
        url, available = integrator.discover_agenda_url(event)
        assert url is None
        assert available is False


# ---------------------------------------------------------------------------
# _try_llm_discovery
# ---------------------------------------------------------------------------


class TestTryLlmDiscovery:
    def test_no_source_url_returns_none(self, integrator):
        event = {"source_url": ""}
        url, available = integrator._try_llm_discovery(event)
        assert url is None
        assert available is False

    def test_unsafe_source_url_returns_none(self, integrator):
        event = {"source_url": "ftp://internal.server/agenda"}
        url, available = integrator._try_llm_discovery(event)
        assert url is None
        assert available is False


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class TestCostTracking:
    def test_initial_cost_is_zero(self, integrator):
        assert integrator.total_cost == 0.0
        assert integrator.total_tokens == 0

    def test_reset_cost_tracking(self, integrator):
        integrator._total_cost = 1.50
        integrator._total_tokens = 5000
        integrator.reset_cost_tracking()
        assert integrator.total_cost == 0.0
        assert integrator.total_tokens == 0

    def test_cost_accumulates(self, integrator):
        integrator._total_cost = 0.05
        integrator._total_cost += 0.10
        assert integrator.total_cost == pytest.approx(0.15, abs=1e-9)

    def test_token_count_accumulates(self, integrator):
        integrator._total_tokens = 100
        integrator._total_tokens += 200
        assert integrator.total_tokens == 300


# ---------------------------------------------------------------------------
# enhance_event_with_agenda
# ---------------------------------------------------------------------------


class TestEnhanceEventWithAgenda:
    def test_event_with_existing_agenda_url_skips_discovery(self, integrator):
        """When event already has agenda_url, discover_agenda_url is not called."""
        event = {
            "agenda_url": "https://example.gov/agenda.pdf",
            "agenda_available": True,
            "title": "Council Meeting",
        }
        # Mock parse_agenda_content to return empty (avoid real LLM call)
        with patch.object(integrator, "parse_agenda_content", return_value=[]):
            result = integrator.enhance_event_with_agenda(event)

        assert result["agenda_url"] == "https://example.gov/agenda.pdf"
        assert result["agenda_expansion"]["available"] is True
        assert result["agenda_expansion"]["source_url"] == "https://example.gov/agenda.pdf"
        assert result["agenda_expansion"]["actionable_items"] == []

    def test_event_without_agenda_url_triggers_discovery(self, integrator):
        event = {
            "source_url": "",
            "jurisdiction": {"id": "city-nobody"},
            "title": "Test",
        }
        result = integrator.enhance_event_with_agenda(event)
        assert result["agenda_url"] is None
        assert result["agenda_available"] is False
        assert result["agenda_expansion"]["available"] is False
        assert result["agenda_expansion"]["unavailable_reason"] == "No published agenda found"

    def test_cancellation_detected_sets_status(self, integrator):
        cancel_item = AgendaItem(
            item_ref="CANCELLATION_NOTICE",
            title="Meeting Cancelled",
            description="Cancelled due to holiday",
            actionable=False,
            actionable_reason="This meeting has been cancelled and will not occur",
        )
        event = {
            "agenda_url": "https://example.gov/cancel.pdf",
            "agenda_available": True,
            "title": "Council Meeting",
        }
        with patch.object(integrator, "parse_agenda_content", return_value=[cancel_item]):
            result = integrator.enhance_event_with_agenda(event)

        assert result["status"] == "cancelled"
        assert "CANCELLED" in result["engagement_info"].upper()
        cancel_notice = result["agenda_expansion"]["cancellation_notice"]
        assert cancel_notice["cancelled"] is True
        assert cancel_notice["reason"] == "Cancelled due to holiday"
        # Cancellation items should not appear in actionable_items
        assert result["agenda_expansion"]["actionable_items"] == []

    def test_actionable_items_populated(self, integrator):
        items = [
            AgendaItem(
                item_ref="5A",
                title="Housing Policy Update",
                description="Review housing element",
                actionable=True,
                actionable_reason="Public hearing on housing",
                project_types=["housing"],
            ),
            AgendaItem(
                item_ref="5B",
                title="Minutes Approval",
                description="Routine approval",
                actionable=False,
                actionable_reason="",
                project_types=["governance"],
            ),
        ]
        event = {
            "agenda_url": "https://example.gov/agenda.pdf",
            "agenda_available": True,
            "title": "Council Meeting",
        }
        with patch.object(integrator, "parse_agenda_content", return_value=items):
            result = integrator.enhance_event_with_agenda(event)

        actionable = result["agenda_expansion"]["actionable_items"]
        assert len(actionable) == 1
        assert actionable[0]["item_ref"] == "5A"
        assert actionable[0]["title"] == "Housing Policy Update"
        assert actionable[0]["project_types"] == ["housing"]
        assert actionable[0]["actionable"] is True

    def test_agenda_available_but_no_items_sets_parse_failure(self, integrator):
        event = {
            "agenda_url": "https://example.gov/agenda.pdf",
            "agenda_available": True,
            "title": "Council Meeting",
        }
        with patch.object(integrator, "parse_agenda_content", return_value=[]):
            result = integrator.enhance_event_with_agenda(event)

        assert result["agenda_expansion"]["parsed"] is False
        assert result["agenda_expansion"]["parse_failure_reason"] == "Agenda may be placeholder/not yet finalized"

    def test_original_event_not_mutated(self, integrator):
        event = {"source_url": "", "jurisdiction": {"id": "city-test"}, "title": "X"}
        original_keys = set(event.keys())
        integrator.enhance_event_with_agenda(event)
        # Original dict should not gain new keys
        assert set(event.keys()) == original_keys


# ---------------------------------------------------------------------------
# _extract_pdf_text
# ---------------------------------------------------------------------------


class TestExtractPdfText:
    @pytest.fixture(autouse=True)
    def _setup_mock_pypdf2(self):
        """Inject a fake PyPDF2 module so we can test PDF extraction logic."""
        fake_pypdf2 = types.ModuleType("PyPDF2")

        class FakePdfReader:
            def __init__(self, file_obj):
                self.pages = _FAKE_PAGES

        fake_pypdf2.PdfReader = FakePdfReader
        with patch.dict(sys.modules, {"PyPDF2": fake_pypdf2}):
            yield

    def test_consent_calendar_section_found(self, integrator):
        """When CONSENT CALENDAR exists, text starts near that section."""
        page1 = MagicMock()
        page1.extract_text.return_value = "Preamble and boilerplate\n" * 20
        page2 = MagicMock()
        page2.extract_text.return_value = "\nCONSENT CALENDAR\nItem 1: Approve minutes\nItem 2: Award contract"

        global _FAKE_PAGES
        _FAKE_PAGES = [page1, page2]

        result = integrator._extract_pdf_text(b"fake-pdf-bytes")
        assert "CONSENT CALENDAR" in result
        assert "Item 1: Approve minutes" in result

    def test_regular_calendar_section_found(self, integrator):
        page = MagicMock()
        page.extract_text.return_value = "Header stuff\nREGULAR CALENDAR\nItem A: Budget hearing"

        global _FAKE_PAGES
        _FAKE_PAGES = [page]

        result = integrator._extract_pdf_text(b"fake-pdf-bytes")
        assert "REGULAR CALENDAR" in result
        assert "Budget hearing" in result

    def test_no_calendar_section_returns_from_beginning(self, integrator):
        page = MagicMock()
        page.extract_text.return_value = "Simple agenda without calendar markers"

        global _FAKE_PAGES
        _FAKE_PAGES = [page]

        result = integrator._extract_pdf_text(b"fake-pdf-bytes")
        assert "Simple agenda without calendar markers" in result

    def test_both_calendars_starts_at_earlier_one(self, integrator):
        """When both CONSENT and REGULAR exist, start at the earlier one."""
        text = "Preamble\nCONSENT CALENDAR\nItem 1\nREGULAR CALENDAR\nItem 2"
        page = MagicMock()
        page.extract_text.return_value = text

        global _FAKE_PAGES
        _FAKE_PAGES = [page]

        result = integrator._extract_pdf_text(b"fake-pdf-bytes")
        # CONSENT appears first, so result should start near CONSENT
        assert "CONSENT CALENDAR" in result
        assert "REGULAR CALENDAR" in result


class TestExtractPdfTextNoPyPDF2:
    def test_pypdf2_not_available_returns_message(self, integrator):
        with patch.dict(sys.modules, {"PyPDF2": None}):
            result = integrator._extract_pdf_text(b"fake-pdf-bytes")
        assert "PyPDF2 not available" in result
        assert str(len(b"fake-pdf-bytes")) in result


# ---------------------------------------------------------------------------
# parse_agenda_content — project_type handling
# ---------------------------------------------------------------------------


class TestParseAgendaContentProjectTypes:
    def test_empty_agenda_url_returns_empty(self, integrator):
        result = integrator.parse_agenda_content("", {})
        assert result == []

    def test_none_agenda_url_returns_empty(self, integrator):
        result = integrator.parse_agenda_content(None, {})
        assert result == []

    def test_unsafe_agenda_url_returns_empty(self, integrator):
        result = integrator.parse_agenda_content("ftp://internal/agenda.pdf", {})
        assert result == []

    def test_string_project_type_converted_to_list(self, integrator):
        """Backward compatibility: string project_type becomes single-element list."""
        llm_response = json.dumps({
            "items": [{
                "item_ref": "1",
                "title": "Housing Hearing",
                "description": "Public hearing",
                "actionable": True,
                "actionable_reason": "Public can comment",
                "project_type": "housing",
            }]
        })

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.iter_content = MagicMock(return_value=[b"<html>agenda</html>"])
        mock_response.raise_for_status = MagicMock()

        with patch.object(integrator.session, "get", return_value=mock_response):
            with patch.object(integrator, "_call_llm", return_value=llm_response):
                with patch.object(integrator, "_detect_cancellation", return_value=(False, "")):
                    with patch.object(integrator, "_validate_agenda_freshness", return_value=(False, "")):
                        items = integrator.parse_agenda_content(
                            "https://example.gov/agenda.html",
                            {"title": "Test", "when_human": "Oct 15"},
                        )

        assert len(items) == 1
        assert items[0].project_types == ["housing"]

    def test_array_project_types_preserved(self, integrator):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "2",
                "title": "Climate Infrastructure",
                "description": "Green bonds",
                "actionable": True,
                "actionable_reason": "Budget vote",
                "project_types": ["environment", "budget"],
            }]
        })

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.iter_content = MagicMock(return_value=[b"<html>agenda</html>"])
        mock_response.raise_for_status = MagicMock()

        with patch.object(integrator.session, "get", return_value=mock_response):
            with patch.object(integrator, "_call_llm", return_value=llm_response):
                with patch.object(integrator, "_detect_cancellation", return_value=(False, "")):
                    with patch.object(integrator, "_validate_agenda_freshness", return_value=(False, "")):
                        items = integrator.parse_agenda_content(
                            "https://example.gov/agenda.html",
                            {"title": "Test", "when_human": "Oct 15"},
                        )

        assert len(items) == 1
        assert items[0].project_types == ["environment", "budget"]


# ---------------------------------------------------------------------------
# _try_pattern_fallback
# ---------------------------------------------------------------------------


class TestTryPatternFallback:
    def test_no_source_url_returns_none(self, integrator):
        event = {"source_url": ""}
        url, available = integrator._try_pattern_fallback(event)
        assert url is None
        assert available is False

    def test_unsafe_source_url_returns_none(self, integrator):
        event = {"source_url": "file:///etc/passwd"}
        url, available = integrator._try_pattern_fallback(event)
        assert url is None
        assert available is False
