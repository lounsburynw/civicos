# Recommended: AmLegal Client Hardening

**Priority:** P0 (amlegal_client_hardening)
**Area:** security_fixes
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The American Legal Publishing (AmLegal) municipal code parser was rewritten with deterministic format detection + LLM fallback (1956d3a). It's been tested on 4 cities: Sacramento (8,236 sections), Gridley (2,071), Fairfax (1,649), Pinole (1,978). Six new cities are in JURISDICTION_MAP. **Remaining: store Sacramento to Postgres, verify vector indexing pipeline.**

Previous session completed `token_issuer_env_config` — token issuer is deployed and verified on Modal (`GET /coordination/tokens/info` returns `enabled: true`). Also recreated missing `civic-anthropic` Modal secret.

## What Exists Now

- **Parser** (`american_legal.py`) — works for 4+ cities, deterministic format detection with LLM fallback
- **JURISDICTION_MAP** — includes Sacramento, Gridley, Fairfax, Pinole, plus San Rafael and others
- **RefreshRunner** (`refresh.py`) — orchestrates corpus refresh (scheduling, change detection, store, re-embed)
- **`refresh_municipal_code()`** method already exists in RefreshRunner
- **PostgresBackend** has `upsert_municipal_code()` method
- **Vector indexing** pipeline exists for municipal_code corpus type

## Key Files

| File | Purpose |
|------|---------|
| `packages/civicos/src/civicos/_internal/legal/corpus/american_legal.py` | AmLegal parser + JURISDICTION_MAP |
| `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py` | RefreshRunner, RefreshPolicy, RefreshableCorpus |
| `packages/civicos/src/civicos/storage/postgres_backend.py` | `upsert_municipal_code()` |
| `packages/civicos/tests/test_refresh.py` | Refresh/upsert tests |
| `packages/civicos/tests/test_integration_pgvector.py` | Vector indexing integration tests |
| `packages/civicos-extraction/src/civicos_extraction/cli/municipal_code.py` | CLI for municipal code operations |

## Suggested Approach

1. **Parse Sacramento** — run the AmLegal parser for `city-sacramento` to extract sections
2. **Store to Postgres** — use `upsert_municipal_code()` or `RefreshRunner.refresh_municipal_code()` to store Sacramento's 8,236 sections to Postgres
3. **Verify storage** — check section count with `/data-status city-sacramento` or direct query
4. **Vector indexing** — run vector indexing for Sacramento's municipal code (`/vectors` or `modal run scripts/modal_ingest.py`)
5. **Verify vectors** — check embedding coverage with `/vector-coverage city-sacramento`
6. **Test queries** — verify `what_applies("housing", jurisdiction="city-sacramento")` returns results

## Tests to Run

```bash
# Refresh/upsert tests
pytest packages/civicos/tests/test_refresh.py -q --override-ini="addopts="

# Vector integration tests
pytest packages/civicos/tests/test_integration_pgvector.py -q --override-ini="addopts="

# Smoke test
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Sacramento municipal code sections stored in Postgres (8,000+ rows)
- [ ] Vector embeddings generated for Sacramento municipal_code corpus
- [ ] `what_applies()` returns relevant Sacramento results
- [ ] Existing San Rafael data unaffected (no regressions)
- [ ] All tests pass

## Deferred Items

- **token_purchase_ui** (P3) — Stripe checkout flow for buying tokens (now unblocked — issuer deployed)
- **cross_marin_query_prototype** (P1, in_progress) — Cross-jurisdiction queries within Marin County
- **cross_county_query_prototype** (P1, in_progress) — Cross-county queries (Berkeley vs San Rafael)
