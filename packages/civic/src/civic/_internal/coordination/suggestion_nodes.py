"""
Suggestion Workflow Nodes

Individual node functions for the suggestion generation workflow.
Each node transforms the SuggestionState.
"""

from typing import List
from datetime import datetime, timedelta
import logging

from civic._internal.state import StateManager
from civic._internal.coordination.suggestion_state import SuggestionState

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/civic_state.db"


def gather_context(state: SuggestionState) -> SuggestionState:
    """
    Gather user context from database.

    Collects:
    - User subscriptions (what they follow)
    - User topics of interest (from subscriptions)
    - User initiatives (what they created)
    """
    logger.info(f"Gathering context for user: {state.get('user_id', 'anonymous')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)
    user_id = state.get("user_id")

    user_subscriptions = []
    user_interests = []
    user_initiatives = []

    if user_id:
        # Get subscriptions
        user_subscriptions = state_mgr.query_subscriptions(user_id=user_id)

        # Extract interests from subscriptions
        user_interests = _extract_interests(user_subscriptions, state_mgr)

        # Get user's initiatives
        all_initiatives = state_mgr.query_initiatives(
            jurisdiction_id=state.get("jurisdiction"),
            status="active",
            limit=50
        )
        user_initiatives = [
            init for init in all_initiatives
            if init.get("creator_id") == user_id
        ]

    return {
        **state,
        "user_subscriptions": user_subscriptions,
        "user_interests": user_interests,
        "user_initiatives": user_initiatives,
        "status": "gathered",
    }


def _extract_interests(subscriptions: List[dict], state_mgr: StateManager) -> List[str]:
    """Extract topic interests from subscriptions."""
    topics = set()
    for sub in subscriptions:
        if sub.get("item_type") == "topic":
            topics.add(sub.get("item_id", ""))
        elif sub.get("item_type") == "initiative":
            init = state_mgr.get_initiative(sub.get("item_id"))
            if init and init.get("topic"):
                topics.add(init["topic"])
    return list(topics)


def generate_candidates(state: SuggestionState) -> SuggestionState:
    """
    Generate candidate suggestions from multiple sources.

    Sources:
    - Upcoming meetings matching interests
    - Trending initiatives (2+ supporters)
    - Coordination opportunities (5+ supporters)
    - Pending outcomes to report
    """
    logger.info("Generating suggestion candidates")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)
    jurisdiction = state.get("jurisdiction")
    user_id = state.get("user_id")
    user_interests = state.get("user_interests", [])

    candidates = []

    # 1. Meeting suggestions
    candidates.extend(_generate_meeting_candidates(
        state_mgr, jurisdiction, user_interests, user_id
    ))

    # 2. Trending initiative suggestions
    candidates.extend(_generate_trending_candidates(
        state_mgr, jurisdiction, user_id
    ))

    # 3. Coordination suggestions (for user's own initiatives)
    user_initiatives = state.get("user_initiatives", [])
    candidates.extend(_generate_coordination_candidates(
        user_initiatives, user_id
    ))

    # 4. Outcome suggestions
    candidates.extend(_generate_outcome_candidates(
        state_mgr, jurisdiction, user_id
    ))

    return {
        **state,
        "candidates": candidates,
        "status": "generated",
    }


def _generate_meeting_candidates(
    state_mgr: StateManager,
    jurisdiction: str,
    user_interests: List[str],
    user_id: str = None
) -> List[dict]:
    """Generate meeting suggestion candidates."""
    candidates = []
    now = datetime.now()
    cutoff = now + timedelta(days=30)

    city_state = state_mgr.get_city_state(jurisdiction)
    if not city_state:
        return candidates

    meetings = city_state.get("meetings", [])

    for meeting in meetings:
        meeting_date_str = meeting.get("meeting_datetime") or meeting.get("date")
        if not meeting_date_str:
            continue

        try:
            if isinstance(meeting_date_str, str):
                meeting_date = datetime.fromisoformat(
                    meeting_date_str.replace('Z', '+00:00')
                )
            else:
                meeting_date = meeting_date_str
        except (ValueError, TypeError):
            continue

        # Make naive datetime comparable
        if meeting_date.tzinfo is not None:
            meeting_date = meeting_date.replace(tzinfo=None)

        # Only future meetings within 30 days
        if not (now < meeting_date <= cutoff):
            continue

        meeting_id = meeting.get("id", "")
        meeting_title = meeting.get("title", "Upcoming Meeting")

        # Skip if user already follows
        if user_id:
            existing = state_mgr.get_subscription_by_user_item(
                user_id, "meeting", meeting_id
            )
            if existing:
                continue

        # Base score
        score = 50.0

        # Boost for matching interests
        if user_interests:
            agenda_items = meeting.get("full_data", {})
            if isinstance(agenda_items, dict):
                agenda_items = agenda_items.get("agenda_items", [])
            for item in agenda_items if isinstance(agenda_items, list) else []:
                item_title = str(item.get("title", "")).lower()
                item_desc = str(item.get("description", "")).lower()
                for topic in user_interests:
                    if topic.lower() in item_title or topic.lower() in item_desc:
                        score += 30
                        break

        # Boost for sooner meetings
        days_until = (meeting_date - now).days
        if days_until <= 7:
            score += 20
        elif days_until <= 14:
            score += 10

        date_str = meeting_date.strftime("%B %d")
        reason = "Matches your interests" if score > 70 else "Happening soon"

        candidates.append({
            "type": "upcoming_meeting",
            "title": f"{meeting_title} on {date_str}",
            "reason": reason,
            "action": "follow",
            "item_id": meeting_id,
            "score": score,
        })

    return candidates


def _generate_trending_candidates(
    state_mgr: StateManager,
    jurisdiction: str,
    user_id: str = None
) -> List[dict]:
    """Generate trending initiative candidates."""
    candidates = []

    initiatives = state_mgr.query_initiatives(
        jurisdiction_id=jurisdiction,
        status="active",
        limit=20
    )

    for init in initiatives:
        init_id = init.get("id", "")
        supporter_count = init.get("supporter_count", 0)
        voice_count = init.get("voice_count", 0)

        # Skip if user already follows
        if user_id:
            existing = state_mgr.get_subscription_by_user_item(
                user_id, "initiative", init_id
            )
            if existing:
                continue

        # Only suggest initiatives with activity
        if supporter_count < 2 and voice_count < 2:
            continue

        score = 40 + min(supporter_count * 5, 30) + min(voice_count * 3, 15)
        title = init.get("title", "Initiative")
        topic = init.get("topic", "")

        candidates.append({
            "type": "trending_initiative",
            "title": f"{supporter_count} people supporting: {title}",
            "reason": f"Growing interest in {topic}" if topic else "Gaining momentum",
            "action": "add_voice",
            "item_id": init_id,
            "score": score,
        })

    return candidates


def _generate_coordination_candidates(
    user_initiatives: List[dict],
    user_id: str = None
) -> List[dict]:
    """Generate coordination opportunity candidates."""
    candidates = []

    if not user_id:
        return candidates

    for init in user_initiatives:
        init_id = init.get("id", "")
        supporter_count = init.get("supporter_count", 0)

        # Coordination threshold: 5+ supporters
        if supporter_count < 5:
            continue

        candidates.append({
            "type": "coordination_ready",
            "title": f"Your initiative has {supporter_count} supporters",
            "reason": "Ready to take collective action?",
            "action": "coordinate",
            "item_id": init_id,
            "score": 90,  # High priority for coordination-ready
        })

    return candidates


def _generate_outcome_candidates(
    state_mgr: StateManager,
    jurisdiction: str,
    user_id: str = None
) -> List[dict]:
    """Generate pending outcome candidates."""
    candidates = []

    city_state = state_mgr.get_city_state(jurisdiction)
    if not city_state:
        return candidates

    now = datetime.now()
    past_week = now - timedelta(days=7)
    meetings = city_state.get("meetings", [])

    for meeting in meetings:
        meeting_date_str = meeting.get("meeting_datetime") or meeting.get("date")
        if not meeting_date_str:
            continue

        try:
            if isinstance(meeting_date_str, str):
                meeting_date = datetime.fromisoformat(
                    meeting_date_str.replace('Z', '+00:00')
                )
            else:
                meeting_date = meeting_date_str
        except (ValueError, TypeError):
            continue

        if meeting_date.tzinfo is not None:
            meeting_date = meeting_date.replace(tzinfo=None)

        # Only meetings in past week
        if not (past_week <= meeting_date < now):
            continue

        meeting_id = meeting.get("id", "")
        meeting_title = meeting.get("title", "Meeting")

        # Check if user followed this meeting
        if user_id:
            sub = state_mgr.get_subscription_by_user_item(
                user_id, "meeting", meeting_id
            )
            if not sub:
                continue

        # Check if outcome already reported
        existing = state_mgr.get_outcome_for_item("agenda_item", meeting_id)
        if existing:
            continue

        candidates.append({
            "type": "outcome_pending",
            "title": f"What happened at {meeting_title}?",
            "reason": f"Meeting was on {meeting_date.strftime('%B %d')}",
            "action": "report_outcome",
            "item_id": meeting_id,
            "score": 70,
        })

    return candidates


def rank_suggestions(state: SuggestionState) -> SuggestionState:
    """
    Rank candidates by relevance score.

    Sorts candidates by score descending.
    """
    logger.info("Ranking suggestions")

    candidates = state.get("candidates", [])
    ranked = sorted(candidates, key=lambda x: -x.get("score", 0))

    return {
        **state,
        "ranked_suggestions": ranked,
        "status": "ranked",
    }


def filter_suggestions(state: SuggestionState) -> SuggestionState:
    """
    Filter out suggestions user has already seen/acted on.

    Limits to reasonable number per type.
    """
    logger.info("Filtering suggestions")

    ranked = state.get("ranked_suggestions", [])

    # Group by type and limit
    by_type = {}
    for s in ranked:
        stype = s.get("type", "other")
        if stype not in by_type:
            by_type[stype] = []
        by_type[stype].append(s)

    # Limit per type
    limits = {
        "upcoming_meeting": 3,
        "trending_initiative": 3,
        "coordination_ready": 2,
        "outcome_pending": 2,
    }

    filtered = []
    for stype, items in by_type.items():
        limit = limits.get(stype, 2)
        filtered.extend(items[:limit])

    # Re-sort by score
    filtered = sorted(filtered, key=lambda x: -x.get("score", 0))

    return {
        **state,
        "filtered_suggestions": filtered,
        "status": "filtered",
    }


def format_suggestions(state: SuggestionState) -> SuggestionState:
    """
    Format suggestions for output.

    Converts score to priority integer.
    """
    logger.info("Formatting suggestions")

    filtered = state.get("filtered_suggestions", [])

    suggestions = []
    for s in filtered:
        suggestions.append({
            "type": s.get("type"),
            "title": s.get("title"),
            "reason": s.get("reason"),
            "action": s.get("action"),
            "item_id": s.get("item_id"),
            "priority": int(s.get("score", 0)),
        })

    return {
        **state,
        "suggestions": suggestions,
        "status": "complete",
    }
