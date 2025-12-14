"""
Orchestrator Module - AI-driven coordination

Contains:
- suggestions.py - suggestions() - proactive recommendations
- coordinator.py - coordinate() - collective action planning
- outcomes.py - report_outcome() - feedback loop
"""

from civic.orchestrator.suggestions import get_suggestions, Suggestion
from civic.orchestrator.coordinator import coordinate_action, CoordinationPlan
from civic.orchestrator.outcomes import report_outcome, Outcome

__all__ = [
    "get_suggestions",
    "Suggestion",
    "coordinate_action",
    "CoordinationPlan",
    "report_outcome",
    "Outcome",
]
