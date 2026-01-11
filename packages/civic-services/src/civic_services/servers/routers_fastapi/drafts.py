"""
Drafts router: draft comments and submissions.

Endpoints:
- GET /events/{event_id}/drafts - Get drafts for an event
- GET /events/{event_id}/draft-comment - Get most recent draft for user
- POST /events/{event_id}/draft-comment - Create draft comment
- POST /events/{event_id}/items/{item_id}/regenerate - Regenerate item comment
- GET /drafts/{draft_id} - Get single draft
- PUT /drafts/{draft_id} - Update draft
- DELETE /drafts/{draft_id} - Delete draft
- POST /drafts/{draft_id}/submit - Mark draft as submitted
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Draft(BaseModel):
    """Draft comment record."""
    id: str
    user_id: str
    event_id: str
    content: str
    status: str  # draft, submitted, approved, rejected
    created_at: str
    updated_at: Optional[str] = None
    submitted_at: Optional[str] = None
    event_title: Optional[str] = None
    item_id: Optional[str] = None
    item_title: Optional[str] = None


class CreateDraftRequest(BaseModel):
    """Request to create a draft comment."""
    content: str
    item_id: Optional[str] = None


class UpdateDraftRequest(BaseModel):
    """Request to update a draft."""
    content: str


class RegenerateRequest(BaseModel):
    """Request to regenerate a comment."""
    tone: Optional[str] = None  # formal, casual, passionate
    focus: Optional[str] = None  # concern, support, question


# === Auth Dependency ===

from .dependencies import verify_auth


# === Storage Helper ===

def get_draft_storage():
    """Get draft storage instance."""
    try:
        from civic_services.storage.draft_storage import DraftStorage
        return DraftStorage()
    except ImportError:
        return None


# === Endpoints ===

@router.get("/events/{event_id}/drafts")
async def get_event_drafts(
    event_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    token: str = Depends(verify_auth)
):
    """
    Get all drafts for an event.

    Returns user's draft comments for the specified event.
    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            return {"drafts": [], "note": "Draft storage not available"}

        drafts = storage.get_event_drafts(event_id=event_id, user_id=token, status=status)

        return {
            "event_id": event_id,
            "drafts": drafts,
            "count": len(drafts)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/events/{event_id}/draft-comment")
async def get_event_draft_comment(
    event_id: str,
    user_id: Optional[str] = Query(None, description="User ID to get draft for"),
    token: str = Depends(verify_auth)
):
    """
    Get the most recent draft comment for an event.

    Returns the user's most recent draft or null if none exists.
    Enables Google Docs-style draft loading without API generation cost.
    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            return {
                "draft_id": None,
                "draft": None,
                "structured_summary": None,
                "personal_context": None,
                "selected_agenda_items": [],
                "is_template": False,
                "created_at": None,
                "updated_at": None,
                "submitted": False,
                "note": "Draft storage not available"
            }

        # Use provided user_id or token
        target_user = user_id or token
        drafts = storage.get_event_drafts(event_id=event_id, user_id=target_user)

        if not drafts:
            return {
                "draft_id": None,
                "draft": None,
                "structured_summary": None,
                "personal_context": None,
                "selected_agenda_items": [],
                "is_template": False,
                "created_at": None,
                "updated_at": None,
                "submitted": False
            }

        # Get most recent draft (already sorted by updated_at desc)
        most_recent = drafts[0]

        return {
            "draft_id": most_recent.get("id"),
            "draft": most_recent.get("content"),
            "structured_summary": most_recent.get("structured_summary"),
            "personal_context": most_recent.get("personal_context"),
            "selected_agenda_items": most_recent.get("selected_agenda_items", []),
            "is_template": most_recent.get("is_template", False),
            "created_at": most_recent.get("created_at"),
            "updated_at": most_recent.get("updated_at"),
            "submitted": most_recent.get("status") == "submitted"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/events/{event_id}/draft-comment")
async def create_draft_comment(
    event_id: str,
    request: CreateDraftRequest,
    token: str = Depends(verify_auth)
):
    """
    Create a draft comment for an event.

    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Draft storage not available")

        draft = storage.create_draft(
            user_id=token,
            event_id=event_id,
            content=request.content,
            item_id=request.item_id
        )

        return {
            "success": True,
            "draft": draft
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/events/{event_id}/items/{item_id}/regenerate")
async def regenerate_item_comment(
    event_id: str,
    item_id: str,
    request: RegenerateRequest,
    token: str = Depends(verify_auth)
):
    """
    Regenerate a comment for a specific agenda item.

    Uses AI to generate a new comment based on the item context.
    Requires authentication.
    """
    try:
        # Get the event and item context
        from .events import load_all_events
        all_events = load_all_events()

        event = None
        item = None
        for e in all_events:
            if e.get("id") == event_id:
                event = e
                for i in e.get("agenda_items", []):
                    if i.get("id") == item_id:
                        item = i
                        break
                break

        if not event:
            raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")
        if not item:
            raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")

        # Generate comment using LLM
        try:
            import openai
            client = openai.OpenAI()

            tone = request.tone or "formal"
            focus = request.focus or "concern"

            prompt = f"""Generate a public comment for a city council agenda item.

Event: {event.get('title', 'Unknown')}
Item: {item.get('title', 'Unknown')}
Description: {item.get('description', 'No description')}

Tone: {tone}
Focus: {focus}

Write a 2-3 paragraph public comment that:
1. Clearly identifies the item being addressed
2. States a clear position or asks a specific question
3. Provides reasoning or evidence for the position
4. Is respectful and constructive

Comment:"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500
            )

            generated_content = response.choices[0].message.content

        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Comment generation failed: {str(e)}")

        # Save as draft
        storage = get_draft_storage()
        if storage:
            draft = storage.create_draft(
                user_id=token,
                event_id=event_id,
                content=generated_content,
                item_id=item_id
            )
            return {
                "success": True,
                "draft": draft,
                "generated": True
            }
        else:
            return {
                "success": True,
                "content": generated_content,
                "generated": True,
                "note": "Draft storage not available - content not saved"
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get a single draft by ID.

    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Draft storage not available")

        draft = storage.get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")

        # Verify ownership
        if draft.get("user_id") != token:
            raise HTTPException(status_code=403, detail="Not authorized to view this draft")

        return draft

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: str,
    request: UpdateDraftRequest,
    token: str = Depends(verify_auth)
):
    """
    Update a draft.

    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Draft storage not available")

        # Verify draft exists and user owns it
        draft = storage.get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        if draft.get("user_id") != token:
            raise HTTPException(status_code=403, detail="Not authorized to update this draft")

        # Update draft
        updated = storage.update_draft(draft_id, content=request.content)

        return {
            "success": True,
            "draft": updated
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: str,
    token: str = Depends(verify_auth)
):
    """
    Delete a draft.

    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Draft storage not available")

        # Verify draft exists and user owns it
        draft = storage.get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        if draft.get("user_id") != token:
            raise HTTPException(status_code=403, detail="Not authorized to delete this draft")

        # Delete draft
        deleted = storage.delete_draft(draft_id)

        return {
            "success": deleted,
            "message": "Draft deleted" if deleted else "Failed to delete"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/drafts/{draft_id}/submit")
async def submit_draft(
    draft_id: str,
    token: str = Depends(verify_auth)
):
    """
    Mark a draft as submitted.

    Updates status and records submission timestamp.
    Requires authentication.
    """
    try:
        storage = get_draft_storage()
        if not storage:
            raise HTTPException(status_code=503, detail="Draft storage not available")

        # Verify draft exists and user owns it
        draft = storage.get_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft not found: {draft_id}")
        if draft.get("user_id") != token:
            raise HTTPException(status_code=403, detail="Not authorized to submit this draft")

        # Mark as submitted
        submitted = storage.mark_submitted(draft_id)

        return {
            "success": True,
            "draft": submitted
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
