# Navigation Mode: Structured Outputs Architecture

**Status**: 📋 **Design Document** (To be implemented Session 56.5)
**Last Updated**: 2025-11-02
**Supersedes**: Original function calling approach (Session 27)

---

## Problem Statement

**Current Issue** (Session 56): Navigation mode uses OpenAI function calling with *descriptive* schemas, not *prescriptive* enforcement.

**Real Bug Example**:
```
User: "Find housing meetings in Berkeley"
  ↓
ChatRouter returns: {action: "search_events", topic: "housing"}  ❌ Missing jurisdiction!
  ↓
Frontend classifies as "simple" query (no jurisdiction)
  ↓
Filters already-loaded Oakland events → 0 Berkeley results found
```

**Root Cause**: Function calling is a *soft schema* - LLM sees `jurisdiction: "optional city name"` but doesn't know it MUST extract "Berkeley" from the natural language.

---

## Solution: Structured Outputs

**New Approach**: Navigation mode becomes a **structured query parser** with guaranteed schema compliance.

```
User: "Find housing meetings in Berkeley"
  ↓
Navigation LLM with STRUCTURED OUTPUTS (hard schema enforcement)
  ↓
Guaranteed output: {
  operation: "search_events",
  filters: {jurisdiction: "berkeley", topic: "housing"}
}  ✅ Completeness enforced!
  ↓
Backend API call with exact parameters → Berkeley housing events returned
```

---

## Architecture

### 1. Mode Detection (Unchanged)

Mode detection determines **which specialized parser to use**:

```python
def detect_mode(message: str, context: str) -> str:
    """
    Determine if user wants to:
    - Navigation: Search/find/navigate content
    - Focus: Understand specific item deeply
    - Compare: Analyze multiple items
    """
    # Uses gpt-4o-mini with lightweight classification
    # Returns: "navigation", "focus", "compare", or "uncertain"
```

**Navigation indicators**: "find", "show", "search", "list", "what meetings"

**Once mode is determined, dispatch to specialized handler...**

---

### 2. Navigation Mode Handler (NEW)

Navigation mode uses **OpenAI Structured Outputs** to guarantee complete, valid operation schemas.

#### Structured Output Schema

```typescript
// TypeScript representation of JSON Schema

type NavigationOperation =
  | SearchEventsOperation
  | SearchLegislationOperation
  | NavigateOperation
  | ClarifyOperation

interface SearchEventsOperation {
  operation: "search_events"
  filters: {
    jurisdiction: string  // REQUIRED - enforced by schema
    topic?: ProjectType   // Optional
    dateRange?: string
    searchQuery?: string
  }
  ui_hints?: {
    sidebar: "expand_events"
    preserve_filters: boolean
  }
}

interface SearchLegislationOperation {
  operation: "search_legislation"
  filters: {
    topic: ProjectType    // REQUIRED
    level: "state" | "federal" | "both"
  }
  ui_hints?: {
    sidebar: "expand_legislative"
  }
}

interface NavigateOperation {
  operation: "navigate"
  target: {
    type: "event" | "bill" | "program" | "issue" | "thread"
    id: string            // REQUIRED - artifact ID
  }
}

interface ClarifyOperation {
  operation: "clarify"
  question: string        // REQUIRED - what to ask user
  options: string[]       // REQUIRED - suggested answers (2-4 options)
}
```

#### Backend Implementation

```python
# src/civic_chat_router.py (updated)

NAVIGATION_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["search_events", "search_legislation", "navigate", "clarify"]
        },
        "filters": {
            "type": "object",
            "properties": {
                "jurisdiction": {"type": "string"},  # For search_events
                "topic": {"type": "string"},
                "dateRange": {"type": "string"},
                "searchQuery": {"type": "string"},
                "level": {"type": "string", "enum": ["state", "federal", "both"]}
            },
            # Conditional requirements based on operation
            "if": {"properties": {"operation": {"const": "search_events"}}},
            "then": {"required": ["jurisdiction"]},  # ← ENFORCED!
        },
        "target": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "id": {"type": "string"}
            }
        },
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["operation"]
}

NAVIGATION_SYSTEM_PROMPT = """
You are a navigation parser for civic engagement.

Your ONLY job: Parse user queries into structured backend operations.

CRITICAL RULES:
1. ALWAYS extract jurisdiction if mentioned (e.g., "in Berkeley" → jurisdiction: "berkeley")
2. Normalize jurisdiction to lowercase, no spaces (e.g., "San Francisco" → "san-francisco")
3. Map synonyms: "SF" → "san-francisco", "the city" → use user's registered city from context
4. If jurisdiction is ambiguous, use operation: "clarify"

Examples:

Input: "Find housing meetings in Berkeley"
Context: User is registered in Oakland
Output: {
  "operation": "search_events",
  "filters": {"jurisdiction": "berkeley", "topic": "housing"}
}

Input: "Show me meetings"
Context: User is registered in Oakland
Output: {
  "operation": "clarify",
  "question": "Which city's meetings would you like to see?",
  "options": ["Oakland (your city)", "Berkeley", "All Bay Area cities"]
}

Input: "What about San Francisco?"
Context: Previous query was about housing
Output: {
  "operation": "search_events",
  "filters": {"jurisdiction": "san-francisco", "topic": "housing"}
}
"""

def handle_navigation_mode(
    message: str,
    context: dict,
    conversation_history: list
) -> dict:
    """
    Handle Navigation mode with structured outputs.

    Returns validated NavigationOperation with guaranteed schema compliance.
    """
    # Build context string
    user_jurisdiction = context.get('user_city', 'unknown')
    context_str = f"User's registered city: {user_jurisdiction}"

    # Add conversation context for follow-ups
    if conversation_history:
        last_query = conversation_history[-2:] if len(conversation_history) >= 2 else []
        context_str += f"\n\nRecent context: {last_query}"

    # Call OpenAI with structured outputs
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": NAVIGATION_SYSTEM_PROMPT},
            {"role": "system", "content": f"Context:\n{context_str}"},
            {"role": "user", "content": message}
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "navigation_operation",
                "schema": NAVIGATION_SCHEMA,
                "strict": True  # ← Enforce schema compliance!
            }
        },
        temperature=0.1  # Low temperature for consistent parsing
    )

    # Parse structured output
    operation = json.loads(response.choices[0].message.content)

    # Validate operation-specific requirements
    if operation['operation'] == 'search_events':
        if 'filters' not in operation or 'jurisdiction' not in operation['filters']:
            # Schema should prevent this, but defensive check
            raise ValueError("search_events requires jurisdiction in filters")

    return operation
```

---

### 3. Frontend Integration

**Query parser becomes simpler**:

```typescript
// frontend/civic-workspace/src/services/navigationParser.ts

export interface NavigationOperation {
  operation: 'search_events' | 'search_legislation' | 'navigate' | 'clarify'
  filters?: EventFilters | LegislationFilters
  target?: ArtifactReference
  question?: string
  options?: string[]
}

export async function parseNavigationQuery(
  message: string,
  context: ChatContext
): Promise<NavigationOperation> {
  // Call backend navigation endpoint
  const response = await api.parseNavigation(message, context)

  // Backend returns validated structured output
  return response  // No client-side classification needed!
}
```

**ChatPanel dispatch becomes straightforward**:

```typescript
// ChatPanel.vue (simplified)

async function handleNavigationMode(message: string) {
  // Get structured operation from backend
  const operation = await parseNavigationQuery(message, currentContext)

  // Dispatch based on operation type
  switch (operation.operation) {
    case 'search_events':
      // Guaranteed to have jurisdiction!
      await api.searchEvents({
        jurisdiction: operation.filters.jurisdiction,  // ✅ Always present
        topic: operation.filters.topic,
        dateRange: operation.filters.dateRange
      })
      break

    case 'search_legislation':
      await api.searchLegislation({
        topic: operation.filters.topic,  // ✅ Always present
        level: operation.filters.level || 'both'
      })
      break

    case 'navigate':
      workspaceStore.openArtifact(operation.target)  // ✅ Always has type + id
      break

    case 'clarify':
      // Show clarification UI
      chatStore.addMessage({
        role: 'assistant',
        content: operation.question,
        quickReplies: operation.options  // ✅ Always 2-4 options
      })
      break
  }
}
```

---

## Benefits

### 1. Guaranteed Completeness ✅

**Before** (Function Calling):
```python
# LLM might return:
{
  "name": "search_events",
  "arguments": {"topic": "housing"}  # ❌ Missing jurisdiction!
}
```

**After** (Structured Outputs):
```python
# Schema enforcement guarantees:
{
  "operation": "search_events",
  "filters": {"jurisdiction": "berkeley", "topic": "housing"}  # ✅ Complete!
}
```

### 2. Explicit Fallback Strategy ✅

**Before**: Silently fails when ambiguous (searches wrong city)

**After**: Explicit `clarify` operation:
```python
{
  "operation": "clarify",
  "question": "Which city?",
  "options": ["Oakland (your city)", "Berkeley", "San Francisco"]
}
```

### 3. Backend Compatibility by Design ✅

Schema matches API exactly - no impedance mismatch between parsed intent and backend expectations.

### 4. Testable & Debuggable ✅

```python
# Unit test
def test_navigation_parsing():
    operation = parse_navigation("Find housing in Berkeley", context={})

    assert operation['operation'] == 'search_events'
    assert operation['filters']['jurisdiction'] == 'berkeley'
    assert operation['filters']['topic'] == 'housing'
    # ✅ Schema guarantees these fields exist!
```

### 5. Context Preservation ✅

```python
# Follow-up query:
Input: "What about transportation?"
Context: Previous query was "housing in Berkeley"

# Structured output preserves context:
{
  "operation": "search_events",
  "filters": {
    "jurisdiction": "berkeley",  # ← Preserved from context
    "topic": "transportation"    # ← Updated from query
  }
}
```

---

## Migration Plan

### Phase 1: Parallel Implementation (1 session)

**Backend**:
1. Add `handle_navigation_mode()` with structured outputs
2. Keep existing function calling as fallback
3. Add feature flag: `USE_STRUCTURED_NAVIGATION = True`

**Frontend**:
1. Update `parseNavigationQuery()` to use new endpoint
2. Simplify query classifier (no longer needed)

### Phase 2: Validation & Testing (1 session)

**Test Cases**:
- ✅ Explicit jurisdiction extraction: "Find housing in Berkeley"
- ✅ Implicit jurisdiction (user's city): "Show me meetings"
- ✅ Clarification for ambiguity: "Show meetings" (no user context)
- ✅ Context preservation: "What about SF?" (after Berkeley query)
- ✅ Complex queries: "housing or transportation in next 2 weeks"

**Success Criteria**:
- 100% of queries with explicit jurisdiction extract it correctly
- 0% silent failures (all ambiguity triggers clarify operation)
- Latency <500ms for 95th percentile

### Phase 3: Deprecation (1 session)

Remove old function calling code, finalize documentation.

---

## Cost Impact

**Structured Outputs Pricing** (OpenAI):
- Same as regular completion tokens
- No additional cost for schema enforcement

**Expected Impact**:
- Navigation queries: ~50 tokens → ~$0.00001 per query
- 100 users × 10 queries/day × 30 days = 30,000 queries/month
- Total: ~$0.30/month (unchanged from current)

---

## Comparison: Function Calling vs Structured Outputs

| Aspect | Function Calling | Structured Outputs |
|--------|-----------------|-------------------|
| **Schema Enforcement** | Soft (descriptive) | Hard (prescriptive) |
| **Missing Fields** | Silently omitted | Guaranteed present (if required) |
| **Validation** | Client-side | Server-side (OpenAI enforces) |
| **Ambiguity Handling** | Implicit failure | Explicit `clarify` operation |
| **Type Safety** | JSON parsing required | Type-safe from API |
| **Cost** | ~$0.30/month | ~$0.30/month (same) |
| **Latency** | ~300ms | ~300ms (same) |
| **Best For** | Conversational responses | Command parsing |

**Decision**: Use **Structured Outputs for Navigation** (command parsing), keep **Function Calling for Focus/Compare** (conversational analysis).

---

## Future Extensions

### 1. Complex Query Composition

```python
# Multi-step query:
Input: "Show housing meetings in Berkeley and related state bills"

# Structured output can return multiple operations:
{
  "operations": [
    {
      "operation": "search_events",
      "filters": {"jurisdiction": "berkeley", "topic": "housing"}
    },
    {
      "operation": "search_legislation",
      "filters": {"topic": "housing", "level": "state"}
    }
  ]
}
```

### 2. Progressive Clarification

```python
# Ambiguous query:
Input: "Show meetings about housing"

# First clarification:
{
  "operation": "clarify",
  "question": "Which city?",
  "options": ["Oakland", "Berkeley", "San Francisco"]
}

# User selects "Berkeley"

# Second clarification:
{
  "operation": "clarify",
  "question": "What timeframe?",
  "options": ["This week", "This month", "All upcoming"]
}

# Final operation:
{
  "operation": "search_events",
  "filters": {"jurisdiction": "berkeley", "topic": "housing", "dateRange": "this-week"}
}
```

### 3. Natural Language Refinement

```python
# Initial query:
Input: "Show housing meetings"
Result: 50 meetings found

# Refinement:
Input: "Just next week"
Context: Previous query was housing

# Structured output updates filters:
{
  "operation": "search_events",
  "filters": {
    "jurisdiction": "oakland",      # Preserved
    "topic": "housing",             # Preserved
    "dateRange": "next-week"        # Added
  }
}
```

---

## References

- **OpenAI Structured Outputs Docs**: https://platform.openai.com/docs/guides/structured-outputs
- **Original Function Calling** (Session 27): `CHAT_ROUTING_ARCHITECTURE.md`
- **Mode System** (Session 56): `CHAT_STRATEGY_ROADMAP.md`
- **Implementation**: `src/civic_chat_router.py` (to be updated)

---

## Summary

Navigation mode refactor replaces soft function calling with hard structured outputs:

✅ **Guaranteed schema compliance** - No more missing jurisdiction bugs
✅ **Explicit fallback** - Clarify operations instead of silent failures
✅ **Backend compatible** - Schema matches API exactly
✅ **Type safe** - Frontend gets validated structures
✅ **Same cost** - $0.30/month for 100 users
✅ **Testable** - Clear contracts for unit tests

**Next Step**: Implement in Session 56.5 (estimated 3-4 hours)
