"""
MCP Server for Civic State

Exposes StateManager queries as MCP tools. Part of civic-state package.

Usage:
    from civic_state import create_mcp_server

    server = create_mcp_server(db_path="data/civic.db")
    server.run()  # stdio mode

CLI:
    civic-state-server [--http] [--port PORT] [--db PATH]
"""

from typing import Optional, Dict, Any
from civic._internal.state.manager import StateManager

try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None


class IssuesServer:
    """
    MCP Server wrapper for civic issues.

    Provides a clean interface for creating and configuring
    the issues MCP server.
    """

    def __init__(self, db_path: str = "data/civic_state.db"):
        """
        Initialize the issues server.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._state_manager: Optional[StateManager] = None
        self._mcp = self._create_server()

    def _get_state_manager(self) -> StateManager:
        """Lazy-load StateManager instance."""
        if self._state_manager is None:
            self._state_manager = StateManager(self.db_path)
        return self._state_manager

    def _create_server(self) -> FastMCP:
        """Create and configure the MCP server with tools."""
        mcp = FastMCP(
            "civic-issues",
            instructions=(
                "Query civic issues (SeeClickFix complaints) for jurisdictions. "
                "Use query_issues to find specific issues by street, type, or status. "
                "Use get_issue_stats for aggregate statistics. "
                "Use get_street_summary for corridor analysis."
            )
        )

        # Register tools
        @mcp.tool()
        def query_issues(
            jurisdiction: str,
            street: Optional[str] = None,
            issue_type: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 50
        ) -> Dict[str, Any]:
            """
            Query civic issues for a jurisdiction.

            Args:
                jurisdiction: City identifier (e.g., "city-san-rafael")
                street: Filter by street name (partial match)
                issue_type: Filter by type (e.g., "Pothole", "Graffiti")
                status: Filter by status ("open" or "closed")
                limit: Max results (default 50, max 100)

            Returns:
                Dictionary with matching issues and count
            """
            sm = self._get_state_manager()
            limit = min(limit, 100)

            issues = sm.query_issues(
                jurisdiction_id=jurisdiction,
                street=street,
                issue_type=issue_type,
                status=status,
                limit=limit
            )

            # Simplify for AI consumption
            simplified = [
                {
                    "id": issue.get("id"),
                    "title": issue.get("title"),
                    "issue_type": issue.get("issue_type"),
                    "address": issue.get("address"),
                    "status": issue.get("status"),
                    "created_at": issue.get("created_at")
                }
                for issue in issues
            ]

            return {
                "jurisdiction": jurisdiction,
                "filters": {"street": street, "issue_type": issue_type, "status": status},
                "count": len(simplified),
                "issues": simplified
            }

        @mcp.tool()
        def get_issue_stats(jurisdiction: str) -> Dict[str, Any]:
            """
            Get aggregate statistics about issues for a jurisdiction.

            Args:
                jurisdiction: City identifier (e.g., "city-san-rafael")

            Returns:
                Statistics including total count, breakdown by status and type
            """
            sm = self._get_state_manager()
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
        def get_street_summary(jurisdiction: str, street: str) -> Dict[str, Any]:
            """
            Get a summary of issues for a specific street.

            Args:
                jurisdiction: City identifier (e.g., "city-san-rafael")
                street: Street name to analyze (e.g., "5th", "Lincoln Ave")

            Returns:
                Summary with issue counts by type and unique addresses
            """
            sm = self._get_state_manager()

            issues = sm.query_issues(
                jurisdiction_id=jurisdiction,
                street=street,
                limit=100
            )

            # Analyze by type
            type_counts: Dict[str, int] = {}
            status_counts = {"open": 0, "closed": 0}
            addresses: set = set()

            for issue in issues:
                issue_type = issue.get("issue_type") or "Unknown"
                type_counts[issue_type] = type_counts.get(issue_type, 0) + 1

                status = issue.get("status") or "open"
                if status in status_counts:
                    status_counts[status] += 1

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
            sm = self._get_state_manager()
            jurisdictions = sm.list_jurisdictions()

            return {
                "jurisdictions": [
                    {
                        "jurisdiction_id": j.get("jurisdiction_id"),
                        "name": j.get("jurisdiction_name"),
                    }
                    for j in jurisdictions
                ],
                "total": len(jurisdictions)
            }

        return mcp

    def run(self) -> None:
        """Run the server in stdio mode (for Claude Desktop)."""
        self._mcp.run()

    def sse_app(self):
        """Get the SSE app for HTTP mode (for LangGraph, web clients)."""
        return self._mcp.sse_app()

    @property
    def mcp(self) -> FastMCP:
        """Access the underlying FastMCP instance."""
        return self._mcp


def create_mcp_server(db_path: str = "data/civic_state.db") -> IssuesServer:
    """
    Factory function to create an MCP server for civic state.

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured IssuesServer instance

    Example:
        server = create_mcp_server("data/civic.db")
        server.run()  # stdio mode
    """
    if not MCP_AVAILABLE:
        raise ImportError("MCP not installed. Install with: pip install civic-state[mcp]")
    return IssuesServer(db_path=db_path)


# Alias for backwards compatibility
create_issues_server = create_mcp_server


def main():
    """CLI entry point for civic-state MCP server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Civic State MCP Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--db", type=str, default="data/civic_state.db", help="Database path")
    args = parser.parse_args()

    server = create_mcp_server(db_path=args.db)

    if args.http:
        try:
            import uvicorn
        except ImportError:
            print("uvicorn not installed. Install with: pip install civic-state[http]", file=sys.stderr)
            sys.exit(1)
        print(f"Starting Civic State MCP Server on http://localhost:{args.port}")
        uvicorn.run(server.sse_app(), host="0.0.0.0", port=args.port)
    else:
        print("Starting Civic State MCP Server (stdio mode)", file=sys.stderr)
        server.run()


if __name__ == "__main__":
    main()
