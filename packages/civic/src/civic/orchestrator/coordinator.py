"""
Coordinator Module - coordinate() implementation

Plans collective action using civic-coordination LangGraph workflows.
"""

from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Optional civic-coordination import
try:
    from civic._internal.coordination import run_coordination, get_campaign_state
    COORDINATION_AVAILABLE = True
except ImportError:
    COORDINATION_AVAILABLE = False


@dataclass
class CoordinationPlan:
    """Plan for collective action."""
    action: str  # plan_testimony, draft_letter, schedule_meeting, notify_supporters
    initiative_id: str
    steps: List[dict] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)
    deadline: Optional[datetime] = None
    status: str = "planning"


def coordinate_action(
    jurisdiction: str,
    initiative_id: str,
    action: str
) -> CoordinationPlan:
    """
    Request coordination support.

    Uses civic-coordination LangGraph workflows to help groups
    take collective action.

    Available actions:
    - plan_testimony: Coordinate testimony at upcoming meeting
    - draft_letter: Collaborative letter writing
    - schedule_meeting: Organize a community meeting
    - notify_supporters: Send updates to supporters

    Args:
        jurisdiction: City/jurisdiction ID
        initiative_id: ID of the initiative to coordinate
        action: Action type

    Returns:
        CoordinationPlan with steps and participants

    Raises:
        ImportError: If civic-coordination not installed
        ValueError: If action is invalid
    """
    # Validate action
    valid_actions = {"plan_testimony", "draft_letter", "schedule_meeting", "notify_supporters"}
    if action not in valid_actions:
        raise ValueError(f"action must be one of {valid_actions}")

    if not COORDINATION_AVAILABLE:
        raise ImportError(
            "civic-coordination not installed. "
            "Install with: pip install civic-coordination"
        )

    # Run LangGraph coordination workflow
    result = run_coordination(jurisdiction, initiative_id)

    # Convert to CoordinationPlan
    return CoordinationPlan(
        action=action,
        initiative_id=initiative_id,
        steps=result.get("steps", []),
        participants=result.get("actors", {}).get("residents", []),
        deadline=result.get("deadline"),
        status=result.get("status", "planning"),
    )


def get_coordination_status(campaign_id: str) -> dict:
    """
    Get status of a running coordination campaign.

    Args:
        campaign_id: ID of the campaign

    Returns:
        Campaign state dict
    """
    if not COORDINATION_AVAILABLE:
        raise ImportError(
            "civic-coordination not installed. "
            "Install with: pip install civic-coordination"
        )

    return get_campaign_state(campaign_id)
