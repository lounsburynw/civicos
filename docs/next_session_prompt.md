# Recommended: Upcoming Ballot Preview

**Priority:** P0 (upcoming_ballot_preview)
**Area:** election_integration
**Date:** 2026-03-27

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

CivicOS has strong *historical* election results (141 elections across 3 counties via Civera ElectionStats) but cannot currently answer "what's on my upcoming ballot?" — the most useful question for civic participation. We researched all available sources and found a practical path using free government data: CA SOS certified candidate PDFs + Marin Registrar website scraping.

The June 2, 2026 Statewide Direct Primary is the target election. `whats_next(include_elections=True)` already returns the date, but we have zero candidate/measure data for it.

## What Needs to Be Done

### Phase 1: CA SOS PDF Parser (covers ~80% of the June ballot)

The CA Secretary of State publishes certified candidate lists as PDFs at predictable CDN URLs:
- `https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/congress.pdf`
- `https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/state-senate.pdf`
- `https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/assembly.pdf`
- `https://elections.cdn.sos.ca.gov/statewide-elections/2026-primary/governor.pdf`
- (plus: lt-governor, controller, treasurer, attorney-general, etc.)

These PDFs are **well-structured** with consistent layout per candidate:
- Name, party preference, incumbent marker (*)
- Address, phone, website, email
- Ballot designation (occupation)

**Marin-relevant districts:** US House D2, State Senate D2, Assembly D12

Parse with `pdfplumber` or `PyMuPDF`, filter to Marin districts, store as pre-election contest/candidate data.

### Phase 2: Marin Registrar Scraper Extension

Extend the existing `MarinRegistrarClient` (Playwright-based, Cloudflare-aware) with new methods:
- `get_candidate_filings()` — scrape the candidate list page for county/local races
- `get_ballot_measures()` — scrape measure list with full text, arguments, rebuttals

This covers: County Supervisor D5, Almonte Sanitary District, local measures (at least Measure J).

### Phase 3: Key Dates / Deadlines

CA SOS key dates page (`sos.ca.gov/.../key-dates-and-deadlines`) is a structured HTML table. Parse registration deadline (May 18), ballot mailing date (May 4), etc. Store in the existing `deadlines` field on `UpcomingElection`.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_results.py` — Existing CA SOS client (REST results API). New PDF parser methods go here or in a new file.
- `packages/civicos-extraction/src/civicos_extraction/clients/marin_registrar.py:27-495` — Existing Playwright scraper for Marin elections website. Extend with candidate filing + measure scraping.
- `packages/civicos/src/civicos/civicos.py:650-825` — `whats_next()` method that returns `UpcomingElection` objects. Already has `deadlines` field.
- `packages/civicos/src/civicos/types.py:139-147` — `UpcomingElection` dataclass (id, name, date, type, deadlines, source, source_url).
- `packages/civicos/src/civicos/storage/protocols/elections.py` — Election storage protocol (store_elections, store_election_contests).
- `docs/internal/election-data-research.md` — Full research including pre-election source analysis (see bottom section "Implementation Status").
- `scripts/modal_ingest.py` — Modal functions for election fetch/store.

## Suggested Approach

1. **Start with the SOS PDFs** — download one (e.g., `congress.pdf`), inspect structure with `pdfplumber`, build a parser that extracts candidate records
2. **Filter to Marin districts** — US House D2, State Senate D2, Assembly D12
3. **Map to storage format** — use existing `store_election_contests()` with contest_type, candidates, etc.
4. **Wire into a Modal function** — `fetch_sos_candidate_filings()` that downloads + parses + stores
5. **Test with live data** — the June 2026 PDFs are already published on the CDN
6. **If time permits** — extend Marin Registrar client for county-level candidates/measures

## Relevant Memories

- `memory/feedback_browser_automation.md` — Cloudflare-protected sites need headed Playwright
- `memory/feedback_civic_data_aggregators.md` — Prefer primary government sources over aggregator APIs
- `memory/feedback_no_hardcoded_locale.md` — Extraction clients must be locale-agnostic

## Tests to Run

```bash
# Election tests (regression)
pytest packages/civicos-extraction/tests/test_election_detection.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] CA SOS PDF parser extracts structured candidate data (name, party, occupation, district)
- [ ] Marin-relevant races identified and filtered (House D2, Senate D2, Assembly D12)
- [ ] Candidate data stored via existing election storage protocol
- [ ] `whats_next(include_elections=True)` returns June 2026 with candidate details
- [ ] At least one deadline populated (registration deadline: May 18, 2026)
