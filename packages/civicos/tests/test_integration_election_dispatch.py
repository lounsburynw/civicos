"""
Integration tests for election dispatch: config-driven provider selection in scheduled_election_refresh().

Validates that:
1. get_active_jurisdictions() loads state-california.json and other CA jurisdictions
2. election_sources config correctly maps to provider dispatch
3. The dispatch logic selects the right providers with correct parameters

These tests exercise the real config loading from data/extraction/*.json
and verify the dispatch conditions that scheduled_election_refresh() uses.

Run: pytest packages/civicos/tests/test_integration_election_dispatch.py -v --override-ini="addopts="
"""

import json

import pytest


def _load_active_jurisdictions():
    """Load jurisdictions using the real config loader."""
    from civicos_extraction.config import get_active_jurisdictions
    return get_active_jurisdictions()


class TestElectionConfigLoading:
    """Verify extraction configs are correctly loaded for election dispatch."""

    def test_state_california_loaded(self):
        """state-california.json is discovered by get_active_jurisdictions()."""
        jurisdictions = _load_active_jurisdictions()
        assert "state-california" in jurisdictions, (
            "state-california not found in active jurisdictions. "
            f"Found: {sorted(jurisdictions.keys())}"
        )

    def test_state_california_has_ca_sos(self):
        """state-california has ca_sos_results as its election source."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["state-california"]
        election_sources = config.get("election_sources", {})
        assert "ca_sos_results" in election_sources

    def test_san_rafael_has_ca_sos(self):
        """city-san-rafael now includes ca_sos_results with districts."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["city-san-rafael"]
        election_sources = config.get("election_sources", {})
        assert "ca_sos_results" in election_sources
        ca_sos = election_sources["ca_sos_results"]
        assert ca_sos["county"] == "marin"
        assert "districts" in ca_sos
        assert ca_sos["districts"]["us-rep"] == [2]
        assert ca_sos["districts"]["state-assembly"] == [12]
        assert ca_sos["districts"]["state-senate"] == [2]

    def test_san_rafael_retains_existing_sources(self):
        """Existing election sources are preserved."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["city-san-rafael"]
        election_sources = config.get("election_sources", {})
        assert "marin_registrar_results" in election_sources
        marin = election_sources["marin_registrar_results"]
        assert marin["division_filter"] == "City of San Rafael"

    def test_county_marin_has_ca_sos(self):
        """county-marin also has ca_sos_results (added in previous session)."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["county-marin"]
        election_sources = config.get("election_sources", {})
        assert "ca_sos_results" in election_sources
        assert election_sources["ca_sos_results"]["county"] == "marin"


class TestElectionDispatchLogic:
    """Test the dispatch logic that scheduled_election_refresh() uses.

    Extracts the dispatch conditionals from the function and verifies
    correct provider selection and parameter passing for each jurisdiction.
    """

    KNOWN_PROVIDERS = {"marin_registrar_results", "ca_sos_results"}

    def _dispatch_providers(self, config):
        """Simulate the dispatch logic from scheduled_election_refresh().

        Returns dict of {provider_name: params_dict} for providers that
        would be called.
        """
        election_sources = config.get("election_sources", {})
        dispatched = {}

        if "marin_registrar_results" in election_sources:
            provider_config = election_sources["marin_registrar_results"]
            if provider_config is True:
                provider_config = {}
            dispatched["marin_registrar_results"] = {
                "from_year": provider_config.get("from_year", 2010),
                "division_filter": provider_config.get("division_filter", ""),
            }

        if "ca_sos_results" in election_sources:
            provider_config = election_sources["ca_sos_results"]
            if provider_config is True:
                provider_config = {}
            districts = provider_config.get("districts", {})
            dispatched["ca_sos_results"] = {
                "county": provider_config.get("county", ""),
                "districts_json": json.dumps(districts) if districts else "",
            }

        return dispatched

    def test_state_california_dispatches_ca_sos_only(self):
        """state-california should only dispatch ca_sos_results (no Google Civic)."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["state-california"]
        dispatched = self._dispatch_providers(config)
        assert "ca_sos_results" in dispatched
        assert "google_civic" not in dispatched
        # Statewide: no county or districts
        assert dispatched["ca_sos_results"]["county"] == ""
        assert dispatched["ca_sos_results"]["districts_json"] == ""

    def test_san_rafael_dispatches_both_providers(self):
        """city-san-rafael should dispatch Marin Registrar + CA SOS."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["city-san-rafael"]
        dispatched = self._dispatch_providers(config)
        assert set(dispatched.keys()) == {"marin_registrar_results", "ca_sos_results"}

        # Verify CA SOS params
        ca_sos = dispatched["ca_sos_results"]
        assert ca_sos["county"] == "marin"
        districts = json.loads(ca_sos["districts_json"])
        assert districts == {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}

        # Verify Marin Registrar params
        marin = dispatched["marin_registrar_results"]
        assert marin["from_year"] == 2010
        assert marin["division_filter"] == "City of San Rafael"

    def test_county_marin_dispatches_both_providers(self):
        """county-marin should dispatch Marin Registrar + CA SOS."""
        jurisdictions = _load_active_jurisdictions()
        config = jurisdictions["county-marin"]
        dispatched = self._dispatch_providers(config)
        assert "marin_registrar_results" in dispatched
        assert "ca_sos_results" in dispatched
        assert dispatched["ca_sos_results"]["county"] == "marin"

    def test_no_election_sources_dispatches_nothing(self):
        """Jurisdictions without election_sources should dispatch nothing."""
        config = {"source_type": "proudcity", "jurisdiction_id": "city-test"}
        dispatched = self._dispatch_providers(config)
        assert dispatched == {}

    def test_unknown_providers_detected(self):
        """Unknown provider keys are detectable (scheduled_election_refresh logs a warning)."""
        config = {
            "election_sources": {
                "fake_provider": {"key": "value"},
            }
        }
        election_sources = config.get("election_sources", {})
        unknown = set(election_sources.keys()) - self.KNOWN_PROVIDERS
        assert unknown == {"fake_provider"}

    def test_ca_sos_true_uses_defaults(self):
        """ca_sos_results: true (bare boolean) should use empty defaults."""
        config = {"election_sources": {"ca_sos_results": True}}
        dispatched = self._dispatch_providers(config)
        ca_sos = dispatched["ca_sos_results"]
        assert ca_sos["county"] == ""
        assert ca_sos["districts_json"] == ""
