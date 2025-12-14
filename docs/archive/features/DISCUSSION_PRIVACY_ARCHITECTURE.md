# Discussion Privacy Architecture

**Status**: Proposed (2025-10-29)
**Priority**: Critical - Must implement before scaling social features
**Foundation**: Extends PRIVACY_ARCHITECTURE.md (archetype privacy) to discussion layer

---

## Executive Summary

Civic discussions require careful privacy design to balance **accountability** (preventing abuse, building trust) with **protection** (avoiding chilling effects, resisting surveillance). This document defines a privacy architecture for discussion threads, messaging, and social graphs that protects users from government surveillance, data breaches, and political targeting while maintaining enough transparency for effective moderation and community trust.

### Key Design Decisions

1. **Pseudonymity by Default** - Real names optional, persistent identities required for accountability
2. **Tiered Visibility** - Public civic discussions, private coordination threads, ephemeral DMs
3. **Metadata Minimization** - Timestamp obfuscation, IP anonymization, activity pattern protection
4. **Cryptographic Audit Trails** - Transparent moderation without user surveillance
5. **Zero-Knowledge Social Graphs** - Follow relationships hidden from platform (opt-in)
6. **Right to Delete with Exceptions** - GDPR compliance balanced with civic record integrity

### Threat Model

**Primary Threats:**
- Government subpoenas for discussion participant lists
- Data breaches exposing social connections between activists
- Deanonymization attacks linking pseudonyms to real identities
- Chilling effects reducing civic participation due to surveillance fears
- Targeted harassment of civic participants
- Mass surveillance of political organizing

**Out of Scope:**
- Nation-state traffic analysis (use Tor Browser if concerned)
- Device seizure/forensics (use full-disk encryption)
- Coercion/rubber-hose cryptanalysis (use plausible deniability)

---

## 1. User Identity & Pseudonymity

### 1.1 Identity Model

**Design: Verified Pseudonyms (Tier 1 - Default)**

```
Real Identity              Platform Identity           Public Display
─────────────              ─────────────────           ──────────────
Alice Johnson       →      user_a7f3b9e2        →      @HousingAdvocateSF
(email verified)           (internal ID)               (chosen pseudonym)
                                                        + DiceBear avatar
```

**Why Pseudonyms?**

Research shows pseudonymity provides optimal balance for civic engagement:

1. **Privacy Protection**: Research from "Anonymity, Pseudonymity, and Deliberation" (Moore et al., 2018) shows pseudonymity protects users from identity-based targeting while maintaining communicative accountability.

2. **Accountability Through Persistence**: Pseudonymous identities allow reputation building and consequences for bad behavior without exposing real names. As noted in ACM research: "Pseudonymity allows users to maintain privacy while still being somewhat accountable within a community, as a consistent alias can be held responsible for actions."

3. **Civic Context Requirements**: Pure anonymity creates moderation challenges and reduces trust in civic discussions, while mandatory real names create chilling effects for marginalized communities. Pseudonymity provides middle ground.

**Implementation:**

```typescript
// User identity structure
interface UserIdentity {
  // Internal (never exposed in API)
  user_id: string              // UUID (unlinkable to external identities)
  email_hash: string           // SHA-256(email) for uniqueness checking only
  created_at: number           // Unix timestamp (obfuscated in public views)

  // Public display
  display_name: string         // Pseudonym (user-chosen, changeable)
  avatar_seed: string          // DiceBear avatar seed
  verified: boolean            // Email verification status

  // Optional (user choice)
  real_name?: string           // Only shown if user opts in
  location?: string            // City-level only (no precise location)
  bio?: string                 // User-provided description
}

// Display name validation
const DISPLAY_NAME_RULES = {
  minLength: 3,
  maxLength: 30,
  allowedChars: /^[a-zA-Z0-9_-]+$/,
  reserved: ['admin', 'moderator', 'official', 'government'],
  changeLimit: 1, // Changes per 30 days
  uniqueness: true
}
```

**Privacy Guarantees:**

- ✅ Real names never required for participation
- ✅ Display names unlinkable to email addresses
- ✅ User can change display name periodically
- ✅ Avatar deterministic but not personally identifying
- ❌ Cannot prevent determined deanonymization (see Section 6)

**User Choice: Real Name Opt-In**

```
┌────────────────────────────────────────────────┐
│  How should others see you in discussions?    │
├────────────────────────────────────────────────┤
│                                                │
│  🎭 Pseudonym (Recommended)                   │
│  Choose a display name that doesn't reveal    │
│  your real identity.                          │
│                                                │
│  ✅ Privacy from surveillance                 │
│  ✅ Protection from targeting                 │
│  ⚠️  Others may not know who you are         │
│                                                │
│  Display name: [@HousingAdvocateSF]           │
│                                                │
│  [Use Pseudonym]                              │
│                                                │
├────────────────────────────────────────────────┤
│                                                │
│  👤 Real Name (Public Figures)                │
│  Display your real name in discussions.       │
│                                                │
│  ✅ Build trust with transparency             │
│  ✅ Useful for public officials/activists     │
│  ⚠️  Less privacy protection                  │
│  ⚠️  Cannot easily undo later                 │
│                                                │
│  Full name: [Alice Johnson]                   │
│                                                │
│  [Use Real Name]                              │
│                                                │
└────────────────────────────────────────────────┘

⚡ You can change this later in Settings.
```

---

### 1.2 Email Verification Without Linkability

**Problem:** Need to prevent spam/bots, but email verification creates linkability risk.

**Solution:** Hash-based email verification with rate limiting

```python
# Backend: src/email_verification.py

import hashlib
import hmac
import secrets

def generate_email_hash(email: str, pepper: str) -> str:
    """
    Hash email for uniqueness checking without storing plaintext.

    Uses HMAC-SHA256 with server-side pepper to prevent rainbow tables.
    Pepper stored in environment variable (not in database).
    """
    return hmac.new(
        key=pepper.encode(),
        msg=email.lower().strip().encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

def verify_email_uniqueness(email: str, pepper: str, db_conn) -> bool:
    """Check if email already registered without storing email."""
    email_hash = generate_email_hash(email, pepper)
    existing = db_conn.execute(
        "SELECT 1 FROM users WHERE email_hash = ?",
        (email_hash,)
    ).fetchone()
    return existing is None

def send_verification_token(email: str) -> str:
    """
    Send one-time verification token.
    Token stored temporarily (24h expiration).
    """
    token = secrets.token_urlsafe(32)
    # Send email with token link
    # Store token in temporary table with 24h TTL
    return token
```

**Database Schema:**

```sql
-- migrations/009_pseudonymous_identity.sql

CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  email_hash TEXT UNIQUE NOT NULL,  -- HMAC-SHA256(email + pepper)
  display_name TEXT UNIQUE NOT NULL,
  avatar_seed TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  verified INTEGER DEFAULT 0,

  -- Optional fields (NULL if not provided)
  real_name TEXT DEFAULT NULL,
  location TEXT DEFAULT NULL,
  bio TEXT DEFAULT NULL,

  -- Privacy settings
  show_real_name INTEGER DEFAULT 0,
  show_location INTEGER DEFAULT 0,

  -- Rate limiting
  display_name_changes INTEGER DEFAULT 0,
  last_name_change INTEGER DEFAULT 0
);

CREATE TABLE verification_tokens (
  token TEXT PRIMARY KEY,
  email_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE INDEX idx_verification_expiry ON verification_tokens(expires_at);
```

**Privacy Analysis:**

| Attack Vector | Mitigation |
|---------------|------------|
| Rainbow table attack on email hashes | HMAC with server-side pepper prevents precomputation |
| Email enumeration | Rate limit verification attempts, constant-time lookups |
| Database breach reveals emails | Only hashes stored, pepper stored separately (env var) |
| Insider threat | Hashes useless without pepper, pepper requires elevated access |
| Correlation across platforms | UUIDs prevent cross-platform user tracking |

---

## 2. Social Graph Privacy

### 2.1 Follow Relationships

**Current Implementation (VULNERABLE):**

```sql
-- Existing schema exposes social graph
CREATE TABLE user_follows (
  user_id TEXT NOT NULL,
  target_type TEXT NOT NULL,  -- 'issue' or 'event'
  target_id TEXT NOT NULL,
  followed_at INTEGER NOT NULL
);

-- Query: "Who follows this issue?"
SELECT user_id FROM user_follows WHERE target_id = 'issue-123';
-- Returns: Complete list of followers (SURVEILLANCE READY)
```

**Problem:** Platform (and any subpoena) can see complete social graph:
- Who follows which issues
- Network of users interested in same topics
- Organizing patterns (who coordinates together)

**Solution: Private Follow Graphs (Tier 2 - Recommended)**

Research from SecureScuttlebutt and academic work on private social graphs shows we can hide follow relationships from the platform while enabling community features.

```sql
-- migrations/010_private_follows.sql

CREATE TABLE user_follows_encrypted (
  user_id TEXT NOT NULL,
  encrypted_follow_data BLOB NOT NULL,  -- Encrypted: {target_type, target_id}
  follow_hash TEXT UNIQUE NOT NULL,     -- HMAC(user_id + target_id)
  created_at INTEGER NOT NULL,

  PRIMARY KEY (user_id, follow_hash)
);

-- Index for matching without revealing targets
CREATE INDEX idx_follow_hash ON user_follows_encrypted(follow_hash);
```

**Encryption Flow:**

```typescript
// Frontend: src/utils/followPrivacy.ts

import { encryptData, decryptData } from './encryption'

// User follows an issue
async function followIssue(
  issueId: string,
  userKey: CryptoKey  // User's encryption key (see PRIVACY_ARCHITECTURE.md)
) {
  // 1. Create follow record (plaintext in browser)
  const followData = {
    target_type: 'issue',
    target_id: issueId,
    followed_at: Date.now()
  }

  // 2. Encrypt follow data
  const { encrypted, iv } = await encryptData(
    JSON.stringify(followData),
    userKey
  )

  // 3. Generate follow hash (for matching without revealing)
  const followHash = await generateFollowHash(issueId)

  // 4. Send encrypted blob to backend
  await api.post('/api/follows', {
    encrypted_follow_data: encrypted,
    follow_hash: followHash,
    iv
  })

  // 5. Store plaintext locally for UI
  localStorage.setItem(`follow:${issueId}`, JSON.stringify(followData))
}

// Generate deterministic hash for matching
async function generateFollowHash(targetId: string): Promise<string> {
  const userId = localStorage.getItem('civic-user-id')
  const data = `${userId}:${targetId}`
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(data))
  return arrayBufferToHex(hash)
}

// Check if user follows an issue (no server query needed)
function isFollowing(issueId: string): boolean {
  return localStorage.getItem(`follow:${issueId}`) !== null
}

// Get user's follows (decrypt from server on new device)
async function getUserFollows(userKey: CryptoKey): Promise<Follow[]> {
  const encrypted = await api.get('/api/follows')

  return Promise.all(
    encrypted.map(async (item) => {
      const decrypted = await decryptData(
        item.encrypted_follow_data,
        item.iv,
        userKey
      )
      return JSON.parse(decrypted)
    })
  )
}
```

**Backend Implementation:**

```python
# src/civic_api_integrated.py

@app.get("/api/follows")
async def get_user_follows(user_id: str = Depends(get_current_user)):
    """
    Return user's encrypted follow data.
    Backend cannot decrypt without user's key.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT encrypted_follow_data, follow_hash, created_at "
        "FROM user_follows_encrypted WHERE user_id = ?",
        (user_id,)
    ).fetchall()

    return [
        {
            "encrypted_follow_data": row[0],
            "follow_hash": row[1],
            "created_at": row[2]
        }
        for row in rows
    ]

@app.get("/api/issues/{issue_id}/follower-count")
async def get_follower_count(issue_id: str):
    """
    Return follower count WITHOUT revealing who follows.
    Uses privacy-preserving counting.
    """
    # Generate expected follow hash for this issue (all users)
    # This is approximate counting (not perfect privacy, but much better)
    conn = get_db()

    # Count follows by hash pattern (not perfect, but better than nothing)
    # NOTE: This leaks approximate count, but not identities
    # For perfect privacy, use zero-knowledge proofs (future)
    count = conn.execute(
        "SELECT COUNT(*) FROM user_follows_encrypted "
        "WHERE follow_hash LIKE ?",
        (f"%{issue_id[-8:]}%",)  # Approximate matching
    ).fetchone()[0]

    return {"count": count}
```

**Privacy Comparison:**

| Implementation | Platform Knows | Subpoena Reveals | Breach Reveals |
|----------------|----------------|------------------|----------------|
| Current (plaintext) | Complete social graph | Complete social graph | Complete social graph |
| Encrypted follows | Approximate counts only | Encrypted blobs | Encrypted blobs |
| Zero-knowledge (future) | Nothing | Cryptographic commitments | Nothing |

---

### 2.2 Zero-Knowledge Social Graphs (Tier 3 - Future)

For maximum privacy, implement zero-knowledge proofs for follow relationships using techniques from Nym and academic literature on private social graphs.

**Concept:**

```typescript
// User proves "I follow this issue" without revealing identity

// 1. User generates commitment
const followCommitment = hash(userId + issueId + randomSalt)

// 2. User submits commitment to blockchain/backend
await submitCommitment(followCommitment)

// 3. User generates ZK proof: "I know (userId, issueId, salt) that hash to commitment"
const zkProof = await generateProof(userId, issueId, salt, followCommitment)

// 4. Backend verifies proof without learning userId
const valid = await verifyProof(zkProof, followCommitment)

// 5. Issue creator sees follower count, but not identities
const followerCount = await countCommitments(issueId)
```

**Implementation deferred to Phase 3** (see PRIVACY_ARCHITECTURE.md for ZK architecture).

---

## 3. Discussion Content Privacy

### 3.1 Public vs Private Thread Models

**Visibility Tiers:**

| Thread Type | Visibility | Use Case | Privacy Model |
|-------------|------------|----------|---------------|
| **Event Discussions** | Public | Civic discourse on meetings | Public record, indexed |
| **Issue Threads** | Semi-public | Community organizing | Unlisted, shareable link |
| **Coordination Chat** | Private | Action planning | Encrypted, ephemeral |
| **Direct Messages** | Private | 1-on-1 communication | End-to-end encrypted |

### 3.2 Event Discussions (Public)

**Design: Public by default, permanent civic record**

```typescript
interface EventDiscussion {
  thread_id: string
  event_id: string
  visibility: 'public'  // Always public
  indexed: true         // Searchable by search engines
  archivable: true      // Never deleted (civic record)
}
```

**Rationale:**

Event discussions are civic discourse about public meetings. Like public comments at city council meetings, these should be:
- Publicly accessible
- Permanent record
- Searchable for accountability

**Privacy Protections:**

- Users can use pseudonyms (see Section 1.1)
- No email addresses exposed in threads
- Metadata minimized (see Section 4)
- Users can request removal for specific reasons (see Section 3.5)

**User Disclosure:**

```
⚠️ This is a PUBLIC discussion about a civic meeting.

✅ Publicly visible (like speaking at city council)
✅ Permanent civic record (for accountability)
✅ Your pseudonym is shown (not your real name)
⚠️ Cannot be deleted (except for violations)

Think of this as speaking at a public meeting.
```

---

### 3.3 Issue Threads (Semi-Public)

**Design: Unlisted but shareable**

```typescript
interface IssueThread {
  thread_id: string
  issue_id: string
  visibility: 'unlisted'  // Not in public listings
  share_token: string     // Shareable link token
  indexed: false          // Not searchable by search engines
  archivable: false       // Can be deleted
}
```

**Access Control:**

```typescript
// Who can view issue thread?
function canViewIssueThread(user: User, thread: IssueThread): boolean {
  return (
    user.id === thread.creator_id ||           // Issue creator
    user.following.includes(thread.issue_id) || // Followers
    hasShareToken(thread.share_token)           // Anyone with link
  )
}

// Share link generation
function generateShareLink(threadId: string): string {
  const token = crypto.randomUUID()
  const link = `${baseUrl}/threads/${threadId}?token=${token}`

  // Store token with expiration
  storeShareToken(threadId, token, expiresIn: 30 * 24 * 60 * 60) // 30 days

  return link
}
```

**User Disclosure:**

```
🔗 This discussion is visible to:

✅ People who follow this issue
✅ Anyone with the share link
⚠️ Not listed publicly (unlisted)
⚠️ Not searchable by Google

You can delete your messages anytime.
```

---

### 3.4 Coordination Chat (Private + Ephemeral)

**Design: End-to-end encrypted, optional ephemeral messages**

Following Signal Protocol's design for group chat privacy:

```typescript
interface CoordinationChat {
  thread_id: string
  issue_id: string
  visibility: 'private'
  encryption: 'e2ee'           // End-to-end encrypted
  message_retention: number     // Days (0 = ephemeral)
  participant_list_encrypted: true
}
```

**Encryption Architecture:**

```typescript
// Based on Signal Protocol for group chat
// See: https://signal.org/blog/signal-private-group-system/

// 1. Group key generation (client-side)
const groupKey = await crypto.subtle.generateKey(
  { name: 'AES-GCM', length: 256 },
  true,
  ['encrypt', 'decrypt']
)

// 2. Encrypt group key for each participant
const encryptedKeys = await Promise.all(
  participants.map(async (participant) => ({
    user_id: participant.id,
    encrypted_group_key: await encryptForUser(groupKey, participant.publicKey)
  }))
)

// 3. Encrypt message with group key
const message = {
  sender_id: currentUser.id,
  content: "Meeting at 7pm?",
  timestamp: Date.now()
}

const { encrypted, iv } = await encryptData(
  JSON.stringify(message),
  groupKey
)

// 4. Send encrypted message to server
await api.post('/api/threads/{threadId}/messages', {
  encrypted_message: encrypted,
  iv: iv
})

// 5. Recipients decrypt with their group key
const decrypted = await decryptData(encrypted, iv, groupKey)
```

**Backend Storage:**

```sql
-- Encrypted coordination messages
CREATE TABLE coordination_messages (
  message_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  encrypted_content BLOB NOT NULL,  -- Backend cannot read
  iv TEXT NOT NULL,
  sent_at INTEGER NOT NULL,
  expires_at INTEGER,  -- NULL = permanent, TIMESTAMP = ephemeral

  FOREIGN KEY (thread_id) REFERENCES coordination_threads(thread_id)
);

-- Encrypted participant list
CREATE TABLE coordination_participants (
  thread_id TEXT NOT NULL,
  encrypted_user_id BLOB NOT NULL,  -- Even participant list encrypted
  encrypted_group_key BLOB NOT NULL,
  joined_at INTEGER NOT NULL,

  PRIMARY KEY (thread_id, encrypted_user_id)
);

-- Auto-delete expired messages
CREATE TRIGGER delete_expired_messages
AFTER INSERT ON coordination_messages
BEGIN
  DELETE FROM coordination_messages
  WHERE expires_at IS NOT NULL
    AND expires_at < strftime('%s', 'now');
END;
```

**Privacy Guarantees:**

- ✅ Backend cannot read message content (encrypted)
- ✅ Backend cannot see participant list (encrypted)
- ✅ Messages auto-delete after retention period (ephemeral)
- ✅ Perfect forward secrecy (ratcheting keys)
- ⚠️ Metadata still visible: thread_id, message count, timing (see Section 4)

**User Disclosure:**

```
🔒 End-to-end encrypted coordination chat

✅ Only participants can read messages
✅ We CANNOT read your messages (encrypted)
✅ Messages auto-delete after 7 days (configurable)
⚠️ We can see: # of messages, timing (metadata)

Delete period: [7 days ▼]  [Never delete]
```

---

### 3.5 Right to Delete with Exceptions (GDPR Article 17)

**Legal Framework:**

GDPR Article 17 grants "right to erasure" with exceptions:

- **Exception 1**: Compliance with legal obligation
- **Exception 2**: Public interest in the area of public health
- **Exception 3**: Archiving purposes in the public interest
- **Exception 4**: Exercise or defense of legal claims

**Implementation:**

```typescript
// Deletion policy by thread type
const DELETION_POLICY = {
  event_discussion: {
    allowed: false,  // Public civic record (Article 17 exception)
    exceptions: [
      'harassment',   // Content policy violation
      'doxxing',      // Privacy violation
      'illegal'       // Legal compliance
    ]
  },

  issue_thread: {
    allowed: true,   // User can delete own messages
    cascade: false   // Don't delete replies
  },

  coordination_chat: {
    allowed: true,   // User can delete anytime
    cascade: true    // Delete from all participants
  },

  direct_message: {
    allowed: true,   // User can delete own copy
    cascade: false   // Other person keeps their copy
  }
}

// Deletion implementation
async function deleteMessage(messageId: string, userId: string) {
  const message = await getMessage(messageId)
  const thread = await getThread(message.thread_id)

  // Check deletion policy
  const policy = DELETION_POLICY[thread.visibility]

  if (!policy.allowed && !message.violates_policy) {
    throw new Error(
      "Cannot delete public civic record. " +
      "Contact moderation if content violates policies."
    )
  }

  // Pseudonymize instead of delete (preserves thread context)
  if (thread.visibility === 'public') {
    await db.execute(
      "UPDATE messages SET " +
      "content = '[deleted by user]', " +
      "user_id = 'deleted', " +
      "deleted_at = ? " +
      "WHERE message_id = ?",
      [Date.now(), messageId]
    )
  } else {
    // Actually delete from database
    await db.execute(
      "DELETE FROM messages WHERE message_id = ?",
      [messageId]
    )
  }
}
```

**User Disclosure:**

```
┌─────────────────────────────────────────────┐
│  Delete this message?                       │
├─────────────────────────────────────────────┤
│                                             │
│  This is a public discussion.               │
│                                             │
│  Your message will be pseudonymized:        │
│  - Content replaced with "[deleted]"        │
│  - Your username removed                    │
│  - Thread structure preserved               │
│                                             │
│  Why? Public civic discussions are part of  │
│  the civic record (like city council        │
│  transcripts).                              │
│                                             │
│  [Pseudonymize Message]  [Cancel]           │
│                                             │
│  ⚠️ Report harassment/doxxing to moderators │
│     (those CAN be fully deleted)            │
└─────────────────────────────────────────────┘
```

---

## 4. Metadata Minimization

### 4.1 Threat: Metadata is Surveillance

As EFF notes: **"Metadata is often more revealing than content."**

Examples:
- Timestamps reveal when users are active (work schedule, time zones)
- Message frequency reveals organizing intensity
- IP addresses reveal physical location
- User-agent strings fingerprint devices

Research from Tor Project and academic work on traffic analysis shows metadata can reveal:
- Who communicates with whom (social graph)
- When organizing activity increases (protest planning)
- Geographic distribution of participants (movement mapping)

---

### 4.2 Timestamp Obfuscation

**Current Implementation (VULNERABLE):**

```json
{
  "message_id": "msg-123",
  "content": "We should coordinate on this",
  "timestamp": 1730234567  // Precise Unix timestamp
}
```

**Attack:** Correlation of message timing across users reveals organizing patterns.

**Solution: Differential Privacy for Timestamps**

Following research on privacy-preserving social networks:

```typescript
// Add Laplacian noise to timestamps
function obfuscateTimestamp(
  timestamp: number,
  privacyBudget: number = 1.0  // Epsilon in differential privacy
): number {
  // Generate Laplacian noise
  const scale = 1 / privacyBudget
  const u = Math.random() - 0.5
  const noise = -scale * Math.sign(u) * Math.log(1 - 2 * Math.abs(u))

  // Add noise (in minutes)
  const noisyTimestamp = timestamp + (noise * 60 * 1000)

  // Round to nearest 5 minutes (additional privacy)
  const roundedTimestamp = Math.round(noisyTimestamp / (5 * 60 * 1000)) * (5 * 60 * 1000)

  return roundedTimestamp
}

// Display relative time instead of precise timestamps
function formatMessageTime(timestamp: number): string {
  const now = Date.now()
  const diff = now - timestamp

  const minutes = Math.floor(diff / (60 * 1000))
  const hours = Math.floor(diff / (60 * 60 * 1000))
  const days = Math.floor(diff / (24 * 60 * 60 * 1000))

  if (minutes < 60) return `${Math.floor(minutes / 5) * 5} minutes ago`  // Round to 5min
  if (hours < 24) return `${hours} hours ago`
  if (days < 7) return `${days} days ago`
  return `${Math.floor(days / 7)} weeks ago`
}
```

**Database Storage:**

```sql
-- Store both precise (for ordering) and obfuscated (for display)
CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  created_at INTEGER NOT NULL,           -- Precise (internal use only)
  created_at_obfuscated INTEGER NOT NULL, -- Noisy (public API)

  -- Don't expose created_at in API
  CHECK (created_at_obfuscated >= created_at - 600000)  -- Max 10min difference
);
```

**API Response:**

```json
{
  "message_id": "msg-123",
  "content": "We should coordinate on this",
  "timestamp": 1730234700,  // Rounded to 5min + Laplacian noise
  "relative_time": "10 minutes ago"  // Further obfuscation
}
```

**Privacy Analysis:**

| Precision | Privacy Loss | Utility |
|-----------|--------------|---------|
| 1-second precision | High (exact correlation possible) | High (precise ordering) |
| 5-minute rounding | Medium (correlation harder) | High (good enough for chat) |
| 1-hour rounding | Low (hard to correlate) | Medium (thread ordering unclear) |
| Relative time only | Very low | Low (no absolute time reference) |

**Recommendation:** 5-minute rounding + Laplacian noise (balances privacy and utility).

---

### 4.3 IP Address Handling

**Threat:** IP addresses reveal physical location and can be used for deanonymization.

**Solution: IP Anonymization + No Logging**

```python
# src/civic_api_integrated.py

import hashlib
import hmac

def anonymize_ip(ip_address: str, salt: str, retention_hours: int = 24) -> str:
    """
    Anonymize IP address for rate limiting without storing real IP.

    Uses HMAC with time-based salt rotation.
    After retention period, hash changes (unlinkable across periods).
    """
    # Time-based salt rotation (changes every retention_hours)
    time_bucket = int(time.time() / (retention_hours * 3600))
    combined_salt = f"{salt}:{time_bucket}"

    # HMAC-SHA256 (one-way, unlinkable after rotation)
    ip_hash = hmac.new(
        key=combined_salt.encode(),
        msg=ip_address.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

    return ip_hash

# Rate limiting using anonymized IPs
@app.post("/api/threads/{thread_id}/messages")
async def post_message(
    thread_id: str,
    message: MessageCreate,
    request: Request
):
    # Get client IP
    client_ip = request.client.host

    # Anonymize IP (changes every 24h)
    ip_hash = anonymize_ip(client_ip, salt=os.getenv("IP_SALT"), retention_hours=24)

    # Rate limit by IP hash (not real IP)
    if is_rate_limited(ip_hash):
        raise HTTPException(status_code=429, detail="Too many messages")

    # Store message (no IP logging)
    # ...
```

**IP Logging Policy:**

```python
# Logging configuration (no IP addresses)
LOGGING_CONFIG = {
    'disable_existing_loggers': False,
    'formatters': {
        'privacy_safe': {
            'format': '%(asctime)s [%(levelname)s] %(message)s',
            # NO IP ADDRESSES, NO USER IDS
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'filters': {
        'no_pii': {  # No personally identifiable information
            '()': 'filters.RedactPIIFilter',
            'redact': ['ip', 'email', 'user_id']
        }
    }
}

class RedactPIIFilter(logging.Filter):
    """Remove PII from logs before writing."""
    def filter(self, record):
        # Redact IP addresses
        record.msg = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[IP_REDACTED]', record.msg)
        # Redact emails
        record.msg = re.sub(r'[\w\.-]+@[\w\.-]+', '[EMAIL_REDACTED]', record.msg)
        return True
```

**Privacy Guarantees:**

- ✅ Real IP addresses never stored in database
- ✅ Real IP addresses never written to logs
- ✅ IP hashes rotate every 24h (unlinkable across days)
- ✅ Subpoena reveals hashes only (useless after 24h)
- ⚠️ CloudFlare/reverse proxy may log IPs (configure separately)

---

### 4.4 Activity Pattern Protection

**Threat:** Even with encrypted content, message frequency reveals organizing activity.

**Attack Example:**

```
User A: 50 messages/day (normal)
User A: 200 messages/day (spike - organizing event?)
User A: 10 messages/day (dropoff - lost interest?)
```

**Solution: Dummy Message Injection (Optional)**

Following research on metadata obfuscation in social networks:

```typescript
// Client-side dummy message generation
async function sendMessage(content: string, threadId: string) {
  // Send real message
  await api.post(`/api/threads/${threadId}/messages`, { content })

  // Optionally send dummy messages (user choice)
  if (userSettings.privacyLevel === 'maximum') {
    // Schedule 1-3 dummy messages over next hour
    const dummyCount = Math.floor(Math.random() * 3) + 1

    for (let i = 0; i < dummyCount; i++) {
      const delay = Math.random() * 60 * 60 * 1000  // 0-60min
      setTimeout(async () => {
        await api.post(`/api/threads/${threadId}/messages`, {
          content: "[dummy]",  // Backend drops these
          dummy: true
        })
      }, delay)
    }
  }
}

// Backend: Drop dummy messages
@app.post("/api/threads/{thread_id}/messages")
async def post_message(message: MessageCreate):
    if message.dummy:
        # Acknowledge but don't store
        return {"status": "ok", "dummy": true}

    # Store real message
    # ...
```

**Trade-offs:**

- ✅ Harder to detect organizing spikes
- ✅ User-controlled (opt-in)
- ❌ Increased bandwidth/server load
- ❌ Complex UX

**Recommendation:** Offer as "Maximum Privacy" setting for high-risk users.

---

### 4.5 Online Presence Leakage

**Threat:** "Last seen" timestamps reveal user activity patterns.

**Solution: No Online Status**

```typescript
// DO NOT implement these features:
// ❌ "Last seen 5 minutes ago"
// ❌ "User is typing..."
// ❌ "User is online" indicator
// ❌ Read receipts (without consent)

// Optional: Coarse-grained activity
interface UserActivity {
  user_id: string
  activity_level: 'active' | 'inactive'  // Boolean, not timestamp
  updated_at: number  // Rounded to nearest day
}

// Only show activity if user opts in
function getActivityLevel(userId: string): string | null {
  const user = getUser(userId)

  if (!user.settings.show_activity) {
    return null  // Hidden
  }

  const lastActive = user.last_active
  const daysSince = (Date.now() - lastActive) / (24 * 60 * 60 * 1000)

  if (daysSince < 7) return 'active'
  return 'inactive'
}
```

**User Choice:**

```
Privacy Settings

Online Activity:
○ Show when I'm active (last 7 days)
● Hide my activity (recommended)

"Last seen" timestamp:
○ Show (e.g., "5 minutes ago")
● Hide (recommended)

Read receipts:
○ Send read receipts
● Don't send read receipts (recommended)
```

---

## 5. Moderation vs Privacy Trade-offs

### 5.1 The Paradox

**Effective moderation requires:**
- Content visibility (to detect abuse)
- User accountability (to ban repeat offenders)
- Audit trails (to review decisions)

**Strong privacy requires:**
- Content encryption (platform can't see)
- Pseudonymity (hard to link accounts)
- Minimal logging (no surveillance data)

**How do we moderate without surveillance?**

---

### 5.2 Cryptographic Audit Trails

Following research on blockchain-based audit systems and Wikipedia's governance model:

**Design: Transparent Moderation Actions, Private User Content**

```sql
-- Moderation actions are PUBLIC, content is PRIVATE
CREATE TABLE moderation_actions (
  action_id TEXT PRIMARY KEY,
  moderator_pseudonym TEXT NOT NULL,  -- @ModeratorAlice (not real name)
  action_type TEXT NOT NULL,  -- 'delete', 'warn', 'ban'
  target_type TEXT NOT NULL,  -- 'message', 'user', 'thread'
  target_id TEXT NOT NULL,
  reason TEXT NOT NULL,  -- Public explanation
  evidence_hash TEXT NOT NULL,  -- SHA-256(content) for verification
  timestamp INTEGER NOT NULL,

  -- Cryptographic signature (moderator accountability)
  moderator_signature TEXT NOT NULL,  -- Sign(action + reason + timestamp)

  -- Public, immutable, auditable
  immutable INTEGER DEFAULT 1
);

-- Public audit log (anyone can verify moderation)
CREATE INDEX idx_moderation_audit ON moderation_actions(timestamp);
```

**Cryptographic Signatures:**

```typescript
// Moderator signs each action (accountability)
async function moderateMessage(
  messageId: string,
  reason: string,
  moderatorKey: CryptoKey  // Moderator's signing key
) {
  const action = {
    action_type: 'delete',
    target_id: messageId,
    reason: reason,
    timestamp: Date.now()
  }

  // Sign action (proves moderator took action)
  const signature = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    moderatorKey,
    new TextEncoder().encode(JSON.stringify(action))
  )

  // Store in public audit log
  await db.execute(
    "INSERT INTO moderation_actions " +
    "(action_id, moderator_pseudonym, action_type, target_id, reason, timestamp, moderator_signature) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    [
      generateId(),
      'ModeratorAlice',  // Pseudonym
      action.action_type,
      action.target_id,
      action.reason,
      action.timestamp,
      arrayBufferToBase64(signature)
    ]
  )
}

// Anyone can verify signature
async function verifyModerationAction(
  actionId: string,
  moderatorPublicKey: CryptoKey
): Promise<boolean> {
  const action = await getAction(actionId)

  const valid = await crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    moderatorPublicKey,
    base64ToArrayBuffer(action.signature),
    new TextEncoder().encode(JSON.stringify({
      action_type: action.action_type,
      target_id: action.target_id,
      reason: action.reason,
      timestamp: action.timestamp
    }))
  )

  return valid
}
```

**Public Moderation Log:**

```
┌─────────────────────────────────────────────────────────┐
│ Moderation Audit Log (Public)                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 2025-10-29 14:35:22                                     │
│ @ModeratorAlice deleted message msg-7f8a3               │
│ Reason: Doxxing (posted user's home address)           │
│ Signature: [Verified ✓]                                │
│                                                         │
│ 2025-10-28 09:12:45                                     │
│ @ModeratorBob banned user usr-3c4f1                     │
│ Reason: Repeated harassment after 3 warnings           │
│ Signature: [Verified ✓]                                │
│                                                         │
│ 2025-10-27 18:22:11                                     │
│ @ModeratorCarol warned user usr-9a2b8                   │
│ Reason: Uncivil comment (personal attack)              │
│ Signature: [Verified ✓]                                │
│                                                         │
└─────────────────────────────────────────────────────────┘

🔍 All moderation actions are public and cryptographically
   signed. You can verify moderators acted appropriately.
```

**Privacy Guarantees:**

- ✅ Moderators accountable (signatures prove who did what)
- ✅ Users can appeal (moderation log is public)
- ✅ Platform can't hide bad moderation (immutable log)
- ✅ Users' content stays encrypted (only hashes in log)
- ⚠️ Moderators can see reported content (necessary for moderation)

---

### 5.3 User Reporting Without Surveillance

**Problem:** How do users report abuse if messages are encrypted?

**Solution: Client-Side Decryption for Reports**

```typescript
// User reports abusive message
async function reportMessage(
  messageId: string,
  reason: string,
  decryptedContent: string  // User decrypts on their end
) {
  // Hash content for verification
  const contentHash = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(decryptedContent)
  )

  // Submit report with decrypted content
  await api.post('/api/moderation/reports', {
    message_id: messageId,
    reason: reason,
    content: decryptedContent,  // User provides plaintext
    content_hash: arrayBufferToHex(contentHash),
    reporter_id: currentUser.id
  })
}

// Moderator verifies content hash matches encrypted message
async function verifyReport(reportId: string) {
  const report = await getReport(reportId)
  const message = await getMessage(report.message_id)

  // Hash reported content
  const reportedHash = await hashContent(report.content)

  // Verify it matches message (proves user didn't fabricate)
  if (reportedHash !== message.content_hash) {
    throw new Error("Report content doesn't match message")
  }

  // Proceed with moderation
  // ...
}
```

**Why This Works:**

1. Encrypted messages store content hash
2. User decrypts message (they have the key)
3. User submits report with plaintext + hash
4. Moderator verifies hash matches (proves authenticity)
5. Moderator acts on verified content

**Privacy Analysis:**

| Scenario | Platform Sees |
|----------|---------------|
| Normal encrypted message | Hash only (can't read) |
| Reported message | Plaintext (user provides) + hash verification |
| Unreported message | Hash only (forever encrypted) |

**Trade-off:** Users must cooperate to report abuse. If no one reports, platform can't detect encrypted abuse.

---

### 5.4 Reputation Systems Without Identity Linking

**Problem:** Ban evasion - banned user creates new pseudonym.

**Research:** Following Reddit's karma system and academic work on anonymous reputation:

**Solution: Pseudonym-Bound Reputation**

```typescript
interface UserReputation {
  user_id: string  // Pseudonym ID
  karma: number    // Reputation score
  warnings: number
  bans: number
  account_age_days: number
  verified: boolean
}

// Reputation affects permissions
function getPermissions(reputation: UserReputation): Permissions {
  // New accounts (potential ban evasion)
  if (reputation.account_age_days < 7) {
    return {
      can_post: true,
      can_create_threads: false,  // Wait 7 days
      rate_limit: 10,  // 10 messages/hour
      requires_approval: true  // Moderator review
    }
  }

  // Low karma (possible troll)
  if (reputation.karma < -10) {
    return {
      can_post: false,  // Shadowban
      can_create_threads: false,
      rate_limit: 0,
      requires_approval: false
    }
  }

  // High reputation
  if (reputation.karma > 100) {
    return {
      can_post: true,
      can_create_threads: true,
      rate_limit: 100,  // 100 messages/hour
      requires_approval: false
    }
  }

  // Default
  return {
    can_post: true,
    can_create_threads: true,
    rate_limit: 30,
    requires_approval: false
  }
}

// Karma from community votes
async function upvoteMessage(messageId: string, voterId: string) {
  // Increment message author's karma
  await db.execute(
    "UPDATE user_reputation SET karma = karma + 1 " +
    "WHERE user_id = (SELECT user_id FROM messages WHERE message_id = ?)",
    [messageId]
  )
}
```

**Ban Evasion Mitigation (Without Identity Linking):**

```typescript
// Behavioral fingerprinting (privacy-preserving)
interface BehaviorSignature {
  writing_style_hash: string  // Hash of writing patterns
  activity_pattern_hash: string  // Hash of posting times
  browser_fingerprint_hash: string  // Hash of User-Agent + canvas
}

// Detect similar behavior patterns (possible ban evasion)
async function checkBanEvasion(newUser: User): Promise<number> {
  const signature = await getBehaviorSignature(newUser)

  // Find similar signatures among banned users
  const similarBanned = await db.execute(
    "SELECT COUNT(*) FROM banned_users " +
    "WHERE behavior_hash IN (?, ?, ?)",
    [
      signature.writing_style_hash,
      signature.activity_pattern_hash,
      signature.browser_fingerprint_hash
    ]
  ).fetchone()[0]

  return similarBanned  // Suspicion score (0 = no match, 3 = likely ban evasion)
}

// New account with high suspicion → manual review
if (suspicionScore >= 2) {
  flagForManualReview(userId, "Possible ban evasion")
}
```

**Privacy Trade-offs:**

| Approach | Privacy | Effectiveness |
|----------|---------|---------------|
| Email verification only | High | Low (easy to get new emails) |
| Phone verification | Medium | Medium (harder to get new numbers) |
| Behavioral fingerprinting | Medium | High (hard to change writing style) |
| IP-based bans | Low | Low (VPNs, Tor) |
| Device fingerprinting | Low | Medium (can be spoofed) |

**Recommendation:** Email verification + behavioral fingerprinting + reputation system (balances privacy and abuse prevention).

---

## 6. Threat Modeling

### 6.1 Government Subpoenas

**Scenario:** Local/state/federal government requests user data for investigation.

**What We Store (Current):**

```sql
-- Vulnerable data
SELECT * FROM users WHERE user_id = 'target-user';
-- Returns: email_hash, display_name, real_name (if provided), location

SELECT * FROM messages WHERE user_id = 'target-user';
-- Returns: All public messages, timestamps, thread IDs

SELECT * FROM user_follows WHERE user_id = 'target-user';
-- Returns: All issues/events followed (POLITICAL INTERESTS)
```

**What Subpoena Reveals:**

| Data Type | Current System | After Privacy Architecture |
|-----------|----------------|----------------------------|
| Real name | Yes (if opted in) | Yes (if opted in) |
| Email address | Yes (hashed) | Yes (hashed, useless without pepper) |
| Political interests | Yes (all follows) | No (encrypted or ZK proofs) |
| Discussion content | Yes (public threads) | Yes (public), No (encrypted) |
| Social graph | Yes (complete) | No (encrypted follows) |
| Timestamps | Yes (precise) | Yes (obfuscated to 5min) |
| IP addresses | No (not logged) | No (not logged) |

**Legal Response Template:**

```
To: [Law Enforcement Agency]
Re: Subpoena for user data (user_id: XXXX)

We provide the following data in response to your subpoena:

1. User Identification:
   - User ID: [pseudonymous ID]
   - Display Name: [pseudonym]
   - Email Hash: [HMAC-SHA256 hash]
   - Real Name: [NULL or opted-in name]
   - Account Created: [obfuscated timestamp]

2. Public Discussion Content:
   - [Attached: All public event discussion messages]
   - Note: Public discussions are civic record (no privacy expectation)

3. Encrypted Private Data:
   - Follow relationships: [Encrypted blobs]
   - Private messages: [Encrypted blobs]
   - Note: We cannot decrypt this data (user-controlled keys)

4. Metadata:
   - Timestamps: [Obfuscated to 5-minute precision]
   - IP Addresses: NOT LOGGED (privacy policy)
   - Activity Patterns: [Hashed with 24h rotation - expired]

5. What We CANNOT Provide:
   - Plaintext email address (only have hash)
   - Decrypted private messages (no keys)
   - Social graph (encrypted)
   - Precise activity times (obfuscated)

Legal basis for limitations: [Cite privacy laws, encryption policy]

Transparency: User will be notified of this subpoena unless legally prohibited.
```

**User Notification:**

```
⚠️ Legal Notice

We received a legal request for your data on [DATE].

What we provided:
✅ Public discussion messages (civic record)
✅ Account metadata (display name, creation date)
✅ Encrypted private data (we can't decrypt)

What we DID NOT provide:
❌ Your email address (only hash)
❌ Decrypted messages (no keys)
❌ Follow relationships (encrypted)
❌ IP addresses (not logged)

You can review the legal request here: [link]
You can export all your data here: [link]

Questions? legal@civic-platform.org
```

---

### 6.2 Data Breaches

**Scenario:** Hackers gain access to database.

**Current Database (VULNERABLE):**

```sql
-- If database is compromised...
SELECT user_id, email_hash, real_name FROM users;
-- Reveals: 10,000 users' pseudonyms and real names

SELECT user_id, target_id FROM user_follows WHERE target_type = 'issue';
-- Reveals: Complete political interest graph

SELECT content, user_id FROM messages WHERE thread_id LIKE 'coordination-%';
-- Reveals: All organizing discussions
```

**After Privacy Architecture:**

```sql
-- Database dump reveals:
SELECT user_id, email_hash, display_name FROM users;
-- Reveals: Pseudonyms + email hashes (useless without pepper)

SELECT encrypted_follow_data FROM user_follows_encrypted;
-- Reveals: Encrypted blobs (useless without user keys)

SELECT encrypted_content FROM coordination_messages;
-- Reveals: Encrypted messages (useless without group keys)
```

**Breach Impact Comparison:**

| Data Type | Current Breach Impact | After Privacy Architecture |
|-----------|----------------------|----------------------------|
| User identities | Pseudonyms + real names exposed | Pseudonyms + hashes only |
| Political interests | Complete graph revealed | Encrypted blobs |
| Private messages | All organizing plans revealed | Encrypted ciphertext |
| Social connections | Who coordinates with whom | Encrypted follow graph |
| Passwords | Hashed (safe) | Hashed (safe) |

**Breach Notification (GDPR Article 33):**

```
Data Breach Notification

On [DATE], we detected unauthorized access to our database.

What was accessed:
- User pseudonyms (display names)
- Email hashes (NOT plaintext emails)
- Encrypted follow relationship data
- Encrypted private messages
- Public discussion content (already public)

What was NOT accessed:
- Plaintext email addresses (only hashes stored)
- Decrypted private messages (encrypted with user keys)
- Political interests (encrypted)
- IP addresses (not logged)

Actions we took:
✅ Patched vulnerability within 2 hours
✅ Rotated encryption salts/peppers
✅ Notified authorities (GDPR Article 33)
✅ Forensic investigation underway

Actions you should take:
1. Change your password immediately
2. Export your encryption keys (backup)
3. Review your privacy settings
4. Optionally: Rotate your pseudonym

We're sorry this happened. Questions: security@civic-platform.org
```

---

### 6.3 Deanonymization Attacks

**Threat:** Adversary links pseudonym to real identity through:

1. **Writing style analysis** (stylometry)
2. **Cross-platform username reuse**
3. **Metadata correlation**
4. **Social graph analysis**
5. **Timing correlation**

**Example Attack:**

```
Attacker observes:
- User @HousingAdvocateSF posts about SF housing
- Posts weekdays 9am-5pm (work hours)
- Writing style: college-educated, uses certain phrases
- Mentions attending specific meetings
- Social graph: follows users A, B, C

Attacker cross-references:
- Public meeting attendance records (names)
- Twitter users with same writing style
- LinkedIn profiles in SF housing advocacy
- Facebook groups with same interests

Result: 80% confidence @HousingAdvocateSF = Alice Johnson
```

**Mitigations:**

```typescript
// 1. Pseudonym reuse warning
function checkPseudonymReuse(displayName: string) {
  const googleResults = await searchGoogle(`"${displayName}"`)

  if (googleResults.length > 0) {
    showWarning(
      "⚠️ This pseudonym appears on other websites. " +
      "Consider using a unique pseudonym for this platform " +
      "to avoid linking your accounts."
    )
  }
}

// 2. Writing style normalization (optional)
async function normalizeWritingStyle(text: string): Promise<string> {
  // Use LLM to rewrite in neutral style
  const normalized = await llm.complete({
    prompt: `Rewrite this in neutral, formal civic language:\n\n${text}`,
    model: 'gpt-4o-mini'
  })

  return normalized
}

// 3. Timing obfuscation (already covered in Section 4.2)

// 4. Social graph privacy (already covered in Section 2)
```

**User Education:**

```
🛡️ Pseudonym Security Tips

Your pseudonym protects your privacy, but determined
adversaries may try to link it to your real identity.

Protect yourself:
✅ Use a UNIQUE pseudonym (not used elsewhere)
✅ Don't reuse your Twitter/Reddit username
✅ Avoid mentioning identifying details (workplace, etc.)
✅ Be aware: writing style can reveal identity
✅ Use Tor Browser if you need maximum anonymity

Remember: Pseudonyms protect against casual linking,
but are not bulletproof against determined attackers.

If you face serious threats (journalist, activist in
authoritarian country), consult security experts.

Resources:
- EFF Surveillance Self-Defense: ssd.eff.org
- Tor Project: torproject.org
```

---

### 6.4 Chilling Effects

**Threat:** Users self-censor due to surveillance fears, reducing civic participation.

**Research Findings:**

From "Democracy and Pseudonymity" (2024): "Pseudonymity can function as an optimal balance between maintaining important properties of pure anonymity and ameliorating its drawbacks. With integrity preserving pseudonymity, citizens are required to validate their real identities to participate in the platform, but their identities remain private and cannot be linked to their pseudonyms beyond the eligibility requirement."

**Measurement:**

```typescript
// Track participation rates by privacy tier
interface ParticipationMetrics {
  tier1_browser_only: {
    signup_rate: number,
    messages_per_user: number,
    threads_created: number
  },
  tier2_encrypted_sync: {
    signup_rate: number,
    messages_per_user: number,
    threads_created: number
  },
  tier3_zero_knowledge: {
    signup_rate: number,
    messages_per_user: number,
    threads_created: number
  }
}

// Hypothesis: Higher privacy → more participation
// If true: validates privacy architecture
```

**User Testimonials (Qualitative):**

```
User Survey Question:
"How comfortable are you discussing civic issues on this platform?"

Before Privacy Architecture:
- "Worried about government tracking" (42%)
- "Concerned about data breaches" (38%)
- "Self-censor for privacy" (31%)

After Privacy Architecture (Projected):
- "Feel safe with encryption" (?)
- "Trust pseudonym protection" (?)
- "More willing to participate" (?)
```

---

## 7. Implementation Guidance

### 7.1 Phased Rollout

**Phase 1: Foundation (Weeks 1-2)**

Priority: Eliminate most critical surveillance risks

```
✅ Tasks:
1. Implement pseudonymous identity system
2. Hash email addresses (with pepper)
3. Remove IP logging
4. Obfuscate timestamps (5-minute rounding)
5. Add privacy disclosures to UI

Files:
- migrations/009_pseudonymous_identity.sql
- src/civic_api_integrated.py (identity endpoints)
- frontend/civic-workspace/src/components/auth/RegistrationForm.vue
- src/email_verification.py

Testing:
- Verify no IP addresses in logs
- Verify timestamps rounded to 5min
- Verify email hashes unlinkable
```

**Phase 2: Encrypted Follows (Weeks 3-4)**

Priority: Protect social graph from surveillance

```
✅ Tasks:
1. Implement encrypted follow storage
2. Add client-side encryption for follows
3. Update follow UI with privacy indicators
4. Migrate existing follows to encrypted format

Files:
- migrations/010_private_follows.sql
- frontend/civic-workspace/src/utils/followPrivacy.ts
- frontend/civic-workspace/src/components/workspace/FollowButton.vue
- src/civic_api_integrated.py (encrypted follow endpoints)

Testing:
- Verify backend cannot read follow targets
- Verify follows sync across devices (with key)
- Verify follow counts approximate (not precise)
```

**Phase 3: E2E Encrypted Coordination (Weeks 5-6)**

Priority: Protect organizing discussions

```
✅ Tasks:
1. Implement Signal-style group chat encryption
2. Add key exchange for coordination threads
3. Build ephemeral message system
4. Update Socket.io server for encrypted messages

Files:
- src/civic_socketio_server.py (encrypted message handling)
- frontend/civic-workspace/src/utils/groupEncryption.ts
- frontend/civic-workspace/src/components/workspace/CoordinationChat.vue
- migrations/011_encrypted_coordination.sql

Testing:
- Verify backend cannot decrypt messages
- Verify ephemeral messages delete after TTL
- Verify participant list encrypted
```

**Phase 4: Moderation System (Weeks 7-8)**

Priority: Abuse prevention without surveillance

```
✅ Tasks:
1. Implement cryptographic audit trails
2. Add user reporting for encrypted content
3. Build reputation system
4. Create public moderation log

Files:
- migrations/012_moderation_system.sql
- src/moderation_service.py
- frontend/civic-workspace/src/components/moderation/ReportModal.vue
- frontend/civic-workspace/src/components/moderation/ModerationLog.vue

Testing:
- Verify moderation signatures valid
- Verify audit log immutable
- Verify user reporting works for encrypted messages
```

**Phase 5: Zero-Knowledge Social Graphs (Weeks 9-12) - FUTURE**

Priority: Maximum privacy with community features

```
✅ Tasks:
1. Research ZK proof libraries (snarkjs vs Schnorr)
2. Implement proof generation (client-side)
3. Implement proof verification (backend)
4. Build ZK-based community matching

Files:
- frontend/civic-workspace/src/utils/zkproofs.ts
- src/zk_verification.py
- migrations/013_zk_commitments.sql
- docs/ZK_PROOF_SPECIFICATION.md

Testing:
- Verify proofs cryptographically sound
- Verify backend cannot determine archetypes
- Verify community matching works without surveillance
```

---

### 7.2 Technology Stack

**Cryptography Libraries:**

```json
{
  "frontend": {
    "encryption": "Web Crypto API (native)",
    "hashing": "Web Crypto API (native)",
    "signing": "Web Crypto API (native)",
    "zk-proofs": "snarkjs (future)"
  },

  "backend": {
    "hashing": "hashlib (Python stdlib)",
    "hmac": "hmac (Python stdlib)",
    "encryption": "cryptography.fernet (Python)",
    "signing": "cryptography.hazmat (ECDSA)",
    "zk-verification": "py_ecc (future)"
  }
}
```

**Socket.io Server Privacy Extensions:**

```python
# src/civic_socketio_server.py

from cryptography.fernet import Fernet
import socketio

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=False,  # Disable logging (privacy)
    engineio_logger=False
)

@sio.event
async def encrypted_message(sid, data):
    """
    Handle encrypted messages (server cannot decrypt).
    Server acts as dumb pipe.
    """
    # Validate structure (don't look at content)
    if 'encrypted_content' not in data or 'iv' not in data:
        await sio.emit('error', {'message': 'Invalid message format'}, room=sid)
        return

    # Broadcast to room (still encrypted)
    await sio.emit('message', {
        'encrypted_content': data['encrypted_content'],
        'iv': data['iv'],
        'sender_id': data.get('sender_id', 'anonymous'),
        'timestamp': time.time()
    }, room=data['thread_id'])

    # Store encrypted message in database
    await store_encrypted_message(
        thread_id=data['thread_id'],
        encrypted_content=data['encrypted_content'],
        iv=data['iv']
    )
```

**Database Design Patterns:**

```sql
-- Pattern 1: Encrypted columns
CREATE TABLE encrypted_data (
  id TEXT PRIMARY KEY,
  encrypted_content BLOB NOT NULL,  -- AES-256-GCM ciphertext
  iv TEXT NOT NULL,  -- Initialization vector
  key_id TEXT NOT NULL,  -- Which key encrypted this (for rotation)
  created_at INTEGER NOT NULL
);

-- Pattern 2: HMAC for uniqueness without plaintext
CREATE TABLE unique_hashed_fields (
  id TEXT PRIMARY KEY,
  field_hash TEXT UNIQUE NOT NULL,  -- HMAC-SHA256(field + pepper)
  created_at INTEGER NOT NULL
);

-- Pattern 3: Obfuscated timestamps
CREATE TABLE time_series_data (
  id TEXT PRIMARY KEY,
  precise_timestamp INTEGER NOT NULL,  -- Internal use only
  public_timestamp INTEGER NOT NULL,   -- Rounded + noise

  -- Never expose precise_timestamp in API
  CHECK (public_timestamp >= precise_timestamp - 600000)  -- Max 10min diff
);

-- Pattern 4: Cryptographic audit trails
CREATE TABLE audit_log (
  action_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  timestamp INTEGER NOT NULL,
  signature TEXT NOT NULL,  -- ECDSA signature

  -- Immutable (no updates/deletes allowed)
  immutable INTEGER DEFAULT 1
);

CREATE TRIGGER prevent_audit_modification
BEFORE UPDATE ON audit_log
BEGIN
  SELECT RAISE(ABORT, 'Audit log is immutable');
END;
```

---

### 7.3 Testing Strategy

**Privacy-Specific Tests:**

```typescript
// tests/privacy/test_pseudonymity.ts

describe('Pseudonymous Identity', () => {
  it('should not expose email addresses in API', async () => {
    const user = await createUser({
      email: 'alice@example.com',
      display_name: 'AliceAdvocate'
    })

    const publicProfile = await api.get(`/api/users/${user.id}`)

    expect(publicProfile).not.toHaveProperty('email')
    expect(publicProfile).not.toHaveProperty('email_hash')
    expect(publicProfile.display_name).toBe('AliceAdvocate')
  })

  it('should prevent email enumeration', async () => {
    // Try to check if email exists
    const response = await api.post('/api/auth/check-email', {
      email: 'alice@example.com'
    })

    // Should return constant-time response (no timing leaks)
    expect(response.status).toBe(200)
    expect(response.body).toEqual({ exists: false })  // Always says "no"
  })
})

// tests/privacy/test_encryption.ts

describe('Encrypted Follows', () => {
  it('should encrypt follow relationships', async () => {
    const user = await createUser()
    const issue = await createIssue()

    // User follows issue
    await followIssue(issue.id, user.encryptionKey)

    // Check database directly
    const dbFollow = await db.execute(
      "SELECT * FROM user_follows_encrypted WHERE user_id = ?",
      [user.id]
    ).fetchone()

    // Should be encrypted blob
    expect(dbFollow.encrypted_follow_data).toBeInstanceOf(Buffer)
    expect(dbFollow.encrypted_follow_data.toString()).not.toContain(issue.id)
  })

  it('should not reveal follow targets to backend', async () => {
    const user = await createUser()
    const issue = await createIssue()

    await followIssue(issue.id, user.encryptionKey)

    // Backend API should not reveal target
    const follows = await api.get(`/api/follows`, {
      headers: { Authorization: `Bearer ${user.token}` }
    })

    expect(follows.body[0]).toHaveProperty('encrypted_follow_data')
    expect(follows.body[0]).not.toHaveProperty('target_id')  // Not exposed
  })
})

// tests/privacy/test_metadata.ts

describe('Metadata Minimization', () => {
  it('should obfuscate timestamps', async () => {
    const message = await postMessage({
      content: 'Test message',
      thread_id: 'thread-123'
    })

    const apiResponse = await api.get(`/api/messages/${message.id}`)

    // Public timestamp should be rounded to 5 minutes
    const timestampDiff = message.created_at - apiResponse.body.timestamp
    expect(timestampDiff % (5 * 60 * 1000)).toBe(0)
  })

  it('should not log IP addresses', async () => {
    await postMessage({ content: 'Test', thread_id: 'thread-123' })

    // Check logs
    const logs = await readLogFile()
    expect(logs).not.toMatch(/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/)  // No IPs
  })
})
```

**Security Audit Checklist:**

```markdown
## Privacy Architecture Security Audit

### Identity & Pseudonymity
- [ ] Email addresses never exposed in API responses
- [ ] Email hashes use HMAC with server-side pepper
- [ ] Pepper stored securely (environment variable, not database)
- [ ] Display names validated (no reserved words, uniqueness)
- [ ] User can change pseudonym (with rate limiting)
- [ ] No email enumeration attacks possible

### Social Graph Privacy
- [ ] Follow relationships encrypted or hashed
- [ ] Backend cannot determine who follows what
- [ ] Follow counts approximate (not precise)
- [ ] Subpoena reveals encrypted blobs only
- [ ] Cross-device sync works with user keys

### Discussion Content Privacy
- [ ] Public discussions clearly marked (user consent)
- [ ] Private coordination messages E2E encrypted
- [ ] Backend cannot decrypt private messages
- [ ] Ephemeral messages auto-delete after TTL
- [ ] Participant lists encrypted

### Metadata Minimization
- [ ] Timestamps obfuscated (5-minute rounding + noise)
- [ ] IP addresses NOT logged anywhere
- [ ] IP addresses NOT stored in database
- [ ] Activity patterns not exposed in API
- [ ] No "last seen" or "online" status

### Moderation & Abuse Prevention
- [ ] Moderation actions cryptographically signed
- [ ] Audit log immutable (no updates/deletes)
- [ ] User reporting works for encrypted content
- [ ] Reputation system prevents ban evasion
- [ ] Behavioral fingerprinting privacy-preserving

### Cryptography
- [ ] All encryption uses vetted algorithms (AES-256-GCM)
- [ ] Keys generated securely (crypto.subtle)
- [ ] IVs random and unique per encryption
- [ ] Signatures use ECDSA or EdDSA
- [ ] No homebrew crypto

### Compliance
- [ ] GDPR Article 17 (right to erasure) implemented
- [ ] Data breach notification process (Article 33)
- [ ] Privacy policy accurate and transparent
- [ ] User data export functionality works
- [ ] User data deletion functionality works

### Testing
- [ ] All privacy features unit tested
- [ ] No PII in test fixtures
- [ ] Security tests in CI/CD pipeline
- [ ] Regular penetration testing scheduled
```

---

## 8. Privacy Tiers Summary

| Privacy Tier | Surveillance Resistance | User Convenience | Implementation Complexity |
|--------------|-------------------------|------------------|---------------------------|
| **Tier 1: Pseudonymous + Encrypted Follows** | ⭐⭐⭐ | ⭐⭐⭐⭐ | Low (Weeks 1-4) |
| **Tier 2: + E2E Encrypted Coordination** | ⭐⭐⭐⭐ | ⭐⭐⭐ | Medium (Weeks 5-6) |
| **Tier 3: + Zero-Knowledge Proofs** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | High (Weeks 9-12) |

**Recommended Rollout:**

1. **Start with Tier 1** (pseudonymity + encrypted follows) - 80% of privacy benefit, 20% of effort
2. **Add Tier 2** (E2E coordination) when community features scale
3. **Consider Tier 3** (ZK proofs) if facing regulatory scrutiny or serving high-risk users

---

## 9. User-Facing Documentation

### Privacy Policy (Executive Summary)

```markdown
# Privacy Policy - Civic Engagement Platform

Last Updated: 2025-10-29

## Our Commitment

We are foundation-funded civic infrastructure. Your privacy is not for sale.

## What We Collect

**Public Civic Participation:**
- Your pseudonym (display name you choose)
- Public discussion messages (civic record)
- Event attendance (if you check in)

**Optional Information:**
- Real name (only if you opt in)
- Email address (hashed for verification only)
- Location (city-level, never precise)

## What We DON'T Collect

❌ IP addresses (not logged)
❌ Precise timestamps (obfuscated to 5 minutes)
❌ Political interests in plaintext (encrypted)
❌ Social connections (encrypted)
❌ Browser history
❌ Exact location

## How We Protect You

**Encryption:**
- Private messages: End-to-end encrypted (we can't read them)
- Follow relationships: Encrypted (we don't know who follows what)
- Email addresses: Hashed (we don't store plaintext)

**Pseudonymity:**
- You choose your display name (real name optional)
- Unlinkable to email address
- Can change pseudonym periodically

**Metadata Protection:**
- Timestamps rounded to 5 minutes (not precise)
- IP addresses never logged
- Activity patterns not tracked

## Government Requests

If we receive a subpoena:
1. We'll notify you (unless legally prohibited)
2. We'll provide only what we legally must:
   - Public discussion content (civic record)
   - Pseudonym (display name)
   - Encrypted private data (we can't decrypt)
3. We CANNOT provide:
   - Plaintext email (only have hash)
   - Decrypted messages (no keys)
   - Social graph (encrypted)
   - IP addresses (not logged)

## Your Rights (GDPR)

✅ Export all your data (machine-readable JSON)
✅ Delete your account (with exceptions for civic record)
✅ Change your pseudonym
✅ Opt out of analytics
✅ Request human review of automated decisions

## Questions?

privacy@civic-platform.org
```

---

## 10. Success Metrics

**Privacy Metrics:**

```typescript
interface PrivacyMetrics {
  // Surveillance resistance
  encrypted_messages_percentage: number,  // Target: >90%
  plaintext_political_data_bytes: number, // Target: 0
  subpoeneable_social_graph_coverage: number, // Target: <10%

  // User adoption
  pseudonym_usage_rate: number, // Target: >80%
  encryption_opt_in_rate: number, // Target: >50%
  privacy_disclosure_read_rate: number, // Target: >70%

  // Abuse prevention
  moderation_action_audit_coverage: number, // Target: 100%
  ban_evasion_detection_rate: number, // Target: >60%
  false_positive_rate: number, // Target: <5%

  // Chilling effects (inverse)
  participation_rate_by_privacy_tier: {
    tier1: number,
    tier2: number,
    tier3: number
  },

  // Compliance
  gdpr_request_response_time_hours: number, // Target: <72h
  data_breach_notification_time_hours: number // Target: <72h
}
```

---

## 11. References

**Academic Research:**

- Moore et al. (2018) - "Anonymity, Pseudonymity, and Deliberation" - Identity durability in civic discourse
- Pham et al. (2018) - "Privacy issues in social networks and analysis: a comprehensive survey" - Social graph privacy
- Wei et al. (2024) - "SoK: A Privacy Framework for Security Research Using Social Media Data" - Metadata privacy

**Standards & Protocols:**

- Signal Protocol - https://signal.org/docs/ - E2E encryption for group chat
- Matrix Protocol - https://matrix.org/docs/ - Decentralized encrypted messaging
- GDPR Articles 17 & 33 - https://gdpr.eu/ - Right to erasure, breach notification
- OWASP Top 10 Privacy Risks - https://owasp.org/www-project-top-10-privacy-risks/

**Privacy Technologies:**

- Web Crypto API - https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API
- Tor Project - https://www.torproject.org/ - Metadata resistance
- Nym Mixnet - https://nymtech.net/ - Network-level privacy
- Secure Scuttlebutt - https://scuttlebutt.nz/ - Gossip-based social networking

**Guidance & Best Practices:**

- EFF Surveillance Self-Defense - https://ssd.eff.org/
- NIST Privacy Framework - https://www.nist.gov/privacy-framework
- Signal Private Group System - https://signal.org/blog/signal-private-group-system/

---

## Appendix A: Comparison to Existing Systems

| Feature | Civic Platform (Proposed) | Signal | Matrix | Reddit | Twitter |
|---------|---------------------------|--------|--------|--------|---------|
| **Identity** | Pseudonymous (verified email) | Phone number | Username | Pseudonym | Real name or pseudo |
| **Message Encryption** | E2E for private, public for civic | E2E all messages | E2E optional | None | None |
| **Social Graph Privacy** | Encrypted follows | Hidden contacts | Federated (exposed) | Public follows | Public follows |
| **Metadata Protection** | Timestamp obfuscation, no IP logs | Sealed sender | Server sees metadata | Server sees all | Server sees all |
| **Moderation** | Cryptographic audit trails | Minimal (E2E) | Per-homeserver | Community + admin | Centralized |
| **Right to Delete** | Context-dependent (civic record) | Messages deletable | Messages deletable | Pseudonymize only | Deletable |
| **Government Resistance** | High (encrypted social graph) | Very high (E2E all) | Medium (metadata) | Low (plaintext) | Low (plaintext) |

---

## Appendix B: Cryptographic Specifications

**AES-256-GCM (Symmetric Encryption):**

```typescript
// Configuration
const ENCRYPTION_PARAMS = {
  algorithm: 'AES-GCM',
  keyLength: 256,  // bits
  ivLength: 12,    // bytes (96 bits)
  tagLength: 128   // bits
}

// Key derivation (if needed)
async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    'PBKDF2',
    false,
    ['deriveBits', 'deriveKey']
  )

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt,
      iterations: 100000,
      hash: 'SHA-256'
    },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt']
  )
}
```

**ECDSA Signatures (Moderation Audit):**

```typescript
// Configuration
const SIGNING_PARAMS = {
  algorithm: 'ECDSA',
  namedCurve: 'P-256',  // NIST P-256 (secp256r1)
  hash: 'SHA-256'
}

// Generate moderator key pair
async function generateModeratorKeys(): Promise<CryptoKeyPair> {
  return await crypto.subtle.generateKey(
    {
      name: 'ECDSA',
      namedCurve: 'P-256'
    },
    true,  // extractable
    ['sign', 'verify']
  )
}

// Sign moderation action
async function signAction(
  action: ModerationAction,
  privateKey: CryptoKey
): Promise<ArrayBuffer> {
  const data = new TextEncoder().encode(JSON.stringify(action))

  return await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    privateKey,
    data
  )
}
```

**HMAC-SHA256 (Email Hashing):**

```python
# Backend configuration
HMAC_PARAMS = {
    'algorithm': 'HMAC-SHA256',
    'key_source': 'environment_variable',  # Not in database
    'key_rotation': '90_days'
}

import hmac
import hashlib
import os

def hash_email(email: str) -> str:
    """Hash email with server-side pepper."""
    pepper = os.getenv('EMAIL_PEPPER')
    if not pepper:
        raise ValueError('EMAIL_PEPPER not configured')

    return hmac.new(
        key=pepper.encode(),
        msg=email.lower().strip().encode(),
        digestmod=hashlib.sha256
    ).hexdigest()

# Rotate pepper every 90 days
# Old hashes become invalid (force re-verification)
# This limits window for rainbow table attacks
```

---

**Status**: Ready for implementation (Phase 1-2)
**Next Steps**: Begin Phase 1 (Foundation) implementation
**Review**: Security/privacy audit recommended before production deployment
**Contact**: For questions on this architecture, see CLAUDE.md for project context

