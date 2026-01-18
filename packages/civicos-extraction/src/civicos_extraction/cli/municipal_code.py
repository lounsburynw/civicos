"""
Municipal code fetch command for civic-extract CLI.

Fetches municipal code from Municode API and stores to Postgres.

Usage:
    civic-extract municipal-code --jurisdiction city-san-rafael
    civic-extract municipal-code --jurisdiction city-san-rafael --cloud
    civic-extract municipal-code --jurisdiction city-san-rafael --dry-run
    civic-extract municipal-code --jurisdiction city-san-rafael --stats --cloud
"""

import argparse
import json
import logging
import os
from dataclasses import asdict
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


def add_municipal_code_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the municipal-code subcommand to the parser."""
    parser = subparsers.add_parser(
        "municipal-code",
        help="Fetch municipal code from Municode API",
        description="Fetch and store municipal code sections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store to cloud Postgres instead of local JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration only - don't fetch",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only - don't fetch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum sections to fetch (for testing)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/municipal_code",
        help="Directory for local output files (default: data/municipal_code)",
    )


def run_municipal_code(args: argparse.Namespace) -> int:
    """Run the municipal-code command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    jurisdiction_id = args.jurisdiction
    cloud_mode = args.cloud or os.environ.get("DATABASE_URL")

    logger.info(f"Municipal code command for {jurisdiction_id}")
    logger.info(f"Cloud mode: {bool(cloud_mode)}")

    # Stats mode - show current counts
    if args.stats:
        return show_stats(jurisdiction_id, cloud_mode)

    # Dry-run mode - validate configuration
    if args.dry_run:
        return validate_config(jurisdiction_id)

    # Normal mode - fetch and store
    return fetch_and_store_municipal_code(
        jurisdiction_id=jurisdiction_id,
        cloud=cloud_mode,
        output_dir=args.output_dir,
        limit=args.limit,
    )


def show_stats(jurisdiction_id: str, cloud: bool) -> int:
    """Show statistics for municipal code in storage."""
    if cloud:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            return 1

        try:
            from civicos.storage.postgres_backend import PostgresBackend
            backend = PostgresBackend(database_url)
            count = backend.get_municipal_code_count(jurisdiction_id)

            logger.info("=" * 50)
            logger.info(f"Municipal code for {jurisdiction_id}")
            logger.info(f"Total sections: {count}")
            logger.info("=" * 50)
            return 0
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return 1
    else:
        logger.info("Local stats not implemented - use --cloud for cloud storage stats")
        return 0


def validate_config(jurisdiction_id: str) -> int:
    """Validate configuration for municipal code fetch."""
    logger.info("=" * 50)
    logger.info("Municipal Code Dry Run")
    logger.info("=" * 50)

    # Check Municode availability
    try:
        from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
        corpus = MunicipalCodeCorpus.for_jurisdiction(jurisdiction_id)
        logger.info(f"Jurisdiction: {jurisdiction_id}")
        logger.info(f"Municode corpus: Initialized successfully")

        # Check if jurisdiction is in the known map
        if jurisdiction_id in corpus.JURISDICTION_MAP:
            jur_info = corpus.JURISDICTION_MAP[jurisdiction_id]
            logger.info(f"  State: {jur_info.get('state')}")
            logger.info(f"  Name: {jur_info.get('name')}")
        else:
            logger.warning(f"  Jurisdiction not in known map - will attempt auto-discovery")

        logger.info("Configuration: VALID")
    except Exception as e:
        logger.error(f"Failed to initialize Municode corpus: {e}")
        return 1

    # Check cloud configuration
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        logger.info(f"Cloud storage: Available (DATABASE_URL set)")
    else:
        logger.info("Cloud storage: Not configured (DATABASE_URL not set)")

    logger.info("=" * 50)
    return 0


def fetch_and_store_municipal_code(
    jurisdiction_id: str,
    cloud: bool,
    output_dir: str,
    limit: Optional[int] = None,
) -> int:
    """Fetch municipal code from Municode and store it."""
    import time
    start_time = time.time()

    # Initialize corpus
    try:
        from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus
        corpus = MunicipalCodeCorpus.for_jurisdiction(jurisdiction_id)
    except Exception as e:
        logger.error(f"Failed to initialize Municode corpus: {e}")
        return 1

    logger.info(f"Fetching municipal code from Municode API...")

    # Stream sections from Municode
    sections: List[Dict[str, Any]] = []
    try:
        for section in corpus.stream_sections():
            section_dict = asdict(section)
            section_dict['source'] = 'municode'
            sections.append(section_dict)

            if len(sections) % 100 == 0:
                logger.info(f"  Fetched {len(sections)} sections...")

            if limit and len(sections) >= limit:
                logger.info(f"Reached limit of {limit} sections")
                break

    except Exception as e:
        logger.error(f"Error fetching sections: {e}")
        if not sections:
            return 1
        logger.warning(f"Continuing with {len(sections)} sections fetched before error")

    if not sections:
        logger.warning("No sections fetched")
        return 1

    duration_seconds = int(time.time() - start_time)
    logger.info(f"Fetched {len(sections)} sections in {duration_seconds}s")

    # Store to cloud if requested
    if cloud:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            return 1

        try:
            from civicos.storage.postgres_backend import PostgresBackend
            backend = PostgresBackend(database_url)

            logger.info(f"Storing {len(sections)} sections to Postgres...")
            count = backend.store_municipal_code(jurisdiction_id, sections)

            logger.info("=" * 50)
            logger.info(f"Municipal Code Fetch Complete for {jurisdiction_id}")
            logger.info(f"Sections stored: {count}")
            logger.info(f"Duration: {duration_seconds}s")
            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"Failed to store municipal code: {e}")
            return 1
    else:
        # Store locally as JSON
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"municipal_code_{jurisdiction_id.replace('-', '_')}.json"

        output_data = {
            "jurisdiction_id": jurisdiction_id,
            "fetched_at": datetime.now().isoformat(),
            "count": len(sections),
            "sections": sections,
        }

        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("=" * 50)
        logger.info(f"Municipal Code Fetch Complete for {jurisdiction_id}")
        logger.info(f"Sections saved: {len(sections)}")
        logger.info(f"Output file: {output_file}")
        logger.info(f"Duration: {duration_seconds}s")
        logger.info("=" * 50)

    return 0
