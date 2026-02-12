"""
REST API endpoints for CivicOS tools.

Exposes MCP tools as REST endpoints with proper OpenAPI documentation.
This enables Open WebUI integration via OpenAPI mode (bypassing buggy MCP support).

Usage:
    These endpoints are mounted alongside the MCP endpoint in modal_mcp.py.
    Open WebUI can import tools via the /openapi.json spec.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field
import json


# ─────────── Request/Response Models ───────────
# Pydantic models for FastAPI request validation and OpenAPI generation


class CityPulseRequest(BaseModel):
    """Request for city_pulse tool."""
    days_ahead: int = Field(default=7, description="Days to look ahead for upcoming meetings")
    days_back: int = Field(default=30, description="Days to look back for recent decisions")


class SearchMeetingHistoryRequest(BaseModel):
    """Request for search_meeting_history tool."""
    query: str = Field(..., description="Search query (e.g., 'homeless shelter', 'bike lane')")
    include_transcripts: bool = Field(default=True, description="Include video transcript excerpts")
    limit: int = Field(default=10, description="Maximum results per category")


class GetUpcomingMeetingsRequest(BaseModel):
    """Request for get_upcoming_meetings tool."""
    days: int = Field(default=30, description="Days to look ahead")


class FindSimilarIssuesRequest(BaseModel):
    """Request for find_similar_issues tool."""
    topic: str = Field(..., description="Topic to search (e.g., 'traffic safety', 'pothole')")
    semantic: bool = Field(default=True, description="Use semantic matching")
    limit: int = Field(default=20, description="Maximum results")


class SearchRegulatoryStackRequest(BaseModel):
    """Request for search_regulatory_stack tool."""
    topic: str = Field(..., description="Topic to search (e.g., 'accessory dwelling units')")
    jurisdiction: str = Field(default="san-rafael")


class ComposePublicCommentRequest(BaseModel):
    """Request for compose_public_comment tool."""
    item_title: str = Field(..., description="Title/description of the agenda item")
    topic: Optional[str] = Field(default=None, description="Optional topic for finding related context")


class GetPublicTestimonyRequest(BaseModel):
    """Request for get_public_testimony tool."""
    topic: str = Field(..., description="Topic to search")
    limit: int = Field(default=5, description="Maximum excerpts to return")


class SearchAgendaPacketsRequest(BaseModel):
    """Request for search_agenda_packets tool."""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, description="Maximum results")


class SearchBudgetRequest(BaseModel):
    """Request for search_budget tool."""
    query: Optional[str] = Field(default=None, description="Department or category to search")
    fiscal_year: Optional[str] = Field(default=None, description="Filter by fiscal year (e.g., 'FY25-26')")


class GeoSearchIssuesRequest(BaseModel):
    """Request for geo_search_issues tool."""
    area: str = Field(..., description="Street name, corridor, or neighborhood")
    radius_blocks: int = Field(default=2, description="Search radius in blocks")
    issue_types: Optional[list[str]] = Field(default=None, description="Filter by issue types")


class NeighborhoodReportRequest(BaseModel):
    """Request for neighborhood_report tool."""
    neighborhood: str = Field(..., description="Neighborhood name or area")


class GetDecisionContextRequest(BaseModel):
    """Request for get_decision_context tool."""
    query: str = Field(..., description="Search query")
    limit: int = Field(default=5, description="Maximum results")


class DecisionDetailRequest(BaseModel):
    """Request for decision_detail tool."""
    title: str = Field(..., description="Decision title to look up")


class GetItemContextRequest(BaseModel):
    """Request for get_item_context tool."""
    item_type: str = Field(..., description="Item type: agenda_item, decision, issue, legislation, meeting, or initiative")
    item_id: str = Field(..., description="Item ID (UUID or bill number)")
    depth: str = Field(default="standard", description="Context depth: minimal, standard, or deep")
    sections: Optional[str] = Field(default=None, description="Comma-separated sections (omit for all). Valid: history, regulatory, community, financial, testimony, participation")


class CommentSynthesisRequest(BaseModel):
    """Request for comment-synthesis endpoint."""
    entity_id: str = Field(..., description="Entity ID to get comment synthesis for (e.g., 'agenda-item:123')")


class ToolResponse(BaseModel):
    """Standard response for all tool endpoints."""
    success: bool = True
    data: Any = Field(..., description="Tool response data")
    error: Optional[str] = Field(default=None, description="Error message if success=False")


# ─────────── REST Endpoints ───────────

def create_rest_router(registry, civic, jurisdiction, validate_input, logger):
    """
    Create a FastAPI router with REST endpoints for all tools.

    Args:
        registry: ToolRegistry instance with bound handlers
        civic: CivicOS instance
        jurisdiction: Jurisdiction string
        validate_input: Input validation function
        logger: Logger instance

    Returns:
        FastAPI APIRouter
    """
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/api/tools", tags=["Civic Tools"])

    def call_tool_safe(name: str, args: dict) -> dict:
        """Call a tool and return parsed JSON response."""
        try:
            result = registry.call_tool(name, args)
            # Result is already JSON string from handler wrapper
            if isinstance(result, str):
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
                    return {"text": result}
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Tool {name} error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/city-pulse", response_model=ToolResponse,
                 summary="Get structured city data",
                 description="Get structured city activity data (meetings, decisions, community issues) as JSON. Returns raw data suitable for analysis or display. Use when you need specific counts, dates, or structured information about civic activity.")
    async def city_pulse(request: CityPulseRequest):
        data = call_tool_safe("city_pulse", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/search-meeting-history", response_model=ToolResponse,
                 summary="Search meeting history",
                 description="Search past city council meetings and decisions on a topic.")
    async def search_meeting_history(request: SearchMeetingHistoryRequest):
        data = call_tool_safe("search_meeting_history", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/get-upcoming-meetings", response_model=ToolResponse,
                 summary="Get upcoming meetings",
                 description="Get upcoming city council meetings and agenda items.")
    async def get_upcoming_meetings(request: GetUpcomingMeetingsRequest):
        data = call_tool_safe("get_upcoming_meetings", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/find-similar-issues", response_model=ToolResponse,
                 summary="Find similar community issues",
                 description="Find community issues related to a topic via 311/SeeClickFix.")
    async def find_similar_issues(request: FindSimilarIssuesRequest):
        data = call_tool_safe("find_similar_issues", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/search-regulatory-stack", response_model=ToolResponse,
                 summary="Search regulatory stack",
                 description="Search relevant laws and regulations across local, state, and federal levels.")
    async def search_regulatory_stack(request: SearchRegulatoryStackRequest):
        data = call_tool_safe("search_regulatory_stack", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/compose-public-comment", response_model=ToolResponse,
                 summary="Get context for public comment",
                 description="Get context for writing a public comment on a civic agenda item.")
    async def compose_public_comment(request: ComposePublicCommentRequest):
        data = call_tool_safe("compose_public_comment", request.model_dump(exclude_none=True))
        return ToolResponse(data=data)

    @router.post("/get-public-testimony", response_model=ToolResponse,
                 summary="Get public testimony",
                 description="Get public testimony excerpts on a topic from meeting transcripts.")
    async def get_public_testimony(request: GetPublicTestimonyRequest):
        data = call_tool_safe("get_public_testimony", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/search-agenda-packets", response_model=ToolResponse,
                 summary="Search agenda packets",
                 description="Search agenda packets and staff reports.")
    async def search_agenda_packets(request: SearchAgendaPacketsRequest):
        data = call_tool_safe("search_agenda_packets", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/search-budget", response_model=ToolResponse,
                 summary="Search city budget",
                 description="Search city budget data by department or category.")
    async def search_budget(request: SearchBudgetRequest):
        data = call_tool_safe("search_budget", request.model_dump(exclude_none=True))
        return ToolResponse(data=data)

    @router.post("/geo-search-issues", response_model=ToolResponse,
                 summary="Geographic issue search",
                 description="Search 311 issues by geographic area (street, neighborhood).")
    async def geo_search_issues(request: GeoSearchIssuesRequest):
        data = call_tool_safe("geo_search_issues", request.model_dump(exclude_none=True))
        return ToolResponse(data=data)

    @router.post("/neighborhood-report", response_model=ToolResponse,
                 summary="Generate neighborhood report",
                 description="Generate a comprehensive report for a neighborhood.")
    async def neighborhood_report(request: NeighborhoodReportRequest):
        data = call_tool_safe("neighborhood_report", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/get-decision-context", response_model=ToolResponse,
                 summary="Get decision context",
                 description="Get decisions with linked transcript excerpts showing what was discussed.")
    async def get_decision_context(request: GetDecisionContextRequest):
        data = call_tool_safe("get_decision_context", request.model_dump())
        return ToolResponse(data=data)

    @router.post("/decision-detail", response_model=ToolResponse,
                 summary="Get decision detail",
                 description="Get structured detail for a specific decision including testimony and related decisions. For dashboard expansion.")
    async def decision_detail(request: DecisionDetailRequest):
        data = call_tool_safe("decision_detail", request.model_dump())
        return ToolResponse(data=data)

    @router.get("/get-started", response_model=ToolResponse,
                summary="Welcome overview for new users",
                description="Get a friendly welcome overview for new users. Returns formatted text with upcoming meetings, recent decisions, and suggestions for what to explore. Use when users first arrive or ask general questions like 'what can you help with?' or 'what's going on?'")
    async def get_started():
        data = call_tool_safe("get_started", {})
        return ToolResponse(data=data)

    @router.get("/get-comment-guidelines", response_model=ToolResponse,
                summary="Get comment guidelines",
                description="Get public comment guidelines and submission information.")
    async def get_comment_guidelines(jurisdiction: str = "san-rafael"):
        data = call_tool_safe("get_comment_guidelines", {"jurisdiction": jurisdiction})
        return ToolResponse(data=data)

    @router.get("/issue-geography", response_model=ToolResponse,
                summary="Get issue locations for map",
                description="Get 311 issues with latitude/longitude for geographic visualization.")
    async def issue_geography(limit: int = 2000):
        try:
            issues = civic._storage.get_issues(
                jurisdiction_id=jurisdiction, limit=limit
            )
            points = []
            for i in issues:
                lat = i.get('latitude')
                lng = i.get('longitude')
                if lat and lng:
                    points.append({
                        "lat": float(lat),
                        "lng": float(lng),
                        "type": i.get('issue_type', 'other'),
                        "status": i.get('status', 'open'),
                        "address": i.get('address', ''),
                        "created_at": i.get('created_at', ''),
                    })
            return ToolResponse(data={
                "points": points,
                "total": len(points),
            })
        except Exception as e:
            logger.error(f"Error in issue_geography: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/budget-summary", response_model=ToolResponse,
                summary="Budget allocation summary",
                description="Budget items grouped by department/fund/program with dollar amounts and percentages.")
    async def budget_summary(group_by: str = "department", fiscal_year: Optional[str] = None):
        try:
            # Auto-detect latest fiscal year if not specified
            if not fiscal_year:
                items = civic._storage.get_budget_items(jurisdiction)
                years = sorted(set(i.get("fiscal_year") for i in items if i.get("fiscal_year")), reverse=True)
                fiscal_year = years[0] if years else "2025-2026"

            rows = civic._storage.get_budget_summary(
                jurisdiction_id=jurisdiction,
                fiscal_year=fiscal_year,
                group_by=group_by,
            )
            total_cents = sum(int(r.get("budgeted_cents", 0) or 0) for r in rows)
            categories = []
            for r in rows:
                budgeted_cents = int(r.get("budgeted_cents", 0) or 0)
                categories.append({
                    "category": r.get(group_by) or "Other",
                    "budgeted_dollars": budgeted_cents / 100,
                    "percentage": round(float(budgeted_cents) / total_cents * 100, 1) if total_cents else 0,
                    "item_count": int(r.get("item_count", 0)),
                })
            return ToolResponse(data={
                "categories": categories,
                "total_budgeted_dollars": total_cents / 100,
                "fiscal_year": fiscal_year,
                "group_by": group_by,
            })
        except Exception as e:
            logger.error(f"Error in budget_summary: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/data-provenance", response_model=ToolResponse,
                summary="Data provenance info",
                description="Data source transparency: jurisdiction, corpus coverage, data freshness, and endpoint URLs.")
    async def data_provenance():
        try:
            from civicos.diagnostics import DataStatus
            from civicos.registry import get_relay_url, get_jurisdiction_url

            status = DataStatus(civic._storage, civic._vectors, jurisdiction)
            report = status.summary()

            # Build corpus summary
            corpora = []
            for key, c in report.corpus_counts.items():
                corpora.append({
                    "corpus_type": c.corpus_type,
                    "display_name": c.display_name,
                    "storage_count": c.storage_count,
                    "vector_count": c.vector_count,
                    "coverage_percent": round(c.coverage_percent, 1) if c.coverage_percent is not None else None,
                    "last_indexed": c.last_indexed.isoformat() if c.last_indexed else None,
                })

            # Storage stats for freshness
            freshness = {}
            if report.storage_stats:
                s = report.storage_stats
                freshness = {
                    "earliest_meeting": s.earliest_meeting.isoformat() if s.earliest_meeting else None,
                    "latest_meeting": s.latest_meeting.isoformat() if s.latest_meeting else None,
                    "last_updated": s.last_updated.isoformat() if s.last_updated else None,
                }

            return ToolResponse(data={
                "jurisdiction": jurisdiction,
                "mcp_endpoint": get_jurisdiction_url(jurisdiction),
                "relay_url": get_relay_url(),
                "storage_backend": type(civic._storage).__name__,
                "total_storage_docs": report.total_storage_docs,
                "total_vector_docs": report.total_vector_docs,
                "overall_coverage_percent": round(report.overall_coverage_percent, 1) if report.overall_coverage_percent is not None else None,
                "corpora": corpora,
                "freshness": freshness,
                "generated_at": report.timestamp.isoformat(),
            })
        except Exception as e:
            logger.error(f"Error in data_provenance: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/get-item-context", response_model=ToolResponse,
                 summary="Get comprehensive context for a civic item",
                 description="Assemble history, regulatory, community, financial, testimony, and participation context for any civic item. Returns a structured bundle suitable for LLM conversations.")
    async def get_item_context(request: GetItemContextRequest):
        from civicos_services.context import (
            assemble_context,
            ItemNotFoundError,
            RelayUnavailableError,
            ItemType,
            ContextDepth,
        )

        # Validate item_type
        try:
            item_type = ItemType(request.item_type)
        except ValueError:
            valid = ", ".join(t.value for t in ItemType)
            raise HTTPException(status_code=422, detail=f"Invalid item_type '{request.item_type}'. Valid: {valid}")

        # Parse depth
        try:
            depth = ContextDepth(request.depth)
        except ValueError:
            depth = ContextDepth.standard

        # Parse sections
        sections = None
        if request.sections:
            sections = set(s.strip() for s in request.sections.split(",") if s.strip())

        try:
            bundle = await assemble_context(
                item_type=item_type,
                item_id=request.item_id,
                jurisdiction=jurisdiction,
                sections=sections,
                depth=depth,
            )
            return ToolResponse(data=bundle.model_dump(mode="json"))
        except ItemNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Item not found: {e.item_type}/{e.item_id}")
        except Exception as e:
            logger.error(f"Context assembly error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/comment-synthesis", response_model=ToolResponse,
                  summary="Comment synthesis for an entity",
                  description="Aggregate public comments for an entity: total count, stance breakdown, and comment texts. No LLM — pure data aggregation for edge AI synthesis.")
    async def comment_synthesis(request: CommentSynthesisRequest):
        import httpx
        import os

        from civicos.registry import get_relay_url
        relay_url = os.environ.get("CIVICOS_RELAY_URL") or os.environ.get("CIVICOS_API_URL") or get_relay_url()
        relay_url = relay_url.rstrip("/")
        entity_id = request.entity_id

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{relay_url}/coordination/comments/{entity_id}"
                )
                response.raise_for_status()
                comments = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch comments from relay: {e}")
            raise HTTPException(status_code=502, detail=f"Relay unavailable: {e}")

        # Aggregate stance counts
        support = 0
        oppose = 0
        neutral = 0
        for c in comments:
            stance = (c.get("stance") or "").lower()
            if stance == "support":
                support += 1
            elif stance == "oppose":
                oppose += 1
            else:
                neutral += 1

        # Build comment summaries (newest first, already sorted by relay)
        comment_entries = []
        for c in comments:
            comment_entries.append({
                "text": c.get("comment_text", ""),
                "stance": c.get("stance") or "neutral",
                "timestamp": c.get("timestamp", ""),
                "author_short": (c.get("public_key") or "")[:8],
            })

        return ToolResponse(data={
            "entity_id": entity_id,
            "total": len(comments),
            "support": support,
            "oppose": oppose,
            "neutral": neutral,
            "comments": comment_entries,
        })

    return router
