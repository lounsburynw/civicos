#!/usr/bin/env python3
"""
Turnkey jurisdiction onboarding.

Generates configs locally, then runs Modal ingestion pipeline.
Single command from zero to searchable data.

Usage:
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin
    python scripts/onboard.py --city "San Anselmo" --state CA --county Marin
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --dry-run
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --skip-ingestion
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --force
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


def main():
    parser = argparse.ArgumentParser(description="Turnkey jurisdiction onboarding")
    parser.add_argument("--city", default="", help="City name (e.g., 'Mill Valley')")
    parser.add_argument("--url", default="", help="Direct platform URL")
    parser.add_argument("--state", default="CA", help="Two-letter state code")
    parser.add_argument("--county", default="", help="County name (e.g., 'Marin')")
    parser.add_argument("--level", default="city", help="Jurisdiction level")
    parser.add_argument("--jurisdiction", default="", help="Override jurisdiction ID")
    parser.add_argument("--days-past", type=int, default=365, help="Days of history")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't store")
    parser.add_argument("--skip-ingestion", action="store_true", help="Only generate configs")
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
        slug = re.sub(r"\s+", "-", args.city.strip().lower())
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
        content = yaml_path.read_text()
        if "county:" not in content or "county: null" in content:
            state_upper = args.state.upper() if args.state else ""
            additions = f"""
financial:
  state: {state_upper}
  county: {args.county}

federal_programs:
  hud_grantee: {args.county} County
  hud_relationship: consortium
  notes: "Receives HUD funds via {args.county} County"
"""
            if "metadata:" in content:
                content = content.replace("metadata:", additions + "\nmetadata:")
            else:
                content += "\n" + additions
            yaml_path.write_text(content)
            print(f"  Enriched YAML with county: {args.county}")

    # -------------------------------------------------------------------
    # Phase 2: Check existing data
    # -------------------------------------------------------------------
    print(f"\n[Phase 2] Checking existing data for {jid}...")

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            from civicos.storage.postgres_backend import PostgresBackend
            backend = PostgresBackend(database_url)
            meetings = backend.get_meetings(jid)
            print(f"  Existing meetings: {len(meetings)}")
            decisions = backend.get_decision_count(jid)
            print(f"  Existing decisions: {decisions}")
        except Exception as e:
            print(f"  Could not check: {e}")
    else:
        print("  WARNING: No DATABASE_URL set")

    if args.skip_ingestion:
        print(f"\n[DONE] Configs generated. To ingest:")
        print(f"  modal run scripts/modal_ingest.py --meetings --chunks --agenda --decisions --vectors --jurisdiction {jid} --meetings-days-past {args.days_past}")
        return

    # -------------------------------------------------------------------
    # Phase 3: Run ingestion via Modal
    # -------------------------------------------------------------------
    print(f"\n[Phase 3] Running Modal ingestion pipeline...")
    print(f"  Stages: meetings → chunks → agenda → decisions → vectors")

    # Build modal command
    modal_cmd = [
        "modal", "run", "scripts/modal_ingest.py",
        "--meetings", "--chunks", "--agenda", "--decisions", "--vectors",
        "--jurisdiction", jid,
        "--meetings-days-past", str(args.days_past),
    ]
    if args.dry_run:
        modal_cmd.append("--dry-run")

    print(f"  Command: {' '.join(modal_cmd)}")
    print()

    # Run modal ingestion (streams output)
    result = subprocess.run(modal_cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print(f"\nERROR: Modal ingestion failed (exit code {result.returncode})")
        sys.exit(result.returncode)

    # -------------------------------------------------------------------
    # Phase 4: Verify
    # -------------------------------------------------------------------
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"Onboard Complete: {jid}")
    print(f"Total time: {elapsed:.0f}s")
    print("=" * 60)
    print(f"\nVerify:")
    print(f"  modal run scripts/modal_ingest.py --stats-only --jurisdiction {jid}")


if __name__ == "__main__":
    main()
