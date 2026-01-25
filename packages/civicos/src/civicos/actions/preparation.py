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
    legal_citations: List[dict] = field(default_factory=list)


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


def _format_legal_citation(entry: dict, entry_type: str) -> Optional[dict]:
    """
    Format a regulatory context entry into a proper legal citation.

    Args:
        entry: Raw entry from regulatory context (bill, ordinance, program)
        entry_type: Type of entry ("state", "federal", "local")

    Returns:
        Formatted citation dict or None if not suitable for citation
    """
    # Skip placeholder entries
    if entry.get("note"):
        return None

    citation_type = entry.get("type", "")
    relevance = entry.get("relevance_score", 0)

    # Skip low-relevance entries (noise)
    if relevance < 0.5:
        return None

    # State legislation (California bills)
    if citation_type == "bill" and entry_type == "state":
        bill_number = entry.get("bill_number", "")
        bill_name = entry.get("bill_name", "")
        if not bill_number:
            return None

        # Format: "Cal. Gov. Code (SB 9)" for enacted, "SB 9" for pending
        status = entry.get("status_label", "")
        if status in ("Passed", "Enacted", "Signed"):
            citation = f"Cal. Gov. Code ({bill_number})"
        else:
            citation = bill_number

        # Get excerpt from relevant sections if available
        sections = entry.get("relevant_sections", [])
        excerpt = ""
        if sections and isinstance(sections[0], dict):
            excerpt = sections[0].get("content", "")[:200]

        return {
            "type": "state_bill",
            "citation": citation,
            "title": bill_name,
            "relevance": round(relevance, 2),
            "excerpt": excerpt,
            "url": entry.get("official_url", ""),
            "requires_local_action": entry.get("requires_local_action", False),
            "local_deadline": entry.get("local_deadline", ""),
        }

    # Federal legislation
    if citation_type == "federal_bill":
        bill_number = entry.get("bill_number", "")
        bill_name = entry.get("bill_name", "")
        if not bill_number:
            return None

        sections = entry.get("relevant_sections", [])
        excerpt = ""
        if sections and isinstance(sections[0], dict):
            excerpt = sections[0].get("content", "")[:200]

        return {
            "type": "federal_bill",
            "citation": bill_number,
            "title": bill_name,
            "relevance": round(relevance, 2),
            "excerpt": excerpt,
            "url": entry.get("official_url", ""),
            "requires_local_action": entry.get("requires_local_action", False),
        }

    # Federal programs
    if citation_type == "federal_program":
        program_name = entry.get("program_name", "")
        if not program_name:
            return None

        cfda = entry.get("cfda_number", "")
        citation = f"{program_name}"
        if cfda:
            citation = f"{program_name} (CFDA {cfda})"

        return {
            "type": "federal_program",
            "citation": citation,
            "title": program_name,
            "relevance": round(relevance, 2),
            "excerpt": entry.get("description", "")[:200],
            "url": "",
            "agency": entry.get("administering_agency", ""),
        }

    # Municipal code sections
    if citation_type in ("ordinance", "county_ordinance"):
        section_num = entry.get("section_number", "")
        section_name = entry.get("section_name", "")
        if not section_num:
            return None

        # Format: "San Rafael Municipal Code § 14.06.030"
        if citation_type == "county_ordinance":
            jurisdiction = entry.get("jurisdiction", "")
            # Extract county name from jurisdiction ID
            county_name = jurisdiction.replace("county-", "").replace("-", " ").title()
            citation = f"{county_name} County Code § {section_num}"
        else:
            citation = f"Municipal Code § {section_num}"

        return {
            "type": citation_type,
            "citation": citation,
            "title": section_name,
            "relevance": round(relevance, 2),
            "excerpt": entry.get("text_preview", "")[:200],
            "url": "",
        }

    return None


def _extract_legal_citations(regulatory_context: dict) -> List[dict]:
    """
    Extract and format legal citations from regulatory context.

    Prioritizes:
    1. Local ordinances (directly applicable)
    2. State bills requiring local implementation
    3. Enacted state legislation
    4. Federal programs

    Args:
        regulatory_context: Result from get_regulatory_context()

    Returns:
        List of formatted citation dicts, sorted by relevance
    """
    citations = []

    # Process local ordinances first (most directly applicable)
    for entry in regulatory_context.get("local", []):
        citation = _format_legal_citation(entry, "local")
        if citation:
            # Boost local citations
            citation["_sort_priority"] = 1
            citations.append(citation)

    # Process state legislation
    for entry in regulatory_context.get("state", []):
        citation = _format_legal_citation(entry, "state")
        if citation:
            # Boost bills requiring local action
            if citation.get("requires_local_action"):
                citation["_sort_priority"] = 2
            else:
                citation["_sort_priority"] = 3
            citations.append(citation)

    # Process federal (programs and bills)
    for entry in regulatory_context.get("federal", []):
        citation = _format_legal_citation(entry, "federal")
        if citation:
            citation["_sort_priority"] = 4
            citations.append(citation)

    # Sort by priority then relevance, take top 5
    citations.sort(key=lambda c: (c.get("_sort_priority", 99), -c.get("relevance", 0)))

    # Remove sort priority from output
    for c in citations:
        c.pop("_sort_priority", None)

    return citations[:5]


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


def _generate_talking_points(
    item: dict,
    regulatory_context: dict,
    legal_citations: List[dict] = None
) -> List[str]:
    """
    Generate talking points based on item, regulatory context, and legal citations.

    When legal citations are available, generates specific, actionable points
    that reference the legal basis for positions.
    """
    points = []
    legal_citations = legal_citations or []

    title = item.get("title", "this item")

    # Basic talking point from item
    points.append(f"I'm here to speak about {title}.")

    # Generate citation-informed talking points
    for citation in legal_citations[:3]:
        citation_type = citation.get("type", "")
        citation_str = citation.get("citation", "")
        citation_title = citation.get("title", "")

        if not citation_str:
            continue

        # Local ordinances - most directly applicable
        if citation_type in ("ordinance", "county_ordinance"):
            points.append(
                f"Cite {citation_str} ({citation_title}) for local requirements."
            )

        # State bills requiring local action - high urgency
        elif citation_type == "state_bill" and citation.get("requires_local_action"):
            deadline = citation.get("local_deadline", "")
            if deadline:
                points.append(
                    f"State law {citation_str} requires local action by {deadline}."
                )
            else:
                points.append(
                    f"Cite {citation_str} - state law requiring local implementation."
                )

        # Enacted state legislation - good legal foundation
        elif citation_type == "state_bill":
            points.append(
                f"Cite {citation_str} for legal foundation on {citation_title.lower() if citation_title else 'this issue'}."
            )

        # Federal programs - funding opportunities
        elif citation_type == "federal_program":
            agency = citation.get("agency", "")
            if agency:
                points.append(
                    f"Federal funding available via {citation_str} ({agency})."
                )
            else:
                points.append(
                    f"Federal funding available via {citation_str}."
                )

        # Federal bills
        elif citation_type == "federal_bill":
            if citation.get("requires_local_action"):
                points.append(
                    f"Federal bill {citation_str} may require local compliance."
                )
            else:
                points.append(
                    f"Federal bill {citation_str} provides relevant policy context."
                )

    # If no legal citations were used, fall back to generic regulatory context
    if len(points) == 1:
        state_bills = regulatory_context.get("state", [])
        for bill in state_bills[:2]:
            if isinstance(bill, dict):
                bill_num = bill.get("bill_number", "")
                bill_name = bill.get("bill_name", "")
                if bill_num:
                    points.append(f"This relates to {bill_num}: {bill_name}.")

        federal_programs = regulatory_context.get("federal", [])
        for program in federal_programs[:1]:
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

    # 4. Extract legal citations from regulatory context
    legal_citations = _extract_legal_citations(regulatory_context)

    # 5. Generate talking points informed by legal citations
    talking_points = _generate_talking_points(item, regulatory_context, legal_citations)

    # 6. Find allies
    meeting_id = meeting.get("id")
    allies = _find_allies(state, jurisdiction, agenda_item_id, meeting_id)

    # 7. Compile logistics
    logistics = _compile_logistics(meeting)

    # 8. Get historical decisions (placeholder - would need what_happened)
    historical_decisions = []

    return Preparation(
        agenda_item_id=agenda_item_id,
        regulatory_context=regulatory_context,
        historical_decisions=historical_decisions,
        talking_points=talking_points,
        allies=allies,
        logistics=logistics,
        legal_citations=legal_citations,
    )
