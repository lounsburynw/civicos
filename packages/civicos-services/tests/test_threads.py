"""
Tests for threads router: listing threads, getting thread info, messages.

Mocks ThreadStorage (external dependency) while exercising all logic in the
router endpoints. Auth is overridden via FastAPI dependency_overrides so
tests run as a fixed user.

To run:
    pytest packages/civicos-services/tests/test_threads.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.threads import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI app with the threads router."""
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
    """Create a mock ThreadStorage with configurable returns."""
    s = MagicMock()
    s.get_user_threads.return_value = overrides.get("user_threads", [])
    s.get_thread.return_value = overrides.get("get_thread", None)
    s.get_thread_participants.return_value = overrides.get("participants", [])
    s.get_messages.return_value = overrides.get("messages", [])
    s.create_message.return_value = overrides.get(
        "create_message",
        {"id": "m-1", "thread_id": "t-1", "user_id": "user-42", "content": "hi",
         "created_at": "2026-04-10T12:00:00Z", "is_system": False},
    )
    return s


SAMPLE_THREAD = {
    "id": "t-1",
    "focal_type": "event",
    "focal_id": "evt-100",
    "title": "Council Meeting Discussion",
    "participant_count": 3,
    "message_count": 7,
    "created_at": "2026-04-01T10:00:00Z",
    "last_message_at": "2026-04-08T14:30:00Z",
}

ISSUE_THREAD = {
    "id": "t-2",
    "focal_type": "issue",
    "focal_id": "iss-500",
    "title": "Pothole on Main St",
    "participant_count": 2,
    "message_count": 4,
    "created_at": "2026-04-02T09:00:00Z",
    "last_message_at": "2026-04-09T11:00:00Z",
}

ANOTHER_EVENT_THREAD = {
    "id": "t-3",
    "focal_type": "event",
    "focal_id": "evt-200",
    "title": "Planning Commission",
    "participant_count": 5,
    "message_count": 12,
    "created_at": "2026-04-03T08:00:00Z",
    "last_message_at": "2026-04-10T10:00:00Z",
}

SAMPLE_MESSAGE = {
    "id": "m-1",
    "thread_id": "t-1",
    "user_id": "user-42",
    "content": "What time does the meeting start?",
    "created_at": "2026-04-08T13:00:00Z",
    "is_system": False,
}


# ---------------------------------------------------------------------------
# GET /threads
# ---------------------------------------------------------------------------

class TestListThreads:
    def test_returns_all_user_threads(self, client):
        storage = _make_storage(user_threads=[SAMPLE_THREAD, ISSUE_THREAD, ANOTHER_EVENT_THREAD])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert len(data["threads"]) == 3
        assert data["threads"][0]["id"] == "t-1"
        assert data["threads"][1]["id"] == "t-2"
        assert data["threads"][2]["id"] == "t-3"

    def test_passes_token_as_user_id_to_storage(self, client):
        storage = _make_storage(user_threads=[])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads")
        assert resp.status_code == 200
        storage.get_user_threads.assert_called_once_with("user-42")

    def test_filter_by_focal_type_event(self, client):
        storage = _make_storage(user_threads=[SAMPLE_THREAD, ISSUE_THREAD, ANOTHER_EVENT_THREAD])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads?focal_type=event")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        returned_ids = [t["id"] for t in data["threads"]]
        assert returned_ids == ["t-1", "t-3"]

    def test_filter_by_focal_type_issue(self, client):
        storage = _make_storage(user_threads=[SAMPLE_THREAD, ISSUE_THREAD, ANOTHER_EVENT_THREAD])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads?focal_type=issue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["threads"][0]["id"] == "t-2"
        assert data["threads"][0]["focal_type"] == "issue"

    def test_filter_by_focal_id(self, client):
        storage = _make_storage(user_threads=[SAMPLE_THREAD, ISSUE_THREAD, ANOTHER_EVENT_THREAD])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads?focal_id=evt-100")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["threads"][0]["id"] == "t-1"

    def test_filter_by_focal_type_and_id_combined(self, client):
        """Both filters applied in sequence."""
        storage = _make_storage(user_threads=[SAMPLE_THREAD, ISSUE_THREAD, ANOTHER_EVENT_THREAD])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads?focal_type=event&focal_id=evt-200")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["threads"][0]["id"] == "t-3"

    def test_filter_no_match_returns_empty_list(self, client):
        storage = _make_storage(user_threads=[SAMPLE_THREAD, ISSUE_THREAD])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads?focal_id=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["threads"] == []

    def test_empty_user_threads(self, client):
        storage = _make_storage(user_threads=[])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["threads"] == []
        assert data["count"] == 0

    def test_storage_unavailable_returns_empty_with_note(self, client):
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=None):
            resp = client.get("/threads")
        assert resp.status_code == 200
        data = resp.json()
        assert data["threads"] == []
        assert data["note"] == "Thread storage not available"
        # 'count' key should not be present in unavailable path
        assert "count" not in data

    def test_storage_exception_returns_500(self, client):
        storage = _make_storage()
        storage.get_user_threads.side_effect = RuntimeError("DB connection lost")
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads")
        assert resp.status_code == 500
        assert "DB connection lost" in resp.json()["detail"]
        assert "Server error" in resp.json()["detail"]

    def test_missing_auth_returns_401(self, app):
        """Without the dependency override, missing Authorization yields 401."""
        with TestClient(app) as c:
            resp = c.get("/threads")
        assert resp.status_code == 401

    def test_filter_ignores_threads_missing_focal_type_key(self, client):
        """Threads without a focal_type key are excluded by the filter."""
        without_type = {"id": "t-x", "focal_id": "evt-100", "created_at": "2026-04-01"}
        storage = _make_storage(user_threads=[SAMPLE_THREAD, without_type])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads?focal_type=event")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["threads"][0]["id"] == "t-1"


# ---------------------------------------------------------------------------
# GET /threads/{thread_id}
# ---------------------------------------------------------------------------

class TestGetThreadInfo:
    def test_returns_thread_with_participants(self, client):
        participants = [
            {"user_id": "user-42", "joined_at": "2026-04-01T10:00:00Z"},
            {"user_id": "user-7", "joined_at": "2026-04-02T11:00:00Z"},
        ]
        storage = _make_storage(get_thread=SAMPLE_THREAD, participants=participants)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread"]["id"] == "t-1"
        assert data["thread"]["title"] == "Council Meeting Discussion"
        assert data["thread"]["focal_type"] == "event"
        assert data["thread"]["participant_count"] == 3
        assert data["thread"]["message_count"] == 7
        assert len(data["participants"]) == 2
        assert data["participants"][0]["user_id"] == "user-42"
        assert data["participants"][1]["user_id"] == "user-7"

    def test_queries_storage_with_thread_id_path_param(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1")
        assert resp.status_code == 200
        storage.get_thread.assert_called_once_with("t-1")
        storage.get_thread_participants.assert_called_once_with("t-1")

    def test_empty_participants_list(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD, participants=[])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread"]["id"] == "t-1"
        assert data["participants"] == []

    def test_thread_not_found_returns_404(self, client):
        storage = _make_storage(get_thread=None)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Thread not found: nonexistent"

    def test_thread_not_found_does_not_query_participants(self, client):
        storage = _make_storage(get_thread=None)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/nonexistent")
        assert resp.status_code == 404
        storage.get_thread_participants.assert_not_called()

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=None):
            resp = client.get("/threads/t-1")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Thread storage not available"

    def test_storage_exception_returns_500(self, client):
        storage = _make_storage()
        storage.get_thread.side_effect = RuntimeError("DB down")
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1")
        assert resp.status_code == 500
        assert "DB down" in resp.json()["detail"]
        assert "Server error" in resp.json()["detail"]

    def test_participants_exception_returns_500(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        storage.get_thread_participants.side_effect = RuntimeError("timeout")
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1")
        assert resp.status_code == 500
        assert "timeout" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /threads/{thread_id}/messages
# ---------------------------------------------------------------------------

class TestGetThreadMessages:
    def test_returns_messages_with_count(self, client):
        msgs = [
            {**SAMPLE_MESSAGE, "id": "m-1", "content": "first"},
            {**SAMPLE_MESSAGE, "id": "m-2", "content": "second"},
            {**SAMPLE_MESSAGE, "id": "m-3", "content": "third"},
        ]
        storage = _make_storage(get_thread=SAMPLE_THREAD, messages=msgs)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "t-1"
        assert data["count"] == 3
        assert len(data["messages"]) == 3
        assert data["messages"][0]["id"] == "m-1"
        assert data["messages"][0]["content"] == "first"
        assert data["messages"][2]["content"] == "third"

    def test_default_limit_is_50_and_before_is_none(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD, messages=[SAMPLE_MESSAGE])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1/messages")
        assert resp.status_code == 200
        storage.get_messages.assert_called_once_with("t-1", limit=50, before=None)

    def test_custom_limit_passed_through(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD, messages=[SAMPLE_MESSAGE])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1/messages?limit=10")
        assert resp.status_code == 200
        storage.get_messages.assert_called_once_with("t-1", limit=10, before=None)

    def test_before_parameter_passed_through(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD, messages=[])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1/messages?before=m-99&limit=25")
        assert resp.status_code == 200
        storage.get_messages.assert_called_once_with("t-1", limit=25, before="m-99")

    def test_empty_messages_returns_zero_count(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD, messages=[])
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "t-1"
        assert data["messages"] == []
        assert data["count"] == 0

    def test_thread_not_found_returns_404(self, client):
        storage = _make_storage(get_thread=None)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/nonexistent/messages")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Thread not found: nonexistent"

    def test_thread_not_found_does_not_query_messages(self, client):
        storage = _make_storage(get_thread=None)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/nonexistent/messages")
        assert resp.status_code == 404
        storage.get_messages.assert_not_called()

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=None):
            resp = client.get("/threads/t-1/messages")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Thread storage not available"

    def test_storage_exception_returns_500(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        storage.get_messages.side_effect = RuntimeError("query failed")
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.get("/threads/t-1/messages")
        assert resp.status_code == 500
        assert "query failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /threads/{thread_id}/messages
# ---------------------------------------------------------------------------

class TestSendMessage:
    def test_creates_message_and_returns_success(self, client):
        created = {
            "id": "m-new",
            "thread_id": "t-1",
            "user_id": "user-42",
            "content": "Hello thread",
            "created_at": "2026-04-10T12:00:00Z",
            "is_system": False,
        }
        storage = _make_storage(get_thread=SAMPLE_THREAD, create_message=created)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/t-1/messages", json={"content": "Hello thread"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"]["id"] == "m-new"
        assert data["message"]["content"] == "Hello thread"
        assert data["message"]["user_id"] == "user-42"
        assert data["message"]["thread_id"] == "t-1"
        assert data["message"]["is_system"] is False

    def test_passes_thread_id_content_and_token_to_storage(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/t-1/messages", json={"content": "test body"})
        assert resp.status_code == 200
        storage.create_message.assert_called_once_with(
            thread_id="t-1",
            user_id="user-42",
            content="test body",
        )

    def test_thread_not_found_returns_404(self, client):
        storage = _make_storage(get_thread=None)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/nonexistent/messages", json={"content": "x"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Thread not found: nonexistent"

    def test_thread_not_found_does_not_create_message(self, client):
        storage = _make_storage(get_thread=None)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/nonexistent/messages", json={"content": "x"})
        assert resp.status_code == 404
        storage.create_message.assert_not_called()

    def test_storage_unavailable_returns_503(self, client):
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=None):
            resp = client.post("/threads/t-1/messages", json={"content": "hi"})
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Thread storage not available"

    def test_missing_content_returns_422(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/t-1/messages", json={})
        assert resp.status_code == 422

    def test_empty_content_still_calls_storage(self, client):
        """Pydantic's str type does not reject empty strings; routing passes it through."""
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/t-1/messages", json={"content": ""})
        assert resp.status_code == 200
        storage.create_message.assert_called_once_with(
            thread_id="t-1",
            user_id="user-42",
            content="",
        )

    def test_create_message_exception_returns_500(self, client):
        storage = _make_storage(get_thread=SAMPLE_THREAD)
        storage.create_message.side_effect = RuntimeError("insert failed")
        with patch("civicos_services.servers.routers.threads.get_thread_storage", return_value=storage):
            resp = client.post("/threads/t-1/messages", json={"content": "hi"})
        assert resp.status_code == 500
        assert "insert failed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# get_thread_storage helper
# ---------------------------------------------------------------------------

class TestGetThreadStorage:
    def test_returns_none_when_thread_storage_module_missing(self):
        """The module is not shipped in the package; import should fail and return None."""
        from civicos_services.servers.routers.threads import get_thread_storage
        result = get_thread_storage()
        # thread_storage module does not exist in civicos_services.storage,
        # so ImportError is caught and None is returned.
        assert result is None


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestPydanticModels:
    def test_thread_model_required_fields(self):
        from civicos_services.servers.routers.threads import Thread
        t = Thread(
            id="t-1", focal_type="event", focal_id="evt-100",
            created_at="2026-04-01T10:00:00Z",
        )
        assert t.id == "t-1"
        assert t.focal_type == "event"
        assert t.focal_id == "evt-100"
        assert t.participant_count == 0
        assert t.message_count == 0
        assert t.title is None
        assert t.last_message_at is None

    def test_thread_model_with_all_fields(self):
        from civicos_services.servers.routers.threads import Thread
        t = Thread(
            id="t-2", focal_type="issue", focal_id="iss-1",
            title="Pothole", participant_count=5, message_count=12,
            created_at="2026-04-01T10:00:00Z",
            last_message_at="2026-04-05T11:00:00Z",
        )
        assert t.title == "Pothole"
        assert t.participant_count == 5
        assert t.message_count == 12
        assert t.last_message_at == "2026-04-05T11:00:00Z"

    def test_message_model_required_fields(self):
        from civicos_services.servers.routers.threads import Message
        m = Message(
            id="m-1", thread_id="t-1", user_id="u-1",
            content="hello", created_at="2026-04-01T10:00:00Z",
        )
        assert m.id == "m-1"
        assert m.thread_id == "t-1"
        assert m.user_id == "u-1"
        assert m.content == "hello"
        assert m.is_system is False

    def test_message_model_is_system_flag(self):
        from civicos_services.servers.routers.threads import Message
        m = Message(
            id="m-2", thread_id="t-1", user_id="system",
            content="User joined", created_at="2026-04-01T10:00:00Z",
            is_system=True,
        )
        assert m.is_system is True
        assert m.user_id == "system"

    def test_send_message_request_content(self):
        from civicos_services.servers.routers.threads import SendMessageRequest
        req = SendMessageRequest(content="Hello thread")
        assert req.content == "Hello thread"

    def test_send_message_request_requires_content(self):
        from civicos_services.servers.routers.threads import SendMessageRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="content"):
            SendMessageRequest()  # type: ignore[call-arg]
