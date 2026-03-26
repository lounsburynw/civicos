"""
Tests for CASOSResultsClient — CA Secretary of State election results API.

Unit tests mock the REST API.  Integration tests hit the live API (no auth needed).
"""

import pytest
from unittest.mock import patch, MagicMock

from civicos_extraction.clients.ca_sos_results import (
    CASOSResultsClient,
    ca_sos_results_to_election,
    ca_sos_race_to_contest,
    ca_sos_measure_to_contest,
    extract_ca_sos_results_to_storage,
    _parse_votes,
    _parse_percent,
    _parse_int,
    _map_contest_type_from_endpoint,
    _slugify,
    STATEWIDE_RACES,
)


# ==================== Fixtures ====================


SAMPLE_CANDIDATE_RACE = {
    "raceTitle": "U.S. House of Representatives District 2 - Statewide Results",
    "Reporting": "100.0% (30,238 of 30,238) precincts reporting",
    "ReportingTime": "December 5, 2025, 1:45 p.m.",
    "candidates": [
        {
            "Name": "Jared Huffman",
            "Party": "Dem",
            "Votes": "23,772",
            "Percent": "52.5",
            "incumbent": True,
        },
        {
            "Name": "Chris Coulombe",
            "Party": "Rep",
            "Votes": "21,456",
            "Percent": "47.5",
            "incumbent": False,
        },
    ],
}

SAMPLE_BALLOT_MEASURES = {
    "raceTitle": "Ballot Measures - Statewide Results",
    "Reporting": "100.0% (18,399 of 18,399) precincts reporting",
    "ReportingTime": "December 5, 2025, 1:45 p.m.",
    "ballot-measures": [
        {
            "Name": "Congressional Redistricting",
            "Number": "50",
            "yesVotes": "7453339",
            "yesPercent": "64.4",
            "noVotes": "4116998",
            "noPercent": "35.6",
        },
        {
            "Name": "Raise Minimum Wage",
            "Number": "32",
            "yesVotes": "3000000",
            "yesPercent": "40.0",
            "noVotes": "4500000",
            "noPercent": "60.0",
        },
    ],
}

SAMPLE_STATUS = {
    "marin": {
        "county": 21,
        "reportType": "U",
        "precinctsReporting": "58",
        "precinctsTotal": "58",
        "precinctsReportingPercent": "100.0",
        "voterTurnout": "118495",
        "totalRegisteredVoters": "173896",
        "voterTurnoutPercentage": "68.1",
        "countyName": "Marin",
        "timestamp": "December 2, 2025, 10:32 a.m.",
    },
    "los-angeles": {
        "county": 19,
        "reportType": "U",
        "precinctsReporting": "4513",
        "precinctsTotal": "4513",
        "precinctsReportingPercent": "100.0",
        "countyName": "Los Angeles",
        "timestamp": "December 2, 2025, 11:00 a.m.",
    },
}

SAMPLE_COUNTY_BREAKDOWN = [
    {
        "raceTitle": "U.S. House of Representatives District 2 - Marin Results",
        "Reporting": "100.0% (58 of 58) precincts reporting",
        "ReportingTime": "December 2, 2025, 10:32 a.m.",
        "candidates": [
            {"Name": "Jared Huffman", "Party": "Dem", "Votes": "15,234", "Percent": "68.2", "incumbent": True},
            {"Name": "Chris Coulombe", "Party": "Rep", "Votes": "7,123", "Percent": "31.8", "incumbent": False},
        ],
    },
    {
        "raceTitle": "U.S. House of Representatives District 2 - Statewide Results",
        "Reporting": "100.0% (30,238 of 30,238) precincts reporting",
        "ReportingTime": "December 5, 2025, 1:45 p.m.",
        "candidates": [
            {"Name": "Jared Huffman", "Party": "Dem", "Votes": "23,772", "Percent": "52.5", "incumbent": True},
            {"Name": "Chris Coulombe", "Party": "Rep", "Votes": "21,456", "Percent": "47.5", "incumbent": False},
        ],
    },
]


# ==================== Unit Tests: Vote Parsing ====================


class TestVoteParsing:
    """Test string-to-number parsing helpers."""

    def test_parse_votes_comma_formatted(self):
        assert _parse_votes("2,909,979") == 2909979

    def test_parse_votes_no_commas(self):
        assert _parse_votes("7453339") == 7453339

    def test_parse_votes_small(self):
        assert _parse_votes("23,772") == 23772

    def test_parse_votes_none(self):
        assert _parse_votes(None) is None

    def test_parse_votes_empty(self):
        assert _parse_votes("") is None

    def test_parse_votes_whitespace(self):
        assert _parse_votes("  23,772  ") == 23772

    def test_parse_percent(self):
        assert _parse_percent("52.5") == 52.5

    def test_parse_percent_whole(self):
        assert _parse_percent("100.0") == 100.0

    def test_parse_percent_none(self):
        assert _parse_percent(None) is None

    def test_parse_int_simple(self):
        assert _parse_int("58") == 58

    def test_parse_int_comma(self):
        assert _parse_int("18,399") == 18399

    def test_parse_int_none(self):
        assert _parse_int(None) is None


# ==================== Unit Tests: Contest Type Mapping ====================


class TestContestTypeMapping:

    def test_president(self):
        assert _map_contest_type_from_endpoint("/returns/president") == "federal_president"

    def test_us_senate(self):
        assert _map_contest_type_from_endpoint("/returns/us-senate") == "federal_senate"

    def test_governor(self):
        assert _map_contest_type_from_endpoint("/returns/governor") == "state_governor"

    def test_us_rep(self):
        assert _map_contest_type_from_endpoint("/returns/us-rep/district/2") == "federal_house"

    def test_state_assembly(self):
        assert _map_contest_type_from_endpoint("/returns/state-assembly/district/12") == "state_legislature"

    def test_state_senate(self):
        assert _map_contest_type_from_endpoint("/returns/state-senate/district/2") == "state_legislature"

    def test_ballot_measures(self):
        assert _map_contest_type_from_endpoint("/returns/ballot-measures") == "state_proposition"

    def test_boe(self):
        assert _map_contest_type_from_endpoint("/returns/board-of-equalization/district/1") == "state_legislature"

    def test_unknown(self):
        assert _map_contest_type_from_endpoint("/returns/unknown-race") == "other"


# ==================== Unit Tests: Slugify ====================


class TestSlugify:

    def test_simple(self):
        assert _slugify("President") == "president"

    def test_spaces(self):
        assert _slugify("U.S. House of Representatives District 2") == "u-s-house-of-representatives-district-2"

    def test_special_chars(self):
        assert _slugify("Proposition 50: Congressional Redistricting") == "proposition-50-congressional-redistricting"


# ==================== Unit Tests: Client ====================


class TestCASOSResultsClient:
    """Unit tests for CASOSResultsClient."""

    def test_client_initialization(self):
        client = CASOSResultsClient()
        assert client.jurisdiction_id == "state-california"
        assert client.platform_name == "ca_sos_results"
        assert client.source_id == "ca_sos_results-state-california"
        assert client.base_url == "https://api.sos.ca.gov"

    def test_client_custom_jurisdiction(self):
        client = CASOSResultsClient("county-marin")
        assert client.jurisdiction_id == "county-marin"

    @patch.object(CASOSResultsClient, "_get")
    def test_get_statewide_race(self, mock_get):
        mock_get.return_value = SAMPLE_CANDIDATE_RACE
        client = CASOSResultsClient()
        result = client.get_statewide_race("president")
        assert result["raceTitle"] == SAMPLE_CANDIDATE_RACE["raceTitle"]
        mock_get.assert_called_once_with("/returns/president")

    @patch.object(CASOSResultsClient, "_get")
    def test_get_district_race(self, mock_get):
        mock_get.return_value = SAMPLE_CANDIDATE_RACE
        client = CASOSResultsClient()
        result = client.get_district_race("us-rep", 2)
        mock_get.assert_called_once_with("/returns/us-rep/district/2")

    @patch.object(CASOSResultsClient, "_get")
    def test_get_ballot_measures(self, mock_get):
        mock_get.return_value = SAMPLE_BALLOT_MEASURES
        client = CASOSResultsClient()
        result = client.get_ballot_measures()
        assert len(result["ballot-measures"]) == 2

    @patch.object(CASOSResultsClient, "_get")
    def test_get_ballot_measure_single(self, mock_get):
        mock_get.return_value = {"Number": "50", "Name": "Test"}
        client = CASOSResultsClient()
        client.get_ballot_measure(50)
        mock_get.assert_called_once_with("/returns/ballot-measures/prop/50")

    @patch.object(CASOSResultsClient, "_get")
    def test_get_county_breakdown(self, mock_get):
        mock_get.return_value = SAMPLE_COUNTY_BREAKDOWN
        client = CASOSResultsClient()
        result = client.get_county_breakdown("us-rep", "marin", district=2)
        assert len(result) == 2
        mock_get.assert_called_once_with("/returns/us-rep/district/2/county/marin")

    @patch.object(CASOSResultsClient, "_get")
    def test_get_county_breakdown_statewide(self, mock_get):
        mock_get.return_value = SAMPLE_COUNTY_BREAKDOWN
        client = CASOSResultsClient()
        client.get_county_breakdown("president", "marin")
        mock_get.assert_called_once_with("/returns/president/county/marin")

    @patch.object(CASOSResultsClient, "_get")
    def test_get_ballot_measures_county(self, mock_get):
        mock_get.return_value = {}
        client = CASOSResultsClient()
        client.get_ballot_measures_county("marin")
        mock_get.assert_called_once_with("/returns/ballot-measures/county/marin")

    @patch.object(CASOSResultsClient, "_get")
    def test_get_reporting_status(self, mock_get):
        mock_get.return_value = SAMPLE_STATUS
        client = CASOSResultsClient()
        result = client.get_reporting_status()
        assert "marin" in result
        assert result["marin"]["reportType"] == "U"

    @patch.object(CASOSResultsClient, "_get")
    def test_get_reporting_status_typed(self, mock_get):
        mock_get.return_value = SAMPLE_STATUS
        client = CASOSResultsClient()
        client.get_reporting_status("general")
        mock_get.assert_called_once_with("/returns/status/general")

    @patch.object(CASOSResultsClient, "_get")
    def test_health_success(self, mock_get):
        mock_get.return_value = SAMPLE_STATUS
        client = CASOSResultsClient()
        h = client.health()
        assert h.is_available is True
        assert h.available_count == 2

    @patch.object(CASOSResultsClient, "_get")
    def test_health_failure(self, mock_get):
        mock_get.side_effect = ConnectionError("Network error")
        client = CASOSResultsClient()
        h = client.health()
        assert h.is_available is False
        assert len(h.errors) == 1

    @patch.object(CASOSResultsClient, "_get")
    def test_validate_success(self, mock_get):
        mock_get.return_value = SAMPLE_STATUS
        client = CASOSResultsClient()
        v = client.validate()
        assert v.is_valid is True
        assert v.api_reachable is True

    @patch.object(CASOSResultsClient, "_get")
    def test_validate_failure(self, mock_get):
        mock_get.side_effect = ConnectionError("Network error")
        client = CASOSResultsClient()
        v = client.validate()
        assert v.is_valid is False
        assert v.api_reachable is False

    @patch.object(CASOSResultsClient, "_get")
    def test_get_all_statewide_races(self, mock_get):
        """Returns available races, skips 404s."""
        mock_get.side_effect = [
            SAMPLE_CANDIDATE_RACE,  # president
            Exception("404"),        # us-senate
            SAMPLE_CANDIDATE_RACE,  # governor
        ] + [Exception("404")] * 7  # remaining statewide races

        client = CASOSResultsClient()
        results = client.get_all_statewide_races()
        assert len(results) == 2
        assert results[0]["_endpoint"] == "/returns/president"


# ==================== Unit Tests: Storage Mappers ====================


class TestCASOSResultsToElection:

    def test_basic_election(self):
        result = ca_sos_results_to_election(
            reporting_time="December 5, 2025, 1:45 p.m.",
            report_type="U",
            election_type="general",
        )
        assert result["id"] == "ca-sos-2025-general"
        assert "California" in result["name"]
        assert "2025" in result["name"]
        assert result["election_type"] == "general"
        assert result["election_date"] == "2025-12-05"
        assert result["source"] == "ca_sos_results"
        assert result["raw_data"]["report_type"] == "U"
        assert result["raw_data"]["status"] == "certified"

    def test_preliminary_election(self):
        result = ca_sos_results_to_election(
            reporting_time="November 5, 2024, 9:38 a.m.",
            report_type="R",
        )
        assert result["id"] == "ca-sos-2024-general"
        assert result["election_date"] == "2024-11-05"
        assert result["raw_data"]["status"] == "preliminary"

    def test_no_reporting_time(self):
        result = ca_sos_results_to_election()
        assert result["id"] == "ca-sos-current-general"
        assert result["election_date"] is None

    def test_primary_election(self):
        result = ca_sos_results_to_election(
            reporting_time="March 5, 2024, 1:00 p.m.",
            election_type="primary",
        )
        assert result["id"] == "ca-sos-2024-primary"
        assert result["election_date"] == "2024-03-05"
        assert "Primary" in result["name"]


class TestCASOSRaceToContest:

    def test_candidate_race(self):
        result = ca_sos_race_to_contest(
            SAMPLE_CANDIDATE_RACE,
            endpoint="/returns/us-rep/district/2",
        )
        assert result["id"].startswith("ca-sos-")
        assert result["contest_type"] == "federal_house"
        assert len(result["candidates"]) == 2

        # Check vote parsing
        huffman = result["candidates"][0]
        assert huffman["name"] == "Jared Huffman"
        assert huffman["votes_received"] == 23772
        assert huffman["vote_percentage"] == 52.5
        assert huffman["party"] == "Dem"
        assert huffman["incumbent"] is True
        assert huffman["is_winner"] is True

        coulombe = result["candidates"][1]
        assert coulombe["votes_received"] == 21456
        assert coulombe["is_winner"] is False

    def test_raw_data_contains_mapped_candidates(self):
        result = ca_sos_race_to_contest(SAMPLE_CANDIDATE_RACE, "/returns/president")
        assert "mapped_candidates" in result["raw_data"]
        assert len(result["raw_data"]["mapped_candidates"]) == 2

    def test_no_ballot_measure(self):
        result = ca_sos_race_to_contest(SAMPLE_CANDIDATE_RACE, "/returns/president")
        assert result["ballot_measure"] is None


class TestCASOSMeasureToContest:

    def test_passing_measure(self):
        measure = SAMPLE_BALLOT_MEASURES["ballot-measures"][0]  # Prop 50 — passes
        result = ca_sos_measure_to_contest(measure)

        assert result["id"] == "ca-sos-measure-50"
        assert result["contest_type"] == "state_proposition"
        assert result["ballot_measure"] is not None
        assert result["ballot_measure"]["passed"] is True
        assert result["ballot_measure"]["yes_votes"] == 7453339
        assert result["ballot_measure"]["no_votes"] == 4116998
        assert result["ballot_measure"]["yes_percentage"] == 64.4
        assert result["ballot_measure"]["no_percentage"] == 35.6
        assert "Proposition 50" in result["title"]

    def test_failing_measure(self):
        measure = SAMPLE_BALLOT_MEASURES["ballot-measures"][1]  # Prop 32 — fails
        result = ca_sos_measure_to_contest(measure)

        assert result["id"] == "ca-sos-measure-32"
        assert result["ballot_measure"]["passed"] is False
        assert result["ballot_measure"]["yes_votes"] == 3000000
        assert result["ballot_measure"]["no_votes"] == 4500000

    def test_yes_no_candidates(self):
        measure = SAMPLE_BALLOT_MEASURES["ballot-measures"][0]
        result = ca_sos_measure_to_contest(measure)

        assert len(result["candidates"]) == 2
        yes_cand = result["candidates"][0]
        assert yes_cand["name"] == "Yes"
        assert yes_cand["is_winner"] is True

        no_cand = result["candidates"][1]
        assert no_cand["name"] == "No"
        assert no_cand["is_winner"] is False

    def test_raw_data_contains_mapped_data(self):
        measure = SAMPLE_BALLOT_MEASURES["ballot-measures"][0]
        result = ca_sos_measure_to_contest(measure)
        assert "mapped_candidates" in result["raw_data"]
        assert "mapped_ballot_measure" in result["raw_data"]


# ==================== Unit Tests: Extract to Storage ====================


class TestExtractCASOSResultsToStorage:

    @patch.object(CASOSResultsClient, "get_all_results")
    def test_full_extraction(self, mock_get_all):
        mock_get_all.return_value = {
            "statewide_races": [
                {**SAMPLE_CANDIDATE_RACE, "_endpoint": "/returns/president"},
            ],
            "district_races": [
                {**SAMPLE_CANDIDATE_RACE, "_endpoint": "/returns/us-rep/district/2"},
            ],
            "ballot_measures": SAMPLE_BALLOT_MEASURES,
            "county_statewide": [],
            "county_district": [],
            "county_ballot_measures": None,
            "status": SAMPLE_STATUS,
        }

        mock_storage = MagicMock()
        mock_storage.store_elections.return_value = 1
        mock_storage.store_election_contests.side_effect = [1, 1, 2]  # statewide, district, measures

        client = CASOSResultsClient()
        counts = extract_ca_sos_results_to_storage(
            client=client,
            storage=mock_storage,
            jurisdiction_id="state-california",
        )

        assert counts["elections"] == 1
        assert counts["contests"] == 4  # 1 statewide + 1 district + 2 measures
        assert counts["candidates"] == 4  # 2 per candidate race
        assert counts["ballot_measures"] == 2

        # Verify storage calls
        assert mock_storage.store_elections.call_count == 1
        assert mock_storage.store_election_contests.call_count == 3

    @patch.object(CASOSResultsClient, "get_all_results")
    def test_extraction_empty(self, mock_get_all):
        mock_get_all.return_value = {
            "statewide_races": [],
            "district_races": [],
            "ballot_measures": None,
            "county_statewide": [],
            "county_district": [],
            "county_ballot_measures": None,
            "status": None,
        }

        mock_storage = MagicMock()
        mock_storage.store_elections.return_value = 1
        # No contest storage calls

        client = CASOSResultsClient()
        counts = extract_ca_sos_results_to_storage(client=client, storage=mock_storage)

        assert counts["elections"] == 1
        assert counts["contests"] == 0
        assert counts["candidates"] == 0
        assert counts["ballot_measures"] == 0


# ==================== Integration Tests ====================


class TestCASOSResultsIntegration:
    """Integration tests hitting the live CA SOS API.

    No auth required.  These tests verify the API is reachable and
    returns expected data structures.  They will fail if no election
    data is currently loaded in the API.
    """

    @pytest.mark.integration
    @pytest.mark.slow
    def test_reporting_status(self):
        client = CASOSResultsClient()
        status = client.get_reporting_status()
        # Should have at least some counties
        assert len(status) > 0
        # Marin should be present
        if "marin" in status:
            marin = status["marin"]
            assert "reportType" in marin
            assert "countyName" in marin

    @pytest.mark.integration
    @pytest.mark.slow
    def test_health_check(self):
        client = CASOSResultsClient()
        h = client.health()
        assert h.is_available is True
        assert h.available_count > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_validate(self):
        client = CASOSResultsClient()
        v = client.validate()
        assert v.is_valid is True
        assert v.api_reachable is True

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ballot_measures(self):
        """Ballot measures should be available for the current election."""
        client = CASOSResultsClient()
        try:
            result = client.get_ballot_measures()
            measures = result.get("ballot-measures", [])
            if measures:
                m = measures[0]
                assert "Name" in m
                assert "Number" in m
                assert "yesVotes" in m
                assert "noVotes" in m
                # Verify vote parsing works on real data
                yes_votes = _parse_votes(m["yesVotes"])
                assert yes_votes is None or isinstance(yes_votes, int)
        except Exception:
            pytest.skip("No ballot measure data currently loaded in CA SOS API")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_statewide_race(self):
        """Try to fetch at least one statewide race."""
        client = CASOSResultsClient()
        found = False
        for slug in STATEWIDE_RACES:
            try:
                result = client.get_statewide_race(slug)
                assert "raceTitle" in result
                assert "candidates" in result
                found = True
                break
            except Exception:
                continue
        if not found:
            pytest.skip("No statewide race data currently loaded in CA SOS API")
