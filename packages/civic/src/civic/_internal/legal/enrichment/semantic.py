"""
Semantic enrichment using vector search.

Replaces keyword matching with true RAG for more accurate
legislative context discovery.

Requires: pip install civic-legal[embeddings]
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)

try:
    from civic._internal.legal.retrieval import LegalSearch, ContextBuilder
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False
    LegalSearch = None
    ContextBuilder = None


class SemanticEnricher:
    """
    Enriches civic opportunities using vector search over legislation.

    Instead of keyword matching, this uses:
    1. Vector similarity to find relevant bills
    2. LLM reranking for precision
    3. Context building for relevance summaries

    Usage:
        enricher = SemanticEnricher(persist_directory="./legal_index")
        context = enricher.enrich(opportunity)
    """

    def __init__(
        self,
        persist_directory: str = "./legal_index",
        openai_api_key: Optional[str] = None,
        top_k: int = 5,
        use_reranker: bool = False,
    ):
        """
        Initialize semantic enricher.

        Args:
            persist_directory: Path to vector store
            openai_api_key: OpenAI API key
            top_k: Number of results to retrieve
            use_reranker: Enable cross-encoder reranking
        """
        if not DEPS_AVAILABLE:
            raise ImportError(
                "Semantic enrichment requires embeddings. "
                "Install with: pip install civic-legal[embeddings]"
            )

        self.search = LegalSearch(
            persist_directory=persist_directory,
            openai_api_key=openai_api_key,
            use_reranker=use_reranker,
        )
        self.context_builder = ContextBuilder(max_tokens=1000)
        self.top_k = top_k

    def enrich(self, opportunity: dict) -> Optional[dict]:
        """
        Enrich a civic opportunity with legislative context.

        Args:
            opportunity: CivicEvent dict

        Returns:
            legislative_context dict or None
        """
        # Build search query from opportunity
        query = self._build_query(opportunity)
        if not query:
            return None

        # Search for relevant legislation
        results = self.search.query(
            query=query,
            top_k=self.top_k,
        )

        if not results:
            logger.debug(f"No relevant legislation found for: {query[:100]}")
            return None

        # Build context
        context = self.context_builder.build(results, query)

        # Convert to legislative_context format
        return {
            "state_legislation_refs": list(set(
                r.bill_id for r in results if r.bill_id != "unknown"
            ))[:2],  # Max 2 bills
            "federal_program_refs": [],  # TODO: Add federal search
            "relevance_summary": self._generate_summary(results, opportunity),
        }

    def _build_query(self, opportunity: dict) -> str:
        """Build search query from opportunity fields."""
        parts = []

        # Title is most important
        if opportunity.get("title"):
            parts.append(opportunity["title"])

        # Description adds context
        if opportunity.get("description"):
            desc = opportunity["description"]
            # Truncate long descriptions
            if len(desc) > 200:
                desc = desc[:200] + "..."
            parts.append(desc)

        # Project type helps narrow
        project_type = opportunity.get("project_type", "")
        if project_type:
            parts.append(f"topic: {project_type}")

        return " ".join(parts)

    def _generate_summary(
        self,
        results: list,
        opportunity: dict,
    ) -> str:
        """Generate relevance summary from search results."""
        if not results:
            return ""

        top_result = results[0]

        # Get bill info from metadata
        title = top_result.metadata.get("title", "relevant legislation")
        bill_id = top_result.bill_id

        return f"Related to {bill_id}: {title}"


def create_semantic_enricher(**kwargs) -> SemanticEnricher:
    """Factory function for SemanticEnricher."""
    return SemanticEnricher(**kwargs)
