"""
CivicOS Query Interface v2 — 5 semantic verbs.

Replaces 50+ individual tools with:
  civic.search   — multi-corpus search with result merging
  civic.upcoming — temporal queries (meetings, hearings, comment periods)
  civic.context  — deep context for a specific item (wraps assemble_context)
  civic.act      — participation actions (comment, voice, initiative)
  civic.explore  — discovery (jurisdictions, corpora, schemas, capabilities)
"""

from civicos_services.query.models import (
    CivicResult,
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
    ResponseMeta,
)
from civicos_services.query.router import create_v2_router

__all__ = [
    "CivicResult",
    "SearchRequest",
    "SearchResponse",
    "UpcomingRequest",
    "UpcomingResponse",
    "ContextRequest",
    "ContextResponse",
    "ActRequest",
    "ActResponse",
    "ExploreRequest",
    "ExploreResponse",
    "ResponseMeta",
    "create_v2_router",
]
