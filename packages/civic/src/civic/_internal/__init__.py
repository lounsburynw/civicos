"""
Internal modules for the Civic package.

These modules are implementation details and should not be imported directly.
Use the public API: from civic import Civic
"""

from civic._internal.state import StateManager, CityState, Meeting, AgendaItem, Issue
from civic._internal.legal import (
    LegislativeCache,
    create_default_cache,
    enrich_opportunity,
    enrich_opportunities_batch,
    find_relevant_bills,
    find_relevant_programs,
)
from civic._internal.coordination import (
    run_coordination,
    get_campaign_state,
    CoordinationState,
    run_suggestion_workflow,
    get_suggestion_state,
    SuggestionState,
)
from civic._internal.jurisdiction import (
    JurisdictionError,
    normalize_jurisdiction,
    display_jurisdiction,
    extract_state,
    is_valid_jurisdiction,
)

__all__ = [
    # State
    "StateManager",
    "CityState",
    "Meeting",
    "AgendaItem",
    "Issue",
    # Legal
    "LegislativeCache",
    "create_default_cache",
    "enrich_opportunity",
    "enrich_opportunities_batch",
    "find_relevant_bills",
    "find_relevant_programs",
    # Coordination
    "run_coordination",
    "get_campaign_state",
    "CoordinationState",
    # Suggestions
    "run_suggestion_workflow",
    "get_suggestion_state",
    "SuggestionState",
    # Jurisdiction utilities
    "JurisdictionError",
    "normalize_jurisdiction",
    "display_jurisdiction",
    "extract_state",
    "is_valid_jurisdiction",
]
