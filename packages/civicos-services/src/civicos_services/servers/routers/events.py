"""
Events router: event listings, search, and related endpoints.

Endpoints:
- GET /events - List all events
- GET /events/search - Search events with filters
- GET /events/{event_id} - Get single event
- GET /events/{event_id}/discussion-stats - Get discussion stats
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class Event(BaseModel):
    """Event/opportunity response."""
    id: str
    title: str
    start: Optional[str] = None
    when: Optional[str] = None
    location: Optional[str] = None
    project_type: Optional[str] = None
    jurisdiction_id: Optional[str] = None
    jurisdiction: Optional[Dict[str, Any]] = None
    agenda_items: Optional[List[Dict[str, Any]]] = None
    legislative_context: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


class EventSearchResponse(BaseModel):
    """Event search results."""
    events: List[Dict[str, Any]]
    count: int
    query: Dict[str, Any]
    jurisdictions_searched: List[str]


class EventListResponse(BaseModel):
    """Event list response."""
    events: Optional[List[Dict[str, Any]]] = None


# === Helper Functions ===

def load_all_events() -> List[Dict]:
    """Load all events from JSON files."""
    events = []
    schema_dir = Path("data/events")

    if not schema_dir.exists():
        return events

    # Group files by jurisdiction to get most recent
    jurisdiction_files = {}
    for file_path in schema_dir.glob("events_*.json"):
        filename = file_path.stem
        parts = filename.split("_")
        if len(parts) >= 3:
            jur_id = "_".join(parts[1:-1])
            if jur_id not in jurisdiction_files or file_path.stat().st_mtime > jurisdiction_files[jur_id].stat().st_mtime:
                jurisdiction_files[jur_id] = file_path

    # Load most recent file for each jurisdiction
    for file_path in jurisdiction_files.values():
        try:
            with open(file_path, "r") as f:
                event_data = json.load(f)
                events.extend(event_data.get("events", []))
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    return events


def text_matches_event(event: Dict, query: str) -> bool:
    """Check if query matches event text."""
    searchable = [
        event.get("title", ""),
        event.get("description", ""),
        event.get("body_name", ""),
    ]

    # Add agenda item titles and descriptions
    for item in event.get("agenda_items", []):
        searchable.append(item.get("title", ""))
        searchable.append(item.get("description", ""))

    return any(query in text.lower() for text in searchable if text)


def parse_date_range(date_range: str):
    """Parse date range string into start/end dates."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    date_range_lower = date_range.lower().strip()

    if date_range_lower in ("this week", "thisweek"):
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)
    elif date_range_lower in ("next week", "nextweek"):
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=1)
        end = start + timedelta(days=7)
    elif date_range_lower in ("this month", "thismonth"):
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            end = today.replace(month=today.month + 1, day=1)
    elif date_range_lower in ("next month", "nextmonth"):
        if today.month == 12:
            start = today.replace(year=today.year + 1, month=1, day=1)
            end = today.replace(year=today.year + 1, month=2, day=1)
        else:
            start = today.replace(month=today.month + 1, day=1)
            if today.month + 1 == 12:
                end = today.replace(year=today.year + 1, month=1, day=1)
            else:
                end = today.replace(month=today.month + 2, day=1)
    else:
        # Try to parse as month name (e.g., "October", "Jan")
        months = {
            "january": 1, "jan": 1,
            "february": 2, "feb": 2,
            "march": 3, "mar": 3,
            "april": 4, "apr": 4,
            "may": 5,
            "june": 6, "jun": 6,
            "july": 7, "jul": 7,
            "august": 8, "aug": 8,
            "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10,
            "november": 11, "nov": 11,
            "december": 12, "dec": 12,
        }
        month_num = months.get(date_range_lower)
        if month_num:
            year = today.year if month_num >= today.month else today.year + 1
            start = datetime(year, month_num, 1)
            if month_num == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, month_num + 1, 1)
        else:
            # Default to all time
            start = datetime(2020, 1, 1)
            end = datetime(2100, 1, 1)

    return start, end


def event_in_date_range(event: Dict, start: datetime, end: datetime) -> bool:
    """Check if event falls within date range."""
    event_date_str = event.get("start") or event.get("when")
    if not event_date_str:
        return False

    try:
        event_date = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
        event_date = event_date.replace(tzinfo=None)  # Naive comparison
        return start <= event_date < end
    except Exception:
        return False


# === Auth Dependency ===

from .dependencies import verify_auth


# === Endpoints ===

@router.get("/events", response_model=EventListResponse)
async def list_events(
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction ID"),
    project_type: Optional[str] = Query(None, description="Filter by project type"),
    start_date: Optional[str] = Query(None, description="Filter by start date (ISO format)"),
    user_id: str = Depends(verify_auth)
):
    """
    List all events/opportunities.

    Requires authentication.
    """
    try:
        events = load_all_events()

        # Filter by jurisdiction if provided
        if jurisdiction:
            events = [
                e for e in events
                if (e.get("jurisdiction_id") or e.get("jurisdiction", {}).get("id")) == jurisdiction
            ]

        # Filter by project type if provided
        if project_type:
            events = [e for e in events if e.get("project_type") == project_type]

        # Filter by start date if provided
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            events = [
                e for e in events
                if e.get("when") and datetime.fromisoformat(e["when"].replace("Z", "+00:00")) >= start_dt
            ]

        return {"events": events}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/events/search", response_model=EventSearchResponse)
async def search_events(
    jurisdiction: Optional[str] = Query(None, description="Jurisdiction(s) - comma-separated or 'all'"),
    topics: Optional[str] = Query(None, description="Topic(s) - comma-separated"),
    topic: Optional[str] = Query(None, description="Single topic (alias for topics)"),
    q: Optional[str] = Query(None, description="Text search query"),
    date_range: Optional[str] = Query(None, description="Date range filter"),
    itemCountMin: Optional[int] = Query(None, description="Minimum agenda items"),
    user_id: str = Depends(verify_auth)
):
    """
    Search events with filtering.

    Supports:
    - Multiple jurisdictions (comma-separated) or 'all'
    - Multiple topics (comma-separated)
    - Text search across title, description, agenda items
    - Date range filters (this week, next month, October, etc.)
    - Minimum agenda item count

    Requires authentication.
    """
    try:
        # Handle jurisdiction parameter
        if jurisdiction and jurisdiction.strip().lower() == "all":
            jurisdictions = []
            search_all = True
        else:
            jurisdictions = [j.strip() for j in jurisdiction.split(",")] if jurisdiction else []
            search_all = False

        # Handle topics (support both singular and plural params)
        topics_param = topics or topic
        topic_list = [t.strip() for t in topics_param.split(",")] if topics_param else []

        # Load all events
        all_events = load_all_events()

        # Track which jurisdictions are included
        jurisdictions_searched = set()

        # Filter by jurisdiction(s)
        if jurisdictions and not search_all:
            filtered_events = []
            for e in all_events:
                jur_id = e.get("jurisdiction_id") or e.get("jurisdiction", {}).get("id")
                if jur_id in jurisdictions:
                    filtered_events.append(e)
                    jurisdictions_searched.add(jur_id)
            all_events = filtered_events
        elif not search_all and not jurisdictions:
            all_events = []
        else:
            # search_all=True - include all jurisdictions
            for e in all_events:
                jur_id = e.get("jurisdiction_id") or e.get("jurisdiction", {}).get("id")
                if jur_id:
                    jurisdictions_searched.add(jur_id)

        # Filter by topic(s)
        if topic_list:
            all_events = [
                e for e in all_events
                if e.get("project_type") in topic_list
                or any(t in e.get("legislative_context", {}).get("topics", []) for t in topic_list)
            ]

        # Text search
        if q:
            query_lower = q.lower()
            all_events = [e for e in all_events if text_matches_event(e, query_lower)]

        # Date range filter
        if date_range:
            start, end = parse_date_range(date_range)
            all_events = [e for e in all_events if event_in_date_range(e, start, end)]

        # Item count filter
        if itemCountMin is not None:
            all_events = [e for e in all_events if len(e.get("agenda_items", [])) >= itemCountMin]

        # Sort by date
        all_events.sort(key=lambda e: e.get("start", ""))

        return {
            "events": all_events,
            "count": len(all_events),
            "query": {
                "jurisdictions": jurisdictions if not search_all else ["all"],
                "topics": topic_list,
                "q": q,
                "date_range": date_range,
                "itemCountMin": itemCountMin
            },
            "jurisdictions_searched": sorted(list(jurisdictions_searched))
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    user_id: str = Depends(verify_auth)
):
    """
    Get a single event by ID.

    Requires authentication.
    """
    try:
        all_events = load_all_events()

        for event in all_events:
            if event.get("id") == event_id:
                return event

        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/events/{event_id}/discussion-stats")
async def get_event_discussion_stats(
    event_id: str,
    user_id: str = Depends(verify_auth)
):
    """
    Get discussion statistics for an event.

    Returns thread count, message count, and participant count.
    Requires authentication.
    """
    try:
        # Import thread storage
        try:
            from civicos_services.storage.thread_storage import ThreadStorage
            storage = ThreadStorage()
        except ImportError:
            return {
                "event_id": event_id,
                "thread_count": 0,
                "message_count": 0,
                "participant_count": 0,
                "error": "Thread storage not available"
            }

        # Get threads for this event
        threads = storage.get_threads_for_focal(focal_type="event", focal_id=event_id)

        # Calculate stats
        message_count = 0
        participants = set()

        for thread in threads:
            messages = storage.get_messages(thread["id"])
            message_count += len(messages)
            for msg in messages:
                if msg.get("user_id"):
                    participants.add(msg["user_id"])

        return {
            "event_id": event_id,
            "thread_count": len(threads),
            "message_count": message_count,
            "participant_count": len(participants)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
