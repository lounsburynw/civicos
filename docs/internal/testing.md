# Testing

## Tiers

| Tier | Where | Time | When |
|------|-------|------|------|
| Smoke | Local | ~75s | Session start (`init.sh`) |
| Targeted | Local | 1-3m | During development |
| Mutation | Local/CI | 1-10m | After writing tests |
| Full | CI (GitHub Actions) | ~10-15m | On push/PR |

## Commands

```bash
# Smoke (core API)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Targeted (example: RAG)
pytest packages/civicos/tests/test_integration_rag_san_rafael.py -q --override-ini="addopts="

# Full (let CI handle this)
pytest packages/civicos/tests/ -q --override-ini="addopts="
```

Or use `/test [smoke|targeted|full|mutation]`.

## Mutation Testing

Mutation testing validates that tests actually catch defects. It mutates source code and checks if tests break.

**Tool:** mutmut 3.x (configured in `packages/civicos/pyproject.toml` under `[tool.mutmut]`)

```bash
# Run via slash command (recommended — handles config swapping)
/test mutation src/civicos/calendar.py

# Run directly (requires manually editing pyproject.toml paths_to_mutate)
cd packages/civicos && mutmut run
mutmut results    # Show surviving mutants
mutmut show <id>  # Show specific mutant diff
```

**Key facts:**
- mutmut 3.x reads config from `[tool.mutmut]` in pyproject.toml — no CLI flags for paths
- `also_copy = ["src/"]` is required so mutmut's temp directory has the full package
- CI runs mutation testing on changed files only (PRs), reporting-only (non-blocking)
- Full workflow design: `docs/internal/mutation-testing-workflow.md`

**Baseline (April 2026):**

| Module | Score | Killed/Total | Notes |
|--------|-------|-------------|-------|
| `calendar.py` | **96%** | 102/106 | 4 survivors are equivalent/trampoline limits |
| `elections/cycles.py` | **77%** | 304/394 | Pushed from 66% via field-level contest assertions |
| `elections/deadlines.py` | **65%** | 70/107 | Similar to cycles — election date logic |
| `meetings/reconciliation.py` | new | — | 29 tests written, baseline pending |
| `meetings/minutes.py` | new | — | 20 tests written, baseline pending |

**Targets:** Security paths 90%+, query layer 80%+, storage 75%+, everything else 60%+.

## CI

GitHub Actions runs the full suite on push to main and PRs:
- 4 runners x 2 workers = 8-way parallel
- Config: `.github/workflows/tests.yml`

## Rules

- Never run full suite locally — let CI handle it
- Use smoke tests for quick validation
- Each `pilot.json` item has a `test_file` field for targeted testing
- Check CI status before merging
