# Recommended: Client SDK Extraction — Phase 5 (Second Surface Proof) + Web Components Scoping

**Priority:** P0 (`client_sdk_extraction`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Four sessions completed Phases 1-4 of the client SDK extraction:
- **Phase 1** (commit `40cd791`): Created `packages/civicos-client/` with StorageAdapter, types, RegistryClient, ApiClient. Rewired extension (40+ call sites).
- **Phase 2** (commit `0b95db7`): Added Signer interface, event helpers, 9 `cast*` methods on ApiClient, ExtensionSigner adapter.
- **Phase 3** (commit `358cbcd`): Extracted AI layer — types, manager, prompts, 3 providers, AICredentialStorage.
- **Phase 4** (commit `431df29`): Created `CivicSession` orchestration class (220 lines). Provides `loadPulseBundle`, `loadVoiceCounts`, `loadCommentThread`, `loadDecisionDetail`, `loadInitiativeDetail`, `draftComment`, `enrichDraft`, `askQuestion`, plus static entity ID helpers. SidePanel rewired — 12 functions now delegate to session methods.

The SDK is feature-complete. What remains is **validation** (Phase 5) and **scoping the next layer** (Web Components).

## Recommended Task: Two Parts

### Part 1: Phase 5 — Second Surface Proof

Build a minimal page that imports `@civicos/client` and performs a read operation, proving the SDK works outside the Chrome extension.

**Suggested approach:**
1. Create `packages/civicos-client/examples/pulse-reader.html` (or `.ts` script)
2. Import `RegistryClient`, `ApiClient`, `CivicSession` from the SDK
3. Use `MemoryStorageAdapter` (implement a trivial in-memory `StorageAdapter`)
4. Call `session.loadPulse()` or `session.loadPulseBundle()` and render/log the result
5. Optionally test a write with a mock Signer (`castVoice`)

**Key consideration:** The SDK uses `StorageAdapter` interface for caching. The extension uses `ChromeStorageAdapter`. A second surface needs its own adapter — the simplest is an in-memory Map. `MemoryAICredentialStorage` already exists in the SDK (`ai/storage.ts`), but there's no `MemoryStorageAdapter` for the base `StorageAdapter` interface yet. You'll need to add one (5-10 lines).

### Part 2: Scope Web Components Layer

The user wants to explore **Web Components** (`@civicos/components`) as a UI abstraction layer on top of the SDK. The architecture would be:

```
Layer 1: @civicos/client (SDK)         — data, API, AI, orchestration  [DONE]
Layer 2: @civicos/components           — reusable UI widgets (Web Components)
Layer 3: Surface apps                  — compose widgets + layout
```

Svelte compiles to Custom Elements natively (`<svelte:options customElement="civic-pulse-card" />`). This would let any surface (extension, Open WebUI, standalone page, MCP App) embed `<civic-pulse-card jurisdiction="city-san-rafael">` without framework dependencies.

**Scoping tasks:**
1. Identify 3-5 candidate components from SidePanel (e.g., pulse card, voice buttons, comment thread, initiative card)
2. Evaluate Svelte Custom Element compilation constraints (Shadow DOM styling, prop reactivity, cross-component state)
3. Create a `civic_web_components` item in pilot.json with clear phases
4. Optionally prototype one component (e.g., `<civic-voice-buttons>`) to validate the approach

## Key Files

- `packages/civicos-client/src/session.ts` — CivicSession class (the new orchestration layer)
- `packages/civicos-client/src/index.ts:66-78` — All SDK exports including CivicSession
- `packages/civicos-client/src/interfaces.ts` — StorageAdapter, Signer interfaces
- `packages/civicos-client/src/ai/storage.ts:20-35` — MemoryAICredentialStorage (pattern for MemoryStorageAdapter)
- `packages/civicos-client/src/api.ts` — ApiClient with all REST + relay methods
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — 5587 lines, now uses CivicSession
- `apps/civicos-extension/src/lib/adapters/chrome-storage.ts` — ChromeStorageAdapter reference impl

## Tests
```bash
cd packages/civicos-client && npm run build   # SDK compiles
cd apps/civicos-extension && npm run build    # Extension still works
# Phase 5: run the second surface proof (TBD based on implementation)
```

## Success Criteria
- [ ] A non-extension surface successfully imports `@civicos/client` and calls `loadPulse()`
- [ ] `MemoryStorageAdapter` added to SDK for non-browser contexts
- [ ] Both packages still build clean
- [ ] Web Components scoped as a pilot.json item with clear phases
- [ ] (Stretch) One prototype Web Component validates the approach
