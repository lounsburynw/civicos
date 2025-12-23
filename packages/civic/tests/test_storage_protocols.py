"""
Tests for StorageBackend and VectorBackend protocols.

Verifies:
1. Protocol definitions are correctly structured
2. Dataclasses serialize properly
3. Protocol implementations can be validated at runtime
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from civic.storage import (
    SearchResult,
    StorageBackend,
    StorageStats,
    StorageValidationResult,
    VectorBackend,
    VectorStats,
    VectorValidationResult,
)


class TestStorageStats:
    """Tests for StorageStats dataclass."""

    def test_basic_stats(self):
        """StorageStats holds basic counts."""
        stats = StorageStats(
            jurisdiction_id="city-san-rafael",
            meeting_count=42,
            agenda_item_count=150,
        )
        assert stats.jurisdiction_id == "city-san-rafael"
        assert stats.meeting_count == 42
        assert stats.agenda_item_count == 150

    def test_stats_with_temporal_info(self):
        """StorageStats includes temporal boundaries."""
        now = datetime.now()
        stats = StorageStats(
            jurisdiction_id="city-san-rafael",
            meeting_count=10,
            agenda_item_count=50,
            earliest_meeting=datetime(2024, 1, 1),
            latest_meeting=datetime(2025, 12, 31),
            last_updated=now,
        )
        assert stats.earliest_meeting == datetime(2024, 1, 1)
        assert stats.latest_meeting == datetime(2025, 12, 31)
        assert stats.last_updated == now

    def test_stats_to_dict(self):
        """StorageStats serializes to JSON-compatible dict."""
        stats = StorageStats(
            jurisdiction_id="city-san-rafael",
            meeting_count=10,
            agenda_item_count=50,
            earliest_meeting=datetime(2024, 1, 1, 12, 0, 0),
            size_bytes=1024,
            metadata={"db_version": "1.0"},
        )
        d = stats.to_dict()
        assert d["jurisdiction_id"] == "city-san-rafael"
        assert d["meeting_count"] == 10
        assert d["earliest_meeting"] == "2024-01-01T12:00:00"
        assert d["size_bytes"] == 1024
        assert d["metadata"]["db_version"] == "1.0"


class TestStorageValidationResult:
    """Tests for StorageValidationResult dataclass."""

    def test_valid_result(self):
        """Valid storage backend passes all checks."""
        result = StorageValidationResult(
            is_valid=True,
            connected=True,
            schema_valid=True,
            check_duration_ms=15.5,
        )
        assert result.is_valid
        assert result.connected
        assert result.schema_valid
        assert len(result.errors) == 0

    def test_invalid_result(self):
        """Invalid storage backend has errors."""
        result = StorageValidationResult(
            is_valid=False,
            connected=False,
            schema_valid=False,
            errors=["Connection refused", "Schema version mismatch"],
            check_duration_ms=100.0,
        )
        assert not result.is_valid
        assert len(result.errors) == 2

    def test_validation_to_dict(self):
        """StorageValidationResult serializes correctly."""
        result = StorageValidationResult(
            is_valid=True,
            connected=True,
            schema_valid=True,
            warnings=["Using legacy schema"],
        )
        d = result.to_dict()
        assert d["is_valid"]
        assert d["warnings"] == ["Using legacy schema"]


class TestVectorStats:
    """Tests for VectorStats dataclass."""

    def test_basic_vector_stats(self):
        """VectorStats holds basic index info."""
        stats = VectorStats(
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
            document_count=100,
        )
        assert stats.jurisdiction_id == "city-san-rafael"
        assert stats.corpus_type == "meetings"
        assert stats.document_count == 100

    def test_coverage_calculation(self):
        """VectorStats calculates coverage percent."""
        stats = VectorStats(
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
            document_count=80,
            storage_document_count=100,
        )
        assert stats.coverage_percent == 80.0

    def test_coverage_none_when_no_storage_count(self):
        """Coverage is None when storage count unknown."""
        stats = VectorStats(
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
            document_count=100,
        )
        assert stats.coverage_percent is None

    def test_vector_stats_to_dict(self):
        """VectorStats serializes with coverage."""
        stats = VectorStats(
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
            document_count=50,
            storage_document_count=100,
            embedding_model="text-embedding-3-small",
            embedding_dimension=1536,
        )
        d = stats.to_dict()
        assert d["coverage_percent"] == 50.0
        assert d["embedding_model"] == "text-embedding-3-small"


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_basic_search_result(self):
        """SearchResult holds core fields."""
        result = SearchResult(
            id="meeting-123",
            content="City Council discussed housing policy",
            score=0.89,
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
        )
        assert result.id == "meeting-123"
        assert result.score == 0.89
        assert "housing" in result.content

    def test_search_result_with_meeting_info(self):
        """SearchResult includes source meeting details."""
        result = SearchResult(
            id="item-456",
            content="Approve rezoning for residential development",
            score=0.75,
            jurisdiction_id="city-san-rafael",
            corpus_type="agenda_items",
            meeting_id="meeting-123",
            meeting_title="City Council Regular Meeting",
            meeting_datetime=datetime(2025, 1, 15, 19, 0),
        )
        assert result.meeting_id == "meeting-123"
        assert result.meeting_datetime.year == 2025

    def test_search_result_to_dict(self):
        """SearchResult serializes correctly."""
        result = SearchResult(
            id="meeting-123",
            content="Test content",
            score=0.5,
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
            metadata={"category": "planning"},
        )
        d = result.to_dict()
        assert d["score"] == 0.5
        assert d["metadata"]["category"] == "planning"


class TestStorageBackendProtocol:
    """Tests for StorageBackend protocol."""

    def test_protocol_is_runtime_checkable(self):
        """StorageBackend can be checked at runtime."""
        # Create a mock implementation
        @dataclass
        class MockStorageBackend:
            _backend_type: str = "mock"

            @property
            def backend_type(self) -> str:
                return self._backend_type

            def validate(self) -> StorageValidationResult:
                return StorageValidationResult(
                    is_valid=True, connected=True, schema_valid=True
                )

            def store_meetings(
                self,
                jurisdiction_id: str,
                meetings: List[Any],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(meetings)

            def get_meetings(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                since: Optional[datetime] = None,
                until: Optional[datetime] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_stats(self, jurisdiction_id: str) -> StorageStats:
                return StorageStats(
                    jurisdiction_id=jurisdiction_id,
                    meeting_count=0,
                    agenda_item_count=0,
                )

            def delete_meetings(
                self,
                jurisdiction_id: str,
                meeting_ids: Optional[List[str]] = None,
            ) -> int:
                return 0

            def create_operation(
                self,
                operation_id: str,
                jurisdiction_id: str,
                name: str,
            ) -> Dict[str, Any]:
                return {"id": operation_id, "status": "pending"}

            def update_operation_status(
                self,
                operation_id: str,
                status: str,
                current_step: Optional[str] = None,
                progress_percent: Optional[float] = None,
                items_processed: Optional[int] = None,
                items_total: Optional[int] = None,
            ) -> bool:
                return True

            def complete_operation(
                self,
                operation_id: str,
                result: Dict[str, Any],
                error: Optional[str] = None,
            ) -> bool:
                return True

            def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
                return None

            def get_operations(
                self,
                jurisdiction_id: Optional[str] = None,
                status: Optional[str] = None,
                limit: int = 20,
            ) -> List[Dict[str, Any]]:
                return []

        mock = MockStorageBackend()
        assert isinstance(mock, StorageBackend)

    def test_incomplete_implementation_fails_check(self):
        """Incomplete StorageBackend implementation fails runtime check."""

        class IncompleteBackend:
            @property
            def backend_type(self) -> str:
                return "incomplete"

            # Missing: validate, store_meetings, get_meetings, get_stats, delete_meetings

        incomplete = IncompleteBackend()
        assert not isinstance(incomplete, StorageBackend)


class TestVectorBackendProtocol:
    """Tests for VectorBackend protocol."""

    def test_protocol_is_runtime_checkable(self):
        """VectorBackend can be checked at runtime."""

        @dataclass
        class MockVectorBackend:
            _backend_type: str = "mock"
            _embedding_model: str = "test-model"
            _embedding_dimension: int = 768

            @property
            def backend_type(self) -> str:
                return self._backend_type

            @property
            def embedding_model(self) -> str:
                return self._embedding_model

            @property
            def embedding_dimension(self) -> int:
                return self._embedding_dimension

            def validate(self) -> VectorValidationResult:
                return VectorValidationResult(
                    is_valid=True, connected=True, index_exists=True
                )

            def index_from_storage(
                self,
                storage_backend: StorageBackend,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                batch_size: int = 100,
            ) -> int:
                return 0

            def search(
                self,
                query: str,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                top_k: int = 5,
                min_score: Optional[float] = None,
            ) -> List[SearchResult]:
                return []

            def get_stats(
                self,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                storage_backend: Optional[StorageBackend] = None,
            ) -> VectorStats:
                return VectorStats(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=corpus_type,
                    document_count=0,
                )

            def delete_index(
                self,
                jurisdiction_id: str,
                corpus_type: Optional[str] = None,
            ) -> int:
                return 0

        mock = MockVectorBackend()
        assert isinstance(mock, VectorBackend)

    def test_embedding_properties_required(self):
        """VectorBackend requires embedding_model and embedding_dimension properties."""

        @dataclass
        class CompleteVectorBackend:
            """Backend with all required properties including embeddings."""

            @property
            def backend_type(self) -> str:
                return "complete"

            @property
            def embedding_model(self) -> str:
                return "nomic-ai/nomic-embed-text-v1.5"

            @property
            def embedding_dimension(self) -> int:
                return 768

            def validate(self) -> VectorValidationResult:
                return VectorValidationResult(
                    is_valid=True, connected=True, index_exists=True
                )

            def index_from_storage(
                self,
                storage_backend: StorageBackend,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                batch_size: int = 100,
            ) -> int:
                return 0

            def search(
                self,
                query: str,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                top_k: int = 5,
                min_score: Optional[float] = None,
            ) -> List[SearchResult]:
                return []

            def get_stats(
                self,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                storage_backend: Optional[StorageBackend] = None,
            ) -> VectorStats:
                return VectorStats(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=corpus_type,
                    document_count=0,
                    embedding_model=self.embedding_model,
                    embedding_dimension=self.embedding_dimension,
                )

            def delete_index(
                self,
                jurisdiction_id: str,
                corpus_type: Optional[str] = None,
            ) -> int:
                return 0

        backend = CompleteVectorBackend()
        assert isinstance(backend, VectorBackend)
        assert backend.embedding_model == "nomic-ai/nomic-embed-text-v1.5"
        assert backend.embedding_dimension == 768

        # Stats should include embedding info
        stats = backend.get_stats("city-san-rafael")
        assert stats.embedding_model == "nomic-ai/nomic-embed-text-v1.5"
        assert stats.embedding_dimension == 768

    def test_incomplete_vector_implementation_fails(self):
        """Incomplete VectorBackend fails runtime check."""

        class IncompleteVector:
            @property
            def backend_type(self) -> str:
                return "incomplete"

        incomplete = IncompleteVector()
        assert not isinstance(incomplete, VectorBackend)

    def test_missing_embedding_properties_fails(self):
        """VectorBackend without embedding properties fails runtime check."""

        class MissingEmbeddingVector:
            """Backend missing embedding_model and embedding_dimension."""

            @property
            def backend_type(self) -> str:
                return "incomplete"

            def validate(self) -> VectorValidationResult:
                return VectorValidationResult(
                    is_valid=True, connected=True, index_exists=True
                )

            def index_from_storage(
                self,
                storage_backend: StorageBackend,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                batch_size: int = 100,
            ) -> int:
                return 0

            def search(
                self,
                query: str,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                top_k: int = 5,
                min_score: Optional[float] = None,
            ) -> List[SearchResult]:
                return []

            def get_stats(
                self,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                storage_backend: Optional[StorageBackend] = None,
            ) -> VectorStats:
                return VectorStats(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=corpus_type,
                    document_count=0,
                )

            def delete_index(
                self,
                jurisdiction_id: str,
                corpus_type: Optional[str] = None,
            ) -> int:
                return 0

        incomplete = MissingEmbeddingVector()
        # Should fail because missing embedding_model and embedding_dimension
        assert not isinstance(incomplete, VectorBackend)


class TestProtocolIntegration:
    """Tests for protocol integration patterns."""

    def test_index_from_storage_pattern(self):
        """VectorBackend.index_from_storage reads from StorageBackend."""
        # This tests the key design principle: index reads from storage, not memory

        @dataclass
        class InMemoryStorage:
            _data: Dict[str, List[Dict]] = None
            _backend_type: str = "memory"

            def __post_init__(self):
                self._data = {}

            @property
            def backend_type(self) -> str:
                return self._backend_type

            def validate(self) -> StorageValidationResult:
                return StorageValidationResult(
                    is_valid=True, connected=True, schema_valid=True
                )

            def store_meetings(
                self,
                jurisdiction_id: str,
                meetings: List[Any],
                as_of: Optional[datetime] = None,
            ) -> int:
                self._data[jurisdiction_id] = meetings
                return len(meetings)

            def get_meetings(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                since: Optional[datetime] = None,
                until: Optional[datetime] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return self._data.get(jurisdiction_id, [])

            def get_stats(self, jurisdiction_id: str) -> StorageStats:
                data = self._data.get(jurisdiction_id, [])
                return StorageStats(
                    jurisdiction_id=jurisdiction_id,
                    meeting_count=len(data),
                    agenda_item_count=0,
                )

            def delete_meetings(
                self,
                jurisdiction_id: str,
                meeting_ids: Optional[List[str]] = None,
            ) -> int:
                count = len(self._data.get(jurisdiction_id, []))
                self._data[jurisdiction_id] = []
                return count

            def create_operation(
                self,
                operation_id: str,
                jurisdiction_id: str,
                name: str,
            ) -> Dict[str, Any]:
                return {"id": operation_id, "status": "pending"}

            def update_operation_status(
                self,
                operation_id: str,
                status: str,
                current_step: Optional[str] = None,
                progress_percent: Optional[float] = None,
                items_processed: Optional[int] = None,
                items_total: Optional[int] = None,
            ) -> bool:
                return True

            def complete_operation(
                self,
                operation_id: str,
                result: Dict[str, Any],
                error: Optional[str] = None,
            ) -> bool:
                return True

            def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
                return None

            def get_operations(
                self,
                jurisdiction_id: Optional[str] = None,
                status: Optional[str] = None,
                limit: int = 20,
            ) -> List[Dict[str, Any]]:
                return []

        @dataclass
        class InMemoryVector:
            _index: Dict[str, List[Dict]] = None
            _backend_type: str = "memory"
            _embedding_model: str = "test-model"
            _embedding_dimension: int = 768

            def __post_init__(self):
                self._index = {}

            @property
            def backend_type(self) -> str:
                return self._backend_type

            @property
            def embedding_model(self) -> str:
                return self._embedding_model

            @property
            def embedding_dimension(self) -> int:
                return self._embedding_dimension

            def validate(self) -> VectorValidationResult:
                return VectorValidationResult(
                    is_valid=True, connected=True, index_exists=True
                )

            def index_from_storage(
                self,
                storage_backend: StorageBackend,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                batch_size: int = 100,
            ) -> int:
                # Read from storage - the key pattern!
                meetings = storage_backend.get_meetings(jurisdiction_id)
                key = f"{jurisdiction_id}:{corpus_type}"
                self._index[key] = meetings
                return len(meetings)

            def search(
                self,
                query: str,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                top_k: int = 5,
                min_score: Optional[float] = None,
            ) -> List[SearchResult]:
                return []

            def get_stats(
                self,
                jurisdiction_id: str,
                corpus_type: str = "meetings",
                storage_backend: Optional[StorageBackend] = None,
            ) -> VectorStats:
                key = f"{jurisdiction_id}:{corpus_type}"
                count = len(self._index.get(key, []))
                return VectorStats(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=corpus_type,
                    document_count=count,
                )

            def delete_index(
                self,
                jurisdiction_id: str,
                corpus_type: Optional[str] = None,
            ) -> int:
                key = f"{jurisdiction_id}:{corpus_type or 'meetings'}"
                count = len(self._index.get(key, []))
                self._index[key] = []
                return count

        # Simulate 4-stage pipeline: discover -> ingest -> store -> index
        storage = InMemoryStorage()
        vector = InMemoryVector()

        # Verify protocols
        assert isinstance(storage, StorageBackend)
        assert isinstance(vector, VectorBackend)

        # Store phase
        meetings = [{"id": "1", "title": "Meeting 1"}, {"id": "2", "title": "Meeting 2"}]
        stored = storage.store_meetings("city-san-rafael", meetings)
        assert stored == 2

        # Index phase - reads from storage, not memory
        indexed = vector.index_from_storage(storage, "city-san-rafael", "meetings")
        assert indexed == 2

        # Verify stats
        storage_stats = storage.get_stats("city-san-rafael")
        vector_stats = vector.get_stats("city-san-rafael")
        assert storage_stats.meeting_count == 2
        assert vector_stats.document_count == 2


class TestPgVectorBackend:
    """Tests for PgVectorBackend stub implementation."""

    def test_pgvector_backend_has_required_properties(self):
        """PgVectorBackend exposes embedding_model and embedding_dimension."""
        from civic.storage import PgVectorBackend

        backend = PgVectorBackend(
            connection_string="postgresql://localhost/test",
            embedding_model="nomic-ai/nomic-embed-text-v1.5",
            embedding_dimension=768,
        )

        assert backend.backend_type == "pgvector"
        assert backend.embedding_model == "nomic-ai/nomic-embed-text-v1.5"
        assert backend.embedding_dimension == 768

    def test_pgvector_backend_uses_defaults(self):
        """PgVectorBackend uses default embedding model and dimension."""
        from civic.storage import PgVectorBackend

        backend = PgVectorBackend(
            connection_string="postgresql://localhost/test"
        )

        assert backend.backend_type == "pgvector"
        # Default model (may be overridden by CIVIC_EMBEDDING_MODEL env var)
        assert backend.embedding_model is not None
        assert len(backend.embedding_model) > 0
        # Default dimension for nomic-embed-text-v1.5
        assert backend.embedding_dimension == 768

    def test_pgvector_backend_methods_raise_not_implemented(self):
        """PgVectorBackend methods raise NotImplementedError (stub)."""
        from civic.storage import PgVectorBackend

        backend = PgVectorBackend(
            connection_string="postgresql://localhost/test"
        )

        # All methods should raise NotImplementedError
        with pytest.raises(NotImplementedError):
            backend.validate()

        with pytest.raises(NotImplementedError):
            backend.index_from_storage(None, "city-san-rafael")

        with pytest.raises(NotImplementedError):
            backend.search("housing", "city-san-rafael")

        with pytest.raises(NotImplementedError):
            backend.get_stats("city-san-rafael")

        with pytest.raises(NotImplementedError):
            backend.delete_index("city-san-rafael")

    def test_pgvector_backend_is_importable(self):
        """PgVectorBackend can be imported from civic.storage."""
        from civic.storage import PgVectorBackend

        # Verify it's the correct class
        assert hasattr(PgVectorBackend, 'embedding_model')
        assert hasattr(PgVectorBackend, 'embedding_dimension')
        assert hasattr(PgVectorBackend, 'backend_type')
