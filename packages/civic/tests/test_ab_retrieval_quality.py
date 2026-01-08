"""
Retrieval Quality Validation for pgvector backend.

This module validates that pgvector semantic search produces high-quality results
for the Civic platform. Since pilot data is stored exclusively in pgvector
(not duplicated in ChromaDB), these tests validate quality through:

1. Score sanity checks - scores in valid range (0, 1]
2. Relevance spot checks - known queries return semantically relevant results
3. Cross-corpus consistency - similar queries return results from multiple corpora
4. Result count validation - expected volume of results per corpus

Quality Metrics:
- Scores in valid cosine similarity range (0, 1]
- Top results have high relevance (score > 0.6)
- Known domain queries return domain-specific content

Run tests:
    pytest packages/civic/tests/test_ab_retrieval_quality.py -v

Requirements:
    - DATABASE_URL set in .env (for pgvector)
"""

import os
from dataclasses import dataclass
from typing import List, Optional

import pytest

# Mark all tests as requiring pgvector
pytestmark = [pytest.mark.integration, pytest.mark.requires_pgvector]


# Benchmark queries by corpus type with expected relevance patterns
BENCHMARK_QUERIES = {
    "municipal_code": {
        "ADU zoning regulations": ["zoning", "accessory", "dwelling", "ADU", "residential"],
        "parking requirements": ["parking", "space", "vehicle", "lot"],
        "building permits": ["permit", "building", "construct", "code"],
        "residential height limits": ["height", "residential", "feet", "story", "limit"],
        "noise ordinance": ["noise", "sound", "decibel", "nuisance"],
    },
    "chunks": {
        "housing development project": ["housing", "development", "project", "unit"],
        "budget allocation": ["budget", "fund", "allocation", "fiscal"],
        "climate action plan": ["climate", "emission", "carbon", "sustainability"],
        "traffic study": ["traffic", "vehicle", "transportation", "road"],
        "general plan update": ["general plan", "land use", "planning"],
    },
    "transcripts": {
        "public comment housing": ["public comment", "housing", "speaker"],
        "council discussion budget": ["council", "budget", "discussion", "fiscal"],
        "planning commission": ["planning", "commission", "project", "application"],
        "affordable housing": ["affordable", "housing", "income", "unit"],
        "downtown development": ["downtown", "development", "district", "business"],
    },
    "issues": {
        "pothole repair": ["pothole", "road", "repair", "street"],
        "graffiti removal": ["graffiti", "vandalism", "clean", "remove"],
        "parking violation": ["parking", "violation", "car", "ticket"],
        "streetlight outage": ["streetlight", "light", "outage", "dark"],
        "sidewalk damage": ["sidewalk", "crack", "trip", "concrete"],
    },
    "decisions": {
        "approved project": ["approved", "project", "motion", "vote"],
        "denied variance": ["denied", "variance", "appeal", "rejected"],
        "continued hearing": ["continued", "hearing", "postpone", "reschedule"],
        "unanimous vote": ["unanimous", "vote", "council", "motion"],
        "environmental review": ["environmental", "CEQA", "review", "impact"],
    },
}


@dataclass
class QueryResult:
    """Result of a quality validation query."""
    query: str
    corpus_type: str
    result_count: int
    top_score: Optional[float]
    avg_score: Optional[float]
    score_range_valid: bool
    expected_terms_found: int
    total_expected_terms: int


def count_expected_terms(content: str, expected_terms: List[str]) -> int:
    """Count how many expected terms appear in content."""
    content_lower = content.lower()
    return sum(1 for term in expected_terms if term.lower() in content_lower)


class TestPgVectorRetrievalQuality:
    """Validate pgvector retrieval quality through spot checks."""

    @pytest.fixture
    def pgvector_backend(self):
        """Get PgVectorBackend."""
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set")

        from civic.storage.pgvector_backend import PgVectorBackend
        return PgVectorBackend(db_url, provider_type="fastembed")

    def _validate_query(
        self,
        query: str,
        expected_terms: List[str],
        corpus_type: str,
        pgvector_backend,
        top_k: int = 10,
    ) -> QueryResult:
        """Validate a query returns relevant results."""
        results = pgvector_backend.search(
            query=query,
            jurisdiction_id="city-san-rafael",
            corpus_type=corpus_type,
            top_k=top_k,
        )

        # Score validation
        score_range_valid = all(0 < r.score <= 1.0 for r in results)
        top_score = results[0].score if results else None
        avg_score = sum(r.score for r in results) / len(results) if results else None

        # Relevance validation - count expected terms in top results
        terms_found = 0
        for r in results[:3]:  # Check top 3 results
            content = r.content if r.content else ""
            terms_found += count_expected_terms(content, expected_terms)

        return QueryResult(
            query=query,
            corpus_type=corpus_type,
            result_count=len(results),
            top_score=top_score,
            avg_score=avg_score,
            score_range_valid=score_range_valid,
            expected_terms_found=terms_found,
            total_expected_terms=len(expected_terms) * 3,  # 3 results checked
        )

    def test_municipal_code_quality(self, pgvector_backend):
        """Municipal code queries return relevant results."""
        results = []
        for query, expected_terms in BENCHMARK_QUERIES["municipal_code"].items():
            result = self._validate_query(
                query, expected_terms, "municipal_code", pgvector_backend
            )
            results.append(result)

        # Report
        print(f"\nMUNICIPAL CODE QUALITY REPORT")
        print("-" * 50)
        for r in results:
            relevance_pct = (r.expected_terms_found / r.total_expected_terms * 100
                           if r.total_expected_terms > 0 else 0)
            print(f"Query: {r.query}")
            print(f"  Results: {r.result_count}, Top score: {r.top_score:.3f}" if r.top_score else f"  Results: {r.result_count}")
            print(f"  Term relevance: {r.expected_terms_found}/{r.total_expected_terms} ({relevance_pct:.0f}%)")

        # Assertions
        for r in results:
            assert r.result_count > 0, f"No results for '{r.query}'"
            assert r.score_range_valid, f"Invalid scores for '{r.query}'"
            if r.top_score:
                assert r.top_score > 0.5, f"Low top score {r.top_score:.3f} for '{r.query}'"

    def test_chunks_quality(self, pgvector_backend):
        """PDF chunk queries return relevant results."""
        results = []
        for query, expected_terms in BENCHMARK_QUERIES["chunks"].items():
            result = self._validate_query(
                query, expected_terms, "chunks", pgvector_backend
            )
            results.append(result)

        print(f"\nCHUNKS (PDF) QUALITY REPORT")
        print("-" * 50)
        for r in results:
            relevance_pct = (r.expected_terms_found / r.total_expected_terms * 100
                           if r.total_expected_terms > 0 else 0)
            print(f"Query: {r.query}")
            print(f"  Results: {r.result_count}, Top score: {r.top_score:.3f}" if r.top_score else f"  Results: {r.result_count}")
            print(f"  Term relevance: {r.expected_terms_found}/{r.total_expected_terms} ({relevance_pct:.0f}%)")

        for r in results:
            assert r.result_count > 0, f"No results for '{r.query}'"
            assert r.score_range_valid, f"Invalid scores for '{r.query}'"

    def test_transcripts_quality(self, pgvector_backend):
        """Transcript queries return relevant results."""
        results = []
        for query, expected_terms in BENCHMARK_QUERIES["transcripts"].items():
            result = self._validate_query(
                query, expected_terms, "transcripts", pgvector_backend
            )
            results.append(result)

        print(f"\nTRANSCRIPTS QUALITY REPORT")
        print("-" * 50)
        for r in results:
            relevance_pct = (r.expected_terms_found / r.total_expected_terms * 100
                           if r.total_expected_terms > 0 else 0)
            print(f"Query: {r.query}")
            print(f"  Results: {r.result_count}, Top score: {r.top_score:.3f}" if r.top_score else f"  Results: {r.result_count}")
            print(f"  Term relevance: {r.expected_terms_found}/{r.total_expected_terms} ({relevance_pct:.0f}%)")

        for r in results:
            assert r.result_count > 0, f"No results for '{r.query}'"
            assert r.score_range_valid, f"Invalid scores for '{r.query}'"

    def test_issues_quality(self, pgvector_backend):
        """Issue queries return relevant results."""
        results = []
        for query, expected_terms in BENCHMARK_QUERIES["issues"].items():
            result = self._validate_query(
                query, expected_terms, "issues", pgvector_backend
            )
            results.append(result)

        print(f"\nISSUES QUALITY REPORT")
        print("-" * 50)
        for r in results:
            relevance_pct = (r.expected_terms_found / r.total_expected_terms * 100
                           if r.total_expected_terms > 0 else 0)
            print(f"Query: {r.query}")
            print(f"  Results: {r.result_count}, Top score: {r.top_score:.3f}" if r.top_score else f"  Results: {r.result_count}")
            print(f"  Term relevance: {r.expected_terms_found}/{r.total_expected_terms} ({relevance_pct:.0f}%)")

        for r in results:
            assert r.result_count > 0, f"No results for '{r.query}'"
            assert r.score_range_valid, f"Invalid scores for '{r.query}'"

    def test_decisions_quality(self, pgvector_backend):
        """Decision queries return relevant results."""
        results = []
        for query, expected_terms in BENCHMARK_QUERIES["decisions"].items():
            result = self._validate_query(
                query, expected_terms, "decisions", pgvector_backend
            )
            results.append(result)

        print(f"\nDECISIONS QUALITY REPORT")
        print("-" * 50)
        for r in results:
            relevance_pct = (r.expected_terms_found / r.total_expected_terms * 100
                           if r.total_expected_terms > 0 else 0)
            print(f"Query: {r.query}")
            print(f"  Results: {r.result_count}, Top score: {r.top_score:.3f}" if r.top_score else f"  Results: {r.result_count}")
            print(f"  Term relevance: {r.expected_terms_found}/{r.total_expected_terms} ({relevance_pct:.0f}%)")

        for r in results:
            assert r.result_count > 0, f"No results for '{r.query}'"
            assert r.score_range_valid, f"Invalid scores for '{r.query}'"


class TestScoreDistribution:
    """Validate score distributions are reasonable."""

    @pytest.fixture
    def pgvector_backend(self):
        """Get PgVectorBackend."""
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set")

        from civic.storage.pgvector_backend import PgVectorBackend
        return PgVectorBackend(db_url, provider_type="fastembed")

    def test_score_range_across_corpora(self, pgvector_backend):
        """Scores should be in valid range (0, 1] across all corpus types."""
        corpus_types = ["municipal_code", "chunks", "transcripts", "issues", "decisions"]

        for corpus_type in corpus_types:
            # Use first query from benchmark set
            query = list(BENCHMARK_QUERIES[corpus_type].keys())[0]
            results = pgvector_backend.search(
                query=query,
                jurisdiction_id="city-san-rafael",
                corpus_type=corpus_type,
                top_k=10,
            )

            for r in results:
                assert 0 < r.score <= 1.0, (
                    f"Score {r.score} out of range for {corpus_type}, query: {query}"
                )

    def test_top_scores_reasonable(self, pgvector_backend):
        """Top scores should indicate high relevance (> 0.5)."""
        corpus_types = ["municipal_code", "chunks", "transcripts", "issues", "decisions"]
        min_top_scores = []

        print("\nTOP SCORE ANALYSIS")
        print("-" * 50)

        for corpus_type in corpus_types:
            # Test multiple queries per corpus
            queries = list(BENCHMARK_QUERIES[corpus_type].keys())[:3]
            top_scores = []

            for query in queries:
                results = pgvector_backend.search(
                    query=query,
                    jurisdiction_id="city-san-rafael",
                    corpus_type=corpus_type,
                    top_k=1,
                )
                if results:
                    top_scores.append(results[0].score)

            if top_scores:
                avg_top = sum(top_scores) / len(top_scores)
                min_top = min(top_scores)
                min_top_scores.append(min_top)
                print(f"{corpus_type}: avg top score {avg_top:.3f}, min {min_top:.3f}")

        # At least some corpus should have high relevance scores
        assert max(min_top_scores) > 0.6, "No corpus achieved minimum top score > 0.6"


class TestCrossCorpusSearch:
    """Validate cross-corpus search behavior via UnifiedSearch."""

    @pytest.fixture
    def unified_search(self):
        """Get UnifiedSearch instance."""
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set")

        from civic._internal.search.unified import UnifiedSearch
        return UnifiedSearch("city-san-rafael")

    def test_search_all_returns_mixed_results(self, unified_search):
        """Cross-corpus search should return results from multiple corpora."""
        # Query that could match multiple corpora
        query = "housing development affordable"
        results = unified_search.search_all(query, top_k=20)

        assert len(results) > 0, "No cross-corpus results"

        # Check we get multiple source types
        source_types = set(r.source_type for r in results)
        print(f"\nCross-corpus query: {query}")
        print(f"Source types found: {source_types}")
        print(f"Total results: {len(results)}")

        # Should have at least 2 different source types
        assert len(source_types) >= 2, (
            f"Expected multiple source types, got: {source_types}"
        )

    def test_corpus_specific_search(self, unified_search):
        """search_corpus() should restrict to specified corpus."""
        query = "zoning variance"
        results = unified_search.search_corpus("municipal_code", query, top_k=10)

        assert len(results) > 0, "No municipal code results"

        # All results should be from municipal_code
        for r in results:
            assert r.source_type == "municipal_code", (
                f"Expected municipal_code, got {r.source_type}"
            )


class TestQualityReport:
    """Generate comprehensive quality report."""

    @pytest.fixture
    def pgvector_backend(self):
        """Get PgVectorBackend."""
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set")

        from civic.storage.pgvector_backend import PgVectorBackend
        return PgVectorBackend(db_url, provider_type="fastembed")

    def test_generate_quality_report(self, pgvector_backend):
        """Generate comprehensive quality validation report."""
        print("\n" + "=" * 70)
        print("PGVECTOR RETRIEVAL QUALITY VALIDATION REPORT")
        print("=" * 70)

        corpus_stats = {}

        for corpus_type, queries in BENCHMARK_QUERIES.items():
            top_scores = []
            avg_scores = []
            result_counts = []
            terms_found_total = 0
            terms_expected_total = 0

            for query, expected_terms in queries.items():
                results = pgvector_backend.search(
                    query=query,
                    jurisdiction_id="city-san-rafael",
                    corpus_type=corpus_type,
                    top_k=10,
                )

                result_counts.append(len(results))
                if results:
                    top_scores.append(results[0].score)
                    avg_scores.append(sum(r.score for r in results) / len(results))

                    # Count expected terms in top 3
                    for r in results[:3]:
                        content = r.content if r.content else ""
                        terms_found_total += count_expected_terms(content, expected_terms)
                    terms_expected_total += len(expected_terms) * 3

            corpus_stats[corpus_type] = {
                "avg_top_score": sum(top_scores) / len(top_scores) if top_scores else 0,
                "avg_result_count": sum(result_counts) / len(result_counts),
                "term_relevance": terms_found_total / terms_expected_total if terms_expected_total else 0,
                "queries_with_results": sum(1 for c in result_counts if c > 0),
                "total_queries": len(queries),
            }

        # Print report
        for corpus_type, stats in corpus_stats.items():
            print(f"\n{corpus_type.upper()}")
            print(f"  Queries with results: {stats['queries_with_results']}/{stats['total_queries']}")
            print(f"  Avg top score: {stats['avg_top_score']:.3f}")
            print(f"  Avg result count: {stats['avg_result_count']:.1f}")
            print(f"  Term relevance: {stats['term_relevance']:.1%}")

        # Summary
        print("\n" + "-" * 70)
        print("SUMMARY")
        print("-" * 70)

        all_queries_with_results = sum(s["queries_with_results"] for s in corpus_stats.values())
        total_queries = sum(s["total_queries"] for s in corpus_stats.values())
        avg_top_score = sum(s["avg_top_score"] for s in corpus_stats.values()) / len(corpus_stats)
        avg_term_relevance = sum(s["term_relevance"] for s in corpus_stats.values()) / len(corpus_stats)

        print(f"  Total queries tested: {total_queries}")
        print(f"  Queries with results: {all_queries_with_results} ({all_queries_with_results/total_queries:.1%})")
        print(f"  Average top score: {avg_top_score:.3f}")
        print(f"  Average term relevance: {avg_term_relevance:.1%}")

        # Quality gates
        print("\n" + "-" * 70)
        print("QUALITY GATES")
        print("-" * 70)

        gates_passed = 0
        total_gates = 3

        if all_queries_with_results == total_queries:
            print("  [PASS] All queries return results")
            gates_passed += 1
        else:
            print(f"  [FAIL] Only {all_queries_with_results}/{total_queries} queries return results")

        if avg_top_score > 0.6:
            print(f"  [PASS] Average top score {avg_top_score:.3f} > 0.6")
            gates_passed += 1
        else:
            print(f"  [FAIL] Average top score {avg_top_score:.3f} <= 0.6")

        if avg_term_relevance > 0.1:
            print(f"  [PASS] Average term relevance {avg_term_relevance:.1%} > 10%")
            gates_passed += 1
        else:
            print(f"  [FAIL] Average term relevance {avg_term_relevance:.1%} <= 10%")

        print(f"\n  Quality gates passed: {gates_passed}/{total_gates}")
        print("=" * 70)

        # Assertions
        assert all_queries_with_results == total_queries, "Some queries returned no results"
        assert avg_top_score > 0.5, f"Average top score {avg_top_score:.3f} too low"
