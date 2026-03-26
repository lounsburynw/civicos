# Recommended: Run Marin Election Ingestion + Build BoardDocs Client

**Priority:** P0 (boarddocs_client)
**Area:** election_integration
**Date:** 2026-03-25

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session built the `MarinRegistrarResultsClient` — a GraphQL client for historical Marin County election results (46 elections, 521 contests, 1,404 candidates, 2010-2025). Client is complete with 34 unit + 5 integration tests, storage mappers, and a Modal ingestion function. The client URL is configurable for multi-county support (Sonoma, Yolo use the same Civera/ElectionStats platform).

**Not yet done:** (1) actual ingestion into Postgres, (2) schema decision on `election_candidates` table.

## Pre-P0: Run Marin Election Ingestion + Schema Decision

Before starting BoardDocs, run the election results ingestion that was built but never executed.

### Schema Decision: election_candidates table

Currently candidate vote data (votes_received, is_winner, vote_percentage) lives only in `raw_data` JSONB on `election_contests`. This works for display but prevents direct SQL queries on vote data.

**Consider** adding a dedicated table before ingestion:
```sql
CREATE TABLE election_candidates (
    id TEXT NOT NULL,
    contest_id TEXT NOT NULL,
    name TEXT NOT NULL,
    party TEXT,
    votes_received INTEGER,
    vote_percentage FLOAT,
    is_winner BOOLEAN DEFAULT FALSE,
    source TEXT,
    valid_from TIMESTAMP, valid_to TIMESTAMP, deleted_at TIMESTAMP,
    PRIMARY KEY (id, contest_id, valid_from)
);
```

Enables: "races with <5% margin", "link council voting records to election results." If only the API displays contest details, JSONB is fine — skip the table.

### Run Ingestion

```bash
# Dry run first
modal run scripts/modal_ingest.py::fetch_marin_election_results --dry-run

# San Rafael
modal run scripts/modal_ingest.py::fetch_marin_election_results --division-filter "City of San Rafael"

# All Marin (no filter) — covers Mill Valley, San Anselmo, etc.
modal run scripts/modal_ingest.py::fetch_marin_election_results
```

## P0: BoardDocs Client

Build `BoardDocsClient` for school board meeting ingestion. Covers 5 Marin districts: MCOE, Ross Valley SD, Larkspur-Corte Madera SD, Sausalito-Marin City SD, Marin Community College.

**API details** (undocumented POST endpoints, no auth):
- `POST /BD-GetMeetingsList?open` — returns JSON meeting list
- `POST /PRINT-AgendaDetailed` — returns HTML agenda with file links
- Config per district: `app_path` (e.g. `ca/rova`) + `committee_id`
- Reference impl: `llama-index-readers-boarddocs` (pip package)
- `docs/internal/election-data-research.md` has known committee IDs for 4 Marin districts

### Key Files
- `packages/civicos-extraction/src/civicos_extraction/clients/boarddocs.py` — create new
- `packages/civicos-extraction/src/civicos_extraction/clients/factory.py` — register source_type
- `packages/civicos-extraction/tests/test_boarddocs.py` — create new
- `docs/internal/election-data-research.md` — BoardDocs section has endpoint details + committee IDs

### Suggested Approach
1. Read `docs/internal/election-data-research.md` BoardDocs section for full API details
2. Build `BoardDocsClient` with `get_meetings()` and `get_agenda(meeting_id)`
3. Register as `boarddocs` source type in factory
4. Map meetings to existing Meeting dataclass
5. Test against live endpoints (no auth needed)

### Election Results Context (already complete)
- `packages/civicos-extraction/src/civicos_extraction/clients/marin_registrar.py:506` — `MarinRegistrarResultsClient`
- `packages/civicos-extraction/tests/test_marin_registrar.py` — 39 tests
- `scripts/modal_ingest.py:3509` — `fetch_marin_election_results()` Modal function
- `packages/civicos/src/civicos/_internal/elections/__init__.py` — Candidate has votes_received, vote_percentage, is_winner; BallotMeasure has yes/no vote tallies
- `packages/civicos/src/civicos/storage/postgres_backend.py:8913` — `store_election_contests()` stores to `raw_data` JSONB

## Tests to Run

```bash
# Election results tests (verify still passing)
pytest packages/civicos-extraction/tests/test_marin_registrar.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Schema decision made on election_candidates table (add or skip)
- [ ] Marin election results ingested to Postgres
- [ ] BoardDocsClient fetches meetings from at least one Marin school district
- [ ] BoardDocs meetings map to Meeting dataclass
- [ ] Registered as source_type in factory
- [ ] No regressions in smoke tests
