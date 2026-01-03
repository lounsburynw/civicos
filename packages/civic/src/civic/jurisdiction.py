"""
Jurisdiction Registry - Centralized jurisdiction configuration management.

This module re-exports from civic_config for backward compatibility.
All jurisdiction configuration is now maintained in the civic-config package.

Usage:
    from civic.jurisdiction import JurisdictionRegistry, JurisdictionConfig

For new code, consider importing directly from civic_config:
    from civic_config import JurisdictionRegistry, JurisdictionConfig
"""

# Re-export all public symbols from civic_config
from civic_config import (
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
