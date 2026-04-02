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

    @patch("civicos_extraction.clients.clarity_elections.requests.head")
    def test_detect_known_county(self, mock_head):
        mock_head.return_value = MagicMock(status_code=200)
        result = detect_clarity_elections("santa clara", "CA")
        assert result is not None
        assert result["county"] == "santa clara"
        assert result["url_name"] == "Santa_Clara"
        assert result["state"] == "CA"

    @patch("civicos_extraction.clients.clarity_elections.requests.head")
    def test_detect_skips_civera_preferred(self, mock_head):
        """Counties where Civera is preferred should not return Clarity."""
        result = detect_clarity_elections("marin", "CA")
        assert result is None
        mock_head.assert_not_called()

    @patch("civicos_extraction.clients.clarity_elections.requests.head")
    def test_detect_unknown_county_probes(self, mock_head):
        """Unknown counties are probed dynamically."""
        mock_head.return_value = MagicMock(status_code=200)
        result = detect_clarity_elections("san diego", "CA")
        assert result is not None
        assert result["url_name"] == "San_Diego"
        mock_head.assert_called_once()

    @patch("civicos_extraction.clients.clarity_elections.requests.head")
    def test_detect_unknown_county_not_found(self, mock_head):
        mock_head.return_value = MagicMock(status_code=404)
        result = detect_clarity_elections("san diego", "CA")
        assert result is None

    @patch("civicos_extraction.clients.clarity_elections.requests.head")
    def test_detect_network_error(self, mock_head):
        import requests
        mock_head.side_effect = requests.RequestException("timeout")
        result = detect_clarity_elections("santa clara", "CA")
        assert result is None


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

    def test_flat_format(self):
        """Direct array of contest objects."""
        summary = [{"CT": "Mayor"}, {"CT": "Council"}]
        contests = parse_summary_contests(summary)
        assert len(contests) == 2

    def test_object_with_contests_key(self):
        summary = {"Contests": [{"CT": "Mayor"}]}
        contests = parse_summary_contests(summary)
        assert len(contests) == 1

    def test_object_with_c_key(self):
        summary = {"C": [{"CT": "Mayor"}]}
        contests = parse_summary_contests(summary)
        assert len(contests) == 1

    def test_empty_returns_empty(self):
        assert parse_summary_contests([]) == []
        assert parse_summary_contests({}) == []
        assert parse_summary_contests(None) == []

    def test_alt_field_name(self):
        """Contests with "N" field are recognized."""
        summary = [{"N": "Board Member"}]
        contests = parse_summary_contests(summary)
        assert len(contests) == 1


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

    @patch.object(ClarityElectionsClient, "get_summary")
    @patch.object(ClarityElectionsClient, "discover_elections")
    def test_full_pipeline(self, mock_discover, mock_summary):
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

        sources = {"clarity_elections": {"county": "santa clara", "url_name": "Santa_Clara"}}
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
