"""
Follows router: following events, issues, topics.

Endpoints:
- GET /follows - Get all follows for user
- GET /follows/{focal_type}/{focal_id} - Get follow info
- POST /follows - Create a follow
- POST /follows/{focal_type}/{focal_id}/mark-read - Mark thread as read
- DELETE /follows/{focal_type}/{focal_id} - Unfollow
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Follow(BaseModel):
    """Follow record."""
    id: str
    user_id: str
    focal_type: str  # event, issue, topic
    focal_id: str
    focal_title: Optional[str] = None
    created_at: str
    last_read_at: Optional[str] = None


class CreateFollowRequest(BaseModel):
    """Request to create a follow."""
    focal_type: str
    focal_id: str
    focal_title: Optional[str] = None


# === Auth Dependency ===

from .dependencies import verify_auth


# === Storage Helper ===

def get_follow_storage():
    """Get follow storage instance."""
    try:
        from civicos_services.storage.follow_storage import FollowStorage
        return FollowStorage()
    except ImportError:
        return None


# === Endpoints ===

@router.get("/follows")
async def get_user_follows(
    token: str = Depends(verify_auth)
):
    """
    Get all follows for the current user.

    Returns list of all items the user is following.
    Requires authentication.
    """
    try:
        storage = get_follow_storage()
        if not storage:
            return {
                "follows": [],
                "count": 0,
                "note": "Follow storage not available"
            }

        # Get all follows for user
        follows = storage.get_follows_for_user(token)

        return {
            "follows": follows,
            "count": len(follows)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/follows/{focal_type}/{focal_id}")
async def get_follow_info(
    focal_type: str,
    focal_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get follow information for a specific item.

    Returns whether the user is following and any unread updates.
    Requires authentication.
    """
    try:
        storage = get_follow_storage()
        if not storage:
            return {
                "is_following": False,
                "unread_count": 0,
                "note": "Follow storage not available"
            }

        # Check if user is following
        follow = storage.get_follow(token, focal_type, focal_id)

        if not follow:
            return {
                "is_following": False,
                "unread_count": 0
            }

        # Get unread count
        unread = storage.get_unread_count(token, focal_type, focal_id)

        return {
            "is_following": True,
            "follow": follow,
            "unread_count": unread,
            "last_read_at": follow.get("last_read_at")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/follows")
async def create_follow(
    request: CreateFollowRequest,
    token: str = Depends(verify_auth)
):
    """
    Create a follow (subscribe to updates).

    Requires authentication.
    """
    try:
        storage = get_follow_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Follow storage not available")

        # Create follow
        follow = storage.create_follow(
            user_id=token,
            focal_type=request.focal_type,
            focal_id=request.focal_id,
            focal_title=request.focal_title
        )

        return {
            "success": True,
            "follow": follow
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/follows/{focal_type}/{focal_id}/mark-read")
async def mark_thread_read(
    focal_type: str,
    focal_id: str,
    token: str = Depends(verify_auth)
):
    """
    Mark a followed item's thread as read.

    Updates last_read_at timestamp.
    Requires authentication.
    """
    try:
        storage = get_follow_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Follow storage not available")

        # Update last read
        updated = storage.mark_read(token, focal_type, focal_id)

        return {
            "success": True,
            "last_read_at": updated.get("last_read_at") if updated else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.delete("/follows/{focal_type}/{focal_id}")
async def delete_follow(
    focal_type: str,
    focal_id: str,
    token: str = Depends(verify_auth)
):
    """
    Unfollow an item.

    Requires authentication.
    """
    try:
        storage = get_follow_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Follow storage not available")

        # Delete follow
        deleted = storage.delete_follow(token, focal_type, focal_id)

        return {
            "success": deleted,
            "message": "Unfollowed" if deleted else "Was not following"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
