"""
Strategy Suggestions Workflow State Schema

Defines the state object passed between strategy suggestion workflow nodes.
The StrategySuggester provides strategic recommendations based on learned patterns.
"""

from typing import TypedDict, List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class StrategySuggestion:
    """
    A strategic suggestion based on learned patterns.

    Provides actionable recommendations for approaching a civic topic.
    """
    type: str  # build_support, coordinate_action, monitor_decision, engage_officials
    title: str
    reason: str
    action: str  # Specific action to take
    confidence: str  # low, medium, high
    based_on_patterns: int  # Number of patterns supporting this suggestion
    priority: int = 1  # 1 = highest priority

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for output."""
        return {
            "type": self.type,
            "title": self.title,
            "reason": self.reason,
            "action": self.action,
            "confidence": self.confidence,
            "based_on_patterns": self.based_on_patterns,
            "priority": self.priority,
        }


@dataclass
class PatternAnalysis:
    """
    Analysis of patterns for a topic.

    Synthesizes insights from successful patterns.
    """
    topic: str
    pattern_count: int
    avg_supporters: float
    coordination_rate: float  # % of successes that used coordination
    success_rate: float  # % of tracked outcomes that succeeded
    common_actions: List[str]  # Most common actions in successes

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for output."""
        return {
            "topic": self.topic,
            "pattern_count": self.pattern_count,
            "avg_supporters": self.avg_supporters,
            "coordination_rate": self.coordination_rate,
            "success_rate": self.success_rate,
            "common_actions": self.common_actions,
        }


class StrategyState(TypedDict):
    """
    State object passed between strategy suggestion workflow nodes.

    Flow: load_context → query_topic_patterns → analyze_success_factors
          → generate_strategy_suggestions → prioritize_suggestions → format_output
    """
    # Input context
    db_path: str
    jurisdiction: str
    topic: str
    user_id: Optional[str]

    # Context gathered
    existing_initiatives: List[dict]  # Active initiatives on this topic
    upcoming_decisions: List[dict]  # Pending decisions on this topic
    user_history: List[dict]  # User's past engagement (if user_id provided)

    # Pattern data
    success_patterns: List[dict]  # Patterns from successful outcomes
    failure_patterns: List[dict]  # Patterns from failed outcomes
    pattern_analysis: Optional[dict]  # Synthesized analysis

    # Strategy output
    raw_suggestions: List[dict]  # Generated suggestions before prioritization
    prioritized_suggestions: List[dict]  # Sorted by priority
    suggestions: List[dict]  # Final formatted output

    # Workflow metadata
    status: str  # loading, querying, analyzing, generating, prioritizing, complete
    created_at: str
    error: Optional[str]
