# Module 5: Jurisdiction Scope and Attestation Rollup

*How relay scope maps to jurisdictions, how attestation works across government levels, and how to handle the messy reality of U.S. governance structure.*

*Prerequisites: Modules 1-4. You should understand keys, events, relays, attestation, and relay trust.*

---

## The Deceptively Simple Question

"What jurisdiction does a relay cover?"

This looks like a straightforward infrastructure question — like asking "what region does this database serve?" But it's actually three entangled questions:

1. **What entities does a relay host?** (data scope)
2. **What attestations does a relay accept?** (identity scope)
3. **How many relay instances should you run?** (operational scope)

Each has different constraints and different answers.

---

## Question 1: What Entities Does a Relay Host?

A relay is a store for signed events. The events themselves carry jurisdiction tags (`["j", "city-san-rafael"]`). A single relay *can* host entities from any number of jurisdictions — there's no technical constraint. The entity namespaces already handle disambiguation:

```
decision:city-san-rafael:2026-02-03:item-6a     ← city entity
initiative:marin-county:transit-expansion        ← county entity
legislation:california:sb-1234                   ← state entity
program:us-federal:cdbg-2026                     ← federal entity
```

These can all live on the same relay. The relay doesn't need to "know" about jurisdictional boundaries — the entities self-describe through their namespaced identifiers.

So the question isn't really "what jurisdiction does a relay cover?" but rather **"what determines which entities end up on which relay?"** And the answer is: **the operator's choice**, driven by their data ingestion capability and their mission.

| Operator | Likely scope | Reason |
|----------|-------------|--------|
| CivicOS (reference) | All jurisdictions with data | Mission is broad civic coordination |
| Local newspaper | Their metro area | Reporting coverage area |
| City government | Their own city | Official channel |
| Housing coalition | Housing entities across levels | Issue-based, cross-jurisdiction |
| University researcher | Whatever they're studying | Research scope |

The relay is jurisdiction-agnostic. The scoping is a business decision, not an architectural one.

---

## Question 2: What Attestations Does a Relay Accept?

This is the harder question — the one that forces a real design decision.

### The Problem

Attestation is currently scoped to a jurisdiction: the d-tag is `attest:city-san-rafael:{pubkey}`. When a San Rafael resident wants to voice on a county-level entity, what happens?

```
Scenario:
  Resident attested for "city-san-rafael"
  Wants to voice on "initiative:marin-county:transit-expansion"

  The relay checks their attestation_proof:
    d-tag = "attest:city-san-rafael:{pubkey}"
    j-tag = "city-san-rafael"

  But the voice entity is in "marin-county".
  Does the attestation satisfy the gate?
```

### Three Possible Models

**Model A: Strict Matching**

Attestation jurisdiction must exactly match entity jurisdiction. A city-san-rafael attestation only works for city-san-rafael entities.

```
Consequence: A San Rafael resident needs separate attestation
for city, county, state, and federal participation.

That's 4 events to attend, 4 codes to redeem.

Completely impractical. Nobody will do this.
```

**Model B: Upward Rollup**

City attestation is valid at city, county, state, and federal levels — because being a San Rafael resident necessarily makes you a Marin County resident, a California resident, and a U.S. resident.

```
city-san-rafael attestation → valid for:
  city-san-rafael entities        ✓ (exact match)
  marin-county entities           ✓ (San Rafael is in Marin)
  california entities             ✓ (Marin is in California)
  us-federal entities             ✓ (California is in the US)

marin-county attestation → valid for:
  city-san-rafael entities        ✗ (county doesn't prove city)
  marin-county entities           ✓ (exact match)
  california entities             ✓ (rollup)
  us-federal entities             ✓ (rollup)
```

Rollup goes up, not down or sideways. A county attestation doesn't prove you live in a specific city. A San Rafael attestation doesn't let you voice on Novato city entities.

**Model C: Jurisdiction-Agnostic**

Any valid attestation from any jurisdiction satisfies the gate. A Berkeley resident can voice on San Rafael entities.

```
Consequence: Attestation proves "you're a real person who
attended a community event somewhere" but not that you have
standing in the specific jurisdiction of the entity.

A well-funded interest could attest supporters in one city
and deploy their voices in another city's decisions.
```

### Why Model B Is Right

**Model B (upward rollup)** matches how civic standing actually works:

```
Real life:
  You testify at a county board of supervisors meeting as a
  county resident. Nobody asks for a separate county-level ID.
  Your city address proves county residency.

  You comment on a state bill as a California resident.
  Your city address proves state residency.

  The hierarchy is implicit: city ⊂ county ⊂ state ⊂ federal.

CivicOS should mirror this:
  Your city attestation proves residency at all higher levels.
  One code, one attestation, full civic participation.
```

It's practical (one attestation covers all levels), it preserves locality (you can't vote sideways into another city), and it matches the mental model residents already have.

### Analogy: Mailing Address

```
Your address:
  123 Main St, San Rafael, CA 94901, USA

This single address proves:
  ✓ You live on Main St (neighborhood level)
  ✓ You live in San Rafael (city level)
  ✓ You live in Marin County (county level)
  ✓ You live in California (state level)
  ✓ You live in the United States (federal level)

  ✗ It does NOT prove you live in Novato
  ✗ It does NOT prove you live in Sonoma County

Attestation rollup works the same way.
Your city attestation cascades upward, not sideways.
```

### Implementation: Jurisdiction Hierarchy

Upward rollup requires the system to know the containment relationships between jurisdictions. This is a simple tree in the registry:

```json
{
  "city-san-rafael": {
    "parent": "marin-county",
    "type": "city"
  },
  "city-novato": {
    "parent": "marin-county",
    "type": "city"
  },
  "marin-county": {
    "parent": "california",
    "type": "county"
  },
  "california": {
    "parent": "us-federal",
    "type": "state"
  },
  "us-federal": {
    "parent": null,
    "type": "federal"
  }
}
```

When the relay verifies an attestation against an entity:

```
attestation_jurisdiction = "city-san-rafael"
entity_jurisdiction = "marin-county"

Check: is "city-san-rafael" equal to or a descendant of "marin-county"?

Walk up the tree:
  city-san-rafael → parent: marin-county ← MATCH

Result: attestation is valid for this entity.
```

```
attestation_jurisdiction = "city-san-rafael"
entity_jurisdiction = "city-novato"

Check: is "city-san-rafael" equal to or a descendant of "city-novato"?

Walk up the tree:
  city-san-rafael → parent: marin-county
  marin-county → parent: california
  california → parent: us-federal
  us-federal → parent: null (root)

  Never encountered "city-novato".

Result: attestation is NOT valid for this entity.
```

---

## The Special Districts Problem

U.S. governance doesn't fit a clean tree. School districts, water districts, transit authorities, and special assessment zones overlap city boundaries in messy ways:

```
Marin County
├── San Rafael (city)
├── San Anselmo (city)
├── Fairfax (city)
├── Novato (city)
│
├── Ross Valley School District
│   └── Covers: parts of San Anselmo, Fairfax, and San Rafael
│       (but NOT all of San Rafael — some is in different districts)
│
├── Marin Municipal Water District
│   └── Covers: most of southern Marin
│       (but NOT Novato, which has its own water district)
│
├── Golden Gate Transit
│   └── Covers: Marin County AND Sonoma County
│       (crosses county boundaries!)
│
└── Marin Healthcare District
    └── Covers: all of Marin County
        (aligned with county boundary — easy case)
```

A San Rafael resident might be in the Ross Valley School District, or might not — it depends on their specific address. The clean hierarchy breaks down.

### Options for Special Districts

**Option 1: Treat special districts as peers of their member jurisdictions.**

Ross Valley School District accepts attestation from any city it overlaps with (San Anselmo, Fairfax, San Rafael). This over-includes — some San Rafael residents aren't in the district — but it's simple and errs on the side of access.

```
ross-valley-school-district:
  accepts_from: [city-san-anselmo, city-fairfax, city-san-rafael]
  type: special_district
```

**Option 2: Geographic attestation.**

Attestation includes a location (neighborhood or coordinates), and the relay checks geographic containment against district boundaries. More precise but significantly more complex — you need GIS boundary data for every special district.

```
attestation:
  jurisdiction: city-san-rafael
  neighborhood: terra-linda
  coordinates: [37.97, -122.53]

ross-valley-school-district:
  boundary: [GeoJSON polygon]
  → check: are the coordinates inside the polygon?
```

**Option 3: Defer to the agent layer.**

The relay accepts any upward-rollup attestation. The agent layer helps users understand standing:

```
Agent: "This is a Ross Valley School District item. The district
covers parts of San Rafael, San Anselmo, and Fairfax. Based on
your neighborhood (Terra Linda), you're in this district. Would
you like to voice?"
```

The relay doesn't enforce district boundaries — it accepts the broader city/county attestation. The agent provides context about standing. This keeps the relay simple and moves the nuance to where intelligence lives (the edge).

### Recommendation

For the pilot: **don't solve this.** San Rafael has one unified school district. Special district overlap doesn't arise.

For multi-city: **Option 1 (peer membership) plus Option 3 (agent guidance).** Keep the relay's acceptance logic simple (tree walk + explicit peer lists for special districts). Use the agent layer for nuance.

Geographic attestation (Option 2) is the most correct but introduces significant complexity (GIS data, boundary queries, address geocoding) for marginal benefit at early scale. Consider it if special district participation becomes a primary use case.

---

## Question 3: How Many Relay Instances to Run?

Given that a single relay can host multiple jurisdictions, this is an operational question, not an architectural one.

### Options

**Option A: One relay, all jurisdictions.**

```
civicos-relay.modal.run
  → hosts: city-san-rafael, marin-county, california, us-federal
  → one database, one deployment, one codebase
```

**Option B: One relay per jurisdiction.**

```
relay-san-rafael.modal.run    → city-san-rafael only
relay-marin.modal.run         → marin-county only
relay-california.modal.run    → california only
```

**Option C: One relay per geographic region.**

```
relay-bayarea.modal.run       → all Bay Area jurisdictions
relay-socal.modal.run         → all SoCal jurisdictions
```

### Tradeoffs

| Factor | Single relay | Per-jurisdiction | Per-region |
|--------|-------------|-----------------|------------|
| **Operational simplicity** | Best — one thing to deploy | Worst — N deployments | Middle |
| **Fault isolation** | Worst — one failure takes everything down | Best — failures are scoped | Good |
| **Federation path** | Hard to hand off one city to another operator | Clean — hand off the whole relay | Messy — partial handoffs |
| **Cost** | Lowest — shared infrastructure | Highest — per-instance overhead | Middle |
| **Data separation** | All in one database | Clean separation | Partial separation |
| **Handoff to cities** | Requires extraction | City gets their own relay cleanly | Requires extraction |

### The Practical Answer

**Start with Option A** (single relay, all jurisdictions). It's simplest, cheapest, and sufficient for pilot and early multi-city deployment.

But **namespace everything as if you'll split later** — which the entity namespacing already does. Entities are `decision:city-san-rafael:...`, not `decision:2026-02-03:...`. Attestations are `attest:city-san-rafael:...`, not `attest:...`. The jurisdiction is always explicit.

The moment a city wants to run its own relay, or an independent operator wants to host a specific jurisdiction, the split is clean: extract all events with `j-tag = "city-X"` and hand them over. The namespacing makes this a simple filter, not a migration.

### When to Split

Split from single relay to per-jurisdiction when:

- **A city wants to run its own relay** (sovereignty demand)
- **An independent operator wants a specific jurisdiction** (federation demand)
- **Scale requires it** (database or compute limits — unlikely before hundreds of jurisdictions)
- **Regulatory requirements** (data residency laws, which aren't currently a factor for public civic data)

Don't split preemptively. The operational complexity isn't worth it until there's concrete demand.

### What Actually Constrains Multi-Jurisdiction Deployment

The relay hosting is trivial. A single Supabase database can handle thousands of jurisdictions' voice records. The real bottleneck is **data ingestion** — each city requires custom extraction work:

```
Adding a new city:
  1. Identify agenda management system (Legistar, Novus, PrimeGov, etc.)
  2. Build or configure extractor
  3. Parse agenda PDFs, extract items, topics, dates
  4. Ingest meeting transcripts
  5. Ingest municipal code
  6. Generate vector embeddings
  7. Configure jurisdiction in registry

Time: weeks to months per jurisdiction
Cost: Engineering effort, not infrastructure

vs.

Adding a new city to the relay:
  1. Add jurisdiction to registry
  2. Entities start arriving with the new j-tag

Time: minutes
Cost: Negligible
```

The data pipeline is the deployment unit, not the relay. Relay scope follows data availability.

---

## The Full Scoping Model

Putting all three questions together:

```
ENTITY SCOPE:
  Relay hosts whatever entities it has data for.
  Entities self-describe via namespaced identifiers.
  No architectural constraint on mixing jurisdictions.
  Scoping is an operator choice based on data availability and mission.

ATTESTATION SCOPE:
  Upward rollup: city attestation valid at city, county, state, federal.
  No sideways rollup: city-A attestation not valid for city-B entities.
  Special districts: peer membership lists + agent-layer guidance.
  Hierarchy published in registry, relay walks the tree.

INSTANCE SCOPE:
  Start with one relay serving all jurisdictions.
  Split when federation demand, city sovereignty, or scale requires it.
  Namespacing makes future splits clean (filter by j-tag).
  Data ingestion, not relay hosting, is the deployment bottleneck.
```

---

## See Also

- [Relay Federation](../relay/federation.md) — Operational reference for attestation rollup and multi-operator peering
- [Federation Domain Architecture](../decisions/federation_domain_architecture.md) — Domain strategy and operator model

---

## Questions to Explore

**On attestation rollup:**
- "What if someone moves from San Rafael to Novato? Their attestation says city-san-rafael but they no longer live there. How should this be handled?"
- "Should there be a concept of 'downward attestation' — a county-level attestation that proves residency somewhere in the county without specifying which city?"
- "How does attestation rollup interact with thematic relays that span multiple jurisdictions?"

**On special districts:**
- "What real special districts exist in Marin County, and which ones would matter for civic coordination?"
- "How do existing civic engagement platforms handle the special district boundary problem?"
- "Could a school district issue its own attestation codes at school events? How would that integrate?"

**On relay instances:**
- "What would the handoff process look like when San Rafael wants to run its own relay?"
- "How does the Mastodon instance migration experience inform CivicOS's relay migration design?"
- "At what scale (number of jurisdictions, number of voices) does a single database become insufficient?"

**On the hierarchy:**
- "Indian country (tribal jurisdictions) doesn't fit the city/county/state tree at all. How would tribal sovereignty be represented?"
- "What about unincorporated areas that aren't in any city but are in a county?"
- "How do other countries' government structures (UK parishes, French communes) map to this model?"
