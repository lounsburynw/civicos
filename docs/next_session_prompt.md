# Recommended: Complete or scope down Alameda County data (`complete_alameda_ingest_or_scope`)

**Priority:** P0
**Area:** federation_testbed > complete_alameda_ingest_or_scope
**Date:** 2026-04-09

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

The previous session was a testing infrastructure session (mutation testing). The P0 (`complete_alameda_ingest_or_scope`) was not worked on — it carries forward unchanged.

county-alameda has meetings (265) and decisions (709) with chunks (2,532) indexed, but **zero** transcripts, issues, municipal_code, elected_officials, and elections. Users can search Alameda decisions but can't drill down to transcripts, officials, or community issues.

## Decision: Two Paths

### Path A: Full ingest (higher value, higher cost)
Enable transcription, issues, municipal code for county-alameda. Check video URL availability first.

### Path B: Scope down (faster, lower risk)
Ship with limited UX — decisions + chunks only, "drill-down unavailable" label.

**Start with feasibility check:**
1. Check video URLs: `python3 -c "from dotenv import load_dotenv; load_dotenv(); from civicos import CivicOS; c = CivicOS('county-alameda'); ms = c.storage.get_meetings('county-alameda', limit=10); print([m.get('video_url') for m in ms])"`
2. If no video URLs → Path B is pragmatic

## Key Files
- `data/extraction/county-alameda.json` — Granicus source config
- `data/jurisdictions/county-alameda.yaml` — Ingestion config (transcription: false)
- `launch.json` — P0 item description

## Success Criteria
- [ ] Decision made: Path A or Path B
- [ ] Item marked done in launch.json
- [ ] New P0 promoted

---

## Parallel Track: Mutation Testing Continuation

The previous session built mutation testing infrastructure and identified 34 untested source files. This is P1 work that can run in parallel or be picked up when the P0 is done.

### What was built (7 commits on main)
- `docs/internal/mutation-testing-workflow.md` — full design doc
- `.critics/mutation.critic.md` — LLM critic for test anti-patterns
- CI job in `.github/workflows/tests.yml` — PR-only mutation reporting
- `/test mutation [file]` slash command
- `scripts/run_mutation_baseline.sh` — per-module baseline script
- mutmut 3.x configured in `packages/civicos/pyproject.toml`

### Current scores
| Module | Score | Killed/Total |
|--------|-------|-------------|
| `calendar.py` | **96%** | 102/106 |
| `elections/cycles.py` | **77%** | 304/394 |
| `elections/deadlines.py` | **65%** | 70/107 |
| `meetings/reconciliation.py` | — | 29 tests written |
| `meetings/minutes.py` | — | 20 tests written |

### The gap
- 71 source files, 52,538 lines total
- **34 files (10,400 lines) have zero tests**
- Full inventory in `docs/internal/testing.md` under "Coverage Inventory"

### Next testing steps (prioritized)
1. **Breadth**: Write first tests for untested pure-logic files: `types.py` (516 lines), `diagnostics.py` (482), `config.py` (433), `funding/matcher.py` (428), `cost.py` (137), `issues/classify.py` (48)
2. **Depth**: Push `cycles.py` 77% → 80%+ (need ~6 kills from `_resolve_us_senate`)
3. **Baselines**: Run mutmut on `decision.py`, `reconciliation.py`, `minutes.py`

### mutmut quirks to know
- `also_copy = ["src/"]` required in pyproject.toml config
- `--ignore=tests/test_deployment_rollback.py` needed (broken imports)
- Trampoline doesn't detect default parameter mutations
- Use `patch("module.datetime")` for boundary tests (datetime.now() drift)

## Caveats
- **Cost awareness**: See `memory/feedback_cost_communication.md` before expensive pipelines
- **YouTube proxy expired**: `civic-youtube-proxy` Modal secret has 407 errors (blocks audio download)

## Open PRs
None.
