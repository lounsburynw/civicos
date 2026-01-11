"""
Threads router: messaging threads and messages.

Endpoints:
- GET /threads - List all user threads
- GET /threads/{thread_id} - Get thread info
- GET /threads/{thread_id}/messages - Get thread messages
- POST /threads/{thread_id}/messages - Send message to thread
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Thread(BaseModel):
    """Thread record."""
    id: str
    focal_type: str  # event, issue
    focal_id: str
    title: Optional[str] = None
    participant_count: int = 0
    message_count: int = 0
    created_at: str
    last_message_at: Optional[str] = None


class Message(BaseModel):
    """Message record."""
    id: str
    thread_id: str
    user_id: str
    content: str
    created_at: str
    is_system: bool = False


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    content: str


# === Auth Dependency ===

from .dependencies import verify_auth


# === Storage Helper ===

def get_thread_storage():
    """Get thread storage instance."""
    try:
        from civic_services.storage.thread_storage import ThreadStorage
        return ThreadStorage()
    except ImportError:
        return None


# === Endpoints ===

@router.get("/threads")
async def list_threads(
    focal_type: Optional[str] = Query(None, description="Filter by focal type"),
    focal_id: Optional[str] = Query(None, description="Filter by focal ID"),
    token: str = Depends(verify_auth)
):
    """
    List all threads the user participates in.

    Optionally filter by focal type (event, issue) or focal ID.
    Requires authentication.
    """
    try:
        storage = get_thread_storage()
        if not storage:
            return {"threads": [], "note": "Thread storage not available"}

        # Get user's threads
        threads = storage.get_user_threads(token)

        # Apply filters
        if focal_type:
            threads = [t for t in threads if t.get("focal_type") == focal_type]

        if focal_id:
            threads = [t for t in threads if t.get("focal_id") == focal_id]

        return {
            "threads": threads,
            "count": len(threads)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/threads/{thread_id}")
async def get_thread_info(
    thread_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get information about a specific thread.

    Returns thread metadata and participant info.
    Requires authentication.
    """
    try:
        storage = get_thread_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Thread storage not available")

        thread = storage.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")

        # Get participants
        participants = storage.get_thread_participants(thread_id)

        return {
            "thread": thread,
            "participants": participants
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(50, description="Maximum messages to return"),
    before: Optional[str] = Query(None, description="Get messages before this ID"),
    token: str = Depends(verify_auth)
):
    """
    Get messages from a thread.

    Returns messages in chronological order.
    Requires authentication.
    """
    try:
        storage = get_thread_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Thread storage not available")

        # Verify thread exists
        thread = storage.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")

        # Get messages
        messages = storage.get_messages(thread_id, limit=limit, before=before)

        return {
            "thread_id": thread_id,
            "messages": messages,
            "count": len(messages)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    request: SendMessageRequest,
    token: str = Depends(verify_auth)
):
    """
    Send a message to a thread.

    Requires authentication.
    """
    try:
        storage = get_thread_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Thread storage not available")

        # Verify thread exists
        thread = storage.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")

        # Create message
        message = storage.create_message(
            thread_id=thread_id,
            user_id=token,
            content=request.content
        )

        return {
            "success": True,
            "message": message
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
