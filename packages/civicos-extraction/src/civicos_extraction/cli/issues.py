"""
Unified 311 issues command for civic-extract CLI.

Fetches operational issues from 311 providers (SeeClickFix, etc.) and stores
them in the Civic database. Supports multiple providers with a unified interface.

Usage:
    civic-extract issues --jurisdiction city-san-rafael
    civic-extract issues --jurisdiction city-san-rafael --provider seeclickfix
    civic-extract issues --jurisdiction city-san-rafael --cloud
    civic-extract issues --jurisdiction city-san-rafael --dry-run
    civic-extract issues --jurisdiction city-san-rafael --stats
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def add_issues_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the issues subcommand to the parser."""
    parser = subparsers.add_parser(
        "issues",
        help="Fetch and store 311 issues from providers",
        description="Fetch operational issues from 311 providers and store in Civic database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--provider",
        default="seeclickfix",
        choices=["seeclickfix", "all"],
        help="Issue provider (default: seeclickfix)",
    )
    parser.add_argument(
        "--place-url",
        help="Provider-specific place URL (default: derived from jurisdiction)",
    )
    parser.add_argument(
        "--status",
        default=None,
        choices=["open", "closed", "acknowledged"],
        help="Filter by status (default: all)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum pages to fetch (default: 50)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Issues per page (default: 100, max: 100)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store issues in cloud Postgres (requires DATABASE_URL)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/pilot",
        help="Directory for local output files (default: data/pilot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration only - don't fetch issues",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only - don't fetch new issues",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate existing local JSON data to cloud storage",
    )


def derive_place_url(jurisdiction_id: str) -> str:
    """
    Derive provider place_url from jurisdiction ID.

    Examples:
        city-san-rafael -> san-rafael
        city-new-york -> new-york
    """
    place_url = jurisdiction_id
    for prefix in ["city-", "county-", "town-"]:
        if place_url.startswith(prefix):
            place_url = place_url[len(prefix):]
            break
    return place_url


def load_existing_issues(output_dir: str, jurisdiction_id: str) -> List[Dict[str, Any]]:
    """Load existing issues from local JSON files."""
    output_path = Path(output_dir)

    # Try multiple file patterns
    patterns = [
        f"seeclickfix_{jurisdiction_id.replace('-', '_')}.json",
        f"seeclickfix_sanrafael_complete.json",
        f"seeclickfix_sanrafael_all.json",
    ]

    for pattern in patterns:
        file_path = output_path / pattern
        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and "issues" in data:
                        return data["issues"]
            except Exception as e:
                logger.warning(f"Error loading {file_path}: {e}")

    return []


def normalize_legacy_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a legacy SeeClickFix issue to NormalizedIssue format.

    Handles the format from the existing seeclickfix.py CLI.
    """
    # Extract external_id from various formats - always convert to string
    external_id = issue.get("external_id")
    if not external_id:
        issue_id = issue.get("id", "")
        if isinstance(issue_id, str) and issue_id.startswith("scf-"):
            external_id = issue_id[4:]  # Remove "scf-" prefix
        else:
            external_id = str(issue_id)
    else:
        external_id = str(external_id)  # Ensure it's a string

    # Extract location data
    location = issue.get("location", {})
    address = issue.get("address") or location.get("address", "")
    latitude = issue.get("latitude") or location.get("lat")
    longitude = issue.get("longitude") or location.get("lng")

    # Extract reporter name
    reporter = issue.get("reporter", {})
    reporter_name = issue.get("reporter_name") or reporter.get("name")
    if reporter_name == "Anonymous":
        reporter_name = None

    # Extract images
    images = issue.get("images", [])
    if not images:
        media = issue.get("media", {})
        if media.get("image_url"):
            images = [media["image_url"]]
        elif media.get("image_full"):
            images = [media["image_full"]]

    # Extract issue type
    issue_type = issue.get("issue_type") or issue.get("category", "")

    # Build provider metadata
    provider_metadata = issue.get("provider_metadata", {})
    if not provider_metadata:
        provider_metadata = {
            "category_id": issue.get("category_id"),
            "organization": issue.get("organization"),
            "rating": issue.get("rating"),
            "comment_count": issue.get("comment_count"),
            "html_url": issue.get("html_url"),
        }
        # Include original seeclickfix metadata if present
        if issue.get("_seeclickfix_metadata"):
            provider_metadata.update(issue["_seeclickfix_metadata"])

    return {
        "provider": "seeclickfix",
        "external_id": external_id,
        "title": issue.get("title", ""),
        "description": issue.get("description", ""),
        "issue_type": issue_type,
        "status": issue.get("status", "open"),
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "closed_at": issue.get("closed_at"),
        "reporter_name": reporter_name,
        "images": images,
        "provider_metadata": provider_metadata,
    }


def run_issues(args: argparse.Namespace) -> int:
    """Run the issues command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    jurisdiction_id = args.jurisdiction
    provider = args.provider
    place_url = args.place_url or derive_place_url(jurisdiction_id)

    logger.info(f"Issues command for {jurisdiction_id}")
    logger.info(f"Provider: {provider}, Place URL: {place_url}")

    # Stats mode - just show current counts
    if args.stats:
        return show_stats(jurisdiction_id, args.cloud)

    # Migrate mode - load local data and store to cloud
    if args.migrate:
        return migrate_issues(jurisdiction_id, args.output_dir, args.cloud, args.dry_run)

    # Dry-run mode - validate configuration
    if args.dry_run:
        return validate_config(jurisdiction_id, provider, place_url, args.cloud)

    # Normal mode - fetch and store issues
    return fetch_and_store_issues(
        jurisdiction_id=jurisdiction_id,
        provider=provider,
        place_url=place_url,
        status=args.status,
        max_pages=args.max_pages,
        per_page=args.per_page,
        cloud=args.cloud,
        output_dir=args.output_dir,
    )


def show_stats(jurisdiction_id: str, cloud: bool) -> int:
    """Show statistics for issues in storage."""
    if cloud:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            return 1

        try:
            from civicos.storage.postgres_backend import PostgresBackend
            backend = PostgresBackend(database_url)
            count = backend.get_issue_count(jurisdiction_id)
            seeclickfix_count = backend.get_issue_count(jurisdiction_id, provider="seeclickfix")

            logger.info("=" * 50)
            logger.info(f"Issues for {jurisdiction_id}")
            logger.info(f"Total issues: {count}")
            logger.info(f"  SeeClickFix: {seeclickfix_count}")
            logger.info("=" * 50)
            return 0
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return 1
    else:
        logger.info("Local stats not implemented - use --cloud for cloud storage stats")
        return 0


def migrate_issues(jurisdiction_id: str, output_dir: str, cloud: bool, dry_run: bool) -> int:
    """Migrate existing local JSON data to cloud storage."""
    if not cloud:
        logger.error("--migrate requires --cloud flag")
        return 1

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return 1

    # Load existing issues from local files
    logger.info(f"Loading existing issues from {output_dir}...")
    existing_issues = load_existing_issues(output_dir, jurisdiction_id)

    if not existing_issues:
        logger.warning("No existing issues found to migrate")
        return 0

    logger.info(f"Found {len(existing_issues)} issues to migrate")

    # Normalize to new format
    logger.info("Normalizing issues to unified format...")
    normalized = [normalize_legacy_issue(issue) for issue in existing_issues]

    if dry_run:
        logger.info("Dry-run mode - would migrate these issues:")
        # Show sample
        for issue in normalized[:5]:
            logger.info(f"  {issue['external_id']}: {issue['title'][:50]}...")
        if len(normalized) > 5:
            logger.info(f"  ... and {len(normalized) - 5} more")
        return 0

    # Store to cloud
    try:
        from civicos.storage.postgres_backend import PostgresBackend
        backend = PostgresBackend(database_url)

        logger.info(f"Storing {len(normalized)} issues to Postgres...")
        count = backend.store_issues(jurisdiction_id, normalized)

        logger.info("=" * 50)
        logger.info(f"Migration Complete for {jurisdiction_id}")
        logger.info(f"Issues migrated: {count}")
        logger.info("=" * 50)

        return 0
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1


def validate_config(jurisdiction_id: str, provider: str, place_url: str, cloud: bool) -> int:
    """Validate configuration without fetching data."""
    logger.info("Dry-run mode - validating configuration...")

    # Test provider access
    if provider == "seeclickfix":
        try:
            from civicos.issues.providers.seeclickfix import SeeclickfixProvider
            prov = SeeclickfixProvider()
            issues = prov.get_issues(place_url, per_page=1, page=1)
            logger.info(f"Provider test: {len(issues)} issue(s) accessible from SeeClickFix")
        except Exception as e:
            logger.error(f"Provider test failed: {e}")
            return 1

    # Test cloud connection if requested
    if cloud:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            return 1

        try:
            from civicos.storage.postgres_backend import PostgresBackend
            backend = PostgresBackend(database_url)
            result = backend.validate()
            if result.is_valid:
                logger.info("Cloud connection: OK")
            else:
                logger.error(f"Cloud connection failed: {result.errors}")
                return 1
        except Exception as e:
            logger.error(f"Cloud connection test failed: {e}")
            return 1

    logger.info("Configuration validated successfully")
    return 0


def fetch_and_store_issues(
    jurisdiction_id: str,
    provider: str,
    place_url: str,
    status: Optional[str],
    max_pages: int,
    per_page: int,
    cloud: bool,
    output_dir: str,
) -> int:
    """Fetch issues from provider and store them."""
    # Import provider
    if provider == "seeclickfix":
        try:
            from civicos.issues.providers.seeclickfix import SeeclickfixProvider
            prov = SeeclickfixProvider()
        except ImportError as e:
            logger.error(f"Failed to import provider: {e}")
            return 1
    else:
        logger.error(f"Unknown provider: {provider}")
        return 1

    # Fetch all issues
    logger.info(f"Fetching issues from {provider}...")
    issues = prov.get_all_issues(
        place_url=place_url,
        status=status,
        max_pages=max_pages,
        per_page=per_page,
    )

    if not issues:
        logger.warning("No issues fetched")
        return 1

    logger.info(f"Fetched {len(issues)} issues")

    # Convert to dicts
    issue_dicts = [issue.to_dict() for issue in issues]

    # Store to cloud if requested
    if cloud:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL environment variable not set")
            return 1

        try:
            from civicos.storage.postgres_backend import PostgresBackend
            backend = PostgresBackend(database_url)

            logger.info(f"Storing {len(issue_dicts)} issues to Postgres...")
            count = backend.store_issues(jurisdiction_id, issue_dicts)

            logger.info("=" * 50)
            logger.info(f"Issues Fetch Complete for {jurisdiction_id}")
            logger.info(f"Provider: {provider}")
            logger.info(f"Issues stored: {count}")
            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"Failed to store issues: {e}")
            return 1
    else:
        # Store locally
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"issues_{jurisdiction_id.replace('-', '_')}.json"

        output_data = {
            "jurisdiction_id": jurisdiction_id,
            "provider": provider,
            "fetched_at": datetime.now().isoformat(),
            "count": len(issue_dicts),
            "issues": issue_dicts,
        }

        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)

        logger.info("=" * 50)
        logger.info(f"Issues Fetch Complete for {jurisdiction_id}")
        logger.info(f"Provider: {provider}")
        logger.info(f"Issues saved: {len(issue_dicts)}")
        logger.info(f"Output file: {output_file}")
        logger.info("=" * 50)

    return 0
