# Recommended: Turnkey Onboard + Marin Sibling Ingestion

**Priority:** P0 (`marin_sibling_ingestion`)
**Area:** federation_testbed
**Date:** 2026-03-15

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session rewrote `docs/public/data-ingestion.md` with correct Modal CLI commands and verification steps. During review, we discovered the onboarding experience has significant friction: two separate config files (extraction JSON + jurisdiction YAML), no single command to go from zero to ingested data, and the `/onboard` flow is a Claude Code skill rather than something an operator can run. Mill Valley and San Anselmo are the perfect test cases — both partially onboarded with meetings in Postgres but 0 decisions, chunks, or vectors.

## What Was Done This Session

1. **Data ingestion guide rewritten** (`docs/public/data-ingestion.md`) — correct `modal run` commands for all 10 ingestion steps, cost tiers, verification workflow
2. **P0 item created** for this task with full scope notes

## Three Deliverables

### 1. Streamline the onboard flow into a single entry point

Currently an operator must:
- Run `onboard_jurisdiction()` to generate extraction config JSON
- Manually create jurisdiction YAML from schema template
- Run 6-10 separate `modal run` commands for ingestion
- Run vector indexing separately

**Goal:** A single Modal function (e.g., `modal run scripts/modal_ingest.py::onboard`) that takes a jurisdiction URL + ID and does everything: platform detection, config generation, Tier 1+2 ingestion, and vector indexing. Or at minimum, a script that chains the existing functions.

### 2. Validate on Mill Valley and San Anselmo

Run the new flow on both cities. Current state:

| | Mill Valley | San Anselmo |
|---|---|---|
| Registry (`config/registry.json`) | Yes | Yes |
| Extraction config (`data/extraction/`) | Yes (Granicus) | **Missing** |
| Jurisdiction YAML (`data/jurisdictions/`) | **Missing** | Yes (fully populated) |
| Meetings in Postgres | 56 | 169 |
| Decisions | 0 | 0 |
| Vectors | 0 | 0 |

**Success criteria:** Non-zero decisions AND vectors for both cities.

### 3. Update docs

After validating the flow works, update `docs/public/data-ingestion.md` to document the turnkey path alongside the manual step-by-step that's already there.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/onboard.py` — `onboard_jurisdiction()` generates extraction config, does platform detection
- `data/jurisdictions/schema.yaml` — YAML schema reference
- `data/jurisdictions/city-san-anselmo.yaml` — complete example (San Anselmo has YAML but no extraction config)
- `data/extraction/city-mill-valley.json` — Granicus extraction config (Mill Valley has this but no YAML)
- `scripts/modal_ingest.py` — all ingestion functions (`fetch_meetings`, `extract_chunks`, `extract_agenda_items`, `extract_decisions`)
- `scripts/modal_vectors.py:534` — `main()` entry point for vector indexing
- `.claude/commands/onboard.md` — current `/onboard` skill (references `civic-extract onboard --full` which may not exist)
- `docs/public/data-ingestion.md` — the guide we just rewrote (update after validation)

## Suggested Approach

1. Read `onboard.py` to understand what `onboard_jurisdiction()` already does
2. Decide the right entry point: new Modal function in `modal_ingest.py`, standalone script, or enhanced `onboard_jurisdiction()`
3. Implement — should generate both configs if missing, then chain Tier 1+2+4 ingestion
4. Test on Mill Valley first (simpler: 56 meetings, has extraction config, needs YAML)
5. Test on San Anselmo (169 meetings, has YAML, needs extraction config)
6. Verify with `/data-status` for both cities
7. Update `docs/public/data-ingestion.md` with the turnkey flow
8. Update the `/onboard` skill if the interface changed

## Tests to Run

```bash
# Verify data landed
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, DataStatus, format_data_status
for jid in ['city-mill-valley', 'city-san-anselmo']:
    c = CivicOS(jid)
    status = DataStatus(c.storage, c._vectors, jid)
    print(f'=== {jid} ===')
    print(format_data_status(status.summary()))
"

# Vector stats
modal run scripts/modal_vectors.py --jurisdiction city-mill-valley --stats-only
modal run scripts/modal_vectors.py --jurisdiction city-san-anselmo --stats-only
```

## Success Criteria

- [ ] Single command/function onboards a jurisdiction from URL to searchable data
- [ ] Mill Valley: non-zero decisions, chunks, and vector embeddings
- [ ] San Anselmo: non-zero decisions, chunks, and vector embeddings
- [ ] `docs/public/data-ingestion.md` updated with turnkey flow
- [ ] A newbie reading the guide could onboard a city without Claude Code skills

## Parallel Session Note

`amlegal_client_hardening` (P1, security_fixes) may be in progress in a parallel session. Avoid touching `packages/civicos/src/civicos/_internal/legal/corpus/` to prevent conflicts.
