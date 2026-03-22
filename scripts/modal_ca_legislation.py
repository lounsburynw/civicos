"""
Modal function for California Legislature bill ingestion to PostgreSQL.

Downloads bulk data from https://downloads.leginfo.legislature.ca.gov/
and ingests bills, hearings, votes, and history into PostgreSQL.

Uses the same bulk download format as modal_cacode.py (codified law),
but targets the legislation and legislative_events tables.

Setup:
    Ensure Modal secrets exist:
    modal secret create civic-db DATABASE_URL="postgresql://..."

Usage:
    # Full session ingest (current 2025-2026)
    modal run scripts/modal_ca_legislation.py

    # Dry run (parse only, show stats)
    modal run scripts/modal_ca_legislation.py --dry-run

    # Stats only (check what's in DB)
    modal run scripts/modal_ca_legislation.py --stats-only

    # Specific session
    modal run scripts/modal_ca_legislation.py --session 2023-2024

    # Include bill text (larger download, slower)
    modal run scripts/modal_ca_legislation.py --include-text

    # Only AB/SB bills (skip resolutions)
    modal run scripts/modal_ca_legislation.py --bills-only
"""

import modal
import os
from typing import Optional

app = modal.App("civic-ca-legislation")

civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "requests>=2.28.0",
    )
    .add_local_python_source("civicos")
    .add_local_python_source("civicos_extraction")
)


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civicos-california-env")],
    memory=8192,   # 8GB — session archive is ~700MB
    timeout=7200,  # 2 hours
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=60.0),
)
def sync_california_legislation(
    session: str = "2025-2026",
    dry_run: bool = False,
    stats_only: bool = False,
    include_text: bool = False,
    bills_only: bool = False,
) -> dict:
    """
    Sync California Legislature bills from bulk downloads to PostgreSQL.

    Args:
        session: Legislative session (e.g., "2025-2026")
        dry_run: Parse only, don't store
        stats_only: Show DB stats only
        include_text: Include full bill text (larger download)
        bills_only: Only ingest AB and SB bills (skip resolutions)

    Returns:
        Dict with ingestion results
    """
    import json
    import logging
    import time

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    # Stats only mode
    if stats_only:
        from civicos.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)

        leg_count = db.get_legislation_count("CA")
        events_count = db.get_legislative_events_count(state="CA")

        return {
            "session": session,
            "legislation_count": leg_count,
            "legislative_events_count": events_count,
        }

    # Fetch and parse
    from civicos_extraction.clients.california_legislature import (
        CaliforniaLegislatureClient,
    )

    client = CaliforniaLegislatureClient()
    logger.info(f"Fetching CA legislature data for session {session}...")
    start = time.time()

    data = client.fetch_session_data(
        session=session,
        include_text=include_text,
    )

    fetch_time = time.time() - start
    logger.info(f"Fetched in {fetch_time:.1f}s")

    bills = data["bills"]
    hearings = data["hearings"]
    vote_summaries = data["vote_summaries"]
    history = data["history"]

    # Filter to AB/SB only if requested
    if bills_only:
        bills = [b for b in bills if b.measure_type in ("AB", "SB")]

    # Build bill lookup for normalization
    bill_lookup = {b.bill_id: b for b in bills}

    # Normalize bills for storage
    normalized_bills = [client.normalize_bill_for_storage(b) for b in bills]

    # Normalize events
    hearing_events = [
        client.normalize_hearing_for_storage(h, bill_lookup)
        for h in hearings
    ]
    vote_events = [
        client.normalize_vote_for_storage(v, bill_lookup)
        for v in vote_summaries
    ]
    # History actions — only store significant ones to avoid noise
    significant_history = [
        a for a in history
        if a.action_code or a.action_status  # has structured data
    ]
    history_events = [
        client.normalize_history_for_storage(a, bill_lookup)
        for a in significant_history
    ]

    all_events = hearing_events + vote_events + history_events

    stats = {
        "session": session,
        "bills_parsed": len(bills),
        "hearings_parsed": len(hearings),
        "votes_parsed": len(vote_summaries),
        "history_actions_parsed": len(history),
        "significant_history": len(significant_history),
        "total_events": len(all_events),
        "fetch_time_s": round(fetch_time, 1),
    }

    if dry_run:
        # Show sample data
        stats["dry_run"] = True
        if normalized_bills:
            stats["sample_bill"] = normalized_bills[0]
        if hearing_events:
            stats["sample_hearing"] = hearing_events[0]
        if vote_events:
            stats["sample_vote"] = vote_events[0]

        # Counts by measure type
        type_counts = {}
        for b in bills:
            type_counts[b.measure_type] = type_counts.get(b.measure_type, 0) + 1
        stats["by_measure_type"] = type_counts

        return stats

    # Store to PostgreSQL
    from civicos.storage.postgres_backend import PostgresBackend
    db = PostgresBackend(database_url)

    # Store bills in batches
    logger.info(f"Storing {len(normalized_bills)} bills...")
    store_start = time.time()
    batch_size = 500
    bills_stored = 0
    for i in range(0, len(normalized_bills), batch_size):
        batch = normalized_bills[i:i + batch_size]
        bills_stored += db.store_legislation(state="CA", bills=batch)
    bills_store_time = time.time() - store_start

    # Store events
    logger.info(f"Storing {len(all_events)} legislative events...")
    events_start = time.time()
    events_stored = 0
    for i in range(0, len(all_events), batch_size):
        batch = all_events[i:i + batch_size]
        events_stored += db.store_legislative_events(batch)
    events_store_time = time.time() - events_start

    # Final counts
    total_legislation = db.get_legislation_count("CA")
    total_events = db.get_legislative_events_count(state="CA")

    stats.update({
        "bills_stored": bills_stored,
        "events_stored": events_stored,
        "bills_store_time_s": round(bills_store_time, 1),
        "events_store_time_s": round(events_store_time, 1),
        "total_legislation_in_db": total_legislation,
        "total_events_in_db": total_events,
    })

    logger.info(f"Done. {bills_stored} bills, {events_stored} events stored.")
    return stats


@app.local_entrypoint()
def main(
    session: str = "2025-2026",
    dry_run: bool = False,
    stats_only: bool = False,
    include_text: bool = False,
    bills_only: bool = False,
):
    """CLI entrypoint for Modal."""
    print(f"California Legislature Ingestion — Session {session}")
    print("=" * 50)

    if stats_only:
        print("Mode: Stats only")
    elif dry_run:
        print("Mode: Dry run (parse only)")
    else:
        print("Mode: Full ingestion")

    result = sync_california_legislation.remote(
        session=session,
        dry_run=dry_run,
        stats_only=stats_only,
        include_text=include_text,
        bills_only=bills_only,
    )

    print("\n" + "=" * 50)
    print("RESULT:")
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                if isinstance(v, dict):
                    print(f"    {k}:")
                    for k2, v2 in v.items():
                        print(f"      {k2}: {v2}")
                else:
                    print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    print("=" * 50)
