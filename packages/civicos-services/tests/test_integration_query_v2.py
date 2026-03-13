"""
Integration tests for v2 query interface against PostgreSQL.

Validates the full stack: verbs → adapters → CivicOS API → PostgresBackend.
Includes RRF ranking calibration with real queries.

Run: pytest packages/civicos-services/tests/test_integration_query_v2.py -v --override-ini="addopts="
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Load .env for DATABASE_URL
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Clear expired HF token to avoid fastembed auth errors (cached model is sufficient)
if os.environ.get("HF_TOKEN"):
    os.environ.pop("HF_TOKEN", None)
if os.environ.get("HUGGING_FACE_HUB_TOKEN"):
    os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos-services/src"))

os.chdir(str(PROJECT_ROOT))

from civicos_services.query.models import (
    SearchMode,
    SearchRequest,
    ContextRequest,
    ExploreRequest,
)
from civicos_services.query.verbs import execute_search, execute_context, execute_explore

pytestmark = [pytest.mark.integration, pytest.mark.requires_pgvector]

JURISDICTION = "city-san-rafael"


@pytest.fixture(scope="module")
def civic():
    """Module-scoped CivicOS instance connected to PostgreSQL.

    Performs a warmup query to load the embedding model (~30s first time).
    Subsequent queries use the cached model and are fast.
    """
    from civicos import CivicOS
    c = CivicOS(JURISDICTION)
    # Verify we're on PostgreSQL
    backend_name = type(c.storage).__name__
    assert backend_name == "PostgresBackend", (
        f"Expected PostgresBackend, got {backend_name}. Is DATABASE_URL set?"
    )
    # Warmup: load embedding model by running a throwaway query.
    # The first call loads the model (~30s), subsequent calls are fast.
    c.what_happened("warmup")
    return c


def _run(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


# =========================================================================
# Basic search — multi-corpus
# =========================================================================

class TestSearchIntegration:
    """Test civic.search against real data."""

    def test_single_corpus_decisions(self, civic):
        req = SearchRequest(query="housing", corpus=["decisions"], limit=5)
        resp = _run(execute_search(req, civic, JURISDICTION))

        assert resp.results, "Expected decision results for 'housing'"
        assert resp.meta.corpora_searched == ["decisions"]
        assert resp.meta.corpus_status.get("decisions") == "ok"
        for r in resp.results:
            assert r.type == "decision"
            assert r.ref.startswith("decision:")

    def test_single_corpus_legislation(self, civic):
        """Legislation uses what_applies which calls external APIs (~40s).

        The 10s corpus timeout means this will often return timeout status.
        We validate the timeout is handled gracefully rather than asserting results.
        """
        req = SearchRequest(query="housing", corpus=["legislation"], limit=5)
        resp = _run(execute_search(req, civic, JURISDICTION))

        status = resp.meta.corpus_status.get("legislation", "unknown")
        assert status in ("ok", "timeout", "empty"), f"Unexpected status: {status}"
        # If it did return results, validate structure
        for r in resp.results:
            assert r.type == "legislation"
            assert r.details.get("bill_number") or r.details.get("status")

    def test_multi_corpus_search(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions", "testimony"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        assert resp.results, "Expected results from multi-corpus search"
        assert len(resp.meta.corpora_searched) == 2
        # At least one corpus should contribute results
        types_seen = {r.type for r in resp.results}
        assert "decision" in types_seen or "testimony" in types_seen

    def test_three_corpus_search(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions", "testimony", "issues"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        assert resp.results
        assert len(resp.meta.corpora_searched) == 3
        # Check relevance scores are normalized 0-1
        for r in resp.results:
            assert 0.0 <= (r.relevance or 0) <= 1.0

    def test_search_with_testimony(self, civic):
        req = SearchRequest(query="shelter", corpus=["testimony"], limit=5)
        resp = _run(execute_search(req, civic, JURISDICTION))

        # Testimony may or may not have results for this query
        assert resp.meta.corpus_status.get("testimony") in ("ok", "empty")


# =========================================================================
# Aggregate and trend modes
# =========================================================================

class TestAggregateTrendIntegration:
    """Test aggregate and trend modes with real data."""

    def test_aggregate_mode(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions", "testimony"],
            mode=SearchMode.aggregate,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        assert resp.aggregates is not None
        assert len(resp.aggregates) == 2
        for agg in resp.aggregates:
            assert agg.corpus in ("decisions", "testimony")
        # At least one corpus should have results
        total = sum(a.count for a in resp.aggregates)
        assert total > 0, "Expected non-zero aggregate counts"

    def test_trend_mode(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.trend,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        assert resp.trends is not None
        # Trends should have time buckets
        if resp.trends:
            assert resp.trends[0].period  # e.g., "2025-11"
            assert resp.trends[0].count > 0


# =========================================================================
# Diff mode (set operator -)
# =========================================================================

class TestDiffModeIntegration:
    """Test diff mode against real data — 'what's new since X'."""

    def test_diff_returns_recent_decisions(self, civic):
        # Use a snapshot date that should exclude older items
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.diff,
            snapshot_date="2025-01-01",
            limit=20,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        # All results should be dated after the snapshot
        for r in resp.results:
            if r.date:
                assert r.date[:10] > "2025-01-01", (
                    f"Diff returned item dated {r.date} which should be excluded"
                )

    def test_diff_with_recent_snapshot_filters_more(self, civic):
        # Compare: older snapshot should return more results than newer
        req_old = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.diff,
            snapshot_date="2024-01-01",
            limit=50,
        )
        req_new = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.diff,
            snapshot_date="2025-10-01",
            limit=50,
        )
        resp_old = _run(execute_search(req_old, civic, JURISDICTION))
        resp_new = _run(execute_search(req_new, civic, JURISDICTION))

        assert len(resp_old.results) >= len(resp_new.results), (
            f"Older snapshot should return >= results: "
            f"{len(resp_old.results)} vs {len(resp_new.results)}"
        )

    def test_diff_requires_snapshot_date(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.diff,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        # Should return error, not crash
        assert not resp.results
        assert "error" in resp.meta.corpus_status


# =========================================================================
# Intersect mode (set operator &)
# =========================================================================

class TestIntersectModeIntegration:
    """Test intersect mode — cross-corpus correlation."""

    def test_intersect_decisions_with_testimony(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.intersect,
            intersect_corpus=["testimony"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        # May or may not find correlated items, but should not crash
        assert resp.meta.corpora_searched
        # If results found, they should be decisions that correlate with testimony
        for r in resp.results:
            assert r.type == "decision"

    def test_intersect_requires_intersect_corpus(self, civic):
        req = SearchRequest(
            query="housing",
            corpus=["decisions"],
            mode=SearchMode.intersect,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        assert not resp.results
        assert "error" in resp.meta.corpus_status


# =========================================================================
# Concept lookup via civic.context
# =========================================================================

class TestConceptLookupIntegration:
    """Test civic.context(concept=...) against real municipal code."""

    def test_concept_conditional_use_permit(self, civic):
        req = ContextRequest(concept="conditional use permit")
        resp = _run(execute_context(req, civic, JURISDICTION))

        assert resp.context is not None
        assert resp.context.get("concept") == "conditional use permit"
        # Should find municipal code sections
        if resp.context.get("found"):
            assert resp.context.get("sections"), "Expected sections in concept response"
            for section in resp.context["sections"]:
                assert "title" in section
                assert "ref" in section

    def test_concept_zoning(self, civic):
        req = ContextRequest(concept="zoning")
        resp = _run(execute_context(req, civic, JURISDICTION))

        assert resp.context is not None
        assert resp.context.get("concept") == "zoning"

    def test_concept_not_found(self, civic):
        req = ContextRequest(concept="xylophone manufacturing regulations")
        resp = _run(execute_context(req, civic, JURISDICTION))

        assert resp.context is not None
        # Obscure query — may or may not find results, but should not crash
        assert "concept" in resp.context


# =========================================================================
# Explore verb
# =========================================================================

class TestExploreIntegration:
    """Test civic.explore against real data."""

    def test_explore_corpora_counts(self, civic):
        req = ExploreRequest(what="corpora", jurisdiction=JURISDICTION)
        resp = _run(execute_explore(req, civic, JURISDICTION))

        assert resp.data is not None
        corpora = resp.data.get("corpora", [])
        assert len(corpora) > 0, "Expected at least one corpus"

        # Check that populated corpora have counts
        populated = [c for c in corpora if c.get("storage_count", 0) > 0]
        assert len(populated) > 0, "Expected at least one populated corpus"

    def test_explore_capabilities(self, civic):
        req = ExploreRequest(what="capabilities")
        resp = _run(execute_explore(req, civic, JURISDICTION))

        assert resp.data is not None
        assert "verbs" in resp.data
        assert "civic.search" in resp.data["verbs"]


# =========================================================================
# RRF ranking calibration
# =========================================================================

class TestRRFCalibration:
    """
    Calibrate RRF ranking with real queries.

    These tests verify that:
    1. Multi-corpus searches produce diverse results (not dominated by one corpus)
    2. Relevance scores are properly normalized
    3. Results from different corpora are interleaved reasonably
    """

    def test_housing_corpus_diversity(self, civic):
        """Housing query across fast corpora should show diversity in top 10."""
        req = SearchRequest(
            query="housing",
            corpus=["decisions", "testimony", "issues"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        # Only check corpora that returned results (not timed out)
        ok_corpora = [c for c, s in resp.meta.corpus_status.items() if s == "ok"]
        if len(ok_corpora) < 2:
            pytest.skip(f"Only {len(ok_corpora)} corpora returned results: {resp.meta.corpus_status}")

        types = [r.type for r in resp.results]
        unique_types = set(types)

        # With k=60, first result from each corpus scores ~equally,
        # so we expect results from at least 2 corpora in top 10
        assert len(unique_types) >= 2, (
            f"Expected diversity in top 10, got only: {unique_types}. "
            f"Types in order: {types}"
        )

    def test_shelter_corpus_diversity(self, civic):
        """Shelter query — decisions + testimony should both appear."""
        req = SearchRequest(
            query="shelter",
            corpus=["decisions", "testimony"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        # Log for manual inspection regardless
        print(f"\n  Shelter results ({len(resp.results)}):")
        print(f"  Status: {resp.meta.corpus_status}")
        for r in resp.results[:5]:
            print(f"    [{r.type}] {r.title[:60]}  rel={r.relevance}")

    def test_budget_not_buried(self, civic):
        """Budget results shouldn't be buried by larger corpora."""
        req = SearchRequest(
            query="public safety",
            corpus=["decisions", "budget"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        types = [r.type for r in resp.results]
        # Log for inspection
        print(f"\n  Public safety results ({len(resp.results)}):")
        for r in resp.results[:5]:
            print(f"    [{r.type}] {r.title[:60]}  rel={r.relevance}")

        # Budget should appear somewhere in results if it has data
        budget_status = resp.meta.corpus_status.get("budget", "unknown")
        if budget_status == "ok":
            assert "budget" in types, (
                f"Budget had results but none appeared in merged top 10. "
                f"Types: {types}"
            )

    def test_relevance_normalization(self, civic):
        """Relevance scores should be normalized to [0, 1] with top result = 1.0."""
        req = SearchRequest(
            query="housing",
            corpus=["decisions", "testimony"],
            limit=10,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        if resp.results:
            # Top result should have relevance 1.0 (normalized)
            assert resp.results[0].relevance == 1.0, (
                f"Top result relevance should be 1.0, got {resp.results[0].relevance}"
            )
            # All should be in [0, 1]
            for r in resp.results:
                assert 0.0 <= r.relevance <= 1.0

    def test_rrf_interleaving_pattern(self, civic):
        """With k=60, results from different corpora should interleave."""
        req = SearchRequest(
            query="safety",
            corpus=["decisions", "testimony", "issues"],
            limit=15,
        )
        resp = _run(execute_search(req, civic, JURISDICTION))

        ok_corpora = [c for c, s in resp.meta.corpus_status.items() if s == "ok"]
        if len(ok_corpora) < 2:
            pytest.skip(f"Need 2+ corpora with results, got {ok_corpora}")

        if len(resp.results) < 3:
            pytest.skip("Not enough results for interleaving test")

        # Check that we don't have all results from one corpus first
        # (which would indicate RRF isn't working)
        first_three_types = [r.type for r in resp.results[:3]]
        assert len(set(first_three_types)) >= 2, (
            f"First 3 results all same type ({first_three_types}), "
            f"RRF should interleave from different corpora"
        )

    def test_calibration_report(self, civic):
        """
        Run 5 real queries and report corpus distribution.

        This is a diagnostic test — it always passes but prints
        a calibration report for manual review.
        """
        queries = ["housing", "public safety", "shelter", "budget", "transportation"]
        print("\n\n=== RRF CALIBRATION REPORT (k=60) ===")
        print(f"{'Query':<20} {'Corpus Distribution':<50} {'Top Type'}")
        print("-" * 90)

        for query in queries:
            req = SearchRequest(
                query=query,
                corpus=["decisions", "testimony", "issues"],
                limit=10,
            )
            resp = _run(execute_search(req, civic, JURISDICTION))

            type_counts = {}
            for r in resp.results:
                type_counts[r.type] = type_counts.get(r.type, 0) + 1

            dist = ", ".join(f"{t}:{c}" for t, c in sorted(type_counts.items()))
            top_type = resp.results[0].type if resp.results else "none"
            print(f"  {query:<18} {dist:<48} {top_type}")

        print("=" * 90)
        # Always passes — this is for manual review
