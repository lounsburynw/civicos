# Recommended: Action Attribution — Close the Feedback Loop

**Priority:** P0
**Area:** relay > action_primitives > action_attribution
**Date:** 2026-02-11
**Previous session:** 573

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The action system is now complete through Phase 2. Users can: create initiatives, add action items with deadlines/templates, commit ("I'll do this"), track commitments in a persistent "My Commitments" panel, download .ics calendar events, mark done, and withdraw. What's missing is the **feedback loop** — when a decision outcome is recorded, committed users should see "your comment was 1 of 27 that influenced this vote." Without attribution, the action system is just another CRUD feature.

### Prior Commits (done)
- civicos `5022ea6`: Phase 1 — deadline_context, withdraw, review fixes
- civicos `3631a9e`: Phase 2 — coordination_url, backend for My Commitments
- openwebui `339dfd4`: Phase 2 — My Commitments panel, .ics calendar, coordination_url display

### Also Note: Relay Needs Deployment
Phase 1+2 action system changes are committed locally but **not deployed to Modal**. Consider deploying first (quick) so real users can test.

## Recommended Task: Action Attribution

### What to Build

1. **Outcome recording endpoint** (backend)
   - `POST /coordination/initiative/{id}/outcome`
   - Outcome types: `passed`, `failed`, `continued`, `modified`, `partial`
   - Links a decision outcome to an initiative
   - Store: new `coordination_outcomes` table or field on `coordination_initiatives`

2. **Attribution generation** (backend)
   - When outcome is recorded, query all commitments/completions for that initiative's actions
   - Generate personalized attribution per participant pubkey
   - "Your comment was 1 of 27 submitted. The council voted 4-1 to approve."
   - Non-participants see aggregate: "27 comments submitted, initiative passed 4-1"

3. **Attribution display** (frontend)
   - Outcome banner on initiative card in CityPulse
   - Personalized impact message for committed users
   - Aggregate stats for everyone else

### Existing Code to Build On

- `report_outcome()` in `packages/civicos/src/civic/orchestrator/outcomes.py` — SQLite-only, needs relay/Postgres upgrade
- CivicCompletion (Kind 30812) already tracks who completed what action
- `CivicActionProgress` already has commitment_count/completion_count
- Design reference: `docs/critical/COORDINATION_PROTOCOL.md:570-656`

## Key Files

- `packages/civicos-services/src/civicos_services/servers/routers/coordination.py` — add outcome endpoint here
- `packages/civicos-relay/src/civicos_relay/voice/models.py:185-260` — CivicActionEvent, CivicCommitment, CivicCompletion models
- `packages/civicos-relay/src/civicos_relay/voice/civic_action_service.py` — action service layer
- `packages/civicos-relay/src/civicos_relay/storage/postgres.py:423-540` — initiative/action storage
- `packages/civicos/src/civic/orchestrator/outcomes.py` — existing report_outcome (SQLite-only)
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — initiative display, My Commitments panel
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — API client types and functions
- `docs/critical/COORDINATION_PROTOCOL.md:570-656` — Attribution design spec

## Suggested Approach

1. Design the outcome model (add to relay models.py or new model)
2. Add `coordination_outcomes` table or `outcome` fields to `coordination_initiatives`
3. Create `POST /coordination/initiative/{id}/outcome` endpoint with signature verification
4. Create `GET /coordination/initiative/{id}/attribution/{pubkey}` endpoint
5. Add attribution display to CityPulse initiative cards
6. Test with existing initiative data

## Tests to Run
```bash
# Relay tests (action models, storage)
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos-relay/tests/ -q --override-ini="addopts="

# Smoke tests
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria
- [ ] Outcome recording endpoint works (POST with signed outcome)
- [ ] Attribution query returns personalized message per pubkey
- [ ] CityPulse shows outcome banner on initiatives with recorded outcomes
- [ ] Committed users see personal impact message
- [ ] Non-participants see aggregate stats
- [ ] Existing tests still pass (233 relay + 42 smoke)

## Dev Environment
- Frontend: `cd ~/projects/civicos-openwebui && npm run dev` (localhost:5173, hot reload)
- Backend: `./scripts/dev.sh api` (localhost:8001)
- Use venv Python directly: `/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3`
