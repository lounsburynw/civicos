"""
Regression test for upcoming_verb_ignores_jurisdiction.

execute_upcoming() must query meetings for the requested jurisdiction (jid),
not the CivicOS instance's jurisdiction. Previously, civic.whats_next() was
hardwired to civic.jurisdiction, so cross-jurisdiction fan-out returned the
wrong jurisdiction's events.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from civicos_services.query.verbs import execute_upcoming, _get_upcoming_meetings
from civicos_services.query.models import UpcomingRequest


def _make_meeting(jid, title, hours_from_now=24):
    """Create a meeting dict as storage backends return them."""
    dt = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
    return {
        "id": f"{jid}-meeting-1",
        "title": title,
        "meeting_datetime": dt.isoformat(),
        "meeting_type": "Regular Meeting",
        "location": f"{jid} City Hall",
    }


def _mock_storage(meetings_by_jid):
    """Create a mock storage that returns different meetings per jurisdiction."""
    storage = MagicMock()

    def get_meetings(jurisdiction_id, since=None, until=None, **kwargs):
        return meetings_by_jid.get(jurisdiction_id, [])

    def get_agenda_items(meeting_id=None, **kwargs):
        return []

    storage.get_meetings = MagicMock(side_effect=get_meetings)
    storage.get_agenda_items = MagicMock(side_effect=get_agenda_items)
    return storage


def test_get_upcoming_meetings_uses_explicit_jurisdiction():
    """_get_upcoming_meetings queries the given jurisdiction, not some default."""
    meetings_by_jid = {
        "city-san-rafael": [_make_meeting("city-san-rafael", "SR Planning Commission")],
        "city-tiburon": [_make_meeting("city-tiburon", "Tiburon Town Council")],
    }
    storage = _mock_storage(meetings_by_jid)

    # Query for tiburon
    result = _get_upcoming_meetings(storage, "city-tiburon", days=30)

    # Must get tiburon's meeting, not san-rafael's
    assert len(result) == 1
    assert result[0].title == "Tiburon Town Council"
    assert result[0].id == "city-tiburon-meeting-1"

    # Verify storage was called with the correct jurisdiction
    storage.get_meetings.assert_called_once()
    call_kwargs = storage.get_meetings.call_args
    assert call_kwargs.kwargs.get("jurisdiction_id") == "city-tiburon"


def test_execute_upcoming_uses_request_jurisdiction():
    """execute_upcoming queries request.jurisdiction, not civic.jurisdiction."""
    meetings_by_jid = {
        "city-san-rafael": [_make_meeting("city-san-rafael", "SR Bicycle Committee")],
        "city-tiburon": [_make_meeting("city-tiburon", "Tiburon Town Council")],
    }
    storage = _mock_storage(meetings_by_jid)

    # Simulate a CivicOS instance for san-rafael
    civic = MagicMock()
    civic.jurisdiction = "city-san-rafael"
    civic.storage = storage

    # But request is for tiburon
    request = UpcomingRequest(
        jurisdiction="city-tiburon",
        types=["meetings"],
        days=30,
    )

    response = asyncio.run(
        execute_upcoming(request, civic, jurisdiction="city-san-rafael")
    )

    # Results must be tiburon's meetings, not san-rafael's
    assert len(response.results) == 1
    assert response.results[0].title == "Tiburon Town Council"
    assert response.results[0].ref == "meeting:city-tiburon:city-tiburon-meeting-1"
    assert response.results[0].type == "meeting"


def test_execute_upcoming_falls_back_to_jurisdiction_param():
    """When request.jurisdiction is None, uses the jurisdiction parameter."""
    meetings_by_jid = {
        "city-belvedere": [_make_meeting("city-belvedere", "Belvedere City Council")],
    }
    storage = _mock_storage(meetings_by_jid)

    civic = MagicMock()
    civic.jurisdiction = "city-san-rafael"
    civic.storage = storage

    request = UpcomingRequest(
        jurisdiction=None,
        types=["meetings"],
        days=30,
    )

    response = asyncio.run(
        execute_upcoming(request, civic, jurisdiction="city-belvedere")
    )

    assert len(response.results) == 1
    assert response.results[0].title == "Belvedere City Council"
    assert response.results[0].ref == "meeting:city-belvedere:city-belvedere-meeting-1"
    assert response.results[0].type == "meeting"
