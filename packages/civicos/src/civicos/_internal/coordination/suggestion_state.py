"""
Suggestion Workflow State Schema

Defines the state object passed between suggestion workflow nodes.
"""

from typing import TypedDict, List, Optional
from dataclasses import dataclass


@dataclass
class SuggestionCandidate:
    """A candidate suggestion before ranking."""
    type: str  # upcoming_meeting, trending_initiative, coordination_ready, outcome_pending
    title: str
    reason: str
    action: str  # follow, add_voice, coordinate, report_outcome
    item_id: str
    score: float = 0.0  # Relevance score for ranking


class SuggestionState(TypedDict):
    """
    State object passed between suggestion workflow nodes.

    Flow: gather_context → generate_candidates → rank → filter → format
    """
    # Input context
    user_id: Optional[str]
    jurisdiction: str
    db_path: str

    # User context (gathered)
    user_interests: List[str]  # Topics user cares about
    user_subscriptions: List[dict]  # What user follows
    user_initiatives: List[dict]  # Initiatives user created

    # Candidates (generated)
    candidates: List[dict]  # Raw suggestion candidates

    # Ranked results
    ranked_suggestions: List[dict]  # Sorted by relevance

    # Filtered results (removes already-seen)
    filtered_suggestions: List[dict]

    # Final output
    suggestions: List[dict]  # Formatted for output

    # Workflow metadata
    status: str  # gathering, generating, ranking, filtering, formatting, complete
    created_at: str
    error: Optional[str]
