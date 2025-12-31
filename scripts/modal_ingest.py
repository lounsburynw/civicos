"""
Modal unified ingestion script for Civic data pipeline.

This module provides a single entrypoint for running all data ingestion tasks
in parallel on Modal's serverless compute infrastructure. It orchestrates:
- Municipal code fetch (Municode API)
- Legislation text fetch (LegiScan API)
- Vector indexing (fastembed embeddings)

Architecture:
    modal run scripts/modal_ingest.py --all
    └── spawn() parallel tasks:
        ├── fetch_municipal_code()  → Postgres
        ├── fetch_legislation()     → Postgres
        └── index_vectors()         → pgvector

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal setup
    3. Create secrets:
       modal secret create civic-db DATABASE_URL="postgresql://..."
       modal secret create civic-legiscan LEGISCAN_API_KEY="..."
    4. Run: modal run scripts/modal_ingest.py --all

Usage:
    # Run all ingestion (municipal, legislation, vectors)
    modal run scripts/modal_ingest.py --all

    # Run specific components
    modal run scripts/modal_ingest.py --municipal
    modal run scripts/modal_ingest.py --legislation
    modal run scripts/modal_ingest.py --vectors

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
    - Recommendation: Use --legislation-jurisdiction to run one at a time

Cost Estimates (Modal compute):
    - Municipal code fetch: ~$0.05 (20-30 min, 4GB)
    - Legislation fetch: ~$0.20 (1-4 hours, 4GB)
    - Vector indexing: ~$0.10 (5-10 min, 16GB)
    - Full --all run: ~$0.35
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
        "requests>=2.31.0",  # For LegiScan API
        "fastembed>=0.3.0",  # For embeddings
        "numpy<2",  # fastembed compatibility
        "langgraph>=0.2.0",
    )
    # Add local civic packages
    .add_local_python_source("civic", "civic_extraction", "civic_services")
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
        all_corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"]

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
    vectors: bool = False,
    jurisdiction: str = "city-san-rafael",
    legislation_jurisdiction: str = "state-CA",
    legislation_limit: int | None = None,
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
        modal run scripts/modal_ingest.py --vectors

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
    run_municipal = all or municipal
    run_legislation = all or legislation
    run_vectors = all or vectors

    if not (run_municipal or run_legislation or run_vectors):
        print("No tasks specified. Use --all, --municipal, --legislation, or --vectors")
        print("Use --stats-only to check current state")
        return

    print("\n" + "=" * 60)
    print("Civic Unified Ingestion")
    print("=" * 60)
    print(f"Tasks: {'municipal ' if run_municipal else ''}{'legislation ' if run_legislation else ''}{'vectors' if run_vectors else ''}")
    if run_municipal:
        print(f"  Municipal: {jurisdiction}")
    if run_legislation:
        print(f"  Legislation: {legislation_jurisdiction}" + (f" (limit: {legislation_limit})" if legislation_limit else ""))
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

    # Wait for fetch tasks to complete before vectorizing
    # (vectors should index the fresh data)
    fetch_results = {}
    for name, handle in handles:
        print(f"\nWaiting for {name}...")
        result = handle.get()
        fetch_results[name] = result
        print(f"  {name}: {result.get('elapsed_seconds', 0):.1f}s, cost: ${result.get('cost_usd', 0):.4f}")

    # Now run vectors (after fetches complete, so we index fresh data)
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
