#!/usr/bin/env python3
"""
Re-index transcript chunks with roster-aware speaker names.

This script updates vector embeddings for transcripts after speaker metadata
has been updated (e.g., after running backfill_speaker_metadata.py).

The process:
1. Deletes existing transcript vectors for the jurisdiction
2. Re-expands transcripts to chunks using updated speakers_metadata
3. Re-indexes chunks into pgvector with correct speaker names

After this runs, semantic search results will show proper speaker names
like "Kate Colin (Mayor)" instead of "Speaker A".

Usage:
    # Dry run (see what would be re-indexed)
    python scripts/reindex_transcript_speakers.py --dry-run

    # Re-index all transcripts
    python scripts/reindex_transcript_speakers.py

    # Re-index specific jurisdiction
    python scripts/reindex_transcript_speakers.py --jurisdiction city-san-rafael

Prerequisites:
    - speakers_metadata has been backfilled (run backfill_speaker_metadata.py first)
    - DATABASE_URL is set in .env

Note: This is equivalent to running:
    civic-extract vectors --jurisdiction <jid> --corpus transcripts --reindex --force
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/civicos/src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/civicos-extraction/src"))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def verify_speakers_metadata(jurisdiction_id: str) -> dict:
    """
    Verify that transcripts have speakers_metadata with roster data.

    Returns:
        Dict with counts of transcripts and roster-matched speakers
    """
    from civicos import CivicOS

    c = CivicOS(jurisdiction_id)
    transcripts = c._storage.get_transcripts(jurisdiction_id)

    total = len(transcripts)
    with_metadata = 0
    total_speakers = 0
    roster_matched = 0

    for t in transcripts:
        td = t.get("transcript", {})
        sm = td.get("speakers_metadata", {})
        if sm:
            with_metadata += 1
            total_speakers += len(sm)
            roster_matched += sum(1 for s in sm.values() if s.get("roster_matched"))

    return {
        "total_transcripts": total,
        "with_speakers_metadata": with_metadata,
        "total_speakers": total_speakers,
        "roster_matched_speakers": roster_matched,
    }


def reindex_transcript_chunks(
    jurisdiction_id: str,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """
    Re-index transcript chunks with updated speaker metadata.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        dry_run: If True, only show what would be done
        force: If True, proceed even if some safety checks fail

    Returns:
        Dict with indexing results
    """
    import os
    from civicos import CivicOS

    # Verify DATABASE_URL is set
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL not set in environment")
        return {"status": "error", "error": "DATABASE_URL not set"}

    # Initialize storage
    c = CivicOS(jurisdiction_id)
    backend = c._storage
    pgvector = c._vectors

    backend_name = type(backend).__name__
    if backend_name != "PostgresBackend":
        logger.error(f"Expected PostgresBackend, got {backend_name}")
        return {"status": "error", "error": f"Wrong backend: {backend_name}"}

    # Verify speakers_metadata exists
    logger.info(f"Verifying speakers_metadata for {jurisdiction_id}...")
    metadata_stats = verify_speakers_metadata(jurisdiction_id)

    logger.info(f"  Transcripts: {metadata_stats['total_transcripts']}")
    logger.info(f"  With speakers_metadata: {metadata_stats['with_speakers_metadata']}")
    logger.info(f"  Total speakers: {metadata_stats['total_speakers']}")
    logger.info(f"  Roster-matched: {metadata_stats['roster_matched_speakers']}")

    if metadata_stats['with_speakers_metadata'] == 0:
        logger.warning("No transcripts have speakers_metadata!")
        logger.warning("Run backfill_speaker_metadata.py first.")
        if not force:
            return {"status": "error", "error": "No speakers_metadata found"}

    # Get current vector stats
    stats = pgvector.get_stats(jurisdiction_id, "transcripts")
    logger.info(f"\nCurrent vector index:")
    logger.info(f"  Transcript vectors: {stats.document_count}")

    if dry_run:
        logger.info("\n--- DRY RUN ---")
        logger.info(f"Would delete {stats.document_count} transcript vectors")
        logger.info(f"Would re-index from {metadata_stats['total_transcripts']} transcripts")
        logger.info(f"Speaker names would use roster-corrected names")
        return {
            "status": "dry_run",
            "would_delete": stats.document_count,
            "would_index": metadata_stats['total_transcripts'],
        }

    # Delete existing transcript vectors
    logger.info(f"\nDeleting existing transcript vectors...")
    pgvector.delete_index(jurisdiction_id, "transcripts")
    logger.info(f"  Deleted {stats.document_count} vectors")

    # Re-index from storage (this will use expand_transcripts_to_chunks
    # which reads speakers_metadata from the transcript records)
    logger.info(f"\nRe-indexing transcripts with roster-aware speaker names...")

    from civicos._internal.meetings.transcript import expand_transcripts_to_chunks

    indexed_count = pgvector.index_from_storage(
        storage_backend=backend,
        jurisdiction_id=jurisdiction_id,
        corpus_type="transcripts",
        batch_size=100,
        allow_dimension_change=True,
        transcript_chunker=expand_transcripts_to_chunks,
        use_copy=True,  # Safe since we just deleted all vectors
    )

    logger.info(f"  Indexed {indexed_count} transcript chunks")

    # Verify new index
    new_stats = pgvector.get_stats(jurisdiction_id, "transcripts")
    logger.info(f"\nNew vector index:")
    logger.info(f"  Transcript vectors: {new_stats.document_count}")

    return {
        "status": "success",
        "deleted": stats.document_count,
        "indexed": indexed_count,
        "final_count": new_stats.document_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Re-index transcript chunks with roster-aware speaker names"
    )
    parser.add_argument(
        "--jurisdiction", "-j",
        default="city-san-rafael",
        help="Jurisdiction to re-index (default: city-san-rafael)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Proceed even if some safety checks fail"
    )

    args = parser.parse_args()

    result = reindex_transcript_chunks(
        jurisdiction_id=args.jurisdiction,
        dry_run=args.dry_run,
        force=args.force,
    )

    if result["status"] == "success":
        print(f"\n✓ Re-indexing complete: {result['indexed']} chunks indexed")
    elif result["status"] == "dry_run":
        print(f"\nDry run complete. Use without --dry-run to apply changes.")
    else:
        print(f"\n✗ Error: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
