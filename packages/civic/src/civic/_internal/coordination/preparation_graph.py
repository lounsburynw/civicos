"""
Preparation Workflow Graph

LangGraph StateGraph for generating meeting preparation materials.

Usage:
    from civic._internal.coordination import run_preparation_workflow

    # Generate preparation materials
    result = run_preparation_workflow(
        agenda_item_id="item_123",
        jurisdiction="san-rafael",
        user_id="user_456"
    )
    prep = result['preparation']
    print(prep['talking_points'])
"""

from typing import Optional, Dict, Any
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from civic._internal.coordination.preparation_state import PreparationState
from civic._internal.coordination.preparation_nodes import (
    load_agenda_item,
    gather_regulatory_context,
    find_allies,
    generate_talking_points,
    compile_logistics,
    format_preparation,
    DEFAULT_DB_PATH,
)

logger = logging.getLogger(__name__)


def create_preparation_workflow(db_path: str = DEFAULT_DB_PATH) -> StateGraph:
    """
    Create the LangGraph preparation workflow.

    Workflow:
        START → load_item → gather_context → find_allies → generate_points → compile_logistics → format → END

    Args:
        db_path: Path to SQLite database

    Returns:
        Configured StateGraph (not compiled)
    """
    workflow = StateGraph(PreparationState)

    # Add nodes
    workflow.add_node("load_item", load_agenda_item)
    workflow.add_node("gather_context", gather_regulatory_context)
    workflow.add_node("find_allies", find_allies)
    workflow.add_node("generate_points", generate_talking_points)
    workflow.add_node("compile_logistics", compile_logistics)
    workflow.add_node("format", format_preparation)

    # Set entry point
    workflow.set_entry_point("load_item")

    # Linear flow
    workflow.add_edge("load_item", "gather_context")
    workflow.add_edge("gather_context", "find_allies")
    workflow.add_edge("find_allies", "generate_points")
    workflow.add_edge("generate_points", "compile_logistics")
    workflow.add_edge("compile_logistics", "format")
    workflow.add_edge("format", END)

    return workflow


class PreparationApp:
    """
    Compiled preparation workflow with checkpointing.

    Provides a clean interface for generating meeting preparation materials.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH, checkpointer=None):
        """
        Initialize the preparation app.

        Args:
            db_path: Path to SQLite database
            checkpointer: LangGraph checkpointer (default: MemorySaver)
        """
        self.db_path = db_path
        self.checkpointer = checkpointer or MemorySaver()
        self._workflow = create_preparation_workflow(db_path=db_path)
        self._app = self._workflow.compile(checkpointer=self.checkpointer)

    def run(
        self,
        agenda_item_id: str,
        jurisdiction: str,
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a preparation workflow.

        Args:
            agenda_item_id: ID of the agenda item to prepare for
            jurisdiction: City identifier (e.g., "san-rafael")
            user_id: Optional user ID for personalization
            thread_id: Optional thread ID for checkpointing

        Returns:
            Final workflow state with preparation materials

        Example:
            app = PreparationApp()
            result = app.run("item_123", "san-rafael", user_id="user_456")
            print(result['preparation']['talking_points'])
        """
        thread_id = thread_id or f"prep-{agenda_item_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        initial_state = {
            "agenda_item_id": agenda_item_id,
            "jurisdiction": jurisdiction,
            "user_id": user_id,
            "db_path": self.db_path,
            "agenda_item": None,
            "meeting": None,
            "topic": "",
            "regulatory_context": {},
            "historical_decisions": [],
            "allies": [],
            "talking_points": [],
            "logistics": {},
            "preparation": {},
            "status": "starting",
            "created_at": datetime.now().isoformat(),
            "error": None,
        }

        logger.info(f"Starting preparation workflow: {thread_id}")

        result = self._app.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        return result

    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current state of a preparation workflow.

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
            logger.error(f"Failed to get preparation state: {e}")
            return None


# Default app instance (uses in-memory checkpointing)
_default_preparation_app: Optional[PreparationApp] = None


def get_default_preparation_app(db_path: str = DEFAULT_DB_PATH) -> PreparationApp:
    """Get or create the default preparation app."""
    global _default_preparation_app
    if _default_preparation_app is None:
        _default_preparation_app = PreparationApp(db_path=db_path)
    return _default_preparation_app


def run_preparation_workflow(
    agenda_item_id: str,
    jurisdiction: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Run a preparation workflow using the default app.

    Args:
        agenda_item_id: ID of the agenda item to prepare for
        jurisdiction: City identifier (e.g., "san-rafael")
        user_id: Optional user ID for personalization
        thread_id: Optional thread ID for checkpointing
        db_path: Database path

    Returns:
        Final workflow state with preparation materials

    Example:
        result = run_preparation_workflow("item_123", "san-rafael")
        prep = result['preparation']
        for point in prep['talking_points']:
            print(f"- {point}")
    """
    app = get_default_preparation_app(db_path=db_path)
    return app.run(agenda_item_id, jurisdiction, user_id, thread_id)


def get_preparation_state(
    thread_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Get current state of a preparation workflow.

    Args:
        thread_id: Workflow thread ID
        db_path: Database path

    Returns:
        Current state or None if not found
    """
    app = get_default_preparation_app(db_path=db_path)
    return app.get_state(thread_id)
