"""
Internal modules for the Civic package.

These modules are implementation details and should not be imported directly.
Use the public API: from civicos import CivicOS
"""

from civicos._internal.state import StateManager, CityState, Meeting, AgendaItem, Issue
from civicos._internal.legal import (
    LegislativeCache,
    create_default_cache,
    enrich_opportunity,
    enrich_opportunities_batch,
    find_relevant_bills,
    find_relevant_programs,
)
from civicos._internal.jurisdiction import (
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
    # Jurisdiction utilities
    "JurisdictionError",
    "normalize_jurisdiction",
    "display_jurisdiction",
    "extract_state",
    "is_valid_jurisdiction",
]
