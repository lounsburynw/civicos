"""
Retrieval layer for legal document search.

Provides:
- LegalSearch: High-level search interface
- Reranker: Cross-encoder reranking for precision
- ContextBuilder: Build LLM context from search results

Requires: pip install civicos-legal[embeddings]
"""

try:
    from civicos._internal.legal.retrieval.search import LegalSearch
    from civicos._internal.legal.retrieval.reranker import Reranker
    from civicos._internal.legal.retrieval.context import ContextBuilder

    __all__ = ["LegalSearch", "Reranker", "ContextBuilder"]
except ImportError:
    __all__ = []

    def _raise_import_error(*args, **kwargs):
        raise ImportError(
            "Retrieval dependencies not installed. "
            "Install with: pip install civicos-legal[embeddings]"
        )

    LegalSearch = _raise_import_error
    Reranker = _raise_import_error
    ContextBuilder = _raise_import_error
