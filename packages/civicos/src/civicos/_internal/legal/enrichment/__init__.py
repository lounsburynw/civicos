"""
Event enrichment with legislative context.

Provides two enrichment paths:
1. Keyword-based (fast, current civic-enrichment implementation)
2. Semantic (RAG-based, uses vector search)

For backwards compatibility, this module re-exports from civic-enrichment.
New code should import from here for future semantic capabilities.

Usage:
    from civicos._internal.legal.enrichment import enrich_opportunity, LegislativeCache

    cache = LegislativeCache()
    context = enrich_opportunity(opportunity, cache)

    # Or with semantic enrichment (requires [embeddings])
    context = enrich_opportunity(opportunity, cache, mode="semantic")
"""

# Re-export from civic-enrichment for backwards compatibility
try:
    from civic_enrichment.cache import LegislativeCache, create_default_cache
    from civic_enrichment.matcher import (
        enrich_opportunity as _keyword_enrich,
        enrich_opportunities_batch as _keyword_enrich_batch,
        find_relevant_bills,
        find_relevant_programs,
        extract_state_from_jurisdiction,
        TOPIC_ENRICHMENT_POLICY,
    )
    LEGACY_AVAILABLE = True
except ImportError:
    LEGACY_AVAILABLE = False
    LegislativeCache = None
    create_default_cache = None
    _keyword_enrich = None
    _keyword_enrich_batch = None
    find_relevant_bills = None
    find_relevant_programs = None
    extract_state_from_jurisdiction = None
    TOPIC_ENRICHMENT_POLICY = {}

# Semantic enrichment (requires embeddings)
try:
    from civicos._internal.legal.enrichment.semantic import SemanticEnricher
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    SemanticEnricher = None


def enrich_opportunity(
    opportunity: dict,
    cache: "LegislativeCache" = None,
    mode: str = "keyword",
    **kwargs
) -> dict | None:
    """
    Enrich a civic opportunity with legislative context.

    Args:
        opportunity: CivicEvent dict from schema
        cache: LegislativeCache instance (required for keyword mode)
        mode: "keyword" (fast, default) or "semantic" (RAG-based)
        **kwargs: Additional arguments passed to enricher

    Returns:
        legislative_context dict or None

    Raises:
        ImportError: If required dependencies not installed
    """
    if mode == "keyword":
        if not LEGACY_AVAILABLE:
            raise ImportError(
                "civic-enrichment not installed. "
                "Install with: pip install civic-enrichment"
            )
        if cache is None:
            raise ValueError("cache required for keyword mode")
        return _keyword_enrich(opportunity, cache)

    elif mode == "semantic":
        if not SEMANTIC_AVAILABLE:
            raise ImportError(
                "Semantic enrichment requires embeddings. "
                "Install with: pip install civicos-legal[embeddings]"
            )
        enricher = SemanticEnricher(**kwargs)
        return enricher.enrich(opportunity)

    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'keyword' or 'semantic'.")


def enrich_opportunities_batch(
    opportunities: list[dict],
    cache: "LegislativeCache" = None,
    mode: str = "keyword",
    **kwargs
) -> list[dict]:
    """
    Enrich multiple opportunities in batch.

    Args:
        opportunities: List of CivicEvent dicts
        cache: LegislativeCache instance (required for keyword mode)
        mode: "keyword" (fast, default) or "semantic" (RAG-based)

    Returns:
        List of opportunities with legislative_context added where relevant
    """
    if mode == "keyword":
        if not LEGACY_AVAILABLE:
            raise ImportError("civic-enrichment not installed")
        if cache is None:
            raise ValueError("cache required for keyword mode")
        return _keyword_enrich_batch(opportunities, cache)

    elif mode == "semantic":
        # Semantic batch enrichment
        enriched = []
        for opp in opportunities:
            context = enrich_opportunity(opp, mode="semantic", **kwargs)
            if context:
                enriched.append({**opp, "legislative_context": context})
            else:
                enriched.append(opp)
        return enriched

    else:
        raise ValueError(f"Unknown mode: {mode}")


__all__ = [
    # Cache (re-exported)
    "LegislativeCache",
    "create_default_cache",
    # Enrichment functions
    "enrich_opportunity",
    "enrich_opportunities_batch",
    "find_relevant_bills",
    "find_relevant_programs",
    "extract_state_from_jurisdiction",
    "TOPIC_ENRICHMENT_POLICY",
    # Semantic (optional)
    "SemanticEnricher",
    "SEMANTIC_AVAILABLE",
    "LEGACY_AVAILABLE",
]
