"""
Tests for conversations router: AI conversations, chat routing, and research queries.

Mocks external dependencies (ConversationStore, LLM providers, ChatRouter, auth)
while exercising all logic in the router endpoints.

To run:
    pytest packages/civicos-services/tests/test_conversations.py -q --override-ini="addopts="
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Stub out civicos_relay and its submodules to avoid coincurve dependency.
# The conversations router does not use relay at all — the __init__.py
# re-exports the coordination router which chains relay → coincurve.
_relay_coord = ModuleType("civicos_relay.server.coordination")
_relay_coord.router = MagicMock()  # type: ignore[attr-defined]
_relay_server = ModuleType("civicos_relay.server")
_relay_server.coordination = _relay_coord  # type: ignore[attr-defined]
_relay_stub = ModuleType("civicos_relay")
_relay_stub.server = _relay_server  # type: ignore[attr-defined]

_stubs = {
    "civicos_relay": _relay_stub,
    "civicos_relay.server": _relay_server,
    "civicos_relay.server.coordination": _relay_coord,
    "civicos_relay.voice": ModuleType("civicos_relay.voice"),
    "civicos_relay.voice.models": ModuleType("civicos_relay.voice.models"),
    "civicos_relay.voice.service": ModuleType("civicos_relay.voice.service"),
    "civicos_relay.voice.crypto": ModuleType("civicos_relay.voice.crypto"),
}
for name, mod in _stubs.items():
    if name not in sys.modules:
        sys.modules[name] = mod

from civicos_services.servers.routers.conversations import (
    router,
    CONVERSATIONS,
    ConversationMessage,
    ConversationRequest,
    ConversationResponse,
    ChatRouteRequest,
    ChatRouteResponse,
    ChatActionUsage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a FastAPI app with the conversations router."""
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


@pytest.fixture(autouse=True)
def clear_in_memory_conversations():
    """Clear in-memory conversation store between tests."""
    CONVERSATIONS.clear()
    yield
    CONVERSATIONS.clear()


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------

class TestConversationMessage:
    def test_fields(self):
        msg = ConversationMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_role(self):
        msg = ConversationMessage(role="system", content="You are helpful")
        assert msg.role == "system"
        assert msg.content == "You are helpful"


class TestConversationRequest:
    def test_required_fields_only(self):
        req = ConversationRequest(message="What meetings are coming up?")
        assert req.message == "What meetings are coming up?"
        assert req.conversation_id is None
        assert req.history is None
        assert req.context is None

    def test_all_fields(self):
        req = ConversationRequest(
            message="Follow up",
            conversation_id="conv-123",
            history=[ConversationMessage(role="user", content="Hi")],
            context={"jurisdiction": "city-san-rafael"},
        )
        assert req.conversation_id == "conv-123"
        assert len(req.history) == 1
        assert req.history[0].role == "user"
        assert req.history[0].content == "Hi"
        assert req.context["jurisdiction"] == "city-san-rafael"


class TestChatRouteRequest:
    def test_defaults(self):
        req = ChatRouteRequest(message="Show me meetings")
        assert req.message == "Show me meetings"
        assert req.mode == "navigation"
        assert req.conversation_id is None
        assert req.context is None
        assert req.serialized_context is None
        assert req.model_override is None
        assert req.user_context is None

    def test_mode_override(self):
        req = ChatRouteRequest(message="Compare housing", mode="compare")
        assert req.mode == "compare"

    def test_user_context(self):
        req = ChatRouteRequest(
            message="test",
            user_context={"zip": "94901", "interests": ["housing"]},
        )
        assert req.user_context["zip"] == "94901"
        assert "housing" in req.user_context["interests"]


class TestChatActionUsage:
    def test_defaults(self):
        usage = ChatActionUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_with_values(self):
        usage = ChatActionUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


class TestChatRouteResponse:
    def test_required_fields(self):
        resp = ChatRouteResponse(action="respond", conversation_id="c-1")
        assert resp.action == "respond"
        assert resp.conversation_id == "c-1"
        assert resp.mode_changed is False
        assert resp.multi_operation is False
        assert resp.parameters is None
        assert resp.message is None
        assert resp.mcp_result is None
        assert resp.mcp_tool is None
        assert resp.personalization_reasoning is None
        assert resp.usage is None
        assert resp.error is None

    def test_all_fields(self):
        resp = ChatRouteResponse(
            action="search_events",
            parameters={"query": "housing"},
            message="Found 3 meetings",
            reasoning="User asked about housing meetings",
            conversation_id="c-2",
            mode="focus",
            mode_changed=True,
            mode_reason="Deep dive detected",
            multi_operation=True,
            operation_count=2,
            all_operations=[{"action": "search_events"}, {"action": "view_legislative_context"}],
            mcp_result="MCP output here",
            mcp_tool="search_agenda_packets",
            personalization_reasoning="Based on your 94901 zip code",
            provider_used="openai",
            model_used="gpt-4o",
            usage=ChatActionUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            error=None,
        )
        assert resp.action == "search_events"
        assert resp.parameters["query"] == "housing"
        assert resp.mode == "focus"
        assert resp.mode_changed is True
        assert resp.mode_reason == "Deep dive detected"
        assert resp.multi_operation is True
        assert resp.operation_count == 2
        assert len(resp.all_operations) == 2
        assert resp.mcp_result == "MCP output here"
        assert resp.mcp_tool == "search_agenda_packets"
        assert resp.personalization_reasoning == "Based on your 94901 zip code"
        assert resp.provider_used == "openai"
        assert resp.model_used == "gpt-4o"
        assert resp.usage.total_tokens == 300


# ---------------------------------------------------------------------------
# POST /conversation — handle_conversation
# ---------------------------------------------------------------------------

class TestHandleConversation:
    def test_returns_response_with_provider(self, client):
        """Provider available: uses provider.chat() and returns response."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "The next council meeting is Tuesday."

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={"message": "When is the next meeting?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "The next council meeting is Tuesday."
        assert len(data["conversation_id"]) == 36  # UUID format
        assert data["sources"] == []
        assert data["suggestions"] == []

    def test_preserves_provided_conversation_id(self, client):
        """When conversation_id is provided, it's echoed back."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Response"

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={
                "message": "Hello",
                "conversation_id": "conv-existing-123",
            })

        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "conv-existing-123"

    def test_uses_history_from_request(self, client):
        """When history is provided, it's used instead of store/memory."""
        captured_messages = []
        mock_provider = MagicMock()

        def capture_chat(msgs, **kwargs):
            captured_messages.extend(list(msgs))
            return "Follow-up response"

        mock_provider.chat.side_effect = capture_chat

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={
                "message": "And what about parks?",
                "history": [
                    {"role": "user", "content": "Tell me about housing"},
                    {"role": "assistant", "content": "Housing is important"},
                ],
            })

        assert resp.status_code == 200
        assert resp.json()["response"] == "Follow-up response"
        # Verify provider received 2 history + 1 new user message at call time
        assert len(captured_messages) == 3
        assert captured_messages[0]["role"] == "user"
        assert captured_messages[0]["content"] == "Tell me about housing"
        assert captured_messages[2]["role"] == "user"
        assert captured_messages[2]["content"] == "And what about parks?"

    def test_loads_history_from_store(self, client):
        """When store is available and no history provided, loads from store."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Stored context response"

        mock_store = MagicMock()
        mock_store.get_conversation.return_value = [
            {"role": "user", "content": "Prior message"},
        ]

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=mock_store),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={
                "message": "Continue",
                "conversation_id": "conv-existing",
            })

        assert resp.status_code == 200
        assert resp.json()["response"] == "Stored context response"
        mock_store.get_conversation.assert_called_once_with("conv-existing")

    def test_falls_back_to_in_memory_storage(self, client):
        """When no store and no history, uses in-memory CONVERSATIONS dict."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Memory response"

        # Pre-populate in-memory store
        CONVERSATIONS["conv-mem"] = [{"role": "user", "content": "Earlier"}]

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={
                "message": "Follow up",
                "conversation_id": "conv-mem",
            })

        assert resp.status_code == 200
        # Verify the in-memory history was used
        call_messages = mock_provider.chat.call_args[0][0]
        assert call_messages[0]["content"] == "Earlier"
        assert call_messages[1]["content"] == "Follow up"

    def test_saves_conversation_to_store(self, client):
        """After response, saves full message history to store."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Saved response"
        mock_store = MagicMock()
        mock_store.get_conversation.return_value = []

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=mock_store),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={"message": "Save this"})

        assert resp.status_code == 200
        # Verify save was called with messages including both user + assistant
        save_call = mock_store.save_conversation.call_args
        saved_messages = save_call[0][1]
        assert len(saved_messages) == 2
        assert saved_messages[0] == {"role": "user", "content": "Save this"}
        assert saved_messages[1] == {"role": "assistant", "content": "Saved response"}
        # user_id is the auth token
        assert save_call[1]["user_id"] == "user-42"

    def test_saves_to_in_memory_when_no_store(self, client):
        """Without store, saves to in-memory CONVERSATIONS dict."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "In-memory saved"

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={
                "message": "Store me",
                "conversation_id": "conv-inmem",
            })

        assert resp.status_code == 200
        assert "conv-inmem" in CONVERSATIONS
        assert len(CONVERSATIONS["conv-inmem"]) == 2
        assert CONVERSATIONS["conv-inmem"][0]["content"] == "Store me"
        assert CONVERSATIONS["conv-inmem"][1]["content"] == "In-memory saved"

    def test_openai_fallback_when_no_provider(self, client):
        """When LLM provider unavailable, falls back to direct OpenAI call."""
        mock_openai_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OpenAI fallback response"
        mock_openai_client.chat.completions.create.return_value = mock_response

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=None),
            patch("openai.OpenAI", return_value=mock_openai_client),
        ):
            resp = client.post("/conversation", json={"message": "Fallback test"})

        assert resp.status_code == 200
        assert resp.json()["response"] == "OpenAI fallback response"
        # Verify system message was included
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args[1]["model"] == "gpt-4o-mini"
        messages = call_args[1]["messages"]
        assert messages[0]["role"] == "system"
        assert "civic engagement assistant" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Fallback test"

    def test_openai_fallback_includes_system_prompt_keywords(self, client):
        """The system prompt in OpenAI fallback mentions key civic topics."""
        mock_openai_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_openai_client.chat.completions.create.return_value = mock_response

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=None),
            patch("openai.OpenAI", return_value=mock_openai_client),
        ):
            resp = client.post("/conversation", json={"message": "test"})

        assert resp.status_code == 200
        system_content = mock_openai_client.chat.completions.create.call_args[1]["messages"][0]["content"]
        assert "legislation" in system_content
        assert "local democracy" in system_content

    def test_returns_503_when_openai_fails(self, client):
        """When both provider and OpenAI fail, returns 503."""
        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=None),
            patch("openai.OpenAI", side_effect=RuntimeError("No API key")),
        ):
            resp = client.post("/conversation", json={"message": "test"})

        assert resp.status_code == 503
        assert "LLM not available" in resp.json()["detail"]
        assert "No API key" in resp.json()["detail"]

    def test_passes_context_to_provider(self, client):
        """Request context is forwarded to provider.chat()."""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Context-aware response"

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={
                "message": "What about housing?",
                "context": {"jurisdiction": "city-san-rafael"},
            })

        assert resp.status_code == 200
        call_kwargs = mock_provider.chat.call_args[1]
        assert call_kwargs["context"] == {"jurisdiction": "city-san-rafael"}

    def test_server_error_returns_500(self, client):
        """Unexpected exceptions return 500 with error detail."""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = ValueError("Unexpected error in chat")

        with (
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
            patch("civicos_services.servers.routers.conversations.get_llm_provider", return_value=mock_provider),
        ):
            resp = client.post("/conversation", json={"message": "trigger error"})

        assert resp.status_code == 500
        assert "Unexpected error in chat" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /chat/route — route_chat
# ---------------------------------------------------------------------------

class TestRouteChatWithRouter:
    """Tests for chat routing when ChatRouter is available."""

    def _mock_chat_router(self, result):
        """Create a mock ChatRouter that returns the given result dict."""
        mock = MagicMock()
        mock.route_message.return_value = result
        return mock

    def test_routes_message_and_returns_action(self, client):
        chat_router = self._mock_chat_router({
            "action": "search_events",
            "parameters": {"query": "housing"},
            "message": "Found 3 upcoming meetings about housing",
            "reasoning": "User asked about housing meetings",
            "mode": "navigation",
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "Show me housing meetings"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "search_events"
        assert data["parameters"]["query"] == "housing"
        assert data["message"] == "Found 3 upcoming meetings about housing"
        assert data["reasoning"] == "User asked about housing meetings"
        assert data["mode"] == "navigation"

    def test_preserves_conversation_id(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={
                "message": "Hello",
                "conversation_id": "conv-specific-id",
            })

        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "conv-specific-id"

    def test_generates_conversation_id_when_missing(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "Hello"})

        assert resp.status_code == 200
        assert len(resp.json()["conversation_id"]) == 36  # UUID

    def test_passes_mode_to_router(self, client):
        chat_router = self._mock_chat_router({"action": "respond", "mode": "compare"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "Compare A vs B", "mode": "compare"})

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["mode"] == "compare"

    def test_defaults_mode_to_navigation(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "Hello"})

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["mode"] == "navigation"

    def test_passes_serialized_context(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={
                "message": "test",
                "serialized_context": "Open artifact: budget chart",
            })

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["serialized_context"] == "Open artifact: budget chart"

    def test_defaults_serialized_context_to_empty_string(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["serialized_context"] == ""

    def test_passes_user_context(self, client):
        chat_router = self._mock_chat_router({"action": "respond", "personalization_reasoning": "Based on 94901"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={
                "message": "test",
                "user_context": {"zip": "94901"},
            })

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["user_context"] == {"zip": "94901"}
        assert resp.json()["personalization_reasoning"] == "Based on 94901"

    def test_passes_model_override(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={
                "message": "test",
                "model_override": "gpt-4o",
            })

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["model_override"] == "gpt-4o"

    def test_mode_change_fields(self, client):
        chat_router = self._mock_chat_router({
            "action": "search_events",
            "mode": "focus",
            "mode_changed": True,
            "mode_reason": "Deep dive detected",
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "Tell me everything about housing"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "focus"
        assert data["mode_changed"] is True
        assert data["mode_reason"] == "Deep dive detected"

    def test_multi_operation_fields(self, client):
        chat_router = self._mock_chat_router({
            "action": "search_events",
            "multi_operation": True,
            "operation_count": 2,
            "all_operations": [
                {"action": "search_events", "parameters": {"query": "parks"}},
                {"action": "view_legislative_context", "parameters": {"query": "parks"}},
            ],
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "parks meetings or laws"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["multi_operation"] is True
        assert data["operation_count"] == 2
        assert len(data["all_operations"]) == 2
        assert data["all_operations"][0]["action"] == "search_events"
        assert data["all_operations"][1]["action"] == "view_legislative_context"

    def test_mcp_result_fields(self, client):
        chat_router = self._mock_chat_router({
            "action": "respond",
            "mcp_result": "Found 3 agenda items about housing",
            "mcp_tool": "search_agenda_packets",
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "search agendas for housing"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["mcp_result"] == "Found 3 agenda items about housing"
        assert data["mcp_tool"] == "search_agenda_packets"

    def test_usage_field_parsing(self, client):
        chat_router = self._mock_chat_router({
            "action": "respond",
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 75,
                "total_tokens": 225,
            },
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["prompt_tokens"] == 150
        assert data["usage"]["completion_tokens"] == 75
        assert data["usage"]["total_tokens"] == 225

    def test_usage_defaults_missing_fields_to_zero(self, client):
        chat_router = self._mock_chat_router({
            "action": "respond",
            "usage": {"prompt_tokens": 50},  # missing completion_tokens and total_tokens
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["prompt_tokens"] == 50
        assert data["usage"]["completion_tokens"] == 0
        assert data["usage"]["total_tokens"] == 0

    def test_no_usage_field_when_absent(self, client):
        chat_router = self._mock_chat_router({"action": "respond"})

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 200
        assert resp.json()["usage"] is None

    def test_loads_conversation_history_from_store(self, client):
        """When store and conversation_id exist, loads history for router."""
        chat_router = self._mock_chat_router({"action": "respond"})
        mock_store = MagicMock()
        mock_store.get_conversation.return_value = [
            {"role": "user", "content": "Prior message"},
        ]

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=mock_store),
        ):
            resp = client.post("/chat/route", json={
                "message": "Follow up",
                "conversation_id": "conv-hist",
            })

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["conversation_history"] == [{"role": "user", "content": "Prior message"}]

    def test_no_history_when_no_conversation_id(self, client):
        """Without conversation_id, conversation_history is None."""
        chat_router = self._mock_chat_router({"action": "respond"})
        mock_store = MagicMock()

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=mock_store),
        ):
            resp = client.post("/chat/route", json={"message": "New conversation"})

        assert resp.status_code == 200
        call_kwargs = chat_router.route_message.call_args[1]
        assert call_kwargs["conversation_history"] is None
        mock_store.get_conversation.assert_not_called()

    def test_provider_metadata_fields(self, client):
        chat_router = self._mock_chat_router({
            "action": "respond",
            "provider_used": "anthropic",
            "model_used": "claude-3-opus",
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 200
        assert resp.json()["provider_used"] == "anthropic"
        assert resp.json()["model_used"] == "claude-3-opus"

    def test_error_field_from_router(self, client):
        chat_router = self._mock_chat_router({
            "action": "respond",
            "error": "Rate limit exceeded",
        })

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 200
        assert resp.json()["error"] == "Rate limit exceeded"

    def test_router_exception_returns_500(self, client):
        chat_router = MagicMock()
        chat_router.route_message.side_effect = RuntimeError("Router crashed")

        with (
            patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=chat_router),
            patch("civicos_services.servers.routers.conversations.get_conversation_store", return_value=None),
        ):
            resp = client.post("/chat/route", json={"message": "test"})

        assert resp.status_code == 500
        assert "Router crashed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /chat/route — Fallback (no ChatRouter)
# ---------------------------------------------------------------------------

class TestRouteChatFallback:
    """Tests for keyword-based fallback routing when ChatRouter is unavailable."""

    def test_meeting_keyword_routes_to_search_events(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "When is the next meeting?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "search_events"
        assert data["mode_changed"] is False

    def test_event_keyword_routes_to_search_events(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Show me upcoming events"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "search_events"

    def test_agenda_keyword_routes_to_search_events(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "What's on the agenda?"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "search_events"

    def test_council_keyword_routes_to_search_events(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "council session"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "search_events"

    def test_issue_keyword_routes_to_file_complaint(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "I have an issue with a pothole"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "file_complaint"

    def test_problem_keyword_routes_to_file_complaint(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "There's a problem with the sidewalk"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "file_complaint"

    def test_complaint_keyword_routes_to_file_complaint(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "I want to file a complaint"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "file_complaint"

    def test_broken_keyword_routes_to_file_complaint(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "The streetlight is broken"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "file_complaint"

    def test_fix_keyword_routes_to_file_complaint(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Please fix the road"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "file_complaint"

    def test_law_keyword_routes_to_legislative(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "What law applies to this?"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "view_legislative_context"

    def test_bill_keyword_routes_to_legislative(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Tell me about this bill"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "view_legislative_context"

    def test_legislation_keyword_routes_to_legislative(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Find related legislation"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "view_legislative_context"

    def test_vote_keyword_routes_to_legislative(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "How did they vote?"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "view_legislative_context"

    def test_election_keyword_routes_to_legislative(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "When is the election?"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "view_legislative_context"

    def test_unmatched_message_defaults_to_respond(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Hello, how are you?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "respond"
        assert data["message"] == "Chat router not available. Please try again later."

    def test_respond_action_has_unavailable_message(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Random words"})

        assert resp.status_code == 200
        assert resp.json()["message"] == "Chat router not available. Please try again later."

    def test_non_respond_action_has_no_message(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "upcoming meeting"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "search_events"
        assert resp.json()["message"] is None

    def test_fallback_uses_provided_mode(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={
                "message": "Hello",
                "mode": "focus",
            })

        assert resp.status_code == 200
        assert resp.json()["mode"] == "focus"

    def test_fallback_defaults_mode_to_navigation(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Hello"})

        assert resp.status_code == 200
        assert resp.json()["mode"] == "navigation"

    def test_fallback_returns_empty_parameters(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "When is the meeting?"})

        assert resp.status_code == 200
        assert resp.json()["parameters"] == {}

    def test_case_insensitive_keyword_matching(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "MEETING AGENDA"})

        assert resp.status_code == 200
        assert resp.json()["action"] == "search_events"

    def test_fallback_generates_conversation_id(self, client):
        with patch("civicos_services.servers.routers.conversations.get_chat_router", return_value=None):
            resp = client.post("/chat/route", json={"message": "Hello"})

        assert resp.status_code == 200
        assert len(resp.json()["conversation_id"]) == 36  # UUID


# ---------------------------------------------------------------------------
# POST /research — handle_research_query
# ---------------------------------------------------------------------------

class TestResearchEndpoint:
    def test_returns_research_result(self, client):
        mock_service = MagicMock()
        mock_service.research.return_value = {
            "answer": "San Rafael was incorporated in 1874.",
            "confidence": 0.95,
        }
        mock_cls = MagicMock(return_value=mock_service)

        with patch(
            "civicos_services.storage.research_service.ResearchService",
            mock_cls,
        ):
            resp = client.post("/research", json={"query": "When was San Rafael incorporated?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["query"] == "When was San Rafael incorporated?"
        assert data["result"]["answer"] == "San Rafael was incorporated in 1874."
        assert data["result"]["confidence"] == 0.95

    def test_passes_context_to_service(self, client):
        mock_service = MagicMock()
        mock_service.research.return_value = {"answer": "Yes"}
        mock_cls = MagicMock(return_value=mock_service)

        with patch(
            "civicos_services.storage.research_service.ResearchService",
            mock_cls,
        ):
            resp = client.post("/research", json={
                "query": "What is the budget?",
                "context": {"jurisdiction": "city-san-rafael"},
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_service.research.assert_called_once_with(
            "What is the budget?",
            context={"jurisdiction": "city-san-rafael"},
        )

    def test_missing_query_returns_400(self, client):
        resp = client.post("/research", json={"context": {"foo": "bar"}})
        assert resp.status_code == 400
        assert "Query is required" in resp.json()["detail"]

    def test_empty_query_returns_400(self, client):
        resp = client.post("/research", json={"query": ""})
        assert resp.status_code == 400
        assert "Query is required" in resp.json()["detail"]

    def test_no_query_key_returns_400(self, client):
        resp = client.post("/research", json={})
        assert resp.status_code == 400
        assert "Query is required" in resp.json()["detail"]

    def test_research_service_unavailable_returns_503(self, client):
        with patch.dict(
            "sys.modules",
            {"civicos_services.storage.research_service": None},
        ):
            resp = client.post("/research", json={"query": "test"})

        assert resp.status_code == 503
        assert "Research service not available" in resp.json()["detail"]

    def test_research_service_error_returns_500(self, client):
        mock_service = MagicMock()
        mock_service.research.side_effect = RuntimeError("Database connection failed")
        mock_cls = MagicMock(return_value=mock_service)

        with patch(
            "civicos_services.storage.research_service.ResearchService",
            mock_cls,
        ):
            resp = client.post("/research", json={"query": "test"})

        assert resp.status_code == 500
        assert "Database connection failed" in resp.json()["detail"]

    def test_null_context_is_passed(self, client):
        mock_service = MagicMock()
        mock_service.research.return_value = {"answer": "Result"}
        mock_cls = MagicMock(return_value=mock_service)

        with patch(
            "civicos_services.storage.research_service.ResearchService",
            mock_cls,
        ):
            resp = client.post("/research", json={"query": "test"})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_service.research.assert_called_once_with("test", context=None)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

class TestGetConversationStore:
    def test_returns_none_when_import_fails(self):
        """When ConversationStore module is missing, returns None."""
        from civicos_services.servers.routers.conversations import get_conversation_store
        with patch.dict("sys.modules", {"civicos_services.storage.conversation_store": None}):
            result = get_conversation_store()
        assert result is None


class TestGetChatRouter:
    def test_returns_none_when_import_fails(self):
        """When civic_chat_router module is missing, returns None."""
        from civicos_services.servers.routers.conversations import get_chat_router
        with patch.dict("sys.modules", {"civicos_services.chat.civic_chat_router": None}):
            result = get_chat_router()
        assert result is None
