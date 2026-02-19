"""
Leverage point enrichment for legislation bills.

Generates actionable leverage points describing what residents can do
about each bill, using Claude Haiku for cost-effective batch enrichment.

Usage:
    civic-extract enrich-leverage --state CA
    civic-extract enrich-leverage --state CA --dry-run
    civic-extract enrich-leverage --state CA --limit 100
    civic-extract enrich-leverage --state US --batch-size 30
    civic-extract enrich-leverage --state CA --stats
"""

import argparse
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None


def add_enrich_leverage_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the enrich-leverage subcommand to the parser."""
    parser = subparsers.add_parser(
        "enrich-leverage",
        help="Generate leverage points for legislation bills",
        description="Use Claude to generate actionable leverage points for legislation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--state",
        default="CA",
        help="State code to enrich (default: CA)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of bills to enrich (default: all unenriched)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of bills per API call (default: 25)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be enriched without making changes",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current leverage point coverage statistics only",
    )


LEVERAGE_POINT_PROMPT = """For each bill below, generate a "leverage_point" — a concise sentence describing a specific action a local resident can take regarding this bill.

Rules:
- Be concrete and actionable: reference specific mechanisms like committee hearings, public comment periods, local implementation decisions, budget allocation choices, or contacting representatives
- For state bills: focus on what residents can do at the city/county level (attend planning meetings, testify at council, advocate for local implementation)
- For federal bills: focus on contacting representatives or participating in local implementation
- If the bill is purely procedural, honorary, or internal with NO clear citizen action opportunity, respond with null
- Keep each leverage_point to 1-2 sentences max
- Do not fabricate deadlines or hearing dates

Return JSON only, no markdown wrapping:
{{
  "results": [
    {{"bill_id": "...", "leverage_point": "..." or null}}
  ]
}}

Bills:
{bills_json}"""


def get_unenriched_bills(
    state: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch bills with summaries but no leverage_point."""
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    query = """
        SELECT bill_id, bill_number, bill_name, state, status, summary
        FROM legislation
        WHERE state = %s
          AND valid_to IS NULL
          AND leverage_point IS NULL
          AND summary IS NOT NULL
        ORDER BY bill_number
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, (state,))
    rows = cursor.fetchall()

    bills = []
    for row in rows:
        bills.append({
            "bill_id": row[0],
            "bill_number": row[1],
            "bill_name": row[2] or "",
            "state": row[3],
            "status": row[4] or "",
            "summary": row[5] or "",
        })

    cursor.close()
    conn.close()

    return bills


def get_leverage_stats(state: str) -> Dict[str, int]:
    """Get leverage point coverage statistics for a state."""
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(leverage_point) as enriched,
            COUNT(*) - COUNT(leverage_point) as unenriched,
            COUNT(CASE WHEN summary IS NOT NULL AND leverage_point IS NULL THEN 1 END) as candidates
        FROM legislation
        WHERE state = %s AND valid_to IS NULL
    """, (state,))

    row = cursor.fetchone()
    cursor.close()
    conn.close()

    return {
        "total": row[0],
        "enriched": row[1],
        "unenriched": row[2],
        "candidates": row[3],
    }


def enrich_batch(
    bills: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate leverage points for a batch of bills using Claude Haiku.

    Returns list of dicts with bill_id and leverage_point (or None).
    """
    if not ANTHROPIC_AVAILABLE:
        logger.error("Anthropic SDK not installed. Install with: pip install anthropic")
        return []

    bill_entries = json.dumps([{
        "bill_id": b["bill_id"],
        "bill_number": b["bill_number"],
        "title": b["bill_name"],
        "state": b["state"],
        "status": b["status"],
        "summary": b["summary"][:300],
    } for b in bills], indent=2)

    prompt = LEVERAGE_POINT_PROMPT.format(bills_json=bill_entries)

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": prompt,
            }],
        )

        text = response.content[0].text.strip()

        # Handle markdown-wrapped JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())
        results = result.get("results", [])

        # Filter to only non-null leverage points
        enriched = [
            r for r in results
            if r.get("leverage_point") is not None
        ]

        return enriched

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Raw response: {text[:500]}")
        return []
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return []


def run_enrich_leverage(args: argparse.Namespace) -> int:
    """Run the leverage point enrichment command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    state = args.state.upper()

    # Stats-only mode
    if args.stats:
        stats = get_leverage_stats(state)
        pct = (stats["enriched"] / stats["total"] * 100) if stats["total"] > 0 else 0
        logger.info(f"Leverage point coverage for {state}:")
        logger.info(f"  Total bills: {stats['total']}")
        logger.info(f"  Enriched:    {stats['enriched']} ({pct:.1f}%)")
        logger.info(f"  Unenriched:  {stats['unenriched']}")
        logger.info(f"  Candidates:  {stats['candidates']} (have summary, missing leverage_point)")
        return 0

    # Check requirements
    if not ANTHROPIC_AVAILABLE:
        logger.error("Anthropic SDK not installed. Run: pip install anthropic")
        return 1

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set")
        return 1

    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set")
        return 1

    # Fetch unenriched bills
    logger.info(f"Fetching unenriched {state} bills...")
    bills = get_unenriched_bills(state, limit=args.limit)
    logger.info(f"Found {len(bills)} bills to enrich")

    if not bills:
        logger.info("No bills to enrich")
        return 0

    if args.dry_run:
        logger.info(f"[DRY RUN] Would enrich {len(bills)} bills in batches of {args.batch_size}")
        for bill in bills[:5]:
            logger.info(f"  {bill['bill_number']}: {bill['bill_name'][:60]}")
        if len(bills) > 5:
            logger.info(f"  ... and {len(bills) - 5} more")
        return 0

    # Process in batches
    batch_size = args.batch_size
    total_enriched = 0
    total_skipped = 0
    all_updates = []

    num_batches = (len(bills) + batch_size - 1) // batch_size
    start_time = time.time()

    for i in range(0, len(bills), batch_size):
        batch = bills[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Batch {batch_num}/{num_batches} ({len(batch)} bills)...")

        enriched = enrich_batch(batch)

        if not enriched:
            logger.warning(f"Batch {batch_num} returned no results")
            total_skipped += len(batch)
            continue

        for r in enriched:
            all_updates.append({
                "bill_id": r["bill_id"],
                "leverage_point": r["leverage_point"],
            })

        enriched_count = len(enriched)
        skipped_count = len(batch) - enriched_count
        total_enriched += enriched_count
        total_skipped += skipped_count

        logger.info(f"  → {enriched_count} enriched, {skipped_count} skipped (null/procedural)")

        # Rate limiting: ~0.5s between batches
        if i + batch_size < len(bills):
            time.sleep(0.5)

    elapsed = time.time() - start_time

    # Update database
    if all_updates:
        logger.info(f"Updating {len(all_updates)} bills in database...")
        from civicos.storage.postgres_backend import PostgresBackend

        backend = PostgresBackend(os.environ["DATABASE_URL"])
        updated = backend.update_legislation_leverage_points(state, all_updates)
        logger.info(f"Updated {updated} bills")

    # Summary
    logger.info(f"\nEnrichment complete in {elapsed:.1f}s:")
    logger.info(f"  Enriched: {total_enriched}")
    logger.info(f"  Skipped:  {total_skipped} (null/procedural)")
    logger.info(f"  Total:    {total_enriched + total_skipped}")

    # Show updated stats
    stats = get_leverage_stats(state)
    pct = (stats["enriched"] / stats["total"] * 100) if stats["total"] > 0 else 0
    logger.info(f"\nCoverage for {state}: {stats['enriched']}/{stats['total']} ({pct:.1f}%)")

    return 0
