"""
Tests for the StateElectionProvider abstraction.

Validates the provider registry, CaliforniaElectionProvider, and
that unsupported states return empty results through the dispatcher.
"""

import pytest
from unittest.mock import patch

from civicos_extraction.providers import (
    StateElectionProvider,
    get_provider,
    _PROVIDERS,
)
from civicos_extraction.providers.california import CaliforniaElectionProvider
from civicos_extraction.providers.texas import TexasElectionProvider


# Auto-mock Civera validation (avoid network calls)
@pytest.fixture(autouse=True)
def mock_civera_validation(monkeypatch):
    monkeypatch.setattr(
        "civicos_extraction.onboard._validate_civera_division_filter",
        lambda *args, **kwargs: True,
    )


@pytest.fixture(autouse=True)
def clear_provider_cache():
    """Clear the provider registry between tests to avoid state leakage."""
    _PROVIDERS.clear()
    yield
    _PROVIDERS.clear()


# --- Provider Registry ---


class TestProviderRegistry:
    """Provider registry dispatches to the correct state provider."""

    def test_get_ca_provider(self):
        provider = get_provider("CA")
        assert provider is not None
        assert isinstance(provider, CaliforniaElectionProvider)
        assert provider.state_code == "CA"

    def test_get_ca_provider_case_insensitive(self):
        provider = get_provider("ca")
        assert provider is not None
        assert provider.state_code == "CA"

    def test_get_tx_provider(self):
        provider = get_provider("TX")
        assert provider is not None
        assert isinstance(provider, TexasElectionProvider)
        assert provider.state_code == "TX"

    def test_get_tx_provider_case_insensitive(self):
        provider = get_provider("tx")
        assert provider is not None
        assert provider.state_code == "TX"

    def test_unsupported_state_returns_none(self):
        assert get_provider("OR") is None
        assert get_provider("ZZ") is None

    def test_empty_state_returns_none(self):
        assert get_provider("") is None

    def test_provider_is_cached(self):
        p1 = get_provider("CA")
        p2 = get_provider("CA")
        assert p1 is p2

    def test_abc_not_instantiable(self):
        with pytest.raises(TypeError):
            StateElectionProvider()


# --- CaliforniaElectionProvider ---


class TestCaliforniaElectionProvider:
    """CA provider produces the same results as the original inline logic."""

    def test_marin_city(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-san-rafael", "marin")
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}
        assert result["marin_registrar_results"]["from_year"] == 2010
        assert result["marin_registrar_results"]["division_filter"] == "San Rafael"

    def test_marin_county(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("county-marin", "marin")
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}
        assert result["marin_registrar_results"]["division_filter"] == "Marin County"

    def test_non_civera_county(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-los-angeles", "los angeles")
        assert result["ca_sos_results"] == {"county": "los angeles", "county_breakdown": True}
        assert "marin_registrar_results" not in result
        assert "civera_election_stats" not in result

    def test_sonoma_gets_civera(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("county-sonoma", "sonoma")
        assert "ca_sos_results" in result
        assert "civera_election_stats" in result
        assert result["civera_election_stats"]["county_slug"] == "sonoma"

    def test_san_joaquin_gets_civera(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("county-san-joaquin", "san-joaquin")
        assert "ca_sos_results" in result
        assert "civera_election_stats" in result
        assert result["civera_election_stats"]["county_slug"] == "san-joaquin"
        assert result["civera_election_stats"]["graphql_url"] == (
            "https://electionstats.sjgov.org/api/graphql_pr"
        )

    def test_non_civera_gets_county_breakdown_flag(self):
        """Non-Civera counties get county_breakdown=True on SOS source."""
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-oakland", "alameda")
        assert result["ca_sos_results"]["county_breakdown"] is True
        assert "civera_election_stats" not in result

    def test_civera_county_has_county_breakdown_false(self):
        """Civera counties get explicit county_breakdown=False — Civera is primary."""
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("county-sonoma", "sonoma")
        assert result["ca_sos_results"]["county_breakdown"] is False

    def test_with_lat_lng_adds_districts(self):
        provider = CaliforniaElectionProvider()
        mock_districts = {"us-rep": [2], "state-senate": [2], "state-assembly": [12]}
        with patch("civicos_extraction.onboard.detect_districts", return_value=mock_districts):
            result = provider.detect_election_sources(
                "city-san-rafael", "marin", lat=37.97, lng=-122.53,
            )
        assert result["ca_sos_results"]["districts"] == mock_districts

    def test_without_lat_lng_no_districts(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-san-rafael", "marin")
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}

    def test_empty_county_no_civera(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-test", "")
        assert result["ca_sos_results"] == {"county": "", "county_breakdown": True}
        assert "marin_registrar_results" not in result


# --- TexasElectionProvider ---


class TestTexasElectionProvider:
    """TX provider returns tx_sos_results for all Texas jurisdictions."""

    def test_travis_county_city(self):
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("city-austin", "travis")
        assert result["tx_sos_results"] == {"county": "travis", "county_breakdown": True}

    def test_harris_county_city(self):
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("city-houston", "harris")
        assert result["tx_sos_results"] == {"county": "harris", "county_breakdown": True}

    def test_county_jurisdiction(self):
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("county-bexar", "bexar")
        assert result["tx_sos_results"] == {"county": "bexar", "county_breakdown": True}

    def test_empty_county(self):
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("city-test", "")
        assert result["tx_sos_results"] == {"county": "", "county_breakdown": True}

    def test_always_county_breakdown_true(self):
        """All TX counties use county_breakdown=True (no registrar APIs yet)."""
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("city-dallas", "dallas")
        assert result["tx_sos_results"]["county_breakdown"] is True

    def test_with_lat_lng_adds_districts(self):
        provider = TexasElectionProvider()
        mock_districts = {"us-rep": [21], "state-senate": [14], "state-assembly": [47]}
        with patch("civicos_extraction.onboard.detect_districts", return_value=mock_districts):
            result = provider.detect_election_sources(
                "city-austin", "travis", lat=30.27, lng=-97.74,
            )
        assert result["tx_sos_results"]["districts"] == mock_districts

    def test_without_lat_lng_no_districts(self):
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("city-austin", "travis")
        assert result["tx_sos_results"] == {"county": "travis", "county_breakdown": True}

    def test_no_ca_sources(self):
        """TX provider never returns CA-specific sources."""
        provider = TexasElectionProvider()
        result = provider.detect_election_sources("city-austin", "travis")
        assert "ca_sos_results" not in result
        assert "marin_registrar_results" not in result
        assert "civera_election_stats" not in result


# --- Dispatcher integration ---


class TestDispatcherIntegration:
    """The onboard.py dispatcher routes through providers correctly."""

    def test_ca_dispatches_to_provider(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-san-rafael", "CA", "Marin")
        assert "ca_sos_results" in result
        assert "marin_registrar_results" in result

    def test_tx_dispatches_to_provider(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-austin", "TX", "Travis")
        assert "tx_sos_results" in result
        assert result["tx_sos_results"]["county"] == "travis"

    def test_unsupported_state_returns_empty(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-portland", "OR", "Multnomah")
        assert result == {}

    def test_empty_state_returns_empty(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-test", "", "SomeCounty")
        assert result == {}

    def test_county_normalization_in_dispatcher(self):
        """County suffix stripping happens in dispatcher before reaching provider."""
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-mill-valley", "CA", "Marin County")
        assert result["ca_sos_results"]["county"] == "marin"
        assert "marin_registrar_results" in result
