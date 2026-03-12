"""
civic-extraction: Platform clients for extracting civic meeting data

Provides clients for municipal meeting platforms:
- Legistar (6+ cities)
- CivicClerk (11+ cities)
- ProudCity (San Rafael and others)

Usage:
    from civicos_extraction import LegistarClient, CivicClerkClient, ProudCityClient

    # Legistar
    legistar = LegistarClient("berkeley")
    events = legistar.get_events(days_ahead=30)

    # CivicClerk
    civicclerk = CivicClerkClient("elcerritoca")
    events = civicclerk.get_events(days_ahead=30)

    # ProudCity (San Rafael)
    from civicos_extraction import create_san_rafael_client
    proudcity = create_san_rafael_client()
    events = proudcity.get_events(days_ahead=30, days_past=30)

All clients implement a common interface:
- get_events(days_ahead, ...) -> List[Dict]
- normalize_event(event) -> Meeting
"""

from civicos_extraction.clients.legistar import LegistarClient
from civicos_extraction.clients.civicclerk import CivicClerkClient
from civicos_extraction.clients.proudcity import (
    ProudCityClient,
    ProudCitySource,
    create_san_rafael_client,
    create_san_rafael_source,
)
from civicos_extraction.clients.google_civic import (
    GoogleCivicClient,
    create_san_rafael_civic_client,
)
from civicos_extraction.clients.base import (
    BaseExtractor,
    Meeting,
    DataSource,
    HealthStatus,
    ValidationResult,
    ExtractionConfig,
)
from civicos_extraction.pipeline import (
    Pipeline,
    PipelineResult,
    StageStatus,
    StageState,
    IngestCheckpoint,
    PostIngestionReport,
    save_checkpoint,
    load_checkpoint,
    checkpoint_path_for_jurisdiction,
)
from civicos_extraction.meeting_schema import (
    MeetingValidator,
    MeetingValidationResult,
    BatchValidationResult,
    MEETING_SCHEMA,
)
from civicos_extraction.platform_detection import (
    DetectionResult,
    detect_platform,
    detect_platform_batch,
    discover_granicus_subdomain,
)
from civicos_extraction.manifest import (
    IngestionManifest,
    SourceEntry,
    ValidationSummary,
    save_manifest,
    load_manifest,
    list_manifests,
    get_latest_manifest,
)
from civicos_extraction.config import (
    load_jurisdiction_config,
    get_active_jurisdictions,
    get_jurisdictions_with_hud_config,
    get_hud_grantee,
    get_hud_relationship,
)

__version__ = "0.1.0"
__all__ = [
    "LegistarClient",
    "CivicClerkClient",
    "ProudCityClient",
    "ProudCitySource",
    "create_san_rafael_client",
    "create_san_rafael_source",
    "GoogleCivicClient",
    "create_san_rafael_civic_client",
    "BaseExtractor",
    "Meeting",
    "DataSource",
    "HealthStatus",
    "ValidationResult",
    "ExtractionConfig",
    "Pipeline",
    "PipelineResult",
    "StageStatus",
    "StageState",
    "IngestCheckpoint",
    "PostIngestionReport",
    "save_checkpoint",
    "load_checkpoint",
    "checkpoint_path_for_jurisdiction",
    "DetectionResult",
    "detect_platform",
    "detect_platform_batch",
    "discover_granicus_subdomain",
    "MeetingValidator",
    "MeetingValidationResult",
    "BatchValidationResult",
    "MEETING_SCHEMA",
    "IngestionManifest",
    "SourceEntry",
    "ValidationSummary",
    "save_manifest",
    "load_manifest",
    "list_manifests",
    "get_latest_manifest",
    "load_jurisdiction_config",
    "get_active_jurisdictions",
    "get_jurisdictions_with_hud_config",
    "get_hud_grantee",
    "get_hud_relationship",
]
