"""
Default election source provider.

Generic provider for states without custom detection logic (e.g., Civera
county registrar APIs). Works for any state that has a StateElectionConfig
entry — no per-state provider file needed.

Produces a single source key: {state_code.lower()}_sos_results with county,
county_breakdown=True, and optional legislative districts from the Census
Bureau geocoder.

States with complex per-county detection logic (e.g., California with Civera)
should implement a custom StateElectionProvider subclass instead.
"""

import logging
from typing import Any, Dict, Optional

from civicos_extraction.providers import StateElectionProvider

logger = logging.getLogger(__name__)


class DefaultElectionProvider(StateElectionProvider):
    """Election source detection for any state without a custom provider.

    Instantiated with a state code and generates a standard SOS source key.
    """

    def __init__(self, state_code: str):
        self._state_code = state_code.upper()

    @property
    def state_code(self) -> str:
        return self._state_code

    def detect_election_sources(
        self,
        jurisdiction_id: str,
        county: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        source_key = f"{self._state_code.lower()}_sos_results"
        source_config: Dict[str, Any] = {"county": county, "county_breakdown": True}

        if lat is not None and lng is not None:
            from civicos_extraction.onboard import detect_districts
            districts = detect_districts(lat, lng, self._state_code)
            if districts:
                source_config["districts"] = districts

        return {source_key: source_config}
