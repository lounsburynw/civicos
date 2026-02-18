# Recommended: Client SDK Extraction — Phases 3-5 (AI Layer, Operations, Second Surface)

**Priority:** P0 (`client_sdk_extraction`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Two sessions completed Phases 1-2 of the client SDK extraction:
- **Phase 1** (commit `40cd791`): Created `packages/civicos-client/` with StorageAdapter, types, RegistryClient, ApiClient. Rewired extension (40+ call sites).
- **Phase 2** (commit `0b95db7`): Added Signer interface, event helpers (`events.ts`), 9 `cast*` methods on ApiClient, ExtensionSigner adapter. Simplified all 8 SidePanel signing sites (-167 lines).

**Three phases remain to complete `client_sdk_extraction`:**
1. AI layer extraction (~1005 lines across 10 files)
2. Business operations extraction from SidePanel (5628-line file)
3. Second surface proof

The user wants all three completed across upcoming sessions.

## Recommended Task: Phase 3 — AI Layer Extraction

Move the AI subsystem from the extension into `@civicos/client`. This follows the same pattern as Phases 1-2: define interface → move code → create Chrome adapter → rewire extension.

### File Assessment

**Platform-agnostic (move verbatim to `@civicos/client`):**
- `ai/types.ts` (50 lines) — `AIProvider`, `AIMessage`, `AIConfig` interfaces
- `ai/prompts.ts` (95 lines) — Prompt templates, no browser deps
- `ai/providers/claude.ts` (110 lines) — Claude API client (pure fetch)
- `ai/providers/openai.ts` (105 lines) — OpenAI API client (pure fetch)
- `ai/providers/index.ts` (3 lines) — Re-exports

**Needs Chrome adapter extraction:**
- `ai/storage.ts` (123 lines) — Uses `chrome.storage.local/session` for API keys, OAuth, prefs. Extract `AIStorageAdapter` interface, create `ChromeAIStorage` adapter.
- `ai/manager.ts` (165 lines) — Line 29 checks `typeof chrome !== 'undefined'`. Inject storage adapter instead.
- `ai/providers/civicos-proxy.ts` (133 lines) — Lines 27, 46 use `chrome.runtime.sendMessage` for identity. Inject Signer instead.

**Chrome-only (stays in extension):**
- `ai/providers/chrome-nano.ts` (102 lines) — Chrome built-in AI API (`self.ai.languageModel`)
- `ai/providers/gemini.ts` (119 lines) — Uses `chrome.identity.getAuthToken()`

### Suggested Approach

1. Create `packages/civicos-client/src/ai/` directory
2. Move `types.ts`, `prompts.ts` verbatim
3. Define `AIStorageAdapter` interface (get/set/remove for credentials + prefs)
4. Move `manager.ts` with injected `AIStorageAdapter` (replace chrome check)
5. Move `claude.ts`, `openai.ts` verbatim
6. Move `civicos-proxy.ts` with injected `Signer` (replace chrome.runtime.sendMessage)
7. Create `ChromeAIStorage` adapter in extension
8. Rewire extension imports
9. Verify both packages build

### After AI Layer: Phases 4-5

**Phase 4 — Business operations extraction:** Extract orchestration logic from SidePanel.svelte into `packages/civicos-client/src/operations.ts`. The cast* methods already handle signing; operations.ts would handle the full flow (optimistic updates, error handling, state management patterns). This is the largest phase — SidePanel is 5628 lines.

**Phase 5 — Second surface proof:** Build a minimal web page or test harness that imports `@civicos/client` and performs a read operation (getCityPulse) and optionally a write (castVoice with a mock/direct signer). This validates the whole extraction.

## Key Files

- `packages/civicos-client/src/` — SDK source (interfaces.ts, api.ts, events.ts, registry.ts, types.ts, index.ts)
- `packages/civicos-client/package.json` — Package config (no deps currently)
- `apps/civicos-extension/src/lib/ai/` — AI subsystem to extract (10 files, ~1005 lines)
- `apps/civicos-extension/src/lib/client.ts` — Singleton exports (registry, signer, api)
- `apps/civicos-extension/src/lib/adapters/` — Chrome adapters (chrome-storage.ts, extension-signer.ts)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:1-7` — Current imports (already simplified)

## Tests
```bash
cd packages/civicos-client && npm run build   # SDK compiles
cd apps/civicos-extension && npm run build    # Extension still works
```

## Success Criteria
- [ ] AI types, prompts, and portable providers moved to `@civicos/client`
- [ ] `AIStorageAdapter` interface defined, `ChromeAIStorage` adapter created
- [ ] `civicos-proxy.ts` uses injected Signer instead of chrome.runtime.sendMessage
- [ ] Both packages build clean
- [ ] Extension AI features still work (manual test: try AI draft in side panel)
