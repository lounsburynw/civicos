"""
Tests for state/mcp.py — IssuesServer MCP server.

Covers: tool registration, query_issues, get_issue_stats, get_street_summary,
list_jurisdictions, factory function, limit capping, output structure.
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_mcp_env():
    """Create IssuesServer with mocked FastMCP and StateManager."""
    mock_fastmcp_cls = MagicMock()
    mock_mcp_instance = MagicMock()
    mock_fastmcp_cls.return_value = mock_mcp_instance

    registered_tools = {}

    def capture_tool():
        def decorator(fn):
            registered_tools[fn.__name__] = fn
            return fn
        return decorator

    mock_mcp_instance.tool = capture_tool

    with patch("civicos._internal.state.mcp.MCP_AVAILABLE", True), \
         patch("civicos._internal.state.mcp.FastMCP", mock_fastmcp_cls), \
         patch("civicos._internal.state.mcp.StateManager") as mock_sm_cls:

        mock_sm = MagicMock()
        mock_sm_cls.return_value = mock_sm

        from civicos._internal.state.mcp import IssuesServer
        server = IssuesServer(db_path=":memory:")
        server._state_manager = mock_sm

        yield server, registered_tools, mock_sm


# ---------- IssuesServer ----------

class TestIssuesServer:

    def test_registers_all_four_tools(self, mock_mcp_env):
        _, tools, _ = mock_mcp_env
        expected_tools = {"query_issues", "get_issue_stats", "get_street_summary", "list_jurisdictions"}
        assert set(tools.keys()) == expected_tools

    def test_lazy_state_manager_init(self):
        with patch("civicos._internal.state.mcp.MCP_AVAILABLE", True), \
             patch("civicos._internal.state.mcp.FastMCP", MagicMock()), \
             patch("civicos._internal.state.mcp.StateManager") as mock_sm_cls:
            from civicos._internal.state.mcp import IssuesServer
            server = IssuesServer(db_path="test.db")
            # Not initialized until first access
            assert server._state_manager is None
            sm = server._get_state_manager()
            # Now initialized with correct path
            mock_sm_cls.assert_called_once_with("test.db")
            # Second call returns same instance
            sm2 = server._get_state_manager()
            assert sm is sm2
            mock_sm_cls.assert_called_once()  # Still only one call


# ---------- query_issues tool ----------

class TestQueryIssuesTool:

    def test_simplifies_output_to_core_fields_only(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = [
            {
                "id": "issue-1",
                "title": "Pothole on 4th St",
                "issue_type": "Pothole",
                "address": "123 4th St",
                "status": "open",
                "created_at": "2026-01-15",
                "internal_notes": "should be stripped",
                "raw_data": {"big": "object"},
            }
        ]

        result = tools["query_issues"]("city-san-rafael")
        issue = result["issues"][0]
        assert issue == {
            "id": "issue-1",
            "title": "Pothole on 4th St",
            "issue_type": "Pothole",
            "address": "123 4th St",
            "status": "open",
            "created_at": "2026-01-15",
        }
        assert result["count"] == 1

    def test_clamps_limit_to_100(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = []

        tools["query_issues"]("city-test", limit=500)
        actual_limit = mock_sm.query_issues.call_args[1]["limit"]
        assert actual_limit == 100

    def test_preserves_limit_under_100(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = []

        tools["query_issues"]("city-test", limit=25)
        actual_limit = mock_sm.query_issues.call_args[1]["limit"]
        assert actual_limit == 25

    def test_passes_all_filter_params(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = []

        result = tools["query_issues"](
            "city-test",
            street="Main St",
            issue_type="Graffiti",
            status="closed",
            limit=10,
        )
        assert result["filters"] == {
            "street": "Main St",
            "issue_type": "Graffiti",
            "status": "closed",
        }

    def test_returns_empty_for_no_matches(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = []

        result = tools["query_issues"]("city-test", issue_type="UFO")
        assert result["count"] == 0
        assert result["issues"] == []


# ---------- get_issue_stats tool ----------

class TestGetIssueStatsTool:

    def test_formats_stats_with_type_breakdown(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.get_issue_stats.return_value = {
            "total_issues": 150,
            "by_status": {"open": 80, "closed": 70},
            "top_types": [("Pothole", 45), ("Graffiti", 30), ("Noise", 20)],
        }

        result = tools["get_issue_stats"]("city-san-rafael")
        assert result["total_issues"] == 150
        assert result["by_status"] == {"open": 80, "closed": 70}
        assert result["top_issue_types"] == [
            {"type": "Pothole", "count": 45},
            {"type": "Graffiti", "count": 30},
            {"type": "Noise", "count": 20},
        ]

    def test_handles_empty_stats_gracefully(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.get_issue_stats.return_value = {}

        result = tools["get_issue_stats"]("city-test")
        assert result["total_issues"] == 0
        assert result["by_status"] == {}
        assert result["top_issue_types"] == []


# ---------- get_street_summary tool ----------

class TestGetStreetSummaryTool:

    def test_computes_correct_aggregations(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = [
            {"issue_type": "Pothole", "status": "open", "address": "100 5th Ave"},
            {"issue_type": "Pothole", "status": "closed", "address": "200 5th Ave"},
            {"issue_type": "Graffiti", "status": "open", "address": "100 5th Ave"},
        ]

        result = tools["get_street_summary"]("city-san-rafael", "5th Ave")
        assert result["total_issues"] == 3
        assert result["by_status"] == {"open": 2, "closed": 1}
        assert result["by_type"]["Pothole"] == 2
        assert result["by_type"]["Graffiti"] == 1
        assert result["unique_addresses"] == 2
        assert set(result["sample_addresses"]) == {"100 5th Ave", "200 5th Ave"}

    def test_returns_zeros_for_empty_street(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = []

        result = tools["get_street_summary"]("city-test", "Nonexistent St")
        assert result["total_issues"] == 0
        assert result["by_status"] == {"open": 0, "closed": 0}
        assert result["by_type"] == {}
        assert result["unique_addresses"] == 0
        assert result["sample_addresses"] == []

    def test_treats_missing_type_as_unknown(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = [
            {"issue_type": None, "status": "open", "address": "1 Main"},
        ]

        result = tools["get_street_summary"]("city-test", "Main")
        assert result["by_type"] == {"Unknown": 1}

    def test_skips_null_addresses_in_dedup(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = [
            {"issue_type": "X", "status": "open", "address": None},
            {"issue_type": "X", "status": "open", "address": "1 Main"},
        ]

        result = tools["get_street_summary"]("city-test", "Main")
        assert result["unique_addresses"] == 1
        assert result["sample_addresses"] == ["1 Main"]

    def test_sorts_types_by_frequency_descending(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = [
            {"issue_type": "Rare", "status": "open", "address": "1 A"},
            {"issue_type": "Common", "status": "open", "address": "2 A"},
            {"issue_type": "Common", "status": "open", "address": "3 A"},
            {"issue_type": "Common", "status": "open", "address": "4 A"},
        ]

        result = tools["get_street_summary"]("city-test", "A St")
        type_names = list(result["by_type"].keys())
        type_counts = list(result["by_type"].values())
        assert type_names[0] == "Common"
        assert type_counts[0] == 3
        assert type_counts[0] > type_counts[1]

    def test_caps_sample_addresses_at_10(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.query_issues.return_value = [
            {"issue_type": "X", "status": "open", "address": f"{i} Main St"}
            for i in range(20)
        ]

        result = tools["get_street_summary"]("city-test", "Main")
        assert result["unique_addresses"] == 20
        assert len(result["sample_addresses"]) == 10


# ---------- list_jurisdictions tool ----------

class TestListJurisdictionsTool:

    def test_returns_formatted_jurisdictions(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.list_jurisdictions.return_value = [
            {"jurisdiction_id": "city-san-rafael", "jurisdiction_name": "San Rafael"},
            {"jurisdiction_id": "city-novato", "jurisdiction_name": "Novato"},
        ]

        result = tools["list_jurisdictions"]()
        assert result["total"] == 2
        assert result["jurisdictions"] == [
            {"jurisdiction_id": "city-san-rafael", "name": "San Rafael"},
            {"jurisdiction_id": "city-novato", "name": "Novato"},
        ]

    def test_returns_empty_list(self, mock_mcp_env):
        _, tools, mock_sm = mock_mcp_env
        mock_sm.list_jurisdictions.return_value = []

        result = tools["list_jurisdictions"]()
        assert result["total"] == 0
        assert result["jurisdictions"] == []


# ---------- Factory function ----------

class TestCreateMcpServer:

    def test_import_guard_with_install_instructions(self):
        with patch("civicos._internal.state.mcp.MCP_AVAILABLE", False):
            from civicos._internal.state.mcp import create_mcp_server
            with pytest.raises(ImportError, match="pip install"):
                create_mcp_server()

    def test_alias_points_to_same_function(self):
        from civicos._internal.state.mcp import create_mcp_server, create_issues_server
        assert create_issues_server is create_mcp_server
