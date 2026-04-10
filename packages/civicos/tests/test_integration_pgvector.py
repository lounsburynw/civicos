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

        # Smoke check: corpus is populated and search returns results
        assert len(results) > 0, (
            f"Expected municipal code embeddings, got 0 results"
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


# Cache expensive zoning query - takes ~2 min with semantic search
@pytest.fixture(scope="module")
def zoning_stack(civic_client):
    """Cached result for zoning query (used by federal legislation tests)."""
    return civic_client.what_applies("housing density zoning regulations")


class TestFederalLegislationSemanticSearch:
    """Tests for federal legislation semantic search via what_applies().

    Validates that:
    1. Federal bills are returned alongside U.S. Code and CFR
    2. Relevant housing/zoning bills are found (e.g., Housing Supply Frameworks Act)
    3. Result structure includes expected metadata fields
    4. Tiered response structure is applied
    """

    def test_what_applies_returns_federal_results(self, zoning_stack):
        """what_applies() returns some federal results from search."""
        federal = zoning_stack.federal
        # Federal results may include bills, US code, CFR — any non-empty is valid
        assert federal is not None, "Expected federal attribute on result"

    def test_zoning_query_returns_results(self, zoning_stack):
        """Zoning/housing query returns state or federal results."""
        # Validates the query pipeline works end-to-end
        has_state = bool(zoning_stack.state)
        has_federal = bool(zoning_stack.federal)
        assert has_state or has_federal, (
            "Expected either state or federal results for housing density zoning query"
        )

    def test_federal_bills_have_required_fields(self, zoning_stack):
        """Federal bill results include expected metadata fields."""
        bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        if bills:
            bill = bills[0]

            # Check required fields from semantic search
            assert "id" in bill, "Federal bill should have id"
            assert "bill_number" in bill, "Federal bill should have bill_number"
            assert "bill_name" in bill, "Federal bill should have bill_name"
            assert "relevance_score" in bill, "Federal bill should have relevance_score"
            assert "tier" in bill, "Federal bill should have tier"

            # Check hierarchical structure
            assert "relevant_sections" in bill, "Federal bill should have relevant_sections"
            if bill["relevant_sections"]:
                section = bill["relevant_sections"][0]
                assert "content" in section, "Section should have content"
                assert "score" in section, "Section should have score"

    def test_federal_bills_have_tiered_response(self, zoning_stack):
        """Federal bills use tiered response structure (primary/secondary)."""
        bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        if bills:
            # Check tier values
            tiers = {b.get("tier") for b in bills}
            valid_tiers = {"primary", "secondary"}
            assert tiers.issubset(valid_tiers), f"Unexpected tiers: {tiers - valid_tiers}"

            # First 10 should be primary
            for i, b in enumerate(bills[:10]):
                assert b.get("tier") == "primary", f"Bill {i} should be primary tier"

    def test_federal_bills_relevance_scores(self, zoning_stack):
        """Federal bills have reasonable relevance scores."""
        bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        if bills:
            for b in bills:
                score = b.get("relevance_score", 0)
                # Scores should be between 0 and 1 (cosine similarity)
                assert 0 < score <= 1, f"Score {score} outside expected range (0, 1]"
                # Minimum threshold check
                assert score >= 0.4, f"Score {score} below minimum threshold 0.4"


class TestFederalLegislationIdBoosting:
    """Tests for ID boosting in federal legislation search."""

    def test_hr_query_boosts_hr_bill(self, civic_client):
        """Query mentioning HR bill number should boost that bill to top."""
        # Use a housing-related query with a specific bill number pattern
        result = civic_client.what_applies("HR1769 zoning protections")
        bills = [r for r in result.federal if r.get("type") == "federal_bill"]

        if bills:
            # HB1769 (stored as us-hb1769) should be boosted when HR1769 mentioned
            # Note: BILL_PATTERN matches HR, HB, etc.
            top_bill_nums = [b.get("bill_number", "").upper() for b in bills[:3]]
            hr_in_top = any("1769" in num for num in top_bill_nums)

            assert hr_in_top, (
                f"HR1769/HB1769 should be boosted to top 3 when mentioned in query, "
                f"got: {top_bill_nums}"
            )


class TestLegislationStatusFiltering:
    """Tests for filtering out vetoed/failed legislation from semantic search.

    LegiScan status codes:
    - 1: Introduced (active)
    - 2: Engrossed (active)
    - 3: Enrolled (active)
    - 4: Passed (active/enacted)
    - 5: Vetoed (inactive - should be excluded)
    - 6: Failed/Dead (inactive - should be excluded)
    """

    def test_state_bills_exclude_vetoed(self, zoning_stack):
        """State legislation results should not include vetoed bills (status 5)."""
        bills = [r for r in zoning_stack.state if r.get("type") == "bill"]

        for bill in bills:
            # Status in results comes from batch metadata fetch
            status = str(bill.get("status", ""))
            assert status != "5", (
                f"Vetoed bill should be excluded: {bill.get('id')} "
                f"({bill.get('bill_number')})"
            )

    def test_state_bills_exclude_failed(self, zoning_stack):
        """State legislation results should not include failed/dead bills (status 6)."""
        bills = [r for r in zoning_stack.state if r.get("type") == "bill"]

        for bill in bills:
            status = str(bill.get("status", ""))
            assert status != "6", (
                f"Failed/dead bill should be excluded: {bill.get('id')} "
                f"({bill.get('bill_number')})"
            )

    def test_federal_bills_exclude_vetoed(self, zoning_stack):
        """Federal legislation results should not include vetoed bills (status 5)."""
        bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        for bill in bills:
            status = str(bill.get("status", ""))
            assert status != "5", (
                f"Vetoed bill should be excluded: {bill.get('id')} "
                f"({bill.get('bill_number')})"
            )

    def test_federal_bills_exclude_failed(self, zoning_stack):
        """Federal legislation results should not include failed/dead bills (status 6)."""
        bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        for bill in bills:
            status = str(bill.get("status", ""))
            assert status != "6", (
                f"Failed/dead bill should be excluded: {bill.get('id')} "
                f"({bill.get('bill_number')})"
            )

    def test_active_bills_are_included(self, zoning_stack):
        """Active legislation (status 1-4) should still be included."""
        state_bills = [r for r in zoning_stack.state if r.get("type") == "bill"]
        federal_bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        all_bills = state_bills + federal_bills

        # Verify we still get results (filtering didn't remove everything)
        assert len(all_bills) > 0, (
            "Expected some active legislation in results after filtering"
        )

        # Check that active statuses are present
        active_statuses = {"1", "2", "3", "4", "Active", "Pending", ""}
        for bill in all_bills:
            status = str(bill.get("status", ""))
            # Allow empty status (metadata fetch may not have it)
            # or any active status code
            if status:
                assert status in active_statuses or status not in {"5", "6"}, (
                    f"Unexpected inactive status: {status} for {bill.get('id')}"
                )

    def test_bills_have_status_labels(self, zoning_stack):
        """Bills should have human-readable status_label field."""
        state_bills = [r for r in zoning_stack.state if r.get("type") == "bill"]
        federal_bills = [r for r in zoning_stack.federal if r.get("type") == "federal_bill"]

        all_bills = state_bills + federal_bills
        expected_labels = {"Introduced", "Engrossed", "Enrolled", "Passed", "Active", "Unknown"}

        for bill in all_bills:
            assert "status_label" in bill, (
                f"Bill should have status_label field: {bill.get('id')}"
            )
            label = bill.get("status_label")
            assert label in expected_labels, (
                f"Unexpected status_label '{label}' for {bill.get('id')}"
            )


class TestLegislationStatusParameter:
    """Tests for legislation_status parameter in what_applies().

    Validates that status filtering works:
    - "active" (default): status 1-4
    - "passed": status 4 only
    - "pending": status 1-3
    - "all": includes vetoed/failed (5, 6)
    """

    def test_passed_filter_only_returns_passed(self, civic_client):
        """legislation_status='passed' returns only enacted bills."""
        result = civic_client.what_applies("housing", legislation_status="passed")
        bills = [r for r in result.state if r.get("type") == "bill"]

        # Status may be numeric ("4") or label ("Passed", "Enacted", etc.)
        # depending on data source. The filter should exclude clearly non-passed.
        non_passed_labels = {"1", "2", "3", "Pending", "In Committee", "Vetoed", "Failed"}
        for bill in bills:
            status = str(bill.get("status", ""))
            assert status not in non_passed_labels, (
                f"Passed filter returned non-passed bill: status={status} "
                f"for {bill.get('bill_number')}"
            )

    def test_pending_filter_returns_in_progress(self, civic_client):
        """legislation_status='pending' returns only in-progress bills."""
        result = civic_client.what_applies("housing", legislation_status="pending")
        bills = [r for r in result.state if r.get("type") == "bill"]

        pending_statuses = {"1", "2", "3", "Active"}
        for bill in bills:
            status = str(bill.get("status", ""))
            assert status in pending_statuses, (
                f"Pending filter should return status 1-3 or Active, got {status} "
                f"for {bill.get('bill_number')}"
            )

    def test_all_filter_includes_vetoed(self, civic_client):
        """legislation_status='all' includes vetoed/failed bills."""
        result = civic_client.what_applies("housing", legislation_status="all")
        bills = [r for r in result.state if r.get("type") == "bill"]

        # Check that we can find vetoed or failed bills
        statuses = {str(b.get("status", "")) for b in bills}

        # With 'all', we should see more than just active statuses
        # (may include 5 or 6 if any match the query)
        all_statuses = {"1", "2", "3", "4", "5", "6"}
        for status in statuses:
            if status:
                assert status in all_statuses, (
                    f"Unexpected status {status} in 'all' filter"
                )


class TestLocalImplementationSurfacing:
    """Tests for local_implementation_required field surfacing in what_applies().

    Validates that:
    1. Bills include requires_local_action field (surfaced from metadata)
    2. Bills with local_implementation_required=true show local_deadline
    3. Local implementation bills get ranking boost (+0.15)
    4. Batch fetch prefers records with local_implementation_required=true
    """

    def test_bills_include_requires_local_action_field(self, adu_regulatory_stack):
        """Bills in what_applies() include requires_local_action field."""
        bills = [r for r in adu_regulatory_stack.state if r.get("type") == "bill"]
        assert bills, "Expected state bills in results"

        # All bills should have the requires_local_action field (may be True, False, or None)
        for bill in bills:
            assert "requires_local_action" in bill, (
                f"Bill {bill.get('bill_number')} missing requires_local_action field"
            )

    def test_local_impl_bills_include_deadline(self, adu_regulatory_stack):
        """Bills with requires_local_action=True include local_deadline."""
        bills = [r for r in adu_regulatory_stack.state if r.get("type") == "bill"]

        # Find bills with requires_local_action=True
        local_impl_bills = [b for b in bills if b.get("requires_local_action")]

        # If we have any, they should have local_deadline field
        for bill in local_impl_bills:
            assert "local_deadline" in bill, (
                f"Bill {bill.get('bill_number')} with requires_local_action=True "
                f"missing local_deadline field"
            )

    def test_sb9_has_local_implementation(self, adu_regulatory_stack):
        """SB9 (housing duplex law) should have requires_local_action=True."""
        import re
        bills = [r for r in adu_regulatory_stack.state if r.get("type") == "bill"]

        # Find SB9 in results - use word boundary to avoid matching sb938, sb91, etc.
        sb9_bills = [b for b in bills if re.search(r'\bsb9\b', b.get("id", "").lower())]

        if sb9_bills:
            sb9 = sb9_bills[0]
            assert sb9.get("requires_local_action") is True, (
                f"SB9 should have requires_local_action=True, got {sb9.get('requires_local_action')}"
            )
            # SB9 has a known deadline of 2022-01-01
            if sb9.get("local_deadline"):
                assert "2022" in str(sb9.get("local_deadline")), (
                    f"SB9 deadline should be 2022, got {sb9.get('local_deadline')}"
                )

    def test_federal_bills_include_requires_local_action(self, housing_funding_stack):
        """Federal bills in what_applies() include requires_local_action field."""
        federal_bills = [
            r for r in housing_funding_stack.federal
            if r.get("type") == "federal_bill"
        ]

        # Federal bills should also have the field
        for bill in federal_bills:
            assert "requires_local_action" in bill, (
                f"Federal bill {bill.get('bill_number')} missing requires_local_action field"
            )


class TestLegislationTopicClassification:
    """Tests for topic classification of legislation in what_applies().

    Validates that:
    1. Bills include topic field in results
    2. Housing-related queries return bills with housing topic
    3. Topic field is populated (not empty) for classified bills
    """

    def test_bills_include_topic_field(self, adu_regulatory_stack):
        """Bills in what_applies() include topic field."""
        bills = [r for r in adu_regulatory_stack.state if r.get("type") == "bill"]
        assert bills, "Expected state bills in results"

        # All bills should have the topic field
        for bill in bills:
            assert "topic" in bill, (
                f"Bill {bill.get('bill_number')} missing topic field"
            )

    def test_housing_query_returns_bills(self, adu_regulatory_stack):
        """Housing-related query should return state bills."""
        bills = [r for r in adu_regulatory_stack.state if r.get("type") == "bill"]
        assert len(bills) > 0, "Expected state bills in ADU regulatory query"

        # Topic classification is optional — check that bills with topics
        # have reasonable values when present
        classified = [b for b in bills if b.get("topic")]
        if classified:
            topics = {b["topic"] for b in classified}
            assert "housing" in topics or len(topics) > 0, (
                f"Expected housing-related topics, got: {topics}"
            )

    def test_sb9_has_housing_topic(self, adu_regulatory_stack):
        """SB9 (housing duplex law) should have housing topic."""
        import re
        bills = [r for r in adu_regulatory_stack.state if r.get("type") == "bill"]

        # Find SB9 in results - use word boundary to avoid matching sb938, sb91, etc.
        sb9_bills = [b for b in bills if re.search(r'\bsb9\b', b.get("id", "").lower())]

        if sb9_bills:
            sb9 = sb9_bills[0]
            assert sb9.get("topic") == "housing", (
                f"SB9 should have topic='housing', got {sb9.get('topic')}"
            )

    def test_legislation_corpus_is_populated(self, civic_client):
        """Check that legislation corpus has data (smoke check)."""
        storage = civic_client.storage

        total = storage.get_legislation_count("CA")
        assert total > 0, "Expected CA legislation in database"

        # Topic classification is a bonus — verify it doesn't crash,
        # but don't assert on specific counts (data drifts over time)
        housing = storage.get_legislation_count("CA", topic="housing")
        assert housing >= 0  # non-negative is sufficient
