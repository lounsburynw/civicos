"""
FastAPI dependencies for Civic API.

Extracted to avoid circular imports between main app and routers.

Supports two auth sources:
1. Env-based keys (CIVICOS_WEB_KEY, etc.) — fast, no DB hit
2. DB-backed keys (platform_api_keys table) — checked if env keys miss
"""

from dataclasses import dataclass, field
from typing import Optional, Set

from fastapi import Header, HTTPException, Request

# Lazy import to avoid circular dependency
_config = None


@dataclass
class AuthContext:
    """Authentication context returned by verify_auth / optional_auth.

    Backward-compatible: str(context) returns the key identifier,
    so existing code using `token: str = Depends(verify_auth)` still works.
    """

    key_id: str
    source: str = "env"  # "env" or "db"
    tier: str = "admin"
    rate_limit_per_minute: int = 1000
    jurisdictions: list = field(default_factory=list)
    name: str = ""
    email: str = ""

    def __str__(self) -> str:
        return self.key_id

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self.key_id == other
        if isinstance(other, AuthContext):
            return self.key_id == other.key_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.key_id)


def get_config():
    """Lazily load config to avoid import issues."""
    global _config
    if _config is None:
        from ...core.config import config
        _config = config
    return _config


def get_api_keys() -> Set[str]:
    """Get valid API keys from config."""
    config = get_config()
    keys = config.get_api_keys()
    # Config may return dict or set; handle both
    if isinstance(keys, dict):
        return set(keys.keys())
    return set(keys) if keys else set()


def _check_db_key(token: str) -> Optional[AuthContext]:
    """Check token against DB-backed API keys. Returns AuthContext or None."""
    try:
        from ...core.api_keys import get_api_key_store

        store = get_api_key_store()
        if not store.available:
            return None

        info = store.validate_key(token)
        if info is None:
            return None

        return AuthContext(
            key_id=info.key_id,
            source="db",
            tier=info.tier,
            rate_limit_per_minute=info.rate_limit_per_minute,
            jurisdictions=info.jurisdictions,
            name=info.name,
            email=info.email,
        )
    except Exception:
        return None


async def verify_auth(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> AuthContext:
    """
    Verify Bearer token authentication.

    Checks env-based keys first (fast), then DB-backed keys.
    Returns AuthContext with key info.
    Raises HTTPException if invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Authentication required",
                "message": "Include Bearer token in Authorization header",
                "example": "Authorization: Bearer <your_api_key>"
            }
        )

    token = authorization.replace("Bearer ", "")

    # 1. Check env-based keys first (fast, no DB hit)
    api_keys = get_api_keys()
    if token in api_keys:
        ctx = AuthContext(key_id=token, source="env", tier="admin")
        request.state.auth_context = ctx
        return ctx

    # 2. Check DB-backed keys
    db_ctx = _check_db_key(token)
    if db_ctx is not None:
        request.state.auth_context = db_ctx
        # Fire-and-forget: update last_used_at
        try:
            from ...core.api_keys import get_api_key_store
            import asyncio
            store = get_api_key_store()
            asyncio.get_event_loop().call_soon(store.update_last_used, db_ctx.key_id)
        except Exception:
            pass
        return db_ctx

    raise HTTPException(
        status_code=401,
        detail={
            "error": "Invalid authentication",
            "message": "API key not recognized"
        }
    )


async def optional_auth(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[AuthContext]:
    """
    Optional authentication - returns AuthContext if present, None otherwise.
    Does not raise exceptions.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.replace("Bearer ", "")

    # Check env-based keys first
    api_keys = get_api_keys()
    if token in api_keys:
        ctx = AuthContext(key_id=token, source="env", tier="admin")
        request.state.auth_context = ctx
        return ctx

    # Check DB-backed keys
    db_ctx = _check_db_key(token)
    if db_ctx is not None:
        request.state.auth_context = db_ctx
        return db_ctx

    return None


async def get_user_id(token: str) -> str:
    """
    Get user_id from authenticated token.

    MVP Implementation: Token IS the user_id.
    Handles both str and AuthContext.
    """
    return str(token)
