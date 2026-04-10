"""
Tests for civic_schema_adapter.py — the schema transformation layer.

Focuses on pure-logic methods: type normalization, phone extraction, date parsing,
location normalization, engagement tier classification, action type extraction,
HTML-to-text conversion, validation, and dataclass serialization.

To run:
    pytest packages/civicos-services/tests/test_civic_schema_adapter.py -q --override-ini="addopts="
"""

from datetime import datetime, timezone

import pytest

from civicos_services.processing.civic_schema_adapter import (
    CivicSchemaAdapter,
    ContactInfo,
    EngagementInfo,
    Jurisdiction,
    SchemaCivicOpportunity,
    WikiEnhancement,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter():
    return CivicSchemaAdapter()


# ---------------------------------------------------------------------------
# normalize_project_type
# ---------------------------------------------------------------------------


class TestNormalizeProjectType:
    def test_primary_category_passes_through(self, adapter):
        assert adapter.normalize_project_type("transportation") == "transportation"
        assert adapter.normalize_project_type("housing") == "housing"
        assert adapter.normalize_project_type("budget") == "budget"

    def test_variation_maps_to_primary(self, adapter):
        assert adapter.normalize_project_type("traffic") == "transportation"
        assert adapter.normalize_project_type("transit") == "transportation"
        assert adapter.normalize_project_type("micromobility") == "transportation"
        assert adapter.normalize_project_type("recreation") == "parks"
        assert adapter.normalize_project_type("zoning") == "planning"
        assert adapter.normalize_project_type("ordinance") == "governance"
        assert adapter.normalize_project_type("behavioral health") == "health"

    def test_case_insensitive(self, adapter):
        assert adapter.normalize_project_type("TRANSPORTATION") == "transportation"
        assert adapter.normalize_project_type("Traffic") == "transportation"
        assert adapter.normalize_project_type("  Housing  ") == "housing"

    def test_unknown_falls_back_to_community(self, adapter):
        assert adapter.normalize_project_type("underwater_basket_weaving") == "community"
        assert adapter.normalize_project_type("") == "community"


# ---------------------------------------------------------------------------
# normalize_meeting_type
# ---------------------------------------------------------------------------


class TestNormalizeMeetingType:
    def test_exact_key_match(self, adapter):
        assert adapter.normalize_meeting_type("city council") == "city_council"
        assert adapter.normalize_meeting_type("planning commission") == "planning_commission"
        assert adapter.normalize_meeting_type("workshop") == "workshop"

    def test_substring_match(self, adapter):
        assert adapter.normalize_meeting_type("regular city council meeting") == "city_council"
        assert adapter.normalize_meeting_type("special planning commission hearing") == "planning_commission"
        assert adapter.normalize_meeting_type("public hearing on zoning") == "public_hearing"

    def test_case_insensitive(self, adapter):
        assert adapter.normalize_meeting_type("City Council") == "city_council"
        assert adapter.normalize_meeting_type("  WORKSHOP  ") == "workshop"

    def test_unknown_falls_back_to_community_meeting(self, adapter):
        assert adapter.normalize_meeting_type("special session") == "community_meeting"
        assert adapter.normalize_meeting_type("") == "community_meeting"


# ---------------------------------------------------------------------------
# _determine_enhanced_engagement_tier
# ---------------------------------------------------------------------------


class TestDetermineEngagementTier:
    def test_public_hearing_indicator_in_title(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Public Hearing on Rezoning", "Some description"
        )
        assert result == "public_hearing"

    def test_fee_schedule_triggers_public_hearing(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Planning & Development Fee Schedule Update", ""
        )
        assert result == "public_hearing"

    def test_zoning_triggers_public_hearing(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Zoning Amendment", "Development proposal for downtown"
        )
        assert result == "public_hearing"

    def test_second_reading_triggers_civic_action(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "[Second Reading] Ordinance 1234", "Amending parking rules"
        )
        assert result == "civic_action"

    def test_action_calendar_triggers_civic_action(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Action Calendar Item", "Approving a contract"
        )
        assert result == "civic_action"

    def test_budget_triggers_civic_action(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Consent item", "Budget review for FY26"
        )
        assert result == "civic_action"

    def test_agenda_section_contributes_to_classification(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {"agenda_section": "Action Calendar"}, "Item 5", "Approve contract"
        )
        assert result == "civic_action"

    def test_generic_item_returns_quick_action(self, adapter):
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Minutes Approval", "Approve minutes from last meeting"
        )
        assert result == "quick_action"

    def test_public_hearing_takes_priority_over_civic_action(self, adapter):
        # "public hearing" and "action calendar" both present — hearing wins
        result = adapter._determine_enhanced_engagement_tier(
            {}, "Public Hearing from Action Calendar", "Budget zoning"
        )
        assert result == "public_hearing"


# ---------------------------------------------------------------------------
# extract_jurisdiction_from_meeting
# ---------------------------------------------------------------------------


class TestExtractJurisdictionFromMeeting:
    def test_city_jurisdiction_id(self, adapter):
        j = adapter.extract_jurisdiction_from_meeting({
            "jurisdiction_id": "city-san-rafael",
            "website": "https://cityofsanrafael.org",
            "calendar_url": "https://cityofsanrafael.org/calendar",
        })
        assert j.id == "city-san-rafael"
        assert j.name == "San Rafael"
        assert j.type == "city"
        assert j.website == "https://cityofsanrafael.org"
        assert j.meeting_calendar_url == "https://cityofsanrafael.org/calendar"

    def test_county_marin_special_case(self, adapter):
        j = adapter.extract_jurisdiction_from_meeting({"jurisdiction_id": "county-marin"})
        assert j.id == "county-marin"
        assert j.name == "Marin County"

    def test_other_jurisdiction_id_format(self, adapter):
        j = adapter.extract_jurisdiction_from_meeting({"jurisdiction_id": "school-district-abc"})
        assert j.name == "School District Abc"

    def test_legacy_city_field_fallback(self, adapter):
        j = adapter.extract_jurisdiction_from_meeting({"city": "Mill Valley"})
        assert j.id == "city-mill-valley"
        assert j.name == "Mill Valley"

    def test_missing_city_fallback(self, adapter):
        j = adapter.extract_jurisdiction_from_meeting({})
        assert j.name == "Unknown City"
        assert j.id == "city-unknown-city"


# ---------------------------------------------------------------------------
# _extract_phone_number
# ---------------------------------------------------------------------------


class TestExtractPhoneNumber:
    def test_parenthesized_format(self, adapter):
        assert adapter._extract_phone_number("Call (415) 555-1234") == "(415) 555-1234"

    def test_dashed_format(self, adapter):
        assert adapter._extract_phone_number("Phone: 415-555-1234") == "415-555-1234"

    def test_ten_digit_format(self, adapter):
        assert adapter._extract_phone_number("Dial 4155551234") == "4155551234"

    def test_international_format(self, adapter):
        # Parenthesized pattern matches first, so +1 prefix is stripped
        assert adapter._extract_phone_number("+1 (415) 555-1234") == "(415) 555-1234"

    def test_empty_input(self, adapter):
        assert adapter._extract_phone_number("") == ""

    def test_zoom_meeting_id_ignored(self, adapter):
        assert adapter._extract_phone_number("Zoom ID: 840 9897 7308#") == ""

    def test_short_non_phone_passthrough(self, adapter):
        assert adapter._extract_phone_number("x4321") == "x4321"


# ---------------------------------------------------------------------------
# extract_action_type
# ---------------------------------------------------------------------------


class TestExtractActionType:
    def test_second_reading_bracket(self, adapter):
        assert adapter.extract_action_type("[Second Reading] Ordinance 123") == "second_reading"

    def test_public_hearing_bracket(self, adapter):
        assert adapter.extract_action_type("[Public Hearing] Zone Change") == "public_hearing"

    def test_consent_bracket(self, adapter):
        assert adapter.extract_action_type("[Consent] Minutes Approval") == "consent"

    def test_first_reading_bracket(self, adapter):
        assert adapter.extract_action_type("[First Reading] New Ordinance") == "first_reading"

    def test_public_comment_keyword(self, adapter):
        assert adapter.extract_action_type("Public Comment Period") == "public_comment"

    def test_contract_amendment(self, adapter):
        assert adapter.extract_action_type("Contract Amendment for Road Work") == "contract_amendment"

    def test_contract_award(self, adapter):
        assert adapter.extract_action_type("Contract Award for Sewer Repair") == "contract_award"

    def test_budget_adoption(self, adapter):
        assert adapter.extract_action_type("Adopt FY26 Budget") == "budget_adoption"

    def test_grant_action(self, adapter):
        assert adapter.extract_action_type("Accept Grant from HUD") == "grant_action"

    def test_ordinance_adoption(self, adapter):
        assert adapter.extract_action_type("Adopt Ordinance No. 2024-05") == "ordinance_adoption"

    def test_resolution(self, adapter):
        assert adapter.extract_action_type("Resolution Supporting Climate Action") == "resolution"

    def test_planning_action(self, adapter):
        assert adapter.extract_action_type("Zoning Variance Request") == "planning_action"

    def test_referral(self, adapter):
        assert adapter.extract_action_type("Referral to Finance Committee") == "referral"

    def test_policy_direction(self, adapter):
        assert adapter.extract_action_type("Direction to Staff on Parking Policy") == "policy_direction"

    def test_information_item(self, adapter):
        assert adapter.extract_action_type("Quarterly Report on Housing") == "information_item"

    def test_acceptance(self, adapter):
        assert adapter.extract_action_type("Accept Donation from Lions Club") == "acceptance"

    def test_generic_title_returns_action(self, adapter):
        assert adapter.extract_action_type("Miscellaneous Item") == "action"

    def test_bracket_takes_priority_over_keyword(self, adapter):
        # "[Second Reading]" should win even though "public comment" appears later
        assert adapter.extract_action_type("[Second Reading] Public Comment Ordinance") == "second_reading"


# ---------------------------------------------------------------------------
# _normalize_location
# ---------------------------------------------------------------------------


class TestNormalizeLocation:
    def test_dash_separator_becomes_comma(self, adapter):
        result = adapter._normalize_location("Council Chambers - 1400 5th Ave, Suite 100")
        assert result == "Council Chambers, 1400 5th Avenue, Suite 100"

    def test_street_abbreviations_expanded(self, adapter):
        assert "Street" in adapter._normalize_location("123 Main St, Suite 100")
        assert "Avenue" in adapter._normalize_location("456 Oak Ave, Floor 2")
        assert "Boulevard" in adapter._normalize_location("789 Sunset Blvd, Room 3")

    def test_empty_input_returns_not_specified(self, adapter):
        assert adapter._normalize_location("") == "Location not specified"
        assert adapter._normalize_location("   ") == "Location not specified"
        assert adapter._normalize_location(None) == "Location not specified"
        assert adapter._normalize_location("Location not specified") == "Location not specified"

    def test_whitespace_cleaned(self, adapter):
        result = adapter._normalize_location("  City   Hall,   Room  A  ")
        assert "  " not in result
        assert result == "City Hall, Room A"


# ---------------------------------------------------------------------------
# _get_engagement_info
# ---------------------------------------------------------------------------


class TestGetEngagementInfo:
    def test_public_comment_with_participation_info(self, adapter):
        result = adapter._get_engagement_info(
            "Public Comment Period",
            {"how_to_participate": "Sign up at the podium"},
            {},
        )
        assert result == "Sign up at the podium"

    def test_public_comment_falls_back_to_speaker_instructions(self, adapter):
        result = adapter._get_engagement_info(
            "Public Comment Period",
            {"how_to_participate": ""},
            {"speaker_instructions": "3 minutes per speaker"},
        )
        assert result == "3 minutes per speaker"

    def test_public_comment_with_zoom_fallback(self, adapter):
        result = adapter._get_engagement_info(
            "Public Comment Period",
            {},
            {
                "speaker_instructions": "Not specified",
                "meeting_info": {"zoom_link": "https://zoom.us/j/123", "dial_in_number": "1-669-444-9171"},
            },
        )
        assert "https://zoom.us/j/123" in result
        assert "1-669-444-9171" in result

    def test_public_comment_no_info_returns_empty(self, adapter):
        result = adapter._get_engagement_info("Public Comment Period", {}, {})
        assert result == ""

    def test_non_public_comment_returns_empty(self, adapter):
        result = adapter._get_engagement_info(
            "Consent Calendar Item",
            {"how_to_participate": "Attend meeting"},
            {"speaker_instructions": "Sign up"},
        )
        assert result == ""


# ---------------------------------------------------------------------------
# _clean_title_sponsor_names
# ---------------------------------------------------------------------------


class TestCleanTitleSponsorNames:
    def test_removes_colon_prefix(self, adapter):
        result = adapter._clean_title_sponsor_names("Lynn Cooper: Approve Minutes")
        assert result == "Approve Minutes"

    def test_removes_space_prefix_before_capital(self, adapter):
        result = adapter._clean_title_sponsor_names("Gael Alcock Accept Donation from Club")
        assert result == "Accept Donation from Club"

    def test_short_result_keeps_original(self, adapter):
        # If cleaning would produce something too short, keep original
        result = adapter._clean_title_sponsor_names("John Doe: Ok")
        assert result == "John Doe: Ok"

    def test_no_sponsor_name_unchanged(self, adapter):
        title = "Approve Contract for Sewer Repair"
        assert adapter._clean_title_sponsor_names(title) == title


# ---------------------------------------------------------------------------
# extract_engagement_structure
# ---------------------------------------------------------------------------


class TestExtractEngagementStructure:
    def test_from_item_data(self, adapter):
        result = adapter.extract_engagement_structure(
            {"engagement": {"webinar_id": "840 9897 7308", "speaker_time_minutes": 3}},
            {},
        )
        assert result.webinar_id == "840 9897 7308"
        assert result.speaker_time_minutes == 3
        assert result.dial_in is None

    def test_falls_back_to_meeting_data(self, adapter):
        result = adapter.extract_engagement_structure(
            {},
            {"engagement": {"dial_in": ["1-669-444-9171"], "raise_hand_phone": "*9"}},
        )
        assert result.dial_in == ["1-669-444-9171"]
        assert result.raise_hand_phone == "*9"

    def test_no_engagement_returns_none(self, adapter):
        assert adapter.extract_engagement_structure({}, {}) is None


# ---------------------------------------------------------------------------
# create_wiki_enhancement
# ---------------------------------------------------------------------------


class TestCreateWikiEnhancement:
    def test_uses_success_strategy(self, adapter):
        wiki = adapter.create_wiki_enhancement({"success_strategy": "Reference policy 4.1"})
        assert wiki.success_strategy == "Reference policy 4.1"
        assert wiki.precedent_examples == []
        assert wiki.related_opportunities == []

    def test_falls_back_to_deadline_guidance(self, adapter):
        wiki = adapter.create_wiki_enhancement({"deadline_guidance": "Submit 48h before"})
        assert wiki.success_strategy == "Submit 48h before"

    def test_default_when_empty(self, adapter):
        wiki = adapter.create_wiki_enhancement({})
        assert wiki.success_strategy == "Standard public comment procedures apply"

    def test_recommended_approach_passed(self, adapter):
        wiki = adapter.create_wiki_enhancement({
            "success_strategy": "X",
            "recommended_approach": "Show up early",
        })
        assert wiki.recommended_approach == "Show up early"


# ---------------------------------------------------------------------------
# convert_to_iso_datetime
# ---------------------------------------------------------------------------


class TestConvertToIsoDatetime:
    def test_iso_format_passthrough(self, adapter):
        iso = "2025-10-15T18:00:00-07:00"
        assert adapter.convert_to_iso_datetime(iso) == iso

    def test_iso_with_z_passthrough(self, adapter):
        iso = "2025-10-15T18:00:00Z"
        assert adapter.convert_to_iso_datetime(iso) == iso

    def test_yyyy_mm_dd_format(self, adapter):
        result = adapter.convert_to_iso_datetime("2025-10-15")
        # Should contain the date and default time 18:00
        assert "2025-10-15" in result
        assert "18:00" in result

    def test_yyyy_mm_dd_custom_default_time(self, adapter):
        result = adapter.convert_to_iso_datetime("2025-10-15", default_time="09:00")
        assert "09:00" in result

    def test_slash_format(self, adapter):
        result = adapter.convert_to_iso_datetime("10/15/2025")
        assert "2025" in result
        assert "18:00" in result

    def test_legistar_format(self, adapter):
        result = adapter.convert_to_iso_datetime("2025-10-09 00:00:00")
        assert "2025-10-09" in result

    def test_long_month_with_comma(self, adapter):
        result = adapter.convert_to_iso_datetime("March 15, 2025")
        assert "2025" in result
        assert "03" in result or "3" in result

    def test_long_month_with_time_and_ampm(self, adapter):
        result = adapter.convert_to_iso_datetime("September 23, 2025 7:00 pm")
        assert "2025" in result
        # 7:00 PM = 19:00
        assert "19:00" in result or "19:" in result

    def test_month_day_only_uses_current_year(self, adapter):
        result = adapter.convert_to_iso_datetime("March 15")
        current_year = str(datetime.now().year)
        assert current_year in result

    def test_empty_string_returns_current_timestamp(self, adapter):
        before = datetime.now(timezone.utc)
        result = adapter.convert_to_iso_datetime("")
        after = datetime.now(timezone.utc)
        # Should return a valid ISO timestamp close to "now"
        parsed = datetime.fromisoformat(result)
        assert parsed.year == before.year
        assert before.month == parsed.month
        assert before.day == parsed.day

    def test_unparseable_returns_current_timestamp(self, adapter):
        before = datetime.now(timezone.utc)
        result = adapter.convert_to_iso_datetime("not-a-date")
        parsed = datetime.fromisoformat(result)
        assert parsed.year == before.year
        assert before.month == parsed.month
        assert before.day == parsed.day


# ---------------------------------------------------------------------------
# html_to_text
# ---------------------------------------------------------------------------


class TestHtmlToText:
    def test_strips_tags(self, adapter):
        result = adapter.html_to_text("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result
        assert "<" not in result

    def test_preserves_list_bullets(self, adapter):
        html = "<ul><li>Item one</li><li>Item two</li></ul>"
        result = adapter.html_to_text(html)
        assert "Item one" in result
        assert "Item two" in result

    def test_decodes_html_entities(self, adapter):
        result = adapter.html_to_text("<p>Fish &amp; Chips &lt;3</p>")
        assert "Fish & Chips <3" in result

    def test_empty_input_returns_empty(self, adapter):
        assert adapter.html_to_text("") == ""
        assert adapter.html_to_text("   ") == ""

    def test_table_cells_get_separators(self, adapter):
        html = "<tr><td>Name</td><td>Value</td></tr>"
        result = adapter.html_to_text(html)
        assert "Name" in result
        assert "Value" in result


# ---------------------------------------------------------------------------
# validate_opportunity
# ---------------------------------------------------------------------------


class TestValidateOpportunity:
    def _make_valid_opportunity(self):
        return SchemaCivicOpportunity(
            id="test-id",
            title="Housing Hearing",
            original_title="Housing Hearing",
            description="Public hearing on housing policy",
            when="2025-10-15T18:00:00-07:00",
            deadline=None,
            engagement_info="Attend and speak",
            impact_summary="Affects 500 residents",
            source_url="https://example.gov",
            location="City Hall",
            meeting_type="public_hearing",
            project_type="housing",
            engagement_tier="public_hearing",
            jurisdiction=Jurisdiction(id="city-test", name="Test City", type="city"),
            contact_info=ContactInfo(email="clerk@test.gov"),
            wiki_enhancement=WikiEnhancement(success_strategy="Reference policy 4.1"),
            created_at="2025-10-01T00:00:00Z",
            scraped_from="https://example.gov",
        )

    def test_valid_opportunity_passes(self, adapter):
        opp = self._make_valid_opportunity()
        assert adapter.validate_opportunity(opp) is True

    def test_missing_title_fails(self, adapter):
        opp = self._make_valid_opportunity()
        opp.title = ""
        assert adapter.validate_opportunity(opp) is False

    def test_missing_description_fails(self, adapter):
        opp = self._make_valid_opportunity()
        opp.description = ""
        assert adapter.validate_opportunity(opp) is False

    def test_missing_jurisdiction_name_fails(self, adapter):
        opp = self._make_valid_opportunity()
        opp.jurisdiction.name = ""
        assert adapter.validate_opportunity(opp) is False

    def test_missing_email_fails(self, adapter):
        opp = self._make_valid_opportunity()
        opp.contact_info.email = ""
        assert adapter.validate_opportunity(opp) is False

    def test_missing_engagement_info_fails(self, adapter):
        opp = self._make_valid_opportunity()
        opp.engagement_info = ""
        assert adapter.validate_opportunity(opp) is False


# ---------------------------------------------------------------------------
# _extract_subject_line
# ---------------------------------------------------------------------------


class TestExtractSubjectLine:
    def test_extracts_from_subject_header(self, adapter):
        html = "Subject: Weekly Civic Digest\n<p>Content here</p>"
        assert adapter._extract_subject_line(html, "Test City") == "Weekly Civic Digest"

    def test_extracts_from_title_tag(self, adapter):
        html = "<html><title>Council Update</title><body>...</body></html>"
        assert adapter._extract_subject_line(html, "Test City") == "Council Update"

    def test_extracts_from_h1_tag(self, adapter):
        html = "<html><body><h1>Planning Commission Report</h1></body></html>"
        assert adapter._extract_subject_line(html, "Test City") == "Planning Commission Report"

    def test_extracts_from_markdown_header(self, adapter):
        html = "# Budget Review Summary\nContent here"
        assert adapter._extract_subject_line(html, "Test City") == "Budget Review Summary"

    def test_fallback_to_jurisdiction_name(self, adapter):
        html = "<p>No header here</p>"
        assert adapter._extract_subject_line(html, "San Rafael") == "San Rafael Civic Update"

    def test_empty_html_fallback(self, adapter):
        assert adapter._extract_subject_line("", "San Rafael") == "San Rafael Civic Update"

    def test_short_subject_skipped(self, adapter):
        # Subject shorter than 5 chars should be skipped
        html = "Subject: Hi\n<h1>Real Civic Update for City</h1>"
        result = adapter._extract_subject_line(html, "Test City")
        assert result == "Real Civic Update for City"


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_simple_dataclass(self, adapter):
        contact = ContactInfo(email="a@b.com", name="Jane", phone="555-1234")
        result = adapter.to_dict(contact)
        assert result["email"] == "a@b.com"
        assert result["name"] == "Jane"
        assert result["phone"] == "555-1234"

    def test_empty_strings_become_none(self, adapter):
        contact = ContactInfo(email="a@b.com", name="", title="", phone="")
        result = adapter.to_dict(contact)
        assert result["name"] is None
        assert result["title"] is None
        assert result["phone"] is None
        # Non-empty field stays as-is
        assert result["email"] == "a@b.com"

    def test_nested_dataclass(self, adapter):
        j = Jurisdiction(id="city-test", name="Test City", type="city")
        contact = ContactInfo(email="c@d.com")
        wiki = WikiEnhancement(success_strategy="Be prepared")
        opp = SchemaCivicOpportunity(
            id="opp-1",
            title="Hearing",
            original_title="Hearing",
            description="Desc",
            when="2025-10-15T18:00:00Z",
            deadline=None,
            engagement_info="Attend",
            impact_summary="Big impact",
            source_url="https://example.gov",
            location="City Hall",
            meeting_type="public_hearing",
            project_type="housing",
            engagement_tier="public_hearing",
            jurisdiction=j,
            contact_info=contact,
            wiki_enhancement=wiki,
            created_at="2025-10-01T00:00:00Z",
            scraped_from="https://example.gov",
        )
        result = adapter.to_dict(opp)
        assert result["jurisdiction"]["id"] == "city-test"
        assert result["contact_info"]["email"] == "c@d.com"
        assert result["wiki_enhancement"]["success_strategy"] == "Be prepared"

    def test_list_of_dataclasses(self, adapter):
        j = Jurisdiction(id="city-test", name="Test", type="city")
        result = adapter.to_dict(j)
        # list fields are in WikiEnhancement — test indirectly
        wiki = WikiEnhancement(
            success_strategy="X",
            precedent_examples=["case1", "case2"],
        )
        wiki_dict = adapter.to_dict(wiki)
        assert wiki_dict["precedent_examples"] == ["case1", "case2"]

    def test_none_values_stay_none(self, adapter):
        result = adapter.to_dict(ContactInfo(email="a@b.com", name="", phone=""))
        assert result["office"] is None  # empty string → None


# ---------------------------------------------------------------------------
# extract_contact_info
# ---------------------------------------------------------------------------


class TestExtractContactInfo:
    def test_opportunity_level_contact(self, adapter):
        contact = adapter.extract_contact_info(
            {"contact_email": "planning@city.gov", "contact_name": "Jane Doe"},
            {},
        )
        assert contact.email == "planning@city.gov"
        assert contact.name == "Jane Doe"

    def test_meeting_level_fallback(self, adapter):
        contact = adapter.extract_contact_info(
            {},
            {"public_comment_email": "clerk@city.gov", "phone": "(415) 555-1234"},
        )
        assert contact.email == "clerk@city.gov"
        assert contact.phone == "(415) 555-1234"

    def test_opportunity_email_takes_priority(self, adapter):
        contact = adapter.extract_contact_info(
            {"contact_email": "priority@city.gov"},
            {"public_comment_email": "fallback@city.gov"},
        )
        assert contact.email == "priority@city.gov"


# ---------------------------------------------------------------------------
# create_human_readable_time
# ---------------------------------------------------------------------------


class TestCreateHumanReadableTime:
    @pytest.fixture(autouse=True)
    def _ensure_pytz(self):
        """Skip tests if pytz is not available."""
        pytest.importorskip("pytz")

    def test_known_jurisdiction_returns_local_time(self, adapter):
        adapter.current_jurisdiction_id = "city-san-rafael"
        result = adapter.create_human_readable_time("2025-10-15T01:00:00Z")
        # UTC 01:00 = PDT 6:00 PM (Oct is DST)
        assert result is not None
        assert "PT" in result or "PDT" in result or "PST" in result

    def test_unknown_jurisdiction_still_returns_string(self, adapter):
        adapter.current_jurisdiction_id = "city-nowhere"
        result = adapter.create_human_readable_time("2025-10-15T18:00:00Z")
        # Should still produce a human-readable string with the correct date
        assert "Oct" in result
        assert "2025" in result
        assert ":" in result  # Contains a time component

    def test_invalid_datetime_returns_none(self, adapter):
        result = adapter.create_human_readable_time("not-a-date")
        assert result is None


# ---------------------------------------------------------------------------
# WikiEnhancement dataclass
# ---------------------------------------------------------------------------


class TestWikiEnhancementDataclass:
    def test_post_init_defaults_lists(self):
        wiki = WikiEnhancement(success_strategy="Test")
        assert wiki.precedent_examples == []
        assert wiki.related_opportunities == []

    def test_explicit_lists_not_overwritten(self):
        wiki = WikiEnhancement(
            success_strategy="Test",
            precedent_examples=["A"],
            related_opportunities=["B"],
        )
        assert wiki.precedent_examples == ["A"]
        assert wiki.related_opportunities == ["B"]


# ---------------------------------------------------------------------------
# adapt_civic_opportunity (integration-level, mocking time)
# ---------------------------------------------------------------------------


class TestAdaptCivicOpportunity:
    def test_produces_schema_opportunity_from_minimal_input(self, adapter):
        adapter.current_jurisdiction_id = "city-san-rafael"
        jurisdiction = Jurisdiction(id="city-san-rafael", name="San Rafael", type="city")
        item = {
            "title": "Approve Minutes",
            "description": "Approve regular council minutes",
            "impact_summary": "Administrative action",
            "project_type": "governance",
            "contact_email": "clerk@sanrafael.org",
        }
        meeting_data = {
            "date": "October 15, 2025",
            "start_time": "18:00",
            "location": "City Hall",
        }
        result = adapter.adapt_civic_opportunity(
            item, meeting_data, jurisdiction, "https://example.gov/meeting"
        )
        assert result is not None
        assert result.title == "Approve Minutes"
        assert result.project_type == "governance"
        assert result.jurisdiction.id == "city-san-rafael"
        assert result.action_type == "action"
        assert result.source_url == "https://example.gov/meeting"

    def test_deduplicates_description_same_as_title(self, adapter):
        adapter.current_jurisdiction_id = "city-test"
        jurisdiction = Jurisdiction(id="city-test", name="Test", type="city")
        item = {
            "title": "Housing Update",
            "description": "Housing Update",  # Same as title — should be cleared
            "project_type": "housing",
        }
        meeting_data = {"date": "2025-10-15", "start_time": "18:00"}
        result = adapter.adapt_civic_opportunity(
            item, meeting_data, jurisdiction, "https://example.gov"
        )
        assert result.description == ""

    def test_deduplicates_impact_same_as_title(self, adapter):
        adapter.current_jurisdiction_id = "city-test"
        jurisdiction = Jurisdiction(id="city-test", name="Test", type="city")
        item = {
            "title": "Budget Review",
            "description": "Annual review of the city budget",
            "impact_summary": "Budget Review",  # Same as title — should be cleared
            "project_type": "budget",
        }
        meeting_data = {"date": "2025-10-15", "start_time": "18:00"}
        result = adapter.adapt_civic_opportunity(
            item, meeting_data, jurisdiction, "https://example.gov"
        )
        assert result.impact_summary == ""

    def test_clears_deadline_when_no_reason(self, adapter):
        adapter.current_jurisdiction_id = "city-test"
        jurisdiction = Jurisdiction(id="city-test", name="Test", type="city")
        item = {
            "title": "Item",
            "description": "Desc",
            "project_type": "governance",
            # No deadline_reason
        }
        meeting_data = {"date": "2025-10-15", "start_time": "18:00"}
        result = adapter.adapt_civic_opportunity(
            item, meeting_data, jurisdiction, "https://example.gov"
        )
        assert result.deadline is None

    def test_bad_item_returns_none_or_raises(self, adapter):
        # None item causes AttributeError both in the try and the except handler
        with pytest.raises(AttributeError):
            adapter.adapt_civic_opportunity(None, {}, None, "")

    def test_event_date_used_over_meeting_date(self, adapter):
        adapter.current_jurisdiction_id = "city-test"
        jurisdiction = Jurisdiction(id="city-test", name="Test", type="city")
        item = {
            "title": "Workshop",
            "description": "Community workshop",
            "project_type": "governance",
            "event_date": "2025-11-01T19:00:00-07:00",
        }
        meeting_data = {"date": "2025-10-15", "start_time": "18:00"}
        result = adapter.adapt_civic_opportunity(
            item, meeting_data, jurisdiction, "https://example.gov"
        )
        assert "2025-11-01" in result.when
