"""Relay configuration models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PeerConfig(BaseModel):
    """Configuration for a peer relay."""

    url: str = Field(description="Base URL of the peer relay")
    namespaces: list[str] = Field(
        description="Entity namespaces to sync (e.g., 'city-san-rafael:*')"
    )
    sync_interval: int = Field(
        default=300, description="Seconds between sync attempts"
    )
    public_key: Optional[str] = Field(
        default=None, description="Peer's public key for signature verification"
    )
    enabled: bool = Field(default=True)

    # Health tracking (runtime state, not persisted in YAML)
    healthy: bool = Field(default=True, description="Current health status")
    consecutive_failures: int = Field(
        default=0, description="Consecutive failed health checks"
    )
    last_health_check: Optional[datetime] = Field(
        default=None, description="Timestamp of last health check"
    )
    last_successful_sync: Optional[datetime] = Field(
        default=None, description="Timestamp of last successful sync"
    )


class RelayConfig(BaseModel):
    """Configuration for a relay instance."""

    relay_id: str = Field(
        description="Unique identifier for this relay (e.g., 'relay.civicos.org/san-rafael')"
    )
    private_key_path: Optional[str] = Field(
        default=None, description="Path to relay private key PEM file"
    )
    namespaces: list[str] = Field(
        default_factory=list,
        description="Entity namespaces this relay hosts (e.g., 'city-san-rafael:*')",
    )
    peers: list[PeerConfig] = Field(
        default_factory=list, description="Peer relays to sync with"
    )

    # Server settings
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8003)

    # Database
    database_url: Optional[str] = Field(default=None)

    # Sync settings
    sync_enabled: bool = Field(default=True)
    sync_batch_size: int = Field(default=100)

    # Health check settings
    health_check_timeout: int = Field(
        default=10, description="Timeout in seconds for health checks"
    )
    health_check_interval: int = Field(
        default=60, description="Seconds between health checks"
    )
    max_consecutive_failures: int = Field(
        default=3, description="Failures before marking peer unhealthy"
    )

    @classmethod
    def from_env(cls) -> "RelayConfig":
        """Load configuration from environment variables."""
        import os

        peers = []
        # Parse RELAY_PEERS as comma-separated URLs (simple format for env)
        peers_str = os.environ.get("RELAY_PEERS", "")
        if peers_str:
            for url in peers_str.split(","):
                url = url.strip()
                if url:
                    peers.append(PeerConfig(url=url, namespaces=["*"]))

        return cls(
            relay_id=os.environ.get("RELAY_ID", "relay.local"),
            private_key_path=os.environ.get("RELAY_PRIVATE_KEY_PATH"),
            namespaces=os.environ.get("RELAY_NAMESPACES", "*").split(","),
            peers=peers,
            host=os.environ.get("RELAY_HOST", "0.0.0.0"),
            port=int(os.environ.get("RELAY_PORT", "8003")),
            database_url=os.environ.get("DATABASE_URL"),
            sync_enabled=os.environ.get("RELAY_SYNC_ENABLED", "true").lower() == "true",
        )

    @classmethod
    def from_yaml(cls, path: str) -> "RelayConfig":
        """Load configuration from YAML file."""
        import yaml
        from pathlib import Path

        with open(Path(path)) as f:
            data = yaml.safe_load(f)

        relay_data = data.get("relay", data)
        return cls(**relay_data)
