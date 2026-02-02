"""
MCP Registry Router - Discovery endpoint for CivicOS MCP servers.

Provides a public registry of official CivicOS-approved MCP server endpoints,
enabling clients to discover available civic data sources.
"""

import os
import json
import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


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
