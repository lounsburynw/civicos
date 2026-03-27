"""
Tests for election source detection during onboarding.

Validates detect_election_sources() and _infer_division_name() produce
correct election source configs for various jurisdiction types.
"""

import pytest

from civicos_extraction.onboard import (
    detect_election_sources,
    _infer_division_name,
)


# --- _infer_division_name tests ---


class TestInferDivisionName:
    """Division name inference for Marin Registrar filter."""

    def test_city_prefix(self):
        assert _infer_division_name("city-san-rafael") == "City of San Rafael"

    def test_city_single_word(self):
        assert _infer_division_name("city-novato") == "City of Novato"

    def test_city_multi_word(self):
        assert _infer_division_name("city-mill-valley") == "City of Mill Valley"

    def test_town_prefix(self):
        assert _infer_division_name("town-fairfax") == "Town of Fairfax"

    def test_town_multi_word(self):
        assert _infer_division_name("town-san-anselmo") == "Town of San Anselmo"

    def test_county_prefix(self):
        assert _infer_division_name("county-marin") == "Marin County"

    def test_county_multi_word(self):
        assert _infer_division_name("county-san-francisco") == "San Francisco County"

    def test_school_prefix_with_lookup(self):
        """School districts should use the full name from school_districts.json."""
        result = _infer_division_name("school-novato")
        assert result == "Novato Unified School District"

    def test_school_prefix_unknown_fallback(self):
        """Unknown school districts fall back to slug + 'School District'."""
        result = _infer_division_name("school-unknown-district")
        assert result == "Unknown District School District"

    def test_no_prefix(self):
        """IDs without a recognized prefix return title-cased slug."""
        result = _infer_division_name("some-thing")
        assert result == "Thing"

    def test_bare_id(self):
        """Single-segment IDs with no dash."""
        result = _infer_division_name("standalone")
        assert result == "Standalone"


# --- detect_election_sources tests ---


class TestDetectElectionSources:
    """Election source detection based on state and county."""

    def test_california_marin_city(self):
        """CA + Marin → CA SOS + Marin Registrar."""
        result = detect_election_sources("city-san-rafael", "CA", "Marin")
        assert result["ca_sos_results"] == {"county": "marin"}
        assert result["marin_registrar_results"]["from_year"] == 2010
        assert result["marin_registrar_results"]["division_filter"] == "City of San Rafael"
        assert len(result) == 2

    def test_california_marin_county(self):
        """County-level Marin jurisdiction."""
        result = detect_election_sources("county-marin", "CA", "Marin")
        assert result["ca_sos_results"] == {"county": "marin"}
        assert result["marin_registrar_results"]["division_filter"] == "Marin County"

    def test_california_non_marin(self):
        """CA outside Marin → CA SOS only."""
        result = detect_election_sources("city-los-angeles", "CA", "Los Angeles")
        assert result["ca_sos_results"] == {"county": "los angeles"}
        assert "marin_registrar_results" not in result
        assert len(result) == 1

    def test_non_california(self):
        """Non-CA → empty (no state-specific sources yet)."""
        result = detect_election_sources("city-portland", "OR", "Multnomah")
        assert "ca_sos_results" not in result
        assert "marin_registrar_results" not in result
        assert len(result) == 0

    def test_non_california_returns_empty(self):
        """Non-CA jurisdictions have no auto-detected sources."""
        result = detect_election_sources("city-anytown", "TX", "Travis")
        assert len(result) == 0

    def test_state_case_insensitive(self):
        """State comparison should be case-insensitive."""
        result = detect_election_sources("city-sacramento", "ca", "Sacramento")
        assert "ca_sos_results" in result

    def test_county_case_insensitive(self):
        """County comparison for Marin should be case-insensitive."""
        result = detect_election_sources("city-novato", "CA", "MARIN")
        assert "marin_registrar_results" in result

    def test_school_district_marin(self):
        """School district in Marin gets CA SOS + Marin Registrar with correct division."""
        result = detect_election_sources("school-novato", "CA", "Marin")
        assert result["ca_sos_results"] == {"county": "marin"}
        assert result["marin_registrar_results"]["division_filter"] == "Novato Unified School District"

    def test_empty_state(self):
        """Empty state string → no sources."""
        result = detect_election_sources("city-test", "", "SomeCounty")
        assert "ca_sos_results" not in result
        assert len(result) == 0

    def test_empty_county(self):
        """Empty county → no Marin Registrar."""
        result = detect_election_sources("city-test", "CA", "")
        assert result["ca_sos_results"] == {"county": ""}
        assert "marin_registrar_results" not in result

    def test_matches_existing_san_rafael_config(self):
        """Output should be compatible with existing city-san-rafael.json format."""
        result = detect_election_sources("city-san-rafael", "CA", "Marin")
        assert "ca_sos_results" in result
        assert "marin_registrar_results" in result
        assert result["ca_sos_results"]["county"] == "marin"
        assert result["marin_registrar_results"]["from_year"] == 2010

    def test_matches_existing_county_marin_config(self):
        """Output should match county-marin.json structure."""
        result = detect_election_sources("county-marin", "CA", "Marin")
        assert result["marin_registrar_results"]["division_filter"] == "Marin County"
        assert result["marin_registrar_results"]["from_year"] == 2010

    # --- Civera ElectionStats detection (Sonoma, Yolo) ---

    def test_sonoma_gets_civera_source(self):
        """Sonoma County → CA SOS + Civera ElectionStats."""
        result = detect_election_sources("county-sonoma", "CA", "Sonoma")
        assert "ca_sos_results" in result
        assert "civera_election_stats" in result
        assert result["civera_election_stats"]["county_slug"] == "sonoma"
        assert "graphql_url" in result["civera_election_stats"]
        assert "marin_registrar_results" not in result

    def test_yolo_gets_civera_source(self):
        """Yolo County → CA SOS + Civera ElectionStats."""
        result = detect_election_sources("county-yolo", "CA", "Yolo")
        assert "ca_sos_results" in result
        assert "civera_election_stats" in result
        assert result["civera_election_stats"]["county_slug"] == "yolo"

    def test_marin_does_not_get_civera_source(self):
        """Marin uses legacy marin_registrar_results, not civera_election_stats."""
        result = detect_election_sources("county-marin", "CA", "Marin")
        assert "marin_registrar_results" in result
        assert "civera_election_stats" not in result

    def test_civera_detection_case_insensitive(self):
        """County name matching for Civera is case-insensitive."""
        result = detect_election_sources("city-petaluma", "CA", "SONOMA")
        assert "civera_election_stats" in result
        assert result["civera_election_stats"]["county_slug"] == "sonoma"

    def test_non_civera_county_no_civera_source(self):
        """Counties without Civera don't get civera_election_stats."""
        result = detect_election_sources("city-oakland", "CA", "Alameda")
        assert "ca_sos_results" in result
        assert "civera_election_stats" not in result
