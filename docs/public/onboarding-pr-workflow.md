# Adding a New City via PR

Step-by-step guide for adding a new jurisdiction to CivicOS through the PR workflow.

## Prerequisites

- Python 3.11+ with `pyyaml` installed
- CivicOS repo cloned and `civicos-env` activated
- Onboarding script available: `scripts/onboard.py`

## Workflow

### 1. Run Onboarding (auto-generates config)

```bash
source civicos-env/bin/activate
python scripts/onboard.py --city "City Name" --state XX --sandbox --dry-run
```

This auto-discovers:
- Meeting platform (Granicus, Legistar, CivicClerk, ProudCity, etc.)
- YouTube channel for transcripts
- Election sources (Civera, CA SOS)
- USAspending federal programs

Review the generated files:
- `data/jurisdictions/city-{slug}.yaml` — jurisdiction configuration
- `data/extraction/city-{slug}.json` — extraction metadata

### 2. Review and Edit the YAML

Open `data/jurisdictions/city-{slug}.yaml` and verify:

| Field | Check |
|-------|-------|
| `jurisdiction_id` | Matches filename (e.g., `city-san-rafael`) |
| `level` | Correct level (`city`, `county`, `state`) |
| `display_name` | Human-readable name |
| `parent_jurisdictions` | Correct hierarchy (city -> county -> state -> country) |
| `data_sources.meetings` | Platform detected correctly, base_url valid |
| `contact_info` | Clerk email, address if available |

### 3. Generate Registry Files

```bash
python scripts/generate_registries.py --check    # Preview changes
python scripts/generate_registries.py             # Apply changes
```

This patches three files:
1. `config/registry.json` — service routing (domain, Modal app name)
2. `packages/civicos-config/src/civicos_config/jurisdiction.py` — JurisdictionConfig entry
3. `packages/civicos/src/civicos/_internal/jurisdiction.py` — aliases and display names

### 4. Validate

```bash
python scripts/validate_registry.py
```

All errors must be resolved before opening a PR. Warnings are informational.

Common checks:
- YAML required fields present
- Jurisdiction ID format valid
- No duplicate domains or IDs
- Parent jurisdictions reference valid entries
- Display name consistent between YAML and registry.json

### 5. Run Tests

```bash
# Jurisdiction tests
pytest packages/civicos/tests/test_jurisdiction.py -q --override-ini="addopts="

# Registry validation tests
pytest packages/civicos/tests/test_registry_validation.py -q --override-ini="addopts="

# Smoke tests (core API)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

### 6. Open PR

```bash
git checkout -b onboard/city-{slug}
git add data/jurisdictions/city-{slug}.yaml data/extraction/city-{slug}.json
git add config/registry.json
git add packages/civicos-config/src/civicos_config/jurisdiction.py
git add packages/civicos/src/civicos/_internal/jurisdiction.py
git commit -m "feat: Onboard city-{slug}"
git push -u origin onboard/city-{slug}
gh pr create --title "Onboard: City Name" --body "Adds City Name jurisdiction via onboarding pipeline."
```

### 7. CI Validation

The `validate-registry.yml` workflow runs automatically on PRs that touch:
- `data/jurisdictions/*.yaml`
- `config/registry.json`

It runs:
1. `scripts/validate_registry.py` — schema and integrity checks
2. `scripts/generate_registries.py --check` — registry sync verification

The PR cannot merge if validation fails.

### 8. Post-Merge

After the PR is merged to main:
1. The jurisdiction is automatically available to the CivicOS API
2. Run ingestion: `/ingest city-{slug}` to populate data
3. Deploy: `/deploy api` to update the production API

## File Reference

| File | Purpose |
|------|---------|
| `data/jurisdictions/{id}.yaml` | Jurisdiction configuration (source of truth) |
| `data/jurisdictions/schema.yaml` | YAML schema documentation |
| `data/extraction/{id}.json` | Extraction metadata (auto-discovered) |
| `config/registry.json` | Service routing (generated from YAML) |
| `scripts/onboard.py` | Auto-discovery and config generation |
| `scripts/generate_registries.py` | Patches registry files from YAML |
| `scripts/validate_registry.py` | Validates YAML and registry integrity |
