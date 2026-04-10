"""
Tests for user router: profile, location, civic history, context, export, delete.

Mocks external dependencies (PersonalizationService, IssueStorage, DraftStorage,
FollowStorage, ThreadStorage, auth) while exercising all logic in the router.

To run:
    pytest packages/civicos-services/tests/test_user.py -q --override-ini="addopts="
"""

import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.user import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI app with the user router and auth bypassed."""
    app = FastAPI()
    app.include_router(router, prefix="/user")
    return app


@pytest.fixture
def client(app):
    """TestClient with auth dependency overridden to return 'user-42'."""
    from civicos_services.servers.routers.dependencies import verify_auth, AuthContext

    async def mock_auth():
        return AuthContext(key_id="user-42", source="env", tier="admin")

    app.dependency_overrides[verify_auth] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _mock_personalization_service(**overrides):
    """Create a mock PersonalizationService with configurable returns."""
    svc = MagicMock()
    svc.get_user_profile.return_value = overrides.get("profile", None)
    svc.get_user_location.return_value = overrides.get("location", None)
    svc.update_user_profile.return_value = overrides.get("updated_profile", {"user_id": "user-42", "name": "Updated"})
    svc.set_user_location.return_value = overrides.get("set_location", {"latitude": 37.97, "longitude": -122.53})
    svc.delete_user.return_value = None
    return svc


SAMPLE_PROFILE = {
    "user_id": "user-42",
    "name": "Alice",
    "location": {"latitude": 37.97, "longitude": -122.53, "jurisdiction_id": "city-san-rafael"},
    "interests": ["housing", "transit"],
    "created_at": "2026-01-01T00:00:00Z",
}

SAMPLE_ISSUES = [
    {"id": "iss-1", "title": "Pothole on Main", "created_at": "2026-03-01T10:00:00", "status": "open"},
    {"id": "iss-2", "title": "Broken light", "created_at": "2026-02-15T08:00:00", "status": "closed"},
]

SAMPLE_DRAFTS = [
    {"id": "draft-1", "event_title": "City Council", "content": "I support the rezoning proposal", "submitted_at": "2026-03-05T14:00:00"},
]

SAMPLE_FOLLOWS = [
    {"id": "fol-1", "focal_type": "topic", "focal_id": "housing", "focal_title": "Housing", "created_at": "2026-02-20T12:00:00"},
    {"id": "fol-2", "focal_type": "meeting", "focal_id": "mtg-99", "focal_title": "Planning Commission", "created_at": "2026-03-10T09:00:00"},
]

SAMPLE_MESSAGES = [
    {"id": "msg-1", "content": "Hello", "created_at": "2026-03-01T11:00:00"},
]


def _assert_user_id(value, expected="user-42"):
    """Assert user_id matches, handling both str and serialized AuthContext."""
    if isinstance(value, dict):
        assert value["key_id"] == expected
    else:
        assert value == expected


@contextmanager
def _mock_storage_module(module_path, class_name, mock_cls):
    """Inject a mock class into sys.modules for lazy-import code.

    The source code does `from civicos_services.storage.X import Y` inside
    endpoint functions.  We create a temporary module object that has `Y`
    as an attribute so the import succeeds and returns our mock.
    """
    fake_mod = types.ModuleType(module_path)
    setattr(fake_mod, class_name, mock_cls)
    old = sys.modules.get(module_path)
    sys.modules[module_path] = fake_mod
    try:
        yield mock_cls
    finally:
        if old is None:
            sys.modules.pop(module_path, None)
        else:
            sys.modules[module_path] = old


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

class TestGetProfile:
    def test_returns_profile_from_service(self, client):
        svc = _mock_personalization_service(profile=SAMPLE_PROFILE)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.get("/user/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-42"
        assert data["name"] == "Alice"
        assert data["interests"] == ["housing", "transit"]
        assert data["location"]["jurisdiction_id"] == "city-san-rafael"

    def test_returns_defaults_when_service_unavailable(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None):
            resp = client.get("/user/profile")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        assert data["name"] is None
        assert data["interests"] == []
        assert data["note"] == "Personalization service not available"

    def test_returns_defaults_when_profile_is_none(self, client):
        svc = _mock_personalization_service(profile=None)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.get("/user/profile")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        assert data["name"] is None
        assert data["interests"] == []
        assert "created_at" in data
        assert data["created_at"].endswith("Z")

    def test_returns_500_on_service_exception(self, client):
        svc = MagicMock()
        svc.get_user_profile.side_effect = RuntimeError("DB down")
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.get("/user/profile")
        assert resp.status_code == 500
        assert "Server error" in resp.json()["detail"]
        assert "DB down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /profile
# ---------------------------------------------------------------------------

class TestUpdateProfile:
    def test_updates_name_and_interests(self, client):
        updated = {"user_id": "user-42", "name": "Bob", "interests": ["parks"]}
        svc = _mock_personalization_service(updated_profile=updated)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/profile", json={"name": "Bob", "interests": ["parks"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["profile"]["name"] == "Bob"
        assert data["profile"]["interests"] == ["parks"]
        # Verify service was called with correct args
        svc.update_user_profile.assert_called_once()
        call_kwargs = svc.update_user_profile.call_args
        assert call_kwargs.kwargs["name"] == "Bob"
        assert call_kwargs.kwargs["interests"] == ["parks"]

    def test_returns_503_when_service_unavailable(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None):
            resp = client.post("/user/profile", json={"name": "Test"})
        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"]

    def test_returns_500_on_service_exception(self, client):
        svc = MagicMock()
        svc.update_user_profile.side_effect = RuntimeError("Write failed")
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/profile", json={"name": "X"})
        assert resp.status_code == 500
        assert "Write failed" in resp.json()["detail"]

    def test_empty_update_body_still_succeeds(self, client):
        updated = {"user_id": "user-42"}
        svc = _mock_personalization_service(updated_profile=updated)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/profile", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# GET /location
# ---------------------------------------------------------------------------

class TestGetLocation:
    def test_returns_location_from_service(self, client):
        loc = {"latitude": 37.97, "longitude": -122.53, "jurisdiction_id": "city-san-rafael"}
        svc = _mock_personalization_service(location=loc)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.get("/user/location")
        assert resp.status_code == 200
        data = resp.json()
        assert data["location"]["latitude"] == 37.97
        assert data["location"]["longitude"] == -122.53
        assert data["location"]["jurisdiction_id"] == "city-san-rafael"

    def test_returns_null_location_when_service_unavailable(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None):
            resp = client.get("/user/location")
        assert resp.status_code == 200
        data = resp.json()
        assert data["location"] is None
        assert data["note"] == "Personalization service not available"

    def test_returns_null_location_when_not_set(self, client):
        svc = _mock_personalization_service(location=None)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.get("/user/location")
        assert resp.status_code == 200
        assert resp.json()["location"] is None


# ---------------------------------------------------------------------------
# POST /location
# ---------------------------------------------------------------------------

class TestSetLocation:
    def test_sets_location_with_address(self, client):
        loc_result = {"latitude": 37.97, "longitude": -122.53, "address": "123 Main St"}
        svc = _mock_personalization_service(set_location=loc_result)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/location", json={"latitude": 37.97, "longitude": -122.53, "address": "123 Main St"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["location"]["latitude"] == 37.97
        assert data["location"]["address"] == "123 Main St"

    def test_sets_location_without_address(self, client):
        loc_result = {"latitude": 38.0, "longitude": -123.0}
        svc = _mock_personalization_service(set_location=loc_result)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/location", json={"latitude": 38.0, "longitude": -123.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["location"]["latitude"] == 38.0

    def test_returns_503_when_service_unavailable(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None):
            resp = client.post("/user/location", json={"latitude": 37.0, "longitude": -122.0})
        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"]

    def test_returns_422_for_missing_required_fields(self, client):
        svc = _mock_personalization_service()
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/location", json={"latitude": 37.0})
        assert resp.status_code == 422

    def test_passes_correct_args_to_service(self, client):
        svc = _mock_personalization_service()
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.post("/user/location", json={"latitude": 37.5, "longitude": -122.5, "address": "456 Oak"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        call_kwargs = svc.set_user_location.call_args.kwargs
        assert call_kwargs["user_id"] == "user-42"
        assert call_kwargs["latitude"] == 37.5
        assert call_kwargs["longitude"] == -122.5
        assert call_kwargs["address"] == "456 Oak"


# ---------------------------------------------------------------------------
# GET /civic-history
# ---------------------------------------------------------------------------

class TestGetCivicHistory:
    @contextmanager
    def _with_storages(self, issues=None, drafts=None, follows=None):
        """Inject mock storage modules for the lazy imports in civic-history."""
        mock_issue_cls = MagicMock()
        mock_issue_cls.return_value.get_issues_for_user.return_value = issues or []
        mock_draft_cls = MagicMock()
        mock_draft_cls.return_value.get_user_drafts.return_value = drafts or []
        mock_follow_cls = MagicMock()
        mock_follow_cls.return_value.get_follows_for_user.return_value = follows or []

        with _mock_storage_module("civicos_services.storage.issue_storage", "IssueStorage", mock_issue_cls), \
             _mock_storage_module("civicos_services.storage.draft_storage", "DraftStorage", mock_draft_cls), \
             _mock_storage_module("civicos_services.storage.follow_storage", "FollowStorage", mock_follow_cls):
            yield

    def test_aggregates_issues_drafts_and_follows(self, client):
        """History includes items from all three sources."""
        with self._with_storages(issues=SAMPLE_ISSUES, drafts=SAMPLE_DRAFTS, follows=SAMPLE_FOLLOWS):
            resp = client.get("/user/civic-history")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        # 2 issues + 1 draft + 2 follows = 5 items
        assert data["count"] == 5
        types = {item["type"] for item in data["history"]}
        assert "issue_filed" in types
        assert "comment_submitted" in types
        assert "follow_created" in types

    def test_history_sorted_most_recent_first(self, client):
        """Items are sorted by timestamp descending."""
        with self._with_storages(issues=SAMPLE_ISSUES, drafts=SAMPLE_DRAFTS, follows=SAMPLE_FOLLOWS):
            resp = client.get("/user/civic-history")
        data = resp.json()
        timestamps = [item["timestamp"] for item in data["history"] if item["timestamp"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_history_respects_limit_parameter(self, client):
        """Only returns up to `limit` items."""
        with self._with_storages(issues=SAMPLE_ISSUES, drafts=SAMPLE_DRAFTS, follows=SAMPLE_FOLLOWS):
            resp = client.get("/user/civic-history?limit=2")
        data = resp.json()
        assert data["count"] == 2
        assert len(data["history"]) == 2

    def test_issue_filed_has_correct_fields(self, client):
        """Issue history items contain expected type, title, and reference_id."""
        with self._with_storages(issues=SAMPLE_ISSUES):
            resp = client.get("/user/civic-history")
        data = resp.json()
        issue_items = [h for h in data["history"] if h["type"] == "issue_filed"]
        assert len(issue_items) == 2
        first = issue_items[0]
        assert first["title"] == "Pothole on Main"
        assert first["reference_id"] == "iss-1"
        assert first["description"] == "Filed issue: Pothole on Main"

    def test_comment_submitted_truncates_content(self, client):
        """Draft content is truncated to 100 chars in description."""
        long_draft = [{"id": "d-1", "event_title": "Hearing", "content": "A" * 200, "submitted_at": "2026-01-01T00:00:00"}]
        with self._with_storages(drafts=long_draft):
            resp = client.get("/user/civic-history")
        data = resp.json()
        comment_items = [h for h in data["history"] if h["type"] == "comment_submitted"]
        assert len(comment_items) == 1
        assert len(comment_items[0]["description"]) == 100

    def test_follow_created_includes_focal_info(self, client):
        """Follow history items include focal type and ID in description."""
        with self._with_storages(follows=SAMPLE_FOLLOWS):
            resp = client.get("/user/civic-history")
        data = resp.json()
        follow_items = [h for h in data["history"] if h["type"] == "follow_created"]
        assert len(follow_items) == 2
        assert "Following: Housing" in follow_items[0]["title"] or "Following: Planning Commission" in follow_items[0]["title"]
        assert any("topic" in f["description"] for f in follow_items)

    def test_empty_history_when_no_storages_available(self, client):
        """Returns empty history when all storage imports fail."""
        with patch.dict("sys.modules", {
            "civicos_services.storage.issue_storage": None,
            "civicos_services.storage.draft_storage": None,
            "civicos_services.storage.follow_storage": None,
        }):
            resp = client.get("/user/civic-history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["history"] == []


# ---------------------------------------------------------------------------
# GET /context
# ---------------------------------------------------------------------------

class TestGetContext:
    def test_includes_profile_data_when_service_available(self, client):
        svc = _mock_personalization_service(profile=SAMPLE_PROFILE)
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc), \
             patch.dict("sys.modules", {
                 "civicos_services.storage.follow_storage": None,
                 "civicos_services.storage.issue_storage": None,
             }):
            resp = client.get("/user/context")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        assert data["interests"] == ["housing", "transit"]
        assert data["jurisdiction_id"] == "city-san-rafael"
        assert data["location"]["latitude"] == 37.97
        assert data["timestamp"].endswith("Z")

    def test_includes_follows_and_issues(self, client):
        svc = _mock_personalization_service(profile=None)

        mock_follow_cls = MagicMock()
        mock_follow_cls.return_value.get_follows_for_user.return_value = SAMPLE_FOLLOWS

        mock_issue_cls = MagicMock()
        mock_issue_cls.return_value.get_issues_for_user.return_value = SAMPLE_ISSUES

        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc), \
             _mock_storage_module("civicos_services.storage.follow_storage", "FollowStorage", mock_follow_cls), \
             _mock_storage_module("civicos_services.storage.issue_storage", "IssueStorage", mock_issue_cls):
            resp = client.get("/user/context")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["follows"]) == 2
        assert data["follows"][0]["type"] == "topic"
        assert data["follows"][0]["id"] == "housing"
        assert len(data["recent_issues"]) == 2
        assert data["recent_issues"][0]["id"] == "iss-1"
        assert data["recent_issues"][0]["title"] == "Pothole on Main"

    def test_context_without_profile_service(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None), \
             patch.dict("sys.modules", {
                 "civicos_services.storage.follow_storage": None,
                 "civicos_services.storage.issue_storage": None,
             }):
            resp = client.get("/user/context")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        assert data["follows"] == []
        assert data["recent_issues"] == []
        # No location or interests keys when profile service unavailable
        assert "location" not in data
        assert "interests" not in data

    def test_follows_limited_to_10(self, client):
        many_follows = [{"focal_type": "topic", "focal_id": f"t-{i}", "created_at": f"2026-01-{i+1:02d}"} for i in range(15)]
        mock_follow_cls = MagicMock()
        mock_follow_cls.return_value.get_follows_for_user.return_value = many_follows

        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None), \
             _mock_storage_module("civicos_services.storage.follow_storage", "FollowStorage", mock_follow_cls), \
             patch.dict("sys.modules", {"civicos_services.storage.issue_storage": None}):
            resp = client.get("/user/context")
        data = resp.json()
        assert len(data["follows"]) == 10

    def test_issues_limited_to_5(self, client):
        many_issues = [{"id": f"iss-{i}", "title": f"Issue {i}", "status": "open"} for i in range(10)]
        mock_issue_cls = MagicMock()
        mock_issue_cls.return_value.get_issues_for_user.return_value = many_issues

        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None), \
             patch.dict("sys.modules", {"civicos_services.storage.follow_storage": None}), \
             _mock_storage_module("civicos_services.storage.issue_storage", "IssueStorage", mock_issue_cls):
            resp = client.get("/user/context")
        data = resp.json()
        assert len(data["recent_issues"]) == 5


# ---------------------------------------------------------------------------
# GET /export
# ---------------------------------------------------------------------------

class TestExportUserData:
    def test_exports_all_data_sources(self, client):
        svc = _mock_personalization_service(profile=SAMPLE_PROFILE)

        mock_issue_cls = MagicMock()
        mock_issue_cls.return_value.get_issues_for_user.return_value = SAMPLE_ISSUES

        mock_follow_cls = MagicMock()
        mock_follow_cls.return_value.get_follows_for_user.return_value = SAMPLE_FOLLOWS

        mock_draft_cls = MagicMock()
        mock_draft_cls.return_value.get_user_drafts.return_value = SAMPLE_DRAFTS

        mock_thread_cls = MagicMock()
        mock_thread_cls.return_value.get_user_messages.return_value = SAMPLE_MESSAGES

        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc), \
             _mock_storage_module("civicos_services.storage.issue_storage", "IssueStorage", mock_issue_cls), \
             _mock_storage_module("civicos_services.storage.follow_storage", "FollowStorage", mock_follow_cls), \
             _mock_storage_module("civicos_services.storage.draft_storage", "DraftStorage", mock_draft_cls), \
             _mock_storage_module("civicos_services.storage.thread_storage", "ThreadStorage", mock_thread_cls):
            resp = client.get("/user/export")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        assert data["exported_at"].endswith("Z")
        assert data["profile"]["name"] == "Alice"
        assert len(data["issues"]) == 2
        assert data["issues"][0]["id"] == "iss-1"
        assert len(data["follows"]) == 2
        assert len(data["drafts"]) == 1
        assert data["drafts"][0]["id"] == "draft-1"
        assert len(data["messages"]) == 1
        assert data["messages"][0]["id"] == "msg-1"

    def test_export_with_no_services_returns_empty_collections(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None), \
             patch.dict("sys.modules", {
                 "civicos_services.storage.issue_storage": None,
                 "civicos_services.storage.follow_storage": None,
                 "civicos_services.storage.draft_storage": None,
                 "civicos_services.storage.thread_storage": None,
             }):
            resp = client.get("/user/export")
        assert resp.status_code == 200
        data = resp.json()
        _assert_user_id(data["user_id"])
        assert data["profile"] == {}
        assert data["issues"] == []
        assert data["follows"] == []
        assert data["drafts"] == []
        assert data["messages"] == []

    def test_export_partial_service_availability(self, client):
        """When only some storage imports succeed, export still returns available data."""
        mock_issue_cls = MagicMock()
        mock_issue_cls.return_value.get_issues_for_user.return_value = SAMPLE_ISSUES

        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None), \
             _mock_storage_module("civicos_services.storage.issue_storage", "IssueStorage", mock_issue_cls), \
             patch.dict("sys.modules", {
                 "civicos_services.storage.follow_storage": None,
                 "civicos_services.storage.draft_storage": None,
                 "civicos_services.storage.thread_storage": None,
             }):
            resp = client.get("/user/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["issues"]) == 2
        assert data["follows"] == []
        assert data["drafts"] == []
        assert data["messages"] == []


# ---------------------------------------------------------------------------
# DELETE /
# ---------------------------------------------------------------------------

class TestDeleteUserAccount:
    def test_deletes_all_data_sources(self, client):
        svc = _mock_personalization_service()

        mock_issue_cls = MagicMock()
        mock_follow_cls = MagicMock()
        mock_draft_cls = MagicMock()
        mock_thread_cls = MagicMock()

        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc), \
             _mock_storage_module("civicos_services.storage.issue_storage", "IssueStorage", mock_issue_cls), \
             _mock_storage_module("civicos_services.storage.follow_storage", "FollowStorage", mock_follow_cls), \
             _mock_storage_module("civicos_services.storage.draft_storage", "DraftStorage", mock_draft_cls), \
             _mock_storage_module("civicos_services.storage.thread_storage", "ThreadStorage", mock_thread_cls):
            resp = client.delete("/user/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "User account deleted"
        details = data["details"]
        _assert_user_id(details["user_id"])
        assert details["deleted_at"].endswith("Z")
        assert details["deleted"]["profile"] is True
        assert details["deleted"]["issues"] is True
        assert details["deleted"]["follows"] is True
        assert details["deleted"]["drafts"] is True
        assert details["deleted"]["messages"] is True

        # Verify each service's delete was actually called
        svc.delete_user.assert_called_once()
        mock_issue_cls.return_value.delete_user_issues.assert_called_once()
        mock_follow_cls.return_value.delete_user_follows.assert_called_once()
        mock_draft_cls.return_value.delete_user_drafts.assert_called_once()
        mock_thread_cls.return_value.delete_user_messages.assert_called_once()

    def test_delete_marks_false_for_unavailable_services(self, client):
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=None), \
             patch.dict("sys.modules", {
                 "civicos_services.storage.issue_storage": None,
                 "civicos_services.storage.follow_storage": None,
                 "civicos_services.storage.draft_storage": None,
                 "civicos_services.storage.thread_storage": None,
             }):
            resp = client.delete("/user/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        details = data["details"]
        assert details["deleted"]["issues"] is False
        assert details["deleted"]["follows"] is False
        assert details["deleted"]["drafts"] is False
        assert details["deleted"]["messages"] is False
        # profile key should not be present since service was None
        assert "profile" not in details["deleted"]

    def test_delete_returns_500_on_unexpected_error(self, client):
        svc = MagicMock()
        svc.delete_user.side_effect = RuntimeError("Cascade failed")
        with patch("civicos_services.servers.routers.user.get_personalization_service", return_value=svc):
            resp = client.delete("/user/")
        assert resp.status_code == 500
        assert "Cascade failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestPydanticModels:
    """Verify Pydantic models enforce types and defaults correctly."""

    def test_location_requires_lat_lng(self):
        from civicos_services.servers.routers.user import Location
        loc = Location(latitude=37.97, longitude=-122.53)
        assert loc.latitude == 37.97
        assert loc.longitude == -122.53
        assert loc.address is None
        assert loc.jurisdiction_id is None

    def test_location_accepts_all_fields(self):
        from civicos_services.servers.routers.user import Location
        loc = Location(
            latitude=37.97, longitude=-122.53,
            address="123 Main", jurisdiction_id="city-san-rafael",
            city="San Rafael", state="CA", zip_code="94901"
        )
        assert loc.city == "San Rafael"
        assert loc.zip_code == "94901"

    def test_profile_update_request_all_optional(self):
        from civicos_services.servers.routers.user import ProfileUpdateRequest
        req = ProfileUpdateRequest()
        assert req.name is None
        assert req.email is None
        assert req.interests is None
        assert req.notification_preferences is None

    def test_civic_history_item_fields(self):
        from civicos_services.servers.routers.user import CivicHistoryItem
        item = CivicHistoryItem(type="issue_filed", timestamp="2026-01-01T00:00:00Z", title="Test")
        assert item.type == "issue_filed"
        assert item.title == "Test"
        assert item.description is None
        assert item.reference_id is None

    def test_user_export_requires_all_collection_fields(self):
        from civicos_services.servers.routers.user import UserExport
        export = UserExport(
            user_id="u-1",
            profile={"name": "Test"},
            issues=[],
            follows=[],
            drafts=[],
            messages=[],
            exported_at="2026-01-01T00:00:00Z",
        )
        assert export.user_id == "u-1"
        assert export.profile == {"name": "Test"}
        assert export.exported_at == "2026-01-01T00:00:00Z"

    def test_location_set_request_rejects_missing_longitude(self):
        from pydantic import ValidationError
        from civicos_services.servers.routers.user import LocationSetRequest
        with pytest.raises(ValidationError, match="longitude"):
            LocationSetRequest(latitude=37.0)
