"""
Context builder for LLM prompts.

Transforms search results into well-formatted context for LLM prompts,
with citation tracking and token management.
"""

from dataclasses import dataclass
from typing import Optional

from civicos._internal.legal.retrieval.search import LegalSearchResult


@dataclass
class LegalContext:
    """Built context for LLM prompts."""
    text: str  # Formatted context text
    citations: list[dict]  # Citation metadata
    token_count: int  # Estimated tokens
    sources: list[str]  # Source bill IDs


class ContextBuilder:
    """
    Builds LLM context from search results.

    Features:
    - Deduplication of overlapping chunks
    - Citation formatting
    - Token budget management
    - Source attribution

    Usage:
        builder = ContextBuilder(max_tokens=4000)
        context = builder.build(search_results, query="wildfire funding")
    """

    # Rough estimate: 4 chars per token
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        max_tokens: int = 4000,
        include_metadata: bool = True,
        citation_style: str = "inline",  # "inline", "footnote", "none"
    ):
        """
        Initialize context builder.

        Args:
            max_tokens: Maximum tokens in output
            include_metadata: Include bill metadata
            citation_style: How to format citations
        """
        self.max_tokens = max_tokens
        self.include_metadata = include_metadata
        self.citation_style = citation_style

    def build(
        self,
        results: list[LegalSearchResult],
        query: Optional[str] = None,
    ) -> LegalContext:
        """
        Build context from search results.

        Args:
            results: Search results to include
            query: Original query (for relevance header)

        Returns:
            LegalContext with formatted text and metadata
        """
        sections = []
        citations = []
        sources = set()
        current_tokens = 0
        max_chars = self.max_tokens * self.CHARS_PER_TOKEN

        # Header
        if query:
            header = f"Relevant California legislation for: {query}\n\n"
            sections.append(header)
            current_tokens += len(header) // self.CHARS_PER_TOKEN

        # Add results until budget exhausted
        for i, result in enumerate(results):
            # Format this result
            section = self._format_result(result, i + 1)
            section_tokens = len(section) // self.CHARS_PER_TOKEN

            # Check budget
            if current_tokens + section_tokens > self.max_tokens:
                # Add truncation notice
                sections.append(
                    f"\n[{len(results) - i} additional results truncated due to context limit]"
                )
                break

            sections.append(section)
            current_tokens += section_tokens

            # Track citations
            citations.append({
                "index": i + 1,
                "bill_id": result.bill_id,
                "section": result.section,
                "relevance": result.relevance_score,
            })
            sources.add(result.bill_id)

        text = "\n".join(sections)

        return LegalContext(
            text=text,
            citations=citations,
            token_count=len(text) // self.CHARS_PER_TOKEN,
            sources=list(sources),
        )

    def _format_result(self, result: LegalSearchResult, index: int) -> str:
        """Format a single result for context."""
        parts = []

        # Citation header
        if self.citation_style == "inline":
            parts.append(f"[{index}] {result.bill_id}")
        elif self.citation_style == "footnote":
            parts.append(f"{result.bill_id}")

        # Metadata
        if self.include_metadata:
            meta_parts = []
            if result.section != "unknown":
                meta_parts.append(f"Section: {result.section}")
            if result.metadata.get("title"):
                meta_parts.append(f"Title: {result.metadata['title']}")
            if result.metadata.get("author"):
                meta_parts.append(f"Author: {result.metadata['author']}")
            if meta_parts:
                parts.append(" | ".join(meta_parts))

        # Text content
        parts.append(result.text)

        return "\n".join(parts) + "\n"

    def build_comparison(
        self,
        results_a: list[LegalSearchResult],
        results_b: list[LegalSearchResult],
        label_a: str = "Current",
        label_b: str = "Proposed",
    ) -> LegalContext:
        """
        Build context comparing two sets of results.

        Useful for showing how legislation changed or comparing bills.
        """
        sections = []
        citations = []
        sources = set()

        # Section A
        sections.append(f"## {label_a}\n")
        for i, result in enumerate(results_a[:3]):  # Limit each section
            sections.append(self._format_result(result, i + 1))
            sources.add(result.bill_id)

        # Section B
        sections.append(f"\n## {label_b}\n")
        for i, result in enumerate(results_b[:3]):
            sections.append(self._format_result(result, len(results_a) + i + 1))
            sources.add(result.bill_id)

        text = "\n".join(sections)

        return LegalContext(
            text=text,
            citations=citations,
            token_count=len(text) // self.CHARS_PER_TOKEN,
            sources=list(sources),
        )
