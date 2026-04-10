"""
Tests for SemanticEnricher query building and summary generation.

Tests the pure-logic methods; LegalSearch/ContextBuilder are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from civicos._internal.legal.enrichment.semantic import (
    SemanticEnricher,
    create_semantic_enricher,
    DEPS_AVAILABLE,
)


@pytest.fixture
def mock_deps():
    """Patch LegalSearch and ContextBuilder so SemanticEnricher can be instantiated."""
    mock_search = MagicMock()
    mock_context_builder = MagicMock()
    with patch(
        "civicos._internal.legal.enrichment.semantic.LegalSearch",
        return_value=mock_search,
    ), patch(
        "civicos._internal.legal.enrichment.semantic.ContextBuilder",
        return_value=mock_context_builder,
    ), patch(
        "civicos._internal.legal.enrichment.semantic.DEPS_AVAILABLE",
        True,
    ):
        enricher = SemanticEnricher(persist_directory="/tmp/test")
        yield enricher, mock_search, mock_context_builder


# ---------- _build_query ----------

class TestBuildQuery:

    @pytest.fixture(autouse=True)
    def setup(self, mock_deps):
        self.enricher, _, _ = mock_deps

    def test_title_only(self):
        query = self.enricher._build_query({"title": "Housing affordability"})
        assert "Housing affordability" in query

    def test_title_and_description(self):
        query = self.enricher._build_query({
            "title": "Zoning amendment",
            "description": "Rezoning for mixed use",
        })
        assert "Zoning amendment" in query
        assert "Rezoning for mixed use" in query

    def test_long_description_truncated(self):
        long_desc = "A" * 300
        query = self.enricher._build_query({
            "title": "Test",
            "description": long_desc,
        })
        assert len(query) < 300  # Truncated desc + title
        assert "..." in query

    def test_project_type_included(self):
        query = self.enricher._build_query({
            "title": "Test",
            "project_type": "transportation",
        })
        assert "topic: transportation" in query

    def test_empty_opportunity_returns_empty(self):
        query = self.enricher._build_query({})
        assert query == ""

    def test_none_fields_skipped(self):
        query = self.enricher._build_query({
            "title": None,
            "description": None,
            "project_type": None,
        })
        assert query.strip() == ""


# ---------- _generate_summary ----------

class TestGenerateSummary:

    @pytest.fixture(autouse=True)
    def setup(self, mock_deps):
        self.enricher, _, _ = mock_deps

    def test_generates_summary_from_top_result(self):
        result = SimpleNamespace(
            bill_id="AB-1234",
            metadata={"title": "California Housing Act"},
        )
        summary = self.enricher._generate_summary([result], {"title": "Test"})
        assert "AB-1234" in summary
        assert "California Housing Act" in summary

    def test_empty_results_returns_empty(self):
        summary = self.enricher._generate_summary([], {"title": "Test"})
        assert summary == ""

    def test_missing_title_in_metadata(self):
        result = SimpleNamespace(
            bill_id="SB-100",
            metadata={},
        )
        summary = self.enricher._generate_summary([result], {})
        assert "SB-100" in summary
        assert "relevant legislation" in summary


# ---------- enrich ----------

class TestEnrich:

    @pytest.fixture(autouse=True)
    def setup(self, mock_deps):
        self.enricher, self.mock_search, self.mock_context_builder = mock_deps

    def test_returns_none_for_empty_opportunity(self):
        result = self.enricher.enrich({})
        assert result is None

    def test_returns_none_when_no_results(self):
        self.mock_search.query.return_value = []
        result = self.enricher.enrich({"title": "Test"})
        assert result is None

    def test_returns_complete_legislative_context(self):
        mock_result = SimpleNamespace(
            bill_id="AB-1234",
            metadata={"title": "California Housing Act"},
        )
        self.mock_search.query.return_value = [mock_result]
        self.mock_context_builder.build.return_value = {"context": "test"}

        result = self.enricher.enrich({"title": "Housing policy"})
        assert result["state_legislation_refs"] == ["AB-1234"]
        assert result["federal_program_refs"] == []
        assert "AB-1234" in result["relevance_summary"]
        assert "California Housing Act" in result["relevance_summary"]

    def test_unknown_bill_ids_excluded(self):
        mock_result = SimpleNamespace(
            bill_id="unknown",
            metadata={"title": "Some bill"},
        )
        self.mock_search.query.return_value = [mock_result]
        self.mock_context_builder.build.return_value = {}

        result = self.enricher.enrich({"title": "Test"})
        assert result["state_legislation_refs"] == []

    def test_max_two_bill_refs(self):
        results = [
            SimpleNamespace(bill_id=f"AB-{i}", metadata={"title": f"Bill {i}"})
            for i in range(5)
        ]
        self.mock_search.query.return_value = results
        self.mock_context_builder.build.return_value = {}

        result = self.enricher.enrich({"title": "Test"})
        assert len(result["state_legislation_refs"]) <= 2


# ---------- create_semantic_enricher ----------

class TestFactory:

    def test_factory_returns_enricher(self, mock_deps):
        with patch(
            "civicos._internal.legal.enrichment.semantic.LegalSearch",
            return_value=MagicMock(),
        ), patch(
            "civicos._internal.legal.enrichment.semantic.ContextBuilder",
            return_value=MagicMock(),
        ), patch(
            "civicos._internal.legal.enrichment.semantic.DEPS_AVAILABLE",
            True,
        ):
            enricher = create_semantic_enricher(persist_directory="/tmp/test")
            assert isinstance(enricher, SemanticEnricher)


# ---------- Import guard ----------

class TestImportGuard:

    def test_raises_without_deps(self):
        with patch(
            "civicos._internal.legal.enrichment.semantic.DEPS_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="Semantic enrichment requires"):
                SemanticEnricher()
