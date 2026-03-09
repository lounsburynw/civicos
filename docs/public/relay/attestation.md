# Gated Attestation

Attestation is CivicOS's defense against spam, bot armies, and coordinated manipulation. It converts a digital problem (unlimited key generation) into a physical one (you must show up in person).

## The Problem

Generating a cryptographic key pair is free and instant. A single laptop can produce a million "citizens" in an hour. Without a gate, any coordination system is vulnerable to Sybil attacks — one entity pretending to be many.

```
The attack (without attestation):

1. Generate 10,000 key pairs          (< 1 second)
2. Sign 10,000 "support" voices       (< 1 second)
3. Send to relay                       (< 1 second)

Result: "10,023 residents support this initiative!"
Reality: 23 real people, 10,000 fake keys
```

This problem has gotten worse with autonomous AI agents, which can generate realistic engagement histories, produce human-sounding comments, and operate at scale for pennies.

## The Gate

CivicOS uses a hard gate: to voice or comment, you must present a valid attestation proof. No proof, no participation. Browsing, reading, and subscribing remain open to everyone.

To get attested, you must physically attend a community event (farmer's market, city council meeting, library pop-up) and receive a single-use code from a volunteer. The volunteer uses human judgment — "this is a person" — not bureaucratic verification. No government ID is checked. No name is recorded.

| Attack vector | Cost without gate | Cost with gate |
|---------------|-------------------|----------------|
| Generate 10,000 fake keys | Free | Irrelevant (no attestation = can't voice) |
| Build fake history over months | Automated | Irrelevant (history doesn't bypass gate) |
| Get 10,000 attestations | N/A | 10,000 physical appearances at events |

## How It Works

### Step 1: Community Event

A volunteer distributes single-use attestation codes — one per person. Codes are printed on cards or displayed as QR codes.

### Step 2: Redeem in Extension

The resident opens the CivicOS browser extension, enters the code, and clicks "Verify." The extension signs a Nostr event binding the code to the resident's public key.

### Step 3: Relay Issues Attestation

The relay checks:
- Code exists and hasn't been used
- Code hasn't expired
- This pubkey isn't already attested for this jurisdiction

If all checks pass, the relay signs a **kind 30850 Nostr event** — an attestation that this pubkey is verified for the jurisdiction.

### Step 4: Stored Locally

The signed attestation is stored in the browser's local storage. From then on, every voice and comment the resident submits includes this attestation as embedded proof.

## The Attestation Event

```json
{
  "kind": 30850,
  "pubkey": "jurisdiction_issuer_pubkey",
  "tags": [
    ["d", "attest:city-san-rafael:user_pubkey"],
    ["p", "user_pubkey"],
    ["j", "city-san-rafael"],
    ["type", "physical"]
  ],
  "content": "civicos:attestation:v1:city-san-rafael:physical:1739520000",
  "sig": "schnorr_signature_by_issuer"
}
```

Key observations:

1. **Signed by the issuer, not the user.** The `pubkey` field is the jurisdiction's issuer key. This is what makes it an authority-issued credential.
2. **Addressable.** The d-tag ensures one attestation per user per jurisdiction.
3. **Self-contained.** Any relay can verify the attestation by checking the issuer's signature — no database lookup required.

## Verification: The Six Checks

When a voice arrives at the relay with an attestation proof, the relay runs six checks:

| Check | Validates | Defends Against |
|-------|-----------|-----------------|
| **Kind** | Proof is a kind 30850 event | Attaching a random Nostr event as "proof" |
| **Issuer** | Signed by the jurisdiction's official issuer keypair | Self-attestation |
| **D-tag** | Matches `attest:{jurisdiction}:{your_pubkey}` | Using someone else's attestation |
| **Required tags** | Has `["p", your_pubkey]` and `["j", jurisdiction]` | Cross-jurisdiction or cross-user misuse |
| **Event ID** | Hash of event contents matches claimed ID | Post-signing tampering |
| **Schnorr signature** | Valid against the issuer's public key | Forgery |

## Why Embed, Not Look Up

The attestation proof is embedded *on* each voice, not looked up in a separate table. This is deliberate:

- **Self-contained** — The voice carries its own proof
- **Portable** — Works on any relay without database access
- **Fast reads** — No JOIN required
- **Federation-ready** — A receiving relay can verify independently

Think of it like a passport: you don't call the issuing country every time someone shows you their passport. The document itself is the proof.

## Multi-Issuer Attestation

Multiple independent organizations can be trusted issuers for a jurisdiction — each holding their own signing key via the [`civicos-signer`](../packages/civicos-signer.md) service. This separation of attestation authority from relay operation is built in from launch, not deferred to a future phase.

### How it works

Each trusted organization (civic group, library, city office) runs a `civicos-signer` instance that holds their private key. When a resident redeems a code that organization distributed, the relay calls the organization's signer to produce the attestation:

```
Resident redeems code → Relay looks up issuer → calls org's /sign endpoint → attestation signed by org's key
```

The attestation event's `pubkey` field identifies which organization vouched for the resident. The relay verifies attestations against a registry of trusted issuer pubkeys per jurisdiction.

### Attestation types

Different organizations may use different distribution methods. The `type` tag on the attestation event records the method:

| Type | Meaning | Example issuer |
|------|---------|----------------|
| `physical` | Resident attended an in-person event | Civic group at a farmer's market |
| `community-vouched` | Vouched for by a trusted community member | Social services organization |
| `mail` | Code delivered to a residential address | City clerk's office |

### Why this matters

Separating attestation authority from relay operation means:

- **No single point of trust.** CivicOS doesn't control who gets attested.
- **Smaller blast radius.** A compromised org key only affects that org's attestations.
- **Organizations use methods appropriate to their constituency.** A social services org uses community vouching; a city office uses mail; a civic group uses events.

## What Attestation Is Not

### Not identity verification

Attestation proves you physically attended a community event. It does not prove your name, address, citizenship, or residency status. This is deliberate — CivicOS is inclusive by design. The gate is "you're a real person who cares enough to show up," not "you can produce government ID."

### Not surveillance

The system has intentional privacy gaps:

- **The volunteer knows:** A person showed up and got a code. They don't know the person's key or how they vote.
- **The relay knows:** A key is attested. It doesn't know who the person is or where they got the code.
- **No single party knows** both who the person is and how they participate.

### Not foolproof

A determined person can get multiple codes across multiple events. This is acceptable noise — it doesn't scale. What gated attestation *does* prevent is the existential threat: bot armies, autonomous agents, and casual Sybil attacks.
