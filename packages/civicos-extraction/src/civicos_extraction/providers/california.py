"""
California election source provider.

Detects available election data sources for California jurisdictions:
- CA Secretary of State (all CA jurisdictions, with county breakdown fallback)
- Civera ElectionStats (counties with known instances: Marin, San Joaquin, Sonoma, Yolo)
- Clarity Elections ENR (7 net-new counties: Butte, Contra Costa, Madera, Merced, Santa Clara, Shasta, Ventura)
- Legislative district detection via Census Bureau geocoder
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

        # Clarity Elections — available for counties with known Clarity ENR pages.
        # Skipped if county already has Civera (Civera has permanent archives;
        # Clarity data is ephemeral).
        has_clarity = False
        if not has_civera:
            from civicos_extraction.clients.clarity_elections import (
                CLARITY_INSTANCES,
                has_clarity_instance,
            )
            if has_clarity_instance(county, "CA"):
                instance = CLARITY_INSTANCES["CA"][county]
                sources["clarity_elections"] = {
                    "county": county,
                    "url_name": instance["url_name"],
                }
                has_clarity = True
                logger.info(
                    f"Clarity Elections detected for {county} county "
                    f"({instance['url_name']})",
                )

        # CA SOS — available for all California jurisdictions.
        # county_breakdown: True when neither Civera nor Clarity is available
        # (SOS is primary local race data source), False otherwise.
        has_local_source = has_civera or has_clarity
        ca_sos: Dict[str, Any] = {"county": county, "county_breakdown": not has_local_source}
        if lat is not None and lng is not None:
            from civicos_extraction.onboard import detect_districts
            districts = detect_districts(lat, lng, self.state_code)
            if districts:
                ca_sos["districts"] = districts
        sources["ca_sos_results"] = ca_sos

        return sources
