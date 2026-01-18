"""
Funding module for linking budget items to federal/state funding sources.

SESSION 444: Initial implementation of budget-funding source linking.
SESSION 445: Added funding reconciliation to validate budget-award alignment.
"""

from .matcher import FundingMatcher, extract_cfda_numbers, Match
from .reconciler import (
    FundingReconciler,
    ReconciliationItem,
    ReconciliationReport,
    reconcile_funding,
)

__all__ = [
    # Matcher exports (Session 444)
    "FundingMatcher",
    "extract_cfda_numbers",
    "Match",
    # Reconciler exports (Session 445)
    "FundingReconciler",
    "ReconciliationItem",
    "ReconciliationReport",
    "reconcile_funding",
]
