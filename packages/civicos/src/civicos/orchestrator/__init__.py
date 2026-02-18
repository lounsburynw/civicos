"""
Orchestrator Module - AI-driven coordination

Contains:
- suggestions.py - suggestions() - proactive recommendations
- outcomes.py - report_outcome() - feedback loop
"""

from civicos.orchestrator.suggestions import get_suggestions, Suggestion
from civicos.orchestrator.outcomes import report_outcome, Outcome

__all__ = [
    "get_suggestions",
    "Suggestion",
    "report_outcome",
    "Outcome",
]
