import type { ContextElement, ContextPriority } from '@/types/context';
import type { CivicEvent, StateBill, FederalProgram } from '@/types/civic';

/**
 * Generate UUID (simple version for client-side)
 */
export function generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

/**
 * Generate content hash (simple SHA-256 using SubtleCrypto)
 */
export async function generateContentHash(data: any): Promise<string> {
    const json = JSON.stringify(data);
    const encoder = new TextEncoder();
    const dataBuffer = encoder.encode(json);

    const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

    return hashHex;
}

/**
 * Create context element from event artifact
 */
export async function createEventContext(
    event: CivicEvent,
    artifactId: string,
    priority: ContextPriority = 'primary'
): Promise<ContextElement> {
    const contentHash = await generateContentHash(event);

    return {
        id: generateUUID(),
        content_version: '1.0',
        content_hash: contentHash,
        type: 'event',
        artifact_id: artifactId,
        source: 'user_opened',
        created_at: new Date(),
        updated_at: new Date(),
        accessed_at: new Date(),
        priority,
        relationships: {
            related: extractRelatedBills(event)
        },
        user_signals: {
            view_duration: 0,
            scroll_depth: 0,
            interaction_count: 0,
            explicit_pin: false
        },
        metadata: {
            title: event.title,
            summary: generateEventSummary(event),
            keywords: extractKeywords(event),
            topics: event.agenda_expansion?.actionable_items?.flatMap(item => item.project_types || []) || [],
            jurisdiction: event.jurisdiction.id,
            event: {
                event_id: event.id,
                title: event.title,
                jurisdiction_id: event.jurisdiction.id,
                meeting_date: new Date(event.when),
                meeting_type: event.meeting_type || 'unknown',
                active_tab: 'details',
                agenda_item_count: event.agenda_expansion?.actionable_items?.length || 0,
                actionable_item_count: event.agenda_expansion?.actionable_items?.filter(item => item.actionable).length || 0
            }
        },
        data: event
    };
}

/**
 * Extract related bill IDs from event
 */
function extractRelatedBills(event: CivicEvent): string[] {
    const bills: string[] = [];

    event.agenda_expansion?.actionable_items?.forEach(item => {
        if (item.legislative_context?.state_legislation_refs) {
            bills.push(...item.legislative_context.state_legislation_refs);
        }
    });

    return [...new Set(bills)]; // Deduplicate
}

/**
 * Generate event summary for context
 */
function generateEventSummary(event: CivicEvent): string {
    const date = new Date(event.when).toLocaleDateString();
    const itemCount = event.agenda_expansion?.actionable_items?.length || 0;
    const actionableCount = event.agenda_expansion?.actionable_items?.filter(item => item.actionable).length || 0;

    return `${event.meeting_type || 'Meeting'} on ${date} with ${itemCount} agenda items (${actionableCount} actionable).`;
}

/**
 * Extract keywords from event
 */
function extractKeywords(event: CivicEvent): string[] {
    const keywords: Set<string> = new Set();

    // Add meeting type
    if (event.meeting_type) {
        keywords.add(event.meeting_type.toLowerCase());
    }

    // Add topics from agenda items
    event.agenda_expansion?.actionable_items?.forEach(item => {
        item.project_types?.forEach(topic => keywords.add(topic));
    });

    return Array.from(keywords);
}

/**
 * Create context element from issue artifact
 */
export async function createIssueContext(
    issue: any,
    artifactId: string,
    priority: ContextPriority = 'primary'
): Promise<ContextElement> {
    const contentHash = await generateContentHash(issue);

    return {
        id: generateUUID(),
        content_version: '1.0',
        content_hash: contentHash,
        type: 'issue',
        artifact_id: artifactId,
        source: 'user_opened',
        created_at: new Date(),
        updated_at: new Date(),
        accessed_at: new Date(),
        priority,
        relationships: {
            related: issue.linked_events || []
        },
        user_signals: {
            view_duration: 0,
            scroll_depth: 0,
            interaction_count: 0,
            explicit_pin: false
        },
        metadata: {
            title: issue.ai_title || issue.short_name || 'Untitled Issue',
            summary: issue.description_preview || issue.description || '',
            keywords: [issue.issue_type || 'issue'],
            topics: [issue.issue_type || 'other'],
            jurisdiction: '', // Issues may not have jurisdiction
            issue: {
                issue_id: issue.id,
                category: issue.issue_type || 'other',
                status: issue.status || 'open',
                linked_events: issue.linked_events || []
            }
        },
        data: issue
    };
}

/**
 * Create context element from thread artifact
 */
export async function createThreadContext(
    thread: any,
    artifactId: string,
    priority: ContextPriority = 'secondary'
): Promise<ContextElement> {
    const contentHash = await generateContentHash(thread);

    return {
        id: generateUUID(),
        content_version: '1.0',
        content_hash: contentHash,
        type: 'thread',
        artifact_id: artifactId,
        source: 'user_opened',
        created_at: new Date(),
        updated_at: new Date(),
        accessed_at: new Date(),
        priority,
        relationships: {
            parent: thread.focal_id // Link to parent event/issue
        },
        user_signals: {
            view_duration: 0,
            scroll_depth: 0,
            interaction_count: 0,
            explicit_pin: false
        },
        metadata: {
            title: thread.title || 'Discussion Thread',
            summary: `Discussion thread with ${thread.message_count || 0} messages`,
            keywords: [thread.focal_type || 'discussion'],
            topics: [],
            jurisdiction: '',
            thread: {
                thread_id: thread.thread_id || thread.id,
                discussion_type: thread.focal_type || 'event',
                message_count: thread.message_count || 0,
                participant_count: thread.participant_count || 0
            }
        },
        data: thread
    };
}

/**
 * Create context element from bill artifact
 */
export async function createBillContext(
    bill: StateBill,
    artifactId: string,
    priority: ContextPriority = 'reference'
): Promise<ContextElement> {
    const contentHash = await generateContentHash(bill);

    return {
        id: generateUUID(),
        content_version: '1.0',
        content_hash: contentHash,
        type: 'bill',
        artifact_id: artifactId,
        source: 'user_opened',
        created_at: new Date(),
        updated_at: new Date(),
        accessed_at: new Date(),
        priority,
        relationships: {},
        user_signals: {
            view_duration: 0,
            scroll_depth: 0,
            interaction_count: 0,
            explicit_pin: false
        },
        metadata: {
            title: bill.title,
            summary: bill.summary || '',
            keywords: [bill.bill],
            topics: bill.topics || [],
            jurisdiction: bill.state || 'CA',
            bill: {
                bill_id: bill.bill,
                bill_number: bill.bill,
                level: 'state',
                status: bill.status || 'unknown',
                topics: bill.topics || []
            }
        },
        data: bill
    };
}

/**
 * Create context element from federal program artifact
 */
export async function createProgramContext(
    program: FederalProgram,
    artifactId: string,
    priority: ContextPriority = 'reference'
): Promise<ContextElement> {
    const contentHash = await generateContentHash(program);

    return {
        id: generateUUID(),
        content_version: '1.0',
        content_hash: contentHash,
        type: 'program',
        artifact_id: artifactId,
        source: 'user_opened',
        created_at: new Date(),
        updated_at: new Date(),
        accessed_at: new Date(),
        priority,
        relationships: {},
        user_signals: {
            view_duration: 0,
            scroll_depth: 0,
            interaction_count: 0,
            explicit_pin: false
        },
        metadata: {
            title: program.program_name,
            summary: program.overview || program.description || '',
            keywords: program.program_id ? [program.program_id] : [],
            topics: program.topics || [],
            jurisdiction: 'US',
            program: {
                program_id: program.program_id || program.program_name,
                program_name: program.program_name,
                level: 'federal',
                topics: program.topics || []
            }
        },
        data: program
    };
}

/**
 * Session 55: Serialize context elements for LLM consumption
 * Converts ContextElement objects to token-efficient summaries
 * Max ~200 tokens per element
 */
export function serializeContextForLLM(elements: ContextElement[]): string {
    if (elements.length === 0) {
        return "No artifacts currently in context.";
    }

    const serialized = elements.map((element, index) => {
        const num = index + 1;
        const title = element.metadata.title;
        const type = element.type;
        const topics = element.metadata.topics.slice(0, 3).join(', ');

        // Type-specific summary
        let summary = '';
        switch (element.type) {
            case 'event':
                const event = element.data as CivicEvent;
                const eventDate = new Date(event.when).toLocaleDateString();
                const agendaItems = event.agenda_expansion?.actionable_items || [];
                const itemCount = agendaItems.length;

                // Session 55: Include agenda item titles so LLM can reason about them
                // Include event_id so LLM can call functions that require it (e.g., explain_event)
                let agendaSummary = `Event ID: ${event.id}\n   Meeting: ${eventDate} in ${event.jurisdiction.name}. ${itemCount} actionable items.`;
                if (agendaItems.length > 0 && agendaItems.length <= 10) {
                    // Include titles for up to 10 items (token-efficient)
                    const itemTitles = agendaItems
                        .map((item: any, idx: number) => `${idx + 1}. ${item.title || 'Untitled'}`)
                        .join('; ');
                    agendaSummary += `\n   Agenda: ${itemTitles}`;
                } else if (agendaItems.length > 10) {
                    agendaSummary += ` (${agendaItems.length} items - see event for full list)`;
                }
                summary = agendaSummary;
                break;
            case 'bill':
                const bill = element.data as StateBill;
                summary = `State bill ${bill.bill}: ${bill.title}. Status: ${bill.status}.`;
                break;
            case 'program':
                const program = element.data as FederalProgram;
                const allocation = program.fy2025_allocation || 'Allocation unknown';
                summary = `Program ID: ${program.program_id}\n   Federal program from ${program.agency}. ${allocation}.`;
                break;
            case 'issue':
                const issue = element.data as any;
                const linkedEvents = issue.linked_events?.length || 0;
                summary = `Issue ID: ${issue.id}\n   User-reported issue. Status: ${issue.status}. ${linkedEvents} matched events.`;
                break;
            case 'thread':
                const thread = element.data as any;
                summary = `Discussion thread with ${thread.participant_count || 0} participants, ${thread.message_count || 0} messages.`;
                break;
            case 'draft':
                const eventTitle = element.metadata.event?.title || 'event';
                summary = `Comment draft for ${eventTitle}.`;
                break;
        }

        return `${num}. [${type.toUpperCase()}] ${title}\n   ${summary}\n   Topics: ${topics || 'none'}`;
    }).join('\n\n');

    return `# Active Context (${elements.length} artifact${elements.length === 1 ? '' : 's'})\n\n${serialized}`;
}
