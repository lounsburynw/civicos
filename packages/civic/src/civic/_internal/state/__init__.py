"""
State management for civic data.

Internal module - use `from civic import Civic` instead.
"""

from civic._internal.state.manager import StateManager
from civic._internal.state.models import (
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
