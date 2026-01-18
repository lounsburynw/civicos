"""
State management for civic data.

Internal module - use `from civicos import CivicOS` instead.
"""

from civicos._internal.state.manager import StateManager
from civicos._internal.state.models import (
    CityState,
    Meeting,
    AgendaItem,
    Issue,
)

__all__ = [
    "StateManager",
    "CityState",
    "Meeting",
    "AgendaItem",
    "Issue",
]
