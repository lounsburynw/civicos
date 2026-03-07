# Extension Development

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Svelte 5 (reactive runes: `$state`, `$derived`) |
| Bundler | Vite 6 |
| Language | TypeScript 5.3 (strict) |
| Styling | CSS custom properties (theme system) |
| Crypto | @noble/curves, @noble/hashes (secp256k1 Schnorr) |
| Mnemonics | @scure/bip32, @scure/bip39 |
| Charts | Chart.js (budget breakdown) |
| Maps | Leaflet (issue map) |
| Client SDK | @civicos/client |
| Components | @civicos/components |

## Dev Workflow

```bash
cd apps/civicos-extension
npm install
npm run dev    # Watch mode — rebuilds dist/ on change
```

After `npm run dev`, reload the extension in `chrome://extensions` to pick up changes. For most UI changes, closing and reopening the side panel is sufficient.

```bash
npm run build  # Production build
```

## Entry Points

The extension builds multiple entry points (Vite multi-page):

| Entry | Output | Purpose |
|-------|--------|---------|
| `src/side-panel/main.ts` | `side-panel.html` | Main civic dashboard (primary UI) |
| `src/popup/main.ts` | `popup.html` | Toolbar icon click (quick actions) |
| `src/options/main.ts` | `options.html` | Settings page |
| `src/service-worker.ts` | `service-worker.js` | Background process (identity, signing) |
| `src/nip07-provider.ts` | `content-scripts/nip07-provider.js` | NIP-07 `window.nostr` injection |
| `src/claude-bridge.ts` | `content-scripts/claude-bridge.js` | Claude.ai context injection |

## Component Architecture

The extension uses components from two packages:

**@civicos/components** (shared library):
- `CivicMeetingCard` — Meeting display with date, location, agenda link
- `CivicAgendaItemCard` — Agenda item with summary and participation guide
- `CivicDecisionCard` — Decision with outcome badge and vote breakdown
- `CivicVoiceButtons` — Support/oppose/watching stance buttons
- `CivicBudgetBreakdown` — Chart.js budget visualization
- `CivicIssueMap` — Leaflet map of community issues
- `CivicInitiativeCard` — Initiative with attestation badges
- `CivicCommentThread` — Comment display
- `CivicProvenancePanel` — Data source attribution
- `CivicIdentityChip` — User identity display
- `CivicAgendaView`, `CivicDecisionView`, `CivicInitiativeView` — Smart views that compose leaf components

**Extension-specific components** (in `src/side-panel/`, `src/options/`):
- Side panel layout, section collapsing, jurisdiction tabs
- Options page forms (identity, AI provider, journal)

## API Communication

The extension uses `@civicos/client` for all API calls:

```typescript
import { CivicSession, RegistryClient, ApiClient } from '@civicos/client';

// Session loads city pulse data
const session = new CivicSession(registryClient);
const pulse = await session.loadPulse();

// Direct API calls
const api = new ApiClient(baseUrl);
await api.castVoice(entityId, stance, jurisdiction, proof);
const counts = await api.getVoiceCountsBatch(ids, jurisdiction);
```

**Service worker messages** (via `chrome.runtime.sendMessage`):
- Identity: `CREATE_IDENTITY`, `IMPORT_IDENTITY`, `UNLOCK`, `LOCK`, `DELETE_IDENTITY`
- Signing: `SIGN_EVENT`, `SIGN_MESSAGE`
- NIP-07: `NIP07_GET_PUBLIC_KEY`, `NIP07_SIGN_EVENT`, `NIP07_GET_RELAYS`
- Attestation: `REDEEM_ATTESTATION`

## Storage

| Store | Contents |
|-------|----------|
| `chrome.storage.local` | Encrypted keys, cached pulse, profile, journal, stances, attestation |
| `chrome.storage.session` | Unlock state (cleared on browser close) |

Key prefixes: `civicos_pulse_cache`, `civicos_profile`, `civicos_journal`, `civicos_user_stances`, `civicos_attestation`, `civicos_session_key`

## Permissions (manifest.json)

- `sidePanel` — Side panel UI
- `storage` — chrome.storage access
- `alarms` — Timer-based tasks
- Host permissions: `*.civicosproject.org`, `*.modal.run` (required); localhost, AI provider APIs (optional)

## Theme System

Themes are managed by `@civicos/components/theme`:

```typescript
import { initTheme, setTheme } from '@civicos/components';
initTheme();       // Apply saved theme on load
setTheme('dark');  // Switch theme
```

Themes use CSS custom properties (`--civic-*` tokens).
