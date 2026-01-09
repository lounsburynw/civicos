#!/usr/bin/env python3
"""
SRCS (San Rafael City Schools) Data Ingestion Script

Ingests school board meeting data from Simbli portal:
1. Scrapes meetings from Simbli board page
2. Downloads agenda PDFs via MID workflow
3. Uploads PDFs directly to R2 storage during download
4. Extracts text chunks from PDFs
5. Stores meetings and chunks in PostgreSQL
6. Indexes chunks in pgvector for semantic search

Usage:
    # Dry run (show what would be ingested)
    python scripts/ingest_srcs.py --dry-run

    # Ingest meetings only (no PDFs)
    python scripts/ingest_srcs.py --meetings-only

    # Full ingestion (meetings + PDFs + chunks + R2 upload)
    python scripts/ingest_srcs.py

    # Skip R2 upload (local processing only)
    python scripts/ingest_srcs.py --skip-r2

    # Limit number of meetings to process
    python scripts/ingest_srcs.py --limit 5

    # Verbose output
    python scripts/ingest_srcs.py -v

Requirements:
    - DATABASE_URL environment variable (PostgreSQL connection string)
    - Playwright browser installed: playwright install chromium
    - For R2 uploads: BLOB_STORAGE_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
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
    skip_r2: bool = False,
) -> int:
    """
    Download agenda PDFs, upload to R2, and extract text chunks.

    PDFs are uploaded directly to R2 during download with the key pattern:
    school-san-rafael/agendas/{meeting_id}.pdf

    The R2 URL is stored in meetings.agenda_url for consistent access.

    Args:
        meetings: List of meeting dictionaries with simbli_mid in raw_data
        dry_run: If True, show what would be processed without storing
        skip_r2: If True, skip R2 upload (local processing only)

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
            r2_key = f"{JURISDICTION_ID}/agendas/{m['id']}.pdf"
            logger.info(f"  - {m['id']} (MID: {mid}) -> {r2_key}")
        return 0

    from civic.storage.postgres_backend import PostgresBackend

    backend = PostgresBackend(database_url)

    # Initialize blob storage for R2 uploads
    blob_storage = None
    if not skip_r2:
        from civic.storage.blob import get_blob_storage
        try:
            blob_storage = get_blob_storage()
            validation = blob_storage.validate()
            if validation.is_valid:
                logger.info(f"Blob storage ready: {blob_storage.backend_type}")
            else:
                logger.warning(f"Blob storage validation failed: {validation.errors}")
                logger.warning("Continuing without R2 upload")
                blob_storage = None
        except Exception as e:
            logger.warning(f"Could not initialize blob storage: {e}")
            logger.warning("Continuing without R2 upload")
            blob_storage = None

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

                    # Upload to R2 if available
                    r2_url = None
                    if blob_storage:
                        r2_key = f"{JURISDICTION_ID}/agendas/{meeting_id}.pdf"
                        try:
                            r2_url = blob_storage.upload(
                                key=r2_key,
                                data=pdf_bytes,
                                content_type="application/pdf",
                                metadata={
                                    "meeting_id": meeting_id,
                                    "meeting_title": meeting_title,
                                    "source": "simbli",
                                },
                            )
                            logger.info(f"  Uploaded to R2: {r2_key}")

                            # Update meeting with agenda_url
                            _update_meeting_agenda_url(
                                backend, JURISDICTION_ID, meeting_id, r2_url
                            )
                        except Exception as e:
                            logger.error(f"  Failed to upload to R2: {e}")

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


def _update_meeting_agenda_url(
    backend, jurisdiction_id: str, meeting_id: str, agenda_url: str
) -> bool:
    """
    Update meeting record with agenda_url using StorageBackend protocol.

    Args:
        backend: StorageBackend instance (PostgresBackend or SQLiteBackend)
        jurisdiction_id: Jurisdiction ID (e.g., "school-san-rafael")
        meeting_id: Meeting ID to update
        agenda_url: R2 URL for the agenda PDF

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        updated = backend.update_meeting(
            jurisdiction_id=jurisdiction_id,
            meeting_id=meeting_id,
            updates={"agenda_url": agenda_url},
        )
        if updated:
            logger.debug(f"  Updated agenda_url for {meeting_id}")
        return updated

    except Exception as e:
        logger.error(f"  Failed to update agenda_url: {e}")
        return False


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


def backfill_r2_agenda_urls(
    dry_run: bool = False,
    limit: int = 0,
) -> int:
    """
    Backfill R2 agenda URLs for meetings that have simbli_mid but no agenda_url.

    This is for meetings that were ingested before R2 upload was integrated.
    Downloads PDFs via Simbli MID workflow and uploads to R2.

    Args:
        dry_run: If True, show what would be processed without storing
        limit: Maximum meetings to process (0 = no limit)

    Returns:
        Number of meetings updated with R2 URLs
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Cannot backfill.")
        return 0

    from civic.storage import get_storage_backend

    # Use StorageBackend protocol to get all meetings
    backend = get_storage_backend()
    all_meetings = backend.get_meetings(JURISDICTION_ID)

    # Filter in Python: meetings with simbli_mid but no agenda_url
    meetings_to_backfill = []
    for meeting in all_meetings:
        # Skip if already has agenda_url
        if meeting.get("agenda_url"):
            continue

        # Check for simbli_mid in full_data.raw_data
        full_data = meeting.get("full_data") or {}
        if isinstance(full_data, str):
            import json
            full_data = json.loads(full_data)
        raw_data = full_data.get("raw_data", {})
        simbli_mid = raw_data.get("simbli_mid")

        if simbli_mid:
            meetings_to_backfill.append({
                "id": meeting["id"],
                "title": meeting.get("title", "Unknown"),
                "simbli_mid": simbli_mid,
            })

    # Sort by meeting date descending (most recent first)
    meetings_to_backfill.sort(
        key=lambda m: m.get("meeting_datetime", ""),
        reverse=True
    )

    if not meetings_to_backfill:
        logger.info("No meetings need R2 backfill")
        return 0

    if limit > 0:
        meetings_to_backfill = meetings_to_backfill[:limit]

    logger.info(f"Found {len(meetings_to_backfill)} meetings to backfill")

    if dry_run:
        logger.info("DRY RUN: Would backfill R2 URLs for:")
        for m in meetings_to_backfill:
            r2_key = f"{JURISDICTION_ID}/agendas/{m['id']}.pdf"
            logger.info(f"  - {m['id']} (MID: {m['simbli_mid']}) -> {r2_key}")
        return 0

    from civic_extraction.clients.simbli import create_srcs_simbli_client
    from civic.storage.blob import get_blob_storage

    # backend already created above via get_storage_backend()

    # Initialize blob storage for R2 uploads
    try:
        blob_storage = get_blob_storage()
        validation = blob_storage.validate()
        if not validation.is_valid:
            logger.error(f"Blob storage validation failed: {validation.errors}")
            return 0
        logger.info(f"Blob storage ready: {blob_storage.backend_type}")
    except Exception as e:
        logger.error(f"Could not initialize blob storage: {e}")
        return 0

    updated_count = 0

    with create_srcs_simbli_client(headless=True) as client:
        for i, meeting in enumerate(meetings_to_backfill, 1):
            meeting_id = meeting["id"]
            simbli_mid = meeting["simbli_mid"]
            title = meeting["title"]

            logger.info(f"[{i}/{len(meetings_to_backfill)}] {meeting_id}: {title[:40]}...")

            try:
                pdf_bytes = client.download_agenda_pdf_via_mid(simbli_mid)

                if pdf_bytes:
                    logger.info(f"  Downloaded {len(pdf_bytes)} bytes")

                    # Upload to R2
                    r2_key = f"{JURISDICTION_ID}/agendas/{meeting_id}.pdf"
                    try:
                        r2_url = blob_storage.upload(
                            key=r2_key,
                            data=pdf_bytes,
                            content_type="application/pdf",
                            metadata={
                                "meeting_id": meeting_id,
                                "meeting_title": title,
                                "source": "simbli",
                            },
                        )
                        logger.info(f"  Uploaded to R2: {r2_key}")

                        # Update meeting with agenda_url
                        if _update_meeting_agenda_url(backend, JURISDICTION_ID, meeting_id, r2_url):
                            updated_count += 1
                            logger.info(f"  Updated agenda_url")
                        else:
                            logger.warning(f"  Failed to update agenda_url")

                    except Exception as e:
                        logger.error(f"  Failed to upload to R2: {e}")
                else:
                    logger.warning(f"  Failed to download PDF")

            except Exception as e:
                logger.error(f"  Error processing {meeting_id}: {e}")

            # Rate limiting
            time.sleep(2)

    logger.info(f"Backfill complete: {updated_count}/{len(meetings_to_backfill)} meetings updated")
    return updated_count


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
        "--skip-r2",
        action="store_true",
        help="Skip R2 upload (local processing only, no agenda_url update)",
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
        "--backfill-r2",
        action="store_true",
        help="Backfill R2 agenda URLs for meetings with simbli_mid but no agenda_url",
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

    # Backfill R2 agenda URLs mode
    if args.backfill_r2:
        logger.info("Backfilling R2 agenda URLs for meetings with simbli_mid but no agenda_url...")
        updated = backfill_r2_agenda_urls(
            dry_run=args.dry_run,
            limit=args.limit,
        )
        if not args.dry_run:
            print(f"\nBackfill complete: {updated} meetings updated with R2 URLs")
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
    print(f"Skip R2: {args.skip_r2}")
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

    # Step 2: Download PDFs, upload to R2, and extract chunks
    logger.info("\nStep 2: Downloading PDFs, uploading to R2, and extracting chunks...")
    total_chunks = ingest_pdfs(meetings, dry_run=args.dry_run, skip_r2=args.skip_r2)

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
