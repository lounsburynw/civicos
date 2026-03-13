"""
QueryPlanner — deterministic rules engine.

Takes verb params → QueryPlan (list of CorpusQuery objects).
No LLM. Distributes global limit across corpora.
"""

import math
from typing import Dict, List, Optional

from civicos_services.query.models import CorpusQuery, QueryPlan
from civicos_services.query.adapters import get_adapter


def plan_search(
    query: str,
    corpus: List[str],
    limit: int = 10,
    since: Optional[str] = None,
    until: Optional[str] = None,
    location: Optional[str] = None,
    depth: str = "standard",
) -> QueryPlan:
    """
    Plan a multi-corpus search.

    Distributes the global limit across corpora (minimum 3 per corpus).
    Only includes filters each adapter declares it supports.
    """
    n_corpora = len(corpus)
    per_corpus = max(3, math.ceil(limit / n_corpora))

    queries = []
    for corpus_name in corpus:
        adapter = get_adapter(corpus_name)
        if adapter is None:
            continue

        # Build filter params — only include what adapter supports
        params: Dict[str, str] = {}
        if since and "since" in adapter.supported_filters:
            params["since"] = since
        if until and "until" in adapter.supported_filters:
            params["until"] = until
        if location and "location" in adapter.supported_filters:
            params["location"] = location

        queries.append(CorpusQuery(
            corpus=corpus_name,
            method="search",
            params=params,
            per_corpus_limit=per_corpus,
        ))

    return QueryPlan(
        corpus_queries=queries,
        timeout_ms=10000,
    )
