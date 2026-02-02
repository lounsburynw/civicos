"""
Admin router: cache stats, operations, provider stats, monitoring.

Endpoints:
- GET /cache-stats - Cache statistics
- GET /provider-stats - LLM provider usage
- GET /cost-estimate - Cost estimation (LLM tokens)
- GET /cost-status - ETL cost status with daily/monthly thresholds
- GET /cost-dashboard - Actual operating costs with time-series breakdown
- GET /operations - List background operations
- GET /operations/{id} - Get operation status
- GET /data/{type} - Data browser
- GET /vector-stats - Vector index stats
- GET /api-key-status - External API key validation status
- GET /assemblyai-usage - AssemblyAI transcription usage and cost tracking
- POST /trigger - Trigger admin actions
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict
import os
import time
import logging
import requests

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)


router = APIRouter()


# === Pydantic Models ===

class CacheStats(BaseModel):
    """Cache statistics response."""
    hits: int
    misses: int
    hit_rate: float
    size: int
    max_size: int


class ProviderStats(BaseModel):
    """Provider usage statistics."""
    providers: Dict[str, Dict[str, Any]]
    total_requests: int
    total_tokens: int


class CostEstimate(BaseModel):
    """Cost estimation response."""
    period: str
    estimated_cost: float
    breakdown: Dict[str, float]


class Operation(BaseModel):
    """Background operation."""
    id: str
    type: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    progress: Optional[float] = None
    error: Optional[str] = None


class AdminTriggerRequest(BaseModel):
    """Admin trigger request."""
    action: str
    params: Optional[Dict[str, Any]] = None


class APIKeyStatus(BaseModel):
    """Status of an external API key."""
    service_name: str
    is_configured: bool  # Key exists in environment
    is_valid: Optional[bool] = None  # Successfully validated (None if not checked)
    validation_method: str  # "api_call", "not_configured", "cached"
    last_validated: Optional[str] = None
    error_message: Optional[str] = None
    response_time_ms: Optional[int] = None


class APIKeyStatusResponse(BaseModel):
    """Response for API key status endpoint."""
    timestamp: str
    keys: Dict[str, APIKeyStatus]
    overall_status: str  # "healthy", "warning", "degraded", "unconfigured"


class AssemblyAIUsage(BaseModel):
    """AssemblyAI transcription usage statistics."""
    period: str  # "current_month" or "last_30_days"
    period_start: str  # ISO date
    period_end: str  # ISO date
    transcript_count: int
    total_minutes: float
    estimated_cost_usd: float
    last_updated: str  # ISO timestamp


class AssemblyAIUsageResponse(BaseModel):
    """Response for AssemblyAI usage endpoint."""
    timestamp: str
    is_configured: bool
    usage: Optional[AssemblyAIUsage] = None
    error_message: Optional[str] = None
    cached: bool = False


# === API Key Validation Cache ===
# Simple in-memory cache to avoid hitting external APIs on every request
_api_key_cache: Dict[str, Dict[str, Any]] = {}
_API_KEY_CACHE_TTL_SECONDS = 300  # 5 minutes

# === AssemblyAI Usage Cache ===
# Cache usage stats for 1 hour (usage doesn't change frequently)
_usage_cache: Dict[str, Dict[str, Any]] = {}
_USAGE_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_cached_validation(service_name: str) -> Optional[Dict[str, Any]]:
    """Get cached validation result if not expired."""
    if service_name in _api_key_cache:
        cached = _api_key_cache[service_name]
        if time.time() - cached.get("cached_at", 0) < _API_KEY_CACHE_TTL_SECONDS:
            return cached
    return None


def _set_cached_validation(service_name: str, result: Dict[str, Any]) -> None:
    """Cache a validation result."""
    result["cached_at"] = time.time()
    _api_key_cache[service_name] = result


def _get_cached_usage(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached usage result if not expired."""
    if cache_key in _usage_cache:
        cached = _usage_cache[cache_key]
        if time.time() - cached.get("cached_at", 0) < _USAGE_CACHE_TTL_SECONDS:
            return cached
    return None


def _set_cached_usage(cache_key: str, result: Dict[str, Any]) -> None:
    """Cache a usage result."""
    result["cached_at"] = time.time()
    _usage_cache[cache_key] = result


# === Auth Dependency ===

from .dependencies import verify_auth


# === Shared State ===

# Provider stats tracking (shared with main API)
provider_stats = defaultdict(lambda: {"count": 0, "total_tokens": 0})


# === Endpoints ===

@router.get("/cache-stats")
async def get_cache_stats(token: str = Depends(verify_auth)):
    """
    Get cache statistics.

    Returns hit/miss rates and cache size information.
    Requires authentication.
    """
    try:
        # Try to get stats from legislative cache
        try:
            from civicos_services.legislative.legislative_context_cache import legislative_cache
            cache_stats = {
                "legislative": {
                    "hits": getattr(legislative_cache, "_hits", 0),
                    "misses": getattr(legislative_cache, "_misses", 0),
                    "size": len(getattr(legislative_cache, "_cache", {})),
                }
            }
        except ImportError:
            cache_stats = {"legislative": {"available": False}}

        # Try to get research service cache stats
        try:
            from civicos_services.storage.research_service import ResearchService
            research = ResearchService()
            cache_stats["research"] = {
                "cached_queries": len(getattr(research, "_cache", {})),
            }
        except ImportError:
            cache_stats["research"] = {"available": False}

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "caches": cache_stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/provider-stats")
async def get_provider_stats(token: str = Depends(verify_auth)):
    """
    Get LLM provider usage statistics.

    Returns per-provider request counts and token usage.
    Requires authentication.
    """
    try:
        # Get stats from provider module
        try:
            from civicos_services.core.llm_provider import get_provider_stats
            stats = get_provider_stats()
        except ImportError:
            stats = dict(provider_stats)

        total_requests = sum(p.get("count", 0) for p in stats.values())
        total_tokens = sum(p.get("total_tokens", 0) for p in stats.values())

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "providers": stats,
            "totals": {
                "requests": total_requests,
                "tokens": total_tokens
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/cost-estimate")
async def get_cost_estimate(
    period: str = Query("day", description="Estimate period: day, week, month"),
    token: str = Depends(verify_auth)
):
    """
    Get cost estimation for LLM usage.

    Based on current usage patterns, estimates costs for the specified period.
    Requires authentication.
    """
    try:
        # Cost per 1M tokens (approximate)
        costs_per_million = {
            "openai": {"input": 0.50, "output": 1.50},
            "anthropic": {"input": 3.00, "output": 15.00},
            "google": {"input": 0.25, "output": 0.50},
        }

        # Get current stats
        try:
            from civicos_services.core.llm_provider import get_provider_stats
            stats = get_provider_stats()
        except ImportError:
            stats = dict(provider_stats)

        # Calculate costs
        breakdown = {}
        total_cost = 0.0

        for provider, usage in stats.items():
            tokens = usage.get("total_tokens", 0)
            provider_costs = costs_per_million.get(provider, {"input": 1.0, "output": 2.0})
            # Assume 70% input, 30% output
            cost = (tokens * 0.7 * provider_costs["input"] + tokens * 0.3 * provider_costs["output"]) / 1_000_000
            breakdown[provider] = cost
            total_cost += cost

        # Scale by period
        multiplier = {"day": 1, "week": 7, "month": 30}.get(period, 1)

        return {
            "period": period,
            "estimated_cost": round(total_cost * multiplier, 4),
            "breakdown": {k: round(v * multiplier, 4) for k, v in breakdown.items()},
            "note": "Estimates based on current token usage patterns"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/cost-status")
async def get_cost_status(token: str = Depends(verify_auth)):
    """
    Get current ETL cost status with daily and monthly thresholds.

    Returns:
    - overall_status: "healthy", "warning", or "critical"
    - daily: Cost status vs $5/day threshold
    - monthly: Cost status vs $50/month threshold

    Triggers alerts when thresholds are exceeded.
    Requires authentication.
    """
    try:
        from civicos_services.monitoring.automated_civic_refresh import TemporalCostManager

        manager = TemporalCostManager()
        status = manager.get_cost_status()

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **status
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/cost-dashboard")
async def get_cost_dashboard(
    period: str = Query("month", description="Period: day, week, month, or all"),
    service: Optional[str] = Query(None, description="Filter by service (modal, openai, anthropic)"),
    jurisdiction_id: Optional[str] = Query(None, description="Filter by jurisdiction"),
    token: str = Depends(verify_auth)
):
    """
    Get operating cost dashboard with aggregated costs and time-series breakdown.

    Returns actual costs logged to operating_costs table (LLM and Modal compute).
    Provides summary totals and daily breakdown for visualization.

    Requires authentication.
    """
    try:
        # Use public Civic API (not private _storage)
        try:
            from civicos import CivicOS
            from dotenv import load_dotenv
            load_dotenv()
            c = CivicOS("city-san-rafael")
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        # Delegate to public Civic method
        return c.get_operating_cost_dashboard(
            period=period,
            service=service,
            jurisdiction_id=jurisdiction_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/operations")
async def list_operations(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum operations to return"),
    token: str = Depends(verify_auth)
):
    """
    List background operations.

    Returns list of data refresh, indexing, and other background tasks.
    Requires authentication.
    """
    try:
        # Try to get operations from operation tracker
        try:
            from civicos_services.monitoring.operation_tracker import OperationTracker
            tracker = OperationTracker()
            operations = tracker.list_operations(status=status, limit=limit)
        except ImportError:
            operations = []

        return {
            "operations": operations,
            "count": len(operations)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/operations/{operation_id}")
async def get_operation_status(
    operation_id: str,
    token: str = Depends(verify_auth)
):
    """
    Get status of a specific operation.

    Requires authentication.
    """
    try:
        # Try to get operation from tracker
        try:
            from civicos_services.monitoring.operation_tracker import OperationTracker
            tracker = OperationTracker()
            operation = tracker.get_operation(operation_id)
        except ImportError:
            operation = None

        if not operation:
            raise HTTPException(status_code=404, detail=f"Operation not found: {operation_id}")

        return operation

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/data/{data_type}")
async def browse_data(
    data_type: str,
    limit: int = Query(50, description="Maximum items to return"),
    offset: int = Query(0, description="Offset for pagination"),
    token: str = Depends(verify_auth)
):
    """
    Browse data by type for schema exploration.

    Supported types: meetings, decisions, transcripts, chunks, issues,
    budget_items, municipal_code, legislation

    Requires authentication.
    """
    try:
        # Import Civic to access storage
        try:
            from civicos import CivicOS
            from dotenv import load_dotenv
            load_dotenv()
            c = CivicOS("city-san-rafael")
        except ImportError:
            raise HTTPException(status_code=503, detail="Civic library not available")

        storage = c._storage

        # Map data types to storage methods
        data_fetchers = {
            "meetings": lambda: storage.get_meetings(limit=limit, offset=offset),
            "decisions": lambda: storage.get_decisions(limit=limit, offset=offset),
            "transcripts": lambda: storage.get_transcripts(limit=limit, offset=offset),
            "chunks": lambda: storage.get_chunks(limit=limit, offset=offset),
            "issues": lambda: storage.get_issues(limit=limit, offset=offset),
            "budget_items": lambda: storage.get_budget_items(limit=limit, offset=offset),
        }

        if data_type not in data_fetchers:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown data type: {data_type}. Supported: {list(data_fetchers.keys())}"
            )

        items = data_fetchers[data_type]()

        return {
            "type": data_type,
            "items": items,
            "count": len(items),
            "offset": offset,
            "limit": limit
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/vector-stats")
async def get_vector_stats(token: str = Depends(verify_auth)):
    """
    Get vector index statistics.

    Returns embedding counts per corpus type.
    Requires authentication.
    """
    try:
        # Try to get stats from vector backend
        try:
            from civicos import CivicOS
            from dotenv import load_dotenv
            load_dotenv()
            c = CivicOS("city-san-rafael")
            vector = c._vector
        except ImportError:
            raise HTTPException(status_code=503, detail="Vector backend not available")

        # Get stats per corpus type
        corpus_types = ["transcripts", "chunks", "municipal_code", "issues", "decisions", "meetings"]
        stats = {}

        for corpus_type in corpus_types:
            try:
                count = vector.count(corpus_type=corpus_type)
                stats[corpus_type] = {"count": count}
            except Exception:
                stats[corpus_type] = {"count": 0, "error": "Unable to count"}

        total = sum(s.get("count", 0) for s in stats.values())

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "corpus_stats": stats,
            "total_embeddings": total
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


def _validate_assemblyai_key(api_key: str) -> Dict[str, Any]:
    """
    Validate AssemblyAI API key by making a lightweight API call.

    Uses the /v2/upload endpoint with a simple HEAD-like call to verify auth.
    """
    import requests

    start_time = time.time()
    try:
        # AssemblyAI uses Authorization header with the API key directly
        # We can verify the key by calling the /v2/transcript endpoint with a list request
        # This is lightweight (just lists recent transcripts, limited to 1)
        response = requests.get(
            "https://api.assemblyai.com/v2/transcript",
            headers={"Authorization": api_key},
            params={"limit": 1},
            timeout=10
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 200:
            return {
                "is_valid": True,
                "response_time_ms": elapsed_ms,
                "validation_method": "api_call"
            }
        elif response.status_code == 401:
            return {
                "is_valid": False,
                "error_message": "Invalid API key (401 Unauthorized)",
                "response_time_ms": elapsed_ms,
                "validation_method": "api_call"
            }
        else:
            return {
                "is_valid": False,
                "error_message": f"Unexpected response: {response.status_code}",
                "response_time_ms": elapsed_ms,
                "validation_method": "api_call"
            }
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "is_valid": None,
            "error_message": "Request timed out",
            "response_time_ms": elapsed_ms,
            "validation_method": "api_call"
        }
    except requests.exceptions.RequestException as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "is_valid": None,
            "error_message": f"Connection error: {str(e)}",
            "response_time_ms": elapsed_ms,
            "validation_method": "api_call"
        }


def _validate_legiscan_key(api_key: str) -> Dict[str, Any]:
    """
    Validate LegiScan API key by making a lightweight API call.

    Uses the getStateList operation which is minimal and doesn't consume query quota significantly.
    """
    import requests

    start_time = time.time()
    try:
        response = requests.get(
            "https://api.legiscan.com/",
            params={"key": api_key, "op": "getStateList"},
            timeout=10
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                return {
                    "is_valid": True,
                    "response_time_ms": elapsed_ms,
                    "validation_method": "api_call"
                }
            elif data.get("status") == "ERROR":
                error_msg = data.get("alert", {}).get("message", "Unknown API error")
                return {
                    "is_valid": False,
                    "error_message": f"API error: {error_msg}",
                    "response_time_ms": elapsed_ms,
                    "validation_method": "api_call"
                }
        return {
            "is_valid": False,
            "error_message": f"Unexpected response: {response.status_code}",
            "response_time_ms": elapsed_ms,
            "validation_method": "api_call"
        }
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "is_valid": None,
            "error_message": "Request timed out",
            "response_time_ms": elapsed_ms,
            "validation_method": "api_call"
        }
    except requests.exceptions.RequestException as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "is_valid": None,
            "error_message": f"Connection error: {str(e)}",
            "response_time_ms": elapsed_ms,
            "validation_method": "api_call"
        }


# Cost per minute from transcribe.py: $0.015 transcription + $0.005 diarization
ASSEMBLYAI_COST_PER_MINUTE = 0.02


def _fetch_assemblyai_usage(api_key: str, period: str = "current_month") -> Dict[str, Any]:
    """
    Fetch AssemblyAI transcription usage for a given period.

    Args:
        api_key: AssemblyAI API key
        period: "current_month" or "last_30_days"

    Returns:
        Dict with transcript_count, total_minutes, estimated_cost_usd, period dates
    """
    # Determine date range
    now = datetime.utcnow()
    if period == "current_month":
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # last_30_days
        period_start = now - timedelta(days=30)
    period_end = now

    try:
        # AssemblyAI /v2/transcript returns transcripts with pagination
        # We need to fetch all transcripts created since period_start
        transcripts = []
        after_id = None
        page_limit = 200  # Max per page

        while True:
            params = {"limit": page_limit}
            if after_id:
                params["after_id"] = after_id

            response = requests.get(
                "https://api.assemblyai.com/v2/transcript",
                headers={"Authorization": api_key},
                params=params,
                timeout=30
            )

            if response.status_code != 200:
                return {
                    "error": f"API error: {response.status_code}",
                    "period": period
                }

            data = response.json()
            page_transcripts = data.get("transcripts", [])

            if not page_transcripts:
                break

            # Filter and collect transcripts within date range
            for t in page_transcripts:
                created = t.get("created")
                if created:
                    try:
                        # AssemblyAI returns ISO format: 2026-01-10T15:30:00.000000Z
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                        if created_dt >= period_start:
                            transcripts.append(t)
                        elif created_dt < period_start:
                            # Transcripts are returned newest-first, so we can stop
                            break
                    except (ValueError, TypeError):
                        continue

            # Check if we should stop pagination
            last_created = page_transcripts[-1].get("created")
            if last_created:
                try:
                    last_dt = datetime.fromisoformat(last_created.replace("Z", "+00:00")).replace(tzinfo=None)
                    if last_dt < period_start:
                        break
                except (ValueError, TypeError):
                    pass

            # Get next page
            page_info = data.get("page_details", {})
            if not page_info.get("next_url"):
                break
            after_id = page_transcripts[-1].get("id")
            if not after_id:
                break

        # Calculate totals
        total_seconds = 0
        for t in transcripts:
            # audio_duration is in milliseconds
            duration_ms = t.get("audio_duration")
            if duration_ms and t.get("status") == "completed":
                total_seconds += duration_ms / 1000

        total_minutes = total_seconds / 60
        estimated_cost = total_minutes * ASSEMBLYAI_COST_PER_MINUTE

        return {
            "period": period,
            "period_start": period_start.strftime("%Y-%m-%d"),
            "period_end": period_end.strftime("%Y-%m-%d"),
            "transcript_count": len([t for t in transcripts if t.get("status") == "completed"]),
            "total_minutes": round(total_minutes, 2),
            "estimated_cost_usd": round(estimated_cost, 2)
        }

    except requests.exceptions.Timeout:
        return {"error": "Request timed out", "period": period}
    except requests.exceptions.RequestException as e:
        return {"error": f"Connection error: {str(e)}", "period": period}


@router.get("/api-key-status")
async def get_api_key_status(
    force_refresh: bool = Query(False, description="Bypass cache and re-validate keys"),
    token: str = Depends(verify_auth)
):
    """
    Get validation status for external API keys.

    Checks AssemblyAI and LegiScan API keys by making lightweight validation calls.
    Results are cached for 5 minutes to avoid excessive API calls.

    Returns:
    - Per-key status (configured, valid, error details)
    - Overall status: healthy (all valid), warning (some invalid), degraded (none valid), unconfigured (none set)

    Requires authentication.
    """
    from dotenv import load_dotenv
    load_dotenv()

    keys_status: Dict[str, APIKeyStatus] = {}
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Check AssemblyAI
    assemblyai_key = os.getenv("ASSEMBLYAI_API_KEY")
    if assemblyai_key:
        cached = None if force_refresh else _get_cached_validation("assemblyai")
        if cached:
            keys_status["assemblyai"] = APIKeyStatus(
                service_name="AssemblyAI",
                is_configured=True,
                is_valid=cached.get("is_valid"),
                validation_method="cached",
                last_validated=cached.get("last_validated"),
                error_message=cached.get("error_message"),
                response_time_ms=cached.get("response_time_ms")
            )
        else:
            result = _validate_assemblyai_key(assemblyai_key)
            result["last_validated"] = timestamp
            _set_cached_validation("assemblyai", result)
            keys_status["assemblyai"] = APIKeyStatus(
                service_name="AssemblyAI",
                is_configured=True,
                is_valid=result.get("is_valid"),
                validation_method=result.get("validation_method", "api_call"),
                last_validated=timestamp,
                error_message=result.get("error_message"),
                response_time_ms=result.get("response_time_ms")
            )
    else:
        keys_status["assemblyai"] = APIKeyStatus(
            service_name="AssemblyAI",
            is_configured=False,
            is_valid=None,
            validation_method="not_configured",
            error_message="ASSEMBLYAI_API_KEY not set in environment"
        )

    # Check LegiScan
    legiscan_key = os.getenv("LEGISCAN_API_KEY")
    if legiscan_key:
        cached = None if force_refresh else _get_cached_validation("legiscan")
        if cached:
            keys_status["legiscan"] = APIKeyStatus(
                service_name="LegiScan",
                is_configured=True,
                is_valid=cached.get("is_valid"),
                validation_method="cached",
                last_validated=cached.get("last_validated"),
                error_message=cached.get("error_message"),
                response_time_ms=cached.get("response_time_ms")
            )
        else:
            result = _validate_legiscan_key(legiscan_key)
            result["last_validated"] = timestamp
            _set_cached_validation("legiscan", result)
            keys_status["legiscan"] = APIKeyStatus(
                service_name="LegiScan",
                is_configured=True,
                is_valid=result.get("is_valid"),
                validation_method=result.get("validation_method", "api_call"),
                last_validated=timestamp,
                error_message=result.get("error_message"),
                response_time_ms=result.get("response_time_ms")
            )
    else:
        keys_status["legiscan"] = APIKeyStatus(
            service_name="LegiScan",
            is_configured=False,
            is_valid=None,
            validation_method="not_configured",
            error_message="LEGISCAN_API_KEY not set in environment"
        )

    # Determine overall status
    configured_keys = [k for k, v in keys_status.items() if v.is_configured]
    valid_keys = [k for k, v in keys_status.items() if v.is_valid is True]

    if not configured_keys:
        overall_status = "unconfigured"
    elif len(valid_keys) == len(configured_keys):
        overall_status = "healthy"
    elif len(valid_keys) > 0:
        overall_status = "warning"
    else:
        overall_status = "degraded"

    return APIKeyStatusResponse(
        timestamp=timestamp,
        keys=keys_status,
        overall_status=overall_status
    )


@router.get("/assemblyai-usage")
async def get_assemblyai_usage(
    period: str = Query("current_month", description="Period: 'current_month' or 'last_30_days'"),
    force_refresh: bool = Query(False, description="Bypass cache and fetch fresh data"),
    token: str = Depends(verify_auth)
):
    """
    Get AssemblyAI transcription usage statistics.

    Shows transcript count, total minutes transcribed, and estimated cost ($0.02/minute)
    for the specified period. Results are cached for 1 hour.

    Args:
        period: "current_month" (default) or "last_30_days"
        force_refresh: Bypass cache if True

    Returns:
        AssemblyAIUsageResponse with usage stats or error message

    Requires authentication.
    """
    from dotenv import load_dotenv
    load_dotenv()

    timestamp = datetime.utcnow().isoformat() + "Z"

    # Validate period
    if period not in ("current_month", "last_30_days"):
        period = "current_month"

    # Check if API key is configured
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        return AssemblyAIUsageResponse(
            timestamp=timestamp,
            is_configured=False,
            error_message="ASSEMBLYAI_API_KEY not set in environment"
        )

    # Check cache
    cache_key = f"assemblyai_usage_{period}"
    if not force_refresh:
        cached = _get_cached_usage(cache_key)
        if cached:
            return AssemblyAIUsageResponse(
                timestamp=timestamp,
                is_configured=True,
                usage=AssemblyAIUsage(
                    period=cached.get("period", period),
                    period_start=cached.get("period_start", ""),
                    period_end=cached.get("period_end", ""),
                    transcript_count=cached.get("transcript_count", 0),
                    total_minutes=cached.get("total_minutes", 0.0),
                    estimated_cost_usd=cached.get("estimated_cost_usd", 0.0),
                    last_updated=cached.get("last_updated", timestamp)
                ),
                cached=True
            )

    # Fetch fresh usage data
    result = _fetch_assemblyai_usage(api_key, period)

    if "error" in result:
        return AssemblyAIUsageResponse(
            timestamp=timestamp,
            is_configured=True,
            error_message=result["error"]
        )

    # Cache the result
    result["last_updated"] = timestamp
    _set_cached_usage(cache_key, result)

    return AssemblyAIUsageResponse(
        timestamp=timestamp,
        is_configured=True,
        usage=AssemblyAIUsage(
            period=result["period"],
            period_start=result["period_start"],
            period_end=result["period_end"],
            transcript_count=result["transcript_count"],
            total_minutes=result["total_minutes"],
            estimated_cost_usd=result["estimated_cost_usd"],
            last_updated=timestamp
        ),
        cached=False
    )


@router.post("/trigger")
async def trigger_admin_action(
    request: AdminTriggerRequest,
    token: str = Depends(verify_auth)
):
    """
    Trigger an admin action.

    Supported actions:
    - refresh_data: Trigger data refresh
    - reindex_vectors: Reindex vector embeddings
    - clear_cache: Clear caches

    Requires authentication.
    """
    try:
        action = request.action
        params = request.params or {}

        if action == "refresh_data":
            # Trigger data refresh
            try:
                from civicos_services.monitoring.automated_civic_refresh import trigger_refresh
                result = trigger_refresh(params.get("jurisdiction_id"))
                return {"success": True, "action": action, "result": result}
            except ImportError:
                raise HTTPException(status_code=503, detail="Refresh service not available")

        elif action == "reindex_vectors":
            # Trigger vector reindexing
            try:
                from civicos_services.processing.vector_indexer import trigger_reindex
                result = trigger_reindex(params.get("corpus_type"))
                return {"success": True, "action": action, "result": result}
            except ImportError:
                raise HTTPException(status_code=503, detail="Vector indexer not available")

        elif action == "clear_cache":
            # Clear caches
            try:
                from civicos_services.legislative.legislative_context_cache import legislative_cache
                legislative_cache.clear()
                return {"success": True, "action": action, "message": "Caches cleared"}
            except ImportError:
                return {"success": True, "action": action, "message": "No caches to clear"}

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown action: {action}. Supported: refresh_data, reindex_vectors, clear_cache"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/status")
async def get_admin_status(token: str = Depends(verify_auth)):
    """
    Get admin status overview.

    Returns pipeline health, storage stats, and system status.
    Requires authentication.
    """
    try:
        status = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "components": {}
        }

        # Check storage
        try:
            from civicos import CivicOS
            from dotenv import load_dotenv
            load_dotenv()
            c = CivicOS("city-san-rafael")
            storage = c._storage
            status["components"]["storage"] = {
                "status": "healthy",
                "backend": type(storage).__name__
            }
        except Exception as e:
            status["components"]["storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }

        # Check vector backend
        try:
            vector = c._vector
            status["components"]["vector"] = {
                "status": "healthy",
                "backend": type(vector).__name__
            }
        except Exception as e:
            status["components"]["vector"] = {
                "status": "unhealthy",
                "error": str(e)
            }

        # Determine overall status
        all_healthy = all(
            comp.get("status") == "healthy"
            for comp in status["components"].values()
        )
        status["overall"] = "healthy" if all_healthy else "degraded"

        return status

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
