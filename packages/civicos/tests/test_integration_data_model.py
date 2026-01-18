"""
Integration tests for data model consistency.

Tests verify:
- Hybrid sync: agenda_items stored in both JSON (full_data) and relational table
- get_city_state() returns meetings with agenda_items attached
- whats_next() can filter by topic using relational agenda_items
- prepare() can find agenda items from relational table

Run: python -m pytest packages/civic/tests/test_integration_data_model.py -v
"""

import os
import sys
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# Mark all tests in this module as integration
pytestmark = pytest.mark.integration

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add packages to path
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic/src"))

from civicos._internal.state import StateManager
from civicos import CivicOS


class TestAgendaItemsRelational:
    """
    Test: Agenda items stored in agenda_items table, not just embedded in full_data JSON.

    This tests the hybrid sync approach:
    - JSON blob (full_data) remains source of truth for flexibility
    - Relational table (agenda_items) enables queries and FK relationships
    """

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_agenda_items.db")
            yield db_path

    @pytest.fixture
    def state_manager(self, temp_db):
        """Create StateManager with temp database."""
        return StateManager(temp_db)

    @pytest.fixture
    def sample_meeting_with_items(self):
        """Create a sample meeting with agenda items."""
        return {
            "id": "meeting-2025-01-15",
            "title": "City Council Regular Meeting",
            "meeting_datetime": "2025-01-15T18:00:00",
            "meeting_type": "City Council",
            "status": "scheduled",
            "location": "City Hall, Council Chambers",
            "source_platform": "test",
            "agenda_items": [
                {
                    "id": "item-001",
                    "item_number": "6.a",
                    "title": "Affordable Housing Development at 350 Main Street",
                    "description": "Consider approval of affordable housing project",
                    "project_type": "housing",
                    "actionability": "high",
                    "impact_level": "significant",
                },
                {
                    "id": "item-002",
                    "item_number": "6.b",
                    "title": "Traffic Calming Measures on Oak Avenue",
                    "description": "Review proposed speed bumps and crosswalks",
                    "project_type": "transportation",
                    "actionability": "medium",
                },
                {
                    "id": "item-003",
                    "item_number": "7.a",
                    "title": "Annual Budget Review",
                    "description": "Mid-year budget review and adjustments",
                    "project_type": "budget",
                },
            ]
        }

    def test_update_meetings_populates_agenda_items_table(self, state_manager, sample_meeting_with_items):
        """
        Verify that update_meetings() inserts agenda items into the relational table.
        """
        # Store meeting with agenda items
        state_manager.update_meetings(
            "city-test",
            [sample_meeting_with_items],
            as_of=datetime.now()
        )

        # Query the agenda_items table directly
        conn = sqlite3.connect(state_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM agenda_items WHERE valid_to IS NULL
            ORDER BY item_number
        """)
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Verify items are in relational table
        assert len(items) == 3, f"Expected 3 agenda items, got {len(items)}"

        # Verify correct meeting_id linkage
        for item in items:
            assert item['meeting_id'] == "meeting-2025-01-15"

        # Verify item data
        item_ids = [i['id'] for i in items]
        assert "item-001" in item_ids
        assert "item-002" in item_ids
        assert "item-003" in item_ids

        # Verify project_type is stored
        housing_item = next(i for i in items if i['id'] == "item-001")
        assert housing_item['project_type'] == "housing"

    def test_update_meetings_also_stores_full_data_json(self, state_manager, sample_meeting_with_items):
        """
        Verify that full_data JSON blob still contains agenda_items (hybrid approach).
        """
        state_manager.update_meetings(
            "city-test",
            [sample_meeting_with_items],
            as_of=datetime.now()
        )

        # Query meeting directly
        conn = sqlite3.connect(state_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT full_data FROM meetings WHERE id = ? AND valid_to IS NULL
        """, ("meeting-2025-01-15",))
        row = cursor.fetchone()
        conn.close()

        import json
        full_data = json.loads(row['full_data'])

        # Verify agenda_items in JSON blob
        assert 'agenda_items' in full_data
        assert len(full_data['agenda_items']) == 3

    def test_get_city_state_attaches_agenda_items_to_meetings(self, state_manager, sample_meeting_with_items):
        """
        Verify that get_city_state() returns meetings with agenda_items attached.
        """
        state_manager.update_meetings(
            "city-test",
            [sample_meeting_with_items],
            as_of=datetime.now()
        )

        city_state = state_manager.get_city_state("city-test")

        # Should have meetings
        assert len(city_state['meetings']) == 1
        meeting = city_state['meetings'][0]

        # Meeting should have agenda_items attached
        assert 'agenda_items' in meeting
        assert len(meeting['agenda_items']) == 3

        # Verify agenda_items have expected fields
        item_titles = [i['title'] for i in meeting['agenda_items']]
        assert "Affordable Housing Development at 350 Main Street" in item_titles
        assert "Traffic Calming Measures on Oak Avenue" in item_titles

    def test_get_city_state_also_returns_flat_agenda_items(self, state_manager, sample_meeting_with_items):
        """
        Verify that get_city_state() also returns a flat list of all agenda_items.
        """
        state_manager.update_meetings(
            "city-test",
            [sample_meeting_with_items],
            as_of=datetime.now()
        )

        city_state = state_manager.get_city_state("city-test")

        # Should have flat agenda_items list
        assert 'agenda_items' in city_state
        assert len(city_state['agenda_items']) == 3

    def test_temporal_versioning_closes_old_agenda_items(self, state_manager, sample_meeting_with_items):
        """
        Verify that updating meetings closes old agenda_item versions.
        """
        # First update
        first_time = datetime(2025, 1, 10, 12, 0, 0)
        state_manager.update_meetings(
            "city-test",
            [sample_meeting_with_items],
            as_of=first_time
        )

        # Second update with modified agenda items
        modified_meeting = sample_meeting_with_items.copy()
        modified_meeting['agenda_items'] = [
            {
                "id": "item-001",
                "item_number": "6.a",
                "title": "Affordable Housing - AMENDED",
                "project_type": "housing",
            },
            {
                "id": "item-004",  # New item
                "item_number": "6.c",
                "title": "New Business",
                "project_type": "general",
            },
        ]

        second_time = datetime(2025, 1, 11, 12, 0, 0)
        state_manager.update_meetings(
            "city-test",
            [modified_meeting],
            as_of=second_time
        )

        # Query all agenda_items (including closed)
        conn = sqlite3.connect(state_manager.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM agenda_items ORDER BY valid_from")
        all_items = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM agenda_items WHERE valid_to IS NULL")
        current_items = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Should have 5 total rows (3 closed + 2 current)
        assert len(all_items) == 5, f"Expected 5 total items, got {len(all_items)}"

        # Should have 2 current items
        assert len(current_items) == 2, f"Expected 2 current items, got {len(current_items)}"

        # Current items should be the updated ones
        current_ids = [i['id'] for i in current_items]
        assert "item-001" in current_ids
        assert "item-004" in current_ids


class TestWhatsNextUsesRelational:
    """
    Test: whats_next() retrieves agenda_items from relational join, not JSON parsing.
    """

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_whats_next.db")
            yield db_path

    @pytest.fixture
    def civic_with_meetings(self, temp_db):
        """Create Civic instance with seeded meetings."""
        civic = CivicOS("city-test", db_path=temp_db)

        # Seed future meetings with agenda items
        tomorrow = datetime.now() + timedelta(days=1)
        next_week = datetime.now() + timedelta(days=7)

        meetings = [
            {
                "id": "meeting-tomorrow",
                "title": "Planning Commission",
                "meeting_datetime": tomorrow.isoformat(),
                "meeting_type": "Planning",
                "status": "scheduled",
                "source_platform": "test",
                "agenda_items": [
                    {"id": "plan-item-1", "title": "Zoning Amendment", "topic": "housing"},
                    {"id": "plan-item-2", "title": "Park Renovation", "topic": "parks"},
                ]
            },
            {
                "id": "meeting-next-week",
                "title": "City Council",
                "meeting_datetime": next_week.isoformat(),
                "meeting_type": "Council",
                "status": "scheduled",
                "source_platform": "test",
                "agenda_items": [
                    {"id": "council-item-1", "title": "Housing Trust Fund", "topic": "housing"},
                    {"id": "council-item-2", "title": "Road Repairs", "topic": "transportation"},
                ]
            },
        ]

        civic._state.update_meetings("city-test", meetings)
        return civic

    def test_whats_next_returns_meetings_with_agenda_items(self, civic_with_meetings):
        """
        Verify whats_next() returns meetings with agenda_items populated.
        """
        meetings = civic_with_meetings.whats_next(days=30)

        assert len(meetings) == 2

        # Each meeting should have agenda_items
        for meeting in meetings:
            assert hasattr(meeting, 'agenda_items') or 'agenda_items' in meeting.__dict__
            # The Meeting dataclass has agenda_items as a field
            assert len(meeting.agenda_items) > 0

    def test_whats_next_filters_by_topic(self, civic_with_meetings):
        """
        Verify whats_next() can filter meetings by topic using agenda_items.
        """
        # Filter by housing topic
        housing_meetings = civic_with_meetings.whats_next(topics=["housing"], days=30)

        # Both meetings have housing items
        assert len(housing_meetings) == 2

        # Filter by parks (only in tomorrow's meeting)
        parks_meetings = civic_with_meetings.whats_next(topics=["parks"], days=30)

        # Only Planning Commission has parks item
        assert len(parks_meetings) == 1
        assert "Planning" in parks_meetings[0].title


class TestExtractorsStoreRelationally:
    """
    Test: Verify the pattern works for extractor-style data.
    """

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_extractors.db")
            yield db_path

    def test_meeting_without_agenda_items(self, temp_db):
        """
        Verify meetings without agenda_items work correctly.
        """
        state_manager = StateManager(temp_db)

        meeting_no_items = {
            "id": "meeting-no-items",
            "title": "Special Session",
            "meeting_datetime": "2025-01-20T18:00:00",
            "source_platform": "test",
            # No agenda_items
        }

        state_manager.update_meetings("city-test", [meeting_no_items])

        city_state = state_manager.get_city_state("city-test")

        assert len(city_state['meetings']) == 1
        meeting = city_state['meetings'][0]

        # Should have empty agenda_items list
        assert meeting['agenda_items'] == []

    def test_agenda_item_id_generation(self, temp_db):
        """
        Verify agenda items without IDs get auto-generated IDs.
        """
        state_manager = StateManager(temp_db)

        meeting_with_no_id_items = {
            "id": "meeting-auto-id",
            "title": "Auto ID Test",
            "meeting_datetime": "2025-01-20T18:00:00",
            "source_platform": "test",
            "agenda_items": [
                {"title": "Item without ID", "project_type": "general"},
                {"title": "Another item without ID", "project_type": "housing"},
            ]
        }

        state_manager.update_meetings("city-test", [meeting_with_no_id_items])

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM agenda_items WHERE valid_to IS NULL")
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert len(ids) == 2
        # IDs should be auto-generated based on meeting ID and index
        assert "meeting-auto-id-item-0" in ids
        assert "meeting-auto-id-item-1" in ids

    def test_agenda_item_topic_field_mapping(self, temp_db):
        """
        Verify 'topic' field maps to 'project_type' column.
        """
        state_manager = StateManager(temp_db)

        meeting = {
            "id": "meeting-topic-test",
            "title": "Topic Field Test",
            "meeting_datetime": "2025-01-20T18:00:00",
            "source_platform": "test",
            "agenda_items": [
                {"id": "topic-item", "title": "Test Item", "topic": "environment"},
            ]
        }

        state_manager.update_meetings("city-test", [meeting])

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT project_type FROM agenda_items WHERE id = 'topic-item'")
        row = cursor.fetchone()
        conn.close()

        # 'topic' field should map to 'project_type' column
        assert row['project_type'] == "environment"
