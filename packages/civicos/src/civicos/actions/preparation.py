"""
Preparation Module - prepare() implementation

Generates meeting preparation materials.
"""

from typing import List, Optional
from dataclasses import dataclass, field

from civicos._internal.state import StateManager


@dataclass
class Preparation:
    """Meeting preparation materials."""
    agenda_item_id: str
    regulatory_context: dict = field(default_factory=dict)
    historical_decisions: List[dict] = field(default_factory=list)
    talking_points: List[str] = field(default_factory=list)
    allies: List[dict] = field(default_factory=list)
    logistics: dict = field(default_factory=dict)


def _get_agenda_item(
    state: StateManager,
    jurisdiction: str,
    agenda_item_id: str
) -> Optional[dict]:
    """Fetch an agenda item by ID from the state manager."""
    city_state = state.get_city_state(jurisdiction)
    if not city_state or "error" in city_state:
        return None

    # Search agenda_items directly
    for item in city_state.get("agenda_items", []):
        if item.get("id") == agenda_item_id:
            return item

    # Also check embedded in meetings.full_data.agenda_items
    # Note: full_data can be nested (full_data.full_data.agenda_items) due to how meetings are stored
    for meeting in city_state.get("meetings", []):
        full_data = meeting.get("full_data", {})
        if isinstance(full_data, dict):
            # Check direct agenda_items
            for item in full_data.get("agenda_items", []):
                if item.get("id") == agenda_item_id:
                    item["_meeting"] = meeting
                    return item
            # Check nested full_data (double-wrapped)
            nested_full_data = full_data.get("full_data", {})
            if isinstance(nested_full_data, dict):
                for item in nested_full_data.get("agenda_items", []):
                    if item.get("id") == agenda_item_id:
                        item["_meeting"] = meeting
                        return item

    return None


def _get_meeting_for_agenda_item(
    state: StateManager,
    jurisdiction: str,
    agenda_item_id: str
) -> Optional[dict]:
    """Find the meeting containing an agenda item."""
    city_state = state.get_city_state(jurisdiction)
    if not city_state or "error" in city_state:
        return None

    # Check agenda_items table for meeting_id
    for item in city_state.get("agenda_items", []):
        if item.get("id") == agenda_item_id:
            meeting_id = item.get("meeting_id")
            for meeting in city_state.get("meetings", []):
                if meeting.get("id") == meeting_id:
                    return meeting
            break

    # Check embedded in meetings.full_data.agenda_items
    # Note: full_data can be nested (full_data.full_data.agenda_items)
    for meeting in city_state.get("meetings", []):
        full_data = meeting.get("full_data", {})
        if isinstance(full_data, dict):
            # Check direct agenda_items
            for item in full_data.get("agenda_items", []):
                if item.get("id") == agenda_item_id:
                    return meeting
            # Check nested full_data (double-wrapped)
            nested_full_data = full_data.get("full_data", {})
            if isinstance(nested_full_data, dict):
                for item in nested_full_data.get("agenda_items", []):
                    if item.get("id") == agenda_item_id:
                        return meeting

    return None


def _extract_topic_from_item(item: dict) -> str:
    """Extract a topic keyword from an agenda item for context lookup."""
    # Use project_type if available
    if item.get("project_type"):
        return item["project_type"]

    # Fall back to title keywords
    title = (item.get("title") or "").lower()
    topic_keywords = {
        "housing": ["housing", "residential", "apartment", "zoning", "development"],
        "transportation": ["transit", "transportation", "bike", "traffic", "parking", "sidewalk"],
        "environment": ["environment", "climate", "sustainability", "green", "energy"],
        "budget": ["budget", "finance", "tax", "revenue", "appropriation"],
        "education": ["school", "education", "student", "teacher"],
    }

    for topic, keywords in topic_keywords.items():
        for kw in keywords:
            if kw in title:
                return topic

    return "general"


def _generate_talking_points(item: dict, regulatory_context: dict) -> List[str]:
    """Generate talking points based on item and regulatory context."""
    points = []

    title = item.get("title", "this item")

    # Basic talking point from item
    points.append(f"I'm here to speak about {title}.")

    # Add regulatory context talking points
    state_bills = regulatory_context.get("state", [])
    for bill in state_bills[:2]:  # Top 2 relevant bills
        if isinstance(bill, dict) and bill.get("bill"):
            points.append(
                f"This relates to {bill['bill']}: {bill.get('title', 'state legislation')}."
            )

    federal_programs = regulatory_context.get("federal", [])
    for program in federal_programs[:1]:  # Top federal program
        if isinstance(program, dict) and program.get("program_name"):
            points.append(
                f"Federal funding via {program['program_name']} may be relevant."
            )

    # Add call to action
    points.append("I urge the council to consider community impact.")

    return points


def _find_allies(
    state: StateManager,
    jurisdiction: str,
    agenda_item_id: str,
    meeting_id: str = None
) -> List[dict]:
    """Find others who have voiced on or follow related items."""
    allies = []

    # Get voices on this agenda item
    voices = state.query_voices("agenda_item", agenda_item_id, limit=10)
    for voice in voices:
        allies.append({
            "type": "voiced",
            "user_id": voice.get("user_id"),
            "stance": voice.get("stance"),
            "item_id": agenda_item_id,
        })

    # Get subscriptions to this agenda item
    subs = state.query_subscriptions(item_type="meeting", item_id=meeting_id, limit=10)
    for sub in subs:
        # Avoid duplicates
        if not any(a.get("user_id") == sub.get("user_id") for a in allies):
            allies.append({
                "type": "following",
                "user_id": sub.get("user_id"),
                "item_id": meeting_id,
            })

    return allies


def _compile_logistics(meeting: dict) -> dict:
    """Compile logistics for meeting participation."""
    logistics = {
        "meeting_title": meeting.get("title"),
        "meeting_datetime": meeting.get("meeting_datetime"),
        "location": meeting.get("location"),
        "virtual_url": meeting.get("virtual_url"),
        "agenda_url": meeting.get("agenda_url"),
        "comment_deadline": meeting.get("comment_deadline"),
        "public_comment_rules": "Check city website for public comment procedures.",
    }

    # Add helpful tips based on meeting type
    meeting_type = meeting.get("meeting_type", "").lower()
    if "city council" in meeting_type:
        logistics["tips"] = [
            "Sign up to speak during public comment period",
            "Prepare a 2-3 minute statement",
            "Bring written copies for council members",
        ]
    elif "planning" in meeting_type:
        logistics["tips"] = [
            "Review the staff report before attending",
            "Bring visual aids if relevant",
            "Note the project number for reference",
        ]
    else:
        logistics["tips"] = [
            "Arrive early to sign up for public comment",
            "Keep remarks focused and within time limits",
        ]

    return logistics


def prepare_for_meeting(
    agenda_item_id: str,
    jurisdiction: str,
    user_id: str = None,
    db_path: str = "data/civic_state.db"
) -> Preparation:
    """
    Get preparation materials for participating.

    Returns context, talking points, allies, and logistics
    for an upcoming agenda item.

    Uses:
    - civicos-state for agenda item and meeting data
    - civic context module for regulatory context
    - civicos-state for historical decisions and allies

    Args:
        agenda_item_id: ID of the agenda item
        jurisdiction: City/jurisdiction ID
        user_id: Optional user ID for personalization
        db_path: Path to database (for testing)

    Returns:
        Preparation with context, talking points, allies, logistics

    Raises:
        ValueError: If agenda_item_id not found
    """
    state = StateManager(db_path)

    # 1. Fetch agenda item
    item = _get_agenda_item(state, jurisdiction, agenda_item_id)
    if not item:
        raise ValueError(f"Agenda item '{agenda_item_id}' not found in {jurisdiction}")

    # 2. Find the parent meeting
    meeting = _get_meeting_for_agenda_item(state, jurisdiction, agenda_item_id)
    if meeting is None:
        # Create minimal meeting info if not found
        meeting = {"title": "Meeting", "location": "Unknown"}

    # 3. Get regulatory context
    topic = _extract_topic_from_item(item)
    try:
        from civicos.context import get_regulatory_context
        reg_stack = get_regulatory_context(jurisdiction, topic)
        regulatory_context = {
            "topic": reg_stack.topic,
            "federal": reg_stack.federal,
            "state": reg_stack.state,
            "local": reg_stack.local,
        }
    except Exception:
        regulatory_context = {
            "topic": topic,
            "federal": [],
            "state": [],
            "local": [],
        }

    # 4. Generate talking points
    talking_points = _generate_talking_points(item, regulatory_context)

    # 5. Find allies
    meeting_id = meeting.get("id")
    allies = _find_allies(state, jurisdiction, agenda_item_id, meeting_id)

    # 6. Compile logistics
    logistics = _compile_logistics(meeting)

    # 7. Get historical decisions (placeholder - would need what_happened)
    historical_decisions = []

    return Preparation(
        agenda_item_id=agenda_item_id,
        regulatory_context=regulatory_context,
        historical_decisions=historical_decisions,
        talking_points=talking_points,
        allies=allies,
        logistics=logistics,
    )
