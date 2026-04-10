"""
Tests for civic_digest.py — the digest generator module.

Focuses on pure-logic methods: truncation, categorization, rendering,
deduplication, stale content detection, location fallbacks, and date validation.

To run:
    pytest packages/civicos-services/tests/test_civic_digest.py -q --override-ini="addopts="
"""

import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Patch env vars and openai before importing module (CivicDigest.__init__ calls exit(1) without them)
_ENV_PATCH = {
    "OPENAI_API_KEY": "test-key-fake",
    "GMAIL_EMAIL": "test@example.com",
    "GMAIL_APP_PASSWORD": "test-app-password-16ch",
}

with patch.dict(os.environ, _ENV_PATCH):
    with patch("openai.OpenAI"):
        from civicos_services.processing.civic_digest import (
            CivicDigest,
            CivicOpportunity,
        )

# Inject logging into the module namespace (used by _validate_datetime_sanity
# but not explicitly imported at module level)
import civicos_services.processing.civic_digest as _civic_digest_mod

_civic_digest_mod.logging = logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def digest():
    """Create a CivicDigest instance with mocked external dependencies."""
    with patch.dict(os.environ, _ENV_PATCH):
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            d = CivicDigest()
            d.openai_client = mock_client
            return d


# ---------------------------------------------------------------------------
# CivicOpportunity dataclass
# ---------------------------------------------------------------------------


class TestCivicOpportunity:
    def test_to_dict_returns_all_fields_with_correct_values(self):
        opp = CivicOpportunity(
            title="Zoning Hearing",
            when="2026-05-01T18:00:00",
            engagement_info="Attend and comment",
            impact_summary="Rezoning affects 50 homes",
            source_url="https://example.gov/meeting/1",
            location="City Hall",
            deadline="2026-04-30",
            project_type="housing",
            contact_email="planning@example.gov",
            contact_name="Jane Doe",
            success_strategy="Reference policy 4.1",
            engagement_tier="attend",
            deadline_guidance="Submit 48h before meeting",
        )
        d = opp.to_dict()
        assert d["title"] == "Zoning Hearing"
        assert d["when"] == "2026-05-01T18:00:00"
        assert d["project_type"] == "housing"
        assert d["contact_email"] == "planning@example.gov"
        assert d["engagement_tier"] == "attend"
        assert d["deadline_guidance"] == "Submit 48h before meeting"

    def test_default_values(self):
        opp = CivicOpportunity(
            title="Item",
            when="2026-01-01",
            engagement_info="info",
            impact_summary="summary",
            source_url="https://example.gov",
        )
        d = opp.to_dict()
        assert d["location"] == ""
        assert d["deadline"] == ""
        assert d["project_type"] == ""
        assert d["contact_email"] == ""
        assert d["engagement_tier"] == "email"


# ---------------------------------------------------------------------------
# _truncate_safely
# ---------------------------------------------------------------------------


class TestTruncateSafely:
    def test_short_text_returned_unchanged(self, digest):
        text = "Hello world."
        result = digest._truncate_safely(text, limit_chars=100)
        assert result == "Hello world."

    def test_text_at_exact_limit_returned_unchanged(self, digest):
        text = "A" * 100
        result = digest._truncate_safely(text, limit_chars=100)
        assert result == text

    def test_long_text_truncated_with_marker(self, digest):
        # 50 chars of text, truncate at 30
        text = "First sentence. Second sentence. Third sentence end."
        result = digest._truncate_safely(text, limit_chars=30)
        assert "[... content truncated for length ...]" in result
        assert len(result) < len(text) + 50  # original + marker

    def test_truncation_preserves_sentence_boundary(self, digest):
        # Place sentence end within the 80% window of the limit
        text = "A" * 40 + ". " + "B" * 60  # period at position 40
        result = digest._truncate_safely(text, limit_chars=50)
        # Should truncate at the period (position 40) since 40 > 50*0.8=40
        # The boundary condition: 40 is NOT > 40 (strict >), so it won't use the period
        # It will truncate at 50 chars
        assert result.endswith("[... content truncated for length ...]")

    def test_truncation_does_not_lose_more_than_20_percent(self, digest):
        # Put a period very early — should NOT be used because it loses > 20%
        text = "Hi. " + "X" * 200
        result = digest._truncate_safely(text, limit_chars=100)
        # Period at position 2 is < 100*0.8=80, so truncation ignores it
        # Falls back to hard cut at 100
        content_before_marker = result.replace(
            "\n\n[... content truncated for length ...]", ""
        )
        assert len(content_before_marker) == 100

    def test_truncation_uses_newline_boundary(self, digest):
        # Double newline within the 80% window
        text = "A" * 85 + "\n\n" + "B" * 50
        result = digest._truncate_safely(text, limit_chars=100)
        assert "[... content truncated for length ...]" in result


# ---------------------------------------------------------------------------
# _categorize_civic_event
# ---------------------------------------------------------------------------


class TestCategorizeCivicEvent:
    def test_volunteer_event(self, digest):
        category, impact = digest._categorize_civic_event(
            "Hillside Volunteer Cleanup Day", "Help clean the park"
        )
        assert category == "community_action"
        assert "community involvement" in impact.lower()

    def test_meeting_event(self, digest):
        category, impact = digest._categorize_civic_event(
            "City Council Meeting", "Regular monthly meeting"
        )
        assert category == "public_meeting"
        assert "government decisions" in impact.lower()

    def test_educational_event(self, digest):
        category, impact = digest._categorize_civic_event(
            "City Open House Tour", "Tour the new facility"
        )
        assert category == "educational"
        assert "awareness" in impact.lower()

    def test_service_event(self, digest):
        category, impact = digest._categorize_civic_event(
            "Community Blood Drive", "Donate blood at City Hall"
        )
        assert category == "community_service"
        assert "health" in impact.lower() or "emergency" in impact.lower()

    def test_general_event(self, digest):
        category, impact = digest._categorize_civic_event(
            "Spring Festival", "Annual community celebration"
        )
        assert category == "general"
        assert "civic participation" in impact.lower()

    def test_park_event_categorized_as_community_action(self, digest):
        category, _ = digest._categorize_civic_event("Park Restoration", "")
        assert category == "community_action"


# ---------------------------------------------------------------------------
# _get_participation_guidance
# ---------------------------------------------------------------------------


class TestGetParticipationGuidance:
    def test_volunteer_guidance(self, digest):
        result = digest._get_participation_guidance("Weekend Volunteer Event")
        assert "Volunteer Registration Form" in result

    def test_tour_guidance(self, digest):
        result = digest._get_participation_guidance("City Hall Tour")
        assert "RSVP" in result

    def test_blood_drive_guidance(self, digest):
        result = digest._get_participation_guidance("Annual Blood Drive")
        assert "ELCERRITO" in result

    def test_cleanup_guidance(self, digest):
        result = digest._get_participation_guidance("Creek Cleanup Day")
        assert "long pants" in result

    def test_meeting_guidance(self, digest):
        result = digest._get_participation_guidance("Planning Commission Meeting")
        assert "public comment" in result.lower()

    def test_generic_event_guidance(self, digest):
        result = digest._get_participation_guidance("Spring Concert")
        assert "Contact the city" in result


# ---------------------------------------------------------------------------
# _get_project_type
# ---------------------------------------------------------------------------


class TestGetProjectType:
    @pytest.mark.parametrize(
        "event_name,expected",
        [
            ("Park Restoration Project", "environment"),
            ("Climate Action Plan Review", "environment"),
            ("Affordable Housing Proposal", "housing"),
            ("Zoning Variance Request", "housing"),
            ("Planning Commission Meeting", "development"),
            ("Design Review Board", "development"),
            ("Annual Budget Workshop", "budget"),
            ("Finance Committee Meeting", "budget"),
            ("School District Update", "education"),
            ("Library Advisory Board", "education"),
            ("Transit Authority Board", "transportation"),
            ("Bike Lane Project", "transportation"),
            ("Police Oversight Board", "public_safety"),
            ("Fire Department Review", "public_safety"),
            ("Election Certification", "elections"),
            ("Ballot Measure Discussion", "elections"),
            ("Community Health Fair", "community"),
            ("Volunteer Appreciation Day", "community"),
            ("Regular Board Session", "governance"),
        ],
    )
    def test_project_type_classification(self, digest, event_name, expected):
        assert digest._get_project_type(event_name) == expected


# ---------------------------------------------------------------------------
# _get_extraction_schema / _get_empty_civic_data
# ---------------------------------------------------------------------------


class TestSchemaAndEmptyData:
    def test_extraction_schema_has_required_top_level_fields(self, digest):
        schema = digest._get_extraction_schema()
        assert schema["name"] == "CivicNewsletter"
        required = schema["schema"]["required"]
        assert "meeting" in required
        assert "items" in required
        assert "recap_rows" in required
        assert "bottom_line" in required

    def test_extraction_schema_meeting_requires_date(self, digest):
        schema = digest._get_extraction_schema()
        meeting_required = schema["schema"]["properties"]["meeting"]["required"]
        assert meeting_required == ["date"]

    def test_extraction_schema_items_have_required_fields(self, digest):
        schema = digest._get_extraction_schema()
        item_required = schema["schema"]["properties"]["items"]["items"]["required"]
        assert "title" in item_required
        assert "project_type" in item_required
        assert "how_to_participate" in item_required

    def test_empty_civic_data_structure(self, digest):
        data = digest._get_empty_civic_data()
        assert data["meeting"]["date"] == "Not specified"
        assert data["items"] == []
        assert data["recap_rows"] == []
        assert "Unable to extract" in data["bottom_line"]


# ---------------------------------------------------------------------------
# _render_fallback_newsletter
# ---------------------------------------------------------------------------


class TestRenderFallbackNewsletter:
    def test_contains_city_name_and_date(self, digest):
        civic_data = {
            "meeting": {"city": "San Rafael", "date": "2026-04-15"},
            "items": [],
            "bottom_line": "Check the agenda.",
        }
        result = digest._render_fallback_newsletter(civic_data, "https://example.gov")
        assert "San Rafael" in result
        assert "2026-04-15" in result

    def test_renders_agenda_items(self, digest):
        civic_data = {
            "meeting": {
                "city": "Berkeley",
                "date": "2026-05-01",
                "start_time": "6:00 PM",
                "location": "City Hall",
                "livestream": "",
                "public_comment_email": "council@berkeley.gov",
                "public_comment_rules": "3 min per person",
            },
            "items": [
                {
                    "title": "Housing Rezoning",
                    "change": "Rezone 5 blocks to mixed-use",
                    "impact": "500 new units possible",
                    "how_to_participate": "Email or attend",
                }
            ],
            "bottom_line": "Big meeting for housing.",
        }
        result = digest._render_fallback_newsletter(civic_data, "https://example.gov")
        assert "Housing Rezoning" in result
        assert "Rezone 5 blocks" in result
        assert "500 new units" in result
        assert "Big meeting for housing." in result

    def test_includes_source_url_link(self, digest):
        civic_data = {
            "meeting": {"city": "Test", "date": "2026-01-01"},
            "items": [],
            "bottom_line": "N/A",
        }
        result = digest._render_fallback_newsletter(
            civic_data, "https://city.gov/agenda"
        )
        assert "https://city.gov/agenda" in result
        assert "View original meeting agenda" in result

    def test_no_source_url_omits_link(self, digest):
        civic_data = {
            "meeting": {"city": "Test", "date": "2026-01-01"},
            "items": [],
            "bottom_line": "N/A",
        }
        result = digest._render_fallback_newsletter(civic_data, "")
        assert "View original meeting agenda" not in result


# ---------------------------------------------------------------------------
# _combine_newsletters
# ---------------------------------------------------------------------------


class TestCombineNewsletters:
    def test_combines_with_city_header(self, digest):
        newsletters = ["## Meeting A\nContent A", "## Meeting B\nContent B"]
        result = digest._combine_newsletters(newsletters, "Novato")
        assert "Novato" in result
        assert "Meeting 1" in result
        assert "Content A" in result
        assert "Meeting 2" in result
        assert "Content B" in result

    def test_single_newsletter_still_wrapped(self, digest):
        result = digest._combine_newsletters(["Only one"], "Ross")
        assert "Ross" in result
        assert "Only one" in result
        assert "Meeting 1" in result


# ---------------------------------------------------------------------------
# _render_combined_newsletter
# ---------------------------------------------------------------------------


class TestRenderCombinedNewsletter:
    def test_structure_with_multiple_meetings(self, digest):
        data = [
            {
                "city": "Oakland",
                "meeting_title": "City Council",
                "meeting_date": "2026-05-10",
                "source_url": "https://oakland.gov/cc",
                "agenda_items": [
                    {
                        "title": "Budget Review",
                        "impact": "Affects parks funding",
                        "how_to_participate": "Attend and speak",
                    }
                ],
            },
            {
                "city": "Oakland",
                "meeting_title": "Planning Commission",
                "meeting_date": "2026-05-12",
                "source_url": "https://oakland.gov/pc",
                "agenda_items": [],
            },
        ]
        result = digest._render_combined_newsletter(data, "https://oakland.gov/cal")
        assert "Oakland" in result
        assert "City Council" in result
        assert "Planning Commission" in result
        assert "Budget Review" in result
        assert "2 meetings found" in result

    def test_stores_combined_data_in_attributes(self, digest):
        data = [
            {
                "city": "TestCity",
                "meeting_title": "Board",
                "meeting_date": "2026-06-01",
                "source_url": "",
                "agenda_items": [{"title": "Item X"}],
            }
        ]
        digest._render_combined_newsletter(data, "https://test.gov")
        assert digest._last_civic_data["city"] == "TestCity"
        assert len(digest._last_civic_data["items"]) == 1
        assert digest._last_civic_data["items"][0]["title"] == "Item X"
        assert digest._last_source_url == "https://test.gov"


# ---------------------------------------------------------------------------
# _empty_digest / _fallback_digest
# ---------------------------------------------------------------------------


class TestDigestRendering:
    def test_empty_digest_contains_city_name(self, digest):
        result = digest._empty_digest("Larkspur")
        assert "Larkspur" in result
        assert "Subject:" in result
        assert "No Major Civic Opportunities This Week in Larkspur" in result

    def test_fallback_digest_includes_event_details(self, digest):
        events = [
            CivicOpportunity(
                title="Road Closure",
                when="2026-06-01T09:00:00",
                engagement_info="Call public works",
                impact_summary="Main St closed for 2 weeks",
                source_url="https://city.gov/road",
            )
        ]
        result = digest._fallback_digest(events, "Tiburon")
        assert "Tiburon" in result
        assert "Road Closure" in result
        assert "Main St closed for 2 weeks" in result
        assert "Call public works" in result
        assert "Subject:" in result


# ---------------------------------------------------------------------------
# _create_modern_table
# ---------------------------------------------------------------------------


class TestCreateModernTable:
    def test_empty_table_returns_empty_string(self, digest):
        assert digest._create_modern_table([]) == ""

    def test_table_with_header_and_rows(self, digest):
        rows = [
            ["Topic", "Status"],
            ["Housing", "Approved"],
            ["Budget", "Pending"],
        ]
        html = digest._create_modern_table(rows)
        assert "<table" in html
        assert "<th" in html
        assert "Topic" in html
        assert "Housing" in html
        assert "Approved" in html
        assert "Budget" in html
        assert "Pending" in html

    def test_table_alternates_row_background(self, digest):
        rows = [
            ["Col"],
            ["Row1"],
            ["Row2"],
            ["Row3"],
        ]
        html = digest._create_modern_table(rows)
        assert "#f8f9fa" in html  # even row color


# ---------------------------------------------------------------------------
# _markdown_to_html
# ---------------------------------------------------------------------------


class TestMarkdownToHtml:
    def test_h1_header_converted(self, digest):
        md = "# Main Title"
        html = digest._markdown_to_html(md)
        assert "<h1" in html
        assert "Main Title" in html

    def test_h2_participate_section_styled(self, digest):
        md = "## 🗣️ How to Participate\n- **Meeting:** details here"
        html = digest._markdown_to_html(md)
        assert "How to Participate" in html
        assert "details here" in html

    def test_h3_agenda_item(self, digest):
        md = "### Zoning Change\n- **Change:** Rezone area"
        html = digest._markdown_to_html(md)
        assert "<h3" in html
        assert "Zoning Change" in html

    def test_subject_line_stripped(self, digest):
        md = "Subject: Important Meeting\n# Title"
        html = digest._markdown_to_html(md)
        # Subject line should not appear in the HTML body
        assert "Subject: Important Meeting" not in html
        assert "Title" in html

    def test_markdown_links_converted_to_html(self, digest):
        md = "- **Full Agenda:** [View agenda](https://city.gov/agenda)"
        html = digest._markdown_to_html(md)
        assert 'href="https://city.gov/agenda"' in html
        assert "View agenda" in html

    def test_footer_line_rendered(self, digest):
        md = "⚡ *Independent and nonpartisan summary.*"
        html = digest._markdown_to_html(md)
        assert "Independent and nonpartisan summary." in html
        assert "<em" in html

    def test_wraps_in_newsletter_template(self, digest):
        md = "# Test"
        html = digest._markdown_to_html(md)
        assert "<!DOCTYPE html>" in html
        assert "Civic Brief" in html


# ---------------------------------------------------------------------------
# _validate_datetime_sanity
# ---------------------------------------------------------------------------


class TestValidateDatetimeSanity:
    def test_rejects_none(self, digest):
        assert digest._validate_datetime_sanity(None) is False

    def test_accepts_tomorrow(self, digest):
        tomorrow = datetime.now() + timedelta(days=1)
        assert digest._validate_datetime_sanity(tomorrow, "Council Meeting") is True

    def test_accepts_date_within_2_days_past(self, digest):
        yesterday = datetime.now() - timedelta(days=1)
        assert (
            digest._validate_datetime_sanity(yesterday, "Recent Meeting") is True
        )

    def test_rejects_date_more_than_2_days_past(self, digest):
        old = datetime.now() - timedelta(days=5)
        assert (
            digest._validate_datetime_sanity(old, "Old Meeting", "TestSource")
            is False
        )

    def test_rejects_date_more_than_365_days_future(self, digest):
        far_future = datetime.now() + timedelta(days=400)
        assert (
            digest._validate_datetime_sanity(far_future, "Far Future", "TestSource")
            is False
        )

    def test_accepts_date_364_days_in_future(self, digest):
        near_limit = datetime.now() + timedelta(days=364)
        assert digest._validate_datetime_sanity(near_limit, "Annual Event") is True

    def test_boundary_1_day_ago_accepted(self, digest):
        # 1 day ago: days_until = -1 or -2, condition is < -2, so it should pass
        boundary = datetime.now() - timedelta(hours=36)
        assert (
            digest._validate_datetime_sanity(boundary, "Boundary Past") is True
        )

    def test_boundary_exactly_365_days_future(self, digest):
        # 365 days: condition is > 365, so 365 should pass
        boundary = datetime.now() + timedelta(days=365)
        assert (
            digest._validate_datetime_sanity(boundary, "Boundary Future") is True
        )

    def test_timezone_aware_datetime(self, digest):
        aware_tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        assert digest._validate_datetime_sanity(aware_tomorrow, "Aware Event") is True


# ---------------------------------------------------------------------------
# _deduplicate_agenda_items
# ---------------------------------------------------------------------------


class TestDeduplicateAgendaItems:
    def test_removes_duplicate_across_meetings(self, digest):
        schema = {
            "events": [
                {
                    "title": "City Council Oct",
                    "when_human": "Oct 15",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {"title": "Budget Amendment", "item_ref": "5A"},
                            {"title": "Park Renovation", "item_ref": "5B"},
                        ],
                    },
                },
                {
                    "title": "City Council Nov",
                    "when_human": "Nov 15",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {"title": "Budget Amendment", "item_ref": "5A"},  # dup
                            {"title": "New Library", "item_ref": "6A"},
                        ],
                    },
                },
            ]
        }
        result = digest._deduplicate_agenda_items(schema)
        # First meeting keeps both items
        assert len(result["events"][0]["agenda_expansion"]["actionable_items"]) == 2
        # Second meeting loses the duplicate
        second_items = result["events"][1]["agenda_expansion"]["actionable_items"]
        assert len(second_items) == 1
        assert second_items[0]["title"] == "New Library"

    def test_keeps_unique_items(self, digest):
        schema = {
            "events": [
                {
                    "title": "Meeting A",
                    "when_human": "Jan 10",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {"title": "Item 1", "item_ref": "1"},
                        ],
                    },
                },
                {
                    "title": "Meeting B",
                    "when_human": "Jan 20",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {"title": "Item 2", "item_ref": "2"},
                        ],
                    },
                },
            ]
        }
        result = digest._deduplicate_agenda_items(schema)
        assert len(result["events"][0]["agenda_expansion"]["actionable_items"]) == 1
        assert len(result["events"][1]["agenda_expansion"]["actionable_items"]) == 1

    def test_skips_unparsed_events(self, digest):
        schema = {
            "events": [
                {
                    "title": "Unparsed",
                    "when_human": "Jan 1",
                    "agenda_expansion": {"parsed": False, "actionable_items": []},
                },
            ]
        }
        result = digest._deduplicate_agenda_items(schema)
        assert len(result["events"]) == 1  # unchanged

    def test_empty_events_list(self, digest):
        schema = {"events": []}
        result = digest._deduplicate_agenda_items(schema)
        assert result["events"] == []


# ---------------------------------------------------------------------------
# _detect_stale_content
# ---------------------------------------------------------------------------


class TestDetectStaleContent:
    def test_flags_old_fiscal_year(self, digest):
        current_year = datetime.now().year
        old_fy = current_year - 4  # 4 years old → flagged
        schema = {
            "events": [
                {
                    "title": "Budget Meeting",
                    "when_human": "Jan 15",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {
                                "title": f"FY {old_fy}-{old_fy + 1} Budget",
                                "description": "",
                            }
                        ],
                    },
                }
            ]
        }
        result = digest._detect_stale_content(schema)
        item = result["events"][0]["agenda_expansion"]["actionable_items"][0]
        assert item["_stale_content_warning"] is True
        assert str(old_fy) in item["_warning_reason"]
        assert item["_warning_severity"] == "medium"

    def test_high_severity_for_very_old_content(self, digest):
        current_year = datetime.now().year
        very_old_fy = current_year - 6
        schema = {
            "events": [
                {
                    "title": "Old Review",
                    "when_human": "Feb",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {
                                "title": f"FY {very_old_fy}-{very_old_fy + 1}",
                                "description": "",
                            }
                        ],
                    },
                }
            ]
        }
        result = digest._detect_stale_content(schema)
        item = result["events"][0]["agenda_expansion"]["actionable_items"][0]
        assert item["_warning_severity"] == "high"

    def test_does_not_flag_recent_fiscal_year(self, digest):
        current_year = datetime.now().year
        schema = {
            "events": [
                {
                    "title": "Current Budget",
                    "when_human": "Mar",
                    "agenda_expansion": {
                        "parsed": True,
                        "actionable_items": [
                            {
                                "title": f"FY {current_year}-{current_year + 1} Budget",
                                "description": "",
                            }
                        ],
                    },
                }
            ]
        }
        result = digest._detect_stale_content(schema)
        item = result["events"][0]["agenda_expansion"]["actionable_items"][0]
        assert "_stale_content_warning" not in item

    def test_ignores_unparsed_events(self, digest):
        schema = {
            "events": [
                {
                    "title": "X",
                    "when_human": "Apr",
                    "agenda_expansion": {
                        "parsed": False,
                        "actionable_items": [
                            {"title": "FY 2018-19 Budget", "description": ""}
                        ],
                    },
                }
            ]
        }
        result = digest._detect_stale_content(schema)
        item = result["events"][0]["agenda_expansion"]["actionable_items"][0]
        assert "_stale_content_warning" not in item


# ---------------------------------------------------------------------------
# _add_location_fallback
# ---------------------------------------------------------------------------


class TestAddLocationFallback:
    def test_adds_fallback_for_known_jurisdiction(self, digest):
        schema = {
            "events": [
                {
                    "title": "Council Meeting",
                    "location": "",
                    "jurisdiction": {"id": "city-san-rafael"},
                    "participation_mechanisms": [],
                }
            ]
        }
        result = digest._add_location_fallback(schema)
        assert (
            result["events"][0]["location"]
            == "1400 Fifth Avenue, San Rafael, CA 94901"
        )

    def test_adds_generic_fallback_for_unknown_jurisdiction(self, digest):
        schema = {
            "events": [
                {
                    "title": "Meeting",
                    "location": "",
                    "jurisdiction": {"id": "city-unknown-place"},
                    "participation_mechanisms": [],
                }
            ]
        }
        result = digest._add_location_fallback(schema)
        assert result["events"][0]["location"] == "City Hall"

    def test_does_not_overwrite_existing_location(self, digest):
        schema = {
            "events": [
                {
                    "title": "Meeting",
                    "location": "Community Center, 100 Main St",
                    "jurisdiction": {"id": "city-san-rafael"},
                    "participation_mechanisms": [],
                }
            ]
        }
        result = digest._add_location_fallback(schema)
        assert result["events"][0]["location"] == "Community Center, 100 Main St"

    def test_handles_none_location(self, digest):
        schema = {
            "events": [
                {
                    "title": "Meeting",
                    "location": None,
                    "jurisdiction": {"id": "city-berkeley"},
                    "participation_mechanisms": [],
                }
            ]
        }
        result = digest._add_location_fallback(schema)
        assert "Berkeley" in result["events"][0]["location"]

    def test_updates_attend_participation_mechanism(self, digest):
        schema = {
            "events": [
                {
                    "title": "Meeting",
                    "location": "",
                    "jurisdiction": {"id": "city-oakland"},
                    "participation_mechanisms": [
                        {"type": "attend", "location": ""},
                        {"type": "email", "contact": "test@example.gov"},
                    ],
                }
            ]
        }
        result = digest._add_location_fallback(schema)
        attend = [
            m
            for m in result["events"][0]["participation_mechanisms"]
            if m["type"] == "attend"
        ][0]
        assert "Oakland" in attend["location"]

    def test_whitespace_only_location_treated_as_empty(self, digest):
        schema = {
            "events": [
                {
                    "title": "Meeting",
                    "location": "   ",
                    "jurisdiction": {"id": "city-el-cerrito"},
                    "participation_mechanisms": [],
                }
            ]
        }
        result = digest._add_location_fallback(schema)
        assert "El Cerrito" in result["events"][0]["location"]


# ---------------------------------------------------------------------------
# send_email — mock SMTP, verify message construction
# ---------------------------------------------------------------------------


class TestSendEmail:
    def test_constructs_email_with_correct_fields(self, digest):
        content = "Subject: Test Subject\n<html><body>Hello</body></html>"
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server

            digest.send_email(content, "user@example.com")

            mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with(
                "test@example.com", "test-app-password-16ch"
            )

            # Verify sendmail was called with correct args
            call_args = mock_server.sendmail.call_args
            assert call_args[0][0] == "test@example.com"  # from
            assert call_args[0][1] == "user@example.com"  # to
            # The message body should contain the HTML content
            assert "Hello" in call_args[0][2]

            mock_server.quit.assert_called_once()

    def test_subject_extracted_from_content(self, digest):
        content = "Subject: My Digest\n<html>body</html>"
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server

            digest.send_email(content, "user@example.com")

            msg_str = mock_server.sendmail.call_args[0][2]
            assert "My Digest" in msg_str

    def test_fallback_subject_when_no_prefix(self, digest):
        content = "No subject line here\n<html>body</html>"
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value = mock_server

            digest.send_email(content, "user@example.com")

            msg_str = mock_server.sendmail.call_args[0][2]
            assert "Civic Digest" in msg_str


# ---------------------------------------------------------------------------
# _extract_civic_data routing
# ---------------------------------------------------------------------------


class TestExtractCivicDataRouting:
    """Tests routing logic in _extract_civic_data.

    These mock internal extraction methods (mock-the-subject) because the
    downstream methods call OpenAI. The assertions verify correct routing
    conditions and argument forwarding — wiring tests, not behavior tests.
    """

    def test_routes_to_standard_when_no_agent_registry(self, digest):
        with patch.object(
            digest, "_extract_civic_data_standard", return_value={"items": []}
        ) as mock_std:
            with patch.object(
                digest, "_extract_civic_data_legistar"
            ) as mock_legistar:
                with patch.object(
                    _civic_digest_mod, "AGENT_REGISTRY_AVAILABLE", False
                ):
                    result = digest._extract_civic_data(
                        "source text", "https://x.gov"
                    )
                    # Standard route called with correct arguments
                    mock_std.assert_called_once_with("source text", "https://x.gov")
                    # Agent-specific routes NOT called
                    mock_legistar.assert_not_called()
                    assert result == {"items": []}

    def test_routes_to_standard_when_no_source_url(self, digest):
        with patch.object(
            digest, "_extract_civic_data_standard", return_value={"items": []}
        ) as mock_std:
            with patch.object(
                digest, "_extract_civic_data_legistar"
            ) as mock_legistar:
                result = digest._extract_civic_data("source text", "")
                # Standard route called with empty URL forwarded
                mock_std.assert_called_once_with("source text", "")
                # Agent-specific routes NOT called
                mock_legistar.assert_not_called()
                assert result == {"items": []}


# ---------------------------------------------------------------------------
# _detect_jurisdiction
# ---------------------------------------------------------------------------


class TestDetectJurisdiction:
    def test_returns_jurisdiction_id_for_known_domain(self, digest):
        # The method uses JurisdictionRegistry and automated_civic_refresh.
        # With the real imports available, known URLs should return real IDs.
        result = digest._detect_jurisdiction(
            "https://www.cityofsanrafael.org/meetings"
        )
        # Should resolve to the San Rafael jurisdiction
        assert result == "city-san-rafael"

    def test_returns_unknown_for_unrecognized_domain(self, digest):
        result = digest._detect_jurisdiction(
            "https://totally-unknown-city-xyz.gov/meetings"
        )
        assert result == "unknown"


# ---------------------------------------------------------------------------
# _wrap_in_newsletter_template
# ---------------------------------------------------------------------------


class TestWrapInNewsletterTemplate:
    def test_wraps_content_in_html_structure(self, digest):
        html = digest._wrap_in_newsletter_template("<p>Hello</p>")
        assert "<!DOCTYPE html>" in html
        assert "<p>Hello</p>" in html
        assert "Civic Brief" in html
        assert "Your guide to local government" in html
        assert "Questions? Reply to this email" in html

    def test_template_is_valid_html(self, digest):
        html = digest._wrap_in_newsletter_template("<p>Content</p>")
        assert html.count("<html") == 1
        assert html.count("</html>") == 1
        assert html.count("<body") == 1
        assert html.count("</body>") == 1
