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

    # Turnkey onboard (separate script — generates configs, then runs ingestion)
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin

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
    .apt_install("libpq-dev", "gcc", "ffmpeg", "nodejs")
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
        "yt-dlp>=2026.3.0",  # For audio download (YouTube patches extractors frequently; keep recent)
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
    # CIVICOS_EXTRACTION_DIR: used by civicos_config.paths for EXTRACTION_DIR
    # CIVICOS_CONFIG_DIR: used by civicos_extraction.config for get_config_dir()
    # CIVICOS_JURISDICTIONS_DIR: used by civicos_config.paths for JURISDICTIONS_DIR
    .env({
        "CIVICOS_EXTRACTION_DIR": "/config/extraction",
        "CIVICOS_CONFIG_DIR": "/config/extraction",
        "CIVICOS_JURISDICTIONS_DIR": "/config/jurisdictions",
    })
    # Add local civicos packages (add_local_* must be last)
    .add_local_python_source("civicos", "civicos_config", "civicos_extraction", "civicos_services")
    # Add jurisdiction config files for config-driven pipeline iteration
    .add_local_dir("data/extraction", remote_path="/config/extraction")
    # Add jurisdiction YAML configs (for data_sources routing, e.g. amlegal detection)
    .add_local_dir("data/jurisdictions", remote_path="/config/jurisdictions")
    # Add municipal code cache (AMLegal cached text + format specs)
    .add_local_dir("data/municipal_code", remote_path="/data/municipal_code")
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

    # Pass cache_dir for AMLegal jurisdictions (cached text mounted from local)
    cache_dir = "/data/municipal_code" if os.path.isdir("/data/municipal_code") else None
    corpus = MunicipalCodeCorpus.for_jurisdiction(jurisdiction, rate_limit=rate_limit,
                                                   cache_dir=cache_dir)

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

    # Capture fingerprint for future refresh comparisons
    fingerprint = None
    if hasattr(corpus, "get_fingerprint"):
        try:
            fingerprint = corpus.get_fingerprint()
        except Exception:
            pass

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
                last_fetch_hash=fingerprint,
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
# Municipal Code Refresh (incremental)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=7200,
)
def refresh_municipal_code(
    jurisdiction: str = "city-san-rafael",
    force: bool = False,
    dry_run: bool = False,
    reindex: bool = True,
) -> dict:
    """Refresh municipal code if it has changed since the last fetch.

    Checks for updates using publisher-specific fingerprinting (Municode job
    publish date, AMLegal supplement string), then diffs against Postgres and
    upserts only changed sections. Re-embeds changed sections afterward.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        force: Skip interval/fingerprint checks and always refresh
        dry_run: Check for changes but don't store
        reindex: Re-embed changed sections after upsert
    """
    import logging
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    from civicos._internal.legal.corpus.refresh import RefreshRunner
    from civicos.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    backend = PostgresBackend(database_url)

    # For vector reindexing, use the remote index_vectors function
    # RefreshRunner handles the diff/upsert; we trigger reindex separately
    runner = RefreshRunner(storage_backend=backend)

    logger.info(f"[REFRESH] Starting municipal code refresh: {jurisdiction}")
    result = runner.refresh_municipal_code(
        jurisdiction_id=jurisdiction,
        force=force,
        dry_run=dry_run,
        reindex_vectors=False,  # We'll trigger Modal reindex below
    )

    logger.info(
        f"[REFRESH] {jurisdiction}: {result.status} "
        f"(+{result.sections_added} ~{result.sections_modified} "
        f"-{result.sections_removed} ={result.sections_unchanged})"
    )

    # Trigger vector reindexing via Modal if sections changed
    vector_result = None
    if (
        reindex
        and not dry_run
        and result.status == "updated"
        and (result.sections_added + result.sections_modified) > 0
    ):
        logger.info(f"[REFRESH] Triggering vector reindex for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="municipal_code",
            reindex=True,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    output = {
        "task": "refresh_municipal_code",
        "jurisdiction": jurisdiction,
        "status": result.status,
        "sections_added": result.sections_added,
        "sections_modified": result.sections_modified,
        "sections_removed": result.sections_removed,
        "sections_unchanged": result.sections_unchanged,
        "dry_run": dry_run,
        "force": force,
        "elapsed_seconds": result.elapsed_seconds,
    }
    if result.change_signal:
        output["fingerprint"] = result.change_signal.new_fingerprint
        output["change_message"] = result.change_signal.message
    if vector_result:
        output["vector_result"] = vector_result
    if result.error:
        output["error"] = result.error

    return output


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

        # Run vector+LLM relevance scoring after indexing
        logger.info("[RULES] Running vector+LLM relevance scoring...")
        llm_result = score_federal_rules_llm.remote(dry_run=dry_run)
        logger.info(f"  LLM scoring: {llm_result.get('candidates_scored', 0)} rules scored")

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
# Vector+LLM Relevance Scoring for Federal Rules
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=3600,  # 1 hour (LLM calls)
)
def score_federal_rules_llm(
    jurisdiction: str = "city-san-rafael",
    dry_run: bool = False,
) -> dict:
    """Score federal rules using vector similarity + LLM confirmation pipeline.

    3-stage pipeline:
    1. Build policy vectors from municipal_code embeddings
    2. Retrieve candidate federal rules via pgvector cosine similarity
    3. Score candidates with gpt-4o-mini for local relevance + summary

    Args:
        jurisdiction: Source jurisdiction for policy vectors
        dry_run: If True, run but don't write results
    """
    import logging
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos.storage.pgvector_backend import PgVectorBackend
    from civicos._internal.legal.vector_relevance import run_vector_llm_pipeline

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    vector_backend = PgVectorBackend(database_url)

    result = run_vector_llm_pipeline(
        storage_backend=backend,
        pgvector_backend=vector_backend,
        jurisdiction_id=jurisdiction,
        federal_jurisdiction="federal-US",
        dry_run=dry_run,
    )

    logger.info(f"[LLM-RELEVANCE] Pipeline complete: {result}")
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
# Federal Awards (USAspending.gov)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=3600,  # 1 hour
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_federal_awards(
    dry_run: bool = False,
    auto_index: bool = False,
    max_pages: int = 20,
) -> dict:
    """Fetch federal awards from USAspending.gov for all configured jurisdictions.

    Iterates jurisdiction configs looking for 'usaspending' section with
    recipient_name (and optional recipient_uei). Fetches grants and direct
    payments, stores via store_federal_awards(), optionally indexes vectors.

    Args:
        dry_run: If True, fetch but don't store
        auto_index: If True, index vectors after storing
        max_pages: Max pages per award group per jurisdiction

    Returns:
        Dict with per-jurisdiction results
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    from civicos.storage import get_storage_backend
    from civicos.jurisdiction_config import get_jurisdictions_with_usaspending
    from civicos_extraction.clients.usaspending import USAspendingClient

    backend = get_storage_backend(database_url)

    # Read USAspending config from jurisdiction YAML (data/jurisdictions/*.yaml)
    jurisdictions = get_jurisdictions_with_usaspending()
    logger.info(f"Found {len(jurisdictions)} jurisdictions with USAspending config")

    start_time = time.time()
    results = {}
    total_stored = 0

    for jid, config in jurisdictions.items():
        usa = config.federal_programs.usaspending
        search_names = usa.search_names
        allowed_names = usa.allowed_names
        recipient_uei = usa.recipient_uei

        if not search_names and not recipient_uei:
            logger.warning(f"[{jid}] usaspending config has no search_names or recipient_uei, skipping")
            continue

        # Ensure allowed_names includes all search_names
        for sn in search_names:
            if sn not in allowed_names:
                allowed_names.append(sn)

        logger.info(f"[{jid}] Fetching federal awards (names={search_names}, uei={recipient_uei})")

        # Run one search per name, deduplicate by award_id
        all_awards = {}
        for search_name in search_names:
            client = USAspendingClient(
                jurisdiction_id=jid,
                recipient_name=search_name,
                recipient_uei=recipient_uei,
            )
            batch = client.get_awards(max_pages=max_pages)
            for a in batch:
                aid = a.get("award_id")
                if aid and aid not in all_awards:
                    all_awards[aid] = a
            time.sleep(0.5)

        awards = list(all_awards.values())
        raw_count = len(awards)

        # Filter false positives: only keep awards whose recipient_name
        # matches one of the allowed names (case-insensitive)
        if allowed_names and not recipient_uei:
            allowed_upper = {n.upper() for n in allowed_names}
            awards = [a for a in awards if a.get("recipient_name", "").upper() in allowed_upper]
            if len(awards) < raw_count:
                logger.info(f"[{jid}] Filtered {raw_count - len(awards)} false positives (kept {len(awards)})")

        logger.info(f"[{jid}] Fetched {len(awards)} awards from USAspending")

        if dry_run:
            results[jid] = {"fetched": len(awards), "stored": 0, "dry_run": True}
            continue

        if not awards:
            results[jid] = {"fetched": 0, "stored": 0}
            continue

        stored = backend.store_federal_awards(jid, awards)
        total_stored += stored
        logger.info(f"[{jid}] Stored {stored} awards")
        results[jid] = {"fetched": len(awards), "stored": stored}

    # Auto-index vectors for jurisdictions that got awards
    vector_result = None
    if auto_index and not dry_run and total_stored > 0:
        logger.info("Auto-indexing federal_awards vectors...")
        for jid in results:
            if results[jid].get("stored", 0) > 0:
                try:
                    vr = index_vectors.local(
                        jurisdiction=jid,
                        corpus="federal_awards",
                        reindex=True,
                    )
                    results[jid]["vector_result"] = vr
                    logger.info(f"[{jid}] Indexed {vr.get('federal_awards', {}).get('indexed', 0)} vectors")
                except Exception as e:
                    logger.warning(f"[{jid}] Vector indexing failed: {e}")
                    results[jid]["vector_error"] = str(e)

    elapsed = time.time() - start_time
    return {
        "status": "success",
        "total_stored": total_stored,
        "jurisdictions": results,
        "auto_index": auto_index,
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 1),
    }


# =============================================================================
# Congressional Votes (Congress.gov API + House Clerk XML + Senate XML)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=2048,
    timeout=3600,  # 1 hour
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_congressional_votes(
    congress: int = 119,
    session: int = 1,
    bioguide_ids: list = None,
    max_roll_calls: int = 50,
    dry_run: bool = False,
) -> dict:
    """Fetch congressional roll call votes for tracked representatives.

    Fetches House and Senate roll call votes, extracts per-member positions
    from House Clerk XML and Senate.gov XML, and stores them in the
    congressional_votes table linked to elected_officials by bioguide_id.

    Args:
        congress: Congress number (default: 119, the current congress)
        session: Session number (1 or 2)
        bioguide_ids: Specific bioguide IDs to fetch. If None, reads from
            elected_officials table (federal reps only).
        max_roll_calls: Max number of roll calls to process per chamber
        dry_run: If True, fetch but don't store

    Returns:
        Dict with results summary
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    from civicos.storage import get_storage_backend
    from civicos_extraction.clients.representatives import CongressGovClient

    backend = get_storage_backend(database_url)
    client = CongressGovClient()

    if not client.api_key:
        raise ValueError("No Congress.gov API key configured")

    start_time = time.time()

    # If no bioguide_ids specified, get federal reps from elected_officials table
    if not bioguide_ids:
        from civicos_extraction.config import get_active_jurisdictions
        jurisdictions = get_active_jurisdictions()
        all_officials = []
        for jid in jurisdictions:
            try:
                officials = backend.get_elected_officials(jid, current_only=True)
                all_officials.extend(officials)
            except Exception:
                pass  # Skip jurisdictions without elected_officials support
        # Extract bioguide_id from "congress-{bioguideId}" format
        bioguide_ids = list({
            o["id"].replace("congress-", "")
            for o in all_officials
            if o.get("id", "").startswith("congress-")
        })
        logger.info(f"Found {len(bioguide_ids)} federal reps in elected_officials")

    if not bioguide_ids:
        return {"status": "no_representatives", "message": "No federal reps found in elected_officials"}

    bioguide_set = set(bioguide_ids)
    all_votes = []
    house_roll_calls_processed = 0
    senate_votes_processed = 0

    # ---- House votes ----
    logger.info(f"Fetching House roll calls for Congress {congress}, Session {session}...")
    house_roll_calls = client.get_house_roll_calls(congress, session, limit=250)
    logger.info(f"Found {len(house_roll_calls)} House roll calls")

    # Process most recent first (reverse chronological from API)
    for rc in house_roll_calls[:max_roll_calls]:
        roll_call_num = rc.get("rollCallNumber")
        if not roll_call_num:
            continue

        vote_date = rc.get("startDate", "")[:10]  # Extract YYYY-MM-DD
        legis_type = rc.get("legislationType", "")
        legis_num = rc.get("legislationNumber", "")
        bill_id_str = f"{legis_type}{legis_num}" if legis_type and legis_num else None
        vote_id = f"H-{congress}-{session}-{roll_call_num}"

        # Fetch per-member votes from House Clerk XML
        member_votes = client.get_house_member_votes(
            congress, session, roll_call_num, bioguide_ids=list(bioguide_set)
        )

        for mv in member_votes:
            all_votes.append({
                "vote_id": vote_id,
                "bioguide_id": mv["bioguide_id"],
                "chamber": "House",
                "congress": congress,
                "session": session,
                "roll_call_number": roll_call_num,
                "vote_date": vote_date,
                "vote_position": mv["vote"],
                "bill_id": bill_id_str,
                "bill_title": mv.get("vote_description", ""),
                "vote_question": mv.get("vote_question", rc.get("voteType", "")),
                "vote_result": mv.get("vote_result", rc.get("result", "")),
                "member_name": mv.get("name", ""),
                "member_party": mv.get("party", ""),
                "member_state": mv.get("state", ""),
            })

        house_roll_calls_processed += 1
        if house_roll_calls_processed % 10 == 0:
            logger.info(f"Processed {house_roll_calls_processed} House roll calls, {len(all_votes)} votes so far")

    # ---- Senate votes ----
    # Senate doesn't have a convenient list API; we iterate vote numbers
    logger.info(f"Fetching Senate votes for Congress {congress}, Session {session}...")

    # Build name→bioguide_id mapping from elected_officials for Senate matching.
    # Senate XML uses lis_member_id (not bioguide), so we match by state to
    # identify our tracked senators, then store with lis_member_id as the
    # identifier (bioguide mapping would require a separate lookup table).
    tracked_states = set()
    conn = backend._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, metadata FROM elected_officials
        WHERE id LIKE 'congress-%%'
          AND valid_to IS NULL AND deleted_at IS NULL
    """)
    for row in cursor.fetchall():
        # We track all states that have federal reps — Senate votes for
        # senators from these states will be stored
        meta = row[1] if row[1] else {}
        state = meta.get("state") if isinstance(meta, dict) else None
        if state:
            tracked_states.add(state)
    backend._return_connection(conn)

    # Try fetching Senate votes by number (start from most recent)
    # Senate.gov XML uses sequential vote numbers within a session
    senate_vote_num = 1
    consecutive_failures = 0
    max_failures = 5  # Stop after 5 consecutive 404s (reached end of votes)

    while senate_votes_processed < max_roll_calls and consecutive_failures < max_failures:
        member_votes = client.get_senate_member_votes(
            congress, session, senate_vote_num
        )

        if not member_votes:
            consecutive_failures += 1
            senate_vote_num += 1
            continue

        consecutive_failures = 0
        vote_id = f"S-{congress}-{session}-{senate_vote_num}"

        # Filter to senators from tracked states (e.g., CA)
        # Store with lis_member_id as bioguide_id since Senate XML
        # doesn't provide bioguide IDs directly
        for mv in member_votes:
            vote_date = mv.get("vote_date", "")
            if not vote_date:
                # Skip votes without a parseable date
                continue
            all_votes.append({
                "vote_id": vote_id,
                "bioguide_id": mv.get("lis_member_id", ""),
                "chamber": "Senate",
                "congress": congress,
                "session": session,
                "roll_call_number": senate_vote_num,
                "vote_date": vote_date,
                "vote_position": mv["vote"],
                "bill_id": mv.get("legislation_number", ""),
                "bill_title": mv.get("vote_description", ""),
                "vote_question": mv.get("vote_question", ""),
                "vote_result": mv.get("vote_result", ""),
                "member_name": mv.get("name", ""),
                "member_party": mv.get("party", ""),
                "member_state": mv.get("state", ""),
            })

        senate_votes_processed += 1
        senate_vote_num += 1

        if senate_votes_processed % 10 == 0:
            logger.info(f"Processed {senate_votes_processed} Senate votes, {len(all_votes)} total votes")

    logger.info(f"Total votes collected: {len(all_votes)} (House: {house_roll_calls_processed} roll calls, Senate: {senate_votes_processed} votes)")

    if dry_run:
        elapsed = time.time() - start_time
        return {
            "status": "dry_run",
            "total_votes": len(all_votes),
            "house_roll_calls": house_roll_calls_processed,
            "senate_votes": senate_votes_processed,
            "bioguide_ids": bioguide_ids,
            "elapsed_seconds": round(elapsed, 1),
        }

    if not all_votes:
        return {"status": "no_votes", "total_votes": 0}

    stored = backend.store_congressional_votes(all_votes)
    elapsed = time.time() - start_time

    logger.info(f"Stored {stored} congressional votes in {elapsed:.1f}s")

    return {
        "status": "success",
        "total_stored": stored,
        "house_roll_calls": house_roll_calls_processed,
        "senate_votes": senate_votes_processed,
        "bioguide_ids": bioguide_ids,
        "elapsed_seconds": round(elapsed, 1),
    }


# =============================================================================
# Congressional Hearings
# =============================================================================


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=2048,
    timeout=3600,
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_congressional_hearings(
    congress: int = 119,
    days_back: int = 90,
    days_ahead: int = 60,
    dry_run: bool = False,
) -> dict:
    """Fetch congressional committee hearings from Congress.gov API.

    Fetches both House and Senate committee hearings and stores them in
    the congressional_hearings table. Retrieves detail for each meeting
    to get committee info, location, and related bills.

    Args:
        congress: Congress number (default: 119)
        days_back: How many days back to look for past hearings
        days_ahead: How many days ahead to look for upcoming hearings
        dry_run: If True, fetch but don't store

    Returns:
        Dict with results summary
    """
    import logging
    import os
    import time
    from datetime import datetime, timedelta, timezone

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    from civicos.storage import get_storage_backend
    from civicos_extraction.clients.representatives import CongressGovClient

    backend = get_storage_backend(database_url)
    client = CongressGovClient()

    if not client.api_key:
        raise ValueError("No Congress.gov API key configured")

    start_time = time.time()
    now = datetime.now(timezone.utc)
    date_start = now - timedelta(days=days_back)
    date_end = now + timedelta(days=days_ahead)

    all_hearings = []
    errors = 0

    for chamber in ["house", "senate"]:
        logger.info(f"Fetching {chamber} committee meetings for congress {congress}...")

        # Paginate through the list endpoint
        offset = 0
        page_limit = 250
        chamber_meetings = []

        while True:
            meetings = client.get_committee_hearings(
                congress=congress, chamber=chamber,
                limit=page_limit, offset=offset,
            )
            if not meetings:
                break

            chamber_meetings.extend(meetings)
            offset += page_limit

            # Congress.gov returns all meetings for the congress, so we
            # fetch until we have them all (or hit a reasonable cap)
            if len(meetings) < page_limit or offset >= 5000:
                break

        logger.info(f"  Found {len(chamber_meetings)} {chamber} committee meetings total")

        # Fetch detail for each meeting to get full info
        detailed = 0
        for meeting_summary in chamber_meetings:
            event_id = meeting_summary.get("eventId")
            if not event_id:
                continue

            detail = client.get_committee_hearing_detail(
                congress=congress,
                chamber=chamber,
                event_id=str(event_id),
            )
            if not detail:
                errors += 1
                continue

            # Parse hearing date and filter to our window
            hearing_date_str = detail.get("date")
            if hearing_date_str:
                try:
                    hearing_dt = datetime.fromisoformat(hearing_date_str.replace("Z", "+00:00"))
                    if hearing_dt < date_start or hearing_dt > date_end:
                        continue
                except (ValueError, TypeError):
                    pass

            # Extract committee info
            committees = detail.get("committees", [])
            committee_name = committees[0].get("name", "") if committees else ""
            committee_code = committees[0].get("systemCode", "") if committees else ""

            # Extract related bills from meetingDocuments
            related_bills = []
            for doc in detail.get("meetingDocuments", []):
                if doc.get("documentType") == "Bills and Resolutions":
                    related_bills.append({
                        "name": doc.get("name", ""),
                        "url": doc.get("url", ""),
                    })

            # Extract location
            location = detail.get("location", {})

            chamber_title = chamber.capitalize()
            if chamber == "house":
                chamber_title = "House"

            hearing_record = {
                "event_id": str(event_id),
                "chamber": chamber_title,
                "congress": congress,
                "hearing_date": hearing_date_str,
                "title": detail.get("title", ""),
                "hearing_type": detail.get("type", ""),
                "meeting_status": detail.get("meetingStatus", ""),
                "committee_name": committee_name,
                "committee_code": committee_code,
                "location_building": location.get("building", ""),
                "location_room": location.get("room", ""),
                "related_bills": related_bills if related_bills else None,
                "hearing_url": f"https://www.congress.gov/event/{congress}th-congress/{chamber}/{event_id}",
            }

            all_hearings.append(hearing_record)
            detailed += 1

        logger.info(f"  Detailed {detailed} {chamber} hearings within date window")

    logger.info(f"Total hearings collected: {len(all_hearings)} ({errors} detail fetch errors)")

    if dry_run:
        elapsed = time.time() - start_time
        return {
            "status": "dry_run",
            "total_hearings": len(all_hearings),
            "errors": errors,
            "elapsed_seconds": round(elapsed, 1),
        }

    if not all_hearings:
        return {"status": "no_hearings", "total_hearings": 0}

    stored = backend.store_congressional_hearings(all_hearings)
    elapsed = time.time() - start_time

    logger.info(f"Stored {stored} congressional hearings in {elapsed:.1f}s")

    return {
        "status": "success",
        "total_stored": stored,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
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

    Returns error dict instead of raising, so starmap doesn't cancel all workers.
    """
    import logging
    import os
    import hashlib

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    try:
        return _embed_and_store_batch_inner(chunks, jurisdiction_id, corpus_type, reindex)
    except Exception as e:
        logger.exception(f"Worker failed for {corpus_type} ({len(chunks)} chunks): {e}")
        return {"success": 0, "failed": len(chunks), "error": str(e)}


def _embed_and_store_batch_inner(
    chunks: list[dict],
    jurisdiction_id: str,
    corpus_type: str,
    reindex: bool = False,
) -> dict:
    """Inner implementation of _embed_and_store_batch (unwrapped for clarity)."""
    import logging
    import os
    import hashlib

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
    from civicos._internal.jurisdiction import JurisdictionError
    from civicos._internal.meetings.transcript import expand_transcripts_to_chunks
    from civicos._internal.legal.embeddings.chunker import (
        expand_municipal_code_to_chunks,
        expand_legislation_to_chunks,
        expand_executive_orders_to_chunks,
        expand_federal_rules_to_chunks,
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
        all_corpus_types = ["programs", "executive_orders", "federal_rules", "legislation"]
    else:
        all_corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues", "agenda_items", "budget_items", "federal_awards"]

    corpus_types = all_corpus_types if corpus == "all" else [corpus]
    results = {}

    for ct in corpus_types:
        logger.info(f"Processing corpus: {ct}")

        if reindex:
            deleted = pgvector.delete_index(jurisdiction, ct)
            logger.info(f"  Deleted {deleted} existing vectors")

        # Deferred indexing: drop HNSW index before bulk insert, rebuild after.
        # With partitioned tables, this only affects the corpus_type partition,
        # so other corpus types remain fully indexed and searchable.
        pgvector.drop_hnsw_index(ct)

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
        elif ct == "federal_rules":
            raw = backend.get_federal_rules()
            chunks = expand_federal_rules_to_chunks(raw)
        elif ct == "budget_items":
            try:
                chunks = backend.get_budget_items(jurisdiction)
            except JurisdictionError:
                logger.warning(f"  Skipping budget_items: {jurisdiction} not in jurisdiction registry")
                pgvector.rebuild_hnsw_index(ct)
                results[ct] = {"status": "skipped", "indexed": 0}
                continue
        elif ct == "federal_awards":
            try:
                raw = backend.get_federal_awards(jurisdiction)
            except JurisdictionError:
                logger.warning(f"  Skipping federal_awards: {jurisdiction} not in jurisdiction registry")
                pgvector.rebuild_hnsw_index(ct)
                results[ct] = {"status": "skipped", "indexed": 0}
                continue
            chunks = []
            for award in raw:
                parts = []
                if award.get("awarding_agency"):
                    parts.append(f"Agency: {award['awarding_agency']}")
                if award.get("recipient_name"):
                    parts.append(f"Recipient: {award['recipient_name']}")
                if award.get("program_name"):
                    parts.append(award["program_name"])
                if award.get("award_type"):
                    parts.append(f"Type: {award['award_type']}")
                amount = award.get("amount_cents", 0)
                if amount:
                    parts.append(f"Amount: ${amount / 100:,.0f}")
                text = "\n".join(parts)
                if not text.strip():
                    continue
                chunks.append({
                    "id": f"award-{award.get('award_id', '')}",
                    "text": text,
                    "award_id": award.get("award_id"),
                    "recipient_name": award.get("recipient_name"),
                    "awarding_agency": award.get("awarding_agency"),
                    "amount_cents": amount,
                    "metadata": {
                        "cfda_number": award.get("cfda_number"),
                        "period_start": award.get("period_start"),
                        "period_end": award.get("period_end"),
                    },
                })
        else:
            logger.warning(f"Unknown corpus type: {ct}")
            continue

        if not chunks:
            logger.warning(f"  No chunks found for {ct}")
            # Rebuild index even if no new chunks (we dropped it above)
            pgvector.rebuild_hnsw_index(ct)
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

            # Run parallel workers (individual failures return error dicts, not exceptions)
            worker_results = list(_embed_and_store_batch.starmap(batches))

            # Aggregate results (workers return error dicts on failure instead of raising)
            failed_workers = [r for r in worker_results if r.get("error")]
            if failed_workers:
                logger.warning(f"  {len(failed_workers)}/{len(worker_results)} workers failed for {ct}")
                for fw in failed_workers:
                    logger.warning(f"    Worker error: {fw['error']}")
            total_success = sum(r.get("success", 0) for r in worker_results)
            total_failed = sum(r.get("failed", 0) for r in worker_results)
            num_batches = len(batches)

        # Rebuild HNSW index after bulk inserts complete
        logger.info(f"  Rebuilding HNSW index for {ct}...")
        index_rebuilt = pgvector.rebuild_hnsw_index(ct)

        results[ct] = {
            "status": "success" if total_failed == 0 else "partial",
            "indexed": total_success,
            "failed": total_failed,
            "workers": num_batches,
            "hnsw_rebuilt": index_rebuilt,
        }
        logger.info(f"  Indexed {total_success} chunks ({total_failed} failed), HNSW {'rebuilt' if index_rebuilt else 'FAILED'}")

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
    """Fetch meetings from configured source (ProudCity, Granicus, etc.).

    Source type is auto-detected from the jurisdiction's ExtractionConfig
    in data/extraction/{jurisdiction}.json.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael", "county-marin")
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
    from civicos_extraction.clients.base import ExtractionConfig

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    # Load extraction config to determine source type
    config = ExtractionConfig.from_jurisdiction(jurisdiction)
    source_type = config.source_type
    logger.info(f"[MEETINGS] Starting fetch: jurisdiction={jurisdiction}, source={source_type}, incremental={incremental}")

    # Determine date range
    if incremental:
        metadata = backend.get_refresh_metadata(jurisdiction, "meetings", source_type)
        if metadata and metadata.get("last_fetch_at"):
            last_fetch = datetime.fromisoformat(metadata["last_fetch_at"])
            days_since = (datetime.now() - last_fetch).days
            days_past = min(days_past, max(7, days_since + 1))  # At least 7 days overlap
            logger.info(f"  Incremental mode: last fetch {days_since} days ago, fetching {days_past} days back")

    # Instantiate source-specific client based on extraction config.
    # When adding a new source type here, also add it to
    # SUPPORTED_MEETING_SOURCES in civicos_extraction/clients/__init__.py.
    try:
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
        elif source_type == "boarddocs":
            # BoardDocs needs full client for agenda extraction — delegate to standalone function
            # which fetches meetings + agendas + stores chunks and agenda items directly
            result = fetch_boarddocs_meetings.remote(
                app_path=config.metadata.get("app_path", ""),
                jurisdiction=jurisdiction,
                committee_id=config.metadata.get("committee_id", ""),
                dry_run=dry_run,
            )
            return result
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
        elif source_type == "simbli":
            # Simbli requires Playwright (separate image), delegate to standalone function
            result = fetch_simbli_meetings.remote(
                jurisdiction=jurisdiction,
                days_past=days_past,
                dry_run=dry_run,
            )
            return result
        elif source_type == "playwright_llm":
            # Playwright+LLM requires browser (separate image), delegate
            result = fetch_playwright_llm_meetings.remote(
                jurisdiction=jurisdiction,
                days_past=days_past,
                dry_run=dry_run,
            )
            return result
        else:
            from civicos_extraction.clients import SUPPORTED_MEETING_SOURCES
            logger.warning(f"[MEETINGS] source_type '{source_type}' not yet supported "
                           f"(supported: {', '.join(sorted(SUPPORTED_MEETING_SOURCES))}) — skipping")
            return {
                "meetings_fetched": 0,
                "meetings_stored": 0,
                "incremental": incremental,
                "skipped": True,
                "skip_reason": f"source_type '{source_type}' not yet supported",
                "elapsed_seconds": 0,
                "cost_usd": 0,
            }
    except Exception as e:
        logger.error(f"Error fetching meetings: {e}")
        backend.update_refresh_metadata(
            jurisdiction, "meetings", source_type,
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
            jurisdiction, "meetings", source_type,
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
    """Fetch 311 issues from configured source (SeeClickFix, etc.).

    Source type is read from the jurisdiction's ExtractionConfig
    ``issue_source`` field (default: "seeclickfix").

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
    from civicos_extraction.clients.base import ExtractionConfig

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    # Load extraction config to determine issue source
    config = ExtractionConfig.from_jurisdiction(jurisdiction)
    issue_source = config.issue_source or "seeclickfix"
    logger.info(f"[ISSUES] Starting fetch: jurisdiction={jurisdiction}, source={issue_source}, incremental={incremental}")

    # Instantiate source-specific client based on extraction config.
    # When adding a new issue source here, also add it to
    # SUPPORTED_ISSUE_SOURCES in civicos_extraction/clients/__init__.py.
    if issue_source == "seeclickfix":
        from civicos_services.clients.seeclickfix_client import SeeClickFixClient

        # Derive place_url from jurisdiction
        place_url = jurisdiction
        for prefix in ["city-", "county-", "town-"]:
            if place_url.startswith(prefix):
                place_url = place_url[len(prefix):]
                break

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
    else:
        from civicos_extraction.clients import SUPPORTED_ISSUE_SOURCES
        logger.warning(f"[ISSUES] issue_source '{issue_source}' not yet supported "
                       f"(supported: {', '.join(sorted(SUPPORTED_ISSUE_SOURCES))}) — skipping")
        return {
            "task": "issues",
            "jurisdiction": jurisdiction,
            "issues_fetched": 0,
            "issues_stored": 0,
            "pages_fetched": 0,
            "incremental": incremental,
            "skipped": True,
            "skip_reason": f"issue_source '{issue_source}' not yet supported",
            "elapsed_seconds": 0,
            "cost_usd": 0,
        }

    logger.info(f"Fetched {len(all_issues)} issues total")

    # Store issues
    stored_count = 0
    if not dry_run and all_issues:
        try:
            stored_count = backend.store_issues(jurisdiction, all_issues)
            logger.info(f"Stored {stored_count} issues")

            # Update refresh metadata
            backend.update_refresh_metadata(
                jurisdiction, "issues", issue_source,
                items_fetched=len(all_issues),
                items_stored=stored_count,
                status="completed",
            )
        except Exception as e:
            logger.error(f"Error storing issues: {e}")
            backend.update_refresh_metadata(
                jurisdiction, "issues", issue_source,
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
        "issue_source": issue_source,
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
# Election Refresh Tracking (shared by all election fetch functions)
# =============================================================================

def _detect_election_transition(
    backend,
    jurisdiction: str,
    source_name: str,
    new_election_ids: list,
    counts: dict,
    logger,
    count_fields: tuple = ("elections", "contests", "candidates"),
    extra_hash_input: str = "",
) -> tuple:
    """Detect election cycle transitions and compute a refresh fingerprint.

    Checks previous refresh metadata for this source, compares election IDs,
    and logs any transitions. Returns a fingerprint suitable for last_fetch_hash
    and transition info if a cycle change was detected.

    Args:
        backend: PostgresBackend instance
        jurisdiction: Target jurisdiction
        source_name: Election source (e.g., "ca_sos_results", "civera_election_stats")
        new_election_ids: Election IDs returned by the current fetch
        counts: Dict of counts from extraction (e.g., elections, contests, candidates)
        logger: Logger instance
        count_fields: Tuple of keys in counts to include in the hash
        extra_hash_input: Additional string to include in hash (e.g., year range)

    Returns:
        (fingerprint, cycle_transition_or_None)
    """
    import hashlib
    import time as _time

    prev_meta = backend.get_refresh_metadata(jurisdiction, "elections", source_name)
    prev_ids = set()
    if prev_meta and prev_meta.get("last_fetch_hash"):
        # Fingerprint format: "{id1,id2,...}:{count_hash}" or legacy "{count_hash}"
        parts = prev_meta["last_fetch_hash"].split(":", 1)
        if len(parts) == 2 and not all(c in "0123456789abcdef" for c in parts[0]):
            prev_ids = set(parts[0].split(",")) if parts[0] else set()

    new_ids = set(new_election_ids) if new_election_ids else set()

    # Skip transition detection if the fetch returned no elections —
    # an empty set likely means the API timed out or is between cycles,
    # not that all elections were removed.  Preserve the previous fingerprint.
    if not new_ids:
        prev_hash = prev_meta.get("last_fetch_hash", "") if prev_meta else ""
        count_values = ":".join(str(counts.get(f, 0)) for f in count_fields)
        if extra_hash_input:
            count_values += f":{extra_hash_input}"
        count_hash = hashlib.sha256(count_values.encode()).hexdigest()[:16]
        # Keep previous IDs in fingerprint to avoid false transitions on next run
        if prev_hash and ":" in prev_hash:
            ids_part = prev_hash.rsplit(":", 1)[0]
            return f"{ids_part}:{count_hash}", None
        return count_hash, None

    cycle_transition = None
    if prev_ids and new_ids and prev_ids != new_ids:
        removed = sorted(prev_ids - new_ids)
        added = sorted(new_ids - prev_ids)
        cycle_transition = {
            "previous_ids": sorted(prev_ids),
            "new_ids": sorted(new_ids),
            "added": added,
            "removed": removed,
            "detected_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        }
        logger.warning(
            f"Election cycle transition for {jurisdiction} [{source_name}]: "
            f"removed={removed}, added={added}. "
            f"Previous data preserved via temporal versioning."
        )

    # Fingerprint: "{sorted_ids}:{count_hash}"
    ids_str = ",".join(sorted(new_ids)) if new_ids else ""
    count_values = ":".join(str(counts.get(f, 0)) for f in count_fields)
    if extra_hash_input:
        count_values += f":{extra_hash_input}"
    count_hash = hashlib.sha256(count_values.encode()).hexdigest()[:16]
    fingerprint = f"{ids_str}:{count_hash}" if ids_str else count_hash

    return fingerprint, cycle_transition


# =============================================================================
# Marin Election Results Fetch (GraphQL — ElectionStats / Civera)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=4096,
    timeout=900,  # 15 minutes (fetches 46 elections with contests)
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_marin_election_results(
    jurisdiction: str = "city-san-rafael",
    from_year: int = 2010,
    to_year: int = 2026,
    division_filter: str = "",
    dry_run: bool = False,
    auto_index: bool = False,
) -> dict:
    """Fetch historical election results from Marin County GraphQL API.

    Queries pastelections.marincounty.gov (ElectionStats by Civera) for
    election results including contests, candidates, vote counts, and winners.
    No API key required.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        from_year: Start year for election range (default 2010)
        to_year: End year for election range (default 2026)
        division_filter: Filter contests to this division (e.g., "City of San Rafael")
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.marin_registrar import (
        MarinRegistrarResultsClient,
        extract_marin_results_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(
        f"[MARIN RESULTS] Starting fetch: jurisdiction={jurisdiction}, "
        f"years={from_year}-{to_year}, division={division_filter or 'all'}"
    )

    # Create client and validate
    client = MarinRegistrarResultsClient(jurisdiction_id=jurisdiction)
    validation = client.validate()
    if not validation.is_valid:
        raise RuntimeError(f"Marin Registrar GraphQL validation failed: {validation.errors}")

    if dry_run:
        # Dry run: just list elections
        events = client.list_elections(from_year=from_year, to_year=to_year)
        elapsed = time.time() - start_time
        return {
            "task": "marin_election_results",
            "jurisdiction": jurisdiction,
            "elections_found": len(events),
            "elections_stored": 0,
            "contests_stored": 0,
            "candidates_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 4 * elapsed * 0.000463,
        }

    # Extract and store
    backend = PostgresBackend(database_url)
    counts = extract_marin_results_to_storage(
        client=client,
        storage=backend,
        jurisdiction_id=jurisdiction,
        from_year=from_year,
        to_year=to_year,
        division_filter=division_filter or None,
    )

    # Detect election cycle transitions and compute fingerprint
    fingerprint, cycle_transition = _detect_election_transition(
        backend, jurisdiction, "marin_registrar_results",
        counts.get("election_ids", []), counts, logger,
        extra_hash_input=f"{from_year}-{to_year}",
    )

    # Update refresh metadata
    backend.update_refresh_metadata(
        jurisdiction, "elections", "marin_registrar_results",
        items_fetched=counts["elections"] + counts["contests"],
        items_stored=counts["elections"] + counts["contests"],
        status="completed",
        last_fetch_hash=fingerprint,
    )

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and counts["elections"] > 0:
        logger.info(f"[MARIN RESULTS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="elections",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "marin_election_results",
        "jurisdiction": jurisdiction,
        "elections_stored": counts["elections"],
        "contests_stored": counts["contests"],
        "candidates_stored": counts["candidates"],
        "from_year": from_year,
        "to_year": to_year,
        "division_filter": division_filter or None,
        "dry_run": False,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if cycle_transition:
        result["cycle_transition"] = cycle_transition
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# Civera ElectionStats Fetch (GraphQL — generalized for any Civera county)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=4096,
    timeout=900,  # 15 minutes (may fetch 50+ elections with contests)
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_civera_election_results(
    jurisdiction: str = "county-sonoma",
    county_slug: str = "",
    graphql_url: str = "",
    from_year: int = 2010,
    to_year: int = 2026,
    division_filter: str = "",
    dry_run: bool = False,
    auto_index: bool = False,
) -> dict:
    """Fetch historical election results from a Civera ElectionStats GraphQL API.

    Generalized version of fetch_marin_election_results that works with any
    county running the Civera ElectionStats platform (Marin, Sonoma, Yolo, etc.).

    Args:
        jurisdiction: Target jurisdiction (e.g., "county-sonoma")
        county_slug: County identifier for ID namespacing (e.g., "sonoma")
                     If empty, looked up from CIVERA_INSTANCES registry.
        graphql_url: GraphQL endpoint URL. If empty, looked up from CIVERA_INSTANCES.
        from_year: Start year for election range (default 2010)
        to_year: End year for election range (default 2026)
        division_filter: Filter contests to this division (e.g., "City of Petaluma")
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.civera_election_stats import (
        CiveraElectionStatsClient,
        CIVERA_INSTANCES,
        extract_civera_results_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Resolve county_slug and graphql_url from registry if not provided
    if not county_slug:
        # Try to infer from jurisdiction_id (e.g., "county-sonoma" → "sonoma")
        county_slug = jurisdiction.replace("county-", "").replace("city-", "")
    if not graphql_url:
        instance = CIVERA_INSTANCES.get(county_slug)
        if instance:
            graphql_url = instance["graphql_url"]
        else:
            raise ValueError(
                f"No graphql_url provided and county_slug={county_slug!r} not in CIVERA_INSTANCES. "
                f"Known: {list(CIVERA_INSTANCES.keys())}"
            )

    logger.info(
        f"[CIVERA] Starting fetch: jurisdiction={jurisdiction}, county={county_slug}, "
        f"years={from_year}-{to_year}, division={division_filter or 'all'}"
    )

    client = CiveraElectionStatsClient(
        jurisdiction_id=jurisdiction,
        graphql_url=graphql_url,
        county_slug=county_slug,
    )
    validation = client.validate()
    if not validation.is_valid:
        raise RuntimeError(f"Civera GraphQL validation failed ({county_slug}): {validation.errors}")

    if dry_run:
        events = client.list_elections(from_year=from_year, to_year=to_year)
        elapsed = time.time() - start_time
        return {
            "task": "civera_election_results",
            "jurisdiction": jurisdiction,
            "county_slug": county_slug,
            "elections_found": len(events),
            "elections_stored": 0,
            "contests_stored": 0,
            "candidates_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 4 * elapsed * 0.000463,
        }

    backend = PostgresBackend(database_url)
    counts = extract_civera_results_to_storage(
        client=client,
        storage=backend,
        jurisdiction_id=jurisdiction,
        county_slug=county_slug,
        from_year=from_year,
        to_year=to_year,
        division_filter=division_filter or None,
    )

    # Detect election cycle transitions and compute fingerprint
    fingerprint, cycle_transition = _detect_election_transition(
        backend, jurisdiction, "civera_election_stats",
        counts.get("election_ids", []), counts, logger,
        extra_hash_input=f"{from_year}-{to_year}",
    )

    backend.update_refresh_metadata(
        jurisdiction, "elections", "civera_election_stats",
        items_fetched=counts["elections"] + counts["contests"],
        items_stored=counts["elections"] + counts["contests"],
        status="completed",
        last_fetch_hash=fingerprint,
    )

    vector_result = None
    if auto_index and counts["elections"] > 0:
        logger.info(f"[CIVERA] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="elections",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "civera_election_results",
        "jurisdiction": jurisdiction,
        "county_slug": county_slug,
        "elections_stored": counts["elections"],
        "contests_stored": counts["contests"],
        "candidates_stored": counts["candidates"],
        "from_year": from_year,
        "to_year": to_year,
        "division_filter": division_filter or None,
        "dry_run": False,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if cycle_transition:
        result["cycle_transition"] = cycle_transition
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# CA Secretary of State Election Results Fetch (REST — api.sos.ca.gov)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=4096,
    timeout=600,  # 10 minutes (single election, statewide + district + measures)
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_ca_sos_election_results(
    jurisdiction: str = "state-california",
    county: str = "",
    districts_json: str = "",
    election_type: str = "general",
    dry_run: bool = False,
    auto_index: bool = False,
) -> dict:
    """Fetch election results from CA Secretary of State API.

    Queries api.sos.ca.gov for statewide races, district races, ballot measures,
    and county-level breakdowns.  No API key required.

    Note: the API only serves the current/most-recent election — no historical data.

    Args:
        jurisdiction: Target jurisdiction (default "state-california")
        county: County slug for breakdowns (e.g., "marin")
        districts_json: JSON dict mapping race_type to district numbers,
                        e.g., '{"us-rep": [2], "state-assembly": [12], "state-senate": [2]}'
        election_type: "general", "primary", or "special"
        dry_run: If True, fetch but don't store
        auto_index: If True, trigger vector indexing after successful storage
    """
    import json
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.ca_sos_results import (
        CASOSResultsClient,
        extract_ca_sos_results_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Parse districts
    districts = None
    if districts_json:
        districts = json.loads(districts_json)

    logger.info(
        f"[CA SOS] Starting fetch: jurisdiction={jurisdiction}, "
        f"county={county or 'none'}, election_type={election_type}"
    )

    # Create client and validate
    client = CASOSResultsClient(jurisdiction_id=jurisdiction)
    validation = client.validate()
    if not validation.is_valid:
        raise RuntimeError(f"CA SOS API validation failed: {validation.errors}")

    if dry_run:
        # Dry run: fetch status only
        status = client.get_reporting_status()
        elapsed = time.time() - start_time
        return {
            "task": "ca_sos_election_results",
            "jurisdiction": jurisdiction,
            "counties_reporting": len(status),
            "elections_stored": 0,
            "contests_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 4 * elapsed * 0.000463,
        }

    # Extract and store
    backend = PostgresBackend(database_url)
    counts = extract_ca_sos_results_to_storage(
        client=client,
        storage=backend,
        jurisdiction_id=jurisdiction,
        county=county or None,
        districts=districts,
        election_type=election_type,
    )

    # Detect election cycle transitions and compute fingerprint
    new_election_id = counts.get("election_id")
    election_ids = [new_election_id] if new_election_id else []
    fingerprint, cycle_transition = _detect_election_transition(
        backend, jurisdiction, "ca_sos_results",
        election_ids, counts, logger,
        count_fields=("elections", "contests", "candidates", "ballot_measures"),
    )

    # Update refresh metadata
    backend.update_refresh_metadata(
        jurisdiction, "elections", "ca_sos_results",
        items_fetched=counts["contests"],
        items_stored=counts["contests"],
        status="completed",
        last_fetch_hash=fingerprint,
    )

    # Auto-index vectors if requested and data was stored
    vector_result = None
    if auto_index and counts["elections"] > 0:
        logger.info(f"[CA SOS] Auto-indexing vectors for {jurisdiction}...")
        vector_result = index_vectors.remote(
            jurisdiction=jurisdiction,
            corpus="elections",
            reindex=False,
        )
        logger.info(f"  Vectors indexed: {vector_result.get('total_indexed', 0)}")

    elapsed = time.time() - start_time
    result = {
        "task": "ca_sos_election_results",
        "jurisdiction": jurisdiction,
        "election_id": new_election_id,
        "elections_stored": counts["elections"],
        "contests_stored": counts["contests"],
        "candidates_stored": counts["candidates"],
        "ballot_measures_stored": counts["ballot_measures"],
        "county": county or None,
        "election_type": election_type,
        "dry_run": False,
        "auto_index": auto_index,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }
    if cycle_transition:
        result["cycle_transition"] = cycle_transition
    if vector_result:
        result["vector_result"] = vector_result
    return result


# =============================================================================
# CA SOS Ballot Preview (Pre-Election Candidate PDFs)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=4096,
    timeout=600,  # 10 minutes (downloads + parses multiple PDFs)
    retries=modal.Retries(max_retries=2, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_ballot_preview(
    jurisdiction: str = "city-san-rafael",
    election_slug: str = "2026-primary",
    election_date: str = "2026-06-02",
    election_type: str = "primary",
    races_json: str = "",
    dry_run: bool = False,
) -> dict:
    """Fetch pre-election candidate data from CA SOS certified candidate PDFs.

    Downloads certified candidate list PDFs from the SOS CDN and extracts
    candidate name, party, ballot designation, contact info for each district.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        election_slug: CDN path segment (e.g., "2026-primary")
        election_date: Election date ISO string (e.g., "2026-06-02")
        election_type: "primary", "general", or "special"
        races_json: JSON dict mapping race slug to district list,
                    e.g., '{"congress": [2], "governor": null}'
        dry_run: If True, parse but don't store
    """
    import hashlib
    import json
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.ca_sos_ballot_preview import (
        CASOSBallotPreviewClient,
        extract_ca_sos_preview_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Parse race/district config (required — comes from extraction config)
    if not races_json:
        raise ValueError(
            f"races_json is required for {jurisdiction} — "
            f"configure ca_sos_ballot_preview.races in data/extraction/{jurisdiction}.json"
        )
    race_districts = json.loads(races_json)

    logger.info(
        f"[Ballot Preview] Starting: jurisdiction={jurisdiction}, "
        f"election={election_slug}, races={list(race_districts.keys())}"
    )

    client = CASOSBallotPreviewClient(
        election_slug=election_slug,
        election_date=election_date,
        election_type=election_type,
    )

    if dry_run:
        all_cands = client.get_all_candidates(race_districts)
        total = sum(
            len(cands) for dmap in all_cands.values() for cands in dmap.values()
        )
        elapsed = time.time() - start_time
        return {
            "task": "ballot_preview",
            "jurisdiction": jurisdiction,
            "races_checked": len(all_cands),
            "candidates_found": total,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 4 * elapsed * 0.000463,
        }

    backend = PostgresBackend(database_url)
    counts = extract_ca_sos_preview_to_storage(
        client=client,
        storage=backend,
        jurisdiction_id=jurisdiction,
        race_districts=race_districts,
    )

    fingerprint = hashlib.sha256(
        f"{counts['elections']}:{counts['contests']}:{counts['candidates']}".encode()
    ).hexdigest()[:16]

    backend.update_refresh_metadata(
        jurisdiction, "elections", "ca_sos_ballot_preview",
        items_fetched=counts["candidates"],
        items_stored=counts["candidates"],
        status="completed",
        last_fetch_hash=fingerprint,
    )

    elapsed = time.time() - start_time
    return {
        "task": "ballot_preview",
        "jurisdiction": jurisdiction,
        "election_slug": election_slug,
        "elections_stored": counts["elections"],
        "contests_stored": counts["contests"],
        "candidates_stored": counts["candidates"],
        "dry_run": False,
        "elapsed_seconds": elapsed,
        "cost_usd": 4 * elapsed * 0.000463,
    }


# =============================================================================
# Derive Elected Officials from Contest Winners
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=2048,
    timeout=300,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=5.0),
)
def derive_elected_officials(
    jurisdiction: str = "city-san-rafael",
    dry_run: bool = False,
) -> dict:
    """Derive elected officials from election contest winners.

    Scans election_contests for candidates with is_winner=True and creates
    elected_officials records, keeping only the most recent winner per seat.

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        dry_run: If True, log what would be derived but don't store
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos._internal.elections.derive import derive_officials_from_contests

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    if dry_run:
        elections = backend.get_elections(jurisdiction, include_past=True)
        total_contests = 0
        total_winners = 0
        for e in elections:
            contests = backend.get_election_contests(e["id"])
            total_contests += len(contests)
            for c in contests:
                raw = c.get("raw_data") or {}
                cands = raw.get("mapped_candidates", raw.get("candidates", []))
                total_winners += sum(1 for cd in cands if cd.get("is_winner"))

        elapsed = time.time() - start_time
        return {
            "task": "derive_elected_officials",
            "jurisdiction": jurisdiction,
            "elections_scanned": len(elections),
            "contests_scanned": total_contests,
            "winners_found": total_winners,
            "officials_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
        }

    officials_stored = derive_officials_from_contests(backend, jurisdiction)

    elapsed = time.time() - start_time
    logger.info(
        f"[DERIVE OFFICIALS] {jurisdiction}: {officials_stored} officials derived "
        f"in {elapsed:.1f}s"
    )

    return {
        "task": "derive_elected_officials",
        "jurisdiction": jurisdiction,
        "officials_stored": officials_stored,
        "dry_run": False,
        "elapsed_seconds": elapsed,
    }


# =============================================================================
# BoardDocs School Board Meeting Fetch
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
    ],
    memory=2048,
    timeout=3600,  # 1 hour (fetches meetings + agendas + stores chunks/agenda items)
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=30.0),
)
def fetch_boarddocs_meetings(
    app_path: str = "ca/rova",
    jurisdiction: str = "",
    committee_id: str = "",
    dry_run: bool = False,
) -> dict:
    """Fetch school board meetings and extract structured content from BoardDocs.

    Queries BoardDocs POST endpoints for meeting lists and full agendas.
    Stores meetings, chunks, and agenda items directly — no PDF download
    or LLM extraction needed since BoardDocs provides structured data.

    Args:
        app_path: BoardDocs site path (e.g., "ca/rova" for Ross Valley SD)
        jurisdiction: Target jurisdiction ID. If empty, inferred from app_path.
        committee_id: BoardDocs committee ID. If empty, auto-discovered from main page.
        dry_run: If True, fetch but don't store
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.boarddocs import (
        BoardDocsClient,
        extract_boarddocs_meetings_to_storage,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Resolve jurisdiction from app_path if not provided
    if not jurisdiction:
        jurisdiction = f"school-{app_path.replace('/', '-')}"

    logger.info(
        f"[BOARDDOCS] Starting fetch: app_path={app_path}, "
        f"jurisdiction={jurisdiction}, committee_id={committee_id or 'auto-discover'}"
    )

    # Create client
    client = BoardDocsClient(
        app_path=app_path,
        jurisdiction_id=jurisdiction,
        committee_id=committee_id or None,
    )

    # Validate
    validation = client.validate()
    if not validation.is_valid:
        raise RuntimeError(f"BoardDocs validation failed: {validation.errors}")

    meetings = client.get_meetings()
    logger.info(f"[BOARDDOCS] Fetched {len(meetings)} meetings")

    if dry_run:
        elapsed = time.time() - start_time
        return {
            "task": "boarddocs_meetings",
            "app_path": app_path,
            "jurisdiction": jurisdiction,
            "meetings_found": len(meetings),
            "meetings_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 2 * elapsed * 0.000463,
        }

    # Store meetings
    backend = PostgresBackend(database_url)
    count = extract_boarddocs_meetings_to_storage(
        client=client,
        storage=backend,
        jurisdiction_id=jurisdiction,
    )

    # Fetch agendas and extract chunks + agenda items directly.
    # BoardDocs provides structured data via API — no PDF download or LLM needed.
    agendas_fetched = 0
    total_chunks = 0
    total_agenda_items = 0
    for m in meetings:
        meeting_id = f"boarddocs-{m.unique}"
        items = client.get_agenda(m.unique)
        if not items:
            continue
        agendas_fetched += 1

        # Build chunks from agenda item body text
        chunks_data = []
        agenda_items_data = []
        chunk_idx = 0

        for item_idx, item in enumerate(items):
            text = (item.body_text or "").strip()
            title = f"{item.category}: {item.subject}".strip(": ")

            # Store as agenda item
            actionability = "informational"
            if item.item_type and item.item_type.lower() in ("action", "action item"):
                actionability = "actionable"
            elif item.item_type and item.item_type.lower() == "discussion":
                actionability = "actionable"

            agenda_items_data.append({
                "id": f"agenda:{jurisdiction}:{meeting_id}:{item_idx}",
                "meeting_id": meeting_id,
                "item_number": item.category,
                "title": title,
                "description": text[:2000] if text else None,
                "actionability": actionability,
                "comment_eligible": actionability == "actionable",
                "stance_eligible": False,
            })

            # Create chunk from body text (skip empty/procedural items)
            if text and len(text) > 20:
                chunks_data.append({
                    "id": f"chunk-{meeting_id}-{chunk_idx}",
                    "meeting_id": meeting_id,
                    "text": text,
                    "agenda_item": item.category,
                    "agenda_title": title,
                    "page_start": 0,
                    "page_end": 0,
                    "chunk_index": chunk_idx,
                    "total_chunks": 1,
                    "metadata": {
                        "source_type": "boarddocs_agenda",
                        "source_file": f"boarddocs://{app_path}/{m.unique}",
                    },
                })
                chunk_idx += 1

            # Also create chunks from attachments description if available
            for att in (item.attachments or []):
                att_text = att.get("name", "")
                if att_text:
                    chunks_data.append({
                        "id": f"chunk-{meeting_id}-{chunk_idx}",
                        "meeting_id": meeting_id,
                        "text": f"Attachment: {att_text}",
                        "agenda_item": item.category,
                        "agenda_title": title,
                        "page_start": 0,
                        "page_end": 0,
                        "chunk_index": chunk_idx,
                        "total_chunks": 1,
                        "metadata": {
                            "source_type": "boarddocs_attachment",
                            "source_file": att.get("url", ""),
                        },
                    })
                    chunk_idx += 1

        # Store chunks
        if chunks_data:
            stored = backend.store_chunks(jurisdiction, chunks_data, meeting_id=meeting_id)
            total_chunks += stored
            logger.info(f"  {meeting_id}: {stored} chunks from {len(items)} agenda items")

        # Store agenda items
        if agenda_items_data:
            stored = backend.store_agenda_items(meeting_id, agenda_items_data)
            total_agenda_items += stored

    logger.info(
        f"[BOARDDOCS] Content extraction: {agendas_fetched} agendas, "
        f"{total_chunks} chunks, {total_agenda_items} agenda items"
    )

    # Update refresh metadata
    import hashlib
    fingerprint = hashlib.sha256(
        f"{count}:{app_path}:{client.committee_id}".encode()
    ).hexdigest()[:16]

    backend.update_refresh_metadata(
        jurisdiction, "meetings", "boarddocs",
        items_fetched=len(meetings),
        items_stored=count,
        status="completed",
        last_fetch_hash=fingerprint,
    )

    elapsed = time.time() - start_time
    return {
        "task": "boarddocs_meetings",
        "app_path": app_path,
        "jurisdiction": jurisdiction,
        "committee_id": client.committee_id,
        "meetings_found": len(meetings),
        "meetings_stored": count,
        "agendas_fetched": agendas_fetched,
        "chunks_stored": total_chunks,
        "agenda_items_stored": total_agenda_items,
        "dry_run": False,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
    }


# =============================================================================
# Simbli School Board Meetings (Playwright-based)
# =============================================================================

# Playwright image for bot-protected sites (Simbli, CivicPlus, universal adapter).
# Browser-based extraction image (Playwright + Chromium).
# Separate from civic_image because Chromium adds ~300MB.
# Used by: Simbli school boards, Playwright+LLM custom sites.
browser_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "playwright>=1.40.0",
        "playwright-stealth>=1.0.0",
        "python-dotenv>=1.0.0",
        "openai>=1.0.0",
        "google-generativeai>=0.8.0",
    )
    .run_commands("playwright install --with-deps chromium")
    .env({
        "CIVICOS_EXTRACTION_DIR": "/config/extraction",
        "CIVICOS_CONFIG_DIR": "/config/extraction",
        "CIVICOS_JURISDICTIONS_DIR": "/config/jurisdictions",
    })
    .add_local_python_source("civicos", "civicos_config", "civicos_extraction", "civicos_services")
    .add_local_dir("data/extraction", remote_path="/config/extraction")
    .add_local_dir("data/jurisdictions", remote_path="/config/jurisdictions")
)


@app.function(
    image=browser_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,
    timeout=600,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_simbli_meetings(
    jurisdiction: str = "",
    board_url: str = "",
    days_past: int = 365,
    dry_run: bool = False,
) -> dict:
    """Fetch school board meetings from a Simbli/AgendaOnline portal.

    Uses Playwright browser automation to scrape meeting data from Simbli-hosted
    portals (simbli.eboardsolutions.com) and AgendaOnline portals (agendaonline.net).

    Args:
        jurisdiction: Target jurisdiction ID (e.g., "school-novato"). If provided,
            loads board_url from extraction config.
        board_url: Direct Simbli/AgendaOnline URL. Overrides config if provided.
        days_past: How many days back to fetch (default: 365)
        dry_run: If True, fetch but don't store
    """
    import logging
    import os
    import time
    from datetime import date

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos_extraction.clients.simbli import SimbliClient, extract_simbli_meetings_to_storage

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Resolve board_url from extraction config if not provided directly
    if not board_url and jurisdiction:
        from civicos_extraction.config import ExtractionConfig
        config = ExtractionConfig.from_jurisdiction(jurisdiction)
        board_url = config.metadata.get("board_url", config.base_url)

    if not board_url:
        raise ValueError("Either jurisdiction or board_url must be provided")

    if not jurisdiction:
        jurisdiction = "school-unknown"

    logger.info(f"[SIMBLI] Starting fetch: jurisdiction={jurisdiction}, board_url={board_url}")

    # Create client
    client = SimbliClient(
        board_url=board_url,
        jurisdiction_id=jurisdiction,
        headless=True,
    )

    from datetime import timedelta
    since_date = date.today().replace(year=date.today().year - 1) if days_past >= 365 else (
        date.today() - timedelta(days=days_past)
    )

    meetings = client.get_meetings(since=since_date)
    logger.info(f"[SIMBLI] Fetched {len(meetings)} meetings")

    if dry_run:
        elapsed = time.time() - start_time
        return {
            "task": "simbli_meetings",
            "jurisdiction": jurisdiction,
            "board_url": board_url,
            "meetings_found": len(meetings),
            "meetings_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 2 * elapsed * 0.000463,
        }

    # Store
    backend = PostgresBackend(database_url)
    count = extract_simbli_meetings_to_storage(
        client=client,
        storage=backend,
        jurisdiction_id=jurisdiction,
    )

    # Update refresh metadata
    backend.update_refresh_metadata(
        jurisdiction, "meetings", "simbli",
        items_fetched=len(meetings),
        items_stored=count,
        status="completed",
        fetch_window_days=days_past,
    )

    elapsed = time.time() - start_time
    return {
        "task": "simbli_meetings",
        "jurisdiction": jurisdiction,
        "board_url": board_url,
        "meetings_found": len(meetings),
        "meetings_stored": count,
        "dry_run": False,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
    }


@app.function(
    image=browser_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-openai"),
        modal.Secret.from_name("civic-google"),
    ],
    memory=4096,
    timeout=600,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0, initial_delay=10.0),
)
def fetch_playwright_llm_meetings(
    jurisdiction: str = "",
    days_past: int = 365,
    dry_run: bool = False,
) -> dict:
    """Fetch meetings from custom sites via Playwright rendering + LLM extraction.

    For municipalities without a standard platform (Granicus, CivicPlus, etc.),
    renders the page with Playwright and uses an LLM to extract meeting data
    from the visible text. Document links (PDFs) are annotated inline via DOM API.

    Args:
        jurisdiction: Target jurisdiction ID (e.g., "city-ross")
        days_past: How many days back to include (default: 365)
        dry_run: If True, fetch but don't store
    """
    import hashlib
    import logging
    import os
    import time
    from datetime import datetime

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    from civicos_extraction.clients.base import ExtractionConfig, Meeting
    from civicos_extraction.clients.playwright_llm import extract_meetings_from_page

    config = ExtractionConfig.from_jurisdiction(jurisdiction)
    page_url = config.metadata.get("meeting_page_url", config.base_url)

    logger.info(f"[PLAYWRIGHT_LLM] Starting: jurisdiction={jurisdiction}, url={page_url}")

    raw_meetings = extract_meetings_from_page(page_url, jurisdiction)
    logger.info(f"[PLAYWRIGHT_LLM] Extracted {len(raw_meetings)} raw meetings")

    # Convert to Meeting objects, dedup by ID
    seen_ids: set = set()
    meetings = []
    now = datetime.now()
    for m in raw_meetings:
        dt_str = m.get("date", "")
        try:
            dt = datetime.fromisoformat(dt_str)
        except (ValueError, TypeError):
            continue
        mid = f"playwright-llm-{jurisdiction}-{hashlib.sha256((m.get('title', '') + dt_str).encode()).hexdigest()[:12]}"
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        meetings.append(Meeting(
            id=mid,
            title=m.get("title", "Meeting"),
            meeting_datetime=dt,
            jurisdiction_id=jurisdiction,
            meeting_type=m.get("meeting_type"),
            status="completed" if dt < now else "scheduled",
            agenda_url=m.get("agenda_url"),
            minutes_url=m.get("minutes_url"),
            video_url=m.get("video_url"),
            source_platform="playwright_llm",
            source_url=page_url,
        ))

    logger.info(f"[PLAYWRIGHT_LLM] {len(meetings)} meetings after dedup")

    if dry_run:
        elapsed = time.time() - start_time
        return {
            "task": "playwright_llm_meetings",
            "jurisdiction": jurisdiction,
            "meetings_fetched": len(meetings),
            "meetings_stored": 0,
            "dry_run": True,
            "elapsed_seconds": elapsed,
            "cost_usd": 2 * elapsed * 0.000463,
        }

    # Store
    from civicos.storage.postgres_backend import PostgresBackend
    backend = PostgresBackend(database_url)
    meeting_dicts = [m.to_dict() if hasattr(m, "to_dict") else m.__dict__ for m in meetings]
    stored = int(backend.store_meetings(jurisdiction, meeting_dicts)) if meeting_dicts else 0

    # Update refresh metadata
    backend.update_refresh_metadata(
        jurisdiction, "meetings", "playwright_llm",
        items_fetched=len(meetings),
        items_stored=stored,
        status="completed",
        fetch_window_days=days_past,
    )

    elapsed = time.time() - start_time
    return {
        "task": "playwright_llm_meetings",
        "jurisdiction": jurisdiction,
        "meetings_fetched": len(meetings),
        "meetings_stored": stored,
        "dry_run": False,
        "elapsed_seconds": elapsed,
        "cost_usd": 2 * elapsed * 0.000463,
    }


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
    skipped = sum(1 for r in results if r.status in ("skipped", "no_sources"))
    no_sources = sum(1 for r in results if r.status == "no_sources")
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
    logger.info(f"[DECISIONS] Skipped {skipped} (already extracted or no sources), {no_sources} no sources available, {failed} failed")

    result = {
        "task": "decisions",
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results),
        "meetings_extracted": extracted,
        "meetings_skipped": skipped,
        "meetings_no_sources": no_sources,
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
# Batch Audio Download (parallel across jurisdictions)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-r2"),
        modal.Secret.from_name("civic-youtube-cookies"),
        modal.Secret.from_name("civic-youtube-proxy"),
    ],
    memory=4096,
    timeout=3600,  # 1 hour per jurisdiction
)
def download_audio_for_jurisdiction(
    jurisdiction: str,
    limit: int = 0,
    dry_run: bool = False,
) -> dict:
    """Download audio for a single jurisdiction. Designed to be spawned in parallel.

    Downloads meeting audio (YouTube or Granicus video_url), converts to
    opus@48kbps mono, and uploads to R2. Returns summary dict.

    Usage:
        # Spawned by batch_audio_download, or directly:
        modal run scripts/modal_ingest.py::download_audio_for_jurisdiction --jurisdiction city-fairfax
    """
    import logging
    import os
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    logger.info(f"[AUDIO] Starting audio download: jurisdiction={jurisdiction}, limit={limit}")

    # Decode YouTube cookies
    import base64
    import tempfile

    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64", "")
    cookies_path = ""
    if cookies_b64:
        cookies_bytes = base64.b64decode(cookies_b64)
        cookies_fd, cookies_path = tempfile.mkstemp(suffix=".txt", prefix="yt_cookies_")
        with os.fdopen(cookies_fd, "wb") as f:
            f.write(cookies_bytes)
        logger.info("[AUDIO] YouTube cookies loaded")

    proxy_url = os.environ.get("PROXY_URL", "")
    if proxy_url:
        proxy_display = proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
        logger.info(f"[AUDIO] Proxy configured: {proxy_display}")

    try:
        from civicos_extraction.cli.audio import run_audio_download

        results = run_audio_download(
            jurisdiction_id=jurisdiction,
            input_dir="data",
            output_dir="data/youtube_audio",
            cookies_path=cookies_path,
            checkpoint_dir="data/checkpoints",
            dry_run=dry_run,
            limit=limit,
            cloud=True,
            proxy=proxy_url or None,
            download_delay=5,
            max_workers=3,
        )

        elapsed = time.time() - start_time
        downloaded = sum(1 for r in (results or []) if r.status == "success")
        skipped = sum(1 for r in (results or []) if r.status == "skipped")
        failed = sum(1 for r in (results or []) if r.status == "error")

        logger.info(f"[AUDIO] Complete: {downloaded} downloaded, {skipped} skipped, {failed} failed in {elapsed:.0f}s")

        return {
            "jurisdiction": jurisdiction,
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
            "elapsed_seconds": round(elapsed, 1),
        }
    except Exception as e:
        logger.error(f"[AUDIO] Failed for {jurisdiction}: {e}")
        return {
            "jurisdiction": jurisdiction,
            "error": str(e),
            "elapsed_seconds": round(time.time() - start_time, 1),
        }
    finally:
        if cookies_path and os.path.exists(cookies_path):
            os.remove(cookies_path)


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-r2"),
    ],
    timeout=120,
)
def estimate_audio_costs(jurisdictions: str = "") -> dict:
    """Estimate costs for batch audio download before committing resources.

    Returns per-jurisdiction breakdown of:
    - Videos to download (total minus already in R2)
    - Source type (YouTube=proxy, Granicus=free)
    - Estimated proxy bandwidth cost
    - Estimated R2 storage
    - Estimated Modal compute time

    Cost model (conservative estimates):
    - Residential proxy: ~$10/GB (varies by provider)
    - YouTube raw download: ~250 MB/video through proxy
    - Granicus HLS audio-only: ~200 MB/video (free, no proxy)
    - Opus output: ~60 MB/3hr meeting -> R2 storage ~$0.015/GB/month
    - Modal compute: ~$0.10/hr per container
    - AssemblyAI transcription: ~$0.65/hr of audio (separate step)
    """
    import logging
    import os
    import psycopg2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Resolve jurisdiction list
    if jurisdictions == "auto" or not jurisdictions:
        cur.execute("""
            SELECT DISTINCT jurisdiction_id FROM meetings
            WHERE video_url IS NOT NULL
            GROUP BY jurisdiction_id HAVING COUNT(video_url) > 0
            ORDER BY jurisdiction_id
        """)
        jids = [r[0] for r in cur.fetchall()]
    else:
        jids = [j.strip() for j in jurisdictions.split(",") if j.strip()]

    # Also include jurisdictions with videos table entries (YouTube)
    cur.execute("SELECT DISTINCT jurisdiction_id FROM videos ORDER BY jurisdiction_id")
    video_jids = [r[0] for r in cur.fetchall()]
    for jid in video_jids:
        if jid not in jids:
            jids.append(jid)

    from civicos.storage import get_blob_storage
    blob = get_blob_storage()

    PROXY_COST_PER_GB = 10.0  # $/GB — residential proxy
    YOUTUBE_RAW_MB = 250  # avg raw download per YouTube video
    GRANICUS_RAW_MB = 200  # avg audio-only HLS download per Granicus video
    MODAL_COST_PER_HR = 0.10  # $/hr per container
    ASSEMBLYAI_PER_HR = 0.65  # $/hr of audio
    AVG_MEETING_HOURS = 2.5  # avg meeting duration

    estimates = {}
    total_proxy_gb = 0
    total_new_videos = 0

    for jid in jids:
        # Count videos with URLs
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE video_url LIKE '%%youtube%%') as youtube,
                COUNT(*) FILTER (WHERE video_url LIKE '%%granicus%%') as granicus,
                COUNT(*) FILTER (WHERE video_url NOT LIKE '%%youtube%%' AND video_url NOT LIKE '%%granicus%%' AND video_url IS NOT NULL) as other
            FROM meetings WHERE jurisdiction_id = %s AND video_url IS NOT NULL
        """, (jid,))
        row = cur.fetchone()
        yt_count, gran_count, other_count = row

        # Also check videos table for YouTube discoveries
        cur.execute("SELECT COUNT(*) FROM videos WHERE jurisdiction_id = %s", (jid,))
        videos_table = cur.fetchone()[0]
        # YouTube total = max of meetings.video_url YouTube count and videos table
        yt_total = max(yt_count, videos_table)

        # Count already in R2
        r2_keys = blob.list_keys(f"audio/{jid}/")
        existing = len(r2_keys)

        total_videos = yt_total + gran_count + other_count
        new_videos = max(0, total_videos - existing)

        # Estimate how many of the new ones are YouTube vs Granicus
        if total_videos > 0:
            yt_ratio = yt_total / total_videos
            gran_ratio = gran_count / total_videos
        else:
            yt_ratio, gran_ratio = 0, 0

        new_yt = int(new_videos * yt_ratio)
        new_gran = int(new_videos * gran_ratio)
        new_other = new_videos - new_yt - new_gran

        proxy_gb = (new_yt * YOUTUBE_RAW_MB) / 1024
        proxy_cost = proxy_gb * PROXY_COST_PER_GB
        total_proxy_gb += proxy_gb
        total_new_videos += new_videos

        # Estimated hours of audio for transcription cost
        audio_hours = new_videos * AVG_MEETING_HOURS
        transcription_cost = audio_hours * ASSEMBLYAI_PER_HR

        estimates[jid] = {
            "total_videos": total_videos,
            "existing_in_r2": existing,
            "new_to_download": new_videos,
            "youtube_videos": new_yt,
            "granicus_videos": new_gran + new_other,
            "proxy_bandwidth_gb": round(proxy_gb, 2),
            "proxy_cost_usd": round(proxy_cost, 2),
            "transcription_cost_usd": round(transcription_cost, 2),
            "audio_hours": round(audio_hours, 1),
        }

    conn.close()

    total_proxy_cost = total_proxy_gb * PROXY_COST_PER_GB
    total_audio_hours = total_new_videos * AVG_MEETING_HOURS
    total_transcription_cost = total_audio_hours * ASSEMBLYAI_PER_HR
    total_modal_cost = len(jids) * 1.0 * MODAL_COST_PER_HR  # ~1hr per jurisdiction

    return {
        "jurisdictions": estimates,
        "totals": {
            "new_videos": total_new_videos,
            "proxy_bandwidth_gb": round(total_proxy_gb, 2),
            "proxy_cost_usd": round(total_proxy_cost, 2),
            "modal_cost_usd": round(total_modal_cost, 2),
            "transcription_cost_usd": round(total_transcription_cost, 2),
            "total_estimated_cost_usd": round(total_proxy_cost + total_modal_cost + total_transcription_cost, 2),
        },
        "notes": [
            "Proxy cost applies only to YouTube videos (Granicus is free/direct)",
            "Transcription cost is for AssemblyAI (separate --transcripts step)",
            "Proxy cost varies by provider (~$5-15/GB for residential)",
            "Pass --approve-cost to proceed after reviewing estimate",
        ],
    }


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    timeout=14400,  # 4 hours — orchestrator waits for all per-jurisdiction jobs
)
def batch_audio_download(
    jurisdictions: str = "",
    limit: int = 0,
    dry_run: bool = False,
) -> dict:
    """Orchestrate parallel audio downloads across multiple jurisdictions.

    Each jurisdiction gets its own Modal container running in parallel.
    Containers download audio, convert to opus@48kbps mono, upload to R2.

    IMPORTANT: Run with --dry-run first to see cost estimate.
    Pass --approve-cost to skip the estimate step.

    Args:
        jurisdictions: Comma-separated jurisdiction IDs, or "auto" to detect
                      all jurisdictions with video URLs but missing audio.
        limit: Max videos per jurisdiction (0 = no limit)
        dry_run: If True, show what would be downloaded

    Usage:
        modal run scripts/modal_ingest.py --batch-audio --jurisdictions auto --dry-run
        modal run scripts/modal_ingest.py --batch-audio --jurisdictions auto --approve-cost
        modal run scripts/modal_ingest.py --batch-audio --jurisdictions auto --approve-cost --detach
    """
    import logging
    import os
    import psycopg2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    jids = []
    if jurisdictions == "auto" or not jurisdictions:
        # Auto-detect: jurisdictions with video_url in meetings
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT jurisdiction_id, COUNT(video_url) as video_count
            FROM meetings
            WHERE video_url IS NOT NULL
            GROUP BY jurisdiction_id
            HAVING COUNT(video_url) > 0
            ORDER BY jurisdiction_id
        """)
        jids = [r[0] for r in cur.fetchall()]
        conn.close()
        logger.info(f"[BATCH] Auto-detected {len(jids)} jurisdictions with video URLs: {jids}")
    else:
        jids = [j.strip() for j in jurisdictions.split(",") if j.strip()]
        logger.info(f"[BATCH] Explicit jurisdictions: {jids}")

    if not jids:
        logger.info("[BATCH] No jurisdictions to process")
        return {"jurisdictions": [], "message": "No jurisdictions found"}

    # Spawn parallel jobs — each runs in its own container
    logger.info(f"[BATCH] Spawning {len(jids)} parallel audio download jobs...")
    handles = []
    for jid in jids:
        handle = download_audio_for_jurisdiction.spawn(
            jurisdiction=jid,
            limit=limit,
            dry_run=dry_run,
        )
        handles.append((jid, handle))
        logger.info(f"  Spawned: {jid}")

    # Collect results (blocks until all complete)
    results = {}
    for jid, handle in handles:
        try:
            result = handle.get()
            results[jid] = result
            downloaded = result.get("downloaded", 0)
            skipped = result.get("skipped", 0)
            failed = result.get("failed", 0)
            elapsed = result.get("elapsed_seconds", 0)
            logger.info(f"  {jid}: {downloaded} new, {skipped} skipped, {failed} failed ({elapsed:.0f}s)")
        except Exception as e:
            results[jid] = {"error": str(e)}
            logger.error(f"  {jid}: FAILED — {e}")

    total_downloaded = sum(r.get("downloaded", 0) for r in results.values())
    total_failed = sum(r.get("failed", 0) for r in results.values())
    logger.info(f"\n[BATCH] Complete: {total_downloaded} new audio files, {total_failed} failures across {len(jids)} jurisdictions")

    return {"jurisdictions": list(results.keys()), "results": results}


# =============================================================================
# Batch Transcription (parallel across jurisdictions)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-r2"),
    ],
    timeout=14400,  # 4 hours — orchestrator waits for all per-jurisdiction jobs
)
def batch_transcribe(
    jurisdictions: str = "",
    since_date: str = "",
    cost_cap_usd: float = 50.0,
    dry_run: bool = False,
) -> dict:
    """Orchestrate parallel transcription across multiple jurisdictions.

    Spawns extract_transcripts for each jurisdiction that has audio in R2
    but missing transcripts. Respects the tiered transcription policy:
    only transcribes meetings since since_date (default 6 months).

    Args:
        jurisdictions: Comma-separated IDs, or "auto" to detect from R2 audio
        since_date: Only transcribe meetings on or after this date (YYYY-MM-DD)
        cost_cap_usd: Per-jurisdiction cost cap (default $50)
        dry_run: If True, show what would be transcribed
    """
    import logging
    import os
    import psycopg2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    # Resolve jurisdictions
    if jurisdictions == "auto" or not jurisdictions:
        from civicos.storage import get_blob_storage
        blob = get_blob_storage()

        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT jurisdiction_id FROM meetings ORDER BY jurisdiction_id")
        all_jids = [r[0] for r in cur.fetchall()]
        conn.close()

        # Only include jurisdictions that have audio in R2
        jids = []
        for jid in all_jids:
            keys = blob.list_keys(f"audio/{jid}/")
            if keys:
                jids.append(jid)
        logger.info(f"[BATCH-TXN] Auto-detected {len(jids)} jurisdictions with audio in R2: {jids}")
    else:
        jids = [j.strip() for j in jurisdictions.split(",") if j.strip()]
        logger.info(f"[BATCH-TXN] Explicit jurisdictions: {jids}")

    if not jids:
        logger.info("[BATCH-TXN] No jurisdictions to process")
        return {"jurisdictions": [], "message": "No jurisdictions with audio found"}

    # Spawn parallel transcription jobs
    logger.info(f"[BATCH-TXN] Spawning {len(jids)} parallel transcription jobs (cost cap ${cost_cap_usd:.0f}/jurisdiction)...")
    handles = []
    for jid in jids:
        handle = extract_transcripts.spawn(
            jurisdiction=jid,
            dry_run=dry_run,
            batch=True,
            auto_index=True,
            since_date=since_date,
            cost_cap_usd=cost_cap_usd,
        )
        handles.append((jid, handle))
        logger.info(f"  Spawned: {jid}")

    # Collect results
    results = {}
    total_cost = 0
    total_transcribed = 0
    for jid, handle in handles:
        try:
            result = handle.get()
            results[jid] = result
            cost = result.get("cost_usd", 0)
            transcribed = result.get("transcripts_extracted", 0)
            skipped = result.get("transcripts_skipped", 0)
            total_cost += cost
            total_transcribed += transcribed
            logger.info(f"  {jid}: {transcribed} transcribed, {skipped} skipped, ${cost:.2f}")
        except Exception as e:
            results[jid] = {"error": str(e)}
            logger.error(f"  {jid}: FAILED — {e}")

    logger.info(f"\n[BATCH-TXN] Complete: {total_transcribed} transcripts, ${total_cost:.2f} total across {len(jids)} jurisdictions")
    return {"jurisdictions": list(results.keys()), "results": results, "total_cost_usd": total_cost, "total_transcribed": total_transcribed}


# =============================================================================
# Consolidated Onboard (full pipeline per jurisdiction)
# =============================================================================

@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    timeout=14400,  # 4 hours for full pipeline
)
def onboard_jurisdiction(
    jurisdiction: str,
    since_date: str = "",
    cost_cap_usd: float = 50.0,
    days_past: int = 180,
    dry_run: bool = False,
) -> dict:
    """Run complete onboarding pipeline for a single jurisdiction.

    Chains all ingestion stages in dependency order with parallelism
    where possible. Each stage spawns in its own Modal container.

    Pipeline:
      Phase 1: meetings + issues (parallel)
      Phase 2: discover videos + extract chunks (parallel, need meetings)
      Phase 3: download audio (needs video discovery)
      Phase 4: transcribe audio (needs audio in R2)
      Phase 5: agenda items + decisions (parallel, need meetings)
      Phase 6: index all vectors (needs all data)

    Args:
        jurisdiction: Target jurisdiction ID (e.g., "city-sausalito")
        since_date: Only transcribe meetings since this date (YYYY-MM-DD)
        cost_cap_usd: Per-jurisdiction transcription cost cap
        days_past: Days to look back for meetings (default 180 = ~6 months)
        dry_run: If True, run fetches but skip audio/transcription
    """
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    start_time = time.time()

    results = {}
    errors = []

    def run_stage(name, handle):
        """Collect result from a spawned handle, logging errors."""
        try:
            result = handle.get()
            results[name] = result
            elapsed = result.get("elapsed_seconds", 0)
            logger.info(f"  [{jurisdiction}] {name}: OK ({elapsed:.0f}s)")
            return result
        except Exception as e:
            errors.append(name)
            results[name] = {"error": str(e)}
            logger.error(f"  [{jurisdiction}] {name}: FAILED — {e}")
            return None

    logger.info(f"[ONBOARD] Starting pipeline: {jurisdiction} (days_past={days_past}, dry_run={dry_run})")

    # Phase 1: Fetch base data (parallel)
    logger.info(f"  [{jurisdiction}] Phase 1: meetings + issues")
    meetings_h = fetch_meetings.spawn(
        jurisdiction=jurisdiction, days_past=days_past, auto_index=False, dry_run=dry_run,
    )
    issues_h = fetch_issues.spawn(
        jurisdiction=jurisdiction, auto_index=False, dry_run=dry_run,
    )
    meetings_result = run_stage("meetings", meetings_h)
    run_stage("issues", issues_h)

    # Phase 2: Discover videos + extract chunks (parallel, after meetings)
    logger.info(f"  [{jurisdiction}] Phase 2: videos + chunks")
    videos_h = discover_videos.spawn(
        jurisdiction=jurisdiction, days_past=days_past, days_ahead=30, dry_run=dry_run,
    )
    chunks_h = extract_chunks.spawn(
        jurisdiction=jurisdiction, auto_index=False, dry_run=dry_run,
    )
    run_stage("videos", videos_h)
    run_stage("chunks", chunks_h)

    # Phase 3: Download audio (after video discovery)
    if not dry_run:
        logger.info(f"  [{jurisdiction}] Phase 3: audio download")
        audio_h = download_audio_for_jurisdiction.spawn(
            jurisdiction=jurisdiction,
        )
        run_stage("audio", audio_h)
    else:
        logger.info(f"  [{jurisdiction}] Phase 3: audio download [SKIPPED — dry run]")
        results["audio"] = {"status": "skipped", "reason": "dry_run"}

    # Phase 4: Transcribe (after audio download)
    if not dry_run:
        logger.info(f"  [{jurisdiction}] Phase 4: transcription (since={since_date or 'default'}, cap=${cost_cap_usd:.0f})")
        transcripts_h = extract_transcripts.spawn(
            jurisdiction=jurisdiction,
            since_date=since_date,
            cost_cap_usd=cost_cap_usd,
            batch=True,
            auto_index=False,
        )
        run_stage("transcripts", transcripts_h)
    else:
        logger.info(f"  [{jurisdiction}] Phase 4: transcription [SKIPPED — dry run]")
        results["transcripts"] = {"status": "skipped", "reason": "dry_run"}

    # Phase 5: Agenda items + decisions (parallel, after meetings)
    logger.info(f"  [{jurisdiction}] Phase 5: agenda + decisions")
    agenda_h = extract_agenda_items.spawn(
        jurisdiction=jurisdiction, auto_index=False, dry_run=dry_run,
    )
    decisions_h = extract_decisions.spawn(
        jurisdiction=jurisdiction, auto_index=False, dry_run=dry_run,
    )
    run_stage("agenda", agenda_h)
    run_stage("decisions", decisions_h)

    # Phase 6: Index all vectors
    logger.info(f"  [{jurisdiction}] Phase 6: vector indexing")
    vectors_h = index_vectors.spawn(jurisdiction=jurisdiction, corpus="all")
    run_stage("vectors", vectors_h)

    elapsed = time.time() - start_time
    logger.info(f"[ONBOARD] {jurisdiction} complete in {elapsed:.0f}s ({len(errors)} errors)")

    return {
        "jurisdiction": jurisdiction,
        "stages": list(results.keys()),
        "results": results,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 1),
    }


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    timeout=21600,  # 6 hours for multi-jurisdiction onboarding
)
def batch_onboard(
    jurisdictions: str = "",
    since_date: str = "",
    cost_cap_usd: float = 50.0,
    days_past: int = 180,
    dry_run: bool = False,
) -> dict:
    """Orchestrate parallel onboarding across multiple jurisdictions.

    Spawns onboard_jurisdiction for each jurisdiction in parallel.
    Each gets its own set of Modal containers for the full pipeline.

    Args:
        jurisdictions: Comma-separated jurisdiction IDs
        since_date: Only transcribe meetings since this date (YYYY-MM-DD)
        cost_cap_usd: Per-jurisdiction transcription cost cap
        days_past: Days to look back for meetings
        dry_run: If True, skip audio/transcription stages
    """
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    jids = [j.strip() for j in jurisdictions.split(",") if j.strip()]
    if not jids:
        return {"jurisdictions": [], "message": "No jurisdictions specified"}

    logger.info(f"[BATCH-ONBOARD] Spawning {len(jids)} parallel onboard jobs...")
    handles = []
    for jid in jids:
        handle = onboard_jurisdiction.spawn(
            jurisdiction=jid,
            since_date=since_date,
            cost_cap_usd=cost_cap_usd,
            days_past=days_past,
            dry_run=dry_run,
        )
        handles.append((jid, handle))
        logger.info(f"  Spawned: {jid}")

    results = {}
    total_errors = 0
    for jid, handle in handles:
        try:
            result = handle.get()
            results[jid] = result
            n_errors = len(result.get("errors", []))
            total_errors += n_errors
            elapsed = result.get("elapsed_seconds", 0)
            logger.info(f"  {jid}: {len(result.get('stages', []))} stages, {n_errors} errors ({elapsed:.0f}s)")
        except Exception as e:
            results[jid] = {"error": str(e)}
            total_errors += 1
            logger.error(f"  {jid}: FAILED — {e}")

    logger.info(f"\n[BATCH-ONBOARD] Complete: {len(jids)} jurisdictions, {total_errors} total errors")
    return {"jurisdictions": jids, "results": results, "total_errors": total_errors}


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
    since_date: str = "",
    cost_cap_usd: float = 50.0,
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

    Transcription Policy (see docs/internal/transcription-policy.md):
        - Tier 1 (recent): Full transcription for meetings since since_date
        - Tier 2 (older): Covered by agenda chunks, no transcription needed
        - Default since_date: 6 months ago (rolling window)
        - cost_cap_usd prevents runaway spending per invocation

    Args:
        jurisdiction: Target jurisdiction (e.g., "city-san-rafael")
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be processed without extracting
        batch: If True, use AssemblyAI batch mode for parallel transcription
        auto_index: If True, trigger vector indexing after successful extraction
        meeting_type: Filter by meeting type (e.g., "planning_commission")
        since_days: Only process videos discovered within this many days (0 = no filter)
        since_date: Only transcribe meetings on or after this date (YYYY-MM-DD).
                    Default: 6 months ago. Implements Tier 1 transcription window.
        cost_cap_usd: Maximum AssemblyAI spend per invocation (default $50).
                      Stops processing when cap is reached.

    Cost: ~$0.65/hr audio (~$1.60 per 2.5-hour meeting)
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

    from datetime import datetime, timedelta

    meeting_type_filter = meeting_type if meeting_type else None
    since_days_filter = since_days if since_days > 0 else None

    # Convert since_date to since_days_filter so downstream functions actually filter
    if since_date and not since_days_filter:
        since_dt = datetime.strptime(since_date, "%Y-%m-%d")
        since_days_filter = (datetime.now() - since_dt).days
        logger.info(f"[TRANSCRIPTS] Transcription window: since {since_date} ({since_days_filter} days)")

    # Apply transcription policy: default to 6-month window if no filter specified
    if not since_date and not since_days_filter:
        since_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        since_days_filter = 180
        logger.info(f"[TRANSCRIPTS] No date filter specified — defaulting to Tier 1 window: since {since_date}")

    logger.info(f"[TRANSCRIPTS] Starting extraction: jurisdiction={jurisdiction}, limit={limit}, batch={batch}, meeting_type={meeting_type_filter}, since_days={since_days_filter}, cost_cap=${cost_cap_usd:.0f}")

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
            cloud=True,  # Store in R2
            meeting_type=meeting_type_filter,
            since_days=since_days_filter,
            proxy=proxy_url or None,
            download_delay=5,  # 5s stagger between download submissions (rate limit avoidance)
            max_workers=3,  # Parallel download+convert+upload
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

        # Apply cost cap: estimate meetings to process, limit if needed
        # Average meeting = 2.5 hrs * $0.65/hr = $1.625
        max_meetings_by_cost = int(cost_cap_usd / 1.625) if cost_cap_usd > 0 else 0
        effective_limit = limit if limit > 0 else max_meetings_by_cost
        if limit > 0:
            effective_limit = min(limit, max_meetings_by_cost) if max_meetings_by_cost > 0 else limit
        logger.info(f"[TRANSCRIPTS] Cost cap ${cost_cap_usd:.0f} -> max ~{max_meetings_by_cost} meetings (effective limit: {effective_limit})")

        transcribe_results = run_transcription(
            jurisdiction_id=jurisdiction,
            input_dir="data/youtube_audio",
            output_dir="data/testimony",
            checkpoint_dir="data/checkpoints",
            dry_run=dry_run,
            limit=effective_limit,
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
    # Schedule moved to GitHub Actions: .github/workflows/cron-low-velocity-refresh.yml
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

    def run_with_retry(func, stage_name: str, max_retries: int = 2, initial_delay: float = 30.0, **kwargs):
        """Run a Modal .local() function with retry logic for transient failures.

        Handles both exceptions AND soft failures (status="failed" in returned dict).
        """
        delay = initial_delay
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = func.local(**kwargs)
                # Check for soft failures (e.g., LegiScan returning status: ERROR)
                if isinstance(result, dict) and result.get("status") == "failed":
                    last_error = result.get("error", "unknown")
                    if attempt < max_retries:
                        logger.warning(f"  {stage_name} returned failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {last_error}")
                        time.sleep(delay)
                        delay *= 2
                        continue
                    else:
                        logger.error(f"  {stage_name} failed after {max_retries + 1} attempts: {last_error}")
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"  {stage_name} failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.exception(f"  {stage_name} failed after {max_retries + 1} attempts")

        return {"status": "failed", "error": str(last_error)}

    logger.info("Starting scheduled low-velocity refresh")
    start_time = time.time()

    import os
    from civicos.storage.postgres_backend import PostgresBackend
    from civicos.storage.pgvector_backend import PgVectorBackend
    from civicos._internal.legal.corpus.refresh import RefreshRunner
    from civicos._internal.legal.corpus.providers import LegislationCorpusProvider
    from civicos_extraction.config import get_active_jurisdictions

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    vectors = PgVectorBackend(database_url)
    runner = RefreshRunner(backend, vectors)

    jurisdictions = get_active_jurisdictions()
    logger.info(f"Found {len(jurisdictions)} configured jurisdictions: {list(jurisdictions.keys())}")

    results = {}
    pipeline_error = None

    try:
        # =========================================================================
        # Global operations (not per-jurisdiction)
        # =========================================================================

        # Legislation sync via RefreshRunner (weekly, auto-index vectors)
        # Provider handles: master list fetch → normalize → store_legislation()
        # RefreshRunner handles: scheduling, metadata, vector reindexing
        # Text population is a downstream step (fetch_legislation) after storage
        from civicos_extraction.clients.legiscan import LegiScanClient
        legiscan_client = LegiScanClient()  # Uses LEGISCAN_API_KEY from env

        # Build state list: always include federal, add configured states
        # Read state jurisdictions from registry or YAML configs
        _leg_targets = [("federal", "US Federal", "US")]
        import glob as _glob
        from pathlib import Path
        for _yp in sorted(_glob.glob(str(Path(__file__).parent.parent / "data" / "jurisdictions" / "state-*.yaml"))):
            import yaml as _lyaml
            with open(_yp) as _yf:
                _scfg = _lyaml.safe_load(_yf) or {}
            _sjid = _scfg.get("jurisdiction_id", "")
            _sinfo = _scfg.get("state_info", {})
            _sabbr = _sinfo.get("abbreviation", "")
            if _sjid and _sabbr:
                _leg_targets.insert(0, (f"state-{_sabbr}", _sabbr, _sabbr))

        for leg_jurisdiction, leg_label, state_code in _leg_targets:
            logger.info(f"Syncing {leg_label} legislation via RefreshRunner...")
            result_key = f"legislation_{leg_label.replace(' ', '_')}"
            try:
                leg_provider = LegislationCorpusProvider(
                    client=legiscan_client,
                    jurisdiction_id=leg_jurisdiction,
                    state_code=state_code,
                )
                leg_refresh = runner.refresh_corpus(leg_provider, reindex_vectors=True)
                leg_result = {
                    "task": "sync_legislation",
                    "jurisdiction": leg_jurisdiction,
                    "status": leg_refresh.status,
                    "bills_stored": leg_refresh.sections_added,
                    "vectors_indexed": leg_refresh.vectors_reindexed,
                }
                if leg_refresh.status == "error":
                    leg_result["error"] = leg_refresh.error

                # Downstream: populate full_text for bills missing it
                if leg_refresh.status == "updated" and leg_refresh.sections_added > 0:
                    logger.info(f"  Populating full_text for {leg_label} bills...")
                    text_result = run_with_retry(
                        fetch_legislation,
                        f"{leg_label} text population",
                        jurisdiction=leg_jurisdiction, dry_run=False, auto_index=False,
                    )
                    leg_result["text_result"] = text_result
                    text_updated = text_result.get("bills_with_text", 0)
                    logger.info(f"  {leg_label} text population: {text_updated} bills updated")

            except Exception as e:
                logger.exception(f"  {leg_label} legislation sync failed")
                leg_result = {"status": "failed", "error": str(e)}

            results[result_key] = leg_result
            if leg_result.get("status") not in ("failed", "error"):
                stored = leg_result.get("bills_stored", 0)
                indexed = leg_result.get("vectors_indexed", 0)
                logger.info(f"  {leg_label} Legislation: {stored} stored, {indexed} vectors indexed")

        # Executive Orders from Federal Register (incremental, auto-index vectors)
        logger.info("Fetching Executive Orders from Federal Register...")
        result = run_with_retry(
            fetch_executive_orders,
            "Executive Orders fetch",
            dry_run=False, incremental=True, auto_index=True,
        )
        results["executive_orders"] = result
        if result.get("status") != "failed":
            stored = result.get('orders_stored', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"  Executive Orders: {stored} new orders stored (of {result.get('orders_fetched', 0)} fetched), {indexed} vectors indexed")

        # Federal Rules from Federal Register (proposed rules, final rules, notices)
        logger.info("Fetching Federal Rules from Federal Register...")
        result = run_with_retry(
            fetch_federal_rules,
            "Federal Rules fetch",
            dry_run=False, incremental=True, auto_index=True,
        )
        results["federal_rules"] = result
        if result.get("status") != "failed":
            stored = result.get('rules_stored', 0)
            indexed = result.get('vector_result', {}).get('total_indexed', 0) if result.get('auto_index') else 0
            logger.info(f"  Federal Rules: {stored} new rules stored (of {result.get('rules_fetched', 0)} fetched), {indexed} vectors indexed")

        # Legislative Events (hearing dates parsed from existing legislation — no API calls)
        for _le_jid, _le_abbr, _ in _leg_targets:
            if _le_jid == "federal":
                continue  # Federal events handled separately
            logger.info(f"Extracting legislative events from {_le_abbr} legislation...")
            result = run_with_retry(
                extract_legislative_events,
                f"Legislative events extraction ({_le_abbr})",
                state=_le_abbr, dry_run=False,
            )
            results[f"legislative_events_{_le_abbr}"] = result
            if result.get("status") != "failed":
                stored = result.get('events_stored', 0)
                logger.info(f"  Legislative Events {_le_abbr}: {stored} events stored (of {result.get('events_parsed', 0)} parsed from {result.get('bills_read', 0)} bills)")

        # Federal programs from SAM.gov (full catalog refresh)
        logger.info("Fetching federal programs from SAM.gov...")
        result = run_with_retry(
            fetch_federal_programs,
            "Federal programs fetch",
            dry_run=False, force_refresh=True, auto_index=True,
        )
        results["federal_programs"] = result
        if result.get("status") != "failed":
            stored = result.get("programs_stored", 0)
            indexed = result.get("vector_result", {}).get("total_indexed", 0) if result.get("auto_index") else 0
            logger.info(f"  Federal programs: {stored} programs stored, {indexed} vectors indexed")

        # HUD allocations (CDBG, HOME, etc.) - already iterates all configured jurisdictions
        logger.info("Fetching HUD allocations for all configured jurisdictions...")
        result = run_with_retry(
            fetch_all_hud_allocations,
            "HUD allocations fetch",
            dry_run=False,
        )
        results["hud_allocations"] = result
        if result.get("status") != "failed":
            new_years = result.get("new_years_discovered", [])
            jcount = result.get("jurisdictions_processed", 0)
            stored = result.get("total_allocations_stored", 0)
            if new_years:
                logger.info(f"  HUD allocations: {stored} stored across {jcount} jurisdictions, NEW YEARS FOUND: {new_years}")
            else:
                logger.info(f"  HUD allocations: {stored} stored across {jcount} jurisdictions")

        # NOTE: Federal programs vector indexing is now handled by auto_index=True
        # in the fetch_federal_programs call above (avoids duplicate indexing).

        # Federal awards from USAspending.gov (iterates all configured jurisdictions)
        logger.info("Fetching federal awards from USAspending.gov...")
        result = run_with_retry(
            fetch_federal_awards,
            "Federal awards fetch",
            dry_run=False, auto_index=True,
        )
        results["federal_awards"] = result
        if result.get("status") != "failed":
            total = result.get("total_stored", 0)
            jcount = len(result.get("jurisdictions", {}))
            logger.info(f"  Federal awards: {total} stored across {jcount} jurisdictions")

        # Congressional votes (House + Senate roll calls for tracked representatives)
        # Weekly cron: process last 25 roll calls per chamber (typical week: 10-20).
        # For initial/manual fetch, use a higher max_roll_calls.
        logger.info("Fetching congressional votes...")
        result = run_with_retry(
            fetch_congressional_votes,
            "Congressional votes fetch",
            congress=119, session=1, max_roll_calls=25, dry_run=False,
        )
        results["congressional_votes"] = result
        if result.get("status") != "failed":
            total = result.get("total_stored", 0)
            house = result.get("house_roll_calls", 0)
            senate = result.get("senate_votes", 0)
            logger.info(f"  Congressional votes: {total} stored ({house} House roll calls, {senate} Senate votes)")

        # Congressional hearings (committee meetings from Congress.gov)
        # Weekly cron: look back 14 days (7-day overlap) + 60 days ahead.
        # For initial/manual fetch, use the default days_back=90.
        logger.info("Fetching congressional hearings...")
        result = run_with_retry(
            fetch_congressional_hearings,
            "Congressional hearings fetch",
            congress=119, days_back=14, days_ahead=60, dry_run=False,
        )
        results["congressional_hearings"] = result
        if result.get("status") != "failed":
            total = result.get("total_stored", 0)
            logger.info(f"  Congressional hearings: {total} stored")

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

    except Exception as e:
        logger.exception(f"Pipeline crashed with unhandled exception: {e}")
        pipeline_error = e
        results["_pipeline_crash"] = {"status": "failed", "error": str(e)}

    finally:
        elapsed = time.time() - start_time
        status = "crashed" if pipeline_error else "complete"
        logger.info(f"Low-velocity refresh {status} in {elapsed:.1f}s for {len(jurisdictions)} jurisdictions")

        # Send pipeline summary notification (always, even on crash)
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

    if pipeline_error:
        # Re-raise so Modal returns non-zero exit code to GH Actions.
        # Without this, crashed pipelines silently report "success".
        raise pipeline_error

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
        # civicos-platform (PLATFORM_DATABASE_URL) added to this function's
        # secrets list once the secret is provisioned on Modal. Until then,
        # usage rollup is skipped gracefully in the function body.
    ],
    memory=4096,
    timeout=10800,  # 3 hours (transcription can take time)
    # Schedule moved to GitHub Actions: .github/workflows/cron-high-velocity-refresh.yml
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

    import os
    from civicos.storage.postgres_backend import PostgresBackend
    from civicos.storage.pgvector_backend import PgVectorBackend
    from civicos._internal.legal.corpus.refresh import RefreshRunner
    from civicos._internal.legal.corpus.providers import MeetingCorpusProvider, IssueCorpusProvider
    from civicos_extraction.config import get_active_jurisdictions
    from civicos_extraction.clients.base import ExtractionConfig

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)
    vectors = PgVectorBackend(database_url)
    runner = RefreshRunner(backend, vectors)

    jurisdictions = get_active_jurisdictions()
    logger.info(f"Found {len(jurisdictions)} configured jurisdictions: {list(jurisdictions.keys())}")

    results = {}
    total_transcription_cost = 0.0

    for jid, config in jurisdictions.items():
        # Skip jurisdictions without high-velocity data sources
        source_type = config.get("source_type", "")
        if source_type in ("county", "financial"):
            logger.info(f"Skipping {jid} (source_type={source_type}, no high-velocity data)")
            continue

        logger.info(f"Processing jurisdiction: {jid}")
        results[jid] = {}

        # === STAGE 1: Meetings + Issues via RefreshRunner ===
        # Meetings: create source-specific client, wrap in provider, refresh
        meeting_provider = None
        logger.info(f"  [{jid}] Refreshing meetings via RefreshRunner...")
        try:
            ext_config = ExtractionConfig.from_jurisdiction(jid)
            src_type = ext_config.source_type

            if src_type == "proudcity":
                from civicos_extraction.clients.proudcity import ProudCityClient
                client = ProudCityClient(base_url=ext_config.base_url, jurisdiction_id=jid, archives=ext_config.archives or None)
            elif src_type == "granicus":
                from civicos_extraction.clients.granicus import GranicusSource
                client = GranicusSource(ext_config)
            elif src_type == "civicplus":
                from civicos_extraction.clients.civicplus import CivicPlusSource
                client = CivicPlusSource(ext_config)
            elif src_type == "universal":
                from civicos_extraction.clients.universal import UniversalSource
                client = UniversalSource(ext_config)
            elif src_type in ("legistar", "civicclerk", "escribe"):
                from civicos_extraction.clients.factory import create_source
                client = create_source(ext_config)
            else:
                from civicos_extraction.clients import SUPPORTED_MEETING_SOURCES
                logger.warning(f"  [{jid}] source_type '{src_type}' not supported in refresh "
                               f"(supported: {', '.join(sorted(SUPPORTED_MEETING_SOURCES))}) — skipping")
                results[jid]["meetings"] = {"skipped": True, "reason": f"source_type '{src_type}' not supported in refresh"}
                continue

            meeting_provider = MeetingCorpusProvider(
                client=client, jurisdiction_id=jid, source_name=src_type,
            )
            meeting_refresh = runner.refresh_corpus(meeting_provider, reindex_vectors=True)

            # Extract reactive signals from MeetingStoreResult for downstream stages
            sr = meeting_provider.last_store_result
            meetings_result = {
                "task": "meetings",
                "jurisdiction": jid,
                "status": meeting_refresh.status,
                "meetings_stored": meeting_refresh.sections_added,
                "vectors_indexed": meeting_refresh.vectors_reindexed,
                # Reactive signals (from MeetingStoreResult, None-safe)
                "new_meeting_ids": getattr(sr, "new_meeting_ids", []) if sr else [],
                "updated_meeting_ids": getattr(sr, "updated_meeting_ids", []) if sr else [],
                "minutes_appeared_ids": getattr(sr, "minutes_appeared", []) if sr else [],
                "video_appeared_ids": getattr(sr, "video_appeared", []) if sr else [],
                "agenda_appeared_ids": getattr(sr, "agenda_appeared", []) if sr else [],
                "has_new_material": getattr(sr, "has_new_material", False) if sr else False,
                "has_minutes_updates": getattr(sr, "has_minutes_updates", False) if sr else False,
                "has_video_updates": getattr(sr, "has_video_updates", False) if sr else False,
                "has_agenda_updates": getattr(sr, "has_agenda_updates", False) if sr else False,
            }
            if meeting_refresh.status == "error":
                meetings_result["error"] = meeting_refresh.error
        except Exception as e:
            logger.exception(f"  [{jid}] Meeting refresh failed")
            meetings_result = {"status": "failed", "error": str(e)}

        results[jid]["meetings"] = meetings_result
        if meetings_result.get("status") not in ("failed", "error"):
            stored = meetings_result.get("meetings_stored", 0)
            indexed = meetings_result.get("vectors_indexed", 0)
            logger.info(f"    Meetings: {stored} stored, {indexed} vectors indexed")

        # Issues: refresh via RefreshRunner (source from jurisdiction config)
        from civicos.jurisdiction_config import load_jurisdiction_config
        jur_config = load_jurisdiction_config(jid)
        issues_source = jur_config.data_sources.issues

        if not issues_source:
            logger.info(f"  [{jid}] No issues source configured — skipping")
            issues_result = {"status": "skipped", "reason": "no issues source configured"}
        else:
            logger.info(f"  [{jid}] Refreshing issues via RefreshRunner (source={issues_source})...")
            try:
                if issues_source == "seeclickfix":
                    from civicos_services.clients.seeclickfix_client import SeeClickFixClient
                    issues_client = SeeClickFixClient()
                else:
                    raise ValueError(f"Unsupported issues source '{issues_source}' for {jid}")

                issue_provider = IssueCorpusProvider(
                    client=issues_client, jurisdiction_id=jid, source_name=issues_source,
                )
                issue_refresh = runner.refresh_corpus(issue_provider, reindex_vectors=True)
                issues_result = {
                    "task": "issues",
                    "jurisdiction": jid,
                    "status": issue_refresh.status,
                    "issues_stored": issue_refresh.sections_added,
                    "vectors_indexed": issue_refresh.vectors_reindexed,
                }
                if issue_refresh.status == "error":
                    issues_result["error"] = issue_refresh.error
            except Exception as e:
                logger.exception(f"  [{jid}] Issue refresh failed")
                issues_result = {"status": "failed", "error": str(e)}

        results[jid]["issues"] = issues_result
        if issues_result.get("status") not in ("failed", "error", "skipped"):
            stored = issues_result.get("issues_stored", 0)
            indexed = issues_result.get("vectors_indexed", 0)
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

    # Usage log rollup: aggregate old logs into daily summaries
    try:
        import psycopg2
        platform_url = os.environ.get("PLATFORM_DATABASE_URL")
        if platform_url:
            conn = psycopg2.connect(platform_url)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO platform_usage_daily (key_id, endpoint, date, request_count, avg_response_ms, error_count)
                        SELECT key_id, endpoint, DATE(timestamp) as date,
                            COUNT(*) as request_count,
                            AVG(response_time_ms)::int as avg_response_ms,
                            COUNT(*) FILTER (WHERE status_code >= 400) as error_count
                        FROM platform_usage_logs
                        WHERE timestamp < NOW() - INTERVAL '90 days' AND key_id IS NOT NULL
                        GROUP BY key_id, endpoint, DATE(timestamp)
                        ON CONFLICT (key_id, endpoint, date) DO UPDATE SET
                            request_count = platform_usage_daily.request_count + EXCLUDED.request_count,
                            avg_response_ms = ((platform_usage_daily.avg_response_ms * platform_usage_daily.request_count
                                + EXCLUDED.avg_response_ms * EXCLUDED.request_count)
                                / (platform_usage_daily.request_count + EXCLUDED.request_count))::int,
                            error_count = platform_usage_daily.error_count + EXCLUDED.error_count
                    """)
                    aggregated = cur.rowcount
                    cur.execute("DELETE FROM platform_usage_logs WHERE timestamp < NOW() - INTERVAL '90 days'")
                    deleted = cur.rowcount
                conn.commit()
                logger.info(f"Usage rollup: aggregated={aggregated}, deleted={deleted}")
            finally:
                conn.close()
        else:
            logger.info("PLATFORM_DATABASE_URL not set, skipping usage rollup")
    except Exception as e:
        logger.warning(f"Usage rollup failed (non-fatal): {e}")

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
    # Schedule moved to GitHub Actions: .github/workflows/cron-meetings-poll.yml
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
# Calendar-Aware Election Refresh
# =============================================================================


# Cadence thresholds (days before election)
ELECTION_DAILY_THRESHOLD = 7    # ≤7 days: all sources fire every run
ELECTION_WEEKLY_THRESHOLD = 90  # 8–90 days: officials/ballot/deadlines on weekly schedule


def determine_refresh_cadence(
    election_sources: dict,
    daily_threshold: int = ELECTION_DAILY_THRESHOLD,
    weekly_threshold: int = ELECTION_WEEKLY_THRESHOLD,
) -> tuple:
    """Determine refresh cadence based on proximity to nearest configured election.

    Scans election_date fields across all source configs in a jurisdiction.

    Args:
        election_sources: The election_sources dict from jurisdiction config.
        daily_threshold: Days threshold for daily cadence (default 7).
        weekly_threshold: Days threshold for weekly cadence (default 90).

    Returns (cadence, days_until_nearest, nearest_date_str):
    - ("daily", N, "YYYY-MM-DD")  if nearest election is ≤daily_threshold days away
    - ("weekly", N, "YYYY-MM-DD") if nearest election is ≤weekly_threshold days away
    - ("monthly", N, "YYYY-MM-DD") if >weekly_threshold days away
    - ("monthly", None, None)      if no valid future election dates configured
    """
    from datetime import date as _date

    nearest_days = None
    nearest_date_str = None

    for _source_name, source_config in election_sources.items():
        if not isinstance(source_config, dict):
            continue
        election_date_str = source_config.get("election_date")
        if not election_date_str:
            continue
        try:
            election_date = _date.fromisoformat(election_date_str)
            days_until = (election_date - _date.today()).days
            if days_until >= 0 and (nearest_days is None or days_until < nearest_days):
                nearest_days = days_until
                nearest_date_str = election_date_str
        except ValueError:
            continue

    if nearest_days is not None and nearest_days <= daily_threshold:
        return ("daily", nearest_days, nearest_date_str)
    elif nearest_days is not None and nearest_days <= weekly_threshold:
        return ("weekly", nearest_days, nearest_date_str)
    else:
        return ("monthly", nearest_days, nearest_date_str)


def should_run_today(cadence: str) -> bool:
    """Determine if a jurisdiction should be processed today given its cadence.

    The GH Actions cron fires daily. This gates actual work:
    - daily: always run
    - weekly: run on Mondays and 1st of month
    - monthly: run on 1st of month only
    """
    from datetime import date as _date

    today = _date.today()
    if cadence == "daily":
        return True
    elif cadence == "weekly":
        return today.weekday() == 0 or today.day == 1  # Monday or 1st
    else:
        return today.day == 1


def check_election_coverage(backend, jurisdictions, logger):
    """Monthly election data completeness report.

    For each jurisdiction with election_sources, count:
    - elections (all, including past)
    - contests (across all elections)
    - deadlines (across all elections)
    - officials (all, including former)

    Returns structured report with per-jurisdiction counts and gap flags.
    """
    report = {
        "jurisdictions_checked": 0,
        "jurisdictions_with_gaps": 0,
        "details": {},
    }

    for jid, config in jurisdictions.items():
        election_sources = config.get("election_sources", {})
        if not election_sources:
            continue

        report["jurisdictions_checked"] += 1

        # Count elections (including past)
        elections = backend.get_elections(jid, include_past=True)
        election_count = len(elections)

        # Count contests and deadlines across all elections
        contest_count = 0
        deadline_count = 0
        for election in elections:
            eid = election.get("id")
            if eid:
                contest_count += len(backend.get_election_contests(eid))
                deadline_count += len(backend.get_election_deadlines(eid))

        # Count officials (all, not just current)
        officials = backend.get_elected_officials(jid, current_only=False)
        official_count = len(officials)

        # Flag gaps
        gaps = []
        if election_count == 0:
            gaps.append("elections")
        if contest_count == 0:
            gaps.append("contests")
        if deadline_count == 0:
            gaps.append("deadlines")
        if official_count == 0:
            gaps.append("officials")

        detail = {
            "elections": election_count,
            "contests": contest_count,
            "deadlines": deadline_count,
            "officials": official_count,
            "gaps": gaps,
        }
        report["details"][jid] = detail

        if gaps:
            report["jurisdictions_with_gaps"] += 1
            logger.warning(
                f"  [{jid}] COVERAGE GAP: missing {', '.join(gaps)} "
                f"(elections={election_count}, contests={contest_count}, "
                f"deadlines={deadline_count}, officials={official_count})"
            )
        else:
            logger.info(
                f"  [{jid}] Coverage OK: "
                f"elections={election_count}, contests={contest_count}, "
                f"deadlines={deadline_count}, officials={official_count}"
            )

    logger.info(
        f"Coverage report: {report['jurisdictions_checked']} checked, "
        f"{report['jurisdictions_with_gaps']} with gaps"
    )

    return report


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
    # Schedule moved to GitHub Actions: .github/workflows/cron-election-refresh.yml
)
def scheduled_election_refresh():
    """Calendar-aware election and officials data refresh.

    Runs daily via GH Actions at 3 AM UTC. Cadence per jurisdiction varies
    based on proximity to the nearest configured election_date:

    - daily  (≤7 days):  All sources fire — capture election-night results
    - weekly (8–90 days): Officials, ballot preview, deadlines only (Mondays + 1st)
    - monthly (>90 days): All sources fire (1st of month only)

    Data sources (dispatched per-jurisdiction via election_sources config):
    - civera_election_stats: Civera ElectionStats GraphQL (Marin, Sonoma, Yolo, etc.)
    - ca_sos_results: CA Secretary of State election results
    - ca_sos_ballot_preview: CA SOS certified candidate PDFs (pre-election, own date guard)

    Elected officials: Congress.gov (federal), LegiScan (state), curated (local)

    Iterates all configured jurisdictions from data/extraction/*.json.
    """
    import json as json_mod
    import logging
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting calendar-aware election refresh")
    start_time = time.time()

    import os
    from datetime import date as date_type, datetime as datetime_type

    from civicos.storage.postgres_backend import PostgresBackend
    from civicos._internal.elections.deadlines import generate_deadlines
    from civicos._internal.elections.derive import derive_officials_from_contests
    from civicos_extraction.config import get_active_jurisdictions

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")
    backend = PostgresBackend(database_url)

    jurisdictions = get_active_jurisdictions()
    logger.info(f"Found {len(jurisdictions)} configured jurisdictions: {list(jurisdictions.keys())}")

    results = {}

    for jid, config in jurisdictions.items():
        results[jid] = {}

        # Read election_sources from config
        election_sources = config.get("election_sources", {})

        from civicos_extraction.clients import SUPPORTED_ELECTION_SOURCES
        unsupported = set(election_sources.keys()) - SUPPORTED_ELECTION_SOURCES
        if unsupported:
            logger.info(
                f"  [{jid}] Election source(s) without fetch clients: {unsupported}. "
                f"Detected but not yet fetchable. Officials and deadlines still run."
            )

        # --- Calendar-aware cadence gating ---
        cadence, days_until, nearest_date = determine_refresh_cadence(election_sources)
        if nearest_date:
            logger.info(f"  [{jid}] Cadence: {cadence} ({days_until} days until {nearest_date})")
        else:
            logger.info(f"  [{jid}] Cadence: {cadence} (no election dates configured)")

        if not should_run_today(cadence):
            next_run = "Monday" if cadence == "weekly" else "1st of month"
            logger.info(f"  [{jid}] Skipping: {cadence} cadence, next run {next_run}")
            results[jid] = {"status": "skipped", "cadence": cadence, "days_until_election": days_until}
            continue

        # Per-source gating to minimize redundant writes:
        # - Civera: pure historical data — monthly only (1st of month)
        # - CA SOS Results: captures election-night data — daily near election, monthly otherwise
        # - Officials, ballot preview, deadlines: always run when jurisdiction runs
        is_first = date_type.today().day == 1
        run_civera = is_first
        run_sos_results = (cadence == "daily") or is_first
        if not run_civera:
            skipped = []
            if "civera_election_stats" in election_sources:
                skipped.append("civera (monthly only)")
            if not run_sos_results and "ca_sos_results" in election_sources:
                skipped.append("ca_sos_results (monthly only)")
            if skipped:
                logger.info(f"  [{jid}] Skipping: {', '.join(skipped)}")

        # --- Civera ElectionStats (generalized: Marin, Sonoma, Yolo, etc.) ---
        if run_civera and "civera_election_stats" in election_sources:
            provider_config = election_sources["civera_election_stats"]
            if provider_config is True:
                provider_config = {}
            try:
                county_slug = provider_config.get("county_slug", "")
                graphql_url = provider_config.get("graphql_url", "")
                from_year = provider_config.get("from_year", 2010)
                division_filter = provider_config.get("division_filter", "")
                logger.info(f"  [{jid}] Fetching elections (Civera, county={county_slug}, from_year={from_year}, division={division_filter or 'all'})...")
                result = fetch_civera_election_results.local(
                    jurisdiction=jid,
                    county_slug=county_slug,
                    graphql_url=graphql_url,
                    from_year=from_year,
                    division_filter=division_filter,
                    dry_run=False,
                    auto_index=True,
                )
                results[jid]["civera_election_stats"] = result
                logger.info(f"    Civera ({county_slug}): {result.get('elections_stored', 0)} elections stored")
            except Exception as e:
                logger.exception(f"  [{jid}] Civera fetch failed")
                results[jid]["civera_election_stats"] = {"status": "failed", "error": str(e)}

        # --- CA Secretary of State Results (election-night data near election) ---
        if run_sos_results and "ca_sos_results" in election_sources:
            provider_config = election_sources["ca_sos_results"]
            if provider_config is True:
                provider_config = {}
            try:
                county = provider_config.get("county", "")
                districts = provider_config.get("districts", {})
                districts_json = json_mod.dumps(districts) if districts else ""
                logger.info(f"  [{jid}] Fetching elections (CA SOS, county={county or 'statewide'})...")
                result = fetch_ca_sos_election_results.local(
                    jurisdiction=jid,
                    county=county,
                    districts_json=districts_json,
                    dry_run=False,
                    auto_index=True,
                )
                results[jid]["ca_sos_results"] = result
                logger.info(f"    CA SOS: {result.get('contests_stored', 0)} contests stored")
            except Exception as e:
                logger.exception(f"  [{jid}] CA SOS fetch failed")
                results[jid]["ca_sos_results"] = {"status": "failed", "error": str(e)}

        # --- CA SOS Ballot Preview (pre-election candidate PDFs) ---
        # Only fetch within 90 days before election_date; skip if election has passed.
        if "ca_sos_ballot_preview" in election_sources:
            provider_config = election_sources["ca_sos_ballot_preview"]
            if provider_config is True:
                provider_config = {}
            election_slug = provider_config.get("election_slug", "")
            election_date_str = provider_config.get("election_date", "")
            window_days = provider_config.get("window_days", 90)
            # Date-based guard: only fetch in the pre-election window
            skip_reason = None
            if not election_date_str:
                skip_reason = "no election_date configured"
            else:
                try:
                    election_date_parsed = date_type.fromisoformat(election_date_str)
                    days_until = (election_date_parsed - date_type.today()).days
                    if days_until < 0:
                        skip_reason = f"election {election_slug} already passed ({election_date_str}, {-days_until} days ago)"
                    elif days_until > window_days:
                        skip_reason = f"election {election_slug} is {days_until} days away (>{window_days}), too early for ballot preview"
                except ValueError:
                    skip_reason = f"invalid election_date format: {election_date_str!r}"
            if skip_reason:
                logger.info(f"  [{jid}] Skipping ballot preview: {skip_reason}")
                results[jid]["ca_sos_ballot_preview"] = {"status": "skipped", "reason": skip_reason}
            else:
                try:
                    election_type = provider_config.get("election_type", "primary")
                    races = provider_config.get("races", {})
                    races_json = json_mod.dumps(races) if races else ""
                    logger.info(f"  [{jid}] Fetching ballot preview (CA SOS, election={election_slug}, {days_until} days until election)...")
                    result = fetch_ballot_preview.local(
                        jurisdiction=jid,
                        election_slug=election_slug,
                        election_date=election_date_str,
                        election_type=election_type,
                        races_json=races_json,
                        dry_run=False,
                        auto_index=True,
                    )
                    results[jid]["ca_sos_ballot_preview"] = result
                    logger.info(f"    Ballot preview: {result.get('candidates_stored', 0)} candidates stored")
                except Exception as e:
                    logger.exception(f"  [{jid}] Ballot preview fetch failed")
                    results[jid]["ca_sos_ballot_preview"] = {"status": "failed", "error": str(e)}

        # --- Elected Officials (always runs) ---
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

        # --- Generate Election Deadlines (for elections missing them) ---
        try:
            state_code = config.get("state", "CA")
            elections = backend.get_elections(jid, include_past=False)
            deadlines_generated = 0

            for e in elections:
                election_id = e["id"]
                election_date = e.get("election_date")
                if not election_date:
                    continue

                # Skip if deadlines already exist
                existing = backend.get_election_deadlines(election_id)
                if existing:
                    continue

                # Parse date
                if isinstance(election_date, str):
                    election_date = date_type.fromisoformat(election_date)
                elif isinstance(election_date, datetime_type):
                    election_date = election_date.date()

                deadlines = generate_deadlines(election_date, state_code=state_code)
                deadline_dicts = [
                    {
                        "deadline_type": d.deadline_type,
                        "deadline_date": d.deadline_date.isoformat(),
                        "description": d.description,
                    }
                    for d in deadlines
                ]

                count = backend.store_election_deadlines(election_id, deadline_dicts)
                deadlines_generated += count

            if deadlines_generated > 0:
                logger.info(f"    Deadlines: {deadlines_generated} generated for {len(elections)} upcoming elections")
            results[jid]["deadlines"] = {"generated": deadlines_generated, "elections_checked": len(elections)}
        except Exception as e:
            logger.exception(f"  [{jid}] Deadline generation failed")
            results[jid]["deadlines"] = {"status": "failed", "error": str(e)}

        # --- Derive Officials from Contest Winners (always runs) ---
        try:
            logger.info(f"  [{jid}] Deriving officials from contest winners...")
            derived_count = derive_officials_from_contests(backend, jid)
            results[jid]["officials_derived"] = {"count": derived_count}
            if derived_count > 0:
                logger.info(f"    Officials derived: {derived_count} from contest winners")
        except Exception as e:
            logger.exception(f"  [{jid}] Officials derivation failed")
            results[jid]["officials_derived"] = {"status": "failed", "error": str(e)}

    elapsed = time.time() - start_time
    processed = sum(1 for r in results.values() if r.get("status") != "skipped")
    skipped = sum(1 for r in results.values() if r.get("status") == "skipped")
    logger.info(f"Election refresh complete in {elapsed:.1f}s — {processed} processed, {skipped} skipped (of {len(jurisdictions)} total)")

    # --- Monthly coverage report (1st of month only) ---
    coverage_report = None
    if date_type.today().day == 1:
        logger.info("Running monthly election coverage report...")
        try:
            coverage_report = check_election_coverage(backend, jurisdictions, logger)
        except Exception as e:
            logger.exception("Coverage report failed")
            coverage_report = {"status": "failed", "error": str(e)}

    result = {
        "schedule": "election_calendar_aware",
        "jurisdictions_total": len(jurisdictions),
        "jurisdictions_processed": processed,
        "jurisdictions_skipped": skipped,
        "results": results,
        "elapsed_seconds": elapsed,
    }
    if coverage_report is not None:
        result["coverage_report"] = coverage_report
    return result


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

def _print_onboard_results(result: dict):
    """Print formatted onboard results summary."""
    print("\n" + "=" * 60)
    print("  ONBOARD RESULTS")
    print("=" * 60)

    for jid in result.get("jurisdictions", []):
        r = result["results"].get(jid, {})
        if "error" in r and isinstance(r.get("error"), str):
            print(f"\n  {jid}: FAILED — {r['error']}")
            continue

        elapsed = r.get("elapsed_seconds", 0)
        errors = r.get("errors", [])
        print(f"\n  {jid} ({elapsed:.0f}s)")

        stages = r.get("results", {})
        for stage, stage_result in stages.items():
            if isinstance(stage_result, dict) and "error" in stage_result:
                print(f"    x {stage}: {stage_result['error'][:100]}")
            elif isinstance(stage_result, dict) and stage_result.get("status") == "skipped":
                print(f"    - {stage}: skipped ({stage_result.get('reason', '')})")
            elif stage == "meetings":
                fetched = stage_result.get("meetings_fetched", 0) if isinstance(stage_result, dict) else 0
                stored = stage_result.get("meetings_stored", 0) if isinstance(stage_result, dict) else 0
                print(f"    + meetings: {fetched} fetched, {stored} stored")
            elif stage == "issues":
                fetched = stage_result.get("issues_fetched", 0) if isinstance(stage_result, dict) else 0
                stored = stage_result.get("issues_stored", 0) if isinstance(stage_result, dict) else 0
                print(f"    + issues: {fetched} fetched, {stored} stored")
            elif stage == "videos":
                discovered = stage_result.get("videos_discovered", 0) if isinstance(stage_result, dict) else 0
                stored = stage_result.get("videos_stored", 0) if isinstance(stage_result, dict) else 0
                print(f"    + videos: {discovered} discovered, {stored} stored")
            elif stage == "audio":
                downloaded = stage_result.get("downloaded", 0) if isinstance(stage_result, dict) else 0
                skipped = stage_result.get("skipped", 0) if isinstance(stage_result, dict) else 0
                print(f"    + audio: {downloaded} downloaded, {skipped} skipped")
            elif stage == "transcripts":
                extracted = stage_result.get("transcripts_extracted", 0) if isinstance(stage_result, dict) else 0
                cost = stage_result.get("transcription_cost_usd", 0) if isinstance(stage_result, dict) else 0
                print(f"    + transcripts: {extracted} extracted (${cost:.2f})")
            elif stage == "chunks":
                total = stage_result.get("chunks_extracted", 0) if isinstance(stage_result, dict) else 0
                print(f"    + chunks: {total} extracted")
            elif stage == "agenda":
                items = stage_result.get("items_extracted", 0) if isinstance(stage_result, dict) else 0
                print(f"    + agenda: {items} items")
            elif stage == "decisions":
                total = stage_result.get("decisions_extracted", 0) if isinstance(stage_result, dict) else 0
                print(f"    + decisions: {total} extracted")
            elif stage == "vectors":
                indexed = stage_result.get("total_indexed", 0) if isinstance(stage_result, dict) else 0
                print(f"    + vectors: {indexed} indexed")
            else:
                print(f"    + {stage}: OK")

        if errors:
            print(f"    Errors: {', '.join(errors)}")

    total_errors = result.get("total_errors", 0)
    print()
    print("=" * 60)
    if total_errors > 0:
        print(f"  {total_errors} stage(s) had errors across {len(result.get('jurisdictions', []))} jurisdictions")
    else:
        print(f"  All stages complete for {len(result.get('jurisdictions', []))} jurisdiction(s)")
    print("=" * 60)


@app.local_entrypoint()
def main(
    all: bool = False,
    batch_audio: bool = False,
    batch_transcribe_flag: bool = False,
    onboard: bool = False,
    approve_cost: bool = False,
    jurisdictions: str = "",
    onboard_days_past: int = 180,
    municipal: bool = False,
    legislation: bool = False,
    executive_orders: bool = False,
    federal_programs: bool = False,
    federal_rules: bool = False,
    federal_awards: bool = False,
    legislative_events: bool = False,
    meetings: bool = False,
    issues: bool = False,
    elections: bool = False,
    ballot_preview: bool = False,
    elected_officials: bool = False,
    videos: bool = False,
    transcripts: bool = False,
    chunks: bool = False,
    agenda: bool = False,
    decisions: bool = False,
    vectors: bool = False,
    score_rules: bool = False,
    refresh: bool = False,
    force: bool = False,
    jurisdiction: str = "city-san-rafael",
    legislation_jurisdiction: str = "state-CA",
    legislation_limit: int | None = None,
    transcripts_limit: int = 0,
    transcripts_since: str = "",
    transcripts_cost_cap: float = 50.0,
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
        # Onboard a new jurisdiction (full pipeline: meetings -> audio -> transcripts -> decisions -> vectors)
        modal run scripts/modal_ingest.py --onboard --jurisdiction city-sausalito --dry-run
        modal run scripts/modal_ingest.py --onboard --jurisdiction city-sausalito --approve-cost
        modal run scripts/modal_ingest.py --onboard --jurisdictions "city-sausalito,city-tiburon" --approve-cost
        modal run scripts/modal_ingest.py --onboard --jurisdictions "city-sausalito" --approve-cost --onboard-days-past 365

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

        # Incremental refresh (checks fingerprint, diffs, upserts deltas only)
        modal run scripts/modal_ingest.py --refresh --jurisdiction city-san-rafael
        modal run scripts/modal_ingest.py --refresh --force  # Skip interval/fingerprint check

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
    if batch_audio:
        jids_arg = jurisdictions or "auto"

        # Step 1: Always show cost estimate first
        print("\nEstimating costs...")
        estimate = estimate_audio_costs.remote(jurisdictions=jids_arg)

        print("\n" + "=" * 60)
        print("  BATCH AUDIO DOWNLOAD — COST ESTIMATE")
        print("=" * 60)
        print(f"{'Jurisdiction':<25} {'New':>4} {'YT':>4} {'Gran':>4} {'Proxy$':>8} {'Transcr$':>9}")
        print("-" * 60)
        for jid, e in estimate["jurisdictions"].items():
            print(
                f"  {jid:<23} {e['new_to_download']:>4} {e['youtube_videos']:>4} "
                f"{e['granicus_videos']:>4} ${e['proxy_cost_usd']:>6.2f} "
                f"${e['transcription_cost_usd']:>7.2f}"
            )
        t = estimate["totals"]
        print("-" * 60)
        print(f"  {'TOTAL':<23} {t['new_videos']:>4}")
        print()
        print(f"  Proxy bandwidth:    {t['proxy_bandwidth_gb']:.1f} GB  →  ${t['proxy_cost_usd']:.2f}")
        print(f"  Modal compute:                    →  ${t['modal_cost_usd']:.2f}")
        print(f"  Transcription (if run later):      →  ${t['transcription_cost_usd']:.2f}")
        print(f"  ─────────────────────────────────────────")
        print(f"  Audio download total:              →  ${t['proxy_cost_usd'] + t['modal_cost_usd']:.2f}")
        print(f"  Full pipeline (incl. transcribe):  →  ${t['total_estimated_cost_usd']:.2f}")
        print()
        for note in estimate.get("notes", []):
            print(f"  * {note}")
        print()

        # Step 2: Gate on --approve-cost (or --dry-run just shows estimate)
        if dry_run:
            print("  [DRY RUN] No downloads started.")
            return

        if not approve_cost:
            print("  ⛔ Pass --approve-cost to proceed with download.")
            print("  Example: modal run scripts/modal_ingest.py --batch-audio --approve-cost")
            return

        # Step 3: Proceed with download
        print(f"  ✓ Cost approved. Launching downloads...")
        result = batch_audio_download.remote(
            jurisdictions=jids_arg,
            limit=transcripts_limit,
            dry_run=False,
        )
        print("\n" + "=" * 60)
        print("Batch Audio Download Results")
        print("=" * 60)
        for jid in result.get("jurisdictions", []):
            r = result["results"].get(jid, {})
            if "error" in r:
                print(f"  {jid}: FAILED — {r['error']}")
            else:
                print(f"  {jid}: {r.get('downloaded', 0)} new, {r.get('skipped', 0)} skipped, {r.get('failed', 0)} failed ({r.get('elapsed_seconds', 0):.0f}s)")
        return

    if batch_transcribe_flag:
        jids_arg = jurisdictions or "auto"
        since = transcripts_since or "2026-01-01"
        cap = transcripts_cost_cap

        # Show estimate first
        estimate = estimate_audio_costs.remote(jurisdictions=jids_arg)
        total_new = sum(e["new_to_download"] for e in estimate["jurisdictions"].values())
        total_txn = estimate["totals"]["transcription_cost_usd"]

        print("\n" + "=" * 60)
        print("  BATCH TRANSCRIPTION — COST ESTIMATE")
        print("=" * 60)
        print(f"  Since:     {since}")
        print(f"  Per-jurisdiction cap: ${cap:.0f}")
        print(f"  Estimated total transcription: ${total_txn:.0f}")
        print(f"  (actual cost depends on how many meetings have audio in R2)")
        print()

        if not approve_cost:
            print("  Pass --approve-cost to proceed.")
            print(f"  Example: modal run scripts/modal_ingest.py --batch-transcribe-flag --approve-cost --transcripts-since {since}")
            return

        print(f"  Cost approved. Launching transcription across jurisdictions...")
        result = batch_transcribe.remote(
            jurisdictions=jids_arg,
            since_date=since,
            cost_cap_usd=cap,
            dry_run=dry_run,
        )
        print("\n" + "=" * 60)
        print("Batch Transcription Results")
        print("=" * 60)
        for jid in result.get("jurisdictions", []):
            r = result["results"].get(jid, {})
            if "error" in r:
                print(f"  {jid}: FAILED — {r['error']}")
            else:
                txn = r.get("transcripts_extracted", 0)
                cost = r.get("cost_usd", 0)
                print(f"  {jid}: {txn} transcribed, ${cost:.2f}")
        print(f"\n  TOTAL: {result.get('total_transcribed', 0)} transcripts, ${result.get('total_cost_usd', 0):.2f}")
        return

    if onboard:
        # Resolve jurisdiction list
        if jurisdictions:
            jids = [j.strip() for j in jurisdictions.split(",") if j.strip()]
        else:
            jids = [jurisdiction]

        since = transcripts_since or ""
        cap = transcripts_cost_cap

        # Step 1: Show cost estimate
        print("\nEstimating costs for onboarding...")
        estimate = estimate_audio_costs.remote(jurisdictions=",".join(jids))

        print("\n" + "=" * 60)
        print("  ONBOARD — COST ESTIMATE")
        print("=" * 60)
        print(f"  Jurisdictions: {', '.join(jids)}")
        print(f"  Lookback:      {onboard_days_past} days (~{onboard_days_past // 30} months)")
        print(f"  Transcription: since {since or 'default (6 months)'}, cap ${cap:.0f}/jurisdiction")
        print()
        print(f"  {'Jurisdiction':<25} {'New':>4} {'YT':>4} {'Gran':>4} {'Proxy$':>8} {'Transcr$':>9}")
        print("  " + "-" * 58)
        for jid in jids:
            e = estimate["jurisdictions"].get(jid, {})
            if e:
                print(
                    f"  {jid:<25} {e.get('new_to_download', 0):>4} {e.get('youtube_videos', 0):>4} "
                    f"{e.get('granicus_videos', 0):>4} ${e.get('proxy_cost_usd', 0):>6.2f} "
                    f"${e.get('transcription_cost_usd', 0):>7.2f}"
                )
            else:
                print(f"  {jid:<25}  (no video data yet — meetings will be fetched first)")
        t = estimate["totals"]
        print("  " + "-" * 58)
        print(f"  Proxy bandwidth:    {t['proxy_bandwidth_gb']:.1f} GB  →  ${t['proxy_cost_usd']:.2f}")
        print(f"  Transcription:                     →  ${t['transcription_cost_usd']:.2f}")
        print(f"  Modal compute:                     →  ${t['modal_cost_usd']:.2f}")
        print(f"  ─────────────────────────────────────────")
        print(f"  Estimated total:                   →  ${t['total_estimated_cost_usd']:.2f}")
        print()
        print("  Pipeline: meetings → issues → videos → audio → transcripts")
        print("            → chunks → agenda → decisions → vectors")
        print()
        for note in estimate.get("notes", []):
            print(f"  * {note}")
        print()

        if dry_run:
            print("  [DRY RUN] Launching pipeline without audio/transcription...")
            print()
            result = batch_onboard.remote(
                jurisdictions=",".join(jids),
                since_date=since,
                cost_cap_usd=cap,
                days_past=onboard_days_past,
                dry_run=True,
            )
            _print_onboard_results(result)
            return

        if not approve_cost:
            print("  Pass --approve-cost to proceed with full pipeline.")
            print(f"  Example: modal run scripts/modal_ingest.py --onboard --jurisdiction {jids[0]} --approve-cost")
            if len(jids) > 1:
                print(f"  Example: modal run scripts/modal_ingest.py --onboard --jurisdictions \"{','.join(jids)}\" --approve-cost")
            return

        print(f"  Cost approved. Launching full onboard pipeline...")
        print()
        result = batch_onboard.remote(
            jurisdictions=",".join(jids),
            since_date=since,
            cost_cap_usd=cap,
            days_past=onboard_days_past,
            dry_run=False,
        )
        _print_onboard_results(result)
        return

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
    # Note: elections is NOT in --all (use scheduled_election_refresh for state-specific sources)
    # Note: transcripts is included in --all as part of daily pipeline
    # Note: elected_officials is NOT in --all (monthly refresh via scheduled_election_refresh)
    run_municipal = all or municipal
    run_legislation = all or legislation
    run_executive_orders = all or executive_orders
    run_federal_programs = federal_programs  # Not in --all (weekly refresh)
    run_federal_rules = federal_rules  # Not in --all (weekly refresh)
    run_federal_awards = federal_awards  # Not in --all (weekly refresh)
    run_legislative_events = legislative_events  # Not in --all (weekly refresh)
    run_meetings = all or meetings
    run_issues = all or issues
    run_elections = elections  # Not in --all (use scheduled_election_refresh)
    run_ballot_preview = ballot_preview  # Not in --all (pre-election only)
    run_elected_officials = elected_officials  # Not in --all (monthly refresh)
    run_transcripts = all or transcripts
    run_chunks = all or chunks
    run_agenda = all or agenda
    run_decisions = decisions  # Explicitly not in --all (weekly only)
    run_videos = videos  # Not in --all (YouTube jurisdictions need explicit flag)
    run_vectors = all or vectors
    run_score_rules = score_rules  # Not in --all (explicit or auto after fetch)
    run_refresh = refresh  # Not in --all (explicit only)

    if not (run_municipal or run_legislation or run_executive_orders or run_federal_programs or run_federal_rules or run_federal_awards or run_legislative_events or run_meetings or run_issues or run_elections or run_ballot_preview or run_elected_officials or run_videos or run_transcripts or run_chunks or run_agenda or run_decisions or run_vectors or run_score_rules or run_refresh):
        print("No tasks specified. Use --all, --municipal, --legislation, --executive-orders, --federal-programs, --federal-rules, --federal-awards, --legislative-events, --meetings, --issues, --elections, --ballot-preview, --elected-officials, --videos, --transcripts, --chunks, --agenda, --decisions, --vectors, or --refresh")
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
    if run_federal_awards:
        task_list.append("federal_awards")
    if run_legislative_events:
        task_list.append("legislative_events")
    if run_meetings:
        task_list.append("meetings")
    if run_issues:
        task_list.append("issues")
    if run_elections:
        task_list.append("elections")
    if run_ballot_preview:
        task_list.append("ballot_preview")
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
    if run_refresh:
        task_list.append("refresh")
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
    if run_federal_awards:
        print(f"  Federal Awards: USAspending.gov (all configured jurisdictions)")
    if run_legislative_events:
        print(f"  Legislative Events: {legislation_jurisdiction} (hearing dates from existing bills)")
    if run_meetings:
        print(f"  Meetings: {jurisdiction}" + (" (incremental)" if incremental else ""))
    if run_issues:
        print(f"  Issues: {jurisdiction}" + (" (incremental)" if incremental else ""))
    if run_elections:
        print(f"  Elections: {jurisdiction}")
    if run_ballot_preview:
        print(f"  Ballot Preview: {jurisdiction} (CA SOS candidate PDFs)")
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
    if run_refresh:
        print(f"  Refresh: {jurisdiction} (municipal_code)" + (" (force)" if force else ""))
    print(f"Dry run: {dry_run}")
    print(f"Auto-index: {auto_index}" + (" (vectors indexed after each store)" if auto_index else " (vectors NOT indexed after store)"))
    print("=" * 60)

    # Spawn tasks in parallel
    handles = []

    if run_refresh:
        print("\nSpawning municipal code refresh (incremental)...")
        handle = refresh_municipal_code.spawn(
            jurisdiction=jurisdiction,
            force=force,
            dry_run=dry_run,
            reindex=auto_index,
        )
        handles.append(("refresh_municipal_code", handle))

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

    if run_score_rules:
        print("Spawning federal rules LLM relevance scoring...")
        handle = score_federal_rules_llm.spawn(
            jurisdiction=jurisdiction,
            dry_run=dry_run,
        )
        handles.append(("score_rules", handle))

    if run_federal_awards:
        print("Spawning federal awards fetch...")
        handle = fetch_federal_awards.spawn(
            dry_run=dry_run,
            auto_index=auto_index,
        )
        handles.append(("federal_awards", handle))

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
        print("Spawning elections refresh (state-specific sources)...")
        handle = scheduled_election_refresh.spawn()
        handles.append(("elections", handle))

    if run_ballot_preview:
        import json as json_mod
        config_path = f"data/extraction/{jurisdiction}.json"
        races_json = ""
        try:
            with open(config_path) as f:
                config = json_mod.load(f)
            bp_config = config.get("election_sources", {}).get("ca_sos_ballot_preview", {})
            if bp_config.get("races"):
                races_json = json_mod.dumps(bp_config["races"])
            election_slug = bp_config.get("election_slug", "2026-primary")
            election_date = bp_config.get("election_date", "2026-06-02")
            election_type = bp_config.get("election_type", "primary")
        except FileNotFoundError:
            election_slug = "2026-primary"
            election_date = "2026-06-02"
            election_type = "primary"
        print(f"Spawning ballot preview ({election_slug})...")
        handle = fetch_ballot_preview.spawn(
            jurisdiction=jurisdiction,
            election_slug=election_slug,
            election_date=election_date,
            election_type=election_type,
            races_json=races_json,
            dry_run=dry_run,
        )
        handles.append(("ballot_preview", handle))

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
    fetch_errors = {}
    for name, handle in handles:
        print(f"\nWaiting for {name}...")
        try:
            result = handle.get()
            fetch_results[name] = result
            print(f"  {name}: {result.get('elapsed_seconds', 0):.1f}s, cost: ${result.get('cost_usd', 0):.4f}")
        except Exception as e:
            fetch_errors[name] = str(e)
            print(f"  {name}: FAILED — {e}")
            fetch_results[name] = {"error": str(e), "elapsed_seconds": 0, "cost_usd": 0}

    # Extract transcripts after meetings are fetched (audio download + transcription)
    transcripts_result = None
    if run_transcripts:
        print(f"\nRunning transcript extraction (audio + transcription)...")
        print(f"  Cost cap: ${transcripts_cost_cap:.0f} | Since: {transcripts_since or 'default (6 months)'}")
        transcripts_result = extract_transcripts.remote(
            jurisdiction=jurisdiction,
            limit=transcripts_limit,
            dry_run=dry_run,
            batch=True,  # Use batch mode for parallel transcription
            auto_index=auto_index,
            since_date=transcripts_since,
            cost_cap_usd=transcripts_cost_cap,
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

    if fetch_errors:
        print(f"\n⚠️  {len(fetch_errors)} stage(s) failed:")
        for name, err in fetch_errors.items():
            print(f"  ✗ {name}: {err[:200]}")
    print("=" * 60)
    print(f"Total estimated cost: ${total_cost:.4f}")
    print("=" * 60)

