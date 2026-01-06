"""
Platform clients for civic meeting extraction.

Each client wraps a specific municipal platform API:
- legistar: Legistar API (Granicus product)
- civicclerk: CivicClerk API (Granicus product)
- proudcity: ProudCity/WordPress web scraping (San Rafael, etc.)
- usaspending: USAspending.gov federal awards API
- cagrants: California Grants Portal (grants.ca.gov via data.ca.gov)
- fac: Federal Audit Clearinghouse (Single Audit / SEFA data)
- google_civic: Google Civic Information API (elections, voter info)
- representatives: Unified representative lookup (Congress.gov, Open States, local)
"""

from civic_extraction.clients.legistar import LegistarClient
from civic_extraction.clients.civicclerk import CivicClerkClient
from civic_extraction.clients.proudcity import (
    ProudCityClient,
    ProudCitySource,
    create_san_rafael_client,
    create_san_rafael_source,
)
from civic_extraction.clients.usaspending import USAspendingClient
from civic_extraction.clients.cagrants import CaliforniaGrantsClient
from civic_extraction.clients.fac import (
    FederalAuditClearinghouseClient,
    create_san_rafael_fac_client,
)
from civic_extraction.clients.ca_state_controller import (
    CAStateControllerClient,
    create_san_rafael_sco_client,
)
from civic_extraction.clients.google_civic import (
    GoogleCivicClient,
    create_san_rafael_civic_client,
    google_civic_to_election,
    google_civic_to_voter_info,
    extract_elections_to_storage,
    extract_voter_info_to_storage,
    ElectionStorageProtocol,
)
from civic_extraction.clients.representatives import (
    RepresentativesClient,
    Representative,
    CongressGovClient,
    OpenStatesClient,
    create_san_rafael_representatives_client,
    representative_to_elected_official,
    extract_elected_officials_to_storage,
    ElectedOfficialStorageProtocol,
)
from civic_extraction.clients.base import (
    BaseExtractor,
    Meeting,
    ExtractionConfig,
    DataSource,
    HealthStatus,
)
from civic_extraction.clients.legiscan import LegiScanClient, TOPIC_KEYWORDS
from civic_extraction.clients.seeclickfix import SeeClickFixClient

__all__ = [
    "LegistarClient",
    "CivicClerkClient",
    "ProudCityClient",
    "ProudCitySource",
    "create_san_rafael_client",
    "create_san_rafael_source",
    "USAspendingClient",
    "CaliforniaGrantsClient",
    "FederalAuditClearinghouseClient",
    "create_san_rafael_fac_client",
    "CAStateControllerClient",
    "create_san_rafael_sco_client",
    "GoogleCivicClient",
    "create_san_rafael_civic_client",
    "google_civic_to_election",
    "google_civic_to_voter_info",
    "extract_elections_to_storage",
    "extract_voter_info_to_storage",
    "ElectionStorageProtocol",
    "RepresentativesClient",
    "Representative",
    "CongressGovClient",
    "OpenStatesClient",
    "create_san_rafael_representatives_client",
    "representative_to_elected_official",
    "extract_elected_officials_to_storage",
    "ElectedOfficialStorageProtocol",
    "BaseExtractor",
    "Meeting",
    "ExtractionConfig",
    "DataSource",
    "HealthStatus",
    "LegiScanClient",
    "TOPIC_KEYWORDS",
    "SeeClickFixClient",
]
