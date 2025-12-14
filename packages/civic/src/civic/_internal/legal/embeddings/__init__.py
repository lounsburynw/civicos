"""
Embeddings layer for legal document vectors.

Provides:
- LegalChunker: Document splitting aware of legal structure
- VectorStore: ChromaDB interface for storage
- LegalIndexer: Build and update the vector index

Requires: pip install civic-legal[embeddings]
"""

try:
    import chromadb
    import openai
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

if DEPS_AVAILABLE:
    from civic._internal.legal.embeddings.chunker import LegalChunker
    from civic._internal.legal.embeddings.store import VectorStore
    from civic._internal.legal.embeddings.indexer import LegalIndexer

    __all__ = ["LegalChunker", "VectorStore", "LegalIndexer"]
else:
    __all__ = []

    def _raise_import_error(*args, **kwargs):
        raise ImportError(
            "Embeddings dependencies not installed. "
            "Install with: pip install civic-legal[embeddings]"
        )

    LegalChunker = _raise_import_error
    VectorStore = _raise_import_error
    LegalIndexer = _raise_import_error
