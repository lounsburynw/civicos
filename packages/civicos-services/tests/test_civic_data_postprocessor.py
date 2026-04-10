"""
Tests for civic_data_postprocessor.py — universal accuracy and consistency fixes
for extracted civic data.

Covers: fallback categorization (keyword matching), engagement tier classification,
URL resolution, item validation, deduplication, meeting timing normalization,
meeting logistics enrichment, LLM-based categorization (with mocked OpenAI client),
and full post-processing pipeline.

To run:
    pytest packages/civicos-services/tests/test_civic_data_postprocessor.py -q --override-ini="addopts="
"""

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.processing.civic_data_postprocessor import CivicDataPostProcessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def processor():
    return CivicDataPostProcessor()


@pytest.fixture
def default_config():
    return {
        "jurisdiction_id": "unknown",
        "agent_type": "standard",
        "contact_email": "info@city.gov",
        "timezone": "America/Los_Angeles",
    }


@pytest.fixture
def san_rafael_config():
    return {
        "jurisdiction_id": "city-san-rafael",
        "agent_type": "standard",
        "contact_email": "clerk@cityofsanrafael.org",
        "timezone": "America/Los_Angeles",
        "website": "https://cityofsanrafael.org",
        "meeting_calendar_url": "https://cityofsanrafael.org/meetings",
    }


# ---------------------------------------------------------------------------
# _get_default_config
# ---------------------------------------------------------------------------


class TestGetDefaultConfig:
    def test_returns_expected_keys(self, processor):
        config = processor._get_default_config()
        assert config["jurisdiction_id"] == "unknown"
        assert config["agent_type"] == "standard"
        assert config["contact_email"] == "info@city.gov"
        assert config["timezone"] == "America/Los_Angeles"


# ---------------------------------------------------------------------------
# _fallback_categorization
# ---------------------------------------------------------------------------


class TestFallbackCategorization:
    def test_gogo_maps_to_accessibility(self, processor):
        """'gogo' keyword (no space) matches GoGo brand name."""
        item = {"title": "Contract with GoGo Technologies", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "accessibility"

    def test_go_go_with_space_does_not_match_gogo(self, processor):
        """'Go Go' (with space) does NOT match 'gogo' keyword."""
        item = {"title": "Contract with Go Go Technologies", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "city services"

    def test_wheelchair_maps_to_accessibility(self, processor):
        item = {"title": "Wheelchair ramp installation", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "accessibility"

    def test_seniors_maps_to_accessibility(self, processor):
        item = {"title": "Services for Seniors", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "accessibility"

    def test_paratransit_maps_to_accessibility(self, processor):
        item = {"title": "Paratransit budget", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "accessibility"

    def test_tnc_maps_to_mobility_pricing(self, processor):
        item = {"title": "TNC user tax implementation", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "mobility_pricing"

    def test_micromobility_maps_to_mobility_pricing(self, processor):
        item = {"title": "Micromobility fee schedule", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "mobility_pricing"

    def test_art_maps_to_arts_culture(self, processor):
        item = {"title": "Art Center renovation", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "arts_culture"

    def test_cultural_maps_to_arts_culture(self, processor):
        item = {"title": "Cultural festival planning", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "arts_culture"

    def test_community_dinner_maps_to_arts_culture(self, processor):
        item = {"title": "Community Dinner event", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "arts_culture"

    def test_homeless_maps_to_homeless_services(self, processor):
        item = {"title": "Homeless shelter funding", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "homeless_services"

    def test_drop_in_maps_to_homeless_services(self, processor):
        item = {"title": "Drop-in center hours", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "homeless_services"

    def test_housing_maps_to_building_development(self, processor):
        item = {"title": "Housing element update", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "building-development"

    def test_zoning_maps_to_building_development(self, processor):
        item = {"title": "Zoning variance request", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "building-development"

    def test_fee_schedule_maps_to_building_development(self, processor):
        item = {"title": "Development fee schedule update", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "building-development"

    def test_traffic_maps_to_transportation(self, processor):
        item = {"title": "Traffic signal timing", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "transportation"

    def test_parking_maps_to_transportation(self, processor):
        item = {"title": "Parking structure proposal", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "transportation"

    def test_health_maps_to_public_safety(self, processor):
        item = {"title": "Public health emergency plan", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "public safety"

    def test_police_maps_to_public_safety(self, processor):
        """'police' keyword matches — use title without 'art' substring in other words."""
        item = {"title": "Police staffing review", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "public safety"

    def test_art_substring_in_department_matches_arts_culture(self, processor):
        """'art' substring match means 'department' triggers arts_culture before public safety."""
        item = {"title": "Police department staffing", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "arts_culture"

    def test_disease_maps_to_public_safety(self, processor):
        item = {"title": "Disease intervention program", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "public safety"

    def test_grant_maps_to_taxes_finance(self, processor):
        item = {"title": "Federal grant application", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "taxes-finance"

    def test_budget_maps_to_taxes_finance(self, processor):
        item = {"title": "Annual budget review", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "taxes-finance"

    def test_parks_maps_to_parks_recreation(self, processor):
        item = {"title": "Parks master plan", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "parks-recreation"

    def test_recreation_maps_to_parks_recreation(self, processor):
        item = {"title": "Recreation center hours", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "parks-recreation"

    def test_marina_maps_to_parks_recreation(self, processor):
        item = {"title": "Marina maintenance", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "parks-recreation"

    def test_unknown_topic_defaults_to_city_services(self, processor):
        item = {"title": "Proclamation honoring local volunteer", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "city services"

    def test_empty_title_defaults_to_city_services(self, processor):
        item = {"title": "", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "city services"

    def test_keyword_in_change_field_detected(self, processor):
        item = {"title": "General item", "change": "Affects parking meters", "impact": ""}
        assert processor._fallback_categorization(item) == "transportation"

    def test_keyword_in_impact_field_detected(self, processor):
        item = {"title": "General item", "change": "", "impact": "Budget revenue increase"}
        assert processor._fallback_categorization(item) == "taxes-finance"

    def test_missing_change_and_impact_fields(self, processor):
        item = {"title": "Housing development proposal"}
        assert processor._fallback_categorization(item) == "building-development"

    def test_tax_keyword_matches_mobility_pricing_not_finance(self, processor):
        """'tax' appears in mobility_pricing keywords, matched before taxes-finance."""
        item = {"title": "New tax on rideshare", "change": "", "impact": ""}
        assert processor._fallback_categorization(item) == "mobility_pricing"


# ---------------------------------------------------------------------------
# _determine_engagement_tier
# ---------------------------------------------------------------------------


class TestDetermineEngagementTier:
    def test_public_hearing_flag_returns_public_hearing(self, processor):
        item = {"title": "Regular item", "public_hearing": True}
        assert processor._determine_engagement_tier(item) == "public_hearing"

    def test_public_hearing_false_not_treated_as_hearing(self, processor):
        item = {"title": "Regular item", "public_hearing": False}
        assert processor._determine_engagement_tier(item) == "civic_action"

    def test_ordinance_in_title_returns_civic_action(self, processor):
        item = {"title": "Ordinance 2025-10: Parking Regulations"}
        assert processor._determine_engagement_tier(item) == "civic_action"

    def test_resolution_in_title_returns_civic_action(self, processor):
        item = {"title": "Resolution supporting affordable housing"}
        assert processor._determine_engagement_tier(item) == "civic_action"

    def test_policy_in_title_returns_civic_action(self, processor):
        item = {"title": "New policy on remote work"}
        assert processor._determine_engagement_tier(item) == "civic_action"

    def test_consent_calendar_section_returns_quick_action(self, processor):
        item = {"title": "Approve minutes", "section": "Consent Calendar"}
        assert processor._determine_engagement_tier(item) == "quick_action"

    def test_consent_calendar_case_insensitive(self, processor):
        item = {"title": "Approve minutes", "section": "CONSENT CALENDAR"}
        assert processor._determine_engagement_tier(item) == "quick_action"

    def test_generic_item_defaults_to_civic_action(self, processor):
        item = {"title": "Staff report on community outreach"}
        assert processor._determine_engagement_tier(item) == "civic_action"

    def test_public_hearing_overrides_consent_calendar(self, processor):
        """public_hearing flag takes priority over section."""
        item = {"title": "Fee update", "public_hearing": True, "section": "Consent Calendar"}
        assert processor._determine_engagement_tier(item) == "public_hearing"

    def test_public_hearing_overrides_ordinance_keyword(self, processor):
        item = {"title": "Ordinance amendment", "public_hearing": True}
        assert processor._determine_engagement_tier(item) == "public_hearing"

    def test_no_section_field_defaults_to_civic_action(self, processor):
        item = {"title": "Budget discussion"}
        assert processor._determine_engagement_tier(item) == "civic_action"


# ---------------------------------------------------------------------------
# _resolve_source_url
# ---------------------------------------------------------------------------


class TestResolveSourceUrl:
    def test_item_number_appended_as_anchor(self, processor):
        result = processor._resolve_source_url(
            "https://city.gov/agendas", {"item_number": "Item 5"}
        )
        assert result == "https://city.gov/agendas#item-5"

    def test_spaces_converted_to_dashes_in_anchor(self, processor):
        result = processor._resolve_source_url(
            "https://city.gov/agendas", {"item_number": "Public Hearing 3"}
        )
        assert result == "https://city.gov/agendas#public-hearing-3"

    def test_no_item_number_returns_base_url(self, processor):
        result = processor._resolve_source_url("https://city.gov/agendas", {})
        assert result == "https://city.gov/agendas"

    def test_empty_item_number_returns_base_url(self, processor):
        result = processor._resolve_source_url("https://city.gov/agendas", {"item_number": ""})
        assert result == "https://city.gov/agendas"

    def test_none_item_number_returns_base_url(self, processor):
        result = processor._resolve_source_url(
            "https://city.gov/agendas", {"item_number": None}
        )
        assert result == "https://city.gov/agendas"


# ---------------------------------------------------------------------------
# _validate_item
# ---------------------------------------------------------------------------


class TestValidateItem:
    def test_item_with_title_is_valid(self, processor):
        assert processor._validate_item({"title": "Budget Review"}) is True

    def test_item_without_title_is_invalid(self, processor):
        assert processor._validate_item({"change": "Some change"}) is False

    def test_item_with_empty_title_is_invalid(self, processor):
        assert processor._validate_item({"title": ""}) is False

    def test_item_with_none_title_is_invalid(self, processor):
        assert processor._validate_item({"title": None}) is False

    def test_item_with_extra_fields_still_valid(self, processor):
        assert processor._validate_item({"title": "X", "extra": "data"}) is True


# ---------------------------------------------------------------------------
# _enhance_contact_info
# ---------------------------------------------------------------------------


class TestEnhanceContactInfo:
    def test_adds_contact_email_from_config(self, processor, san_rafael_config):
        item = {"title": "Test"}
        result = processor._enhance_contact_info(item, san_rafael_config)
        assert result["contact_email"] == "clerk@cityofsanrafael.org"

    def test_default_email_when_config_missing_key(self, processor):
        config = {"jurisdiction_id": "test"}
        item = {"title": "Test"}
        result = processor._enhance_contact_info(item, config)
        assert result["contact_email"] == "info@city.gov"

    def test_overwrites_existing_contact_email(self, processor, san_rafael_config):
        item = {"title": "Test", "contact_email": "old@example.com"}
        result = processor._enhance_contact_info(item, san_rafael_config)
        assert result["contact_email"] == "clerk@cityofsanrafael.org"


# ---------------------------------------------------------------------------
# _deduplicate_items
# ---------------------------------------------------------------------------


class TestDeduplicateItems:
    def test_no_duplicates_preserves_all(self, processor):
        items = [
            {"title": "Housing Update", "date": "2025-10-01"},
            {"title": "Budget Review", "date": "2025-10-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 2
        assert result[0]["title"] == "Housing Update"
        assert result[1]["title"] == "Budget Review"

    def test_exact_duplicate_removed(self, processor):
        items = [
            {"title": "Housing Update", "date": "2025-10-01"},
            {"title": "Housing Update", "date": "2025-10-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1
        assert result[0]["title"] == "Housing Update"

    def test_same_title_different_date_kept(self, processor):
        items = [
            {"title": "Housing Update", "date": "2025-10-01"},
            {"title": "Housing Update", "date": "2025-11-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 2

    def test_case_insensitive_duplicate_detection(self, processor):
        items = [
            {"title": "Housing Update", "date": "2025-10-01"},
            {"title": "HOUSING UPDATE", "date": "2025-10-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1
        assert result[0]["title"] == "Housing Update"  # Keeps first

    def test_whitespace_normalized_in_duplicate_check(self, processor):
        items = [
            {"title": "Housing  Update", "date": "2025-10-01"},
            {"title": "Housing Update", "date": "2025-10-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1

    def test_datetime_with_T_separator_extracts_date_part(self, processor):
        items = [
            {"title": "Budget Review", "date": "2025-10-01T18:00:00"},
            {"title": "Budget Review", "date": "2025-10-01T19:00:00"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1  # Same date part = duplicate

    def test_fallback_to_when_field_for_date(self, processor):
        items = [
            {"title": "Item A", "when": "2025-10-01T18:00:00"},
            {"title": "Item A", "when": "2025-10-01T19:00:00"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1

    def test_fallback_to_meeting_datetime_field(self, processor):
        items = [
            {"title": "Item A", "meeting_datetime": "2025-10-01T18:00:00"},
            {"title": "Item A", "meeting_datetime": "2025-10-01T19:00:00"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1

    def test_fallback_to_event_date_field(self, processor):
        items = [
            {"title": "Item A", "event_date": "2025-10-01"},
            {"title": "Item A", "event_date": "2025-10-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1

    def test_no_date_fields_uses_no_date_key(self, processor):
        items = [
            {"title": "Item A"},
            {"title": "Item A"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 1

    def test_items_with_and_without_date_not_duplicated(self, processor):
        items = [
            {"title": "Item A", "date": "2025-10-01"},
            {"title": "Item A"},  # no date
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 2  # Different date keys

    def test_empty_list_returns_empty(self, processor):
        assert processor._deduplicate_items([]) == []

    def test_preserves_order_of_first_occurrence(self, processor):
        items = [
            {"title": "Third", "date": "2025-10-01"},
            {"title": "First", "date": "2025-10-01"},
            {"title": "Third", "date": "2025-10-01"},
        ]
        result = processor._deduplicate_items(items)
        assert len(result) == 2
        assert result[0]["title"] == "Third"
        assert result[1]["title"] == "First"


# ---------------------------------------------------------------------------
# _extract_meeting_datetime
# ---------------------------------------------------------------------------


class TestExtractMeetingDatetime:
    def test_returns_existing_iso_datetime(self, processor, default_config):
        data = {"meeting": {"iso_datetime": "2025-10-01T18:00:00-07:00"}}
        result = processor._extract_meeting_datetime(data, default_config)
        assert result == "2025-10-01T18:00:00-07:00"

    def test_constructs_from_date_and_time(self, processor, default_config):
        data = {"meeting": {"date": "October 1, 2025", "start_time": "6:00 PM"}}
        result = processor._extract_meeting_datetime(data, default_config)
        assert result == "2025-10-01T18:00:00-07:00"

    def test_returns_none_when_no_meeting(self, processor, default_config):
        result = processor._extract_meeting_datetime({}, default_config)
        assert result is None

    def test_returns_none_with_date_only(self, processor, default_config):
        data = {"meeting": {"date": "October 1, 2025"}}
        result = processor._extract_meeting_datetime(data, default_config)
        assert result is None

    def test_returns_none_with_time_only(self, processor, default_config):
        data = {"meeting": {"start_time": "6:00 PM"}}
        result = processor._extract_meeting_datetime(data, default_config)
        assert result is None

    def test_returns_none_with_empty_date(self, processor, default_config):
        data = {"meeting": {"date": "", "start_time": "6:00 PM"}}
        result = processor._extract_meeting_datetime(data, default_config)
        assert result is None

    def test_returns_none_with_unparseable_date(self, processor, default_config):
        data = {"meeting": {"date": "not-a-date", "start_time": "not-a-time"}}
        result = processor._extract_meeting_datetime(data, default_config)
        assert result is None


# ---------------------------------------------------------------------------
# _normalize_meeting_timing
# ---------------------------------------------------------------------------


class TestNormalizeMeetingTiming:
    def test_sets_iso_datetime_on_meeting(self, processor, default_config):
        data = {
            "meeting": {"date": "October 1, 2025", "start_time": "6:00 PM"},
            "items": [{"title": "Item A"}, {"title": "Item B"}],
        }
        result = processor._normalize_meeting_timing(data, default_config)
        assert result["meeting"]["iso_datetime"] == "2025-10-01T18:00:00-07:00"

    def test_sets_when_and_deadline_on_items(self, processor, default_config):
        data = {
            "meeting": {"iso_datetime": "2025-10-01T18:00:00-07:00"},
            "items": [{"title": "Item A"}, {"title": "Item B"}],
        }
        result = processor._normalize_meeting_timing(data, default_config)
        assert result["items"][0]["when"] == "2025-10-01T18:00:00-07:00"
        assert result["items"][0]["deadline"] == "2025-10-01T18:00:00-07:00"
        assert result["items"][1]["when"] == "2025-10-01T18:00:00-07:00"

    def test_no_meeting_datetime_skips_items(self, processor, default_config):
        data = {"meeting": {}, "items": [{"title": "Item A"}]}
        result = processor._normalize_meeting_timing(data, default_config)
        assert "when" not in result["items"][0]
        assert "deadline" not in result["items"][0]

    def test_no_items_key_does_not_error(self, processor, default_config):
        data = {"meeting": {"iso_datetime": "2025-10-01T18:00:00-07:00"}}
        result = processor._normalize_meeting_timing(data, default_config)
        assert "items" not in result

    def test_no_meeting_key_does_not_error(self, processor, default_config):
        data = {"items": [{"title": "Item A"}]}
        result = processor._normalize_meeting_timing(data, default_config)
        assert "when" not in result["items"][0]


# ---------------------------------------------------------------------------
# _enhance_meeting_logistics
# ---------------------------------------------------------------------------


class TestEnhanceMeetingLogistics:
    def test_sets_meeting_type_to_city_council(self, processor, default_config):
        data = {"meeting": {"meeting_type": "community_meeting"}}
        result = processor._enhance_meeting_logistics(data, default_config)
        assert result["meeting"]["meeting_type"] == "city_council"

    def test_adds_public_comment_email_from_config(self, processor, san_rafael_config):
        data = {"meeting": {}}
        result = processor._enhance_meeting_logistics(data, san_rafael_config)
        assert result["meeting"]["public_comment_email"] == "clerk@cityofsanrafael.org"

    def test_does_not_overwrite_existing_comment_email(self, processor, san_rafael_config):
        data = {"meeting": {"public_comment_email": "existing@city.gov"}}
        result = processor._enhance_meeting_logistics(data, san_rafael_config)
        assert result["meeting"]["public_comment_email"] == "existing@city.gov"

    def test_adds_website_from_config(self, processor, san_rafael_config):
        data = {"meeting": {}}
        result = processor._enhance_meeting_logistics(data, san_rafael_config)
        assert result["meeting"]["website"] == "https://cityofsanrafael.org"

    def test_does_not_overwrite_existing_website(self, processor, san_rafael_config):
        data = {"meeting": {"website": "https://other.gov"}}
        result = processor._enhance_meeting_logistics(data, san_rafael_config)
        assert result["meeting"]["website"] == "https://other.gov"

    def test_adds_calendar_url_from_config(self, processor, san_rafael_config):
        data = {"meeting": {}}
        result = processor._enhance_meeting_logistics(data, san_rafael_config)
        assert result["meeting"]["calendar_url"] == "https://cityofsanrafael.org/meetings"

    def test_no_website_in_config_skips(self, processor, default_config):
        data = {"meeting": {}}
        result = processor._enhance_meeting_logistics(data, default_config)
        assert "website" not in result["meeting"]

    def test_creates_meeting_key_if_missing(self, processor, default_config):
        data = {}
        result = processor._enhance_meeting_logistics(data, default_config)
        assert result["meeting"]["meeting_type"] == "city_council"
        assert result["meeting"]["public_comment_email"] == "info@city.gov"

    def test_default_email_used_when_not_in_config(self, processor):
        config = {"jurisdiction_id": "test"}
        data = {"meeting": {}}
        result = processor._enhance_meeting_logistics(data, config)
        assert result["meeting"]["public_comment_email"] == "info@city.gov"


# ---------------------------------------------------------------------------
# _validate_civic_data
# ---------------------------------------------------------------------------


class TestValidateCivicData:
    def test_adds_processing_metadata(self, processor, default_config):
        data = {"items": []}
        result = processor._validate_civic_data(data, default_config)
        meta = result["processing_metadata"]
        assert meta["post_processed"] is True
        assert meta["jurisdiction_id"] == "unknown"
        assert meta["llm_categorization"] is False
        assert meta["version"] == "1.0"

    def test_metadata_timestamp_is_iso_format(self, processor, default_config):
        data = {}
        result = processor._validate_civic_data(data, default_config)
        processed_at = result["processing_metadata"]["processed_at"]
        # Should be parseable as ISO datetime
        dt = datetime.fromisoformat(processed_at)
        assert dt.year >= 2025

    def test_llm_categorization_true_when_client_present(self, default_config):
        processor = CivicDataPostProcessor(openai_client=MagicMock())
        data = {}
        result = processor._validate_civic_data(data, default_config)
        assert result["processing_metadata"]["llm_categorization"] is True

    def test_jurisdiction_id_from_config(self, processor):
        config = {"jurisdiction_id": "city-berkeley"}
        data = {}
        result = processor._validate_civic_data(data, config)
        assert result["processing_metadata"]["jurisdiction_id"] == "city-berkeley"

    def test_preserves_existing_data(self, processor, default_config):
        data = {"items": [{"title": "A"}], "meeting": {"city": "Berkeley"}}
        result = processor._validate_civic_data(data, default_config)
        assert result["items"] == [{"title": "A"}]
        assert result["meeting"]["city"] == "Berkeley"


# ---------------------------------------------------------------------------
# _map_project_category_llm — fallback path (no client)
# ---------------------------------------------------------------------------


class TestMapProjectCategoryNoLLM:
    def test_uses_fallback_when_no_client(self, processor):
        item = {"title": "Housing element update", "change": "", "impact": ""}
        result = processor._map_project_category_llm(item)
        assert result == "building-development"

    def test_empty_title_falls_back_to_city_services(self, processor):
        item = {"title": "", "change": "", "impact": ""}
        result = processor._map_project_category_llm(item)
        assert result == "city services"


# ---------------------------------------------------------------------------
# _map_project_category_llm — LLM path (mocked client)
# ---------------------------------------------------------------------------


class TestMapProjectCategoryWithLLM:
    def test_valid_llm_category_returned(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "transportation"
        mock_client.chat.completions.create.return_value = mock_response

        processor = CivicDataPostProcessor(openai_client=mock_client)
        item = {"title": "Bus route expansion", "change": "New route", "impact": ""}
        result = processor._map_project_category_llm(item)
        assert result == "transportation"

    def test_invalid_llm_category_falls_back(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "invalid_category"
        mock_client.chat.completions.create.return_value = mock_response

        processor = CivicDataPostProcessor(openai_client=mock_client)
        item = {"title": "Parks master plan", "change": "", "impact": ""}
        result = processor._map_project_category_llm(item)
        assert result == "parks-recreation"  # Fallback keyword match

    def test_llm_exception_falls_back(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        processor = CivicDataPostProcessor(openai_client=mock_client)
        item = {"title": "Budget review", "change": "", "impact": ""}
        result = processor._map_project_category_llm(item)
        assert result == "taxes-finance"  # Fallback keyword match

    def test_llm_context_includes_all_fields(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "transportation"
        mock_client.chat.completions.create.return_value = mock_response

        processor = CivicDataPostProcessor(openai_client=mock_client)
        item = {
            "title": "Route change",
            "change": "Modify bus schedule",
            "impact": "Better coverage",
            "department": "Transit",
        }
        result = processor._map_project_category_llm(item)

        # Assert the return value, not just the call
        assert result == "transportation"

        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][1]["content"]
        assert "Route change" in prompt
        assert "Modify bus schedule" in prompt
        assert "Better coverage" in prompt
        assert "Transit" in prompt


# ---------------------------------------------------------------------------
# _process_item
# ---------------------------------------------------------------------------


class TestProcessItem:
    def test_sets_source_url_and_project_type(self, processor, default_config):
        item = {"title": "Housing Update", "item_number": "Item 3"}
        result = processor._process_item(item, "https://city.gov/agenda", default_config)
        assert result["source_url"] == "https://city.gov/agenda#item-3"
        assert result["project_type"] == "building-development"

    def test_sets_engagement_tier(self, processor, default_config):
        item = {"title": "Approve minutes", "section": "Consent Calendar"}
        result = processor._process_item(item, "https://city.gov", default_config)
        assert result["engagement_tier"] == "quick_action"

    def test_sets_contact_email(self, processor, default_config):
        item = {"title": "Test item"}
        result = processor._process_item(item, "https://city.gov", default_config)
        assert result["contact_email"] == "info@city.gov"

    def test_returns_none_for_invalid_item(self, processor, default_config):
        item = {"change": "No title present"}
        result = processor._process_item(item, "https://city.gov", default_config)
        assert result is None

    def test_does_not_mutate_original_item(self, processor, default_config):
        item = {"title": "Test item"}
        original_keys = set(item.keys())
        processor._process_item(item, "https://city.gov", default_config)
        assert set(item.keys()) == original_keys


# ---------------------------------------------------------------------------
# _get_jurisdiction_config
# ---------------------------------------------------------------------------


class TestGetJurisdictionConfig:
    def test_returns_default_when_jurisdiction_not_found(self, processor):
        """Real method called with a jurisdiction that won't exist in CITY_CONFIGS."""
        config = processor._get_jurisdiction_config("city-nonexistent-xyz-12345")
        # Whether import succeeds (returns default for missing) or fails (ImportError path),
        # the result should be the default config with known values
        assert config["jurisdiction_id"] == "unknown"
        assert config["agent_type"] == "standard"
        assert config["contact_email"] == "info@city.gov"
        assert config["timezone"] == "America/Los_Angeles"

    def test_returns_default_on_import_error(self, processor):
        """When CITY_CONFIGS import fails, should fall back to default config."""
        import builtins
        import sys

        original_import = builtins.__import__

        def import_raising(name, *args, **kwargs):
            if "automated_civic_refresh" in name:
                raise ImportError("mocked for test")
            return original_import(name, *args, **kwargs)

        # Clear cached module so __import__ is actually called
        mod_key = "civicos_services.monitoring.automated_civic_refresh"
        saved = sys.modules.pop(mod_key, None)
        try:
            with patch("builtins.__import__", side_effect=import_raising):
                config = processor._get_jurisdiction_config("city-anything")
        finally:
            if saved is not None:
                sys.modules[mod_key] = saved

        assert config["jurisdiction_id"] == "unknown"
        assert config["agent_type"] == "standard"
        assert config["contact_email"] == "info@city.gov"
        assert config["timezone"] == "America/Los_Angeles"


# ---------------------------------------------------------------------------
# process_civic_data — full pipeline
# ---------------------------------------------------------------------------


class TestProcessCivicData:
    def test_full_pipeline_processes_items(self, processor):
        data = {
            "meeting": {"iso_datetime": "2025-10-01T18:00:00-07:00"},
            "items": [
                {"title": "Housing Element Update", "item_number": "Item 1"},
                {"title": "Parks Master Plan", "item_number": "Item 2"},
            ],
        }
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(
                data, "https://city.gov/agenda", "city-test"
            )

        assert len(result["items"]) == 2
        assert result["items"][0]["project_type"] == "building-development"
        assert result["items"][1]["project_type"] == "parks-recreation"
        assert result["items"][0]["source_url"] == "https://city.gov/agenda#item-1"
        assert result["items"][1]["source_url"] == "https://city.gov/agenda#item-2"
        assert result["processing_metadata"]["post_processed"] is True

    def test_pipeline_removes_invalid_items(self, processor):
        data = {
            "meeting": {},
            "items": [
                {"title": "Valid item"},
                {"change": "Missing title"},  # Invalid
                {"title": "Another valid item"},
            ],
        }
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(data, "https://city.gov", "city-test")

        assert len(result["items"]) == 2
        assert result["items"][0]["title"] == "Valid item"
        assert result["items"][1]["title"] == "Another valid item"

    def test_pipeline_deduplicates_items(self, processor):
        data = {
            "meeting": {},
            "items": [
                {"title": "Housing Update", "date": "2025-10-01"},
                {"title": "Housing Update", "date": "2025-10-01"},
                {"title": "Budget Review", "date": "2025-10-01"},
            ],
        }
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(data, "https://city.gov", "city-test")

        titles = [item["title"] for item in result["items"]]
        assert titles.count("Housing Update") == 1
        assert "Budget Review" in titles

    def test_pipeline_sets_meeting_type(self, processor):
        data = {"meeting": {"meeting_type": "community_meeting"}, "items": []}
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(data, "https://city.gov", "city-test")

        assert result["meeting"]["meeting_type"] == "city_council"

    def test_pipeline_without_items_key(self, processor):
        data = {"meeting": {"iso_datetime": "2025-10-01T18:00:00-07:00"}}
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(data, "https://city.gov", "city-test")

        assert "items" not in result
        assert result["processing_metadata"]["post_processed"] is True

    def test_pipeline_does_not_mutate_input(self, processor):
        data = {
            "meeting": {"meeting_type": "community_meeting"},
            "items": [{"title": "Item A"}],
        }
        import copy

        original = copy.deepcopy(data)
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            processor.process_civic_data(data, "https://city.gov", "city-test")

        # The top-level dict is copied, so original should be preserved
        assert "processing_metadata" not in original

    def test_pipeline_sets_timing_on_items(self, processor):
        data = {
            "meeting": {"iso_datetime": "2025-10-01T18:00:00-07:00"},
            "items": [{"title": "Budget Review"}],
        }
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(data, "https://city.gov", "city-test")

        assert result["items"][0]["when"] == "2025-10-01T18:00:00-07:00"
        assert result["items"][0]["deadline"] == "2025-10-01T18:00:00-07:00"

    def test_pipeline_empty_items_list(self, processor):
        data = {"meeting": {}, "items": []}
        with patch.object(processor, "_get_jurisdiction_config") as mock_config:
            mock_config.return_value = processor._get_default_config()
            result = processor.process_civic_data(data, "https://city.gov", "city-test")

        assert result["items"] == []
        assert result["processing_metadata"]["post_processed"] is True


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_no_openai_client(self):
        processor = CivicDataPostProcessor()
        assert processor.openai_client is None

    def test_with_openai_client(self):
        client = MagicMock()
        processor = CivicDataPostProcessor(openai_client=client)
        assert processor.openai_client is client

    def test_standard_categories_populated(self):
        processor = CivicDataPostProcessor()
        assert "accessibility" in processor.standard_categories
        assert "transportation" in processor.standard_categories
        assert "city services" in processor.standard_categories
        assert len(processor.standard_categories) == 10
