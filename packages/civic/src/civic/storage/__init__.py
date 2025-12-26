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

import os
from typing import Optional

from .backend import (
    StorageBackend,
    StorageStats,
    StorageValidationResult,
)
from .pgvector_backend import PgVectorBackend
from .postgres_backend import PostgresBackend
from .sqlite_backend import SQLiteBackend
from .vector import (
    SearchResult,
    VectorBackend,
    VectorStats,
    VectorValidationResult,
)


def get_storage_backend(url: Optional[str] = None) -> StorageBackend:
    """
    Factory function to get the appropriate storage backend.

    Selects backend based on DATABASE_URL format:
    - postgresql://... -> PostgresBackend
    - sqlite:///...    -> SQLiteBackend
    - (default)        -> SQLiteBackend with get_state_db_path()

    Args:
        url: Database URL. If not provided, uses DATABASE_URL environment
             variable. If neither is set, defaults to SQLite.

    Returns:
        StorageBackend instance (SQLiteBackend or PostgresBackend)

    Examples:
        # Use environment variable
        backend = get_storage_backend()

        # Explicit SQLite
        backend = get_storage_backend("sqlite:///data/civic.db")

        # Explicit Postgres
        backend = get_storage_backend("postgresql://user:pass@host:5432/civic")
    """
    url = url or os.getenv("DATABASE_URL")

    if url is None:
        # Default to SQLite with standard path
        return SQLiteBackend()

    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return PostgresBackend(url)

    if url.startswith("sqlite:///"):
        # Extract path from sqlite:/// URL
        db_path = url.replace("sqlite:///", "")
        return SQLiteBackend(db_path)

    # Fallback: treat as SQLite path
    return SQLiteBackend(url)

__all__ = [
    # Storage backend
    "StorageBackend",
    "StorageStats",
    "StorageValidationResult",
    # Factory function
    "get_storage_backend",
    # SQLite implementation
    "SQLiteBackend",
    # PostgreSQL implementation
    "PostgresBackend",
    # Vector backend
    "VectorBackend",
    "VectorStats",
    "VectorValidationResult",
    "SearchResult",
    # pgvector implementation (stub)
    "PgVectorBackend",
]
