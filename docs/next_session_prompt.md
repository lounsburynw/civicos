# Recommended: Provenance Footer — Data Source Transparency

**Priority:** P0
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-12
**Previous session:** Dashboard MVP completion (CSS fix, data-forward validation)

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed the **civic dashboard MVP** — fixed the CSS layout overlap (z-index inversion in CityPulsePane.svelte), verified all 7 sections present data without editorializing, and marked `civic_dashboard_mvp` as ready. Also discovered `expandable_decisions` was already fully implemented and marked it ready too.

The **provenance footer** is the natural next step: a small info panel showing where the dashboard data comes from. This builds trust — critical for a civic tool — by showing MCP endpoint, jurisdiction, data freshness, and corpus coverage. Now unblocked by the MVP being done.

## Recommended Task: Provenance Footer

Build a collapsible provenance panel accessible via info icon in the CityPulse header. Shows:
- Jurisdiction name and MCP endpoint URL
- Data freshness (last sync timestamp per corpus type)
- Corpus coverage summary (e.g., "98 meetings, 44 decisions, 16K municipal codes")
- Relay ID / pubkey (if relay is configured)

### Implementation Plan
1. **Backend**: New `/data-provenance` endpoint returning structured provenance data
2. **Frontend**: Small info icon (ℹ) in the CityPulse header that expands a provenance panel

## Key Files

- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte:868-873` — header where info icon goes
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — API client (add `getDataProvenance()`)
- `apps/civicos-mcp/rest_api.py` — REST API (add `/data-provenance` endpoint)
- `apps/civicos-mcp/tools/handlers.py` — MCP tool handlers (add `data_provenance` handler)
- `packages/civicos/src/civicos/diagnostics.py` — `DataStatus` class has corpus counts already
- `docs/critical/CIVIC_DASHBOARD_VISION.md` — UX vision reference

## Suggested Approach

1. Start with the backend: add a `data_provenance` handler that returns jurisdiction, endpoint URL, corpus counts (reuse `DataStatus`), and last-updated timestamps
2. Wire it as a REST endpoint at `/data-provenance`
3. Add `getDataProvenance()` to the frontend API client
4. Add a small info icon button in the CityPulse header (`.pulse-header` at line 868)
5. On click, expand a provenance panel showing the data (use `slide` transition like other expandables)
6. Style to match the existing dashboard aesthetic (compact, data-forward)

## Tests to Run
```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# MCP city pulse tests (covers dashboard endpoints)
pytest packages/civicos/tests/test_mcp_city_pulse.py -q --override-ini="addopts="
```

## Success Criteria
- [ ] `/data-provenance` endpoint returns jurisdiction, corpus counts, freshness timestamps
- [ ] Info icon in CityPulse header expands provenance panel
- [ ] Panel shows corpus coverage (meetings, decisions, transcripts, issues, etc.)
- [ ] Panel shows data freshness (last updated per corpus)
- [ ] `provenance_footer` marked ready in pilot.json

## Also Notable
- **Relay deployment pending** — action attribution + voice/revoke endpoints committed locally but not deployed to Modal
- **SQL migration pending** — `scripts/sql/add_action_events.sql` needs to run on relay DB for outcomes/attributions tables
- **LLM provider config** — operational concern for pilot (not a code blocker), needed for chat + draft features in Open WebUI
- **openwebui commits not pushed** — 5 commits ahead of origin on civicos-main branch

## Dev Environment
- Frontend: `cd ~/projects/civicos-openwebui && npm run dev` (localhost:5173, hot reload)
- Backend: `./scripts/dev.sh api` (localhost:8001)
- Use venv Python directly: `/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3`
