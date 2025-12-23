"""
Research module for civic data discovery.

This module provides tools for researching civic data from web sources
using AI-powered search providers (Perplexity, Tavily, etc.).

Example usage:
    from civic_extraction.research import MunicipalFundingResearcher, get_provider

    # Use default provider (from CIVIC_SEARCH_PROVIDER env var)
    researcher = MunicipalFundingResearcher()
    result = researcher.research("San Rafael", "California")

    # Use specific provider
    from civic_extraction.research.providers import PerplexityProvider
    provider = PerplexityProvider()
    researcher = MunicipalFundingResearcher(provider=provider)
"""

from .municipal import MunicipalFundingResearcher, MunicipalFundingPrograms
from .providers import SearchProvider, SearchResult, get_provider

__all__ = [
    "MunicipalFundingResearcher",
    "MunicipalFundingPrograms",
    "SearchProvider",
    "SearchResult",
    "get_provider",
]
