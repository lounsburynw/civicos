"""
Legislative refresh command for civic-extract CLI.

Fetches and filters legislative bills from LegiScan API using LLM-assisted
relevance filtering to identify locally-actionable legislation.

Usage:
    civic-extract legislative --topic housing
    civic-extract legislative --topic all --schedule
    civic-extract legislative --topic housing --dry-run
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

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


# Topic keywords for discovery (matches legiscan_client.py)
TOPIC_KEYWORDS = {
    "housing": ["housing", "affordable housing", "zoning", "density", "ADU", "duplex", "RHNA"],
    "transportation": ["transportation", "transit", "bicycle", "pedestrian", "VMT", "complete streets"],
    "environment": ["climate", "environment", "sustainability", "clean energy", "emissions", "conservation"],
    "budget": ["budget", "tax", "revenue", "bond", "fiscal", "appropriation"],
    "education": ["education", "school", "college", "student", "teacher", "curriculum"],
}


@dataclass
class LegislativeCheckpoint:
    """Checkpoint for legislative refresh progress."""

    topic: str
    state: str
    bills_fetched: int
    bills_filtered: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LegislativeCheckpoint":
        return cls(**data)


def add_legislative_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the legislative subcommand to the parser."""
    parser = subparsers.add_parser(
        "legislative",
        help="Refresh legislative context from LegiScan API",
        description="Fetch and filter legislative bills using LLM-assisted relevance filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--topic",
        required=True,
        choices=["housing", "transportation", "environment", "budget", "education", "all"],
        help="Topic to discover (or 'all' for all topics)",
    )
    parser.add_argument(
        "--state",
        default="california",
        help="State to search (default: california)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=90,
        help="Days back to search (default: 90)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum bills to analyze with LLM per topic (default: 20)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/legislative",
        help="Directory for output files (default: data/legislative)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration only - don't fetch bills",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (weekly on Sunday at 6am) instead of once",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory for checkpoint files (default: data/checkpoints)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store legislation to cloud Postgres instead of local JSON files",
    )
    parser.add_argument(
        "--migrate-json",
        action="store_true",
        help="Migrate existing JSON legislation files to cloud Postgres (requires --cloud)",
    )
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="Bulk ingest ALL bills from LegiScan master list (requires --cloud). Gets ~2,800 CA bills in 1 API call.",
    )


def run_legislative(args: argparse.Namespace) -> int:
    """Run the legislative command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle JSON migration mode
    if args.migrate_json:
        if not args.cloud:
            logger.error("--migrate-json requires --cloud flag")
            return 1
        return migrate_json_to_cloud(
            state=args.state,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )

    # Handle bulk ingestion mode
    if args.bulk:
        if not args.cloud:
            logger.error("--bulk requires --cloud flag")
            return 1
        return bulk_ingest_legislation(
            state=args.state,
            dry_run=args.dry_run,
        )

    if args.schedule:
        run_scheduled(
            topic=args.topic,
            state=args.state,
            days_back=args.days_back,
            limit=args.limit,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        result = run_legislative_refresh(
            topic=args.topic,
            state=args.state,
            days_back=args.days_back,
            limit=args.limit,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
            cloud=args.cloud,
        )

        if result is None and not args.dry_run:
            return 1

        return 0


def check_api_keys() -> Dict[str, bool]:
    """Check for required API keys."""
    return {
        "LEGISCAN_API_KEY": bool(os.getenv("LEGISCAN_API_KEY")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
    }


def checkpoint_path_for_legislative(
    topic: str, state: str, checkpoint_dir: str
) -> Path:
    """Get checkpoint file path for legislative refresh."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"legislative_{state}_{topic}.json"


def save_checkpoint(checkpoint: LegislativeCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[LegislativeCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return LegislativeCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def bulk_ingest_legislation(
    state: str = "california",
    dry_run: bool = False,
) -> int:
    """
    Bulk ingest ALL bills from LegiScan master list to PostgreSQL.

    Uses getMasterList API to fetch all bills for current session in 1 API call.
    This provides ~2,800 CA bills for RAG indexing.

    Args:
        state: State to ingest (default: california)
        dry_run: If True, validate only - don't store

    Returns:
        0 on success, 1 on failure
    """
    logger.info(f"Bulk ingesting {state} legislation from LegiScan master list")

    # Check for required keys
    if not os.getenv("LEGISCAN_API_KEY"):
        logger.error("LEGISCAN_API_KEY not set. Required for bulk ingestion.")
        return 1

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Required for cloud storage.")
        return 1

    # Import LegiScan client from local clients module
    from civic_extraction.clients.legiscan import LegiScanClient

    # Fetch master list
    client = LegiScanClient()
    # Map state names to LegiScan codes
    state_map = {
        "california": "CA",
        "federal": "US",
        "congress": "US",
    }
    state_code = state_map.get(state.lower(), state.upper())

    logger.info(f"Fetching master list for {state_code}...")
    bills = client.get_master_list(state_code)

    if not bills:
        logger.error("No bills returned from master list")
        return 1

    logger.info(f"Retrieved {len(bills)} bills from LegiScan")

    if dry_run:
        logger.info("Dry-run mode - validating...")
        logger.info(f"Would ingest {len(bills)} bills to PostgreSQL")
        # Show sample
        if bills:
            sample = bills[0]
            logger.info(f"Sample bill: {sample.get('number')} - {sample.get('title', '')[:60]}...")
        return 0

    # Connect to PostgreSQL
    try:
        from civic.storage.postgres_backend import PostgresBackend
        postgres_backend = PostgresBackend(database_url)
        logger.info("Connected to PostgreSQL")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return 1

    # Transform bills for storage
    # Master list format differs from search results
    bills_for_storage = []
    for bill in bills:
        bill_number = bill.get('number', '')
        normalized_id = f"{state_code.lower()}-{bill_number.lower().replace(' ', '')}"

        bills_for_storage.append({
            'bill_id': normalized_id,
            'bill_number': bill_number,
            'bill_name': bill.get('title', ''),
            'summary': bill.get('description', ''),
            'status': str(bill.get('status', '')),
            'official_url': bill.get('url', ''),
            'legiscan_id': bill.get('bill_id'),
            # Master list doesn't include these, but we track them
            'last_action': bill.get('last_action', ''),
            'last_action_date': bill.get('last_action_date'),
            'status_date': bill.get('status_date'),
        })

    # Store in batches for progress reporting
    batch_size = 500
    total_stored = 0

    for i in range(0, len(bills_for_storage), batch_size):
        batch = bills_for_storage[i:i + batch_size]
        try:
            stored = postgres_backend.store_legislation(
                state=state_code,
                bills=batch,
            )
            total_stored += stored
            logger.info(f"Stored batch {i // batch_size + 1}: {stored} bills (total: {total_stored})")
        except Exception as e:
            logger.error(f"Error storing batch: {e}")

    # Report final stats
    try:
        total_in_db = postgres_backend.get_legislation_count(state_code)
        logger.info("=" * 50)
        logger.info("Bulk Ingestion Complete")
        logger.info("=" * 50)
        logger.info(f"Bills ingested this run: {total_stored}")
        logger.info(f"Total bills in PostgreSQL for {state_code}: {total_in_db}")
        logger.info(f"LegiScan API queries used: {client.query_count}")
        logger.info("=" * 50)
    except Exception as e:
        logger.warning(f"Could not get final stats: {e}")

    return 0


def migrate_json_to_cloud(
    state: str = "california",
    output_dir: str = "data/legislation",
    dry_run: bool = False,
) -> int:
    """
    Migrate existing JSON legislation files to PostgreSQL cloud storage.

    Reads JSON files from data/legislation/state/{state}/ and stores to Postgres.

    Args:
        state: State to migrate (default: california)
        output_dir: Base directory for legislation data
        dry_run: If True, validate only - don't store

    Returns:
        0 on success, 1 on failure
    """
    logger.info(f"Migrating {state} legislation JSON to PostgreSQL")

    # Check for DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Required for cloud storage.")
        return 1

    # Find JSON files
    state_dir = Path(output_dir) / "state" / state
    if not state_dir.exists():
        logger.error(f"State directory not found: {state_dir}")
        return 1

    # Get topic JSON files (exclude verification/audit files)
    topic_files = [
        f for f in state_dir.glob("*.json")
        if f.stem in TOPIC_KEYWORDS.keys()
    ]

    if not topic_files:
        logger.error(f"No topic JSON files found in {state_dir}")
        return 1

    logger.info(f"Found {len(topic_files)} topic files: {[f.stem for f in topic_files]}")

    if dry_run:
        logger.info("Dry-run mode - validating files...")
        total_bills = 0
        for topic_file in topic_files:
            try:
                with open(topic_file) as f:
                    data = json.load(f)
                bills = data.get("state_legislation", {})
                total_bills += len(bills)
                logger.info(f"  {topic_file.stem}: {len(bills)} bills")
            except Exception as e:
                logger.error(f"  {topic_file.stem}: Error reading - {e}")
        logger.info(f"Total bills to migrate: {total_bills}")
        return 0

    # Connect to PostgreSQL
    try:
        from civic.storage.postgres_backend import PostgresBackend
        postgres_backend = PostgresBackend(database_url)
        logger.info("Connected to PostgreSQL")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return 1

    # Migrate each topic file
    state_code = "CA" if state.lower() == "california" else state.upper()
    total_migrated = 0

    for topic_file in topic_files:
        topic = topic_file.stem
        logger.info(f"Migrating {topic} legislation...")

        try:
            with open(topic_file) as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading {topic_file}: {e}")
            continue

        # Extract bills from state_legislation dict
        state_legislation = data.get("state_legislation", {})
        if not state_legislation:
            logger.warning(f"No state_legislation in {topic_file}")
            continue

        # Convert dict format to list format for storage
        bills_for_storage = []
        for bill_key, bill_data in state_legislation.items():
            bill = dict(bill_data)
            bill['bill_id'] = bill_key  # e.g., "ca-sb9"
            bills_for_storage.append(bill)

        try:
            stored = postgres_backend.store_legislation(
                state=state_code,
                bills=bills_for_storage,
                topic=topic,
            )
            logger.info(f"  Stored {stored} {topic} bills")
            total_migrated += stored
        except Exception as e:
            logger.error(f"Error storing {topic} legislation: {e}")

    # Report final stats
    try:
        total_in_db = postgres_backend.get_legislation_count(state_code)
        logger.info("=" * 50)
        logger.info(f"Migration Complete")
        logger.info(f"Bills migrated this run: {total_migrated}")
        logger.info(f"Total bills in PostgreSQL for {state_code}: {total_in_db}")
        logger.info("=" * 50)
    except Exception as e:
        logger.warning(f"Could not get final stats: {e}")

    return 0


def run_legislative_refresh(
    topic: str,
    state: str = "california",
    days_back: int = 90,
    limit: int = 20,
    output_dir: str = "data/legislative",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    cloud: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Run legislative refresh for a topic.

    Args:
        topic: Topic to discover (or 'all' for all topics)
        state: State to search
        days_back: Days back to search
        limit: Maximum bills to analyze with LLM per topic
        output_dir: Directory for output files
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, validate only - don't fetch bills
        cloud: If True, store to Postgres instead of local JSON files

    Returns:
        Result dict with counts if successful, None if failed
    """
    logger.info(f"Starting legislative refresh for topic: {topic}, state: {state}")

    # Check API keys
    api_keys = check_api_keys()
    if not api_keys["LEGISCAN_API_KEY"]:
        logger.error(
            "LEGISCAN_API_KEY not set. Register at https://legiscan.com/ for free API access (30,000 queries/month)"
        )
        return None

    if not api_keys["OPENAI_API_KEY"]:
        logger.warning(
            "OPENAI_API_KEY not set. LLM filtering will be disabled - bills will not be filtered for local relevance."
        )

    # Import services here to avoid import errors if civic-services not installed
    # Import from local legislative module
    from civic_extraction.legislative.legislative_discovery import LegislativeDiscovery

    # Check cloud storage requirements
    postgres_backend = None
    if cloud:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set. Required for --cloud mode.")
            return None
        try:
            from civic.storage.postgres_backend import PostgresBackend
            postgres_backend = PostgresBackend(database_url)
            logger.info("Cloud storage: PostgreSQL connected")
        except ImportError:
            logger.error("civic package not available for cloud storage.")
            return None
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return None

    if dry_run:
        logger.info("Dry-run mode - validating configuration...")
        has_legiscan = "yes" if api_keys.get("LEGISCAN_API_KEY") else "no"
        has_openai = "yes" if api_keys.get("OPENAI_API_KEY") else "no"
        logger.info(f"API Keys configured: LegiScan={has_legiscan}, OpenAI={has_openai}")
        logger.info(f"Would fetch {topic} legislation for {state} (last {days_back} days)")
        logger.info(f"Would analyze up to {limit} bills per topic with LLM filtering")
        logger.info(f"Storage mode: {'cloud (PostgreSQL)' if cloud else 'local (JSON files)'}")

        topics = list(TOPIC_KEYWORDS.keys()) if topic == "all" else [topic]
        logger.info(f"Topics to process: {', '.join(topics)}")

        return {"dry_run": True, "status": "validated", "cloud": cloud}

    # Initialize discovery
    discovery = LegislativeDiscovery()

    # Handle "all" topics
    topics = list(TOPIC_KEYWORDS.keys()) if topic == "all" else [topic]

    total_bills_fetched = 0
    total_bills_filtered = 0
    results_by_topic: Dict[str, Any] = {}

    for current_topic in topics:
        logger.info("=" * 50)
        logger.info(f"Discovering {current_topic.upper()} legislation")
        logger.info("=" * 50)

        # Discover relevant bills
        try:
            relevant_bills = discovery.discover_topic(
                topic=current_topic,
                state=state,
                days_back=days_back,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error discovering {current_topic} legislation: {e}")
            relevant_bills = []

        if relevant_bills:
            logger.info(f"Found {len(relevant_bills)} relevant bills for {current_topic}")
            for bill in relevant_bills:
                logger.info(f"  - {bill.get('bill_number')}: {bill.get('leverage_point', 'TBD')}")

            if cloud and postgres_backend:
                # Store to PostgreSQL cloud database
                try:
                    # Convert state name to state code for storage
                    state_code = "CA" if state.lower() == "california" else state.upper()

                    # Transform bills for storage
                    bills_for_storage = []
                    for bill in relevant_bills:
                        # Normalize bill data structure
                        bill_data = dict(bill)

                        # Generate bill_id from bill_number (e.g., "SB 838" -> "ca-sb838")
                        # LegiScan may use 'bill_id' for its numeric ID, so we need to generate ours
                        bill_number = bill_data.get('bill_number', '')
                        if bill_number:
                            # Normalize: "SB 838" -> "ca-sb838"
                            normalized = bill_number.lower().replace(' ', '').replace('.', '')
                            bill_data['bill_id'] = f"{state_code.lower()}-{normalized}"
                        elif 'bill_id' not in bill_data:
                            # Fallback to legiscan_id if no bill_number
                            legiscan_id = bill_data.get('legiscan_id') or bill_data.get('_legiscan_id')
                            if legiscan_id:
                                bill_data['bill_id'] = f"{state_code.lower()}-legiscan-{legiscan_id}"
                            else:
                                continue  # Skip bills without identifiers

                        # Preserve legiscan_id separately
                        if 'bill_id' in bill_data and str(bill_data.get('bill_id', '')).isdigit():
                            bill_data['legiscan_id'] = bill_data['bill_id']
                            bill_number = bill_data.get('bill_number', '')
                            if bill_number:
                                normalized = bill_number.lower().replace(' ', '').replace('.', '')
                                bill_data['bill_id'] = f"{state_code.lower()}-{normalized}"

                        bills_for_storage.append(bill_data)

                    stored = postgres_backend.store_legislation(
                        state=state_code,
                        bills=bills_for_storage,
                        topic=current_topic,
                    )
                    logger.info(f"Stored {stored} bills to PostgreSQL")
                except Exception as e:
                    logger.error(f"Error storing legislation to PostgreSQL: {e}")
            else:
                # Update local JSON context file
                try:
                    discovery.update_legislative_context(
                        topic=current_topic,
                        relevant_bills=relevant_bills,
                        state=state,
                        dry_run=False,
                    )
                except Exception as e:
                    logger.error(f"Error updating legislative context: {e}")

            total_bills_filtered += len(relevant_bills)
        else:
            logger.info(f"No relevant bills found for {current_topic}")

        # Track counts (approximate since we don't have pre-filter count)
        results_by_topic[current_topic] = {
            "bills_filtered": len(relevant_bills) if relevant_bills else 0,
        }

        # Save checkpoint for this topic
        checkpoint = LegislativeCheckpoint(
            topic=current_topic,
            state=state,
            bills_fetched=len(relevant_bills) if relevant_bills else 0,
            bills_filtered=len(relevant_bills) if relevant_bills else 0,
            timestamp=datetime.now().isoformat(),
        )
        checkpoint_path = checkpoint_path_for_legislative(current_topic, state, checkpoint_dir)
        save_checkpoint(checkpoint, checkpoint_path)

    # Get API usage stats
    try:
        stats = discovery.legiscan.get_query_stats()
        logger.info("=" * 50)
        logger.info("LegiScan API Usage")
        logger.info("=" * 50)
        logger.info(f"Queries this session: {stats['queries_this_session']}")
        logger.info(f"Monthly limit: {stats['monthly_limit']}")
        logger.info(f"Estimated remaining: {stats['estimated_remaining']}")
    except Exception as e:
        logger.warning(f"Could not get API stats: {e}")

    # Save combined output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"legislative_refresh_{state}_{datetime.now().strftime('%Y%m%d')}.json"

    output_data = {
        "state": state,
        "topics": topics,
        "days_back": days_back,
        "refreshed_at": datetime.now().isoformat(),
        "total_bills_filtered": total_bills_filtered,
        "results_by_topic": results_by_topic,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    logger.info(f"Saved refresh summary to {output_file}")

    # Index legislation to ChromaDB for semantic search
    if total_bills_filtered > 0:
        logger.info("=" * 50)
        logger.info("Indexing legislation to ChromaDB")
        logger.info("=" * 50)
        try:
            from civic._internal.meetings.embeddings import CivicEmbeddings

            # Use a generic jurisdiction for state-level legislation
            embedder = CivicEmbeddings(jurisdiction_id="state-california")
            collection = embedder.build_legislation_index(state=state, topics=topics)
            logger.info(f"Indexed {collection.count()} bills to ChromaDB")
        except ImportError:
            logger.warning("civic package not available - skipping vector indexing")
        except Exception as e:
            logger.error(f"Error indexing legislation: {e}")

    # Report cloud storage stats if using cloud mode
    if cloud and postgres_backend:
        try:
            state_code = "CA" if state.lower() == "california" else state.upper()
            total_in_db = postgres_backend.get_legislation_count(state_code)
            logger.info("=" * 50)
            logger.info("Cloud Storage Summary")
            logger.info("=" * 50)
            logger.info(f"Total bills in PostgreSQL for {state_code}: {total_in_db}")
        except Exception as e:
            logger.warning(f"Could not get cloud storage stats: {e}")

    # Summary
    logger.info("=" * 50)
    logger.info(f"Legislative Refresh Complete")
    logger.info(f"Topics processed: {', '.join(topics)}")
    logger.info(f"Total relevant bills identified: {total_bills_filtered}")
    logger.info(f"Storage: {'PostgreSQL (cloud)' if cloud else 'JSON files (local)'}")
    logger.info(f"Output: {output_file}")
    logger.info("=" * 50)

    return {
        "state": state,
        "topics": topics,
        "total_bills_filtered": total_bills_filtered,
        "results_by_topic": results_by_topic,
        "output_file": str(output_file),
        "cloud": cloud,
    }


def run_scheduled(
    topic: str,
    state: str = "california",
    days_back: int = 90,
    limit: int = 20,
    output_dir: str = "data/legislative",
    checkpoint_dir: str = "data/checkpoints",
) -> None:
    """
    Run legislative refresh on a schedule.

    Uses the schedule library to run weekly on Sunday at 6am.
    Weekly is appropriate since legislation moves slowly.
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting legislative scheduler for topic: {topic}, state: {state}")
    logger.info("Will run weekly on Sunday at 06:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled legislative refresh starting")
        run_legislative_refresh(
            topic=topic,
            state=state,
            days_back=days_back,
            limit=limit,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for Sunday at 6am
    schedule.every().sunday.at("06:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial legislative refresh...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute
