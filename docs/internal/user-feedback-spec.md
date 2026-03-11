# User Feedback Spec

**Status:** Draft
**Date:** 2026-03-09
**Depends on:** Launch Readiness Spec (coordination layer, authorization model, relay federation)

CivicOS needs a user feedback channel before launch. This spec describes a feedback system built on the relay's coordination layer — the same Nostr-signed infrastructure that handles voices, comments, and attestations.

## Design Principles

1. **Built on our own infrastructure.** Feedback flows through the relay as signed Nostr events. This dogfoods the coordination layer and produces cryptographically attributable feedback without requiring a separate account system.

2. **Surface-agnostic.** The feedback UI is a shared Svelte component (`CivicFeedbackForm`) in `civicos-components`. The extension is the first consumer, but any surface (web app, embedded widget, future mobile) can use it. The component emits structured data; the consumer handles signing and submission.

3. **Complementary to launch readiness.** This spec adds one new coordination event kind, one relay endpoint, one shared component, and one MCP admin tool. It does not introduce new authorization mechanisms — it uses the existing Nostr signature layer (Layer 2 from launch readiness spec) for signed submissions.

---

## Event Kind

```python
# packages/civicos-relay/src/civicos_relay/nostr/kinds.py
CIVIC_FEEDBACK = 1804  # Regular (non-addressable) — allows multiple submissions per user
```

**Why regular, not addressable:** Users should be able to submit multiple feedback items. Addressable kinds (30xxx) enforce one-per-key-per-d-tag, which fits voices (one stance per entity) but not feedback.

**Event structure:**

| Field | Value |
|-------|-------|
| kind | 1804 |
| content | Free-text feedback body |
| pubkey | Submitter's Nostr public key (or empty for anonymous) |
| sig | Schnorr signature over serialized event (or empty for anonymous) |
| created_at | Unix timestamp |
| tags | See below |

**Tags:**

| Tag | Required | Example | Purpose |
|-----|----------|---------|---------|
| `t` | Yes | `bug`, `feature`, `general` | Feedback type |
| `j` | Yes | `city-san-rafael` | Jurisdiction context |
| `v` | Yes | `1` | Schema version |

The `t` tag uses the same convention as NIP-12 hashtags. Three types at launch:

- **bug** — Something is broken or wrong
- **feature** — Something is missing or could be better
- **general** — Everything else (praise, confusion, questions)

---

## Anti-Spam

### Signed Feedback (Extension Users)

**Rate limiting per pubkey:** 10 submissions per hour, enforced at the relay endpoint. The relay already tracks pubkeys for voice operations; feedback uses the same mechanism.

Why this is sufficient for launch:
- Pilot users are attested San Rafael residents — a small, known population
- Generating new Nostr keys is possible but doesn't grant attestation, limiting abuse utility
- Rate limits can be tightened post-launch if needed

### Anonymous Feedback (Future)

Not implemented at launch. The pilot population all has the extension (and therefore keys). For users without the extension, the public docs site includes a contact email and GitHub Issues link.

If anonymous feedback is added later, options include:
- IP-based rate limiting (3/hour) — simple, imperfect
- NIP-13 proof-of-work — elegant, adds client complexity
- CAPTCHA — effective, poor UX

This is a post-launch decision based on observed demand.

---

## Implementation

### 1. Relay Storage

**Migration:** `scripts/sql/add_feedback.sql`

```sql
CREATE TABLE coordination_feedback (
  id SERIAL PRIMARY KEY,
  public_key TEXT NOT NULL,
  feedback_type TEXT NOT NULL CHECK (feedback_type IN ('bug', 'feature', 'general')),
  content TEXT NOT NULL,
  jurisdiction TEXT NOT NULL,
  signature TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_feedback_jurisdiction ON coordination_feedback(jurisdiction);
CREATE INDEX idx_feedback_type ON coordination_feedback(feedback_type);
CREATE INDEX idx_feedback_received ON coordination_feedback(received_at DESC);
```

**Storage class:** `PostgresFeedbackStorage` following `PostgresVoiceStorage` pattern in `packages/civicos-relay/src/civicos_relay/storage/postgres.py`. Methods:

- `save_feedback(feedback) -> None` — INSERT (no upsert)
- `get_feedback(jurisdiction, type?, limit?, offset?) -> list[Feedback]` — Query with optional filters
- `get_feedback_count(jurisdiction, type?) -> int` — Count for admin dashboards

**Rate limiting:** Check `COUNT(*) WHERE public_key = %s AND received_at > NOW() - INTERVAL '1 hour'` before insert. Return 429 if >= 10.

### 2. Relay Endpoint

```
POST /coordination/feedback
  Request: { feedback_type, content, jurisdiction, public_key, signature, created_at }
  Response: 201 { id, received_at } | 400 (invalid signature) | 429 (rate limited)

GET /coordination/feedback?jurisdiction=...&type=...&limit=...&offset=...
  Response: 200 [ { id, feedback_type, content, jurisdiction, public_key, created_at, received_at } ]
  Auth: Admin API key (per launch readiness spec Layer 3)
```

The POST endpoint verifies the Nostr signature using the same `VoiceService.verify()` path. The GET endpoint requires admin auth — feedback is not public-facing data.

### 3. Client API

**`packages/civicos-client/src/events.ts`:**

```typescript
export function createFeedbackEventContent(
  type: string,
  content: string,
): string {
  return JSON.stringify({ type, content, v: 1 });
}

export function createFeedbackTags(
  type: string,
  jurisdiction: string,
): string[][] {
  return [['t', type], ['j', jurisdiction], ['v', '1']];
}
```

**`packages/civicos-client/src/api.ts`:**

```typescript
async submitFeedback(
  feedbackType: string,
  content: string,
  jurisdiction: string,
  publicKey: string,
  signature: string,
  createdAt: number,
): Promise<boolean>
```

Follows the same fire-and-forget pattern as `submitVoice`.

### 4. Shared Component

**`packages/civicos-components/src/components/CivicFeedbackForm.svelte`**

```svelte
<svelte:options customElement="civic-feedback-form" />
```

**Props:**

| Prop | Type | Default | Purpose |
|------|------|---------|---------|
| `jurisdiction` | `string` | `''` | Pre-filled jurisdiction |
| `disabled` | `boolean` | `false` | Disable when identity locked |
| `onsubmit` | `(detail) => void` | — | Callback with `{ type, content }` |

**Behavior:**
- Three-option type selector (bug / feature / general)
- Textarea for free-text content (min 10 chars, max 2000 chars)
- Submit button with loading and success states
- Success state auto-clears after 3 seconds
- Styled with `--civic-*` CSS custom properties (inherits from consumer)

**The component does NOT:**
- Know about Nostr keys or signing
- Make network requests
- Store state beyond the current form
- Assume any particular host surface

### 5. Extension Integration

**Trigger:** Floating action button (FAB) in the side panel. Visible on all views. Toggles the feedback form as an overlay or slide-up panel.

**Wiring:**

```svelte
<CivicFeedbackForm
  jurisdiction={jurisdiction}
  disabled={!identity?.isUnlocked}
  onsubmit={handleFeedback}
/>
```

```typescript
async function handleFeedback({ type, content }) {
  const createdAt = Math.floor(Date.now() / 1000);
  const serialized = createFeedbackEventContent(type, content);
  const signature = await signer.sign(serialized);
  api.submitFeedback(type, content, jurisdiction,
    identity.publicKey, signature, createdAt).catch(() => {});
}
```

Follows the same optimistic pattern as `handleVoice` — submit and forget, no spinner on the main UI.

### 6. MCP Admin Tool

```
query_feedback(jurisdiction, type?, limit?)
  → Returns recent feedback items with counts by type
  → Wraps PostgresFeedbackStorage.get_feedback()
```

This aligns with the launch readiness spec's MCP-native administration principle. Operators review feedback by talking to their MCP server, not by logging into a dashboard.

---

## Federation Behavior

Feedback events are **local to the receiving relay.** They do not federate via peer sync.

Rationale:
- Feedback is operational data for the relay operator, not civic coordination data
- A civic org's relay receives feedback about that org's service, not about another operator's
- Federating feedback would leak operational concerns across trust boundaries
- If cross-operator feedback aggregation is needed later, it can be added as an opt-in sync filter

This is consistent with the launch readiness spec's namespace filtering design — sync filters control what crosses relay boundaries.

---

## Sequencing

| Step | Package | Depends On |
|------|---------|------------|
| 1. SQL migration + storage class | civicos-relay | Nothing |
| 2. Relay endpoint with rate limiting | civicos-relay | Step 1 |
| 3. Client API methods | civicos-client | Step 2 (for testing) |
| 4. `CivicFeedbackForm` component | civicos-components | Nothing (parallel with 1-3) |
| 5. Extension FAB + integration | civicos-extension | Steps 3, 4 |
| 6. MCP admin tool | civicos-mcp | Step 2 |

Steps 1-3 and step 4 can run in parallel. Total estimated scope: 1 session.

---

## What's NOT In This Spec

- **Anonymous feedback** — Deferred to post-launch. Contact email and GitHub Issues cover the gap.
- **Feedback categories beyond three** — Start minimal. Add categories based on what users actually submit.
- **Feedback response/resolution workflow** — Operators read feedback via MCP. No ticketing system. If volume demands it, that's a separate spec.
- **Auto-context capture** — The component could capture what view/entity the user was on. Deferred for simplicity; easy to add as an optional prop later.
- **Feedback analytics/dashboards** — The MCP tool provides raw access. Analytics tooling is post-launch.
