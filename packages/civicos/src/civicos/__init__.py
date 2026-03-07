"""
CivicOS - Unified Civic Engagement Platform

The main entry point for civic engagement.

Usage:
    from civicos import CivicOS

    c = CivicOS("san-rafael-ca")

    # Query (Learn)
    c.what_applies("housing")
    c.whats_next(["transportation"])

    # Action (Act)
    c.start_something(topic="traffic", title="Protected bike lane")
    c.add_voice("agenda_item", "item_123", "support", "As a cyclist...")

"""

__version__ = "0.1.0"

# Main class
from civicos.civicos import CivicOS

# Result types (for type hints) - imported from types.py
from civicos.types import (
    RegulatoryStack,
    Decision,
    TranscriptExcerpt,
    TranscriptLink,
    DecisionWithContext,
    Meeting,
    UpcomingElection,
    Community,
    Initiative,
    Voice,
    Subscription,
    Preparation,
    ActionDraft,
    BudgetItem,
    BudgetSummary,
    FundingFlow,
    FundingFlowImpact,
    FederalExpenditure,
    IntergovernmentalRevenue,
    IntergovernmentalRevenueSummary,
    FederalProgram,
    # Entity types (from storage)
    Legislation,
    MunicipalCodeSection,
    ElectedOfficial,
    ExecutiveOrder,
)

# Cross-corpus search result type
from civicos.history import UnifiedSearchResult, HybridSearchResult

# Context types (for what_applies configuration)
from civicos.context import RankingMode

# Storage types (for dashboard/admin use)
from civicos.storage import StorageStats

# Diagnostics (schema-aware data status and coverage)
from civicos.diagnostics import (
    DataStatus,
    VectorCoverage,
    DataStatusReport,
    CorpusCount,
    format_data_status,
    format_vector_coverage,
    SCHEMA_REFERENCE,
)

# Jurisdiction registry (centralized config)
from civicos.jurisdiction import JurisdictionRegistry, JurisdictionConfig, CITY_CONFIGS

# Runtime configuration (turnkey deployment)
from civicos.config import CivicOSConfig, PeerConfig, ExtractorConfig, load_config

# Service registry (URL resolution)
from civicos.registry import (
    get_jurisdiction_url,
    get_default_jurisdiction_url,
    get_default_jurisdiction,
    get_relay_url,
    get_jurisdiction_domain,
    get_modal_app_name,
    get_modal_workspace,
)

# Path resolution (centralized data paths)
from civicos.paths import (
    DataPathResolver,
    get_resolver,
    reset_resolver,
    get_data_path,
    get_bundled_path,
    get_user_path,
    get_state_db_path,
    get_vectors_dir,
    get_checkpoints_dir,
)

# Optional MCP support - lazy import to avoid circular dependencies
MCP_AVAILABLE = False
mcp_server = None
serve_mcp = None

def _load_mcp():
    """Lazy-load MCP components."""
    global MCP_AVAILABLE, mcp_server, serve_mcp
    try:
        from civicos.mcp import create_mcp_server, main
        MCP_AVAILABLE = True
        mcp_server = create_mcp_server
        serve_mcp = main
    except ImportError:
        pass

# Don't auto-load MCP - let users call _load_mcp() or import directly

__all__ = [
    # Version
    "__version__",
    # Main class
    "CivicOS",
    # Result types (from types.py)
    "RegulatoryStack",
    "Decision",
    "TranscriptExcerpt",
    "TranscriptLink",
    "DecisionWithContext",
    "Meeting",
    "UpcomingElection",
    "Community",
    "Initiative",
    "Voice",
    "Subscription",
    "Preparation",
    "ActionDraft",
    "BudgetItem",
    "BudgetSummary",
    "FundingFlow",
    "FundingFlowImpact",
    "FederalExpenditure",
    "IntergovernmentalRevenue",
    "IntergovernmentalRevenueSummary",
    "FederalProgram",
    # Entity types (from storage)
    "Legislation",
    "MunicipalCodeSection",
    "ElectedOfficial",
    "ExecutiveOrder",
    # Cross-corpus search result types
    "UnifiedSearchResult",
    "HybridSearchResult",
    # Context types
    "RankingMode",
    # Storage types
    "StorageStats",
    # Diagnostics
    "DataStatus",
    "VectorCoverage",
    "DataStatusReport",
    "CorpusCount",
    "format_data_status",
    "format_vector_coverage",
    "SCHEMA_REFERENCE",
    # Jurisdiction registry
    "JurisdictionRegistry",
    "JurisdictionConfig",
    "CITY_CONFIGS",
    # Runtime configuration
    "CivicOSConfig",
    "PeerConfig",
    "ExtractorConfig",
    "load_config",
    # Path resolution
    "DataPathResolver",
    "get_resolver",
    "reset_resolver",
    "get_data_path",
    "get_bundled_path",
    "get_user_path",
    "get_state_db_path",
    "get_vectors_dir",
    "get_checkpoints_dir",
    # Service registry
    "get_jurisdiction_url",
    "get_default_jurisdiction_url",
    "get_default_jurisdiction",
    "get_relay_url",
    "get_jurisdiction_domain",
    "get_modal_app_name",
    "get_modal_workspace",
    # MCP
    "MCP_AVAILABLE",
    "mcp_server",
    "serve_mcp",
]
