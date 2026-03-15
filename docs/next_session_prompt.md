# Recommended: Data Ingestion Guide

**Priority:** P0 (`data_ingestion_guide`)
**Area:** operator_readiness
**Date:** 2026-03-15

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed the v2 adapter storage refactor — all corpus adapters now call storage/vector backends directly instead of CivicOS methods, and cross-jurisdiction search no longer creates CivicOS instances. However, validation showed that sibling cities have no extracted decisions (Mill Valley: 0, San Anselmo: 0, Berkeley: 0), which blocks 3-4 federation_testbed items (`cross_marin_query_prototype`, `cross_county_query_prototype`, `pagination_protocol_update`, `federation_adr`). Writing the data ingestion guide is the force multiplier that unblocks all of them.

## What Was Done This Session

1. **v2 adapter refactor** — All 10 adapters changed from `search(civic, ...)` to `search(storage, vectors, ...)`. Cross-jurisdiction fan-out simplified (no CivicOS instances). 130 tests updated and passing.

## Recommended Task

Write a public-facing guide (`docs/public/ingestion.md` or similar) that enables operators to ingest data for their jurisdiction. The guide should cover:
- How to add a new jurisdiction (config YAML + registry.json)
- How to run each ingestion source (meetings, decisions, issues, legislation, transcripts, municipal code)
- How to verify data landed correctly (`/data-status`)
- How to trigger vector indexing after ingestion

## Key Files

- `docs/internal/ingestion.md` — Existing internal ingestion doc (San Rafael-focused, not operator-facing)
- `data/jurisdictions/*.yaml` — Jurisdiction config files (schema.yaml for format)
- `config/registry.json` — Jurisdiction registry (parent_jurisdictions, display names)
- `packages/civicos-extraction/` — All extraction scripts/parsers
- `.claude/skills/ingest.md` — The `/ingest` slash command
- `.claude/skills/onboard.md` — The `/onboard` slash command

## Current Data State (for context)

| Jurisdiction | Decisions | Meetings | Notes |
|---|---|---|---|
| city-san-rafael | 83 | 96 | Full pilot data |
| city-mill-valley | 0 | 56 | Meetings only, no decisions extracted, NO jurisdiction YAML |
| city-san-anselmo | 0 | 169 | Meetings only, no decisions extracted |
| city-berkeley | 0 | 10 | Minimal data |

## Suggested Approach

1. Read existing `docs/internal/ingestion.md` and `/onboard` skill to understand current workflow
2. Read `data/jurisdictions/schema.yaml` and a sample YAML (e.g., `city-san-rafael.yaml`)
3. Write `docs/public/ingestion.md` — operator-facing guide covering the full pipeline
4. Consider whether to also run ingestion for Mill Valley / San Anselmo to validate the guide (and unblock federation items)

## Tests to Run

```bash
# No specific test file — this is a docs task
# But validate any code examples in the guide work:
/data-status city-san-rafael     # Verify diagnostics work
```

## Success Criteria

- [ ] Public-facing ingestion guide exists at `docs/public/ingestion.md`
- [ ] Guide covers: jurisdiction setup, source ingestion, verification, vector indexing
- [ ] Guide is accurate against current codebase (not stale)
- [ ] Optionally: Mill Valley or San Anselmo has decisions after following the guide

## Parallel Session Note

`amlegal_client_hardening` (municipal code parser) is being worked on in a parallel session. Avoid touching `packages/civicos-extraction/` municipal code parsers or `packages/civicos/src/civicos/_internal/legal/corpus/` to prevent conflicts.
