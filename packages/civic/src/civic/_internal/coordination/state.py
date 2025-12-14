"""
Coordination State Schema

Defines the state object passed between LangGraph workflow nodes.
"""

from typing import TypedDict, Annotated, Optional


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
