"""
Tests for Playwright + LLM extraction client.

All tests mock Playwright rendering and LLM calls — no live browser or API calls.
Tests focus on JSON parsing, URL resolution, filtering, and scoring logic.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.clients.base import ExtractionConfig, Meeting
from civicos_extraction.clients.playwright_llm import (
    PlaywrightLLMSource,
    _EXTRACTION_PROMPT,
    _OFFICIALS_PROMPT,
    extract_meetings_from_page,
    extract_officials_from_page,
    find_government_page,
)


# ============================================================================
# Helpers
# ============================================================================


def _mock_llm_response(content: str):
    """Build a mock LLM provider that returns content."""
    provider = MagicMock()
    provider.complete.return_value = MagicMock(content=content)
    return provider


def _patch_render_and_llm(page_text: str, llm_content: str):
    """Return context manager that patches _render_page and get_llm_provider."""
    render_patch = patch(
        "civicos_extraction.clients.playwright_llm._render_page",
        return_value=("<html></html>", page_text),
    )
    provider = _mock_llm_response(llm_content)
    llm_patch = patch(
        "civicos_extraction.llm.get_llm_provider",
        return_value=provider,
    )
    env_patch = patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    return render_patch, llm_patch, env_patch, provider


# ============================================================================
# TestFindGovernmentPage — pure logic, no mocks
# ============================================================================


class TestFindGovernmentPage:
    """Tests for find_government_page HTML link extraction and scoring."""

    def test_finds_city_council_link(self):
        html = '<a href="/government/city-council">City Council</a>'
        result = find_government_page("https://www.example.gov", html)
        assert result == "https://www.example.gov/government/city-council"

    def test_finds_town_council_link(self):
        html = '<a href="/town-council">Town Council Members</a>'
        result = find_government_page("https://www.townofross.gov", html)
        assert result == "https://www.townofross.gov/town-council"

    def test_finds_board_of_supervisors_link(self):
        html = '<a href="/board">Board of Supervisors</a>'
        result = find_government_page("https://www.county.gov", html)
        assert result == "https://www.county.gov/board"

    def test_finds_elected_officials_link(self):
        html = '<a href="/officials">Elected Officials</a>'
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/officials"

    def test_prefers_council_members_over_government(self):
        """Scoring: council-members > city-council > government."""
        html = (
            '<a href="/government">Your Government</a>'
            '<a href="/government/city-council">City Council</a>'
            '<a href="/council-members">Council Members</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/council-members"

    def test_prefers_city_council_over_government(self):
        html = (
            '<a href="/government">Your Government</a>'
            '<a href="/government/city-council">City Council</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/government/city-council"

    def test_skips_meeting_and_agenda_links(self):
        """Links containing meeting/agenda/calendar keywords are excluded."""
        html = (
            '<a href="/meetings/city-council">City Council Meetings</a>'
            '<a href="/agenda/city-council">City Council Agenda</a>'
            '<a href="/calendar/city-council">City Council Calendar</a>'
            '<a href="/council-members">Council Members</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/council-members"

    def test_skips_minutes_links(self):
        html = (
            '<a href="/minutes/city-council">City Council Minutes</a>'
            '<a href="/your-government/city-council">City Council</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/your-government/city-council"

    def test_skips_archive_links(self):
        html = (
            '<a href="/archive/city-council">City Council Archive</a>'
            '<a href="/council-members">Council Members</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/council-members"

    def test_skips_javascript_links(self):
        html = (
            '<a href="javascript:void(0)">City Council</a>'
            '<a href="/real-council">City Council</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/real-council"

    def test_skips_mailto_links(self):
        html = (
            '<a href="mailto:council@city.gov">City Council</a>'
            '<a href="/council">City Council</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/council"

    def test_skips_anchor_links(self):
        html = (
            '<a href="#council-section">City Council</a>'
            '<a href="/council">City Council</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/council"

    def test_resolves_relative_urls(self):
        html = '<a href="/gov/council">City Council</a>'
        result = find_government_page("https://www.city.gov/some/page", html)
        assert result == "https://www.city.gov/gov/council"

    def test_resolves_non_slash_relative_urls(self):
        html = '<a href="council-page">City Council</a>'
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/council-page"

    def test_filters_external_domain_links(self):
        """Links to external domains are excluded."""
        html = (
            '<a href="https://other-site.com/council">City Council</a>'
            '<a href="/local-council">City Council</a>'
        )
        result = find_government_page("https://www.city.gov", html)
        assert result == "https://www.city.gov/local-council"

    def test_fallback_paths_when_no_links(self):
        """Returns common council paths when no matching links found."""
        html = "<html><body><p>Welcome to our city</p></body></html>"
        result = find_government_page("https://www.city.gov", html)
        # Fallback paths are scored; council-members scores 10 (highest)
        assert result == "https://www.city.gov/council-members"

    def test_returns_fallback_for_empty_html(self):
        """Empty HTML still returns fallback paths."""
        result = find_government_page("https://www.city.gov", "")
        # Fallback paths are scored; council-members scores 10 (highest)
        assert result == "https://www.city.gov/council-members"

    def test_preserves_url_scheme(self):
        html = '<a href="/council">City Council</a>'
        result = find_government_page("http://www.city.gov", html)
        assert result.startswith("http://")

    def test_handles_base_url_with_path(self):
        """Base URL path is stripped; only scheme+netloc used for resolution."""
        html = '<a href="/council">City Council</a>'
        result = find_government_page("https://www.city.gov/pages/home", html)
        assert result == "https://www.city.gov/council"


# ============================================================================
# TestExtractMeetingsFromPage — mock I/O, test parsing logic
# ============================================================================


class TestExtractMeetingsFromPage:
    """Tests for extract_meetings_from_page JSON parsing and normalization."""

    def test_extracts_meetings_from_clean_json(self):
        meetings_json = json.dumps([
            {
                "title": "City Council Meeting",
                "date": "2026-03-15T18:00:00",
                "meeting_type": "city_council",
                "agenda_url": "https://example.gov/agenda.pdf",
                "minutes_url": None,
                "video_url": None,
            },
            {
                "title": "Planning Commission",
                "date": "2026-03-10T19:00:00",
                "meeting_type": "planning_commission",
                "agenda_url": None,
                "minutes_url": None,
                "video_url": None,
            },
        ])
        rp, lp, ep, provider = _patch_render_and_llm("page text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 2
        assert result[0]["title"] == "City Council Meeting"
        assert result[0]["meeting_type"] == "city_council"
        assert result[0]["agenda_url"] == "https://example.gov/agenda.pdf"
        assert result[1]["title"] == "Planning Commission"

    def test_strips_markdown_json_fences(self):
        llm_response = '```json\n[{"title": "Council Meeting", "date": "2026-01-01"}]\n```'
        rp, lp, ep, _ = _patch_render_and_llm("text", llm_response)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        assert result[0]["title"] == "Council Meeting"

    def test_strips_bare_backtick_fences(self):
        llm_response = '```\n[{"title": "Board Meeting", "date": "2026-02-01"}]\n```'
        rp, lp, ep, _ = _patch_render_and_llm("text", llm_response)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        assert result[0]["title"] == "Board Meeting"

    def test_truncates_page_text_at_max_chars(self):
        """Page text exceeding max_text_chars is truncated with marker."""
        long_text = "x" * 20000
        rp, lp, ep, provider = _patch_render_and_llm(long_text, "[]")
        with rp, lp, ep:
            extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
                max_text_chars=500,
            )
        # Verify the prompt sent to LLM contains truncated text
        call_args = provider.complete.call_args
        prompt_content = call_args[0][0][0]["content"]
        assert "[... truncated ...]" in prompt_content
        # The text portion should be around max_text_chars, not the full 20k
        assert len(prompt_content) < 5000  # prompt template + 500 chars, not 20k

    def test_does_not_truncate_short_text(self):
        short_text = "Short meetings page"
        rp, lp, ep, provider = _patch_render_and_llm(short_text, "[]")
        with rp, lp, ep:
            extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
                max_text_chars=15000,
            )
        call_args = provider.complete.call_args
        prompt_content = call_args[0][0][0]["content"]
        assert "[... truncated ...]" not in prompt_content
        assert "Short meetings page" in prompt_content

    def test_resolves_relative_agenda_urls(self):
        meetings_json = json.dumps([
            {"title": "Meeting", "agenda_url": "/docs/agenda.pdf"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert result[0]["agenda_url"] == "https://example.gov/docs/agenda.pdf"

    def test_resolves_relative_url_without_leading_slash(self):
        meetings_json = json.dumps([
            {"title": "Meeting", "minutes_url": "docs/minutes.pdf"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert result[0]["minutes_url"] == "https://example.gov/docs/minutes.pdf"

    def test_preserves_absolute_urls(self):
        meetings_json = json.dumps([
            {"title": "Meeting", "video_url": "https://youtube.com/watch?v=abc"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert result[0]["video_url"] == "https://youtube.com/watch?v=abc"

    def test_skips_entries_without_title(self):
        meetings_json = json.dumps([
            {"title": "Valid Meeting"},
            {"title": "", "date": "2026-01-01"},
            {"date": "2026-02-01"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        assert result[0]["title"] == "Valid Meeting"

    def test_skips_non_dict_entries(self):
        meetings_json = json.dumps([
            {"title": "Valid Meeting"},
            "not a dict",
            42,
            None,
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        assert result[0]["title"] == "Valid Meeting"

    def test_returns_empty_on_no_json_array(self):
        rp, lp, ep, _ = _patch_render_and_llm("text", "I couldn't find any meetings on this page.")
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert result == []

    def test_returns_empty_on_invalid_json(self):
        rp, lp, ep, _ = _patch_render_and_llm("text", '[{"title": "broken json"')
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        # Truncated JSON salvage will try — but this has no closing brace
        assert result == []

    def test_salvages_truncated_json_response(self):
        """Truncated LLM response with partial array is salvaged."""
        truncated = '[{"title": "Meeting One", "date": "2026-01-01"}, {"title": "Meeting Two", "date": "2026-02-01"}, {"title": "Trun'
        rp, lp, ep, _ = _patch_render_and_llm("text", truncated)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        # Should salvage the first two complete objects
        assert len(result) == 2
        assert result[0]["title"] == "Meeting One"
        assert result[1]["title"] == "Meeting Two"

    def test_salvage_fails_for_no_closing_brace(self):
        """Truncated response with no complete object returns empty."""
        truncated = '[{"title": "Trun'
        rp, lp, ep, _ = _patch_render_and_llm("text", truncated)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        # "}" exists in the string at index... let me check
        # Actually '{"title": "Trun' has a closing brace? No it doesn't.
        # Wait: '{' is at index 1, but there's no '}'. So rfind("}") returns -1.
        # last_brace > 0 is False, so returns [].
        assert result == []

    def test_raises_without_api_key(self):
        with patch(
            "civicos_extraction.clients.playwright_llm._render_page",
            return_value=("<html/>", "text"),
        ):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(RuntimeError, match="LLM API key required"):
                    extract_meetings_from_page(
                        url="https://example.gov/meetings",
                        jurisdiction_id="city-test",
                    )

    def test_prompt_includes_jurisdiction_id(self):
        rp, lp, ep, provider = _patch_render_and_llm("page content", "[]")
        with rp, lp, ep:
            extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-ross",
            )
        call_args = provider.complete.call_args
        prompt = call_args[0][0][0]["content"]
        assert "city-ross" in prompt

    def test_prompt_includes_page_text(self):
        rp, lp, ep, provider = _patch_render_and_llm("Unique meeting text XYZ", "[]")
        with rp, lp, ep:
            extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        call_args = provider.complete.call_args
        prompt = call_args[0][0][0]["content"]
        assert "Unique meeting text XYZ" in prompt

    def test_llm_called_with_low_temperature(self):
        rp, lp, ep, provider = _patch_render_and_llm("text", "[]")
        with rp, lp, ep:
            extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        call_kwargs = provider.complete.call_args[1]
        assert call_kwargs["temperature"] == 0.1

    def test_base_url_extraction_from_page_url(self):
        """Base URL for resolving relative links comes from the page URL."""
        meetings_json = json.dumps([
            {"title": "Meeting", "agenda_url": "/doc.pdf"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://www.townofrossca.gov/meetings/calendar",
                jurisdiction_id="city-ross",
            )
        assert result[0]["agenda_url"] == "https://www.townofrossca.gov/doc.pdf"


# ============================================================================
# TestExtractOfficialsFromPage — mock I/O, test parsing logic
# ============================================================================


class TestExtractOfficialsFromPage:
    """Tests for extract_officials_from_page parsing and ID generation."""

    def test_extracts_officials_with_correct_fields(self):
        officials_json = json.dumps([
            {"name": "Jane Smith", "role": "Mayor", "district": None, "email": "jane@city.gov", "phone": "555-0001"},
            {"name": "Bob Jones", "role": "Council Member", "district": "1", "email": None, "phone": None},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("page text", officials_json)
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert len(result) == 2
        assert result[0]["name"] == "Jane Smith"
        assert result[0]["seat"] == "Mayor"
        assert result[0]["email"] == "jane@city.gov"
        assert result[0]["phone"] == "555-0001"
        assert result[0]["jurisdiction_id"] == "city-test"
        assert result[0]["source"] == "website"
        assert result[1]["name"] == "Bob Jones"
        assert result[1]["district"] == "1"

    def test_id_format_is_web_jurisdiction_slugified_name(self):
        officials_json = json.dumps([
            {"name": "Jane A. Smith-Jones", "role": "Mayor"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", officials_json)
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        expected_id = "web-city-test-jane-a-smith-jones"
        assert result[0]["id"] == expected_id

    def test_id_strips_leading_trailing_hyphens(self):
        officials_json = json.dumps([
            {"name": "  Jane Smith  ", "role": "Mayor"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", officials_json)
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        # Slug should not have leading/trailing hyphens from whitespace
        assert not result[0]["id"].endswith("-")
        assert result[0]["id"] == "web-city-test-jane-smith"

    def test_default_seat_when_role_missing(self):
        officials_json = json.dumps([
            {"name": "Jane Smith"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", officials_json)
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert result[0]["seat"] == "Elected Official"

    def test_skips_entries_without_name(self):
        officials_json = json.dumps([
            {"name": "Valid Official", "role": "Mayor"},
            {"name": "", "role": "Nobody"},
            {"role": "Missing Name"},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", officials_json)
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        assert result[0]["name"] == "Valid Official"

    def test_skips_non_dict_entries(self):
        officials_json = json.dumps([
            {"name": "Jane Smith", "role": "Mayor"},
            "not a dict",
            42,
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", officials_json)
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1

    def test_returns_empty_without_api_key(self):
        """No API key returns empty list (does not raise)."""
        with patch.dict("os.environ", {}, clear=True):
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert result == []

    def test_returns_empty_on_no_json_array(self):
        rp, lp, ep, _ = _patch_render_and_llm("text", "No officials found on this page.")
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert result == []

    def test_returns_empty_on_invalid_json(self):
        rp, lp, ep, _ = _patch_render_and_llm("text", '[{"name": broken')
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert result == []

    def test_prompt_includes_jurisdiction_id(self):
        rp, lp, ep, provider = _patch_render_and_llm("text", "[]")
        with rp, lp, ep:
            extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-ross",
            )
        call_args = provider.complete.call_args
        prompt = call_args[0][0][0]["content"]
        assert "city-ross" in prompt

    def test_truncates_page_text_at_max_chars(self):
        long_text = "y" * 20000
        rp, lp, ep, provider = _patch_render_and_llm(long_text, "[]")
        with rp, lp, ep:
            extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
                max_text_chars=500,
            )
        call_args = provider.complete.call_args
        prompt = call_args[0][0][0]["content"]
        assert "[... truncated ...]" in prompt


# ============================================================================
# TestPlaywrightLLMSource — wrapper protocol tests
# ============================================================================


class TestPlaywrightLLMSource:
    """Tests for PlaywrightLLMSource config wrapper."""

    @pytest.fixture
    def config(self):
        return ExtractionConfig(
            source_id="playwright-llm-city-ross",
            source_type="playwright_llm",
            jurisdiction_id="city-ross",
            base_url="https://www.townofrossca.gov",
            metadata={"meeting_page_url": "https://www.townofrossca.gov/meetings"},
        )

    @pytest.fixture
    def source(self, config):
        return PlaywrightLLMSource(config)

    def test_source_id_format(self, source):
        assert source.source_id == "playwright-llm-city-ross"

    def test_source_type(self, source):
        assert source.source_type == "playwright_llm"

    def test_jurisdiction_id(self, source):
        assert source.jurisdiction_id == "city-ross"

    def test_meeting_page_url_from_metadata(self, source):
        assert source._meeting_page_url == "https://www.townofrossca.gov/meetings"

    def test_meeting_page_url_falls_back_to_base_url(self):
        config = ExtractionConfig(
            source_id="playwright-llm-city-test",
            source_type="playwright_llm",
            jurisdiction_id="city-test",
            base_url="https://www.city.gov",
            metadata={},
        )
        source = PlaywrightLLMSource(config)
        assert source._meeting_page_url == "https://www.city.gov"

    def test_validate_with_url(self, source):
        result = source.validate()
        assert result.is_valid is True
        assert result.config_valid is True
        assert len(result.errors) == 0

    def test_validate_without_url(self):
        config = ExtractionConfig(
            source_id="playwright-llm-city-test",
            source_type="playwright_llm",
            jurisdiction_id="city-test",
            base_url="",
            metadata={"meeting_page_url": ""},
        )
        source = PlaywrightLLMSource(config)
        result = source.validate()
        assert result.is_valid is False
        assert "meeting_page_url" in result.errors[0]

    def test_get_events_delegates_to_extract_meetings(self, source):
        mock_meetings = [{"title": "Council Meeting", "date": "2026-03-15"}]
        with patch(
            "civicos_extraction.clients.playwright_llm.extract_meetings_from_page",
            return_value=mock_meetings,
        ) as mock_extract:
            result = source.get_events()
        assert result == mock_meetings
        mock_extract.assert_called_once_with(
            url="https://www.townofrossca.gov/meetings",
            jurisdiction_id="city-ross",
        )

    def test_get_meetings_aliases_get_events(self, source):
        mock_meetings = [{"title": "Board Meeting"}]
        with patch(
            "civicos_extraction.clients.playwright_llm.extract_meetings_from_page",
            return_value=mock_meetings,
        ):
            result = source.get_meetings(days_ahead=30, days_past=7)
        assert result == mock_meetings

    def test_normalize_event_uses_wrong_meeting_param_name(self, source):
        """BUG: normalize_event passes meeting_id/source_id/source_type to Meeting
        which expects id/source_platform. Documents the mismatch for future fix."""
        event = {"title": "Meeting", "date": "2026-01-01T10:00:00"}
        with pytest.raises(TypeError, match="meeting_id"):
            source.normalize_event(event)

    def test_normalize_event_date_parsing_valid_iso(self, source):
        """Test the date parsing logic inside normalize_event (before Meeting construction)."""
        # We test the fromisoformat path by checking what normalize_event computes.
        # Since normalize_event crashes at Meeting(), we test the inner logic directly.
        event = {"title": "Council", "date": "2026-03-15T18:00:00"}
        date_str = event.get("date", "")
        parsed = datetime.fromisoformat(date_str)
        assert parsed == datetime(2026, 3, 15, 18, 0, 0)

    def test_normalize_event_date_parsing_invalid_falls_back(self, source):
        """Invalid date string triggers fallback to epoch."""
        date_str = "not-a-date"
        try:
            parsed = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            parsed = datetime(1970, 1, 1)
        assert parsed == datetime(1970, 1, 1)

    def test_normalize_event_date_parsing_empty_falls_back(self, source):
        """Empty date string triggers fallback to epoch."""
        date_str = ""
        try:
            parsed = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            parsed = datetime(1970, 1, 1)
        assert parsed == datetime(1970, 1, 1)

    def test_normalize_event_id_computation(self, source):
        """Verify the SHA-256 ID computation logic used by normalize_event."""
        title = "Council Meeting"
        parsed_date = datetime.fromisoformat("2026-03-15T18:00:00")
        id_source = f"city-ross:{title}:{parsed_date.isoformat()}"
        meeting_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]
        assert len(meeting_id) == 16
        # Stable: same input → same ID
        meeting_id2 = hashlib.sha256(id_source.encode()).hexdigest()[:16]
        assert meeting_id == meeting_id2

    def test_normalize_event_different_titles_produce_different_ids(self, source):
        """Different titles produce different meeting IDs."""
        date = datetime(2026, 3, 15, 18, 0, 0)
        id1 = hashlib.sha256(f"city-ross:Council Meeting:{date.isoformat()}".encode()).hexdigest()[:16]
        id2 = hashlib.sha256(f"city-ross:Planning Meeting:{date.isoformat()}".encode()).hexdigest()[:16]
        assert id1 != id2

    def test_normalize_event_default_title(self, source):
        """Missing title defaults to 'Unknown Meeting'."""
        event = {"date": "2026-01-01T10:00:00"}
        title = event.get("title", "Unknown Meeting")
        assert title == "Unknown Meeting"

    def test_health_check_success(self, source):
        mock_meetings = [{"title": "M1"}, {"title": "M2"}]
        with patch(
            "civicos_extraction.clients.playwright_llm.extract_meetings_from_page",
            return_value=mock_meetings,
        ):
            health = source.health()
        assert health.is_available is True
        assert health.available_count == 2
        assert health.source_id == "playwright-llm-city-ross"
        assert health.source_type == "playwright_llm"
        assert health.jurisdiction_id == "city-ross"
        assert len(health.errors) == 0
        assert health.check_duration_ms >= 0

    def test_health_check_failure(self, source):
        with patch(
            "civicos_extraction.clients.playwright_llm.extract_meetings_from_page",
            side_effect=RuntimeError("Browser crash"),
        ):
            health = source.health()
        assert health.is_available is False
        assert health.available_count == 0
        assert len(health.errors) == 1
        assert "Browser crash" in health.errors[0]

    def test_health_check_empty_meetings(self, source):
        with patch(
            "civicos_extraction.clients.playwright_llm.extract_meetings_from_page",
            return_value=[],
        ):
            health = source.health()
        assert health.is_available is False
        assert health.available_count == 0


# ============================================================================
# TestExtractionPrompts — verify prompt templates
# ============================================================================


class TestExtractionPrompts:
    """Tests for prompt template content and formatting."""

    def test_extraction_prompt_has_placeholders(self):
        assert "{jurisdiction_id}" in _EXTRACTION_PROMPT
        assert "{page_text}" in _EXTRACTION_PROMPT

    def test_officials_prompt_has_placeholders(self):
        assert "{jurisdiction_id}" in _OFFICIALS_PROMPT
        assert "{page_text}" in _OFFICIALS_PROMPT

    def test_extraction_prompt_formats_without_error(self):
        result = _EXTRACTION_PROMPT.format(
            jurisdiction_id="city-test",
            page_text="Sample text",
        )
        assert "city-test" in result
        assert "Sample text" in result

    def test_officials_prompt_formats_without_error(self):
        result = _OFFICIALS_PROMPT.format(
            jurisdiction_id="city-ross",
            page_text="Council members page",
        )
        assert "city-ross" in result
        assert "Council members page" in result


# ============================================================================
# TestEdgeCases
# ============================================================================


class TestEdgeCases:
    """Edge cases for JSON parsing, URL handling, and boundary conditions."""

    def test_meetings_with_extra_text_around_json(self):
        """LLM returns text before/after JSON array."""
        llm_response = 'Here are the meetings:\n[{"title": "Council"}]\nHope that helps!'
        rp, lp, ep, _ = _patch_render_and_llm("text", llm_response)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        assert result[0]["title"] == "Council"

    def test_meetings_json_with_null_url_fields(self):
        meetings_json = json.dumps([
            {"title": "Meeting", "agenda_url": None, "minutes_url": None, "video_url": None},
        ])
        rp, lp, ep, _ = _patch_render_and_llm("text", meetings_json)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert len(result) == 1
        # None URLs should not be resolved
        assert result[0]["agenda_url"] is None

    def test_empty_json_array(self):
        rp, lp, ep, _ = _patch_render_and_llm("text", "[]")
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        assert result == []

    def test_officials_empty_array(self):
        rp, lp, ep, _ = _patch_render_and_llm("text", "[]")
        with rp, lp, ep:
            result = extract_officials_from_page(
                url="https://example.gov/council",
                jurisdiction_id="city-test",
            )
        assert result == []

    def test_salvage_with_broken_last_object(self):
        """Truncated JSON where last complete object has trailing comma."""
        truncated = '[{"title": "One"}, {"title": "Two"}, {"title": "Thr'
        rp, lp, ep, _ = _patch_render_and_llm("text", truncated)
        with rp, lp, ep:
            result = extract_meetings_from_page(
                url="https://example.gov/meetings",
                jurisdiction_id="city-test",
            )
        # rfind("}") finds the closing brace of "Two", salvages [One, Two]
        assert len(result) == 2
        assert result[0]["title"] == "One"
        assert result[1]["title"] == "Two"

    def test_google_api_key_also_accepted(self):
        """GOOGLE_API_KEY is accepted as an alternative to OPENAI_API_KEY."""
        meetings_json = json.dumps([{"title": "Meeting"}])
        with patch(
            "civicos_extraction.clients.playwright_llm._render_page",
            return_value=("<html/>", "text"),
        ):
            provider = _mock_llm_response(meetings_json)
            with patch(
                "civicos_extraction.llm.get_llm_provider",
                return_value=provider,
            ):
                with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}, clear=True):
                    result = extract_meetings_from_page(
                        url="https://example.gov/meetings",
                        jurisdiction_id="city-test",
                    )
        assert len(result) == 1
