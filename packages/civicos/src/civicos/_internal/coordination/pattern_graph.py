"""
Pattern Learning Workflow Graph

LangGraph StateGraph for learning from outcomes and suggesting strategies.

Usage:
    from civicos._internal.coordination import PatternLearner, run_pattern_learning

    # Learn from an outcome
    learner = PatternLearner()
    learner.learn_from_outcome("out_12345678")

    # Get success patterns
    patterns = learner.get_success_patterns("housing", "san-rafael")

    # Suggest strategy for initiative
    strategy = learner.suggest_strategy("init_abc123")
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from civicos._internal.coordination.pattern_state import (
    PatternState,
    Pattern,
    Strategy,
)
from civicos._internal.coordination.pattern_nodes import (
    # Learning nodes
    load_outcome,
    gather_preceding_actions,
    extract_context,
    create_pattern,
    store_pattern,
    # Strategy nodes
    load_initiative,
    query_patterns,
    analyze_patterns,
    generate_strategy,
    DEFAULT_DB_PATH,
)

logger = logging.getLogger(__name__)


def create_learning_workflow(db_path: str = DEFAULT_DB_PATH) -> StateGraph:
    """
    Create the LangGraph workflow for learning from outcomes.

    Workflow:
        START → load_outcome → gather_preceding_actions → extract_context
              → create_pattern → store_pattern → END

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured StateGraph (not compiled)
    """
    workflow = StateGraph(PatternState)

    # Add nodes
    workflow.add_node("load_outcome", load_outcome)
    workflow.add_node("gather_preceding_actions", gather_preceding_actions)
    workflow.add_node("extract_context", extract_context)
    workflow.add_node("create_pattern", create_pattern)
    workflow.add_node("store_pattern", store_pattern)

    # Set entry point
    workflow.set_entry_point("load_outcome")

    # Linear flow
    workflow.add_edge("load_outcome", "gather_preceding_actions")
    workflow.add_edge("gather_preceding_actions", "extract_context")
    workflow.add_edge("extract_context", "create_pattern")
    workflow.add_edge("create_pattern", "store_pattern")
    workflow.add_edge("store_pattern", END)

    return workflow


def create_strategy_workflow(db_path: str = DEFAULT_DB_PATH) -> StateGraph:
    """
    Create the LangGraph workflow for suggesting strategies.

    Workflow:
        START → load_initiative → query_patterns → analyze_patterns
              → generate_strategy → END

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured StateGraph (not compiled)
    """
    workflow = StateGraph(PatternState)

    # Add nodes
    workflow.add_node("load_initiative", load_initiative)
    workflow.add_node("query_patterns", query_patterns)
    workflow.add_node("analyze_patterns", analyze_patterns)
    workflow.add_node("generate_strategy", generate_strategy)

    # Set entry point
    workflow.set_entry_point("load_initiative")

    # Linear flow
    workflow.add_edge("load_initiative", "query_patterns")
    workflow.add_edge("query_patterns", "analyze_patterns")
    workflow.add_edge("analyze_patterns", "generate_strategy")
    workflow.add_edge("generate_strategy", END)

    return workflow


class PatternLearner:
    """
    Learn from outcomes to improve future recommendations.

    Provides two main capabilities:
    1. Learn from outcomes - extract patterns from what worked/didn't work
    2. Suggest strategies - recommend approaches based on successful patterns

    Example:
        learner = PatternLearner()

        # Learn from outcome
        pattern = learner.learn_from_outcome("out_12345678")

        # Get success patterns for a topic
        patterns = learner.get_success_patterns("housing")

        # Suggest strategy for initiative
        strategy = learner.suggest_strategy("init_abc123")
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH, checkpointer=None):
        """
        Initialize the pattern learner.

        Args:
            db_path: Path to SQLite database
            checkpointer: LangGraph checkpointer (default: MemorySaver)
        """
        self.db_path = db_path
        self.checkpointer = checkpointer or MemorySaver()

        # Compile workflows
        self._learning_workflow = create_learning_workflow(db_path=db_path)
        self._learning_app = self._learning_workflow.compile(
            checkpointer=self.checkpointer
        )

        self._strategy_workflow = create_strategy_workflow(db_path=db_path)
        self._strategy_app = self._strategy_workflow.compile(
            checkpointer=self.checkpointer
        )

    def learn_from_outcome(
        self,
        outcome_id: str = None,
        item_type: str = None,
        item_id: str = None,
        jurisdiction: str = None,
        thread_id: str = None,
    ) -> Dict[str, Any]:
        """
        Learn from an outcome by extracting patterns.

        What actions preceded this outcome? What was the context?
        Store the pattern for future strategy suggestions.

        Args:
            outcome_id: ID of the outcome to learn from
            item_type: Type of item (if no outcome_id)
            item_id: ID of item (if no outcome_id)
            jurisdiction: Jurisdiction for context
            thread_id: Optional thread ID for checkpointing

        Returns:
            Pattern dictionary with learned information

        Example:
            pattern = learner.learn_from_outcome("out_12345678")
            print(pattern['topic'], pattern['outcome'])
        """
        thread_id = thread_id or f"learn-{outcome_id or item_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        initial_state = {
            "db_path": self.db_path,
            "jurisdiction": jurisdiction,
            "outcome_id": outcome_id,
            "item_type": item_type,
            "item_id": item_id,
            "outcome_result": None,
            "initiative_id": None,
            "initiative_topic": None,
            "preceding_actions": [],
            "context_at_time": {},
            "participants": [],
            "pattern": None,
            "stored_patterns": [],
            "strategy": None,
            "status": "starting",
            "mode": "learn",
            "created_at": datetime.now().isoformat(),
            "error": None,
        }

        logger.info(f"Starting learning workflow: {thread_id}")

        result = self._learning_app.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        return result.get("pattern", {})

    def get_success_patterns(
        self,
        topic: str,
        jurisdiction: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Get patterns that led to successful outcomes.

        Args:
            topic: Topic to search for (e.g., "housing", "traffic")
            jurisdiction: Optional jurisdiction filter

        Returns:
            List of pattern dictionaries

        Example:
            patterns = learner.get_success_patterns("housing")
            for p in patterns:
                print(f"{p['outcome']}: {p['participant_count']} participants")
        """
        # Use strategy workflow to query patterns
        thread_id = f"query-{topic}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Create a dummy initiative state to query patterns
        initial_state = {
            "db_path": self.db_path,
            "jurisdiction": jurisdiction or "",
            "outcome_id": None,
            "item_type": None,
            "item_id": None,
            "outcome_result": None,
            "initiative_id": None,
            "initiative_topic": topic,
            "preceding_actions": [],
            "context_at_time": {},
            "participants": [],
            "pattern": None,
            "stored_patterns": [],
            "strategy": None,
            "status": "starting",
            "mode": "query",
            "created_at": datetime.now().isoformat(),
            "error": None,
        }

        # Run just the query_patterns node
        from civicos._internal.coordination.pattern_nodes import query_patterns
        result = query_patterns(initial_state)

        # Filter for successful outcomes (passed or modified)
        patterns = result.get("stored_patterns", [])
        success_patterns = [
            p for p in patterns
            if p.get("outcome") in ("passed", "modified")
        ]

        return success_patterns

    def suggest_strategy(
        self,
        initiative_id: str,
        thread_id: str = None,
    ) -> Dict[str, Any]:
        """
        Suggest strategy based on successful patterns.

        Args:
            initiative_id: ID of the initiative to suggest strategy for
            thread_id: Optional thread ID for checkpointing

        Returns:
            Strategy dictionary with recommendations

        Example:
            strategy = learner.suggest_strategy("init_abc123")
            print(strategy['suggestion'])
            print(f"Recommend coordination: {strategy['recommend_coordination']}")
        """
        thread_id = thread_id or f"strategy-{initiative_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        initial_state = {
            "db_path": self.db_path,
            "jurisdiction": None,
            "outcome_id": None,
            "item_type": None,
            "item_id": None,
            "outcome_result": None,
            "initiative_id": initiative_id,
            "initiative_topic": None,
            "preceding_actions": [],
            "context_at_time": {},
            "participants": [],
            "pattern": None,
            "stored_patterns": [],
            "strategy": None,
            "status": "starting",
            "mode": "suggest",
            "created_at": datetime.now().isoformat(),
            "error": None,
        }

        logger.info(f"Starting strategy workflow: {thread_id}")

        result = self._strategy_app.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        return result.get("strategy", {})

    def get_state(self, thread_id: str, mode: str = "learn") -> Optional[Dict[str, Any]]:
        """
        Get current state of a pattern learning workflow.

        Args:
            thread_id: Workflow thread ID
            mode: "learn" or "suggest"

        Returns:
            Current state or None if not found
        """
        try:
            app = self._learning_app if mode == "learn" else self._strategy_app
            state = app.get_state(
                config={"configurable": {"thread_id": thread_id}}
            )
            return state.values if state else None
        except Exception as e:
            logger.error(f"Failed to get pattern state: {e}")
            return None


# Default learner instance
_default_learner: Optional[PatternLearner] = None


def get_default_learner(db_path: str = DEFAULT_DB_PATH) -> PatternLearner:
    """Get or create the default pattern learner."""
    global _default_learner
    if _default_learner is None:
        _default_learner = PatternLearner(db_path=db_path)
    return _default_learner


def run_pattern_learning(
    outcome_id: str = None,
    item_type: str = None,
    item_id: str = None,
    jurisdiction: str = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Run pattern learning using the default learner.

    Args:
        outcome_id: ID of the outcome to learn from
        item_type: Type of item (if no outcome_id)
        item_id: ID of item (if no outcome_id)
        jurisdiction: Jurisdiction for context
        db_path: Database path

    Returns:
        Pattern dictionary with learned information

    Example:
        pattern = run_pattern_learning(outcome_id="out_12345678")
        print(pattern['topic'], pattern['outcome'])
    """
    learner = get_default_learner(db_path=db_path)
    return learner.learn_from_outcome(
        outcome_id=outcome_id,
        item_type=item_type,
        item_id=item_id,
        jurisdiction=jurisdiction,
    )


def get_success_patterns(
    topic: str,
    jurisdiction: str = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Get success patterns using the default learner.

    Args:
        topic: Topic to search for
        jurisdiction: Optional jurisdiction filter
        db_path: Database path

    Returns:
        List of pattern dictionaries
    """
    learner = get_default_learner(db_path=db_path)
    return learner.get_success_patterns(topic, jurisdiction)


def suggest_strategy(
    initiative_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Suggest strategy using the default learner.

    Args:
        initiative_id: ID of the initiative
        db_path: Database path

    Returns:
        Strategy dictionary with recommendations
    """
    learner = get_default_learner(db_path=db_path)
    return learner.suggest_strategy(initiative_id)


def get_pattern_state(
    thread_id: str,
    mode: str = "learn",
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Get current state of a pattern learning workflow.

    Args:
        thread_id: Workflow thread ID
        mode: "learn" or "suggest"
        db_path: Database path

    Returns:
        Current state or None if not found
    """
    learner = get_default_learner(db_path=db_path)
    return learner.get_state(thread_id, mode)
