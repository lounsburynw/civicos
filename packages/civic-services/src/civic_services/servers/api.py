#!/usr/bin/env python3
"""
FastAPI-based Civic API Server.

Session 508: Migration from BaseHTTPRequestHandler to FastAPI.
Provides the same endpoints with:
- Automatic OpenAPI documentation at /docs
- Pydantic request/response validation
- Native async/await support
- Cleaner route definitions with decorators

Run with: uvicorn civic_services.servers.api:app --port 8001
"""

import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Structured logging
try:
    from ..core.logging_config import (
        configure_logging, get_logger,
        set_correlation_id, clear_correlation_id
    )
    configure_logging()
    logger = get_logger('civic_api')
except ImportError:
    logger = logging.getLogger('civic_api')
    logging.basicConfig(level=logging.INFO)

# Core imports
from ..core.config import config
from ..core.rate_limiter import rate_limiter

# Import routers
from .routers import (
    core_router,
    events_router,
    issues_router,
    admin_router,
    user_router,
    follows_router,
    threads_router,
    legislative_router,
    conversations_router,
    drafts_router,
)


# === Pydantic Models ===

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    status: int


class RateLimitInfo(BaseModel):
    """Rate limit information."""
    error: str
    message: str
    retry_after: int


# === Lifespan ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("startup", extra={"message": "Civic FastAPI server starting"})
    yield
    logger.info("shutdown", extra={"message": "Civic FastAPI server shutting down"})


# === Application Factory ===

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Civic API",
        description="AI-enabled infrastructure for local self-organization and governance",
        version="0.4.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    allowed_origins = config.get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    )

    # Include routers
    app.include_router(core_router, tags=["Core"])
    app.include_router(events_router, prefix="/api", tags=["Events"])
    app.include_router(issues_router, prefix="/api", tags=["Issues"])
    app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
    app.include_router(user_router, prefix="/api/user", tags=["User"])
    app.include_router(follows_router, prefix="/api", tags=["Follows"])
    app.include_router(threads_router, prefix="/api", tags=["Threads"])
    app.include_router(legislative_router, prefix="/api", tags=["Legislative"])
    app.include_router(conversations_router, prefix="/api", tags=["Conversations"])
    app.include_router(drafts_router, prefix="/api", tags=["Drafts"])

    return app


# === Middleware ===

@asynccontextmanager
async def request_context(request: Request):
    """Set up request context with correlation ID."""
    correlation_id = str(uuid.uuid4())[:8]
    try:
        if 'set_correlation_id' in dir():
            set_correlation_id(correlation_id)
        yield correlation_id
    finally:
        if 'clear_correlation_id' in dir():
            clear_correlation_id()


# === Dependencies ===

async def get_client_id(request: Request) -> str:
    """Extract client ID for rate limiting."""
    # Use X-Forwarded-For if behind proxy, otherwise use client host
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_rate_limit(
    request: Request,
    client_id: str = Depends(get_client_id)
) -> None:
    """Check rate limit and raise HTTPException if exceeded."""
    allowed, limit_info = rate_limiter.check_rate_limit(client_id)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Limit: {limit_info['limit_value']} per {limit_info['limit']}",
                "retry_after": limit_info['retry_after']
            },
            headers={"Retry-After": str(limit_info['retry_after'])}
        )


# Re-export auth dependencies for backwards compatibility
from .routers.dependencies import (
    verify_auth,
    optional_auth,
    get_user_id,
    get_api_keys,
)


# === Request Logging Middleware ===

async def log_request(request: Request, call_next):
    """Log request start and completion."""
    start_time = time.time()
    correlation_id = str(uuid.uuid4())[:8]

    logger.info("request_start", extra={
        "method": request.method,
        "path": request.url.path,
        "client_ip": request.client.host if request.client else None,
        "correlation_id": correlation_id
    })

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000
    logger.info("request_complete", extra={
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": round(duration_ms, 2),
        "correlation_id": correlation_id
    })

    return response


# === Create App ===

app = create_app()

# Add request logging middleware
app.middleware("http")(log_request)


# === Direct Routes (not in routers) ===

@app.get("/health", tags=["Core"])
async def health_check(request: Request):
    """
    Health check endpoint (public, no auth required).

    Returns basic health status for load balancers and monitoring.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": "0.4.0"
    }


# === Main ===

if __name__ == "__main__":
    import uvicorn

    port = config.get_api_port()

    uvicorn.run(
        "civic_services.servers.api:app",
        host="0.0.0.0",
        port=port,
        reload=config.env == "development",
        log_level="info"
    )
