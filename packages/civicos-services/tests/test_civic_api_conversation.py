"""Tests for civic_api_conversation.py — Flask-based civic conversation API.

Covers the auth decorator, health check, conversation endpoint (profile creation,
context persistence, service dispatch, error handling), MCP tools listing, civic
events loader (filesystem I/O), user profile GET/PUT, conversation context lookup,
and the 404 error handler.

The subject under test (Flask routes, require_auth, module-level dicts) is never
mocked. External dependencies (conversation_service, filesystem via Path) are mocked
at the boundary. The conversation_service object is stubbed before module import
because the source file's own relative imports (``from .utils.conversation_service``)
point at a non-existent path — this is a known import-layout quirk of the module.

To run:
    pytest packages/civicos-services/tests/test_civic_api_conversation.py -q --override-ini="addopts="
"""

import json
import sys
import types
from pathlib import Path as _RealPath
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub the two imports that civic_api_conversation.py expects before loading it.
# The module does `from .utils.conversation_service import conversation_service`
# and `from .civic_schema_adapter import CivicSchemaAdapter`, but neither exists
# under `civicos_services.chat`. Pre-populating sys.modules lets the import resolve
# via the normal relative-import path, so we exercise the real module top-to-bottom.
# ---------------------------------------------------------------------------

_STUB_CONVERSATION_SERVICE = MagicMock(name="stub_conversation_service")
_STUB_CONVERSATION_SERVICE.enable_mcp = True
_STUB_CONVERSATION_SERVICE.civic_opportunities = []


def _install_stub_modules() -> None:
    utils_pkg_name = "civicos_services.chat.utils"
    conv_mod_name = "civicos_services.chat.utils.conversation_service"
    adapter_mod_name = "civicos_services.chat.civic_schema_adapter"

    if utils_pkg_name not in sys.modules:
        stub_utils_pkg = types.ModuleType(utils_pkg_name)
        stub_utils_pkg.__path__ = []  # mark as a package
        sys.modules[utils_pkg_name] = stub_utils_pkg

    if conv_mod_name not in sys.modules:
        stub_conv_mod = types.ModuleType(conv_mod_name)
        stub_conv_mod.conversation_service = _STUB_CONVERSATION_SERVICE
        sys.modules[conv_mod_name] = stub_conv_mod

    if adapter_mod_name not in sys.modules:
        stub_adapter_mod = types.ModuleType(adapter_mod_name)

        class _StubAdapter:
            def __init__(self):
                pass

        stub_adapter_mod.CivicSchemaAdapter = _StubAdapter
        sys.modules[adapter_mod_name] = stub_adapter_mod


_install_stub_modules()

from civicos_services.chat import civic_api_conversation as cac  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WEB_KEY = "test-web-key-2024"
DEMO_KEY = "demo-key-2024"
AUTH_HEADERS = {"Authorization": f"Bearer {WEB_KEY}"}


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level state and API keys before and after every test."""
    cac.user_profiles.clear()
    cac.conversation_contexts.clear()
    cac.API_KEYS = {"web": WEB_KEY, "demo": DEMO_KEY}
    # Fresh mock for each test so call history doesn't bleed across tests.
    cac.conversation_service.reset_mock()
    cac.conversation_service.enable_mcp = True
    cac.conversation_service.civic_opportunities = []
    cac.conversation_service.handle_conversation.side_effect = None
    cac.conversation_service.handle_conversation.return_value = {
        "message": {"id": "msg-1", "content": "hello"},
        "actions": [],
        "conversation_context": {},
    }
    yield
    cac.user_profiles.clear()
    cac.conversation_contexts.clear()


@pytest.fixture
def client():
    cac.app.config["TESTING"] = True
    return cac.app.test_client()


# ---------------------------------------------------------------------------
# require_auth decorator
# ---------------------------------------------------------------------------


class TestRequireAuth:
    def test_missing_authorization_header_returns_401_with_error_message(self, client):
        resp = client.post("/api/conversation", json={"message": "hi"})
        assert resp.status_code == 401
        assert resp.get_json() == {"error": "No authorization header"}

    def test_non_bearer_authorization_returns_401_invalid_format(self, client):
        resp = client.post(
            "/api/conversation",
            json={"message": "hi"},
            headers={"Authorization": "Basic abcdef"},
        )
        assert resp.status_code == 401
        assert resp.get_json() == {"error": "Invalid authorization format"}

    def test_bearer_with_unknown_token_returns_401_invalid_api_key(self, client):
        resp = client.post(
            "/api/conversation",
            json={"message": "hi"},
            headers={"Authorization": "Bearer not-a-real-key"},
        )
        assert resp.status_code == 401
        assert resp.get_json() == {"error": "Invalid API key"}

    def test_valid_web_api_key_allows_request_through(self, client):
        resp = client.post(
            "/api/conversation",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {WEB_KEY}"},
        )
        assert resp.status_code == 200

    def test_valid_demo_api_key_allows_request_through(self, client):
        resp = client.post(
            "/api/conversation",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {DEMO_KEY}"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_returns_200_and_healthy_status(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "healthy"

    def test_health_reports_service_name(self, client):
        body = client.get("/api/health").get_json()
        assert body["service"] == "civic-conversation-api"

    def test_health_reflects_mcp_enabled_true(self, client):
        cac.conversation_service.enable_mcp = True
        body = client.get("/api/health").get_json()
        assert body["mcp_enabled"] is True

    def test_health_reflects_mcp_enabled_false(self, client):
        cac.conversation_service.enable_mcp = False
        body = client.get("/api/health").get_json()
        assert body["mcp_enabled"] is False

    def test_health_includes_iso_timestamp(self, client):
        body = client.get("/api/health").get_json()
        # ISO format from datetime.now().isoformat() includes "T"
        assert "T" in body["timestamp"]
        assert body["timestamp"][:4].isdigit()  # year prefix

    def test_health_does_not_require_auth(self, client):
        # No Authorization header — should still work.
        resp = client.get("/api/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/conversation
# ---------------------------------------------------------------------------


class TestConversationEndpoint:
    def test_requires_auth(self, client):
        resp = client.post("/api/conversation", json={"message": "hi"})
        assert resp.status_code == 401

    def test_empty_json_body_returns_400_message_required(self, client):
        # `not data` branch: empty dict is falsy.
        resp = client.post(
            "/api/conversation",
            json={},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "Message required"}

    def test_missing_message_key_returns_400(self, client):
        resp = client.post(
            "/api/conversation",
            json={"user_id": "u-1"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "Message required"}

    def test_creates_new_user_profile_with_defaults(self, client):
        client.post(
            "/api/conversation",
            json={"message": "hi", "user_id": "alice"},
            headers=AUTH_HEADERS,
        )
        profile = cac.user_profiles["alice"]
        assert profile["id"] == "alice"
        assert profile["experience_level"] == "new"
        assert profile["location"]["city"] == "San Rafael"
        assert profile["location"]["state"] == "California"
        assert profile["location"]["county"] == "Marin County"
        assert profile["civic_profile"]["interests"] == []
        assert profile["civic_profile"]["impact_score"] == 0
        assert profile["civic_profile"]["visits"] == 1
        assert profile["civic_profile"]["interactions"] == 0

    def test_new_profile_uses_supplied_location_fields(self, client):
        client.post(
            "/api/conversation",
            json={
                "message": "hi",
                "user_id": "bob",
                "city": "Oakland",
                "state": "California",
                "county": "Alameda County",
                "email": "bob@example.com",
                "interests": ["housing", "transit"],
            },
            headers=AUTH_HEADERS,
        )
        profile = cac.user_profiles["bob"]
        assert profile["location"]["city"] == "Oakland"
        assert profile["location"]["county"] == "Alameda County"
        assert profile["email"] == "bob@example.com"
        assert profile["civic_profile"]["interests"] == ["housing", "transit"]

    def test_reuses_existing_user_profile_without_overwriting(self, client):
        cac.user_profiles["carol"] = {
            "id": "carol",
            "experience_level": "experienced",
            "email": "carol@example.com",
            "civic_profile": {"interests": ["climate"], "visits": 7},
            "location": {"city": "Berkeley"},
        }
        client.post(
            "/api/conversation",
            json={"message": "hi", "user_id": "carol", "city": "Novato"},
            headers=AUTH_HEADERS,
        )
        profile = cac.user_profiles["carol"]
        # The existing profile must not be replaced with a fresh "new" record.
        assert profile["experience_level"] == "experienced"
        assert profile["location"]["city"] == "Berkeley"
        assert profile["civic_profile"]["visits"] == 7

    def test_generates_uuid_when_conversation_id_missing(self, client):
        resp = client.post(
            "/api/conversation",
            json={"message": "hi", "user_id": "u-1"},
            headers=AUTH_HEADERS,
        )
        body = resp.get_json()
        assert isinstance(body["conversation_id"], str)
        # uuid4 hex form is 36 chars with 4 dashes.
        assert len(body["conversation_id"]) == 36
        assert body["conversation_id"].count("-") == 4

    def test_preserves_supplied_conversation_id(self, client):
        resp = client.post(
            "/api/conversation",
            json={
                "message": "hi",
                "user_id": "u-1",
                "conversation_id": "conv-xyz-123",
            },
            headers=AUTH_HEADERS,
        )
        assert resp.get_json()["conversation_id"] == "conv-xyz-123"

    def test_returns_message_from_conversation_service(self, client):
        cac.conversation_service.handle_conversation.return_value = {
            "message": {"id": "m-7", "content": "Sure, here is info on housing."},
            "actions": [],
            "conversation_context": {},
        }
        resp = client.post(
            "/api/conversation",
            json={"message": "housing", "user_id": "u-1"},
            headers=AUTH_HEADERS,
        )
        body = resp.get_json()
        assert body["message"]["id"] == "m-7"
        assert body["message"]["content"] == "Sure, here is info on housing."

    def test_returns_actions_from_conversation_service(self, client):
        cac.conversation_service.handle_conversation.return_value = {
            "message": {"id": "m-1", "content": "ok"},
            "actions": [
                {"type": "compose_comment", "label": "Write comment"},
                {"type": "view_meeting", "label": "See meeting"},
            ],
            "conversation_context": {},
        }
        resp = client.post(
            "/api/conversation",
            json={"message": "housing"},
            headers=AUTH_HEADERS,
        )
        actions = resp.get_json()["actions"]
        assert len(actions) == 2
        assert actions[0]["type"] == "compose_comment"
        assert actions[1]["label"] == "See meeting"

    def test_defaults_actions_to_empty_list_when_service_omits_them(self, client):
        cac.conversation_service.handle_conversation.return_value = {
            "message": {"id": "m-1", "content": "ok"},
            "conversation_context": {},
        }
        body = client.post(
            "/api/conversation",
            json={"message": "hi"},
            headers=AUTH_HEADERS,
        ).get_json()
        assert body["actions"] == []

    def test_defaults_conversation_context_to_empty_dict_when_service_omits(self, client):
        cac.conversation_service.handle_conversation.return_value = {
            "message": {"id": "m-1", "content": "ok"},
            # No conversation_context key.
        }
        client.post(
            "/api/conversation",
            json={"message": "hi", "conversation_id": "conv-a"},
            headers=AUTH_HEADERS,
        )
        assert cac.conversation_contexts["conv-a"] == {}

    def test_stores_conversation_context_for_later_retrieval(self, client):
        cac.conversation_service.handle_conversation.return_value = {
            "message": {"id": "m-1", "content": "ok"},
            "actions": [],
            "conversation_context": {"topic": "housing", "turn": 3},
        }
        client.post(
            "/api/conversation",
            json={"message": "hi", "conversation_id": "conv-b"},
            headers=AUTH_HEADERS,
        )
        assert cac.conversation_contexts["conv-b"] == {"topic": "housing", "turn": 3}

    def test_passes_prior_conversation_context_to_service(self, client):
        cac.conversation_contexts["conv-c"] = {"topic": "budget", "turn": 2}
        client.post(
            "/api/conversation",
            json={"message": "more", "conversation_id": "conv-c", "user_id": "u-1"},
            headers=AUTH_HEADERS,
        )
        call_kwargs = cac.conversation_service.handle_conversation.call_args.kwargs
        assert call_kwargs["user_message"] == "more"
        assert call_kwargs["conversation_context"] == {"topic": "budget", "turn": 2}
        assert call_kwargs["user_profile"]["id"] == "u-1"

    def test_user_experience_defaults_to_new_for_new_profile(self, client):
        body = client.post(
            "/api/conversation",
            json={"message": "hi", "user_id": "u-new"},
            headers=AUTH_HEADERS,
        ).get_json()
        assert body["user_experience"] == "new"

    def test_user_experience_reflects_existing_profile(self, client):
        cac.user_profiles["u-old"] = {
            "id": "u-old",
            "experience_level": "experienced",
        }
        body = client.post(
            "/api/conversation",
            json={"message": "hi", "user_id": "u-old"},
            headers=AUTH_HEADERS,
        ).get_json()
        assert body["user_experience"] == "experienced"

    def test_service_exception_returns_500_with_details(self, client):
        cac.conversation_service.handle_conversation.side_effect = RuntimeError(
            "boom-kapow"
        )
        resp = client.post(
            "/api/conversation",
            json={"message": "hi"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["error"] == "Failed to process conversation"
        assert body["details"] == "boom-kapow"


# ---------------------------------------------------------------------------
# /api/mcp-tools
# ---------------------------------------------------------------------------


class TestMcpTools:
    def test_requires_auth(self, client):
        resp = client.get("/api/mcp-tools")
        assert resp.status_code == 401

    def test_returns_exactly_two_tools(self, client):
        body = client.get("/api/mcp-tools", headers=AUTH_HEADERS).get_json()
        assert len(body["tools"]) == 2

    def test_first_tool_is_compose_public_comment(self, client):
        body = client.get("/api/mcp-tools", headers=AUTH_HEADERS).get_json()
        first = body["tools"][0]
        assert first["name"] == "compose_public_comment"
        assert "AI-powered public comments" in first["description"]
        assert first["parameters"]["item_id"] == "string"
        assert first["parameters"]["item_title"] == "string"

    def test_second_tool_is_get_comment_guidelines(self, client):
        body = client.get("/api/mcp-tools", headers=AUTH_HEADERS).get_json()
        second = body["tools"][1]
        assert second["name"] == "get_comment_guidelines"
        assert "submission guidelines" in second["description"]
        assert second["parameters"]["jurisdiction"] == "string (default: san-rafael)"

    def test_enabled_flag_reflects_conversation_service_true(self, client):
        cac.conversation_service.enable_mcp = True
        body = client.get("/api/mcp-tools", headers=AUTH_HEADERS).get_json()
        assert body["enabled"] is True

    def test_enabled_flag_reflects_conversation_service_false(self, client):
        cac.conversation_service.enable_mcp = False
        body = client.get("/api/mcp-tools", headers=AUTH_HEADERS).get_json()
        assert body["enabled"] is False


# ---------------------------------------------------------------------------
# /api/civic-events
# ---------------------------------------------------------------------------


def _patch_schema_dir(monkeypatch, schema_dir):
    """Redirect ``Path(__file__).parent / "output" / "schema"`` to schema_dir."""

    class _Step:
        def __init__(self, remaining):
            self._remaining = remaining

        def __truediv__(self, other):
            if self._remaining <= 1:
                return schema_dir
            return _Step(self._remaining - 1)

    class _Source:
        @property
        def parent(self):
            return _Step(2)

    def _fake_path_ctor(arg):
        # Only intercept the specific Path(__file__) call in the route.
        if arg == cac.__file__:
            return _Source()
        return _RealPath(arg)

    monkeypatch.setattr(cac, "Path", _fake_path_ctor)


class TestCivicEvents:
    def test_requires_auth(self, client):
        resp = client.get("/api/civic-events")
        assert resp.status_code == 401

    def test_returns_empty_list_when_schema_dir_missing(
        self, client, tmp_path, monkeypatch
    ):
        missing = tmp_path / "does-not-exist"
        _patch_schema_dir(monkeypatch, missing)
        resp = client.get("/api/civic-events", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["events"] == []
        assert body["count"] == 0

    def test_loads_opportunities_from_single_file(self, client, tmp_path, monkeypatch):
        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        (schema_dir / "alpha.json").write_text(
            json.dumps(
                {
                    "civic_opportunities": [
                        {"id": "opp-1", "title": "Housing Element"},
                        {"id": "opp-2", "title": "Climate Plan"},
                    ]
                }
            )
        )
        _patch_schema_dir(monkeypatch, schema_dir)

        body = client.get("/api/civic-events", headers=AUTH_HEADERS).get_json()
        assert body["count"] == 2
        assert body["events"][0]["id"] == "opp-1"
        assert body["events"][0]["title"] == "Housing Element"
        assert body["events"][1]["id"] == "opp-2"

    def test_aggregates_opportunities_across_multiple_files(
        self, client, tmp_path, monkeypatch
    ):
        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        (schema_dir / "a.json").write_text(
            json.dumps({"civic_opportunities": [{"id": "a1"}]})
        )
        (schema_dir / "b.json").write_text(
            json.dumps({"civic_opportunities": [{"id": "b1"}, {"id": "b2"}]})
        )
        _patch_schema_dir(monkeypatch, schema_dir)

        body = client.get("/api/civic-events", headers=AUTH_HEADERS).get_json()
        assert body["count"] == 3
        ids = sorted(e["id"] for e in body["events"])
        assert ids == ["a1", "b1", "b2"]

    def test_ignores_files_without_civic_opportunities_key(
        self, client, tmp_path, monkeypatch
    ):
        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        (schema_dir / "with.json").write_text(
            json.dumps({"civic_opportunities": [{"id": "x"}]})
        )
        (schema_dir / "without.json").write_text(json.dumps({"other_key": [1, 2, 3]}))
        _patch_schema_dir(monkeypatch, schema_dir)

        body = client.get("/api/civic-events", headers=AUTH_HEADERS).get_json()
        assert body["count"] == 1
        assert body["events"][0]["id"] == "x"

    def test_count_field_matches_events_length(self, client, tmp_path, monkeypatch):
        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        (schema_dir / "a.json").write_text(
            json.dumps(
                {
                    "civic_opportunities": [
                        {"id": f"opp-{i}"} for i in range(5)
                    ]
                }
            )
        )
        _patch_schema_dir(monkeypatch, schema_dir)

        body = client.get("/api/civic-events", headers=AUTH_HEADERS).get_json()
        assert body["count"] == len(body["events"])
        assert body["count"] == 5

    def test_response_includes_iso_timestamp(self, client, tmp_path, monkeypatch):
        _patch_schema_dir(monkeypatch, tmp_path / "nope")
        body = client.get("/api/civic-events", headers=AUTH_HEADERS).get_json()
        assert "T" in body["timestamp"]
        assert body["timestamp"][:4].isdigit()


# ---------------------------------------------------------------------------
# /api/user-profile
# ---------------------------------------------------------------------------


class TestUserProfile:
    def test_requires_auth(self, client):
        resp = client.get("/api/user-profile?user_id=x")
        assert resp.status_code == 401

    def test_get_without_user_id_returns_400(self, client):
        resp = client.get("/api/user-profile", headers=AUTH_HEADERS)
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "user_id required"}

    def test_get_unknown_user_returns_404(self, client):
        resp = client.get("/api/user-profile?user_id=ghost", headers=AUTH_HEADERS)
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "User not found"}

    def test_get_returns_stored_profile_verbatim(self, client):
        cac.user_profiles["alice"] = {
            "id": "alice",
            "email": "alice@example.com",
            "experience_level": "experienced",
            "civic_profile": {"visits": 12},
        }
        resp = client.get("/api/user-profile?user_id=alice", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == "alice"
        assert body["email"] == "alice@example.com"
        assert body["experience_level"] == "experienced"
        assert body["civic_profile"]["visits"] == 12

    def test_put_creates_new_profile_when_absent(self, client):
        resp = client.put(
            "/api/user-profile?user_id=newbie",
            json={"email": "new@example.com", "experience_level": "new"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        profile = cac.user_profiles["newbie"]
        assert profile["id"] == "newbie"
        assert profile["email"] == "new@example.com"
        assert profile["experience_level"] == "new"
        assert "created_at" in profile

    def test_put_updates_whitelisted_fields_on_existing_profile(self, client):
        cac.user_profiles["alice"] = {
            "id": "alice",
            "email": "old@example.com",
            "experience_level": "new",
            "location": {"city": "San Rafael"},
            "civic_profile": {"visits": 1},
        }
        client.put(
            "/api/user-profile?user_id=alice",
            json={
                "email": "new@example.com",
                "experience_level": "experienced",
                "location": {"city": "Oakland"},
                "civic_profile": {"visits": 10},
            },
            headers=AUTH_HEADERS,
        )
        profile = cac.user_profiles["alice"]
        assert profile["email"] == "new@example.com"
        assert profile["experience_level"] == "experienced"
        assert profile["location"]["city"] == "Oakland"
        assert profile["civic_profile"]["visits"] == 10

    def test_put_ignores_fields_outside_whitelist(self, client):
        cac.user_profiles["alice"] = {
            "id": "alice",
            "email": "alice@example.com",
        }
        client.put(
            "/api/user-profile?user_id=alice",
            json={"email": "new@example.com", "is_admin": True, "secret": "shh"},
            headers=AUTH_HEADERS,
        )
        profile = cac.user_profiles["alice"]
        assert profile["email"] == "new@example.com"
        assert "is_admin" not in profile
        assert "secret" not in profile

    def test_put_refreshes_last_active_timestamp(self, client):
        cac.user_profiles["alice"] = {
            "id": "alice",
            "last_active": "2020-01-01T00:00:00",
        }
        client.put(
            "/api/user-profile?user_id=alice",
            json={"email": "a@b.c"},
            headers=AUTH_HEADERS,
        )
        profile = cac.user_profiles["alice"]
        assert profile["last_active"] != "2020-01-01T00:00:00"
        # New timestamp must be ISO-formatted and from this century.
        assert "T" in profile["last_active"]
        assert profile["last_active"].startswith("20")

    def test_put_returns_updated_profile_in_response_body(self, client):
        resp = client.put(
            "/api/user-profile?user_id=alice",
            json={"email": "alice@example.com"},
            headers=AUTH_HEADERS,
        )
        body = resp.get_json()
        assert body["id"] == "alice"
        assert body["email"] == "alice@example.com"

    def test_put_without_user_id_returns_400(self, client):
        resp = client.put(
            "/api/user-profile",
            json={"email": "x@y.z"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "user_id required"}


# ---------------------------------------------------------------------------
# /api/conversation-context
# ---------------------------------------------------------------------------


class TestConversationContext:
    def test_requires_auth(self, client):
        resp = client.get("/api/conversation-context?conversation_id=c-1")
        assert resp.status_code == 401

    def test_missing_conversation_id_returns_400(self, client):
        resp = client.get("/api/conversation-context", headers=AUTH_HEADERS)
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "conversation_id required"}

    def test_unknown_conversation_id_returns_404(self, client):
        resp = client.get(
            "/api/conversation-context?conversation_id=ghost",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "Conversation not found"}

    def test_known_conversation_id_returns_stored_context(self, client):
        cac.conversation_contexts["conv-7"] = {
            "topic": "transportation",
            "turn": 4,
            "last_action": "search",
        }
        resp = client.get(
            "/api/conversation-context?conversation_id=conv-7",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["topic"] == "transportation"
        assert body["turn"] == 4
        assert body["last_action"] == "search"


# ---------------------------------------------------------------------------
# 404 error handler
# ---------------------------------------------------------------------------


class TestErrorHandlers:
    def test_unknown_endpoint_returns_json_404(self, client):
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "Endpoint not found"}
