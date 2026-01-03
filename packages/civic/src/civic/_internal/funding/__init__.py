"""
Funding module for linking budget items to federal/state funding sources.

SESSION 444: Initial implementation of budget-funding source linking.
"""

from .matcher import FundingMatcher, extract_cfda_numbers, Match

__all__ = ["FundingMatcher", "extract_cfda_numbers", "Match"]
