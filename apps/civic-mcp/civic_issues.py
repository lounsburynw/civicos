"""
MCP Server for Civic Issues

Exposes StateManager queries as MCP tools, allowing any MCP-compatible AI
to query San Rafael civic issues (SeeClickFix complaints).

Usage:
    # Run as stdio server (for Claude Desktop, etc.)
    python apps/civic-mcp/civic_issues.py

    # Run as HTTP server (for LangGraph, etc.)
    python apps/civic-mcp/civic_issues.py --http --port 8080
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp.server.fastmcp import FastMCP
from typing import Optional, List, Dict, Any
import json

# Import StateManager
from state_manager import StateManager

# Initialize MCP server
mcp = FastMCP(
    "civic-issues",
    instructions="Query civic issues (SeeClickFix complaints) for San Rafael and other jurisdictions. Use query_issues to find specific issues by street, type, or status. Use get_issue_stats for aggregate statistics."
)

# Default database path (relative to project root)
DB_PATH = Path(__file__).parent.parent / "data" / "civic_state.db"


def get_state_manager() -> StateManager:
    """Get StateManager instance with configured database path."""
    return StateManager(str(DB_PATH))


@mcp.tool()
def query_issues(
    jurisdiction: str,
    street: Optional[str] = None,
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Query civic issues (SeeClickFix complaints) for a jurisdiction.

    Args:
        jurisdiction: City identifier (e.g., "city-san-rafael")
        street: Filter by street name (partial match, e.g., "5th" or "Lincoln")
        issue_type: Filter by issue type (e.g., "Pothole", "Graffiti")
        status: Filter by status ("open" or "closed")
        limit: Maximum number of results (default 50, max 100)

    Returns:
        Dictionary with matching issues and count

    Examples:
        - query_issues("city-san-rafael", street="5th") -> 5th Avenue issues
        - query_issues("city-san-rafael", issue_type="Pothole") -> All potholes
        - query_issues("city-san-rafael", status="open") -> Open issues only
    """
    sm = get_state_manager()

    # Cap limit at 100
    limit = min(limit, 100)

    issues = sm.query_issues(
        jurisdiction_id=jurisdiction,
        street=street,
        issue_type=issue_type,
        status=status,
        limit=limit
    )

    # Simplify response for AI consumption
    simplified = []
    for issue in issues:
        simplified.append({
            "id": issue.get("id"),
            "title": issue.get("title"),
            "issue_type": issue.get("issue_type"),
            "address": issue.get("address"),
            "status": issue.get("status"),
            "created_at": issue.get("created_at")
        })

    return {
        "jurisdiction": jurisdiction,
        "filters": {
            "street": street,
            "issue_type": issue_type,
            "status": status
        },
        "count": len(simplified),
        "issues": simplified
    }


@mcp.tool()
def get_issue_stats(jurisdiction: str) -> Dict[str, Any]:
    """
    Get aggregate statistics about civic issues for a jurisdiction.

    Args:
        jurisdiction: City identifier (e.g., "city-san-rafael")

    Returns:
        Statistics including total count, breakdown by status and type

    Examples:
        - get_issue_stats("city-san-rafael") -> San Rafael issue statistics
    """
    sm = get_state_manager()
    stats = sm.get_issue_stats(jurisdiction)

    return {
        "jurisdiction": jurisdiction,
        "total_issues": stats.get("total_issues", 0),
        "by_status": stats.get("by_status", {}),
        "top_issue_types": [
            {"type": t, "count": c}
            for t, c in stats.get("top_types", [])
        ]
    }


@mcp.tool()
def get_street_issues_summary(jurisdiction: str, street: str) -> Dict[str, Any]:
    """
    Get a summary of issues for a specific street, useful for pilot outreach.

    Args:
        jurisdiction: City identifier (e.g., "city-san-rafael")
        street: Street name to analyze (e.g., "5th", "Lincoln Ave")

    Returns:
        Summary with issue counts by type and list of unique addresses

    Examples:
        - get_street_issues_summary("city-san-rafael", "5th") -> 5th Ave analysis
    """
    sm = get_state_manager()

    issues = sm.query_issues(
        jurisdiction_id=jurisdiction,
        street=street,
        limit=100
    )

    # Analyze by type
    type_counts = {}
    status_counts = {"open": 0, "closed": 0}
    addresses = set()

    for issue in issues:
        # Count by type
        issue_type = issue.get("issue_type") or "Unknown"
        type_counts[issue_type] = type_counts.get(issue_type, 0) + 1

        # Count by status
        status = issue.get("status") or "open"
        if status in status_counts:
            status_counts[status] += 1

        # Collect unique addresses
        if issue.get("address"):
            addresses.add(issue["address"])

    return {
        "jurisdiction": jurisdiction,
        "street": street,
        "total_issues": len(issues),
        "by_status": status_counts,
        "by_type": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "unique_addresses": len(addresses),
        "sample_addresses": list(addresses)[:10]
    }


@mcp.tool()
def list_jurisdictions() -> Dict[str, Any]:
    """
    List all jurisdictions with civic issue data.

    Returns:
        List of jurisdiction IDs with issue counts
    """
    sm = get_state_manager()

    # Query the database directly for jurisdiction list
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT jurisdiction_id, COUNT(*) as issue_count
        FROM issues
        WHERE valid_to IS NULL
        GROUP BY jurisdiction_id
        ORDER BY issue_count DESC
    """)

    jurisdictions = []
    for row in cursor.fetchall():
        jurisdictions.append({
            "jurisdiction_id": row[0],
            "issue_count": row[1]
        })

    conn.close()

    return {
        "jurisdictions": jurisdictions,
        "total_jurisdictions": len(jurisdictions)
    }


def main():
    """Run the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Civic Issues MCP Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    args = parser.parse_args()

    if args.http:
        # Run as HTTP server for LangGraph integration
        import uvicorn
        print(f"Starting Civic Issues MCP Server on http://localhost:{args.port}")
        uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=args.port)
    else:
        # Run as stdio server for Claude Desktop
        print("Starting Civic Issues MCP Server (stdio mode)", file=sys.stderr)
        mcp.run()


if __name__ == "__main__":
    main()
