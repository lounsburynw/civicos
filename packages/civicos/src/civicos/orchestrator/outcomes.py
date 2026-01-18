"""
Outcomes Module - report_outcome() implementation

Records outcomes to close the feedback loop.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from civicos._internal.state import StateManager


@dataclass
class Outcome:
    """Recorded outcome of a decision."""
    id: str
    item_type: str  # initiative, agenda_item, decision
    item_id: str
    outcome: str  # passed, failed, continued, modified
    notes: Optional[str] = None
    vote_breakdown: Optional[Dict[str, int]] = None
    recorded_by: str = "user"  # user or system
    recorded_at: datetime = field(default_factory=datetime.now)


def report_outcome(
    item_id: str,
    outcome: str,
    notes: str = None,
    item_type: str = "agenda_item",
    user_id: str = "anonymous",
    vote_breakdown: Dict[str, int] = None,
    db_path: str = "data/civic_state.db"
) -> Outcome:
    """
    Report outcome of a decision.

    Closes the feedback loop by recording what happened.
    This data improves future recommendations and helps
    learn what coordination strategies work.

    Args:
        item_id: ID of the item
        outcome: Result ("passed", "failed", "continued", "modified")
        notes: Optional notes (e.g., "Passed 4-1, implementation starts Q2")
        item_type: Type of item ("initiative", "agenda_item", "decision")
        user_id: ID of the reporter
        vote_breakdown: Optional vote breakdown (e.g., {"yes": 4, "no": 1})
        db_path: Path to the database

    Returns:
        Recorded Outcome

    Raises:
        ValueError: Invalid outcome or item_type
    """
    # Validate outcome
    valid_outcomes = {"passed", "failed", "continued", "modified"}
    if outcome not in valid_outcomes:
        raise ValueError(f"outcome must be one of {valid_outcomes}")

    # Validate item_type
    valid_item_types = {"initiative", "agenda_item", "decision"}
    if item_type not in valid_item_types:
        raise ValueError(f"item_type must be one of {valid_item_types}")

    # Generate unique ID
    outcome_id = f"out_{uuid.uuid4().hex[:8]}"

    # Store outcome in database
    state_mgr = StateManager(db_path)
    result = state_mgr.create_outcome(
        outcome_id=outcome_id,
        item_type=item_type,
        item_id=item_id,
        outcome=outcome,
        notes=notes,
        vote_breakdown=vote_breakdown,
        recorded_by=user_id,
    )

    # Return Outcome dataclass
    return Outcome(
        id=result["id"],
        item_type=result["item_type"],
        item_id=result["item_id"],
        outcome=result["outcome"],
        notes=result.get("notes"),
        vote_breakdown=result.get("vote_breakdown"),
        recorded_by=result["recorded_by"],
        recorded_at=datetime.fromisoformat(result["recorded_at"]),
    )
