"""
Suggestion Workflow Graph

LangGraph StateGraph for generating proactive suggestions.

Usage:
    from civic._internal.coordination import run_suggestion_workflow

    # Generate suggestions
    result = run_suggestion_workflow("san-rafael", user_id="user_123")
    suggestions = result['suggestions']
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from civic._internal.coordination.suggestion_state import SuggestionState
from civic._internal.coordination.suggestion_nodes import (
    gather_context,
    generate_candidates,
    rank_suggestions,
    filter_suggestions,
    format_suggestions,
    DEFAULT_DB_PATH,
)

logger = logging.getLogger(__name__)


def create_suggestion_workflow(db_path: str = DEFAULT_DB_PATH) -> StateGraph:
    """
    Create the LangGraph suggestion workflow.

    Workflow:
        START → gather_context → generate_candidates → rank → filter → format → END

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured StateGraph (not compiled)
    """
    workflow = StateGraph(SuggestionState)

    # Add nodes
    workflow.add_node("gather_context", gather_context)
    workflow.add_node("generate_candidates", generate_candidates)
    workflow.add_node("rank", rank_suggestions)
    workflow.add_node("filter", filter_suggestions)
    workflow.add_node("format", format_suggestions)

    # Set entry point
    workflow.set_entry_point("gather_context")

    # Linear flow
    workflow.add_edge("gather_context", "generate_candidates")
    workflow.add_edge("generate_candidates", "rank")
    workflow.add_edge("rank", "filter")
    workflow.add_edge("filter", "format")
    workflow.add_edge("format", END)

    return workflow


class SuggestionApp:
    """
    Compiled suggestion workflow with checkpointing.

    Provides a clean interface for generating suggestions.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH, checkpointer=None):
        """
        Initialize the suggestion app.

        Args:
            db_path: Path to SQLite database
            checkpointer: LangGraph checkpointer (default: MemorySaver)
        """
        self.db_path = db_path
        self.checkpointer = checkpointer or MemorySaver()
        self._workflow = create_suggestion_workflow(db_path=db_path)
        self._app = self._workflow.compile(checkpointer=self.checkpointer)

    def run(
        self,
        jurisdiction: str,
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a suggestion workflow.

        Args:
            jurisdiction: City identifier (e.g., "san-rafael")
            user_id: Optional user ID for personalization
            thread_id: Optional thread ID for checkpointing

        Returns:
            Final workflow state with suggestions

        Example:
            app = SuggestionApp()
            result = app.run("san-rafael", user_id="user_123")
            print(result['suggestions'])
        """
        thread_id = thread_id or f"suggestions-{user_id or 'anon'}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        initial_state = {
            "user_id": user_id,
            "jurisdiction": jurisdiction,
            "db_path": self.db_path,
            "user_interests": [],
            "user_subscriptions": [],
            "user_initiatives": [],
            "candidates": [],
            "ranked_suggestions": [],
            "filtered_suggestions": [],
            "suggestions": [],
            "status": "starting",
            "created_at": datetime.now().isoformat(),
            "error": None,
        }

        logger.info(f"Starting suggestion workflow: {thread_id}")

        result = self._app.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        return result

    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current state of a suggestion workflow.

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
            logger.error(f"Failed to get suggestion state: {e}")
            return None


# Default app instance (uses in-memory checkpointing)
_default_suggestion_app: Optional[SuggestionApp] = None


def get_default_suggestion_app(db_path: str = DEFAULT_DB_PATH) -> SuggestionApp:
    """Get or create the default suggestion app."""
    global _default_suggestion_app
    if _default_suggestion_app is None:
        _default_suggestion_app = SuggestionApp(db_path=db_path)
    return _default_suggestion_app


def run_suggestion_workflow(
    jurisdiction: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Run a suggestion workflow using the default app.

    Args:
        jurisdiction: City identifier (e.g., "san-rafael")
        user_id: Optional user ID for personalization
        thread_id: Optional thread ID for checkpointing
        db_path: Database path

    Returns:
        Final workflow state with suggestions

    Example:
        result = run_suggestion_workflow("san-rafael", user_id="user_123")
        for s in result['suggestions']:
            print(f"[{s['type']}] {s['title']}")
    """
    app = get_default_suggestion_app(db_path=db_path)
    return app.run(jurisdiction, user_id, thread_id)


def get_suggestion_state(
    thread_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Get current state of a suggestion workflow.

    Args:
        thread_id: Workflow thread ID
        db_path: Database path

    Returns:
        Current state or None if not found
    """
    app = get_default_suggestion_app(db_path=db_path)
    return app.get_state(thread_id)
