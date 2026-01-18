"""
Research module for civic data discovery.

This module provides tools for researching civic data from web sources
using AI-powered search providers (Perplexity, Tavily, etc.).

Architecture:
    - BaseResearcher: Abstract class with common orchestration logic
    - Topic-specific researchers extend BaseResearcher
    - SearchProvider: Abstract interface for search backends

Example usage:
    from civicos_extraction.research import MunicipalFundingResearcher, get_provider

    # Use default provider (from CIVICOS_SEARCH_PROVIDER env var)
    researcher = MunicipalFundingResearcher()
    result = researcher.research("San Rafael", "California")

    # Use specific provider
    from civicos_extraction.research.providers import PerplexityProvider
    provider = PerplexityProvider()
    researcher = MunicipalFundingResearcher(provider=provider)

Extending for new topics:
    from civicos_extraction.research import BaseResearcher

    class TransportationResearcher(BaseResearcher):
        def _get_topic(self) -> str:
            return "transportation"

        def _get_query_templates(self) -> list[QueryTemplate]:
            return [...]

        def _build_prompt(self, jurisdiction, state, **kwargs) -> str:
            return "..."

        def _parse_response(self, result) -> Optional[BaseModel]:
            return TransportationPrograms(...)

        def _merge_results(self, result) -> Optional[BaseModel]:
            return merged_data
"""

from .base import (
    BaseResearcher,
    EnsembleResearchResult,
    MunicipalityConfig,
    QueryResult,
    QueryTemplate,
    ResearchResult,
)
from .municipal import MunicipalFundingResearcher, MunicipalFundingPrograms
from .providers import SearchProvider, SearchResult, get_provider

__all__ = [
    # Base classes for extending
    "BaseResearcher",
    "QueryTemplate",
    "MunicipalityConfig",
    # Result types
    "ResearchResult",
    "EnsembleResearchResult",
    "QueryResult",
    # Housing researcher
    "MunicipalFundingResearcher",
    "MunicipalFundingPrograms",
    # Provider interface
    "SearchProvider",
    "SearchResult",
    "get_provider",
]
