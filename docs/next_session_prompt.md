# Recommended: Local Impact Relevance Scoring

**Priority:** P0 (local_impact_relevance)
**Area:** multi_scale_participation
**Date:** 2026-03-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Federal data pipelines are now fully hardened — all 8 federal corpora (legislation, executive orders, federal rules, congressional votes/hearings, programs, awards, HUD allocations) have automated weekly refreshes via GitHub Actions cron. Refresh windows were tightened to match weekly cadence. The next step is making this data *actionable* for local users by scoring federal rules by their relevance to San Rafael / Marin County.

## What Needs to Be Done

Add heuristic-based local relevance scoring to federal rules (no LLM cost). Three scoring signals:

1. **Agency-to-topic mapping** — Map federal agency names (EPA, HUD, DOT, etc.) to local topic categories (environment, housing, transportation). San Rafael's active policy areas should score higher.

2. **Geographic text matching** — Scan title/abstract for mentions of CA, California, Marin, San Rafael, Bay Area, etc. Direct geographic mentions are strong relevance signals.

3. **CFR part matching** — Match regulation_id_numbers / docket_ids against locally relevant Code of Federal Regulations parts (e.g., Title 24 = housing, Title 40 = environment).

The output is two new columns on `federal_rules`: `local_relevance_score` (float 0-1) and `relevance_reasons` (JSONB array of matched signals). Backfill existing ~4,115 rules.

## Key Files

- `packages/civicos/src/civicos/storage/postgres_backend.py:6310` — `store_federal_rules()` (add new columns)
- `packages/civicos/src/civicos/storage/postgres_backend.py:6384` — `get_federal_rules()` (return new fields)
- `packages/civicos-services/src/civicos_services/query/verbs.py:600` — federal comment periods in v2 search (add sort-by-relevance)
- `apps/civicos-mcp/tools/handlers.py` — MCP tools for federal rules (expose relevance)
- `packages/civicos/src/civicos/_internal/legal/embeddings/chunker.py:704` — `expand_federal_rules_to_chunks()` (include relevance in vector text)

## Suggested Approach

1. **Define scoring function** — Pure Python function that takes a federal rule dict and a jurisdiction config, returns `(score: float, reasons: list[str])`. Put it in `packages/civicos/src/civicos/_internal/legal/` as a new module (e.g., `relevance.py`).

2. **Add DB columns** — ALTER TABLE federal_rules ADD COLUMN local_relevance_score FLOAT, ADD COLUMN relevance_reasons JSONB. Add migration to `scripts/sql/`.

3. **Integrate into storage** — Update `store_federal_rules()` to compute and store relevance on ingest. Update `get_federal_rules()` to return the new fields.

4. **Backfill existing rules** — One-time script or Modal function to score all ~4,115 existing rules.

5. **Surface in UX** — Sort federal rules by relevance in v2 search results and MCP tool responses. Extension can show relevance badge.

## Infrastructure Notes

- Federal rules table has ~4,115 rows (check with `/data-status`)
- The `expand_federal_rules_to_chunks()` function (created this session in `chunker.py:704`) should include relevance_reasons in vector text for semantic search
- Scheduled refresh (`fetch_federal_rules` in `scripts/modal_ingest.py:1117`) should score new rules on ingest via `auto_index=True` path
- No LLM calls needed — this is pure heuristic matching
- launch.json notes say this is a 2-session item

## Success Criteria

- [ ] Scoring function covers all 3 signals (agency mapping, geographic text, CFR parts)
- [ ] New columns added to federal_rules table with migration
- [ ] Existing ~4,115 rules backfilled with scores
- [ ] v2 search results sort federal rules by local_relevance_score
- [ ] MCP tools expose relevance score and reasons
