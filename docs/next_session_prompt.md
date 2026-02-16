# Recommended: Extension UX Parity Audit — Open WebUI vs Side Panel

**Priority:** P0 (`extension_ux_parity`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-16

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Two sessions polished the extension's Claude MCP flow: AI action row (`[✦ Gemini] [Claude ↗]`), markdown rendering, sentiment enrichment, connector setup banner, and claude-bridge content script. Banner race condition is fixed, bridge has platform-aware shortcuts + dismiss button, clipboard error handling works. User validated the full flow works end-to-end.

**What remains** for `extension_ux_parity`: the extension side panel needs to match the Open WebUI CityPulse feature set. This is the original scope of the P0 item.

## Recommended Task

**Audit the Open WebUI CityPulse component against the extension side panel and close the feature gaps.**

### Gap Areas to Investigate

1. **Form field parity** — validation, hints, field types (e.g., Create Initiative form)
2. **Conditional rendering** — auth gates, tier checks, role-based sections (extension has identity tiers: easy/private)
3. **Loading/error states** — skeletons, retry logic, empty states (some exist, may be incomplete)
4. **Interaction patterns** — expand/collapse, hover effects, transitions

## Key Files

**Extension side panel:**
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — the entire side panel (~4400 lines)
- `apps/civicos-extension/src/lib/types.ts` — type definitions
- `apps/civicos-extension/src/lib/api.ts` — API client

**Open WebUI CityPulse (comparison target):**
- `~/projects/civicos-openwebui/src/lib/components/chat/CityPulse.svelte` — main CityPulse component
- Look for sub-components in the same directory

## What Works Now (Extension)

- **City Pulse dashboard**: meetings, agenda items, decisions, budget
- **Identity**: easy (email-verified) and private (wallet/passkey) tiers with inline unlock
- **Voice/Stances**: support/oppose/watching on agenda items and decisions
- **Comments**: threaded comments with synthesis
- **AI**: Ask AI (local provider) + Claude ↗ (external) peer buttons with markdown responses
- **Connector setup**: MCP banner with guided Claude.ai setup
- **Initiatives**: create/browse community initiatives
- **Map + charts**: Leaflet map for issues, Chart.js doughnut for budget
- **Commitments**: track personal action commitments

## Suggested Approach

1. **Read CityPulse.svelte** in Open WebUI fork — catalog every section, feature, and interaction pattern
2. **Compare against SidePanel.svelte** — identify missing features, inferior patterns, or missing states
3. **Prioritize gaps** — focus on user-visible features first (forms, loading states, error handling)
4. **Implement the highest-impact gaps** — aim for 3-5 meaningful improvements per session
5. **Build and verify**: `cd apps/civicos-extension && npm run build && npm run typecheck`

## Success Criteria

- [ ] Audit document listing all feature gaps between CityPulse and extension
- [ ] At least 3 high-impact gaps closed (e.g., form validation, loading skeletons, error retry)
- [ ] Extension builds clean (vite + tsc)
- [ ] User can load extension and see improved UX parity

## Uncommitted Changes

There are uncommitted changes from this session and the previous one. Stage and commit before starting new work:

```bash
git diff --name-only  # Review what's changed
# Key files: SidePanel.svelte, claude-bridge.ts, pilot.json, claude-progress.txt
# Plus from previous session: package.json, prompts.ts, next_session_prompt.md
```
