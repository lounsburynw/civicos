# Recommended: CivicClerk Pipeline Wiring

**Priority:** P0 (civicclerk_pipeline_wiring)
**Area:** turnkey_onboarding
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Turnkey onboarding is now the top priority — a new `turnkey_onboarding` category was added to launch.json with 10 items. We just completed `legistar_client` (wired Legistar into the pipeline, tested on Sacramento/Oakland/Denver). The pattern is proven and repeatable.

**CivicClerk is next because the client already exists** — it just needs the same elif branch + registry addition that took ~15 minutes for Legistar. Cities blocked: El Cerrito, Hayward, San Pablo.

## What Was Done This Session

1. Wired Legistar into `fetch_meetings()` — 76 Sacramento meetings stored in Postgres
2. Fixed datetime parsing bug (Legistar returns "1:00 PM" not ISO)
3. Verified on Oakland (17 meetings) and Denver (50 meetings)
4. Created `turnkey_onboarding` category in launch.json (10 items)
5. Split issue tracking into multi-provider dispatch (FixItMarin prompted this)

## Key Files

| File | Purpose |
|------|---------|
| `scripts/modal_ingest.py:2886` | `fetch_meetings()` source dispatch — add `elif source_type == "civicclerk":` after legistar branch |
| `packages/civicos-extraction/src/civicos_extraction/clients/civicclerk.py` | Existing CivicClerk client — check constructor, `get_meetings()`, `normalize_event()` |
| `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py:115` | `SUPPORTED_MEETING_SOURCES` — add `"civicclerk"` |
| `packages/civicos-extraction/src/civicos_extraction/clients/legistar.py:363` | Reference: the Legistar `normalize_event()` fix for datetime parsing — check if CivicClerk has the same issue |

## Suggested Approach

1. **Read CivicClerkClient** — check constructor params, `get_meetings()` return type, datetime handling
2. **Add elif branch** in `fetch_meetings()` at `modal_ingest.py:2896` (after legistar branch)
3. **Add "civicclerk" to SUPPORTED_MEETING_SOURCES** in `__init__.py:115`
4. **Test against a real CivicClerk city** — try El Cerrito or Hayward. Verify meetings fetch with correct datetimes
5. **Store in Postgres** — verify meetings stored, San Rafael unaffected
6. **Add datetime parsing tests** if CivicClerk has format quirks (like Legistar's 12-hour format)
7. **If time permits:** Start `escribe_pipeline_wiring` (P1) — same pattern, ~15 min

## Pattern Reference (from Legistar wiring)

```python
# modal_ingest.py — add after the legistar elif
elif source_type == "civicclerk":
    from civicos_extraction.clients.civicclerk import CivicClerkClient
    client = CivicClerkClient(
        # check constructor for required params
    )
    meetings = client.get_meetings(days_ahead=days_ahead, days_past=days_past)
```

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_integration_extraction_failures.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] CivicClerk added to SUPPORTED_MEETING_SOURCES
- [ ] fetch_meetings() handles source_type="civicclerk"
- [ ] Meetings fetched from at least one CivicClerk city (El Cerrito, Hayward, or San Pablo)
- [ ] Correct datetimes (no datetime.now() fallback)
- [ ] San Rafael data unaffected
- [ ] Unit tests for any datetime parsing fixes

## Turnkey Onboarding Roadmap (for context)

After CivicClerk, the remaining items in priority order:
- P1: `escribe_pipeline_wiring` — same wiring pattern, Canadian cities
- P1: `html_agenda_extraction` — fix chunks=0 for HTML-only agendas
- P1: `issue_provider_dispatch` — generalize fetch_issues() like fetch_meetings()
- P2: `onboard_quality_gates`, `issue_provider_detection`, `onboard_end_to_end_test`
- P3: `onboard_transcript_auto`, `onboard_deploy_integration`, `onboard_batch_mode`
