"""
Platform clients for civic meeting extraction.

Each client wraps a specific municipal platform API:
- legistar: Legistar API (Granicus product)
- civicclerk: CivicClerk API (Granicus product)
- proudcity: ProudCity/WordPress web scraping (San Rafael, etc.)
- usaspending: USAspending.gov federal awards API
- cagrants: California Grants Portal (grants.ca.gov via data.ca.gov)
- fac: Federal Audit Clearinghouse (Single Audit / SEFA data)
- marin_registrar: Marin County Registrar of Voters (local elections)
- boarddocs: BoardDocs school board portals (meetings, agendas, attachments)
- san_rafael_clerk: San Rafael City Clerk (city candidates, local measures)
- representatives: Unified representative lookup (Congress.gov, Open States, local)
- hud_exchange: HUD Exchange / HUD CPD allocation data (CDBG, HOME, ESG, etc.)
- sam_assistance: SAM.gov Assistance Listings (federal program definitions, formerly CFDA)
- ca_sos_results: CA Secretary of State election results (api.sos.ca.gov)
"""

from civicos_extraction.clients.legistar import LegistarClient
from civicos_extraction.clients.civicclerk import CivicClerkClient
from civicos_extraction.clients.proudcity import (
    ProudCityClient,
    ProudCitySource,
    create_san_rafael_client,
    create_san_rafael_source,
)
from civicos_extraction.clients.usaspending import USAspendingClient
from civicos_extraction.clients.cagrants import CaliforniaGrantsClient
from civicos_extraction.clients.fac import (
    FederalAuditClearinghouseClient,
    create_san_rafael_fac_client,
)
from civicos_extraction.clients.ca_state_controller import (
    CAStateControllerClient,
    create_san_rafael_sco_client,
)
from civicos_extraction.clients.representatives import (
    RepresentativesClient,
    Representative,
    CongressGovClient,
    OpenStatesClient,
    create_san_rafael_representatives_client,
    representative_to_elected_official,
    extract_elected_officials_to_storage,
    ElectedOfficialStorageProtocol,
)
from civicos_extraction.clients.granicus import (
    GranicusClient,
    GranicusSource,
    create_marin_county_client,
    create_marin_county_source,
)
from civicos_extraction.clients.base import (
    BaseExtractor,
    Meeting,
    ExtractionConfig,
    DataSource,
    ElectionExtractor,
    ContestDict,
    ContestCandidate,
    HealthStatus,
    classify_contest_type,
)
from civicos_extraction.clients.legiscan import LegiScanClient, TOPIC_KEYWORDS
from civicos_extraction.clients.seeclickfix import SeeClickFixClient
from civicos_extraction.clients.marin_registrar import (
    MarinRegistrarClient,
    create_san_rafael_registrar_client,
    marin_election_to_storage,
    extract_marin_elections_to_storage,
)
from civicos_extraction.clients.civera_election_stats import (
    CiveraElectionStatsClient,
    CIVERA_INSTANCES,
    civera_results_to_election,
    civera_results_to_contest,
    extract_civera_results_to_storage,
)
from civicos_extraction.clients.san_rafael_clerk import (
    SanRafaelClerkClient,
    create_san_rafael_clerk_client,
    san_rafael_candidate_to_storage,
    san_rafael_measure_to_storage,
)
from civicos_extraction.clients.simbli import (
    SimbliClient,
    SimbliMeeting,
    create_srcs_simbli_client,
    simbli_meeting_to_storage,
    extract_simbli_meetings_to_storage,
)
from civicos_extraction.clients.youtube_boards import (
    YouTubeBoardsClient,
    YouTubeBoardsSource,
    YouTubeVideo,
    create_srcs_youtube_client,
    create_srcs_youtube_source,
)
from civicos_extraction.clients.hud_exchange import (
    HUDExchangeClient,
    HUDAllocation,
    create_hud_exchange_client,
    hud_allocation_to_storage,
    extract_allocations_to_storage,
)
from civicos_extraction.clients.sam_assistance import (
    SAMAssistanceClient,
    AssistanceListing,
    create_sam_assistance_client,
    sam_program_to_storage,
    extract_programs_for_topics,
    extract_programs_by_aln,
)
# Registry of meeting source types with implemented fetch support in the
# ingestion pipeline.  Used by onboard.py and modal_ingest.py to decide
# which stages to run.  Add new source types here as clients are wired up.
SUPPORTED_MEETING_SOURCES: frozenset[str] = frozenset({"proudcity", "granicus", "legistar", "civicclerk", "escribe", "boarddocs", "simbli", "civicplus", "universal"})

# Registry of 311 issue source types with implemented fetch support.
# Used by modal_ingest.py fetch_issues() to dispatch to the correct client.
# Add new issue providers here as clients are wired up.
SUPPORTED_ISSUE_SOURCES: frozenset[str] = frozenset({"seeclickfix", "gogov"})

# Registry of election source types with implemented fetch support.
# Used by modal_ingest.py and scheduled_election_refresh() for dispatch.
# Add new election providers here as clients are wired up.
SUPPORTED_ELECTION_SOURCES: frozenset[str] = frozenset({
    "civera_election_stats",
    "marin_registrar_results",
    "ca_sos_results",
    "ca_sos_ballot_preview",
    "clarity_elections",
})


def is_election_source_supported(source_key: str) -> bool:
    """Check whether a fetch client exists for an election source key."""
    return source_key in SUPPORTED_ELECTION_SOURCES


from civicos_extraction.clients.boarddocs import (
    BoardDocsClient,
    BoardDocsMeeting,
    AgendaItem,
    boarddocs_meeting_to_storage,
    extract_boarddocs_meetings_to_storage,
)
from civicos_extraction.clients.escribe import EScribeClient
from civicos_extraction.clients.ca_sos_results import (
    CASOSResultsClient,
    ca_sos_results_to_election,
    ca_sos_race_to_contest,
    ca_sos_measure_to_contest,
    extract_ca_sos_results_to_storage,
    STATEWIDE_RACES,
)
from civicos_extraction.clients.ca_sos_ballot_preview import (
    CASOSBallotPreviewClient,
    parse_candidate_pdf,
    ca_sos_preview_to_election,
    ca_sos_preview_to_contest,
    extract_ca_sos_preview_to_storage,
    RACE_CONFIGS as BALLOT_PREVIEW_RACES,
)
from civicos_extraction.clients.clarity_elections import (
    ClarityElectionsClient,
    CLARITY_INSTANCES,
    has_clarity_instance,
    detect_clarity_elections,
    clarity_results_to_election,
    clarity_contest_to_storage,
    extract_clarity_results_to_storage,
)
from civicos_extraction.clients.federal_register import (
    FederalRegisterClient,
    get_recent_executive_orders,
)

__all__ = [
    "SUPPORTED_MEETING_SOURCES",
    "SUPPORTED_ISSUE_SOURCES",
    "SUPPORTED_ELECTION_SOURCES",
    "ElectionExtractor",
    "ContestDict",
    "ContestCandidate",
    "LegistarClient",
    "CivicClerkClient",
    "EScribeClient",
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
    "RepresentativesClient",
    "Representative",
    "CongressGovClient",
    "OpenStatesClient",
    "create_san_rafael_representatives_client",
    "representative_to_elected_official",
    "extract_elected_officials_to_storage",
    "ElectedOfficialStorageProtocol",
    "GranicusClient",
    "GranicusSource",
    "create_marin_county_client",
    "create_marin_county_source",
    "BaseExtractor",
    "Meeting",
    "ExtractionConfig",
    "DataSource",
    "HealthStatus",
    "classify_contest_type",
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
    "SAMAssistanceClient",
    "AssistanceListing",
    "create_sam_assistance_client",
    "sam_program_to_storage",
    "extract_programs_for_topics",
    "extract_programs_by_aln",
    "BoardDocsClient",
    "BoardDocsMeeting",
    "AgendaItem",
    "boarddocs_meeting_to_storage",
    "extract_boarddocs_meetings_to_storage",
    "CASOSResultsClient",
    "ca_sos_results_to_election",
    "ca_sos_race_to_contest",
    "ca_sos_measure_to_contest",
    "extract_ca_sos_results_to_storage",
    "STATEWIDE_RACES",
    "FederalRegisterClient",
    "get_recent_executive_orders",
    "CASOSBallotPreviewClient",
    "parse_candidate_pdf",
    "ca_sos_preview_to_election",
    "ca_sos_preview_to_contest",
    "extract_ca_sos_preview_to_storage",
    "BALLOT_PREVIEW_RACES",
    "CiveraElectionStatsClient",
    "CIVERA_INSTANCES",
    "civera_results_to_election",
    "civera_results_to_contest",
    "extract_civera_results_to_storage",
    "ClarityElectionsClient",
    "CLARITY_INSTANCES",
    "has_clarity_instance",
    "detect_clarity_elections",
    "clarity_results_to_election",
    "clarity_contest_to_storage",
    "extract_clarity_results_to_storage",
]
