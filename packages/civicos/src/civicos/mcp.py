"""
Civic MCP Server

Unified MCP server exposing all Civic platform tools.

Usage:
    # Run standalone
    civic-server

    # Or in code
    from civicos.mcp import create_mcp_server, main
    server = create_mcp_server()
    server.run()

Tools exposed:
    Query (Learn):
    - what_applies: Get regulatory stack for a topic
    - what_happened: Search past decisions
    - whats_next: Get upcoming meetings
    - whos_with_me: Find others who care

    Coordination tools have moved to civicos-relay.

"""

from typing import Optional, List

# Optional MCP import
try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None


class CivicServer:
    """
    MCP Server wrapper for Civic platform.

    Provides a clean interface for creating and configuring
    the unified Civic MCP server.
    """

    def __init__(
        self,
        db_path: str = "data/civic_state.db",
        jurisdiction_id: str = "city-san-rafael"
    ):
        """
        Initialize the Civic server.

        Args:
            db_path: Path to SQLite database
            jurisdiction_id: Jurisdiction ID for Civic instance
        """
        self.db_path = db_path
        self.jurisdiction_id = jurisdiction_id
        self._civic = None
        self._mcp = self._create_server() if MCP_AVAILABLE else None

    def _get_civic(self):
        """Lazy-load Civic instance."""
        if self._civic is None:
            from civicos.civicos import CivicOS
            self._civic = CivicOS(self.jurisdiction_id, db_path=self.db_path)
        return self._civic

    def _create_server(self):
        """Create the FastMCP server with all tools."""
        if not MCP_AVAILABLE:
            return None

        mcp = FastMCP("civic")

        # ─────────── QUERY TOOLS (Learn) ───────────

        @mcp.tool()
        def what_applies(
            jurisdiction: str,
            topic: str,
            location: str = None
        ) -> dict:
            """
            Get regulatory stack for a topic.

            Use when user asks: "What are the rules for...", "Can I...", "Is it legal to..."

            Args:
                jurisdiction: City/jurisdiction ID (e.g., "san-rafael-ca")
                topic: Topic to search (e.g., "housing", "bike lanes")
                location: Optional specific location

            Returns:
                Dict with federal, state, and local regulatory context
            """
            from civicos.civicos import CivicOS
            c = CivicOS(jurisdiction, db_path=self.db_path)
            result = c.what_applies(topic, location)
            return {
                "topic": result.topic,
                "jurisdiction": result.jurisdiction,
                "federal": result.federal,
                "state": result.state,
                "local": result.local,
            }

        @mcp.tool()
        def what_happened(
            jurisdiction: str,
            query: str,
            since: str = None
        ) -> list:
            """
            Search past decisions.

            Use when user asks: "Has the city ever...", "What happened with...", "Any precedent for..."

            Args:
                jurisdiction: City/jurisdiction ID
                query: Search query (e.g., "bike lanes", "housing development")
                since: Optional date filter (ISO format)

            Returns:
                List of matching decisions
            """
            from civicos.civicos import CivicOS
            c = CivicOS(jurisdiction, db_path=self.db_path)
            results = c.what_happened(query, since)
            return [
                {
                    "id": d.id,
                    "title": d.title,
                    "date": str(d.date),
                    "outcome": d.outcome,
                    "body": d.body,
                }
                for d in results
            ]

        @mcp.tool()
        def whats_next(
            jurisdiction: str,
            topics: list = None,
            days: int = 30
        ) -> list:
            """
            Get upcoming meetings and agendas.

            Use when user asks: "When can I...", "Is there a meeting about...", "How do I participate..."

            Args:
                jurisdiction: City/jurisdiction ID
                topics: Optional list of topics to filter by
                days: Days to look ahead (default 30)

            Returns:
                List of upcoming meetings with agenda items
            """
            from civicos.civicos import CivicOS
            c = CivicOS(jurisdiction, db_path=self.db_path)
            meetings = c.whats_next(topics, days)
            return [
                {
                    "id": m.id,
                    "title": m.title,
                    "date": str(m.date),
                    "body": m.body,
                    "agenda_items": m.agenda_items,
                    "location": m.location,
                }
                for m in meetings
            ]

        @mcp.tool()
        def whos_with_me(
            jurisdiction: str,
            topic: str
        ) -> dict:
            """
            Find others who care about this topic.

            Use when user asks: "Am I alone in...", "Who else cares about...", "Is anyone working on..."

            Args:
                jurisdiction: City/jurisdiction ID
                topic: Topic to search

            Returns:
                Community info with follower count, voices, initiatives
            """
            from civicos.civicos import CivicOS
            c = CivicOS(jurisdiction, db_path=self.db_path)
            community = c.whos_with_me(topic)
            return {
                "topic": community.topic,
                "jurisdiction": community.jurisdiction,
                "follower_count": community.follower_count,
                "recent_voices": community.recent_voices,
                "active_initiatives": community.active_initiatives,
            }

        return mcp

    def run(self):
        """Run the MCP server in stdio mode."""
        if self._mcp:
            self._mcp.run()
        else:
            print("MCP not available. Install with: pip install civic[mcp]")


# Module-level server instance (lazy)
_server_instance = None


def create_mcp_server(db_path: str = "data/civic_state.db") -> CivicServer:
    """Create a Civic MCP server instance."""
    return CivicServer(db_path=db_path)


def get_server() -> Optional[CivicServer]:
    """Get or create the module-level server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = create_mcp_server()
    return _server_instance


# For backwards compatibility
server = None  # Lazy - use get_server()


def main():
    """Run the MCP server."""
    srv = create_mcp_server()
    srv.run()


if __name__ == "__main__":
    main()
