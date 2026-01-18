"""
Calendar Module - whats_next() implementation

Gets upcoming meetings from civicos-state.
"""

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from civicos._internal.state import StateManager


@dataclass
class Meeting:
    """An upcoming meeting."""
    id: str
    title: str
    date: datetime
    body: str
    agenda_items: List[dict] = field(default_factory=list)
    location: Optional[str] = None


def get_upcoming_meetings(
    state_manager: StateManager,
    jurisdiction: str,
    topics: List[str] = None,
    days: int = 30
) -> List[Meeting]:
    """
    Get upcoming meetings matching topics.

    Uses civicos-state StateManager to query meetings.

    Args:
        state_manager: StateManager instance
        jurisdiction: City/jurisdiction ID
        topics: Optional list of topics to filter by
        days: Number of days to look ahead

    Returns:
        List of upcoming meetings
    """
    # Get city state
    city_state = state_manager.get_city_state(jurisdiction)
    if not city_state:
        return []

    meetings_data = city_state.get("meetings", [])
    now = datetime.now()
    cutoff = now + timedelta(days=days)

    meetings = []
    for m in meetings_data:
        # Support both 'meeting_datetime' (relational) and 'date' (legacy) keys
        meeting_date = m.get("meeting_datetime") or m.get("date")
        if isinstance(meeting_date, str):
            try:
                meeting_date = datetime.fromisoformat(meeting_date)
            except ValueError:
                meeting_date = now
        elif meeting_date is None:
            continue  # Skip meetings without a date

        # Filter by date range
        if meeting_date < now or meeting_date > cutoff:
            continue

        # Filter by topics if provided
        if topics:
            agenda_items = m.get("agenda_items", [])
            topic_match = False
            for item in agenda_items:
                # Support both 'topic' (JSON) and 'project_type' (relational) keys
                item_topic = (item.get("topic") or item.get("project_type") or "").lower()
                if any(t.lower() in item_topic for t in topics):
                    topic_match = True
                    break
            if not topic_match:
                continue

        meetings.append(Meeting(
            id=m.get("id", ""),
            title=m.get("title", ""),
            date=meeting_date,
            body=m.get("body", ""),
            agenda_items=m.get("agenda_items", []),
            location=m.get("location"),
        ))

    # Sort by date
    meetings.sort(key=lambda m: m.date)

    return meetings
