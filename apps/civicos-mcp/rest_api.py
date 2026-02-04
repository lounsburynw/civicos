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
                 summary="Get city pulse snapshot",
                 description="Get a comprehensive snapshot of city activity including upcoming meetings, recent decisions, and trending issues.")
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

    @router.get("/get-started", response_model=ToolResponse,
                summary="Get started",
                description="Get an overview of what's happening in local government.")
    async def get_started():
        data = call_tool_safe("get_started", {})
        return ToolResponse(data=data)

    @router.get("/get-comment-guidelines", response_model=ToolResponse,
                summary="Get comment guidelines",
                description="Get public comment guidelines and submission information.")
    async def get_comment_guidelines(jurisdiction: str = "san-rafael"):
        data = call_tool_safe("get_comment_guidelines", {"jurisdiction": jurisdiction})
        return ToolResponse(data=data)

    return router
