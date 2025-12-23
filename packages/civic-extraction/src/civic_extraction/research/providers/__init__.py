"""
Search providers for research operations.

Providers abstract different search APIs (Perplexity, Tavily, etc.)
behind a common interface.
"""

from .base import SearchProvider, SearchProviderError, SearchResult
from .perplexity import PerplexityProvider

__all__ = [
    "SearchProvider",
    "SearchProviderError",
    "SearchResult",
    "PerplexityProvider",
    "get_provider",
]


def get_provider(name: str | None = None) -> SearchProvider:
    """
    Get a search provider by name.

    Args:
        name: Provider name. If None, uses CIVIC_SEARCH_PROVIDER env var,
              defaulting to "perplexity".

    Returns:
        Configured SearchProvider instance.

    Raises:
        ValueError: If provider name is unknown.
    """
    import os

    if name is None:
        name = os.environ.get("CIVIC_SEARCH_PROVIDER", "perplexity")

    name = name.lower()

    if name == "perplexity":
        return PerplexityProvider()
    # Future providers:
    # elif name == "tavily":
    #     return TavilyProvider()
    else:
        raise ValueError(
            f"Unknown search provider: {name}. "
            f"Available: perplexity"
        )
