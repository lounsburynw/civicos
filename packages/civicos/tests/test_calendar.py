"""Tests for civicos.calendar — upcoming meetings logic.

Validates date filtering, topic matching, field mapping, and sort order
against real behavior, not just import/type checks.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from civicos.calendar import get_upcoming_meetings, Meeting


@pytest.fixture
def mock_state_manager():
    """StateManager stub that returns controlled meeting data."""
    manager = MagicMock()
    return manager


def _make_meeting(days_from_now, title="City Council", body="Council", **kwargs):
    """Helper to create a meeting dict at a relative date offset."""
    dt = datetime.now() + timedelta(days=days_from_now)
    m = {
        "id": kwargs.get("id", f"meeting-{days_from_now}"),
        "title": title,
        "meeting_datetime": dt.isoformat(),
        "body": body,
        "agenda_items": kwargs.get("agenda_items", []),
        "location": kwargs.get("location"),
    }
    return m


class TestGetUpcomingMeetings:
    """Core behavior tests for get_upcoming_meetings."""

    def test_default_window_is_30_days(self, mock_state_manager):
        """Kills mutant 1: days=30 → 31. A meeting between day 30 and 31
        should be excluded with default days=30 but included with days=31."""
        frozen_now = datetime(2026, 6, 1, 12, 0, 0)
        # Meeting at day 30.5 — beyond 30-day window, within 31-day window
        meeting_dt = frozen_now + timedelta(days=30, hours=12)
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                {"id": "m-edge", "title": "Day 30.5", "meeting_datetime": meeting_dt.isoformat(), "body": "C"},
                {"id": "m-safe", "title": "Day 5", "meeting_datetime": (frozen_now + timedelta(days=5)).isoformat(), "body": "C"},
            ]
        }
        with patch("civicos.calendar.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            # Default days=30: cutoff = June 1 + 30d = July 1. Day 30.5 = July 1 12:00 > July 1 00:00 → excluded
            result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        assert result[0].title == "Day 5"

    def test_jurisdiction_passed_to_state_manager(self, mock_state_manager):
        """Kills mutant 3: get_city_state(jurisdiction) → get_city_state(None)."""
        mock_state_manager.get_city_state.return_value = None
        get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        mock_state_manager.get_city_state.assert_called_once_with("city-san-rafael")

    def test_returns_future_meetings_within_window(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="Planning Commission"),
                _make_meeting(10, title="City Council"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 2
        assert result[0].title == "Planning Commission"
        assert result[1].title == "City Council"

    def test_excludes_past_meetings(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(-5, title="Past Meeting"),
                _make_meeting(5, title="Future Meeting"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        assert result[0].title == "Future Meeting"

    def test_excludes_meetings_beyond_window(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="Within Window"),
                _make_meeting(45, title="Beyond 30-day Window"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael", days=30)
        assert len(result) == 1
        assert result[0].title == "Within Window"

    def test_custom_days_window(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="Soon"),
                _make_meeting(50, title="Later"),
                _make_meeting(100, title="Much Later"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael", days=60)
        assert len(result) == 2
        titles = [m.title for m in result]
        assert "Soon" in titles
        assert "Later" in titles
        assert "Much Later" not in titles

    def test_empty_state_returns_empty_list(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = None
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert result == []

    def test_no_meetings_key_returns_empty(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {}
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert result == []

    def test_meeting_exactly_at_now_not_excluded(self, mock_state_manager):
        """Kills mutant 31: `<` → `<=` on now boundary.
        With `<`: `now < now` is False → meeting NOT excluded (included).
        With `<=`: `now <= now` is True → meeting excluded.
        We expect the meeting at exactly now to be included."""
        frozen_now = datetime(2026, 6, 1, 12, 0, 0)
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                {"id": "m-now", "title": "Right Now", "meeting_datetime": frozen_now.isoformat(), "body": "C"},
            ]
        }
        with patch("civicos.calendar.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        assert result[0].title == "Right Now"

    def test_meeting_exactly_at_cutoff_included(self, mock_state_manager):
        """Kills mutant 32: `>` → `>=` on cutoff boundary.
        With `>`: `cutoff > cutoff` is False → meeting NOT excluded (included).
        With `>=`: `cutoff >= cutoff` is True → meeting excluded."""
        frozen_now = datetime(2026, 6, 1, 12, 0, 0)
        cutoff_dt = frozen_now + timedelta(days=30)
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                {"id": "m-edge", "title": "At Cutoff", "meeting_datetime": cutoff_dt.isoformat(), "body": "C"},
            ]
        }
        with patch("civicos.calendar.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = get_upcoming_meetings(mock_state_manager, "city-san-rafael", days=30)
        assert len(result) == 1
        assert result[0].title == "At Cutoff"

    def test_sorted_by_date(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(20, title="Later"),
                _make_meeting(3, title="Soonest"),
                _make_meeting(10, title="Middle"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 3
        assert result[0].title == "Soonest"
        assert result[1].title == "Middle"
        assert result[2].title == "Later"


class TestTopicFiltering:
    """Tests for topic-based meeting filtering."""

    def test_filters_by_topic(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="Housing Meeting", agenda_items=[
                    {"topic": "affordable housing"},
                ]),
                _make_meeting(10, title="Parks Meeting", agenda_items=[
                    {"topic": "park maintenance"},
                ]),
            ]
        }
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["housing"]
        )
        assert len(result) == 1
        assert result[0].title == "Housing Meeting"

    def test_topic_matching_is_case_insensitive(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, agenda_items=[{"topic": "Affordable Housing"}]),
            ]
        }
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["housing"]
        )
        assert len(result) == 1

    def test_no_topics_returns_all(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, agenda_items=[{"topic": "housing"}]),
                _make_meeting(10, agenda_items=[{"topic": "parks"}]),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 2

    def test_topic_matches_project_type_key(self, mock_state_manager):
        """Relational schema uses project_type instead of topic."""
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, agenda_items=[{"project_type": "housing"}]),
            ]
        }
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["housing"]
        )
        assert len(result) == 1

    def test_topic_filter_with_missing_agenda_items_key(self, mock_state_manager):
        """Kills mutants 36/38: agenda_items default [] → None in topic filter.
        A meeting with no agenda_items key should be skipped (not crash)
        when topics are provided."""
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="No Agenda"),  # agenda_items=[] by default in helper
                _make_meeting(10, title="Has Agenda", agenda_items=[{"topic": "housing"}]),
            ]
        }
        # Manually remove the agenda_items key from the first meeting
        mock_state_manager.get_city_state.return_value["meetings"][0].pop("agenda_items")
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["housing"]
        )
        assert len(result) == 1
        assert result[0].title == "Has Agenda"

    def test_topic_filter_item_with_neither_topic_nor_project_type(self, mock_state_manager):
        """Kills mutant 53: `or ''` → `or 'XXXX'` in item_topic fallback.
        An agenda item with neither 'topic' nor 'project_type' should not
        spuriously match. Search for 'xx' which would match 'xxxx' but not ''."""
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="Empty Items", agenda_items=[
                    {"description": "General business"},  # no topic, no project_type
                ]),
            ]
        }
        # 'xx' is a substring of 'xxxx' (mutant) but not of '' (original)
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["xx"]
        )
        # Original: item_topic = "".lower() → "" → "xx" not in "" → no match → excluded
        # Mutant:   item_topic = "xxxx".lower() → "xxxx" → "xx" in "xxxx" → match → included
        assert len(result) == 0

    def test_non_matching_meeting_doesnt_block_later_matches(self, mock_state_manager):
        """Kills mutant 61: `continue` → `break` in topic_match check.
        A non-matching meeting should skip to the next, not stop iteration."""
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, title="Parks Only", agenda_items=[
                    {"topic": "park maintenance"},
                ]),
                _make_meeting(10, title="Housing Meeting", agenda_items=[
                    {"topic": "housing policy"},
                ]),
            ]
        }
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["housing"]
        )
        # With continue: skips Parks, finds Housing → len=1
        # With break: stops after Parks → len=0
        assert len(result) == 1
        assert result[0].title == "Housing Meeting"

    def test_no_matching_topics_returns_empty(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, agenda_items=[{"topic": "parks"}]),
            ]
        }
        result = get_upcoming_meetings(
            mock_state_manager, "city-san-rafael", topics=["housing"]
        )
        assert len(result) == 0


class TestFieldMapping:
    """Tests for field mapping between JSON/relational schemas."""

    def test_meeting_fields_populated(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                _make_meeting(5, id="m-123", title="Council",
                              body="City Council", location="City Hall"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        m = result[0]
        assert m.id == "m-123"
        assert m.title == "Council"
        assert m.body == "City Council"
        assert m.location == "City Hall"
        assert isinstance(m.date, datetime)

    def test_legacy_date_key(self, mock_state_manager):
        """Legacy data uses 'date' instead of 'meeting_datetime'."""
        dt = (datetime.now() + timedelta(days=5)).isoformat()
        mock_state_manager.get_city_state.return_value = {
            "meetings": [{"id": "m-1", "title": "Old", "date": dt, "body": "C"}]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        assert isinstance(result[0].date, datetime)

    def test_missing_date_skips_meeting(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                {"id": "m-1", "title": "No Date", "body": "C"},
                _make_meeting(5, title="Has Date"),
            ]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        assert result[0].title == "Has Date"

    def test_invalid_date_string_uses_fallback(self, mock_state_manager):
        mock_state_manager.get_city_state.return_value = {
            "meetings": [
                {"id": "m-1", "title": "Bad Date", "meeting_datetime": "not-a-date", "body": "C"},
            ]
        }
        # Invalid date falls back to now, which is before the cutoff, so it may or may not appear
        # The key behavior: it doesn't crash
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert isinstance(result, list)

    def test_agenda_items_populated_on_meeting(self, mock_state_manager):
        """Kills mutants 73/96/100/101: agenda_items not set, wrong key, or wrong case."""
        items = [{"topic": "housing"}, {"topic": "parks"}]
        mock_state_manager.get_city_state.return_value = {
            "meetings": [_make_meeting(5, agenda_items=items)]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        assert result[0].agenda_items == items
        assert result[0].agenda_items[0]["topic"] == "housing"

    def test_missing_optional_fields_default(self, mock_state_manager):
        dt = (datetime.now() + timedelta(days=5)).isoformat()
        mock_state_manager.get_city_state.return_value = {
            "meetings": [{"meeting_datetime": dt}]
        }
        result = get_upcoming_meetings(mock_state_manager, "city-san-rafael")
        assert len(result) == 1
        m = result[0]
        assert m.id == ""
        assert m.title == ""
        assert m.body == ""
        assert m.location is None
        assert m.agenda_items == []
