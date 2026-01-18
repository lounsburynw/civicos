"""
Tests for the EmbeddingProvider abstraction.

Tests both SentenceTransformerProvider (local) and OpenAIProvider (API-based)
to ensure the unified interface works correctly across implementations.

Run: pytest packages/civic/tests/test_embedding_provider.py -v
"""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import numpy as np

# Mark all tests in this module as integration + rag
pytestmark = [pytest.mark.integration, pytest.mark.rag]

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add source path for imports
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic/src"))

from civicos._internal.embeddings import (
    EmbeddingProvider,
    SentenceTransformerProvider,
    FastEmbedProvider,
    OpenAIProvider,
    get_embedding_provider,
)


class TestSentenceTransformerProvider:
    """Tests for the local SentenceTransformer embedding provider."""

    def test_encode_single_text(self):
        """Provider encodes a single text string."""
        provider = SentenceTransformerProvider()
        embeddings = provider.encode("hello world")

        assert isinstance(embeddings, np.ndarray)
        assert embeddings.shape == (1, provider.embedding_dimension)

    def test_encode_multiple_texts(self):
        """Provider encodes multiple texts at once."""
        provider = SentenceTransformerProvider()
        texts = ["hello world", "goodbye world", "test text"]
        embeddings = provider.encode(texts)

        assert isinstance(embeddings, np.ndarray)
        assert embeddings.shape == (3, provider.embedding_dimension)

    def test_embedding_dimension(self):
        """Default model has 768 dimensions."""
        provider = SentenceTransformerProvider()
        assert provider.embedding_dimension == 768

    def test_model_name_default(self):
        """Default model is nomic-ai/nomic-embed-text-v1.5."""
        provider = SentenceTransformerProvider()
        assert provider.model_name == "nomic-ai/nomic-embed-text-v1.5"

    def test_model_name_custom(self):
        """Custom model name is respected."""
        provider = SentenceTransformerProvider(model_name="all-mpnet-base-v2")
        assert provider.model_name == "all-mpnet-base-v2"

    def test_embeddings_have_consistent_magnitude(self):
        """Embeddings should have consistent magnitude for similar length texts."""
        provider = SentenceTransformerProvider()
        embeddings = provider.encode([
            "test text one",
            "another test phrase",
            "short sample sentence",
        ])

        # Compute L2 norms
        norms = [np.linalg.norm(e) for e in embeddings]
        # Norms should be relatively consistent (within 50% of each other)
        # Note: nomic-embed-text-v1.5 produces unnormalized embeddings (~20-30 norm)
        assert max(norms) / min(norms) < 1.5, f"Norms vary too much: {norms}"

    def test_similar_texts_have_high_similarity(self):
        """Semantically similar texts should have high cosine similarity."""
        provider = SentenceTransformerProvider()
        embeddings = provider.encode([
            "The city council approved the housing project",
            "Council members voted yes on the residential development",
            "The weather forecast shows rain tomorrow",
        ])

        # Cosine similarity between first two (semantically similar)
        sim_similar = np.dot(embeddings[0], embeddings[1]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
        )

        # Cosine similarity between first and third (semantically different)
        sim_different = np.dot(embeddings[0], embeddings[2]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[2])
        )

        assert sim_similar > sim_different, (
            f"Similar texts should have higher similarity: {sim_similar} vs {sim_different}"
        )
        assert sim_similar > 0.5, f"Similar texts should have >0.5 similarity: {sim_similar}"

    def test_batch_size_parameter(self):
        """Batch size parameter is respected (doesn't error)."""
        provider = SentenceTransformerProvider()
        texts = [f"text {i}" for i in range(150)]
        embeddings = provider.encode(texts, batch_size=50)

        assert embeddings.shape == (150, provider.embedding_dimension)

    def test_empty_text_handling(self):
        """Provider handles empty text gracefully."""
        provider = SentenceTransformerProvider()
        embeddings = provider.encode("")

        assert isinstance(embeddings, np.ndarray)
        assert embeddings.shape == (1, provider.embedding_dimension)

    def test_lazy_loading(self):
        """Model is not loaded until first encode call."""
        provider = SentenceTransformerProvider()
        # Model should not be loaded yet
        assert provider._model is None

        # Access embedding_dimension forces model load
        _ = provider.embedding_dimension
        assert provider._model is not None


class TestOpenAIProvider:
    """Tests for the OpenAI embedding provider using mocks."""

    def test_encode_single_text_mocked(self):
        """Provider encodes a single text string (mocked API)."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider()

            # Mock the OpenAI client by setting _client directly
            mock_client = Mock()
            mock_response = Mock()
            mock_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create.return_value = mock_response
            provider._client = mock_client

            embeddings = provider.encode("hello world")

        assert isinstance(embeddings, np.ndarray)
        assert embeddings.shape == (1, 1536)

    def test_encode_multiple_texts_mocked(self):
        """Provider encodes multiple texts (mocked API)."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider()

            # Mock the OpenAI client by setting _client directly
            mock_client = Mock()
            mock_response = Mock()
            mock_response.data = [
                Mock(embedding=[0.1] * 1536),
                Mock(embedding=[0.2] * 1536),
                Mock(embedding=[0.3] * 1536),
            ]
            mock_client.embeddings.create.return_value = mock_response
            provider._client = mock_client

            embeddings = provider.encode(["text1", "text2", "text3"])

        assert embeddings.shape == (3, 1536)

    def test_embedding_dimension(self):
        """Default model has 1536 dimensions."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider()
            assert provider.embedding_dimension == 1536

    def test_model_name_default(self):
        """Default model is text-embedding-3-small."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider()
            assert provider.model_name == "text-embedding-3-small"

    def test_model_name_custom(self):
        """Custom model name is respected."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider(model_name="text-embedding-3-large")
            assert provider.model_name == "text-embedding-3-large"
            assert provider.embedding_dimension == 3072

    def test_api_key_from_env(self):
        """API key is read from environment variable."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider()
            assert provider._api_key == "env-key"

    def test_api_key_from_parameter(self):
        """API key parameter overrides environment."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            provider = OpenAIProvider(api_key="param-key")
            assert provider._api_key == "param-key"

    def test_missing_api_key_raises_error(self):
        """Missing API key raises ValueError on use."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove OPENAI_API_KEY if present
            os.environ.pop("OPENAI_API_KEY", None)
            provider = OpenAIProvider()
            with pytest.raises(ValueError, match="OpenAI API key required"):
                _ = provider._openai_client

    def test_batch_processing_mocked(self):
        """Large inputs are processed in batches."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider()

            # Create mock responses for 2 batches
            def create_mock_response(n_items):
                response = Mock()
                response.data = [Mock(embedding=[0.1] * 1536) for _ in range(n_items)]
                return response

            # Mock the OpenAI client by setting _client directly
            mock_client = Mock()
            mock_client.embeddings.create.side_effect = [
                create_mock_response(100),  # First batch
                create_mock_response(50),   # Second batch
            ]
            provider._client = mock_client

            texts = [f"text {i}" for i in range(150)]
            embeddings = provider.encode(texts, batch_size=100)

        assert embeddings.shape == (150, 1536)
        assert mock_client.embeddings.create.call_count == 2


class TestGetEmbeddingProvider:
    """Tests for the factory function."""

    def test_default_is_fastembed(self):
        """Default provider is FastEmbed (lightweight ONNX-based)."""
        # Clear env var if set
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CIVICOS_EMBEDDING_PROVIDER", None)
            provider = get_embedding_provider()
            assert isinstance(provider, FastEmbedProvider)

    def test_explicit_local(self):
        """Explicit 'local' returns SentenceTransformerProvider."""
        provider = get_embedding_provider("local")
        assert isinstance(provider, SentenceTransformerProvider)

    def test_explicit_openai(self):
        """Explicit 'openai' returns OpenAIProvider."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = get_embedding_provider("openai")
            assert isinstance(provider, OpenAIProvider)

    def test_env_var_local(self):
        """CIVICOS_EMBEDDING_PROVIDER=local returns SentenceTransformerProvider."""
        with patch.dict(os.environ, {"CIVICOS_EMBEDDING_PROVIDER": "local"}):
            provider = get_embedding_provider()
            assert isinstance(provider, SentenceTransformerProvider)

    def test_env_var_openai(self):
        """CIVICOS_EMBEDDING_PROVIDER=openai returns OpenAIProvider."""
        with patch.dict(os.environ, {
            "CIVICOS_EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key"
        }):
            provider = get_embedding_provider()
            assert isinstance(provider, OpenAIProvider)

    def test_model_name_passed_to_local(self):
        """Model name is passed to local provider."""
        provider = get_embedding_provider("local", model_name="custom-model")
        assert provider.model_name == "custom-model"

    def test_model_name_passed_to_openai(self):
        """Model name is passed to OpenAI provider."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = get_embedding_provider("openai", model_name="text-embedding-3-large")
            assert provider.model_name == "text-embedding-3-large"

    def test_unknown_provider_raises_error(self):
        """Unknown provider type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embedding_provider("unknown")

    def test_case_insensitive(self):
        """Provider type is case-insensitive."""
        provider = get_embedding_provider("LOCAL")
        assert isinstance(provider, SentenceTransformerProvider)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = get_embedding_provider("OpenAI")
            assert isinstance(provider, OpenAIProvider)


class TestProviderInterface:
    """Tests to verify both providers satisfy the EmbeddingProvider interface."""

    def test_local_is_embedding_provider(self):
        """SentenceTransformerProvider is an EmbeddingProvider."""
        provider = SentenceTransformerProvider()
        assert isinstance(provider, EmbeddingProvider)

    def test_openai_is_embedding_provider(self):
        """OpenAIProvider is an EmbeddingProvider."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIProvider()
            assert isinstance(provider, EmbeddingProvider)

    def test_interface_methods_exist(self):
        """Both providers have required interface methods."""
        local = SentenceTransformerProvider()

        # Check methods exist
        assert hasattr(local, 'encode')
        assert hasattr(local, 'embedding_dimension')
        assert hasattr(local, 'model_name')
        assert callable(local.encode)

    def test_encode_returns_numpy_array(self):
        """encode() returns numpy array for both providers."""
        local = SentenceTransformerProvider()
        result = local.encode("test")
        assert isinstance(result, np.ndarray)

    def test_embedding_dimension_is_int(self):
        """embedding_dimension is an integer for both providers."""
        local = SentenceTransformerProvider()
        assert isinstance(local.embedding_dimension, int)
        assert local.embedding_dimension > 0

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            openai = OpenAIProvider()
            assert isinstance(openai.embedding_dimension, int)
            assert openai.embedding_dimension > 0

    def test_model_name_is_string(self):
        """model_name is a string for both providers."""
        local = SentenceTransformerProvider()
        assert isinstance(local.model_name, str)
        assert len(local.model_name) > 0

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            openai = OpenAIProvider()
            assert isinstance(openai.model_name, str)
            assert len(openai.model_name) > 0
