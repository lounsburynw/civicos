"""
civic-extraction: Platform clients for extracting civic meeting data

Provides clients for municipal meeting platforms:
- Legistar (6+ cities)
- CivicClerk (11+ cities)
- ProudCity (San Rafael and others)

Usage:
    from civic_extraction import LegistarClient, CivicClerkClient, ProudCityClient

    # Legistar
    legistar = LegistarClient("berkeley")
    events = legistar.get_events(days_ahead=30)

    # CivicClerk
    civicclerk = CivicClerkClient("elcerritoca")
    events = civicclerk.get_events(days_ahead=30)

    # ProudCity (San Rafael)
    from civic_extraction import create_san_rafael_client
    proudcity = create_san_rafael_client()
    events = proudcity.get_events(days_ahead=30, days_past=30)

All clients implement a common interface:
- get_events(days_ahead, ...) -> List[Dict]
- normalize_event(event) -> Meeting
"""

from civic_extraction.clients.legistar import LegistarClient
from civic_extraction.clients.civicclerk import CivicClerkClient
from civic_extraction.clients.proudcity import (
    ProudCityClient,
    ProudCitySource,
    create_san_rafael_client,
    create_san_rafael_source,
)
from civic_extraction.clients.base import (
    BaseExtractor,
    Meeting,
    DataSource,
    HealthStatus,
    ValidationResult,
    ExtractionConfig,
)
from civic_extraction.pipeline import (
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
from civic_extraction.platform_detection import (
    DetectionResult,
    detect_platform,
    detect_platform_batch,
)

__version__ = "0.1.0"
__all__ = [
    "LegistarClient",
    "CivicClerkClient",
    "ProudCityClient",
    "ProudCitySource",
    "create_san_rafael_client",
    "create_san_rafael_source",
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
]
