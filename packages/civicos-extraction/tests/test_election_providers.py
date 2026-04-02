"""
Tests for the StateElectionProvider abstraction.

Validates the provider registry, CaliforniaElectionProvider,
DefaultElectionProvider, and dispatcher integration.
"""

import pytest
from unittest.mock import patch

from civicos_extraction.providers import (
    StateElectionProvider,
    get_provider,
    _PROVIDERS,
)
from civicos_extraction.providers.california import CaliforniaElectionProvider
from civicos_extraction.providers.default import DefaultElectionProvider


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
        assert isinstance(provider, DefaultElectionProvider)
        assert provider.state_code == "TX"

    def test_get_tx_provider_case_insensitive(self):
        provider = get_provider("tx")
        assert provider is not None
        assert provider.state_code == "TX"

    def test_get_fl_provider(self):
        provider = get_provider("FL")
        assert provider is not None
        assert isinstance(provider, DefaultElectionProvider)
        assert provider.state_code == "FL"

    def test_get_fl_provider_case_insensitive(self):
        provider = get_provider("fl")
        assert provider is not None
        assert provider.state_code == "FL"

    def test_get_ny_provider(self):
        """NY has a StateElectionConfig — auto-gets a DefaultElectionProvider."""
        provider = get_provider("NY")
        assert provider is not None
        assert isinstance(provider, DefaultElectionProvider)
        assert provider.state_code == "NY"

    def test_get_pa_provider(self):
        """PA has a StateElectionConfig — auto-gets a DefaultElectionProvider."""
        provider = get_provider("PA")
        assert provider is not None
        assert isinstance(provider, DefaultElectionProvider)
        assert provider.state_code == "PA"

    def test_get_il_provider(self):
        """IL has a StateElectionConfig — auto-gets a DefaultElectionProvider."""
        provider = get_provider("IL")
        assert provider is not None
        assert isinstance(provider, DefaultElectionProvider)
        assert provider.state_code == "IL"

    def test_unsupported_state_returns_none(self):
        """States without StateElectionConfig get no provider."""
        assert get_provider("GU") is None
        assert get_provider("ZZ") is None

    def test_empty_state_returns_none(self):
        assert get_provider("") is None

    def test_provider_is_cached(self):
        p1 = get_provider("CA")
        p2 = get_provider("CA")
        assert p1 is p2

    def test_default_provider_is_cached(self):
        p1 = get_provider("TX")
        p2 = get_provider("TX")
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
        assert result["civera_election_stats"]["county_slug"] == "marin"
        assert result["civera_election_stats"]["from_year"] == 2010
        assert result["civera_election_stats"]["division_filter"] == "San Rafael"

    def test_marin_county(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("county-marin", "marin")
        assert result["ca_sos_results"] == {"county": "marin", "county_breakdown": False}
        assert result["civera_election_stats"]["county_slug"] == "marin"
        assert result["civera_election_stats"]["division_filter"] == "Marin County"

    def test_non_civera_county(self):
        provider = CaliforniaElectionProvider()
        result = provider.detect_election_sources("city-los-angeles", "los angeles")
        assert result["ca_sos_results"] == {"county": "los angeles", "county_breakdown": True}
        assert "marin_registrar_results" not in result  # legacy key removed
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
        assert "marin_registrar_results" not in result  # legacy key removed


# --- DefaultElectionProvider (TX, FL, NY, PA, IL, etc.) ---


class TestDefaultElectionProvider:
    """DefaultElectionProvider works for any state with a StateElectionConfig."""

    def test_tx_source_key(self):
        provider = DefaultElectionProvider("TX")
        result = provider.detect_election_sources("city-austin", "travis")
        assert "tx_sos_results" in result
        assert result["tx_sos_results"]["county"] == "travis"
        # Travis has Clarity, so county_breakdown=False (Clarity provides local data)
        assert "clarity_elections" in result
        assert result["tx_sos_results"]["county_breakdown"] is False

    def test_fl_source_key(self):
        provider = DefaultElectionProvider("FL")
        result = provider.detect_election_sources("city-miami", "miami-dade")
        assert "fl_sos_results" in result
        assert result["fl_sos_results"]["county"] == "miami-dade"
        # Miami-Dade not in Clarity registry, gets county_breakdown=True
        assert result["fl_sos_results"]["county_breakdown"] is True

    def test_ny_source_key(self):
        provider = DefaultElectionProvider("NY")
        result = provider.detect_election_sources("city-new-york", "new york")
        assert "ny_sos_results" in result
        assert result["ny_sos_results"] == {"county": "new york", "county_breakdown": True}

    def test_pa_source_key(self):
        provider = DefaultElectionProvider("PA")
        result = provider.detect_election_sources("city-philadelphia", "philadelphia")
        assert "pa_sos_results" in result

    def test_il_source_key(self):
        provider = DefaultElectionProvider("IL")
        result = provider.detect_election_sources("city-chicago", "cook")
        assert "il_sos_results" in result

    def test_empty_county(self):
        provider = DefaultElectionProvider("TX")
        result = provider.detect_election_sources("city-test", "")
        assert result["tx_sos_results"] == {"county": "", "county_breakdown": True}

    def test_county_breakdown_depends_on_clarity(self):
        """Default provider sets county_breakdown based on Clarity availability."""
        # Hillsborough FL has Clarity → county_breakdown=False
        provider = DefaultElectionProvider("FL")
        result = provider.detect_election_sources("city-tampa", "hillsborough")
        assert "clarity_elections" in result
        assert result["fl_sos_results"]["county_breakdown"] is False

        # Unknown county without Clarity → county_breakdown=True
        result2 = provider.detect_election_sources("city-test", "unknown_county")
        assert "clarity_elections" not in result2
        assert result2["fl_sos_results"]["county_breakdown"] is True

    def test_with_lat_lng_adds_districts(self):
        provider = DefaultElectionProvider("TX")
        mock_districts = {"us-rep": [21], "state-senate": [14], "state-assembly": [47]}
        with patch("civicos_extraction.onboard.detect_districts", return_value=mock_districts):
            result = provider.detect_election_sources(
                "city-austin", "travis", lat=30.27, lng=-97.74,
            )
        assert result["tx_sos_results"]["districts"] == mock_districts

    def test_without_lat_lng_no_districts(self):
        provider = DefaultElectionProvider("FL")
        result = provider.detect_election_sources("city-miami", "miami-dade")
        assert result["fl_sos_results"] == {"county": "miami-dade", "county_breakdown": True}

    def test_no_ca_sources(self):
        """Default provider never returns CA-specific sources."""
        provider = DefaultElectionProvider("TX")
        result = provider.detect_election_sources("city-austin", "travis")
        assert "ca_sos_results" not in result
        assert "civera_election_stats" not in result

    def test_no_cross_state_sources(self):
        """FL provider doesn't return TX sources and vice versa."""
        fl_provider = DefaultElectionProvider("FL")
        fl_result = fl_provider.detect_election_sources("city-miami", "miami-dade")
        assert "tx_sos_results" not in fl_result

        tx_provider = DefaultElectionProvider("TX")
        tx_result = tx_provider.detect_election_sources("city-austin", "travis")
        assert "fl_sos_results" not in tx_result

    def test_state_code_uppercased(self):
        """State code is normalized to uppercase."""
        provider = DefaultElectionProvider("ny")
        assert provider.state_code == "NY"
        result = provider.detect_election_sources("city-buffalo", "erie")
        assert "ny_sos_results" in result


# --- Dispatcher integration ---


class TestDispatcherIntegration:
    """The onboard.py dispatcher routes through providers correctly."""

    def test_ca_dispatches_to_provider(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-san-rafael", "CA", "Marin")
        assert "ca_sos_results" in result
        assert "civera_election_stats" in result

    def test_tx_dispatches_to_provider(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-austin", "TX", "Travis")
        assert "tx_sos_results" in result
        assert result["tx_sos_results"]["county"] == "travis"

    def test_fl_dispatches_to_provider(self):
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-miami", "FL", "Miami-Dade")
        assert "fl_sos_results" in result
        assert result["fl_sos_results"]["county"] == "miami-dade"

    def test_ny_dispatches_to_provider(self):
        """NY auto-gets a DefaultElectionProvider via STATE_CONFIGS."""
        from civicos_extraction.onboard import detect_election_sources
        result = detect_election_sources("city-buffalo", "NY", "Erie")
        assert "ny_sos_results" in result
        assert result["ny_sos_results"]["county"] == "erie"

    def test_unsupported_state_returns_empty(self):
        """States without StateElectionConfig return empty dict."""
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
        assert "civera_election_stats" in result
