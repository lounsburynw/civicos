"""
CivicOS MCP Server - Container Entry Point

This is the entry point for Docker/container deployments.
For Modal deployment, use modal_app.py instead.

Supports jurisdiction-specific deployments via CIVICOS_JURISDICTION env var.
Each jurisdiction level (federal, state, city) gets different tools.

Usage:
    # City-level server (default)
    CIVICOS_JURISDICTION=city-san-rafael uvicorn server:app --host 0.0.0.0 --port 8080

    # Federal-level server
    CIVICOS_JURISDICTION=country-united-states uvicorn server:app --host 0.0.0.0 --port 8080

Or with Python:
    python server.py
"""

import os
import sys
import logging
import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("civicos-mcp")

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create FastAPI app
app = FastAPI(
    title="CivicOS MCP Server",
    description="MCP server providing civic data tools for AI assistants",
    version="1.0.0",
)

# Global state (initialized on startup)
_civic = None
_registry = None
_jurisdiction = None
_jurisdiction_config = None
_validate_input = None


@app.on_event("startup")
async def startup():
    """Initialize CivicOS and tool registry on startup."""
    global _civic, _registry, _jurisdiction, _jurisdiction_config, _validate_input
    import time

    logger.info("Initializing CivicOS MCP Server...")

    from civicos import CivicOS
    from tools.registry import ToolRegistry
    from tools import handlers
    from civicos_input_validator import validate_civic_input

    # Load jurisdiction config
    from handlers.loader import load_jurisdiction_config, get_tools_for_level

    _jurisdiction = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")
    _jurisdiction_config = load_jurisdiction_config(_jurisdiction)
    _validate_input = validate_civic_input

    logger.info(
        f"Jurisdiction: {_jurisdiction_config.display_name} "
        f"(level: {_jurisdiction_config.level})"
    )

    # Initialize CivicOS
    start = time.time()
    _civic = CivicOS(_jurisdiction)
    init_time = time.time() - start
    logger.info(
        f"CivicOS initialized for {_jurisdiction} "
        f"(storage: {type(_civic._storage).__name__}, {init_time:.1f}s)"
    )

    # Pre-warm embedding model if available
    if _civic._vectors is not None:
        logger.info("Pre-warming embedding model...")
        start = time.time()
        provider = _civic._vectors._embedding_provider
        _ = provider.encode(["warmup query"])
        warmup_time = time.time() - start
        logger.info(f"Embedding model ready ({provider.model_name}, {warmup_time:.1f}s)")

    # Create tool registry
    _registry = ToolRegistry()

    # Get enabled tools for this jurisdiction level
    enabled_tools = _jurisdiction_config.get_enabled_tools()
    logger.info(f"Enabled tools for {_jurisdiction_config.level} level: {len(enabled_tools)}")

    # Import config-driven handlers for engagement tools
    from handlers.jurisdiction import engagement as config_handlers

    # Map tools to handlers (with config-driven replacements where available)
    config_driven = {
        "compose_public_comment": config_handlers.compose_public_comment,
        "get_comment_guidelines": config_handlers.get_comment_guidelines,
        "get_comment_template": config_handlers.get_comment_template,
    }

    handler_map = {
        # Core civic tools
        "search_meeting_history": handlers.search_meeting_history,
        "get_upcoming_meetings": handlers.get_upcoming_meetings,
        "find_similar_issues": handlers.find_similar_issues,
        "search_regulatory_stack": handlers.search_regulatory_stack,
        "compose_public_comment": config_driven["compose_public_comment"],
        "city_pulse": handlers.city_pulse,
        "get_issue_analytics": handlers.get_issue_analytics,
        "get_issue_trends": handlers.get_issue_trends,
        "geo_search_issues": handlers.geo_search_issues,
        "search_budget": handlers.search_budget,
        "get_public_testimony": handlers.get_public_testimony,
        "search_agenda_packets": handlers.search_agenda_packets,
        "get_comment_guidelines": config_driven["get_comment_guidelines"],
        "get_started": handlers.get_started,
        # 311 analysis tools
        "query_issue_data": handlers.query_issue_data,
        "get_issue_resolution_stats": handlers.get_issue_resolution_stats,
        "detect_trends": handlers.detect_trends,
        "get_issue_sample": handlers.get_issue_sample,
        "find_issues_near_address": handlers.find_issues_near_address,
        "find_repeat_issues": handlers.find_repeat_issues,
        "get_seasonal_patterns": handlers.get_seasonal_patterns,
        "compare_zip_codes": handlers.compare_zip_codes,
        "neighborhood_report": handlers.neighborhood_report,
        # Council/voting tools
        "get_voting_record": handlers.get_voting_record,
        "get_decision_context": handlers.get_decision_context,
        # Legislation & Executive Order tools
        "search_legislation": handlers.search_legislation,
        "get_bill_detail": handlers.get_bill_detail,
        "get_leverage_points": handlers.get_leverage_points,
        "search_executive_orders": handlers.search_executive_orders,
        "get_recent_executive_orders": handlers.get_recent_executive_orders,
        # Financial tools
        "get_funding_flow": handlers.get_funding_flow,
        "get_federal_expenditures": handlers.get_federal_expenditures,
        "get_intergovernmental_revenue": handlers.get_intergovernmental_revenue,
        # Action tools
        "get_comment_template": config_driven["get_comment_template"],
        "prepare_for_meeting": handlers.prepare_for_meeting,
        # Coordination tools
        "get_voice_counts": handlers.get_voice_counts,
        "subscribe_to_topic": handlers.subscribe_to_topic,
        "prepare_voice": handlers.prepare_voice,
        "broadcast_voice": handlers.broadcast_voice,
        "prepare_initiative": handlers.prepare_initiative,
        "broadcast_initiative": handlers.broadcast_initiative,
        "list_initiatives": handlers.list_initiatives,
        "list_relays": handlers.list_relays,
        # Context Assembly
        "get_item_context": handlers.get_item_context,
    }

    def wrap_handler(handler_fn):
        def wrapped(args: dict) -> str:
            result = handler_fn(_civic, _jurisdiction, _validate_input, logger, args)
            if isinstance(result, dict):
                return json.dumps(result, indent=2, default=str)
            return result
        return wrapped

    # Only bind handlers for tools enabled at this jurisdiction level
    bound_count = 0
    for name, handler_fn in handler_map.items():
        if name in enabled_tools:
            try:
                _registry.bind_handler(name, wrap_handler(handler_fn))
                bound_count += 1
            except ValueError as e:
                logger.warning(f"Could not bind handler {name}: {e}")

    # Mount v2 query interface
    try:
        from civicos_services.query import create_v2_router
        v2_router = create_v2_router(_civic, _jurisdiction, registry=_registry, logger_override=logger)
        app.include_router(v2_router)
        logger.info("v2 query interface mounted at /api/v2/civic/")
    except Exception as e:
        logger.warning(f"Could not mount v2 query interface: {e}")

    logger.info(
        f"MCP Server ready with {bound_count} tools "
        f"(level: {_jurisdiction_config.level})"
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "civicos-mcp",
        "jurisdiction": _jurisdiction,
        "jurisdiction_level": _jurisdiction_config.level if _jurisdiction_config else "unknown",
        "display_name": _jurisdiction_config.display_name if _jurisdiction_config else _jurisdiction,
        "platform": "container",
        "tools_count": len(_registry) if _registry else 0,
        "tools": [name for name, _ in _registry] if _registry else [],
    }


@app.get("/registry")
async def get_registry():
    """
    CivicOS MCP Server Registry.

    Returns the official registry of CivicOS-approved MCP servers.
    Clients can use this to discover available MCP endpoints.
    """
    import datetime
    registry_path = os.path.join(os.path.dirname(__file__), "registry_data.json")
    try:
        with open(registry_path, "r") as f:
            registry_data = json.load(f)

        # Add health status for this server
        for operator in registry_data.get("operators", []):
            if operator.get("jurisdiction_id") == _jurisdiction:
                operator["health"] = {
                    "status": "healthy",
                    "tools_count": len(_registry) if _registry else 0,
                    "checked_at": datetime.datetime.utcnow().isoformat() + "Z"
                }

        return registry_data
    except FileNotFoundError:
        return {
            "version": "1.0.0",
            "operators": [],
            "error": "Registry data not found"
        }


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC endpoint for Claude.ai and ChatGPT."""
    try:
        data = await request.json()
        method = data.get("method", "")
        params = data.get("params", {})
        request_id = data.get("id", 1)

        logger.debug(f"MCP request: {method}")

        if method == "initialize":
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "CivicOS MCP Server",
                        "version": "1.0.0",
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False},
                    },
                },
                "id": request_id,
            })

        elif method == "tools/list":
            # Include both v1 tools and v2 verbs
            v2_tools = _get_v2_tool_definitions()
            all_tools = _registry.list_tools() + v2_tools
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {"tools": all_tools},
                "id": request_id,
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            # Route v2 verbs to async handlers
            if tool_name.startswith("civic_"):
                try:
                    result = await _handle_v2_tool(tool_name, tool_args)
                except Exception as e:
                    return JSONResponse({
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": str(e)},
                        "id": request_id,
                    })

                result_text = json.dumps(result, indent=2, default=str)
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                    "id": request_id,
                })

            try:
                result = _registry.call_tool(tool_name, tool_args)
            except ValueError as e:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": str(e)},
                    "id": request_id,
                })

            # Format result for MCP
            if isinstance(result, dict):
                result_text = json.dumps(result, indent=2, default=str)
            elif isinstance(result, list):
                result_text = "\n\n".join(str(item) for item in result[:20])
            else:
                result_text = str(result)

            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
                "id": request_id,
            })

        elif method == "resources/list":
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {
                    "resources": [
                        {
                            "uri": f"civicos://{_jurisdiction}/meetings",
                            "name": "Upcoming Meetings",
                            "description": "City council meetings and agendas",
                        },
                        {
                            "uri": f"civicos://{_jurisdiction}/decisions",
                            "name": "Recent Decisions",
                            "description": "Recent council decisions and outcomes",
                        },
                    ]
                },
                "id": request_id,
            })

        elif method == "prompts/list":
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {
                    "prompts": [
                        {
                            "name": "research_topic",
                            "description": "Research a civic topic thoroughly",
                            "arguments": [
                                {"name": "topic", "description": "The topic to research", "required": True}
                            ],
                        },
                        {
                            "name": "meeting_prep",
                            "description": "Prepare for an upcoming council meeting",
                            "arguments": [
                                {"name": "meeting_description", "description": "Meeting or agenda item", "required": True}
                            ],
                        },
                    ]
                },
                "id": request_id,
            })

        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id,
            })

    except Exception as e:
        import traceback
        logger.error(f"MCP endpoint error: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": str(e),
                "data": traceback.format_exc(),
            },
            "id": data.get("id", 1) if 'data' in dir() else 1,
        })


def _get_v2_tool_definitions() -> list:
    """Return MCP tool definitions for the 5 v2 verbs."""
    return [
        {
            "name": "civic_search",
            "description": "Multi-corpus civic search. Searches across decisions, legislation, testimony, issues, budget, meetings, and more with server-side composition and ranking.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "corpus": {"type": "array", "items": {"type": "string"}, "description": "Corpus types to search: decisions, testimony, testimony:public, legislation, issues, budget, meetings, municipal_code, packets, rules, orders"},
                    "jurisdiction": {"type": "string", "description": "Jurisdiction filter (e.g., city-san-rafael)"},
                    "since": {"type": "string", "description": "Date range start (ISO format)"},
                    "until": {"type": "string", "description": "Date range end (ISO format)"},
                    "location": {"type": "string", "description": "Geographic filter"},
                    "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
                    "depth": {"type": "string", "enum": ["minimal", "standard", "deep"], "default": "standard"},
                    "mode": {"type": "string", "enum": ["search", "aggregate", "trend", "diff", "intersect"], "description": "search (items), aggregate (counts/stats), trend (temporal), diff (new since snapshot), intersect (cross-corpus join)", "default": "search"},
                    "cursor": {"type": "string", "description": "Opaque pagination cursor from a previous response"},
                    "snapshot_date": {"type": "string", "description": "ISO date for diff mode — returns items newer than this date"},
                    "intersect_corpus": {"type": "array", "items": {"type": "string"}, "description": "For intersect mode — secondary corpora to join against"},
                },
                "required": ["query", "corpus"],
            },
        },
        {
            "name": "civic_upcoming",
            "description": "Query upcoming civic events: meetings, hearings, comment periods, elections, pending legislation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "types": {"type": "array", "items": {"type": "string"}, "description": "Event types: meetings, hearings, comment_periods, legislation, elections", "default": ["meetings"]},
                    "jurisdiction": {"type": "string"},
                    "days": {"type": "integer", "description": "Days ahead (default 14)", "default": 14},
                    "actionable_only": {"type": "boolean", "description": "Only items where participation is possible", "default": False},
                },
            },
        },
        {
            "name": "civic_context",
            "description": "Get comprehensive context for a civic item using its ref, OR look up a civic term/concept (e.g., 'conditional use permit'). Provide ref OR concept, not both.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Opaque item reference from search/upcoming results"},
                    "concept": {"type": "string", "description": "Civic term to look up (e.g., 'conditional use permit', 'ADU', 'variance')"},
                    "depth": {"type": "string", "enum": ["minimal", "standard", "deep"], "default": "standard"},
                    "sections": {"type": "array", "items": {"type": "string"}, "description": "Sections to include (omit for all): history, regulatory, financial, testimony, participation"},
                },
            },
        },
        {
            "name": "civic_act",
            "description": "Execute civic participation actions: prepare_comment, comment_template, comment_guidelines, prepare_meeting, prepare_voice, broadcast_voice, prepare_initiative, broadcast_initiative, subscribe.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action name"},
                    "ref": {"type": "string", "description": "Item reference for context-dependent actions"},
                    "params": {"type": "object", "description": "Action-specific parameters"},
                },
                "required": ["action"],
            },
        },
        {
            "name": "civic_explore",
            "description": "Discover available jurisdictions, corpora, corpus schemas, actions, and capabilities. Use this first to understand what data is available.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "what": {"type": "string", "description": "What to explore: jurisdictions, corpora, corpus_schema:{name}, actions, capabilities, schema_version"},
                    "jurisdiction": {"type": "string"},
                },
                "required": ["what"],
            },
        },
    ]


async def _handle_v2_tool(tool_name: str, args: dict) -> dict:
    """Handle a v2 MCP tool call by routing to verb implementations."""
    from civicos_services.query.models import (
        SearchRequest,
        UpcomingRequest,
        ContextRequest,
        ActRequest,
        ExploreRequest,
    )
    from civicos_services.query.verbs import (
        execute_search,
        execute_upcoming,
        execute_context,
        execute_act,
        execute_explore,
    )

    if tool_name == "civic_search":
        req = SearchRequest(**args)
        resp = await execute_search(req, _civic, _jurisdiction)
    elif tool_name == "civic_upcoming":
        req = UpcomingRequest(**args)
        resp = await execute_upcoming(req, _civic, _jurisdiction)
    elif tool_name == "civic_context":
        req = ContextRequest(**args)
        resp = await execute_context(req, _civic, _jurisdiction)
    elif tool_name == "civic_act":
        req = ActRequest(**args)

        def call_handler(name, handler_args):
            return _registry.call_tool(name, handler_args)

        resp = await execute_act(req, _civic, _jurisdiction, call_handler)
    elif tool_name == "civic_explore":
        req = ExploreRequest(**args)
        resp = await execute_explore(req, _civic, _jurisdiction)
    else:
        raise ValueError(f"Unknown v2 tool: {tool_name}")

    return resp.model_dump(mode="json")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
