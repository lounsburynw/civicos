/**
 * Chat Mode Configuration (Revised Session 56)
 *
 * Defines three task-based chat modes aligned with Phase 2 capabilities.
 * Each mode provides context filtering optimized for specific user intents.
 *
 * Phase 2 (Current - Sessions 50-60): Navigation, Focus, Compare
 * Phase 3 (Future - Sessions 60+): Add Draft mode for comment composition
 *
 * Session 56.5: Navigation mode upgraded to Structured Outputs architecture.
 * See: docs/NAVIGATION_MODE_STRUCTURED_OUTPUTS.md
 * See: docs/CHAT_STRATEGY_ROADMAP.md
 * See: docs/CONTEXT_MANAGEMENT_ARCHITECTURE.md
 */

import type { ContextElement } from '@/types/context';

export type ChatMode = 'navigation' | 'focus' | 'compare';

export interface ChatModeConfig {
    name: string;
    description: string;
    contextFilter: (element: ContextElement) => boolean;
    maxElements: number;
    systemPrompt: string;
    icon: string;  // Lucide icon name
}

/**
 * Chat mode definitions with task-based naming
 *
 * Design principle: Mode names match user mental models, not technical concepts.
 * Users think "I want to find meetings" (navigation), not abstract technical modes.
 */
export const CHAT_MODES: Record<ChatMode, ChatModeConfig> = {
    /**
     * NAVIGATION MODE - Finding and exploring content
     * Phase 1 complete (Session 27) - Multi-result search
     * Session 56.5 - Upgraded to Structured Outputs for guaranteed schema compliance
     *
     * Task-based (not artifact-type dependent):
     * - "Find housing meetings in Berkeley" (events)
     * - "Show me zoning bills" (legislation)
     * - "What federal programs support ADUs?" (programs)
     * - User intent: SEARCH/NAVIGATE to content (not focused on specific item yet)
     */
    navigation: {
        name: 'Navigation',
        description: 'Find and explore civic content',
        contextFilter: (el: ContextElement) => el.priority === 'primary',
        maxElements: 5,  // Show multiple search results
        systemPrompt: `You help users navigate to civic content of ANY TYPE (events, bills, programs, issues).

When users are SEARCHING for content:
- Show them MULTIPLE results (open event lists, bill lists, program lists)
- Provide brief summaries to help them choose
- Ask clarifying questions to narrow down options
- Use search_events(), view_legislative_context(), and other navigation functions

The task is NAVIGATION (finding things), not the artifact type. Works for any content type.

Keep responses action-oriented and concise. Your goal is to help them find what they're looking for quickly.`,
        icon: 'search'
    },

    /**
     * FOCUS MODE - Deep dive into specific content
     * Phase 2 current (Session 55) - Single item understanding
     *
     * Task-based (not artifact-type dependent):
     * - "What's this event about?" (event)
     * - "Explain this bill's provisions" (bill)
     * - "How much is this allocation?" (program)
     * - User intent: UNDERSTAND one specific thing deeply
     */
    focus: {
        name: 'Focus',
        description: 'Understand specific content deeply',
        contextFilter: (el: ContextElement) => el.priority === 'primary',
        maxElements: 1,  // Single artifact deep dive
        systemPrompt: `You help users understand ONE specific civic item in detail (event, bill, program, issue, thread).

When a user is viewing ONE THING:
- Provide detailed explanations with civic planning knowledge
- Answer specific questions about details (agenda items, provisions, allocations)
- Reference related context when helpful
- Use your general knowledge to explain civic concepts
- Call explain_event() for FORMATTED lists, use reasoning for explanations

The task is FOCUS (understanding one thing), not the artifact type. Works for any single item.

You're seeing exactly what the user is viewing. Use that context intelligently to provide precise, helpful answers.`,
        icon: 'zoom-in'
    },

    /**
     * COMPARE MODE - Multi-item analysis
     * Phase 2 current (Session 50+) - Cross-reference and synthesis
     *
     * Task-based (not artifact-type dependent):
     * - "Compare AB 1033 and SB 423" (bill ↔ bill)
     * - "How do these three events relate?" (event ↔ event ↔ event)
     * - "What's the connection between this meeting and those bills?" (event ↔ bills)
     * - User intent: ANALYZE relationships between multiple things
     */
    compare: {
        name: 'Compare',
        description: 'Analyze multiple items together',
        contextFilter: (el: ContextElement) => ['primary', 'secondary'].includes(el.priority),
        maxElements: 4,  // Compare 2-4 items flexibly
        systemPrompt: `You help users analyze and compare MULTIPLE civic items of ANY TYPE (events, bills, programs, issues).

When users have MULTIPLE artifacts open (2-4 items):
- Compare and contrast them systematically (works across types!)
- Find connections, patterns, and relationships
- Highlight similarities and differences
- Cite specific details from each artifact
- Cross-reference context (event ↔ bill ↔ program, or event ↔ event, etc.)

The task is COMPARISON (analyzing relationships), not the artifact types. Works for any combination.

Provide analytical responses with clear citations. Help users see the bigger picture across multiple sources.`,
        icon: 'git-compare'
    }
};

/**
 * Get icon name for a chat mode
 */
export function getModeIcon(mode: ChatMode): string {
    return CHAT_MODES[mode]?.icon || 'message-circle';
}

/**
 * Get system prompt for a chat mode
 */
export function getModeSystemPrompt(mode: ChatMode): string {
    return CHAT_MODES[mode]?.systemPrompt || '';
}

/**
 * Filter context elements by mode
 */
export function filterContextByMode(
    elements: ContextElement[],
    mode: ChatMode
): ContextElement[] {
    const config = CHAT_MODES[mode];
    if (!config) return elements;

    return elements
        .filter(config.contextFilter)
        .slice(0, config.maxElements);
}
