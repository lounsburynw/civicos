"""
CivicOS Configuration - Unified configuration for CivicOS instances.

This module provides config-driven setup for turnkey CivicOS deployment.
Supports YAML files, environment variables, and programmatic construction.

Usage:
    # From YAML file
    config = CivicOSConfig.from_yaml("civicos.yaml")
    c = CivicOS(config)

    # From environment variables
    config = CivicOSConfig.from_env()
    c = CivicOS(config)

    # Programmatic
    config = CivicOSConfig(jurisdiction_id="city-san-rafael")
    c = CivicOS(config)

    # Backward compatible - string still works
    c = CivicOS("san-rafael")
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import os
import logging

logger = logging.getLogger(__name__)

# Optional YAML support - gracefully degrade if not installed
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None


@dataclass
class PeerConfig:
    """Configuration for a federation peer."""

    jurisdiction_id: str
    mcp_endpoint: str
    display_name: Optional[str] = None
    enabled: bool = True


@dataclass
class ExtractorConfig:
    """Configuration for a data extractor."""

    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CivicOSConfig:
    """
    Configuration for a CivicOS instance.

    This is the turnkey configuration model that allows new jurisdictions
    to be onboarded without code changes. It combines runtime settings
    (which jurisdiction to use) with optional metadata and federation config.

    Attributes:
        jurisdiction_id: Canonical jurisdiction ID (e.g., "city-san-rafael").
            Accepts various formats - will be normalized.
        display_name: Human-readable name (e.g., "San Rafael, CA").
            If not provided, derived from JurisdictionRegistry.
        timezone: IANA timezone (e.g., "America/Los_Angeles").
            If not provided, derived from JurisdictionRegistry or defaults to UTC.
        db_path: Path to SQLite database (optional, uses default if not set).
        peers: List of federation peer configurations.
        extractors: Dictionary of extractor configurations.
        federation_enabled: Whether to enable federated queries.
        metadata: Additional custom metadata.
    """

    jurisdiction_id: str
    display_name: Optional[str] = None
    timezone: Optional[str] = None
    db_path: Optional[str] = None
    peers: List[PeerConfig] = field(default_factory=list)
    extractors: Dict[str, ExtractorConfig] = field(default_factory=dict)
    federation_enabled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize jurisdiction_id and derive missing fields from registry."""
        # Normalize jurisdiction ID to canonical format
        from civicos._internal.jurisdiction import normalize_jurisdiction
        self.jurisdiction_id = normalize_jurisdiction(self.jurisdiction_id, strict=False)

        # Derive display_name and timezone from JurisdictionRegistry if not provided
        from civicos.jurisdiction import JurisdictionRegistry

        if self.display_name is None:
            self.display_name = JurisdictionRegistry.get_display_name(
                self.jurisdiction_id,
                default=self._derive_display_name()
            )

        if self.timezone is None:
            self.timezone = JurisdictionRegistry.get_timezone(
                self.jurisdiction_id,
                default="UTC"
            )

    def _derive_display_name(self) -> str:
        """Derive a display name from jurisdiction_id if not in registry."""
        # Convert "city-san-rafael" -> "San Rafael"
        parts = self.jurisdiction_id.split("-")
        # Remove prefix like "city", "county", "school"
        if parts[0] in ("city", "county", "school", "district"):
            parts = parts[1:]
        return " ".join(p.title() for p in parts)

    @classmethod
    def from_yaml(cls, path: str) -> "CivicOSConfig":
        """
        Load configuration from a YAML file.

        Args:
            path: Path to YAML configuration file.

        Returns:
            CivicOSConfig instance.

        Raises:
            ImportError: If PyYAML is not installed.
            FileNotFoundError: If the file doesn't exist.
            ValueError: If required fields are missing.

        Example YAML:
            jurisdiction_id: city-san-rafael
            display_name: "San Rafael, CA"
            timezone: America/Los_Angeles

            federation_enabled: true
            peers:
              - jurisdiction_id: city-berkeley
                mcp_endpoint: https://berkeley.civicos.org/mcp

            extractors:
              legistar:
                enabled: false
              proudcity:
                enabled: true
                config:
                  base_url: https://www.cityofsanrafael.org
        """
        if not YAML_AVAILABLE:
            raise ImportError(
                "PyYAML is required for YAML config loading. "
                "Install with: pip install pyyaml"
            )

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty configuration file: {path}")

        if "jurisdiction_id" not in data:
            raise ValueError(
                f"Configuration must include 'jurisdiction_id'. File: {path}"
            )

        return cls._from_dict(data)

    @classmethod
    def from_env(cls, prefix: str = "CIVICOS") -> "CivicOSConfig":
        """
        Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix (default: "CIVICOS").

        Returns:
            CivicOSConfig instance.

        Environment variables:
            {PREFIX}_JURISDICTION: Jurisdiction ID (required, or default to "city-san-rafael")
            {PREFIX}_DISPLAY_NAME: Display name (optional)
            {PREFIX}_TIMEZONE: Timezone (optional)
            {PREFIX}_DB_PATH: Database path (optional)
            {PREFIX}_FEDERATION_ENABLED: Enable federation (optional, "true"/"false")

        Example:
            CIVICOS_JURISDICTION=city-san-rafael
            CIVICOS_DISPLAY_NAME="San Rafael, CA"
            CIVICOS_TIMEZONE=America/Los_Angeles
        """
        jurisdiction_id = os.getenv(
            f"{prefix}_JURISDICTION",
            os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")
        )

        display_name = os.getenv(f"{prefix}_DISPLAY_NAME")
        timezone = os.getenv(f"{prefix}_TIMEZONE")
        db_path = os.getenv(f"{prefix}_DB_PATH")

        federation_enabled = os.getenv(
            f"{prefix}_FEDERATION_ENABLED", "false"
        ).lower() in ("true", "1", "yes")

        return cls(
            jurisdiction_id=jurisdiction_id,
            display_name=display_name,
            timezone=timezone,
            db_path=db_path,
            federation_enabled=federation_enabled,
        )

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "CivicOSConfig":
        """Create config from dictionary (internal helper)."""
        # Parse peers
        peers = []
        if "peers" in data:
            for peer_data in data["peers"]:
                peers.append(PeerConfig(
                    jurisdiction_id=peer_data["jurisdiction_id"],
                    mcp_endpoint=peer_data["mcp_endpoint"],
                    display_name=peer_data.get("display_name"),
                    enabled=peer_data.get("enabled", True),
                ))

        # Parse extractors
        extractors = {}
        if "extractors" in data:
            for name, ext_data in data["extractors"].items():
                if isinstance(ext_data, dict):
                    extractors[name] = ExtractorConfig(
                        name=name,
                        enabled=ext_data.get("enabled", True),
                        config=ext_data.get("config", {}),
                    )
                elif isinstance(ext_data, bool):
                    # Shorthand: "legistar: false"
                    extractors[name] = ExtractorConfig(
                        name=name,
                        enabled=ext_data,
                    )

        return cls(
            jurisdiction_id=data["jurisdiction_id"],
            display_name=data.get("display_name"),
            timezone=data.get("timezone"),
            db_path=data.get("db_path"),
            peers=peers,
            extractors=extractors,
            federation_enabled=data.get("federation_enabled", False),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary (for serialization)."""
        result = {
            "jurisdiction_id": self.jurisdiction_id,
            "display_name": self.display_name,
            "timezone": self.timezone,
        }

        if self.db_path:
            result["db_path"] = self.db_path

        if self.federation_enabled:
            result["federation_enabled"] = True

        if self.peers:
            result["peers"] = [
                {
                    "jurisdiction_id": p.jurisdiction_id,
                    "mcp_endpoint": p.mcp_endpoint,
                    "display_name": p.display_name,
                    "enabled": p.enabled,
                }
                for p in self.peers
            ]

        if self.extractors:
            result["extractors"] = {
                name: {
                    "enabled": ext.enabled,
                    "config": ext.config,
                }
                for name, ext in self.extractors.items()
            }

        if self.metadata:
            result["metadata"] = self.metadata

        return result

    def to_yaml(self, path: Optional[str] = None) -> str:
        """
        Convert config to YAML string.

        Args:
            path: Optional path to write YAML file.

        Returns:
            YAML string representation.

        Raises:
            ImportError: If PyYAML is not installed.
        """
        if not YAML_AVAILABLE:
            raise ImportError(
                "PyYAML is required for YAML export. "
                "Install with: pip install pyyaml"
            )

        yaml_str = yaml.dump(
            self.to_dict(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        if path:
            Path(path).write_text(yaml_str)
            logger.info(f"Wrote configuration to {path}")

        return yaml_str

    def get_enabled_peers(self) -> List[PeerConfig]:
        """Get list of enabled federation peers."""
        return [p for p in self.peers if p.enabled]

    def get_extractor_config(self, name: str) -> Optional[ExtractorConfig]:
        """Get configuration for a specific extractor."""
        return self.extractors.get(name)

    def is_extractor_enabled(self, name: str) -> bool:
        """Check if an extractor is enabled (default: True if not configured)."""
        ext = self.extractors.get(name)
        return ext.enabled if ext else True

    def validate(self) -> List[str]:
        """
        Validate configuration and return list of issues.

        Returns:
            List of validation issue descriptions. Empty if valid.
        """
        issues = []

        # Check jurisdiction_id is present
        if not self.jurisdiction_id:
            issues.append("jurisdiction_id is required")

        # Validate timezone format (basic check)
        if self.timezone and "/" not in self.timezone and self.timezone != "UTC":
            issues.append(
                f"timezone '{self.timezone}' doesn't look like IANA format "
                "(expected e.g., 'America/Los_Angeles')"
            )

        # Validate peers
        for i, peer in enumerate(self.peers):
            if not peer.jurisdiction_id:
                issues.append(f"peers[{i}].jurisdiction_id is required")
            if not peer.mcp_endpoint:
                issues.append(f"peers[{i}].mcp_endpoint is required")
            elif not peer.mcp_endpoint.startswith(("http://", "https://")):
                issues.append(
                    f"peers[{i}].mcp_endpoint should be a URL "
                    f"(got: {peer.mcp_endpoint})"
                )

        return issues


def load_config(
    path: Optional[str] = None,
    env_prefix: str = "CIVICOS",
) -> CivicOSConfig:
    """
    Load CivicOS configuration with fallback chain.

    Tries sources in order:
    1. Explicit path (if provided)
    2. CIVICOS_CONFIG environment variable (if set)
    3. Default locations: ./civicos.yaml, ./config/civicos.yaml
    4. Environment variables

    Args:
        path: Explicit path to config file (optional).
        env_prefix: Environment variable prefix.

    Returns:
        CivicOSConfig instance.

    Example:
        config = load_config()  # Auto-detect
        config = load_config("my-city.yaml")  # Explicit file
    """
    # 1. Explicit path
    if path and Path(path).exists():
        logger.info(f"Loading config from explicit path: {path}")
        return CivicOSConfig.from_yaml(path)

    # 2. Environment variable pointing to config file
    env_config_path = os.getenv(f"{env_prefix}_CONFIG")
    if env_config_path and Path(env_config_path).exists():
        logger.info(f"Loading config from {env_prefix}_CONFIG: {env_config_path}")
        return CivicOSConfig.from_yaml(env_config_path)

    # 3. Default locations
    default_locations = [
        Path("civicos.yaml"),
        Path("config/civicos.yaml"),
        Path.home() / ".civicos" / "config.yaml",
    ]

    for loc in default_locations:
        if loc.exists():
            logger.info(f"Loading config from default location: {loc}")
            return CivicOSConfig.from_yaml(str(loc))

    # 4. Fall back to environment variables
    logger.debug(f"No config file found, using environment variables with prefix {env_prefix}")
    return CivicOSConfig.from_env(prefix=env_prefix)
