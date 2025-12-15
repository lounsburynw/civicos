"""
MCP server for civic-legal.

Exposes legal RAG tools via Model Context Protocol:
- search_legislation: Vector search over California bills
- enrich_event: Add legislative context to civic events
- get_bill: Fetch specific bill details
- search_by_topic: Topic-based legislation search

Usage:
    # Run server
    civic-legal-server

    # Or with HTTP transport
    civic-legal-server --transport http --port 8003
"""

import argparse
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None


def create_mcp_server(
    persist_directory: str = "./data/vectors/legal",
    openai_api_key: Optional[str] = None,
) -> "Server":
    """
    Create MCP server with legal RAG tools.

    Args:
        persist_directory: Path to vector store
        openai_api_key: OpenAI API key for embeddings

    Returns:
        MCP Server instance
    """
    if not MCP_AVAILABLE:
        raise ImportError(
            "MCP not installed. Install with: pip install civic-legal[mcp]"
        )

    server = Server("civic-legal")

    # Lazy-load search to avoid startup cost
    _search = None

    def get_search():
        nonlocal _search
        if _search is None:
            try:
                from civic._internal.legal.retrieval import LegalSearch
                _search = LegalSearch(
                    persist_directory=persist_directory,
                    openai_api_key=openai_api_key,
                )
            except ImportError:
                logger.warning("Embeddings not available - search disabled")
        return _search

    @server.list_tools()
    async def list_tools():
        """List available tools."""
        return [
            Tool(
                name="search_legislation",
                description="Search California legislation using semantic similarity",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results (default: 5)",
                            "default": 5
                        },
                        "session": {
                            "type": "string",
                            "description": "Filter by legislative session (e.g., '2023-2024')"
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="enrich_event",
                description="Add legislative context to a civic event",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Event title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description"
                        },
                        "project_type": {
                            "type": "string",
                            "description": "Event type (housing, transportation, etc.)"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["keyword", "semantic"],
                            "description": "Enrichment mode (default: keyword)",
                            "default": "keyword"
                        }
                    },
                    "required": ["title"]
                }
            ),
            Tool(
                name="search_by_topic",
                description="Search legislation by topic area",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "enum": ["housing", "transportation", "environment", "budget", "education"],
                            "description": "Topic area"
                        },
                        "session": {
                            "type": "string",
                            "description": "Legislative session"
                        },
                        "top_k": {
                            "type": "integer",
                            "default": 10
                        }
                    },
                    "required": ["topic"]
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""

        if name == "search_legislation":
            search = get_search()
            if search is None:
                return [TextContent(
                    type="text",
                    text="Search not available - embeddings not installed"
                )]

            query = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)
            session = arguments.get("session")

            filter_dict = {"session": session} if session else None

            results = search.query(
                query=query,
                top_k=top_k,
                filter=filter_dict,
            )

            # Format results
            text_parts = [f"Found {len(results)} results for: {query}\n"]
            for i, r in enumerate(results, 1):
                text_parts.append(
                    f"\n{i}. {r.bill_id} (relevance: {r.relevance_score:.2f})\n"
                    f"   Section: {r.section}\n"
                    f"   {r.text[:200]}..."
                )

            return [TextContent(type="text", text="\n".join(text_parts))]

        elif name == "enrich_event":
            from civic._internal.legal.enrichment import enrich_opportunity

            opportunity = {
                "title": arguments.get("title", ""),
                "description": arguments.get("description", ""),
                "project_type": arguments.get("project_type", ""),
                "jurisdiction": {"id": "city-unknown"},
            }

            mode = arguments.get("mode", "keyword")

            try:
                if mode == "keyword":
                    from civic._internal.legal.enrichment import LegislativeCache, create_default_cache
                    cache = create_default_cache()
                    context = enrich_opportunity(opportunity, cache, mode="keyword")
                else:
                    context = enrich_opportunity(opportunity, mode="semantic")

                if context:
                    return [TextContent(
                        type="text",
                        text=f"Legislative context:\n{context}"
                    )]
                else:
                    return [TextContent(
                        type="text",
                        text="No relevant legislative context found"
                    )]

            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"Error enriching event: {e}"
                )]

        elif name == "search_by_topic":
            search = get_search()
            if search is None:
                return [TextContent(
                    type="text",
                    text="Search not available - embeddings not installed"
                )]

            topic = arguments.get("topic", "")
            session = arguments.get("session")
            top_k = arguments.get("top_k", 10)

            results = search.search_by_topic(
                topic=topic,
                session=session,
                top_k=top_k,
            )

            text_parts = [f"Found {len(results)} {topic} bills:\n"]
            for i, r in enumerate(results, 1):
                text_parts.append(f"{i}. {r.bill_id}: {r.text[:100]}...")

            return [TextContent(type="text", text="\n".join(text_parts))]

        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]

    return server


class LegalServer:
    """Wrapper class for MCP server lifecycle."""

    def __init__(self, **kwargs):
        self.server = create_mcp_server(**kwargs)

    async def run(self):
        """Run the server."""
        async with stdio_server() as (read, write):
            await self.server.run(read, write)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Civic Legal MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8003,
        help="HTTP port (if using http transport)"
    )
    parser.add_argument(
        "--persist-dir",
        default="./data/vectors/legal",
        help="Vector store directory"
    )
    args = parser.parse_args()

    if args.transport == "http":
        # HTTP transport requires uvicorn
        try:
            import uvicorn
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route

            server = create_mcp_server(persist_directory=args.persist_dir)
            transport = SseServerTransport("/messages")

            async def handle_sse(request):
                async with transport.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    await server.run(streams[0], streams[1])

            app = Starlette(routes=[Route("/sse", handle_sse)])
            uvicorn.run(app, host="0.0.0.0", port=args.port)

        except ImportError:
            print("HTTP transport requires: pip install civic-legal[http]")
            return 1
    else:
        # stdio transport (default)
        logging.basicConfig(level=logging.INFO)
        server = LegalServer(persist_directory=args.persist_dir)
        asyncio.run(server.run())

    return 0


if __name__ == "__main__":
    exit(main())
