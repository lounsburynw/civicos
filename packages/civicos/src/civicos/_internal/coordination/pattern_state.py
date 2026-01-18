"""
Pattern Learning State Schema

Defines the state object passed between pattern learning workflow nodes.
The PatternLearner learns from outcomes to improve future recommendations.
"""

from typing import TypedDict, List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Pattern:
    """
    A learned pattern from outcome data.

    Records what actions and context led to successful or failed outcomes,
    enabling future strategy suggestions.
    """
    id: str
    topic: str
    jurisdiction: str
    outcome: str  # passed, failed, continued, modified
    actions: List[dict]  # Actions that preceded this outcome
    participant_count: int
    coordination_used: bool
    context: Dict[str, Any]  # Context at time of actions
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "topic": self.topic,
            "jurisdiction": self.jurisdiction,
            "outcome": self.outcome,
            "actions": self.actions,
            "participant_count": self.participant_count,
            "coordination_used": self.coordination_used,
            "context": self.context,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }


@dataclass
class Strategy:
    """
    A suggested strategy based on learned patterns.

    Provides recommendations for how to approach an initiative
    based on successful patterns from similar situations.
    """
    confidence: str  # low, medium, high
    suggestion: str
    recommend_coordination: bool
    avg_supporters: float
    similar_successes: List[Pattern] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for output."""
        return {
            "confidence": self.confidence,
            "suggestion": self.suggestion,
            "recommend_coordination": self.recommend_coordination,
            "avg_supporters": self.avg_supporters,
            "similar_successes": [
                p.to_dict() if isinstance(p, Pattern) else p
                for p in self.similar_successes
            ],
        }


class PatternState(TypedDict):
    """
    State object passed between pattern learning workflow nodes.

    Flow for learning:
        load_outcome → gather_preceding_actions → extract_context → create_pattern → store

    Flow for strategy:
        load_initiative → query_patterns → analyze_patterns → generate_strategy
    """
    # Input context
    db_path: str
    jurisdiction: str

    # For learning from outcome
    outcome_id: Optional[str]
    item_type: Optional[str]  # initiative, agenda_item, decision
    item_id: Optional[str]
    outcome_result: Optional[str]  # passed, failed, continued, modified

    # For strategy suggestion
    initiative_id: Optional[str]
    initiative_topic: Optional[str]

    # Gathered data
    preceding_actions: List[dict]  # Actions that led to this outcome
    context_at_time: Dict[str, Any]  # Context when actions happened
    participants: List[str]  # Who engaged with the item

    # Pattern data
    pattern: Optional[dict]  # The extracted pattern
    stored_patterns: List[dict]  # Patterns loaded from storage

    # Strategy output
    strategy: Optional[dict]  # Generated strategy suggestion

    # Workflow metadata
    status: str  # loading, gathering, extracting, storing, analyzing, complete
    mode: str  # learn or suggest
    created_at: str
    error: Optional[str]
