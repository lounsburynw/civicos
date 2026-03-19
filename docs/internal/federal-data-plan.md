# Federal Data Enrichment Plan

**Created:** 2026-03-18
**Scope:** 10 sessions
**Goal:** Transform federal data from a firehose of DC activity into locally-relevant, actionable civic information that mirrors the structure of city-level data.

## Current State

We have the **catalog** of federal activity but not the **relevance layer** that makes it meaningful to a specific resident:

| Corpus | Rows | Embeddings | Refresh | Gap |
|--------|------|-----------|---------|-----|
| executive_orders | 1,525 | 21,046 | Weekly | No local impact mapping |
| federal_rules | 4,115 | 3,606 (88%) | Weekly | 45% of proposed rules missing comment_url; no relevance scoring |
| legislation (US) | 14,855 | ~45k | **NOT REFRESHING** | No votes, no hearing data, no scheduled refresh |
| legislation (CA) | 5,842 | ~22k | Weekly (failing) | LegiScan sync errors |
| federal_awards | 5 | 0 | Manual | Client exists, barely used. Should be hundreds of awards |
| federal_programs | 2,346 | 14,033 | Weekly | Missing cfda_numbers on many programs |
| legislative_events | 4,849 | 0 | Weekly | Parsed from bills, no congressional hearings |

**API keys available:** Congress.gov (YES), LegiScan (YES), USAspending (no key needed), Federal Register (no key needed).
**API keys missing:** regulations.gov (read-only GET works without key), SAM.gov (registration needed for full access).

## Design Principle

The single shared PostgreSQL database is a bootstrap constraint. The target architecture is fully federated — each jurisdiction with its own DB, federating via peer MCP calls. Data structures should support eventual per-jurisdiction isolation:
- Federal data tagged with `jurisdiction_id = 'country-united-states'`
- Funding data tagged with recipient jurisdiction
- Avoid designs that assume shared-DB joins across jurisdiction boundaries

## Session Plan

### Sessions 1-2: Federal Funding Pipeline (USAspending)

**Parallel to:** city budget corpus
**Question answered:** "What federal money flows to my city?"

**Session 1 — Ingest**
- Bulk ingest via existing `USAspendingClient.get_awards()` for all configured jurisdictions
- USAspending API is free, no key needed, supports geographic filtering
- Target: hundreds of awards for San Rafael + Marin County jurisdictions
- Store in existing `federal_awards` table (schema already correct)
- Add to `scheduled_low_velocity_refresh()` in `scripts/modal_ingest.py`
- Index vector embeddings for semantic search

**Session 2 — Query + UX**
- Build `FundingAdapter` for v2 search: `civic.search("housing funding")` returns relevant awards
- Add to `civic.upcoming` for grants with approaching expiration dates
- Wire into extension: "Federal Funding" section showing active grants with amounts, agencies, expiration dates
- MCP tool: `search_federal_funding` with jurisdiction + topic filters

**Key files:**
- `packages/civicos-extraction/src/civicos_extraction/clients/usaspending.py` — client exists
- `packages/civicos/src/civicos/storage/postgres_backend.py` — `federal_awards` table exists
- `scripts/modal_ingest.py` — add to low-velocity refresh

### Sessions 3-4: Congressional Votes

**Parallel to:** city council voting records (`get_voting_record` tool)
**Question answered:** "How did my representative vote on this?"

**Session 3 — Ingest**
- Extend `CongressGovClient` with:
  - `get_member_votes(bioguide_id)` — Congress.gov `/member/{id}/voted-on`
  - `get_bill_votes(congress, bill_type, number)` — `/bill/{congress}/{type}/{number}/actions`
- New `congressional_votes` table: `bill_id`, `member_bioguide_id`, `vote` (yea/nay/present/not_voting), `roll_call_number`, `vote_date`
- Link to `legislation` table by bill_id, to `elected_officials` by bioguide_id
- Ingest recent votes for CA senators + CA-2 representative
- Add to weekly refresh

**Session 4 — Query + UX**
- MCP tool: `get_congressional_votes` (by member, by bill, by topic)
- Wire into v2: `civic.search("housing votes")` returns how local reps voted
- Extension: "How They Voted" view on Federal tab, linked from legislation items
- Parallels existing `get_voting_record` for city council

**Key files:**
- `packages/civicos-extraction/src/civicos_extraction/clients/representatives.py` — `CongressGovClient` class
- Congress.gov API: `https://api.congress.gov/v3` (5000 req/hour)

### Sessions 5-6: Congressional Hearings

**Parallel to:** city council meetings with public comment
**Question answered:** "What congressional hearings are coming up that affect my community?"

**Session 5 — Ingest**
- Extend `CongressGovClient` with:
  - `get_committee_hearings(committee_code, start_date)` — `/committee-meeting`
  - `get_hearing_detail(hearing_jacketNumber)` — `/hearing/{congress}/{jacketNumber}`
- New `congressional_hearings` table: `hearing_id`, `committee`, `date`, `title`, `witnesses`, `related_bill_ids`, `location`, `url`
- Filter to committees relevant to locally-stored topics (map committee codes to topic categories)
- Ingest upcoming + recent 90 days
- Add to weekly refresh

**Session 6 — Query + UX**
- Wire into `civic.upcoming(types=["hearings"])` for federal hearings alongside state legislative hearings
- Extension Federal tab timeline: hearings + comment periods on unified calendar
- MCP tool: `get_upcoming_hearings` (already exists for state, extend for federal)
- Written testimony submission guidance (parallel to local public comment guidance)

**Key files:**
- Congress.gov API: `/committee-meeting`, `/hearing` endpoints
- `packages/civicos-services/src/civicos_services/query/verbs.py` — `execute_upcoming()`

### Sessions 7-8: Local Impact Relevance Layer

**No local parallel — this is novel**
**Question answered:** "Of all these federal rules, which ones actually affect my city?"

**Session 7 — Relevance Scoring**
- Build agency-to-topic mapping using existing data:
  - Map federal agency names (EPA, HUD, DOT, FEMA, etc.) to topic categories that exist in local municipal code and legislation
  - Score rules by: (a) agency→topic match, (b) text mentions of California/Marin/San Rafael, (c) CFR part matches locally-relevant regulatory areas
- Add `local_relevance_score` and `relevance_reasons` columns to `federal_rules`
- Heuristic scoring (fast, no LLM cost) — run at ingest time
- Backfill existing 4,115 rules

**Session 8 — Relevance-Filtered UX**
- Extension Federal tab sorts by relevance score (locally-important rules first, not chronological)
- `draft_federal_comment` shows "This rule is relevant to San Rafael because..." context
- `civic.search` with `corpus=["federal_rules"]` includes relevance boosting
- `civic.explore(what="actions")` highlights locally-relevant open comment periods

**Key files:**
- `packages/civicos/src/civicos/storage/postgres_backend.py` — add columns
- `apps/civicos-mcp/tools/handlers.py` — update `draft_federal_comment`
- `packages/civicos-services/src/civicos_services/query/adapters.py` — relevance boost

### Session 9: Pipeline Hardening

**Question answered:** "Is the federal data staying current?"

- Add US federal legislation to `scheduled_low_velocity_refresh()` (currently only CA syncs)
- Debug and fix CA legislation sync failure (`status: failed` on last run)
- Close the 12% embedding gap on federal_rules (509 rules without vectors)
- Verify all new corpora (awards, votes, hearings) have scheduled refreshes
- Add refresh_metadata entries for all federal corpora

**Key files:**
- `scripts/modal_ingest.py` — `scheduled_low_velocity_refresh()`
- `.github/workflows/cron-low-velocity-refresh.yml`

### Session 10: Federal Server Deployment

**Question answered:** "Can AI agents access federal data independently?"

- Deploy `country-united-states` Modal MCP (`civicos-federal`)
- Now meaningful: serves funding search, congressional votes, hearing timeline, relevance-scored comment periods
- Federal server becomes the peer that city MCPs will eventually federate with when the shared DB splits
- Create `civicos-federal-env` Modal secret
- Verify all federal tools served at `federal.civicosproject.org/mcp`

**Key files:**
- `apps/civicos-mcp/modal_mcp.py`
- `apps/civicos-mcp/jurisdictions/federal.yaml`
- `config/registry.json`

## Structural Parallels

| Local civic data | Federal equivalent | Sessions |
|---|---|---|
| City council meetings + public comment | Federal rulemaking comment periods | Done (existing) |
| Council votes/decisions | Congressional votes on bills | 3-4 |
| Upcoming meetings | Congressional hearings | 5-6 |
| City budget | Federal funding to city | 1-2 |
| Staff reports | Agency impact assessments / CBO scores | Out of scope |
| Municipal code | Code of Federal Regulations (CFR) | Out of scope |
| 311 issues | (no direct equivalent) | N/A |
| "Why does this matter here?" | Local impact relevance scoring | 7-8 |

## What This Plan Leaves Out

- **CFR (Code of Federal Regulations)** — too massive, marginal value until relevance layer is strong
- **Agency enforcement actions** (EPA fines, OSHA inspections) — fragmented APIs, no unified source
- **CBO scores / impact assessments** — available via Congress.gov, lower priority than votes/hearings
- **Relay integration for comment tracking** — coordinating "I submitted a comment" across relay network
- **Grant application deadlines** (Grants.gov) — needs SAM.gov API key
- **regulations.gov comment counts** — GET API can show how many comments each rule received (social proof)

## Dependencies

- Sessions 1-2 are independent, can start immediately
- Sessions 3-4 depend on `CONGRESS_GOV_API_KEY` (available)
- Sessions 5-6 depend on sessions 3-4 (shared Congress.gov client extensions)
- Sessions 7-8 depend on having enough federal data to score (after sessions 1-6)
- Session 9 depends on sessions 1-6 (all new corpora need refresh scheduling)
- Session 10 depends on all above (the federal server should serve all the new data)
