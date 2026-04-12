"""
Tests for San Rafael seed data script.

This module verifies that the seed script correctly:
- Seeds city_states with proper jurisdiction config
- Seeds meetings from enhanced manifest
- Seeds issues from SeeClickFix JSON
- Supports dry-run mode
- Generates verification reports
- Handles idempotent re-seeding
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add scripts directory to path for seed module import
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from seed_san_rafael import (
    seed_city_state,
    seed_meetings,
    seed_issues,
    generate_report,
    JURISDICTION_ID,
)

# Mark as slow: seeds database with 100+ records from manifest/JSON
pytestmark = pytest.mark.slow


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def test_db(tmp_path):
    """Create a test SQLite database with required schema."""
    db_path = tmp_path / "civic_state.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create city_states table
    conn.execute("""
        CREATE TABLE city_states (
            jurisdiction_id TEXT PRIMARY KEY,
            jurisdiction_name TEXT NOT NULL,
            as_of TIMESTAMP NOT NULL,
            active_residents INTEGER DEFAULT 0,
            pending_comments INTEGER DEFAULT 0,
            coordination_threads INTEGER DEFAULT 0,
            completeness_score REAL DEFAULT 0.0,
            data_sources TEXT,
            extraction_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create meetings table
    conn.execute("""
        CREATE TABLE meetings (
            id TEXT NOT NULL,
            jurisdiction_id TEXT NOT NULL,
            title TEXT NOT NULL,
            meeting_datetime TIMESTAMP NOT NULL,
            meeting_type TEXT,
            status TEXT,
            location TEXT,
            virtual_url TEXT,
            agenda_url TEXT,
            minutes_url TEXT,
            video_url TEXT,
            comment_deadline TIMESTAMP,
            source_platform TEXT NOT NULL,
            source_url TEXT,
            last_verified TIMESTAMP,
            data_quality_score REAL,
            valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            valid_to TIMESTAMP,
            full_data TEXT,
            PRIMARY KEY (id, valid_from),
            FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id)
        )
    """)

    # Create issues table
    conn.execute("""
        CREATE TABLE issues (
            id TEXT PRIMARY KEY,
            jurisdiction_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            issue_type TEXT,
            address TEXT,
            latitude REAL,
            longitude REAL,
            status TEXT DEFAULT 'open',
            closed_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            matched_meetings TEXT,
            matched_agenda_items TEXT,
            match_score REAL,
            match_reason TEXT,
            follower_count INTEGER DEFAULT 0,
            coordination_thread_id TEXT,
            valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            valid_to TIMESTAMP,
            FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id)
        )
    """)

    conn.commit()
    return conn


@pytest.fixture
def sample_meetings_file(tmp_path):
    """Create a sample meetings JSON file for testing."""
    meetings_data = {
        "jurisdiction_id": "city-san-rafael",
        "jurisdiction_name": "San Rafael",
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "extraction_timestamp": datetime.now().isoformat(),
        "total_meetings": 3,
        "meetings": {
            "city_council": [
                {
                    "title": "City Council - January 15, 2024",
                    "meeting_slug": "city-council-january-15-2024",
                    "meeting_url": "https://example.com/meetings/2024-01-15",
                    "date_parsed": "2024-01-15",
                    "meeting_type": "city_council",
                    "agenda_packet_pdf_url": "https://example.com/agenda.pdf",
                },
                {
                    "title": "City Council - February 19, 2024",
                    "meeting_slug": "city-council-february-19-2024",
                    "meeting_url": "https://example.com/meetings/2024-02-19",
                    "date_parsed": "2024-02-19",
                    "meeting_type": "city_council",
                },
            ],
            "planning_commission": [
                {
                    "title": "Planning Commission - January 22, 2024",
                    "meeting_slug": "planning-commission-january-22-2024",
                    "meeting_url": "https://example.com/meetings/pc-2024-01-22",
                    "date_parsed": "2024-01-22",
                    "meeting_type": "planning_commission",
                },
            ],
        },
    }
    meetings_file = tmp_path / "meetings.json"
    with open(meetings_file, "w") as f:
        json.dump(meetings_data, f)
    return meetings_file


@pytest.fixture
def sample_issues_file(tmp_path):
    """Create a sample SeeClickFix issues JSON file for testing."""
    issues_data = [
        {
            "id": "scf-12345",
            "external_id": 12345,
            "source": "seeclickfix",
            "issue_type": "operational",
            "title": "Pothole on Main Street",
            "description": "Large pothole causing traffic issues",
            "status": "open",
            "location": {
                "address": "123 Main St, San Rafael, CA 94901",
                "lat": 37.9735,
                "lng": -122.5311,
            },
            "created_at": "2024-01-10T10:00:00-08:00",
            "updated_at": "2024-01-10T10:00:00-08:00",
        },
        {
            "id": "scf-12346",
            "external_id": 12346,
            "source": "seeclickfix",
            "issue_type": "operational",
            "title": "Broken streetlight",
            "description": "Streetlight not working on Oak Ave",
            "status": "acknowledged",
            "location": {
                "address": "456 Oak Ave, San Rafael, CA 94901",
                "lat": 37.9740,
                "lng": -122.5320,
            },
            "created_at": "2024-01-11T14:30:00-08:00",
            "updated_at": "2024-01-12T09:00:00-08:00",
        },
        {
            "id": "scf-12347",
            "external_id": 12347,
            "source": "seeclickfix",
            "issue_type": "quality_of_life",
            "title": "Graffiti removal needed",
            "description": "Graffiti on wall near downtown",
            "status": "closed",
            "location": {
                "address": "789 4th St, San Rafael, CA 94901",
                "lat": 37.9745,
                "lng": -122.5300,
            },
            "created_at": "2024-01-05T08:00:00-08:00",
            "updated_at": "2024-01-08T16:00:00-08:00",
        },
    ]
    issues_file = tmp_path / "issues.json"
    with open(issues_file, "w") as f:
        json.dump(issues_data, f)
    return issues_file


# ============================================================================
# City State Tests
# ============================================================================


class TestSeedCityState:
    """Tests for city_states seeding."""

    def test_seed_city_state_creates_entry(self, test_db):
        """Seeding creates a city_states entry."""
        count, messages = seed_city_state(test_db, dry_run=False)

        assert count == 1
        assert "Creating city state" in messages[0]

        cursor = test_db.execute(
            "SELECT * FROM city_states WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["jurisdiction_name"] == "San Rafael, CA"
        data_sources = json.loads(row["data_sources"])
        assert "proudcity" in data_sources
        assert "seeclickfix" in data_sources
        assert len(data_sources) == 4

    def test_seed_city_state_updates_existing(self, test_db):
        """Seeding updates an existing entry."""
        # Create initial entry
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "Old Name", datetime.now().isoformat())
        )
        test_db.commit()

        count, messages = seed_city_state(test_db, dry_run=False)

        assert count == 1
        assert "already exists, updating" in messages[0]

        cursor = test_db.execute(
            "SELECT jurisdiction_name FROM city_states WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        row = cursor.fetchone()
        assert row["jurisdiction_name"] == "San Rafael, CA"

    def test_seed_city_state_dry_run(self, test_db):
        """Dry run doesn't create entries."""
        count, messages = seed_city_state(test_db, dry_run=True)

        assert count == 1

        cursor = test_db.execute(
            "SELECT * FROM city_states WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        assert cursor.fetchone() is None


# ============================================================================
# Meetings Tests
# ============================================================================


class TestSeedMeetings:
    """Tests for meetings seeding."""

    def test_seed_meetings_inserts_records(self, test_db, sample_meetings_file, monkeypatch):
        """Seeding inserts meeting records from JSON."""
        # Need to seed city_state first (foreign key)
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        # Monkeypatch the MEETINGS_FILE path
        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "MEETINGS_FILE", sample_meetings_file)

        count, messages = seed_meetings(test_db, dry_run=False)

        assert count == 3
        assert "Inserted 3 meetings" in messages[-1]

        cursor = test_db.execute(
            "SELECT COUNT(*) as cnt FROM meetings WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        assert cursor.fetchone()["cnt"] == 3

    def test_seed_meetings_stores_meeting_type(self, test_db, sample_meetings_file, monkeypatch):
        """Meetings are stored with correct meeting_type."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "MEETINGS_FILE", sample_meetings_file)

        seed_meetings(test_db, dry_run=False)

        cursor = test_db.execute(
            "SELECT meeting_type, COUNT(*) as cnt FROM meetings "
            "WHERE jurisdiction_id = ? GROUP BY meeting_type",
            (JURISDICTION_ID,)
        )
        types = {row["meeting_type"]: row["cnt"] for row in cursor.fetchall()}
        assert types.get("city_council") == 2
        assert types.get("planning_commission") == 1

    def test_seed_meetings_skips_existing(self, test_db, sample_meetings_file, monkeypatch):
        """Seeding skips already existing meetings."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "MEETINGS_FILE", sample_meetings_file)

        # First seed
        seed_meetings(test_db, dry_run=False)

        # Second seed should skip
        count, messages = seed_meetings(test_db, dry_run=False)
        assert count == 0
        assert "skipped 3 existing" in messages[-1]

    def test_seed_meetings_force_overwrites(self, test_db, sample_meetings_file, monkeypatch):
        """Force mode overwrites existing meetings."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "MEETINGS_FILE", sample_meetings_file)

        # First seed
        seed_meetings(test_db, dry_run=False)

        # Force re-seed
        count, messages = seed_meetings(test_db, dry_run=False, force=True)
        assert count == 3
        assert "Inserted 3 meetings" in messages[-1]


# ============================================================================
# Issues Tests
# ============================================================================


class TestSeedIssues:
    """Tests for issues seeding."""

    def test_seed_issues_inserts_records(self, test_db, sample_issues_file, monkeypatch):
        """Seeding inserts issue records from JSON."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "ISSUES_FILE", sample_issues_file)

        count, messages = seed_issues(test_db, dry_run=False)

        assert count == 3
        assert "Inserted 3" in messages[-1]

        cursor = test_db.execute(
            "SELECT COUNT(*) as cnt FROM issues WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        assert cursor.fetchone()["cnt"] == 3

    def test_seed_issues_preserves_status(self, test_db, sample_issues_file, monkeypatch):
        """Issues are stored with correct status from source."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "ISSUES_FILE", sample_issues_file)

        seed_issues(test_db, dry_run=False)

        cursor = test_db.execute(
            "SELECT status, COUNT(*) as cnt FROM issues "
            "WHERE jurisdiction_id = ? GROUP BY status",
            (JURISDICTION_ID,)
        )
        statuses = {row["status"]: row["cnt"] for row in cursor.fetchall()}
        assert statuses.get("open") == 1
        assert statuses.get("acknowledged") == 1
        assert statuses.get("closed") == 1

    def test_seed_issues_stores_location(self, test_db, sample_issues_file, monkeypatch):
        """Issues store location data correctly."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "ISSUES_FILE", sample_issues_file)

        seed_issues(test_db, dry_run=False)

        cursor = test_db.execute(
            "SELECT address, latitude, longitude FROM issues WHERE id = 'scf-12345'"
        )
        row = cursor.fetchone()
        assert "Main St" in row["address"]
        assert abs(row["latitude"] - 37.9735) < 0.001
        assert abs(row["longitude"] - (-122.5311)) < 0.001

    def test_seed_issues_dry_run(self, test_db, sample_issues_file, monkeypatch):
        """Dry run doesn't insert issues."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "ISSUES_FILE", sample_issues_file)

        count, messages = seed_issues(test_db, dry_run=True)

        cursor = test_db.execute(
            "SELECT COUNT(*) as cnt FROM issues WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        assert cursor.fetchone()["cnt"] == 0


# ============================================================================
# Report Tests
# ============================================================================


class TestGenerateReport:
    """Tests for verification report generation."""

    def test_generate_report_structure(self, test_db, sample_meetings_file, sample_issues_file, monkeypatch):
        """Report has expected structure."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "MEETINGS_FILE", sample_meetings_file)
        monkeypatch.setattr(seed_san_rafael, "ISSUES_FILE", sample_issues_file)

        seed_city_state(test_db)
        seed_meetings(test_db)
        seed_issues(test_db)
        test_db.commit()

        report = generate_report(test_db)

        assert report["jurisdiction_id"] == JURISDICTION_ID
        assert "T" in report["timestamp"]  # ISO format datetime
        tables = report["tables"]
        assert tables["city_states"]["count"] == 1
        assert tables["city_states"]["jurisdiction_name"] == "San Rafael, CA"
        assert "meetings" in tables
        assert "issues" in tables

    def test_generate_report_counts(self, test_db, sample_meetings_file, sample_issues_file, monkeypatch):
        """Report includes correct counts."""
        test_db.execute(
            "INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of) VALUES (?, ?, ?)",
            (JURISDICTION_ID, "San Rafael", datetime.now().isoformat())
        )
        test_db.commit()

        import seed_san_rafael
        monkeypatch.setattr(seed_san_rafael, "MEETINGS_FILE", sample_meetings_file)
        monkeypatch.setattr(seed_san_rafael, "ISSUES_FILE", sample_issues_file)

        seed_city_state(test_db)
        seed_meetings(test_db)
        seed_issues(test_db)
        test_db.commit()

        report = generate_report(test_db)

        assert report["tables"]["meetings"]["count"] == 3
        assert report["tables"]["issues"]["count"] == 3
        assert report["tables"]["issues"]["by_status"]["open"] == 1
