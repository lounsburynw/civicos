"""
Abstract embedding provider interface for Civic.

Provides a unified interface for generating embeddings, supporting both
local (SentenceTransformer) and API-based (OpenAI) providers. The interface
is designed to be extensible for additional providers (Cohere, Google, etc.).

Usage:
    from civic._internal.embeddings import get_embedding_provider

    # Uses CIVIC_EMBEDDING_PROVIDER env var (default: 'local')
    provider = get_embedding_provider()
    embeddings = provider.encode(["text1", "text2"])

Configuration:
    CIVIC_EMBEDDING_PROVIDER: 'local' (SentenceTransformer) or 'openai'
    CIVIC_EMBEDDING_MODEL: Model name (defaults per provider)
    OPENAI_API_KEY: Required if using 'openai' provider
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Union
import os

import numpy as np


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.

    All providers must implement encode() and expose embedding_dimension.
    This enables unified vector operations regardless of underlying model.

    Implementations exist for:
    - SentenceTransformerProvider: Local models, no API costs
    - OpenAIProvider: API-based, higher quality embeddings

    The interface is designed to support future providers:
    - Cohere (embed-english-v3.0)
    - Google Vertex AI (text-embedding-004)
    - Ollama (nomic-embed-text)
    - AWS Bedrock (Titan Embeddings)
    """

    @abstractmethod
    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 100,
    ) -> np.ndarray:
        """
        Encode text(s) into embeddings.

        Args:
            texts: Single text string or list of text strings to encode
            batch_size: Number of texts to process per batch (for efficiency)

        Returns:
            numpy array of shape (n_texts, embedding_dimension)
            For single text input, returns shape (1, embedding_dimension)
        """
        ...

    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Return the embedding dimension for this provider."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name being used."""
        ...


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Local embedding provider using SentenceTransformer.

    No API costs, runs entirely locally. Good balance of quality and speed.
    Default model: all-MiniLM-L6-v2 (384 dimensions)

    Usage:
        provider = SentenceTransformerProvider()
        embeddings = provider.encode(["hello world", "goodbye world"])
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize SentenceTransformer provider.

        Args:
            model_name: SentenceTransformer model name.
                       Defaults to CIVIC_EMBEDDING_MODEL env var or 'all-MiniLM-L6-v2'
        """
        try:
            from sentence_transformers import SentenceTransformer
            self._st_available = True
        except ImportError:
            self._st_available = False

        self._model_name = model_name or os.environ.get(
            "CIVIC_EMBEDDING_MODEL", self.DEFAULT_MODEL
        )

        # Lazy load model
        self._model = None
        self._dimension: Optional[int] = None

    def _ensure_available(self):
        """Check that sentence-transformers is available."""
        if not self._st_available:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install with: pip install sentence-transformers"
            )

    @property
    def _sentence_transformer(self):
        """Lazy-load the SentenceTransformer model."""
        self._ensure_available()
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 100,
    ) -> np.ndarray:
        """
        Encode texts using SentenceTransformer.

        Args:
            texts: Text or list of texts to encode
            batch_size: Batch size for encoding (default 100)

        Returns:
            numpy array of embeddings, shape (n_texts, 384) for default model
        """
        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]

        # SentenceTransformer handles batching internally
        embeddings = self._sentence_transformer.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        return embeddings

    @property
    def embedding_dimension(self) -> int:
        """Return embedding dimension (384 for default model)."""
        if self._dimension is None:
            # Force model load to get dimension
            _ = self._sentence_transformer
        return self._dimension

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name


class FastEmbedProvider(EmbeddingProvider):
    """
    Lightweight embedding provider using FastEmbed (ONNX-based).

    No PyTorch dependency, uses ONNX Runtime instead. Significantly smaller
    footprint (~500MB vs ~3GB for sentence-transformers/PyTorch).
    Default model: BAAI/bge-small-en-v1.5 (384 dimensions)

    Usage:
        provider = FastEmbedProvider()
        embeddings = provider.encode(["hello world", "goodbye world"])
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    # Dimension by model
    MODEL_DIMENSIONS = {
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-large-en-v1.5": 1024,
        "sentence-transformers/all-MiniLM-L6-v2": 384,
    }

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize FastEmbed provider.

        Args:
            model_name: FastEmbed model name.
                       Defaults to CIVIC_EMBEDDING_MODEL env var or 'BAAI/bge-small-en-v1.5'
        """
        try:
            from fastembed import TextEmbedding
            self._fastembed_available = True
        except ImportError:
            self._fastembed_available = False

        self._model_name = model_name or os.environ.get(
            "CIVIC_EMBEDDING_MODEL", self.DEFAULT_MODEL
        )

        # Lazy load model
        self._model = None

    def _ensure_available(self):
        """Check that fastembed is available."""
        if not self._fastembed_available:
            raise ImportError(
                "fastembed is required for FastEmbed embeddings. "
                "Install with: pip install fastembed"
            )

    @property
    def _text_embedding(self):
        """Lazy-load the TextEmbedding model."""
        self._ensure_available()
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 100,
    ) -> np.ndarray:
        """
        Encode texts using FastEmbed.

        Args:
            texts: Text or list of texts to encode
            batch_size: Batch size for encoding (default 100)

        Returns:
            numpy array of embeddings, shape (n_texts, 384) for default model
        """
        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]

        # FastEmbed returns a generator, convert to list then array
        embeddings_gen = self._text_embedding.embed(texts, batch_size=batch_size)
        embeddings_list = list(embeddings_gen)

        return np.array(embeddings_list)

    @property
    def embedding_dimension(self) -> int:
        """Return embedding dimension (384 for default model)."""
        return self.MODEL_DIMENSIONS.get(self._model_name, 384)

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name


class OpenAIProvider(EmbeddingProvider):
    """
    API-based embedding provider using OpenAI.

    Higher quality embeddings but requires API key and has per-token costs.
    Default model: text-embedding-3-small (1536 dimensions)

    Usage:
        provider = OpenAIProvider(api_key="sk-...")
        embeddings = provider.encode(["hello world", "goodbye world"])
    """

    DEFAULT_MODEL = "text-embedding-3-small"
    # Dimension by model
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize OpenAI embedding provider.

        Args:
            model_name: OpenAI embedding model name.
                       Defaults to CIVIC_EMBEDDING_MODEL env var or 'text-embedding-3-small'
            api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
        """
        try:
            import openai
            self._openai_available = True
        except ImportError:
            self._openai_available = False

        self._model_name = model_name or os.environ.get(
            "CIVIC_EMBEDDING_MODEL", self.DEFAULT_MODEL
        )

        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

        # Lazy init client
        self._client = None

    def _ensure_available(self):
        """Check that openai is available and configured."""
        if not self._openai_available:
            raise ImportError(
                "openai is required for OpenAI embeddings. "
                "Install with: pip install openai"
            )
        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key."
            )

    @property
    def _openai_client(self):
        """Lazy-load the OpenAI client."""
        self._ensure_available()
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 100,
    ) -> np.ndarray:
        """
        Encode texts using OpenAI API.

        Args:
            texts: Text or list of texts to encode
            batch_size: Batch size for API calls (default 100)

        Returns:
            numpy array of embeddings, shape (n_texts, 1536) for default model
        """
        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            response = self._openai_client.embeddings.create(
                model=self._model_name,
                input=batch,
            )

            # Extract embeddings in order
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)

        return np.array(all_embeddings)

    @property
    def embedding_dimension(self) -> int:
        """Return embedding dimension (1536 for default model)."""
        return self.MODEL_DIMENSIONS.get(self._model_name, 1536)

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name


def get_embedding_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    **kwargs,
) -> EmbeddingProvider:
    """
    Factory function to get the configured embedding provider.

    Args:
        provider_type: Provider to use:
                      - 'fastembed': FastEmbed (ONNX-based, lightweight, recommended for production)
                      - 'local': SentenceTransformer (PyTorch-based, larger footprint)
                      - 'openai': OpenAI API (requires API key, has per-token costs)
                      Defaults to CIVIC_EMBEDDING_PROVIDER env var or 'fastembed'.
        model_name: Model name override. Defaults to CIVIC_EMBEDDING_MODEL env var.
        **kwargs: Additional arguments passed to the provider constructor.

    Returns:
        EmbeddingProvider instance

    Examples:
        # Use default (FastEmbed, lightweight ONNX-based)
        provider = get_embedding_provider()

        # Explicitly use OpenAI
        provider = get_embedding_provider('openai')

        # Use SentenceTransformer (larger, requires PyTorch)
        provider = get_embedding_provider('local', model_name='all-mpnet-base-v2')
    """
    provider_type = provider_type or os.environ.get(
        "CIVIC_EMBEDDING_PROVIDER", "fastembed"
    )

    if provider_type.lower() == "fastembed":
        return FastEmbedProvider(model_name=model_name, **kwargs)
    elif provider_type.lower() == "local":
        return SentenceTransformerProvider(model_name=model_name, **kwargs)
    elif provider_type.lower() == "openai":
        return OpenAIProvider(model_name=model_name, **kwargs)
    else:
        raise ValueError(
            f"Unknown embedding provider: {provider_type}. "
            "Use 'fastembed', 'local' (SentenceTransformer), or 'openai'."
        )
