"""Tests for the Clarity Elections ENR client and wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from civicos_extraction.clients.clarity_elections import (
    BASE_URL,
    CLARITY_INSTANCES,
    ClarityElectionsClient,
    _county_to_url_name,
    _infer_election_date,
    _infer_election_type,
    _is_parallel_array_format,
    clarity_contest_to_storage,
    clarity_results_to_election,
    detect_clarity_elections,
    extract_clarity_results_to_storage,
    has_clarity_instance,
    parse_summary_contests,
)


# ==================== Registry & Helpers ====================


class TestClarityRegistry:
    """Validate the CLARITY_INSTANCES registry."""

    def test_ca_has_known_counties(self):
        ca = CLARITY_INSTANCES["CA"]
        assert "butte" in ca
        assert "contra costa" in ca
        assert "santa clara" in ca
        assert "ventura" in ca
        assert "shasta" in ca

    def test_civera_overlap_marked(self):
        ca = CLARITY_INSTANCES["CA"]
        assert ca["marin"]["prefer_civera"] is True
        assert ca["sonoma"]["prefer_civera"] is True

    def test_net_new_not_prefer_civera(self):
        ca = CLARITY_INSTANCES["CA"]
        for county in ["butte", "contra costa", "madera", "merced", "santa clara", "shasta", "ventura"]:
            assert ca[county].get("prefer_civera") is not True, f"{county} should not prefer Civera"

    def test_has_clarity_instance_true(self):
        assert has_clarity_instance("santa clara", "CA") is True
        assert has_clarity_instance("Santa Clara", "CA") is True

    def test_has_clarity_instance_false(self):
        assert has_clarity_instance("los angeles", "CA") is False
        assert has_clarity_instance("marin", "TX") is False

    def test_has_clarity_instance_case_insensitive(self):
        assert has_clarity_instance("BUTTE", "ca") is True

    def test_loaded_from_json_file(self):
        """CLARITY_INSTANCES is loaded from data/extraction/clarity_instances.json."""
        from civicos_extraction.clients.clarity_elections import _load_clarity_instances
        loaded = _load_clarity_instances()
        assert "CA" in loaded
        assert "santa clara" in loaded["CA"]
        assert loaded["CA"]["santa clara"]["url_name"] == "Santa_Clara"


class TestCountyToUrlName:
    """URL name generation from county names."""

    def test_simple_county(self):
        assert _county_to_url_name("butte") == "Butte"

    def test_two_word_county(self):
        assert _county_to_url_name("santa clara") == "Santa_Clara"
        assert _county_to_url_name("contra costa") == "Contra_Costa"

    def test_hyphenated(self):
        assert _county_to_url_name("san-joaquin") == "San_Joaquin"

    def test_underscored(self):
        assert _county_to_url_name("santa_clara") == "Santa_Clara"


# ==================== Detection ====================


class TestDetectClarityElections:
    """Test Clarity Elections detection probing."""

    def test_detect_known_county_no_probe(self):
        """Registered counties return immediately without HTTP probe."""
        result = detect_clarity_elections("santa clara", "CA")
        assert result is not None
        assert result["county"] == "santa clara"
        assert result["url_name"] == "Santa_Clara"
        assert result["state"] == "CA"

    def test_detect_skips_civera_preferred(self):
        """Counties where Civera is preferred should not return Clarity."""
        result = detect_clarity_elections("marin", "CA")
        assert result is None

    @patch("civicos_extraction.clients.clarity_elections.requests.get")
    def test_detect_unknown_county_probes(self, mock_get):
        """Unknown counties are probed dynamically via GET."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.content = b"x" * 2000  # Must exceed 1000-byte threshold
        mock_get.return_value = mock_resp
        result = detect_clarity_elections("san diego", "CA")
        assert result is not None
        assert result["url_name"] == "San_Diego"
        mock_get.assert_called_once()

    @patch("civicos_extraction.clients.clarity_elections.requests.get")
    def test_detect_unknown_county_not_found(self, mock_get):
        mock_resp = MagicMock(status_code=404)
        mock_resp.content = b""
        mock_get.return_value = mock_resp
        result = detect_clarity_elections("san diego", "CA")
        assert result is None

    @patch("civicos_extraction.clients.clarity_elections.requests.get")
    def test_detect_network_error(self, mock_get):
        """Network errors during probe return None."""
        import requests
        mock_get.side_effect = requests.RequestException("timeout")
        result = detect_clarity_elections("san diego", "CA")
        assert result is None

    def test_detect_non_ca_registered_county(self):
        """Non-CA registered county returns immediately."""
        result = detect_clarity_elections("travis", "TX")
        assert result is not None
        assert result["county"] == "travis"
        assert result["state"] == "TX"
        assert result["url_name"] == "Travis"


# ==================== Client ====================


class TestClarityElectionsClient:
    """Test ClarityElectionsClient protocol implementation."""

    def test_properties(self):
        client = ClarityElectionsClient(
            jurisdiction_id="city-cupertino",
            state="CA",
            county="santa clara",
        )
        assert client.platform_name == "clarity_elections"
        assert client.source_id == "clarity-santa-clara"
        assert client.source_type == "clarity_elections"
        assert client.url_name == "Santa_Clara"

    def test_custom_url_name(self):
        client = ClarityElectionsClient(
            jurisdiction_id="city-test",
            state="CA",
            county="test",
            url_name="Custom_Name",
        )
        assert client.url_name == "Custom_Name"

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_health_available(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.head.return_value = MagicMock(status_code=200)
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "butte")
        health = client.health()
        assert health.is_available is True
        assert health.source_type == "clarity_elections"
        assert not health.errors

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_health_unavailable(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.head.return_value = MagicMock(status_code=404)
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "butte")
        health = client.health()
        assert health.is_available is False
        assert len(health.errors) == 1

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_validate_valid(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.head.return_value = MagicMock(status_code=200)
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "butte")
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_validate_unreachable(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.head.return_value = MagicMock(status_code=503)
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "butte")
        result = client.validate()
        assert result.is_valid is False
        assert not result.api_reachable

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_get_current_version(self, mock_session_cls):
        mock_session = MagicMock()
        mock_resp = MagicMock(status_code=200, text="367736\n")
        mock_session.get.return_value = mock_resp
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "santa clara")
        ver = client.get_current_version("125819")
        assert ver == "367736"

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_get_current_version_404(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(status_code=404)
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "santa clara")
        ver = client.get_current_version("999999")
        assert ver is None

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_discover_from_registry(self, mock_session_cls):
        """discover_elections() returns IDs from the static registry."""
        mock_session = MagicMock()
        # Landing page scrape returns nothing (SPA)
        mock_session.get.return_value = MagicMock(status_code=200, text="<html></html>")
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "santa clara")
        elections = client.discover_elections()
        assert len(elections) >= 1
        ids = [e["election_id"] for e in elections]
        assert "125819" in ids

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_discover_deduplicates(self, mock_session_cls):
        """Registry IDs and scraped IDs are deduplicated."""
        mock_session = MagicMock()
        # Simulate scrape finding the same ID that's in the registry
        html = '<a href="/CA/Santa_Clara/125819/">Election</a>'
        mock_session.get.return_value = MagicMock(status_code=200, text=html)
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "santa clara")
        elections = client.discover_elections()
        ids = [e["election_id"] for e in elections]
        # Should appear only once despite being in both registry and HTML
        assert ids.count("125819") == 1

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_discover_empty_registry_falls_back_to_scrape(self, mock_session_cls):
        """Counties not in registry still discover via scrape."""
        mock_session = MagicMock()
        html = '<a href="/CA/San_Diego/99999/">Election</a>'
        mock_session.get.return_value = MagicMock(status_code=200, text=html)
        mock_session_cls.return_value = mock_session

        # san diego is not in the registry
        client = ClarityElectionsClient("city-test", "CA", "san diego")
        elections = client.discover_elections()
        assert len(elections) == 1
        assert elections[0]["election_id"] == "99999"

    @patch("civicos_extraction.clients.clarity_elections.requests.Session")
    def test_discover_scrape_failure_still_returns_registry(self, mock_session_cls):
        """Network failure on scrape doesn't lose registry IDs."""
        import requests as req
        mock_session = MagicMock()
        mock_session.get.side_effect = req.RequestException("timeout")
        mock_session_cls.return_value = mock_session

        client = ClarityElectionsClient("city-test", "CA", "santa clara")
        elections = client.discover_elections()
        assert len(elections) >= 1
        assert elections[0]["election_id"] == "125819"


# ==================== Mappers ====================


class TestInferElectionType:
    def test_general(self):
        assert _infer_election_type("November 5, 2024 General Election") == "general"

    def test_primary(self):
        assert _infer_election_type("March 5, 2024 Presidential Primary") == "primary"

    def test_runoff(self):
        assert _infer_election_type("E145 December 30, 2025 Runoff") == "runoff"

    def test_special(self):
        assert _infer_election_type("Special Election April 2025") == "special"

    def test_recall(self):
        assert _infer_election_type("Recall Election") == "recall"


class TestInferElectionDate:
    def test_month_day_year(self):
        assert _infer_election_date("November 5, 2024 General") == "2024-11-05"

    def test_month_day_year_no_comma(self):
        assert _infer_election_date("December 30 2025 Runoff") == "2025-12-30"

    def test_slash_format(self):
        assert _infer_election_date("12/17/2025") == "2025-12-17"

    def test_no_date(self):
        assert _infer_election_date("Unknown Election") is None

    def test_prefixed(self):
        assert _infer_election_date("E145 December 30, 2025 Runoff") == "2025-12-30"


class TestClarityResultsToElection:
    def test_basic_mapping(self):
        result = clarity_results_to_election(
            "125819", "November 5, 2024 General Election",
            "santa clara", "CA", "Santa_Clara",
        )
        assert result["id"] == "clarity-santa-clara-125819"
        assert result["name"] == "November 5, 2024 General Election"
        assert result["election_date"] == "2024-11-05"
        assert result["election_type"] == "general"
        assert result["source"] == "clarity_elections"
        assert "Santa_Clara/125819" in result["source_url"]

    def test_explicit_date_overrides_inferred(self):
        result = clarity_results_to_election(
            "100", "Some Election", "butte", "CA", "Butte",
            election_date="2025-06-01",
        )
        assert result["election_date"] == "2025-06-01"


class TestClarityContestToStorage:
    """Test contest mapping from Clarity JSON to ContestDict."""

    def test_race_contest(self):
        contest = {
            "CT": "City Council Member",
            "IQ": False,
            "V": [
                {"CH": "Jane Doe", "TOT": 5000, "PE": "55.5"},
                {"CH": "John Smith", "TOT": 4000, "PE": "44.5"},
            ],
        }
        result = clarity_contest_to_storage(contest, "santa clara", "125819")
        assert result["title"] == "City Council Member"
        assert len(result["candidates"]) == 2
        assert result["candidates"][0]["name"] == "Jane Doe"
        assert result["candidates"][0]["votes_received"] == 5000
        assert result["candidates"][0]["vote_percentage"] == 55.5
        assert result["candidates"][0]["is_winner"] is True
        assert result["candidates"][1]["is_winner"] is False
        assert result["ballot_measure"] is None
        assert result["number_elected"] == 1

    def test_ballot_measure(self):
        contest = {
            "CT": "Measure A: School Bond",
            "IQ": True,
            "V": [
                {"CH": "Yes", "TOT": 6000, "PE": "60.0"},
                {"CH": "No", "TOT": 4000, "PE": "40.0"},
            ],
        }
        result = clarity_contest_to_storage(contest, "ventura", "100")
        assert result["contest_type"] == "local_measure"
        assert result["number_elected"] == 0
        assert result["ballot_measure"] is not None
        assert result["ballot_measure"]["passed"] is True
        assert result["ballot_measure"]["yes_votes"] == 6000
        assert result["ballot_measure"]["no_votes"] == 4000

    def test_string_is_question(self):
        """IQ can be a string "true" in some Clarity versions."""
        contest = {"CT": "Measure B", "IQ": "true", "V": []}
        result = clarity_contest_to_storage(contest, "butte", "100")
        assert result["contest_type"] == "local_measure"

    def test_alt_field_names(self):
        """Handle alternate field names (N instead of CT, etc.)."""
        contest = {
            "N": "Mayor",
            "V": [{"N": "Alice", "totalVotes": "1,234", "P": "100.0"}],
        }
        result = clarity_contest_to_storage(contest, "shasta", "200")
        assert result["title"] == "Mayor"
        assert result["candidates"][0]["name"] == "Alice"
        assert result["candidates"][0]["votes_received"] == 1234

    def test_no_candidates(self):
        contest = {"CT": "Empty Contest"}
        result = clarity_contest_to_storage(contest, "merced", "300")
        assert result["candidates"] == []

    def test_contest_ids_are_unique(self):
        c1 = clarity_contest_to_storage(
            {"CT": "Mayor", "V": []}, "butte", "100",
        )
        c2 = clarity_contest_to_storage(
            {"CT": "Mayor", "V": []}, "butte", "200",
        )
        assert c1["id"] != c2["id"]

    def test_candidate_id_collision_resistance(self):
        """Two candidates with the same slugified name get distinct IDs."""
        contest = {
            "CT": "Board",
            "V": [
                {"CH": "Bob Smith", "TOT": 100},
                {"CH": "Bob Smith", "TOT": 200},  # duplicate name
            ],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        ids = [c["id"] for c in result["candidates"]]
        assert len(ids) == len(set(ids)), f"Duplicate candidate IDs: {ids}"

    def test_all_candidates_have_source(self):
        contest = {
            "CT": "Test",
            "V": [{"CH": "A", "TOT": 1}, {"CH": "B", "TOT": 2}],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        for cand in result["candidates"]:
            assert cand["source"] == "clarity_elections"


# ==================== Summary Parsing ====================


class TestParseSummaryContests:
    """Test flexible parsing of Clarity summary JSON variants."""

    def test_grouped_format(self):
        """Array of groups with "C" contests array."""
        summary = [
            {"C": [{"CT": "Mayor"}, {"CT": "Council"}]},
            {"C": [{"CT": "Measure A"}]},
        ]
        contests = parse_summary_contests(summary)
        assert len(contests) == 3
        assert contests[0]["CT"] == "Mayor"
        assert contests[1]["CT"] == "Council"
        assert contests[2]["CT"] == "Measure A"

    def test_flat_format(self):
        """Direct array of contest objects."""
        summary = [{"CT": "Mayor"}, {"CT": "Council"}]
        contests = parse_summary_contests(summary)
        assert len(contests) == 2
        assert contests[0]["CT"] == "Mayor"
        assert contests[1]["CT"] == "Council"

    def test_object_with_contests_key(self):
        summary = {"Contests": [{"CT": "Mayor"}]}
        contests = parse_summary_contests(summary)
        assert len(contests) == 1
        assert contests[0]["CT"] == "Mayor"

    def test_object_with_c_key(self):
        summary = {"C": [{"CT": "Mayor"}]}
        contests = parse_summary_contests(summary)
        assert len(contests) == 1
        assert contests[0]["CT"] == "Mayor"

    def test_empty_returns_empty(self):
        assert parse_summary_contests([]) == []
        assert parse_summary_contests({}) == []
        assert parse_summary_contests(None) == []

    def test_alt_field_name(self):
        """Contests with "N" field are recognized."""
        summary = [{"N": "Board Member"}]
        contests = parse_summary_contests(summary)
        assert len(contests) == 1
        assert contests[0]["N"] == "Board Member"

    def test_parallel_array_format(self):
        """Live Clarity ENR uses parallel arrays: C (string), CH, V, PCT."""
        summary = [
            {
                "C": "Assessor",
                "CH": ["Alice", "Bob", "Write-in"],
                "V": [143029, 76481, 0],
                "PCT": [65.15, 34.85, 0],
                "P": ["", "", ""],
                "W": [0, 0, 0],
            },
            {
                "C": "Mayor",
                "CH": ["Carol", "Dave"],
                "V": [5000, 4000],
                "PCT": [55.5, 44.5],
                "P": ["", ""],
                "W": [0, 0],
            },
        ]
        contests = parse_summary_contests(summary)
        assert len(contests) == 2
        assert contests[0]["C"] == "Assessor"
        assert contests[1]["C"] == "Mayor"


# ==================== Live Parallel-Array Format ====================


class TestParallelArrayFormat:
    """Tests for the live Clarity ENR parallel-array JSON format."""

    def test_detection_positive(self):
        contest = {
            "C": "Assessor",
            "CH": ["Alice", "Bob"],
            "V": [5000, 4000],
        }
        assert _is_parallel_array_format(contest) is True

    def test_detection_negative_nested(self):
        """Nested-object format should not trigger parallel detection."""
        contest = {
            "CT": "Mayor",
            "V": [{"CH": "Alice", "TOT": 5000}],
        }
        assert _is_parallel_array_format(contest) is False

    def test_detection_negative_empty(self):
        contest = {"CT": "Mayor"}
        assert _is_parallel_array_format(contest) is False

    def test_contest_mapping(self):
        """Full parallel-array contest maps correctly to storage format."""
        contest = {
            "C": "Assessor",
            "CH": ["Neysa Fligor", "Rishi Kumar", "Write-in"],
            "V": [143029, 76481, 0],
            "PCT": [65.1583, 34.8417, 0],
            "P": ["", "", ""],
            "W": [0, 0, 0],
            "T": 219510,
        }
        result = clarity_contest_to_storage(contest, "santa clara", "125819")
        assert result["title"] == "Assessor"
        assert len(result["candidates"]) == 3
        assert result["candidates"][0]["name"] == "Neysa Fligor"
        assert result["candidates"][0]["votes_received"] == 143029
        assert result["candidates"][0]["vote_percentage"] == 65.1583
        assert result["candidates"][1]["name"] == "Rishi Kumar"
        assert result["candidates"][1]["votes_received"] == 76481
        # No W flags set, so winner is highest vote count
        assert result["candidates"][0]["is_winner"] is True
        assert result["candidates"][1]["is_winner"] is False
        assert result["candidates"][2]["is_winner"] is False

    def test_winner_from_w_flags(self):
        """W array flags should be used for winner detection when present."""
        contest = {
            "C": "Mayor",
            "CH": ["Alice", "Bob"],
            "V": [5000, 4000],
            "PCT": [55.5, 44.5],
            "W": [1, 0],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        assert result["candidates"][0]["is_winner"] is True
        assert result["candidates"][1]["is_winner"] is False

    def test_empty_party_becomes_none(self):
        contest = {
            "C": "Council",
            "CH": ["Alice"],
            "V": [1000],
            "P": [""],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        assert result["candidates"][0]["party"] is None

    def test_party_preserved_when_set(self):
        contest = {
            "C": "Governor",
            "CH": ["Alice", "Bob"],
            "V": [5000, 4000],
            "P": ["DEM", "REP"],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        assert result["candidates"][0]["party"] == "DEM"
        assert result["candidates"][1]["party"] == "REP"

    def test_ballot_measure_parallel(self):
        """Ballot measures in parallel format with IQ flag."""
        contest = {
            "C": "Measure A: School Bond",
            "IQ": True,
            "CH": ["Yes", "No"],
            "V": [6000, 4000],
            "PCT": [60.0, 40.0],
            "W": [1, 0],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        assert result["contest_type"] == "local_measure"
        assert result["ballot_measure"] is not None
        assert result["ballot_measure"]["passed"] is True
        assert result["ballot_measure"]["yes_votes"] == 6000
        assert result["ballot_measure"]["no_votes"] == 4000

    def test_ballot_measure_auto_detected_from_yes_no(self):
        """Live ENR has no IQ flag — detect from YES/NO candidates."""
        contest = {
            "C": "PROP. 2 - AUTHORIZES BONDS FOR PUBLIC SCHOOL AND COMMUNITY COLLEGE FACILITIES",
            "CH": ["YES", "NO"],
            "V": [211275, 165402],
            "PCT": [56.09, 43.91],
            "W": [0, 0],
        }
        result = clarity_contest_to_storage(contest, "ventura", "122837")
        assert result["ballot_measure"] is not None
        assert result["ballot_measure"]["passed"] is True
        assert result["ballot_measure"]["yes_votes"] == 211275
        assert result["ballot_measure"]["no_votes"] == 165402
        assert result["number_elected"] == 0

    def test_ids_unique_across_candidates(self):
        contest = {
            "C": "Board",
            "CH": ["Bob Smith", "Bob Smith"],
            "V": [100, 200],
        }
        result = clarity_contest_to_storage(contest, "test", "100")
        ids = [c["id"] for c in result["candidates"]]
        assert len(ids) == len(set(ids))

    def test_full_live_santa_clara_format(self):
        """Exact structure from live Santa Clara Dec 2025 runoff."""
        contest = {
            "CATKEY": "C_0",
            "CAT": "Results",
            "C": "Assessor",
            "K": "1",
            "AggID": None,
            "regvoters": 0,
            "BCxContest": 0,
            "VF": 1,
            "TP": 579,
            "PR": 495,
            "TV": 0,
            "BC": 0,
            "RC": 0,
            "RO": 0,
            "CH": ["Neysa Fligor", "Rishi Kumar", "Write-in"],
            "CHAggId": None,
            "P": ["", "", ""],
            "PCT": [65.1583071386269, 34.8416928613731, 0],
            "V": [143029, 76481, 0],
            "T": 219510,
            "W": [0, 0, 0],
            "CRC": [0, 0, 0],
            "CRO": [0, 0, 0],
            "IsCumulative": None,
            "CumulativeVotes": None,
            "CumulativeChoices": None,
            "CumulativePercentages": None,
            "IsContestNoChoice": 0,
            "IsRCV": False,
            "RCVAwaitingResults": False,
        }
        result = clarity_contest_to_storage(contest, "santa-clara", "125819")
        assert result["title"] == "Assessor"
        assert len(result["candidates"]) == 3
        assert result["candidates"][0]["name"] == "Neysa Fligor"
        assert result["candidates"][0]["votes_received"] == 143029
        assert result["candidates"][0]["vote_percentage"] == pytest.approx(65.158, abs=0.01)
        assert result["candidates"][1]["votes_received"] == 76481
        # Write-in has 0 votes
        assert result["candidates"][2]["votes_received"] == 0
        assert result["candidates"][2]["name"] == "Write-in"
        # Winner by vote count (W flags all 0)
        assert result["candidates"][0]["is_winner"] is True
        assert result["id"] == "clarity-santa-clara-125819-assessor"
        assert result["ballot_measure"] is None


class TestFullPipelineParallelFormat:
    """Test extraction pipeline with live parallel-array format."""

    def _make_client(self):
        return ClarityElectionsClient(
            jurisdiction_id="city-cupertino",
            state="CA",
            county="santa clara",
            url_name="Santa_Clara",
        )

    @patch.object(ClarityElectionsClient, "get_election_settings")
    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_pipeline_with_parallel_format(self, mock_discover, mock_summary, mock_settings):
        """Full pipeline works end-to-end with live parallel-array data."""
        mock_discover.return_value = [
            {"election_id": "125819", "name": "December 30, 2025 Runoff"},
        ]
        mock_summary.return_value = [
            {
                "C": "Assessor",
                "CH": ["Neysa Fligor", "Rishi Kumar", "Write-in"],
                "V": [143029, 76481, 0],
                "PCT": [65.15, 34.85, 0],
                "P": ["", "", ""],
                "W": [0, 0, 0],
                "T": 219510,
            },
        ]
        mock_settings.return_value = None

        mock_storage = MagicMock()
        mock_storage.store_elections.return_value = 1
        mock_storage.store_election_contests.return_value = 1

        client = self._make_client()
        counts = extract_clarity_results_to_storage(
            client, mock_storage, "city-cupertino", "santa clara", "CA",
        )

        assert counts["elections"] == 1
        assert counts["contests"] == 1
        assert counts["candidates"] == 3

        # Verify contest was mapped from parallel format
        contests_call = mock_storage.store_election_contests.call_args
        contests = contests_call[0][1]
        assert len(contests) == 1
        assert contests[0]["title"] == "Assessor"
        assert len(contests[0]["candidates"]) == 3
        assert contests[0]["candidates"][0]["name"] == "Neysa Fligor"


# ==================== Extraction ====================


class TestExtractClarityResultsToStorage:
    """Test the full extraction pipeline with mocked HTTP and storage."""

    def _make_client(self):
        return ClarityElectionsClient(
            jurisdiction_id="city-cupertino",
            state="CA",
            county="santa clara",
            url_name="Santa_Clara",
        )

    @patch.object(ClarityElectionsClient, "get_election_settings")
    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_full_pipeline(self, mock_discover, mock_summary, mock_settings):
        mock_discover.return_value = [
            {"election_id": "125819", "name": "November 5 2024 General"},
        ]
        mock_summary.return_value = [
            {
                "EL": "November 5, 2024 General Election",
                "C": [
                    {
                        "CT": "City Council",
                        "IQ": False,
                        "V": [
                            {"CH": "Alice", "TOT": 3000, "PE": "60.0"},
                            {"CH": "Bob", "TOT": 2000, "PE": "40.0"},
                        ],
                    },
                    {
                        "CT": "Measure Z: Parks Bond",
                        "IQ": True,
                        "V": [
                            {"CH": "Yes", "TOT": 4000, "PE": "66.7"},
                            {"CH": "No", "TOT": 2000, "PE": "33.3"},
                        ],
                    },
                ],
            },
        ]
        mock_settings.return_value = None  # No settings available

        mock_storage = MagicMock()
        mock_storage.store_elections.return_value = 1
        mock_storage.store_election_contests.return_value = 2

        client = self._make_client()
        counts = extract_clarity_results_to_storage(
            client, mock_storage, "city-cupertino", "santa clara", "CA",
        )

        assert counts["elections"] == 1
        assert counts["contests"] == 2
        assert counts["candidates"] == 4

        mock_storage.store_elections.assert_called_once()
        mock_storage.store_election_contests.assert_called_once()

        # Verify the election dict
        election_call = mock_storage.store_elections.call_args
        election = election_call[0][1][0]
        assert election["source"] == "clarity_elections"
        assert election["name"] == "November 5, 2024 General Election"

        # Verify contest dicts
        contests_call = mock_storage.store_election_contests.call_args
        contests = contests_call[0][1]
        assert len(contests) == 2
        assert contests[0]["title"] == "City Council"
        assert contests[1]["contest_type"] == "local_measure"

    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_no_elections_found(self, mock_discover):
        mock_discover.return_value = []
        mock_storage = MagicMock()

        client = self._make_client()
        counts = extract_clarity_results_to_storage(
            client, mock_storage, "city-test", "santa clara",
        )

        assert counts["elections"] == 0
        mock_storage.store_elections.assert_not_called()

    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_purged_election_skipped(self, mock_discover, mock_summary):
        """Elections with no summary (purged) are gracefully skipped."""
        mock_discover.return_value = [
            {"election_id": "99999", "name": "Old Election"},
        ]
        mock_summary.return_value = None
        mock_storage = MagicMock()

        client = self._make_client()
        counts = extract_clarity_results_to_storage(
            client, mock_storage, "city-test", "santa clara",
        )

        assert counts["elections"] == 0
        mock_storage.store_elections.assert_not_called()

    @patch.object(ClarityElectionsClient, "get_election_settings")
    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_archive_on_fetch(self, mock_discover, mock_summary, mock_settings):
        """When archive_blob is provided, raw JSON is archived before parsing."""
        mock_discover.return_value = [
            {"election_id": "125819", "name": "Test Election"},
        ]
        summary_data = [{"C": "Mayor", "CH": ["Alice"], "V": [1000], "PCT": [100.0]}]
        mock_summary.return_value = summary_data
        mock_settings.return_value = None

        mock_storage = MagicMock()
        mock_storage.store_elections.return_value = 1
        mock_storage.store_election_contests.return_value = 1

        mock_blob = MagicMock()

        client = self._make_client()
        counts = extract_clarity_results_to_storage(
            client, mock_storage, "city-cupertino", "santa clara", "CA",
            archive_blob=mock_blob,
        )

        assert counts["elections"] == 1
        mock_blob.upload.assert_called_once()
        call_args = mock_blob.upload.call_args
        assert "clarity-elections/CA/Santa_Clara/125819/summary.json" == call_args[1]["key"]
        assert call_args[1]["content_type"] == "application/json"

    @patch.object(ClarityElectionsClient, "get_election_settings")
    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_archive_failure_does_not_block_extraction(self, mock_discover, mock_summary, mock_settings):
        """Archive failure is logged but does not prevent data extraction."""
        mock_discover.return_value = [
            {"election_id": "125819", "name": "Test Election"},
        ]
        mock_summary.return_value = [{"C": "Mayor", "CH": ["Alice"], "V": [1000], "PCT": [100.0]}]
        mock_settings.return_value = None

        mock_storage = MagicMock()
        mock_storage.store_elections.return_value = 1
        mock_storage.store_election_contests.return_value = 1

        mock_blob = MagicMock()
        mock_blob.upload.side_effect = RuntimeError("R2 down")

        client = self._make_client()
        counts = extract_clarity_results_to_storage(
            client, mock_storage, "city-cupertino", "santa clara", "CA",
            archive_blob=mock_blob,
        )

        # Extraction still succeeds despite archive failure
        assert counts["elections"] == 1
        assert counts["contests"] == 1


# ==================== Fetch Handler Dispatch ====================


class TestFetchHandlerRegistration:
    """Test that clarity_elections is registered in _FETCH_HANDLERS."""

    def test_clarity_handler_registered(self):
        from civicos_extraction.election_fetch import _FETCH_HANDLERS
        assert "clarity_elections" in _FETCH_HANDLERS

    def test_supported_sources_includes_clarity(self):
        from civicos_extraction.clients import SUPPORTED_ELECTION_SOURCES
        assert "clarity_elections" in SUPPORTED_ELECTION_SOURCES


class TestFetchClarity:
    """Test the _fetch_clarity handler."""

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    def test_dispatches_clarity(self, mock_backend_cls, mock_officials):
        from civicos_extraction.election_fetch import (
            _FETCH_HANDLERS,
            fetch_elections_for_jurisdiction,
        )

        mock_handler = MagicMock(return_value={"status": "completed", "contests_stored": 5})
        mock_officials.return_value = {"status": "skipped"}

        sources = {"clarity_elections": {"county": "santa clara", "state": "CA", "url_name": "Santa_Clara"}}
        with patch.dict(_FETCH_HANDLERS, {"clarity_elections": mock_handler}):
            result = fetch_elections_for_jurisdiction(
                "city-cupertino", sources, database_url="postgresql://test",
            )

        mock_handler.assert_called_once()
        assert result["clarity_elections"]["status"] == "completed"


# ==================== CA Provider Integration ====================


class TestCaliforniaProviderClarity:
    """Test CaliforniaElectionProvider Clarity integration."""

    @pytest.fixture(autouse=True)
    def mock_civera_validation(self, monkeypatch):
        monkeypatch.setattr(
            "civicos_extraction.onboard._validate_civera_division_filter",
            lambda *args, **kwargs: True,
        )

    @pytest.fixture(autouse=True)
    def clear_provider_cache(self):
        from civicos_extraction.providers import _PROVIDERS
        _PROVIDERS.clear()
        yield
        _PROVIDERS.clear()

    def test_clarity_county_gets_clarity_source(self):
        from civicos_extraction.providers.california import CaliforniaElectionProvider
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-cupertino", "santa clara")
        assert "clarity_elections" in result
        assert result["clarity_elections"]["county"] == "santa clara"
        assert result["clarity_elections"]["state"] == "CA"
        assert result["clarity_elections"]["url_name"] == "Santa_Clara"

    def test_clarity_county_sos_no_breakdown(self):
        """Clarity counties get county_breakdown=False since Clarity is the local source."""
        from civicos_extraction.providers.california import CaliforniaElectionProvider
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-cupertino", "santa clara")
        assert result["ca_sos_results"]["county_breakdown"] is False

    def test_civera_county_no_clarity(self):
        """Civera counties should NOT get a Clarity source (Civera is preferred)."""
        from civicos_extraction.providers.california import CaliforniaElectionProvider
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-san-rafael", "marin")
        assert "clarity_elections" not in result
        assert "civera_election_stats" in result

    def test_no_source_county_still_gets_sos_breakdown(self):
        """Counties with neither Civera nor Clarity get SOS county_breakdown=True."""
        from civicos_extraction.providers.california import CaliforniaElectionProvider
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-oakland", "alameda")
        assert "clarity_elections" not in result
        assert "civera_election_stats" not in result
        assert result["ca_sos_results"]["county_breakdown"] is True

    def test_all_seven_net_new_counties(self):
        """All 7 net-new Clarity counties produce clarity_elections source."""
        from civicos_extraction.providers.california import CaliforniaElectionProvider
        provider = CaliforniaElectionProvider()
        net_new = ["butte", "contra costa", "madera", "merced", "santa clara", "shasta", "ventura"]
        for county in net_new:
            jid = f"city-test-{county.replace(' ', '-')}"
            result = provider.detect_election_sources(jid, county)
            assert "clarity_elections" in result, f"Missing clarity_elections for {county}"
            assert result["clarity_elections"]["county"] == county


# ==================== Default Provider Clarity Integration ====================


class TestDefaultProviderClarity:
    """Test DefaultElectionProvider Clarity integration for non-CA states."""

    @pytest.fixture(autouse=True)
    def clear_provider_cache(self):
        from civicos_extraction.providers import _PROVIDERS
        _PROVIDERS.clear()
        yield
        _PROVIDERS.clear()

    def test_registered_county_gets_clarity_source(self):
        """Non-CA county in registry gets clarity_elections source."""
        from civicos_extraction.providers.default import DefaultElectionProvider
        provider = DefaultElectionProvider("TX")
        result = provider.detect_election_sources("city-austin", "travis")
        assert "clarity_elections" in result
        assert result["clarity_elections"]["county"] == "travis"
        assert result["clarity_elections"]["state"] == "TX"
        assert result["clarity_elections"]["url_name"] == "Travis"

    def test_registered_county_sos_no_breakdown(self):
        """Clarity counties get county_breakdown=False since Clarity provides local data."""
        from civicos_extraction.providers.default import DefaultElectionProvider
        provider = DefaultElectionProvider("TX")
        result = provider.detect_election_sources("city-austin", "travis")
        assert result["tx_sos_results"]["county_breakdown"] is False

    def test_unregistered_county_no_clarity(self, monkeypatch):
        """Counties not in registry and failing probe get no Clarity source."""
        monkeypatch.setattr(
            "civicos_extraction.clients.clarity_elections.detect_clarity_elections",
            lambda county, state, **kwargs: None,
        )
        from civicos_extraction.providers.default import DefaultElectionProvider
        provider = DefaultElectionProvider("WY")
        result = provider.detect_election_sources("city-cheyenne", "laramie")
        assert "clarity_elections" not in result
        assert result["wy_sos_results"]["county_breakdown"] is True

    def test_multi_state_registry_coverage(self):
        """Verify registry has entries for multiple US states."""
        from civicos_extraction.clients.clarity_elections import CLARITY_INSTANCES
        states_with_clarity = [s for s in CLARITY_INSTANCES if CLARITY_INSTANCES[s]]
        assert len(states_with_clarity) >= 10, (
            f"Expected 10+ states in registry, got {len(states_with_clarity)}: "
            f"{sorted(states_with_clarity)}"
        )

    def test_non_ca_states_in_registry(self):
        """Non-CA states should be present in the Clarity registry."""
        from civicos_extraction.clients.clarity_elections import CLARITY_INSTANCES
        expected_states = ["TX", "FL", "GA", "OH", "CO", "SC", "OK", "AL"]
        for state in expected_states:
            assert state in CLARITY_INSTANCES, f"Missing {state} from registry"
            assert len(CLARITY_INSTANCES[state]) > 0, f"Empty {state} in registry"

    def test_texas_counties_detected(self):
        """TX counties with Clarity produce proper election sources."""
        from civicos_extraction.providers.default import DefaultElectionProvider
        provider = DefaultElectionProvider("TX")
        for county, url_name in [
            ("travis", "Travis"),
            ("denton", "Denton"),
            ("el paso", "El_Paso"),
            ("fort bend", "Fort_Bend"),
        ]:
            result = provider.detect_election_sources(f"city-test-{county}", county)
            assert "clarity_elections" in result, f"Missing clarity for TX/{county}"
            assert result["clarity_elections"]["url_name"] == url_name

    def test_florida_counties_detected(self):
        """FL counties with Clarity produce proper election sources."""
        from civicos_extraction.providers.default import DefaultElectionProvider
        provider = DefaultElectionProvider("FL")
        for county in ["duval", "hillsborough", "orange", "palm beach"]:
            result = provider.detect_election_sources(f"city-test-{county}", county)
            assert "clarity_elections" in result, f"Missing clarity for FL/{county}"

    def test_dynamic_probe_fallback(self, monkeypatch):
        """For unregistered counties, detect_clarity_elections probes dynamically."""
        monkeypatch.setattr(
            "civicos_extraction.clients.clarity_elections.detect_clarity_elections",
            lambda county, state, **kwargs: {
                "county": county.lower(),
                "state": state,
                "url_name": county.title(),
            },
        )
        from civicos_extraction.providers.default import DefaultElectionProvider
        provider = DefaultElectionProvider("WA")
        result = provider.detect_election_sources("city-seattle", "king")
        assert "clarity_elections" in result
        assert result["clarity_elections"]["county"] == "king"

    def test_state_key_format(self):
        """SOS source key follows {state}_sos_results format."""
        from civicos_extraction.providers.default import DefaultElectionProvider
        for state in ["TX", "FL", "GA", "OH"]:
            provider = DefaultElectionProvider(state)
            result = provider.detect_election_sources("city-test", "some_county")
            expected_key = f"{state.lower()}_sos_results"
            assert expected_key in result


# ==================== Multi-State Data Quality ====================


class TestMultiStateParallelArrayParsing:
    """Test that non-CA Clarity data parses correctly through existing pipeline."""

    def test_tx_format_parallel_arrays(self):
        """TX Clarity data uses same parallel-array format as CA."""
        from civicos_extraction.clients.clarity_elections import (
            parse_summary_contests,
            clarity_contest_to_storage,
        )
        # Simulated TX-style contest
        summary = [{
            "C": "DEM United States Senator",
            "CH": ["Alice Smith", "Bob Jones"],
            "V": [15000, 12000],
            "PCT": [55.56, 44.44],
            "P": ["DEM", "DEM"],
            "W": ["X", ""],
            "T": 27000,
        }]
        contests = parse_summary_contests(summary)
        assert len(contests) == 1
        mapped = clarity_contest_to_storage(contests[0], "travis", "125931")
        assert mapped["title"] == "DEM United States Senator"
        assert mapped["contest_type"] == "federal_senate"
        assert len(mapped["candidates"]) == 2
        assert mapped["candidates"][0]["name"] == "Alice Smith"
        assert mapped["candidates"][0]["is_winner"] is True

    def test_fl_format_with_ballot_measures(self):
        """FL Clarity data with ballot measures (YES/NO candidates)."""
        from civicos_extraction.clients.clarity_elections import (
            parse_summary_contests,
            clarity_contest_to_storage,
        )
        summary = [{
            "C": "Amendment 1 - Partisan School Board Elections",
            "CH": ["YES", "NO"],
            "V": [80000, 60000],
            "PCT": [57.14, 42.86],
            "P": ["", ""],
            "W": ["", ""],
            "T": 140000,
        }]
        contests = parse_summary_contests(summary)
        mapped = clarity_contest_to_storage(contests[0], "hillsborough", "43959")
        assert mapped["contest_type"] == "local_measure"
        assert mapped["ballot_measure"] is not None
        assert mapped["ballot_measure"]["yes_votes"] == 80000
        assert mapped["ballot_measure"]["no_votes"] == 60000


# ==================== Integration: Postgres End-to-End ====================


class TestClarityPostgresIntegration:
    """Integration test: full Clarity pipeline with mocked HTTP, real Postgres.

    Validates that the extraction pipeline correctly stores elections and
    contests through the real Postgres storage backend. HTTP is mocked
    to avoid depending on Clarity availability.
    """

    @pytest.fixture
    def postgres_backend(self):
        """Get real Postgres backend (skips if DATABASE_URL not set)."""
        import os
        from dotenv import load_dotenv

        load_dotenv()
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            pytest.skip("DATABASE_URL not set — skipping Postgres integration test")

        from civicos.storage.postgres_backend import PostgresBackend

        return PostgresBackend(db_url)

    @patch.object(ClarityElectionsClient, "get_election_settings")
    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_clarity_to_postgres_end_to_end(
        self, mock_discover, mock_summary, mock_settings, postgres_backend,
    ):
        """Full pipeline: Clarity → parse → store in real Postgres.

        Uses city-san-rafael (registered pilot) with fake election ID 999999
        to validate the storage wiring without affecting real data.
        """
        mock_discover.return_value = [
            {"election_id": "999999", "name": "Integration Test Election"},
        ]
        mock_summary.return_value = [
            {
                "C": "DEM United States Senator",
                "CH": ["Test Candidate A", "Test Candidate B"],
                "V": [15000, 12000],
                "PCT": [55.56, 44.44],
                "P": ["DEM", "DEM"],
                "W": ["X", ""],
                "T": 27000,
            },
            {
                "C": "City Proposition 1 - Parks Bond",
                "CH": ["YES", "NO"],
                "V": [8000, 6000],
                "PCT": [57.14, 42.86],
                "P": ["", ""],
                "W": ["", ""],
                "T": 14000,
            },
        ]
        mock_settings.return_value = {
            "ElectionName": "March 4, 2025 Primary Election",
            "ElectionDate": "03/04/2025",
        }

        client = ClarityElectionsClient(
            jurisdiction_id="city-san-rafael",
            state="CA",
            county="marin",
            url_name="Marin",
        )

        counts = extract_clarity_results_to_storage(
            client=client,
            storage=postgres_backend,
            jurisdiction_id="city-san-rafael",
            county_slug="marin",
            state="CA",
        )

        # Pipeline ran successfully
        assert counts["elections"] >= 1
        assert counts["contests"] >= 2
        assert counts["candidates"] >= 4
