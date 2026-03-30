"""
California election source provider.

Detects available election data sources for California jurisdictions:
- CA Secretary of State (all CA jurisdictions, with county breakdown fallback)
- Civera ElectionStats (counties with known instances: Marin, San Joaquin, Sonoma, Yolo)
- Legislative district detection via Census Bureau geocoder

Marin County uses a legacy "marin_registrar_results" config key for
backwards compatibility with existing extraction configs.
"""

import logging
from typing import Any, Dict, Optional

from civicos_extraction.providers import StateElectionProvider

logger = logging.getLogger(__name__)


class CaliforniaElectionProvider(StateElectionProvider):
    """Election source detection for California jurisdictions."""

    @property
    def state_code(self) -> str:
        return "CA"

    def detect_election_sources(
        self,
        jurisdiction_id: str,
        county: str,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        sources: Dict[str, Any] = {}

        # Civera ElectionStats — available for counties with known instances
        from civicos_extraction.clients.civera_election_stats import CIVERA_INSTANCES
        has_civera = county in CIVERA_INSTANCES

        if has_civera:
            from civicos_extraction.onboard import (
                _infer_division_name,
                _validate_civera_division_filter,
            )
            instance = CIVERA_INSTANCES[county]
            division_filter = _infer_division_name(jurisdiction_id)

            validated = _validate_civera_division_filter(
                instance["graphql_url"], county, division_filter,
            )

            if county == "marin":
                # Marin uses legacy config key for backwards compatibility
                sources["marin_registrar_results"] = {
                    "from_year": 2010,
                    "division_filter": division_filter,
                }
            else:
                sources["civera_election_stats"] = {
                    "county_slug": county,
                    "graphql_url": instance["graphql_url"],
                    "from_year": 2010,
                    "division_filter": division_filter,
                }

            if not validated:
                logger.warning(
                    f"Division filter '{division_filter}' returned 0 contests "
                    f"from Civera ({county}). Local race data may be missing. "
                    f"Check the registrar's actual division names."
                )

        # CA SOS — available for all California jurisdictions.
        # county_breakdown: True for non-Civera counties (SOS is primary local
        # race data source), False for Civera counties (Civera is primary).
        ca_sos: Dict[str, Any] = {"county": county, "county_breakdown": not has_civera}
        if lat is not None and lng is not None:
            from civicos_extraction.onboard import detect_districts
            districts = detect_districts(lat, lng, self.state_code)
            if districts:
                ca_sos["districts"] = districts
        sources["ca_sos_results"] = ca_sos

        return sources
