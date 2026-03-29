# Recommended: Ballot Measure Content Ingestion

**Priority:** P0 (ballot_measure_content)
**Area:** ballot_awareness
**Date:** 2026-03-29

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session completed `local_candidate_data` and significantly hardened the onboarding automation pipeline. Local election results (mayor, city council, town council, ballot measures) are now extracted from the Civera ElectionStats GraphQL API for all 3 pilot jurisdictions. The onboarding flow was improved with: Civera division filter validation, CDE-based school district detection, auto-detected contact info from city websites, and YouTube meeting playlist discovery.

The ballot data gap: we store pass/fail results for local measures (e.g., "Measure P: Yes 52%, No 48%") but **not the measure text itself** — what voters actually need to decide. State measures come from the CA voter guide; local measures come from county sample ballots.

## What Needs to Be Done

Ingest ballot measure content: the actual question text, fiscal impact summaries, and pro/con arguments. This makes the `explore what='my_ballot'` response genuinely useful — right now it shows measure titles but not what they propose.

## Key Files

- `packages/civicos/src/civicos/_internal/elections/__init__.py:30-45` — `ContestType` enum includes `local_measure`, `state_proposition`
- `packages/civicos-extraction/src/civicos_extraction/clients/civera_election_stats.py:428-441` — `_map_contest_type()` handles ballot questions, stores `raw_data.mapped_ballot_measure`
- `packages/civicos-services/src/civicos_services/query/verbs.py:1298-1427` — `explore what='my_ballot'` ballot display code
- `packages/civicos/src/civicos/storage/postgres_backend.py:8913-8977` — `store_election_contests()` with `raw_data` JSONB
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_ballot_preview.py` — pattern for CA SOS PDF extraction

## Data Sources

1. **State measures** — CA Voter Guide at `voterguide.sos.ca.gov`. Published as web pages and PDFs with: measure text, fiscal impact, arguments for/against. The CA SOS ballot preview client is a good pattern to follow (PDF -> structured data).

2. **Local measures** — County sample ballots. The Civera API already stores `ballotQuestion.questionText` but it's just the title. Full text + fiscal impact come from the county recorder's sample ballot publication.

3. **Already stored** — `raw_data.mapped_ballot_measure` has: title, passed (bool), yes_votes, no_votes, percentages. Need to add: `full_text`, `fiscal_impact`, `argument_for`, `argument_against`.

## Suggested Approach

1. **Extend the ballot measure schema** — Add content fields to the `mapped_ballot_measure` structure in `raw_data` JSONB (no schema migration needed — it's JSON).

2. **Build CA voter guide client** — Fetch state measure content from `voterguide.sos.ca.gov`. Follow the CA SOS ballot preview pattern (PDF or HTML -> structured extraction). Use LLM only to parse fetched content, not as a knowledge source.

3. **Extend Civera extraction** — Check if the Civera GraphQL API has fuller ballot question text. If not, the county sample ballot (Marin registrar) is the source for local measure text.

4. **Update ballot display** — Modify `explore what='my_ballot'` to include measure content in the response.

5. **Write tests** — Mock-based unit tests for extraction, integration test for ballot display.

## Tests to Run

```bash
# Existing ballot tests
pytest packages/civicos/tests/test_explore_ballot.py -v --override-ini="addopts="
# Election tests (regression)
pytest packages/civicos/tests/test_election_calendar.py -q --override-ini="addopts="
# Extraction tests
pytest packages/civicos-extraction/tests/test_marin_registrar.py -q --override-ini="addopts=" -k "not integration"
```

## Success Criteria

- [ ] State measure content (text, fiscal impact, pro/con) ingested from CA voter guide
- [ ] Local measure content ingested from county sample ballot or Civera
- [ ] `explore what='my_ballot'` includes measure content in response
- [ ] Content stored in `raw_data.mapped_ballot_measure` (no schema migration)
- [ ] Works for 2024 measures already in database (backfill)
- [ ] Extraction pattern generalizable to other counties

## Session Summary (for context)

This session made 5 commits:
1. `378ea03` — Extracted local candidate data from Civera for all 3 pilot cities (40 contests, 92 candidates)
2. `1dc1ef1` — Fixed `_infer_division_name` to use bare city names (broader Civera matching)
3. `cb22dde` — Added Civera validation + CDE school district detection to onboarding
4. `e4e30c4` — Added contact info auto-detection + YouTube playlist detection
5. `6e5b240` — Wired all auto-detection functions into `onboard_jurisdiction` flow

Key design principle established: **LLMs process fetched external data, never their own training knowledge, for civic facts.** Authoritative sources: CDE for school districts, Civera for election results, Census for districts, city websites for contact info.
