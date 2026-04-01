"""
State election source providers.

Each state that CivicOS supports for election source detection implements
a StateElectionProvider subclass. The provider knows how to detect
available election data sources (registrar APIs, SOS data, etc.) for
jurisdictions in that state.

Adding a new state:
1. Add a StateElectionConfig entry in civicos._internal.elections.state_config
2. Done — DefaultElectionProvider auto-creates for any state with a config.
   Only implement a custom provider if you need per-county logic (e.g., CA/Civera).

Usage:
    from civicos_extraction.providers import get_provider
    provider = get_provider("CA")
    if provider:
        sources = provider.detect_election_sources("city-san-rafael", "marin", 37.97, -122.53)
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StateElectionProvider(ABC):
    """Abstract base class for state-specific election source detection.

    Each provider detects what election data sources are available for
    a jurisdiction in its state (e.g., Secretary of State feeds, county
    registrar APIs like Civera, legacy scrapers).
    """

    @property
    @abstractmethod
    def state_code(self) -> str:
        """Two-letter state code (e.g., 'CA')."""

    @abstractmethod
    def detect_election_sources(
        self,
        jurisdiction_id: str,
        county: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Detect available election data sources for a jurisdiction.

        Args:
            jurisdiction_id: e.g. "city-san-rafael", "county-marin"
            county: Normalized county name (lowercase, no "County" suffix)
            lat: Latitude from geocoding (enables district detection)
            lng: Longitude from geocoding (enables district detection)

        Returns:
            Dict keyed by source name, matching the election_sources
            schema in extraction configs. Example:
            {"ca_sos_results": {"county": "marin", "districts": {"us-rep": [2]}}}
        """


# Provider registry — instances are created lazily on first access.
_PROVIDERS: Dict[str, StateElectionProvider] = {}


def get_provider(state_code: str) -> Optional[StateElectionProvider]:
    """Get the election source provider for a state.

    Returns None for states without a registered provider (those states
    will have no auto-detected election sources during onboarding).
    """
    code = state_code.upper() if state_code else ""
    if not code:
        return None
    if code not in _PROVIDERS:
        _create_provider(code)
    return _PROVIDERS.get(code)


def _create_provider(state_code: str) -> None:
    """Lazy-create and register a provider instance.

    CA has a custom provider (Civera per-county logic). All other states
    with a StateElectionConfig get a DefaultElectionProvider automatically.
    """
    if state_code == "CA":
        from civicos_extraction.providers.california import CaliforniaElectionProvider
        _PROVIDERS["CA"] = CaliforniaElectionProvider()
        return

    # Any state with a StateElectionConfig gets a DefaultElectionProvider
    from civicos import supported_states
    if state_code in supported_states():
        from civicos_extraction.providers.default import DefaultElectionProvider
        _PROVIDERS[state_code] = DefaultElectionProvider(state_code)
