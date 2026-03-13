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

CORPUS_TIMEOUT_S = 10


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
                        civic, jid, request.query, fetch_limit,
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
                # Comment periods from upcoming meetings with comment-eligible items
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
                corpus_status["comment_periods"] = "ok"

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

    return UpcomingResponse(
        results=results,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
            corpora_searched=request.types,
            corpus_counts={t: sum(1 for r in results if r.type == t or t in (r.type + "s")) for t in request.types},
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
    """Execute context assembly for a specific item."""
    start = time.monotonic()

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

    return ContextResponse(
        context=context_data,
        meta=ResponseMeta(
            schema_version=SCHEMA_VERSION,
            query_time_ms=total_time,
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
            status = DataStatus(civic._storage, civic._vectors, jid)
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
                "311 issues, budgets) for AI agents and developers. Use civic.explore to "
                "discover available data, civic.search for queries, civic.upcoming for "
                "temporal events, civic.context for deep item context, and civic.act for "
                "participation actions."
            ),
        }

    else:
        data = {"error": f"Unknown explore target: {what}. Available: jurisdictions, corpora, corpus_schema:{{name}}, actions, capabilities, schema_version"}

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
    }
    return descriptions.get(action, action)
