#!/usr/bin/env python3
"""
Ingest federal programs data from JSON files into PostgreSQL.

Migrates data from:
- data/funding/federal/*.json (national program definitions)
- data/jurisdiction_overrides/*.json (jurisdiction-specific allocations)

Usage:
    python scripts/ingest_federal_programs.py
    python scripts/ingest_federal_programs.py --dry-run
    python scripts/ingest_federal_programs.py --jurisdiction city-san-rafael

SESSION 505: Created for federal_programs_postgres_migration
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import os


def load_federal_programs_json(data_dir: Path) -> List[Dict[str, Any]]:
    """Load all federal programs from data/funding/federal/*.json."""
    programs = []
    federal_dir = data_dir / "funding" / "federal"

    if not federal_dir.exists():
        print(f"Warning: {federal_dir} does not exist")
        return programs

    for json_file in federal_dir.glob("*.json"):
        # Skip audit copies
        if "_audit" in json_file.name:
            continue

        print(f"  Loading {json_file.name}...")
        with open(json_file) as f:
            data = json.load(f)

        topic = data.get("topic", json_file.stem)
        data_sources = data.get("data_sources", [])
        verification_status = data.get("verification_status", "DRAFT")

        for program_id, prog_data in data.get("programs", {}).items():
            programs.append({
                "program_id": program_id,
                "program_name": prog_data.get("program_name", program_id),
                "administering_agency": prog_data.get("administering_agency", "Unknown"),
                "description": prog_data.get("description"),
                "topic": topic,
                "cfda_number": prog_data.get("cfda_number"),
                "eligible_activities": prog_data.get("eligible_activities"),
                "compliance_requirements": prog_data.get("compliance_requirements"),
                "citizen_participation": prog_data.get("resident_input_opportunities"),
                "keywords": prog_data.get("keywords"),
                "key_contacts": prog_data.get("key_contacts"),
                "official_url": prog_data.get("official_url"),
                "source_url": str(json_file),
                "verification_status": verification_status,
                "data_sources": data_sources,
            })

    return programs


def load_jurisdiction_allocations(data_dir: Path, jurisdiction_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Load jurisdiction-specific allocations from data/jurisdiction_overrides/*.json."""
    allocations_by_jurisdiction: Dict[str, List[Dict[str, Any]]] = {}
    overrides_dir = data_dir / "jurisdiction_overrides"

    if not overrides_dir.exists():
        print(f"Warning: {overrides_dir} does not exist")
        return allocations_by_jurisdiction

    for json_file in overrides_dir.glob("*.json"):
        file_jurisdiction = json_file.stem  # e.g., "city-san-rafael"

        # Skip if filtering by jurisdiction
        if jurisdiction_id and file_jurisdiction != jurisdiction_id:
            continue

        print(f"  Loading {json_file.name}...")
        with open(json_file) as f:
            data = json.load(f)

        jurisdiction = data.get("jurisdiction_id", file_jurisdiction)
        allocations = []

        for program_id, prog_data in data.get("federal_programs", {}).items():
            # Extract FY2026 allocation if present
            fy2026_alloc = prog_data.get("marin_county_fy2026_allocation", {})
            fy2026_status = prog_data.get("fy2026_status", {})

            # Calculate allocation amount in cents
            allocation_amount_cents = None
            if fy2026_alloc.get("total_cdbg"):
                allocation_amount_cents = int(fy2026_alloc["total_cdbg"]) * 100
            elif fy2026_alloc.get("total_home"):
                allocation_amount_cents = int(fy2026_alloc["total_home"]) * 100

            allocations.append({
                "program_id": program_id,
                "fiscal_year": "FY2026",
                "allocation_amount_cents": allocation_amount_cents,
                "allocation_status": fy2026_status.get("status", "UNKNOWN"),
                "allocation_note": prog_data.get("allocation_note") or fy2026_status.get("note"),
                "local_allocation_model": prog_data.get("local_allocation_model"),
                "administering_entity": prog_data.get("local_administrator") or (
                    prog_data.get("key_contacts", {}).get("administrator")
                ),
                "application_process": prog_data.get("application_process"),
                "compliance_requirements": prog_data.get("compliance_requirements"),
                "citizen_participation": prog_data.get("citizen_participation"),
                "key_contacts": prog_data.get("key_contacts"),
                "source_url": fy2026_alloc.get("source_url") or str(json_file),
                "metadata": {
                    "fy2026_sources": fy2026_status.get("sources", []),
                    "fy2026_allocation_details": fy2026_alloc,
                },
            })

        if allocations:
            allocations_by_jurisdiction[jurisdiction] = allocations

    return allocations_by_jurisdiction


def ingest_federal_programs(
    dry_run: bool = False,
    jurisdiction_id: Optional[str] = None,
) -> Dict[str, int]:
    """
    Ingest federal programs data into PostgreSQL.

    Args:
        dry_run: If True, only print what would be done
        jurisdiction_id: If provided, only ingest allocations for this jurisdiction

    Returns:
        Dict with counts: programs_stored, allocations_stored
    """
    data_dir = Path(__file__).parent.parent / "data"
    results = {"programs_stored": 0, "allocations_stored": 0}

    # Load data from JSON files
    print("\n=== Loading Federal Programs JSON ===")
    programs = load_federal_programs_json(data_dir)
    print(f"Loaded {len(programs)} program definitions")

    print("\n=== Loading Jurisdiction Allocations JSON ===")
    allocations_by_jurisdiction = load_jurisdiction_allocations(data_dir, jurisdiction_id)
    total_allocations = sum(len(a) for a in allocations_by_jurisdiction.values())
    print(f"Loaded {total_allocations} allocations across {len(allocations_by_jurisdiction)} jurisdictions")

    if dry_run:
        print("\n=== DRY RUN - No changes made ===")
        print(f"Would store {len(programs)} federal programs")
        for jurisdiction, allocations in allocations_by_jurisdiction.items():
            print(f"Would store {len(allocations)} allocations for {jurisdiction}")
        return results

    # Check for DATABASE_URL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("\nError: DATABASE_URL not set. Set it in .env or environment.")
        print("Example: DATABASE_URL=postgresql://user:pass@host:5432/dbname")
        sys.exit(1)

    # Import PostgresBackend
    from civic.storage.postgres_backend import PostgresBackend

    backend = PostgresBackend(database_url)

    # Store federal programs (national definitions)
    print("\n=== Storing Federal Programs ===")
    try:
        stored = backend.store_federal_programs(programs)
        results["programs_stored"] = stored
        print(f"Stored {stored} federal programs")
    except Exception as e:
        print(f"Error storing federal programs: {e}")
        raise

    # Store jurisdiction allocations
    print("\n=== Storing Jurisdiction Allocations ===")
    for jurisdiction, allocations in allocations_by_jurisdiction.items():
        try:
            stored = backend.store_federal_program_allocations(
                jurisdiction_id=jurisdiction,
                allocations=allocations,
            )
            results["allocations_stored"] += stored
            print(f"  {jurisdiction}: {stored} allocations")
        except Exception as e:
            print(f"  Error storing allocations for {jurisdiction}: {e}")
            continue

    # Summary
    print("\n=== Summary ===")
    print(f"Federal programs stored: {results['programs_stored']}")
    print(f"Allocations stored: {results['allocations_stored']}")

    # Verify with counts
    print("\n=== Verification ===")
    programs_count = backend.get_federal_programs_count()
    print(f"Total programs in database: {programs_count}")

    for jurisdiction in allocations_by_jurisdiction.keys():
        alloc_count = backend.get_federal_program_allocations_count(jurisdiction)
        print(f"Allocations for {jurisdiction}: {alloc_count}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Ingest federal programs data into PostgreSQL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be done, don't write to database",
    )
    parser.add_argument(
        "--jurisdiction",
        type=str,
        help="Only ingest allocations for this jurisdiction (e.g., city-san-rafael)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("FEDERAL PROGRAMS POSTGRES MIGRATION")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    results = ingest_federal_programs(
        dry_run=args.dry_run,
        jurisdiction_id=args.jurisdiction,
    )

    print("\n=== Done ===")
    return 0 if results["programs_stored"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
