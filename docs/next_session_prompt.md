# Recommended: Federal Pipeline Hardening

**Priority:** P0 (federal_pipeline_hardening)
**Area:** multi_scale_participation
**Date:** 2026-03-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The federal MCP server is now deployed at `civicos-federal` on Modal (23 tools, jurisdiction=country-united-states). All federal data sources work: congressional votes, hearings, executive orders, federal rules/comment periods, legislation. The next step is ensuring this data stays fresh via automated pipeline hardening.

## What Needs to Be Done

### Federal Pipeline Hardening

The federal data was ingested manually during development sessions. For production reliability, the pipelines need:

1. **Cron-based refresh** — GitHub Actions workflows (`.github/workflows/cron-*.yml`) to periodically re-ingest federal data sources:
   - Congressional votes: daily or weekly
   - Congressional hearings: daily (committee schedules change)
   - Executive orders: daily (via Federal Register API)
   - Federal rules/comment periods: daily (regulations.gov)
   - Legislation: weekly (LegiScan updates)

2. **Checkpoint management** — Ensure ingestion checkpoints track what's been fetched to avoid duplicates and enable incremental updates. See `/checkpoint` command.

3. **Error alerting** — Pipeline failures should notify (via existing `civic-notify` secret).

4. **Data freshness monitoring** — The `/data-status` and admin tools should show when federal data was last refreshed.

## Key Files

- `.github/workflows/` — Existing cron workflow examples
- `scripts/modal_ingest.py` — Modal-based ingestion runner
- `packages/civicos-extraction/` — Extraction modules for each data source
- `packages/civicos/src/civicos/storage/` — Storage backends with upsert methods
- Existing cron patterns: `cron-refresh-*.yml` workflows

## Infrastructure Notes

- **Modal Secrets:** `civicos-federal-env` has DATABASE_URL (pooler format: `postgres.{project_ref}@pooler.supabase.com`), OPENAI_API_KEY, CONGRESS_GOV_API_KEY, CIVICOS_JURISDICTION
- **Placeholder secrets:** `civicos-attestation` and `civicos-platform` exist with placeholder values (created for deploy compatibility)
- **Scheduling:** Use GitHub Actions cron, NOT `modal.Cron()` (Modal starter plan limits)

## Success Criteria

- [ ] At least 3 federal data sources have automated refresh workflows
- [ ] Ingestion checkpoints prevent duplicate data
- [ ] Pipeline failures produce notifications
- [ ] `/data-status` shows last-refreshed timestamps for federal corpora
