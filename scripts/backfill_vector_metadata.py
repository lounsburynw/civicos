#!/usr/bin/env python3
"""
Backfill metadata for vector_embeddings that were indexed without metadata.

Fixes MCP data quality issues:
- Transcript embeddings: populates speaker, timestamps, video_id, etc.
- Decision embeddings: populates title, outcome, meeting_date
- Meeting embeddings: populates meeting_title, meeting_datetime

Usage:
    python3 scripts/backfill_vector_metadata.py --corpus transcripts
    python3 scripts/backfill_vector_metadata.py --corpus decisions
    python3 scripts/backfill_vector_metadata.py --corpus all
    python3 scripts/backfill_vector_metadata.py --corpus transcripts --dry-run
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civicos" / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_env():
    """Load .env file manually (avoids dotenv frame issues)."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def backfill_transcripts(jurisdiction_id: str, dry_run: bool = False):
    """
    Re-run transcript chunker and update metadata for existing embeddings.

    The chunker produces chunk dicts with speaker, timestamps, video_id, etc.
    We match by chunk ID and UPDATE the metadata column.
    """
    import psycopg2
    from civicos._internal.meetings.transcript import expand_transcripts_to_chunks

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Get source transcripts
    cur.execute(
        "SELECT id, jurisdiction_id, video_id, transcript FROM transcripts WHERE jurisdiction_id = %s",
        (jurisdiction_id,),
    )
    rows = cur.fetchall()
    logger.info(f"Found {len(rows)} source transcripts")

    # Convert to dicts for the chunker
    transcripts = []
    for row in rows:
        transcript_data = row[3]
        if isinstance(transcript_data, str):
            transcript_data = json.loads(transcript_data)
        transcripts.append({
            "id": row[0],
            "jurisdiction_id": row[1],
            "video_id": row[2],
            "transcript": transcript_data,
        })

    # Run chunker
    logger.info("Running transcript chunker...")
    chunks = expand_transcripts_to_chunks(transcripts)
    logger.info(f"Produced {len(chunks)} chunks")

    # Build lookup: chunk_id -> metadata
    chunk_metadata = {}
    for chunk in chunks:
        chunk_id = chunk["id"]
        # Build metadata dict (same logic as index_from_storage)
        metadata = {
            k: v
            for k, v in chunk.items()
            if k not in ("id", "text", "content", "meeting_id", "meeting_title", "meeting_date", "meeting_datetime")
        }
        chunk_metadata[chunk_id] = metadata

    logger.info(f"Built metadata for {len(chunk_metadata)} chunks")

    # Check how many existing embeddings match
    cur.execute(
        """SELECT id FROM vector_embeddings
        WHERE corpus_type = 'transcripts' AND jurisdiction_id = %s""",
        (jurisdiction_id,),
    )
    existing_ids = {row[0] for row in cur.fetchall()}

    matched = existing_ids & set(chunk_metadata.keys())
    unmatched_existing = existing_ids - set(chunk_metadata.keys())
    unmatched_new = set(chunk_metadata.keys()) - existing_ids

    logger.info(f"Existing embeddings: {len(existing_ids)}")
    logger.info(f"Matched: {len(matched)}")
    logger.info(f"Unmatched existing (won't update): {len(unmatched_existing)}")
    logger.info(f"New chunks (no embedding): {len(unmatched_new)}")

    if dry_run:
        # Show sample
        for chunk_id in list(matched)[:3]:
            meta = chunk_metadata[chunk_id]
            logger.info(f"  Would update {chunk_id}: video_id={meta.get('video_id')}, "
                        f"speaker={meta.get('speaker')}, start_ms={meta.get('start_ms')}, "
                        f"start_timestamp={meta.get('start_timestamp')}")
        logger.info("DRY RUN - no changes made")
        conn.close()
        return 0

    # Batch UPDATE metadata
    updated = 0
    batch_size = 100
    matched_list = list(matched)

    for i in range(0, len(matched_list), batch_size):
        batch = matched_list[i : i + batch_size]
        for chunk_id in batch:
            meta = chunk_metadata[chunk_id]
            meta_json = json.dumps(meta, default=str)
            cur.execute(
                """UPDATE vector_embeddings
                SET metadata = %s::jsonb
                WHERE id = %s AND corpus_type = 'transcripts' AND jurisdiction_id = %s""",
                (meta_json, chunk_id, jurisdiction_id),
            )
            updated += cur.rowcount

        conn.commit()
        logger.info(f"  Updated {min(i + batch_size, len(matched_list))}/{len(matched_list)}")

    logger.info(f"Updated {updated} transcript embeddings with metadata")
    conn.close()
    return updated


def backfill_decisions(jurisdiction_id: str, dry_run: bool = False):
    """
    Join vector_embeddings against decisions table to populate metadata.

    Decision embedding IDs match decisions.id (e.g., "2025-12-15-2.a").
    """
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Get decision data from source table
    cur.execute(
        """SELECT id, title, outcome, meeting_date, topics, agenda_item, summary
        FROM decisions WHERE jurisdiction_id = %s""",
        (jurisdiction_id,),
    )
    decisions = {}
    for row in cur.fetchall():
        decisions[row[0]] = {
            "title": row[1],
            "outcome": row[2],
            "meeting_date": row[3],
            "topics": row[4],
            "agenda_item": row[5],
            "summary": row[6],
        }
    logger.info(f"Found {len(decisions)} source decisions")

    # Get existing decision embeddings
    cur.execute(
        """SELECT id FROM vector_embeddings
        WHERE corpus_type = 'decisions' AND jurisdiction_id = %s""",
        (jurisdiction_id,),
    )
    existing_ids = {row[0] for row in cur.fetchall()}
    logger.info(f"Found {len(existing_ids)} decision embeddings")

    matched = existing_ids & set(decisions.keys())
    logger.info(f"Matched: {len(matched)}")

    if dry_run:
        for did in list(matched)[:3]:
            d = decisions[did]
            logger.info(f"  Would update {did}: title={d['title'][:60]}, "
                        f"outcome={d['outcome']}, date={d['meeting_date']}")
        logger.info("DRY RUN - no changes made")
        conn.close()
        return 0

    # Update metadata and meeting_datetime for each matched decision
    updated = 0
    for did in matched:
        d = decisions[did]
        # Build metadata
        metadata = {
            "title": d["title"],
            "outcome": d["outcome"],
            "topics": d["topics"],
            "agenda_item": d["agenda_item"],
        }
        meta_json = json.dumps(metadata, default=str)

        # Parse meeting_date to datetime for the meeting_datetime column
        meeting_dt = None
        if d["meeting_date"]:
            try:
                from datetime import datetime
                meeting_dt = datetime.strptime(d["meeting_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                meeting_dt = None

        cur.execute(
            """UPDATE vector_embeddings
            SET metadata = %s::jsonb,
                meeting_title = %s,
                meeting_datetime = %s
            WHERE id = %s AND corpus_type = 'decisions' AND jurisdiction_id = %s""",
            (meta_json, d["title"], meeting_dt, did, jurisdiction_id),
        )
        updated += cur.rowcount

    conn.commit()
    logger.info(f"Updated {updated} decision embeddings with metadata")
    conn.close()
    return updated


def backfill_meetings(jurisdiction_id: str, dry_run: bool = False):
    """
    Populate meeting_title and meeting_datetime for meeting embeddings.
    """
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Get meeting data
    cur.execute(
        """SELECT id, title, meeting_datetime FROM meetings WHERE jurisdiction_id = %s""",
        (jurisdiction_id,),
    )
    meetings = {}
    for row in cur.fetchall():
        meetings[row[0]] = {"title": row[1], "datetime": row[2]}
    logger.info(f"Found {len(meetings)} source meetings")

    # Get existing meeting embeddings
    cur.execute(
        """SELECT id, meeting_id FROM vector_embeddings
        WHERE corpus_type = 'meetings' AND jurisdiction_id = %s""",
        (jurisdiction_id,),
    )
    embeddings = [(row[0], row[1]) for row in cur.fetchall()]
    logger.info(f"Found {len(embeddings)} meeting embeddings")

    if dry_run:
        for emb_id, meeting_id in embeddings[:3]:
            mid = meeting_id or emb_id
            if mid in meetings:
                m = meetings[mid]
                logger.info(f"  Would update {emb_id}: title={m['title'][:50]}, dt={m['datetime']}")
        logger.info("DRY RUN - no changes made")
        conn.close()
        return 0

    updated = 0
    for emb_id, meeting_id in embeddings:
        mid = meeting_id or emb_id
        if mid in meetings:
            m = meetings[mid]
            cur.execute(
                """UPDATE vector_embeddings
                SET meeting_title = %s, meeting_datetime = %s
                WHERE id = %s AND corpus_type = 'meetings' AND jurisdiction_id = %s""",
                (m["title"], m["datetime"], emb_id, jurisdiction_id),
            )
            updated += cur.rowcount

    conn.commit()
    logger.info(f"Updated {updated} meeting embeddings")
    conn.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill vector embedding metadata")
    parser.add_argument("--corpus", choices=["transcripts", "decisions", "meetings", "all"], default="all")
    parser.add_argument("--jurisdiction", default="city-san-rafael")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without making changes")
    args = parser.parse_args()

    load_env()

    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL not set. Check .env file.")
        sys.exit(1)

    if args.corpus in ("transcripts", "all"):
        logger.info("=== Backfilling transcript metadata ===")
        backfill_transcripts(args.jurisdiction, dry_run=args.dry_run)

    if args.corpus in ("decisions", "all"):
        logger.info("=== Backfilling decision metadata ===")
        backfill_decisions(args.jurisdiction, dry_run=args.dry_run)

    if args.corpus in ("meetings", "all"):
        logger.info("=== Backfilling meeting metadata ===")
        backfill_meetings(args.jurisdiction, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
