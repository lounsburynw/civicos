# Browser Extension Architecture

**Status:** Design
**Created:** 2026-02-12
**Related:** `EDGE_INTELLIGENCE_ARCHITECTURE.md`, `MCP_INTEGRATION_STRATEGY.md`, `COORDINATION_PROTOCOL.md`

## Overview

The CivicOS browser extension is the **fifth instantiation pattern** for the Personal MCP (alongside MCP App, Claude Desktop, Self-Hosted, and Jurisdiction-Hosted Open WebUI). It is the primary distribution surface for launch.

The extension **is** the Personal MCP — not a wrapper around it, not a client to it. It runs the user's edge agent directly in the browser's extension context, with full access to Web Crypto, WebAuthn, IndexedDB, and `window.nostr`. This solves the iframe sandbox problem (MCP Apps can't access browser extensions), provides persistent background execution (service worker), and works across every AI surface the user visits.

### Why a Browser Extension

| Problem | Extension Solution |
|---------|--------------------|
| MCP App iframe blocks NIP-07 | Extension has full browser API access |
| Open WebUI requires city hosting | Extension is self-distributed via Chrome Web Store |
| AI surface lock-in | Extension injects context into any AI surface |
| Identity scattered across surfaces | Extension is canonical identity home |
| Civic context isolated from web browsing | Extension overlays civic context on any page |

### Platform Target

**Chrome-first.** Chrome holds ~65% global browser share and higher among likely early adopters. Brave (Chromium-based) runs Chrome extensions natively, providing a privacy-conscious option for free. Firefox support is a future consideration if demand warrants — the core APIs differ (Firefox uses sidebar instead of Side Panel) but the architecture is portable.

Chrome's vendor (Google) can observe that the extension makes HTTP requests to jurisdiction MCP endpoints, but cannot see signed Nostr event content. The privacy properties live in the extension architecture itself, not the browser vendor. Users wanting browser-level privacy should use Brave.

## Core Principle: Edge Intelligence

Intelligence lives client-side. The extension implements three layers, each progressively more capable:

### Layer 1: Deterministic Intelligence (In-Extension, No LLM)

Runs entirely within the extension's service worker and side panel. No network calls required beyond MCP data fetching.

- **Filtering:** "Show housing items near Terra Linda" — geo-filter + topic match against structured Jurisdiction MCP data
- **Ranking:** Sort by deadline proximity, voice momentum, neighborhood relevance
- **Synthesis:** Aggregate voice counts, compute trends, format commitment deadline reminders
- **Alerting:** Background checks for approaching deadlines, new decisions in followed topics

This covers ~70% of what City Pulse displays today. It is data presentation, filtering, and structured computation — not reasoning.

### Layer 2: Connected Intelligence (User's AI Surface)

The user is already conversing with an AI (Claude.ai, ChatGPT, Gemini, etc.). The extension injects civic context *into* that conversation rather than duplicating the reasoning.

- Extension detects AI surface via content script
- Provides "Civic Context" injection: upcoming meetings, relevant decisions, user's commitments, initiative status
- The AI does the reasoning ("What should I say at the housing meeting?"); the extension provides the civic substrate
- MCP connection management lets the AI surface query jurisdiction tools directly

This is the primary intelligence mode for most users. The extension makes their existing AI civic-aware.

### Layer 3: Local LLM (Optional, Sovereign Intelligence)

For users who want fully private reasoning without any cloud AI dependency.

- Extension connects to a locally-running Ollama instance (`localhost:11434`)
- Enables: topic extraction from articles, personalized recommendation, natural language queries over civic data
- Not required — the extension works fully without it
- Represents the "sovereign intelligence" option for maximum privacy

### The Reframe

The extension doesn't need to *contain* intelligence. It needs to **make intelligence available** — by being the bridge between the user's civic context and whatever AI surface they're on. The intelligence is the LLM they're already talking to; the extension provides the civic substrate.

## UX Surfaces

The extension uses four Chrome extension surfaces, each with a distinct purpose:

### 1. Side Panel — City Pulse

The primary interface. Opened via the extension icon or keyboard shortcut. Renders the City Pulse UX adapted from the Open WebUI fork.

```
┌───────────────────────────────────────────────────┐
│  City Pulse                          [Settings ⚙] │
│  ┌─────────────────────────────────────────────┐  │
│  │  npub1q7k... · Easy mode · ✓ Verified      │  │
│  │  San Rafael · Terra Linda · This Week       │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  Upcoming Meetings (2)                      [▼]  │
│  ├── City Council — Feb 18 @ 7pm                 │
│  │   [Add to calendar]                           │
│  └── Planning Commission — Feb 20 @ 6pm         │
│                                                   │
│  Voice Your Stance (3 items)                [▼]  │
│  ├── #4.2 Downtown Bike Lane Extension           │
│  │   12 support · 3 oppose · [Support] [Oppose] │
│  │   [Comment thread (8)] [Email clerk]          │
│  ├── #4.3 Parking Meter Rate Adjustment          │
│  └── #5.1 Affordable Housing Overlay             │
│                                                   │
│  Decided (4 recent)                         [▼]  │
│  ├── ✓ Cannabis dispensary setback — Approved 4-1│
│  └── ✗ Fence height variance — Denied 3-2       │
│                                                   │
│  My Commitments (1 due soon)                [▼]  │
│  └── ⚡ Submit public comment on bike lane        │
│      Due: Feb 17 (2 days) · [Done] [Withdraw]   │
│                                                   │
│  Community Initiatives (5)                  [▼]  │
│  ├── Terra Linda density review (12 voices)      │
│  │   [Actions (3)] [Voice] [Coordination]        │
│  └── Downtown parking reform (8 voices)          │
│                                                   │
│  ─── Connected MCPs ───                          │
│  ● San Rafael (healthy) · 32 tools              │
│  ● Marin County (healthy) · 18 tools            │
│  ○ California [Connect]                          │
└───────────────────────────────────────────────────┘
```

**Sections** mirror the Open WebUI City Pulse component:
- **Identity chip** — always visible in header, shows npub + mode + attestation status
- **Upcoming Meetings** — from Jurisdiction MCP, with calendar integration (Google Calendar + .ics)
- **Voice Your Stance** — agenda items with inline voice counts, support/oppose buttons, comment threads
- **Decided** — recent outcomes with expandable context
- **My Commitments** — deadline tracking with urgency indicators, done/withdraw actions
- **Community Initiatives** — active initiatives with nested civic actions, progress tracking, templates
- **Connected MCPs** — health status of connected jurisdiction servers

**Data source:** All civic data fetched from connected Jurisdiction MCPs via HTTP. Voice/action data from the CivicOS Relay via WebSocket. User context (neighborhood, interests, commitments) stored locally in extension storage.

### 2. Popup — Quick Actions

Shown on extension icon click (if side panel is closed). Compact summary with immediate actions.

```
┌───────────────────────────────────────┐
│  CivicOS · San Rafael                 │
│                                       │
│  [Inject Context] [Open Pulse] [⚙]   │
│                                       │
│  Next: City Council, Feb 18 @ 7pm    │
│  1 commitment due in 2 days          │
│  3 items to voice on                 │
└───────────────────────────────────────┘
```

The **Inject Context** button is the primary action — pastes the user's civic context into the current AI chat. See Context Injection below.

### 3. Content Scripts — AI Surface Integration

Content scripts detect supported AI surfaces and provide integration affordances. Injection is **opt-in per site** with persistent memory.

**Permission model:**
```
┌───────────────────────────────────────────┐
│  CivicOS wants to integrate with          │
│  claude.ai                                │
│                                           │
│  This allows:                             │
│  · Injecting civic context into chats     │
│  · Configuring MCP connections            │
│  · Showing civic relevance indicators     │
│                                           │
│  [Always on claude.ai] [Just this once]   │
│  [Never on claude.ai]                     │
└───────────────────────────────────────────┘
```

Site permissions stored in extension storage. Configurable in Options page. Users never re-prompted for a site they've already approved or denied — they can change this in settings at any time.

**Supported AI surfaces (launch):**
- Claude.ai — MCP Integrations auto-configuration + context injection
- ChatGPT — MCP connector configuration (when available) + context injection

**Supported AI surfaces (post-launch):**
- Gemini, Copilot, and other MCP-compatible surfaces as they emerge

### 4. Options Page — Settings

Full configuration interface for identity, connections, and preferences.

```
┌─────────────────────────────────────────────────────────┐
│  CivicOS Extension Settings                             │
│                                                         │
│  ── Identity ──                                         │
│  Mode: Easy (passkey) · npub1q7k...                     │
│  Attestation: ✓ Verified San Rafael resident            │
│  [Export identity] [Upgrade to Private mode]            │
│                                                         │
│  ── Jurisdictions ──                                    │
│  ● City of San Rafael [primary]                         │
│    san-rafael.civicosproject.org · 32 tools             │
│  ● Marin County                                        │
│    marin-county.civicosproject.org · 18 tools           │
│  [+ Add jurisdiction]                                   │
│                                                         │
│  ── Preferences ──                                      │
│  Neighborhood: Terra Linda                              │
│  Interests: housing, transit, public safety             │
│  Filters: ignore parking meter complaints               │
│                                                         │
│  ── AI Surface Permissions ──                           │
│  claude.ai: Always allow                    [Change]    │
│  chat.openai.com: Always allow              [Change]    │
│  gemini.google.com: Never asked             [Change]    │
│  [✓] Auto-configure MCP connections when available      │
│                                                         │
│  ── Advanced ──                                         │
│  Local LLM: Not connected                              │
│  [Connect to Ollama (localhost:11434)]                  │
│  NIP-07: Extension provides window.nostr               │
│  [✓] Act as NIP-07 provider on all pages               │
└─────────────────────────────────────────────────────────┘
```

## Context Injection

The extension's most distinctive capability: bridging civic context into any AI conversation.

### Injection Modes

**Mode A: Paste injection (works everywhere, launch target)**

User clicks "Inject Context" (popup or side panel). Extension composes a structured context block and pastes it into the active chat input:

```
I'm a verified San Rafael resident (Terra Linda neighborhood).

Upcoming: City Council meeting Feb 18 at 7pm.
  - Agenda item #4.2: Downtown Bike Lane Extension (I support this, 12 support / 3 oppose)
  - Agenda item #5.1: Affordable Housing Overlay (not yet voiced)

My commitment: Submit public comment on bike lane by Feb 17.

Active initiatives I follow:
  - "Terra Linda density review" — 12 voices, 3 pending actions
  - "Downtown parking reform" — 8 voices

Context from: CivicOS extension (san-rafael.civicosproject.org)
```

This requires no special API access — it works on any text input on any page.

**Mode B: MCP auto-configuration (Claude.ai, ChatGPT when supported)**

The extension programmatically adds Jurisdiction MCP URLs to the AI surface's MCP integration settings. The AI then has direct tool access to civic data — `search_meeting_history()`, `get_upcoming_meetings()`, `get_voice_counts()`, etc.

The user's AI assistant becomes civic-aware without manual MCP configuration.

**Mode C: Contextual side panel (post-launch)**

The extension observes the AI conversation (via DOM) and surfaces relevant civic context in the side panel as topics arise. If the user asks their AI about housing policy, the side panel automatically shows related decisions, active initiatives, and upcoming meetings on housing.

### Context Composition

The extension composes context from:

1. **User profile** — neighborhood, interests, identity status, attestation
2. **Commitments** — active commitments with deadlines and urgency
3. **Voiced items** — items the user has supported/opposed
4. **Upcoming meetings** — filtered by relevance to user interests
5. **Active initiatives** — initiatives the user follows or has voiced on

All sourced from local extension storage (for user data) and cached Jurisdiction MCP queries (for civic data). No additional network calls needed at injection time.

## Identity

The extension is the canonical home for the user's civic identity. It implements the tiered identity system from `EDGE_INTELLIGENCE_ARCHITECTURE.md` with one addition: the extension itself acts as a NIP-07 provider.

### Tiered Identity

| Tier | Mechanism | Friction | Security |
|------|-----------|----------|----------|
| **Easy** | WebAuthn passkey + PRF extension | Lowest — TouchID/FaceID, 10s setup | Medium — cloud-synced passkeys |
| **Private** | BIP-39 mnemonic + PBKDF2 + AES-256-GCM | Medium — password required | Higher — no cloud sync |
| **Sovereign** | NIP-07 detection OR extension-managed keys | Varies | Highest — full self-custody |

All three tiers produce the same output: a **BIP-340 Schnorr signature** over a canonical message. The relay accepts any valid signature regardless of how it was produced.

### Signing Flow

```
User action (voice, commit, complete)
    │
    ▼
Extension checks identity status
    ├── No identity → Onboarding flow (mode selection + setup)
    └── Has identity → Continue
    │
    ▼
Construct canonical message
    ("civicos:voice:v1:{entity}:{stance}:{timestamp}")
    │
    ▼
Request signature from provider
    ├── Easy: browser WebAuthn prompt → PRF → derive key → sign
    ├── Private: extension popup asks password → decrypt key → sign
    └── Sovereign: window.nostr.signEvent() or hardware prompt
    │
    ▼
Broadcast signed event to relay
    │
    ▼
Only the signed payload leaves the browser.
Never: private key, query context, user identity.
```

### Extension as NIP-07 Provider

The extension injects `window.nostr` into web pages (configurable, opt-in per site). This means:

1. **CivicOS identity works across the Nostr ecosystem** — the user's civic identity can sign events on any Nostr client (Primal, Snort, etc.)
2. **Existing Nostr users get automatic integration** — if the user already has nos2x or Alby, the extension detects their existing `window.nostr` and uses it (Sovereign mode auto-detection)
3. **No conflict with existing extensions** — if another NIP-07 provider is detected, the extension defers to it rather than overriding

**NIP-07 interface implemented by the extension:**
```typescript
window.nostr = {
  getPublicKey(): Promise<string>,           // hex-encoded pubkey
  signEvent(event: UnsignedEvent): Promise<SignedEvent>,
  getRelays?(): Promise<Record<string, {read: boolean, write: boolean}>>,
  nip04?: {                                  // encrypted DMs (future)
    encrypt(pubkey: string, plaintext: string): Promise<string>,
    decrypt(pubkey: string, ciphertext: string): Promise<string>
  }
}
```

### Attestation Flow

Attestation is **required** to voice or comment. The relay rejects submissions without a valid attestation proof (403) or with a forged one (400). Unattested users can still browse civic data and subscribe to notifications.

**Current (pilot — physical attestation via single-use codes):**

1. User gets a single-use code from a volunteer at a community event
2. User enters code in extension Options > Attestation
3. Relay signs a kind-30850 Nostr event binding the user's npub to the jurisdiction
4. Extension stores the full attestation event locally
5. Side panel shows attestation status: "Attested for San Rafael"
6. Every voice and comment embeds this event as `attestation_proof`
7. Relay verifies the proof (Schnorr signature, issuer check, tag validation) before accepting

**Future (city SSO attestation):**

1. User visits `civic.sanrafael.gov/verify` (or similar city-hosted page)
2. City page authenticates user via LDAP/SSO
3. Extension presents its npub to the city page (via content script or NIP-07)
4. City backend signs a kind-30850 event: "npub1q7k... is a verified San Rafael resident"
5. Extension stores the attestation event, same flow as physical attestation from there

## MCP Connection Management

### Discovery

On install, the extension fetches the CivicOS service registry (`config/registry.json`) to bootstrap available jurisdictions. It may also query the internal registry API (`/api/mcp/internal/servers`) for federated peer discovery.

```
Extension installed
    │
    ▼
Fetch registry.json → available jurisdictions
    │
    ▼
Geo-locate user (if permitted) → suggest nearby jurisdictions
    │
    ▼
User selects jurisdictions to connect
    │
    ▼
Extension connects to each Jurisdiction MCP via HTTP
    │
    ▼
Background health checks (periodic)
    │
    ▼
Tools and data available in side panel
```

### Connection UI

```
┌─────────────────────────────────────────────────┐
│  Connected Jurisdictions                         │
│                                                  │
│  ● City of San Rafael              [primary]    │
│    san-rafael.civicosproject.org                 │
│    32 tools · Last sync: 2 min ago              │
│    Attestation: ✓ Verified resident             │
│                                                  │
│  ● Marin County                                 │
│    marin-county.civicosproject.org               │
│    18 tools · Last sync: 5 min ago              │
│    Attestation: none                            │
│                                                  │
│  ○ State of California           [available]    │
│    california.civicosproject.org                 │
│    [Connect]                                    │
│                                                  │
│  + Add jurisdiction...                          │
│    ┌──────────────────────────────────┐          │
│    │ Search or enter MCP URL...      │          │
│    └──────────────────────────────────┘          │
│    Suggested (based on location):               │
│    · Marin County                               │
│    · State of California                        │
│    · United States (federal)                    │
│                                                  │
│  ── AI Surface Integration ──                   │
│  [✓] Auto-add MCPs to Claude.ai                │
│  [✓] Auto-add MCPs to ChatGPT                  │
└─────────────────────────────────────────────────┘
```

### Multi-Jurisdiction Federation

Users can connect to multiple jurisdictions simultaneously. The extension queries each Jurisdiction MCP independently and presents unified results in City Pulse. Voice counts aggregate across jurisdictions with attestation signals:

```
Initiative: "Bay Area transit coordination"
  38 Verified San Rafael residents
   6 Verified Marin County residents (other cities)
   3 Unverified participants
```

Cross-jurisdictional voices work because the relay protocol is jurisdiction-agnostic — a signed voice event is valid on any relay. Attestation provides provenance but doesn't gate participation.

## Site Content Interaction (Post-Launch Roadmap)

The extension's content script infrastructure enables a future **civic lens** on the web: surfacing civic context when the user browses news, social media, or government sites.

### How It Works

```
User reads news article:
  "Marin supervisors approve controversial housing development..."
        │
Content script extracts page content
        │
Topic extraction (Layer 1: keyword match against jurisdiction data)
  → housing, Marin County, development, approval
        │
Cross-reference connected Jurisdiction MCPs
  → Decision #38 from Marin County MCP
  → Related: San Rafael General Plan housing element
  → Active initiative: "Terra Linda density review"
        │
Side panel surfaces relevant context:

┌─────────────────────────────────────────┐
│  Related to this article                │
│                                         │
│  Decision: Marin supervisors approved   │
│  housing density increase (Jan 28)      │
│  Vote: 4-1 · Your stance: not voiced   │
│                                         │
│  Local impact: San Rafael General Plan  │
│  housing element may be affected        │
│                                         │
│  Active initiative:                     │
│  "Terra Linda density review" (12 voices│
│  [Voice support] [Voice oppose]         │
│                                         │
│  [Ask my AI about this]                 │
│  → Injects article + civic context      │
└─────────────────────────────────────────┘
```

### "Ask My AI About This"

The bridge between site content and connected intelligence. When clicked:

1. Extension extracts the article/post content (or user-selected text)
2. Composes a context block: article summary + relevant civic data from Jurisdiction MCPs + user context
3. Injects into the user's preferred AI surface (Claude.ai, ChatGPT, etc.)
4. The AI reasons over the combined context: "Given this development approval and your interest in housing density, here are local actions you could take..."

### Intelligence Layers for Site Content

- **Layer 1 (deterministic):** Keyword/topic matching against cached jurisdiction data. Works offline, instant, no LLM needed. Sufficient for "this article mentions housing and your city has a housing initiative."
- **Layer 2 (connected):** User clicks "Ask my AI" to get deeper reasoning from their AI surface.
- **Layer 3 (local LLM):** Ollama extracts topics, summarizes articles, generates recommendations — all privately, no cloud dependency.

### Supported Sites (Future)

| Site Type | What the Extension Surfaces |
|-----------|-----------------------------|
| News articles | Related decisions, initiatives, upcoming meetings |
| Social media posts | Relevant civic context, fact-checking against official records |
| Government sites | Enhanced navigation, voice counts, attestation status |
| Real estate listings | Zoning info, nearby issues, planned developments |
| School district pages | Budget data, board decisions, parent initiatives |

Site content interaction is **opt-in per site** using the same permission model as AI surface injection. The extension never reads page content without explicit user consent.

## Technical Architecture

### Manifest V3 Structure

```
civicos-extension/
├── manifest.json              # Manifest V3 config
├── service-worker.js          # Background: MCP client, cache, identity store
├── side-panel/
│   ├── index.html             # Side panel shell
│   └── city-pulse.js          # City Pulse UI (Svelte or Preact)
├── popup/
│   ├── index.html
│   └── popup.js               # Quick actions
├── content-scripts/
│   ├── ai-surface-detector.js # Detect Claude.ai, ChatGPT, etc.
│   ├── context-injector.js    # Paste/configure civic context
│   ├── nip07-provider.js      # Inject window.nostr
│   └── site-content.js        # Article/post extraction (post-launch)
├── options/
│   ├── index.html
│   └── options.js             # Settings UI
├── lib/
│   ├── mcp-client.ts          # HTTP MCP client (browser-compatible)
│   ├── relay-client.ts        # WebSocket relay client
│   ├── providers/
│   │   ├── passkey.ts         # Easy mode (WebAuthn + PRF)
│   │   ├── local-wallet.ts    # Private mode (BIP-39 + AES-GCM)
│   │   └── nip07.ts           # Sovereign mode (detect/defer)
│   ├── signing.ts             # Unified signing flow
│   ├── context.ts             # User context (interests, neighborhood)
│   ├── cache.ts               # IndexedDB civic data cache
│   ├── permissions.ts         # Per-site permission storage
│   └── payments/
│       ├── nwc-client.ts      # Nostr Wallet Connect client
│       ├── l402-handler.ts    # L402 response handling + macaroon management
│       ├── cashu-wallet.ts    # NIP-60 Cashu wallet (post-launch)
│       └── spending.ts        # Spending controls, limits, history
└── _locales/                  # i18n
```

### Service Worker (Background)

The Manifest V3 service worker handles:

- **MCP Client Pool** — maintains HTTP connections to N Jurisdiction MCPs, handles L402 payment flow
- **Data Cache** — periodic refresh of meetings, decisions, voice counts → IndexedDB
- **Identity Store** — encrypted key material in `chrome.storage.local`
- **Wallet Client** — NWC connection to Lightning wallet, Cashu wallet state, spending controls
- **Commitment Tracker** — deadline monitoring, badge/notification for approaching deadlines
- **Relay Connection** — WebSocket to CivicOS relay for real-time voice/action updates
- **Health Checks** — periodic MCP endpoint health verification

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Browser Extension (Manifest V3)                            │
│                                                             │
│  Service Worker                                             │
│  ├── MCP Client Pool → Jurisdiction MCPs (HTTP, read-only)  │
│  ├── Relay Client → CivicOS Relay (WebSocket, signed events)│
│  ├── Wallet Client → Lightning wallet (NWC) + Cashu mint    │
│  ├── Data Cache (IndexedDB)                                 │
│  ├── Identity Store (chrome.storage.local, encrypted)       │
│  └── Optional: Ollama Client (localhost:11434)              │
│                                                             │
│  Side Panel ←→ Service Worker (chrome.runtime messaging)    │
│  Popup ←→ Service Worker                                    │
│  Content Scripts ←→ Service Worker                          │
│  Options ←→ Service Worker                                  │
│                                                             │
│  Outbound (only these leave the browser):                   │
│  ├── Signed Nostr events → Relay (voice, commit, complete)  │
│  ├── Read-only MCP queries → Jurisdiction MCPs              │
│  │   (no user identity attached, equivalent to visiting     │
│  │    the city website)                                     │
│  ├── Lightning payments → Wallet (NWC, for paid tool calls) │
│  └── Injected context → AI surface (explicit user action)   │
│                                                             │
│  Never leaves:                                              │
│  ├── Private keys                                           │
│  ├── Query history                                          │
│  ├── Browsing patterns                                      │
│  ├── Participation history (local only)                     │
│  └── User preferences and filters                           │
└─────────────────────────────────────────────────────────────┘
```

### Offline Capability

The extension caches civic data in IndexedDB for offline access:

| Data | Cache Strategy | Freshness |
|------|---------------|-----------|
| Meetings/agendas | Refresh on side panel open, background sync hourly | Stale OK (meetings don't change often) |
| Decisions | Refresh daily | Stale OK |
| Voice counts | Real-time via WebSocket, fallback to cached | Best-effort real-time |
| User commitments | Local-first, synced on reconnect | Always fresh (local source of truth) |
| Initiatives | Refresh on side panel open | Stale OK |
| MCP tool definitions | Cache on connect, refresh weekly | Rarely changes |

Offline mode supports: viewing cached civic data, composing (but not broadcasting) signed events, identity management, commitment tracking. Events queued offline are broadcast when connectivity returns.

### Permissions

The extension requests minimal Chrome permissions:

```json
{
  "permissions": [
    "sidePanel",
    "storage",
    "alarms"
  ],
  "optional_permissions": [
    "notifications"
  ],
  "host_permissions": [],
  "optional_host_permissions": [
    "https://claude.ai/*",
    "https://chat.openai.com/*",
    "https://chatgpt.com/*",
    "https://gemini.google.com/*",
    "https://*.civicosproject.org/*"
  ]
}
```

- **`sidePanel`** — City Pulse UI
- **`storage`** — identity, preferences, cache, site permissions
- **`alarms`** — background sync, deadline reminders
- **`notifications`** (optional) — deadline alerts, meeting reminders
- **Host permissions are optional** — requested per-site when the user first opts in to integration. The extension functions fully (side panel, identity, MCP connections) without any host permissions.

## Privacy Model

The browser extension maintains the same privacy guarantees as all CivicOS instantiation patterns:

**What stays on device:**
- All queries and browsing patterns
- All identity material (keys, passkeys, mnemonics)
- All personalization (interests, neighborhood, filters)
- All query history and participation patterns
- All page content analysis (site content interaction)

**What leaves (only by explicit user action):**
- Signed Nostr events (voice, commitment, completion) — signature only, no query context
- Read-only MCP tool calls — no user identity attached, equivalent to visiting city website
- Injected context to AI surfaces — only when user clicks "Inject Context"
- Lightning payments (when user triggers a paid tool call) — payment amount visible to wallet provider, but not correlated with civic identity unless user chooses a custodial wallet

**What the extension never does:**
- Phone home to CivicOS servers with telemetry or analytics
- Track which pages the user visits
- Send browsing data to any third party
- Log which AI surfaces the user uses
- Correlate civic participation with browsing behavior

## Payments — Self-Sustaining Economic Model

The Nostr ecosystem provides a mature micropayment infrastructure that maps directly onto CivicOS's architecture. Because the extension already manages Nostr identity (keypairs), adding a payment layer requires connecting a wallet — not building new identity infrastructure.

### Design Principle

**Civic participation is always free. Compute-intensive synthesis is paid.**

Viewing meetings, casting voices, tracking commitments, reading decisions — all free, always. The payment layer gates expensive operations that involve LLM inference or bulk data processing. This aligns with "price for sustainability, not extraction" from `docs/funding/SUSTAINABILITY_MODEL.md`.

### Three Payment Protocols

#### L402 — Pay-Per-Query for MCP Endpoints

[L402](https://docs.lightning.engineering/the-lightning-network/l402) (Lightning HTTP 402) gates HTTP API endpoints with Lightning micropayments. No accounts, no API keys, no login — the payment *is* the authentication.

**How it works:**

```
Extension calls Jurisdiction MCP: prepare("housing meeting")
        │
        ▼
MCP responds: HTTP 402 Payment Required
  ├── Lightning invoice: 100 sats (~$0.05)
  ├── Macaroon: [auth token with caveats]
  └── Description: "Meeting preparation synthesis"
        │
        ▼
Extension auto-pays via connected wallet (NWC)
  └── User sees: "Preparing brief... (100 sats)"
        │
        ▼
Extension retries with macaroon + preimage (proof of payment)
        │
        ▼
MCP returns: Full meeting preparation with context
```

**Why L402 fits CivicOS:** Jurisdiction MCPs are already HTTP endpoints. L402 is middleware — it wraps existing tool handlers without changing the MCP protocol. The Jurisdiction MCP operator (city, nonprofit, or CivicOS) sets per-tool pricing. Free tools return data directly; paid tools return `402` first.

**Macaroon caveats** enable flexible access policies:
- Time-limited tokens (good for 24 hours)
- Tool-scoped tokens (valid only for `prepare()`)
- Jurisdiction-scoped tokens (valid only for `city-san-rafael`)
- Subscription-like tokens (monthly pass, unlimited `prepare()` calls)

#### NIP-47 / Nostr Wallet Connect — The Wallet Bridge

[NIP-47](https://nips.nostr.com/47) lets applications request Lightning payments from the user's wallet via Nostr. The user connects once; the extension can request payments on their behalf with configurable approval thresholds.

**Extension integration:**

```
┌─────────────────────────────────────────────────┐
│  Options Page — Wallet                          │
│                                                  │
│  ── Lightning Wallet ──                         │
│  Status: Connected (Alby)                       │
│  Balance: 12,400 sats (~$6.20)                  │
│  NWC URI: nostr+walletconnect://...             │
│                                                  │
│  ── Spending Controls ──                        │
│  Auto-approve up to: [200] sats per request     │
│  Daily limit: [2,000] sats                      │
│  Require confirmation above limit: [✓]          │
│                                                  │
│  ── This Month ──                               │
│  Total spent: 1,450 sats (~$0.73)              │
│  Breakdown:                                     │
│    prepare() calls: 800 sats (8 calls)          │
│    suggestions(): 400 sats (4 calls)            │
│    coordinate(): 250 sats (1 call)              │
│                                                  │
│  [Disconnect wallet] [Transaction history]      │
└─────────────────────────────────────────────────┘
```

**Wallet compatibility:** Any NWC-supporting wallet works — [Alby](https://getalby.com), Zeus, Mutiny, Phoenix, Coinos. [Alby already ships an MCP server](https://github.com/getAlby/mcp) for Lightning + NWC, validating this integration path.

#### NIP-60 + NIP-61 / Cashu — Privacy-Preserving Payments

[Cashu](https://cashu.space) is Chaumian ecash running on Lightning. [NIP-60](https://nips.nostr.com/60) stores wallet state on Nostr relays (portable across clients). [NIP-61](https://nips.nostr.com/61) defines Nutzaps — ecash tokens locked to a recipient's pubkey where the payment itself is the receipt.

**Why Cashu matters for CivicOS:** Lightning payments are pseudonymous but not private — node operators can observe payment routes. Cashu adds a privacy layer: the mint cannot link payer to payee. For civic participation in sensitive contexts, this matters.

**Relay payment model:**
- User tops up Cashu wallet via Lightning
- Relay accepts Cashu tokens for premium event storage (e.g., long-form initiative proposals, media attachments)
- Relay operator redeems tokens at the mint
- No link between the user's identity and their payment

### Pricing Model

| Service | Cost | Gate | Rationale |
|---------|------|------|-----------|
| Read-only queries (`what_happened`, `get_upcoming_meetings`, `get_voice_counts`) | **Free** | None | Public civic data, equivalent to visiting city website |
| Participation (`voice`, `commit`, `complete`, relay writes) | **Free** | None | Permissionless civic participation is the core mission |
| Synthesis (`prepare`, `suggestions`, `coordinate`) | **50-200 sats** (~$0.03-0.10) | L402 | LLM inference cost passthrough |
| Personalized daily brief | **500 sats/day** (~$0.25) | L402 or subscription macaroon | Recurring compute for personalization |
| Bulk API access (organizations, advocacy groups) | **Subscription** | NWC recurring or macaroon | Higher volume, predictable revenue |
| Premium relay storage (media, long-form) | **10-50 sats** | Cashu | Storage cost passthrough |

**Graceful degradation for users without wallets:**
- All free features work without any wallet connection
- Paid features show a clear prompt: "This requires a Lightning wallet. [Learn more] [Set up Alby (2 min)]"
- No hard wall — the extension never breaks, it just limits to free-tier features
- Jurisdiction operators can subsidize: a city could pre-fund a macaroon that covers all `prepare()` calls for verified residents

### Revenue Flow

```
User pays 100 sats for prepare()
        │
        ▼
L402 middleware on Jurisdiction MCP
        │
        ├──► Jurisdiction operator (city/nonprofit): 70 sats
        │    Covers: hosting, LLM inference, data freshness
        │
        └──► CivicOS protocol fee: 30 sats
             Covers: registry, relay infrastructure, development

Relay accepts Cashu token for storage
        │
        ▼
Relay operator redeems at mint
        │
        └──► Relay operator: 100%
             Covers: storage, bandwidth, uptime
```

**Jurisdiction operators set their own prices.** CivicOS provides recommended pricing and L402 middleware. Operators can price higher (premium data freshness), lower (subsidized by city budget), or free (foundation-funded). The protocol fee is optional and configurable — operators running their own relay infrastructure can disable it.

### Interaction With Identity

Payments compose naturally with the tiered identity system:

| Identity Tier | Wallet Options | Privacy Level |
|---------------|---------------|---------------|
| **Easy** (passkey) | Custodial wallet (Alby Hub, Coinos) or NWC | Pseudonymous — wallet provider sees payments |
| **Private** (mnemonic) | Self-custodial NWC wallet (Phoenix, Zeus) | Private — only your node sees payments |
| **Sovereign** (NIP-07) | Self-custodial + Cashu | Maximum — ecash breaks payment-identity link |

The extension's wallet connection is independent of identity tier — any tier can use any wallet. But the privacy-conscious user naturally gravitates toward Private identity + self-custodial wallet + Cashu for relay payments.

### Interaction With the Extension

The wallet integrates into the existing extension surfaces:

**Side panel:** Paid tool calls show cost inline: "Preparing meeting brief... (100 sats)". Monthly spending summary in the Connected MCPs section.

**Popup:** Quick balance check. "Balance: 12,400 sats. This month: 1,450 sats spent."

**Options page:** Wallet connection (NWC URI), spending controls, transaction history, Cashu mint configuration.

**Content scripts:** When injecting context that triggers a paid MCP call, the extension shows the cost before proceeding.

### Server-Side: L402 Middleware for Jurisdiction MCPs

The L402 gate is middleware on the Jurisdiction MCP HTTP server. It wraps existing tool handlers:

```python
# Conceptual — middleware on the MCP HTTP endpoint
FREE_TOOLS = {
    "search_meeting_history", "get_upcoming_meetings",
    "get_voice_counts", "get_decision_context",
    "city_pulse", "get_started",
}

PAID_TOOLS = {
    "prepare": 100,          # sats
    "suggestions": 100,
    "coordinate": 250,
    "compose_public_comment": 50,
}

async def l402_middleware(request, tool_name):
    if tool_name in FREE_TOOLS:
        return await handle_tool(request, tool_name)

    if has_valid_macaroon(request):
        return await handle_tool(request, tool_name)

    invoice = await create_invoice(
        amount=PAID_TOOLS[tool_name],
        description=f"CivicOS: {tool_name}",
    )
    return Response(
        status=402,
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'}
    )
```

This requires a Lightning node or LSP (Lightning Service Provider) behind the Jurisdiction MCP. Options: Alby Hub (hosted), LND (self-hosted), or Greenlight (CLN cloud). The choice is the operator's — CivicOS provides the middleware, not the node.

## Relationship to Existing Instantiation Patterns

The browser extension becomes the **recommended pattern** for individual users, while existing patterns remain valid for specific contexts:

| Pattern | Best For | Status |
|---------|----------|--------|
| **Browser Extension** | Individual residents (primary distribution) | **New — launch target** |
| MCP App (iframe) | Zero-install trial in Claude.ai/ChatGPT | Existing (limited identity) |
| Claude Desktop (stdio) | Power users, developers | Existing (full identity) |
| Self-Hosted | Maximum sovereignty, organizations | Existing |
| Jurisdiction Open WebUI | City-hosted civic portal, verified residents | Existing (pilot target) |

The extension and Jurisdiction Open WebUI are complementary: the city hosts Open WebUI for residents who want a managed experience with city SSO attestation, while the extension serves users who want civic awareness across all their AI surfaces. Both connect to the same Jurisdiction MCPs and Relay — a voice cast in Open WebUI and a voice cast in the extension are identical signed Nostr events.

## Implementation Phases

### Phase 0: Extension Scaffold + Identity

- Manifest V3 project setup (Svelte or Preact for UI)
- Service worker with identity store
- Easy mode (WebAuthn + PRF) and Private mode (BIP-39 + AES-GCM)
- NIP-07 provider injection (`window.nostr`)
- Options page with identity management
- **Ship:** Extension with identity only, no civic data yet

### Phase 1: MCP Connections + City Pulse

- MCP HTTP client (browser-compatible, no Node APIs)
- Registry-based jurisdiction discovery
- Connection management UI
- Side panel with City Pulse UX (meetings, decisions, voice)
- IndexedDB caching
- **Ship:** Full civic dashboard in side panel

### Phase 2: Voice + Signing

- Relay WebSocket client
- Signing flow (all three tiers)
- Voice support/oppose on agenda items and initiatives
- Commitment tracking and deadline alerts
- Comment threads
- **Ship:** Full civic participation from the extension

### Phase 3: AI Surface Integration

- Content script AI surface detection (Claude.ai, ChatGPT)
- Per-site opt-in permission model with memory
- Context injection (paste mode)
- MCP auto-configuration (where supported)
- Popup quick actions
- **Ship:** Civic context in any AI conversation

### Phase 4: Payments (Post-Launch)

- NWC wallet connection in Options page (connect Alby, Zeus, Phoenix, etc.)
- L402 client in MCP client: detect 402 responses, auto-pay, retry with macaroon
- Spending controls: per-request threshold, daily limit, confirmation prompts
- Transaction history and monthly spending summary
- Cashu wallet (NIP-60) for privacy-preserving relay payments
- **Ship:** Self-sustaining economic model for MCP and relay services
- **Server-side prerequisite:** L402 middleware on Jurisdiction MCP (see Payments section)

### Phase 5: Site Content Interaction (Post-Launch)

- Content script page analysis
- Topic extraction (deterministic, keyword-based)
- Cross-reference with Jurisdiction MCP data
- Side panel contextual civic overlay
- "Ask my AI about this" bridge
- Optional Ollama integration for private topic extraction
- **Ship:** Civic lens on the web

## WebMCP Integration (Post-Launch)

[WebMCP](https://techhub.iodigital.com/articles/web-mcp-making-the-web-ai-agent-ready) is a W3C Draft Community Group Report (published Feb 10, 2026) that adds a `navigator.modelContext` browser API, letting any website — or browser extension — expose structured, callable tools to AI agents. Developed by Google and Microsoft, incubated through the W3C Web Machine Learning community group.

**Status:** Chrome 146 Canary behind a flag. [MCP-B](https://docs.mcp-b.ai/) serves as a polyfill. Chrome stable expected mid-to-late 2026. API surface may change before stabilization.

### How It Works

Instead of AI agents scraping DOM or relying on pasted text, websites and extensions register tools that agents discover and invoke directly:

```javascript
navigator.modelContext.registerTool({
  name: 'get_upcoming_meetings',
  description: 'Get upcoming city council meetings for this jurisdiction',
  inputSchema: {
    type: 'object',
    properties: {
      jurisdiction: { type: 'string' },
      days_ahead: { type: 'number', default: 14 }
    }
  },
  async execute({ jurisdiction, days_ahead }) {
    return await mcpClient.call('get_upcoming_meetings', { jurisdiction, days_ahead });
  }
});
```

Tools execute client-side within the browser's existing session. WebMCP is complementary to Anthropic's MCP — MCP operates server-side (Jurisdiction MCPs), WebMCP operates client-side (browser).

### Impact on Context Injection

WebMCP provides a cleaner mechanism for all three context injection modes:

| Current Mode | WebMCP Alternative | Benefit |
|---|---|---|
| **Mode A: Paste injection** | Extension registers civic tools via `navigator.modelContext` — AI agents discover them natively | Structured tool calls replace pasted text blocks |
| **Mode B: MCP auto-configuration** | Browser natively bridges tools to AI agents — no per-surface DOM hacking | Eliminates the most fragile part of our strategy |
| **Mode C: Contextual side panel** | AI agent calls `get_relevant_civic_context(topic)` directly | Replaces DOM observation with structured queries |

### Extension as WebMCP Tool Provider

When `navigator.modelContext` is available, the extension registers civic tools on every page where the user has granted permission. Any AI agent on any surface discovers:

- `get_upcoming_meetings()` — upcoming meetings filtered by user interests
- `get_voice_counts()` — voice tallies on active agenda items
- `get_user_civic_context()` — user's commitments, voiced items, neighborhood
- `search_decisions()` — historical decision search
- `get_active_initiatives()` — community initiatives the user follows

This is a progressive enhancement — the extension checks for `navigator.modelContext` availability and falls back to paste injection (Mode A) on browsers without it.

### City Websites as WebMCP Tool Providers

Cities could add WebMCP tools directly to their websites (`sanrafael.gov`), exposing civic data to any AI agent browsing the site — without requiring a separate MCP server for basic queries. This is a potential selling point for city adoption post-launch.

### Strategy

- **Phases 0-2:** No dependency on WebMCP. Ship identity, MCP connections, voice/signing as designed.
- **Phase 3 (AI Surface Integration):** Check Chrome stable support. If available, build WebMCP tool registration as primary mode, paste injection as fallback. If not available, ship paste injection, add WebMCP as progressive enhancement when it lands.
- **Phase 5 (Site Content Interaction):** Websites adopting WebMCP expose structured tools, reducing reliance on DOM scraping for topic extraction.

### Not a Dependency

WebMCP validates our architectural bet (browser extension as distribution surface) but is not required for any phase. Every feature works without it. WebMCP just makes the AI surface bridge dramatically cleaner when it arrives.

## Port from Existing Code

The following existing code ports to the extension with minimal changes:

| Existing | Extension Equivalent | Changes Needed |
|----------|---------------------|----------------|
| `civicos-personal-mcp/lib/providers/passkey-provider.ts` | `lib/providers/passkey.ts` | Remove Node.js dependencies |
| `civicos-personal-mcp/lib/providers/local-wallet-provider.ts` | `lib/providers/local-wallet.ts` | IndexedDB → chrome.storage |
| `civicos-personal-mcp/lib/providers/crypto.ts` | `lib/providers/crypto.ts` | Already browser-compatible (Web Crypto) |
| `civicos-personal-mcp/lib/jurisdiction-mcp-client.ts` | `lib/mcp-client.ts` | Remove Node fetch, use browser fetch |
| `civicos-openwebui/src/lib/components/civic/CityPulse.svelte` | `side-panel/city-pulse.svelte` | Remove Open WebUI dependencies, standalone |
| `civicos-openwebui/src/lib/apis/civic.ts` | `lib/civic-api.ts` | Point to MCP client instead of REST |
| `civicos-relay/src/civicos_relay/nostr/models.py` | `lib/nostr-models.ts` | TypeScript equivalent (partially exists) |

The `SigningProvider` abstraction is surface-agnostic by design — it ports directly. The City Pulse Svelte component is the largest porting effort but the data model and section structure are identical.

For payments, [Alby's MCP server](https://github.com/getAlby/mcp) provides reference implementations for NWC client, L402 handling, and LNURL — these can be adapted for the extension's `lib/payments/` module rather than built from scratch.
