"""
Tests for election source detection during onboarding.

Validates detect_election_sources(), _infer_division_name(), and
detect_districts() produce correct election source configs for
various jurisdiction types.
"""

import pytest
from unittest.mock import patch, MagicMock

from civicos_extraction.onboard import (
    detect_election_sources,
    detect_districts,
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

    # --- District detection via lat/lng ---

    def test_california_with_lat_lng_adds_districts(self):
        """CA + lat/lng → districts populated in ca_sos_results."""
        mock_districts = {"us-rep": [2], "state-senate": [2], "state-assembly": [12]}
        with patch("civicos_extraction.onboard.detect_districts", return_value=mock_districts):
            result = detect_election_sources(
                "city-san-rafael", "CA", "Marin", lat=37.9735, lng=-122.5311,
            )
        assert result["ca_sos_results"]["county"] == "marin"
        assert result["ca_sos_results"]["districts"] == mock_districts

    def test_california_without_lat_lng_no_districts(self):
        """CA without lat/lng → no districts field."""
        result = detect_election_sources("city-san-rafael", "CA", "Marin")
        assert result["ca_sos_results"] == {"county": "marin"}

    def test_non_california_with_lat_lng_no_districts(self):
        """Non-CA with lat/lng → no ca_sos_results at all."""
        result = detect_election_sources(
            "city-portland", "OR", "Multnomah", lat=45.5, lng=-122.6,
        )
        assert "ca_sos_results" not in result

    def test_district_detection_failure_still_returns_county(self):
        """If Census API fails, ca_sos_results still has county without districts."""
        with patch("civicos_extraction.onboard.detect_districts", return_value=None):
            result = detect_election_sources(
                "city-san-rafael", "CA", "Marin", lat=37.9735, lng=-122.5311,
            )
        assert result["ca_sos_results"] == {"county": "marin"}

    def test_county_suffix_stripped(self):
        """Google Maps returns 'Marin County' — 'County' suffix must be stripped."""
        result = detect_election_sources("city-mill-valley", "CA", "Marin County")
        assert result["ca_sos_results"]["county"] == "marin"
        assert "marin_registrar_results" in result  # Marin check should still match

    def test_county_suffix_stripped_case_insensitive(self):
        """'MARIN COUNTY' should also work."""
        result = detect_election_sources("city-novato", "CA", "MARIN COUNTY")
        assert result["ca_sos_results"]["county"] == "marin"
        assert "marin_registrar_results" in result


# --- detect_districts tests ---


# Mock Census API response matching San Rafael (37.9735, -122.5311)
CENSUS_RESPONSE_SAN_RAFAEL = {
    "result": {
        "geographies": {
            "119th Congressional Districts": [
                {"GEOID": "0602", "NAME": "Congressional District 2", "CDSESSN": "119", "CD119": "02"}
            ],
            "2024 State Legislative Districts - Upper": [
                {"GEOID": "06002", "NAME": "State Senate District 2", "SLDU": "002"}
            ],
            "2024 State Legislative Districts - Lower": [
                {"GEOID": "06012", "NAME": "Assembly District 12", "SLDL": "012"}
            ],
            "States": [
                {"GEOID": "06", "NAME": "California"}
            ],
        }
    }
}

# Mock response with no district data (e.g. ocean coordinates)
CENSUS_RESPONSE_NO_DISTRICTS = {
    "result": {
        "geographies": {
            "States": [],
        }
    }
}

# Mock response with partial data (only congressional)
CENSUS_RESPONSE_PARTIAL = {
    "result": {
        "geographies": {
            "119th Congressional Districts": [
                {"GEOID": "0614", "NAME": "Congressional District 14"}
            ],
        }
    }
}


class TestDetectDistricts:
    """District detection using Census Bureau Geocoding API."""

    def _mock_response(self, json_data, status_code=200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = json_data
        mock.raise_for_status.return_value = None
        return mock

    def test_san_rafael_districts(self):
        """San Rafael coordinates → CD-2, Senate-2, Assembly-12."""
        with patch("civicos_extraction.onboard.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(CENSUS_RESPONSE_SAN_RAFAEL)
            result = detect_districts(37.9735, -122.5311, "CA")

        assert result == {
            "us-rep": [2],
            "state-senate": [2],
            "state-assembly": [12],
        }
        # Verify correct API call
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["x"] == -122.5311
        assert call_kwargs[1]["params"]["y"] == 37.9735

    def test_no_districts_returns_none(self):
        """Coordinates with no district data → None."""
        with patch("civicos_extraction.onboard.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(CENSUS_RESPONSE_NO_DISTRICTS)
            result = detect_districts(0.0, 0.0)

        assert result is None

    def test_partial_districts(self):
        """Response with only congressional district → partial result."""
        with patch("civicos_extraction.onboard.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(CENSUS_RESPONSE_PARTIAL)
            result = detect_districts(37.5, -122.2)

        assert result == {"us-rep": [14]}
        assert "state-senate" not in result
        assert "state-assembly" not in result

    def test_api_failure_returns_none(self):
        """Network failure → None (graceful degradation)."""
        import requests as req
        with patch("civicos_extraction.onboard.requests.get", side_effect=req.ConnectionError("timeout")):
            result = detect_districts(37.9735, -122.5311)

        assert result is None

    def test_api_http_error_returns_none(self):
        """HTTP 500 → None."""
        import requests as req
        with patch("civicos_extraction.onboard.requests.get") as mock_get:
            mock_resp = self._mock_response({}, status_code=500)
            mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
            mock_get.return_value = mock_resp
            result = detect_districts(37.9735, -122.5311)

        assert result is None

    def test_malformed_geoid_skipped(self):
        """GEOID too short → that district type skipped."""
        bad_response = {
            "result": {
                "geographies": {
                    "119th Congressional Districts": [
                        {"GEOID": "06", "NAME": "Bad"}  # too short
                    ],
                    "2024 State Legislative Districts - Upper": [
                        {"GEOID": "06002", "NAME": "Senate 2", "SLDU": "002"}
                    ],
                }
            }
        }
        with patch("civicos_extraction.onboard.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(bad_response)
            result = detect_districts(37.9735, -122.5311)

        assert "us-rep" not in result
        assert result["state-senate"] == [2]

    def test_district_zero_skipped(self):
        """At-large districts (district 0) are skipped."""
        at_large_response = {
            "result": {
                "geographies": {
                    "119th Congressional Districts": [
                        {"GEOID": "5000", "NAME": "At Large", "CD119": "00"}
                    ],
                    "2024 State Legislative Districts - Lower": [
                        {"GEOID": "50001", "NAME": "District 1", "SLDL": "001"}
                    ],
                }
            }
        }
        with patch("civicos_extraction.onboard.requests.get") as mock_get:
            mock_get.return_value = self._mock_response(at_large_response)
            result = detect_districts(44.0, -72.7)

        # At-large CD skipped, but state lower chamber included
        assert "us-rep" not in result
        assert result["state-assembly"] == [1]


class TestDetectDistrictsLive:
    """Live integration test against Census Bureau API (requires network)."""

    @pytest.mark.integration
    def test_san_rafael_live(self):
        """Hit real Census API for San Rafael — validates API format hasn't changed."""
        result = detect_districts(37.9735, -122.5311, "CA")
        assert result is not None
        assert result["us-rep"] == [2]
        assert result["state-senate"] == [2]
        assert result["state-assembly"] == [12]
