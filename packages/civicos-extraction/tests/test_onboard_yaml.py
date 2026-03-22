"""
Tests for jurisdiction YAML generation during onboarding.

Validates that _generate_jurisdiction_yaml() produces complete, valid YAML
for city, county, and state levels with all required fields.
"""

import yaml
import pytest
from datetime import date

from civicos_extraction.onboard import (
    _generate_jurisdiction_yaml,
    _default_refresh_policies,
    _default_governing_body,
    _usaspending_from_candidates,
)


# --- Fixtures ---

@pytest.fixture
def city_config():
    """Minimal extraction config for a city (ProudCity platform)."""
    return {
        "source_type": "proudcity",
        "base_url": "https://www.cityofexample.org",
        "archives": {
            "city_council": "/city-council-meetings/",
            "planning_commission": "/planning-commission-meetings/",
        },
        "metadata": {
            "detected_platform": "proudcity",
            "scan_provenance": "auto",
        },
    }


@pytest.fixture
def county_config():
    """Minimal extraction config for a county (Granicus platform)."""
    return {
        "source_type": "granicus",
        "base_url": "https://marin.granicus.com",
        "archives": {
            "board_of_supervisors": {"publisher_id": 5, "view_id": 5},
        },
    }


@pytest.fixture
def state_config():
    """Minimal extraction config for a state."""
    return {
        "source_type": "standard",
        "base_url": "https://www.legislature.ca.gov",
    }


@pytest.fixture
def usaspending_candidates():
    """Mock USAspending discovery results."""
    return [
        {
            "recipient_name": "CITY OF EXAMPLEVILLE",
            "award_count": 15,
            "total_amount": 2500000.0,
            "is_government": True,
        },
        {
            "recipient_name": "EXAMPLEVILLE COOPERATIVE",
            "award_count": 3,
            "total_amount": 50000.0,
            "is_government": False,
        },
    ]


# --- Helper ---

def _parse_yaml(yaml_str: str) -> dict:
    """Parse YAML string, stripping the header comment."""
    return yaml.safe_load(yaml_str)


# --- Tests: _default_refresh_policies ---

class TestDefaultRefreshPolicies:
    def test_city_policies(self):
        policies = _default_refresh_policies("city")
        assert "meetings" in policies
        assert "issues" in policies
        assert "municipal_code" in policies
        assert "legislation" in policies
        assert policies["meetings"]["interval"] == "1d"
        assert policies["municipal_code"]["strategy"] == "content_hash"

    def test_state_policies(self):
        policies = _default_refresh_policies("state")
        assert "legislation" in policies
        assert "meetings" not in policies
        assert "issues" not in policies

    def test_federal_policies(self):
        policies = _default_refresh_policies("federal")
        assert "legislation" in policies
        assert len(policies) == 1


# --- Tests: _default_governing_body ---

class TestDefaultGoverningBody:
    def test_city_body(self):
        body = _default_governing_body("Exampleville", "city")
        assert body["name"] == "Exampleville City Council"
        assert body["members_title"] == "Mayor and Council Members"

    def test_county_body(self):
        body = _default_governing_body("Marin", "county")
        assert "Board of Supervisors" in body["name"]

    def test_town_body(self):
        body = _default_governing_body("Corte Madera", "town")
        assert "Town Council" in body["name"]

    def test_state_body(self):
        body = _default_governing_body("California", "state")
        assert body["name"] is None


# --- Tests: _usaspending_from_candidates ---

class TestUSAspendingFromCandidates:
    def test_picks_government_candidate(self, usaspending_candidates):
        result = _usaspending_from_candidates("Exampleville", usaspending_candidates)
        assert result is not None
        assert "usaspending" in result
        assert "CITY OF EXAMPLEVILLE" in result["usaspending"]["search_names"]
        # Should include reversed form
        assert "EXAMPLEVILLE, CITY OF" in result["usaspending"]["search_names"]

    def test_empty_candidates_returns_none(self):
        result = _usaspending_from_candidates("Test", [])
        assert result is None

    def test_none_candidates_returns_none(self):
        result = _usaspending_from_candidates("Test", None)
        assert result is None

    def test_non_government_fallback(self):
        candidates = [
            {"recipient_name": "TEST CORP", "award_count": 5, "is_government": False},
        ]
        result = _usaspending_from_candidates("Test", candidates)
        assert result is not None
        assert "TEST CORP" in result["usaspending"]["search_names"]


# --- Tests: _generate_jurisdiction_yaml (city) ---

class TestGenerateCityYAML:
    def test_identity_fields(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            website="https://www.cityofexample.org", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert doc["jurisdiction_id"] == "city-exampleville"
        assert doc["level"] == "city"
        assert doc["display_name"] == "Exampleville"

    def test_parent_jurisdictions(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            state_abbrev="CA", county="Marin County",
        )
        doc = _parse_yaml(yaml_str)
        assert "state-california" in doc["parent_jurisdictions"]
        assert "country-united-states" in doc["parent_jurisdictions"]

    def test_contact_info_complete(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            contact_email="clerk@example.org", website="https://example.org",
        )
        doc = _parse_yaml(yaml_str)
        ci = doc["contact_info"]
        assert ci["clerk_email"] == "clerk@example.org"
        assert ci["website"] == "https://example.org"
        assert "public_comment_deadline" in ci
        assert "in_person_time_limit" in ci
        assert "city_hall_address" in ci

    def test_governing_body_present(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        assert "governing_body" in doc
        assert doc["governing_body"]["name"] == "Exampleville City Council"

    def test_data_sources_meetings(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        meetings = doc["data_sources"]["meetings"]
        assert meetings["source_type"] == "proudcity"
        assert meetings["base_url"] == "https://www.cityofexample.org"
        assert "city_council" in meetings["archives"]

    def test_data_sources_provenance_stripped(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        meetings = doc["data_sources"]["meetings"]
        # scan_provenance should be stripped (ends with _provenance)
        metadata = meetings.get("metadata", {})
        assert "scan_provenance" not in metadata
        assert "detected_platform" in metadata

    def test_financial_context(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            state_abbrev="CA", county="Marin County",
        )
        doc = _parse_yaml(yaml_str)
        assert doc["financial"]["state"] == "CA"
        assert doc["financial"]["county"] == "Marin"

    def test_refresh_policies(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        assert "refresh" in doc
        assert doc["refresh"]["meetings"]["interval"] == "1d"
        assert doc["refresh"]["municipal_code"]["strategy"] == "content_hash"

    def test_ingestion_tiers(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        ing = doc["ingestion"]
        assert ing["meetings"] is True
        assert ing["issues"] is True
        assert ing["municipal_code"] is True
        assert ing["transcription"] is False
        assert ing["vector_indexing"] is True

    def test_modal_config(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        assert doc["modal"]["min_containers"] == 0
        assert "civicos-env" in doc["modal"]["secrets"]

    def test_tools_config(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        assert doc["tools_enabled"] is None
        assert doc["tool_overrides"] == {}

    def test_metadata(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        assert doc["metadata"]["created"] == date.today().isoformat()
        assert "Auto-generated" in doc["metadata"]["notes"]

    def test_usaspending_integration(self, city_config, usaspending_candidates):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            usaspending_candidates=usaspending_candidates,
        )
        doc = _parse_yaml(yaml_str)
        assert "federal_programs" in doc
        assert "CITY OF EXAMPLEVILLE" in doc["federal_programs"]["usaspending"]["search_names"]

    def test_zip_code_included(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            zip_code="94901",
        )
        doc = _parse_yaml(yaml_str)
        assert "zip_codes" in doc
        assert "94901" in doc["zip_codes"]

    def test_no_state_info_for_city(self, city_config):
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
        )
        doc = _parse_yaml(yaml_str)
        assert "state_info" not in doc


# --- Tests: _generate_jurisdiction_yaml (county) ---

class TestGenerateCountyYAML:
    def test_county_identity(self, county_config):
        yaml_str = _generate_jurisdiction_yaml(
            "county-marin", "Marin", county_config,
            level="county", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert doc["level"] == "county"
        assert doc["jurisdiction_id"] == "county-marin"

    def test_county_no_county_in_financial(self, county_config):
        yaml_str = _generate_jurisdiction_yaml(
            "county-marin", "Marin", county_config,
            level="county", state_abbrev="CA", county="Marin County",
        )
        doc = _parse_yaml(yaml_str)
        # County's own name shouldn't appear as financial.county (redundant)
        assert "county" not in doc["financial"]

    def test_county_no_zip_codes(self, county_config):
        yaml_str = _generate_jurisdiction_yaml(
            "county-marin", "Marin", county_config,
            level="county", zip_code="94901",
        )
        doc = _parse_yaml(yaml_str)
        # Counties span many zips — single zip should not be included
        assert "zip_codes" not in doc or doc.get("zip_codes") == []

    def test_county_governing_body(self, county_config):
        yaml_str = _generate_jurisdiction_yaml(
            "county-marin", "Marin", county_config,
            level="county",
        )
        doc = _parse_yaml(yaml_str)
        assert "Board of Supervisors" in doc["governing_body"]["name"]


# --- Tests: _generate_jurisdiction_yaml (state) ---

class TestGenerateStateYAML:
    def test_state_identity(self, state_config):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert doc["level"] == "state"
        assert doc["jurisdiction_id"] == "state-california"

    def test_state_info_present(self, state_config):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert "state_info" in doc
        assert doc["state_info"]["abbreviation"] == "CA"
        assert doc["state_info"]["governor_title"] == "Governor"

    def test_state_no_governing_body(self, state_config):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        # States don't get governing_body (use state_info instead)
        assert "governing_body" not in doc

    def test_state_refresh_policies(self, state_config):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert "legislation" in doc["refresh"]
        assert "meetings" not in doc["refresh"]

    def test_state_parent_is_country(self, state_config):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert doc["parent_jurisdictions"] == ["country-united-states"]

    def test_state_no_usaspending(self, state_config, usaspending_candidates):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
            usaspending_candidates=usaspending_candidates,
        )
        doc = _parse_yaml(yaml_str)
        # USAspending only for city/county
        assert "federal_programs" not in doc

    def test_state_legislation_source(self, state_config):
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        assert doc["data_sources"].get("legislation") == "leginfo_api"


# --- Tests: Validation integration ---

class TestYAMLValidation:
    """Test that generated YAML loads and validates via jurisdiction_config."""

    def test_city_yaml_validates(self, city_config):
        from civicos.jurisdiction_config import validate_jurisdiction_config
        yaml_str = _generate_jurisdiction_yaml(
            "city-exampleville", "Exampleville", city_config,
            website="https://www.cityofexample.org",
            state_abbrev="CA", county="Marin County",
        )
        doc = _parse_yaml(yaml_str)
        config = _load_config_from_dict(doc)
        result = validate_jurisdiction_config(config)
        # Should have no errors (warnings are OK)
        errors = [i for i in result.issues if i.severity == "error"]
        assert result.is_valid, f"Validation errors: {[e.message for e in errors]}"

    def test_county_yaml_validates(self, county_config):
        from civicos.jurisdiction_config import validate_jurisdiction_config
        yaml_str = _generate_jurisdiction_yaml(
            "county-marin", "Marin", county_config,
            level="county", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        config = _load_config_from_dict(doc)
        result = validate_jurisdiction_config(config)
        errors = [i for i in result.issues if i.severity == "error"]
        assert result.is_valid, f"Validation errors: {[e.message for e in errors]}"

    def test_state_yaml_validates(self, state_config):
        from civicos.jurisdiction_config import validate_jurisdiction_config
        yaml_str = _generate_jurisdiction_yaml(
            "state-california", "California", state_config,
            level="state", state_abbrev="CA",
        )
        doc = _parse_yaml(yaml_str)
        config = _load_config_from_dict(doc)
        result = validate_jurisdiction_config(config)
        errors = [i for i in result.issues if i.severity == "error"]
        assert result.is_valid, f"Validation errors: {[e.message for e in errors]}"


def _load_config_from_dict(data: dict):
    """Build a JurisdictionConfig from a raw YAML dict (mirrors load_jurisdiction_config)."""
    from civicos.jurisdiction_config import (
        JurisdictionConfig,
        ContactInfo,
        GoverningBody,
        StateInfo,
        DataSources,
        MeetingsSource,
        TranscriptsSource,
        FinancialContext,
        FederalPrograms,
        USAspendingConfig,
        ModalConfig,
        Metadata,
    )

    contact_data = data.get("contact_info") or {}
    contact_info = ContactInfo(
        clerk_email=contact_data.get("clerk_email") or "",
        city_hall_address=contact_data.get("city_hall_address") or "",
        phone=contact_data.get("phone") or "",
        website=contact_data.get("website") or "",
        public_comment_deadline=contact_data.get("public_comment_deadline", "5:00 PM day of meeting"),
        in_person_time_limit=contact_data.get("in_person_time_limit", "3 minutes"),
        public_comment_subject=contact_data.get("public_comment_subject", "Public Comment - [Agenda Item Title]"),
    )

    body_data = data.get("governing_body") or {}
    governing_body = GoverningBody(
        name=body_data.get("name") or "City Council",
        members_title=body_data.get("members_title") or "Mayor and Council Members",
        meeting_schedule=body_data.get("meeting_schedule") or "",
        meeting_location=body_data.get("meeting_location") or "",
    )

    state_data = data.get("state_info") or {}
    state_info = StateInfo(
        abbreviation=state_data.get("abbreviation") or "",
        timezone=state_data.get("timezone") or "America/Los_Angeles",
        legislature=state_data.get("legislature") or "",
        governor_title=state_data.get("governor_title") or "Governor",
    )

    # Parse meetings
    ds_data = data.get("data_sources") or {}
    meetings_data = ds_data.get("meetings") or {}
    meetings = MeetingsSource(
        source_type=meetings_data.get("source_type") or "",
        base_url=meetings_data.get("base_url") or "",
        auto_discover=meetings_data.get("auto_discover", False),
        archives=meetings_data.get("archives") or {},
    )

    transcripts_data = ds_data.get("transcripts") or {}
    transcripts = TranscriptsSource(
        source=transcripts_data.get("source") or "",
        playlist_id=transcripts_data.get("playlist_id"),
    )

    data_sources = DataSources(
        meetings=meetings,
        issues=ds_data.get("issues") or "",
        budget=ds_data.get("budget") or "",
        municipal_code=ds_data.get("municipal_code") or "",
        transcripts=transcripts,
        legislation=ds_data.get("legislation") or "",
        revenue=ds_data.get("revenue") or "",
        expenditures=ds_data.get("expenditures") or "",
        funding=ds_data.get("funding") or "",
    )

    fin_data = data.get("financial") or {}
    financial = FinancialContext(
        state=fin_data.get("state") or "",
        county=fin_data.get("county") or "",
        sco=fin_data.get("sco") or {},
    )

    fed_data = data.get("federal_programs") or {}
    usa_data = fed_data.get("usaspending") or {}
    federal_programs = FederalPrograms(
        hud_grantee=fed_data.get("hud_grantee") or "",
        hud_relationship=fed_data.get("hud_relationship") or "",
        usaspending=USAspendingConfig(
            search_names=usa_data.get("search_names") or [],
            allowed_names=usa_data.get("allowed_names") or [],
            recipient_uei=usa_data.get("recipient_uei") or "",
        ),
        notes=fed_data.get("notes") or "",
    )

    modal_data = data.get("modal") or {}
    modal = ModalConfig(
        min_containers=modal_data.get("min_containers", 0),
        secrets=modal_data.get("secrets") or ["civicos-env"],
    )

    meta_data = data.get("metadata") or {}
    metadata = Metadata(
        created=meta_data.get("created") or "",
        updated=meta_data.get("updated") or "",
        notes=meta_data.get("notes") or "",
    )

    return JurisdictionConfig(
        jurisdiction_id=data.get("jurisdiction_id", ""),
        level=data.get("level", ""),
        display_name=data.get("display_name", ""),
        parent_jurisdictions=data.get("parent_jurisdictions") or [],
        contact_info=contact_info,
        governing_body=governing_body,
        state_info=state_info,
        data_sources=data_sources,
        financial=financial,
        federal_programs=federal_programs,
        zip_codes=data.get("zip_codes") or [],
        neighborhoods=data.get("neighborhoods") or [],
        tools_enabled=data.get("tools_enabled"),
        tool_overrides=data.get("tool_overrides") or {},
        modal=modal,
        metadata=metadata,
    )
