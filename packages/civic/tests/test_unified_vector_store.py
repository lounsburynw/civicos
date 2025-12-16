"""
Tests for the unified VectorStore with configurable EmbeddingProvider.

Validates that VectorStore works correctly with any EmbeddingProvider implementation,
including dimension validation and proper integration.

Run: pytest packages/civic/tests/test_unified_vector_store.py -v
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import numpy as np

# Mark all tests in this module as integration + rag
pytestmark = [pytest.mark.integration, pytest.mark.rag]

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add source path for imports
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic/src"))

from civic._internal.embeddings import (
    SentenceTransformerProvider,
    FastEmbedProvider,
    OpenAIProvider,
    get_embedding_provider,
)
from civic._internal.legal.embeddings.store import VectorStore, SearchResult


@pytest.fixture
def temp_store_dir():
    """Create a temporary directory for the vector store."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def local_provider():
    """Create a local SentenceTransformer provider."""
    return SentenceTransformerProvider()


@pytest.fixture
def mock_openai_provider():
    """Create a mocked OpenAI provider."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        provider = OpenAIProvider()

        # Mock the OpenAI client
        mock_client = Mock()

        def mock_embeddings_create(model, input):
            response = Mock()
            if isinstance(input, str):
                input = [input]
            response.data = [Mock(embedding=[0.1] * 1536) for _ in input]
            return response

        mock_client.embeddings.create.side_effect = mock_embeddings_create
        provider._client = mock_client

        yield provider


class TestVectorStoreWithLocalProvider:
    """Tests for VectorStore with local SentenceTransformer provider."""

    def test_create_store_with_default_provider(self, temp_store_dir):
        """VectorStore uses FastEmbed provider by default."""
        store = VectorStore(persist_directory=temp_store_dir)

        assert store.provider is not None
        assert isinstance(store.provider, FastEmbedProvider)
        assert store.provider.embedding_dimension == 768

    def test_create_store_with_explicit_provider(self, temp_store_dir, local_provider):
        """VectorStore accepts explicit provider."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        assert store.provider is local_provider
        assert store.provider.embedding_dimension == 768

    def test_add_and_search_documents(self, temp_store_dir, local_provider):
        """Store can add documents and search them."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        documents = [
            {"id": "doc1", "text": "Housing affordability crisis in California", "metadata": {"topic": "housing"}},
            {"id": "doc2", "text": "Public transportation funding proposal", "metadata": {"topic": "transit"}},
            {"id": "doc3", "text": "Affordable housing development guidelines", "metadata": {"topic": "housing"}},
        ]

        added = store.add_documents(documents)
        assert added == 3
        assert store.count() == 3

        # Search for housing-related documents
        results = store.search("housing affordability", top_k=2)

        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        # Housing docs should rank higher than transit
        assert results[0].metadata.get("topic") == "housing"

    def test_search_with_filter(self, temp_store_dir, local_provider):
        """Store supports metadata filtering."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        documents = [
            {"id": "doc1", "text": "Housing in session 2023", "metadata": {"session": "2023"}},
            {"id": "doc2", "text": "Housing in session 2024", "metadata": {"session": "2024"}},
        ]

        store.add_documents(documents)

        # Filter to only 2024 session
        results = store.search("housing", top_k=5, filter={"session": "2024"})

        assert len(results) == 1
        assert results[0].metadata["session"] == "2024"

    def test_delete_documents(self, temp_store_dir, local_provider):
        """Store can delete documents."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        documents = [
            {"id": "doc1", "text": "First document"},
            {"id": "doc2", "text": "Second document"},
        ]

        store.add_documents(documents)
        assert store.count() == 2

        store.delete(["doc1"])
        assert store.count() == 1

    def test_collection_metadata_includes_embedding_info(self, temp_store_dir, local_provider):
        """Collection metadata tracks embedding model and dimension."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        metadata = store._collection.metadata

        assert metadata.get("embedding_model") == local_provider.model_name
        assert metadata.get("embedding_dimension") == local_provider.embedding_dimension
        assert metadata.get("hnsw:space") == "cosine"


class TestVectorStoreWithOpenAIProvider:
    """Tests for VectorStore with mocked OpenAI provider."""

    def test_create_store_with_openai_provider(self, temp_store_dir, mock_openai_provider):
        """VectorStore works with OpenAI provider."""
        store = VectorStore(persist_directory=temp_store_dir, provider=mock_openai_provider)

        assert store.provider is mock_openai_provider
        assert store.provider.embedding_dimension == 1536

    def test_add_and_search_with_openai(self, temp_store_dir, mock_openai_provider):
        """Store operations work with OpenAI provider."""
        store = VectorStore(persist_directory=temp_store_dir, provider=mock_openai_provider)

        documents = [
            {"id": "doc1", "text": "Test document one"},
            {"id": "doc2", "text": "Test document two"},
        ]

        added = store.add_documents(documents)
        assert added == 2

        results = store.search("test", top_k=2)
        assert len(results) == 2


class TestDimensionValidation:
    """Tests for embedding dimension validation."""

    def test_dimension_mismatch_raises_error(self, temp_store_dir, local_provider, mock_openai_provider):
        """Opening store with mismatched dimensions raises error."""
        # Create store with local provider (768 dims)
        store1 = VectorStore(persist_directory=temp_store_dir, provider=local_provider)
        store1.add_documents([{"id": "doc1", "text": "test"}])
        del store1

        # Try to open with OpenAI provider (1536 dims) - should fail
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            VectorStore(persist_directory=temp_store_dir, provider=mock_openai_provider)

    def test_same_dimension_provider_works(self, temp_store_dir, local_provider):
        """Opening store with matching dimensions works."""
        # Create store with local provider
        store1 = VectorStore(persist_directory=temp_store_dir, provider=local_provider)
        store1.add_documents([{"id": "doc1", "text": "test"}])
        del store1

        # Create new provider (same model)
        new_provider = SentenceTransformerProvider()

        # Should work - same dimensions
        store2 = VectorStore(persist_directory=temp_store_dir, provider=new_provider)
        assert store2.count() == 1

    def test_empty_collection_allows_any_provider(self, temp_store_dir, local_provider, mock_openai_provider):
        """Empty collections don't validate dimensions."""
        # Create empty store with local provider
        store1 = VectorStore(persist_directory=temp_store_dir, provider=local_provider)
        assert store1.count() == 0
        del store1

        # Can open with different provider since collection is empty
        # Note: ChromaDB stores metadata on collection creation, so this tests
        # that we handle the case where no documents exist yet
        store2 = VectorStore(persist_directory=temp_store_dir, provider=mock_openai_provider)
        # The validation should pass because there are no embeddings yet
        # (though metadata may differ)


class TestVectorStoreIntegration:
    """Integration tests for complete workflows."""

    def test_batch_processing(self, temp_store_dir, local_provider):
        """Store handles batch processing correctly."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        # Create 150 documents (more than default batch size of 100)
        documents = [
            {"id": f"doc{i}", "text": f"Document number {i} about civic engagement"}
            for i in range(150)
        ]

        added = store.add_documents(documents, batch_size=50)
        assert added == 150
        assert store.count() == 150

    def test_persistence_across_instances(self, temp_store_dir, local_provider):
        """Store data persists across instances."""
        # Add documents in first instance
        store1 = VectorStore(persist_directory=temp_store_dir, provider=local_provider)
        store1.add_documents([
            {"id": "doc1", "text": "Persistent document"},
        ])
        del store1

        # Verify in second instance
        store2 = VectorStore(persist_directory=temp_store_dir, provider=local_provider)
        assert store2.count() == 1

        results = store2.search("persistent")
        assert len(results) == 1
        assert results[0].document_id == "doc1"

    def test_semantic_search_quality(self, temp_store_dir, local_provider):
        """Semantic search returns relevant results."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        documents = [
            {"id": "housing1", "text": "New affordable housing development approved by city council"},
            {"id": "transit1", "text": "Bus route expansion to serve downtown area"},
            {"id": "housing2", "text": "Zoning changes to allow more residential units"},
            {"id": "env1", "text": "Solar panel installation incentive program"},
            {"id": "housing3", "text": "Rent control measures under consideration"},
        ]

        store.add_documents(documents)

        # Search for housing-related content
        results = store.search("affordable housing policy", top_k=3)

        # All top 3 should be housing-related
        housing_ids = {"housing1", "housing2", "housing3"}
        result_ids = {r.document_id for r in results}

        assert len(result_ids & housing_ids) >= 2, (
            f"Expected at least 2 housing docs in top 3, got: {result_ids}"
        )

    def test_score_range(self, temp_store_dir, local_provider):
        """Search scores are in expected range [0, 1]."""
        store = VectorStore(persist_directory=temp_store_dir, provider=local_provider)

        documents = [
            {"id": "doc1", "text": "Housing affordability is important"},
            {"id": "doc2", "text": "Something completely different about weather"},
        ]

        store.add_documents(documents)

        results = store.search("housing affordability", top_k=2)

        for result in results:
            assert 0.0 <= result.score <= 1.0, f"Score {result.score} out of range"


class TestLegalIndexerAndSearchIntegration:
    """Tests that LegalIndexer and LegalSearch work with unified VectorStore."""

    def test_legal_indexer_accepts_provider(self, temp_store_dir, local_provider):
        """LegalIndexer accepts provider parameter."""
        from civic._internal.legal.embeddings.indexer import LegalIndexer

        indexer = LegalIndexer(
            persist_directory=temp_store_dir,
            provider=local_provider,
        )

        assert indexer.store.provider is local_provider

    def test_legal_search_accepts_provider(self, temp_store_dir, local_provider):
        """LegalSearch accepts provider parameter."""
        from civic._internal.legal.retrieval.search import LegalSearch

        search = LegalSearch(
            persist_directory=temp_store_dir,
            provider=local_provider,
        )

        assert search.store.provider is local_provider

    def test_indexer_and_search_share_provider_compatibility(self, temp_store_dir, local_provider):
        """Indexer and Search work together with same provider type."""
        from civic._internal.legal.embeddings.indexer import LegalIndexer
        from civic._internal.legal.retrieval.search import LegalSearch

        # Index with local provider
        indexer = LegalIndexer(
            persist_directory=temp_store_dir,
            provider=local_provider,
        )
        indexer.store.add_documents([
            {"id": "bill1", "text": "Housing affordability bill", "metadata": {"bill_id": "AB-123"}},
        ])
        del indexer

        # Search with new local provider instance
        new_provider = SentenceTransformerProvider()
        search = LegalSearch(
            persist_directory=temp_store_dir,
            provider=new_provider,
        )

        results = search.query("housing")
        assert len(results) == 1
        assert results[0].bill_id == "AB-123"
