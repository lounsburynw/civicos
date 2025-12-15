"""
LangGraph Coordination Workflow Prototype

Simple workflow: detect_decision → discover_residents → END

This is the foundation for multi-agent civic coordination.

Usage:
    from coordination_graph import run_coordination, get_campaign_state

    # Start a campaign
    result = run_coordination("city-san-rafael", "parking_policy")

    # Check state
    state = get_campaign_state("campaign-parking_policy")
"""

from typing import TypedDict, Annotated, Literal, Optional, List, Dict, Any
from datetime import datetime
import operator
import sqlite3
import json
import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


# =============================================================================
# STATE SCHEMA
# =============================================================================

def merge_actors(existing: dict, new: dict) -> dict:
    """Custom reducer for merging nested actor dictionaries."""
    result = existing.copy() if existing else {}
    for key, value in new.items():
        if key in result:
            result[key].extend(value)
        else:
            result[key] = value
    return result


class CoordinationState(TypedDict):
    """
    State object passed between workflow nodes.

    This is the core data structure for coordination campaigns.
    LangGraph automatically checkpoints this state between nodes.
    """
    # Decision context
    jurisdiction_id: str
    decision_type: str  # e.g., "parking_policy", "wildfire_prevention"
    decision_score: int  # 0-200, threshold is 100

    # Actor discovery
    actors: Annotated[dict, merge_actors]  # {"residents": [ids], "orgs": [ids]}

    # Campaign metadata
    campaign_id: Optional[str]
    status: str  # flagged, discovering, outreach, active, completed

    # Timestamps
    created_at: str
    updated_at: str

    # Error handling
    error: Optional[str]


# =============================================================================
# AGENT NODES
# =============================================================================

def detect_decision(state: CoordinationState) -> CoordinationState:
    """
    Score a decision for coordination potential.

    Scoring factors:
    - Budget impact (>$100K = 50pts)
    - Policy scope (city-wide = 30pts)
    - Topic sensitivity (wildfire, housing = 20pts)
    - Complaint volume (>20 complaints = 40pts)
    """
    logger.info(f"Detecting decision: {state['decision_type']} for {state['jurisdiction_id']}")

    score = 0

    # Score based on decision type
    high_stakes_types = {
        'wildfire_prevention': 80,  # High public interest
        'parking_policy': 60,       # Affects many residents
        'traffic_signals': 50,      # Safety concern
        'illegal_dumping': 40,      # Environmental
        'budget': 70,               # Financial decisions
        'housing': 90,              # Housing crisis
    }

    decision_type = state['decision_type'].lower()
    for key, points in high_stakes_types.items():
        if key in decision_type:
            score += points
            break

    # Query complaint volume from StateManager
    try:
        conn = sqlite3.connect('data/civic_state.db')
        cursor = conn.cursor()

        # Count related issues
        cursor.execute("""
            SELECT COUNT(*) FROM issues
            WHERE jurisdiction_id = ?
              AND valid_to IS NULL
        """, (state['jurisdiction_id'],))

        complaint_count = cursor.fetchone()[0]
        conn.close()

        # Add points for complaint volume
        if complaint_count > 100:
            score += 50
        elif complaint_count > 50:
            score += 30
        elif complaint_count > 20:
            score += 20

        logger.info(f"Found {complaint_count} complaints, score now: {score}")

    except Exception as e:
        logger.warning(f"Could not query complaints: {e}")

    return {
        **state,
        "decision_score": score,
        "status": "flagged" if score >= 100 else "low_priority",
        "updated_at": datetime.now().isoformat()
    }


def discover_residents(state: CoordinationState) -> CoordinationState:
    """
    Find affected residents using StateManager issue data.

    Discovery sources:
    1. SeeClickFix complaints (by street/type)
    2. Geographic proximity (PostGIS - future)
    3. Issue follows (future)
    """
    logger.info(f"Discovering residents for {state['decision_type']} in {state['jurisdiction_id']}")

    residents = []

    try:
        conn = sqlite3.connect('data/civic_state.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Map decision types to issue queries
        query_patterns = {
            'parking_policy': '%parking%',
            'parking': '%parking%',
            'traffic_signals': '%traffic%',
            'traffic': '%traffic%',
            'wildfire_prevention': '%tree%',
            'wildfire': '%tree%',
            'illegal_dumping': '%dump%',
            'dumping': '%dump%',
        }

        # Find matching pattern
        pattern = None
        decision_lower = state['decision_type'].lower()
        for key, p in query_patterns.items():
            if key in decision_lower:
                pattern = p
                break

        if pattern:
            # Query issues matching the pattern
            cursor.execute("""
                SELECT DISTINCT address, issue_type, status, created_at
                FROM issues
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
                  AND (issue_type LIKE ? OR address LIKE ?)
                ORDER BY created_at DESC
                LIMIT 50
            """, (state['jurisdiction_id'], pattern, pattern))

            for row in cursor.fetchall():
                residents.append({
                    'address': row['address'],
                    'issue_type': row['issue_type'],
                    'status': row['status'],
                    'created_at': row['created_at']
                })

        conn.close()
        logger.info(f"Discovered {len(residents)} affected residents/locations")

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return {
            **state,
            "error": str(e),
            "status": "discovery_failed",
            "updated_at": datetime.now().isoformat()
        }

    return {
        **state,
        "actors": {
            **state.get("actors", {}),
            "residents": residents
        },
        "status": "discovered",
        "updated_at": datetime.now().isoformat()
    }


# =============================================================================
# CONDITIONAL ROUTING
# =============================================================================

def should_discover(state: CoordinationState) -> Literal["discover", "skip"]:
    """Route based on decision score threshold."""
    if state.get("decision_score", 0) >= 100:
        return "discover"
    return "skip"


# =============================================================================
# WORKFLOW DEFINITION
# =============================================================================

def create_coordination_workflow():
    """
    Create the LangGraph coordination workflow.

    Workflow:
        START → detect_decision → [conditional] → discover_residents → END
                                      ↓
                                    skip → END
    """
    workflow = StateGraph(CoordinationState)

    # Add nodes
    workflow.add_node("detect_decision", detect_decision)
    workflow.add_node("discover_residents", discover_residents)

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


# =============================================================================
# WORKFLOW EXECUTION
# =============================================================================

# Global checkpointer (in-memory for prototype, Postgres for production)
checkpointer = MemorySaver()

# Compile workflow
workflow = create_coordination_workflow()
app = workflow.compile(checkpointer=checkpointer)


def run_coordination(
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
        result = run_coordination("city-san-rafael", "parking_policy")
        print(result['decision_score'])  # e.g., 140
        print(len(result['actors']['residents']))  # e.g., 42
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

    result = app.invoke(
        initial_state,
        config={"configurable": {"thread_id": thread_id}}
    )

    return result


def get_campaign_state(thread_id: str) -> Optional[Dict[str, Any]]:
    """
    Get current state of a campaign.

    Args:
        thread_id: Campaign thread ID

    Returns:
        Current state or None if not found
    """
    try:
        state = app.get_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        return state.values if state else None
    except Exception as e:
        logger.error(f"Failed to get campaign state: {e}")
        return None


# =============================================================================
# DEMO / TESTING
# =============================================================================

def demo():
    """Demonstrate the coordination workflow."""
    print("=" * 60)
    print("LangGraph Coordination Workflow Demo")
    print("=" * 60)

    # Test 1: High-stakes decision (should trigger discovery)
    print("\n1. Testing high-stakes decision (parking_policy)...")
    result = run_coordination("city-san-rafael", "parking_policy")

    print(f"   Decision score: {result['decision_score']}")
    print(f"   Status: {result['status']}")
    print(f"   Residents discovered: {len(result.get('actors', {}).get('residents', []))}")

    if result.get('actors', {}).get('residents'):
        print(f"   Sample resident: {result['actors']['residents'][0]}")

    # Test 2: Low-stakes decision (should skip discovery)
    print("\n2. Testing low-stakes decision (other)...")
    result2 = run_coordination("city-san-rafael", "other_topic")

    print(f"   Decision score: {result2['decision_score']}")
    print(f"   Status: {result2['status']}")
    print(f"   Discovery skipped: {result2['status'] == 'low_priority'}")

    # Test 3: Traffic signals
    print("\n3. Testing traffic decision (traffic_signals)...")
    result3 = run_coordination("city-san-rafael", "traffic_signals")

    print(f"   Decision score: {result3['decision_score']}")
    print(f"   Status: {result3['status']}")
    print(f"   Residents discovered: {len(result3.get('actors', {}).get('residents', []))}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo()
