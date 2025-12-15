"""
High-level legal document search.

Combines vector search with optional reranking for best results.

Usage:
    # Default: uses local SentenceTransformer embeddings
    search = LegalSearch("./data/vectors/legal")

    # With custom embedding provider
    from civic._internal.embeddings import get_embedding_provider
    provider = get_embedding_provider("openai")
    search = LegalSearch("./data/vectors/legal", provider=provider)
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from civic._internal.legal.embeddings.store import VectorStore, SearchResult

if TYPE_CHECKING:
    from civic._internal.embeddings.provider import EmbeddingProvider


@dataclass
class LegalSearchResult:
    """Enhanced search result with relevance info."""
    bill_id: str
    section: str
    text: str
    relevance_score: float
    metadata: dict


class LegalSearch:
    """
    High-level interface for searching legal documents.

    Combines:
    - Vector similarity search (fast recall)
    - Optional reranking (improved precision)
    - Metadata filtering

    Usage:
        search = LegalSearch("./data/vectors/legal")
        results = search.query(
            "wildfire prevention funding programs",
            top_k=10,
            filter={"session": "2023-2024"},
        )
    """

    def __init__(
        self,
        persist_directory: str = "./data/vectors/legal",
        provider: Optional["EmbeddingProvider"] = None,
        use_reranker: bool = False,
    ):
        """
        Initialize search.

        Args:
            persist_directory: Path to vector store
            provider: EmbeddingProvider instance. Defaults to local SentenceTransformer.
            use_reranker: Enable cross-encoder reranking
        """
        self.store = VectorStore(
            persist_directory=persist_directory,
            provider=provider,
        )
        self.use_reranker = use_reranker
        self._reranker = None

        if use_reranker:
            from civic._internal.legal.retrieval.reranker import Reranker
            self._reranker = Reranker()

    def query(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[dict] = None,
        rerank_top_k: Optional[int] = None,
    ) -> list[LegalSearchResult]:
        """
        Search for relevant legal documents.

        Args:
            query: Natural language search query
            top_k: Number of results to return
            filter: Metadata filter (e.g., {"session": "2023-2024"})
            rerank_top_k: If set, retrieve this many then rerank to top_k

        Returns:
            List of LegalSearchResult objects
        """
        # Determine retrieval count
        retrieve_k = rerank_top_k if rerank_top_k else top_k

        # Vector search
        raw_results = self.store.search(
            query=query,
            top_k=retrieve_k,
            filter=filter,
        )

        # Optional reranking
        if self._reranker and rerank_top_k:
            raw_results = self._reranker.rerank(query, raw_results, top_k)

        # Convert to LegalSearchResult
        results = []
        for r in raw_results[:top_k]:
            results.append(LegalSearchResult(
                bill_id=r.metadata.get("bill_id", "unknown"),
                section=r.metadata.get("section", "unknown"),
                text=r.text,
                relevance_score=r.score,
                metadata=r.metadata,
            ))

        return results

    def find_related_bills(
        self,
        bill_id: str,
        top_k: int = 5,
    ) -> list[LegalSearchResult]:
        """
        Find bills related to a given bill.

        Args:
            bill_id: Bill identifier (e.g., "AB-1234")
            top_k: Number of related bills

        Returns:
            Related bills
        """
        # Get the bill's text
        results = self.store.search(
            query="",  # Empty - we'll use filter
            top_k=1,
            filter={"bill_id": bill_id},
        )

        if not results:
            return []

        # Search for similar using the bill's text
        return self.query(
            query=results[0].text[:500],  # Use first 500 chars
            top_k=top_k + 1,
            filter={"bill_id": {"$ne": bill_id}},  # Exclude the bill itself
        )[:top_k]

    def search_by_topic(
        self,
        topic: str,
        session: Optional[str] = None,
        top_k: int = 10,
    ) -> list[LegalSearchResult]:
        """
        Search by topic area.

        Args:
            topic: Topic area (housing, transportation, environment, etc.)
            session: Optional session filter
            top_k: Number of results

        Returns:
            Relevant results
        """
        filter_dict = {}
        if session:
            filter_dict["session"] = session

        # Use topic-specific query
        topic_queries = {
            "housing": "housing affordability zoning development residential",
            "transportation": "transit roads highways public transportation",
            "environment": "climate emissions pollution environmental protection",
            "budget": "appropriations funding allocation budget",
            "education": "schools education students teachers",
        }

        query = topic_queries.get(topic.lower(), topic)

        return self.query(
            query=query,
            top_k=top_k,
            filter=filter_dict if filter_dict else None,
        )
