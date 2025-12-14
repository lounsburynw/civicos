"""
Coordination Workflow Graph

LangGraph StateGraph for civic coordination campaigns.

Usage:
    from civic._internal.coordination import run_coordination, get_campaign_state

    # Start a campaign
    result = run_coordination("city-san-rafael", "parking_policy")

    # Check state
    state = get_campaign_state("campaign-parking_policy")
"""

from typing import Optional, Dict, Any
from datetime import datetime
import logging
from functools import partial

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from civic._internal.coordination.state import CoordinationState
from civic._internal.coordination.nodes import (
    detect_decision,
    discover_residents,
    should_discover,
    DEFAULT_DB_PATH,
)

logger = logging.getLogger(__name__)


def create_coordination_workflow(db_path: str = DEFAULT_DB_PATH) -> StateGraph:
    """
    Create the LangGraph coordination workflow.

    Workflow:
        START → detect_decision → [conditional] → discover_residents → END
                                      ↓
                                    skip → END

    Args:
        db_path: Path to SQLite database for issue queries

    Returns:
        Configured StateGraph (not compiled)
    """
    workflow = StateGraph(CoordinationState)

    # Create node functions with db_path bound
    def detect_node(state):
        return detect_decision(state, db_path=db_path)

    def discover_node(state):
        return discover_residents(state, db_path=db_path)

    # Add nodes
    workflow.add_node("detect_decision", detect_node)
    workflow.add_node("discover_residents", discover_node)

    # Set entry point
    workflow.set_entry_point("detect_decision")

    # Add conditional edge from detect_decision
    workflow.add_conditional_edges(
        "detect_decision",
        should_discover,
        {
            "discover": "discover_residents",
            "skip": END
        }
    )

    # discover_residents → END
    workflow.add_edge("discover_residents", END)

    return workflow


class CoordinationApp:
    """
    Compiled coordination workflow with checkpointing.

    Provides a clean interface for running campaigns and querying state.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH, checkpointer=None):
        """
        Initialize the coordination app.

        Args:
            db_path: Path to SQLite database
            checkpointer: LangGraph checkpointer (default: MemorySaver)
        """
        self.db_path = db_path
        self.checkpointer = checkpointer or MemorySaver()
        self._workflow = create_coordination_workflow(db_path=db_path)
        self._app = self._workflow.compile(checkpointer=self.checkpointer)

    def run(
        self,
        jurisdiction_id: str,
        decision_type: str,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run a coordination workflow.

        Args:
            jurisdiction_id: City identifier (e.g., "city-san-rafael")
            decision_type: Type of decision (e.g., "parking_policy")
            thread_id: Optional thread ID for resuming (default: auto-generated)

        Returns:
            Final workflow state

        Example:
            app = CoordinationApp()
            result = app.run("city-san-rafael", "parking_policy")
            print(result['decision_score'])
        """
        thread_id = thread_id or f"campaign-{decision_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        initial_state = {
            "jurisdiction_id": jurisdiction_id,
            "decision_type": decision_type,
            "decision_score": 0,
            "actors": {},
            "campaign_id": thread_id,
            "status": "starting",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": None
        }

        logger.info(f"Starting coordination workflow: {thread_id}")

        result = self._app.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}}
        )

        return result

    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current state of a campaign.

        Args:
            thread_id: Campaign thread ID

        Returns:
            Current state or None if not found
        """
        try:
            state = self._app.get_state(
                config={"configurable": {"thread_id": thread_id}}
            )
            return state.values if state else None
        except Exception as e:
            logger.error(f"Failed to get campaign state: {e}")
            return None


# Default app instance (uses in-memory checkpointing)
_default_app: Optional[CoordinationApp] = None


def get_default_app(db_path: str = DEFAULT_DB_PATH) -> CoordinationApp:
    """Get or create the default coordination app."""
    global _default_app
    if _default_app is None:
        _default_app = CoordinationApp(db_path=db_path)
    return _default_app


def run_coordination(
    jurisdiction_id: str,
    decision_type: str,
    thread_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Run a coordination workflow using the default app.

    Args:
        jurisdiction_id: City identifier (e.g., "city-san-rafael")
        decision_type: Type of decision (e.g., "parking_policy")
        thread_id: Optional thread ID for resuming
        db_path: Database path

    Returns:
        Final workflow state
    """
    app = get_default_app(db_path=db_path)
    return app.run(jurisdiction_id, decision_type, thread_id)


def get_campaign_state(
    thread_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Get current state of a campaign.

    Args:
        thread_id: Campaign thread ID
        db_path: Database path

    Returns:
        Current state or None if not found
    """
    app = get_default_app(db_path=db_path)
    return app.get_state(thread_id)
