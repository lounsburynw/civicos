# Recommended: Registry PR Workflow (operator_readiness)

**Priority:** P0 (registry_pr_workflow)
**Area:** operator_readiness
**Date:** 2026-04-02

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The election_source_auto_detection item is complete — Clarity Elections auto-detection now covers 48 counties across 14 US states. The onboarding pipeline (`scripts/onboard.py`) can detect meeting platforms, election sources, and generate jurisdiction configs. What's missing is a documented, CI-validated workflow for the PR that adds a new jurisdiction to `config/registry.json`. Currently there's no schema validation or CI check on registry edits.

Launch phase is 126/137 items done, 6 remaining.

## What to Build

### 1. Registry JSON Schema Validation
Create a validation script or JSON schema that checks `config/registry.json` for:
- Required fields per jurisdiction (domain, display_name, parent_jurisdictions)
- No duplicate jurisdiction IDs
- Parent jurisdictions reference valid IDs
- Domain uniqueness
- Valid structure (no typos in field names)

### 2. CI Workflow for Registry PRs
Create `.github/workflows/validate-registry.yml` that runs on PRs touching `config/registry.json` or `data/jurisdictions/*.yaml`. Should run the schema validator and existing jurisdiction tests.

### 3. Document the PR Workflow
Write a clear guide (or update existing docs) explaining how to add a new city:
1. Run `/onboard --city "Name" --state XX --sandbox --dry-run`
2. Review generated files (extraction config, jurisdiction YAML)
3. Run `scripts/generate_registries.py` to update registry files
4. Open PR — CI validates schema and runs tests
5. Merge — city is live

## Key Files

- `config/registry.json` — Service URLs, deployment config for 15+ jurisdictions
- `scripts/onboard.py` — Turnkey onboarding script (sandbox, dry-run, cleanup modes)
- `scripts/generate_registries.py` — Auto-generates 3 registry files from YAML
- `packages/civicos-config/src/civicos_config/jurisdiction.py` — JurisdictionRegistry class
- `packages/civicos/tests/test_jurisdiction.py` — Existing jurisdiction tests (~100 lines)
- `docs/internal/onboarding-friction-log.md` — Friction analysis from 6 onboardings
- `docs/public/data-ingestion.md` — Full ingestion guide
- `.github/workflows/` — Existing CI workflows (no registry validation yet)

## Suggested Approach

1. Read `config/registry.json` to understand current schema
2. Write a validation script (`scripts/validate_registry.py`) that checks integrity
3. Create `.github/workflows/validate-registry.yml` triggered on PR
4. Add tests for registry validation (e.g., in `tests/test_registry_validation.py`)
5. Document the workflow in `docs/public/onboarding-pr-workflow.md`
6. Update `launch.json` status when complete

## Tests to Run

```bash
pytest packages/civicos/tests/test_jurisdiction.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
python scripts/generate_registries.py --dry-run  # verify generator works
```

## Success Criteria

- [ ] Registry validation script exists and catches common errors
- [ ] CI workflow runs on PRs touching registry/jurisdiction files
- [ ] Clear documentation for adding a new city via PR
- [ ] Existing tests still pass
- [ ] launch.json item marked done
