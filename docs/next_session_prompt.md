# Recommended: Civic Dashboard MVP — Fix CSS Layout + Final Validation

**Priority:** P0
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-12
**Previous session:** Action attribution system (outcome recording + activity-based feedback)

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session built the **action attribution system** — two commits:
1. `9973f0c` Outcome-based attribution (record initiative outcomes, auto-generate attributions)
2. `db727a3` Activity-based attribution (immediate feedback on action completion, no outcome needed)

The attribution system is complete with 30 tests passing. The relay action system now has the full lifecycle: create action -> commit -> complete -> get immediate feedback -> (optionally) record outcome -> get outcome attribution.

**Migration needed:** Run `scripts/sql/add_action_events.sql` on the relay database to create `coordination_outcomes` and `coordination_attributions` tables. This is idempotent.

The **civic dashboard MVP** is the highest remaining priority. Most pieces are done (issue map, voice, comments, chat integration) but CSS layout issues remain and final validation is needed before MCP registry listing.

## Recommended Task: Finish Dashboard MVP

### What's Done (from pilot.json progress)
- Open WebUI integration, civic dashboard display, REST API client, chat integration
- LLM-triggered artifacts, issue geography viz (enhanced with filters, expand modal)
- Voice toggle, comment threads, one-comment-per-person
- Issue map: type/recency/status filters, trend line, expand modal

### What Remains
1. **Fix CSS layout** — dashboard overlaps chat in some states (IN PROGRESS per subtasks)
2. **Configure LLM provider for Open WebUI** — needed for chat + draft features
3. **Test data-forward presentation** — verify no editorializing in dashboard output
4. **Deploy relay action changes to Modal** — voice/revoke + action attribution endpoints

## Key Files

- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — main dashboard component
- `~/projects/civicos-openwebui/src/lib/components/civic/IssueMap.svelte` — issue geography visualization
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — API client for civic endpoints
- `packages/civicos-services/src/civicos_services/servers/routers/coordination.py` — coordination endpoints (new: outcome + attribution)
- `docs/critical/CIVIC_DASHBOARD_VISION.md` — UX vision doc

## Suggested Approach

1. Start dev servers: `./scripts/dev.sh api` + `cd ~/projects/civicos-openwebui && npm run dev`
2. Open `localhost:5173` and inspect the dashboard layout issues
3. Fix CSS overlaps between dashboard and chat panels
4. Test voice/comment flow end-to-end in browser
5. Verify data-forward presentation (patterns shown, no editorializing)
6. Deploy relay to Modal if time permits (action attribution endpoints)

## Tests to Run
```bash
# Smoke tests
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Attribution tests (new)
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos-relay/tests/test_action_attribution.py -q --override-ini="addopts="

# MCP city pulse tests
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos/tests/test_mcp_city_pulse.py -q --override-ini="addopts="
```

## Success Criteria
- [ ] Dashboard CSS layout doesn't overlap chat in any viewport
- [ ] Issue map renders with live San Rafael data
- [ ] Voice + comment flow works end-to-end
- [ ] Data presentation is pattern-forward, not editorial
- [ ] `civic_dashboard_mvp` marked ready in pilot.json

## Also Notable (P1)
- **expandable_decisions** — expand decision rows to show vote breakdown, testimony. Blocked by dashboard MVP.
- **Relay deployment** — action system changes (attribution, coordination_url, deadline_context) committed locally but not deployed to Modal.
- **Run SQL migration** — `scripts/sql/add_action_events.sql` needs to run on relay DB for outcomes/attributions tables.

## Dev Environment
- Frontend: `cd ~/projects/civicos-openwebui && npm run dev` (localhost:5173, hot reload)
- Backend: `./scripts/dev.sh api` (localhost:8001)
- Use venv Python directly: `/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3`
