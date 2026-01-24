"""
Integration tests for pgvector search functionality.

These tests validate that the Civic API correctly uses pgvector for semantic
search across various corpus types (municipal code, transcripts, decisions, etc.).

Tests are marked with @pytest.mark.requires_pgvector and automatically skip
when DATABASE_URL is not set. In CI, these run with GitHub Actions secrets.

Run locally (with DATABASE_URL in .env):
    pytest packages/civicos/tests/test_integration_pgvector.py -v

Run in CI:
    Automatically runs as part of full test suite when DATABASE_URL secret is set.
"""

import os

import pytest

# Mark all tests as requiring pgvector
pytestmark = [pytest.mark.integration, pytest.mark.requires_pgvector]


# Module-scoped fixtures to avoid repeated model loading and query execution
# Each what_applies() call takes ~2 min due to semantic search, so cache results
@pytest.fixture(scope="module")
def civic_client():
    """Get Civic client connected to pgvector database (shared across tests)."""
    from dotenv import load_dotenv
    load_dotenv()

    from civicos import CivicOS
    return CivicOS("city-san-rafael")


@pytest.fixture(scope="module")
def pgvector_backend():
    """Get PgVectorBackend connected to database (shared across tests)."""
    from dotenv import load_dotenv
    load_dotenv()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL not set")

    from civicos.storage.pgvector_backend import PgVectorBackend
    return PgVectorBackend(db_url, provider_type="fastembed")


# Cache expensive what_applies() results - each call takes ~2 min
@pytest.fixture(scope="module")
def adu_regulatory_stack(civic_client):
    """Cached result for ADU zoning query (used by multiple tests)."""
    return civic_client.what_applies("ADU zoning regulations")


class TestMunicipalCodeSearch:
    """Tests for municipal code search via what_applies().

    Note: what_applies() takes ~2 min per call due to semantic search.
    Tests share cached fixtures where possible to minimize runtime.
    """

    def test_what_applies_returns_ordinances(self, adu_regulatory_stack):
        """what_applies() returns municipal code ordinances from pgvector."""
        # Should have local results
        assert adu_regulatory_stack.local, "Expected local results from what_applies()"

        # Should include ordinance type results
        ordinances = [r for r in adu_regulatory_stack.local if r.get("type") == "ordinance"]
        assert len(ordinances) > 0, "Expected ordinance results from municipal code search"

    def test_adu_query_finds_relevant_sections(self, adu_regulatory_stack):
        """ADU query should find relevant zoning sections."""
        ordinances = [r for r in adu_regulatory_stack.local if r.get("type") == "ordinance"]
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

    def test_municipal_code_result_structure(self, adu_regulatory_stack):
        """Municipal code results have expected fields."""
        # Reuse ADU result to check structure (saves ~2 min)
        ordinances = [r for r in adu_regulatory_stack.local if r.get("type") == "ordinance"]
        if ordinances:
            # Check first ordinance has expected fields
            ordinance = ordinances[0]
            assert "section_number" in ordinance
            assert "relevance_score" in ordinance
            assert ordinance["relevance_score"] > 0, "Relevance score should be positive"

    def test_municipal_code_relevance_scores(self, adu_regulatory_stack):
        """Municipal code results have reasonable relevance scores."""
        # Reuse ADU result to check scores (saves ~2 min)
        ordinances = [r for r in adu_regulatory_stack.local if r.get("type") == "ordinance"]
        if ordinances:
            # Scores should be between 0 and 1 (cosine similarity normalized)
            for ordinance in ordinances:
                score = ordinance.get("relevance_score", 0)
                assert 0 < score <= 1, f"Score {score} outside expected range (0, 1]"


class TestCrossCorpusSearch:
    """Tests for cross-corpus search functionality."""

    def test_what_applies_includes_state_results(self, adu_regulatory_stack):
        """what_applies() returns state legislation in addition to local."""
        # Reuse ADU result (saves ~2 min) - state results exist regardless of topic
        assert adu_regulatory_stack.state is not None, "Expected state results"

    def test_what_applies_returns_regulatory_stack(self, adu_regulatory_stack):
        """what_applies() returns a complete RegulatoryStack."""
        # Check RegulatoryStack structure using cached result
        assert hasattr(adu_regulatory_stack, "topic")
        assert hasattr(adu_regulatory_stack, "jurisdiction")
        assert hasattr(adu_regulatory_stack, "federal")
        assert hasattr(adu_regulatory_stack, "state")
        assert hasattr(adu_regulatory_stack, "local")

        assert adu_regulatory_stack.topic == "ADU zoning regulations"
        assert adu_regulatory_stack.jurisdiction == "city-san-rafael"


class TestPgVectorBackendDirect:
    """Direct tests for PgVectorBackend.search()."""

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


# Cache expensive housing funding query - takes ~2 min with semantic search
@pytest.fixture(scope="module")
def housing_funding_stack(civic_client):
    """Cached result for housing funding query (used by federal programs tests)."""
    return civic_client.what_applies("affordable housing funding")


class TestFederalProgramsSemanticSearch:
    """Tests for federal programs semantic search via what_applies().

    Validates that:
    1. Federal programs are returned alongside U.S. Code and CFR
    2. Relevant housing programs (CDBG, HOME, HTF) are found
    3. Result structure includes expected metadata fields
    4. Tiered response structure is applied
    """

    def test_what_applies_returns_federal_programs(self, housing_funding_stack):
        """what_applies() returns federal programs from vector search."""
        federal = housing_funding_stack.federal
        assert federal, "Expected federal results from what_applies()"

        # Should have federal_program type results
        programs = [r for r in federal if r.get("type") == "federal_program"]
        assert len(programs) > 0, "Expected federal_program results from semantic search"

    def test_housing_query_finds_relevant_programs(self, housing_funding_stack):
        """Housing funding query finds CDBG, HOME, or HTF programs."""
        programs = [r for r in housing_funding_stack.federal if r.get("type") == "federal_program"]

        # Extract program names
        program_names = [p.get("program_name", "").upper() for p in programs]

        # At least one of these key housing programs should be found
        expected_programs = ["CDBG", "HOME", "HOUSING TRUST", "LIHTC", "BLOCK GRANT"]
        found = any(
            any(exp in name for exp in expected_programs)
            for name in program_names
        )

        assert found, (
            f"Expected housing-related programs (CDBG, HOME, HTF, LIHTC), "
            f"got: {program_names[:5]}"
        )

    def test_federal_programs_have_required_fields(self, housing_funding_stack):
        """Federal program results include expected metadata fields."""
        programs = [r for r in housing_funding_stack.federal if r.get("type") == "federal_program"]

        if programs:
            program = programs[0]

            # Check required fields from semantic search
            assert "id" in program, "Federal program should have id"
            assert "program_name" in program, "Federal program should have program_name"
            assert "relevance_score" in program, "Federal program should have relevance_score"
            assert "tier" in program, "Federal program should have tier"

            # Check optional metadata fields
            assert "administering_agency" in program, "Federal program should have administering_agency"
            assert "description" in program, "Federal program should have description"

    def test_federal_programs_have_tiered_response(self, housing_funding_stack):
        """Federal programs use tiered response structure (primary/secondary)."""
        programs = [r for r in housing_funding_stack.federal if r.get("type") == "federal_program"]

        if programs:
            # Check tier values
            tiers = {p.get("tier") for p in programs}
            valid_tiers = {"primary", "secondary"}
            assert tiers.issubset(valid_tiers), f"Unexpected tiers: {tiers - valid_tiers}"

            # First 10 should be primary
            for i, p in enumerate(programs[:10]):
                assert p.get("tier") == "primary", f"Program {i} should be primary tier"

    def test_federal_programs_relevance_scores(self, housing_funding_stack):
        """Federal programs have reasonable relevance scores."""
        programs = [r for r in housing_funding_stack.federal if r.get("type") == "federal_program"]

        if programs:
            for p in programs:
                score = p.get("relevance_score", 0)
                # Scores should be between 0 and 1 (cosine similarity)
                assert 0 < score <= 1, f"Score {score} outside expected range (0, 1]"
                # Minimum threshold check
                assert score >= 0.4, f"Score {score} below minimum threshold 0.4"


class TestFederalProgramsIdBoosting:
    """Tests for ID boosting in federal programs search."""

    def test_cdbg_query_boosts_cdbg_program(self, civic_client):
        """Query mentioning CDBG should boost CDBG program to top."""
        result = civic_client.what_applies("CDBG grants for infrastructure")
        programs = [r for r in result.federal if r.get("type") == "federal_program"]

        if programs:
            # CDBG should be in top 3 when explicitly mentioned
            top_names = [p.get("program_name", "").upper() for p in programs[:3]]
            cdbg_in_top = any("CDBG" in name or "BLOCK GRANT" in name for name in top_names)

            assert cdbg_in_top, (
                f"CDBG should be boosted to top 3 when mentioned in query, "
                f"got: {top_names}"
            )
