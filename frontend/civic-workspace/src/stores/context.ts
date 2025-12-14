import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ContextElement, ContextElementType, ContextQuery, ContextPriority } from '@/types/context';
import { CHAT_MODES, type ChatMode, filterContextByMode } from '@/config/chatModes';

/**
 * Context Store
 *
 * Manages explicit context registry for chat system with mode-aware filtering.
 * Provides key-value lookup (Phase 1-2) with schema ready for
 * structured queries (Phase 3-4) and semantic retrieval (Phase 5+).
 *
 * Session 53: Added mode-aware context filtering (discovery, focus, compare)
 * Session 56: Revised to 3-mode system aligned with Phase 2 capabilities
 */
export const useContextStore = defineStore('context', () => {
    // State
    const registry = ref<Map<string, ContextElement>>(new Map());
    const activeMode = ref<ChatMode>('navigation');  // Default to navigation mode (search and discovery)

    // Indexes for fast queries (Phase 3-4)
    const typeIndex = ref<Map<ContextElementType, Set<string>>>(new Map());
    const relationshipIndex = ref<Map<string, Set<string>>>(new Map());
    const topicIndex = ref<Map<string, Set<string>>>(new Map());

    // Getters
    const allContext = computed(() => {
        // Get all non-expired context (unfiltered)
        return Array.from(registry.value.values())
            .filter(el => !el.expires_at || el.expires_at > new Date())
            .sort((a, b) => scorePriority(a, b));
    });

    const activeContext = computed(() => {
        // Filter by active mode
        return filterContextByMode(allContext.value, activeMode.value);
    });

    const contextCount = computed(() => registry.value.size);

    const primaryContext = computed(() => {
        return allContext.value.filter(el => el.priority === 'primary');
    });

    const modeConfig = computed(() => CHAT_MODES[activeMode.value]);

    // Actions
    function register(element: ContextElement): string {
        // Check for duplicates via content_hash
        const existing = findByContentHash(element.content_hash);
        if (existing) {
            // Update accessed_at timestamp
            update(existing.id, { accessed_at: new Date() });
            return existing.id;
        }

        // Add to registry
        registry.value.set(element.id, element);

        // Update indexes
        updateIndexes(element);

        // Prune stale context if needed
        pruneStaleContext();

        console.log('[ContextStore] Registered:', element.type, element.metadata.title);
        return element.id;
    }

    function unregister(id: string): void {
        const element = registry.value.get(id);
        if (!element) return;

        registry.value.delete(id);
        removeFromIndexes(element);

        console.log('[ContextStore] Unregistered:', element.type, element.metadata.title);
    }

    function update(id: string, updates: Partial<ContextElement>): void {
        const element = registry.value.get(id);
        if (!element) return;

        const updated = {
            ...element,
            ...updates,
            updated_at: new Date()
        };

        registry.value.set(id, updated);
    }

    function get(id: string): ContextElement | undefined {
        const element = registry.value.get(id);
        if (element) {
            // Update accessed_at on retrieval
            update(id, { accessed_at: new Date() });
        }
        return element;
    }

    function findByContentHash(hash: string): ContextElement | undefined {
        return Array.from(registry.value.values()).find(
            el => el.content_hash === hash
        );
    }

    function query(filters: ContextQuery): ContextElement[] {
        // Phase 3-4: Structured query support
        // For now, simple filtering
        let candidates = Array.from(registry.value.values());

        if (filters.types) {
            candidates = candidates.filter(el => filters.types!.includes(el.type));
        }

        if (filters.priority) {
            candidates = candidates.filter(el => filters.priority!.includes(el.priority));
        }

        if (filters.maxAge) {
            const cutoff = Date.now() - parseMaxAge(filters.maxAge);
            candidates = candidates.filter(el => el.accessed_at.getTime() > cutoff);
        }

        if (filters.relatedTo) {
            candidates = candidates.filter(el =>
                el.relationships.related?.includes(filters.relatedTo!)
            );
        }

        if (filters.jurisdiction) {
            candidates = candidates.filter(el =>
                el.metadata.jurisdiction === filters.jurisdiction
            );
        }

        if (filters.topics && filters.topics.length > 0) {
            candidates = candidates.filter(el =>
                filters.topics!.some(topic => el.metadata.topics.includes(topic))
            );
        }

        return candidates
            .sort((a, b) => scorePriority(a, b))
            .slice(0, filters.limit || 10);
    }

    function clear(): void {
        registry.value.clear();
        typeIndex.value.clear();
        relationshipIndex.value.clear();
        topicIndex.value.clear();
    }

    function setMode(mode: ChatMode, reason?: string): void {
        const previousMode = activeMode.value;
        activeMode.value = mode;

        // Enhanced logging for transparency (Session 53)
        // TODO Session 55-56: Add chat-visible mode change messages
        const modeConfig = CHAT_MODES[mode];
        console.log(
            `%c[Context Mode] ${previousMode} → ${mode}`,
            'color: #268bd2; font-weight: bold',
            `\n  Description: ${modeConfig.description}`,
            `\n  Max Elements: ${modeConfig.maxElements}`,
            reason ? `\n  Reason: ${reason}` : ''
        );
    }

    // Helper functions
    function updateIndexes(element: ContextElement): void {
        // Type index
        if (!typeIndex.value.has(element.type)) {
            typeIndex.value.set(element.type, new Set());
        }
        typeIndex.value.get(element.type)!.add(element.id);

        // Topic index
        element.metadata.topics.forEach(topic => {
            if (!topicIndex.value.has(topic)) {
                topicIndex.value.set(topic, new Set());
            }
            topicIndex.value.get(topic)!.add(element.id);
        });

        // Relationship index
        if (element.relationships.related) {
            element.relationships.related.forEach(relatedId => {
                if (!relationshipIndex.value.has(relatedId)) {
                    relationshipIndex.value.set(relatedId, new Set());
                }
                relationshipIndex.value.get(relatedId)!.add(element.id);
            });
        }
    }

    function removeFromIndexes(element: ContextElement): void {
        typeIndex.value.get(element.type)?.delete(element.id);

        element.metadata.topics.forEach(topic => {
            topicIndex.value.get(topic)?.delete(element.id);
        });

        element.relationships.related?.forEach(relatedId => {
            relationshipIndex.value.get(relatedId)?.delete(element.id);
        });
    }

    function pruneStaleContext(): void {
        // Remove expired context elements
        const now = new Date();
        Array.from(registry.value.values()).forEach(element => {
            if (element.expires_at && element.expires_at < now) {
                unregister(element.id);
            }
        });

        // Limit registry size to 50 elements (keep most recent/high priority)
        if (registry.value.size > 50) {
            const sorted = Array.from(registry.value.values())
                .sort((a, b) => scorePriority(b, a)); // Reverse sort

            const toRemove = sorted.slice(50);
            toRemove.forEach(el => unregister(el.id));
        }
    }

    function scorePriority(a: ContextElement, b: ContextElement): number {
        const priorityScores: Record<ContextPriority, number> = {
            primary: 4,
            secondary: 3,
            reference: 2,
            background: 1
        };

        const aPriority = priorityScores[a.priority] || 0;
        const bPriority = priorityScores[b.priority] || 0;

        if (aPriority !== bPriority) {
            return bPriority - aPriority;
        }

        // Tie-break by accessed_at (more recent first)
        return b.accessed_at.getTime() - a.accessed_at.getTime();
    }

    function parseMaxAge(maxAge: string): number {
        const match = maxAge.match(/^(\d+)([hdw])$/);
        if (!match) return 0;

        const value = parseInt(match[1]);
        const unit = match[2];

        const multipliers: Record<string, number> = {
            h: 3600000,      // hours
            d: 86400000,     // days
            w: 604800000     // weeks
        };

        return value * (multipliers[unit] || 0);
    }

    const store = {
        // State
        registry,
        activeMode,

        // Getters
        allContext,
        activeContext,
        contextCount,
        primaryContext,
        modeConfig,

        // Actions
        register,
        unregister,
        update,
        get,
        findByContentHash,
        query,
        clear,
        setMode
    };

    // DEV ONLY: Expose to window for console testing
    if (import.meta.env.DEV) {
        (window as any).__CIVIC_CONTEXT_STORE__ = store;
        console.log('%c[Context Store] Available at window.__CIVIC_CONTEXT_STORE__', 'color: #268bd2; font-weight: bold');
    }

    // Log initialization
    const initModeConfig = CHAT_MODES[activeMode.value];
    console.log(
        `%c[Context Mode] Initialized to ${activeMode.value}`,
        'color: #268bd2; font-weight: bold',
        `\n  Description: ${initModeConfig.description}`,
        `\n  Max Elements: ${initModeConfig.maxElements}`
    );

    return store;
});
