"""
Pattern Learning Workflow Nodes

Individual node functions for the pattern learning workflow.
Each node transforms the PatternState.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from statistics import mean
import logging
import uuid
import json

from civic._internal.state import StateManager
from civic._internal.coordination.pattern_state import (
    PatternState,
    Pattern,
    Strategy,
)

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = "data/civic_state.db"


# ─────────── LEARNING NODES ───────────


def load_outcome(state: PatternState) -> PatternState:
    """
    Load outcome data from the database.

    First node in the learning workflow.
    """
    logger.info(f"Loading outcome: {state.get('outcome_id')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    outcome_id = state.get("outcome_id")
    item_type = state.get("item_type")
    item_id = state.get("item_id")

    # If we have outcome_id, load it
    if outcome_id:
        outcome = state_mgr.get_outcome(outcome_id)
        if outcome:
            return {
                **state,
                "item_type": outcome.get("item_type"),
                "item_id": outcome.get("item_id"),
                "outcome_result": outcome.get("outcome"),
                "status": "loaded",
            }
        else:
            return {
                **state,
                "error": f"Outcome not found: {outcome_id}",
                "status": "error",
            }

    # If we have item_type and item_id, load the most recent outcome
    if item_type and item_id:
        outcome = state_mgr.get_outcome_for_item(item_type, item_id)
        if outcome:
            return {
                **state,
                "outcome_id": outcome.get("id"),
                "outcome_result": outcome.get("outcome"),
                "status": "loaded",
            }

    return {
        **state,
        "error": "No outcome specified",
        "status": "error",
    }


def gather_preceding_actions(state: PatternState) -> PatternState:
    """
    Gather actions that preceded this outcome.

    Looks for:
    - Voices (comments/stances) on the item
    - Subscriptions (follows) on the item
    - Coordination events for initiatives
    """
    logger.info(f"Gathering preceding actions for: {state.get('item_id')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    item_type = state.get("item_type")
    item_id = state.get("item_id")
    actions = []
    participants = []

    # Get voices on the item
    voices = state_mgr.query_voices(item_type, item_id, limit=100)
    for voice in voices:
        actions.append({
            "action": "add_voice",
            "stance": voice.get("stance"),
            "user_id": voice.get("user_id"),
            "created_at": voice.get("created_at"),
        })
        if voice.get("user_id"):
            participants.append(voice["user_id"])

    # Get subscriptions on the item
    subs = state_mgr.query_subscriptions(item_type=item_type, item_id=item_id)
    for sub in subs:
        actions.append({
            "action": "follow",
            "user_id": sub.get("user_id"),
            "created_at": sub.get("created_at"),
        })
        if sub.get("user_id") and sub["user_id"] not in participants:
            participants.append(sub["user_id"])

    # Check for coordination events (for initiatives)
    coordination_used = False
    if item_type == "initiative":
        initiative = state_mgr.get_initiative(item_id)
        if initiative:
            # Coordination indicated by high supporter count
            if initiative.get("supporter_count", 0) >= 5:
                coordination_used = True
                actions.append({
                    "action": "coordinate",
                    "supporter_count": initiative.get("supporter_count", 0),
                })

    return {
        **state,
        "preceding_actions": actions,
        "participants": list(set(participants)),
        "status": "gathered",
    }


def extract_context(state: PatternState) -> PatternState:
    """
    Extract context at the time actions happened.

    Captures:
    - Topic from initiative or agenda item
    - Jurisdiction
    - Number of participants
    - Whether coordination was used
    """
    logger.info(f"Extracting context for: {state.get('item_id')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    item_type = state.get("item_type")
    item_id = state.get("item_id")
    jurisdiction = state.get("jurisdiction")

    context = {
        "item_type": item_type,
        "item_id": item_id,
        "jurisdiction": jurisdiction,
    }

    # Get topic from initiative
    if item_type == "initiative":
        initiative = state_mgr.get_initiative(item_id)
        if initiative:
            context["topic"] = initiative.get("topic", "general")
            context["title"] = initiative.get("title")
            context["supporter_count"] = initiative.get("supporter_count", 0)
            context["voice_count"] = initiative.get("voice_count", 0)
            if not jurisdiction:
                jurisdiction = initiative.get("jurisdiction_id")
                context["jurisdiction"] = jurisdiction

    # Check if coordination was used
    actions = state.get("preceding_actions", [])
    coordination_used = any(a.get("action") == "coordinate" for a in actions)
    context["coordination_used"] = coordination_used

    return {
        **state,
        "context_at_time": context,
        "jurisdiction": jurisdiction or state.get("jurisdiction"),
        "status": "extracted",
    }


def create_pattern(state: PatternState) -> PatternState:
    """
    Create a pattern from the gathered data.

    Synthesizes actions and context into a reusable pattern.
    """
    logger.info("Creating pattern from outcome data")

    actions = state.get("preceding_actions", [])
    context = state.get("context_at_time", {})
    participants = state.get("participants", [])

    pattern_id = f"pat_{uuid.uuid4().hex[:8]}"

    pattern = Pattern(
        id=pattern_id,
        topic=context.get("topic", "general"),
        jurisdiction=state.get("jurisdiction", "unknown"),
        outcome=state.get("outcome_result", "unknown"),
        actions=actions,
        participant_count=len(participants),
        coordination_used=context.get("coordination_used", False),
        context=context,
        created_at=datetime.now(),
    )

    return {
        **state,
        "pattern": pattern.to_dict(),
        "status": "created",
    }


def store_pattern(state: PatternState) -> PatternState:
    """
    Store the pattern in the database.

    Patterns are stored in the outcomes table notes field as JSON
    for the MVP. In production, a dedicated patterns table would be used.
    """
    logger.info("Storing pattern")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    pattern = state.get("pattern")
    if not pattern:
        return {
            **state,
            "error": "No pattern to store",
            "status": "error",
        }

    # For MVP, we store patterns by updating the outcome notes
    # with pattern metadata. In production, use a dedicated patterns table.
    outcome_id = state.get("outcome_id")
    if outcome_id:
        # Pattern is already associated with the outcome
        logger.info(f"Pattern {pattern.get('id')} associated with outcome {outcome_id}")

    return {
        **state,
        "status": "stored",
    }


# ─────────── STRATEGY NODES ───────────


def load_initiative(state: PatternState) -> PatternState:
    """
    Load initiative for strategy suggestion.

    First node in the strategy suggestion workflow.
    """
    logger.info(f"Loading initiative: {state.get('initiative_id')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    initiative_id = state.get("initiative_id")
    if not initiative_id:
        return {
            **state,
            "error": "No initiative_id specified",
            "status": "error",
        }

    initiative = state_mgr.get_initiative(initiative_id)
    if not initiative:
        return {
            **state,
            "error": f"Initiative not found: {initiative_id}",
            "status": "error",
        }

    return {
        **state,
        "initiative_topic": initiative.get("topic", "general"),
        "jurisdiction": initiative.get("jurisdiction_id") or state.get("jurisdiction"),
        "status": "loaded",
    }


def query_patterns(state: PatternState) -> PatternState:
    """
    Query patterns matching the initiative's topic and jurisdiction.

    Looks for successful patterns to learn from.
    """
    logger.info(f"Querying patterns for topic: {state.get('initiative_topic')}")

    db_path = state.get("db_path", DEFAULT_DB_PATH)
    state_mgr = StateManager(db_path)

    topic = state.get("initiative_topic", "general")
    jurisdiction = state.get("jurisdiction")

    # Query outcomes to extract patterns
    # Filter for successful outcomes (passed or modified)
    all_outcomes = state_mgr.query_outcomes(
        outcome="passed",
        limit=50
    )

    # Also get modified outcomes (partial wins)
    modified_outcomes = state_mgr.query_outcomes(
        outcome="modified",
        limit=20
    )
    all_outcomes.extend(modified_outcomes)

    patterns = []
    for outcome in all_outcomes:
        item_type = outcome.get("item_type")
        item_id = outcome.get("item_id")

        # Get voices/subscriptions to estimate participant count
        voices = state_mgr.query_voices(item_type, item_id, limit=100)
        subs = state_mgr.query_subscriptions(item_type=item_type, item_id=item_id)

        participant_ids = set()
        for v in voices:
            if v.get("user_id"):
                participant_ids.add(v["user_id"])
        for s in subs:
            if s.get("user_id"):
                participant_ids.add(s["user_id"])

        # Get topic for initiative items
        item_topic = "general"
        coordination_used = False
        if item_type == "initiative":
            initiative = state_mgr.get_initiative(item_id)
            if initiative:
                item_topic = initiative.get("topic", "general")
                coordination_used = initiative.get("supporter_count", 0) >= 5

        # Only include patterns matching topic (fuzzy match)
        if topic.lower() not in item_topic.lower() and item_topic.lower() not in topic.lower():
            # Also check for common topic overlap
            topic_words = set(topic.lower().split())
            item_words = set(item_topic.lower().split())
            if not topic_words & item_words:
                continue

        patterns.append({
            "id": f"pat_{outcome.get('id', 'unknown')[:8]}",
            "topic": item_topic,
            "jurisdiction": jurisdiction or "unknown",
            "outcome": outcome.get("outcome"),
            "participant_count": len(participant_ids),
            "coordination_used": coordination_used,
            "item_id": item_id,
            "item_type": item_type,
        })

    return {
        **state,
        "stored_patterns": patterns,
        "status": "queried",
    }


def analyze_patterns(state: PatternState) -> PatternState:
    """
    Analyze patterns to extract insights.

    Computes:
    - Average participant count for success
    - Coordination usage rate
    - Confidence level based on pattern count
    """
    logger.info("Analyzing patterns")

    patterns = state.get("stored_patterns", [])

    if not patterns:
        return {
            **state,
            "status": "analyzed",
        }

    # Calculate statistics
    participant_counts = [p.get("participant_count", 0) for p in patterns]
    avg_participants = mean(participant_counts) if participant_counts else 0

    coordination_count = sum(1 for p in patterns if p.get("coordination_used"))
    coordination_rate = coordination_count / len(patterns) if patterns else 0

    # Store analysis in context
    analysis = {
        "pattern_count": len(patterns),
        "avg_participants": avg_participants,
        "coordination_rate": coordination_rate,
        "recommend_coordination": coordination_rate > 0.5,
    }

    context = state.get("context_at_time", {})
    context["analysis"] = analysis

    return {
        **state,
        "context_at_time": context,
        "status": "analyzed",
    }


def generate_strategy(state: PatternState) -> PatternState:
    """
    Generate strategy suggestion based on patterns.

    Creates actionable recommendations for the initiative.
    """
    logger.info("Generating strategy suggestion")

    patterns = state.get("stored_patterns", [])
    context = state.get("context_at_time", {})
    analysis = context.get("analysis", {})

    if not patterns:
        strategy = Strategy(
            confidence="low",
            suggestion="No similar precedent found. Consider building initial support.",
            recommend_coordination=False,
            avg_supporters=0,
            similar_successes=[],
        )
    else:
        pattern_count = len(patterns)
        avg_supporters = analysis.get("avg_participants", 0)
        recommend_coordination = analysis.get("recommend_coordination", False)

        # Determine confidence based on pattern count
        if pattern_count >= 5:
            confidence = "high"
        elif pattern_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        # Generate suggestion text
        if recommend_coordination:
            suggestion = f"Similar initiatives succeeded with ~{int(avg_supporters)} supporters using coordinated action."
        else:
            suggestion = f"Similar initiatives succeeded with ~{int(avg_supporters)} supporters."

        if pattern_count > 1:
            suggestion += f" Based on {pattern_count} similar successes."

        strategy = Strategy(
            confidence=confidence,
            suggestion=suggestion,
            recommend_coordination=recommend_coordination,
            avg_supporters=avg_supporters,
            similar_successes=patterns[:3],  # Top 3 patterns
        )

    return {
        **state,
        "strategy": strategy.to_dict(),
        "status": "complete",
    }
