# Recommended: Civic Web Components — Phase 1 (Package Scaffold + First Components)

**Priority:** P0 (`civic_web_components`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The `@civicos/client` SDK is complete (5 phases, commit `784b60d`). It provides `RegistryClient`, `ApiClient`, `CivicSession`, `MemoryStorageAdapter` — all platform-agnostic. A Node.js proof script loads live data without Chrome APIs.

The primary motivation for Web Components is **decomposing SidePanel.svelte** (5,587 lines — 57% of the entire extension). Voice buttons alone appear 7+ times with identical markup. Extracting reusable `<civic-*>` components also enables multi-surface distribution (Open WebUI, standalone pages, MCP Apps).

## Recommended Task

Create `packages/civicos-components/` with Svelte 5 Custom Elements. Build two low-complexity, high-reuse components:

### `<civic-voice-buttons>`
- Support/Oppose/Watch button group with active state highlighting
- Props: `entity-id`, `user-stance`, `disabled`, `locked`
- Events: `civic-voice` (detail: `{ entityId, stance }`)
- Currently duplicated at SidePanel.svelte:2068-2093 and :2453-2473

### `<civic-synthesis-bar>`
- Stacked horizontal bar showing comment support/oppose/neutral distribution
- Props: `support`, `oppose`, `neutral`
- No events (pure presentational)
- Currently at SidePanel.svelte:2121-2140, CSS at :4605-4620

## Key Files

- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — 5,587-line monolith to decompose
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:2068-2093` — Voice buttons (agenda items)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:2453-2473` — Voice buttons (decisions)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:2121-2140` — Synthesis bar
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:4043-4065` — Voice button CSS
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:4605-4620` — Synthesis bar CSS
- `apps/civicos-extension/package.json` — Svelte 5.50.2, Vite 6, `@sveltejs/vite-plugin-svelte` 5
- `packages/civicos-client/src/index.ts` — SDK exports (data types for component props)
- `pilot.json:4469-4536` — Full `civic_web_components` item with all 5 candidates + phases

## Suggested Approach

1. **Scaffold package**: Create `packages/civicos-components/` with Svelte 5, Vite, TypeScript. Configure `compilerOptions.customElement: true` in `svelte.config.js`. Add `@civicos/client` as peer dependency for types.

2. **Build `<civic-voice-buttons>`**: Extract markup + CSS from SidePanel:2068-2093. Use `<svelte:options customElement="civic-voice-buttons" />`. Props via Svelte 5 `$props()`. Dispatch `civic-voice` CustomEvent on click.

3. **Build `<civic-synthesis-bar>`**: Extract from SidePanel:2121-2140. Pure presentational — computed segment widths from props.

4. **Wire into extension**: Import components into SidePanel, replace duplicated markup with `<civic-voice-buttons>` and `<civic-synthesis-bar>` tags. Verify extension still builds and functions.

5. **Create standalone demo**: An HTML page that loads the components bundle and renders them with static data — proves components work outside extension.

### Technical Notes (Svelte 5 Custom Elements)

- Use `<svelte:options customElement="civic-voice-buttons" />` at top of `.svelte` file
- Svelte 5 uses `$props()` rune — maps to Custom Element attributes automatically
- Shadow DOM encapsulates CSS (styles must be in component, not external)
- Complex objects: use JS properties (`.data = obj`) not HTML attributes for non-string props
- Events: use `CustomEvent` dispatch, not Svelte's `createEventDispatcher` (deprecated in v5)
- The extension can import Svelte components directly (same bundler), bypassing Custom Element overhead

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile
cd apps/civicos-extension && npm run build         # Extension still works with components
npx tsx examples/pulse-reader.ts                    # SDK still works (in packages/civicos-client/)
```

## Success Criteria

- [ ] `packages/civicos-components/` created with Svelte 5 + Vite + TypeScript
- [ ] `<civic-voice-buttons>` renders Support/Oppose/Watch with active state and dispatches events
- [ ] `<civic-synthesis-bar>` renders stacked bar from numeric props
- [ ] Extension SidePanel uses the new components (at least voice buttons in one location)
- [ ] Both packages build clean
- [ ] Standalone HTML demo renders components without extension
