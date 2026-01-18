"""
Tests for vector indexing CLI safety features.

These tests validate the incremental indexing safety mechanisms:
1. Default behavior uses upsert (no deletion)
2. --reindex warns if delete > create and requires --force
3. --reindex --force proceeds even with count mismatch

Run:
    pytest packages/civic-extraction/tests/test_vectors_cli.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.cli.vectors import run_vector_indexing, VectorIndexResult


class MockStats:
    """Mock for pgvector.get_stats() return value."""
    def __init__(self, document_count: int = 0, storage_document_count: int = 0):
        self.document_count = document_count
        self.storage_document_count = storage_document_count
        self.embedding_model = "mock-model"
        self.embedding_dimension = 384
        self.last_indexed = None


class MockValidation:
    """Mock for pgvector.validate() return value."""
    is_valid = True
    errors = []
    warnings = []
    check_duration_ms = 10.0


class TestIncrementalIndexingSafety:
    """Tests for incremental vector indexing safety."""

    @pytest.mark.unit
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    @patch("civic.storage.pgvector_backend.PgVectorBackend")
    @patch("civic.storage.get_storage_backend")
    def test_incremental_mode_uses_upsert(self, mock_get_storage, MockPgVector):
        """Default (no --reindex) uses upsert via use_copy=False."""
        mock_backend = MagicMock()
        mock_get_storage.return_value = mock_backend

        mock_pgvector = MagicMock()
        MockPgVector.return_value = mock_pgvector
        mock_pgvector.validate.return_value = MockValidation()
        mock_pgvector.get_stats.return_value = MockStats(
            document_count=10,  # Existing vectors
            storage_document_count=15,  # More in storage
        )
        mock_pgvector.index_from_storage.return_value = 5  # Indexed 5 new

        run_vector_indexing(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            reindex=False,  # Incremental mode
        )

        # Should NOT call delete_index in incremental mode
        mock_pgvector.delete_index.assert_not_called()

        # Should call index_from_storage with use_copy=False (upsert mode)
        mock_pgvector.index_from_storage.assert_called_once()
        call_kwargs = mock_pgvector.index_from_storage.call_args.kwargs
        assert call_kwargs.get("use_copy") is False or "use_copy" not in call_kwargs, \
            "Incremental mode should use upsert (use_copy=False)"

    @pytest.mark.unit
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    @patch("civic.storage.pgvector_backend.PgVectorBackend")
    @patch("civic.storage.get_storage_backend")
    def test_reindex_matching_counts_proceeds(self, mock_get_storage, MockPgVector):
        """--reindex proceeds normally when counts match."""
        mock_backend = MagicMock()
        mock_get_storage.return_value = mock_backend

        mock_pgvector = MagicMock()
        MockPgVector.return_value = mock_pgvector
        mock_pgvector.validate.return_value = MockValidation()
        mock_pgvector.get_stats.return_value = MockStats(
            document_count=10,  # Existing vectors
            storage_document_count=10,  # Same count in storage
        )
        mock_pgvector.delete_index.return_value = 10
        mock_pgvector.index_from_storage.return_value = 10

        results = run_vector_indexing(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            reindex=True,
            force=False,  # No force needed when counts match
        )

        # Should proceed with deletion and indexing
        mock_pgvector.delete_index.assert_called_once()
        mock_pgvector.index_from_storage.assert_called_once()

        assert results is not None
        assert len(results) == 1
        assert results[0].status == "success"

    @pytest.mark.unit
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    @patch("civic.storage.pgvector_backend.PgVectorBackend")
    @patch("civic.storage.get_storage_backend")
    def test_reindex_delete_exceeds_create_fails_without_force(self, mock_get_storage, MockPgVector):
        """--reindex fails when delete > create without --force."""
        mock_backend = MagicMock()
        mock_get_storage.return_value = mock_backend

        mock_pgvector = MagicMock()
        MockPgVector.return_value = mock_pgvector
        mock_pgvector.validate.return_value = MockValidation()
        mock_pgvector.get_stats.return_value = MockStats(
            document_count=50,  # Many existing vectors
            storage_document_count=10,  # Far fewer in current storage query
        )

        results = run_vector_indexing(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            reindex=True,
            force=False,  # No force - should fail
        )

        # Should NOT delete or index
        mock_pgvector.delete_index.assert_not_called()
        mock_pgvector.index_from_storage.assert_not_called()

        # Should return error result
        assert results is not None
        assert len(results) == 1
        assert results[0].status == "error"
        assert results[0].error is not None and "Safety check failed" in results[0].error

    @pytest.mark.unit
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    @patch("civic.storage.pgvector_backend.PgVectorBackend")
    @patch("civic.storage.get_storage_backend")
    def test_reindex_force_proceeds_despite_mismatch(self, mock_get_storage, MockPgVector):
        """--reindex --force proceeds even when delete > create."""
        mock_backend = MagicMock()
        mock_get_storage.return_value = mock_backend

        mock_pgvector = MagicMock()
        MockPgVector.return_value = mock_pgvector
        mock_pgvector.validate.return_value = MockValidation()
        mock_pgvector.get_stats.return_value = MockStats(
            document_count=50,  # Many existing vectors
            storage_document_count=10,  # Far fewer in current storage query
        )
        mock_pgvector.delete_index.return_value = 50
        mock_pgvector.index_from_storage.return_value = 10

        results = run_vector_indexing(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            reindex=True,
            force=True,  # Force allows destructive operation
        )

        # Should proceed with deletion despite mismatch
        mock_pgvector.delete_index.assert_called_once()
        mock_pgvector.index_from_storage.assert_called_once()

        assert results is not None
        assert len(results) == 1
        assert results[0].status == "success"

    @pytest.mark.unit
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    @patch("civic.storage.pgvector_backend.PgVectorBackend")
    @patch("civic.storage.get_storage_backend")
    def test_reindex_uses_copy_mode(self, mock_get_storage, MockPgVector):
        """--reindex uses COPY mode (faster) since we've deleted existing vectors."""
        mock_backend = MagicMock()
        mock_get_storage.return_value = mock_backend

        mock_pgvector = MagicMock()
        MockPgVector.return_value = mock_pgvector
        mock_pgvector.validate.return_value = MockValidation()
        mock_pgvector.get_stats.return_value = MockStats(
            document_count=10,
            storage_document_count=10,
        )
        mock_pgvector.delete_index.return_value = 10
        mock_pgvector.index_from_storage.return_value = 10

        run_vector_indexing(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            reindex=True,
        )

        # Should use COPY mode (use_copy=True) since we deleted first
        mock_pgvector.index_from_storage.assert_called_once()
        call_kwargs = mock_pgvector.index_from_storage.call_args.kwargs
        assert call_kwargs.get("use_copy") is True, \
            "Reindex mode should use COPY (use_copy=True) for speed"

    @pytest.mark.unit
    @patch.dict("os.environ", {"DATABASE_URL": "postgres://test"})
    @patch("civic.storage.pgvector_backend.PgVectorBackend")
    @patch("civic.storage.get_storage_backend")
    def test_incremental_skips_fully_indexed(self, mock_get_storage, MockPgVector):
        """Incremental mode skips corpus that is already fully indexed."""
        mock_backend = MagicMock()
        mock_get_storage.return_value = mock_backend

        mock_pgvector = MagicMock()
        MockPgVector.return_value = mock_pgvector
        mock_pgvector.validate.return_value = MockValidation()
        mock_pgvector.get_stats.return_value = MockStats(
            document_count=10,  # Already indexed
            storage_document_count=10,  # Same as vectors
        )

        results = run_vector_indexing(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            reindex=False,  # Incremental
        )

        # Should skip since already fully indexed
        mock_pgvector.delete_index.assert_not_called()
        mock_pgvector.index_from_storage.assert_not_called()

        assert results is not None
        assert len(results) == 1
        assert results[0].status == "skipped"


class TestVectorIndexResult:
    """Tests for VectorIndexResult dataclass."""

    @pytest.mark.unit
    def test_success_result(self):
        """VectorIndexResult success state."""
        result = VectorIndexResult(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            documents_indexed=10,
            status="success",
        )
        assert result.status == "success"
        assert result.error is None

    @pytest.mark.unit
    def test_error_result(self):
        """VectorIndexResult error state."""
        result = VectorIndexResult(
            jurisdiction_id="city-test",
            corpus_type="decisions",
            documents_indexed=0,
            status="error",
            error="Test error message",
        )
        assert result.status == "error"
        assert result.error is not None and "Test error" in result.error
