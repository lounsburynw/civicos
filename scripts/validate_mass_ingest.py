"""
Mass-ingest launch validation pass.

Runs a per-jurisdiction validation across the 15 mass-ingest jurisdictions
(Marin 11 cities + county-marin + city-san-francisco + county-alameda +
city-berkeley). For each jurisdiction:

1. Fetch storage counts (meetings, decisions, transcripts, chunks, issues,
   municipal_code, agenda_items) via the StorageBackend protocol.
2. Fetch vector counts for each corpus via the vector backend.
3. Fetch elections + elected_officials counts via public methods.
   `get_election_count(jid, include_past=True)` is required because the
   default filters future-only; `get_elected_official_count` is not in
   `DataStatus` so a separate call is needed. See feedback_data_status_gaps.
4. Run 3 canonical v2 API queries: "housing", "budget", and an upcoming
   meetings fetch.
5. Emit pass/fail with reason codes.

Pass/fail rules are intentionally conservative: a jurisdiction is
"launch-ready" only if it has >0 meetings, >0 decisions, and all three
queries return without error. Lesser gaps (e.g. missing transcripts, 0
issues) are surfaced as warnings so they don't block launch on their
own, but they're captured for follow-up filing.

Output: stdout summary + JSON at /tmp/mass_ingest_validation.json.

Usage:
    source civicos-env/bin/activate
    python3 scripts/validate_mass_ingest.py
"""

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from civicos import CivicOS
from civicos_services.query.models import SearchRequest, UpcomingRequest
from civicos_services.query.verbs import execute_search, execute_upcoming


JURISDICTIONS = [
    # Marin cities
    "city-san-rafael",
    "city-novato",
    "city-mill-valley",
    "city-san-anselmo",
    "city-fairfax",
    "city-larkspur",
    "city-corte-madera",
    "city-ross",
    "city-belvedere",
    "city-tiburon",
    "city-sausalito",
    # Marin county
    "county-marin",
    # SF
    "city-san-francisco",
    # Alameda
    "county-alameda",
    "city-berkeley",
]

# Corpora to count on the vector side
VECTOR_CORPORA = [
    "decisions",
    "meetings",
    "transcripts",
    "chunks",
    "issues",
    "municipal_code",
    "agenda_items",
]

OUTPUT_PATH = Path("/tmp/mass_ingest_validation.json")


def fetch_storage_counts(civic: CivicOS, jid: str) -> dict:
    """Fetch storage-side counts for a jurisdiction via the public backend API.

    Uses only public StorageBackend methods. For meetings, falls back to
    `len(get_meetings(jid))` since no `get_meeting_count` exists — slightly
    more expensive (~250 row dicts max per jurisdiction) but stays inside
    the protocol surface.
    """
    s = civic.storage
    counts = {}
    # Named count methods on StorageBackend
    count_methods = {
        "decisions": "get_decision_count",
        "transcripts": "get_transcript_count",
        "chunks": "get_chunk_count",
        "issues": "get_issue_count",
        "municipal_code": "get_municipal_code_count",
        "agenda_items": "get_agenda_item_count",
        "videos": "get_video_count",
    }
    for corpus, method in count_methods.items():
        try:
            fn = getattr(s, method, None)
            if fn is None:
                counts[corpus] = None
                continue
            counts[corpus] = fn(jid)
        except Exception as e:
            counts[corpus] = f"ERROR: {e.__class__.__name__}: {e}"
    # Meetings: no public count method, use len(get_meetings()) — public.
    try:
        counts["meetings"] = len(s.get_meetings(jid))
    except Exception as e:
        counts["meetings"] = f"ERROR: {e.__class__.__name__}: {e}"
    return counts


def fetch_elections_and_officials(civic: CivicOS, jid: str) -> dict:
    """Fetch elections and elected_officials counts via public methods.

    `get_election_count(jid, include_past=False)` filters future-only, which
    masks historical elections in diagnostics. We pass `include_past=True`
    to get the full count. `get_elected_official_count` already counts
    current officials with the right `valid_to IS NULL AND deleted_at IS
    NULL` predicate.
    """
    out: dict = {"elections": None, "elected_officials": None}
    s = civic.storage
    try:
        out["elections"] = s.get_election_count(jid, include_past=True)
    except Exception as e:
        out["elections_error"] = f"{e.__class__.__name__}: {e}"
    try:
        out["elected_officials"] = s.get_elected_official_count(jid)
    except Exception as e:
        out["officials_error"] = f"{e.__class__.__name__}: {e}"
    return out


def fetch_vector_counts(civic: CivicOS, jid: str) -> dict:
    """Fetch vector-side counts for each corpus."""
    v = civic.vectors
    counts = {}
    for corpus in VECTOR_CORPORA:
        try:
            counts[corpus] = v.count(jurisdiction_id=jid, corpus_type=corpus)
        except Exception as e:
            counts[corpus] = f"ERROR: {e.__class__.__name__}: {e}"
    return counts


async def run_query(
    civic: CivicOS, jid: str, query: str, corpus: list[str], limit: int = 5
) -> dict:
    """Run a v2 search query and return a compact report."""
    t0 = time.time()
    try:
        req = SearchRequest(query=query, corpus=corpus, limit=limit)
        resp = await execute_search(req, civic, jid)
        dt_ms = int((time.time() - t0) * 1000)
        return {
            "ok": True,
            "query": query,
            "corpus": corpus,
            "num_results": len(resp.results),
            "top_title": (resp.results[0].title if resp.results else None),
            "top_relevance": (
                resp.results[0].relevance if resp.results else None
            ),
            "corpus_status": dict(resp.meta.corpus_status or {}),
            "corpus_counts": dict(resp.meta.corpus_counts or {}),
            "elapsed_ms": dt_ms,
        }
    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        return {
            "ok": False,
            "query": query,
            "corpus": corpus,
            "error": f"{e.__class__.__name__}: {e}",
            "elapsed_ms": dt_ms,
        }


async def run_upcoming(civic: CivicOS, jid: str) -> dict:
    """Run a v2 upcoming query.

    UpcomingResponse uses `results: List[CivicResult]`, not `events`.
    """
    t0 = time.time()
    try:
        req = UpcomingRequest(types=["meetings"], days=60)
        resp = await execute_upcoming(req, civic, jid)
        dt_ms = int((time.time() - t0) * 1000)
        return {
            "ok": True,
            "num_events": len(resp.results),
            "top_title": resp.results[0].title if resp.results else None,
            "elapsed_ms": dt_ms,
        }
    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        return {
            "ok": False,
            "error": f"{e.__class__.__name__}: {e}",
            "elapsed_ms": dt_ms,
        }


def classify(jid: str, report: dict) -> dict:
    """Apply pass/fail rules with reason codes.

    Hard fail: zero meetings AND zero decisions (totally empty), or any
    query raised an exception, or storage meetings > 0 but all three queries
    returned zero results across the board, or any storage count returned
    an error string (DB pool exhaustion, etc.).

    Warn (soft): storage imbalance indicating silent onboarding failures,
    e.g. "decisions ghost" (decisions but no transcripts/chunks/issues/
    officials), or vector coverage gaps.
    """
    storage = report["storage"]
    vectors = report["vectors"]
    queries = report["queries"]
    upcoming = report["upcoming"]
    elect = report["elections_direct"]

    def _n(x):
        return x if isinstance(x, int) else 0

    def _is_err(x):
        return isinstance(x, str) and x.startswith("ERROR:")

    meetings = _n(storage.get("meetings"))
    decisions = _n(storage.get("decisions"))
    transcripts = _n(storage.get("transcripts"))
    chunks = _n(storage.get("chunks"))
    issues = _n(storage.get("issues"))
    officials = _n(elect.get("elected_officials"))

    reasons = []
    warnings = []
    status = "pass"

    # Hard fail: storage call errored
    err_corpora = [c for c, v in storage.items() if _is_err(v)]
    if err_corpora:
        status = "fail"
        reasons.append(f"storage errors on: {', '.join(err_corpora)}")

    # Hard fail: totally empty (only when storage actually returned counts)
    if not err_corpora and meetings == 0 and decisions == 0:
        status = "fail"
        reasons.append("empty: no meetings AND no decisions")

    # Hard fail: any query raised
    for label, q in queries.items():
        if not q["ok"]:
            status = "fail"
            reasons.append(f"query_error[{label}]: {q.get('error','?')}")
    if not upcoming["ok"]:
        status = "fail"
        reasons.append(f"query_error[upcoming]: {upcoming.get('error','?')}")

    # Hard fail: all queries returned zero despite non-empty storage
    all_q_zero = all(
        q["ok"] and (q.get("num_results") or 0) == 0 for q in queries.values()
    )
    if all_q_zero and (meetings > 0 or decisions > 0):
        status = "fail"
        reasons.append("all queries returned zero results despite non-empty storage")

    # Soft warnings: ghost patterns
    if decisions > 20 and transcripts == 0 and chunks == 0 and issues == 0 and officials == 0:
        warnings.append(
            f"ghost: {decisions} decisions but 0 transcripts/chunks/issues/officials"
        )
    # Decision vectors missing despite stored decisions
    dec_vec = vectors.get("decisions")
    if isinstance(dec_vec, int) and decisions > 0 and dec_vec == 0:
        warnings.append(f"no decision vectors ({decisions} decisions stored)")
    # Meeting vectors missing despite stored meetings
    mtg_vec = vectors.get("meetings")
    if isinstance(mtg_vec, int) and meetings > 0 and mtg_vec == 0:
        warnings.append(f"no meeting vectors ({meetings} meetings stored)")
    # Thin transcripts
    if meetings > 20 and transcripts == 0:
        warnings.append(f"zero transcripts despite {meetings} meetings")

    return {"status": status, "reasons": reasons, "warnings": warnings}


async def validate_jurisdiction(jid: str) -> dict:
    """Run the full validation pass for one jurisdiction.

    Creates a fresh CivicOS instance per jurisdiction. The Postgres pool is
    class-level (shared across instances with the same connection string),
    so this is cheap as long as connections are returned properly.

    NB: We can't use a single shared CivicOS because `execute_upcoming` reads
    `civic.jurisdiction` instead of honoring its explicit `jurisdiction`
    parameter (see verbs.py line ~640: `civic.whats_next()`). That bug is
    filed separately as `upcoming_verb_ignores_jurisdiction`.
    """
    report: dict = {"jurisdiction": jid, "error": None}
    try:
        civic = CivicOS(jid)
        backend = type(civic.storage).__name__
        report["backend"] = backend
        if backend != "PostgresBackend":
            report["error"] = (
                f"wrong backend: {backend} (expected PostgresBackend — check .env DATABASE_URL)"
            )
            report["verdict"] = {
                "status": "fail",
                "reasons": ["wrong storage backend"],
                "warnings": [],
            }
            return report

        report["storage"] = fetch_storage_counts(civic, jid)
        report["elections_direct"] = fetch_elections_and_officials(civic, jid)
        report["vectors"] = fetch_vector_counts(civic, jid)

        # Run queries only if there's something to search
        queries: dict[str, dict] = {}
        queries["housing"] = await run_query(
            civic, jid, "housing", ["decisions", "meetings"], limit=5
        )
        queries["budget"] = await run_query(
            civic, jid, "budget", ["decisions", "meetings"], limit=5
        )
        report["queries"] = queries
        report["upcoming"] = await run_upcoming(civic, jid)

        report["verdict"] = classify(jid, report)
    except Exception as e:
        report["error"] = f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}"
        report["verdict"] = {
            "status": "fail",
            "reasons": [f"exception: {e.__class__.__name__}"],
            "warnings": [],
        }
    return report


def fmt_count(v) -> str:
    if isinstance(v, int):
        return f"{v:>7d}"
    if v is None:
        return "   n/a "
    return "   ERR "


def print_report(reports: list[dict]) -> None:
    print()
    print("=" * 100)
    print("MASS-INGEST LAUNCH VALIDATION")
    print("=" * 100)
    print()
    print(
        f"{'jurisdiction':<24} {'mtg':>7} {'dec':>7} {'txc':>7} {'chk':>7} "
        f"{'iss':>7} {'muni':>7} {'off':>5} {'dvec':>7} status"
    )
    print("-" * 100)
    for r in reports:
        jid = r["jurisdiction"]
        s = r.get("storage", {})
        v = r.get("vectors", {})
        e = r.get("elections_direct", {})
        verdict = r.get("verdict", {}).get("status", "?")
        status_label = {"pass": "PASS", "fail": "FAIL"}.get(verdict, "?")
        if r.get("verdict", {}).get("warnings"):
            status_label += " (warn)"
        print(
            f"{jid:<24} "
            f"{fmt_count(s.get('meetings'))} "
            f"{fmt_count(s.get('decisions'))} "
            f"{fmt_count(s.get('transcripts'))} "
            f"{fmt_count(s.get('chunks'))} "
            f"{fmt_count(s.get('issues'))} "
            f"{fmt_count(s.get('municipal_code'))} "
            f"{fmt_count(e.get('elected_officials')):>5} "
            f"{fmt_count(v.get('decisions'))} "
            f"{status_label}"
        )
    print()
    # Failures + warnings detail
    print("DETAIL (failures and warnings)")
    print("-" * 100)
    any_detail = False
    for r in reports:
        jid = r["jurisdiction"]
        verdict = r.get("verdict", {})
        if verdict.get("status") == "fail" or verdict.get("warnings"):
            any_detail = True
            print(f"\n{jid}  [{verdict.get('status','?').upper()}]")
            for reason in verdict.get("reasons", []):
                print(f"  FAIL: {reason}")
            for w in verdict.get("warnings", []):
                print(f"  warn: {w}")
            # Show query samples
            qs = r.get("queries", {})
            for label, q in qs.items():
                if q.get("ok"):
                    nr = q.get("num_results", 0)
                    top = q.get("top_title") or "-"
                    print(
                        f"  q[{label}]: {nr} results, top={top[:60]!r}, "
                        f"{q.get('elapsed_ms','?')}ms"
                    )
                else:
                    print(f"  q[{label}]: ERROR {q.get('error')}")
            u = r.get("upcoming", {})
            if u.get("ok"):
                print(
                    f"  q[upcoming]: {u.get('num_events', 0)} events, "
                    f"top={u.get('top_title') or '-'!r}, {u.get('elapsed_ms','?')}ms"
                )
            else:
                print(f"  q[upcoming]: ERROR {u.get('error')}")
    if not any_detail:
        print("  (no failures or warnings)")
    print()
    # Summary counts
    passes = sum(
        1 for r in reports if r.get("verdict", {}).get("status") == "pass"
    )
    fails = sum(
        1 for r in reports if r.get("verdict", {}).get("status") == "fail"
    )
    warns = sum(
        1
        for r in reports
        if r.get("verdict", {}).get("status") == "pass"
        and r.get("verdict", {}).get("warnings")
    )
    print(
        f"SUMMARY: {passes} pass  ({warns} with warnings),  {fails} fail  — "
        f"{len(reports)} jurisdictions total"
    )
    print()


async def main() -> int:
    reports: list[dict] = []
    for jid in JURISDICTIONS:
        print(f"[validate] {jid}...", flush=True)
        r = await validate_jurisdiction(jid)
        reports.append(r)

    print_report(reports)

    OUTPUT_PATH.write_text(json.dumps(reports, indent=2, default=str))
    print(f"Wrote detailed JSON report to {OUTPUT_PATH}")

    # Exit non-zero if any jurisdiction failed
    any_fail = any(
        r.get("verdict", {}).get("status") == "fail" for r in reports
    )
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
