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

# Build image with all dependencies pre-installed
# This image is cached, so subsequent runs start quickly
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2
    .apt_install("libpq-dev", "gcc")
    # Python dependencies
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "fastembed>=0.3.0",
        "numpy<2",  # fastembed compatibility
    )
)

# Mount local civic packages into the container
# This is more reliable than pip install from private GitHub
civic_mount = modal.Mount.from_local_python_packages("civic", "civic_extraction")


@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db")],
    memory=16384,  # 16GB RAM - sufficient for fastembed + batch processing
    timeout=3600,  # 1 hour max
    retries=modal.Retries(
        max_retries=2,
        backoff_coefficient=2.0,
        initial_delay=10.0,
    ),
)
def index_corpus(
    corpus: str,
    jurisdiction: str = "city-san-rafael",
    batch_size: int = 100,
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
        Dict with results per corpus type
    """
    import logging
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    logger.info(f"Starting vector indexing: corpus={corpus}, jurisdiction={jurisdiction}")
    logger.info(f"Parameters: batch_size={batch_size}, offset={offset}, limit={limit}, reindex={reindex}")

    # Initialize backends
    backend = get_storage_backend()
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
    all_corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"]
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
            count = pgvector.index_from_storage(
                storage_backend=backend,
                jurisdiction_id=jurisdiction,
                corpus_type=ct,
                batch_size=batch_size,
                offset=offset,
                limit=limit,
                allow_dimension_change=reindex,
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

    logger.info(f"Indexing complete: {total_indexed} documents indexed")
    logger.info(f"Results: {success_count} success, {error_count} errors")

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
        Dict with stats per corpus type
    """
    import os

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = get_storage_backend()
    pgvector = PgVectorBackend(
        connection_string=database_url,
        provider_type="fastembed",
    )

    corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"]
    stats = {}

    for ct in corpus_types:
        s = pgvector.get_stats(jurisdiction, ct, backend)
        coverage = (
            f"{s.document_count / s.storage_document_count * 100:.1f}%"
            if s.storage_document_count
            else "N/A"
        )
        stats[ct] = {
            "indexed": s.document_count,
            "total": s.storage_document_count or 0,
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
        batch_size=100,
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


@app.local_entrypoint()
def main(
    corpus: str = "all",
    jurisdiction: str = "city-san-rafael",
    batch_size: int = 100,
    offset: int = 0,
    limit: int | None = None,
    reindex: bool = False,
    stats_only: bool = False,
):
    """
    CLI entrypoint for modal run.

    Examples:
        modal run scripts/modal_vectors.py
        modal run scripts/modal_vectors.py --corpus chunks
        modal run scripts/modal_vectors.py --stats-only
        modal run scripts/modal_vectors.py --corpus chunks --reindex
    """
    if stats_only:
        result = get_stats.remote(jurisdiction)
        print("\n" + "=" * 60)
        print(f"Vector Index Statistics for {jurisdiction}")
        print("=" * 60)
        for corpus_type, s in result.items():
            status = "✓" if s["indexed"] == s["total"] and s["total"] > 0 else "○"
            print(f"{status} {corpus_type:15} {s['indexed']:>5}/{s['total']:<5} ({s['coverage']})")
        print("=" * 60)
        return

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
        if r["status"] == "success":
            print(f"✓ {corpus_type:15} {r['indexed']:>5} indexed")
            total_indexed += r["indexed"]
        elif r["status"] == "skipped":
            print(f"○ {corpus_type:15} skipped ({r['message']})")
        else:
            print(f"✗ {corpus_type:15} FAILED: {r.get('error', 'unknown')}")

    print("=" * 60)
    print(f"Total: {total_indexed} documents indexed")
