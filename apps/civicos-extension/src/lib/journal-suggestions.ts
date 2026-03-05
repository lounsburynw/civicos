/**
 * Journal Suggestions — AI-suggested updates based on chat interactions.
 *
 * Tracks chat interactions in chrome.storage.session (ephemeral, per browser session).
 * After a threshold of interactions, generates journal update suggestions via AI.
 * User must explicitly accept suggestions — no auto-writes.
 */

const INTERACTIONS_KEY = 'civicos_journal_interactions';
const DISMISSED_KEY = 'civicos_journal_dismissed_topics';
const INTERACTION_THRESHOLD = 5;

export interface TrackedInteraction {
  question: string;
  toolUsed?: string;
  timestamp: number;
}

export interface JournalSuggestion {
  text: string;
  section: string;
}

/** Record a chat interaction. Returns true if threshold reached (time to suggest). */
export async function trackInteraction(question: string, toolUsed?: string): Promise<boolean> {
  const interaction: TrackedInteraction = { question, toolUsed, timestamp: Date.now() };

  const stored = await chrome.storage.session.get(INTERACTIONS_KEY);
  const interactions: TrackedInteraction[] = stored[INTERACTIONS_KEY] || [];
  interactions.push(interaction);
  await chrome.storage.session.set({ [INTERACTIONS_KEY]: interactions });

  return interactions.length >= INTERACTION_THRESHOLD && interactions.length % INTERACTION_THRESHOLD === 0;
}

/** Get tracked interactions since last suggestion batch. */
export async function getRecentInteractions(): Promise<TrackedInteraction[]> {
  const stored = await chrome.storage.session.get(INTERACTIONS_KEY);
  return stored[INTERACTIONS_KEY] || [];
}

/** Clear tracked interactions (after suggestions generated). */
export async function clearInteractions(): Promise<void> {
  await chrome.storage.session.remove(INTERACTIONS_KEY);
}

/** Get previously dismissed topics to avoid re-suggesting. */
async function getDismissedTopics(): Promise<string[]> {
  const stored = await chrome.storage.local.get(DISMISSED_KEY);
  return stored[DISMISSED_KEY] || [];
}

/** Save a dismissed topic so we don't re-suggest it. */
export async function dismissTopic(topic: string): Promise<void> {
  const dismissed = await getDismissedTopics();
  if (!dismissed.includes(topic.toLowerCase())) {
    dismissed.push(topic.toLowerCase());
    // Keep last 50 dismissed topics
    const trimmed = dismissed.slice(-50);
    await chrome.storage.local.set({ [DISMISSED_KEY]: trimmed });
  }
}

/**
 * Build the prompt that asks the AI to generate journal suggestions.
 * Returns null if there's nothing meaningful to suggest from.
 */
export function buildSuggestionPrompt(
  interactions: TrackedInteraction[],
  journalText: string,
  dismissedTopics: string[],
): string | null {
  if (interactions.length === 0) return null;

  const interactionSummary = interactions
    .map(i => `- "${i.question}"${i.toolUsed ? ` (${i.toolUsed})` : ''}`)
    .join('\n');

  const dismissedNote = dismissedTopics.length > 0
    ? `\nDo NOT suggest topics related to: ${dismissedTopics.join(', ')}`
    : '';

  return `You are analyzing a user's recent civic AI interactions to suggest updates to their civic journal.

Their journal is a personal document tracking civic interests, concerns, and engagement. Here are the sections:
- What I care about
- What I support
- What frustrates me
- What I'm following
- My vision for the city
- My civic history
- Organizations I trust
- How I engage
- My perspective

CURRENT JOURNAL:
${journalText || '(empty — no journal content yet)'}

RECENT INTERACTIONS (${interactions.length} queries):
${interactionSummary}
${dismissedNote}

Based on the gap between what they've been asking about and what's already in their journal, suggest 1-3 specific additions. Only suggest topics that are clearly new — not already covered by the journal.

Respond ONLY with a JSON array (no markdown, no explanation). Each item: {"text": "specific topic to add", "section": "exact section name from the list above"}

If there are no meaningful new topics to suggest, respond with an empty array: []`;
}

/**
 * Parse the AI response into JournalSuggestion objects.
 * Handles various response formats gracefully.
 */
export function parseSuggestions(response: string): JournalSuggestion[] {
  try {
    // Strip markdown code fences if present
    let cleaned = response.trim();
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
    }

    const parsed = JSON.parse(cleaned);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .filter((item: unknown): item is { text: string; section: string } =>
        typeof item === 'object' && item !== null &&
        typeof (item as Record<string, unknown>).text === 'string' &&
        typeof (item as Record<string, unknown>).section === 'string'
      )
      .slice(0, 3); // Cap at 3 suggestions
  } catch {
    return [];
  }
}

/**
 * Generate journal suggestions from recent interactions.
 * Uses the AI manager's complete() method — no tool execution needed.
 */
export async function generateSuggestions(
  askAI: (prompt: string) => Promise<string | null>,
  journalText: string,
): Promise<JournalSuggestion[]> {
  const interactions = await getRecentInteractions();
  const dismissed = await getDismissedTopics();
  const prompt = buildSuggestionPrompt(interactions, journalText, dismissed);
  if (!prompt) return [];

  const response = await askAI(prompt);
  if (!response) return [];

  const suggestions = parseSuggestions(response);
  // Clear interactions after generating suggestions
  await clearInteractions();
  return suggestions;
}
