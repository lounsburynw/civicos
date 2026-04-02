# Configuration Critic

Review code changes to ensure jurisdiction-specific behavior is driven by configuration, not hardcoded.

## Context

CivicOS supports multiple jurisdictions, each configured in `data/jurisdictions/*.yaml`. These YAML files are the single source of truth for how a jurisdiction behaves — which providers to use, what refresh intervals to apply, which corpora to ingest, and how to connect to data sources.

The jurisdiction critic catches hardcoded *jurisdiction IDs*. This critic catches hardcoded *jurisdiction behavior* — any value that should vary per-jurisdiction but is baked into code instead of read from config.

## Key Files

- `data/jurisdictions/*.yaml` — Per-jurisdiction configuration (source of truth)
- `packages/civicos/src/civicos/jurisdiction_config.py` — `load_jurisdiction_config()`, `DataSources`, `JurisdictionConfig`
- `packages/civicos-extraction/src/civicos_extraction/clients/base.py` — `ExtractionConfig`
- `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py` — `load_refresh_policies()`

## Check

### 1. Provider dispatch from config?

Client instantiation must be driven by jurisdiction config, not assumed.

```python
# FAIL — assumes all jurisdictions use SeeClickFix
client = SeeClickFixClient()
provider = IssueCorpusProvider(client=client, jurisdiction_id=jid)

# PASS — reads source from config, dispatches accordingly
issues_source = jur_config.data_sources.issues
if issues_source == "seeclickfix":
    client = SeeClickFixClient()
elif issues_source == "qalert":
    client = QAlertClient(...)
else:
    raise ValueError(f"Unsupported issues source '{issues_source}' for {jid}")
```

Signs of violation:
- Specific client class imported/instantiated unconditionally
- `source_name` set to a literal string instead of read from config
- No `if/elif` dispatch on source type before creating a client
- Missing graceful skip when a jurisdiction has no source configured for a corpus type

### 2. Refresh intervals from YAML policies?

Scheduling behavior must come from `refresh:` block in YAML, not hardcoded.

```python
# FAIL — hardcoded interval
if days_since_last_fetch < 7:
    return  # skip

# PASS — reads from YAML policy via RefreshRunner
if not runner.should_refresh(jid, corpus_type, policy):
    return  # skip (interval from YAML)
```

Signs of violation:
- Literal day/hour intervals in cron or refresh logic
- `timedelta(days=7)` comparisons that bypass `RefreshPolicy`
- Ignoring `load_refresh_policies()` return value

### 3. Ingestion tier gates from config?

Which corpora to process should come from the `ingestion:` block, not hardcoded assumptions.

```yaml
ingestion:
  meetings: true
  transcription: true
  agenda_items: false    # Disabled for this jurisdiction
```

```python
# FAIL — assumes all jurisdictions want agenda items
extract_agenda_items(jurisdiction=jid)

# PASS — checks config
if jur_config.ingestion.get("agenda_items", True):
    extract_agenda_items(jurisdiction=jid)
```

### 4. URLs and endpoints from config?

Base URLs, archive paths, and API endpoints should come from `data_sources`, not hardcoded.

```python
# FAIL — hardcoded URL
client = ProudCityClient(base_url="https://www.cityofsanrafael.org")

# PASS — from config
client = ProudCityClient(base_url=ext_config.base_url, jurisdiction_id=jid)
```

### 5. Geographic/identity assumptions from config?

State codes, county names, and geographic data should come from jurisdiction YAML.

```python
# FAIL — assumes California
state_code = "CA"

# PASS — derived from jurisdiction config or hierarchy
state_code = jur_config.financial.state
```

Exception: Code that explicitly iterates a known set (e.g., `for state in ["CA", "US"]:` in a cron that syncs all states) is acceptable — the iteration set itself should eventually come from config, but hardcoded iteration over a small known set is low risk.

**Platform instance registries (election sources, meeting platforms):** Must live in JSON data files under `data/extraction/`, NOT as hardcoded Python dicts. Examples: `civera_instances.json`, `clarity_instances.json`. The Python module loads the JSON at import time via a `_load_*_instances()` function (see `civera_election_stats.py` and `clarity_elections.py` for the pattern). New election platform registries MUST follow this pattern — never add a new hardcoded `*_INSTANCES` dict in Python code. The `state` field MUST be passed explicitly in source configs, never defaulted.

### 6. Unsupported values handled?

When config dispatch encounters an unknown value:
- Raise `ValueError` with the value AND the jurisdiction ID
- Missing/empty config skips gracefully with a log message, not a crash
- Never silently fall through to a default provider

## Output

```json
{
  "pass": true|false,
  "issues": [
    {
      "severity": "critical|warning|info",
      "file": "path/to/file.py",
      "line": 123,
      "category": "provider_dispatch|refresh_policy|ingestion_tier|url|geography",
      "message": "SeeClickFixClient instantiated without checking data_sources.issues config"
    }
  ]
}
```

Severity guide:
- **critical**: Hardcoded provider in cron/API code (breaks multi-jurisdiction)
- **warning**: Hardcoded interval that bypasses refresh policy, missing ingestion tier check
- **info**: Hardcoded value in one-off script or test fixture (acceptable but note it)
