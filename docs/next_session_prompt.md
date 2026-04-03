# Production Onboard: Sausalito + Fairfax (with School Districts)

**Priority:** P0 — first official city expansion beyond San Rafael
**Area:** operator_readiness
**Date:** 2026-04-03

> This is the definitive checklist from the hardening session. All sandbox QC passed (8/8 Marin cities). Cron pipeline fixed and deployed. Execute this checklist.

## Phase 0: Confirm Infrastructure (5 min)

The previous session fixed all cron jobs (commit c43ee70) and triggered a manual run. Confirm it passed:

```bash
gh run list --workflow=cron-meetings-poll.yml --limit 3
# The 2026-04-03T23:09 run should show "success"
# If it failed, check logs: gh run view <id> --log-failed | tail -30
```

Also confirm San Rafael data caught up (was stale since 04-01):
```bash
/data-status city-san-rafael
# meetings should have dates within last 3 days
```

If crons are still failing, debug that FIRST — don't onboard with broken refresh.

## Phase 1: Onboard Sausalito Bundle

### 1a. city-sausalito (Granicus, 55 meetings, 89% agenda)

Extraction config already exists and passes QC. This is a production onboard (Modal + Postgres), NOT sandbox:

```bash
# Dry run first — review configs, see cost estimate
python scripts/onboard.py --city Sausalito --state CA --county Marin --dry-run

# Review YAML — verify display_name, website (should be townofSausalito.gov, NOT granicus URL),
# contact_info, federal_programs.usaspending.search_names
# Edit data/jurisdictions/city-sausalito.yaml if needed

# Production onboard (Modal + Postgres + vectors)
python scripts/onboard.py --city Sausalito --state CA --county Marin --deploy
```

Expected: ~55 meetings ingested, vectors indexed, API live. Cost: ~$1.50.

### 1b. school-sausalito-marin-city (BoardDocs)

```bash
# School district — extraction config exists, needs YAML + ingestion
python scripts/onboard.py --level school --city Sausalito --state CA --county Marin --deploy
# If --level school doesn't auto-find it, use the existing config directly:
# Generate YAML, then: modal run scripts/modal_ingest.py::fetch_meetings --jurisdiction school-sausalito-marin-city
```

BoardDocs runs on civic_image (no browser needed). Lighter than Simbli.

## Phase 2: Onboard Fairfax Bundle

### 2a. city-fairfax (ProudCity, 99 meetings, 100% agenda)

```bash
python scripts/onboard.py --city Fairfax --state CA --county Marin --dry-run
# Review YAML
python scripts/onboard.py --city Fairfax --state CA --county Marin --deploy
```

Expected: ~99 meetings. Cost: ~$2.00.

### 2b. school-ross-valley (BoardDocs — serves Fairfax, Ross, San Anselmo)

```bash
python scripts/onboard.py --level school --city Fairfax --state CA --county Marin --deploy
```

## Phase 3: Single Deploy + Verify (5 min)

One deploy covers all new jurisdictions:

```bash
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

Then verify each:
```bash
# Quick API query test for each
for jid in city-sausalito city-fairfax school-sausalito-marin-city school-ross-valley; do
  echo "=== $jid ==="
  curl -s "https://civicos-api--civicosproject.modal.run/api/v2/civic/search" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"meeting\",\"jurisdiction\":\"$jid\",\"limit\":1}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  Results: {len(d.get(\"results\",[]))}')"
done
```

## Phase 4: Cron Readiness (2 min)

The onboard script now checks this automatically (Phase 3.7). But verify manually:

```bash
python3 -c "
import json, yaml
from pathlib import Path
P = Path('.')
modal_ok = {'proudcity','granicus','legistar','civicclerk','escribe','boarddocs','civicplus','universal','simbli','playwright_llm'}
for jid in ['city-sausalito', 'city-fairfax', 'school-sausalito-marin-city', 'school-ross-valley']:
    with open(P / 'data' / 'extraction' / f'{jid}.json') as f:
        st = json.load(f).get('source_type','?')
    yp = P / 'data' / 'jurisdictions' / f'{jid}.yaml'
    has_yaml = yp.exists()
    print(f'{jid:35s} {st:12s} modal={st in modal_ok}  yaml={has_yaml}')
"
```

All 4 should show `modal=True yaml=True`.

## Phase 5: Wait for Cron + Confirm (next day)

After the next cron cycle (~6 hours):
```bash
gh run list --workflow=cron-high-velocity-refresh.yml --limit 1
# Should show success and include the new jurisdictions in logs
```

Check data freshness:
```bash
/data-status city-sausalito
/data-status city-fairfax
```

## Cost Estimate

| Jurisdiction | Platform | Meetings | Est. Cost |
|-------------|----------|----------|-----------|
| city-sausalito | Granicus | ~55 | $1.50 |
| city-fairfax | ProudCity | ~99 | $2.00 |
| school-sausalito-marin-city | BoardDocs | ~20 | $0.50 |
| school-ross-valley | BoardDocs | ~20 | $0.50 |
| **Total** | | | **~$4.50** |

No transcripts included. Add ~$25/city if AssemblyAI transcription desired.

## Key Files Modified This Session

| File | Change |
|------|--------|
| `scripts/onboard.py` | Pre-ingestion probe (Phase 2.1), cron readiness check (Phase 3.7), _instantiate_client factory |
| `scripts/ingest_local.py` | load_dotenv(), playwright_llm dedup |
| `scripts/modal_ingest.py` | browser_image (renamed from simbli_image), fetch_playwright_llm_meetings() |
| `packages/civicos-extraction/src/civicos_extraction/__init__.py` | Removed onboard import (was breaking Modal) |
| `packages/civicos-extraction/src/civicos_extraction/clients/playwright_llm.py` | DOM-based link extraction, markdown fence stripping |
| `packages/civicos-extraction/src/civicos_extraction/clients/civicplus.py` | Fixed ValidationResult kwargs |
| `data/extraction/city-novato.json` | Fixed view_id 1→7 |
| `data/jurisdictions/city-novato.yaml` | Fixed archives + column_map |

## Success Criteria

- [ ] Cron run from 2026-04-03 23:09 completed successfully
- [ ] San Rafael data freshness restored (meetings within last 3 days)
- [ ] city-sausalito queryable on live API
- [ ] city-fairfax queryable on live API
- [ ] school-sausalito-marin-city queryable on live API
- [ ] school-ross-valley queryable on live API
- [ ] Next cron cycle picks up all 4 new jurisdictions
