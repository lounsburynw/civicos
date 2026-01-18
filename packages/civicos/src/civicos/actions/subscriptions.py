"""
Subscriptions Module - follow() implementation

Manages user subscriptions to items for update notifications.
"""

from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from civicos._internal.state import StateManager


@dataclass
class Subscription:
    """User subscription to an item."""
    id: str
    user_id: str
    item_type: str  # "meeting", "initiative", "topic", "decision"
    item_id: str
    notification_prefs: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


def follow_item(
    item_type: str,
    item_id: str,
    user_id: str = "anonymous",
    notification_prefs: dict = None,
    db_path: str = "data/civic_state.db"
) -> Subscription:
    """
    Follow an item for updates.

    Subscribe to notifications about a meeting, initiative,
    topic, or decision.

    Args:
        item_type: Type ("meeting", "initiative", "topic", "decision")
        item_id: ID of the item
        user_id: ID of the user
        notification_prefs: Optional notification preferences
        db_path: Path to database (for testing)

    Returns:
        Created Subscription

    Raises:
        ValueError: Invalid item_type
    """
    # Validate item_type
    valid_types = {"meeting", "initiative", "topic", "decision"}
    if item_type not in valid_types:
        raise ValueError(f"item_type must be one of {valid_types}")

    # Generate unique ID
    subscription_id = f"sub_{uuid.uuid4().hex[:8]}"

    # Store in database
    state = StateManager(db_path)
    result = state.create_subscription(
        subscription_id=subscription_id,
        item_type=item_type,
        item_id=item_id,
        user_id=user_id,
        notification_prefs=notification_prefs,
    )

    # Parse created_at back to datetime
    created_at = result.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif created_at is None:
        created_at = datetime.now()

    return Subscription(
        id=result["id"],
        user_id=result["user_id"],
        item_type=result["item_type"],
        item_id=result["item_id"],
        notification_prefs=result.get("notification_prefs") or {},
        created_at=created_at,
    )


def unfollow_item(
    subscription_id: str,
    db_path: str = "data/civic_state.db"
) -> bool:
    """
    Unfollow an item.

    Remove a subscription to stop receiving notifications.

    Args:
        subscription_id: ID of the subscription to remove
        db_path: Path to database (for testing)

    Returns:
        True if unsubscribed, False if subscription not found
    """
    state = StateManager(db_path)
    return state.delete_subscription(subscription_id)
