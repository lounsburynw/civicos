# Module 2: Nostr and the Relay

*How the Nostr protocol works, why CivicOS builds on it, and what a relay actually does.*

*Prerequisite: Module 1 (Cryptographic Foundations) — you should understand key pairs, signatures, and hashing.*

---

## Why Not Just Build a Normal App?

Before diving into Nostr, let's understand why CivicOS doesn't just use a traditional database with user accounts.

### The Platform Trap

Every civic engagement platform before CivicOS followed the same pattern:

```
Resident → creates account on Platform X → participates → Platform X controls everything
```

This creates three fatal problems for civic infrastructure:

**1. Platform dependency.** If the platform goes bankrupt, gets acquired, or changes direction, all civic participation data disappears. This has happened repeatedly — EveryBlock (shut down 2013), Neighborland (pivoted), SeeClickFix (acquired, changed focus).

**2. Vendor lock-in.** Your civic history, your connections, your voice — all locked inside one company's database. You can't take it with you. You can't verify it independently.

**3. Incentive misalignment.** Platforms optimize for engagement (time on site, clicks, outrage) because that's how they make money. Civic coordination requires the opposite: informed, deliberate participation. Nextdoor makes money when neighbors argue. CivicOS has no engagement metrics at all.

### The Protocol Alternative

Instead of a platform, CivicOS uses a **protocol** — a shared set of rules that anyone can implement.

```
Analogy: Platform vs. Protocol

Email (protocol):
  You can use Gmail, Outlook, Proton, or run your own server.
  You can switch providers and keep your address.
  No single company controls email.

Facebook Messenger (platform):
  You can only use Facebook's app.
  You can't take your messages to another service.
  Facebook controls everything.

CivicOS uses Nostr (protocol):
  You can use any Nostr client.
  You can connect to any relay.
  No single entity controls civic participation.
```

Nostr is the specific protocol CivicOS builds on.

---

## What Is Nostr?

Nostr stands for **Notes and Other Stuff Transmitted by Relays**. It's a decentralized protocol for publishing signed messages, originally designed for social networking but general enough for any application.

### The Core Idea

Nostr has just three concepts:

1. **Events** — signed JSON messages (the only data type in Nostr)
2. **Relays** — servers that store and forward events
3. **Clients** — apps that create, sign, and read events

That's it. The entire protocol fits on a few pages. This simplicity is intentional — complex protocols are hard to implement correctly and create barriers to adoption.

### An Event

Every piece of data in Nostr is an "event." An event is a JSON object with a fixed structure:

```json
{
  "id": "hash of all fields below",
  "pubkey": "author's public key (64 hex chars)",
  "created_at": 1738464000,
  "kind": 1,
  "tags": [
    ["p", "someone's pubkey"],
    ["t", "topic"]
  ],
  "content": "Hello, Nostr!",
  "sig": "Schnorr signature (128 hex chars)"
}
```

Let's break this down:

| Field | What It Is | Analogy |
|-------|-----------|---------|
| `id` | Hash of the event contents | Fingerprint |
| `pubkey` | Who created this event | Return address on a letter |
| `created_at` | When it was created (Unix timestamp) | Postmark |
| `kind` | What type of event this is | "Letter" vs. "Postcard" vs. "Package" |
| `tags` | Structured metadata | Labels on the envelope |
| `content` | The actual message | What's inside the envelope |
| `sig` | Cryptographic signature | Wax seal proving it's from the sender |

**The `id` is computed, not assigned.** It's a SHA-256 hash of `[0, pubkey, created_at, kind, tags, content]`. This means:
- No central authority assigns IDs (no auto-increment, no UUID server)
- The ID is deterministic — the same event always produces the same ID
- Tampering with any field changes the ID, breaking the signature

### Event Kinds

The `kind` field tells relays and clients what type of event this is. Think of it like file extensions — `.jpg` tells your computer "this is an image," and `kind: 1` tells a Nostr client "this is a text note."

**Standard Nostr kinds:**

| Kind | What | Example |
|------|------|---------|
| 0 | User metadata (profile) | Display name, bio, avatar |
| 1 | Text note (like a tweet) | "Hello, Nostr!" |
| 3 | Contact list | Who you follow |
| 4 | Encrypted DM | Private message |

**CivicOS civic kinds (custom, in the 30000+ range):**

| Kind | What | Example |
|------|------|---------|
| 30800 | Civic Voice | "I support the bike lane proposal" |
| 30801 | Civic Entity | The bike lane proposal itself |
| 30802 | Civic Subscription | "Notify me about housing topics" |
| 30850 | Civic Attestation | "This person attended a community event" |
| 30810 | Civic Action | "Write a letter to the council by Feb 14" |
| 30811 | Civic Commitment | "I committed to writing that letter" |
| 30812 | Civic Completion | "I wrote and sent the letter" |

### Event Categories

Nostr events fall into three categories based on their kind number:

```
Regular events (kinds 1-9999):
  Every event is stored. Duplicates rejected by ID.
  Like email: each message is a separate thing.

  Example: Kind 1800 (Civic Vouch) — "I vouch for this person"
  You can vouch for someone multiple times. Each vouch is stored.

Replaceable events (kinds 10000-19999):
  One per kind per pubkey. Newer replaces older.
  Like a profile: you update it, not create a new one.

  Example: Kind 10800 (Civic Provenance) — your reputation record.
  When your voice count changes, the old provenance is replaced.

Addressable events (kinds 30000-39999):
  One per kind per pubkey per "d-tag". Newer replaces older.
  Like a wiki page: identified by a name, editable.

  Example: Kind 30800 (Civic Voice) — your stance on entity X.
  d-tag = "decision:city-san-rafael:2026-02-03:item-6a"
  If you change your stance, the old voice is replaced.
```

**Why this matters for civic coordination:**

Voices are addressable (kind 30800) because you should only have one stance on an entity at a time. If you change your mind from "support" to "oppose," the new voice replaces the old one — there's no ambiguity.

Attestations are also addressable (kind 30850) because you should only have one attestation per jurisdiction. The d-tag `attest:city-san-rafael:{your_pubkey}` ensures one attestation per person per city.

### Tags

Tags are how events reference other events, topics, and metadata. They're arrays of strings:

```json
"tags": [
  ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
  ["j", "city-san-rafael"],
  ["stance", "support"],
  ["t", "housing"],
  ["p", "someone_elses_pubkey"]
]
```

| Tag | Convention | CivicOS Meaning |
|-----|-----------|-----------------|
| `d` | Addressable identifier | Entity being voiced on |
| `p` | Referenced pubkey | Person being attested / mentioned |
| `t` | Topic | Housing, transportation, etc. |
| `j` | (CivicOS custom) | Jurisdiction: city-san-rafael, marin-county |
| `a` | Referenced addressable event | Parent entity for actions |

Tags are the primary way to query for events. When you ask "what are the voices on this agenda item?", you're filtering by the `d` tag.

---

## What Is a Relay?

A relay is a server that:

1. **Receives** signed events from clients
2. **Stores** them
3. **Serves** them to clients that request matching events

That's it. A relay is a dumb pipe — it doesn't filter, rank, recommend, or manipulate. It stores and serves.

### Analogy: Post Office vs. Social Media

```
Social media (Facebook, Nextdoor):
  You post a message.
  The PLATFORM decides who sees it.
  The PLATFORM decides the order.
  The PLATFORM decides if it's shown at all.
  The platform optimizes for engagement.

Relay (Nostr):
  You publish a signed event.
  The RELAY stores it.
  CLIENTS decide what to request.
  CLIENTS decide the order and filtering.
  The relay has no opinion on content.
```

A relay is more like a bulletin board than a newspaper. Anyone can pin something up. Anyone can come read. The bulletin board doesn't editorialized or curate.

### Analogy: Library Shelf

A relay is a library shelf:
- Authors (clients) place books (events) on the shelf
- Readers (other clients) browse the shelf by category (tags/kinds)
- The shelf doesn't decide which books are "good" — it just holds them
- Anyone can run a library (relay), and authors can place books on multiple shelves

### How Clients Talk to Relays

Relays use WebSocket connections (persistent, bidirectional):

```
Client → Relay:

  Publish an event:
    ["EVENT", { kind: 30800, pubkey: "...", ... }]

  Subscribe to events matching a filter:
    ["REQ", "subscription-id", { kinds: [30800], "#j": ["city-san-rafael"] }]

  Stop a subscription:
    ["CLOSE", "subscription-id"]


Relay → Client:

  Here's an event matching your subscription:
    ["EVENT", "subscription-id", { kind: 30800, ... }]

  End of stored events (now streaming new ones):
    ["EOSE", "subscription-id"]

  Acknowledgment:
    ["OK", "event-id", true, ""]
```

**Three messages from clients. Three messages from relays.** That's the entire protocol.

### What Makes This Powerful

**No accounts.** Clients don't "log in" to relays. They just connect and publish signed events. The relay verifies the signature. There's no session, no cookie, no token.

**Multiple relays.** A client can connect to many relays simultaneously. If one goes down, others still work. If you don't trust one relay operator, use a different one.

**Relay independence.** Each relay can set its own policies: what kinds of events to accept, storage limits, access controls. But all relays speak the same protocol, so clients work with any of them.

---

## How CivicOS Uses Nostr

### The CivicOS Relay

CivicOS runs a relay that speaks standard Nostr protocol with civic-specific extensions. The relay:

- Accepts standard NIP-01 WebSocket connections
- Stores civic events (voices, entities, subscriptions, attestations)
- Maintains voice count aggregations per entity
- Verifies attestation proofs on voice/comment submission
- Exposes REST API endpoints for simpler client integration

```
                    CivicOS Relay
                    ┌──────────────────────────────┐
                    │                              │
   Browser          │  Event Storage               │
   Extension ──────►│  (PostgreSQL)                │
   (WebSocket)      │    voices, entities,         │
                    │    attestations, actions      │
                    │                              │
   REST API ───────►│  Verification                │
   (HTTP)           │    signature check           │
                    │    attestation proof check   │
                    │    deduplication              │
                    │                              │
   Other Nostr      │  Aggregation                 │
   Clients ────────►│    voice counts per entity   │
   (WebSocket)      │    attested vs total         │
                    │                              │
                    └──────────────────────────────┘
```

### Civic Voices as Nostr Events

When you voice "support" on an agenda item, the browser extension creates this Nostr event:

```json
{
  "kind": 30800,
  "pubkey": "your_public_key",
  "created_at": 1738464000,
  "tags": [
    ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
    ["j", "city-san-rafael"],
    ["stance", "support"],
    ["t", "housing"]
  ],
  "content": "",
  "sig": "your_schnorr_signature"
}
```

This event, along with your attestation proof, is sent to the relay. The relay verifies everything and stores it.

**Why kind 30800 (addressable)?** Because the d-tag identifies the specific civic entity. The "addressable" property means if you later change your stance, the new event replaces the old one. One voice per person per entity.

### Entity Namespaces

CivicOS entities have structured identifiers:

```
Government-originated (signed by jurisdiction key):
  decision:city-san-rafael:2026-02-03:item-6a
  agenda:2026-02-03:city-council
  meeting:city-san-rafael:2026-02-03

Community-originated (signed by creator's key):
  initiative:san-rafael:bike-lane-4th-st
  initiative:marin-county:transit-expansion
```

Both types receive voices. The entity's namespace makes its origin clear — you can tell whether something was created by the city government or by a community member.

---

## Federation: Multiple Relays

### Why Multiple Relays?

A single relay is a single point of failure and control. CivicOS is designed to work across multiple relays.

```
Single relay (fragile):
  If the relay goes down → all civic coordination stops
  If the operator is compromised → voice counts can be manipulated
  If the operator censors → voices can be suppressed

Multiple relays (resilient):
  If one relay goes down → others continue
  If one is compromised → others provide correct counts
  If one censors → voices are on other relays too
```

### How Federation Works

Relays that host the same entities can peer with each other — synchronizing voice records across relays.

```
Relay A                          Relay B
(run by CivicOS)                 (run by local newspaper)
┌────────────────┐               ┌────────────────┐
│ bike-lane:     │               │ bike-lane:     │
│   12 support   │◄─── sync ───►│   12 support   │
│   3 oppose     │               │   3 oppose     │
│                │               │                │
│ housing-plan:  │               │                │
│   8 support    │               │                │
└────────────────┘               └────────────────┘

User casts voice on Relay A:
  → Relay A stores it, sends to Relay B
  → Relay B verifies the signature, stores it
  → Both relays now show the same count
```

**Voices are self-verifying** (from Module 1). When Relay B receives a voice from Relay A, it doesn't have to trust Relay A. It independently verifies the Schnorr signature and attestation proof. If anything is wrong, it rejects the voice.

### Jurisdictional Relays

Each jurisdiction can run its own relay:

```
San Rafael relay    → hosts city-san-rafael entities
Marin County relay  → hosts marin-county entities
California relay    → hosts california entities
Federal relay       → hosts us-federal entities
```

Your agent (we'll cover this in Module 3) subscribes to whichever relays match your civic life. The agent handles the complexity — you just see your local civic landscape.

### Cross-Jurisdiction Coordination

A single civic issue often spans multiple levels of government:

```
Issue: Affordable housing in San Rafael

Federal level:  CDBG funding (Community Development Block Grants)
State level:    SB 1234 (density bonus law)
County level:   Marin housing allocation plan
City level:     4th Street rezoning proposal

Each level has its own relay, its own entities, its own voices.
An agent subscribed to all four relays can connect the dots:

  "Monday's rezoning implements the state density bonus law.
   The affordable units depend on CDBG funding, which Congress
   is debating cutting. These three things are connected."
```

No single relay can produce that synthesis. It requires reasoning across multiple relays — which is what the agent layer does (Module 3).

---

## The Relay as Infrastructure

### What the Relay Stores

| Data | Purpose | Visible To |
|------|---------|-----------|
| Voice records | Who supports/opposes what | Everyone (public) |
| Entity metadata | What's being decided | Everyone (public) |
| Voice counts | How many people care | Everyone (public) |
| Attestation proofs | Who is attested | Everyone (embedded on voices) |
| Subscriptions | Who wants notifications | Only the subscriber |

### What the Relay Does NOT Store

| Data | Where It Lives |
|------|---------------|
| User profiles | Nowhere (keys are identities) |
| Browsing history | Nowhere (no tracking) |
| Private keys | User's device only |
| Engagement metrics | Nowhere (no metrics) |
| Rankings or scores | Nowhere (no algorithm) |

### Analogy: The Relay as Public Square

```
Traditional platform = Shopping mall
  - Owned by a corporation
  - They control who enters
  - They track where you go
  - They optimize the layout to make you buy things
  - They can kick you out

CivicOS relay = Public square
  - Open to anyone
  - Nobody tracks who comes and goes
  - Bulletin boards show what people care about
  - You can stand up and be counted (voice)
  - Nobody can revoke your presence

The square doesn't have an algorithm. It doesn't send you push
notifications optimized for engagement. It just... exists. And
anyone can build another square next door.
```

---

## The Browser Extension as Client

In the CivicOS system, the browser extension is a Nostr client. It:

1. **Generates and stores** your key pair (private key in localStorage)
2. **Signs events** when you voice or comment (using your private key)
3. **Reads events** from the relay (voices, entities, counts)
4. **Stores your attestation** proof locally
5. **Embeds the proof** on every voice/comment before sending

```
Browser Extension (Client)              CivicOS Relay
┌─────────────────────────┐             ┌─────────────────┐
│                         │             │                 │
│  Private key (secret)   │             │                 │
│  Public key             │             │  Stores events  │
│  Attestation proof      │             │  Verifies sigs  │
│                         │             │  Counts voices  │
│  When you tap "Support":│    HTTP/WS  │                 │
│  1. Build event         │────────────►│  1. Check sig   │
│  2. Attach attest proof │             │  2. Check proof │
│  3. Sign with priv key  │             │  3. Store       │
│  4. Send to relay       │             │  4. Update count│
│                         │             │                 │
│  Display:               │◄────────────│  Return counts  │
│  "23 support, 5 oppose" │             │  & voice list   │
│                         │             │                 │
└─────────────────────────┘             └─────────────────┘
```

The extension also works as a standard NIP-07 signer — meaning other Nostr clients can ask it to sign events. This is how you could use a general Nostr client (like Damus or Primal) to interact with civic entities, though the CivicOS extension provides a much better civic-specific UX.

---

## Recap: The Full Picture So Far

```
Module 1: Cryptographic Foundations
  → Keys give you a self-sovereign identity
  → Signatures prove messages are yours
  → Hashes create tamper-proof event IDs

Module 2: Nostr and the Relay
  → Events are signed JSON messages
  → Relays store and serve events (dumb pipes)
  → Clients create, sign, and read events
  → CivicOS extends Nostr with civic event kinds
  → Federation enables resilience and pluralism
  → The browser extension is a Nostr client

Still missing:
  → How do we know a voice is from a REAL PERSON? (Module 3)
  → How does the system prevent spam from autonomous agents? (Module 3)
  → How does the agent layer provide intelligent filtering? (Module 3)
  → Why did we choose this architecture over alternatives? (Module 3)
```

Module 3 brings everything together: attestation (the gate that proves you're real), edge intelligence (the agent that makes civic data useful), and the design decisions that led to this architecture.
