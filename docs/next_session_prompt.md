# Recommended: Cross-County Query Prototype (Phase B)

**Priority:** P0
**Area:** federation_testbed > cross_county_query_prototype
**Status in launch.json:** in_progress
**Date:** 2026-04-06
**Spec:** `docs/internal/cross-county-relevance-spec.md` (and `cross-jurisdiction-query-spec.md` for context)

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

Last session verified `cross_marin_query_prototype` end-to-end on the expanded Marin dataset (10 cities + 9 school districts) and marked it `done`. All Phase A acceptance criteria pass: jurisdiction resolution, tier boosting, sibling boundary enforcement, parallel fan-out, real-data semantic ranking. Phase B (cross-county) is the natural follow-up — Berkeley is already onboarded (273 decisions, 79 meetings), the v2 layer already has `also_include` for explicit cross-county opt-in (commit `d2d20f4`), and `get_jurisdiction_tier()` already returns `cross_county` correctly.

The remaining work is **end-to-end validation against real cross-county data plus answering the spec's open question: "when should cross-county results appear?"**

## Verified Data State (2026-04-06)

| Jurisdiction | Meetings | Decisions | Notes |
|---|---|---|---|
| city-san-rafael | 106 | 111 | base for tests |
| city-berkeley | 79 | **273** | ✅ ingested — confirmed against Postgres |
| city-san-francisco | 40 | 188 | ✅ ingested last session |
| county-marin | 131 | 105 | ✅ ingested |
| **county-alameda** | **0** | **0** | ❌ **NOT ingested** despite `onboard_county_alameda` marked done |

⚠️ **`county-alameda` is the data gap.** Berkeley's parent chain (`city-berkeley → county-alameda → state-california → country-united-states`) has nothing at the county level. This means parent-chain queries from Berkeley return empty for county results — Phase B can either work around this or fix it as part of the work. Verify the launch.json status of `onboard_county_alameda` is wrong before assuming the test design.

## Recommended Task

Validate cross-county queries against real data and answer the spec's open questions:

1. **`also_include` end-to-end test**: SR + Berkeley with `also_include=["city-berkeley"]` for "housing" — do Berkeley results appear with `cross_county` tier weight (0.5)? Are they actually useful or noise?
2. **Boundary regression test**: SR with `include_siblings=True` (only) must NOT pull Berkeley. Add a real-data integration test if missing.
3. **Shared state-parent test**: SR + Berkeley both have `state-california` as a parent. With `include_parents=True`, state-level legislation should appear once for both — verify dedup and that the relevance weight is `parent_state` (0.7), not double-counted.
4. **Spec open question**: when *should* cross-county results appear? Document the answer in `docs/internal/cross-county-relevance-spec.md` based on tested results. Likely: "only on explicit `also_include`, never via implicit fan-out."

## Key Files

- `packages/civicos-services/src/civicos_services/query/jurisdictions.py:141-177` — `get_jurisdiction_tier()` (Berkeley→SR returns `cross_county`)
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py:54-127` — `resolve_jurisdictions()` — `also_include` is handled in `verbs.py`, not here
- `packages/civicos-services/src/civicos_services/query/verbs.py:391-401` — where `also_include` is appended to `target_jids` after `resolve_jurisdictions`
- `packages/civicos-services/src/civicos_services/query/models.py:109-140` — `SearchRequest.also_include`, `include_parents`, `include_siblings`
- `packages/civicos-services/tests/test_query_v2.py:1822-1991` — existing cross-jurisdiction tests (mocked)
- `packages/civicos-services/tests/test_integration_query_v2.py` — existing real-Postgres tests (23 pass, 159s) — add cross-county cases here
- `docs/internal/cross-county-relevance-spec.md` — the spec to update with test findings

## Suggested Approach

1. Start with a 1-shot live verification script (analogous to last session's): SR base, run three queries — `include_siblings=True`, `also_include=["city-berkeley"]`, `include_parents=True` — and dump top results with jurisdiction + relevance.
2. Confirm Berkeley results carry `cross_county` tier (0.5x weight) and that boundary-crossing requires explicit `also_include`.
3. Add 2-3 integration test cases to `test_integration_query_v2.py` covering the boundary regression and the `also_include` path against real Postgres.
4. Decide whether the empty-`county-alameda` situation is in scope: either (a) carve it out as a known data gap, file a separate item to re-run `/onboard county-alameda`, and proceed with city-level testing only, or (b) actually onboard county-alameda first (likely 1-2hr extraction job) so the parent-chain test is meaningful.
5. Document spec answers and mark `cross_county_query_prototype` `done`.

## Tests to Run

```bash
# Unit tests for cross-jurisdiction (fast)
source civicos-env/bin/activate && pytest packages/civicos-services/tests/test_query_v2.py -q \
  --override-ini="addopts=" -k "tier or sibling or parent or jurisdiction or cross or also_include"

# Integration tests against real Postgres (slower; ~3 min)
source civicos-env/bin/activate && pytest packages/civicos-services/tests/test_integration_query_v2.py -q \
  --override-ini="addopts="
```

## Success Criteria

- [ ] Live cross-county query (SR + `also_include=["city-berkeley"]`, "housing") returns Berkeley results with relevance ≤ 0.5x raw cosine (`cross_county` weight applied)
- [ ] SR + `include_siblings=True` does NOT include Berkeley (regression test added to `test_integration_query_v2.py`)
- [ ] State-parent dedup verified — `state-california` results appear once when querying via either SR or Berkeley with `include_parents=True`
- [ ] Spec open question on "when should cross-county appear" answered in `docs/internal/cross-county-relevance-spec.md`
- [ ] `county-alameda` empty-state either (a) explicitly out of scope with a follow-up item filed, or (b) re-ingested
- [ ] `cross_county_query_prototype` marked `done` in `launch.json`
- [ ] New P0 promoted before `/nextsesh`

## Caveats / Things to Verify

- **county-alameda data gap is the most important caveat** — last session's notes (and the prior next-session prompt) implied Berkeley's parent county was loaded; it isn't. `onboard_county_alameda` in launch.json is marked `done` but Postgres says zero rows. Worth investigating *why* — was it a stub onboard with no extraction run, or did the extraction fail silently?
- The single-jurisdiction code path leaves `CivicResult.jurisdiction = None` (asymmetry with the cross-jid path which tags every result). Minor; not a bug for Phase B but watch for it in test assertions.
- Last session's verification used `execute_search(req, civic, base_jid)` — note signature is `(request, civic, jurisdiction)`, not `(request, storage, vectors, jurisdiction)`.

## Open PRs

None as of session end.
