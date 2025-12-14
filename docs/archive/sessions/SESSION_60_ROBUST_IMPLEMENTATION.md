# Session 60: Robust Implementation Guide

**Date**: 2025-11-03
**Approach**: Zero Hard-Coded Hacks
**Estimate**: 8 hours (5 phases)

---

## 🎯 Design Principles

**Zero Hard-Coded Hacks**: All normalization handled by LLM or auto-generated from configuration.

### Key Decisions

1. **No JURISDICTION_MAPPINGS dictionary** - LLM normalizes using auto-generated reference from `CITY_CONFIGS`
2. **Structured clarify operations** - Use `{id, display}` objects instead of string matching
3. **Self-maintaining** - System updates automatically when cities are added/removed

### Benefits Over Hard-Coded Approach

| Aspect | Hard-Coded | Robust (LLM-Based) |
|--------|-----------|-------------------|
| Maintainability | ❌ Manual updates | ✅ Auto-updates |
| Extensibility | ❌ Code changes | ✅ Config changes |
| Typo handling | ❌ Fails | ✅ Intelligent matching |
| Alias support | ❌ Manual entries | ✅ Contextual inference |
| Implementation time | 6h | 8h (+33%) |
| Long-term cost | High (tech debt) | Low (zero debt) |
| Monthly cost | $0.35 | $0.40 (+14%) |

**Decision**: +2 hours and +$0.05/month is worth it for zero technical debt.

---

## 📋 Implementation Phases

### Phase 1: Backend Multi-Jurisdiction Support (~2 hours)

**No changes from original proposal** - See `CHAT_ROUTING_ARCHITECTURE.md` Phase 1

---

### Phase 2A: LLM-Based Jurisdiction Normalization (~2 hours)

**Goal**: Eliminate hard-coded JURISDICTION_MAPPINGS dictionary (50+ entries).

#### Step 1: Delete JURISDICTION_MAPPINGS

**File**: `src/civic_chat_router.py`

**Delete lines 18-67**:
```python
# DELETE THIS ENTIRE SECTION
JURISDICTION_MAPPINGS = {
    "berkeley": "city-berkeley",
    "oakland": "city-oakland",
    # ... 50+ entries ...
}
```

#### Step 2: Create Dynamic System Prompt Generator

**File**: `src/civic_chat_router.py`

**Add before NAVIGATION_SYSTEM_PROMPT** (around line 399):

```python
def get_navigation_system_prompt() -> str:
    """
    Generate navigation system prompt with dynamic jurisdiction reference.

    Auto-generates from CITY_CONFIGS so new cities work immediately.
    Handles typos, aliases, and variations via LLM intelligence.
    """
    from automated_civic_refresh import CITY_CONFIGS

    # Auto-generate jurisdiction reference
    jurisdiction_lines = []
    for city_name, config in sorted(CITY_CONFIGS.items()):
        jurisdiction_id = config['jurisdiction_id']
        # Show city name → jurisdiction_id mapping
        jurisdiction_lines.append(f'  - "{city_name}" → "{jurisdiction_id}"')

    jurisdiction_reference = "\n".join(jurisdiction_lines)

    return f"""You are a navigation parser for civic engagement.

Your ONLY job: Parse user queries into structured backend operations.

JURISDICTION NORMALIZATION:
When user mentions a jurisdiction, output the normalized jurisdiction_id from this list:

{jurisdiction_reference}

SPECIAL VALUES:
  - "all" → searches ALL configured jurisdictions above
  - User says "all bay area", "everywhere", "all cities" → output "all"

COMMON ALIASES (use your intelligence):
  - "SF" → "city-san-francisco"
  - "The Town" → "city-oakland"
  - "Berk" → "city-berkeley"

TYPO HANDLING:
  - Use closest match from list above
  - Example: "Berkely" → "city-berkeley"
  - Example: "Oaklnd" → "city-oakland"

UNKNOWN JURISDICTIONS:
  - If user mentions city NOT in list, use pattern: "city-{{lowercase-hyphenated}}"
  - Example: "Palo Alto" → "city-palo-alto"

CRITICAL: Never use hard-coded mappings. Infer from this reference list and context.

MULTI-OPERATION SUPPORT (Session 57.5):
- Use operations array with 1 item for simple queries: "Find housing in Berkeley"
- Use operations array with 2+ items for OR queries: "Find housing in Berkeley OR transportation in Concord"
- Each operation in the array is completely independent with its own filters
- Maximum 5 operations per query

CRITICAL: Set unused fields to null for each operation.

[... rest of system prompt from original NAVIGATION_SYSTEM_PROMPT ...]
"""
```

#### Step 3: Replace Static Prompt with Dynamic Function

**File**: `src/civic_chat_router.py`

**Replace** (around line 399-613):
```python
# OLD:
NAVIGATION_SYSTEM_PROMPT = """You are a navigation parser..."""

# NEW:
# Generate dynamic prompt (called once at module load)
NAVIGATION_SYSTEM_PROMPT = get_navigation_system_prompt()
```

#### Step 4: Simplify normalize_jurisdiction Function

**File**: `src/civic_chat_router.py`

**Replace** (lines 70-99):
```python
def normalize_jurisdiction(llm_jurisdiction: str) -> str:
    """
    Minimal normalization - LLM already handles this via dynamic system prompt.

    Just ensure consistent format:
    - Lowercase
    - Hyphenate spaces
    - Prepend "city-" if needed

    Args:
        llm_jurisdiction: Already-normalized jurisdiction from LLM

    Returns:
        Final jurisdiction ID for database queries

    Examples:
        "all" → "all"
        "city-berkeley" → "city-berkeley"
        "berkeley" → "city-berkeley" (adds prefix)
    """
    # Handle special case
    if llm_jurisdiction.lower() in ['all', 'everywhere']:
        return 'all'

    # LLM should output correct format, but ensure consistency
    normalized = llm_jurisdiction.lower().strip()

    # If LLM forgot "city-" prefix, add it (unless county/special district)
    if not normalized.startswith('city-') and not normalized.endswith('-county') and normalized != 'bart':
        normalized = f'city-{normalized}'

    return normalized
```

#### Step 5: Update _process_single_operation

**File**: `src/civic_chat_router.py`

**Replace** (lines 890-930):
```python
if op_type == 'search_events':
    filters = operation.get('filters', {})
    jurisdiction = filters.get('jurisdiction')

    # NEW: Allow "all" as valid jurisdiction, default to "all" if not specified
    if not jurisdiction:
        jurisdiction = 'all'

    # Minimal normalization (LLM already did the heavy lifting)
    normalized_jurisdiction = normalize_jurisdiction(jurisdiction)
    logger.info(f"Normalized jurisdiction: '{jurisdiction}' → '{normalized_jurisdiction}'")

    # Session 57: Normalize topic to canonical project_type
    topic = filters.get('topic')
    normalized_topic = normalize_topic(topic) if topic else None
    if topic and normalized_topic != topic:
        logger.info(f"Normalized topic: '{topic}' → '{normalized_topic}'")

    return {
        'action': 'search_events',
        'parameters': {
            'jurisdiction': normalized_jurisdiction,
            'topic': normalized_topic,
            'date_range': filters.get('dateRange'),
            'query': filters.get('searchQuery')
        },
        'reasoning': f"Searching for events in {normalized_jurisdiction}",
        'usage': {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
    }
```

**Testing**:
```bash
# Test that LLM normalizes correctly
python -c "
from civic_chat_router import get_router
router = get_router()

# Test typo handling
result = router.handle_navigation_mode('Show meetings in Berkely', {})  # Typo
assert result['parameters']['jurisdiction'] == 'city-berkeley'

# Test alias
result = router.handle_navigation_mode('Show meetings in SF', {})
assert result['parameters']['jurisdiction'] == 'city-san-francisco'

# Test 'all'
result = router.handle_navigation_mode('Show meetings everywhere', {})
assert result['parameters']['jurisdiction'] == 'all'

print('✅ All LLM normalization tests passed')
"
```

---

### Phase 2B: Structured Clarify Operations (~1 hour)

**Goal**: Eliminate hard-coded option mappings via structured `{id, display}` objects.

#### Step 1: Update NAVIGATION_SCHEMA

**File**: `src/civic_chat_router.py`

**Replace** (lines 324-397):
```python
NAVIGATION_SCHEMA = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "description": "Array of operations to perform...",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["search_events", "search_legislation", "navigate", "clarify"],
                        "description": "Type of operation"
                    },
                    "filters": {
                        "type": ["object", "null"],
                        # ... existing filter properties ...
                    },
                    "target": {
                        "type": ["object", "null"],
                        # ... existing target properties ...
                    },
                    "question": {
                        "type": ["string", "null"],
                        "description": "Question for clarify operation"
                    },
                    "options": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",  # CHANGED from string to object
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Backend value (e.g., 'city-berkeley', 'all')"
                                },
                                "display": {
                                    "type": "string",
                                    "description": "User-facing text (e.g., 'Berkeley', 'All Bay Area cities')"
                                }
                            },
                            "required": ["id", "display"]
                        },
                        "description": "Structured options for clarify operation"
                    }
                },
                "required": ["type"],
                "additionalProperties": False
            }
        }
    },
    "required": ["operations"],
    "additionalProperties": False
}
```

#### Step 2: Update System Prompt for Structured Clarify

**File**: `src/civic_chat_router.py`

**Add to get_navigation_system_prompt()** (around clarify operation section):
```python
clarify (asking user for clarification):
- filters: null
- target: null
- question: MUST be a string (never null!)
- options: MUST be an array of objects with 'id' and 'display' fields (2-4 options)

  Example for jurisdiction clarification:
  {{
    "type": "clarify",
    "filters": null,
    "target": null,
    "question": "Which city's meetings would you like to see?",
    "options": [
      {{"id": "city-berkeley", "display": "Berkeley"}},
      {{"id": "city-oakland", "display": "Oakland"}},
      {{"id": "city-san-francisco", "display": "San Francisco"}},
      {{"id": "all", "display": "All Bay Area cities"}}
    ]
  }}

  CRITICAL:
  - 'id' = exact value to use in search_events filter (e.g., "city-berkeley", "all")
  - 'display' = user-friendly text to show in UI (e.g., "Berkeley", "All Bay Area cities")
  - This allows robust follow-up mapping (user says "all bay area" → maps to id="all")
  - Use jurisdiction_ids from the list above for option IDs
```

#### Step 3: Update Clarify Processing

**File**: `src/civic_chat_router.py`

**Replace** (_process_single_operation clarify section, lines 998-1033):
```python
elif op_type == 'clarify':
    question = operation.get('question')
    options = operation.get('options')

    # Validate structured options
    if not options or not isinstance(options, list):
        logger.error(f"clarify missing/invalid options: {operation}")
        return {
            'action': 'respond',
            'message': question or "I need more information.",
            'error': 'Missing required field: options'
        }

    # Validate option structure
    for opt in options:
        if not isinstance(opt, dict) or 'id' not in opt or 'display' not in opt:
            logger.error(f"clarify has malformed option: {opt}")
            return {
                'action': 'respond',
                'message': question or "I need more information.",
                'error': 'Malformed option (missing id or display)'
            }

    # Format options for display
    option_display = "\n".join([f"- {opt['display']}" for opt in options])

    # Return clarification with structured options
    return {
        'action': 'respond',
        'message': f"{question}\n\nOptions:\n{option_display}",
        'clarify': {
            'question': question,
            'options': options  # Preserve structured format [{id, display}, ...]
        },
        'reasoning': 'Requesting clarification from user',
        'usage': {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
    }
```

**Testing**:
```bash
# Test structured clarify
python -c "
from civic_chat_router import get_router
router = get_router()

# Test clarify generates structured options
result = router.handle_navigation_mode('Show meetings', {})  # No jurisdiction
assert result.get('clarify') is not None
assert isinstance(result['clarify']['options'], list)
assert 'id' in result['clarify']['options'][0]
assert 'display' in result['clarify']['options'][0]

print('✅ Structured clarify test passed')
"
```

---

### Phase 2C: Frontend Search Integration (~1 hour)

**Goal**: Always call backend `/api/events/search` endpoint. Eliminate two-path logic.

#### Step 1: Simplify handleSearchEvents

**File**: `frontend/civic-workspace/src/components/chat/ChatPanel.vue`

**Replace** (lines 518-599):
```typescript
async function handleSearchEvents(params: any) {
  console.log('[ChatPanel] Search events:', params)

  // Check if user has set their location (unless searching "all")
  if (!userStore.hasLocation && params.jurisdiction !== 'all') {
    chatStore.addMessage({
      role: 'assistant',
      content: `📍 **Location Required**\n\nTo show you civic meetings in your area, I need to know where you're located.\n\nPlease enter your address in the location prompt to get started. Your full address is never stored—we only keep your city and county.`
    })
    return
  }

  // Show workspace if in chat-first mode
  if (workspaceStore.viewMode === 'chat-first' && !workspaceStore.workspaceVisible) {
    workspaceStore.toggleWorkspaceVisibility()
  }

  // Expand Events section in sidebar
  sidebarStore.expandSectionExclusive('events')
  triggerSectionPulse('events')  // Session 59: Visual feedback

  // NEW: Always call backend search API (unified path - eliminates queryClassifier)
  try {
    const searchParams = {
      jurisdiction: params.jurisdiction || 'all',  // Default to 'all'
      topic: params.topic,
      query: params.query,  // Keyword search
      dateRange: params.date_range
    }

    console.log('[ChatPanel] Calling backend search:', searchParams)
    const results = await api.searchEvents(searchParams)

    // Update workspace based on result scope
    if (results.jurisdictions_searched.length === 1) {
      // Single jurisdiction → apply filters to EventsPanel (existing UX)
      const eventsPanel = eventsPanelRef?.value
      if (eventsPanel && 'applyFilters' in eventsPanel) {
        eventsPanel.applyFilters({
          topic: params.topic,
          dateRange: params.date_range,
          searchQuery: params.query
        })

        // Session 59: Trigger filter highlight if topic filter applied
        if (params.topic) {
          triggerFilterHighlight('events', 'topic')
        }
      }

      chatStore.addMessage({
        role: 'assistant',
        content: `Found **${results.count} events** in ${results.jurisdictions_searched[0]}.`
      })
    } else {
      // Multi-jurisdiction → create workspace tabs (Session 59+)
      // TODO: Implement createMultiJurisdictionWorkspace in Phase 4
      console.log('[ChatPanel] Multi-jurisdiction results:', results)

      chatStore.addMessage({
        role: 'assistant',
        content: `Found **${results.count} events** across **${results.jurisdictions_searched.length} jurisdictions**.`
      })
    }
  } catch (error) {
    console.error('[ChatPanel] Search error:', error)
    chatStore.addMessage({
      role: 'assistant',
      content: `I encountered an error searching for events. Please try again.`
    })
  }
}
```

#### Step 2: Remove queryClassifier (Optional Cleanup)

**File**: `frontend/civic-workspace/src/services/queryClassifier.ts`

**Action**: Delete file (no longer needed)

**File**: `frontend/civic-workspace/src/components/chat/ChatPanel.vue`

**Action**: Remove import:
```typescript
// DELETE:
import { classifySearchQuery, formatQueryDescription, type ClassifiedQuery } from '../../services/queryClassifier'
```

---

### Phase 3: Conversation Context Enhancement (~1 hour)

**Goal**: Preserve structured clarify operations for robust follow-up handling.

#### Step 1: Update Conversation History Storage

**File**: `src/civic_api_integrated.py`

**Replace** (lines 5428-5444):
```python
# Update conversation history
assistant_message = {"role": "assistant"}

if result.get('clarify'):
    # NEW: Preserve structured clarify details for follow-up context
    assistant_message['content'] = result.get('message', '')
    assistant_message['clarify'] = result['clarify']  # Structured {question, options[{id, display}]}
elif result['action'] != 'respond':
    # Function call - preserve OpenAI function_call format
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
```

#### Step 2: Update Context String Builder

**File**: `src/civic_chat_router.py`

**Replace** (lines 778-796 in handle_navigation_mode):
```python
# Build context string for LLM
user_jurisdiction = context.get('user_city', 'unknown') if context else 'unknown'
context_str = f"User's registered city: {user_jurisdiction}"

# Add conversation context for follow-up queries
if conversation_history and len(conversation_history) >= 2:
    # Get last 2 messages for context
    recent = conversation_history[-2:]
    context_str += f"\n\nRecent conversation:\n"
    for msg in recent:
        if msg.get('clarify'):
            # NEW: Show structured clarify options for follow-up inference
            clarify = msg['clarify']
            options_formatted = "\n".join([
                f"    - id=\"{opt['id']}\", display=\"{opt['display']}\""
                for opt in clarify['options']
            ])
            context_str += f"{msg['role']}: [Asked clarification]\n"
            context_str += f"  Question: {clarify['question']}\n"
            context_str += f"  Options:\n{options_formatted}\n"
            context_str += f"  CRITICAL: If user's next message is a response, map it to option.id using semantic similarity\n"
            context_str += f"  Example: User says 'all bay area' → maps to id='all' (from 'All Bay Area cities' option)\n"
        elif msg.get('function_call'):
            # For function calls, show the function name AND arguments
            func_name = msg['function_call'].get('name', 'unknown')
            func_args_str = msg['function_call'].get('arguments', '{}')
            try:
                func_args = json.loads(func_args_str)
                context_str += f"{msg['role']}: [Called {func_name} with jurisdiction={func_args.get('jurisdiction')}, topic={func_args.get('topic')}]\n"
            except:
                context_str += f"{msg['role']}: [Called {func_name}]\n"
        else:
            content = msg.get('content') or ''
            context_str += f"{msg['role']}: {content[:100]}...\n" if content else f"{msg['role']}: [no content]\n"
```

#### Step 3: Add Follow-Up Inference to System Prompt

**File**: `src/civic_chat_router.py`

**Add to get_navigation_system_prompt()** (after CONTEXT-AWARE INFERENCE section):
```python
FOLLOW-UP CONTEXT INFERENCE (Session 60 - Robust):
When previous assistant message was clarify operation, user's response is selecting an option.

CRITICAL RULES:
1. Check if conversation context shows clarify with structured options
2. Map user response to option.id (NOT display text)
3. Use semantic similarity - handle typos, case variations, paraphrases

Example:
  Assistant asked: "Which city?" with structured options:
    - {id: "city-berkeley", display: "Berkeley"}
    - {id: "all", display: "All Bay Area cities"}

  User says: "all bay area" (lowercase, slight variation)
  You MUST: Create search_events operation with jurisdiction="all" (mapped from option.id)

  User says: "berkeley"
  You MUST: Create search_events operation with jurisdiction="city-berkeley"

  User says: "berk" (abbreviated)
  You MUST: Fuzzy match to "city-berkeley" (closest option)

Use your intelligence to match user response to option.id (NOT display text).
DO NOT repeat clarification if user's response semantically matches an option.
```

**Testing**:
```bash
# Test follow-up mapping
python -c "
from civic_chat_router import get_router

router = get_router()

# Simulate conversation with clarify
conversation = [
    {'role': 'user', 'content': 'Show meetings'},
    {
        'role': 'assistant',
        'content': 'Which city?',
        'clarify': {
            'question': 'Which city?',
            'options': [
                {'id': 'city-berkeley', 'display': 'Berkeley'},
                {'id': 'all', 'display': 'All Bay Area cities'}
            ]
        }
    }
]

# Test follow-up: User says 'all bay area' (lowercase variation)
result = router.handle_navigation_mode(
    message='all bay area',
    context={},
    conversation_history=conversation
)

# Should map to jurisdiction='all'
assert result['action'] == 'search_events'
assert result['parameters']['jurisdiction'] == 'all'
print('✅ Follow-up mapping test passed')
"
```

---

### Phase 4: UI Enhancement (~1 hour)

**No changes from original proposal** - See `CHAT_ROUTING_ARCHITECTURE.md` Phase 4

---

## ✅ Success Criteria

| Metric | Test | Expected |
|--------|------|----------|
| Zero hard-coded mappings | Count JURISDICTION_MAPPINGS references | 0 |
| LLM handles typos | "Berkely" → events | ✅ Returns city-berkeley events |
| LLM handles aliases | "SF" → events | ✅ Returns city-san-francisco events |
| Structured clarify | Check clarify response | ✅ Has {id, display} objects |
| Follow-up mapping | "all bay area" after clarify | ✅ Maps to jurisdiction='all' |
| Backend search | Monitor chat queries | ✅ 100% hit /api/events/search |
| No repeated clarifications | Follow-up flow test | ✅ <5% repeat rate |

---

## 📊 Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM hallucinates jurisdictions | Structured outputs schema enforces valid operations |
| Cost increase from longer prompt | +$0.05/month is negligible vs. tech debt |
| Implementation takes longer | +2 hours investment prevents future refactoring |
| Breaking changes | Comprehensive test suite + staged rollout |

---

## 🚀 Deployment Strategy

### Session 60 (5 hours)
1. Phase 1: Backend multi-jurisdiction (2h)
2. Phase 2A: LLM normalization (2h)
3. Phase 2B: Structured clarify (1h)

**Test**: Multi-jurisdiction queries, typo handling, clarify follow-ups

### Session 61 (3 hours)
1. Phase 2C: Frontend integration (1h)
2. Phase 3: Context enhancement (1h)
3. Phase 4: UI polish (1h)

**Test**: End-to-end flows, UI grouping, performance

### Rollout
- Deploy to staging
- Run manual test suite (see Success Criteria)
- Monitor for 24h
- Deploy to production

---

## 📚 Related Documentation

- `CHAT_ROUTING_ARCHITECTURE.md` - Complete architecture (updated with robust approach)
- `next_session_prompt.md` - Session 60 quick start
- `CHAT_STRATEGY_ROADMAP.md` - Long-term vision

---

**Last Updated**: 2025-11-03
**Status**: Ready for implementation ✅
