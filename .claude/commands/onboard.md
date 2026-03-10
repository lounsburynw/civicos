# Onboard a New City

Interactive jurisdiction onboarding wizard. Detects the civic platform automatically, generates extraction + jurisdiction configs, presents ingestion tier costs, and validates.

Supports cities, counties, and other jurisdiction levels.

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

### Step 5: Present Ingestion Tiers + Cost Estimate

Show the user the 4-tier ingestion model and ask which tiers to enable:

```
Ingestion Tiers for {jurisdiction_id}:

Tier 1 — Free (always recommended):
  [x] meetings          Meeting discovery + extraction
  [x] pdf_chunks        Agenda packet PDF text extraction
  [ ] issues            SeeClickFix/311 issue sync
  [ ] municipal_code    Municipal code sync

Tier 2 — Low cost (~$0.10-0.50/meeting, LLM-powered):
  [x] agenda_items      Agenda item extraction + actionability
  [ ] decisions         Decision extraction from transcripts
  [x] legislation       State/federal bill sync

Tier 3 — Higher cost (~$0.02/min audio):
  [ ] transcription     Audio transcription (AssemblyAI)
  [ ] diarization       Speaker diarization (requires transcription)

Tier 4 — GPU (~$0.01/batch):
  [x] vector_indexing   Semantic search embeddings
```

**Defaults by level:**
- **City**: meetings, pdf_chunks, agenda_items, legislation, vector_indexing enabled
- **County**: meetings, pdf_chunks, agenda_items, legislation, vector_indexing enabled
- **State**: legislation, vector_indexing enabled

Transcription/diarization default to **off** for new jurisdictions (enable when ready).

Write the `ingestion:` block to the jurisdiction YAML based on user choices.

**Provide a cost estimate** based on what's known:
- Count meetings from health check (e.g., "1,641 meetings available")
- Estimate agenda extraction cost (meetings × ~$0.25)
- Estimate transcription cost if enabled (meetings with audio × avg duration × $0.02/min)

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

And what to do next:
- `/ingest meetings --jurisdiction {jurisdiction_id}` — start meeting extraction
- `/ingest agendas --jurisdiction {jurisdiction_id}` — extract agenda items
- Enable transcription when ready (update `ingestion.transcription: true`)

## Notes

- Platform detection works for **Granicus** (direct *.granicus.com URLs, 95% confidence; indirect via city site links, 85%), **Legistar** (API probe), **CivicClerk** (OData probe), and **ProudCity** (HTML scrape).
- For Granicus, `discover_view_ids()` probes view_ids 1-50 automatically. Review discovered bodies — some may be historical or redundant.
- Ingestion tiers are stored in `data/jurisdictions/{id}.yaml` under `ingestion:`. The pipeline reads these to decide what to run.
- Reference configs: `city-san-rafael.yaml` (all tiers enabled), `county-marin.yaml` (conservative defaults).
