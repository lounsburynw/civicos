# Recommended: Civic Journal Phase 2 — AI-Suggested Updates

**Priority:** P0 is `turnkey_city_deployment` (deferred). Recommend this instead — completes the edge intelligence feedback loop.
**Area:** edge_intelligence > browser_extension
**Date:** 2026-03-05

> This is recommended context from Session 22. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 22 built Phase 1 of the Civic Journal — a markdown context document (AGENTS.md paradigm) that replaced 7 structured profile fields. Settings now has just Name + Civic Journal with edit/preview, import/export, and a 9-section template. The journal flows to both cloud (CivicOS proxy) and local (Ollama) AI paths. Everything works end-to-end.

The missing piece: nothing writes back. The user manually maintains the journal. Phase 2 adds AI-suggested updates based on session activity.

## What Session 22 Built
- Civic Journal with markdown edit/preview tabs in Settings
- Pre-populated 9-section template (care about, support, frustrations, following, vision, civic history, trusted orgs, engagement style, perspective)
- Export/import as `.md`, reset to template
- `ChatUserContext` simplified to just `{ journalNotes?: string }`
- Journal context injected into both CivicOS proxy AND Ollama system prompts
- Removed all structured profile fields except Name
- Fixed pre-existing bug: Pydantic camelCase alias mapping

## Recommended Task

Build a mechanism where the AI proposes journal updates after interactions, batched and user-approved.

**Design constraints (from discussion with user):**
- Never auto-write to the journal — user owns the document
- Batch suggestions (not after every interaction) to avoid notification fatigue
- User must approve/dismiss proposed changes
- Use a sensible heuristic for when to suggest (e.g., every N interactions, or when new topics detected)

**Suggested approach:**
1. Track interaction topics in `chrome.storage.session` (ephemeral, per-browser-session)
2. After N chat/draft interactions (e.g., 5), compare topics against journal content
3. Generate suggested additions: "Add 'parking impact' to What I care about?"
4. Show suggestions in a non-intrusive UI (e.g., banner in SidePanel or notification in Settings)
5. User accepts (appends to journal + saves) or dismisses

## Key Files
- `apps/civicos-extension/src/options/Options.svelte` — Journal UI (edit/preview/save)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:148` — `buildUserContext()` reads journal
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:264` — `loadJournal()` from storage
- `packages/civicos-client/src/ai/types.ts:22` — `ChatUserContext { journalNotes?: string }`
- `packages/civicos-client/src/ai/providers/ollama.ts:132` — Ollama journal injection
- `packages/civicos-services/.../routers/ai_proxy.py:307` — Server journal injection
- `packages/civicos-client/src/session.ts:204` — `chat()` orchestration
- `packages/civicos-services/.../storage/personalization_service.py` — UNUSED, candidate for deletion

## Edge Intelligence Status (as of Session 22)

| Capability | Status |
|---|---|
| AI Providers (6) | WORKING |
| Chat (tool-backed) | WORKING |
| Draft Comments | WORKING |
| Journal → Cloud AI | WORKING |
| Journal → Local AI (Ollama) | WORKING |
| Identity/Nostr Auth | WORKING |
| Attestation Gating | WORKING |
| Feedback → Journal | NOT BUILT (this task) |
| PersonalizationService | UNUSED (delete candidate) |

## Success Criteria
- [ ] Interaction topics tracked in ephemeral storage
- [ ] After N interactions, AI generates journal update suggestions
- [ ] Suggestions shown to user in non-intrusive UI
- [ ] User can accept (journal updated + saved) or dismiss
- [ ] No auto-writes — journal remains user-owned
