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
- marin_registrar: Marin County Registrar of Voters (local elections)
- san_rafael_clerk: San Rafael City Clerk (city candidates, local measures)
- representatives: Unified representative lookup (Congress.gov, Open States, local)
- hud_exchange: HUD Exchange / HUD CPD allocation data (CDBG, HOME, ESG, etc.)
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
from civic_extraction.clients.marin_registrar import (
    MarinRegistrarClient,
    create_san_rafael_registrar_client,
    marin_election_to_storage,
    extract_marin_elections_to_storage,
)
from civic_extraction.clients.san_rafael_clerk import (
    SanRafaelClerkClient,
    create_san_rafael_clerk_client,
    san_rafael_candidate_to_storage,
    san_rafael_measure_to_storage,
)
from civic_extraction.clients.simbli import (
    SimbliClient,
    SimbliMeeting,
    create_srcs_simbli_client,
    simbli_meeting_to_storage,
    extract_simbli_meetings_to_storage,
)
from civic_extraction.clients.youtube_boards import (
    YouTubeBoardsClient,
    YouTubeBoardsSource,
    YouTubeVideo,
    create_srcs_youtube_client,
    create_srcs_youtube_source,
)
from civic_extraction.clients.hud_exchange import (
    HUDExchangeClient,
    HUDAllocation,
    create_hud_exchange_client,
    hud_allocation_to_storage,
    extract_allocations_to_storage,
)

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
    "MarinRegistrarClient",
    "create_san_rafael_registrar_client",
    "marin_election_to_storage",
    "extract_marin_elections_to_storage",
    "SanRafaelClerkClient",
    "create_san_rafael_clerk_client",
    "san_rafael_candidate_to_storage",
    "san_rafael_measure_to_storage",
    "SimbliClient",
    "SimbliMeeting",
    "create_srcs_simbli_client",
    "simbli_meeting_to_storage",
    "extract_simbli_meetings_to_storage",
    "YouTubeBoardsClient",
    "YouTubeBoardsSource",
    "YouTubeVideo",
    "create_srcs_youtube_client",
    "create_srcs_youtube_source",
    "HUDExchangeClient",
    "HUDAllocation",
    "create_hud_exchange_client",
    "hud_allocation_to_storage",
    "extract_allocations_to_storage",
]
