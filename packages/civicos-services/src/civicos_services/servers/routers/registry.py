"""
MCP Registry Router - Discovery endpoint for CivicOS MCP servers.

Provides:
1. Public registry of official CivicOS-approved MCP server endpoints
2. Internal registry for CivicOS platform discovery, health aggregation, and capability introspection

Public endpoints (for external clients):
- GET /api/mcp/registry - Full public registry
- GET /api/mcp/registry/operators/{id} - Single operator details
- GET /api/mcp/registry/jurisdictions/{jid}/operators - Operators by jurisdiction

Internal endpoints (for CivicOS platform):
- GET /api/mcp/internal/servers - All active CivicOS MCP servers
- GET /api/mcp/internal/servers/{jurisdiction_id} - Server details + capabilities
- GET /api/mcp/internal/health - Aggregated health across all servers
- GET /api/mcp/internal/tools - All tools with jurisdiction mapping
"""

import asyncio
import os
import json
import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import jurisdiction config for internal registry
try:
    from civicos.jurisdiction_config import get_active_jurisdictions, load_jurisdiction_config
    JURISDICTION_CONFIG_AVAILABLE = True
except ImportError:
    JURISDICTION_CONFIG_AVAILABLE = False
    get_active_jurisdictions = None
    load_jurisdiction_config = None


router = APIRouter()


# === Pydantic Models ===

class OperatorLocation(BaseModel):
    """Geographic location of an operator."""
    city: str
    county: Optional[str] = None
    state: str


class OperatorContact(BaseModel):
    """Contact information for an operator."""
    organization: str
    url: Optional[str] = None
    email: Optional[str] = None


class OperatorHealth(BaseModel):
    """Health status of an operator's MCP endpoint."""
    status: str  # healthy, unhealthy, unknown
    tools_count: Optional[int] = None
    checked_at: str
    response_time_ms: Optional[int] = None


class MCPOperator(BaseModel):
    """An MCP server operator in the registry."""
    id: str
    jurisdiction_id: str
    name: str
    description: Optional[str] = None
    mcp_endpoint: str
    type: str  # official, community, experimental
    status: str  # active, inactive, deprecated
    authoritative_for: List[str] = []
    tools_count: Optional[int] = None
    location: Optional[OperatorLocation] = None
    contact: Optional[OperatorContact] = None
    health: Optional[OperatorHealth] = None


class RegistryMetadata(BaseModel):
    """Metadata about the registry."""
    protocol_version: str
    documentation_url: Optional[str] = None
    github_url: Optional[str] = None


class MCPRegistry(BaseModel):
    """The full MCP server registry."""
    version: str
    updated: str
    registry_url: Optional[str] = None
    operators: List[MCPOperator]
    metadata: Optional[RegistryMetadata] = None


# === Internal Registry Models ===


class InternalServerHealth(BaseModel):
    """Health status from an MCP server's /health endpoint."""
    status: str  # healthy, unhealthy, unknown
    tools_count: Optional[int] = None
    tools: Optional[List[str]] = None
    checked_at: str
    response_time_ms: Optional[int] = None
    jurisdiction_level: Optional[str] = None
    display_name: Optional[str] = None


class InternalMCPServer(BaseModel):
    """An MCP server in the internal registry."""
    jurisdiction_id: str
    level: str  # federal, state, county, city
    display_name: str
    mcp_endpoint: str
    health_endpoint: str
    parent_jurisdictions: List[str] = []
    health: Optional[InternalServerHealth] = None


class InternalRegistryResponse(BaseModel):
    """Response from internal servers list."""
    version: str = "1.0.0"
    updated: str
    total_servers: int
    servers: List[InternalMCPServer]


class AggregatedHealth(BaseModel):
    """Aggregated health across all servers."""
    updated: str
    total_servers: int
    healthy: int
    unhealthy: int
    unknown: int
    total_tools: int
    servers: Dict[str, InternalServerHealth]


class ToolInfo(BaseModel):
    """Information about a tool across jurisdictions."""
    name: str
    available_at: List[str]  # jurisdiction_ids
    levels: List[str]  # jurisdiction levels where available


class ToolsResponse(BaseModel):
    """Response from tools introspection endpoint."""
    updated: str
    total_tools: int
    tools: List[ToolInfo]


# === Registry Data ===

# Default registry data - can be overridden by environment or external file
DEFAULT_REGISTRY = {
    "version": "1.0.0",
    "updated": "2026-02-02T00:00:00Z",
    "registry_url": "https://civicosproject.org/mcp/registry",
    "operators": [
        {
            "id": "civicos-san-rafael",
            "jurisdiction_id": "city-san-rafael",
            "name": "San Rafael",
            "description": "City of San Rafael civic data - meetings, decisions, budget, issues",
            "mcp_endpoint": "https://san-rafael.civicosproject.org/mcp",
            "type": "official",
            "status": "active",
            "authoritative_for": ["meetings", "decisions", "budget", "issues", "municipal_code"],
            "tools_count": 30,
            "location": {
                "city": "San Rafael",
                "county": "Marin",
                "state": "CA"
            },
            "contact": {
                "organization": "CivicOS Project",
                "url": "https://civicosproject.org"
            }
        }
    ],
    "metadata": {
        "protocol_version": "2024-11-05",
        "documentation_url": "https://civicosproject.org/docs/mcp",
        "github_url": "https://github.com/civicosproject/civicos"
    }
}


def load_registry_data() -> dict:
    """
    Load registry data from file or return default.

    Checks for:
    1. CIVICOS_MCP_REGISTRY_FILE environment variable
    2. apps/civicos-mcp/registry_data.json
    3. Falls back to DEFAULT_REGISTRY
    """
    # Check environment variable first
    registry_file = os.getenv("CIVICOS_MCP_REGISTRY_FILE")

    if not registry_file:
        # Try default location relative to project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )))
        registry_file = os.path.join(project_root, "apps", "civicos-mcp", "registry_data.json")

    if registry_file and os.path.exists(registry_file):
        try:
            with open(registry_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    return DEFAULT_REGISTRY


async def check_operator_health(endpoint: str, timeout: float = 5.0) -> OperatorHealth:
    """
    Check the health of an MCP operator endpoint.

    Makes a GET request to /health and measures response time.
    """
    start = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{endpoint.rstrip('/mcp')}/health")
            response_time = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                return OperatorHealth(
                    status="healthy",
                    tools_count=data.get("tools_count"),
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    response_time_ms=response_time
                )
            else:
                return OperatorHealth(
                    status="unhealthy",
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    response_time_ms=response_time
                )
    except Exception:
        return OperatorHealth(
            status="unknown",
            checked_at=datetime.now(timezone.utc).isoformat()
        )


# === Internal Registry Helpers ===


def _build_mcp_endpoint(jurisdiction_id: str) -> str:
    """
    Build MCP endpoint URL from jurisdiction ID.

    URL scheme: {jurisdiction-slug}.civicosproject.org/mcp

    Examples:
        city-san-rafael -> san-rafael.civicosproject.org/mcp
        state-california -> california.civicosproject.org/mcp
        country-united-states -> federal.civicosproject.org/mcp
    """
    # Special case for federal
    if jurisdiction_id == "country-united-states":
        return "https://federal.civicosproject.org/mcp"

    # Remove level prefix (city-, state-, county-)
    for prefix in ["city-", "state-", "county-", "country-"]:
        if jurisdiction_id.startswith(prefix):
            slug = jurisdiction_id[len(prefix):]
            return f"https://{slug}.civicosproject.org/mcp"

    # Fallback: use as-is
    return f"https://{jurisdiction_id}.civicosproject.org/mcp"


def _get_internal_servers() -> List[InternalMCPServer]:
    """
    Get all CivicOS MCP servers from jurisdiction configs.

    Uses get_active_jurisdictions() as source of truth.
    """
    if not JURISDICTION_CONFIG_AVAILABLE:
        return []

    servers = []
    for jid, config in get_active_jurisdictions().items():
        mcp_endpoint = _build_mcp_endpoint(jid)
        health_endpoint = mcp_endpoint.replace("/mcp", "/health")

        servers.append(InternalMCPServer(
            jurisdiction_id=jid,
            level=config.level,
            display_name=config.display_name,
            mcp_endpoint=mcp_endpoint,
            health_endpoint=health_endpoint,
            parent_jurisdictions=config.parent_jurisdictions,
        ))

    # Sort by level (federal, state, county, city) then by name
    level_order = {"federal": 0, "state": 1, "county": 2, "city": 3}
    servers.sort(key=lambda s: (level_order.get(s.level, 99), s.display_name))

    return servers


async def check_internal_server_health(
    jurisdiction_id: str,
    endpoint: str,
    timeout: float = 10.0
) -> InternalServerHealth:
    """
    Check health of an internal MCP server.

    Uses longer timeout (10s) to account for cold starts on Modal.
    Returns full health info including tools list.
    """
    start = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(endpoint)
            response_time = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

            if response.status_code == 200:
                data = response.json()
                return InternalServerHealth(
                    status="healthy",
                    tools_count=data.get("tools_count"),
                    tools=data.get("tools", []),
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    response_time_ms=response_time,
                    jurisdiction_level=data.get("jurisdiction_level"),
                    display_name=data.get("display_name"),
                )
            else:
                return InternalServerHealth(
                    status="unhealthy",
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    response_time_ms=response_time,
                )
    except Exception:
        return InternalServerHealth(
            status="unknown",
            checked_at=datetime.now(timezone.utc).isoformat(),
        )


# === Endpoints ===

@router.get("/mcp/registry", response_model=MCPRegistry)
async def get_mcp_registry(check_health: bool = False):
    """
    Get the CivicOS MCP Server Registry.

    Returns the official registry of CivicOS-approved MCP servers.
    Clients can use this to discover available MCP endpoints for civic data.

    Query Parameters:
        check_health: If true, performs live health checks on each operator (slower)

    Example usage:
        GET /api/mcp/registry
        GET /api/mcp/registry?check_health=true
    """
    registry_data = load_registry_data()

    # Optionally check health of each operator
    if check_health:
        for operator in registry_data.get("operators", []):
            endpoint = operator.get("mcp_endpoint", "")
            if endpoint:
                health = await check_operator_health(endpoint)
                operator["health"] = health.model_dump()

    # Update timestamp
    registry_data["updated"] = datetime.now(timezone.utc).isoformat()

    return registry_data


@router.get("/mcp/registry/operators/{operator_id}", response_model=MCPOperator)
async def get_operator(operator_id: str, check_health: bool = True):
    """
    Get a specific MCP operator by ID.

    Returns detailed information about a single operator including
    live health status by default.
    """
    registry_data = load_registry_data()

    for operator in registry_data.get("operators", []):
        if operator.get("id") == operator_id:
            # Check health by default for single operator queries
            if check_health:
                endpoint = operator.get("mcp_endpoint", "")
                if endpoint:
                    health = await check_operator_health(endpoint)
                    operator["health"] = health.model_dump()
            return operator

    raise HTTPException(status_code=404, detail=f"Operator '{operator_id}' not found")


@router.get("/mcp/registry/jurisdictions/{jurisdiction_id}/operators")
async def get_operators_by_jurisdiction(jurisdiction_id: str) -> List[MCPOperator]:
    """
    Get all MCP operators for a specific jurisdiction.

    Useful when multiple operators serve the same jurisdiction
    (e.g., official city server + community-run server).
    """
    registry_data = load_registry_data()

    operators = [
        op for op in registry_data.get("operators", [])
        if op.get("jurisdiction_id") == jurisdiction_id
    ]

    if not operators:
        raise HTTPException(
            status_code=404,
            detail=f"No operators found for jurisdiction '{jurisdiction_id}'"
        )

    return operators


# === Internal Registry Endpoints ===


@router.get("/mcp/internal/servers", response_model=InternalRegistryResponse)
async def get_internal_servers(check_health: bool = False):
    """
    Get all active CivicOS MCP servers.

    Returns servers discovered from jurisdiction configuration files.
    This is the internal registry used by the CivicOS platform for:
    - Multi-jurisdiction discovery
    - UX development against stable interface
    - Federation patterns

    Query Parameters:
        check_health: If true, performs live health checks (slower, ~10s per server)

    Example:
        GET /api/mcp/internal/servers
        GET /api/mcp/internal/servers?check_health=true
    """
    if not JURISDICTION_CONFIG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Jurisdiction configuration module not available"
        )

    servers = _get_internal_servers()

    if check_health:
        # Parallel health checks with 10s timeout per server
        health_tasks = [
            check_internal_server_health(s.jurisdiction_id, s.health_endpoint)
            for s in servers
        ]
        health_results = await asyncio.gather(*health_tasks)

        for server, health in zip(servers, health_results):
            server.health = health

    return InternalRegistryResponse(
        updated=datetime.now(timezone.utc).isoformat(),
        total_servers=len(servers),
        servers=servers,
    )


@router.get("/mcp/internal/servers/{jurisdiction_id}", response_model=InternalMCPServer)
async def get_internal_server(jurisdiction_id: str, check_health: bool = True):
    """
    Get details for a specific CivicOS MCP server.

    Returns server info including live health check by default.
    """
    if not JURISDICTION_CONFIG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Jurisdiction configuration module not available"
        )

    servers = _get_internal_servers()
    server = next((s for s in servers if s.jurisdiction_id == jurisdiction_id), None)

    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"Server not found for jurisdiction '{jurisdiction_id}'"
        )

    if check_health:
        server.health = await check_internal_server_health(
            server.jurisdiction_id,
            server.health_endpoint
        )

    return server


@router.get("/mcp/internal/health", response_model=AggregatedHealth)
async def get_aggregated_health():
    """
    Get aggregated health status across all CivicOS MCP servers.

    Performs parallel health checks on all servers and returns:
    - Count of healthy/unhealthy/unknown servers
    - Total tools across all servers
    - Per-server health details

    Useful for monitoring dashboards and status pages.
    """
    if not JURISDICTION_CONFIG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Jurisdiction configuration module not available"
        )

    servers = _get_internal_servers()

    # Parallel health checks
    health_tasks = [
        check_internal_server_health(s.jurisdiction_id, s.health_endpoint)
        for s in servers
    ]
    health_results = await asyncio.gather(*health_tasks)

    # Aggregate results
    healthy = 0
    unhealthy = 0
    unknown = 0
    total_tools = 0
    server_health: Dict[str, InternalServerHealth] = {}

    for server, health in zip(servers, health_results):
        server_health[server.jurisdiction_id] = health
        if health.status == "healthy":
            healthy += 1
            total_tools += health.tools_count or 0
        elif health.status == "unhealthy":
            unhealthy += 1
        else:
            unknown += 1

    return AggregatedHealth(
        updated=datetime.now(timezone.utc).isoformat(),
        total_servers=len(servers),
        healthy=healthy,
        unhealthy=unhealthy,
        unknown=unknown,
        total_tools=total_tools,
        servers=server_health,
    )


@router.get("/mcp/internal/tools", response_model=ToolsResponse)
async def get_tools_across_servers():
    """
    Get all tools available across CivicOS MCP servers.

    Performs health checks to discover tools, then deduplicates and maps
    each tool to the jurisdictions where it's available.

    Useful for:
    - Capability introspection
    - Tool discovery across multi-jurisdiction deployments
    - Federation planning

    Note: This endpoint is slower as it performs health checks on all servers.
    """
    if not JURISDICTION_CONFIG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Jurisdiction configuration module not available"
        )

    servers = _get_internal_servers()

    # Parallel health checks to get tools
    health_tasks = [
        check_internal_server_health(s.jurisdiction_id, s.health_endpoint)
        for s in servers
    ]
    health_results = await asyncio.gather(*health_tasks)

    # Build tool -> jurisdictions mapping
    tool_map: Dict[str, Dict[str, Any]] = {}

    for server, health in zip(servers, health_results):
        if health.status == "healthy" and health.tools:
            for tool_name in health.tools:
                if tool_name not in tool_map:
                    tool_map[tool_name] = {
                        "available_at": [],
                        "levels": set(),
                    }
                tool_map[tool_name]["available_at"].append(server.jurisdiction_id)
                tool_map[tool_name]["levels"].add(server.level)

    # Convert to response format
    tools = [
        ToolInfo(
            name=name,
            available_at=sorted(info["available_at"]),
            levels=sorted(info["levels"]),
        )
        for name, info in sorted(tool_map.items())
    ]

    return ToolsResponse(
        updated=datetime.now(timezone.utc).isoformat(),
        total_tools=len(tools),
        tools=tools,
    )
