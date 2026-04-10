"""
Tests for legal/mcp.py — MCP server for legal RAG tools.

Covers: tool listing, search_legislation, enrich_event, search_by_topic,
unknown tool handling, lazy search init, import guards.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


# ---------- Helpers ----------

def run_async(coro):
    """Run an async function synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def mock_mcp_deps():
    """Patch MCP dependencies so we can create the server."""
    mock_server_cls = MagicMock()
    mock_server = MagicMock()
    mock_server_cls.return_value = mock_server

    # Capture decorated handlers
    handlers = {}

    def capture_list_tools():
        def decorator(fn):
            handlers["list_tools"] = fn
            return fn
        return decorator

    def capture_call_tool():
        def decorator(fn):
            handlers["call_tool"] = fn
            return fn
        return decorator

    mock_server.list_tools = capture_list_tools
    mock_server.call_tool = capture_call_tool

    with patch("civicos._internal.legal.mcp.MCP_AVAILABLE", True), \
         patch("civicos._internal.legal.mcp.Server", mock_server_cls), \
         patch("civicos._internal.legal.mcp.Tool", MagicMock(), create=True), \
         patch("civicos._internal.legal.mcp.TextContent", create=True) as mock_tc:
        mock_tc.side_effect = lambda **kwargs: SimpleNamespace(**kwargs)

        from civicos._internal.legal.mcp import create_mcp_server
        server = create_mcp_server(persist_directory="/tmp/test")
        yield server, handlers, mock_tc


# ---------- create_mcp_server ----------

class TestCreateMcpServer:

    def test_import_guard_raises_with_install_instructions(self):
        with patch("civicos._internal.legal.mcp.MCP_AVAILABLE", False):
            from civicos._internal.legal.mcp import create_mcp_server
            with pytest.raises(ImportError, match="pip install"):
                create_mcp_server()

    def test_registers_both_handler_types(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps
        assert "list_tools" in handlers
        assert "call_tool" in handlers


# ---------- list_tools ----------

class TestListTools:

    def test_returns_three_tools(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps
        tools = run_async(handlers["list_tools"]())
        assert len(tools) == 3


# ---------- call_tool: search_legislation ----------

class TestSearchLegislation:

    def test_formats_results_with_bill_ids_and_scores(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        mock_result = SimpleNamespace(
            bill_id="AB-1234",
            relevance_score=0.85,
            section="Section 1",
            text="Housing affordability requirements for local jurisdictions",
        )

        with patch(
            "civicos._internal.legal.retrieval.LegalSearch",
            create=True,
        ) as mock_search_cls:
            mock_search = MagicMock()
            mock_search.query.return_value = [mock_result]
            mock_search_cls.return_value = mock_search

            result = run_async(handlers["call_tool"]("search_legislation", {"query": "housing"}))

        assert len(result) == 1
        text = result[0].text
        assert "AB-1234" in text
        assert "0.85" in text
        assert "1 results" in text
        assert "housing" in text

    def test_passes_query_params_to_search(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        with patch(
            "civicos._internal.legal.retrieval.LegalSearch",
            create=True,
        ) as mock_search_cls:
            mock_search = MagicMock()
            mock_search.query.return_value = []
            mock_search_cls.return_value = mock_search

            run_async(handlers["call_tool"]("search_legislation", {
                "query": "housing policy",
                "top_k": 3,
                "session": "2023-2024",
            }))

        mock_search.query.assert_called_once_with(
            query="housing policy",
            top_k=3,
            filter={"session": "2023-2024"},
        )

    def test_returns_unavailable_when_search_fails_to_init(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        with patch(
            "civicos._internal.legal.retrieval.LegalSearch",
            side_effect=ImportError("no embeddings"),
            create=True,
        ):
            result = run_async(handlers["call_tool"]("search_legislation", {"query": "test"}))

        assert len(result) == 1
        assert "not available" in result[0].text.lower()


# ---------- call_tool: enrich_event ----------

class TestEnrichEvent:

    def test_returns_error_message_on_failure(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        with patch(
            "civicos._internal.legal.enrichment.enrich_opportunity",
            side_effect=Exception("enrichment failed"),
        ), patch(
            "civicos._internal.legal.enrichment.create_default_cache",
            return_value=MagicMock(),
        ), patch(
            "civicos._internal.legal.enrichment.LegislativeCache",
            MagicMock(),
        ):
            result = run_async(handlers["call_tool"]("enrich_event", {
                "title": "Test Event",
                "mode": "keyword",
            }))

        assert len(result) == 1
        assert "enrichment failed" in result[0].text.lower()

    def test_returns_no_context_message_when_none(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        with patch(
            "civicos._internal.legal.enrichment.enrich_opportunity",
            return_value=None,
        ), patch(
            "civicos._internal.legal.enrichment.create_default_cache",
            return_value=MagicMock(),
        ), patch(
            "civicos._internal.legal.enrichment.LegislativeCache",
            MagicMock(),
        ):
            result = run_async(handlers["call_tool"]("enrich_event", {
                "title": "Obscure Topic",
                "mode": "keyword",
            }))

        assert len(result) == 1
        assert "no relevant" in result[0].text.lower()


# ---------- call_tool: search_by_topic ----------

class TestSearchByTopic:

    def test_formats_topic_results(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        mock_result = SimpleNamespace(
            bill_id="SB-100",
            text="Environmental regulation for water quality standards",
        )

        mock_search = MagicMock()
        mock_search.search_by_topic.return_value = [mock_result]

        with patch(
            "civicos._internal.legal.retrieval.LegalSearch",
            return_value=mock_search,
            create=True,
        ):
            result = run_async(handlers["call_tool"]("search_by_topic", {
                "topic": "environment",
                "top_k": 5,
            }))

        assert len(result) == 1
        text = result[0].text
        assert "SB-100" in text
        assert "environment" in text
        assert "1" in text  # count

    def test_returns_unavailable_when_search_fails(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps

        with patch(
            "civicos._internal.legal.retrieval.LegalSearch",
            side_effect=ImportError("no embeddings"),
            create=True,
        ):
            result = run_async(handlers["call_tool"]("search_by_topic", {"topic": "housing"}))

        assert len(result) == 1
        assert "not available" in result[0].text.lower()


# ---------- call_tool: unknown tool ----------

class TestUnknownTool:

    def test_returns_error_with_tool_name(self, mock_mcp_deps):
        _, handlers, _ = mock_mcp_deps
        result = run_async(handlers["call_tool"]("nonexistent_tool", {}))
        assert len(result) == 1
        assert "nonexistent_tool" in result[0].text
        assert "Unknown tool" in result[0].text
