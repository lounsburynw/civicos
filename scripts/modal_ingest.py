"""
Modal unified ingestion script for Civic data pipeline.

This module provides a single entrypoint for running all data ingestion tasks
in parallel on Modal's serverless compute infrastructure. It orchestrates:
- Municipal code fetch (Municode API)
- Legislation sync (LegiScan API) - master list + text population
- Federal rules fetch (Federal Register API) - proposed rules, final rules, notices
- Legislative events extraction - hearing dates parsed from existing bills
- Meeting discovery (ProudCity API) - supports incremental fetch
- Issue fetch (SeeClickFix API) - supports incremental fetch
- Transcript extraction (AssemblyAI) - downloads audio and transcribes with speaker diarization
- Chunk extraction (PDF parsing) - downloads agenda PDFs and extracts text chunks
- Agenda items extraction (LLM) - extracts actionable items from agendas
- Decision extraction (LLM) - extracts high-stakes decisions from meeting minutes
- Vector indexing (fastembed embeddings)

Architecture:
    modal run scripts/modal_ingest.py --all
    └── spawn() parallel tasks:
        ├── fetch_municipal_code()       → Postgres
        ├── sync_legislation()           → Postgres (master list + text)
        ├── fetch_meetings()             → Postgres (incremental)
        ├── fetch_issues()               → Postgres (incremental)
        ├── extract_transcripts()        → R2 (audio) + Postgres (transcripts), after meetings
        ├── extract_chunks()             → Postgres (incremental, after meetings)
        ├── extract_agenda_items()       → Postgres (LLM-powered)
        └── index_vectors()              → pgvector

    modal run scripts/modal_ingest.py --decisions        # Not in --all (weekly only)
    └── extract_decisions()              → Postgres (LLM-powered, weekly)

    modal run scripts/modal_ingest.py --federal-rules    # Not in --all (weekly only)
    └── fetch_federal_rules()            → Postgres (Federal Register API, free)

    modal run scripts/modal_ingest.py --legislative-events  # Not in --all (weekly only)
    └── extract_legislative_events()     → Postgres (no API calls, parses existing bills)

    Scheduled refreshes (via modal deploy):
        scheduled_low_velocity_refresh()  # Weekly: legislation, EOs, federal rules, legislative events, decisions
        scheduled_high_velocity_refresh() # Daily: meetings, issues, transcripts, chunks, agenda items, vectors
        scheduled_election_refresh()      # Monthly: elections from Google Civic API

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal setup
    3. Create secrets:
       modal secret create civic-db DATABASE_URL="postgresql://..."
       modal secret create civic-legiscan LEGISCAN_API_KEY="..."
       modal secret create civic-assemblyai ASSEMBLYAI_API_KEY="..."
       modal secret create civic-google GOOGLE_API_KEY="..."  # For YouTube, elections, geocoding
       modal secret create civic-notify CIVICOS_NTFY_TOPIC="civicos-admin-XXXX"  # Push notifications (ntfy)
    4. Run: modal run scripts/modal_ingest.py --all
    5. Deploy for scheduled runs: modal deploy scripts/modal_ingest.py

Usage:
    # Run all ingestion (municipal, legislation, transcripts, chunks, vectors)
    modal run scripts/modal_ingest.py --all

    # Run specific components
    modal run scripts/modal_ingest.py --municipal
    modal run scripts/modal_ingest.py --legislation
    modal run scripts/modal_ingest.py --federal-rules
    modal run scripts/modal_ingest.py --legislative-events
    modal run scripts/modal_ingest.py --meetings
    modal run scripts/modal_ingest.py --issues
    modal run scripts/modal_ingest.py --transcripts
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
    - Federal Register API: No quota, no key needed, ~1 req/s rate limit
    - Recommendation: Use --legislation-jurisdiction to run one at a time

Cost Estimates (Modal compute):
    - Municipal code fetch: ~$0.05 (20-30 min, 4GB)
    - Legislation sync: ~$0.20 (1-4 hours, 4GB) - includes master list + text
    - Meeting fetch: ~$0.02 (5 min, 4GB)
    - Issues fetch: ~$0.02 (5 min, 4GB)
    - Vector indexing: ~$0.10 (5-10 min, 16GB)
    - Full --all run: ~$0.40
"""

from typing import Optional

import modal

# Define the Modal app
app = modal.App("civic-ingest")

# Persistent volume for model caching (fastembed downloads ~500MB models)
# This prevents re-downloading on every cold start and avoids cache corruption
model_cache = modal.Volume.from_name("civic-model-cache", create_if_missing=True)

# Build unified image with all dependencies
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2 and audio processing
    .apt_install("libpq-dev", "gcc", "ffmpeg")
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
        "assemblyai>=0.35.0",  # For transcription
        "yt-dlp>=2024.1.0",  # For audio download
        "pysocks>=1.7.0",  # SOCKS5 proxy support for yt-dlp
        "google-api-python-client>=2.0.0",  # For YouTube duration validation
        "python-dotenv>=1.0.0",  # For environment variable loading
        "boto3>=1.34.0",  # For R2 blob storage access
        "openai>=1.0.0",  # For agenda/decision extraction (LLM calls)
        "google-generativeai>=0.8.0",  # For Gemini-based extraction
        "PyPDF2>=3.0.0",  # For agenda PDF text extraction (decision/agenda pipelines)
        "openpyxl>=3.0.0",  # For HUD allocation Excel parsing
        "fastapi>=0.100.0",  # Required by Modal for web endpoints
    )
    # Environment variables (must come before add_local_* per Modal requirements)
    .env({"CIVICOS_CONFIG_DIR": "/config/extraction"})
    # Add local civicos packages (add_local_* must be last)
    .add_local_python_source("civicos", "civicos_config", "civicos_extraction", "civicos_services")
    # Add jurisdiction config files for config-driven pipeline iteration
    .add_local_dir("data/extraction", remote_path="/config/extraction")
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
    auto_index: bool = False,
) -> dict:
    """Fetch complete municipal code from Municode API and store to Postgres.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        dry_run: If True, fetch but don't store
        rate_limit: Seconds between API requests
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time
    from dataclasses import asdict

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
    from civicos.storage.postgres_backend import PostgresBackend

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
        try:
            stored_count = backend.store_municipal_code(jurisdiction_id=jurisdiction, sections=sections)
            logger.info(f"Stored {stored_count} sections")

            backend.update_refresh_metadata(
                jurisdiction, "municipal_code", "municode",
                items_fetched=len(sections),
                items_stored=stored_count,
                status="completed",
            )
        except Exception as e:
            logger.error(f"Error storing municipal code: {e}")
            backend.update_refresh_metadata(
                jurisdiction, "municipal_code", "municode",
                status="failed", error_message=str(e),
            )
            raise

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored_count > 0 and not dry_run:
        logger.info(f"[MUNICIPAL] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="municipal_code",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    cost_usd = 4 * elapsed * 0.000463
    result = {
        "task": "municipal_code",
        "jurisdiction": jurisdiction,
        "sections_fetched": len(sections),
        "sections_with_text": with_text,
        "sections_stored": stored_count,
        "titles": len(titles_seen),
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": cost_usd,
    }
    if vector_result:
        result["vector_result"] = vector_result

    # Log to operating_costs table
    if not dry_run:
        from civicos.cost import log_modal_cost
        log_modal_cost(
            function_name="fetch_municipal_code",
            elapsed_seconds=elapsed,
            memory_gb=4,
            jurisdiction_id=jurisdiction,
            metadata={"sections_stored": stored_count, "titles": len(titles_seen)},
            storage_backend=backend,
        )

    return result


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
    auto_index: bool = False,
) -> dict:
    """Fetch bill text from LegiScan API and store to Postgres.

    Args:
        jurisdiction: Target jurisdiction (e.g., "state-CA")
        limit: Maximum bills to process (None = no limit)
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage
    """
    import base64
    import logging
    import os
    import re
    import time
    import requests

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend

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

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and updates and not dry_run:
        logger.info(f"[LEGISLATION] Auto-indexing vectors for {jurisdiction}...")
        # Legislation uses "legislation-CA" format for vector indexing
        vector_jurisdiction = f"legislation-{state_code}"
        vector_result = index_vectors.remote(
            jurisdiction=vector_jurisdiction,
            corpus="legislation",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    cost_usd = 4 * elapsed * 0.000463
    result = {
        "task": "legislation",
        "jurisdiction": jurisdiction,
        "bills_processed": len(bills_needing_text),
        "bills_with_text": len(updates),
        "api_calls": api_calls,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": cost_usd,
    }
    if vector_result:
        result["vector_result"] = vector_result

    # Log to operating_costs table
    if not dry_run:
        from civicos.cost import log_modal_cost
        log_modal_cost(
            function_name="fetch_legislation",
            elapsed_seconds=elapsed,
            memory_gb=4,
            jurisdiction_id=jurisdiction,
            metadata={"bills_with_text": len(updates), "api_calls": api_calls},
            storage_backend=backend,
        )

    return result


# =============================================================================
# Legislation Sync (Master List + Text Population)
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
def sync_legislation(
    jurisdiction: str = "state-CA",
    dry_run: bool = False,
    skip_text: bool = False,
    auto_index: bool = False,
) -> dict:
    """Sync legislation from LegiScan: discover new bills, update statuses, populate text.

    This is the main function for scheduled legislation refresh. It performs:
    1. Fetch master list from LegiScan (1 API call) - discovers new bills, status updates
    2. Store/upsert bills via store_legislation() with temporal versioning
    3. Optionally populate full_text for bills missing it (via fetch_legislation)
    4. Auto-index vectors for new/updated bills

    Args:
        jurisdiction: Target jurisdiction (e.g., "state-CA", "federal")
        dry_run: If True, validate only - don't store
        skip_text: If True, skip full_text population step (faster sync)
        auto_index: If True, trigger vector indexing after successful storage

    API Quota:
        - getMasterList: 1 API call per state (efficient!)
        - Text population: 2 API calls per bill (only for bills missing text)
        - Running weekly stays well within 30k/month free tier
    """
    import logging
    import os
    import time

    import requests

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend

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

    logger.info(f"[LEGISLATION SYNC] Starting: jurisdiction={jurisdiction}, state={state_code}")

    backend = PostgresBackend(database_url)

    # Get count before sync
    count_before = backend.get_legislation_count(state_code)
    logger.info(f"Bills in database before sync: {count_before}")

    # Step 1: Fetch master list from LegiScan (1 API call)
    logger.info("Fetching master list from LegiScan...")
    try:
        response = requests.get(
            "https://api.legiscan.com/",
            params={"key": legiscan_key, "op": "getMasterList", "state": state_code},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"LegiScan API error: {e}")
        backend.update_refresh_metadata(
            jurisdiction, "legislation", "legiscan",
            status="failed", error_message=str(e),
        )
        return {
            "task": "sync_legislation",
            "jurisdiction": jurisdiction,
            "status": "failed",
            "error": str(e),
        }

    if data.get("status") != "OK":
        logger.error(f"LegiScan API returned status: {data.get('status')}")
        backend.update_refresh_metadata(
            jurisdiction, "legislation", "legiscan",
            status="failed", error_message=f"LegiScan status: {data.get('status')}",
        )
        return {
            "task": "sync_legislation",
            "jurisdiction": jurisdiction,
            "status": "failed",
            "error": f"LegiScan status: {data.get('status')}",
        }

    # Parse master list - format is {session_id: {"0": session_info, "1": bill, "2": bill, ...}}
    master_list = data.get("masterlist", {})
    bills_raw = []
    for key, value in master_list.items():
        if isinstance(value, dict) and value.get("bill_id"):
            bills_raw.append(value)

    logger.info(f"Retrieved {len(bills_raw)} bills from LegiScan master list")

    if not bills_raw:
        logger.warning("No bills returned from master list")
        return {
            "task": "sync_legislation",
            "jurisdiction": jurisdiction,
            "status": "empty",
            "bills_fetched": 0,
        }

    # Step 2: Transform and store bills
    bills_for_storage = []
    for bill in bills_raw:
        bill_number = bill.get("number", "")
        normalized_id = f"{state_code.lower()}-{bill_number.lower().replace(' ', '')}"

        bills_for_storage.append({
            "bill_id": normalized_id,
            "bill_number": bill_number,
            "bill_name": bill.get("title", ""),
            "summary": bill.get("description", ""),
            "status": str(bill.get("status", "")),
            "official_url": bill.get("url", ""),
            "legiscan_id": bill.get("bill_id"),
            "last_action": bill.get("last_action", ""),
            "last_action_date": bill.get("last_action_date"),
            "status_date": bill.get("status_date"),
        })

    if dry_run:
        logger.info(f"[DRY RUN] Would sync {len(bills_for_storage)} bills")
        return {
            "task": "sync_legislation",
            "jurisdiction": jurisdiction,
            "status": "dry_run",
            "bills_fetched": len(bills_for_storage),
        }

    # Store in batches
    batch_size = 500
    total_stored = 0
    for i in range(0, len(bills_for_storage), batch_size):
        batch = bills_for_storage[i:i + batch_size]
        try:
            stored = backend.store_legislation(state=state_code, bills=batch)
            total_stored += stored
            logger.info(f"Stored batch {i // batch_size + 1}: {stored} bills updated/inserted")
        except Exception as e:
            logger.error(f"Error storing batch: {e}")

    count_after = backend.get_legislation_count(state_code)
    new_bills = count_after - count_before
    logger.info(f"Sync complete: {total_stored} bills processed, {new_bills} new bills added")

    # Update refresh metadata
    backend.update_refresh_metadata(
        jurisdiction, "legislation", "legiscan",
        items_fetched=len(bills_for_storage),
        items_stored=total_stored,
        status="completed",
    )

    # Step 3: Populate text for bills missing it (unless skip_text)
    text_result = None
    if not skip_text:
        logger.info("Populating full_text for bills missing it...")
        text_result = fetch_legislation.local(
            jurisdiction=jurisdiction,
            dry_run=False,
            auto_index=False,  # We'll index once at the end
        )
        logger.info(f"Text population: {text_result.get('bills_with_text', 0)} bills updated")

    # Step 4: Auto-index vectors if requested
    vector_result = None
    if auto_index:
        logger.info(f"[LEGISLATION SYNC] Auto-indexing vectors for {jurisdiction}...")
        vector_jurisdiction = f"legislation-{state_code}"
        vector_result = index_vectors.remote(
            jurisdiction=vector_jurisdiction,
            corpus="legislation",
            reindex=False,
        )
        logger.info(f"Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    cost_usd = 4 * elapsed * 0.000463  # 4GB Modal pricing

    result = {
        "task": "sync_legislation",
        "jurisdiction": jurisdiction,
        "status": "success",
        "bills_fetched": len(bills_for_storage),
        "bills_stored": total_stored,
        "new_bills": new_bills,
        "count_before": count_before,
        "count_after": count_after,
        "api_calls_master_list": 1,
        "skip_text": skip_text,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": cost_usd,
    }
    if text_result:
        result["text_result"] = text_result
    if vector_result:
        result["vector_result"] = vector_result

    # Log to operating_costs table
    from civicos.cost import log_modal_cost
    log_modal_cost(
        function_name="sync_legislation",
        elapsed_seconds=elapsed,
        memory_gb=4,
        jurisdiction_id=jurisdiction,
        metadata={
            "bills_fetched": len(bills_for_storage),
            "bills_stored": total_stored,
            "new_bills": new_bills,
        },
        storage_backend=backend,
    )

    return result


# =============================================================================
# Executive Orders (Federal Register API)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=3600,  # 1 hour
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_executive_orders(
    dry_run: bool = False,
    incremental: bool = True,
    days_lookback: int = 30,
    auto_index: bool = False,
) -> dict:
    """Fetch Executive Orders from Federal Register API and store to Postgres.

    Supports incremental fetch using refresh_metadata to track last fetch time.
    EOs have higher velocity than codified law, so weekly refresh is recommended.

    Args:
        dry_run: If True, fetch but don't store
        incremental: If True, only fetch EOs published since last refresh
        days_lookback: Days to look back for initial/full fetch (default 30)
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time
    from datetime import datetime, timedelta

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.federal_register import FederalRegisterClient

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    client = FederalRegisterClient()

    # Determine date filter for incremental fetch
    # Use latest signing_date from existing EOs via public API (get_executive_orders)
    # rather than raw SQL, to maintain protocol compliance and backend portability
    since_date = None
    if incremental:
        # Get most recent EO via public API (returns ordered by signing_date DESC)
        recent_eos = backend.get_executive_orders(limit=1)
        if recent_eos:
            latest_eo = recent_eos[0]
            # Use signing_date as the reference (publication_date may be None)
            latest_date = latest_eo.get("signing_date")
            if latest_date:
                # Add 7-day overlap to catch any delayed publications or republications
                overlap_days = 7
                if hasattr(latest_date, 'strftime'):
                    since_date = (latest_date - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
                else:
                    # Already a string, parse and adjust
                    from datetime import date as date_type
                    parsed = date_type.fromisoformat(str(latest_date)[:10])
                    since_date = (parsed - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
                logger.info(f"[EO] Incremental mode: fetching since {since_date} (latest in DB: {latest_date})")
            else:
                since_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
                logger.info(f"[EO] Initial fetch: looking back {days_lookback} days (since {since_date})")
        else:
            # No existing EOs - use days_lookback
            since_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
            logger.info(f"[EO] Initial fetch: looking back {days_lookback} days (since {since_date})")
    else:
        # Full fetch - use days_lookback
        since_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
        logger.info(f"[EO] Full fetch: looking back {days_lookback} days (since {since_date})")

    # Fetch EOs from Federal Register API
    logger.info("[EO] Fetching Executive Orders from Federal Register...")
    orders = client.fetch_executive_orders(since_date=since_date, per_page=100, max_pages=50)
    logger.info(f"[EO] Fetched {len(orders)} Executive Orders")

    # Store to database
    stored_count = 0
    if orders and not dry_run:
        try:
            stored_count = backend.store_executive_orders(orders)
            logger.info(f"[EO] Stored {stored_count} new Executive Orders (deduped)")

            backend.update_refresh_metadata(
                "federal-US", "executive_orders", "federal_register",
                items_fetched=len(orders),
                items_stored=stored_count,
                status="completed",
            )
        except Exception as e:
            logger.error(f"Error storing executive orders: {e}")
            backend.update_refresh_metadata(
                "federal-US", "executive_orders", "federal_register",
                status="failed", error_message=str(e),
            )
            raise
    elif dry_run:
        logger.info("[EO] Dry run - skipping storage")

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored_count > 0 and not dry_run:
        logger.info("[EO] Auto-indexing vectors for executive_orders...")
        vector_result = index_vectors.remote(
            jurisdiction="federal-US",
            corpus="executive_orders",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "executive_orders",
        "orders_fetched": len(orders),
        "orders_stored": stored_count,
        "since_date": since_date,
        "incremental": incremental,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=512,
    timeout=900,  # 15 min per batch (Federal Register can be slow)
)
def _fetch_eo_text_batch(orders: list[dict]) -> dict:
    """Worker function to fetch full_text for a batch of Executive Orders.

    Called by backfill_executive_orders_text via .map() for parallel processing.
    Each worker handles a small batch with internal rate limiting.
    """
    import os
    import time
    import requests

    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    backend = PostgresBackend(database_url)

    succeeded = 0
    failed = 0
    skipped = 0

    session = requests.Session()
    session.headers.update({"User-Agent": "Civic Conversational OS"})

    for order in orders:
        doc_number = order["document_number"]
        raw_url = order.get("raw_text_url")

        if not raw_url:
            skipped += 1
            continue

        try:
            # Fetch full text
            response = session.get(raw_url, timeout=30)
            if response.status_code == 200 and len(response.text) > 100:
                backend.update_executive_order_text(
                    document_number=doc_number,
                    full_text=response.text,
                )
                succeeded += 1
            else:
                failed += 1
        except Exception:
            failed += 1

        # Light rate limiting within batch (0.1s)
        time.sleep(0.1)

    return {"succeeded": succeeded, "failed": failed, "skipped": skipped}


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=1024,
    timeout=1200,  # 20 min orchestrator timeout
)
def backfill_executive_orders_text(
    dry_run: bool = False,
    num_workers: int = 30,
    max_orders: Optional[int] = None,
) -> dict:
    """Backfill full_text for Executive Orders using parallel workers.

    Fetches full text from raw_text_url for all EOs missing content.
    Uses Modal .map() for parallel processing across multiple workers.

    Args:
        dry_run: If True, report what would be fetched but don't update
        num_workers: Number of parallel workers (default 20)
        max_orders: Maximum orders to process (None for all)

    Returns:
        Summary with counts of processed, succeeded, failed orders
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    # Get orders missing text
    missing_orders = backend.get_executive_orders_missing_text(limit=max_orders)
    logger.info(f"[EO Backfill] Found {len(missing_orders)} orders missing full_text")

    if dry_run:
        return {
            "task": "backfill_executive_orders_text",
            "orders_needing_text": len(missing_orders),
            "dry_run": True,
        }

    if not missing_orders:
        return {
            "task": "backfill_executive_orders_text",
            "orders_processed": 0,
            "message": "No orders need backfill",
        }

    # Split into batches for parallel processing
    batch_size = max(1, len(missing_orders) // num_workers)
    batches = [
        missing_orders[i:i + batch_size]
        for i in range(0, len(missing_orders), batch_size)
    ]
    logger.info(f"[EO Backfill] Dispatching {len(batches)} batches to parallel workers")

    # Run parallel workers
    results = list(_fetch_eo_text_batch.map(batches))

    # Aggregate results
    total_succeeded = sum(r["succeeded"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_skipped = sum(r["skipped"] for r in results)

    elapsed = time.time() - start_time
    logger.info(f"[EO Backfill] Complete: {total_succeeded} succeeded, {total_failed} failed, "
               f"{total_skipped} skipped in {elapsed:.1f}s")

    return {
        "task": "backfill_executive_orders_text",
        "orders_processed": total_succeeded + total_failed + total_skipped,
        "succeeded": total_succeeded,
        "failed": total_failed,
        "skipped": total_skipped,
        "elapsed_seconds": elapsed,
        "num_workers": len(batches),
    }


# =============================================================================
# Federal Rules (Federal Register API — Proposed Rules, Final Rules, Notices)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=3600,  # 1 hour
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_federal_rules(
    dry_run: bool = False,
    incremental: bool = True,
    days_lookback: int = 90,
    auto_index: bool = False,
) -> dict:
    """Fetch federal rulemaking documents from Federal Register API and store to Postgres.

    Fetches three document types:
    - Proposed rules (NPRMs) — have public comment periods
    - Final rules — codified regulations
    - Notices — agency announcements

    Supports incremental fetch using the most recent publication_date in the DB.
    Weekly refresh recommended (low velocity, free API, no key needed).

    Args:
        dry_run: If True, fetch but don't store
        incremental: If True, only fetch rules published since last refresh
        days_lookback: Days to look back for initial/full fetch (default 90)
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time
    from datetime import datetime, timedelta

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.federal_register import FederalRegisterClient

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    client = FederalRegisterClient()

    # Determine date filter for incremental fetch
    since_date = None
    if incremental:
        existing_rules = backend.get_federal_rules(limit=1)
        if existing_rules:
            latest = existing_rules[0]
            pub_date = latest.get("publication_date") or latest.get("created_at")
            if pub_date:
                overlap_days = 14
                if hasattr(pub_date, 'strftime'):
                    since_date = (pub_date - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
                else:
                    from datetime import date as date_type
                    parsed = date_type.fromisoformat(str(pub_date)[:10])
                    since_date = (parsed - timedelta(days=overlap_days)).strftime("%Y-%m-%d")
                logger.info(f"[RULES] Incremental mode: fetching since {since_date} (latest in DB: {pub_date})")
            else:
                since_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
                logger.info(f"[RULES] Initial fetch: looking back {days_lookback} days (since {since_date})")
        else:
            since_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
            logger.info(f"[RULES] Initial fetch: looking back {days_lookback} days (since {since_date})")
    else:
        since_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
        logger.info(f"[RULES] Full fetch: looking back {days_lookback} days (since {since_date})")

    # Fetch all three rule types from Federal Register API
    all_rules = []
    for rule_type, method in [
        ("proposed rules", client.get_proposed_rules),
        ("final rules", client.get_final_rules),
        ("notices", client.get_notices),
    ]:
        logger.info(f"[RULES] Fetching {rule_type}...")
        rules = method(since_date=since_date, per_page=100, max_pages=20)
        logger.info(f"[RULES] Fetched {len(rules)} {rule_type}")
        all_rules.extend(rules)

    logger.info(f"[RULES] Total fetched: {len(all_rules)} rules across all types")

    # Store to database
    stored_count = 0
    if all_rules and not dry_run:
        try:
            stored_count = backend.store_federal_rules(all_rules)
            logger.info(f"[RULES] Stored {stored_count} new rules (deduped)")

            backend.update_refresh_metadata(
                "federal-US", "federal_rules", "federal_register",
                items_fetched=len(all_rules),
                items_stored=stored_count,
                status="completed",
            )
        except Exception as e:
            logger.error(f"Error storing federal rules: {e}")
            backend.update_refresh_metadata(
                "federal-US", "federal_rules", "federal_register",
                status="failed", error_message=str(e),
            )
            raise
    elif dry_run:
        logger.info("[RULES] Dry run - skipping storage")

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored_count > 0 and not dry_run:
        logger.info("[RULES] Auto-indexing vectors for federal_rules...")
        vector_result = index_vectors.remote(
            jurisdiction="federal-US",
            corpus="federal_rules",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "federal_rules",
        "rules_fetched": len(all_rules),
        "rules_stored": stored_count,
        "since_date": since_date,
        "incremental": incremental,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# Legislative Events (Hearing dates parsed from existing legislation)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=1800,  # 30 min
)
def extract_legislative_events(
    state: str = "CA",
    dry_run: bool = False,
) -> dict:
    """Extract legislative events (hearings) from existing bill data in Postgres.

    Reads bills already stored in the legislation table and parses last_action
    text for hearing dates and committee references. No external API calls needed.

    Args:
        state: State code to process (default "CA")
        dry_run: If True, parse but don't store
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.legiscan import parse_hearing_events_from_legislation

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    # Read existing bills (no API calls)
    logger.info(f"[EVENTS] Reading {state} legislation from database...")
    bills = backend.get_legislation(state=state, limit=5000)
    logger.info(f"[EVENTS] Read {len(bills)} bills")

    # Parse hearing events from bill data
    events = parse_hearing_events_from_legislation(bills, state=state)
    logger.info(f"[EVENTS] Parsed {len(events)} hearing events from bill actions")

    # Store to database
    stored_count = 0
    if events and not dry_run:
        try:
            stored_count = backend.store_legislative_events(events)
            logger.info(f"[EVENTS] Stored {stored_count} legislative events (deduped)")
        except Exception as e:
            logger.error(f"Error storing legislative events: {e}")
            raise
    elif dry_run:
        logger.info("[EVENTS] Dry run - skipping storage")

    elapsed = time.time() - start_time
    result = {
        "task": "legislative_events",
        "state": state,
        "bills_read": len(bills),
        "events_parsed": len(events),
        "events_stored": stored_count,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    return result


# =============================================================================
# Federal Programs (SAM.gov Assistance Listings)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=3600,  # 1 hour (CSV download + parsing)
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_federal_programs(
    dry_run: bool = False,
    force_refresh: bool = False,
    auto_index: bool = False,
) -> dict:
    """
    Fetch all federal program definitions from SAM.gov Assistance Listings.

    Downloads the complete catalog (~2,300 programs) from GSA's public CSV
    and stores to PostgreSQL. This replaces the manually curated subset with
    authoritative federal data.

    The CSV is cached for 24 hours locally, but force_refresh=True will
    re-download regardless.

    Args:
        dry_run: If True, fetch and parse but don't store to database
        force_refresh: If True, bypass cache and re-download CSV
        auto_index: If True, trigger vector indexing after successful storage

    Returns:
        dict with task results including programs_fetched, programs_stored
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.sam_assistance import (
        SAMAssistanceClient,
        sam_program_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info("[FEDERAL PROGRAMS] Starting SAM.gov Assistance Listings fetch")

    # Initialize client with short cache if force_refresh
    cache_max_age = 0.001 if force_refresh else 24.0  # 24 hours default
    client = SAMAssistanceClient(cache_max_age_hours=cache_max_age)

    # Validate connectivity
    validation = client.validate()
    if not validation.is_valid:
        raise RuntimeError(f"SAM.gov validation failed: {validation.errors}")

    # Fetch all programs
    logger.info("Fetching all programs from SAM.gov...")
    client._load_programs()  # Force load into cache
    programs_fetched = client.get_program_count()
    logger.info(f"  Fetched {programs_fetched} programs")

    # Convert to storage format
    logger.info("Converting to storage format...")
    storage_programs = []
    for aln, listing in client._program_cache.items():
        try:
            storage_programs.append(sam_program_to_storage(listing))
        except Exception as e:
            logger.warning(f"  Error converting {aln}: {e}")

    logger.info(f"  Converted {len(storage_programs)} programs")

    # Store to database
    stored = 0
    if not dry_run:
        logger.info("Storing to PostgreSQL...")
        backend = PostgresBackend(database_url)
        try:
            stored = backend.store_federal_programs(storage_programs)
            logger.info(f"  Stored {stored} programs")

            backend.update_refresh_metadata(
                "federal-US", "programs", "sam_gov",
                items_fetched=programs_fetched,
                items_stored=stored,
                status="completed",
            )
        except Exception as e:
            logger.error(f"Error storing federal programs: {e}")
            backend.update_refresh_metadata(
                "federal-US", "programs", "sam_gov",
                status="failed", error_message=str(e),
            )
            raise
    else:
        logger.info("  [DRY RUN] Skipping storage")

    # Get agency breakdown
    agency_counts: dict = {}
    for p in storage_programs:
        agency = p.get("administering_agency", "UNKNOWN")
        agency_counts[agency] = agency_counts.get(agency, 0) + 1

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored > 0 and not dry_run:
        logger.info("[FEDERAL PROGRAMS] Auto-indexing vectors...")
        vector_result = index_vectors.remote(
            jurisdiction="federal-US",
            corpus="programs",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "federal_programs",
        "programs_fetched": programs_fetched,
        "programs_converted": len(storage_programs),
        "programs_stored": stored,
        "dry_run": dry_run,
        "force_refresh": force_refresh,
        "auto_index": auto_index,
        "agency_breakdown": dict(sorted(agency_counts.items(), key=lambda x: -x[1])[:10]),
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# HUD Allocations (CDBG, HOME, ESG, etc.)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=2048,
    timeout=1800,  # 30 min (Excel downloads)
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_hud_allocations(
    jurisdiction: str = "",
    grantee_name: str = "",
    dry_run: bool = False,
) -> dict:
    """
    Fetch HUD CPD formula allocations (CDBG, HOME, ESG, etc.) from HUD.gov.

    Downloads official HUD Excel spreadsheets for each fiscal year and extracts
    allocations for the specified grantee (e.g., Marin County for San Rafael).

    Auto-detects new fiscal years by checking if the expected URL exists.
    This allows automatic ingestion when FY2026+ allocations are published.

    If jurisdiction is provided without grantee_name, loads grantee from
    jurisdiction config (data/extraction/{jurisdiction}.json).

    Args:
        jurisdiction: Target Civic jurisdiction (e.g., "city-san-rafael")
        grantee_name: HUD grantee name (e.g., "Marin County" for consortium cities).
                      If empty, loads from jurisdiction config.
        dry_run: If True, fetch and parse but don't store to database

    Returns:
        dict with task results including allocations fetched/stored per fiscal year
    """
    import logging
    import os
    import time

    import requests

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.hud_exchange import (
        HUDExchangeClient,
        HUD_ALLOCATION_URLS,
        hud_allocation_to_storage,
    )
    from civicos_extraction.config import get_hud_grantee, get_hud_relationship

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Load grantee from config if not explicitly provided
    if not grantee_name and jurisdiction:
        grantee_name = get_hud_grantee(jurisdiction)
        if not grantee_name:
            return {
                "task": "hud_allocations",
                "jurisdiction": jurisdiction,
                "error": f"No HUD grantee configured for {jurisdiction}. Add federal_programs.hud_grantee to jurisdiction config.",
                "elapsed_seconds": time.time() - start_time,
            }

    if not jurisdiction or not grantee_name:
        return {
            "task": "hud_allocations",
            "error": "Must provide jurisdiction (and optionally grantee_name, or configure in jurisdiction config)",
            "elapsed_seconds": time.time() - start_time,
        }

    # Get HUD relationship type from config
    hud_relationship = get_hud_relationship(jurisdiction) or "unknown"

    logger.info(f"[HUD ALLOCATIONS] Starting fetch for {jurisdiction} (grantee: {grantee_name}, relationship: {hud_relationship})")

    # Auto-detect available fiscal years (check for new years beyond configured)
    current_year = 2026  # Update annually or compute from date
    available_years = set(HUD_ALLOCATION_URLS.keys())

    # Check for new fiscal years not yet in HUD_ALLOCATION_URLS
    url_pattern = "https://www.hud.gov/sites/dfiles/CPD/documents/FY{year}-Formula-Allocations-All-Grantees.xlsx"
    new_years_found = []

    for year in range(max(available_years) + 1, current_year + 2):  # Check up to FY+1
        test_url = url_pattern.format(year=year)
        try:
            response = requests.head(test_url, timeout=10)
            if response.status_code == 200:
                logger.info(f"  Discovered new fiscal year: FY{year}")
                available_years.add(year)
                new_years_found.append(year)
        except requests.RequestException:
            pass  # URL not available yet

    if new_years_found:
        logger.info(f"  New fiscal years detected: {new_years_found}")

    # Initialize client
    client = HUDExchangeClient()

    # Fetch allocations for all available years
    all_allocations = []
    years_fetched = {}

    for year in sorted(available_years, reverse=True):
        try:
            allocations = client.get_allocations(grantee_name, fiscal_year=year)
            if allocations:
                for a in allocations:
                    storage_record = hud_allocation_to_storage(a, jurisdiction)
                    # Add consortium metadata based on HUD relationship
                    if hud_relationship == "consortium":
                        storage_record["local_allocation_model"] = "joint_county"
                        storage_record["allocation_note"] = (
                            f"Receives HUD funds via {grantee_name} consortium. "
                            f"County-wide allocation; local share per consortium agreement."
                        )
                        storage_record["metadata"]["consortium"] = f"{grantee_name} Urban County Program"
                        storage_record["metadata"]["entitlement_grantee"] = a.grantee_name
                    all_allocations.append(storage_record)
                years_fetched[year] = len(allocations)
                logger.info(f"  FY{year}: {len(allocations)} allocations")
        except Exception as e:
            logger.warning(f"  FY{year}: Failed to fetch - {e}")
            years_fetched[year] = f"error: {e}"

    logger.info(f"  Total allocations: {len(all_allocations)}")

    # Store to database
    stored = 0
    if not dry_run and all_allocations:
        logger.info("Storing to PostgreSQL...")
        backend = PostgresBackend(database_url)
        stored = backend.store_federal_program_allocations(jurisdiction, all_allocations)
        logger.info(f"  Stored {stored} allocations")
    elif dry_run:
        logger.info("  [DRY RUN] Skipping storage")

    elapsed = time.time() - start_time
    return {
        "task": "hud_allocations",
        "jurisdiction": jurisdiction,
        "grantee_name": grantee_name,
        "hud_relationship": hud_relationship,
        "years_fetched": years_fetched,
        "new_years_discovered": new_years_found,
        "allocations_total": len(all_allocations),
        "allocations_stored": stored,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
    }


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=2048,
    timeout=3600,  # 1 hour (multiple jurisdictions)
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_all_hud_allocations(dry_run: bool = False) -> dict:
    """
    Fetch HUD allocations for ALL configured jurisdictions.

    Iterates over all jurisdiction configs that have federal_programs.hud_grantee
    defined and fetches allocations for each.

    Args:
        dry_run: If True, fetch and parse but don't store to database

    Returns:
        dict with results per jurisdiction
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos_extraction.config import get_jurisdictions_with_hud_config

    # Get all jurisdictions with HUD config
    jurisdictions = get_jurisdictions_with_hud_config()

    if not jurisdictions:
        return {
            "task": "fetch_all_hud_allocations",
            "error": "No jurisdictions found with HUD config. Add federal_programs.hud_grantee to jurisdiction configs.",
            "elapsed_seconds": time.time() - start_time,
        }

    logger.info(f"[HUD ALLOCATIONS] Found {len(jurisdictions)} jurisdictions with HUD config")

    results = {}
    total_stored = 0
    new_years_all = []

    for config in jurisdictions:
        jid = config.get("jurisdiction_id")
        grantee = config.get("federal_programs", {}).get("hud_grantee")

        logger.info(f"  Processing {jid} (grantee: {grantee})...")

        try:
            result = fetch_hud_allocations.local(
                jurisdiction=jid,
                grantee_name=grantee,
                dry_run=dry_run,
            )
            results[jid] = result
            total_stored += result.get("allocations_stored", 0)
            new_years_all.extend(result.get("new_years_discovered", []))
        except Exception as e:
            logger.exception(f"  Failed for {jid}")
            results[jid] = {"error": str(e)}

    elapsed = time.time() - start_time
    return {
        "task": "fetch_all_hud_allocations",
        "jurisdictions_processed": len(jurisdictions),
        "total_allocations_stored": total_stored,
        "new_years_discovered": list(set(new_years_all)),
        "results": results,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
    }


# =============================================================================
# Vector Indexing (Parallel)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=65536,  # 64GB per worker (fastembed uses CPU, memory is the bottleneck)
    timeout=900,  # 15 min per batch (CPU-only, increased from 10 min for safety)
    volumes={"/cache": model_cache},  # Persistent model cache
)
def _embed_and_store_batch(
    chunks: list[dict],
    jurisdiction_id: str,
    corpus_type: str,
    reindex: bool = False,
) -> dict:
    """Worker function to embed and store a batch of chunks.

    Called by index_vectors via .map() for parallel processing.
    Each worker embeds its batch and inserts via public PgVectorBackend methods.

    When reindex=False, uses upsert (ON CONFLICT) to handle existing vectors.
    When reindex=True, uses COPY for speed (caller must delete existing vectors first).
    """
    import logging
    import os
    import hashlib

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    # Use persistent volume for fastembed model cache
    # Must be set before PgVectorBackend loads the embedding model
    os.environ["FASTEMBED_CACHE_PATH"] = "/cache/fastembed"

    from civicos.storage.pgvector_backend import PgVectorBackend

    database_url = os.environ.get("DATABASE_URL")
    pgvector = PgVectorBackend(connection_string=database_url, provider_type="fastembed")

    # Extract text content for embedding
    texts = []
    for chunk in chunks:
        if corpus_type == "budget_items":
            # Budget items have special text extraction
            parts = []
            if chunk.get("department"):
                parts.append(f"Department: {chunk['department']}")
            if chunk.get("fund"):
                parts.append(f"Fund: {chunk['fund']}")
            if chunk.get("program"):
                parts.append(f"Program: {chunk['program']}")
            if chunk.get("line_item"):
                parts.append(f"Line Item: {chunk['line_item']}")
            if chunk.get("notes"):
                parts.append(f"Notes: {chunk['notes']}")
            if chunk.get("fiscal_year"):
                parts.append(f"Fiscal Year: {chunk['fiscal_year']}")
            content = "\n".join(parts) if parts else ""
        else:
            content = chunk.get("content") or chunk.get("text") or chunk.get("title", "")
        texts.append(content)

    # Generate embeddings using public interface
    embeddings = pgvector.encode_texts(texts, batch_size=len(texts))

    # Build records for bulk insert
    records = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # Generate deterministic ID based on corpus type
        if corpus_type == "budget_items":
            # Budget items use item_id as the unique identifier
            chunk_id = chunk.get("item_id") or f"budget-{chunk.get('id', idx)}"
            content = texts[idx]  # Use pre-computed content
        else:
            content = chunk.get("content") or chunk.get("text") or chunk.get("title", "")
            chunk_id = chunk.get("id") or hashlib.sha256(
                f"{jurisdiction_id}:{corpus_type}:{content[:200]}".encode()
            ).hexdigest()[:32]

        # Extract metadata
        meeting_id = chunk.get("meeting_id")
        if corpus_type == "budget_items":
            # Budget items: use department + line_item as display title
            meeting_title = f"{chunk.get('department', '')} - {chunk.get('line_item', '')}"
            # Include budget-specific fields in metadata for retrieval
            metadata = {
                "budgeted_cents": chunk.get("budgeted_cents"),
                "revised_cents": chunk.get("revised_cents"),
                "actual_cents": chunk.get("actual_cents"),
                "fiscal_year": chunk.get("fiscal_year"),
                "fund": chunk.get("fund"),
                "department": chunk.get("department"),
                "program": chunk.get("program"),
                "source_url": chunk.get("source_url"),
                "source_page": chunk.get("source_page"),
            }
        else:
            meeting_title = chunk.get("meeting_title")
            metadata = chunk.get("metadata", {})

        records.append({
            "id": chunk_id,
            "content": content,
            "embedding": embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "meeting_datetime": chunk.get("meeting_datetime"),
            "metadata": metadata,
        })

    # Bulk insert using public interface
    # COPY is faster but requires no duplicate IDs (safe only when reindexing).
    # Upsert (ON CONFLICT) is needed for incremental indexing.
    result = pgvector.bulk_insert_embeddings(
        records=records,
        jurisdiction_id=jurisdiction_id,
        corpus_type=corpus_type,
        use_copy=reindex,
    )
    logger.info(f"Inserted {result['success']} embeddings")
    return result


def _embed_and_store_inline(
    chunks: list[dict],
    jurisdiction_id: str,
    corpus_type: str,
    reindex: bool,
    pgvector,
) -> dict:
    """Embed and store a small corpus inline (no worker containers).

    Same logic as _embed_and_store_batch but runs inside the orchestrator,
    avoiding the overhead of spawning 64GB worker containers for small corpora.
    """
    import hashlib
    import logging

    logger = logging.getLogger(__name__)

    texts = []
    for chunk in chunks:
        if corpus_type == "budget_items":
            parts = []
            if chunk.get("department"):
                parts.append(f"Department: {chunk['department']}")
            if chunk.get("fund"):
                parts.append(f"Fund: {chunk['fund']}")
            if chunk.get("program"):
                parts.append(f"Program: {chunk['program']}")
            if chunk.get("line_item"):
                parts.append(f"Line Item: {chunk['line_item']}")
            if chunk.get("notes"):
                parts.append(f"Notes: {chunk['notes']}")
            if chunk.get("fiscal_year"):
                parts.append(f"Fiscal Year: {chunk['fiscal_year']}")
            content = "\n".join(parts) if parts else ""
        else:
            content = chunk.get("content") or chunk.get("text") or chunk.get("title", "")
        texts.append(content)

    embeddings = pgvector.encode_texts(texts, batch_size=len(texts))

    records = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        if corpus_type == "budget_items":
            chunk_id = chunk.get("item_id") or f"budget-{chunk.get('id', idx)}"
            content = texts[idx]
        else:
            content = chunk.get("content") or chunk.get("text") or chunk.get("title", "")
            chunk_id = chunk.get("id") or hashlib.sha256(
                f"{jurisdiction_id}:{corpus_type}:{content[:200]}".encode()
            ).hexdigest()[:32]

        meeting_id = chunk.get("meeting_id")
        if corpus_type == "budget_items":
            meeting_title = f"{chunk.get('department', '')} - {chunk.get('line_item', '')}"
            metadata = {
                "budgeted_cents": chunk.get("budgeted_cents"),
                "revised_cents": chunk.get("revised_cents"),
                "actual_cents": chunk.get("actual_cents"),
                "fiscal_year": chunk.get("fiscal_year"),
                "fund": chunk.get("fund"),
                "department": chunk.get("department"),
                "program": chunk.get("program"),
                "source_url": chunk.get("source_url"),
                "source_page": chunk.get("source_page"),
            }
        else:
            meeting_title = chunk.get("meeting_title")
            metadata = chunk.get("metadata", {})

        records.append({
            "id": chunk_id,
            "content": content,
            "embedding": embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "meeting_datetime": chunk.get("meeting_datetime"),
            "metadata": metadata,
        })

    result = pgvector.bulk_insert_embeddings(
        records=records,
        jurisdiction_id=jurisdiction_id,
        corpus_type=corpus_type,
        use_copy=reindex,
    )
    logger.info(f"  Inline indexed {result['success']} embeddings ({result['failed']} failed)")
    return result


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=65536,  # 64GB for orchestrator (loads all chunks)
    timeout=1800,  # 30 min total
    volumes={"/cache": model_cache},  # For inline embedding (small corpora)
)
def index_vectors(
    jurisdiction: str = "city-san-rafael",
    corpus: str = "all",
    reindex: bool = False,
    num_workers: int = 40,  # CPU-only workers (no GPU concurrency limit applies)
) -> dict:
    """Generate embeddings and store to pgvector using parallel workers.

    For small corpora (< 500 items), embeds inline to avoid spawning
    dozens of 64GB worker containers for trivial workloads.
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    # Set fastembed cache path (shared volume, same as workers)
    os.environ["FASTEMBED_CACHE_PATH"] = "/cache/fastembed"

    from civicos.storage import get_storage_backend
    from civicos.storage.pgvector_backend import PgVectorBackend
    from civicos._internal.meetings.transcript import expand_transcripts_to_chunks
    from civicos._internal.legal.embeddings.chunker import (
        expand_municipal_code_to_chunks,
        expand_legislation_to_chunks,
        expand_executive_orders_to_chunks,
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

    # Determine corpus types based on jurisdiction
    if jurisdiction.startswith("state-"):
        all_corpus_types = ["legislation"]
    elif jurisdiction.startswith("federal-"):
        all_corpus_types = ["programs", "executive_orders"]  # Federal programs + EOs
    else:
        all_corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues", "agenda_items", "budget_items"]

    corpus_types = all_corpus_types if corpus == "all" else [corpus]
    results = {}

    for ct in corpus_types:
        logger.info(f"Processing corpus: {ct}")

        if reindex:
            deleted = pgvector.delete_index(jurisdiction, ct)
            logger.info(f"  Deleted {deleted} existing vectors")

        # Fetch and expand documents to chunks
        if ct == "decisions":
            chunks = backend.get_decisions(jurisdiction)
        elif ct == "chunks":
            chunks = backend.get_chunks(jurisdiction)
        elif ct == "meetings":
            chunks = backend.get_meetings(jurisdiction)
        elif ct == "transcripts":
            raw = backend.get_transcripts(jurisdiction)
            chunks = expand_transcripts_to_chunks(raw)

            # Build video_id → meeting_id lookup for proper meeting linkage
            # Transcript chunks have video_id but need actual meeting_id
            video_to_meeting = backend.get_video_meeting_mapping(jurisdiction)

            if video_to_meeting:
                logger.info(f"  Built video→meeting lookup: {len(video_to_meeting)} mappings")
                # Enrich chunks with meeting_id
                for chunk in chunks:
                    video_id = chunk.get("video_id")
                    if video_id and video_id in video_to_meeting:
                        chunk["meeting_id"] = video_to_meeting[video_id]
        elif ct == "municipal_code":
            raw = backend.get_municipal_code(jurisdiction)
            chunks = expand_municipal_code_to_chunks(raw)
        elif ct == "issues":
            chunks = backend.get_issues(jurisdiction)
        elif ct == "legislation":
            state_code = jurisdiction.split("-")[-1].upper()
            raw = backend.get_legislation(state=state_code)
            chunks = expand_legislation_to_chunks(raw)
        elif ct == "executive_orders":
            raw = backend.get_executive_orders()
            chunks = expand_executive_orders_to_chunks(raw)
        elif ct == "agenda_items":
            chunks = backend.get_agenda_items(jurisdiction_id=jurisdiction)
        elif ct == "programs":
            chunks = backend.get_programs()
        elif ct == "budget_items":
            chunks = backend.get_budget_items(jurisdiction)
        else:
            logger.warning(f"Unknown corpus type: {ct}")
            continue

        if not chunks:
            logger.warning(f"  No chunks found for {ct}")
            results[ct] = {"status": "skipped", "indexed": 0}
            continue

        # Fast path: embed inline for small corpora (avoids spawning dozens of
        # 64GB worker containers for trivial workloads like 60 decisions).
        # Threshold of 500 covers decisions, meetings, budget_items, agenda_items.
        INLINE_THRESHOLD = 500
        if len(chunks) <= INLINE_THRESHOLD:
            logger.info(f"  {len(chunks)} chunks — embedding inline (below {INLINE_THRESHOLD} threshold)")
            worker_result = _embed_and_store_inline(chunks, jurisdiction, ct, reindex, pgvector)
            total_success = worker_result["success"]
            total_failed = worker_result["failed"]
            num_batches = 0
        else:
            logger.info(f"  {len(chunks)} chunks — dispatching to {num_workers} parallel workers")

            # Split into batches for parallel processing
            batch_size = max(1, len(chunks) // num_workers)
            batches = [
                (chunks[i:i + batch_size], jurisdiction, ct, reindex)
                for i in range(0, len(chunks), batch_size)
            ]

            # Run parallel workers
            worker_results = list(_embed_and_store_batch.starmap(batches))

            # Aggregate results
            total_success = sum(r["success"] for r in worker_results)
            total_failed = sum(r["failed"] for r in worker_results)
            num_batches = len(batches)

        results[ct] = {
            "status": "success" if total_failed == 0 else "partial",
            "indexed": total_success,
            "failed": total_failed,
            "workers": num_batches,
        }
        logger.info(f"  Indexed {total_success} chunks ({total_failed} failed)")

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
    auto_index: bool = False,
) -> dict:
    """Fetch meetings from ProudCity API with optional incremental mode.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        days_past: Days to look back for meetings (default 30)
        days_ahead: Days to look ahead for meetings (default 90)
        incremental: If True, use refresh_metadata to determine date range
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time
    from datetime import datetime, timedelta

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend

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
        from civicos_extraction.clients.proudcity import ProudCityClient
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
    store_result = None
    if not dry_run and meetings:
        # Convert Meeting objects to dicts for storage
        meeting_dicts = [m.to_dict() if hasattr(m, 'to_dict') else m.__dict__ for m in meetings]
        store_result = backend.store_meetings(jurisdiction, meeting_dicts)
        stored_count = int(store_result)
        logger.info(f"Stored {stored_count} meetings")
        if store_result.new_meeting_ids:
            logger.info(f"  New meetings: {store_result.new_meeting_ids}")
        if store_result.minutes_appeared:
            logger.info(f"  Minutes appeared: {store_result.minutes_appeared}")
        if store_result.video_appeared:
            logger.info(f"  Video appeared: {store_result.video_appeared}")
        if store_result.agenda_appeared:
            logger.info(f"  Agenda appeared: {store_result.agenda_appeared}")

        # Update refresh metadata
        backend.update_refresh_metadata(
            jurisdiction, "meetings", "proudcity",
            items_fetched=len(meetings),
            items_stored=stored_count,
            status="completed",
            fetch_window_days=days_past,
        )

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored_count > 0 and not dry_run:
        logger.info(f"[MEETINGS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="meetings",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "meetings",
        "jurisdiction": jurisdiction,
        "meetings_fetched": len(meetings),
        "meetings_stored": stored_count,
        "incremental": incremental,
        "days_past": days_past,
        "days_ahead": days_ahead,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
        # Change manifest for reactive pipelines
        "new_meeting_ids": store_result.new_meeting_ids if store_result else [],
        "updated_meeting_ids": store_result.updated_meeting_ids if store_result else [],
        "minutes_appeared_ids": store_result.minutes_appeared if store_result else [],
        "video_appeared_ids": store_result.video_appeared if store_result else [],
        "agenda_appeared_ids": store_result.agenda_appeared if store_result else [],
        "has_new_material": store_result.has_new_material if store_result else False,
        "has_minutes_updates": store_result.has_minutes_updates if store_result else False,
        "has_video_updates": store_result.has_video_updates if store_result else False,
        "has_agenda_updates": store_result.has_agenda_updates if store_result else False,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# YouTube Video Fetch (for school districts and YouTube-based jurisdictions)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-google"),  # GOOGLE_API_KEY for YouTube Data API
    ],
    memory=2048,
    timeout=600,  # 10 minutes
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_videos(
    jurisdiction: str = "school-san-rafael",
    dry_run: bool = False,
) -> dict:
    """Fetch YouTube videos for a jurisdiction with YouTube playlist config.

    This function is designed for jurisdictions like school districts that have
    meetings recorded on YouTube but no Legistar/ProudCity integration.

    Pipeline Integration:
        Run this BEFORE extract_transcripts() to discover videos that can be
        transcribed. The videos are stored to the 'videos' table, which is then
        read by the audio download step of extract_transcripts().

    Args:
        jurisdiction: Target jurisdiction (e.g., "school-san-rafael")
        dry_run: If True, fetch but don't store

    Returns:
        dict with task info, videos_discovered, videos_stored counts
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.youtube_boards import YouTubeBoardsSource

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    logger.info(f"[VIDEOS] Starting YouTube fetch: jurisdiction={jurisdiction}")

    # Get videos from YouTube playlist
    try:
        source = YouTubeBoardsSource.from_jurisdiction(jurisdiction)
        youtube_videos = source.client.get_videos()
        logger.info(f"  Discovered {len(youtube_videos)} videos from YouTube playlist")
    except Exception as e:
        logger.error(f"Error fetching videos: {e}")
        raise

    if not youtube_videos:
        elapsed = time.time() - start_time
        return {
            "task": "videos",
            "jurisdiction": jurisdiction,
            "videos_discovered": 0,
            "videos_stored": 0,
            "dry_run": dry_run,
            "elapsed_seconds": elapsed,
            "cost_usd": 2 * elapsed * 0.000463,
        }

    # Convert to storage format
    storage_videos = []
    for v in youtube_videos:
        storage_videos.append({
            "video_id": v.video_id,
            "title": v.title,
            "date": v.published_at.strftime("%Y-%m-%d"),
            "youtube_url": v.watch_url,
            "meeting_url": None,
        })

    if dry_run:
        logger.info(f"  [DRY RUN] Would store {len(storage_videos)} videos")
        elapsed = time.time() - start_time
        return {
            "task": "videos",
            "jurisdiction": jurisdiction,
            "videos_discovered": len(youtube_videos),
            "videos_stored": 0,
            "dry_run": dry_run,
            "elapsed_seconds": elapsed,
            "cost_usd": 2 * elapsed * 0.000463,
        }

    # Store videos
    videos_stored = backend.store_videos(jurisdiction, storage_videos)
    logger.info(f"  Stored {videos_stored} videos")

    elapsed = time.time() - start_time
    logger.info(f"[VIDEOS] Complete in {elapsed:.1f}s")

    return {
        "task": "videos",
        "jurisdiction": jurisdiction,
        "videos_discovered": len(youtube_videos),
        "videos_stored": videos_stored,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
    }


# =============================================================================
# YouTube Video Discovery (ProudCity jurisdictions)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=2048,
    timeout=600,  # 10 minutes
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def discover_videos(
    jurisdiction: str = "city-san-rafael",
    days_past: int = 7,
    days_ahead: int = 30,
    dry_run: bool = False,
) -> dict:
    """Discover YouTube videos by scraping meeting pages for ProudCity jurisdictions.

    Scrapes each meeting page's HTML for embedded YouTube video IDs.
    Stores discovered videos to the 'videos' table so extract_transcripts()
    can find them for audio download and transcription.

    Pipeline Integration:
        Runs AFTER fetch_meetings() (which discovers meeting pages) and
        BEFORE extract_transcripts() (which needs video records to download audio).

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        days_past: Days to look back for meetings (default 7 for daily refresh)
        days_ahead: Days to look ahead for meetings (default 30)
        dry_run: If True, discover but don't store
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"[VIDEOS] Starting YouTube discovery: jurisdiction={jurisdiction}, days_past={days_past}, days_ahead={days_ahead}")

    from civicos_extraction.cli.youtube import run_youtube_discovery

    results = run_youtube_discovery(
        jurisdiction_id=jurisdiction,
        days_past=days_past,
        days_ahead=days_ahead,
        output_dir="data",
        checkpoint_dir="data/checkpoints",
        timeout=10,
        dry_run=dry_run,
        cloud=True,
    )

    videos_discovered = len(results) if results else 0
    elapsed = time.time() - start_time
    logger.info(f"[VIDEOS] Complete in {elapsed:.1f}s: {videos_discovered} videos discovered")

    return {
        "task": "discover_videos",
        "jurisdiction": jurisdiction,
        "videos_discovered": videos_discovered,
        "days_past": days_past,
        "days_ahead": days_ahead,
        "dry_run": dry_run,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
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
    auto_index: bool = False,
) -> dict:
    """Fetch 311 issues from SeeClickFix API with optional incremental mode.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        max_pages: Maximum pages to fetch (default 50)
        per_page: Issues per page (default 100, max 100)
        incremental: If True, use refresh_metadata to determine starting page
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time
    from datetime import datetime

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_services.clients.seeclickfix_client import SeeClickFixClient

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

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored_count > 0 and not dry_run:
        logger.info(f"[ISSUES] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="issues",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "issues",
        "jurisdiction": jurisdiction,
        "issues_fetched": len(all_issues),
        "issues_stored": stored_count,
        "pages_fetched": current_page,
        "incremental": incremental,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


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
    auto_index: bool = False,
) -> dict:
    """Fetch elections from Google Civic API and store to Postgres.

    This fetches all available elections from Google's Civic Information API
    and stores them for the specified jurisdiction. Elections include
    national, state, and local races.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage

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

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.google_civic import (
        GoogleCivicClient,
        google_civic_to_election,
    )

    database_url = os.environ.get("DATABASE_URL")
    google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_CIVICOS_API_KEY")

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

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and stored_count > 0 and not dry_run:
        logger.info(f"[ELECTIONS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="elections",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "elections",
        "jurisdiction": jurisdiction,
        "elections_fetched": len(elections),
        "elections_stored": stored_count,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-legiscan"),  # LEGISCAN_API_KEY for state legislators
        modal.Secret.from_name("civic-congress"),  # FAC_API_KEY for federal representatives
    ],
    memory=4096,
    timeout=300,  # 5 minutes
)
def fetch_elected_officials(
    jurisdiction: str = "city-san-rafael",
    include_federal: bool = True,
    include_state: bool = True,
    include_local: bool = True,
    dry_run: bool = False,
) -> dict:
    """Fetch elected officials and store to Postgres.

    This fetches representatives from multiple levels of government:
    - Federal: Congress.gov API (US House, Senate)
    - State: LegiScan API (CA Assembly, Senate)
    - Local: Curated data (San Rafael City Council, Mayor, County Supervisor)

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        include_federal: Include federal representatives
        include_state: Include state legislators
        include_local: Include local officials (council, mayor)
        dry_run: If True, fetch but don't store

    Setup:
        1. Modal secrets should include:
           - civic-db: DATABASE_URL
           - civic-legiscan: LEGISCAN_API_KEY (for state legislators)
        2. Federal API uses data.gov key from FAC_API_KEY or CONGRESS_GOV_API_KEY
           (already in civic-db or can be omitted - will return partial results)
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.representatives import (
        RepresentativesClient,
        extract_elected_officials_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"[ELECTED_OFFICIALS] Starting fetch: jurisdiction={jurisdiction}")
    logger.info(f"  include_federal={include_federal}, include_state={include_state}, include_local={include_local}")

    # Create client (picks up API keys from environment)
    client = RepresentativesClient(
        jurisdiction_id=jurisdiction,
        congress_api_key=os.environ.get("CONGRESS_GOV_API_KEY") or os.environ.get("FAC_API_KEY"),
        legiscan_api_key=os.environ.get("LEGISCAN_API_KEY"),
    )

    # Fetch representatives
    representatives = client.get_representatives(
        include_federal=include_federal,
        include_state=include_state,
        include_local=include_local,
    )
    logger.info(f"Fetched {len(representatives)} representatives")

    # Log representatives by level
    federal = [r for r in representatives if r.level == "federal"]
    state = [r for r in representatives if r.level == "state"]
    local = [r for r in representatives if r.level == "local"]
    logger.info(f"  Federal: {len(federal)}, State: {len(state)}, Local: {len(local)}")

    for rep in representatives:
        logger.info(f"  - {rep.name} ({rep.office}) [{rep.level}]")

    if not representatives:
        elapsed = time.time() - start_time
        return {
            "task": "elected_officials",
            "jurisdiction": jurisdiction,
            "officials_fetched": 0,
            "officials_stored": 0,
            "dry_run": dry_run,
            "elapsed_seconds": elapsed,
            "cost_usd": 4 * elapsed * 0.000463,
        }

    # Store to database
    stored_count = 0
    if not dry_run:
        backend = PostgresBackend(database_url)
        stored_count = extract_elected_officials_to_storage(
            client=client,
            storage=backend,
            jurisdiction_id=jurisdiction,
            include_federal=include_federal,
            include_state=include_state,
            include_local=include_local,
        )
        logger.info(f"Stored {stored_count} elected officials")

        # Update refresh metadata
        backend.update_refresh_metadata(
            jurisdiction, "elected_officials", "representatives",
            items_fetched=len(representatives),
            items_stored=stored_count,
            status="completed",
        )

    elapsed = time.time() - start_time
    return {
        "task": "elected_officials",
        "jurisdiction": jurisdiction,
        "officials_fetched": len(representatives),
        "officials_stored": stored_count,
        "by_level": {
            "federal": len(federal),
            "state": len(state),
            "local": len(local),
        },
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
    auto_index: bool = False,
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
        auto_index: If True, trigger vector indexing after successful extraction
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos_extraction.cli.chunks import run_chunk_extraction

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

    # Auto-index vectors if requested and chunks were extracted
    vector_result = None
    if auto_index and total_chunks > 0 and not dry_run:
        logger.info(f"[CHUNKS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="chunks",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    result = {
        "task": "chunks",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_failed": failed,
        "chunks_extracted": total_chunks,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 8 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


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
    auto_index: bool = False,
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
        auto_index: If True, trigger vector indexing after successful extraction
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos_extraction.cli.agenda import run_agenda_extraction

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

    # Auto-index vectors if requested and items were extracted
    vector_result = None
    if auto_index and total_items > 0 and not dry_run:
        logger.info(f"[AGENDA] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="agenda_items",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    logger.info(f"[AGENDA] Extracted {total_items} items ({actionable_items} actionable) from {extracted} meetings")
    logger.info(f"[AGENDA] Skipped {skipped} (already extracted), {failed} failed")

    result = {
        "task": "agenda_items",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_failed": failed,
        "items_extracted": total_items,
        "actionable_items": actionable_items,
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 8 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


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
    auto_index: bool = False,
    since: str = "",
    until: str = "",
    meeting_ids: list = None,
) -> dict:
    """Extract high-stakes decisions from meeting minutes using LLM.

    This function:
    1. Reads meetings from Postgres that have agenda/minutes URLs
    2. Downloads PDFs and extracts high-stakes decisions using LLM
    3. Stores decisions to Postgres

    Can be called in two modes:
    - Batch mode (default): processes all unextracted meetings, used by weekly cron
    - Targeted mode (meeting_ids set): processes specific meetings, used by reactive pipeline
      when minutes appear on previously-processed meetings

    Pipeline Integration:
        This is a Modal orchestration task, not a Pipeline class instance.
        It bypasses the standard 4-stage pattern (discover→ingest→store→index)
        because decision extraction is:
        - LLM-intensive (not suited for streaming callbacks)
        - Already incremental (skips previously extracted meetings)

        Vector indexing happens separately via index_vectors() which includes
        "decisions" in its corpus_types. In scheduled_low_velocity_refresh,
        extract_decisions runs BEFORE index_vectors to maintain store→index order.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be processed without extracting
        auto_index: If True, trigger vector indexing after successful extraction
        since: Filter meetings since this date (YYYY-MM-DD)
        until: Filter meetings until this date (YYYY-MM-DD)
        meeting_ids: If set, only process these specific meetings (targeted mode)
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos_extraction.cli.decisions import run_decision_extraction
    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    if meeting_ids:
        logger.info(f"[DECISIONS] Targeted extraction: jurisdiction={jurisdiction}, meeting_ids={meeting_ids}")
    else:
        logger.info(f"[DECISIONS] Starting extraction: jurisdiction={jurisdiction}, limit={limit}, since={since or 'all'}, until={until or 'all'}")

    results = run_decision_extraction(
        jurisdiction_id=jurisdiction,
        input_dir="data/meetings",
        output_dir="data/decisions",
        checkpoint_dir="data/checkpoints",
        dry_run=dry_run,
        limit=limit,
        cloud=True,
        since=since or None,
        until=until or None,
        meeting_ids=meeting_ids,
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
    skipped = sum(1 for r in results if r.status in ("skipped", "no_minutes"))
    no_minutes = sum(1 for r in results if r.status == "no_minutes")
    failed = sum(1 for r in results if r.status == "error")
    total_decisions = sum(r.decisions_count for r in results if r.status == "success")

    # Detect degraded runs: many failures or zero decisions from many meetings
    non_skipped = extracted + failed
    is_degraded = failed > 0 and failed >= non_skipped * 0.5  # >50% failure rate
    if is_degraded:
        logger.error(
            f"[DECISIONS] DEGRADED: {failed}/{non_skipped} meetings failed "
            f"(likely agenda download failures from cloud IPs)"
        )

    # Update refresh metadata
    if not dry_run:
        status = "degraded" if is_degraded else "completed"
        error_msg = (
            f"{failed}/{non_skipped} meetings failed agenda download"
            if is_degraded else None
        )
        backend.update_refresh_metadata(
            jurisdiction, "decisions", "llm_extraction",
            items_fetched=len(results),
            items_stored=total_decisions,
            status=status,
            error_message=error_msg,
        )

    # Auto-index vectors if requested and decisions were extracted
    vector_result = None
    if auto_index and total_decisions > 0 and not dry_run:
        logger.info(f"[DECISIONS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="decisions",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    logger.info(f"[DECISIONS] Extracted {total_decisions} decisions from {extracted} meetings")
    logger.info(f"[DECISIONS] Skipped {skipped} (already extracted or no minutes), {no_minutes} awaiting minutes, {failed} failed")

    result = {
        "task": "decisions",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_no_minutes": no_minutes,
        "meetings_failed": failed,
        "decisions_extracted": total_decisions,
        "targeted": bool(meeting_ids),
        "dry_run": dry_run,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 8 * elapsed * 0.000463,
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# Transcript Extraction (Audio Download + Transcription)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-assemblyai"),  # ASSEMBLYAI_API_KEY
        modal.Secret.from_name("civic-google"),  # GOOGLE_API_KEY for YouTube duration validation
        modal.Secret.from_name("civic-r2"),  # R2 blob storage for audio files
        modal.Secret.from_name("civic-youtube-cookies"),  # YouTube cookies to bypass bot detection (base64-encoded)
        modal.Secret.from_name("civic-youtube-proxy"),  # Residential proxy for YouTube downloads (PROXY_URL)
        modal.Secret.from_name("civic-openai"),  # For LLM speaker estimation
    ],
    memory=8192,  # 8GB for concurrent audio processing
    timeout=7200,  # 2 hours (multi-meeting transcription batch)
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=60.0),
)
def extract_transcripts(
    jurisdiction: str = "city-san-rafael",
    limit: int = 0,
    dry_run: bool = False,
    batch: bool = True,
    auto_index: bool = False,
    meeting_type: str = "",
    since_days: int = 0,
) -> dict:
    """Extract transcripts from meeting audio using AssemblyAI.

    This function:
    1. Reads meetings with youtube_url from Postgres
    2. Downloads audio files to R2 (if not already present)
    3. Transcribes with AssemblyAI + speaker diarization
    4. Validates transcript duration vs YouTube source
    5. Stores transcripts to Postgres

    Pipeline Integration:
        Runs in scheduled_high_velocity_refresh AFTER fetch_meetings (which
        discovers videos) and BEFORE index_vectors (which indexes transcripts).
        This ensures transcript data is available for vector embedding.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be processed without extracting
        batch: If True, use AssemblyAI batch mode for parallel transcription
        auto_index: If True, trigger vector indexing after successful extraction
        meeting_type: Filter by meeting type (e.g., "planning_commission")
        since_days: Only process videos discovered within this many days (0 = no filter)

    Cost: ~$0.02/minute audio (~$2.40 per 2-hour meeting)
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    assemblyai_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not assemblyai_key and not dry_run:
        raise ValueError("ASSEMBLYAI_API_KEY not set. Create Modal secret: modal secret create civic-assemblyai ASSEMBLYAI_API_KEY='...'")

    meeting_type_filter = meeting_type if meeting_type else None
    since_days_filter = since_days if since_days > 0 else None
    logger.info(f"[TRANSCRIPTS] Starting extraction: jurisdiction={jurisdiction}, limit={limit}, batch={batch}, meeting_type={meeting_type_filter}, since_days={since_days_filter}")

    # Decode YouTube cookies from Modal secret (base64-encoded)
    # Bypasses YouTube bot detection from datacenter IPs.
    # Fallback: run `civic-extract audio --cloud` locally (residential IP) to upload audio to R2.
    import base64
    import tempfile

    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64", "")
    cookies_path = ""
    if cookies_b64:
        cookies_bytes = base64.b64decode(cookies_b64)
        cookies_fd, cookies_path = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
        with os.fdopen(cookies_fd, "wb") as f:
            f.write(cookies_bytes)
        logger.info("[TRANSCRIPTS] YouTube cookies loaded from secret")
    else:
        logger.info("[TRANSCRIPTS] No YouTube cookies available (downloads may fail from cloud IPs)")

    # Residential proxy for YouTube downloads from datacenter IPs
    proxy_url = os.environ.get("PROXY_URL", "")
    if proxy_url:
        has_scheme = "://" in proxy_url
        has_auth = "@" in proxy_url
        proxy_display = proxy_url.split("@")[-1] if has_auth else proxy_url
        logger.info(f"[TRANSCRIPTS] Residential proxy configured: {proxy_display} (scheme={has_scheme}, auth={has_auth}, len={len(proxy_url)})")
    else:
        logger.info("[TRANSCRIPTS] No proxy configured (downloads from datacenter IPs may fail)")

    # Step 1: Download audio files (if not already in R2)
    logger.info("[TRANSCRIPTS] Step 1: Downloading audio files...")
    try:
        from civicos_extraction.cli.audio import run_audio_download

        audio_results = run_audio_download(
            jurisdiction_id=jurisdiction,
            input_dir="data",
            output_dir="data/youtube_audio",
            cookies_path=cookies_path,
            checkpoint_dir="data/checkpoints",
            dry_run=dry_run,
            limit=limit,
            quality="128",
            cloud=True,  # Store in R2
            meeting_type=meeting_type_filter,
            since_days=since_days_filter,
            proxy=proxy_url or None,
        )

        if audio_results is None and not dry_run:
            logger.warning("[TRANSCRIPTS] No videos found for audio download")
            audio_downloaded = 0
            audio_skipped = 0
        else:
            audio_downloaded = sum(1 for r in (audio_results or []) if r.status == "success")
            audio_skipped = sum(1 for r in (audio_results or []) if r.status == "skipped")
            audio_failed = sum(1 for r in (audio_results or []) if r.status == "error")
            logger.info(f"[TRANSCRIPTS] Audio: {audio_downloaded} downloaded, {audio_skipped} already in R2")
            if audio_failed > 0 and audio_downloaded == 0 and cookies_b64:
                logger.warning("[TRANSCRIPTS] All audio downloads failed with cookies present - cookies may be expired")
                logger.warning("[TRANSCRIPTS] Refresh: modal secret create civic-youtube-cookies YOUTUBE_COOKIES_B64=\"$(base64 < cookies.txt)\"")
    except Exception as e:
        logger.exception("[TRANSCRIPTS] Audio download failed")
        audio_downloaded = 0
        audio_skipped = 0
    finally:
        if cookies_path:
            try:
                os.unlink(cookies_path)
            except OSError:
                pass

    # Step 2: Transcribe audio files
    logger.info("[TRANSCRIPTS] Step 2: Transcribing audio files...")
    try:
        from civicos_extraction.cli.transcribe import run_transcription

        transcribe_results = run_transcription(
            jurisdiction_id=jurisdiction,
            input_dir="data/youtube_audio",
            output_dir="data/testimony",
            checkpoint_dir="data/checkpoints",
            dry_run=dry_run,
            limit=limit,
            min_speakers=15,
            max_speakers=50,
            cloud=True,  # Read audio from R2, store transcripts in Postgres
            batch=batch,  # Use batch mode for parallel processing
            meeting_type=meeting_type_filter,
            since_days=since_days_filter,
            auto_estimate_speakers=True,  # Estimate per-video from YouTube captions
        )

        if transcribe_results is None and not dry_run:
            logger.warning("[TRANSCRIPTS] No audio files to transcribe")
            transcripts_extracted = 0
            transcripts_skipped = 0
            transcripts_failed = 0
            duration_issues = 0
            total_cost = 0.0
        else:
            transcripts_extracted = sum(1 for r in (transcribe_results or []) if r.status == "success")
            transcripts_skipped = sum(1 for r in (transcribe_results or []) if r.status == "skipped")
            transcripts_failed = sum(1 for r in (transcribe_results or []) if r.status == "error")
            # Count duration validation issues
            duration_issues = sum(
                1 for r in (transcribe_results or [])
                if r.status == "success" and r.duration_valid is False
            )
            total_cost = sum(r.cost_usd or 0.0 for r in (transcribe_results or []) if r.status == "success")

            logger.info(f"[TRANSCRIPTS] Transcribed: {transcripts_extracted}, skipped: {transcripts_skipped}, failed: {transcripts_failed}")
            if duration_issues > 0:
                logger.warning(f"[TRANSCRIPTS] Duration validation issues: {duration_issues}")

    except Exception as e:
        logger.exception("[TRANSCRIPTS] Transcription failed")
        transcripts_extracted = 0
        transcripts_skipped = 0
        transcripts_failed = 0
        duration_issues = 0
        total_cost = 0.0

    # Auto-index vectors if requested and transcripts were extracted
    vector_result = None
    if auto_index and transcripts_extracted > 0 and not dry_run:
        logger.info(f"[TRANSCRIPTS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="transcripts",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    logger.info(f"[TRANSCRIPTS] Complete in {elapsed:.1f}s. Cost: ${total_cost:.2f}")

    result = {
        "task": "transcripts",
        "jurisdiction": jurisdiction,
        "audio_downloaded": audio_downloaded,
        "audio_skipped": audio_skipped,
        "transcripts_extracted": transcripts_extracted,
        "transcripts_skipped": transcripts_skipped,
        "transcripts_failed": transcripts_failed,
        "duration_validation_issues": duration_issues,
        "dry_run": dry_run,
        "batch_mode": batch,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "transcription_cost_usd": total_cost,
        "cost_usd": 8 * elapsed * 0.000463 + total_cost,  # Modal compute + AssemblyAI
    }
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# Scheduled Refreshes
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-legiscan"),
        modal.Secret.from_name("civic-openai"),  # For LLM extraction (agenda, decisions)
        modal.Secret.from_name("civic-notify"),  # Push notifications (ntfy or legacy Slack)
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

    Legislation sync (via sync_legislation):
    - Fetches master list to discover new bills and status updates
    - Stores/upserts bills with temporal versioning
    - Populates full_text for bills missing it
    - Auto-indexes vectors

    Iterates all configured jurisdictions from data/extraction/*.json.
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting scheduled low-velocity refresh")
    start_time = time.time()

    from civicos_extraction.config import get_active_jurisdictions

    jurisdictions = get_active_jurisdictions()
    logger.info(f"Found {len(jurisdictions)} configured jurisdictions: {list(jurisdictions.keys())}")

    results = {}

    # =========================================================================
    # Global operations (not per-jurisdiction)
    # =========================================================================

    # Legislation CA (run weekly to avoid quota issues, auto-index vectors)
    # Uses sync_legislation() which:
    #   1. Fetches master list to discover new bills and status updates (1 API call)
    #   2. Stores/upserts bills with temporal versioning
    #   3. Populates full_text for bills missing it
    #   4. Auto-indexes vectors
    try:
        logger.info("Syncing CA legislation...")
        result = sync_legislation.local(jurisdiction="state-CA", dry_run=False, auto_index=True)
        results["legislation_CA"] = result
        new_bills = result.get('new_bills', 0)
        stored = result.get('bills_stored', 0)
        text_updated = result.get('text_result', {}).get('bills_with_text', 0)
        indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
        logger.info(f"  CA Legislation: {new_bills} new bills, {stored} total stored, {text_updated} texts populated, {indexed} vectors indexed")
    except Exception as e:
        logger.exception("CA legislation sync failed")
        results["legislation_CA"] = {"status": "failed", "error": str(e)}

    # Executive Orders from Federal Register (incremental, auto-index vectors)
    try:
        logger.info("Fetching Executive Orders from Federal Register...")
        result = fetch_executive_orders.local(dry_run=False, incremental=True, auto_index=True)
        results["executive_orders"] = result
        stored = result.get('orders_stored', 0)
        indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
        logger.info(f"  Executive Orders: {stored} new orders stored (of {result.get('orders_fetched', 0)} fetched), {indexed} vectors indexed")
    except Exception as e:
        logger.exception("Executive Orders fetch failed")
        results["executive_orders"] = {"status": "failed", "error": str(e)}

    # Federal Rules from Federal Register (proposed rules, final rules, notices)
    try:
        logger.info("Fetching Federal Rules from Federal Register...")
        result = fetch_federal_rules.local(dry_run=False, incremental=True, auto_index=True)
        results["federal_rules"] = result
        stored = result.get('rules_stored', 0)
        indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
        logger.info(f"  Federal Rules: {stored} new rules stored (of {result.get('rules_fetched', 0)} fetched), {indexed} vectors indexed")
    except Exception as e:
        logger.exception("Federal Rules fetch failed")
        results["federal_rules"] = {"status": "failed", "error": str(e)}

    # Legislative Events (hearing dates parsed from existing legislation — no API calls)
    try:
        logger.info("Extracting legislative events from CA legislation...")
        result = extract_legislative_events.local(state="CA", dry_run=False)
        results["legislative_events_CA"] = result
        stored = result.get('events_stored', 0)
        logger.info(f"  Legislative Events CA: {stored} events stored (of {result.get('events_parsed', 0)} parsed from {result.get('bills_read', 0)} bills)")
    except Exception as e:
        logger.exception("Legislative events extraction failed")
        results["legislative_events_CA"] = {"status": "failed", "error": str(e)}

    # Federal programs from SAM.gov (full catalog refresh)
    try:
        logger.info("Fetching federal programs from SAM.gov...")
        result = fetch_federal_programs.local(dry_run=False, force_refresh=True, auto_index=True)
        results["federal_programs"] = result
        stored = result.get("programs_stored", 0)
        indexed = result.get("vector_result", {}).get("total_indexed", 0) if result.get("auto_index") else 0
        logger.info(f"  Federal programs: {stored} programs stored, {indexed} vectors indexed")
    except Exception as e:
        logger.exception("Federal programs fetch failed")
        results["federal_programs"] = {"status": "failed", "error": str(e)}

    # HUD allocations (CDBG, HOME, etc.) - already iterates all configured jurisdictions
    try:
        logger.info("Fetching HUD allocations for all configured jurisdictions...")
        result = fetch_all_hud_allocations.local(dry_run=False)
        results["hud_allocations"] = result
        new_years = result.get("new_years_discovered", [])
        jcount = result.get("jurisdictions_processed", 0)
        stored = result.get("total_allocations_stored", 0)
        if new_years:
            logger.info(f"  HUD allocations: {stored} stored across {jcount} jurisdictions, NEW YEARS FOUND: {new_years}")
        else:
            logger.info(f"  HUD allocations: {stored} stored across {jcount} jurisdictions")
    except Exception as e:
        logger.exception("HUD allocations fetch failed")
        results["hud_allocations"] = {"status": "failed", "error": str(e)}

    # NOTE: Federal programs vector indexing is now handled by auto_index=True
    # in the fetch_federal_programs call above (avoids duplicate indexing).

    # =========================================================================
    # Per-jurisdiction operations
    # =========================================================================

    for jid, config in jurisdictions.items():
        # Skip jurisdictions without per-jurisdiction low-velocity data sources
        # (e.g., county-marin is financial context only, no municipal code/meetings/minutes)
        source_type = config.get("source_type", "")
        if source_type in ("county", "financial"):
            logger.info(f"Skipping {jid} (source_type={source_type}, no per-jurisdiction low-velocity data)")
            continue

        logger.info(f"Processing jurisdiction: {jid}")
        results[jid] = {}

        # Municipal code (always full refresh - no incremental API support, auto-index vectors)
        try:
            logger.info(f"  [{jid}] Fetching municipal code...")
            result = fetch_municipal_code.local(jurisdiction=jid, dry_run=False, auto_index=True)
            results[jid]["municipal_code"] = result
            stored = result.get('sections_stored', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"    Municipal code: {stored} sections stored, {indexed} vectors indexed")
        except Exception as e:
            logger.exception(f"  [{jid}] Municipal code fetch failed")
            results[jid]["municipal_code"] = {"status": "failed", "error": str(e)}

        # Agenda items extraction (LLM-powered, after meetings are available, auto-index vectors)
        try:
            logger.info(f"  [{jid}] Extracting agenda items...")
            result = extract_agenda_items.local(jurisdiction=jid, dry_run=False, auto_index=True)
            results[jid]["agenda_items"] = result
            extracted = result.get('items_extracted', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"    Agenda items: {extracted} items ({result.get('actionable_items', 0)} actionable), {indexed} vectors indexed")
        except Exception as e:
            logger.exception(f"  [{jid}] Agenda items extraction failed")
            results[jid]["agenda_items"] = {"status": "failed", "error": str(e)}

        # Decision extraction (LLM-powered, weekly because minutes PDFs lag behind meetings, auto-index vectors)
        try:
            logger.info(f"  [{jid}] Extracting decisions...")
            result = extract_decisions.local(jurisdiction=jid, dry_run=False, auto_index=True)
            results[jid]["decisions"] = result
            extracted = result.get('decisions_extracted', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"    Decisions: {extracted} decisions from {result.get('meetings_extracted', 0)} meetings, {indexed} vectors indexed")
        except Exception as e:
            logger.exception(f"  [{jid}] Decision extraction failed")
            results[jid]["decisions"] = {"status": "failed", "error": str(e)}

        # NOTE: Vector indexing now handled by auto_index=True on each fetch/extract call above.
        # This ensures vectors are indexed immediately after data is stored, closing the
        # staleness gap where data could exist in storage but not be searchable.

    elapsed = time.time() - start_time
    logger.info(f"Low-velocity refresh complete in {elapsed:.1f}s for {len(jurisdictions)} jurisdictions")

    # Send pipeline summary notification
    try:
        from civicos_services.monitoring.pipeline_run_summary import send_pipeline_summary
        summary = send_pipeline_summary(
            results=results,
            schedule="low_velocity_weekly",
            elapsed_seconds=elapsed,
        )
        logger.info(f"Pipeline summary: {summary['stages_succeeded']}/{summary['stages_succeeded'] + summary['stages_failed']} passed, sent={summary['notification_sent']}")
    except Exception as e:
        logger.warning(f"Failed to send pipeline summary notification: {e}")

    return {
        "schedule": "low_velocity_weekly",
        "jurisdictions_processed": len(jurisdictions),
        "results": results,
        "elapsed_seconds": elapsed,
    }


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-assemblyai"),  # For transcript extraction
        modal.Secret.from_name("civic-google"),  # For YouTube duration validation
        modal.Secret.from_name("civic-r2"),  # R2 blob storage for audio files
        modal.Secret.from_name("civic-youtube-cookies"),  # For YouTube audio download
        modal.Secret.from_name("civic-youtube-proxy"),  # Residential proxy for YouTube downloads
        modal.Secret.from_name("civic-openai"),  # For speaker estimation + agenda extraction
        modal.Secret.from_name("civic-notify"),  # Push notifications (ntfy or legacy Slack)
    ],
    memory=4096,
    timeout=10800,  # 3 hours (transcription can take time)
    schedule=modal.Cron("0 14 * * *"),  # Daily at 2 PM UTC = 6 AM Pacific
)
def scheduled_high_velocity_refresh():
    """Daily scheduled refresh for high-velocity corpora (meetings, issues, transcripts, chunks, agenda items).

    Runs daily at 2 PM UTC = 6 AM Pacific.
    Incremental fetch for data that changes frequently.

    Pipeline (per jurisdiction):
        1. fetch_meetings() - Scrape new meetings from ProudCity
        2. fetch_issues() - Fetch new issues from SeeClickFix
        3. discover_videos() - Scrape meeting pages for YouTube video IDs
        4. extract_transcripts() - Download audio + transcribe with AssemblyAI
        5. extract_chunks() - Download PDFs and extract text chunks (incremental)
        6. extract_agenda_items() - Extract actionable items from agendas (LLM-powered)
        7. index_vectors() - Index all corpora to pgvector (via auto_index)

    Note: Agenda items moved from weekly to daily (Session 540) because:
    - New meetings are discovered daily
    - Agenda items are key for prospective civic engagement
    - Users need upcoming meeting details promptly

    Iterates all configured jurisdictions from data/extraction/*.json.
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    def run_with_retry(func, stage_name: str, max_retries: int = 2, initial_delay: float = 30.0, **kwargs):
        """Run a Modal .local() function with retry logic for transient failures.

        Args:
            func: Modal function to call with .local()
            stage_name: Human-readable name for logging
            max_retries: Maximum retry attempts (default 2)
            initial_delay: Initial delay in seconds, doubles each retry
            **kwargs: Arguments to pass to the function

        Returns:
            Function result on success, or dict with status="failed" on exhausted retries
        """
        delay = initial_delay
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return func.local(**kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"  {stage_name} failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    logger.exception(f"  {stage_name} failed after {max_retries + 1} attempts")

        return {"status": "failed", "error": str(last_error)}

    logger.info("Starting scheduled high-velocity refresh")
    start_time = time.time()

    from civicos_extraction.config import get_active_jurisdictions

    jurisdictions = get_active_jurisdictions()
    logger.info(f"Found {len(jurisdictions)} configured jurisdictions: {list(jurisdictions.keys())}")

    results = {}
    total_transcription_cost = 0.0

    for jid, config in jurisdictions.items():
        # Skip jurisdictions without high-velocity data sources
        # (e.g., county-marin is financial context only, no meetings/issues/videos)
        source_type = config.get("source_type", "")
        if source_type in ("county", "financial"):
            logger.info(f"Skipping {jid} (source_type={source_type}, no high-velocity data)")
            continue

        logger.info(f"Processing jurisdiction: {jid}")
        results[jid] = {}

        # === STAGE 1: Always run cheap polls (meetings + issues) ===
        logger.info(f"  [{jid}] Fetching meetings (incremental)...")
        meetings_result = run_with_retry(
            fetch_meetings,
            f"[{jid}] Meetings fetch",
            jurisdiction=jid,
            incremental=True,
            dry_run=False,
            auto_index=True,
        )
        results[jid]["meetings"] = meetings_result
        if meetings_result.get("status") != "failed":
            stored = meetings_result.get('meetings_stored', 0)
            indexed = meetings_result.get('vector_result', {}).get('total_indexed', 0) if meetings_result.get('auto_index') else 0
            logger.info(f"    Meetings: {stored} stored, {indexed} vectors indexed")

        logger.info(f"  [{jid}] Fetching issues (incremental)...")
        result = run_with_retry(
            fetch_issues,
            f"[{jid}] Issues fetch",
            jurisdiction=jid,
            incremental=True,
            dry_run=False,
            auto_index=True,
        )
        results[jid]["issues"] = result
        if result.get("status") != "failed":
            stored = result.get('issues_stored', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"    Issues: {stored} stored, {indexed} vectors indexed")

        # === STAGE 2: Reactive — only run expensive stages if meetings changed ===
        has_new_material = meetings_result.get("has_new_material", False)
        has_agenda = meetings_result.get("has_agenda_updates", False)
        has_minutes = meetings_result.get("has_minutes_updates", False)
        has_video = meetings_result.get("has_video_updates", False)
        new_ids = meetings_result.get("new_meeting_ids", [])
        agenda_ids = meetings_result.get("agenda_appeared_ids", [])
        minutes_ids = meetings_result.get("minutes_appeared_ids", [])
        video_ids = meetings_result.get("video_appeared_ids", [])

        has_any_change = has_new_material or has_agenda or has_minutes or has_video
        if not has_any_change:
            logger.info(f"  [{jid}] No new material — skipping downstream stages")
            results[jid]["skipped_downstream"] = True
        else:
            logger.info(
                f"  [{jid}] Changes detected: {len(new_ids)} new, "
                f"{len(agenda_ids)} agendas, {len(minutes_ids)} minutes, "
                f"{len(video_ids)} videos appeared"
            )

            # Chunk + agenda extraction — triggered by new meetings or agenda URLs appearing
            if has_new_material or has_agenda:
                # Chunk extraction (incremental - skips already-chunked meetings, auto-index vectors)
                logger.info(f"  [{jid}] Extracting chunks from new meetings...")
                result = run_with_retry(
                    extract_chunks,
                    f"[{jid}] Chunk extraction",
                    jurisdiction=jid,
                    dry_run=False,
                    auto_index=True,
                )
                results[jid]["chunks"] = result
                if result.get("status") != "failed":
                    extracted = result.get('chunks_extracted', 0)
                    indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
                    logger.info(f"    Chunks: {extracted} extracted from {result.get('meetings_extracted', 0)} meetings, {indexed} vectors indexed")

                # Agenda items extraction (LLM-powered)
                logger.info(f"  [{jid}] Extracting agenda items...")
                result = run_with_retry(
                    extract_agenda_items,
                    f"[{jid}] Agenda items extraction",
                    max_retries=1,  # LLM calls are expensive, limit retries
                    jurisdiction=jid,
                    dry_run=False,
                    auto_index=True,
                )
                results[jid]["agenda_items"] = result
                if result.get("status") != "failed":
                    extracted = result.get('items_extracted', 0)
                    indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
                    logger.info(f"    Agenda items: {extracted} items ({result.get('actionable_items', 0)} actionable), {indexed} vectors indexed")

            # Video discovery + transcription — triggered when video_url appears
            if has_video:
                logger.info(f"  [{jid}] Video appeared on {len(video_ids)} meetings — discovering and transcribing...")
                result = run_with_retry(
                    discover_videos,
                    f"[{jid}] Video discovery",
                    jurisdiction=jid,
                    days_past=7,
                    days_ahead=30,
                    dry_run=False,
                )
                results[jid]["videos"] = result
                if result.get("status") != "failed":
                    discovered = result.get('videos_discovered', 0)
                    logger.info(f"    Videos: {discovered} discovered")

                # Transcript extraction (audio download + transcription, auto-index vectors)
                logger.info(f"  [{jid}] Extracting transcripts (audio + transcription)...")
                result = run_with_retry(
                    extract_transcripts,
                    f"[{jid}] Transcript extraction",
                    max_retries=1,  # Transcription is expensive, limit retries
                    jurisdiction=jid,
                    since_days=7,  # Only videos discovered in last 7 days
                    dry_run=False,
                    batch=True,  # Use batch mode for parallel transcription
                    auto_index=True,
                )
                results[jid]["transcripts"] = result
                if result.get("status") != "failed":
                    cost = result.get("transcription_cost_usd", 0)
                    total_transcription_cost += cost
                    extracted = result.get('transcripts_extracted', 0)
                    indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
                    logger.info(
                        f"    Transcripts: {extracted} transcribed, "
                        f"{result.get('transcripts_skipped', 0)} skipped, "
                        f"{indexed} vectors indexed, cost: ${cost:.2f}"
                    )
                    if result.get("duration_validation_issues", 0) > 0:
                        logger.warning(f"    Duration validation issues: {result.get('duration_validation_issues')}")

            # Decision extraction — triggered when minutes appear on previously-processed meetings
            if has_minutes:
                logger.info(f"  [{jid}] Minutes appeared on {len(minutes_ids)} meetings — extracting decisions...")
                result = run_with_retry(
                    extract_decisions,
                    f"[{jid}] Reactive decision extraction",
                    max_retries=1,
                    jurisdiction=jid,
                    meeting_ids=minutes_ids,
                    dry_run=False,
                    auto_index=True,
                )
                results[jid]["decisions"] = result
                if result.get("status") != "failed":
                    extracted = result.get('decisions_extracted', 0)
                    logger.info(f"    Decisions: {extracted} extracted from {len(minutes_ids)} meetings")

    elapsed = time.time() - start_time
    logger.info(f"High-velocity refresh complete in {elapsed:.1f}s for {len(jurisdictions)} jurisdictions")
    logger.info(f"Total transcription cost: ${total_transcription_cost:.2f}")

    # Send pipeline summary notification
    try:
        from civicos_services.monitoring.pipeline_run_summary import send_pipeline_summary
        summary = send_pipeline_summary(
            results=results,
            schedule="high_velocity_daily",
            elapsed_seconds=elapsed,
            total_transcription_cost=total_transcription_cost,
        )
        logger.info(f"Pipeline summary: {summary['stages_succeeded']}/{summary['stages_succeeded'] + summary['stages_failed']} passed, sent={summary['notification_sent']}")
    except Exception as e:
        logger.warning(f"Failed to send pipeline summary notification: {e}")

    return {
        "schedule": "high_velocity_daily",
        "jurisdictions_processed": len(jurisdictions),
        "results": results,
        "elapsed_seconds": elapsed,
        "total_transcription_cost_usd": total_transcription_cost,
    }


# =============================================================================
# Frequent Meetings Poll (Reactive Pipeline)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-openai"),  # For agenda/decision extraction if triggered
        modal.Secret.from_name("civic-assemblyai"),  # For transcript extraction if video appears
        modal.Secret.from_name("civic-google"),  # For YouTube duration validation
        modal.Secret.from_name("civic-r2"),  # R2 blob storage for audio files
        modal.Secret.from_name("civic-youtube-cookies"),  # For YouTube audio download
        modal.Secret.from_name("civic-youtube-proxy"),  # Residential proxy for YouTube downloads
        modal.Secret.from_name("civic-notify"),
    ],
    memory=4096,  # Higher memory for transcript extraction
    timeout=3600,  # 1 hour (transcription can take time if triggered)
    schedule=modal.Cron("0 14,22,2,6 * * *"),  # Every ~4h: 6AM, 2PM, 6PM, 10PM Pacific
)
def scheduled_meetings_poll():
    """Lightweight meetings-only poll that triggers downstream extraction reactively.

    Runs 4x/day covering business hours. Only fetches meetings (cheap HTTP scrape).
    If new meetings or minutes appear, spawns chunk/agenda/decision extraction.

    Cost: ~$0.02/run when idle (no new material), ~$2/month total.
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting scheduled meetings poll (reactive)")
    start_time = time.time()

    from civicos_extraction.config import get_active_jurisdictions

    jurisdictions = get_active_jurisdictions()
    results = {}

    for jid, config in jurisdictions.items():
        source_type = config.get("source_type", "")
        if source_type in ("county", "financial"):
            continue

        logger.info(f"[{jid}] Polling meetings...")
        try:
            meetings_result = fetch_meetings.local(
                jurisdiction=jid,
                incremental=True,
                dry_run=False,
                auto_index=True,
            )
        except Exception as e:
            logger.warning(f"[{jid}] Meetings poll failed: {e}")
            results[jid] = {"status": "failed", "error": str(e)}
            continue

        results[jid] = {"meetings": meetings_result}
        has_new_material = meetings_result.get("has_new_material", False)
        has_agenda = meetings_result.get("has_agenda_updates", False)
        has_minutes = meetings_result.get("has_minutes_updates", False)
        has_video = meetings_result.get("has_video_updates", False)
        new_ids = meetings_result.get("new_meeting_ids", [])
        agenda_ids = meetings_result.get("agenda_appeared_ids", [])
        minutes_ids = meetings_result.get("minutes_appeared_ids", [])
        video_ids = meetings_result.get("video_appeared_ids", [])

        has_any_change = has_new_material or has_agenda or has_minutes or has_video
        if not has_any_change:
            logger.info(f"  [{jid}] No new material — done")
            continue

        logger.info(
            f"  [{jid}] Changes: {len(new_ids)} new, {len(agenda_ids)} agendas, "
            f"{len(minutes_ids)} minutes, {len(video_ids)} videos appeared"
        )

        # Spawn chunk + agenda extraction for new meetings or newly-available agendas
        if has_new_material or has_agenda:
            try:
                logger.info(f"  [{jid}] Extracting chunks from new meetings...")
                chunk_result = extract_chunks.local(
                    jurisdiction=jid, dry_run=False, auto_index=True,
                )
                results[jid]["chunks"] = chunk_result
                chunks_extracted = chunk_result.get('chunks_extracted', 0)
                logger.info(f"    Chunks: {chunks_extracted} extracted")
            except Exception as e:
                logger.warning(f"  [{jid}] Chunk extraction failed: {e}")

            try:
                logger.info(f"  [{jid}] Extracting agenda items...")
                agenda_result = extract_agenda_items.local(
                    jurisdiction=jid, dry_run=False, auto_index=True,
                )
                results[jid]["agenda_items"] = agenda_result
                items_extracted = agenda_result.get('items_extracted', 0)
                logger.info(f"    Agenda items: {items_extracted} extracted")
            except Exception as e:
                logger.warning(f"  [{jid}] Agenda extraction failed: {e}")

        # Spawn video discovery + transcription when video_url appears
        if has_video:
            try:
                logger.info(f"  [{jid}] Discovering videos for {len(video_ids)} meetings...")
                video_result = discover_videos.local(
                    jurisdiction=jid, days_past=7, days_ahead=30, dry_run=False,
                )
                results[jid]["videos"] = video_result
                discovered = video_result.get('videos_discovered', 0)
                logger.info(f"    Videos: {discovered} discovered")
            except Exception as e:
                logger.warning(f"  [{jid}] Video discovery failed: {e}")

            try:
                logger.info(f"  [{jid}] Extracting transcripts...")
                transcript_result = extract_transcripts.local(
                    jurisdiction=jid, since_days=7, batch=True, auto_index=True,
                )
                results[jid]["transcripts"] = transcript_result
                extracted = transcript_result.get('transcripts_extracted', 0)
                cost = transcript_result.get('transcription_cost_usd', 0)
                logger.info(f"    Transcripts: {extracted} transcribed, cost: ${cost:.2f}")
            except Exception as e:
                logger.warning(f"  [{jid}] Transcript extraction failed: {e}")

        # Spawn targeted decision extraction for meetings where minutes appeared
        if has_minutes:
            try:
                logger.info(f"  [{jid}] Extracting decisions for {len(minutes_ids)} meetings with new minutes...")
                decision_result = extract_decisions.local(
                    jurisdiction=jid,
                    meeting_ids=minutes_ids,
                    dry_run=False,
                    auto_index=True,
                )
                results[jid]["decisions"] = decision_result
                decisions_extracted = decision_result.get('decisions_extracted', 0)
                logger.info(f"    Decisions: {decisions_extracted} extracted")
            except Exception as e:
                logger.warning(f"  [{jid}] Decision extraction failed: {e}")

    elapsed = time.time() - start_time
    logger.info(f"Meetings poll complete in {elapsed:.1f}s")

    return {
        "schedule": "meetings_poll",
        "jurisdictions_processed": len(results),
        "results": results,
        "elapsed_seconds": elapsed,
    }


# =============================================================================
# Monthly Election Refresh (Google Civic API)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-google"),  # Contains GOOGLE_API_KEY
        modal.Secret.from_name("civic-legiscan"),  # LEGISCAN_API_KEY for state legislators
        modal.Secret.from_name("civic-congress"),  # FAC_API_KEY for federal representatives
    ],
    memory=4096,
    timeout=600,  # 10 minutes
    schedule=modal.Cron("0 3 1 * *"),  # Monthly on 1st at 3 AM UTC (7 PM Pacific prev day)
)
def scheduled_election_refresh():
    """Monthly scheduled refresh for election and elected officials data.

    Runs 1st of month at 3 AM UTC = 7 PM Pacific previous day.
    Monthly cadence is sufficient because:
    - VIP (Voter Information Project) publishes election data 2-3 weeks before elections
    - Elected officials change infrequently (after elections or special circumstances)

    Data sources:
    - Elections: Google Civic Information API
    - Elected officials: Congress.gov (federal), LegiScan (state), curated (local)

    Iterates all configured jurisdictions from data/extraction/*.json.
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting scheduled election refresh")
    start_time = time.time()

    from civicos_extraction.config import get_active_jurisdictions

    jurisdictions = get_active_jurisdictions()
    logger.info(f"Found {len(jurisdictions)} configured jurisdictions: {list(jurisdictions.keys())}")

    results = {}

    for jid, config in jurisdictions.items():
        results[jid] = {}

        # Fetch elections
        try:
            logger.info(f"  [{jid}] Fetching elections...")
            result = fetch_elections.local(jurisdiction=jid, dry_run=False, auto_index=True)
            results[jid]["elections"] = result
            stored = result.get('elections_stored', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"    Elections: {result.get('elections_fetched', 0)} fetched, {stored} stored, {indexed} vectors indexed")
        except Exception as e:
            logger.exception(f"  [{jid}] Election fetch failed")
            results[jid]["elections"] = {"status": "failed", "error": str(e)}

        # Fetch elected officials
        try:
            logger.info(f"  [{jid}] Fetching elected officials...")
            result = fetch_elected_officials.local(jurisdiction=jid, dry_run=False)
            results[jid]["elected_officials"] = result
            stored = result.get('officials_stored', 0)
            by_level = result.get('by_level', {})
            logger.info(f"    Officials: {result.get('officials_fetched', 0)} fetched, {stored} stored")
            logger.info(f"      Federal: {by_level.get('federal', 0)}, State: {by_level.get('state', 0)}, Local: {by_level.get('local', 0)}")
        except Exception as e:
            logger.exception(f"  [{jid}] Elected officials fetch failed")
            results[jid]["elected_officials"] = {"status": "failed", "error": str(e)}

    elapsed = time.time() - start_time
    logger.info(f"Election refresh complete in {elapsed:.1f}s for {len(jurisdictions)} jurisdictions")

    return {
        "schedule": "election_monthly",
        "jurisdictions_processed": len(jurisdictions),
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

    from civicos.storage import get_storage_backend
    from civicos.storage.pgvector_backend import PgVectorBackend
    from civicos.storage.postgres_backend import PostgresBackend

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
# HTTP Trigger Endpoint (manual / webhook)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-openai"),
        modal.Secret.from_name("civic-notify"),
    ],
    memory=2048,
    timeout=1800,
)
@modal.fastapi_endpoint(method="POST")
def trigger_ingest(body: dict):
    """HTTP endpoint for on-demand ingestion with reactive logic.

    POST body:
        {
            "jurisdiction": "city-san-rafael",
            "stages": ["meetings", "chunks", "decisions"],  // optional, defaults to reactive
        }

    Secured via Modal's built-in auth (requires Modal token).

    If no stages specified, runs reactive logic:
    - Always polls meetings
    - Only runs downstream stages if new material detected
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    jurisdiction = body.get("jurisdiction", "city-san-rafael")
    stages = body.get("stages")
    start_time = time.time()
    results = {}

    STAGE_MAP = {
        "meetings": lambda: fetch_meetings.local(jurisdiction=jurisdiction, incremental=True, auto_index=True),
        "issues": lambda: fetch_issues.local(jurisdiction=jurisdiction, incremental=True, auto_index=True),
        "videos": lambda: discover_videos.local(jurisdiction=jurisdiction, days_past=7, days_ahead=30),
        "chunks": lambda: extract_chunks.local(jurisdiction=jurisdiction, auto_index=True),
        "agenda_items": lambda: extract_agenda_items.local(jurisdiction=jurisdiction, auto_index=True),
        "decisions": lambda: extract_decisions.local(jurisdiction=jurisdiction, auto_index=True),
        "transcripts": lambda: extract_transcripts.local(jurisdiction=jurisdiction, since_days=7, batch=True, auto_index=True),
    }

    if stages:
        # Explicit stage list — run requested stages
        for stage in stages:
            if stage not in STAGE_MAP:
                results[stage] = {"status": "error", "error": f"Unknown stage: {stage}"}
                continue
            try:
                results[stage] = STAGE_MAP[stage]()
            except Exception as e:
                logger.warning(f"Stage {stage} failed: {e}")
                results[stage] = {"status": "failed", "error": str(e)}
    else:
        # Reactive mode — poll meetings, conditionally run downstream
        try:
            meetings_result = fetch_meetings.local(
                jurisdiction=jurisdiction, incremental=True, auto_index=True,
            )
            results["meetings"] = meetings_result

            if meetings_result.get("has_new_material") or meetings_result.get("has_agenda_updates"):
                for stage in ("chunks", "agenda_items"):
                    try:
                        results[stage] = STAGE_MAP[stage]()
                    except Exception as e:
                        results[stage] = {"status": "failed", "error": str(e)}

            if meetings_result.get("has_video_updates"):
                for stage in ("videos", "transcripts"):
                    try:
                        results[stage] = STAGE_MAP[stage]()
                    except Exception as e:
                        results[stage] = {"status": "failed", "error": str(e)}

            if meetings_result.get("has_minutes_updates"):
                minutes_ids = meetings_result.get("minutes_appeared_ids", [])
                try:
                    results["decisions"] = extract_decisions.local(
                        jurisdiction=jurisdiction, meeting_ids=minutes_ids, auto_index=True,
                    )
                except Exception as e:
                    results["decisions"] = {"status": "failed", "error": str(e)}

            has_any = (
                meetings_result.get("has_new_material")
                or meetings_result.get("has_agenda_updates")
                or meetings_result.get("has_minutes_updates")
                or meetings_result.get("has_video_updates")
            )
            if not has_any:
                results["downstream"] = "skipped (no new material)"

        except Exception as e:
            results["meetings"] = {"status": "failed", "error": str(e)}

    elapsed = time.time() - start_time
    return {
        "status": "ok",
        "jurisdiction": jurisdiction,
        "mode": "explicit" if stages else "reactive",
        "results": results,
        "elapsed_seconds": round(elapsed, 1),
    }


# =============================================================================
# Unified Entrypoint
# =============================================================================

@app.local_entrypoint()
def main(
    all: bool = False,
    municipal: bool = False,
    legislation: bool = False,
    executive_orders: bool = False,
    federal_programs: bool = False,
    federal_rules: bool = False,
    legislative_events: bool = False,
    meetings: bool = False,
    issues: bool = False,
    elections: bool = False,
    elected_officials: bool = False,
    videos: bool = False,
    transcripts: bool = False,
    chunks: bool = False,
    agenda: bool = False,
    decisions: bool = False,
    vectors: bool = False,
    jurisdiction: str = "city-san-rafael",
    legislation_jurisdiction: str = "state-CA",
    legislation_limit: int | None = None,
    transcripts_limit: int = 0,
    chunks_limit: int = 0,
    agenda_limit: int = 0,
    decisions_limit: int = 0,
    decisions_since: str = "",
    decisions_until: str = "",
    meetings_days_past: int = 30,
    incremental: bool = False,
    reindex: bool = False,
    dry_run: bool = False,
    stats_only: bool = False,
    auto_index: bool = True,
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
        modal run scripts/modal_ingest.py --elected-officials
        modal run scripts/modal_ingest.py --videos --jurisdiction school-san-rafael
        modal run scripts/modal_ingest.py --transcripts
        modal run scripts/modal_ingest.py --chunks
        modal run scripts/modal_ingest.py --vectors

        # Backfill meetings with extended lookback (120 days = ~4 months)
        modal run scripts/modal_ingest.py --meetings --meetings-days-past 120

        # Incremental mode (only fetch since last refresh)
        modal run scripts/modal_ingest.py --meetings --incremental
        modal run scripts/modal_ingest.py --issues --incremental

        # Extract transcripts (audio download + transcription with AssemblyAI)
        modal run scripts/modal_ingest.py --transcripts
        modal run scripts/modal_ingest.py --transcripts --transcripts-limit 5  # Limit to 5 meetings

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

        # Auto-indexing (enabled by default)
        # Vectors are indexed after each data store, closing the staleness gap
        modal run scripts/modal_ingest.py --meetings  # Indexes meeting vectors after store
        modal run scripts/modal_ingest.py --meetings --no-auto-index  # Skip vector indexing
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
    # Note: transcripts is included in --all as part of daily pipeline
    # Note: elected_officials is NOT in --all (monthly refresh via scheduled_election_refresh)
    run_municipal = all or municipal
    run_legislation = all or legislation
    run_executive_orders = all or executive_orders
    run_federal_programs = federal_programs  # Not in --all (weekly refresh)
    run_federal_rules = federal_rules  # Not in --all (weekly refresh)
    run_legislative_events = legislative_events  # Not in --all (weekly refresh)
    run_meetings = all or meetings
    run_issues = all or issues
    run_elections = all or elections
    run_elected_officials = elected_officials  # Not in --all (monthly refresh)
    run_transcripts = all or transcripts
    run_chunks = all or chunks
    run_agenda = all or agenda
    run_decisions = decisions  # Explicitly not in --all (weekly only)
    run_videos = videos  # Not in --all (YouTube jurisdictions need explicit flag)
    run_vectors = all or vectors

    if not (run_municipal or run_legislation or run_executive_orders or run_federal_programs or run_federal_rules or run_legislative_events or run_meetings or run_issues or run_elections or run_elected_officials or run_videos or run_transcripts or run_chunks or run_agenda or run_decisions or run_vectors):
        print("No tasks specified. Use --all, --municipal, --legislation, --executive-orders, --federal-programs, --federal-rules, --legislative-events, --meetings, --issues, --elections, --elected-officials, --videos, --transcripts, --chunks, --agenda, --decisions, or --vectors")
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
    if run_executive_orders:
        task_list.append("executive_orders")
    if run_federal_programs:
        task_list.append("federal_programs")
    if run_federal_rules:
        task_list.append("federal_rules")
    if run_legislative_events:
        task_list.append("legislative_events")
    if run_meetings:
        task_list.append("meetings")
    if run_issues:
        task_list.append("issues")
    if run_elections:
        task_list.append("elections")
    if run_elected_officials:
        task_list.append("elected_officials")
    if run_videos:
        task_list.append("videos")
    if run_transcripts:
        task_list.append("transcripts")
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
    if run_executive_orders:
        print(f"  Executive Orders: federal-US (incremental)")
    if run_federal_programs:
        print(f"  Federal Programs: SAM.gov (full catalog)")
    if run_federal_rules:
        print(f"  Federal Rules: Federal Register (proposed rules, final rules, notices)")
    if run_legislative_events:
        print(f"  Legislative Events: {legislation_jurisdiction} (hearing dates from existing bills)")
    if run_meetings:
        print(f"  Meetings: {jurisdiction}" + (" (incremental)" if incremental else ""))
    if run_issues:
        print(f"  Issues: {jurisdiction}" + (" (incremental)" if incremental else ""))
    if run_elections:
        print(f"  Elections: {jurisdiction}")
    if run_elected_officials:
        print(f"  Elected Officials: {jurisdiction} (federal, state, local)")
    if run_videos:
        print(f"  Videos: {jurisdiction} (YouTube)")
    if run_transcripts:
        print(f"  Transcripts: {jurisdiction}" + (f" (limit: {transcripts_limit})" if transcripts_limit else " (incremental)"))
    if run_chunks:
        print(f"  Chunks: {jurisdiction}" + (f" (limit: {chunks_limit})" if chunks_limit else " (incremental)"))
    if run_agenda:
        print(f"  Agenda: {jurisdiction}" + (f" (limit: {agenda_limit})" if agenda_limit else " (incremental)"))
    if run_decisions:
        print(f"  Decisions: {jurisdiction}" + (f" (limit: {decisions_limit})" if decisions_limit else " (incremental)"))
    if run_vectors:
        print(f"  Vectors: {jurisdiction}")
    print(f"Dry run: {dry_run}")
    print(f"Auto-index: {auto_index}" + (" (vectors indexed after each store)" if auto_index else " (vectors NOT indexed after store)"))
    print("=" * 60)

    # Spawn tasks in parallel
    handles = []

    if run_municipal:
        print("\nSpawning municipal code fetch...")
        handle = fetch_municipal_code.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("municipal_code", handle))

    if run_legislation:
        print("Spawning legislation sync (master list + text population)...")
        handle = sync_legislation.spawn(
            jurisdiction=legislation_jurisdiction,
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("legislation", handle))

    if run_executive_orders:
        print("Spawning executive orders fetch...")
        handle = fetch_executive_orders.spawn(
            dry_run=dry_run,
            incremental=True,  # Always incremental for EOs
            auto_index=auto_index,
        )
        handles.append(("executive_orders", handle))

    if run_federal_programs:
        print("Spawning federal programs fetch...")
        handle = fetch_federal_programs.spawn(
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("federal_programs", handle))

    if run_federal_rules:
        print("Spawning federal rules fetch...")
        handle = fetch_federal_rules.spawn(
            dry_run=dry_run,
            incremental=True,
            auto_index=auto_index,
        )
        handles.append(("federal_rules", handle))

    if run_legislative_events:
        print("Spawning legislative events extraction...")
        # Extract state code from legislation_jurisdiction (e.g., "state-CA" -> "CA")
        state_code = legislation_jurisdiction.split("-")[-1] if "-" in legislation_jurisdiction else "CA"
        handle = extract_legislative_events.spawn(
            state=state_code,
            dry_run=dry_run,
        )
        handles.append(("legislative_events", handle))

    if run_meetings:
        print("Spawning meetings fetch...")
        handle = fetch_meetings.spawn(
            jurisdiction=jurisdiction,
            days_past=meetings_days_past,
            incremental=incremental,
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("meetings", handle))

    if run_issues:
        print("Spawning issues fetch...")
        handle = fetch_issues.spawn(
            jurisdiction=jurisdiction,
            incremental=incremental,
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("issues", handle))

    if run_elections:
        print("Spawning elections fetch...")
        handle = fetch_elections.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("elections", handle))

    if run_elected_officials:
        print("Spawning elected officials fetch...")
        handle = fetch_elected_officials.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
        )
        handles.append(("elected_officials", handle))

    if run_videos:
        print("Spawning videos fetch (YouTube)...")
        handle = fetch_videos.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
        )
        handles.append(("videos", handle))

    # Wait for fetch tasks to complete before chunks and vectors
    # (chunks need meetings fetched, vectors need all data ready)
    fetch_results = {}
    for name, handle in handles:
        print(f"\nWaiting for {name}...")
        result = handle.get()
        fetch_results[name] = result
        print(f"  {name}: {result.get('elapsed_seconds', 0):.1f}s, cost: ${result.get('cost_usd', 0):.4f}")

    # Extract transcripts after meetings are fetched (audio download + transcription)
    transcripts_result = None
    if run_transcripts:
        print("\nRunning transcript extraction (audio + transcription)...")
        transcripts_result = extract_transcripts.remote(
            jurisdiction=jurisdiction,
            limit=transcripts_limit,
            dry_run=dry_run,
            batch=True,  # Use batch mode for parallel transcription
            auto_index=auto_index,
        )
        print(f"  transcripts: {transcripts_result.get('elapsed_seconds', 0):.1f}s, cost: ${transcripts_result.get('cost_usd', 0):.4f}")
        if transcripts_result.get("duration_validation_issues", 0) > 0:
            print(f"  ⚠️ Duration validation issues: {transcripts_result.get('duration_validation_issues')}")

    # Extract chunks after meetings are fetched
    chunks_result = None
    if run_chunks:
        print("\nRunning chunk extraction...")
        chunks_result = extract_chunks.remote(
            jurisdiction=jurisdiction,
            limit=chunks_limit,
            dry_run=dry_run,
            auto_index=auto_index,
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
            auto_index=auto_index,
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
            auto_index=auto_index,
            since=decisions_since,
            until=decisions_until,
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
        elif name == "federal_programs":
            print(f"+ Federal Programs: {result.get('programs_fetched', 0)} fetched, {result.get('programs_stored', 0)} stored")
        elif name == "federal_rules":
            print(f"+ Federal Rules: {result.get('rules_fetched', 0)} fetched, {result.get('rules_stored', 0)} stored")
        elif name == "legislative_events":
            print(f"+ Legislative Events: {result.get('events_parsed', 0)} parsed, {result.get('events_stored', 0)} stored")
        elif name == "meetings":
            incr = " (incremental)" if result.get("incremental") else ""
            print(f"+ Meetings{incr}: {result.get('meetings_fetched', 0)} fetched, {result.get('meetings_stored', 0)} stored")
        elif name == "issues":
            incr = " (incremental)" if result.get("incremental") else ""
            print(f"+ Issues{incr}: {result.get('issues_fetched', 0)} fetched, {result.get('issues_stored', 0)} stored")
        elif name == "elections":
            print(f"+ Elections: {result.get('elections_fetched', 0)} fetched, {result.get('elections_stored', 0)} stored")
        elif name == "videos":
            print(f"+ Videos (YouTube): {result.get('videos_discovered', 0)} discovered, {result.get('videos_stored', 0)} stored")

    if transcripts_result:
        cost = transcripts_result.get("cost_usd", 0)
        total_cost += cost
        extracted = transcripts_result.get("transcripts_extracted", 0)
        skipped = transcripts_result.get("transcripts_skipped", 0)
        audio_downloaded = transcripts_result.get("audio_downloaded", 0)
        duration_issues = transcripts_result.get("duration_validation_issues", 0)
        transcription_cost = transcripts_result.get("transcription_cost_usd", 0)
        print(f"+ Transcripts: {extracted} transcribed, {skipped} skipped, {audio_downloaded} audio downloaded")
        print(f"    AssemblyAI cost: ${transcription_cost:.2f}")
        if duration_issues > 0:
            print(f"    ⚠️ Duration validation issues: {duration_issues}")

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
