"""
Embedding provider abstraction for Civic.

Provides a unified interface for generating embeddings, supporting both
local (SentenceTransformer) and API-based (OpenAI) providers.

Usage:
    from civicos._internal.embeddings import get_embedding_provider

    # Uses CIVICOS_EMBEDDING_PROVIDER env var (default: 'local')
    provider = get_embedding_provider()
    embeddings = provider.encode(["text1", "text2"])

Configuration:
    CIVICOS_EMBEDDING_PROVIDER: 'local' (SentenceTransformer) or 'openai'
    CIVICOS_EMBEDDING_MODEL: Model name (defaults per provider)
    OPENAI_API_KEY: Required if using 'openai' provider
"""

from .provider import (
    EmbeddingProvider,
    SentenceTransformerProvider,
    FastEmbedProvider,
    OpenAIProvider,
    get_embedding_provider,
)

__all__ = [
    "EmbeddingProvider",
    "SentenceTransformerProvider",
    "FastEmbedProvider",
    "OpenAIProvider",
    "get_embedding_provider",
]
