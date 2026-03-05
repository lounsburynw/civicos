/**
 * Model-agnostic prompt composition for AI drafting.
 *
 * These produce plain text strings — any AIProvider can call complete(text).
 */

import type { PulseAgendaItem, VoiceCounts, ContextBundle } from '../types.js';
import type { ChatUserContext } from './types.js';

type Stance = 'support' | 'oppose' | 'watching';

/** @deprecated Use ChatUserContext instead */
export type DraftUserContext = ChatUserContext;

export const SYSTEM_PROMPT =
  'You are a civic engagement assistant. Draft concise, respectful public comments for local government agenda items. Focus on community impact and specific concerns. Keep comments under 400 characters. Write in first person as a concerned resident. Do not use hashtags or emojis.';

export const QA_SYSTEM_PROMPT =
  'You are a knowledgeable civic engagement assistant helping residents understand local government. Explain agenda items, decisions, and public testimony in clear, accessible language. Be concise but thorough. Use bullet points for key takeaways when helpful. When community sentiment data is provided (stances, public comments, testimony), weave it into your response — summarize what residents are saying, identify key themes and concerns, and note any points of agreement or disagreement. Present sentiment as community voice, not statistics.';

export function composeDraftPrompt(
  item: PulseAgendaItem,
  stance?: Stance,
  counts?: VoiceCounts,
  userContext?: DraftUserContext,
): string {
  const lines: string[] = [
    `Draft a public comment for this agenda item:`,
    '',
    `Title: ${item.title}`,
    `Meeting: ${item.meeting_title} (${item.meeting_date})`,
  ];

  if (item.item_number) lines.push(`Item #${item.item_number}`);
  if (item.project_type) lines.push(`Type: ${item.project_type}`);
  if (item.description) lines.push(`Description: ${item.description}`);
  if (item.why_it_matters) lines.push(`Why it matters: ${item.why_it_matters}`);

  if (counts && counts.total > 0) {
    lines.push(
      `Community sentiment: ${counts.support} support, ${counts.oppose} oppose, ${counts.watching} watching`,
    );
  }

  if (userContext) {
    const parts: string[] = [];
    if (userContext.neighborhood) parts.push(`lives in ${userContext.neighborhood}`);
    if (userContext.district) parts.push(`is in ${userContext.district}`);
    if (userContext.yearsInArea) parts.push(`has lived here ${userContext.yearsInArea} years`);
    if (userContext.stakes && userContext.stakes.length > 0) parts.push(`is a ${userContext.stakes.join(', ')}`);
    if (userContext.expertise) parts.push(`has expertise in ${userContext.expertise}`);
    if (userContext.interests && userContext.interests.length > 0) parts.push(`cares about ${userContext.interests.join(', ')}`);
    if (parts.length > 0) lines.push(`The commenter ${parts.join(', ')}.`);
  }

  if (stance) {
    const stanceLabel = stance === 'support' ? 'in support of' : stance === 'oppose' ? 'opposing' : 'watching/neutral on';
    lines.push('', `Write the comment from the perspective of a resident ${stanceLabel} this item.`);
  } else {
    lines.push('', 'Write a neutral, constructive comment asking for clarity on community impact.');
  }

  return lines.join('\n');
}

export function composeEnrichPrompt(draft: string, context: ContextBundle): string {
  const lines: string[] = [
    'Rewrite this public comment incorporating the additional context below.',
    'Keep the same stance and tone but add specific references from the context.',
    'Stay under 400 characters.',
    '',
    '--- Current draft ---',
    draft,
    '',
    '--- Additional context ---',
  ];

  if (context.sections?.history) {
    const h = context.sections.history;
    if (h.related_decisions && h.related_decisions.length > 0) {
      lines.push('Related decisions:');
      for (const d of h.related_decisions.slice(0, 3)) {
        lines.push(`- ${d.title} (${d.outcome || 'pending'}, ${d.date || 'no date'})`);
      }
    }
    if (h.summary) lines.push(`History: ${h.summary}`);
  }

  if (context.sections?.regulatory) {
    const r = context.sections.regulatory;
    if (r.applicable_codes && r.applicable_codes.length > 0) {
      lines.push('Applicable codes:');
      for (const c of r.applicable_codes.slice(0, 3)) {
        lines.push(`- ${c.title}: ${c.summary || c.code_ref || ''}`);
      }
    }
  }

  if (context.sections?.testimony) {
    const t = context.sections.testimony;
    if (t.public_comments && t.public_comments.length > 0) {
      lines.push(`Public testimony (${t.public_comments.length} speakers):`);
      for (const c of t.public_comments.slice(0, 3)) {
        lines.push(`- ${c.speaker}: ${c.text.slice(0, 150)}`);
      }
    }
  }

  lines.push('', '--- Rewritten comment ---');
  return lines.join('\n');
}
