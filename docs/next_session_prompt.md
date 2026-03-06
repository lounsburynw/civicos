# Recommended: MCP API Key Gate + Privacy-Preserving Relay Billing

**Priority:** P0 is `turnkey_city_deployment` (deferred). Recommend this instead — cheap infrastructure that enables monetization if volume arrives.
**Area:** deployment_artifacts > api_server
**Date:** 2026-03-05

> This is recommended context from Session 25. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 25 moved the AI proxy from MCP to relay (security fix — signature verification was silently bypassed). The relay is now the metered gateway for all authenticated AI requests. MCP is purely public civic data.

Two billing surfaces exist:
1. **MCP** (commercial API access) — journalists, newsrooms, AI platforms querying civic data. These users expect to identify themselves. Standard API key + Stripe works fine.
2. **Relay** (resident AI access) — attested residents using /ai/draft and /ai/chat. These users have Nostr pseudonymous identity. We've spent significant effort on privacy (Nostr keys, attestation without PII, Schnorr signatures). Billing must not undo that.

## Privacy Constraint

The current `api_keys.py` schema stores `stripe_customer_id` alongside `key_id` in the same row. Usage logs link `key_id` to endpoints + timestamps. If a resident's Nostr pubkey is linked to a Stripe customer (name, email, payment method), every civic question they asked becomes attributable to a real person. This is a surveillance-ready data model for civic inquiry — unacceptable.

**Requirement:** Resident AI billing must preserve pseudonymity. The payment system must not be joinable to the query log.

## Two-Part Task

### Part 1: MCP API Key Gate (~1-2hrs)

Wire existing `ApiKeyStore` into MCP REST endpoints. This is straightforward — commercial users identify themselves.

- **No key**: public rate limit (60 req/min per IP) — civic access stays free
- **Valid key**: tier-based rate limit (60-1000 req/min) — commercial access
- **Invalid key**: 401
- **No Platform DB**: graceful pass-through

**Key files:**
- `apps/civicos-mcp/rest_api.py:155` — REST router where middleware attaches
- `packages/civicos-services/src/civicos_services/core/api_keys.py` — `ApiKeyStore`
- `scripts/sql/add_platform_billing.sql` — DB migration

**Don't break internal calls:** The relay calls MCP REST endpoints for /ai/chat tool execution (server-to-server, no API key). Give the relay its own internal API key, or set the unauthenticated limit high enough (60 req/min per IP should suffice).

### Part 2: Design Privacy-Preserving Relay Billing (~1hr design)

Design (don't build yet) the billing model for resident AI access. The goal: frictionless payment by non-technical users while preserving the pseudonymity we've architected.

**Approach: Stripe with architectural data separation.**

The insight: separate the system that knows "who paid" from the system that knows "what they asked." Both exist, but they never share a key.

```
Stripe (knows identity)          Relay (knows queries)
  |                                |
  |-- payment confirms -->  credit ledger (pubkey + balance)
  |                                |
  |  (no query data)        (no identity data)
```

Concrete design:
- **Credit ledger table** on relay DB: `pubkey`, `credits_remaining`, `last_topped_up`. No Stripe ID, no email, no name.
- **Stripe checkout** is a one-shot interaction: user pays, webhook increments credits for a pubkey, Stripe receipt goes to their email. The relay only stores the pubkey + credit count.
- **Usage deducts credits** from the ledger. Query logs reference pubkey only (already the case).
- **The join doesn't exist in any single database.** Stripe knows "jane@email.com paid $5 to CivicOS." The relay knows "pubkey abc123 asked about housing policy." Neither system can reconstruct "Jane asked about housing."

This is option 3 from the privacy spectrum — Stripe with enforced data separation. It's frictionless (Stripe checkout is familiar UX), preserves pseudonymity (no identity in the relay DB), and is architecturally enforced (not just a policy).

**Deliverable for Part 2:** A short design doc or ADR in `docs/decisions/` with the credit ledger schema, the Stripe webhook flow, and the data separation invariant. No code yet — just the design for a future session to implement.

## What's Already Built
- `api_keys.py` — Full `ApiKeyStore` with Stripe integration (works for MCP commercial keys as-is)
- `billing.py` — Stripe checkout + webhook endpoints
- `scripts/sql/add_platform_billing.sql` — DB migration for platform tables
- Tier config: free (60/min), journalist (120/min), organization (300/min), city (600/min), api (1000/min)
- Relay already tracks per-pubkey usage (rate limits in ai_proxy.py)

## Success Criteria
- [ ] MCP REST endpoints gated with optional API key middleware
- [ ] Unauthenticated = rate-limited, valid key = tier limits, invalid = 401
- [ ] Relay → MCP tool calls still work
- [ ] No Platform DB = graceful pass-through
- [ ] Design doc for privacy-preserving relay billing (credit ledger + data separation)
- [ ] **Invariant documented:** no single database can join payment identity to query content
