#!/usr/bin/env python3
"""
Integrated Civic API with Authentication and Schema Compliance
Bridges civic_digest.py → data/events/*.json → Conversational Interface

Addresses Priority 1 + TECHNICAL_DEBT issues #1 (Auth) and #5 (Integration Testing)
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from pathlib import Path
import sys
import hashlib
import time
import uuid
import sqlite3
import logging
from urllib.parse import parse_qs, urlparse
from collections import defaultdict
from typing import Dict, List, Optional, Any

# Structured logging (Session 246)
try:
    from ..core.logging_config import (
        configure_logging, get_logger, with_correlation_id,
        set_correlation_id, clear_correlation_id, get_correlation_id,
        log_request_start, log_request_complete, log_error, log_audit
    )
    configure_logging()
    logger = get_logger('civic_api')
except ImportError:
    # Fallback if logging_config not available
    logger = logging.getLogger('civic_api')
    logging.basicConfig(level=logging.INFO)

# Error rate monitoring (Session 294)
_error_alert_manager = None
_error_alert_checked = False

def get_error_alert_manager():
    """Lazily initialize and return the error alert manager, or None if unavailable."""
    global _error_alert_manager, _error_alert_checked
    if not _error_alert_checked:
        _error_alert_checked = True
        try:
            from ..monitoring.error_alerting import ErrorAlertManager
            _error_alert_manager = ErrorAlertManager()
            logger.debug("module_loaded", extra={"module_name": "error_alerting"})
        except Exception as e:
            _error_alert_manager = None
            logger.warning("module_unavailable", extra={"module_name": "error_alerting", "error": str(e)})
    return _error_alert_manager


# Request metrics monitoring (Session 296)
_request_metrics_manager = None
_request_metrics_checked = False

def get_request_metrics_manager():
    """Lazily initialize and return the request metrics manager, or None if unavailable."""
    global _request_metrics_manager, _request_metrics_checked
    if not _request_metrics_checked:
        _request_metrics_checked = True
        try:
            from ..monitoring.request_metrics import RequestMetricsManager
            _request_metrics_manager = RequestMetricsManager()
            logger.debug("module_loaded", extra={"module_name": "request_metrics"})
        except Exception as e:
            _request_metrics_manager = None
            logger.warning("module_unavailable", extra={"module_name": "request_metrics", "error": str(e)})
    return _request_metrics_manager


# Active users monitoring (Session 297)
_active_users_manager = None
_active_users_checked = False

def get_active_users_manager():
    """Lazily initialize and return the active users manager, or None if unavailable."""
    global _active_users_manager, _active_users_checked
    if not _active_users_checked:
        _active_users_checked = True
        try:
            from ..monitoring.active_users import ActiveUsersManager
            _active_users_manager = ActiveUsersManager()
            logger.debug("module_loaded", extra={"module_name": "active_users"})
        except Exception as e:
            _active_users_manager = None
            logger.warning("module_unavailable", extra={"module_name": "active_users", "error": str(e)})
    return _active_users_manager

# Core imports
from ..core.config import config, get_data_path, get_bundled_path, get_user_path
from ..core.rate_limiter import rate_limiter
from ..processing.civic_input_validator import CivicInputValidator, ValidationResult
from ..clients.legistar_client import create_client as create_legistar_client

# Agenda integration system
try:
    from ..processing.agenda_integration import AgendaIntegrator
    AGENDA_INTEGRATION_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "agenda_integration"})
except ImportError:
    AGENDA_INTEGRATION_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "agenda_integration", "reason": "Import failed"})

# Legislative context enrichment
try:
    from ..legislative.legislative_enrichment import enrich_opportunities_batch
    from ..legislative.legislative_context_cache import legislative_cache
    LEGISLATIVE_ENRICHMENT_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "legislative_enrichment"})
except ImportError:
    LEGISLATIVE_ENRICHMENT_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "legislative_enrichment", "reason": "Import failed"})

# Complaint handling system (Phase 1 MVP)
try:
    from ..issues.issue_handler import handle_message as handle_issue
    COMPLAINT_HANDLER_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "issue_handler"})
except ImportError as e:
    COMPLAINT_HANDLER_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "issue_handler", "error": str(e)})

# Research service for cache-first factual retrieval (Session 66)
# Uses lazy initialization to avoid requiring API keys at import time
_research_service = None
_research_service_checked = False

def get_research_service():
    """Lazily initialize and return the research service, or None if unavailable."""
    global _research_service, _research_service_checked
    if not _research_service_checked:
        _research_service_checked = True
        try:
            from ..storage.research_service import ResearchService
            _research_service = ResearchService()
            logger.debug("module_loaded", extra={"module_name": "research_service"})
        except Exception as e:
            _research_service = None
            logger.warning("module_unavailable", extra={"module_name": "research_service", "error": str(e)})
    return _research_service

# OpenAI integration for conversation API
try:
    import openai
    OPENAI_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "openai"})
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "openai", "reason": "Not installed"})

# Session 68: LLM Provider abstraction for cost optimization
try:
    from ..core.llm_provider import get_provider_for_task
    LLM_PROVIDER_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "llm_provider"})
except ImportError as e:
    LLM_PROVIDER_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "llm_provider", "error": str(e), "fallback": "openai_only"})

# Chat routing system (Session 27 - Chat-first navigation)
try:
    from ..chat.civic_chat_router import get_router
    CHAT_ROUTING_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "civic_chat_router"})
except ImportError as e:
    CHAT_ROUTING_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "civic_chat_router", "error": str(e)})

# Personalization service (Phase 1 - Database & Service Foundation)
try:
    from ..storage.personalization_service import PersonalizationService
    PERSONALIZATION_SERVICE_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "personalization_service"})
except ImportError as e:
    PERSONALIZATION_SERVICE_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "personalization_service", "error": str(e)})

# Conversation store (Session 79 - Persistent conversation storage)
try:
    from ..storage.conversation_store import ConversationStore
    CONVERSATION_STORE_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "conversation_store"})
except ImportError as e:
    CONVERSATION_STORE_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "conversation_store", "error": str(e)})

# SeeClickFix integration (Session 90 - Operational complaint→policy bridge)
try:
    from ..clients.seeclickfix_client import SeeClickFixClient
    SEECLICKFIX_AVAILABLE = True
    logger.debug("module_loaded", extra={"module_name": "seeclickfix_client"})
except ImportError as e:
    SEECLICKFIX_AVAILABLE = False
    logger.warning("module_unavailable", extra={"module_name": "seeclickfix_client", "error": str(e)})

# County mapping for hierarchical jurisdiction tree
COUNTY_MAPPING = {
    # Alameda County
    "city-oakland": {"county": "Alameda County", "state": "California"},
    "city-berkeley": {"county": "Alameda County", "state": "California"},
    "city-hayward": {"county": "Alameda County", "state": "California"},
    "city-san-leandro": {"county": "Alameda County", "state": "California"},
    "city-union-city": {"county": "Alameda County", "state": "California"},
    "city-dublin": {"county": "Alameda County", "state": "California"},
    "city-pleasanton": {"county": "Alameda County", "state": "California"},

    # Contra Costa County
    "city-el-cerrito": {"county": "Contra Costa County", "state": "California"},
    "city-concord": {"county": "Contra Costa County", "state": "California"},
    "city-pleasant-hill": {"county": "Contra Costa County", "state": "California"},
    "city-pinole": {"county": "Contra Costa County", "state": "California"},
    "city-pittsburg": {"county": "Contra Costa County", "state": "California"},
    "city-antioch": {"county": "Contra Costa County", "state": "California"},
    "city-richmond": {"county": "Contra Costa County", "state": "California"},

    # Marin County
    "city-san-rafael": {"county": "Marin County", "state": "California"},

    # Sonoma County
    "city-santa-rosa": {"county": "Sonoma County", "state": "California"},

    # Santa Clara County
    "city-campbell": {"county": "Santa Clara County", "state": "California"},
    "city-los-altos": {"county": "Santa Clara County", "state": "California"},
    "city-los-altos-hills": {"county": "Santa Clara County", "state": "California"},
    "city-milpitas": {"county": "Santa Clara County", "state": "California"},

    # Napa County
    "city-napa": {"county": "Napa County", "state": "California"},

    # San Mateo County
    "city-daly-city": {"county": "San Mateo County", "state": "California"},

    # Santa Cruz County
    "city-scotts-valley": {"county": "Santa Cruz County", "state": "California"},
}

# Conversation management
class ConversationManager:
    """DEPRECATED: Use ConversationStore for persistent storage with full message format support.

    This class is kept for backward compatibility with legacy /api/conversation endpoint.
    Migrate to ConversationStore for:
    - Persistent storage across server restarts
    - Full OpenAI message format (including tool_calls)
    - User association and conversation history
    - ChatGPT/Claude-style session management
    """

    def __init__(self, max_history: int = 10):
        self.conversations: Dict[str, List[dict]] = defaultdict(list)
        self.max_history = max_history
        self.validator = CivicInputValidator()

    def add_message(self, conversation_id: str, role: str, content: str = None,
                   tool_calls: List[dict] = None, metadata: dict = None) -> None:
        """Add a message to conversation history with optional tool_calls support.

        NOTE: This is a temporary fix. Migrate to ConversationStore for full persistence.

        Args:
            conversation_id: Conversation identifier
            role: Message role (user, assistant, system, tool)
            content: Message content (optional for assistant with only tool_calls)
            tool_calls: For assistant - list of tool calls in OpenAI format
            metadata: Optional metadata (model, tokens, provider, etc.)
        """
        message = {
            "role": role,
            "timestamp": datetime.now().isoformat()
        }

        # Add content if provided
        if content is not None:
            message["content"] = content

        # Add tool_calls if provided (FIX: was missing!)
        if tool_calls:
            message["tool_calls"] = tool_calls

        # Add metadata if provided
        if metadata:
            message["metadata"] = metadata

        self.conversations[conversation_id].append(message)

        # Trim history to prevent memory issues
        if len(self.conversations[conversation_id]) > self.max_history * 2:
            # Keep system message and recent history
            system_msgs = [m for m in self.conversations[conversation_id] if m["role"] == "system"][:1]
            recent_msgs = self.conversations[conversation_id][-(self.max_history * 2 - 1):]
            self.conversations[conversation_id] = system_msgs + recent_msgs
    
    def get_context(self, conversation_id: str) -> List[dict]:
        """Get conversation context for AI model"""
        return self.conversations[conversation_id][-self.max_history:]
    
    def validate_input(self, user_input: str) -> ValidationResult:
        """Validate and sanitize user input for conversation"""
        import html
        
        # Length validation - 2000 chars max for conversation messages
        if len(user_input) > 2000:
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                error_message=f"Message too long ({len(user_input)} characters). Please keep messages under 2000 characters.",
                severity="ERROR"
            )
        
        if len(user_input.strip()) < 1:
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                error_message="Message cannot be empty",
                severity="ERROR"
            )
        
        # Basic validation - allow most content but sanitize HTML entities
        # This is more permissive than validate_key_points which is too strict
        sanitized = html.escape(user_input)
        
        # Check for obvious attack patterns
        dangerous_patterns = [
            r'javascript:',
            r'data:text/html',
            r'vbscript:',
            r'on\w+\s*=',  # Event handlers
            r'<iframe',
            r'<embed',
            r'<object'
        ]
        
        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, user_input.lower()):
                return ValidationResult(
                    is_valid=False,
                    sanitized_value="",
                    error_message="Input contains potentially dangerous content",
                    severity="WARNING"
                )
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=sanitized,
            error_message=None,
            severity="INFO"
        )
    
    def clear_old_conversations(self, hours: int = 24) -> None:
        """Clear conversations older than specified hours"""
        cutoff = datetime.now().timestamp() - (hours * 3600)
        for conv_id in list(self.conversations.keys()):
            if self.conversations[conv_id]:
                last_msg = self.conversations[conv_id][-1]
                msg_time = datetime.fromisoformat(last_msg["timestamp"]).timestamp()
                if msg_time < cutoff:
                    del self.conversations[conv_id]

# Initialize conversation manager globally
conversation_manager = ConversationManager()

# Initialize personalization service globally
if PERSONALIZATION_SERVICE_AVAILABLE:
    personalization_service = PersonalizationService('data/civic_participation.db')
    print("[civic_api] ✅ PersonalizationService initialized with database: data/civic_participation.db")
else:
    personalization_service = None
    print("[civic_api] ⚠️  PersonalizationService not available - profile and civic history features disabled")

# Initialize conversation store globally (Session 80 - Persistent conversations)
if CONVERSATION_STORE_AVAILABLE:
    conversation_store = ConversationStore('data/civic_participation.db')
    print("[civic_api] ✅ ConversationStore initialized with database: data/civic_participation.db")
else:
    conversation_store = None
    print("[civic_api] ⚠️  ConversationStore not available - conversations will not persist across restarts")

# Data Freshness Management for Crisis Resolution
class DataFreshnessManager:
    """LLM-driven data freshness management balancing UX needs with cost constraints"""

    def __init__(self):
        self.ux_trust_threshold = 7  # UX requirement: never >7 days for future-focused queries
        self.engineering_cost_limit = 50  # Engineering constraint: <$50/month
        if OPENAI_AVAILABLE:
            self.openai_client = openai.OpenAI()  # For LLM-based intent analysis
        else:
            self.openai_client = None

    def assess_data_freshness(self, user_query: str = None) -> dict:
        """Joint assessment considering both UX needs and engineering constraints"""
        import glob
        import os
        import time

        schema_files = glob.glob('data/events/events_*.json')
        if not schema_files:
            return {"status": "no_data", "action": "emergency_refresh", "user_message": "Loading current civic data..."}

        latest_file = max(schema_files, key=os.path.getmtime)
        age_days = (time.time() - os.path.getmtime(latest_file)) / 86400

        # Use LLM to analyze user intent instead of keyword matching
        if user_query and self.openai_client:
            intent_analysis = self.analyze_user_intent(user_query)
            user_needs_current = intent_analysis.get("needs_current_data", False)
            temporal_focus = intent_analysis.get("temporal_focus", "current_active")
        else:
            user_needs_current = False
            temporal_focus = "current_active"

        # UX-Engineering decision matrix
        if age_days > 14:
            return {"status": "critical", "action": "immediate_refresh", "user_message": "⚠️ Updating civic data - please wait"}
        elif age_days > 7 and user_needs_current:
            return {"status": "refresh_needed", "action": "background_refresh", "user_message": "📅 Refreshing current meetings..."}
        elif age_days > 7:
            return {"status": "stale", "action": "schedule_refresh", "user_message": f"⚠️ Data from {age_days:.0f} days ago"}
        elif age_days > 3:
            return {"status": "aging", "action": "monitor", "user_message": f"📅 Updated {age_days:.0f} days ago"}
        else:
            return {"status": "fresh", "action": "none", "user_message": "✅ Current data"}

    def apply_ux_freshness_indicators(self, events: List[dict], freshness_status: dict) -> List[dict]:
        """Apply UX-appropriate freshness indicators to events"""
        if freshness_status["status"] in ["stale", "critical"]:
            user_message = freshness_status["user_message"]
            for opp in events:
                # Prepend freshness warning to existing description
                original_desc = opp.get('description', '')
                opp['description'] = f"{user_message}\n\n{original_desc}"
                # Add refresh action for stale data
                if 'actions' not in opp:
                    opp['actions'] = []
                opp['actions'].append({
                    "type": "refresh_data",
                    "label": "Refresh Current Data",
                    "priority": "high"
                })
        return events

    def analyze_user_intent(self, user_query: str) -> dict:
        """Analyze user query intent using LLM for smart refresh decisions"""
        if not self.openai_client:
            # Conservative fallback when OpenAI not available
            return {
                "temporal_focus": "current_active",
                "needs_current_data": True,
                "urgency_level": "general",
                "confidence": 0.5
            }

        intent_prompt = f"""
        Analyze this civic engagement query for data freshness requirements:

        Query: "{user_query}"

        Determine:
        1. temporal_focus: "future_only" (upcoming meetings/events), "current_active" (ongoing events), "recent_past" (past 6 months), "historical" (older than 6 months)
        2. needs_current_data: true if user needs up-to-date information, false if historical/procedural
        3. urgency_level: "immediate", "this_week", "this_month", "general"
        4. confidence: 0.0-1.0

        Examples:
        - "When's the next city council meeting?" → {{"temporal_focus": "future_only", "needs_current_data": true, "urgency_level": "this_week", "confidence": 0.95}}
        - "How do I submit public comments?" → {{"temporal_focus": "current_active", "needs_current_data": false, "urgency_level": "general", "confidence": 0.9}}
        - "What housing projects were discussed last month?" → {{"temporal_focus": "recent_past", "needs_current_data": false, "urgency_level": "general", "confidence": 0.85}}

        Return only valid JSON.
        """

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": intent_prompt}],
                max_tokens=200,
                temperature=0.1
            )

            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[DataFreshnessManager] LLM intent analysis failed: {e}")
            # Conservative fallback
            return {
                "temporal_focus": "current_active",
                "needs_current_data": True,
                "urgency_level": "general",
                "confidence": 0.5
            }

# Data freshness manager - lazy initialization to avoid API key requirement at import
_data_freshness_manager = None

def get_data_freshness_manager():
    """Lazily initialize and return the data freshness manager."""
    global _data_freshness_manager
    if _data_freshness_manager is None:
        _data_freshness_manager = DataFreshnessManager()
    return _data_freshness_manager

# Configure audit logging (Session 246: Uses structured logging from logging_config)
# audit_logger is now configured via configure_logging() with JSON output
audit_logger = get_logger('civic_audit') if 'get_logger' in dir() else logging.getLogger('civic_audit')

# Conversation storage for chat routing (Session 27)
# Session 80: Legacy in-memory fallback - ConversationStore is now preferred
# Only used when ConversationStore is unavailable (backwards compatibility)
CONVERSATIONS: Dict[str, List[Dict]] = {}

class AuthenticatedCivicAPIHandler(BaseHTTPRequestHandler):
    """Authenticated HTTP handler for civic data API with schema integration"""

    # Session 68: Provider usage tracking for cost monitoring
    provider_stats = defaultdict(lambda: {"count": 0, "total_tokens": 0})

    # Load API keys from centralized config
    def get_api_keys(self):
        """Load API keys from centralized configuration"""
        return config.get_api_keys()
    
    def authenticate_request(self):
        """Check API key authentication"""
        # Allow public endpoints
        public_endpoints = [
            '/api/status',
            '/health',
            '/api/config/google-maps-key',
            '/api/onboarding/cards'  # Privacy-first: no auth required for card generation
        ]
        if self.path in public_endpoints:
            return True

        auth_header = self.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False

        api_key = auth_header.replace('Bearer ', '')
        return api_key in self.get_api_keys()

    def get_user_id_from_token(self) -> Optional[str]:
        """
        Extract user_id from Bearer token in Authorization header.

        MVP Implementation: Token IS the user_id (simple authentication)
        This works for foundation-funded civic infrastructure.

        Production upgrade path: Use JWT with user_id in payload
        """
        auth_header = self.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.replace('Bearer ', '')

        # For MVP: token is the user_id
        # In production: decode JWT and extract user_id from payload
        return token

    def send_auth_error(self):
        """Send authentication required response"""
        self.send_response(401)
        self.send_header('Content-Type', 'application/json')
        # Use proper CORS from config
        origin = self.headers.get('Origin', '*')
        allowed_origins = config.get_cors_origins()
        if '*' in allowed_origins or origin in allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
        else:
            self.send_header('Access-Control-Allow-Origin', allowed_origins[0] if allowed_origins else '*')
        self.end_headers()
        error_response = {
            'error': 'Authentication required',
            'message': 'Include Bearer token in Authorization header',
            'example': 'Authorization: Bearer <your_api_key>'
        }
        self.wfile.write(json.dumps(error_response, indent=2).encode())
        # Session 296: Log request completion for metrics
        self._log_request_complete(401)
    
    def send_rate_limit_error(self, limit_info):
        """Send rate limit exceeded response"""
        self.send_response(429)  # Too Many Requests
        self.send_header('Content-Type', 'application/json')
        self.send_header('Retry-After', str(limit_info['retry_after']))

        # Use proper CORS from config
        origin = self.headers.get('Origin', '*')
        allowed_origins = config.get_cors_origins()
        if '*' in allowed_origins or origin in allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
        else:
            self.send_header('Access-Control-Allow-Origin', allowed_origins[0] if allowed_origins else '*')

        self.end_headers()

        error_response = {
            'error': 'Rate limit exceeded',
            'message': f"Too many requests. Limit: {limit_info['limit_value']} per {limit_info['limit']}",
            'retry_after': limit_info['retry_after']
        }
        self.wfile.write(json.dumps(error_response, indent=2).encode())
        # Session 296: Log request completion for metrics
        self._log_request_complete(429)
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        # Use proper CORS from config
        origin = self.headers.get('Origin', '*')
        allowed_origins = config.get_cors_origins()
        if '*' in allowed_origins or origin in allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
        else:
            self.send_header('Access-Control-Allow-Origin', allowed_origins[0] if allowed_origins else '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Max-Age', '3600')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests with authentication and rate limiting"""
        # Session 246: Request logging with correlation ID
        # Session 296: Store as instance vars for request completion logging
        self._request_start_time = time.time()
        self._request_method = "GET"
        correlation_id = set_correlation_id() if 'set_correlation_id' in dir() else str(uuid.uuid4())[:8]
        client_ip = self.client_address[0] if self.client_address else None

        # Log request start
        logger.info("request_start", extra={
            "method": "GET",
            "path": self.path,
            "client_ip": client_ip,
            "correlation_id": correlation_id
        })

        # Check rate limit first
        client_id = rate_limiter.get_client_id(self)
        allowed, limit_info = rate_limiter.check_rate_limit(client_id)
        
        if not allowed:
            self.send_rate_limit_error(limit_info)
            return

        # Parse path early for public endpoint check
        from urllib.parse import urlparse
        parsed_path = urlparse(self.path)
        base_path = parsed_path.path

        # Session 270: /help is public (no auth required)
        if base_path == '/help':
            self.serve_help()
            return

        # Authenticate all other requests
        if not self.authenticate_request():
            self.send_auth_error()
            return

        if base_path == '/api/events/search':
            self.serve_events_search()
        elif base_path == '/api/issues/search':
            # Session 62: Issues search endpoint (mirrors events pattern)
            self.serve_issues_search()
        elif base_path == '/api/events/discussion-stats':
            self.serve_event_discussion_stats()
        elif base_path == '/api/events':
            self.serve_opportunities()
        elif base_path == '/api/jurisdictions':
            self.serve_jurisdictions()
        elif base_path == '/api/admin/cache-stats':
            # SESSION 48: Cache statistics endpoint
            self.handle_cache_stats()
        elif base_path == '/api/admin/provider-stats':
            # SESSION 68: Provider usage statistics
            self.handle_provider_stats()
        elif base_path == '/api/admin/cost-estimate':
            # SESSION 68: Cost estimation endpoint
            self.handle_cost_estimate()
        elif base_path == '/admin/status':
            # SESSION 299: Admin status endpoint for pipeline health
            self.serve_admin_status()
        elif base_path.startswith('/api/operational-issues/'):
            # SESSION 90: SeeClickFix operational complaints
            # GET /api/operational-issues/{jurisdiction_id}?per_page=20&page=1&status=open
            path_parts = base_path.split('/')
            if len(path_parts) >= 4:
                jurisdiction_id = path_parts[3]
                self.serve_operational_issues(jurisdiction_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/events/') and 'drafts' in base_path:
            # GET /api/events/{event_id}/drafts?user_id=xyz (all drafts)
            # GET /api/events/{event_id}/draft-comment?user_id=xyz (single most recent draft)
            path_parts = base_path.split('/')
            print(f"[civic_api] DEBUG drafts route: path_parts={path_parts}, len={len(path_parts)}")
            if len(path_parts) >= 4:
                event_id = path_parts[3]
                print(f"[civic_api] DEBUG: event_id={event_id}, checking routes...")
                if 'draft-comment' in base_path:
                    print(f"[civic_api] Routing to handle_get_draft")
                    self.handle_get_draft(event_id)
                elif len(path_parts) >= 5 and path_parts[4] == 'drafts':
                    print(f"[civic_api] Routing to handle_get_all_drafts")
                    self.handle_get_all_drafts(event_id)
                else:
                    print(f"[civic_api] DEBUG: No route match! path_parts[4]={path_parts[4] if len(path_parts) > 4 else 'N/A'}")
                    self.send_error(404)
            else:
                print(f"[civic_api] DEBUG: path_parts too short!")
                self.send_error(404)
        elif base_path.startswith('/api/events/'):
            # Extract opportunity ID from path
            opp_id = base_path.split('/')[-1]
            self.serve_single_opportunity(opp_id)
        elif base_path.startswith('/api/issues/'):
            # Handle issue-specific endpoints
            path_parts = base_path.split('/')
            if len(path_parts) >= 4:
                issue_id = path_parts[3]
                if len(path_parts) >= 5 and path_parts[4] == 'status-history':
                    # GET /api/issues/{id}/status-history
                    self.serve_issue_status_history(issue_id)
                elif len(path_parts) >= 5 and path_parts[4] == 'timeline':
                    # GET /api/issues/{id}/timeline
                    self.serve_issue_timeline(issue_id)
                elif len(path_parts) == 4:
                    # GET /api/issues/{id}
                    self.serve_single_issue(issue_id)
                else:
                    self.send_error(404)
            else:
                # GET /api/issues?user_id={user_id}
                parsed_url = urlparse(self.path)
                query_params = parse_qs(parsed_url.query)
                user_id = query_params.get('user_id', [None])[0]
                if user_id:
                    self.serve_user_issues(user_id)
                else:
                    self.send_json({'error': 'user_id parameter required'}, 400)
        elif base_path == '/api/issues':
            # GET /api/issues?user_id={user_id} (user_id optional - if omitted, returns all issues)
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            user_id = query_params.get('user_id', [None])[0]
            self.serve_user_issues(user_id)  # user_id can be None for "all issues"
        elif base_path == '/api/follows':
            # GET /api/follows?user_id={user_id} - Get all follows for a user
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            user_id = query_params.get('user_id', [None])[0]
            if user_id:
                self.serve_user_follows(user_id)
            else:
                self.send_json({'error': 'user_id parameter required'}, 400)
        elif base_path.startswith('/api/follows/'):
            # GET /api/follows/{focal_type}/{focal_id}?user_id={user_id}
            path_parts = base_path.split('/')
            if len(path_parts) >= 5:
                focal_type = path_parts[3]
                focal_id = path_parts[4]
                parsed_url = urlparse(self.path)
                query_params = parse_qs(parsed_url.query)
                user_id = query_params.get('user_id', [None])[0]
                self.serve_follow_info(focal_type, focal_id, user_id)
            else:
                self.send_error(404)
        elif base_path == '/api/legislative/state':
            # Extract topic from query params
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            topic = query_params.get('topic', [None])[0]
            if topic:
                self.serve_legislative_state(topic)
            else:
                self.send_json({'error': 'topic parameter required'}, 400)
        elif base_path == '/api/legislative/federal':
            # Extract topic from query params
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            topic = query_params.get('topic', [None])[0]
            if topic:
                self.serve_legislative_federal(topic)
            else:
                self.send_json({'error': 'topic parameter required'}, 400)
        elif base_path == '/api/threads':
            # GET /api/threads - List all threads
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            jurisdiction_id = query_params.get('jurisdiction', [None])[0]
            self.serve_all_threads(jurisdiction_id)
        elif base_path.startswith('/api/threads/'):
            # GET /api/threads/{thread_id} or GET /api/threads/{thread_id}/messages
            path_parts = base_path.split('/')
            if len(path_parts) >= 4:
                thread_id = path_parts[3]
                if len(path_parts) >= 5 and path_parts[4] == 'messages':
                    # GET /api/threads/{thread_id}/messages
                    parsed_url = urlparse(self.path)
                    query_params = parse_qs(parsed_url.query)
                    user_id = query_params.get('user_id', [None])[0]
                    if user_id:
                        self.serve_thread_messages(thread_id, user_id)
                    else:
                        self.send_json({'error': 'user_id parameter required'}, 400)
                else:
                    # GET /api/threads/{thread_id} - Get thread details
                    self.serve_thread_info(thread_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/legistar/'):
            # Handle Legistar API endpoints: /api/legistar/{city}/events
            path_parts = base_path.split('/')
            if len(path_parts) >= 5 and path_parts[4] == 'events':
                city = path_parts[3]
                self.serve_legistar_events(city)
            else:
                self.send_error(404)
        elif base_path == '/api/refresh':
            self.refresh_data()
        elif base_path.startswith('/api/agenda/'):
            # Handle agenda integration endpoints: /api/agenda/{event_id}/discover, /api/agenda/{event_id}/parse
            path_parts = base_path.split('/')
            if len(path_parts) >= 4:
                event_id = path_parts[3]
                if len(path_parts) >= 5:
                    action = path_parts[4]
                    if action == 'discover':
                        self.serve_agenda_discovery(event_id)
                    elif action == 'parse':
                        self.serve_agenda_parsing(event_id)
                    else:
                        self.send_error(404)
                else:
                    self.serve_agenda_status(event_id)
            else:
                self.send_error(404)
        elif base_path == '/api/user/location':
            # GET /api/user/location?user_id={user_id}
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            user_id = query_params.get('user_id', [None])[0]
            if user_id:
                self.serve_user_location(user_id)
            else:
                self.send_json({'error': 'user_id parameter required'}, 400)
        elif base_path == '/api/config/google-maps-key':
            # Public endpoint to get Google Maps API key for frontend Places Autocomplete
            # API key should be restricted by HTTP referrer in Google Cloud Console
            self.serve_google_maps_key()
        elif base_path == '/api/user/profile':
            # GET /api/user/profile - Get authenticated user's profile
            self.serve_user_profile()
        elif base_path == '/api/user/civic-history':
            # GET /api/user/civic-history - Get user's civic action history
            self.serve_user_civic_history()
        elif base_path == '/api/user/context':
            # GET /api/user/context?type={demographics|interests|history|full}
            self.serve_user_context()
        elif base_path == '/api/user/export':
            # GET /api/user/export - GDPR data export
            self.serve_user_export()
        elif base_path == '/api/onboarding/cards':
            # GET /api/onboarding/cards - Generate Values Explorer cards (PUBLIC)
            # Privacy-first: No authentication required, no user tracking
            self.serve_onboarding_cards()
        elif base_path in ['/api/status', '/health']:
            self.serve_status()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests with authentication and rate limiting"""
        # Session 246: Request logging with correlation ID
        # Session 296: Store as instance vars for request completion logging
        self._request_start_time = time.time()
        self._request_method = "POST"
        correlation_id = set_correlation_id() if 'set_correlation_id' in dir() else str(uuid.uuid4())[:8]
        client_ip = self.client_address[0] if self.client_address else None

        # Log request start
        logger.info("request_start", extra={
            "method": "POST",
            "path": self.path,
            "client_ip": client_ip,
            "correlation_id": correlation_id
        })

        # Check rate limit first
        client_id = rate_limiter.get_client_id(self)
        allowed, limit_info = rate_limiter.check_rate_limit(client_id)

        if not allowed:
            self.send_rate_limit_error(limit_info)
            return

        # Authenticate all requests
        if not self.authenticate_request():
            self.send_auth_error()
            return

        # Parse path for issue-specific endpoints
        from urllib.parse import urlparse
        parsed_url = urlparse(self.path)
        base_path = parsed_url.path

        if self.path == '/api/conversation':
            self.handle_conversation()
        elif self.path == '/api/chat/route':
            self.handle_route_chat()
        elif self.path == '/api/refresh-data':
            self.handle_manual_refresh()
        elif self.path == '/api/issues':
            self.handle_file_issue()
        elif base_path.startswith('/api/issues/'):
            # Handle issue-specific POST endpoints
            path_parts = base_path.split('/')
            if len(path_parts) >= 5 and path_parts[4] == 'link-events':
                # POST /api/issues/{id}/link-events
                issue_id = path_parts[3]
                self.handle_link_events(issue_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/drafts/') and '/submit' in base_path:
            # POST /api/drafts/{draft_id}/submit
            path_parts = base_path.split('/')
            if len(path_parts) >= 5 and path_parts[4] == 'submit':
                draft_id = path_parts[3]
                self.handle_mark_draft_submitted(draft_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/events/'):
            # Handle event-specific POST endpoints
            path_parts = base_path.split('/')
            print(f"[civic_api] DEBUG POST /api/events/: path_parts={path_parts}, len={len(path_parts)}")

            # Check for per-item regenerate endpoint first (Session 47)
            # POST /api/events/{event_id}/items/{item_ref}/regenerate
            if len(path_parts) >= 7 and path_parts[4] == 'items' and path_parts[6] == 'regenerate':
                event_id = path_parts[3]
                item_ref = path_parts[5]
                print(f"[civic_api] DEBUG: Calling handle_regenerate_item_comment with event_id={event_id}, item_ref={item_ref}")
                self.handle_regenerate_item_comment(event_id, item_ref)
            elif len(path_parts) >= 5 and path_parts[4] == 'draft-comment':
                # POST /api/events/{id}/draft-comment
                event_id = path_parts[3]
                print(f"[civic_api] DEBUG: Calling handle_draft_comment with event_id={event_id}")
                self.handle_draft_comment(event_id)
            else:
                print(f"[civic_api] DEBUG: No match for event endpoints")
                self.send_error(404)
        elif self.path == '/api/follows':
            self.handle_create_follow()
        elif base_path.startswith('/api/threads/'):
            # POST /api/threads/{thread_id}/messages
            path_parts = base_path.split('/')
            if len(path_parts) >= 5 and path_parts[4] == 'messages':
                thread_id = path_parts[3]
                self.handle_send_message(thread_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/follows/') and '/mark-read' in base_path:
            # POST /api/follows/{focal_type}/{focal_id}/mark-read
            path_parts = base_path.split('/')
            if len(path_parts) >= 6 and path_parts[5] == 'mark-read':
                focal_type = path_parts[3]
                focal_id = path_parts[4]
                self.handle_mark_thread_read(focal_type, focal_id)
            else:
                self.send_error(404)
        elif self.path == '/api/user/location':
            self.handle_set_user_location()
        elif self.path == '/api/user/profile':
            # POST /api/user/profile - Create or update user profile
            self.handle_user_profile()
        elif self.path == '/api/research':
            # POST /api/research - Answer factual queries from cached data
            self.handle_research_query()
        elif base_path == '/api/admin/trigger':
            # SESSION 302: Admin manual trigger operations
            self.handle_admin_trigger()
        else:
            self.send_error(404)

    def do_PUT(self):
        """Handle PUT requests with authentication and rate limiting"""
        # Session 296: Store as instance vars for request completion logging
        self._request_start_time = time.time()
        self._request_method = "PUT"

        # Check rate limit first
        client_id = rate_limiter.get_client_id(self)
        allowed, limit_info = rate_limiter.check_rate_limit(client_id)

        if not allowed:
            self.send_rate_limit_error(limit_info)
            return

        # Authenticate all requests
        if not self.authenticate_request():
            self.send_auth_error()
            return

        # Parse path to handle issue status updates
        parsed_url = urlparse(self.path)
        base_path = parsed_url.path

        if base_path.startswith('/api/drafts/'):
            # PUT /api/drafts/{draft_id}
            path_parts = base_path.split('/')
            if len(path_parts) >= 4:
                draft_id = path_parts[3]
                self.handle_update_draft(draft_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/issues/'):
            path_parts = base_path.split('/')
            if len(path_parts) >= 5 and path_parts[4] == 'status':
                # PUT /api/issues/{id}/status
                issue_id = path_parts[3]
                self.handle_update_issue_status(issue_id)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_DELETE(self):
        """Handle DELETE requests with authentication and rate limiting"""
        # Session 296: Store as instance vars for request completion logging
        self._request_start_time = time.time()
        self._request_method = "DELETE"

        # Check rate limit first
        client_id = rate_limiter.get_client_id(self)
        allowed, limit_info = rate_limiter.check_rate_limit(client_id)

        if not allowed:
            self.send_rate_limit_error(limit_info)
            return

        # Authenticate all requests
        if not self.authenticate_request():
            self.send_auth_error()
            return

        # Parse path to handle follow deletions
        parsed_url = urlparse(self.path)
        base_path = parsed_url.path

        if base_path == '/api/user':
            # DELETE /api/user - GDPR account deletion
            self.handle_delete_user()
        elif base_path.startswith('/api/drafts/'):
            # DELETE /api/drafts/{draft_id} - SESSION 48
            path_parts = base_path.split('/')
            if len(path_parts) >= 4:
                draft_id = path_parts[3]
                self.handle_delete_draft(draft_id)
            else:
                self.send_error(404)
        elif base_path.startswith('/api/follows/'):
            # DELETE /api/follows/{focal_type}/{focal_id}
            path_parts = base_path.split('/')
            if len(path_parts) >= 5:
                focal_type = path_parts[3]
                focal_id = path_parts[4]
                # Get user_id from query params
                query_params = parse_qs(parsed_url.query)
                user_id = query_params.get('user_id', [None])[0]
                if user_id:
                    self.handle_delete_follow(user_id, focal_type, focal_id)
                else:
                    self.send_json({'error': 'user_id parameter required'}, 400)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def serve_opportunities(self):
        """Serve latest civic events from schema-compliant files with filtering support"""
        try:
            # Parse query parameters
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Extract filter parameters
            jurisdiction_id = query_params.get('jurisdiction_id', [None])[0]
            project_type = query_params.get('project_type', [None])[0]
            start_date = query_params.get('start_date', [None])[0]

            # Find event files
            schema_dir = Path('data/events')
            if not schema_dir.exists():
                self.send_json([])
                return

            # Load events from jurisdiction files
            events = []

            # If jurisdiction_id is specified, load only that jurisdiction's most recent file
            if jurisdiction_id:
                pattern = f'events_{jurisdiction_id}_*.json'
                json_files = sorted(schema_dir.glob(pattern), key=os.path.getmtime, reverse=True)
                if json_files:
                    with open(json_files[0], 'r') as f:
                        event_data = json.load(f)
                        events.extend(event_data.get('events', []))
            else:
                # Load all jurisdiction files (most recent for each jurisdiction)
                # Group files by jurisdiction
                jurisdiction_files = {}
                for file_path in schema_dir.glob('events_*.json'):
                    # Extract jurisdiction_id from filename: events_{jurisdiction_id}_{timestamp}.json
                    filename = file_path.stem
                    parts = filename.split('_')
                    if len(parts) >= 3:
                        jur_id = '_'.join(parts[1:-1])  # Handle multi-part jurisdiction IDs
                        if jur_id not in jurisdiction_files or file_path.stat().st_mtime > jurisdiction_files[jur_id].stat().st_mtime:
                            jurisdiction_files[jur_id] = file_path

                # Load most recent file for each jurisdiction
                for file_path in jurisdiction_files.values():
                    try:
                        with open(file_path, 'r') as f:
                            event_data = json.load(f)
                            events.extend(event_data.get('events', []))
                    except Exception as e:
                        print(f"Error loading {file_path}: {e}")
                        continue

            # Apply filters
            if project_type:
                events = [e for e in events if e.get('project_type') == project_type]

            if start_date:
                from datetime import datetime
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                events = [e for e in events if e.get('when') and datetime.fromisoformat(e['when'].replace('Z', '+00:00')) >= start_dt]

            # Hydrate legislative context for each event
            for event in events:
                legislative_context = event.get('legislative_context')
                if legislative_context:
                    jurisdiction_id = event.get('jurisdiction', {}).get('id')
                    project_type = event.get('project_type', 'general')
                    event['legislative_context'] = self.hydrate_legislative_context(
                        legislative_context,
                        jurisdiction_id,
                        project_type
                    )

            # Return schema-compliant events
            self.send_json(events)

        except Exception as e:
            print(f"[civic_api] ERROR: {str(e)}")
            self.send_error(500, f"Server error: {str(e)}")

    def serve_events_search(self):
        """
        Search events with filtering (Session 28 - Chat UX Refinements)
        Session 56: Enhanced to support multiple jurisdictions/topics
        Session 60: Added "all" jurisdiction support for multi-jurisdiction queries

        Query params:
          - jurisdiction: single (city-berkeley), multiple (city-berkeley,city-oakland), or "all"
          - topics: single (housing) or multiple (housing,transportation)
          - q: text search query
          - date_range: "this week", "next month", "October", etc.
          - itemCountMin: minimum number of agenda items

        Returns:
          {
            "events": [...],  # Filtered event list
            "count": 5,
            "query": {...},    # Echo search params
            "jurisdictions_searched": ["city-berkeley", ...]  # NEW: List of jurisdictions included
          }
        """
        try:
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Extract search parameters (handle both single and comma-separated lists)
            jurisdiction_param = query_params.get('jurisdiction', [None])[0]

            # Session 60: Handle "all" jurisdiction
            if jurisdiction_param and jurisdiction_param.strip().lower() == 'all':
                jurisdictions = []  # Empty list = search all jurisdictions
                search_all = True
            else:
                jurisdictions = [j.strip() for j in jurisdiction_param.split(',')] if jurisdiction_param else []
                search_all = False

            # Support both 'topic' (singular) and 'topics' (plural) for backwards compatibility
            topics_param = query_params.get('topics', [None])[0] or query_params.get('topic', [None])[0]
            topics = [t.strip() for t in topics_param.split(',')] if topics_param else []

            text_query = query_params.get('q', [None])[0]
            date_range = query_params.get('date_range', [None])[0]

            item_count_min_param = query_params.get('itemCountMin', [None])[0]
            item_count_min = int(item_count_min_param) if item_count_min_param else None

            # Load all events
            all_events = self._load_all_events()

            # Track which jurisdictions are included in results
            jurisdictions_searched = set()

            # Filter by jurisdiction(s) - OR condition
            # Session 60: If search_all=True, skip jurisdiction filtering
            if jurisdictions and not search_all:
                filtered_events = []
                for e in all_events:
                    jur_id = e.get('jurisdiction_id') or e.get('jurisdiction', {}).get('id')
                    if jur_id in jurisdictions:
                        filtered_events.append(e)
                        jurisdictions_searched.add(jur_id)
                all_events = filtered_events
            elif not search_all and not jurisdictions:
                # No jurisdiction specified and not "all" → empty results
                all_events = []
            else:
                # search_all=True → include all jurisdictions
                for e in all_events:
                    jur_id = e.get('jurisdiction_id') or e.get('jurisdiction', {}).get('id')
                    if jur_id:
                        jurisdictions_searched.add(jur_id)

            # Filter by topic(s) - OR condition
            # Session 56 fix: Check event.project_type (matches frontend EventsPanel filtering)
            if topics:
                all_events = [e for e in all_events
                             if e.get('project_type') in topics
                             or any(topic in e.get('legislative_context', {}).get('topics', [])
                                   for topic in topics)]

            # Text search (title, description, agenda items)
            if text_query:
                text_query_lower = text_query.lower()
                all_events = [e for e in all_events if self._text_matches_event(e, text_query_lower)]

            # Date range filter
            if date_range:
                start, end = self._parse_date_range(date_range)
                all_events = [e for e in all_events
                             if self._event_in_date_range(e, start, end)]

            # Item count filter
            if item_count_min is not None:
                all_events = [e for e in all_events
                             if len(e.get('agenda_items', [])) >= item_count_min]

            # Sort by date
            all_events.sort(key=lambda e: e.get('start', ''))

            # Return results (Session 60: Added jurisdictions_searched)
            self.send_json({
                "events": all_events,
                "count": len(all_events),
                "query": {
                    "jurisdictions": jurisdictions if not search_all else ["all"],
                    "topics": topics,
                    "q": text_query,
                    "date_range": date_range,
                    "itemCountMin": item_count_min
                },
                "jurisdictions_searched": sorted(list(jurisdictions_searched))  # NEW: Session 60
            })

        except Exception as e:
            print(f"[civic_api] Search ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Search error: {str(e)}")

    def serve_issues_search(self):
        """
        Search user's issues with filtering (Session 63 - Robust Fix)
        Mirrors /api/events/search pattern for consistency.

        Query params:
          - user_id: required - whose issues to search
          - ownership: filter by ownership (mine=user filed, following=user follows, all=both)
          - status: filter by issue status (open=not closed, closed=resolved, matched=has events, all=any)
          - category: issue_type filter (infrastructure, housing, environment, public_safety, other)
          - jurisdiction: city filter (city-berkeley, city-oakland, etc.)
          - q: text search query (searches title, description, address)

        Returns:
          {
            "issues": [...],  # Filtered issue list
            "count": 5,
            "query": {...},    # Echo search params
            "filters_applied": {...}  # Which filters were active
          }
        """
        try:
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Extract search parameters
            user_id = query_params.get('user_id', [None])[0]
            if not user_id:
                self.send_json({'error': 'user_id parameter required'}, 400)
                return

            # Session 63: Separate ownership from status
            ownership = query_params.get('ownership', [None])[0] or 'mine'  # mine/following/all
            status = query_params.get('status', [None])[0] or 'all'  # open/closed/matched/all
            category = query_params.get('category', [None])[0]  # issue_type
            jurisdiction = query_params.get('jurisdiction', [None])[0]
            text_query = query_params.get('q', [None])[0]

            # Load user's issues
            try:
                from issue_storage import IssueStorage
                storage = IssueStorage()
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage
                storage = IssueStorage()

            # Session 63: Load issues based on ownership filter (independent from status)
            all_issues = []

            if ownership == 'following':
                # Load only issues user is following (may be filed by others)
                try:
                    from issue_storage import CommunityStorage
                    community_storage = CommunityStorage()

                    # Get issue IDs user is following
                    followed_issue_ids = set()
                    follows = community_storage.get_user_follows(user_id)
                    for follow in follows:
                        if follow.get('focal_type') == 'issue':
                            followed_issue_ids.add(follow.get('focal_id'))

                    # Load all followed issues (regardless of who filed them)
                    for issue_id in followed_issue_ids:
                        issue = storage.get_issue(issue_id)
                        if issue:
                            all_issues.append(issue)

                except Exception as e:
                    print(f"[civic_api] Error loading followed issues: {e}")
                    import traceback
                    traceback.print_exc()
                    all_issues = []

            elif ownership == 'mine':
                # Load only issues filed by user
                all_issues = storage.get_user_complaints(user_id)

            else:  # ownership == 'all'
                # Load both user's filed issues AND followed issues
                try:
                    # Get user's own issues
                    user_issues = storage.get_user_complaints(user_id)
                    all_issues.extend(user_issues)

                    # Get followed issues (may overlap with user_issues)
                    from issue_storage import CommunityStorage
                    community_storage = CommunityStorage()
                    followed_issue_ids = set()
                    follows = community_storage.get_user_follows(user_id)
                    for follow in follows:
                        if follow.get('focal_type') == 'issue':
                            followed_issue_ids.add(follow.get('focal_id'))

                    # Add followed issues (skip duplicates)
                    existing_ids = {i.get('id') for i in all_issues}
                    for issue_id in followed_issue_ids:
                        if issue_id not in existing_ids:
                            issue = storage.get_issue(issue_id)
                            if issue:
                                all_issues.append(issue)
                except Exception as e:
                    print(f"[civic_api] Error loading all issues: {e}")
                    # Fall back to just user's issues
                    all_issues = storage.get_user_complaints(user_id)

            # Filter by category (issue_type)
            if category and category != 'all':
                all_issues = [i for i in all_issues if i.get('issue_type') == category]

            # Filter by jurisdiction
            if jurisdiction and jurisdiction != 'all':
                all_issues = [i for i in all_issues if i.get('jurisdiction_id') == jurisdiction]

            # Filter by status (independent from ownership - Session 63)
            if status == 'open':
                # Open = not closed (includes pending and matched)
                all_issues = [i for i in all_issues if i.get('status') != 'closed']
            elif status == 'closed':
                # Closed = resolved/completed
                all_issues = [i for i in all_issues if i.get('status') == 'closed']
            elif status == 'matched':
                # Has matched events
                all_issues = [i for i in all_issues
                             if len(i.get('matched_events', [])) > 0]

            # Text search (title, description, address)
            if text_query:
                text_query_lower = text_query.lower()
                all_issues = [i for i in all_issues
                             if self._text_matches_issue(i, text_query_lower)]

            # Sort by created_at (most recent first)
            all_issues.sort(key=lambda i: i.get('created_at', ''), reverse=True)

            # Return results
            self.send_json({
                "issues": all_issues,
                "count": len(all_issues),
                "query": {
                    "user_id": user_id,
                    "ownership": ownership,
                    "status": status,
                    "category": category,
                    "jurisdiction": jurisdiction,
                    "q": text_query
                },
                "filters_applied": {
                    "ownership": ownership if ownership and ownership != 'all' else None,
                    "status": status if status and status != 'all' else None,
                    "category": category if category and category != 'all' else None,
                    "jurisdiction": jurisdiction if jurisdiction and jurisdiction != 'all' else None,
                    "text_search": bool(text_query)
                }
            })

        except Exception as e:
            print(f"[civic_api] Issues search ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Issues search error: {str(e)}")

    def _text_matches_issue(self, issue: Dict, query: str) -> bool:
        """Check if text query matches issue fields"""
        searchable = ' '.join([
            issue.get('title', ''),
            issue.get('description', ''),
            issue.get('address', ''),
            issue.get('issue_type', '')
        ]).lower()
        return query in searchable

    def _load_all_events(self) -> List[Dict]:
        """Load all events from JSON files"""
        events = []
        schema_dir = Path('data/events')

        if not schema_dir.exists():
            return events

        # Group files by jurisdiction to get most recent
        jurisdiction_files = {}
        for file_path in schema_dir.glob('events_*.json'):
            filename = file_path.stem
            parts = filename.split('_')
            if len(parts) >= 3:
                jur_id = '_'.join(parts[1:-1])
                if jur_id not in jurisdiction_files or file_path.stat().st_mtime > jurisdiction_files[jur_id].stat().st_mtime:
                    jurisdiction_files[jur_id] = file_path

        # Load most recent file for each jurisdiction
        for file_path in jurisdiction_files.values():
            try:
                with open(file_path, 'r') as f:
                    event_data = json.load(f)
                    events.extend(event_data.get('events', []))
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

        return events

    def _text_matches_event(self, event: Dict, query: str) -> bool:
        """Check if query matches event text"""
        # Search in title
        if query in event.get('title', '').lower():
            return True

        # Search in description
        if query in event.get('description', '').lower():
            return True

        # Search in agenda items
        for item in event.get('agenda_items', []):
            if query in item.get('title', '').lower():
                return True
            if query in item.get('description', '').lower():
                return True

        return False

    def _parse_date_range(self, range_str: str) -> tuple:
        """Parse natural language date range"""
        from datetime import datetime, timedelta
        today = datetime.now()

        range_str_lower = range_str.lower()

        if range_str_lower == "this week":
            start = today
            end = today + timedelta(days=7)
        elif range_str_lower == "next week":
            start = today + timedelta(days=7)
            end = today + timedelta(days=14)
        elif range_str_lower == "next month":
            start = today
            end = today + timedelta(days=30)
        elif range_str_lower == "this month":
            start = today.replace(day=1)
            end = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            # Try to parse month name
            try:
                # Parse month name like "October"
                month_start = datetime.strptime(range_str, "%B")
                start = month_start.replace(year=today.year)
                # If month is in the past, assume next year
                if start.month < today.month:
                    start = start.replace(year=today.year + 1)
                # End of month
                if start.month == 12:
                    end = start.replace(year=start.year + 1, month=1, day=1)
                else:
                    end = start.replace(month=start.month + 1, day=1)
            except:
                # Default to next 30 days
                start = today
                end = today + timedelta(days=30)

        return (start, end)

    def _event_in_date_range(self, event: Dict, start: datetime, end: datetime) -> bool:
        """Check if event is within date range"""
        try:
            # Parse ISO datetime string
            event_start = datetime.fromisoformat(event.get('start', '').replace('Z', '+00:00'))
            # Remove timezone info for comparison
            event_start = event_start.replace(tzinfo=None)
            return start <= event_start <= end
        except:
            # If parsing fails, include the event
            return True

    def serve_single_opportunity(self, opp_id):
        """Serve a single opportunity by ID"""
        try:
            # Load events and find the matching one
            schema_dir = Path('data/events')
            print(f"[serve_single_opportunity] Looking for events in: {schema_dir.absolute()}")
            print(f"[serve_single_opportunity] Current working directory: {os.getcwd()}")
            json_files = list(schema_dir.glob('events_*.json'))
            print(f"[serve_single_opportunity] Found {len(json_files)} event files")

            if not json_files:
                self.send_error(404, "Event not found - no data files available")
                return

            # Search through all event files for the matching event
            for json_file in json_files:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Search through events array
                for event in data.get('events', []):
                    if event.get('id') == opp_id:
                        # Return the event directly - it already matches the CivicEvent schema
                        self.send_json(event)
                        return

            self.send_error(404, f"Event {opp_id} not found")

        except Exception as e:
            print(f"[civic_api] ERROR serving opportunity {opp_id}: {str(e)}")
            self.send_error(500, f"Server error: {str(e)}")

    def serve_jurisdictions(self):
        """
        Aggregate jurisdictions from event data with counts and metadata.

        Response format:
        [
          {
            "id": "city-berkeley",
            "name": "Berkeley",
            "type": "city",
            "event_count": 35,
            "issue_count": 12,
            "cdbg_allocation": "$2.67M"
          }
        ]
        """
        try:
            import glob
            import re
            from pathlib import Path

            # Import automated_civic_refresh to access CITY_CONFIGS
            try:
                from automated_civic_refresh import CITY_CONFIGS
            except ImportError:
                import sys
                sys.path.insert(0, str(Path(__file__).parent))
                from automated_civic_refresh import CITY_CONFIGS

            # Import issue storage for issue counts
            try:
                from issue_storage import IssueStorage
                storage = IssueStorage()
                complaint_storage_available = True
            except Exception as e:
                print(f"[civic_api] Warning: Could not load issue storage: {e}")
                complaint_storage_available = False

            # 1. List all event files
            schema_dir = Path('data/events')
            if not schema_dir.exists():
                self.send_json({'jurisdictions': [], 'message': 'No event data available'})
                return

            event_files = list(schema_dir.glob('events_*.json'))

            # 2. Extract jurisdiction_id from filenames and count events
            jurisdiction_counts = {}
            for file_path in event_files:
                # Pattern: events_{jurisdiction_id}_{date}_{time}.json (e.g., events_city-berkeley_20251013_100328.json)
                match = re.match(r'events_([a-z0-9\-]+)_\d{8}_\d{6}\.json', file_path.name)
                if match:
                    jurisdiction_id = match.group(1)

                    # Count events in this file
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                            event_count = len(data.get('events', []))

                            # Keep track of highest count for each jurisdiction
                            if jurisdiction_id not in jurisdiction_counts:
                                jurisdiction_counts[jurisdiction_id] = event_count
                            else:
                                # Use max count across multiple files
                                jurisdiction_counts[jurisdiction_id] = max(
                                    jurisdiction_counts[jurisdiction_id],
                                    event_count
                                )
                    except Exception as e:
                        print(f"[civic_api] Warning: Could not parse {file_path.name}: {e}")

            # 3. Build jurisdiction list with metadata
            jurisdictions = []
            for jurisdiction_id, event_count in jurisdiction_counts.items():
                # Get jurisdiction metadata from CITY_CONFIGS
                jurisdiction_name = jurisdiction_id.replace('-', ' ').title()
                jurisdiction_type = 'city'

                # Find matching config
                for city_key, config in CITY_CONFIGS.items():
                    if config['jurisdiction_id'] == jurisdiction_id:
                        jurisdiction_name = config.get('jurisdiction_id', jurisdiction_id).replace('city-', '').replace('-', ' ').title()
                        if jurisdiction_id.startswith('county-'):
                            jurisdiction_type = 'county'
                        elif jurisdiction_id == 'bart':
                            jurisdiction_type = 'transit_agency'
                        break

                # 4. Query database for issue counts (issues)
                issue_count = 0
                if complaint_storage_available:
                    try:
                        import sqlite3
                        with sqlite3.connect(storage.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT COUNT(*) FROM issues
                                WHERE jurisdiction_id = ?
                            """, (jurisdiction_id,))
                            issue_count = cursor.fetchone()[0]
                    except Exception as e:
                        print(f"[civic_api] Warning: Could not query issues for {jurisdiction_id}: {e}")

                # 5. Load CDBG allocation from jurisdiction overrides
                cdbg_allocation = None
                override_path = Path(f'data/jurisdiction_overrides/{jurisdiction_id}.json')
                if override_path.exists():
                    try:
                        with open(override_path, 'r') as f:
                            override_data = json.load(f)
                            allocation_amount = override_data.get('federal_programs', {}).get('cdbg', {}).get('fy2025_allocation')
                            if allocation_amount:
                                # Format as currency (e.g., $2.67M)
                                if allocation_amount >= 1_000_000:
                                    cdbg_allocation = f"${allocation_amount / 1_000_000:.2f}M"
                                else:
                                    cdbg_allocation = f"${allocation_amount / 1_000:.0f}K"
                    except Exception as e:
                        print(f"[civic_api] Warning: Could not load CDBG data for {jurisdiction_id}: {e}")

                # Get county and state from COUNTY_MAPPING
                hierarchy = COUNTY_MAPPING.get(jurisdiction_id, {})
                county = hierarchy.get('county')
                state = hierarchy.get('state', 'California')

                # Build jurisdiction object
                jurisdictions.append({
                    'id': jurisdiction_id,
                    'name': jurisdiction_name,
                    'type': jurisdiction_type,
                    'county': county,
                    'state': state,
                    'event_count': event_count,
                    'issue_count': issue_count,
                    'cdbg_allocation': cdbg_allocation
                })

            # Sort by event count descending
            jurisdictions.sort(key=lambda x: x['event_count'], reverse=True)

            self.send_json({
                'jurisdictions': jurisdictions,
                'metadata': {
                    'total_jurisdictions': len(jurisdictions),
                    'total_events': sum(j['event_count'] for j in jurisdictions),
                    'total_issues': sum(j['issue_count'] for j in jurisdictions)
                }
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving jurisdictions: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_operational_issues(self, jurisdiction_id: str):
        """
        Fetch operational issues from SeeClickFix for a given jurisdiction.

        Session 90: SeeClickFix integration - operational complaint→policy bridge

        Query parameters:
        - per_page: Results per page (default: 20, max: 100)
        - page: Page number (default: 1)
        - status: Filter by status - "open", "closed", "acknowledged", or None for all (default: "open")

        Response format:
        {
          "issues": [...],
          "metadata": {
            "page": 1,
            "per_page": 20,
            "total_pages": 5,
            "has_more": true,
            "source": "seeclickfix",
            "jurisdiction": "san-rafael",
            "issue_type": "operational"
          }
        }
        """
        if not SEECLICKFIX_AVAILABLE:
            self.send_json({
                'error': 'SeeClickFix integration not available',
                'issues': [],
                'metadata': {'source': 'seeclickfix', 'error': 'Integration unavailable'}
            }, 503)
            return

        try:
            # Parse query parameters
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            per_page = int(query_params.get('per_page', ['20'])[0])
            page = int(query_params.get('page', ['1'])[0])
            status = query_params.get('status', ['open'])[0]

            # Validate parameters
            per_page = min(max(per_page, 1), 100)  # Clamp to 1-100
            page = max(page, 1)  # Minimum page 1

            # Map jurisdiction_id to place_url for SeeClickFix
            # Handle multiple jurisdiction_id formats:
            # - "city-san-rafael" → "san-rafael"
            # - "sanrafael" → "san-rafael"
            JURISDICTION_TO_PLACE_URL = {
                'city-san-rafael': 'san-rafael',
                'sanrafael': 'san-rafael',
                'san-rafael': 'san-rafael',
                # Add more cities as needed
            }

            place_url = JURISDICTION_TO_PLACE_URL.get(
                jurisdiction_id.lower(),
                jurisdiction_id.replace('city-', '')  # Fallback: strip city- prefix
            )

            print(f"[civic_api] Fetching operational issues for {jurisdiction_id} (place_url: {place_url})")
            print(f"[civic_api] Parameters: per_page={per_page}, page={page}, status={status}")

            # Initialize SeeClickFix client
            client = SeeClickFixClient()

            # Fetch issues
            result = client.get_issues(
                place_url=place_url,
                per_page=per_page,
                page=page,
                status=status if status != 'all' else None
            )

            # Enhance metadata
            result['metadata']['source'] = 'seeclickfix'
            result['metadata']['jurisdiction'] = jurisdiction_id
            result['metadata']['issue_type'] = 'operational'

            print(f"[civic_api] ✅ Found {len(result['issues'])} operational issues")

            self.send_json(result)

        except ValueError as e:
            print(f"[civic_api] Invalid parameter: {str(e)}")
            self.send_json({
                'error': f'Invalid parameter: {str(e)}',
                'issues': [],
                'metadata': {}
            }, 400)
        except Exception as e:
            print(f"[civic_api] ERROR serving operational issues: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_json({
                'error': f'Server error: {str(e)}',
                'issues': [],
                'metadata': {}
            }, 500)

    def serve_user_issues(self, user_id: str = None):
        """
        Retrieve issues with matched events.
        If user_id is provided, returns only that user's issues.
        If user_id is None, returns all issues.

        Note: Status is lifecycle-based (open | escalated | resolved).
        Check matched_events.length > 0 to determine if matches exist.

        Response format:
        [
          {
            "id": "issue-uuid",
            "user_id": "user123",
            "description": "Pothole on Main St",
            "issue_type": "transportation",
            "jurisdiction_id": "city-berkeley",
            "status": "open",
            "created_at": "2025-10-13T10:00:00Z",
            "updated_at": "2025-10-13T11:00:00Z",
            "matched_events": [
              {
                "event_id": "event-123",
                "match_score": 0.85,
                "match_reason": "Transportation topic + Main St location"
              }
            ],
            "related_complaints": ["issue-uuid-2"],
            "discussion_group_id": null
          }
        ]
        """
        try:
            # Import issue storage
            try:
                from issue_storage import IssueStorage
                storage = IssueStorage()
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage
                storage = IssueStorage()

            # Get issues (all or filtered by user_id)
            if user_id:
                issues = storage.get_user_complaints(user_id)
            else:
                # Get all issues (no user filter)
                issues = self._get_all_issues(storage)

            # Format response to match TypeScript Complaint interface
            formatted_complaints = []
            for issue in issues:
                formatted_complaints.append({
                    'id': issue['id'],
                    'user_id': issue['user_id'],
                    'description': issue['description'],
                    'issue_type': issue.get('issue_type'),
                    'jurisdiction_id': issue['jurisdiction_id'],
                    'status': issue['status'],
                    'created_at': issue['created_at'],
                    'updated_at': issue['updated_at'],
                    'matched_events': issue.get('matched_events', []),
                    'related_issues': issue.get('related_complaints', []),
                    'discussion_group_id': issue.get('discussion_group_id'),
                    'location': {
                        'address': issue.get('address'),
                        'latitude': issue.get('latitude'),
                        'longitude': issue.get('longitude')
                    } if issue.get('address') else None,
                    # AI-generated content
                    'ai_title': issue.get('ai_title'),
                    'ai_summary': issue.get('ai_summary'),
                    'ai_generated_at': issue.get('ai_generated_at'),
                    # Short name (KEYWORD-123 format)
                    'short_name': f"{issue.get('short_name_keyword')}-{issue.get('short_name_number')}" if issue.get('short_name_keyword') else None
                })

            self.send_json({
                'issues': formatted_complaints,
                'metadata': {
                    'total_complaints': len(formatted_complaints),
                    'matched_count': len([c for c in formatted_complaints if c['matched_events']]),
                    'open_count': len([c for c in formatted_complaints if c['status'] == 'open'])
                }
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving user issues: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def _get_all_issues(self, storage):
        """
        Get all issues from all users (no user_id filter).
        Used when ownership filter is set to "All".
        """
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all issues (no user filter)
            cursor.execute("""
                SELECT * FROM issues
                ORDER BY created_at DESC
            """)

            issues = []
            for row in cursor.fetchall():
                issue = dict(row)

                # Load matched events for this issue
                cursor.execute("""
                    SELECT event_id, match_score, match_reason
                    FROM issue_event_matches
                    WHERE issue_id = ?
                    ORDER BY
                        CASE WHEN match_score IS NULL THEN 1 ELSE 0 END,
                        match_score DESC
                """, (issue['id'],))

                issue["matched_events"] = [
                    {
                        "event_id": r[0],
                        "match_score": r[1],
                        "match_reason": r[2]
                    }
                    for r in cursor.fetchall()
                ]

                # Find similar issues
                if issue.get('issue_type'):
                    similar = storage.find_similar_issues(
                        issue['jurisdiction_id'],
                        issue['issue_type']
                    )
                    # Exclude self from similar issues
                    issue['related_complaints'] = [
                        s['id'] for s in similar if s['id'] != issue['id']
                    ]
                else:
                    issue['related_complaints'] = []

                issues.append(issue)

            return issues

    def serve_single_issue(self, issue_id: str):
        """
        Retrieve a single issue by ID.

        GET /api/issues/{id}

        Note: Status is lifecycle-based (open | escalated | resolved).
        Check matched_events.length > 0 to determine if matches exist.

        Response format:
        {
          "id": "issue-uuid",
          "user_id": "user123",
          "description": "Pothole on Main St",
          "issue_type": "transportation",
          "jurisdiction_id": "city-berkeley",
          "status": "open",
          "created_at": "2025-10-13T10:00:00Z",
          "updated_at": "2025-10-13T11:00:00Z",
          "matched_events": [...],
          "related_complaints": [...],
          "discussion_group_id": null,
          "location": {...}
        }
        """
        try:
            # Import issue storage
            try:
                from issue_storage import IssueStorage
                storage = IssueStorage()
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage
                storage = IssueStorage()

            # Get issue by ID
            issue = storage.get_issue(issue_id)

            if not issue:
                self.send_json({'error': f'Complaint {issue_id} not found'}, 404)
                return

            # Format response to match TypeScript Complaint interface
            formatted_complaint = {
                'id': issue['id'],
                'user_id': issue['user_id'],
                'description': issue['description'],
                'issue_type': issue.get('issue_type'),
                'jurisdiction_id': issue['jurisdiction_id'],
                'status': issue['status'],
                'created_at': issue['created_at'],
                'updated_at': issue['updated_at'],
                'matched_events': issue.get('matched_events', []),
                'related_issues': issue.get('related_complaints', []),
                'discussion_group_id': issue.get('discussion_group_id'),
                'location': {
                    'address': issue.get('address'),
                    'latitude': issue.get('latitude'),
                    'longitude': issue.get('longitude')
                } if issue.get('address') else None,
                # AI-generated content
                'ai_title': issue.get('ai_title'),
                'ai_summary': issue.get('ai_summary'),
                'ai_generated_at': issue.get('ai_generated_at'),
                # Short name (KEYWORD-123 format)
                'short_name': f"{issue.get('short_name_keyword')}-{issue.get('short_name_number')}" if issue.get('short_name_keyword') else None
            }

            self.send_json(formatted_complaint)

        except Exception as e:
            print(f"[civic_api] ERROR serving single issue: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_file_issue(self):
        """
        Handle POST /api/issues - File a new issue with automatic event matching.

        Request format:
        {
          "user_id": "user123",
          "description": "There is a huge pothole on Main Street",
          "jurisdiction_id": "city-berkeley",
          "issue_type": "transportation",  # Optional: housing, transportation, environment, etc.
          "location": {  # Optional
            "address": "Main St & 5th Ave",
            "latitude": 37.8715,
            "longitude": -122.2730
          }
        }

        Response format:
        {
          "issue_id": "uuid",
          "status": "open",  # Always 'open' on creation (lifecycle status)
          "matched_events": [  # Check .length > 0 to determine if matches exist
            {
              "event_id": "event-123",
              "title": "Transportation Committee Meeting",
              "when": "2025-10-15T18:00:00",
              "match_score": 0.85,
              "match_reason": "Transportation topic + Main St location"
            }
          ],
          "message": "Found 2 relevant civic meetings where you can address this issue"
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            user_id = data.get('user_id')
            description = data.get('description')
            jurisdiction_id = data.get('jurisdiction_id')

            if not user_id:
                self.send_json({'error': 'user_id is required'}, 400)
                return
            if not description:
                self.send_json({'error': 'description is required'}, 400)
                return
            if not jurisdiction_id:
                self.send_json({'error': 'jurisdiction_id is required'}, 400)
                return

            # Extract optional fields
            issue_type = data.get('issue_type')
            location = data.get('location')

            # Import storage
            try:
                from issue_storage import IssueStorage, CommunityStorage
                from issue_matcher import match_issue_to_events
                from issue_detector import IssueDetector
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage, CommunityStorage
                from issue_matcher import match_issue_to_events
                from issue_detector import IssueDetector

            storage = IssueStorage()
            community_storage = CommunityStorage()

            # Auto-detect issue_type if not provided
            if not issue_type or issue_type.strip() == '':
                print(f"[civic_api] Auto-detecting issue_type for issue...")
                try:
                    detector = IssueDetector()
                    user_context = {'jurisdiction_id': jurisdiction_id}
                    intent = detector.detect_complaint(description, user_context)
                    if intent and intent.issue_type:
                        issue_type = intent.issue_type
                        print(f"[civic_api] Auto-detected issue_type: {issue_type}")
                    else:
                        # Fallback to 'other' if detection fails
                        issue_type = 'other'
                        print(f"[civic_api] Could not auto-detect issue_type, defaulting to 'other'")
                except Exception as e:
                    print(f"[civic_api] WARNING: Auto-detection failed: {str(e)}, defaulting to 'other'")
                    issue_type = 'other'

            # Create issue
            issue_id = storage.create_issue(
                user_id=user_id,
                description=description,
                jurisdiction_id=jurisdiction_id,
                issue_type=issue_type,
                location=location
            )

            print(f"[civic_api] Created issue {issue_id} for user {user_id}")

            # Get issue for matching
            issue = storage.get_issue(issue_id)
            if not issue:
                self.send_json({'error': 'Failed to create issue'}, 500)
                return

            # Match to events
            matches = match_issue_to_events(issue)

            # Format matched events with full event details
            matched_events = []
            if matches:
                for event_data, score, reason in matches[:5]:  # Top 5 matches
                    # Store match in database
                    storage.link_to_event(
                        issue_id=issue_id,
                        event_id=event_data.get('id', 'unknown'),
                        match_score=score,
                        match_reason=reason
                    )

                    # Format for response
                    matched_events.append({
                        'event_id': event_data.get('id'),
                        'title': event_data.get('title'),
                        'when': event_data.get('when'),
                        'meeting_type': event_data.get('meeting_type'),
                        'match_score': round(score, 2),
                        'match_reason': reason
                    })

            # Auto-follow matched events (Task 1: Complaint→Discussion Integration)
            if matched_events:
                for match in matched_events:
                    event_id = match['event_id']
                    event_title = match['title']

                    try:
                        # Create follow + coordination thread
                        follow_result = community_storage.create_follow(
                            user_id=user_id,
                            focal_type='event',
                            focal_id=event_id,
                            jurisdiction_id=jurisdiction_id
                        )

                        thread_id = follow_result['thread_id']

                        # Add timeline entry for issue
                        storage.add_timeline_entry(
                            issue_id=issue_id,
                            event_type='linked',
                            description=f"Automatically following matched event: {event_title}",
                            source='system',
                            metadata={'thread_id': thread_id, 'event_id': event_id}
                        )

                        print(f"[civic_api] Auto-followed event {event_id} for issue {issue_id}")
                    except Exception as e:
                        # Don't fail the whole request if auto-follow fails
                        print(f"[civic_api] WARNING: Failed to auto-follow event {event_id}: {str(e)}")

            # Build response
            # Note: Status is always 'open' on creation (lifecycle status)
            # Clients compute has_matches from matched_events.length > 0
            response = {
                'issue_id': issue_id,
                'status': 'open',
                'matched_events': matched_events,
                'message': self._format_complaint_message(len(matched_events))
            }

            self.send_json(response, 201)
            print(f"[civic_api] Filed issue {issue_id}: {len(matched_events)} matches")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR filing issue: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def _format_complaint_message(self, match_count: int) -> str:
        """Format success message based on match count"""
        if match_count == 0:
            return "Your issue has been recorded. We'll notify you when a relevant civic meeting is scheduled."
        elif match_count == 1:
            return "Found 1 relevant civic meeting where you can address this issue."
        else:
            return f"Found {match_count} relevant civic meetings where you can address this issue."

    def serve_issue_timeline(self, issue_id: str):
        """
        Handle GET /api/issues/{id}/timeline - Retrieve timeline for a issue.

        Response format:
        {
          "timeline": [
            {
              "entry_id": "uuid",
              "issue_id": "uuid",
              "timestamp": "2025-10-13T10:30:00",
              "event_type": "filed",
              "description": "Issue filed",
              "source": "user",
              "metadata": {}
            }
          ]
        }
        """
        try:
            # Import storage
            try:
                from issue_storage import IssueStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage

            storage = IssueStorage()

            # Get timeline entries
            timeline = storage.get_issue_timeline(issue_id)

            self.send_json({
                'timeline': timeline
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving issue timeline: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_issue_status_history(self, issue_id: str):
        """
        Handle GET /api/issues/{id}/status-history - Retrieve status history for an issue.

        Returns only filed + status_change events (user's issue lifecycle).
        Distinct from timeline which filters for government responses.

        Response format:
        {
          "history": [
            {
              "entry_id": "uuid",
              "issue_id": "uuid",
              "timestamp": "2025-10-13T10:30:00",
              "event_type": "filed",
              "description": "Issue filed",
              "source": "user",
              "metadata": {}
            }
          ]
        }
        """
        try:
            # Import storage
            try:
                from issue_storage import IssueStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage

            storage = IssueStorage()

            # Get status history entries
            history = storage.get_issue_status_history(issue_id)

            self.send_json({
                'history': history
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving issue status history: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_update_issue_status(self, issue_id: str):
        """
        Handle PUT /api/issues/{id}/status - Update issue lifecycle status.

        Note: Status is purely lifecycle-based (open | closed with closed_reason).
        Connection status (has_matches) is computed from matched_events.length > 0.

        Request format:
        {
          "status": "open" | "closed",
          "closed_reason": "resolved" | "duplicate" | "not-actionable" | "abandoned" (required if status='closed'),
          "note": "Optional note about status change"
        }

        Response format:
        {
          "success": true,
          "issue_id": "uuid",
          "new_status": "closed",
          "closed_reason": "resolved",
          "message": "Issue status updated"
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            new_status = data.get('status')
            if not new_status:
                self.send_json({'error': 'status is required'}, 400)
                return

            # Validate status value
            valid_statuses = ['open', 'closed']
            if new_status not in valid_statuses:
                self.send_json({'error': f'status must be one of: {", ".join(valid_statuses)}'}, 400)
                return

            # Validate closed_reason if status is 'closed'
            closed_reason = data.get('closed_reason')
            if new_status == 'closed':
                if not closed_reason:
                    self.send_json({'error': 'closed_reason is required when status is "closed"'}, 400)
                    return

                valid_reasons = ['resolved', 'duplicate', 'not-actionable', 'abandoned']
                if closed_reason not in valid_reasons:
                    self.send_json({'error': f'closed_reason must be one of: {", ".join(valid_reasons)}'}, 400)
                    return

            # Extract optional note
            note = data.get('note')

            # Import storage
            try:
                from issue_storage import IssueStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage

            storage = IssueStorage()

            # Check if issue exists
            issue = storage.get_issue(issue_id)
            if not issue:
                self.send_json({'error': 'Issue not found'}, 404)
                return

            # Update status (this also creates a timeline entry)
            storage.update_status(issue_id, new_status, note, closed_reason)

            response = {
                'success': True,
                'issue_id': issue_id,
                'new_status': new_status,
                'message': 'Issue status updated'
            }

            # Include closed_reason in response if provided
            if closed_reason:
                response['closed_reason'] = closed_reason

            self.send_json(response)

        except Exception as e:
            print(f"[civic_api] ERROR updating issue status: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_link_events(self, issue_id: str):
        """
        Handle POST /api/issues/{id}/link-events - Manually link issue to events.

        Request format:
        {
          "event_ids": ["event-id-1", "event-id-2", ...]
        }

        Response format:
        {
          "success": true,
          "issue_id": "uuid",
          "linked_count": 2,
          "message": "Successfully linked 2 events",
          "issue": {...}  // Updated issue with all matched events
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            event_ids = data.get('event_ids')
            if not event_ids:
                self.send_json({'error': 'event_ids is required'}, 400)
                return

            if not isinstance(event_ids, list) or len(event_ids) == 0:
                self.send_json({'error': 'event_ids must be a non-empty array'}, 400)
                return

            # Import storage
            try:
                from issue_storage import IssueStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import IssueStorage

            storage = IssueStorage()

            # Check if issue exists
            issue = storage.get_issue(issue_id)
            if not issue:
                self.send_json({'error': 'Complaint not found'}, 404)
                return

            # Get already linked event IDs to avoid duplicates
            existing_event_ids = {e['event_id'] for e in issue.get('matched_events', [])}

            # Validate that events exist before linking
            from pathlib import Path
            schema_dir = Path('data/events')
            valid_event_ids = set()
            invalid_event_ids = []

            # Load all event IDs from JSON files
            for json_file in schema_dir.glob('events_*.json'):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        for event in data.get('events', []):
                            valid_event_ids.add(event.get('id'))
                except Exception as e:
                    print(f"[civic_api] Warning: Could not read {json_file}: {e}")

            # Filter to only valid, non-duplicate event IDs
            events_to_link = []
            for event_id in event_ids:
                if event_id not in valid_event_ids:
                    invalid_event_ids.append(event_id)
                elif event_id in existing_event_ids:
                    # Skip - already linked
                    pass
                else:
                    events_to_link.append(event_id)

            # Link valid events
            linked_count = 0
            for event_id in events_to_link:
                storage.link_to_event(
                    issue_id=issue_id,
                    event_id=event_id,
                    match_score=None,
                    match_reason=None
                )
                linked_count += 1

            # Get updated issue
            updated_complaint = storage.get_issue(issue_id)

            # Build response message
            message_parts = []
            if linked_count > 0:
                message_parts.append(f'Successfully linked {linked_count} event{"s" if linked_count != 1 else ""}')
            if invalid_event_ids:
                message_parts.append(f'{len(invalid_event_ids)} invalid event ID{"s" if len(invalid_event_ids) != 1 else ""}')

            already_linked = len([e for e in event_ids if e in existing_event_ids])
            if already_linked > 0:
                message_parts.append(f'{already_linked} already linked')

            message = '. '.join(message_parts) if message_parts else 'No changes made'

            self.send_json({
                'success': True,
                'issue_id': issue_id,
                'linked_count': linked_count,
                'invalid_event_ids': invalid_event_ids,
                'message': message,
                'issue': updated_complaint
            })

            print(f"[civic_api] Manually linked {linked_count} events to issue {issue_id}")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR linking events to issue: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def get_cached_item_comment(self, event_id: str, item_ref: str) -> dict | None:
        """
        Check if item comment exists in cache (Session 47).

        Returns dict with content, legislative_context, word_count, generated_at
        or None if not cached.
        """
        db_path = get_user_path('civic_participation.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT content, legislative_context, word_count, generated_at
            FROM item_comment_cache
            WHERE event_id = ? AND item_ref = ?
        ''', (event_id, item_ref))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'content': row[0],
                'legislative_context': json.loads(row[1]) if row[1] else {},
                'word_count': row[2],
                'generated_at': row[3]
            }
        return None

    def cache_item_comment(self, event_id: str, item_ref: str, item_title: str,
                          content: str, legislative_context: dict, word_count: int):
        """
        Store generated item comment in cache (Session 47).
        """
        db_path = get_user_path('civic_participation.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO item_comment_cache
            (event_id, item_ref, item_title, content, legislative_context, word_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (event_id, item_ref, item_title, content, json.dumps(legislative_context), word_count))

        conn.commit()
        conn.close()

    def _log_cache_metric(self, event_id: str, item_ref: str, hit: bool):
        """
        Log cache hit/miss for analytics (Session 48).
        Non-blocking - failures won't crash generation.
        """
        try:
            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO cache_metrics (event_id, item_ref, hit)
                VALUES (?, ?, ?)
            ''', (event_id, item_ref, 1 if hit else 0))

            conn.commit()
            conn.close()
        except Exception as e:
            # Don't crash on metrics logging failure
            print(f"[civic_api] ⚠️ Failed to log cache metric: {e}")

    def generate_single_item_comment(self, event: dict, item: dict,
                                     personal_context: dict, archetypes: list) -> str:
        """
        Generate focused comment for single agenda item with OpenAI (Session 47).

        Returns just the comment text (no greeting/closing - those are added in merge).
        """
        if not OPENAI_AVAILABLE:
            return f"Comment for {item.get('item_ref', 'item')} - {item.get('title', '')}"

        item_title = item.get('title', '')
        item_description = item.get('description', '')
        item_ref = item.get('item_ref', '')
        legislative_context = item.get('legislative_context', {})

        # Build legislative context string
        legislative_context_str = ""
        if legislative_context:
            state_bills = legislative_context.get('state_bills', [])
            federal_programs = legislative_context.get('federal_programs', [])

            if state_bills:
                legislative_context_str += "\n\nRELEVANT STATE LEGISLATION:\n"
                for bill in state_bills[:2]:  # Limit to 2 most relevant
                    legislative_context_str += f"- {bill.get('bill_number', '')}: {bill.get('title', '')}\n"

            if federal_programs:
                legislative_context_str += "\nRELEVANT FEDERAL PROGRAMS:\n"
                for program in federal_programs[:2]:  # Limit to 2 most relevant
                    legislative_context_str += f"- {program.get('program_name', '')}: {program.get('description', '')}\n"

        # Build personal context string
        personal_context_str = ""
        if personal_context:
            years = personal_context.get('yearsInArea', '')
            district = personal_context.get('district', '')
            expertise = personal_context.get('expertise', '')

            if years or district or expertise:
                personal_context_str = "\n\nPERSONAL CONTEXT:\n"
                if years:
                    personal_context_str += f"- Resident for {years} years\n"
                if district:
                    personal_context_str += f"- District: {district}\n"
                if expertise:
                    personal_context_str += f"- Background: {expertise}\n"

        # Build archetype string
        archetype_str = ""
        if archetypes:
            archetype_str = "\n\nCIVIC ARCHETYPE:\n"
            archetype_str += f"- {archetypes[0].get('name', '')}: {archetypes[0].get('description', '')}\n"

        # Build prompt for single item
        prompt = f"""Generate a focused public comment for this specific agenda item.

Event: {event.get('title', '')}
Agenda Item {item_ref}: {item_title}
Description: {item_description}{legislative_context_str}{personal_context_str}{archetype_str}

Generate a 60-100 word comment addressing ONLY this agenda item. Include:
1. Clear position (support/oppose/questions)
2. Personal stake/expertise if relevant
3. Specific legislative references if available (use EXACT bill numbers)
4. Actionable request for council

CRITICAL - Citation Accuracy:
- Use EXACT bill numbers (e.g., "AB 1147", not "AB 117")
- Use EXACT program names and organization names

Format: Plain paragraph(s), no greeting/closing (will be added in merge).
Tone: Professional but conversational, genuinely passionate."""

        client = openai.OpenAI()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a civic engagement assistant helping residents draft effective public comments."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        return response.choices[0].message.content.strip()

    def merge_item_comments(self, item_comments: list, event: dict, personal_context: dict) -> str:
        """
        Merge per-item comments into organized final draft (Session 47).

        Returns complete draft with greeting, organized sections, and closing.
        """
        body_name = event.get('jurisdiction', {}).get('body_name', 'Council Members')

        # Build organized comment sections
        sections = []
        for item_comment in item_comments:
            section = f"""**Item {item_comment['item_ref']}: {item_comment['item_title']}**

{item_comment['content']}"""
            sections.append(section)

        # Personal intro if provided
        intro = ""
        if personal_context:
            years = personal_context.get('yearsInArea', '')
            district = personal_context.get('district', '')
            expertise = personal_context.get('expertise', '')

            intro_parts = []
            if years:
                intro_parts.append(f"resident for {years} years")
            if district:
                intro_parts.append(f"in {district}")
            if expertise:
                intro_parts.append(f"with background in {expertise}")

            if intro_parts:
                intro = f"As a {', '.join(intro_parts)}, "

        # Build final draft
        item_count = len(item_comments)
        plural = 's' if item_count > 1 else ''

        final_draft = f"""Dear {body_name},

{intro}I am writing regarding {item_count} item{plural} on tonight's agenda:

{chr(10).join(sections)}

Thank you for your consideration and service to our community.

Sincerely,
[Your Name]"""

        return final_draft

    def handle_draft_comment(self, event_id: str):
        """
        Handle POST /api/events/{event_id}/draft-comment

        Generate AI-powered public comment draft from structured input.

        Request format:
        {
            "position": "support" | "oppose" | "neutral" | "questions",
            "keyConcern": "1-2 sentence key concern (20-300 chars)",
            "personalContext": {  // Optional
                "stakes": ["homeowner", "parent", ...],
                "yearsInArea": 15,
                "district": "District 3",
                "expertise": "Urban planner"
            },
            "agendaItemIds": ["item-7.2", "item-9.1"]  // Optional - multiple agenda items
            // OR legacy:
            "agendaItemId": "item-7.2"  // Optional - single agenda item (backward compatible)
        }

        Response format:
        {
            "draft": "Dear Council Members,\n\nI am writing to...",
            "word_count": 247,
            "estimated_speaking_time": "1 minute 30 seconds",
            "structured_summary": {
                "tldr": "Brief summary",
                "position": "support",
                "key_topics": ["housing", "transportation"],
                "legislative_references": ["AB 1147", "CDBG"]
            }
        }
        """
        print(f"[civic_api] DEBUG handle_draft_comment: ENTERED with event_id={event_id}")
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            print(f"[civic_api] DEBUG: content_length={content_length}")
            if content_length == 0:
                print(f"[civic_api] DEBUG: No content_length, returning 400")
                self.send_json({'error': 'Request body required'}, 400)
                return

            print(f"[civic_api] DEBUG: Reading request body...")
            body = self.rfile.read(content_length).decode('utf-8')
            print(f"[civic_api] DEBUG: Body read, length={len(body)}")
            data = json.loads(body)
            print(f"[civic_api] DEBUG: JSON parsed successfully")

            # Extract optional fields (AI will infer if not provided)
            position = data.get('position')  # Optional - AI will infer from context
            key_concern = data.get('keyConcern', '')  # Optional - AI will infer from event/agenda
            personal_context = data.get('personalContext', {})

            # Support both single item (legacy) and multiple items (new)
            agenda_item_id = data.get('agendaItemId')  # Legacy: single item
            agenda_item_ids = data.get('agendaItemIds', [])  # New: multiple items
            if agenda_item_id and not agenda_item_ids:
                agenda_item_ids = [agenda_item_id]  # Convert single to list for unified handling

            user_id = data.get('userId')  # Optional - for personalized comment framing
            archetypes = data.get('archetypes', [])  # Optional - user civic archetypes (Privacy Tier 1)
            print(f"[civic_api] DEBUG: Extracted fields - position={position}, key_concern={key_concern[:50] if key_concern else 'None'}, user_id={user_id}, agenda_items={len(agenda_item_ids)}")

            # Load event data
            print(f"[civic_api] DEBUG: Looking for event_id={event_id}")
            event = self._find_event_by_id(event_id)
            print(f"[civic_api] DEBUG: Event found: {event is not None}")
            if not event:
                print(f"[civic_api] DEBUG: Event not found, returning 404")
                self.send_json({'error': 'Event not found'}, 404)
                return
            print(f"[civic_api] DEBUG: Event title: {event.get('title', 'NO TITLE')[:100]}")

            # Extract event details
            event_title = event.get('title', '')
            event_description = event.get('description', '')
            event_date = event.get('when', '')

            # SESSION 44 SIMPLIFIED APPROACH:
            # - If user selects items → generate with those items
            # - If no items selected but good description → generate general comment
            # - If no items selected and generic/missing description → BLOCK (user must select items)
            # Frontend will pre-select all substantive items by default
            #
            # PROCEDURAL ITEM FILTERING (for frontend pre-selection):
            # The frontend should filter out procedural items when pre-selecting:
            # - Roll call, approval of minutes, public comment periods, etc.
            # - Patterns: /public comment|roll call|approval of minutes|council updates|
            #             announcements|miscellaneous|consent calendar|pledge|invocation|closed session/i
            # - Keep: substantive policy discussions (housing, health, transportation, etc.)

            # Define generic/useless description patterns
            GENERIC_DESCRIPTIONS = ['calendar event', 'meeting', 'event', 'agenda', 'council meeting', '']

            # Check if description is good enough for general comment
            description_is_generic = (
                not event_description or
                event_description.strip().lower() in GENERIC_DESCRIPTIONS
            )

            # Get specific agenda items if referenced (supports multiple items)
            agenda_items_context = ""
            matched_items = []
            if agenda_item_ids and 'agenda_expansion' in event:
                actionable_items = event.get('agenda_expansion', {}).get('actionable_items', [])
                print(f"[civic_api] DEBUG: Looking for {len(agenda_item_ids)} agenda items")
                print(f"[civic_api] DEBUG: Requested item IDs: {agenda_item_ids}")
                print(f"[civic_api] DEBUG: Found {len(actionable_items)} actionable items in event")
                if actionable_items:
                    print(f"[civic_api] DEBUG: Available item_refs: {[item.get('item_ref') for item in actionable_items]}")

                # Match each requested item
                for target_id in agenda_item_ids:
                    for item in actionable_items:
                        # Match by id, item_reference, item_ref, OR title (fallback for items without IDs)
                        if (item.get('id') == target_id or
                            item.get('item_reference') == target_id or
                            item.get('item_ref') == target_id or
                            item.get('title') == target_id):
                            matched_items.append(item)
                            print(f"[civic_api] DEBUG: MATCHED agenda item: {item.get('title', '')}")
                            break
                    else:
                        print(f"[civic_api] DEBUG: NO MATCH FOUND for agenda_item_id: '{target_id}'")

                # Build context string
                if matched_items:
                    if len(matched_items) == 1:
                        agenda_items_context = f"\n\nSpecific Agenda Item:\n"
                    else:
                        agenda_items_context = f"\n\nSelected Agenda Items ({len(matched_items)} items):\n"

                    for idx, item in enumerate(matched_items, 1):
                        if len(matched_items) > 1:
                            agenda_items_context += f"\nItem {idx}: {item.get('item_ref', '')} - {item.get('title', '')}\n"
                        else:
                            agenda_items_context += f"Title: {item.get('title', '')}\n"
                        agenda_items_context += f"Description: {item.get('description', '')}\n"

                    print(f"[civic_api] ✅ Built agenda context for {len(matched_items)} items")
                    print(f"[civic_api] DEBUG: agenda_items_context preview: {agenda_items_context[:200]}...")
                else:
                    print(f"[civic_api] ⚠️  No items matched even though {len(agenda_item_ids)} were requested")

            # STOCK TEMPLATE: No items selected + generic description = provide editable template
            if not matched_items and description_is_generic:
                print(f"[civic_api] ℹ️  No items selected and description is generic - returning stock template")

                # Build stock template with user's personal context
                jurisdiction = event.get('jurisdiction', {})
                if isinstance(jurisdiction, dict):
                    city_name = jurisdiction.get('name', 'our city')
                else:
                    city_name = 'our city'

                template_parts = ["Hi,", ""]

                # Personalize with user context if available
                if personal_context:
                    years = personal_context.get('yearsInArea', '')
                    district = personal_context.get('district', '')
                    stakes = personal_context.get('stakes', [])

                    if years:
                        template_parts.append(f"My name is [Your Name], and I've been a resident of {city_name} for {years} years.")
                    else:
                        template_parts.append(f"My name is [Your Name], and I'm a resident of {city_name}.")

                    if district:
                        template_parts.append(f"I live in {district}.")

                    template_parts.append("")

                    if stakes:
                        # Format stakes nicely
                        stakes_str = ', '.join(stakes)
                        template_parts.append(f"As someone concerned about {stakes_str}, I'm writing to share my perspective on today's meeting.")
                    else:
                        template_parts.append("I'm writing to share my perspective on today's meeting.")
                else:
                    template_parts.append(f"My name is [Your Name], and I'm a resident of {city_name}.")
                    template_parts.append("")
                    template_parts.append("I'm writing to share my perspective on today's meeting.")

                template_parts.extend([
                    "",
                    "[Share your main concern or point of view here. What brings you to this meeting? What issue matters most to you?]",
                    "",
                    "[Provide specific examples or details that support your concern. Personal stories are powerful!]",
                    "",
                    "[State your specific request to the council. What action do you want them to take?]",
                    "",
                    "Thank you for your time and consideration."
                ])

                stock_template = "\n".join(template_parts)

                # SAVE STOCK TEMPLATE TO comment_drafts TABLE (Session 45)
                draft_id = str(uuid.uuid4())
                db_path = get_user_path('civic_participation.db')
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                personal_context_json = json.dumps(personal_context) if personal_context else None
                structured_summary_json = json.dumps({
                    'tldr': 'Editable template - customize before submitting',
                    'position': 'neutral',
                    'key_topics': [],
                    'legislative_references': []
                })

                cursor.execute('''
                    INSERT INTO comment_drafts (
                        id, user_id, event_id, version, content,
                        structured_summary, personal_context, selected_agenda_items,
                        is_template, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''', (
                    draft_id,
                    user_id or 'anonymous',
                    event_id,
                    stock_template,
                    structured_summary_json,
                    personal_context_json,
                    None  # No agenda items selected for templates
                ))
                conn.commit()
                conn.close()

                print(f"[civic_api] ✅ Saved stock template to comment_drafts table: {draft_id}")

                # Return as draft with metadata indicating it's a template
                self.send_json({
                    'draft_id': draft_id,  # NEW: Client needs this for autosave
                    'draft': stock_template,
                    'word_count': len(stock_template.split()),
                    'estimated_speaking_time': "2 minutes (editable template)",
                    'comment_id': None,  # No ID for templates
                    'is_template': True,
                    'message': 'No specific agenda items selected. Here\'s an editable template to get you started. Select agenda items for a more focused AI-generated comment.',
                    'structured_summary': {
                        'tldr': 'Editable template - customize before submitting',
                        'position': 'neutral',
                        'key_topics': [],
                        'legislative_references': [],
                        'primary_archetype': None
                    }
                })
                return

            # Get legislative context
            legislative_context = ""
            if 'legislative_context' in event:
                leg_ctx = event['legislative_context']
                state_bills = leg_ctx.get('state_bills', [])
                federal_programs = leg_ctx.get('federal_programs', [])

                if state_bills:
                    legislative_context += "\n\nRelated State Legislation (USE EXACT BILL NUMBERS):\n"
                    for bill in state_bills[:3]:  # Limit to top 3 for brevity
                        legislative_context += f"- {bill.get('bill_number', '')}: {bill.get('title', '')}\n"

                if federal_programs:
                    legislative_context += "\n\nRelated Federal Programs:\n"
                    for program in federal_programs[:2]:  # Limit to top 2
                        legislative_context += f"- {program.get('program_name', '')}: {program.get('description', '')}\n"

            # Build archetype context for personalized comment framing (Session 41)
            # Archetypes are Privacy Tier 1 (browser-only), passed from frontend
            archetype_context = ""
            if archetypes and len(archetypes) > 0:
                # Build archetype context for AI prompt (top 3 archetypes)
                archetype_context = "\n\nUser Values (frame the comment using these priorities):\n"
                for archetype in archetypes[:3]:
                    name = archetype.get('name', '')
                    description = archetype.get('description', '')
                    archetype_context += f"- {name}: {description}\n"

                print(f"[civic_api] ✅ Using {len(archetypes)} civic archetypes for personalized framing")
            else:
                print(f"[civic_api] ℹ️  No archetypes provided - generating generic comment")

            # Build personal context string
            personal_context_str = ""
            if personal_context:
                personal_context_str = "\n\nPersonal Context:"

                stakes = personal_context.get('stakes', [])
                if stakes:
                    personal_context_str += f"\n- Stakes: {', '.join(stakes)}"

                years_in_area = personal_context.get('yearsInArea')
                district = personal_context.get('district', '')
                if years_in_area or district:
                    residency_parts = []
                    if years_in_area:
                        residency_parts.append(f"{years_in_area} years in area")
                    if district:
                        residency_parts.append(district)
                    personal_context_str += f"\n- Residency: {', '.join(residency_parts)}"

                expertise = personal_context.get('expertise', '')
                if expertise:
                    personal_context_str += f"\n- Expertise: {expertise}"

            # Build system prompt for comment generation (Step 1: Generation only)
            system_prompt = f"""You are an expert civic engagement assistant helping a community member draft a public comment for a city council meeting.
{archetype_context}

STRUCTURE:
1. Start with proper greeting format:
   - First line: "Hi,"
   - Blank line
   - Next line: "My name is [NAME]" and continue with introduction
   (This creates readable spacing, not "Hi, my name is" run together)
2. Core argument (2-3 paragraphs) using the user's archetype values
3. Call to action - what you want the council to do

CRITICAL - Archetype Framing:
If User Values are provided, THE TOP ARCHETYPE MUST DOMINATE THE ENTIRE COMMENT.
- Don't just mention topics - adopt this person's WORLDVIEW and POLICY SOLUTIONS
- Green New Dealer → Demand government investment, jobs programs, public infrastructure (NOT just "education")
- Labor Organizer → Center worker protections, living wages, union standards as primary concern
- Regional Thinker → Call for multi-jurisdictional coordination, metropolitan solutions
- The user's #1 archetype should be the PRIMARY lens for the ENTIRE argument

CRITICAL - Be Specific and Tangible:
When the council is asking for suggestions or input:
- Provide CONCRETE examples, not abstract principles
- Give SPECIFIC policy recommendations with details
- Include tangible implementation ideas (timelines, budgets, partnerships)
- Name specific organizations, programs, bills when relevant
- AVOID vague statements like "we need more education" or "raise awareness"
- INSTEAD say things like: "Partner with X organization to run Y program on Z schedule"

Examples of GOOD specificity:
✓ "Create a $500K fund for small business grants up to $25K each"
✓ "Require all new buildings over 50 units to include 20% affordable units"
✓ "Install bike lanes on Main St between 1st and 5th by Q2 2026"
✓ "Partner with East Bay Bicycle Coalition to offer monthly E-bike safety workshops"

Examples of BAD vagueness (AVOID):
✗ "We need to support small businesses"
✗ "Do more for affordable housing"
✗ "Improve bike infrastructure"
✗ "Provide more education about E-bike safety"

CRITICAL - Writing Style:
- Write conversationally, like a real person (NOT like polished AI writing)
- Use shorter sentences, contractions where natural
- Sound passionate but authentic, not like a corporate memo

CRITICAL - Citation Accuracy:
- Use EXACT bill numbers (e.g., "AB 1147", not "AB 117")
- Use EXACT program names and organization names

Length: 200-300 words
Tone: Professional but conversational, genuinely passionate

Return ONLY the comment text, no JSON or additional formatting."""

            # Build user prompt with auto-inference
            # Determine target description based on selection
            if matched_items:
                if len(matched_items) == 1:
                    target_item = f"{matched_items[0].get('item_ref', '')} - {matched_items[0].get('title', '')}"
                else:
                    target_item = f"{len(matched_items)} agenda items"
            else:
                target_item = event_title

            # Build user guidance section (optional hints)
            user_guidance = ""
            if position:
                user_guidance += f"\nSuggested Position: {position.upper()}"
            if key_concern:
                user_guidance += f"\nSuggested Focus: {key_concern}"

            # Use conditional prompt: focus on agenda items if provided, otherwise use full event context
            if matched_items and agenda_items_context:
                if len(matched_items) == 1:
                    # SINGLE ITEM: Focus ONLY on the specific item
                    print(f"[civic_api] Using SINGLE ITEM prompt for: {matched_items[0].get('item_ref')}")
                    user_prompt = f"""Meeting: {event_title}
Date: {event_date}

SPECIFIC AGENDA ITEM (PRIMARY FOCUS):
{agenda_items_context}
{legislative_context}
{personal_context_str}
{user_guidance}

Task: Generate a public comment specifically addressing this agenda item.
Focus ONLY on the content of this specific agenda item. Do not address other
topics from the broader meeting unless directly relevant to this item.

Your comment should:
- Take a clear position based on THIS agenda item's details and the resident's personal context
- Address specific concerns relevant to THIS item and the resident's stakes
- Incorporate relevant legislative context to strengthen the argument
- End with a concrete recommendation for the council about THIS specific item

The comment should sound authentic and personally motivated, not generic."""
                else:
                    # MULTIPLE ITEMS: Weave them into a cohesive narrative
                    print(f"[civic_api] Using MULTIPLE ITEMS prompt for {len(matched_items)} items: {[item.get('item_ref') for item in matched_items]}")
                    user_prompt = f"""Meeting: {event_title}
Date: {event_date}

SELECTED AGENDA ITEMS (ALL {len(matched_items)} ITEMS ARE IMPORTANT):
{agenda_items_context}
{legislative_context}
{personal_context_str}
{user_guidance}

Task: Generate a SINGLE cohesive public comment addressing ALL {len(matched_items)} selected agenda items.

CRITICAL - Weave Multiple Items into One Narrative:
- Find the COMMON THREAD connecting these items (e.g., they all affect housing, or transportation)
- Create ONE unified argument that addresses all items naturally
- Don't list items separately - integrate them into a flowing comment
- Show how these items relate to each other and the resident's concerns
- Make it clear this is ONE person's turn to speak (not multiple separate comments)

Your comment should:
- Open with a statement that frames ALL the items together (their common impact)
- Take a clear position on the COLLECTION of items based on the resident's context
- Weave specific details from each item into the narrative naturally
- Incorporate relevant legislative context to strengthen the argument
- End with a concrete recommendation that addresses the GROUP of items

The comment should sound authentic and personally motivated, like one coherent statement, not a list."""
            else:
                # GENERAL MEETING COMMENT: Good description, no specific items selected
                # (Only reaches here if description is good, since we block earlier for generic descriptions)
                print(f"[civic_api] Using GENERAL MEETING prompt (good description, no items selected)")
                user_prompt = f"""Meeting: {event_title}
Date: {event_date}
Description: {event_description}
{legislative_context}
{personal_context_str}
{user_guidance}

Task: Generate a thoughtful public comment on this meeting that:
- Takes a clear position based on the meeting details and personal context
- Addresses specific concerns relevant to this resident's stakes
- Incorporates relevant legislative context to strengthen the argument
- Ends with a concrete recommendation for the council

The comment should sound authentic and personally motivated, not generic."""

            # Prepare messages for OpenAI
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # STEP 1: Generate draft comment (plain text)
            # SESSION 47: Use per-item generation with caching when items are selected
            # SESSION 64: Keep item_comments for structured response
            item_comments = []  # Initialize outside block so it's available for response
            if matched_items and len(matched_items) > 0:
                print(f"[civic_api] 🔄 Using PER-ITEM generation for {len(matched_items)} items")

                # Generate per-item comments (parallel or sequential)
                for item in matched_items:
                    item_ref = item.get('item_ref')

                    # Check cache first
                    cached = self.get_cached_item_comment(event_id, item_ref)
                    if cached:
                        print(f"[civic_api] ✅ Cache hit for {item_ref}")

                        # SESSION 48: Log cache hit
                        self._log_cache_metric(event_id, item_ref, hit=True)

                        item_comments.append({
                            'item_ref': item_ref,
                            'item_title': item.get('title', ''),
                            'content': cached['content'],
                            'legislative_context': cached['legislative_context'],
                            'word_count': cached['word_count']
                        })
                        continue

                    # Generate new item-level comment
                    print(f"[civic_api] 🔨 Generating NEW comment for {item_ref}")
                    item_comment_text = self.generate_single_item_comment(
                        event=event,
                        item=item,
                        personal_context=personal_context,
                        archetypes=archetypes
                    )

                    # Cache it
                    self.cache_item_comment(
                        event_id=event_id,
                        item_ref=item_ref,
                        item_title=item.get('title', ''),
                        content=item_comment_text,
                        legislative_context=item.get('legislative_context', {}),
                        word_count=len(item_comment_text.split())
                    )

                    # SESSION 48: Log cache miss
                    self._log_cache_metric(event_id, item_ref, hit=False)

                    item_comments.append({
                        'item_ref': item_ref,
                        'item_title': item.get('title', ''),
                        'content': item_comment_text,
                        'legislative_context': item.get('legislative_context', {}),
                        'word_count': len(item_comment_text.split())
                    })

                # Merge into organized final comment
                draft = self.merge_item_comments(item_comments, event, personal_context)
                validation_warnings = []  # Per-item generation includes validation

                # Extract metadata from merged draft
                if OPENAI_AVAILABLE:
                    client = openai.OpenAI()
                    extraction_prompt = f"""Analyze this public comment and extract structured metadata.

Comment:
{draft}

Generate structured metadata as JSON with this EXACT structure:
{{
  "tldr": "• First key ask or action\\n• Second key ask or action\\n• Third key ask or action",
  "position": "support|oppose|neutral|questions",
  "key_topics": ["topic1", "topic2", "topic3"],
  "legislative_references": ["AB 1147", "CDBG"]
}}

CRITICAL - TLDR Format (Bullet Points):
- Create 2-3 bullet points (use \\n between bullets)
- Each bullet should be a SPECIFIC ask or action (under 20 words)
- Extract SPECIFIC organizations, bills, numbers, timelines
- Use bullet character: • (not dash or asterisk)
- Format: "• First point\\n• Second point\\n• Third point"

Position Classification:
- support: Comment advocates FOR a specific proposal/action
- oppose: Comment argues AGAINST a specific proposal/action
- neutral: Comment provides suggestions/ideas WITHOUT advocating for/against existing proposal
- questions: Comment asks for clarification or requests information

Key Topics (choose up to 3 from):
- housing, transportation, environment, budget, education, public_safety,
  labor, health, infrastructure, development, governance"""

                    try:
                        # Session 68: Use provider abstraction
                        if LLM_PROVIDER_AVAILABLE:
                            metadata_response = provider.complete(
                                messages=[{"role": "user", "content": extraction_prompt}],
                                max_tokens=200,
                                temperature=0.3,
                                response_format={"type": "json_object"}
                            )
                            metadata = json.loads(metadata_response.content)
                        else:
                            # Fallback to OpenAI directly
                            metadata_response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "user", "content": extraction_prompt}],
                                max_tokens=200,
                                temperature=0.3,
                                response_format={"type": "json_object"}
                            )
                            metadata = json.loads(metadata_response.choices[0].message.content)

                        tldr = metadata.get('tldr', '')
                        position = metadata.get('position', 'neutral')
                        key_topics = metadata.get('key_topics', [])
                        legislative_references = metadata.get('legislative_references', [])

                        print(f"[civic_api] ✅ Extracted metadata from per-item draft: position={position}, {len(key_topics)} topics")

                    except Exception as e:
                        print(f"[civic_api] ⚠️ Metadata extraction failed: {e}")
                        # Fallback to empty metadata
                        tldr = ""
                        position = "neutral"
                        key_topics = []
                        legislative_references = []
                else:
                    tldr = ""
                    position = "neutral"
                    key_topics = []
                    legislative_references = []

            elif not OPENAI_AVAILABLE:
                # Fallback if OpenAI not available
                fallback_text = f"I am writing to comment on {target_item}."
                if key_concern:
                    fallback_text += f"\n\n{key_concern}"
                draft = f"[OpenAI not configured - using fallback]\n\nDear Council Members,\n\n{fallback_text}\n\nThank you for your consideration."
                validation_warnings = []
                tldr = ""
                position = "neutral"
                key_topics = []
                legislative_references = []
            else:
                # LEGACY: Monolithic generation for events without selected items
                print(f"[civic_api] 📝 Using LEGACY monolithic generation (no items selected)")

                # Session 68: Use provider abstraction for cost tracking
                if LLM_PROVIDER_AVAILABLE:
                    provider = get_provider_for_task('draft')
                    print(f"[civic_api] 💰 Using provider: {provider.name} ({provider.default_model})")

                    # Call 1: Generate draft
                    response = provider.complete(
                        messages=messages,
                        max_tokens=800,
                        temperature=0.7
                    )
                    draft = response.content
                else:
                    # Fallback to OpenAI directly
                    client = openai.OpenAI()
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=messages,
                        max_tokens=800,
                        temperature=0.7
                    )
                    draft = response.choices[0].message.content

                # VALIDATE LEGISLATIVE REFERENCES
                from legislative_reference_validator import validate_comment_draft

                # Only validate if we have legislative context
                if 'legislative_context' in event:
                    draft, validation_errors = validate_comment_draft(draft, event['legislative_context'])
                    validation_warnings = [
                        {
                            'type': error['type'],
                            'message': error['message'],
                            'severity': error['severity']
                        }
                        for error in validation_errors
                    ]

                    if validation_errors:
                        # Log validation issues for monitoring
                        print(f"[civic_api] ⚠️  Legislative reference validation corrected {len(validation_errors)} issues in comment draft")
                        for error in validation_errors:
                            print(f"[civic_api]   - {error['message']}")
                else:
                    validation_warnings = []

                # STEP 2: Extract metadata from draft (separate AI call)
                extraction_prompt = f"""Analyze this public comment and extract structured metadata.

Comment:
{draft}

Generate structured metadata as JSON with this EXACT structure:
{{
  "tldr": "• First key ask or action\\n• Second key ask or action\\n• Third key ask or action",
  "position": "support|oppose|neutral|questions",
  "key_topics": ["topic1", "topic2", "topic3"],
  "legislative_references": ["AB 1147", "CDBG"]
}}

CRITICAL - TLDR Format (Bullet Points):
- Create 2-3 bullet points (use \\n between bullets)
- Each bullet should be a SPECIFIC ask or action (under 20 words)
- Extract SPECIFIC organizations, bills, numbers, timelines
- Use bullet character: • (not dash or asterisk)
- Format: "• First point\\n• Second point\\n• Third point"

GOOD TLDRs (use this format):
✓ "• Partner with East Bay Bicycle Coalition for monthly workshops\\n• Build protected bike lanes on Main St per AB 1096\\n• Allocate $500K for implementation by Q2 2026"
✓ "• Allocate $500K for housing grants to low-income families\\n• Set deadline of Q2 2026 for program launch\\n• Partner with housing nonprofits for outreach"
✓ "• Hire 10 firefighters for Station 5\\n• Purchase 2 new fire trucks with ladder capacity\\n• Complete hiring and purchases by end of fiscal year"

BAD TLDRs (too vague - AVOID):
✗ "Support balanced approach to E-bike safety through community engagement"
✗ "We need to ensure safe e-bike usage through proper regulations"
✗ Single long sentence without bullets
✗ Abstract goals without concrete actions

Position Classification:
- support: Comment advocates FOR a specific proposal/action
- oppose: Comment argues AGAINST a specific proposal/action
- neutral: Comment provides suggestions/ideas WITHOUT advocating for/against existing proposal
- questions: Comment asks for clarification or requests information

Key Topics (choose up to 3 from):
- housing, transportation, environment, budget, education, public_safety,
  labor, health, infrastructure, development, governance"""

                try:
                    # Session 68: Use provider abstraction
                    if LLM_PROVIDER_AVAILABLE:
                        metadata_response = provider.complete(
                            messages=[{"role": "user", "content": extraction_prompt}],
                            max_tokens=200,
                            temperature=0.3,
                            response_format={"type": "json_object"}
                        )
                        metadata = json.loads(metadata_response.content)
                    else:
                        # Fallback to OpenAI directly
                        metadata_response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": extraction_prompt}],
                            max_tokens=200,
                            temperature=0.3,
                            response_format={"type": "json_object"}
                        )
                        metadata = json.loads(metadata_response.choices[0].message.content)

                    tldr = metadata.get('tldr', '')
                    position = metadata.get('position', 'neutral')
                    key_topics = metadata.get('key_topics', [])
                    legislative_references = metadata.get('legislative_references', [])

                    print(f"[civic_api] ✅ Extracted metadata: position={position}, {len(key_topics)} topics, {len(legislative_references)} refs")

                except Exception as e:
                    print(f"[civic_api] ⚠️ Metadata extraction failed: {e}")
                    # Fallback to empty metadata
                    tldr = ""
                    position = "neutral"
                    key_topics = []
                    legislative_references = []

            # Calculate metrics
            word_count = len(draft.split())
            speaking_time_mins = word_count / 150  # 150 words per minute
            if speaking_time_mins < 1:
                speaking_time = f"{int(speaking_time_mins * 60)} seconds"
            else:
                mins = int(speaking_time_mins)
                secs = int((speaking_time_mins - mins) * 60)
                if secs > 0:
                    speaking_time = f"{mins} minute{'s' if mins > 1 else ''} {secs} seconds"
                else:
                    speaking_time = f"{mins} minute{'s' if mins > 1 else ''}"

            # Store in database
            import sqlite3
            import uuid
            from datetime import datetime

            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            comment_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat() + 'Z'

            # Store structured summary as JSON
            structured_summary_json = json.dumps({
                'tldr': tldr,
                'position': position,
                'key_topics': key_topics,
                'legislative_references': legislative_references,
                'primary_archetype': archetypes[0]['id'] if archetypes and len(archetypes) > 0 else None
            }) if tldr else None

            # SESSION 45: SAVE TO comment_drafts TABLE FOR PERSISTENCE (ALWAYS)
            # This enables Google Docs-style autosave and draft resumption
            draft_id = str(uuid.uuid4())

            # Prepare JSON fields for draft storage
            structured_summary_for_draft = json.dumps({
                'tldr': tldr,
                'position': position,
                'key_topics': key_topics,
                'legislative_references': legislative_references
            }) if tldr else None

            personal_context_json = json.dumps(personal_context) if personal_context else None
            selected_agenda_items_json = json.dumps([item.get('item_ref') for item in matched_items if item.get('item_ref')]) if matched_items else None

            # Determine is_template flag
            is_template_flag = False  # Regular AI draft

            # SESSION 48: Auto-tag drafts based on key_topics from metadata
            tags_json = json.dumps(key_topics) if key_topics else None

            cursor.execute('''
                INSERT INTO comment_drafts (
                    id, user_id, event_id, version, content,
                    structured_summary, personal_context, selected_agenda_items,
                    is_template, tags, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (
                draft_id,
                user_id or 'anonymous',
                event_id,
                draft,
                structured_summary_for_draft,
                personal_context_json,
                selected_agenda_items_json,
                is_template_flag,
                tags_json
            ))
            conn.commit()

            print(f"[civic_api] ✅ Saved draft to comment_drafts table: {draft_id}")

            # Store only if position and key_concern exist (legacy requirement)
            # If not provided, we skip database storage for now
            if position and key_concern:
                # For backward compatibility, store first item in agenda_item_id column
                db_agenda_item_id = matched_items[0].get('item_ref') if matched_items else None

                # Try to insert with structured_summary, fallback if column doesn't exist yet
                try:
                    cursor.execute("""
                        INSERT INTO comments (
                            id, user_id, event_id, agenda_item_id,
                            position, key_concern, personal_context,
                            ai_draft_generated, ai_draft,
                            structured_summary,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        comment_id,
                        None,  # user_id - will be added when auth is implemented
                        event_id,
                        db_agenda_item_id,  # Store first item for backward compat
                        position,
                        key_concern,
                        json.dumps(personal_context) if personal_context else None,
                        True,
                        draft,
                        structured_summary_json,
                        now
                    ))
                except sqlite3.OperationalError as e:
                    if 'no column named structured_summary' in str(e):
                        # Column doesn't exist yet - insert without it
                        print(f"[civic_api] ⚠️  structured_summary column not found - run migration 013")
                        cursor.execute("""
                            INSERT INTO comments (
                                id, user_id, event_id, agenda_item_id,
                                position, key_concern, personal_context,
                                ai_draft_generated, ai_draft,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            comment_id,
                            None,
                            event_id,
                            db_agenda_item_id,  # Store first item for backward compat
                            position,
                            key_concern,
                            json.dumps(personal_context) if personal_context else None,
                            True,
                            draft,
                            now
                        ))
                    else:
                        raise

                # Insert ALL matched items into junction table (migration 014)
                if matched_items:
                    try:
                        for idx, item in enumerate(matched_items):
                            item_id = item.get('item_ref')
                            if item_id:
                                cursor.execute("""
                                    INSERT INTO comment_agenda_items (
                                        comment_id, agenda_item_id, item_order, created_at
                                    ) VALUES (?, ?, ?, ?)
                                """, (comment_id, item_id, idx, now))
                        print(f"[civic_api] ✅ Stored {len(matched_items)} agenda items in junction table")
                    except sqlite3.OperationalError as e:
                        if 'no such table: comment_agenda_items' in str(e):
                            print(f"[civic_api] ⚠️  comment_agenda_items table not found - run migration 014")
                        else:
                            raise

                conn.commit()

            conn.close()

            # Return response with validation warnings and structured summary
            response_data = {
                'draft_id': draft_id,  # NEW: Client needs this for autosave
                'draft': draft,
                'word_count': word_count,
                'estimated_speaking_time': speaking_time,
                'comment_id': comment_id
            }

            # SESSION 64: Add structured sections if multi-item draft
            if item_comments and len(item_comments) > 0:
                response_data['item_sections'] = item_comments
                print(f"[civic_api] ✅ Returning {len(item_comments)} structured sections")

            # Add structured summary if available
            if tldr or key_topics or legislative_references:
                response_data['structured_summary'] = {
                    'tldr': tldr,
                    'position': position,
                    'key_topics': key_topics,
                    'legislative_references': legislative_references,
                    'primary_archetype': archetypes[0]['id'] if archetypes and len(archetypes) > 0 else None
                }

            # Add validation warnings if any
            if validation_warnings:
                response_data['validation_warnings'] = validation_warnings

            self.send_json(response_data)

            position_str = position if position else 'auto-inferred'
            print(f"[civic_api] Generated comment draft for event {event_id} ({word_count} words, {position_str})")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR generating comment draft: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def _find_event_by_id(self, event_id: str) -> dict:
        """Find event by ID across all event files"""
        all_events = self._load_all_events()
        for event in all_events:
            if event.get('id') == event_id:
                return event
        return None

    def handle_regenerate_item_comment(self, event_id: str, item_ref: str):
        """
        Handle POST /api/events/{event_id}/items/{item_ref}/regenerate (Session 47)

        Regenerate comment for single agenda item (bypasses cache).

        Request format:
        {
            "userId": "user-123",
            "archetypes": [...],
            "personalContext": {...}
        }

        Response:
        {
            "content": "...",
            "word_count": 87,
            "item_ref": "7.2"
        }
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            user_id = data.get('userId')
            archetypes = data.get('archetypes', [])
            personal_context = data.get('personalContext', {})

            # Load event
            event = self._find_event_by_id(event_id)
            if not event:
                self.send_json({'error': 'Event not found'}, 404)
                return

            # Find the specific item
            actionable_items = event.get('agenda_expansion', {}).get('actionable_items', [])
            item = next((i for i in actionable_items if i.get('item_ref') == item_ref), None)

            if not item:
                self.send_json({'error': f'Agenda item {item_ref} not found'}, 404)
                return

            print(f"[civic_api] 🔨 Regenerating comment for item {item_ref} (bypassing cache)")

            # Generate new comment (bypassing cache)
            new_content = self.generate_single_item_comment(event, item, personal_context, archetypes)
            word_count = len(new_content.split())

            # Update cache
            self.cache_item_comment(
                event_id=event_id,
                item_ref=item_ref,
                item_title=item.get('title', ''),
                content=new_content,
                legislative_context=item.get('legislative_context', {}),
                word_count=word_count
            )

            print(f"[civic_api] ✅ Regenerated and cached {item_ref} ({word_count} words)")

            self.send_json({
                'content': new_content,
                'word_count': word_count,
                'item_ref': item_ref
            })

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR regenerating item: {str(e)}")
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_get_draft(self, event_id: str):
        """
        Handle GET /api/events/{event_id}/draft-comment?user_id=xyz

        Returns most recent draft for this user+event, or null if none exists.
        Enables Google Docs-style draft loading (no API generation cost on refresh).
        """
        from urllib.parse import urlparse, parse_qs

        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        user_id = query_params.get('user_id', ['anonymous'])[0]

        db_path = get_user_path('civic_participation.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, content, structured_summary, personal_context,
                   selected_agenda_items, is_template, created_at, updated_at, submitted
            FROM comment_drafts
            WHERE user_id = ? AND event_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
        ''', (user_id, event_id))

        row = cursor.fetchone()
        conn.close()

        if not row:
            self.send_json({'draft': None})
            print(f"[civic_api] No existing draft found for user={user_id}, event={event_id}")
            return

        # Parse JSON fields
        structured_summary = json.loads(row[2]) if row[2] else None
        personal_context = json.loads(row[3]) if row[3] else {}
        selected_agenda_items = json.loads(row[4]) if row[4] else []

        self.send_json({
            'draft_id': row[0],
            'draft': row[1],
            'structured_summary': structured_summary,
            'personal_context': personal_context,
            'selected_agenda_items': selected_agenda_items,
            'is_template': bool(row[5]),
            'created_at': row[6],
            'updated_at': row[7],
            'submitted': bool(row[8])
        })

        print(f"[civic_api] ✅ Loaded existing draft {row[0]} for user={user_id}, event={event_id}")

    def handle_update_draft(self, draft_id: str):
        """
        Handle PUT /api/drafts/{draft_id}

        Body: { "content": "updated text...", "word_count": 250, "speaking_time": "1 min 40s" }

        Updates draft content (autosave from frontend).
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            updated_content = data.get('content')
            if not updated_content:
                self.send_json({'error': 'content field required'}, 400)
                return

            # SESSION 48: Support optional tags update
            tags = data.get('tags')  # Optional array like ["housing", "transportation"]
            tags_json = json.dumps(tags) if tags is not None else None

            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Update content and optionally tags
            if tags_json is not None:
                cursor.execute('''
                    UPDATE comment_drafts
                    SET content = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (updated_content, tags_json, draft_id))
            else:
                cursor.execute('''
                    UPDATE comment_drafts
                    SET content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (updated_content, draft_id))

            if cursor.rowcount == 0:
                conn.close()
                self.send_json({'error': 'Draft not found'}, 404)
                return

            conn.commit()
            conn.close()

            self.send_json({'success': True, 'updated_at': datetime.utcnow().isoformat() + 'Z'})
            print(f"[civic_api] ✅ Autosaved draft {draft_id}")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR updating draft: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_mark_draft_submitted(self, draft_id: str):
        """
        Handle POST /api/drafts/{draft_id}/submit

        Marks draft as submitted after user emails to clerk.
        """
        try:
            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE comment_drafts
                SET submitted = TRUE, submitted_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (draft_id,))

            if cursor.rowcount == 0:
                conn.close()
                self.send_json({'error': 'Draft not found'}, 404)
                return

            conn.commit()
            conn.close()

            self.send_json({'success': True})
            print(f"[civic_api] ✅ Marked draft {draft_id} as submitted")

        except Exception as e:
            print(f"[civic_api] ERROR marking draft as submitted: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_delete_draft(self, draft_id: str):
        """
        Handle DELETE /api/drafts/{draft_id}

        Permanently delete a draft (no undo). SESSION 48
        """
        try:
            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Delete draft
            cursor.execute('DELETE FROM comment_drafts WHERE id = ?', (draft_id,))
            deleted_count = cursor.rowcount

            conn.commit()
            conn.close()

            if deleted_count == 0:
                self.send_json({'error': 'Draft not found'}, 404)
                return

            self.send_json({'success': True, 'message': 'Draft deleted'})
            print(f"[civic_api] ✅ Deleted draft {draft_id}")

        except Exception as e:
            print(f"[civic_api] ERROR deleting draft: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_get_all_drafts(self, event_id: str):
        """
        Handle GET /api/events/{event_id}/drafts?user_id=xyz

        Returns all drafts for this user+event (multi-draft system).
        Each draft is keyed by agenda item selection.
        """
        from urllib.parse import urlparse, parse_qs

        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        user_id = query_params.get('user_id', ['anonymous'])[0]

        db_path = get_user_path('civic_participation.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, content, structured_summary, personal_context, selected_agenda_items, created_at, updated_at, submitted, tags
            FROM comment_drafts
            WHERE user_id = ? AND event_id = ?
            ORDER BY updated_at DESC
        ''', (user_id, event_id))

        drafts = []
        for row in cursor.fetchall():
            selected_agenda_items = json.loads(row[4]) if row[4] else []
            structured_summary = json.loads(row[2]) if row[2] else None
            personal_context = json.loads(row[3]) if row[3] else {}
            tags = json.loads(row[8]) if row[8] else []  # SESSION 48: Tags
            drafts.append({
                'draft_id': row[0],
                'content': row[1],  # Full content for client-side loading
                'content_preview': row[1][:100] if row[1] else '',  # First 100 chars for display
                'structured_summary': structured_summary,
                'personal_context': personal_context,
                'selected_agenda_items': selected_agenda_items,
                'created_at': row[5],
                'updated_at': row[6],
                'submitted': bool(row[7]),
                'tags': tags  # SESSION 48: Include tags in response
            })

        conn.close()

        self.send_json({'drafts': drafts})
        print(f"[civic_api] ✅ Loaded {len(drafts)} drafts for user={user_id}, event={event_id}")

    def handle_cache_stats(self):
        """
        Handle GET /api/admin/cache-stats

        Returns cache hit rate statistics (Session 48).
        """
        try:
            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Overall stats
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN hit = 1 THEN 1 ELSE 0 END) as hits,
                    SUM(CASE WHEN hit = 0 THEN 1 ELSE 0 END) as misses
                FROM cache_metrics
            ''')
            row = cursor.fetchone()
            total, hits, misses = row[0], row[1] or 0, row[2] or 0
            hit_rate = (hits / total * 100) if total > 0 else 0

            # Top cached items
            cursor.execute('''
                SELECT item_ref, COUNT(*) as hit_count
                FROM cache_metrics
                WHERE hit = 1
                GROUP BY item_ref
                ORDER BY hit_count DESC
                LIMIT 10
            ''')
            top_items = [{'item_ref': row[0], 'hit_count': row[1]} for row in cursor.fetchall()]

            conn.close()

            self.send_json({
                'total_requests': total,
                'cache_hits': hits,
                'cache_misses': misses,
                'hit_rate_percent': round(hit_rate, 2),
                'top_cached_items': top_items
            })
            print(f"[civic_api] ✅ Cache stats: {hits}/{total} hits ({hit_rate:.1f}%)")

        except Exception as e:
            print(f"[civic_api] ERROR getting cache stats: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_provider_stats(self):
        """
        Handle GET /api/admin/provider-stats

        Returns provider usage statistics (Session 68).

        Response format:
        {
            "google": {"count": 150, "total_tokens": 12500},
            "openai": {"count": 50, "total_tokens": 8000},
            "perplexity": {"count": 10, "total_tokens": 2000}
        }
        """
        try:
            self.send_json(dict(self.provider_stats))
            print(f"[civic_api] ✅ Provider stats: {len(self.provider_stats)} providers tracked")
        except Exception as e:
            print(f"[civic_api] ERROR getting provider stats: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_cost_estimate(self):
        """
        Handle GET /api/admin/cost-estimate

        Estimates monthly costs based on current usage (Session 68).

        Response format:
        {
            "google": {"tokens": 12500, "cost": "$0.00094", "requests": 150},
            "openai": {"tokens": 8000, "cost": "$0.0048", "requests": 50},
            "total_cost": "$0.00574",
            "monthly_projection": "$1.72"
        }
        """
        try:
            # Cost per 1M tokens (as of 2025)
            rates = {
                "google": 0.075,      # Gemini Flash
                "openai": 0.60,       # gpt-4o-mini
                "groq": 0.27,         # Llama 3.3
                "perplexity": 1.00,   # Sonar
                "anthropic": 3.00     # Claude Sonnet 4
            }

            costs = {}
            total_cost = 0

            for provider, stats in self.provider_stats.items():
                tokens = stats["total_tokens"]
                requests = stats["count"]
                rate = rates.get(provider, 0)
                cost = (tokens / 1_000_000) * rate

                costs[provider] = {
                    "tokens": tokens,
                    "cost": f"${cost:.5f}",
                    "requests": requests
                }
                total_cost += cost

            # Project monthly costs (assume current data represents 1 day)
            # Very rough estimate - real usage patterns vary
            monthly_projection = total_cost * 30

            costs["total_cost"] = f"${total_cost:.5f}"
            costs["monthly_projection"] = f"${monthly_projection:.2f}"

            self.send_json(costs)
            print(f"[civic_api] ✅ Cost estimate: ${total_cost:.5f} current, ${monthly_projection:.2f} monthly")
        except Exception as e:
            print(f"[civic_api] ERROR estimating costs: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_user_follows(self, user_id: str):
        """
        Handle GET /api/follows?user_id={user_id}

        Returns all follows for a user (issues and events they're following).

        Response format:
        {
          "follows": [
            {
              "follow_id": "uuid",
              "focal_type": "issue",
              "focal_id": "issue-uuid",
              "jurisdiction_id": "city-berkeley",
              "created_at": "2025-10-26T10:00:00Z",
              "last_seen_at": "2025-10-26T12:00:00Z"
            }
          ],
          "metadata": {
            "total_follows": 5,
            "issue_follows": 3,
            "event_follows": 2
          }
        }
        """
        try:
            import sqlite3

            # Connect to database
            db_path = get_user_path('civic_participation.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query all follows for this user
            cursor.execute('''
                SELECT follow_id, user_id, focal_type, focal_id, jurisdiction_id, created_at, last_seen_at
                FROM follows
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))

            rows = cursor.fetchall()
            conn.close()

            # Format follows
            follows = []
            for row in rows:
                follows.append({
                    'follow_id': row['follow_id'],
                    'focal_type': row['focal_type'],
                    'focal_id': row['focal_id'],
                    'jurisdiction_id': row['jurisdiction_id'],
                    'created_at': row['created_at'],
                    'last_seen_at': row['last_seen_at']
                })

            # Calculate metadata
            issue_follows = sum(1 for f in follows if f['focal_type'] == 'issue')
            event_follows = sum(1 for f in follows if f['focal_type'] == 'event')

            self.send_json({
                'follows': follows,
                'metadata': {
                    'total_follows': len(follows),
                    'issue_follows': issue_follows,
                    'event_follows': event_follows
                }
            })

            print(f"[civic_api] Served {len(follows)} follows for user {user_id}")

        except Exception as e:
            print(f"[civic_api] ERROR serving user follows: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_follow_info(self, focal_type: str, focal_id: str, user_id: Optional[str] = None):
        """
        Handle GET /api/follows/{focal_type}/{focal_id}?user_id={user_id}

        Returns follow information for a focal point (issue or event).

        Response format:
        {
          "follower_count": 5,
          "thread_id": "uuid",
          "your_following": true
        }
        """
        try:
            # Validate focal_type
            if focal_type not in ['issue', 'event']:
                self.send_json({'error': 'focal_type must be "issue" or "event"'}, 400)
                return

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Get follow info
            follow_info = storage.get_follow_info(focal_type, focal_id, user_id)

            self.send_json(follow_info)

        except Exception as e:
            print(f"[civic_api] ERROR getting follow info: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_create_follow(self):
        """
        Handle POST /api/follows - Create a follow and auto-create coordination thread.

        Request format:
        {
          "user_id": "hash",
          "focal_type": "issue",
          "focal_id": "uuid",
          "jurisdiction_id": "city-name"
        }

        Response format:
        {
          "follower_count": 5,
          "thread_id": "uuid",
          "your_following": true
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            user_id = data.get('user_id')
            focal_type = data.get('focal_type')
            focal_id = data.get('focal_id')

            if not user_id:
                self.send_json({'error': 'user_id is required'}, 400)
                return
            if not focal_type:
                self.send_json({'error': 'focal_type is required'}, 400)
                return
            if not focal_id:
                self.send_json({'error': 'focal_id is required'}, 400)
                return

            # Validate focal_type
            if focal_type not in ['issue', 'event']:
                self.send_json({'error': 'focal_type must be "issue" or "event"'}, 400)
                return

            # Optional jurisdiction_id
            jurisdiction_id = data.get('jurisdiction_id')

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Create follow (auto-creates thread if needed)
            result = storage.create_follow(user_id, focal_type, focal_id, jurisdiction_id)

            self.send_json(result)

            print(f"[civic_api] User {user_id} followed {focal_type} {focal_id}")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR creating follow: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_delete_follow(self, user_id: str, focal_type: str, focal_id: str):
        """
        Handle DELETE /api/follows/{focal_type}/{focal_id}?user_id={user_id}

        Removes a follow (unfollow).

        Response format:
        {
          "follower_count": 4,
          "your_following": false
        }
        """
        try:
            # Validate focal_type
            if focal_type not in ['issue', 'event']:
                self.send_json({'error': 'focal_type must be "issue" or "event"'}, 400)
                return

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Delete follow
            result = storage.delete_follow(user_id, focal_type, focal_id)

            self.send_json(result)

            print(f"[civic_api] User {user_id} unfollowed {focal_type} {focal_id}")

        except Exception as e:
            print(f"[civic_api] ERROR deleting follow: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def _load_event_by_id(self, event_id: str) -> Optional[Dict]:
        """Load a single event by ID from JSON files"""
        all_events = self._load_all_events()
        for event in all_events:
            if event.get('id') == event_id:
                return event
        return None

    def _load_complaint_by_id(self, issue_id: str) -> Optional[Dict]:
        """Load a single issue by ID from database"""
        try:
            from issue_storage import IssueStorage
        except ImportError:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent))
            from issue_storage import IssueStorage

        storage = IssueStorage()
        # get_issue only takes issue_id
        issue = storage.get_issue(issue_id)
        return issue

    def serve_all_threads(self, jurisdiction_id: Optional[str] = None):
        """
        Handle GET /api/threads?jurisdiction={jurisdiction_id}

        Lists all active coordination threads with metadata.

        Response format:
        {
          "threads": [
            {
              "thread_id": "uuid",
              "focal_type": "issue" or "event",
              "focal_id": "uuid",
              "participant_count": 5,
              "message_count": 23,
              "created_at": "2025-10-15T09:00:00Z",
              "last_message_at": "2025-10-16T14:30:00Z"
            }
          ]
        }
        """
        try:
            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Get all threads (optionally filtered by jurisdiction)
            threads = storage.get_all_threads(jurisdiction_id=jurisdiction_id)

            # Hydrate focal_point_title for each thread
            for thread in threads:
                focal_type = thread.get('focal_type')
                focal_id = thread.get('focal_id')

                if focal_type == 'event':
                    # Load event title
                    event = self._load_event_by_id(focal_id)
                    thread['focal_point_title'] = event.get('title', 'Untitled Event') if event else 'Unknown Event'
                elif focal_type == 'issue':
                    # Load issue and use short_name, fallback to ai_title or truncated description
                    issue = self._load_complaint_by_id(focal_id)
                    if issue:
                        # Compute short_name from database fields (same as API endpoints)
                        short_name = f"{issue.get('short_name_keyword')}-{issue.get('short_name_number')}" if issue.get('short_name_keyword') else None

                        # Prioritize short_name (KEYWORD-NUMBER format), then ai_title, then truncated description
                        if short_name:
                            thread['focal_point_title'] = short_name
                        elif issue.get('ai_title'):
                            thread['focal_point_title'] = issue['ai_title']
                        elif issue.get('description'):
                            desc = issue['description']
                            thread['focal_point_title'] = desc[:80] + ('...' if len(desc) > 80 else '')
                        else:
                            thread['focal_point_title'] = 'Unknown Issue'
                    else:
                        thread['focal_point_title'] = 'Unknown Issue'
                else:
                    thread['focal_point_title'] = 'Unknown'

            self.send_json({
                'threads': threads,
                'count': len(threads)
            })

            print(f"[civic_api] Served {len(threads)} threads" + (f" for jurisdiction {jurisdiction_id}" if jurisdiction_id else ""))

        except Exception as e:
            print(f"[civic_api] ERROR getting threads: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_thread_info(self, thread_id: str):
        """
        Handle GET /api/threads/{thread_id}

        Gets thread metadata including focal point info and counts.

        Response format:
        {
          "thread_id": "uuid",
          "focal_type": "issue" or "event",
          "focal_id": "uuid",
          "participant_count": 5,
          "message_count": 23,
          "created_at": "2025-10-15T09:00:00Z",
          "last_message_at": "2025-10-16T14:30:00Z"
        }
        """
        try:
            print(f"[civic_api] Serving thread info for ID: {thread_id}")

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Get thread info
            thread_info = storage.get_thread_info(thread_id)
            print(f"[civic_api] Thread info result: {thread_info}")

            if not thread_info:
                print(f"[civic_api] Thread {thread_id} not found in database")
                self.send_json({'error': 'Thread not found'}, 404)
                return

            self.send_json(thread_info)
            print(f"[civic_api] Successfully served thread info")

        except Exception as e:
            print(f"[civic_api] ERROR getting thread info: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_thread_messages(self, thread_id: str, user_id: str):
        """
        Handle GET /api/threads/{thread_id}/messages?user_id={user_id}

        Fetches all messages for a thread plus participant information.

        Response format:
        {
          "messages": [
            {
              "message_id": "uuid",
              "thread_id": "uuid",
              "user_id": "hash",
              "content": "text",
              "created_at": "2025-10-16T10:30:00Z"
            }
          ],
          "participants": [
            {
              "user_id": "hash",
              "jurisdiction_id": "city-name",
              "created_at": "2025-10-15T09:00:00Z"
            }
          ]
        }
        """
        try:
            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Get messages with nested structure (for threaded replies)
            messages = storage.get_thread_messages_nested(thread_id)

            # Get participants (method internally looks up focal point from thread_id)
            participants = storage.get_thread_participants(thread_id)

            # Get thread info to determine focal type
            thread_info = storage.get_thread_info(thread_id)

            # Get related issues if this is an event thread (Task 2: Complaint→Discussion Integration)
            related_issues = []
            if thread_info and thread_info.get('focal_type') == 'event':
                event_id = thread_info['focal_id']
                related_issues = storage.get_related_issues_for_event(event_id)

            response = {
                'messages': messages,
                'participants': participants
            }

            # Only include related_issues if there are any
            if related_issues:
                response['related_issues'] = related_issues

            self.send_json(response)

        except Exception as e:
            print(f"[civic_api] ERROR getting thread messages: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_send_message(self, thread_id: str):
        """
        Handle POST /api/threads/{thread_id}/messages

        Creates a new message in a thread.

        Request format:
        {
          "user_id": "hash",
          "content": "message text",
          "parent_message_id": "uuid" (optional - for nested replies)
        }

        Response format:
        {
          "message_id": "uuid",
          "thread_id": "uuid",
          "user_id": "hash",
          "content": "text",
          "created_at": "2025-10-16T10:30:00Z",
          "parent_message_id": "uuid" or null,
          "reply_count": 0
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            user_id = data.get('user_id')
            content = data.get('content')
            parent_message_id = data.get('parent_message_id')  # Optional

            if not user_id:
                self.send_json({'error': 'user_id is required'}, 400)
                return
            if not content:
                self.send_json({'error': 'content is required'}, 400)
                return

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Create message (with optional parent_message_id)
            message = storage.create_message(thread_id, user_id, content, parent_message_id)

            self.send_json(message)

            print(f"[civic_api] Message created in thread {thread_id} by user {user_id}")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR creating message: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_event_discussion_stats(self):
        """
        Handle GET /api/events/discussion-stats?event_ids=event1,event2,event3

        Returns discussion stats for multiple events.

        Response format:
        {
          "stats": [
            {
              "event_id": "berkeley-planning-2025-10-20",
              "thread_id": "uuid",
              "participant_count": 15,
              "message_count": 42
            }
          ]
        }
        """
        try:
            # Parse query string
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            event_ids_str = query_params.get('event_ids', [''])[0]

            if not event_ids_str:
                self.send_json({'stats': []})
                return

            event_ids = event_ids_str.split(',')

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            stats = []
            for event_id in event_ids:
                # Get threads for this event
                threads = storage.get_threads_for_focal_point('event', event_id)

                if threads:
                    thread = threads[0]  # One thread per event
                    stats.append({
                        'event_id': event_id,
                        'thread_id': thread['thread_id'],
                        'participant_count': thread.get('participant_count', 0),
                        'message_count': thread.get('message_count', 0)
                    })

            self.send_json({'stats': stats})

            print(f"[civic_api] Served discussion stats for {len(event_ids)} events ({len(stats)} with discussions)")

        except Exception as e:
            print(f"[civic_api] ERROR getting event discussion stats: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_mark_thread_read(self, focal_type: str, focal_id: str):
        """
        Handle POST /api/follows/{focal_type}/{focal_id}/mark-read

        Updates last_seen_at timestamp for a user's follow of a focal point.

        Request format:
        {
          "user_id": "hash"
        }

        Response format:
        {
          "success": true
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            user_id = data.get('user_id')

            if not user_id:
                self.send_json({'error': 'user_id is required'}, 400)
                return

            # Validate focal_type
            if focal_type not in ['issue', 'event']:
                self.send_json({'error': 'focal_type must be "issue" or "event"'}, 400)
                return

            # Import storage
            try:
                from issue_storage import CommunityStorage
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from issue_storage import CommunityStorage

            storage = CommunityStorage()

            # Mark thread as seen
            storage.mark_thread_seen(user_id, focal_type, focal_id)

            self.send_json({'success': True})

            print(f"[civic_api] User {user_id} marked {focal_type} {focal_id} as read")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR marking thread as read: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_set_user_location(self):
        """
        Handle POST /api/user/location - Set user's location with geocoding + validation

        Request format:
        {
          "user_id": "hash",
          "address": "123 Oak St, Oakland, CA"
        }

        Response format:
        {
          "location": {
            "lat": 37.8044,
            "lng": -122.2712,
            "city": "Oakland",
            "county": "Alameda County",
            "state": "California",
            "jurisdictions": {
              "city": "city-oakland",
              "county": "alameda-county"
            }
          },
          "validation": {
            "valid": true,
            "distance_miles": 5.2,
            "reason": "Valid - within acceptable distance"
          }
        }
        """
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Validate required fields
            user_id = data.get('user_id')
            address = data.get('address')

            if not user_id:
                self.send_json({'error': 'user_id is required'}, 400)
                return
            if not address:
                self.send_json({'error': 'address is required'}, 400)
                return

            # Import services
            try:
                from geocoding_service import get_geocoding_service
                from location_validator import get_location_validator
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent))
                from geocoding_service import get_geocoding_service
                from location_validator import get_location_validator

            # Geocode address
            geocoding_service = get_geocoding_service()
            geocoded = geocoding_service.geocode_address(address)

            if not geocoded:
                self.send_json({'error': 'Could not geocode address. Please check the address and try again.'}, 400)
                return

            # Validate location (IP geolocation anti-bot protection)
            location_validator = get_location_validator()

            # Get user's IP
            user_ip = self.headers.get('X-Forwarded-For', self.client_address[0])
            if ',' in user_ip:
                user_ip = user_ip.split(',')[0].strip()

            validation = location_validator.validate_location(
                user_ip,
                geocoded['lat'],
                geocoded['lng']
            )

            # Store location (only lat/lng - privacy preserving)
            # TODO: Add database table for user locations
            # For now, we'll just return the location data
            # Frontend will store it in localStorage

            response = {
                'location': {
                    'lat': geocoded['lat'],
                    'lng': geocoded['lng'],
                    'city': geocoded.get('city'),
                    'county': geocoded.get('county'),
                    'state': geocoded.get('state'),
                    'street_name': geocoded.get('street_name'),  # For display name
                    'jurisdictions': geocoded['jurisdictions']
                },
                'validation': validation
            }

            self.send_json(response)

            print(f"[civic_api] User {user_id} set location: {geocoded.get('city')} ({geocoded['lat']}, {geocoded['lng']})")
            print(f"[civic_api] Validation: {validation['reason']}")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR setting user location: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    # ===== PERSONALIZATION POST/DELETE HANDLERS =====

    def handle_user_profile(self):
        """
        Handle POST /api/user/profile - Create or update user profile

        User ID extracted from Bearer token.

        Request format:
        {
          "jurisdictionId": "city-berkeley",
          "displayName": "Jane Doe",
          "stakes": ["homeowner", "parent"],
          "yearsInArea": 15,
          "civicInterests": ["housing", "education"],
          "expertise": "urban planning",
          ...
        }

        Response format:
        {
          "user_id": "user123",
          "profile_completeness": 65,
          ...all profile fields...
        }
        """
        try:
            # Get user_id from Bearer token
            user_id = self.get_user_id_from_token()
            if not user_id:
                self.send_json({'error': 'Authentication required'}, 401)
                return

            # Check if PersonalizationService is available
            if not personalization_service:
                self.send_json({'error': 'Personalization service not available'}, 503)
                return

            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            profile_data = json.loads(body)

            # Check if profile exists (update vs create)
            existing_profile = personalization_service.get_user_profile(user_id)

            if existing_profile:
                # Update existing profile
                # For now, we'll recreate it (PersonalizationService.update_user_profile not yet implemented)
                # This is acceptable for Phase 2 MVP
                updated_profile = personalization_service.create_user_profile(user_id, profile_data)
                self.send_json(updated_profile)
                print(f"[civic_api] Updated profile for user: {user_id}")
            else:
                # Create new profile
                new_profile = personalization_service.create_user_profile(user_id, profile_data)
                self.send_json(new_profile, status_code=201)
                print(f"[civic_api] Created new profile for user: {user_id}")

        except ValueError as e:
            # Missing required fields
            self.send_json({'error': str(e)}, 400)
        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR handling user profile: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_research_query(self):
        """
        Handle POST /api/research - Answer factual queries from cached data

        Request format:
        {
          "question": "What is Berkeley's CDBG allocation?",
          "search_scope": "allocations"  // Optional: "all", "legislative", "events", "allocations"
        }

        Response format:
        {
          "answer": "Berkeley's CDBG allocation for FY2025 is $2.67M...",
          "sources": ["data/jurisdiction_overrides/city-berkeley.json"],
          "confidence": "high",
          "provider": "gemini-flash"
        }
        """
        try:
            # Check if research service is available (lazy initialization)
            if get_research_service() is None:
                self.send_json({'error': 'Research service not available'}, 503)
                return

            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json({'error': 'Request body required'}, 400)
                return

            body = self.rfile.read(content_length).decode('utf-8')
            request_data = json.loads(body)

            # Extract parameters
            question = request_data.get('question', '').strip()
            search_scope = request_data.get('search_scope', 'all')

            # Validate question
            if not question:
                self.send_json({'error': 'Question is required'}, 400)
                return

            # Validate scope
            valid_scopes = ['all', 'legislative', 'events', 'allocations']
            if search_scope not in valid_scopes:
                self.send_json({
                    'error': f'Invalid search_scope. Must be one of: {", ".join(valid_scopes)}'
                }, 400)
                return

            # Query research service
            svc = get_research_service()
            result = svc.query(question, search_scope=search_scope)

            # Add provider info for debugging
            response = {
                'answer': result['answer'],
                'sources': result['sources'],
                'confidence': result['confidence'],
                'provider': svc.provider.name
            }

            self.send_json(response)
            print(f"[civic_api] Research query answered: '{question[:50]}...' (scope: {search_scope})")

        except json.JSONDecodeError:
            self.send_json({'error': 'Invalid JSON in request body'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR handling research query: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def handle_delete_user(self):
        """
        Handle DELETE /api/user - GDPR account deletion

        User ID extracted from Bearer token.
        Deletes user profile, civic history, and inferred interests.

        Response format:
        {
          "success": true,
          "message": "User account deleted successfully",
          "user_id": "user123",
          "deleted_count": {
            "profile": 1,
            "civic_history": 42,
            "inferred_interests": 5
          }
        }
        """
        try:
            # Get user_id from Bearer token
            user_id = self.get_user_id_from_token()
            if not user_id:
                self.send_json({'error': 'Authentication required'}, 401)
                return

            # Check if PersonalizationService is available
            if not personalization_service:
                self.send_json({'error': 'Personalization service not available'}, 503)
                return

            # Delete all user data from personalization tables
            conn = personalization_service._get_connection()
            cursor = conn.cursor()

            # Count records before deletion (for response)
            cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE user_id = ?", (user_id,))
            profile_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM civic_history WHERE user_id = ?", (user_id,))
            history_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM inferred_interests WHERE user_id = ?", (user_id,))
            interests_count = cursor.fetchone()[0]

            # Perform deletions
            cursor.execute("DELETE FROM inferred_interests WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM civic_history WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))

            conn.commit()
            conn.close()

            # Clear cache
            if user_id in personalization_service.cache:
                del personalization_service.cache[user_id]

            response = {
                'success': True,
                'message': 'User account deleted successfully',
                'user_id': user_id,
                'deleted_count': {
                    'profile': profile_count,
                    'civic_history': history_count,
                    'inferred_interests': interests_count
                }
            }

            self.send_json(response)
            print(f"[civic_api] Deleted user account: {user_id} (profile: {profile_count}, history: {history_count}, interests: {interests_count})")

        except Exception as e:
            print(f"[civic_api] ERROR deleting user account: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_user_location(self, user_id: str):
        """
        Handle GET /api/user/location?user_id={user_id}

        Returns user's stored location (if any).

        Response format:
        {
          "location": {
            "lat": 37.8044,
            "lng": -122.2712,
            "city": "Oakland",
            "county": "Alameda County",
            "state": "California",
            "street_name": "Oak St",
            "jurisdictions": {
              "city": "city-oakland",
              "county": "alameda-county"
            }
          }
        }

        Returns 404 if no location set.
        """
        try:
            # TODO: Retrieve location from database
            # For Phase 3, frontend stores location in localStorage
            # This endpoint is a placeholder for future database integration

            # For now, return 404 (not found)
            # Frontend will handle this by showing LocationEntry modal
            self.send_json({'error': 'Location not found. Please set your location.'}, 404)

        except Exception as e:
            print(f"[civic_api] ERROR serving user location: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_google_maps_key(self):
        """
        Handle GET /api/config/google-maps-key

        Returns Google Maps API key for frontend Places Autocomplete.
        This is a public endpoint - API key should be restricted by HTTP referrer in Google Cloud Console.

        Response format:
        {
          "api_key": "AIza..."
        }
        """
        try:
            api_key = os.getenv('GOOGLE_MAPS_API_KEY')
            if not api_key:
                self.send_json({'error': 'Google Maps API key not configured'}, 500)
                return

            self.send_json({'api_key': api_key})

        except Exception as e:
            print(f"[civic_api] ERROR serving Google Maps API key: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    # ===== PERSONALIZATION ENDPOINTS =====

    def serve_user_profile(self):
        """
        Handle GET /api/user/profile

        Get authenticated user's profile with demographics, preferences, and completeness score.
        User ID extracted from Bearer token.

        Response format:
        {
          "user_id": "user123",
          "display_name": "Jane Doe",
          "jurisdiction_id": "city-berkeley",
          "stakes": ["homeowner", "parent"],
          "years_in_area": 15,
          "civic_interests": ["housing", "education"],
          "profile_completeness": 65,
          ...
        }
        """
        try:
            # Get user_id from Bearer token
            user_id = self.get_user_id_from_token()
            if not user_id:
                self.send_json({'error': 'Authentication required'}, 401)
                return

            # Check if PersonalizationService is available
            if not personalization_service:
                self.send_json({'error': 'Personalization service not available'}, 503)
                return

            # Get user profile
            profile = personalization_service.get_user_profile(user_id)

            if not profile:
                self.send_json({'error': 'Profile not found', 'user_id': user_id}, 404)
                return

            self.send_json(profile)

        except Exception as e:
            print(f"[civic_api] ERROR serving user profile: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_user_civic_history(self):
        """
        Handle GET /api/user/civic-history

        Get user's civic action history with optional filtering.
        User ID extracted from Bearer token.

        Query parameters:
        - action_types: Comma-separated list of action types (optional)
        - since: ISO date to filter actions after (optional)
        - limit: Max number of results (default: 100, max: 500)

        Response format:
        {
          "user_id": "user123",
          "actions": [
            {
              "action_id": "uuid",
              "action_type": "event_clicked",
              "entity_type": "event",
              "entity_id": "event-123",
              "created_at": "2025-10-29T12:00:00",
              "metadata": {"topic": "housing"},
              "jurisdiction_id": "city-berkeley",
              "topic": "housing"
            }
          ],
          "count": 42
        }
        """
        try:
            # Get user_id from Bearer token
            user_id = self.get_user_id_from_token()
            if not user_id:
                self.send_json({'error': 'Authentication required'}, 401)
                return

            # Check if PersonalizationService is available
            if not personalization_service:
                self.send_json({'error': 'Personalization service not available'}, 503)
                return

            # Parse query parameters
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            # Extract filters
            action_types_param = query_params.get('action_types', [None])[0]
            action_types = action_types_param.split(',') if action_types_param else None

            since_param = query_params.get('since', [None])[0]
            since = datetime.fromisoformat(since_param) if since_param else None

            limit_param = query_params.get('limit', ['100'])[0]
            limit = min(int(limit_param), 500)  # Cap at 500

            # Get civic history
            actions = personalization_service.get_civic_history(
                user_id,
                action_types=action_types,
                since=since,
                limit=limit
            )

            self.send_json({
                'user_id': user_id,
                'actions': actions,
                'count': len(actions)
            })

        except ValueError as e:
            self.send_json({'error': f'Invalid parameter: {str(e)}'}, 400)
        except Exception as e:
            print(f"[civic_api] ERROR serving civic history: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_user_context(self):
        """
        Handle GET /api/user/context

        Get personalized context for AI features (comment drafting, recommendations).
        User ID extracted from Bearer token.

        Query parameters:
        - type: Context type (demographics|interests|history|full) - default: full

        Response format:
        {
          "stakes": ["homeowner"],
          "yearsInArea": 15,
          "expertise": "urban planning",
          "civicInterests": ["housing"],
          "inferredInterests": {"housing": 0.95, "transportation": 0.42},
          "recentActions": [...]
        }
        """
        try:
            # Get user_id from Bearer token
            user_id = self.get_user_id_from_token()
            if not user_id:
                self.send_json({'error': 'Authentication required'}, 401)
                return

            # Check if PersonalizationService is available
            if not personalization_service:
                self.send_json({'error': 'Personalization service not available'}, 503)
                return

            # Parse query parameters
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)

            context_type = query_params.get('type', ['full'])[0]

            # Validate context type
            valid_types = ['demographics', 'interests', 'history', 'full']
            if context_type not in valid_types:
                self.send_json({'error': f'Invalid context type. Must be one of: {", ".join(valid_types)}'}, 400)
                return

            # Get context
            context = personalization_service.get_context_for_ai(user_id, context_type)

            if not context:
                self.send_json({'error': 'Profile not found', 'user_id': user_id}, 404)
                return

            self.send_json(context)

        except Exception as e:
            print(f"[civic_api] ERROR serving user context: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_user_export(self):
        """
        Handle GET /api/user/export

        GDPR data export - returns all user data in JSON format.
        User ID extracted from Bearer token.

        Response format:
        {
          "export_date": "2025-10-29T12:00:00",
          "user_id": "user123",
          "profile": {...},
          "civic_history": [...],
          "inferred_interests": {...}
        }
        """
        try:
            # Get user_id from Bearer token
            user_id = self.get_user_id_from_token()
            if not user_id:
                self.send_json({'error': 'Authentication required'}, 401)
                return

            # Check if PersonalizationService is available
            if not personalization_service:
                self.send_json({'error': 'Personalization service not available'}, 503)
                return

            # Get all user data
            profile = personalization_service.get_user_profile(user_id)
            civic_history = personalization_service.get_civic_history(user_id, limit=10000)
            inferred_interests = personalization_service.infer_civic_interests(user_id)

            export_data = {
                'export_date': datetime.now().isoformat(),
                'user_id': user_id,
                'profile': profile,
                'civic_history': civic_history,
                'inferred_interests': inferred_interests
            }

            self.send_json(export_data)

        except Exception as e:
            print(f"[civic_api] ERROR serving user export: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_legislative_state(self, topic: str):
        """
        Serve state legislation by topic.

        Endpoint: GET /api/legislative/state?topic={topic}
        Topics: housing, transportation, environment, budget, education

        Response format:
        {
          "bills": [
            {
              "bill": "California Housing Opportunity and More Efficiency (HOME) Act",
              "status": "Active",
              "leverage_point": "...",
              "official_url": "...",
              "title": "SB 9 (2021)",
              ...
            }
          ],
          "metadata": {
            "topic": "housing",
            "count": 6,
            "last_updated": "2025-10-07T14:03:15Z"
          }
        }
        """
        try:
            # Session 64: Map common aliases to canonical topics
            topic_aliases = {
                'cdbg': 'budget',  # CDBG is a federal budget program
                'funding': 'budget',
                'grants': 'budget'
            }
            topic = topic_aliases.get(topic.lower(), topic)

            # Validate topic
            valid_topics = ['housing', 'transportation', 'environment', 'budget', 'education']
            if topic not in valid_topics:
                self.send_json({
                    'error': f'Invalid topic. Must be one of: {", ".join(valid_topics)}'
                }, 400)
                return

            # Load state legislation file for topic
            leg_file = Path(f'data/legislation/state/california/{topic}.json')

            if not leg_file.exists():
                self.send_json({
                    'bills': [],
                    'metadata': {
                        'topic': topic,
                        'count': 0,
                        'error': f'No state legislation data available for topic: {topic}'
                    }
                })
                return

            with open(leg_file, 'r') as f:
                data = json.load(f)

            # Extract state legislation
            state_legislation = data.get('state_legislation', {})
            bills = []

            for bill_id, bill_data in state_legislation.items():
                bills.append({
                    'bill': bill_data.get('bill'),
                    'status': bill_data.get('status'),
                    'leverage_point': bill_data.get('leverage_point'),
                    'official_url': bill_data.get('official_url'),
                    'title': f"{bill_id.upper().replace('CA-', '')} ({bill_data.get('enacted', '')[:4]})",
                    'summary': bill_data.get('summary'),
                    'keywords': bill_data.get('keywords', [])
                })

            self.send_json({
                'bills': bills,
                'metadata': {
                    'topic': topic,
                    'count': len(bills),
                    'last_updated': data.get('last_updated')
                }
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving state legislation: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_legislative_federal(self, topic: str):
        """
        Serve federal programs by topic.

        Endpoint: GET /api/legislative/federal?topic={topic}
        Topics: housing, transportation, environment, budget, education

        Response format:
        {
          "programs": [
            {
              "program_name": "Community Development Block Grant",
              "agency": "HUD",
              "leverage_point": "...",
              "info_url": "...",
              "fy2025_allocation": "$3.3B national",
              ...
            }
          ],
          "metadata": {
            "topic": "housing",
            "count": 4,
            "last_updated": "2025-10-07T16:01:43Z"
          }
        }
        """
        try:
            # Session 64: Map common aliases to canonical topics
            topic_aliases = {
                'cdbg': 'budget',  # CDBG is a federal budget program
                'funding': 'budget',
                'grants': 'budget'
            }
            topic = topic_aliases.get(topic.lower(), topic)

            # Validate topic
            valid_topics = ['housing', 'transportation', 'environment', 'budget', 'education']
            if topic not in valid_topics:
                self.send_json({
                    'error': f'Invalid topic. Must be one of: {", ".join(valid_topics)}'
                }, 400)
                return

            # Load federal programs file for topic
            fed_file = Path(f'data/funding/federal/{topic}.json')

            if not fed_file.exists():
                self.send_json({
                    'programs': [],
                    'metadata': {
                        'topic': topic,
                        'count': 0,
                        'error': f'No federal programs data available for topic: {topic}'
                    }
                })
                return

            with open(fed_file, 'r') as f:
                data = json.load(f)

            # Extract federal programs
            programs_data = data.get('programs', {})
            programs = []

            for program_id, program_info in programs_data.items():
                programs.append({
                    'program_name': program_info.get('program_name'),
                    'agency': program_info.get('administering_agency'),
                    'leverage_point': program_info.get('leverage_point'),
                    'info_url': program_info.get('official_url'),
                    'fy2025_allocation': program_info.get('fy2025_allocation'),
                    'description': program_info.get('description'),
                    'keywords': program_info.get('keywords', [])
                })

            self.send_json({
                'programs': programs,
                'metadata': {
                    'topic': topic,
                    'count': len(programs),
                    'last_updated': data.get('last_updated')
                }
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving federal programs: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def detect_refresh_need(self, user_input: str) -> bool:
        """Detect when users need current data"""
        freshness_keywords = [
            'this week', 'upcoming', 'next meeting', 'current',
            'latest', 'recent', 'when is', 'scheduled'
        ]

        # Check if user is asking about current events
        needs_fresh = any(keyword in user_input.lower() for keyword in freshness_keywords)

        # Check data age
        import glob, os, time
        schema_files = glob.glob('data/events/events_*.json')
        if schema_files:
            latest_file = max(schema_files, key=os.path.getmtime)
            age_days = (time.time() - os.path.getmtime(latest_file)) / 86400
            return needs_fresh and age_days > 3

        return False

    def trigger_background_refresh(self, scope='current_active_only'):
        """UX-aware background refresh with temporal filtering"""
        import threading
        import subprocess
        import time
        from datetime import datetime, timedelta

        def refresh_worker():
            """Background refresh with temporal scope filtering"""
            try:
                # Log refresh start for UX monitoring
                print(f"🔄 Background refresh triggered ({scope}): {time.strftime('%Y-%m-%d %H:%M:%S')}")

                # Determine temporal filtering based on scope
                if scope == 'future_meetings_only':
                    # Short-term strategy: Only future meetings
                    cmd_args = ['--future-only']
                elif scope == 'include_recent_past':
                    # Long-term strategy: Include recent past (6 months) for context
                    cmd_args = ['--include-recent-past']
                else:  # current_active_only
                    # Default: Current and upcoming only
                    cmd_args = []

                # Execute refresh with temporal filtering
                cmd = ['python', 'src/automated_civic_refresh.py'] + cmd_args
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5-minute timeout
                )

                if result.returncode == 0:
                    print(f"✅ Background refresh completed successfully ({scope})")
                    # Parse output to report filtering results
                    output_lines = result.stdout.split('\n')
                    for line in output_lines:
                        if 'events generated' in line.lower():
                            print(f"📅 {line}")
                else:
                    print(f"❌ Background refresh failed: {result.stderr[:200]}")
                    # Log failure for UX team to monitor user impact

            except subprocess.TimeoutExpired:
                print(f"⏰ Background refresh timed out ({scope}) - will retry in next cycle")
            except Exception as e:
                print(f"🚨 Background refresh error ({scope}): {e}")

        # Start background refresh without blocking user experience
        threading.Thread(target=refresh_worker, daemon=True).start()

    def refresh_data(self):
        """Trigger data refresh using direct module import (secure implementation)"""
        try:
            print("Refreshing civic data...")
            
            # Import civic_digest module directly instead of using subprocess
            try:
                from . import civic_digest
            except ImportError:
                import civic_digest
            
            # Create digest instance (same as civic_digest.py does)
            digest = civic_digest.CivicDigest()
            
            # Use known working URL (same as test command)
            test_url = "https://www.cityofsanrafael.org/meetings/planning-commission-may-27-2025/"
            
            # Run the scraping (without sending email)
            events = digest.scrape_meeting(test_url)
            
            self.send_json({
                'status': 'success',
                'message': 'Data refreshed successfully',
                'opportunities_found': len(events),
                'test_url': test_url,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            print(f"[civic_api] ERROR refreshing data: {str(e)}")
            self.send_error(500, f"Refresh error: {str(e)}")
    
    def handle_conversation(self):
        """
        Handle AI conversation endpoint with civic context.
        Session 81: Migrated to persistent ConversationStore.

        Legacy endpoint for conversational HTML interface.
        """
        # Check if ConversationStore is available, fallback to in-memory if not
        use_persistent_storage = CONVERSATION_STORE_AVAILABLE and conversation_store is not None

        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                audit_logger.warning(f"Conversation request with no body from {self.client_address[0]}")
                self.send_json({'error': 'No message provided'}, 400)
                return

            body = self.rfile.read(content_length)
            data = json.loads(body)

            # Validate required fields
            message = data.get('message', '').strip()
            if not message:
                audit_logger.warning(f"Conversation request with empty message from {self.client_address[0]}")
                self.send_json({'error': 'Message is required'}, 400)
                return

            # Validate and sanitize input
            validation = conversation_manager.validate_input(message)
            if not validation.is_valid:
                audit_logger.warning(f"Invalid input detected from {self.client_address[0]}: {validation.error_message}")
                self.send_json({
                    'error': 'Invalid input',
                    'message': validation.error_message
                }, 400)
                return

            # Use sanitized message
            message = validation.sanitized_value

            # Extract context from request (needed for issue detection)
            conversation_id = data.get('conversation_id')
            user_id = data.get('user_id')
            city = data.get('city')  # No default - require explicit city for issue handling
            state = data.get('state', 'California')
            county = data.get('county', 'Marin County')
            interests = data.get('interests', [])
            event_context = data.get('event_context')  # NEW: Event-specific context for draft comments

            # Get or create conversation in persistent storage
            if use_persistent_storage:
                if not conversation_id:
                    # Create new conversation in persistent store
                    conversation_id = conversation_store.create_conversation(
                        user_id=user_id,
                        title=None  # Will auto-generate from first message
                    )
                    audit_logger.info(f"Created new persistent conversation: {conversation_id[:8]}...")
                else:
                    # Use existing conversation
                    pass
            else:
                # Fallback to in-memory storage (legacy behavior)
                if not conversation_id:
                    conversation_id = str(uuid.uuid4())

            # DEBUG: Log what we received
            print(f"[civic_api] DEBUG Conversation Request:")
            print(f"  - City: {city}")
            print(f"  - Event context received: {event_context is not None}")
            if event_context:
                print(f"  - Event title: {event_context.get('title', 'N/A')}")
                print(f"  - Event when: {event_context.get('when', 'N/A')}")
                print(f"  - Event description: {event_context.get('description', 'N/A')[:100]}...")
                print(f"  - Event project_type: {event_context.get('project_type', 'N/A')}")

            # === NEW: Complaint Detection ===
            # Check if message is a issue and handle accordingly
            audit_logger.info(f"Complaint detection | HANDLER_AVAILABLE: {COMPLAINT_HANDLER_AVAILABLE}")
            if COMPLAINT_HANDLER_AVAILABLE:
                try:
                    # Build user context for issue handler
                    jurisdiction_map = {
                        'Berkeley': 'city-berkeley',
                        'Oakland': 'city-oakland',
                        'San Rafael': 'city-san-rafael',
                        'Santa Rosa': 'city-santa-rosa',
                        'Hayward': 'city-hayward',
                        'El Cerrito': 'city-el-cerrito'
                    }
                    jurisdiction_id = jurisdiction_map.get(city)

                    user_context = {
                        'jurisdiction_id': jurisdiction_id,
                        'name': data.get('user_name'),
                        'email': data.get('user_email')
                    }

                    # Try issue handling first
                    print(f"[civic_api] DEBUG: Calling issue handler with message: '{message[:50]}...', jurisdiction: {jurisdiction_id}")
                    complaint_response = handle_issue(
                        message=message,
                        user_id=user_id or 'anonymous',
                        user_context=user_context
                    )
                    print(f"[civic_api] DEBUG: Issue handler returned type: '{complaint_response['type']}'")

                    # If it's a issue (matched or no_match), return issue response
                    if complaint_response['type'] in ['matched', 'no_match', 'missing_jurisdiction']:
                        print(f"[civic_api] DEBUG: Complaint detected! Formatting response...")
                        # Format response for conversational UI
                        response_data = self.format_complaint_response(
                            complaint_response,
                            conversation_id
                        )

                        # Log issue handling
                        audit_logger.info(
                            f"Complaint handled | Type: {complaint_response['type']} | "
                            f"User: {user_id or 'anonymous'} | "
                            f"ConvID: {conversation_id[:8]}..."
                        )

                        self.send_json(response_data)
                        return
                    else:
                        print(f"[civic_api] DEBUG: Not a issue (type: '{complaint_response['type']}'), falling through to normal conversation")

                except Exception as e:
                    # Log error but continue with normal conversation
                    print(f"[civic_api] Issue handler error (falling back to conversation): {e}")
                    import traceback
                    traceback.print_exc()
                    audit_logger.warning(f"Issue handler error | ConvID: {conversation_id[:8]}... | Error: {str(e)}")

            # === END: Complaint Detection ===

            # Check if user query indicates need for fresh data and trigger background refresh
            if self.detect_refresh_need(message):
                print(f"🔄 User query indicates need for fresh data: '{message[:50]}...'")
                # Analyze intent to determine optimal refresh scope
                intent_analysis = get_data_freshness_manager().analyze_user_intent(message)
                if intent_analysis['temporal_focus'] == 'future_only':
                    refresh_scope = 'future_meetings_only'
                elif intent_analysis['temporal_focus'] == 'recent_past':
                    refresh_scope = 'include_recent_past'
                else:
                    refresh_scope = 'current_active_only'

                # Trigger non-blocking background refresh
                self.trigger_background_refresh(scope=refresh_scope)

            # Log conversation attempt
            audit_logger.info(f"Conversation request | IP: {self.client_address[0]} | User: {user_id or 'anonymous'} | City: {city} | ConvID: {conversation_id[:8]}... | Length: {len(message)} chars | Event: {event_context.get('title', 'None') if event_context else 'None'}")

            # Get conversation history for AI context
            if use_persistent_storage:
                # Load civic events and build system prompt
                events = self.get_civic_context(city)
                filtered_opportunities = self.filter_opportunities_by_interests(events, interests)
                system_prompt = self.build_civic_system_prompt(city, state, county, interests, filtered_opportunities, event_context)

                # Get conversation history from persistent store
                # Include system prompt as active context (ephemeral, regenerated each turn)
                conversation_history = conversation_store.get_messages_for_llm(
                    conversation_id,
                    active_context={'system_prompt': system_prompt}
                )
            else:
                # Fallback: use in-memory conversation manager
                conversation_history = None  # Will be handled by generate_ai_response

            # Generate AI response
            ai_response, usage_data = self.generate_ai_response(
                message, conversation_id, city, state, county, interests, event_context,
                conversation_history=conversation_history,
                use_persistent_storage=use_persistent_storage
            )
            
            # Extract action buttons from AI response and events
            action_result = self.extract_action_buttons(ai_response, city, interests)
            
            # Check data freshness and add warning if stale
            freshness = self.get_data_freshness()
            response_data = {
                'response': ai_response,
                'actions': action_result.get('legacy_actions', []),  # For backward compatibility
                'grouped_actions': action_result.get('grouped_actions', []),  # New grouped structure
                'conversation_id': conversation_id,
                'timestamp': datetime.now().isoformat()
            }
            
            if freshness and freshness['is_stale']:
                response_data['data_warning'] = f"Note: Civic data is {freshness['age_days']} days old. Information may not reflect the most current meetings and events."
                response_data['data_freshness'] = {
                    'age_days': freshness['age_days'],
                    'last_updated': freshness['last_updated']
                }
            
            # Store messages in conversation history
            if use_persistent_storage:
                # Store user message
                conversation_store.add_message(
                    conversation_id,
                    role='user',
                    content=message
                )

                # Store assistant response
                conversation_store.add_message(
                    conversation_id,
                    role='assistant',
                    content=ai_response,
                    metadata={
                        'model': usage_data.get('model') if usage_data else None,
                        'usage': usage_data.get('usage') if usage_data else None,
                        'actions_count': sum(len(g.get('actions', [])) for g in action_result.get('grouped_actions', []))
                    }
                )

                # Auto-generate title from first message if needed
                conv = conversation_store.get_conversation(conversation_id)
                if not conv.get('title'):
                    title = self._generate_conversation_title(message)
                    conversation_store.update_title(conversation_id, title)

            # Log successful response
            total_actions = sum(len(g.get('actions', [])) for g in action_result.get('grouped_actions', []))
            response_len = len(ai_response) if ai_response else 0
            storage_type = "persistent" if use_persistent_storage else "in-memory"
            audit_logger.info(f"Conversation response ({storage_type}) | ConvID: {conversation_id[:8]}... | Response length: {response_len} chars | Actions: {total_actions} | Data age: {freshness['age_days'] if freshness else 'unknown'} days | Success: true")

            # Send response with action buttons and freshness info
            self.send_json(response_data)
            
        except json.JSONDecodeError:
            audit_logger.warning(f"Invalid JSON in conversation request from {self.client_address[0]}")
            self.send_json({'error': 'Invalid JSON'}, 400)
        except Exception as e:
            audit_logger.error(f"Conversation error | IP: {self.client_address[0]} | Error: {type(e).__name__}")
            self.send_json({
                'error': 'Internal server error',
                'message': 'An error occurred processing your request'
            }, 500)

    def format_complaint_response(self, complaint_response: dict, conversation_id: str) -> dict:
        """
        Format issue handler response for conversational UI.

        Converts issue handler structured response into the format
        expected by the conversational UI (compatible with existing chat interface).
        """
        response_type = complaint_response['type']

        if response_type == 'matched':
            # Complaint matched to civic events
            matches = complaint_response.get('matches', [])

            # Build conversational response text
            response_text = complaint_response.get('message', 'Found relevant civic meetings:')
            response_text += f"\n\n{len(matches)} upcoming meeting{'s' if len(matches) != 1 else ''} where you can address this issue:"

            for i, match in enumerate(matches, 1):
                response_text += f"\n\n{i}. **{match['title']}**"
                response_text += f"\n   📅 {match['when']}"
                response_text += f"\n   ✨ {match['why_relevant']}"

            response_text += "\n\nI can help you prepare for these meetings. Would you like to:"
            response_text += "\n- Draft a public comment"
            response_text += "\n- Learn about the meeting format"
            response_text += "\n- Get reminders before the meeting"

            # Build action buttons (convert issue actions to UI actions)
            grouped_actions = []
            for match in matches:
                actions = []

                # Add calendar action
                actions.append({
                    'type': 'calendar',
                    'label': 'Add to Calendar',
                    'icon': '📅',
                    'event': {
                        'title': match['title'],
                        'start': match.get('when'),  # Should be ISO format
                        'description': match.get('why_relevant', ''),
                        'url': match.get('source_url')
                    }
                })

                # Add view details action
                if match.get('source_url'):
                    actions.append({
                        'type': 'link',
                        'label': 'View Meeting Details',
                        'icon': '🔗',
                        'url': match['source_url']
                    })

                # Add learn more action
                actions.append({
                    'type': 'learn_more',
                    'label': 'Ask Questions',
                    'icon': '💡',
                    'context': f"Tell me more about how I can participate in: {match['title']}"
                })

                grouped_actions.append({
                    'opportunity_title': match['title'],
                    'actions': actions
                })

            return {
                'response': response_text,
                'type': 'complaint_matched',
                'issue_id': complaint_response.get('issue_id'),
                'grouped_actions': grouped_actions,
                'actions': [],  # Legacy format
                'conversation_id': conversation_id,
                'timestamp': datetime.now().isoformat(),
                'metadata': {
                    'match_count': len(matches),
                    'handler_type': 'issue'
                }
            }

        elif response_type == 'no_match':
            # Complaint stored but no matches found
            response_text = complaint_response.get('message', 'Thank you for reporting this issue.')

            similar_count = complaint_response.get('similar_count', 0)
            if similar_count > 0:
                response_text += f"\n\n💬 Good news: {similar_count} other resident{'s' if similar_count != 1 else ''} "
                response_text += f"reported similar issues. Community support can help get this addressed!"

            response_text += "\n\nI'll track this issue and notify you when relevant meetings are scheduled."
            response_text += "\n\nIn the meantime, you can:"
            response_text += "\n- Report directly to the city"
            response_text += "\n- Connect with others who reported similar issues"
            response_text += "\n- Explore other civic opportunities in your city"

            return {
                'response': response_text,
                'type': 'complaint_no_match',
                'issue_id': complaint_response.get('issue_id'),
                'grouped_actions': [],
                'actions': [],
                'conversation_id': conversation_id,
                'timestamp': datetime.now().isoformat(),
                'metadata': {
                    'similar_complaints': similar_count,
                    'handler_type': 'issue'
                }
            }

        elif response_type == 'missing_jurisdiction':
            # Need to clarify which city
            response_text = complaint_response.get('message')
            response_text += "\n\nSupported cities:"
            response_text += "\n- Berkeley\n- Oakland\n- San Rafael\n- Santa Rosa\n- Hayward\n- El Cerrito"

            return {
                'response': response_text,
                'type': 'clarification_needed',
                'conversation_id': conversation_id,
                'timestamp': datetime.now().isoformat(),
                'metadata': {
                    'clarification_type': 'jurisdiction',
                    'handler_type': 'issue'
                }
            }

        else:
            # Not a issue - should not reach here, but handle gracefully
            return {
                'response': 'How can I help you with civic information?',
                'type': 'general',
                'conversation_id': conversation_id,
                'timestamp': datetime.now().isoformat()
            }

    def handle_route_chat(self):
        """
        Handle chat routing endpoint (Session 27 - Chat-first navigation).
        Session 80: Migrated to persistent ConversationStore.

        Routes user chat messages to appropriate functions using OpenAI function calling.
        Enables natural language navigation: "show housing meetings" → search_events()

        POST /api/chat/route
        Request:
            {
                "message": "Show me housing meetings in Berkeley",
                "conversation_id": "optional-session-id",
                "user_id": "optional-user-id",
                "context": {
                    "current_artifact": "event-123",
                    "current_jurisdiction": "city-berkeley"
                }
            }

        Response:
            {
                "action": "search_events",
                "parameters": {"query": "housing", "jurisdiction": "Berkeley"},
                "reasoning": "I'll search for housing-related meetings in Berkeley.",
                "conversation_id": "abc-123",
                "usage": {"prompt_tokens": 450, "completion_tokens": 180, "total_tokens": 630}
            }
        """
        if not CHAT_ROUTING_AVAILABLE:
            self.send_json({
                'error': 'Chat routing not available',
                'message': 'Chat routing system is not configured. Please contact support.'
            }, 503)
            return

        # Check if ConversationStore is available, fallback to in-memory if not
        use_persistent_storage = CONVERSATION_STORE_AVAILABLE and conversation_store is not None

        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                audit_logger.warning(f"Chat route request with no body from {self.client_address[0]}")
                self.send_json({'error': 'No message provided'}, 400)
                return

            body = self.rfile.read(content_length)
            data = json.loads(body)

            # Validate required fields
            message = data.get('message', '').strip()
            if not message:
                audit_logger.warning(f"Chat route request with empty message from {self.client_address[0]}")
                self.send_json({'error': 'Message is required'}, 400)
                return

            # Extract optional fields
            conversation_id = data.get('conversation_id')
            user_id = data.get('user_id')  # Session 80: user association
            context = data.get('context', {})
            mode = data.get('mode', 'navigation')  # Session 55: chat mode
            serialized_context = data.get('serialized_context', '')  # Session 55: LLM context
            model_override = data.get('model_override')  # Session 88: Manual model selection

            # Active UI context (ephemeral, not stored in DB)
            active_context = {
                'serialized_artifacts': serialized_context,
                'current_jurisdiction': context.get('current_jurisdiction'),
                'user_city': context.get('user_city'),
                'current_artifact': context.get('current_artifact')
            }

            # Get or create conversation
            if use_persistent_storage:
                if not conversation_id:
                    # Create new conversation in persistent store
                    conversation_id = conversation_store.create_conversation(
                        user_id=user_id,
                        title=None  # Will auto-generate from first message
                    )
                    audit_logger.info(f"Created new persistent conversation: {conversation_id[:8]}...")

                # Get conversation history with active context injection
                conversation_history = conversation_store.get_messages_for_llm(
                    conversation_id,
                    active_context=active_context
                )
            else:
                # Fallback to in-memory storage (legacy behavior)
                if not conversation_id:
                    conversation_id = str(uuid.uuid4())
                    CONVERSATIONS[conversation_id] = []
                conversation_history = CONVERSATIONS.get(conversation_id, [])

            # Route the message
            router = get_router()
            result = router.route_message(
                message=message,
                conversation_history=conversation_history,
                context=context,
                mode=mode,
                serialized_context=serialized_context,
                model_override=model_override  # Session 88: Manual model selection
            )

            # Store messages in conversation history
            if use_persistent_storage:
                # Store user message
                conversation_store.add_message(
                    conversation_id,
                    role='user',
                    content=message
                )

                # Store assistant response
                if result.get('clarify'):
                    # Session 60: Clarification response
                    # Store clarify data in metadata for now (not in OpenAI format)
                    conversation_store.add_message(
                        conversation_id,
                        role='assistant',
                        content=result.get('message', ''),
                        metadata={
                            'clarify': result['clarify'],
                            'model': result.get('model_used'),
                            'provider': result.get('provider_used'),
                            'usage': result.get('usage')
                        }
                    )
                elif result['action'] != 'respond':
                    # Function call - store with tool_calls in OpenAI format
                    tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
                    conversation_store.add_message(
                        conversation_id,
                        role='assistant',
                        content=result.get('reasoning', ''),
                        tool_calls=[{
                            'id': tool_call_id,
                            'type': 'function',
                            'function': {
                                'name': result['action'],
                                'arguments': json.dumps(result.get('parameters', {}))
                            }
                        }],
                        metadata={
                            'model': result.get('model_used'),
                            'provider': result.get('provider_used'),
                            'usage': result.get('usage')
                        }
                    )

                    # Session 82: Store tool response message (required by OpenAI API)
                    # Format the function execution results for the next turn
                    tool_response_content = json.dumps({
                        'action': result['action'],
                        'parameters': result.get('parameters', {}),
                        'message': result.get('message', ''),
                        'reasoning': result.get('reasoning', '')
                    })
                    conversation_store.add_message(
                        conversation_id,
                        role='tool',
                        content=tool_response_content,
                        tool_call_id=tool_call_id
                    )
                else:
                    # Regular response
                    conversation_store.add_message(
                        conversation_id,
                        role='assistant',
                        content=result.get('message', ''),
                        metadata={
                            'model': result.get('model_used'),
                            'provider': result.get('provider_used'),
                            'usage': result.get('usage')
                        }
                    )

                # Auto-generate title from first message if needed
                conv = conversation_store.get_conversation(conversation_id)
                if not conv.get('title'):
                    title = self._generate_conversation_title(message)
                    conversation_store.update_title(conversation_id, title)

            else:
                # Fallback: Update in-memory conversation history (legacy behavior)
                # Session 55.5: Preserve function_call structure for proper LLM reasoning
                # Session 60: Preserve structured clarify details for follow-up context
                assistant_message = {"role": "assistant"}

                if result.get('clarify'):
                    # Session 60: Preserve structured clarify details for follow-up context
                    assistant_message['content'] = result.get('message', '')
                    assistant_message['clarify'] = result['clarify']  # Structured {question, options[{id, display}]}
                elif result['action'] != 'respond':
                    # Function call - preserve OpenAI function_call format
                    assistant_message['content'] = None
                    assistant_message['function_call'] = {
                        'name': result['action'],
                        'arguments': json.dumps(result.get('parameters', {}))
                    }
                else:
                    # Conversational response
                    assistant_message['content'] = result.get('message', '')

                CONVERSATIONS[conversation_id] = conversation_history + [
                    {"role": "user", "content": message},
                    assistant_message
                ]

            # Add conversation_id to response
            result['conversation_id'] = conversation_id

            # Log chat routing
            storage_type = "persistent" if use_persistent_storage else "in-memory"
            audit_logger.info(
                f"Chat routing ({storage_type}) | Action: {result['action']} | "
                f"User: {self.client_address[0]} | "
                f"ConvID: {conversation_id[:8]}..."
            )

            self.send_json(result)

        except json.JSONDecodeError:
            audit_logger.error(f"Invalid JSON in chat route request from {self.client_address[0]}")
            self.send_json({'error': 'Invalid JSON'}, 400)
        except Exception as e:
            audit_logger.error(f"Error routing chat message: {e}", exc_info=True)
            self.send_json({
                'error': 'Internal server error',
                'message': 'Failed to route message. Please try again.'
            }, 500)

    def _generate_conversation_title(self, first_message: str) -> str:
        """Generate conversation title from first user message.

        Simple heuristic: Use first 50 chars, or extract key topic.
        Future: Could use LLM to generate better titles.

        Args:
            first_message: First message in the conversation

        Returns:
            Generated title (max 50 chars)
        """
        # Simple truncation for now
        title = first_message.strip()
        if len(title) > 50:
            title = title[:47] + "..."

        return title

    def generate_ai_response(self, message: str, conversation_id: str,
                            city: str, state: str, county: str,
                            interests: List[str], event_context: dict = None,
                            conversation_history: List[dict] = None,
                            use_persistent_storage: bool = False) -> tuple:
        """Generate AI response with civic context
        Session 81: Updated to support persistent ConversationStore.

        Args:
            message: User's message
            conversation_id: Conversation ID
            city: City name
            state: State name
            county: County name
            interests: User's interests
            event_context: Optional event-specific context for targeted responses
                          (e.g., when drafting comments for specific events)
            conversation_history: Optional conversation history from ConversationStore
            use_persistent_storage: Whether using persistent storage (affects return value)

        Returns:
            Tuple of (ai_message: str, usage_data: dict) where usage_data contains model/usage info
        """

        try:
            # Initialize provider via task-based routing for conversational queries
            from llm_provider import get_model_for_task
            provider = get_model_for_task('conversational')

            # Load civic events for context
            events = self.get_civic_context(city)

            # Build system prompt with civic context - filter by user interests
            filtered_opportunities = self.filter_opportunities_by_interests(events, interests)
            system_prompt = self.build_civic_system_prompt(city, state, county, interests, filtered_opportunities, event_context)

            print(f"[civic_api] DEBUG System prompt length: {len(system_prompt)} chars")
            print(f"[civic_api] DEBUG System prompt includes event context: {'🎯 FOCUSED EVENT CONTEXT' in system_prompt}")

            # Get conversation history
            if use_persistent_storage and conversation_history is not None:
                # Using persistent storage - conversation history already includes system prompt
                # Just need to add user message for this turn
                # Add user message (with event context hint if available)
                if event_context:
                    # Prepend event context reminder to user message
                    enhanced_message = f"[Context: Viewing event '{event_context.get('title', 'N/A')}']\n\n{message}"
                    print(f"[civic_api] DEBUG Enhanced user message: {enhanced_message[:150]}...")
                    user_message_content = enhanced_message
                else:
                    print(f"[civic_api] DEBUG User message (no event context): {message[:150]}...")
                    user_message_content = message

                # Append user message to history for this API call
                messages = conversation_history + [{"role": "user", "content": user_message_content}]
            else:
                # Fallback: use in-memory conversation manager
                if not conversation_manager.get_context(conversation_id):
                    # Initialize conversation with system prompt ONLY on first message
                    conversation_manager.add_message(conversation_id, "system", system_prompt)
                elif event_context:
                    # If we have event context but conversation exists, update system prompt
                    # This ensures event-specific instructions are always included
                    conversation_manager.messages[conversation_id] = [
                        {"role": "system", "content": system_prompt}
                    ] + [msg for msg in conversation_manager.get_context(conversation_id) if msg["role"] != "system"]

                # Add user message (with event context hint if available)
                if event_context:
                    # Prepend event context reminder to user message
                    enhanced_message = f"[Context: Viewing event '{event_context.get('title', 'N/A')}']\n\n{message}"
                    print(f"[civic_api] DEBUG Enhanced user message: {enhanced_message[:150]}...")
                    conversation_manager.add_message(conversation_id, "user", enhanced_message)
                else:
                    print(f"[civic_api] DEBUG User message (no event context): {message[:150]}...")
                    conversation_manager.add_message(conversation_id, "user", message)

                # Get messages for API call
                messages = conversation_manager.get_context(conversation_id)
            
            # Call LLM via provider abstraction
            print(f"[civic_api] DEBUG: Calling LLM with {len(messages)} messages using model {provider.default_model}")
            print(f"[civic_api] DEBUG: Message roles: {[msg['role'] for msg in messages]}")
            print(f"[civic_api] DEBUG: Last user message: {messages[-1]['content'][:200] if messages[-1]['role'] == 'user' else 'N/A'}...")

            response = provider.complete(
                messages=messages,
                max_tokens=1000,
                timeout=30
            )

            print(f"[civic_api] DEBUG: LLM response received")
            ai_message = response.content

            print(f"[civic_api] DEBUG: AI message content: {ai_message[:100] if ai_message else 'NONE/EMPTY'}")

            # Handle None or empty response
            if not ai_message:
                print(f"[civic_api] WARNING: LLM returned empty content, using fallback")
                return self.generate_fallback_response(message, city), None

            # Collect usage data
            usage_data = {
                'model': provider.default_model,
                'usage': {
                    'prompt_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else 0,
                    'completion_tokens': response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else 0,
                    'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
                }
            }

            # Store AI response in history (only for in-memory fallback)
            if not use_persistent_storage:
                conversation_manager.add_message(conversation_id, "assistant", ai_message)

            return ai_message, usage_data

        except Exception as e:
            print(f"[civic_api] LLM API error occurred: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return self.generate_fallback_response(message, city), None
    
    def build_civic_system_prompt(self, city: str, state: str, county: str,
                                 interests: List[str], events: List[dict],
                                 event_context: dict = None) -> str:
        """Build system prompt with civic context

        Args:
            city: City name
            state: State name
            county: County name
            interests: User's interests
            events: List of civic events
            event_context: Optional specific event context for targeted responses
        """
        prompt = f"""You are a helpful civic engagement assistant for {city}, {state}.

Your role is to help residents understand and participate in local government.
Be conversational, friendly, and encouraging about civic participation.

Current location: {city}, {county}, {state}
User interests: {', '.join(interests) if interests else 'general civic engagement'}"""

        # Add event-specific context if provided
        if event_context:
            prompt += f"""

🎯 FOCUSED EVENT CONTEXT:
The user is currently viewing this specific event and asking for help:
- Title: {event_context.get('title', 'N/A')}
- Date: {event_context.get('when', 'N/A')}
- Description: {event_context.get('description', 'N/A')}
- Project Type: {event_context.get('project_type', 'general')}

**IMPORTANT - Draft Comment Instructions:**
When the user asks to draft a public comment or help with commenting:
1. Generate a professional, well-structured public comment template
2. Reference the SPECIFIC event title and details above
3. Include placeholders for the user to personalize (e.g., [your name], [your address], [your specific concern])
4. Structure the comment with:
   - Opening: State your name and address (placeholder)
   - Position: Clear statement of support/opposition/concern
   - Reasoning: 2-3 specific points related to THIS event
   - Local impact: How this affects the community
   - Closing: Thank committee members and request (placeholder)
5. Keep it concise (under 500 words - suitable for 2-3 minute spoken comment)
6. Use respectful, professional language
7. Focus on facts and local impacts, not general opinions

Example structure:
"Dear [Committee Name] Members,

My name is [YOUR NAME] and I reside at [YOUR ADDRESS] in {city}.

I am writing to [express support for / raise concerns about] the [SPECIFIC ITEM FROM EVENT TITLE].

[Point 1 - specific to this event]
[Point 2 - specific to this event]
[Point 3 - local impact specific to {city}]

Thank you for considering my input. I request that [SPECIFIC ACTION YOU WANT].

Respectfully,
[YOUR NAME]"
"""

        prompt += f"""

CURRENT CIVIC OPPORTUNITIES IN {city.upper()} (filtered based on user interests):
"""
        
        if events:
            for opp in events[:5]:  # Include top 5 events with full details
                # Extract meeting details from the data
                meeting_when = opp.get('when', '')
                deadline = opp.get('deadline', '')
                contact_info = opp.get('contact_info', {})
                engagement_info = opp.get('engagement_info', '')
                source_url = opp.get('source_url', '')
                location = opp.get('location', city)
                
                # Make events more prominent
                prompt += f"\n{'='*60}\n"
                prompt += f"📍 OPPORTUNITY: {opp.get('title', 'Untitled')}\n"
                prompt += f"   Why Relevant: Matches your interest in {', '.join(interests) if interests else 'civic engagement'}\n"
                prompt += f"   Description: {opp.get('description', 'No description available')}\n"
                prompt += f"   Meeting Date: {meeting_when if meeting_when else 'Date TBD'}\n"
                prompt += f"   Comment Deadline: {deadline if deadline else 'No specific deadline'}\n"
                prompt += f"   Location: {location}\n"
                
                # Add contact information
                if contact_info:
                    email = contact_info.get('email', '')
                    phone = contact_info.get('phone', '')
                    if email:
                        prompt += f"   Contact Email: {email}\n"
                    if phone:
                        prompt += f"   Contact Phone: {phone}\n"
                
                prompt += f"   How to Participate: {engagement_info}\n"
                if source_url:
                    prompt += f"   Meeting Details: {source_url}\n"
                prompt += "\n"
        else:
            prompt += "\n- No current events loaded\n"
        
        prompt += "\n🎯 RESPONSE GUIDELINES:\n"
        prompt += "1. **Keep responses concise**: Action buttons show detailed opportunity info, so focus your text on guidance and context\n"
        prompt += "2. **Avoid listing opportunity details**: Don't repeat titles, dates, locations that appear in action buttons\n"
        prompt += "3. **Be conversational and strategic**: Provide value beyond what's in the buttons - offer insights, next steps, or helpful context\n"
        prompt += "4. **When users ask about events**: Reference them briefly, focus on what's your next step? or which interests you most?\n"
        prompt += "5. **For discovery queries**: Lead with a short overview, then let action buttons provide the details\n"
        prompt += "6. **End with engaging questions** when appropriate:\n"
        prompt += "   - What specific aspects interest you?\n"
        prompt += "   - What's your preferred way to participate?\n"
        prompt += "   - Are you looking to advocate for a particular outcome?\n"
        prompt += "7. **Guide strategy, not logistics**: Help users think through their approach rather than repeating meeting details\n"

        prompt += "\n📜 LEGISLATIVE CONTEXT GUIDELINES:\n"
        prompt += "When civic opportunity includes legislative_context field:\n"
        prompt += "1. **ONLY surface federal/state context if it increases local action clarity**\n"
        prompt += "2. **Focus on LOCAL LEVERAGE POINTS** - what residents can influence at city level\n"
        prompt += "3. **Use federal/state context to explain WHY this local meeting matters**\n"
        prompt += "4. **NEVER list legislation unless it creates actionable local opportunity**\n"
        prompt += "5. **ALWAYS explain local control points BEFORE mentioning legislation**\n"
        prompt += "\nGood example: 'The Planning Commission meets Tuesday at 6pm to implement SB 9's duplex requirements. You can influence which neighborhoods are affected and what design standards apply. Attending this meeting is your leverage point.'\n"
        prompt += "Bad example: 'Here are 5 California housing bills and 3 federal programs. SB 9 was passed in 2021 and requires cities to allow duplexes...'\n"

        prompt += "\nCRITICAL: Your responses will be displayed with action buttons that show opportunity titles, dates, locations, and contact details.\n"
        prompt += "DO NOT repeat this information in your text. Focus on strategic guidance, context, and follow-up questions instead.\n"
        
        return prompt
    
    def filter_opportunities_by_interests(self, events: List[dict], interests: List[str]) -> List[dict]:
        """Filter events by user interests with intelligent matching"""
        if not interests or not events:
            return events[:5]  # Return top 5 if no interests specified
        
        # Map interests to project types and related keywords
        interest_mapping = {
            'housing': ['housing', 'development', 'zoning', 'affordable', 'apartment', 'residential', 'tenant', 'rent', 'home', 'dwelling', 'construction', 'building'],
            'transportation': ['transportation', 'transit', 'traffic', 'parking', 'bike', 'bicycle', 'pedestrian', 'road', 'street', 'mobility', 'vehicle', 'bus', 'train', 'commute'],
            'environment': ['environment', 'climate', 'sustainability', 'park', 'tree', 'green', 'pollution', 'conservation', 'energy', 'solar', 'waste', 'recycling', 'water'],
            'budget': ['budget', 'finance', 'tax', 'spending', 'revenue', 'fiscal', 'cost', 'funding', 'grant', 'fee', 'expense', 'appropriation'],
            'safety': ['safety', 'police', 'fire', 'emergency', 'crime', 'security', 'public safety', 'enforcement', 'prevention', 'hazard', 'protection'],
            'general': []  # General matches everything
        }
        
        filtered = []
        unmatched = []
        
        for opp in events:
            # Check if opportunity matches any user interests
            matched = False
            opp_text = f"{opp.get('title', '')} {opp.get('description', '')} {opp.get('project_type', '')}".lower()
            
            for interest in interests:
                interest_lower = interest.lower()
                if interest_lower == 'general':
                    matched = True
                    break
                
                # Check direct interest keywords
                keywords = interest_mapping.get(interest_lower, [interest_lower])
                if any(keyword in opp_text for keyword in keywords):
                    matched = True
                    break
            
            if matched:
                filtered.append(opp)
            else:
                unmatched.append(opp)
        
        # If we have fewer than 3 matches, add some unmatched ones for context
        if len(filtered) < 3:
            to_add = min(3 - len(filtered), len(unmatched))
            filtered.extend(unmatched[:to_add])
        
        return filtered[:5]  # Return top 5 relevant events
    
    def get_data_freshness(self) -> Optional[dict]:
        """Check age of schema data and return freshness info"""
        try:
            schema_dir = Path('data/events')
            if not schema_dir.exists():
                return None
            
            latest_file = max(schema_dir.glob('*.json'), key=os.path.getmtime, default=None)
            if not latest_file:
                return None
                
            file_age_days = (datetime.now() - datetime.fromtimestamp(
                latest_file.stat().st_mtime)).days
            
            return {
                "age_days": file_age_days,
                "is_stale": file_age_days > 7,
                "last_updated": datetime.fromtimestamp(latest_file.stat().st_mtime).isoformat(),
                "filename": latest_file.name
            }
        except Exception as e:
            print(f"[civic_api] Error checking data freshness: {e}")
            return None

    def get_civic_context(self, city: str) -> List[dict]:
        """Load civic events for context"""
        try:
            schema_dir = Path('data/events')
            if not schema_dir.exists():
                return []
            
            json_files = sorted(schema_dir.glob('newsletter_*.json'), 
                              key=os.path.getmtime, reverse=True)
            if not json_files:
                return []
            
            with open(json_files[0], 'r') as f:
                data = json.load(f)
            
            events = []
            for opp in data.get('events', []):
                events.append({
                    'title': opp.get('title', ''),
                    'description': opp.get('description', ''),
                    'meeting_date': opp.get('when', ''),
                    'impact': opp.get('impact_summary', ''),
                    'project_type': opp.get('project_type', ''),
                    'contact_info': opp.get('contact_info', {}),
                    'engagement_tier': opp.get('engagement_tier', ''),
                    'deadline': opp.get('deadline', ''),
                    'source_url': opp.get('source_url', ''),
                    'when': opp.get('when', ''),
                    'engagement_info': opp.get('engagement_info', ''),
                    'location': opp.get('location', '')
                })
            
            return events[:5]  # Return top 5 for context
            
        except Exception as e:
            print(f"[civic_api] Error loading context: {str(e)}")
            return []
    
    def calculate_relevance_score(self, opp_title: str, ai_response: str) -> float:
        """Calculate word overlap percentage between opportunity and response"""
        title_words = set(word.lower() for word in opp_title.split() if len(word) > 2)  # Ignore short words
        response_words = set(word.lower() for word in ai_response.split() if len(word) > 2)
        
        if not title_words:
            return 0.0
        
        overlap = title_words.intersection(response_words)
        return len(overlap) / len(title_words)

    def extract_action_buttons(self, ai_response: str, city: str, interests: List[str]) -> dict:
        """Extract grouped actionable buttons from AI response based on mentioned events"""
        grouped_actions = []
        
        # Configuration constants
        MAX_OPPORTUNITIES = 10  # Max number of events to show buttons for
        MAX_BUTTONS_PER_OPP = 4  # Email, Calendar, Link, Learn More
        ACTION_LABEL_MAX_LENGTH = 30
        RELEVANCE_THRESHOLD = 0.3  # 30% word overlap minimum
        DEFAULT_CITY_CLERK_EMAIL = os.getenv('DEFAULT_CLERK_EMAIL', 'city.clerk@cityofsanrafael.org')
        
        # Load current events to find matches
        events = self.get_civic_context(city)
        filtered_opps = self.filter_opportunities_by_interests(events, interests)
        
        # Find events mentioned in response using improved algorithm
        response_lower = ai_response.lower()
        relevant_opps = []
        
        for opp in filtered_opps:
            title = opp.get('title', '')
            if title:
                score = self.calculate_relevance_score(title, ai_response)
                if score > RELEVANCE_THRESHOLD:
                    relevant_opps.append((score, opp))
        
        # Sort by relevance and take top events
        relevant_opps.sort(key=lambda x: x[0], reverse=True)

        for score, opp in relevant_opps[:MAX_OPPORTUNITIES]:  # Process top relevant events
            opp_actions = []
            opp_id = opp.get('id', '')
            opp_title = opp.get('title', 'Civic Event')
            
            # Extract contact info for email action
            contact_info = opp.get('contact_info', {})
            email = contact_info.get('email', DEFAULT_CITY_CLERK_EMAIL)
            
            if email:
                # Create email action with icon
                subject = f"Public Comment: {opp_title}"
                opp_actions.append({
                    'type': 'email',
                    'label': 'Draft Email',
                    'icon': '📧',
                    'mailto': email,
                    'subject': subject,
                    'body': f"Dear {city} Officials,\n\nI am writing to comment on: {opp_title}.\n\n[Your comment here]\n\nThank you,\n[Your name]"
                })
            
            # Extract source URL for use in calendar and link actions
            source_url = opp.get('source_url', '')
            
            # Extract meeting date for calendar action with better validation
            meeting_date = opp.get('when', '')
            if meeting_date and 'T' in meeting_date:  # Check if ISO format date
                try:
                    # Validate the date format
                    from datetime import datetime
                    datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
                    
                    # Calculate end time (2 hours after start)
                    start_dt = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
                    end_dt = start_dt + timedelta(hours=2)
                    
                    # Get comprehensive location details
                    venue_name = opp.get('location', f'{city} City Hall')
                    venue_address = self.get_venue_full_address(venue_name, city)
                    
                    # Build comprehensive description with all participation details
                    description_parts = []
                    if opp.get('description'):
                        description_parts.append(f"Agenda Item: {opp.get('description')}")
                    
                    if opp.get('impact_summary'):
                        description_parts.append(f"Impact: {opp.get('impact_summary')}")
                    
                    # Add participation methods
                    engagement_info = opp.get('engagement_info', '')
                    if engagement_info:
                        description_parts.append(f"How to Participate:\n{engagement_info}")
                    else:
                        # Fallback participation info
                        description_parts.append(f"""How to Participate:
- In Person: {venue_address}
- Email Comments: {email if 'email' in locals() else 'city.clerk@' + city.lower().replace(' ', '') + '.gov'}
- Public Comment: Arrive early to sign up for public comment period""")
                    
                    if source_url:
                        description_parts.append(f"Meeting Details: {source_url}")
                    
                    full_description = "\n\n".join(description_parts)
                    
                    opp_actions.append({
                        'type': 'calendar',
                        'label': 'Add to Calendar',
                        'icon': '📅',
                        'event': {
                            'id': opp_id or f"civic-{hash(opp_title)}",
                            'title': f"{opp_title} - {self.get_meeting_type_from_url(source_url)} Meeting",
                            'start': meeting_date,
                            'end': end_dt.isoformat(),
                            'location': venue_address,
                            'description': full_description,
                            'url': source_url if source_url else None
                        }
                    })
                except ValueError:
                    # Skip invalid dates
                    print(f"[civic_api] Warning: Invalid date format in opportunity: {meeting_date}")
                    continue
            
            # Note: View Details button removed as unnecessary - users can access meeting details through consolidated meeting links
            
            # Add exactly one "Ask Questions" action for deeper engagement
            opp_actions.append({
                'type': 'learn_more',
                'label': 'Ask Questions',
                'icon': '💡',
                'opportunity_id': opp_id or f"civic-{hash(opp_title)}",
                'opportunity_title': opp_title,
                'context': self.generateFollowUpPrompt(opp_title, opp)
            })
            
            # Add this opportunity's grouped actions with additional metadata for frontend
            if opp_actions:
                grouped_actions.append({
                    'opportunity_title': opp_title,
                    'opportunity_id': opp_id or f"civic-{hash(opp_title)}",
                    'opportunity_description': opp.get('description', ''),
                    'opportunity_impact': opp.get('impact_summary', ''),
                    'source_url': source_url,  # Add source_url for agenda links
                    'actions': opp_actions
                })
        
        # Return grouped actions structure
        return {
            'grouped_actions': grouped_actions,
            'legacy_actions': self._convert_to_legacy_format(grouped_actions)  # For backward compatibility
        }
    
    def get_venue_full_address(self, venue_name: str, city: str) -> str:
        """Get full address for common civic venues"""
        venue_addresses = {
            'city hall': f"City Hall, {city}, CA",
            'community center': f"Community Center, {city}, CA", 
            'council chambers': f"Council Chambers, City Hall, {city}, CA",
            'planning department': f"Planning Department, City Hall, {city}, CA"
        }
        
        # Check for exact match first
        venue_lower = venue_name.lower()
        for key, address in venue_addresses.items():
            if key in venue_lower:
                return address
        
        # Default format for any venue
        if venue_name and venue_name != f'{city} City Hall':
            return f"{venue_name}, {city}, CA"
        else:
            return f"City Hall, {city}, CA"
    
    def get_meeting_type_from_url(self, url: str) -> str:
        """Extract meeting type from URL for better calendar titles"""
        if not url:
            return "City"
            
        url_lower = url.lower()
        if 'planning-commission' in url_lower or 'planning' in url_lower:
            return "Planning Commission"
        elif 'city-council' in url_lower or 'council' in url_lower:
            return "City Council"
        elif 'school-board' in url_lower or 'school' in url_lower:
            return "School Board"
        elif 'zoning' in url_lower:
            return "Zoning Board"
        elif 'parks' in url_lower:
            return "Parks Commission"
        else:
            return "City"
    
    def generateFollowUpPrompt(self, opp_title: str, opp_data: dict) -> str:
        """Generate contextual follow-up prompt for Learn More button"""
        # Create a specific follow-up question based on the opportunity type
        title_lower = opp_title.lower()
        
        if 'housing' in title_lower or 'building' in title_lower or 'development' in title_lower:
            return f"What are the specific housing impacts and timeline for '{opp_title}'? How can residents get involved?"
        elif 'budget' in title_lower or 'tax' in title_lower or 'finance' in title_lower:
            return f"How will '{opp_title}' affect residents financially? What are the key budget details?"
        elif 'traffic' in title_lower or 'transportation' in title_lower or 'parking' in title_lower:
            return f"What are the traffic and transportation impacts of '{opp_title}'? How can I provide input?"
        elif 'environment' in title_lower or 'climate' in title_lower or 'green' in title_lower:
            return f"What are the environmental benefits and concerns regarding '{opp_title}'?"
        else:
            return f"Can you explain the community impact and participation options for '{opp_title}'?"
    
    def _convert_to_legacy_format(self, grouped_actions: List[dict]) -> List[dict]:
        """Convert grouped actions to legacy flat format for backward compatibility"""
        flat_actions = []
        for group in grouped_actions[:1]:  # Take first group for legacy format
            for action in group.get('actions', [])[:3]:  # Max 3 actions
                flat_actions.append(action)
        return flat_actions
    
    def generate_fallback_response(self, message: str, city: str) -> str:
        """Generate fallback response when AI is not available"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['hello', 'hi', 'hey']):
            return f"Hello! I'm here to help you engage with {city} local government. What would you like to know about civic participation?"
        
        elif any(word in message_lower for word in ['meeting', 'when', 'schedule']):
            return f"City meetings in {city} are typically held monthly. You can find the full schedule on the city website. Would you like to know about specific upcoming events?"
        
        elif any(word in message_lower for word in ['participate', 'involved', 'help']):
            return f"There are many ways to participate in {city} government: attend meetings, submit public comments, join committees, or contact your representatives. What interests you most?"
        
        elif any(word in message_lower for word in ['housing', 'development', 'planning']):
            return f"Housing and development are important topics in {city}. The Planning Commission meets monthly to review projects. Would you like to know about current proposals?"
        
        else:
            return f"I can help you learn about {city} government and how to participate. Try asking about meetings, how to get involved, or specific topics like housing or transportation."

    def serve_legistar_events(self, city: str):
        """Serve Legistar API events for a specific city"""
        try:
            # Validate city parameter
            if not city or not city.replace('-', '').isalpha():
                self.send_json({
                    'error': 'Invalid city parameter',
                    'available_cities': ['oakland', 'santa-rosa', 'sonoma-county']
                }, status=400)
                return

            # Create and test Legistar client
            client = create_legistar_client(city)
            if not client:
                self.send_json({
                    'error': f'No Legistar client available for {city}',
                    'available_cities': ['oakland', 'santa-rosa', 'sonoma-county']
                }, status=404)
                return

            # Probe client capabilities
            capabilities = client.probe_capabilities()
            if not capabilities.get('api_accessible'):
                self.send_json({
                    'error': f'Legistar API not accessible for {city}',
                    'city': city,
                    'capabilities': capabilities
                }, status=503)
                return

            # Get recent events (last 7 days + next 30 days)
            events = client.get_recent_events(days_back=7, days_forward=30)

            # Transform events to civic events format
            civic_opportunities = []
            for event in events:
                opportunity = {
                    'opportunity_id': f"legistar_{city}_{event.get('event_id', 'unknown')}",
                    'title': f"{event.get('title', 'Unknown Meeting')} - {city.replace('-', ' ').title()}",
                    'date': event.get('date', ''),
                    'location': event.get('location', 'See agenda for details'),
                    'meeting_type': event.get('meeting_type', 'Meeting'),
                    'body_name': event.get('body_name', ''),
                    'engagement_info': {
                        'how_to_participate': 'Public comment typically allowed - check agenda',
                        'registration_required': False,
                        'contact_info': f'Contact {city.replace("-", " ").title()} clerk for details'
                    },
                    'urls': {
                        'agenda': event.get('agenda_url', ''),
                        'video': event.get('video_url', ''),
                        'minutes': event.get('minutes_url', '')
                    },
                    'source': 'legistar_api',
                    'municipality': city.replace('-', ' ').title(),
                    'data_updated': datetime.now().isoformat()
                }

                # Only include events with meaningful content
                if opportunity['title'] and opportunity['date']:
                    civic_opportunities.append(opportunity)

            response_data = {
                'city': city,
                'total_events': len(civic_opportunities),
                'events': civic_opportunities,
                'api_capabilities': capabilities,
                'data_source': 'legistar_api',
                'last_updated': datetime.now().isoformat()
            }

            self.send_json(response_data)

        except Exception as e:
            print(f"❌ Legistar API error for {city}: {str(e)}")
            self.send_json({
                'error': f'Internal server error getting {city} events',
                'details': str(e)[:200] if str(e) else 'Unknown error'
            }, status=500)

    def serve_onboarding_cards(self):
        """
        Generate Values Explorer cards for onboarding (PUBLIC ENDPOINT)

        Privacy-first design:
        - No authentication required
        - No user tracking
        - No storage of swipe decisions
        - Generic topic-based cards for all users

        Cards help users discover their civic archetypes, which are
        stored CLIENT-SIDE ONLY in browser localStorage.

        See: docs/PRIVACY_ARCHITECTURE.md (Tier 1: Browser-Only Privacy)
        """
        try:
            # Generate topic-based cards (always available, no user-specific data)
            topic_cards = [
                {
                    'id': 'topic-housing',
                    'type': 'topic',
                    'title': 'Housing & Development',
                    'description': 'Affordable housing, zoning changes, new construction projects',
                    'image': '/images/topics/housing.jpg',
                    'metadata': {
                        'topic': 'housing',
                        'project_type': 'housing'
                    }
                },
                {
                    'id': 'topic-transportation',
                    'type': 'topic',
                    'title': 'Transportation & Transit',
                    'description': 'Public transit, bike lanes, traffic improvements, parking',
                    'image': '/images/topics/transportation.jpg',
                    'metadata': {
                        'topic': 'transportation',
                        'project_type': 'transportation'
                    }
                },
                {
                    'id': 'topic-environment',
                    'type': 'topic',
                    'title': 'Environment & Climate',
                    'description': 'Climate action, sustainability, green infrastructure, parks',
                    'image': '/images/topics/environment.jpg',
                    'metadata': {
                        'topic': 'environment',
                        'project_type': 'environment'
                    }
                },
                {
                    'id': 'topic-budget',
                    'type': 'topic',
                    'title': 'Budget & Finance',
                    'description': 'City budget, taxes, government spending, financial oversight',
                    'image': '/images/topics/budget.jpg',
                    'metadata': {
                        'topic': 'budget',
                        'project_type': 'budget'
                    }
                },
                {
                    'id': 'topic-education',
                    'type': 'topic',
                    'title': 'Education & Schools',
                    'description': 'Schools, libraries, youth programs, educational facilities',
                    'image': '/images/topics/education.jpg',
                    'metadata': {
                        'topic': 'education',
                        'project_type': 'education'
                    }
                },
                {
                    'id': 'topic-public-safety',
                    'type': 'topic',
                    'title': 'Public Safety',
                    'description': 'Police, fire, emergency services, crime prevention',
                    'image': '/images/topics/public_safety.jpg',
                    'metadata': {
                        'topic': 'public_safety',
                        'project_type': 'public_safety'
                    }
                },
                {
                    'id': 'topic-community',
                    'type': 'topic',
                    'title': 'Community & Culture',
                    'description': 'Arts, culture, community centers, public spaces, events',
                    'image': '/images/topics/community.jpg',
                    'metadata': {
                        'topic': 'community',
                        'project_type': 'community'
                    }
                },
                {
                    'id': 'topic-development',
                    'type': 'topic',
                    'title': 'Economic Development',
                    'description': 'Business development, downtown revitalization, local economy',
                    'image': '/images/topics/development.jpg',
                    'metadata': {
                        'topic': 'development',
                        'project_type': 'development'
                    }
                },
                {
                    'id': 'topic-governance',
                    'type': 'topic',
                    'title': 'Government & Accountability',
                    'description': 'Transparency, ethics, government operations, public records',
                    'image': '/images/topics/governance.jpg',
                    'metadata': {
                        'topic': 'governance',
                        'project_type': 'governance'
                    }
                },
                {
                    'id': 'topic-elections',
                    'type': 'topic',
                    'title': 'Elections & Voting',
                    'description': 'Voting rights, election integrity, campaign finance',
                    'image': '/images/topics/elections.jpg',
                    'metadata': {
                        'topic': 'elections',
                        'project_type': 'elections'
                    }
                }
            ]

            # Return cards in randomized order for variety
            import random
            cards = topic_cards.copy()
            random.shuffle(cards)

            response = {
                'cards': cards,
                'total': len(cards),
                'privacy_notice': 'Your swipe decisions are NEVER sent to our servers. They stay in your browser only.',
                'generated_at': datetime.now().isoformat()
            }

            self.send_json(response)

        except Exception as e:
            print(f"[onboarding/cards] Error generating cards: {e}")
            import traceback
            traceback.print_exc()
            self.send_json({
                'error': 'Failed to generate onboarding cards',
                'details': str(e)
            }, status=500)

    def serve_status(self):
        """Serve API status and health check with comprehensive system checks"""
        checks = {}
        overall_healthy = True

        # 1. Database connectivity check
        db_check = self._check_database_health()
        checks['database'] = db_check
        if db_check['status'] != 'healthy':
            overall_healthy = False

        # 2. ChromaDB availability check
        chromadb_check = self._check_chromadb_health()
        checks['chromadb'] = chromadb_check
        if chromadb_check['status'] != 'healthy':
            overall_healthy = False

        # 3. External services check (non-blocking, degraded ok)
        services_check = self._check_external_services()
        checks['services'] = services_check
        # External services being unavailable = degraded, not unhealthy

        # 4. Data availability check
        schema_dir = Path('data/events')
        schema_files = list(schema_dir.glob('newsletter_*.json')) if schema_dir.exists() else []
        digest_available = (Path(__file__).parent / 'civic_digest.py').exists()

        checks['data'] = {
            'status': 'healthy' if schema_files else 'degraded',
            'schema_files_available': len(schema_files),
            'latest_data': schema_files[-1].name if schema_files else None,
            'last_updated': datetime.fromtimestamp(schema_files[-1].stat().st_mtime).isoformat() if schema_files else None,
            'civic_digest_available': digest_available,
            'pipeline_ready': digest_available and len(schema_files) > 0
        }

        # 5. Error rate check (Session 294)
        error_metrics_check = self._check_error_rate()
        checks['error_rate'] = error_metrics_check
        # Elevated error rate = degraded status
        if error_metrics_check.get('status') == 'critical':
            overall_healthy = False

        # 6. Request metrics check (Session 296)
        request_metrics_check = self._check_request_metrics()
        checks['request_metrics'] = request_metrics_check

        # 7. Active users check (Session 297)
        active_users_check = self._check_active_users()
        checks['active_users'] = active_users_check

        # Determine overall status
        if not overall_healthy:
            overall_status = 'unhealthy'
        elif (services_check.get('legistar') == 'unavailable' or
              checks['data']['status'] == 'degraded' or
              error_metrics_check.get('status') == 'elevated'):
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'

        status = {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'version': '0.4.0',
            'checks': checks
        }

        # Add extended info for /api/status endpoint
        if self.path == '/api/status':
            status['endpoints'] = {
                'public': ['/api/status', '/health'],
                'authenticated': [
                    '/api/events (GET - list all)',
                    '/api/events/{id} (GET - single opportunity)',
                    '/api/jurisdictions (GET - list all jurisdictions with counts)',
                    '/api/issues?user_id={user} (GET - user issues)',
                    '/api/refresh (GET - refresh data)',
                    '/api/conversation (POST - AI conversation)',
                    '/api/legistar/{city}/events (GET - Legistar API events)',
                    'Available cities: oakland, santa-rosa, sonoma-county'
                ]
            }
            status['authentication'] = 'Bearer token required for protected endpoints'

        # Add sample API key for testing (development only)
        if self.path == '/health' and config.env == 'development':
            status['test_credentials'] = {
                'sample_header': 'Authorization: Bearer <your_api_key>',
                'note': 'See INTEGRATION_GUIDE.md for API key setup'
            }

        self.send_json(status)

    # Class-level cache for source inventory (avoid repeated scraping)
    _source_inventory_cache: Dict[str, Any] = {}
    _source_inventory_cache_ttl = 3600  # 1 hour

    def serve_admin_status(self):
        """SESSION 299: Serve admin pipeline health status with detailed database and collection stats.

        GET /admin/status returns comprehensive JSON including:
        - Database table row counts and timestamps (meetings, issues, agenda_items, initiatives)
        - ChromaDB collection document counts
        - Source availability counts (optional, cached)
        - Overall pipeline health

        Query params:
        - jurisdiction: Jurisdiction ID (default: san-rafael)
        - include_sources: Include source inventory counts (default: false, slower)
        - refresh_sources: Force refresh of source inventory cache (default: false)
        """
        from urllib.parse import parse_qs, urlparse
        import sqlite3

        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        jurisdiction_id = params.get('jurisdiction', ['san-rafael'])[0]
        include_sources = params.get('include_sources', ['false'])[0].lower() == 'true'
        refresh_sources = params.get('refresh_sources', ['false'])[0].lower() == 'true'

        result = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'jurisdiction': jurisdiction_id,
            'database': {},
            'chromadb': {},
            'files': {},
            'sources': None  # Populated if include_sources=true
        }

        # 1. State database stats (meetings, agenda_items, issues, initiatives)
        state_db_path = get_user_path('civic_state.db')
        if os.path.exists(state_db_path):
            try:
                conn = sqlite3.connect(state_db_path, timeout=5)
                cursor = conn.cursor()

                # Meetings
                try:
                    cursor.execute("""
                        SELECT COUNT(*), MIN(meeting_datetime), MAX(meeting_datetime), MAX(updated_at)
                        FROM meetings
                        WHERE jurisdiction_id = ? AND valid_to IS NULL
                    """, (jurisdiction_id,))
                    row = cursor.fetchone()
                    result['database']['meetings'] = {
                        'count': row[0] or 0,
                        'earliest': row[1],
                        'latest': row[2],
                        'last_updated': row[3]
                    }
                except sqlite3.OperationalError:
                    result['database']['meetings'] = {'count': 0, 'error': 'table_missing'}

                # Agenda items
                try:
                    cursor.execute("""
                        SELECT COUNT(*), MAX(enriched_at)
                        FROM agenda_items
                        WHERE valid_to IS NULL
                          AND meeting_id IN (
                              SELECT id FROM meetings
                              WHERE jurisdiction_id = ? AND valid_to IS NULL
                          )
                    """, (jurisdiction_id,))
                    row = cursor.fetchone()
                    result['database']['agenda_items'] = {
                        'count': row[0] or 0,
                        'last_enriched': row[1]
                    }
                except sqlite3.OperationalError:
                    result['database']['agenda_items'] = {'count': 0, 'error': 'table_missing'}

                # Issues
                try:
                    cursor.execute("""
                        SELECT COUNT(*), MAX(updated_at)
                        FROM issues
                        WHERE jurisdiction_id = ?
                    """, (jurisdiction_id,))
                    row = cursor.fetchone()
                    result['database']['issues'] = {
                        'count': row[0] or 0,
                        'last_updated': row[1]
                    }

                    # By status breakdown
                    cursor.execute("""
                        SELECT status, COUNT(*)
                        FROM issues
                        WHERE jurisdiction_id = ?
                        GROUP BY status
                    """, (jurisdiction_id,))
                    result['database']['issues']['by_status'] = {
                        r[0]: r[1] for r in cursor.fetchall()
                    }
                except sqlite3.OperationalError:
                    result['database']['issues'] = {'count': 0, 'error': 'table_missing'}

                # Initiatives
                try:
                    cursor.execute("""
                        SELECT COUNT(*), MAX(updated_at)
                        FROM initiatives
                        WHERE jurisdiction_id = ?
                    """, (jurisdiction_id,))
                    row = cursor.fetchone()
                    result['database']['initiatives'] = {
                        'count': row[0] or 0,
                        'last_updated': row[1]
                    }
                except sqlite3.OperationalError:
                    result['database']['initiatives'] = {'count': 0, 'error': 'table_missing'}

                conn.close()
                result['database']['status'] = 'connected'
                result['database']['path'] = str(state_db_path)
                result['database']['size_bytes'] = os.path.getsize(state_db_path)
            except Exception as e:
                result['database']['status'] = 'error'
                result['database']['error'] = str(e)
                result['status'] = 'degraded'
        else:
            result['database']['status'] = 'missing'
            result['database']['path'] = str(state_db_path)
            result['status'] = 'degraded'

        # 2. ChromaDB collection stats
        vectors_dir = Path(get_user_path('')) / 'pilot' / 'vectors'
        persist_dir = vectors_dir / jurisdiction_id

        if persist_dir.exists():
            result['chromadb']['path'] = str(persist_dir)
            chroma_db = persist_dir / 'chroma.sqlite3'
            if chroma_db.exists():
                result['chromadb']['size_bytes'] = chroma_db.stat().st_size

            try:
                import chromadb
                from chromadb.config import Settings

                client = chromadb.PersistentClient(
                    path=str(persist_dir),
                    settings=Settings(anonymized_telemetry=False)
                )

                # Expected collections
                collection_names = [
                    f'{jurisdiction_id}_decisions',
                    f'{jurisdiction_id}_chunks',
                    f'{jurisdiction_id}_transcripts',
                    f'{jurisdiction_id}_issues',
                    f'{jurisdiction_id}_municipal_code',
                ]

                result['chromadb']['collections'] = {}
                total_docs = 0

                for name in collection_names:
                    corpus_type = name.replace(f'{jurisdiction_id}_', '')
                    try:
                        collection = client.get_collection(name)
                        count = collection.count()
                        metadata = collection.metadata or {}
                        result['chromadb']['collections'][corpus_type] = {
                            'name': name,
                            'count': count,
                            'created_at': metadata.get('created_at'),
                            'metadata': metadata
                        }
                        total_docs += count
                    except Exception:
                        result['chromadb']['collections'][corpus_type] = None

                result['chromadb']['total_documents'] = total_docs
                result['chromadb']['status'] = 'connected'
            except ImportError:
                result['chromadb']['status'] = 'chromadb_not_installed'
            except Exception as e:
                result['chromadb']['status'] = 'error'
                result['chromadb']['error'] = str(e)
        else:
            result['chromadb']['status'] = 'no_storage'
            result['chromadb']['path'] = str(persist_dir)

        # 3. File stats
        participation_db_path = get_user_path('civic_participation.db')
        if os.path.exists(participation_db_path):
            result['files']['participation_db_size_bytes'] = os.path.getsize(participation_db_path)

        if os.path.exists(state_db_path):
            result['files']['state_db_size_bytes'] = os.path.getsize(state_db_path)

        # 4. Source inventory (optional - requires scraping)
        if include_sources:
            cache_key = f"source_inventory_{jurisdiction_id}"
            cached = AuthenticatedCivicAPIHandler._source_inventory_cache.get(cache_key)

            # Check if cache is valid
            if cached and not refresh_sources:
                cache_time = cached.get('_cached_at', 0)
                if time.time() - cache_time < AuthenticatedCivicAPIHandler._source_inventory_cache_ttl:
                    result['sources'] = cached
                    result['sources']['_from_cache'] = True

            # Fetch fresh if not cached or expired
            if result['sources'] is None:
                try:
                    from civic_extraction.clients.proudcity import create_san_rafael_client

                    # Currently only ProudCity for San Rafael
                    if jurisdiction_id in ['san-rafael', 'city-san-rafael']:
                        client = create_san_rafael_client()
                        inventory = client.get_source_inventory(include_coverage=True)

                        meetings_data = {
                            'platform': 'proudcity',
                            'available': inventory['total'],
                            'by_type': inventory['by_type'],
                            'last_checked': inventory['timestamp']
                        }

                        # Include coverage data if available (SESSION 305)
                        if 'coverage' in inventory:
                            coverage = inventory['coverage']
                            meetings_data['configured_count'] = coverage['configured_count']
                            meetings_data['discovered_count'] = coverage['discovered_count']
                            meetings_data['missing'] = coverage['missing']
                            meetings_data['coverage_percent'] = coverage['coverage_percent']

                        result['sources'] = {
                            'meetings': meetings_data,
                            '_cached_at': time.time(),
                            '_from_cache': False
                        }

                        # Cache it
                        AuthenticatedCivicAPIHandler._source_inventory_cache[cache_key] = result['sources']
                    else:
                        result['sources'] = {
                            'meetings': {
                                'platform': 'unknown',
                                'available': None,
                                'error': f'No source client configured for {jurisdiction_id}'
                            }
                        }
                except ImportError as e:
                    result['sources'] = {'error': f'Source client not available: {str(e)}'}
                except Exception as e:
                    logger.error(f"Source inventory error: {e}", exc_info=True)
                    result['sources'] = {'error': str(e)}

        # 5. Determine overall status
        if result['database'].get('status') == 'error' or result['chromadb'].get('status') == 'error':
            result['status'] = 'unhealthy'
        elif result['database'].get('status') == 'missing' or result['chromadb'].get('status') == 'no_storage':
            result['status'] = 'degraded'

        self.send_json(result)

    def handle_admin_trigger(self):
        """SESSION 302: Handle admin manual trigger operations.

        POST /api/admin/trigger
        Body: { "operation": "fetch_meetings", "jurisdiction": "san-rafael" }

        Supported operations:
        - fetch_meetings: Trigger ProudCity scraper to fetch new meetings
        - discover_videos: Scan meetings for YouTube video URLs (SESSION 303)
        """
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}

            operation = data.get('operation')
            jurisdiction = data.get('jurisdiction', 'san-rafael')

            if not operation:
                self.send_json({
                    'status': 'error',
                    'error': 'Missing required field: operation'
                }, status=400)
                return

            if operation == 'fetch_meetings':
                result = self._trigger_fetch_meetings(jurisdiction)
                self.send_json(result)
            elif operation == 'discover_videos':
                result = self._trigger_discover_videos(jurisdiction)
                self.send_json(result)
            else:
                self.send_json({
                    'status': 'error',
                    'error': f'Unknown operation: {operation}',
                    'supported_operations': ['fetch_meetings', 'discover_videos']
                }, status=400)

        except json.JSONDecodeError as e:
            self.send_json({
                'status': 'error',
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
        except Exception as e:
            logger.error(f"Admin trigger error: {e}", exc_info=True)
            self.send_json({
                'status': 'error',
                'error': str(e)
            }, status=500)

    def _trigger_fetch_meetings(self, jurisdiction: str) -> dict:
        """SESSION 302: Trigger ProudCity scraper to fetch meetings.

        Args:
            jurisdiction: Jurisdiction ID (e.g., 'san-rafael')

        Returns:
            Dict with operation result
        """
        from datetime import datetime
        start_time = time.time()

        result = {
            'status': 'success',
            'operation': 'fetch_meetings',
            'jurisdiction': jurisdiction,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        try:
            # Import scraper
            from civic_extraction.clients.proudcity import create_san_rafael_client

            # Create client and fetch events
            client = create_san_rafael_client()

            # Fetch meetings for next 90 days, past 30 days
            events = client.get_events(days_ahead=90, days_past=30)
            result['count_fetched'] = len(events)

            # Normalize to Meeting format
            meetings = []
            for event in events:
                meeting = client.normalize_event(event)
                if meeting:
                    meetings.append({
                        'id': meeting.id,
                        'title': meeting.title,
                        'meeting_datetime': meeting.meeting_datetime.isoformat() if meeting.meeting_datetime else None,
                        'meeting_type': meeting.meeting_type,
                        'status': meeting.status,
                        'location': meeting.location,
                        'virtual_url': meeting.virtual_url,
                        'agenda_url': meeting.agenda_url,
                        'minutes_url': meeting.minutes_url,
                        'video_url': meeting.video_url,
                        'source_platform': meeting.source_platform,
                        'source_url': meeting.source_url,
                    })

            result['count_normalized'] = len(meetings)

            if meetings:
                # Store to database using StateManager
                from ..storage.state_manager import StateManager

                state_db_path = get_user_path('civic_state.db')
                state_mgr = StateManager(str(state_db_path))

                # Map jurisdiction to jurisdiction_id format
                jurisdiction_id = f"city-{jurisdiction}" if not jurisdiction.startswith('city-') else jurisdiction

                # Get existing meeting count before update
                existing = state_mgr.query_meetings(jurisdiction_id=jurisdiction_id)
                existing_ids = {m.get('id') for m in existing}

                # Update meetings (this does temporal versioning)
                updated = state_mgr.update_meetings(jurisdiction_id, meetings)
                result['count_stored'] = updated

                # Calculate new meetings
                new_ids = {m['id'] for m in meetings}
                truly_new = new_ids - existing_ids
                result['count_new'] = len(truly_new)
            else:
                result['count_stored'] = 0
                result['count_new'] = 0

            result['duration_seconds'] = round(time.time() - start_time, 2)
            logger.info(f"Fetch meetings completed: {result}")

        except ImportError as e:
            result['status'] = 'error'
            result['error'] = f'Scraper module not available: {str(e)}'
            logger.error(f"Fetch meetings import error: {e}")
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logger.error(f"Fetch meetings error: {e}", exc_info=True)

        return result

    def _trigger_discover_videos(self, jurisdiction: str) -> dict:
        """SESSION 303: Discover YouTube videos from meeting records.

        Scans meetings in the database for video_url fields and extracts
        YouTube video IDs. Returns stats about discovered videos.

        Args:
            jurisdiction: Jurisdiction ID (e.g., 'san-rafael')

        Returns:
            Dict with operation result including video counts
        """
        import re
        from datetime import datetime
        start_time = time.time()

        result = {
            'status': 'success',
            'operation': 'discover_videos',
            'jurisdiction': jurisdiction,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        try:
            from ..storage.state_manager import StateManager

            state_db_path = get_user_path('civic_state.db')
            state_mgr = StateManager(str(state_db_path))

            # Map jurisdiction to jurisdiction_id format
            jurisdiction_id = f"city-{jurisdiction}" if not jurisdiction.startswith('city-') else jurisdiction

            # Query all current meetings for this jurisdiction
            meetings = state_mgr.query_meetings(jurisdiction_id=jurisdiction_id)
            result['count_meetings'] = len(meetings)

            # Find meetings with video URLs
            youtube_pattern = re.compile(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})')

            videos_discovered = []
            meetings_with_video = 0

            for meeting in meetings:
                video_url = meeting.get('video_url')
                if video_url:
                    meetings_with_video += 1
                    match = youtube_pattern.search(video_url)
                    if match:
                        video_id = match.group(1)
                        videos_discovered.append({
                            'video_id': video_id,
                            'meeting_id': meeting.get('id'),
                            'meeting_title': meeting.get('title'),
                            'meeting_date': meeting.get('meeting_datetime'),
                            'youtube_url': f'https://www.youtube.com/watch?v={video_id}'
                        })

            result['count_meetings_with_video'] = meetings_with_video
            result['count_videos_discovered'] = len(videos_discovered)

            # Include first 10 videos as sample
            result['videos_sample'] = videos_discovered[:10]

            result['duration_seconds'] = round(time.time() - start_time, 2)
            logger.info(f"Discover videos completed: {result['count_videos_discovered']} videos from {result['count_meetings_with_video']} meetings")

        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logger.error(f"Discover videos error: {e}", exc_info=True)

        return result

    def _check_database_health(self) -> dict:
        """Check SQLite database connectivity"""
        # Use config-based data directory (supports /app/data in production)
        db_path = get_user_path('civic_participation.db')
        result = {
            'status': 'healthy',
            'civic_participation_db': {'status': 'unknown'}
        }

        try:
            import sqlite3
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=5)
                cursor = conn.cursor()
                # Simple connectivity test
                cursor.execute("SELECT 1")
                cursor.fetchone()
                # Get table count as basic integrity check
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                conn.close()

                result['civic_participation_db'] = {
                    'status': 'connected',
                    'tables': table_count,
                    'path': db_path,
                    'size_bytes': os.path.getsize(db_path)
                }
            else:
                result['civic_participation_db'] = {
                    'status': 'missing',
                    'path': db_path
                }
                result['status'] = 'unhealthy'
        except Exception as e:
            result['civic_participation_db'] = {
                'status': 'error',
                'error': str(e)
            }
            result['status'] = 'unhealthy'

        return result

    def _check_chromadb_health(self) -> dict:
        """Check ChromaDB vector store availability for all cities"""
        result = {
            'status': 'healthy',
            'details': {
                'cities': {}
            }
        }

        # Use config-based data directory (supports /app/data in production)
        vectors_base = get_bundled_path('pilot', 'vectors')

        try:
            if not os.path.exists(vectors_base):
                result['status'] = 'degraded'
                result['details'] = {
                    'status': 'missing',
                    'path': vectors_base,
                    'cities': {}
                }
                return result

            # Scan for all city-* directories
            city_dirs = []
            for entry in os.listdir(vectors_base):
                if entry.startswith('city-') and os.path.isdir(os.path.join(vectors_base, entry)):
                    city_dirs.append(entry)

            if not city_dirs:
                result['status'] = 'degraded'
                result['details'] = {
                    'status': 'no_cities',
                    'path': vectors_base,
                    'cities': {}
                }
                return result

            # Check each city's vector store
            cities_healthy = 0
            for city_dir in sorted(city_dirs):
                city_name = city_dir.replace('city-', '')
                city_path = os.path.join(vectors_base, city_dir)
                chroma_db = os.path.join(city_path, 'chroma.sqlite3')

                if os.path.exists(chroma_db):
                    city_info = {
                        'status': 'available',
                        'size_bytes': os.path.getsize(chroma_db)
                    }
                    # Try to get collection count
                    try:
                        import chromadb
                        client = chromadb.PersistentClient(path=city_path)
                        collections = client.list_collections()
                        city_info['collections'] = len(collections)
                    except Exception:
                        city_info['collections'] = 'unknown'
                    cities_healthy += 1
                else:
                    city_info = {'status': 'no_storage'}

                result['details']['cities'][city_name] = city_info

            result['details']['total_cities'] = len(city_dirs)
            result['details']['healthy_cities'] = cities_healthy

            if cities_healthy == 0:
                result['status'] = 'degraded'
        except Exception as e:
            result['status'] = 'unhealthy'
            result['details'] = {
                'status': 'error',
                'error': str(e)
            }

        return result

    def _check_external_services(self) -> dict:
        """Check external service availability (non-blocking)"""
        result = {
            'openai': 'unavailable',
            'legistar': 'unknown'
        }

        # OpenAI check (just verify key exists, don't make API call)
        if OPENAI_AVAILABLE and os.getenv('OPENAI_API_KEY'):
            result['openai'] = 'configured'

        # Legistar check - just verify client is available
        # Don't make actual API call to avoid latency
        try:
            if legistar_client:
                result['legistar'] = 'available'
            else:
                result['legistar'] = 'unavailable'
        except Exception:
            result['legistar'] = 'unavailable'

        return result

    def _check_error_rate(self) -> dict:
        """Check error rate from recent requests (Session 294)"""
        result = {
            'status': 'healthy',
            'details': {
                'window_minutes': 5,
                'total_requests': 0,
                'error_count': 0,
                'error_rate_percent': 0.0
            }
        }

        try:
            alert_manager = get_error_alert_manager()
            if not alert_manager:
                result['details']['note'] = 'Error monitoring not available'
                return result

            metrics = alert_manager.get_error_metrics()

            result['details'] = {
                'window_minutes': metrics.get('window_minutes', 5),
                'total_requests': metrics.get('total_requests', 0),
                'error_count': metrics.get('error_count', 0),
                'client_error_count': metrics.get('client_error_count', 0),
                'error_rate_percent': metrics.get('error_rate_percent', 0.0),
                'top_error_endpoints': metrics.get('top_error_endpoints', [])
            }

            # Map metrics status to health check status
            metrics_status = metrics.get('status', 'normal')
            if metrics_status == 'critical':
                result['status'] = 'critical'
            elif metrics_status == 'elevated':
                result['status'] = 'elevated'
            else:
                result['status'] = 'healthy'

            # Also trigger alert check (will debounce if needed)
            alert_manager.check_and_alert()

        except Exception as e:
            result['status'] = 'unknown'
            result['details']['error'] = str(e)

        return result

    def _check_request_metrics(self) -> dict:
        """Check request metrics for volume monitoring (Session 296)"""
        result = {
            'status': 'healthy',
            'details': {
                'window_minutes': 5,
                'total_requests': 0,
                'requests_per_minute': 0.0
            }
        }

        try:
            metrics_manager = get_request_metrics_manager()
            if not metrics_manager:
                result['details']['note'] = 'Request metrics not available'
                return result

            metrics = metrics_manager.get_request_metrics()

            result['details'] = {
                'window_minutes': metrics.get('window_minutes', 5),
                'total_requests': metrics.get('total_requests', 0),
                'requests_per_minute': metrics.get('requests_per_minute', 0.0),
                'success_count': metrics.get('success_count', 0),
                'client_error_count': metrics.get('client_error_count', 0),
                'server_error_count': metrics.get('server_error_count', 0),
                'response_time_p50': metrics.get('response_time_p50'),
                'response_time_p95': metrics.get('response_time_p95'),
                'response_time_avg': metrics.get('response_time_avg'),
                'top_endpoints': metrics.get('top_endpoints', [])[:5]
            }

        except Exception as e:
            result['status'] = 'unknown'
            result['details']['error'] = str(e)

        return result

    def _check_active_users(self) -> dict:
        """Check active users metrics for usage monitoring (Session 297)"""
        result = {
            'status': 'healthy',
            'details': {
                'window_minutes': 5,
                'unique_users': 0,
                'daily_active_users': 0
            }
        }

        try:
            metrics_manager = get_active_users_manager()
            if not metrics_manager:
                result['details']['note'] = 'Active users metrics not available'
                return result

            metrics = metrics_manager.get_active_users()

            result['details'] = {
                'window_minutes': metrics.get('window_minutes', 5),
                'unique_users': metrics.get('unique_users', 0),
                'active_users_per_hour': metrics.get('active_users_per_hour', 0.0),
                'authenticated_users': metrics.get('authenticated_users', 0),
                'anonymous_users': metrics.get('anonymous_users', 0),
                'daily_active_users': metrics.get('daily_active_users', 0)
            }

        except Exception as e:
            result['status'] = 'unknown'
            result['details']['error'] = str(e)

        return result

    def handle_manual_refresh(self):
        """Handle user-triggered data refresh with LLM intent analysis"""
        try:
            # Parse request body for user query
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                request_data = json.loads(post_data.decode('utf-8'))
                user_query = request_data.get('query', '')
            else:
                user_query = ''

            # Analyze user intent to determine refresh scope
            if user_query:
                intent_analysis = get_data_freshness_manager().analyze_user_intent(user_query)

                # Determine refresh strategy based on temporal focus
                if intent_analysis['temporal_focus'] == 'future_only':
                    refresh_scope = 'future_meetings_only'
                elif intent_analysis['temporal_focus'] == 'recent_past':
                    refresh_scope = 'include_recent_past'
                else:
                    refresh_scope = 'current_active_only'
            else:
                refresh_scope = 'current_active_only'
                intent_analysis = {}

            # Trigger targeted background refresh
            self.trigger_background_refresh(scope=refresh_scope)

            response = {
                "success": True,
                "message": f"Refreshing {refresh_scope.replace('_', ' ')} data",
                "estimated_completion": "2-3 minutes",
                "intent_analysis": intent_analysis,
                "refresh_scope": refresh_scope,
                "status_endpoint": "/api/status",
                "user_message": "Data refresh initiated - please check back in a few minutes"
            }

            self.send_json(response)

        except json.JSONDecodeError:
            self.send_json({
                "success": False,
                "error": "Invalid JSON in request body",
                "user_message": "Please provide valid request data"
            }, 400)
        except Exception as e:
            print(f"[civic_api] Manual refresh error: {e}")
            self.send_json({
                "success": False,
                "error": str(e),
                "user_message": "Refresh failed - please try again or contact support"
            }, 500)

    def serve_agenda_status(self, event_id: str):
        """Get agenda integration status for an event"""
        if not AGENDA_INTEGRATION_AVAILABLE:
            self.send_json({
                "error": "Agenda integration not available",
                "message": "Agenda parsing system not installed"
            }, status_code=503)
            return

        try:
            # Find event in current data
            event = self._find_event_by_id(event_id)
            if not event:
                self.send_json({
                    "error": "Event not found",
                    "event_id": event_id
                }, status_code=404)
                return

            # Return agenda integration status
            agenda_status = {
                "event_id": event_id,
                "event_title": event.get('title', 'Unknown'),
                "agenda_available": event.get('agenda_available'),
                "agenda_url": event.get('agenda_url'),
                "agenda_expansion": event.get('agenda_expansion', {
                    "available": False,
                    "parsed": False,
                    "actionable_items": []
                }),
                "last_checked": event.get('created_at'),
                "actions": {
                    "discover_agenda": f"/api/agenda/{event_id}/discover",
                    "parse_agenda": f"/api/agenda/{event_id}/parse"
                }
            }

            self.send_json(agenda_status)

        except Exception as e:
            self.send_json({
                "error": "Failed to get agenda status",
                "details": str(e)
            }, status_code=500)

    def serve_agenda_discovery(self, event_id: str):
        """Discover agenda URL for an event using LLM analysis"""
        if not AGENDA_INTEGRATION_AVAILABLE:
            self.send_json({
                "error": "Agenda integration not available"
            }, status_code=503)
            return

        try:
            # Find event in current data
            event = self._find_event_by_id(event_id)
            if not event:
                self.send_json({
                    "error": "Event not found",
                    "event_id": event_id
                }, status_code=404)
                return

            # Initialize agenda integrator
            integrator = AgendaIntegrator()

            # Discover agenda URL
            agenda_url, agenda_available = integrator.discover_agenda_url(event)

            response = {
                "event_id": event_id,
                "discovery_result": {
                    "agenda_url": agenda_url,
                    "agenda_available": agenda_available,
                    "discovered_at": datetime.now().isoformat()
                },
                "next_steps": {
                    "parse_agenda": f"/api/agenda/{event_id}/parse" if agenda_available else None,
                    "view_event": f"/api/events/{event_id}"
                }
            }

            self.send_json(response)

        except Exception as e:
            self.send_json({
                "error": "Agenda discovery failed",
                "details": str(e)
            }, status_code=500)

    def serve_agenda_parsing(self, event_id: str):
        """Parse agenda content and extract actionable items"""
        if not AGENDA_INTEGRATION_AVAILABLE:
            self.send_json({
                "error": "Agenda integration not available"
            }, status_code=503)
            return

        try:
            # Find event in current data
            event = self._find_event_by_id(event_id)
            if not event:
                self.send_json({
                    "error": "Event not found",
                    "event_id": event_id
                }, status_code=404)
                return

            # Check if agenda URL is available
            agenda_url = event.get('agenda_url')
            if not agenda_url:
                self.send_json({
                    "error": "No agenda URL available",
                    "message": "Run agenda discovery first",
                    "discovery_endpoint": f"/api/agenda/{event_id}/discover"
                }, status_code=400)
                return

            # Initialize agenda integrator
            integrator = AgendaIntegrator()

            # Parse agenda content
            agenda_items = integrator.parse_agenda_content(agenda_url, event)

            # Build response with actionable items
            actionable_items = [
                {
                    'item_ref': item.item_ref,
                    'title': item.title,
                    'description': item.description,
                    'actionable': item.actionable,
                    'actionable_because': item.actionable_reason,
                    'participation_mechanisms': item.participation_mechanisms
                }
                for item in agenda_items if item.actionable
            ]

            response = {
                "event_id": event_id,
                "agenda_url": agenda_url,
                "parsing_result": {
                    "total_items_found": len(agenda_items),
                    "actionable_items_count": len(actionable_items),
                    "actionable_items": actionable_items,
                    "parsed_at": datetime.now().isoformat()
                },
                "next_steps": {
                    "view_enhanced_event": f"/api/events/{event_id}",
                    "get_agenda_status": f"/api/agenda/{event_id}"
                }
            }

            self.send_json(response)

        except Exception as e:
            self.send_json({
                "error": "Agenda parsing failed",
                "details": str(e)
            }, status_code=500)

    def generate_opportunity_id(self, item):
        """Generate consistent opportunity ID from item data"""
        title = item.get('title', 'untitled')
        # Create short hash from title for consistent IDs
        return f"opp_{hashlib.md5(title.encode()).hexdigest()[:8]}"
    
    def extract_participation_methods_from_schema(self, item):
        """Extract participation methods from schema-compliant item"""
        methods = []
        how = item.get('how_to_participate', '').lower()
        
        if 'email' in how or '@' in how:
            methods.append('email_comment')
        if 'online' in how or 'zoom' in how or 'virtual' in how:
            methods.append('virtual_attendance')
        if 'attend' in how or 'person' in how or 'meeting' in how:
            methods.append('in_person_attendance')
        if 'comment' in how:
            methods.append('public_comment')
        if 'write' in how or 'letter' in how:
            methods.append('written_comment')
        
        return methods if methods else ['public_comment']
    
    def extract_participation_methods_from_schema_engagement(self, engagement_info):
        """Extract participation methods from schema engagement_info field"""
        methods = []
        how = engagement_info.lower()
        
        if 'email' in how or '@' in how:
            methods.append('email_comment')
        if 'online' in how or 'zoom' in how or 'virtual' in how:
            methods.append('virtual_attendance')
        if 'attend' in how or 'person' in how or 'meeting' in how:
            methods.append('in_person_attendance')
        if 'comment' in how:
            methods.append('public_comment')
        if 'write' in how or 'letter' in how:
            methods.append('written_comment')
        
        return methods if methods else ['public_comment']
    
    def extract_deadline_from_participation(self, participation_text):
        """Extract deadline date from participation instructions"""
        import re
        # Look for common date patterns in participation text
        date_patterns = [
            r'by ([A-Za-z]+ \d{1,2})',
            r'before ([A-Za-z]+ \d{1,2})',
            r'deadline.*?(\d{1,2}/\d{1,2}/\d{2,4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, participation_text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def categorize_from_project_type(self, project_type):
        """Map schema project_type to API categories"""
        type_mapping = {
            'housing': 'housing',
            'development': 'housing',
            'transportation': 'transportation',
            'budget': 'budget',
            'environment': 'environment',
            'safety': 'public_safety',
            'planning': 'planning'
        }
        return type_mapping.get(project_type.lower(), 'general')

    def load_jurisdiction_override(self, jurisdiction_id, program_id):
        """
        Load jurisdiction-specific override data for federal programs.

        Example: FY2025 CDBG allocation for city-berkeley
        """
        if not jurisdiction_id:
            return None

        override_path = Path(f"data/jurisdiction_overrides/{jurisdiction_id}.json")

        if not override_path.exists():
            return None

        try:
            with open(override_path, 'r') as f:
                override_data = json.load(f)

            # Return program-specific override data if available
            federal_programs = override_data.get("federal_programs", {})
            return federal_programs.get(program_id)

        except Exception as e:
            logger.error(f"Failed to load jurisdiction override for {jurisdiction_id}: {e}")
            return None

    def hydrate_legislative_context(self, legislative_context, jurisdiction_id, project_type):
        """
        Resolve legislative context references to full details.
        Called when serving opportunity via API endpoint.
        """
        if not legislative_context or not LEGISLATIVE_ENRICHMENT_AVAILABLE:
            return legislative_context

        # Extract state from jurisdiction_id (e.g., "city-berkeley" -> "california")
        state = None
        if jurisdiction_id and jurisdiction_id.startswith(("city-", "county-")):
            state = "california"  # All current jurisdictions are in California

        if not state:
            return legislative_context

        # Lazy-load legislative context from cache
        leg_data = legislative_cache.get(state, project_type)

        if not leg_data:
            return legislative_context

        # Create hydrated context with full details
        hydrated = {**legislative_context}

        # Resolve state legislation references
        if "state_legislation_refs" in legislative_context:
            hydrated["state_legislation"] = []
            for ref in legislative_context["state_legislation_refs"]:
                if ref in leg_data.get("state_legislation", {}):
                    bill_data = leg_data["state_legislation"][ref]
                    hydrated["state_legislation"].append({
                        "id": ref,
                        "bill": bill_data.get("bill"),
                        "status": bill_data.get("status"),
                        "leverage_point": bill_data.get("leverage_point"),
                        "summary": bill_data.get("summary"),
                        "official_url": bill_data.get("official_url")
                    })

        # Resolve federal program references
        if "federal_program_refs" in legislative_context:
            hydrated["federal_programs"] = []
            for ref in legislative_context["federal_program_refs"]:
                if ref in leg_data.get("federal_programs", {}):
                    program_data = leg_data["federal_programs"][ref]
                    program = {
                        "id": ref,
                        "program_name": program_data.get("program_name"),
                        "administering_agency": program_data.get("administering_agency"),
                        "leverage_point": program_data.get("leverage_point"),
                        "description": program_data.get("description"),
                        "official_url": program_data.get("official_url"),
                        "keywords": program_data.get("keywords", [])
                    }

                    # Load jurisdiction-specific overrides (e.g., FY2025 CDBG allocation)
                    jurisdiction_override = self.load_jurisdiction_override(jurisdiction_id, ref)
                    if jurisdiction_override:
                        program.update(jurisdiction_override)

                    hydrated["federal_programs"].append(program)

        return hydrated
    
    def extract_tags_from_schema_item(self, item):
        """Extract relevant tags from schema-compliant item"""
        tags = []
        title = item.get('title', '').lower()
        project_type = item.get('project_type', '').lower()
        
        # Add project type as tag
        if project_type:
            tags.append(project_type)
            
        # Add common civic tags based on content
        if 'hearing' in title:
            tags.append('public_hearing')
        if 'comment' in title or 'comment' in item.get('how_to_participate', '').lower():
            tags.append('public_comment')
        if 'budget' in title:
            tags.append('budget')
        if 'plan' in title:
            tags.append('planning')
        if 'development' in title:
            tags.append('development')
        
        return list(set(tags))  # Remove duplicates
    
    def extract_tags_from_schema_opportunity(self, opportunity):
        """Extract relevant tags from schema opportunity"""
        tags = []
        title = opportunity.get('title', '').lower()
        project_type = opportunity.get('project_type', '').lower()
        
        # Add project type as tag
        if project_type:
            tags.append(project_type)
            
        # Add common civic tags based on content
        if 'hearing' in title:
            tags.append('public_hearing')
        if 'comment' in title or 'comment' in opportunity.get('engagement_info', '').lower():
            tags.append('public_comment')
        if 'budget' in title:
            tags.append('budget')
        if 'plan' in title:
            tags.append('planning')
        if 'development' in title:
            tags.append('development')
        if 'permit' in title:
            tags.append('permit')
        if 'environmental' in title:
            tags.append('environmental')
        
        return list(set(tags))  # Remove duplicates

    def _log_request_complete(self, status_code: int):
        """
        Session 296: Log request completion for metrics tracking.
        Uses instance variables set by do_GET/POST/PUT/DELETE.
        """
        start_time = getattr(self, '_request_start_time', None)
        method = getattr(self, '_request_method', 'UNKNOWN')

        if start_time is not None:
            duration_ms = (time.time() - start_time) * 1000
            try:
                log_request_complete(
                    logger,
                    method=method,
                    path=self.path,
                    status_code=status_code,
                    duration_ms=duration_ms
                )
            except Exception:
                # Don't let logging failures break responses
                pass

    def send_json(self, data, status_code=200):
        """Send JSON response with CORS headers, rate limit info, and standardized format"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')

        # Add rate limit headers if available
        client_id = rate_limiter.get_client_id(self)
        _, limit_headers = rate_limiter.check_rate_limit(client_id)
        if limit_headers and isinstance(limit_headers, dict):
            for header, value in limit_headers.items():
                if header.startswith('X-RateLimit'):
                    self.send_header(header, value)

        # Use proper CORS from config
        origin = self.headers.get('Origin', '*')
        allowed_origins = config.get_cors_origins()
        if '*' in allowed_origins or origin in allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
        else:
            self.send_header('Access-Control-Allow-Origin', allowed_origins[0] if allowed_origins else '*')
        self.send_header('X-API-Version', '0.3.0')
        self.send_header('X-Integration-Status', 'schema-compliant')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

        # Session 296: Log request completion for metrics
        self._log_request_complete(status_code)

    def serve_help(self):
        """
        Session 270: Serve user documentation as styled HTML.

        Reads GETTING_STARTED.md and renders it client-side using marked.js.
        This endpoint is public (no auth required) to make docs accessible.
        """
        # Find the docs directory
        # In production: /app/docs/user_guides/GETTING_STARTED.md
        # In development: ../../docs/user_guides/GETTING_STARTED.md (relative to packages/civic-services)
        docs_paths = [
            Path('/app/docs/user_guides/GETTING_STARTED.md'),  # Production (Docker)
            Path(__file__).parent.parent.parent.parent.parent.parent / 'docs' / 'user_guides' / 'GETTING_STARTED.md',  # Development
        ]

        markdown_content = None
        for docs_path in docs_paths:
            if docs_path.exists():
                try:
                    markdown_content = docs_path.read_text(encoding='utf-8')
                    break
                except Exception as e:
                    logger.warning("help_docs_read_error", extra={"path": str(docs_path), "error": str(e)})

        if not markdown_content:
            # Fallback content if docs not found
            markdown_content = """# Civic Help

Welcome to Civic! Documentation is being set up.

For help, contact the Civic team.
"""

        # HTML template with marked.js for client-side rendering
        html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Civic - Getting Started</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root {
            --primary: #2196F3;
            --text-primary: #1a1a2e;
            --text-secondary: #666;
            --background: #fefefe;
            --background-secondary: #f8f9fa;
            --border: #e0e0e0;
            --accent-green: #859900;
            --accent-cyan: #2aa198;
        }

        * {
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background: var(--background);
            margin: 0;
            padding: 0;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 24px;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
        }

        .header h1 {
            color: var(--primary);
            font-size: 28px;
            margin: 0 0 8px 0;
        }

        .header p {
            color: var(--text-secondary);
            margin: 0;
        }

        #content h1 {
            font-size: 32px;
            color: var(--primary);
            margin-top: 0;
        }

        #content h2 {
            font-size: 24px;
            color: var(--text-primary);
            margin-top: 40px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }

        #content h3 {
            font-size: 18px;
            color: var(--text-primary);
            margin-top: 32px;
        }

        #content p {
            color: var(--text-primary);
            margin: 16px 0;
        }

        #content ul, #content ol {
            padding-left: 24px;
        }

        #content li {
            margin: 8px 0;
        }

        #content strong {
            color: var(--text-primary);
        }

        #content em {
            color: var(--text-secondary);
            background: var(--background-secondary);
            padding: 2px 6px;
            border-radius: 4px;
            font-style: normal;
        }

        #content code {
            background: var(--background-secondary);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 14px;
        }

        #content hr {
            border: none;
            border-top: 1px solid var(--border);
            margin: 32px 0;
        }

        #content table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }

        #content th, #content td {
            padding: 12px;
            text-align: left;
            border: 1px solid var(--border);
        }

        #content th {
            background: var(--background-secondary);
            font-weight: 600;
        }

        #content a {
            color: var(--primary);
            text-decoration: none;
        }

        #content a:hover {
            text-decoration: underline;
        }

        .back-link {
            display: inline-block;
            margin-bottom: 24px;
            color: var(--primary);
            text-decoration: none;
            font-size: 14px;
        }

        .back-link:hover {
            text-decoration: underline;
        }

        @media (max-width: 600px) {
            .container {
                padding: 24px 16px;
            }

            #content h1 {
                font-size: 24px;
            }

            #content h2 {
                font-size: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">&larr; Back to Civic</a>
        <div id="content"></div>
    </div>
    <script>
        const markdown = MARKDOWN_CONTENT_PLACEHOLDER;
        document.getElementById('content').innerHTML = marked.parse(markdown);
    </script>
</body>
</html>'''

        # Escape the markdown content for embedding in JavaScript
        import json as json_module
        escaped_content = json_module.dumps(markdown_content)

        # Replace placeholder with actual content
        html_output = html_template.replace('MARKDOWN_CONTENT_PLACEHOLDER', escaped_content)

        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'public, max-age=3600')  # Cache for 1 hour
        self.end_headers()
        self.wfile.write(html_output.encode('utf-8'))

        logger.info("help_served", extra={"status": "success"})

    def log_message(self, format, *args):
        """Custom logging with structured logging (Session 246)"""
        # Parse the standard HTTP request log format to extract details
        message = format % args
        # Typical format: "GET /api/events HTTP/1.1" 200 -
        logger.debug("http_request", extra={"raw_message": message})

def run_authenticated_server(port=8001):
    """Run the authenticated API server"""
    # Validate environment configuration on startup
    try:
        config.validate_environment()
        logger.info("server_startup", extra={"status": "environment_validated"})
    except RuntimeError as e:
        logger.error("server_startup_failed", extra={"error": str(e), "phase": "environment_validation"})
        return

    # Clean up old conversations periodically
    conversation_manager.clear_old_conversations(24)

    # Bind to 0.0.0.0 to accept connections from outside the container (required for Fly.io)
    host = '0.0.0.0'
    server = HTTPServer((host, port), AuthenticatedCivicAPIHandler)

    # Log server startup
    logger.info("server_started", extra={
        "port": port,
        "host": host,
        "openai_available": OPENAI_AVAILABLE and bool(os.getenv('OPENAI_API_KEY'))
    })

    # Console output for human-readable startup info (kept for operators)
    print(f"Civic API running on http://{host}:{port}")
    print(f"Health: /health | Status: /api/status | Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("server_shutdown", extra={"reason": "keyboard_interrupt"})
        server.shutdown()

if __name__ == '__main__':
    # Check for refresh flag
    if len(sys.argv) > 1 and sys.argv[1] == '--refresh':
        print("🔄 Refreshing civic data before starting server...")
        try:
            # Import civic_digest module directly instead of using subprocess
            try:
                from . import civic_digest
            except ImportError:
                import civic_digest
            
            # Create digest instance and refresh data
            digest = civic_digest.CivicDigest()
            test_url = "https://www.cityofsanrafael.org/meetings/planning-commission-may-27-2025/"
            events = digest.scrape_meeting(test_url)
            
            print(f"✅ Data refresh complete! Found {len(events)} events")
        except Exception as e:
            print(f"⚠️  Data refresh failed: {e}, but starting server anyway...")
    
    # Use port from config system (respects CIVIC_API_PORT environment variable)
    port = config.get_api_port()
    run_authenticated_server(port=port)