"""
Municipal research module.

Provides structured research capabilities for municipal data including
funding programs, ordinances, and civic engagement opportunities.

Supports:
- Single-query research (fast)
- Ensemble research (multiple focused queries, more comprehensive)
- Municipality-specific configuration via research_config.yaml
"""

from .funding import (
    EnsembleResearchResult,
    MunicipalFundingResearcher,
    MunicipalityConfig,
    QueryResult,
    ResearchResult,
)
from .query_templates import (
    HOUSING_QUERY_TEMPLATES,
    QueryTemplate,
    get_templates_for_topic,
)
from .schemas import (
    BallotMeasure,
    ContactInfo,
    FundingProgram,
    IncomeLimits,
    MunicipalFundingPrograms,
    RecentFundingAward,
)

__all__ = [
    # Researcher
    "MunicipalFundingResearcher",
    # Results
    "EnsembleResearchResult",
    "QueryResult",
    "ResearchResult",
    # Config
    "MunicipalityConfig",
    # Templates
    "HOUSING_QUERY_TEMPLATES",
    "QueryTemplate",
    "get_templates_for_topic",
    # Schemas
    "BallotMeasure",
    "ContactInfo",
    "FundingProgram",
    "IncomeLimits",
    "MunicipalFundingPrograms",
    "RecentFundingAward",
]
