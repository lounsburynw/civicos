"""
Suggestions Module - suggestions() implementation

Generates proactive suggestions using AI orchestration.
"""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from civicos._internal.state import StateManager


@dataclass
class Suggestion:
    """Proactive suggestion for the user."""
    type: str  # upcoming_meeting, trending_initiative, coordination_ready, outcome_pending
    title: str
    reason: str
    action: str  # follow, add_voice, coordinate, report_outcome
    item_id: str
    priority: int = 0  # Higher = more relevant


def get_suggestions(
    jurisdiction: str,
    user_id: str = None,
    db_path: str = "data/civic_state.db"
) -> List[Suggestion]:
    """
    Get proactive suggestions.

    AI-driven suggestions based on:
    - User interests and history
    - Upcoming meetings matching interests
    - Trending initiatives
    - Coordination opportunities
    - Pending outcomes to report

    Args:
        jurisdiction: City/jurisdiction ID
        user_id: Optional user ID for personalization
        db_path: Path to the database

    Returns:
        List of suggestions sorted by priority
    """
    suggestions = []
    state_mgr = StateManager(db_path)

    # Get user context if user_id provided
    user_subscriptions = []
    user_voices = []
    if user_id:
        user_subscriptions = state_mgr.query_subscriptions(user_id=user_id)
        # Get topics user has engaged with
        user_topics = _extract_user_interests(user_subscriptions, state_mgr)
    else:
        user_topics = []

    # 1. Upcoming meetings matching interests
    suggestions.extend(_get_meeting_suggestions(
        state_mgr, jurisdiction, user_topics, user_id
    ))

    # 2. Trending initiatives (with recent growth in supporters)
    suggestions.extend(_get_trending_initiative_suggestions(
        state_mgr, jurisdiction, user_id
    ))

    # 3. Coordination opportunities (initiatives with 5+ supporters)
    suggestions.extend(_get_coordination_suggestions(
        state_mgr, jurisdiction, user_id
    ))

    # 4. Pending outcomes to report
    suggestions.extend(_get_outcome_suggestions(
        state_mgr, jurisdiction, user_id
    ))

    # Sort by priority (highest first) and return
    return sorted(suggestions, key=lambda s: -s.priority)


def _extract_user_interests(
    subscriptions: List[dict],
    state_mgr: StateManager
) -> List[str]:
    """Extract topics from user subscriptions."""
    topics = set()
    for sub in subscriptions:
        if sub.get("item_type") == "topic":
            topics.add(sub.get("item_id", ""))
        elif sub.get("item_type") == "initiative":
            # Get initiative to find its topic
            init = state_mgr.get_initiative(sub.get("item_id"))
            if init and init.get("topic"):
                topics.add(init["topic"])
    return list(topics)


def _get_meeting_suggestions(
    state_mgr: StateManager,
    jurisdiction: str,
    user_topics: List[str],
    user_id: str = None
) -> List[Suggestion]:
    """Get suggestions for upcoming meetings matching user interests."""
    suggestions = []

    # Get upcoming meetings (next 30 days)
    now = datetime.now()
    cutoff = now + timedelta(days=30)

    city_state = state_mgr.get_city_state(jurisdiction)
    if not city_state:
        return suggestions

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
        if meeting_date.tzinfo is None:
            meeting_date_naive = meeting_date
        else:
            meeting_date_naive = meeting_date.replace(tzinfo=None)

        # Only include future meetings
        if meeting_date_naive < now or meeting_date_naive > cutoff:
            continue

        meeting_id = meeting.get("id", "")
        meeting_title = meeting.get("title", "Upcoming Meeting")

        # Check if user already follows this meeting
        if user_id:
            existing_sub = state_mgr.get_subscription_by_user_item(
                user_id, "meeting", meeting_id
            )
            if existing_sub:
                continue

        # Calculate priority based on topic match and time proximity
        priority = 50  # Base priority

        # Higher priority if matches user topics
        if user_topics:
            agenda_items = meeting.get("full_data", {})
            if isinstance(agenda_items, dict):
                agenda_items = agenda_items.get("agenda_items", [])
            for item in agenda_items if isinstance(agenda_items, list) else []:
                item_title = str(item.get("title", "")).lower()
                item_desc = str(item.get("description", "")).lower()
                for topic in user_topics:
                    if topic.lower() in item_title or topic.lower() in item_desc:
                        priority += 30
                        break

        # Higher priority for sooner meetings
        days_until = (meeting_date_naive - now).days
        if days_until <= 7:
            priority += 20
        elif days_until <= 14:
            priority += 10

        date_str = meeting_date_naive.strftime("%B %d")
        reason = "Matches your interests" if priority > 70 else "Happening soon"

        suggestions.append(Suggestion(
            type="upcoming_meeting",
            title=f"{meeting_title} on {date_str}",
            reason=reason,
            action="follow",
            item_id=meeting_id,
            priority=priority,
        ))

    # Limit to top 3 meeting suggestions
    return sorted(suggestions, key=lambda s: -s.priority)[:3]


def _get_trending_initiative_suggestions(
    state_mgr: StateManager,
    jurisdiction: str,
    user_id: str = None
) -> List[Suggestion]:
    """Get suggestions for trending initiatives."""
    suggestions = []

    # Get active initiatives
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
            existing_sub = state_mgr.get_subscription_by_user_item(
                user_id, "initiative", init_id
            )
            if existing_sub:
                continue

        # Only suggest initiatives with some activity
        if supporter_count < 2 and voice_count < 2:
            continue

        # Calculate priority
        priority = 40 + min(supporter_count * 5, 30) + min(voice_count * 3, 15)

        title = init.get("title", "Initiative")
        topic = init.get("topic", "")

        suggestions.append(Suggestion(
            type="trending_initiative",
            title=f"{supporter_count} people supporting: {title}",
            reason=f"Growing interest in {topic}" if topic else "Gaining momentum",
            action="add_voice",
            item_id=init_id,
            priority=priority,
        ))

    # Limit to top 3
    return sorted(suggestions, key=lambda s: -s.priority)[:3]


def _get_coordination_suggestions(
    state_mgr: StateManager,
    jurisdiction: str,
    user_id: str = None
) -> List[Suggestion]:
    """Get suggestions for initiatives ready for coordination."""
    suggestions = []

    # Get user's initiatives if user_id provided
    if not user_id:
        return suggestions

    initiatives = state_mgr.query_initiatives(
        jurisdiction_id=jurisdiction,
        status="active",
        limit=50
    )

    for init in initiatives:
        # Only suggest for user's own initiatives
        if init.get("creator_id") != user_id:
            continue

        init_id = init.get("id", "")
        supporter_count = init.get("supporter_count", 0)

        # Coordination threshold: 5+ supporters
        if supporter_count < 5:
            continue

        priority = 90  # High priority for coordination-ready

        suggestions.append(Suggestion(
            type="coordination_ready",
            title=f"Your initiative has {supporter_count} supporters",
            reason="Ready to take collective action?",
            action="coordinate",
            item_id=init_id,
            priority=priority,
        ))

    # Limit to top 2
    return sorted(suggestions, key=lambda s: -s.priority)[:2]


def _get_outcome_suggestions(
    state_mgr: StateManager,
    jurisdiction: str,
    user_id: str = None
) -> List[Suggestion]:
    """Get suggestions for pending outcomes to report."""
    suggestions = []

    # Get meetings that have passed but may need outcome reporting
    city_state = state_mgr.get_city_state(jurisdiction)
    if not city_state:
        return suggestions

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

        # Make naive datetime comparable
        if meeting_date.tzinfo is None:
            meeting_date_naive = meeting_date
        else:
            meeting_date_naive = meeting_date.replace(tzinfo=None)

        # Only check meetings in the past week
        if not (past_week <= meeting_date_naive < now):
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
        existing_outcome = state_mgr.get_outcome_for_item("agenda_item", meeting_id)
        if existing_outcome:
            continue

        suggestions.append(Suggestion(
            type="outcome_pending",
            title=f"What happened at {meeting_title}?",
            reason=f"Meeting was on {meeting_date_naive.strftime('%B %d')}",
            action="report_outcome",
            item_id=meeting_id,
            priority=70,
        ))

    # Limit to top 2
    return sorted(suggestions, key=lambda s: -s.priority)[:2]
