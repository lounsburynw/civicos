"""
QueryPlanner — deterministic rules engine.

Takes verb params → QueryPlan (list of CorpusQuery objects).
No LLM. Distributes global limit across corpora.
"""

import base64
import json
import math
from typing import Dict, List, Optional

from civicos_services.query.models import CorpusQuery, QueryPlan
from civicos_services.query.adapters import get_adapter


def decode_cursor(cursor: Optional[str]) -> Dict[str, int]:
    """Decode a base64-encoded JSON cursor into per-corpus offsets.

    Cursor format: base64(json({"decisions": 5, "legislation": 5, ...}))
    Returns empty dict on invalid/missing cursor.
    """
    if not cursor:
        return {}
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        offsets = json.loads(decoded)
        if isinstance(offsets, dict) and all(isinstance(v, int) for v in offsets.values()):
            return offsets
        return {}
    except Exception:
        return {}


def encode_cursor(offsets: Dict[str, int]) -> Optional[str]:
    """Encode per-corpus offsets into a base64 cursor string.

    Returns None if all offsets are 0 or dict is empty.
    """
    non_zero = {k: v for k, v in offsets.items() if v > 0}
    if not non_zero:
        return None
    raw = json.dumps(non_zero, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def plan_search(
    query: str,
    corpus: List[str],
    limit: int = 10,
    since: Optional[str] = None,
    until: Optional[str] = None,
    location: Optional[str] = None,
    depth: str = "standard",
    cursor: Optional[str] = None,
) -> QueryPlan:
    """
    Plan a multi-corpus search.

    Distributes the global limit across corpora (minimum 3 per corpus).
    Only includes filters each adapter declares it supports.
    Decodes cursor to set per-corpus offsets.
    """
    offsets = decode_cursor(cursor)

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
            offset=offsets.get(corpus_name, 0),
        ))

    return QueryPlan(
        corpus_queries=queries,
        timeout_ms=10000,
    )
