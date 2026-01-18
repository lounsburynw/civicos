"""
CLI for viewing extraction audit logs.

Usage:
    civic-extract audit --jurisdiction city-san-rafael
    civic-extract audit --jurisdiction city-san-rafael --json
    civic-extract audit --jurisdiction city-san-rafael --limit 50
"""

import argparse
import json
import logging
import sys
from typing import Any

from civicos_extraction.manifest import AuditLog

logger = logging.getLogger(__name__)


def add_audit_parser(subparsers: Any) -> None:
    """Add audit subcommand parser."""
    parser = subparsers.add_parser(
        "audit",
        help="View extraction audit log with aggregated metrics per platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
View extraction audit log with aggregated metrics per platform.

The audit log aggregates data from ingestion manifests to show:
- Run counts per platform
- Success rates
- Total records processed
- First and last run timestamps

Examples:
    # View audit log for a jurisdiction
    civic-extract audit --jurisdiction city-san-rafael

    # Output as JSON for scripting
    civic-extract audit --jurisdiction city-san-rafael --json

    # Limit to most recent 50 manifests
    civic-extract audit --jurisdiction city-san-rafael --limit 50
""",
    )

    parser.add_argument(
        "--jurisdiction", "-j",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=100,
        help="Maximum manifests to process (default: 100)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )


def run_audit(args: argparse.Namespace) -> int:
    """Run audit command."""
    try:
        audit = AuditLog.from_manifests(
            jurisdiction_id=args.jurisdiction,
            limit=args.limit,
        )
    except Exception as e:
        print(f"Error generating audit log: {e}", file=sys.stderr)
        logger.exception("Failed to generate audit log")
        return 1

    if audit.total_runs == 0:
        print(f"No extraction runs found for {args.jurisdiction}")
        return 0

    if args.json:
        print(json.dumps(audit.to_dict(), indent=2))
    else:
        print(audit.summary())

    return 0
