# Recommended: Civic Context Document — Edge Intelligence v2

**Priority:** P0 is turnkey_city_deployment, but consider this instead — highest-leverage UX gap.
**Date:** 2026-03-05

## The Problem

Session 21 built full profile parity (7 fields in chrome.storage.local, threaded to AI). But the personalization is shallow: flat form fields string-interpolated into a system prompt. The EDGE_INTELLIGENCE_ARCHITECTURE.md envisions a rich edge agent; what exists is a bag of strings.

## The CLAUDE.md Insight

A living context document is better than structured form fields:
- Accumulates understanding over time (not a static form)
- Accepts unstructured input (grievances, news reactions, meeting notes)
- AI reads the full document per interaction, not just 7 flat fields
- Residents who doomscroll about state/national issues have momentum — capture it and connect to local action

## What Exists

1. **Profile fields** (chrome.storage): name, neighborhood, district, yearsInArea, stakes, expertise, interests
2. **System prompt**: "The user lives in X, is a Y, cares about Z"
3. **PersonalizationService** (backend, unused): `infer_civic_interests()`, `get_context_for_ai()` — never called
4. **No behavioral tracking, no unstructured input path**

## Suggested Phasing

**Phase 1: Civic Journal** — free-form text area, timestamped entries in chrome.storage, included in AI context alongside structured fields. "You mentioned frustration about the encampment → this connects to agenda item 4.2 on March 18."

**Phase 2: Implicit Accumulation** — track item expansions, searches, votes. Auto-enrich context: "You've been following the bike lane proposal (3 interactions)."

**Phase 3: AI-Maintained Context** — after each interaction, edge agent updates the user's context doc. Like CLAUDE.md auto-memory for civic participation.

## Key Files
- `apps/civicos-extension/src/options/Options.svelte` — Settings profile UI
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — SidePanel
- `packages/civicos-client/src/ai/types.ts` — ChatUserContext
- `packages/civicos-client/src/ai/prompts.ts` — composeDraftPrompt
- `packages/civicos-services/.../routers/ai_proxy.py` — server system prompt
- `packages/civicos-services/.../storage/personalization_service.py` — unused PersonalizationService
- `docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md` — full vision doc
