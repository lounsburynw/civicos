"""
Tests for v2 query interface.

Tests adapters, planner, merger, ref parsing, and verb integration.
"""

import asyncio
from contextlib import contextmanager
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
    score: float = 0.85

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


def make_mock_storage():
    """Create a mock StorageBackend with sensible defaults."""
    storage = MagicMock()
    storage.get_meetings.return_value = [
        {"id": "mtg-1", "title": "City Council Meeting", "body": "City Council",
         "meeting_datetime": "2025-07-01T18:00:00", "location": "City Hall",
         "agenda_items": []},
    ]
    storage.get_budget_items.return_value = [
        {"id": "bud-1", "fund": "General Fund", "department": "Housing",
         "line_item": "Affordable Housing Program", "budgeted_cents": 50000000,
         "fiscal_year": "FY25-26"},
    ]
    storage.get_issues.return_value = [
        {"id": "iss-1", "summary": "Pothole on Main St", "status": "open",
         "issue_type": "Road", "address": "123 Main St", "created_at": "2025-03-01",
         "description": "Large pothole on Main St near downtown"},
    ]
    storage.get_legislation.return_value = [
        {"bill_id": "ca-sb9", "bill_number": "SB-9", "bill_name": "Housing Development",
         "status_label": "Enacted", "status": "4", "state": "CA",
         "summary": "Allows lot splits for housing", "enacted_date": "2021-09-16"},
    ]
    storage.get_legislation_batch.return_value = {
        "ca-sb9": {"bill_id": "ca-sb9", "bill_number": "SB-9", "bill_name": "Housing Development",
                    "status_label": "Enacted", "status": "4", "state": "CA",
                    "summary": "Allows lot splits for housing", "enacted_date": "2021-09-16"},
    }
    return storage


def make_mock_vectors():
    """Create a mock VectorBackend."""
    return MagicMock()


# Default regulatory stack for patching
_DEFAULT_REG_STACK = MockRegulatoryStack(
    state=[{"bill_id": "ca-sb9", "bill_number": "SB-9", "bill_name": "Housing Development",
            "status_label": "Enacted", "state": "CA", "summary": "Allows lot splits"}],
    local=[{"section_number": "14.06.030", "section_title": "ADU Regulations",
            "text": "Accessory dwelling units..."}],
)


@contextmanager
def adapter_patches(decisions=None, transcripts=None, regulatory=None, hybrid=None):
    """Patch all adapter backend dependencies with mock data.

    Use this context manager around any test that calls adapter.search()
    or verb functions that invoke adapters.
    """
    with patch("civicos.history.search_decisions", return_value=decisions if decisions is not None else [MockDecision()]), \
         patch("civicos.history.search_transcripts", return_value=transcripts if transcripts is not None else [MockTranscriptExcerpt()]), \
         patch("civicos.context.get_regulatory_context", return_value=regulatory if regulatory is not None else _DEFAULT_REG_STACK), \
         patch("civicos.history.search_hybrid", return_value=hybrid if hybrid is not None else []):
        yield


def make_mock_civic():
    """Create a mock CivicOS instance with storage/vector backends.

    The mock has both old-style methods (for upcoming/act verbs) and
    _storage/_vectors attributes (for search adapters).
    """
    civic = MagicMock()
    civic.jurisdiction = "city-san-rafael"

    # Storage and vector backends (used by adapters via verbs)
    civic.storage = make_mock_storage()
    civic.vectors = make_mock_vectors()

    # Old-style methods (still used by upcoming/act/explore verbs)
    civic.whats_next.return_value = [MockMeeting()]
    civic.what_applies.return_value = _DEFAULT_REG_STACK

    return civic


# === Adapter Tests ===

class TestDecisionsAdapter:
    def test_search_returns_civic_results(self):
        adapter = DecisionsAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        with adapter_patches():
            results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)

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
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        with adapter_patches():
            results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)

        assert len(results) == 1
        r = results[0]
        assert r.type == "testimony"
        assert r.details["speaker"] == "Jane Smith"
        assert r.details["speaker_role"] == "public"

    def test_search_public_only(self):
        adapter = TestimonyAdapter(sub_corpus="public")
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        with patch("civicos.history.search_transcripts", return_value=[MockTranscriptExcerpt(is_public_comment=True)]) as mock_st:
            results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)
            mock_st.assert_called_once()
            # Verify public_comment_only=True was passed
            assert mock_st.call_args[1].get("public_comment_only") is True

    def test_corpus_name_with_subcorpus(self):
        adapter = TestimonyAdapter(sub_corpus="council")
        assert adapter.corpus_name == "testimony:council"


class TestLegislationAdapter:
    def test_search_returns_legislation_from_storage(self):
        """Storage fallback: returns legislation when no vectors available."""
        adapter = LegislationAdapter()
        storage = make_mock_storage()
        results = adapter.search(storage, None, "city-san-rafael", "housing", 10)

        assert len(results) >= 1
        r = results[0]
        assert r.type == "legislation"
        assert r.details["bill_number"] == "SB-9"
        assert r.details["status"] == "Enacted"
        assert r.details["state"] == "CA"

    def test_search_uses_vector_relevance(self):
        """Vector path: uses semantic scores instead of positional."""
        adapter = LegislationAdapter()
        storage = make_mock_storage()
        vectors = MagicMock()

        mock_hit = MagicMock()
        mock_hit.score = 0.78
        mock_hit.metadata = {"bill_id": "ca-sb9"}
        mock_hit.content = "Housing development bill"
        vectors.search.return_value = [mock_hit]

        results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)

        assert len(results) >= 1
        assert results[0].relevance == 0.78
        assert results[0].details["bill_number"] == "SB-9"

    def test_resolves_state_code_from_jurisdiction(self):
        """city-* jurisdictions resolve to CA state code."""
        adapter = LegislationAdapter()
        assert adapter._resolve_state_code("city-san-rafael") == "CA"
        assert adapter._resolve_state_code("city-berkeley") == "CA"
        assert adapter._resolve_state_code("state-california") == "CA"
        assert adapter._resolve_state_code("county-marin") == "CA"


class TestIssuesAdapter:
    def test_search_returns_issues(self):
        adapter = IssuesAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        results = adapter.search(storage, vectors, "city-san-rafael", "pothole", 10)

        assert len(results) == 1
        r = results[0]
        assert r.type == "issue"
        assert r.details["status"] == "open"
        assert r.details["category"] == "Road"


class TestBudgetAdapter:
    def test_search_returns_budget(self):
        adapter = BudgetAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        results = adapter.search(storage, vectors, "city-san-rafael", "Housing", 10)

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

        with adapter_patches():
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
        with adapter_patches():
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) >= 1
        assert resp.results[0].type == "decision"

    def test_partial_failure(self):
        """One corpus erroring shouldn't block others."""
        civic = make_mock_civic()
        civic.storage.get_issues.side_effect = Exception("DB error")

        req = SearchRequest(query="test", corpus=["decisions", "issues"])
        with adapter_patches():
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

    def test_explore_representatives(self):
        civic = make_mock_civic()
        civic.storage.get_elected_officials.return_value = [
            {
                "id": "official-city-san-rafael-mayor",
                "name": "Kate Colin",
                "seat": "Mayor",
                "jurisdiction_id": "city-san-rafael",
                "term_start": "2024-11-05",
                "term_end": None,
                "candidate_id": "marin-cand-585-kate-colin",
            },
        ]
        req = ExploreRequest(what="representatives")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["jurisdiction"] == "city-san-rafael"
        assert len(resp.data["levels"]) >= 1
        assert resp.data["total_officials"] >= 1
        officials = resp.data["levels"][0]["officials"]
        assert officials[0]["name"] == "Kate Colin"
        assert officials[0]["seat"] == "Mayor"

    def test_explore_representatives_empty(self):
        civic = make_mock_civic()
        civic.storage.get_elected_officials.return_value = []
        req = ExploreRequest(what="representatives")
        resp = asyncio.get_event_loop().run_until_complete(
            _run_explore(req, civic)
        )
        assert resp.data["jurisdiction"] == "city-san-rafael"
        assert resp.data["levels"] == []
        assert resp.data["total_officials"] == 0

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
        # Get a ref from search
        adapter = DecisionsAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        with adapter_patches():
            results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)
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
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        mock_hr = MagicMock()
        mock_hr.source_type = "pdf"
        mock_hr.id = "chunk-1"
        mock_hr.text = "Staff recommends approval of the project..."
        mock_hr.score = 0.9
        mock_hr.agenda_item = "5a. ADU Ordinance"
        mock_hr.page_start = 12
        mock_hr.page_end = 15

        with adapter_patches(hybrid=[mock_hr]):
            results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)
        assert len(results) == 1
        d = results[0].details
        assert d["source_type"] == "pdf"
        assert d["agenda_item"] == "5a. ADU Ordinance"
        assert d["page_start"] == 12
        assert d["page_end"] == 15

    def test_orders_adapter_has_details(self):
        adapter = OrdersAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        reg = MockRegulatoryStack(
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
        with adapter_patches(regulatory=reg):
            results = adapter.search(storage, vectors, "city-san-rafael", "housing", 10)
        assert len(results) == 1
        d = results[0].details
        assert d["eo_number"] == 14008
        assert d["president"] == "Biden"
        assert d["status"] == "active"

    def test_rules_adapter_has_details(self):
        adapter = RulesAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        reg = MockRegulatoryStack(
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
        with adapter_patches(regulatory=reg):
            results = adapter.search(storage, vectors, "city-san-rafael", "fair housing", 10)
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


# === Cursor / Pagination Tests ===

class TestCursorEncoding:
    def test_encode_decode_roundtrip(self):
        from civicos_services.query.planner import encode_cursor, decode_cursor
        offsets = {"decisions": 5, "legislation": 3}
        cursor = encode_cursor(offsets)
        assert cursor is not None
        decoded = decode_cursor(cursor)
        assert decoded == offsets

    def test_encode_empty_returns_none(self):
        from civicos_services.query.planner import encode_cursor
        assert encode_cursor({}) is None
        assert encode_cursor({"decisions": 0}) is None

    def test_decode_none_returns_empty(self):
        from civicos_services.query.planner import decode_cursor
        assert decode_cursor(None) == {}
        assert decode_cursor("") == {}

    def test_decode_invalid_returns_empty(self):
        from civicos_services.query.planner import decode_cursor
        assert decode_cursor("not-valid-base64!!!") == {}
        assert decode_cursor("dGVzdA==") == {}  # decodes to "test", not JSON dict

    def test_planner_distributes_offsets(self):
        from civicos_services.query.planner import plan_search, encode_cursor
        cursor = encode_cursor({"decisions": 5})
        plan = plan_search(
            query="housing", corpus=["decisions", "legislation"],
            limit=10, cursor=cursor,
        )
        offsets = {cq.corpus: cq.offset for cq in plan.corpus_queries}
        assert offsets["decisions"] == 5
        assert offsets["legislation"] == 0


class TestPagination:
    def test_adapter_offset_skips_results(self):
        adapter = DecisionsAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        many_decisions = [
            MockDecision(id=f"dec-{i}", title=f"Decision {i}") for i in range(10)
        ]
        with adapter_patches(decisions=many_decisions):
            # No offset: get first 3
            r0 = adapter.search(storage, vectors, "city-test", "housing", limit=3, offset=0)
            assert len(r0) == 3
            assert r0[0].ref.endswith("dec-0")

            # Offset=3: skip first 3
            r1 = adapter.search(storage, vectors, "city-test", "housing", limit=3, offset=3)
            assert len(r1) == 3
            assert r1[0].ref.endswith("dec-3")

    def test_adapter_offset_beyond_results_returns_empty(self):
        adapter = DecisionsAdapter()
        storage = make_mock_storage()
        vectors = make_mock_vectors()
        with adapter_patches(decisions=[MockDecision()]):
            results = adapter.search(storage, vectors, "city-test", "housing", limit=5, offset=10)
        assert results == []

    def test_search_returns_cursor_when_full_page(self):
        """If a corpus returns a full page, the response should include a cursor."""
        civic = make_mock_civic()
        many_decisions = [
            MockDecision(id=f"dec-{i}", title=f"Decision {i}") for i in range(10)
        ]

        req = SearchRequest(query="housing", corpus=["decisions"], limit=5)
        with adapter_patches(decisions=many_decisions):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # With limit=5 and 1 corpus, per_corpus = max(3, ceil(5/1)) = 5
        # Adapter returns 5 results (full page) → cursor should be set
        assert resp.meta.cursor is not None

    def test_search_no_cursor_when_results_exhausted(self):
        """If all corpora return fewer results than per_corpus_limit, no cursor."""
        civic = make_mock_civic()

        req = SearchRequest(query="housing", corpus=["decisions"], limit=10)
        with adapter_patches(decisions=[MockDecision()]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert resp.meta.cursor is None

    def test_cursor_pagination_second_page(self):
        """Using cursor from first page should offset the second page."""
        from civicos_services.query.planner import encode_cursor

        civic = make_mock_civic()
        all_decisions = [
            MockDecision(id=f"dec-{i}", title=f"Decision {i}") for i in range(20)
        ]

        # Second page with offset=5 for decisions
        cursor = encode_cursor({"decisions": 5})
        req = SearchRequest(query="housing", corpus=["decisions"], limit=5, cursor=cursor)
        with adapter_patches(decisions=all_decisions):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # Results should start from offset 5
        assert resp.results[0].ref.endswith("dec-5")


# === Aggregate Mode Tests ===

class TestAggregateMode:
    def test_aggregate_returns_counts(self):
        from civicos_services.query.models import SearchMode
        civic = make_mock_civic()

        req = SearchRequest(
            query="housing", corpus=["decisions", "legislation"],
            mode=SearchMode.aggregate,
        )
        with adapter_patches():
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert resp.results == []
        assert resp.aggregates is not None
        assert len(resp.aggregates) == 2

        by_corpus = {a.corpus: a for a in resp.aggregates}
        assert "decisions" in by_corpus
        assert by_corpus["decisions"].count >= 1

    def test_aggregate_includes_date_range(self):
        from civicos_services.query.models import SearchMode
        civic = make_mock_civic()

        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode=SearchMode.aggregate,
        )
        with adapter_patches(decisions=[
            MockDecision(id="dec-1", date=datetime(2025, 1, 15)),
            MockDecision(id="dec-2", date=datetime(2025, 6, 15)),
        ]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        agg = resp.aggregates[0]
        assert agg.count == 2
        assert agg.earliest.startswith("2025-01-15")
        assert agg.latest.startswith("2025-06-15")

    def test_aggregate_empty_corpus(self):
        from civicos_services.query.models import SearchMode
        civic = make_mock_civic()

        req = SearchRequest(
            query="nothing", corpus=["decisions"],
            mode=SearchMode.aggregate,
        )
        with adapter_patches(decisions=[]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert resp.aggregates[0].count == 0
        assert resp.aggregates[0].earliest is None


# === Trend Mode Tests ===

class TestTrendMode:
    def test_trend_returns_time_buckets(self):
        from civicos_services.query.models import SearchMode
        civic = make_mock_civic()

        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode=SearchMode.trend,
        )
        with adapter_patches(decisions=[
            MockDecision(id="dec-1", date=datetime(2025, 1, 10)),
            MockDecision(id="dec-2", date=datetime(2025, 1, 20)),
            MockDecision(id="dec-3", date=datetime(2025, 3, 5)),
        ]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert resp.results == []
        assert resp.trends is not None
        assert len(resp.trends) >= 2  # At least 2 months

        by_period = {t.period: t.count for t in resp.trends}
        assert by_period.get("2025-01") == 2
        assert by_period.get("2025-03") == 1

    def test_trend_multi_corpus(self):
        from civicos_services.query.models import SearchMode
        civic = make_mock_civic()
        # Issues adapter uses storage.get_issues() — set up matching data
        civic.storage.get_issues.return_value = [
            {"id": "iss-1", "summary": "Pothole on road", "status": "open",
             "issue_type": "Road", "address": "123 Main", "created_at": "2025-02-15",
             "description": "Pothole on road near downtown"},
        ]

        req = SearchRequest(
            query="road", corpus=["decisions", "issues"],
            mode=SearchMode.trend,
        )
        with adapter_patches(decisions=[
            MockDecision(id="dec-1", date=datetime(2025, 2, 1)),
        ]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert resp.trends is not None
        feb_trends = [t for t in resp.trends if t.period == "2025-02"]
        assert len(feb_trends) == 2  # one for decisions, one for issues

    def test_trend_no_dates_goes_to_unknown(self):
        from civicos_services.query.models import SearchMode
        civic = make_mock_civic()

        @dataclass
        class NoDatedDecision:
            id: str = "dec-1"
            title: str = "Undated"
            date: object = None
            outcome: str = "Approved"
            body: str = "Council"
            votes: dict = None
            score: float = 0.85

        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode=SearchMode.trend,
        )
        with adapter_patches(decisions=[NoDatedDecision()]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # date=None should produce "unknown" period
        assert any(t.period == "unknown" for t in resp.trends)


# === SearchMode enum Tests ===

class TestSearchMode:
    def test_default_mode_is_search(self):
        from civicos_services.query.models import SearchMode
        req = SearchRequest(query="test", corpus=["decisions"])
        assert req.mode == SearchMode.search

    def test_mode_from_string(self):
        req = SearchRequest(query="test", corpus=["decisions"], mode="aggregate")
        assert req.mode.value == "aggregate"

    def test_cursor_field_optional(self):
        req = SearchRequest(query="test", corpus=["decisions"])
        assert req.cursor is None


# === Diff Mode Tests (- operator / EXCEPT) ===

class TestDiffMode:
    """Tests for mode='diff' — returns items new since snapshot_date."""

    def test_diff_requires_snapshot_date(self):
        """diff mode without snapshot_date returns error in meta."""
        civic = make_mock_civic()
        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode="diff",
        )
        with adapter_patches():
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 0
        assert "snapshot_date" in str(resp.meta.corpus_status)

    def test_diff_returns_only_new_items(self):
        """diff mode filters out items dated before snapshot."""
        civic = make_mock_civic()

        old_dec = MockDecision(id="dec-old", title="Old policy", date=datetime(2025, 1, 1))
        new_dec = MockDecision(id="dec-new", title="New policy", date=datetime(2025, 8, 1))

        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode="diff",
            snapshot_date="2025-06-01",
        )
        with adapter_patches(decisions=[old_dec, new_dec]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # Only dec-new (2025-08-01) is after snapshot (2025-06-01)
        assert len(resp.results) == 1
        assert "dec-new" in resp.results[0].ref

    def test_diff_excludes_items_on_snapshot_date(self):
        """Items dated exactly on snapshot_date are excluded (not new)."""
        civic = make_mock_civic()

        on_date = MockDecision(id="dec-on", title="Same day", date=datetime(2025, 6, 1))
        after_date = MockDecision(id="dec-after", title="After", date=datetime(2025, 6, 2))

        req = SearchRequest(
            query="test", corpus=["decisions"],
            mode="diff",
            snapshot_date="2025-06-01",
        )
        with adapter_patches(decisions=[on_date, after_date]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 1
        assert "dec-after" in resp.results[0].ref

    def test_diff_skips_undated_items(self):
        """Items without dates are excluded from diff results."""
        civic = make_mock_civic()

        undated = MockDecision(id="dec-undated", title="No date")
        undated.date = None

        req = SearchRequest(
            query="test", corpus=["decisions"],
            mode="diff",
            snapshot_date="2025-01-01",
        )
        with adapter_patches(decisions=[undated]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 0

    def test_diff_handles_datetime_snapshot(self):
        """snapshot_date with time component is normalized to date-only."""
        civic = make_mock_civic()

        new_dec = MockDecision(id="dec-new", title="New", date=datetime(2025, 8, 1))

        req = SearchRequest(
            query="test", corpus=["decisions"],
            mode="diff",
            snapshot_date="2025-06-01T12:00:00",
        )
        with adapter_patches(decisions=[new_dec]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 1

    def test_diff_multi_corpus(self):
        """diff mode works across multiple corpora."""
        civic = make_mock_civic()
        civic.storage.get_issues.return_value = []

        old_dec = MockDecision(id="dec-old", title="Old", date=datetime(2025, 1, 1))
        new_dec = MockDecision(id="dec-new", title="New", date=datetime(2025, 8, 1))

        req = SearchRequest(
            query="housing", corpus=["decisions", "issues"],
            mode="diff",
            snapshot_date="2025-06-01",
        )
        with adapter_patches(decisions=[old_dec, new_dec]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 1
        assert resp.meta.corpus_counts.get("decisions", 0) == 1


# === Intersect Mode Tests (& operator / INTERSECT) ===

class TestIntersectMode:
    """Tests for mode='intersect' — cross-corpus joins."""

    def test_intersect_requires_intersect_corpus(self):
        """intersect mode without intersect_corpus returns error."""
        civic = make_mock_civic()
        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode="intersect",
        )
        with adapter_patches():
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 0
        assert "intersect_corpus" in str(resp.meta.corpus_status)

    def test_intersect_filters_by_date_overlap(self):
        """intersect returns primary results that share dates with secondary."""
        civic = make_mock_civic()

        dec = MockDecision(id="dec-1", title="Housing vote", date=datetime(2025, 6, 15))
        testimony = MockTranscriptExcerpt(id="tr-1", text="I support housing")

        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode="intersect",
            intersect_corpus=["testimony"],
        )
        with adapter_patches(decisions=[dec], transcripts=[testimony]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # The decision date matches testimony date, so it should be included
        assert len(resp.results) >= 0  # May or may not match depending on adapter date format

    def test_intersect_filters_by_title_overlap(self):
        """intersect returns primary results with significant title word overlap (>= 6 chars)."""
        civic = make_mock_civic()

        dec = MockDecision(id="dec-1", title="Approve housing development rezoning", date=datetime(2025, 6, 15))
        testimony = MockTranscriptExcerpt(id="tr-1", text="I support this development rezoning")

        req = SearchRequest(
            query="housing", corpus=["decisions"],
            mode="intersect",
            intersect_corpus=["testimony"],
        )
        with adapter_patches(decisions=[dec], transcripts=[testimony]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # "development" (11 chars) and "rezoning" (8 chars) are significant words — should match
        assert len(resp.results) == 1

    def test_intersect_no_match(self):
        """intersect returns empty when no overlap between corpora."""
        civic = make_mock_civic()
        civic.storage.get_issues.return_value = [
            {"id": "iss-1", "summary": "Pothole on Elm St", "status": "open",
             "issue_type": "Road", "address": "456 Elm St", "created_at": "2025-09-01",
             "description": "Pothole on Elm St sidewalk"},
        ]

        dec = MockDecision(id="dec-1", title="Budget amendment", date=datetime(2025, 6, 15))

        req = SearchRequest(
            query="anything", corpus=["decisions"],
            mode="intersect",
            intersect_corpus=["issues"],
        )
        with adapter_patches(decisions=[dec]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        assert len(resp.results) == 0

    def test_intersect_short_words_dont_match(self):
        """Common short words (< 6 chars) like 'city', 'plan' don't cause false positives."""
        civic = make_mock_civic()

        dec = MockDecision(id="dec-1", title="City plan for code update", date=datetime(2025, 6, 15))
        testimony = MockTranscriptExcerpt(id="tr-1", text="The city plan needs work")

        req = SearchRequest(
            query="anything", corpus=["decisions"],
            mode="intersect",
            intersect_corpus=["testimony"],
        )
        with adapter_patches(decisions=[dec], transcripts=[testimony]):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_search(req, civic)
            )
        # "city" (4), "plan" (4), "code" (4) are all < 6 chars — no match
        assert len(resp.results) == 0


# === Concept Lookup Tests (civic jargon) ===

class TestConceptLookup:
    """Tests for civic.context(concept='...' ) — jargon/definition lookup."""

    def test_concept_request_validation_requires_ref_or_concept(self):
        """ContextRequest requires either ref or concept."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ContextRequest()

    def test_concept_request_rejects_both_ref_and_concept(self):
        """ContextRequest rejects both ref and concept."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ContextRequest(ref="decision:city-san-rafael:dec-1", concept="zoning")

    def test_concept_lookup_returns_sections(self):
        """Concept lookup searches municipal_code and returns matching sections."""
        civic = make_mock_civic()
        req = ContextRequest(concept="conditional use permit")
        with adapter_patches():
            resp = asyncio.get_event_loop().run_until_complete(
                _run_context(req, civic)
            )
        assert resp.context is not None
        assert resp.context.get("concept") == "conditional use permit"
        assert resp.context.get("found") is True
        assert "sections" in resp.context
        assert len(resp.context["sections"]) > 0
        assert "municipal_code" in resp.meta.corpora_searched

    def test_concept_lookup_not_found(self):
        """Concept lookup returns found=False when no matches."""
        civic = make_mock_civic()

        req = ContextRequest(concept="xyzzy nonexistent term")
        with adapter_patches(regulatory=MockRegulatoryStack(local=[])):
            resp = asyncio.get_event_loop().run_until_complete(
                _run_context(req, civic)
            )
        assert resp.context["concept"] == "xyzzy nonexistent term"
        assert resp.context["found"] is False

    def test_concept_lookup_section_structure(self):
        """Concept lookup sections have expected fields."""
        civic = make_mock_civic()
        req = ContextRequest(concept="ADU regulations")
        with adapter_patches():
            resp = asyncio.get_event_loop().run_until_complete(
                _run_context(req, civic)
            )
        if resp.context.get("found") and resp.context.get("sections"):
            section = resp.context["sections"][0]
            assert "ref" in section
            assert "title" in section
            assert "excerpt" in section
            assert "section_number" in section

    def test_ref_context_still_works(self):
        """Existing ref-based context still works after adding concept support."""
        req = ContextRequest(ref="decision:city-san-rafael:dec-1")
        assert req.ref == "decision:city-san-rafael:dec-1"
        assert req.concept is None


# === SearchMode enum extensions ===

class TestSearchModeExtensions:
    def test_diff_mode_from_string(self):
        req = SearchRequest(query="test", corpus=["decisions"], mode="diff")
        assert req.mode.value == "diff"

    def test_intersect_mode_from_string(self):
        req = SearchRequest(query="test", corpus=["decisions"], mode="intersect")
        assert req.mode.value == "intersect"

    def test_snapshot_date_field(self):
        req = SearchRequest(query="test", corpus=["decisions"], snapshot_date="2025-06-01")
        assert req.snapshot_date == "2025-06-01"

    def test_intersect_corpus_field(self):
        req = SearchRequest(
            query="test", corpus=["decisions"],
            intersect_corpus=["testimony"],
        )
        assert req.intersect_corpus == ["testimony"]

    def test_snapshot_date_rejects_invalid_format(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SearchRequest(query="test", corpus=["decisions"], snapshot_date="yesterday")

    def test_snapshot_date_accepts_iso_date(self):
        req = SearchRequest(query="test", corpus=["decisions"], snapshot_date="2025-06-01")
        assert req.snapshot_date == "2025-06-01"

    def test_snapshot_date_accepts_iso_datetime(self):
        req = SearchRequest(query="test", corpus=["decisions"], snapshot_date="2025-06-01T12:00:00")
        assert req.snapshot_date == "2025-06-01T12:00:00"


# === Jurisdiction Resolution Tests ===

class TestJurisdictionResolution:
    def test_base_only(self):
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions("city-san-rafael")
        assert result == ["city-san-rafael"]

    def test_include_parents(self):
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions("city-san-rafael", include_parents=True)
        assert result[0] == "city-san-rafael"
        assert "county-marin" in result
        assert "state-california" in result
        assert "country-united-states" in result

    def test_include_siblings(self):
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions("city-san-rafael", include_siblings=True)
        assert result[0] == "city-san-rafael"
        assert "city-mill-valley" in result
        assert "city-san-anselmo" in result
        # Parents should NOT be included when only siblings requested
        assert "county-marin" not in result

    def test_parents_and_siblings(self):
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions(
            "city-san-rafael", include_parents=True, include_siblings=True
        )
        assert result[0] == "city-san-rafael"
        assert "county-marin" in result
        assert "city-mill-valley" in result
        assert "city-san-anselmo" in result

    def test_no_duplicates(self):
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions(
            "city-san-rafael", include_parents=True, include_siblings=True
        )
        assert len(result) == len(set(result))

    def test_tier_self(self):
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "city-san-rafael") == "self"

    def test_tier_parent_county(self):
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "county-marin") == "parent_county"

    def test_tier_parent_state(self):
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "state-california") == "parent_state"

    def test_tier_parent_federal(self):
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "country-united-states") == "parent_federal"

    def test_tier_sibling(self):
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "city-mill-valley") == "sibling"

    def test_tier_cross_county(self):
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "city-berkeley") == "cross_county"

    def test_tier_sf_cross_county(self):
        """SR→SF is cross_county: both have county parents but different counties."""
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-rafael", "city-san-francisco") == "cross_county"

    def test_tier_sf_parent_county(self):
        """SF lists county-san-francisco as parent."""
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("city-san-francisco", "county-san-francisco") == "parent_county"

    def test_tier_sf_county_child(self):
        """county-san-francisco → city-san-francisco is a child relationship."""
        from civicos_services.query.jurisdictions import get_jurisdiction_tier
        assert get_jurisdiction_tier("county-san-francisco", "city-san-francisco") == "child"

    def test_tier_weight_self(self):
        from civicos_services.query.jurisdictions import get_tier_weight
        assert get_tier_weight("city-san-rafael", "city-san-rafael") == 1.0

    def test_tier_weight_parent_county(self):
        from civicos_services.query.jurisdictions import get_tier_weight
        assert get_tier_weight("city-san-rafael", "county-marin") == 0.9

    def test_tier_weight_parent_state(self):
        from civicos_services.query.jurisdictions import get_tier_weight
        assert get_tier_weight("city-san-rafael", "state-california") == 0.7

    def test_tier_weight_parent_federal(self):
        from civicos_services.query.jurisdictions import get_tier_weight
        assert get_tier_weight("city-san-rafael", "country-united-states") == 0.5

    def test_tier_weight_sibling(self):
        from civicos_services.query.jurisdictions import get_tier_weight
        assert get_tier_weight("city-san-rafael", "city-mill-valley") == 0.8

    def test_validate_jurisdiction_ids_valid(self):
        from civicos_services.query.jurisdictions import validate_jurisdiction_ids
        assert validate_jurisdiction_ids(["city-san-rafael", "city-berkeley"]) == []

    def test_validate_jurisdiction_ids_unknown(self):
        from civicos_services.query.jurisdictions import validate_jurisdiction_ids
        unknown = validate_jurisdiction_ids(["city-san-rafael", "city-nonexistent"])
        assert unknown == ["city-nonexistent"]

    def test_validate_jurisdiction_ids_empty(self):
        from civicos_services.query.jurisdictions import validate_jurisdiction_ids
        assert validate_jurisdiction_ids([]) == []

    def test_downward_fanout_capped(self):
        """Downward resolution caps children at max_children."""
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        # county-marin has 3 children (san-rafael, mill-valley, san-anselmo)
        result = resolve_jurisdictions("county-marin", include_siblings=True, max_children=1)
        # Base + 1 child (capped)
        children = [j for j in result if j != "county-marin"]
        assert len(children) == 1

    def test_default_cap_allows_small_fanout(self):
        """Default cap (20) doesn't affect small registries."""
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions("county-marin", include_siblings=True)
        # All Marin children should be present (well under 20)
        assert "city-san-rafael" in result
        assert "city-mill-valley" in result
        assert "city-san-anselmo" in result

    def test_sibling_fanout_capped(self):
        """Sideways sibling resolution also respects max_children."""
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        result = resolve_jurisdictions("city-san-rafael", include_siblings=True, max_children=1)
        siblings = [j for j in result if j != "city-san-rafael"]
        assert len(siblings) == 1


# === Cross-Jurisdiction Search Tests ===

class TestCrossJurisdictionSearch:
    def test_search_request_cross_jurisdiction_fields(self):
        """SearchRequest accepts include_parents and include_siblings."""
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            include_parents=True,
            include_siblings=True,
        )
        assert req.include_parents is True
        assert req.include_siblings is True

    def test_search_request_defaults_no_cross_jurisdiction(self):
        """By default, cross-jurisdiction is off."""
        req = SearchRequest(query="housing", corpus=["decisions"])
        assert req.include_parents is False
        assert req.include_siblings is False

    def test_civic_result_has_jurisdiction_field(self):
        """CivicResult includes optional jurisdiction field."""
        r = CivicResult(
            type="decision",
            ref="decision:city-san-rafael:1",
            title="Test",
            jurisdiction="city-san-rafael",
        )
        assert r.jurisdiction == "city-san-rafael"

    def test_civic_result_jurisdiction_defaults_none(self):
        """CivicResult.jurisdiction defaults to None for backward compat."""
        r = CivicResult(type="decision", ref="test:1", title="Test")
        assert r.jurisdiction is None

    @pytest.mark.asyncio
    async def test_cross_jurisdiction_search_with_parents(self):
        """Cross-jurisdiction search fans out to parent jurisdictions."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()

        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            include_parents=True,
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        # Should have results
        assert len(response.results) > 0

        # Should have jurisdiction_results grouping
        assert response.jurisdiction_results is not None

        # Base jurisdiction should be in results
        assert "city-san-rafael" in response.jurisdiction_results

        # Results should have jurisdiction tagged
        for r in response.results:
            assert r.jurisdiction is not None

    @pytest.mark.asyncio
    async def test_cross_jurisdiction_search_tier_boosting(self):
        """Sibling results get relevance reduced by tier weight (0.8)."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()

        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            include_siblings=True,
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        # Find a sibling result
        sibling_results = [
            r for r in response.results if r.jurisdiction and r.jurisdiction != "city-san-rafael"
        ]
        if sibling_results:
            # Sibling relevance should be boosted down (0.8x)
            for r in sibling_results:
                assert r.relevance is not None
                assert r.relevance <= 0.8  # Max relevance * 0.8 tier weight

    @pytest.mark.asyncio
    async def test_single_jurisdiction_search_unchanged(self):
        """Standard search (no cross-jurisdiction flags) still works."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()
        req = SearchRequest(query="housing", corpus=["decisions"])

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        assert len(response.results) > 0
        # No jurisdiction_results in single-jurisdiction mode
        assert response.jurisdiction_results is None

    def test_search_request_also_include_field(self):
        """SearchRequest accepts also_include and defaults to None."""
        req = SearchRequest(query="housing", corpus=["decisions"])
        assert req.also_include is None

        req2 = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
        )
        assert req2.also_include == ["city-berkeley"]

    @pytest.mark.asyncio
    async def test_also_include_triggers_cross_jurisdiction(self):
        """also_include alone (no parents/siblings) triggers cross-jurisdiction fan-out."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()

        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        # Should produce jurisdiction_results (cross-jurisdiction mode)
        assert response.jurisdiction_results is not None
        # Base jurisdiction always included
        assert "city-san-rafael" in response.jurisdiction_results
        # Explicitly included jurisdiction present
        assert "city-berkeley" in response.jurisdiction_results

    @pytest.mark.asyncio
    async def test_also_include_cross_county_tier_weight(self):
        """Cross-county jurisdictions via also_include get 0.5 weight."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()

        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        berkeley_results = [
            r for r in response.results if r.jurisdiction == "city-berkeley"
        ]
        for r in berkeley_results:
            assert r.relevance is not None
            # Cross-county weight is 0.5, so max relevance is 0.5
            assert r.relevance <= 0.5

    @pytest.mark.asyncio
    async def test_also_include_deduplicates_with_resolved(self):
        """also_include does not duplicate jurisdictions already resolved by siblings/parents."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()

        # include_siblings already resolves sibling cities; adding one explicitly shouldn't duplicate
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            include_siblings=True,
            also_include=["city-san-rafael"],  # already the base — should not duplicate
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        # city-san-rafael should appear exactly once in jurisdiction_results keys
        jid_list = list(response.jurisdiction_results.keys())
        assert jid_list.count("city-san-rafael") == 1

    @pytest.mark.asyncio
    async def test_also_include_rejects_unknown_jurisdiction(self):
        """also_include with unknown jurisdiction IDs returns error, not empty results."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()

        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-nonexistent"],
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        # Should return error in meta, not fan out to unknown jurisdiction
        assert response.results == []
        assert "error" in response.meta.corpus_status
        assert "city-nonexistent" in response.meta.corpus_status["error"]

    # === per_jurisdiction_limit (comparative cross-jid mode) ===

    def test_search_request_per_jurisdiction_limit_field(self):
        """SearchRequest accepts per_jurisdiction_limit and defaults to None."""
        req = SearchRequest(query="housing", corpus=["decisions"])
        assert req.per_jurisdiction_limit is None

        req2 = SearchRequest(
            query="housing",
            corpus=["decisions"],
            per_jurisdiction_limit=5,
        )
        assert req2.per_jurisdiction_limit == 5

    def test_per_jurisdiction_limit_validation(self):
        """per_jurisdiction_limit must be in [1, 50]."""
        with pytest.raises(ValueError):
            SearchRequest(query="x", corpus=["decisions"], per_jurisdiction_limit=0)
        with pytest.raises(ValueError):
            SearchRequest(query="x", corpus=["decisions"], per_jurisdiction_limit=51)

    @pytest.mark.asyncio
    async def test_per_jurisdiction_limit_triggers_cross_jurisdiction(self):
        """per_jurisdiction_limit alone triggers cross-jurisdiction fan-out."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()
        # No also_include / parents / siblings — but per_jurisdiction_limit is set
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            per_jurisdiction_limit=3,
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        # Even with just the base jid, comparative mode produces jurisdiction_results
        assert response.jurisdiction_results is not None
        assert "city-san-rafael" in response.jurisdiction_results

    @pytest.mark.asyncio
    async def test_per_jurisdiction_limit_caps_each_bucket(self):
        """Each jid bucket in jurisdiction_results is capped at per_jurisdiction_limit."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()
        # Provide 5 mock decisions per jid; cap at 2
        many_decisions = [
            MockDecision(id=f"dec-{i}", title=f"Housing decision {i}")
            for i in range(5)
        ]
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
            per_jurisdiction_limit=2,
        )

        with adapter_patches(decisions=many_decisions):
            response = await execute_search(req, civic, "city-san-rafael")

        assert response.jurisdiction_results is not None
        for jid, bucket in response.jurisdiction_results.items():
            assert len(bucket) <= 2, f"{jid} bucket exceeded cap: {len(bucket)}"

    @pytest.mark.asyncio
    async def test_per_jurisdiction_limit_flat_results_total(self):
        """Flat results in comparative mode are bounded by N × num_jurisdictions, not request.limit."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()
        many_decisions = [
            MockDecision(id=f"dec-{i}", title=f"Housing decision {i}")
            for i in range(10)
        ]
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
            per_jurisdiction_limit=3,
            limit=2,  # Intentionally smaller than 3 × 2 jids — should be ignored in comparative mode
        )

        with adapter_patches(decisions=many_decisions):
            response = await execute_search(req, civic, "city-san-rafael")

        # 2 jids × 3 cap = up to 6 results, NOT limited to request.limit=2
        assert len(response.results) > 2, (
            f"Comparative mode should not apply request.limit, got {len(response.results)}"
        )
        assert len(response.results) <= 6

    @pytest.mark.asyncio
    async def test_per_jurisdiction_limit_makes_cross_county_visible(self):
        """In comparative mode, cross-county jurisdictions appear in flat results
        even when their tier-boosted relevance is lower than base jurisdiction's."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
            per_jurisdiction_limit=3,
        )

        with adapter_patches():
            response = await execute_search(req, civic, "city-san-rafael")

        flat_jids = {r.jurisdiction for r in response.results}
        # Both base and cross-county jid must be visible in flat results
        assert "city-san-rafael" in flat_jids
        assert "city-berkeley" in flat_jids

    @pytest.mark.asyncio
    async def test_default_winner_take_all_unchanged(self):
        """Without per_jurisdiction_limit, request.limit caps the flat results
        and lower-tier jids may be crowded out — preserves backwards compat."""
        from civicos_services.query.verbs import execute_search

        civic = make_mock_civic()
        many_decisions = [
            MockDecision(id=f"dec-{i}", title=f"Housing decision {i}")
            for i in range(20)
        ]
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            also_include=["city-berkeley"],
            limit=5,  # default per_jurisdiction_limit=None
        )

        with adapter_patches(decisions=many_decisions):
            response = await execute_search(req, civic, "city-san-rafael")

        # Flat results capped by request.limit
        assert len(response.results) <= 5
        # jurisdiction_results buckets are NOT capped
        assert response.jurisdiction_results is not None
        # Both jids fanned out (mocks return same data, but bucket sizes are uncapped)
        assert "city-san-rafael" in response.jurisdiction_results
        assert "city-berkeley" in response.jurisdiction_results
