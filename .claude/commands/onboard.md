# Onboard a New City

Interactive jurisdiction onboarding wizard. Detects the civic platform automatically, generates extraction + jurisdiction configs, presents ingestion tier costs, and validates.

Supports cities, counties, and other jurisdiction levels.

## Turnkey Option

For a fully automated onboard, use the standalone script:

```bash
python scripts/onboard.py --city "<CITY_NAME>" --state <ST> --county "<COUNTY>"
```

This generates both configs and runs the full Modal ingestion pipeline. Use `--skip-ingestion` to generate configs only, or `--dry-run` to preview without storing.

## Interactive Steps (if turnkey doesn't fit)

## Steps

### Step 1: Gather Information

Ask the user for:
- **Jurisdiction name** (required) — e.g., "Berkeley", "Marin County"
- **Website or platform URL** (required) — e.g., "https://berkeleyca.gov" or "https://marin.granicus.com"
- **Jurisdiction level** (default: city) — city, county, state
- **State** (default: CA)
- **County** (required for cities) — e.g., "Alameda"

Infer the jurisdiction_id: `{level}-{slug}` (e.g., `city-berkeley`, `county-marin`).

### Step 2: Auto-Detect Platform + Generate Extraction Config

Run platform detection and discovery via the onboard module:

```python
source civicos-env/bin/activate && python3 -c "
from civicos_extraction.onboard import onboard_jurisdiction
result = onboard_jurisdiction('<URL>', '<JURISDICTION_ID>')
print(f'Success: {result.success}')
print(f'Platform: {result.detection.get(\"source_type\") if result.detection else \"unknown\"}')
print(f'Confidence: {result.detection.get(\"confidence\", 0):.0%}' if result.detection else '')
print(f'Config path: {result.config_path}')
print(f'Discovered bodies: {result.discovered_bodies}')
print(f'Next steps: {result.next_steps}')
if result.errors:
    print(f'Errors: {result.errors}')
"
```

Show the user: detected platform, confidence, discovered bodies, and the generated extraction config JSON.

If detection fails, ask the user for the platform type and Granicus subdomain / Legistar client name / etc.

### Step 3: Review Extraction Config

Read and display the generated `data/extraction/{jurisdiction_id}.json`. Ask the user to confirm or edit:
- `archives` — are the right bodies included?
- `metadata` — any platform-specific fields to add?

### Step 4: Create Jurisdiction YAML

Generate `data/jurisdictions/{jurisdiction_id}.yaml` using the template from `data/jurisdictions/schema.yaml`.

Auto-populate from detection results:
- `jurisdiction_id`, `level`, `display_name`
- `parent_jurisdictions` (infer from state/county)
- `data_sources.meetings` (from extraction config)
- `financial.state`, `financial.county`

Leave TODOs for fields that require manual lookup:
- `contact_info` (clerk email, address, phone)
- `governing_body` (meeting schedule, location)
- `zip_codes`, `neighborhoods`

### Step 4.5: Confirm Federal Funding Recipients (USAspending)

The onboarding function automatically searches USAspending.gov for federal award recipients matching the jurisdiction name. If candidates were found (`result.usaspending_candidates`), present them to the user:

```
Federal Funding Recipients (USAspending.gov):

The following recipients were found matching "{jurisdiction_name}".
Government entities are marked with [GOV]. Select which ones belong to this jurisdiction:

  [1] [GOV] CITY OF SAN RAFAEL — 2 awards, $904,988
  [2] [GOV] SAN RAFAEL, CITY OF — 1 award, $16,088,886
  [3]       SAN RAFAEL COOP — 5 awards, $717,900
  [4]       SAN RAFAEL ELEMENTARY SCHOOL — 1 award, $50,000

Which recipients belong to this jurisdiction? (e.g., "1,2" or "all gov" or "none")
```

Based on the user's selection, write the `federal_programs.usaspending` block in the jurisdiction YAML:

```yaml
federal_programs:
  usaspending:
    search_names:
      - "CITY OF SAN RAFAEL"
      - "SAN RAFAEL, CITY OF"
    allowed_names:
      - "CITY OF SAN RAFAEL"
      - "SAN RAFAEL, CITY OF"
```

- `search_names`: the selected recipient names (used as API search terms)
- `allowed_names`: same list (used to filter false positives from broad searches)

If no candidates were found or user selects "none", omit the `usaspending` section.

### Step 5: Present Ingestion Tiers + Cost Estimate

Show the user the 4-tier ingestion model and ask which tiers to enable:

```
Ingestion Tiers for {jurisdiction_id}:

Tier 1 — Free (always recommended):
  [x] meetings          Meeting discovery + extraction
  [x] pdf_chunks        Agenda packet PDF text extraction
  [ ] issues            SeeClickFix/311 issue sync
  [ ] municipal_code    Municipal code sync

Tier 2 — Low cost (Gemini Flash LLM, ~$0.02-0.15/meeting):
  [x] agenda_items      Agenda item extraction + actionability
  [ ] decisions         Decision extraction from minutes
  [x] legislation       State/federal bill sync (LegiScan free tier)

Tier 3 — Transcription (AssemblyAI, ~$0.23/hr with diarization):
  [ ] transcription     Audio transcription ($0.21/hr)
  [ ] diarization       Speaker diarization (+$0.02/hr, requires transcription)

Tier 4 — Vectors (Modal T4 GPU, ~$0.05-0.15/run):
  [x] vector_indexing   Semantic search embeddings (fastembed)
```

**Defaults by level:**
- **City**: meetings, pdf_chunks, agenda_items, legislation, vector_indexing enabled
- **County**: meetings, pdf_chunks, agenda_items, legislation, vector_indexing enabled
- **State**: legislation, vector_indexing enabled

Transcription/diarization default to **off** for new jurisdictions (enable when ready).

Write the `ingestion:` block to the jurisdiction YAML based on user choices.

**Generate a cost estimate** using the cost estimator (reads verified prices from `cost_registry.yaml`):

```python
source civicos-env/bin/activate && python3 -c "
from civicos_extraction.onboard import estimate_costs

# Adjust meeting_count from health check, avg_meeting_hours from typical duration
est = estimate_costs(
    meeting_count=<MEETINGS_PER_MONTH>,
    avg_meeting_hours=2.0,
    tiers={
        'transcription': <True/False>,
        'diarization': <True/False>,
        # ... any non-default tier settings
    },
    include_backfill=<ARCHIVE_COUNT or 0>,
)
print(est.format())
"
```

Show the formatted estimate to the user. Key context:
- AssemblyAI has a **185-hour free tier** (~92 meetings before charges)
- Agenda/decision extraction uses **Gemini Flash** ($0.075/1M tokens), not OpenAI
- Vector indexing uses **fastembed on T4 GPU**, not OpenAI embeddings

### Step 6: Validate

Run health check and validate config:

```python
source civicos-env/bin/activate && python3 -c "
from civicos_extraction.clients.granicus import GranicusSource  # or ProudCitySource, etc.
source = GranicusSource.from_jurisdiction('<JURISDICTION_ID>')
print('=== Health ===')
h = source.health()
print(f'Available: {h.is_available}, Count: {h.available_count}')
print('=== Validate ===')
v = source.validate()
print(f'Valid: {v.is_valid}, Errors: {v.errors}, Warnings: {v.warnings}')
"
```

### Step 7: Guide Through Remaining TODOs

Help the user fill in remaining fields in the jurisdiction YAML:
1. **Contact info** — clerk email, city hall address, phone, public comment rules
2. **Governing body** — name, member title, meeting schedule, location
3. **HUD grantee** — look up at hudexchange.info
4. **Zip codes** — jurisdiction zip codes
5. **Neighborhoods** — major areas (cities only)
6. **Budget source** — opengov or municipal_portal
7. **Transcripts source** — youtube playlist ID or granicus audio

### Step 8: Summary + Next Steps

Show the user what was created:
- `data/extraction/{jurisdiction_id}.json` — extraction config
- `data/jurisdictions/{jurisdiction_id}.yaml` — jurisdiction config

**Turnkey option** — if the user wants everything in one shot:
```bash
civic-extract onboard --city "{city}" --state {ST} --full
```
`--full` enables: YAML generation, extraction pipeline, vector indexing, legislation loading, and municipal code loading.

**Individual flags** (if the user wants control):
- `--run-pipeline` — extract meetings to PostgreSQL
- `--index-vectors` — create vector embeddings (enables semantic search)
- `--load-legislation` — load state legislation from LegiScan (requires `LEGISCAN_API_KEY`)
- `--load-municipal-code` — load municipal code from Municode API
- `--generate-yaml` — generate jurisdiction YAML file

**Manual steps after onboarding:**
- Enable transcription when ready (update `ingestion.transcription: true`)
- Deploy to Modal for scheduled refresh: `modal deploy scripts/modal_ingest.py`
- Update extension registry: `cd apps/civicos-registry && npx wrangler deploy`

## Data Quality Reference (city-san-rafael)

Use San Rafael as the baseline for what good ingestion looks like. After onboarding, compare the new jurisdiction's ratios against these. Large deviations signal platform-specific issues worth investigating before scaling up.

| Metric | San Rafael | What it means |
|--------|-----------|---------------|
| meetings/month | ~16 | Healthy city council + commissions |
| chunks/meeting | ~52 | Agenda PDFs are downloadable and parseable |
| agenda_items/meeting | ~3 | LLM extraction is finding actionable items |
| decisions/meeting | ~0.45 | Minutes contain votable decisions (not all meetings have them) |
| vectors/meeting | ~171 | All corpora are indexing (meetings + chunks + decisions + transcripts) |
| transcripts/meeting | ~0.19 | ~1 in 5 meetings have audio available |

**Red flags after a 30-day sample:**
- `chunks/meeting = 0` → Platform uses HTML agendas, not PDFs (e.g., Mill Valley Granicus). Chunk search won't work.
- `decisions/meeting = 0` → Minutes are too thin or not yet posted. Decision search won't work.
- `agenda_items/meeting = 0` → LLM extraction failing. Check if agendas are behind auth or in an unsupported format.
- `meetings = 0` → Extraction config is wrong (bad view ID, wrong platform, etc.). Don't proceed.

**Expected ranges by platform:**

| Platform | chunks/meeting | decisions/meeting | Notes |
|----------|---------------|-------------------|-------|
| ProudCity | 40-80 | 0.3-0.6 | Direct PDF links, rich minutes |
| Granicus (PDF) | 30-60 | 0.3-0.5 | S3-hosted PDFs |
| Granicus (HTML) | **0** | 0.0-0.1 | No PDFs, thin HTML minutes |
| Legistar | 20-50 | 0.3-0.5 | API-accessible attachments |
| CivicClerk | 10-40 | 0.2-0.4 | OData API |

## Notes

- Platform detection works for **Granicus** (direct *.granicus.com URLs, 95% confidence; indirect via city site links, 85%), **Legistar** (API probe), **CivicClerk** (OData probe), and **ProudCity** (HTML scrape).
- For Granicus, `discover_view_ids()` probes view_ids 1-50 automatically. Review discovered bodies — some may be historical or redundant.
- Ingestion tiers are stored in `data/jurisdictions/{id}.yaml` under `ingestion:`. The pipeline reads these to decide what to run.
- Reference configs: `city-san-rafael.yaml` (all tiers enabled), `county-marin.yaml` (conservative defaults).
