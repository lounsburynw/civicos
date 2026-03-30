"""
Texas election source provider.

Detects available election data sources for Texas jurisdictions:
- TX Secretary of State (all TX jurisdictions, county-level breakdown)
- Legislative district detection via Census Bureau geocoder

Texas SOS election results are published at results.texas-election.com
and sos.texas.gov/elections/. Unlike California, Texas does not expose a
clean public REST API — results are web-based with county-level reporting.
The tx_sos_results source config signals the extraction pipeline to use
the TX SOS client when available.

County registrar sources (e.g., Harris County, Travis County) can be
added as they are discovered, following the Civera registry pattern used
in California.
"""

import logging
from typing import Any, Dict, Optional

from civicos_extraction.providers import StateElectionProvider

logger = logging.getLogger(__name__)


class TexasElectionProvider(StateElectionProvider):
    """Election source detection for Texas jurisdictions."""

    @property
    def state_code(self) -> str:
        return "TX"

    def detect_election_sources(
        self,
        jurisdiction_id: str,
        county: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        sources: Dict[str, Any] = {}

        # TX SOS — available for all Texas jurisdictions.
        # Texas publishes county-level election results through the SOS.
        # county_breakdown is always True since there are no county
        # registrar APIs discovered yet (unlike CA's Civera instances).
        tx_sos: Dict[str, Any] = {"county": county, "county_breakdown": True}

        if lat is not None and lng is not None:
            from civicos_extraction.onboard import detect_districts
            districts = detect_districts(lat, lng, self.state_code)
            if districts:
                tx_sos["districts"] = districts

        sources["tx_sos_results"] = tx_sos
        return sources
