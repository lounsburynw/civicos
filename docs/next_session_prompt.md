# Recommended: Municipal Data Isolation

**Priority:** P0
**Area:** data_architecture > data_federation
**Date:** 2026-03-09

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session completed `feedback_channel` — full relay-backed feedback system with Nostr kind 1804, signed events, rate-limited endpoints, CivicFeedbackForm component, and MCP admin tool. Pilot is now at ~96% (24 items remaining, all P3). `municipal_data_isolation` is set as P0 because clean per-jurisdiction data isolation is a prerequisite for onboarding a second city.

## Recommended Task

Verify that all municipal data (meetings, decisions, issues, transcripts, chunks, budget_items) is cleanly isolatable per jurisdiction. The current schema already has `jurisdiction_id` columns, but we need to confirm:
1. No cross-jurisdiction dependencies exist in queries or joins
2. A city-owned instance could run with only its own data
3. Vector embeddings are jurisdiction-scoped (they are, via `jurisdiction` column)
4. Coordination data (voices, comments, initiatives) is jurisdiction-filtered

This is a verification + report task, not a large code change.

## Key Files

- `packages/civicos/src/civicos/storage/postgres_backend.py` — Main storage backend, all queries filter by jurisdiction
- `packages/civicos/src/civicos/storage/pgvector_backend.py` — Vector storage, check jurisdiction scoping
- `docs/internal/storage-schema.md` — Database table schemas
- `packages/civicos-services/src/civicos_services/servers/routers/coordination.py` — Coordination endpoints, check jurisdiction filtering
- `packages/civicos-relay/src/civicos_relay/storage/postgres.py` — Relay storage classes

## Suggested Approach

1. **Audit SQL queries** in `postgres_backend.py` — verify every query filters by `jurisdiction_id`
2. **Audit vector queries** in `pgvector_backend.py` — verify embeddings are jurisdiction-scoped
3. **Audit coordination tables** — voices, comments, initiatives, feedback all have jurisdiction columns
4. **Check for shared/reference data** — legislation and federal programs are shared across jurisdictions by design (not municipal data)
5. **Write verification report** — document findings, flag any issues, propose fixes if needed
6. **Update pilot.json** — mark `municipal_data_isolation` as ready if verification passes

## Tests to Run

```bash
# Smoke test (verify nothing broken)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Check data counts per jurisdiction
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, DataStatus
c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(status.summary())
"
```

## Success Criteria

- [ ] All municipal data queries filter by jurisdiction_id (verified via code audit)
- [ ] Vector embeddings are jurisdiction-scoped
- [ ] Coordination tables have jurisdiction filtering
- [ ] Shared reference data (legislation, federal programs) correctly identified as non-municipal
- [ ] Verification report written (can be brief, in claude-progress.txt)
- [ ] `municipal_data_isolation` marked ready in pilot.json
