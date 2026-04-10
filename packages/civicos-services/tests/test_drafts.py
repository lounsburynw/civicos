"""
Tests for drafts router: CRUD operations on draft comments and AI regeneration.

Mocks external dependencies (DraftStorage, OpenAI, events loader, auth)
while exercising all logic in the router endpoints.

To run:
    pytest packages/civicos-services/tests/test_drafts.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.drafts import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI app with the drafts router."""
    app = FastAPI()
    app.include_router(router)
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


def _make_storage(**overrides):
    """Create a mock DraftStorage with configurable returns."""
    s = MagicMock()
    s.get_event_drafts.return_value = overrides.get("event_drafts", [])
    s.get_draft.return_value = overrides.get("get_draft", None)
    s.create_draft.return_value = overrides.get("create_draft", {"id": "d-1", "content": "new"})
    s.update_draft.return_value = overrides.get("update_draft", {"id": "d-1", "content": "updated"})
    s.delete_draft.return_value = overrides.get("delete_draft", True)
    s.mark_submitted.return_value = overrides.get("mark_submitted", {"id": "d-1", "status": "submitted"})
    return s


SAMPLE_DRAFT = {
    "id": "d-1",
    "user_id": "user-42",
    "event_id": "evt-100",
    "content": "I support the housing plan.",
    "status": "draft",
    "created_at": "2026-03-01T10:00:00Z",
    "updated_at": "2026-03-01T12:00:00Z",
    "structured_summary": "Housing support",
    "personal_context": "Homeowner",
    "selected_agenda_items": ["item-a", "item-b"],
    "is_template": False,
}

OTHER_USER_DRAFT = {
    "id": "d-99",
    "user_id": "other-user",
    "event_id": "evt-100",
    "content": "Not my draft.",
    "status": "draft",
    "created_at": "2026-03-01T09:00:00Z",
}

SAMPLE_EVENTS = [
    {
        "id": "evt-100",
        "title": "City Council Regular Meeting",
        "agenda_items": [
            {"id": "item-a", "title": "Housing Rezoning", "description": "Rezone parcel for housing"},
            {"id": "item-b", "title": "Budget Review", "description": "FY27 budget first reading"},
        ],
    },
    {
        "id": "evt-200",
        "title": "Planning Commission",
        "agenda_items": [],
    },
]


# ---------------------------------------------------------------------------
# GET /events/{event_id}/drafts
# ---------------------------------------------------------------------------

class TestGetEventDrafts:
    def test_returns_drafts_for_event(self, client):
        storage = _make_storage(event_drafts=[SAMPLE_DRAFT])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "evt-100"
        assert data["count"] == 1
        assert data["drafts"][0]["id"] == "d-1"
        assert data["drafts"][0]["content"] == "I support the housing plan."

    def test_passes_status_filter_to_storage(self, client):
        storage = _make_storage(event_drafts=[])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/drafts?status=submitted")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        storage.get_event_drafts.assert_called_once_with(
            event_id="evt-100", user_id="user-42", status="submitted"
        )

    def test_empty_drafts_list(self, client):
        storage = _make_storage(event_drafts=[])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["drafts"] == []
        assert data["count"] == 0

    def test_storage_unavailable_returns_empty(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.get("/events/evt-100/drafts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["drafts"] == []
        assert data["note"] == "Draft storage not available"

    def test_storage_exception_returns_500(self, client):
        storage = _make_storage()
        storage.get_event_drafts.side_effect = RuntimeError("DB down")
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/drafts")
        assert resp.status_code == 500
        assert "DB down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /events/{event_id}/draft-comment
# ---------------------------------------------------------------------------

class TestGetEventDraftComment:
    def test_returns_most_recent_draft(self, client):
        storage = _make_storage(event_drafts=[SAMPLE_DRAFT])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/draft-comment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == "d-1"
        assert data["draft"] == "I support the housing plan."
        assert data["structured_summary"] == "Housing support"
        assert data["personal_context"] == "Homeowner"
        assert data["selected_agenda_items"] == ["item-a", "item-b"]
        assert data["is_template"] is False
        assert data["created_at"] == "2026-03-01T10:00:00Z"
        assert data["updated_at"] == "2026-03-01T12:00:00Z"
        assert data["submitted"] is False

    def test_submitted_draft_sets_submitted_true(self, client):
        submitted = {**SAMPLE_DRAFT, "status": "submitted"}
        storage = _make_storage(event_drafts=[submitted])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/draft-comment")
        assert resp.status_code == 200
        assert resp.json()["submitted"] is True

    def test_no_drafts_returns_null_fields(self, client):
        storage = _make_storage(event_drafts=[])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/draft-comment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] is None
        assert data["draft"] is None
        assert data["structured_summary"] is None
        assert data["personal_context"] is None
        assert data["selected_agenda_items"] == []
        assert data["is_template"] is False
        assert data["submitted"] is False

    def test_storage_unavailable_returns_null_fields_with_note(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.get("/events/evt-100/draft-comment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] is None
        assert data["draft"] is None
        assert data["note"] == "Draft storage not available"
        assert data["submitted"] is False

    def test_uses_provided_user_id_over_token(self, client):
        storage = _make_storage(event_drafts=[])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/draft-comment?user_id=other-user")
        assert resp.status_code == 200
        storage.get_event_drafts.assert_called_once_with(
            event_id="evt-100", user_id="other-user"
        )

    def test_falls_back_to_token_when_no_user_id(self, client):
        storage = _make_storage(event_drafts=[])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/draft-comment")
        assert resp.status_code == 200
        storage.get_event_drafts.assert_called_once_with(
            event_id="evt-100", user_id="user-42"
        )

    def test_draft_missing_optional_fields_uses_defaults(self, client):
        """Draft dict without structured_summary, personal_context, etc."""
        minimal = {"id": "d-2", "content": "Minimal", "status": "draft", "created_at": "2026-03-01T10:00:00Z"}
        storage = _make_storage(event_drafts=[minimal])
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/events/evt-100/draft-comment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == "d-2"
        assert data["draft"] == "Minimal"
        assert data["structured_summary"] is None
        assert data["selected_agenda_items"] == []
        assert data["is_template"] is False


# ---------------------------------------------------------------------------
# POST /events/{event_id}/draft-comment
# ---------------------------------------------------------------------------

class TestCreateDraftComment:
    def test_creates_draft_with_content(self, client):
        created = {"id": "d-new", "content": "My comment", "event_id": "evt-100"}
        storage = _make_storage(create_draft=created)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post("/events/evt-100/draft-comment", json={"content": "My comment"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["draft"]["id"] == "d-new"
        assert data["draft"]["content"] == "My comment"

    def test_creates_draft_with_item_id(self, client):
        storage = _make_storage()
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post(
                "/events/evt-100/draft-comment",
                json={"content": "My comment", "item_id": "item-a"}
            )
        assert resp.status_code == 200
        storage.create_draft.assert_called_once_with(
            user_id="user-42",
            event_id="evt-100",
            content="My comment",
            item_id="item-a"
        )

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.post("/events/evt-100/draft-comment", json={"content": "My comment"})
        assert resp.status_code == 503
        assert "Draft storage not available" in resp.json()["detail"]

    def test_missing_content_returns_422(self, client):
        storage = _make_storage()
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post("/events/evt-100/draft-comment", json={})
        assert resp.status_code == 422

    def test_storage_exception_returns_500(self, client):
        storage = _make_storage()
        storage.create_draft.side_effect = RuntimeError("Insert failed")
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post("/events/evt-100/draft-comment", json={"content": "test"})
        assert resp.status_code == 500
        assert "Insert failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /events/{event_id}/items/{item_id}/regenerate
# ---------------------------------------------------------------------------

class TestRegenerateItemComment:
    def _mock_openai(self, content="Generated comment about housing."):
        """Create a mock OpenAI client that returns specified content."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    def test_regenerates_and_saves_draft(self, client):
        mock_openai = self._mock_openai("AI-generated comment about rezoning.")
        storage = _make_storage(create_draft={"id": "d-gen", "content": "AI-generated comment about rezoning."})
        with (
            patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage),
            patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS),
            patch("openai.OpenAI", return_value=mock_openai),
        ):
            resp = client.post(
                "/events/evt-100/items/item-a/regenerate",
                json={"tone": "formal", "focus": "support"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["generated"] is True
        assert data["draft"]["id"] == "d-gen"
        assert data["draft"]["content"] == "AI-generated comment about rezoning."

    def test_regenerate_passes_tone_and_focus_to_prompt(self, client):
        mock_openai = self._mock_openai("Some response")
        storage = _make_storage()
        with (
            patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage),
            patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS),
            patch("openai.OpenAI", return_value=mock_openai),
        ):
            resp = client.post(
                "/events/evt-100/items/item-a/regenerate",
                json={"tone": "passionate", "focus": "question"}
            )
        assert resp.status_code == 200
        call_args = mock_openai.chat.completions.create.call_args
        prompt_text = call_args[1]["messages"][0]["content"]
        assert "passionate" in prompt_text
        assert "question" in prompt_text

    def test_regenerate_defaults_tone_and_focus(self, client):
        mock_openai = self._mock_openai("Default response")
        storage = _make_storage()
        with (
            patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage),
            patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS),
            patch("openai.OpenAI", return_value=mock_openai),
        ):
            resp = client.post(
                "/events/evt-100/items/item-a/regenerate",
                json={}
            )
        assert resp.status_code == 200
        call_args = mock_openai.chat.completions.create.call_args
        prompt_text = call_args[1]["messages"][0]["content"]
        assert "formal" in prompt_text
        assert "concern" in prompt_text

    def test_regenerate_includes_event_and_item_in_prompt(self, client):
        mock_openai = self._mock_openai("Response")
        storage = _make_storage()
        with (
            patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage),
            patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS),
            patch("openai.OpenAI", return_value=mock_openai),
        ):
            resp = client.post("/events/evt-100/items/item-a/regenerate", json={})
        assert resp.status_code == 200
        prompt_text = mock_openai.chat.completions.create.call_args[1]["messages"][0]["content"]
        assert "City Council Regular Meeting" in prompt_text
        assert "Housing Rezoning" in prompt_text
        assert "Rezone parcel for housing" in prompt_text

    def test_event_not_found_returns_404(self, client):
        with patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS):
            resp = client.post("/events/nonexistent/items/item-a/regenerate", json={})
        assert resp.status_code == 404
        assert "Event not found: nonexistent" in resp.json()["detail"]

    def test_item_not_found_returns_404(self, client):
        with patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS):
            resp = client.post("/events/evt-100/items/nonexistent/regenerate", json={})
        assert resp.status_code == 404
        assert "Item not found: nonexistent" in resp.json()["detail"]

    def test_openai_failure_returns_503(self, client):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = RuntimeError("API quota exceeded")
        with (
            patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS),
            patch("openai.OpenAI", return_value=mock_openai),
        ):
            resp = client.post("/events/evt-100/items/item-a/regenerate", json={})
        assert resp.status_code == 503
        assert "Comment generation failed" in resp.json()["detail"]
        assert "API quota exceeded" in resp.json()["detail"]

    def test_regenerate_without_storage_returns_content_unsaved(self, client):
        mock_openai = self._mock_openai("Unsaved comment text")
        with (
            patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None),
            patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS),
            patch("openai.OpenAI", return_value=mock_openai),
        ):
            resp = client.post("/events/evt-100/items/item-a/regenerate", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["generated"] is True
        assert data["content"] == "Unsaved comment text"
        assert "not saved" in data["note"]

    def test_event_with_empty_agenda_items_item_not_found(self, client):
        with patch("civicos_services.servers.routers.events.load_all_events", return_value=SAMPLE_EVENTS):
            resp = client.post("/events/evt-200/items/item-a/regenerate", json={})
        assert resp.status_code == 404
        assert "Item not found: item-a" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /drafts/{draft_id}
# ---------------------------------------------------------------------------

class TestGetDraft:
    def test_returns_draft_by_id(self, client):
        storage = _make_storage(get_draft=SAMPLE_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/drafts/d-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "d-1"
        assert data["content"] == "I support the housing plan."
        assert data["event_id"] == "evt-100"

    def test_not_found_returns_404(self, client):
        storage = _make_storage(get_draft=None)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/drafts/nonexistent")
        assert resp.status_code == 404
        assert "Draft not found: nonexistent" in resp.json()["detail"]

    def test_other_users_draft_returns_403(self, client):
        storage = _make_storage(get_draft=OTHER_USER_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.get("/drafts/d-99")
        assert resp.status_code == 403
        assert "Not authorized to view this draft" in resp.json()["detail"]

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.get("/drafts/d-1")
        assert resp.status_code == 503
        assert "Draft storage not available" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PUT /drafts/{draft_id}
# ---------------------------------------------------------------------------

class TestUpdateDraft:
    def test_updates_draft_content(self, client):
        updated = {**SAMPLE_DRAFT, "content": "Revised comment."}
        storage = _make_storage(get_draft=SAMPLE_DRAFT, update_draft=updated)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.put("/drafts/d-1", json={"content": "Revised comment."})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["draft"]["content"] == "Revised comment."

    def test_passes_content_to_storage(self, client):
        storage = _make_storage(get_draft=SAMPLE_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            client.put("/drafts/d-1", json={"content": "New text"})
        storage.update_draft.assert_called_once_with("d-1", content="New text")

    def test_not_found_returns_404(self, client):
        storage = _make_storage(get_draft=None)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.put("/drafts/nonexistent", json={"content": "x"})
        assert resp.status_code == 404
        assert "Draft not found: nonexistent" in resp.json()["detail"]

    def test_other_users_draft_returns_403(self, client):
        storage = _make_storage(get_draft=OTHER_USER_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.put("/drafts/d-99", json={"content": "hijack"})
        assert resp.status_code == 403
        assert "Not authorized to update this draft" in resp.json()["detail"]

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.put("/drafts/d-1", json={"content": "x"})
        assert resp.status_code == 503

    def test_missing_content_returns_422(self, client):
        storage = _make_storage(get_draft=SAMPLE_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.put("/drafts/d-1", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /drafts/{draft_id}
# ---------------------------------------------------------------------------

class TestDeleteDraft:
    def test_deletes_owned_draft(self, client):
        storage = _make_storage(get_draft=SAMPLE_DRAFT, delete_draft=True)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.delete("/drafts/d-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "Draft deleted"

    def test_delete_failure_returns_success_false(self, client):
        storage = _make_storage(get_draft=SAMPLE_DRAFT, delete_draft=False)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.delete("/drafts/d-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["message"] == "Failed to delete"

    def test_not_found_returns_404(self, client):
        storage = _make_storage(get_draft=None)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.delete("/drafts/nonexistent")
        assert resp.status_code == 404
        assert "Draft not found: nonexistent" in resp.json()["detail"]

    def test_other_users_draft_returns_403(self, client):
        storage = _make_storage(get_draft=OTHER_USER_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.delete("/drafts/d-99")
        assert resp.status_code == 403
        assert "Not authorized to delete this draft" in resp.json()["detail"]

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.delete("/drafts/d-1")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /drafts/{draft_id}/submit
# ---------------------------------------------------------------------------

class TestSubmitDraft:
    def test_marks_draft_as_submitted(self, client):
        submitted = {**SAMPLE_DRAFT, "status": "submitted", "submitted_at": "2026-03-02T09:00:00Z"}
        storage = _make_storage(get_draft=SAMPLE_DRAFT, mark_submitted=submitted)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post("/drafts/d-1/submit")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["draft"]["status"] == "submitted"
        assert data["draft"]["submitted_at"] == "2026-03-02T09:00:00Z"

    def test_calls_mark_submitted_with_draft_id(self, client):
        storage = _make_storage(get_draft=SAMPLE_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            client.post("/drafts/d-1/submit")
        storage.mark_submitted.assert_called_once_with("d-1")

    def test_not_found_returns_404(self, client):
        storage = _make_storage(get_draft=None)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post("/drafts/nonexistent/submit")
        assert resp.status_code == 404
        assert "Draft not found: nonexistent" in resp.json()["detail"]

    def test_other_users_draft_returns_403(self, client):
        storage = _make_storage(get_draft=OTHER_USER_DRAFT)
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=storage):
            resp = client.post("/drafts/d-99/submit")
        assert resp.status_code == 403
        assert "Not authorized to submit this draft" in resp.json()["detail"]

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.drafts.get_draft_storage", return_value=None):
            resp = client.post("/drafts/d-1/submit")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestPydanticModels:
    def test_draft_model_required_fields(self):
        from civicos_services.servers.routers.drafts import Draft
        d = Draft(
            id="d-1", user_id="u-1", event_id="evt-1",
            content="test", status="draft", created_at="2026-01-01"
        )
        assert d.id == "d-1"
        assert d.status == "draft"
        assert d.updated_at is None
        assert d.submitted_at is None
        assert d.item_id is None

    def test_draft_model_with_optional_fields(self):
        from civicos_services.servers.routers.drafts import Draft
        d = Draft(
            id="d-1", user_id="u-1", event_id="evt-1",
            content="test", status="submitted", created_at="2026-01-01",
            updated_at="2026-01-02", submitted_at="2026-01-02",
            event_title="Council", item_id="i-1", item_title="Housing"
        )
        assert d.updated_at == "2026-01-02"
        assert d.submitted_at == "2026-01-02"
        assert d.event_title == "Council"
        assert d.item_id == "i-1"
        assert d.item_title == "Housing"

    def test_create_draft_request_defaults(self):
        from civicos_services.servers.routers.drafts import CreateDraftRequest
        req = CreateDraftRequest(content="My comment")
        assert req.content == "My comment"
        assert req.item_id is None

    def test_regenerate_request_defaults(self):
        from civicos_services.servers.routers.drafts import RegenerateRequest
        req = RegenerateRequest()
        assert req.tone is None
        assert req.focus is None

    def test_regenerate_request_with_values(self):
        from civicos_services.servers.routers.drafts import RegenerateRequest
        req = RegenerateRequest(tone="passionate", focus="support")
        assert req.tone == "passionate"
        assert req.focus == "support"
