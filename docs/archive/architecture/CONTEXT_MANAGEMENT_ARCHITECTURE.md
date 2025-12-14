# Context Management Architecture

**Status**: ✅ **Phases 1-3 Complete** - Infrastructure built, chat integration pending
**Version**: 1.1
**Last Updated**: 2025-11-02
**Authors**: Architecture planning session

## Executive Summary

This document defines a **future-proof context management architecture** for the Civic Conversational OS. The schema is designed to work seamlessly across three levels of sophistication:

1. **Phase 1-2** (Current): Implicit context + visual indicators
2. **Phase 3-4** (Near-term): Explicit context registry with mode-aware filtering
3. **Phase 5+** (Future): RAG-style semantic retrieval with vector embeddings

**Critical Design Principle**: The schema is **retrieval-strategy agnostic**. Context elements are structured to work with simple key-value lookups today and vector similarity search tomorrow—without schema migration.

---

## ⚡ Implementation Progress

**Status as of Session 53.5** (2025-11-02):

- ✅ **Phase 1 Complete**: Visual context indicators (Session 51 - 3 hours)
- ✅ **Phase 2 Complete**: Context registry with full schema (Session 52 - 4 hours)
- ✅ **Phase 3 Complete**: Mode-aware filtering with 4 modes (Session 53 - 4 hours)
- ✅ **Phase 3.5 Complete**: Centralized artifact ID management (Session 53.5 - 3 hours)
- ❌ **Phase 4 Pending**: Chat integration with context system

**Total Implementation**: 14 hours across 4 sessions (Sessions 51-53.5)

### Key Architectural Achievement

**Infrastructure built ahead of schedule**: All three core phases (visual indicators, registry, mode-aware filtering) are production-ready and working in the UI. Context registry successfully tracks artifacts, manages priorities, filters by mode, and provides visual feedback.

### Critical Integration Gap

**Chat endpoint doesn't consume context yet**: While the context registry tracks which artifacts are open and filters them by mode, the chat LLM (`/api/chat/route`) doesn't query this registry. Chat currently receives minimal context (just current artifact ID), preventing:

- Multi-artifact analysis ("compare these 3 bills")
- Context-aware responses using open documents
- Mode-specific system prompts (navigation vs research vs coach)
- Automatic bill/program citation in responses

### Next Steps

**Option A - Connect Chat to Context** (2-3 hours):
- Modify `/api/chat/route` to query context store
- Inject active contexts into LLM prompt based on mode
- Add mode-aware system prompts
- **Unlocks**: Smart multi-document chat (Phase 2 of CHAT_STRATEGY_ROADMAP.md)

**Option B - Continue Feature Development**:
- Proceed with Email Pre-Population (Session 54)
- Defer chat integration to later sessions
- **Trade-off**: Context system remains unused by chat

See `CHAT_ROUTING_ARCHITECTURE.md` for chat integration requirements.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Future Compatibility Requirements](#future-compatibility-requirements)
3. [Core Schema Design](#core-schema-design)
4. [Retrieval Strategy Evolution](#retrieval-strategy-evolution)
5. [Implementation Phases](#implementation-phases)
6. [Migration Path](#migration-path)
7. [Technical Specifications](#technical-specifications)
8. [Example Scenarios](#example-scenarios)

---

## Problem Statement

### Current Limitations

As of Session 50, context management is **implicit**:
```typescript
// Current approach
const activeArtifact = workspaceStore.activeArtifact;
chatBackend.sendMessage(message, { artifact_id: activeArtifact?.id });
```

**Works for**: Single-artifact navigation and research
**Breaks down for**:
- Multi-document workflows (drafting proposal from 3 events + 2 bills)
- Civic coaching (requires full user history + open artifacts)
- Workflow orchestration (coordinating across many sources)
- Document composition (synthesizing across heterogeneous sources)

### Strategic Context Needs

Our **4-phase chat evolution** (see `CHAT_STRATEGY_ROADMAP.md`) has escalating context requirements:

| Phase | Context Needs | Complexity |
|-------|--------------|------------|
| **Phase 1**: Navigation | Single artifact (current state) | Low |
| **Phase 2**: Research | 2-3 related artifacts | Medium |
| **Phase 3**: Coach | Full civic history + active workflow | High |
| **Phase 4**: Orchestrator | Multi-document synthesis + relationships | Very High |

**Foundation pitch impact**: Advanced context management enables "democratic participation toolkit" narrative (not just a comment tool).

---

## Future Compatibility Requirements

### Design Goals

The schema must support **all three retrieval strategies** without migration:

#### Strategy 1: Key-Value Lookup (Phase 1-2)
```typescript
// Simple map lookup by ID
contextRegistry.get(artifactId) → ContextElement
```

#### Strategy 2: Structured Query (Phase 3-4)
```typescript
// Filter by type, priority, temporal, relationships
contextRegistry.query({
    types: ['event', 'bill'],
    priority: ['primary', 'secondary'],
    maxAge: '24h',
    relatedTo: 'event-123'
}) → ContextElement[]
```

#### Strategy 3: Semantic Retrieval (Phase 5+)
```typescript
// Vector similarity search (future)
contextRegistry.semanticSearch({
    query: "housing affordability in Berkeley",
    topK: 5,
    filters: { types: ['event', 'bill'], recency: '30d' }
}) → ContextElement[]
```

### Industry Standards Compatibility

Schema follows patterns from:
- **Anthropic MCP** (Model Context Protocol) - resource schema
- **LangChain** - Document/context abstraction
- **OpenAI Assistants API** - Thread/message context
- **Pinecone/Weaviate** - Vector metadata schemas

**Key insight**: All vector DBs store metadata alongside embeddings. Our schema IS that metadata structure—we can add vector embeddings later without changing the schema.

**Integration with LLM Provider Architecture** (2025-11-05):

The Context Management system is designed to work seamlessly with the provider-agnostic LLM architecture (see `docs/LLM_PROVIDER_ARCHITECTURE.md`):

- ✅ **MCP-Compatible Context**: `ContextElement` schema translates 1:1 to MCP resources
- ✅ **Provider-Agnostic Serialization**: Context elements work with OpenAI, Claude, Gemini via abstraction layer
- ✅ **Tool Registry Integration**: Context-aware tools can query registry for related artifacts
- ✅ **RAG-Ready**: Schema supports Anthropic Contextual Retrieval without migration
- ✅ **Agentic Workflows**: Multi-step workflows can maintain context across LLM calls

**Example: Context → LLM Provider**:
```python
# Serialize context for any LLM provider
active_context = context_store.getActiveContext()
serialized = serializeContextForLLM(active_context)

# Works with any provider
llm_provider = get_llm_provider("anthropic")  # or "openai", "google"
response = llm_provider.chat_completion(
    messages=[
        {"role": "system", "content": serialized},
        {"role": "user", "content": "What bills relate to these events?"}
    ]
)
```

This architecture enables **future-proof context management** compatible with all major AI systems (Claude Code, LangChain agents, MCP servers).

---

## Core Schema Design

### Context Element Schema (Future-Proof)

```typescript
/**
 * Core context element schema - compatible with all retrieval strategies
 *
 * Version: 1.0 (extensible via content_version field)
 * Future-proof: Can add vector embeddings without schema change
 */
interface ContextElement {
    // === IDENTITY & VERSIONING ===
    id: string;                      // Unique identifier (UUID)
    content_version: string;         // Schema version (e.g., "1.0", "2.0")
    content_hash: string;            // SHA-256 of data field (deduplication)

    // === CORE METADATA ===
    type: ContextElementType;        // 'event' | 'bill' | 'program' | 'thread' | 'draft' | 'issue'
    artifact_id: string;             // Corresponds to UI artifact/tab
    source: string;                  // Where context came from (e.g., "user_opened", "auto_linked")

    // === TEMPORAL TRACKING ===
    created_at: Date;                // When added to context
    updated_at: Date;                // Last modification
    accessed_at: Date;               // Last time LLM accessed this
    expires_at?: Date;               // Optional TTL for transient context

    // === PRIORITY & RELATIONSHIPS ===
    priority: 'primary' | 'secondary' | 'reference' | 'background';
    relationships: {
        parent?: string;             // Parent context element (e.g., event for agenda item)
        children?: string[];         // Child elements (e.g., agenda items for event)
        related?: string[];          // Related elements (e.g., bills referenced in event)
        supersedes?: string;         // Replaces older context element
    };

    // === USER INTERACTION SIGNALS ===
    user_signals: {
        view_duration?: number;      // Seconds artifact was visible
        scroll_depth?: number;       // 0-1, how far user scrolled
        interaction_count?: number;  // Clicks, selections, edits
        explicit_pin?: boolean;      // User explicitly pinned to context
        explicit_exclude?: boolean;  // User explicitly removed from context
    };

    // === RICH METADATA (for semantic retrieval) ===
    metadata: {
        title: string;               // Human-readable title
        summary: string;             // 1-2 sentence summary (for LLM context injection)
        keywords: string[];          // Extracted keywords (for search)
        topics: string[];            // Civic topics (housing, transportation, etc.)
        jurisdiction: string;        // City/county identifier

        // Type-specific metadata
        event?: EventMetadata;
        bill?: BillMetadata;
        program?: ProgramMetadata;
        thread?: ThreadMetadata;
        draft?: DraftMetadata;
        issue?: IssueMetadata;
    };

    // === STRUCTURED DATA (full object) ===
    data: ContextData;               // Type-specific full data

    // === FUTURE: VECTOR EMBEDDINGS (additive, no schema change) ===
    embeddings?: {
        summary_embedding?: number[];     // Vector of metadata.summary
        content_embedding?: number[];     // Vector of full data
        model: string;                    // e.g., "text-embedding-3-small"
        dimension: number;                // e.g., 1536
    };
}

/**
 * Type-specific metadata schemas
 */
interface EventMetadata {
    event_id: string;
    jurisdiction_id: string;
    meeting_date: Date;
    meeting_type: string;
    active_tab: 'details' | 'discussion' | 'drafts';

    // Sub-context: agenda items
    selected_agenda_items?: string[];  // IDs of agenda items user is focusing on
    agenda_item_count: number;
    actionable_item_count: number;

    // Sub-context: draft state
    active_draft?: {
        draft_id: string;
        position: string;
        key_concern: string;
        is_modified: boolean;
        word_count: number;
    };

    // Sub-context: discussion activity
    discussion_stats?: {
        thread_id: string;
        participant_count: number;
        message_count: number;
        unread_count: number;
        user_mentioned: boolean;
    };

    // Legislative references
    referenced_bills?: string[];       // Bill IDs mentioned in event
    referenced_programs?: string[];    // Program IDs mentioned in event
}

interface BillMetadata {
    bill_id: string;
    bill_number: string;               // e.g., "AB 1147"
    state: string;
    session: string;
    topic: string;
    status: string;

    // User interaction
    user_annotations?: string[];       // User highlighted sections
    scroll_position?: number;          // 0-1, where user is in document

    // Relationships
    related_events?: string[];         // Events that reference this bill
    related_drafts?: string[];         // Drafts that cite this bill
}

interface ProgramMetadata {
    program_id: string;
    program_name: string;
    agency: string;
    topic: string;

    // Financial context
    total_allocation?: number;
    jurisdiction_allocation?: number;

    // Relationships
    related_events?: string[];
    related_bills?: string[];
}

interface ThreadMetadata {
    thread_id: string;
    thread_type: 'event_discussion' | 'issue_coordination';
    participant_count: number;
    message_count: number;
    created_at: Date;
    last_activity: Date;

    // User involvement
    user_is_participant: boolean;
    user_is_follower: boolean;
    unread_count: number;
    user_mentioned: boolean;
}

interface DraftMetadata {
    draft_id: string;
    document_type: 'public_comment' | 'proposal' | 'legislation' | 'letter';
    context_id: string;                // event_id, bill_id, etc.

    // Draft state
    position: string;
    key_concern: string;
    personal_context: string;
    word_count: number;
    is_modified: boolean;
    last_saved: Date;

    // Composition
    section_count: number;
    referenced_bills?: string[];
    referenced_events?: string[];

    // Tags
    tags: string[];
    privacy_tier: 'anonymous' | 'semi_identified' | 'fully_identified';
}

interface IssueMetadata {
    issue_id: string;
    category: string;
    status: string;
    priority: string;

    // Civic linkage
    linked_events?: string[];
    coordination_thread_id?: string;
    follower_count: number;

    // User relationship
    user_is_reporter: boolean;
    user_is_follower: boolean;
}

/**
 * Type-specific full data (stored in data field)
 */
type ContextData =
    | { type: 'event'; event: EventData }
    | { type: 'bill'; bill: BillData }
    | { type: 'program'; program: ProgramData }
    | { type: 'thread'; thread: ThreadData }
    | { type: 'draft'; draft: DraftData }
    | { type: 'issue'; issue: IssueData };
```

### Schema Design Rationale

#### 1. **ID-Based References** (not embedded objects)
```typescript
// ✅ GOOD: References by ID
relationships: {
    related: ['bill-123', 'event-456']
}

// ❌ BAD: Embedded objects
relationships: {
    related: [{ type: 'bill', data: {...} }]  // Creates duplication
}
```
**Why**: Enables deduplication, relationship graphs, and separate vector storage.

#### 2. **Metadata + Data Separation**
```typescript
metadata: {
    title: "Berkeley City Council - Housing",  // Lightweight, for LLM injection
    summary: "Discussion of AB 1147 impact"    // Short, embeddable
}
data: {
    event: { /* full 50KB event object */ }    // Heavy, for display
}
```
**Why**: LLM context windows are limited. Inject metadata for most cases, fetch full data only when needed.

#### 3. **Content Hashing** (deduplication)
```typescript
content_hash: "sha256:a1b2c3..."  // Hash of data field
```
**Why**: Two artifacts showing the same event share one context element. Critical for performance.

#### 4. **User Signals** (behavioral data)
```typescript
user_signals: {
    view_duration: 45,      // Spent 45s viewing
    scroll_depth: 0.8,      // Read 80% of content
    interaction_count: 5    // 5 clicks/selections
}
```
**Why**: Enables future ML-based relevance ranking without schema changes.

#### 5. **Optional Embeddings Field** (additive future-proofing)
```typescript
embeddings?: {
    summary_embedding: [0.123, -0.456, ...],  // 1536-dim vector
    model: "text-embedding-3-small"
}
```
**Why**: Can add vectors later without schema migration. Vector DBs store metadata+vectors together.

---

## Retrieval Strategy Evolution

### Phase 1-2: Simple Map Lookup (Sessions 1-52)

**Implementation**: Pinia store with Map
```typescript
export const useContextStore = defineStore('context', {
    state: () => ({
        registry: new Map<string, ContextElement>()
    }),

    actions: {
        get(id: string): ContextElement | undefined {
            return this.registry.get(id);
        }
    }
});
```

**Use case**: Single artifact context (navigation, basic research)
**Cost**: $0
**Latency**: <1ms

### Phase 3-4: Structured Query (Sessions 54-70)

**Implementation**: In-memory filtering with indexes
```typescript
export const useContextStore = defineStore('context', {
    state: () => ({
        registry: new Map<string, ContextElement>(),

        // Indexes for fast queries (built incrementally)
        typeIndex: new Map<ContextElementType, Set<string>>(),
        relationshipIndex: new Map<string, Set<string>>(),
        topicIndex: new Map<string, Set<string>>()
    }),

    actions: {
        query(filters: ContextQuery): ContextElement[] {
            let candidates = Array.from(this.registry.values());

            // Filter by type (use index)
            if (filters.types) {
                const typeSet = new Set<string>();
                filters.types.forEach(type => {
                    this.typeIndex.get(type)?.forEach(id => typeSet.add(id));
                });
                candidates = candidates.filter(el => typeSet.has(el.id));
            }

            // Filter by priority
            if (filters.priority) {
                candidates = candidates.filter(el =>
                    filters.priority!.includes(el.priority)
                );
            }

            // Filter by recency
            if (filters.maxAge) {
                const cutoff = Date.now() - parseMaxAge(filters.maxAge);
                candidates = candidates.filter(el =>
                    el.accessed_at.getTime() > cutoff
                );
            }

            // Filter by relationships
            if (filters.relatedTo) {
                candidates = candidates.filter(el =>
                    el.relationships.related?.includes(filters.relatedTo!)
                );
            }

            // Sort by priority + recency
            return candidates
                .sort((a, b) => scorePriority(a, b))
                .slice(0, filters.limit || 10);
        }
    }
});
```

**Use case**: Multi-artifact workflows, coaching, mode-aware filtering
**Cost**: $0
**Latency**: ~5-10ms (in-memory filtering)

### Phase 5+: Semantic Retrieval (Future)

**Implementation**: Hybrid (vector DB + structured filters)
```typescript
// Vector DB schema (Pinecone/Qdrant/Weaviate)
interface VectorRecord {
    id: string;                          // Same as ContextElement.id
    vector: number[];                    // Embedding
    metadata: ContextElement['metadata']; // Full metadata (for filtering)
}

// Hybrid search: vector similarity + structured filters
async function semanticSearch(query: string, filters: ContextQuery): Promise<ContextElement[]> {
    // 1. Get query embedding
    const queryEmbedding = await openai.embeddings.create({
        model: "text-embedding-3-small",
        input: query
    });

    // 2. Vector search with metadata filters
    const results = await vectorDB.query({
        vector: queryEmbedding.data[0].embedding,
        topK: 20,
        filter: {
            type: { $in: filters.types },
            priority: { $in: filters.priority },
            'metadata.jurisdiction': filters.jurisdiction,
            created_at: { $gte: filters.minDate }
        }
    });

    // 3. Fetch full ContextElements from cache/DB
    const elements = await Promise.all(
        results.matches.map(match => contextStore.get(match.id))
    );

    return elements.filter(Boolean);
}
```

**Use case**: "Find all housing discussions in Berkeley from the last 3 months"
**Cost**: ~$0.0001 per search (embedding + vector query)
**Latency**: ~50-100ms (API + vector search)

**Migration path**:
1. Generate embeddings for existing context elements (one-time batch job)
2. Add embeddings on context creation going forward
3. Gradually introduce semantic search for complex queries
4. Keep structured queries for simple cases (faster, cheaper)

---

## Implementation Phases

### Phase 1: Context Indicators ✅ COMPLETE (Session 51) - 3 hours

**Actual Implementation**: Session 51 (2025-11-01)

**Goal**: Visual transparency into implicit context (no schema changes)

**Components**:
```vue
<!-- ContextIndicator.vue -->
<div class="context-indicator">
    <div class="context-badge">
        <Icon name="layers" />
        <span>{{ activeArtifactCount }} active</span>
    </div>

    <Transition name="expand">
        <div v-if="expanded" class="context-detail">
            <div v-for="artifact in openArtifacts" :key="artifact.id">
                <Icon :name="getIconForType(artifact.type)" />
                <span>{{ artifact.title }}</span>
            </div>
        </div>
    </Transition>
</div>
```

**Backend**: No changes (uses existing workspace state)

**Value**: Users understand what chat can "see"

---

### Phase 2: Context Registry Implementation ✅ COMPLETE (Session 52) - 4 hours

**Actual Implementation**: Session 52 (2025-11-02)

**Goal**: Explicit context management with full schema

**Schema Implementation**:
```typescript
// src/stores/context.ts
import { defineStore } from 'pinia';
import { ContextElement, ContextQuery } from '@/types/context';

export const useContextStore = defineStore('context', {
    state: () => ({
        registry: new Map<string, ContextElement>(),
        typeIndex: new Map<string, Set<string>>(),
        relationshipIndex: new Map<string, Set<string>>()
    }),

    actions: {
        register(element: ContextElement): void {
            // Check for duplicates via content_hash
            const existing = this.findByContentHash(element.content_hash);
            if (existing) {
                this.update(existing.id, { accessed_at: new Date() });
                return;
            }

            // Add to registry
            this.registry.set(element.id, element);

            // Update indexes
            this.updateIndexes(element);

            // Prune if needed
            this.pruneStaleContext();
        },

        unregister(id: string): void {
            const element = this.registry.get(id);
            if (!element) return;

            this.registry.delete(id);
            this.removeFromIndexes(element);
        },

        update(id: string, updates: Partial<ContextElement>): void {
            const element = this.registry.get(id);
            if (!element) return;

            const updated = { ...element, ...updates, updated_at: new Date() };
            this.registry.set(id, updated);
        },

        query(filters: ContextQuery): ContextElement[] {
            // See Phase 3-4 implementation above
        }
    },

    getters: {
        activeContext(): ContextElement[] {
            return Array.from(this.registry.values())
                .filter(el => !el.expires_at || el.expires_at > new Date())
                .sort((a, b) => scorePriority(a, b));
        }
    }
});
```

**Artifact Integration**:
```vue
<!-- EventArtifact.vue -->
<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue';
import { useContextStore } from '@/stores/context';

const contextStore = useContextStore();
const contextId = ref<string>();

onMounted(() => {
    // Register context on mount
    contextId.value = contextStore.register({
        id: generateUUID(),
        content_version: '1.0',
        content_hash: hashObject(props.event),
        type: 'event',
        artifact_id: props.artifactId,
        source: 'user_opened',
        created_at: new Date(),
        updated_at: new Date(),
        accessed_at: new Date(),
        priority: 'primary',
        relationships: {
            related: extractRelatedBills(props.event)
        },
        user_signals: {
            view_duration: 0,
            scroll_depth: 0,
            interaction_count: 0
        },
        metadata: {
            title: props.event.title,
            summary: props.event.participation_summary || '',
            keywords: extractKeywords(props.event),
            topics: [props.event.project_type],
            jurisdiction: props.event.jurisdiction_id,
            event: {
                event_id: props.event.id,
                jurisdiction_id: props.event.jurisdiction_id,
                meeting_date: new Date(props.event.meeting_date),
                meeting_type: props.event.meeting_type || 'Council Meeting',
                active_tab: activeTab.value,
                agenda_item_count: props.event.agenda_items?.length || 0,
                actionable_item_count: props.event.agenda_items?.filter(i => i.actionable).length || 0
            }
        },
        data: {
            type: 'event',
            event: props.event
        }
    });
});

// Update sub-context when user switches tabs
watch(activeTab, (newTab) => {
    if (contextId.value) {
        contextStore.update(contextId.value, {
            'metadata.event.active_tab': newTab,
            accessed_at: new Date()
        });
    }
});

onUnmounted(() => {
    if (contextId.value) {
        contextStore.unregister(contextId.value);
    }
});
</script>
```

**Backend Integration**:
```python
# src/civic_chat_router.py
@app.post("/api/chat/route")
async def route_chat(request: ChatRequest):
    # Receive serialized context from frontend
    context_elements = request.context  # List[ContextElement]

    # Build context string for LLM
    context_str = serialize_context_for_llm(context_elements)

    # Include in system prompt
    system_prompt = f"""You are a civic engagement assistant.

Current user context:
{context_str}

Available functions: ...
"""

    # Rest of routing logic...
```

**Value**: Explicit context management, enables multi-artifact workflows

---

### Phase 3: Mode-Aware Context ✅ COMPLETE (Session 53) - 4 hours

**Actual Implementation**: Session 53 (2025-11-01)

**Goal**: Different chat modes see different context

**Mode Definitions**:
```typescript
// src/config/chatModes.ts
interface ChatModeConfig {
    name: string;
    description: string;
    contextFilter: (element: ContextElement) => boolean;
    maxElements: number;
    systemPrompt: string;
}

export const CHAT_MODES: Record<string, ChatModeConfig> = {
    navigation: {
        name: 'Navigation',
        description: 'Navigate to events, bills, and content',
        contextFilter: (el) => el.priority === 'primary',
        maxElements: 1,
        systemPrompt: 'You are a navigation assistant. Help users find and open relevant content. Use the available navigation functions to open artifacts.'
    },

    research: {
        name: 'Research',
        description: 'Search and analyze across open content',
        contextFilter: (el) => ['primary', 'secondary'].includes(el.priority),
        maxElements: 3,
        systemPrompt: 'You are a research assistant. Analyze the user\'s open artifacts and help them find connections, patterns, and insights.'
    },

    coach: {
        name: 'Coach',
        description: 'Guide through civic participation process',
        contextFilter: (el) => true,  // See everything
        maxElements: 5,
        systemPrompt: 'You are a civic engagement coach. Help users understand processes, draft comments, and take action. Consider their full civic history and current context.'
    },

    orchestrator: {
        name: 'Orchestrator',
        description: 'Coordinate multi-document workflows',
        contextFilter: (el) => el.type !== 'reference',
        maxElements: 10,
        systemPrompt: 'You are a workflow orchestrator. Help users synthesize information across multiple sources to create proposals, comments, or analysis.'
    }
};
```

**Mode Switching**:
```typescript
// src/stores/context.ts (updated)
export const useContextStore = defineStore('context', {
    state: () => ({
        registry: new Map<string, ContextElement>(),
        activeMode: 'navigation' as keyof typeof CHAT_MODES,
        // ...
    }),

    actions: {
        setMode(mode: keyof typeof CHAT_MODES) {
            this.activeMode = mode;
        },

        getActiveContext(): ContextElement[] {
            const modeConfig = CHAT_MODES[this.activeMode];
            const filtered = Array.from(this.registry.values())
                .filter(modeConfig.contextFilter)
                .sort((a, b) => scorePriority(a, b))
                .slice(0, modeConfig.maxElements);

            return filtered;
        }
    }
});
```

**UI Mode Indicator**:
```vue
<!-- ChatPanel.vue -->
<div class="chat-mode-selector">
    <button
        v-for="(config, key) in CHAT_MODES"
        :key="key"
        :class="{ active: contextStore.activeMode === key }"
        @click="contextStore.setMode(key)"
    >
        <Icon :name="getModeIcon(key)" />
        <span>{{ config.name }}</span>
    </button>
</div>
```

**Value**: Optimized context per use case, prevents token bloat

---

### Phase 3.5: Artifact ID Management ✅ COMPLETE (Session 53.5) - 3 hours

**Actual Implementation**: Session 53.5 (2025-11-02)

**Goal**: Prevent artifact ID mismatches between openArtifact() and context registration

**Problem Solved**:
- Bills/programs weren't closing when removed from context
- Root cause: ID format inconsistency (e.g., `bill-AB 1147` vs `AB 1147`)

**Implementation**: `src/utils/artifactIds.ts`
```typescript
// Centralized ID generation for all artifact types
export const ArtifactIds = {
  event: (event) => event.id,                    // Raw ID
  bill: (bill) => `bill-${bill.bill}`,          // Prefixed
  program: (program) => `program-${program.program_name}`, // Prefixed
  issue: (issueId) => issueId,                  // Raw ID
  thread: (threadId) => threadId,               // Raw ID
};

// Runtime validation
export function isValidArtifactId(type: string, id: string): boolean;
```

**Files Changed**: 14 files (1 new, 13 modified)
- All artifact components now use `ArtifactIds.{type}()` helper
- All `openArtifact()` calls use centralized helpers
- workspace.ts validates ID format and logs warnings

**Value**: Single source of truth, prevents entire class of ID mismatch bugs

---

### Phase 4: Chat Integration (Session 54+) - PENDING ⏸️

**Goal**: Connect context registry to chat endpoint for multi-document intelligence

**Requirements**:
- Modify `/api/chat/route` to query context store
- Inject active contexts into LLM prompt based on mode
- Add mode-aware system prompts
- Support multi-artifact analysis

**Estimated Effort**: 2-3 hours

See `CHAT_ROUTING_ARCHITECTURE.md` for detailed integration requirements.

---

### Phase 5: Advanced Features (Sessions 55+) - Future

**Features**:

#### 4a. Auto-Linking (Session 61-62)
```typescript
// Automatically add related bills when event is opened
watch(() => contextStore.registry.get(eventContextId), (eventContext) => {
    if (!eventContext) return;

    const billIds = eventContext.metadata.event?.referenced_bills || [];
    billIds.forEach(billId => {
        contextStore.registerRelated({
            type: 'bill',
            artifact_id: `bill-${billId}`,
            priority: 'reference',  // Lower priority
            source: 'auto_linked',
            relationships: {
                parent: eventContext.id
            },
            // ... fetch bill data
        });
    });
});
```

#### 4b. User Context Preferences (Session 63-64)
```typescript
interface UserContextPreferences {
    max_elements: number;           // Default 5
    auto_include_related: boolean;  // Default true
    auto_include_drafts: boolean;   // Default true
    context_ttl: number;            // Minutes, default 60
    preferred_topics: string[];     // Filter by topics
}

// Store in user profile (PersonalizationService)
```

#### 4c. Context Diff View (Session 65-66)
```vue
<!-- Show what context changed between messages -->
<div class="context-diff">
    <div class="added">
        <Icon name="plus-circle" />
        <span>Added: Bill AB 1147</span>
    </div>
    <div class="removed">
        <Icon name="minus-circle" />
        <span>Removed: Event (closed tab)</span>
    </div>
</div>
```

---

### Phase 5: Semantic Retrieval (Future)

**Prerequisites**:
- High usage (>1000 users) to justify costs
- Complex queries that benefit from semantic search
- Budget for vector DB hosting (~$20/month for 10K vectors)

**Implementation**:
1. Generate embeddings for all context elements (one-time)
2. Set up vector DB (Pinecone/Qdrant)
3. Sync new context elements to vector DB
4. Implement hybrid search (structured + semantic)
5. A/B test semantic vs. structured retrieval

**Migration**: Zero schema changes (just add `embeddings` field)

---

## Migration Path

### Version 1.0 → 1.1: Add Embeddings (Future)

**Schema change**: Additive only
```typescript
// Before (v1.0)
interface ContextElement {
    // ... all existing fields
}

// After (v1.1) - ADDITIVE
interface ContextElement {
    // ... all existing fields (unchanged)

    embeddings?: {  // NEW OPTIONAL FIELD
        summary_embedding?: number[];
        content_embedding?: number[];
        model: string;
        dimension: number;
    };
}
```

**Migration script**:
```typescript
// migrations/add_embeddings.ts
async function migrateToV1_1() {
    const elements = await loadAllContextElements();

    for (const element of elements) {
        if (element.content_version === '1.0') {
            // Generate embedding for summary
            const embedding = await openai.embeddings.create({
                model: "text-embedding-3-small",
                input: element.metadata.summary
            });

            // Add embeddings field
            element.embeddings = {
                summary_embedding: embedding.data[0].embedding,
                model: "text-embedding-3-small",
                dimension: 1536
            };

            element.content_version = '1.1';
            await saveContextElement(element);
        }
    }
}
```

**Backwards compatibility**: All v1.0 code works unchanged (embeddings are optional)

---

## Technical Specifications

### Storage

**Phase 2-3**: In-memory (Pinia store)
- **Capacity**: ~1000 elements (5MB)
- **Persistence**: sessionStorage (survives refresh)
- **Latency**: <1ms

**Phase 4**: SQLite cache (optional)
- **Purpose**: Persist context across sessions
- **Schema**: Same as ContextElement
- **Sync**: On register/unregister

**Phase 5**: Vector DB (future)
- **Options**: Pinecone, Qdrant, Weaviate
- **Schema**: ContextElement metadata + embeddings
- **Sync**: Real-time on context changes

### Performance Targets

| Phase | Operation | Target Latency | Target Cost |
|-------|-----------|----------------|-------------|
| 1-2 | Get by ID | <1ms | $0 |
| 3-4 | Structured query | <10ms | $0 |
| 5 | Semantic search | <100ms | ~$0.0001 |

### Context Limits

**Token budget**: 128K context window (Claude 3.5 Sonnet)
- Reserve 100K for conversation history
- Use 28K for context injection (~20K tokens)

**Element limits by mode**:
- Navigation: 1 element (~500 tokens)
- Research: 3 elements (~1500 tokens)
- Coach: 5 elements (~3000 tokens)
- Orchestrator: 10 elements (~6000 tokens)

**Serialization strategy**:
```typescript
function serializeForLLM(element: ContextElement): string {
    // Lightweight: Use metadata only (50-100 tokens)
    return `
[${element.type.toUpperCase()}] ${element.metadata.title}
Summary: ${element.metadata.summary}
Topics: ${element.metadata.topics.join(', ')}
`;

    // OR full data for primary context (500-1000 tokens)
    // return JSON.stringify(element.data);
}
```

---

## Example Scenarios

### Scenario 1: Multi-Document Comment Draft (Phase 3-4)

**User workflow**:
1. Opens Berkeley housing event (event-123)
2. Clicks bill AB 1147 from event
3. Opens discussion thread about housing
4. Starts drafting comment

**Context state**:
```typescript
[
    {
        id: 'ctx-1',
        type: 'event',
        artifact_id: 'artifact-event-123',
        priority: 'primary',
        metadata: {
            title: 'Berkeley City Council - Housing',
            topics: ['housing'],
            event: {
                active_tab: 'drafts',
                selected_agenda_items: ['item-5'],
                active_draft: {
                    draft_id: 'draft-789',
                    position: 'in_favor',
                    is_modified: true
                }
            }
        }
    },
    {
        id: 'ctx-2',
        type: 'bill',
        artifact_id: 'artifact-bill-ab1147',
        priority: 'secondary',
        relationships: {
            related: ['ctx-1']  // Related to event
        },
        metadata: {
            title: 'AB 1147 - Affordable Housing',
            bill: {
                related_events: ['event-123'],
                related_drafts: ['draft-789']
            }
        }
    },
    {
        id: 'ctx-3',
        type: 'thread',
        artifact_id: 'artifact-thread-456',
        priority: 'reference',
        metadata: {
            title: 'Discussion: Berkeley Housing Crisis',
            thread: {
                participant_count: 15,
                user_is_participant: true,
                unread_count: 3
            }
        }
    }
]
```

**Chat query**: "Help me strengthen my comment with evidence from AB 1147"

**Context-aware response**:
```
I can see you're drafting a comment in favor of the Berkeley housing proposal
(agenda item 5). Based on AB 1147 (Affordable Housing) which you have open:

1. The bill requires 20% affordable units for developments over 10 units
2. Your event references AB 1147 compliance for the proposed project
3. 15 people in the discussion thread have raised concerns about affordability

I can help you add a section citing AB 1147's requirements. Would you like me to:
- Add a new section referencing the bill's 20% requirement?
- Inject specific legislative language?
- Connect your comment to points raised in the discussion?
```

### Scenario 2: Civic Coaching with History (Phase 3-4)

**User workflow**:
1. User has attended 3 previous meetings
2. Submitted 2 public comments
3. Following 4 issues
4. Currently viewing new housing event

**Context state** (includes PersonalizationService data):
```typescript
[
    {
        id: 'ctx-current',
        type: 'event',
        priority: 'primary',
        metadata: {
            title: 'Berkeley Housing - Jan 2025',
            event: {
                meeting_date: '2025-01-15'
            }
        }
    },
    // PLUS civic history from PersonalizationService
    {
        id: 'ctx-history',
        type: 'user_profile',
        priority: 'background',
        metadata: {
            civic_history: {
                attended_meetings: 3,
                submitted_comments: 2,
                topics_engaged: ['housing', 'transportation'],
                expertise_level: 'intermediate'
            }
        }
    }
]
```

**Chat query**: "Should I attend this meeting?"

**Context-aware coaching**:
```
Based on your civic history (3 meetings attended, 2 comments on housing),
this meeting is highly relevant:

1. Topic alignment: You've engaged with housing before (2 prior comments)
2. Continuation: This is a follow-up to the Dec 2024 meeting you attended
3. Impact: One of your followed issues (#42 - 5th Ave Housing) is on the agenda

I recommend attending because:
- You have context from previous meetings
- Your expertise (intermediate level) makes your input valuable
- The 5th Ave issue you're following needs community support

Would you like me to:
- Draft a public comment based on your previous comments?
- Set a calendar reminder?
- Connect you with the 8 other people following issue #42?
```

---

## Open Questions & Future Work

### 1. Context Prioritization Algorithm

Current: Simple priority levels (primary, secondary, reference, background)

**Future**: ML-based relevance scoring
```typescript
function scoreContextRelevance(
    element: ContextElement,
    userQuery: string,
    userHistory: CivicHistory
): number {
    return (
        0.4 * semanticSimilarity(element.metadata.summary, userQuery) +
        0.3 * recencyScore(element.accessed_at) +
        0.2 * userInteractionScore(element.user_signals) +
        0.1 * topicAlignmentScore(element.metadata.topics, userHistory.topics)
    );
}
```

### 2. Context Compression

For large contexts (Phase 4+), consider:
- LLM-based summarization of old context elements
- Hierarchical context (summary → full details on demand)
- Differential context (send only changes between messages)

### 3. Cross-Session Context

Should context persist across browser sessions?
- **Pro**: Continuity (resume drafts, remember open tabs)
- **Con**: Privacy concerns, stale data

**Proposal**: Opt-in persistent context with 24h TTL

### 4. Collaborative Context

Future: Multiple users working on same proposal
- Shared context registry
- Real-time context sync (Socket.io)
- Conflict resolution (who added/removed context)

---

## Integration with Existing Systems

### PersonalizationService Integration

```typescript
// Enrich context with user profile data
function enrichWithPersonalization(
    context: ContextElement[],
    userId: string
): ContextElement[] {
    const profile = personalizationService.getUserProfile(userId);
    const history = personalizationService.getCivicHistory(userId);

    // Add user profile as background context
    context.push({
        id: 'user-profile',
        type: 'user_profile',
        priority: 'background',
        metadata: {
            title: 'Your Civic Profile',
            summary: `Engaged with ${history.length} civic actions`,
            topics: profile.interests
        },
        data: { profile, history }
    });

    return context;
}
```

### Chat Router Integration

```typescript
// src/civic_chat_router.py (updated)
@app.post("/api/chat/route")
async def route_chat(request: ChatRequest):
    # Receive context from frontend
    context_elements = request.context

    # Enrich with personalization
    if request.user_id:
        context_elements = enrich_with_personalization(
            context_elements,
            request.user_id
        )

    # Filter by mode
    mode_config = CHAT_MODES[request.mode]
    active_context = filter_context_by_mode(context_elements, mode_config)

    # Serialize for LLM
    context_str = serialize_context_for_llm(active_context)

    # Build system prompt
    system_prompt = f"{mode_config.system_prompt}\n\nCurrent context:\n{context_str}"

    # Route with function calling
    response = await openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            *request.messages
        ],
        functions=get_functions_for_mode(request.mode)
    )

    return response
```

---

## Success Metrics

### Phase 2-3 (Explicit Context)
- **Context accuracy**: % of time LLM references correct artifacts (target: >95%)
- **User control**: % of users who manually add/remove context (target: >20%)
- **Multi-artifact usage**: % of conversations with 2+ context elements (target: >30%)

### Phase 4 (Advanced Features)
- **Auto-link value**: % of auto-linked context used in responses (target: >50%)
- **Context efficiency**: Avg tokens saved by mode-aware filtering (target: 20-30%)
- **Workflow completion**: % of multi-document workflows completed (target: >60%)

### Phase 5 (Semantic Retrieval)
- **Search relevance**: User ratings of semantic search results (target: >4/5)
- **Cost efficiency**: Cost per search vs. value delivered (target: <$0.001 per valuable result)
- **Query complexity**: % of queries that benefit from semantic search (target: >40%)

---

## Conclusion

This context management architecture provides:

1. **Future-proof schema**: Works with key-value, structured query, and semantic retrieval
2. **Incremental implementation**: Build Phase 1-2 now, evolve to Phase 3-5 later
3. **Zero migration cost**: Additive schema changes only (embeddings are optional)
4. **Industry-standard patterns**: Compatible with MCP, LangChain, vector DBs
5. **Foundation-ready narrative**: "Sophisticated context management enables democratic participation toolkit"

**Next steps**:
1. Review and approve schema design
2. Implement Phase 1 (context indicators) in Sessions 52-53
3. Implement Phase 2 (context registry) in Sessions 54-56
4. Update `CHAT_STRATEGY_ROADMAP.md` with context evolution
5. Update `next_session_prompt.md` with Phase 1 implementation guide

---

## Appendix A: TypeScript Type Definitions

See separate file: `src/types/context.ts`

## Appendix B: Backend Schema (Python)

See separate file: `src/schemas/context.py`

## Appendix C: Migration Scripts

See: `migrations/context_v1_to_v1_1.ts`
