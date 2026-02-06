# Edge Intelligence Architecture

> User-centric agents interfacing with jurisdiction MCP servers and the Nostr-extended coordination protocol.

## Strategic Position

**MCP-native is the primary surface. Web frontend is the fallback.**

The Edge Intelligence layer closes the loop between:
- **Read**: Jurisdiction MCP servers (civic data, meetings, decisions) ✓
- **Coordinate**: Relay protocol (voices, initiatives, commitments) ✓
- **Act**: User-centric agents that personalize and simplify participation ← this document

## Why MCP-First

| Traditional Approach | MCP-First Approach |
|---------------------|-------------------|
| Build web app, add AI as feature | Build for AI assistants, add web for accessibility |
| Users learn new UI | Users stay in familiar AI assistant |
| Maintain frontend + backend | Maintain backend; AI hosts render UI |
| Distribution requires marketing | Distribution via MCP connector directories |

**The bet**: Engaged civic participants increasingly live in AI assistants. Meeting them there eliminates friction and reduces development surface.

**January 2026 context**: MCP Apps extension released, enabling interactive UI components inside Claude.ai, Goose, VS Code, and other MCP-compatible hosts. This changes the calculus—MCP servers can now provide rich interfaces, not just text responses.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PRIMARY: AI-Native Surface                              │
│            Claude.ai / Goose / ChatGPT / Gemini / Ollama                   │
│                                                                             │
│   User: "I want to support the bike lane proposal"                         │
│                           │                                                 │
│                           ▼                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │              Personal Civic MCP (user's edge agent)                  │  │
│   │                                                                      │  │
│   │  • Parses intent, applies user context                              │  │
│   │  • Queries Jurisdiction MCP for civic data                          │  │
│   │  • Manages identity (tiered: Easy/Private/Sovereign)                │  │
│   │  • Handles signing flow                                              │  │
│   │  • Explains: "Showing this because you're interested in transit"    │  │
│   │                                                                      │  │
│   │  ┌───────────────────────────────────────────────────────────────┐  │  │
│   │  │  MCP App: Voice Interface                                      │  │  │
│   │  │  ┌─────────────────────────────────────────────────────────┐  │  │  │
│   │  │  │  🚴 Protected Bike Lane on 4th Street                   │  │  │  │
│   │  │  │  Community: 47 Support | 12 Oppose | 23 Watching        │  │  │  │
│   │  │  │  [🟢 Support]  [🔴 Oppose]  [👁 Watch]                  │  │  │  │
│   │  │  │  Signing as npub1q7k... (TouchID to confirm)            │  │  │  │
│   │  │  └─────────────────────────────────────────────────────────┘  │  │  │
│   │  └───────────────────────────────────────────────────────────────┘  │  │
│   └──────────────────────────┬──────────────────────────────────────────┘  │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │ queries civic data (no user context sent)
                               ▼
              ┌───────────────────────────────────────────────────────────────┐
              │              Jurisdiction MCP (civicos-mcp)                   │
              │              Read-only public civic data                      │
              │                                                               │
              │  • Meetings, decisions, agendas                              │
              │  • 311 issues, legislation, municipal code                   │
              │  • Voice counts, initiative status                           │
              │  • No user state, no personalization                         │
              │                                                               │
              │  Deployed: san-rafael.civicosproject.org/mcp                 │
              └───────────────────────────────┬───────────────────────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────────────┐
                              │         civicos-relay                 │
                              │                                       │
                              │  • Voice aggregation                  │
                              │  • Initiative tracking                │
                              │  • Commitment management              │
                              │  • Multi-jurisdiction federation     │
                              └───────────────────────────────────────┘
                                              │
                      ┌───────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FALLBACK: Web Surface                                   │
│                   civicos-workspace (Vue)                                   │
│                                                                             │
│   • For users without AI assistant subscriptions                           │
│   • Shares identity system with MCP surface                                │
│   • Embeds same Personal MCP logic (via web components)                    │
│   • Accessibility/reach path                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key insight:** The Personal MCP is the user's agent. It stores their context, manages their identity, and translates raw civic data into personalized, actionable information. The Jurisdiction MCP is the public library—it knows about the city, not the user.

## Two-MCP Architecture

A key distinction: there are **two types of MCP servers** in this architecture.

### Jurisdiction MCP (Read-Only)

The **Jurisdiction MCP** (`civicos-mcp`) is a public, read-only server that provides civic data for a jurisdiction:

- Meetings, decisions, agendas
- 311 issues, legislation, municipal code
- Voice counts, initiative status
- No user state, no personalization
- Deployed publicly (e.g., `san-rafael.civicosproject.org/mcp`)

This is the "library"—it answers questions about civic activity but doesn't know who's asking.

### Personal Civic MCP (User's Edge Agent)

The **Personal MCP** is the user's own agent that:

- Stores user context (interests, location, filtering instructions)
- Manages identity and keys (tiered system)
- Queries Jurisdiction MCPs for civic data
- Applies personalized filtering and reasoning
- Handles signing (keys never leave user control)
- Explains *why* something is relevant to *this* user

This is the "librarian"—it knows the user's interests and translates civic data into personalized, actionable information.

### Relationship

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI Host (Claude.ai, ChatGPT, etc.)                  │
│                                                                             │
│   User: "What housing issues affect my neighborhood?"                       │
│                           │                                                 │
│                           ▼                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    Personal Civic MCP                                │  │
│   │                    (user's edge agent)                               │  │
│   │                                                                      │  │
│   │  Context: Terra Linda, interests=[housing], filter="ignore parking" │  │
│   │  Identity: npub1q7k... (Easy mode, passkey-derived)                 │  │
│   │                                                                      │  │
│   │  1. Receives query with user context                                │  │
│   │  2. Queries Jurisdiction MCP for housing data                       │  │
│   │  3. Filters by location (Terra Linda)                               │  │
│   │  4. Applies user's filtering instructions                           │  │
│   │  5. Explains: "Showing this because you live near the proposed      │  │
│   │     development site and are interested in housing"                 │  │
│   └──────────────────────┬──────────────────────────────────────────────┘  │
│                          │                                                  │
└──────────────────────────┼──────────────────────────────────────────────────┘
                           │ queries (no user context sent)
                           ▼
              ┌─────────────────────────────────────────────────────────────┐
              │                    Jurisdiction MCP                          │
              │                    (civicos-mcp)                             │
              │                                                              │
              │  • search_meeting_history("housing", jurisdiction)          │
              │  • get_voice_counts(entity)                                 │
              │  • search_regulatory_stack("housing")                       │
              │                                                              │
              │  Returns: raw civic data, no personalization                │
              └─────────────────────────────────────────────────────────────┘
```

## Personal MCP Instantiation

**The core design challenge**: How does a layperson "run their own MCP"? This is a new paradigm.

Three instantiation patterns, each with different identity options:

### Pattern 1: MCP App (Zero Install)

The Personal MCP runs as an **MCP App inside the AI host** (Claude.ai, ChatGPT, Gemini).

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude.ai / ChatGPT                                            │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  MCP App (sandboxed iframe)                              │  │
│   │                                                          │  │
│   │  • Runs in browser sandbox                              │  │
│   │  • IndexedDB for key storage                            │  │
│   │  • Web Crypto / WebAuthn APIs available                 │  │
│   │  • Cannot access browser extensions                     │  │
│   │                                                          │  │
│   │  Identity options: 🟢 Easy, 🟡 Private                  │  │
│   │  NOT available: 🔴 Sovereign (NIP-07)                   │  │
│   └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Zero installation—works immediately in Claude.ai/ChatGPT
- User context persists in IndexedDB
- Passkey/password-based signing works

**Cons:**
- Cannot access NIP-07 extensions (nos2x, Alby) due to iframe sandbox
- Hardware wallet access limited (WebUSB may be blocked)
- Dependent on AI host's MCP Apps support

**Identity modes available:** 🟢 Easy, 🟡 Private

### Pattern 2: Claude Desktop / Local MCP (Full Access)

The Personal MCP runs **locally via stdio** (Claude Desktop, Goose, etc.).

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude Desktop / Goose                                         │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  Personal Civic MCP (local process)                      │  │
│   │                                                          │  │
│   │  • Full system access                                   │  │
│   │  • Can detect window.nostr (NIP-07)                     │  │
│   │  • Hardware wallet via WebUSB/WebHID                    │  │
│   │  • Local file storage for keys                          │  │
│   │                                                          │  │
│   │  Identity options: 🟢 Easy, 🟡 Private, 🔴 Sovereign    │  │
│   │  Including: NIP-07 extensions, hardware wallets         │  │
│   └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Full NIP-07 support (nos2x, Alby, etc.)
- Hardware wallet integration
- No sandbox restrictions

**Cons:**
- Requires local installation
- User must configure Claude Desktop config

**Identity modes available:** 🟢 Easy, 🟡 Private, 🔴 Sovereign (all sub-options)

### Pattern 3: Self-Hosted (Full Sovereignty)

User runs their own Personal MCP server.

**Pros:**
- Complete control over code and data
- Can integrate with any signing infrastructure
- Air-gapped setups possible

**Cons:**
- Requires technical expertise
- User responsible for security, updates

**Identity modes available:** All modes, plus custom integrations

### Pattern 4: Jurisdiction-Hosted Open WebUI

> **Implementation note:** CivicOS maintains a private Open WebUI fork (`github.com/lounsburynw/civicos-openwebui`), symlinked into the monorepo at `apps/civicos-openwebui-fork/`. City Pulse and civic components live there.

The municipality hosts an [Open WebUI](https://docs.openwebui.com/) instance for residents. This inverts the subscription model—city pays for infrastructure, citizens use for free.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    City-Hosted Open WebUI                                   │
│                    (e.g., civic.sanrafael.gov)                              │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Authentication: City LDAP/SSO                                       │  │
│   │  → Proves residency (account = verified resident)                   │  │
│   │  → City signs attestation: "npub1abc is verified SR resident"       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  LLM Backend (choose one):                                           │  │
│   │                                                                      │  │
│   │  Option A: Local Ollama                                             │  │
│   │  → Queries NEVER leave city infrastructure                          │  │
│   │  → No external API calls                                            │  │
│   │  → Requires GPU infrastructure + IT maintenance                     │  │
│   │                                                                      │  │
│   │  Option B: Enterprise API (RECOMMENDED FOR PILOT)                   │  │
│   │  → Claude API or OpenAI API with enterprise agreement               │  │
│   │  → Better LLM quality for nuanced civic questions                   │  │
│   │  → ~$300/month for city-scale usage                                 │  │
│   │  → Contractual privacy: no training, short retention, audit rights  │  │
│   │  → Lower operational burden (no GPU, automatic model updates)       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Client-Side Identity (still in browser)                             │  │
│   │  → Passkey/mnemonic-derived Nostr keys                              │  │
│   │  → User signs civic actions (city CANNOT impersonate)               │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   MCP Connections:                                                          │
│   → Own Jurisdiction MCP (san-rafael.civicosproject.org/mcp)              │
│   → County Jurisdiction MCP (marin-county.civicosproject.org/mcp)         │
│   → State Jurisdiction MCP (california.civicosproject.org/mcp)            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### LLM Backend Options

| Aspect | Local Ollama | Enterprise API |
|--------|--------------|----------------|
| **Query privacy** | Maximum (never leaves city) | Contractual (enterprise agreement) |
| **LLM quality** | Good (Llama 3, Mistral) | Excellent (Claude, GPT-4) |
| **Cost model** | GPU hardware + IT time | ~$300/month API costs |
| **Operational burden** | High (maintain infrastructure) | Low (managed service) |
| **Model updates** | Manual | Automatic |
| **Vendor dependency** | None | Anthropic/OpenAI |

**Enterprise API Privacy Guarantees:**

With an enterprise agreement, cities can negotiate:
- No training on civic queries
- Data retention limits (e.g., 30-day deletion)
- Audit rights
- SOC 2 compliance
- Custom data processing agreements

This shifts the privacy model from "queries never leave city" to "queries are contractually protected." For most US municipalities operating under rule of law, this is an acceptable tradeoff for significantly better LLM quality.

**Hybrid Option:**

Open WebUI supports multiple backends. Cities could:
- Default to Ollama for routine queries (cost control)
- Route complex queries to Claude API (quality)
- Offer user choice ("Use local AI" toggle for privacy-sensitive users)

**Pros (both options):**
- Zero cost to citizens (no AI subscription required)
- City attestation = sybil resistance + verified residency
- Integrated with existing city identity (SSO with other city services)
- Open WebUI has [native MCP support](https://docs.openwebui.com/features/mcp/)

**Cons:**
- City bears infrastructure/API cost
- Enterprise API: queries leave city infrastructure (with contractual protections)
- Local Ollama: lower LLM quality, higher operational burden
- Creates per-jurisdiction silos (mitigated by federation)

**Identity modes available:** 🟢 Easy, 🟡 Private (NIP-07 possible if not sandboxed)

#### Cross-Jurisdictional Coordination

City-hosted Open WebUI preserves cross-jurisdictional coordination:

| Concern | How It Works |
|---------|--------------|
| **Querying other jurisdictions** | Open WebUI connects to ANY Jurisdiction MCP (city, county, state) |
| **Voicing on other jurisdictions** | Relay accepts any valid Nostr signature |
| **Attestation portability** | City attestation travels with npub across jurisdictions |
| **Guest voices** | Allowed, displayed as "unverified" (vs "Verified SR resident") |

**Attestation display example:**
```
┌─────────────────────────────────────────────────────────────────┐
│  🚴 Protected Bike Lane on 4th Street (San Rafael)             │
│                                                                 │
│  Support: 47                                                    │
│    ├── 38 Verified San Rafael residents                        │
│    ├── 6 Verified Marin County residents (other cities)        │
│    └── 3 Unverified                                             │
│                                                                 │
│  [Your attestation: Verified San Rafael resident]              │
└─────────────────────────────────────────────────────────────────┘
```

#### Hierarchical Attestation

For county/state issues, attestations aggregate:

```
City attests → "npub1abc is verified San Rafael resident"
                              │
                              ▼
County verifies → "npub1abc is attested by a city in Marin County"
                              │
                              ▼
State verifies → "npub1abc is attested by a county in California"
```

This enables trust signals at every level without re-verification.

#### Recommended for Pilot

Pattern 4 with **Enterprise API backend** is recommended for the San Rafael pilot:

1. **Removes subscription barrier** — biggest friction point for citizen adoption
2. **City attestation** — solves proof-of-residency, provides sybil resistance
3. **Claude/GPT-4 quality** — nuanced civic questions deserve excellent answers
4. **Low operational burden** — no GPU infrastructure, automatic model updates
5. **Reasonable cost** — ~$300/month is negligible in city budget terms
6. **Contractual privacy** — enterprise agreement provides legal protections
7. **San Rafael context** — trusted jurisdiction, rule of law, privacy tradeoff acceptable

For cities with higher privacy requirements or distrust of cloud providers, the Ollama option remains available.
5. Can still federate with other jurisdictions

For authoritarian contexts, Pattern 2 (Claude Desktop) or Pattern 3 (Self-hosted) remain necessary.

### Instantiation ↔ Identity Constraints

The instantiation method constrains available identity modes:

| Instantiation | 🟢 Easy | 🟡 Private | 🔴 NIP-07 | 🔴 Hardware | 🔴 Airgap |
|--------------|---------|------------|-----------|-------------|-----------|
| **MCP App** (iframe) | ✅ | ✅ | ❌ | ⚠️ Limited | ✅ |
| **Claude Desktop** (local) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Self-hosted** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Jurisdiction Open WebUI** | ✅ | ✅ | ⚠️ Depends | ⚠️ Depends | ✅ |

**Why NIP-07 requires local install:** Browser extensions inject `window.nostr` into pages, but MCP Apps run in sandboxed iframes that cannot access the parent window's extensions. Jurisdiction-hosted Open WebUI may or may not sandbox the interface.

**Implication for authoritarian contexts:** Users who need state-actor resistance should use Claude Desktop (local) or self-hosted patterns to access Sovereign identity modes. The MCP App pattern (zero install) trades some security for convenience. Jurisdiction-hosted Open WebUI is appropriate for trusted jurisdictions operating under rule of law.

## Tiered Identity System

Users choose their security/convenience tradeoff. All modes produce the same output: a Schnorr signature over a canonical message. The relay doesn't know or care which mode was used.

### Design Principles

1. **Non-custodial**: No server-side key storage
2. **Nostr-compatible**: secp256k1/Schnorr/BIP-39 for ecosystem portability
3. **Progressive sovereignty**: Users can upgrade to more secure modes
4. **Transparent threat model**: Users understand what each mode protects against

### Mode Comparison

| Aspect | 🟢 Easy | 🟡 Private | 🔴 Sovereign |
|--------|---------|------------|--------------|
| **Setup** | 10 seconds | 1 minute | Already have keys |
| **Auth** | TouchID/FaceID | Password | External tool |
| **Key storage** | Derived from passkey | IndexedDB (encrypted) | User-managed |
| **Recovery** | Passkey sync + email | Recovery phrase | User-managed |
| **Cloud dependency** | Apple/Google | None | None |
| **State-actor resistant** | ❌ No | ⚠️ Partial | ✅ Yes |
| **Target user** | Normal residents | Privacy-conscious | Dissidents, power users |
| **MCP App** (iframe) | ✅ | ✅ | ⚠️ Airgap only |
| **Claude Desktop** (local) | ✅ | ✅ | ✅ All options |

### 🟢 Easy Mode

**How it works:**
1. User provides email (for recovery anchor and notifications)
2. Browser creates a passkey (WebAuthn) with PRF extension
3. PRF output is deterministic: same passkey + same email = same 32-byte secret
4. Secret derives Nostr keypair via HKDF
5. TouchID/FaceID triggers signing

**Key derivation:**
```
email ──► SHA256 ──► salt
                       │
passkey + salt ──► PRF ──► 32 bytes ──► HKDF ──► secp256k1 private key
                                                          │
                                                          ▼
                                              Schnorr public key (npub)
```

**Why it's convenient:**
- No password to remember
- No recovery phrase to write down
- Passkeys sync across devices via iCloud/Google
- Same key regenerates on any device with same passkey + email

**Why it's compromisable:**
- Apple/Google control passkey sync infrastructure
- Biometrics can be physically compelled
- Email links to real identity
- State actor with legal authority can obtain passkey material

**Browser support:** Chrome 116+, Safari 17+ (PRF extension required)

### 🟡 Private Mode

**How it works:**
1. User chooses a password
2. System generates BIP-39 mnemonic (12 words)
3. Mnemonic derives Nostr keypair via NIP-06 path
4. Private key encrypted with password-derived key (PBKDF2 + AES-256-GCM)
5. Encrypted key stored in IndexedDB
6. Password required to unlock and sign

**Key derivation:**
```
random entropy ──► BIP-39 mnemonic (12 words)
                          │
                          ▼
              mnemonicToSeed ──► NIP-06 derivation ──► secp256k1 private key
                                (m/44'/1237'/0'/0/0)            │
                                                               ▼
                                                   Schnorr public key (npub)
```

**Storage:**
```
password ──► PBKDF2 (100k iterations) ──► AES-256-GCM key
                                                │
private key + IV ──────────────────────► encrypted blob ──► IndexedDB
```

**Recovery:**
- User must save 12-word recovery phrase
- Phrase can import into any Nostr-compatible wallet
- Lose password + phrase = lose identity permanently

**Threat model:**
- Resistant to remote compromise (no cloud sync)
- Vulnerable to device seizure + password coercion
- Password can potentially be "forgotten" under duress (vs biometrics)

### 🔴 Sovereign Mode

**User brings their own keys.** Three sub-options, with varying instantiation requirements:

#### Option A: Nostr Extension (NIP-07)

**Requires:** Claude Desktop or self-hosted (not available in MCP App iframe)

- Alby, nos2x, or other browser extension manages keys
- Extension injects `window.nostr` into the page
- Signing flow:
  1. Personal MCP detects `window.nostr` object
  2. Requests public key: `window.nostr.getPublicKey()`
  3. Requests signature: `window.nostr.signEvent(event)`
  4. Extension prompts user for approval
  5. Signed event returned to Personal MCP
- Keys may be hardware-backed (Alby + Ledger integration)
- User can use same identity across Nostr ecosystem

**Why not in MCP App:** Browser extensions inject into pages, but MCP Apps run in sandboxed iframes that cannot access the parent window's `window.nostr` object.

#### Option B: Hardware Wallet

**Requires:** Claude Desktop or self-hosted (limited WebUSB in MCP App)

- Ledger, Trezor via WebUSB/WebHID
- Keys never leave secure element
- User confirms each signature on device
- Signing flow:
  1. Personal MCP connects to hardware wallet via WebUSB
  2. Sends signing request with message
  3. User confirms on device screen
  4. Device returns signature

#### Option C: Airgapped Signing

**Available in:** All instantiation patterns (including MCP App)

- User provides public key only during setup
- For each signing action:
  1. System displays message and QR code
  2. User scans with airgapped device
  3. Signs on airgapped device
  4. Pastes signature back (or scans return QR)
- Maximum security, maximum friction
- Suitable for high-risk situations

**Threat model:**
- Resistant to remote compromise
- Resistant to cloud subpoena (no cloud involvement)
- Device seizure resistance depends on hardware security
- Airgapped option resistant to all remote attacks

**Recommendation for high-risk users:** Install Claude Desktop and use NIP-07 with a hardware-backed extension like Alby + Ledger. This provides the best balance of usability and security for users in authoritarian contexts.

### Mode Migration

Users can upgrade to more sovereign modes (never downgrade):

```
🟢 Easy ──► 🟡 Private ──► 🔴 Sovereign
        │              │
        │              └── Export mnemonic, import to external wallet
        │
        └── Export mnemonic (derived from passkey), set password
```

Migration preserves the same keypair, so civic history (voices, initiatives) stays linked to the same identity.

## MCP Apps Integration

MCP Apps (released January 2026) enable interactive UI components rendered inside MCP-compatible hosts.

### UI Resources

The jurisdiction MCP server declares UI resources:

```json
{
  "resources": [
    {
      "uri": "ui://civicos/dashboard",
      "name": "Civic Dashboard",
      "mimeType": "text/html;profile=mcp-app",
      "description": "Personalized civic activity and suggestions"
    },
    {
      "uri": "ui://civicos/voice/{entity}",
      "name": "Voice Interface",
      "mimeType": "text/html;profile=mcp-app",
      "description": "Cast voice on a civic item with real-time counts"
    },
    {
      "uri": "ui://civicos/meeting/{meeting_id}",
      "name": "Meeting Prep",
      "mimeType": "text/html;profile=mcp-app",
      "description": "Interactive meeting preparation"
    },
    {
      "uri": "ui://civicos/identity",
      "name": "Identity Manager",
      "mimeType": "text/html;profile=mcp-app",
      "description": "Manage civic identity and security mode"
    }
  ]
}
```

### Security Model

MCP Apps run in sandboxed iframes:
- Cannot access parent window
- Communicate via postMessage (MCP JSON-RPC)
- Can use IndexedDB/localStorage within their origin
- Can invoke Web Crypto, WebAuthn APIs

This enables client-side key management within the MCP App—keys never traverse the network.

### Tool Integration

Tools can return UI resources for rich interaction:

```python
@tool
def cast_voice(entity: str, stance: str) -> ToolResult:
    # If user needs to sign, return UI component
    return ToolResult(
        content=[{
            "type": "resource",
            "resource": {
                "uri": f"ui://civicos/voice/{entity}?stance={stance}",
                "mimeType": "text/html;profile=mcp-app"
            }
        }]
    )
```

## Tool Architecture

Tools are split between the two MCP types based on whether they require user context.

### Jurisdiction MCP Tools (Read-Only, Public)

These tools query civic data without any user context. They're exposed by the public Jurisdiction MCP (`civicos-mcp`):

| Tool | Purpose |
|------|---------|
| `search_meeting_history` | Past decisions and transcript excerpts |
| `get_upcoming_meetings` | Upcoming agendas |
| `find_similar_issues` | 311 complaints by topic |
| `search_regulatory_stack` | Municipal/state/federal law |
| `city_pulse` | Activity snapshot |
| `get_public_testimony` | What residents have said |
| `get_voice_counts` | Voice aggregates for an entity |
| `list_initiatives` | Active initiatives in jurisdiction |

**Design principle:** The Jurisdiction MCP is the "library"—it provides public civic knowledge but doesn't know who's asking or why.

### Personal MCP Tools (Personalized, Authenticated)

These tools require user context and/or identity. They're exposed by the user's Personal MCP:

#### Write Tools

Single authenticated calls that handle signing internally:

| Tool | Purpose | Identity Required |
|------|---------|-------------------|
| `cast_voice` | Support/oppose/watch an item | Yes |
| `follow_topic` | Subscribe to topic updates | Yes |
| `start_initiative` | Create coordination focal point | Yes |
| `make_commitment` | Commit to take action | Yes |
| `unfollow` | Remove subscription | Yes |

These tools:
1. Receive the action request
2. Check for identity (prompt setup if missing)
3. Invoke signing flow (passkey/password/extension based on mode)
4. Broadcast signed payload to relay
5. Return confirmation

The signature is created client-side; only the signed payload is sent to the relay.

#### Context Tools

Personalized based on user's context and history:

| Tool | Purpose |
|------|---------|
| `get_suggestions` | Proactive recommendations based on interests |
| `get_relevant_now` | Items needing attention (deadlines, meetings) |
| `get_my_activity` | Engagement history |
| `get_my_follows` | Active subscriptions |
| `get_my_voices` | Positions taken |

These tools query the Jurisdiction MCP, then filter and rank based on user context stored in the Personal MCP.

#### Identity Tools

| Tool | Purpose |
|------|---------|
| `get_identity_status` | Current mode, public key, setup state |
| `setup_identity` | Returns identity setup UI |
| `export_identity` | Returns mnemonic (Private mode) or instructions (Easy mode) |
| `upgrade_identity` | Migrate to more sovereign mode |

### Tool Flow Example

```
User: "I want to support the bike lane proposal"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Personal MCP                                                    │
│                                                                  │
│  1. Parse intent: cast_voice(entity="bike-lane-4th-st",         │
│                              stance="support")                   │
│                                                                  │
│  2. Query Jurisdiction MCP for entity details + voice counts    │
│                                                                  │
│  3. Check identity status                                        │
│     └── No identity? Return setup UI                            │
│     └── Has identity? Continue                                   │
│                                                                  │
│  4. Invoke signing flow (based on identity mode)                │
│     └── 🟢 Easy: TouchID prompt                                 │
│     └── 🟡 Private: Password prompt                             │
│     └── 🔴 Sovereign: Extension/hardware/paste                  │
│                                                                  │
│  5. Broadcast to relay                                          │
│                                                                  │
│  6. Return: "You've voiced support. 48 others support this."    │
└─────────────────────────────────────────────────────────────────┘
```

## Signing Flow

Unified across all identity modes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SIGNING FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. User action (e.g., "cast_voice")                                       │
│                           │                                                 │
│                           ▼                                                 │
│  2. MCP App checks for identity                                            │
│     ├── No identity? Show setup UI (mode selection)                        │
│     └── Has identity? Continue                                             │
│                           │                                                 │
│                           ▼                                                 │
│  3. Construct canonical message                                            │
│     "civicos:voice:v1:{entity}:{stance}:{timestamp}"                       │
│                           │                                                 │
│                           ▼                                                 │
│  4. Request signature from provider                                        │
│     ├── 🟢 Easy: TouchID prompt → PRF → derive key → sign                  │
│     ├── 🟡 Private: Password prompt → decrypt key → sign                   │
│     └── 🔴 Sovereign: Extension popup / hardware confirm / paste sig       │
│                           │                                                 │
│                           ▼                                                 │
│  5. Broadcast to relay                                                     │
│     POST /coordination/voice                                               │
│     { entity, stance, timestamp, public_key, signature }                   │
│                           │                                                 │
│                           ▼                                                 │
│  6. Relay verifies signature (Schnorr BIP-340)                             │
│     ├── Valid? Store voice, update counts                                  │
│     └── Invalid? Reject                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

The relay is agnostic to signing method. It receives:
- Public key (npub)
- Message
- Schnorr signature

If the signature verifies, the voice is accepted. The relay never knows if the user touched TouchID, entered a password, or used an airgapped laptop in a Faraday cage.

## Threat Model

### Explicit Non-Goals (Easy Mode)

Easy mode is **not designed to resist**:
- Government subpoena of Apple/Google passkey infrastructure
- Physical coercion to provide biometric
- State-level adversaries with legal authority
- Sophisticated nation-state attacks

**Easy mode is designed for:** San Rafael residents who forget passwords, participating in local government under rule of law.

### Progressive Threat Resistance

| Threat | 🟢 Easy | 🟡 Private | 🔴 Sovereign |
|--------|---------|------------|--------------|
| Curious neighbor | ✅ | ✅ | ✅ |
| Data breach (server) | ✅ | ✅ | ✅ |
| Device theft (locked) | ✅ | ✅ | ✅ |
| Device theft (unlocked) | ⚠️ | ⚠️ | ✅ (hardware) |
| Phishing | ✅ | ⚠️ | ✅ |
| Cloud provider subpoena | ❌ | ✅ | ✅ |
| Biometric coercion | ❌ | ✅ | ✅ |
| Password coercion | N/A | ⚠️ | ✅ (hardware) |
| Nation-state adversary | ❌ | ⚠️ | ✅ |

### User Communication

The UI clearly communicates the threat model:

```
🟢 Easy Mode
"Convenient and secure for everyday civic participation.
Not recommended if you face persecution for your political views."

🟡 Private Mode
"More private. No cloud sync, no biometrics.
You're responsible for remembering your password and saving your recovery phrase."

🔴 Sovereign Mode
"Maximum security. You control your keys completely.
For high-risk situations or users who want full self-sovereignty."
```

## Implementation Roadmap

### Phase 0: Personal MCP Scaffold

**Goal:** Create the Personal MCP as a separate package that users can run locally or that runs as an MCP App.

**Files:**
- `apps/civicos-personal-mcp/` - New package for Personal MCP
  - `server.py` - MCP server with personal tools
  - `context.py` - User context management
  - `identity.py` - Tiered identity system
- `apps/civicos-personal-mcp/ui/` - MCP App components (for iframe instantiation)

**Design decisions:**
- Single codebase serves both local (Claude Desktop) and MCP App (iframe) patterns
- Feature detection for identity modes (NIP-07 only available locally)
- Shared storage abstraction (IndexedDB for iframe, file system for local)

### Phase 1: Identity Providers

**Files:**
- `apps/civicos-personal-mcp/ui/identity/` - Identity setup and management UIs
- `apps/civicos-personal-mcp/lib/providers/` - SigningProvider implementations
  - `passkey-provider.ts` (Easy) - WebAuthn + PRF
  - `local-wallet-provider.ts` (Private) - BIP-39 + encrypted storage
  - `nostr-extension-provider.ts` (Sovereign) - NIP-07 detection (local only)
  - `hardware-wallet-provider.ts` (Sovereign) - WebUSB (local only)
  - `manual-signing-provider.ts` (Sovereign) - Airgapped flow (all patterns)

**Enables:** Identity creation, persistence, signing across all instantiation patterns

### Phase 2: Write Tools + Voice UI

**Files:**
- `apps/civicos-personal-mcp/tools/write_handlers.py` - cast_voice, follow_topic, etc.
- `apps/civicos-personal-mcp/ui/voice.html` - Voice casting MCP App

**Enables:** Casting voices from Claude.ai/ChatGPT

### Phase 3: Context Tools + Personalization

**Files:**
- `apps/civicos-personal-mcp/tools/context_handlers.py` - get_suggestions, get_relevant_now
- `apps/civicos-personal-mcp/services/context_service.py` - User context + Jurisdiction MCP queries

**Enables:** Personalized civic recommendations ("Showing this because you live near...")

### Phase 4: Full MCP Apps Suite

**Files:**
- `apps/civicos-personal-mcp/ui/dashboard.html` - Civic dashboard
- `apps/civicos-personal-mcp/ui/meeting.html` - Meeting prep
- `apps/civicos-personal-mcp/ui/initiative.html` - Initiative creation/tracking

**Enables:** Full interactive experience in Claude.ai

### Migration from Current Architecture

The current `apps/civicos-mcp/` (Jurisdiction MCP) remains unchanged—it's already the read-only public server.

The new `apps/civicos-personal-mcp/` contains the personalized layer that:
1. Connects to Jurisdiction MCP for civic data
2. Applies user context for filtering/personalization
3. Manages identity and signing
4. Renders MCP App UIs

## Technical Specifications

### Cryptographic Standards

| Component | Standard | Notes |
|-----------|----------|-------|
| Curve | secp256k1 | Nostr/Bitcoin compatible |
| Signature | Schnorr (BIP-340) | Nostr standard |
| Mnemonic | BIP-39 | 12 words, English wordlist |
| Key derivation | NIP-06 | Path: m/44'/1237'/0'/0/0 |
| Encryption | AES-256-GCM | For Private mode key storage |
| KDF | PBKDF2-SHA256 | 100k iterations for password → key |
| Passkey PRF | WebAuthn PRF extension | For Easy mode key derivation |

### Message Formats

**Voice:**
```
civicos:voice:v1:{entity}:{stance}:{iso8601_timestamp}
```

**Initiative:**
```
civicos:initiative:v1:{initiative_id}:{topic}:{title_hash}:{iso8601_timestamp}
```

### Storage

**Easy Mode (localStorage):**
```json
{
  "civic-easy-email": "user@example.com",
  "civic-easy-credential-id": "base64-encoded-credential-id"
}
```

**Private Mode (IndexedDB `civic-wallet` store):**
```json
{
  "publicKey": "hex-encoded-pubkey",
  "encryptedPrivateKey": "hex-encoded-ciphertext",
  "salt": "hex-encoded-salt",
  "iv": "hex-encoded-iv",
  "createdAt": 1706900000000
}
```

**Sovereign Mode (localStorage):**
```json
{
  "civic-identity-mode": "sovereign",
  "civic-sovereign-type": "nostr-extension|hardware|manual",
  "civic-sovereign-pubkey": "hex-encoded-pubkey"
}
```

## References

- [MCP Apps Specification](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx)
- [Open WebUI Documentation](https://docs.openwebui.com/) - Self-hosted AI platform with MCP support
- [Open WebUI MCP Integration](https://docs.openwebui.com/features/mcp/) - Native MCP support in Open WebUI
- [WebAuthn PRF Extension](https://w3c.github.io/webauthn/#prf-extension)
- [BIP-39: Mnemonic code for generating deterministic keys](https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki)
- [BIP-340: Schnorr Signatures](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki)
- [NIP-06: Basic key derivation from mnemonic seed phrase](https://github.com/nostr-protocol/nips/blob/master/06.md)
- [NIP-07: window.nostr capability for web browsers](https://github.com/nostr-protocol/nips/blob/master/07.md)
- [COORDINATION_PROTOCOL.md](./COORDINATION_PROTOCOL.md) - Relay protocol details
- [MCP_INTEGRATION_STRATEGY.md](./MCP_INTEGRATION_STRATEGY.md) - Jurisdiction MCP server architecture
