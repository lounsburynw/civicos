"""
Vector store interface for legal documents.

Uses ChromaDB for local vector storage with configurable embedding providers.
Supports both local (SentenceTransformer) and API-based (OpenAI) embeddings.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None

if TYPE_CHECKING:
    from civicos._internal.embeddings.provider import EmbeddingProvider


@dataclass
class SearchResult:
    """A search result from the vector store."""
    document_id: str
    text: str
    score: float
    metadata: dict


class VectorStore:
    """
    ChromaDB-backed vector store for legal documents.

    Features:
    - Persistent storage to disk
    - Configurable embedding provider (local or OpenAI)
    - Metadata filtering
    - Batch operations
    - Dimension validation

    Usage:
        # Default: uses local SentenceTransformer embeddings
        store = VectorStore("./data/vectors/legal")

        # With explicit provider
        from civicos._internal.embeddings import get_embedding_provider
        provider = get_embedding_provider("openai")
        store = VectorStore("./data/vectors/legal", provider=provider)

        store.add_documents([...])
        results = store.search("wildfire prevention", top_k=5)
    """

    COLLECTION_NAME = "legal_documents"

    def __init__(
        self,
        persist_directory: str = "./data/vectors/legal",
        provider: Optional["EmbeddingProvider"] = None,
    ):
        """
        Initialize vector store.

        Args:
            persist_directory: Path to store ChromaDB data
            provider: EmbeddingProvider instance. Defaults to local SentenceTransformer.
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is required. Install with: pip install civicos-legal[embeddings]"
            )

        self.persist_directory = persist_directory

        # Initialize embedding provider (default: local SentenceTransformer)
        if provider is None:
            from civicos._internal.embeddings.provider import get_embedding_provider
            provider = get_embedding_provider()
        self.provider = provider

        # Initialize ChromaDB
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create collection with embedding metadata
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.provider.model_name,
                "embedding_dimension": self.provider.embedding_dimension,
            },
        )

        # Validate dimension compatibility with existing collection
        self._validate_dimension()

    def add_documents(
        self,
        documents: list[dict],
        batch_size: int = 100,
    ) -> int:
        """
        Add documents to the store.

        Args:
            documents: List of dicts with 'id', 'text', and optional 'metadata'
            batch_size: Number of documents per batch

        Returns:
            Number of documents added
        """
        added = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]

            ids = [d["id"] for d in batch]
            texts = [d["text"] for d in batch]
            # ChromaDB requires non-empty metadata dicts
            metadatas = [d.get("metadata") or {"_placeholder": True} for d in batch]

            # Get embeddings from OpenAI
            embeddings = self._embed_texts(texts)

            # Add to ChromaDB
            self._collection.add(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            added += len(batch)

        return added

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[dict] = None,
    ) -> list[SearchResult]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            top_k: Number of results to return
            filter: Optional metadata filter

        Returns:
            List of SearchResult objects
        """
        # Get query embedding
        query_embedding = self._embed_texts([query])[0]

        # Search
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter,
        )

        # Convert to SearchResult objects
        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                search_results.append(SearchResult(
                    document_id=doc_id,
                    text=results["documents"][0][i] if results["documents"] else "",
                    score=1 - results["distances"][0][i] if results["distances"] else 0,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                ))

        return search_results

    def delete(self, ids: list[str]) -> int:
        """Delete documents by ID."""
        self._collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        """Get total document count."""
        return self._collection.count()

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for a list of texts using the configured provider."""
        embeddings = self.provider.encode(texts)
        return embeddings.tolist()

    def _validate_dimension(self) -> None:
        """
        Validate that the provider's embedding dimension matches the collection.

        Raises:
            ValueError: If dimensions are incompatible
        """
        # Only validate if collection has documents
        if self._collection.count() == 0:
            return

        collection_meta = self._collection.metadata or {}
        stored_dimension = collection_meta.get("embedding_dimension")

        if stored_dimension is not None:
            if stored_dimension != self.provider.embedding_dimension:
                raise ValueError(
                    f"Embedding dimension mismatch: provider uses {self.provider.embedding_dimension} "
                    f"dimensions but collection was created with {stored_dimension} dimensions. "
                    f"Use a provider with matching dimensions or rebuild the index."
                )
