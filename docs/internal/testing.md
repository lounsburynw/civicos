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

**Mutation Baselines (April 2026):**

| Module | Score | Killed/Total | Notes |
|--------|-------|-------------|-------|
| `calendar.py` | **96%** | 102/106 | 4 survivors are equivalent/trampoline limits |
| `elections/cycles.py` | **77%** | 304/394 | Needs ~6 kills for 80% target |
| `elections/deadlines.py` | **65%** | 70/107 | Needs work to reach 80% |
| `meetings/reconciliation.py` | pending | — | 29 tests written, baseline pending |
| `meetings/minutes.py` | pending | — | 20 tests written, baseline pending |

**Targets:** Security paths 90%+, query layer 80%+, storage 75%+, everything else 60%+.

## Coverage Inventory (April 2026, updated April 10)

### Repo-Wide Summary

| Package | Test Files | Test Lines | Source Files | Source Lines | Test:Source |
|---------|-----------|------------|-------------|-------------|------------|
| **civicos** | 69 | 46,713 | 89 | 53,934 | 0.87 |
| **civicos-extraction** | 59 | 40,608 | 93 | 52,023 | 0.78 |
| **civicos-services** | 88 | 65,066 | 116 | 46,240 | 1.41 |
| **civicos-relay** | 24 | 9,473 | 43 | 15,424 | 0.61 |
| civicos-config | 0 | 0 | 3 | 2,060 | 0.00 |
| civicos-signer | 0 | 0 | 4 | 1,546 | 0.00 |
| civicos-client (TS) | 0 | 0 | 40 | 8,702 | 0.00 |
| civicos-components (Svelte) | 0 | 0 | 24 | 19,936 | 0.00 |
| civicos-extension (Svelte) | 0 | 0 | 42 | 10,228 | 0.00 |
| civicos-mcp | 5 | 2,855 | 17 | 9,977 | 0.29 |
| civicos-personal-mcp | 9 | 3,771 | 53 | 13,154 | 0.29 |
| **Total** | **254** | **168,486** | **554** | **250,368** | **0.67** |

**Main 4 packages combined:** 240 test files, 161,860 test lines, 0.97 test:source ratio.

### How We Got Here

The test overhaul (April 9-10, 2026) used a headless executor/critic pipeline (`scripts/test_overhaul.sh`) to generate tests for untested modules. Results:

| Phase | Files | Tests | Method |
|-------|-------|-------|--------|
| Manual (session) | 8 | 186 | Hand-written + critic audit |
| Pipeline: civicos | 1 | 76 | Executor + critic |
| Pipeline: extraction | 27 | ~3,000 | Executor + critic |
| Pipeline: services | 49 | ~4,000+ | Executor + critic (2 overnight runs) |
| Pipeline: relay | 1 | ~50 | Executor + critic |
| **Total new** | **86** | **~7,300+** | |

The critic caught and fixed anti-patterns in 55% of executor outputs, validating the two-agent design.

### Remaining Gaps

#### Critical: Untested large files

**Storage backends (P3 triage target, 0 dedicated tests):**
- `civicos/storage/sqlite_backend.py` — 4,076 lines
- `civicos/storage/backend.py` — 2,185 lines
- `civicos/storage/pgvector_backend.py` — 2,099 lines

**Coordination/relay (P1 triage target):**
- `civicos_relay/server/coordination.py` — 3,237 lines
- `civicos_relay/storage/postgres.py` — 2,644 lines
- `civicos_relay/server/acceptance.py` — 640 lines

**Core processing:**
- `civicos_services/processing/civic_digest.py` — 3,901 lines
- `civicos_services/query/verbs.py` — 1,604 lines (P2 triage target)
- `civicos_services/chat/civic_chat_router.py` — 1,546 lines
- `civicos_extraction/onboard.py` — 3,325 lines

#### Frontend: Zero coverage
56K lines of TypeScript/Svelte across civicos-client, civicos-components, civicos-extension. No test infrastructure exists.

#### Config/signer packages: Zero coverage
civicos-config (2K lines), civicos-signer (1.5K lines).

#### Pre-existing tests: Unaudited quality
~160 test files that existed before the overhaul haven't been checked against the mutation critic. The original audit estimated 74% were theater (mock-heavy, trivial assertions).

## Next Phase: Depth

The overhaul achieved **breadth** (most files have tests). The next phase focuses on **depth** (mutation baselines on priority targets) and **quality** (auditing pre-existing tests).

### Phase 1: Mutation baselines on triage priorities

Run mutmut against the modules identified in `mutation-testing-workflow.md`:

| Priority | Modules | Target | Est. Time |
|----------|---------|--------|-----------|
| P1: Security | `relay/voice/crypto.py`, `relay/acceptance/`, `services/middleware.py` | 90%+ | 2-3 hrs |
| P2: Query | `services/query/verbs.py`, `services/query/adapters/` | 80%+ | 2-3 hrs |
| P3: Storage | `civicos/storage/postgres.py`, `civicos/storage/sqlite.py` | 75%+ | 3-4 hrs |
| P4: Elections | Push `cycles.py` 77%→80%, `deadlines.py` 65%→80% | 80%+ | 1-2 hrs |

**Headless-compatible.** Each module can be baselined via:
```bash
claude -p "Run /test mutation on {module}. If score < {target}, improve tests until it meets the target. Report final score."
```

### Phase 2: Audit pre-existing tests

Run the mutation critic against all pre-existing test files. Fix theater tests in-place.

```bash
claude -p "Read .critics/mutation.critic.md. Audit {test_file} against all 7 checks. Fix any anti-patterns in-place. Report VERDICT."
```

**Headless-compatible.** Can batch via:
```bash
for f in packages/civicos/tests/test_*.py; do
  claude -p "..." --allowedTools "Edit,Write,Read,Bash,Glob,Grep"
done
```

### Phase 3: CI enforcement

| Step | Action | Status |
|------|--------|--------|
| Reporting | Mutation score in PR comments | Done |
| Soft gate | Warn below 50% | **TODO** |
| Hard gate | Block below 70% | **TODO** (after P1-P3 baselines pass) |

### Phase 4: Frontend tests

Requires setting up test infrastructure (vitest for Svelte/TS). Lowest priority — backend correctness matters more at launch.

## Headless Test Pipeline

`scripts/test_overhaul.sh` automates test generation with executor/critic pattern.

```bash
# Generate tests for a package (no commit)
./scripts/test_overhaul.sh civicos-services

# Generate + commit per package
AUTOCOMMIT=true ./scripts/test_overhaul.sh

# Prevent laptop sleep for overnight runs
caffeinate ./scripts/test_overhaul.sh
```

See `docs/internal/headless-test-overhaul.md` for full documentation.

## CI

GitHub Actions runs the full suite on push to main and PRs:
- 4 runners x 2 workers = 8-way parallel
- Config: `.github/workflows/tests.yml`

## Rules

- Never run full suite locally — let CI handle it
- Use smoke tests for quick validation
- Each `launch.json` item has a `test_file` field for targeted testing
- Check CI status before merging
- Validate tests with mutation testing after writing: `/test mutation <file>`
- New tests must pass the mutation critic's 7 anti-patterns (`.critics/mutation.critic.md`)
