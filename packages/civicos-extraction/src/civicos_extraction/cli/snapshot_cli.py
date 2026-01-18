"""
CLI for managing data snapshots.

Usage:
    civic-extract snapshot create --jurisdiction city-san-rafael --version Q1-2026
    civic-extract snapshot list --jurisdiction city-san-rafael
    civic-extract snapshot info --jurisdiction city-san-rafael --version Q1-2026
    civic-extract snapshot verify --jurisdiction city-san-rafael --version Q1-2026
"""

import argparse
import json
import logging
import os
import sys
from typing import Any

from civicos_extraction.manifest import (
    AuditLog,
    DataSnapshot,
    get_snapshot,
    list_snapshots,
    save_snapshot,
)

logger = logging.getLogger(__name__)


def add_snapshot_parser(subparsers: Any) -> None:
    """Add snapshot subcommand parser."""
    parser = subparsers.add_parser(
        "snapshot",
        help="Manage versioned data snapshots for quarterly releases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Manage versioned data snapshots for quarterly releases.

Snapshots provide point-in-time releases of extracted data with:
- Version tagging (Q1-2026, Q2-2026, etc.)
- Aggregated metrics from extraction runs
- File checksums for integrity verification
- Release metadata

Examples:
    # Create a quarterly snapshot
    civic-extract snapshot create -j city-san-rafael -v Q1-2026

    # Create with description and include data files
    civic-extract snapshot create -j city-san-rafael -v Q1-2026 \\
        --description "Initial pilot data release" \\
        --include-files

    # List all snapshots
    civic-extract snapshot list -j city-san-rafael

    # View snapshot details
    civic-extract snapshot info -j city-san-rafael -v Q1-2026

    # Verify snapshot integrity
    civic-extract snapshot verify -j city-san-rafael -v Q1-2026
""",
    )

    parser.add_argument(
        "action",
        choices=["create", "list", "info", "verify"],
        help="Action to perform",
    )
    parser.add_argument(
        "--jurisdiction", "-j",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--version", "-v",
        help="Snapshot version (e.g., Q1-2026). Required for create/info/verify.",
    )
    parser.add_argument(
        "--description", "-d",
        default="",
        help="Release description/notes (for create)",
    )
    parser.add_argument(
        "--release-type", "-t",
        choices=["quarterly", "urgent", "manual"],
        default="quarterly",
        help="Release type (default: quarterly)",
    )
    parser.add_argument(
        "--include-files",
        action="store_true",
        help="Include data files with checksums (for create)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )


def run_snapshot(args: argparse.Namespace) -> int:
    """Run snapshot command."""
    if args.action == "create":
        return _create_snapshot(args)
    elif args.action == "list":
        return _list_snapshots(args)
    elif args.action == "info":
        return _info_snapshot(args)
    elif args.action == "verify":
        return _verify_snapshot(args)
    return 1


def _create_snapshot(args: argparse.Namespace) -> int:
    """Create a new data snapshot."""
    if not args.version:
        print("Error: --version is required for create action", file=sys.stderr)
        return 1

    # Validate version format
    if not DataSnapshot.validate_version(args.version):
        print(
            f"Error: Invalid version format '{args.version}'. "
            "Use Q1-2026, 2026-01-15, or v1.0.0 format.",
            file=sys.stderr,
        )
        return 1

    # Check if snapshot already exists
    existing = get_snapshot(args.jurisdiction, args.version)
    if existing:
        print(
            f"Error: Snapshot {args.version} already exists for {args.jurisdiction}",
            file=sys.stderr,
        )
        return 1

    try:
        # Build audit log for metrics
        audit = AuditLog.from_manifests(
            jurisdiction_id=args.jurisdiction,
            limit=100,
        )

        # Create snapshot
        snapshot = DataSnapshot.create(
            jurisdiction_id=args.jurisdiction,
            version=args.version,
            release_type=args.release_type,
            description=args.description,
            audit_log=audit if audit.total_runs > 0 else None,
        )

        # Include data files if requested
        if args.include_files:
            _add_data_files(snapshot, args.jurisdiction)

        # Save snapshot
        filepath = save_snapshot(snapshot)

        if args.json:
            print(json.dumps({
                "status": "created",
                "snapshot_id": snapshot.snapshot_id,
                "version": snapshot.version,
                "filepath": filepath,
                "total_records": snapshot.total_records,
                "file_count": len(snapshot.included_files),
            }, indent=2))
        else:
            print(f"Created snapshot: {snapshot.snapshot_id}")
            print(f"Version: {snapshot.version}")
            print(f"Saved to: {filepath}")
            if snapshot.total_records:
                print(f"Total records: {snapshot.total_records:,}")
            if snapshot.included_files:
                print(f"Files included: {len(snapshot.included_files)}")

        return 0

    except Exception as e:
        print(f"Error creating snapshot: {e}", file=sys.stderr)
        logger.exception("Failed to create snapshot")
        return 1


def _add_data_files(snapshot: DataSnapshot, jurisdiction_id: str) -> None:
    """Add common data files to the snapshot."""
    data_root = os.environ.get("CIVICOS_DATA_ROOT", "data")

    # Common data file patterns to include
    data_files = [
        ("extraction_checkpoint", f"{data_root}/extraction/{jurisdiction_id}.json"),
        ("pilot_meetings", f"{data_root}/pilot/meetings.json"),
        ("pilot_decisions", f"{data_root}/pilot/decisions.json"),
        ("pilot_issues", f"{data_root}/pilot/issues.json"),
    ]

    for name, path in data_files:
        if os.path.exists(path):
            try:
                # Try to get record count for data files
                record_count = None
                if path.endswith(".json"):
                    with open(path) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        record_count = len(data)
                    elif isinstance(data, dict) and "records" in data:
                        record_count = len(data["records"])

                snapshot.add_file(name, path, "data", record_count)
            except Exception as e:
                logger.warning(f"Failed to add file {path}: {e}")


def _list_snapshots(args: argparse.Namespace) -> int:
    """List all snapshots for a jurisdiction."""
    try:
        snapshots = list_snapshots(args.jurisdiction)
    except Exception as e:
        print(f"Error listing snapshots: {e}", file=sys.stderr)
        logger.exception("Failed to list snapshots")
        return 1

    if not snapshots:
        if args.json:
            print(json.dumps({"snapshots": [], "count": 0}, indent=2))
        else:
            print(f"No snapshots found for {args.jurisdiction}")
        return 0

    if args.json:
        print(json.dumps({"snapshots": snapshots, "count": len(snapshots)}, indent=2))
    else:
        print("=" * 70)
        print(f"SNAPSHOTS: {args.jurisdiction}")
        print("=" * 70)
        print(f"{'Version':<15} {'Type':<12} {'Created':<20} {'Records':<12} {'Files':<6}")
        print("-" * 70)
        for s in snapshots:
            created = s["created_at"][:10]  # Just date part
            print(
                f"{s['version']:<15} {s['release_type']:<12} {created:<20} "
                f"{s['total_records']:<12,} {s['file_count']:<6}"
            )
        print("-" * 70)
        print(f"Total: {len(snapshots)} snapshot(s)")

    return 0


def _info_snapshot(args: argparse.Namespace) -> int:
    """Show detailed information about a snapshot."""
    if not args.version:
        print("Error: --version is required for info action", file=sys.stderr)
        return 1

    try:
        snapshot = get_snapshot(args.jurisdiction, args.version)
    except Exception as e:
        print(f"Error loading snapshot: {e}", file=sys.stderr)
        logger.exception("Failed to load snapshot")
        return 1

    if not snapshot:
        print(
            f"Snapshot {args.version} not found for {args.jurisdiction}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2))
    else:
        print(snapshot.summary())

    return 0


def _verify_snapshot(args: argparse.Namespace) -> int:
    """Verify integrity of a snapshot's files."""
    if not args.version:
        print("Error: --version is required for verify action", file=sys.stderr)
        return 1

    try:
        snapshot = get_snapshot(args.jurisdiction, args.version)
    except Exception as e:
        print(f"Error loading snapshot: {e}", file=sys.stderr)
        logger.exception("Failed to load snapshot")
        return 1

    if not snapshot:
        print(
            f"Snapshot {args.version} not found for {args.jurisdiction}",
            file=sys.stderr,
        )
        return 1

    result = snapshot.verify_integrity()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 50)
        print(f"SNAPSHOT VERIFICATION: {snapshot.version}")
        print("=" * 50)
        print(f"Files checked: {result['files_checked']}")

        if result["verified"]:
            print("Status: VERIFIED ✓")
        else:
            print("Status: FAILED ✗")
            if result["files_missing"]:
                print(f"\nMissing files ({len(result['files_missing'])}):")
                for name in result["files_missing"]:
                    print(f"  - {name}")
            if result["files_modified"]:
                print(f"\nModified files ({len(result['files_modified'])}):")
                for name in result["files_modified"]:
                    print(f"  - {name}")

        print("=" * 50)

    return 0 if result["verified"] else 1
