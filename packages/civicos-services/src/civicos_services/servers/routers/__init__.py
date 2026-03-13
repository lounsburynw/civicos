"""
FastAPI routers for Civic API.

Session 508: Domain-specific routers migrated from BaseHTTPRequestHandler.
Each router handles a specific domain of endpoints.
"""

from .core import router as core_router
from .events import router as events_router
from .issues import router as issues_router
from .admin import router as admin_router
from .user import router as user_router
from .follows import router as follows_router
from .threads import router as threads_router
from .legislative import router as legislative_router
from .conversations import router as conversations_router
from .drafts import router as drafts_router
# Coordination router lives in civicos_relay package (canonical location).
# Re-exported here for backward compatibility with local dev server (api.py).
from civicos_relay.server.coordination import router as coordination_router
from .nostr import router as nostr_router
from .registry import router as registry_router
from .context import router as context_router
from .ai_proxy import router as ai_proxy_router
from .billing import router as billing_router

__all__ = [
    "core_router",
    "events_router",
    "issues_router",
    "admin_router",
    "user_router",
    "follows_router",
    "threads_router",
    "legislative_router",
    "conversations_router",
    "drafts_router",
    "coordination_router",
    "nostr_router",
    "registry_router",
    "context_router",
    "ai_proxy_router",
    "billing_router",
]
