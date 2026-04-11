"""
Tests for geocoding_service.py — Google Maps geocoding client.

Covers the jurisdiction mapping loader (YAML directory scanning), GeocodingService
init, Google Maps address-component parsing, geocode_address/reverse_geocode
request handling, and the singleton factory. The filesystem (YAML loader) and
the HTTP layer (requests.get) are the only mocked boundaries — all parsing,
mapping, and control flow run for real.

To run:
    pytest packages/civicos-services/tests/test_geocoding_service.py -q --override-ini="addopts="
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import yaml

import civicos_services.clients.geocoding_service as geo_mod
from civicos_services.clients.geocoding_service import (
    GeocodingService,
    _load_jurisdiction_mappings,
    get_geocoding_service,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level caches before and after every test."""
    geo_mod._jurisdiction_mappings = None
    geo_mod._geocoding_service = None
    yield
    geo_mod._jurisdiction_mappings = None
    geo_mod._geocoding_service = None


def _write_yaml(dir_path: Path, name: str, content: dict) -> Path:
    """Write a YAML file to dir_path/<name>.yaml and return its path."""
    file = dir_path / f"{name}.yaml"
    file.write_text(yaml.safe_dump(content))
    return file


def _make_service(api_key: str = "test-key") -> GeocodingService:
    """
    Build a GeocodingService without touching the real jurisdictions dir.

    Pre-seeds the module cache with empty maps so __init__ won't scan the
    real data/jurisdictions directory. Tests that care about jurisdiction
    lookups set service.city_to_jurisdiction / county_to_jurisdiction
    explicitly after construction.
    """
    if geo_mod._jurisdiction_mappings is None:
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
    return GeocodingService(api_key=api_key)


def _sample_google_result(
    lat: float = 37.8044,
    lng: float = -122.2712,
    formatted: str = "123 Oak St, Oakland, CA 94612, USA",
    city: str = "Oakland",
    county: str = "Alameda County",
    state_long: str = "California",
    state_short: str = "CA",
    zip_code: str = "94612",
    street: str = "Oak St",
) -> dict:
    """Build a Google Maps Geocoding API result fixture."""
    return {
        "formatted_address": formatted,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "address_components": [
            {"long_name": "123", "short_name": "123", "types": ["street_number"]},
            {"long_name": street, "short_name": street, "types": ["route"]},
            {"long_name": city, "short_name": city, "types": ["locality", "political"]},
            {"long_name": county, "short_name": county,
             "types": ["administrative_area_level_2", "political"]},
            {"long_name": state_long, "short_name": state_short,
             "types": ["administrative_area_level_1", "political"]},
            {"long_name": "United States", "short_name": "US",
             "types": ["country", "political"]},
            {"long_name": zip_code, "short_name": zip_code, "types": ["postal_code"]},
        ],
    }


def _mock_response(status: str = "OK", results=None) -> MagicMock:
    resp = MagicMock()
    payload = {"status": status}
    if results is not None:
        payload["results"] = results
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _load_jurisdiction_mappings
# ---------------------------------------------------------------------------


class TestLoadJurisdictionMappings:
    def test_missing_directory_returns_empty_maps(self, tmp_path: Path):
        missing = tmp_path / "does-not-exist"
        result = _load_jurisdiction_mappings(missing)
        assert result == {"city": {}, "county": {}}

    def test_empty_directory_returns_empty_maps(self, tmp_path: Path):
        result = _load_jurisdiction_mappings(tmp_path)
        assert result == {"city": {}, "county": {}}

    def test_city_yaml_builds_city_map(self, tmp_path: Path):
        _write_yaml(tmp_path, "city-oakland", {
            "level": "city",
            "display_name": "Oakland",
            "jurisdiction_id": "city-oakland",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {"Oakland": "city-oakland"}
        assert result["county"] == {}

    def test_county_yaml_appends_county_suffix(self, tmp_path: Path):
        """Google returns 'Alameda County'; YAML display_name is 'Alameda'."""
        _write_yaml(tmp_path, "county-alameda", {
            "level": "county",
            "display_name": "Alameda",
            "jurisdiction_id": "county-alameda",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["county"] == {"Alameda County": "county-alameda"}
        assert "Alameda" not in result["county"]

    def test_county_display_name_already_has_county_kept_as_is(self, tmp_path: Path):
        """If display_name already contains 'County', don't double-append."""
        _write_yaml(tmp_path, "county-marin", {
            "level": "county",
            "display_name": "Marin County",
            "jurisdiction_id": "county-marin",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["county"] == {"Marin County": "county-marin"}
        assert "Marin County County" not in result["county"]

    def test_schema_yaml_is_skipped(self, tmp_path: Path):
        _write_yaml(tmp_path, "schema", {
            "level": "city",
            "display_name": "Schema City",
            "jurisdiction_id": "schema-city",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {}
        assert result["county"] == {}

    def test_missing_level_field_skipped(self, tmp_path: Path):
        _write_yaml(tmp_path, "no-level", {
            "display_name": "Nowhere",
            "jurisdiction_id": "city-nowhere",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {}

    def test_missing_display_name_field_skipped(self, tmp_path: Path):
        _write_yaml(tmp_path, "no-name", {
            "level": "city",
            "jurisdiction_id": "city-nowhere",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {}

    def test_missing_jurisdiction_id_field_skipped(self, tmp_path: Path):
        _write_yaml(tmp_path, "no-id", {
            "level": "city",
            "display_name": "Nowhere",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {}

    def test_non_dict_yaml_skipped(self, tmp_path: Path):
        (tmp_path / "list.yaml").write_text("- just\n- a\n- list\n")
        result = _load_jurisdiction_mappings(tmp_path)
        assert result == {"city": {}, "county": {}}

    def test_malformed_yaml_handled_and_other_files_still_loaded(self, tmp_path: Path):
        # Undefined anchor forces a yaml.composer.ComposerError
        (tmp_path / "broken.yaml").write_text("foo: *undefined\n")
        _write_yaml(tmp_path, "city-oakland", {
            "level": "city",
            "display_name": "Oakland",
            "jurisdiction_id": "city-oakland",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        # The broken file should be skipped, not abort the whole scan
        assert result["city"] == {"Oakland": "city-oakland"}

    def test_non_city_non_county_level_not_added(self, tmp_path: Path):
        """level='country' is neither city nor county — omit from both maps."""
        _write_yaml(tmp_path, "country-usa", {
            "level": "country",
            "display_name": "United States",
            "jurisdiction_id": "country-united-states",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {}
        assert result["county"] == {}

    def test_mixed_city_and_county_both_loaded(self, tmp_path: Path):
        _write_yaml(tmp_path, "city-oakland", {
            "level": "city",
            "display_name": "Oakland",
            "jurisdiction_id": "city-oakland",
        })
        _write_yaml(tmp_path, "county-alameda", {
            "level": "county",
            "display_name": "Alameda",
            "jurisdiction_id": "county-alameda",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {"Oakland": "city-oakland"}
        assert result["county"] == {"Alameda County": "county-alameda"}

    def test_multiple_cities_all_loaded(self, tmp_path: Path):
        _write_yaml(tmp_path, "city-oakland", {
            "level": "city", "display_name": "Oakland", "jurisdiction_id": "city-oakland",
        })
        _write_yaml(tmp_path, "city-berkeley", {
            "level": "city", "display_name": "Berkeley", "jurisdiction_id": "city-berkeley",
        })
        _write_yaml(tmp_path, "city-emeryville", {
            "level": "city", "display_name": "Emeryville", "jurisdiction_id": "city-emeryville",
        })
        result = _load_jurisdiction_mappings(tmp_path)
        assert result["city"] == {
            "Oakland": "city-oakland",
            "Berkeley": "city-berkeley",
            "Emeryville": "city-emeryville",
        }

    def test_cache_returns_same_dict_on_second_call(self, tmp_path: Path):
        _write_yaml(tmp_path, "city-oakland", {
            "level": "city",
            "display_name": "Oakland",
            "jurisdiction_id": "city-oakland",
        })
        first = _load_jurisdiction_mappings(tmp_path)
        # Add a new file — it must NOT appear in the cached result
        _write_yaml(tmp_path, "city-berkeley", {
            "level": "city",
            "display_name": "Berkeley",
            "jurisdiction_id": "city-berkeley",
        })
        second = _load_jurisdiction_mappings(tmp_path)
        assert first is second
        assert second["city"] == {"Oakland": "city-oakland"}


# ---------------------------------------------------------------------------
# GeocodingService.__init__
# ---------------------------------------------------------------------------


class TestGeocodingServiceInit:
    def test_api_key_from_argument(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        service = GeocodingService(api_key="abc-123")
        assert service.api_key == "abc-123"

    def test_api_key_from_environment(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "env-key")
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        service = GeocodingService()
        assert service.api_key == "env-key"

    def test_argument_overrides_environment(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "env-key")
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        service = GeocodingService(api_key="explicit-key")
        assert service.api_key == "explicit-key"

    def test_empty_string_argument_falls_through_to_env(self, monkeypatch):
        """`api_key or os.getenv(...)` — empty string is falsy, so env is used."""
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "env-key")
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        service = GeocodingService(api_key="")
        assert service.api_key == "env-key"

    def test_missing_api_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
        with pytest.raises(ValueError, match="Google Maps API key required"):
            GeocodingService()

    def test_base_url_is_google_geocoding_endpoint(self):
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        service = GeocodingService(api_key="k")
        assert service.base_url == "https://maps.googleapis.com/maps/api/geocode/json"

    def test_loads_city_and_county_maps_from_cache(self):
        geo_mod._jurisdiction_mappings = {
            "city": {"Oakland": "city-oakland"},
            "county": {"Alameda County": "county-alameda"},
        }
        service = GeocodingService(api_key="k")
        assert service.city_to_jurisdiction == {"Oakland": "city-oakland"}
        assert service.county_to_jurisdiction == {"Alameda County": "county-alameda"}


# ---------------------------------------------------------------------------
# _parse_address_components
# ---------------------------------------------------------------------------


class TestParseAddressComponents:
    def test_empty_list_returns_empty_dict(self):
        service = _make_service()
        assert service._parse_address_components([]) == {}

    def test_locality_stored_as_city(self):
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "Oakland", "short_name": "Oakland", "types": ["locality"]},
        ])
        assert result == {"city": "Oakland"}

    def test_admin_area_level_2_stored_as_county(self):
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "Alameda County", "short_name": "Alameda County",
             "types": ["administrative_area_level_2"]},
        ])
        assert result == {"county": "Alameda County"}

    def test_admin_area_level_1_stored_as_state(self):
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "California", "short_name": "CA",
             "types": ["administrative_area_level_1"]},
        ])
        # State uses long_name, not short_name
        assert result == {"state": "California"}

    def test_postal_code_uses_short_name(self):
        """ZIP is stored from short_name, not long_name."""
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "94612-1234", "short_name": "94612", "types": ["postal_code"]},
        ])
        assert result == {"zip_code": "94612"}

    def test_route_stored_as_street_name_long_name(self):
        """Street name uses long_name for display."""
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "Oak Street", "short_name": "Oak St", "types": ["route"]},
        ])
        assert result == {"street_name": "Oak Street"}

    def test_unrecognised_types_ignored(self):
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "Downtown", "short_name": "Downtown", "types": ["sublocality"]},
            {"long_name": "United States", "short_name": "US", "types": ["country"]},
            {"long_name": "123", "short_name": "123", "types": ["street_number"]},
        ])
        assert result == {}

    def test_full_component_list_parsed(self):
        service = _make_service()
        components = [
            {"long_name": "123", "short_name": "123", "types": ["street_number"]},
            {"long_name": "Oak Street", "short_name": "Oak St", "types": ["route"]},
            {"long_name": "Oakland", "short_name": "Oakland",
             "types": ["locality", "political"]},
            {"long_name": "Alameda County", "short_name": "Alameda County",
             "types": ["administrative_area_level_2", "political"]},
            {"long_name": "California", "short_name": "CA",
             "types": ["administrative_area_level_1", "political"]},
            {"long_name": "United States", "short_name": "US",
             "types": ["country", "political"]},
            {"long_name": "94612", "short_name": "94612", "types": ["postal_code"]},
        ]
        result = service._parse_address_components(components)
        assert result == {
            "street_name": "Oak Street",
            "city": "Oakland",
            "county": "Alameda County",
            "state": "California",
            "zip_code": "94612",
        }

    def test_locality_matches_first_type_only(self):
        """elif chain: locality wins over admin_level_2 if locality appears first."""
        service = _make_service()
        result = service._parse_address_components([
            {"long_name": "San Francisco", "short_name": "SF",
             "types": ["locality", "administrative_area_level_2"]},
        ])
        # 'locality' is checked first, so this is stored as city, not county
        assert result == {"city": "San Francisco"}


# ---------------------------------------------------------------------------
# _determine_jurisdictions
# ---------------------------------------------------------------------------


class TestDetermineJurisdictions:
    def test_known_city_mapped(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {}
        result = service._determine_jurisdictions({"city": "Oakland"})
        assert result == {"city": "city-oakland"}

    def test_unknown_city_omitted(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {}
        result = service._determine_jurisdictions({"city": "Atlantis"})
        assert result == {}

    def test_known_county_mapped(self):
        service = _make_service()
        service.city_to_jurisdiction = {}
        service.county_to_jurisdiction = {"Alameda County": "county-alameda"}
        result = service._determine_jurisdictions({"county": "Alameda County"})
        assert result == {"county": "county-alameda"}

    def test_city_and_county_both_mapped(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {"Alameda County": "county-alameda"}
        result = service._determine_jurisdictions({
            "city": "Oakland",
            "county": "Alameda County",
        })
        assert result == {"city": "city-oakland", "county": "county-alameda"}

    def test_empty_components_returns_empty(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {"Alameda County": "county-alameda"}
        assert service._determine_jurisdictions({}) == {}

    def test_none_city_not_mapped(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {}
        result = service._determine_jurisdictions({"city": None})
        assert result == {}

    def test_state_and_zip_ignored_for_jurisdictions(self):
        """Only 'city' and 'county' component keys drive jurisdiction lookup."""
        service = _make_service()
        service.city_to_jurisdiction = {}
        service.county_to_jurisdiction = {}
        result = service._determine_jurisdictions({
            "state": "California",
            "zip_code": "94612",
            "street_name": "Oak St",
        })
        assert result == {}

    def test_partial_match_city_only(self):
        """If the county isn't in the map but city is, return just the city."""
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {"Marin County": "county-marin"}
        result = service._determine_jurisdictions({
            "city": "Oakland",
            "county": "Alameda County",  # not in map
        })
        assert result == {"city": "city-oakland"}


# ---------------------------------------------------------------------------
# geocode_address
# ---------------------------------------------------------------------------


class TestGeocodeAddress:
    def test_ok_response_returns_parsed_location(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {"Alameda County": "county-alameda"}

        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.geocode_address("123 Oak St, Oakland, CA")

        assert result["lat"] == 37.8044
        assert result["lng"] == -122.2712
        assert result["formatted_address"] == "123 Oak St, Oakland, CA 94612, USA"
        assert result["city"] == "Oakland"
        assert result["county"] == "Alameda County"
        assert result["state"] == "California"
        assert result["zip_code"] == "94612"
        assert result["street_name"] == "Oak St"
        assert result["jurisdictions"] == {
            "city": "city-oakland",
            "county": "county-alameda",
        }

    def test_request_sends_address_and_api_key_params(self):
        service = _make_service(api_key="secret-key")
        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp) as mock_get:
            result = service.geocode_address("123 Oak St")

        # Request construction: URL, params, and timeout
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://maps.googleapis.com/maps/api/geocode/json"
        assert call_args[1]["params"] == {
            "address": "123 Oak St",
            "key": "secret-key",
        }
        assert call_args[1]["timeout"] == 5
        # Return value: response is actually parsed, not just "was called"
        assert result is not None
        assert result["lat"] == 37.8044
        assert result["formatted_address"] == "123 Oak St, Oakland, CA 94612, USA"

    def test_zero_results_status_returns_none(self):
        service = _make_service()
        resp = _mock_response(status="ZERO_RESULTS", results=[])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("nowhere address") is None

    def test_over_query_limit_status_returns_none(self):
        service = _make_service()
        resp = _mock_response(status="OVER_QUERY_LIMIT", results=[])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("any") is None

    def test_request_denied_status_returns_none(self):
        service = _make_service()
        resp = _mock_response(status="REQUEST_DENIED", results=[])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("any") is None

    def test_ok_status_with_no_results_key_returns_none(self):
        """`results` key absent but status=OK — treated as failure."""
        service = _make_service()
        resp = MagicMock()
        resp.json.return_value = {"status": "OK"}
        resp.raise_for_status = MagicMock()
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("any") is None

    def test_ok_status_with_empty_results_returns_none(self):
        service = _make_service()
        resp = _mock_response(status="OK", results=[])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("any") is None

    def test_connection_error_returns_none(self):
        service = _make_service()
        with patch.object(
            geo_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            assert service.geocode_address("any") is None

    def test_timeout_returns_none(self):
        service = _make_service()
        with patch.object(
            geo_mod.requests, "get",
            side_effect=requests.Timeout("slow"),
        ):
            assert service.geocode_address("any") is None

    def test_http_error_via_raise_for_status_returns_none(self):
        service = _make_service()
        resp = MagicMock()
        resp.raise_for_status = MagicMock(
            side_effect=requests.HTTPError("500 Server Error")
        )
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("any") is None

    def test_malformed_result_dict_returns_none(self):
        """KeyError inside parsing is caught by the generic Exception handler."""
        service = _make_service()
        resp = MagicMock()
        resp.json.return_value = {
            "status": "OK",
            "results": [{"nothing": "useful"}],  # Missing geometry/address_components
        }
        resp.raise_for_status = MagicMock()
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.geocode_address("any") is None

    def test_uses_first_result_when_multiple_returned(self):
        """Google may return multiple matches; only the first is parsed."""
        service = _make_service()
        service.city_to_jurisdiction = {}
        service.county_to_jurisdiction = {}
        first = _sample_google_result(lat=1.0, lng=2.0, city="Oakland")
        second = _sample_google_result(lat=9.9, lng=9.9, city="Berkeley")
        resp = _mock_response(status="OK", results=[first, second])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.geocode_address("ambiguous")

        assert result["lat"] == 1.0
        assert result["lng"] == 2.0
        assert result["city"] == "Oakland"

    def test_unmapped_city_returns_empty_jurisdictions(self):
        """If the city isn't in the map, jurisdictions dict has only county."""
        service = _make_service()
        service.city_to_jurisdiction = {}  # No cities mapped
        service.county_to_jurisdiction = {"Alameda County": "county-alameda"}

        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.geocode_address("addr")

        assert result["jurisdictions"] == {"county": "county-alameda"}
        # Raw city/county from parsed components still present
        assert result["city"] == "Oakland"
        assert result["county"] == "Alameda County"

    def test_fully_unmapped_yields_empty_jurisdictions(self):
        service = _make_service()
        service.city_to_jurisdiction = {}
        service.county_to_jurisdiction = {}

        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.geocode_address("addr")

        assert result["jurisdictions"] == {}
        assert result["city"] == "Oakland"


# ---------------------------------------------------------------------------
# reverse_geocode
# ---------------------------------------------------------------------------


class TestReverseGeocode:
    def test_ok_response_returns_parsed_location(self):
        service = _make_service()
        service.city_to_jurisdiction = {"Oakland": "city-oakland"}
        service.county_to_jurisdiction = {"Alameda County": "county-alameda"}

        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.reverse_geocode(37.8044, -122.2712)

        assert result["lat"] == 37.8044
        assert result["lng"] == -122.2712
        assert result["formatted_address"] == "123 Oak St, Oakland, CA 94612, USA"
        assert result["city"] == "Oakland"
        assert result["county"] == "Alameda County"
        assert result["state"] == "California"
        assert result["zip_code"] == "94612"
        assert result["street_name"] == "Oak St"
        assert result["jurisdictions"] == {
            "city": "city-oakland",
            "county": "county-alameda",
        }

    def test_returned_latlng_are_the_input_not_response(self):
        """reverse_geocode preserves the caller's coordinates verbatim."""
        service = _make_service()
        # Response has DIFFERENT coordinates to prove the input is preferred
        sample = _sample_google_result(lat=99.9, lng=-99.9)
        resp = _mock_response(status="OK", results=[sample])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.reverse_geocode(37.8044, -122.2712)

        assert result["lat"] == 37.8044
        assert result["lng"] == -122.2712

    def test_sends_latlng_param_with_comma(self):
        service = _make_service(api_key="rev-key")
        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp) as mock_get:
            result = service.reverse_geocode(37.5, -122.3)

        call_args = mock_get.call_args
        assert call_args[0][0] == "https://maps.googleapis.com/maps/api/geocode/json"
        assert call_args[1]["params"] == {
            "latlng": "37.5,-122.3",
            "key": "rev-key",
        }
        assert call_args[1]["timeout"] == 5
        # Return value: input coordinates are preserved verbatim
        assert result is not None
        assert result["lat"] == 37.5
        assert result["lng"] == -122.3

    def test_negative_coordinates_formatted_correctly(self):
        service = _make_service()
        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp) as mock_get:
            result = service.reverse_geocode(-33.8688, 151.2093)

        assert mock_get.call_args[1]["params"]["latlng"] == "-33.8688,151.2093"
        # Return value: negative lat is preserved in the output
        assert result is not None
        assert result["lat"] == -33.8688
        assert result["lng"] == 151.2093

    def test_zero_results_status_returns_none(self):
        service = _make_service()
        resp = _mock_response(status="ZERO_RESULTS", results=[])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.reverse_geocode(0.0, 0.0) is None

    def test_missing_results_key_returns_none(self):
        service = _make_service()
        resp = MagicMock()
        resp.json.return_value = {"status": "OK"}
        resp.raise_for_status = MagicMock()
        with patch.object(geo_mod.requests, "get", return_value=resp):
            assert service.reverse_geocode(1.0, 2.0) is None

    def test_request_exception_returns_none(self):
        service = _make_service()
        with patch.object(
            geo_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            assert service.reverse_geocode(37.0, -122.0) is None

    def test_unmapped_coordinates_yield_empty_jurisdictions(self):
        service = _make_service()
        service.city_to_jurisdiction = {}
        service.county_to_jurisdiction = {}
        resp = _mock_response(status="OK", results=[_sample_google_result()])
        with patch.object(geo_mod.requests, "get", return_value=resp):
            result = service.reverse_geocode(37.0, -122.0)

        assert result["jurisdictions"] == {}
        assert result["city"] == "Oakland"


# ---------------------------------------------------------------------------
# get_geocoding_service (singleton factory)
# ---------------------------------------------------------------------------


class TestGetGeocodingService:
    def test_returns_geocoding_service_instance(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "sing-key")
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        service = get_geocoding_service()
        assert type(service) is GeocodingService
        assert service.api_key == "sing-key"
        assert service.base_url == "https://maps.googleapis.com/maps/api/geocode/json"

    def test_second_call_returns_cached_instance(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "sing-key")
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        first = get_geocoding_service()
        second = get_geocoding_service()
        assert first is second

    def test_cached_instance_survives_env_change(self, monkeypatch):
        """Once created, the singleton is not re-created on subsequent calls
        even if the environment changes — the cached instance keeps its key."""
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "first-key")
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        first = get_geocoding_service()
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "second-key")
        second = get_geocoding_service()
        assert first is second
        assert second.api_key == "first-key"

    def test_raises_when_no_key_and_no_cached_instance(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
        geo_mod._jurisdiction_mappings = {"city": {}, "county": {}}
        with pytest.raises(ValueError, match="Google Maps API key required"):
            get_geocoding_service()
