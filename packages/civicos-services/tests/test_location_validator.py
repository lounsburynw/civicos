"""
Tests for location_validator.py — IP geolocation anti-bot validation.

Covers LocationValidator init + provider selection, the local/private IP
detection helper, the Haversine distance helper, both _geolocate_ip provider
paths (ipinfo.io and ip-api.com), the validate_location orchestrator (local
shortcut, within/outside distance, fail-open on geolocation failure, fail-open
on unexpected exceptions), and the get_location_validator singleton factory.

The only mocked boundaries are `requests.get` (HTTP) and the `IPINFO_TOKEN`
environment variable. All parsing, distance math, and control flow run for
real against the module under test.

To run:
    pytest packages/civicos-services/tests/test_location_validator.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

import civicos_services.core.location_validator as lv_mod
from civicos_services.core.location_validator import (
    LocationValidator,
    get_location_validator,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Ensure no stray IPINFO_TOKEN leaks into tests, and reset the singleton."""
    monkeypatch.delenv("IPINFO_TOKEN", raising=False)
    lv_mod._location_validator = None
    yield
    lv_mod._location_validator = None


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _ipinfo_payload(
    loc: str = "37.8044,-122.2712",
    city: str = "Oakland",
    region: str = "California",
    country: str = "US",
) -> dict:
    return {"loc": loc, "city": city, "region": region, "country": country}


def _ipapi_payload(
    status: str = "success",
    lat: float = 37.8044,
    lon: float = -122.2712,
    city: str = "Oakland",
    region_name: str = "California",
    country_code: str = "US",
) -> dict:
    return {
        "status": status,
        "lat": lat,
        "lon": lon,
        "city": city,
        "regionName": region_name,
        "countryCode": country_code,
    }


# ---------------------------------------------------------------------------
# LocationValidator.__init__
# ---------------------------------------------------------------------------


class TestLocationValidatorInit:
    def test_explicit_token_selects_ipinfo_provider(self):
        v = LocationValidator(ipinfo_token="explicit-abc")
        assert v.ipinfo_token == "explicit-abc"
        assert v.use_ipinfo is True
        assert v.base_url == "https://ipinfo.io"

    def test_env_token_used_when_argument_none(self, monkeypatch):
        monkeypatch.setenv("IPINFO_TOKEN", "env-token")
        v = LocationValidator()
        assert v.ipinfo_token == "env-token"
        assert v.use_ipinfo is True
        assert v.base_url == "https://ipinfo.io"

    def test_argument_overrides_env(self, monkeypatch):
        monkeypatch.setenv("IPINFO_TOKEN", "env-token")
        v = LocationValidator(ipinfo_token="arg-token")
        assert v.ipinfo_token == "arg-token"

    def test_no_token_falls_back_to_ipapi(self):
        v = LocationValidator()
        assert v.ipinfo_token is None
        assert v.use_ipinfo is False
        assert v.base_url == "http://ip-api.com/json"

    def test_empty_string_token_argument_falls_through_to_env(self, monkeypatch):
        """`ipinfo_token or os.getenv(...)` — empty is falsy."""
        monkeypatch.setenv("IPINFO_TOKEN", "env-token")
        v = LocationValidator(ipinfo_token="")
        assert v.ipinfo_token == "env-token"
        assert v.use_ipinfo is True

    def test_empty_string_token_and_no_env_falls_back_to_ipapi(self):
        v = LocationValidator(ipinfo_token="")
        assert v.ipinfo_token is None
        assert v.use_ipinfo is False
        assert v.base_url == "http://ip-api.com/json"


# ---------------------------------------------------------------------------
# _is_local_ip
# ---------------------------------------------------------------------------


class TestIsLocalIp:
    def test_empty_string_is_local(self):
        assert LocationValidator()._is_local_ip("") is True

    def test_none_treated_as_local(self):
        # `if not ip` — None short-circuits to True
        assert LocationValidator()._is_local_ip(None) is True

    def test_localhost_string_is_local(self):
        assert LocationValidator()._is_local_ip("localhost") is True

    def test_loopback_v4_is_local(self):
        assert LocationValidator()._is_local_ip("127.0.0.1") is True

    def test_loopback_v6_is_local(self):
        assert LocationValidator()._is_local_ip("::1") is True

    def test_10_dot_range_is_local(self):
        assert LocationValidator()._is_local_ip("10.0.0.1") is True
        assert LocationValidator()._is_local_ip("10.255.255.255") is True

    def test_just_outside_10_range_not_local(self):
        assert LocationValidator()._is_local_ip("11.0.0.1") is False
        assert LocationValidator()._is_local_ip("9.255.255.255") is False

    def test_172_16_through_31_is_local(self):
        assert LocationValidator()._is_local_ip("172.16.0.1") is True
        assert LocationValidator()._is_local_ip("172.20.5.5") is True
        assert LocationValidator()._is_local_ip("172.31.255.255") is True

    def test_172_just_below_range_not_local(self):
        assert LocationValidator()._is_local_ip("172.15.0.1") is False

    def test_172_just_above_range_not_local(self):
        assert LocationValidator()._is_local_ip("172.32.0.1") is False

    def test_192_168_range_is_local(self):
        assert LocationValidator()._is_local_ip("192.168.0.1") is True
        assert LocationValidator()._is_local_ip("192.168.255.255") is True

    def test_192_167_not_local(self):
        assert LocationValidator()._is_local_ip("192.167.0.1") is False

    def test_192_169_not_local(self):
        assert LocationValidator()._is_local_ip("192.169.0.1") is False

    def test_public_google_dns_not_local(self):
        assert LocationValidator()._is_local_ip("8.8.8.8") is False

    def test_public_cloudflare_dns_not_local(self):
        assert LocationValidator()._is_local_ip("1.1.1.1") is False

    def test_ipv6_address_not_matching_list_returns_false(self):
        """Non-loopback IPv6 has len(split('.')) != 4 and bypasses range checks."""
        assert LocationValidator()._is_local_ip("2001:db8::1") is False


# ---------------------------------------------------------------------------
# _calculate_distance (Haversine)
# ---------------------------------------------------------------------------


class TestCalculateDistance:
    def test_same_point_distance_zero(self):
        v = LocationValidator()
        assert v._calculate_distance(37.8044, -122.2712, 37.8044, -122.2712) == 0.0

    def test_one_degree_latitude_about_69_miles(self):
        """1° latitude ≈ 69.0976 miles (R=3959)."""
        v = LocationValidator()
        d = v._calculate_distance(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(69.0976, abs=0.001)

    def test_one_degree_longitude_at_equator_about_69_miles(self):
        """At the equator, 1° longitude ≈ 69.0976 miles."""
        v = LocationValidator()
        d = v._calculate_distance(0.0, 0.0, 0.0, 1.0)
        assert d == pytest.approx(69.0976, abs=0.001)

    def test_oakland_to_san_rafael(self):
        """Oakland (37.8044, -122.2712) → San Rafael (37.9735, -122.5311)."""
        v = LocationValidator()
        d = v._calculate_distance(37.8044, -122.2712, 37.9735, -122.5311)
        assert d == pytest.approx(18.368, abs=0.01)

    def test_oakland_to_new_york(self):
        """Continental distance Oakland → NYC ≈ 2557.55 miles."""
        v = LocationValidator()
        d = v._calculate_distance(37.8044, -122.2712, 40.7128, -74.0060)
        assert d == pytest.approx(2557.55, abs=0.5)

    def test_distance_is_symmetric(self):
        v = LocationValidator()
        ab = v._calculate_distance(37.8044, -122.2712, 40.7128, -74.0060)
        ba = v._calculate_distance(40.7128, -74.0060, 37.8044, -122.2712)
        assert ab == pytest.approx(ba, abs=1e-9)

    def test_antipodal_half_circumference(self):
        """(0,0) to (0,180) ≈ π·R ≈ 12437.565 miles."""
        v = LocationValidator()
        d = v._calculate_distance(0.0, 0.0, 0.0, 180.0)
        assert d == pytest.approx(12437.565, abs=0.01)

    def test_equator_to_north_pole_quarter_circumference(self):
        """(0,0) to (90,0) ≈ π·R/2 ≈ 6218.78 miles."""
        v = LocationValidator()
        d = v._calculate_distance(0.0, 0.0, 90.0, 0.0)
        assert d == pytest.approx(6218.78, abs=0.01)

    def test_short_distance_oakland_to_berkeley(self):
        """Short distance (~4.6 miles) still computes accurately."""
        v = LocationValidator()
        d = v._calculate_distance(37.8044, -122.2712, 37.8716, -122.2727)
        assert d == pytest.approx(4.644, abs=0.01)


# ---------------------------------------------------------------------------
# _geolocate_ip — ipinfo.io path
# ---------------------------------------------------------------------------


class TestGeolocateIpInfo:
    def test_ipinfo_success_returns_parsed_location(self):
        v = LocationValidator(ipinfo_token="tk")
        resp = _mock_response(_ipinfo_payload(
            loc="37.8044,-122.2712",
            city="Oakland",
            region="California",
            country="US",
        ))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v._geolocate_ip("8.8.8.8")

        assert result == {
            "city": "Oakland",
            "region": "California",
            "country": "US",
            "lat": 37.8044,
            "lng": -122.2712,
        }

    def test_ipinfo_request_sends_ip_in_url_and_token_in_params(self):
        v = LocationValidator(ipinfo_token="secret-tk")
        resp = _mock_response(_ipinfo_payload())
        with patch.object(lv_mod.requests, "get", return_value=resp) as mock_get:
            result = v._geolocate_ip("8.8.8.8")

        call_args = mock_get.call_args
        assert call_args[0][0] == "https://ipinfo.io/8.8.8.8/json"
        assert call_args[1]["params"] == {"token": "secret-tk"}
        assert call_args[1]["timeout"] == 5
        # Also assert result was actually parsed, not just the request made
        assert result["lat"] == 37.8044
        assert result["city"] == "Oakland"

    def test_ipinfo_empty_loc_returns_none(self):
        v = LocationValidator(ipinfo_token="tk")
        resp = _mock_response(_ipinfo_payload(loc=""))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_loc_with_only_one_value_returns_none(self):
        v = LocationValidator(ipinfo_token="tk")
        resp = _mock_response(_ipinfo_payload(loc="37.8"))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_missing_loc_field_returns_none(self):
        """No `loc` key at all — .get('', '') defaults to empty string."""
        v = LocationValidator(ipinfo_token="tk")
        resp = _mock_response({"city": "Oakland"})
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_connection_error_returns_none(self):
        v = LocationValidator(ipinfo_token="tk")
        with patch.object(
            lv_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_timeout_returns_none(self):
        v = LocationValidator(ipinfo_token="tk")
        with patch.object(
            lv_mod.requests, "get",
            side_effect=requests.Timeout("slow"),
        ):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_http_error_returns_none(self):
        v = LocationValidator(ipinfo_token="tk")
        resp = MagicMock()
        resp.raise_for_status = MagicMock(
            side_effect=requests.HTTPError("401 Unauthorized"),
        )
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_invalid_lat_lng_returns_none(self):
        """Non-numeric loc values → ValueError caught by generic Exception."""
        v = LocationValidator(ipinfo_token="tk")
        resp = _mock_response(_ipinfo_payload(loc="not,numbers"))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipinfo_missing_metadata_fields_filled_with_none(self):
        """`city`/`region`/`country` absent → .get() returns None values."""
        v = LocationValidator(ipinfo_token="tk")
        resp = _mock_response({"loc": "37.8044,-122.2712"})
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v._geolocate_ip("8.8.8.8")
        assert result == {
            "city": None,
            "region": None,
            "country": None,
            "lat": 37.8044,
            "lng": -122.2712,
        }


# ---------------------------------------------------------------------------
# _geolocate_ip — ip-api.com fallback path
# ---------------------------------------------------------------------------


class TestGeolocateIpApi:
    def test_ipapi_success_returns_parsed_location(self):
        v = LocationValidator()  # no token → ip-api
        resp = _mock_response(_ipapi_payload())
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v._geolocate_ip("8.8.8.8")

        assert result == {
            "city": "Oakland",
            "region": "California",
            "country": "US",
            "lat": 37.8044,
            "lng": -122.2712,
        }

    def test_ipapi_request_uses_url_without_token(self):
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload())
        with patch.object(lv_mod.requests, "get", return_value=resp) as mock_get:
            result = v._geolocate_ip("8.8.8.8")

        call_args = mock_get.call_args
        assert call_args[0][0] == "http://ip-api.com/json/8.8.8.8"
        # No params passed for ip-api (only timeout kwarg)
        assert "params" not in call_args[1]
        assert call_args[1]["timeout"] == 5
        # Response actually parsed
        assert result["lat"] == 37.8044
        assert result["region"] == "California"

    def test_ipapi_fail_status_returns_none(self):
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload(status="fail"))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipapi_missing_status_returns_none(self):
        v = LocationValidator()
        resp = _mock_response({"lat": 37.8, "lon": -122.2})
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipapi_connection_error_returns_none(self):
        v = LocationValidator()
        with patch.object(
            lv_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipapi_http_error_returns_none(self):
        v = LocationValidator()
        resp = MagicMock()
        resp.raise_for_status = MagicMock(
            side_effect=requests.HTTPError("429 Too Many Requests"),
        )
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipapi_json_parse_error_returns_none(self):
        """Non-RequestException (e.g., json decode) caught by generic handler."""
        v = LocationValidator()
        resp = MagicMock()
        resp.json.side_effect = ValueError("not json")
        resp.raise_for_status = MagicMock()
        with patch.object(lv_mod.requests, "get", return_value=resp):
            assert v._geolocate_ip("8.8.8.8") is None

    def test_ipapi_preserves_regionname_and_countrycode(self):
        """Key names differ from ipinfo: regionName → region, countryCode → country."""
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload(
            region_name="Texas",
            country_code="US",
            lat=30.2672,
            lon=-97.7431,
            city="Austin",
        ))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v._geolocate_ip("1.2.3.4")
        assert result["region"] == "Texas"
        assert result["country"] == "US"
        assert result["city"] == "Austin"
        assert result["lat"] == 30.2672
        assert result["lng"] == -97.7431


# ---------------------------------------------------------------------------
# validate_location
# ---------------------------------------------------------------------------


class TestValidateLocation:
    def test_local_ip_shortcut_returns_valid_without_http(self):
        v = LocationValidator()
        with patch.object(lv_mod.requests, "get") as mock_get:
            result = v.validate_location("127.0.0.1", 37.8044, -122.2712)

        assert mock_get.call_count == 0
        assert result["valid"] is True
        assert result["distance_miles"] == 0.0
        assert result["ip_location"]["city"] == "localhost"
        assert result["ip_location"]["region"] == "dev"
        # Local shortcut echoes the claimed coords as the "ip_location"
        assert result["ip_location"]["lat"] == 37.8044
        assert result["ip_location"]["lng"] == -122.2712
        assert result["reason"] == "localhost/private IP - validation skipped"

    def test_private_192_168_ip_skipped(self):
        v = LocationValidator()
        with patch.object(lv_mod.requests, "get") as mock_get:
            result = v.validate_location("192.168.1.42", 0.0, 0.0)
        assert mock_get.call_count == 0
        assert result["valid"] is True
        assert result["distance_miles"] == 0.0

    def test_within_distance_returns_valid_and_rounded_distance(self):
        v = LocationValidator()  # uses ip-api path
        # IP geolocated to Oakland; claimed address also Oakland → ~0 miles
        resp = _mock_response(_ipapi_payload(lat=37.8044, lon=-122.2712))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 37.8044, -122.2712)

        assert result["valid"] is True
        assert result["distance_miles"] == 0.0
        assert result["ip_location"]["city"] == "Oakland"
        assert result["ip_location"]["lat"] == 37.8044
        assert result["reason"] == "Valid - within acceptable distance"

    def test_within_distance_short_realistic_hop(self):
        """Oakland IP → San Rafael claimed (18.37 mi), default 50mi limit."""
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload(lat=37.8044, lon=-122.2712))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 37.9735, -122.5311)

        assert result["valid"] is True
        assert result["distance_miles"] == 18.37  # rounded to 2 decimals
        assert result["reason"] == "Valid - within acceptable distance"

    def test_outside_distance_returns_invalid_with_reason(self):
        v = LocationValidator()
        # IP in Oakland, claim in NYC → ~2557 miles
        resp = _mock_response(_ipapi_payload(lat=37.8044, lon=-122.2712))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 40.7128, -74.0060)

        assert result["valid"] is False
        assert result["distance_miles"] == pytest.approx(2557.55, abs=0.5)
        assert result["ip_location"]["city"] == "Oakland"
        assert "exceeds 50.0 mile limit" in result["reason"]
        assert "2557" in result["reason"]

    def test_boundary_at_exactly_max_distance_is_valid(self):
        """`distance <= max_distance_miles` — boundary must be inclusive."""
        v = LocationValidator()
        # 1° latitude ≈ 69.0976 miles; choose max_distance at that value
        resp = _mock_response(_ipapi_payload(lat=0.0, lon=0.0))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 1.0, 0.0, max_distance_miles=70.0)

        assert result["valid"] is True
        assert result["distance_miles"] == 69.1  # rounded to 2 decimals

    def test_boundary_just_over_max_distance_is_invalid(self):
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload(lat=0.0, lon=0.0))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 1.0, 0.0, max_distance_miles=69.0)

        assert result["valid"] is False
        assert "69.1 miles exceeds 69.0 mile limit" in result["reason"]

    def test_custom_max_distance_used_in_comparison(self):
        """A 100mi trip is invalid at 50mi limit but valid at 200mi limit."""
        v = LocationValidator()
        # From (0,0) to (0, 1.4475) ≈ 100 miles
        resp = _mock_response(_ipapi_payload(lat=0.0, lon=0.0))

        with patch.object(lv_mod.requests, "get", return_value=resp):
            tight = v.validate_location("8.8.8.8", 0.0, 1.4475, max_distance_miles=50.0)
        with patch.object(lv_mod.requests, "get", return_value=resp):
            loose = v.validate_location("8.8.8.8", 0.0, 1.4475, max_distance_miles=200.0)

        assert tight["valid"] is False
        assert loose["valid"] is True
        # Both compute the same raw distance
        assert tight["distance_miles"] == loose["distance_miles"]
        assert tight["distance_miles"] == pytest.approx(100.0, abs=0.1)

    def test_geolocation_failure_fails_open(self):
        """Geolocation returns None → allowed to pass, marked so in reason."""
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload(status="fail"))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 37.8044, -122.2712)

        assert result["valid"] is True
        assert result["distance_miles"] is None
        assert result["ip_location"] is None
        assert result["reason"] == "IP geolocation unavailable - allowed"

    def test_http_exception_inside_geolocate_fails_open(self):
        v = LocationValidator()
        with patch.object(
            lv_mod.requests, "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            result = v.validate_location("8.8.8.8", 37.8044, -122.2712)

        # _geolocate_ip catches RequestException → returns None → fail-open path
        assert result["valid"] is True
        assert result["distance_miles"] is None
        assert result["ip_location"] is None
        assert result["reason"] == "IP geolocation unavailable - allowed"

    def test_unexpected_exception_in_validator_fails_open(self):
        """Malformed IP naturally raises ValueError inside _is_local_ip (int('abc')).
        That exception propagates to validate_location's outer try/except, which
        must fail-open with the exception message embedded in `reason`."""
        v = LocationValidator()
        with patch.object(lv_mod.requests, "get") as mock_get:
            result = v.validate_location("11.abc.1.1", 37.8044, -122.2712)

        # The bad IP short-circuits before any HTTP call is attempted
        assert mock_get.call_count == 0
        assert result["valid"] is True
        assert result["distance_miles"] is None
        assert result["ip_location"] is None
        assert result["reason"] == (
            "Validation error - allowed: invalid literal for int() with base 10: 'abc'"
        )

    def test_default_max_distance_is_50_miles(self):
        """Distance of 60mi should fail under the default threshold."""
        v = LocationValidator()
        # (0,0) → (0, 0.8685) ≈ 60 miles
        resp = _mock_response(_ipapi_payload(lat=0.0, lon=0.0))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 0.0, 0.8685)

        assert result["valid"] is False
        assert "exceeds 50.0 mile limit" in result["reason"]

    def test_distance_rounded_to_two_decimals(self):
        """distance_miles is explicitly rounded to 2dp."""
        v = LocationValidator()
        resp = _mock_response(_ipapi_payload(lat=0.0, lon=0.0))
        with patch.object(lv_mod.requests, "get", return_value=resp):
            result = v.validate_location("8.8.8.8", 1.0, 0.0)

        # Raw is ~69.0976 → rounded 69.1
        assert result["distance_miles"] == 69.1


# ---------------------------------------------------------------------------
# get_location_validator (singleton factory)
# ---------------------------------------------------------------------------


class TestGetLocationValidator:
    def test_returns_location_validator_instance(self):
        v = get_location_validator()
        assert type(v) is LocationValidator
        # With no IPINFO_TOKEN, defaults to ip-api fallback
        assert v.use_ipinfo is False
        assert v.base_url == "http://ip-api.com/json"

    def test_second_call_returns_cached_instance(self):
        first = get_location_validator()
        second = get_location_validator()
        assert first is second

    def test_cached_instance_survives_env_change(self, monkeypatch):
        """Once created, singleton isn't rebuilt when IPINFO_TOKEN changes."""
        first = get_location_validator()  # no token → ip-api
        assert first.use_ipinfo is False

        monkeypatch.setenv("IPINFO_TOKEN", "late-token")
        second = get_location_validator()
        assert first is second
        # The cached instance keeps its original config
        assert second.use_ipinfo is False
        assert second.ipinfo_token is None

    def test_fresh_instance_after_module_reset_honors_env(self, monkeypatch):
        """Resetting the module global and re-calling picks up the new env."""
        monkeypatch.setenv("IPINFO_TOKEN", "fresh-token")
        lv_mod._location_validator = None
        v = get_location_validator()
        assert v.ipinfo_token == "fresh-token"
        assert v.use_ipinfo is True
        assert v.base_url == "https://ipinfo.io"
