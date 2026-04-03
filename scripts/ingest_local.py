#!/usr/bin/env python3
"""
Local ingestion pipeline — runs entirely on your machine with SQLite.

No Modal, no Supabase, no cloud infrastructure required.
Use this to test onboarding a city before committing to production.

Usage:
    python scripts/ingest_local.py --jurisdiction city-austin --meetings
    python scripts/ingest_local.py --jurisdiction city-austin --meetings --issues
    python scripts/ingest_local.py --jurisdiction city-austin --all
    python scripts/ingest_local.py --jurisdiction city-austin --all --db /tmp/test.sqlite
    python scripts/ingest_local.py --list                     # Show sandbox databases
    python scripts/ingest_local.py --cleanup city-austin       # Delete sandbox

Creates a SQLite database at data/sandbox_{jurisdiction}.sqlite with ChromaDB
vectors alongside it. Same StorageBackend protocol as production Postgres.
"""

import argparse
import hashlib
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos-extraction" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos-services" / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _default_db_path(jurisdiction: str) -> Path:
    return PROJECT_ROOT / "data" / f"sandbox_{jurisdiction}.sqlite"


def _get_backends(db_path: str, jurisdiction: str):
    """Create SQLite storage + ChromaDB vector backends."""
    from civicos.storage.sqlite_backend import SQLiteBackend

    backend = SQLiteBackend(db_path)

    # ChromaDB for local vector indexing
    chroma_dir = str(Path(db_path).parent / f"sandbox_{jurisdiction}_vectors")
    try:
        from civicos.storage.chroma_backend import ChromaBackend
        vectors = ChromaBackend(persist_directory=chroma_dir)
    except ImportError:
        vectors = None
        logger.warning("chromadb not installed — vector indexing disabled")

    return backend, vectors


def fetch_meetings_local(backend, jurisdiction: str, days_past: int = 365, days_ahead: int = 90) -> dict:
    """Fetch meetings from platform API and store to local SQLite."""
    from datetime import datetime, timedelta
    from civicos_extraction.clients.base import ExtractionConfig

    config = ExtractionConfig.from_jurisdiction(jurisdiction)
    source_type = config.source_type
    logger.info(f"[MEETINGS] Fetching from {source_type} for {jurisdiction}")

    if source_type == "proudcity":
        from civicos_extraction.clients.proudcity import ProudCityClient
        client = ProudCityClient(
            base_url=config.base_url,
            jurisdiction_id=jurisdiction,
            archives=config.archives or None,
        )
        meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "granicus":
        from civicos_extraction.clients.granicus import GranicusSource
        source = GranicusSource(config)
        meetings = source.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "legistar":
        from civicos_extraction.clients.legistar import LegistarClient
        client = LegistarClient(
            client_name=config.metadata.get("client_name", config.source_id.replace("legistar-", "")),
            jurisdiction_id=jurisdiction,
        )
        meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "civicclerk":
        from civicos_extraction.clients.civicclerk import CivicClerkClient
        client = CivicClerkClient(
            subdomain=config.metadata.get("subdomain", config.source_id.replace("civicclerk-", "")),
            jurisdiction_id=jurisdiction,
        )
        meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "escribe":
        from civicos_extraction.clients.escribe import EScribeClient
        client = EScribeClient(
            instance_name=config.metadata.get("instance_name", config.source_id.replace("escribe-", "")),
            jurisdiction_id=jurisdiction,
        )
        meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "civicplus":
        from civicos_extraction.clients.civicplus import CivicPlusClient
        client = CivicPlusClient(
            base_url=config.base_url,
            jurisdiction_id=jurisdiction,
            archives=config.archives or {},
            minutes_archives=config.metadata.get("minutes_archives", {}),
        )
        meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "universal":
        from civicos_extraction.clients.universal import UniversalSource
        source = UniversalSource(config)
        meetings = source.get_meetings(days_ahead=days_ahead, days_past=days_past)
    elif source_type == "playwright_llm":
        from civicos_extraction.clients.playwright_llm import extract_meetings_from_page
        from civicos_extraction.clients.base import Meeting
        page_url = config.metadata.get("meeting_page_url", config.base_url)
        raw_meetings = extract_meetings_from_page(page_url, jurisdiction)
        # Convert raw dicts to Meeting objects
        meetings = []
        for m in raw_meetings:
            dt_str = m.get("date", "")
            try:
                dt = datetime.fromisoformat(dt_str)
            except (ValueError, TypeError):
                dt = datetime.now()
            meetings.append(Meeting(
                id="playwright-llm-{}-{}".format(jurisdiction, hashlib.sha256((m.get("title", "") + dt_str).encode()).hexdigest()[:12]),
                title=m.get("title", "Meeting"),
                meeting_datetime=dt,
                jurisdiction_id=jurisdiction,
                meeting_type=m.get("meeting_type"),
                status="completed" if dt < datetime.now() else "scheduled",
                agenda_url=m.get("agenda_url"),
                minutes_url=m.get("minutes_url"),
                video_url=m.get("video_url"),
                source_platform="playwright_llm",
                source_url=page_url,
            ))
    else:
        logger.warning(f"Unsupported source_type: {source_type}")
        return {"meetings_fetched": 0, "meetings_stored": 0}

    logger.info(f"Fetched {len(meetings)} meetings")

    if meetings:
        meeting_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m.__dict__ for m in meetings]
        store_result = backend.store_meetings(jurisdiction, meeting_dicts)
        stored = int(store_result)
        logger.info(f"Stored {stored} meetings")
        return {"meetings_fetched": len(meetings), "meetings_stored": stored}

    return {"meetings_fetched": 0, "meetings_stored": 0}


def fetch_issues_local(backend, jurisdiction: str, max_pages: int = 50) -> dict:
    """Fetch 311 issues from SeeClickFix and store to local SQLite."""
    from civicos_extraction.clients.base import ExtractionConfig

    config = ExtractionConfig.from_jurisdiction(jurisdiction)
    issue_source = config.issue_source or "seeclickfix"
    logger.info(f"[ISSUES] Fetching from {issue_source} for {jurisdiction}")

    if issue_source == "gogov":
        from civicos_extraction.clients.gogov import GoGovClient
        client = GoGovClient(jurisdiction_id=jurisdiction)
        issues = client.get_issues(max_results=500)
        if issues:
            store_result = backend.store_issues(jurisdiction, issues)
            stored = int(store_result)
            logger.info(f"Stored {stored} GOGov issues")
            client.close()
            return {"issues_fetched": len(issues), "issues_stored": stored}
        client.close()
        return {"issues_fetched": 0, "issues_stored": 0}

    if issue_source != "seeclickfix":
        logger.warning(f"Issue source '{issue_source}' not yet supported locally")
        return {"issues_fetched": 0, "issues_stored": 0}

    from civicos_services.clients.seeclickfix_client import SeeClickFixClient

    place_url = jurisdiction
    for prefix in ["city-", "county-", "town-"]:
        if place_url.startswith(prefix):
            place_url = place_url[len(prefix):]
            break

    client = SeeClickFixClient()
    all_issues = []
    current_page = 1

    while current_page <= max_pages:
        result = client.get_issues(place_url=place_url, per_page=100, page=current_page, status=None)
        issues = result.get("issues", [])
        if not issues:
            break

        for issue in issues:
            issue["provider"] = issue.pop("source", "seeclickfix")
            if "external_id" in issue:
                issue["external_id"] = str(issue["external_id"])
            if "location" in issue and isinstance(issue["location"], dict):
                loc = issue.pop("location")
                issue["address"] = loc.get("address")
                issue["latitude"] = loc.get("lat")
                issue["longitude"] = loc.get("lng")

        all_issues.extend(issues)
        logger.info(f"  Fetched {len(issues)} issues (total: {len(all_issues)})")

        if not result.get("metadata", {}).get("has_more", False):
            break
        current_page += 1

    logger.info(f"Fetched {len(all_issues)} issues total")

    stored = 0
    if all_issues:
        stored = backend.store_issues(jurisdiction, all_issues)
        logger.info(f"Stored {stored} issues")

    return {"issues_fetched": len(all_issues), "issues_stored": stored}


def fetch_elections_local(backend, jurisdiction: str) -> dict:
    """Fetch election data from configured sources and store to local SQLite."""
    import json

    config_path = PROJECT_ROOT / "data" / "extraction" / f"{jurisdiction}.json"
    if not config_path.exists():
        logger.warning(f"[ELECTIONS] No extraction config at {config_path}")
        return {"elections_fetched": 0, "officials_fetched": 0}

    with open(config_path) as f:
        config_data = json.load(f)

    election_sources = config_data.get("election_sources", {})

    if not election_sources:
        logger.info(f"[ELECTIONS] No election sources configured for {jurisdiction}")
        return {"elections_fetched": 0, "officials_fetched": 0}

    total_elections = 0
    total_officials = 0

    # Civera election stats (county registrar)
    if "civera_election_stats" in election_sources:
        civera_config = election_sources["civera_election_stats"]
        logger.info(f"[ELECTIONS] Fetching from civera_election_stats for {jurisdiction}")
        try:
            from civicos_extraction.clients.civera_election_stats import (
                CiveraElectionStatsClient,
                extract_civera_results_to_storage,
            )
            county_slug = civera_config.get("county_slug", "")
            client = CiveraElectionStatsClient(
                jurisdiction_id=jurisdiction,
                graphql_url=civera_config.get("graphql_url", ""),
                county_slug=county_slug,
            )
            counts = extract_civera_results_to_storage(
                client=client,
                storage=backend,
                jurisdiction_id=jurisdiction,
                county_slug=county_slug,
                from_year=civera_config.get("from_year", 2010),
                division_filter=civera_config.get("division_filter"),
            )
            total_elections += counts.get("elections", 0)
            logger.info(f"  Civera: {counts.get('elections', 0)} elections, {counts.get('contests', 0)} contests")
        except Exception as e:
            logger.warning(f"  Civera fetch failed: {e}")

    return {
        "elections_fetched": total_elections,
        "officials_fetched": total_officials,
    }


def index_vectors_local(backend, vectors, jurisdiction: str) -> dict:
    """Index meetings into ChromaDB for local semantic search."""
    if vectors is None:
        logger.warning("No vector backend — skipping indexing")
        return {"total_indexed": 0}

    logger.info(f"[VECTORS] Indexing {jurisdiction} into ChromaDB...")

    # Get meetings for embedding
    meetings = backend.get_meetings(jurisdiction)
    if not meetings:
        logger.info("No meetings to index")
        return {"total_indexed": 0}

    texts = []
    metadatas = []
    ids = []
    for m in meetings:
        # Build text from meeting fields
        title = m.get("title", m.get("meeting_title", ""))
        body = m.get("body", m.get("body_name", ""))
        date = str(m.get("meeting_datetime", m.get("date", "")))
        text = f"{title} - {body} - {date}"
        texts.append(text)
        metadatas.append({"jurisdiction_id": jurisdiction, "corpus_type": "meetings"})
        ids.append(m.get("meeting_id", m.get("id", str(len(ids)))))

    collection = vectors._client.get_or_create_collection(
        name=f"sandbox_{jurisdiction}_meetings",
    )
    collection.upsert(documents=texts, metadatas=metadatas, ids=[str(i) for i in ids])
    logger.info(f"Indexed {len(texts)} meeting embeddings into ChromaDB")

    return {"total_indexed": len(texts)}


def show_sandboxes():
    """List all sandbox databases."""
    sandbox_dir = PROJECT_ROOT / "data"
    dbs = sorted(sandbox_dir.glob("sandbox_*.sqlite"))
    if not dbs:
        print("No sandbox databases found.")
        return
    print("Sandbox databases:")
    for db in dbs:
        size_mb = db.stat().st_size / (1024 * 1024)
        jid = db.stem.replace("sandbox_", "")
        print(f"  {jid}: {db.name} ({size_mb:.1f} MB)")


def cleanup_sandbox(jurisdiction: str):
    """Remove sandbox database and vector directory."""
    db_path = _default_db_path(jurisdiction)
    chroma_dir = PROJECT_ROOT / "data" / f"sandbox_{jurisdiction}_vectors"

    removed = False
    if db_path.exists():
        db_path.unlink()
        print(f"  Removed {db_path.relative_to(PROJECT_ROOT)}")
        removed = True
    if chroma_dir.exists():
        import shutil
        shutil.rmtree(chroma_dir)
        print(f"  Removed {chroma_dir.relative_to(PROJECT_ROOT)}/")
        removed = True

    if removed:
        print(f"Done. Sandbox for {jurisdiction} cleaned up.")
    else:
        print(f"No sandbox found for {jurisdiction}.")


def main():
    parser = argparse.ArgumentParser(description="Local ingestion pipeline (SQLite, no Modal)")
    parser.add_argument("--jurisdiction", "-j", help="Jurisdiction ID (e.g., city-austin)")
    parser.add_argument("--db", help="SQLite database path (default: data/sandbox_{jurisdiction}.sqlite)")
    parser.add_argument("--meetings", action="store_true", help="Fetch meetings")
    parser.add_argument("--issues", action="store_true", help="Fetch 311 issues")
    parser.add_argument("--elections", action="store_true", help="Fetch elections")
    parser.add_argument("--vectors", action="store_true", help="Index vectors (ChromaDB)")
    parser.add_argument("--all", action="store_true", help="Run all stages")
    parser.add_argument("--days-past", type=int, default=365, help="Days of history (default: 365)")
    parser.add_argument("--list", action="store_true", help="List sandbox databases")
    parser.add_argument("--cleanup", metavar="JURISDICTION_ID", help="Remove sandbox for a jurisdiction")
    args = parser.parse_args()

    if args.list:
        show_sandboxes()
        return

    if args.cleanup:
        cleanup_sandbox(args.cleanup)
        return

    if not args.jurisdiction:
        parser.error("--jurisdiction is required (or use --list / --cleanup)")

    if args.all:
        args.meetings = args.issues = args.elections = args.vectors = True

    if not any([args.meetings, args.issues, args.elections, args.vectors]):
        parser.error("Specify at least one stage: --meetings, --issues, --elections, --vectors, or --all")

    jid = args.jurisdiction
    db_path = args.db or str(_default_db_path(jid))

    print("=" * 60)
    print("CivicOS Local Ingestion (Sandbox)")
    print("=" * 60)
    print(f"  Jurisdiction: {jid}")
    print(f"  Database: {db_path}")
    print(f"  Stages: {' '.join(s for s in ['meetings', 'issues', 'elections', 'vectors'] if getattr(args, s))}")
    print("=" * 60)

    backend, vectors = _get_backends(db_path, jid)
    start_time = time.time()
    results = {}

    if args.meetings:
        results["meetings"] = fetch_meetings_local(backend, jid, days_past=args.days_past)

    if args.issues:
        results["issues"] = fetch_issues_local(backend, jid)

    if args.elections:
        results["elections"] = fetch_elections_local(backend, jid)

    if args.vectors:
        results["vectors"] = index_vectors_local(backend, vectors, jid)

    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    for stage, data in results.items():
        parts = [f"{k}: {v}" for k, v in data.items()]
        print(f"  {stage}: {', '.join(parts)}")
    print(f"\n  Time: {elapsed:.1f}s")
    print(f"  Database: {db_path}")
    print(f"\nTo clean up: python scripts/ingest_local.py --cleanup {jid}")


if __name__ == "__main__":
    main()
