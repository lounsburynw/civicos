"""
Tests for v2 query interface.

Tests adapters, planner, merger, ref parsing, and verb integration.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from civicos_services.query.models import (
    SCHEMA_VERSION,
    CivicResult,
    SearchRequest,
    UpcomingRequest,
    ContextRequest,
    ActRequest,
    ExploreRequest,
    CorpusQuery,
    QueryPlan,
    ResponseMeta,
)
from civicos_services.query.adapters import (
    DecisionsAdapter,
    TestimonyAdapter,
    LegislationAdapter,
    IssuesAdapter,
    MeetingsAdapter,
    BudgetAdapter,
    MunicipalCodeAdapter,
    PacketsAdapter,
    OrdersAdapter,
    RulesAdapter,
    get_adapter,
    list_corpus_names,
    ADAPTER_REGISTRY,
)
from civicos_services.query.planner import plan_search
from civicos_services.query.merger import reciprocal_rank_fusion
from civicos_services.query.verbs import parse_ref


# === Mock Data ===

@dataclass
class MockDecision:
    id: str = "dec-1"
    title: str = "Approve housing policy"
    date: datetime = None
    outcome: str = "Approved 4-1"
    body: str = "City Council"
    votes: dict = None

    def __post_init__(self):
        if self.date is None:
            self.date = datetime(2025, 6, 15)
        if self.votes is None:
            self.votes = {"yes": 4, "no": 1}


@dataclass
class MockTranscriptExcerpt:
    id: str = "tr-1"
    text: str = "I support this housing development for our neighborhood."
    speaker: str = "Jane Smith"
    speaker_role: str = "public"
    speaker_name: str = "Jane Smith"
    video_id: str = "abc123"
    start_timestamp: str = "01:23:45"
    end_timestamp: str = "01:24:30"
    start_ms: int = 5025000
    end_ms: int = 5070000
    is_public_comment: bool = True
    score: float = 0.85

    @property
    def video_url(self):
        if not self.video_id:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"


@dataclass
class MockRegulatoryStack:
    topic: str = "housing"
    jurisdiction: str = "city-san-rafael"
    federal: list = field(default_factory=list)
    state: list = field(default_factory=list)
    local: list = field(default_factory=list)


@dataclass
class MockMeeting:
    id: str = "mtg-1"
    title: str = "City Council Regular Meeting"
    date: datetime = None
    body: str = "City Council"
    agenda_items: list = field(default_factory=list)
    location: str = "City Hall"

    def __post_init__(self):
        if self.date is None:
            self.date = datetime(2025, 7, 1)


@dataclass
class MockBudgetItem:
    id: str = "bud-1"
    fund: str = "General Fund"
    department: str = "Housing"
    line_item: str = "Affordable Housing Program"
    budgeted_dollars: float = 500000.0
    fiscal_year: str = "FY25-26"


def make_mock_civic():
    """Create a mock CivicOS instance."""
    civic = MagicMock()
    civic.jurisdiction = "city-san-rafael"

    civic.what_happened.return_value = [MockDecision()]
    civic.what_was_said.return_value = [MockTranscriptExcerpt()]
    civic.get_public_testimony.return_value = [
        MockTranscriptExcerpt(is_public_comment=True),
    ]
    civic.what_applies.return_value = MockRegulatoryStack(
        state=[{"bill_id": "ca-sb9", "bill_number": "SB-9", "bill_name": "Housing Development", "status_label": "Enacted", "state": "CA", "summary": "Allows lot splits"}],
        local=[{"section_number": "14.06.030", "section_title": "ADU Regulations", "text": "Accessory dwelling units..."}],
    )
    civic.whats_next.return_value = [MockMeeting()]
    civic.budget.return_value = [MockBudgetItem()]
    civic.search_issues.return_value = [
        {"id": "iss-1", "summary": "Pothole on Main St", "status": "open", "issue_type": "Road", "address": "123 Main St", "created_at": "2025-03-01"},
    ]
    civic._storage = MagicMock()
    civic._storage.get_meetings.return_value = [
        {"id": "mtg-1", "title": "City Council Meeting", "body": "City Council", "meeting_datetime": "2025-07-01T18:00:00", "location": "City Hall"},
    ]

    return civic


# === Adapter Tests ===

class TestDecisionsAdapter:
    def test_search_returns_civic_results(self):
        adapter = DecisionsAdapter()
        civic = make_mock_civic()
        results = adapter.search(civic, "city-san-rafael", "housing", 10)

        assert len(results) == 1
        r = results[0]
        assert r.type == "decision"
        assert "dec-1" in r.ref
        assert r.title == "Approve housing policy"
        assert r.details["outcome"] == "Approved 4-1"
        assert r.details["vote_summary"] == "4-1"
        assert r.details["body"] == "City Council"

    def test_supported_filters(self):
        adapter = DecisionsAdapter()
        assert "query" in adapter.supported_filters
        assert "since" in adapter.supported_filters


class TestTestimonyAdapter:
    def test_search_all_testimony(self):
        adapter = TestimonyAdapter()
        civic = make_mock_civic()
        results = adapter.search(civic, "city-san-rafael", "housing", 10)

        assert len(results) == 1
        r = results[0]
        assert r.type == "testimony"
        assert r.details["speaker"] == "Jane Smith"
        assert r.details["speaker_role"] == "public"
        assert r.details["video_url"] is not None

    def test_search_public_only(self):
        adapter = TestimonyAdapter(sub_corpus="public")
        civic = make_mock_civic()
        results = adapter.search(civic, "city-san-rafael", "housing", 10)

        assert len(results) >= 1
        civic.get_public_testimony.assert_called_once()

    def test_corpus_name_with_subcorpus(self):
        adapter = TestimonyAdapter(sub_corpus="council")
        assert adapter.corpus_name == "testimony:council"


class TestLegislationAdapter:
    def test_search_returns_legislation(self):
        adapter = LegislationAdapter()
        civic = make_mock_civic()
        results = adapter.search(civic, "city-san-rafael", "housing", 10)

        assert len(results) >= 1
        r = results[0]
        assert r.type == "legislation"
        assert r.details["bill_number"] == "SB-9"
        assert r.details["status"] == "Enacted"
        assert r.details["state"] == "CA"


class TestIssuesAdapter:
    def test_search_returns_issues(self):
        adapter = IssuesAdapter()
        civic = make_mock_civic()
        results = adapter.search(civic, "city-san-rafael", "pothole", 10)

        assert len(results) == 1
        r = results[0]
        assert r.type == "issue"
        assert r.details["status"] == "open"
        assert r.details["category"] == "Road"


class TestBudgetAdapter:
    def test_search_returns_budget(self):
        adapter = BudgetAdapter()
        civic = make_mock_civic()
        results = adapter.search(civic, "city-san-rafael", "Housing", 10)

        assert len(results) == 1
        r = results[0]
        assert r.type == "budget"
        assert r.details["amount"] == 500000.0
        assert r.details["department"] == "Housing"


class TestAdapterRegistry:
    def test_all_corpus_names_have_adapters(self):
        names = list_corpus_names()
        assert "decisions" in names
        assert "testimony" in names
        assert "testimony:public" in names
        assert "legislation" in names
        assert "issues" in names
        assert "budget" in names
        assert "meetings" in names
        assert "municipal_code" in names
        assert "packets" in names

    def test_get_adapter(self):
        assert get_adapter("decisions") is not None
        assert get_adapter("nonexistent") is None


# === Planner Tests ===

class TestQueryPlanner:
    def test_plan_distributes_limit(self):
        plan = plan_search(
            query="housing",
            corpus=["decisions", "legislation"],
            limit=10,
        )
        assert len(plan.corpus_queries) == 2
        # Each corpus gets at least ceil(10/2) = 5
        for cq in plan.corpus_queries:
            assert cq.per_corpus_limit >= 5

    def test_plan_respects_minimum_per_corpus(self):
        plan = plan_search(
            query="test",
            corpus=["decisions", "legislation", "testimony", "issues"],
            limit=4,
        )
        for cq in plan.corpus_queries:
            assert cq.per_corpus_limit >= 3  # minimum

    def test_plan_filters_to_supported(self):
        plan = plan_search(
            query="housing",
            corpus=["decisions"],
            since="2025-01-01",
            location="downtown",  # decisions don't support location
        )
        cq = plan.corpus_queries[0]
        assert "since" in cq.params
        assert "location" not in cq.params  # filtered out

    def test_plan_skips_unknown_corpus(self):
        plan = plan_search(query="test", corpus=["nonexistent"])
        assert len(plan.corpus_queries) == 0


# === Merger Tests ===

class TestMerger:
    def test_single_corpus_passthrough(self):
        results = [
            CivicResult(type="decision", ref="ref1", title="A", relevance=0.9),
            CivicResult(type="decision", ref="ref2", title="B", relevance=0.7),
        ]
        merged = reciprocal_rank_fusion({"decisions": results}, global_limit=10)
        assert len(merged) == 2
        assert merged[0].ref == "ref1"

    def test_rrf_interleaves_corpora(self):
        decisions = [
            CivicResult(type="decision", ref="d1", title="Decision 1"),
            CivicResult(type="decision", ref="d2", title="Decision 2"),
        ]
        legislation = [
            CivicResult(type="legislation", ref="l1", title="Legislation 1"),
            CivicResult(type="legislation", ref="l2", title="Legislation 2"),
        ]
        merged = reciprocal_rank_fusion(
            {"decisions": decisions, "legislation": legislation},
            global_limit=4,
        )
        assert len(merged) == 4
        # Top-ranked from each corpus should be interleaved
        types = [r.type for r in merged]
        # Both types should appear in top results
        assert "decision" in types[:2]
        assert "legislation" in types[:2]

    def test_rrf_respects_global_limit(self):
        results = {
            "a": [CivicResult(type="a", ref=f"a{i}", title=f"A{i}") for i in range(10)],
            "b": [CivicResult(type="b", ref=f"b{i}", title=f"B{i}") for i in range(10)],
        }
        merged = reciprocal_rank_fusion(results, global_limit=5)
        assert len(merged) == 5

    def test_rrf_empty_input(self):
        assert reciprocal_rank_fusion({}) == []

    def test_rrf_partial_results(self):
        """When one corpus returns empty, others still work."""
        merged = reciprocal_rank_fusion(
            {
                "decisions": [CivicResult(type="decision", ref="d1", title="A")],
                "legislation": [],
            },
            global_limit=10,
        )
        assert len(merged) == 1


# === Ref Parsing Tests ===

class TestRefParsing:
    def test_basic_ref(self):
        parsed = parse_ref("decision:city-san-rafael:dec-123")
        assert parsed["type"] == "decision"
        assert parsed["jurisdiction"] == "city-san-rafael"
        assert parsed["item_id"] == "dec-123"

    def test_ref_with_colons_in_id(self):
        parsed = parse_ref("meeting:city-san-rafael:2025-07-01:item-3b")
        assert parsed["type"] == "meeting"
        assert parsed["jurisdiction"] == "city-san-rafael"
        assert parsed["item_id"] == "2025-07-01:item-3b"

    def test_invalid_ref(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            parse_ref("invalid")

    def test_roundtrip(self):
        """Ref from adapter can be parsed back."""
        adapter = DecisionsAdapter()
        ref = adapter._make_ref("decision", "city-san-rafael", "dec-1")
        parsed = parse_ref(ref)
        assert parsed["type"] == "decision"
        assert parsed["item_id"] == "dec-1"


# === Integration Tests ===

class TestSearchIntegration:
    def test_multi_corpus_search(self):
        civic = make_mock_civic()
        req = SearchRequest(
            query="housing",
            corpus=["decisions", "legislation"],
        )

        resp = asyncio.get_event_loop().run_until_complete(
            _run_search(req, civic)
        )

        assert len(resp.results) > 0
        assert resp.meta.schema_version == SCHEMA_VERSION
        assert "decisions" in resp.meta.corpora_searched
        assert "legislation" in resp.meta.corpora_searched
        assert resp.meta.query_time_ms >= 0

        # Check types are present
        types = {r.type for r in resp.results}
        assert "decision" in types or "legislation" in types

    def test_single_corpus_search(self):
        civic = make_mock_civic()
        req = SearchRequest(query="housing", corpus=["decisions"])
        resp = asyncio.get_event_loop().run_until_complete(
            _run_search(req, civic)
        )
        assert len(resp.results) >= 1
        assert resp.results[0].type == "decision"

    def test_partial_failure(self):
        """One corpus erroring shouldn't block others."""
        civic = make_mock_civic()
        civic.search_issues.side_effect = Exception("DB error")

        req = SearchRequest(query="test", corpus=["decisions", "issues"])
        resp = asyncio.get_event_loop().run_until_complete(
            _run_search(req, civic)
        )

        # Decisions should still return
        assert any(r.type == "decision" for r in resp.results)
        # Issues should show error status
        assert resp.meta.corpus_status.get("issues") == "error"
        assert resp.meta.corpus_status.get("decisions") == "ok"


class TestUpcomingIntegration:
    def test_upcoming_meetings(self):
        civic = make_mock_civic()
        req = UpcomingRequest(types=["meetings"], days=30)
        resp = asyncio.get_event_loop().run_until_complete(
            _run_upcoming(req, civic)
        )
        assert len(resp.results) >= 1
        assert resp.results[0].type == "meeting"
        assert resp.meta.schema_version == SCHEMA_VERSION


class TestExploreIntegration:
    def test_explore_schema_version(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="schema_version")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["schema_version"] == SCHEMA_VERSION

    def test_explore_capabilities(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="capabilities")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert "verbs" in resp.data
        assert len(resp.data["verbs"]) == 5
        assert "corpora" in resp.data
        assert "actions" in resp.data

    def test_explore_corpus_schema(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="corpus_schema:decisions")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["corpus"] == "decisions"
        assert "outcome" in resp.data["fields"]
        assert "vote_summary" in resp.data["fields"]

    def test_explore_actions(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="actions")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        action_names = [a["name"] for a in resp.data["actions"]]
        assert "prepare_comment" in action_names
        assert "subscribe" in action_names

    def test_explore_unknown(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="nonexistent")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert "error" in resp.data


# === civic.context Integration Tests ===

class TestContextIntegration:
    def test_context_with_decision_ref(self):
        civic = make_mock_civic()
        req = ContextRequest(ref="decision:city-san-rafael:dec-123")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_context(req, civic)
        )
        assert resp.meta.schema_version == SCHEMA_VERSION
        assert resp.meta.query_time_ms >= 0
        # Context may have error if assemble_context isn't fully mocked,
        # but should not raise
        assert resp.context is not None

    def test_context_with_meeting_ref(self):
        civic = make_mock_civic()
        req = ContextRequest(ref="meeting:city-san-rafael:mtg-1")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_context(req, civic)
        )
        assert resp.context is not None
        assert resp.meta.schema_version == SCHEMA_VERSION

    def test_context_with_depth_and_sections(self):
        civic = make_mock_civic()
        req = ContextRequest(
            ref="decision:city-san-rafael:dec-1",
            depth="deep",
            sections=["history", "testimony"],
        )
        resp = asyncio.get_event_loop().run_until_complete(
            _run_context(req, civic)
        )
        assert resp.context is not None

    def test_context_invalid_ref(self):
        civic = make_mock_civic()
        req = ContextRequest(ref="invalid")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_context(req, civic)
        )
        assert "error" in resp.context

    def test_context_ref_roundtrip_from_search(self):
        """Refs produced by search adapters can be consumed by context."""
        civic = make_mock_civic()
        # Get a ref from search
        adapter = DecisionsAdapter()
        results = adapter.search(civic, "city-san-rafael", "housing", 10)
        ref = results[0].ref

        # Parse it — should not raise
        parsed = parse_ref(ref)
        assert parsed["type"] == "decision"
        assert parsed["jurisdiction"] == "city-san-rafael"
        assert parsed["item_id"] == "dec-1"


# === civic.act Integration Tests ===

class TestActIntegration:
    def test_prepare_comment(self):
        mock_handler = MagicMock(return_value='{"draft": "I support this..."}')
        civic = make_mock_civic()
        req = ActRequest(
            action="prepare_comment",
            ref="decision:city-san-rafael:dec-1",
            params={"stance": "support"},
        )
        resp = asyncio.get_event_loop().run_until_complete(
            _run_act(req, civic, mock_handler)
        )
        assert resp.meta.schema_version == SCHEMA_VERSION
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args
        assert call_args[0][0] == "compose_public_comment"

    def test_comment_template(self):
        mock_handler = MagicMock(return_value='{"template": "Dear Council..."}')
        civic = make_mock_civic()
        req = ActRequest(action="comment_template", params={"topic": "housing"})
        resp = asyncio.get_event_loop().run_until_complete(
            _run_act(req, civic, mock_handler)
        )
        mock_handler.assert_called_once_with("get_comment_template", {"topic": "housing"})
        assert resp.result is not None

    def test_subscribe(self):
        mock_handler = MagicMock(return_value='{"subscribed": true}')
        civic = make_mock_civic()
        req = ActRequest(
            action="subscribe",
            ref="meeting:city-san-rafael:housing-topic",
            params={"email": "test@example.com"},
        )
        resp = asyncio.get_event_loop().run_until_complete(
            _run_act(req, civic, mock_handler)
        )
        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        assert call_args[0] == "subscribe_to_topic"
        assert "topic" in call_args[1]

    def test_unknown_action(self):
        mock_handler = MagicMock()
        civic = make_mock_civic()
        req = ActRequest(action="nonexistent_action")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_act(req, civic, mock_handler)
        )
        assert "error" in resp.result
        assert "Unknown action" in resp.result["error"]
        mock_handler.assert_not_called()

    def test_handler_error(self):
        mock_handler = MagicMock(side_effect=Exception("Handler failed"))
        civic = make_mock_civic()
        req = ActRequest(action="prepare_comment", params={"topic": "housing"})
        resp = asyncio.get_event_loop().run_until_complete(
            _run_act(req, civic, mock_handler)
        )
        assert "error" in resp.result

    def test_ref_extracts_item_title_for_comment(self):
        """prepare_comment maps ref item_id to item_title param."""
        mock_handler = MagicMock(return_value='{"draft": "..."}')
        civic = make_mock_civic()
        req = ActRequest(
            action="prepare_comment",
            ref="decision:city-san-rafael:ADU-ordinance-update",
        )
        resp = asyncio.get_event_loop().run_until_complete(
            _run_act(req, civic, mock_handler)
        )
        call_args = mock_handler.call_args[0][1]
        assert call_args["item_title"] == "ADU-ordinance-update"


# === Adapter Detail Field Tests ===

class TestAdapterDetails:
    """Verify all adapters populate essential detail fields (not empty dicts)."""

    def test_packets_adapter_has_details(self):
        adapter = PacketsAdapter()
        civic = make_mock_civic()
        # Mock what_happened_with_discussion to return HybridSearchResult-like objects
        mock_hr = MagicMock()
        mock_hr.source_type = "pdf"
        mock_hr.id = "chunk-1"
        mock_hr.text = "Staff recommends approval of the project..."
        mock_hr.score = 0.9
        mock_hr.agenda_item = "5a. ADU Ordinance"
        mock_hr.page_start = 12
        mock_hr.page_end = 15
        civic.what_happened_with_discussion.return_value = [mock_hr]

        results = adapter.search(civic, "city-san-rafael", "housing", 10)
        assert len(results) == 1
        d = results[0].details
        assert d["source_type"] == "pdf"
        assert d["agenda_item"] == "5a. ADU Ordinance"
        assert d["page_start"] == 12
        assert d["page_end"] == 15

    def test_orders_adapter_has_details(self):
        adapter = OrdersAdapter()
        civic = make_mock_civic()
        civic.what_applies.return_value = MockRegulatoryStack(
            federal=[{
                "title": "Executive Order on Housing",
                "type": "executive order",
                "id": "eo-14008",
                "eo_number": 14008,
                "president": "Biden",
                "status": "active",
                "signing_date": "2021-01-27",
                "abstract": "Addresses climate crisis...",
            }],
        )
        results = adapter.search(civic, "city-san-rafael", "housing", 10)
        assert len(results) == 1
        d = results[0].details
        assert d["eo_number"] == 14008
        assert d["president"] == "Biden"
        assert d["status"] == "active"

    def test_rules_adapter_has_details(self):
        adapter = RulesAdapter()
        civic = make_mock_civic()
        civic.what_applies.return_value = MockRegulatoryStack(
            federal=[{
                "title": "Affirmatively Furthering Fair Housing",
                "id": "rule-123",
                "agency": "HUD",
                "type": "final rule",
                "publication_date": "2025-01-15",
                "effective_date": "2025-07-01",
                "summary": "Requires jurisdictions to...",
            }],
        )
        results = adapter.search(civic, "city-san-rafael", "fair housing", 10)
        assert len(results) == 1
        d = results[0].details
        assert d["agency"] == "HUD"
        assert d["document_type"] == "final rule"
        assert d["effective_date"] == "2025-07-01"


# === Corpus Schema Tests ===

class TestCorpusSchemas:
    """Verify all adapters have corresponding corpus schemas in explore."""

    def test_all_base_corpora_have_schemas(self):
        from civicos_services.query.verbs import CORPUS_SCHEMAS
        expected = [
            "decisions", "legislation", "testimony", "meetings",
            "issues", "budget", "municipal_code", "packets", "orders", "rules",
        ]
        for corpus in expected:
            assert corpus in CORPUS_SCHEMAS, f"Missing schema for {corpus}"
            assert len(CORPUS_SCHEMAS[corpus]) > 0, f"Empty schema for {corpus}"

    def test_explore_corpus_schema_packets(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="corpus_schema:packets")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["corpus"] == "packets"
        assert "source_type" in resp.data["fields"]
        assert "agenda_item" in resp.data["fields"]

    def test_explore_corpus_schema_orders(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="corpus_schema:orders")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["corpus"] == "orders"
        assert "eo_number" in resp.data["fields"]

    def test_explore_corpus_schema_rules(self):
        civic = make_mock_civic()
        req = ExploreRequest(what="corpus_schema:rules")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["corpus"] == "rules"
        assert "agency" in resp.data["fields"]


# === Rate Limiter Tests ===

class TestRateLimiterQueryUnits:
    @pytest.fixture(autouse=True)
    def _add_mcp_path(self):
        """Add civicos-mcp to path so api_key_middleware is importable."""
        import sys
        import os
        mcp_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "apps", "civicos-mcp")
        mcp_path = os.path.abspath(mcp_path)
        if mcp_path not in sys.path:
            sys.path.insert(0, mcp_path)
        yield
        if mcp_path in sys.path:
            sys.path.remove(mcp_path)

    def test_single_unit_cost(self):
        from api_key_middleware import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(window_seconds=60)

        allowed, remaining = limiter.check("test-single", limit=10, cost=1)
        assert allowed is True
        assert remaining == 9

    def test_multi_unit_cost(self):
        from api_key_middleware import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(window_seconds=60)

        # 5-corpus search costs 5 units
        allowed, remaining = limiter.check("test-multi", limit=10, cost=5)
        assert allowed is True
        assert remaining == 5

    def test_multi_unit_exceeds_limit(self):
        from api_key_middleware import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(window_seconds=60)

        # Fill up 8 of 10
        limiter.check("test-exceed", limit=10, cost=8)
        # 5-corpus search should be denied (8 + 5 > 10)
        allowed, remaining = limiter.check("test-exceed", limit=10, cost=5)
        assert allowed is False

    def test_multi_unit_exactly_at_limit(self):
        from api_key_middleware import SlidingWindowRateLimiter
        limiter = SlidingWindowRateLimiter(window_seconds=60)

        # Cost exactly equal to limit should succeed
        allowed, remaining = limiter.check("test-exact", limit=5, cost=5)
        assert allowed is True
        assert remaining == 0

        # One more should fail
        allowed, remaining = limiter.check("test-exact", limit=5, cost=1)
        assert allowed is False

    def test_charge_query_units(self):
        """charge_query_units adds extra entries to the sliding window."""
        import importlib
        import api_key_middleware
        importlib.reload(api_key_middleware)
        from api_key_middleware import charge_query_units, _rate_limiter

        # Use a mock request with unique IP to avoid cross-test pollution
        mock_request = MagicMock()
        mock_request.state.api_key_info = None
        mock_request.client.host = "10.99.99.99"

        key = "ip:10.99.99.99"
        initial_count = len(_rate_limiter._requests.get(key, []))

        # Charge 4 extra units
        charge_query_units(mock_request, 4)

        new_count = len(_rate_limiter._requests.get(key, []))
        assert new_count == initial_count + 4


# === FastAPI Integration Tests ===

class TestV2Router:
    """Test the FastAPI router with TestClient."""

    @pytest.fixture
    def client(self):
        """Create a TestClient with v2 router mounted."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from civicos_services.query.router import create_v2_router

        app = FastAPI()
        civic = make_mock_civic()
        # Create router without auth middleware (ImportError path)
        router = create_v2_router(civic, "city-san-rafael")
        app.include_router(router)
        return TestClient(app)

    def test_search_endpoint(self, client):
        resp = client.post("/api/v2/civic/search", json={
            "query": "housing",
            "corpus": ["decisions"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "meta" in data
        assert data["meta"]["schema_version"] == SCHEMA_VERSION

    def test_search_multi_corpus(self, client):
        resp = client.post("/api/v2/civic/search", json={
            "query": "housing",
            "corpus": ["decisions", "legislation"],
            "limit": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["meta"]["corpora_searched"]) == 2

    def test_search_missing_corpus(self, client):
        """corpus is required."""
        resp = client.post("/api/v2/civic/search", json={
            "query": "housing",
        })
        assert resp.status_code == 422

    def test_search_missing_query(self, client):
        resp = client.post("/api/v2/civic/search", json={
            "corpus": ["decisions"],
        })
        assert resp.status_code == 422

    def test_upcoming_endpoint(self, client):
        resp = client.post("/api/v2/civic/upcoming", json={
            "types": ["meetings"],
            "days": 7,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["meta"]["schema_version"] == SCHEMA_VERSION

    def test_upcoming_default_params(self, client):
        resp = client.post("/api/v2/civic/upcoming", json={})
        assert resp.status_code == 200

    def test_context_endpoint(self, client):
        resp = client.post("/api/v2/civic/context", json={
            "ref": "decision:city-san-rafael:dec-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data

    def test_context_missing_ref(self, client):
        resp = client.post("/api/v2/civic/context", json={})
        assert resp.status_code == 422

    def test_act_endpoint(self, client):
        # Without registry, should get handler unavailable error in result
        resp = client.post("/api/v2/civic/act", json={
            "action": "prepare_comment",
            "params": {"topic": "housing"},
        })
        assert resp.status_code == 200
        data = resp.json()
        # Will have error since no registry, but shouldn't 500
        assert "result" in data

    def test_act_unknown_action(self, client):
        resp = client.post("/api/v2/civic/act", json={
            "action": "nonexistent",
        })
        assert resp.status_code == 200
        assert "error" in resp.json()["result"]

    def test_explore_endpoint(self, client):
        resp = client.post("/api/v2/civic/explore", json={
            "what": "schema_version",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["schema_version"] == SCHEMA_VERSION

    def test_explore_capabilities(self, client):
        resp = client.post("/api/v2/civic/explore", json={
            "what": "capabilities",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["verbs"]) == 5

    def test_explore_missing_what(self, client):
        resp = client.post("/api/v2/civic/explore", json={})
        assert resp.status_code == 422

    def test_v1_endpoints_unaffected(self):
        """v2 router doesn't interfere with v1 paths."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from civicos_services.query.router import create_v2_router

        app = FastAPI()
        civic = make_mock_civic()

        # Mount a fake v1 endpoint
        @app.get("/api/tools/health")
        def v1_health():
            return {"status": "ok"}

        router = create_v2_router(civic, "city-san-rafael")
        app.include_router(router)
        client = TestClient(app)

        # v1 still works
        assert client.get("/api/tools/health").status_code == 200
        # v2 also works
        assert client.post("/api/v2/civic/explore", json={"what": "schema_version"}).status_code == 200


# === Helpers ===

async def _run_search(req, civic):
    from civicos_services.query.verbs import execute_search
    return await execute_search(req, civic, "city-san-rafael")

async def _run_upcoming(req, civic):
    from civicos_services.query.verbs import execute_upcoming
    return await execute_upcoming(req, civic, "city-san-rafael")

async def _run_context(req, civic):
    from civicos_services.query.verbs import execute_context
    return await execute_context(req, civic, "city-san-rafael")

async def _run_act(req, civic, call_handler):
    from civicos_services.query.verbs import execute_act
    return await execute_act(req, civic, "city-san-rafael", call_handler)

async def _run_explore(req, civic):
    from civicos_services.query.verbs import execute_explore
    return await execute_explore(req, civic, "city-san-rafael")
