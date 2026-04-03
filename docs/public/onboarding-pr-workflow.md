# Adding a New City via PR

Step-by-step guide for adding a new jurisdiction to CivicOS through the PR workflow.

## Prerequisites

- Python 3.11+ with `pyyaml` installed
- CivicOS repo cloned and `civicos-env` activated
- Onboarding script available: `scripts/onboard.py`

## Workflow

### 1. Generate Config Files

```bash
source civicos-env/bin/activate
python scripts/onboard.py --city "City Name" --state XX --county "County Name" --skip-ingestion
```

| Flag | Purpose |
|------|---------|
| `--city` | City name as it appears officially (e.g., "Mill Valley") |
| `--state` | Two-letter state code (e.g., CA, TX) |
| `--county` | County name — recommended for accurate election source detection and parent jurisdiction hierarchy |
| `--skip-ingestion` | Generate config files only, no data ingestion |

This auto-discovers:
- Meeting platform (Granicus, Legistar, CivicClerk, ProudCity, etc.)
- Meeting bodies and view IDs
- YouTube channel for transcripts
- Election sources (Civera, CA SOS)
- USAspending federal programs

**Output files:**
- `data/jurisdictions/city-{slug}.yaml` — jurisdiction configuration (source of truth)
- `data/extraction/city-{slug}.json` — extraction metadata

> **Caution:** If configs already exist, the script skips generation but still probes for a YouTube channel and writes it to the YAML. If you have already hand-edited the YAML, check that the script didn't overwrite your changes (especially `data_sources.transcripts`). Use `--force` to regenerate from scratch instead.

#### Other useful flags

| Flag | When to use |
|------|-------------|
| `--dry-run` | Preview what would be fetched without storing anything |
| `--sandbox` | Ingest to local SQLite instead of production Postgres (combine with `--no-validate` for fully local) |
| `--force` | Regenerate configs from scratch (**overwrites manual edits** — use with care) |
| `--url URL` | Provide the platform URL directly if auto-detection fails |

### 2. Review and Edit the YAML

Open `data/jurisdictions/city-{slug}.yaml` and verify:

| Field | Check |
|-------|-------|
| `jurisdiction_id` | Matches filename (e.g., `city-san-rafael`) |
| `level` | Correct level (`city`, `county`, `state`) |
| `display_name` | Human-readable name |
| `parent_jurisdictions` | Correct hierarchy (city → county → state → country) |
| `data_sources.meetings.source_type` | Platform detected correctly |
| `data_sources.meetings.base_url` | URL is valid and accessible |
| `data_sources.meetings.archives` | At least one meeting body with a view ID |
| `data_sources.transcripts` | YouTube channel actually belongs to this city (not a neighbor). Set `source: null` if no YouTube channel exists |
| `contact_info` | Clerk email, address, website if available |

Also check `data/extraction/city-{slug}.json`:
- `state` field is present (two-letter code)
- `archives` has at least one entry (not empty `{}`)
- `metadata.default_view_id` points to a valid view

See `data/jurisdictions/schema.yaml` for the full YAML schema reference.

#### Troubleshooting: Auto-discovery failures

Auto-discovery works for most cities but can fail in specific cases:

**"No meeting bodies discovered"** — The script found the platform domain but couldn't find valid meeting pages.

- **Granicus**: View IDs don't always start at 1. To find the correct view ID:
  1. Visit the city's official website and look for "Agendas & Minutes" or "City Council" links
  2. The link will contain `view_id=N` (e.g., `novato.granicus.com/AgendaViewer.php?view_id=7`)
  3. Alternatively, try `https://{domain}.granicus.com/ViewPublisher.php?view_id=N` for N = 1 through 15
  4. Update `archives` and `default_view_id` in both the YAML and JSON configs
  5. For the column_map, check the table headers on the ViewPublisher page (Meeting=0, Date=1, etc.)
  
  **For headless/automated runs**: Search the web for `site:{domain}.granicus.com ViewPublisher` or `"{city name}" granicus agendas` to find the view_id without manual browsing.

- **Legistar**: The `client_name` may not match the city slug. Check the city's website for Legistar links to find the correct client name.

**"Failed to fetch Granicus view"** — The Granicus subdomain is wrong. Check the city's official website for links to agendas/minutes — the correct Granicus URL will be in those links. Common patterns: `{city}.granicus.com`, `cityof{city}.granicus.com`, `{city}-{state}.granicus.com`.

**Wrong YouTube channel detected** — The auto-search sometimes picks a neighboring city. Verify the channel name matches the city, or set `transcripts.source: null` if the city doesn't post meetings to YouTube.

**SeeClickFix timeout** — SeeClickFix can be slow or blocked. If issues detection fails, you can manually set `issue_source: "seeclickfix"` in the extraction JSON if you know the city uses it, or leave it as `null`.

After manual corrections, re-run validation (Step 4) to confirm the configs are valid.

### 3. Generate Registry Files

```bash
python scripts/generate_registries.py --check    # Preview changes
python scripts/generate_registries.py             # Apply changes
```

This patches three files from the YAML:
1. `config/registry.json` — service routing (domain, Modal app name)
2. `packages/civicos-config/src/civicos_config/jurisdiction.py` — JurisdictionConfig entry
3. `packages/civicos/src/civicos/_internal/jurisdiction.py` — aliases and display names

> **Note:** The script processes **all** YAML files in `data/jurisdictions/`, not just the one you created. You may see entries for other jurisdictions in the output — this is normal.

> **"WARNING: Could not find insertion point in jurisdiction.py"** — This means the script couldn't auto-insert a `JurisdictionConfig` entry into `jurisdiction.py`. This is safe to ignore if your jurisdiction already appears in `config/registry.json` (the primary registry). The `jurisdiction.py` entries provide optional enrichment (wiki files, cost targets) and can be added manually later if needed.

### 4. Validate

```bash
python scripts/validate_registry.py
```

Check the output for errors related to **your jurisdiction**. Errors for your jurisdiction must be resolved before opening a PR. Warnings are informational.

Pre-existing errors for other jurisdictions (e.g., a `display_name` mismatch on `country-united-states`) are not your responsibility — note them but don't let them block your PR.

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

### 6. Validate Data Quality (Sandbox)

Before opening a PR, verify the extraction pipeline can actually pull data for your jurisdiction:

```bash
python scripts/onboard.py --city "City Name" --state XX --county "County Name" --sandbox --no-validate
```

This ingests to local SQLite (no Modal or Postgres required). Check the output for:
- **Meetings found > 0** — extraction is working
- **Chunks > 0** — agenda PDFs are being parsed
- **No critical errors** in the quality report

Data is stored in `data/sandbox_city-{slug}.sqlite`. Clean up with `python scripts/ingest_local.py --cleanup city-{slug}`.

If this fails but tests pass, the issue is likely in the extraction config (wrong view ID, unreachable URL, etc.) — revisit Step 2.

> **Important:** You need both `--sandbox` and `--no-validate`. Without `--no-validate`, the script runs a Modal-based validation gate before the local ingestion, which requires cloud infrastructure. The `--no-validate` flag skips that gate and goes straight to local SQLite ingestion.

> **Important:** Do not use `--force` here. That regenerates configs from scratch and will overwrite any manual corrections you made in Step 2.

### 7. Open PR

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

### 8. CI Validation

The `validate-registry.yml` workflow runs automatically on PRs that touch:
- `data/jurisdictions/*.yaml`
- `config/registry.json`

It runs:
1. `scripts/validate_registry.py` — schema and integrity checks
2. `scripts/generate_registries.py --check` — registry sync verification

The PR cannot merge if validation fails.

### 9. Post-Merge: Data Ingestion

After the PR is merged to main:

1. **Test locally first** (optional):
   ```bash
   python scripts/onboard.py --city "City Name" --state XX --county "County Name" --sandbox
   ```
   This ingests to local SQLite so you can verify data quality before production.

2. **Production ingestion** (requires Modal access):
   ```bash
   python scripts/onboard.py --city "City Name" --state XX --county "County Name" --yes
   ```
   Or run the Modal pipeline directly:
   ```bash
   modal run scripts/modal_ingest.py --jurisdiction city-{slug} \
     --meetings --chunks --agenda --decisions --issues --vectors \
     --meetings-days-past 365
   ```

3. **Deploy**: `/deploy api` to update the production API with the new jurisdiction.

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

## CLI Quick Reference

```
python scripts/onboard.py --help

Key flags:
  --city NAME           City name
  --state XX            Two-letter state code
  --county NAME         County name (recommended)
  --skip-ingestion      Generate configs only (no data ingestion)
  --dry-run             Preview without storing
  --sandbox             Ingest to local SQLite (use with --no-validate for fully local)
  --no-validate         Skip Modal validation gate (required for local-only sandbox)
  --force               Regenerate existing configs
  --url URL             Provide platform URL directly
  --yes                 Auto-confirm cost estimates
  --deploy              Deploy API to Modal after ingestion
  --cleanup ID          Remove all data + configs for a jurisdiction
```
