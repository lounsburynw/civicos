"""
Coordination Workflow Nodes

Agent nodes for the LangGraph coordination workflow.
"""

from typing import Literal
from datetime import datetime
import sqlite3
import logging

from civic._internal.coordination.state import CoordinationState

logger = logging.getLogger(__name__)

# Default database path - can be overridden
DEFAULT_DB_PATH = "data/civic_state.db"


def detect_decision(
    state: CoordinationState,
    db_path: str = DEFAULT_DB_PATH
) -> CoordinationState:
    """
    Score a decision for coordination potential.

    Scoring factors:
    - Budget impact (>$100K = 50pts)
    - Policy scope (city-wide = 30pts)
    - Topic sensitivity (wildfire, housing = 20pts)
    - Complaint volume (>20 complaints = 40pts)
    """
    logger.debug(f"Detecting decision: {state['decision_type']} for {state['jurisdiction_id']}")

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
        conn = sqlite3.connect(db_path)
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

        logger.debug(f"Found {complaint_count} complaints, score now: {score}")

    except Exception as e:
        logger.debug(f"Could not query complaints: {e}")

    return {
        **state,
        "decision_score": score,
        "status": "flagged" if score >= 100 else "low_priority",
        "updated_at": datetime.now().isoformat()
    }


def discover_residents(
    state: CoordinationState,
    db_path: str = DEFAULT_DB_PATH
) -> CoordinationState:
    """
    Find affected residents using StateManager issue data.

    Discovery sources:
    1. SeeClickFix complaints (by street/type)
    2. Geographic proximity (PostGIS - future)
    3. Issue follows (future)
    """
    logger.debug(f"Discovering residents for {state['decision_type']} in {state['jurisdiction_id']}")

    residents = []

    try:
        conn = sqlite3.connect(db_path)
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
        logger.debug(f"Discovered {len(residents)} affected residents/locations")

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


def should_discover(state: CoordinationState) -> Literal["discover", "skip"]:
    """Route based on decision score threshold."""
    if state.get("decision_score", 0) >= 100:
        return "discover"
    return "skip"
