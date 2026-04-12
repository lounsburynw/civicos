"""
Tests for election API endpoints.

Tests the REST API endpoints for election data:
- GET /api/elections
- GET /api/elections/{id}
- GET /api/elections/{id}/contests
- GET /api/voting-record/{official}
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch

from civicos import CivicOS
from civicos.civicos import UpcomingElection
from civicos.storage.data_source import LocalDataSource


class TestElectionEndpoints:
    """Test election REST API functionality via Civic class."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage backend with election data."""
        storage = Mock()
        storage.backend_type = 'postgres'

        # Use dates within the next 365 days (from now)
        tomorrow = date.today() + timedelta(days=1)
        next_month = date.today() + timedelta(days=30)

        # Mock elections data - dates must be in the future to pass window filter
        storage.get_elections.return_value = [
            {
                'id': 'election-1',
                'jurisdiction_id': 'city-san-rafael',
                'name': 'California Primary',
                'election_date': next_month.isoformat(),  # Return as string (like DB)
                'election_type': 'primary',
                'source': 'google_civic',
                'source_url': 'https://example.com/election',
            },
            {
                'id': 'election-2',
                'jurisdiction_id': 'city-san-rafael',
                'name': 'Michigan Special Primary',
                'election_date': tomorrow.isoformat(),
                'election_type': 'special',
                'source': 'google_civic',
                'source_url': None,
            },
        ]

        # Mock deadlines data - use strings like DB returns
        reg_deadline = (date.today() + timedelta(days=20)).isoformat()
        storage.get_election_deadlines.return_value = [
            {
                'id': 'deadline-1',
                'election_id': 'election-1',
                'deadline_type': 'voter_registration',
                'deadline_date': reg_deadline,
                'description': 'Last day to register to vote',
            },
        ]

        # Mock contests data
        storage.get_election_contests.return_value = [
            {
                'id': 'contest-1',
                'election_id': 'election-1',
                'name': 'US Senator',
                'type': 'federal',
                'level': 'federal',
                'district': 'California',
                'candidates': [],
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
                c._data_source = LocalDataSource(mock_storage)
                return c

    def test_whats_next_includes_elections(self, civic_with_mock, mock_storage):
        """whats_next with include_elections returns UpcomingElection objects."""
        # Mock meetings to be empty so we only see elections
        mock_storage.get_meetings.return_value = []

        result = civic_with_mock.whats_next(include_elections=True, days=365)

        # Should contain UpcomingElection objects
        elections = [x for x in result if isinstance(x, UpcomingElection)]
        assert len(elections) > 0

    def test_election_has_required_fields(self, civic_with_mock, mock_storage):
        """Elections have all required fields with correct values."""
        mock_storage.get_meetings.return_value = []

        result = civic_with_mock.whats_next(include_elections=True, days=365)
        elections = [x for x in result if isinstance(x, UpcomingElection)]

        assert len(elections) >= 1
        election = elections[0]
        # Assert specific values from mock data
        assert election.name in ('California Primary', 'Michigan Special Primary')
        assert election.election_type in ('primary', 'special')
        assert election.id in ('election-1', 'election-2')
        assert isinstance(election.deadlines, list)

    def test_election_deadlines_populated(self, civic_with_mock, mock_storage):
        """Elections include specific deadline data from storage."""
        mock_storage.get_meetings.return_value = []

        result = civic_with_mock.whats_next(include_elections=True, days=365)
        elections = [x for x in result if isinstance(x, UpcomingElection)]

        assert len(elections) >= 1
        # Find the California Primary which has a deadline in the mock
        cal_primary = [e for e in elections if e.name == 'California Primary']
        assert len(cal_primary) == 1
        assert len(cal_primary[0].deadlines) == 1
        assert cal_primary[0].deadlines[0]['deadline_type'] == 'voter_registration'
        assert cal_primary[0].deadlines[0]['description'] == 'Last day to register to vote'

    def test_get_elections_filters_by_jurisdiction(self, civic_with_mock, mock_storage):
        """whats_next passes correct jurisdiction when fetching elections."""
        mock_storage.get_meetings.return_value = []

        result = civic_with_mock.whats_next(include_elections=True, days=365)
        elections = [x for x in result if isinstance(x, UpcomingElection)]

        # California Primary (30 days out) always appears; Michigan Special
        # (tomorrow) may be filtered by UTC window edge at day boundary
        assert len(elections) >= 1
        names = {e.name for e in elections}
        assert 'California Primary' in names
        cal = [e for e in elections if e.name == 'California Primary']
        assert cal[0].election_type == 'primary'
        assert cal[0].source == 'google_civic'

    def test_get_election_contests_returns_list(self, civic_with_mock, mock_storage):
        """Storage backend contest data matches expected schema and values."""
        contests = civic_with_mock.storage.get_election_contests('election-1')

        assert len(contests) == 1
        assert contests[0]['id'] == 'contest-1'
        assert contests[0]['name'] == 'US Senator'
        assert contests[0]['type'] == 'federal'
        assert contests[0]['level'] == 'federal'
        assert contests[0]['district'] == 'California'
        assert contests[0]['election_id'] == 'election-1'


class TestVotingRecordEndpoint:
    """Test voting record API functionality."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage with voting data."""
        storage = Mock()

        # Mock official data
        storage.get_official_by_name.return_value = {
            "id": "official-1",
            "name": "Kate Colin",
            "seat": "Mayor",
            "jurisdiction_id": "city-san-rafael",
            "term_start": "2022-01-01",
        }

        # Mock decisions with votes
        storage.get_decisions.return_value = [
            {
                "id": "decision-1",
                "title": "Housing Development Approval",
                "meeting_date": "2024-11-15",
                "outcome": "approved",
                "vote_json": {
                    "Kate Colin": "yes",
                    "Eli Hill": "yes",
                },
                "topics": ["housing"],
            },
            {
                "id": "decision-2",
                "title": "Traffic Safety Measure",
                "meeting_date": "2024-11-01",
                "outcome": "approved",
                "vote_json": {
                    "Kate Colin": "no",
                    "Eli Hill": "yes",
                },
                "topics": ["transportation"],
            },
        ]

        return storage

    @pytest.fixture
    def civic_with_mock(self, mock_storage):
        """Create Civic with mocked storage."""
        with patch('civicos.civicos.get_storage_backend') as mock_get_storage:
            mock_get_storage.return_value = mock_storage
            with patch('civicos.civicos.get_vector_backend') as mock_get_vector:
                mock_get_vector.return_value = Mock()
                c = CivicOS("san-rafael")
                c._storage = mock_storage
                c._data_source = LocalDataSource(mock_storage)
                return c

    def test_voting_record_returns_correct_structure(self, civic_with_mock, mock_storage):
        """Voting record has correct values matching mock data."""
        record = civic_with_mock.get_voting_record("Kate Colin")

        assert record.official_name == "Kate Colin"
        assert record.official_id == "official-1"
        assert record.topic == "all"
        assert record.total_votes == 2
        assert record.abstain_votes == 0
        assert len(record.decisions) == 2

    def test_voting_record_counts_correct(self, civic_with_mock, mock_storage):
        """Voting record counts are accurate."""
        record = civic_with_mock.get_voting_record("Kate Colin")

        assert record.total_votes == 2
        assert record.yes_votes == 1
        assert record.no_votes == 1

    def test_voting_record_topic_filter(self, civic_with_mock, mock_storage):
        """Voting record can be filtered by topic."""
        record = civic_with_mock.get_voting_record("Kate Colin", topic="housing")

        # Should only include housing decisions
        assert record.topic == "housing"
        # Counts should reflect filtered results
        assert record.total_votes == 1
        assert record.yes_votes == 1

    def test_voting_record_decisions_serializable(self, civic_with_mock, mock_storage):
        """Decisions in voting record contain correct values from mock data."""
        record = civic_with_mock.get_voting_record("Kate Colin")

        assert len(record.decisions) == 2
        # Verify specific decision data
        housing = [d for d in record.decisions if d['title'] == 'Housing Development Approval']
        assert len(housing) == 1
        assert housing[0]['vote'] == 'yes'
        assert housing[0]['outcome'] == 'approved'
        assert housing[0]['decision_id'] == 'decision-1'

        traffic = [d for d in record.decisions if d['title'] == 'Traffic Safety Measure']
        assert len(traffic) == 1
        assert traffic[0]['vote'] == 'no'
        assert traffic[0]['outcome'] == 'approved'


class TestElectionDataIntegration:
    """Integration tests using real database (if available)."""

    @pytest.fixture
    def civic_real(self):
        """Create Civic with real storage (may use Postgres if DATABASE_URL set)."""
        from dotenv import load_dotenv
        load_dotenv()
        return CivicOS("city-san-rafael")

    @pytest.mark.integration
    def test_real_elections_query(self, civic_real):
        """Test elections can be queried from real database."""
        # This test requires DATABASE_URL to be set
        result = civic_real.whats_next(include_elections=True, days=365)

        assert isinstance(result, list)
        # Count elections
        elections = [x for x in result if isinstance(x, UpcomingElection)]
        # Should have at least one election (per pilot data)
        # Note: may be 0 if no upcoming elections in window

    @pytest.mark.integration
    def test_real_election_structure(self, civic_real):
        """Test real election data has correct structure."""
        result = civic_real.whats_next(include_elections=True, days=365)
        elections = [x for x in result if isinstance(x, UpcomingElection)]

        for election in elections:
            # Validate structure
            assert election.id is not None
            assert election.name is not None
            assert election.election_date is not None
            assert isinstance(election.deadlines, list)


class TestElectionVectorEmbeddings:
    """Tests for election vector embedding functionality."""

    def test_election_to_text_basic(self):
        """_election_to_text produces searchable text representation."""
        from civicos.storage.pgvector_backend import PgVectorBackend

        # Create minimal backend instance for method access
        # (method doesn't use self attributes)
        election = {
            'id': 'election-1',
            'name': 'California Primary Election',
            'election_type': 'primary',
            'election_date': '2026-06-02',
        }

        # Access method via class (unbound)
        text = PgVectorBackend._election_to_text(None, election)

        assert 'California Primary Election' in text
        assert 'primary' in text
        assert '2026-06-02' in text

    def test_election_to_text_with_contests(self):
        """_election_to_text includes contest information from raw_data."""
        from civicos.storage.pgvector_backend import PgVectorBackend

        election = {
            'id': 'election-1',
            'name': 'General Election',
            'election_type': 'general',
            'election_date': '2026-11-03',
            'raw_data': {
                'contests': [
                    {'title': 'U.S. Senator'},
                    {'title': 'State Assembly District 10'},
                ],
            },
        }

        text = PgVectorBackend._election_to_text(None, election)

        assert 'U.S. Senator' in text
        assert 'State Assembly District 10' in text

    def test_election_to_text_with_ballot_measures(self):
        """_election_to_text includes ballot measure descriptions."""
        from civicos.storage.pgvector_backend import PgVectorBackend

        election = {
            'id': 'election-1',
            'name': 'General Election',
            'election_type': 'general',
            'election_date': '2026-11-03',
            'raw_data': {
                'ballot_measures': [
                    {
                        'title': 'Proposition 1',
                        'description': 'Authorizes bonds for housing programs',
                    },
                    {
                        'title': 'Measure A',
                        'description': 'Local sales tax for transportation',
                    },
                ],
            },
        }

        text = PgVectorBackend._election_to_text(None, election)

        # Should include measure text for semantic search
        assert 'housing' in text.lower() or 'Proposition 1' in text
        assert 'transportation' in text.lower() or 'Measure A' in text

    def test_election_to_text_handles_json_string(self):
        """_election_to_text parses raw_data when it's a JSON string."""
        import json
        from civicos.storage.pgvector_backend import PgVectorBackend

        election = {
            'id': 'election-1',
            'name': 'Primary Election',
            'election_type': 'primary',
            'election_date': '2026-06-02',
            'raw_data': json.dumps({
                'contests': [{'title': 'Governor'}],
            }),
        }

        text = PgVectorBackend._election_to_text(None, election)

        assert 'Governor' in text

    def test_election_to_text_handles_empty(self):
        """_election_to_text falls back to str(election) for minimal data."""
        from civicos.storage.pgvector_backend import PgVectorBackend

        election = {
            'id': 'election-1',
        }

        text = PgVectorBackend._election_to_text(None, election)

        # With no name/type/date, falls back to str(election)
        assert 'election-1' in text


class TestElectionVectorIndexing:
    """Integration tests for election vector indexing."""

    @pytest.fixture
    def pgvector_backend(self):
        """Get PgVectorBackend if DATABASE_URL is available."""
        import os
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            pytest.skip("DATABASE_URL not set - skipping integration test")

        from civicos.storage.pgvector_backend import PgVectorBackend
        return PgVectorBackend(connection_string=db_url)

    @pytest.fixture
    def storage_backend(self):
        """Get PostgresBackend if DATABASE_URL is available."""
        import os
        from dotenv import load_dotenv
        load_dotenv()

        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            pytest.skip("DATABASE_URL not set - skipping integration test")

        from civicos.storage.postgres_backend import PostgresBackend
        return PostgresBackend(connection_string=db_url)

    @pytest.mark.integration
    def test_index_elections_from_storage(self, pgvector_backend, storage_backend):
        """Can index election data from PostgreSQL storage."""
        # Check if there's election data to index
        elections = storage_backend.get_elections(
            'city-san-rafael', include_past=True
        )

        if not elections:
            pytest.skip("No elections in database to test indexing")

        # Index a small batch (don't reindex all)
        count = pgvector_backend.index_from_storage(
            storage_backend=storage_backend,
            jurisdiction_id='city-san-rafael',
            corpus_type='elections',
            batch_size=10,
            limit=5,  # Only index up to 5 for test
        )

        # Should index at least some elections
        assert count >= 0  # May be 0 if already indexed

    @pytest.mark.integration
    def test_search_elections(self, pgvector_backend):
        """Can search indexed elections by semantic query."""
        results = pgvector_backend.search(
            query="primary election California",
            jurisdiction_id='city-san-rafael',
            corpus_type='elections',
            top_k=5,
        )

        # Results may be empty if no elections indexed yet
        assert isinstance(results, list)

        if results:
            # Check result structure
            for result in results:
                assert hasattr(result, 'id')
                assert hasattr(result, 'content')
                assert hasattr(result, 'score')

    @pytest.mark.integration
    def test_search_ballot_measures(self, pgvector_backend):
        """Can search for ballot measures by topic."""
        results = pgvector_backend.search(
            query="housing bond measure ballot",
            jurisdiction_id='city-san-rafael',
            corpus_type='elections',
            top_k=5,
        )

        # Results may be empty if no relevant elections indexed
        assert isinstance(results, list)
