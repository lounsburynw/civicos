# Recommended: Civic Web Components — Phase 4 (Comment Thread)

**Priority:** P0 (`civic_web_components`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 3 is complete (commit `5bfb189`). The `@civicos/components` package now has 5 components:
- `<civic-voice-buttons>` — Support/Oppose/Watch (Phase 1)
- `<civic-synthesis-bar>` — stacked bar chart (Phase 1)
- `<civic-agenda-item-card>` — agenda item with tags, voice counts (Phase 2)
- `<civic-decision-card>` — expandable decision with testimony, council, AI callbacks (Phase 2)
- `<civic-initiative-card>` — initiative with actions, progress, commit/complete buttons (Phase 3)

SidePanel is at **5261 lines** (down from ~5540). Standalone bundle is 146KB. Both packages build clean.

## Recommended Task — Phase 4

Extract the comment thread from SidePanel into `<CivicCommentThread>`. This is the highest-complexity extraction — the thread section (lines 2051-2187, ~135 lines of template) includes AI drafting, enrichment, synthesis, and compose state.

### `<civic-comment-thread>` (recommended scope)
- Toggle button with comment count + attested count + email clerk link
- Thread container: loading state, comment list with stance coloring, synthesis bar
- AI features: summarize thread button + AI response display
- Compose area: textarea with AI draft/enrich buttons, char counter, submit/update
- Already composes `<CivicSynthesisBar>` internally

### What to EXCLUDE (keep in parent):
- `toggleCommentThread()` function (lines 411-447) — fetches comments, manages state
- `handleSubmitComment()` function (lines 449+) — submits via session
- `handleDraftWithAI()` / `handleEnrichDraft()` — AI orchestration
- `composeThreadSummary()` — builds AI prompt
- All these stay in parent as callbacks; the component fires events

### Props
```typescript
{
  entityId: string;
  comments?: Comment[];
  commentCount?: number;
  attestedCount?: number;
  synthesis?: { support: number; oppose: number; neutral: number } | null;
  expanded?: boolean;
  loading?: boolean;
  error?: string;
  draft?: string;
  userPublicKey?: string;
  isUnlocked?: boolean;
  hasIdentity?: boolean;
  aiAvailable?: boolean;
  activeProviderName?: string;
  draftLoading?: boolean;
  enrichLoading?: boolean;
  summarizeLoading?: boolean;
  summaryHtml?: string;
  clerkEmail?: string;
  itemTitle?: string;  // for mailto link
  showEmailClerk?: boolean;
  commentEligible?: boolean;
  ontoggle?: () => void;
  onsubmit?: (detail: { text: string }) => void;
  ondraftchange?: (detail: { text: string }) => void;
  ondraft?: () => void;
  onenrich?: () => void;
  onsummarize?: () => void;
}
```

## Key Files

- `packages/civicos-components/src/components/CivicInitiativeCard.svelte` — Phase 3 pattern (most recent)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:2051-2187` — comment thread template to extract
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:411-447` — `toggleCommentThread()` (stays in parent)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:449-500` — `handleSubmitComment()` (stays in parent)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:4218-4420` — comment thread CSS (approx range)
- `packages/civicos-components/src/components/CivicSynthesisBar.svelte` — already a component, compose internally
- `packages/civicos-components/src/index.ts` — register new component
- `packages/civicos-client/src/types.ts` — `Comment`, `CommentCounts`, `CommentSynthesis` types

## Technical Notes

- Component renders the full comment section (toggle + thread + compose) — parent provides no wrapper
- The compose textarea has two-way binding via `ondraftchange` callback (parent stores draft in Map)
- `getUserComment()` logic (check if user has existing comment) can be a `$derived` inside the component
- Thread already uses `<CivicSynthesisBar>` — import as sibling component
- AI draft/enrich/summarize: fire callbacks, parent handles orchestration
- The `getMailtoLink(item)` function stays in parent — pass computed mailto href as prop, or pass email + title
- `renderMarkdown()` used for AI summary — pass pre-rendered HTML (same pattern as DecisionCard)

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile
cd apps/civicos-extension && npm run build         # Extension still works
```

## Success Criteria

- [ ] `<civic-comment-thread>` renders toggle with comment count
- [ ] Expanded shows comment list with stance coloring and attested badges
- [ ] Synthesis bar renders when data available (composes CivicSynthesisBar)
- [ ] Compose area with textarea, char counter, submit button
- [ ] AI draft/enrich/summarize buttons fire callbacks
- [ ] Email clerk link works
- [ ] Extension SidePanel uses the comment thread component
- [ ] Both packages build clean
- [ ] Standalone demo updated with comment thread example
