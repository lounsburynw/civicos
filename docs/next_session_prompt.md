# Recommended: Deploy Marin Test Relays

**Priority:** P0 (`deploy_marin_test_relays`)
**Area:** federation_testbed (Phase A)
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Mill Valley and San Anselmo have been onboarded (meetings + agenda items in PostgreSQL). The next federation step is deploying separate relay instances for these jurisdictions on Modal. This validates multi-relay deployment — same code, different jurisdiction config. These are private, not public-facing.

The existing San Rafael relay is deployed at `apps/civicos-relay/modal_relay.py`. The task is to deploy 2 additional instances.

## What Was Completed This Session

`query_interface_operators` (P0) is done:
- 23 live-data integration tests against PostgreSQL (all passing)
- RRF calibration: k=60 shows good 4:4 interleaving between corpora
- Known issue: legislation/municipal_code timeout at 10s (what_applies takes ~40s)

## Recommended Task

Deploy 2 additional relay instances on Modal for Mill Valley and San Anselmo.

### Approach Options

1. **Separate Modal apps** — one `modal_relay.py` per jurisdiction (simplest, some duplication)
2. **Parameterized single app** — one `modal_relay.py` that accepts jurisdiction via env var or Modal secret
3. **Multi-jurisdiction single app** — one app serving all jurisdictions (most complex)

Option 2 is likely best — keeps code DRY while Modal handles isolation.

## Key Files

- `apps/civicos-relay/modal_relay.py` — Existing San Rafael relay deployment
- `packages/civicos-relay/src/civicos_relay/server/app.py` — Relay server application
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py` — Acceptance policy
- `docs/internal/deployment.md` — Modal deployment procedures
- `data/jurisdictions/city-mill-valley.yaml` — Mill Valley jurisdiction config
- `data/jurisdictions/city-san-anselmo.yaml` — San Anselmo jurisdiction config

## Suggested Approach

1. Read `apps/civicos-relay/modal_relay.py` to understand the current deployment pattern
2. Read `docs/internal/deployment.md` for Modal deployment procedures
3. Check Modal secrets: `modal secret list` (need `civicos-secrets` or similar)
4. Create parameterized deployment (jurisdiction via env var or separate Modal apps)
5. Deploy with `modal deploy` and validate with health checks
6. Test that each relay serves its jurisdiction's data correctly

## Tests to Run

```bash
# Smoke tests (should stay green)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Health check after deployment
/health relay
```

## Success Criteria

- [ ] Mill Valley relay deployed on Modal (private, not public-facing)
- [ ] San Anselmo relay deployed on Modal (private, not public-facing)
- [ ] Each relay serves correct jurisdiction data
- [ ] Health checks pass for all 3 relays (San Rafael + 2 new)
- [ ] Deployment documented (how to add more jurisdictions)
