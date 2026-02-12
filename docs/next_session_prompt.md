# Recommended: Browser Extension — Phase 0 Scaffold

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12
**Previous session:** Context Assembly API (MCP tool + Open WebUI "Chat with this" integration)

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed **context_assembly_api** — the surface-agnostic context assembly layer. Added `get_item_context` MCP tool + REST endpoint (`POST /api/tools/get-item-context`) and integrated "Chat with this decision" / "Chat" buttons into CityPulse in Open WebUI. All 6 context sections (history, regulatory, community, financial, testimony, participation) are live.

The **browser_extension** is now unblocked. It's the primary distribution surface for launch — a Chrome extension that IS the Personal MCP, managing identity, connecting to Jurisdiction MCPs, and injecting civic context into any AI surface (Claude.ai, ChatGPT). Full architecture doc exists.

## Recommended Task: Phase 0 — Extension Scaffold

Phase 0 from `pilot.json` and the architecture doc: **Extension scaffold + tiered identity + NIP-07 provider.** This is the foundation — a Chrome Manifest V3 extension with:
- Side panel placeholder (City Pulse shell)
- Tiered identity: Easy (passphrase → key), Private (Web Crypto), Sovereign (NIP-07 relay)
- Extension popup with identity tier selector
- Service worker background script for future alerting

## Key Files

- `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` — **Full architecture doc** (read this first, ~300 lines)
- `docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md` — Edge intelligence theory
- `apps/civicos-personal-mcp/` — Existing Personal MCP (TypeScript, has signing providers to port)
- `apps/civicos-personal-mcp/src/lib/providers/` — Signing providers (Easy/Private/Sovereign patterns)
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — Dashboard to port to side panel
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — API client (reusable for extension)
- `packages/civicos/src/civicos/registry.py` — Jurisdiction MCP URLs

## Suggested Approach

1. Read `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` thoroughly — it has detailed Phase 0 spec
2. Create extension scaffold at `apps/civicos-extension/` (Chrome Manifest V3)
   - `manifest.json` with side_panel, background service worker, content scripts
   - `src/side-panel/` — Svelte side panel (port CityPulse skeleton)
   - `src/popup/` — Identity tier selector
   - `src/background/` — Service worker
   - `src/lib/` — Shared types, identity, MCP client
3. Implement tiered identity (port from `apps/civicos-personal-mcp/src/lib/providers/`)
   - Easy mode: deterministic key from passphrase (SHA-256 → secp256k1)
   - Private mode: Web Crypto P-256 (existing implementation)
   - Sovereign mode: NIP-07 `window.nostr` provider
4. Wire up basic side panel that fetches City Pulse data from the jurisdiction MCP
5. Build with Vite + Svelte, load as unpacked extension in Chrome

## Tests to Run
```bash
# Context assembly tests (verify nothing broke)
pytest packages/civicos-services/tests/test_context_agent.py -q --override-ini="addopts="

# Personal MCP tests (signing patterns to port)
cd apps/civicos-personal-mcp && npx vitest run
```

## Success Criteria
- [ ] Extension loads in Chrome as unpacked extension
- [ ] Side panel opens and shows basic City Pulse placeholder
- [ ] Identity tier selection works (at least Easy mode generates valid keypair)
- [ ] Can fetch data from jurisdiction MCP endpoint (`https://san-rafael.civicosproject.org`)
- [ ] Extension scaffold committed to `apps/civicos-extension/`

## Also Notable
- **Pilot at 95%** (453/478 items ready) — 23 remaining after context_assembly_api
- **Relay deployment still pending** — action attribution + voice/revoke endpoints committed but not deployed to Modal
- **SQL migration pending** — `scripts/sql/add_action_events.sql` needs to run on relay DB
- **Context assembly needs Modal deploy** — `get_item_context` REST endpoint committed but not yet deployed; run `modal deploy` for `apps/civicos-mcp/modal_mcp.py`
- **Open WebUI changes committed but not pushed** — `aa7ac4c` in civicos-openwebui needs `git push`

## Dev Environment
- Frontend: `cd ~/projects/civicos-openwebui && VITE_CIVICOS_API_URL=http://localhost:8001 npm run dev` (localhost:5173)
- Backend: `./scripts/dev.sh api` (localhost:8001)
- Extension dev: Load unpacked from `apps/civicos-extension/dist/` in `chrome://extensions`
