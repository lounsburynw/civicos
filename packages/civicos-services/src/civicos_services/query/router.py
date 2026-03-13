"""
v2 Router — registers all 5 verbs at /api/v2/civic/{verb}.

Handles API key auth and rate limiting.
Multi-corpus queries charge N query units (1 per corpus searched).
v1 tools remain fully functional — v2 is purely additive.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def create_v2_router(civic, jurisdiction: str, registry=None, logger_override=None):
    """
    Create a FastAPI router for the v2 query interface.

    Args:
        civic: CivicOS instance
        jurisdiction: Default jurisdiction string
        registry: Optional ToolRegistry for civic.act handler delegation
        logger_override: Optional logger

    Returns:
        FastAPI APIRouter with all 5 verb endpoints
    """
    from fastapi import APIRouter, Depends, Request

    log = logger_override or logger

    router = APIRouter(
        prefix="/api/v2/civic",
        tags=["Civic v2"],
    )

    # Auth middleware is required — fail fast if missing
    _charge_query_units = None
    try:
        from api_key_middleware import require_api_key_or_rate_limit, charge_query_units
        router.dependencies = [Depends(require_api_key_or_rate_limit)]
        _charge_query_units = charge_query_units
    except ImportError:
        # In test environments, auth middleware may not be on sys.path.
        # In production (Modal/container), it must be available.
        import os
        if os.getenv("CIVICOS_DEV_MODE") or os.getenv("PYTEST_CURRENT_TEST"):
            log.warning("api_key_middleware not available (dev/test mode), v2 endpoints unauthenticated")
        else:
            raise RuntimeError(
                "api_key_middleware is required for v2 endpoints. "
                "Ensure apps/civicos-mcp is on sys.path."
            )

    from civicos_services.query.models import (
        SearchRequest,
        SearchResponse,
        UpcomingRequest,
        UpcomingResponse,
        ContextRequest,
        ContextResponse,
        ActRequest,
        ActResponse,
        ExploreRequest,
        ExploreResponse,
    )
    from civicos_services.query.verbs import (
        execute_search,
        execute_upcoming,
        execute_context,
        execute_act,
        execute_explore,
    )

    @router.post(
        "/search",
        response_model=SearchResponse,
        summary="Multi-corpus civic search",
        description="Search across civic data corpora with server-side composition and ranking. "
                    "Query cost: 1 unit per corpus searched.",
    )
    async def civic_search(body: SearchRequest, request: Request):
        # Charge extra query units for multi-corpus searches (middleware already charged 1)
        extra = len(body.corpus) - 1
        if extra > 0 and _charge_query_units:
            _charge_query_units(request, extra)
        return await execute_search(body, civic, jurisdiction)

    @router.post(
        "/upcoming",
        response_model=UpcomingResponse,
        summary="Upcoming civic events",
        description="Query upcoming meetings, hearings, comment periods, and elections.",
    )
    async def civic_upcoming(body: UpcomingRequest):
        return await execute_upcoming(body, civic, jurisdiction)

    @router.post(
        "/context",
        response_model=ContextResponse,
        summary="Deep item context",
        description="Get comprehensive context for a civic item using its ref.",
    )
    async def civic_context(body: ContextRequest):
        return await execute_context(body, civic, jurisdiction)

    @router.post(
        "/act",
        response_model=ActResponse,
        summary="Participation actions",
        description="Execute civic participation actions (comment, voice, initiative).",
    )
    async def civic_act(body: ActRequest):
        def call_handler(name: str, args: dict):
            if registry is not None:
                return registry.call_tool(name, args)
            raise ValueError(f"No handler registry available for action: {name}")

        return await execute_act(body, civic, jurisdiction, call_handler)

    @router.post(
        "/explore",
        response_model=ExploreResponse,
        summary="Discover capabilities",
        description="Explore available jurisdictions, corpora, schemas, actions, and capabilities.",
    )
    async def civic_explore(body: ExploreRequest):
        return await execute_explore(body, civic, jurisdiction)

    return router
