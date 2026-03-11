# Recommended: Stripe Secrets Deployment

**Priority:** P0
**Area:** billing_payments
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The usage logging and rollup pipeline is now complete — all three services (API, MCP, Relay) log requests to the Platform DB, and a daily rollup runs as part of `scheduled_high_velocity_refresh`. The next step in the billing pipeline is deploying Stripe secrets so the checkout/webhook endpoints can function.

## Recommended Task

Configure Stripe API keys and price IDs in Modal secrets so the billing endpoints can process payments. This is a prerequisite for `billing_endpoint_deployment` and `stripe_key_delivery_automation` (both P1).

## Key Files

- `.env.example:316-330` — Stripe env var names and descriptions
- `packages/civicos-services/src/civicos_services/core/stripe_billing.py` — Stripe billing logic (checkout, webhooks)
- `packages/civicos-services/src/civicos_services/core/api_keys.py` — API key provisioning (called after Stripe checkout)
- `apps/civicos-mcp/modal_mcp.py` — MCP server where billing endpoints need to be mounted
- `launch.json:104-111` — This item's checklist entry

## Suggested Approach

1. Check if Stripe account exists: does the user have `STRIPE_SECRET_KEY` already?
2. If yes, create Modal secret: `modal secret create civicos-stripe STRIPE_SECRET_KEY=sk_... STRIPE_WEBHOOK_SECRET=whsec_... STRIPE_PRICE_JOURNALIST=price_... STRIPE_PRICE_ORGANIZATION=price_... STRIPE_PRICE_CITY=price_... STRIPE_PRICE_API=price_...`
3. If no, guide user through Stripe Dashboard setup (create products/prices first)
4. Verify secret exists: `modal secret list | grep stripe`
5. Add secrets to local `.env` for dev testing
6. Mark `stripe_secrets_deployment` done in `launch.json`
7. Optionally continue to `billing_endpoint_deployment` (P1) — mount billing router in `modal_mcp.py`

## Tests to Run

```bash
# No automated test — verify via:
modal secret list | grep stripe
# Then optionally test billing import:
python3 -c "from civicos_services.core.stripe_billing import create_checkout_session; print('Import OK')"
```

## Success Criteria

- [ ] Stripe secrets configured in Modal (`civicos-stripe` or added to `civicos-env`)
- [ ] Stripe env vars added to local `.env`
- [ ] `stripe_secrets_deployment` marked done in `launch.json`

## What Changed This Session (uncommitted)

1. `scripts/modal_ingest.py` — Added `civicos-platform` secret + usage rollup logic to daily high-velocity refresh
2. `scripts/modal_usage_rollup.py` — Removed cron (now runs via ingest), added psycopg2 image for manual runs
3. `scripts/modal_vectors.py` — Removed redundant weekly cron (daily ingest covers vector indexing)
4. `launch.json` — `deploy_usage_rollup` marked done, `stripe_secrets_deployment` set as P0

## Infrastructure Notes

- **Platform DB**: Supabase project `axhmnnvefrtliyszbuou` (us-west-1), pooler URL required for Modal (IPv6 not supported)
- **Modal cron limit**: 5 crons max on current plan. 4 are in `civic-ingest`, 1 slot freed by removing `civic-vectors` cron. There may be a phantom 5th cron Modal is counting — if you need another cron slot, investigate via Modal GUI or contact support.
- **Stale MCP apps**: `civicos-marin-county` (19d idle), `civicos-federal` (20d), `civicos-california` (20d), `civicos-personal-mcp` (30d), `civicos-mcp-apps` (30d) — safe to stop if resources needed, but they're just idle web endpoints.
