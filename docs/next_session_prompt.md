# Recommended: Universal Adapter Design Session

**Priority:** P0 (`universal_adapter_design`)
**Area:** federation_testbed
**Date:** 2026-03-13

> Design session — research + ADR, not implementation. The goal is a design document, not code.

## Context

All 6 known meeting platforms are now in the auto-discovery chain (Granicus, Legistar, CivicClerk, eScribe, Simbli, ProudCity). But major cities like Portland and NYC use custom platforms that require bespoke client development. This session designs an LLM-powered universal adapter to handle the long tail.

Additionally, the existing Simbli client (`clients/simbli.py`) uses hardcoded regex and CSS selectors built for one district (SRCS). It's a concrete example of brittle extraction that the universal adapter should replace.

## The Problem

- Portland OR: custom system at `portland.gov/council/agenda/all`
- NYC: custom system
- Any city with budget to build their own site
- Simbli client: works for SRCS but regex-based parsing won't generalize across districts

## Existing Pattern to Extend

We already use LLMs for extraction config generation:
- `clients/granicus.py` — LLM generates column maps from raw HTML (`generate_column_map()`)
- `clients/granicus.py` — LLM generates body names from view data (`generate_body_names()`)
- Both produce structured config that the client then uses deterministically

This pattern (LLM generates config, client uses config) is the foundation to extend.

## Key Questions to Answer

1. Can we define a **declarative scraping config** (CSS selectors, URL patterns, pagination rules, date formats) that a generic client interprets?
2. How much can the LLM **reliably infer** from a cold URL vs. needing human hints?
3. What's the **failure mode** — does it degrade gracefully or silently return garbage?
4. Is declarative config worth the complexity vs. just writing a bespoke client per major city?
5. Should the LLM run at **onboard time** (one-shot config generation) or at **extraction time** (per-page parsing)?

## Suggested Approach

1. Read `clients/granicus.py` LLM integration (~lines 200-300) for the existing pattern
2. Read `clients/simbli.py` to understand what "brittle extraction" looks like
3. Research: how do tools like Firecrawl, Jina Reader, or browser-use handle arbitrary page parsing?
4. Design the adapter architecture (ADR format)
5. Prototype the config schema (what fields? what's required vs. optional?)
6. Write the ADR to `docs/public/decisions/`

## Key Files

- `clients/granicus.py:200-300` — Existing LLM config generation pattern
- `clients/simbli.py` — Brittle regex example to improve
- `clients/base.py:413` — BaseExtractor ABC (adapter must conform)
- `docs/public/decisions/` — Where ADRs live

## Success Criteria

- [ ] ADR written documenting the universal adapter design
- [ ] Config schema defined (fields, types, examples)
- [ ] Decision on onboard-time vs. extraction-time LLM usage
- [ ] Simbli identified as first migration candidate
- [ ] Portland OR used as test case for cold-URL inference
- [ ] Failure modes documented with mitigation strategies
