"""
Modal function for vector indexing with high memory.

This module provides serverless compute for embedding generation, solving the
memory constraints of GitHub Actions runners (7GB) by using Modal's configurable
memory (16GB+).

Architecture:
    GitHub Actions (trigger) -> Modal (compute) -> Postgres/pgvector (storage)

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal setup
    3. Create secret: modal secret create civic-db DATABASE_URL="postgresql://..."
    4. Deploy: modal deploy scripts/modal_vectors.py

Usage:
    # Run indexing for all corpus types
    modal run scripts/modal_vectors.py

    # Run indexing for specific corpus
    modal run scripts/modal_vectors.py --corpus chunks

    # Check stats only
    modal run scripts/modal_vectors.py --stats-only

    # Trigger from GitHub Actions (see .github/workflows/vector-refresh-modal.yml)
"""

import modal

# Define the Modal app
app = modal.App("civic-vectors")

# Build image with GPU support and model pre-cached
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2
    .apt_install("libpq-dev", "gcc")
    # Python dependencies with GPU support
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "fastembed-gpu>=0.3.0",  # GPU-accelerated version
        "numpy<2",
        "langgraph>=0.2.0",
        "httpx>=0.24.0",
    )
    # Pre-download the embedding model during image build
    .run_commands(
        "python -c \"from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')\""
    )
    # Add local packages (civic_extraction not needed for vector indexing)
    .add_local_python_source("civic")
    .add_local_python_source("civic_config")
)


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    gpu="T4",  # T4 sufficient for embeddings, bulk DB inserts are the win
    memory=16384,
    timeout=3600,
    retries=modal.Retries(
        max_retries=2,
        backoff_coefficient=2.0,
        initial_delay=10.0,
    ),
)
def index_corpus(
    corpus: str,
    jurisdiction: str = "city-san-rafael",
    batch_size: int = 500,  # Larger batches for bulk inserts
    offset: int = 0,
    limit: int | None = None,
    reindex: bool = False,
) -> dict:
    """
    Index a corpus type into pgvector.

    Args:
        corpus: Corpus type ("chunks", "decisions", "meetings", etc.) or "all"
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael")
        batch_size: Number of documents to embed at once
        offset: Skip first N documents (for splitting across jobs)
        limit: Process at most N documents
        reindex: If True, delete existing vectors first

    Returns:
        Dict with results per corpus type, including cost estimate
    """
    import logging
    import time
    start_time = time.time()
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend
    from civic._internal.meetings.transcript import expand_transcripts_to_chunks
    from civic._internal.legal.embeddings.chunker import (
        expand_municipal_code_to_chunks,
        expand_legislation_to_chunks,
        expand_codified_law_to_chunks,
        expand_executive_orders_to_chunks,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    logger.info(f"Starting vector indexing: corpus={corpus}, jurisdiction={jurisdiction}")
    logger.info(f"Parameters: batch_size={batch_size}, offset={offset}, limit={limit}, reindex={reindex}")

    # Initialize backends (use postgres for storage - legislation is only there)
    backend = get_storage_backend(database_url)
    pgvector = PgVectorBackend(
        connection_string=database_url,
        provider_type="fastembed",
    )

    # Validate pgvector connection
    validation = pgvector.validate()
    if not validation.is_valid:
        error_msg = f"pgvector validation failed: {validation.errors}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.info(f"pgvector connection validated ({validation.check_duration_ms:.1f}ms)")

    # Determine corpus types to process
    # Different jurisdiction prefixes have different corpus types:
    # - "city-*": Local civic data (meetings, decisions, issues, etc.)
    # - "legislation-*": State legislation (e.g., "legislation-CA")
    # - "federal-US", "federal-CFR", "state-CA": Codified law
    # - "federal-EO": Executive Orders
    #
    # Note: "state-CA" is for CA codified law (CA Codes), not legislation
    # Legislation uses "legislation-CA" format
    codified_law_jurisdictions = {"federal-US", "federal-CFR", "state-CA"}

    all_corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"]
    if jurisdiction in codified_law_jurisdictions:
        all_corpus_types = ["codified_law"]
    elif jurisdiction == "federal-EO":
        all_corpus_types = ["executive_orders"]
    elif jurisdiction.startswith("legislation-"):
        # legislation-CA -> state code CA
        all_corpus_types = ["legislation"]
    corpus_types = all_corpus_types if corpus == "all" else [corpus]

    results = {}

    for ct in corpus_types:
        logger.info(f"Processing corpus: {ct}")

        # Delete existing vectors if reindexing
        if reindex:
            deleted = pgvector.delete_index(jurisdiction, ct)
            logger.info(f"  Deleted {deleted} existing vectors")

        # Check current state
        stats = pgvector.get_stats(jurisdiction, ct, backend)
        logger.info(f"  Current state: {stats.document_count}/{stats.storage_document_count or '?'} indexed")

        # Skip if already fully indexed (unless reindexing)
        if not reindex and stats.storage_document_count:
            if stats.document_count >= stats.storage_document_count:
                logger.info(f"  Skipping {ct} - already fully indexed")
                results[ct] = {
                    "status": "skipped",
                    "indexed": 0,
                    "total": stats.storage_document_count,
                    "message": "Already fully indexed",
                }
                continue

        # Index from storage
        try:
            # Pass chunkers when needed (storage layer is domain-agnostic)
            transcript_chunker = expand_transcripts_to_chunks if ct == "transcripts" else None
            if ct == "municipal_code":
                legal_chunker_fn = expand_municipal_code_to_chunks
            elif ct == "legislation":
                legal_chunker_fn = expand_legislation_to_chunks
            elif ct == "codified_law":
                legal_chunker_fn = expand_codified_law_to_chunks
            elif ct == "executive_orders":
                legal_chunker_fn = expand_executive_orders_to_chunks
            else:
                legal_chunker_fn = None
            count = pgvector.index_from_storage(
                storage_backend=backend,
                jurisdiction_id=jurisdiction,
                corpus_type=ct,
                batch_size=batch_size,
                offset=offset,
                limit=limit,
                allow_dimension_change=reindex,
                transcript_chunker=transcript_chunker,
                legal_chunker=legal_chunker_fn,
                use_copy=reindex,  # COPY is 10x faster when vectors deleted first
            )

            results[ct] = {
                "status": "success",
                "indexed": count,
                "total": stats.storage_document_count,
            }
            logger.info(f"  Successfully indexed {count} documents")

        except Exception as e:
            logger.exception(f"  Error indexing {ct}")
            results[ct] = {
                "status": "error",
                "indexed": 0,
                "error": str(e),
            }

    # Log summary
    total_indexed = sum(r.get("indexed", 0) for r in results.values())
    success_count = sum(1 for r in results.values() if r["status"] == "success")
    error_count = sum(1 for r in results.values() if r["status"] == "error")

    # Cost tracking
    elapsed_seconds = time.time() - start_time
    memory_gb = 16  # Configured memory
    gb_seconds = memory_gb * elapsed_seconds
    estimated_cost = gb_seconds * 0.000463  # Modal CPU pricing

    logger.info(f"Indexing complete: {total_indexed} documents indexed")
    logger.info(f"Results: {success_count} success, {error_count} errors")
    logger.info(f"Cost: {elapsed_seconds:.0f}s × {memory_gb}GB = ${estimated_cost:.3f}")

    results["_cost"] = {
        "elapsed_seconds": elapsed_seconds,
        "memory_gb": memory_gb,
        "gb_seconds": gb_seconds,
        "estimated_cost_usd": estimated_cost,
    }
    return results


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,  # 4GB is sufficient for stats
    timeout=300,
)
def get_stats(jurisdiction: str = "city-san-rafael") -> dict:
    """
    Get vector index statistics for all corpus types.

    Args:
        jurisdiction: Jurisdiction ID

    Returns:
        Dict with stats per corpus type, including chunk_count for chunked corpora
    """
    import os

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend
    from civic._internal.meetings.transcript import expand_transcripts_to_chunks
    from civic._internal.legal.embeddings.chunker import (
        expand_municipal_code_to_chunks,
        expand_legislation_to_chunks,
        expand_codified_law_to_chunks,
        expand_executive_orders_to_chunks,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Use postgres backend for storage (legislation is only in postgres)
    backend = get_storage_backend(database_url)
    pgvector = PgVectorBackend(
        connection_string=database_url,
        provider_type="fastembed",
    )

    # Determine corpus types based on jurisdiction type
    codified_law_jurisdictions = {"federal-US", "federal-CFR", "state-CA"}

    if jurisdiction in codified_law_jurisdictions:
        corpus_types = ["codified_law"]
    elif jurisdiction == "federal-EO":
        corpus_types = ["executive_orders"]
    elif jurisdiction.startswith("legislation-"):
        corpus_types = ["legislation"]
    else:
        corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"]
    stats = {}

    for ct in corpus_types:
        s = pgvector.get_stats(jurisdiction, ct, backend)
        coverage = (
            f"{s.document_count / s.storage_document_count * 100:.1f}%"
            if s.storage_document_count
            else "N/A"
        )

        # For chunked corpora, calculate actual chunk count for parallel distribution
        chunk_count = s.storage_document_count or 0
        if ct == "municipal_code" and chunk_count > 0:
            raw_sections = backend.get_municipal_code(jurisdiction)
            chunks = expand_municipal_code_to_chunks(raw_sections)
            chunk_count = len(chunks)
        elif ct == "transcripts" and chunk_count > 0:
            raw_transcripts = backend.get_transcripts(jurisdiction)
            chunks = expand_transcripts_to_chunks(raw_transcripts)
            chunk_count = len(chunks)
        elif ct == "legislation" and chunk_count > 0:
            if jurisdiction.startswith("state-"):
                state_code = jurisdiction.split("-", 1)[1].upper()
            else:
                state_code = jurisdiction.upper()
            raw_bills = backend.get_legislation(state=state_code)
            chunks = expand_legislation_to_chunks(raw_bills)
            chunk_count = len(chunks)
        elif ct == "codified_law" and chunk_count > 0:
            raw_sections = backend.get_codified_law(jurisdiction)
            chunks = expand_codified_law_to_chunks(raw_sections)
            chunk_count = len(chunks)
        elif ct == "executive_orders" and chunk_count > 0:
            raw_orders = backend.get_executive_orders()
            chunks = expand_executive_orders_to_chunks(raw_orders)
            chunk_count = len(chunks)

        stats[ct] = {
            "indexed": s.document_count,
            "total": s.storage_document_count or 0,
            "chunk_count": chunk_count,  # Actual count for parallel distribution
            "coverage": coverage,
            "model": s.embedding_model,
        }

    return stats


# Scheduled function for weekly refresh
@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=16384,
    timeout=3600,
    schedule=modal.Cron("0 6 * * 0"),  # Weekly on Sunday at 6 AM UTC
)
def scheduled_refresh():
    """Weekly scheduled vector refresh."""
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Starting scheduled vector refresh")

    # Run full indexing
    result = index_corpus.local(
        corpus="all",
        jurisdiction="city-san-rafael",
        batch_size=1000,  # Large batches reduce DB round-trips
    )

    # Log results
    for corpus_type, r in result.items():
        if r["status"] == "success":
            logger.info(f"{corpus_type}: indexed {r['indexed']} documents")
        elif r["status"] == "skipped":
            logger.info(f"{corpus_type}: skipped ({r['message']})")
        else:
            logger.error(f"{corpus_type}: FAILED - {r.get('error', 'unknown error')}")

    return result


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=4096,  # Lightweight - just deletes
    timeout=300,
)
def delete_vectors(jurisdiction: str, corpus: str) -> int:
    """Delete all vectors for a jurisdiction/corpus. Returns count deleted."""
    import os
    from civic.storage.pgvector_backend import PgVectorBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    pgvector = PgVectorBackend(
        connection_string=database_url,
        provider_type="fastembed",
    )
    return pgvector.delete_index(jurisdiction, corpus)


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    cpu=16,  # 16 CPUs for fast parallel embedding inference
    memory=32768,  # 32GB RAM to match CPU count
    timeout=3600,
)
def index_batch(
    corpus: str,
    jurisdiction: str,
    batch_size: int,
    offset: int,
    limit: int,
    worker_id: int,
    use_copy: bool = False,
) -> dict:
    """
    Index a batch of documents (used for parallel processing).

    This function is designed to be called in parallel by multiple workers,
    each processing a different offset/limit range.

    Args:
        use_copy: If True, use PostgreSQL COPY for bulk inserts (10x faster).
                  Only safe when existing vectors have been deleted first.
    """
    import logging
    import os

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [Worker {worker_id}] %(message)s",
    )
    logger = logging.getLogger(__name__)

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend
    from civic._internal.meetings.transcript import expand_transcripts_to_chunks
    from civic._internal.legal.embeddings.chunker import (
        expand_municipal_code_to_chunks,
        expand_legislation_to_chunks,
        expand_codified_law_to_chunks,
        expand_executive_orders_to_chunks,
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    logger.info(f"Starting batch: corpus={corpus}, offset={offset}, limit={limit}")

    backend = get_storage_backend(database_url)
    pgvector = PgVectorBackend(
        connection_string=database_url,
        provider_type="fastembed",
    )

    # Select chunker based on corpus type
    transcript_chunker = expand_transcripts_to_chunks if corpus == "transcripts" else None
    if corpus == "municipal_code":
        legal_chunker_fn = expand_municipal_code_to_chunks
    elif corpus == "legislation":
        legal_chunker_fn = expand_legislation_to_chunks
    elif corpus == "codified_law":
        legal_chunker_fn = expand_codified_law_to_chunks
    elif corpus == "executive_orders":
        legal_chunker_fn = expand_executive_orders_to_chunks
    else:
        legal_chunker_fn = None

    try:
        count = pgvector.index_from_storage(
            storage_backend=backend,
            jurisdiction_id=jurisdiction,
            corpus_type=corpus,
            batch_size=batch_size,
            offset=offset,
            limit=limit,
            allow_dimension_change=True,  # Parallel workers may see dimension changes
            transcript_chunker=transcript_chunker,
            legal_chunker=legal_chunker_fn,
            use_copy=use_copy,
        )
        logger.info(f"Completed batch: indexed {count} documents")
        return {"status": "success", "indexed": count, "worker_id": worker_id}
    except Exception as e:
        logger.exception(f"Error in batch")
        return {"status": "error", "indexed": 0, "error": str(e), "worker_id": worker_id}


@app.local_entrypoint()
def main(
    corpus: str = "all",
    jurisdiction: str = "city-san-rafael",
    batch_size: int = 1000,  # Large batches reduce DB round-trips
    offset: int = 0,
    limit: int | None = None,
    reindex: bool = False,
    stats_only: bool = False,
    parallel: int = 1,
):
    """
    CLI entrypoint for modal run.

    Examples:
        modal run scripts/modal_vectors.py
        modal run scripts/modal_vectors.py --corpus chunks
        modal run scripts/modal_vectors.py --stats-only
        modal run scripts/modal_vectors.py --corpus chunks --reindex
        modal run scripts/modal_vectors.py --corpus municipal_code --reindex --parallel 4
    """
    if stats_only:
        result = get_stats.remote(jurisdiction)
        print("\n" + "=" * 60)
        print(f"Vector Index Statistics for {jurisdiction}")
        print("=" * 60)
        for corpus_type, s in result.items():
            status = "✓" if s["indexed"] == s["total"] and s["total"] > 0 else "○"
            model = s.get("model", "unknown")
            model_short = model.split("/")[-1] if model else "unknown"
            print(f"{status} {corpus_type:15} {s['indexed']:>5}/{s['total']:<5} ({s['coverage']}) [{model_short}]")
        print("=" * 60)
        return

    # Parallel processing mode
    if parallel > 1:
        if corpus == "all":
            print("ERROR: --parallel requires a specific --corpus (not 'all')")
            return

        print(f"\nStarting PARALLEL vector indexing on Modal ({parallel} workers)...")
        print(f"Corpus: {corpus}, Jurisdiction: {jurisdiction}")

        # Get stats to determine total document count
        stats = get_stats.remote(jurisdiction)
        if corpus not in stats:
            print(f"ERROR: Unknown corpus type: {corpus}")
            return

        # Use chunk_count for chunked corpora (municipal_code, transcripts, legislation)
        # This ensures correct distribution for parallel workers
        total_docs = stats[corpus].get("chunk_count", stats[corpus]["total"])
        if total_docs == 0:
            print(f"No documents to index for {corpus}")
            return

        print(f"Total documents (chunks): {total_docs}")

        # Delete existing vectors first if reindexing
        if reindex:
            print(f"Deleting existing vectors for {corpus}...")
            # Direct delete via a lightweight function call
            delete_count = delete_vectors.remote(jurisdiction, corpus)
            print(f"Deleted {delete_count} existing vectors, ready for parallel indexing")

        # Calculate ranges for each worker
        # use_copy=True when reindexing (vectors deleted above, so COPY is safe and 10x faster)
        docs_per_worker = (total_docs + parallel - 1) // parallel
        ranges = []
        for i in range(parallel):
            worker_offset = i * docs_per_worker
            worker_limit = min(docs_per_worker, total_docs - worker_offset)
            if worker_limit > 0:
                ranges.append((corpus, jurisdiction, batch_size, worker_offset, worker_limit, i, reindex))

        print(f"Spawning {len(ranges)} parallel workers...")
        for i, (_, _, _, off, lim, _, use_copy) in enumerate(ranges):
            print(f"  Worker {i}: offset={off}, limit={lim}, use_copy={use_copy}")

        # Run all workers in parallel using starmap
        results = list(index_batch.starmap(ranges))

        # Aggregate results
        print("\n" + "=" * 60)
        print("Parallel Indexing Results")
        print("=" * 60)

        total_indexed = 0
        errors = []
        for r in results:
            if r["status"] == "success":
                print(f"✓ Worker {r['worker_id']:2}: {r['indexed']:>5} indexed")
                total_indexed += r["indexed"]
            else:
                print(f"✗ Worker {r['worker_id']:2}: FAILED - {r.get('error', 'unknown')}")
                errors.append(r)

        print("=" * 60)
        print(f"Total: {total_indexed} documents indexed across {len(ranges)} workers")
        if errors:
            print(f"WARNING: {len(errors)} worker(s) failed")
        return

    # Sequential processing (original behavior)
    print(f"\nStarting vector indexing on Modal (16GB RAM)...")
    print(f"Corpus: {corpus}, Jurisdiction: {jurisdiction}")
    if offset or limit:
        print(f"Range: offset={offset}, limit={limit}")

    result = index_corpus.remote(
        corpus=corpus,
        jurisdiction=jurisdiction,
        batch_size=batch_size,
        offset=offset,
        limit=limit,
        reindex=reindex,
    )

    print("\n" + "=" * 60)
    print("Indexing Results")
    print("=" * 60)

    total_indexed = 0
    for corpus_type, r in result.items():
        if corpus_type.startswith("_"):  # Skip metadata keys like _cost
            continue
        if r["status"] == "success":
            print(f"✓ {corpus_type:15} {r['indexed']:>5} indexed")
            total_indexed += r["indexed"]
        elif r["status"] == "skipped":
            print(f"○ {corpus_type:15} skipped ({r['message']})")
        else:
            print(f"✗ {corpus_type:15} FAILED: {r.get('error', 'unknown')}")

    print("=" * 60)
    print(f"Total: {total_indexed} documents indexed")
