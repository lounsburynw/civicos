"""
Embeddings layer for legal document vectors.

Provides:
- LegalChunker: Document splitting aware of legal structure
- VectorStore: ChromaDB interface for storage

Note: LegalIndexer was removed - legislation is now indexed via pgvector using
expand_legislation_to_chunks() + PgVectorBackend.index_from_storage().

Requires: pip install civicos-legal[embeddings]
"""

try:
    import chromadb
    import openai
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

if DEPS_AVAILABLE:
    from civicos._internal.legal.embeddings.chunker import LegalChunker
    from civicos._internal.legal.embeddings.store import VectorStore

    __all__ = ["LegalChunker", "VectorStore"]
else:
    __all__ = []

    def _raise_import_error(*args, **kwargs):
        raise ImportError(
            "Embeddings dependencies not installed. "
            "Install with: pip install civicos-legal[embeddings]"
        )

    LegalChunker = _raise_import_error
    VectorStore = _raise_import_error
