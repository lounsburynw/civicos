#!/usr/bin/env python3
"""
Database migration runner for Civic platform.

Provides versioned schema migrations with:
- Version tracking via schema_versions table
- Ordered execution by migration filename
- Idempotent migrations (safe to re-run)
- Multi-database coordination
- Dry-run mode for validation

Usage:
    python scripts/migrate.py                    # Run all pending migrations
    python scripts/migrate.py --dry-run          # Show what would be applied
    python scripts/migrate.py --status           # Show migration status
    python scripts/migrate.py --target 005       # Migrate up to version 005
    python scripts/migrate.py --db civic_state   # Migrate specific database
"""

import argparse
import hashlib
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
DATA_DIR = PROJECT_ROOT / "data"

# Database configurations
DATABASES = {
    "civic_state": DATA_DIR / "civic_state.db",
    "civic_participation": DATA_DIR / "civic_participation.db",
}


def get_migration_files() -> list[tuple[str, str, Path]]:
    """Get all migration files sorted by version number and name.

    Returns list of (version, key, filepath) tuples where:
    - version: numeric prefix (e.g., "002")
    - key: full filename without extension (e.g., "002_add_complaints")
    - filepath: full Path to the file
    """
    migrations = []

    for f in MIGRATIONS_DIR.glob("*.sql"):
        # Extract version number from filename (e.g., "002_add_complaints.sql" -> "002")
        match = re.match(r"^(\d+)_", f.name)
        if match:
            version = match.group(1)
            key = f.stem  # filename without extension
            migrations.append((version, key, f))

    # Sort by version number first, then alphabetically by name for same version
    migrations.sort(key=lambda x: (int(x[0]), x[1]))
    return migrations


def compute_checksum(filepath: Path) -> str:
    """Compute MD5 checksum of migration file."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def ensure_schema_versions_table(conn: sqlite3.Connection):
    """Create schema_versions tracking table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_versions (
            version TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            execution_time_ms INTEGER,
            applied_by TEXT DEFAULT 'migrate.py'
        )
    """)
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> dict[str, dict]:
    """Get dict of applied migrations keyed by migration key (filename without .sql)."""
    ensure_schema_versions_table(conn)
    cursor = conn.execute(
        "SELECT version, filename, checksum, applied_at FROM schema_versions ORDER BY version"
    )
    # Key by filename stem (without .sql extension) to handle duplicate version numbers
    return {
        Path(row[1]).stem: {"version": row[0], "filename": row[1], "checksum": row[2], "applied_at": row[3]}
        for row in cursor.fetchall()
    }


def apply_migration(
    conn: sqlite3.Connection,
    key: str,
    version: str,
    filepath: Path,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Apply a single migration file.

    Args:
        conn: Database connection
        key: Migration key (filename without .sql extension)
        version: Version number prefix
        filepath: Path to migration file
        dry_run: If True, don't actually apply

    Returns (success, message) tuple.
    """
    checksum = compute_checksum(filepath)

    # Read migration SQL
    with open(filepath, "r") as f:
        sql = f.read()

    if dry_run:
        return True, f"Would apply: {filepath.name}"

    start_time = datetime.now()

    try:
        # Execute migration
        conn.executescript(sql)

        # Record migration as applied (use key as version for uniqueness)
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        conn.execute(
            """
            INSERT OR REPLACE INTO schema_versions
            (version, filename, checksum, applied_at, execution_time_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, filepath.name, checksum, datetime.now().isoformat(), execution_time),
        )
        conn.commit()

        return True, f"Applied {filepath.name} in {execution_time}ms"

    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Failed to apply {filepath.name}: {e}"


def check_migration_checksum(
    applied: dict, key: str, filepath: Path
) -> Optional[str]:
    """Check if migration file has changed since it was applied."""
    if key not in applied:
        return None

    current_checksum = compute_checksum(filepath)
    if current_checksum != applied[key]["checksum"]:
        return (
            f"WARNING: {filepath.name} has changed since it was applied! "
            f"Original: {applied[key]['checksum'][:8]}... "
            f"Current: {current_checksum[:8]}..."
        )
    return None


def migrate(
    db_path: Path,
    dry_run: bool = False,
    target_version: Optional[str] = None,
    verbose: bool = True,
) -> tuple[int, int, list[str]]:
    """
    Run pending migrations on a database.

    Returns (applied_count, skipped_count, messages).
    """
    messages = []

    if not db_path.exists():
        if dry_run:
            messages.append(f"Would create database: {db_path}")
        else:
            # Create parent directory if needed
            db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    applied = get_applied_migrations(conn)
    migrations = get_migration_files()

    applied_count = 0
    skipped_count = 0

    for version, key, filepath in migrations:
        # Check if target version reached
        if target_version and int(version) > int(target_version):
            break

        # Check for modified migrations
        checksum_warning = check_migration_checksum(applied, key, filepath)
        if checksum_warning:
            messages.append(checksum_warning)

        # Skip already applied (using full key, not just version)
        if key in applied:
            if verbose:
                messages.append(f"Skipped {filepath.name} (already applied)")
            skipped_count += 1
            continue

        # Apply migration
        success, msg = apply_migration(conn, key, version, filepath, dry_run)
        messages.append(msg)

        if success:
            applied_count += 1
        else:
            conn.close()
            return applied_count, skipped_count, messages

    conn.close()
    return applied_count, skipped_count, messages


def show_status(db_name: str, db_path: Path):
    """Show migration status for a database."""
    print(f"\n{'=' * 60}")
    print(f"Database: {db_name}")
    print(f"Path: {db_path}")
    print(f"{'=' * 60}")

    if not db_path.exists():
        print("Status: Database does not exist yet")
        return

    conn = sqlite3.connect(db_path)
    applied = get_applied_migrations(conn)
    migrations = get_migration_files()
    conn.close()

    print(f"\nMigrations ({len(applied)} applied, {len(migrations) - len(applied)} pending):\n")

    for version, key, filepath in migrations:
        if key in applied:
            info = applied[key]
            status = f"✓ Applied {info['applied_at'][:19]}"
            # Check for changes
            if compute_checksum(filepath) != info["checksum"]:
                status += " ⚠️  MODIFIED"
        else:
            status = "○ Pending"

        print(f"  {version}: {filepath.name:<45} {status}")


def main():
    parser = argparse.ArgumentParser(
        description="Run database migrations for Civic platform"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be applied without making changes",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show migration status for all databases",
    )
    parser.add_argument(
        "--target",
        type=str,
        help="Migrate up to this version (e.g., '005')",
    )
    parser.add_argument(
        "--db",
        type=str,
        choices=list(DATABASES.keys()),
        help="Migrate specific database only",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--mark-applied",
        type=str,
        metavar="MIGRATION",
        help="Mark a specific migration as applied without running it (e.g., '006_add_nested_threading')",
    )

    args = parser.parse_args()

    # Select databases to process
    if args.db:
        dbs = {args.db: DATABASES[args.db]}
    else:
        dbs = DATABASES

    if args.status:
        for name, path in dbs.items():
            show_status(name, path)
        return 0

    # Mark specific migration as applied
    if args.mark_applied:
        key = args.mark_applied
        migrations = get_migration_files()
        migration_info = None
        for version, k, filepath in migrations:
            if k == key:
                migration_info = (version, k, filepath)
                break

        if not migration_info:
            print(f"Error: Migration '{key}' not found")
            return 1

        version, key, filepath = migration_info
        checksum = compute_checksum(filepath)

        for db_name, db_path in dbs.items():
            if not db_path.exists():
                print(f"Skipping {db_name}: database does not exist")
                continue

            conn = sqlite3.connect(db_path)
            ensure_schema_versions_table(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO schema_versions
                (version, filename, checksum, applied_at, execution_time_ms, applied_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, filepath.name, checksum, datetime.now().isoformat(), 0, "mark-applied"),
            )
            conn.commit()
            conn.close()
            print(f"Marked {filepath.name} as applied in {db_name}")

        return 0

    # Run migrations
    print(f"\n{'=' * 60}")
    print("Civic Database Migration")
    print(f"{'=' * 60}")

    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)\n")

    total_applied = 0
    total_skipped = 0
    errors = []

    for db_name, db_path in dbs.items():
        print(f"\n→ {db_name} ({db_path})")

        applied, skipped, messages = migrate(
            db_path,
            dry_run=args.dry_run,
            target_version=args.target,
            verbose=args.verbose,
        )

        for msg in messages:
            if msg.startswith("Failed") or msg.startswith("WARNING"):
                print(f"  ⚠️  {msg}")
                if msg.startswith("Failed"):
                    errors.append(msg)
            elif args.verbose or msg.startswith("Applied") or msg.startswith("Would"):
                print(f"  ✓ {msg}")

        total_applied += applied
        total_skipped += skipped
        print(f"  Applied: {applied}, Skipped: {skipped}")

    # Summary
    print(f"\n{'=' * 60}")
    if args.dry_run:
        print(f"Dry run complete: {total_applied} would be applied")
    else:
        print(f"Migration complete: {total_applied} applied, {total_skipped} skipped")

    if errors:
        print(f"\n⚠️  {len(errors)} error(s) occurred!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
