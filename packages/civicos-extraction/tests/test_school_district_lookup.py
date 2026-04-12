"""
Tests for school district lookup table loading and search.

Validates that load_school_districts(), lookup_school_district(),
and lookup_school_districts_by_county() work correctly with
the static lookup table in data/school_districts.json.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from civicos_extraction.onboard import (
    load_school_districts,
    lookup_school_district,
    lookup_school_districts_by_county,
)


# --- Fixtures ---

@pytest.fixture
def sample_districts():
    """Minimal school district lookup table for testing."""
    return {
        "california": {
            "marin": [
                {
                    "name": "Novato Unified School District",
                    "jurisdiction_id": "school-novato",
                    "platform": "simbli",
                    "board_url": "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030351",
                    "simbli_district_id": "36030351",
                },
                {
                    "name": "Ross Valley School District",
                    "jurisdiction_id": "school-ross-valley",
                    "platform": "boarddocs",
                    "board_url": "https://go.boarddocs.com/ca/rova/Board.nsf",
                },
                {
                    "name": "Mill Valley School District",
                    "jurisdiction_id": "school-mill-valley-sd",
                    "platform": "simbli",
                    "board_url": "https://agendaonline.net/public/millvalley",
                },
            ],
            "sonoma": [
                {
                    "name": "Petaluma City Schools",
                    "jurisdiction_id": "school-petaluma",
                    "platform": "boarddocs",
                    "board_url": "https://go.boarddocs.com/ca/petaluma/Board.nsf",
                },
            ],
        }
    }


# --- load_school_districts ---

class TestLoadSchoolDistricts:

    def test_loads_real_file(self):
        """The actual data/school_districts.json should load successfully."""
        data = load_school_districts()
        assert "california" in data
        assert "marin" in data["california"]
        assert len(data["california"]["marin"]) >= 10  # 10 curated + auto-detected

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Returns empty dict when file doesn't exist."""
        data = load_school_districts(tmp_path / "nonexistent.json")
        assert data == {}

    def test_all_districts_have_required_fields(self):
        """Every district entry must have name, jurisdiction_id, platform, board_url."""
        data = load_school_districts()
        required = {"name", "jurisdiction_id", "platform", "board_url"}
        for state, counties in data.items():
            for county, districts in counties.items():
                for d in districts:
                    missing = required - set(d.keys())
                    assert not missing, f"{d.get('name', '?')} missing: {missing}"


# --- lookup_school_district ---

class TestLookupSchoolDistrict:

    def test_exact_name_match(self, sample_districts):
        result = lookup_school_district(
            "Novato Unified School District", "CA", districts=sample_districts
        )
        assert result is not None
        assert result["jurisdiction_id"] == "school-novato"

    def test_partial_name_match(self, sample_districts):
        result = lookup_school_district("Novato", "CA", districts=sample_districts)
        assert result is not None
        assert result["jurisdiction_id"] == "school-novato"

    def test_case_insensitive(self, sample_districts):
        result = lookup_school_district("ross valley", "CA", districts=sample_districts)
        assert result is not None
        assert result["jurisdiction_id"] == "school-ross-valley"

    def test_jurisdiction_id_slug_match(self, sample_districts):
        result = lookup_school_district("mill-valley-sd", "CA", districts=sample_districts)
        assert result is not None
        assert result["jurisdiction_id"] == "school-mill-valley-sd"

    def test_narrows_by_county(self, sample_districts):
        result = lookup_school_district("Novato", "CA", county="Marin", districts=sample_districts)
        assert result is not None
        assert result["jurisdiction_id"] == "school-novato"

    def test_wrong_county_returns_none(self, sample_districts):
        result = lookup_school_district("Novato", "CA", county="Sonoma", districts=sample_districts)
        assert result is None

    def test_unknown_name_returns_none(self, sample_districts):
        result = lookup_school_district("Nonexistent District", "CA", districts=sample_districts)
        assert result is None

    def test_unknown_state_returns_none(self, sample_districts):
        result = lookup_school_district("Novato", "TX", districts=sample_districts)
        assert result is None

    def test_state_abbreviation_converted(self, sample_districts):
        """CA should be converted to 'california' for lookup."""
        result = lookup_school_district("Novato", "CA", districts=sample_districts)
        assert result is not None
        assert result["jurisdiction_id"] == "school-novato"

    def test_searches_all_counties_without_county_arg(self, sample_districts):
        """Without county filter, should search all counties in state."""
        result = lookup_school_district("Petaluma", "CA", districts=sample_districts)
        assert result is not None
        assert result["jurisdiction_id"] == "school-petaluma"


# --- lookup_school_districts_by_county ---

class TestLookupSchoolDistrictsByCounty:

    def test_returns_all_in_county(self, sample_districts):
        results = lookup_school_districts_by_county("CA", "Marin", districts=sample_districts)
        assert len(results) == 3

    def test_returns_empty_for_unknown_county(self, sample_districts):
        results = lookup_school_districts_by_county("CA", "Alameda", districts=sample_districts)
        assert results == []

    def test_returns_empty_for_unknown_state(self, sample_districts):
        results = lookup_school_districts_by_county("TX", "Marin", districts=sample_districts)
        assert results == []

    def test_county_case_insensitive(self, sample_districts):
        results = lookup_school_districts_by_county("CA", "marin", districts=sample_districts)
        assert len(results) == 3

    def test_real_marin_county(self):
        """Real lookup table should have at least the 10 curated Marin districts."""
        results = lookup_school_districts_by_county("CA", "Marin")
        assert len(results) >= 10  # 10 curated + auto-detected
        platforms = {d["platform"] for d in results}
        assert platforms == {"simbli", "boarddocs"}

    def test_each_district_has_board_url(self):
        """Every real Marin district must have a board_url."""
        results = lookup_school_districts_by_county("CA", "Marin")
        for d in results:
            assert d["board_url"].startswith("http"), f"{d['name']} has invalid board_url"


# --- Integration: real data/school_districts.json ---

class TestRealSchoolDistrictsJson:

    def test_simbli_districts_have_urls(self):
        data = load_school_districts()
        for d in data["california"]["marin"]:
            if d["platform"] == "simbli":
                assert d["board_url"].startswith("http"), f"{d['name']} has invalid board_url: {d['board_url']}"

    def test_boarddocs_districts_have_app_path(self):
        data = load_school_districts()
        for d in data["california"]["marin"]:
            if d["platform"] == "boarddocs":
                assert "boarddocs_app_path" in d, f"{d['name']} missing boarddocs_app_path"
                assert "/" in d["boarddocs_app_path"], f"{d['name']} boarddocs_app_path should be a path like 'ca/rova': {d['boarddocs_app_path']}"

    def test_onboarded_districts_in_lookup_table(self):
        """School districts with extraction configs should appear in lookup table."""
        data = load_school_districts()
        extraction_dir = Path(__file__).parents[3] / "data" / "extraction"
        marin_ids = {d["jurisdiction_id"] for d in data["california"]["marin"]}
        # Find school-* extraction configs that exist
        school_configs = list(extraction_dir.glob("school-*.json"))
        assert len(school_configs) >= 5, "Expected at least 5 school extraction configs"
        for config_path in school_configs:
            jid = config_path.stem
            assert jid in marin_ids, f"Config {jid} not in lookup table"

    def test_no_duplicate_jurisdiction_ids(self):
        data = load_school_districts()
        all_ids = []
        for state_data in data.values():
            for entries in state_data.values():
                for entry in entries:
                    all_ids.append(entry["jurisdiction_id"])
        dupes = [jid for jid in all_ids if all_ids.count(jid) > 1]
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs: {set(dupes)}"
