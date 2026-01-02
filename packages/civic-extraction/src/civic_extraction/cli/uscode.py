"""
U.S. Code ingestion command for civic-extract CLI.

Parses U.S. Code XML files and stores sections to PostgreSQL for
RAG indexing via what_applies() queries.

Usage:
    civic-extract uscode --input data/uscode/usc42.xml --cloud
    civic-extract uscode --input data/uscode/usc42.xml --cloud --dry-run
    civic-extract uscode --input data/uscode/usc42.xml --stats
    civic-extract uscode --input data/uscode/ --cloud --batch
"""

import argparse
import logging
import os
from pathlib import Path
from typing import List

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


def add_uscode_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the uscode subcommand to the parser."""
    parser = subparsers.add_parser(
        "uscode",
        help="Ingest U.S. Code sections from XML to PostgreSQL",
        description="Parse U.S. Code XML files and store sections for RAG indexing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to U.S. Code XML file or directory containing XML files",
    )
    parser.add_argument(
        "--jurisdiction",
        default="federal-US",
        help="Jurisdiction identifier (default: federal-US)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count sections only - don't store to database",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store sections to cloud PostgreSQL (requires DATABASE_URL)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about the input file(s) only",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process all XML files in input directory (batch mode)",
    )
    parser.add_argument(
        "--chapter",
        help="Filter to specific chapter (e.g., '8' for housing in Title 42)",
    )


def run_uscode(args: argparse.Namespace) -> int:
    """Run the uscode command."""
    if hasattr(args, 'verbose') and args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate input path
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input path not found: {input_path}")
        return 1

    # Determine files to process
    if input_path.is_dir():
        if not args.batch:
            logger.error("Use --batch flag to process all XML files in directory")
            return 1
        xml_files = list(input_path.glob("*.xml"))
        if not xml_files:
            logger.error(f"No XML files found in {input_path}")
            return 1
        logger.info(f"Found {len(xml_files)} XML files in {input_path}")
    else:
        xml_files = [input_path]

    # Stats only mode
    if args.stats:
        return show_stats(xml_files, chapter_filter=args.chapter)

    # Cloud mode requires DATABASE_URL
    if args.cloud:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set. Required for cloud storage.")
            return 1

    # Process files
    return ingest_uscode(
        xml_files=xml_files,
        jurisdiction_id=args.jurisdiction,
        chapter_filter=args.chapter,
        dry_run=args.dry_run,
        cloud=args.cloud,
    )


def show_stats(xml_files: List[Path], chapter_filter: str = None) -> int:
    """Show statistics about U.S. Code XML files."""
    try:
        from civic_extraction.uscode import USCodeParser
    except ImportError:
        logger.error("civic_extraction.uscode not available")
        return 1

    total_sections = 0
    total_active = 0

    for xml_file in xml_files:
        logger.info(f"Analyzing {xml_file.name}...")
        parser = USCodeParser(xml_file)
        stats = parser.get_stats()

        logger.info(f"  Title: {stats['title_number']} - {stats['title_name']}")
        logger.info(f"  Total sections: {stats['total_sections']}")
        logger.info(f"  Active sections: {stats['active_sections']}")
        logger.info(f"  Chapters: {stats['chapters']}")

        if chapter_filter:
            # Count sections in specific chapter
            chapter_count = 0
            for section in parser.parse_sections(chapter_filter=chapter_filter):
                chapter_count += 1
            logger.info(f"  Sections in chapter {chapter_filter}: {chapter_count}")

        total_sections += stats['total_sections']
        total_active += stats['active_sections']

    logger.info("=" * 50)
    logger.info(f"TOTAL: {total_sections} sections ({total_active} active)")
    return 0


def ingest_uscode(
    xml_files: List[Path],
    jurisdiction_id: str = "federal-US",
    chapter_filter: str = None,
    dry_run: bool = False,
    cloud: bool = False,
) -> int:
    """
    Ingest U.S. Code sections from XML to PostgreSQL.

    Args:
        xml_files: List of XML files to process
        jurisdiction_id: Jurisdiction identifier (e.g., "federal-US")
        chapter_filter: Optional chapter filter
        dry_run: If True, validate only - don't store
        cloud: If True, store to cloud PostgreSQL

    Returns:
        0 on success, 1 on failure
    """
    try:
        from civic_extraction.uscode import USCodeParser
    except ImportError:
        logger.error("civic_extraction.uscode not available")
        return 1

    # Parse all sections first
    all_sections = []

    for xml_file in xml_files:
        logger.info(f"Parsing {xml_file.name}...")
        parser = USCodeParser(xml_file)

        for section in parser.parse_sections(chapter_filter=chapter_filter):
            # Skip sections without identifiers (notes, annotations, structural elements)
            # True sections have identifiers like "/us/usc/t42/s1437"
            if not section.identifier:
                continue
            all_sections.append(section.to_dict())

        logger.info(f"  Parsed {len(all_sections)} sections total")

    if not all_sections:
        logger.warning("No sections found to ingest")
        return 0

    logger.info(f"Total sections to ingest: {len(all_sections)}")

    # Dry run - just report
    if dry_run:
        logger.info("Dry-run mode - validating...")
        logger.info(f"Would ingest {len(all_sections)} sections to {jurisdiction_id}")
        if all_sections:
            sample = all_sections[0]
            logger.info(f"Sample: {sample['citation']} - {sample['heading'][:60]}...")
        return 0

    # Cloud storage
    if cloud:
        return store_to_cloud(all_sections, jurisdiction_id)

    # Local - just report (no local file storage for codified law)
    logger.info("No --cloud flag. Use --cloud to store to PostgreSQL.")
    logger.info(f"Parsed {len(all_sections)} sections (not stored)")
    return 0


def store_to_cloud(
    sections: List[dict],
    jurisdiction_id: str,
) -> int:
    """Store sections to cloud PostgreSQL using COPY optimization."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return 1

    try:
        from civic.storage.postgres_backend import PostgresBackend
        postgres_backend = PostgresBackend(database_url)
        logger.info("Connected to PostgreSQL")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return 1

    # Use COPY for bulk insert (10x faster than execute_values)
    # Send all sections at once - COPY handles it efficiently
    try:
        import time
        start = time.time()
        stored = postgres_backend.store_codified_law(
            jurisdiction_id=jurisdiction_id,
            sections=sections,
            use_copy=True,  # 10x faster bulk insert
        )
        elapsed = time.time() - start
        logger.info(f"Stored {stored} sections in {elapsed:.1f}s using COPY")
    except Exception as e:
        logger.error(f"Error storing sections: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Report final stats
    try:
        total_in_db = postgres_backend.get_codified_law_count(jurisdiction_id)
        logger.info("=" * 50)
        logger.info("U.S. Code Ingestion Complete")
        logger.info("=" * 50)
        logger.info(f"Sections ingested this run: {stored}")
        logger.info(f"Total sections in PostgreSQL for {jurisdiction_id}: {total_in_db}")
        logger.info("=" * 50)
    except Exception as e:
        logger.warning(f"Could not get final stats: {e}")

    return 0
