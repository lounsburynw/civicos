"""
Tests for issues router: listing, search, timeline, status history,
creation, linking, status updates, and operational issues.

Mocks external dependencies (IssueStorage, SeeClickFixClient, auth)
while exercising all filtering, sorting, and error logic in the router.

To run:
    pytest packages/civicos-services/tests/test_issues.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.issues import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI app with the issues router and auth bypassed."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """TestClient with auth dependency overridden to return 'user-1'."""
    from civicos_services.servers.routers.dependencies import verify_auth, AuthContext

    async def mock_auth():
        return AuthContext(key_id="user-1", source="env", tier="admin")

    app.dependency_overrides[verify_auth] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_issue(
    id="iss-1",
    user_id="user-1",
    title="Pothole on Main St",
    description="Large pothole near 123 Main",
    category="roads",
    status="open",
    jurisdiction_id="city-san-rafael",
    created_at="2026-01-15T10:00:00",
    linked_events=None,
    status_history=None,
    address=None,
    **extra,
):
    d = {
        "id": id,
        "user_id": user_id,
        "title": title,
        "description": description,
        "category": category,
        "status": status,
        "jurisdiction_id": jurisdiction_id,
        "created_at": created_at,
        "linked_events": linked_events or [],
        "status_history": status_history or [],
    }
    if address is not None:
        d["address"] = address
    d.update(extra)
    return d


SAMPLE_ISSUES = [
    _make_issue(id="iss-1", user_id="user-1", status="open", category="roads"),
    _make_issue(
        id="iss-2",
        user_id="user-1",
        title="Broken streetlight",
        description="Streetlight out on Elm Ave",
        status="closed",
        category="lighting",
    ),
    _make_issue(
        id="iss-3",
        user_id="user-2",
        title="Graffiti on bridge",
        description="Graffiti tags on pedestrian bridge",
        status="open",
        category="vandalism",
    ),
    _make_issue(
        id="iss-4",
        user_id="user-1",
        title="Noise complaint",
        description="Construction noise after hours",
        status="resolved",
        category="noise",
        linked_events=["evt-10"],
    ),
]


@pytest.fixture
def mock_storage():
    """Return a mock IssueStorage pre-loaded with SAMPLE_ISSUES."""
    storage = MagicMock()
    storage.get_issues_for_user.return_value = list(SAMPLE_ISSUES)
    storage.get_followed_issue_ids.return_value = {"iss-3"}
    storage.get_issue.side_effect = lambda iid: next(
        (i for i in SAMPLE_ISSUES if i["id"] == iid), None
    )
    return storage


@pytest.fixture
def patch_storage(mock_storage):
    """Patch get_issue_storage to return the mock."""
    with patch(
        "civicos_services.servers.routers.issues.get_issue_storage",
        return_value=mock_storage,
    ):
        yield mock_storage


# ---------------------------------------------------------------------------
# GET /issues — list issues
# ---------------------------------------------------------------------------

class TestListIssues:
    def test_returns_own_issues_by_default(self, client, patch_storage):
        resp = client.get("/issues")
        assert resp.status_code == 200
        body = resp.json()
        # ownership=mine filters to user_id == "user-1" (the auth token)
        ids = [i["id"] for i in body["issues"]]
        assert "iss-1" in ids
        assert "iss-2" in ids
        assert "iss-4" in ids
        assert "iss-3" not in ids  # user-2's issue
        assert body["count"] == 3

    def test_ownership_all_returns_every_issue(self, client, patch_storage):
        resp = client.get("/issues?ownership=all")
        body = resp.json()
        assert body["count"] == 4
        ids = {i["id"] for i in body["issues"]}
        assert ids == {"iss-1", "iss-2", "iss-3", "iss-4"}

    def test_ownership_following_returns_followed_issues(self, client, patch_storage):
        resp = client.get("/issues?ownership=following")
        body = resp.json()
        ids = [i["id"] for i in body["issues"]]
        assert ids == ["iss-3"]
        assert body["count"] == 1

    def test_status_open_excludes_closed_and_resolved(self, client, patch_storage):
        resp = client.get("/issues?ownership=all&status=open")
        body = resp.json()
        statuses = {i["status"] for i in body["issues"]}
        assert "closed" not in statuses
        assert "resolved" not in statuses
        ids = {i["id"] for i in body["issues"]}
        assert ids == {"iss-1", "iss-3"}

    def test_status_closed_includes_closed_and_resolved(self, client, patch_storage):
        resp = client.get("/issues?ownership=all&status=closed")
        body = resp.json()
        ids = {i["id"] for i in body["issues"]}
        assert ids == {"iss-2", "iss-4"}

    def test_status_matched_returns_issues_with_linked_events(self, client, patch_storage):
        resp = client.get("/issues?ownership=all&status=matched")
        body = resp.json()
        ids = [i["id"] for i in body["issues"]]
        assert ids == ["iss-4"]
        assert body["issues"][0]["linked_events"] == ["evt-10"]

    def test_user_id_param_overrides_token(self, client, patch_storage):
        resp = client.get("/issues?user_id=user-2&ownership=mine")
        body = resp.json()
        ids = [i["id"] for i in body["issues"]]
        assert ids == ["iss-3"]
        patch_storage.get_issues_for_user.assert_called_with("user-2")

    def test_storage_unavailable_returns_empty_with_error(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.get("/issues")
            assert resp.status_code == 200
            body = resp.json()
            assert body["issues"] == []
            assert body["count"] == 0
            assert body["error"] == "Issue storage not available"

    def test_storage_exception_returns_500(self, client):
        bad_storage = MagicMock()
        bad_storage.get_issues_for_user.side_effect = RuntimeError("DB gone")
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=bad_storage,
        ):
            resp = client.get("/issues")
            assert resp.status_code == 500
            assert "DB gone" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /issues/search
# ---------------------------------------------------------------------------

class TestSearchIssues:
    def test_basic_search_returns_matching_issues(self, client, patch_storage):
        resp = client.get("/issues/search?user_id=user-1")
        assert resp.status_code == 200
        body = resp.json()
        # Default ownership=mine → user-1's issues
        assert body["count"] == 3
        assert body["query"]["user_id"] == "user-1"

    def test_category_filter(self, client, patch_storage):
        resp = client.get("/issues/search?user_id=user-1&ownership=all&category=roads")
        body = resp.json()
        assert body["count"] == 1
        assert body["issues"][0]["category"] == "roads"
        assert body["filters_applied"]["category"] == "roads"

    def test_category_matches_issue_type_field(self, client):
        """Category filter also checks the issue_type field."""
        storage = MagicMock()
        issue_with_issue_type = _make_issue(
            id="iss-x", category=None, issue_type="paving"
        )
        storage.get_issues_for_user.return_value = [issue_with_issue_type]
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.get(
                "/issues/search?user_id=user-1&ownership=all&category=paving"
            )
            body = resp.json()
            assert body["count"] == 1
            assert body["issues"][0]["id"] == "iss-x"

    def test_jurisdiction_filter(self, client, patch_storage):
        resp = client.get(
            "/issues/search?user_id=user-1&ownership=all&jurisdiction=city-san-rafael"
        )
        body = resp.json()
        assert body["count"] == 4  # all sample issues are city-san-rafael
        assert body["filters_applied"]["jurisdiction"] == "city-san-rafael"

    def test_jurisdiction_filter_excludes_non_matching(self, client, patch_storage):
        resp = client.get(
            "/issues/search?user_id=user-1&ownership=all&jurisdiction=city-mill-valley"
        )
        body = resp.json()
        assert body["count"] == 0

    def test_text_search_in_title(self, client, patch_storage):
        resp = client.get("/issues/search?user_id=user-1&ownership=all&q=pothole")
        body = resp.json()
        assert body["count"] == 1
        assert body["issues"][0]["id"] == "iss-1"
        assert body["filters_applied"]["q"] == "pothole"

    def test_text_search_in_description(self, client, patch_storage):
        resp = client.get(
            "/issues/search?user_id=user-1&ownership=all&q=construction"
        )
        body = resp.json()
        assert body["count"] == 1
        assert body["issues"][0]["id"] == "iss-4"

    def test_text_search_in_address(self, client):
        storage = MagicMock()
        storage.get_issues_for_user.return_value = [
            _make_issue(id="iss-addr", address="456 Oak Blvd"),
        ]
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.get(
                "/issues/search?user_id=user-1&ownership=all&q=oak"
            )
            body = resp.json()
            assert body["count"] == 1
            assert body["issues"][0]["id"] == "iss-addr"

    def test_text_search_case_insensitive(self, client, patch_storage):
        resp = client.get("/issues/search?user_id=user-1&ownership=all&q=POTHOLE")
        body = resp.json()
        assert body["count"] == 1
        assert body["issues"][0]["id"] == "iss-1"

    def test_combined_filters_narrow_results(self, client, patch_storage):
        resp = client.get(
            "/issues/search?user_id=user-1&ownership=all"
            "&status=open&category=roads&q=pothole"
        )
        body = resp.json()
        assert body["count"] == 1
        assert body["issues"][0]["id"] == "iss-1"
        assert body["filters_applied"] == {
            "status": "open",
            "category": "roads",
            "q": "pothole",
        }

    def test_storage_unavailable_returns_empty_search_result(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.get("/issues/search?user_id=user-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["issues"] == []
            assert body["count"] == 0
            assert body["query"]["user_id"] == "user-1"

    def test_query_field_captures_all_params(self, client, patch_storage):
        resp = client.get(
            "/issues/search?user_id=user-1&ownership=following"
            "&status=closed&category=noise&jurisdiction=city-san-rafael&q=test"
        )
        body = resp.json()
        q = body["query"]
        assert q["user_id"] == "user-1"
        assert q["ownership"] == "following"
        assert q["status"] == "closed"
        assert q["category"] == "noise"
        assert q["jurisdiction"] == "city-san-rafael"
        assert q["q"] == "test"


# ---------------------------------------------------------------------------
# GET /issues/{issue_id}
# ---------------------------------------------------------------------------

class TestGetIssue:
    def test_returns_existing_issue(self, client, patch_storage):
        resp = client.get("/issues/iss-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "iss-1"
        assert body["title"] == "Pothole on Main St"
        assert body["user_id"] == "user-1"

    def test_not_found_returns_404(self, client, patch_storage):
        resp = client.get("/issues/nonexistent")
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]

    def test_storage_unavailable_returns_503(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.get("/issues/iss-1")
            assert resp.status_code == 503
            assert "not available" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /issues/{issue_id}/timeline
# ---------------------------------------------------------------------------

class TestIssueTimeline:
    def test_timeline_includes_creation_event(self, client, patch_storage):
        resp = client.get("/issues/iss-1/timeline")
        assert resp.status_code == 200
        body = resp.json()
        assert body["issue_id"] == "iss-1"
        types = [e["type"] for e in body["timeline"]]
        assert "created" in types
        created = next(e for e in body["timeline"] if e["type"] == "created")
        assert created["timestamp"] == "2026-01-15T10:00:00"
        assert "Pothole on Main St" in created["description"]

    def test_timeline_includes_status_history(self, client):
        issue = _make_issue(
            id="iss-hist",
            status_history=[
                {
                    "status": "in_progress",
                    "from_status": "open",
                    "timestamp": "2026-01-16T08:00:00",
                    "reason": "Assigned to crew",
                },
                {
                    "status": "resolved",
                    "from_status": "in_progress",
                    "timestamp": "2026-01-17T14:00:00",
                    "reason": "Repaired",
                },
            ],
        )
        storage = MagicMock()
        storage.get_issue.return_value = issue
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.get("/issues/iss-hist/timeline")
            body = resp.json()
            status_events = [
                e for e in body["timeline"] if e["type"] == "status_change"
            ]
            assert len(status_events) == 2
            assert status_events[0]["to_status"] == "in_progress"
            assert status_events[0]["from_status"] == "open"
            assert status_events[0]["reason"] == "Assigned to crew"
            assert status_events[1]["to_status"] == "resolved"

    def test_timeline_includes_linked_events(self, client, patch_storage):
        resp = client.get("/issues/iss-4/timeline")
        body = resp.json()
        linked = [e for e in body["timeline"] if e["type"] == "event_linked"]
        assert len(linked) == 1
        assert linked[0]["event_id"] == "evt-10"
        assert "evt-10" in linked[0]["description"]

    def test_timeline_sorted_by_timestamp(self, client):
        issue = _make_issue(
            id="iss-sort",
            created_at="2026-01-10T00:00:00",
            status_history=[
                {"status": "closed", "timestamp": "2026-01-12T00:00:00"},
            ],
            linked_events=["evt-5"],
        )
        storage = MagicMock()
        storage.get_issue.return_value = issue
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.get("/issues/iss-sort/timeline")
            body = resp.json()
            timestamps = [
                e.get("timestamp") or "" for e in body["timeline"]
            ]
            assert timestamps == sorted(timestamps)

    def test_timeline_empty_history_only_has_creation(self, client, patch_storage):
        resp = client.get("/issues/iss-1/timeline")
        body = resp.json()
        # iss-1 has no status_history and no linked_events
        assert len(body["timeline"]) == 1
        assert body["timeline"][0]["type"] == "created"

    def test_timeline_not_found_returns_404(self, client, patch_storage):
        resp = client.get("/issues/nope/timeline")
        assert resp.status_code == 404

    def test_timeline_storage_unavailable_returns_503(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.get("/issues/iss-1/timeline")
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /issues/{issue_id}/status-history
# ---------------------------------------------------------------------------

class TestStatusHistory:
    def test_returns_current_status_and_history(self, client):
        issue = _make_issue(
            id="iss-sh",
            status="resolved",
            status_history=[
                {"status": "in_progress", "timestamp": "2026-01-15"},
                {"status": "resolved", "timestamp": "2026-01-16"},
            ],
        )
        storage = MagicMock()
        storage.get_issue.return_value = issue
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.get("/issues/iss-sh/status-history")
            assert resp.status_code == 200
            body = resp.json()
            assert body["issue_id"] == "iss-sh"
            assert body["current_status"] == "resolved"
            assert len(body["history"]) == 2
            assert body["history"][0]["status"] == "in_progress"
            assert body["history"][1]["status"] == "resolved"

    def test_empty_history(self, client, patch_storage):
        resp = client.get("/issues/iss-1/status-history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_status"] == "open"
        assert body["history"] == []

    def test_not_found_returns_404(self, client, patch_storage):
        resp = client.get("/issues/missing/status-history")
        assert resp.status_code == 404

    def test_storage_unavailable_returns_503(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.get("/issues/iss-1/status-history")
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /issues
# ---------------------------------------------------------------------------

class TestCreateIssue:
    def test_creates_issue_with_all_fields(self, client):
        created = _make_issue(id="iss-new", user_id="user-1", title="New issue")
        storage = MagicMock()
        storage.create_issue.return_value = created
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.post(
                "/issues",
                json={
                    "title": "New issue",
                    "description": "Some desc",
                    "category": "parks",
                    "jurisdiction_id": "city-san-rafael",
                    "location": {"lat": 37.97, "lng": -122.53},
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert body["issue"]["id"] == "iss-new"
            # Verify storage was called with auth token as user_id
            storage.create_issue.assert_called_once_with(
                user_id="user-1",
                title="New issue",
                description="Some desc",
                category="parks",
                jurisdiction_id="city-san-rafael",
                location={"lat": 37.97, "lng": -122.53},
            )

    def test_creates_issue_with_minimal_fields(self, client):
        created = _make_issue(id="iss-min", title="Minimal")
        storage = MagicMock()
        storage.create_issue.return_value = created
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=storage,
        ):
            resp = client.post("/issues", json={"title": "Minimal"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            storage.create_issue.assert_called_once_with(
                user_id="user-1",
                title="Minimal",
                description=None,
                category=None,
                jurisdiction_id=None,
                location=None,
            )

    def test_missing_title_returns_422(self, client, patch_storage):
        resp = client.post("/issues", json={})
        assert resp.status_code == 422

    def test_storage_unavailable_returns_500(self, client):
        """create_issue has no explicit None guard — None storage raises AttributeError → 500."""
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.post("/issues", json={"title": "Test"})
            assert resp.status_code == 500
            assert "Server error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /issues/{issue_id}/link-events
# ---------------------------------------------------------------------------

class TestLinkEvents:
    def test_links_events_to_issue(self, client, patch_storage):
        patch_storage.link_events.return_value = ["evt-1", "evt-2"]
        resp = client.post(
            "/issues/iss-1/link-events",
            json={"event_ids": ["evt-1", "evt-2"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["issue_id"] == "iss-1"
        assert body["linked_events"] == ["evt-1", "evt-2"]
        patch_storage.link_events.assert_called_once_with(
            "iss-1", ["evt-1", "evt-2"]
        )

    def test_issue_not_found_returns_404(self, client, patch_storage):
        resp = client.post(
            "/issues/nonexistent/link-events",
            json={"event_ids": ["evt-1"]},
        )
        assert resp.status_code == 404

    def test_storage_unavailable_returns_503(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.post(
                "/issues/iss-1/link-events",
                json={"event_ids": ["evt-1"]},
            )
            assert resp.status_code == 503

    def test_empty_event_ids_still_calls_storage(self, client, patch_storage):
        patch_storage.link_events.return_value = []
        resp = client.post(
            "/issues/iss-1/link-events",
            json={"event_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["linked_events"] == []


# ---------------------------------------------------------------------------
# PUT /issues/{issue_id}/status
# ---------------------------------------------------------------------------

class TestUpdateIssueStatus:
    def test_updates_status_with_reason(self, client, patch_storage):
        updated_issue = _make_issue(id="iss-1", status="closed")
        patch_storage.update_status.return_value = updated_issue
        resp = client.put(
            "/issues/iss-1/status",
            json={"status": "closed", "reason": "Repaired"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["issue"]["status"] == "closed"
        patch_storage.update_status.assert_called_once_with(
            issue_id="iss-1",
            new_status="closed",
            reason="Repaired",
            updated_by="user-1",
        )

    def test_updates_status_without_reason(self, client, patch_storage):
        updated_issue = _make_issue(id="iss-1", status="in_progress")
        patch_storage.update_status.return_value = updated_issue
        resp = client.put(
            "/issues/iss-1/status",
            json={"status": "in_progress"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["issue"]["status"] == "in_progress"
        patch_storage.update_status.assert_called_once_with(
            issue_id="iss-1",
            new_status="in_progress",
            reason=None,
            updated_by="user-1",
        )

    def test_issue_not_found_returns_404(self, client, patch_storage):
        resp = client.put(
            "/issues/nonexistent/status",
            json={"status": "closed"},
        )
        assert resp.status_code == 404

    def test_missing_status_returns_422(self, client, patch_storage):
        resp = client.put("/issues/iss-1/status", json={})
        assert resp.status_code == 422

    def test_storage_unavailable_returns_503(self, client):
        with patch(
            "civicos_services.servers.routers.issues.get_issue_storage",
            return_value=None,
        ):
            resp = client.put(
                "/issues/iss-1/status",
                json={"status": "closed"},
            )
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /operational-issues/{jurisdiction_id}
# ---------------------------------------------------------------------------

class TestOperationalIssues:
    """SeeClickFixClient is imported locally inside the endpoint function,
    so we patch it at the source module path."""

    def test_returns_seeclickfix_issues(self, client):
        mock_issues = [
            {"id": "scf-1", "title": "Broken curb", "status": "open"},
            {"id": "scf-2", "title": "Fallen tree", "status": "acknowledged"},
        ]
        mock_client = MagicMock()
        mock_client.get_issues.return_value = mock_issues
        with patch(
            "civicos_services.clients.seeclickfix_client.SeeClickFixClient",
            return_value=mock_client,
        ):
            resp = client.get("/operational-issues/city-san-rafael?limit=10")
            assert resp.status_code == 200
            body = resp.json()
            assert body["jurisdiction_id"] == "city-san-rafael"
            assert body["count"] == 2
            assert body["source"] == "seeclickfix"
            assert body["issues"][0]["title"] == "Broken curb"
            assert body["issues"][1]["title"] == "Fallen tree"
            mock_client.get_issues.assert_called_once_with(
                "city-san-rafael", limit=10, status=None
            )

    def test_passes_status_filter_to_client(self, client):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = []
        with patch(
            "civicos_services.clients.seeclickfix_client.SeeClickFixClient",
            return_value=mock_client,
        ):
            resp = client.get(
                "/operational-issues/city-san-rafael?status=open&limit=5"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["count"] == 0
            assert body["issues"] == []
            mock_client.get_issues.assert_called_once_with(
                "city-san-rafael", limit=5, status="open"
            )

    def test_import_failure_returns_empty_list(self, client):
        """When SeeClickFixClient import fails, endpoint returns empty list."""
        import civicos_services.clients.seeclickfix_client as scf_mod
        original_class = scf_mod.SeeClickFixClient
        # Temporarily remove the class so the local import raises ImportError-like behavior
        with patch.dict(
            "sys.modules",
            {"civicos_services.clients.seeclickfix_client": None},
        ):
            resp = client.get("/operational-issues/city-test")
            assert resp.status_code == 200
            body = resp.json()
            assert body["issues"] == []
            assert body["count"] == 0
            assert body["jurisdiction_id"] == "city-test"

    def test_default_limit_is_50(self, client):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = []
        with patch(
            "civicos_services.clients.seeclickfix_client.SeeClickFixClient",
            return_value=mock_client,
        ):
            resp = client.get("/operational-issues/city-san-rafael")
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
            mock_client.get_issues.assert_called_once_with(
                "city-san-rafael", limit=50, status=None
            )
