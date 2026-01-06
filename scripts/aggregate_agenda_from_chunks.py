#!/usr/bin/env python3
"""
Aggregate agenda items from already-extracted chunks.

This script creates agenda items from the chunks table, which already
contains parsed PDF content with proper item references (7.a, 6.b, etc.).

This is more reliable than re-parsing PDFs because:
1. Chunks are already extracted and verified
2. No additional PDF downloads needed
3. Can use LLM for actionability classification only (lower cost)

Usage:
    # Dry run - show what would be created
    python scripts/aggregate_agenda_from_chunks.py --dry-run

    # Run extraction (stores to database)
    python scripts/aggregate_agenda_from_chunks.py

    # Limit to specific meetings
    python scripts/aggregate_agenda_from_chunks.py --limit 5
"""

import argparse
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_chunks_by_meeting(jurisdiction_id: str = "city-san-rafael") -> Dict[str, List[Dict]]:
    """
    Get all chunks grouped by meeting_id.

    Returns:
        Dict mapping meeting_id -> list of chunk dicts
    """
    import psycopg2

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    cur.execute("""
        SELECT meeting_id, agenda_item, agenda_title, text, page_start, page_end
        FROM chunks
        WHERE jurisdiction_id = %s
        ORDER BY meeting_id, agenda_item, chunk_index
    """, (jurisdiction_id,))

    chunks_by_meeting: Dict[str, List[Dict]] = defaultdict(list)
    for row in cur.fetchall():
        chunk = {
            "meeting_id": row[0],
            "agenda_item": row[1],
            "agenda_title": row[2],
            "text": row[3],
            "page_start": row[4],
            "page_end": row[5],
        }
        chunks_by_meeting[row[0]].append(chunk)

    conn.close()
    return dict(chunks_by_meeting)


def is_valid_agenda_ref(item_ref: str) -> bool:
    """
    Check if an agenda item reference is a valid municipal agenda format.

    Valid formats:
    - Numbered items: 1, 2, 3, 4 (single digit)
    - Lettered sub-items: 1.a, 2.b, 7.a, 5.c
    - Number+letter (no dot): 3a, 4b
    - Roman numerals: I, II, III
    - Special meeting items: SM 1.a

    Invalid formats:
    - TOC entries: toc_0, toc_39
    - File artifacts: closing, 33p, 078.p, ADP9B92.tmp
    - PDF/UUID refs: 26.p, 4f, 039e, 2025b, a3d6f5fa-...
    - Timestamps: 10p, 38p
    - Unknown
    """
    import re

    if not item_ref:
        return False

    item_ref = item_ref.strip()

    # Skip TOC and unknown
    if item_ref.startswith("toc_") or item_ref == "unknown":
        return False

    # Skip "closing" artifacts
    if item_ref.lower() in ("closing", "close", "closed"):
        return False

    # Skip items that look like file/page refs (end with .p, .t, etc.)
    if re.match(r".*\.[a-z]$", item_ref) and not re.match(r"^\d+\.[a-z]$", item_ref):
        return False

    # Skip hex/UUID-like refs (contain only hex chars, 4+ chars)
    if re.match(r"^[0-9a-f]{4,}$", item_ref.lower()):
        return False

    # Skip timestamp-like refs (digits followed by 'p' for PM)
    if re.match(r"^\d+p$", item_ref.lower()):
        return False

    # Skip refs that start with a year (2025, etc.)
    if re.match(r"^20\d{2}", item_ref):
        return False

    # Valid patterns - strict match only these:
    valid_patterns = [
        r"^\d+$",                    # Single number: 1, 2, 3
        r"^\d+\.[a-zA-Z]$",          # Number.letter: 1.a, 7.b
        r"^\d+[a-zA-Z]$",            # Number+letter: 3a, 4b
        r"^SM \d+\.[a-zA-Z]$",       # Special meeting: SM 1.a
        r"^[IVX]+$",                 # Roman numerals: I, II, III
    ]

    for pattern in valid_patterns:
        if re.match(pattern, item_ref, re.IGNORECASE):
            return True

    return False


def aggregate_chunks_to_items(chunks: List[Dict]) -> List[Dict]:
    """
    Aggregate chunks into distinct agenda items.

    Multiple chunks can belong to the same agenda item - we combine them.

    Returns:
        List of agenda item dicts with combined text
    """
    items_by_ref: Dict[str, Dict] = {}

    for chunk in chunks:
        item_ref = chunk.get("agenda_item", "unknown")

        # Skip invalid agenda references
        if not is_valid_agenda_ref(item_ref):
            continue

        if item_ref not in items_by_ref:
            items_by_ref[item_ref] = {
                "item_ref": item_ref,
                "title": chunk.get("agenda_title", ""),
                "text_parts": [],
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
            }

        # Append text part
        text = chunk.get("text", "")
        if text:
            items_by_ref[item_ref]["text_parts"].append(text)

        # Update page range
        if chunk.get("page_start"):
            current = items_by_ref[item_ref].get("page_start")
            if current is None or chunk["page_start"] < current:
                items_by_ref[item_ref]["page_start"] = chunk["page_start"]
        if chunk.get("page_end"):
            current = items_by_ref[item_ref].get("page_end")
            if current is None or chunk["page_end"] > current:
                items_by_ref[item_ref]["page_end"] = chunk["page_end"]

    # Combine text parts
    items = []
    for item in items_by_ref.values():
        combined_text = "\n\n".join(item.pop("text_parts"))
        item["description"] = combined_text[:2000]  # Limit description length
        items.append(item)

    return items


def classify_actionability_batch(items: List[Dict], meeting_title: str) -> List[Dict]:
    """
    Use LLM to classify actionability for a batch of items.

    This is more efficient than classifying one at a time.
    """
    if not items:
        return items

    try:
        from civic_services.core.llm_provider import get_model_for_task
        provider = get_model_for_task("draft")  # Use fast model for classification

        # Build items summary for LLM
        items_text = "\n".join([
            f"- [{item['item_ref']}] {item['title'][:100]}: {item['description'][:200]}..."
            for item in items[:30]  # Limit to 30 items per batch
        ])

        prompt = f"""Analyze these municipal meeting agenda items for public actionability.

Meeting: {meeting_title}

Items:
{items_text}

For each item, classify:
1. actionable: true/false - Can residents meaningfully participate or should be aware?
2. actionable_reason: Brief explanation of WHY (if actionable)
3. project_type: housing, transportation, environment, budget, education, development, public_safety, community, elections, governance

Return JSON:
{{
    "items": [
        {{"item_ref": "7.a", "actionable": true, "actionable_reason": "Public hearing...", "project_type": "housing"}},
        ...
    ]
}}

Focus on items with:
- Public hearings or comment periods
- Policy decisions affecting residents
- Budget/financial matters
- Development or zoning changes

Skip procedural items (minutes approval, announcements)."""

        response = provider.complete(
            messages=[
                {"role": "system", "content": "You are a civic engagement expert. Classify agenda items for public participation."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0,
        )

        # Parse response
        import json
        text = response.content.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]

        result = json.loads(text.strip())
        classifications = {c["item_ref"]: c for c in result.get("items", [])}

        # Merge classifications into items
        for item in items:
            if item["item_ref"] in classifications:
                c = classifications[item["item_ref"]]
                item["actionable"] = c.get("actionable", False)
                item["actionable_reason"] = c.get("actionable_reason", "")
                item["project_type"] = c.get("project_type", "governance")
            else:
                # Default for unclassified
                item["actionable"] = False
                item["actionable_reason"] = ""
                item["project_type"] = "governance"

        return items

    except Exception as e:
        logger.warning(f"LLM classification failed: {e}, using defaults")
        for item in items:
            item["actionable"] = True  # Conservative default
            item["actionable_reason"] = "Extracted from agenda, actionability not verified"
            item["project_type"] = "governance"
        return items


def get_meeting_title(meeting_id: str) -> str:
    """Get meeting title from database."""
    import psycopg2

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return meeting_id

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute("SELECT title FROM meetings WHERE id = %s", (meeting_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else meeting_id
    except Exception:
        return meeting_id


def store_agenda_items(meeting_id: str, items: List[Dict]) -> int:
    """Store agenda items to database."""
    from civic.storage.postgres_backend import PostgresBackend

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    backend = PostgresBackend(database_url)

    # Format items for storage
    formatted_items = []
    for item in items:
        formatted = {
            "item_ref": item["item_ref"],
            "item_number": item["item_ref"],
            "title": item.get("title", "")[:500],
            "description": item.get("description", "")[:2000],
            "actionable": item.get("actionable", True),
            "actionable_reason": item.get("actionable_reason", ""),
            "project_types": [item.get("project_type", "governance")],
            "participation_mechanisms": [],
            "related_agenda_items": [],
            "follows_from": None,
            "addresses_issues": [],
            "policy_chain": [],
        }
        formatted_items.append(formatted)

    return backend.store_agenda_items(meeting_id, formatted_items)


def items_exist_for_meeting(meeting_id: str) -> bool:
    """Check if real agenda items (not just metadata) exist for a meeting."""
    import psycopg2

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return False

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        # Check for items with proper item references (like 7.a, 3.b, etc.)
        # not just "Agenda" or "Agenda Packet"
        cur.execute("""
            SELECT COUNT(*) FROM agenda_items
            WHERE meeting_id = %s
            AND valid_to IS NULL
            AND item_number ~ '^[0-9]'  -- Starts with a number
        """, (meeting_id,))
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Aggregate agenda items from chunks")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of meetings")
    parser.add_argument("--jurisdiction", default="city-san-rafael", help="Jurisdiction ID")
    parser.add_argument("--force", action="store_true", help="Re-extract even if items exist")
    parser.add_argument("--classify", action="store_true", help="Use LLM for actionability classification")
    args = parser.parse_args()

    logger.info(f"Aggregating agenda items from chunks for {args.jurisdiction}")

    # Get chunks grouped by meeting
    chunks_by_meeting = get_chunks_by_meeting(args.jurisdiction)
    logger.info(f"Found {len(chunks_by_meeting)} meetings with chunks")

    # Apply limit
    meeting_ids = list(chunks_by_meeting.keys())
    if args.limit:
        meeting_ids = meeting_ids[:args.limit]

    total_items = 0
    meetings_processed = 0
    meetings_skipped = 0

    for meeting_id in meeting_ids:
        meeting_title = get_meeting_title(meeting_id)

        # Check if already has real items
        if not args.force and items_exist_for_meeting(meeting_id):
            logger.info(f"  Skipping {meeting_id[:50]}... (already has items)")
            meetings_skipped += 1
            continue

        chunks = chunks_by_meeting[meeting_id]
        items = aggregate_chunks_to_items(chunks)

        if not items:
            logger.info(f"  No items for {meeting_id[:50]}...")
            continue

        if args.classify:
            items = classify_actionability_batch(items, meeting_title)
        else:
            # Default all to actionable without LLM
            for item in items:
                item["actionable"] = True
                item["actionable_reason"] = "Extracted from agenda"
                item["project_type"] = "governance"

        if args.dry_run:
            logger.info(f"  Would create {len(items)} items for {meeting_title[:50]}...")
            for item in items[:5]:
                logger.info(f"    [{item['item_ref']}] {item['title'][:60]}...")
            if len(items) > 5:
                logger.info(f"    ... and {len(items) - 5} more")
        else:
            count = store_agenda_items(meeting_id, items)
            logger.info(f"  Stored {count} items for {meeting_title[:50]}...")

        total_items += len(items)
        meetings_processed += 1

    logger.info("=" * 50)
    logger.info(f"Meetings processed: {meetings_processed}")
    logger.info(f"Meetings skipped: {meetings_skipped}")
    logger.info(f"Total agenda items: {total_items}")
    if args.dry_run:
        logger.info("(dry run - no changes made)")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
