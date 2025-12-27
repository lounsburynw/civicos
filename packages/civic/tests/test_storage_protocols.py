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

            # Decision methods
            def store_decisions(
                self,
                jurisdiction_id: str,
                decisions: List[Dict[str, Any]],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(decisions)

            def get_decisions(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                since: Optional[str] = None,
                until: Optional[str] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_decision_count(self, jurisdiction_id: str) -> int:
                return 0

            # Chunk methods
            def store_chunks(
                self,
                jurisdiction_id: str,
                chunks: List[Dict[str, Any]],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(chunks)

            def get_chunks(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                meeting_id: Optional[str] = None,
                agenda_item: Optional[str] = None,
                source_type: Optional[str] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_chunk_count(self, jurisdiction_id: str) -> int:
                return 0

            # Issue methods
            def store_issues(
                self,
                jurisdiction_id: str,
                issues: List[Dict[str, Any]],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(issues)

            def get_issues(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                provider: Optional[str] = None,
                status: Optional[str] = None,
                issue_type: Optional[str] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_issue_count(
                self, jurisdiction_id: str, provider: Optional[str] = None
            ) -> int:
                return 0

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

            # Decision methods
            def store_decisions(
                self,
                jurisdiction_id: str,
                decisions: List[Dict[str, Any]],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(decisions)

            def get_decisions(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                since: Optional[str] = None,
                until: Optional[str] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_decision_count(self, jurisdiction_id: str) -> int:
                return 0

            # Chunk methods
            def store_chunks(
                self,
                jurisdiction_id: str,
                chunks: List[Dict[str, Any]],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(chunks)

            def get_chunks(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                meeting_id: Optional[str] = None,
                agenda_item: Optional[str] = None,
                source_type: Optional[str] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_chunk_count(self, jurisdiction_id: str) -> int:
                return 0

            # Issue methods
            def store_issues(
                self,
                jurisdiction_id: str,
                issues: List[Dict[str, Any]],
                as_of: Optional[datetime] = None,
            ) -> int:
                return len(issues)

            def get_issues(
                self,
                jurisdiction_id: str,
                as_of: Optional[datetime] = None,
                provider: Optional[str] = None,
                status: Optional[str] = None,
                issue_type: Optional[str] = None,
                limit: Optional[int] = None,
            ) -> List[Dict[str, Any]]:
                return []

            def get_issue_count(
                self, jurisdiction_id: str, provider: Optional[str] = None
            ) -> int:
                return 0

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
    """Tests for PgVectorBackend implementation."""

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

    def test_pgvector_backend_has_implemented_methods(self):
        """PgVectorBackend has all required methods implemented."""
        from civic.storage import PgVectorBackend

        backend = PgVectorBackend(
            connection_string="postgresql://localhost/test"
        )

        # Verify methods exist and are callable
        assert callable(backend.validate)
        assert callable(backend.index_from_storage)
        assert callable(backend.search)
        assert callable(backend.get_stats)
        assert callable(backend.delete_index)

    def test_pgvector_backend_validate_without_connection(self):
        """PgVectorBackend.validate returns error when cannot connect."""
        from civic.storage import PgVectorBackend

        backend = PgVectorBackend(
            connection_string="postgresql://localhost:5432/nonexistent_db"
        )

        # Should not raise, but return validation result with errors
        result = backend.validate()
        assert result.connected is False or len(result.errors) > 0

    def test_pgvector_backend_is_importable(self):
        """PgVectorBackend can be imported from civic.storage."""
        from civic.storage import PgVectorBackend

        # Verify it's the correct class
        assert hasattr(PgVectorBackend, 'embedding_model')
        assert hasattr(PgVectorBackend, 'embedding_dimension')
        assert hasattr(PgVectorBackend, 'backend_type')


class TestGetStorageBackend:
    """Tests for get_storage_backend factory function."""

    def test_factory_is_importable(self):
        """get_storage_backend can be imported from civic.storage."""
        from civic.storage import get_storage_backend

        assert callable(get_storage_backend)

    def test_returns_sqlite_by_default(self, monkeypatch):
        """Returns SQLiteBackend when no DATABASE_URL is set."""
        from civic.storage import SQLiteBackend, get_storage_backend

        # Ensure DATABASE_URL is not set
        monkeypatch.delenv("DATABASE_URL", raising=False)

        backend = get_storage_backend()
        assert isinstance(backend, SQLiteBackend)
        assert backend.backend_type == "sqlite"

    def test_returns_sqlite_for_sqlite_url(self, tmp_path):
        """Returns SQLiteBackend for sqlite:/// URLs."""
        from civic.storage import SQLiteBackend, get_storage_backend

        db_path = str(tmp_path / "test.db")
        backend = get_storage_backend(f"sqlite:///{db_path}")

        assert isinstance(backend, SQLiteBackend)
        assert backend.backend_type == "sqlite"

    def test_returns_postgres_for_postgresql_url(self):
        """Returns PostgresBackend for postgresql:// URLs."""
        from civic.storage import PostgresBackend, get_storage_backend

        backend = get_storage_backend("postgresql://user:pass@localhost:5432/civic")

        assert isinstance(backend, PostgresBackend)
        assert backend.backend_type == "postgres"

    def test_returns_postgres_for_postgres_url(self):
        """Returns PostgresBackend for postgres:// URLs (alternate scheme)."""
        from civic.storage import PostgresBackend, get_storage_backend

        backend = get_storage_backend("postgres://user:pass@localhost:5432/civic")

        assert isinstance(backend, PostgresBackend)
        assert backend.backend_type == "postgres"

    def test_uses_environment_variable(self, monkeypatch, tmp_path):
        """Uses DATABASE_URL environment variable when no URL provided."""
        from civic.storage import SQLiteBackend, get_storage_backend

        db_path = str(tmp_path / "env_test.db")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

        backend = get_storage_backend()

        assert isinstance(backend, SQLiteBackend)

    def test_explicit_url_overrides_env(self, monkeypatch):
        """Explicit URL parameter overrides DATABASE_URL env var."""
        from civic.storage import PostgresBackend, get_storage_backend

        # Set env to SQLite
        monkeypatch.setenv("DATABASE_URL", "sqlite:///data/test.db")

        # But pass Postgres URL explicitly
        backend = get_storage_backend("postgresql://user:pass@localhost:5432/civic")

        assert isinstance(backend, PostgresBackend)

    def test_fallback_treats_path_as_sqlite(self, tmp_path):
        """Falls back to SQLite for plain paths (backwards compatibility)."""
        from civic.storage import SQLiteBackend, get_storage_backend

        db_path = str(tmp_path / "plain_path.db")
        backend = get_storage_backend(db_path)

        assert isinstance(backend, SQLiteBackend)


class TestPostgresBackendStructure:
    """Tests for PostgresBackend class structure (without real connection)."""

    def test_postgres_backend_is_importable(self):
        """PostgresBackend can be imported from civic.storage."""
        from civic.storage import PostgresBackend

        assert PostgresBackend is not None

    def test_postgres_backend_has_required_methods(self):
        """PostgresBackend has all StorageBackend methods."""
        from civic.storage import PostgresBackend

        required_methods = [
            'backend_type',
            'validate',
            'store_meetings',
            'get_meetings',
            'get_stats',
            'delete_meetings',
            # Operation tracking methods
            'create_operation',
            'update_operation_status',
            'complete_operation',
            'get_operation',
            'get_operations',
            # Decision methods (SESSION 366)
            'store_decisions',
            'get_decisions',
            'get_decision_count',
            # Chunk methods (SESSION 367)
            'store_chunks',
            'get_chunks',
            'get_chunk_count',
            # Video methods (SESSION 379)
            'store_videos',
            'get_videos',
            'get_video_count',
        ]

        for method in required_methods:
            assert hasattr(PostgresBackend, method), f"Missing method: {method}"

    def test_postgres_backend_type_property(self):
        """PostgresBackend.backend_type returns 'postgres'."""
        from civic.storage import PostgresBackend

        backend = PostgresBackend("postgresql://localhost/test")
        assert backend.backend_type == "postgres"


# ============================================================================
# Blob Storage Tests (SESSION 370)
# ============================================================================


class TestBlobStats:
    """Tests for BlobStats dataclass."""

    def test_basic_blob_stats(self):
        """BlobStats holds basic counts."""
        from civic.storage import BlobStats

        stats = BlobStats(
            total_objects=100,
            total_bytes=1024 * 1024,  # 1 MB
        )
        assert stats.total_objects == 100
        assert stats.total_bytes == 1024 * 1024

    def test_blob_stats_with_content_types(self):
        """BlobStats includes content type breakdown."""
        from civic.storage import BlobStats

        stats = BlobStats(
            total_objects=60,
            total_bytes=1024 * 1024 * 10,
            by_content_type={
                "application/pdf": 50,
                "audio/mpeg": 10,
            },
        )
        assert stats.by_content_type["application/pdf"] == 50
        assert stats.by_content_type["audio/mpeg"] == 10

    def test_blob_stats_to_dict(self):
        """BlobStats serializes to JSON-compatible dict."""
        from civic.storage import BlobStats

        stats = BlobStats(
            total_objects=10,
            total_bytes=500,
            by_content_type={"text/plain": 10},
            metadata={"bucket": "test-bucket"},
        )
        d = stats.to_dict()
        assert d["total_objects"] == 10
        assert d["total_bytes"] == 500
        assert d["by_content_type"]["text/plain"] == 10
        assert d["metadata"]["bucket"] == "test-bucket"


class TestBlobValidationResult:
    """Tests for BlobValidationResult dataclass."""

    def test_valid_blob_result(self):
        """Valid blob storage passes all checks."""
        from civic.storage import BlobValidationResult

        result = BlobValidationResult(
            is_valid=True,
            connected=True,
            writable=True,
            check_duration_ms=5.0,
        )
        assert result.is_valid
        assert result.connected
        assert result.writable
        assert len(result.errors) == 0

    def test_invalid_blob_result(self):
        """Invalid blob storage has errors."""
        from civic.storage import BlobValidationResult

        result = BlobValidationResult(
            is_valid=False,
            connected=False,
            writable=False,
            errors=["Bucket not found", "Access denied"],
            check_duration_ms=50.0,
        )
        assert not result.is_valid
        assert len(result.errors) == 2

    def test_blob_validation_to_dict(self):
        """BlobValidationResult serializes correctly."""
        from civic.storage import BlobValidationResult

        result = BlobValidationResult(
            is_valid=True,
            connected=True,
            writable=True,
            warnings=["Using free tier"],
        )
        d = result.to_dict()
        assert d["is_valid"]
        assert d["warnings"] == ["Using free tier"]


class TestBlobStorageProtocol:
    """Tests for BlobStorage protocol."""

    def test_protocol_is_runtime_checkable(self):
        """BlobStorage can be checked at runtime."""
        from civic.storage import BlobStats, BlobStorage, BlobValidationResult

        @dataclass
        class MockBlobStorage:
            _backend_type: str = "mock"

            @property
            def backend_type(self) -> str:
                return self._backend_type

            def validate(self) -> BlobValidationResult:
                return BlobValidationResult(
                    is_valid=True, connected=True, writable=True
                )

            def upload(
                self,
                key: str,
                data: bytes,
                content_type: Optional[str] = None,
                metadata: Optional[Dict[str, str]] = None,
            ) -> str:
                return f"mock://{key}"

            def download(self, key: str) -> bytes:
                return b"test data"

            def exists(self, key: str) -> bool:
                return True

            def delete(self, key: str) -> bool:
                return True

            def list_keys(self, prefix: str = "") -> List[str]:
                return []

            def get_stats(self) -> BlobStats:
                return BlobStats(total_objects=0, total_bytes=0)

        mock = MockBlobStorage()
        assert isinstance(mock, BlobStorage)

    def test_incomplete_blob_implementation_fails_check(self):
        """Incomplete BlobStorage implementation fails runtime check."""
        from civic.storage import BlobStorage

        class IncompleteBlobBackend:
            @property
            def backend_type(self) -> str:
                return "incomplete"

            # Missing: validate, upload, download, exists, delete, list_keys, get_stats

        incomplete = IncompleteBlobBackend()
        assert not isinstance(incomplete, BlobStorage)


class TestLocalBlobBackend:
    """Tests for LocalBlobBackend implementation."""

    def test_local_backend_type(self, tmp_path):
        """LocalBlobBackend has correct backend_type."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))
        assert backend.backend_type == "local"

    def test_local_validate_success(self, tmp_path):
        """LocalBlobBackend validates writable directory."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))
        result = backend.validate()

        assert result.is_valid
        assert result.connected
        assert result.writable
        assert len(result.errors) == 0

    def test_local_upload_and_download(self, tmp_path):
        """LocalBlobBackend can upload and download files."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        # Upload
        test_data = b"Hello, World!"
        path = backend.upload("test/file.txt", test_data, "text/plain")
        assert "test/file.txt" in path

        # Download
        downloaded = backend.download("test/file.txt")
        assert downloaded == test_data

    def test_local_exists(self, tmp_path):
        """LocalBlobBackend.exists checks for file presence."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        assert not backend.exists("nonexistent.txt")

        backend.upload("exists.txt", b"data")
        assert backend.exists("exists.txt")

    def test_local_delete(self, tmp_path):
        """LocalBlobBackend.delete removes files."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        backend.upload("to_delete.txt", b"data")
        assert backend.exists("to_delete.txt")

        result = backend.delete("to_delete.txt")
        assert result is True
        assert not backend.exists("to_delete.txt")

        # Deleting non-existent returns False
        result = backend.delete("nonexistent.txt")
        assert result is False

    def test_local_list_keys(self, tmp_path):
        """LocalBlobBackend.list_keys returns matching files."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        # Upload some files
        backend.upload("dir1/file1.txt", b"data1")
        backend.upload("dir1/file2.txt", b"data2")
        backend.upload("dir2/file3.txt", b"data3")

        # List all
        all_keys = backend.list_keys()
        assert len(all_keys) == 3

        # List with prefix
        dir1_keys = backend.list_keys("dir1/")
        assert len(dir1_keys) == 2
        assert all(k.startswith("dir1/") for k in dir1_keys)

    def test_local_get_stats(self, tmp_path):
        """LocalBlobBackend.get_stats returns correct counts."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        # Empty initially
        stats = backend.get_stats()
        assert stats.total_objects == 0
        assert stats.total_bytes == 0

        # Add files
        backend.upload("file1.txt", b"data1")
        backend.upload("file2.txt", b"data2data2")

        stats = backend.get_stats()
        assert stats.total_objects == 2
        assert stats.total_bytes == 15  # 5 + 10 bytes

    def test_local_download_nonexistent_raises(self, tmp_path):
        """LocalBlobBackend.download raises KeyError for missing files."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        with pytest.raises(KeyError):
            backend.download("nonexistent.txt")

    def test_local_nested_directories(self, tmp_path):
        """LocalBlobBackend handles nested directory structures."""
        from civic.storage import LocalBlobBackend

        backend = LocalBlobBackend(str(tmp_path / "blobs"))

        # Deep path
        backend.upload("city/san-rafael/2024/01/15/agenda.pdf", b"pdf data")

        assert backend.exists("city/san-rafael/2024/01/15/agenda.pdf")
        data = backend.download("city/san-rafael/2024/01/15/agenda.pdf")
        assert data == b"pdf data"


class TestR2Backend:
    """Tests for R2Backend class structure (without real connection)."""

    def test_r2_backend_is_importable(self):
        """R2Backend can be imported from civic.storage."""
        from civic.storage import R2Backend

        assert R2Backend is not None

    def test_r2_backend_has_required_methods(self):
        """R2Backend has all BlobStorage methods."""
        from civic.storage import R2Backend

        required_attrs = [
            'backend_type',
            'validate',
            'upload',
            'download',
            'exists',
            'delete',
            'list_keys',
            'get_stats',
            'from_env',
            'from_url',
        ]

        for attr in required_attrs:
            assert hasattr(R2Backend, attr), f"Missing: {attr}"

    def test_r2_from_url_validates_format(self):
        """R2Backend.from_url validates URL format."""
        from civic.storage import R2Backend

        # Invalid format (missing scheme)
        with pytest.raises(ValueError, match="Invalid R2 URL format"):
            R2Backend.from_url("account/bucket")

        # Invalid format (missing bucket)
        with pytest.raises(ValueError, match="Invalid R2 URL format"):
            R2Backend.from_url("r2://account_only")

    def test_r2_from_env_requires_url(self, monkeypatch):
        """R2Backend.from_env requires BLOB_STORAGE_URL."""
        from civic.storage import R2Backend

        monkeypatch.delenv("BLOB_STORAGE_URL", raising=False)

        with pytest.raises(ValueError, match="BLOB_STORAGE_URL"):
            R2Backend.from_env()


class TestGetBlobStorage:
    """Tests for get_blob_storage factory function."""

    def test_factory_is_importable(self):
        """get_blob_storage can be imported from civic.storage."""
        from civic.storage import get_blob_storage

        assert callable(get_blob_storage)

    def test_returns_local_by_default(self, monkeypatch):
        """Returns LocalBlobBackend when no BLOB_STORAGE_URL is set."""
        from civic.storage import LocalBlobBackend, get_blob_storage

        monkeypatch.delenv("BLOB_STORAGE_URL", raising=False)

        backend = get_blob_storage()
        assert isinstance(backend, LocalBlobBackend)
        assert backend.backend_type == "local"

    def test_returns_local_for_local_url(self, tmp_path):
        """Returns LocalBlobBackend for local:// URLs."""
        from civic.storage import LocalBlobBackend, get_blob_storage

        path = str(tmp_path / "blobs")
        backend = get_blob_storage(f"local://{path}")

        assert isinstance(backend, LocalBlobBackend)
        assert backend.backend_type == "local"

    def test_returns_r2_for_r2_url(self, monkeypatch):
        """Returns R2Backend for r2:// URLs (with credentials)."""
        from civic.storage import R2Backend, get_blob_storage

        # Set required credentials
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "test_key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test_secret")

        backend = get_blob_storage("r2://account123/bucket-name")

        assert isinstance(backend, R2Backend)
        assert backend.backend_type == "r2"

    def test_uses_environment_variable(self, monkeypatch, tmp_path):
        """Uses BLOB_STORAGE_URL environment variable when no URL provided."""
        from civic.storage import LocalBlobBackend, get_blob_storage

        path = str(tmp_path / "env_blobs")
        monkeypatch.setenv("BLOB_STORAGE_URL", f"local://{path}")

        backend = get_blob_storage()

        assert isinstance(backend, LocalBlobBackend)

    def test_explicit_url_overrides_env(self, monkeypatch, tmp_path):
        """Explicit URL parameter overrides BLOB_STORAGE_URL env var."""
        from civic.storage import LocalBlobBackend, get_blob_storage

        # Set env to one path
        monkeypatch.setenv("BLOB_STORAGE_URL", "local:///some/other/path")

        # But pass different path explicitly
        path = str(tmp_path / "explicit_blobs")
        backend = get_blob_storage(f"local://{path}")

        assert isinstance(backend, LocalBlobBackend)
        assert str(path) in str(backend.base_path)

    def test_fallback_treats_path_as_local(self, tmp_path):
        """Falls back to LocalBlobBackend for plain paths."""
        from civic.storage import LocalBlobBackend, get_blob_storage

        path = str(tmp_path / "plain_path")
        backend = get_blob_storage(path)

        assert isinstance(backend, LocalBlobBackend)


# ============================================================================
# Video Storage Tests (SESSION 379)
# ============================================================================


class TestVideoStorageMethods:
    """Tests for video storage methods on PostgresBackend."""

    def test_postgres_backend_has_video_methods(self):
        """PostgresBackend has video storage methods."""
        from civic.storage import PostgresBackend

        assert hasattr(PostgresBackend, 'store_videos')
        assert hasattr(PostgresBackend, 'get_videos')
        assert hasattr(PostgresBackend, 'get_video_count')

    def test_store_videos_signature(self):
        """store_videos has correct signature."""
        from civic.storage import PostgresBackend
        import inspect

        sig = inspect.signature(PostgresBackend.store_videos)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'jurisdiction_id' in params
        assert 'videos' in params
        assert 'as_of' in params

    def test_get_videos_signature(self):
        """get_videos has correct signature."""
        from civic.storage import PostgresBackend
        import inspect

        sig = inspect.signature(PostgresBackend.get_videos)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'jurisdiction_id' in params
        assert 'as_of' in params
        assert 'limit' in params

    def test_get_video_count_signature(self):
        """get_video_count has correct signature."""
        from civic.storage import PostgresBackend
        import inspect

        sig = inspect.signature(PostgresBackend.get_video_count)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'jurisdiction_id' in params
