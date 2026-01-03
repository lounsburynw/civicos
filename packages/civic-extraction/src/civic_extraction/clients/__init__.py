"""
Platform clients for civic meeting extraction.

Each client wraps a specific municipal platform API:
- legistar: Legistar API (Granicus product)
- civicclerk: CivicClerk API (Granicus product)
- proudcity: ProudCity/WordPress web scraping (San Rafael, etc.)
- usaspending: USAspending.gov federal awards API
- cagrants: California Grants Portal (grants.ca.gov via data.ca.gov)
- fac: Federal Audit Clearinghouse (Single Audit / SEFA data)
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
    "CaliforniaGrantsClient",
    "FederalAuditClearinghouseClient",
    "create_san_rafael_fac_client",
    "BaseExtractor",
    "Meeting",
    "ExtractionConfig",
    "DataSource",
    "HealthStatus",
]
