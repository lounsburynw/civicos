"""
Tests for query modules.

Tests context, history, calendar, and community modules.
"""

import pytest
from datetime import datetime, timedelta


class TestContextModule:
    """Test context.py (what_applies)."""

    def test_get_regulatory_context_import(self):
        """Can import get_regulatory_context."""
        from civic.context import get_regulatory_context, RegulatoryStack
        assert callable(get_regulatory_context)

    def test_get_regulatory_context_returns_stack(self):
        """get_regulatory_context returns RegulatoryStack."""
        from civic.context import get_regulatory_context
        result = get_regulatory_context("san-rafael-ca", "housing")
        assert result.topic == "housing"
        assert result.jurisdiction == "san-rafael-ca"


class TestHistoryModule:
    """Test history.py (what_happened)."""

    def test_search_decisions_import(self):
        """Can import search_decisions."""
        from civic.history import search_decisions, Decision
        assert callable(search_decisions)


class TestCalendarModule:
    """Test calendar.py (whats_next)."""

    def test_get_upcoming_meetings_import(self):
        """Can import get_upcoming_meetings."""
        from civic.calendar import get_upcoming_meetings, Meeting
        assert callable(get_upcoming_meetings)


class TestCommunityModule:
    """Test community.py (whos_with_me)."""

    def test_find_community_import(self):
        """Can import find_community."""
        from civic.community import find_community, Community
        assert callable(find_community)
