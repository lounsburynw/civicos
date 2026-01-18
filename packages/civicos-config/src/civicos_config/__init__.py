"""
Civic Config - Shared jurisdiction configuration for Civic platform packages.

This module provides the single source of truth for jurisdiction-related
configuration including timezone mappings, agent types, meeting URLs, and
contact information.

Usage:
    from civicos_config import JurisdictionRegistry, JurisdictionConfig

    config = JurisdictionRegistry.get("san_rafael")
    config = JurisdictionRegistry.get_by_id("city-san-rafael")
    timezone = JurisdictionRegistry.get_timezone("city-san-rafael")
"""

from civicos_config.jurisdiction import (
    GranicusConfig,
    JurisdictionConfig,
    JurisdictionRegistry,
    CITY_CONFIGS,
)

__all__ = [
    "GranicusConfig",
    "JurisdictionConfig",
    "JurisdictionRegistry",
    "CITY_CONFIGS",
]
