"""
Test LangGraph integration with MCP Civic Issues Server

This demonstrates how LangGraph workflows can use MCP tools
to query civic data through the standardized MCP protocol.

Usage:
    python tests/test_mcp_langgraph_integration.py
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_mcp_adapters.client import MultiServerMCPClient, StdioConnection, load_mcp_tools
import json


async def test_mcp_connection():
    """Test connecting to civic-issues MCP server via stdio."""
    print("=" * 60)
    print("Testing MCP + LangGraph Integration")
    print("=" * 60)

    # Configure stdio connection to our MCP server
    server_config = {
        "civic-issues": StdioConnection(
            transport="stdio",
            command="python",
            args=["mcp_servers/civic_issues.py"],
            cwd=str(Path(__file__).parent.parent)
        )
    }

    # New API: Create client and use session context manager
    client = MultiServerMCPClient(server_config)

    async with client.session("civic-issues") as session:
        # Load tools from the MCP server
        print("\n1. Loading MCP tools...")
        tools = await load_mcp_tools(session)

        print(f"   Loaded {len(tools)} tools:")
        for tool in tools:
            print(f"   - {tool.name}")

        # Test query_issues tool
        print("\n2. Testing query_issues tool...")
        query_tool = next(t for t in tools if t.name == "query_issues")

        result = await query_tool.ainvoke({
            "jurisdiction": "city-san-rafael",
            "street": "5th",
            "limit": 5
        })

        # Parse result (may be string or dict)
        if isinstance(result, str):
            result = json.loads(result)

        print(f"   Result: Found {result.get('count', 0)} issues")
        if result.get('issues'):
            print(f"   Sample: {result['issues'][0].get('title', 'N/A')}")

        # Test get_issue_stats tool
        print("\n3. Testing get_issue_stats tool...")
        stats_tool = next(t for t in tools if t.name == "get_issue_stats")

        result = await stats_tool.ainvoke({
            "jurisdiction": "city-san-rafael"
        })

        if isinstance(result, str):
            result = json.loads(result)

        print(f"   Total issues: {result.get('total_issues', 0)}")
        print(f"   By status: {result.get('by_status', {})}")

        # Test get_street_issues_summary tool (pilot analysis)
        print("\n4. Testing get_street_issues_summary tool...")
        summary_tool = next(t for t in tools if t.name == "get_street_issues_summary")

        result = await summary_tool.ainvoke({
            "jurisdiction": "city-san-rafael",
            "street": "Lincoln"
        })

        if isinstance(result, str):
            result = json.loads(result)

        print(f"   Lincoln Ave issues: {result.get('total_issues', 0)}")
        print(f"   Unique addresses: {result.get('unique_addresses', 0)}")

    print("\n" + "=" * 60)
    print("MCP Integration Test Complete!")
    print("=" * 60)
    print("\nNext: Use these tools in LangGraph coordination workflow")


async def test_langgraph_with_mcp_tools():
    """
    Demonstrate using MCP tools in a LangGraph workflow.

    This shows how to replace direct SQLite queries with MCP tool calls,
    making the workflow portable to any MCP-compatible environment.
    """
    print("\n" + "=" * 60)
    print("LangGraph + MCP Coordination Demo")
    print("=" * 60)

    from langgraph.graph import StateGraph, END
    from typing import TypedDict, Any, List

    # State schema
    class MCPCoordinationState(TypedDict):
        jurisdiction_id: str
        decision_type: str
        decision_score: int
        issues: List[dict]
        status: str

    # Configure MCP client
    server_config = {
        "civic-issues": StdioConnection(
            transport="stdio",
            command="python",
            args=["mcp_servers/civic_issues.py"],
            cwd=str(Path(__file__).parent.parent)
        )
    }

    # We need to keep the client open during workflow execution
    mcp_client = MultiServerMCPClient(server_config)

    async with mcp_client.session("civic-issues") as session:
        tools = await load_mcp_tools(session)
        stats_tool = next(t for t in tools if t.name == "get_issue_stats")
        query_tool = next(t for t in tools if t.name == "query_issues")

        # Node: Score decision using MCP tool
        async def score_decision_mcp(state: MCPCoordinationState) -> MCPCoordinationState:
            """Score decision using MCP get_issue_stats tool."""
            print(f"\n   Scoring decision for {state['jurisdiction_id']}...")

            stats = await stats_tool.ainvoke({
                "jurisdiction": state["jurisdiction_id"]
            })

            # Parse result if string
            if isinstance(stats, str):
                stats = json.loads(stats)

            # Score based on issue volume
            total_issues = stats.get("total_issues", 0)
            score = 50  # Base score

            if total_issues > 1000:
                score += 80
            elif total_issues > 500:
                score += 60
            elif total_issues > 100:
                score += 40

            # Bonus for decision type
            decision_type = state["decision_type"].lower()
            if "parking" in decision_type:
                score += 30
            if "traffic" in decision_type:
                score += 25

            print(f"   Total issues: {total_issues}, Score: {score}")

            return {
                **state,
                "decision_score": score,
                "status": "scored"
            }

        # Node: Discover affected issues using MCP tool
        async def discover_issues_mcp(state: MCPCoordinationState) -> MCPCoordinationState:
            """Discover related issues using MCP query_issues tool."""
            print(f"\n   Discovering issues for {state['decision_type']}...")

            # Map decision types to search patterns
            street_patterns = {
                "parking_policy": "5th",  # 5th Ave parking decision
                "traffic_signals": "",    # All traffic issues
                "dumping": "Lincoln",     # Lincoln Ave dumping
            }

            street = street_patterns.get(state["decision_type"].lower(), "")

            result = await query_tool.ainvoke({
                "jurisdiction": state["jurisdiction_id"],
                "street": street if street else None,
                "limit": 20
            })

            # Parse result if string
            if isinstance(result, str):
                result = json.loads(result)

            issues = result.get("issues", [])
            print(f"   Found {len(issues)} related issues")

            return {
                **state,
                "issues": issues,
                "status": "discovered" if issues else "no_matches"
            }

        # Build workflow
        workflow = StateGraph(MCPCoordinationState)
        workflow.add_node("score_decision", score_decision_mcp)
        workflow.add_node("discover_issues", discover_issues_mcp)

        workflow.set_entry_point("score_decision")
        workflow.add_edge("score_decision", "discover_issues")
        workflow.add_edge("discover_issues", END)

        app = workflow.compile()

        # Run workflow
        print("\nRunning MCP-powered coordination workflow...")

        initial_state = {
            "jurisdiction_id": "city-san-rafael",
            "decision_type": "parking_policy",
            "decision_score": 0,
            "issues": [],
            "status": "starting"
        }

        result = await app.ainvoke(initial_state)

        print("\n" + "-" * 40)
        print("Workflow Result:")
        print(f"  Decision Score: {result['decision_score']}")
        print(f"  Status: {result['status']}")
        print(f"  Issues Found: {len(result['issues'])}")
        if result['issues']:
            print(f"  Sample Issue: {result['issues'][0].get('title', 'N/A')}")

    print("\n" + "=" * 60)
    print("LangGraph + MCP Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    # Run connection test first
    asyncio.run(test_mcp_connection())

    # Then run LangGraph integration demo
    asyncio.run(test_langgraph_with_mcp_tools())
