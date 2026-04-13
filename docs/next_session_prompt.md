# Recommended: Federation ADR (`federation_adr`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-12

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session completed `token_purchase_ui` — Stripe checkout -> blinded tokens flow with claim_secret auth, Stripe-backed claim tracking, and TokenBalance extension UI. The launch checklist now has 3 items remaining (all P3 except this P0). The distribution pivot memo (2026-04-10) set the roadmap as "Ops hardening -> SF onboard -> federation queries." This ADR documents the federation architecture to unblock that final step.

## What's Needed

Write an Architecture Decision Record for federation boundaries. This is a documentation/design task, not implementation. The ADR should cover:

1. **Which protocols change vs. stay** — What's shared across jurisdictions (token issuance, voice, identity) vs. what's per-jurisdiction (data, relay endpoints, sync)
2. **Execution model for cross-jurisdiction queries** — How `walk_scope` fans out to parent/sibling jurisdictions, latency implications, failure modes
3. **Trust chain design** — How relays verify each other's attestations, how token issuers from different jurisdictions interoperate
4. **Federation vs. replication** — Where data lives vs. where it's queried, caching strategy

## Existing Context to Read

- `docs/public/decisions/` — Existing ADRs (vector storage, entity IDs, federation, tool scope)
- `docs/public/relay/overview.md` — Relay architecture, trust model
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py` — Acceptance policy tiers
- `packages/civicos-relay/src/civicos_relay/voice/` — Voice + crypto modules
- `apps/civicos-mcp/tools/scope_walk.py` — `walk_scope` implementation
- `docs/public/decisions/tool_scope_and_federation.md` — Current scope/federation decision

## Success Criteria

- [ ] ADR written at `docs/public/decisions/federation_boundaries.md`
- [ ] Documents protocol boundaries (shared vs. per-jurisdiction)
- [ ] Documents cross-jurisdiction query execution model
- [ ] Documents trust chain for multi-relay federation
- [ ] References existing ADRs where relevant
- [ ] A new P0 assigned before session end

## Remaining Launch Items After This

| Priority | Item | Category |
|----------|------|----------|
| P3 | `operator_relay_dockerfile` | operator_readiness |
| P3 | `direct_city_submission` | federation_testbed |

## Open PRs

None.
