"""
Abstract base for search/research providers.

Providers execute web searches and return results with citations.
This abstraction allows swapping between Perplexity, Tavily, or other
search APIs without changing research logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """Result from a search provider."""

    content: str
    """The search result content/answer."""

    citations: list[str] = field(default_factory=list)
    """Source URLs cited in the response."""

    model: str = ""
    """Model used for the search."""

    cost: float = 0.0
    """Cost of the API call in USD."""

    raw_response: Optional[dict] = None
    """Raw API response for debugging/audit."""


class SearchProvider(ABC):
    """Abstract base class for search providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging and config."""
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        max_tokens: int = 4000,
        temperature: float = 0.2,
    ) -> SearchResult:
        """
        Execute a search query and return results.

        Args:
            query: The search query/prompt.
            max_tokens: Maximum tokens in response.
            temperature: Response temperature (lower = more focused).

        Returns:
            SearchResult with content, citations, and metadata.

        Raises:
            SearchProviderError: If the search fails.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


class SearchProviderError(Exception):
    """Error from a search provider."""

    def __init__(self, provider: str, message: str, cause: Optional[Exception] = None):
        self.provider = provider
        self.message = message
        self.cause = cause
        super().__init__(f"[{provider}] {message}")
