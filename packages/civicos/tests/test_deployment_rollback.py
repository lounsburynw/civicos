"""
Tests for deployment rollback procedures.

This module verifies that the backup/restore mechanisms work correctly,
providing confidence that the documented rollback procedures are reliable.

The tests cover:
- Backup creation with checksums
- Restore from backup with integrity verification
- Checksum mismatch detection (corrupted backup rejection)
- Compressed backup support
- SQLite integrity verification
- Retention policy logic
"""

import gzip
import hashlib
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Add scripts directory to path for backup module import
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from backup import (
    backup_database,
    clean_old_backups,
    compute_checksum,
    get_backup_filename,
    list_backups,
    parse_backup_filename,
    restore_database,
    verify_backup,
    verify_sqlite_integrity,
    BACKUP_DIR,
    DATABASES,
    RETENTION_DAILY,
    RETENTION_WEEKLY,
)

# Mark as slow: backup/restore operations with time.sleep() delays
pytestmark = pytest.mark.slow


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def test_backup_dir(tmp_path):
    """Create isolated backup directory for testing."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@pytest.fixture
def test_db(tmp_path):
    """Create a test SQLite database with sample data."""
    db_path = tmp_path / "test_civic.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob'), ('Charlie')")
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings (key, value) VALUES ('version', '1.0')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def test_db_with_more_data(tmp_path):
    """Create a larger test database for compression testing."""
    db_path = tmp_path / "test_civic_large.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, data TEXT)")
    # Insert enough data to make compression meaningful
    for i in range(1000):
        conn.execute(
            "INSERT INTO events (data) VALUES (?)",
            (f"Event data {i} with some repetitive content for compression" * 10,),
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def monkeypatch_backup_paths(monkeypatch, test_backup_dir, tmp_path):
    """Redirect backup module paths to test directories."""
    import backup as backup_module

    # Create test database files
    test_databases = {
        "test_state": tmp_path / "civic_state.db",
        "test_participation": tmp_path / "civic_participation.db",
    }

    # Initialize test databases
    for name, path in test_databases.items():
        conn = sqlite3.connect(path)
        conn.execute(f"CREATE TABLE test_{name} (id INTEGER PRIMARY KEY, data TEXT)")
        conn.execute(f"INSERT INTO test_{name} (data) VALUES ('sample data')")
        conn.commit()
        conn.close()

    monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
    monkeypatch.setattr(backup_module, "DATABASES", test_databases)

    return test_databases


# ============================================================================
# Unit Tests: Core Functions
# ============================================================================


class TestChecksumComputation:
    """Tests for checksum computation."""

    def test_compute_checksum_deterministic(self, tmp_path):
        """Checksum should be deterministic for same content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        checksum1 = compute_checksum(test_file)
        checksum2 = compute_checksum(test_file)

        assert checksum1 == checksum2
        assert len(checksum1) == 64  # SHA256 hex digest length

    def test_compute_checksum_changes_with_content(self, tmp_path):
        """Checksum should change when content changes."""
        test_file = tmp_path / "test.txt"

        test_file.write_text("Content A")
        checksum_a = compute_checksum(test_file)

        test_file.write_text("Content B")
        checksum_b = compute_checksum(test_file)

        assert checksum_a != checksum_b


class TestBackupFilenameGeneration:
    """Tests for backup filename parsing and generation."""

    def test_get_backup_filename_format(self):
        """Backup filename should follow expected format."""
        ts = datetime(2025, 1, 15, 10, 30, 45)
        filename = get_backup_filename("civic_state", ts, compressed=False)

        assert filename == "civic_state_20250115_103045.db"

    def test_get_backup_filename_compressed(self):
        """Compressed backup should have .db.gz extension."""
        ts = datetime(2025, 1, 15, 10, 30, 45)
        filename = get_backup_filename("civic_state", ts, compressed=True)

        assert filename == "civic_state_20250115_103045.db.gz"

    def test_parse_backup_filename_valid(self):
        """Should parse valid backup filename."""
        info = parse_backup_filename("civic_state_20250115_103045.db")

        assert info is not None
        assert info["db_name"] == "civic_state"
        assert info["timestamp"] == datetime(2025, 1, 15, 10, 30, 45)
        assert info["compressed"] is False
        assert info["filename"] == "civic_state_20250115_103045.db"

    def test_parse_backup_filename_compressed(self):
        """Should parse compressed backup filename."""
        info = parse_backup_filename("civic_state_20250115_103045.db.gz")

        assert info is not None
        assert info["compressed"] is True

    def test_parse_backup_filename_invalid(self):
        """Should return None for invalid filename format."""
        assert parse_backup_filename("invalid_backup.db") is None
        assert parse_backup_filename("backup.txt") is None
        assert parse_backup_filename("civic_state_invalid_date.db") is None


class TestSQLiteIntegrity:
    """Tests for SQLite integrity verification."""

    def test_verify_integrity_valid_database(self, test_db):
        """Should pass for valid database."""
        is_valid, message = verify_sqlite_integrity(test_db)

        assert is_valid is True
        assert "passed" in message.lower()

    def test_verify_integrity_nonexistent_file(self, tmp_path):
        """Should fail for non-existent file."""
        nonexistent = tmp_path / "nonexistent.db"
        is_valid, message = verify_sqlite_integrity(nonexistent)

        assert is_valid is False
        assert "cannot open" in message.lower()

    def test_verify_integrity_corrupted_database(self, tmp_path):
        """Should fail for corrupted database."""
        corrupted = tmp_path / "corrupted.db"
        # Write random data that isn't valid SQLite
        corrupted.write_bytes(b"not a valid sqlite database content")

        is_valid, message = verify_sqlite_integrity(corrupted)

        assert is_valid is False


# ============================================================================
# Integration Tests: Backup/Restore Cycle
# ============================================================================


class TestBackupDatabase:
    """Tests for database backup functionality."""

    def test_backup_creates_file_and_checksum(self, test_db, test_backup_dir, monkeypatch):
        """Backup should create both database file and checksum."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        success, message, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=False
        )

        assert success is True
        assert backup_path is not None
        assert backup_path.exists()

        # Check checksum file exists
        checksum_file = backup_path.with_suffix(backup_path.suffix + ".sha256")
        assert checksum_file.exists()

        # Verify checksum content format
        checksum_content = checksum_file.read_text()
        assert len(checksum_content.split()[0]) == 64  # SHA256 hex

    def test_backup_dry_run_no_files(self, test_db, test_backup_dir, monkeypatch):
        """Dry run should not create any files."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        success, message, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=True
        )

        assert success is True
        assert "Would backup" in message
        # No files should exist in backup dir
        assert len(list(test_backup_dir.glob("*.db*"))) == 0

    def test_backup_nonexistent_database(self, tmp_path, test_backup_dir, monkeypatch):
        """Backup should fail for non-existent database."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        nonexistent = tmp_path / "nonexistent.db"
        success, message, backup_path = backup_database(
            "test_civic", nonexistent, compress=False, dry_run=False
        )

        assert success is False
        assert "not found" in message.lower()

    def test_backup_compressed(self, test_db_with_more_data, test_backup_dir, monkeypatch):
        """Compressed backup should be smaller than original."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        success, message, backup_path = backup_database(
            "test_civic", test_db_with_more_data, compress=True, dry_run=False
        )

        assert success is True
        assert backup_path.suffix == ".gz"

        # Compressed should be smaller than original
        original_size = test_db_with_more_data.stat().st_size
        compressed_size = backup_path.stat().st_size
        assert compressed_size < original_size


class TestRestoreDatabase:
    """Tests for database restore functionality."""

    def test_restore_from_backup(self, test_db, test_backup_dir, tmp_path, monkeypatch):
        """Should successfully restore database from backup."""
        import backup as backup_module

        # Setup isolated test databases
        test_databases = {"test_civic": tmp_path / "target_civic.db"}
        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
        monkeypatch.setattr(backup_module, "DATABASES", test_databases)

        # Create backup
        success, _, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=False
        )
        assert success is True

        # Restore to target
        success, message = restore_database(
            backup_path, target_db="test_civic", dry_run=False, force=True
        )

        assert success is True
        assert test_databases["test_civic"].exists()

        # Verify restored data
        conn = sqlite3.connect(test_databases["test_civic"])
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 3  # Original had 3 users

    def test_restore_rejects_without_force(
        self, test_db, test_backup_dir, tmp_path, monkeypatch
    ):
        """Restore should reject overwriting existing database without --force."""
        import backup as backup_module

        # Create target that already exists
        target_path = tmp_path / "existing.db"
        conn = sqlite3.connect(target_path)
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.close()

        test_databases = {"test_civic": target_path}
        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
        monkeypatch.setattr(backup_module, "DATABASES", test_databases)

        # Create backup
        success, _, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=False
        )

        # Try restore without force
        success, message = restore_database(
            backup_path, target_db="test_civic", dry_run=False, force=False
        )

        assert success is False
        assert "exists" in message.lower()

    def test_restore_rejects_corrupted_checksum(
        self, test_db, test_backup_dir, tmp_path, monkeypatch
    ):
        """Restore should reject backup with mismatched checksum."""
        import backup as backup_module

        test_databases = {"test_civic": tmp_path / "target_civic.db"}
        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
        monkeypatch.setattr(backup_module, "DATABASES", test_databases)

        # Create backup
        success, _, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=False
        )
        assert success is True

        # Corrupt the checksum file
        checksum_file = backup_path.with_suffix(backup_path.suffix + ".sha256")
        checksum_file.write_text("0000000000000000000000000000000000000000000000000000000000000000  backup.db\n")

        # Try restore - should fail due to checksum mismatch
        success, message = restore_database(
            backup_path, target_db="test_civic", dry_run=False, force=True
        )

        assert success is False
        assert "checksum" in message.lower()

    def test_restore_compressed_backup(
        self, test_db_with_more_data, test_backup_dir, tmp_path, monkeypatch
    ):
        """Should restore from compressed backup."""
        import backup as backup_module

        test_databases = {"test_civic": tmp_path / "target_civic.db"}
        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
        monkeypatch.setattr(backup_module, "DATABASES", test_databases)

        # Create compressed backup
        success, _, backup_path = backup_database(
            "test_civic", test_db_with_more_data, compress=True, dry_run=False
        )
        assert success is True
        assert backup_path.suffix == ".gz"

        # Restore from compressed
        success, message = restore_database(
            backup_path, target_db="test_civic", dry_run=False, force=True
        )

        assert success is True

        # Verify data integrity
        conn = sqlite3.connect(test_databases["test_civic"])
        cursor = conn.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1000  # Original had 1000 events

    def test_restore_creates_pre_restore_backup(
        self, test_backup_dir, tmp_path, monkeypatch
    ):
        """Restore should create pre-restore backup of existing database."""
        import backup as backup_module

        # Create target with existing data
        target_path = tmp_path / "target_civic.db"
        conn = sqlite3.connect(target_path)
        conn.execute("CREATE TABLE existing_data (id INTEGER)")
        conn.execute("INSERT INTO existing_data (id) VALUES (999)")
        conn.commit()
        conn.close()

        # Create a source database to backup from
        source_path = tmp_path / "source.db"
        conn = sqlite3.connect(source_path)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('Alice')")
        conn.commit()
        conn.close()

        test_databases = {"test_civic": target_path}
        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
        monkeypatch.setattr(backup_module, "DATABASES", test_databases)

        # Create backup from source
        success, _, backup_path = backup_module.backup_database(
            "test_civic", source_path, compress=False, dry_run=False
        )
        assert success is True

        # Restore (which should preserve the existing target)
        success, message = backup_module.restore_database(
            backup_path, target_db="test_civic", dry_run=False, force=True
        )

        assert success is True

        # Check pre-restore backup was created
        pre_restore = target_path.with_suffix(".pre_restore")
        assert pre_restore.exists()

        # Verify pre-restore backup contains original target data
        conn = sqlite3.connect(pre_restore)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "existing_data" in tables, f"Expected 'existing_data' in {tables}"
        cursor = conn.execute("SELECT id FROM existing_data")
        row = cursor.fetchone()
        conn.close()
        assert row is not None, "No rows found in existing_data table"
        assert row[0] == 999

        # Verify target now has restored source data
        conn = sqlite3.connect(target_path)
        target_tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "users" in target_tables, f"Expected 'users' table in target, got {target_tables}"
        cursor = conn.execute("SELECT name FROM users")
        row = cursor.fetchone()
        conn.close()
        assert row is not None, "No rows found in users table"
        assert row[0] == "Alice"


class TestVerifyBackup:
    """Tests for backup verification."""

    def test_verify_valid_backup(self, test_db, test_backup_dir, monkeypatch):
        """Should verify valid backup successfully."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        success, _, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=False
        )

        is_valid, messages = verify_backup(backup_path)

        assert is_valid is True
        assert any("checksum verified" in m.lower() for m in messages)
        assert any("integrity" in m.lower() and "passed" in m.lower() for m in messages)

    def test_verify_missing_checksum(self, test_db, test_backup_dir, monkeypatch):
        """Should warn when checksum file is missing."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        success, _, backup_path = backup_database(
            "test_civic", test_db, compress=False, dry_run=False
        )

        # Remove checksum file
        checksum_file = backup_path.with_suffix(backup_path.suffix + ".sha256")
        checksum_file.unlink()

        is_valid, messages = verify_backup(backup_path)

        # Should still be valid (integrity check passes) but with warning
        assert is_valid is True
        assert any("no checksum" in m.lower() for m in messages)


class TestListBackups:
    """Tests for listing backups."""

    def test_list_backups_empty(self, test_backup_dir, monkeypatch):
        """Should return empty list when no backups exist."""
        import backup as backup_module

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        backups = list_backups()
        assert backups == []

    def test_list_backups_sorted_by_date(self, test_db, test_backup_dir, monkeypatch):
        """Should list backups sorted by date, newest first."""
        import backup as backup_module
        import time

        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)

        # Create multiple backups with delays long enough for distinct timestamps
        # Backup filename uses seconds precision, so we need at least 1 second between
        backup_database("test_civic", test_db, compress=False, dry_run=False)
        time.sleep(1.1)
        backup_database("test_civic", test_db, compress=False, dry_run=False)
        time.sleep(1.1)
        backup_database("test_civic", test_db, compress=False, dry_run=False)

        backups = list_backups()

        assert len(backups) == 3
        # Should be sorted newest first
        assert backups[0]["timestamp"] > backups[1]["timestamp"]
        assert backups[1]["timestamp"] > backups[2]["timestamp"]


class TestRetentionPolicy:
    """Tests for backup retention policy."""

    def test_clean_old_backups_dry_run(
        self, test_backup_dir, tmp_path, monkeypatch
    ):
        """Dry run should not delete any files."""
        import backup as backup_module

        # Create test database
        test_db = tmp_path / "test.db"
        conn = sqlite3.connect(test_db)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.close()

        test_databases = {"test_civic": test_db}
        monkeypatch.setattr(backup_module, "BACKUP_DIR", test_backup_dir)
        monkeypatch.setattr(backup_module, "DATABASES", test_databases)

        # Create backups
        for _ in range(3):
            backup_database("test_civic", test_db, compress=False, dry_run=False)

        initial_count = len(list(test_backup_dir.glob("*.db")))

        deleted, messages = clean_old_backups(dry_run=True)

        final_count = len(list(test_backup_dir.glob("*.db")))
        assert final_count == initial_count  # No files deleted


# ============================================================================
# End-to-End Tests: Full Rollback Scenario
# ============================================================================


class TestFullRollbackScenario:
    """
    End-to-end tests simulating full rollback scenarios.

    These tests verify the complete backup/restore workflow as it would
    be used during an actual deployment rollback.
    """

    def test_full_backup_restore_cycle(self, tmp_path):
        """
        Simulate complete backup -> modify -> restore cycle.

        This is the core scenario for deployment rollback:
        1. Create initial database state
        2. Backup
        3. Make changes (simulate deployment)
        4. Restore from backup
        5. Verify original state is recovered
        """
        import backup as backup_module

        # Setup isolated environment
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        db_path = tmp_path / "civic_state.db"
        test_databases = {"civic_state": db_path}

        # Monkeypatch within test
        original_backup_dir = backup_module.BACKUP_DIR
        original_databases = backup_module.DATABASES
        backup_module.BACKUP_DIR = backup_dir
        backup_module.DATABASES = test_databases

        try:
            # Step 1: Create initial state
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE meetings (id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute("INSERT INTO meetings (title) VALUES ('City Council Meeting')")
            conn.execute("INSERT INTO meetings (title) VALUES ('Planning Commission')")
            conn.commit()
            conn.close()

            # Verify initial state
            conn = sqlite3.connect(db_path)
            initial_count = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
            conn.close()
            assert initial_count == 2

            # Step 2: Create backup
            success, _, backup_path = backup_database(
                "civic_state", db_path, compress=False, dry_run=False
            )
            assert success is True

            # Step 3: Simulate deployment changes (potentially bad changes)
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM meetings")  # Oops, bad migration!
            conn.execute("INSERT INTO meetings (title) VALUES ('Corrupted Data')")
            conn.commit()
            conn.close()

            # Verify bad state
            conn = sqlite3.connect(db_path)
            bad_count = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
            bad_titles = conn.execute("SELECT title FROM meetings").fetchall()
            conn.close()
            assert bad_count == 1
            assert bad_titles[0][0] == "Corrupted Data"

            # Step 4: Restore from backup
            success, message = restore_database(
                backup_path, target_db="civic_state", dry_run=False, force=True
            )
            assert success is True

            # Step 5: Verify original state recovered
            conn = sqlite3.connect(db_path)
            restored_count = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
            restored_titles = [
                r[0] for r in conn.execute("SELECT title FROM meetings ORDER BY id").fetchall()
            ]
            conn.close()

            assert restored_count == 2
            assert "City Council Meeting" in restored_titles
            assert "Planning Commission" in restored_titles
            assert "Corrupted Data" not in restored_titles

        finally:
            # Restore original module state
            backup_module.BACKUP_DIR = original_backup_dir
            backup_module.DATABASES = original_databases

    def test_rollback_preserves_schema(self, tmp_path):
        """Verify that schema is preserved through backup/restore."""
        import backup as backup_module

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        db_path = tmp_path / "civic_state.db"
        test_databases = {"civic_state": db_path}

        original_backup_dir = backup_module.BACKUP_DIR
        original_databases = backup_module.DATABASES
        backup_module.BACKUP_DIR = backup_dir
        backup_module.DATABASES = test_databases

        try:
            # Create complex schema
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE
                );
                CREATE INDEX idx_users_email ON users(email);

                CREATE TABLE voices (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE VIEW active_users AS
                    SELECT DISTINCT u.* FROM users u
                    JOIN voices v ON u.id = v.user_id;
            """)
            conn.execute("INSERT INTO users (name, email) VALUES ('Test', 'test@example.com')")
            conn.commit()
            conn.close()

            # Backup
            success, _, backup_path = backup_database(
                "civic_state", db_path, compress=False, dry_run=False
            )
            assert success is True

            # Delete and recreate with different schema
            db_path.unlink()
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE different_schema (x INTEGER)")
            conn.close()

            # Restore
            success, _ = restore_database(
                backup_path, target_db="civic_state", dry_run=False, force=True
            )
            assert success is True

            # Verify schema restored
            conn = sqlite3.connect(db_path)

            # Check tables
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "users" in table_names
            assert "voices" in table_names
            assert "different_schema" not in table_names

            # Check index
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = [i[0] for i in indexes]
            assert "idx_users_email" in index_names

            # Check view
            views = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view'"
            ).fetchall()
            view_names = [v[0] for v in views]
            assert "active_users" in view_names

            conn.close()

        finally:
            backup_module.BACKUP_DIR = original_backup_dir
            backup_module.DATABASES = original_databases
