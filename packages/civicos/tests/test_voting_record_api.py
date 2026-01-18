"""
Tests for get_voting_record() API method.

Tests the voting record retrieval and aggregation functionality
for elected officials.
"""

import pytest
from datetime import datetime, date
from unittest.mock import Mock, patch

from civicos import CivicOS
from civicos._internal.elections import VotingRecord, ElectedOfficial


class TestGetVotingRecord:
    """Test get_voting_record() method."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage backend."""
        storage = Mock()

        # Default official data
        storage.get_official_by_name.return_value = {
            "id": "official-1",
            "name": "Jane Smith",
            "seat": "Council Member",
            "jurisdiction_id": "san-rafael",
            "term_start": "2022-01-01",
            "name_variations": ["Councilmember Smith", "J. Smith"],
        }

        # Default decisions with vote_results
        storage.get_decisions.return_value = [
            {
                "id": "decision-1",
                "title": "Housing Development Approval",
                "meeting_date": "2024-11-15",
                "outcome": "approved",
                "vote_json": {
                    "Jane Smith": "yes",
                    "Bob Jones": "yes",
                    "Alice Brown": "no",
                },
                "topics": ["housing", "development"],
            },
            {
                "id": "decision-2",
                "title": "Traffic Safety Measure",
                "meeting_date": "2024-11-01",
                "outcome": "approved",
                "vote_json": {
                    "Jane Smith": "no",
                    "Bob Jones": "yes",
                    "Alice Brown": "yes",
                },
                "topics": ["transportation", "safety"],
            },
            {
                "id": "decision-3",
                "title": "Budget Amendment",
                "meeting_date": "2024-10-15",
                "outcome": "approved",
                "vote_json": {
                    "Jane Smith": "absent",
                    "Bob Jones": "yes",
                    "Alice Brown": "yes",
                },
                "topics": ["budget"],
            },
            {
                "id": "decision-4",
                "title": "Affordable Housing Initiative",
                "meeting_date": "2024-10-01",
                "outcome": "approved",
                "vote_json": {
                    "Jane Smith": "yes",
                    "Bob Jones": "no",
                    "Alice Brown": "yes",
                },
                "topics": ["housing", "affordable"],
            },
        ]

        return storage

    @pytest.fixture
    def civic_with_mock(self, mock_storage):
        """Create Civic instance with mocked storage."""
        with patch('civicos.civicos.get_storage_backend') as mock_get_storage:
            mock_get_storage.return_value = mock_storage
            with patch('civicos.civicos.get_vector_backend') as mock_get_vector:
                mock_get_vector.return_value = Mock()
                c = CivicOS("san-rafael")
                c._storage = mock_storage
                return c

    def test_basic_voting_record(self, civic_with_mock, mock_storage):
        """Test retrieving basic voting record without filters."""
        record = civic_with_mock.get_voting_record("Jane Smith")

        assert record.official_name == "Jane Smith"
        assert record.official_id == "official-1"
        assert record.total_votes == 4
        assert record.yes_votes == 2
        assert record.no_votes == 1
        assert record.abstain_votes == 1
        assert len(record.decisions) == 4

    def test_voting_record_with_topic_filter(self, civic_with_mock, mock_storage):
        """Test voting record filtered by topic."""
        record = civic_with_mock.get_voting_record("Jane Smith", topic="housing")

        assert record.topic == "housing"
        assert record.total_votes == 2
        assert record.yes_votes == 2
        assert record.no_votes == 0
        assert record.abstain_votes == 0
        assert len(record.decisions) == 2

        # Verify decisions are housing-related
        for d in record.decisions:
            assert "housing" in [t.lower() for t in d["topics"]]

    def test_voting_record_yes_percentage(self, civic_with_mock, mock_storage):
        """Test yes_percentage property."""
        record = civic_with_mock.get_voting_record("Jane Smith")

        # 2 yes out of 4 total = 50%
        assert record.yes_percentage == 50.0

    def test_voting_record_zero_votes(self, civic_with_mock, mock_storage):
        """Test yes_percentage with zero votes returns 0."""
        mock_storage.get_decisions.return_value = []

        record = civic_with_mock.get_voting_record("Jane Smith")

        assert record.total_votes == 0
        assert record.yes_percentage == 0.0

    def test_voting_record_date_filter(self, civic_with_mock, mock_storage):
        """Test voting record with date range filter."""
        # The since/until are passed to storage.get_decisions
        civic_with_mock.get_voting_record(
            "Jane Smith",
            since="2024-11-01",
            until="2024-11-30"
        )

        # Verify get_decisions was called with date filters
        # (jurisdiction gets normalized to city-san-rafael)
        mock_storage.get_decisions.assert_called_once()
        call_args = mock_storage.get_decisions.call_args
        assert call_args.kwargs["since"] == "2024-11-01"
        assert call_args.kwargs["until"] == "2024-11-30"
        assert call_args.kwargs["limit"] == 1000

    def test_official_not_found_raises_error(self, civic_with_mock, mock_storage):
        """Test that ValueError is raised for unknown official."""
        mock_storage.get_official_by_name.return_value = None
        mock_storage.get_elected_officials.return_value = []

        with pytest.raises(ValueError, match="Official not found"):
            civic_with_mock.get_voting_record("Unknown Person")

    def test_fuzzy_name_matching(self, civic_with_mock, mock_storage):
        """Test that fuzzy name matching finds officials."""
        # First call returns None, then we fall back to fuzzy matching
        mock_storage.get_official_by_name.return_value = None
        mock_storage.get_elected_officials.return_value = [
            {
                "id": "official-1",
                "name": "Jane Smith",
                "seat": "Council Member",
                "jurisdiction_id": "san-rafael",
                "term_start": "2022-01-01",
                "term_end": None,  # Current official
                "name_variations": ["Councilmember Smith", "J. Smith"],
            }
        ]

        # Should match via fuzzy matching
        record = civic_with_mock.get_voting_record("Smith")

        assert record.official_name == "Jane Smith"

    def test_decision_structure(self, civic_with_mock, mock_storage):
        """Test structure of returned decisions."""
        record = civic_with_mock.get_voting_record("Jane Smith")

        # Check first decision structure
        d = record.decisions[0]
        assert "decision_id" in d
        assert "title" in d
        assert "date" in d
        assert "vote" in d
        assert "outcome" in d
        assert "topics" in d

    def test_empty_vote_json_skipped(self, civic_with_mock, mock_storage):
        """Test that decisions without vote_json are skipped."""
        mock_storage.get_decisions.return_value = [
            {
                "id": "decision-1",
                "title": "No Votes",
                "meeting_date": "2024-11-15",
                "outcome": "approved",
                "vote_json": None,
                "topics": ["housing"],
            },
            {
                "id": "decision-2",
                "title": "Empty Votes",
                "meeting_date": "2024-11-14",
                "outcome": "approved",
                "vote_json": {},
                "topics": ["housing"],
            },
        ]

        record = civic_with_mock.get_voting_record("Jane Smith")

        assert record.total_votes == 0
        assert len(record.decisions) == 0

    def test_name_variation_matching_in_votes(self, civic_with_mock, mock_storage):
        """Test matching official name variations in vote results."""
        mock_storage.get_decisions.return_value = [
            {
                "id": "decision-1",
                "title": "Test Decision",
                "meeting_date": "2024-11-15",
                "outcome": "approved",
                "vote_json": {
                    "Councilmember Smith": "yes",  # Uses variation
                    "Bob Jones": "no",
                },
                "topics": ["housing"],
            },
        ]

        record = civic_with_mock.get_voting_record("Jane Smith")

        assert record.yes_votes == 1
        assert len(record.decisions) == 1


class TestVotingRecordModel:
    """Test VotingRecord dataclass."""

    def test_voting_record_creation(self):
        """Test creating a VotingRecord."""
        record = VotingRecord(
            official_id="off-1",
            official_name="Test Official",
            topic="housing",
            total_votes=10,
            yes_votes=7,
            no_votes=2,
            abstain_votes=1,
            decisions=[],
        )

        assert record.official_name == "Test Official"
        assert record.total_votes == 10

    def test_yes_percentage_calculation(self):
        """Test yes_percentage property."""
        record = VotingRecord(
            official_id="off-1",
            official_name="Test",
            topic="all",
            total_votes=10,
            yes_votes=7,
            no_votes=2,
            abstain_votes=1,
            decisions=[],
        )

        assert record.yes_percentage == 70.0

    def test_yes_percentage_zero_total(self):
        """Test yes_percentage with zero total votes."""
        record = VotingRecord(
            official_id="off-1",
            official_name="Test",
            topic="all",
            total_votes=0,
            yes_votes=0,
            no_votes=0,
            abstain_votes=0,
            decisions=[],
        )

        assert record.yes_percentage == 0.0


class TestElectedOfficialMatching:
    """Test ElectedOfficial name matching."""

    def test_matches_name_exact(self):
        """Test exact name matching."""
        official = ElectedOfficial(
            id="off-1",
            name="Jane Smith",
            seat="Council Member",
            jurisdiction_id="san-rafael",
            term_start=date(2022, 1, 1),
            term_end=None,
            name_variations=["Councilmember Smith"],
        )

        assert official.matches_name("Jane Smith")

    def test_matches_name_partial(self):
        """Test partial name matching."""
        official = ElectedOfficial(
            id="off-1",
            name="Jane Smith",
            seat="Council Member",
            jurisdiction_id="san-rafael",
            term_start=date(2022, 1, 1),
            term_end=None,
            name_variations=[],
        )

        assert official.matches_name("Smith")
        assert official.matches_name("Jane")

    def test_matches_name_variation(self):
        """Test matching via name variation."""
        official = ElectedOfficial(
            id="off-1",
            name="Jane Smith",
            seat="Council Member",
            jurisdiction_id="san-rafael",
            term_start=date(2022, 1, 1),
            term_end=None,
            name_variations=["Councilmember Smith", "J. Smith"],
        )

        assert official.matches_name("Councilmember Smith")
        assert official.matches_name("J. Smith")

    def test_matches_name_case_insensitive(self):
        """Test case-insensitive matching."""
        official = ElectedOfficial(
            id="off-1",
            name="Jane Smith",
            seat="Council Member",
            jurisdiction_id="san-rafael",
            term_start=date(2022, 1, 1),
            term_end=None,
            name_variations=[],
        )

        assert official.matches_name("JANE SMITH")
        assert official.matches_name("jane smith")
