"""
Strategy Suggestions Workflow Nodes

Individual node functions for the strategy suggestions workflow.
Each node transforms the StrategyState.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from statistics import mean
import logging

from civic._internal.state import StateManager
from civic._internal.coordination.strategy_state import (
    StrategyState,
    StrategySuggestion,
    PatternAnalysis,
)

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/civic_state.db"


def load_context(state: StrategyState) -> StrategyState:
    """
    Load context for strategy suggestions.

    Gathers:
    - Existing initiatives on the topic
    - Upcoming decisions on the topic
    - User's engagement history (if user_id provided)
    """
    logger.debug(f"Loading context for topic: {state.get('topic')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    jurisdiction = state.get("jurisdiction")
    topic = state.get("topic", "general")
    user_id = state.get("user_id")

    # Get existing initiatives on this topic
    initiatives = state_mgr.query_initiatives(
        jurisdiction_id=jurisdiction,
        topic=topic,
        limit=20
    )

    # Get user's history if user_id provided
    user_history = []
    if user_id:
        # Get user's subscriptions (subscriptions track user_id)
        subs = state_mgr.query_subscriptions(user_id=user_id)
        for s in subs:
            user_history.append({
                "action": "follow",
                "item_type": s.get("item_type"),
                "item_id": s.get("item_id"),
            })

        # For each initiative the user follows, check if they voiced
        for init in initiatives:
            init_id = init.get("id")
            if init_id:
                voices = state_mgr.query_voices("initiative", init_id, limit=100)
                for v in voices:
                    if v.get("user_id") == user_id:
                        user_history.append({
                            "action": "voice",
                            "item_type": "initiative",
                            "item_id": init_id,
                            "stance": v.get("stance"),
                        })

    # Get upcoming decisions (meetings with agenda items)
    # For MVP, we don't have a direct meetings table, so use empty list
    upcoming_decisions = []

    return {
        **state,
        "existing_initiatives": [i for i in initiatives if i],
        "upcoming_decisions": upcoming_decisions,
        "user_history": user_history,
        "status": "context_loaded",
    }


def query_topic_patterns(state: StrategyState) -> StrategyState:
    """
    Query patterns related to the topic.

    Finds both success and failure patterns to learn from.
    """
    logger.debug(f"Querying patterns for topic: {state.get('topic')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    topic = state.get("topic", "general")
    jurisdiction = state.get("jurisdiction")

    # Query all outcomes
    all_outcomes = state_mgr.query_outcomes(limit=100)

    success_patterns = []
    failure_patterns = []

    for outcome in all_outcomes:
        item_type = outcome.get("item_type")
        item_id = outcome.get("item_id")
        result = outcome.get("outcome")

        # Get participation data
        voices = state_mgr.query_voices(item_type, item_id, limit=100)
        subs = state_mgr.query_subscriptions(item_type=item_type, item_id=item_id)

        participant_ids = set()
        stance_counts = {"support": 0, "oppose": 0, "neutral": 0}
        for v in voices:
            if v.get("user_id"):
                participant_ids.add(v["user_id"])
            stance = v.get("stance", "neutral")
            stance_counts[stance] = stance_counts.get(stance, 0) + 1

        for s in subs:
            if s.get("user_id"):
                participant_ids.add(s["user_id"])

        # Get topic from initiative
        item_topic = "general"
        coordination_used = False
        if item_type == "initiative":
            initiative = state_mgr.get_initiative(item_id)
            if initiative:
                item_topic = initiative.get("topic", "general")
                coordination_used = initiative.get("supporter_count", 0) >= 5

        # Check topic match (fuzzy)
        topic_match = (
            topic.lower() in item_topic.lower() or
            item_topic.lower() in topic.lower() or
            bool(set(topic.lower().split()) & set(item_topic.lower().split()))
        )

        if not topic_match:
            continue

        pattern = {
            "id": f"pat_{outcome.get('id', 'unknown')[:8]}",
            "topic": item_topic,
            "jurisdiction": jurisdiction or "unknown",
            "outcome": result,
            "participant_count": len(participant_ids),
            "coordination_used": coordination_used,
            "stance_counts": stance_counts,
            "item_id": item_id,
            "item_type": item_type,
        }

        if result in ("passed", "modified"):
            success_patterns.append(pattern)
        elif result in ("failed", "rejected"):
            failure_patterns.append(pattern)

    return {
        **state,
        "success_patterns": success_patterns,
        "failure_patterns": failure_patterns,
        "status": "patterns_queried",
    }


def analyze_success_factors(state: StrategyState) -> StrategyState:
    """
    Analyze patterns to identify success factors.

    Computes:
    - Average supporter count for success
    - Coordination usage rate
    - Common actions in successes
    - Success rate overall
    """
    logger.debug("Analyzing success factors")

    success_patterns = state.get("success_patterns", [])
    failure_patterns = state.get("failure_patterns", [])
    topic = state.get("topic", "general")

    total_patterns = len(success_patterns) + len(failure_patterns)
    if total_patterns == 0:
        # No patterns found
        analysis = PatternAnalysis(
            topic=topic,
            pattern_count=0,
            avg_supporters=0,
            coordination_rate=0,
            success_rate=0,
            common_actions=[],
        )
        return {
            **state,
            "pattern_analysis": analysis.to_dict(),
            "status": "analyzed",
        }

    # Calculate success statistics
    success_count = len(success_patterns)
    success_rate = success_count / total_patterns if total_patterns > 0 else 0

    # Avg supporters in successes
    if success_patterns:
        participant_counts = [p.get("participant_count", 0) for p in success_patterns]
        avg_supporters = mean(participant_counts) if participant_counts else 0
    else:
        avg_supporters = 0

    # Coordination rate in successes
    if success_patterns:
        coordination_count = sum(1 for p in success_patterns if p.get("coordination_used"))
        coordination_rate = coordination_count / len(success_patterns)
    else:
        coordination_rate = 0

    # Identify common actions (based on stance distribution in successes)
    common_actions = []
    total_support = sum(
        p.get("stance_counts", {}).get("support", 0) for p in success_patterns
    )
    total_oppose = sum(
        p.get("stance_counts", {}).get("oppose", 0) for p in success_patterns
    )

    if total_support > total_oppose:
        common_actions.append("build_support")
    if coordination_rate > 0.5:
        common_actions.append("coordinate_action")
    if avg_supporters >= 5:
        common_actions.append("mobilize_community")

    analysis = PatternAnalysis(
        topic=topic,
        pattern_count=len(success_patterns),
        avg_supporters=avg_supporters,
        coordination_rate=coordination_rate,
        success_rate=success_rate,
        common_actions=common_actions,
    )

    return {
        **state,
        "pattern_analysis": analysis.to_dict(),
        "status": "analyzed",
    }


def generate_strategy_suggestions(state: StrategyState) -> StrategyState:
    """
    Generate strategy suggestions based on analysis.

    Creates actionable recommendations for approaching the topic.
    """
    logger.debug("Generating strategy suggestions")

    analysis = state.get("pattern_analysis", {})
    success_patterns = state.get("success_patterns", [])
    existing_initiatives = state.get("existing_initiatives", [])
    topic = state.get("topic", "general")

    suggestions = []

    pattern_count = analysis.get("pattern_count", 0)
    avg_supporters = analysis.get("avg_supporters", 0)
    coordination_rate = analysis.get("coordination_rate", 0)
    success_rate = analysis.get("success_rate", 0)

    # Determine confidence based on pattern count
    if pattern_count >= 5:
        base_confidence = "high"
    elif pattern_count >= 2:
        base_confidence = "medium"
    else:
        base_confidence = "low"

    # Suggestion 1: Build support (always applicable)
    if avg_supporters > 0:
        support_reason = f"Successful initiatives averaged {int(avg_supporters)} supporters"
    else:
        support_reason = "Building community support increases likelihood of success"

    suggestions.append(StrategySuggestion(
        type="build_support",
        title=f"Build Support for {topic.title()}",
        reason=support_reason,
        action=f"Start or join an initiative and recruit at least {max(5, int(avg_supporters))} supporters",
        confidence=base_confidence,
        based_on_patterns=pattern_count,
        priority=1,
    ))

    # Suggestion 2: Coordinate action (if high coordination rate)
    if coordination_rate > 0.3:
        coord_pct = int(coordination_rate * 100)
        suggestions.append(StrategySuggestion(
            type="coordinate_action",
            title="Use Coordinated Action",
            reason=f"{coord_pct}% of successful initiatives used coordinated action",
            action="Organize a group to attend meetings or submit unified comments",
            confidence=base_confidence,
            based_on_patterns=pattern_count,
            priority=2 if coordination_rate > 0.5 else 3,
        ))

    # Suggestion 3: Join existing initiative (if there are active ones)
    active_initiatives = [i for i in existing_initiatives if i.get("status") == "active"]
    if active_initiatives:
        top_init = active_initiatives[0]
        suggestions.append(StrategySuggestion(
            type="join_initiative",
            title=f"Join: {top_init.get('title', 'Active Initiative')[:40]}",
            reason="Active initiative already working on this topic",
            action=f"Add your voice to initiative {top_init.get('id', '')}",
            confidence="high",
            based_on_patterns=1,
            priority=1,
        ))

    # Suggestion 4: Monitor decisions (if no active work)
    if not active_initiatives and pattern_count == 0:
        suggestions.append(StrategySuggestion(
            type="monitor_decision",
            title=f"Monitor {topic.title()} Decisions",
            reason="No active initiatives on this topic - start by tracking decisions",
            action="Subscribe to notifications for this topic",
            confidence="low",
            based_on_patterns=0,
            priority=3,
        ))

    # Suggestion 5: Learn from failures (if there are failure patterns)
    failure_patterns = state.get("failure_patterns", [])
    if failure_patterns:
        avg_failed_support = mean([
            p.get("participant_count", 0) for p in failure_patterns
        ]) if failure_patterns else 0

        if avg_failed_support < avg_supporters:
            suggestions.append(StrategySuggestion(
                type="avoid_pitfall",
                title="Avoid Common Pitfalls",
                reason=f"Failed initiatives averaged only {int(avg_failed_support)} supporters",
                action="Ensure broad support before advancing to decision stage",
                confidence=base_confidence,
                based_on_patterns=len(failure_patterns),
                priority=2,
            ))

    return {
        **state,
        "raw_suggestions": [s.to_dict() for s in suggestions],
        "status": "generated",
    }


def prioritize_suggestions(state: StrategyState) -> StrategyState:
    """
    Prioritize suggestions by relevance and confidence.

    Sorts by:
    1. Priority (lower = higher priority)
    2. Confidence (high > medium > low)
    3. Pattern count (more patterns = more reliable)
    """
    logger.debug("Prioritizing suggestions")

    raw_suggestions = state.get("raw_suggestions", [])

    # Score each suggestion
    confidence_scores = {"high": 3, "medium": 2, "low": 1}

    def score_suggestion(s: dict) -> tuple:
        priority = s.get("priority", 99)
        confidence = confidence_scores.get(s.get("confidence", "low"), 0)
        patterns = s.get("based_on_patterns", 0)
        return (-priority, -confidence, -patterns)  # Negative for descending sort

    prioritized = sorted(raw_suggestions, key=score_suggestion)

    # Re-assign priority numbers
    for i, s in enumerate(prioritized, 1):
        s["priority"] = i

    return {
        **state,
        "prioritized_suggestions": prioritized,
        "status": "prioritized",
    }


def format_output(state: StrategyState) -> StrategyState:
    """
    Format suggestions for final output.

    Ensures consistent structure and adds metadata.
    """
    logger.debug("Formatting strategy suggestions output")

    prioritized = state.get("prioritized_suggestions", [])
    analysis = state.get("pattern_analysis", {})

    # Add summary to each suggestion
    formatted = []
    for s in prioritized:
        formatted.append({
            "type": s.get("type"),
            "title": s.get("title"),
            "reason": s.get("reason"),
            "action": s.get("action"),
            "confidence": s.get("confidence"),
            "priority": s.get("priority"),
        })

    return {
        **state,
        "suggestions": formatted,
        "status": "complete",
    }
