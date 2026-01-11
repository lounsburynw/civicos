"""
User router: profile, location, context, history, export.

Endpoints:
- GET /profile - Get user profile
- POST /profile - Update user profile
- GET /location - Get user location
- POST /location - Set user location
- GET /civic-history - Get user's civic history
- GET /context - Get user context for AI
- GET /export - Export user data (GDPR)
- DELETE / - Delete user account (GDPR)
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Location(BaseModel):
    """User location."""
    latitude: float
    longitude: float
    address: Optional[str] = None
    jurisdiction_id: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


class UserProfile(BaseModel):
    """User profile."""
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[Location] = None
    interests: Optional[List[str]] = None
    notification_preferences: Optional[Dict[str, bool]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    """Profile update request."""
    name: Optional[str] = None
    email: Optional[str] = None
    interests: Optional[List[str]] = None
    notification_preferences: Optional[Dict[str, bool]] = None


class LocationSetRequest(BaseModel):
    """Location set request."""
    latitude: float
    longitude: float
    address: Optional[str] = None


class CivicHistoryItem(BaseModel):
    """Single item in civic history."""
    type: str  # issue_filed, event_attended, comment_submitted, etc.
    timestamp: str
    title: str
    description: Optional[str] = None
    reference_id: Optional[str] = None


class UserExport(BaseModel):
    """User data export."""
    user_id: str
    profile: Dict[str, Any]
    issues: List[Dict[str, Any]]
    follows: List[Dict[str, Any]]
    drafts: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    exported_at: str


# === Auth Dependency ===

from .dependencies import verify_auth


# === Storage Helper ===

def get_personalization_service():
    """Get personalization service instance."""
    try:
        from civic_services.storage.personalization_service import PersonalizationService
        return PersonalizationService()
    except ImportError:
        return None


# === Endpoints ===

@router.get("/profile")
async def get_user_profile(token: str = Depends(verify_auth)):
    """
    Get current user's profile.

    Returns profile information including location and preferences.
    Requires authentication.
    """
    try:
        service = get_personalization_service()
        if not service:
            return {
                "user_id": token,
                "name": None,
                "location": None,
                "interests": [],
                "created_at": None,
                "note": "Personalization service not available"
            }

        profile = service.get_user_profile(token)

        return profile or {
            "user_id": token,
            "name": None,
            "location": None,
            "interests": [],
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/profile")
async def update_user_profile(
    request: ProfileUpdateRequest,
    token: str = Depends(verify_auth)
):
    """
    Update current user's profile.

    Requires authentication.
    """
    try:
        service = get_personalization_service()
        if not service:
            raise HTTPException(status_code=503, detail="Personalization service not available")

        updated = service.update_user_profile(
            user_id=token,
            name=request.name,
            email=request.email,
            interests=request.interests,
            notification_preferences=request.notification_preferences
        )

        return {
            "success": True,
            "profile": updated
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/location")
async def get_user_location(token: str = Depends(verify_auth)):
    """
    Get current user's location.

    Returns geocoded location with jurisdiction mapping.
    Requires authentication.
    """
    try:
        service = get_personalization_service()
        if not service:
            return {"location": None, "note": "Personalization service not available"}

        location = service.get_user_location(token)

        return {"location": location}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/location")
async def set_user_location(
    request: LocationSetRequest,
    token: str = Depends(verify_auth)
):
    """
    Set current user's location.

    Location is geocoded and mapped to nearest jurisdiction.
    Requires authentication.
    """
    try:
        service = get_personalization_service()
        if not service:
            raise HTTPException(status_code=503, detail="Personalization service not available")

        # Geocode and set location
        location = service.set_user_location(
            user_id=token,
            latitude=request.latitude,
            longitude=request.longitude,
            address=request.address
        )

        return {
            "success": True,
            "location": location
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/civic-history")
async def get_user_civic_history(
    limit: int = 50,
    token: str = Depends(verify_auth)
):
    """
    Get user's civic history.

    Returns chronological list of civic activities:
    - Issues filed
    - Events attended
    - Comments submitted
    - Votes cast

    Requires authentication.
    """
    try:
        history = []

        # Get issues filed
        try:
            from civic_services.storage.issue_storage import IssueStorage
            issue_storage = IssueStorage()
            issues = issue_storage.get_issues_for_user(token)
            for issue in issues[:limit]:
                history.append({
                    "type": "issue_filed",
                    "timestamp": issue.get("created_at"),
                    "title": issue.get("title"),
                    "description": f"Filed issue: {issue.get('title')}",
                    "reference_id": issue.get("id")
                })
        except ImportError:
            pass

        # Get drafts submitted
        try:
            from civic_services.storage.draft_storage import DraftStorage
            draft_storage = DraftStorage()
            drafts = draft_storage.get_user_drafts(token, status="submitted")
            for draft in drafts[:limit]:
                history.append({
                    "type": "comment_submitted",
                    "timestamp": draft.get("submitted_at"),
                    "title": f"Comment on: {draft.get('event_title', 'Unknown')}",
                    "description": draft.get("content", "")[:100],
                    "reference_id": draft.get("id")
                })
        except ImportError:
            pass

        # Get follows
        try:
            from civic_services.storage.follow_storage import FollowStorage
            follow_storage = FollowStorage()
            follows = follow_storage.get_follows_for_user(token)
            for follow in follows[:limit]:
                history.append({
                    "type": "follow_created",
                    "timestamp": follow.get("created_at"),
                    "title": f"Following: {follow.get('focal_title', 'Unknown')}",
                    "description": f"Started following {follow.get('focal_type')}: {follow.get('focal_id')}",
                    "reference_id": follow.get("id")
                })
        except ImportError:
            pass

        # Sort by timestamp (most recent first)
        history.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        return {
            "user_id": token,
            "history": history[:limit],
            "count": len(history[:limit])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/context")
async def get_user_context(token: str = Depends(verify_auth)):
    """
    Get user context for AI conversations.

    Returns structured context including:
    - User preferences
    - Location and jurisdiction
    - Recent activity
    - Followed topics

    Requires authentication.
    """
    try:
        context = {
            "user_id": token,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        # Get profile
        service = get_personalization_service()
        if service:
            profile = service.get_user_profile(token)
            if profile:
                context["location"] = profile.get("location")
                context["interests"] = profile.get("interests", [])
                context["jurisdiction_id"] = profile.get("location", {}).get("jurisdiction_id")

        # Get recent follows
        try:
            from civic_services.storage.follow_storage import FollowStorage
            follow_storage = FollowStorage()
            follows = follow_storage.get_follows_for_user(token)
            context["follows"] = [
                {"type": f.get("focal_type"), "id": f.get("focal_id")}
                for f in follows[:10]
            ]
        except ImportError:
            context["follows"] = []

        # Get recent issues
        try:
            from civic_services.storage.issue_storage import IssueStorage
            issue_storage = IssueStorage()
            issues = issue_storage.get_issues_for_user(token)
            context["recent_issues"] = [
                {"id": i.get("id"), "title": i.get("title"), "status": i.get("status")}
                for i in issues[:5]
            ]
        except ImportError:
            context["recent_issues"] = []

        return context

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/export")
async def export_user_data(token: str = Depends(verify_auth)):
    """
    Export all user data (GDPR compliance).

    Returns complete data export including:
    - Profile information
    - All issues
    - All follows
    - All drafts
    - All messages

    Requires authentication.
    """
    try:
        export = {
            "user_id": token,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "profile": {},
            "issues": [],
            "follows": [],
            "drafts": [],
            "messages": []
        }

        # Get profile
        service = get_personalization_service()
        if service:
            export["profile"] = service.get_user_profile(token) or {}

        # Get all issues
        try:
            from civic_services.storage.issue_storage import IssueStorage
            issue_storage = IssueStorage()
            export["issues"] = issue_storage.get_issues_for_user(token)
        except ImportError:
            pass

        # Get all follows
        try:
            from civic_services.storage.follow_storage import FollowStorage
            follow_storage = FollowStorage()
            export["follows"] = follow_storage.get_follows_for_user(token)
        except ImportError:
            pass

        # Get all drafts
        try:
            from civic_services.storage.draft_storage import DraftStorage
            draft_storage = DraftStorage()
            export["drafts"] = draft_storage.get_user_drafts(token)
        except ImportError:
            pass

        # Get all messages
        try:
            from civic_services.storage.thread_storage import ThreadStorage
            thread_storage = ThreadStorage()
            export["messages"] = thread_storage.get_user_messages(token)
        except ImportError:
            pass

        return export

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.delete("/")
async def delete_user_account(token: str = Depends(verify_auth)):
    """
    Delete user account (GDPR compliance).

    Permanently deletes all user data including:
    - Profile
    - Issues
    - Follows
    - Drafts
    - Messages

    This action is irreversible.
    Requires authentication.
    """
    try:
        deleted_data = {
            "user_id": token,
            "deleted_at": datetime.utcnow().isoformat() + "Z",
            "deleted": {}
        }

        # Delete profile
        service = get_personalization_service()
        if service:
            service.delete_user(token)
            deleted_data["deleted"]["profile"] = True

        # Delete issues
        try:
            from civic_services.storage.issue_storage import IssueStorage
            issue_storage = IssueStorage()
            issue_storage.delete_user_issues(token)
            deleted_data["deleted"]["issues"] = True
        except ImportError:
            deleted_data["deleted"]["issues"] = False

        # Delete follows
        try:
            from civic_services.storage.follow_storage import FollowStorage
            follow_storage = FollowStorage()
            follow_storage.delete_user_follows(token)
            deleted_data["deleted"]["follows"] = True
        except ImportError:
            deleted_data["deleted"]["follows"] = False

        # Delete drafts
        try:
            from civic_services.storage.draft_storage import DraftStorage
            draft_storage = DraftStorage()
            draft_storage.delete_user_drafts(token)
            deleted_data["deleted"]["drafts"] = True
        except ImportError:
            deleted_data["deleted"]["drafts"] = False

        # Delete messages
        try:
            from civic_services.storage.thread_storage import ThreadStorage
            thread_storage = ThreadStorage()
            thread_storage.delete_user_messages(token)
            deleted_data["deleted"]["messages"] = True
        except ImportError:
            deleted_data["deleted"]["messages"] = False

        return {
            "success": True,
            "message": "User account deleted",
            "details": deleted_data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
