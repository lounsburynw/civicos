"""AI proxy endpoint for zero-config AI drafting and tool-backed chat.

Authenticates via Nostr-signed requests (reusing existing identity),
forwards to Anthropic with server-side API key. Users get AI drafting
with zero configuration — no API key needed.

The /ai/chat endpoint adds tool-backed search: the client sends a
natural-language question, Claude selects which civic tool to call,
the server executes it, and returns a synthesized answer.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

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

# Tool-backed chat state (set via configure_chat_tools)
_chat_registry: Any = None
_chat_jurisdiction: str = ""

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


def configure_chat_tools(registry: Any, jurisdiction: str) -> None:
    """Set the tool registry and jurisdiction for the /ai/chat endpoint."""
    global _chat_registry, _chat_jurisdiction
    _chat_registry = registry
    _chat_jurisdiction = jurisdiction

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

    # 4. Forward to Anthropic
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


def _build_chat_tools() -> list[dict]:
    """Build Anthropic tool definitions from the registry for the MVP subset."""
    if not _chat_registry:
        return []
    tools = []
    for tool_def in _chat_registry.list_tools():
        if tool_def["name"] in CHAT_TOOLS:
            tools.append({
                "name": tool_def["name"],
                "description": tool_def["description"],
                "input_schema": tool_def["inputSchema"],
            })
    return tools


@router.post("/ai/chat", response_model=AIChatResponse)
async def ai_chat(request: AIChatRequest):
    """Answer a civic question using AI with tool-backed search.

    Authenticates via Nostr signature, selects the right civic tool,
    executes it server-side, and returns a synthesized answer.
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

    # 4. Check prerequisites
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")

    if not _chat_registry:
        raise HTTPException(status_code=503, detail="Chat tools not configured")

    try:
        tools = _build_chat_tools()
        if not tools:
            return AIChatResponse(success=False, error="No chat tools available")

        jurisdiction = request.jurisdiction or _chat_jurisdiction

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

        # First call: let Claude decide which tool to use
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=[{"role": "user", "content": request.question}],
        )

        # Check if Claude wants to use a tool
        tool_use_block = None
        text_blocks = []
        for block in response.content:
            if block.type == "tool_use":
                tool_use_block = block
            elif block.type == "text":
                text_blocks.append(block.text)

        if not tool_use_block:
            # No tool needed — return Claude's direct answer
            text = "\n".join(text_blocks) if text_blocks else None
            if not text:
                return AIChatResponse(success=False, error="AI returned empty response")
            _record_usage(request.public_key)
            return AIChatResponse(success=True, text=text)

        # Execute the tool
        tool_name = tool_use_block.name
        tool_args = tool_use_block.input

        try:
            tool_result = _chat_registry.call_tool(tool_name, tool_args)
            # Truncate large results
            if isinstance(tool_result, str) and len(tool_result) > MAX_TOOL_RESULT_CHARS:
                tool_result = tool_result[:MAX_TOOL_RESULT_CHARS] + "\n... (truncated)"
        except Exception as e:
            logger.warning("Tool execution failed: %s(%s): %s", tool_name, tool_args, e)
            tool_result = json.dumps({"error": f"Tool failed: {str(e)[:200]}"})

        # Second call: Claude summarizes the tool result
        # Serialize assistant content blocks for the messages API
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

        response2 = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=[
                {"role": "user", "content": request.question},
                {"role": "assistant", "content": assistant_content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_block.id,
                            "content": tool_result if isinstance(tool_result, str) else json.dumps(tool_result),
                        }
                    ],
                },
            ],
        )

        # Extract final text
        final_text = ""
        for block in response2.content:
            if block.type == "text":
                final_text += block.text

        if not final_text:
            return AIChatResponse(success=False, error="AI returned empty response")

        # Record usage at chat rate (2x)
        _record_usage(request.public_key)
        _global_cost["total"] = float(_global_cost.get("total", 0.0)) + CHAT_COST_PER_REQUEST - COST_PER_REQUEST

        logger.info("ai_chat_success", extra={"npub_prefix": request.public_key[:8], "tool": tool_name})
        return AIChatResponse(success=True, text=final_text, tool_used=tool_name)

    except Exception as e:
        logger.exception("AI chat error")
        return AIChatResponse(success=False, error=f"AI service error: {str(e)[:200]}")
