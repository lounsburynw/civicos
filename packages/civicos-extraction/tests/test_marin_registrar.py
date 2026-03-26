"""
Tests for MarinRegistrarResultsClient — Marin County election results GraphQL client.

Unit tests mock the GraphQL API. Integration tests hit the live API (no auth needed).
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from civicos_extraction.clients.marin_registrar import (
    MarinRegistrarResultsClient,
    marin_results_to_election,
    marin_results_to_contest,
    _infer_election_type_from_name,
    _parse_election_date,
    _map_contest_type,
    _PSEUDO_CANDIDATES,
)


# ==================== Fixtures ====================


SAMPLE_EVENTS = [
    {"id": 35, "name": "November 5, 2024 General Election", "group": "2024", "count": 42},
    {"id": 34, "name": "March 5, 2024 Primary Election", "group": "2024", "count": 15},
]

SAMPLE_CONTEST_CANDIDATE = {
    "id": 585,
    "name": "Mayor",
    "office": {"id": 10, "name": "Mayor"},
    "division": {"id": 5, "displayName": "City of San Rafael", "divisionType": {"name": "City"}},
    "event": {"id": 35, "startDate": "2024-11-05T00:00:00", "type": {"name": "General"}},
    "candidates": [
        {
            "displayName": "Kate Colin",
            "nVotes": 15234,
            "pctCandidateVotes": 62.5,
            "candidate": {"pseudocandidate": None},
            "isWinner": True,
            "party": None,
        },
        {
            "displayName": "John Doe",
            "nVotes": 9123,
            "pctCandidateVotes": 37.5,
            "candidate": {"pseudocandidate": None},
            "isWinner": False,
            "party": None,
        },
        {
            "displayName": "TOTAL",
            "nVotes": 24357,
            "pctCandidateVotes": 100.0,
            "candidate": {"pseudocandidate": "TOTAL_VOTES"},
            "isWinner": False,
            "party": None,
        },
    ],
    "ballotQuestionId": None,
    "ballotQuestion": None,
    "nSeats": 1,
    "hasWinners": True,
}

SAMPLE_CONTEST_BALLOT_MEASURE = {
    "id": 600,
    "name": "Measure A",
    "office": {"id": None, "name": ""},
    "division": {"id": 5, "displayName": "City of San Rafael", "divisionType": {"name": "City"}},
    "event": {"id": 35, "startDate": "2024-11-05T00:00:00", "type": {"name": "General"}},
    "candidates": [
        {
            "displayName": "Yes",
            "nVotes": 18000,
            "pctCandidateVotes": 66.7,
            "candidate": {"pseudocandidate": None},
            "isWinner": True,
            "party": None,
        },
        {
            "displayName": "No",
            "nVotes": 9000,
            "pctCandidateVotes": 33.3,
            "candidate": {"pseudocandidate": None},
            "isWinner": False,
            "party": None,
        },
        {
            "displayName": "TOTAL",
            "nVotes": 27000,
            "pctCandidateVotes": 100.0,
            "candidate": {"pseudocandidate": "TOTAL_BALLOTS"},
            "isWinner": False,
            "party": None,
        },
    ],
    "ballotQuestionId": 42,
    "ballotQuestion": {
        "questionText": "Sales Tax for Roads",
        "type": {"name": "tax"},
        "questionNumber": "A",
    },
    "nSeats": 1,
    "hasWinners": True,
}


# ==================== Unit Tests: Client ====================


class TestMarinRegistrarResultsClient:
    """Unit tests for MarinRegistrarResultsClient."""

    def test_client_initialization(self):
        client = MarinRegistrarResultsClient("city-san-rafael")
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.platform_name == "marin_registrar_results"
        assert client.source_id == "marin_registrar_results-city-san-rafael"

    def test_client_default_jurisdiction(self):
        client = MarinRegistrarResultsClient()
        assert client.jurisdiction_id == "city-san-rafael"

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_list_elections(self, mock_graphql):
        mock_graphql.return_value = {"searchSuggestions": {"events": SAMPLE_EVENTS}}
        client = MarinRegistrarResultsClient()
        events = client.list_elections(from_year=2024, to_year=2025)
        assert len(events) == 2
        assert events[0]["id"] == 35
        assert events[0]["name"] == "November 5, 2024 General Election"

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_list_contests(self, mock_graphql):
        mock_graphql.return_value = {"search": {"results": [SAMPLE_CONTEST_CANDIDATE]}}
        client = MarinRegistrarResultsClient()
        contests = client.list_contests(event_id=35)
        assert len(contests) == 1
        assert contests[0]["id"] == 585

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_list_contests_paginates(self, mock_graphql):
        """Test that list_contests fetches multiple pages."""
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": i} for i in range(100, 120)]
        mock_graphql.side_effect = [
            {"search": {"results": page1}},
            {"search": {"results": page2}},
        ]
        client = MarinRegistrarResultsClient()
        contests = client.list_contests(event_id=35, page_size=100)
        assert len(contests) == 120
        assert mock_graphql.call_count == 2

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_get_election_results_filters_pseudocandidates(self, mock_graphql):
        """Pseudo-candidates (TOTAL_VOTES, etc.) should be filtered out."""
        mock_graphql.return_value = {"search": {"results": [SAMPLE_CONTEST_CANDIDATE]}}
        client = MarinRegistrarResultsClient()
        results = client.get_election_results(event_id=35)
        contest = results["contests"][0]
        # Should have 2 real candidates, not 3
        assert len(contest["candidates"]) == 2
        names = [c["displayName"] for c in contest["candidates"]]
        assert "Kate Colin" in names
        assert "John Doe" in names
        assert "TOTAL" not in names

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_get_election_results_division_filter(self, mock_graphql):
        """Division filter should limit contests to matching division."""
        other_contest = {
            **SAMPLE_CONTEST_CANDIDATE,
            "id": 999,
            "division": {"id": 99, "displayName": "Town of Corte Madera", "divisionType": {"name": "Town"}},
        }
        mock_graphql.return_value = {"search": {"results": [SAMPLE_CONTEST_CANDIDATE, other_contest]}}
        client = MarinRegistrarResultsClient()
        results = client.get_election_results(event_id=35, division_filter="San Rafael")
        assert len(results["contests"]) == 1
        assert results["contests"][0]["id"] == 585

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_get_precinct_data(self, mock_graphql):
        mock_graphql.return_value = {
            "contestGranularData": {
                "candidates": [{"candidateId": 1, "nVotes": 100}],
                "voteChannels": [{"id": 5, "name": "Vote Center"}],
                "divisions": [],
            }
        }
        client = MarinRegistrarResultsClient()
        data = client.get_precinct_data(contest_id=585)
        assert len(data["candidates"]) == 1
        assert len(data["voteChannels"]) == 1

    @patch.object(MarinRegistrarResultsClient, "_graphql")
    def test_graphql_error_raises(self, mock_graphql):
        """GraphQL errors should raise RuntimeError."""
        mock_graphql.side_effect = RuntimeError("GraphQL errors: [{'message': 'bad query'}]")
        client = MarinRegistrarResultsClient()
        with pytest.raises(RuntimeError, match="GraphQL errors"):
            client.list_elections()


# ==================== Unit Tests: Helpers ====================


class TestElectionTypeInference:
    def test_general(self):
        assert _infer_election_type_from_name("November 5, 2024 General Election") == "general"

    def test_primary(self):
        assert _infer_election_type_from_name("March 5, 2024 Primary Election") == "primary"

    def test_special(self):
        assert _infer_election_type_from_name("January 27, 2026 Special Parcel Tax Election") == "special"

    def test_recall(self):
        assert _infer_election_type_from_name("September 14, 2021 Recall Election") == "recall"

    def test_unknown_defaults_general(self):
        assert _infer_election_type_from_name("Some Election") == "general"


class TestParsElectionDate:
    def test_iso_datetime(self):
        assert _parse_election_date("2024-11-05T00:00:00") == "2024-11-05"

    def test_iso_date_only(self):
        assert _parse_election_date("2024-11-05") == "2024-11-05"

    def test_none(self):
        assert _parse_election_date(None) is None

    def test_empty_string(self):
        assert _parse_election_date("") is None


class TestMapContestType:
    def test_mayor(self):
        assert _map_contest_type({"office": {"name": "Mayor"}, "division": {}}) == "local_mayor"

    def test_council(self):
        assert _map_contest_type({"office": {"name": "City Council Member"}, "division": {}}) == "local_council"

    def test_school_board(self):
        assert _map_contest_type({
            "office": {"name": "School Board Trustee"},
            "division": {"divisionType": {"name": "School District"}},
        }) == "local_school_board"

    def test_ballot_measure(self):
        assert _map_contest_type({
            "ballotQuestionId": 42,
            "office": {"name": ""},
            "division": {"divisionType": {"name": "City"}},
        }) == "local_measure"

    def test_state_assembly(self):
        assert _map_contest_type({"office": {"name": "Assembly Member"}, "division": {}}) == "state_legislature"

    def test_federal_president(self):
        assert _map_contest_type({"office": {"name": "President"}, "division": {}}) == "federal_president"

    def test_other(self):
        assert _map_contest_type({"office": {"name": "Fire District Commissioner"}, "division": {}}) == "other"


# ==================== Unit Tests: Storage Mappers ====================


class TestMarinResultsToElection:
    def test_basic_mapping(self):
        event = {"id": 35, "name": "November 5, 2024 General Election", "group": "2024", "count": 42}
        result = marin_results_to_election(event, election_date="2024-11-05", election_type_name="General")
        assert result["id"] == "marin-results-35"
        assert result["name"] == "November 5, 2024 General Election"
        assert result["election_date"] == "2024-11-05"
        assert result["election_type"] == "general"
        assert result["source"] == "marin_registrar_results"
        assert "raw_data" in result

    def test_infers_type_from_name_when_no_type_given(self):
        event = {"id": 34, "name": "March 5, 2024 Primary Election", "group": "2024", "count": 15}
        result = marin_results_to_election(event)
        assert result["election_type"] == "primary"


class TestMarinResultsToContest:
    def test_candidate_contest(self):
        # Remove pseudo-candidate for test input (as client filters them)
        contest = {**SAMPLE_CONTEST_CANDIDATE}
        contest["candidates"] = [c for c in contest["candidates"] if not (c["candidate"] or {}).get("pseudocandidate")]

        result = marin_results_to_contest(contest)
        assert result["id"] == "marin-contest-585"
        assert result["title"] == "Mayor"
        assert result["contest_type"] == "local_mayor"
        assert result["district_name"] == "City of San Rafael"
        assert result["number_elected"] == 1
        assert len(result["candidates"]) == 2
        assert result["ballot_measure"] is None

        winner = next(c for c in result["candidates"] if c["is_winner"])
        assert winner["name"] == "Kate Colin"
        assert winner["votes_received"] == 15234
        assert winner["vote_percentage"] == 62.5

    def test_ballot_measure_contest(self):
        contest = {**SAMPLE_CONTEST_BALLOT_MEASURE}
        contest["candidates"] = [c for c in contest["candidates"] if not (c["candidate"] or {}).get("pseudocandidate")]

        result = marin_results_to_contest(contest)
        assert result["contest_type"] == "local_measure"
        assert result["ballot_measure"] is not None

        bm = result["ballot_measure"]
        assert bm["title"].startswith("Measure A:")
        assert bm["passed"] is True
        assert bm["yes_votes"] == 18000
        assert bm["no_votes"] == 9000
        assert bm["yes_percentage"] == 66.7
        assert bm["no_percentage"] == 33.3

    def test_candidate_ids_are_unique(self):
        contest = {**SAMPLE_CONTEST_CANDIDATE}
        contest["candidates"] = [c for c in contest["candidates"] if not (c["candidate"] or {}).get("pseudocandidate")]
        result = marin_results_to_contest(contest)
        ids = [c["id"] for c in result["candidates"]]
        assert len(ids) == len(set(ids))

    def test_raw_data_contains_mapped_candidates(self):
        """raw_data must contain mapped_candidates for JSONB persistence."""
        contest = {**SAMPLE_CONTEST_CANDIDATE}
        contest["candidates"] = [c for c in contest["candidates"] if not (c["candidate"] or {}).get("pseudocandidate")]
        result = marin_results_to_contest(contest)
        raw = result["raw_data"]
        assert "mapped_candidates" in raw
        assert len(raw["mapped_candidates"]) == 2
        assert raw["mapped_candidates"][0]["votes_received"] == 15234

    def test_raw_data_contains_mapped_ballot_measure(self):
        """raw_data must contain mapped_ballot_measure for JSONB persistence."""
        contest = {**SAMPLE_CONTEST_BALLOT_MEASURE}
        contest["candidates"] = [c for c in contest["candidates"] if not (c["candidate"] or {}).get("pseudocandidate")]
        result = marin_results_to_contest(contest)
        raw = result["raw_data"]
        assert "mapped_ballot_measure" in raw
        assert raw["mapped_ballot_measure"]["yes_votes"] == 18000
        assert raw["mapped_ballot_measure"]["passed"] is True


# ==================== Pseudo-Candidate Filtering ====================


class TestPseudoCandidateFiltering:
    def test_pseudo_candidate_set(self):
        assert "TOTAL_VOTES" in _PSEUDO_CANDIDATES
        assert "TOTAL_BALLOTS" in _PSEUDO_CANDIDATES
        assert "PSEUDOCANDIDATE" in _PSEUDO_CANDIDATES
        assert "VOTER_STAT" in _PSEUDO_CANDIDATES

    def test_real_candidate_not_filtered(self):
        assert None not in _PSEUDO_CANDIDATES


# ==================== Integration Tests (Live API) ====================


class TestMarinRegistrarResultsIntegration:
    """Integration tests that hit the live Marin GraphQL API.

    These require network access but no authentication.
    Mark as integration/slow so they can be skipped in CI smoke tests.
    """

    @pytest.mark.integration
    @pytest.mark.slow
    def test_list_elections_returns_data(self):
        """Should return 40+ elections from 2010-2025."""
        client = MarinRegistrarResultsClient()
        events = client.list_elections(from_year=2010, to_year=2025)
        assert len(events) >= 30  # Conservative: API has 46
        assert all("id" in e for e in events)
        assert all("name" in e for e in events)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_list_contests_for_recent_election(self):
        """Should return contests for the Nov 2024 general election."""
        client = MarinRegistrarResultsClient()
        events = client.list_elections(from_year=2024, to_year=2025)
        # Find the November 2024 general
        general = next((e for e in events if "2024" in e.get("name", "") and "general" in e.get("name", "").lower()), None)
        if not general:
            pytest.skip("November 2024 General Election not found")
        contests = client.list_contests(general["id"])
        assert len(contests) >= 10  # Should have many contests
        # Verify structure
        first = contests[0]
        assert "id" in first
        assert "candidates" in first
        assert "office" in first

    @pytest.mark.integration
    @pytest.mark.slow
    def test_get_election_results_with_filter(self):
        """Should filter to San Rafael contests only."""
        client = MarinRegistrarResultsClient()
        events = client.list_elections(from_year=2024, to_year=2025)
        general = next((e for e in events if "2024" in e.get("name", "") and "general" in e.get("name", "").lower()), None)
        if not general:
            pytest.skip("November 2024 General Election not found")
        results = client.get_election_results(general["id"], division_filter="San Rafael")
        assert results["total_contests"] > 0
        for c in results["contests"]:
            div = c.get("division", {}).get("displayName", "")
            assert "san rafael" in div.lower()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_health_check(self):
        client = MarinRegistrarResultsClient()
        health = client.health()
        assert health.is_available is True
        assert health.available_count > 0
        assert health.check_duration_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_validate(self):
        client = MarinRegistrarResultsClient()
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True
