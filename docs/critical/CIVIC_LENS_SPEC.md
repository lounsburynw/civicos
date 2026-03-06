# Civic Lens — Specification

**Status:** Spec
**Created:** 2026-03-06
**Related:** `BROWSER_EXTENSION_ARCHITECTURE.md` (Phase 5), `EDGE_INTELLIGENCE_ARCHITECTURE.md`

## Problem

Civic engagement is pull-based. Users must seek out meetings, agendas, and comment periods. Meanwhile, they spend hours browsing news and social media — often reading about the very issues their city is deciding on — without knowing they can act.

The gap between awareness and action is not informational. It's contextual. The user *sees* the issue. They just don't see the civic action available to them at that moment.

## Solution

**Civic Lens** overlays civic context on any web page the user browses. When the page content intersects with actionable civic items — upcoming votes, open comment periods, active initiatives — the extension surfaces a subtle, dismissible chip linking the user to specific actions.

The user's civic journal (their explicit interest graph) filters matches so only personally relevant items surface. No journal entry, no match — the lens is quiet by default.

## Design Principles

1. **Opt-in per domain.** The extension never reads page content without explicit consent. Default is OFF everywhere.
2. **Privacy by architecture.** All page analysis happens client-side. No browsing data leaves the device. No browsing patterns are stored. No telemetry.
3. **Quiet by default, useful when active.** The chip is small, dismissible, and frequency-capped. The goal is serendipity, not notification fatigue.
4. **Transparent matching.** Every match shows *why* it appeared — which journal entry or interest triggered it. The user always understands the connection.
5. **Action-oriented.** Matches only surface when there's something the user can *do* — voice a stance, submit a comment, attend a meeting, join an initiative. Informational matches without actions are suppressed.

## User Flow

```
User reads Marin IJ article: "Downtown parking meters to get rate hike"
                |
                v
Content script extracts page signals (title, description, article text)
                |
                v
Matcher checks against cached civic data + journal interests
  - Agenda item #4.3: "Parking Meter Rate Adjustment" (Planning Commission, Mar 12)
  - Journal match: "What frustrates me: downtown parking situation"
  - Actionable: comment period open, 8 voices recorded, hearing in 6 days
                |
                v
Chip appears (bottom-right):
  +--------------------------------------+
  |  [icon] 1 civic action related       |
  +--------------------------------------+
                |
        user clicks chip
                |
                v
Expanded card:
  +----------------------------------------------+
  |  Related to what you're reading              |
  |                                              |
  |  Parking Meter Rate Adjustment               |
  |  Planning Commission - Mar 12 @ 6pm          |
  |  8 neighbors have weighed in                 |
  |  [Support] [Oppose] [Details ->]             |
  |                                              |
  |  -- Why this matched --                      |
  |  Journal: "downtown parking situation"        |
  |  + keyword match: "parking meters"           |
  |                                              |
  |  [Open City Pulse] [Don't show on this site] |
  +----------------------------------------------+
                |
        user taps [Support]
                |
                v
Voice recorded (signed via extension identity)
Chip updates: "Voice recorded. 9 neighbors have weighed in."
                |
        user taps [Details ->]
                |
                v
Side panel opens to full item context with testimony,
regulatory stack, and "Ask my AI about this" bridge
```

## Architecture

### System Diagram

```
+-------------------------------------------------------------------+
|  Web Page (any user-enabled domain)                               |
|                                                                   |
|  civic-lens.ts (content script, ISOLATED world)                   |
|  +-------------------------------------------------------------+ |
|  | 1. Extract signals: title, meta, og:tags, article text       | |
|  | 2. Send to service worker via chrome.runtime.sendMessage()   | |
|  | 3. Receive match results                                     | |
|  | 4. Render overlay via Shadow DOM (style-isolated)            | |
|  +-------------------------------------------------------------+ |
+-------------------------------------------------------------------+
        |  CIVIC_LENS_MATCH message
        v
+-------------------------------------------------------------------+
|  Service Worker                                                   |
|                                                                   |
|  civic-lens-matcher.ts (matching engine)                          |
|  +-------------------------------------------------------------+ |
|  |                                                               | |
|  |  Layer 1: Deterministic (instant, no network)                 | |
|  |  - Tokenize page signals into normalized keywords             | |
|  |  - Match against cached CityPulseData items                   | |
|  |  - Filter through journal interest index                      | |
|  |  - Score: keyword_overlap * journal_relevance * urgency       | |
|  |                                                               | |
|  |  Layer 2: On-Device Topic Extraction (~200ms)                 | |
|  |  - Chrome Nano (Gemini Nano) or skip if unavailable           | |
|  |  - Prompt: "Extract civic topics from: {title + 300 words}"   | |
|  |  - Re-run Layer 1 with extracted topics                       | |
|  |  - Bridges vocabulary gap (article words != agenda words)     | |
|  |                                                               | |
|  |  Layer 3: Semantic MCP Search (opt-in, network)               | |
|  |  - search_meeting_history(extracted_topics)                   | |
|  |  - find_similar_issues(extracted_topics)                      | |
|  |  - Only if user enables "deep matching" in settings           | |
|  |  - Results cached per URL for 1 hour                          | |
|  |                                                               | |
|  +-------------------------------------------------------------+ |
|                                                                   |
|  civic-lens-cache.ts (data layer)                                 |
|  +-------------------------------------------------------------+ |
|  |  Pulse cache: CityPulseData refreshed every 30 min           | |
|  |  Journal index: pre-tokenized keywords from journal sections  | |
|  |  Match cache: keyed by URL, TTL 1hr news / 24hr static       | |
|  |  Domain permissions: user-enabled domains list                | |
|  +-------------------------------------------------------------+ |
+-------------------------------------------------------------------+
        |  reads civic data
        v
+-------------------------------------------------------------------+
|  Jurisdiction MCP (public, read-only)                             |
|  - CityPulse: meetings, agenda items, outcomes, comment periods  |
|  - search_meeting_history, find_similar_issues (Layer 3 only)    |
+-------------------------------------------------------------------+
```

### Components

#### 1. Content Script: `src/content-scripts/civic-lens.ts`

Runs on user-enabled domains in ISOLATED world at document_idle.

**Responsibilities:**
- Extract page signals (title, meta description, Open Graph tags, article body text)
- Send signals to service worker for matching
- Receive match results and render overlay
- Handle user interactions (expand, dismiss, voice, navigate)
- Observe SPA navigation (title/URL changes via MutationObserver)

**Page Signal Extraction:**

```typescript
interface PageSignals {
  url: string;
  domain: string;
  title: string;
  description: string;        // meta description or og:description
  articleText: string;         // first 500 words of main article content
  selectedText?: string;       // user-selected text, if any
}
```

Article text extraction strategy:
1. `<article>` element innerText
2. `[role="main"]` innerText
3. Largest `<div>` or `<section>` by text content length
4. Fallback: skip (rely on title + description only)

Text is truncated to 500 words before sending to service worker. No full page content is ever stored or transmitted.

**Overlay rendering:**

The overlay is injected as a custom element with Shadow DOM for complete style isolation from the host page. The Svelte component (`CivicLensOverlay.svelte`) mounts inside the shadow root.

```typescript
// Injection
const host = document.createElement('civicos-lens');
document.body.appendChild(host);
const shadow = host.attachShadow({ mode: 'closed' });
// Mount Svelte component into shadow root
```

**SPA navigation detection:**

```typescript
// Detect client-side navigation (React, Next.js, etc.)
const observer = new MutationObserver(() => {
  if (document.title !== lastTitle || location.href !== lastUrl) {
    lastTitle = document.title;
    lastUrl = location.href;
    debouncedMatch(); // Re-extract and re-match after 1s debounce
  }
});
observer.observe(document.querySelector('head > title'), { childList: true });
```

#### 2. Matching Engine: `src/lib/civic-lens-matcher.ts`

Runs in the service worker context. Stateless function that takes page signals + cached data and returns matches.

**Interface:**

```typescript
interface CivicLensMatch {
  // What matched
  itemType: 'agenda_item' | 'decision' | 'comment_period' | 'hearing'
              | 'initiative' | 'issue' | 'bill';
  itemId: string;
  title: string;
  body: string;                      // e.g., "Planning Commission"
  date?: string;                     // ISO date if time-bound

  // Community context
  voiceCount?: number;               // total voices on this item
  commentCount?: number;

  // Why it matched
  matchReason: MatchReason;

  // What user can do
  actions: CivicLensAction[];

  // Scoring
  relevanceScore: number;            // 0.0 - 1.0
  urgencyScore: number;              // 0.0 - 1.0 (higher = sooner deadline)
  combinedScore: number;             // weighted combination
}

interface MatchReason {
  journalSection?: string;           // "What frustrates me"
  journalExcerpt?: string;           // "downtown parking situation"
  keywordMatches: string[];          // ["parking", "meters", "downtown"]
  matchLayer: 1 | 2 | 3;            // which layer produced the match
}

interface CivicLensAction {
  type: 'voice' | 'comment' | 'calendar' | 'details' | 'initiative';
  label: string;                     // "Support", "Submit comment", "Add to calendar"
  entityId?: string;                 // for voice/comment actions
}
```

**Layer 1: Deterministic Matching**

```
Input: PageSignals + PulseCache + JournalIndex
Output: CivicLensMatch[]

Algorithm:
  1. Tokenize page signals:
     - Split title + description + articleText into lowercase words
     - Remove stop words (the, a, is, at, etc.)
     - Extract named entities: proper nouns, quoted phrases, numbers
     - Normalize: "parking meters" -> ["parking", "meter"]

  2. For each item in cached CityPulseData:
     a. Tokenize item title + description
     b. Compute keyword overlap score (Jaccard similarity)
     c. If overlap > 0.15:
        - Check journal index for interest match
        - If journal match exists:
          - Check if item has available actions (vote open, comment period, etc.)
          - If actionable: add to matches with scores

  3. Score computation:
     keyword_score = |page_tokens ∩ item_tokens| / |page_tokens ∪ item_tokens|
     journal_score = 1.0 if exact phrase match, 0.5 if keyword overlap
     urgency_score = max(0, 1.0 - days_until_deadline / 14)  // peaks at deadline
     combined = 0.4 * keyword + 0.3 * journal + 0.3 * urgency

  4. Filter: combined >= 0.3
  5. Sort by combined descending, cap at 5 matches
```

**Layer 2: Chrome Nano Topic Extraction**

Activated when Layer 1 returns zero matches but the page has substantial text (> 100 words).

```
Prompt:
  "Extract 3-5 civic policy topics from this text. Return only a
   JSON array of short topic phrases. Example: ["housing density",
   "parking reform", "bike infrastructure"]

   Text: {title}. {first 300 words of article}"

Response: ["parking reform", "downtown business district", "meter rates"]

Then: re-run Layer 1 matching using extracted topics as synthetic page tokens.
```

Chrome Nano is on-device (Gemini Nano in Chrome 138+). If unavailable, Layer 2 is skipped. No fallback to cloud — privacy is non-negotiable here.

**Layer 3: Semantic MCP Search**

Activated only when user enables "deep matching" in settings. Makes network calls to the Jurisdiction MCP.

```
For each topic extracted (Layer 1 keywords or Layer 2 topics):
  - POST /api/tools/search-meeting-history {query: topic, limit: 3}
  - POST /api/tools/find-similar-issues {topic: topic, semantic: true, limit: 3}

Filter results with score > 0.6.
De-duplicate against Layer 1/2 matches.
Cache results keyed by URL for 1 hour.
```

#### 3. Cache Layer: `src/lib/civic-lens-cache.ts`

**Pulse Cache:**

```typescript
// Refreshed every 30 min via chrome.alarms
// Also refreshed when side panel loads (piggybacks on existing fetch)
// Stored in chrome.storage.session (ephemeral, cleared on browser restart)

const PULSE_CACHE_KEY = 'civicos_lens_pulse';
const PULSE_CACHE_TTL = 30 * 60 * 1000; // 30 minutes

interface PulseCache {
  data: CityPulseData;
  parentData?: ParentPulseData;  // state/federal comment periods, hearings
  fetchedAt: number;
}
```

**Journal Index:**

```typescript
// Pre-computed keyword index from civic journal text
// Rebuilt when journal changes (chrome.storage.onChanged listener)
// Stored in chrome.storage.session

const JOURNAL_INDEX_KEY = 'civicos_lens_journal_index';

interface JournalIndex {
  // section name -> normalized keyword set
  sections: Record<string, Set<string>>;
  // all keywords flattened for fast lookup
  allKeywords: Set<string>;
  // original excerpts for "why this matched" display
  excerpts: Record<string, string>;  // keyword -> original text
  builtAt: number;
}
```

**Match Cache:**

```typescript
// Prevents re-matching on page revisits and repeat navigations
// Keyed by canonical URL (strip query params for news sites)
// Stored in chrome.storage.session

const MATCH_CACHE_KEY = 'civicos_lens_matches';

interface MatchCacheEntry {
  url: string;
  matches: CivicLensMatch[];
  cachedAt: number;
  ttl: number;  // 1hr for news, 24hr for static, 0 for no-cache
}
```

#### 4. Overlay UI: `src/components/CivicLensOverlay.svelte`

Mounted inside Shadow DOM on the host page. Three states:

**Chip (default):**

```
Position: fixed, bottom-right (24px inset)
Size: compact pill shape
Content: "[icon] N civic actions"
Interaction: click to expand, drag to reposition, X to dismiss
Animation: slide-in from right on appear, fade-out on dismiss
```

Chip design constraints:
- Must not obscure page content (fixed bottom-right, small)
- Must not look like an ad or cookie banner
- Must feel native to the extension, not the page
- Semi-transparent background, respects prefers-color-scheme

**Expanded Card:**

```
Position: anchored to chip, expands upward
Size: 360px wide, variable height (max 480px, scrollable)
Content:
  - Header: "Related to what you're reading"
  - Match list (1-5 items), each with:
    - Item title + body + date
    - Community context (voice count, comment count)
    - Action buttons (Voice, Comment, Calendar, Details)
  - "Why this matched" section (collapsible)
  - Footer: [Open City Pulse] [Don't show on this site]
```

**Action states:**

Voice buttons trigger signing flow via service worker (same as side panel). On success, the chip updates with confirmation. Calendar buttons generate .ics download or open Google Calendar link. Details button opens side panel to the full item context.

#### 5. Service Worker Integration

New message types added to `src/lib/messaging.ts`:

```typescript
// Content script -> Service worker
| { type: 'CIVIC_LENS_MATCH'; signals: PageSignals }
// Service worker -> Content script (response)
| { matches: CivicLensMatch[]; cached: boolean }

// Content script -> Service worker (user actions)
| { type: 'CIVIC_LENS_VOICE'; entityId: string; stance: 'support' | 'oppose' | 'watching' }
| { type: 'CIVIC_LENS_DISMISS_DOMAIN'; domain: string }
| { type: 'CIVIC_LENS_OPEN_DETAILS'; itemId: string }

// Service worker (internal, via chrome.alarms)
| 'CIVIC_LENS_REFRESH_PULSE'
```

#### 6. Domain Permissions

```typescript
// Stored in chrome.storage.sync (syncs across devices)
const LENS_DOMAINS_KEY = 'civicos_lens_domains';
const LENS_GLOBAL_KEY = 'civicos_lens_enabled';

interface LensDomainConfig {
  enabledDomains: string[];       // ["marinij.com", "patch.com", ...]
  disabledDomains: string[];      // explicitly disabled (user clicked "don't show")
  globalEnabled: boolean;          // master switch (default: true once any domain enabled)
}
```

**Activation flow:**

Content script checks domain permissions before extracting signals. If domain is not enabled, the script does nothing (no page reading, no overlay). Domain enablement happens via:

1. Popup quick action: "Enable Civic Lens for {current domain}?" toggle
2. Expanded card footer: "Don't show on this site" (adds to disabled list)
3. Options page: manage all enabled/disabled domains

The first time a user enables any domain, show a one-time explainer:

> Civic Lens reads page titles and article text on enabled sites to find related civic actions. All analysis happens on your device. No browsing data is stored or sent anywhere.

### Manifest Changes

```json
{
  "content_scripts": [
    // ... existing nip07-provider and claude-bridge entries ...
    {
      "matches": ["<all_urls>"],
      "js": ["src/content-scripts/civic-lens.js"],
      "run_at": "document_idle",
      "world": "ISOLATED"
    }
  ],
  "permissions": [
    "sidePanel",
    "storage",
    "alarms"       // already present, used for pulse refresh
  ]
}
```

Note: The content script runs on all URLs but immediately exits if the domain is not in the user's enabled list. This avoids needing `chrome.scripting.registerContentScripts()` dynamic registration (which requires the `scripting` permission) while keeping the privacy model intact — no page content is read on non-enabled domains.

Alternative approach: use `chrome.scripting.registerContentScripts()` to dynamically inject only on enabled domains. This is cleaner (script doesn't load at all on non-enabled sites) but requires adding the `scripting` permission. Worth evaluating during implementation.

## Matching Quality

### What Makes a Good Match

A match should satisfy ALL of:
1. **Topic overlap** — the page content relates to a civic item
2. **Personal relevance** — the user's journal indicates they care about this topic
3. **Actionable** — there's something the user can do (voice, comment, attend, join)

Matches that satisfy only 1 or 2 are suppressed. This is the critical filter that prevents noise.

### False Positive Mitigation

| Risk | Mitigation |
|------|-----------|
| Generic keywords ("city", "plan", "meeting") | Stop word list includes civic-generic terms. Require 2+ non-generic keyword matches. |
| Stale matches (decided items) | Filter pulse cache for only active/upcoming items. Exclude items with past deadlines. |
| Same match on every page of a news site | Match cache prevents re-showing. Frequency cap: max 1 chip per domain per hour after dismissal. |
| User fatigue from too many matches | Cap at 3 matches per page. Prioritize by combined score. |
| Irrelevant semantic matches (Layer 3) | High threshold (score > 0.6). Require journal interest overlap. |

### False Negative Mitigation

| Risk | Mitigation |
|------|-----------|
| Article uses different words than agenda | Layer 2 (Chrome Nano) extracts abstract topics, bridging vocabulary gap |
| User hasn't written relevant journal entries | Journal suggestions system prompts users to fill gaps. Over time, journal becomes richer. |
| Article about nearby jurisdiction not connected | Multi-jurisdiction pulse cache (parent jurisdictions already fetched for side panel) |

## Frequency & Fatigue Controls

```
Per-domain:
  - Max 1 chip appearance per page load
  - After dismiss: no chips on this domain for 1 hour
  - After "Don't show on this site": permanent (until re-enabled)

Per-session:
  - Max 10 chip appearances per browser session
  - Counter resets on browser restart (session storage)

Per-item:
  - Same civic item shown max 3 times across all domains
  - After user takes action (voice/comment): suppress that item from future matches
```

## "Ask My AI About This"

When the user wants deeper engagement, the expanded card includes an "Ask my AI" button that:

1. Extracts article text (or user-selected text)
2. Fetches full item context from Jurisdiction MCP (`getItemContext(itemId, ['history', 'regulatory', 'testimony'], 'standard')`)
3. Composes a context block:

```
I'm reading this article:
"{article title}"
{article excerpt or selected text}

Related civic item:
{item title} — {body}, {date}
{regulatory context, testimony summary, voice counts}

My civic context:
{journal excerpt that triggered the match}

What actions can I take on this? What should I know before the {hearing/vote/comment deadline}?
```

4. Injects into the user's preferred AI surface (Claude.ai via existing bridge, or clipboard for others)

This reuses the existing claude-bridge.ts pattern — store context in session storage, navigate to Claude.ai, bridge script auto-injects.

## Privacy Specification

Civic Lens exists within a system that protects pseudonymous civic voices. A user who voices support for a controversial housing proposal must trust that their browsing patterns, interests, and identity cannot be correlated or de-anonymized. **Any Civic Lens implementation that weakens this guarantee is a regression on the core product, regardless of the feature value it provides.**

This is not a secondary concern. Pseudonymous civic participation is the foundational promise of CivicOS. Civic Lens must enhance civic engagement without creating new surveillance vectors — even subtle ones.

### Threat Model

| Threat | Description | Mitigation |
|--------|-------------|-----------|
| **Interest profiling** | An observer infers a user's political positions from their browsing + matching patterns | All matching is client-side. No server ever sees which pages triggered matches or which civic items were shown. |
| **Browsing correlation** | Layer 3 semantic queries reveal what the user is reading | Layer 3 sends only extracted topic keywords (e.g., "parking reform"), never URLs, article text, or domain names. Topics are indistinguishable from manual City Pulse searches. |
| **Journal exfiltration** | The civic journal (interest graph) leaks to a server | Journal never leaves the device except via user-initiated encrypted relay sync. Relay sees only ciphertext. |
| **Voice-to-browsing linkage** | A voice action taken from Civic Lens overlay can be correlated with the page the user was reading | Voice events contain only the entity ID and stance — same payload as voicing from City Pulse. No referrer URL, no page context, no timestamp correlation beyond the Nostr event's `created_at`. |
| **Domain list as signal** | The list of Civic Lens-enabled domains reveals media consumption habits | Stored locally in chrome.storage.sync (encrypted by Chrome). Never sent to any CivicOS server. If relay-synced in future, must be encrypted client-side. |
| **Frequency analysis** | Timing patterns of MCP queries (Layer 3) reveal browsing cadence | Layer 3 results are cached per URL for 1 hour and batched with the 30-min pulse refresh where possible, flattening timing signals. |
| **Cross-surface correlation** | A mobile share or web app URL paste reveals the article to the server | Server-side signal extraction (if implemented) must be stateless — no logging of URLs, no association with user identity. Prefer client-side extraction. See Open Question #8. |

### Pseudonymity Invariants

These invariants must hold across all surfaces and all build phases. They are not negotiable.

1. **No server learns what the user is reading.** Page signals (URL, title, article text) are extracted and processed client-side. Layer 3 sends only abstracted topic keywords, never source material.

2. **No server learns what matched.** Match results (which civic items were shown on which pages) exist only in client-side session storage. They are never transmitted, logged, or recoverable.

3. **Civic actions are context-free.** A voice, comment, or commitment cast from the Civic Lens overlay is indistinguishable from one cast from City Pulse, the MCP, or any other surface. The signed Nostr event carries no provenance about where the user was when they acted.

4. **The interest graph stays local.** The civic journal and journal index are the user's private data. They sync only via user-initiated encrypted relay backup or Chrome's built-in sync. No CivicOS server can read them.

5. **Domain preferences are private.** Which sites the user enables for Civic Lens is a browsing preference, not civic data. It is never shared with any server.

6. **No behavioral telemetry.** Civic Lens does not record chip impressions, expand rates, dismiss rates, or action conversion rates on any server. Local-only metrics (stored in extension session storage) may be shown to the user in a personal dashboard but are never transmitted.

### Implementation Checkpoints

Every build phase must pass these checks before shipping:

- [ ] **Network audit:** Enumerate all outbound requests. Confirm no page URLs, article text, or domain names leave the device (except abstracted topic keywords for Layer 3).
- [ ] **Storage audit:** Confirm all match results, page signals, and frequency counters use session storage (ephemeral) or local storage (device-only). None use sync storage that could be intercepted.
- [ ] **Voice event audit:** Confirm voice/comment events cast from the overlay contain no fields that identify the source surface (no referrer, no `via: "lens"` tag, no browsing context).
- [ ] **Timing audit:** Confirm Layer 3 queries cannot be trivially correlated with page loads (caching and batching flatten timing).
- [ ] **Cross-surface audit (when applicable):** Confirm mobile share and web app URL paste do not log, store, or associate URLs with user identity on any server.

### What the content script reads (on enabled domains only)

- `document.title`
- `<meta name="description">` content
- `<meta property="og:title">` and `og:description` content
- Article body text (first 500 words, extracted via DOM heuristics)
- `location.href`

### What stays on device (always)

- All extracted page signals (never sent to any server)
- All matching results (computed locally)
- Journal content and interest index
- Domain enable/disable preferences
- Match history and frequency counters
- Chrome Nano inference (on-device)

### What leaves the device (only with Layer 3 enabled)

- Extracted topic keywords sent to Jurisdiction MCP for semantic search
- NOT the URL, NOT the article text, NOT the domain — only topic phrases like "parking reform"
- These are equivalent to manual searches the user could run in City Pulse

### What is never done

- No browsing history is recorded
- No page content is stored beyond the current matching cycle
- No cross-domain tracking or correlation
- No telemetry about which domains the user enables
- No data sent to CivicOS servers (only to Jurisdiction MCP for Layer 3, and that's read-only public data)

## Relationship to Existing Architecture

### Reuses

| Component | How Civic Lens Uses It |
|-----------|----------------------|
| CityPulseData | Primary matching corpus (cached, already fetched for side panel) |
| Civic Journal | Interest filter (already stored in chrome.storage.local) |
| Chrome Nano | Topic extraction (already integrated as AI provider) |
| Voice/Comment APIs | Action execution (same as side panel voice buttons) |
| Claude Bridge | "Ask my AI" context injection (same pattern) |
| Identity/Signing | Voice actions use existing signing flow |
| chrome.alarms | Pulse refresh (already used for background tasks) |

### New

| Component | Purpose |
|-----------|---------|
| `civic-lens.ts` | Content script for page signal extraction + overlay |
| `civic-lens-matcher.ts` | Three-layer matching engine |
| `civic-lens-cache.ts` | Pulse cache, journal index, match cache |
| `CivicLensOverlay.svelte` | Shadow DOM overlay UI |
| Domain permissions | Per-site enable/disable with sync storage |

## Build Phases

### Phase A: Deterministic Lens (MVP)

Layer 1 matching only. No AI, no network calls for matching.

**Delivers:**
- Content script with page signal extraction
- Deterministic keyword matcher against cached pulse data
- Journal interest filtering
- Chip + expanded card overlay (Shadow DOM)
- Per-domain permissions (popup toggle)
- Voice action from overlay
- Match cache + frequency controls

**What it proves:** Does keyword matching against cached civic data produce useful, non-noisy results on real news sites?

### Phase B: Intelligent Lens

Add Layer 2 (Chrome Nano topic extraction).

**Delivers:**
- On-device topic extraction for pages where Layer 1 misses
- Vocabulary bridging (article language -> civic language)
- Improved recall without sacrificing privacy

**What it proves:** Does on-device LLM meaningfully improve match quality beyond keyword overlap?

### Phase C: Deep Lens

Add Layer 3 (semantic MCP search) + "Ask my AI" bridge.

**Delivers:**
- Opt-in semantic search via Jurisdiction MCP
- Full item context assembly for matched items
- "Ask my AI about this" flow (article + civic context -> AI surface)
- Deep matching settings in options page

**What it proves:** Does semantic search find matches that deterministic + Nano miss? Is the "ask my AI" bridge a natural escalation path?

### Phase D: Social Lens

Add community context and cross-user signals.

**Delivers:**
- "N neighbors weighed in" context on matches
- Initiative discovery ("12 people in your area care about this")
- Comment synthesis snippets in expanded card
- Commitment suggestions ("Submit a comment before Mar 12")

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Match precision | >70% of shown matches rated "relevant" by user | Implicit: user expands chip (positive) vs dismisses (negative) |
| Action conversion | >10% of expanded cards lead to voice/comment/calendar action | Count actions taken from overlay |
| Domain retention | >50% of enabled domains stay enabled after 2 weeks | Check disabled-domain list growth |
| Fatigue signal | <3 "don't show on this site" per user per month | Count domain disables |
| Journal enrichment | Users with Civic Lens have 2x richer journals | Compare journal word count, lens-on vs lens-off |

All metrics computed locally from extension storage. No analytics sent anywhere.

## WebMCP Compatibility

[WebMCP](https://techhub.iodigital.com/articles/web-mcp-making-the-web-ai-agent-ready) is a W3C Draft Community Group Report that adds `navigator.modelContext` to browsers, letting websites and extensions expose structured tools to AI agents. Chrome stable expected mid-to-late 2026.

Civic Lens intersects with WebMCP in two ways: as a **consumer** of page-provided tools and as a **provider** of civic tools.

### Civic Lens as WebMCP Consumer

When a news site or government site adopts WebMCP, it can expose structured metadata that replaces DOM scraping:

```javascript
// marinij.com registers WebMCP tools
navigator.modelContext.registerTool({
  name: 'get_article_metadata',
  description: 'Get structured metadata for the current article',
  async execute() {
    return {
      topics: ['parking', 'downtown', 'city council'],
      entities: ['San Rafael', 'Planning Commission'],
      location: 'San Rafael, CA',
      published: '2026-03-06'
    };
  }
});
```

If `navigator.modelContext` is available and the page provides topic/entity tools, Civic Lens can use structured metadata instead of DOM heuristics for signal extraction. This is a progressive enhancement — the content script checks for WebMCP first, falls back to DOM extraction.

```typescript
// In civic-lens.ts signal extraction
async function extractSignals(): Promise<PageSignals> {
  // Prefer WebMCP structured metadata when available
  if ('modelContext' in navigator) {
    const tools = await navigator.modelContext.getTools();
    const metadataTool = tools.find(t =>
      t.name.includes('article_metadata') || t.name.includes('page_topics')
    );
    if (metadataTool) {
      const metadata = await metadataTool.execute();
      return { ...baseSignals, topics: metadata.topics, structured: true };
    }
  }
  // Fallback: DOM heuristic extraction
  return extractFromDOM();
}
```

**Impact on matching quality:** WebMCP-provided topics are author-curated, eliminating the vocabulary gap problem that Layer 2 (Chrome Nano) exists to solve. On WebMCP-enabled sites, matching can skip directly to Layer 1 with high-quality tokens.

### Civic Lens as WebMCP Tool Provider

When the user has Civic Lens active, the extension can register civic tools on the page via `navigator.modelContext`. Any AI agent on any surface then discovers civic actions without going through the side panel or clipboard injection:

```javascript
// Extension registers on user-enabled domains
navigator.modelContext.registerTool({
  name: 'get_civic_actions_for_page',
  description: 'Get civic actions related to the current page content',
  async execute() {
    // Returns the same CivicLensMatch[] that the overlay would show
    return await chrome.runtime.sendMessage({
      type: 'CIVIC_LENS_MATCH',
      signals: await extractSignals()
    });
  }
});

navigator.modelContext.registerTool({
  name: 'voice_civic_stance',
  description: 'Voice support or opposition on a civic item',
  inputSchema: {
    type: 'object',
    properties: {
      entityId: { type: 'string' },
      stance: { enum: ['support', 'oppose', 'watching'] }
    }
  },
  async execute({ entityId, stance }) {
    return await chrome.runtime.sendMessage({
      type: 'CIVIC_LENS_VOICE', entityId, stance
    });
  }
});
```

This transforms "Ask my AI about this" from a clipboard-paste workflow into a native tool call. The AI agent on the page can directly query civic context and take actions — the extension provides the civic substrate as structured tools rather than injected text.

### Strategy

- **Phase A-B:** No WebMCP dependency. Ship DOM extraction + overlay as designed.
- **Phase C:** Check `navigator.modelContext` availability. If present, register civic tools as progressive enhancement alongside the overlay. The overlay remains the primary UX; WebMCP tools are a bonus for users on AI surfaces.
- **Post-stabilization:** If WebMCP reaches Chrome stable, evaluate whether the overlay can be replaced entirely by WebMCP tool registration on AI-enabled pages. The overlay remains necessary for non-AI browsing contexts (news sites, social media) where no agent is listening.

### Not a Dependency

Civic Lens works fully without WebMCP. WebMCP improves two things when available: (1) signal extraction quality on publisher sites, (2) action execution on AI surfaces. Both are progressive enhancements on top of the DOM extraction + overlay foundation.

## Multi-Surface Portability

The browser extension is the first surface for Civic Lens, not the only one. The matching engine and civic data layer are designed to port across surfaces as CivicOS distribution expands.

### Planned Surfaces

| Surface | Platform | Lens Delivery | Signal Source | Timeline |
|---------|----------|--------------|---------------|----------|
| **Chrome Extension** | Desktop browsers | Content script overlay | DOM extraction, WebMCP | Phase A (first) |
| **Mobile App** (iOS/Android) | Phone/tablet | Share sheet + notification | OS share intent, URL metadata | Post-launch |
| **Web App** (civicosproject.org) | Any browser | Embedded widget, URL paste | User-provided URL, bookmarklet | Post-launch |
| **Safari Extension** | macOS/iOS Safari | Content script (WebExtensions API) | Same as Chrome | If demand warrants |

### Architectural Separation

To enable portability, Civic Lens is split into platform-agnostic and platform-specific layers:

```
Platform-agnostic (portable):
  civic-lens-matcher.ts    — matching engine (pure functions, no browser APIs)
  civic-lens-cache.ts      — cache logic (storage interface, not chrome.storage directly)
  types.ts                 — CivicLensMatch, PageSignals, MatchReason, etc.

Platform-specific (per surface):
  Chrome:   civic-lens.ts content script + CivicLensOverlay.svelte + chrome.storage
  Mobile:   share extension + push notifications + platform-native UI
  Web app:  URL input + server-side signal extraction + embedded component
```

The matcher takes `PageSignals` + `PulseCache` + `JournalIndex` and returns `CivicLensMatch[]`. It has no dependency on Chrome APIs, DOM access, or any specific runtime. This is the core that ports everywhere.

### Mobile: Share Sheet + Notifications

Mobile users don't have content scripts, but they have two powerful primitives:

**Share sheet integration (iOS/Android):**

The user reads a news article in any app, taps Share, selects "CivicOS: Find Civic Actions." The share extension receives the URL + title, extracts signals (via server-side fetch if needed), runs the matcher, and shows results in a share sheet card.

```
User reads article in Safari/Chrome/News app
  -> Share -> "CivicOS: Find Civic Actions"
    -> Card: "Parking Meter Rate Adjustment — voice your stance"
      -> Tap -> Opens CivicOS app to full item context
```

This is the mobile equivalent of the desktop overlay chip. The interaction is intentional (user explicitly shares) rather than passive (content script auto-detects), which suits mobile interaction patterns better.

**Push notifications (proactive):**

When the user's journal interests match a new civic item (detected during periodic pulse refresh), the mobile app sends a local notification:

```
"New item matching your interests: Parking Meter Rate Adjustment
 Comment period closes Mar 12. Tap to weigh in."
```

This inverts the Civic Lens model — instead of matching page content against civic data, it matches civic data against the user's interest profile. Same matching engine, different trigger.

**Technical approach:**

For mobile, the likely path is a lightweight native wrapper (Capacitor, React Native, or platform-native) around the same `@civicos/client` SDK that the extension uses. The matcher runs locally on the device. The civic journal syncs via chrome.storage.sync (if the user also has the extension) or via the relay (encrypted, user-controlled).

### Web App: URL Paste + Bookmarklet

For users without the extension or on restricted browsers:

**URL paste:** The CivicOS web app includes a "Civic Lens" page where users paste a URL. Two approaches, with different privacy profiles:

- **Client-side (preferred):** JavaScript on the web app page fetches the URL via the browser (subject to CORS), extracts signals client-side, and runs the matcher in-browser against cached pulse data. The server never sees the URL. This preserves the pseudonymity invariants.
- **Server-side (fallback):** If CORS blocks client-side fetch, the server proxies the page fetch. **This creates a privacy risk:** the server sees which URL the user submitted. If implemented, the proxy must be stateless — no request logging, no URL storage, no association with user identity. The user must be informed: "This URL will be fetched by our server to extract article content. We do not log or store it." Prefer client-side extraction and only fall back to server proxy with explicit user consent.

**Bookmarklet:** A JavaScript bookmarklet that extracts page signals client-side and opens the CivicOS web app with those signals as URL parameters. Functions like a lightweight, install-free version of the content script. Because extraction happens in the user's browser, the pseudonymity invariants are fully preserved — the server receives only the extracted signals (title, description), not the source URL, unless the user explicitly includes it.

```javascript
// Bookmarklet (minified for bookmark bar)
javascript:void(window.open(
  'https://civicosproject.org/lens?title='+encodeURIComponent(document.title)+
  '&url='+encodeURIComponent(location.href)+
  '&desc='+encodeURIComponent(document.querySelector('meta[name=description]')?.content||'')
))
```

### Data Portability Across Surfaces

The civic journal is the user's interest graph that powers Civic Lens matching. It must be available on every surface:

| Storage | Sync Mechanism | Latency |
|---------|---------------|---------|
| chrome.storage.sync | Chrome's built-in sync | Near-instant across Chrome instances |
| Relay (encrypted) | Nostr kind-30803 event (user journal backup) | Seconds, requires relay connection |
| Local file export | Manual JSON export/import | User-initiated |

The relay-based sync is the universal path. A signed, encrypted journal event stored on the relay can be retrieved by any surface that has the user's keys. The extension, mobile app, and web app all read from the same source.

### Implementation Guidance

When building Civic Lens for the Chrome extension (Phase A-D), keep these portability constraints in mind:

1. **Matcher must be pure.** No `chrome.*` APIs, no `document.*` access, no `window.*` globals. Takes typed inputs, returns typed outputs. This is the most important constraint.

2. **Cache interface, not implementation.** Define a `LensCacheStorage` interface. The Chrome implementation uses `chrome.storage.session`. Mobile uses platform keychain or SQLite. Web app uses server-side Redis or in-memory.

3. **Signal extraction is per-surface.** Each surface has its own way of getting page signals. The Chrome content script extracts from DOM. Mobile gets URL + title from the share intent. Web app fetches and parses server-side. All produce the same `PageSignals` shape.

4. **Overlay UI is per-surface.** The Svelte overlay works for Chrome. Mobile needs native UI. Web app needs an embedded component. But the data contract (CivicLensMatch[]) is the same.

5. **Actions route through the same APIs.** Voice, comment, and calendar actions use the same `@civicos/client` SDK regardless of surface. The signing flow differs (extension uses service worker, mobile uses secure enclave, web app uses passkey) but the API calls are identical.

## Open Questions

1. **Content script loading strategy:** Inject on all URLs with early exit, or dynamically register only on enabled domains? The latter is cleaner but requires `scripting` permission.

2. **Overlay positioning:** Fixed bottom-right works for most sites but may conflict with chat widgets, cookie banners, or floating action buttons. Should we detect collisions and reposition?

3. **Multi-jurisdiction matching:** If the user is connected to both San Rafael and Marin County MCPs, should Civic Lens match against both simultaneously? (Likely yes — the pulse cache already includes parent jurisdiction data.)

4. **Mobile surface priority:** The share sheet model (user shares URL -> see civic actions) is a natural mobile fit. Should mobile be Phase E or should it track in parallel once the matcher is proven on desktop?

5. **Selected text matching:** Should the user be able to select text on a page and right-click -> "Find civic actions for this"? This is a natural interaction but requires the `contextMenus` permission.

6. **Keyboard shortcut:** Should there be a shortcut (e.g., Alt+C) to manually trigger Civic Lens matching on the current page, bypassing the domain permission check for one-time use?

7. **Journal sync across surfaces:** chrome.storage.sync covers Chrome-to-Chrome. For cross-platform (extension -> mobile -> web), do we introduce relay-based encrypted journal sync from the start, or defer until a second surface ships?

8. **Server-side signal extraction:** The web app and mobile share sheet may need server-side page fetching (the user provides a URL, not DOM content). Should this be a Jurisdiction MCP tool (`extract_page_signals(url)`) or a separate lightweight service? Privacy implications differ — the server sees the URL.
