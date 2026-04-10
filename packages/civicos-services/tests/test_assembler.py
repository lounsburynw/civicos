"""
Tests for context/assembler.py — item loading, context item building,
section assembly, and full orchestration.

Mocks external I/O (CivicOS storage, vector backends). Tests real
assembly logic, type-specific detail construction, speaker resolution,
budget mapping, and participation derivation.

To run:
    pytest packages/civicos-services/tests/test_assembler.py -q --override-ini="addopts="
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.context.assembler import (
    ALL_SECTION_NAMES,
    PROJECT_TYPE_DEPARTMENT_MAP,
    QUESTION_TEMPLATES,
    SECTION_TIMEOUT_S,
    ItemNotFoundError,
    RelayUnavailableError,
    SectionTimeoutError,
    assemble_context,
    assemble_financial,
    assemble_history,
    assemble_participation,
    assemble_regulatory,
    assemble_testimony,
    build_context_item,
    generate_suggested_questions,
    load_item,
)
from civicos_services.context.models import (
    AgendaItemDetails,
    ContextDepth,
    ContextItem,
    DecisionDetails,
    IssueDetails,
    ItemType,
    LegislationDetails,
    MeetingDetails,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_civic(jurisdiction="city-san-rafael"):
    """Return a mock CivicOS instance with storage backend."""
    civic = MagicMock()
    civic.jurisdiction = jurisdiction
    civic.storage = MagicMock()
    civic.vectors = MagicMock()
    return civic


def _make_context_item(
    item_type=ItemType.agenda_item,
    title="Test Item",
    details=None,
    jurisdiction="city-san-rafael",
):
    """Build a ContextItem for section assembly tests."""
    if details is None:
        details = AgendaItemDetails(meeting_id="m1", meeting_title="Council Meeting")
    return ContextItem(
        type=item_type,
        id="item-1",
        title=title,
        jurisdiction=jurisdiction,
        item_details=details,
    )


def _make_decision_ns(id="d1", title="Decision 1", outcome="approved", date=None):
    """Return a namespace that mimics what civic.what_happened() returns."""
    return SimpleNamespace(
        id=id, title=title, outcome=outcome,
        date=date or datetime(2026, 1, 15, tzinfo=timezone.utc),
    )


def _make_budget_ns(department="Public Works", line_item="Road Repair",
                    budgeted_dollars=50000.0, fiscal_year="FY25-26"):
    return SimpleNamespace(
        department=department, line_item=line_item,
        budgeted_dollars=budgeted_dollars, fiscal_year=fiscal_year,
    )


def _make_excerpt_ns(
    text="This is testimony",
    speaker="Jane Doe",
    speaker_name="Jane Doe",
    speaker_role="public",
    video_url=None,
    start_timestamp=None,
    end_timestamp=None,
):
    return SimpleNamespace(
        text=text, speaker=speaker, speaker_name=speaker_name,
        speaker_role=speaker_role, video_url=video_url,
        start_timestamp=start_timestamp, end_timestamp=end_timestamp,
    )


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------

class TestExceptions:

    def test_item_not_found_error_message(self):
        err = ItemNotFoundError("decision", "d-99", "city-san-rafael")
        assert "decision" in str(err)
        assert "d-99" in str(err)
        assert "city-san-rafael" in str(err)
        assert err.item_type == "decision"
        assert err.item_id == "d-99"
        assert err.jurisdiction == "city-san-rafael"

    def test_section_timeout_error_message(self):
        err = SectionTimeoutError("history", 10.0)
        assert "history" in str(err)
        assert "10.0" in str(err)
        assert err.section == "history"
        assert err.timeout == 10.0

    def test_relay_unavailable_error(self):
        err = RelayUnavailableError("not implemented")
        assert "not implemented" in str(err)


# ---------------------------------------------------------------------------
# load_item Tests
# ---------------------------------------------------------------------------

class TestLoadItem:

    def test_load_decision_by_id(self):
        civic = _mock_civic()
        civic.storage.get_decisions.return_value = [
            {"id": "d-1", "title": "Housing"},
            {"id": "d-2", "title": "Parks"},
        ]
        result = load_item(civic, ItemType.decision, "d-2")
        assert result["id"] == "d-2"
        assert result["title"] == "Parks"

    def test_load_agenda_item_by_id(self):
        civic = _mock_civic()
        civic.storage.get_agenda_items.return_value = [
            {"id": "a-1", "title": "Zoning Amendment"},
        ]
        result = load_item(civic, ItemType.agenda_item, "a-1")
        assert result["title"] == "Zoning Amendment"

    def test_load_issue_by_id(self):
        civic = _mock_civic()
        civic.storage.get_issues.return_value = [
            {"id": "i-1", "status": "open", "title": "Pothole"},
        ]
        result = load_item(civic, ItemType.issue, "i-1")
        assert result["status"] == "open"

    def test_load_meeting_by_id(self):
        civic = _mock_civic()
        civic.storage.get_meetings.return_value = [
            {"id": "m-1", "title": "City Council"},
        ]
        result = load_item(civic, ItemType.meeting, "m-1")
        assert result["title"] == "City Council"

    def test_load_legislation_uses_bill_id_lookup(self):
        civic = _mock_civic()
        civic.storage.get_legislation_by_bill_id.return_value = {
            "bill_id": "ca-sb-123",
            "bill_number": "SB 123",
        }
        result = load_item(civic, ItemType.legislation, "ca-sb-123")
        assert result["bill_number"] == "SB 123"
        civic.storage.get_legislation_by_bill_id.assert_called_once_with(
            state="CA", bill_id="ca-sb-123"
        )

    def test_load_legislation_extracts_state_from_id(self):
        civic = _mock_civic()
        civic.storage.get_legislation_by_bill_id.return_value = {"bill_id": "ny-ab-42"}
        result = load_item(civic, ItemType.legislation, "ny-ab-42")
        assert result["bill_id"] == "ny-ab-42"
        civic.storage.get_legislation_by_bill_id.assert_called_once_with(
            state="NY", bill_id="ny-ab-42"
        )

    def test_load_legislation_defaults_to_ca_without_dash(self):
        civic = _mock_civic()
        civic.storage.get_legislation_by_bill_id.return_value = {"bill_id": "SB123"}
        result = load_item(civic, ItemType.legislation, "SB123")
        assert result["bill_id"] == "SB123"
        civic.storage.get_legislation_by_bill_id.assert_called_once_with(
            state="CA", bill_id="SB123"
        )

    def test_load_initiative_raises_relay_unavailable(self):
        civic = _mock_civic()
        with pytest.raises(RelayUnavailableError, match="relay integration"):
            load_item(civic, ItemType.initiative, "init-1")

    def test_load_item_not_found_raises_error(self):
        civic = _mock_civic()
        civic.storage.get_decisions.return_value = [
            {"id": "d-1", "title": "Housing"},
        ]
        with pytest.raises(ItemNotFoundError) as exc_info:
            load_item(civic, ItemType.decision, "d-nonexistent")
        assert exc_info.value.item_type == "decision"
        assert exc_info.value.item_id == "d-nonexistent"
        assert exc_info.value.jurisdiction == "city-san-rafael"

    def test_load_item_not_found_legislation_returns_none(self):
        civic = _mock_civic()
        civic.storage.get_legislation_by_bill_id.return_value = None
        with pytest.raises(ItemNotFoundError):
            load_item(civic, ItemType.legislation, "ca-fake-99")

    def test_load_empty_list_raises_not_found(self):
        civic = _mock_civic()
        civic.storage.get_issues.return_value = []
        with pytest.raises(ItemNotFoundError):
            load_item(civic, ItemType.issue, "i-1")


# ---------------------------------------------------------------------------
# build_context_item Tests
# ---------------------------------------------------------------------------

class TestBuildContextItem:

    def test_decision_details_from_raw(self):
        civic = _mock_civic()
        raw = {
            "title": "Approve Housing Plan",
            "outcome": "approved",
            "meeting_date": "2026-01-15",
            "vote_json": {"yes": 4, "no": 1},
            "body": "City Council",
            "description": "Multi-unit housing project",
        }
        item = build_context_item(ItemType.decision, "d-1", raw, "city-san-rafael", civic)
        assert item.title == "Approve Housing Plan"
        assert item.description == "Multi-unit housing project"
        assert item.type == ItemType.decision
        assert item.jurisdiction == "city-san-rafael"
        details = item.item_details
        assert details.outcome == "approved"
        assert details.decision_date == datetime(2026, 1, 15)
        assert details.votes == {"yes": 4, "no": 1}
        assert details.body == "City Council"

    def test_decision_body_falls_back_to_meeting_type(self):
        civic = _mock_civic()
        raw = {"title": "X", "meeting_type": "Planning Commission"}
        item = build_context_item(ItemType.decision, "d-1", raw, "city-san-rafael", civic)
        assert item.item_details.body == "Planning Commission"

    def test_agenda_item_with_meeting_lookup(self):
        civic = _mock_civic()
        civic.storage.get_meetings.return_value = [
            {"id": "m-1", "title": "City Council", "meeting_datetime": "2026-03-01", "location": "City Hall"},
        ]
        raw = {
            "title": "Zoning Amendment",
            "meeting_id": "m-1",
            "item_number": "5.A",
            "project_type": "zoning",
            "stance_eligible": True,
            "comment_eligible": False,
        }
        item = build_context_item(ItemType.agenda_item, "a-1", raw, "city-san-rafael", civic)
        details = item.item_details
        assert details.item_number == "5.A"
        assert details.meeting_id == "m-1"
        assert details.meeting_title == "City Council"
        assert details.meeting_date == datetime(2026, 3, 1)
        assert details.meeting_location == "City Hall"
        assert details.project_type == "zoning"
        assert details.stance_eligible is True
        assert details.comment_eligible is False

    def test_agenda_item_without_matching_meeting(self):
        civic = _mock_civic()
        civic.storage.get_meetings.return_value = []
        raw = {"title": "Orphan Item", "meeting_id": "m-gone"}
        item = build_context_item(ItemType.agenda_item, "a-2", raw, "city-san-rafael", civic)
        assert item.item_details.meeting_title == ""

    def test_issue_location_from_dict(self):
        civic = _mock_civic()
        raw = {
            "title": "Pothole",
            "issue_type": "streets",
            "status": "open",
            "location": {"address": "123 Main St", "name": "Downtown"},
            "created_at": "2026-01-01",
        }
        item = build_context_item(ItemType.issue, "i-1", raw, "city-san-rafael", civic)
        assert item.item_details.location == "123 Main St"

    def test_issue_location_from_dict_name_fallback(self):
        civic = _mock_civic()
        raw = {"title": "Pothole", "location": {"name": "Terra Linda"}}
        item = build_context_item(ItemType.issue, "i-2", raw, "city-san-rafael", civic)
        assert item.item_details.location == "Terra Linda"

    def test_issue_location_from_string(self):
        civic = _mock_civic()
        raw = {"title": "Pothole", "location": "456 Oak Ave"}
        item = build_context_item(ItemType.issue, "i-3", raw, "city-san-rafael", civic)
        assert item.item_details.location == "456 Oak Ave"

    def test_issue_location_none_when_missing(self):
        civic = _mock_civic()
        raw = {"title": "Pothole"}
        item = build_context_item(ItemType.issue, "i-4", raw, "city-san-rafael", civic)
        assert item.item_details.location is None

    def test_legislation_keywords_from_json_string(self):
        civic = _mock_civic()
        raw = {
            "bill_name": "Housing Act",
            "bill_number": "SB 123",
            "state": "CA",
            "keywords": '["housing", "zoning"]',
            "status_label": "Enrolled",
        }
        item = build_context_item(ItemType.legislation, "ca-sb-123", raw, "city-san-rafael", civic)
        assert item.title == "Housing Act"
        assert item.item_details.keywords == ["housing", "zoning"]
        assert item.item_details.bill_number == "SB 123"
        assert item.item_details.state == "CA"
        assert item.item_details.status_label == "Enrolled"

    def test_legislation_keywords_from_list(self):
        civic = _mock_civic()
        raw = {"bill_name": "X", "keywords": ["transit"]}
        item = build_context_item(ItemType.legislation, "l-1", raw, "city-san-rafael", civic)
        assert item.item_details.keywords == ["transit"]

    def test_legislation_keywords_invalid_json_becomes_empty(self):
        civic = _mock_civic()
        raw = {"bill_name": "X", "keywords": "not valid json"}
        item = build_context_item(ItemType.legislation, "l-2", raw, "city-san-rafael", civic)
        assert item.item_details.keywords == []

    def test_legislation_keywords_none_becomes_empty(self):
        civic = _mock_civic()
        raw = {"bill_name": "X", "keywords": None}
        item = build_context_item(ItemType.legislation, "l-3", raw, "city-san-rafael", civic)
        assert item.item_details.keywords == []

    def test_meeting_details_with_agenda_count(self):
        civic = _mock_civic()
        civic.storage.get_agenda_items.return_value = [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]
        raw = {
            "id": "m-1",
            "title": "City Council",
            "meeting_type": "Regular",
            "meeting_datetime": "2026-03-01T18:00:00",
            "location": "City Hall",
        }
        item = build_context_item(ItemType.meeting, "m-1", raw, "city-san-rafael", civic)
        assert item.item_details.agenda_item_count == 3
        assert item.item_details.body == "Regular"
        assert item.item_details.location == "City Hall"

    def test_title_fallback_to_bill_name(self):
        civic = _mock_civic()
        raw = {"bill_name": "Housing Act", "keywords": []}
        item = build_context_item(ItemType.legislation, "l-1", raw, "city-san-rafael", civic)
        assert item.title == "Housing Act"

    def test_description_fallback_to_summary(self):
        civic = _mock_civic()
        raw = {"title": "X", "summary": "A brief summary"}
        item = build_context_item(ItemType.decision, "d-1", raw, "city-san-rafael", civic)
        assert item.description == "A brief summary"

    def test_description_fallback_to_abstract(self):
        civic = _mock_civic()
        raw = {"title": "X", "abstract": "An abstract"}
        item = build_context_item(ItemType.decision, "d-1", raw, "city-san-rafael", civic)
        assert item.description == "An abstract"

    def test_why_it_matters_included(self):
        civic = _mock_civic()
        raw = {"title": "X", "why_it_matters": "Affects housing supply"}
        item = build_context_item(ItemType.decision, "d-1", raw, "city-san-rafael", civic)
        assert item.why_it_matters == "Affects housing supply"


# ---------------------------------------------------------------------------
# assemble_participation Tests
# ---------------------------------------------------------------------------

class TestAssembleParticipation:

    def test_follow_always_available(self):
        item = _make_context_item(
            details=AgendaItemDetails(meeting_id="m1", meeting_title="Council")
        )
        result = assemble_participation(item)
        assert "follow" in result.actions_available

    def test_voice_when_stance_eligible(self):
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council", stance_eligible=True
            )
        )
        result = assemble_participation(item)
        assert "voice" in result.actions_available
        assert result.voice_enabled is True

    def test_no_voice_when_not_stance_eligible(self):
        item = _make_context_item(
            details=AgendaItemDetails(meeting_id="m1", meeting_title="Council")
        )
        result = assemble_participation(item)
        assert "voice" not in result.actions_available
        assert result.voice_enabled is False

    def test_comment_when_comment_eligible(self):
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council", comment_eligible=True
            )
        )
        result = assemble_participation(item)
        assert "comment" in result.actions_available
        assert result.comment_status.open is True
        assert result.comment_status.clerk_email == "cityclerk@cityofsanrafael.org"

    def test_no_comment_status_when_not_eligible(self):
        item = _make_context_item(
            details=AgendaItemDetails(meeting_id="m1", meeting_title="Council")
        )
        result = assemble_participation(item)
        assert "comment" not in result.actions_available
        assert result.comment_status is None

    def test_actions_order_voice_comment_follow(self):
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council",
                stance_eligible=True, comment_eligible=True,
            )
        )
        result = assemble_participation(item)
        assert result.actions_available == ["voice", "comment", "follow"]

    def test_comment_closes_at_meeting_date(self):
        meeting_dt = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council",
                comment_eligible=True, meeting_date=meeting_dt,
            )
        )
        result = assemble_participation(item)
        assert result.comment_status.closes_at == meeting_dt

    def test_meeting_logistics_from_datetime(self):
        meeting_dt = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council",
                meeting_date=meeting_dt, meeting_location="City Hall",
            )
        )
        result = assemble_participation(item)
        assert result.meeting_logistics is not None
        assert "Apr" in result.meeting_logistics.date
        assert "15" in result.meeting_logistics.date
        assert "6:30 PM" in result.meeting_logistics.time
        assert result.meeting_logistics.location == "City Hall"
        assert "Zoom" in result.meeting_logistics.how_to_attend

    def test_meeting_logistics_string_date_coerced_by_pydantic(self):
        """Pydantic coerces date strings to datetime, so formatting applies."""
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council",
                meeting_date="2026-04-15",
            )
        )
        result = assemble_participation(item)
        assert result.meeting_logistics is not None
        # Pydantic coerces "2026-04-15" to datetime(2026,4,15) so strftime runs
        assert "Apr" in result.meeting_logistics.date
        assert "15" in result.meeting_logistics.date

    def test_no_meeting_logistics_without_date(self):
        item = _make_context_item(
            details=AgendaItemDetails(meeting_id="m1", meeting_title="Council")
        )
        result = assemble_participation(item)
        assert result.meeting_logistics is None

    def test_meeting_details_uses_date_and_location(self):
        """MeetingDetails has `date` and `location` attrs used by participation."""
        meeting_dt = datetime(2026, 5, 1, 19, 0, tzinfo=timezone.utc)
        item = _make_context_item(
            item_type=ItemType.meeting,
            details=MeetingDetails(
                body="Planning Commission",
                date=meeting_dt,
                location="Council Chambers",
                agenda_item_count=5,
            ),
        )
        result = assemble_participation(item)
        assert result.meeting_logistics is not None
        assert "May" in result.meeting_logistics.date
        assert result.meeting_logistics.location == "Council Chambers"

    def test_non_agenda_item_still_gets_follow(self):
        """Issues and decisions don't have stance/comment but get follow."""
        item = _make_context_item(
            item_type=ItemType.issue,
            details=IssueDetails(status="open"),
        )
        result = assemble_participation(item)
        assert result.actions_available == ["follow"]
        assert result.voice_enabled is False
        assert result.comment_status is None


# ---------------------------------------------------------------------------
# generate_suggested_questions Tests
# ---------------------------------------------------------------------------

class TestGenerateSuggestedQuestions:

    def test_agenda_item_questions(self):
        qs = generate_suggested_questions(ItemType.agenda_item)
        assert len(qs) == 5
        assert any("laws" in q.lower() or "law" in q.lower() for q in qs)
        assert any("participate" in q.lower() for q in qs)

    def test_decision_questions(self):
        qs = generate_suggested_questions(ItemType.decision)
        assert len(qs) == 5
        assert any("voted" in q.lower() for q in qs)

    def test_issue_questions(self):
        qs = generate_suggested_questions(ItemType.issue)
        assert len(qs) == 5
        assert any("similar" in q.lower() for q in qs)

    def test_legislation_questions(self):
        qs = generate_suggested_questions(ItemType.legislation)
        assert len(qs) == 5
        assert any("city" in q.lower() for q in qs)

    def test_meeting_questions(self):
        qs = generate_suggested_questions(ItemType.meeting)
        assert len(qs) == 5
        assert any("agenda" in q.lower() for q in qs)

    def test_initiative_questions(self):
        qs = generate_suggested_questions(ItemType.initiative)
        assert len(qs) == 5
        assert any("voice" in q.lower() for q in qs)

    def test_unknown_type_returns_empty(self):
        # Pass a value that won't be in the dict
        qs = QUESTION_TEMPLATES.get("nonexistent_type", [])
        assert qs == []


# ---------------------------------------------------------------------------
# PROJECT_TYPE_DEPARTMENT_MAP Tests
# ---------------------------------------------------------------------------

class TestProjectTypeDepartmentMap:

    def test_zoning_maps_to_community_development(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP["zoning"] == "Community Development"

    def test_transportation_maps_to_public_works(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP["transportation"] == "Public Works"

    def test_parks_maps_to_community_services(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP["parks"] == "Community Services"

    def test_police_maps_to_police(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP["police"] == "Police"

    def test_fire_maps_to_fire(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP["fire"] == "Fire"

    def test_budget_maps_to_finance(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP["budget"] == "Finance"

    def test_unmapped_type_returns_none(self):
        assert PROJECT_TYPE_DEPARTMENT_MAP.get("unknown_type") is None


# ---------------------------------------------------------------------------
# Async Section Assembly Tests
# ---------------------------------------------------------------------------

class TestAssembleHistory:

    @pytest.mark.asyncio
    async def test_returns_related_decisions(self):
        civic = _mock_civic()
        civic.what_happened = MagicMock(return_value=[
            _make_decision_ns("d1", "Housing Plan", "approved",
                              datetime(2026, 1, 15, tzinfo=timezone.utc)),
            _make_decision_ns("d2", "Zoning Change", "denied",
                              datetime(2025, 11, 3, tzinfo=timezone.utc)),
        ])
        item = _make_context_item(title="Housing Policy")
        result = await assemble_history(civic, item, ContextDepth.standard)
        assert len(result.related_decisions) == 2
        assert result.related_decisions[0].id == "d1"
        assert result.related_decisions[0].title == "Housing Plan"
        assert result.related_decisions[0].outcome == "approved"
        assert result.related_decisions[0].date == "2026-01-15"
        assert result.related_decisions[1].date == "2025-11-03"

    @pytest.mark.asyncio
    async def test_minimal_depth_limits_to_3(self):
        civic = _mock_civic()
        decisions = [_make_decision_ns(f"d{i}", f"Dec {i}") for i in range(10)]
        civic.what_happened = MagicMock(return_value=decisions)
        item = _make_context_item(title="Topic")
        result = await assemble_history(civic, item, ContextDepth.minimal)
        assert len(result.related_decisions) == 3

    @pytest.mark.asyncio
    async def test_standard_depth_limits_to_5(self):
        civic = _mock_civic()
        decisions = [_make_decision_ns(f"d{i}", f"Dec {i}") for i in range(10)]
        civic.what_happened = MagicMock(return_value=decisions)
        item = _make_context_item(title="Topic")
        result = await assemble_history(civic, item, ContextDepth.standard)
        assert len(result.related_decisions) == 5

    @pytest.mark.asyncio
    async def test_empty_decisions_returns_empty_section(self):
        civic = _mock_civic()
        civic.what_happened = MagicMock(return_value=[])
        item = _make_context_item(title="Unknown Topic")
        result = await assemble_history(civic, item, ContextDepth.standard)
        assert result.related_decisions == []

    @pytest.mark.asyncio
    async def test_date_string_handled(self):
        civic = _mock_civic()
        civic.what_happened = MagicMock(return_value=[
            _make_decision_ns("d1", "Old Decision", date="2025-06-01"),
        ])
        item = _make_context_item(title="Topic")
        result = await assemble_history(civic, item, ContextDepth.standard)
        assert result.related_decisions[0].date == "2025-06-01"

    @pytest.mark.asyncio
    async def test_none_date_handled(self):
        civic = _mock_civic()
        civic.what_happened = MagicMock(return_value=[
            SimpleNamespace(id="d1", title="No Date", outcome="tabled", date=None),
        ])
        item = _make_context_item(title="Topic")
        result = await assemble_history(civic, item, ContextDepth.standard)
        assert result.related_decisions[0].date is None


class TestAssembleRegulatory:

    @pytest.mark.asyncio
    async def test_assembles_municipal_code_refs(self):
        civic = _mock_civic()
        stack = SimpleNamespace(
            local=[{"section_number": "14.01", "section_title": "Zoning", "score": 0.85}],
            state=[], federal=[],
        )
        civic.what_applies = MagicMock(return_value=stack)
        item = _make_context_item(title="Zoning")
        result = await assemble_regulatory(civic, item, ContextDepth.standard)
        assert len(result.municipal_code) == 1
        assert result.municipal_code[0].section_number == "14.01"
        assert result.municipal_code[0].section_title == "Zoning"
        assert result.municipal_code[0].relevance_score == 0.85

    @pytest.mark.asyncio
    async def test_assembles_state_legislation(self):
        civic = _mock_civic()
        stack = SimpleNamespace(
            local=[],
            state=[{
                "bill_id": "ca-sb-9",
                "bill_number": "SB 9",
                "status_label": "Signed",
                "summary": "Duplex on single-family lots",
                "leverage_point": "implementation",
            }],
            federal=[],
        )
        civic.what_applies = MagicMock(return_value=stack)
        item = _make_context_item(title="Housing")
        result = await assemble_regulatory(civic, item, ContextDepth.standard)
        assert len(result.state_legislation) == 1
        assert result.state_legislation[0].bill_number == "SB 9"
        assert result.state_legislation[0].leverage_point == "implementation"

    @pytest.mark.asyncio
    async def test_splits_federal_bills_from_executive_orders(self):
        civic = _mock_civic()
        stack = SimpleNamespace(
            local=[], state=[],
            federal=[
                {"title": "Infrastructure Act", "summary": "Federal infra", "official_url": "http://example.com"},
                {"title": "EO on Housing", "summary": "Executive order", "eo_number": "14020"},
                {"title": "EO via doc number", "summary": "Another EO", "document_number": "2026-12345"},
            ],
        )
        civic.what_applies = MagicMock(return_value=stack)
        item = _make_context_item(title="Infrastructure")
        result = await assemble_regulatory(civic, item, ContextDepth.standard)
        assert len(result.federal) == 1
        assert result.federal[0].title == "Infrastructure Act"
        assert len(result.executive_orders) == 2
        assert result.executive_orders[0].title == "EO on Housing"
        assert result.executive_orders[1].title == "EO via doc number"

    @pytest.mark.asyncio
    async def test_empty_stack_returns_empty_sections(self):
        civic = _mock_civic()
        stack = SimpleNamespace(local=[], state=[], federal=[])
        civic.what_applies = MagicMock(return_value=stack)
        item = _make_context_item(title="Obscure Topic")
        result = await assemble_regulatory(civic, item, ContextDepth.standard)
        assert result.municipal_code == []
        assert result.state_legislation == []
        assert result.federal == []
        assert result.executive_orders == []

    @pytest.mark.asyncio
    async def test_none_local_state_federal_handled(self):
        civic = _mock_civic()
        stack = SimpleNamespace(local=None, state=None, federal=None)
        civic.what_applies = MagicMock(return_value=stack)
        item = _make_context_item(title="Topic")
        result = await assemble_regulatory(civic, item, ContextDepth.standard)
        assert result.municipal_code == []

    @pytest.mark.asyncio
    async def test_excerpt_from_full_text_truncated(self):
        civic = _mock_civic()
        long_text = "A" * 500
        stack = SimpleNamespace(
            local=[{"section_number": "1.01", "section_title": "General", "full_text": long_text}],
            state=[], federal=[],
        )
        civic.what_applies = MagicMock(return_value=stack)
        item = _make_context_item(title="Topic")
        result = await assemble_regulatory(civic, item, ContextDepth.standard)
        assert len(result.municipal_code[0].excerpt) == 300


class TestAssembleFinancial:

    @pytest.mark.asyncio
    async def test_returns_budget_items_for_mapped_type(self):
        civic = _mock_civic()
        civic.budget = MagicMock(return_value=[
            _make_budget_ns("Public Works", "Road Repair", 50000.0, "FY25-26"),
            _make_budget_ns("Public Works", "Bridge Maint", 30000.0, "FY25-26"),
        ])
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council", project_type="infrastructure"
            )
        )
        result = await assemble_financial(civic, item, ContextDepth.standard)
        assert len(result.budget_items) == 2
        assert result.budget_items[0].department == "Public Works"
        assert result.budget_items[0].line_item == "Road Repair"
        assert result.budget_items[0].budgeted_dollars == 50000.0
        assert result.total_relevant_budget == 80000.0

    @pytest.mark.asyncio
    async def test_empty_section_when_no_department_mapping(self):
        civic = _mock_civic()
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council", project_type="unknown_type"
            )
        )
        result = await assemble_financial(civic, item, ContextDepth.standard)
        assert result.budget_items == []
        assert result.total_relevant_budget == 0.0

    @pytest.mark.asyncio
    async def test_empty_section_when_no_project_type(self):
        civic = _mock_civic()
        item = _make_context_item(
            details=AgendaItemDetails(meeting_id="m1", meeting_title="Council")
        )
        result = await assemble_financial(civic, item, ContextDepth.standard)
        assert result.budget_items == []

    @pytest.mark.asyncio
    async def test_empty_section_for_non_agenda_item(self):
        """DecisionDetails has no project_type attr."""
        civic = _mock_civic()
        item = _make_context_item(
            item_type=ItemType.decision,
            details=DecisionDetails(outcome="approved"),
        )
        result = await assemble_financial(civic, item, ContextDepth.standard)
        assert result.budget_items == []

    @pytest.mark.asyncio
    async def test_passes_department_to_budget_call(self):
        civic = _mock_civic()
        civic.budget = MagicMock(return_value=[])
        item = _make_context_item(
            details=AgendaItemDetails(
                meeting_id="m1", meeting_title="Council", project_type="zoning"
            )
        )
        result = await assemble_financial(civic, item, ContextDepth.standard)
        civic.budget.assert_called_once_with(department="Community Development")
        assert result.budget_items == []
        assert result.total_relevant_budget == 0.0


class TestAssembleTestimony:

    @pytest.mark.asyncio
    async def test_categorizes_excerpts_by_role(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[
            _make_excerpt_ns("Staff report", "Staff Person", "Staff Person", "staff"),
            _make_excerpt_ns("Council question", "Council Member", "Council Member", "council"),
        ])
        civic.get_public_testimony = MagicMock(return_value=[
            _make_excerpt_ns("I support this", "Jane Doe", "Jane Doe", "public"),
        ])
        item = _make_context_item(title="Housing")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        assert len(result.public_comments) == 1
        assert result.public_comments[0].text == "I support this"
        assert result.public_comments[0].speaker == "Jane Doe"
        assert len(result.staff_discussion) == 1
        assert result.staff_discussion[0].text == "Staff report"
        assert len(result.council_discussion) == 1
        assert result.council_discussion[0].text == "Council question"

    @pytest.mark.asyncio
    async def test_speaker_resolution_fallback_to_role_council(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[
            _make_excerpt_ns("Some text", "?", None, "council"),
        ])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        assert result.council_discussion[0].speaker == "Council Member"

    @pytest.mark.asyncio
    async def test_speaker_resolution_fallback_to_role_staff(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[
            _make_excerpt_ns("Report", "A", None, "staff"),
        ])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        assert result.staff_discussion[0].speaker == "Staff"

    @pytest.mark.asyncio
    async def test_speaker_resolution_fallback_to_role_public(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[])
        civic.get_public_testimony = MagicMock(return_value=[
            _make_excerpt_ns("My concern", "?", None, "public"),
        ])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        assert result.public_comments[0].speaker == "Public Comment"

    @pytest.mark.asyncio
    async def test_speaker_resolution_skips_question_mark(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[
            SimpleNamespace(
                text="text", speaker="?", speaker_name=None, speaker_role=None,
                video_url=None, start_timestamp=None, end_timestamp=None,
            ),
        ])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        # No role and speaker is "?" — should return empty string
        # (this excerpt has speaker_role=None so it won't be in any role bucket)
        # what_was_said results are filtered by role for staff/council — "None" falls through
        assert len(result.staff_discussion) == 0
        assert len(result.council_discussion) == 0

    @pytest.mark.asyncio
    async def test_speaker_resolution_skips_single_char(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[
            _make_excerpt_ns("text", "A", None, "council"),
        ])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        # Single letter "A" with role "council" → falls back to "Council Member"
        assert result.council_discussion[0].speaker == "Council Member"

    @pytest.mark.asyncio
    async def test_speaker_resolution_uses_raw_speaker_when_long_enough(self):
        """When speaker_name is None and role isn't council/staff/public, falls back to raw speaker."""
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[])
        civic.get_public_testimony = MagicMock(return_value=[
            _make_excerpt_ns("text", "Bob Smith", None, None),
        ])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        # speaker_name=None, role=None → falls through to raw speaker "Bob Smith" (len > 1)
        assert len(result.public_comments) == 1
        assert result.public_comments[0].speaker == "Bob Smith"
        assert result.public_comments[0].text == "text"

    @pytest.mark.asyncio
    async def test_empty_testimony_returns_empty_sections(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Obscure")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        assert result.public_comments == []
        assert result.staff_discussion == []
        assert result.council_discussion == []

    @pytest.mark.asyncio
    async def test_video_url_and_timestamps_preserved(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[])
        civic.get_public_testimony = MagicMock(return_value=[
            _make_excerpt_ns(
                "Important point", "Speaker", "Speaker", "public",
                video_url="https://youtube.com/watch?v=abc",
                start_timestamp="00:15:30",
                end_timestamp="00:16:45",
            ),
        ])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        excerpt = result.public_comments[0]
        assert excerpt.video_url == "https://youtube.com/watch?v=abc"
        assert excerpt.start_timestamp == "00:15:30"
        assert excerpt.end_timestamp == "00:16:45"

    @pytest.mark.asyncio
    async def test_minimal_depth_uses_top_k_3(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.minimal)
        civic.what_was_said.assert_called_once_with("Topic", 3)
        civic.get_public_testimony.assert_called_once_with("Topic", 3)
        assert result.public_comments == []
        assert result.staff_discussion == []
        assert result.council_discussion == []

    @pytest.mark.asyncio
    async def test_standard_depth_uses_top_k_5(self):
        civic = _mock_civic()
        civic.what_was_said = MagicMock(return_value=[])
        civic.get_public_testimony = MagicMock(return_value=[])
        item = _make_context_item(title="Topic")
        result = await assemble_testimony(civic, item, ContextDepth.standard)
        civic.what_was_said.assert_called_once_with("Topic", 5)
        civic.get_public_testimony.assert_called_once_with("Topic", 5)
        assert result.public_comments == []
        assert result.staff_discussion == []
        assert result.council_discussion == []


# ---------------------------------------------------------------------------
# assemble_context (Orchestrator) Tests
# ---------------------------------------------------------------------------

class TestAssembleContext:

    @pytest.mark.asyncio
    async def test_full_assembly_returns_bundle_with_all_sections(self):
        mock_civic = _mock_civic()
        mock_civic.storage.get_decisions.return_value = [
            {"id": "d-1", "title": "Housing Decision", "outcome": "approved",
             "meeting_date": "2026-01-15"},
        ]

        # Mock what_happened, what_applies, budget, what_was_said, get_public_testimony
        mock_civic.what_happened = MagicMock(return_value=[])
        mock_civic.what_applies = MagicMock(
            return_value=SimpleNamespace(local=[], state=[], federal=[])
        )
        mock_civic.budget = MagicMock(return_value=[])
        mock_civic.what_was_said = MagicMock(return_value=[])
        mock_civic.get_public_testimony = MagicMock(return_value=[])

        with patch("civicos_services.context.assembler.CivicOS", return_value=mock_civic):
            bundle = await assemble_context(
                ItemType.decision, "d-1", "city-san-rafael",
                depth=ContextDepth.standard,
            )

        assert bundle.item.id == "d-1"
        assert bundle.item.title == "Housing Decision"
        assert bundle.item.type == ItemType.decision
        assert bundle.metadata.jurisdiction == "city-san-rafael"
        assert bundle.metadata.depth == "standard"
        assert bundle.metadata.assembly_time_ms >= 0
        assert len(bundle.suggested_questions) == 5

    @pytest.mark.asyncio
    async def test_minimal_depth_only_includes_participation(self):
        mock_civic = _mock_civic()
        mock_civic.storage.get_decisions.return_value = [
            {"id": "d-1", "title": "Decision"},
        ]
        mock_civic.what_happened = MagicMock(return_value=[])
        mock_civic.what_applies = MagicMock(
            return_value=SimpleNamespace(local=[], state=[], federal=[])
        )
        mock_civic.budget = MagicMock(return_value=[])
        mock_civic.what_was_said = MagicMock(return_value=[])
        mock_civic.get_public_testimony = MagicMock(return_value=[])

        with patch("civicos_services.context.assembler.CivicOS", return_value=mock_civic):
            bundle = await assemble_context(
                ItemType.decision, "d-1", "city-san-rafael",
                depth=ContextDepth.minimal,
            )

        # Only participation should be included; async sections skipped
        assert bundle.metadata.section_status.get("participation") == "ok"
        assert bundle.metadata.section_status.get("history") == "skipped"
        assert bundle.metadata.section_status.get("regulatory") == "skipped"
        assert bundle.metadata.section_status.get("testimony") == "skipped"
        assert bundle.metadata.section_status.get("financial") == "skipped"

    @pytest.mark.asyncio
    async def test_specific_sections_requested(self):
        mock_civic = _mock_civic()
        mock_civic.storage.get_decisions.return_value = [
            {"id": "d-1", "title": "Decision"},
        ]
        mock_civic.what_happened = MagicMock(return_value=[])

        with patch("civicos_services.context.assembler.CivicOS", return_value=mock_civic):
            bundle = await assemble_context(
                ItemType.decision, "d-1", "city-san-rafael",
                sections={"history"},
                depth=ContextDepth.standard,
            )

        assert "history" in bundle.metadata.sections_included
        assert bundle.metadata.section_status.get("history") in ("ok", "empty")
        # Non-requested sections should be skipped
        assert bundle.metadata.section_status.get("testimony") == "skipped"
        assert bundle.metadata.section_status.get("financial") == "skipped"

    @pytest.mark.asyncio
    async def test_section_error_produces_degraded_bundle(self):
        mock_civic = _mock_civic()
        mock_civic.storage.get_decisions.return_value = [
            {"id": "d-1", "title": "Decision"},
        ]
        mock_civic.what_happened = MagicMock(side_effect=RuntimeError("DB down"))
        mock_civic.what_applies = MagicMock(
            return_value=SimpleNamespace(local=[], state=[], federal=[])
        )
        mock_civic.budget = MagicMock(return_value=[])
        mock_civic.what_was_said = MagicMock(return_value=[])
        mock_civic.get_public_testimony = MagicMock(return_value=[])

        with patch("civicos_services.context.assembler.CivicOS", return_value=mock_civic):
            bundle = await assemble_context(
                ItemType.decision, "d-1", "city-san-rafael",
                depth=ContextDepth.standard,
            )

        assert bundle.metadata.degraded is True
        assert "history" in bundle.metadata.section_errors
        assert "DB down" in bundle.metadata.section_errors["history"]
        assert bundle.metadata.section_status["history"] == "error"

    @pytest.mark.asyncio
    async def test_item_not_found_raises(self):
        mock_civic = _mock_civic()
        mock_civic.storage.get_decisions.return_value = []

        with patch("civicos_services.context.assembler.CivicOS", return_value=mock_civic):
            with pytest.raises(ItemNotFoundError) as exc_info:
                await assemble_context(
                    ItemType.decision, "d-missing", "city-san-rafael",
                )
            assert exc_info.value.item_id == "d-missing"


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------

class TestConstants:

    def test_all_section_names(self):
        assert ALL_SECTION_NAMES == {"history", "regulatory", "financial", "testimony", "participation"}

    def test_section_timeout(self):
        assert SECTION_TIMEOUT_S == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
