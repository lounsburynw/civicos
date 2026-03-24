# Recommended: HTML Agenda Extraction

**Priority:** P0 (html_agenda_extraction)
**Area:** turnkey_onboarding
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We just completed CivicClerk + eScribe pipeline wiring (both done). The pipeline now supports 5 meeting sources: proudcity, granicus, legistar, civicclerk, escribe. El Cerrito has 15 meetings in Postgres.

**HTML agenda extraction is next** because some cities (especially Legistar/CivicClerk cities) serve agendas as HTML pages, not PDFs. The chunk extraction pipeline currently detects this case (`validate_pdf_content` returns `is_valid_pdf=False` with "DEGENERATE CASE" warnings) but silently skips them — resulting in chunks=0, which breaks agenda search for those cities.

## What Was Done This Session

1. Wired CivicClerk into `fetch_meetings()` — 15 El Cerrito meetings stored in Postgres
2. Fixed `normalize_event()` to use correct API fields (`eventName`, `eventLocation` dict)
3. Wired eScribe into `fetch_meetings()` — code correct but eScribe has SSL cert issue on macOS
4. Probed Bay Area CivicClerk cities — only El Cerrito (`elcerritoca`) is active; others returned 404

## Key Files

| File | Purpose |
|------|---------|
| `packages/civicos-extraction/src/civicos_extraction/cli/chunks.py:383` | `validate_pdf_content()` — detects HTML content with "DEGENERATE CASE" warnings |
| `packages/civicos-extraction/src/civicos_extraction/cli/chunks.py:1134` | Skip logic: `if not dl.is_valid_pdf: continue` — this is where HTML agendas are dropped |
| `packages/civicos-extraction/src/civicos_extraction/cli/chunks.py:1322` | Cloud mode skip: same pattern, `if not download_result.is_valid_pdf:` |
| `scripts/modal_ingest.py:3625` | `extract_chunks()` — calls `run_chunk_extraction()` |
| `packages/civicos-extraction/src/civicos_extraction/processing/agenda_integration.py` | May have HTML agenda handling logic already |

## Suggested Approach

1. **Understand the current flow** — Read `run_chunk_extraction()` in `chunks.py` to see how PDFs are downloaded, validated, and parsed
2. **Find the skip points** — Lines 1134 and 1322 are where `is_valid_pdf=False` causes skipping. These are the insertion points for HTML handling
3. **Add HTML text extraction** — When content is HTML (detected by validate_pdf_content), extract text using BeautifulSoup or similar. Strip nav/header/footer, keep agenda item text
4. **Chunk the HTML text** — Use the same chunking logic as PDFs (text → fixed-size chunks with overlap)
5. **Store chunks** — Same `store_chunks()` call, just with `source_type="html_agenda"` in metadata
6. **Test on a real city** — Find a city with HTML agendas (check CivicClerk agenda URLs — they may be HTML). Sacramento Legistar may also have HTML agendas
7. **Verify chunks appear** — Run `/data-status` to confirm chunks > 0 for the test city

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] HTML content detected (via existing validate_pdf_content)
- [ ] HTML text extracted into chunks instead of silently skipping
- [ ] Chunks stored in Postgres with correct meeting_id association
- [ ] At least one city's HTML agendas produce chunks > 0
- [ ] PDF agenda extraction still works (no regression)
- [ ] San Rafael chunk count unaffected

## Turnkey Onboarding Roadmap (remaining)

After HTML agenda extraction:
- P1: `issue_provider_dispatch` — generalize fetch_issues() like fetch_meetings()
- P2: `onboard_quality_gates`, `issue_provider_detection`, `onboard_end_to_end_test`
- P3: `onboard_transcript_auto`, `onboard_deploy_integration`, `onboard_batch_mode`
