"""
Initiatives Module - start_something() implementation

Creates user-spawned initiatives.
"""

from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from civicos._internal.state import StateManager


@dataclass
class Initiative:
    """User-created initiative."""
    id: str
    topic: str
    title: str
    description: str
    creator_id: str
    jurisdiction: str
    location: Optional[str] = None
    status: str = "active"
    created_at: datetime = field(default_factory=datetime.now)


def start_initiative(
    jurisdiction: str,
    topic: str,
    title: str,
    description: str,
    creator_id: str = "anonymous",
    location: str = None,
    db_path: str = "data/civic_state.db"
) -> Initiative:
    """
    Start a new initiative.

    Creates a user-spawned initiative that others can support.

    Args:
        jurisdiction: City/jurisdiction ID
        topic: Topic category (e.g., "traffic safety")
        title: Initiative title (e.g., "Protected bike lane on 4th St")
        description: Full description
        creator_id: ID of the creator
        location: Optional location
        db_path: Path to database (for testing)

    Returns:
        Created Initiative
    """
    # Generate unique ID
    initiative_id = f"init_{uuid.uuid4().hex[:8]}"

    # Store in database
    state = StateManager(db_path)
    result = state.create_initiative(
        initiative_id=initiative_id,
        jurisdiction_id=jurisdiction,
        topic=topic,
        title=title,
        description=description,
        creator_id=creator_id,
        location=location,
    )

    # Parse created_at back to datetime
    created_at = result.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif created_at is None:
        created_at = datetime.now()

    return Initiative(
        id=result["id"],
        topic=result["topic"],
        title=result["title"],
        description=result["description"],
        creator_id=result["creator_id"],
        jurisdiction=result["jurisdiction_id"],
        location=result.get("location"),
        status=result.get("status", "active"),
        created_at=created_at,
    )
