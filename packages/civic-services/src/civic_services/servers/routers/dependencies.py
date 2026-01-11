"""
FastAPI dependencies for Civic API.

Extracted to avoid circular imports between main app and routers.
"""

from typing import Optional, Set

from fastapi import Header, HTTPException

# Lazy import to avoid circular dependency
_config = None


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


async def verify_auth(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    Verify Bearer token authentication.

    Returns the user_id (token) if valid.
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
    api_keys = get_api_keys()

    if token not in api_keys:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Invalid authentication",
                "message": "API key not recognized"
            }
        )

    return token


async def optional_auth(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[str]:
    """
    Optional authentication - returns user_id if present, None otherwise.
    Does not raise exceptions.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.replace("Bearer ", "")
    api_keys = get_api_keys()

    if token in api_keys:
        return token
    return None


async def get_user_id(token: str) -> str:
    """
    Get user_id from authenticated token.

    MVP Implementation: Token IS the user_id.
    """
    return token
