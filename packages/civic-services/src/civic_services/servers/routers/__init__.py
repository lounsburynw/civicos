"""
Domain-specific routers for the Civic API.

Decomposed from civic_api_integrated.py (Session 507) to improve maintainability.

Mixin pattern:
- Each mixin contains handlers for a specific domain (meetings, issues, etc.)
- Mixins are inherited by the main AuthenticatedCivicAPIHandler
- This preserves self.send_json, self.path, etc. without additional infrastructure

Post-pilot (Session 508): FastAPI migration will convert these to proper FastAPI routers.
"""

from .base import Router, Route
from .core import CoreMixin

__all__ = [
    'Router',
    'Route',
    'CoreMixin',
]
