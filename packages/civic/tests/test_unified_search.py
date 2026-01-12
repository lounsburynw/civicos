"""
Tests for UnifiedSearch cross-corpus semantic search.

This module validates the UnifiedSearch class that provides unified
search across all 8 corpus types: decisions, pdf, transcript, issue,
municipal_code, legislation, programs, state_programs.

Run: pytest packages/civic/tests/test_unified_search.py -v
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch

from civic._internal.search.unified import (
    UnifiedSearch,
    CorpusInfo,
    CORPUS_TYPES,
)
from civic.history import UnifiedSearchResult


# Skip integration tests if no vector index exists
VECTOR_DIR = "data/pilot/vectors/city-san-rafael"
requires_vector_index = pytest.mark.skipif(
    not os.path.exists(VECTOR_DIR),
    reason="Vector index not available"
)


class TestCorpusTypes:
    """Test corpus type constants."""

    def test_corpus_types_contains_all_types(self):
        """CORPUS_TYPES includes all 8 corpus types."""
        assert "decision" in CORPUS_TYPES
        assert "pdf" in CORPUS_TYPES
        assert "transcript" in CORPUS_TYPES
        assert "issue" in CORPUS_TYPES
        assert "municipal_code" in CORPUS_TYPES
        assert "legislation" in CORPUS_TYPES
        assert "programs" in CORPUS_TYPES
        assert "state_programs" in CORPUS_TYPES
        assert len(CORPUS_TYPES) == 8

    def test_corpus_types_is_frozen(self):
        """CORPUS_TYPES cannot be modified."""
        assert isinstance(CORPUS_TYPES, frozenset)


class TestCorpusInfo:
    """Test CorpusInfo dataclass."""

    def test_corpus_info_creation(self):
        """CorpusInfo stores corpus metadata."""
        info = CorpusInfo(name="decision", document_count=100, available=True)
        assert info.name == "decision"
        assert info.document_count == 100
        assert info.available is True

    def test_corpus_info_unavailable(self):
        """CorpusInfo can represent unavailable corpus."""
        info = CorpusInfo(name="municipal_code", document_count=0, available=False)
        assert info.available is False
        assert info.document_count == 0


class TestUnifiedSearchInit:
    """Test UnifiedSearch initialization."""

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_init_creates_embeddings(self, mock_embeddings_cls):
        """UnifiedSearch creates CivicEmbeddings on init."""
        mock_embeddings = Mock()
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")

        mock_embeddings_cls.assert_called_once_with(
            jurisdiction_id="city-san-rafael",
            persist_directory=None,
        )
        assert search.jurisdiction_id == "city-san-rafael"
        assert search._embeddings is mock_embeddings

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_init_with_custom_persist_dir(self, mock_embeddings_cls):
        """UnifiedSearch accepts custom persist directory."""
        mock_embeddings = Mock()
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael", persist_directory="/custom/path")

        mock_embeddings_cls.assert_called_once_with(
            jurisdiction_id="city-san-rafael",
            persist_directory="/custom/path",
        )


class TestUnifiedSearchGetAvailableCorpora:
    """Test get_available_corpora method."""

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_get_available_corpora_all_available(self, mock_embeddings_cls):
        """get_available_corpora returns info for all corpus types."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"
        mock_embeddings.federal_programs_collection_name = "test_federal_programs"
        mock_embeddings.county_programs_collection_name = "test_county_programs"

        # Mock collection with document counts
        mock_collection = Mock()
        mock_collection.count.return_value = 50
        mock_client = Mock()
        mock_client.get_collection.return_value = mock_collection
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        corpora = search.get_available_corpora()

        assert len(corpora) == 7
        assert corpora["decision"].available is True
        assert corpora["decision"].document_count == 50
        assert corpora["pdf"].available is True
        assert corpora["transcript"].available is True
        assert corpora["issue"].available is True
        assert corpora["municipal_code"].available is True
        assert corpora["legislation"].available is True
        assert corpora["programs"].available is True

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_get_available_corpora_some_missing(self, mock_embeddings_cls):
        """get_available_corpora handles missing collections."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"
        mock_embeddings.federal_programs_collection_name = "test_federal_programs"
        mock_embeddings.county_programs_collection_name = "test_county_programs"

        # Mock client that raises for some collections
        def get_collection_side_effect(name):
            if name in ["test_decisions", "test_chunks"]:
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Collection not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        corpora = search.get_available_corpora()

        assert corpora["decision"].available is True
        assert corpora["decision"].document_count == 100
        assert corpora["pdf"].available is True
        assert corpora["transcript"].available is False
        assert corpora["transcript"].document_count == 0
        assert corpora["issue"].available is False
        assert corpora["municipal_code"].available is False
        assert corpora["legislation"].available is False
        assert corpora["programs"].available is False

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_get_available_corpora_caches_result(self, mock_embeddings_cls):
        """get_available_corpora caches result by default."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"
        mock_embeddings.federal_programs_collection_name = "test_federal_programs"
        mock_embeddings.county_programs_collection_name = "test_county_programs"

        mock_collection = Mock()
        mock_collection.count.return_value = 10
        mock_client = Mock()
        mock_client.get_collection.return_value = mock_collection
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")

        # First call
        corpora1 = search.get_available_corpora()
        # Second call - should use cache
        corpora2 = search.get_available_corpora()

        # Should only query collections once (8 collections: 6 base + federal_programs + county_programs)
        assert mock_client.get_collection.call_count == 8
        assert corpora1 is corpora2

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_get_available_corpora_refresh(self, mock_embeddings_cls):
        """get_available_corpora refresh=True bypasses cache."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"
        mock_embeddings.federal_programs_collection_name = "test_federal_programs"
        mock_embeddings.county_programs_collection_name = "test_county_programs"

        mock_collection = Mock()
        mock_collection.count.return_value = 10
        mock_client = Mock()
        mock_client.get_collection.return_value = mock_collection
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")

        # First call
        search.get_available_corpora()
        # Second call with refresh
        search.get_available_corpora(refresh=True)

        # Should query collections twice (8 + 8)
        assert mock_client.get_collection.call_count == 16


class TestUnifiedSearchSearchAll:
    """Test search_all method."""

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_invalid_corpus_type(self, mock_embeddings_cls):
        """search_all raises ValueError for invalid corpus type."""
        mock_embeddings = Mock()
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")

        with pytest.raises(ValueError) as exc_info:
            search.search_all("housing", corpus_types=["invalid_type"])

        assert "Invalid corpus types" in str(exc_info.value)
        assert "invalid_type" in str(exc_info.value)

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_returns_empty_when_no_corpora(self, mock_embeddings_cls):
        """search_all returns empty list when no corpora available."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        # All collections raise (don't exist)
        mock_client = Mock()
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        results = search.search_all("housing")

        assert results == []

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_queries_available_corpora(self, mock_embeddings_cls):
        """search_all queries all available corpora."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        # Only decisions and chunks available
        def get_collection_side_effect(name):
            if name in ["test_decisions", "test_chunks"]:
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        # Mock search results
        mock_decision_result = Mock()
        mock_decision_result.document_id = "decision-1"
        mock_decision_result.text = "Housing resolution"
        mock_decision_result.score = 0.9
        mock_decision_result.metadata = {"title": "Housing Res"}

        mock_chunk_result = Mock()
        mock_chunk_result.document_id = "chunk-1"
        mock_chunk_result.text = "Staff report content"
        mock_chunk_result.score = 0.85
        mock_chunk_result.metadata = {"agenda_item": "6.a"}

        mock_embeddings.search_decisions.return_value = [mock_decision_result]
        mock_embeddings.search_chunks.return_value = [mock_chunk_result]
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        results = search.search_all("housing", top_k=10)

        # Should have called search methods for available corpora
        mock_embeddings.search_decisions.assert_called_once()
        mock_embeddings.search_chunks.assert_called_once()
        # Should NOT call search for unavailable corpora
        mock_embeddings.search_transcripts.assert_not_called()
        mock_embeddings.search_issues.assert_not_called()
        mock_embeddings.search_municipal_code.assert_not_called()
        mock_embeddings.search_legislation.assert_not_called()

        # Should have 2 results
        assert len(results) == 2

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_filters_by_corpus_types(self, mock_embeddings_cls):
        """search_all only queries specified corpus types."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        # All available
        mock_collection = Mock()
        mock_collection.count.return_value = 100
        mock_client = Mock()
        mock_client.get_collection.return_value = mock_collection
        mock_embeddings._client = mock_client

        mock_embeddings.search_decisions.return_value = []
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        search.search_all("housing", corpus_types=["decision"])

        # Should only call decision search
        mock_embeddings.search_decisions.assert_called_once()
        mock_embeddings.search_chunks.assert_not_called()
        mock_embeddings.search_transcripts.assert_not_called()
        mock_embeddings.search_issues.assert_not_called()
        mock_embeddings.search_municipal_code.assert_not_called()
        mock_embeddings.search_legislation.assert_not_called()

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_sorts_by_score(self, mock_embeddings_cls):
        """search_all returns results sorted by score (highest first)."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        # Only decisions available
        def get_collection_side_effect(name):
            if name == "test_decisions":
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        # Mock results with different scores
        result_low = Mock(document_id="d1", text="low", score=0.5, metadata={})
        result_high = Mock(document_id="d2", text="high", score=0.95, metadata={})
        result_mid = Mock(document_id="d3", text="mid", score=0.7, metadata={})

        mock_embeddings.search_decisions.return_value = [result_low, result_high, result_mid]
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        results = search.search_all("housing")

        # Should be sorted by score descending
        assert results[0].score == 0.95
        assert results[1].score == 0.7
        assert results[2].score == 0.5

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_respects_top_k(self, mock_embeddings_cls):
        """search_all limits results to top_k."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        def get_collection_side_effect(name):
            if name == "test_decisions":
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        # Return 10 results
        mock_results = [
            Mock(document_id=f"d{i}", text=f"text{i}", score=0.9 - i * 0.05, metadata={})
            for i in range(10)
        ]
        mock_embeddings.search_decisions.return_value = mock_results
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        results = search.search_all("housing", top_k=3)

        assert len(results) == 3

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_all_returns_unified_search_results(self, mock_embeddings_cls):
        """search_all returns UnifiedSearchResult objects."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        def get_collection_side_effect(name):
            if name == "test_decisions":
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        mock_result = Mock(
            document_id="decision-123",
            text="Resolution text",
            score=0.9,
            metadata={"title": "Resolution 123", "outcome": "approved"}
        )
        mock_embeddings.search_decisions.return_value = [mock_result]
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        results = search.search_all("resolution", top_k=5)

        assert len(results) == 1
        assert isinstance(results[0], UnifiedSearchResult)
        assert results[0].id == "decision-123"
        assert results[0].source_type == "decision"
        assert results[0].score == 0.9


class TestUnifiedSearchSearchCorpus:
    """Test search_corpus method."""

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_corpus_invalid_type(self, mock_embeddings_cls):
        """search_corpus raises ValueError for invalid corpus type."""
        mock_embeddings = Mock()
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")

        with pytest.raises(ValueError) as exc_info:
            search.search_corpus("invalid", "query")

        assert "Invalid corpus type" in str(exc_info.value)

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_corpus_unavailable(self, mock_embeddings_cls):
        """search_corpus raises ValueError for unavailable corpus."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        # No collections available
        mock_client = Mock()
        mock_client.get_collection.side_effect = Exception("Not found")
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")

        with pytest.raises(ValueError) as exc_info:
            search.search_corpus("decision", "query")

        assert "not available" in str(exc_info.value)

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_corpus_decision_with_filters(self, mock_embeddings_cls):
        """search_corpus passes filters to decision search."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        def get_collection_side_effect(name):
            if name == "test_decisions":
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        mock_embeddings.search_decisions.return_value = []
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        search.search_corpus(
            "decision",
            "housing",
            top_k=5,
            since_ts=1700000000,
            until_ts=1800000000,
        )

        mock_embeddings.search_decisions.assert_called_once_with(
            "housing",
            top_k=5,
            where=None,
            since_ts=1700000000,
            until_ts=1800000000,
        )

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_corpus_transcript_with_filters(self, mock_embeddings_cls):
        """search_corpus passes filters to transcript search."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"

        def get_collection_side_effect(name):
            if name == "test_transcripts":
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        mock_embeddings.search_transcripts.return_value = []
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        search.search_corpus(
            "transcript",
            "homeless",
            speaker_role="public",
            public_comment_only=True,
        )

        mock_embeddings.search_transcripts.assert_called_once_with(
            "homeless",
            top_k=10,
            where=None,
            speaker_role="public",
            public_comment_only=True,
        )

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_search_corpus_legislation_with_filters(self, mock_embeddings_cls):
        """search_corpus passes filters to legislation search."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"
        mock_embeddings.federal_programs_collection_name = "test_federal_programs"
        mock_embeddings.county_programs_collection_name = "test_county_programs"

        def get_collection_side_effect(name):
            if name == "test_legislation":
                mock_col = Mock()
                mock_col.count.return_value = 100
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client

        mock_embeddings.search_legislation.return_value = []
        mock_embeddings.has_legislation.return_value = True
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        search.search_corpus(
            "legislation",
            "housing bills",
            topic="housing",
        )

        mock_embeddings.search_legislation.assert_called_once_with(
            "housing bills",
            top_k=10,
            where=None,
            topic="housing",
        )


class TestUnifiedSearchGetStats:
    """Test get_stats method."""

    @patch("civic._internal.search.unified.CivicEmbeddings")
    def test_get_stats_returns_summary(self, mock_embeddings_cls):
        """get_stats returns comprehensive statistics."""
        mock_embeddings = Mock()
        mock_embeddings.decisions_collection_name = "test_decisions"
        mock_embeddings.chunks_collection_name = "test_chunks"
        mock_embeddings.transcripts_collection_name = "test_transcripts"
        mock_embeddings.issues_collection_name = "test_issues"
        mock_embeddings.municipal_code_collection_name = "test_muni"
        mock_embeddings.legislation_collection_name = "test_legislation"
        mock_embeddings.model_name = "nomic-embed-text-v1.5"
        mock_embeddings.embedding_dimension = 768

        # Mixed availability
        def get_collection_side_effect(name):
            counts = {
                "test_decisions": 50,
                "test_chunks": 200,
                "test_transcripts": 100,
            }
            if name in counts:
                mock_col = Mock()
                mock_col.count.return_value = counts[name]
                return mock_col
            raise Exception("Not found")

        mock_client = Mock()
        mock_client.get_collection.side_effect = get_collection_side_effect
        mock_embeddings._client = mock_client
        mock_embeddings_cls.return_value = mock_embeddings

        search = UnifiedSearch("city-san-rafael")
        stats = search.get_stats()

        assert stats["jurisdiction_id"] == "city-san-rafael"
        assert stats["model"] == "nomic-embed-text-v1.5"
        assert stats["embedding_dimension"] == 768
        assert stats["total_documents"] == 350
        assert set(stats["available_corpora"]) == {"decision", "pdf", "transcript"}
        assert stats["corpora"]["decision"]["document_count"] == 50
        assert stats["corpora"]["decision"]["available"] is True
        assert stats["corpora"]["issue"]["available"] is False


@requires_vector_index
class TestUnifiedSearchIntegration:
    """Integration tests with real vector index (requires data/pilot/vectors)."""

    def test_search_all_with_real_index(self):
        """search_all works with real San Rafael vector index."""
        search = UnifiedSearch("city-san-rafael")
        results = search.search_all("housing", top_k=5)

        # Should return results (San Rafael has housing-related content)
        assert len(results) > 0
        assert all(isinstance(r, UnifiedSearchResult) for r in results)
        assert all(0 <= r.score <= 1 for r in results)

    def test_get_available_corpora_with_real_index(self):
        """get_available_corpora reports real index state."""
        search = UnifiedSearch("city-san-rafael")
        corpora = search.get_available_corpora()

        # Decisions should be available (primary corpus)
        assert corpora["decision"].available is True
        assert corpora["decision"].document_count > 0

    def test_search_corpus_decision_with_real_index(self):
        """search_corpus works for decisions on real index."""
        search = UnifiedSearch("city-san-rafael")

        # Skip if decisions not available
        corpora = search.get_available_corpora()
        if not corpora["decision"].available:
            pytest.skip("Decisions corpus not available")

        results = search.search_corpus("decision", "affordable housing", top_k=3)

        assert len(results) <= 3
        assert all(r.source_type == "decision" for r in results)

    def test_get_stats_with_real_index(self):
        """get_stats returns real statistics."""
        search = UnifiedSearch("city-san-rafael")
        stats = search.get_stats()

        assert stats["jurisdiction_id"] == "city-san-rafael"
        assert stats["total_documents"] > 0
        assert len(stats["available_corpora"]) > 0
