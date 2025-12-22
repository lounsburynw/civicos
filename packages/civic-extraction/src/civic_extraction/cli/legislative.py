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


def run_legislative(args: argparse.Namespace) -> int:
    """Run the legislative command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

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


def run_legislative_refresh(
    topic: str,
    state: str = "california",
    days_back: int = 90,
    limit: int = 20,
    output_dir: str = "data/legislative",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
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
    try:
        from civic_services.legislative.legislative_discovery import LegislativeDiscovery
    except ImportError:
        logger.error("civic-services package not available. Install it first.")
        return None

    if dry_run:
        logger.info("Dry-run mode - validating configuration...")
        logger.info(f"API Keys: LegiScan={api_keys['LEGISCAN_API_KEY']}, OpenAI={api_keys['OPENAI_API_KEY']}")
        logger.info(f"Would fetch {topic} legislation for {state} (last {days_back} days)")
        logger.info(f"Would analyze up to {limit} bills per topic with LLM filtering")

        topics = list(TOPIC_KEYWORDS.keys()) if topic == "all" else [topic]
        logger.info(f"Topics to process: {', '.join(topics)}")

        return {"dry_run": True, "status": "validated"}

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

            # Update context file
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

    # Summary
    logger.info("=" * 50)
    logger.info(f"Legislative Refresh Complete")
    logger.info(f"Topics processed: {', '.join(topics)}")
    logger.info(f"Total relevant bills identified: {total_bills_filtered}")
    logger.info(f"Output: {output_file}")
    logger.info("=" * 50)

    return {
        "state": state,
        "topics": topics,
        "total_bills_filtered": total_bills_filtered,
        "results_by_topic": results_by_topic,
        "output_file": str(output_file),
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
