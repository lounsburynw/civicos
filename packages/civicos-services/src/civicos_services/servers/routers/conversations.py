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
    """Chat routing request."""
    message: str
    context: Optional[Dict[str, Any]] = None


class ChatRouteResponse(BaseModel):
    """Chat routing response."""
    route: str  # events, issues, legislation, general
    intent: str
    entities: Optional[Dict[str, Any]] = None
    response: Optional[str] = None


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
    Route a chat message to the appropriate handler.

    Classifies intent and extracts entities for downstream processing.
    Requires authentication.
    """
    try:
        # Get chat router
        chat_router = get_chat_router()

        if chat_router:
            # Use specialized router
            result = chat_router.route(request.message, context=request.context)
            return {
                "route": result.get("route", "general"),
                "intent": result.get("intent", "unknown"),
                "entities": result.get("entities"),
                "response": result.get("response")
            }
        else:
            # Fallback: simple keyword-based routing
            message_lower = request.message.lower()

            if any(word in message_lower for word in ["meeting", "event", "agenda", "council"]):
                route = "events"
                intent = "find_events"
            elif any(word in message_lower for word in ["issue", "problem", "complaint", "broken", "fix"]):
                route = "issues"
                intent = "file_issue"
            elif any(word in message_lower for word in ["law", "bill", "legislation", "vote", "election"]):
                route = "legislation"
                intent = "find_legislation"
            else:
                route = "general"
                intent = "general_inquiry"

            return {
                "route": route,
                "intent": intent,
                "entities": {},
                "response": None
            }

    except Exception as e:
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
