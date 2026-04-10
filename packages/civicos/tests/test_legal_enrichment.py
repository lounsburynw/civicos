"""
Tests for legal/enrichment/__init__.py — enrichment orchestration.

Covers: mode dispatch (keyword/semantic), error handling, batch enrichment,
output structure validation.
"""

import pytest
from unittest.mock import MagicMock, patch

from civicos._internal.legal.enrichment import (
    enrich_opportunity,
    enrich_opportunities_batch,
)


# ---------- enrich_opportunity ----------

class TestEnrichOpportunity:

    def test_unknown_mode_raises_with_mode_name(self):
        with pytest.raises(ValueError, match="neural_network"):
            enrich_opportunity({"title": "Test"}, mode="neural_network")

    def test_keyword_mode_requires_cache(self):
        with patch("civicos._internal.legal.enrichment.LEGACY_AVAILABLE", True):
            with pytest.raises(ValueError, match="cache required"):
                enrich_opportunity({"title": "Test"}, cache=None, mode="keyword")

    def test_keyword_mode_without_dependency_raises_import_error(self):
        with patch("civicos._internal.legal.enrichment.LEGACY_AVAILABLE", False):
            with pytest.raises(ImportError, match="civic-enrichment"):
                enrich_opportunity({"title": "Test"}, mode="keyword")

    def test_semantic_mode_without_dependency_raises_import_error(self):
        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", False):
            with pytest.raises(ImportError, match="embeddings"):
                enrich_opportunity({"title": "Test"}, mode="semantic")

    def test_keyword_mode_passes_opportunity_and_cache_to_backend(self):
        mock_cache = MagicMock()
        expected = {"state_legislation_refs": ["AB-123"], "relevance_summary": "Housing bill"}
        opportunity = {"title": "Housing", "project_type": "housing"}

        with patch("civicos._internal.legal.enrichment.LEGACY_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment._keyword_enrich", return_value=expected) as mock_fn:
            result = enrich_opportunity(opportunity, cache=mock_cache, mode="keyword")

        assert result["state_legislation_refs"] == ["AB-123"]
        assert result["relevance_summary"] == "Housing bill"
        # Verify the exact opportunity dict was passed (not modified)
        mock_fn.assert_called_once_with(opportunity, mock_cache)

    def test_semantic_mode_returns_enricher_result(self):
        expected = {
            "state_legislation_refs": ["SB-100"],
            "federal_program_refs": [],
            "relevance_summary": "Transit funding bill",
        }
        mock_enricher = MagicMock()
        mock_enricher.enrich.return_value = expected

        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment.SemanticEnricher", return_value=mock_enricher):
            result = enrich_opportunity({"title": "Transit"}, mode="semantic")

        assert result["state_legislation_refs"] == ["SB-100"]
        assert result["relevance_summary"] == "Transit funding bill"

    def test_semantic_mode_passes_kwargs_to_enricher_constructor(self):
        mock_enricher = MagicMock()
        mock_enricher.enrich.return_value = None

        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment.SemanticEnricher", return_value=mock_enricher) as mock_cls:
            enrich_opportunity(
                {"title": "Test"},
                mode="semantic",
                persist_directory="/custom/path",
                top_k=10,
            )

        # Verify kwargs were forwarded to constructor
        mock_cls.assert_called_once_with(persist_directory="/custom/path", top_k=10)
        # Verify enrich was called with the opportunity
        mock_enricher.enrich.assert_called_once_with({"title": "Test"})

    def test_semantic_mode_returns_none_when_no_match(self):
        mock_enricher = MagicMock()
        mock_enricher.enrich.return_value = None

        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment.SemanticEnricher", return_value=mock_enricher):
            result = enrich_opportunity({"title": "Obscure topic"}, mode="semantic")

        assert result is None


# ---------- enrich_opportunities_batch ----------

class TestEnrichOpportunitiesBatch:

    def test_unknown_mode_raises_with_mode_name(self):
        with pytest.raises(ValueError, match="magic"):
            enrich_opportunities_batch([{"title": "A"}], mode="magic")

    def test_keyword_batch_requires_cache(self):
        with patch("civicos._internal.legal.enrichment.LEGACY_AVAILABLE", True):
            with pytest.raises(ValueError, match="cache required"):
                enrich_opportunities_batch([{"title": "A"}], cache=None, mode="keyword")

    def test_keyword_batch_without_dependency_raises(self):
        with patch("civicos._internal.legal.enrichment.LEGACY_AVAILABLE", False):
            with pytest.raises(ImportError):
                enrich_opportunities_batch([{"title": "A"}], mode="keyword")

    def test_keyword_batch_returns_backend_result(self):
        mock_cache = MagicMock()
        opps = [{"title": "A"}, {"title": "B"}]
        enriched = [
            {"title": "A", "legislative_context": {"refs": ["AB-1"]}},
            {"title": "B"},
        ]

        with patch("civicos._internal.legal.enrichment.LEGACY_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment._keyword_enrich_batch", return_value=enriched) as mock_fn:
            result = enrich_opportunities_batch(opps, cache=mock_cache, mode="keyword")

        assert len(result) == 2
        assert result[0]["title"] == "A"
        assert "legislative_context" in result[0]
        assert result[1]["title"] == "B"
        mock_fn.assert_called_once_with(opps, mock_cache)

    def test_semantic_batch_adds_context_to_matched_items(self):
        opps = [{"title": "Housing"}, {"title": "Transit"}, {"title": "Zoning"}]

        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment.SemanticEnricher") as mock_cls:
            mock_enricher = MagicMock()
            mock_enricher.enrich.side_effect = [
                {"state_legislation_refs": ["AB-1"]},  # Housing matched
                None,  # Transit — no match
                {"state_legislation_refs": ["SB-2"]},  # Zoning matched
            ]
            mock_cls.return_value = mock_enricher

            result = enrich_opportunities_batch(opps, mode="semantic")

        assert len(result) == 3
        # Housing: enriched
        assert result[0]["title"] == "Housing"
        assert result[0]["legislative_context"]["state_legislation_refs"] == ["AB-1"]
        # Transit: no match, original preserved
        assert result[1]["title"] == "Transit"
        assert "legislative_context" not in result[1]
        # Zoning: enriched
        assert result[2]["title"] == "Zoning"
        assert result[2]["legislative_context"]["state_legislation_refs"] == ["SB-2"]

    def test_semantic_batch_preserves_all_original_fields(self):
        opps = [{"title": "A", "project_type": "housing", "custom": 42}]

        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment.SemanticEnricher") as mock_cls:
            mock_enricher = MagicMock()
            mock_enricher.enrich.return_value = {"refs": ["AB-1"]}
            mock_cls.return_value = mock_enricher

            result = enrich_opportunities_batch(opps, mode="semantic")

        assert result[0]["title"] == "A"
        assert result[0]["project_type"] == "housing"
        assert result[0]["custom"] == 42
        assert "legislative_context" in result[0]

    def test_semantic_batch_does_not_mutate_input(self):
        original = {"title": "Test", "extra": "value"}
        opps = [original]

        with patch("civicos._internal.legal.enrichment.SEMANTIC_AVAILABLE", True), \
             patch("civicos._internal.legal.enrichment.SemanticEnricher") as mock_cls:
            mock_enricher = MagicMock()
            mock_enricher.enrich.return_value = {"refs": ["AB-1"]}
            mock_cls.return_value = mock_enricher

            result = enrich_opportunities_batch(opps, mode="semantic")

        # Original dict should not be modified
        assert "legislative_context" not in original
        # But result should have it
        assert "legislative_context" in result[0]
