"""
Modal unified ingestion script for Civic data pipeline.

This module provides a single entrypoint for running all data ingestion tasks
in parallel on Modal's serverless compute infrastructure. It orchestrates:
- Municipal code fetch (Municode API)
- Legislation text fetch (LegiScan API)
- Meeting discovery (ProudCity API) - supports incremental fetch
- Issue fetch (SeeClickFix API) - supports incremental fetch
- Chunk extraction (PDF parsing) - downloads agenda PDFs and extracts text chunks
- Agenda items extraction (LLM) - extracts actionable items from agendas
- Decision extraction (LLM) - extracts high-stakes decisions from meeting minutes
- Vector indexing (fastembed embeddings)

Architecture:
    modal run scripts/modal_ingest.py --all
    └── spawn() parallel tasks:
        ├── fetch_municipal_code()  → Postgres
        ├── fetch_legislation()     → Postgres
        ├── fetch_meetings()        → Postgres (incremental)
        ├── fetch_issues()          → Postgres (incremental)
        ├── extract_chunks()        → Postgres (incremental, after meetings)
        ├── extract_agenda_items()  → Postgres (LLM-powered)
        └── index_vectors()         → pgvector

    modal run scripts/modal_ingest.py --decisions  # Not in --all (weekly only)
    └── extract_decisions()         → Postgres (LLM-powered, weekly)

    Scheduled refreshes (via modal deploy):
        scheduled_low_velocity_refresh()  # Weekly: municipal code, legislation, decisions
        scheduled_high_velocity_refresh() # Daily: meetings, issues, chunks, vectors

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal setup
    3. Create secrets:
       modal secret create civic-db DATABASE_URL="postgresql://..."
       modal secret create civic-legiscan LEGISCAN_API_KEY="..."
    4. Run: modal run scripts/modal_ingest.py --all
    5. Deploy for scheduled runs: modal deploy scripts/modal_ingest.py

Usage:
    # Run all ingestion (municipal, legislation, vectors)
    modal run scripts/modal_ingest.py --all

    # Run specific components
    modal run scripts/modal_ingest.py --municipal
    modal run scripts/modal_ingest.py --legislation
    modal run scripts/modal_ingest.py --meetings
    modal run scripts/modal_ingest.py --issues
    modal run scripts/modal_ingest.py --vectors

    # Incremental mode (only fetch since last refresh)
    modal run scripts/modal_ingest.py --meetings --incremental
    modal run scripts/modal_ingest.py --issues --incremental

    # Run municipal + vectors (skip legislation to save quota)
    modal run scripts/modal_ingest.py --municipal --vectors

    # Check stats only (no ingestion)
    modal run scripts/modal_ingest.py --stats-only

    # Dry run (fetch but don't store)
    modal run scripts/modal_ingest.py --all --dry-run

API Quota Considerations:
    - Municode API: No quota, 2 req/s rate limit - always safe to run
    - LegiScan API: 30,000 queries/month free tier
      - CA: ~5,700 calls (2,839 bills × 2)
      - US: ~24,700 calls (12,355 bills × 2)
      - Running both exceeds monthly quota
    - ProudCity API: No quota, ~1 req/s rate limit
    - SeeClickFix API: No quota, ~1 req/s rate limit
    - Recommendation: Use --legislation-jurisdiction to run one at a time

Cost Estimates (Modal compute):
    - Municipal code fetch: ~$0.05 (20-30 min, 4GB)
    - Legislation fetch: ~$0.20 (1-4 hours, 4GB)
    - Meeting fetch: ~$0.02 (5 min, 4GB)
    - Issues fetch: ~$0.02 (5 min, 4GB)
    - Vector indexing: ~$0.10 (5-10 min, 16GB)
    - Full --all run: ~$0.40
"""

import modal

# Define the Modal app
app = modal.App("civic-ingest")

# Build unified image with all dependencies
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2
    .apt_install("libpq-dev", "gcc")
    # Python dependencies for all tasks
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "httpx>=0.24.0",  # For Municode API
        "requests>=2.31.0",  # For LegiScan API and SeeClickFix
        "beautifulsoup4>=4.12.0",  # For ProudCity scraping
        "fastembed>=0.3.0",  # For embeddings
        "numpy<2",  # fastembed compatibility
        "langgraph>=0.2.0",
        "pymupdf>=1.24.0",  # For PDF parsing (chunk extraction)
    )
    # Add local civic packages
    .add_local_python_source("civic", "civic_config", "civic_extraction", "civic_services")
)


# =============================================================================
# Municipal Code Fetch
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=7200,  # 2 hours
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_municipal_code(
    jurisdiction: str = "city-san-rafael",
    dry_run: bool = False,
    rate_limit: float = 2.0,
) -> dict:
    """Fetch complete municipal code from Municode API and store to Postgres."""
    import logging
    import os
    import time
    from dataclasses import asdict

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic._internal.legal.corpus.municipal import MunicipalCodeCorpus
    from civic.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    logger.info(f"[MUNICIPAL] Starting fetch: jurisdiction={jurisdiction}")

    corpus = MunicipalCodeCorpus(jurisdiction_id=jurisdiction, rate_limit=rate_limit)

    sections = []
    titles_seen = set()
    try:
        for section in corpus.stream_sections():
            sections.append(asdict(section))
            titles_seen.add(section.title_number)
            if len(sections) % 100 == 0:
                logger.info(f"  Fetched {len(sections)} sections...")
    finally:
        corpus.close()

    fetch_time = time.time() - start_time
    with_text = sum(1 for s in sections if s.get("full_text"))
    logger.info(f"Fetched {len(sections)} sections ({with_text} with text) in {fetch_time:.1f}s")

    stored_count = 0
    if not dry_run:
        backend = PostgresBackend(database_url)
        stored_count = backend.store_municipal_code(jurisdiction_id=jurisdiction, sections=sections)
        logger.info(f"Stored {stored_count} sections")

    elapsed = time.time() - start_time
    return {
        "task": "municipal_code",
        "jurisdiction": jurisdiction,
        "sections_fetched": len(sections),
        "sections_with_text": with_text,
        "sections_stored": stored_count,
        "titles": len(titles_seen),
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }


# =============================================================================
# Legislation Text Fetch
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-legiscan"),
    ],
    memory=4096,
    timeout=14400,  # 4 hours
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=60.0),
)
def fetch_legislation(
    jurisdiction: str = "state-CA",
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Fetch bill text from LegiScan API and store to Postgres."""
    import base64
    import logging
    import os
    import re
    import time
    import requests

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    legiscan_key = os.environ.get("LEGISCAN_API_KEY")

    if not database_url:
        raise ValueError("DATABASE_URL not set")
    if not legiscan_key:
        raise ValueError("LEGISCAN_API_KEY not set")

    # Parse jurisdiction to state code
    if jurisdiction.startswith("state-"):
        state_code = jurisdiction.replace("state-", "")
    elif jurisdiction.startswith("federal"):
        state_code = "US"
    else:
        state_code = jurisdiction

    logger.info(f"[LEGISLATION] Starting fetch: jurisdiction={jurisdiction}, state={state_code}")

    backend = PostgresBackend(database_url)
    all_bills = backend.get_legislation(state_code)
    bills_needing_text = [b for b in all_bills if not b.get("full_text")]

    if limit:
        bills_needing_text = bills_needing_text[:limit]

    logger.info(f"Found {len(bills_needing_text)} bills needing text (of {len(all_bills)} total)")

    if not bills_needing_text:
        return {
            "task": "legislation",
            "jurisdiction": jurisdiction,
            "bills_processed": 0,
            "bills_with_text": 0,
            "api_calls": 0,
            "dry_run": dry_run,
            "elapsed_seconds": time.time() - start_time,
        }

    def legiscan_request(operation: str, params: dict) -> dict:
        time.sleep(0.5)  # Rate limit
        try:
            response = requests.get(
                "https://api.legiscan.com/",
                params={"key": legiscan_key, "op": operation, **params},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"LegiScan API error: {e}")
            return {}

    def html_to_text(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()

    api_calls = 0
    updates = []

    for i, bill in enumerate(bills_needing_text):
        legiscan_id = bill.get("legiscan_id")
        bill_number = bill.get("bill_number", "unknown")

        if not legiscan_id:
            continue

        if (i + 1) % 50 == 0:
            logger.info(f"[{i+1}/{len(bills_needing_text)}] Processing bills...")

        # Get bill details
        bill_data = legiscan_request("getBill", {"id": legiscan_id})
        api_calls += 1

        if not bill_data or "bill" not in bill_data:
            continue

        texts = bill_data["bill"].get("texts", [])
        if not texts:
            continue

        doc_id = texts[-1].get("doc_id")
        if not doc_id:
            continue

        # Get bill text
        text_data = legiscan_request("getBillText", {"id": doc_id})
        api_calls += 1

        if not text_data or "text" not in text_data:
            continue

        doc_b64 = text_data["text"].get("doc", "")
        if not doc_b64:
            continue

        try:
            doc_html = base64.b64decode(doc_b64).decode("utf-8")
            full_text = html_to_text(doc_html)
            updates.append({"bill_id": bill.get("bill_id"), "full_text": full_text})
        except Exception as e:
            logger.error(f"Error decoding {bill_number}: {e}")

    # Store updates
    if updates and not dry_run:
        stored = backend.update_legislation_text(state_code, updates)
        logger.info(f"Stored {stored} bill texts")

    elapsed = time.time() - start_time
    return {
        "task": "legislation",
        "jurisdiction": jurisdiction,
        "bills_processed": len(bills_needing_text),
        "bills_with_text": len(updates),
        "api_calls": api_calls,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }


# =============================================================================
# Vector Indexing
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=16384,  # 16GB for embeddings
    timeout=3600,  # 1 hour
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def index_vectors(
    jurisdiction: str = "city-san-rafael",
    corpus: str = "all",
    reindex: bool = False,
) -> dict:
    """Generate embeddings and store to pgvector."""
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend
    from civic._internal.meetings.transcript import expand_transcripts_to_chunks
    from civic._internal.legal.embeddings.chunker import (
        expand_municipal_code_to_chunks,
        expand_legislation_to_chunks,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"[VECTORS] Starting indexing: jurisdiction={jurisdiction}, corpus={corpus}")

    backend = get_storage_backend(database_url)
    pgvector = PgVectorBackend(connection_string=database_url, provider_type="fastembed")

    validation = pgvector.validate()
    if not validation.is_valid:
        raise RuntimeError(f"pgvector validation failed: {validation.errors}")

    # Determine corpus types
    if jurisdiction.startswith("state-"):
        all_corpus_types = ["legislation"]
    else:
        all_corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues", "agenda_items"]

    corpus_types = all_corpus_types if corpus == "all" else [corpus]
    results = {}

    for ct in corpus_types:
        logger.info(f"Processing corpus: {ct}")

        if reindex:
            deleted = pgvector.delete_index(jurisdiction, ct)
            logger.info(f"  Deleted {deleted} existing vectors")

        stats = pgvector.get_stats(jurisdiction, ct, backend)

        if not reindex and stats.storage_document_count:
            if stats.document_count >= stats.storage_document_count:
                results[ct] = {"status": "skipped", "indexed": 0}
                continue

        try:
            transcript_chunker = expand_transcripts_to_chunks if ct == "transcripts" else None
            if ct == "municipal_code":
                legal_chunker_fn = expand_municipal_code_to_chunks
            elif ct == "legislation":
                legal_chunker_fn = expand_legislation_to_chunks
            else:
                legal_chunker_fn = None

            count = pgvector.index_from_storage(
                storage_backend=backend,
                jurisdiction_id=jurisdiction,
                corpus_type=ct,
                batch_size=100,
                allow_dimension_change=reindex,
                transcript_chunker=transcript_chunker,
                legal_chunker=legal_chunker_fn,
            )
            results[ct] = {"status": "success", "indexed": count}
            logger.info(f"  Indexed {count} documents")
        except Exception as e:
            logger.exception(f"  Error indexing {ct}")
            results[ct] = {"status": "error", "error": str(e)}

    elapsed = time.time() - start_time
    total_indexed = sum(r.get("indexed", 0) for r in results.values())

    return {
        "task": "vectors",
        "jurisdiction": jurisdiction,
        "corpus_types": corpus_types,
        "results": results,
        "total_indexed": total_indexed,
        "elapsed_seconds": elapsed,
        "cost_usd": 16 * elapsed * 0.000463,
    }


# =============================================================================
# Meeting Fetch (Incremental)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=1800,  # 30 minutes
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_meetings(
    jurisdiction: str = "city-san-rafael",
    days_past: int = 30,
    days_ahead: int = 90,
    incremental: bool = False,
    dry_run: bool = False,
) -> dict:
    """Fetch meetings from ProudCity API with optional incremental mode.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        days_past: Days to look back for meetings (default 30)
        days_ahead: Days to look ahead for meetings (default 90)
        incremental: If True, use refresh_metadata to determine date range
        dry_run: If True, fetch but don't store
    """
    import logging
    import os
    import time
    from datetime import datetime, timedelta

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    logger.info(f"[MEETINGS] Starting fetch: jurisdiction={jurisdiction}, incremental={incremental}")

    # Determine date range
    if incremental:
        metadata = backend.get_refresh_metadata(jurisdiction, "meetings", "proudcity")
        if metadata and metadata.get("last_fetch_at"):
            last_fetch = datetime.fromisoformat(metadata["last_fetch_at"])
            days_since = (datetime.now() - last_fetch).days
            days_past = min(days_past, max(7, days_since + 1))  # At least 7 days overlap
            logger.info(f"  Incremental mode: last fetch {days_since} days ago, fetching {days_past} days back")

    # Fetch meetings using ProudCityClient
    # Map jurisdiction to base_url (add more mappings as needed)
    JURISDICTION_URLS = {
        "city-san-rafael": "https://www.cityofsanrafael.org",
    }
    base_url = JURISDICTION_URLS.get(jurisdiction)
    if not base_url:
        raise ValueError(f"Unknown jurisdiction: {jurisdiction}. Add to JURISDICTION_URLS mapping.")

    try:
        from civic_extraction.clients.proudcity import ProudCityClient
        client = ProudCityClient(
            base_url=base_url,
            jurisdiction_id=jurisdiction,
        )
        meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
    except Exception as e:
        logger.error(f"Error fetching meetings: {e}")
        backend.update_refresh_metadata(
            jurisdiction, "meetings", "proudcity",
            status="failed", error_message=str(e)
        )
        raise

    logger.info(f"Fetched {len(meetings)} meetings")

    # Store meetings
    stored_count = 0
    if not dry_run and meetings:
        # Convert Meeting objects to dicts for storage
        meeting_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m.__dict__ for m in meetings]
        stored_count = backend.store_meetings(jurisdiction, meeting_dicts)
        logger.info(f"Stored {stored_count} meetings")

        # Update refresh metadata
        backend.update_refresh_metadata(
            jurisdiction, "meetings", "proudcity",
            items_fetched=len(meetings),
            items_stored=stored_count,
            status="completed",
            fetch_window_days=days_past,
        )

    elapsed = time.time() - start_time
    return {
        "task": "meetings",
        "jurisdiction": jurisdiction,
        "meetings_fetched": len(meetings),
        "meetings_stored": stored_count,
        "incremental": incremental,
        "days_past": days_past,
        "days_ahead": days_ahead,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }


# =============================================================================
# Issue Fetch (Incremental)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=1800,  # 30 minutes
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_issues(
    jurisdiction: str = "city-san-rafael",
    max_pages: int = 50,
    per_page: int = 100,
    incremental: bool = False,
    dry_run: bool = False,
) -> dict:
    """Fetch 311 issues from SeeClickFix API with optional incremental mode.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        max_pages: Maximum pages to fetch (default 50)
        per_page: Issues per page (default 100, max 100)
        incremental: If True, use refresh_metadata to determine starting page
        dry_run: If True, fetch but don't store
    """
    import logging
    import os
    import time
    from datetime import datetime

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic.storage.postgres_backend import PostgresBackend
    from civic_services.clients.seeclickfix_client import SeeClickFixClient

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    logger.info(f"[ISSUES] Starting fetch: jurisdiction={jurisdiction}, incremental={incremental}")

    # Derive place_url from jurisdiction
    place_url = jurisdiction
    for prefix in ["city-", "county-", "town-"]:
        if place_url.startswith(prefix):
            place_url = place_url[len(prefix):]
            break

    # Initialize client
    client = SeeClickFixClient()

    # Fetch all issues (paginating through results)
    all_issues = []
    current_page = 1

    while current_page <= max_pages:
        logger.info(f"Fetching page {current_page}/{max_pages}...")

        result = client.get_issues(
            place_url=place_url,
            per_page=per_page,
            page=current_page,
            status=None,  # Fetch all statuses
        )

        issues = result.get("issues", [])
        metadata = result.get("metadata", {})

        if metadata.get("error"):
            logger.error(f"API error: {metadata['error']}")
            break

        if not issues:
            logger.info("No more issues to fetch")
            break

        # Normalize issues for storage (map source -> provider, ensure external_id is string)
        for issue in issues:
            issue["provider"] = issue.pop("source", "seeclickfix")
            # Ensure external_id is a string (database column is TEXT)
            if "external_id" in issue:
                issue["external_id"] = str(issue["external_id"])
            # Flatten location if nested
            if "location" in issue and isinstance(issue["location"], dict):
                loc = issue.pop("location")
                issue["address"] = loc.get("address")
                issue["latitude"] = loc.get("lat")
                issue["longitude"] = loc.get("lng")

        all_issues.extend(issues)
        logger.info(f"  Fetched {len(issues)} issues (total: {len(all_issues)})")

        if not metadata.get("has_more", False):
            break

        current_page += 1

    logger.info(f"Fetched {len(all_issues)} issues total")

    # Store issues
    stored_count = 0
    if not dry_run and all_issues:
        try:
            stored_count = backend.store_issues(jurisdiction, all_issues)
            logger.info(f"Stored {stored_count} issues")

            # Update refresh metadata
            backend.update_refresh_metadata(
                jurisdiction, "issues", "seeclickfix",
                items_fetched=len(all_issues),
                items_stored=stored_count,
                status="completed",
            )
        except Exception as e:
            logger.error(f"Error storing issues: {e}")
            backend.update_refresh_metadata(
                jurisdiction, "issues", "seeclickfix",
                status="failed", error_message=str(e)
            )
            raise

    elapsed = time.time() - start_time
    return {
        "task": "issues",
        "jurisdiction": jurisdiction,
        "issues_fetched": len(all_issues),
        "issues_stored": stored_count,
        "pages_fetched": current_page,
        "incremental": incremental,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }


# =============================================================================
# Election Fetch (Google Civic API)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-google"),  # Contains GOOGLE_API_KEY
    ],
    memory=4096,
    timeout=600,  # 10 minutes
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_elections(
    jurisdiction: str = "city-san-rafael",
    dry_run: bool = False,
) -> dict:
    """Fetch elections from Google Civic API and store to Postgres.

    This fetches all available elections from Google's Civic Information API
    and stores them for the specified jurisdiction. Elections include
    national, state, and local races.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        dry_run: If True, fetch but don't store

    Setup:
        1. Create Modal secret with Google API key:
           modal secret create civic-google GOOGLE_API_KEY="your_key_here"
        2. Ensure Google Civic Information API is enabled in Google Cloud Console
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic.storage.postgres_backend import PostgresBackend
    from civic_extraction.clients.google_civic import (
        GoogleCivicClient,
        google_civic_to_election,
    )

    database_url = os.environ.get("DATABASE_URL")
    google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_CIVIC_API_KEY")

    if not database_url:
        raise ValueError("DATABASE_URL not set")
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY not set. Create Modal secret: modal secret create civic-google GOOGLE_API_KEY='...'")

    logger.info(f"[ELECTIONS] Starting fetch: jurisdiction={jurisdiction}")

    # Create client and validate
    client = GoogleCivicClient(jurisdiction_id=jurisdiction, api_key=google_api_key)
    validation = client.validate()
    if not validation.is_valid:
        raise RuntimeError(f"Google Civic API validation failed: {validation.errors}")

    # Fetch elections
    elections_raw = client.get_elections()
    logger.info(f"Fetched {len(elections_raw)} elections from Google Civic API")

    if not elections_raw:
        elapsed = time.time() - start_time
        return {
            "task": "elections",
            "jurisdiction": jurisdiction,
            "elections_fetched": 0,
            "elections_stored": 0,
            "dry_run": dry_run,
            "elapsed_seconds": elapsed,
            "cost_usd": 4 * elapsed * 0.000463,
        }

    # Map to storage format
    elections = [google_civic_to_election(e, jurisdiction) for e in elections_raw]

    # Log elections found
    for e in elections:
        logger.info(f"  - {e.get('name')} ({e.get('election_date')}) [{e.get('election_type')}]")

    # Store to database
    stored_count = 0
    if not dry_run:
        backend = PostgresBackend(database_url)
        stored_count = backend.store_elections(jurisdiction, elections)
        logger.info(f"Stored {stored_count} elections")

        # Update refresh metadata
        backend.update_refresh_metadata(
            jurisdiction, "elections", "google_civic",
            items_fetched=len(elections),
            items_stored=stored_count,
            status="completed",
        )

    elapsed = time.time() - start_time
    return {
        "task": "elections",
        "jurisdiction": jurisdiction,
        "elections_fetched": len(elections),
        "elections_stored": stored_count,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }


# =============================================================================
# Chunk Extraction (PDF Processing)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=8192,  # 8GB for PDF processing
    timeout=3600,  # 1 hour (PDFs can be slow)
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=30.0),
)
def extract_chunks(
    jurisdiction: str = "city-san-rafael",
    limit: int = 0,
    dry_run: bool = False,
) -> dict:
    """Extract text chunks from meeting agenda PDFs.

    This function:
    1. Reads meetings from Postgres that have agenda_url
    2. Checks which meetings haven't been chunked yet (incremental)
    3. Downloads PDFs, parses them, and stores chunks to Postgres

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be processed without extracting
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic_extraction.cli.chunks import run_chunk_extraction

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"[CHUNKS] Starting extraction: jurisdiction={jurisdiction}, limit={limit}")

    # run_chunk_extraction handles:
    # - Reading meetings from Postgres (cloud mode via DATABASE_URL)
    # - Incremental extraction (skips already-chunked meetings)
    # - PDF download, parsing, and storage
    # - Checkpointing for resumption
    results = run_chunk_extraction(
        jurisdiction_id=jurisdiction,
        # Local dirs not used in cloud mode, but required params
        input_dir="data/meetings",
        output_dir="data/chunks",
        checkpoint_dir="data/checkpoints",
        dry_run=dry_run,
        limit=limit,
        cloud=True,  # Force cloud storage mode
    )

    # Summarize results
    if results is None:
        # Dry run or no meetings to process
        elapsed = time.time() - start_time
        return {
            "task": "chunks",
            "jurisdiction": jurisdiction,
            "status": "dry_run" if dry_run else "no_meetings",
            "chunks_extracted": 0,
            "meetings_processed": 0,
            "elapsed_seconds": elapsed,
            "cost_usd": 8 * elapsed * 0.000463,
        }

    # Count actual extractions
    extracted = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "error")
    total_chunks = sum(r.chunks_count for r in results if r.status == "success")

    elapsed = time.time() - start_time
    logger.info(f"[CHUNKS] Extracted {total_chunks} chunks from {extracted} meetings")
    logger.info(f"[CHUNKS] Skipped {skipped} (already chunked), {failed} failed")

    return {
        "task": "chunks",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_failed": failed,
        "chunks_extracted": total_chunks,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 8 * elapsed * 0.000463,
    }


# =============================================================================
# Agenda Items Extraction (LLM-powered)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-openai"),  # For LLM extraction
    ],
    memory=8192,  # 8GB for LLM processing
    timeout=7200,  # 2 hours (many meetings to process)
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=30.0),
)
def extract_agenda_items(
    jurisdiction: str = "city-san-rafael",
    limit: int = 0,
    dry_run: bool = False,
) -> dict:
    """Extract actionable agenda items from meeting PDFs using LLM.

    This function:
    1. Reads meetings from Postgres that have agenda_url
    2. Discovers actual PDF URLs from meeting pages
    3. Downloads PDFs and extracts actionable items using LLM
    4. Stores agenda items to Postgres

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be processed without extracting
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic_extraction.cli.agenda import run_agenda_extraction

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"[AGENDA] Starting extraction: jurisdiction={jurisdiction}, limit={limit}")

    # run_agenda_extraction handles:
    # - Reading meetings from Postgres (cloud mode via DATABASE_URL)
    # - PDF discovery from meeting pages
    # - LLM-powered agenda item extraction
    # - Storing agenda items to Postgres
    results = run_agenda_extraction(
        jurisdiction_id=jurisdiction,
        dry_run=dry_run,
        limit=limit,
        cloud=True,  # Force cloud storage mode
    )

    # Summarize results
    if results is None:
        elapsed = time.time() - start_time
        return {
            "task": "agenda_items",
            "jurisdiction": jurisdiction,
            "status": "dry_run" if dry_run else "no_meetings",
            "items_extracted": 0,
            "meetings_processed": 0,
            "elapsed_seconds": elapsed,
            "cost_usd": 8 * elapsed * 0.000463,
        }

    # Count actual extractions
    extracted = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "error")
    total_items = sum(r.items_count for r in results if r.status == "success")
    actionable_items = sum(r.actionable_count for r in results if r.status == "success")

    elapsed = time.time() - start_time
    logger.info(f"[AGENDA] Extracted {total_items} items ({actionable_items} actionable) from {extracted} meetings")
    logger.info(f"[AGENDA] Skipped {skipped} (already extracted), {failed} failed")

    return {
        "task": "agenda_items",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_failed": failed,
        "items_extracted": total_items,
        "actionable_items": actionable_items,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 8 * elapsed * 0.000463,
    }


# =============================================================================
# Decision Extraction (LLM-powered)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-openai"),  # For LLM extraction
    ],
    memory=8192,  # 8GB for LLM processing
    timeout=7200,  # 2 hours (many meetings to process)
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=30.0),
)
def extract_decisions(
    jurisdiction: str = "city-san-rafael",
    limit: int = 0,
    dry_run: bool = False,
) -> dict:
    """Extract high-stakes decisions from meeting minutes using LLM.

    This function:
    1. Reads meetings from Postgres that have agenda/minutes URLs
    2. Downloads PDFs and extracts high-stakes decisions using LLM
    3. Stores decisions to Postgres

    NOTE: Should run weekly (not daily) because meeting minutes PDFs
    are typically published 1-2 weeks after the meeting.

    Pipeline Integration:
        This is a Modal orchestration task, not a Pipeline class instance.
        It bypasses the standard 4-stage pattern (discover→ingest→store→index)
        because decision extraction is:
        - LLM-intensive (not suited for streaming callbacks)
        - Weekly (not part of daily high-velocity refresh)
        - Already incremental (skips previously extracted meetings)

        Vector indexing happens separately via index_vectors() which includes
        "decisions" in its corpus_types. In scheduled_low_velocity_refresh,
        extract_decisions runs BEFORE index_vectors to maintain store→index order.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be processed without extracting
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civic_extraction.cli.decisions import run_decision_extraction

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"[DECISIONS] Starting extraction: jurisdiction={jurisdiction}, limit={limit}")

    # run_decision_extraction handles:
    # - Reading meetings from Postgres (cloud mode via DATABASE_URL)
    # - Incremental extraction (skips already-extracted meetings)
    # - LLM-powered decision extraction via RetrospectiveAnalyzer
    # - Storing decisions to Postgres
    results = run_decision_extraction(
        jurisdiction_id=jurisdiction,
        # Local dirs not used in cloud mode, but required params
        input_dir="data/meetings",
        output_dir="data/decisions",
        checkpoint_dir="data/checkpoints",
        dry_run=dry_run,
        limit=limit,
        cloud=True,  # Force cloud storage mode
    )

    # Summarize results
    if results is None:
        elapsed = time.time() - start_time
        return {
            "task": "decisions",
            "jurisdiction": jurisdiction,
            "status": "dry_run" if dry_run else "no_meetings",
            "decisions_extracted": 0,
            "meetings_processed": 0,
            "elapsed_seconds": elapsed,
            "cost_usd": 8 * elapsed * 0.000463,
        }

    # Count actual extractions
    extracted = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "error")
    total_decisions = sum(r.decisions_count for r in results if r.status == "success")

    elapsed = time.time() - start_time
    logger.info(f"[DECISIONS] Extracted {total_decisions} decisions from {extracted} meetings")
    logger.info(f"[DECISIONS] Skipped {skipped} (already extracted), {failed} failed")

    return {
        "task": "decisions",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_failed": failed,
        "decisions_extracted": total_decisions,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 8 * elapsed * 0.000463,
    }


# =============================================================================
# Scheduled Refreshes
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-legiscan"),
        modal.Secret.from_name("civic-openai"),  # For LLM extraction (agenda, decisions)
    ],
    memory=4096,
    timeout=14400,  # 4 hours
    schedule=modal.Cron("0 3 * * 0"),  # Weekly on Sunday at 3 AM UTC (7 PM Pacific Sat)
)
def scheduled_low_velocity_refresh():
    """Weekly scheduled refresh for low-velocity corpora (municipal code, legislation, decisions).

    Runs Sunday 3 AM UTC = Saturday 7 PM Pacific.
    Full refresh for static reference data that rarely changes.
    Also runs decision extraction (weekly because minutes PDFs lag behind meetings).
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting scheduled low-velocity refresh")
    start_time = time.time()

    results = {}

    # Municipal code (always full refresh - no incremental API support)
    try:
        logger.info("Fetching municipal code...")
        result = fetch_municipal_code.local(jurisdiction="city-san-rafael", dry_run=False)
        results["municipal_code"] = result
        logger.info(f"  Municipal code: {result.get('sections_stored', 0)} sections stored")
    except Exception as e:
        logger.exception("Municipal code fetch failed")
        results["municipal_code"] = {"status": "failed", "error": str(e)}

    # Legislation CA (run weekly to avoid quota issues)
    try:
        logger.info("Fetching CA legislation...")
        result = fetch_legislation.local(jurisdiction="state-CA", dry_run=False)
        results["legislation_CA"] = result
        logger.info(f"  CA Legislation: {result.get('bills_with_text', 0)} bills updated")
    except Exception as e:
        logger.exception("CA legislation fetch failed")
        results["legislation_CA"] = {"status": "failed", "error": str(e)}

    # Agenda items extraction (LLM-powered, after meetings are available)
    try:
        logger.info("Extracting agenda items...")
        result = extract_agenda_items.local(jurisdiction="city-san-rafael", dry_run=False)
        results["agenda_items"] = result
        logger.info(f"  Agenda items: {result.get('items_extracted', 0)} items ({result.get('actionable_items', 0)} actionable)")
    except Exception as e:
        logger.exception("Agenda items extraction failed")
        results["agenda_items"] = {"status": "failed", "error": str(e)}

    # Decision extraction (LLM-powered, weekly because minutes PDFs lag behind meetings)
    try:
        logger.info("Extracting decisions...")
        result = extract_decisions.local(jurisdiction="city-san-rafael", dry_run=False)
        results["decisions"] = result
        logger.info(f"  Decisions: {result.get('decisions_extracted', 0)} decisions from {result.get('meetings_extracted', 0)} meetings")
    except Exception as e:
        logger.exception("Decision extraction failed")
        results["decisions"] = {"status": "failed", "error": str(e)}

    # Vector indexing (after data is refreshed)
    try:
        logger.info("Indexing vectors...")
        result = index_vectors.local(jurisdiction="city-san-rafael", corpus="all", reindex=False)
        results["vectors"] = result
        logger.info(f"  Vectors: {result.get('total_indexed', 0)} documents indexed")
    except Exception as e:
        logger.exception("Vector indexing failed")
        results["vectors"] = {"status": "failed", "error": str(e)}

    elapsed = time.time() - start_time
    logger.info(f"Low-velocity refresh complete in {elapsed:.1f}s")

    return {
        "schedule": "low_velocity_weekly",
        "results": results,
        "elapsed_seconds": elapsed,
    }


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=3600,  # 1 hour
    schedule=modal.Cron("0 14 * * *"),  # Daily at 2 PM UTC (6 AM Pacific)
)
def scheduled_high_velocity_refresh():
    """Daily scheduled refresh for high-velocity corpora (meetings, issues, chunks).

    Runs daily at 2 PM UTC = 6 AM Pacific.
    Incremental fetch for data that changes frequently.

    Pipeline:
        1. fetch_meetings() - Scrape new meetings from ProudCity
        2. fetch_issues() - Fetch new issues from SeeClickFix
        3. extract_chunks() - Download PDFs and extract text chunks (incremental)
        4. index_vectors() - Index meetings, issues, and chunks to pgvector
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting scheduled high-velocity refresh")
    start_time = time.time()

    results = {}

    # Meetings (incremental)
    try:
        logger.info("Fetching meetings (incremental)...")
        result = fetch_meetings.local(
            jurisdiction="city-san-rafael",
            incremental=True,
            dry_run=False,
        )
        results["meetings"] = result
        logger.info(f"  Meetings: {result.get('meetings_stored', 0)} stored")
    except Exception as e:
        logger.exception("Meetings fetch failed")
        results["meetings"] = {"status": "failed", "error": str(e)}

    # Issues (incremental)
    try:
        logger.info("Fetching issues (incremental)...")
        result = fetch_issues.local(
            jurisdiction="city-san-rafael",
            incremental=True,
            dry_run=False,
        )
        results["issues"] = result
        logger.info(f"  Issues: {result.get('issues_stored', 0)} stored")
    except Exception as e:
        logger.exception("Issues fetch failed")
        results["issues"] = {"status": "failed", "error": str(e)}

    # Chunk extraction (incremental - skips already-chunked meetings)
    try:
        logger.info("Extracting chunks from new meetings...")
        result = extract_chunks.local(
            jurisdiction="city-san-rafael",
            dry_run=False,
        )
        results["chunks"] = result
        logger.info(f"  Chunks: {result.get('chunks_extracted', 0)} extracted from {result.get('meetings_extracted', 0)} meetings")
    except Exception as e:
        logger.exception("Chunk extraction failed")
        results["chunks"] = {"status": "failed", "error": str(e)}

    # Quick vector indexing for meetings, issues, and chunks
    try:
        logger.info("Indexing vectors (meetings, issues, chunks)...")
        for corpus_type in ["meetings", "issues", "chunks"]:
            result = index_vectors.local(
                jurisdiction="city-san-rafael",
                corpus=corpus_type,
                reindex=False,
            )
            results[f"vectors_{corpus_type}"] = result
            logger.info(f"  {corpus_type} vectors: {result.get('total_indexed', 0)} indexed")
    except Exception as e:
        logger.exception("Vector indexing failed")
        results["vectors"] = {"status": "failed", "error": str(e)}

    elapsed = time.time() - start_time
    logger.info(f"High-velocity refresh complete in {elapsed:.1f}s")

    return {
        "schedule": "high_velocity_daily",
        "results": results,
        "elapsed_seconds": elapsed,
    }


# =============================================================================
# Stats
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=120,
)
def get_stats(jurisdiction: str = "city-san-rafael") -> dict:
    """Get current ingestion statistics."""
    import os

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend
    from civic.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = get_storage_backend(database_url)
    pgvector = PgVectorBackend(connection_string=database_url, provider_type="fastembed")
    postgres = PostgresBackend(database_url)

    stats = {"jurisdiction": jurisdiction}

    # Municipal code stats
    try:
        sections = postgres.get_municipal_code(jurisdiction)
        with_text = sum(1 for s in sections if s.get("full_text"))
        stats["municipal_code"] = {
            "total": len(sections),
            "with_text": with_text,
            "coverage": f"{with_text/len(sections)*100:.1f}%" if sections else "N/A",
        }
    except Exception as e:
        stats["municipal_code"] = {"error": str(e)}

    # Legislation stats
    for state in ["CA", "US"]:
        try:
            bills = postgres.get_legislation(state)
            with_text = sum(1 for b in bills if b.get("full_text"))
            stats[f"legislation_{state}"] = {
                "total": len(bills),
                "with_text": with_text,
                "coverage": f"{with_text/len(bills)*100:.1f}%" if bills else "N/A",
            }
        except Exception as e:
            stats[f"legislation_{state}"] = {"error": str(e)}

    # Vector stats
    if jurisdiction.startswith("state-"):
        corpus_types = ["legislation"]
    else:
        corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"]

    vector_stats = {}
    for ct in corpus_types:
        try:
            s = pgvector.get_stats(jurisdiction, ct, backend)
            vector_stats[ct] = {
                "indexed": s.document_count,
                "total": s.storage_document_count or 0,
            }
        except Exception:
            pass

    # Also show legislation vectors for city jurisdictions (stored under state-CA)
    if not jurisdiction.startswith("state-"):
        for state in ["CA", "US"]:
            try:
                s = pgvector.get_stats(f"state-{state}", "legislation", backend)
                vector_stats[f"legislation_{state}"] = {
                    "indexed": s.document_count,
                    "total": s.storage_document_count or 0,
                }
            except Exception:
                pass

    stats["vectors"] = vector_stats

    return stats


# =============================================================================
# Unified Entrypoint
# =============================================================================

@app.local_entrypoint()
def main(
    all: bool = False,
    municipal: bool = False,
    legislation: bool = False,
    meetings: bool = False,
    issues: bool = False,
    elections: bool = False,
    chunks: bool = False,
    agenda: bool = False,
    decisions: bool = False,
    vectors: bool = False,
    jurisdiction: str = "city-san-rafael",
    legislation_jurisdiction: str = "state-CA",
    legislation_limit: int | None = None,
    chunks_limit: int = 0,
    agenda_limit: int = 0,
    decisions_limit: int = 0,
    incremental: bool = False,
    reindex: bool = False,
    dry_run: bool = False,
    stats_only: bool = False,
):
    """
    Unified ingestion entrypoint.

    Examples:
        # Run all ingestion tasks in parallel
        modal run scripts/modal_ingest.py --all

        # Run specific components
        modal run scripts/modal_ingest.py --municipal
        modal run scripts/modal_ingest.py --legislation --legislation-jurisdiction state-CA
        modal run scripts/modal_ingest.py --meetings
        modal run scripts/modal_ingest.py --issues
        modal run scripts/modal_ingest.py --elections
        modal run scripts/modal_ingest.py --chunks
        modal run scripts/modal_ingest.py --vectors

        # Incremental mode (only fetch since last refresh)
        modal run scripts/modal_ingest.py --meetings --incremental
        modal run scripts/modal_ingest.py --issues --incremental

        # Extract chunks (incremental by default - skips already-chunked meetings)
        modal run scripts/modal_ingest.py --chunks
        modal run scripts/modal_ingest.py --chunks --chunks-limit 5  # Limit to 5 meetings

        # Extract decisions (run weekly, not daily - minutes PDFs lag behind meetings)
        modal run scripts/modal_ingest.py --decisions
        modal run scripts/modal_ingest.py --decisions --decisions-limit 5

        # Combine components (skip legislation to save API quota)
        modal run scripts/modal_ingest.py --municipal --vectors

        # Check current stats
        modal run scripts/modal_ingest.py --stats-only

        # Dry run
        modal run scripts/modal_ingest.py --all --dry-run
    """
    if stats_only:
        result = get_stats.remote(jurisdiction)
        print("\n" + "=" * 60)
        print(f"Ingestion Statistics for {result['jurisdiction']}")
        print("=" * 60)

        # Municipal code
        mc = result.get("municipal_code", {})
        if "error" not in mc:
            status = "+" if mc.get("with_text") == mc.get("total") else "o"
            print(f"{status} Municipal Code: {mc.get('with_text', 0)}/{mc.get('total', 0)} ({mc.get('coverage', 'N/A')})")
        else:
            print(f"x Municipal Code: {mc['error']}")

        # Legislation
        for state in ["CA", "US"]:
            leg = result.get(f"legislation_{state}", {})
            if "error" not in leg:
                status = "+" if leg.get("with_text") == leg.get("total") else "o"
                print(f"{status} Legislation {state}: {leg.get('with_text', 0)}/{leg.get('total', 0)} ({leg.get('coverage', 'N/A')})")
            else:
                print(f"x Legislation {state}: {leg['error']}")

        # Vectors
        print("\nVector Indices:")
        for ct, vs in result.get("vectors", {}).items():
            status = "+" if vs.get("indexed") == vs.get("total") and vs.get("total", 0) > 0 else "o"
            print(f"  {status} {ct:15} {vs.get('indexed', 0):>5}/{vs.get('total', 0):<5}")

        print("=" * 60)
        return

    # Determine what to run
    # Note: decisions is NOT included in --all because it should run weekly, not with daily refresh
    # Note: elections is included in --all as it's a lightweight API call
    run_municipal = all or municipal
    run_legislation = all or legislation
    run_meetings = all or meetings
    run_issues = all or issues
    run_elections = all or elections
    run_chunks = all or chunks
    run_agenda = all or agenda
    run_decisions = decisions  # Explicitly not in --all (weekly only)
    run_vectors = all or vectors

    if not (run_municipal or run_legislation or run_meetings or run_issues or run_elections or run_chunks or run_agenda or run_decisions or run_vectors):
        print("No tasks specified. Use --all, --municipal, --legislation, --meetings, --issues, --elections, --chunks, --agenda, --decisions, or --vectors")
        print("Use --stats-only to check current state")
        return

    print("\n" + "=" * 60)
    print("Civic Unified Ingestion")
    print("=" * 60)
    task_list = []
    if run_municipal:
        task_list.append("municipal")
    if run_legislation:
        task_list.append("legislation")
    if run_meetings:
        task_list.append("meetings")
    if run_issues:
        task_list.append("issues")
    if run_elections:
        task_list.append("elections")
    if run_chunks:
        task_list.append("chunks")
    if run_agenda:
        task_list.append("agenda")
    if run_decisions:
        task_list.append("decisions")
    if run_vectors:
        task_list.append("vectors")
    print(f"Tasks: {' '.join(task_list)}")
    if run_municipal:
        print(f"  Municipal: {jurisdiction}")
    if run_legislation:
        print(f"  Legislation: {legislation_jurisdiction}" + (f" (limit: {legislation_limit})" if legislation_limit else ""))
    if run_meetings:
        print(f"  Meetings: {jurisdiction}" + (" (incremental)" if incremental else ""))
    if run_issues:
        print(f"  Issues: {jurisdiction}" + (" (incremental)" if incremental else ""))
    if run_elections:
        print(f"  Elections: {jurisdiction}")
    if run_chunks:
        print(f"  Chunks: {jurisdiction}" + (f" (limit: {chunks_limit})" if chunks_limit else " (incremental)"))
    if run_agenda:
        print(f"  Agenda: {jurisdiction}" + (f" (limit: {agenda_limit})" if agenda_limit else " (incremental)"))
    if run_decisions:
        print(f"  Decisions: {jurisdiction}" + (f" (limit: {decisions_limit})" if decisions_limit else " (incremental)"))
    if run_vectors:
        print(f"  Vectors: {jurisdiction}")
    print(f"Dry run: {dry_run}")
    print("=" * 60)

    # Spawn tasks in parallel
    handles = []

    if run_municipal:
        print("\nSpawning municipal code fetch...")
        handle = fetch_municipal_code.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
        )
        handles.append(("municipal_code", handle))

    if run_legislation:
        print("Spawning legislation text fetch...")
        handle = fetch_legislation.spawn(
            jurisdiction=legislation_jurisdiction,
            limit=legislation_limit,
            dry_run=dry_run,
        )
        handles.append(("legislation", handle))

    if run_meetings:
        print("Spawning meetings fetch...")
        handle = fetch_meetings.spawn(
            jurisdiction=jurisdiction,
            incremental=incremental,
            dry_run=dry_run,
        )
        handles.append(("meetings", handle))

    if run_issues:
        print("Spawning issues fetch...")
        handle = fetch_issues.spawn(
            jurisdiction=jurisdiction,
            incremental=incremental,
            dry_run=dry_run,
        )
        handles.append(("issues", handle))

    if run_elections:
        print("Spawning elections fetch...")
        handle = fetch_elections.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
        )
        handles.append(("elections", handle))

    # Wait for fetch tasks to complete before chunks and vectors
    # (chunks need meetings fetched, vectors need all data ready)
    fetch_results = {}
    for name, handle in handles:
        print(f"\nWaiting for {name}...")
        result = handle.get()
        fetch_results[name] = result
        print(f"  {name}: {result.get('elapsed_seconds', 0):.1f}s, cost: ${result.get('cost_usd', 0):.4f}")

    # Extract chunks after meetings are fetched
    chunks_result = None
    if run_chunks:
        print("\nRunning chunk extraction...")
        chunks_result = extract_chunks.remote(
            jurisdiction=jurisdiction,
            limit=chunks_limit,
            dry_run=dry_run,
        )
        print(f"  chunks: {chunks_result.get('elapsed_seconds', 0):.1f}s, cost: ${chunks_result.get('cost_usd', 0):.4f}")

    # Extract agenda items after meetings are fetched
    agenda_result = None
    if run_agenda:
        print("\nRunning agenda items extraction...")
        agenda_result = extract_agenda_items.remote(
            jurisdiction=jurisdiction,
            limit=agenda_limit,
            dry_run=dry_run,
        )
        print(f"  agenda: {agenda_result.get('elapsed_seconds', 0):.1f}s, cost: ${agenda_result.get('cost_usd', 0):.4f}")

    # Extract decisions after meetings are fetched (weekly only, not in --all)
    decisions_result = None
    if run_decisions:
        print("\nRunning decision extraction...")
        decisions_result = extract_decisions.remote(
            jurisdiction=jurisdiction,
            limit=decisions_limit,
            dry_run=dry_run,
        )
        print(f"  decisions: {decisions_result.get('elapsed_seconds', 0):.1f}s, cost: ${decisions_result.get('cost_usd', 0):.4f}")

    # Now run vectors (after fetches and chunks complete, so we index all data)
    vector_result = None
    if run_vectors:
        print("\nRunning vector indexing...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="all",
            reindex=reindex,
        )
        print(f"  vectors: {vector_result.get('elapsed_seconds', 0):.1f}s, cost: ${vector_result.get('cost_usd', 0):.4f}")

    # Print summary
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)

    total_cost = 0.0

    for name, result in fetch_results.items():
        cost = result.get("cost_usd", 0)
        total_cost += cost
        if name == "municipal_code":
            print(f"+ Municipal Code: {result.get('sections_fetched', 0)} sections fetched, {result.get('sections_stored', 0)} stored")
        elif name == "legislation":
            print(f"+ Legislation: {result.get('bills_with_text', 0)}/{result.get('bills_processed', 0)} bills processed, {result.get('api_calls', 0)} API calls")
        elif name == "meetings":
            incr = " (incremental)" if result.get("incremental") else ""
            print(f"+ Meetings{incr}: {result.get('meetings_fetched', 0)} fetched, {result.get('meetings_stored', 0)} stored")
        elif name == "issues":
            incr = " (incremental)" if result.get("incremental") else ""
            print(f"+ Issues{incr}: {result.get('issues_fetched', 0)} fetched, {result.get('issues_stored', 0)} stored")
        elif name == "elections":
            print(f"+ Elections: {result.get('elections_fetched', 0)} fetched, {result.get('elections_stored', 0)} stored")

    if chunks_result:
        cost = chunks_result.get("cost_usd", 0)
        total_cost += cost
        extracted = chunks_result.get("meetings_extracted", 0)
        skipped = chunks_result.get("meetings_skipped", 0)
        total_chunks = chunks_result.get("chunks_extracted", 0)
        print(f"+ Chunks: {total_chunks} chunks from {extracted} meetings, {skipped} skipped (already chunked)")

    if agenda_result:
        cost = agenda_result.get("cost_usd", 0)
        total_cost += cost
        extracted = agenda_result.get("meetings_extracted", 0)
        skipped = agenda_result.get("meetings_skipped", 0)
        total_items = agenda_result.get("items_extracted", 0)
        actionable = agenda_result.get("actionable_items", 0)
        print(f"+ Agenda: {total_items} items ({actionable} actionable) from {extracted} meetings, {skipped} skipped")

    if decisions_result:
        cost = decisions_result.get("cost_usd", 0)
        total_cost += cost
        extracted = decisions_result.get("meetings_extracted", 0)
        skipped = decisions_result.get("meetings_skipped", 0)
        total_decisions = decisions_result.get("decisions_extracted", 0)
        print(f"+ Decisions: {total_decisions} decisions from {extracted} meetings, {skipped} skipped")

    if vector_result:
        cost = vector_result.get("cost_usd", 0)
        total_cost += cost
        print(f"+ Vectors: {vector_result.get('total_indexed', 0)} documents indexed")
        for ct, r in vector_result.get("results", {}).items():
            status = "+" if r.get("status") == "success" else ("o" if r.get("status") == "skipped" else "x")
            print(f"    {status} {ct}: {r.get('indexed', 0)} indexed")

    print("=" * 60)
    print(f"Total estimated cost: ${total_cost:.4f}")
    print("=" * 60)
