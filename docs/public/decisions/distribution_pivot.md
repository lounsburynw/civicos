# ADR: Distribution Pivot -- OAuth + Free Tier Before Billing

**Status:** Accepted
**Date:** 2026-04-10

## Context

After a month of intensive ingestion/data work (Mar 10 - Apr 10), CivicOS has:
- 23 jurisdictions configured (Marin 11 cities + county, SF, Alameda County, Berkeley, Sacramento, 2 school districts, state + federal)
- 10 platform extraction clients working in production
- Automated cron refresh across all jurisdictions/corpora
- 40+ MCP tools deployed on Modal
- launch.json at 143/151 items complete (95%)

The remaining 8 items are: 3 Stripe billing plumbing, 1 token purchase UI, 1 operator Dockerfile, 3 federation refinements. None are user-facing.

The bottleneck shifted from "is the data good enough" to "can anyone use this." The MCP server is deployed but only accessible via manually-configured Bearer tokens in Claude Desktop.

## Decision

**Prioritize distribution over billing.** Implement MCP OAuth to enable Claude.ai web/mobile connector access, launch with a free tier, and defer Stripe billing until real usage data informs the billing model.

### Ordering

1. **MCP OAuth 2.0 provider** (P0) -- Claude.ai connector access for web + mobile users
2. **Free tier with rate limiting** (P1) -- Generous free tier (e.g. 50 queries/day) without API key purchase
3. **Stripe billing** (deferred) -- Wire up after collecting usage patterns from free-tier users

### Rationale

- **OAuth is the biggest distribution unlock.** Every Claude.ai user can connect in 2 clicks vs. buying an API key and editing config files.
- **Billing model is uncertain.** Usage logging is live but has no real traffic. Flat subscription vs. metered vs. hybrid can't be decided without data.
- **Free tier is sufficient for launch.** Civic data is public. A free tier with rate limiting covers casual use and lets us observe real usage patterns.
- **Stripe can be wired retroactively.** Adding paid tiers on top of an OAuth-authenticated free tier is straightforward. The reverse (bolting OAuth onto a Stripe-first system) is more awkward.

## Consequences

- The 3 `billing_payments` items and `token_purchase_ui` are deferred, not abandoned
- `add_real_source_item_id` demoted from P0 to P2 (synthetic hash works, no observed collisions)
- New `distribution` category added to launch.json
- Usage data from free-tier users will inform the Stripe billing model when we return to it

## Alternatives Considered

1. **Finish the checklist linearly** -- Complete remaining 8 items in priority order. Rejected: all inward-facing, no users.
2. **Stripe first, then OAuth** -- Wire billing before distribution. Rejected: premature optimization of a billing model with no usage data.
3. **Skip OAuth, use API keys only** -- Higher friction, limits audience to developers who read docs. Rejected: Claude.ai connector is the highest-leverage onramp.
