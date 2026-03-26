# Module 4: Relay Trust and Integrity

*How many relays do you need? How do you prevent relay operators — including yourself — from being corrupted? Adversary analysis from first principles.*

*Prerequisites: Modules 1-3. You should understand keys, signatures, Nostr events, relays, federation, and gated attestation.*

---

## The Question

You've learned that relays store and serve signed civic events. You've learned that voices are self-verifying — the relay can't forge them because it doesn't have users' private keys. You've learned that federation means multiple relays can serve the same entities.

But this raises deeper questions:

1. **How many relays should exist?** (Cardinality)
2. **How does that number affect data integrity?** (Robustness)
3. **How do you trust the relay operators — including CivicOS itself — against adversaries?** (Integrity)

These questions get at the trust foundation of the entire system.

---

## Relay Cardinality

Cardinality isn't a single number — it's a function of what you're defending against.

### What Are You Defending Against?

**Availability** (relay goes offline): Any redundancy helps. Two relays serving the same entities means one can go down without data loss. This is standard infrastructure redundancy — solved problem.

**Censorship** (relay silently drops voices): Requires *operator-independent* redundancy. Three relays run by CivicOS on different servers don't help — a single organizational decision suppresses across all three. Three relays run by CivicOS, a local newspaper, and the League of Women Voters are meaningfully independent because they have different incentive structures and no shared chain of command.

**Byzantine faults** (relay actively lies about data): Requires 2f+1 relays to tolerate f malicious operators. To tolerate 1 lying relay, you need at least 3 independent operators. To tolerate 2, you need 5. This is a classical result from distributed systems theory.

### Why CivicOS's Architecture Changes the Cardinality Requirements

In a traditional distributed system, you're trusting relays to faithfully report state — you have to take their word for what the data says. In CivicOS, voices are self-verifying. The relay can't forge them, can't modify them, can't attribute them to the wrong key. So the attack surface is narrower than in a generic distributed system:

```
What a malicious relay CAN do:
  - Refuse to accept a voice (censorship at ingestion)
  - Accept but not serve a voice (silent censorship)
  - Report wrong counts (serve correct voices but lie about totals)
  - Go offline (availability attack)
  - Serve different data to different clients (equivocation)

What a malicious relay CANNOT do:
  - Forge a voice (doesn't have users' private keys)
  - Modify a voice (signature would break)
  - Forge an attestation (doesn't have the issuer key... unless it IS the issuer)
  - Attribute a voice to the wrong person (signature is bound to pubkey)
```

This means cardinality primarily defends against **omission and equivocation**, not fabrication. That's a significantly easier problem.

### Practical Cardinality Tiers

Think about relay deployment in tiers, not as a fixed number:

```
Tier 1: Single operator (pilot)

  CivicOS runs the relay.

  Risk: CivicOS is single point of failure AND control.

  Acceptable because: Pilot scale, proving the thesis, and voices
  are still self-verifying artifacts users could take to another
  relay later.


Tier 2: Operator + auditor (early adoption)

  CivicOS runs the relay.
  One independent party mirrors the data and verifies consistency.
  Could be: a journalist, a civic org, a university research group.
  They don't need to run a full relay — just periodically pull all
  voices and verify signatures + counts independently.

  Risk reduced: Silent censorship becomes detectable.


Tier 3: Multiple independent operators (production)

  3+ relays for major jurisdictions, run by independent organizations.
  CivicOS + local newspaper + civic organization, for example.
  Voices federate between them. Counts are independently verifiable.

  Risk reduced: Censorship requires collusion across organizations
  with different incentive structures.


Tier 4: Permissionless operation (at scale)

  Anyone can run a relay. Dozens exist for active jurisdictions.
  Similar to how multiple Nostr relays exist today.
  Clients connect to several simultaneously.

  Risk reduced: No practical censorship possible.
```

**The key insight:** You don't need Tier 4 to launch. You need Tier 2 to be credible. The jump from Tier 1 (pilot) to Tier 2 (auditable) is the most important transition.

### Operator Independence

The number of relays matters less than the **independence of their operators**. Independence means:

- Different organizational leadership (no shared chain of command)
- Different funding sources (no shared financial pressure point)
- Different incentive structures (newspaper vs. civic org vs. government vs. tech company)
- Different jurisdictions or sectors (geographic and sectoral diversity)

```
Weak independence (same sector):
  Relay A: run by CivicOS
  Relay B: run by CivicOS's fiscal sponsor
  Relay C: run by CivicOS's largest funder

  → All three share financial dependencies.
  → Pressure on the funder cascades to all relays.

Strong independence (cross-sector):
  Relay A: run by CivicOS (civic tech nonprofit)
  Relay B: run by Marin Independent Journal (local newspaper)
  Relay C: run by League of Women Voters (civic organization)
  Relay D: run by Dominican University (academic institution)

  → Different missions, different funders, different incentives.
  → Pressure on any one doesn't affect the others.
  → Collusion across all four is extremely unlikely.
```

---

## Data Robustness

The cardinality question is really asking: **how do you know the data you're seeing is complete and unmanipulated?**

### The Append-Only Property

Voice records have a natural property: they should only be added, never removed (except explicit revocations signed by the voice's own key). A relay's voice set for any entity should be monotonically growing — voice count goes up, never down, unless someone signs a revocation.

Any unexplained reduction in count is evidence of tampering.

### Commitment Logs

This property suggests a powerful technical mechanism: **commitment logs** — periodic, signed cryptographic snapshots of relay state.

```
How commitment logs work:

Every hour (or every N events), the relay publishes a signed
commitment to its complete voice set for each entity:

{
  "entity": "decision:city-san-rafael:proudcity-city-san-rafael-city-council-february-3-2026-tuesday:06",
  "timestamp": "2026-02-03T14:00:00Z",
  "voice_count": 23,
  "merkle_root": "a1b2c3d4...",
  "relay_signature": "..."
}

The "merkle_root" is a hash computed from all voice event IDs
for that entity. It uniquely fingerprints the exact set of voices.

Any client with the full voice list can recompute the root
and verify it matches. If it doesn't, either the relay is lying
about its state or serving incomplete data.
```

**What is a Merkle tree?** A Merkle tree is a data structure where every leaf is a hash of a data block (in this case, a voice event ID), and every non-leaf node is a hash of its children. The root hash at the top uniquely represents the entire set. Change one voice anywhere in the tree, and the root hash changes.

```
                  Root Hash
                 /          \
          Hash(AB)          Hash(CD)
          /     \           /     \
    Hash(A)  Hash(B)  Hash(C)  Hash(D)
       |        |        |        |
    Voice 1  Voice 2  Voice 3  Voice 4

If Voice 3 is removed or modified,
Hash(C) changes → Hash(CD) changes → Root Hash changes.
Any client comparing the root hash would detect the change.
```

### What Commitment Logs Defend Against

| Attack | Without commitment log | With commitment log |
|--------|----------------------|---------------------|
| Silent censorship (accept but don't serve a voice) | Undetectable — relay just omits the voice | Detectable — voice was in a previous root but absent now |
| Equivocation (different data to different clients) | Hard to detect without comparing notes | Clients compare merkle roots — disagreement is proof of equivocation |
| Count inflation (claim more voices than exist) | Undetectable without enumerating all voices | Root commits to exact set — inflated count doesn't match root |
| Historical revision (change old records) | Undetectable | Old commitments are signed and timestamped — revision changes the root |

### Analogy: Certificate Transparency

This isn't a new idea. The internet faced the same problem with certificate authorities (CAs) — organizations that sign HTTPS certificates. How do you know a CA isn't issuing fraudulent certificates?

The answer was **Certificate Transparency (CT)**: force CAs to publish every certificate they issue in an append-only log that anyone can audit. Browsers check that every certificate appears in a CT log. If a CA issues a certificate that's NOT in the log, that's proof of misbehavior.

For CivicOS relays, the equivalent is: force relays to commit to the exact set of voices they claim to have. Anyone can audit the commitment against the actual data.

### Cross-Relay Verification

When multiple relays serve the same entities, they can cross-check automatically:

```
Consistent (confidence high):
  Relay A publishes: entity X has 23 voices, merkle root = abc123
  Relay B publishes: entity X has 23 voices, merkle root = abc123
  → Same count, same root. Both serving identical data.

Inconsistent (investigation needed):
  Relay A publishes: entity X has 23 voices, merkle root = abc123
  Relay B publishes: entity X has 21 voices, merkle root = def456
  → Different count, different root. One or both are wrong.

Resolution:
  Any client can pull the full voice lists from both relays,
  verify all signatures independently, and determine which is correct.

  If Relay A has 2 valid voices that Relay B doesn't:
    → Relay B is censoring (or has a sync lag)

  If Relay A has 2 INVALID voices:
    → Relay A is inflating (serving forged data... but forged
       signatures won't verify, so this is trivially detectable)
```

**The critical property:** Resolving disagreements doesn't require trusting either relay. The voices themselves carry the proof. You verify signatures, not operator claims.

---

## Operator Integrity

Now the hardest question: how do you trust relay operators against sophisticated adversaries?

### Adversary Model

Three classes of adversary, from most to least likely:

**1. Institutional drift** — CivicOS itself gradually prioritizes its own survival (funding relationships, political convenience) over neutral relay operation. Not malice — incentive misalignment over time.

**2. Government pressure** — A city government, state AG, or federal agency pressures relay operators to suppress, reveal, or manipulate civic coordination data.

**3. Capital interests** — Developers, real estate companies, or industry groups attempt to inflate support or suppress opposition for specific civic decisions.

### Adversary: CivicOS Itself (Institutional Capture)

The most important adversary to design against is CivicOS. Not because of malice, but because:

- Foundation funders might have preferences about outcomes
- Organizational incentives might drift over time
- A single operator controlling the reference implementation has outsized power
- If CivicOS is the only relay AND the attestation issuer, it has total control

**Technical defenses:**

**1. Open source everything.** The relay code, the verification logic, the commitment log — all public and auditable. Anyone can run the same software and verify CivicOS's relay is behaving correctly.

**2. Separate the issuer key from the relay operator.** The [`civicos-signer`](../packages/civicos-signer.md) package enforces this separation from launch: trusted organizations hold their own issuer keys and run independent signing services. The relay operator cannot issue attestations — it calls out to the organization that distributed the code.

```
How it works (civicos-signer):
  CivicOS controls: relay operation
  Canal Alliance controls: their attestation signing key
  SR Public Library controls: their attestation signing key
  City Clerk controls: their attestation signing key
  → Multiple independent issuers. Relay calls out to each org's signer.
  → No single party controls attestation.
```

**3. Commitment logs** (described above). CivicOS publishes cryptographic commitments to its relay state. If CivicOS ever censors a voice, the historical commitment record proves it — permanently and irrefutably.

**4. Verifiable builds / reproducible deployment.** Anyone can verify the relay is running the published code, not a modified version. This is how you trust the software, not just the operator.

**Structural defenses:**

**5. Legal structure with public interest mandate.** 501(c)(3) or equivalent, with bylaws that constrain the organization's ability to manipulate civic data. This doesn't prevent capture but makes it legally actionable.

**6. Independent board or advisory committee.** Including journalists, civic organizations, and technologists who would raise alarms if the organization drifted.

**7. Encourage Tier 2+ cardinality early.** The best defense against institutional capture is making CivicOS's relay one of several, not the only one. The moment a second independent relay exists, CivicOS's misbehavior becomes detectable.

### Adversary: Government

Government adversaries come in several forms, each with different attack surfaces:

**Subpoena for voice records.** "Tell us who voiced against the housing project."

```
Defense: Privacy architecture.

Voice records are public and pseudonymous. The relay knows pubkeys,
not people. The attestation system has deliberate privacy gaps:

  Subpoena target    What they know              What they'd learn
  ─────────────────  ─────────────────────────── ──────────────────
  Relay operator     Pubkeys + voices            Who (by key) voiced how
                                                 but NOT real identities

  Code volunteer     Faces of people at events   Who attended
                                                 but NOT their keys

  User's device      Key + attestation           One user's full history
                     (browser localStorage)      (requires device access)

No single subpoena target yields: real identity + full participation.

The government would need to compromise BOTH the event volunteer
AND the user's device to deanonymize a specific voice. These are
held by different parties in different contexts.
```

**Censorship order.** "Remove voices opposing this project."

Defense: Federation + commitment logs. If the voice exists on other relays, censoring one doesn't remove it. If the commitment log shows the voice was previously included and is now missing, the censorship is provably documented — creating a public record of the government's interference.

**Coerced relay operation.** "Modify your relay to suppress voices on topic X."

Defense: Open source + commitment logs + independent relays. The coercion is detectable by any party comparing relay state to commitment history, or comparing across relays. The relay operator can comply with the order while the evidence of coercion is cryptographically preserved.

**Infiltration of attestation distribution.** "Have our agents distribute codes selectively — only to supporters."

This is the hardest government attack because it targets the physical distribution layer, not the cryptographic layer. Mitigations:

- Multiple independent distribution events at different venues, organized by different groups
- No single organization controls all code distribution
- Statistical monitoring: if attestation patterns correlate suspiciously with voice patterns (everyone attested at event X voted the same way), something is wrong
- Rotating distribution volunteers to prevent capture of any single distribution channel

### Adversary: Capital Interests

A developer wants to inflate support for a project. A real estate company wants to suppress opposition.

**Buy attestation codes.** Pay people to attend events, get codes, and voice a specific way.

This is the hardest attack to prevent because it looks like legitimate participation — real people, real codes, real voices. It's also the oldest form of civic corruption (bussing supporters to public hearings). Defenses:

- This costs real money per voice: roughly $50-100 per person to recruit, transport, attend, and vote as directed
- At small scale, it's expensive per voice; at large scale (50+ paid participants), it's conspicuous
- Provenance signals help: if 30 newly-attested keys all voice identically on the same entity within hours, the pattern is visible even though each individual voice is legitimate
- Ultimately this is a social/legal problem, not a cryptographic one — it's the same as real-world paid testimony at public hearings, which is regulated by existing law

**Capture the relay operator.** Buy CivicOS or pressure it through funding.

Defense: Same as institutional capture above — legal structure, independent operators, commitment logs, open source. The more independent operators exist, the more expensive capture becomes (you'd need to buy them all).

**Run a compromised relay.** Set up a relay that selectively serves data to make an issue look more or less popular than it really is.

Defense: Commitment logs + cross-relay verification. The compromised relay's divergence from honest relays is detectable and provable by any client that checks more than one relay.

---

## Summary: Defense in Depth

No single mechanism solves all adversary models. The defense is layered:

```
Layer 1: CRYPTOGRAPHIC (what the math guarantees)
  ✓ Voices can't be forged (signature verification)
  ✓ Voices can't be modified (hash integrity)
  ✓ Attestations can't be forged (issuer signature)
  → Defends against: fabrication, modification, impersonation

Layer 2: STRUCTURAL (how the system is organized)
  ✓ Multiple independent relay operators
  ✓ Separation of relay operation from attestation issuance
  ✓ Open source, auditable code
  → Defends against: censorship, institutional capture, single points of control

Layer 3: COMMITMENT (what the relay provably commits to)
  ✓ Append-only commitment logs with merkle roots
  ✓ Cross-relay verification
  ✓ Signed, timestamped state snapshots
  → Defends against: silent censorship, equivocation, historical revision

Layer 4: SOCIAL/INSTITUTIONAL (how the organization is governed)
  ✓ Public interest legal structure
  ✓ Independent oversight
  ✓ Diverse attestation distribution channels
  ✓ Transparency reports
  → Defends against: institutional drift, funding pressure, capture

Layer 5: PRIVACY ARCHITECTURE (what no single party can see)
  ✓ Relay knows keys, not people
  ✓ Volunteers know faces, not keys
  ✓ No single subpoena deanonymizes a voice
  → Defends against: surveillance, targeted retaliation
```

### What's Solved vs. What's Open

**Solved by current architecture:**
- Voice fabrication and modification (cryptographic signatures)
- Voice attribution (key binding)
- Attestation forgery (issuer signature + 6-check verification)

**Solved by civicos-signer:**
- Issuer key separation — [`civicos-signer`](../packages/civicos-signer.md) enables organizations to hold their own attestation keys independently of the relay operator

**Solvable with known mechanisms (not yet built):**
- Silent censorship detection (commitment logs)
- Equivocation detection (cross-relay merkle root comparison)

**Fundamentally hard (social/institutional, not purely technical):**
- Paid real-person Sybil attacks (bussing supporters)
- Attestation distribution capture (infiltrating volunteer networks)
- Long-term institutional drift of CivicOS itself
- Balancing privacy (pseudonymous keys) with accountability (provenance signals)

The honest summary: the cryptographic architecture handles fabrication well. The open design questions are around omission, equivocation, and capture of the physical attestation layer. Commitment logs and operator independence are the primary defenses for the first two. The third is fundamentally a social and institutional design problem that cryptography can assist but not solve.

---

## See Also

- [Relay Trust Model](../relay/trust.md) — Operational reference for adversary defenses and commitment logs
- [Relay Federation](../relay/federation.md) — Cross-relay verification and multi-operator peering

---

## Questions to Explore

**On cardinality:**
- "At what scale does Tier 2 (operator + auditor) become insufficient? What triggers the move to Tier 3?"
- "How does the Nostr relay ecosystem handle the same cardinality questions today?"
- "What's the minimum viable auditor? How simple can the verification software be?"

**On commitment logs:**
- "Walk me through how Certificate Transparency works and how CivicOS's commitment logs would differ"
- "What happens if a relay publishes a commitment log entry and then later needs to accept a late-arriving federated voice? Does the append-only property break?"
- "How would commitment logs interact with voice revocations?"

**On adversary models:**
- "Compare the CivicOS privacy model to Tor's threat model. What's similar? What's different?"
- "How do existing civic engagement platforms (SeeClickFix, Change.org) handle the paid-supporter problem?"
- "What would a state-level actor's playbook look like against this system? Where would they attack?"

**On institutional integrity:**
- "What legal structures best protect against institutional capture? Compare 501(c)(3), benefit corporation, and cooperative models."
- "How does the separation of attestation issuance from relay operation compare to the separation of powers in government?"
- "What happens to the system if CivicOS ceases to exist? How do you ensure continuity?"
