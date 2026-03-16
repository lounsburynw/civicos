#!/usr/bin/env python3
"""
Turnkey jurisdiction onboarding.

Generates configs locally, runs a validation sample, then runs full ingestion.
Single command from zero to searchable data.

Usage:
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin
    python scripts/onboard.py --city "San Anselmo" --state CA --county Marin
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --dry-run
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --skip-ingestion
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --force
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --no-validate
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Ensure we can import civicos packages
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos-extraction" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos-services" / "src"))

SAMPLE_DAYS = 30


def _get_data_counts(database_url: str, jid: str) -> dict:
    """Query PostgreSQL for corpus counts."""
    from civicos.storage.postgres_backend import PostgresBackend
    backend = PostgresBackend(database_url)
    meetings = backend.get_meetings(jid)
    meeting_count = len(meetings)
    decision_count = backend.get_decision_count(jid)
    chunk_count = backend.get_chunk_count(jid)
    agenda_item_count = backend.get_agenda_item_count(jid)

    return {
        "meetings": meeting_count,
        "decisions": decision_count,
        "chunks": chunk_count,
        "agenda_items": agenda_item_count,
    }


def _quality_report(counts: dict, label: str = "") -> list:
    """Generate quality report lines with red flag detection.

    Returns list of report lines and a list of red flags.
    """
    lines = []
    red_flags = []
    meetings = counts["meetings"]

    header = f"Quality Report{f' ({label})' if label else ''}"
    lines.append(f"\n  {header}")
    lines.append(f"  {'─' * len(header)}")
    lines.append(f"  Meetings:      {meetings}")
    lines.append(f"  Chunks:        {counts['chunks']}")
    lines.append(f"  Agenda items:  {counts['agenda_items']}")
    lines.append(f"  Decisions:     {counts['decisions']}")

    if meetings == 0:
        red_flags.append("meetings = 0 → Extraction config is broken (bad view ID, wrong platform)")
        lines.append(f"\n  ⚠ RED FLAG: {red_flags[-1]}")
        return lines, red_flags

    chunks_per = counts["chunks"] / meetings
    agenda_per = counts["agenda_items"] / meetings
    decisions_per = counts["decisions"] / meetings
    lines.append(f"\n  Ratios (vs San Rafael baseline):")
    lines.append(f"    chunks/meeting:       {chunks_per:.1f}  (baseline: ~52)")
    lines.append(f"    agenda_items/meeting: {agenda_per:.1f}  (baseline: ~3)")
    lines.append(f"    decisions/meeting:    {decisions_per:.2f}  (baseline: ~0.45)")

    if chunks_per == 0:
        red_flags.append(
            "chunks/meeting = 0 → Platform uses HTML agendas, not PDFs. "
            "Chunk search won't work for this jurisdiction."
        )
    if agenda_per == 0:
        red_flags.append(
            "agenda_items/meeting = 0 → LLM extraction failing. "
            "Check if agendas are behind auth or unsupported format."
        )
    if decisions_per == 0:
        red_flags.append(
            "decisions/meeting = 0 → Minutes are too thin or not posted. "
            "Decision search won't work."
        )
    elif decisions_per < 0.1:
        red_flags.append(
            f"decisions/meeting = {decisions_per:.2f} (low) → Minutes may be thin. "
            "Decision quality may be limited."
        )

    if red_flags:
        lines.append(f"\n  ⚠ RED FLAGS:")
        for flag in red_flags:
            lines.append(f"    • {flag}")
    else:
        lines.append(f"\n  ✓ All quality checks passed")

    return lines, red_flags


def _run_modal_ingestion(jid: str, days_past: int, dry_run: bool = False,
                         stages: str = "all") -> int:
    """Run Modal ingestion and return exit code."""
    modal_cmd = ["modal", "run", "scripts/modal_ingest.py"]

    if stages == "all":
        modal_cmd.extend(["--meetings", "--chunks", "--agenda", "--decisions", "--vectors"])
    else:
        for stage in stages.split(","):
            modal_cmd.append(f"--{stage.strip()}")

    modal_cmd.extend(["--jurisdiction", jid, "--meetings-days-past", str(days_past)])
    if dry_run:
        modal_cmd.append("--dry-run")

    print(f"  Command: {' '.join(modal_cmd)}")
    print()
    result = subprocess.run(modal_cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Turnkey jurisdiction onboarding")
    parser.add_argument("--city", default="", help="City name (e.g., 'Mill Valley')")
    parser.add_argument("--url", default="", help="Direct platform URL")
    parser.add_argument("--state", default="CA", help="Two-letter state code")
    parser.add_argument("--county", default="", help="County name (e.g., 'Marin')")
    parser.add_argument("--level", default="city", help="Jurisdiction level")
    parser.add_argument("--jurisdiction", default="", help="Override jurisdiction ID")
    parser.add_argument("--days-past", type=int, default=365, help="Days of history")
    parser.add_argument("--sample-days", type=int, default=SAMPLE_DAYS,
                        help="Days for validation sample (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't store")
    parser.add_argument("--skip-ingestion", action="store_true", help="Only generate configs")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip validation gate, run full ingestion immediately")
    parser.add_argument("--force", action="store_true", help="Regenerate configs")
    args = parser.parse_args()

    if not args.city and not args.url:
        parser.error("Provide --city 'City Name' or --url 'https://...'")

    start_time = time.time()

    print("\n" + "=" * 60)
    print("CivicOS Turnkey Onboard")
    print("=" * 60)
    if args.city:
        print(f"City: {args.city}")
    if args.url:
        print(f"URL: {args.url}")
    print(f"State: {args.state}, County: {args.county or '(auto-detect)'}")
    print(f"Level: {args.level}")
    if args.jurisdiction:
        print(f"Jurisdiction ID: {args.jurisdiction}")
    print(f"Days of history: {args.days_past}")
    if not args.no_validate:
        print(f"Validation sample: {args.sample_days} days")
    print(f"Dry run: {args.dry_run}")
    print("=" * 60)

    # -------------------------------------------------------------------
    # Phase 1: Generate configs locally
    # -------------------------------------------------------------------
    print("\n[Phase 1] Config generation...")

    from dotenv import load_dotenv
    load_dotenv()

    # Derive jurisdiction ID
    jid = args.jurisdiction
    if not jid and args.city:
        # Normalize: lowercase, strip, collapse whitespace/special chars to hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", args.city.strip().lower()).strip("-")
        jid = f"{args.level}-{slug}"

    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"

    configs_exist = extraction_path.exists() and yaml_path.exists()

    if configs_exist and not args.force:
        print(f"  Configs already exist for {jid}:")
        print(f"    Extraction: {extraction_path}")
        print(f"    YAML: {yaml_path}")
        print(f"  Skipping generation (use --force to regenerate)")
    else:
        from civicos_extraction.onboard import onboard_jurisdiction

        result = onboard_jurisdiction(
            url=args.url or "",
            jurisdiction_id=args.jurisdiction or None,
            city_name=args.city or None,
            state=args.state,
            level=args.level,
            generate_yaml=True,
            generate_registries=False,
            validate=1,
            run_pipeline=False,
            index_vectors=False,
            on_progress=lambda step, msg: print(f"  [{step}] {msg}"),
        )

        if not result.success:
            print(f"\nERROR: Config generation failed")
            for err in result.errors:
                print(f"  - {err}")
            sys.exit(1)

        jid = result.jurisdiction_id
        print(f"\n  Jurisdiction ID: {jid}")
        print(f"  Extraction config: {result.config_path}")
        if result.discovered_bodies:
            print(f"  Discovered {len(result.discovered_bodies)} meeting bodies:")
            for name, view_id in result.discovered_bodies.items():
                print(f"    - {name} (view {view_id})")

    # Enrich YAML with county if provided and missing
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    if args.county and yaml_path.exists():
        import yaml as _yaml
        with open(yaml_path) as f:
            data = _yaml.safe_load(f) or {}
        needs_update = False
        if "financial" not in data or not data.get("financial", {}).get("county"):
            state_upper = args.state.upper() if args.state else ""
            data.setdefault("financial", {})
            data["financial"]["state"] = state_upper
            data["financial"]["county"] = args.county
            needs_update = True
        if "federal_programs" not in data:
            data["federal_programs"] = {
                "hud_grantee": f"{args.county} County",
                "hud_relationship": "consortium",
                "notes": f"Receives HUD funds via {args.county} County",
            }
            needs_update = True
        if needs_update:
            with open(yaml_path, "w") as f:
                _yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            print(f"  Enriched YAML with county: {args.county}")

    # -------------------------------------------------------------------
    # Phase 2: Check existing data
    # -------------------------------------------------------------------
    print(f"\n[Phase 2] Checking existing data for {jid}...")

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            counts_before = _get_data_counts(database_url, jid)
            print(f"  Existing meetings:      {counts_before['meetings']}")
            print(f"  Existing chunks:        {counts_before['chunks']}")
            print(f"  Existing agenda items:  {counts_before['agenda_items']}")
            print(f"  Existing decisions:     {counts_before['decisions']}")
        except Exception as e:
            print(f"  Could not check: {e}")
            counts_before = None
    else:
        print("  WARNING: No DATABASE_URL set")
        counts_before = None

    if args.skip_ingestion:
        print(f"\n[DONE] Configs generated. To ingest:")
        print(f"  modal run scripts/modal_ingest.py --meetings --chunks --agenda "
              f"--decisions --vectors --jurisdiction {jid} "
              f"--meetings-days-past {args.days_past}")
        return

    # -------------------------------------------------------------------
    # Phase 2.5: Validation gate (sample before full backfill)
    # -------------------------------------------------------------------
    if not args.no_validate and args.days_past > args.sample_days:
        print(f"\n[Phase 2.5] Validation gate ({args.sample_days}-day sample)...")
        print(f"  Running sample ingestion to check data quality before full backfill.")

        rc = _run_modal_ingestion(jid, args.sample_days, args.dry_run)
        if rc != 0:
            print(f"\nERROR: Sample ingestion failed (exit code {rc})")
            sys.exit(rc)

        # Check quality after sample
        if database_url:
            try:
                sample_counts = _get_data_counts(database_url, jid)
                report_lines, red_flags = _quality_report(sample_counts,
                                                          f"{args.sample_days}-day sample")
                for line in report_lines:
                    print(line)

                if red_flags:
                    print(f"\n  {len(red_flags)} quality issue(s) detected in sample.")
                    print(f"  Full backfill ({args.days_past} days) will cost LLM tokens.")
                    print(f"  Proceeding anyway — review red flags above after completion.")
                    print(f"  (Use --no-validate to skip this check)")
                else:
                    print(f"\n  Sample looks good. Proceeding to full backfill...")
            except Exception as e:
                print(f"  Could not run quality check: {e}")
                print(f"  Proceeding with full backfill anyway...")

    # -------------------------------------------------------------------
    # Phase 3: Run full ingestion via Modal
    # -------------------------------------------------------------------
    print(f"\n[Phase 3] Running Modal ingestion pipeline...")
    print(f"  Stages: meetings → chunks → agenda → decisions → vectors")
    print(f"  Days: {args.days_past}")

    rc = _run_modal_ingestion(jid, args.days_past, args.dry_run)
    if rc != 0:
        print(f"\nERROR: Modal ingestion failed (exit code {rc})")
        sys.exit(rc)

    # -------------------------------------------------------------------
    # Phase 4: Quality report
    # -------------------------------------------------------------------
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"Onboard Complete: {jid}")
    print(f"Total time: {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print("=" * 60)

    if database_url:
        try:
            final_counts = _get_data_counts(database_url, jid)
            report_lines, red_flags = _quality_report(final_counts, "final")
            for line in report_lines:
                print(line)

            # Show delta from before
            if counts_before:
                print(f"\n  Delta from start:")
                for key in ["meetings", "chunks", "agenda_items", "decisions"]:
                    delta = final_counts[key] - counts_before[key]
                    if delta > 0:
                        print(f"    {key}: +{delta}")

            if red_flags:
                print(f"\n  Action items:")
                print(f"    • Review red flags above before relying on this data")
                print(f"    • chunks=0 may require HTML agenda extraction (not yet supported)")
                print(f"    • Low decisions may improve as more minutes are posted")
        except Exception as e:
            print(f"\n  Could not generate quality report: {e}")
            print(f"\n  Verify manually:")
            print(f"    modal run scripts/modal_ingest.py --stats-only --jurisdiction {jid}")
    else:
        print(f"\nVerify:")
        print(f"  modal run scripts/modal_ingest.py --stats-only --jurisdiction {jid}")


if __name__ == "__main__":
    main()
