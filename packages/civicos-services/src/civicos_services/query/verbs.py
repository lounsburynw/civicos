"""
Verb implementations for the v2 query interface.

Each verb is an async function that takes a request + dependencies
and returns a response. The router calls these.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from civicos_services.query.models import (
    SCHEMA_VERSION,
    ActRequest,
    ActResponse,
    AggregateEntry,
    CivicResult,
    ContextRequest,
    ContextResponse,
    ExploreRequest,
    ExploreResponse,
    ResponseMeta,
    SearchMode,
    SearchRequest,
    SearchResponse,
    TrendBucket,
    UpcomingRequest,
    UpcomingResponse,
)
from civicos_services.query.adapters import ADAPTER_REGISTRY, get_adapter, list_corpus_names
from civicos_services.query.planner import plan_search, encode_cursor
from civicos_services.query.merger import reciprocal_rank_fusion

logger = logging.getLogger(__name__)

CORPUS_TIMEOUT_S = 20

# Latency alert thresholds (ms) — per-corpus
CORPUS_LATENCY_WARN_MS = 5_000   # Warn if a single corpus exceeds this
CORPUS_LATENCY_ERROR_MS = 15_000  # Error if a single corpus exceeds this

# Total query latency thresholds (ms)
QUERY_LATENCY_WARN_MS = 8_000
QUERY_LATENCY_ERROR_MS = 20_000


def _log_query_metrics(
    verb: str,
    jurisdiction: str,
    query: str,
    total_time_ms: int,
    corpus_times: dict[str, int],
    corpus_status: dict[str, str],
    corpus_counts: dict[str, int],
    total_results: int,
) -> None:
    """Emit structured log event for query performance tracking.

    Logs at INFO for normal queries, WARNING for slow queries, ERROR for
    very slow queries or those with corpus errors/timeouts.
    """
    slow_corpora = {
        c: t for c, t in corpus_times.items() if t >= CORPUS_LATENCY_WARN_MS
    }
    error_corpora = {
        c: s for c, s in corpus_status.items() if s in ("timeout", "error")
    }

    # Determine log level
    level = logging.INFO
    if slow_corpora or total_time_ms >= QUERY_LATENCY_WARN_MS:
        level = logging.WARNING
    if error_corpora or total_time_ms >= QUERY_LATENCY_ERROR_MS or any(
        t >= CORPUS_LATENCY_ERROR_MS for t in corpus_times.values()
    ):
        level = logging.ERROR

    logger.log(level, "query_complete", extra={
        "verb": verb,
        "jurisdiction": jurisdiction,
        "query": query[:100],
        "total_time_ms": total_time_ms,
        "total_results": total_results,
        "corpus_times_ms": corpus_times,
        "corpus_status": corpus_status,
        "corpus_counts": corpus_counts,
        "slow_corpora": slow_corpora if slow_corpora else None,
        "error_corpora": list(error_corpora.keys()) if error_corpora else None,
    })


# === civic.search ===

async def execute_search(
    request: SearchRequest,
    civic,
    jurisdiction: str,
) -> SearchResponse:
    """Execute a multi-corpus search with parallel fan-out and RRF merging.

    Supports three modes:
    - search: standard result list with optional cursor pagination
    - aggregate: per-corpus counts/statistics
    - trend: time-bucketed counts per corpus

    Cross-jurisdiction: when include_parents or include_siblings is set,
    resolves target jurisdictions, fans out per-jurisdiction, and merges
    with tier-based relevance boosting.
    """
    storage = civic.storage
    vectors = civic.vectors

    # Cross-jurisdiction: delegate to multi-jurisdiction fan-out
    if (
        request.include_parents
        or request.include_siblings
        or request.also_include
        or request.per_jurisdiction_limit is not None
    ):
        return await _execute_cross_jurisdiction_search(request, storage, vectors, jurisdiction)

    start = time.monotonic()

    plan = plan_search(
        query=request.query,
        corpus=request.corpus,
        limit=request.limit,
        since=request.since,
        until=request.until,
        location=request.location,
        depth=request.depth.value,
        cursor=request.cursor,
    )

    jid = request.jurisdiction or jurisdiction
    mode = request.mode

    # Fan out to adapters in parallel
    corpus_results: Dict[str, List[CivicResult]] = {}
    corpus_times: Dict[str, int] = {}
    corpus_status: Dict[str, str] = {}
    corpus_counts: Dict[str, int] = {}

    async def run_corpus(cq):
        adapter = get_adapter(cq.corpus)
        if adapter is None:
            return cq.corpus, [], "error", 0

        c_start = time.monotonic()
        try:
            # For aggregate/trend, fetch more results to get full counts/dates
            fetch_limit = cq.per_corpus_limit if mode == SearchMode.search else 100

            # Run sync adapter in executor with timeout
            loop = asyncio.get_event_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: adapter.search(
                        storage, vectors, jid, request.query, fetch_limit,
                        offset=cq.offset if mode == SearchMode.search else 0,
                        **cq.params,
                    ),
                ),
                timeout=CORPUS_TIMEOUT_S,
            )
            elapsed = int((time.monotonic() - c_start) * 1000)
            status = "ok" if results else "empty"
            return cq.corpus, results, status, elapsed
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - c_start) * 1000)
            logger.warning(f"Corpus {cq.corpus} timed out after {elapsed}ms")
            return cq.corpus, [], "timeout", elapsed
        except Exception as e:
            elapsed = int((time.monotonic() - c_start) * 1000)
            logger.error(f"Corpus {cq.corpus} error: {e}")
            return cq.corpus, [], "error", elapsed

    tasks = [run_corpus(cq) for cq in plan.corpus_queries]
    results = await asyncio.gather(*tasks)

    for corpus_name, corpus_result_list, status, elapsed in results:
        corpus_results[corpus_name] = corpus_result_list
        corpus_times[corpus_name] = elapsed
        corpus_status[corpus_name] = status
        corpus_counts[corpus_name] = len(corpus_result_list)

    total_time = int((time.monotonic() - start) * 1000)
    meta = ResponseMeta(
        schema_version=SCHEMA_VERSION,
        query_time_ms=total_time,
        corpora_searched=list(corpus_results.keys()),
        corpus_counts=corpus_counts,
        corpus_times_ms=corpus_times,
        corpus_status=corpus_status,
        total_results=sum(corpus_counts.values()),
    )

    _log_query_metrics(
        verb="search",
        jurisdiction=jid,
        query=request.query,
        total_time_ms=total_time,
        corpus_times=corpus_times,
        corpus_status=corpus_status,
        corpus_counts=corpus_counts,
        total_results=meta.total_results,
    )

    # === Mode: diff (EXCEPT — what's new since snapshot) ===
    if mode == SearchMode.diff:
        if not request.snapshot_date:
            return SearchResponse(
                results=[],
                meta=ResponseMeta(
                    schema_version=SCHEMA_VERSION,
                    query_time_ms=int((time.monotonic() - start) * 1000),
                    corpus_status={"error": "snapshot_date required for diff mode"},
                ),
            )

        # Filter current results to items dated after the snapshot
        snapshot = request.snapshot_date[:10]
        diff_results: Dict[str, List[CivicResult]] = {}
        for corpus_name, result_list in corpus_results.items():
            new_items = [r for r in result_list if r.date and r.date[:10] > snapshot]
            diff_results[corpus_name] = new_items

        merged = reciprocal_rank_fusion(diff_results, global_limit=request.limit)
        meta.total_results = len(merged)
        meta.corpus_counts = {k: len(v) for k, v in diff_results.items()}

        return SearchResponse(results=merged, meta=meta)

    # === Mode: intersect (INTERSECT — items appearing across corpora) ===
    if mode == SearchMode.intersect:
        if not request.intersect_corpus:
            return SearchResponse(
                results=[],
                meta=ResponseMeta(
                    schema_version=SCHEMA_VERSION,
                    query_time_ms=int((time.monotonic() - start) * 1000),
                    corpus_status={"error": "intersect_corpus required for intersect mode"},
                ),
            )

        # Execute search on the intersect corpora
        intersect_plan = plan_search(
            query=request.query,
            corpus=request.intersect_corpus,
            limit=100,
            since=request.since,
            until=request.until,
            location=request.location,
            depth=request.depth.value,
        )

        intersect_results: Dict[str, List[CivicResult]] = {}

        async def run_intersect_corpus(cq):
            adapter = get_adapter(cq.corpus)
            if adapter is None:
                logger.warning(f"Intersect corpus {cq.corpus}: no adapter found")
                return cq.corpus, []
            try:
                loop = asyncio.get_event_loop()
                results = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: adapter.search(storage, vectors, jid, request.query, 100, offset=0, **cq.params),
                    ),
                    timeout=CORPUS_TIMEOUT_S,
                )
                return cq.corpus, results
            except asyncio.TimeoutError:
                logger.warning(f"Intersect corpus {cq.corpus} timed out")
                return cq.corpus, []
            except Exception as e:
                logger.error(f"Intersect corpus {cq.corpus} error: {e}")
                return cq.corpus, []

        intersect_tasks = [run_intersect_corpus(cq) for cq in intersect_plan.corpus_queries]
        intersect_raw = await asyncio.gather(*intersect_tasks)
        for corpus_name, result_list in intersect_raw:
            intersect_results[corpus_name] = result_list

        # Match primary results against intersect results by date or significant title words.
        # Date matching: same calendar day. Title matching: shared words >= 6 chars
        # (short words like "city", "plan", "code" are too common in civic data).
        intersect_dates = set()
        intersect_words: set = set()
        for result_list in intersect_results.values():
            for r in result_list:
                if r.date:
                    intersect_dates.add(r.date[:10])
                for word in r.title.lower().split():
                    if len(word) >= 6:
                        intersect_words.add(word)

        matched_results: Dict[str, List[CivicResult]] = {}
        for corpus_name, result_list in corpus_results.items():
            matched = []
            for r in result_list:
                date_match = r.date and r.date[:10] in intersect_dates
                primary_words = {w for w in r.title.lower().split() if len(w) >= 6}
                title_match = bool(primary_words & intersect_words)
                if date_match or title_match:
                    matched.append(r)
            matched_results[corpus_name] = matched

        merged = reciprocal_rank_fusion(matched_results, global_limit=request.limit)
        meta.total_results = len(merged)
        meta.corpus_counts = {k: len(v) for k, v in matched_results.items()}

        return SearchResponse(results=merged, meta=meta)

    # === Mode: aggregate ===
    if mode == SearchMode.aggregate:
        aggregates = []
        for corpus_name, result_list in corpus_results.items():
            dates = [r.date for r in result_list if r.date]
            aggregates.append(AggregateEntry(
                corpus=corpus_name,
                count=len(result_list),
                earliest=min(dates) if dates else None,
                latest=max(dates) if dates else None,
            ))
        return SearchResponse(aggregates=aggregates, meta=meta)

    # === Mode: trend ===
    if mode == SearchMode.trend:
        buckets: Dict[str, Dict[str, int]] = {}  # {period: {corpus: count}}
        for corpus_name, result_list in corpus_results.items():
            for r in result_list:
                period = r.date[:7] if r.date and len(r.date) >= 7 else "unknown"
                if period not in buckets:
                    buckets[period] = {}
                buckets[period][corpus_name] = buckets[period].get(corpus_name, 0) + 1

        trends = []
        for period in sorted(buckets.keys()):
            for corpus_name, count in sorted(buckets[period].items()):
                trends.append(TrendBucket(period=period, count=count, corpus=corpus_name))
        return SearchResponse(trends=trends, meta=meta)

    # === Mode: search (default) ===
    merged = reciprocal_rank_fusion(corpus_results, global_limit=request.limit)

    # Build next cursor if any corpus returned a full page
    next_offsets = {}
    for cq in plan.corpus_queries:
        returned = len(corpus_results.get(cq.corpus, []))
        if returned >= cq.per_corpus_limit:
            next_offsets[cq.corpus] = cq.offset + returned
    meta.cursor = encode_cursor(next_offsets)

    return SearchResponse(results=merged, meta=meta)


# === Cross-jurisdiction search ===

async def _execute_cross_jurisdiction_search(
    request: SearchRequest,
    storage,
    vectors,
    jurisdiction: str,
) -> SearchResponse:
    """Fan out search across multiple jurisdictions with tier-based boosting.

    Uses storage/vector backends directly — no CivicOS instances needed.
    Adapters accept jurisdiction as a parameter, so the same storage/vector
    backends serve all jurisdictions (they filter by jurisdiction_id internally).
    """
    from civicos_services.query.jurisdictions import (
        resolve_jurisdictions,
        get_tier_weight,
        validate_jurisdiction_ids,
    )

    start = time.monotonic()
    base_jid = request.jurisdiction or jurisdiction

    # Validate also_include jurisdiction IDs against registry
    if request.also_include:
        unknown = validate_jurisdiction_ids(request.also_include)
        if unknown:
            return SearchResponse(
                meta=ResponseMeta(
                    schema_version=SCHEMA_VERSION,
                    query_time_ms=0,
                    corpus_status={"error": f"Unknown jurisdiction IDs in also_include: {unknown}"},
                ),
            )

    target_jids = resolve_jurisdictions(
        base_jid,
        include_parents=request.include_parents,
        include_siblings=request.include_siblings,
    )

    # Append explicit cross-county jurisdictions (deduplicating)
    if request.also_include:
        for jid in request.also_include:
            if jid not in target_jids:
                target_jids.append(jid)

    logger.info(f"Cross-jurisdiction search: {base_jid} -> {target_jids}")

    # Pre-compute query embedding once and warm the cache for all fan-out threads
    if vectors is not None and hasattr(vectors, '_embedding_cache'):
        try:
            loop = asyncio.get_event_loop()
            query_embedding = await loop.run_in_executor(
                None,
                lambda: vectors._embedding_provider.encode([request.query])[0],
            )
            with vectors._embedding_cache_lock:
                vectors._embedding_cache[request.query] = query_embedding
        except Exception:
            pass  # Fall back to per-search encoding

    # Create a single-jurisdiction request (no cross-jurisdiction flags).
    # When per_jurisdiction_limit is set, each fan-out search fetches that many
    # results from each jid (rather than the global request.limit) so that the
    # comparative interleave has enough material per jid.
    per_jid_limit = request.per_jurisdiction_limit
    per_jid_request = request.model_copy(update={
        "include_parents": False,
        "include_siblings": False,
        "also_include": None,
        "per_jurisdiction_limit": None,
        # If comparative mode, ask each jid for exactly per_jid_limit results.
        # Otherwise leave request.limit alone (planner will divide among corpora).
        **({"limit": per_jid_limit} if per_jid_limit is not None else {}),
    })

    # Fan out per-jurisdiction in parallel — all use shared storage/vectors
    async def search_jurisdiction(jid: str) -> tuple:
        """Run search for one jurisdiction using shared backends."""
        try:
            jid_request = per_jid_request.model_copy(update={"jurisdiction": jid})
            response = await _execute_single_jurisdiction_search(
                jid_request, storage, vectors, jid,
            )
            return jid, response
        except Exception as e:
            logger.error(f"Cross-jurisdiction search failed for {jid}: {e}")
            return jid, SearchResponse(
                meta=ResponseMeta(
                    corpus_status={"error": str(e)},
                ),
            )

    # Fan out all jurisdictions in parallel — no warm-up needed since
    # we're reusing the same storage/vector backends (no connection overhead)
    tasks = [search_jurisdiction(jid) for jid in target_jids]
    jid_responses = await asyncio.gather(*tasks)

    # Collect results, tag with jurisdiction, apply tier boosting
    all_results: List[CivicResult] = []
    jurisdiction_grouped: Dict[str, List[CivicResult]] = {}
    all_corpus_times: Dict[str, int] = {}
    all_corpus_status: Dict[str, str] = {}
    all_corpus_counts: Dict[str, int] = {}

    for jid, response in jid_responses:
        tier_weight = get_tier_weight(base_jid, jid)
        jid_results = []
        for r in response.results:
            r.jurisdiction = jid
            if r.relevance is not None:
                r.relevance = round(r.relevance * tier_weight, 4)
            jid_results.append(r)
        # Sort within-jid by tier-boosted relevance so per-jid caps take the
        # best N from each (not whatever the adapter happened to return first).
        jid_results.sort(key=lambda r: r.relevance or 0, reverse=True)
        if per_jid_limit is not None:
            jid_results = jid_results[:per_jid_limit]
        jurisdiction_grouped[jid] = jid_results
        all_results.extend(jid_results)

        # Merge per-corpus meta (prefix with jurisdiction for uniqueness)
        for corpus, ms in response.meta.corpus_times_ms.items():
            all_corpus_times[f"{jid}:{corpus}"] = ms
        for corpus, status in response.meta.corpus_status.items():
            all_corpus_status[f"{jid}:{corpus}"] = status
        for corpus, count in response.meta.corpus_counts.items():
            all_corpus_counts[f"{jid}:{corpus}"] = count

    # Sort by tier-boosted relevance
    all_results.sort(key=lambda r: r.relevance or 0, reverse=True)
    # In comparative mode the per-jid caps already bound the total; otherwise
    # apply the global request.limit cap to the flat ranked stream.
    if per_jid_limit is None:
        merged = all_results[:request.limit]
    else:
        merged = all_results

    total_time = int((time.monotonic() - start) * 1000)
    meta = ResponseMeta(
        query_time_ms=total_time,
        corpora_searched=list(all_corpus_counts.keys()),
        corpus_counts=all_corpus_counts,
        corpus_times_ms=all_corpus_times,
        corpus_status=all_corpus_status,
        total_results=len(all_results),
    )

    _log_query_metrics(
        verb="search:cross_jurisdiction",
        jurisdiction=base_jid,
        query=request.query,
        total_time_ms=total_time,
        corpus_times=all_corpus_times,
        corpus_status=all_corpus_status,
        corpus_counts=all_corpus_counts,
        total_results=len(all_results),
    )

    return SearchResponse(
        results=merged,
        jurisdiction_results=jurisdiction_grouped,
        meta=meta,
    )


async def _execute_single_jurisdiction_search(
    request: SearchRequest,
    storage,
    vectors,
    jurisdiction: str,
) -> SearchResponse:
    """Execute search for a single jurisdiction using storage/vector backends directly.

    Used by cross-jurisdiction fan-out to avoid creating CivicOS instances.
    """
    start = time.monotonic()

    plan = plan_search(
        query=request.query,
        corpus=request.corpus,
        limit=request.limit,
        since=request.since,
        until=request.until,
        location=request.location,
        depth=request.depth.value,
        cursor=request.cursor,
    )

    jid = request.jurisdiction or jurisdiction
    mode = request.mode

    corpus_results: Dict[str, List[CivicResult]] = {}
    corpus_times: Dict[str, int] = {}
    corpus_status: Dict[str, str] = {}
    corpus_counts: Dict[str, int] = {}

    async def run_corpus(cq):
        adapter = get_adapter(cq.corpus)
        if adapter is None:
            return cq.corpus, [], "error", 0

        c_start = time.monotonic()
        try:
            fetch_limit = cq.per_corpus_limit if mode == SearchMode.search else 100
            loop = asyncio.get_event_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: adapter.search(
                        storage, vectors, jid, request.query, fetch_limit,
                        offset=cq.offset if mode == SearchMode.search else 0,
                        **cq.params,
                    ),
                ),
                timeout=CORPUS_TIMEOUT_S,
            )
            elapsed = int((time.monotonic() - c_start) * 1000)
            status = "ok" if results else "empty"
            return cq.corpus, results, status, elapsed
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - c_start) * 1000)
            return cq.corpus, [], "timeout", elapsed
        except Exception as e:
            elapsed = int((time.monotonic() - c_start) * 1000)
            return cq.corpus, [], "error", elapsed

    tasks = [run_corpus(cq) for cq in plan.corpus_queries]
    results = await asyncio.gather(*tasks)

    for corpus_name, corpus_result_list, status, elapsed in results:
        corpus_results[corpus_name] = corpus_result_list
        corpus_times[corpus_name] = elapsed
        corpus_status[corpus_name] = status
        corpus_counts[corpus_name] = len(corpus_result_list)

    total_time = int((time.monotonic() - start) * 1000)
    meta = ResponseMeta(
        schema_version=SCHEMA_VERSION,
        query_time_ms=total_time,
        corpora_searched=list(corpus_results.keys()),
        corpus_counts=corpus_counts,
        corpus_times_ms=corpus_times,
        corpus_status=corpus_status,
        total_results=sum(corpus_counts.values()),
    )

    merged = reciprocal_rank_fusion(corpus_results, global_limit=request.limit)

    next_offsets = {}
    for cq in plan.corpus_queries:
        returned = len(corpus_results.get(cq.corpus, []))
        if returned >= cq.per_corpus_limit:
            next_offsets[cq.corpus] = cq.offset + returned
    meta.cursor = encode_cursor(next_offsets)

    return SearchResponse(results=merged, meta=meta)


# === civic.upcoming ===

async def execute_upcoming(
    request: UpcomingRequest,
    civic,
    jurisdiction: str,
) -> UpcomingResponse:
    """Execute temporal queries for upcoming events."""
    start = time.monotonic()

    jid = request.jurisdiction or jurisdiction
    results: List[CivicResult] = []
    corpus_times: Dict[str, int] = {}
    corpus_status: Dict[str, str] = {}

    for event_type in request.types:
        c_start = time.monotonic()
        try:
            if event_type == "meetings":
                meetings = civic.whats_next(days=request.days)
                for m in meetings:
                    actionable = bool(m.agenda_items)
                    if request.actionable_only and not actionable:
                        continue
                    results.append(CivicResult(
                        type="meeting",
                        ref=f"meeting:{jid}:{m.id}",
                        title=m.title,
                        date=m.date.isoformat() if m.date else None,
                        summary=f"{m.body} — {len(m.agenda_items)} agenda items" if m.agenda_items else m.body,
                        details={
                            "agenda_item_count": len(m.agenda_items),
                            "has_transcript": False,
                            "location": m.location,
                            "body": m.body,
                        },
                    ))
                corpus_status["meetings"] = "ok" if meetings else "empty"

            elif event_type == "hearings":
                # Hearings are a subset of meetings with public hearing items
                meetings = civic.whats_next(days=request.days)
                for m in meetings:
                    hearing_items = [
                        a for a in m.agenda_items
                        if "hearing" in (a.get("title", "") + a.get("type", "")).lower()
                    ]
                    if hearing_items:
                        results.append(CivicResult(
                            type="hearing",
                            ref=f"meeting:{jid}:{m.id}",
                            title=f"Public Hearing: {hearing_items[0].get('title', m.title)}",
                            date=m.date.isoformat() if m.date else None,
                            summary=f"{len(hearing_items)} hearing item(s)",
                            details={"location": m.location},
                        ))
                corpus_status["hearings"] = "ok"

            elif event_type == "comment_periods":
                # Local comment periods from upcoming meetings
                meetings = civic.whats_next(days=request.days)
                for m in meetings:
                    comment_items = [
                        a for a in m.agenda_items
                        if a.get("comment_eligible", False) or "public comment" in a.get("title", "").lower()
                    ]
                    if comment_items:
                        results.append(CivicResult(
                            type="comment_period",
                            ref=f"meeting:{jid}:{m.id}",
                            title=f"Comment period: {m.title}",
                            date=m.date.isoformat() if m.date else None,
                            summary=f"{len(comment_items)} items open for comment",
                            details={"location": m.location},
                        ))

                # Federal comment periods from regulations.gov data
                if hasattr(civic.storage, "get_open_comment_periods"):
                    try:
                        from datetime import date as _date
                        federal_rules = civic.storage.get_open_comment_periods(
                            limit=20,
                        )
                        for rule in federal_rules:
                            close_date = rule.get("comments_close_on")
                            days_remaining = None
                            if close_date:
                                if isinstance(close_date, str):
                                    close_date = _date.fromisoformat(close_date)
                                days_remaining = (close_date - _date.today()).days

                            agency_names = rule.get("agency_names") or []
                            if isinstance(agency_names, str):
                                agency_names = [agency_names]

                            results.append(CivicResult(
                                type="comment_period",
                                ref=f"rule:us-federal:{rule.get('document_number', '')}",
                                title=rule.get("title", ""),
                                date=str(close_date) if close_date else None,
                                summary=rule.get("abstract", ""),
                                details={
                                    "document_number": rule.get("document_number", ""),
                                    "agency_names": agency_names,
                                    "days_remaining": days_remaining,
                                    "comment_url": rule.get("comment_url", ""),
                                    "html_url": rule.get("html_url", ""),
                                    "document_type": rule.get("document_type", ""),
                                    "topics": rule.get("topics") or [],
                                    "publication_date": str(rule["publication_date"]) if rule.get("publication_date") else None,
                                    "level": "federal",
                                    "local_relevance_score": rule.get("local_relevance_score", 0.0),
                                    "relevance_reasons": rule.get("relevance_reasons") or [],
                                    "local_relevance_summary": rule.get("local_relevance_summary") or "",
                                },
                            ))
                        # Sort federal comment periods by relevance (highest first)
                        federal_start = len(results) - len(federal_rules)
                        federal_results = results[federal_start:]
                        federal_results.sort(
                            key=lambda r: r.details.get("local_relevance_score", 0.0),
                            reverse=True,
                        )
                        results[federal_start:] = federal_results
                    except Exception:
                        pass  # Federal rules not available in this backend

                corpus_status["comment_periods"] = "ok"

            elif event_type == "congressional_hearings":
                # Upcoming federal committee hearings
                from datetime import date as _date, timedelta as _td
                now_date = _date.today()
                end_date = now_date + _td(days=request.days)
                ch_hearings = civic.storage.get_congressional_hearings(
                    hearing_date_start=now_date.isoformat(),
                    hearing_date_end=end_date.isoformat(),
                    limit=50,
                )
                for h in ch_hearings:
                    committee = h.get("committee_name", "")
                    hearing_type = h.get("hearing_type", "Hearing")
                    location = f"{h.get('location_building', '')} {h.get('location_room', '')}".strip()
                    results.append(CivicResult(
                        type="congressional_hearing",
                        ref=f"congressional_hearing:{jid}:{h.get('event_id', '')}",
                        title=f"{committee} — {hearing_type}" if committee else h.get("title", ""),
                        date=h.get("hearing_date"),
                        summary=h.get("title", ""),
                        details={
                            "chamber": h.get("chamber"),
                            "hearing_type": hearing_type,
                            "committee_name": committee,
                            "committee_code": h.get("committee_code"),
                            "location": location or None,
                            "meeting_status": h.get("meeting_status"),
                            "related_bills": h.get("related_bills"),
                            "url": h.get("hearing_url"),
                        },
                    ))
                corpus_status["congressional_hearings"] = "ok" if ch_hearings else "empty"

            elif event_type == "elections":
                meetings_and_elections = civic.whats_next(
                    days=request.days, include_elections=True,
                )
                from civicos.types import UpcomingElection
                for item in meetings_and_elections:
                    if isinstance(item, UpcomingElection):
                        results.append(CivicResult(
                            type="election",
                            ref=f"election:{jid}:{item.id}",
                            title=item.name,
                            date=item.election_date.isoformat() if item.election_date else None,
                            summary=item.election_type,
                            details={
                                "election_type": item.election_type,
                                "deadlines": item.deadlines,
                            },
                        ))
                corpus_status["elections"] = "ok"

            elif event_type == "legislation":
                # Governor's desk / active legislation
                reg_stack = civic.what_applies("pending legislation", legislation_status="pending")
                for bill in reg_stack.state[:10]:
                    results.append(CivicResult(
                        type="legislation",
                        ref=f"legislation:{jid}:{bill.get('bill_id', '')}",
                        title=bill.get("bill_name", bill.get("bill_number", "")),
                        date=bill.get("last_action_date"),
                        summary=bill.get("summary", "")[:200],
                        details={
                            "bill_number": bill.get("bill_number"),
                            "status": bill.get("status_label"),
                            "state": bill.get("state"),
                        },
                    ))
                corpus_status["legislation"] = "ok"

            elapsed = int((time.monotonic() - c_start) * 1000)
            corpus_times[event_type] = elapsed

        except Exception as e:
            elapsed = int((time.monotonic() - c_start) * 1000)
            corpus_times[event_type] = elapsed
            corpus_status[event_type] = "error"
            logger.error(f"upcoming/{event_type} error: {e}")

    # Sort by date ascending
    results.sort(key=lambda r: r.date or "9999")

    total_time = int((time.monotonic() - start) * 1000)

    corpus_counts = {t: sum(1 for r in results if r.type == t or t in (r.type + "s")) for t in request.types}

    _log_query_metrics(
        verb="upcoming",
        jurisdiction=jid,
        query=f"upcoming:{','.join(request.types)}",
        total_time_ms=total_time,
        corpus_times=corpus_times,
        corpus_status=corpus_status,
        corpus_counts=corpus_counts,
        total_results=len(results),
    )

    return UpcomingResponse(
        results=results,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
            corpora_searched=request.types,
            corpus_counts=corpus_counts,
            corpus_times_ms=corpus_times,
            corpus_status=corpus_status,
            total_results=len(results),
        ),
    )


# === civic.context ===

def parse_ref(ref: str) -> dict:
    """Parse opaque ref into components.

    Format: {type}:{jurisdiction}:{item_id}
    The item_id may contain colons (e.g., date-based IDs).
    """
    parts = ref.split(":", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid ref format: {ref}")
    return {
        "type": parts[0],
        "jurisdiction": parts[1],
        "item_id": parts[2],
    }


# Map v2 type names to context assembly ItemType values
_TYPE_TO_ITEM_TYPE = {
    "decision": "decision",
    "meeting": "meeting",
    "issue": "issue",
    "legislation": "legislation",
    "testimony": "agenda_item",  # testimony refs point to agenda items
    "hearing": "meeting",
    "comment_period": "meeting",
    "election": "meeting",
    "budget": "decision",  # Budget refs don't have direct context, fallback
    "packet": "agenda_item",
    "order": "legislation",
    "rule": "legislation",
    "municipal_code": "legislation",
    "agenda_item": "agenda_item",
}


async def execute_context(
    request: ContextRequest,
    civic,
    jurisdiction: str,
) -> ContextResponse:
    """Execute context assembly for a specific item, or civic jargon lookup."""
    start = time.monotonic()

    # === Civic jargon / concept lookup ===
    if request.concept:
        return await _execute_concept_lookup(request, civic, jurisdiction, start)

    # === Standard item context via ref ===
    if not request.ref:
        return ContextResponse(
            context={"error": "ref is required for item context lookup"},
            meta=ResponseMeta(schema_version=SCHEMA_VERSION, query_time_ms=0),
        )

    try:
        parsed = parse_ref(request.ref)
    except ValueError as e:
        return ContextResponse(
            context={"error": str(e)},
            meta=ResponseMeta(schema_version=SCHEMA_VERSION, query_time_ms=0),
        )

    from civicos_services.context import assemble_context, ItemType, ContextDepth

    item_type_str = _TYPE_TO_ITEM_TYPE.get(parsed["type"], parsed["type"])
    try:
        item_type = ItemType(item_type_str)
    except ValueError:
        return ContextResponse(
            context={"error": f"Unknown item type: {parsed['type']}"},
            meta=ResponseMeta(schema_version=SCHEMA_VERSION, query_time_ms=0),
        )

    try:
        depth = ContextDepth(request.depth)
    except ValueError:
        depth = ContextDepth.standard

    sections = set(request.sections) if request.sections else None

    try:
        bundle = await assemble_context(
            item_type=item_type,
            item_id=parsed["item_id"],
            jurisdiction=parsed["jurisdiction"],
            sections=sections,
            depth=depth,
        )
        context_data = bundle.model_dump(mode="json")
    except Exception as e:
        logger.error(f"Context assembly error for {request.ref}: {e}")
        context_data = {"error": str(e)}

    total_time = int((time.monotonic() - start) * 1000)

    log_level = logging.INFO
    if total_time >= QUERY_LATENCY_WARN_MS:
        log_level = logging.WARNING
    if total_time >= QUERY_LATENCY_ERROR_MS:
        log_level = logging.ERROR
    logger.log(log_level, "query_complete", extra={
        "verb": "context",
        "jurisdiction": parsed.get("jurisdiction", jurisdiction),
        "query": f"context:{request.ref}",
        "total_time_ms": total_time,
        "ref_type": parsed.get("type"),
    })

    return ContextResponse(
        context=context_data,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
        ),
    )


async def _execute_concept_lookup(
    request: ContextRequest,
    civic,
    jurisdiction: str,
    start: float,
) -> ContextResponse:
    """Look up a civic concept/term from the municipal code corpus."""
    concept = request.concept
    jid = jurisdiction

    adapter = get_adapter("municipal_code")
    if adapter is None:
        total_time = int((time.monotonic() - start) * 1000)
        return ContextResponse(
            context={"concept": concept, "found": False, "error": "Municipal code corpus is not available."},
            meta=ResponseMeta(schema_version=SCHEMA_VERSION, query_time_ms=total_time),
        )

    storage = civic.storage
    vectors = civic.vectors

    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: adapter.search(storage, vectors, jid, concept, limit=5, offset=0),
            ),
            timeout=CORPUS_TIMEOUT_S,
        )

        if not results:
            context_data = {
                "concept": concept,
                "found": False,
                "explanation": f"No municipal code sections found for '{concept}'.",
            }
        else:
            # Build a concept explanation from the top results
            sections = []
            for r in results:
                sections.append({
                    "ref": r.ref,
                    "title": r.title,
                    "excerpt": r.summary,
                    "section_number": r.details.get("section_number"),
                    "relevance": r.relevance,
                })

            context_data = {
                "concept": concept,
                "found": True,
                "definition_source": "municipal_code",
                "jurisdiction": jid,
                "sections": sections,
                "explanation": (
                    f"Based on {len(sections)} relevant section(s) from the "
                    f"municipal code of {jid}."
                ),
            }
    except Exception as e:
        logger.error(f"Concept lookup error for '{concept}': {e}")
        context_data = {"concept": concept, "found": False, "error": str(e)}

    total_time = int((time.monotonic() - start) * 1000)

    return ContextResponse(
        context=context_data,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
            corpora_searched=["municipal_code"],
        ),
    )


# === civic.act ===

# Map action names to existing handler function names
_ACTION_TO_HANDLER = {
    "prepare_comment": "compose_public_comment",
    "comment_template": "get_comment_template",
    "comment_guidelines": "get_comment_guidelines",
    "prepare_meeting": "prepare_for_meeting",
    "prepare_voice": "prepare_voice",
    "broadcast_voice": "broadcast_voice",
    "prepare_initiative": "prepare_initiative",
    "broadcast_initiative": "broadcast_initiative",
    "subscribe": "subscribe_to_topic",
    "draft_federal_comment": "draft_federal_comment",
    "prepare_federal_comment": "prepare_federal_comment",
}


async def execute_act(
    request: ActRequest,
    civic,
    jurisdiction: str,
    call_handler: Callable,
) -> ActResponse:
    """Execute a participation action by delegating to existing handlers."""
    start = time.monotonic()

    handler_name = _ACTION_TO_HANDLER.get(request.action)
    if handler_name is None:
        return ActResponse(
            result={"error": f"Unknown action: {request.action}. Available: {list(_ACTION_TO_HANDLER.keys())}"},
            meta=ResponseMeta(schema_version=SCHEMA_VERSION, query_time_ms=0),
        )

    # Build args for the handler
    args = dict(request.params)
    if request.ref:
        try:
            parsed = parse_ref(request.ref)
            # Map ref to handler-specific params
            if request.action == "prepare_comment":
                args.setdefault("item_title", parsed["item_id"])
            elif request.action in ("prepare_meeting", "prepare_voice"):
                args.setdefault("meeting_id", parsed["item_id"])
            elif request.action == "subscribe":
                args.setdefault("topic", parsed["item_id"])
            elif request.action in ("draft_federal_comment", "prepare_federal_comment"):
                args.setdefault("document_number", parsed["item_id"])
        except ValueError:
            pass  # Invalid ref, let handler decide

    try:
        result = call_handler(handler_name, args)
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = {"text": result}
    except Exception as e:
        logger.error(f"Action {request.action} error: {e}")
        result = {"error": str(e)}

    total_time = int((time.monotonic() - start) * 1000)

    return ActResponse(
        result=result,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
        ),
    )


# === civic.explore ===

# Essential detail field specs per corpus type
CORPUS_SCHEMAS = {
    "decisions": {
        "outcome": {"type": "string", "description": "Vote outcome (e.g., 'Approved 4-1')"},
        "vote_summary": {"type": "string", "description": "Vote count (e.g., '4-1')"},
        "body": {"type": "string", "description": "Governing body (e.g., 'City Council')"},
    },
    "legislation": {
        "bill_number": {"type": "string", "description": "Bill identifier (e.g., 'SB-9')"},
        "status": {"type": "string", "description": "Current status (e.g., 'Enacted')"},
        "state": {"type": "string", "description": "State code (e.g., 'CA')"},
    },
    "testimony": {
        "speaker": {"type": "string", "description": "Speaker name"},
        "speaker_role": {"type": "string", "description": "Role: public, council, staff"},
        "video_url": {"type": "string", "description": "YouTube URL with timestamp"},
    },
    "meetings": {
        "agenda_item_count": {"type": "integer", "description": "Number of agenda items"},
        "has_transcript": {"type": "boolean", "description": "Whether transcript is available"},
        "location": {"type": "string", "description": "Meeting location"},
    },
    "issues": {
        "status": {"type": "string", "description": "Issue status (open/closed)"},
        "category": {"type": "string", "description": "Issue type/category"},
        "address": {"type": "string", "description": "Location address"},
    },
    "budget": {
        "amount": {"type": "number", "description": "Budgeted amount in dollars"},
        "department": {"type": "string", "description": "City department"},
        "fiscal_year": {"type": "string", "description": "Fiscal year (e.g., 'FY25-26')"},
    },
    "municipal_code": {
        "section_number": {"type": "string", "description": "Code section number"},
        "chapter": {"type": "string", "description": "Chapter identifier"},
    },
    "packets": {
        "source_type": {"type": "string", "description": "Document type (e.g., 'pdf')"},
        "agenda_item": {"type": "string", "description": "Related agenda item title"},
        "page_start": {"type": "integer", "description": "Starting page number"},
        "page_end": {"type": "integer", "description": "Ending page number"},
    },
    "orders": {
        "eo_number": {"type": "integer", "description": "Executive order number"},
        "president": {"type": "string", "description": "Issuing president"},
        "status": {"type": "string", "description": "Current status (active/revoked)"},
    },
    "rules": {
        "agency": {"type": "string", "description": "Issuing federal agency"},
        "document_type": {"type": "string", "description": "Rule type (proposed/final/notice)"},
        "effective_date": {"type": "string", "description": "When the rule takes effect"},
    },
}


async def execute_explore(
    request: ExploreRequest,
    civic,
    jurisdiction: str,
) -> ExploreResponse:
    """Execute discovery queries."""
    start = time.monotonic()
    what = request.what
    jid = request.jurisdiction or jurisdiction

    data: Any = None

    if what == "schema_version":
        data = {"schema_version": SCHEMA_VERSION}

    elif what == "jurisdictions":
        # Return available jurisdictions from registry
        from civicos.jurisdiction import JurisdictionRegistry
        jurisdictions = JurisdictionRegistry.list_all()
        data = {
            "jurisdictions": [
                {
                    "id": j.get("id", ""),
                    "display_name": j.get("display_name", ""),
                    "level": j.get("level", ""),
                }
                for j in jurisdictions
            ]
        }

    elif what == "corpora":
        # Return available corpus types with live counts
        try:
            from civicos.diagnostics import DataStatus
            status = DataStatus(civic.storage, civic.vectors, jid)
            report = status.summary()

            corpora = []
            for adapter_name in sorted(ADAPTER_REGISTRY.keys()):
                adapter = ADAPTER_REGISTRY[adapter_name]
                # Match adapter to corpus count
                corpus_count = None
                for key, cc in report.corpus_counts.items():
                    if cc.corpus_type == adapter_name or adapter_name.startswith(cc.corpus_type):
                        corpus_count = cc
                        break

                entry = {
                    "name": adapter_name,
                    "supported_filters": sorted(adapter.supported_filters),
                    "storage_count": corpus_count.storage_count if corpus_count else 0,
                    "vector_count": corpus_count.vector_count if corpus_count else 0,
                }
                corpora.append(entry)

            data = {"corpora": corpora, "jurisdiction": jid}
        except Exception as e:
            logger.error(f"explore/corpora error: {e}")
            data = {
                "corpora": [
                    {"name": name, "supported_filters": sorted(ADAPTER_REGISTRY[name].supported_filters)}
                    for name in sorted(ADAPTER_REGISTRY.keys())
                ],
                "jurisdiction": jid,
                "error": str(e),
            }

    elif what.startswith("corpus_schema:"):
        corpus_name = what.split(":", 1)[1]
        schema = CORPUS_SCHEMAS.get(corpus_name)
        if schema:
            data = {"corpus": corpus_name, "fields": schema}
        else:
            data = {"error": f"Unknown corpus: {corpus_name}. Available: {list(CORPUS_SCHEMAS.keys())}"}

    elif what == "actions":
        data = {
            "actions": [
                {"name": action, "handler": handler, "description": _action_description(action)}
                for action, handler in _ACTION_TO_HANDLER.items()
            ]
        }

    elif what == "capabilities":
        data = {
            "schema_version": SCHEMA_VERSION,
            "verbs": ["civic.search", "civic.upcoming", "civic.context", "civic.act", "civic.explore"],
            "corpora": list_corpus_names(),
            "actions": list(_ACTION_TO_HANDLER.keys()),
            "jurisdiction": jid,
            "description": (
                "CivicOS provides civic data (meetings, decisions, legislation, testimony, "
                "311 issues, budgets, elected officials) for AI agents and developers. "
                "Use civic.explore to discover available data (including representatives), "
                "civic.search for queries, civic.upcoming for temporal events, "
                "civic.context for deep item context, and civic.act for participation actions."
            ),
        }

    elif what == "representatives":
        from civicos_services.query.jurisdictions import resolve_jurisdictions
        try:
            hierarchy = resolve_jurisdictions(jid, include_parents=True)
            levels = []
            for level_jid in hierarchy:
                officials = civic.storage.get_elected_officials(
                    jurisdiction_id=level_jid,
                    current_only=True,
                )
                if officials:
                    levels.append({
                        "jurisdiction": level_jid,
                        "officials": [
                            {
                                "id": o.get("id"),
                                "name": o.get("name"),
                                "seat": o.get("seat"),
                                "term_start": o.get("term_start"),
                                "term_end": o.get("term_end"),
                                "candidate_id": o.get("candidate_id"),
                            }
                            for o in officials
                        ],
                    })
            data = {
                "jurisdiction": jid,
                "levels": levels,
                "total_officials": sum(len(lv["officials"]) for lv in levels),
            }
        except Exception as e:
            logger.error(f"explore/representatives error: {e}")
            data = {"jurisdiction": jid, "levels": [], "error": str(e)}

    elif what == "my_ballot":
        from datetime import date as date_type
        import json as _json

        try:
            elections_raw = civic.storage.get_elections(jid, include_past=False)

            level_map = {
                "federal_president": "federal",
                "federal_senate": "federal",
                "federal_house": "federal",
                "state_governor": "state",
                "state_executive": "state",
                "state_legislature": "state",
                "state_proposition": "state",
                "local_mayor": "local",
                "local_council": "local",
                "local_school_board": "local",
                "local_measure": "local",
                "judicial": "judicial",
                "other": "other",
            }
            level_order = ["federal", "state", "local", "judicial", "other"]

            today = date_type.today()
            ballot = []

            for election in elections_raw:
                election_id = election.get("id")
                election_date_val = election.get("election_date")
                if isinstance(election_date_val, str):
                    election_date = date_type.fromisoformat(election_date_val)
                elif isinstance(election_date_val, date_type):
                    election_date = election_date_val
                else:
                    election_date = None

                days_until = (election_date - today).days if election_date else None

                # Get contests and group by level
                contests_raw = civic.storage.get_election_contests(election_id)
                grouped: Dict[str, list] = {}
                for c in contests_raw:
                    contest_type = c.get("contest_type", "other")
                    level = level_map.get(contest_type, "other")
                    if level not in grouped:
                        grouped[level] = []

                    # Extract candidates from raw_data.parsed_candidates
                    raw_data = c.get("raw_data")
                    if isinstance(raw_data, str):
                        raw_data = _json.loads(raw_data)
                    parsed = (raw_data or {}).get("parsed_candidates", [])
                    candidates = [
                        {
                            "name": cand.get("name"),
                            "party": cand.get("party"),
                            "incumbent": cand.get("incumbent", False),
                        }
                        for cand in parsed
                    ]

                    # Extract ballot measure content for measure contests
                    ballot_measure = None
                    if contest_type in ("local_measure", "state_proposition"):
                        bm = (raw_data or {}).get("mapped_ballot_measure") or {}
                        if bm:
                            ballot_measure = {
                                "title": bm.get("title"),
                                "description": bm.get("description"),
                                "measure_type": bm.get("measure_type"),
                                "full_text": bm.get("full_text"),
                                "fiscal_impact": bm.get("fiscal_impact"),
                                "arguments_for": bm.get("arguments_for", []),
                                "arguments_against": bm.get("arguments_against", []),
                                "full_text_url": bm.get("full_text_url"),
                                "passed": bm.get("passed"),
                                "yes_votes": bm.get("yes_votes"),
                                "no_votes": bm.get("no_votes"),
                                "yes_percentage": bm.get("yes_percentage"),
                                "no_percentage": bm.get("no_percentage"),
                            }

                    race_entry = {
                        "id": c.get("id"),
                        "title": c.get("title"),
                        "contest_type": contest_type,
                        "district_name": c.get("district_name"),
                        "candidates": candidates,
                    }
                    if ballot_measure:
                        race_entry["ballot_measure"] = ballot_measure

                    grouped[level].append(race_entry)

                contest_levels = [
                    {"level": lv, "races": grouped[lv]}
                    for lv in level_order
                    if lv in grouped
                ]

                # Get deadlines and compute next_deadline
                deadlines_raw = civic.storage.get_election_deadlines(election_id)
                deadlines = []
                next_deadline = None
                for d in deadlines_raw:
                    dl_date_val = d.get("deadline_date")
                    if isinstance(dl_date_val, str):
                        dl_date = date_type.fromisoformat(dl_date_val)
                    elif isinstance(dl_date_val, date_type):
                        dl_date = dl_date_val
                    else:
                        dl_date = None

                    is_passed = dl_date < today if dl_date else False
                    deadlines.append({
                        "type": d.get("deadline_type"),
                        "date": dl_date.isoformat() if dl_date else None,
                        "description": d.get("description"),
                        "passed": is_passed,
                    })

                    if dl_date and not is_passed:
                        dl_days = (dl_date - today).days
                        if next_deadline is None or dl_days < next_deadline["days_until"]:
                            next_deadline = {
                                "type": d.get("deadline_type"),
                                "date": dl_date.isoformat(),
                                "description": d.get("description"),
                                "days_until": dl_days,
                            }

                ballot.append({
                    "election_id": election_id,
                    "name": election.get("name"),
                    "date": election_date.isoformat() if election_date else None,
                    "type": election.get("election_type"),
                    "days_until": days_until,
                    "contests": contest_levels,
                    "total_contests": len(contests_raw),
                    "deadlines": deadlines,
                    "next_deadline": next_deadline,
                })

            # Sort by date (nearest first)
            ballot.sort(key=lambda e: e["date"] or "9999-12-31")

            data = {
                "jurisdiction": jid,
                "elections": ballot,
                "total_elections": len(ballot),
            }
        except Exception as e:
            logger.error(f"explore/my_ballot error: {e}")
            data = {"jurisdiction": jid, "elections": [], "error": str(e)}

    else:
        data = {"error": f"Unknown explore target: {what}. Available: jurisdictions, corpora, corpus_schema:{{name}}, actions, capabilities, representatives, my_ballot, schema_version"}

    total_time = int((time.monotonic() - start) * 1000)

    return ExploreResponse(
        data=data,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
        ),
    )


def _action_description(action: str) -> str:
    """Short description for each action."""
    descriptions = {
        "prepare_comment": "Get context for writing a public comment",
        "comment_template": "Get a comment template for an agenda item",
        "comment_guidelines": "Get public comment submission guidelines",
        "prepare_meeting": "Get preparation materials for attending a meeting",
        "prepare_voice": "Prepare a voice attestation",
        "broadcast_voice": "Broadcast a voice attestation to the relay network",
        "prepare_initiative": "Prepare a community initiative",
        "broadcast_initiative": "Broadcast an initiative to the relay network",
        "subscribe": "Subscribe to updates on a topic",
        "draft_federal_comment": "Draft a public comment for a federal rulemaking with rule context and guidance",
        "prepare_federal_comment": "Get submission context (URL, deadline, instructions) for a federal comment",
    }
    return descriptions.get(action, action)
