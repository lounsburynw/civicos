"""
VectorBackend protocol for semantic search indexing.

Defines the interface for vector search operations (ChromaDB, pgvector).
Part of the 4-stage pipeline: discover -> ingest -> store -> index.

Key design principle: Index reads from StorageBackend, not memory.
This ensures persistence and allows re-indexing without re-fetching.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .backend import StorageBackend


@dataclass
class SearchResult:
    """
    Single result from vector similarity search.
    """

    id: str
    content: str
    score: float  # Similarity score (higher = more similar)

    # Source info
    jurisdiction_id: str
    corpus_type: str  # "meetings", "agenda_items", "legislation"

    # Optional metadata
    meeting_id: Optional[str] = None
    meeting_title: Optional[str] = None
    meeting_datetime: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "jurisdiction_id": self.jurisdiction_id,
            "corpus_type": self.corpus_type,
            "meeting_id": self.meeting_id,
            "meeting_title": self.meeting_title,
            "meeting_datetime": (
                self.meeting_datetime.isoformat() if self.meeting_datetime else None
            ),
            "metadata": self.metadata,
        }


@dataclass
class VectorStats:
    """
    Statistics for a vector collection.

    Used by dashboards to show index health and coverage.
    """

    jurisdiction_id: str
    corpus_type: str
    document_count: int

    # Index info
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    last_indexed: Optional[datetime] = None

    # Coverage metrics
    storage_document_count: Optional[int] = None  # Count from StorageBackend

    # Extra backend-specific stats
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def coverage_percent(self) -> Optional[float]:
        """Calculate index coverage vs storage."""
        if self.storage_document_count is None or self.storage_document_count == 0:
            return None
        return (self.document_count / self.storage_document_count) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "corpus_type": self.corpus_type,
            "document_count": self.document_count,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "last_indexed": (
                self.last_indexed.isoformat() if self.last_indexed else None
            ),
            "storage_document_count": self.storage_document_count,
            "coverage_percent": self.coverage_percent,
            "metadata": self.metadata,
        }


@dataclass
class VectorValidationResult:
    """
    Result of vector backend validation.

    Preflight check for vector DB connectivity and index health.
    """

    is_valid: bool  # All checks passed
    connected: bool  # Can connect to vector database
    index_exists: bool  # Collection/index exists

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    check_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "connected": self.connected,
            "index_exists": self.index_exists,
            "errors": self.errors,
            "warnings": self.warnings,
            "check_duration_ms": self.check_duration_ms,
        }


@runtime_checkable
class VectorBackend(Protocol):
    """
    Protocol for vector search backend (ChromaDB, pgvector).

    Handles embedding generation and similarity search. Key design:
    - Reads from StorageBackend, not from memory
    - Enables re-indexing without re-fetching from source
    - Supports multiple corpus types per jurisdiction

    Implementations:
    - ChromaDBBackend: Local ChromaDB for development
    - PgVectorBackend: pgvector extension for production

    Usage:
        storage = SQLiteBackend("civic.db")
        vector = ChromaDBBackend("./chroma_db")

        # Validate before use
        result = vector.validate()
        if not result.is_valid:
            raise RuntimeError(result.errors)

        # Index from storage (not memory!)
        count = vector.index_from_storage(
            storage_backend=storage,
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings"
        )

        # Search
        results = vector.search(
            query="housing development",
            jurisdiction_id="city-san-rafael",
            corpus_type="meetings",
            top_k=5
        )

        # Inspect embedding configuration
        print(f"Model: {vector.embedding_model}")
        print(f"Dimensions: {vector.embedding_dimension}")
    """

    @property
    def backend_type(self) -> str:
        """Type identifier: 'chromadb', 'pgvector'."""
        ...

    @property
    def embedding_model(self) -> str:
        """
        Embedding model identifier.

        Returns the model name used for generating embeddings.
        Examples: 'nomic-ai/nomic-embed-text-v1.5', 'text-embedding-3-small'
        """
        ...

    @property
    def embedding_dimension(self) -> int:
        """
        Embedding vector dimension.

        Returns the dimension of embedding vectors produced by the model.
        Used for validation and schema creation in vector stores.
        """
        ...

    def validate(self) -> VectorValidationResult:
        """
        Validate vector backend connectivity.

        Preflight check that fails fast with clear error messages for:
        - Vector DB connectivity issues
        - Missing indices/collections
        - Embedding model issues

        Returns:
            VectorValidationResult with is_valid, errors, warnings
        """
        ...

    def index_from_storage(
        self,
        storage_backend: StorageBackend,
        jurisdiction_id: str,
        corpus_type: str = "meetings",
        batch_size: int = 100,
    ) -> int:
        """
        Build vector index from StorageBackend.

        Reads documents from storage, generates embeddings, and indexes.
        This is the key method that connects store -> index stages.

        Args:
            storage_backend: Source of documents to index
            jurisdiction_id: Target jurisdiction
            corpus_type: Type of documents ("meetings", "agenda_items")
            batch_size: Number of documents to process at once

        Returns:
            Number of documents successfully indexed

        Raises:
            VectorError: If indexing fails
        """
        ...

    def search(
        self,
        query: str,
        jurisdiction_id: str,
        corpus_type: str = "meetings",
        top_k: int = 5,
        min_score: Optional[float] = None,
    ) -> List[SearchResult]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            jurisdiction_id: Target jurisdiction
            corpus_type: Type of documents to search
            top_k: Maximum number of results
            min_score: Minimum similarity score threshold

        Returns:
            List of SearchResult ordered by similarity score
        """
        ...

    def get_stats(
        self,
        jurisdiction_id: str,
        corpus_type: str = "meetings",
        storage_backend: Optional[StorageBackend] = None,
    ) -> VectorStats:
        """
        Get vector index statistics.

        If storage_backend provided, includes coverage metrics.

        Args:
            jurisdiction_id: Target jurisdiction
            corpus_type: Type of documents
            storage_backend: Optional, for coverage calculation

        Returns:
            VectorStats with counts and coverage info
        """
        ...

    def delete_index(
        self,
        jurisdiction_id: str,
        corpus_type: Optional[str] = None,
    ) -> int:
        """
        Delete vector index.

        If corpus_type is None, deletes all indices for jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction
            corpus_type: Specific corpus to delete (None = all)

        Returns:
            Number of documents deleted from index
        """
        ...
