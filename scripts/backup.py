#!/usr/bin/env python3
"""
Database backup and restore script for Civic platform.

Provides automated backup/restore with:
- Timestamped backup files with checksums
- Configurable retention policies
- Backup verification via SQLite integrity check
- Optional compression for long-term storage
- Restore with safety checks
- Pre-deployment backup integration

Usage:
    python scripts/backup.py                     # Backup all databases
    python scripts/backup.py --restore BACKUP    # Restore from backup file
    python scripts/backup.py --status            # Show backup status
    python scripts/backup.py --list              # List available backups
    python scripts/backup.py --verify BACKUP     # Verify backup integrity
    python scripts/backup.py --clean             # Remove old backups per retention policy
    python scripts/backup.py --dry-run           # Show what would be done
"""

import argparse
import gzip
import hashlib
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Environment detection
import os
CIVIC_ENV = os.getenv('CIVIC_ENV', 'development').lower()
IS_PRODUCTION = CIVIC_ENV == 'production'

# Project root and data paths (environment-aware)
PROJECT_ROOT = Path(__file__).parent.parent

if IS_PRODUCTION:
    # Production: Fly.io deployment with mounted volumes
    # - /app/user-data/ = persistent user data (what we back up)
    # - /app/bundled-data/ = read-only reference data (bundled with deploys)
    # - /app/data/ = mounted volume for backups
    USER_DATA_DIR = Path("/app/user-data")
    BUNDLED_DATA_DIR = Path("/app/bundled-data")
    BACKUP_DIR = Path("/app/data/backups")

    # In production, we only back up user data (participation database)
    # State data is bundled with deploys and refreshed automatically
    DATABASES = {
        "civic_participation": USER_DATA_DIR / "civic_participation.db",
    }
else:
    # Development: local paths relative to project root
    DATA_DIR = PROJECT_ROOT / "data"
    BACKUP_DIR = DATA_DIR / "backups"

    DATABASES = {
        "civic_state": DATA_DIR / "civic_state.db",
        "civic_participation": DATA_DIR / "civic_participation.db",
    }

# Retention policy: keep last N daily backups + last M weekly backups
RETENTION_DAILY = 7
RETENTION_WEEKLY = 4


def ensure_backup_dir():
    """Create backup directory if it doesn't exist."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def compute_checksum(filepath: Path) -> str:
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_backup_filename(db_name: str, timestamp: datetime, compressed: bool = False) -> str:
    """Generate backup filename with timestamp."""
    ts = timestamp.strftime("%Y%m%d_%H%M%S")
    ext = ".db.gz" if compressed else ".db"
    return f"{db_name}_{ts}{ext}"


def parse_backup_filename(filename: str) -> Optional[dict]:
    """Parse backup filename to extract metadata.

    Returns dict with db_name, timestamp, compressed if valid, None otherwise.
    """
    import re

    # Match pattern: dbname_YYYYMMDD_HHMMSS.db[.gz]
    match = re.match(r"^(.+?)_(\d{8}_\d{6})\.db(\.gz)?$", filename)
    if not match:
        return None

    db_name = match.group(1)
    ts_str = match.group(2)
    compressed = match.group(3) is not None

    try:
        timestamp = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
    except ValueError:
        return None

    return {
        "db_name": db_name,
        "timestamp": timestamp,
        "compressed": compressed,
        "filename": filename,
    }


def verify_sqlite_integrity(db_path: Path) -> tuple[bool, str]:
    """Verify SQLite database integrity.

    Returns (is_valid, message).
    """
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            return True, "Integrity check passed"
        else:
            return False, f"Integrity check failed: {result}"
    except sqlite3.Error as e:
        return False, f"Cannot open database: {e}"


def backup_database(
    db_name: str,
    db_path: Path,
    compress: bool = False,
    dry_run: bool = False,
) -> tuple[bool, str, Optional[Path]]:
    """
    Backup a single database.

    Returns (success, message, backup_path).
    """
    if not db_path.exists():
        return False, f"Database not found: {db_path}", None

    timestamp = datetime.now()
    backup_name = get_backup_filename(db_name, timestamp, compress)
    backup_path = BACKUP_DIR / backup_name
    checksum_path = backup_path.with_suffix(backup_path.suffix + ".sha256")

    if dry_run:
        return True, f"Would backup {db_name} -> {backup_name}", backup_path

    ensure_backup_dir()

    # Create backup using SQLite backup API for consistency
    try:
        # Connect to source
        src_conn = sqlite3.connect(db_path)

        # Create backup connection
        temp_backup = BACKUP_DIR / f"{backup_name}.tmp"
        dst_conn = sqlite3.connect(temp_backup)

        # Use SQLite backup API
        src_conn.backup(dst_conn)

        src_conn.close()
        dst_conn.close()

        # Compress if requested
        if compress:
            with open(temp_backup, "rb") as f_in:
                with gzip.open(backup_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            temp_backup.unlink()
        else:
            temp_backup.rename(backup_path)

        # Compute and save checksum
        checksum = compute_checksum(backup_path)
        checksum_path.write_text(f"{checksum}  {backup_name}\n")

        # Get file size
        size = backup_path.stat().st_size
        size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f}MB"

        return True, f"Backed up {db_name} -> {backup_name} ({size_str})", backup_path

    except sqlite3.Error as e:
        # Clean up partial backup
        if temp_backup.exists():
            temp_backup.unlink()
        if backup_path.exists():
            backup_path.unlink()
        return False, f"Backup failed for {db_name}: {e}", None


def restore_database(
    backup_path: Path,
    target_db: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[bool, str]:
    """
    Restore a database from backup.

    Returns (success, message).
    """
    if not backup_path.exists():
        return False, f"Backup file not found: {backup_path}"

    # Parse backup filename to determine target
    info = parse_backup_filename(backup_path.name)
    if not info and not target_db:
        return False, f"Cannot determine target database from filename. Use --db to specify."

    db_name = target_db or info["db_name"]

    if db_name not in DATABASES:
        return False, f"Unknown database: {db_name}. Valid options: {', '.join(DATABASES.keys())}"

    target_path = DATABASES[db_name]

    # Safety check
    if target_path.exists() and not force:
        return False, f"Target database exists: {target_path}. Use --force to overwrite."

    if dry_run:
        return True, f"Would restore {backup_path.name} -> {target_path}"

    # Verify backup checksum if available
    checksum_path = backup_path.with_suffix(backup_path.suffix + ".sha256")
    if checksum_path.exists():
        stored_checksum = checksum_path.read_text().split()[0]
        actual_checksum = compute_checksum(backup_path)
        if stored_checksum != actual_checksum:
            return False, f"Checksum mismatch! Backup may be corrupted."

    try:
        # Decompress if needed
        if info and info["compressed"]:
            temp_path = BACKUP_DIR / "restore_temp.db"
            with gzip.open(backup_path, "rb") as f_in:
                with open(temp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            source_path = temp_path
        else:
            source_path = backup_path

        # Verify backup integrity before restore
        is_valid, msg = verify_sqlite_integrity(source_path)
        if not is_valid:
            if source_path != backup_path:
                source_path.unlink()
            return False, f"Backup integrity check failed: {msg}"

        # Create backup of current database before overwriting
        if target_path.exists():
            pre_restore_backup = target_path.with_suffix(".pre_restore")
            shutil.copy2(target_path, pre_restore_backup)

        # Restore using file copy
        shutil.copy2(source_path, target_path)

        # Clean up temp file
        if source_path != backup_path and source_path.exists():
            source_path.unlink()

        return True, f"Restored {backup_path.name} -> {db_name}"

    except Exception as e:
        return False, f"Restore failed: {e}"


def verify_backup(backup_path: Path) -> tuple[bool, list[str]]:
    """
    Verify a backup file.

    Returns (is_valid, messages).
    """
    messages = []
    is_valid = True

    if not backup_path.exists():
        return False, [f"Backup file not found: {backup_path}"]

    # Check checksum
    checksum_path = backup_path.with_suffix(backup_path.suffix + ".sha256")
    if checksum_path.exists():
        stored_checksum = checksum_path.read_text().split()[0]
        actual_checksum = compute_checksum(backup_path)
        if stored_checksum == actual_checksum:
            messages.append(f"✓ Checksum verified: {actual_checksum[:16]}...")
        else:
            messages.append(f"✗ Checksum mismatch!")
            messages.append(f"  Expected: {stored_checksum[:16]}...")
            messages.append(f"  Actual:   {actual_checksum[:16]}...")
            is_valid = False
    else:
        messages.append("○ No checksum file (cannot verify integrity)")

    # Parse filename
    info = parse_backup_filename(backup_path.name)
    if info:
        messages.append(f"✓ Filename format valid")
        messages.append(f"  Database: {info['db_name']}")
        messages.append(f"  Timestamp: {info['timestamp'].isoformat()}")
        messages.append(f"  Compressed: {info['compressed']}")
    else:
        messages.append("○ Non-standard filename format")

    # Check SQLite integrity
    try:
        if info and info["compressed"]:
            # Decompress to temp file for verification
            temp_path = BACKUP_DIR / "verify_temp.db"
            with gzip.open(backup_path, "rb") as f_in:
                with open(temp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            check_path = temp_path
        else:
            check_path = backup_path

        integrity_ok, integrity_msg = verify_sqlite_integrity(check_path)

        if integrity_ok:
            messages.append(f"✓ SQLite integrity: {integrity_msg}")
        else:
            messages.append(f"✗ SQLite integrity: {integrity_msg}")
            is_valid = False

        # Get table count
        conn = sqlite3.connect(f"file:{check_path}?mode=ro", uri=True)
        cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        conn.close()
        messages.append(f"  Tables: {table_count}")

        # Clean up temp
        if info and info["compressed"] and temp_path.exists():
            temp_path.unlink()

    except Exception as e:
        messages.append(f"✗ Cannot verify SQLite: {e}")
        is_valid = False

    # File size
    size = backup_path.stat().st_size
    size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f}MB"
    messages.append(f"  Size: {size_str}")

    return is_valid, messages


def list_backups(db_name: Optional[str] = None) -> list[dict]:
    """List all available backups, optionally filtered by database name."""
    ensure_backup_dir()

    backups = []
    for f in BACKUP_DIR.glob("*.db*"):
        # Skip checksum files and temp files
        if f.suffix == ".sha256" or f.name.endswith(".tmp"):
            continue

        info = parse_backup_filename(f.name)
        if info:
            if db_name and info["db_name"] != db_name:
                continue
            info["path"] = f
            info["size"] = f.stat().st_size
            backups.append(info)

    # Sort by timestamp, newest first
    backups.sort(key=lambda x: x["timestamp"], reverse=True)
    return backups


def clean_old_backups(dry_run: bool = False) -> tuple[int, list[str]]:
    """
    Remove old backups according to retention policy.

    Keeps:
    - Last RETENTION_DAILY daily backups
    - Last RETENTION_WEEKLY weekly backups (oldest backup each week)

    Returns (deleted_count, messages).
    """
    messages = []
    deleted = 0

    for db_name in DATABASES:
        backups = list_backups(db_name)
        if not backups:
            continue

        # Separate into daily and weekly
        now = datetime.now()
        daily_cutoff = now - timedelta(days=RETENTION_DAILY)
        weekly_cutoff = now - timedelta(weeks=RETENTION_WEEKLY)

        to_keep = set()

        # Keep recent daily backups
        daily_backups = [b for b in backups if b["timestamp"] >= daily_cutoff]
        for b in daily_backups[:RETENTION_DAILY]:
            to_keep.add(b["path"])

        # Keep weekly backups (one per week)
        weekly_backups = {}
        for b in backups:
            if b["timestamp"] >= weekly_cutoff:
                week_key = b["timestamp"].isocalendar()[:2]  # (year, week)
                if week_key not in weekly_backups:
                    weekly_backups[week_key] = b

        for b in list(weekly_backups.values())[:RETENTION_WEEKLY]:
            to_keep.add(b["path"])

        # Delete old backups
        for b in backups:
            if b["path"] not in to_keep:
                if dry_run:
                    messages.append(f"Would delete: {b['filename']}")
                else:
                    b["path"].unlink()
                    # Also delete checksum file
                    checksum_path = b["path"].with_suffix(b["path"].suffix + ".sha256")
                    if checksum_path.exists():
                        checksum_path.unlink()
                    messages.append(f"Deleted: {b['filename']}")
                deleted += 1

    return deleted, messages


def show_status():
    """Show backup status for all databases."""
    print(f"\n{'=' * 60}")
    print("Civic Database Backup Status")
    print(f"{'=' * 60}")
    print(f"Backup directory: {BACKUP_DIR}")
    print(f"Retention policy: {RETENTION_DAILY} daily, {RETENTION_WEEKLY} weekly")

    for db_name, db_path in DATABASES.items():
        print(f"\n→ {db_name}")

        if db_path.exists():
            size = db_path.stat().st_size
            size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f}MB"
            print(f"  Source: {db_path} ({size_str})")
        else:
            print(f"  Source: {db_path} (NOT FOUND)")
            continue

        backups = list_backups(db_name)
        if backups:
            print(f"  Backups: {len(backups)}")
            # Show most recent
            latest = backups[0]
            age = datetime.now() - latest["timestamp"]
            age_str = f"{age.days}d" if age.days > 0 else f"{age.seconds // 3600}h"
            print(f"  Latest: {latest['filename']} ({age_str} ago)")
        else:
            print(f"  Backups: None")


def show_list(db_name: Optional[str] = None):
    """Display list of available backups."""
    backups = list_backups(db_name)

    if not backups:
        print("No backups found.")
        return

    print(f"\n{'=' * 60}")
    print(f"Available Backups ({len(backups)} total)")
    print(f"{'=' * 60}\n")

    current_db = None
    for b in backups:
        if b["db_name"] != current_db:
            current_db = b["db_name"]
            print(f"→ {current_db}:")

        age = datetime.now() - b["timestamp"]
        if age.days > 0:
            age_str = f"{age.days}d ago"
        elif age.seconds > 3600:
            age_str = f"{age.seconds // 3600}h ago"
        else:
            age_str = f"{age.seconds // 60}m ago"

        size_str = f"{b['size'] / 1024:.1f}KB" if b['size'] < 1024 * 1024 else f"{b['size'] / 1024 / 1024:.1f}MB"
        comp = " (compressed)" if b["compressed"] else ""

        print(f"    {b['filename']:<45} {size_str:>8}  {age_str}{comp}")


def main():
    parser = argparse.ArgumentParser(
        description="Backup and restore databases for Civic platform"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show backup status for all databases",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available backups",
    )
    parser.add_argument(
        "--verify",
        type=str,
        metavar="BACKUP",
        help="Verify a backup file integrity",
    )
    parser.add_argument(
        "--restore",
        type=str,
        metavar="BACKUP",
        help="Restore from a backup file",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove old backups per retention policy",
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress backups with gzip",
    )
    parser.add_argument(
        "--db",
        type=str,
        choices=list(DATABASES.keys()),
        help="Operate on specific database only",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing database on restore",
    )

    args = parser.parse_args()

    # Status command
    if args.status:
        show_status()
        return 0

    # List command
    if args.list:
        show_list(args.db)
        return 0

    # Verify command
    if args.verify:
        backup_path = Path(args.verify)
        if not backup_path.is_absolute():
            backup_path = BACKUP_DIR / backup_path

        print(f"\nVerifying: {backup_path.name}")
        print("-" * 40)

        is_valid, messages = verify_backup(backup_path)
        for msg in messages:
            print(f"  {msg}")

        print("-" * 40)
        if is_valid:
            print("Result: VALID")
            return 0
        else:
            print("Result: INVALID")
            return 1

    # Restore command
    if args.restore:
        backup_path = Path(args.restore)
        if not backup_path.is_absolute():
            backup_path = BACKUP_DIR / backup_path

        print(f"\n{'=' * 60}")
        print("Civic Database Restore")
        print(f"{'=' * 60}")

        if args.dry_run:
            print("Mode: DRY RUN (no changes will be made)\n")

        success, msg = restore_database(
            backup_path,
            target_db=args.db,
            dry_run=args.dry_run,
            force=args.force,
        )

        if success:
            print(f"✓ {msg}")
            return 0
        else:
            print(f"✗ {msg}")
            return 1

    # Clean command
    if args.clean:
        print(f"\n{'=' * 60}")
        print("Cleaning Old Backups")
        print(f"{'=' * 60}")
        print(f"Retention: {RETENTION_DAILY} daily, {RETENTION_WEEKLY} weekly")

        if args.dry_run:
            print("Mode: DRY RUN (no changes will be made)\n")

        deleted, messages = clean_old_backups(dry_run=args.dry_run)
        for msg in messages:
            print(f"  {msg}")

        if deleted == 0:
            print("\nNo old backups to remove.")
        else:
            print(f"\n{'Would remove' if args.dry_run else 'Removed'}: {deleted} backup(s)")

        return 0

    # Default: run backup
    print(f"\n{'=' * 60}")
    print("Civic Database Backup")
    print(f"{'=' * 60}")

    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)\n")

    # Select databases to backup
    if args.db:
        dbs = {args.db: DATABASES[args.db]}
    else:
        dbs = DATABASES

    total_success = 0
    total_failed = 0

    for db_name, db_path in dbs.items():
        success, msg, backup_path = backup_database(
            db_name,
            db_path,
            compress=args.compress,
            dry_run=args.dry_run,
        )

        if success:
            print(f"✓ {msg}")
            total_success += 1
        else:
            print(f"✗ {msg}")
            total_failed += 1

    # Summary
    print(f"\n{'=' * 60}")
    if args.dry_run:
        print(f"Dry run complete: {total_success} would be backed up")
    else:
        print(f"Backup complete: {total_success} succeeded, {total_failed} failed")

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
