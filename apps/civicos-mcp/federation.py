"""
MCP Peer Registry for CivicOS Federation.

Enables discovery and health checking of peer MCP servers across jurisdictions.
This is the glue component that allows one CivicOS MCP instance to discover
and communicate with peer instances serving other cities.

Architecture:
    - PeerRegistry manages known peers and their health status
    - PeerInfo stores metadata about each peer
    - Health checks validate peer availability via MCP endpoint pings
    - Configuration loaded from environment or file

Usage:
    registry = await PeerRegistry.from_env()

    # Get peer for cross-jurisdiction query
    peer = registry.get_peer("city-berkeley")
    if peer and peer.is_healthy:
        # Forward query to peer MCP endpoint
        ...

    # Background health checks
    await registry.refresh_all()
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Information about a peer MCP server."""

    jurisdiction_id: str  # e.g., "city-berkeley"
    mcp_endpoint: str     # e.g., "https://berkeley.civicos.org/mcp"
    last_seen: Optional[datetime] = None
    is_healthy: bool = False
    last_error: Optional[str] = None
    consecutive_failures: int = 0

    def mark_healthy(self) -> None:
        """Mark peer as healthy after successful check."""
        self.is_healthy = True
        self.last_seen = datetime.now(timezone.utc)
        self.last_error = None
        self.consecutive_failures = 0

    def mark_unhealthy(self, error: str) -> None:
        """Mark peer as unhealthy after failed check."""
        self.is_healthy = False
        self.last_error = error
        self.consecutive_failures += 1

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "mcp_endpoint": self.mcp_endpoint,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "is_healthy": self.is_healthy,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
        }


@runtime_checkable
class HealthChecker(Protocol):
    """Protocol for health checking implementations."""

    async def check(self, endpoint: str) -> tuple[bool, Optional[str]]:
        """Check if endpoint is healthy. Returns (is_healthy, error_message)."""
        ...


class HttpHealthChecker:
    """HTTP-based health checker for MCP endpoints."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def check(self, endpoint: str) -> tuple[bool, Optional[str]]:
        """
        Check if MCP endpoint is reachable.

        Uses a simple GET request to the endpoint root.
        MCP servers typically respond with server info or a redirect.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Try to hit the endpoint - MCP servers respond to GET
                response = await client.get(endpoint, follow_redirects=True)

                # Accept any successful response (2xx, 3xx)
                if response.status_code < 400:
                    return (True, None)
                else:
                    return (False, f"HTTP {response.status_code}")

        except httpx.TimeoutException:
            return (False, "Timeout")
        except httpx.ConnectError as e:
            return (False, f"Connection error: {str(e)[:50]}")
        except Exception as e:
            return (False, f"Error: {str(e)[:50]}")


class PeerRegistry:
    """
    Registry of peer MCP servers for federation.

    Manages peer discovery, health checking, and status tracking.
    Peers are identified by jurisdiction_id (e.g., "city-berkeley").
    """

    def __init__(
        self,
        health_checker: Optional[HealthChecker] = None,
        health_check_interval: float = 300.0,  # 5 minutes
        unhealthy_threshold: int = 3,  # Mark unhealthy after 3 failures
    ):
        self._peers: Dict[str, PeerInfo] = {}
        self._health_checker = health_checker or HttpHealthChecker()
        self._health_check_interval = health_check_interval
        self._unhealthy_threshold = unhealthy_threshold
        self._running = False
        self._background_task: Optional[asyncio.Task] = None

    def add_peer(self, jurisdiction_id: str, mcp_endpoint: str) -> PeerInfo:
        """Add a peer to the registry."""
        peer = PeerInfo(jurisdiction_id=jurisdiction_id, mcp_endpoint=mcp_endpoint)
        self._peers[jurisdiction_id] = peer
        logger.info(f"Added peer: {jurisdiction_id} -> {mcp_endpoint}")
        return peer

    def remove_peer(self, jurisdiction_id: str) -> bool:
        """Remove a peer from the registry."""
        if jurisdiction_id in self._peers:
            del self._peers[jurisdiction_id]
            logger.info(f"Removed peer: {jurisdiction_id}")
            return True
        return False

    def get_peer(self, jurisdiction_id: str) -> Optional[PeerInfo]:
        """Get peer info for a jurisdiction."""
        return self._peers.get(jurisdiction_id)

    def list_peers(self, healthy_only: bool = False) -> List[PeerInfo]:
        """List all known peers, optionally filtering to healthy ones."""
        peers = list(self._peers.values())
        if healthy_only:
            peers = [p for p in peers if p.is_healthy]
        return peers

    def list_jurisdictions(self, healthy_only: bool = False) -> List[str]:
        """List jurisdiction IDs of all known peers."""
        return [p.jurisdiction_id for p in self.list_peers(healthy_only=healthy_only)]

    async def health_check(self, jurisdiction_id: str) -> bool:
        """
        Check if a specific peer is reachable.

        Updates the peer's health status in the registry.
        Returns True if peer is healthy, False otherwise.
        """
        peer = self._peers.get(jurisdiction_id)
        if not peer:
            logger.warning(f"Unknown peer: {jurisdiction_id}")
            return False

        is_healthy, error = await self._health_checker.check(peer.mcp_endpoint)

        if is_healthy:
            peer.mark_healthy()
            logger.debug(f"Peer healthy: {jurisdiction_id}")
        else:
            peer.mark_unhealthy(error or "Unknown error")
            logger.warning(f"Peer unhealthy: {jurisdiction_id} - {error}")

        return is_healthy

    async def refresh_all(self) -> Dict[str, bool]:
        """
        Update health status for all peers.

        Returns dict of jurisdiction_id -> is_healthy.
        """
        results = {}

        # Check all peers concurrently
        tasks = [
            self.health_check(jurisdiction_id)
            for jurisdiction_id in self._peers.keys()
        ]

        if tasks:
            health_results = await asyncio.gather(*tasks, return_exceptions=True)

            for jurisdiction_id, result in zip(self._peers.keys(), health_results):
                if isinstance(result, Exception):
                    results[jurisdiction_id] = False
                    logger.error(f"Health check exception for {jurisdiction_id}: {result}")
                else:
                    results[jurisdiction_id] = result

        healthy_count = sum(1 for v in results.values() if v)
        logger.info(f"Health refresh complete: {healthy_count}/{len(results)} peers healthy")

        return results

    async def start_background_checks(self) -> None:
        """Start periodic background health checks."""
        if self._running:
            return

        self._running = True
        self._background_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"Started background health checks (interval: {self._health_check_interval}s)")

    async def stop_background_checks(self) -> None:
        """Stop periodic background health checks."""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        logger.info("Stopped background health checks")

    async def _health_check_loop(self) -> None:
        """Background loop for periodic health checks."""
        while self._running:
            try:
                await self.refresh_all()
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

            await asyncio.sleep(self._health_check_interval)

    def summary(self) -> dict:
        """Get registry summary for diagnostics."""
        peers = self.list_peers()
        healthy = [p for p in peers if p.is_healthy]

        return {
            "total_peers": len(peers),
            "healthy_peers": len(healthy),
            "unhealthy_peers": len(peers) - len(healthy),
            "peers": [p.to_dict() for p in peers],
        }

    # Factory methods

    @classmethod
    def from_config(cls, peers_config: List[dict], **kwargs) -> "PeerRegistry":
        """
        Create registry from a list of peer configurations.

        Each peer config should have:
            - jurisdiction_id: str
            - mcp_endpoint: str
        """
        registry = cls(**kwargs)

        for peer_config in peers_config:
            jurisdiction_id = peer_config.get("jurisdiction_id")
            mcp_endpoint = peer_config.get("mcp_endpoint")

            if jurisdiction_id and mcp_endpoint:
                registry.add_peer(jurisdiction_id, mcp_endpoint)
            else:
                logger.warning(f"Invalid peer config (missing fields): {peer_config}")

        return registry

    @classmethod
    def from_env(cls, **kwargs) -> "PeerRegistry":
        """
        Create registry from environment variables.

        Environment variables:
            CIVICOS_PEERS: Comma-separated list of "jurisdiction_id:endpoint" pairs
                Example: "city-berkeley:https://berkeley.civicos.org/mcp,city-oakland:https://oakland.civicos.org/mcp"

            CIVICOS_PEER_CHECK_INTERVAL: Health check interval in seconds (default: 300)
        """
        registry = cls(**kwargs)

        # Parse CIVICOS_PEERS
        peers_str = os.environ.get("CIVICOS_PEERS", "")
        if peers_str:
            for peer_spec in peers_str.split(","):
                peer_spec = peer_spec.strip()
                if ":" in peer_spec:
                    # Format: "jurisdiction_id:endpoint"
                    # Need to handle the endpoint having colons (https://)
                    parts = peer_spec.split(":", 1)
                    if len(parts) == 2:
                        jurisdiction_id = parts[0].strip()
                        # The endpoint has the rest
                        mcp_endpoint = parts[1].strip()
                        # Handle case where jurisdiction_id got the https
                        if jurisdiction_id.startswith("https"):
                            # Wrong format - try to extract from URL
                            logger.warning(f"Invalid peer spec format: {peer_spec}")
                            continue
                        if jurisdiction_id and mcp_endpoint:
                            registry.add_peer(jurisdiction_id, mcp_endpoint)

        # Override health check interval from env
        interval_str = os.environ.get("CIVICOS_PEER_CHECK_INTERVAL")
        if interval_str:
            try:
                registry._health_check_interval = float(interval_str)
            except ValueError:
                logger.warning(f"Invalid CIVICOS_PEER_CHECK_INTERVAL: {interval_str}")

        return registry

    @classmethod
    def from_yaml(cls, path: str, **kwargs) -> "PeerRegistry":
        """
        Create registry from YAML configuration file.

        Expected format:
            peers:
              - jurisdiction_id: city-berkeley
                mcp_endpoint: https://berkeley.civicos.org/mcp
              - jurisdiction_id: city-oakland
                mcp_endpoint: https://oakland.civicos.org/mcp
        """
        import yaml

        with open(Path(path)) as f:
            data = yaml.safe_load(f)

        peers_config = data.get("peers", [])
        return cls.from_config(peers_config, **kwargs)


# Singleton instance for the MCP server
_registry: Optional[PeerRegistry] = None


def get_registry() -> Optional[PeerRegistry]:
    """Get the global peer registry instance."""
    return _registry


async def init_registry(**kwargs) -> PeerRegistry:
    """
    Initialize the global peer registry.

    Loads configuration from environment and performs initial health check.
    """
    global _registry

    _registry = PeerRegistry.from_env(**kwargs)

    # Initial health check if we have peers
    if _registry.list_peers():
        await _registry.refresh_all()

    return _registry


async def shutdown_registry() -> None:
    """Shutdown the global peer registry."""
    global _registry

    if _registry:
        await _registry.stop_background_checks()
        _registry = None


# Query Routing Functions


@dataclass
class PeerQueryResult:
    """Result from a single peer query."""

    jurisdiction_id: str
    success: bool
    data: Optional[dict] = None  # Parsed JSON response
    raw_response: Optional[str] = None  # Raw text if not JSON
    error: Optional[str] = None
    latency_ms: float = 0.0


@dataclass
class FederatedQueryResult:
    """Aggregated results from federated query across peers."""

    local_jurisdiction: str
    local_results: list  # Results from local CivicOS
    peer_results: Dict[str, PeerQueryResult]  # jurisdiction_id -> result
    total_peers_queried: int
    successful_peers: int
    failed_peers: int
    total_latency_ms: float

    def all_results(self) -> list:
        """Get all results (local + successful peers) as flat list."""
        results = []

        # Local results first (highest priority)
        for item in self.local_results:
            if isinstance(item, dict):
                item["_source_jurisdiction"] = self.local_jurisdiction
            results.append(item)

        # Peer results
        for jurisdiction_id, peer_result in self.peer_results.items():
            if peer_result.success and peer_result.data:
                items = peer_result.data if isinstance(peer_result.data, list) else [peer_result.data]
                for item in items:
                    if isinstance(item, dict):
                        item["_source_jurisdiction"] = jurisdiction_id
                    results.append(item)

        return results


async def query_peer(
    peer: PeerInfo,
    tool_name: str,
    tool_args: dict,
    timeout: float = 10.0,
) -> PeerQueryResult:
    """
    Query a single peer MCP server.

    Sends an HTTP POST to the peer's MCP endpoint to invoke a tool.
    This simulates an MCP tool call via HTTP (for peer-to-peer communication).

    Args:
        peer: PeerInfo for the target peer
        tool_name: Name of the tool to invoke
        tool_args: Arguments to pass to the tool
        timeout: Request timeout in seconds

    Returns:
        PeerQueryResult with success/failure and data
    """
    import time

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # POST to peer's federation query endpoint
            # Format: POST /federation/query with JSON body
            response = await client.post(
                f"{peer.mcp_endpoint}/federation/query",
                json={
                    "tool": tool_name,
                    "args": tool_args,
                },
            )

            latency = (time.time() - start_time) * 1000

            if response.status_code >= 400:
                return PeerQueryResult(
                    jurisdiction_id=peer.jurisdiction_id,
                    success=False,
                    error=f"HTTP {response.status_code}",
                    latency_ms=latency,
                )

            # Try to parse JSON response
            try:
                data = response.json()
                return PeerQueryResult(
                    jurisdiction_id=peer.jurisdiction_id,
                    success=True,
                    data=data,
                    latency_ms=latency,
                )
            except Exception:
                # Return raw text if not JSON
                return PeerQueryResult(
                    jurisdiction_id=peer.jurisdiction_id,
                    success=True,
                    raw_response=response.text,
                    latency_ms=latency,
                )

    except httpx.TimeoutException:
        latency = (time.time() - start_time) * 1000
        return PeerQueryResult(
            jurisdiction_id=peer.jurisdiction_id,
            success=False,
            error="Timeout",
            latency_ms=latency,
        )
    except httpx.ConnectError as e:
        latency = (time.time() - start_time) * 1000
        return PeerQueryResult(
            jurisdiction_id=peer.jurisdiction_id,
            success=False,
            error=f"Connection error: {str(e)[:50]}",
            latency_ms=latency,
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        logger.warning(f"Peer query failed for {peer.jurisdiction_id}: {e}")
        return PeerQueryResult(
            jurisdiction_id=peer.jurisdiction_id,
            success=False,
            error=f"Error: {str(e)[:50]}",
            latency_ms=latency,
        )


async def query_peers_parallel(
    tool_name: str,
    tool_args: dict,
    registry: Optional[PeerRegistry] = None,
    timeout: float = 10.0,
    healthy_only: bool = True,
) -> Dict[str, PeerQueryResult]:
    """
    Query all peers in parallel.

    Sends the same tool call to all (healthy) peers concurrently and
    collects results. Failed peers are logged but don't fail the operation.

    Args:
        tool_name: Name of the tool to invoke on peers
        tool_args: Arguments to pass to the tool
        registry: PeerRegistry instance (uses global if not provided)
        timeout: Per-peer timeout in seconds
        healthy_only: If True, only query healthy peers

    Returns:
        Dict mapping jurisdiction_id -> PeerQueryResult
    """
    if registry is None:
        registry = get_registry()

    if registry is None:
        logger.debug("No peer registry configured, skipping federated query")
        return {}

    peers = registry.list_peers(healthy_only=healthy_only)
    if not peers:
        logger.debug("No peers available for federated query")
        return {}

    logger.info(f"Querying {len(peers)} peers for {tool_name}")

    # Query all peers concurrently
    tasks = [
        query_peer(peer, tool_name, tool_args, timeout)
        for peer in peers
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Build results dict
    peer_results: Dict[str, PeerQueryResult] = {}
    for peer, result in zip(peers, results):
        if isinstance(result, Exception):
            peer_results[peer.jurisdiction_id] = PeerQueryResult(
                jurisdiction_id=peer.jurisdiction_id,
                success=False,
                error=f"Exception: {str(result)[:50]}",
            )
        else:
            peer_results[peer.jurisdiction_id] = result

    successful = sum(1 for r in peer_results.values() if r.success)
    logger.info(f"Federated query complete: {successful}/{len(peers)} peers succeeded")

    return peer_results


def deduplicate_by_id(
    items: list,
    id_field: str = "id",
) -> list:
    """
    Deduplicate items by ID, keeping first occurrence.

    Items are expected to be dicts with an ID field.
    Items without the ID field are kept as-is.

    Args:
        items: List of items (dicts)
        id_field: Field name to use for deduplication

    Returns:
        Deduplicated list preserving order
    """
    seen_ids = set()
    result = []

    for item in items:
        if not isinstance(item, dict):
            result.append(item)
            continue

        item_id = item.get(id_field)
        if item_id is None:
            # No ID, keep it
            result.append(item)
        elif item_id not in seen_ids:
            seen_ids.add(item_id)
            result.append(item)
        # else: duplicate, skip

    return result


def format_federation_summary(
    local_jurisdiction: str,
    peer_results: Dict[str, PeerQueryResult],
) -> str:
    """
    Format a summary line for federated query results.

    Returns a string like:
    "🏛️ **Jurisdictions:** san-rafael (local) + berkeley, oakland (2 peers)"
    """
    if not peer_results:
        return f"🏛️ **Jurisdiction:** {local_jurisdiction}"

    successful = [jid for jid, r in peer_results.items() if r.success]
    failed = [jid for jid, r in peer_results.items() if not r.success]

    parts = [f"🏛️ **Jurisdictions:** {local_jurisdiction} (local)"]

    if successful:
        parts.append(f" + {', '.join(successful)} ({len(successful)} peers)")

    if failed:
        parts.append(f" ⚠️ {len(failed)} peers failed: {', '.join(failed)}")

    return "".join(parts)
