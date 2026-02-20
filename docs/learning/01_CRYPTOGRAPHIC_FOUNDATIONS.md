# Module 1: Cryptographic Foundations

*How keys, signatures, and identity work in CivicOS — from first principles.*

---

## The Problem We're Solving

Imagine you're at a city council meeting. Someone stands up and says: "I'm a San Rafael resident and I support the bike lane proposal." The council can see this person, hear their voice, judge whether they seem credible. Physical presence creates a natural layer of trust.

Now move this online. Someone types "I support the bike lane proposal" into a website. How does anyone know:

1. This is a real person, not a bot?
2. This is the same person who spoke last week, not an impersonator?
3. This person hasn't voted 50 times under different usernames?

Traditional platforms solve this with accounts — you create a username/password on Nextdoor or Facebook, and the platform vouches for your identity. But this creates a fundamental dependency: the platform controls your identity. They can ban you, sell your data, or shut down entirely. Your civic voice exists only at the platform's pleasure.

CivicOS takes a different approach: **you control your own identity using cryptographic keys.** No platform needed.

---

## What Is a Key?

A cryptographic key is just a very large number. That's it. Not a physical key, not a password — a number.

But it's a special kind of number. It comes in pairs:

```
Private key:  a very large secret number (256 bits — think 78 digits)
Public key:   a number mathematically derived from the private key
```

**The critical property:** You can go from private → public, but you cannot go from public → private. This is a one-way mathematical function.

### Analogy: Mailbox

Think of it like a mailbox with a slot:

- **Public key** = the mailbox address. Anyone can find it, anyone can drop a letter in.
- **Private key** = the key to the mailbox. Only you can open it and prove what's inside.

You freely share your public key (it's in your profile, on the relay, visible to everyone). You never share your private key (it stays on your device).

### Analogy: Wax Seal

A better analogy for how CivicOS uses keys is a wax seal on a letter:

- Your **private key** is the unique signet ring that only you possess.
- Your **public key** is the pattern the ring imprints in wax.
- Anyone who knows the pattern (public key) can verify a seal was made by your ring.
- But nobody can forge your ring just by looking at the wax pattern.

When you "voice" on a civic item, you're stamping it with your signet ring. Anyone can verify it's yours. Nobody can forge it.

---

## Digital Signatures

A digital signature is the mathematical version of a wax seal. Here's the intuition:

### What a Signature Proves

When you sign a message (like "I support the bike lane proposal"), the signature proves three things:

1. **Authentication** — This message came from the holder of this private key
2. **Integrity** — The message hasn't been tampered with since signing
3. **Non-repudiation** — The signer can't later deny signing it

### How It Works (Simplified)

```
Signing (you do this):
  message + private_key  →  [math magic]  →  signature

Verification (anyone can do this):
  message + public_key + signature  →  [math magic]  →  true/false
```

The "math magic" is based on elliptic curve mathematics. You don't need to understand the math — just the properties:

- Only the private key holder can produce a valid signature
- Anyone with the public key can verify the signature
- The signature is tied to the exact message — change one character and verification fails
- The signature doesn't reveal the private key

### Analogy: Signing a Check

When you sign a physical check:
- Your handwritten signature is hard to forge (authentication)
- If someone alters the amount, the bank can tell (integrity... in theory)
- You can't say "that wasn't me" if it matches your signature on file (non-repudiation)

A digital signature does all of this, except it's mathematically impossible to forge rather than merely difficult. And it's tied to the exact content — change one character and it's invalid.

---

## The Specific Curve: secp256k1

CivicOS uses a specific mathematical curve called **secp256k1** with **Schnorr signatures** (BIP-340). This is the same cryptography Bitcoin and Nostr use.

Why this matters for you:

- **It's battle-tested.** Billions of dollars depend on this cryptography working correctly.
- **Ecosystem compatibility.** Your CivicOS key works with any Nostr client (Damus, Primal, etc.).
- **Schnorr specifically** (vs. older ECDSA) has nice properties: simpler, faster, and supports signature aggregation.

### Key Format

In CivicOS, keys look like this:

```
Private key (secret!): 64 hex characters
  e.g., 3f7a8b2c... (never shown in full)

Public key (shareable): 64 hex characters
  e.g., a1b2c3d4e5f6...

Nostr format (npub): human-readable encoding of the public key
  e.g., npub1q7k3m5x...
```

The hex format and npub format represent the same key — just different encodings, like how "255" and "FF" both represent the same number in decimal and hexadecimal.

---

## How CivicOS Uses Keys

### Your Identity IS Your Key

In CivicOS, your public key is your identity. There's no username, no email, no account. Just a key.

```
Traditional platform:
  You → create account → platform assigns identity → platform can revoke

CivicOS:
  You → generate key pair → YOUR key IS your identity → nobody can revoke
```

This is a fundamental shift. Your identity is a mathematical object you control, not a row in someone else's database.

### What Your Key Does

| Action | What Happens Cryptographically |
|--------|-------------------------------|
| Voice on an item | You sign "I support entity:bike-lane" with your private key |
| Comment on a decision | You sign your comment text with your private key |
| Revoke a voice | You sign a revocation message with your private key |

Every action is a signed message. The relay can verify every action came from you. Nobody can forge an action as you.

### One Key, One Voice Per Entity

The relay enforces: one voice per public key per entity. This is how we prevent double-voting.

```
Public key A voices "support" on bike-lane     ✓ accepted
Public key A voices "support" on bike-lane     ✗ duplicate (same key, same entity)
Public key A voices "oppose" on housing-plan   ✓ different entity, accepted
Public key B voices "support" on bike-lane     ✓ different key, accepted
```

### Where Your Key Lives

Your private key lives in your browser's local storage (in the CivicOS extension). It never leaves your device. It's never sent to a server.

```
Your device:
  localStorage → private key (encrypted)
                 ↓
  Extension signs messages locally
                 ↓
  Only the signed message is sent to the relay
                 ↓
The relay never sees your private key
```

---

## Hashing: The Other Foundational Concept

A hash function takes any input and produces a fixed-size output (a "digest"). Think of it as a fingerprint for data.

```
hash("Hello, world!")        → 315f5bdb76d078c43b8ac0064e4a0164612b1fce77c869345bfc94c75894edd3
hash("Hello, world!!")       → completely different hash
hash(entire Bible text)      → still just 64 hex characters
```

**Properties:**
- Same input always produces the same hash
- Tiny change in input → completely different hash
- Can't reverse a hash back to the original input
- Virtually impossible for two different inputs to produce the same hash

### How CivicOS Uses Hashes

**Event IDs.** Every Nostr event (voice, comment, attestation) has an ID that's a hash of its contents:

```
event_id = hash(
  pubkey + created_at + kind + tags + content
)
```

This means:
- The event ID is uniquely determined by the event contents
- Changing anything in the event changes the ID
- You can verify an event hasn't been tampered with by recomputing its hash

**Attestation verification.** When verifying an attestation proof (we'll cover this in Module 3), one of the six checks is recomputing the event ID and confirming it matches. This ensures the attestation hasn't been modified since the issuer signed it.

---

## Putting It All Together: A Voice in CivicOS

Let's trace what happens when you tap "Support" on a civic item:

```
1. YOUR DEVICE (browser extension)

   Message to sign:
     entity: "decision:city-san-rafael:2026-02-03:item-6a"
     stance: "support"
     kind: 30800 (civic voice)
     jurisdiction: "city-san-rafael"
     created_at: 1738464000 (Unix timestamp)
     attestation_proof: { ... kind 30850 event ... }

   Your private key signs this message → produces signature (64 bytes)

   Event ID = hash(all the above fields)

2. SENT TO RELAY

   The relay receives:
     - Your public key
     - The message
     - The signature
     - The attestation proof

3. RELAY VERIFIES

   a. Is the signature valid? (Schnorr verify: pubkey + message + sig)
   b. Is the attestation proof valid? (6 checks — see Module 3)
   c. Has this key already voiced on this entity? (dedup check)

   All pass → voice accepted and stored
   Any fail → rejected with error code

4. ANYONE CAN VERIFY LATER

   The stored voice is a self-contained, signed artifact.
   Any relay, any client, any auditor can independently verify:
   - The signature proves it came from this key
   - The attestation proves this key belongs to a real community member
   - The event ID proves nothing was tampered with
```

---

## Why This Matters for Civic Participation

### Comparison With Traditional Platforms

| Property | Nextdoor/Facebook | CivicOS |
|----------|------------------|---------|
| Who controls your identity? | Platform | You |
| Can you be banned? | Yes, at platform discretion | No — your key is yours |
| Can your data be sold? | Yes | No data to sell (keys + signed messages only) |
| Can you move to another provider? | No (platform lock-in) | Yes (key works on any relay) |
| Can you prove a message is yours? | Platform vouches for you | Mathematical proof via signature |
| Can someone forge a message as you? | If they hack the platform, yes | Only if they steal your private key |
| What happens if the platform dies? | Your identity and history are gone | Your key still works, your signed messages are still valid |

### The Core Insight

Traditional platforms are **trusted intermediaries**: "Trust us, this message came from user123." If the platform is compromised, dishonest, or disappears, that trust evaporates.

CivicOS is **trustless verification**: "Here's a mathematical proof this message came from this key." No trust in any intermediary required. The math either checks out or it doesn't.

This is what "protocol over platform" means in practice. The cryptography IS the trust layer.

---

## Concepts to Carry Forward

For Module 2 (The Nostr Protocol), you'll need:

- **Key pair** — private (secret) + public (shareable), mathematically linked
- **Signature** — proof that a message was created by a specific private key holder
- **Hash** — fingerprint of data, used for event IDs and integrity checks
- **secp256k1/Schnorr** — the specific curve and signature scheme (Bitcoin/Nostr standard)
- **Self-verifying** — signed messages can be verified by anyone, no intermediary needed

For Module 3 (Attestation & the CivicOS System), you'll need all of the above plus:

- The distinction between **what you sign** (your civic voice) and **what someone signs about you** (an attestation that you're a real community member)
- The idea that signed artifacts are **portable** — they work on any relay, not just the one that first received them
