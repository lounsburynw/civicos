"""
Vector indexing command for civic-extract CLI.

Indexes meeting chunks and decisions into pgvector for semantic search.

Usage:
    civic-extract vectors --jurisdiction city-san-rafael
    civic-extract vectors --jurisdiction city-san-rafael --corpus decisions
    civic-extract vectors --jurisdiction city-san-rafael --corpus chunks
    civic-extract vectors --jurisdiction city-san-rafael --dry-run
    civic-extract vectors --jurisdiction city-san-rafael --stats

Cloud mode (default when DATABASE_URL set):
    - Reads chunks/decisions from Postgres
    - Indexes into pgvector table
    - Enables semantic search on cloud data
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

from civic._internal.meetings.transcript import expand_transcripts_to_chunks
from civic._internal.legal.embeddings.chunker import (
    expand_municipal_code_to_chunks,
    expand_legislation_to_chunks,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class VectorIndexResult:
    """Result of a vector indexing operation."""

    jurisdiction_id: str
    corpus_type: str
    documents_indexed: int
    status: str  # "success", "skipped", "error"
    error: Optional[str] = None


def add_vectors_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the vectors subcommand to the parser."""
    parser = subparsers.add_parser(
        "vectors",
        help="Index chunks/decisions into pgvector for semantic search",
        description="Build vector index for RAG search on cloud data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--corpus",
        default="chunks",
        choices=["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues", "legislation", "all"],
        help="Type of documents to index (default: chunks)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed, don't actually index",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current vector index statistics",
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force reindex even if vectors already exist",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for embedding generation (default: 100)",
    )
    parser.add_argument(
        "--test-search",
        type=str,
        help="Run a test search query after indexing",
    )
    parser.add_argument(
        "--provider",
        default="fastembed",
        choices=["fastembed", "local", "openai"],
        help="Embedding provider: fastembed (default, portable ONNX), local (sentence-transformers), openai (API)",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="Override embedding model name (provider-specific)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip first N documents (for splitting large corpus across jobs)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N documents (for splitting large corpus across jobs)",
    )


def run_vectors(args: argparse.Namespace) -> int:
    """Run the vectors command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check for DATABASE_URL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        logger.error("Vector indexing requires cloud storage (Postgres + pgvector)")
        logger.error("Set DATABASE_URL to your PostgreSQL connection string")
        return 1

    if args.stats:
        return show_stats(args.jurisdiction, args.corpus, args.provider, args.embedding_model)

    if args.dry_run:
        return dry_run(args.jurisdiction, args.corpus, args.provider, args.embedding_model)

    # Index vectors
    results = run_vector_indexing(
        jurisdiction_id=args.jurisdiction,
        corpus_type=args.corpus,
        reindex=args.reindex,
        batch_size=args.batch_size,
        provider_type=args.provider,
        embedding_model=args.embedding_model,
        offset=args.offset,
        limit=args.limit,
    )

    if not results:
        return 1

    # Run test search if requested
    if args.test_search:
        logger.info("")
        run_test_search(
            args.jurisdiction,
            args.corpus,
            args.test_search,
            provider_type=args.provider,
            embedding_model=args.embedding_model,
        )

    return 0


def show_stats(
    jurisdiction_id: str,
    corpus_type: str,
    provider_type: str = "fastembed",
    embedding_model: Optional[str] = None,
) -> int:
    """Show current vector index statistics."""
    try:
        from civic.storage import get_storage_backend
        from civic.storage.pgvector_backend import PgVectorBackend

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return 1

        backend = get_storage_backend()
        pgvector = PgVectorBackend(
            connection_string=database_url,
            provider_type=provider_type,
            embedding_model=embedding_model,
        )

        # Validate connection
        validation = pgvector.validate()
        if not validation.is_valid:
            logger.error("pgvector validation failed:")
            for error in validation.errors:
                logger.error(f"  - {error}")
            return 1

        logger.info("=" * 50)
        logger.info(f"Vector Index Statistics for {jurisdiction_id}")
        logger.info("=" * 50)

        corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"] if corpus_type == "all" else [corpus_type]

        for ct in corpus_types:
            stats = pgvector.get_stats(jurisdiction_id, ct, backend)
            logger.info(f"\n{ct.upper()}:")
            logger.info(f"  Indexed documents: {stats.document_count}")
            if stats.storage_document_count is not None:
                coverage = (stats.document_count / stats.storage_document_count * 100) if stats.storage_document_count > 0 else 0
                logger.info(f"  Storage documents: {stats.storage_document_count}")
                logger.info(f"  Coverage: {coverage:.1f}%")
            logger.info(f"  Embedding model: {stats.embedding_model}")
            logger.info(f"  Embedding dimension: {stats.embedding_dimension}")
            if stats.last_indexed:
                logger.info(f"  Last indexed: {stats.last_indexed}")

        logger.info("=" * 50)
        return 0

    except ImportError as e:
        logger.error(f"Required package not available: {e}")
        return 1
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return 1


def dry_run(
    jurisdiction_id: str,
    corpus_type: str,
    provider_type: str = "fastembed",
    embedding_model: Optional[str] = None,
) -> int:
    """Show what would be indexed."""
    try:
        from civic.storage import get_storage_backend
        from civic.storage.pgvector_backend import PgVectorBackend

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return 1

        backend = get_storage_backend()
        pgvector = PgVectorBackend(
            connection_string=database_url,
            provider_type=provider_type,
            embedding_model=embedding_model,
        )

        logger.info("Dry-run mode - showing indexing plan:")
        logger.info("=" * 50)

        corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"] if corpus_type == "all" else [corpus_type]

        for ct in corpus_types:
            logger.info(f"\n{ct.upper()}:")

            # Get storage count based on corpus type
            if ct == "chunks":
                docs = backend.get_chunks(jurisdiction_id)
                storage_count = len(docs) if docs else 0
            elif ct == "decisions":
                docs = backend.get_decisions(jurisdiction_id)
                storage_count = len(docs) if docs else 0
            elif ct == "meetings":
                docs = backend.get_meetings(jurisdiction_id)
                storage_count = len(docs) if docs else 0
            elif ct == "transcripts":
                storage_count = backend.get_transcript_count(jurisdiction_id)
            elif ct == "municipal_code":
                storage_count = backend.get_municipal_code_count(jurisdiction_id)
            elif ct == "issues":
                storage_count = backend.get_issue_count(jurisdiction_id)
            else:
                storage_count = 0

            # Get current vector count
            stats = pgvector.get_stats(jurisdiction_id, ct)
            indexed_count = stats.document_count

            to_index = storage_count - indexed_count

            logger.info(f"  Storage documents: {storage_count}")
            logger.info(f"  Already indexed: {indexed_count}")
            logger.info(f"  To index: {max(0, to_index)}")

            if indexed_count > 0 and indexed_count == storage_count:
                logger.info("  Status: Up to date (use --reindex to force)")
            elif storage_count == 0:
                logger.info("  Status: No documents in storage")
            else:
                logger.info("  Status: Indexing needed")

        logger.info("=" * 50)
        return 0

    except ImportError as e:
        logger.error(f"Required package not available: {e}")
        return 1
    except Exception as e:
        logger.error(f"Error in dry run: {e}")
        return 1


def run_vector_indexing(
    jurisdiction_id: str,
    corpus_type: str = "chunks",
    reindex: bool = False,
    batch_size: int = 100,
    provider_type: str = "fastembed",
    embedding_model: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = None,
) -> Optional[List[VectorIndexResult]]:
    """
    Run vector indexing for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        corpus_type: Type of documents ("chunks", "decisions", "meetings", "all")
        reindex: If True, delete existing index and rebuild
        batch_size: Number of documents to embed at once
        provider_type: Embedding provider ('fastembed', 'local', 'openai')
        embedding_model: Override embedding model name
        offset: Skip first N documents (for splitting across jobs)
        limit: Process at most N documents (for splitting across jobs)

    Returns:
        List of VectorIndexResult if successful, None if failed
    """
    try:
        from civic.storage import get_storage_backend
        from civic.storage.pgvector_backend import PgVectorBackend

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return None

        backend = get_storage_backend()
        pgvector = PgVectorBackend(
            connection_string=database_url,
            provider_type=provider_type,
            embedding_model=embedding_model,
        )

        # Validate pgvector connection
        logger.info("Validating pgvector connection...")
        validation = pgvector.validate()
        if not validation.is_valid:
            logger.error("pgvector validation failed:")
            for error in validation.errors:
                logger.error(f"  - {error}")
            return None

        for warning in validation.warnings:
            logger.warning(f"  - {warning}")

        logger.info(f"pgvector ready (check took {validation.check_duration_ms:.1f}ms)")

        # Determine corpus types to index
        corpus_types = ["chunks", "decisions", "meetings", "transcripts", "municipal_code", "issues"] if corpus_type == "all" else [corpus_type]

        results = []

        for ct in corpus_types:
            logger.info("")
            logger.info(f"Indexing {ct} for {jurisdiction_id}...")

            # Delete existing if reindex requested
            if reindex:
                deleted = pgvector.delete_index(jurisdiction_id, ct)
                if deleted > 0:
                    logger.info(f"  Deleted {deleted} existing vectors")

            # Check current state
            stats = pgvector.get_stats(jurisdiction_id, ct, backend)

            if not reindex and stats.storage_document_count:
                if stats.document_count >= stats.storage_document_count:
                    logger.info(f"  {ct} already fully indexed ({stats.document_count} vectors)")
                    results.append(VectorIndexResult(
                        jurisdiction_id=jurisdiction_id,
                        corpus_type=ct,
                        documents_indexed=0,
                        status="skipped",
                    ))
                    continue

            # Index from storage
            try:
                # Pass chunkers when needed (storage layer is domain-agnostic)
                transcript_chunker = expand_transcripts_to_chunks if ct == "transcripts" else None
                if ct == "municipal_code":
                    legal_chunker_fn = expand_municipal_code_to_chunks
                elif ct == "legislation":
                    legal_chunker_fn = expand_legislation_to_chunks
                else:
                    legal_chunker_fn = None
                indexed_count = pgvector.index_from_storage(
                    storage_backend=backend,
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=ct,
                    batch_size=batch_size,
                    allow_dimension_change=reindex,  # Allow dimension change when reindexing
                    offset=offset,
                    limit=limit,
                    transcript_chunker=transcript_chunker,
                    legal_chunker=legal_chunker_fn,
                )

                logger.info(f"  ✓ Indexed {indexed_count} {ct}")
                results.append(VectorIndexResult(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=ct,
                    documents_indexed=indexed_count,
                    status="success",
                ))

            except Exception as e:
                logger.error(f"  Error indexing {ct}: {e}")
                results.append(VectorIndexResult(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type=ct,
                    documents_indexed=0,
                    status="error",
                    error=str(e),
                ))

        # Store ETL cost record (track provider for cost visibility)
        total_indexed = sum(r.documents_indexed for r in results)
        if total_indexed > 0:
            try:
                # Estimate cost based on provider
                # OpenAI: ~$0.02/1M tokens (~500 tokens/doc avg)
                # Local/FastEmbed: $0.00
                if provider_type == "openai":
                    estimated_cost = total_indexed * 500 * 0.02 / 1_000_000
                    cost_note = f"Indexed {total_indexed} {corpus_type} documents via OpenAI embeddings (est ${estimated_cost:.4f})"
                else:
                    estimated_cost = 0.0
                    cost_note = f"Indexed {total_indexed} {corpus_type} documents via {provider_type} (no API cost)"

                cost_id = backend.store_etl_cost(
                    pipeline="vectors",
                    jurisdiction_id=jurisdiction_id,
                    items_processed=total_indexed,
                    cost_usd=estimated_cost,
                    notes=cost_note,
                )
                logger.info(f"ETL run recorded (id={cost_id}): ${estimated_cost:.4f} ({provider_type})")
            except Exception as e:
                logger.debug(f"Failed to record ETL run: {e}")

        # Summary
        logger.info("")
        logger.info("=" * 50)
        logger.info(f"Vector Indexing Complete for {jurisdiction_id}")

        successful = sum(1 for r in results if r.status == "success")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "error")

        logger.info(f"Provider: {provider_type}")
        logger.info(f"Model: {pgvector.embedding_model}")
        logger.info(f"Dimension: {pgvector.embedding_dimension}")
        logger.info(f"Total indexed: {total_indexed}")
        logger.info(f"Corpus types: {successful} success, {skipped} skipped, {failed} failed")
        logger.info("=" * 50)

        return results

    except ImportError as e:
        logger.error(f"Required package not available: {e}")
        logger.error("Install with: pip install psycopg2-binary fastembed")
        logger.error("For local embeddings: pip install sentence-transformers")
        logger.error("For OpenAI embeddings: pip install openai")
        return None
    except Exception as e:
        logger.error(f"Error in vector indexing: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_test_search(
    jurisdiction_id: str,
    corpus_type: str,
    query: str,
    provider_type: str = "fastembed",
    embedding_model: Optional[str] = None,
) -> None:
    """Run a test search query."""
    try:
        from civic.storage.pgvector_backend import PgVectorBackend

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return

        pgvector = PgVectorBackend(
            connection_string=database_url,
            provider_type=provider_type,
            embedding_model=embedding_model,
        )

        # Use first corpus type if "all"
        ct = "chunks" if corpus_type == "all" else corpus_type

        logger.info(f"Test search: \"{query}\" in {ct}")
        logger.info("-" * 50)

        results = pgvector.search(
            query=query,
            jurisdiction_id=jurisdiction_id,
            corpus_type=ct,
            top_k=3,
        )

        if not results:
            logger.info("No results found")
            return

        for i, result in enumerate(results, 1):
            logger.info(f"\n[{i}] Score: {result.score:.4f}")
            logger.info(f"    Meeting: {result.meeting_title or result.meeting_id or 'N/A'}")
            logger.info(f"    Content: {result.content[:150]}...")

    except Exception as e:
        logger.error(f"Test search failed: {e}")


def run_scheduled(
    jurisdiction_id: str,
    corpus_type: str = "chunks",
    batch_size: int = 100,
) -> None:
    """
    Run vector indexing on a schedule.

    Uses the schedule library to run daily at 12pm (after chunks at 11am).
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting vector indexing scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 12:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_vector_indexing(
            jurisdiction_id,
            corpus_type=corpus_type,
            batch_size=batch_size,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 12pm daily (after chunks at 11am)
    schedule.every().day.at("12:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial vector indexing...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)
