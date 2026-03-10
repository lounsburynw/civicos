# Relay Acceptance Policy & Payment Architecture Spec

**Status:** Implemented (Phase 1 — rate limiting + write tool removal). Phases 2-4 pending.
**Date:** 2026-03-10
**Reviewed by:** Architecture agent, Security agent, Cashu feasibility agent

## Problem

All relay write endpoints (voice, comment, initiative, action) verify Schnorr signatures but enforce no further acceptance criteria. Any valid secp256k1 keypair can write unlimited data to the relay, driving up Supabase costs and polluting voice counts with sybil keypairs.

Simultaneously, the MCP server bundles write tools (`broadcast_voice`, `prepare_initiative`, etc.) alongside read-only civic data tools, creating a layering mismatch: the MCP tier-gates tool access, but the relay endpoint itself is wide open. Anyone who knows the relay URL can POST directly, bypassing MCP tier checks entirely.

## Design Principles

1. **Relay provider sovereignty** — each relay operator sets their own acceptance policy. One relay might require physical attestation for voices; another might run fully open.
2. **Privacy preservation** — write access must not require revealing real identity to the relay. Both attestation and payment proofs are bearer credentials with no identity linkage.
3. **Surface separation** — the MCP serves read-only civic data (Stripe-gated). The relay handles writes (acceptance policy-gated). These are separate concerns for separate populations.
4. **Client display autonomy** — the relay stores voices faithfully with their proof metadata. Clients decide how to weight or filter (attested vs. unattested). This is not the relay's job.

---

## Refactor 1: Remove Write Tools from MCP

### Current State

The MCP tool registry (`apps/civicos-mcp/tools/registry.py`) includes 8 coordination/write tools mixed with ~35 read-only civic data tools:

- `prepare_voice`, `broadcast_voice`
- `prepare_initiative`, `broadcast_initiative`
- `subscribe_to_topic`, `list_relays`
- `get_voice_counts`, `list_initiatives`

These are gated at the MCP tier level (`builder` tier required in `api_keys.py`), but the relay endpoints they call have no access control.

### Analysis

The write tool handlers (`tools/handlers.py` lines 3070-3885) have **zero dependency on CivicOS civic data**. They:
- Never use the `civic` (CivicOS API) parameter
- Make HTTP POST/GET calls to the relay API
- Use only `jurisdiction`, `validate_input`, `logger`, and `args`

The codebase already categorizes them separately: `CROSS_LEVEL_TOOLS` and `COORDINATION_TOOLS` in `handlers/loader.py`.

### Change

Disable write tools from the MCP deployment. Read-only tools that query relay state (`get_voice_counts`, `list_initiatives`, `list_relays`) may remain — they are GET operations, not writes.

**Tools to remove from MCP:**
- `prepare_voice`
- `broadcast_voice`
- `prepare_initiative`
- `broadcast_initiative`
- `subscribe_to_topic`

**Tools to keep (read-only relay queries):**
- `get_voice_counts`
- `list_initiatives`
- `list_relays`

**Implementation:** Add an exclusion list to the handler loader in `handlers/loader.py`. The `ToolRegistry` class currently loads all `TOOL_DEFINITIONS` unconditionally; the filtering must happen at handler binding time (where tools become active). No code deletion needed — handlers remain available for future use or a dedicated relay MCP.

**Bug found during review:** The `prepare_initiative` tool description references "ECDSA P-256" signing, but the project uses secp256k1 Schnorr (per CLAUDE.md). This documentation bug should be fixed as part of this change.

### Impact on Tier System

The `builder` tier in `api_keys.py` currently gates write tools. After this change:
- `builder` tier tools list shrinks to read-only participation aids: `get_public_testimony`, `search_agenda_packets`, `compose_public_comment`, `get_decision_context`, `prepare_for_meeting`, `neighborhood_report`, `get_item_context`
- These remain valuable — they're LLM-intensive read operations (context assembly, comment drafting) that justify a paid tier
- `prepare_voice`/`broadcast_voice` move out of tier gating entirely — the relay's acceptance policy replaces MCP tier checks

---

## Refactor 2: Relay Acceptance Policy Layer

### Architecture

A configurable policy layer that sits between signature verification and storage on all write endpoints.

```
POST /coordination/voice
  1. Parse request, build Voice model
  2. Verify Schnorr signature (existing) → 400 if invalid
  3. Check acceptance policy (NEW) → 402/403 if rejected
  4. Save to storage (existing)
```

### Acceptance Policy Configuration

Per-relay, per-event-type configuration:

```yaml
acceptance_policy:
  voice:
    require_one_of: [attestation, payment, rate_limit]
    attested_limit:
      max_per_key_per_day: 50    # Generous for active residents, caps abuse
    paid_limit:
      max_per_key_per_day: 100   # Higher — they're paying per action
    rate_limit:
      max_per_key_per_day: 3     # Taste tier — enough to try, not to spam
      pow_difficulty: 20
  comment:
    require_one_of: [attestation, payment, rate_limit]
    attested_limit:
      max_per_key_per_day: 20
    paid_limit:
      max_per_key_per_day: 50
    rate_limit:
      max_per_key_per_day: 3
      pow_difficulty: 20
  initiative:
    require_one_of: [attestation, payment]
    attested_limit:
      max_per_key_per_day: 5     # Creating initiatives is high-impact
    paid_limit:
      max_per_key_per_day: 10
    # No free tier for initiative creation (higher spam risk)
  action_commit:
    require_one_of: [attestation, payment, rate_limit]
    attested_limit:
      max_per_key_per_day: 50
    paid_limit:
      max_per_key_per_day: 100
    rate_limit:
      max_per_key_per_day: 10
      pow_difficulty: 20
  action_complete:
    require_one_of: [attestation, payment, rate_limit]
    attested_limit:
      max_per_key_per_day: 50
    paid_limit:
      max_per_key_per_day: 100
    rate_limit:
      max_per_key_per_day: 10
      pow_difficulty: 20
  feedback:
    require_one_of: [rate_limit]
    rate_limit:
      max_per_key_per_day: 5
      pow_difficulty: 0
    # Feedback is always free — platform improvement signal
```

**Rate limit rationale:** All tiers are rate-limited. Attestation proves personhood, not intent — an attested key farm (which requires physical attendance per key) caps at 50 writes/key/day, making the ROI of farming attestation events terrible. Paid users get higher limits since each write costs them money. Free tier is a taste — enough to experience the platform, not enough to influence outcomes.

### Three Proof Types

#### 1. Attestation Proof (Free, Unlimited)

Existing infrastructure. Voice/Comment models already have `attestation_proof: Optional[dict]`. Verification function `verify_attestation_proof()` in `voice/crypto.py` is complete and tested.

**What's needed:**
- Wire `verify_attestation_proof()` into write endpoints
- Look up trusted issuer pubkey for the jurisdiction (from `issuer_registry` table)
- Accept write if proof is valid

#### 2. Payment Proof (Blinded Tokens, Per-Action)

Privacy-preserving bearer tokens. The relay (or a separate token service) issues blinded tokens after payment. The relay can verify the signature but cannot link it to the original payment.

**Cashu was evaluated and deferred.** Independent feasibility review found:
- Every major Cashu implementation carries "early development" warnings (pre-1.0)
- Operating a Cashu mint likely requires money transmitter licensing (FinCEN MSB + state licenses)
- Stripe-to-Cashu bridge likely violates Stripe ToS (virtual currency sales)
- 3-5 weeks of client integration work for uncertain ecosystem stability

**Recommended alternative: Blind signature tokens** using existing secp256k1 primitives. This provides the same core privacy property (unlinkable bearer tokens) without mint operation, regulatory exposure, or ecosystem dependency. The acceptance policy abstraction accommodates swappable proof types — if Cashu matures and regulatory clarity improves, migration is straightforward.

**Flow (blind signature scheme):**
1. User pays via Stripe checkout (or Lightning) to a token issuance service
2. Service signs blinded tokens — it cannot link issued tokens to the payment session
3. User unblinds tokens, stores in extension wallet
4. Extension includes token in write request
5. Relay verifies signature, marks token as spent, accepts write
6. No identity linkage between payment and pubkey

**What's needed:**
- `payment_proof: Optional[dict]` field on Voice/Comment/Action models
- Blind signature issuance endpoint (separate from relay)
- Token verification + spent-token tracking in acceptance policy
- Token wallet in extension (`local-wallet.ts` already handles secp256k1)
- Token purchase UI in extension

**Privacy caveat (Stripe funding path):** The Stripe-to-token bridge provides weaker privacy than direct Lightning funding. Timing and amount correlation between Stripe purchase and token redemption is possible if the operator chooses to correlate databases. This is a policy guarantee, not a technical one. Privacy-sensitive users should fund via Lightning. The blind signature scheme prevents the bridge from linking specific tokens to the payment session, but batch-level correlation remains possible.

**Cashu migration path:** The `payment_proof` field and `AcceptancePolicy` abstraction are proof-type-agnostic. If Cashu reaches production readiness and regulatory clarity, adding it as an additional payment proof type requires only a new verifier implementation — no model or API changes.

#### 3. Rate Limit (Free Tier, Capped)

No proof required. The relay tracks writes per pubkey per day and accepts up to the configured limit.

**Sybil resistance caveat:** Per-pubkey rate limiting alone provides zero sybil resistance. Generating secp256k1 keypairs is free and instant — an attacker can create 1,000 keys in under a second, each getting 3 free voices/day. This tier is a UX on-ramp, not a security boundary.

**Mitigation: NIP-13 proof of work.** Require a minimum difficulty on the Nostr event ID hash for rate-limited tier writes (e.g., 20-bit target ≈ 1 second of computation). This is:
- Computationally cheap to verify on the relay
- Expensive to mass-produce across thousands of sybil keys
- Aligned with the Nostr ecosystem (NIP-13 is a recognized standard)
- Barely noticeable to legitimate single-key users

**What's needed:**
- Per-pubkey write counter (PostgreSQL)
- Counter reset on calendar day (UTC)
- HTTP 402 response when limit exceeded, with guidance on attestation or payment
- NIP-13 proof-of-work verification for rate-limited tier (required)
- HTTP-level per-IP rate limiting as first line of defense (before crypto verification)

**Rate limit storage:**
- PostgreSQL: `relay_rate_limits(public_key_hash, event_type, date, count)` — use hashed pubkey to reduce privacy exposure
- TTL/cleanup: daily partitions, drop partitions older than 7 days to prevent unbounded table growth from key farming
- Worst-case cost: at 10,000 sybil keys × 3 voices/day = 30,000 rows/day in voices + 10,000 rows/day in rate_limits. With 7-day TTL on rate_limits and PoW requirement, this is manageable at Supabase pricing.

### Policy Evaluation Logic

```python
class AcceptancePolicy:
    def check(self, event_type: str, public_key: str,
              attestation_proof: dict | None,
              payment_proof: dict | None,
              event_id: str | None = None) -> PolicyResult:
        """
        Returns PolicyResult with:
          - accepted: bool
          - reason: str
          - tier: "attested" | "paid" | "rate_limited" | "rejected"

        All tiers are rate-limited. Attestation/payment determine the
        tier (which sets the limit), not whether a limit exists.
        """
        config = self._config[event_type]
        allowed = config["require_one_of"]

        # Determine tier (best proof wins)
        tier = None

        if "attestation" in allowed and attestation_proof:
            if self._verify_attestation(attestation_proof, public_key):
                tier = "attested"

        if tier is None and "payment" in allowed and payment_proof:
            if self._verify_payment(payment_proof):
                tier = "paid"

        if tier is None and "rate_limit" in allowed:
            # Free tier requires proof of work
            pow_difficulty = config.get("rate_limit", {}).get("pow_difficulty", 0)
            if pow_difficulty > 0 and not self._verify_pow(event_id, pow_difficulty):
                return PolicyResult(accepted=False, reason="Insufficient proof of work")
            tier = "rate_limited"

        if tier is None:
            return PolicyResult(accepted=False, reason="No valid proof")

        # All tiers have rate limits — check the tier-specific limit
        limit_key = {
            "attested": "attested_limit",
            "paid": "paid_limit",
            "rate_limited": "rate_limit",
        }[tier]
        max_per_day = config.get(limit_key, {}).get("max_per_key_per_day", 3)

        if not self._check_rate_limit(public_key, event_type, max_per_day):
            return PolicyResult(
                accepted=False,
                tier=tier,
                reason=f"Daily {tier} limit reached ({max_per_day}/day)",
            )

        return PolicyResult(accepted=True, tier=tier)
```

### HTTP Response on Rejection

```
HTTP 402 Payment Required
{
  "error": "acceptance_policy",
  "message": "Daily voice limit reached for unattested keys",
  "options": [
    {"type": "attestation", "description": "Get attested at a local event for free unlimited access"},
    {"type": "payment", "description": "Pay per voice with Cashu tokens", "mint": "https://mint.civicosproject.org"}
  ]
}
```

The extension can parse this response and guide the user to get attested or fund their wallet.

---

## Payment Architecture Summary

Two payment systems, two populations, zero overlap:

| System | Surface | Payer | What they buy | Privacy |
|--------|---------|-------|---------------|---------|
| **Stripe** | MCP / REST API | Developers, journalists, orgs | Read access to civic data (subscriptions) | Email + credit card (B2B, accepted tradeoff) |
| **Blinded tokens** | Relay (via extension) | Residents, participants | Write access to relay (per-action) | Pseudonymous (blind signatures prevent linkage) |

**Funding paths for blinded tokens:**
- **Stripe checkout** → token issuance service → blinded tokens in extension wallet. Convenient but weaker privacy (timing/amount correlation possible by operator).
- **Lightning payment** → token issuance service → blinded tokens. Stronger privacy. Recommended for privacy-sensitive users.

**Cashu** remains a future option if the ecosystem matures. The acceptance policy abstraction supports adding Cashu as a proof type without architectural changes.

---

## Agent Identity Conventions

Agents (bots, monitors, automated services) are first-class participants in the coordination protocol. They hold their own Nostr keypairs, submit signed events, and are subject to the same acceptance policy as humans. The protocol does not distinguish agents from humans at the write layer — this is intentional.

**Convention, not enforcement.** Agent builders are encouraged (not required) to self-declare via a Nostr kind-0 profile event:

```json
{
  "name": "SR Housing Monitor",
  "about": "Tracks housing-related agenda items in San Rafael. Created by @builder.",
  "bot": true
}
```

The `bot` field follows the existing Nostr convention (NIP-24). Developer docs should recommend this as a best practice.

**Why encouragement, not enforcement:** Requiring `bot: true` for unattested writes creates an arms race where agents fake human profiles. The acceptance tier already provides a natural signal — agents will never have physical attestation, so they land in the "paid" or "rate_limited" tier. Clients can infer "no attestation = possibly an agent" from the tier alone. Self-declaration adds transparency on top of that signal without creating an adversarial dynamic.

**Client display:** The extension (and other clients) can look up a voice's pubkey profile and display accordingly:

| Profile state | Display |
|---|---|
| Has `attestation_proof` | "Verified resident" badge |
| Has kind-0 with `bot: true` | Agent name + description + "Bot" tag |
| No attestation, no bot profile | No special badge (tier visible if client chooses) |

**Future possibilities:**
- Agent directory per jurisdiction ("see all active agents in San Rafael")
- Agent reputation based on contribution history (initiatives created, accuracy of monitoring alerts)
- Builder attribution ("Built by [org]") linked from agent profiles

No relay changes are needed for this — it's a profile convention + client display logic.

---

## Model Changes

### Frozen Model Constraint

The `Voice` model has `model_config = {"frozen": True}`. Adding a mutable `acceptance_tier` that the relay sets after construction conflicts with this. Three options:

1. **Store `acceptance_tier` separately** — relay metadata table, not on the Pydantic model. Voice stays frozen. API responses join the tier from metadata. *(Recommended — cleanest separation of client-submitted data vs. relay-determined metadata.)*
2. **Set tier during construction** — policy check happens before model creation, tier is passed in. Requires restructuring endpoint flow.
3. **Remove frozen constraint** — simplest but loses immutability guarantees.

### Voice (existing fields + new)

```python
class Voice(BaseModel):
    # ... existing fields ...
    attestation_proof: Optional[dict] = None   # Existing, kind-30850
    payment_proof: Optional[dict] = None       # NEW, blinded token proof
    # acceptance_tier stored in relay metadata, NOT on frozen model
```

### Comment, CivicActionEvent, CivicCommitment, CivicCompletion

Same pattern: add `payment_proof` field.

### CastVoiceRequest (existing + new)

```python
class CastVoiceRequest(BaseModel):
    # ... existing fields ...
    attestation_proof: Optional[dict] = None   # Pass-through (MISSING TODAY — must add)
    payment_proof: Optional[dict] = None       # NEW
```

**Note:** `CastVoiceRequest` does not currently include `attestation_proof`. This must be added as a prerequisite for Phase 3.

### Relay Metadata (new)

```sql
CREATE TABLE relay_write_metadata (
    public_key_hash TEXT NOT NULL,
    entity TEXT NOT NULL,
    acceptance_tier TEXT NOT NULL,  -- 'attested', 'paid', 'rate_limited'
    accepted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (public_key_hash, entity)
);
```

API responses join this data when returning voices, so clients can filter/weight by tier.

---

## Implementation Phases

### Phase 0: Fix Existing Security Vulnerabilities (immediate, pre-requisite)

Security review uncovered two critical vulnerabilities in the current relay:

1. **`coincurve` ImportError silently disables ALL signature verification** (`crypto.py:28-33`). If the library isn't installed, `_schnorr_verify()` returns `True` for any input. This must become a hard failure in production.
2. **Optional `created_at` bypasses signature verification** on civic action endpoints (`app.py`). Omitting `created_at` (which is `Optional[int] = None`) skips the verify call entirely. All write endpoints must require `created_at` and reject writes without it.

These must be fixed before the acceptance policy is implemented — there's no point adding a security layer on top of bypassable signature verification.

### Phase 1: MCP Write Tool Removal (immediate)
- Add exclusion list to handler loader for write tools
- Update `builder` tier tool list in `api_keys.py`
- Fix `prepare_initiative` tool description (references P-256 ECDSA, should be secp256k1 Schnorr)
- Update MCP docs (`docs/public/mcp/setup.md`)
- No relay changes

### Phase 2: Rate-Limited Free Tier + HTTP Hardening (near-term)
- Add HTTP-level per-IP rate limiting (before crypto verification)
- Add `AcceptancePolicy` class to relay
- Add per-pubkey rate limiting (PostgreSQL counter with hashed pubkeys, 7-day TTL)
- Add NIP-13 proof-of-work requirement for rate-limited tier
- Wire into all write endpoints
- Return HTTP 402 when limit exceeded
- Add `relay_write_metadata` table for acceptance tier storage
- Update extension to handle 402 responses gracefully (UX for attestation/payment guidance)
- Add monitoring: policy rejections by tier, rate limit hits/day, total writes by tier

### Phase 3: Attestation Enforcement (near-term)
- Add `attestation_proof` to `CastVoiceRequest` and other request schemas (missing today)
- Wire existing `verify_attestation_proof()` into acceptance policy
- Add issuer pubkey lookup per jurisdiction (from `coordination_issuer_registry`)
- Add attestation expiry check (`created_at + validity_period > now`, recommend 1-year validity)
- Design attestation revocation mechanism (blocklist of revoked attestation event IDs)
- Attested voices get unlimited writes
- Store `acceptance_tier` in `relay_write_metadata`
- Define federation behavior: synced voices from other relays carry their source relay's acceptance tier as metadata; local policy is not re-evaluated on sync

### Phase 4: Blinded Token Payment (medium-term)
- Design blind signature scheme using existing secp256k1 primitives
- Implement token issuance service (separate from relay)
- Add token verification + spent-token tracking to acceptance policy
- Atomic verification: token must be marked spent BEFORE write is persisted (no race conditions)
- Add `payment_proof` to models and request schemas
- Add token wallet to extension (`local-wallet.ts`)
- Token purchase flow (Stripe checkout → blinded tokens, Lightning → blinded tokens)
- Failure mode: if token service is unreachable, reject write (do not queue)

**Cashu migration (future):** If Cashu ecosystem reaches production readiness and regulatory clarity improves, add Cashu as an additional payment proof verifier. The `AcceptancePolicy` abstraction supports this without model or API changes.

---

## Resolved Questions

1. ~~**Mint operation**~~ → **Deferred.** Using blind signature tokens instead of Cashu. No mint to operate.
2. ~~**Rate limit storage**~~ → **PostgreSQL** with hashed pubkeys and 7-day TTL partitions.
3. **Read-only relay queries in MCP** → **Yes**, keep `get_voice_counts`, `list_initiatives`, `list_relays`. They're GET operations useful for AI context.
4. **Initiative creation** → **Attested or paid only.** No free tier for initiatives (higher spam risk, spec already reflects this).

## Open Questions

1. **Pricing** — per-voice flat fee? Per-jurisdiction pricing? USD-pegged or sats? (Deferred to Phase 4 design.)
2. **Acceptance tier visibility** — should `acceptance_tier` be returned in API responses, or kept relay-internal? Returning it enables client filtering but leaks metadata about user behavior (e.g., "this pubkey attended an attestation event"). Recommendation: return tier in API responses but strip attestation `created_at` timestamps to reduce deanonymization surface.
3. **Attestation validity period** — 1 year recommended. Shorter periods increase attestation event frequency (operational burden); longer periods reduce revocation effectiveness.
4. **NIP-13 difficulty target** — 20-bit recommended (~1 second computation). Needs benchmarking on typical user devices (mobile browsers).
5. **Existing voice migration** — voices already stored without `acceptance_tier` need a default. Recommend backfilling as `"legacy"` tier (distinct from the three active tiers).

## Review Findings Tracker

Issues identified by independent agent reviews, tracked to resolution:

| # | Finding | Severity | Source | Status |
|---|---------|----------|--------|--------|
| 0a | `coincurve` ImportError silently passes all signatures | CRITICAL | Security | → Phase 0 |
| 0b | Optional `created_at` bypasses civic action sig verification | CRITICAL | Security | → Phase 0 |
| 1 | Free tier zero sybil resistance | CRITICAL | Security, Arch | → Phase 2 (NIP-13 PoW) |
| 2 | No HTTP-level rate limiting | HIGH | Security | → Phase 2 |
| 3 | Attestation proofs never expire / no revocation | HIGH | Security | → Phase 3 |
| 4 | Rate limit counter table unbounded growth | HIGH | Security, Arch | → Phase 2 (TTL partitions) |
| 5 | Frozen model conflict with `acceptance_tier` | MEDIUM | Arch | → Resolved (separate metadata table) |
| 6 | `CastVoiceRequest` missing `attestation_proof` | MEDIUM | Arch | → Phase 3 |
| 7 | Federation behavior for `acceptance_tier` unspecified | MEDIUM | Arch | → Phase 3 |
| 8 | Stripe-to-token bridge timing correlation | MEDIUM | Security, Cashu | → Phase 4 (documented caveat) |
| 9 | `acceptance_tier` leaks user metadata | MEDIUM | Security | → Open Question #2 |
| 10 | Cashu ecosystem pre-1.0 / regulatory risk | HIGH | Cashu | → Resolved (deferred Cashu, use blind tokens) |
| 11 | Extension UX for 402 under-specified | MEDIUM | Arch | → Phase 2 (needs UX design) |
| 12 | No monitoring/observability requirements | MEDIUM | Arch | → Phase 2 |
| 13 | Existing voice migration strategy | LOW | Arch | → Open Question #5 |
| 14 | Comment replay (no deduplication) | MEDIUM | Security | → Backlog |
