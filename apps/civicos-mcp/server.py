"""
CivicOS MCP Server - Container Entry Point

This is the entry point for Docker/container deployments.
For Modal deployment, use modal_app.py instead.

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8080

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
_validate_input = None


@app.on_event("startup")
async def startup():
    """Initialize CivicOS and tool registry on startup."""
    global _civic, _registry, _jurisdiction, _validate_input
    import time

    logger.info("Initializing CivicOS MCP Server...")

    from civicos import CivicOS
    from tools.registry import ToolRegistry
    from tools import handlers
    from civicos_input_validator import validate_civic_input

    _jurisdiction = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")
    _validate_input = validate_civic_input

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

    # Create tool registry and bind handlers
    _registry = ToolRegistry()

    handler_map = {
        "search_meeting_history": handlers.search_meeting_history,
        "get_upcoming_meetings": handlers.get_upcoming_meetings,
        "find_similar_issues": handlers.find_similar_issues,
        "search_regulatory_stack": handlers.search_regulatory_stack,
        "compose_public_comment": handlers.compose_public_comment,
        "city_pulse": handlers.city_pulse,
        "get_issue_analytics": handlers.get_issue_analytics,
        "get_issue_trends": handlers.get_issue_trends,
        "geo_search_issues": handlers.geo_search_issues,
        "search_budget": handlers.search_budget,
        "get_public_testimony": handlers.get_public_testimony,
        "search_agenda_packets": handlers.search_agenda_packets,
        "get_comment_guidelines": handlers.get_comment_guidelines,
        "get_started": handlers.get_started,
        "query_issue_data": handlers.query_issue_data,
        "get_issue_resolution_stats": handlers.get_issue_resolution_stats,
        "detect_trends": handlers.detect_trends,
        "get_issue_sample": handlers.get_issue_sample,
        "find_issues_near_address": handlers.find_issues_near_address,
        "find_repeat_issues": handlers.find_repeat_issues,
        "get_seasonal_patterns": handlers.get_seasonal_patterns,
        "compare_zip_codes": handlers.compare_zip_codes,
        "neighborhood_report": handlers.neighborhood_report,
        "get_voting_record": handlers.get_voting_record,
        "get_decision_context": handlers.get_decision_context,
        "get_funding_flow": handlers.get_funding_flow,
        "get_federal_expenditures": handlers.get_federal_expenditures,
        "get_intergovernmental_revenue": handlers.get_intergovernmental_revenue,
        "get_comment_template": handlers.get_comment_template,
        "prepare_for_meeting": handlers.prepare_for_meeting,
    }

    def wrap_handler(handler_fn):
        def wrapped(args: dict) -> str:
            result = handler_fn(_civic, _jurisdiction, _validate_input, logger, args)
            if isinstance(result, dict):
                return json.dumps(result, indent=2, default=str)
            return result
        return wrapped

    for name, handler_fn in handler_map.items():
        _registry.bind_handler(name, wrap_handler(handler_fn))

    logger.info(f"MCP Server ready with {len(_registry)} tools")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "civicos-mcp",
        "jurisdiction": _jurisdiction,
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
            return JSONResponse({
                "jsonrpc": "2.0",
                "result": {"tools": _registry.list_tools()},
                "id": request_id,
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
