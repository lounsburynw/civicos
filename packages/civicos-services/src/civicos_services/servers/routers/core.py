"""
Core router: health, status, jurisdictions, config, help.

Public endpoints (no auth required):
- GET /health - Basic health check
- GET /api/status - Detailed status with system checks
- GET /api/config/google-maps-key - Frontend config
- GET /help - API documentation
- GET /api/onboarding/cards - Onboarding cards

Authenticated endpoints:
- GET /api/jurisdictions - List jurisdictions with counts
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...core.config import config


router = APIRouter()


# === Pydantic Models ===

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str


class StatusCheck(BaseModel):
    """Individual status check."""
    status: str
    message: Optional[str] = None


class StatusResponse(BaseModel):
    """Detailed status response."""
    status: str
    timestamp: str
    version: str
    checks: Dict[str, Any]
    endpoints: Optional[Dict[str, List[str]]] = None
    authentication: Optional[str] = None


class Jurisdiction(BaseModel):
    """Jurisdiction info."""
    id: str
    name: str
    type: str
    event_count: int
    issue_count: int
    cdbg_allocation: str
    population: Optional[int] = None
    timezone: str = "America/Los_Angeles"


class JurisdictionsResponse(BaseModel):
    """Jurisdictions list response."""
    jurisdictions: List[Jurisdiction]
    total: int


class GoogleMapsKeyResponse(BaseModel):
    """Google Maps API key response."""
    api_key: str


# === Helper Functions ===

def _check_database_health() -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        from civicos import CivicOS
        c = CivicOS("city-san-rafael")
        # Quick query to test connection
        _ = c.storage
        return {"status": "healthy", "message": "Database connected"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_chromadb_health() -> Dict[str, Any]:
    """Check ChromaDB availability."""
    try:
        from civicos.storage.vector_backend import get_vector_backend
        backend = get_vector_backend()
        return {"status": "healthy" if backend else "degraded"}
    except Exception as e:
        return {"status": "degraded", "message": str(e)}


def _check_external_services() -> Dict[str, str]:
    """Check external service availability."""
    return {
        "legistar": "available",  # Could add actual check
        "seeclickfix": "available"
    }


# === Public Endpoints ===

@router.get("/api/status", response_model=StatusResponse)
async def get_status():
    """
    API status and health check with comprehensive system checks.

    This is a public endpoint - no authentication required.
    """
    checks = {}

    # 1. Database connectivity check
    checks["database"] = _check_database_health()

    # 2. ChromaDB availability check
    checks["chromadb"] = _check_chromadb_health()

    # 3. External services check
    checks["services"] = _check_external_services()

    # 4. Data availability check
    schema_dir = Path("data/events")
    schema_files = list(schema_dir.glob("newsletter_*.json")) if schema_dir.exists() else []

    checks["data"] = {
        "status": "healthy" if schema_files else "degraded",
        "schema_files_available": len(schema_files),
        "latest_data": schema_files[-1].name if schema_files else None,
        "last_updated": datetime.fromtimestamp(schema_files[-1].stat().st_mtime).isoformat() if schema_files else None,
    }

    # Determine overall status
    overall_healthy = all(
        check.get("status") in ("healthy", "available")
        for check in [checks["database"], checks["chromadb"]]
    )

    if not overall_healthy:
        overall_status = "unhealthy"
    elif checks["services"].get("legistar") == "unavailable" or checks["data"]["status"] == "degraded":
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "0.4.0",
        "checks": checks,
        "endpoints": {
            "public": ["/api/status", "/health"],
            "authenticated": [
                "/api/events (GET - list all)",
                "/api/events/{id} (GET - single opportunity)",
                "/api/jurisdictions (GET - list all jurisdictions with counts)",
                "/api/issues?user_id={user} (GET - user issues)",
                "/api/refresh (GET - refresh data)",
                "/api/conversation (POST - AI conversation)",
                "/api/legistar/{city}/events (GET - Legistar API events)",
            ]
        },
        "authentication": "Bearer token required for protected endpoints"
    }


@router.get("/api/config/google-maps-key", response_model=GoogleMapsKeyResponse)
async def get_google_maps_key():
    """
    Get Google Maps API key for frontend Places Autocomplete.

    This is a public endpoint - API key should be restricted by HTTP referrer
    in Google Cloud Console.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Google Maps API key not configured")

    return {"api_key": api_key}


@router.get("/help")
async def get_help():
    """
    API documentation and usage guide.

    This is a public endpoint - no authentication required.
    """
    return {
        "name": "Civic API",
        "version": "0.4.0",
        "description": "AI-enabled infrastructure for local self-organization and governance",
        "documentation": "/docs",
        "openapi": "/openapi.json",
        "endpoints": {
            "public": {
                "/health": "Basic health check",
                "/api/status": "Detailed system status",
                "/api/config/google-maps-key": "Frontend config",
                "/help": "This documentation",
            },
            "authenticated": {
                "/api/events": "List civic events and opportunities",
                "/api/events/search": "Search events with filters",
                "/api/issues": "User issues/complaints",
                "/api/jurisdictions": "List jurisdictions",
                "/api/conversation": "AI conversation",
            }
        },
        "authentication": {
            "method": "Bearer token",
            "header": "Authorization: Bearer <your_api_key>",
            "note": "See INTEGRATION_GUIDE.md for API key setup"
        }
    }


@router.get("/api/onboarding/cards")
async def get_onboarding_cards():
    """
    Get onboarding cards for new users.

    This is a public endpoint - privacy-first, no auth required.
    """
    # Load onboarding cards from config or generate defaults
    return {
        "cards": [
            {
                "id": "welcome",
                "title": "Welcome to Civic",
                "description": "Your gateway to local civic engagement",
                "action": "get_started"
            },
            {
                "id": "events",
                "title": "Discover Events",
                "description": "Find city council meetings, planning sessions, and community events",
                "action": "browse_events"
            },
            {
                "id": "issues",
                "title": "Report Issues",
                "description": "Report neighborhood issues and track their resolution",
                "action": "file_issue"
            },
            {
                "id": "community",
                "title": "Join Your Community",
                "description": "Connect with neighbors who care about the same issues",
                "action": "explore_community"
            }
        ]
    }


# === Authenticated Endpoints ===

# Import auth dependency - will be set up in main app
from .dependencies import verify_auth


@router.get("/api/jurisdictions", response_model=JurisdictionsResponse)
async def get_jurisdictions(user_id: str = Depends(verify_auth)):
    """
    List jurisdictions with event/issue counts.

    Requires authentication.
    """
    try:
        # Import automated_civic_refresh to access CITY_CONFIGS
        try:
            from civicos_services.monitoring.automated_civic_refresh import CITY_CONFIGS
        except ImportError:
            CITY_CONFIGS = {}

        # Import issue storage for issue counts
        try:
            from civicos_services.storage.issue_storage import IssueStorage
            storage = IssueStorage()
            complaint_storage_available = True
        except Exception:
            complaint_storage_available = False

        # List all event files
        schema_dir = Path("data/events")
        if not schema_dir.exists():
            return {"jurisdictions": [], "total": 0}

        event_files = list(schema_dir.glob("events_*.json"))

        # Extract jurisdiction_id from filenames and count events
        jurisdiction_counts: Dict[str, int] = {}
        for file_path in event_files:
            # Pattern: events_{jurisdiction_id}_{date}_{time}.json
            match = re.match(r"events_([a-z0-9\-]+)_\d{8}_\d{6}\.json", file_path.name)
            if match:
                jurisdiction_id = match.group(1)

                # Count events in this file
                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)
                        event_count = len(data.get("events", []))

                        if jurisdiction_id not in jurisdiction_counts:
                            jurisdiction_counts[jurisdiction_id] = event_count
                        else:
                            jurisdiction_counts[jurisdiction_id] = max(
                                jurisdiction_counts[jurisdiction_id],
                                event_count
                            )
                except Exception:
                    pass

        # Build jurisdiction list with metadata
        jurisdictions = []
        for jurisdiction_id, event_count in jurisdiction_counts.items():
            # Get jurisdiction metadata from CITY_CONFIGS
            city_config = CITY_CONFIGS.get(jurisdiction_id, {})

            # Get issue count if available
            issue_count = 0
            if complaint_storage_available:
                try:
                    issues = storage.get_issues_for_user(None)
                    issue_count = len([i for i in issues if i.get("jurisdiction_id") == jurisdiction_id])
                except Exception:
                    pass

            # Parse jurisdiction name from ID
            name = jurisdiction_id.replace("city-", "").replace("-", " ").title()
            jtype = "city" if jurisdiction_id.startswith("city-") else "county"

            jurisdictions.append({
                "id": jurisdiction_id,
                "name": name,
                "type": jtype,
                "event_count": event_count,
                "issue_count": issue_count,
                "cdbg_allocation": city_config.get("cdbg_allocation", "N/A"),
                "population": city_config.get("population"),
                "timezone": city_config.get("timezone", "America/Los_Angeles")
            })

        # Sort by event count descending
        jurisdictions.sort(key=lambda x: x["event_count"], reverse=True)

        return {
            "jurisdictions": jurisdictions,
            "total": len(jurisdictions)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
