# Recommended: Client SDK Extraction

**Priority:** P0 (`client_sdk_extraction`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Last session completed `extension_connected_services_redesign` — breadcrumb segments now function as jurisdiction tabs (click to switch content, endpoint bar shows MCP/Relay URLs, health info via title tooltips). The extension's UX layer is now solid.

The next step is **extracting the platform-agnostic business logic** from the extension into a reusable TypeScript SDK (`packages/civicos-client/`). This enables multiple UX surfaces (web app, MCP App iframe, other extensions) to share civic coordination logic.

## What We're Doing

The extension's `src/lib/` is 80% platform-agnostic already. Chrome coupling is concentrated in ~15 call sites across 4 files. All six business flows (voice, comment, commit, complete, withdraw, initiative) follow identical structure: **build unsigned Nostr event → sign → submit to relay → optimistic update**. This pattern is extractable behind two interfaces.

## Two Key Interfaces

### Signer
Replaces `chrome.runtime.sendMessage({ type: 'SIGN_EVENT' })`:
```typescript
interface Signer {
  sign(event: UnsignedNostrEvent): Promise<SignedNostrEvent>;
  signMessage(msg: string): Promise<{ public_key: string; signature: string; created_at: number }>;
  isUnlocked(): Promise<boolean>;
}
```
Implementations: `ExtensionSigner` (chrome messaging), `InProcessSigner` (calls loom-core directly), `NIP07Signer` (window.nostr)

### StorageAdapter
Replaces direct `chrome.storage.local` calls:
```typescript
interface StorageAdapter {
  get(key: string): Promise<any>;
  set(key: string, value: any): Promise<void>;
  remove(key: string): Promise<void>;
}
```
Implementations: `ChromeStorageAdapter`, `LocalStorageAdapter`, `IndexedDBAdapter`

loom-core's `KeyStore` should be implementable in terms of `StorageAdapter` (one wraps the other).

## What Moves to `packages/civicos-client/`

| Extension File | Disposition | Chrome Calls to Remove |
|---|---|---|
| `lib/types.ts` | Move verbatim | 0 |
| `lib/api.ts` | Move; inject URL resolution | 2 direct + 2 indirect |
| `lib/registry.ts` | Move; inject StorageAdapter for cache + jurisdiction pref | 5 |
| `lib/relay-client.ts` | Move; inject StorageAdapter for URL overrides | 2 |
| `lib/providers/types.ts` | Move CivicEventKinds, event tag/content helpers | 0 |
| `lib/ai/prompts.ts` | Move verbatim (pure functions) | 0 |
| `lib/ai/types.ts` | Move verbatim | 0 |
| `lib/ai/manager.ts` | Move; inject storage instead of Chrome feature detection | 1 |
| `lib/ai/providers/claude.ts` | Move verbatim | 0 |
| `lib/ai/providers/openai.ts` | Move verbatim | 0 |
| `lib/ai/providers/civicos-proxy.ts` | Move; inject Signer for auth | 2 |
| New: `operations.ts` | Extract from SidePanel: castVoice(), submitComment(), commitAction(), createInitiative(), etc. | N/A |

## What Stays in the Extension

- `lib/storage.ts` — ChromeStorageAdapter implementation
- `lib/messaging.ts` — Chrome message types + sendMessage()
- `lib/identity.ts` — IdentityManager (Chrome session persistence)
- `lib/providers/local-wallet.ts` — BIP-39 wallet (uses Chrome storage)
- `lib/providers/crypto.ts` — bridge between extension's NostrEvent (optional pubkey) and loom-core's UnsignedEvent (required pubkey)
- `lib/ai/providers/chrome-nano.ts` — Chrome-only by design
- `lib/ai/storage.ts` — ChromeAICredentialStorage
- `src/background/service-worker.ts` — trusted key holder
- `src/content-scripts/*` — NIP-07 injector, Claude bridge
- `src/side-panel/SidePanel.svelte` — rendering only, imports operations from @civicos/client

## Type Mismatch to Resolve

Extension's `NostrEvent` has `pubkey?: string` (optional). loom-core's `UnsignedEvent` has `pubkey: string` (required). The Signer interface should accept pubkey-optional events and derive pubkey internally — matching the extension's current `signNostrEvent()` bridge in `crypto.ts`.

## Implementation Order

1. Create `packages/civicos-client/` with interfaces (Signer, StorageAdapter) and move `types.ts`
2. Move API layer (`api.ts`, `registry.ts`, `relay-client.ts`) with dependency injection
3. Move AI layer (`manager.ts`, `prompts.ts`, portable providers)
4. Extract business operations from SidePanel into `operations.ts`
5. Rewire extension: create Chrome adapters, import from `@civicos/client`
6. Verify: extension works identically, then build a second surface as proof

## Context to Load

- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` — five-layer architecture, two-MCP split
- `docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md` — tiered identity, MCP Apps, signing flow
- `packages/loom-core/src/types.ts` — KeyPair, KeyStore, ProtocolAdapter interfaces
- `apps/civicos-extension/src/lib/` — the code being extracted
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — business logic to extract

## Tests
```bash
cd packages/civicos-client && npm run build   # SDK compiles
cd apps/civicos-extension && npm run build    # Extension still works
```

## Success Criteria
- [ ] `packages/civicos-client/` exists with Signer + StorageAdapter interfaces
- [ ] Types, API, registry, relay-client moved with dependency injection
- [ ] Extension imports from `@civicos/client` and builds clean
- [ ] All six business flows still work via Chrome adapters
