"""
Tests for complaint storage Layer 2 implementation.

Tests CRUD operations, ParticipationMechanism interface, and database integrity.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

from civic_app.issue_storage import IssueStorage as ComplaintStorage, Issue as Complaint


@pytest.fixture
def test_db():
    """Create temporary test database with schema"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)

    # Create schema
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # user_profiles table (needed for foreign key)
        cursor.execute("""
            CREATE TABLE user_profiles (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                first_seen DATETIME NOT NULL,
                last_active DATETIME NOT NULL
            )
        """)

        # civic_actions table (needed for tracking)
        cursor.execute("""
            CREATE TABLE civic_actions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                opportunity_id TEXT,
                jurisdiction_id TEXT,
                timestamp DATETIME NOT NULL,
                completion_status TEXT NOT NULL,
                metadata TEXT
            )
        """)

        # Run migration
        with open('migrations/002_add_complaints.sql') as migration_file:
            migration_sql = migration_file.read()
            cursor.executescript(migration_sql)

        # Add test user
        cursor.execute("""
            INSERT INTO user_profiles (user_id, first_seen, last_active)
            VALUES ('test-user-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)

        conn.commit()

    yield db_path

    # Cleanup
    db_path.unlink()


class TestComplaintStorage:
    """Test CRUD operations"""

    def test_create_complaint(self, test_db):
        """Test creating a new complaint"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test complaint about housing",
            jurisdiction_id="city-berkeley",
            issue_type="housing",
            location={"address": "123 Main St", "latitude": 37.8715, "longitude": -122.2727}
        )

        assert complaint_id is not None
        assert len(complaint_id) == 36  # UUID length

        # Verify it was inserted
        complaint = storage.get_complaint(complaint_id)
        assert complaint["description"] == "Test complaint about housing"
        assert complaint["status"] == "open"
        assert complaint["issue_type"] == "housing"
        assert complaint["address"] == "123 Main St"

    def test_create_complaint_enforces_max_length(self, test_db):
        """Test that description is truncated to 2000 chars"""
        storage = ComplaintStorage(db_path=test_db)

        long_description = "x" * 3000
        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description=long_description,
            jurisdiction_id="city-berkeley"
        )

        complaint = storage.get_complaint(complaint_id)
        assert len(complaint["description"]) == 2000

    def test_get_complaint_not_found(self, test_db):
        """Test retrieving non-existent complaint"""
        storage = ComplaintStorage(db_path=test_db)

        complaint = storage.get_complaint("non-existent-id")
        assert complaint is None

    def test_link_to_event(self, test_db):
        """Test linking complaint to event"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Pothole on Main St",
            jurisdiction_id="city-berkeley",
            issue_type="infrastructure"
        )

        storage.link_to_event(
            complaint_id=complaint_id,
            event_id="event-123",
            match_score=85.0,
            match_reason="Keyword match: pothole, infrastructure"
        )

        complaint = storage.get_complaint(complaint_id)
        assert complaint["status"] == "matched"
        assert len(complaint["matched_events"]) == 1
        assert complaint["matched_events"][0]["event_id"] == "event-123"
        assert complaint["matched_events"][0]["match_score"] == 85.0

    def test_link_multiple_events(self, test_db):
        """Test linking complaint to multiple events"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Housing issue",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        storage.link_to_event(complaint_id, "event-1", 80.0, "Match 1")
        storage.link_to_event(complaint_id, "event-2", 90.0, "Match 2")
        storage.link_to_event(complaint_id, "event-3", 70.0, "Match 3")

        complaint = storage.get_complaint(complaint_id)
        assert len(complaint["matched_events"]) == 3

        # Verify sorted by score descending
        scores = [e["match_score"] for e in complaint["matched_events"]]
        assert scores == [90.0, 80.0, 70.0]

    def test_find_similar_complaints(self, test_db):
        """Test finding similar complaints"""
        storage = ComplaintStorage(db_path=test_db)

        # Create several complaints
        complaint_ids = []
        for i in range(5):
            cid = storage.create_complaint(
                user_id="test-user-1",
                description=f"Housing complaint {i}",
                jurisdiction_id="city-berkeley",
                issue_type="housing"
            )
            complaint_ids.append(cid)

        # Create one with different issue type
        storage.create_complaint(
            user_id="test-user-1",
            description="Transportation complaint",
            jurisdiction_id="city-berkeley",
            issue_type="transportation"
        )

        # Find similar housing complaints
        similar = storage.find_similar_complaints(
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        assert len(similar) == 5
        assert all(c["issue_type"] == "housing" for c in similar)

    def test_update_status(self, test_db):
        """Test updating complaint status"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test",
            jurisdiction_id="city-berkeley"
        )

        storage.update_status(complaint_id, "community_formed")

        complaint = storage.get_complaint(complaint_id)
        assert complaint["status"] == "community_formed"

    def test_civic_action_tracking(self, test_db):
        """Test that complaint submission creates civic action"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        # Verify civic action was created
        with sqlite3.connect(test_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM civic_actions
                WHERE event_type = 'complaint_submit'
                  AND opportunity_id = ?
            """, (complaint_id,))

            action = cursor.fetchone()
            assert action is not None
            assert action["user_id"] == "test-user-1"
            assert action["completion_status"] == "completed"


class TestComplaintClass:
    """Test Complaint class ParticipationMechanism implementation"""

    def test_implements_interface(self, test_db):
        """Test that Complaint implements all interface methods"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test complaint",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint_data = storage.get_complaint(complaint_id)
        complaint = Complaint(complaint_data)

        # Test all interface methods
        assert complaint.get_id() == complaint_id
        assert complaint.get_type() == "Complaint"
        assert isinstance(complaint.get_actions(), list)
        assert isinstance(complaint.get_context(), dict)
        assert complaint.get_lifecycle_status() == "open"
        assert complaint.is_government_generated() == False
        assert complaint.get_participation_threshold() == "low"

    def test_get_actions_no_matches(self, test_db):
        """Test actions when complaint has no matches"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test",
            jurisdiction_id="city-berkeley"
        )

        complaint_data = storage.get_complaint(complaint_id)
        complaint = Complaint(complaint_data)

        actions = complaint.get_actions()
        assert len(actions) == 1
        assert actions[0]["action_type"] == "button"
        assert "Track" in actions[0]["action_label"]

    def test_get_actions_with_matches(self, test_db):
        """Test actions when complaint has matched events"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test",
            jurisdiction_id="city-berkeley"
        )

        storage.link_to_event(complaint_id, "event-1", 85.0, "Match")
        storage.link_to_event(complaint_id, "event-2", 75.0, "Match")

        complaint_data = storage.get_complaint(complaint_id)
        complaint = Complaint(complaint_data)

        actions = complaint.get_actions()
        assert len(actions) == 2
        assert all(a["action_type"] == "link" for a in actions)
        assert "85%" in actions[0]["action_label"]

    def test_get_context(self, test_db):
        """Test context generation"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint_data = storage.get_complaint(complaint_id)
        complaint = Complaint(complaint_data)

        context = complaint.get_context()
        assert "complaint_context" in context
        assert "community_context" in context
        assert "matched_events_count" in context

        assert context["complaint_context"]["issue_type"] == "housing"
        assert context["complaint_context"]["status"] == "open"
        assert context["complaint_context"]["days_open"] >= 0


class TestDatabaseIntegrity:
    """Test database constraints and foreign keys"""

    def test_check_constraints_issue_type(self, test_db):
        """Test that invalid issue_type is rejected"""
        with sqlite3.connect(test_db) as conn:
            cursor = conn.cursor()

            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO complaints (id, user_id, description, jurisdiction_id, issue_type, status)
                    VALUES ('test-id', 'test-user-1', 'test', 'city-berkeley', 'invalid_type', 'open')
                """)

    def test_check_constraints_status(self, test_db):
        """Test that invalid status is rejected"""
        with sqlite3.connect(test_db) as conn:
            cursor = conn.cursor()

            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO complaints (id, user_id, description, jurisdiction_id, status)
                    VALUES ('test-id', 'test-user-1', 'test', 'city-berkeley', 'invalid_status')
                """)

    def test_cascade_delete(self, test_db):
        """Test that deleting complaint cascades to junction tables"""
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="test-user-1",
            description="Test",
            jurisdiction_id="city-berkeley"
        )

        storage.link_to_event(complaint_id, "event-1", 80.0, "Match")

        # Delete complaint (enable foreign keys for cascade)
        with sqlite3.connect(test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
            conn.commit()

        # Verify junction table entry was deleted
        with sqlite3.connect(test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM complaints_to_events WHERE complaint_id = ?
            """, (complaint_id,))
            count = cursor.fetchone()[0]
            assert count == 0
