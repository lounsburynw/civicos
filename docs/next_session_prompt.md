# Recommended: cfr_data_execution

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-06

> This is recommended context from Session 485. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 485 built CFR ingestion infrastructure (parser + Modal script) but didn't execute it. Database currently has 0 CFR sections. Priority reordered: **data execution before new feature development**.

New priority order:
1. **P0:** cfr_data_execution (run Modal job to populate CFR)
2. **P1:** codified_law_vectors (embed all legal corpora for semantic search)
3. **P1:** vector_indexing_automation (auto-embed after ingestion)
4. **P2:** case_law_ingestion (deferred until data pipeline complete)

## Recommended Task

Execute CFR Modal ingestion to populate the database with federal regulations.

## Key Files

- `scripts/modal_cfr.py` - Ready-to-run Modal script
- `packages/civic-extraction/src/civic_extraction/cfr.py` - CFR parser
- `packages/civic/src/civic/context.py:185-215` - CFR search (already integrated)

## Steps

1. **Run pilot subset first:**
```bash
modal run scripts/modal_cfr.py --titles 24,40,49
```
This ingests HUD (Title 24), EPA (Title 40), DOT (Title 49) - most relevant for local govt.

2. **Verify ingestion:**
```bash
modal run scripts/modal_cfr.py --stats-only
```

3. **Run full ingestion (optional):**
```bash
modal run scripts/modal_cfr.py --all-titles
```
All 50 titles, ~180k sections, ~30 min.

4. **Test what_applies():**
```bash
pytest packages/civic/tests/test_civic.py -v -k "what_applies"
```

## Success Criteria

- [ ] CFR sections populated in database (verify with --stats-only)
- [ ] what_applies("housing") returns CFR sections with type='cfr'
- [ ] pilot.json updated: cfr_data_execution -> ready

## Next P1 Items

After cfr_data_execution:
- `codified_law_vectors` - Embed U.S. Code + CA Codes + CFR + EOs to pgvector (~$25)
- `vector_indexing_automation` - Auto-trigger embeddings after data ingestion
