"""
Preparation Workflow Nodes

Individual node functions for the meeting preparation workflow.
Each node transforms the PreparationState.
"""

from typing import List, Optional
import logging

from civic._internal.state import StateManager
from civic._internal.coordination.preparation_state import PreparationState

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/civic_state.db"


def load_agenda_item(state: PreparationState) -> PreparationState:
    """
    Load the agenda item and parent meeting from database.

    Sets agenda_item, meeting fields in state.
    """
    logger.debug(f"Loading agenda item: {state.get('agenda_item_id')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)
    jurisdiction = state.get("jurisdiction")
    agenda_item_id = state.get("agenda_item_id")

    agenda_item = _get_agenda_item(state_mgr, jurisdiction, agenda_item_id)
    meeting = _get_meeting_for_agenda_item(state_mgr, jurisdiction, agenda_item_id)

    if not agenda_item:
        return {
            **state,
            "agenda_item": None,
            "meeting": None,
            "status": "error",
            "error": f"Agenda item '{agenda_item_id}' not found",
        }

    return {
        **state,
        "agenda_item": agenda_item,
        "meeting": meeting or {"title": "Meeting", "location": "Unknown"},
        "status": "loaded",
        "error": None,
    }


def _get_agenda_item(
    state_mgr: StateManager,
    jurisdiction: str,
    agenda_item_id: str
) -> Optional[dict]:
    """Fetch an agenda item by ID from the state manager."""
    city_state = state_mgr.get_city_state(jurisdiction)
    if not city_state or "error" in city_state:
        return None

    # Search agenda_items directly
    for item in city_state.get("agenda_items", []):
        if item.get("id") == agenda_item_id:
            return item

    # Also check embedded in meetings.full_data.agenda_items
    for meeting in city_state.get("meetings", []):
        full_data = meeting.get("full_data", {})
        if isinstance(full_data, dict):
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
    state_mgr: StateManager,
    jurisdiction: str,
    agenda_item_id: str
) -> Optional[dict]:
    """Find the meeting containing an agenda item."""
    city_state = state_mgr.get_city_state(jurisdiction)
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
    for meeting in city_state.get("meetings", []):
        full_data = meeting.get("full_data", {})
        if isinstance(full_data, dict):
            for item in full_data.get("agenda_items", []):
                if item.get("id") == agenda_item_id:
                    return meeting
            nested_full_data = full_data.get("full_data", {})
            if isinstance(nested_full_data, dict):
                for item in nested_full_data.get("agenda_items", []):
                    if item.get("id") == agenda_item_id:
                        return meeting

    return None


def gather_regulatory_context(state: PreparationState) -> PreparationState:
    """
    Gather regulatory context for the agenda item.

    Sets topic, regulatory_context, historical_decisions fields.
    """
    logger.debug("Gathering regulatory context")

    agenda_item = state.get("agenda_item")
    if not agenda_item:
        return {
            **state,
            "topic": "general",
            "regulatory_context": {},
            "historical_decisions": [],
            "status": "gathered",
        }

    jurisdiction = state.get("jurisdiction")
    topic = _extract_topic_from_item(agenda_item)

    # Get regulatory context
    try:
        from civic.context import get_regulatory_context
        reg_stack = get_regulatory_context(jurisdiction, topic)
        regulatory_context = {
            "topic": reg_stack.topic,
            "federal": reg_stack.federal,
            "state": reg_stack.state,
            "local": reg_stack.local,
        }
    except Exception as e:
        logger.debug(f"Could not get regulatory context: {e}")
        regulatory_context = {
            "topic": topic,
            "federal": [],
            "state": [],
            "local": [],
        }

    # Placeholder for historical decisions (would use what_happened)
    historical_decisions = []

    return {
        **state,
        "topic": topic,
        "regulatory_context": regulatory_context,
        "historical_decisions": historical_decisions,
        "status": "gathered",
    }


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


def find_allies(state: PreparationState) -> PreparationState:
    """
    Find others who have voiced on or follow related items.

    Sets allies field.
    """
    logger.debug("Finding allies")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)
    agenda_item_id = state.get("agenda_item_id")
    meeting = state.get("meeting", {})
    meeting_id = meeting.get("id") if meeting else None

    allies = []

    # Get voices on this agenda item
    voices = state_mgr.query_voices("agenda_item", agenda_item_id, limit=10)
    for voice in voices:
        allies.append({
            "type": "voiced",
            "user_id": voice.get("user_id"),
            "stance": voice.get("stance"),
            "item_id": agenda_item_id,
        })

    # Get subscriptions to this meeting
    if meeting_id:
        subs = state_mgr.query_subscriptions(item_type="meeting", item_id=meeting_id, limit=10)
        for sub in subs:
            # Avoid duplicates
            if not any(a.get("user_id") == sub.get("user_id") for a in allies):
                allies.append({
                    "type": "following",
                    "user_id": sub.get("user_id"),
                    "item_id": meeting_id,
                })

    return {
        **state,
        "allies": allies,
        "status": "allies_found",
    }


def generate_talking_points(state: PreparationState) -> PreparationState:
    """
    Generate talking points based on item and regulatory context.

    Sets talking_points field.
    """
    logger.debug("Generating talking points")

    agenda_item = state.get("agenda_item", {})
    regulatory_context = state.get("regulatory_context", {})

    points = []
    title = agenda_item.get("title", "this item") if agenda_item else "this item"

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

    return {
        **state,
        "talking_points": points,
        "status": "points_generated",
    }


def compile_logistics(state: PreparationState) -> PreparationState:
    """
    Compile logistics for meeting participation.

    Sets logistics field.
    """
    logger.debug("Compiling logistics")

    meeting = state.get("meeting") or {}

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
    meeting_type = (meeting.get("meeting_type") or "").lower()
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

    return {
        **state,
        "logistics": logistics,
        "status": "logistics_compiled",
    }


def format_preparation(state: PreparationState) -> PreparationState:
    """
    Format preparation materials for output.

    Sets preparation field with complete materials.
    """
    logger.debug("Formatting preparation materials")

    preparation = {
        "agenda_item_id": state.get("agenda_item_id"),
        "topic": state.get("topic", "general"),
        "regulatory_context": state.get("regulatory_context", {}),
        "historical_decisions": state.get("historical_decisions", []),
        "talking_points": state.get("talking_points", []),
        "allies": state.get("allies", []),
        "logistics": state.get("logistics", {}),
    }

    return {
        **state,
        "preparation": preparation,
        "status": "complete",
    }
