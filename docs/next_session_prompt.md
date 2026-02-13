# Recommended: Browser Extension Phase 2 — Voice Submission + Relay Integration

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context
Session 582 completed Phase 1b: the extension side panel now has expandable decision detail (with testimony), calendar buttons (Google Cal + .ics), data provenance panel, past meeting badges, and voice count display. All 5 read-only enhancements build cleanly. The user wants to continue with Phase 2: voice submission.

| Phase | Item | Priority | Status |
|---|---|---|---|
| Phase 1 | `extension_phase1_city_pulse` | P1 | **ready** |
| Phase 1b | `extension_phase1b_read_enhancements` | P1 | **ready** |
| **Phase 2** | **`extension_phase2_voice_signing`** | **P0** | **not_ready** (NEXT) |
| Phase 2b | `extension_phase2b_commitments` | P1 | not_ready |
| Phase 3 | `extension_phase3_ai_viz` | P2 | not_ready |

## Recommended Task
Add Support/Oppose/Watch buttons to agenda items and decisions. Sign voice events via the service worker's existing `SIGN_EVENT` handler. Submit to the relay coordination API. Include optimistic updates with rollback on failure.

## Key Files
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — main UI (1131 lines), add voice buttons to agenda item and decision cards
- `apps/civicos-extension/src/lib/api.ts` — add `submitVoice()`, `revokeVoice()` calling relay API
- `apps/civicos-extension/src/lib/types.ts` — already has `VoiceCounts` interface
- `apps/civicos-extension/src/lib/messaging.ts:67` — `SIGN_EVENT` message type already defined
- `apps/civicos-extension/src/background/service-worker.ts:87` — `SIGN_EVENT` handler already works (calls `identityManager.signEvent()`)
- `apps/civicos-extension/src/lib/providers/types.ts:13` — `NostrEvent`, `SignedNostrEvent`, `SigningResult` types

### Reference implementation (Open WebUI)
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts:573` — `submitVoice()` function (Kind 30800 event, relay POST)
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts:615` — `revokeVoice()` function
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte:600` — `handleVoice()` with optimistic updates + rollback

## Relay API Endpoints
Base URL: `https://api.civicosproject.org` (env: `CIVICOS_RELAY_URL`)

- `POST /coordination/voice` — Submit voice: `{ entity, stance, public_key, signature, created_at, jurisdiction }`
- `POST /coordination/voice/revoke` — Revoke voice: `{ entity, public_key, signature, created_at }`
- `GET /coordination/voice/counts/{entityId}` — Read counts (already used by Phase 1b)

## Voice Event Structure (Kind 30800)
```typescript
const unsigned: NostrEvent = {
  created_at: Math.floor(Date.now() / 1000),
  kind: 30800,
  tags: [['d', entityId], ['j', jurisdiction], ['stance', stance]],
  content: `civicos:voice:v1:${entityId}:${stance}:${createdAt}`
};
// Sign via: sendMessage({ type: 'SIGN_EVENT', event: unsigned })
// Returns: { success: true, data: SignedNostrEvent }
```

## Suggested Approach
1. Add relay API methods to `api.ts`: `submitVoice(entityId, stance, signedEvent)`, `revokeVoice(entityId, signedEvent)`
2. Add `handleVoice()` to `SidePanel.svelte` following Open WebUI's optimistic update pattern:
   - Construct unsigned Kind 30800 event
   - Send `SIGN_EVENT` message to service worker for signing
   - Optimistically update local voice counts + user stance
   - POST to relay, rollback on failure
   - Re-click same stance = revoke (toggle off)
3. Add Support/Oppose/Watch button row to agenda items (where `stance_eligible`) and decision cards
4. Persist `userStances` Map to `chrome.storage.local` (not localStorage — extension context)
5. Show active stance highlighting (e.g., green border on support, red on oppose)
6. Handle locked identity gracefully (prompt unlock or show "unlock to vote")

## Build & Test
```bash
cd apps/civicos-extension && npm run build
# Reload in chrome://extensions
# Open side panel, unlock identity, click Support on an agenda item
# Verify count increments, click again to revoke, verify count decrements
```

## Success Criteria
- [ ] Support/Oppose/Watch buttons on stance-eligible agenda items
- [ ] Voice counts on decision cards (already showing from Phase 1b)
- [ ] Clicking a button signs event + submits to relay
- [ ] Re-clicking same stance revokes
- [ ] Optimistic count update with rollback on failure
- [ ] User stance persisted across panel reopens
- [ ] Locked identity shows appropriate message
- [ ] pilot.json item `extension_phase2_voice_signing` marked ready
