"""
Topic classification command for civic-extract CLI.

Classifies untagged legislation bills using LLM-based topic classification.
Uses OpenAI gpt-4o-mini for cost-effective batch classification.

Usage:
    civic-extract classify-topics --state CA
    civic-extract classify-topics --state CA --dry-run
    civic-extract classify-topics --state CA --limit 100
    civic-extract classify-topics --state CA --batch-size 30
"""

import argparse
import json
import logging
import os
from typing import Any, Dict, List, Optional

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Check for OpenAI availability
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

# Topic definitions with keywords for classification guidance
TOPIC_DEFINITIONS = {
    "housing": "Zoning, affordable housing, density, ADU, RHNA, residential regulations, rent control, tenant rights, homelessness",
    "transportation": "Transit, pedestrian, bicycle, VMT, complete streets, traffic, parking, public transportation, roads",
    "environment": "Climate, sustainability, clean energy, emissions, conservation, air quality, water, waste, environmental protection",
    "budget": "Tax, appropriation, fiscal, revenue, bonds, spending, fees, assessments, financial regulations",
    "education": "Schools, curriculum, teachers, students, college, workforce development, childcare, early education",
    "public_safety": "Police, fire, emergency services, crime, disaster preparedness, public health emergencies",
    "healthcare": "Medical services, insurance, mental health, substance abuse, public health, hospitals",
    "labor": "Employment, wages, workers rights, unions, workplace safety, unemployment",
    "governance": "Elections, voting, government operations, transparency, public records, ethics",
}


def add_classify_topics_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the classify-topics subcommand to the parser."""
    parser = subparsers.add_parser(
        "classify-topics",
        help="Classify untagged legislation bills by topic",
        description="Use LLM to classify legislation bills into predefined topic categories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--state",
        default="CA",
        help="State code to classify (default: CA)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of bills to classify (default: all untagged)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of bills per LLM API call (default: 25)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be classified without making changes",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current topic distribution statistics only",
    )


def get_untagged_bills(
    state: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch bills without topic tags from PostgreSQL.

    Args:
        state: State code (e.g., "CA")
        limit: Maximum number of bills to return

    Returns:
        List of bill dicts with bill_id, bill_number, bill_name, summary
    """
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    query = """
        SELECT bill_id, bill_number, bill_name, summary
        FROM legislation
        WHERE state = %s
          AND valid_to IS NULL
          AND topic IS NULL
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
            "summary": row[3] or "",
        })

    cursor.close()
    conn.close()

    return bills


def get_topic_stats(state: str) -> Dict[str, int]:
    """Get current topic distribution for a state."""
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COALESCE(topic, 'untagged') as topic,
            COUNT(*) as count
        FROM legislation
        WHERE state = %s AND valid_to IS NULL
        GROUP BY topic
        ORDER BY count DESC
    """, (state,))

    stats = {}
    for row in cursor.fetchall():
        stats[row[0]] = row[1]

    cursor.close()
    conn.close()

    return stats


def classify_bills_batch(
    bills: List[Dict[str, Any]],
    topics: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Classify a batch of bills using OpenAI gpt-4o-mini.

    Args:
        bills: List of bill dicts with bill_id, bill_number, bill_name, summary
        topics: Dict of topic -> description for classification

    Returns:
        List of dicts with bill_id and assigned topic
    """
    if not OPENAI_AVAILABLE:
        logger.error("OpenAI not installed. Install with: pip install openai")
        return []

    topic_list = "\n".join([f"- {k}: {v}" for k, v in topics.items()])

    # Build bill list for prompt
    bill_entries = []
    for b in bills:
        name = b.get("bill_name", "") or ""
        summary = b.get("summary", "") or ""
        # Truncate summary to save tokens
        if len(summary) > 200:
            summary = summary[:200] + "..."
        bill_entries.append({
            "bill_id": b["bill_id"],
            "bill_number": b.get("bill_number", ""),
            "title": name,
            "summary": summary,
        })

    prompt = f"""Classify these California legislation bills into ONE primary topic category.

Available topic categories:
{topic_list}
- other: Bills that don't fit any of the above categories

For each bill, analyze the title and summary to determine the most relevant topic.
If a bill clearly doesn't fit any topic, classify as "other".

Return a JSON object with a "classifications" array containing:
- bill_id: The original bill_id
- topic: The assigned topic category (lowercase)
- confidence: Your confidence level (0.0-1.0)

Bills to classify:
{json.dumps(bill_entries, indent=2)}
"""

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert in California state legislation. Classify bills into topic categories based on their title and summary. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        # Handle various response formats
        classifications = result.get("classifications", [])
        if not classifications and isinstance(result, list):
            classifications = result

        return classifications

    except Exception as e:
        logger.error(f"LLM classification failed: {e}")
        return []


def run_classify_topics(args: argparse.Namespace) -> int:
    """Run the topic classification command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    state = args.state.upper()

    # Stats-only mode
    if args.stats:
        logger.info(f"Topic distribution for {state}:")
        stats = get_topic_stats(state)
        total = sum(stats.values())
        for topic, count in sorted(stats.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total > 0 else 0
            logger.info(f"  {topic}: {count} ({pct:.1f}%)")
        logger.info(f"Total: {total} bills")
        return 0

    # Check for required keys
    if not OPENAI_AVAILABLE:
        logger.error("OpenAI package not installed. Run: pip install openai")
        return 1

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set")
        return 1

    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set")
        return 1

    # Fetch untagged bills
    logger.info(f"Fetching untagged {state} bills...")
    bills = get_untagged_bills(state, limit=args.limit)
    logger.info(f"Found {len(bills)} untagged bills")

    if not bills:
        logger.info("No untagged bills to classify")
        return 0

    if args.dry_run:
        logger.info(f"[DRY RUN] Would classify {len(bills)} bills in batches of {args.batch_size}")
        # Show sample
        for bill in bills[:5]:
            logger.info(f"  {bill['bill_number']}: {bill['bill_name'][:60]}...")
        if len(bills) > 5:
            logger.info(f"  ... and {len(bills) - 5} more")
        return 0

    # Process in batches
    batch_size = args.batch_size
    total_classified = 0
    all_updates = []

    for i in range(0, len(bills), batch_size):
        batch = bills[i:i + batch_size]
        logger.info(f"Classifying batch {i // batch_size + 1}/{(len(bills) + batch_size - 1) // batch_size} ({len(batch)} bills)...")

        classifications = classify_bills_batch(batch, TOPIC_DEFINITIONS)

        if not classifications:
            logger.warning(f"Failed to classify batch {i // batch_size + 1}")
            continue

        for c in classifications:
            bill_id = c.get("bill_id")
            topic = c.get("topic", "").lower()
            confidence = c.get("confidence", 0)

            # Validate topic
            valid_topics = set(TOPIC_DEFINITIONS.keys()) | {"other"}
            if topic not in valid_topics:
                logger.warning(f"Invalid topic '{topic}' for {bill_id}, defaulting to 'other'")
                topic = "other"

            all_updates.append({
                "bill_id": bill_id,
                "topic": topic,
            })
            total_classified += 1

            logger.debug(f"  {bill_id}: {topic} (confidence: {confidence:.2f})")

    # Update database
    if all_updates:
        logger.info(f"Updating {len(all_updates)} bills in database...")
        from civicos.storage.postgres_backend import PostgresBackend

        backend = PostgresBackend(os.environ["DATABASE_URL"])
        updated = backend.update_legislation_topics(state, all_updates)
        logger.info(f"Updated {updated} bills")

    # Show final stats
    logger.info("\nFinal topic distribution:")
    stats = get_topic_stats(state)
    total = sum(stats.values())
    for topic, count in sorted(stats.items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        logger.info(f"  {topic}: {count} ({pct:.1f}%)")

    return 0
