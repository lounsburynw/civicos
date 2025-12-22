#!/usr/bin/env python3
"""
Database migration runner for Civic platform.

Provides versioned schema migrations with:
- Version tracking via schema_versions table
- Ordered execution by migration filename
- Idempotent migrations (safe to re-run)
- Multi-database coordination
- Dry-run mode for validation
- Rollback support via .down.sql files

Usage:
    python scripts/migrate.py                    # Run all pending migrations
    python scripts/migrate.py --dry-run          # Show what would be applied
    python scripts/migrate.py --status           # Show migration status
    python scripts/migrate.py --target 005       # Migrate up to version 005
    python scripts/migrate.py --db civic_state   # Migrate specific database
    python scripts/migrate.py --rollback 1       # Roll back the last migration
    python scripts/migrate.py --rollback-to 005  # Roll back to version 005

Rollback:
    To make a migration reversible, create a corresponding .down.sql file:
        migrations/011_add_feature.sql       # Forward migration
        migrations/011_add_feature.down.sql  # Reverse migration

    The --status command shows which migrations have rollback scripts (↩).
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


def get_migration_files(include_down: bool = False) -> list[tuple[str, str, Path]]:
    """Get all migration files sorted by version number and name.

    Returns list of (version, key, filepath) tuples where:
    - version: numeric prefix (e.g., "002")
    - key: full filename without extension (e.g., "002_add_complaints")
    - filepath: full Path to the file

    Args:
        include_down: If False (default), exclude .down.sql files.
                      If True, include only .down.sql files.
    """
    migrations = []

    for f in MIGRATIONS_DIR.glob("*.sql"):
        is_down = f.name.endswith(".down.sql")

        # Filter based on include_down parameter
        if include_down and not is_down:
            continue
        if not include_down and is_down:
            continue

        # Extract version number from filename (e.g., "002_add_complaints.sql" -> "002")
        match = re.match(r"^(\d+)_", f.name)
        if match:
            version = match.group(1)
            # For down files, key is without .down suffix
            key = f.stem.replace(".down", "") if is_down else f.stem
            migrations.append((version, key, f))

    # Sort by version number first, then alphabetically by name for same version
    migrations.sort(key=lambda x: (int(x[0]), x[1]))
    return migrations


def get_down_migration(key: str) -> Optional[Path]:
    """Get the downgrade migration file for a given migration key.

    Args:
        key: Migration key (e.g., "002_add_complaints")

    Returns:
        Path to .down.sql file if it exists, None otherwise
    """
    down_file = MIGRATIONS_DIR / f"{key}.down.sql"
    return down_file if down_file.exists() else None


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


def rollback_migration(
    conn: sqlite3.Connection,
    key: str,
    version: str,
    down_filepath: Path,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Roll back a single migration using its .down.sql file.

    Args:
        conn: Database connection
        key: Migration key (filename without .sql extension)
        version: Version number prefix
        down_filepath: Path to the .down.sql file
        dry_run: If True, don't actually apply

    Returns (success, message) tuple.
    """
    # Read downgrade SQL
    with open(down_filepath, "r") as f:
        sql = f.read()

    if dry_run:
        return True, f"Would roll back: {key} (using {down_filepath.name})"

    start_time = datetime.now()

    try:
        # Execute downgrade
        conn.executescript(sql)

        # Remove migration from schema_versions
        conn.execute("DELETE FROM schema_versions WHERE version = ?", (key,))
        conn.commit()

        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        return True, f"Rolled back {key} in {execution_time}ms"

    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Failed to roll back {key}: {e}"


def rollback(
    db_path: Path,
    count: int = 1,
    target_version: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> tuple[int, list[str]]:
    """
    Roll back migrations on a database.

    Args:
        db_path: Path to the database
        count: Number of migrations to roll back (default: 1)
        target_version: Roll back to this version (alternative to count)
        dry_run: If True, don't actually apply changes
        verbose: If True, show detailed output

    Returns (rollback_count, messages).
    """
    messages = []

    if not db_path.exists():
        messages.append(f"Database does not exist: {db_path}")
        return 0, messages

    conn = sqlite3.connect(db_path)
    applied = get_applied_migrations(conn)

    if not applied:
        messages.append("No migrations to roll back")
        conn.close()
        return 0, messages

    # Get applied migrations in reverse order (most recent first)
    applied_list = sorted(applied.items(), key=lambda x: x[1]["applied_at"], reverse=True)

    rollback_count = 0

    for key, info in applied_list:
        # Check if we've rolled back enough
        if target_version:
            # Stop when we reach the target version
            version_match = re.match(r"^(\d+)_", key)
            if version_match and int(version_match.group(1)) <= int(target_version):
                break
        else:
            if rollback_count >= count:
                break

        # Check for .down.sql file
        down_file = get_down_migration(key)
        if not down_file:
            messages.append(f"No rollback script for {key} ({key}.down.sql not found)")
            if not dry_run:
                messages.append("Stopping rollback - create .down.sql file or restore from backup")
                break
            continue

        # Get version from key
        version_match = re.match(r"^(\d+)_", key)
        version = version_match.group(1) if version_match else "unknown"

        # Roll back the migration
        success, msg = rollback_migration(conn, key, version, down_file, dry_run)
        messages.append(msg)

        if success:
            rollback_count += 1
        else:
            conn.close()
            return rollback_count, messages

    conn.close()
    return rollback_count, messages


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
        # Check for .down.sql file
        has_down = get_down_migration(key) is not None
        down_indicator = "↩" if has_down else " "

        if key in applied:
            info = applied[key]
            status = f"✓ Applied {info['applied_at'][:19]}"
            # Check for changes
            if compute_checksum(filepath) != info["checksum"]:
                status += " ⚠️  MODIFIED"
        else:
            status = "○ Pending"

        print(f"  {down_indicator} {version}: {filepath.name:<43} {status}")

    # Legend
    print(f"\n  ↩ = has rollback script (.down.sql)")


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
    parser.add_argument(
        "--rollback",
        type=int,
        metavar="N",
        help="Roll back the last N migrations (requires .down.sql files)",
    )
    parser.add_argument(
        "--rollback-to",
        type=str,
        metavar="VERSION",
        help="Roll back to this version (e.g., '005'), rolling back all migrations after it",
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

    # Rollback migrations
    if args.rollback or args.rollback_to:
        print(f"\n{'=' * 60}")
        print("Civic Database Rollback")
        print(f"{'=' * 60}")

        if args.dry_run:
            print("Mode: DRY RUN (no changes will be made)\n")

        total_rolled_back = 0
        errors = []

        for db_name, db_path in dbs.items():
            print(f"\n→ {db_name} ({db_path})")

            rolled_back, messages = rollback(
                db_path,
                count=args.rollback or 999,  # Large number if using rollback_to
                target_version=args.rollback_to,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )

            for msg in messages:
                if msg.startswith("Failed") or msg.startswith("No rollback script") or msg.startswith("Stopping"):
                    print(f"  ⚠️  {msg}")
                    if msg.startswith("Failed"):
                        errors.append(msg)
                else:
                    print(f"  ↩ {msg}")

            total_rolled_back += rolled_back
            print(f"  Rolled back: {rolled_back}")

        # Summary
        print(f"\n{'=' * 60}")
        if args.dry_run:
            print(f"Dry run complete: {total_rolled_back} would be rolled back")
        else:
            print(f"Rollback complete: {total_rolled_back} rolled back")

        if errors:
            print(f"\n⚠️  {len(errors)} error(s) occurred!")
            return 1

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
