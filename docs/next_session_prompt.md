# Recommended: Turnkey Onboarding — New Marin Jurisdiction(s)

**Priority:** P0 (turnkey_onboarding_marin)
**Area:** operator_readiness
**Date:** 2026-04-02

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The onboarding pipeline (`scripts/onboard.py`) exists and has been used to generate configs for Mill Valley, San Anselmo, Berkeley, Sacramento, and Austin — but **San Rafael is the only city that has been fully onboarded end-to-end** (config generation through data ingestion, vector indexing, and production deployment). The other cities have partial YAML configs from dry-run or sandbox testing but were never pushed through the full pipeline.

This session completed `registry_pr_workflow` — there's now a validation script (`scripts/validate_registry.py`), a CI workflow (`.github/workflows/validate-registry.yml`), and a documented PR process (`docs/public/onboarding-pr-workflow.md`). The pipeline tooling is ready; it needs a real end-to-end exercise.

Launch phase is 127/137 items done, 9 remaining.

## Goal

Pick 1-2 new Marin County jurisdictions and run the complete onboarding pipeline end-to-end. Assess reliability, data quality, and remaining friction. Document findings.

**Marin cities not yet fully onboarded:**
- Belvedere, Corte Madera, Fairfax, Larkspur, Novato, Ross, Sausalito, Tiburon

**Good candidates:** Novato (largest un-onboarded Marin city, has school district already in registry), Sausalito, Larkspur, Fairfax, Corte Madera — all likely Granicus-based.

## Key Files

- `scripts/onboard.py` — Turnkey onboarding (platform detection, config generation, ingestion)
- `scripts/generate_registries.py` — Patches 3 registry files from YAML
- `scripts/validate_registry.py` — Validates YAML + registry.json integrity
- `data/jurisdictions/schema.yaml` — YAML schema documentation
- `data/jurisdictions/validation_rules.json` — Validation constants (levels, source types)
- `docs/public/onboarding-pr-workflow.md` — PR workflow guide
- `docs/internal/onboarding-friction-log.md` — Friction analysis from prior onboardings (most issues now fixed)
- `config/registry.json` — 15 jurisdictions currently registered

## Suggested Approach

1. Pick a Marin city (Novato or Sausalito are good choices — meaningful size, likely Granicus)
2. Run dry-run first to verify detection:
   ```bash
   python scripts/onboard.py --city "Novato" --state CA --county Marin --dry-run
   ```
3. Review generated YAML config — verify platform, meeting types, data sources
4. Run sandbox ingestion to assess data quality:
   ```bash
   python scripts/onboard.py --city "Novato" --state CA --county Marin --sandbox --captions-only
   ```
5. Validate with the new tooling:
   ```bash
   python scripts/validate_registry.py
   python scripts/generate_registries.py --check
   ```
6. If data looks good, run full production ingestion (remove `--sandbox`)
7. Document friction points — update `docs/internal/onboarding-friction-log.md`
8. If time permits, repeat for a second city

## Tests to Run

```bash
pytest packages/civicos/tests/test_jurisdiction.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_registry_validation.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] At least one new Marin jurisdiction fully onboarded (config + data + vectors)
- [ ] Onboarding pipeline ran without manual code fixes
- [ ] `validate_registry.py` passes for the new jurisdiction
- [ ] Data quality assessed (meeting counts, agenda extraction, transcript availability)
- [ ] Friction findings documented
- [ ] launch.json item marked done
