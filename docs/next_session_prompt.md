# Recommended: simbli_incapsula_bypass

**Priority:** P0
**Area:** election_integration
**Date:** 2026-04-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session fixed and verified `low_velocity_cron_timeout` — the Modal weekly cron now fans out per-jurisdiction work via `.spawn()` (run 24637784320 completed in 41 min vs 4h+ timeouts; "Spawned 30 per-jurisdiction low-velocity refreshes in parallel" logged; 94/95 stages passed). That unblocked the cron, but school data coverage remains the biggest gap: 7 school jurisdictions are broken because Simbli (eboardsolutions.com) added Imperva/Incapsula WAF and the extraction layer never populates `agenda_url` on Simbli meeting rows.

Promoted `simbli_incapsula_bypass` from P1 → P0 on 2026-04-19 as the next biggest launch unblock.

## Recommended Task

Fix Simbli extraction so the 3 active-but-empty schools get chunks + decisions, and decide a path for the 4 WAF-blocked schools. Root failure mode (confirmed during QC walkthrough): Simbli listings extraction returns meeting rows but `agenda_url` stays None in 100% of cases (except school-san-rafael at 62% — reason unknown). Without `agenda_url` the chunks pipeline has nothing to fetch, so agenda items + decisions are stuck at 0.

**Precise DB state to validate against:**
- Simbli partial (meetings but 0 chunks/decisions): school-novato 42 mtgs, school-tamalpais 38 mtgs, school-san-rafael 72 mtgs / 788 chunks (via legacy BoardDocs fallback)
- Simbli empty (WAF blocks listing requests): school-kentfield, school-mill-valley-sd, school-miller-creek, school-reed-union — all 0/0/0
- Simbli-working via BoardDocs bridge: school-sausalito-marin-city (boarddocs_app_path=ca/smcsd), school-larkspur-corte-madera (boarddocs_app_path=ca/lcmsd) — keep these paths alive

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/simbli.py` — current Simbli client (the listing path that populates meetings without agenda_url)
- `data/jurisdictions/school-*.yaml` — each affected school's config (look for `source: simbli` and any `boarddocs_app_path` fallback)
- `memory/feedback_browser_automation.md` — project convention: Cloudflare/WAF-protected sites need **headed** Playwright, not headless
- Meeting → agenda_url flow: start at the storage column (`meetings.agenda_url`), grep for writes, then trace up to the extraction client

## Suggested Approach

1. Read the current Simbli client to understand what listing-level data comes back and why `agenda_url` stays None.
2. Test in a browser: open a Simbli meeting detail page (e.g., one of school-novato's) and identify where the agenda PDF URL is rendered. Is it in the listing response but dropped, or is it only on the detail page?
3. Pick a strategy (ranked by effort):
   - (a) If agenda_url is in the listing but dropped: client-side parsing fix, small diff.
   - (b) If it requires fetching per-meeting detail pages: add a detail-page fetch step (may need headed Playwright per the feedback memory).
   - (c) Probe for undocumented Simbli JSON/RSS endpoints (cheaper if they exist).
4. For the 4 WAF-blocked schools: confirm whether even the listing request is blocked. If yes, headed Playwright is probably the only path for (a) and (b) above.
5. Write integration test(s) mocking Simbli responses with real agenda_url payloads, verify chunks pipeline picks them up end-to-end.
6. Re-run targeted extraction for one school first (school-novato is a good canary — 42 meetings, clean state). Validate chunks land. Then roll to the other 6.

## Tests to Run

```bash
# If a Simbli test file exists
civicos-env/bin/python3 -m pytest packages/civicos-extraction/tests/ -k simbli -v --override-ini="addopts="

# Smoke the extraction pipeline end-to-end against a test jurisdiction
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_integration_cron_wiring.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] school-novato gets chunks + decisions populated after targeted refresh
- [ ] Same for school-tamalpais and school-san-rafael (SR is partial today; full coverage expected)
- [ ] Decision made on the 4 WAF-blocked schools (kentfield/mill-valley-sd/miller-creek/reed-union): either resolved via headed Playwright, or explicitly deferred with a launch.json note on why
- [ ] Integration test covers the new agenda_url population path
- [ ] school-sausalito-marin-city and school-larkspur-corte-madera BoardDocs fallback still functions (regression check)

## Pipeline Health Context

- Last weekly cron (run 24637784320, 2026-04-19 20:37Z): 94/95 stages passed. Fan-out confirmed working. One lingering per-stage failure — investigate via `gh run view 24637784320 --log | grep -E "FAIL|error"` before Monday's scheduled cron.
- `git log origin/main..HEAD` is clean as of session end — prior session left 17 unpushed commits that nearly caused a false-positive verification; don't make that mistake. See `memory/project_cron_runs_against_origin.md`.

## Known Pending Items (do not re-discover)

- `multi_source_advisory_body_coverage` (P1) — cities split meetings across platforms, advisory bodies missing
- `direct_city_submission` (P1) — clerk-submission endpoint for authenticated meeting data bypass
- 15 QC follow-ups in `jurisdiction_qc_walkthrough.notes` (items #1–#15, especially #13 LLM-based agenda parser for the 36,611 `unparsed` chunks)
- `youtube_proxy` expired — Modal secret `civic-youtube-proxy` has 407 NO_USER; blocks Fairfax transcription

## Open PRs

None.
