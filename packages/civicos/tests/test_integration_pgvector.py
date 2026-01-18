"""
Integration tests for pgvector search functionality.

These tests validate that the Civic API correctly uses pgvector for semantic
search across various corpus types (municipal code, transcripts, decisions, etc.).

Tests are marked with @pytest.mark.requires_pgvector and automatically skip
when DATABASE_URL is not set. In CI, these run with GitHub Actions secrets.

Run locally (with DATABASE_URL in .env):
    pytest packages/civic/tests/test_integration_pgvector.py -v

Run in CI:
    Automatically runs as part of full test suite when DATABASE_URL secret is set.
"""

import os

import pytest

# Mark all tests as requiring pgvector
pytestmark = [pytest.mark.integration, pytest.mark.requires_pgvector]


class TestMunicipalCodeSearch:
    """Tests for municipal code search via what_applies()."""

    @pytest.fixture
    def civic_client(self):
        """Get Civic client connected to pgvector database."""
        from dotenv import load_dotenv
        load_dotenv()

        from civicos import CivicOS
        return CivicOS("city-san-rafael")

    def test_what_applies_returns_ordinances(self, civic_client):
        """what_applies() returns municipal code ordinances from pgvector."""
        result = civic_client.what_applies("ADU zoning regulations")

        # Should have local results
        assert result.local, "Expected local results from what_applies()"

        # Should include ordinance type results
        ordinances = [r for r in result.local if r.get("type") == "ordinance"]
        assert len(ordinances) > 0, "Expected ordinance results from municipal code search"

    def test_adu_query_finds_relevant_sections(self, civic_client):
        """ADU query should find relevant zoning sections."""
        result = civic_client.what_applies("ADU zoning regulations")

        ordinances = [r for r in result.local if r.get("type") == "ordinance"]
        sections = [r.get("section_number", "") for r in ordinances]

        # Section 14.16.285 is San Rafael's ADU regulations
        # Accept either the ADU section (14.16.285) or the definitions section (14.03.030)
        # Both are relevant to ADU queries
        relevant_sections = ["14.16.285", "14.03.030", "14.02.010"]
        found_relevant = any(
            any(s.startswith(sec) for sec in relevant_sections)
            for s in sections if s
        )
        assert found_relevant, (
            f"Expected ADU-related sections (14.16.285, 14.03.030, or 14.02.010), got: {sections}"
        )

    def test_municipal_code_result_structure(self, civic_client):
        """Municipal code results have expected fields."""
        result = civic_client.what_applies("parking requirements")

        ordinances = [r for r in result.local if r.get("type") == "ordinance"]
        if ordinances:
            # Check first ordinance has expected fields
            ordinance = ordinances[0]
            assert "section_number" in ordinance
            assert "relevance_score" in ordinance
            assert ordinance["relevance_score"] > 0, "Relevance score should be positive"

    def test_municipal_code_relevance_scores(self, civic_client):
        """Municipal code results have reasonable relevance scores."""
        result = civic_client.what_applies("building permits")

        ordinances = [r for r in result.local if r.get("type") == "ordinance"]
        if ordinances:
            # Scores should be between 0 and 1 (cosine similarity normalized)
            for ordinance in ordinances:
                score = ordinance.get("relevance_score", 0)
                assert 0 < score <= 1, f"Score {score} outside expected range (0, 1]"


class TestCrossCorpusSearch:
    """Tests for cross-corpus search functionality."""

    @pytest.fixture
    def civic_client(self):
        """Get Civic client connected to pgvector database."""
        from dotenv import load_dotenv
        load_dotenv()

        from civicos import CivicOS
        return CivicOS("city-san-rafael")

    def test_what_applies_includes_state_results(self, civic_client):
        """what_applies() returns state legislation in addition to local."""
        result = civic_client.what_applies("housing development")

        # State results should exist (CA bills from codified_law or legislation)
        assert result.state is not None, "Expected state results"

    def test_what_applies_returns_regulatory_stack(self, civic_client):
        """what_applies() returns a complete RegulatoryStack."""
        result = civic_client.what_applies("traffic safety")

        # Check RegulatoryStack structure
        assert hasattr(result, "topic")
        assert hasattr(result, "jurisdiction")
        assert hasattr(result, "federal")
        assert hasattr(result, "state")
        assert hasattr(result, "local")

        assert result.topic == "traffic safety"
        assert result.jurisdiction == "city-san-rafael"


class TestPgVectorBackendDirect:
    """Direct tests for PgVectorBackend.search()."""

    @pytest.fixture
    def pgvector_backend(self):
        """Get PgVectorBackend connected to database."""
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set")

        from civicos.storage.pgvector_backend import PgVectorBackend
        return PgVectorBackend(db_url, provider_type="fastembed")

    def test_search_municipal_code(self, pgvector_backend):
        """PgVectorBackend.search() returns municipal code results."""
        results = pgvector_backend.search(
            query="zoning variance",
            jurisdiction_id="city-san-rafael",
            corpus_type="municipal_code",
            top_k=5,
        )

        assert len(results) > 0, "Expected results from municipal code search"

        # Check result structure
        for result in results:
            assert hasattr(result, "id")
            assert hasattr(result, "content")
            assert hasattr(result, "metadata")
            assert hasattr(result, "score")

    def test_search_respects_top_k(self, pgvector_backend):
        """Search respects top_k parameter."""
        results = pgvector_backend.search(
            query="building height",
            jurisdiction_id="city-san-rafael",
            corpus_type="municipal_code",
            top_k=3,
        )

        assert len(results) <= 3, f"Expected at most 3 results, got {len(results)}"

    def test_search_different_corpus_types(self, pgvector_backend):
        """Search works across different corpus types."""
        # Test transcripts corpus (plural naming convention)
        transcript_results = pgvector_backend.search(
            query="housing discussion",
            jurisdiction_id="city-san-rafael",
            corpus_type="transcripts",
            top_k=3,
        )

        # Test decisions corpus (plural naming convention)
        decision_results = pgvector_backend.search(
            query="approved project",
            jurisdiction_id="city-san-rafael",
            corpus_type="decisions",
            top_k=3,
        )

        # At least one corpus should have results
        assert transcript_results or decision_results, (
            "Expected results from at least one corpus type (transcripts or decisions)"
        )


class TestVectorEmbeddingCounts:
    """Tests validating expected embedding counts in pgvector."""

    @pytest.fixture
    def pgvector_backend(self):
        """Get PgVectorBackend connected to database."""
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set")

        from civicos.storage.pgvector_backend import PgVectorBackend
        return PgVectorBackend(db_url, provider_type="fastembed")

    def test_municipal_code_has_embeddings(self, pgvector_backend):
        """San Rafael municipal code has substantial embeddings."""
        results = pgvector_backend.search(
            query="test query for counting",
            jurisdiction_id="city-san-rafael",
            corpus_type="municipal_code",
            top_k=100,
        )

        # Should have many municipal code embeddings (expect 5000+)
        # A search returning 100 results indicates the corpus is populated
        assert len(results) > 50, (
            f"Expected many municipal code embeddings, got only {len(results)} results"
        )
