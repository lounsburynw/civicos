# Recommended: Federal Funding Pipeline (USAspending)

**Priority:** P0 (federal_funding_pipeline)
**Area:** multi_scale_participation
**Date:** 2026-03-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This is session 1 of a 10-session federal data enrichment plan (see `docs/internal/federal-data-plan.md`). The plan transforms federal data from a catalog of DC activity into locally-relevant, actionable civic information that mirrors city-level data structures.

Currently we have 5 federal awards totaling $17.2M for San Rafael. The `USAspendingClient` exists and works. The USAspending API is free (no key needed) and supports geographic filtering. This session should produce hundreds of awards across all configured jurisdictions.

## What Already Exists

- `packages/civicos-extraction/src/civicos_extraction/clients/usaspending.py` — `USAspendingClient` with `get_awards()` and `get_awards_by_cfda()` methods
- `federal_awards` table in PostgreSQL — schema: `award_id`, `jurisdiction_id`, `cfda_number`, `recipient_name`, `amount_cents`, `period_start`, `period_end`, `program_name`, `awarding_agency`, etc.
- `federal_programs` table — 2,346 CFDA programs with descriptions and eligibility
- `scripts/modal_ingest.py` — has pattern for adding to `scheduled_low_velocity_refresh()`
- 5 existing awards for `city-san-rafael` (proof the pipeline works end-to-end)

## Suggested Approach

1. **Review USAspendingClient** — understand current `get_awards()` parameters, pagination, geographic filtering
2. **Bulk ingest** — run for all configured jurisdictions (San Rafael, Mill Valley, San Anselmo, Marin County). USAspending filters by recipient name or location.
3. **Add to weekly refresh** — add `fetch_federal_awards()` function to `modal_ingest.py`, call from `scheduled_low_velocity_refresh()`
4. **Index vector embeddings** — enable semantic search over award descriptions
5. **Verify data quality** — check amounts, date ranges, deduplication

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Hundreds of federal awards ingested (not just 5)
- [ ] All configured jurisdictions have award data
- [ ] Awards added to weekly refresh schedule
- [ ] Vector embeddings indexed for semantic search
- [ ] Can query: "What federal funding does San Rafael receive for housing?"

## Session 2 (follow-up)

After ingest, build the query layer:
- `FundingAdapter` for v2 search
- `civic.upcoming` for grants with approaching expiration dates
- Extension display
- MCP tool: `search_federal_funding`
