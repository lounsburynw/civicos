"""
Storage protocols for the Civic platform.

Defines interfaces for the 4-stage extraction pipeline:
    discover -> ingest -> store -> index

StorageBackend: Primary data persistence (SQLite, Postgres)
VectorBackend: Semantic search indexing (ChromaDB, pgvector)

Key design principle: Index reads from StorageBackend, not memory.
This ensures data is persisted before indexing and allows re-indexing
without re-fetching from the data source.

Usage:
    from civic.storage import (
        StorageBackend,
        VectorBackend,
        StorageStats,
        VectorStats,
        SearchResult,
    )

    # Define implementations
    class SQLiteBackend:
        '''SQLite implementation of StorageBackend.'''
        ...

    class ChromaDBBackend:
        '''ChromaDB implementation of VectorBackend.'''
        ...

    # Use in pipeline
    storage = SQLiteBackend("civic.db")
    vector = ChromaDBBackend("./chroma_db")

    # Store ingested meetings
    storage.store_meetings("city-san-rafael", meetings)

    # Index from storage (not memory!)
    vector.index_from_storage(storage, "city-san-rafael", "meetings")

    # Search
    results = vector.search("housing", "city-san-rafael")
"""

from .backend import (
    StorageBackend,
    StorageStats,
    StorageValidationResult,
)
from .vector import (
    SearchResult,
    VectorBackend,
    VectorStats,
    VectorValidationResult,
)

__all__ = [
    # Storage backend
    "StorageBackend",
    "StorageStats",
    "StorageValidationResult",
    # Vector backend
    "VectorBackend",
    "VectorStats",
    "VectorValidationResult",
    "SearchResult",
]
