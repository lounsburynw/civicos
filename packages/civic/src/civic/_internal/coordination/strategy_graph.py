"""
Strategy Suggestions Workflow Graph

LangGraph StateGraph for generating strategy suggestions based on learned patterns.

Usage:
    from civic._internal.coordination import run_strategy_suggestions

    # Get strategy suggestions for a topic
    result = run_strategy_suggestions("san-rafael", "housing")
    for s in result['suggestions']:
        print(f"[{s['type']}] {s['title']}")

    # With user personalization
    result = run_strategy_suggestions(
        "san-rafael", "traffic",
        user_id="user_123"
    )
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from civic._internal.coordination.strategy_state import (
    StrategyState,
    StrategySuggestion,
    PatternAnalysis,
)
from civic._internal.coordination.strategy_nodes import (
    load_context,
    query_topic_patterns,
    analyze_success_factors,
    generate_strategy_suggestions,
    prioritize_suggestions,
    format_output,
    DEFAULT_DB_PATH,
)

logger = logging.getLogger(__name__)


def create_strategy_suggestions_workflow(db_path: str = DEFAULT_DB_PATH) -> StateGraph:
    """
    Create the LangGraph workflow for strategy suggestions.

    Workflow:
        START → load_context → query_topic_patterns → analyze_success_factors
              → generate_strategy_suggestions → prioritize_suggestions
              → format_output → END

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured StateGraph (not compiled)
    """
    workflow = StateGraph(StrategyState)

    # Add nodes
    workflow.add_node("load_context", load_context)
    workflow.add_node("query_topic_patterns", query_topic_patterns)
    workflow.add_node("analyze_success_factors", analyze_success_factors)
    workflow.add_node("generate_strategy_suggestions", generate_strategy_suggestions)
    workflow.add_node("prioritize_suggestions", prioritize_suggestions)
    workflow.add_node("format_output", format_output)

    # Set entry point
    workflow.set_entry_point("load_context")

    # Linear flow
    workflow.add_edge("load_context", "query_topic_patterns")
    workflow.add_edge("query_topic_patterns", "analyze_success_factors")
    workflow.add_edge("analyze_success_factors", "generate_strategy_suggestions")
    workflow.add_edge("generate_strategy_suggestions", "prioritize_suggestions")
    workflow.add_edge("prioritize_suggestions", "format_output")
    workflow.add_edge("format_output", END)

    return workflow


class StrategySuggester:
    """
    Generate strategy suggestions based on learned patterns.

    Analyzes historical outcomes to provide actionable recommendations
    for approaching civic topics.

    Example:
        suggester = StrategySuggester()

        # Get strategy for a topic
        result = suggester.suggest("san-rafael", "housing")
        for s in result['suggestions']:
            print(f"[{s['type']}] {s['title']}")
            print(f"  {s['reason']}")
            print(f"  Action: {s['action']}")
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH, checkpointer=None):
        """
        Initialize the strategy suggester.

        Args:
            db_path: Path to SQLite database
            checkpointer: LangGraph checkpointer (default: MemorySaver)
        """
        self.db_path = db_path
        self.checkpointer = checkpointer or MemorySaver()

        self._workflow = create_strategy_suggestions_workflow(db_path=db_path)
        self._app = self._workflow.compile(checkpointer=self.checkpointer)

    def suggest(
        self,
        jurisdiction: str,
        topic: str,
        user_id: str = None,
        thread_id: str = None,
    ) -> Dict[str, Any]:
        """
        Generate strategy suggestions for a topic.

        Analyzes patterns from historical outcomes to provide
        actionable recommendations.

        Args:
            jurisdiction: City identifier (e.g., "san-rafael")
            topic: Topic to get strategy for (e.g., "housing", "traffic")
            user_id: Optional user ID for personalization
            thread_id: Optional thread ID for checkpointing

        Returns:
            Dictionary with:
            - suggestions: List of strategy suggestions
            - pattern_analysis: Analysis of patterns used
            - status: Workflow status

        Example:
            result = suggester.suggest("san-rafael", "housing")
            print(result['suggestions'][0]['title'])
        """
        thread_id = thread_id or f"strategy-{topic}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        initial_state = {
            "db_path": self.db_path,
            "jurisdiction": jurisdiction,
            "topic": topic,
            "user_id": user_id,
            "existing_initiatives": [],
            "upcoming_decisions": [],
            "user_history": [],
            "success_patterns": [],
            "failure_patterns": [],
            "pattern_analysis": None,
            "raw_suggestions": [],
            "prioritized_suggestions": [],
            "suggestions": [],
            "status": "starting",
            "created_at": datetime.now().isoformat(),
            "error": None,
        }

        logger.info(f"Starting strategy suggestions workflow: {thread_id}")

        result = self._app.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        return result

    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current state of a strategy suggestions workflow.

        Args:
            thread_id: Workflow thread ID

        Returns:
            Current state or None if not found
        """
        try:
            state = self._app.get_state(
                config={"configurable": {"thread_id": thread_id}}
            )
            return state.values if state else None
        except Exception as e:
            logger.error(f"Failed to get strategy state: {e}")
            return None


# Default suggester instance
_default_suggester: Optional[StrategySuggester] = None


def get_default_suggester(db_path: str = DEFAULT_DB_PATH) -> StrategySuggester:
    """Get or create the default strategy suggester."""
    global _default_suggester
    if _default_suggester is None:
        _default_suggester = StrategySuggester(db_path=db_path)
    return _default_suggester


def run_strategy_suggestions(
    jurisdiction: str,
    topic: str,
    user_id: str = None,
    thread_id: str = None,
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """
    Run strategy suggestions using the default suggester.

    Args:
        jurisdiction: City identifier (e.g., "san-rafael")
        topic: Topic to get strategy for
        user_id: Optional user ID for personalization
        thread_id: Optional thread ID for checkpointing
        db_path: Database path

    Returns:
        Dictionary with suggestions, analysis, and status

    Example:
        result = run_strategy_suggestions("san-rafael", "housing")
        for s in result['suggestions']:
            print(f"[{s['priority']}] {s['title']}: {s['action']}")
    """
    suggester = get_default_suggester(db_path=db_path)
    return suggester.suggest(jurisdiction, topic, user_id, thread_id)


def get_strategy_state(
    thread_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Get current state of a strategy suggestions workflow.

    Args:
        thread_id: Workflow thread ID
        db_path: Database path

    Returns:
        Current state or None if not found
    """
    suggester = get_default_suggester(db_path=db_path)
    return suggester.get_state(thread_id)
