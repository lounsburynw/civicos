"""
Tests for civic_chat_router.py — the chat routing module.

Focuses on pure-logic functions: topic normalization, jurisdiction normalization,
complaint pre-filter, boolean query detection, MCP executor logic, mode parsing,
and the overall route_message dispatch.

LLM calls are mocked at the provider layer. The subject (ChatRouter, normalize_topic,
normalize_jurisdiction, MCPToolExecutor) is never mocked.

To run:
    pytest packages/civicos-services/tests/test_civic_chat_router.py -q --override-ini="addopts="
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# Patch env vars and OpenAI before importing (ChatRouter.__init__ creates OpenAI client)
_ENV_PATCH = {
    "OPENAI_API_KEY": "test-key-fake",
}

with patch.dict(os.environ, _ENV_PATCH):
    with patch("openai.OpenAI"):
        from civicos_services.chat.civic_chat_router import (
            ACTION_TO_MCP_TOOL,
            CIVICOS_FUNCTIONS,
            MODE_SYSTEM_PROMPTS,
            MCPToolExecutor,
            TOPIC_NORMALIZATION,
            VALID_TOPICS,
            ChatRouter,
            ComplaintData,
            Operation,
            QueryPlan,
            SearchFilters,
            get_mcp_executor,
            normalize_jurisdiction,
            normalize_topic,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeToolCall:
    name: str
    arguments: dict


@dataclass
class FakeProviderResponse:
    content: str = ""
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    })


# ---------------------------------------------------------------------------
# normalize_topic — pure logic, no mocks needed
# ---------------------------------------------------------------------------


class TestNormalizeTopic:
    """Tests for normalize_topic() — fuzzy topic string → valid enum."""

    def test_empty_string_returns_all(self):
        assert normalize_topic("") == "all"

    def test_none_returns_all(self):
        assert normalize_topic(None) == "all"

    def test_exact_valid_topic_passes_through(self):
        assert normalize_topic("housing") == "housing"
        assert normalize_topic("transportation") == "transportation"
        assert normalize_topic("budget") == "budget"

    def test_case_insensitive_match(self):
        assert normalize_topic("HOUSING") == "housing"
        assert normalize_topic("Transportation") == "transportation"
        assert normalize_topic("BUDGET") == "budget"

    def test_whitespace_stripped(self):
        assert normalize_topic("  housing  ") == "housing"
        assert normalize_topic("\ttransportation\n") == "transportation"

    def test_exact_normalization_map_housing_variants(self):
        assert normalize_topic("affordable housing") == "housing"
        assert normalize_topic("residential") == "housing"
        assert normalize_topic("zoning") == "housing"
        assert normalize_topic("land use") == "housing"
        assert normalize_topic("land-use") == "housing"

    def test_exact_normalization_map_transportation_variants(self):
        assert normalize_topic("transit") == "transportation"
        assert normalize_topic("public transit") == "transportation"
        assert normalize_topic("traffic") == "transportation"
        assert normalize_topic("parking") == "transportation"

    def test_exact_normalization_map_environment_variants(self):
        assert normalize_topic("climate") == "environment"
        assert normalize_topic("sustainability") == "environment"
        assert normalize_topic("renewable energy") == "environment"

    def test_exact_normalization_map_budget_variants(self):
        assert normalize_topic("finance") == "budget"
        assert normalize_topic("funding") == "budget"
        assert normalize_topic("fiscal") == "budget"
        assert normalize_topic("cdbg") == "budget"

    def test_exact_normalization_map_public_safety_variants(self):
        assert normalize_topic("police") == "public_safety"
        assert normalize_topic("fire") == "public_safety"
        assert normalize_topic("crime") == "public_safety"
        assert normalize_topic("law enforcement") == "public_safety"

    def test_exact_normalization_map_community_variants(self):
        assert normalize_topic("parks") == "community"
        assert normalize_topic("recreation") == "community"
        assert normalize_topic("library") == "community"

    def test_fuzzy_substring_matching(self):
        # "housing development and preservation" contains "housing development"
        assert normalize_topic("housing development and preservation") == "housing"

    def test_unknown_topic_falls_back_to_all(self):
        assert normalize_topic("quantum physics") == "all"
        assert normalize_topic("spaceflight") == "all"

    def test_all_valid_topics_pass_through(self):
        for topic in VALID_TOPICS:
            assert normalize_topic(topic) == topic


# ---------------------------------------------------------------------------
# normalize_jurisdiction — pure logic (with core_normalize mocked)
# ---------------------------------------------------------------------------


class TestNormalizeJurisdiction:
    """Tests for normalize_jurisdiction() — special 'all' handling + core delegate."""

    def test_all_keyword_returns_all(self):
        assert normalize_jurisdiction("all") == "all"

    def test_everywhere_keyword_returns_all(self):
        assert normalize_jurisdiction("everywhere") == "all"

    def test_all_case_insensitive(self):
        assert normalize_jurisdiction("ALL") == "all"
        assert normalize_jurisdiction("Everywhere") == "all"

    def test_delegates_to_core_normalize_with_strict_false(self):
        # core_normalize is imported inside the function body, so patch at the source module
        with patch("civicos._internal.jurisdiction.normalize_jurisdiction", return_value="city-berkeley") as core_mock:
            result = normalize_jurisdiction("berkeley")
            assert result == "city-berkeley"
            core_mock.assert_called_once_with("berkeley", strict=False)


# ---------------------------------------------------------------------------
# MCPToolExecutor
# ---------------------------------------------------------------------------


class TestMCPToolExecutor:
    """Tests for MCPToolExecutor — tool validation, request IDs, response parsing."""

    def test_unknown_tool_returns_error_string(self):
        executor = MCPToolExecutor()
        result = executor.execute("nonexistent_tool", {})
        assert "Error: Unknown MCP tool 'nonexistent_tool'" == result

    def test_sequential_request_ids(self):
        executor = MCPToolExecutor()
        assert executor._next_request_id() == 1
        assert executor._next_request_id() == 2
        assert executor._next_request_id() == 3

    def test_available_tools_property_matches_class_constant(self):
        executor = MCPToolExecutor()
        assert executor.available_tools == MCPToolExecutor.AVAILABLE_TOOLS
        assert "search_meeting_history" in executor.available_tools
        assert "get_upcoming_meetings" in executor.available_tools

    def test_jurisdiction_stored(self):
        executor = MCPToolExecutor(jurisdiction="city-berkeley")
        assert executor._jurisdiction == "city-berkeley"

    @patch("httpx.Client")
    def test_execute_parses_text_content(self, MockClient):
        """Successful MCP response with text content items is concatenated."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {"type": "text", "text": "## Meeting Results"},
                    {"type": "text", "text": "Found 3 meetings"},
                ]
            },
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        executor = MCPToolExecutor()
        result = executor.execute("search_meeting_history", {"query": "housing"})

        assert "Meeting Results" in result
        assert "Found 3 meetings" in result

    @patch("httpx.Client")
    def test_execute_non_200_returns_error(self, MockClient):
        """Non-200 HTTP status returns error string with status code."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.post.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        executor = MCPToolExecutor()
        result = executor.execute("search_meeting_history", {"query": "test"})
        assert "Error: MCP server returned status 500" == result

    @patch("httpx.Client")
    def test_execute_jsonrpc_error_returns_message(self, MockClient):
        """JSON-RPC error in response body returns error message."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        executor = MCPToolExecutor()
        result = executor.execute("search_meeting_history", {"query": "test"})
        assert "Error: Method not found" == result

    @patch("httpx.Client")
    def test_execute_empty_content_falls_through_to_json_dump(self, MockClient):
        """Empty content array is falsy, so falls through to json.dumps(result)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"content": []},
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        executor = MCPToolExecutor()
        result = executor.execute("search_meeting_history", {})
        # Empty content list is falsy → falls through to json.dumps
        parsed = json.loads(result)
        assert parsed == {"content": []}

    @patch("httpx.Client")
    def test_execute_string_result_hits_generic_exception(self, MockClient):
        """String result triggers AttributeError on .get() → caught by generic handler."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": "plain string result",
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        executor = MCPToolExecutor()
        result = executor.execute("search_meeting_history", {})
        # String result causes .get() AttributeError → caught by generic except
        assert result.startswith("Error executing search_meeting_history:")
        assert "has no attribute 'get'" in result

    @patch("httpx.Client")
    def test_execute_non_text_content_items_filtered(self, MockClient):
        """Only 'text' type content items are included in output."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {"type": "text", "text": "Relevant text"},
                    {"type": "image", "data": "base64..."},
                    {"type": "text", "text": "More text"},
                ]
            },
            "id": 1,
        }
        mock_client.post.return_value = mock_response
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        executor = MCPToolExecutor()
        result = executor.execute("search_meeting_history", {})
        assert "Relevant text" in result
        assert "More text" in result
        assert "base64" not in result

    def test_execute_connect_error_returns_unavailable_message(self):
        """ConnectError returns user-friendly message about MCP server."""
        import httpx

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            executor = MCPToolExecutor()
            result = executor.execute("search_meeting_history", {})
            assert "Error: MCP server unavailable" in result
            assert "Start with:" in result

    def test_execute_timeout_returns_timeout_message(self):
        """TimeoutException returns timeout-specific error."""
        import httpx

        with patch("httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            executor = MCPToolExecutor()
            result = executor.execute("search_meeting_history", {})
            assert result == "Error: MCP server request timed out"


# ---------------------------------------------------------------------------
# get_mcp_executor — singleton factory
# ---------------------------------------------------------------------------


class TestGetMcpExecutor:
    """Tests for get_mcp_executor() — jurisdiction-keyed singletons."""

    def test_returns_same_instance_for_same_jurisdiction(self):
        # Clear the cache first
        import civicos_services.chat.civic_chat_router as mod
        mod._mcp_executors = {}

        e1 = get_mcp_executor("city-test")
        e2 = get_mcp_executor("city-test")
        assert e1 is e2

    def test_returns_different_instances_for_different_jurisdictions(self):
        import civicos_services.chat.civic_chat_router as mod
        mod._mcp_executors = {}

        e1 = get_mcp_executor("city-alpha")
        e2 = get_mcp_executor("city-beta")
        assert e1 is not e2
        assert e1._jurisdiction == "city-alpha"
        assert e2._jurisdiction == "city-beta"


# ---------------------------------------------------------------------------
# ACTION_TO_MCP_TOOL mapping
# ---------------------------------------------------------------------------


class TestActionToMcpToolMapping:
    """Verify the action→MCP tool mapping is correct."""

    def test_search_events_maps_to_search_meeting_history(self):
        assert ACTION_TO_MCP_TOOL["search_events"] == "search_meeting_history"

    def test_view_legislative_maps_to_regulatory_stack(self):
        assert ACTION_TO_MCP_TOOL["view_legislative_context"] == "search_regulatory_stack"

    def test_draft_comment_maps_to_comment_template(self):
        assert ACTION_TO_MCP_TOOL["draft_comment"] == "get_comment_template"

    def test_file_complaint_not_in_mapping(self):
        assert "file_complaint" not in ACTION_TO_MCP_TOOL

    def test_respond_not_in_mapping(self):
        assert "respond" not in ACTION_TO_MCP_TOOL


# ---------------------------------------------------------------------------
# Pydantic Models — pure validation
# ---------------------------------------------------------------------------


class TestSearchFilters:
    """Tests for SearchFilters Pydantic model."""

    def test_all_fields_optional(self):
        f = SearchFilters()
        assert f.jurisdiction is None
        assert f.topic is None
        assert f.date_range is None
        assert f.query is None
        assert f.level is None

    def test_level_enum_validation(self):
        f = SearchFilters(level="state")
        assert f.level == "state"
        f = SearchFilters(level="federal")
        assert f.level == "federal"
        f = SearchFilters(level="both")
        assert f.level == "both"

    def test_model_dump_excludes_none(self):
        f = SearchFilters(topic="housing", jurisdiction="city-berkeley")
        dumped = f.model_dump(exclude_none=True)
        assert dumped == {"topic": "housing", "jurisdiction": "city-berkeley"}
        assert "date_range" not in dumped


class TestComplaintData:
    """Tests for ComplaintData Pydantic model."""

    def test_all_fields_optional(self):
        c = ComplaintData()
        assert c.title is None
        assert c.description is None
        assert c.address is None
        assert c.category is None

    def test_populated_fields(self):
        c = ComplaintData(
            title="Pothole",
            description="Large pothole on Main St",
            address="123 Main St",
            category="infrastructure",
        )
        assert c.title == "Pothole"
        assert c.category == "infrastructure"


class TestOperation:
    """Tests for Operation Pydantic model."""

    def test_search_events_operation(self):
        op = Operation(
            type="search_events",
            filters=SearchFilters(topic="housing"),
        )
        assert op.type == "search_events"
        assert op.filters.topic == "housing"
        assert op.complaint_data is None

    def test_respond_operation_with_message(self):
        op = Operation(type="respond", message="Hello there")
        assert op.type == "respond"
        assert op.message == "Hello there"

    def test_file_complaint_operation(self):
        op = Operation(
            type="file_complaint",
            complaint_data=ComplaintData(title="Broken sidewalk"),
        )
        assert op.type == "file_complaint"
        assert op.complaint_data.title == "Broken sidewalk"


class TestQueryPlanModel:
    """Tests for QueryPlan Pydantic model."""

    def test_single_operation(self):
        plan = QueryPlan(operations=[
            Operation(type="search_events", filters=SearchFilters(topic="housing")),
        ])
        assert len(plan.operations) == 1

    def test_multiple_operations_for_or_query(self):
        plan = QueryPlan(operations=[
            Operation(type="search_events", filters=SearchFilters(topic="housing")),
            Operation(type="search_events", filters=SearchFilters(topic="transportation")),
        ])
        assert len(plan.operations) == 2
        assert plan.operations[0].filters.topic == "housing"
        assert plan.operations[1].filters.topic == "transportation"

    def test_max_five_operations(self):
        ops = [Operation(type="respond", message=f"msg {i}") for i in range(5)]
        plan = QueryPlan(operations=ops)
        assert len(plan.operations) == 5

    def test_empty_operations_rejected(self):
        with pytest.raises(Exception):
            QueryPlan(operations=[])


# ---------------------------------------------------------------------------
# MODE_SYSTEM_PROMPTS constants
# ---------------------------------------------------------------------------


class TestModeSystemPrompts:
    """Verify system prompt configuration."""

    def test_all_three_modes_have_prompts(self):
        assert "navigation" in MODE_SYSTEM_PROMPTS
        assert "focus" in MODE_SYSTEM_PROMPTS
        assert "compare" in MODE_SYSTEM_PROMPTS

    def test_navigation_prompt_mentions_search(self):
        assert "search" in MODE_SYSTEM_PROMPTS["navigation"].lower()

    def test_focus_prompt_mentions_explain(self):
        prompt = MODE_SYSTEM_PROMPTS["focus"].lower()
        assert "explain" in prompt or "understanding" in prompt

    def test_compare_prompt_mentions_analyze(self):
        prompt = MODE_SYSTEM_PROMPTS["compare"].lower()
        assert "analyze" in prompt or "compare" in prompt


# ---------------------------------------------------------------------------
# CIVICOS_FUNCTIONS — function schema definitions
# ---------------------------------------------------------------------------


class TestCivicosFunctions:
    """Verify the function definitions are well-formed."""

    def test_function_names(self):
        names = {f["name"] for f in CIVICOS_FUNCTIONS}
        assert "search_events" in names
        assert "file_complaint" in names
        assert "view_legislative_context" in names
        assert "search_web" in names
        assert "draft_comment" in names
        assert "view_my_complaints" in names
        assert "explain_event" in names

    def test_search_events_has_topic_enum(self):
        search_fn = next(f for f in CIVICOS_FUNCTIONS if f["name"] == "search_events")
        topic_prop = search_fn["parameters"]["properties"]["topic"]
        assert "enum" in topic_prop
        assert "housing" in topic_prop["enum"]
        assert "transportation" in topic_prop["enum"]

    def test_file_complaint_has_no_required_fields(self):
        complaint_fn = next(f for f in CIVICOS_FUNCTIONS if f["name"] == "file_complaint")
        assert complaint_fn["parameters"]["required"] == []


# ---------------------------------------------------------------------------
# ChatRouter.detect_mode — LLM call mocked at provider layer
# ---------------------------------------------------------------------------


class TestDetectMode:
    """Tests for ChatRouter.detect_mode() — parsing LLM classification responses."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_navigation_mode_parsed_from_hyphen_format(self, router):
        fake_response = FakeProviderResponse(content="navigation - searching for housing meetings")
        with patch("civicos_services.chat.civic_chat_router.get_provider_for_task") as mock_gpt:
            mock_provider = MagicMock()
            mock_provider.complete.return_value = fake_response
            mock_provider.default_model = "test-model"
            mock_provider.name = "test"
            mock_gpt.return_value = mock_provider

            mode, reason = router.detect_mode("find housing meetings", "focus", "")
            assert mode == "navigation"
            assert "housing" in reason.lower()

    def test_focus_mode_parsed(self, router):
        fake_response = FakeProviderResponse(content="focus - definition question about CDBG")
        with patch("civicos_services.chat.civic_chat_router.get_provider_for_task") as mock_gpt:
            mock_provider = MagicMock()
            mock_provider.complete.return_value = fake_response
            mock_provider.default_model = "test-model"
            mock_provider.name = "test"
            mock_gpt.return_value = mock_provider

            mode, reason = router.detect_mode("what is CDBG?", "navigation", "")
            assert mode == "focus"
            assert "CDBG" in reason

    def test_en_dash_separator_handled(self, router):
        """Some models use en dash (–) instead of hyphen (-)."""
        fake_response = FakeProviderResponse(content="compare \u2013 wants to analyze multiple items")
        with patch("civicos_services.chat.civic_chat_router.get_provider_for_task") as mock_gpt:
            mock_provider = MagicMock()
            mock_provider.complete.return_value = fake_response
            mock_provider.default_model = "test-model"
            mock_provider.name = "test"
            mock_gpt.return_value = mock_provider

            mode, reason = router.detect_mode("compare these two", "focus", "")
            assert mode == "compare"
            assert "analyze" in reason.lower()

    def test_invalid_mode_becomes_uncertain(self, router):
        fake_response = FakeProviderResponse(content="discovery - finding content")
        with patch("civicos_services.chat.civic_chat_router.get_provider_for_task") as mock_gpt:
            mock_provider = MagicMock()
            mock_provider.complete.return_value = fake_response
            mock_provider.default_model = "test-model"
            mock_provider.name = "test"
            mock_gpt.return_value = mock_provider

            mode, reason = router.detect_mode("something", "focus", "")
            assert mode == "uncertain"
            assert "Invalid mode" in reason

    def test_provider_error_falls_back_to_current_mode(self, router):
        with patch("civicos_services.chat.civic_chat_router.get_provider_for_task") as mock_gpt:
            mock_provider = MagicMock()
            mock_provider.complete.side_effect = RuntimeError("API down")
            mock_gpt.return_value = mock_provider

            mode, reason = router.detect_mode("test", "focus", "")
            assert mode == "focus"  # Falls back to current_mode
            assert "error" in reason.lower()

    def test_conversation_history_included_in_context(self, router):
        """Conversation history is formatted and passed to the LLM."""
        fake_response = FakeProviderResponse(content="navigation - follow-up query")
        with patch("civicos_services.chat.civic_chat_router.get_provider_for_task") as mock_gpt:
            mock_provider = MagicMock()
            mock_provider.complete.return_value = fake_response
            mock_provider.default_model = "test-model"
            mock_provider.name = "test"
            mock_gpt.return_value = mock_provider

            history = [
                {"role": "user", "content": "show housing meetings"},
                {"role": "assistant", "content": "Found 5 meetings",
                 "function_call": {"name": "search_events", "arguments": '{"topic": "housing"}'}},
            ]
            mode, reason = router.detect_mode("what about Oakland?", "navigation", "", history)
            assert mode == "navigation"

            # Verify the prompt included conversation context
            call_args = mock_provider.complete.call_args
            prompt_content = call_args[1]["messages"][0]["content"]
            assert "search_events" in prompt_content


# ---------------------------------------------------------------------------
# ChatRouter.route_message — filing pre-filter (regex, no LLM)
# ---------------------------------------------------------------------------


class TestRouteMessageFilingPreFilter:
    """Tests for complaint-filing regex pre-filter in route_message()."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def _make_detect_mode_return(self, mode="navigation"):
        """Helper to mock detect_mode consistently."""
        return patch.object(
            ChatRouter, "detect_mode",
            return_value=(mode, f"detected {mode}"),
        )

    def test_report_a_pothole_triggers_file_complaint(self, router):
        with self._make_detect_mode_return():
            result = router.route_message("report a pothole on Main St")
            assert result["action"] == "file_complaint"
            assert result["provider_used"] == "pre-filter"
            assert result["model_used"] == "regex"
            assert "pothole on Main St" in result["parameters"]["title"]

    def test_file_a_complaint_triggers_file_complaint(self, router):
        with self._make_detect_mode_return():
            result = router.route_message("file a complaint about noise")
            assert result["action"] == "file_complaint"
            assert "complaint about noise" in result["parameters"]["title"]

    def test_submit_an_issue_triggers_file_complaint(self, router):
        with self._make_detect_mode_return():
            result = router.route_message("submit an issue about graffiti")
            assert result["action"] == "file_complaint"
            assert "issue about graffiti" in result["parameters"]["title"]

    def test_i_want_to_report_triggers_file_complaint(self, router):
        with self._make_detect_mode_return():
            result = router.route_message("I want to report a broken streetlight")
            assert result["action"] == "file_complaint"

    def test_show_reports_does_not_trigger_filing(self, router):
        """'show' is a search indicator, so filing pre-filter should NOT activate."""
        fake_response = FakeProviderResponse(
            content="Here are the reports",
            tool_calls=[],
        )
        with self._make_detect_mode_return():
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                mock_provider = MagicMock()
                mock_provider.complete.return_value = fake_response
                mock_provider.default_model = "test-model"
                mock_provider.name = "test"
                mock_gmt.return_value = mock_provider
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    result = router.route_message("show reports about potholes")
                    assert result["action"] == "respond"  # NOT file_complaint


# ---------------------------------------------------------------------------
# ChatRouter.route_message — "my complaints" pre-filter
# ---------------------------------------------------------------------------


class TestRouteMessageMyComplaintsPreFilter:
    """Tests for 'my complaints' regex pre-filter forcing view_my_complaints."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_my_issues_forces_view_my_complaints(self, router):
        fake_response = FakeProviderResponse(
            content="",
            tool_calls=[FakeToolCall(name="view_my_complaints", arguments={"ownership": "mine"})],
        )
        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "my complaints")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                mock_provider = MagicMock()
                mock_provider.complete.return_value = fake_response
                mock_provider.default_model = "test-model"
                mock_provider.name = "test"
                mock_gmt.return_value = mock_provider
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    result = router.route_message("show my issues")
                    assert result["action"] == "view_my_complaints"

                    # Verify tool_choice was set to force view_my_complaints
                    call_kwargs = mock_provider.complete.call_args[1]
                    assert call_kwargs["tool_choice"] == {
                        "type": "function",
                        "function": {"name": "view_my_complaints"},
                    }

    def test_issues_im_following_forces_view_my_complaints(self, router):
        fake_response = FakeProviderResponse(
            content="",
            tool_calls=[FakeToolCall(name="view_my_complaints", arguments={"ownership": "following"})],
        )
        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "following")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                mock_provider = MagicMock()
                mock_provider.complete.return_value = fake_response
                mock_provider.default_model = "test-model"
                mock_provider.name = "test"
                mock_gmt.return_value = mock_provider
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    result = router.route_message("issues I'm following")
                    assert result["action"] == "view_my_complaints"


# ---------------------------------------------------------------------------
# ChatRouter.route_message — uncertain mode handling
# ---------------------------------------------------------------------------


class TestRouteMessageUncertainMode:
    """When mode detection returns 'uncertain', router asks user for clarification."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_uncertain_mode_returns_clarification_prompt(self, router):
        with patch.object(ChatRouter, "detect_mode", return_value=("uncertain", "ambiguous query")):
            result = router.route_message("thing", mode="focus")
            assert result["action"] == "respond"
            assert "Search" in result["message"]
            assert "Understand" in result["message"]
            assert "Compare" in result["message"]
            assert result["mode"] == "focus"  # Stays in current mode
            assert result["mode_changed"] is False


# ---------------------------------------------------------------------------
# ChatRouter.route_message — conversational response (no tool calls)
# ---------------------------------------------------------------------------


class TestRouteMessageConversational:
    """When LLM returns no tool calls, router returns a 'respond' action."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_conversational_response_action(self, router):
        fake_response = FakeProviderResponse(
            content="CDBG stands for Community Development Block Grant.",
            tool_calls=[],
        )
        with patch.object(ChatRouter, "detect_mode", return_value=("focus", "definition")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                mock_provider = MagicMock()
                mock_provider.complete.return_value = fake_response
                mock_provider.default_model = "test-model"
                mock_provider.name = "test"
                mock_gmt.return_value = mock_provider
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    result = router.route_message("what is CDBG?", mode="navigation")
                    assert result["action"] == "respond"
                    assert "Community Development Block Grant" in result["message"]
                    assert result["mode"] == "focus"
                    assert result["mode_changed"] is True  # Changed from navigation to focus
                    assert result["provider_used"] == "test"
                    assert result["usage"]["total_tokens"] == 15


# ---------------------------------------------------------------------------
# ChatRouter.route_message — tool call routing with normalization
# ---------------------------------------------------------------------------


class TestRouteMessageToolCallRouting:
    """Tests for function call routing: normalization and response structure."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_search_events_topic_normalized(self, router):
        """Topic 'affordable housing' should be normalized to 'housing'."""
        fake_response = FakeProviderResponse(
            content="Searching for housing meetings",
            tool_calls=[FakeToolCall(
                name="search_events",
                arguments={"topic": "affordable housing", "jurisdiction": "city-san-rafael"},
            )],
        )
        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "search")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                mock_provider = MagicMock()
                mock_provider.complete.return_value = fake_response
                mock_provider.default_model = "test-model"
                mock_provider.name = "test"
                mock_gmt.return_value = mock_provider
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    # Mock MCP executor to avoid HTTP call
                    with patch("civicos_services.chat.civic_chat_router.get_mcp_executor") as mock_mcp:
                        mock_mcp.return_value.execute.return_value = "## Results\n3 meetings found"

                        result = router.route_message("show affordable housing meetings")
                        assert result["action"] == "search_events"
                        assert result["parameters"]["topic"] == "housing"  # Normalized!

    def test_error_handling_returns_fallback_response(self, router):
        """Provider error yields a user-friendly fallback response."""
        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "search")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                mock_provider = MagicMock()
                mock_provider.complete.side_effect = RuntimeError("API quota exceeded")
                mock_provider.name = "test"
                mock_gmt.return_value = mock_provider

                result = router.route_message("find meetings")
                assert result["action"] == "respond"
                assert "error" in result["message"].lower() or "Error" in result.get("error", "")
                assert result["mode"] == "focus"  # Default mode param
                assert result["mode_changed"] is False


# ---------------------------------------------------------------------------
# ChatRouter.route_message — boolean OR/AND query detection
# ---------------------------------------------------------------------------


class TestRouteMessageBooleanQueries:
    """Tests for OR/AND query detection and structured query planning."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_or_query_triggers_structured_planning(self, router):
        """'housing OR transportation' should trigger parse_query_to_plan."""
        multi_plan = QueryPlan(operations=[
            Operation(type="search_events", filters=SearchFilters(topic="housing")),
            Operation(type="search_events", filters=SearchFilters(topic="transportation")),
        ])

        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "OR query")):
            with patch("civicos_services.chat.civic_chat_router.parse_query_to_plan", return_value=multi_plan):
                result = router.route_message("housing OR transportation")
                assert result["action"] == "multi_operation"
                assert result["multi_operation"] is True
                assert result["operation_count"] == 2
                assert len(result["all_operations"]) == 2
                assert result["all_operations"][0]["action"] == "search_events"
                assert result["all_operations"][0]["parameters"]["topic"] == "housing"
                assert result["all_operations"][1]["parameters"]["topic"] == "transportation"

    def test_and_query_detected(self, router):
        """'housing AND transportation' also triggers boolean detection."""
        single_plan = QueryPlan(operations=[
            Operation(type="search_events", filters=SearchFilters(topic="housing")),
        ])

        # Single operation falls through to regular function calling
        fake_response = FakeProviderResponse(
            content="Searching",
            tool_calls=[FakeToolCall(name="search_events", arguments={"topic": "housing"})],
        )

        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "AND query")):
            with patch("civicos_services.chat.civic_chat_router.parse_query_to_plan", return_value=single_plan):
                with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                    mock_provider = MagicMock()
                    mock_provider.complete.return_value = fake_response
                    mock_provider.default_model = "test-model"
                    mock_provider.name = "test"
                    mock_gmt.return_value = mock_provider
                    with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                        with patch("civicos_services.chat.civic_chat_router.get_mcp_executor") as mock_mcp:
                            mock_mcp.return_value.execute.return_value = "results"
                            result = router.route_message("housing AND transportation")
                            # Single operation falls through, not multi_operation
                            assert result["action"] == "search_events"

    def test_comma_query_detected_as_boolean(self, router):
        """'housing, transportation' triggers boolean detection."""
        multi_plan = QueryPlan(operations=[
            Operation(type="search_events", filters=SearchFilters(topic="housing")),
            Operation(type="search_events", filters=SearchFilters(topic="transportation")),
        ])

        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "comma query")):
            with patch("civicos_services.chat.civic_chat_router.parse_query_to_plan", return_value=multi_plan):
                result = router.route_message("housing, transportation")
                assert result["action"] == "multi_operation"
                assert result["operation_count"] == 2

    def test_query_planning_failure_falls_through(self, router):
        """If parse_query_to_plan raises, fall through to regular function calling."""
        fake_response = FakeProviderResponse(
            content="Searching for housing",
            tool_calls=[FakeToolCall(name="search_events", arguments={"topic": "housing"})],
        )

        with patch.object(ChatRouter, "detect_mode", return_value=("navigation", "OR query")):
            with patch("civicos_services.chat.civic_chat_router.parse_query_to_plan", side_effect=Exception("LLM error")):
                with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                    mock_provider = MagicMock()
                    mock_provider.complete.return_value = fake_response
                    mock_provider.default_model = "test-model"
                    mock_provider.name = "test"
                    mock_gmt.return_value = mock_provider
                    with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                        with patch("civicos_services.chat.civic_chat_router.get_mcp_executor") as mock_mcp:
                            mock_mcp.return_value.execute.return_value = "results"
                            result = router.route_message("housing OR transportation")
                            # Falls through to regular function calling
                            assert result["action"] == "search_events"


# ---------------------------------------------------------------------------
# ChatRouter.route_message — web search inline execution
# ---------------------------------------------------------------------------


class TestRouteMessageWebSearch:
    """Tests for inline web search execution when LLM returns search_web tool call."""

    @pytest.fixture
    def router(self):
        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                return ChatRouter()

    def test_search_web_executes_inline_and_returns_respond(self, router):
        # First call: main routing returns search_web tool call
        routing_response = FakeProviderResponse(
            content="",
            tool_calls=[FakeToolCall(name="search_web", arguments={"query": "Berkeley CDBG allocation 2024"})],
        )
        # Second call: search provider returns answer
        search_response = FakeProviderResponse(
            content="Berkeley receives $2.5M in CDBG funding for FY2024.",
        )

        with patch.object(ChatRouter, "detect_mode", return_value=("focus", "factual question")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                # First call returns routing provider, second returns search provider
                routing_provider = MagicMock()
                routing_provider.complete.return_value = routing_response
                routing_provider.default_model = "router-model"
                routing_provider.name = "router"

                search_provider = MagicMock()
                search_provider.complete.return_value = search_response
                search_provider.default_model = "perplexity-model"
                search_provider.name = "perplexity"

                mock_gmt.side_effect = [routing_provider, search_provider]
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    result = router.route_message("How much CDBG funding does Berkeley get?")
                    assert result["action"] == "respond"
                    assert "2.5M" in result["message"]
                    assert result["provider_used"] == "perplexity"

    def test_search_web_error_returns_error_message(self, router):
        routing_response = FakeProviderResponse(
            content="",
            tool_calls=[FakeToolCall(name="search_web", arguments={"query": "test query"})],
        )

        with patch.object(ChatRouter, "detect_mode", return_value=("focus", "search")):
            with patch("civicos_services.chat.civic_chat_router.get_model_for_task") as mock_gmt:
                routing_provider = MagicMock()
                routing_provider.complete.return_value = routing_response
                routing_provider.default_model = "router-model"
                routing_provider.name = "router"

                search_provider = MagicMock()
                search_provider.complete.side_effect = RuntimeError("Perplexity API down")

                mock_gmt.side_effect = [routing_provider, search_provider]
                with patch("civicos_services.chat.civic_chat_router.log_llm_cost"):
                    result = router.route_message("search for something")
                    assert result["action"] == "respond"
                    assert "error" in result["message"].lower()
                    assert result["error"] == "Perplexity API down"


# ---------------------------------------------------------------------------
# get_router singleton
# ---------------------------------------------------------------------------


class TestGetRouter:
    """Tests for get_router() singleton factory."""

    def test_returns_chat_router_with_client(self):
        import civicos_services.chat.civic_chat_router as mod
        mod._router_instance = None  # Reset singleton

        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                from civicos_services.chat.civic_chat_router import get_router
                r = get_router()
                # Verify it's a real ChatRouter with expected attributes
                assert hasattr(r, "route_message")
                assert hasattr(r, "detect_mode")
                assert hasattr(r, "client")

    def test_returns_same_instance(self):
        import civicos_services.chat.civic_chat_router as mod
        mod._router_instance = None

        with patch.dict(os.environ, _ENV_PATCH):
            with patch("openai.OpenAI"):
                from civicos_services.chat.civic_chat_router import get_router
                r1 = get_router()
                r2 = get_router()
                assert r1 is r2
