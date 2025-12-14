# Privacy-First Personalization Architecture

**Status**: Proposed (Session 40 - 2025-10-29)
**Priority**: Critical - Must implement before storing any political data
**Author**: Privacy-first design discussion

---

## 🎯 Core Principle

**Users own their political values. We never store them in plaintext.**

Foundation-funded civic infrastructure should maximize privacy while enabling personalization. This document defines three privacy tiers users can choose from, with full disclosure of trade-offs.

---

## 🚨 Threat Model

### Risks of Centralized Political Data Storage

1. **Government Subpoenas**
   - Local/state/federal government requests user political preferences
   - Court orders to reveal civic interests
   - National security letters (NSL) with gag orders

2. **Data Breaches**
   - Hackers access database with political values
   - Insider threats (rogue employees)
   - Third-party vendor compromises

3. **Political Targeting**
   - Discrimination based on civic interests
   - Opposition research mining
   - Micro-targeted manipulation

4. **Chilling Effects**
   - Users self-censor knowing data is centralized
   - Reduced civic participation due to surveillance concerns
   - Marginalized communities disproportionately impacted

5. **Platform Abuse**
   - Future owners change terms of service
   - Acquisition by political entities
   - Mission drift away from civic mission

6. **Foreign Adversaries**
   - Nation-state access to civic organizing data
   - Identification of political activists
   - Social graph analysis

### Attack Surface

```
Current Plan (REJECTED):
┌─────────────────────────────────────┐
│ Backend Database (SQLite)          │
│ - user_profiles.civic_interests    │  ← VULNERABLE TO SUBPOENA
│ - onboarding_swipes (all decisions)│  ← SURVEILLANCE READY
│ - inferred_interests               │  ← CHILLING EFFECT
└─────────────────────────────────────┘

Privacy-First Architecture (THIS DOC):
┌─────────────────────────────────────┐
│ User's Browser (localStorage)       │  ← USER CONTROLLED
│ - Civic archetypes (never sent)     │  ← NO CENTRAL STORAGE
│ - Political values (local only)     │  ← ZERO SUBPOENA RISK
└─────────────────────────────────────┘
         ↓ (Optional encrypted sync)
┌─────────────────────────────────────┐
│ Backend Database                    │
│ - Encrypted blobs (can't decrypt)  │  ← WE CAN'T READ IT
│ - User controls keys                │  ← PLAUSIBLE DENIABILITY
└─────────────────────────────────────┘
```

---

## 🎭 Archetype-Based Personalization

### Why Archetypes?

Instead of storing granular political values ("supports AB-1482, opposes SB-827"), users match to **civic archetypes** that represent coherent political identities.

**Benefits:**
1. **Privacy through abstraction** - Less revealing than raw values
2. **Easier to understand** - "Housing Champion" vs "civic_interests: ['housing', 'zoning', 'affordability']"
3. **More stable** - Archetypes don't change as often as specific positions
4. **Community formation** - Natural grouping mechanism
5. **Compression** - 10 interests → 2-3 archetypes

### Civic Archetype Definitions (v1.0)

**Core Archetypes (12 total)**

| Archetype | Focus Areas | Example Positions |
|-----------|-------------|-------------------|
| **🏠 Housing Champion** | Affordable housing, tenant rights, zoning reform | Pro-housing density, anti-displacement, ADU supporter |
| **🚇 Transit Advocate** | Public transit, bike infrastructure, walkability | Car-free streets, BRT expansion, bike lane networks |
| **🌳 Environmental Steward** | Climate action, sustainability, green infrastructure | Carbon neutrality, renewable energy, tree preservation |
| **💰 Fiscal Conservative** | Budget oversight, tax policy, government efficiency | Cost-benefit analysis, debt reduction, service optimization |
| **🎨 Community Builder** | Arts, culture, public spaces, social programs | Library funding, community centers, public art |
| **🚨 Safety First** | Public safety, emergency services, crime prevention | Police staffing, fire response times, 911 modernization |
| **📚 Education Advocate** | Schools, youth programs, libraries | Teacher pay, school facilities, early childhood education |
| **🏪 Small Business Booster** | Local economy, business development | Fee reductions, permitting reform, downtown revitalization |
| **👁️ Government Watchdog** | Transparency, accountability, electoral integrity | Open data, conflict of interest rules, campaign finance reform |
| **🏘️ Neighborhood Protector** | Local character, traffic calming, quality of life | Historic preservation, parking policy, noise ordinances |
| **⚖️ Justice Reformer** | Criminal justice, police accountability, equity | Restorative justice, oversight boards, decriminalization |
| **🌍 Regional Thinker** | Cross-jurisdictional issues, regional planning | Transit connections, housing markets, environmental watersheds |

**Archetype Matching Algorithm:**
- Users swipe on 15-20 civic decision cards
- Client-side scoring across all archetypes
- Return top 2-3 archetypes (primary, secondary, tertiary)
- Scores weighted by topic overlap (e.g., housing cards boost Housing Champion score)

**Example User:**
```json
{
  "archetypes": [
    { "id": "housing_champion", "score": 0.85, "rank": 1 },
    { "id": "transit_advocate", "score": 0.72, "rank": 2 },
    { "id": "environmental_steward", "score": 0.65, "rank": 3 }
  ]
}
```

---

## 🛡️ Three Privacy Tiers (User Choice)

### **Tier 1: Browser-Only Storage** ⭐⭐⭐⭐⭐ Privacy

**Architecture:**
```
[User's Browser]
  └── localStorage
      ├── civic-archetypes: [{id, score, rank}]
      ├── civic-profile: {name, jurisdiction, stakes}
      └── civic-key: (optional encryption key)

[Backend Database]
  └── NOTHING (zero political data storage)
```

**How it works:**
1. User completes Values Explorer (swipe cards)
2. Client-side JavaScript matches to archetypes
3. Archetypes stored in browser localStorage only
4. Event recommendations computed client-side
5. Profile export/import for backup/transfer

**Privacy guarantees:**
- ✅ Zero centralized storage of political values
- ✅ No subpoena risk (data doesn't exist on server)
- ✅ No breach risk (no data to steal)
- ✅ Complete user control (localStorage = user's device)

**Trade-offs:**
- ❌ No cross-device sync
- ❌ Lost if browser cache cleared (unless exported)
- ❌ Can't pre-compute recommendations server-side

**User disclosure:**
```
Your political values stay on THIS DEVICE ONLY.

✅ We CANNOT see your values (they never leave your browser)
✅ No government can subpoena your data (it doesn't exist on our servers)
✅ You own your data (export anytime as JSON file)

⚠️  Clear your browser? You'll lose your profile (export to backup)
⚠️  Use multiple devices? Import your profile on each one
```

---

### **Tier 2: Encrypted Cloud Sync** ⭐⭐⭐⭐ Privacy + ⭐⭐⭐⭐ Convenience

**Architecture:**
```
[User's Browser]
  └── localStorage
      ├── civic-archetypes: [{id, score, rank}]  (plaintext locally)
      ├── civic-profile: {name, jurisdiction}
      └── civic-encryption-key: <AES-256-GCM key>  (NEVER SENT)

          ↓ Encrypt client-side

[Backend Database]
  └── encrypted_user_data
      ├── user_id: <anonymous_id>
      ├── encrypted_blob: <base64(AES-encrypted archetypes)>
      ├── iv: <initialization vector>
      └── created_at: <timestamp>
```

**How it works:**
1. User generates encryption key in browser (Web Crypto API)
2. Key stored in localStorage (never sent to server)
3. Archetypes encrypted client-side before upload
4. Backend stores encrypted blob (cannot decrypt without user's key)
5. On new device: User imports their encryption key → decrypts blob

**Encryption specs:**
- Algorithm: AES-256-GCM (authenticated encryption)
- Key generation: `crypto.subtle.generateKey()` (Web Crypto API)
- Key storage: Browser localStorage (user-controlled)
- IV: Random 12-byte initialization vector per encryption
- Key export: JWK format for user backup

**Privacy guarantees:**
- ✅ Backend cannot decrypt (doesn't have key)
- ✅ Data breach reveals encrypted blobs (useless without keys)
- ✅ Subpoena reveals encrypted data (we can't decrypt)
- ✅ Users can prove "we can't read your data" (verifiable encryption)

**Trade-offs:**
- ⚠️ User loses key = loses data (key management responsibility)
- ⚠️ Slightly more complex UX (key backup/restore)
- ✅ Cross-device sync (with key)
- ✅ Survives browser cache clearing (if key backed up)

**User disclosure:**
```
Your political values are encrypted before cloud sync.

✅ Only YOU have the decryption key (we can't read your data)
✅ Cross-device sync (import your key on each device)
✅ Government subpoenas reveal encrypted data (we can't decrypt)

⚠️  CRITICAL: Back up your encryption key! If you lose it, we CANNOT recover your data.
⚠️  You are responsible for key security (treat like a password)

[Download Encryption Key] ← BACKUP THIS FILE
```

---

### **Tier 3: Zero-Knowledge Archetypes** ⭐⭐⭐⭐⭐ Privacy + ⭐⭐⭐⭐⭐ Community

**Architecture:**
```
[User's Browser]
  └── Generates zero-knowledge proofs
      ├── Proof: "I have archetype X" (without revealing X)
      ├── Public commitment: hash(archetype + salt)
      └── Private witness: archetype value

          ↓ Submit ZK proof

[Backend Database]
  └── archetype_commitments
      ├── user_id: <anonymous_id>
      ├── archetype_hash: <hash(archetype + salt)>
      ├── zk_proof: <cryptographic proof>
      └── verified: true

[Smart Matching]
  └── Find users with same archetype_hash
      ├── WITHOUT knowing which archetype
      ├── WITHOUT knowing who the users are
      └── Enable community formation without surveillance
```

**How it works:**
1. User generates archetype commitment: `hash(archetype + random_salt)`
2. Backend stores commitment hash (can't reverse to find archetype)
3. User generates ZK proof: "I know the value that hashes to this commitment"
4. Backend verifies proof without learning the archetype
5. Users with same archetype_hash can find each other
6. Community formation without platform surveillance

**Zero-Knowledge Proof Specs:**
- Protocol: Schnorr signatures or zk-SNARKs (circom)
- Statement: "I know archetype X such that hash(X + salt) = commitment"
- Proof size: ~200 bytes (Schnorr) or ~288 bytes (zk-SNARK)
- Verification: O(1) constant time
- Libraries: `snarkjs` (zk-SNARKs) or `noble-curves` (Schnorr)

**Privacy guarantees:**
- ✅ Platform cannot determine user's archetypes
- ✅ Users can prove membership without revealing identity
- ✅ Community matching without surveillance
- ✅ Cryptographically verifiable ("we provably can't know")

**Trade-offs:**
- ⚠️ Complex implementation (8-12 hours)
- ⚠️ Requires specialized crypto libraries
- ⚠️ Higher cognitive load for users (most advanced option)
- ✅ Maximum privacy with community features
- ✅ Future-proof for privacy regulations

**User disclosure:**
```
Your political values are cryptographically hidden.

✅ We CANNOT determine your archetypes (cryptographic guarantee)
✅ Find others who share your values (without revealing who you are)
✅ Prove membership in groups (without identity disclosure)
✅ Mathematical proof we can't surveil you (zero-knowledge proofs)

⚠️  Most advanced option (for privacy experts)
⚠️  Requires understanding of cryptographic concepts

This uses zero-knowledge proofs (the same tech as Zcash/zkSync).
```

---

## 📊 Privacy Tier Comparison

| Feature | Tier 1: Browser-Only | Tier 2: Encrypted Sync | Tier 3: Zero-Knowledge |
|---------|---------------------|------------------------|------------------------|
| **Political data storage** | None | Encrypted blob | Cryptographic commitment |
| **Subpoena risk** | Zero | Low (can't decrypt) | Zero (provably unknowable) |
| **Breach risk** | Zero | Low (encrypted) | Zero (no data to steal) |
| **Cross-device sync** | Manual (export/import) | Yes (with key) | Yes (with proof) |
| **Community features** | Limited | Limited | Full |
| **Implementation complexity** | Low (1 hour) | Medium (2-3 hours) | High (8-12 hours) |
| **User cognitive load** | Low | Medium | High |
| **Backend storage** | 0 bytes | ~500 bytes/user | ~200 bytes/user |
| **Regulatory compliance** | GDPR native | GDPR compliant | GDPR native |
| **Plausible deniability** | Yes (no data exists) | Yes (can't decrypt) | Yes (mathematical proof) |

---

## 🎛️ User Choice Framework

### Default Recommendation: **Tier 1 (Browser-Only)**

**Why?**
- Simplest for users
- Maximum privacy
- Zero implementation complexity
- Aligns with foundation values

### When to offer Tier 2?
- User explicitly requests cross-device sync
- User understands key management
- User has exported their encryption key

### When to offer Tier 3?
- User wants community features
- User is privacy-conscious and tech-savvy
- Platform has implemented ZK infrastructure

### Choice UI (in ProfileForm after Values Explorer)

```
┌────────────────────────────────────────────────────────┐
│  How should we store your political values?           │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ⭐ This Device Only (Recommended)                    │
│  Your values stay in your browser. Maximum privacy.   │
│  ✅ We can't see your data                            │
│  ✅ No subpoena risk                                  │
│  ⚠️  No cross-device sync (export to backup)         │
│                                                        │
│  [Select This Device Only]                            │
│                                                        │
├────────────────────────────────────────────────────────┤
│                                                        │
│  🔐 Encrypted Cloud Sync (Advanced)                  │
│  We store encrypted copy. Only you have the key.      │
│  ✅ Cross-device sync                                 │
│  ✅ We can't decrypt your data                        │
│  ⚠️  You must back up your encryption key            │
│                                                        │
│  [Enable Encrypted Sync]                              │
│                                                        │
├────────────────────────────────────────────────────────┤
│                                                        │
│  🧮 Zero-Knowledge (Expert)                           │
│  Cryptographic privacy with community features.       │
│  ✅ Mathematically proven we can't know your values   │
│  ✅ Find others with shared values anonymously        │
│  ⚠️  Most complex option (crypto knowledge helpful)   │
│                                                        │
│  [Enable Zero-Knowledge] (Coming Soon)                │
│                                                        │
└────────────────────────────────────────────────────────┘

📖 Why does this matter?
Your political values are sensitive. We believe you should
control where they're stored and who can access them.

[Learn More About Privacy Options]
```

---

## 🏗️ Implementation Roadmap

### Phase 1: Browser-Only (MVP - 1-2 hours)

**Tasks:**
1. Implement client-side archetype matching algorithm
2. Store archetypes in localStorage
3. Add export/import buttons to ProfilePanel
4. Update event filtering to use archetypes
5. Remove all backend political storage

**Files:**
- `frontend/civic-workspace/src/stores/profile.ts` - Add archetype storage
- `frontend/civic-workspace/src/components/onboarding/SwipeOnboarding.vue` - Client-side matching
- `frontend/civic-workspace/src/components/sidebar/ProfilePanel.vue` - Export/import UI

**Backend changes:**
- Remove: `user_profiles.civic_interests`
- Remove: `onboarding_swipes` table
- Remove: `/api/onboarding/swipe` endpoint

---

### Phase 2: Encrypted Sync (Optional - 2-3 hours)

**Tasks:**
1. Implement Web Crypto API encryption
2. Add key generation and storage
3. Create encrypted blob endpoints
4. Build key backup/restore UI
5. Add opt-in choice during profile creation

**Files:**
- `frontend/civic-workspace/src/utils/encryption.ts` - Crypto utilities
- `src/civic_api_integrated.py` - Encrypted blob endpoints
- `migrations/007_encrypted_user_data.sql` - New table

**New endpoints:**
- `POST /api/user/encrypted-archetypes` - Save encrypted blob
- `GET /api/user/encrypted-archetypes` - Retrieve encrypted blob

---

### Phase 3: Zero-Knowledge (Future - 8-12 hours)

**Tasks:**
1. Research ZK proof libraries (snarkjs vs Schnorr)
2. Implement proof generation client-side
3. Implement proof verification backend
4. Build community matching with ZK proofs
5. Add expert-mode UI

**Files:**
- `frontend/civic-workspace/src/utils/zkproofs.ts` - ZK proof generation
- `src/zk_verification.py` - Proof verification (new module)
- `migrations/008_zk_commitments.sql` - Commitment storage

**New endpoints:**
- `POST /api/archetypes/commit` - Submit archetype commitment
- `POST /api/archetypes/prove` - Verify ZK proof
- `GET /api/archetypes/find-matches` - ZK-based matching

---

## 📐 Archetype Matching Algorithm (Client-Side)

```typescript
// File: frontend/civic-workspace/src/utils/archetypeMatching.ts

interface SwipeResult {
  card_id: string
  card_type: 'topic' | 'event'
  direction: 'left' | 'right'
  metadata: {
    topic?: string
    project_type?: string
    jurisdiction?: string
  }
}

interface Archetype {
  id: string
  name: string
  topics: string[]
  weights: Record<string, number> // topic → weight mapping
}

// Archetype definitions with topic weights
const ARCHETYPES: Archetype[] = [
  {
    id: 'housing_champion',
    name: 'Housing Champion',
    topics: ['housing', 'development', 'zoning'],
    weights: {
      'housing': 1.0,
      'development': 0.6,
      'budget': 0.3,
      'community': 0.4
    }
  },
  {
    id: 'transit_advocate',
    name: 'Transit Advocate',
    topics: ['transportation', 'environment', 'development'],
    weights: {
      'transportation': 1.0,
      'environment': 0.5,
      'budget': 0.3
    }
  },
  {
    id: 'environmental_steward',
    name: 'Environmental Steward',
    topics: ['environment', 'transportation', 'development'],
    weights: {
      'environment': 1.0,
      'transportation': 0.4,
      'development': 0.3
    }
  },
  // ... other archetypes
]

export function matchToArchetypes(
  swipes: SwipeResult[],
  topN: number = 3
): ArchetypeMatch[] {
  // Calculate scores for each archetype
  const scores: Record<string, number> = {}

  ARCHETYPES.forEach(archetype => {
    scores[archetype.id] = 0
  })

  // Process right-swipes only (liked cards)
  const likedSwipes = swipes.filter(s => s.direction === 'right')

  likedSwipes.forEach(swipe => {
    const topic = swipe.metadata.project_type || swipe.metadata.topic
    if (!topic) return

    // Add weighted scores to archetypes
    ARCHETYPES.forEach(archetype => {
      const weight = archetype.weights[topic] || 0
      scores[archetype.id] += weight
    })
  })

  // Normalize scores (0-1 range)
  const maxScore = Math.max(...Object.values(scores))
  if (maxScore > 0) {
    Object.keys(scores).forEach(id => {
      scores[id] = scores[id] / maxScore
    })
  }

  // Return top N archetypes
  return Object.entries(scores)
    .map(([id, score]) => ({
      id,
      name: ARCHETYPES.find(a => a.id === id)?.name || id,
      score,
      rank: 0
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topN)
    .map((match, index) => ({
      ...match,
      rank: index + 1
    }))
}

// Store archetypes in localStorage
export function saveArchetypesToBrowser(archetypes: ArchetypeMatch[]): void {
  localStorage.setItem('civic-archetypes', JSON.stringify(archetypes))
  localStorage.setItem('civic-archetypes-updated', new Date().toISOString())
}

// Load archetypes from localStorage
export function loadArchetypesFromBrowser(): ArchetypeMatch[] | null {
  const stored = localStorage.getItem('civic-archetypes')
  return stored ? JSON.parse(stored) : null
}

// Export profile for backup
export function exportProfile(): Blob {
  const data = {
    version: '1.0',
    exported_at: new Date().toISOString(),
    archetypes: loadArchetypesFromBrowser(),
    profile: JSON.parse(localStorage.getItem('civic-profile') || '{}')
  }

  return new Blob(
    [JSON.stringify(data, null, 2)],
    { type: 'application/json' }
  )
}

// Import profile from backup
export function importProfile(json: string): void {
  const data = JSON.parse(json)

  if (data.archetypes) {
    saveArchetypesToBrowser(data.archetypes)
  }

  if (data.profile) {
    localStorage.setItem('civic-profile', JSON.stringify(data.profile))
  }
}
```

---

## 🔒 Encryption Implementation (Tier 2)

```typescript
// File: frontend/civic-workspace/src/utils/encryption.ts

// Generate user's encryption key
export async function generateEncryptionKey(): Promise<CryptoKey> {
  return await crypto.subtle.generateKey(
    {
      name: 'AES-GCM',
      length: 256
    },
    true, // extractable
    ['encrypt', 'decrypt']
  )
}

// Export key for backup
export async function exportKey(key: CryptoKey): Promise<string> {
  const exported = await crypto.subtle.exportKey('jwk', key)
  return JSON.stringify(exported)
}

// Import key from backup
export async function importKey(jwkString: string): Promise<CryptoKey> {
  const jwk = JSON.parse(jwkString)
  return await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt']
  )
}

// Encrypt data
export async function encryptData(
  plaintext: string,
  key: CryptoKey
): Promise<{ encrypted: string, iv: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const encoded = new TextEncoder().encode(plaintext)

  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoded
  )

  return {
    encrypted: arrayBufferToBase64(encrypted),
    iv: arrayBufferToBase64(iv)
  }
}

// Decrypt data
export async function decryptData(
  encrypted: string,
  iv: string,
  key: CryptoKey
): Promise<string> {
  const decrypted = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: base64ToArrayBuffer(iv)
    },
    key,
    base64ToArrayBuffer(encrypted)
  )

  return new TextDecoder().decode(decrypted)
}

// Helper: ArrayBuffer to Base64
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  const binary = String.fromCharCode(...bytes)
  return btoa(binary)
}

// Helper: Base64 to ArrayBuffer
function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

// Store key in localStorage
export function saveKeyToLocalStorage(key: string): void {
  localStorage.setItem('civic-encryption-key', key)
  console.warn('[Security] Encryption key stored in localStorage. Back it up!')
}

// Load key from localStorage
export function loadKeyFromLocalStorage(): string | null {
  return localStorage.getItem('civic-encryption-key')
}
```

---

## 📜 Privacy Disclosure (User-Facing)

### Full Disclosure Page (linked from profile creation)

```markdown
# How We Handle Your Political Values

## Our Privacy Commitment

**We believe your political values are YOUR data, not ours.**

This page explains exactly how we store (or don't store) your civic
interests, archetypes, and political preferences.

---

## What Data Are We Talking About?

When you complete the "Values Explorer" (swiping on civic decisions),
we learn about:

- Which civic topics you care about (housing, transit, environment, etc.)
- Your political archetypes (e.g., "Housing Champion", "Transit Advocate")
- Your preferences on specific civic issues

**This data is politically sensitive and could be misused.**

---

## Three Storage Options (You Choose)

### Option 1: This Device Only (Recommended) ⭐

**How it works:**
- Your values are stored in your browser's localStorage
- They NEVER leave your device
- We CANNOT see them
- No government can subpoena them (they don't exist on our servers)

**Privacy:**
- 🔒 Maximum privacy
- 🔒 Zero surveillance risk
- 🔒 No data breach risk

**Trade-offs:**
- ⚠️ Lost if you clear your browser cache (unless you export first)
- ⚠️ No cross-device sync (export/import on each device)

**What can we see?**
- NOTHING. Your political values never reach our servers.

**What data exists on our servers?**
- None related to your political values.
- We DO store: your submitted comments (public record),
  issues you filed (you chose to share), meetings you attended
  (optional check-in).

---

### Option 2: Encrypted Cloud Sync (Advanced) 🔐

**How it works:**
- Your browser generates an encryption key (never sent to us)
- Your values are encrypted in your browser
- We store the encrypted blob (can't read it)
- You sync across devices by importing your key

**Privacy:**
- 🔒 High privacy (we can't decrypt)
- 🔒 Low surveillance risk (encrypted at rest)
- 🔒 Medium data breach risk (encrypted, but blob exists)

**Trade-offs:**
- ✅ Cross-device sync
- ⚠️ You MUST back up your encryption key (we can't recover it)
- ⚠️ If you lose your key, your data is GONE

**What can we see?**
- Encrypted blob (looks like random bytes to us)
- We cannot decrypt without your key

**What if the government subpoenas your data?**
- We provide encrypted blob (useless without your key)
- We cannot decrypt it (we don't have your key)
- You can verify this (encryption is client-side)

**What if there's a data breach?**
- Hackers get encrypted blobs
- Useless without users' encryption keys
- Keys never leave browsers

---

### Option 3: Zero-Knowledge (Expert) 🧮

**How it works:**
- Your browser generates cryptographic commitments
- You prove you have an archetype without revealing which one
- We verify proofs without learning your values
- Community matching without surveillance

**Privacy:**
- 🔒 Maximum privacy (mathematically proven)
- 🔒 Zero surveillance (we provably cannot know)
- 🔒 Zero data breach risk (no values stored)

**Trade-offs:**
- ✅ Community features (find others anonymously)
- ⚠️ Most complex option (requires crypto understanding)
- ⚠️ Experimental (cutting-edge privacy tech)

**What can we see?**
- Cryptographic commitments (hash values)
- Cannot reverse to find your archetypes
- Mathematically impossible to determine your values

**How do you verify this?**
- Zero-knowledge proofs are public
- You can audit the cryptography
- Same tech as Zcash (privacy cryptocurrency)

---

## Frequently Asked Questions

**Q: Why don't you just store everything like other platforms?**

A: Because we're foundation-funded civic infrastructure, not
   a surveillance company. Your political values should be
   YOUR data, not ours.

**Q: But don't you need my data to recommend events?**

A: We can recommend events using your archetypes stored in
   YOUR browser. No centralized storage needed.

**Q: What if I want to switch from Option 1 to Option 2?**

A: You can upgrade anytime. Export your data from Option 1,
   generate an encryption key, encrypt and upload.

**Q: Can I audit your code?**

A: Yes! We're open source. Check our GitHub repo.

**Q: What if I don't trust you?**

A: Good! Use Option 1 (browser-only). Then you don't have to
   trust us because your data never reaches our servers.

**Q: Do other civic platforms do this?**

A: No. Most store political data in plaintext. We think
   that's dangerous for democracy.

**Q: Is this legal/compliant with GDPR?**

A: Yes. In fact, Option 1 is GDPR-native (no data to regulate).
   Option 2 & 3 are GDPR-compliant.

**Q: What about law enforcement requests?**

A: Option 1: We have no data to provide.
   Option 2: We provide encrypted blobs (can't decrypt).
   Option 3: We provide commitments (can't reverse).

---

## Our Promise

1. We will NEVER store political values in plaintext
2. We will ALWAYS give you choice in how data is stored
3. We will ALWAYS be transparent about what we can/can't see
4. We will ALWAYS prioritize your privacy over our convenience

**Questions?** privacy@civic-platform.org

**Read the code:** github.com/your-org/civic-platform

---

Last updated: 2025-10-29
```

---

## ✅ Success Criteria

### Phase 1 (Browser-Only) Complete When:
- [ ] Archetype matching works client-side
- [ ] Archetypes stored in localStorage
- [ ] Export/import functionality works
- [ ] No political data sent to backend
- [ ] User disclosure shown during profile creation
- [ ] Event filtering uses local archetypes

### Phase 2 (Encrypted Sync) Complete When:
- [ ] Encryption key generation works
- [ ] Client-side encryption functional
- [ ] Encrypted blob storage endpoint exists
- [ ] Key backup/restore UI works
- [ ] Users can opt-in during profile creation
- [ ] Decryption works on new devices

### Phase 3 (Zero-Knowledge) Complete When:
- [ ] ZK proof generation works client-side
- [ ] Backend proof verification works
- [ ] Archetype commitments stored
- [ ] Community matching functional
- [ ] Expert-mode UI complete
- [ ] Cryptographic audit completed

---

## 📚 References

**Privacy Technologies:**
- Web Crypto API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API
- Zero-Knowledge Proofs: https://en.wikipedia.org/wiki/Zero-knowledge_proof
- zk-SNARKs: https://z.cash/technology/zksnarks/
- GDPR Compliance: https://gdpr.eu/

**Similar Implementations:**
- Signal Protocol (end-to-end encryption): https://signal.org/docs/
- Zcash (zero-knowledge transactions): https://z.cash/
- Matrix (encrypted chat): https://matrix.org/

**Threat Modeling:**
- EFF Surveillance Self-Defense: https://ssd.eff.org/
- OWASP Top 10 Privacy Risks: https://owasp.org/www-project-top-10-privacy-risks/

---

**Status**: Ready for implementation (Phase 1)
**Next Steps**: Update next_session_prompt.md and begin Phase 1 implementation
**Review**: Privacy/security team review recommended before production
