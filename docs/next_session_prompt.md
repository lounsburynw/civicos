# Recommended: Multi-County Registrar Research

**Priority:** P0 (multi_county_registrar_research)
**Area:** election_integration
**Date:** 2026-03-26

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

CivicOS has deep election data for Marin County (46 elections, 521 contests, 1,404 candidates, precinct-level results since 2010) via the `MarinRegistrarResultsClient` which scrapes a GraphQL endpoint at `pastelections.marincounty.gov`. CA SOS covers statewide races. But there are no local election results for any other CA county.

The school directory we just built (452 districts, 56 counties) gives us statewide onboarding infrastructure. The next step is expanding election results coverage beyond Marin.

## What Needs to Be Done

Research and prototype election results clients for additional CA counties:

1. **Survey county registrar systems** — Each CA county runs its own election reporting. Identify the common platforms:
   - HART InterCivic (used by several CA counties)
   - Dominion Democracy Suite
   - ES&S ElectionWare
   - Custom county portals
   - Do any share the same GraphQL/REST pattern as Marin?

2. **Pick a pilot county** — Good candidates:
   - **Sonoma** — neighboring county, already has federation test relay
   - **Alameda** — large county, 7 school districts already detected
   - **San Mateo** — 16 school districts detected, Bay Area neighbor

3. **Build or generalize a client** — Can the `MarinRegistrarResultsClient` pattern be generalized? Or does each county need a bespoke client?

4. **Wire into election_sources config** — Same pattern as Marin: add the new county's registrar to `election_sources` in the jurisdiction config.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/marin_registrar.py` — Current Marin client (GraphQL + Playwright)
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_results.py` — CA SOS client (REST)
- `data/extraction/city-san-rafael.json` — Example election_sources config
- `docs/internal/election-data-research.md` — Prior research on data sources
- `docs/internal/election-onboarding-spec.md` — Integration roadmap
- `data/school_districts.json` — 452 districts across 56 counties (just built)

## Suggested Approach

1. **Research phase first** — Web search each candidate county's election results portal. Check if they expose APIs, structured data, or just HTML.
2. **Look for platform commonality** — If multiple counties use the same vendor's reporting portal, one client covers many counties.
3. **Prototype one client** — Pick the county with the most accessible data format.
4. **Integrate** — Add to election_sources config, test with `scheduled_election_refresh()`.

## Relevant Memories

- `memory/project_elections_onboarding.md` — Prior research on election sources
- `memory/feedback_civic_data_aggregators.md` — Prefer primary government sources over aggregator APIs
- `memory/feedback_browser_automation.md` — Cloudflare-protected sites need headed Playwright

## Tests to Run

```bash
# Election tests (regression)
pytest packages/civicos-extraction/tests/test_election_detection.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Survey of 5+ CA county registrar systems documented
- [ ] Common platforms/vendors identified
- [ ] One pilot county selected with accessible election data
- [ ] Prototype client (or generalized pattern) for pilot county
- [ ] Election_sources config wired for pilot county
