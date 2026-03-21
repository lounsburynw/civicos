# Recommended: State Server Deployment

**Priority:** P0 (state_server_deployment)
**Area:** multi_scale_participation
**Date:** 2026-03-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session completed `state_legislative_client` — built a California Legislature bulk data client using official downloads from `downloads.leginfo.legislature.ca.gov`. The DB now has **4,823 CA legislation rows** and **78,625 legislative events** (hearings, votes, history). The multi-scale query stack has level-aware tier weights (state=0.7) and the data is there. What's missing: a deployed state-california server endpoint that surfaces this data.

## What Needs to Be Done

Deploy the state-california Modal MCP server and ensure it serves CA legislation, hearings, votes, and bill history through the standard MCP/REST interface.

The deployment infrastructure already exists — `modal_mcp.py` is parameterized and supports `CIVICOS_JURISDICTION=state-california`. The endpoint `california.civicosproject.org/mcp` is already registered. The main work is:

1. Create the `civicos-california-env` Modal secret (if not already)
2. Deploy the server: `CIVICOS_JURISDICTION=state-california modal deploy apps/civicos-mcp/modal_mcp.py`
3. Verify the state-level tools work with the new legislation + events data
4. Ensure cross-jurisdiction queries from city-san-rafael surface state results
5. Wire the extension CA tab to use the state server
6. Register ingestion cron for weekly CA legislation refresh

## Key Files

- `apps/civicos-mcp/modal_mcp.py:16` — Parameterized Modal deployment, already handles state-california
- `apps/civicos-mcp/jurisdictions/california.yaml` — State config (data_sources: legislation=leginfo_api, revenue=state_controller)
- `packages/civicos-extraction/src/civicos_extraction/clients/california_legislature.py` — Bulk data client (just built)
- `scripts/modal_ca_legislation.py` — Modal function for scheduled CA legislation ingestion
- `packages/civicos/src/civicos/storage/postgres_backend.py:4946` — `store_legislation()` with temporal versioning
- `packages/civicos/src/civicos/storage/postgres_backend.py:6625` — `store_legislative_events()` — hearings, votes
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py` — Tier weights (state=0.7)
- `config/registry.json` — `state-california` jurisdiction entry
- `.github/workflows/cron-*.yml` — Existing cron patterns for scheduled ingestion

## Data Already in DB

| Table | Count | Description |
|-------|-------|-------------|
| legislation (CA) | 4,823 | AB/SB bills, 2025-2026 session |
| legislative_events (CA) | 78,625 | Hearings, votes, history actions |

Key data fields: bill subjects, authors, fiscal flags, vote tallies (ayes/noes/abstain), committee names, hearing dates.

## Suggested Approach

1. **Check Modal secret** — `modal secret list | grep california`. If missing, create `civicos-california-env` with DATABASE_URL pointing to the shared Supabase.
2. **Deploy** — `CIVICOS_JURISDICTION=state-california modal deploy apps/civicos-mcp/modal_mcp.py`
3. **Verify endpoint** — `curl https://california.civicosproject.org/health` (or use `/health`)
4. **Test state tools** — Verify the MCP server exposes legislation search, upcoming hearings, and vote lookup for CA bills
5. **Test cross-jurisdiction** — From city-san-rafael, search with `include_parents=True` and confirm state results appear with 0.7 weight
6. **Extension CA tab** — Check if the extension already has a CA/state tab or needs wiring. Extension code in `apps/civicos-extension/`.
7. **Register ingestion cron** — Add `modal_ca_legislation.py` to GitHub Actions cron (weekly delta refresh). See `.github/workflows/cron-*.yml` for pattern. Use daily delta files (~4MB) not full session archive (~700MB).

## Tests to Run

```bash
# v2 query tests (cross-jurisdiction, tier weighting)
pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts=" -k "jurisdiction or tier"

# Health check after deploy
/health
```

## Success Criteria

- [ ] `civicos-california-env` Modal secret exists with correct DATABASE_URL
- [ ] State-california MCP server deployed and healthy at california.civicosproject.org
- [ ] CA legislation and hearings accessible through MCP tools
- [ ] Cross-jurisdiction queries from city-san-rafael surface state bills at 0.7 weight
- [ ] GitHub Actions cron registered for weekly CA legislation refresh

## Notes

- Do NOT use Open States API — it was acquired by Plural (VC). Use the official bulk downloads or LegiScan.
- Special session bills use `-x1` suffix (e.g., `ca-ab2-x1`) to avoid ID collisions.
- Some hearing events have `committee=None` (2,063 of 9,202) where location code wasn't in lookup. Acceptable for now.
- The `CaliforniaLegislatureClient` supports both direct download and R2 blob storage for Modal.
- Modal scheduling: use GitHub Actions, NOT `modal.Cron()` (starter plan limit).
