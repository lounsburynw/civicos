# Recommended: Turnkey Onboard Hardening

**Priority:** P0 (`turnkey_onboard_hardening`)
**Area:** federation_testbed
**Date:** 2026-03-15

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session built `scripts/onboard.py` — a turnkey onboarding script that takes a city name and produces searchable data in one command. We validated it on Mill Valley and San Anselmo. Both have non-zero meetings, agenda items, decisions, and vectors. However, the runs exposed 7 data quality gaps that must be fixed before cross-jurisdiction queries (P1) can rely on this data, and before open sourcing.

## The 8 Gaps (prioritized by impact)

### 0. No validation gate before full ingestion (CRITICAL)
The onboard script runs 365 days of ingestion immediately — $3-4 in LLM spend — with no upfront check that the data is actually extractable. Mill Valley's 0 chunks and 2/57 decisions would have been caught by ingesting ~30 days first, verifying quality, then scaling up. **Fix:** Add a two-phase flow: (1) ingest a small window (e.g., 30 days), run quality checks (chunks > 0? decisions > 0? agenda items look sane?), present results to operator, (2) only proceed to full backfill if quality passes or operator explicitly confirms. This prevents burning LLM budget on jurisdictions where the platform doesn't yield useful data.
- `scripts/onboard.py` — add `--validate-first` (default on) that runs a 30-day sample + quality gate before full ingestion
- `.claude/commands/onboard.md` — has a "Data Quality Reference" section with San Rafael baseline ratios and red flags per platform. Use these thresholds in the validation gate.

### 1. Chunks = 0 for Granicus HTML agenda sites (HIGH)
Mill Valley got 0 chunks. Granicus uses `GeneratedAgendaViewer.php` (inline HTML) instead of direct PDF links. The chunk extractor only handles PDFs. **Fix:** Extract text from the HTML agenda pages when no PDF link is found. This affects most Granicus jurisdictions.
- `scripts/modal_ingest.py:2818` — `extract_chunks()` function
- Chunk extraction pipeline in `packages/civicos-extraction/`

### 2. Duplicate meetings from multi-view archives (HIGH)
Mill Valley processed 107 meetings for decisions but only has 57 unique meetings. Views 2 and 3 contain identical data. **Fix:** Deduplicate by meeting ID before LLM extraction, or ensure onboard only picks one view per body.
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:519` — `get_meetings()` deduplicates, but decisions/agenda extractors iterate all views independently

### 3. Thin decisions for Mill Valley (MEDIUM)
Only 2/57 meetings yielded decisions. HTML minutes are sparse summaries. San Anselmo got 112, so the extractor works. **Fix:** Add a quality signal to post-onboard report.

### 4. No post-onboard quality report (MEDIUM)
Script prints counts but doesn't assess quality. **Fix:** Add summary section to `scripts/onboard.py` that flags low-quality results with actionable guidance.

### 5. No idempotency on re-run (MEDIUM)
Re-running doubles LLM spend. **Fix:** Verify agenda/decision extraction respects existing data on re-run.

### 6. County enrichment is fragile YAML patching (LOW)
String replacement on YAML is brittle. **Fix:** Use `yaml.safe_load()` / `yaml.dump()` round-trip.

### 7. City name slug sensitivity (LOW)
Different capitalizations produce different slugs. **Fix:** Normalize input before slugifying.

## Current Data State

| | San Rafael | Mill Valley | San Anselmo |
|---|---|---|---|
| Meetings | 98 | 57 | 152 |
| Chunks | 5,084 | **0** | 14 |
| Agenda items | — | 166 | 34 new + prior |
| Decisions | 44 | **2** | **112** |
| Vectors | 16,786 | 591 | 1,037 |

## Key Files

- `scripts/onboard.py` — the turnkey script (207 lines)
- `scripts/modal_ingest.py:2818` — `extract_chunks()`, `:2940` — `extract_agenda_items()`, `:3056` — `extract_decisions()`
- `packages/civicos-extraction/src/civicos_extraction/onboard.py:674` — `_generate_jurisdiction_yaml()`
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:451` — `get_events()` iterates all view_ids
- `data/extraction/city-mill-valley.json` — auto-generated extraction config
- `data/jurisdictions/city-mill-valley.yaml` — auto-generated jurisdiction YAML

## Suggested Approach

1. Start with **gap #1 (HTML chunks)** — biggest impact, unblocks PDF search for all Granicus sites
2. Then **gap #2 (dedup)** — prevents wasting LLM spend on duplicates
3. Then **gap #4 (quality report)** — gives operators visibility
4. Gaps 5-7 are lower priority but quick fixes
5. Re-run onboard on Mill Valley after fixes to verify improvement
6. Verify with `/data-status city-mill-valley`

## Tests to Run

```bash
# Check current state
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, DataStatus, format_data_status
for jid in ['city-mill-valley', 'city-san-anselmo']:
    c = CivicOS(jid)
    status = DataStatus(c.storage, c._vectors, jid)
    print(f'=== {jid} ===')
    print(format_data_status(status.summary()))
"
```

## Success Criteria

- [ ] Mill Valley chunks > 0 (HTML agenda text extraction works)
- [ ] No duplicate meeting processing in agenda/decision extraction
- [ ] Post-onboard output includes quality assessment with actionable guidance
- [ ] Re-running onboard doesn't re-extract already-processed meetings
- [ ] `cross_marin_query_prototype` (P1) is unblocked with quality data
