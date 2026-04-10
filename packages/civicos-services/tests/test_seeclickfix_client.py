"""
Tests for seeclickfix_client.py — SeeClickFix API v2 client.

Tests pure-logic methods (normalization, zoom calculation, place URL generation)
and request-handling logic (retry, throttle, pagination). HTTP calls are mocked;
all data transformation and control flow runs for real.

To run:
    pytest packages/civicos-services/tests/test_seeclickfix_client.py -q --override-ini="addopts="
"""

import time as _time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.clients.seeclickfix_client import (
    SeeClickFixClient,
    get_issues_near_location,
    get_san_rafael_issues,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> SeeClickFixClient:
    """Create a client with rate-limiting interval zeroed for test speed."""
    client = SeeClickFixClient()
    client.min_request_interval = 0  # Skip throttle sleeps in tests
    return client


def _raw_issue(**overrides) -> dict:
    """Minimal raw SeeClickFix API issue with controllable fields."""
    defaults = {
        "id": 12345,
        "summary": "Pothole on 4th Street",
        "description": "Large pothole near intersection",
        "status": "Open",
        "address": "123 4th St, San Rafael, CA",
        "lat": 37.9735,
        "lng": -122.5311,
        "point": {"type": "Point", "coordinates": [-122.5311, 37.9735]},
        "request_type": {
            "id": 42,
            "title": "Pothole/Road Condition",
            "organization": "City of San Rafael",
        },
        "created_at": "2025-10-01T12:00:00-07:00",
        "updated_at": "2025-10-02T09:00:00-07:00",
        "acknowledged_at": None,
        "closed_at": None,
        "reopened_at": None,
        "reporter": {
            "id": 999,
            "name": "Jane Doe",
            "role": "Registered",
            "avatar": {"square_100x100": "https://cdn.scf.com/avatar.jpg"},
            "civic_points": 150,
        },
        "media": {
            "image_full": "https://cdn.scf.com/img_full.jpg",
            "image_square_100x100": "https://cdn.scf.com/img_thumb.jpg",
            "video_url": None,
        },
        "rating": 3,
        "comment_count": 2,
        "html_url": "https://seeclickfix.com/issues/12345",
        "url": "https://seeclickfix.com/api/v2/issues/12345",
        "comment_url": "https://seeclickfix.com/api/v2/issues/12345/comments",
        "transitions": {"close": "https://..."},
        "private_visibility": False,
        "show_blocked_issue_text": False,
    }
    defaults.update(overrides)
    return defaults


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestSeeClickFixClientInit:
    def test_base_url(self):
        client = SeeClickFixClient()
        assert client.base_url == "https://seeclickfix.com/api/v2"

    def test_session_headers(self):
        client = SeeClickFixClient()
        assert "Civic Conversational OS" in client.session.headers["User-Agent"]
        assert client.session.headers["Accept"] == "application/json"

    def test_throttle_defaults(self):
        client = SeeClickFixClient()
        assert client.last_request_time == 0
        assert client.min_request_interval == 0.5


# ---------------------------------------------------------------------------
# _throttle_request
# ---------------------------------------------------------------------------


class TestThrottleRequest:
    def test_first_call_does_not_sleep(self):
        client = _make_client()
        client.last_request_time = 0
        client.min_request_interval = 0.5
        with patch("civicos_services.clients.seeclickfix_client.time.sleep") as mock_sleep:
            client._throttle_request()
            mock_sleep.assert_not_called()
        assert client.last_request_time > 0

    def test_rapid_call_triggers_sleep(self):
        client = _make_client()
        client.min_request_interval = 0.5
        client.last_request_time = _time.time()  # Just now
        with patch("civicos_services.clients.seeclickfix_client.time.sleep") as mock_sleep:
            client._throttle_request()
            mock_sleep.assert_called_once_with(0.5)
        assert client.last_request_time > 0


# ---------------------------------------------------------------------------
# _calculate_zoom_from_radius
# ---------------------------------------------------------------------------


class TestCalculateZoomFromRadius:
    def test_very_large_radius(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(50000) == 10
        assert client._calculate_zoom_from_radius(100000) == 10

    def test_20km(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(20000) == 11
        assert client._calculate_zoom_from_radius(30000) == 11

    def test_10km(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(10000) == 12
        assert client._calculate_zoom_from_radius(15000) == 12

    def test_5km_default(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(5000) == 13
        assert client._calculate_zoom_from_radius(7000) == 13

    def test_2km(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(2000) == 14
        assert client._calculate_zoom_from_radius(3000) == 14

    def test_1km(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(1000) == 15
        assert client._calculate_zoom_from_radius(1500) == 15

    def test_sub_1km(self):
        client = _make_client()
        assert client._calculate_zoom_from_radius(500) == 16
        assert client._calculate_zoom_from_radius(100) == 16

    def test_boundary_values(self):
        """Boundary between each zoom level tier."""
        client = _make_client()
        # 49999 < 50000 → falls to next tier (20000)
        assert client._calculate_zoom_from_radius(49999) == 11
        assert client._calculate_zoom_from_radius(19999) == 12
        assert client._calculate_zoom_from_radius(9999) == 13
        assert client._calculate_zoom_from_radius(4999) == 14
        assert client._calculate_zoom_from_radius(1999) == 15
        assert client._calculate_zoom_from_radius(999) == 16


# ---------------------------------------------------------------------------
# get_place_url_for_city
# ---------------------------------------------------------------------------


class TestGetPlaceUrlForCity:
    def test_single_word(self):
        client = _make_client()
        assert client.get_place_url_for_city("Oakland") == "oakland"

    def test_multi_word(self):
        client = _make_client()
        assert client.get_place_url_for_city("San Rafael") == "san-rafael"

    def test_removes_city_suffix(self):
        client = _make_client()
        assert client.get_place_url_for_city("New York City") == "new-york"

    def test_already_lowercase(self):
        client = _make_client()
        assert client.get_place_url_for_city("berkeley") == "berkeley"

    def test_mixed_case(self):
        client = _make_client()
        assert client.get_place_url_for_city("MILL VALLEY") == "mill-valley"

    def test_state_param_ignored(self):
        """State is accepted but not used in current implementation."""
        client = _make_client()
        result = client.get_place_url_for_city("San Rafael", state="CA")
        assert result == "san-rafael"


# ---------------------------------------------------------------------------
# _normalize_issue
# ---------------------------------------------------------------------------


class TestNormalizeIssue:
    def test_core_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["id"] == "scf-12345"
        assert result["external_id"] == 12345
        assert result["source"] == "seeclickfix"
        assert result["issue_type"] == "operational"
        assert result["title"] == "Pothole on 4th Street"
        assert result["description"] == "Large pothole near intersection"
        assert result["status"] == "open"

    def test_location_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["location"]["address"] == "123 4th St, San Rafael, CA"
        assert result["location"]["lat"] == 37.9735
        assert result["location"]["lng"] == -122.5311
        assert result["location"]["point"]["type"] == "Point"

    def test_category_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["category"] == "Pothole/Road Condition"
        assert result["category_id"] == 42
        assert result["organization"] == "City of San Rafael"

    def test_timestamps(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["created_at"] == "2025-10-01T12:00:00-07:00"
        assert result["updated_at"] == "2025-10-02T09:00:00-07:00"
        assert result["acknowledged_at"] is None
        assert result["closed_at"] is None

    def test_reporter_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["reporter"]["id"] == 999
        assert result["reporter"]["name"] == "Jane Doe"
        assert result["reporter"]["role"] == "Registered"
        assert result["reporter"]["civic_points"] == 150
        assert result["reporter"]["avatar"] == "https://cdn.scf.com/avatar.jpg"

    def test_media_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["media"]["image_url"] == "https://cdn.scf.com/img_full.jpg"
        assert result["media"]["image_thumbnail"] == "https://cdn.scf.com/img_thumb.jpg"
        assert result["media"]["video_url"] is None

    def test_engagement_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["rating"] == 3
        assert result["comment_count"] == 2

    def test_link_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["html_url"] == "https://seeclickfix.com/issues/12345"
        assert result["api_url"] == "https://seeclickfix.com/api/v2/issues/12345"
        assert result["comment_url"] == "https://seeclickfix.com/api/v2/issues/12345/comments"

    def test_metadata_fields(self):
        client = _make_client()
        raw = _raw_issue()
        result = client._normalize_issue(raw)

        assert result["_seeclickfix_metadata"]["private_visibility"] is False
        assert result["_seeclickfix_metadata"]["show_blocked_issue_text"] is False
        assert result["_seeclickfix_metadata"]["transitions"] == {"close": "https://..."}

    def test_missing_fields_use_defaults(self):
        """Empty raw issue should still produce valid normalized output."""
        client = _make_client()
        result = client._normalize_issue({})

        assert result["id"] == "scf-None"
        assert result["external_id"] is None
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["status"] == ""
        assert result["category"] == ""
        assert result["category_id"] is None
        assert result["reporter"]["name"] == "Anonymous"
        assert result["reporter"]["role"] == "Guest"
        assert result["reporter"]["civic_points"] == 0
        assert result["rating"] == 0
        assert result["comment_count"] == 0

    def test_status_lowercased(self):
        client = _make_client()
        result = client._normalize_issue(_raw_issue(status="ACKNOWLEDGED"))
        assert result["status"] == "acknowledged"

    def test_id_prefixed_with_scf(self):
        client = _make_client()
        result = client._normalize_issue(_raw_issue(id=99999))
        assert result["id"] == "scf-99999"
        assert result["external_id"] == 99999


# ---------------------------------------------------------------------------
# _make_request
# ---------------------------------------------------------------------------


class TestMakeRequest:
    def test_success_returns_json(self):
        client = _make_client()
        mock_resp = _mock_response(200, json_data={"issues": [{"id": 1}]})
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request("issues", {"place_url": "san-rafael"})
        assert result == {"issues": [{"id": 1}]}
        client.session.get.assert_called_once()
        # Verify URL construction
        call_args = client.session.get.call_args
        assert "https://seeclickfix.com/api/v2/issues" == call_args[0][0]

    def test_non_retryable_error_returns_none(self):
        """4xx errors (except 429) should return None immediately."""
        client = _make_client()
        mock_resp = _mock_response(404, text="Not Found")
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request("issues/99999")
        assert result is None
        # Only called once (no retry for 404)
        assert client.session.get.call_count == 1

    def test_retryable_status_retries(self):
        """429, 500, 502, 503 should trigger retries."""
        client = _make_client()
        fail_resp = _mock_response(503, text="Service Unavailable")
        ok_resp = _mock_response(200, json_data={"issues": []})
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_services.clients.seeclickfix_client.time.sleep"):
            result = client._make_request("issues", retries=3)

        assert result == {"issues": []}
        assert client.session.get.call_count == 2

    def test_all_retries_exhausted_returns_none(self):
        client = _make_client()
        fail_resp = _mock_response(500, text="Internal Server Error")
        client.session.get = MagicMock(return_value=fail_resp)

        with patch("civicos_services.clients.seeclickfix_client.time.sleep"):
            result = client._make_request("issues", retries=3)

        assert result is None
        assert client.session.get.call_count == 3

    def test_exception_retries_then_returns_none(self):
        client = _make_client()
        client.session.get = MagicMock(side_effect=ConnectionError("timeout"))

        with patch("civicos_services.clients.seeclickfix_client.time.sleep"):
            result = client._make_request("issues", retries=2)

        assert result is None
        assert client.session.get.call_count == 2

    def test_exception_on_first_then_success(self):
        client = _make_client()
        ok_resp = _mock_response(200, json_data={"data": "ok"})
        client.session.get = MagicMock(
            side_effect=[ConnectionError("fail"), ok_resp]
        )

        with patch("civicos_services.clients.seeclickfix_client.time.sleep"):
            result = client._make_request("issues", retries=3)

        assert result == {"data": "ok"}
        assert client.session.get.call_count == 2

    def test_429_triggers_retry(self):
        client = _make_client()
        rate_limit_resp = _mock_response(429, text="Rate Limited")
        ok_resp = _mock_response(200, json_data={"ok": True})
        client.session.get = MagicMock(side_effect=[rate_limit_resp, ok_resp])

        with patch("civicos_services.clients.seeclickfix_client.time.sleep"):
            result = client._make_request("issues", retries=3)

        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# get_issues
# ---------------------------------------------------------------------------


class TestGetIssues:
    def _stub_make_request(self, client, response):
        """Patch _make_request on a client to return a fixed response."""
        client._make_request = MagicMock(return_value=response)

    def test_place_url_sets_params(self):
        client = _make_client()
        raw_issues = [_raw_issue(id=1), _raw_issue(id=2)]
        self._stub_make_request(client, raw_issues)

        result = client.get_issues(place_url="san-rafael", per_page=10, page=1)

        # Verify params passed to _make_request
        call_params = client._make_request.call_args[0][1]
        assert call_params["place_url"] == "san-rafael"
        assert call_params["per_page"] == 10
        assert call_params["page"] == 1

        # Verify normalized output
        assert len(result["issues"]) == 2
        assert result["issues"][0]["id"] == "scf-1"
        assert result["issues"][1]["id"] == "scf-2"

    def test_lat_lng_uses_zoom(self):
        client = _make_client()
        self._stub_make_request(client, [])

        result = client.get_issues(lat=37.97, lng=-122.53, radius=2000)

        call_params = client._make_request.call_args[0][1]
        assert call_params["lat"] == 37.97
        assert call_params["lng"] == -122.53
        assert call_params["zoom"] == 14  # 2000m → zoom 14
        assert "place_url" not in call_params
        assert result["issues"] == []
        assert result["metadata"]["has_more"] is False

    def test_place_url_takes_priority_over_lat_lng(self):
        """When both place_url and lat/lng provided, place_url wins."""
        client = _make_client()
        self._stub_make_request(client, [])

        result = client.get_issues(place_url="san-rafael", lat=37.97, lng=-122.53)

        call_params = client._make_request.call_args[0][1]
        assert call_params["place_url"] == "san-rafael"
        assert "lat" not in call_params
        assert "lng" not in call_params
        assert result["issues"] == []

    def test_per_page_capped_at_100(self):
        client = _make_client()
        self._stub_make_request(client, [])

        result = client.get_issues(place_url="test", per_page=200)

        call_params = client._make_request.call_args[0][1]
        assert call_params["per_page"] == 100
        assert result["issues"] == []

    def test_status_param_passed(self):
        client = _make_client()
        self._stub_make_request(client, [])

        result = client.get_issues(place_url="test", status="closed")

        call_params = client._make_request.call_args[0][1]
        assert call_params["status"] == "closed"
        assert result["issues"] == []

    def test_no_status_omits_param(self):
        client = _make_client()
        self._stub_make_request(client, [])

        result = client.get_issues(place_url="test", status=None)

        call_params = client._make_request.call_args[0][1]
        assert "status" not in call_params
        assert result["issues"] == []

    def test_request_types_joined(self):
        client = _make_client()
        self._stub_make_request(client, [])

        result = client.get_issues(place_url="test", request_types=[42, 55, 100])

        call_params = client._make_request.call_args[0][1]
        assert call_params["request_types"] == "42,55,100"
        assert result["issues"] == []

    def test_api_failure_returns_error_metadata(self):
        client = _make_client()
        self._stub_make_request(client, None)

        result = client.get_issues(place_url="san-rafael", per_page=20, page=3)

        assert result["issues"] == []
        assert result["metadata"]["page"] == 3
        assert result["metadata"]["per_page"] == 20
        assert result["metadata"]["total_pages"] == 0
        assert result["metadata"]["has_more"] is False
        assert result["metadata"]["error"] == "Failed to fetch issues"

    def test_list_response_format(self):
        """SeeClickFix sometimes returns a raw array instead of paginated object."""
        client = _make_client()
        raw_list = [_raw_issue(id=i) for i in range(20)]
        self._stub_make_request(client, raw_list)

        result = client.get_issues(place_url="test", per_page=20)

        assert len(result["issues"]) == 20
        # When list length == per_page → has_more = True
        assert result["metadata"]["has_more"] is True
        assert result["metadata"]["total_pages"] == 1

    def test_list_response_partial_page(self):
        """Partial page in list response → has_more = False."""
        client = _make_client()
        raw_list = [_raw_issue(id=i) for i in range(5)]
        self._stub_make_request(client, raw_list)

        result = client.get_issues(place_url="test", per_page=20, page=2)

        assert len(result["issues"]) == 5
        assert result["metadata"]["has_more"] is False
        # total_pages = page when not full
        assert result["metadata"]["total_pages"] == 2

    def test_paginated_object_response(self):
        """Normal paginated response with metadata."""
        client = _make_client()
        paginated = {
            "issues": [_raw_issue(id=1)],
            "metadata": {
                "page": 1,
                "per_page": 20,
                "total_pages": 3,
                "has_more": True,
            },
        }
        self._stub_make_request(client, paginated)

        result = client.get_issues(place_url="test")

        assert len(result["issues"]) == 1
        assert result["metadata"]["total_pages"] == 3
        assert result["metadata"]["has_more"] is True

    def test_paginated_response_without_metadata(self):
        """Paginated object without metadata key uses defaults."""
        client = _make_client()
        paginated = {"issues": [_raw_issue(id=1)]}
        self._stub_make_request(client, paginated)

        result = client.get_issues(place_url="test", page=1, per_page=20)

        assert len(result["issues"]) == 1
        assert result["metadata"]["page"] == 1
        assert result["metadata"]["has_more"] is False


# ---------------------------------------------------------------------------
# get_issue_by_id
# ---------------------------------------------------------------------------


class TestGetIssueById:
    def test_found_returns_normalized(self):
        client = _make_client()
        raw = _raw_issue(id=42, summary="Broken sidewalk")
        client._make_request = MagicMock(return_value=raw)

        result = client.get_issue_by_id(42)

        assert result["id"] == "scf-42"
        assert result["title"] == "Broken sidewalk"
        assert result["source"] == "seeclickfix"
        client._make_request.assert_called_once_with("issues/42")

    def test_not_found_returns_none(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=None)

        result = client.get_issue_by_id(99999)
        assert result is None


# ---------------------------------------------------------------------------
# get_issues_summary
# ---------------------------------------------------------------------------


class TestGetIssuesSummary:
    def _stub_get_issues(self, client, open_issues, closed_issues):
        """Replace get_issues to return controlled open/closed results."""
        def fake_get_issues(**kwargs):
            if kwargs.get("status") == "open":
                return {"issues": open_issues, "metadata": {}}
            elif kwargs.get("status") == "closed":
                return {"issues": closed_issues, "metadata": {}}
            return {"issues": [], "metadata": {}}

        client.get_issues = MagicMock(side_effect=fake_get_issues)

    def test_empty_results(self):
        client = _make_client()
        self._stub_get_issues(client, [], [])

        result = client.get_issues_summary(place_url="san-rafael")

        assert result["total_open"] == 0
        assert result["total_closed"] == 0
        assert result["by_category"] == {}
        assert result["recent_issues"] == []
        assert result["oldest_open"] is None

    def test_category_counts(self):
        client = _make_client()
        open_issues = [
            {"category": "Pothole", "created_at": "2025-10-01"},
            {"category": "Pothole", "created_at": "2025-10-02"},
            {"category": "Graffiti", "created_at": "2025-10-03"},
        ]
        closed_issues = [
            {"category": "Graffiti", "created_at": "2025-09-20"},
        ]
        self._stub_get_issues(client, open_issues, closed_issues)

        result = client.get_issues_summary(place_url="san-rafael")

        assert result["total_open"] == 3
        assert result["total_closed"] == 1
        assert result["by_category"]["Pothole"] == 2
        assert result["by_category"]["Graffiti"] == 2

    def test_oldest_open_found(self):
        client = _make_client()
        open_issues = [
            {"category": "A", "created_at": "2025-10-05"},
            {"category": "B", "created_at": "2025-09-01"},
            {"category": "C", "created_at": "2025-10-10"},
        ]
        self._stub_get_issues(client, open_issues, [])

        result = client.get_issues_summary(place_url="san-rafael")

        assert result["oldest_open"]["created_at"] == "2025-09-01"

    def test_recent_issues_capped_at_five(self):
        client = _make_client()
        open_issues = [{"category": f"Cat{i}", "created_at": f"2025-10-{i:02d}"} for i in range(1, 11)]
        self._stub_get_issues(client, open_issues, [])

        result = client.get_issues_summary(place_url="san-rafael")

        assert len(result["recent_issues"]) == 5
        # recent_issues is first 5 from open_issues
        assert result["recent_issues"][0]["category"] == "Cat1"
        assert result["recent_issues"][4]["category"] == "Cat5"

    def test_unknown_category_counted(self):
        client = _make_client()
        open_issues = [
            {"created_at": "2025-10-01"},  # No category key
        ]
        self._stub_get_issues(client, open_issues, [])

        result = client.get_issues_summary(place_url="san-rafael")

        assert result["by_category"]["Unknown"] == 1

    def test_passes_location_params(self):
        client = _make_client()
        self._stub_get_issues(client, [], [])

        result = client.get_issues_summary(lat=37.97, lng=-122.53, radius=3000)

        # Both open and closed calls should have been made
        assert client.get_issues.call_count == 2
        for call in client.get_issues.call_args_list:
            assert call[1]["lat"] == 37.97
            assert call[1]["lng"] == -122.53
            assert call[1]["radius"] == 3000
        # Verify summary output reflects empty inputs
        assert result["total_open"] == 0
        assert result["total_closed"] == 0


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    @patch("civicos_services.clients.seeclickfix_client.SeeClickFixClient")
    def test_get_san_rafael_issues_uses_san_rafael_place_url(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_issues.return_value = {
            "issues": [{"id": "scf-1", "title": "Test"}],
            "metadata": {"page": 1},
        }
        MockClient.return_value = mock_instance

        result = get_san_rafael_issues(per_page=5, page=2, status="closed")

        mock_instance.get_issues.assert_called_once_with(
            place_url="san-rafael",
            per_page=5,
            page=2,
            status="closed",
        )
        assert result["issues"][0]["id"] == "scf-1"

    @patch("civicos_services.clients.seeclickfix_client.SeeClickFixClient")
    def test_get_issues_near_location_passes_coords(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.get_issues.return_value = {
            "issues": [],
            "metadata": {"page": 1},
        }
        MockClient.return_value = mock_instance

        result = get_issues_near_location(lat=37.97, lng=-122.53, radius=3000, per_page=10)

        mock_instance.get_issues.assert_called_once_with(
            lat=37.97,
            lng=-122.53,
            radius=3000,
            per_page=10,
            status="open",
        )
        assert result["issues"] == []
