"""AI proxy endpoint for zero-config AI drafting and tool-backed chat.

Authenticates via Nostr-signed requests (reusing existing identity),
forwards to Anthropic with server-side API key. Users get AI drafting
with zero configuration — no API key needed.

The /ai/chat endpoint uses direct Anthropic tool_use: Claude gets
static tool definitions and executes them via REST calls to the MCP
server. Simple, fast, single-turn tool use.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limits
DAILY_LIMIT_PER_NPUB = 20
DAILY_COST_CAP = 5.0  # $5/day global cap
COST_PER_REQUEST = 0.01  # ~$0.01 per Sonnet request
CHAT_COST_PER_REQUEST = 0.02  # ~$0.02 per chat request (2 API calls)
MAX_AGE_SECONDS = 300  # 5-minute replay window
AI_DRAFT_KIND = 24242  # Custom Nostr kind for AI proxy auth

# MCP server base URL (set via configure_ai_proxy)
_mcp_base_url: str = ""

# MVP tool subset for chat — keeps cost/latency low
CHAT_TOOLS = [
    "search_meeting_history",
    "get_upcoming_meetings",
    "search_budget",
    "get_public_testimony",
    "search_legislation",
    "find_similar_issues",
]

MAX_TOOL_RESULT_CHARS = 4000

# Static Anthropic tool definitions for the 6 chat tools
TOOL_DEFINITIONS = [
    {
        "name": "search_meeting_history",
        "description": "Search past city council meetings, decisions, and video transcripts. Returns meeting dates, decision outcomes, and relevant transcript excerpts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g., 'homeless shelter', 'bike lane')"},
                "include_transcripts": {"type": "boolean", "description": "Include video transcript excerpts", "default": True},
                "limit": {"type": "integer", "description": "Maximum results per category", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_upcoming_meetings",
        "description": "Get upcoming city council and commission meetings with their agendas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Days to look ahead", "default": 30},
            },
            "required": [],
        },
    },
    {
        "name": "search_budget",
        "description": "Search the city's budget data by department, program, or spending category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Budget search query (e.g., 'police', 'parks', 'capital improvement')"},
                "limit": {"type": "integer", "description": "Maximum results", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_public_testimony",
        "description": "Search public testimony and comments from meeting transcripts on a specific topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to search testimony for"},
                "limit": {"type": "integer", "description": "Maximum results", "default": 10},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "search_legislation",
        "description": "Search state and federal legislation relevant to the city, including bills and regulatory changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Legislation search query"},
                "limit": {"type": "integer", "description": "Maximum results", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_similar_issues",
        "description": "Find 311/SeeClickFix community-reported issues similar to a topic, using semantic search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to search (e.g., 'traffic safety', 'pothole')"},
                "semantic": {"type": "boolean", "description": "Use semantic matching", "default": True},
                "limit": {"type": "integer", "description": "Maximum results", "default": 20},
            },
            "required": ["topic"],
        },
    },
]

# Tool name → REST endpoint name mapping (underscore → hyphen)
TOOL_REST_MAP = {
    "search_meeting_history": "search-meeting-history",
    "get_upcoming_meetings": "get-upcoming-meetings",
    "search_budget": "search-budget",
    "get_public_testimony": "get-public-testimony",
    "search_legislation": "search-legislation",
    "find_similar_issues": "find-similar-issues",
}


def configure_ai_proxy(mcp_base_url: str) -> None:
    """Set the MCP server base URL for REST tool calls."""
    global _mcp_base_url
    _mcp_base_url = mcp_base_url.rstrip("/")
    logger.info("AI proxy configured with MCP URL: %s", _mcp_base_url)


async def _call_mcp_tool(name: str, args: dict) -> str:
    """Execute a tool via REST call to the MCP server."""
    rest_name = TOOL_REST_MAP.get(name)
    if not rest_name:
        return json.dumps({"error": f"Unknown tool: {name}"})

    url = f"{_mcp_base_url}/api/tools/{rest_name}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=args)
        resp.raise_for_status()
        data = resp.json()

    # Extract result text, truncate if needed
    result = data.get("result", "")
    if isinstance(result, dict):
        result = json.dumps(result, indent=2, default=str)
    if isinstance(result, str) and len(result) > MAX_TOOL_RESULT_CHARS:
        result = result[:MAX_TOOL_RESULT_CHARS] + "\n... (truncated)"
    return result


# In-memory rate tracking (resets on container restart, fine for pilot)
_rate_limits: dict[str, dict] = {}
_global_cost: dict[str, float | str] = {"total": 0.0, "reset_date": ""}


class AIDraftRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    public_key: str
    signature: str
    created_at: int


class AIDraftResponse(BaseModel):
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    provider: str = "civicos"


class ChatUserContext(BaseModel):
    model_config = {"populate_by_name": True}

    journal_notes: Optional[str] = Field(None, alias="journalNotes")


class AIChatRequest(BaseModel):
    question: str
    jurisdiction: Optional[str] = None
    public_key: str
    signature: str
    created_at: int
    user_context: Optional[ChatUserContext] = None


class AIChatResponse(BaseModel):
    success: bool
    text: Optional[str] = None
    tool_used: Optional[str] = None
    error: Optional[str] = None
    provider: str = "civicos"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _check_rate_limit(public_key: str) -> tuple[bool, Optional[str]]:
    """Check per-npub and global rate limits."""
    today = _today_str()

    # Reset global cost if new day
    if _global_cost.get("reset_date") != today:
        _global_cost["total"] = 0.0
        _global_cost["reset_date"] = today

    # Global cost cap
    if float(_global_cost["total"]) >= DAILY_COST_CAP:
        return False, "Service temporarily unavailable — daily capacity reached. Try again tomorrow."

    # Per-npub daily limit
    entry = _rate_limits.get(public_key)
    if not entry or entry.get("reset_date") != today:
        _rate_limits[public_key] = {"count": 0, "reset_date": today}

    if _rate_limits[public_key]["count"] >= DAILY_LIMIT_PER_NPUB:
        return False, f"Rate limit exceeded — {DAILY_LIMIT_PER_NPUB} drafts per day. Try again tomorrow."

    return True, None


def _record_usage(public_key: str) -> None:
    """Record a successful request for rate limiting."""
    today = _today_str()
    if public_key not in _rate_limits or _rate_limits[public_key].get("reset_date") != today:
        _rate_limits[public_key] = {"count": 0, "reset_date": today}
    _rate_limits[public_key]["count"] += 1
    _global_cost["total"] = float(_global_cost.get("total", 0.0)) + COST_PER_REQUEST


def _verify_ai_signature(public_key: str, signature: str, created_at: int) -> bool:
    """Verify Nostr event signature for AI proxy auth.

    The extension signs a Nostr event (kind 24242) with:
      content = "civicos:ai:v1:{public_key}:{created_at}"
      tags = [["action", "ai_draft"]]
    The signature is over the event ID (SHA-256 of serialized event).
    """
    try:
        from civicos_relay.voice.crypto import (
            _check_key_sig,
            _compute_nostr_event_id,
            _schnorr_verify,
        )

        if not _check_key_sig(public_key, signature):
            return False

        tags = [["action", "ai_draft"]]
        content = f"civicos:ai:v1:{public_key}:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, AI_DRAFT_KIND, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        logger.exception("Signature verification error")
        return False


def _check_attestation(public_key: str) -> bool:
    """Check if pubkey has a valid residency attestation."""
    try:
        from .coordination import _get_attestation_storage

        storage = _get_attestation_storage()
        if not storage:
            return False
        attestation = storage.get_attestation(public_key, "city-san-rafael")
        return attestation is not None
    except ImportError:
        # When running on relay (not alongside coordination router),
        # import attestation storage directly
        try:
            from civicos_relay.storage.postgres import PostgresAttestationStorage
            relay_url = os.environ.get("RELAY_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if not relay_url:
                return False
            storage = PostgresAttestationStorage(relay_url)
            attestation = storage.get_attestation(public_key, "city-san-rafael")
            return attestation is not None
        except Exception:
            logger.exception("Attestation check error (direct)")
            return False
    except Exception:
        logger.exception("Attestation check error")
        return False


@router.post("/ai/draft", response_model=AIDraftResponse)
async def ai_draft(request: AIDraftRequest):
    """Generate an AI draft using the CivicOS proxy.

    Authenticates via Nostr signature, verifies attestation,
    rate-limits per npub, and forwards to Anthropic's Claude API.
    """
    # 1. Replay protection — reject stale timestamps
    now = int(time.time())
    if abs(now - request.created_at) > MAX_AGE_SECONDS:
        raise HTTPException(status_code=400, detail="Request expired — timestamp too old")

    # 2. Verify Nostr signature
    if not _verify_ai_signature(request.public_key, request.signature, request.created_at):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Verify residency attestation
    if not _check_attestation(request.public_key):
        raise HTTPException(status_code=403, detail="Residency verification required — verify in Settings to use CivicOS AI")

    # 4. Rate limits
    allowed, error_msg = _check_rate_limit(request.public_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=error_msg)

    # 5. Forward to Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        kwargs: dict = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system_prompt:
            kwargs["system"] = request.system_prompt

        response = client.messages.create(**kwargs)
        text = response.content[0].text if response.content else None

        if not text:
            return AIDraftResponse(success=False, error="AI returned empty response")

        _record_usage(request.public_key)
        logger.info("ai_draft_success", extra={"npub_prefix": request.public_key[:8]})
        return AIDraftResponse(success=True, text=text)

    except anthropic.RateLimitError:
        return AIDraftResponse(success=False, error="AI service is busy — please try again in a moment")
    except Exception as e:
        logger.exception("AI draft error")
        return AIDraftResponse(success=False, error=f"AI service error: {str(e)[:200]}")


@router.post("/ai/chat", response_model=AIChatResponse)
async def ai_chat(request: AIChatRequest):
    """Answer a civic question using AI with tool-backed search.

    Uses direct Anthropic tool_use: Claude gets 6 civic tool definitions
    and calls them via REST to the MCP server. Simple agentic loop.
    """
    # 1. Replay protection
    now = int(time.time())
    if abs(now - request.created_at) > MAX_AGE_SECONDS:
        raise HTTPException(status_code=400, detail="Request expired — timestamp too old")

    # 2. Verify Nostr signature (same auth as draft)
    if not _verify_ai_signature(request.public_key, request.signature, request.created_at):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Verify residency attestation
    if not _check_attestation(request.public_key):
        raise HTTPException(status_code=403, detail="Residency verification required — verify in Settings to use CivicOS AI")

    # 4. Rate limits (shared pool, but chat costs 2x)
    allowed, error_msg = _check_rate_limit(request.public_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=error_msg)

    # 5. Check prerequisites
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")

    if not _mcp_base_url:
        raise HTTPException(status_code=503, detail="Chat tools not configured — MCP URL not set")

    try:
        jurisdiction = request.jurisdiction or "city-san-rafael"

        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = (
            f"You are a civic assistant for {jurisdiction}. "
            "Answer the user's question using the available tools to search real civic data. "
            "Be concise and factual. Cite specific dates, amounts, or meeting names when available. "
            "If no tool is relevant, answer based on your general knowledge and note the limitation."
        )

        # Personalize system prompt with user context
        if request.user_context and request.user_context.journal_notes:
            system_prompt += f" The user's civic journal: {request.user_context.journal_notes}"

        # Agentic loop: let Claude use tools iteratively until it produces a final answer
        messages = [{"role": "user", "content": request.question}]
        tool_used = None
        max_turns = 3  # 3 turns is plenty with direct tool definitions

        for _turn in range(max_turns):
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            # Separate tool_use and text blocks
            tool_use_blocks = []
            text_blocks = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_use_blocks.append(block)
                elif block.type == "text":
                    text_blocks.append(block.text)

            if not tool_use_blocks:
                # No more tool calls — Claude is done
                final_text = "\n".join(text_blocks) if text_blocks else None
                if not final_text:
                    return AIChatResponse(success=False, error="AI returned empty response")

                _record_usage(request.public_key)
                _global_cost["total"] = float(_global_cost.get("total", 0.0)) + CHAT_COST_PER_REQUEST - COST_PER_REQUEST

                logger.info("ai_chat_success", extra={
                    "npub_prefix": request.public_key[:8],
                    "tool": tool_used or "none",
                    "turns": _turn + 1,
                })
                return AIChatResponse(success=True, text=final_text, tool_used=tool_used)

            # Execute all tool calls and build the next message pair
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            tool_result_content = []
            for tool_block in tool_use_blocks:
                tool_used = tool_block.name

                try:
                    result = await _call_mcp_tool(tool_block.name, tool_block.input)
                except Exception as e:
                    logger.warning("MCP tool call failed: %s: %s", tool_block.name, e)
                    result = json.dumps({"error": f"Tool failed: {str(e)[:200]}"})

                tool_result_content.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result if isinstance(result, str) else json.dumps(result),
                })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_result_content})

        # Exhausted turns — return whatever we have
        return AIChatResponse(success=False, error="Chat exceeded maximum tool-use turns")

    except Exception as e:
        logger.exception("AI chat error")
        return AIChatResponse(success=False, error=f"AI service error: {str(e)[:200]}")
