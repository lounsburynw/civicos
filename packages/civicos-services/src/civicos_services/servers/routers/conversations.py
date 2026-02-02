"""
Conversations router: AI conversations and chat routing.

Endpoints:
- POST /conversation - AI conversation
- POST /chat/route - Route chat to appropriate handler
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


router = APIRouter()


# === Pydantic Models ===

class ConversationMessage(BaseModel):
    """Conversation message."""
    role: str  # user, assistant, system
    content: str


class ConversationRequest(BaseModel):
    """Conversation request."""
    message: str
    conversation_id: Optional[str] = None
    history: Optional[List[ConversationMessage]] = None
    context: Optional[Dict[str, Any]] = None


class ConversationResponse(BaseModel):
    """Conversation response."""
    response: str
    conversation_id: str
    sources: Optional[List[Dict[str, Any]]] = None
    suggestions: Optional[List[str]] = None


class ChatRouteRequest(BaseModel):
    """Chat routing request.

    Matches frontend chatRouter.ts interface for full chat routing with
    function calling, mode detection, and context awareness.
    """
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    mode: Optional[str] = "navigation"  # navigation, focus, compare
    serialized_context: Optional[str] = None  # LLM-friendly context from open artifacts
    model_override: Optional[str] = None  # Manual model selection


class ChatActionUsage(BaseModel):
    """Token usage for LLM calls."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatRouteResponse(BaseModel):
    """Chat routing response.

    Full response matching frontend ChatAction interface, supporting
    function calling actions, multi-operations, and provider metadata.
    """
    action: str  # search_events, file_complaint, respond, etc.
    parameters: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    reasoning: Optional[str] = None
    conversation_id: str
    mode: Optional[str] = None  # Detected mode (may differ from input)
    mode_changed: Optional[bool] = False  # True if mode switched
    mode_reason: Optional[str] = None  # Why this mode was chosen
    # Multi-operation support for OR queries
    multi_operation: Optional[bool] = False
    operation_count: Optional[int] = None
    all_operations: Optional[List[Dict[str, Any]]] = None
    # Provider metadata for developer mode
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    usage: Optional[ChatActionUsage] = None
    error: Optional[str] = None


# === Auth Dependency ===

from .dependencies import verify_auth


# === In-Memory Conversation Storage (Fallback) ===

CONVERSATIONS: Dict[str, List[Dict]] = {}


# === Helper Functions ===

def get_conversation_store():
    """Get conversation store instance."""
    try:
        from civicos_services.storage.conversation_store import ConversationStore
        return ConversationStore()
    except ImportError:
        return None


def get_llm_provider():
    """Get LLM provider for conversations."""
    try:
        from civicos_services.core.llm_provider import get_provider_for_task
        return get_provider_for_task("conversation")
    except ImportError:
        return None


def get_chat_router():
    """Get chat router for intent classification."""
    try:
        from civicos_services.chat.civic_chat_router import get_router
        return get_router()
    except ImportError:
        return None


# === Endpoints ===

@router.post("/conversation", response_model=ConversationResponse)
async def handle_conversation(
    request: ConversationRequest,
    token: str = Depends(verify_auth)
):
    """
    Handle an AI conversation.

    Maintains conversation context and provides civic-aware responses.
    Requires authentication.
    """
    try:
        import uuid

        # Get or create conversation ID
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # Get conversation store
        store = get_conversation_store()

        # Build message history
        if request.history:
            messages = [{"role": m.role, "content": m.content} for m in request.history]
        elif store:
            messages = store.get_conversation(conversation_id)
        else:
            messages = CONVERSATIONS.get(conversation_id, [])

        # Add user message
        messages.append({"role": "user", "content": request.message})

        # Get LLM provider
        provider = get_llm_provider()
        if not provider:
            # Fallback to OpenAI directly
            try:
                import openai
                client = openai.OpenAI()

                # Add system message for civic context
                system_message = {
                    "role": "system",
                    "content": """You are a helpful civic engagement assistant. You help users:
- Understand local government processes
- Find relevant civic events and meetings
- Navigate legislation and policy
- Connect with their community

Be concise, accurate, and helpful. When discussing civic matters, focus on empowering
the user to participate effectively in local democracy."""
                }

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[system_message] + messages,
                    max_tokens=500
                )

                assistant_response = response.choices[0].message.content

            except Exception as e:
                raise HTTPException(status_code=503, detail=f"LLM not available: {str(e)}")
        else:
            assistant_response = provider.chat(messages, context=request.context)

        # Add assistant message to history
        messages.append({"role": "assistant", "content": assistant_response})

        # Store conversation
        if store:
            store.save_conversation(conversation_id, messages, user_id=token)
        else:
            CONVERSATIONS[conversation_id] = messages

        return {
            "response": assistant_response,
            "conversation_id": conversation_id,
            "sources": [],
            "suggestions": []
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/chat/route", response_model=ChatRouteResponse)
async def route_chat(
    request: ChatRouteRequest,
    token: str = Depends(verify_auth)
):
    """
    Route a chat message via LLM function calling.

    Uses ChatRouter.route_message() to:
    - Detect optimal chat mode (navigation, focus, compare)
    - Parse intent via OpenAI function calling
    - Execute search_events, file_complaint, view_legislative_context, etc.
    - Return structured action with parameters for frontend UI dispatch

    Requires authentication.
    """
    import uuid

    try:
        # Get or create conversation ID
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # Get chat router
        chat_router = get_chat_router()

        if chat_router:
            # Build conversation history from store if available
            conversation_history = None
            store = get_conversation_store()
            if store and request.conversation_id:
                conversation_history = store.get_conversation(request.conversation_id)

            # Route message via LLM function calling
            result = chat_router.route_message(
                message=request.message,
                conversation_history=conversation_history,
                context=request.context,
                mode=request.mode or 'navigation',
                serialized_context=request.serialized_context or '',
                model_override=request.model_override
            )

            # Build response matching ChatAction interface
            response = {
                "action": result.get("action", "respond"),
                "parameters": result.get("parameters"),
                "message": result.get("message"),
                "reasoning": result.get("reasoning"),
                "conversation_id": conversation_id,
                "mode": result.get("mode"),
                "mode_changed": result.get("mode_changed", False),
                "mode_reason": result.get("mode_reason"),
                "multi_operation": result.get("multi_operation", False),
                "operation_count": result.get("operation_count"),
                "all_operations": result.get("all_operations"),
                "provider_used": result.get("provider_used"),
                "model_used": result.get("model_used"),
                "error": result.get("error"),
            }

            # Handle usage field
            if result.get("usage"):
                response["usage"] = ChatActionUsage(
                    prompt_tokens=result["usage"].get("prompt_tokens", 0),
                    completion_tokens=result["usage"].get("completion_tokens", 0),
                    total_tokens=result["usage"].get("total_tokens", 0)
                )

            return response

        else:
            # Fallback: simple keyword-based routing when ChatRouter unavailable
            message_lower = request.message.lower()

            if any(word in message_lower for word in ["meeting", "event", "agenda", "council"]):
                action = "search_events"
            elif any(word in message_lower for word in ["issue", "problem", "complaint", "broken", "fix"]):
                action = "file_complaint"
            elif any(word in message_lower for word in ["law", "bill", "legislation", "vote", "election"]):
                action = "view_legislative_context"
            else:
                action = "respond"

            return {
                "action": action,
                "parameters": {},
                "message": "Chat router not available. Please try again later." if action == "respond" else None,
                "conversation_id": conversation_id,
                "mode": request.mode or "navigation",
                "mode_changed": False,
            }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Chat routing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/research")
async def handle_research_query(
    request: Dict[str, Any],
    token: str = Depends(verify_auth)
):
    """
    Handle a research query.

    Uses cache-first factual retrieval for research questions.
    Requires authentication.
    """
    try:
        query = request.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Try to get research service
        try:
            from civicos_services.storage.research_service import ResearchService
            service = ResearchService()
            result = service.research(query, context=request.get("context"))
            return {
                "success": True,
                "query": query,
                "result": result
            }
        except ImportError:
            raise HTTPException(status_code=503, detail="Research service not available")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
