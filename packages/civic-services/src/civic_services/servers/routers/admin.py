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
- POST /trigger - Trigger admin actions
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel


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
            from civic_services.legislative.legislative_context_cache import legislative_cache
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
            from civic_services.storage.research_service import ResearchService
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
            from civic_services.core.llm_provider import get_provider_stats
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
            from civic_services.core.llm_provider import get_provider_stats
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
        from civic_services.monitoring.automated_civic_refresh import TemporalCostManager

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
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
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
            from civic_services.monitoring.operation_tracker import OperationTracker
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
            from civic_services.monitoring.operation_tracker import OperationTracker
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
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
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
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
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
                from civic_services.monitoring.automated_civic_refresh import trigger_refresh
                result = trigger_refresh(params.get("jurisdiction_id"))
                return {"success": True, "action": action, "result": result}
            except ImportError:
                raise HTTPException(status_code=503, detail="Refresh service not available")

        elif action == "reindex_vectors":
            # Trigger vector reindexing
            try:
                from civic_services.processing.vector_indexer import trigger_reindex
                result = trigger_reindex(params.get("corpus_type"))
                return {"success": True, "action": action, "result": result}
            except ImportError:
                raise HTTPException(status_code=503, detail="Vector indexer not available")

        elif action == "clear_cache":
            # Clear caches
            try:
                from civic_services.legislative.legislative_context_cache import legislative_cache
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
            from civic import Civic
            from dotenv import load_dotenv
            load_dotenv()
            c = Civic("city-san-rafael")
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
