"""
Tests for election source detection during onboarding.

Validates detect_election_sources(), _infer_division_name(), and
detect_districts() produce correct election source configs for
various jurisdiction types.
"""

import json
import pytest
import requests
from unittest.mock import patch, MagicMock

from civicos_extraction.onboard import (
    detect_election_sources,
    detect_districts,
    _infer_division_name,
    _validate_civera_division_filter,
)

# Auto-mock the Civera validation for unit tests (avoid network calls)
@pytest.fixture(autouse=True)
def mock_civera_validation(monkeypatch):
    """Skip live Civera validation in unit tests."""
    monkeypatch.setattr(
        "civicos_extraction.onboard._validate_civera_division_filter",
        lambda *args, **kwargs: True,
    )


# --- _infer_division_name tests ---


class TestInferDivisionName:
    """Division name inference for Civera division filter.

    Cities and towns use bare names for broad matching (captures both
    "City of X" and "X City Council District N" divisions).
    """

    def test_city_prefix(self):
        # Bare name matches "City of San Rafael" AND "San Rafael City Council District 1"
        assert _infer_division_name("city-san-rafael") == "San Rafael"

    def test_city_single_word(self):
        assert _infer_division_name("city-novato") == "Novato"

    def test_city_multi_word(self):
        assert _infer_division_name("city-mill-valley") == "Mill Valley"

    def test_town_prefix(self):
        assert _infer_division_name("town-fairfax") == "Fairfax"

    def test_town_multi_word(self):
        assert _infer_division_name("town-san-anselmo") == "San Anselmo"

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
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}
        assert result["marin_registrar_results"]["from_year"] == 2010
        assert result["marin_registrar_results"]["division_filter"] == "San Rafael"
        assert len(result) == 2

    def test_california_marin_county(self):
        """County-level Marin jurisdiction."""
        result = detect_election_sources("county-marin", "CA", "Marin")
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}
        assert result["marin_registrar_results"]["division_filter"] == "Marin County"

    def test_california_non_marin(self):
        """CA outside Marin → CA SOS only, with county_breakdown fallback."""
        result = detect_election_sources("city-los-angeles", "CA", "Los Angeles")
        assert result["ca_sos_results"] == {"county": "los angeles", "county_breakdown": True}
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
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}
        assert result["marin_registrar_results"]["division_filter"] == "Novato Unified School District"

    def test_empty_state(self):
        """Empty state string → no sources."""
        result = detect_election_sources("city-test", "", "SomeCounty")
        assert "ca_sos_results" not in result
        assert len(result) == 0

    def test_empty_county(self):
        """Empty county → no Marin Registrar, SOS with county breakdown fallback."""
        result = detect_election_sources("city-test", "CA", "")
        assert result["ca_sos_results"] == {"county": "", "county_breakdown": True}
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
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}

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
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}

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


# --- Civera division filter validation tests ---


class TestValidateCiveraDivisionFilter:
    """Tests for the post-inference validation step.

    These tests need the real _validate_civera_division_filter, so they
    override the autouse mock by patching CiveraElectionStatsClient directly.
    """

    def _mock_client(self, elections, results_count):
        mock_cls = MagicMock()
        mock_inst = mock_cls.return_value
        mock_inst.list_elections.return_value = elections
        mock_inst.get_election_results.return_value = {
            "total_contests": results_count, "contests": [],
        }
        return mock_cls

    def test_valid_filter_returns_true(self, monkeypatch):
        """Known-good filter 'San Rafael' should validate."""
        monkeypatch.undo()  # Remove autouse mock
        mock_cls = self._mock_client(
            [{"id": 35, "name": "2024 Nov - General", "count": 70}], 6,
        )
        with patch("civicos_extraction.clients.civera_election_stats.CiveraElectionStatsClient", mock_cls):
            assert _validate_civera_division_filter(
                "https://example.com/api/graphql_pr", "marin", "San Rafael",
            ) is True

    def test_bad_filter_returns_false(self, monkeypatch):
        """Non-existent division should fail validation."""
        monkeypatch.undo()
        mock_cls = self._mock_client(
            [{"id": 35, "name": "2024 Nov - General", "count": 70}], 0,
        )
        with patch("civicos_extraction.clients.civera_election_stats.CiveraElectionStatsClient", mock_cls):
            assert _validate_civera_division_filter(
                "https://example.com/api/graphql_pr", "marin", "Nonexistent City",
            ) is False

    def test_network_error_returns_true(self, monkeypatch):
        """Network failures shouldn't block onboarding."""
        monkeypatch.undo()
        mock_cls = MagicMock()
        mock_cls.return_value.list_elections.side_effect = RuntimeError("timeout")
        with patch("civicos_extraction.clients.civera_election_stats.CiveraElectionStatsClient", mock_cls):
            assert _validate_civera_division_filter(
                "https://example.com/api/graphql_pr", "marin", "San Rafael",
            ) is True

    def test_no_general_elections_returns_true(self, monkeypatch):
        """If no general elections found, can't validate — assume OK."""
        monkeypatch.undo()
        mock_cls = self._mock_client(
            [{"id": 99, "name": "2025 Special", "count": 1}], 0,
        )
        with patch("civicos_extraction.clients.civera_election_stats.CiveraElectionStatsClient", mock_cls):
            assert _validate_civera_division_filter(
                "https://example.com/api/graphql_pr", "marin", "San Rafael",
            ) is True

    def test_failed_validation_does_not_block_onboarding(self):
        """Failed validation still includes the source (with warning logged)."""
        with patch("civicos_extraction.onboard._validate_civera_division_filter", return_value=False):
            result = detect_election_sources("city-fake-town", "CA", "Marin")
        assert "marin_registrar_results" in result


# --- School district detection via CDE data ---


class TestDetectSchoolDistricts:
    """Tests for CDE-based school district detection."""

    SAMPLE_CDE_TSV = (
        "CDSCode\tCounty\tDistrict\tSchool\tCity\tStatusType\n"
        "1\tMarin\tMiller Creek Elementary\tSome School\tSan Rafael\tActive\n"
        "2\tMarin\tSan Rafael City High\tTerra Linda HS\tSan Rafael\tActive\n"
        "3\tMarin\tMill Valley Elementary\tMV School\tMill Valley\tActive\n"
        "4\tMarin\tRoss Valley Elementary\tBrookside\tSan Anselmo\tActive\n"
        "5\tMarin\tMiller Creek Elementary\tClosed School\tSan Rafael\tClosed\n"
        "6\tSonoma\tPetaluma City Schools\tSome School\tPetaluma\tActive\n"
    )

    def test_finds_districts_for_city(self):
        from civicos_extraction.onboard import detect_school_districts
        mock_resp = MagicMock()
        mock_resp.text = self.SAMPLE_CDE_TSV
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp):
            result = detect_school_districts("San Rafael", "Marin")
        assert result == ["Miller Creek Elementary", "San Rafael City High"]

    def test_excludes_closed_schools(self):
        from civicos_extraction.onboard import detect_school_districts
        mock_resp = MagicMock()
        mock_resp.text = self.SAMPLE_CDE_TSV
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp):
            result = detect_school_districts("San Rafael", "Marin")
        # "Closed" school should not add a duplicate Miller Creek
        assert result.count("Miller Creek Elementary") == 1

    def test_filters_by_county(self):
        from civicos_extraction.onboard import detect_school_districts
        mock_resp = MagicMock()
        mock_resp.text = self.SAMPLE_CDE_TSV
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp):
            result = detect_school_districts("Petaluma", "Sonoma")
        assert result == ["Petaluma City Schools"]

    def test_case_insensitive(self):
        from civicos_extraction.onboard import detect_school_districts
        mock_resp = MagicMock()
        mock_resp.text = self.SAMPLE_CDE_TSV
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp):
            result = detect_school_districts("san rafael", "marin")
        assert len(result) == 2

    def test_no_match_returns_empty(self):
        from civicos_extraction.onboard import detect_school_districts
        mock_resp = MagicMock()
        mock_resp.text = self.SAMPLE_CDE_TSV
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp):
            result = detect_school_districts("Nonexistent City", "Marin")
        assert result == []

    def test_network_error_returns_empty(self):
        from civicos_extraction.onboard import detect_school_districts
        with patch("civicos_extraction.onboard.requests.get", side_effect=requests.ConnectionError):
            result = detect_school_districts("San Rafael", "Marin")
        assert result == []


# --- Contact info detection tests ---


class TestDetectContactInfo:
    """Tests for LLM-assisted contact info extraction from city websites."""

    MOCK_CONTACT_HTML = (
        "<html><body>"
        "<h1>Contact Us</h1>"
        "<p>City Hall: 100 Main St, Testville CA 90001</p>"
        "<p>Phone: (555) 123-4567</p>"
        '<p>Email: <a href="mailto:clerk@testville.gov">clerk@testville.gov</a></p>'
        "</body></html>"
    )

    def test_extracts_from_contact_page(self):
        from civicos_extraction.onboard import detect_contact_info
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = self.MOCK_CONTACT_HTML

        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.raise_for_status.return_value = None
        mock_llm_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "clerk_email": "clerk@testville.gov",
                "city_hall_address": "100 Main St, Testville CA 90001",
                "phone": "(555) 123-4567",
                "public_comment_deadline": None,
                "in_person_time_limit": None,
            })}}]
        }

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp), \
             patch("httpx.post", return_value=mock_llm_resp), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = detect_contact_info("https://testville.gov", "Testville")

        assert result["clerk_email"] == "clerk@testville.gov"
        assert result["phone"] == "(555) 123-4567"
        assert "100 Main" in result["city_hall_address"]

    def test_no_api_key_returns_empty(self):
        from civicos_extraction.onboard import detect_contact_info
        with patch.dict("os.environ", {}, clear=True):
            result = detect_contact_info("https://testville.gov", "Testville")
        assert all(v is None for v in result.values())

    def test_network_error_returns_empty(self):
        from civicos_extraction.onboard import detect_contact_info
        with patch("civicos_extraction.onboard.requests.get", side_effect=requests.ConnectionError), \
             patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = detect_contact_info("https://testville.gov", "Testville")
        assert all(v is None for v in result.values())


# --- YouTube playlist detection tests ---


class TestDetectYoutubePlaylist:
    """Tests for council meeting playlist detection."""

    MOCK_PLAYLISTS = {
        "items": [
            {"id": "PL_misc", "snippet": {"title": "Community Events 2024"}},
            {"id": "PL_council", "snippet": {"title": "City Council Meetings"}},
            {"id": "PL_plan", "snippet": {"title": "Planning Commission"}},
        ]
    }

    def test_finds_council_meeting_playlist(self):
        from civicos_extraction.onboard import detect_youtube_playlist
        mock_resp = MagicMock()
        mock_resp.json.return_value = self.MOCK_PLAYLISTS
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp), \
             patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"}):
            result = detect_youtube_playlist("UC_test_channel")
        assert result == "PL_council"

    def test_no_meeting_playlist_returns_none(self):
        from civicos_extraction.onboard import detect_youtube_playlist
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {"id": "PL1", "snippet": {"title": "Vacation Photos"}},
                {"id": "PL2", "snippet": {"title": "Music Videos"}},
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp), \
             patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"}):
            result = detect_youtube_playlist("UC_test_channel")
        assert result is None

    def test_no_api_key_returns_none(self):
        from civicos_extraction.onboard import detect_youtube_playlist
        with patch.dict("os.environ", {}, clear=True):
            result = detect_youtube_playlist("UC_test_channel")
        assert result is None

    def test_prefers_council_meeting_over_generic(self):
        from civicos_extraction.onboard import detect_youtube_playlist
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {"id": "PL_generic", "snippet": {"title": "Board Meeting Archives"}},
                {"id": "PL_best", "snippet": {"title": "City Council Meeting Recordings"}},
            ]
        }
        mock_resp.raise_for_status.return_value = None

        with patch("civicos_extraction.onboard.requests.get", return_value=mock_resp), \
             patch.dict("os.environ", {"YOUTUBE_API_KEY": "test-key"}):
            result = detect_youtube_playlist("UC_test_channel")
        assert result == "PL_best"  # Higher score: "city council" + "meeting"


class TestDetectSchoolDistrictsLive:
    """Live integration test against CDE API (requires network)."""

    @pytest.mark.integration
    def test_san_rafael_live(self):
        from civicos_extraction.onboard import detect_school_districts
        result = detect_school_districts("San Rafael", "Marin")
        assert len(result) >= 2
        assert any("Miller Creek" in d for d in result)


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
