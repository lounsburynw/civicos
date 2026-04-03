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

            # Type breakdown
            cur.execute("SELECT title, COUNT(*) as cnt FROM meetings GROUP BY title ORDER BY cnt DESC")
            corpus["details"]["types"] = {row["title"]: row["cnt"] for row in cur.fetchall()}

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
