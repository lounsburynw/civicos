# Handoff: Browser Extension Phase 4 — Lightning/Cashu Micropayments

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> Session 585 completed Phase 3 (AI + visualizations). Phase 4 adds micropayments to create a sustainable economic model.

## What Was Completed (Sessions 581-585)

Phases 1-3 of the browser extension are all built and committed:
- **Phase 1:** City Pulse feed (meetings, agenda items, decisions, community issues)
- **Phase 1b:** Decision detail expansion, data provenance, voice counts
- **Phase 2:** Voice submission with Nostr signing (support/oppose/watch)
- **Phase 2b:** Initiatives, civic actions, commitments + CORS fix
- **Phase 3:** AI context injection, testimony summarization, Leaflet issue map, Chart.js budget chart

**Extension size:** 356KB JS, 34KB CSS (112KB + 10KB gzipped). Builds clean, all features working.

## Phase 4: Micropayments Architecture

Reference: `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` (payments section)

### Core Concept
- Civic participation (voice, view, commit) is **always free**
- Compute-intensive MCP tools (prepare, suggestions, coordinate) are gated with **L402**
- Users connect Lightning wallets via **NWC (NIP-47)**
- Privacy-preserving relay payments via **Cashu (NIP-60/61)**

### Features to Implement

1. **L402 Middleware (server-side)**
   - Add L402 challenge/response middleware to Jurisdiction MCP HTTP server
   - Gate compute-intensive endpoints: `compose-public-comment`, `neighborhood-report`, `comment-synthesis`
   - Free endpoints remain ungated: `city-pulse`, `decision-detail`, `voice-counts`, `issue-geography`, `budget-summary`
   - MCP server lives in `apps/civicos-mcp/rest_api.py` and `apps/civicos-mcp/modal_mcp.py`

2. **NWC Client (extension)**
   - NWC (Nostr Wallet Connect, NIP-47) client in the browser extension
   - User enters wallet connection string in Options page
   - Extension can request payments on behalf of user
   - Store connection in `chrome.storage.local` (encrypted)

3. **Cashu Wallet (extension)**
   - NIP-60/61 Cashu ecash tokens for privacy-preserving relay payments
   - Mint integration for token issuance
   - Token spending for relay operations

4. **Spending Controls (extension UI)**
   - Per-request threshold (auto-approve below X sats)
   - Daily spending limit
   - Transaction history in Options page
   - Clear confirmation dialog for larger payments

5. **Graceful Degradation**
   - Free tier always works without any wallet configured
   - Gated features show "Upgrade" button instead of results
   - Progressive disclosure: show what you'd get, offer to connect wallet

### Key References
- L402 docs: https://docs.lightning.engineering/the-lightning-network/l402
- NWC (NIP-47): https://nips.nostr.com/47
- Cashu (NIP-60): https://nips.nostr.com/60
- Alby MCP example: https://github.com/getAlby/mcp
- Sustainability model: `docs/funding/SUSTAINABILITY_MODEL.md`

### Key Files
- `apps/civicos-mcp/rest_api.py` — REST API endpoints (add L402 middleware here)
- `apps/civicos-mcp/modal_mcp.py` — Modal deployment config
- `apps/civicos-extension/src/options/Options.svelte` — Add wallet connection UI
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — Add upgrade prompts
- `apps/civicos-extension/src/lib/api.ts` — Add L402 payment flow to API client
- `apps/civicos-extension/src/background/service-worker.ts` — Handle NWC messages

### Constraints
- Foundation-funded (<$7/month operational)
- Payments must be optional — never block civic participation
- Extension must work fully offline for free-tier features
- Lightning payments should be sub-second for good UX

### Suggested Approach
1. Start with L402 middleware on the server (simplest, no extension changes yet)
2. Add NWC client to extension Options page
3. Wire up API client to handle 402 responses and auto-pay
4. Add Cashu for relay payments (more complex, can be Phase 4b)
5. Add spending controls and transaction history

## pilot.json Status
- `extension_phase4_micropayments`: P0, not_ready
- All Phase 1-3 items: ready
