"""
Chat Router for Civic Conversational OS

Routes user chat messages to appropriate functions using smart provider selection.
Enables natural language navigation: "show housing meetings" → search_events() → UI update.

Session 68: Updated to use provider abstraction for 85% cost reduction.
Session 77: Restored structured query planning for reliable OR/AND queries.
"""

from openai import OpenAI
import json
from typing import Dict, List, Optional, Literal
import os
import logging
import re

# Session 77: Structured outputs for query planning
from pydantic import BaseModel, Field
import instructor

# Session 68: Import provider abstraction
from ..core.llm_provider import get_provider_for_task, get_model_for_task

# Session 507: Cost tracking for LLM calls
from ..core.cost_tracking import log_llm_cost

logger = logging.getLogger(__name__)

# Session 60: JURISDICTION_MAPPINGS dictionary deleted - now using LLM-based normalization
# via get_navigation_system_prompt() which auto-generates from CITY_CONFIGS


# ============================================================================
# Session 77: Pydantic Models for Structured Query Planning
# ============================================================================

class SearchFilters(BaseModel):
    """Filters for search_events and view_legislative_context operations."""
    jurisdiction: Optional[str] = Field(
        None,
        description="Normalized jurisdiction_id (e.g., 'city-berkeley', 'all')"
    )
    topic: Optional[str] = Field(
        None,
        description="Topic enum value (housing, transportation, environment, budget, education, etc.)"
    )
    date_range: Optional[str] = Field(
        None,
        description="Time filter (e.g., 'this week', 'next month')"
    )
    query: Optional[str] = Field(
        None,
        description="Free-text search query for specific items"
    )
    level: Optional[Literal["state", "federal", "both"]] = Field(
        None,
        description="Government level for legislative searches"
    )


class ComplaintData(BaseModel):
    """Data for file_complaint operation."""
    title: Optional[str] = Field(None, description="Short title for complaint")
    description: Optional[str] = Field(None, description="Detailed description")
    address: Optional[str] = Field(None, description="Location of issue")
    category: Optional[str] = Field(None, description="Category of complaint")


class Operation(BaseModel):
    """Single operation in a query plan."""
    type: Literal[
        "search_events",
        "file_complaint",
        "view_legislative_context",
        "view_my_complaints",
        "respond"
    ] = Field(..., description="Type of operation to perform")

    filters: Optional[SearchFilters] = Field(
        None,
        description="Filters for search operations (required for search_events/view_legislative_context)"
    )

    complaint_data: Optional[ComplaintData] = Field(
        None,
        description="Data for file_complaint operation"
    )

    message: Optional[str] = Field(
        None,
        description="Conversational message for respond operation"
    )


class QueryPlan(BaseModel):
    """Complete query plan with one or more operations.

    Examples:
    - Simple: "show housing" → 1 search_events operation
    - OR query: "housing OR transportation" → 2 search_events operations
    - Complex: "housing in Berkeley OR transportation in Oakland" → 2 operations with different filters
    """
    operations: List[Operation] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Array of operations to execute. Use multiple operations for OR queries."
    )


# ============================================================================
# Session 77: Structured Query Planning
# ============================================================================

def parse_query_to_plan(
    message: str,
    context: Optional[Dict] = None,
    conversation_history: Optional[List[Dict]] = None
) -> QueryPlan:
    """
    Parse natural language query into structured QueryPlan using Instructor.

    Uses cheapest model with structured outputs ($0.075/1M for Gemini Flash)
    with automatic retry on validation failures (99.9% success rate).

    Examples:
        "show housing meetings" → QueryPlan with 1 operation
        "housing OR transportation" → QueryPlan with 2 operations
        "housing in Berkeley OR transportation in Oakland" → QueryPlan with 2 operations, different filters

    Args:
        message: User's natural language query
        context: Optional context (user_city, etc.)
        conversation_history: Optional conversation history for context

    Returns:
        QueryPlan with 1+ operations

    Raises:
        Exception: If parsing fails after max retries
    """
    # Get cheap model for query planning
    provider = get_model_for_task('query_planning')

    # Build system prompt with jurisdiction reference
    from civicos_services.monitoring.automated_civic_refresh import CITY_CONFIGS

    jurisdiction_lines = []
    for city_name, config in sorted(CITY_CONFIGS.items()):
        jurisdiction_id = config['jurisdiction_id']
        display_name = city_name.replace('_', ' ').title()
        jurisdiction_lines.append(f'  - "{display_name}" → "{jurisdiction_id}"')

    jurisdiction_reference = "\n".join(jurisdiction_lines)

    system_prompt = f"""You are a query planner for civic engagement.

Parse user queries into structured operations (search, file complaint, etc.).

**JURISDICTION NORMALIZATION**:
Available jurisdictions:
{jurisdiction_reference}

Special values:
  - "all" → searches ALL jurisdictions
  - "bay area", "everywhere" → "all"

**MULTI-OPERATION SUPPORT** (Critical for OR queries):
- Simple query: "housing in Berkeley" → 1 operation
- OR query: "housing OR transportation" → 2 operations (one per topic)
- Complex OR: "housing in Berkeley OR transportation in Oakland" → 2 operations with different filters

**OPERATION TYPES**:
- search_events: Find government meetings
- file_complaint: Report local issues
- view_legislative_context: Browse state bills/federal programs
- view_my_complaints: Show user's filed complaints
- respond: Conversational response (definitions, explanations)

**CRITICAL RULES**:
1. For "X OR Y" queries, create SEPARATE operations for X and Y
2. Use normalized jurisdiction_id from the list above
3. Use exact topic enums: housing, transportation, environment, budget, education, development, public_safety, community, elections, governance
4. Set unused fields to null

User context: {json.dumps(context or {})}"""

    # Build messages with conversation history
    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": message})

    # Wrap provider with Instructor for structured outputs
    try:
        # Get the underlying client based on provider type
        if provider.name in ['openai', 'openrouter', 'groq', 'perplexity']:
            # OpenAI-compatible providers can use instructor.from_openai()
            client = instructor.from_openai(provider.client)
            query_plan = client.chat.completions.create(
                model=provider.default_model,
                max_tokens=1000,
                temperature=0.1,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                response_model=QueryPlan,
                max_retries=3
            )
        elif provider.name == 'anthropic':
            client = instructor.from_anthropic(provider.client)
            query_plan = client.messages.create(
                model=provider.default_model,
                max_tokens=1000,
                temperature=0.1,
                system=system_prompt,
                messages=messages,
                response_model=QueryPlan,
                max_retries=3
            )
        else:
            # For Google/other providers without native Instructor support,
            # fall back to gpt-4o-mini (cheapest reliable fallback)
            logger.info(f"Provider {provider.name} not supported by Instructor, using gpt-4o-mini fallback")
            from openai import OpenAI
            openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            client = instructor.from_openai(openai_client)
            query_plan = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1000,
                temperature=0.1,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                response_model=QueryPlan,
                max_retries=3
            )

        logger.info(f"Query plan parsed: {len(query_plan.operations)} operation(s)")
        for i, op in enumerate(query_plan.operations):
            logger.info(f"  Operation {i+1}: {op.type} {op.filters or op.complaint_data or ''}")

        return query_plan

    except Exception as e:
        logger.error(f"Query planning failed: {e}")
        # Fallback: create simple respond operation
        return QueryPlan(operations=[
            Operation(
                type="respond",
                message="I encountered an error understanding your request. Could you try rephrasing?"
            )
        ])


def normalize_jurisdiction(llm_jurisdiction: str) -> str:
    """
    Normalize LLM jurisdiction output to canonical format.

    Uses the core normalize_jurisdiction() with strict=False for chat context,
    where LLM output may include special values like "all".

    Args:
        llm_jurisdiction: Jurisdiction from LLM (may be "all", alias, or canonical)

    Returns:
        Final jurisdiction ID for database queries

    Examples:
        "all" → "all"
        "city-berkeley" → "city-berkeley"
        "berkeley" → "city-berkeley" (adds prefix)
    """
    from civicos._internal.jurisdiction import normalize_jurisdiction as core_normalize

    # Handle special case for "all jurisdictions" queries
    if llm_jurisdiction.lower() in ['all', 'everywhere']:
        return 'all'

    # Use core normalize with strict=False for chat (LLM may produce edge cases)
    return core_normalize(llm_jurisdiction, strict=False)


# ============================================================================
# Topic Normalization
# Session 71: Backend validation for enum violations from conversation context
# ============================================================================

VALID_TOPICS = {
    "housing", "transportation", "environment", "budget", "education",
    "development", "public_safety", "community", "elections", "governance", "all"
}

TOPIC_NORMALIZATION = {
    # Housing variants
    "housing development": "housing",
    "housing development and preservation": "housing",
    "affordable housing": "housing",
    "residential": "housing",
    "zoning": "housing",
    "land use": "housing",
    "land-use": "housing",

    # Transportation variants
    "transit": "transportation",
    "public transit": "transportation",
    "traffic": "transportation",
    "roads": "transportation",
    "bike": "transportation",
    "pedestrian": "transportation",
    "parking": "transportation",

    # Environment variants
    "climate": "environment",
    "climate change": "environment",
    "sustainability": "environment",
    "green": "environment",
    "environmental": "environment",
    "renewable energy": "environment",

    # Budget variants
    "finance": "budget",
    "financial": "budget",
    "funding": "budget",
    "fiscal": "budget",
    "cdbg": "budget",  # Community Development Block Grant

    # Development variants
    "economic development": "development",
    "business": "development",
    "commercial": "development",

    # Public safety variants
    "police": "public_safety",
    "fire": "public_safety",
    "emergency": "public_safety",
    "safety": "public_safety",
    "law enforcement": "public_safety",
    "crime": "public_safety",

    # Community variants
    "social services": "community",
    "parks": "community",
    "recreation": "community",
    "library": "community",
    "neighborhood": "community",
}

def normalize_topic(topic: str) -> str:
    """
    Normalize fuzzy topic strings to valid enum values.

    Handles LLM violations of enum constraints due to conversation context.
    Example: "housing development and preservation" → "housing"

    Args:
        topic: Raw topic string from LLM function call

    Returns:
        Valid topic enum value, or "all" as safe fallback
    """
    if not topic:
        return "all"

    topic_lower = topic.lower().strip()

    # Exact match to valid enum
    if topic_lower in VALID_TOPICS:
        return topic_lower

    # Exact match in normalization map
    if topic_lower in TOPIC_NORMALIZATION:
        normalized = TOPIC_NORMALIZATION[topic_lower]
        logger.info(f"Normalized topic: '{topic}' → '{normalized}' (exact match)")
        return normalized

    # Fuzzy substring matching
    for pattern, normalized in TOPIC_NORMALIZATION.items():
        if pattern in topic_lower:
            logger.info(f"Normalized topic: '{topic}' → '{normalized}' (fuzzy match: '{pattern}')")
            return normalized

    # No match - safe fallback
    logger.warning(f"Unknown topic '{topic}' - falling back to 'all'")
    return "all"


CIVICOS_FUNCTIONS = [
    {
        "name": "search_events",
        "description": "Search for upcoming PUBLIC government meetings (city council, planning commission, etc.). NEVER use this when user says 'my' followed by 'issues/complaints/reports'. Those queries refer to user's personal filed complaints and MUST use view_my_complaints.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search for specific items/projects (e.g., 'pothole on Main St', 'park renovation'). Do NOT use for topic categories - use 'topic' parameter instead."
                },
                "jurisdiction": {
                    "type": "string",
                    "description": "City or county name (e.g., 'Berkeley', 'Oakland', 'Alameda County'). Use 'all' for Bay Area-wide searches. REQUIRED: If user doesn't specify a city, respond conversationally to ask which city they want."
                },
                "topic": {
                    "type": "string",
                    "enum": ["housing", "transportation", "environment", "budget", "education", "development", "public_safety", "community", "elections", "governance", "all"],
                    "description": "PREFERRED: Filter by topic category. CRITICAL: Use EXACT enum value only - do not expand, modify, or add descriptive words (e.g., use 'housing' not 'housing development', use 'transportation' not 'public transit'). Choose the single closest match."
                },
                "date_range": {
                    "type": "string",
                    "description": "Time filter (e.g., 'this week', 'next month', 'October 2025')"
                }
            }
        }
    },
    {
        "name": "file_complaint",
        "description": "ALWAYS call this function when user mentions reporting, filing, or submitting a complaint or issue. This opens the complaint form UI. Do NOT ask for details conversationally - just call the function immediately, even with empty parameters. Extract any details mentioned (title, description, address, category) and pass them as parameters to pre-fill the form.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the complaint (optional - leave empty if not provided)"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the issue (optional - leave empty if not provided)"
                },
                "address": {
                    "type": "string",
                    "description": "Location of the issue (optional - street address or intersection)"
                },
                "category": {
                    "type": "string",
                    "enum": ["infrastructure", "housing", "environment", "public_safety", "other"],
                    "description": "Category of complaint (optional - will be auto-detected if not provided)"
                }
            },
            "required": []
        }
    },
    {
        "name": "view_legislative_context",
        "description": "Open the Legislative panel UI to BROWSE state bills and federal programs. ONLY use when user explicitly asks to SEE, SHOW, or EXPLORE legislation (e.g., 'show me housing bills', 'what legislation exists'). NEVER use for: (1) Definition/explanation questions ('What is X?', 'Explain Y') - answer conversationally, (2) CDBG allocation questions - answer conversationally, (3) Budget/funding amount questions - answer conversationally, (4) Questions about specific dollar amounts - answer conversationally, (5) Policy questions without wanting to see bills - answer conversationally. Examples of WRONG usage: 'What's CDBG?' (definition - answer conversationally), 'What's Berkeley's CDBG allocation?' (amount - answer conversationally), 'How much funding does Oakland get?' (amount - answer conversationally). Examples of CORRECT usage: 'Show me housing bills', 'What legislation exists about transit?', 'Display community development programs'",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["housing", "transportation", "environment", "budget", "education", "all"],
                    "description": "Topic area to explore. Use 'all' to show legislation across all topics."
                },
                "level": {
                    "type": "string",
                    "enum": ["state", "federal", "both"],
                    "description": "Government level (default: both)"
                },
                "searchQuery": {
                    "type": "string",
                    "description": "Optional search query to filter bills/programs (e.g., 'affordable housing', 'transit')"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "search_web",
        "description": "Search the web for SPECIFIC current data with source citations. Use ONLY when you need real-time facts, budget allocations, funding amounts, or current status updates that you don't have in your knowledge base. DO NOT use for general civic concepts or terminology (planning commission, CDBG definition, etc.) - answer those conversationally. Returns answer with citations. Examples: 'How much CDBG funding does Berkeley receive in 2024?', 'Latest status of AB 1147', 'What happened at last week's city council meeting?'",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for SPECIFIC factual data (budget amounts, current status, recent events) - NOT general definitions"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "draft_comment",
        "description": "Generate a draft public comment for a specific agenda item or meeting. Use when users want help writing comments, testimony, or statements.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Unique identifier for the meeting/event"
                },
                "agenda_item_id": {
                    "type": "string",
                    "description": "Specific agenda item within the meeting"
                },
                "stance": {
                    "type": "string",
                    "enum": ["support", "oppose", "neutral"],
                    "description": "User's position on the issue"
                },
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main points to include in comment"
                }
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "view_my_complaints",
        "description": "Show USER'S OWN filed complaints/issues/reports (personal submissions by the user). REQUIRED when user says: 'my issues', 'my complaints', 'my reports', or ANY query with 'my' + complaint-related word. Can filter by ownership, status, issue_type, jurisdiction. Examples: 'my issues', 'my housing complaints', 'show my reports in Berkeley', 'open complaints I'm following'.",
        "parameters": {
            "type": "object",
            "properties": {
                "ownership": {
                    "type": "string",
                    "enum": ["all", "mine", "following"],
                    "description": "Filter by ownership (mine=filed by me, following=issues I'm following, all=both). Default: 'mine' unless user explicitly mentions 'following'."
                },
                "status": {
                    "type": "string",
                    "enum": ["all", "open", "closed", "matched"],
                    "description": "Filter by issue status (open=not closed, closed=resolved, matched=has linked events). Can combine with ownership."
                },
                "issue_type": {
                    "type": "string",
                    "enum": ["infrastructure", "housing", "environment", "public_safety", "other", "all"],
                    "description": "Filter by issue type (database column: issue_type)"
                },
                "jurisdiction": {
                    "type": "string",
                    "description": "Filter by city jurisdiction_id (e.g., 'city-berkeley', 'all' for no filter)"
                },
                "query": {
                    "type": "string",
                    "description": "Search for specific text in issue title, description, or address"
                }
            }
        }
    },
    {
        "name": "explain_event",
        "description": "Provide detailed explanation of a specific event or agenda item. Use when users ask for explanations, background, or context about a meeting.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Unique identifier for the event"
                },
                "focus": {
                    "type": "string",
                    "enum": ["summary", "legislative_context", "how_to_participate", "background"],
                    "description": "What aspect to explain"
                }
            },
            "required": ["event_id"]
        }
    }
]

# Session 76: Removed NAVIGATION_SCHEMA - now using pure function calling for all modes
# Previous structured outputs approach replaced with industry-standard function calling


# Session 76: Mode-specific system prompts for pure function-calling architecture
# These guide LLM behavior but don't change routing logic (all modes use function calling)

MODE_SYSTEM_PROMPTS = {
    'navigation': """You are a civic engagement navigation assistant.

Your role: Help users find civic content (events, bills, programs) and take actions (file complaints, draft comments).

Be concise and action-oriented. Use functions to retrieve and display information.

**Context handling**:
- Use jurisdiction parameter intelligently (user's city from context if not specified)
- For OR queries ("housing in Berkeley OR transportation in Oakland"), call search_events() twice
- Preserve conversation context for follow-up queries

**When to use each function**:
- search_events: Find meetings, hearings, council sessions
- search_web: Get factual information, definitions, current status
- view_legislative_context: Browse state bills and federal programs (NOT for explanations)
- file_complaint: Report local issues (potholes, code violations, etc.)
- view_my_complaints: Show user's filed complaints/issues
- draft_comment: Generate public comment for specific event
- explain_event: Provide detailed meeting explanation

Keep responses brief. Let the UI do the heavy lifting.""",

    'focus': """You are a civic engagement research assistant.

Your role: Provide detailed explanations for specific items the user is viewing.

Be thorough and educational. Answer questions using context provided, explain concepts and implications clearly.

**Context handling**:
- User is viewing specific artifacts (events, bills, programs)
- Reference artifacts by name when discussing them
- Use search_web for factual questions you're uncertain about
- Explain civic concepts and processes in clear, accessible language

**What you CAN answer** (using general knowledge):
- Civic concepts and terminology (e.g., "What is CDBG?", "What's a planning commission?")
- How government processes work
- General policy explanations
- Legislative concepts

**What to use search_web for**:
- Specific budget allocations or dollar amounts
- Real-time information
- Current status of bills or programs
- Detailed city financial data

Provide comprehensive, well-reasoned answers.""",

    'compare': """You are a civic engagement analysis assistant.

Your role: Analyze and compare multiple items side-by-side.

Be systematic and analytical. Cite specific artifacts by name. Highlight similarities, differences, and relationships.

**Context handling**:
- User has multiple artifacts open (events, bills, programs)
- Reference each artifact explicitly
- Identify patterns, conflicts, and connections
- Use tabular or structured formats when helpful

**Comparison patterns**:
- Events: Compare topics, jurisdictions, timelines, legislative context
- Bills: Compare provisions, status, sponsors, related federal programs
- Programs: Compare funding, eligibility, application processes
- Cross-type: How bills relate to events, how programs fund local initiatives

Be thorough and precise. Provide actionable insights."""
}

SYSTEM_PROMPT = """You are a helpful civic engagement assistant for the Civic Conversational OS platform.

Your role is to help users:
- Find and understand local government meetings and events
- File complaints about local issues
- Explore relevant state legislation and federal programs
- Draft public comments for meetings
- Track their civic engagement activities

Be concise, friendly, and action-oriented. When you call functions, provide brief reasoning for why you're taking that action.

**IMPORTANT**: When users say "my area", "my city", "here", or similar location references, use their current location from the context. If context includes user_city (e.g., "Oakland"), use that as the jurisdiction parameter. Only ask for a specific city if the user explicitly asks about a different location.

Current context:
- Platform covers 26 cities across California
- Events include city council, planning commission, and other local meetings
- Legislative context includes state bills and federal programs across housing, transportation, environment, budget, and education topics
- Users can file complaints that are automatically matched to relevant upcoming meetings

**What you CAN answer (using your general knowledge):**
- Civic concepts and terminology (e.g., "What is CDBG?", "What's a planning commission?")
- How government processes work (e.g., "How do I submit public comment?")
- General policy explanations (e.g., "What is affordable housing?")
- Legislative concepts (e.g., "What's AB 2011?")

**What you DON'T have access to (be honest when asked):**
- Specific budget allocations or dollar amounts for cities (e.g., "How much CDBG funding does Berkeley get?")
- Detailed city financial data
- Real-time grant information
- Meeting recordings or transcripts

When asked about specific data you don't have:
- Clearly state you don't have that specific data
- Suggest where they might find it (e.g., "You can find CDBG allocations in the city's annual Consolidated Plan or on HUD's website")
- Don't make up numbers or offer to show data you don't have
- Don't present multiple choice options unless explicitly asked
"""


class ChatRouter:
    """
    Routes user chat messages to appropriate functions using smart provider selection.

    Session 68: Uses provider abstraction for cost optimization.
    - Navigation queries → Gemini Flash (85% cheaper)
    - Mode detection → Gemini Flash
    - Still supports OpenAI for backward compatibility

    Enables natural language navigation:
    - "show housing meetings" → search_events(query="housing")
    - "report pothole" → file_complaint(category="infrastructure")
    """

    def __init__(self):
        # Session 68: Keep OpenAI client for backward compatibility (some code paths still use it)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def detect_mode(
        self,
        message: str,
        current_mode: str,
        context_summary: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> tuple[str, str]:
        """
        Detect optimal chat mode based on user message and context.

        Returns: (mode, reasoning)

        Uses lightweight LLM call (gpt-4o-mini, <100 tokens) to classify intent.

        IMPORTANT: Modes are task-based, not artifact-type dependent.
        - Discovery works for ANY content type (events, bills, programs, issues)
        - Focus works for ANY single item
        - Compare works for ANY multiple items (even different types)

        CRITICAL: Return "uncertain" if confidence < 80%. Backend will ask user.
        """
        # Build conversation context for follow-up queries
        conversation_context = ""
        if conversation_history and len(conversation_history) >= 2:
            # Get last 2 messages for context
            recent = conversation_history[-2:]
            conversation_context = "\n\nRecent conversation:\n"
            for msg in recent:
                content = msg.get('content') or ''
                if msg.get('function_call'):
                    func_name = msg['function_call'].get('name', 'unknown')
                    func_args_str = msg['function_call'].get('arguments', '{}')
                    # Parse the arguments to make them more readable
                    try:
                        func_args = json.loads(func_args_str)
                        args_summary = ", ".join(f"{k}={v}" for k, v in func_args.items() if v is not None)
                        conversation_context += f"{msg['role']}: [Called {func_name}({args_summary})]\n"
                    except:
                        conversation_context += f"{msg['role']}: [Called {func_name}]\n"
                else:
                    conversation_context += f"{msg['role']}: {content[:100]}\n" if content else f"{msg['role']}: [no content]\n"

        # System prompt for mode detection (Session 68.5: Improved to distinguish definitions from searches)
        detection_prompt = f"""Analyze this user message and determine the best chat mode.

Current mode: {current_mode}
Context: {context_summary[:200]}
{conversation_context}

User message: "{message}"

Modes (TASK-BASED, work for any content type):

**navigation** - SEARCHING for content or TAKING ACTIONS
  Trigger patterns:
  - Action verbs: "find", "search", "show", "list", "display", "get"
  - Location queries: "meetings in Berkeley", "events about housing"
  - Actions: "file a complaint", "report an issue"
  - Follow-ups: "what about Oakland?", "try transportation instead"

  Examples:
  ✅ "find housing meetings"
  ✅ "show me events in Berkeley"
  ✅ "what meetings are happening?" (searching for meetings)
  ✅ "what about Oakland?" (follow-up changing location)

  NOT for:
  ❌ "what is CDBG?" (definition question → focus)
  ❌ "what's affordable housing?" (explanation → focus)
  ❌ "explain this bill" (understanding → focus)

**focus** - UNDERSTANDING or EXPLAINING concepts
  Trigger patterns:
  - Definition questions: "what is X?", "what's X?", "what does X mean?"
  - Explanations: "explain X", "tell me about X", "how does X work?"
  - Questions about specific items in context
  - Clarification: "what's that about?"

  Examples:
  ✅ "what is CDBG?" (definition)
  ✅ "what's affordable housing?" (explanation)
  ✅ "explain this agenda item" (with context)
  ✅ "tell me more" (after viewing something)

  NOT for:
  ❌ "what meetings are there?" (searching → navigation)
  ❌ "what's happening in Berkeley?" (searching → navigation)

**compare** - ANALYZING multiple things side-by-side
  - Requires 2+ items in context OR explicit comparison intent
  - Keywords: "compare", "difference between", "which is better"

CRITICAL DISTINCTION:
- "what [plural noun]" = navigation (searching)
  Examples: "what meetings", "what events", "what bills"
- "what is [singular noun]" = focus (definition)
  Examples: "what is CDBG", "what's housing", "what does X mean"

CONTEXT INFERENCE RULES:
1. If recent conversation shows a function_call, assume follow-up queries continue that task
   - After search_events → vague query = navigation (repeat/modify search)
   - After opening artifact → "tell me more" = focus (explain that item)

2. Only classify as "uncertain" if BOTH conditions are true:
   - Query is genuinely ambiguous in isolation
   - Recent conversation provides NO context to resolve ambiguity

3. Confidence threshold: >80% certain, otherwise use "uncertain"

Reply format: "mode - brief reason"
Examples:
  "navigation - searching for housing meetings"
  "focus - definition question about CDBG"
  "focus - asking for explanation"
  "compare - wants to analyze multiple items"
  "uncertain - no recent context and query is ambiguous"
"""

        try:
            # Session 68: Use smart routing for mode detection (Gemini Flash)
            provider = get_provider_for_task('navigation')

            response = provider.complete(
                messages=[{"role": "user", "content": detection_prompt}],
                max_tokens=150,  # Session 72: Increased for Groq Responses API (reasoning mode + actual response)
                temperature=0.1  # Low temperature for consistent classification
            )

            # Session 507: Log cost for mode detection
            if response.usage:
                log_llm_cost(
                    model=provider.default_model,
                    usage=response.usage,
                    provider=provider.name,
                    task='mode_detection',
                )

            result = response.content.strip()

            # Parse "mode - reason" format (handle both hyphen and en dash)
            # Some models use en dash (–) instead of hyphen (-)
            separator = '–' if '–' in result else '-'
            parts = result.split(separator, 1)
            mode = parts[0].strip().lower()
            reasoning = parts[1].strip() if len(parts) > 1 else "Mode detection"

            # Validate mode
            valid_modes = ['navigation', 'focus', 'compare', 'uncertain']
            if mode not in valid_modes:
                # Invalid response, treat as uncertain
                mode = 'uncertain'
                reasoning = f"Invalid mode detection response: {result}"

            logger.info(f"Mode detection: {mode} - {reasoning}")
            return mode, reasoning

        except Exception as e:
            logger.error(f"Error in mode detection: {e}", exc_info=True)
            # Fallback to current mode on error
            return current_mode, f"Mode detection error: {str(e)}"

# Session 76: Removed handle_navigation_mode() and _process_single_operation()
    # Now using pure function calling for all modes - no structured outputs translation needed

    def route_message(
        self,
        message: str,
        conversation_history: Optional[List[Dict]] = None,
        context: Optional[Dict] = None,
        mode: str = 'focus',
        serialized_context: str = '',
        model_override: Optional[str] = None
    ) -> Dict:
        """
        Route a user message to appropriate function or conversational response.

        Session 76: Pure function-calling architecture - all modes use function calling.
        Mode detection still used for system prompt customization.

        Args:
            message: User's chat message
            conversation_history: Previous messages in conversation (list of {"role": str, "content": str})
            context: Current UI context (current artifact, jurisdiction, etc.)
            mode: Chat mode suggestion ('navigation', 'focus', 'compare')
            serialized_context: LLM-friendly context summary from open artifacts

        Returns:
            {
                "action": "search_events" | "file_complaint" | "respond" | ...,
                "parameters": {...},  # If action requires params
                "message": "...",     # If conversational response
                "reasoning": "...",   # LLM's explanation of action
                "mode": str,          # Detected mode (may differ from input)
                "mode_changed": bool, # True if mode switched
                "mode_reason": str,   # Explanation for mode choice
                "usage": {            # Token usage metrics
                    "prompt_tokens": int,
                    "completion_tokens": int,
                    "total_tokens": int
                }
            }
        """
        # Session 56/76: Detect optimal mode for system prompt selection
        detected_mode, mode_reason = self.detect_mode(
            message=message,
            current_mode=mode,
            context_summary=serialized_context,
            conversation_history=conversation_history
        )

        # CRITICAL: If uncertain, ask the user instead of guessing
        if detected_mode == 'uncertain':
            return {
                'action': 'respond',
                'message': (
                    'I can help you in a few ways:\n\n'
                    '🔍 **Search** for civic content (events, bills, programs)\n'
                    '🔎 **Understand** this item in detail\n'
                    '⚖️ **Compare** multiple items side-by-side\n\n'
                    'What would you like to do?'
                ),
                'mode': mode,  # Stay in current mode
                'mode_changed': False,
                'mode_reason': mode_reason
            }

        # Use detected mode (may differ from suggested mode)
        effective_mode = detected_mode

        messages = list(conversation_history) if conversation_history else []

        # Session 76: Build mode-specific system prompt
        if not messages or messages[0].get("role") != "system":
            # Get mode-specific system prompt
            mode_specific_prompt = MODE_SYSTEM_PROMPTS.get(effective_mode, MODE_SYSTEM_PROMPTS['navigation'])
            # Combine with base system prompt
            full_system_prompt = SYSTEM_PROMPT + "\n\n" + mode_specific_prompt
            messages.insert(0, {"role": "system", "content": full_system_prompt})

        # Session 55: Add serialized multi-artifact context if provided
        if serialized_context:
            context_msg = f"""## User's Current Context

{serialized_context}

**CRITICAL**: The user is currently viewing these artifacts. The context above includes IDs (Event ID, Program ID, Issue ID, etc.) for each artifact.

**When the user asks about "this meeting", "this event", "this bill", etc., they are referring to the artifact(s) in the context above. You ALREADY HAVE the IDs - do NOT ask for them!**

**Answer directly from context when:**
- Simple questions: "What's this about?", "When is this?", "What topics are covered?", "Explain this meeting"
- General overview: "Summarize this meeting", "What's the main focus?", "Give me a TLDR"
- Explanations: "What do you think item X is about?", "Explain this agenda item"
  → Use your general knowledge to infer what items mean based on their titles
- The context contains sufficient information to answer

**Call explain_event function when:**
- User asks for FORMATTED list: "Show me the agenda items", "List each item"
  → To display structured, formatted agenda with checkmarks
  → Extract the Event ID from the context above (e.g., "Event ID: 585ce4ff-...") and pass it as the event_id parameter
- User wants participation details: "How do I comment?", "What's the deadline?"
  → Extract the Event ID from context and pass it to the function
- The summary doesn't contain enough detail to answer fully

**NEVER call explain_event when:**
- You just called it in the previous message (check conversation history!)
- User asks for explanations/reasoning: "what do these mean?", "explain item X"
  → Use your general knowledge to explain civic concepts directly

**Call other functions when:**
- Searching for NEW content: search_events, view_legislative_context
- Taking actions: file_complaint, draft_comment
- Opening different artifacts

**CRITICAL RULE**: If you need to call a function that requires an ID (event_id, program_id, etc.), extract it from the context above. NEVER ask the user for an ID that's already in the context."""
            # Insert after system prompt
            messages.insert(1, {"role": "system", "content": context_msg})

        # Add legacy UI context if provided (backward compatibility)
        if context:
            context_parts = []
            if context.get("user_city"):
                context_parts.append(f"User's city: {context['user_city']}")
            if context.get("current_jurisdiction"):
                context_parts.append(f"Currently viewing: {context['current_jurisdiction']}")
            if context.get("current_event"):
                context_parts.append(f"Currently viewing event: {context['current_event']}")

            if context_parts:
                legacy_context_msg = "\n## Additional UI Context\n" + "\n".join(f"- {part}" for part in context_parts)
                # Insert after serialized context (or after system prompt if no serialized context)
                insert_pos = 2 if serialized_context else 1
                messages.insert(insert_pos, {"role": "system", "content": legacy_context_msg})

        # Add user message
        messages.append({"role": "user", "content": message})

        # Session 77: Detect OR/AND queries → use structured query planning
        or_and_patterns = [
            r'\b(?:or|OR)\b',  # "housing OR transportation"
            r'\b(?:and|AND)\b',  # "housing AND transportation"
            r',\s*(?:and\s+)?',  # "housing, transportation"
        ]

        uses_boolean_logic = any(re.search(pattern, message) for pattern in or_and_patterns)

        if uses_boolean_logic:
            logger.info(f"Detected OR/AND query - using structured query planning")

            try:
                # Parse to QueryPlan
                query_plan = parse_query_to_plan(
                    message=message,
                    context=context,
                    conversation_history=conversation_history
                )

                # If multiple operations, return multi-operation response
                if len(query_plan.operations) > 1:
                    logger.info(f"Multi-operation query: {len(query_plan.operations)} operations")

                    # Convert operations to response format
                    all_operations = []
                    for op in query_plan.operations:
                        operation_dict = {
                            "action": op.type,
                            "parameters": {}
                        }

                        if op.filters:
                            operation_dict["parameters"] = op.filters.model_dump(exclude_none=True)
                        elif op.complaint_data:
                            operation_dict["parameters"] = op.complaint_data.model_dump(exclude_none=True)
                        elif op.message:
                            operation_dict["message"] = op.message

                        all_operations.append(operation_dict)

                    return {
                        "action": "multi_operation",
                        "multi_operation": True,
                        "operation_count": len(all_operations),
                        "all_operations": all_operations,
                        "reasoning": f"Executing {len(all_operations)} searches for OR query",
                        "mode": effective_mode,
                        "mode_changed": effective_mode != mode,
                        "mode_reason": mode_reason,
                        "provider_used": "gemini",  # query_planning task uses Gemini Flash
                        "model_used": "gemini-2.0-flash-exp",
                        "usage": {
                            "prompt_tokens": 0,  # TODO: Track from Instructor
                            "completion_tokens": 0,
                            "total_tokens": 0
                        }
                    }
                else:
                    # Single operation - continue to regular function calling for consistency
                    logger.info("Query planning returned single operation - using regular function calling")

            except Exception as e:
                logger.error(f"Query planning failed, falling back to function calling: {e}")
                # Fall through to regular function calling

        # Session 62: Pre-processing filter for complaint filing (verb usage)
        filing_patterns = [
            r'\b(report|file|submit)\s+(a|an)\s+\w+',  # "report a pothole"
            r'\b(want to|need to|like to|going to)\s+(report|file|submit)',  # "I want to report"
            r'^\s*(report|file|submit)\b',  # Starts with action verb
        ]

        if any(re.search(pattern, message, re.I) for pattern in filing_patterns):
            search_indicators = [r'\bshow\b', r'\bfind\b', r'\bsee\b', r'\bview\b', r'\blist\b']
            is_search_query = any(re.search(indicator, message, re.I) for indicator in search_indicators)

            if not is_search_query:
                logger.info(f"Pre-filter detected complaint filing query - forcing file_complaint")

                parameters = {}
                match = re.search(r'\b(report|file|submit)\s+(a|an)\s+([^,.;]+)', message, re.I)
                if match:
                    parameters['title'] = match.group(3).strip()

                return {
                    "action": "file_complaint",
                    "parameters": parameters,
                    "reasoning": "Opening complaint form",
                    "mode": effective_mode,
                    "mode_changed": effective_mode != mode,
                    "mode_reason": mode_reason,
                    "provider_used": "pre-filter",
                    "model_used": "regex",
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                }

        # Session 62: Pre-processing filters for user-owned content
        # Pattern 1: "issues I'm following" / "issues I follow"
        # Pattern 2: "my" + complaint-word
        # More reliable than relying on OpenAI function descriptions
        is_following_query = re.search(r'\b(complaint|report|issue|submission)s?\b.*\b(I\'m following|I follow|following)\b', message, re.I)
        is_my_query = re.search(r'\bmy\b.*\b(complaint|report|issue|submission)', message, re.I)

        # Session 63: Track if we should force a specific function
        force_function = None
        if is_following_query or is_my_query:
            logger.info(f"Pre-filter detected 'my complaints' query - forcing view_my_complaints via LLM")
            force_function = "view_my_complaints"
            # Don't parse parameters with regex - let LLM handle it cleanly!

        try:
            logger.info(f"Routing message: {message[:100]}...")

            # Session 88: Use model_override if provided, otherwise auto-select based on task
            if model_override:
                logger.info(f"Using manual model override: {model_override}")
                from llm_provider import get_model
                provider = get_model(model_override)
            else:
                # Select task based on mode for optimal model selection
                task_map = {
                    'navigation': 'navigation',  # Use navigation task (cheap, fast)
                    'focus': 'explain',  # Use explain task (better at context awareness)
                    'compare': 'explain'  # Use explain task (analytical)
                }
                task = task_map.get(effective_mode, 'navigation')

                logger.info(f"Using task '{task}' for mode '{effective_mode}' (auto-routing)")
                provider = get_model_for_task(task)

            # Extract provider metadata BEFORE making the call
            provider_name = provider.name
            model_name = provider.default_model

            # Session 63: Force specific function if pre-filter detected it
            tool_choice = {"type": "function", "function": {"name": force_function}} if force_function else "auto"

            response = provider.complete(
                messages=messages,
                tools=CIVICOS_FUNCTIONS,
                tool_choice=tool_choice,
                temperature=0.7
            )

            # Session 507: Log cost for main routing call
            if response.usage:
                log_llm_cost(
                    model=model_name,
                    usage=response.usage,
                    provider=provider_name,
                    task=f'routing_{effective_mode}',
                )

            # Check if model wants to call a function
            if response.tool_calls and len(response.tool_calls) > 0:
                # Session 77: Log ALL tool calls to detect multi-operation queries
                logger.info(f"{provider_name} returned {len(response.tool_calls)} tool call(s)")
                for i, tc in enumerate(response.tool_calls):
                    logger.info(f"  Tool call {i+1}: {tc.name}({tc.arguments})")

                # TEMPORARY: Only process first call (will fix in Session 77)
                tool_call = response.tool_calls[0]

                logger.info(f"{provider_name} function routing: {tool_call.name}")
                logger.info(f"Function arguments: {tool_call.arguments}")
                logger.debug(f"Available functions: {[f['name'] for f in CIVICOS_FUNCTIONS]}")

                # Session 75: Handle search_web inline - execute search and return result
                if tool_call.name == 'search_web':
                    query = tool_call.arguments.get('query', '')
                    logger.info(f"Executing web search for: {query}")

                    try:
                        # Use Perplexity for real-time research
                        search_provider = get_model_for_task('realtime_research')

                        search_response = search_provider.complete(
                            messages=[{"role": "user", "content": query}],
                            max_tokens=1000,
                            temperature=0.7
                        )

                        search_result = search_response.content
                        search_usage = search_response.usage or {}

                        # Session 507: Log cost for web search
                        if search_usage:
                            log_llm_cost(
                                model=search_provider.default_model,
                                usage=search_usage,
                                provider=search_provider.name,
                                task='web_search',
                            )

                        logger.info(f"Web search completed: {len(search_result)} chars")

                        # For web search, just show the search model since that's what generates the response
                        # The navigation model just routes to search_web function
                        return {
                            "action": "respond",
                            "message": search_result,
                            "mode": effective_mode,
                            "mode_changed": effective_mode != mode,
                            "mode_reason": mode_reason,
                            "provider_used": search_provider.name,
                            "model_used": search_provider.default_model,  # Just show the search model
                            "usage": {
                                "prompt_tokens": response.usage.get('prompt_tokens', 0) + search_usage.get('prompt_tokens', 0),
                                "completion_tokens": response.usage.get('completion_tokens', 0) + search_usage.get('completion_tokens', 0),
                                "total_tokens": response.usage.get('total_tokens', 0) + search_usage.get('total_tokens', 0)
                            }
                        }
                    except Exception as e:
                        logger.error(f"Web search error: {e}", exc_info=True)
                        return {
                            "action": "respond",
                            "message": f"I encountered an error searching the web: {str(e)}. Please try rephrasing your question.",
                            "mode": effective_mode,
                            "mode_changed": effective_mode != mode,
                            "mode_reason": mode_reason,
                            "error": str(e)
                        }

                # Session 71/76: Normalize topic and jurisdiction parameters if present
                parameters = tool_call.arguments
                if tool_call.name == 'search_events':
                    # Normalize topic
                    if 'topic' in parameters:
                        original_topic = parameters['topic']
                        parameters['topic'] = normalize_topic(original_topic)
                        if original_topic != parameters['topic']:
                            logger.info(f"Topic normalized for search: '{original_topic}' → '{parameters['topic']}'")

                    # Normalize jurisdiction (Session 76 fix: was missing after pure function-calling refactor!)
                    if 'jurisdiction' in parameters:
                        original_jurisdiction = parameters['jurisdiction']
                        parameters['jurisdiction'] = normalize_jurisdiction(original_jurisdiction)
                        if original_jurisdiction != parameters['jurisdiction']:
                            logger.info(f"Jurisdiction normalized for search: '{original_jurisdiction}' → '{parameters['jurisdiction']}'")

                return {
                    "action": tool_call.name,
                    "parameters": parameters,  # Use normalized parameters
                    "reasoning": response.content or f"I'll help you with that.",
                    "mode": effective_mode,
                    "mode_changed": effective_mode != mode,
                    "mode_reason": mode_reason,
                    "provider_used": provider_name,
                    "model_used": model_name,
                    "usage": {
                        "prompt_tokens": response.usage.get('prompt_tokens', 0),
                        "completion_tokens": response.usage.get('completion_tokens', 0),
                        "total_tokens": response.usage.get('total_tokens', 0)
                    }
                }
            else:
                # Conversational response
                logger.info("Conversational response")

                return {
                    "action": "respond",
                    "message": response.content,
                    "mode": effective_mode,
                    "mode_changed": effective_mode != mode,
                    "mode_reason": mode_reason,
                    "provider_used": provider_name,
                    "model_used": model_name,
                    "usage": {
                        "prompt_tokens": response.usage.get('prompt_tokens', 0),
                        "completion_tokens": response.usage.get('completion_tokens', 0),
                        "total_tokens": response.usage.get('total_tokens', 0)
                    }
                }

        except Exception as e:
            logger.error(f"Error routing message: {e}", exc_info=True)

            # Fallback to conversational response on error
            return {
                "action": "respond",
                "message": "I'm sorry, I encountered an error processing your request. Please try rephrasing or contact support if this persists.",
                "mode": mode,  # Keep current mode on error
                "mode_changed": False,
                "mode_reason": "Error occurred",
                "error": str(e)
            }


# Singleton instance
_router_instance = None


def get_router() -> ChatRouter:
    """Get or create singleton ChatRouter instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = ChatRouter()
    return _router_instance
