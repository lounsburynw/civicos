"""
Jurisdiction Registry - Centralized jurisdiction configuration management.

This module re-exports from civicos_config for backward compatibility.
All jurisdiction configuration is now maintained in the civic-config package.

Usage:
    from civicos.jurisdiction import JurisdictionRegistry, JurisdictionConfig

For new code, consider importing directly from civicos_config:
    from civicos_config import JurisdictionRegistry, JurisdictionConfig
"""

# Re-export all public symbols from civicos_config
from civicos_config import (
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
