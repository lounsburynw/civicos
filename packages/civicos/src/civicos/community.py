"""
Community Module - whos_with_me() implementation

Finds others who care about a topic using civicos-state.
"""

from typing import List
from dataclasses import dataclass, field

from civicos._internal.state import StateManager


@dataclass
class Community:
    """Others who care about a topic."""
    topic: str
    jurisdiction: str
    follower_count: int = 0
    recent_voices: List[dict] = field(default_factory=list)
    active_initiatives: List[dict] = field(default_factory=list)


def find_community(
    state_manager: StateManager,
    jurisdiction: str,
    topic: str
) -> Community:
    """
    Find others who care about this topic.

    Uses civicos-state to query issues, followers, and initiatives
    related to the topic.

    Args:
        state_manager: StateManager instance
        jurisdiction: City/jurisdiction ID
        topic: Topic to search

    Returns:
        Community with followers, voices, and initiatives
    """
    # Query issues related to topic
    issues = state_manager.query_issues(jurisdiction, topic=topic)

    # Count unique addresses/users
    addresses = set()
    if issues:
        for issue in issues:
            addr = issue.get("address")
            if addr:
                addresses.add(addr)

    return Community(
        topic=topic,
        jurisdiction=jurisdiction,
        follower_count=len(addresses),
        recent_voices=[],  # Phase 2
        active_initiatives=[],  # Phase 2
    )
