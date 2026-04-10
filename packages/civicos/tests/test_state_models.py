"""
Tests for state/models.py dataclasses.

Covers: instantiation, defaults, field types, serialization.
"""

import pytest
from datetime import datetime

from civicos._internal.state.models import (
    CityState,
    Meeting,
    AgendaItem,
    Issue,
)


# ---------- CityState ----------

class TestCityState:

    def test_required_fields(self):
        state = CityState(
            jurisdiction_id="city-san-rafael",
            jurisdiction_name="City of San Rafael",
            as_of=datetime(2026, 4, 1),
        )
        assert state.jurisdiction_id == "city-san-rafael"
        assert state.jurisdiction_name == "City of San Rafael"
        assert state.as_of == datetime(2026, 4, 1)

    def test_defaults(self):
        state = CityState(
            jurisdiction_id="city-test",
            jurisdiction_name="Test",
            as_of=datetime(2026, 1, 1),
        )
        assert state.active_residents == 0
        assert state.pending_comments == 0
        assert state.coordination_threads == 0
        assert state.completeness_score == 0.0
        assert state.data_sources == []
        assert state.extraction_version is None
        assert state.created_at is None
        assert state.updated_at is None

    def test_data_sources_independent_per_instance(self):
        """Default list factory should create separate lists per instance."""
        s1 = CityState("a", "A", datetime(2026, 1, 1))
        s2 = CityState("b", "B", datetime(2026, 1, 1))
        s1.data_sources.append("legistar")
        assert s2.data_sources == []


# ---------- Meeting ----------

class TestMeeting:

    def test_required_fields(self):
        m = Meeting(
            id="mtg-1",
            jurisdiction_id="city-san-rafael",
            title="City Council Regular Meeting",
            meeting_datetime=datetime(2026, 4, 1, 18, 0),
        )
        assert m.id == "mtg-1"
        assert m.title == "City Council Regular Meeting"

    def test_defaults(self):
        m = Meeting("m1", "j1", "Test", datetime(2026, 1, 1))
        assert m.meeting_type is None
        assert m.status is None
        assert m.location is None
        assert m.virtual_url is None
        assert m.agenda_url is None
        assert m.minutes_url is None
        assert m.video_url is None
        assert m.comment_deadline is None
        assert m.source_platform == "unknown"
        assert m.source_url is None
        assert m.data_quality_score == 0.0
        assert m.full_data is None

    def test_all_optional_fields(self):
        m = Meeting(
            id="m1",
            jurisdiction_id="j1",
            title="Test",
            meeting_datetime=datetime(2026, 4, 1),
            meeting_type="city_council",
            status="completed",
            location="City Hall",
            virtual_url="https://zoom.us/123",
            agenda_url="https://example.com/agenda.pdf",
            minutes_url="https://example.com/minutes.pdf",
            video_url="https://youtube.com/watch?v=abc",
            source_platform="legistar",
            data_quality_score=0.85,
        )
        assert m.meeting_type == "city_council"
        assert m.status == "completed"
        assert m.source_platform == "legistar"
        assert m.data_quality_score == 0.85


# ---------- AgendaItem ----------

class TestAgendaItem:

    def test_required_fields(self):
        item = AgendaItem(id="ai-1", meeting_id="mtg-1", title="Zoning amendment")
        assert item.id == "ai-1"
        assert item.meeting_id == "mtg-1"
        assert item.title == "Zoning amendment"

    def test_defaults(self):
        item = AgendaItem("a1", "m1", "Test")
        assert item.item_number is None
        assert item.description is None
        assert item.project_type is None
        assert item.actionability is None
        assert item.impact_level is None
        assert item.financial_impact_cents is None
        assert item.comment_count == 0
        assert item.following_count == 0
        assert item.relevant_bills == []
        assert item.federal_programs == []
        assert item.matched_complaints == []
        assert item.video_start_ms is None
        assert item.video_end_ms is None

    def test_list_fields_independent(self):
        """Default list factories should be independent per instance."""
        a1 = AgendaItem("a1", "m1", "T1")
        a2 = AgendaItem("a2", "m1", "T2")
        a1.relevant_bills.append("AB-123")
        a1.federal_programs.append("CDBG")
        a1.matched_complaints.append("issue-1")
        assert a2.relevant_bills == []
        assert a2.federal_programs == []
        assert a2.matched_complaints == []


# ---------- Issue ----------

class TestIssue:

    def test_required_fields(self):
        issue = Issue(
            id="issue-1",
            jurisdiction_id="city-san-rafael",
            source="seeclickfix",
            title="Pothole on 4th Street",
        )
        assert issue.id == "issue-1"
        assert issue.source == "seeclickfix"

    def test_defaults(self):
        issue = Issue("i1", "j1", "native", "Test")
        assert issue.status == "open"
        assert issue.source_id is None
        assert issue.latitude is None
        assert issue.longitude is None
        assert issue.follower_count == 0
        assert issue.matched_meetings == []
        assert issue.matched_agenda_items == []
        assert issue.match_score is None

    def test_list_fields_independent(self):
        i1 = Issue("i1", "j1", "s", "T1")
        i2 = Issue("i2", "j1", "s", "T2")
        i1.matched_meetings.append("mtg-1")
        assert i2.matched_meetings == []

    def test_to_dict_basic(self):
        issue = Issue(
            id="issue-1",
            jurisdiction_id="city-san-rafael",
            source="seeclickfix",
            title="Pothole",
            status="open",
        )
        d = issue.to_dict()
        assert d["id"] == "issue-1"
        assert d["jurisdiction_id"] == "city-san-rafael"
        assert d["source"] == "seeclickfix"
        assert d["title"] == "Pothole"
        assert d["status"] == "open"
        assert d["created_at"] is None
        assert d["updated_at"] is None

    def test_to_dict_datetime_serialization(self):
        """Datetimes should be serialized to ISO format."""
        now = datetime(2026, 4, 1, 12, 0, 0)
        issue = Issue(
            id="i1",
            jurisdiction_id="j1",
            source="native",
            title="Test",
            created_at=now,
            updated_at=now,
        )
        d = issue.to_dict()
        assert d["created_at"] == "2026-04-01T12:00:00"
        assert d["updated_at"] == "2026-04-01T12:00:00"

    def test_to_dict_none_datetimes(self):
        """None datetimes should serialize as None."""
        issue = Issue("i1", "j1", "native", "Test")
        d = issue.to_dict()
        assert d["created_at"] is None
        assert d["updated_at"] is None

    def test_to_dict_includes_location(self):
        issue = Issue(
            id="i1",
            jurisdiction_id="j1",
            source="native",
            title="Test",
            address="123 Main St",
            latitude=37.97,
            longitude=-122.53,
        )
        d = issue.to_dict()
        assert d["address"] == "123 Main St"
        assert d["latitude"] == 37.97
        assert d["longitude"] == -122.53
