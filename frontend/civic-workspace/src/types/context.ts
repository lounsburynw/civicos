/**
 * Context Management Types
 *
 * Future-proof schema compatible with:
 * - Phase 1-2: Key-value lookup
 * - Phase 3-4: Structured queries
 * - Phase 5+: Semantic/vector retrieval
 *
 * See: docs/CONTEXT_MANAGEMENT_ARCHITECTURE.md
 */

export type ContextElementType = 'event' | 'bill' | 'program' | 'thread' | 'draft' | 'issue';
export type ContextPriority = 'primary' | 'secondary' | 'reference' | 'background';

/**
 * Core context element schema
 */
export interface ContextElement {
    // === IDENTITY & VERSIONING ===
    id: string;                      // UUID
    content_version: string;         // Schema version (e.g., "1.0")
    content_hash: string;            // SHA-256 of data field (deduplication)

    // === CORE METADATA ===
    type: ContextElementType;
    artifact_id: string;             // Corresponds to workspace artifact
    source: string;                  // "user_opened" | "auto_linked" | "chat_search"

    // === TEMPORAL TRACKING ===
    created_at: Date;
    updated_at: Date;
    accessed_at: Date;
    expires_at?: Date;               // Optional TTL

    // === PRIORITY & RELATIONSHIPS ===
    priority: ContextPriority;
    relationships: {
        parent?: string;             // Parent context element ID
        children?: string[];         // Child element IDs
        related?: string[];          // Related element IDs
        supersedes?: string;         // Replaces older element
    };

    // === USER INTERACTION SIGNALS ===
    user_signals: {
        view_duration?: number;      // Seconds artifact was visible
        scroll_depth?: number;       // 0-1, how far user scrolled
        interaction_count?: number;  // Clicks, selections, edits
        explicit_pin?: boolean;      // User explicitly pinned
        explicit_exclude?: boolean;  // User explicitly removed
    };

    // === RICH METADATA ===
    metadata: {
        title: string;
        summary: string;             // 1-2 sentence summary
        keywords: string[];
        topics: string[];            // Civic topics
        jurisdiction: string;

        // Type-specific metadata
        event?: EventContextMetadata;
        bill?: BillContextMetadata;
        program?: ProgramContextMetadata;
        thread?: ThreadContextMetadata;
        draft?: DraftContextMetadata;
        issue?: IssueContextMetadata;
    };

    // === STRUCTURED DATA ===
    data: any;                       // Full artifact data
}

/**
 * Event-specific context metadata
 */
export interface EventContextMetadata {
    event_id: string;
    title: string;
    jurisdiction_id: string;
    meeting_date: Date;
    meeting_type: string;
    active_tab: 'details' | 'discussion' | 'drafts';

    // Sub-context
    selected_agenda_items?: string[];
    agenda_item_count: number;
    actionable_item_count: number;

    // Draft state
    active_draft?: {
        draft_id: string;
        position: string;
        has_research: boolean;
    };
}

export interface BillContextMetadata {
    bill_id: string;
    bill_number: string;
    level: 'state' | 'federal';
    status: string;
    topics: string[];
}

export interface ProgramContextMetadata {
    program_id: string;
    program_name: string;
    level: 'federal' | 'state' | 'local';
    topics: string[];
}

export interface ThreadContextMetadata {
    thread_id: string;
    discussion_type: 'event' | 'issue';
    message_count: number;
    participant_count: number;
}

export interface DraftContextMetadata {
    draft_id: string;
    event_id: string;
    position: string;
    word_count: number;
    has_research: boolean;
    selected_items: string[];
}

export interface IssueContextMetadata {
    issue_id: string;
    category: string;
    status: string;
    linked_events: string[];
}

/**
 * Query interface for context retrieval
 */
export interface ContextQuery {
    types?: ContextElementType[];
    priority?: ContextPriority[];
    maxAge?: string;                 // e.g., "24h", "7d"
    minDate?: Date;
    relatedTo?: string;              // Element ID
    jurisdiction?: string;
    topics?: string[];
    limit?: number;
}
