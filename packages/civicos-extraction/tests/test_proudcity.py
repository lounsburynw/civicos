"""Tests for ProudCity client time extraction.

Regression tests for:
- P.M./A.M. dotted format parsing (commit 9c0c12c0)
- Contextual time extraction avoiding closed session times
"""

import re
import pytest


# Extract the time parsing logic for unit testing without network calls.
# This mirrors _extract_date_from_meeting_page's time extraction.

def _parse_time(hour_s, min_s, ampm_s):
    """Parse hour/minute/ampm into HH:MM string."""
    hour = int(hour_s)
    ampm = ampm_s.replace('.', '').lower() if ampm_s else ''
    if ampm == 'pm' and hour != 12:
        hour += 12
    elif ampm == 'am' and hour == 12:
        hour = 0
    if 6 <= hour <= 22:
        return f"{hour:02d}:{min_s}"
    return None


def extract_meeting_time(text_content):
    """Extract meeting start time from page text.

    Mirrors the logic in ProudCityClient._extract_date_from_meeting_page.
    """
    time_pattern = r'(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)'
    parsed_time = None

    # Pass 1: contextual match
    context_patterns = [
        r'(?:regular\s+meeting|call(?:ed)?\s+to\s+order|meeting\s+(?:at|begins?)|public\s+meeting)\s+(?:at\s+)?(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)',
    ]
    for cp in context_patterns:
        m = re.search(cp, text_content, re.IGNORECASE)
        if m:
            t = _parse_time(m.group(1), m.group(2), m.group(3))
            if t:
                parsed_time = t
                break

    # Pass 2: first valid time not in skip context
    if not parsed_time:
        skip_contexts = ('closed session', 'adjour', 'no later than', 'deadline',
                         'cutoff', 'office hour', 'hours:', 'monday', 'tuesday',
                         'wednesday', 'thursday', 'friday', 'a.m.-', 'am-')
        for line in text_content.split('\n'):
            line_lower = line.strip().lower()
            if any(ctx in line_lower for ctx in skip_contexts):
                continue
            m = re.search(time_pattern, line, re.IGNORECASE)
            if m:
                t = _parse_time(m.group(1), m.group(2), m.group(3))
                if t:
                    parsed_time = t
                    break

    return parsed_time


class TestParseTime:
    """Unit tests for AM/PM time parsing."""

    def test_pm_lowercase(self):
        assert _parse_time("6", "00", "pm") == "18:00"

    def test_pm_uppercase(self):
        assert _parse_time("6", "00", "PM") == "18:00"

    def test_pm_dotted_uppercase(self):
        assert _parse_time("6", "00", "P.M.") == "18:00"

    def test_pm_dotted_lowercase(self):
        assert _parse_time("6", "00", "p.m.") == "18:00"

    def test_pm_partial_dot(self):
        assert _parse_time("6", "00", "P.M") == "18:00"

    def test_am_dotted(self):
        assert _parse_time("10", "00", "A.M.") == "10:00"

    def test_noon_pm(self):
        assert _parse_time("12", "00", "pm") == "12:00"

    def test_midnight_am(self):
        """12 AM should be 0:00, which is outside 6-22 range."""
        assert _parse_time("12", "00", "am") is None

    def test_early_morning_skipped(self):
        """5 AM is outside reasonable meeting hours."""
        assert _parse_time("5", "00", "am") is None

    def test_630_pm(self):
        assert _parse_time("6", "30", "p.m.") == "18:30"

    def test_late_evening(self):
        assert _parse_time("9", "30", "P.M.") == "21:30"


class TestExtractMeetingTime:
    """Integration tests for contextual time extraction from page text."""

    def test_fairfax_regular_meeting_context(self):
        """Should extract 6:30 PM from 'Regular Meeting at 6:30 p.m.' not 5:30 PM closed session."""
        page = """
6:30 pm
Wednesday, April 15, 2026 | 6:30 p.m.
Preceded by a Special Meeting in Closed Session at 5:30 p.m.
Closed Session at 5:30 p.m.
Regular Meeting at 6:30 p.m.
Meetings will adjourn no later than 11pm.
8:30 a.m.-12:00 p.m. & 1:00-5:00 p.m.
"""
        assert extract_meeting_time(page) == "18:30"

    def test_san_rafael_regular_meeting_context(self):
        """Should extract 6:00 PM from 'REGULAR MEETING AT 6:00 P.M.'"""
        page = """
6:00 pm
REGULAR MEETING AT 6:00 P.M.
by 4:00 p.m. the day of the meeting.
Monday-Thursday: 9:00am - 4:00pm
Hours: 8:30 a.m. - 5:00 p.m.
"""
        assert extract_meeting_time(page) == "18:00"

    def test_skips_closed_session(self):
        """Should not extract time from 'Closed Session at 5:30 p.m.' line."""
        page = """
Closed Session at 5:30 p.m.
6:00 pm
"""
        assert extract_meeting_time(page) == "18:00"

    def test_skips_office_hours(self):
        """Should not extract time from office hours."""
        page = """
Hours: 8:30 a.m. - 5:00 p.m.
Meeting at 7:00 p.m.
"""
        assert extract_meeting_time(page) == "19:00"

    def test_skips_adjournment(self):
        """Should not extract time from adjournment notice."""
        page = """
Meetings will adjourn no later than 11pm.
7:00 pm
"""
        # "11pm" on the adjournment line should be skipped
        assert extract_meeting_time(page) == "19:00"

    def test_skips_deadline(self):
        """Should not extract time from comment deadline."""
        page = """
Submit comments before 3:00 p.m. the day of the meeting.
Regular Meeting at 6:00 p.m.
"""
        assert extract_meeting_time(page) == "18:00"

    def test_only_skip_contexts_returns_none(self):
        """If all times are in skip contexts, return None."""
        page = """
Closed Session at 5:30 p.m.
Hours: 8:30 a.m. - 5:00 p.m.
"""
        assert extract_meeting_time(page) is None

    def test_context_match_takes_priority(self):
        """Contextual match should win over first-line time."""
        page = """
7:00 pm
Regular Meeting at 6:30 p.m.
"""
        # "Regular Meeting at 6:30 p.m." should be preferred over bare "7:00 pm"
        assert extract_meeting_time(page) == "18:30"

    def test_call_to_order_context(self):
        page = "The meeting was called to order at 7:00 p.m."
        assert extract_meeting_time(page) == "19:00"

    def test_public_meeting_context(self):
        page = "Public meeting at 6:30 p.m. in the Council Chambers"
        assert extract_meeting_time(page) == "18:30"

    def test_no_times_returns_none(self):
        """Page with no parseable times should return None."""
        page = "Town Council Regular Meeting\nMarch 15, 2026"
        assert extract_meeting_time(page) is None

    def test_fallback_to_header_time(self):
        """If no contextual match, use first valid non-skip time."""
        page = """
6:00 pm
Some agenda content here
"""
        assert extract_meeting_time(page) == "18:00"
