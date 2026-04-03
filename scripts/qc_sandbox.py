#!/usr/bin/env python3
"""
QC (quality check) for sandbox onboarding data.

Validates meetings, issues, elections, and officials in a sandbox SQLite
database against expected baselines. Outputs structured JSON for headless
automation or human-readable text.

Usage:
    python scripts/qc_sandbox.py --jurisdiction city-novato
    python scripts/qc_sandbox.py --jurisdiction city-novato --json
    python scripts/qc_sandbox.py --jurisdiction city-novato --db /path/to/db.sqlite
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Load .env for LLM API keys (needed for content review)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def qc_sandbox(db_path: str, jurisdiction: str) -> dict:
    """Run all QC checks on a sandbox database. Returns structured results."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    results = {
        "jurisdiction": jurisdiction,
        "database": db_path,
        "pass": True,
        "corpora": {},
        "warnings": [],
        "errors": [],
    }

    # --- MEETINGS ---
    corpus = {"count": 0, "pass": True, "details": {}, "warnings": [], "errors": []}
    try:
        cur.execute("SELECT COUNT(*) FROM meetings")
        count = cur.fetchone()[0]
        corpus["count"] = count

        if count == 0:
            corpus["pass"] = False
            # Provide actionable diagnostics
            config_path = PROJECT_ROOT / "data" / "extraction" / f"{jurisdiction}.json"
            if config_path.exists():
                import json as _json
                with open(config_path) as _cf:
                    _config = _json.load(_cf)
                _archives = _config.get("archives", {})
                _vid = _config.get("metadata", {}).get("default_view_id", "?")
                _base = _config.get("base_url", "?")
                _stype = _config.get("source_type", "?")
                if not _archives:
                    corpus["errors"].append(
                        f"No meetings found. Archives is empty in extraction config. "
                        f"Platform={_stype}, base_url={_base}, default_view_id={_vid}. "
                        f"Fix: find correct view_id and set archives + default_view_id."
                    )
                else:
                    corpus["errors"].append(
                        f"No meetings found despite archives={_archives}. "
                        f"Check that view_id={_vid} at {_base} returns meeting data, "
                        f"and that column_map matches the page layout."
                    )
            else:
                corpus["errors"].append(
                    f"No meetings found and no extraction config at {config_path}. "
                    f"Run onboard.py --skip-ingestion first."
                )
        else:
            cur.execute("SELECT MIN(meeting_datetime), MAX(meeting_datetime) FROM meetings")
            row = cur.fetchone()
            corpus["details"]["date_range"] = [row[0], row[1]]

            # Agenda coverage
            cur.execute('SELECT COUNT(*) FROM meetings WHERE agenda_url IS NOT NULL AND agenda_url != ""')
            with_agenda = cur.fetchone()[0]
            corpus["details"]["agenda_coverage"] = round(with_agenda / count * 100, 1)
            if with_agenda / count < 0.5:
                corpus["warnings"].append(f"Low agenda coverage: {with_agenda}/{count} ({with_agenda/count*100:.0f}%)")

            # Video coverage
            cur.execute('SELECT COUNT(*) FROM meetings WHERE video_url IS NOT NULL AND video_url != ""')
            with_video = cur.fetchone()[0]
            corpus["details"]["video_coverage"] = round(with_video / count * 100, 1)

            # Body type breakdown (use meeting_type if available, fall back to title)
            cur.execute("""
                SELECT COALESCE(meeting_type, title) as body, COUNT(*) as cnt
                FROM meetings GROUP BY body ORDER BY cnt DESC
            """)
            corpus["details"]["types"] = {row["body"]: row["cnt"] for row in cur.fetchall()}

            # Duplicate check
            cur.execute("SELECT COUNT(*) FROM (SELECT title, meeting_datetime, COUNT(*) as cnt FROM meetings GROUP BY title, meeting_datetime HAVING cnt > 1)")
            dupes = cur.fetchone()[0]
            if dupes:
                corpus["warnings"].append(f"{dupes} duplicate meeting(s) detected")

            # Missing dates
            cur.execute("SELECT COUNT(*) FROM meetings WHERE meeting_datetime IS NULL")
            no_date = cur.fetchone()[0]
            if no_date:
                corpus["errors"].append(f"{no_date} meetings without dates")
                corpus["pass"] = False

    except sqlite3.OperationalError:
        corpus["errors"].append("meetings table not found")
        corpus["pass"] = False

    results["corpora"]["meetings"] = corpus

    # --- ISSUES ---
    corpus = {"count": 0, "pass": True, "details": {}, "warnings": [], "errors": []}
    try:
        cur.execute("SELECT COUNT(*) FROM issues")
        count = cur.fetchone()[0]
        corpus["count"] = count

        if count > 0:
            cur.execute("SELECT MIN(created_at), MAX(created_at) FROM issues")
            row = cur.fetchone()
            corpus["details"]["date_range"] = [row[0], row[1]]

            cur.execute("SELECT status, COUNT(*) as cnt FROM issues GROUP BY status ORDER BY cnt DESC")
            corpus["details"]["statuses"] = {row["status"]: row["cnt"] for row in cur.fetchall()}

        if count < 20:
            corpus["warnings"].append(f"Only {count} issues — SeeClickFix may have limited coverage")

    except sqlite3.OperationalError:
        corpus["warnings"].append("issues table not found (may not be configured)")

    results["corpora"]["issues"] = corpus

    # --- ELECTIONS ---
    corpus = {"count": 0, "pass": True, "details": {}, "warnings": [], "errors": []}
    try:
        cur.execute("SELECT COUNT(*) FROM elections")
        count = cur.fetchone()[0]
        corpus["count"] = count

        if count > 0:
            cur.execute("SELECT MIN(election_date), MAX(election_date) FROM elections")
            row = cur.fetchone()
            corpus["details"]["date_range"] = [row[0], row[1]]

            cur.execute("SELECT election_type, COUNT(*) as cnt FROM elections GROUP BY election_type ORDER BY cnt DESC")
            corpus["details"]["types"] = {row["election_type"]: row["cnt"] for row in cur.fetchall()}

            cur.execute("SELECT source, COUNT(*) as cnt FROM elections GROUP BY source ORDER BY cnt DESC")
            corpus["details"]["sources"] = {row["source"]: row["cnt"] for row in cur.fetchall()}

            # Duplicate check
            cur.execute("SELECT COUNT(*) FROM (SELECT id, COUNT(*) as cnt FROM elections GROUP BY id HAVING cnt > 1)")
            dupes = cur.fetchone()[0]
            if dupes:
                corpus["warnings"].append(f"{dupes} duplicate election ID(s)")
        else:
            corpus["warnings"].append("No elections — check election_sources in extraction config")

    except sqlite3.OperationalError:
        corpus["warnings"].append("elections table not found")

    results["corpora"]["elections"] = corpus

    # --- ELECTION CONTESTS ---
    corpus = {"count": 0, "pass": True, "details": {}, "warnings": [], "errors": []}
    try:
        cur.execute("SELECT COUNT(*) FROM election_contests")
        count = cur.fetchone()[0]
        corpus["count"] = count

        if count > 0:
            cur.execute("SELECT contest_type, COUNT(*) as cnt FROM election_contests GROUP BY contest_type ORDER BY cnt DESC")
            corpus["details"]["types"] = {row["contest_type"]: row["cnt"] for row in cur.fetchall()}

            # Duplicate check
            cur.execute("SELECT COUNT(*) FROM (SELECT id, COUNT(*) as cnt FROM election_contests GROUP BY id HAVING cnt > 1)")
            dupes = cur.fetchone()[0]
            if dupes:
                corpus["warnings"].append(f"{dupes} duplicate contest ID(s)")

    except sqlite3.OperationalError:
        pass  # Table may not exist

    results["corpora"]["contests"] = corpus

    # --- ELECTED OFFICIALS ---
    corpus = {"count": 0, "pass": True, "details": {}, "warnings": [], "errors": []}
    try:
        cur.execute("SELECT COUNT(*) FROM elected_officials")
        count = cur.fetchone()[0]
        corpus["count"] = count

        if count > 0:
            cur.execute("SELECT seat, COUNT(*) as cnt FROM elected_officials GROUP BY seat ORDER BY cnt DESC")
            corpus["details"]["seats"] = {row["seat"]: row["cnt"] for row in cur.fetchall()}

    except sqlite3.OperationalError:
        pass

    results["corpora"]["officials"] = corpus

    # --- OFFICIALS WEB VERIFICATION ---
    # Cross-reference extracted officials against web search results.
    # Catches stale officials, missing names, and wrong role assignments.
    officials_verification = _verify_officials_via_web(db_path, jurisdiction)
    if officials_verification:
        results["officials_verification"] = officials_verification
        if officials_verification.get("warnings"):
            results.setdefault("warnings", []).extend(
                f"[officials_verify] {w}" for w in officials_verification["warnings"]
            )
        if officials_verification.get("errors"):
            results.setdefault("errors", []).extend(
                f"[officials_verify] {e}" for e in officials_verification["errors"]
            )

    # --- STATUS CONSISTENCY CHECK (deterministic) ---
    _status_check = _check_status_consistency(db_path)
    if _status_check.get("warnings"):
        results.setdefault("warnings", []).extend(
            f"[status] {w}" for w in _status_check["warnings"]
        )
    if _status_check.get("errors"):
        results.setdefault("errors", []).extend(
            f"[status] {e}" for e in _status_check["errors"]
        )

    # --- LLM CONTENT REVIEW ---
    # Sample meetings and ask an LLM to validate content quality.
    # Catches garbled titles, bad body names, jurisdiction leakage,
    # and URL issues that quantitative checks miss.
    llm_review = _llm_content_review(db_path, jurisdiction)
    if llm_review:
        results["llm_review"] = llm_review
        if llm_review.get("warnings"):
            results["warnings"].extend(
                f"[llm_review] {w}" for w in llm_review["warnings"]
            )
        if llm_review.get("errors"):
            results["errors"].extend(
                f"[llm_review] {e}" for e in llm_review["errors"]
            )
            if llm_review.get("pass") is False:
                results["pass"] = False

    # --- OVERALL PASS/FAIL ---
    for name, corpus in results["corpora"].items():
        if not corpus["pass"]:
            results["pass"] = False
        results["warnings"].extend(
            f"[{name}] {w}" for w in corpus.get("warnings", [])
        )
        results["errors"].extend(
            f"[{name}] {e}" for e in corpus.get("errors", [])
        )

    db.close()
    return results


_LLM_REVIEW_PROMPT = """\
You are a data quality reviewer for a civic data platform. Review the following \
sample of meeting records scraped from {jurisdiction}'s municipal website.

Check each record for:
1. **Title quality** — Is it a real meeting title, or garbled/truncated/HTML artifacts? \
Titles should be human-readable body names, possibly with a date or descriptor.
2. **Body name** — Does the meeting_type look like a real government body \
(City Council, Planning Commission, etc.)? Flag generic types like "Meeting" or \
overly long names that include dates or document descriptions.
3. **Jurisdiction match** — Do the meetings look like they belong to {jurisdiction}? \
Flag if titles reference a completely different city/county. Note: the jurisdiction_id format \
(city-fairfax) does NOT need to match the website domain (townoffairfaxca.gov) — \
these are different naming conventions for the same city.
4. **URL validity** — Do the agenda/source URLs look plausible (proper domain, not placeholder)?

Do NOT check date-vs-status consistency — that is validated separately.

Records to review:
{records}

Respond with ONLY a JSON object (no markdown fences):
{{
  "pass": true/false,
  "issues": ["list of specific problems found, empty if all good"],
  "warnings": ["minor concerns that don't fail QC"],
  "sample_size": {sample_size},
  "summary": "one sentence overall assessment"
}}

Set pass=false only for clear data quality problems (garbled content, wrong jurisdiction). \
Minor issues like generic body names are warnings, not failures.\
"""


_OFFICIALS_VERIFY_PROMPT = """\
You are verifying elected officials data for {jurisdiction}. We store \
officials at multiple levels: city council/town council, school board \
(Governing Board Members), AND county supervisors. This is intentional — \
all these officials represent residents of this jurisdiction.

I searched the web for "{search_query}" and got these snippets:
{search_results}

Compare our extracted officials against what the web snippets show. Check:
1. **Missing council members** — does the web mention council members we don't have?
2. **Stale officials** — do we list anyone the web says is no longer serving?
3. **Mayor/Vice Mayor** — does the web identify who is mayor? We may only have "Council Member".
4. **Name accuracy** — are the names spelled correctly?

Our extracted officials:
{officials_list}

Respond with ONLY a JSON object (no markdown fences):
{{
  "pass": true/false,
  "verified_count": <number of officials confirmed by web results>,
  "issues": ["specific discrepancies between our data and web results"],
  "warnings": ["minor concerns or things we couldn't verify"],
  "summary": "one sentence assessment"
}}

Set pass=false only if the web clearly shows we're missing current officials \
or listing people who left office. If the web snippets are too limited to verify, \
set pass=true with a warning.\
"""


def _verify_officials_via_web(db_path: str, jurisdiction: str) -> dict:
    """Cross-reference extracted officials against web search results."""
    import os

    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return {}

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    try:
        cur.execute("""
            SELECT name, seat FROM elected_officials
            WHERE seat LIKE '%Council%' OR seat LIKE '%Mayor%'
               OR seat LIKE '%Supervisor%' OR seat LIKE '%Board%'
            ORDER BY seat, name
        """)
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        db.close()
        return {}

    db.close()

    if not rows:
        return {}

    officials_list = "\n".join(f"- {r['name']} ({r['seat']})" for r in rows)

    # Derive city name from jurisdiction_id
    city_name = jurisdiction.replace("city-", "").replace("-", " ").title()
    search_query = f"{city_name} city council members"

    # Web search via DuckDuckGo HTML (doesn't require JS/Playwright)
    try:
        import requests as _req
        from bs4 import BeautifulSoup as _BS
        r = _req.get(
            "https://html.duckduckgo.com/html/",
            params={"q": search_query},
            headers={"User-Agent": "CivicOS-QC/1.0"},
            timeout=10,
        )
        if r.status_code == 200:
            soup = _BS(r.text, "html.parser")
            # Extract search result snippets
            results = soup.select(".result__snippet")
            search_results = "\n".join(r.get_text(strip=True)[:200] for r in results[:5])
            if not search_results:
                search_results = "(no search results)"
        else:
            search_results = f"(search returned {r.status_code})"
    except Exception as e:
        search_results = f"(web search failed: {e})"

    if "(web search" in search_results:
        return {"warnings": ["Officials web verification skipped — Playwright not available"]}

    # Ask LLM to compare
    try:
        from civicos_services.core.llm_provider import get_model_for_task
        import re

        provider = get_model_for_task("navigation")
        prompt = _OFFICIALS_VERIFY_PROMPT.format(
            jurisdiction=jurisdiction,
            search_query=search_query,
            search_results=search_results,
            officials_list=officials_list,
        )

        result = provider.complete(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = result.content.strip()

        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"warnings": [f"Officials verification returned unparseable response"]}

    except Exception as e:
        return {"warnings": [f"Officials verification failed: {e}"]}


def _check_status_consistency(db_path: str) -> dict:
    """Deterministic check: does meeting status match the date?

    Past meetings should be completed/cancelled, future should be scheduled.
    """
    from datetime import datetime, timezone

    result: dict = {"warnings": [], "errors": []}
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    now = datetime.now(timezone.utc)

    try:
        cur.execute("SELECT meeting_datetime, status, title FROM meetings WHERE status IS NOT NULL")
        future_completed = 0
        past_scheduled = 0
        for row in cur.fetchall():
            dt_str = row["meeting_datetime"]
            status = row["status"]
            if not dt_str:
                continue
            try:
                dt = datetime.fromisoformat(dt_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if dt > now and status == "completed":
                future_completed += 1
            elif dt < now and status == "scheduled":
                past_scheduled += 1

        if future_completed:
            result["errors"].append(
                f"{future_completed} future meeting(s) marked as 'completed'"
            )
        if past_scheduled:
            result["warnings"].append(
                f"{past_scheduled} past meeting(s) still marked as 'scheduled'"
            )

    except sqlite3.OperationalError:
        pass

    db.close()
    return result


def _llm_content_review(db_path: str, jurisdiction: str) -> dict:
    """Sample meetings and validate content with an LLM.

    Returns a dict with pass/warnings/errors, or empty dict if LLM unavailable.
    """
    import os

    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return {}

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # Sample up to 5 meetings spread across the date range:
    # newest, oldest, and 3 evenly spaced in between.
    try:
        cur.execute("SELECT COUNT(*) FROM meetings")
        total = cur.fetchone()[0]
        if total <= 5:
            cur.execute("""
                SELECT id, title, meeting_datetime, jurisdiction_id,
                       meeting_type, status, agenda_url, source_url, source_platform
                FROM meetings ORDER BY meeting_datetime
            """)
        else:
            # Pick indices spread across the range
            offsets = [0, total // 4, total // 2, 3 * total // 4, total - 1]
            cur.execute(f"""
                SELECT id, title, meeting_datetime, jurisdiction_id,
                       meeting_type, status, agenda_url, source_url, source_platform
                FROM (
                    SELECT *, ROW_NUMBER() OVER (ORDER BY meeting_datetime) - 1 AS rn
                    FROM meetings
                )
                WHERE rn IN ({','.join(str(o) for o in offsets)})
                ORDER BY meeting_datetime
            """)
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        db.close()
        return {}

    db.close()

    if not rows:
        return {}

    # Format records for the prompt.
    # Pre-compute relative date labels so the LLM doesn't need to reason
    # about what year it is. Models hallucinate that 2026 is "the future"
    # even when told today's date.
    from datetime import datetime as _dt, timezone as _tz
    _now = _dt.now(_tz.utc)

    records = []
    for r in rows:
        # Compute relative label
        dt_str = r["meeting_datetime"] or ""
        relative = ""
        try:
            dt = _dt.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            delta = (_now - dt).days
            if delta > 0:
                relative = f" ({delta} days ago)"
            elif delta < 0:
                relative = f" ({-delta} days from now)"
            else:
                relative = " (today)"
        except (ValueError, TypeError):
            pass

        records.append(
            f"- id={r['id']}\n"
            f"  title={r['title']}\n"
            f"  meeting_datetime={dt_str}{relative}\n"
            f"  jurisdiction_id={r['jurisdiction_id']}\n"
            f"  meeting_type={r['meeting_type']}\n"
            f"  status={r['status']}\n"
            f"  agenda_url={r['agenda_url']}\n"
            f"  source_url={r['source_url']}\n"
            f"  source_platform={r['source_platform']}"
        )
    records_text = "\n".join(records)

    prompt = _LLM_REVIEW_PROMPT.format(
        jurisdiction=jurisdiction,
        records=records_text,
        sample_size=len(rows),
    )

    try:
        from civicos_services.core.llm_provider import get_model_for_task

        provider = get_model_for_task("navigation")
        messages = [{"role": "user", "content": prompt}]
        result = provider.complete(messages, temperature=0.1)
        text = result.content.strip()

        # Parse JSON from response (may have markdown fences)
        import re
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            review = json.loads(json_match.group())
            return review
        else:
            return {"warnings": [f"LLM review returned unparseable response: {text[:200]}"]}

    except Exception as e:
        return {"warnings": [f"LLM content review skipped: {e}"]}


def format_report(results: dict) -> str:
    """Format QC results as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"QC Report: {results['jurisdiction']}")
    lines.append("=" * 60)
    lines.append("")

    for name, corpus in results["corpora"].items():
        status = "PASS" if corpus["pass"] else "FAIL"
        lines.append(f"  {name:20s} {corpus['count']:>6d}  [{status}]")

    lines.append("")

    if results["warnings"]:
        lines.append("Warnings:")
        for w in results["warnings"]:
            lines.append(f"  - {w}")
        lines.append("")

    if results["errors"]:
        lines.append("Errors:")
        for e in results["errors"]:
            lines.append(f"  - {e}")
        lines.append("")

    overall = "PASS" if results["pass"] else "FAIL"
    lines.append(f"Overall: {overall}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="QC sandbox onboarding data")
    parser.add_argument("--jurisdiction", "-j", required=True, help="Jurisdiction ID")
    parser.add_argument("--db", help="SQLite path (default: data/sandbox_{jurisdiction}.sqlite)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    db_path = args.db or str(PROJECT_ROOT / "data" / f"sandbox_{args.jurisdiction}.sqlite")

    if not Path(db_path).exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    results = qc_sandbox(db_path, args.jurisdiction)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_report(results))

    sys.exit(0 if results["pass"] else 1)


if __name__ == "__main__":
    main()
