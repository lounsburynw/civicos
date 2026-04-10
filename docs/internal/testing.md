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

### Coverage Inventory (April 2026)

71 source files, 52,538 lines in `packages/civicos/src/civicos/`.

| Category | Files | Lines | % |
|----------|-------|-------|---|
| Mutation-tested | 5 | ~2,200 | 4% |
| Has tests (not mutation-scored) | 32 | ~40,000 | 76% |
| **Zero tests** | **34** | **~10,400** | **20%** |

**Untested files (prioritized for test writing):**

Pure-logic (highest ROI — no external deps needed):
- `types.py` (516) — dataclasses, enums
- `diagnostics.py` (482) — data status calculations
- `config.py` (433) — configuration parsing
- `funding/matcher.py` (428) — federal funding matching
- `funding/reconciler.py` (400) — funding reconciliation
- `legal/vector_relevance.py` (483) — relevance scoring
- `cost.py` (137) — cost estimation
- `issues/classify.py` (48) — issue classification
- `speakers.py` (222) — speaker identification
- `roster.py` (214) — elected officials
- `registry.py` (205) — corpus registry
- `storage/actionability.py` (153) — actionability scoring

Infrastructure (external deps, harder to unit test):
- `legal/embeddings/chunker.py` (813) — chunking strategy
- `storage/blob.py` (706) — R2 blob operations
- `embeddings/provider.py` (433) — embedding provider
- `issues/providers/seeclickfix.py` (393) — SeeClickFix API
- `legal/corpus/california.py` (359) — CA legislation
- `meetings/pdf_parser.py` (349) — PDF parsing
- `meetings/staff_report.py` (319) — staff report extraction
- `legal/corpus/federal.py` (99) — federal bills

Protocols/types (low ROI — mostly abstract interfaces):
- `storage/protocols/*.py` (5 files, ~1,170) — protocol definitions
- `storage/corpus_types.py` (484) — type definitions
- `state/models.py` (175) — state models

MCP/CLI (integration-heavy):
- `legal/mcp.py` (324), `state/mcp.py` (275), `cli.py` (1,885)

## CI

GitHub Actions runs the full suite on push to main and PRs:
- 4 runners x 2 workers = 8-way parallel
- Config: `.github/workflows/tests.yml`

## Rules

- Never run full suite locally — let CI handle it
- Use smoke tests for quick validation
- Each `pilot.json` item has a `test_file` field for targeted testing
- Check CI status before merging
