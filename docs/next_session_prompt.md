# Recommended: Onboarding YAML Generation

**Priority:** P0 (onboarding_yaml_generation)
**Area:** federation_testbed
**Date:** 2026-03-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The scalability roadmap Phase 1 (generalize RefreshRunner) and Phase 2 (wire cron orchestrators) are complete. The refresh pipeline now uses `RefreshRunner.refresh_corpus()` with `CorpusProvider` instances for meetings, issues, and legislation. Config-driven provider dispatch reads source types from jurisdiction YAML. A new `configuration.critic.md` catches hardcoded provider assumptions going forward.

This session (Phase 4) extends the onboard workflow to generate complete jurisdiction YAML files — making onboarding produce all config needed for a functioning jurisdiction, not just extraction JSON.

## What Exists Now

- `data/jurisdictions/*.yaml` — 11 jurisdiction YAML files (manually created)
- `data/extraction/*.json` — Extraction JSON configs (created by onboard workflow)
- `packages/civicos/src/civicos/jurisdiction_config.py` — `JurisdictionConfig`, `DataSources`, `load_jurisdiction_config()`, `validate_jurisdiction_config()`
- `data/jurisdictions/schema.yaml` — YAML schema reference
- `.claude/commands/onboard.md` — Current onboard slash command

## What Needs to Be Done

1. **Extend the onboard workflow** to generate a jurisdiction YAML alongside the extraction JSON. The YAML should include:
   - Identity (jurisdiction_id, level, display_name)
   - Hierarchy (parent_jurisdictions)
   - Data sources (meetings source_type + base_url, issues source, municipal_code source)
   - Refresh policies (default intervals: meetings 1d, issues 1d, municipal_code 90d, legislation 7d)
   - Ingestion tiers (all true by default for new cities)
   - Contact info (placeholder or scraped if available)

2. **Use existing YAML files as templates** — `data/jurisdictions/city-san-rafael.yaml` is the most complete example.

3. **Validate generated YAML** via `validate_jurisdiction_config()` from `jurisdiction_config.py`.

## Key Files

- `data/jurisdictions/city-san-rafael.yaml` — Reference template (most complete)
- `data/jurisdictions/schema.yaml` — YAML schema
- `packages/civicos/src/civicos/jurisdiction_config.py:392` — `load_jurisdiction_config()`
- `packages/civicos/src/civicos/jurisdiction_config.py:663` — `validate_jurisdiction_config()`
- `.claude/commands/onboard.md` — Current onboard workflow

## Suggested Approach

1. Read the onboard command/script to understand current flow
2. Read `city-san-rafael.yaml` as the reference template
3. Read `schema.yaml` for the YAML schema
4. Add YAML generation to the onboard workflow (after extraction JSON creation)
5. Derive fields from user input and extraction config (source_type, base_url, jurisdiction_id)
6. Default refresh policies and ingestion tiers
7. Validate with `validate_jurisdiction_config()`
8. Test by onboarding a test city and verifying the generated YAML loads correctly

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Jurisdiction config tests
pytest packages/civicos/tests/ -k "jurisdiction_config" -q --override-ini="addopts="
```

## Success Criteria

- [ ] Onboard workflow generates a valid `data/jurisdictions/{jid}.yaml` file
- [ ] Generated YAML passes `validate_jurisdiction_config()`
- [ ] Generated YAML includes: identity, hierarchy, data_sources, refresh policies, ingestion tiers
- [ ] Refresh policies default to sensible intervals (meetings: 1d, issues: 1d, municipal_code: 90d)
- [ ] Existing manually-created YAMLs are not affected

## Roadmap Context

- **Phase 1 (DONE):** Generalize RefreshRunner — CorpusProvider protocol + 3 providers
- **Phase 2 (DONE):** Wire cron orchestrators to use RefreshRunner
- **Phase 4 (P0):** Onboarding YAML generation <-- YOU ARE HERE
- **Phase 5 (P2):** Token issuance track (blind signatures, service, verification)
- **Phase 6 (P3):** Turnkey state onboarding
