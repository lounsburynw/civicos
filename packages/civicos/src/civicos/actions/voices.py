"""
Voices Module - add_voice() implementation

Adds user voices (support, oppose, question) to items.
"""

from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from civicos._internal.state import StateManager


@dataclass
class Voice:
    """User voice on an item."""
    id: str
    user_id: str
    item_type: str  # "initiative", "agenda_item", "decision"
    item_id: str
    stance: str  # "support", "oppose", "question"
    comment: str
    created_at: datetime = field(default_factory=datetime.now)


def add_voice(
    item_type: str,
    item_id: str,
    stance: str,
    comment: str,
    user_id: str = "anonymous",
    db_path: str = "data/civic_state.db"
) -> Voice:
    """
    Add your voice to an item.

    Express support, opposition, or questions about an initiative,
    agenda item, or decision.

    Args:
        item_type: Type of item ("initiative", "agenda_item", "decision")
        item_id: ID of the item
        stance: Your stance ("support", "oppose", "question")
        comment: Your comment
        user_id: ID of the user
        db_path: Path to database (for testing)

    Returns:
        Created Voice

    Raises:
        ValueError: Invalid stance or item_type
    """
    # Validate stance
    valid_stances = {"support", "oppose", "question"}
    if stance not in valid_stances:
        raise ValueError(f"stance must be one of {valid_stances}")

    # Validate item_type
    valid_types = {"initiative", "agenda_item", "decision"}
    if item_type not in valid_types:
        raise ValueError(f"item_type must be one of {valid_types}")

    # Generate unique ID
    voice_id = f"voice_{uuid.uuid4().hex[:8]}"

    # Store in database
    state = StateManager(db_path)
    result = state.create_voice(
        voice_id=voice_id,
        item_type=item_type,
        item_id=item_id,
        stance=stance,
        comment=comment,
        user_id=user_id,
    )

    # Parse created_at back to datetime
    created_at = result.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif created_at is None:
        created_at = datetime.now()

    return Voice(
        id=result["id"],
        user_id=result["user_id"],
        item_type=result["item_type"],
        item_id=result["item_id"],
        stance=result["stance"],
        comment=result["comment"],
        created_at=created_at,
    )
