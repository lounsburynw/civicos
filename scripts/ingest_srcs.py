#!/usr/bin/env python3
"""
SRCS (San Rafael City Schools) Data Ingestion Script

Ingests school board meeting data from Simbli portal:
1. Scrapes meetings from Simbli board page
2. Downloads agenda PDFs via MID workflow
3. Extracts text chunks from PDFs
4. Stores meetings and chunks in PostgreSQL
5. Indexes chunks in pgvector for semantic search

Usage:
    # Dry run (show what would be ingested)
    python scripts/ingest_srcs.py --dry-run

    # Ingest meetings only (no PDFs)
    python scripts/ingest_srcs.py --meetings-only

    # Full ingestion (meetings + PDFs + chunks)
    python scripts/ingest_srcs.py

    # Limit number of meetings to process
    python scripts/ingest_srcs.py --limit 5

    # Verbose output
    python scripts/ingest_srcs.py -v

Requirements:
    - DATABASE_URL environment variable (PostgreSQL connection string)
    - Playwright browser installed: playwright install chromium
"""

import argparse
import logging
import os
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Jurisdiction ID for SRCS
JURISDICTION_ID = "school-san-rafael"


def parse_pdf_to_chunks(
    pdf_bytes: bytes,
    meeting_id: str,
    meeting_title: str,
    page_size: int = 1000,
    overlap: int = 100,
) -> List[Dict[str, Any]]:
    """
    Parse PDF bytes and extract text chunks for RAG indexing.

    Uses PyMuPDF to extract text and splits into overlapping chunks.

    Args:
        pdf_bytes: Raw PDF content
        meeting_id: Meeting ID for chunk association
        meeting_title: Meeting title for context
        page_size: Target chunk size in characters
        overlap: Overlap between chunks

    Returns:
        List of chunk dictionaries ready for storage
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        return []

    chunks = []

    try:
        # Open PDF from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num, page in enumerate(doc):
            page_text = page.get_text()

            if not page_text.strip():
                continue

            # Split page into overlapping chunks
            start = 0
            chunk_index = 0

            while start < len(page_text):
                end = min(start + page_size, len(page_text))

                # Try to break at sentence boundary
                if end < len(page_text):
                    for sep in [". ", ".\n", "\n\n"]:
                        last_sep = page_text[start:end].rfind(sep)
                        if last_sep > page_size // 2:
                            end = start + last_sep + len(sep)
                            break

                chunk_text = page_text[start:end].strip()

                if chunk_text:
                    chunk_id = f"{meeting_id}-p{page_num + 1}-c{chunk_index}"
                    chunks.append({
                        "id": chunk_id,
                        "meeting_id": meeting_id,
                        "text": chunk_text,
                        "page_number": page_num + 1,
                        "chunk_index": chunk_index,
                        "source": "simbli",
                        "metadata": {
                            "meeting_title": meeting_title,
                            "extraction_method": "pymupdf",
                        },
                    })
                    chunk_index += 1

                start = end - overlap if end < len(page_text) else end

        doc.close()
        logger.debug(f"Extracted {len(chunks)} chunks from PDF ({len(pdf_bytes)} bytes)")

    except Exception as e:
        logger.error(f"Error parsing PDF: {e}")

    return chunks


def ingest_meetings(
    since: Optional[date] = None,
    limit: int = 0,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Scrape meetings from Simbli and store in PostgreSQL.

    Args:
        since: Only fetch meetings after this date
        limit: Maximum meetings to process (0 = no limit)
        dry_run: If True, show what would be ingested without storing

    Returns:
        List of meeting dictionaries that were processed
    """
    from civic_extraction.clients.simbli import (
        create_srcs_simbli_client,
        simbli_meeting_to_storage,
    )

    if since is None:
        since = date(2024, 1, 1)

    logger.info(f"Fetching SRCS meetings since {since}")

    meetings = []
    with create_srcs_simbli_client(headless=True) as client:
        simbli_meetings = client.get_meetings(since=since, limit=limit or 50)
        logger.info(f"Found {len(simbli_meetings)} meetings from Simbli")

        for meeting in simbli_meetings:
            mapped = simbli_meeting_to_storage(meeting, JURISDICTION_ID)
            meetings.append(mapped)

            if limit and len(meetings) >= limit:
                break

    if dry_run:
        logger.info("DRY RUN: Would store the following meetings:")
        for m in meetings:
            logger.info(f"  - {m['id']}: {m['title']} ({m['meeting_type']})")
        return meetings

    if not meetings:
        logger.info("No meetings to store")
        return []

    # Store meetings in PostgreSQL
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Cannot store meetings.")
        return meetings

    from civic.storage.postgres_backend import PostgresBackend

    backend = PostgresBackend(database_url)
    stored = backend.store_meetings(JURISDICTION_ID, meetings)
    logger.info(f"Stored {stored} meetings in PostgreSQL")

    return meetings


def ingest_pdfs(
    meetings: List[Dict[str, Any]],
    dry_run: bool = False,
) -> int:
    """
    Download agenda PDFs and extract text chunks.

    Args:
        meetings: List of meeting dictionaries with simbli_mid in raw_data
        dry_run: If True, show what would be processed without storing

    Returns:
        Total number of chunks extracted
    """
    from civic_extraction.clients.simbli import create_srcs_simbli_client

    database_url = os.environ.get("DATABASE_URL")
    if not database_url and not dry_run:
        logger.error("DATABASE_URL not set. Cannot store chunks.")
        return 0

    total_chunks = 0
    meetings_with_mid = [m for m in meetings if m.get("raw_data", {}).get("simbli_mid")]

    if not meetings_with_mid:
        logger.warning("No meetings have Simbli MID for PDF download")
        return 0

    logger.info(f"Processing {len(meetings_with_mid)} meetings with MIDs")

    if dry_run:
        logger.info("DRY RUN: Would download PDFs for:")
        for m in meetings_with_mid:
            mid = m.get("raw_data", {}).get("simbli_mid")
            logger.info(f"  - {m['id']} (MID: {mid})")
        return 0

    from civic.storage.postgres_backend import PostgresBackend

    backend = PostgresBackend(database_url)

    with create_srcs_simbli_client(headless=True) as client:
        for meeting in meetings_with_mid:
            mid = meeting.get("raw_data", {}).get("simbli_mid")
            meeting_id = meeting["id"]
            meeting_title = meeting["title"]

            logger.info(f"Downloading PDF for {meeting_id} (MID: {mid})")

            try:
                pdf_bytes = client.download_agenda_pdf_via_mid(mid)

                if pdf_bytes:
                    logger.info(f"  Downloaded {len(pdf_bytes)} bytes")

                    # Parse PDF to chunks
                    chunks = parse_pdf_to_chunks(
                        pdf_bytes,
                        meeting_id,
                        meeting_title,
                    )

                    if chunks:
                        # Store chunks
                        stored = backend.store_chunks(
                            JURISDICTION_ID,
                            chunks,
                            meeting_id=meeting_id,
                        )
                        logger.info(f"  Stored {stored} chunks")
                        total_chunks += stored
                    else:
                        logger.warning(f"  No chunks extracted from PDF")
                else:
                    logger.warning(f"  Failed to download PDF")

            except Exception as e:
                logger.error(f"  Error processing {meeting_id}: {e}")

            # Rate limiting
            time.sleep(2)

    return total_chunks


def index_vectors(dry_run: bool = False) -> int:
    """
    Index chunks in pgvector for semantic search.

    Args:
        dry_run: If True, show what would be indexed without storing

    Returns:
        Number of vectors indexed
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Cannot index vectors.")
        return 0

    if dry_run:
        logger.info("DRY RUN: Would index chunks in pgvector")
        return 0

    from civic.storage import get_storage_backend
    from civic.storage.pgvector_backend import PgVectorBackend

    logger.info("Indexing chunks in pgvector...")

    backend = get_storage_backend(database_url)
    pgvector = PgVectorBackend(connection_string=database_url, provider_type="fastembed")

    # Validate pgvector connection
    validation = pgvector.validate()
    if not validation.is_valid:
        logger.error(f"pgvector validation failed: {validation.errors}")
        return 0

    try:
        count = pgvector.index_from_storage(
            storage_backend=backend,
            jurisdiction_id=JURISDICTION_ID,
            corpus_type="chunks",
            batch_size=100,
        )
        logger.info(f"Indexed {count} chunk vectors")
        return count

    except Exception as e:
        logger.error(f"Error indexing vectors: {e}")
        return 0


def verify_ingestion() -> Dict[str, Any]:
    """
    Verify ingestion by querying database.

    Returns:
        Dictionary with counts of meetings, chunks, and vectors
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    import psycopg2

    results = {}

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # Count meetings from Simbli
        cursor.execute("""
            SELECT COUNT(*) FROM meetings
            WHERE jurisdiction_id = %s AND source_platform = 'simbli'
            AND valid_to IS NULL
        """, (JURISDICTION_ID,))
        results["meetings"] = cursor.fetchone()[0]

        # Count chunks for this jurisdiction
        cursor.execute("""
            SELECT COUNT(*) FROM chunks
            WHERE jurisdiction_id = %s
            AND valid_to IS NULL
        """, (JURISDICTION_ID,))
        results["chunks"] = cursor.fetchone()[0]

        # Count vectors for chunks
        cursor.execute("""
            SELECT COUNT(*) FROM vector_embeddings
            WHERE jurisdiction_id = %s AND corpus_type = 'chunks'
        """, (JURISDICTION_ID,))
        results["vectors"] = cursor.fetchone()[0]

        cursor.close()
        conn.close()

    except Exception as e:
        results["error"] = str(e)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Ingest SRCS school board meeting data from Simbli",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be ingested without storing",
    )
    parser.add_argument(
        "--meetings-only",
        action="store_true",
        help="Only ingest meetings (skip PDF download and chunking)",
    )
    parser.add_argument(
        "--skip-vectors",
        action="store_true",
        help="Skip vector indexing after chunk extraction",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of meetings to process (0 = no limit)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only fetch meetings since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Just verify existing ingestion (no new data)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Verify mode
    if args.verify:
        logger.info("Verifying SRCS data ingestion...")
        results = verify_ingestion()
        print("\n" + "=" * 50)
        print("SRCS Data Ingestion Status")
        print("=" * 50)
        if "error" in results:
            print(f"ERROR: {results['error']}")
        else:
            print(f"Meetings (source=simbli):  {results.get('meetings', 0)}")
            print(f"Chunks (source=simbli):    {results.get('chunks', 0)}")
            print(f"Vectors (corpus=chunks):   {results.get('vectors', 0)}")
        print("=" * 50)
        return 0

    # Parse since date
    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {args.since}. Use YYYY-MM-DD")
            return 1

    print("\n" + "=" * 60)
    print("SRCS Data Ingestion")
    print("=" * 60)
    print(f"Jurisdiction: {JURISDICTION_ID}")
    print(f"Dry run: {args.dry_run}")
    print(f"Meetings only: {args.meetings_only}")
    print(f"Limit: {args.limit or 'None'}")
    print(f"Since: {since or 'Jan 2024'}")
    print("=" * 60 + "\n")

    # Step 1: Ingest meetings
    logger.info("Step 1: Ingesting meetings from Simbli...")
    meetings = ingest_meetings(
        since=since,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    if not meetings:
        logger.warning("No meetings to process")
        return 0

    if args.meetings_only:
        logger.info("Meetings-only mode. Skipping PDF processing.")
        return 0

    # Step 2: Download PDFs and extract chunks
    logger.info("\nStep 2: Downloading PDFs and extracting chunks...")
    total_chunks = ingest_pdfs(meetings, dry_run=args.dry_run)

    if args.skip_vectors:
        logger.info("Skipping vector indexing (--skip-vectors)")
    elif not args.dry_run and total_chunks > 0:
        # Step 3: Index vectors
        logger.info("\nStep 3: Indexing vectors in pgvector...")
        indexed = index_vectors(dry_run=args.dry_run)

    # Final summary
    print("\n" + "=" * 60)
    print("Ingestion Complete")
    print("=" * 60)
    print(f"Meetings processed: {len(meetings)}")
    if not args.meetings_only:
        print(f"Chunks extracted: {total_chunks}")
    if args.dry_run:
        print("(DRY RUN - no data was stored)")
    print("=" * 60)

    # Verify
    if not args.dry_run:
        results = verify_ingestion()
        if "error" not in results:
            print(f"\nDatabase verification:")
            print(f"  Meetings: {results.get('meetings', 0)}")
            print(f"  Chunks: {results.get('chunks', 0)}")
            print(f"  Vectors: {results.get('vectors', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
