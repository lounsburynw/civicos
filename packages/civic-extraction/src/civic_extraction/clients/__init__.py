"""
Platform clients for civic meeting extraction.

Each client wraps a specific municipal platform API:
- legistar: Legistar API (Granicus product)
- civicclerk: CivicClerk API (Granicus product)
- proudcity: ProudCity/WordPress web scraping (San Rafael, etc.)
- usaspending: USAspending.gov federal awards API
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
from civic_extraction.clients.base import (
    BaseExtractor,
    Meeting,
    ExtractionConfig,
    DataSource,
    HealthStatus,
)

__all__ = [
    "LegistarClient",
    "CivicClerkClient",
    "ProudCityClient",
    "ProudCitySource",
    "create_san_rafael_client",
    "create_san_rafael_source",
    "USAspendingClient",
    "BaseExtractor",
    "Meeting",
    "ExtractionConfig",
    "DataSource",
    "HealthStatus",
]
