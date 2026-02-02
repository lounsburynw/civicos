# Coordination Protocol

Infrastructure for permissionless civic coordination. Defines how residents discover shared interests, express civic voice, and receive timely, relevant notifications — without centralized platforms controlling the experience.

**Status:** MVP Implementation (pilot phase)
**Package:** `packages/civicos-relay/` — federation-ready relay with voice, sync, provenance
**Enables:** Coordination and Focal Points stages of engagement ladder (see `CIVIC_DASHBOARD_VISION.md`)
**Distributed via:** CivicOS MCP server (see `MCP_INTEGRATION_STRATEGY.md`)

---

## Core Thesis

Civic coordination fails today because it requires either centralized platforms (Nextdoor, Citizen) that optimize for engagement over civic value, or informal networks (email chains, word of mouth) that don't scale. A protocol-level approach enables coordination without platform lock-in, surveillance, or algorithmic manipulation.

The protocol has three components:

1. **Relay** — routes civic events to subscribers (no filtering, no ranking)
2. **Voice** — public expression of civic interest with transparent provenance
3. **Edge Intelligence** — user-controlled LLM agents that filter and contextualize events using CivicOS MCP

Together, these replace the centralized recommendation engine with an open system where intelligence lives at the edges, controlled by users.

---

## Architecture Overview

```
City Activity (agendas, decisions, initiatives, issues)
    ↓
CivicOS Backend (extracts, structures, stores)
    ↓
Relay (public event feed — routes, doesn't filter)
    ↓
User's Agent (subscribes to relay, receives events)
    ↓
CivicOS MCP (agent queries for civic context — enrichment)
    ↓
Edge Filtering (agent reasons about relevance using local user context)
    ↓
Notification (however the user wants — email, ntfy, SMS, in-app)
```

**No single party has the full picture:**

| Actor | Knows | Doesn't Know |
|-------|-------|--------------|
| CivicOS Backend | City activity, public data | Who subscribes to what |
| Relay | Subscription filters, voice counts | Why a user cares, user identity |
| User's Agent | User preferences, private context | Other users' preferences |
| City | Who attested at civic center (if applicable) | What they voiced on |

---

## Component 1: Relay

The relay routes civic events to subscribers. It is a message broker, not a platform. It does not filter, rank, suppress, or prioritize. It delivers events matching subscription criteria and maintains voice counts.

Analogy: an SMTP server. It routes mail. It doesn't decide what's important. Intelligence lives at the edges (your email client, your filters, your agent).

### Event Types

Events map to existing CivicOS primitives:

| Event | Trigger | CivicOS Origin |
|-------|---------|----------------|
| `agenda_published` | New agenda available | `whats_next()` |
| `decision_made` | Council votes on item | `what_happened()` |
| `initiative_created` | Someone starts a new initiative | `start_something()` |
| `voice_added` | Someone voices on an initiative | `add_voice()` |
| `threshold_reached` | Voice count crosses subscriber-defined threshold | `whos_with_me()` |
| `public_comment_opened` | Comment period begins | `prepare()` |
| `public_comment_closing` | Comment period ending soon | `prepare()` |
| `meeting_scheduled` | New meeting on calendar | `whats_next()` |

### Event Payload

```json
{
  "event": {
    "type": "agenda_published",
    "jurisdiction": "city-san-rafael",
    "entity": "meeting:2026-02-03:city-council",
    "timestamp": "2026-01-28T09:00:00Z",
    "data": {
      "title": "City Council Regular Meeting",
      "date": "2026-02-03",
      "items": [
        {
          "id": "agenda:2026-02-03:item-6a",
          "title": "4th Street Corridor Rezoning Proposal",
          "topics": ["housing", "zoning", "transportation"]
        }
      ]
    }
  }
}
```

### What the Relay Stores

- Active subscriptions (filter criteria + delivery endpoint)
- Voice records per entity (public, auditable)
- Key provenance (creation date, voice history, attestations)

### What the Relay Does NOT Store

- User profiles or demographics
- Browsing/query history
- Engagement metrics (opens, clicks, time spent)
- Relevance scores or rankings

---

## Component 2: Subscriptions

Subscriptions define what events a user (or their agent) wants to receive. They are declarative (what you want, not how to get it), composable, and transport-agnostic.

### Subscription Schema

```json
{
  "subscription": {
    "id": "sub_a1b2c3",
    "jurisdiction": "city-san-rafael",

    "match": {
      "topics": ["housing", "transportation"],
      "geography": {
        "near": {"lat": 37.9735, "lng": -122.5311},
        "radius_miles": 0.5
      },
      "entities": [
        "initiative:bike-lane-4th-st",
        "official:kate-colin"
      ],
      "events": [
        "agenda_published",
        "decision_made",
        "threshold_reached"
      ],
      "threshold": {
        "voices": 10,
        "direction": "gte"
      }
    },

    "deliver_to": {
      "method": "webhook",
      "endpoint": "https://..."
    }
  }
}
```

### Match Semantics

- **Within a field:** OR (topics `["housing", "transportation"]` matches either)
- **Across fields:** AND (matching topic AND within geography)
- **Omitted fields:** match everything (no topic filter = all topics)

This keeps relay-side evaluation cheap: exact string matching on topics/events/entities, basic geo math on geography, integer comparison on thresholds. The relay doesn't do semantic matching — that's the agent's job.

### Delivery Methods

```json
{"method": "webhook",  "endpoint": "https://..."}
{"method": "sse",      "channel": "..."}
{"method": "ntfy",     "topic": "..."}
{"method": "email",    "address": "..."}
{"method": "mcp",      "server": "..."}
```

The `mcp` method is the future path — server-initiated notifications delivered directly into an AI client session when MCP supports bidirectional messaging.

### Subscriber-Defined Thresholds

The relay doesn't decide what "enough" means. Each subscriber sets their own:

- A neighborhood organizer might want notification at 5 voices
- A council member might care at 50
- A journalist at 100

Different subscribers, different thresholds, same entity. The relay evaluates each independently.

---

## Component 3: Voice

A voice is a public expression of civic interest. It is the coordination primitive — the mechanism by which residents discover shared concerns without a platform orchestrating the discovery.

### Voice vs. Subscription

| | Subscription | Voice |
|---|---|---|
| **Visibility** | Private (only you and relay) | Public (anyone can see) |
| **Purpose** | "Notify me about this" | "I stand behind this" |
| **Sybil resistance** | Not needed | Needed |
| **Counts toward thresholds** | No | Yes |

This mirrors civic life: watching a council meeting is private. Standing up to speak is public.

### Voice Structure

```json
{
  "voice": {
    "entity": "initiative:bike-lane-4th-st",
    "stance": "support",
    "key": "did:key:z6Mkf5r...",
    "timestamp": "2026-01-27T14:30:00Z",
    "signature": "..."
  }
}
```

A voice is signed by the user's keypair. One key, one voice per entity. Voices are immutable once cast (but can be revoked by the same key).

### Provenance-Based Trust

Instead of gatekeeping who can voice, the protocol makes voice quality transparent and lets trust evaluation happen at the edge.

**Key provenance record** (maintained by relay, publicly queryable):

```json
{
  "key": "did:key:z6Mkf5r...",
  "provenance": {
    "created": "2025-08-14",
    "total_voices": 23,
    "initiatives_touched": 12,
    "first_voice": "2025-09-01",
    "jurisdictions": ["city-san-rafael"],
    "vouched_by": ["did:key:z7Nka3...", "did:key:z8Plb9..."],
    "attestations": [
      {
        "issuer": "city-san-rafael",
        "type": "physical",
        "issued": "2026-01-15",
        "expires": "2026-02-15"
      }
    ]
  }
}
```

**Provenance signals:**

| Signal | What It Means | Sybil Cost |
|--------|---------------|------------|
| **Key age** | Key created months/years ago | Time (can't fast-forward) |
| **Voice history** | Diverse engagement across initiatives | Sustained effort per fake identity |
| **Vouching** | Existing voices attest to this key | Social capital |
| **Physical attestation** | Presented key at civic center | Physical presence |
| **Device attestation** | Key bound to hardware device | Device acquisition (~$25-500) |
| **Pattern** | Organic engagement vs. burst creation | Behavioral consistency |

No single signal is definitive. The user's agent weighs them in combination:

```
Agent receives: "Initiative X reached 40 voices"

Agent evaluates provenance:
  28 keys older than 90 days, diverse history    → high quality
  8 keys created this week, no prior voices      → low quality
  4 keys with physical attestation               → high quality
  6 keys with device attestation                 → medium-high quality
  No burst patterns detected                     → organic growth

Agent decides: "This is real momentum, notify user"
```

### Physical Attestation (Optional)

Cities can offer physical attestation as an optional trust signal. This is not required for voicing — it's an additional provenance indicator.

**Flow:**

1. User generates keypair locally (phone, agent)
2. User presents public key at civic center (QR code, NFC, kiosk)
3. City signs the public key: "This key was presented at San Rafael Civic Center, Jan 2026"
4. Attestation stored in provenance, expires monthly
5. City never sees what the key voices on; relay never sees who got attested

**Design requirements:**
- Kiosk must be deliberately amnesiac (sign and forget, no logging)
- Multiple attestation venues (civic center, libraries, community events) to avoid equity barriers
- Attestation is one signal among many, not a gatekeeper

### Device Attestation (Optional)

Device attestation binds a keypair to hardware, making Sybil attacks require additional physical devices rather than just generating more keys.

**Concept:** One attested device → one keypair (or limited keypairs per device)

**Implementation approaches:**

| Approach | Mechanism | Sybil Cost | Platform Dependency |
|----------|-----------|------------|---------------------|
| **Platform attestation** | Apple DeviceCheck, Android Play Integrity | ~$100+ (new phone) | High (Apple/Google) |
| **Passkeys/WebAuthn** | Browser + hardware binding | New device per key | Medium (browser vendors) |
| **Hardware tokens** | YubiKey, Titan Key | ~$25-50 per key | Low (open standards) |
| **Secure enclave** | TPM/SEP limits key generation | Hardware constraint | Medium (device manufacturer) |

**Flow:**

1. User installs app or registers via WebAuthn-enabled browser
2. Device attestation binds keypair to hardware (Secure Enclave, TPM, or platform API)
3. Key stored in tamper-resistant hardware; cannot be exported
4. Attestation record: "This key is bound to device X" (device ID is opaque/hashed)
5. Relay stores attestation type, not device identity

**Provenance record:**

```json
{
  "attestations": [
    {
      "type": "device",
      "platform": "ios",
      "method": "device_check",
      "bound_at": "2025-12-01",
      "device_hash": "a1b2c3..."
    }
  ]
}
```

**Design requirements:**

- Device attestation is optional — keys without it still work, just with lower provenance weight
- Device identity must be opaque (hashed or anonymized) — relay cannot track devices across keys
- Support multiple methods to avoid single-platform gatekeeping
- Shared device handling: libraries and community centers may need "kiosk mode" with limited attestation weight
- Emulator/VM detection where platform APIs support it

**Tradeoffs vs. physical attestation:**

| Dimension | Physical | Device |
|-----------|----------|--------|
| **Accessibility** | Requires travel | Requires modern device |
| **Scalability** | Limited by venue capacity | Unlimited |
| **Renewal** | Monthly (requires return visit) | Continuous (device binding persists) |
| **Privacy** | City sees face, not key usage | Platform sees device, not key usage |
| **Attack surface** | Social engineering at kiosk | Emulators, rooted devices |
| **Equity concerns** | Transportation barriers | Device cost barriers |

**Complementary use:** Physical and device attestation address different attack vectors. Physical attestation proves a human visited a location. Device attestation proves a key is bound to hardware. Neither alone proves unique personhood, but together they increase Sybil cost significantly:

```
Key with both attestations:
  - Someone physically visited San Rafael
  - AND controls a specific hardware device
  - AND that device is not an emulator

Sybil cost: (device cost) × (travel cost) × (time cost)
```

**Status:** Future consideration (post-pilot). Physical attestation is simpler to implement and sufficient for pilot-scale validation. Device attestation becomes valuable at scale where physical venue capacity becomes a bottleneck.

### Entity Namespaces

Two coexisting namespaces distinguish grassroots-originated from government-originated items:

```
initiative:bike-lane-4th-st        ← anyone can create
agenda:2026-02-03:item-6a          ← signed by jurisdiction key
```

Both receive voices. Both trigger thresholds. Provenance makes the origin clear.

---

## Component 4: Edge Intelligence

The user's LLM agent provides intelligent filtering on the client side. This replaces the centralized recommendation engine with user-controlled reasoning.

### Why Edge Filtering Beats Centralized Collaborative Filtering

**Centralized collaborative filtering** (Facebook, Nextdoor, Spotify):
- Optimizes for engagement, not user value (misaligned incentives)
- Statistical correlation: "people who liked X also liked Y"
- Opaque — users can't see or control the algorithm
- Creates filter bubbles, optimizes for outrage in civic contexts
- Platform controls the experience

**Edge LLM filtering:**
- Optimizes for user-defined relevance (aligned incentives)
- Causal reasoning: "this rezoning affects the school your kids attend"
- Transparent — agent can explain every recommendation
- User controls the model, prompt, and filtering logic
- No platform dependency

**The hybrid is stronger than either alone.** The relay provides collaborative signals (voice counts, trending initiatives, threshold events) as public data. The edge agent provides individual causal reasoning using the user's private context. Neither alone achieves what the combination does.

### CivicOS MCP as Knowledge Layer

The edge agent uses CivicOS MCP to enrich relay events with civic context. This is not circular — the MCP server provides public civic knowledge; the agent provides user-specific reasoning.

```
Relay emits:
  "New agenda item: 4th Street Corridor Rezoning"

Agent calls CivicOS MCP:
  search_meeting_history("4th street rezoning")
  find_similar_issues("traffic 4th street")
  get_voting_record("Kate Colin", topic="rezoning")
  search_regulatory_stack("rezoning")

Agent reasons (using local user context):
  "This rezoning is similar to the 2025 proposal that failed 3-2.
   14 open traffic complaints on 4th Street.
   Colin voted against previous proposal.
   State density bonus law may apply.
   User lives on 4th Street and commented on traffic last month.
   → High relevance. Notify."
```

**Role separation:**

| Component | Role | Analogy |
|-----------|------|---------|
| CivicOS MCP | Public civic knowledge | Library |
| User's Agent | Knows user, asks good questions | Librarian |
| Relay | Delivers events | Mail slot |

The library doesn't decide what you should read. The librarian does, using the library's resources and knowledge of your interests.

### User Control Over Intelligence

Users control their filtering in ways impossible with centralized systems:

**Inspect reasoning.** "Why did you show me this?" returns actual reasons, not "the algorithm decided."

**Adjust in natural language.** "Stop showing me parking issues, I don't drive." "Be more aggressive on education topics." "Show me everything about housing, even tangential."

**Choose your model.** Claude, GPT, local model, fine-tuned model. The protocol doesn't care.

**Share filtering strategies.** Because filtering logic is a configuration (prompt + preferences), users can share:

```
"Here's my civic filtering config — optimized for parents
with kids in San Rafael public schools. Surfaces education
budget, school zone traffic, and park safety."
```

This creates a commons of filtering intelligence. Community-maintained lenses for civic activity, not a platform algorithm optimizing for engagement.

---

## Development Sequence

### Phase 1: MVP (Current — Pilot)

Building MVP coordination protocol for Jan 2026 pilot. Combines relay + voice + basic provenance in single phase.

**Package:** `packages/civicos-coordination/`

**MVP Scope:**
- Single relay (no federation)
- Email delivery only (webhook for API clients)
- ECDSA keypairs (not full DID — simpler)
- Basic provenance (key age, voice count — no vouching or attestation)
- Voice counts displayed in frontend and MCP

**What's deferred:**
- Federation between relays
- Physical attestation at civic centers
- Device attestation via WebAuthn/platform APIs
- Vouching system
- SMS/ntfy delivery methods
- DID:key standard (using simpler ECDSA keypairs)

**Implementation items tracked in:** `pilot.json` under `relay` category

### MVP Storage Schema

The relay uses PostgreSQL with the following tables (see `packages/civicos-relay/schema.sql`):

```sql
-- Voices: signed expressions of civic interest
coordination_voices (
    entity VARCHAR(255),           -- "agenda:2026-02-03:item-6a"
    stance VARCHAR(20),            -- support | oppose | watching
    public_key VARCHAR(255),       -- ECDSA public key (hex)
    signature TEXT,                -- Signature of entity+stance
    timestamp TIMESTAMPTZ,
    revoked BOOLEAN,
    UNIQUE (public_key, entity)    -- One voice per key per entity
)

-- Subscriptions: event routing preferences
coordination_subscriptions (
    id VARCHAR(50) PRIMARY KEY,    -- "sub_abc123"
    jurisdiction VARCHAR(100),     -- "city-san-rafael"
    match_criteria JSONB,          -- {topics, event_types, geography}
    delivery_method VARCHAR(20),   -- email | webhook
    delivery_address VARCHAR(255),
    active BOOLEAN,
    public_key VARCHAR(255)        -- Optional link to voice key
)

-- Provenance: trust signals for keys
coordination_provenance (
    public_key VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMPTZ,
    total_voices INTEGER,
    entities_touched INTEGER,
    first_voice_at TIMESTAMPTZ,
    last_voice_at TIMESTAMPTZ,
    jurisdictions JSONB            -- ["city-san-rafael", "marin-county"]
)

-- Events log: audit trail
coordination_events_log (
    event_type VARCHAR(50),        -- agenda_published, decision_made
    jurisdiction VARCHAR(100),
    entity VARCHAR(255),
    timestamp TIMESTAMPTZ,
    data JSONB,
    deliveries_attempted INTEGER,
    deliveries_succeeded INTEGER
)
```

### Relay Database Setup

The relay uses a **separate database** from the main CivicOS backend. This architectural separation enables federation where each municipality runs their own relay with their own database, avoiding data coupling.

**Why separate databases:**
- **Architectural separation:** Relay stores voices/subscriptions/provenance independently
- **Federation pattern:** Each jurisdiction can run their own relay instance
- **No accidental coupling:** CivicOS backend data and relay coordination data stay separate
- **Clear boundaries:** Contributors understand which database handles what

**Setup steps:**

1. **Create a new Supabase project** (or PostgreSQL instance)
   - Go to [supabase.com](https://supabase.com) and create a new project
   - Free tier is sufficient for development and small deployments
   - Name it distinctly (e.g., "civicos-relay-sanrafael")

2. **Get the connection string**
   - In Supabase: Settings → Database → Connection string (URI format)
   - Format: `postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres`

3. **Run the coordination schema**
   ```bash
   # Using psql
   psql $RELAY_DATABASE_URL -f packages/civicos-relay/schema.sql

   # Or via Supabase SQL Editor:
   # Copy contents of packages/civicos-relay/schema.sql and execute
   ```

4. **Configure the environment**
   ```bash
   # In .env (separate from DATABASE_URL which is for CivicOS backend)
   RELAY_DATABASE_URL=postgresql://postgres.xxxxx:password@...
   ```

5. **Verify the setup**
   ```bash
   # Export first (use single quotes to handle special chars in password)
   export RELAY_DATABASE_URL='postgresql://postgres:password@db.xxx.supabase.co:5432/postgres'
   python -m pytest packages/civicos-relay/tests/test_postgres_integration.py -v --override-ini="addopts="
   ```

**For federation deployments:**

When multiple jurisdictions run their own relays:

```
San Rafael relay:
  RELAY_DATABASE_URL=postgresql://...sanrafael-relay...
  Hosts: city-san-rafael entities

Novato relay:
  RELAY_DATABASE_URL=postgresql://...novato-relay...
  Hosts: city-novato entities

Marin County relay:
  RELAY_DATABASE_URL=postgresql://...marin-relay...
  Hosts: marin-county entities
  Peers with: San Rafael, Novato relays for voice deduplication
```

Each relay is completely independent. Peering (voice synchronization across relays) is optional and configured separately.

**Troubleshooting:**

| Issue | Cause | Fix |
|-------|-------|-----|
| Tests skip with "RELAY_DATABASE_URL not set" | Variable set but not exported | Use `export RELAY_DATABASE_URL='...'` (child processes need exported vars) |
| Password with `!` breaks URL | Bash history expansion | Use single quotes: `export VAR='postgres://...p!ass...'` or escape: `\!` |
| `.env` variable expansion fails | `${VAR}` syntax unreliable | Set full URL directly, don't reference other vars |
| `psql` not installed | macOS doesn't include psql | Use Supabase SQL Editor instead (paste schema.sql contents) |
| JSON decode errors in tests | psycopg2 version differences | Fixed in code - `_parse_jsonb()` handles both string and dict |

### Compute Layer (Modal)

The relay is more than a database — it needs compute for event routing, delivery, and AI enhancement. This section clarifies what runs where.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE LAYER                                   │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │ Main Supabase   │     │ Relay Supabase  │     │ Cloudflare R2   │       │
│  │ (civic data)    │     │ (coordination)  │     │ (blobs/audio)   │       │
│  └────────┬────────┘     └────────┬────────┘     └─────────────────┘       │
└───────────┼────────────────────────┼────────────────────────────────────────┘
            │                        │
            │  Triggers/webhooks     │
            ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          COMPUTE LAYER (Modal)                               │
│                                                                              │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │ Relay Worker    │     │ MCP Server      │     │ Vector Indexer  │       │
│  │ (event routing) │     │ (AI queries)    │     │ (embeddings)    │       │
│  │                 │     │                 │     │                 │       │
│  │ • Emit events   │     │ • Claude.ai     │     │ • GPU for embed │       │
│  │ • Match subs    │     │ • ChatGPT       │     │ • Batch process │       │
│  │ • AI summarize  │     │ • Tool serving  │     │                 │       │
│  │ • Deliver       │     │                 │     │                 │       │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘       │
│           │                       │                                         │
│           ▼                       ▼                                         │
│  ┌─────────────────────────────────────────┐                               │
│  │           Claude API (AI calls)          │                               │
│  │  • Summarization for notifications       │                               │
│  │  • Semantic subscription matching        │                               │
│  └─────────────────────────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────┘
            │                       │
            ▼                       ▼
┌───────────────────────┐  ┌───────────────────────┐
│ Delivery              │  │ AI Clients            │
│ • Resend (email)      │  │ • Claude.ai           │
│ • Webhooks            │  │ • ChatGPT             │
└───────────────────────┘  └───────────────────────┘
```

**Why Modal:**
- Already used for vector indexing (GPU access)
- Serverless, pay-per-use (~$2-5/month for pilot volume)
- Supports cron triggers and web endpoints
- Python-native (same codebase)

**What runs where:**

| Component | Platform | Trigger | Purpose |
|-----------|----------|---------|---------|
| **MCP Server** | Modal | HTTP endpoint | Serve AI queries (`civicos--civicos-mcp-mcp-endpoint.modal.run`) |
| **Relay Worker** | Modal | Cron (every 5 min) | Emit events, match subscriptions, deliver |
| **Vector Indexer** | Modal | On-demand | Generate embeddings (GPU-accelerated) |

All serverless compute consolidated on Modal for simplified operations.

**Relay Worker implementation:**

```python
# packages/civicos-relay/modal_worker.py (conceptual)
import modal

app = modal.App("civicos-relay")

@app.function(schedule=modal.Cron("*/5 * * * *"))
async def relay_tick():
    """Check for civic events and route to subscribers."""

    # 1. Query for unprocessed events (new decisions, agendas)
    new_events = check_for_new_civic_events()

    # 2. For each event, match against subscriptions
    for event in new_events:
        matches = match_subscriptions(event)

        # 3. Optional: AI enhancement
        if matches and should_summarize(event):
            summary = await claude_summarize(event)

        # 4. Deliver to matching subscribers
        for sub in matches:
            await deliver(event, sub, summary)

        # 5. Log delivery
        log_event_delivery(event, len(matches))
```

**API endpoints (Session 535):**

REST API endpoints for relay operations are now available in `civicos-services`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/coordination/voice` | POST | Cast a signed voice |
| `/api/coordination/voice/counts/{entity}` | GET | Get voice counts |
| `/api/coordination/voice/{entity}` | GET | List voices for entity |
| `/api/coordination/subscribe` | POST | Create subscription |
| `/api/coordination/subscribe/{id}` | DELETE | Deactivate subscription |
| `/api/coordination/provenance/{key}` | GET | Get key provenance |

**Implementation sequence:**

1. **Phase 1 (Complete):** Storage + API
   - PostgreSQL storage classes ✓
   - REST API endpoints ✓
   - Frontend can display voice counts ✓

2. **Phase 2 (Complete):** MCP Server on Modal
   - Deploy `civicos-mcp` to Modal as web endpoint ✓
   - Connect to Claude.ai and ChatGPT ✓
   - Full parity with Fly.io (25+ tools) ✓
   - Input validation and federation support ✓

3. **Phase 3 (Next):** Relay Worker on Modal
   - Event emission from civic data changes
   - Subscription matching and delivery
   - Resend integration for email

4. **Phase 4:** AI Enhancement
   - Claude API for notification summaries
   - Semantic subscription matching
   - Personalized digests

**Cost estimate (pilot):**

| Component | Provider | Est. Cost/mo |
|-----------|----------|--------------|
| MCP Server | Modal | ~$2-5 |
| Relay Worker | Modal | ~$2-5 |
| Vector Indexer | Modal | ~$5-10 |
| Email delivery | Resend Free | $0 |
| Claude API | Anthropic | ~$5-10 |
| **Total compute** | | **~$15-30/mo** |

This is in addition to storage costs (Supabase: ~$25-50/mo for production, free tier for dev).

### Nostr Protocol Integration

CivicOS extends Nostr (NIP-01) with civic-specific event kinds. This provides maximum ecosystem interoperability — users manage keys via external Nostr clients (Damus, Primal, Amethyst, nos2x) and voice on civic entities through standard Nostr events.

**Why Nostr:**
- **Key management** — Users control keys in existing clients, no CivicOS-specific key infrastructure
- **Ecosystem** — Any Nostr client can connect to CivicOS relays
- **Federation** — Built-in relay federation (NIP-01) replaces custom sync protocol
- **Standards** — secp256k1/Schnorr (BIP-340) is well-tested cryptography

**Civic Event Kinds:**

| Kind | Type | Purpose |
|------|------|---------|
| 30800 | Addressable | Civic Voice (one per pubkey per entity) |
| 30801 | Addressable | Civic Entity (decisions, initiatives, meetings) |
| 30802 | Addressable | Civic Subscription (notification criteria) |
| 10800 | Replaceable | Civic Provenance (self-signed reputation) |
| 1800 | Regular | Civic Vouch (social attestation) |
| 1801 | Regular | Civic Event Notification (relay broadcasts) |
| 1802 | Regular | Key Link Attestation (old key → Nostr migration) |

**WebSocket Endpoint:**

```
wss://relay.civicos.org
```

Standard NIP-01 messages:
- `["EVENT", <event>]` — Publish civic voice or other event
- `["REQ", <sub_id>, {"kinds": [30800], "#j": ["city-san-rafael"]}]` — Subscribe to voices
- `["CLOSE", <sub_id>]` — Unsubscribe

**Key Migration (Old ECDSA → Nostr):**

Existing CivicOS users with SECP256R1 keys can migrate to Nostr while preserving provenance:

1. Generate new Nostr key in preferred client
2. Sign link message with old key: `civicos:link:v1:<new_pubkey>`
3. Publish kind 1802 attestation event with both signatures
4. Relay validates and links keys
5. Provenance transfers to new key

**REST Compatibility:**

Existing REST endpoints continue working with deprecation headers. Clients should migrate to WebSocket by Q2 2026:

| REST Endpoint | Nostr Equivalent |
|--------------|------------------|
| `GET /voice/counts/{entity}` | `["REQ", "counts", {"kinds": [30800], "#d": ["entity"]}]` |
| `GET /voice/{entity}` | `["REQ", "voices", {"kinds": [30800], "#d": ["entity"]}]` |
| `POST /voice` | `["EVENT", <signed CivicVoiceEvent>]` |

See `docs/critical/NOSTR_CIVIC_NIPS.md` for full NIP specification.

### Phase 2: Full Relay (Post-Pilot)

If pilot validates coordination hypothesis, expand relay:

- Multiple delivery methods (ntfy, SMS)
- Event hooks into ingestion pipeline
- Subscription management API
- Rate limiting and abuse prevention

### Phase 3: Full Voice + Provenance (Post-Pilot)

If coordination shows value, expand voice system:

- DID:key migration for standards compliance
- Vouching system (existing keys vouch for new keys)
- Physical attestation infrastructure (optional, city-provided)
- Device attestation via WebAuthn/platform APIs (optional, complements physical)
- Threshold event triggers

### Phase 4: Edge Intelligence (Future)

Agent-side filtering using CivicOS MCP for context enrichment.

- Agent subscribes to relay, receives raw events
- Agent calls CivicOS MCP to enrich with civic context
- Agent applies user preferences to filter and prioritize
- Shareable filtering configurations

**Depends on:** MCP supporting server-initiated messaging (for `deliver_to.method: "mcp"`), or agents polling/using webhook bridges in the interim.

---

## Federation and Hierarchical Government

U.S. governance is hierarchical: federal, state, county, city, special districts. Civic issues routinely span multiple levels — housing involves federal funding (CDBG), state law (density bonus), county planning, and city zoning simultaneously. The protocol must support coordination across these layers without requiring a centralized aggregator.

### Relay Topology

Each jurisdiction operates one or more independent relays. Relays emit events for their jurisdiction's activity. There is no master relay or hierarchical relay chain.

```
Federal relay              emits: congressional votes, federal program changes
State relay (CA)           emits: legislation, regulatory changes
County relay (Marin)       emits: supervisor decisions, county planning
City relay (San Rafael)    emits: council decisions, local initiatives
City relay (San Anselmo)   emits: council decisions, local initiatives
City relay (Novato)        emits: council decisions, local initiatives
```

Relays at different levels do not need to communicate with each other. Cross-level coordination happens at the agent, not the relay.

### Cross-Level Coordination via Edge Intelligence

A user's agent subscribes to relays at whichever levels match their civic life:

```json
{
  "subscriptions": [
    {"relay": "relay.sanrafael.gov",   "match": {"topics": ["housing", "transportation"]}},
    {"relay": "relay.marincounty.org", "match": {"topics": ["housing", "transit"]}},
    {"relay": "relay.ca.gov",          "match": {"topics": ["housing"]}},
    {"relay": "relay.congress.gov",    "match": {"topics": ["CDBG", "housing funding"]}}
  ]
}
```

When events arrive from different levels, the agent uses CivicOS MCP to connect them:

```
Tuesday:   State relay emits "SB 1234 passed — mandatory density bonus"
Thursday:  City relay emits "Agenda item: 4th Street rezoning proposal"
Friday:    Federal relay emits "House committee debates CDBG funding cut"

Agent calls CivicOS MCP:
  search_regulatory_stack("density bonus")
  get_funding_flow(program="CDBG")
  search_meeting_history("rezoning")

Agent synthesizes:
  "Monday's rezoning proposal implements the state density bonus
   law that passed Tuesday. The affordable units in this project
   are funded through CDBG, which Congress is debating cutting 20%.
   These three things are connected and all affect your neighborhood."
```

No single relay can produce that synthesis. It requires reasoning across jurisdictional levels with knowledge of regulatory relationships — exactly what an LLM agent with CivicOS MCP access is good at.

### Entity Jurisdiction Scope

Entities exist at the level of the decision-maker. Voices are cast on entities at the appropriate level.

```
initiative:san-rafael:bike-lane-4th-st       → lives on city relay
initiative:marin-county:transit-expansion     → lives on county relay
initiative:california:sb-1234-housing         → lives on state relay
```

The entity's jurisdiction prefix makes scope unambiguous. A San Rafael resident who cares about a state housing bill voices on the state relay's entity. The agent helps users understand where to voice: "This is a state-level decision. Would you like to voice on the state housing bill?"

For county-level issues, voices aggregate naturally across cities. If residents across San Rafael, San Anselmo, and Novato all voice on `initiative:marin-county:transit-expansion`, the county relay counts all of them — 125 voices total, not three separate city-level counts. No inter-relay coordination needed.

### Multiple Relays Per Jurisdiction

Anyone can run a relay for a jurisdiction. This is a core permissionless property.

**Why multiple relays matter:**

- **Resilience.** No single point of failure. If one relay goes down, others continue.
- **Pluralism.** Different operators bring different perspectives on what entities to host.
- **No single point of control.** No one operator can suppress events or manipulate voice counts.
- **Permissionless operation.** Cities, newspapers, civic organizations, and CivicOS can all run relays.

**Voice portability across relays:**

Voices are self-contained, signed artifacts. They don't belong to a relay — they belong to the entity. Any relay hosting that entity accepts and counts them.

```json
{
  "voice": {
    "entity": "initiative:san-rafael:bike-lane-4th-st",
    "key": "did:key:z6Mkf5r...",
    "stance": "support",
    "signature": "..."
  }
}
```

A user casts a voice on any relay hosting the entity. Relays that host overlapping entities sync voice records and deduplicate by `key + entity` pair. Same key, same entity, counted once regardless of which relay received it.

```
User voices on Relay A  →  Relay A counts, broadcasts to peers
                        →  Relay B receives, deduplicates, counts
                        →  Both relays show same voice count
```

### Relay Federation Protocol

Federation is minimal. Relays that host overlapping entity namespaces peer with each other and exchange voice records. That's it.

**What federates:**
- Voice records (signed, verifiable, deduplicated by key + entity)
- Entity metadata (title, jurisdiction, creator signature)
- Events (agenda published, decision made, threshold reached)

**What does NOT federate:**
- Subscriptions (private to each relay)
- User data (doesn't exist)
- Filtering logic (lives at the edge)

**Peering model:**

Relays declare which entity namespaces they host. Peers discover each other through a lightweight registry or manual configuration.

```
Relay A declares: "I host initiative:san-rafael:*"
Relay B declares: "I host initiative:san-rafael:*, initiative:marin-county:*"

A and B peer on the san-rafael namespace.
Voices cast on either relay propagate to the other.
```

### Thematic Relays

Relay operators can curate scope by topic rather than (or in addition to) jurisdiction. A community organization might run a relay focused on a single issue across multiple levels of government.

```
Housing-focused relay (run by Marin Housing Coalition):
  Hosts: initiative:san-rafael:*, topic=housing
  Hosts: initiative:marin-county:*, topic=housing
  Hosts: initiative:california:*, topic=housing

  → Single subscription gets cross-jurisdictional housing events
  → Voices cast here federate to jurisdiction-specific relays
```

This makes relay operators **curators of civic scope**, not gatekeepers of information. They choose what entities to host and voices flow freely across the network. A user subscribes to the thematic relay for convenience; their voices propagate to all jurisdictional relays hosting those entities.

### Hierarchical Voice Visibility

Voices cast at the city level are visible to city and county relays (when entities federate). This enables upward visibility without requiring users to understand which level of government handles what.

```
Resident voices on initiative:san-rafael:affordable-housing
  → San Rafael relay counts it
  → Marin County relay sees it (if peered on housing entities)
  → County supervisor can see: "45 voices across 3 cities on housing"
```

Downward visibility also works: a state-level entity's voice count is visible to any relay that peers on that namespace. City-level agents can surface state-level momentum to their users.

The hierarchy is emergent from peering relationships, not imposed by protocol structure. A relay can peer upward, downward, or laterally — the protocol doesn't distinguish these directions.

---

## User Experience

Mastodon's federated architecture is powerful in principle but confusing in practice — users choose servers, encounter incomplete search, and must understand federation to make sense of the experience. The coordination protocol avoids this by making the protocol completely invisible. Users interact with civic concepts (issues, meetings, initiatives, voices), never with protocol concepts (relays, keys, federation, provenance).

**Design rule:** The protocol is for developers and operators. The UX is for residents.

### The AI Conversation as Primary Interface

The agent IS the interface. Users don't navigate an app, configure subscriptions, or manage keys. They have a conversation:

```
User:   "What's happening in San Rafael?"

Agent:  Three meetings this week. The big one is Monday —
        City Council is voting on the 4th Street rezoning.
        23 people are watching this item.

User:   "I care about the 4th Street thing. I live nearby."

Agent:  The rezoning would allow mixed-use development on the
        4th Street corridor. 8 people have publicly voiced
        support, 3 oppose. Want me to notify you before
        Monday's meeting and when similar issues come up?

User:   "Yes."

Agent:  Done. I'll notify you before Monday with prep materials.
        Would you like to add your voice on the rezoning?

User:   "I support it."

Agent:  Your support has been recorded. You're one of 9
        supporters. I'll let you know if this picks up
        momentum.
```

What happened behind the scenes:

| User Said | Protocol Action |
|-----------|----------------|
| "What's happening" | Agent queried CivicOS MCP (`get_upcoming_meetings()`) |
| "I care about this" | Agent generated keypair, stored locally |
| "Yes, notify me" | Agent subscribed to city relay (topic + geography filter) |
| "I support it" | Agent signed and cast voice on relay entity |

The user made zero protocol decisions. No relay selection, no key management, no understanding of federation.

### Interaction Surfaces

The protocol supports multiple surfaces. Each hides the same complexity:

```
Three layers, three audiences:

Residents see:
  "23 people care about this. Here's why it matters to you."

Organizers see:
  Voice counts, provenance quality, cross-jurisdiction
  momentum, shareable filtering configs.

Developers see:
  Relay federation, DID keys, voice signatures, peering
  protocol, provenance algorithms, event schemas.
```

Each layer is real and inspectable. Users only go deeper if they choose to.

### Surface 1: AI Chat (Claude.ai, ChatGPT, etc.)

The richest experience. The agent has conversational context, can reason about why events matter to this specific user, and can explain its filtering decisions.

**Available today (Phase 1 — pull-based):**
- CivicOS MCP connected to Claude.ai or any MCP-capable client
- Full civic query capability: meetings, decisions, testimony, budget, regulatory context
- No subscriptions or push — user initiates every interaction

**Future (persistent agents):**
- Agent subscribes to relays on user's behalf
- Agent holds keypair across sessions
- Agent filters events and sends notifications
- Agent casts voices when user approves
- Full protocol participation through conversation

The gap between today and future is persistent agent infrastructure — background processes that maintain state and act on the user's behalf. As AI platforms ship this capability, the full coordination protocol becomes accessible through conversation.

### Surface 2: Web App (civicos.org)

For users who don't use AI chat. Simpler, lower-friction, familiar web patterns:

```
civicos.org/san-rafael

[What neighborhood?]
  → Map pin or zip code

[What do you care about?]
  → ☑ Housing    ☐ Transportation    ☐ Public Safety
  → ☐ Parks      ☑ Schools           ☐ Budget

[How should we reach you?]
  → Email: ___________
  → Phone: ___________ (optional, SMS)

[Done]
  "You'll hear from us when housing or school issues
   come up near your neighborhood."
```

The web app performs the same protocol actions the AI agent would: generates a keypair (stored server-side on behalf of the user), creates relay subscriptions, sets up delivery. Same protocol, different surface.

### Surface 3: Email/SMS Notifications

Push notifications arrive through channels people already use. No app download required.

```
Subject: Monday — City Council votes on 4th Street rezoning

The City Council votes Monday at 7pm on the 4th Street
corridor rezoning proposal. This would allow mixed-use
development near your neighborhood.

23 people are watching this item.
9 support · 3 oppose · 11 watching

[I support this]  [I oppose this]  [Just watching]

── What you should know ──
• Similar proposal failed 3-2 in 2025
• Council member Colin voted against last time
• Public comment is open until Monday 5pm
```

Clicking "I support this" casts a voice. The email contains a signed token linked to the user's keypair (managed by the web app). No login required for the voice action.

The contextual briefing ("what you should know") is generated by the edge intelligence layer — CivicOS MCP provides the civic context, the agent formats it for the notification.

### Why This Avoids Mastodon's Problems

| Mastodon | Coordination Protocol |
|----------|----------------------|
| "Choose a server" | User never sees relays |
| "This user is on another instance" | Voices just appear, federation invisible |
| "Search doesn't work across servers" | Agent queries CivicOS MCP — full search |
| "Moving servers is hard" | Keys are portable, not relay-bound |
| "What's federation?" | User never encounters the concept |
| Mental model: servers and instances | Mental model: my city, my issues, my neighbors |

The protocol is as invisible as HTTPS. You don't choose a certificate authority. You don't think about TLS handshakes. You just visit websites. Similarly, users don't choose relays, manage keys, or understand federation. They ask about their city and express what they care about.

### Progressive Disclosure

Users who want depth can access it:

- **"Why did you show me this?"** — Agent explains its filtering reasoning in plain language
- **"Who supports this?"** — Voice counts with provenance summary (attested vs. unattested)
- **"How confident are you these are real people?"** — Provenance breakdown (key age, history, attestation)
- **"I want to run my own relay"** — Developer docs, relay software, federation protocol

Each question goes one layer deeper. The default experience never requires going deeper than the first layer.

### UX Surface Timeline

| Phase | AI Chat | Web App | Email/SMS |
|-------|---------|---------|-----------|
| **Pilot (now)** | Pull-based queries via MCP | — | — |
| **Relay** | Pull-based + "check for updates" | Subscription signup, topic picker | Event notifications |
| **Voice** | Conversational voicing | Click-to-voice | Voice buttons in notifications |
| **Edge Intelligence** | Full agent: subscribe, filter, voice, notify | Smarter notifications (LLM-contextualized) | Personalized briefings |
| **Persistent Agents** | Always-on coordination partner | Fallback for non-AI users | Delivery channel for all surfaces |

---

## Design Principles

1. **Protocol over platform.** Build infrastructure anyone can use, not an app that locks users in.

2. **Intelligence at the edges.** The relay routes. The agent reasons. Users control the intelligence.

3. **Transparency over gatekeeping.** Don't prevent low-quality voices — make voice quality legible. Trust evaluation happens at the edge.

4. **Permissionless with optional attestation.** Anyone can subscribe and voice from day one. Physical attestation adds signal but isn't required.

5. **Collaborative signals, individual reasoning.** The relay provides what other people are doing (public). The agent provides why it matters to you (private). Neither alone is sufficient.

6. **No engagement optimization.** The relay has no metrics to optimize. It routes events and counts voices. There is no algorithmic feed, no A/B testing on notification timing, no dark patterns. The absence of these is a feature.

---

## Agent Ecosystem

The protocol supports multiple agent types beyond individual residents. Different agents participate differently — residents voice and subscribe, journalists monitor and investigate, organizations coordinate and amplify. The protocol doesn't distinguish agent types at the protocol level; the distinction is behavioral.

### Agent Types

**Resident agents** — the primary participant. Subscribe to local relays, voice on initiatives, receive filtered notifications. Intelligence optimized for personal civic relevance.

**Journalist agents** — accountability monitors. Subscribe across multiple jurisdictions, detect anomalies, cross-reference patterns. They observe but do not voice — journalistic neutrality applies to automated agents as much as to reporters.

```
Journalist agent monitors 20 Bay Area city relays

Detects:
  "initiative:san-rafael:affordable-housing crossed 45 voices
   but 30 appeared in a 2-hour window, all first-time keys,
   no attestations"

Agent calls CivicOS MCP:
  search_meeting_history("affordable housing")
  get_voting_record("all", topic="housing")
  search_agenda_packets("affordable housing developer")

Agent alerts journalist:
  "Possible astroturfing on San Rafael housing initiative.
   30 of 45 voices are suspicious (burst pattern, no history).
   The council votes Monday. Same developer submitted the
   fiscal impact report. Worth investigating."
```

No human journalist can monitor 20 cities for patterns like that. Local journalism is dying because individual reporters can't cover the volume. Agentic journalists covering 20 cities through the protocol are an accountability force multiplier.

**Organization agents** — civic organizations, advocacy groups, neighborhood associations. Subscribe to topic-specific events across jurisdictions, coordinate member voices, amplify community concerns. These agents voice on behalf of the organization (with a distinct organizational key).

**City staff agents** — government-side participants. Monitor voice counts and community sentiment on upcoming agenda items. Surface emerging concerns before they reach the council chamber. Do not voice — government observes community coordination, doesn't participate in it.

### Symbiotic Relationships

Agent types benefit from each other's participation:

- **Journalist agents detecting astroturfing** protect residents whose voices would otherwise be diluted by fake participation.
- **Resident voice counts** give journalists signal about which issues have genuine community energy.
- **Organization agents amplifying concerns** help residents who care about an issue but wouldn't discover it independently.
- **City staff agents monitoring sentiment** create a feedback loop where community coordination visibly reaches decision-makers.

The protocol becomes more valuable as the agent ecosystem diversifies. This is a network effect, but one driven by complementary roles rather than homogeneous users.

---

## Economic Model

The protocol is open and permissionless. Resident civic participation is never paywalled. But relay infrastructure costs money to operate, and sustainability requires a revenue model beyond foundation grants.

### Tiered Access

The protocol is free. The *service* — uptime, speed, multi-jurisdiction coverage, real-time feeds, bulk data — can be priced. This is the Red Hat model: Linux is free, enterprise support costs money.

```
Free (residents):
  Subscribe to events in your jurisdiction
  Voice on entities
  Basic provenance queries
  Email/SMS notifications

Pro (journalists, civic organizations):
  Multi-jurisdiction subscriptions (10+ cities)
  Real-time event feeds (sub-second delivery)
  Bulk provenance queries
  Historical voice data and trend analysis
  Anomaly detection alerts
  API access with higher rate limits

Enterprise (media organizations, civic tech companies):
  Full firehose across all hosted jurisdictions
  Custom federation endpoints
  SLA guarantees
  Bulk data export
  Dedicated support
```

### Why This Doesn't Compromise Permissionless Properties

- **The protocol is open.** Anyone can run their own relay and access everything for free.
- **Resident participation is never gated.** Subscribing, voicing, and receiving notifications are free at every relay.
- **Events, voices, and provenance are public data.** You cannot paywall public civic information.
- **What's priced is service quality.** Uptime, speed, coverage breadth, bulk access, and convenience — not the underlying data or protocol participation.

Analogy: Gmail charges enterprises while SMTP remains an open protocol. Charging for a well-run email service doesn't make email less open.

### Revenue Potential by Agent Type

| Agent Type | What They Pay For | Value Proposition |
|-----------|-------------------|-------------------|
| Journalists | Multi-city monitoring, anomaly detection | Replaces reporter headcount for local coverage |
| Media orgs | Full firehose, bulk export, SLA | Investigative infrastructure at scale |
| Civic orgs | Multi-jurisdiction alerts, member coordination | Issue tracking across government levels |
| Civic tech companies | API access, federation endpoints | Build products on open civic data |
| Government agencies | Sentiment monitoring, cross-jurisdiction visibility | Community engagement intelligence |

### Sustainability Model

```
Phase 1 (pilot):
  Foundation funding → builds protocol, funds initial relays
  Cost: < $7/month per city

Phase 2 (multi-city):
  Foundation funding → expansion to new jurisdictions
  Resident usage → free, proves civic value
  Early journalist/org users → validates commercial tier

Phase 3 (sustainability):
  Commercial tier revenue → sustains relay infrastructure
  Foundation funding → reduced dependency, targeted expansion
  Revenue reinvested → new jurisdictions, protocol development

Phase 4 (ecosystem):
  Multiple relay operators → CivicOS runs reference relay
  Third-party relays → own pricing and service models
  Protocol is infrastructure → CivicOS is one provider among many
```

The goal is not to be the only relay operator. The goal is to prove the protocol, run the reference implementation, and let the ecosystem develop. If other organizations run relays — including free ones — that strengthens the protocol, even if it competes with CivicOS's commercial offering.

### Partnership Model

CivicOS provides the coordination protocol (relay, voice, edge intelligence). Civic data backends provide structured government data at scale. This separation enables faster geographic expansion:

```
CivicOS alone:
  Protocol + data integration per city
  Scaling bottleneck: 6 months of data work per jurisdiction

CivicOS + data partner:
  CivicOS provides: coordination protocol, edge intelligence, MCP server
  Partner provides: structured civic data across jurisdictions
  Scaling bottleneck: removed
```

The protocol is the novel contribution. Civic data extraction is valuable but not unique to CivicOS. Partnerships that leverage existing data infrastructure let CivicOS focus on the coordination layer — the piece nobody else is building.

---

## Open Questions

- **Voice revocation.** Can you un-voice? If so, does the threshold event un-fire? Recommend: revocation allowed, thresholds only fire upward (no "un-threshold" event).

- **Initiative governance.** Anyone can create initiatives. How do you handle spam, duplicate, or misleading initiatives? Provenance helps (low-provenance creator = less credible initiative) but may not be sufficient.

- **Agent accessibility.** Who builds and hosts agents for users who don't run Claude Code or ChatGPT? The web app and email surfaces address basic access, but full edge intelligence requires an AI agent. As AI assistants become more common, this gap closes — but it's real today.

- **Peering discovery.** How do relays find each other? Manual configuration works at small scale. A lightweight registry (DNS-based? well-known URI?) may be needed for broader federation.

- **Conflict resolution.** If two relays disagree on voice counts for the same entity (due to sync lag or a misbehaving relay), who is authoritative? Recommend: voices are self-verifying (signed), so any relay can independently validate. Disagreements resolve through re-verification, not authority.

- **Special districts.** School districts, water districts, transit authorities don't fit the city/county/state hierarchy cleanly. How do their entities and relays integrate? Likely: they operate relays like any other jurisdiction and peer with relevant geographic relays.

- **Commercial agent ethics.** Should lobbyist or corporate agents be allowed to voice? They can subscribe (public data), but voicing implies civic standing. Provenance transparency helps — a corporate key is identifiable — but the protocol may need norms or guidance on commercial participation beyond transparency.

- **Sybil resistance at scale.** The protocol chooses "transparency over gatekeeping" — anyone can generate unlimited keys, and provenance signals make voice quality visible rather than preventing low-quality voices. This works when Sybil attacks are unsophisticated (burst patterns, new keys). But a motivated attacker can generate keys months in advance, build fake engagement history, and obtain physical/device attestations for each. At what scale does this become a real threat? Is provenance transparency sufficient, or does the protocol eventually need stronger identity binding? The bet is that local civic issues rarely attract adversarial investment, but state/federal issues or well-funded astroturfing campaigns may require additional defenses.
