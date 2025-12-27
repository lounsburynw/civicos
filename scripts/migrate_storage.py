#!/usr/bin/env python3
"""
Storage migration script for Civic platform.

Promotes local development data to cloud storage for pilot deployment.

Migrations:
- SQLite → PostgreSQL (structured data)
- Local files → R2 (binary blobs)
- ChromaDB → Fly.io volume (vector embeddings)

Usage:
    # Dry run (show what would be migrated)
    python scripts/migrate_storage.py --dry-run

    # Migrate all data types
    python scripts/migrate_storage.py --target-postgres "postgresql://..." --target-r2 "r2://..."

    # Migrate specific data types
    python scripts/migrate_storage.py --only database
    python scripts/migrate_storage.py --only blobs
    python scripts/migrate_storage.py --only vectors

    # Verify migration
    python scripts/migrate_storage.py --verify

Environment variables:
    TARGET_POSTGRES_URL: PostgreSQL connection string (or --target-postgres)
    TARGET_R2_URL: R2 bucket URL (or --target-r2)
    R2_ACCESS_KEY_ID: R2 credentials (required for R2 migration)
    R2_SECRET_ACCESS_KEY: R2 credentials (required for R2 migration)
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add packages to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic" / "src"))

from civic.storage.sqlite_backend import SQLiteBackend
from civic.storage.blob import LocalBlobBackend, get_blob_storage, BlobStorage


@dataclass
class MigrationManifest:
    """Tracks migration progress for idempotency and resumability."""

    started_at: str
    completed_at: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed

    # Counts for verification
    source_meetings: int = 0
    source_decisions: int = 0
    source_chunks: int = 0
    source_blobs: int = 0
    source_vectors: int = 0

    migrated_meetings: int = 0
    migrated_decisions: int = 0
    migrated_chunks: int = 0
    migrated_blobs: int = 0
    migrated_vectors: int = 0

    # Checksums for verification
    checksums: Dict[str, str] = field(default_factory=dict)

    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "source_meetings": self.source_meetings,
            "source_decisions": self.source_decisions,
            "source_chunks": self.source_chunks,
            "source_blobs": self.source_blobs,
            "source_vectors": self.source_vectors,
            "migrated_meetings": self.migrated_meetings,
            "migrated_decisions": self.migrated_decisions,
            "migrated_chunks": self.migrated_chunks,
            "migrated_blobs": self.migrated_blobs,
            "migrated_vectors": self.migrated_vectors,
            "checksums": self.checksums,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MigrationManifest":
        """Load from dictionary."""
        return cls(
            started_at=data.get("started_at", datetime.now().isoformat()),
            completed_at=data.get("completed_at"),
            status=data.get("status", "pending"),
            source_meetings=data.get("source_meetings", 0),
            source_decisions=data.get("source_decisions", 0),
            source_chunks=data.get("source_chunks", 0),
            source_blobs=data.get("source_blobs", 0),
            source_vectors=data.get("source_vectors", 0),
            migrated_meetings=data.get("migrated_meetings", 0),
            migrated_decisions=data.get("migrated_decisions", 0),
            migrated_chunks=data.get("migrated_chunks", 0),
            migrated_blobs=data.get("migrated_blobs", 0),
            migrated_vectors=data.get("migrated_vectors", 0),
            checksums=data.get("checksums", {}),
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )


class StorageMigration:
    """
    Orchestrates data migration from local dev to cloud storage.

    Provides:
    - Idempotent migrations (safe to run multiple times)
    - Progress reporting
    - Dry-run mode
    - Verification after migration
    """

    def __init__(
        self,
        jurisdictions: List[str],
        source_db_path: Optional[str] = None,
        target_postgres_url: Optional[str] = None,
        source_blobs_path: str = "data/blobs",
        target_r2_url: Optional[str] = None,
        vectors_dir: str = "apps/civic-workspace/data/vectors",
        manifest_path: str = "data/migration_manifest.json",
        dry_run: bool = False,
        verbose: bool = False,
    ):
        """
        Initialize storage migration.

        Args:
            jurisdictions: List of jurisdiction IDs to migrate
            source_db_path: Path to source SQLite database
            target_postgres_url: PostgreSQL connection string
            source_blobs_path: Path to local blob storage
            target_r2_url: R2 bucket URL
            vectors_dir: Path to ChromaDB vector storage
            manifest_path: Path to save migration manifest
            dry_run: If True, show what would be done without making changes
            verbose: If True, print detailed progress
        """
        self.jurisdictions = jurisdictions
        self.target_postgres_url = target_postgres_url
        self.target_r2_url = target_r2_url
        self.vectors_dir = Path(vectors_dir)
        self.manifest_path = Path(manifest_path)
        self.dry_run = dry_run
        self.verbose = verbose

        # Initialize source backends
        self.source_db = SQLiteBackend(source_db_path) if source_db_path else SQLiteBackend()
        self.source_blobs = LocalBlobBackend(source_blobs_path)

        # Target backends initialized lazily
        self._target_db = None
        self._target_blobs = None

        # Load or create manifest
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> MigrationManifest:
        """Load existing manifest or create new one."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    return MigrationManifest.from_dict(json.load(f))
            except Exception as e:
                self._log(f"Warning: Could not load manifest: {e}")

        return MigrationManifest(started_at=datetime.now().isoformat())

    def _save_manifest(self) -> None:
        """Save manifest to disk."""
        if self.dry_run:
            return

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w") as f:
            json.dump(self.manifest.to_dict(), f, indent=2)

    def _log(self, message: str, force: bool = False) -> None:
        """Print log message if verbose or forced."""
        if self.verbose or force:
            print(message)

    def _log_progress(self, step: str, current: int, total: int) -> None:
        """Print progress update."""
        pct = (current / total * 100) if total > 0 else 100
        print(f"  [{step}] {current}/{total} ({pct:.1f}%)")

    @property
    def target_db(self):
        """Lazily initialize target database backend."""
        if self._target_db is None:
            if not self.target_postgres_url:
                raise ValueError("target_postgres_url required for database migration")

            from civic.storage.postgres_backend import PostgresBackend
            self._target_db = PostgresBackend(self.target_postgres_url)

        return self._target_db

    @property
    def target_blobs(self) -> BlobStorage:
        """Lazily initialize target blob backend."""
        if self._target_blobs is None:
            if not self.target_r2_url:
                raise ValueError("target_r2_url required for blob migration")

            self._target_blobs = get_blob_storage(self.target_r2_url)

        return self._target_blobs

    def validate_source(self) -> bool:
        """
        Validate source storage is accessible and has data.

        Returns:
            True if validation passes
        """
        print("\n=== Validating Source Storage ===")
        errors = []

        # Validate SQLite
        result = self.source_db.validate()
        if result.is_valid:
            print(f"  ✓ SQLite database: {self.source_db._db_path}")
        else:
            errors.extend(result.errors)
            print(f"  ✗ SQLite database: {result.errors}")

        # Count source data
        for jid in self.jurisdictions:
            stats = self.source_db.get_stats(jid)
            decisions = self.source_db.get_decision_count(jid)
            chunks = self.source_db.get_chunk_count(jid)

            print(f"  {jid}: {stats.meeting_count} meetings, {decisions} decisions, {chunks} chunks")

            self.manifest.source_meetings += stats.meeting_count
            self.manifest.source_decisions += decisions
            self.manifest.source_chunks += chunks

        # Validate blob storage
        blob_result = self.source_blobs.validate()
        if blob_result.is_valid:
            blob_stats = self.source_blobs.get_stats()
            print(f"  ✓ Blob storage: {blob_stats.total_objects} files, {blob_stats.total_bytes:,} bytes")
            self.manifest.source_blobs = blob_stats.total_objects
        else:
            print(f"  ⚠ Blob storage: {blob_result.errors or 'No files'}")

        # Check vector storage
        if self.vectors_dir.exists():
            vector_dirs = list(self.vectors_dir.glob("*/"))
            print(f"  ✓ Vector storage: {len(vector_dirs)} collections")
            self.manifest.source_vectors = len(vector_dirs)
        else:
            print(f"  ⚠ Vector storage: directory not found")

        if errors:
            self.manifest.errors.extend(errors)
            return False

        return True

    def validate_target(self) -> bool:
        """
        Validate target storage is accessible and ready.

        Returns:
            True if validation passes
        """
        print("\n=== Validating Target Storage ===")
        errors = []

        # Validate PostgreSQL (if URL provided)
        if self.target_postgres_url:
            try:
                result = self.target_db.validate()
                if result.is_valid:
                    print(f"  ✓ PostgreSQL: connected")
                else:
                    if result.warnings:
                        print(f"  ⚠ PostgreSQL: {result.warnings[0]}")
                    else:
                        errors.extend(result.errors)
                        print(f"  ✗ PostgreSQL: {result.errors}")
            except Exception as e:
                errors.append(str(e))
                print(f"  ✗ PostgreSQL: {e}")
        else:
            print("  - PostgreSQL: skipped (no URL provided)")

        # Validate R2 (if URL provided)
        if self.target_r2_url:
            try:
                result = self.target_blobs.validate()
                if result.is_valid:
                    print(f"  ✓ R2: connected and writable")
                else:
                    errors.extend(result.errors)
                    print(f"  ✗ R2: {result.errors}")
            except Exception as e:
                errors.append(str(e))
                print(f"  ✗ R2: {e}")
        else:
            print("  - R2: skipped (no URL provided)")

        if errors:
            self.manifest.errors.extend(errors)
            return False

        return True

    def migrate_database(self) -> bool:
        """
        Migrate SQLite data to PostgreSQL.

        Returns:
            True if migration succeeds
        """
        if not self.target_postgres_url:
            print("\n=== Database Migration: SKIPPED (no target URL) ===")
            return True

        print("\n=== Database Migration: SQLite → PostgreSQL ===")

        if self.dry_run:
            print("  [DRY RUN] Would migrate:")
            print(f"    - {self.manifest.source_meetings} meetings")
            print(f"    - {self.manifest.source_decisions} decisions")
            print(f"    - {self.manifest.source_chunks} chunks")
            return True

        total_meetings = 0
        total_decisions = 0
        total_chunks = 0

        for jid in self.jurisdictions:
            print(f"\n  Migrating {jid}...")

            # Migrate meetings
            meetings = self.source_db.get_meetings(jid)
            if meetings:
                count = self.target_db.store_meetings(jid, meetings)
                total_meetings += count
                self._log(f"    ✓ {count} meetings")

            # Migrate decisions
            decisions = self.source_db.get_decisions(jid)
            if decisions:
                count = self.target_db.store_decisions(jid, decisions)
                total_decisions += count
                self._log(f"    ✓ {count} decisions")

            # Migrate chunks
            chunks = self.source_db.get_chunks(jid)
            if chunks:
                count = self.target_db.store_chunks(jid, chunks)
                total_chunks += count
                self._log(f"    ✓ {count} chunks")

        self.manifest.migrated_meetings = total_meetings
        self.manifest.migrated_decisions = total_decisions
        self.manifest.migrated_chunks = total_chunks

        print(f"\n  ✓ Database migration complete:")
        print(f"    - {total_meetings} meetings")
        print(f"    - {total_decisions} decisions")
        print(f"    - {total_chunks} chunks")

        return True

    def migrate_blobs(self) -> bool:
        """
        Migrate local blob files to R2.

        Returns:
            True if migration succeeds
        """
        if not self.target_r2_url:
            print("\n=== Blob Migration: SKIPPED (no target URL) ===")
            return True

        print("\n=== Blob Migration: Local → R2 ===")

        # List all source blobs
        source_keys = self.source_blobs.list_keys()

        if not source_keys:
            print("  No blobs to migrate")
            return True

        if self.dry_run:
            print(f"  [DRY RUN] Would migrate {len(source_keys)} files:")
            for key in source_keys[:5]:
                print(f"    - {key}")
            if len(source_keys) > 5:
                print(f"    ... and {len(source_keys) - 5} more")
            return True

        migrated = 0
        skipped = 0
        errors = []

        for i, key in enumerate(source_keys):
            try:
                # Check if already exists in target
                if self.target_blobs.exists(key):
                    skipped += 1
                    self._log(f"    ⊘ {key} (already exists)")
                    continue

                # Download from source
                data = self.source_blobs.download(key)

                # Infer content type from extension
                content_type = None
                if key.endswith(".pdf"):
                    content_type = "application/pdf"
                elif key.endswith(".mp3"):
                    content_type = "audio/mpeg"
                elif key.endswith(".mp4"):
                    content_type = "video/mp4"
                elif key.endswith(".json"):
                    content_type = "application/json"

                # Upload to target
                self.target_blobs.upload(key, data, content_type=content_type)
                migrated += 1

                if (i + 1) % 10 == 0 or (i + 1) == len(source_keys):
                    self._log_progress("blobs", i + 1, len(source_keys))

            except Exception as e:
                errors.append(f"{key}: {e}")
                self._log(f"    ✗ {key}: {e}")

        self.manifest.migrated_blobs = migrated

        print(f"\n  ✓ Blob migration complete:")
        print(f"    - {migrated} migrated")
        print(f"    - {skipped} skipped (already exist)")
        if errors:
            print(f"    - {len(errors)} errors")
            self.manifest.errors.extend(errors)

        return len(errors) == 0

    def migrate_vectors(self) -> bool:
        """
        Prepare vector storage for Fly.io deployment.

        ChromaDB stores data in a local directory. For Fly.io deployment:
        1. Package the vector directory
        2. Document the volume mount configuration

        Returns:
            True if preparation succeeds
        """
        print("\n=== Vector Storage: ChromaDB → Fly.io Volume ===")

        if not self.vectors_dir.exists():
            print("  No vector storage directory found")
            return True

        # Calculate directory size
        total_size = 0
        file_count = 0
        for path in self.vectors_dir.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size
                file_count += 1

        print(f"  Vector storage: {file_count} files, {total_size / 1024 / 1024:.1f} MB")

        if self.dry_run:
            print("  [DRY RUN] Would prepare vector storage for Fly.io volume mount")
            print(f"  Recommended volume size: {max(1, int(total_size / 1024 / 1024 / 1024) + 1)} GB")
            return True

        # Create deployment instructions
        instructions = f"""
# ChromaDB Vector Storage Deployment

Vector storage is file-based and requires a Fly.io persistent volume.

## Current Storage
- Location: {self.vectors_dir}
- Files: {file_count}
- Size: {total_size / 1024 / 1024:.1f} MB

## Fly.io Volume Setup

1. Create volume (from project root):
   ```bash
   fly volumes create civic_vectors --region sjc --size 3
   ```

2. Configure fly.toml mount:
   ```toml
   [[mounts]]
     source = "civic_vectors"
     destination = "/app/data/vectors"
   ```

3. Copy vector data to volume:
   ```bash
   # During first deployment, use fly ssh console
   fly ssh console
   # Then rsync or scp the vectors directory
   ```

4. Verify deployment:
   ```bash
   fly ssh console -C "ls -la /app/data/vectors"
   ```

## Alternative: Re-index on Deployment

If vector data is too large, re-index from SQL:
1. Deploy with empty volume
2. Run indexing job: `python -m civic.jobs.reindex --jurisdiction city-san-rafael`
"""

        instructions_path = Path("docs/deployment/vector_storage_setup.md")
        if not self.dry_run:
            instructions_path.parent.mkdir(parents=True, exist_ok=True)
            instructions_path.write_text(instructions)
            print(f"  ✓ Deployment instructions: {instructions_path}")

        self.manifest.migrated_vectors = file_count
        return True

    def verify_migration(self) -> bool:
        """
        Verify migration by comparing source and target counts.

        Returns:
            True if verification passes
        """
        print("\n=== Verification ===")
        errors = []

        # Verify database
        if self.target_postgres_url:
            for jid in self.jurisdictions:
                source_meetings = len(self.source_db.get_meetings(jid))
                target_meetings = len(self.target_db.get_meetings(jid))

                if source_meetings != target_meetings:
                    errors.append(
                        f"{jid} meetings: source={source_meetings}, target={target_meetings}"
                    )
                    print(f"  ✗ {jid} meetings: {source_meetings} → {target_meetings}")
                else:
                    print(f"  ✓ {jid} meetings: {target_meetings}")

                source_decisions = self.source_db.get_decision_count(jid)
                target_decisions = self.target_db.get_decision_count(jid)

                if source_decisions != target_decisions:
                    errors.append(
                        f"{jid} decisions: source={source_decisions}, target={target_decisions}"
                    )
                    print(f"  ✗ {jid} decisions: {source_decisions} → {target_decisions}")
                else:
                    print(f"  ✓ {jid} decisions: {target_decisions}")

        # Verify blobs
        if self.target_r2_url:
            source_keys = set(self.source_blobs.list_keys())
            target_keys = set(self.target_blobs.list_keys())

            missing = source_keys - target_keys
            if missing:
                errors.append(f"Missing blobs: {len(missing)}")
                print(f"  ✗ Blobs: {len(missing)} missing")
                for key in list(missing)[:3]:
                    print(f"      - {key}")
            else:
                print(f"  ✓ Blobs: {len(target_keys)} files")

        if errors:
            self.manifest.errors.extend(errors)
            return False

        print("\n  ✓ All verifications passed")
        return True

    def run(
        self,
        only: Optional[str] = None,
        verify: bool = False,
    ) -> bool:
        """
        Run the complete migration.

        Args:
            only: Migrate only specific type (database, blobs, vectors)
            verify: Only run verification, skip migration

        Returns:
            True if migration succeeds
        """
        start_time = time.time()
        self.manifest.status = "running"

        print("=" * 50)
        print("CIVIC STORAGE MIGRATION")
        print("=" * 50)
        print(f"Jurisdictions: {', '.join(self.jurisdictions)}")
        print(f"Dry run: {self.dry_run}")
        print(f"Started: {datetime.now().isoformat()}")

        try:
            # Validate source
            if not self.validate_source():
                self.manifest.status = "failed"
                self._save_manifest()
                return False

            # Validate target (unless dry run)
            if not self.dry_run and not verify:
                if not self.validate_target():
                    self.manifest.status = "failed"
                    self._save_manifest()
                    return False

            # Run migrations
            if not verify:
                if only is None or only == "database":
                    if not self.migrate_database():
                        self.manifest.status = "failed"
                        self._save_manifest()
                        return False

                if only is None or only == "blobs":
                    if not self.migrate_blobs():
                        self.manifest.status = "failed"
                        self._save_manifest()
                        return False

                if only is None or only == "vectors":
                    if not self.migrate_vectors():
                        self.manifest.status = "failed"
                        self._save_manifest()
                        return False

            # Verify
            if not self.dry_run and (verify or only is None):
                if not self.verify_migration():
                    self.manifest.status = "failed"
                    self._save_manifest()
                    return False

            # Success
            duration = time.time() - start_time
            self.manifest.status = "completed"
            self.manifest.completed_at = datetime.now().isoformat()
            self._save_manifest()

            print("\n" + "=" * 50)
            print("MIGRATION COMPLETE")
            print("=" * 50)
            print(f"Duration: {duration:.1f} seconds")
            if not self.dry_run:
                print(f"Manifest: {self.manifest_path}")

            return True

        except Exception as e:
            self.manifest.status = "failed"
            self.manifest.errors.append(str(e))
            self._save_manifest()
            print(f"\n✗ Migration failed: {e}")
            raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate Civic storage from local to cloud",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--jurisdiction", "-j",
        action="append",
        dest="jurisdictions",
        help="Jurisdiction to migrate (can specify multiple, default: city-san-rafael)",
    )

    parser.add_argument(
        "--target-postgres",
        metavar="URL",
        help="PostgreSQL connection string (or TARGET_POSTGRES_URL env var)",
    )

    parser.add_argument(
        "--target-r2",
        metavar="URL",
        help="R2 bucket URL r2://account/bucket (or TARGET_R2_URL env var)",
    )

    parser.add_argument(
        "--source-db",
        metavar="PATH",
        help="Source SQLite database path (default: auto-detect)",
    )

    parser.add_argument(
        "--source-blobs",
        metavar="PATH",
        default="data/blobs",
        help="Source blob storage path (default: data/blobs)",
    )

    parser.add_argument(
        "--vectors-dir",
        metavar="PATH",
        default="apps/civic-workspace/data/vectors",
        help="ChromaDB vectors directory (default: apps/civic-workspace/data/vectors)",
    )

    parser.add_argument(
        "--only",
        choices=["database", "blobs", "vectors"],
        help="Migrate only specific data type",
    )

    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify migration, skip actual migration",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed progress",
    )

    args = parser.parse_args()

    # Default jurisdictions
    jurisdictions = args.jurisdictions or ["city-san-rafael"]

    # Get target URLs from args or environment
    target_postgres = args.target_postgres or os.getenv("TARGET_POSTGRES_URL")
    target_r2 = args.target_r2 or os.getenv("TARGET_R2_URL")

    # Create migration
    migration = StorageMigration(
        jurisdictions=jurisdictions,
        source_db_path=args.source_db,
        target_postgres_url=target_postgres,
        source_blobs_path=args.source_blobs,
        target_r2_url=target_r2,
        vectors_dir=args.vectors_dir,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    # Run migration
    success = migration.run(only=args.only, verify=args.verify)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
