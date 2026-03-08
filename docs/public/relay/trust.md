# Relay Trust Model

How do you trust relay operators — including CivicOS itself — against adversaries? This document covers the threat model, defense layers, and what's solved versus what remains open.

## What a Relay Can and Cannot Do

Because voices are cryptographically signed by users, the relay's attack surface is narrower than in a typical distributed system:

**A malicious relay CAN:**
- Refuse to accept a voice (censorship at ingestion)
- Accept but not serve a voice (silent censorship)
- Report wrong counts (lie about totals while serving correct individual voices)
- Go offline (availability attack)
- Serve different data to different clients (equivocation)

**A malicious relay CANNOT:**
- Forge a voice (doesn't have users' private keys)
- Modify a voice (signature would break)
- Forge an attestation (doesn't have the issuer key)
- Attribute a voice to the wrong person (signature is bound to pubkey)

This means relay trust primarily defends against **omission and equivocation**, not fabrication.

## Adversary Model

Three classes of adversary, from most to least likely:

### 1. Institutional Drift

CivicOS itself gradually prioritizes its own survival — funding relationships, political convenience — over neutral relay operation. Not malice; incentive misalignment over time. This is the most important adversary to design against because CivicOS controls both the reference implementation and (during pilot) the only relay instance.

### 2. Government Pressure

A city government, state AG, or federal agency pressures relay operators to suppress, reveal, or manipulate civic coordination data.

### 3. Capital Interests

Developers, real estate companies, or industry groups attempt to inflate support or suppress opposition for specific civic decisions.

## Defense Layers

No single mechanism handles all adversaries. The defense is layered:

### Layer 1: Cryptographic (what the math guarantees)

- Voices can't be forged (signature verification)
- Voices can't be modified (hash integrity)
- Attestations can't be forged (issuer signature)

Defends against: fabrication, modification, impersonation.

### Layer 2: Structural (how the system is organized)

- Multiple independent relay operators
- Separation of relay operation from attestation issuance
- Open source, auditable code

Defends against: censorship, institutional capture, single points of control.

### Layer 3: Commitment (what the relay provably commits to)

- Append-only commitment logs with merkle roots
- Cross-relay verification
- Signed, timestamped state snapshots

Defends against: silent censorship, equivocation, historical revision.

### Layer 4: Social/Institutional (how the organization is governed)

- Public interest legal structure
- Independent oversight
- Diverse attestation distribution channels

Defends against: institutional drift, funding pressure, capture.

### Layer 5: Privacy Architecture (what no single party can see)

- Relay knows keys, not people
- Volunteers know faces, not keys
- No single subpoena deanonymizes a voice

Defends against: surveillance, targeted retaliation.

## Relay Cardinality

The number of relays matters less than the **independence of their operators**. Independence means different organizational leadership, different funding sources, different incentive structures.

### Deployment Tiers

**Tier 1: Single operator (pilot).** CivicOS runs the relay. Single point of failure and control. Acceptable because voices are self-verifying artifacts users could take to another relay later.

**Tier 2: Operator + auditor.** CivicOS runs the relay. One independent party (journalist, civic org, university) periodically pulls all voices and verifies signatures and counts independently. Silent censorship becomes detectable.

**Tier 3: Multiple independent operators.** Three or more relays for major jurisdictions, run by independent organizations (e.g., CivicOS + local newspaper + civic organization). Voices federate between them. Censorship requires collusion across organizations with different incentive structures.

**Tier 4: Permissionless operation.** Anyone can run a relay. Dozens exist for active jurisdictions. No practical censorship possible.

The jump from Tier 1 to Tier 2 is the most important transition. You don't need Tier 4 to launch — you need Tier 2 to be credible.

## Commitment Logs

Voice records are append-only — voice count for any entity should only go up, never down (except explicit signed revocations). This property enables **commitment logs**: periodic, signed cryptographic snapshots of relay state.

The relay publishes a merkle root over its complete voice set for each entity. Any client with the full voice list can recompute the root and verify it matches. If it doesn't, either the relay is lying or serving incomplete data.

| Attack | Without commitment log | With commitment log |
|--------|----------------------|---------------------|
| Silent censorship | Undetectable | Detectable — voice was in a previous root but absent now |
| Equivocation | Hard to detect | Clients compare merkle roots — disagreement is proof |
| Count inflation | Undetectable without enumeration | Root commits to exact set — inflated count doesn't match |
| Historical revision | Undetectable | Old commitments are signed and timestamped |

This is analogous to Certificate Transparency: force relays to commit to the exact set of voices they claim to have, so anyone can audit the commitment against the actual data.

## Specific Adversary Defenses

### Against government subpoena

Voice records are public and pseudonymous. The relay knows pubkeys, not people. No single subpoena target yields both real identity and full participation history — the government would need to compromise both an event volunteer (who knows faces but not keys) and the user's device (which has the key but not the person's name).

### Against censorship orders

Federation + commitment logs. If a voice exists on other relays, censoring one doesn't remove it. If the commitment log shows the voice was previously included and is now missing, the censorship is provably documented.

### Against paid supporter attacks (astroturfing)

The hardest attack to prevent because it uses real people with real attestation codes. Defenses are economic (costs ~$50-100 per paid voice, conspicuous at scale) and statistical (if 30 newly-attested keys all voice identically within hours, the pattern is visible). This is fundamentally the same problem as paid testimony at public hearings — a social/legal issue, not a purely technical one.

## What's Solved vs. What's Open

**Solved by current architecture:**
- Voice fabrication and modification (cryptographic signatures)
- Voice attribution (key binding)
- Attestation forgery (issuer signature + six-check verification)

**Solvable with known mechanisms (not yet built):**
- Silent censorship detection (commitment logs)
- Equivocation detection (cross-relay merkle root comparison)
- Issuer key separation (multisig or jurisdiction-held key)

**Fundamentally hard (social/institutional, not purely technical):**
- Paid real-person Sybil attacks
- Attestation distribution capture (infiltrating volunteer networks)
- Long-term institutional drift of CivicOS itself
