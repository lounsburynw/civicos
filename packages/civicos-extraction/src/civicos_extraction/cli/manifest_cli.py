"""
CLI for viewing and managing ingestion manifests.

Usage:
    civic-extract manifest list --jurisdiction city-san-rafael
    civic-extract manifest show --id ingest_20251222_115530_city-san-rafael
    civic-extract manifest latest --jurisdiction city-san-rafael
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Any, Optional

from civicos_extraction.manifest import (
    IngestionManifest,
    list_manifests,
    load_manifest,
    get_latest_manifest,
)

logger = logging.getLogger(__name__)


def add_manifest_parser(subparsers: Any) -> None:
    """Add manifest subcommand parser."""
    parser = subparsers.add_parser(
        "manifest",
        help="View and manage ingestion manifests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
View and manage ingestion manifests.

Examples:
    # List recent manifests for a jurisdiction
    civic-extract manifest list --jurisdiction city-san-rafael

    # Show details of a specific manifest
    civic-extract manifest show --file data/manifests/city-san-rafael/ingest_20251222.json

    # Get the latest manifest
    civic-extract manifest latest --jurisdiction city-san-rafael

    # Output as JSON for scripting
    civic-extract manifest latest --jurisdiction city-san-rafael --json
""",
    )

    parser.add_argument(
        "action",
        choices=["list", "show", "latest"],
        help="Action to perform",
    )
    parser.add_argument(
        "--jurisdiction", "-j",
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--file", "-f",
        help="Path to manifest file (for 'show' action)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=10,
        help="Number of manifests to list (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )


def run_manifest(args: argparse.Namespace) -> int:
    """Run manifest command."""
    if args.action == "list":
        return _list_manifests(args)
    elif args.action == "show":
        return _show_manifest(args)
    elif args.action == "latest":
        return _latest_manifest(args)
    return 1


def _list_manifests(args: argparse.Namespace) -> int:
    """List manifests for a jurisdiction."""
    if not args.jurisdiction:
        print("Error: --jurisdiction is required for 'list'", file=sys.stderr)
        return 1

    manifests = list_manifests(args.jurisdiction, limit=args.limit)

    if not manifests:
        print(f"No manifests found for {args.jurisdiction}")
        return 0

    if args.json:
        print(json.dumps(manifests, indent=2))
        return 0

    # Table format
    print(f"Ingestion manifests for {args.jurisdiction}:")
    print("-" * 80)
    print(f"{'ID':<45} {'Timestamp':<20} {'Records':<10} {'Status':<10}")
    print("-" * 80)

    for m in manifests:
        ts = datetime.fromisoformat(m["timestamp"]).strftime("%Y-%m-%d %H:%M")
        status = "OK" if m["success"] else "FAILED"
        print(f"{m['ingestion_id']:<45} {ts:<20} {m['records_ingested']:<10} {status:<10}")

    print("-" * 80)
    print(f"Total: {len(manifests)} manifest(s)")
    return 0


def _show_manifest(args: argparse.Namespace) -> int:
    """Show details of a specific manifest."""
    if not args.file:
        print("Error: --file is required for 'show'", file=sys.stderr)
        return 1

    try:
        manifest = load_manifest(args.file)
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading manifest: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2))
        return 0

    print(manifest.summary())
    return 0


def _latest_manifest(args: argparse.Namespace) -> int:
    """Get the latest manifest for a jurisdiction."""
    if not args.jurisdiction:
        print("Error: --jurisdiction is required for 'latest'", file=sys.stderr)
        return 1

    manifest = get_latest_manifest(args.jurisdiction)

    if not manifest:
        print(f"No manifests found for {args.jurisdiction}")
        return 0

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2))
        return 0

    print(manifest.summary())
    return 0
