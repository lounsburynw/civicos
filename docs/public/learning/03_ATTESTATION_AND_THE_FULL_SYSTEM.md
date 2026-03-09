# Module 3: Attestation and the Full System

*How CivicOS prevents spam, why gated attestation exists, and how all the pieces fit together.*

*Prerequisites: Module 1 (Cryptographic Foundations) and Module 2 (Nostr and the Relay).*

---

## The Spam Problem

You now understand that CivicOS uses cryptographic keys for identity and Nostr events for civic participation. But there's a critical gap:

**Generating a key pair is free and instant.**

Anyone — or any bot — can generate a thousand key pairs in a second. Each key pair looks legitimate. Each can sign valid Nostr events. A single laptop can produce a million "citizens" in an hour.

```
The attack:

1. Generate 10,000 key pairs          (< 1 second)
2. Sign 10,000 "support" voices       (< 1 second)
3. Send to relay                       (< 1 second)

Result: "10,023 residents support this initiative!"
Reality: 23 real people, 10,000 fake keys
```

This is called a **Sybil attack** — named after a book about a person with multiple personalities. One entity pretends to be many.

### Why This Matters More Now Than Ever

In 2020, Sybil attacks required some effort — writing scripts, managing infrastructure. Today, autonomous AI agents can:

- Generate realistic-looking engagement histories over time
- Produce human-sounding comments
- Simulate organic behavior patterns
- Operate at scale for pennies

The cost of faking civic participation has collapsed to near zero. A coordination system whose value depends on genuine human signal must have a credible defense against this.

### The Old Approach: Weighted Provenance

> **Note:** Weighted provenance was evaluated during early design and rejected. CivicOS now uses exclusively gated attestation (described in the next section). This history is included because understanding *why* the simpler approach fails is essential to understanding why the gate exists.

CivicOS initially tried a different approach — let anyone voice, but make voice quality transparent:

```
Old model (weighted):

  Any key can voice.

  Voice quality signals (provenance):
    Key age: 90 days old → probably real
    Voice history: participated in 12 initiatives → probably real
    Physical attestation: showed up at civic center → definitely real
    Device attestation: key bound to hardware → probably real

  The user's agent weighs these signals:
    "40 voices, but 30 are from brand new keys → suspicious"
    "10 voices, all from keys with months of history → real"
```

This is elegant in theory. In practice, it breaks down:

**Problem 1: Agents can simulate history.** An attacker creates keys months in advance, has them participate in a few low-stakes initiatives to build "organic" history, then deploys them for the target vote.

**Problem 2: Complexity burden on users.** "23 voices (18 high-quality, 5 low-quality)" requires every user to understand provenance weighting. Most people just want to know: are these real?

**Problem 3: No hard boundary.** Without a gate, the relay accepts everything. The attack surface is unbounded — you're playing whack-a-mole with increasingly sophisticated fake engagement.

### The New Approach: Gated Attestation

CivicOS now uses a hard gate:

```
New model (gated):

  To voice or comment, you MUST present a valid attestation proof.
  No proof → 403 Forbidden. Forged proof → 400 Bad Request.

  To get attested, you must physically attend a community event
  and receive a single-use code from a volunteer.

  Browsing, reading, subscribing → still open to everyone.
  Voicing, commenting → requires attestation.
```

**Why this works:**

| Attack vector | Cost with weighted model | Cost with gated model |
|---------------|------------------------|----------------------|
| Generate 10,000 fake keys | Free | Irrelevant (no attestation = can't voice) |
| Build fake history over months | Time, but automated | Irrelevant (history doesn't bypass gate) |
| Get 10,000 attestations | N/A (attestation was optional) | 10,000 physical appearances at events |

The gate converts a digital problem (unlimited key generation) into a physical one (you must show up in person). Physical presence scales poorly for attackers — it's expensive, slow, and conspicuous.

---

## How Attestation Works

### The Flow: Getting Attested

```
Step 1: COMMUNITY EVENT
  ┌──────────────────────────────────────────────────┐
  │  Farmer's market, city council meeting,          │
  │  library pop-up, community center...             │
  │                                                  │
  │  Volunteer has a stack of cards:                  │
  │  ┌──────────────────────────────┐                │
  │  │ Your CivicOS Attestation Code│                │
  │  │                              │                │
  │  │  SR-2026-02-A7K9             │                │
  │  │                              │                │
  │  │ Enter in CivicOS Extension   │                │
  │  │ Options > Attestation        │                │
  │  │ This code can only be used   │                │
  │  │ once.                        │                │
  │  └──────────────────────────────┘                │
  │                                                  │
  │  Volunteer gives ONE code per person.            │
  │  No ID check. Human judgment is sufficient.      │
  └──────────────────────────────────────────────────┘

Step 2: REDEEM IN EXTENSION
  ┌──────────────────────────────────────────────────┐
  │  User opens CivicOS extension → Options          │
  │  Enters code: SR-2026-02-A7K9                    │
  │  Clicks "Verify Code"                            │
  │                                                  │
  │  Extension sends to relay:                       │
  │    {                                             │
  │      code: "SR-2026-02-A7K9",                    │
  │      public_key: "user's pubkey",                │
  │      signature: "signed request"                 │
  │    }                                             │
  └──────────────────────────────────────────────────┘

Step 3: RELAY ISSUES ATTESTATION
  ┌──────────────────────────────────────────────────┐
  │  Relay checks:                                   │
  │    ✓ Code exists in database                     │
  │    ✓ Code hasn't been used yet                   │
  │    ✓ Code hasn't expired                         │
  │    ✓ This pubkey isn't already attested           │
  │                                                  │
  │  Relay signs a kind-30850 Nostr event:           │
  │    "This pubkey is attested for city-san-rafael"  │
  │                                                  │
  │  Relay returns the signed event to the extension │
  └──────────────────────────────────────────────────┘

Step 4: STORED LOCALLY
  ┌──────────────────────────────────────────────────┐
  │  Extension stores the attestation event in       │
  │  browser localStorage.                           │
  │                                                  │
  │  From now on, every voice and comment the user   │
  │  submits includes this event as                  │
  │  "attestation_proof".                            │
  │                                                  │
  │  Extension shows: ✓ Attested for San Rafael      │
  └──────────────────────────────────────────────────┘
```

### The Attestation Event (Kind 30850)

The attestation is a Nostr event — the same structure you learned in Module 2, but with a specific purpose:

```json
{
  "kind": 30850,
  "pubkey": "jurisdiction_issuer_pubkey",
  "created_at": 1739520000,
  "tags": [
    ["d", "attest:city-san-rafael:user_pubkey_here"],
    ["p", "user_pubkey_here"],
    ["j", "city-san-rafael"],
    ["type", "physical"]
  ],
  "content": "civicos:attestation:v1:city-san-rafael:physical:1739520000",
  "sig": "schnorr_signature_by_issuer"
}
```

**Key observations:**

1. **Signed by the ISSUER, not the user.** The `pubkey` field is the jurisdiction's issuer key — a key controlled by the CivicOS relay for that jurisdiction. This is what makes it an authority-issued credential.

2. **Addressable event.** The d-tag `attest:city-san-rafael:{user_pubkey}` means one attestation per user per jurisdiction. You can't accumulate multiple attestations for the same city.

3. **The user is in the tags, not the pubkey.** The `p` tag identifies who is being attested. The `pubkey` field identifies who did the attesting.

### Analogy: Notarized Document

Think of the attestation like a notarized document:

```
Physical world:
  A notary stamps a document: "I witnessed this person's signature."
  The notary's stamp proves the document is legitimate.
  Anyone who recognizes the notary's stamp can trust the document.
  The notary doesn't need to be present for future verification.

CivicOS:
  The jurisdiction issuer signs an event: "This pubkey was attested."
  The issuer's signature proves the attestation is legitimate.
  Anyone who knows the issuer's pubkey can verify the attestation.
  The issuer doesn't need to be contacted for future verification.
```

---

## How Verification Works

When you submit a voice, the relay checks the embedded attestation proof. This is the six-check verification from the commit:

### The Six Checks

```
Your voice arrives at the relay with an attestation_proof attached.

Check 1: KIND
  Is the proof a kind 30850 event?
  Why: Prevents someone from attaching a random Nostr event as "proof"

Check 2: ISSUER
  Was it signed by the jurisdiction's official issuer keypair?
  Why: Prevents self-attestation (you can't attest yourself)

Check 3: D-TAG
  Does the d-tag match "attest:{jurisdiction}:{your_pubkey}"?
  Why: Prevents using someone else's attestation

Check 4: REQUIRED TAGS
  Does it have ["p", your_pubkey] and ["j", jurisdiction]?
  Why: Ensures the attestation is for you, in this jurisdiction

Check 5: EVENT ID
  Does the hash of the event contents match the claimed ID?
  Why: Ensures nothing was tampered with after signing

Check 6: SCHNORR SIGNATURE
  Is the signature valid against the issuer's public key?
  Why: The cryptographic proof that the issuer actually signed this
```

### Why Embed Rather Than Look Up?

The proof is embedded ON the voice, not looked up in a separate table. This is a deliberate architecture choice:

```
Old approach (JOIN):
  Voice table: pubkey, entity, stance, signature
  Attestation table: pubkey, jurisdiction, nostr_event

  To check attestation:
    SELECT * FROM voices
    JOIN attestations ON voices.pubkey = attestations.pubkey
    WHERE attestations.jurisdiction = 'city-san-rafael'

  Problems:
    - Need access to attestation table (not always available)
    - Cross-table JOIN on every read
    - Federation requires sharing the attestation table
    - Other relays can't verify without the original database

New approach (embed):
  Voice record: pubkey, entity, stance, signature, attestation_proof

  To check attestation:
    attestation_proof IS NOT NULL  (one field check)

  To VERIFY attestation:
    Run the 6 checks above on the embedded proof

  Advantages:
    - Self-contained: the voice carries its own proof
    - Portable: works on any relay, no database access needed
    - Fast reads: no JOIN required
    - Federation-ready: receiving relay can verify independently
```

### Analogy: Passport

```
Old approach = calling the DMV every time someone shows you an ID
  "Is this person really licensed?" → call, wait, get answer
  What if the DMV is down? What if you're in another state?

New approach = checking the physical passport in their hand
  Hologram intact? Photo matches? Expiration date valid? Issuer signature valid?
  You don't need to call the issuing country. The document IS the proof.
```

The attestation proof is a cryptographic passport embedded on every voice. Any relay, anywhere, can verify it by checking the math — no phone call to the original issuer needed.

---

## What Attestation Doesn't Do

It's equally important to understand what the attestation system is NOT:

### Not Identity Verification

Attestation does NOT prove who you are. It proves you physically attended a community event. No government ID is checked. No name is recorded. The volunteer uses human judgment ("this is a person") not bureaucratic verification ("this is John Smith of 123 Main St").

```
What attestation proves:
  ✓ A human being physically attended a community event
  ✓ A volunteer judged them to be a real, distinct person
  ✓ Their cryptographic key is bound to that attestation

What attestation does NOT prove:
  ✗ Their legal name
  ✗ Their address
  ✗ Their citizenship or residency status
  ✗ Whether they're "qualified" to have opinions
```

This is deliberate. CivicOS is inclusive by design — undocumented residents, minors, anyone who shows up can participate. The gate is "you're a real person who cares enough to attend a community event," not "you can produce government-issued identification."

### Not Surveillance

The attestation system is designed with privacy gaps — intentional information separations:

```
The volunteer knows:
  ✓ A person showed up and got a code
  ✗ What key the person uses
  ✗ How the person votes

The relay knows:
  ✓ A key is attested for this jurisdiction
  ✓ What the key voices on
  ✗ Who the person behind the key is
  ✗ Where they got the code

No single party knows both:
  - Who the person is AND how they participate
```

### Not Foolproof

A determined person can get multiple codes across multiple events. This is noise, not manipulation — they'd need to physically attend many events, each time convincing a different volunteer they're a new person. This doesn't scale.

What gated attestation DOES prevent:
- Bot armies (no physical presence = no attestation)
- Autonomous agents (no physical presence = no attestation)
- Casual Sybil attacks (generating keys is easy; getting codes is hard)

What it DOESN'T prevent:
- A motivated individual getting 3-4 codes (acceptable noise)
- A person giving their code to another real person (still a real person)

---

## The Three Layers of CivicOS

Now let's zoom out and see how everything fits together. CivicOS has three layers:

```
Layer 3: EDGE INTELLIGENCE (the agent)
  What: An AI that filters and contextualizes civic data for you
  Where: Your device / your AI client (Claude.ai, ChatGPT, etc.)
  Sees: Your preferences, your neighborhood, your civic history
  Does: "This rezoning affects the school your kids attend"

Layer 2: RELAY (the coordination infrastructure)
  What: Stores and serves signed civic events
  Where: Server(s) run by CivicOS and/or community operators
  Sees: Voices, entities, counts (all public)
  Does: "12 people support this, 3 oppose"

Layer 1: CIVIC DATA (the knowledge base)
  What: Structured government data (meetings, decisions, legislation)
  Where: CivicOS backend (PostgreSQL), exposed via MCP
  Sees: Official records, agendas, transcripts, budget
  Does: "Council votes Monday at 7pm on 4th Street rezoning"
```

### How the Layers Interact

```
A resident asks: "What's happening with housing in my area?"

Layer 1 (Civic Data):
  → MCP server queries: meetings, decisions, legislation
  → Returns: "Council votes Monday on 4th Street rezoning.
     Similar proposal failed 3-2 in 2025."

Layer 2 (Relay):
  → Voice counts: "23 people care. 15 support, 3 oppose, 5 watching."
  → All voices carry attestation proofs → "all 23 are attested"

Layer 3 (Edge Intelligence):
  → Agent knows: user lives on 4th Street, cares about housing
  → Agent reasons: "This directly affects your neighborhood.
     State density bonus law may apply. CDBG funding at risk."
  → Agent surfaces: "High relevance. Here's what you should know
     before Monday's meeting."
```

### Who Knows What

This is the privacy model — no single component has the full picture:

```
                    Knows your          Knows what         Knows who
                    preferences?        people voice on?   the people are?

Civic Data (MCP)      No                  N/A                N/A
Relay                 No                  Yes (public)       No (just keys)
Edge Agent            Yes                 Yes                No (just keys)
Volunteer             No                  No                 Partially (face)
```

**Nobody has:** Your preferences AND your identity AND your civic history all together. This is a feature, not a limitation.

---

## Edge Intelligence: The Agent Layer

The agent is where intelligence lives in CivicOS. It replaces the centralized recommendation engine (Facebook's algorithm, Nextdoor's feed) with user-controlled reasoning.

### Why Intelligence at the Edge?

```
Centralized intelligence (Facebook, Nextdoor):
  Platform has ALL the data:
    - What you click on
    - How long you look at posts
    - Who you interact with
    - What makes you angry (engagement!)

  Platform decides what you see:
    - Optimized for time-on-site
    - Outrage gets more engagement → shown more
    - You can't see or control the algorithm
    - "Why am I seeing this?" → no answer

Edge intelligence (CivicOS):
  Agent has YOUR data (preferences, location, history)
  Agent queries PUBLIC data (civic data, voice counts)
  Agent applies YOUR filtering logic

  You control what you see:
    - "Stop showing me parking issues"
    - "Be more aggressive on education"
    - "Why did you show me this?" → actual explanation
    - "I want to see everything about housing" → done
```

### The MCP Connection

MCP (Model Context Protocol) is how the agent accesses civic data. Think of it as a library card for the agent:

```
Without MCP:
  Agent knows: "User cares about housing"
  Agent can do: Search the internet, read news articles
  Quality: Generic, not locally specific

With MCP (Jurisdiction MCP):
  Agent knows: "User cares about housing"
  Agent can call:
    search_meeting_history("housing")
    get_public_testimony("rezoning")
    search_regulatory_stack("density bonus")
    get_budget_items("housing")
    find_similar_issues("traffic 4th street")

  Quality: Deeply local, specific, sourced from official records
```

MCP is the bridge between "general AI that can talk about housing" and "AI that knows the specific housing decisions San Rafael is making, who voted how, what the budget impact is, and what state law applies."

### Analogy: Librarian

```
The civic data (MCP)  = the library's collection
The relay             = the community bulletin board in the library lobby
The agent             = your personal librarian who knows your interests

The librarian doesn't own the books.
The librarian doesn't control the bulletin board.
The librarian helps YOU find what matters to YOU.

A good librarian says:
  "I know you care about schools. There's a budget hearing
   Tuesday that affects school funding. Also, 14 people posted
   on the bulletin board about the same topic. Want me to
   pull the relevant meeting minutes?"

The library exists whether or not you have a librarian.
But the librarian makes it vastly more useful.
```

---

## Action Primitives: From Signal to Outcome

Voices express interest. But civic change requires action. CivicOS has three event types for turning coordination into real-world outcomes:

### The Engagement Ladder

```
Level 1: AWARENESS
  "I know about this issue"
  → Browse civic data, subscribe to notifications

Level 2: SIGNAL
  "I care about this issue"
  → Voice: support, oppose, or watching

Level 3: COMMITMENT
  "I will do something about this issue"
  → Commit to: write a letter, attend meeting, call official

Level 4: ACTION
  "I did something about this issue"
  → Complete: letter sent, meeting attended, call made

Level 5: IMPACT
  "My action contributed to the outcome"
  → Attribution: "Your comment was cited by the supervisor"
```

### How Actions Work

```
Step 1: Organizer creates an ACTION (kind 30810)
  "Write a comment to the planning commission by Feb 14.
   Here's a template. Target: 30 comments."

Step 2: Participants make COMMITMENTS (kind 30811)
  "I will write a comment."
  → 27 commitments so far out of 30 target

Step 3: Participants submit COMPLETIONS (kind 30812)
  "I wrote and sent my comment."
  → 24 completed out of 27 committed

Step 4: Everyone can see progress:
  Written Comment:  24 completed / 27 committed / 30 target
  Attend Meeting:    0 completed / 11 committed / 15 target
  Contact Rodoni:    8 completed / 10 committed / 10 target
```

### Why This Matters

| Without Actions | With Actions |
|-----------------|--------------|
| "89 people clicked support" | "27 letters submitted to the commission" |
| Council sees: online clicks | Council sees: constituent letters |
| No follow-through mechanism | "You committed — here's your reminder" |
| No attribution | "Your letter was cited in the vote" |

89 voices are a signal. 27 letters are a civic action. The difference matters to decision-makers.

---

## Design Decisions: Why This Architecture?

### Decision 1: Protocol Over Platform

**We chose to build infrastructure, not an app.**

```
The app approach:
  Build a beautiful civic engagement app
  + Faster to ship
  + Better UX control
  - Users locked into our app
  - We become the gatekeeper
  - If we fail, everything disappears

The protocol approach:
  Build coordination infrastructure anyone can use
  + No lock-in
  + Resilient to any single operator failing
  + Multiple UX surfaces (extension, web, AI, email)
  - Harder to build
  - Less UX control
  - Slower to ship

We chose protocol because civic infrastructure must outlast any
single company. Democratic coordination can't depend on a startup
surviving.
```

### Decision 2: Nostr Over Custom Protocol

**We chose to extend Nostr rather than build from scratch.**

```
Custom protocol:
  + Perfect fit for civic use case
  - No ecosystem (have to build everything)
  - No key management tools for users
  - No existing clients
  - Have to convince people to adopt our protocol

Nostr extension:
  + Existing ecosystem (Damus, Primal, nos2x, etc.)
  + Key management solved (multiple wallets)
  + Standard cryptography (secp256k1/BIP-340)
  + Federation built-in (NIP-01)
  - Some civic needs don't map perfectly to Nostr
  - Higher kind numbers for our event types

We chose Nostr because the ecosystem is more valuable than
a perfect protocol fit. Users don't need to learn a new system.
```

### Decision 3: Gated Over Weighted

**We chose hard attestation gate over weighted provenance.**

```
Weighted provenance:
  + More permissive (anyone can participate)
  + Elegant (quality visible, evaluation at edge)
  - Breaks against autonomous agents
  - Complexity burden on users
  - No hard boundary against spam

Gated attestation:
  + Hard defense against spam and bots
  + Simple mental model (attested or not)
  + Federation-friendly (proof travels with voice)
  - Requires in-person event attendance
  - Friction for new users
  - Equity concerns (must get to an event)

We chose gated because the spam threat from autonomous agents
is existential for a coordination system. A system full of fake
voices is worse than useless — it actively misleads.

Mitigations for friction/equity:
  - Codes distributed at many venue types
  - No ID required
  - Once attested, no further friction
  - Browsing and reading remain fully open
```

### Decision 4: Edge Intelligence Over Centralized Algorithm

**We chose user-controlled AI filtering over platform-controlled recommendation.**

```
Centralized algorithm (Facebook model):
  + "Just works" — users don't configure anything
  + Platform can optimize holistically
  - Misaligned incentives (engagement ≠ civic value)
  - Opaque (can't see or control the algorithm)
  - Platform has all user data
  - Creates filter bubbles

Edge intelligence:
  + Aligned incentives (your agent works for you)
  + Transparent (can explain every recommendation)
  + Private (preferences stay on your device)
  + Controllable ("stop showing me parking issues")
  - Requires AI infrastructure
  - Variable quality depending on model
  - More setup for power-user features

We chose edge intelligence because civic coordination cannot
be subordinate to an engagement optimization function. The
intelligence must serve the user, not the platform.
```

### Decision 5: Embed Attestation Proof Over Database JOIN

**We chose write-time embedding over read-time lookup.**

```
Read-time JOIN:
  + Simpler storage (attestation in one table)
  + Familiar pattern (standard SQL)
  - Requires attestation database access
  - Can't verify across relays
  - Slower reads (JOIN on every query)
  - Federation requires sharing attestation DB

Write-time embedding:
  + Self-contained voices (proof travels with the voice)
  + Any relay can verify independently
  + Fast reads (field presence check)
  + Federation-ready (no shared database needed)
  - Larger voice records (include full proof)
  - Proof is repeated per voice per user

We chose embedding because federation is a core goal.
A voice that can only be verified by the relay that issued
the attestation is not truly portable. Embedding makes
voices self-verifying artifacts.
```

---

## The Complete System Map

Here's everything in one view:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR DEVICE                                  │
│                                                                      │
│  Browser Extension                    AI Client                      │
│  ┌───────────────────────┐           ┌──────────────────────┐       │
│  │ Private key (secret)  │           │ Claude.ai / ChatGPT  │       │
│  │ Public key            │           │                      │       │
│  │ Attestation proof     │           │ Your preferences     │       │
│  │                       │           │ Your location        │       │
│  │ Signs voices/comments │           │ Your filtering logic │       │
│  │ Displays civic data   │           │                      │       │
│  └───────────┬───────────┘           └──────────┬───────────┘       │
│              │                                   │                   │
└──────────────┼───────────────────────────────────┼───────────────────┘
               │ Signed events                     │ MCP queries
               │ (with attestation proof)          │
               ▼                                   ▼
┌──────────────────────────┐     ┌──────────────────────────────────┐
│     CivicOS RELAY        │     │     CivicOS BACKEND              │
│                          │     │     (Jurisdiction MCP)            │
│  Stores:                 │     │                                  │
│  - Voices (signed)       │     │  Serves:                         │
│  - Entities              │     │  - Meetings, decisions           │
│  - Subscriptions         │     │  - Transcripts, testimony        │
│  - Actions/commitments   │     │  - Legislation, municipal code   │
│                          │     │  - Budget, issues                │
│  Verifies:               │     │  - Historical context            │
│  - Signatures            │     │                                  │
│  - Attestation proofs    │     │  PostgreSQL + pgvector            │
│                          │     │  (semantic search enabled)       │
│  Aggregates:             │     │                                  │
│  - Voice counts          │     │  Exposed via:                    │
│  - Attested counts       │     │  - MCP (for AI clients)          │
│                          │     │  - REST API                      │
│  PostgreSQL              │     │                                  │
│  (separate database)     │     │                                  │
└──────────┬───────────────┘     └──────────────────────────────────┘
           │
           │ Federation (optional)
           │ (signed events synced between relays)
           ▼
┌──────────────────────────┐
│     OTHER RELAYS         │
│                          │
│  Same protocol, different│
│  operators               │
│                          │
│  Can verify all proofs   │
│  independently (no trust │
│  in originating relay)   │
└──────────────────────────┘
```

### Data Flow: From City Hall to Your Screen

```
1. CITY ACTIVITY
   San Rafael City Council publishes agenda for Feb 3 meeting
   Item 6a: 4th Street Corridor Rezoning Proposal

2. DATA INGESTION
   CivicOS extractors pull from Legistar (agenda management system)
   Parse agenda PDF, extract items, topics, dates
   Store in PostgreSQL: meetings table, chunks table (PDF content)
   Generate vector embeddings for semantic search

3. CIVIC DATA AVAILABLE
   MCP server can now answer:
   "What's on the agenda?" → Item 6a: 4th Street Rezoning
   "What happened last time?" → Failed 3-2 in 2025
   "What does the code say?" → Municipal code on rezoning
   "What's the state law?" → Density bonus law SB 1234

4. RELAY RECEIVES ENTITY
   Entity event (kind 30801) published to relay
   "decision:city-san-rafael:2026-02-03:item-6a"

5. RESIDENTS VOICE
   23 attested residents voice on the entity
   Each voice carries: signature + attestation proof
   Relay verifies and stores each one
   Voice count: 15 support, 3 oppose, 5 watching

6. YOUR AGENT SYNTHESIZES
   Agent subscribes to relay → sees voice counts
   Agent queries MCP → gets civic context
   Agent knows your preferences → housing, 4th Street area

   "The council votes Monday on 4th Street rezoning.
    23 attested residents are engaged — 15 support.
    This is similar to the 2025 proposal that failed 3-2.
    State density bonus law may require higher density.
    This directly affects your neighborhood."

7. YOU DECIDE
   Read the briefing. Maybe voice. Maybe commit to attend
   the meeting. Maybe write a comment.

   Your action → signed event → relay → counted → visible.
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **Attestation** | Proof that a key belongs to a real community member (kind 30850 event signed by jurisdiction issuer) |
| **Attestation proof** | The full kind-30850 Nostr event embedded on each voice/comment |
| **BIP-340** | The Schnorr signature standard CivicOS uses (Bitcoin Improvement Proposal 340) |
| **d-tag** | The tag that makes addressable events unique — like a page name in a wiki |
| **Edge intelligence** | AI filtering that runs on the user's side, not a central server |
| **Entity** | A civic item you can voice on (decision, initiative, agenda item, meeting) |
| **Event** | A signed JSON message in the Nostr protocol (the only data type) |
| **Federation** | Multiple relays syncing voice records for the same entities |
| **Gated attestation** | Requiring a valid attestation proof to voice or comment (the current model) |
| **Issuer keypair** | The jurisdiction's key pair used to sign attestation events |
| **Kind** | The type of Nostr event (30800 = voice, 30850 = attestation, etc.) |
| **MCP** | Model Context Protocol — how AI agents access structured civic data |
| **Nostr** | Notes and Other Stuff Transmitted by Relays — the underlying protocol |
| **Provenance** | Additional context about a key's history (age, voice count, attestation type) |
| **Relay** | A server that stores and serves signed Nostr events |
| **Schnorr signature** | The signature scheme used (secp256k1 curve, BIP-340 standard) |
| **secp256k1** | The elliptic curve used for all CivicOS cryptography (same as Bitcoin) |
| **Sybil attack** | Creating fake identities to manipulate vote/voice counts |
| **Voice** | A signed expression of civic interest (support, oppose, watching) on an entity |
| **Weighted provenance** | The old model where voice quality was a spectrum (replaced by gated attestation) |

---

## See Also

- [Relay Attestation](../relay/attestation.md) — Operational reference for gated attestation
- [Relay Overview](../relay/overview.md) — Relay services and architecture
- [AI Proxy](../relay/ai-proxy.md) — How the relay provides privacy-preserving AI access

---

## Questions to Explore

If you're using NotebookLM or Claude.ai to dig deeper, here are good starting questions:

**Cryptography:**
- "Explain how Schnorr signatures differ from ECDSA and why CivicOS chose Schnorr"
- "Walk me through exactly how a Nostr event ID is computed from its fields"
- "What would happen if someone's private key was compromised? What can they do?"

**Architecture:**
- "Why does CivicOS use two separate databases (main + relay)?"
- "How does the MCP server work? What tools does it expose to AI clients?"
- "Walk me through federation — what happens when two relays disagree on voice counts?"

**Attestation:**
- "What are the equity concerns with physical attestation and how does CivicOS address them?"
- "How would device attestation (WebAuthn) complement physical attestation?"
- "What happens if the jurisdiction issuer keypair is compromised?"

**Design tradeoffs:**
- "Compare CivicOS's approach to spam prevention with reCAPTCHA, proof-of-work, and social graphs"
- "Why is engagement optimization harmful for civic coordination specifically?"
- "How does the 'intelligence at the edges' approach compare to collaborative filtering?"

**Civic coordination:**
- "Why do action primitives (commitment, completion) matter beyond just voice counts?"
- "How does cross-jurisdiction coordination work for an issue that spans city, county, and state?"
- "What's the difference between an initiative and a decision entity?"
