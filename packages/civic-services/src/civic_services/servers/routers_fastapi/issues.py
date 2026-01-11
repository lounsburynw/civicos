"""
Issues router: user issues/complaints, search, and related endpoints.

Endpoints:
- GET /issues - List user's issues
- GET /issues/search - Search issues with filters
- GET /issues/{issue_id} - Get single issue
- GET /issues/{issue_id}/timeline - Get issue timeline
- GET /issues/{issue_id}/status-history - Get issue status history
- POST /issues - File a new issue
- POST /issues/{issue_id}/link-events - Link events to issue
- PUT /issues/{issue_id}/status - Update issue status
- GET /operational-issues/{jurisdiction_id} - Get operational issues (SeeClickFix)
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Issue(BaseModel):
    """Issue/complaint response."""
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    jurisdiction_id: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    linked_events: Optional[List[str]] = None

    class Config:
        extra = "allow"


class IssueSearchResponse(BaseModel):
    """Issue search results."""
    issues: List[Dict[str, Any]]
    count: int
    query: Dict[str, Any]
    filters_applied: Dict[str, Any]


class IssueCreateRequest(BaseModel):
    """Request to create a new issue."""
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    jurisdiction_id: Optional[str] = None
    location: Optional[Dict[str, Any]] = None


class IssueStatusUpdate(BaseModel):
    """Request to update issue status."""
    status: str
    reason: Optional[str] = None


class LinkEventsRequest(BaseModel):
    """Request to link events to an issue."""
    event_ids: List[str]


# === Auth Dependency ===

from .dependencies import verify_auth


# === Storage Helper ===

def get_issue_storage():
    """Get issue storage instance."""
    try:
        from civic_services.storage.issue_storage import IssueStorage
        return IssueStorage()
    except ImportError:
        return None


# === Endpoints ===

@router.get("/issues")
async def list_issues(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    ownership: Optional[str] = Query("mine", description="mine/following/all"),
    status: Optional[str] = Query("all", description="open/closed/matched/all"),
    token: str = Depends(verify_auth)
):
    """
    List issues for a user.

    - ownership=mine: Issues filed by the user
    - ownership=following: Issues the user is following
    - ownership=all: Both

    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            return {"issues": [], "count": 0, "error": "Issue storage not available"}

        # Use token as user_id if not specified
        target_user_id = user_id or token

        # Get user's issues
        issues = storage.get_issues_for_user(target_user_id)

        # Filter by ownership
        if ownership == "mine":
            issues = [i for i in issues if i.get("user_id") == target_user_id]
        elif ownership == "following":
            # Get followed issues
            following_ids = storage.get_followed_issue_ids(target_user_id)
            issues = [i for i in issues if i.get("id") in following_ids]
        # else: "all" - no filter

        # Filter by status
        if status != "all":
            if status == "open":
                issues = [i for i in issues if i.get("status") not in ("closed", "resolved")]
            elif status == "closed":
                issues = [i for i in issues if i.get("status") in ("closed", "resolved")]
            elif status == "matched":
                issues = [i for i in issues if i.get("linked_events")]

        return {
            "issues": issues,
            "count": len(issues)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/issues/search", response_model=IssueSearchResponse)
async def search_issues(
    user_id: str = Query(..., description="User ID (required)"),
    ownership: Optional[str] = Query("mine", description="mine/following/all"),
    status: Optional[str] = Query("all", description="open/closed/matched/all"),
    category: Optional[str] = Query(None, description="Issue category filter"),
    jurisdiction: Optional[str] = Query(None, description="Jurisdiction filter"),
    q: Optional[str] = Query(None, description="Text search query"),
    token: str = Depends(verify_auth)
):
    """
    Search issues with filtering.

    Mirrors /api/events/search pattern for consistency.

    Query params:
    - user_id: required - whose issues to search
    - ownership: mine/following/all
    - status: open/closed/matched/all
    - category: issue_type filter
    - jurisdiction: city filter
    - q: text search

    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            return {
                "issues": [],
                "count": 0,
                "query": {"user_id": user_id},
                "filters_applied": {},
                "error": "Issue storage not available"
            }

        # Get user's issues
        issues = storage.get_issues_for_user(user_id)

        filters_applied = {}

        # Filter by ownership
        if ownership == "mine":
            issues = [i for i in issues if i.get("user_id") == user_id]
            filters_applied["ownership"] = "mine"
        elif ownership == "following":
            following_ids = storage.get_followed_issue_ids(user_id)
            issues = [i for i in issues if i.get("id") in following_ids]
            filters_applied["ownership"] = "following"

        # Filter by status
        if status != "all":
            if status == "open":
                issues = [i for i in issues if i.get("status") not in ("closed", "resolved")]
            elif status == "closed":
                issues = [i for i in issues if i.get("status") in ("closed", "resolved")]
            elif status == "matched":
                issues = [i for i in issues if i.get("linked_events")]
            filters_applied["status"] = status

        # Filter by category
        if category:
            issues = [i for i in issues if i.get("category") == category or i.get("issue_type") == category]
            filters_applied["category"] = category

        # Filter by jurisdiction
        if jurisdiction:
            issues = [i for i in issues if i.get("jurisdiction_id") == jurisdiction]
            filters_applied["jurisdiction"] = jurisdiction

        # Text search
        if q:
            q_lower = q.lower()
            issues = [
                i for i in issues
                if q_lower in (i.get("title") or "").lower()
                or q_lower in (i.get("description") or "").lower()
                or q_lower in (i.get("address") or "").lower()
            ]
            filters_applied["q"] = q

        return {
            "issues": issues,
            "count": len(issues),
            "query": {
                "user_id": user_id,
                "ownership": ownership,
                "status": status,
                "category": category,
                "jurisdiction": jurisdiction,
                "q": q
            },
            "filters_applied": filters_applied
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/issues/{issue_id}")
async def get_issue(
    issue_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get a single issue by ID.

    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Issue storage not available")

        issue = storage.get_issue(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue not found: {issue_id}")

        return issue

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/issues/{issue_id}/timeline")
async def get_issue_timeline(
    issue_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get timeline of events related to an issue.

    Returns chronological list of updates, linked events, and status changes.
    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Issue storage not available")

        issue = storage.get_issue(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue not found: {issue_id}")

        # Build timeline from issue history
        timeline = []

        # Add creation event
        timeline.append({
            "type": "created",
            "timestamp": issue.get("created_at"),
            "description": f"Issue created: {issue.get('title')}"
        })

        # Add status changes from history if available
        status_history = issue.get("status_history", [])
        for entry in status_history:
            timeline.append({
                "type": "status_change",
                "timestamp": entry.get("timestamp"),
                "description": f"Status changed to: {entry.get('status')}",
                "from_status": entry.get("from_status"),
                "to_status": entry.get("status"),
                "reason": entry.get("reason")
            })

        # Add linked events
        linked_events = issue.get("linked_events", [])
        for event_id in linked_events:
            timeline.append({
                "type": "event_linked",
                "event_id": event_id,
                "description": f"Linked to event: {event_id}"
            })

        # Sort by timestamp
        timeline.sort(key=lambda x: x.get("timestamp") or "")

        return {
            "issue_id": issue_id,
            "timeline": timeline
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/issues/{issue_id}/status-history")
async def get_issue_status_history(
    issue_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get status change history for an issue.

    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Issue storage not available")

        issue = storage.get_issue(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue not found: {issue_id}")

        return {
            "issue_id": issue_id,
            "current_status": issue.get("status"),
            "history": issue.get("status_history", [])
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/issues")
async def create_issue(
    request: IssueCreateRequest,
    token: str = Depends(verify_auth)
):
    """
    Create a new issue/complaint.

    Requires authentication. The authenticated user becomes the issue owner.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Issue storage not available")

        # Create issue
        issue = storage.create_issue(
            user_id=token,
            title=request.title,
            description=request.description,
            category=request.category,
            jurisdiction_id=request.jurisdiction_id,
            location=request.location
        )

        return {
            "success": True,
            "issue": issue
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/issues/{issue_id}/link-events")
async def link_events_to_issue(
    issue_id: str,
    request: LinkEventsRequest,
    token: str = Depends(verify_auth)
):
    """
    Link events to an issue.

    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Issue storage not available")

        issue = storage.get_issue(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue not found: {issue_id}")

        # Link events
        linked = storage.link_events(issue_id, request.event_ids)

        return {
            "success": True,
            "issue_id": issue_id,
            "linked_events": linked
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.put("/issues/{issue_id}/status")
async def update_issue_status(
    issue_id: str,
    request: IssueStatusUpdate,
    token: str = Depends(verify_auth)
):
    """
    Update issue status.

    Requires authentication.
    """
    try:
        storage = get_issue_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Issue storage not available")

        issue = storage.get_issue(issue_id)
        if not issue:
            raise HTTPException(status_code=404, detail=f"Issue not found: {issue_id}")

        # Update status
        updated = storage.update_status(
            issue_id=issue_id,
            new_status=request.status,
            reason=request.reason,
            updated_by=token
        )

        return {
            "success": True,
            "issue": updated
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/operational-issues/{jurisdiction_id}")
async def get_operational_issues(
    jurisdiction_id: str,
    limit: int = Query(50, description="Maximum issues to return"),
    status: Optional[str] = Query(None, description="Filter by status"),
    token: str = Depends(verify_auth)
):
    """
    Get operational issues (SeeClickFix complaints) for a jurisdiction.

    These are community-reported infrastructure issues from external sources.
    Requires authentication.
    """
    try:
        # Try to load SeeClickFix data
        try:
            from civic_services.clients.seeclickfix_client import SeeClickFixClient
            client = SeeClickFixClient()
            issues = client.get_issues(jurisdiction_id, limit=limit, status=status)
        except ImportError:
            issues = []

        return {
            "jurisdiction_id": jurisdiction_id,
            "issues": issues,
            "count": len(issues),
            "source": "seeclickfix"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
