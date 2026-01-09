# Recommended: simbli_pdf_download

**Priority:** P0
**Area:** data_readiness > school_district
**Date:** 2026-01-08

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

SimbliClient now extracts meetings with MIDs from the SRCS board portal. The MID discovery feature was implemented this session - MIDs are extracted from onclick attributes (ViewMeeting pattern) without needing to click. Integration test verified 4/4 meetings have MIDs discovered.

Now we need to use these MIDs to implement the actual PDF download workflow.

## Recommended Task

Implement the 2-step PDF download workflow for Simbli agendas using the captured MIDs.

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/simbli.py` - SimbliClient implementation
- `packages/civic-extraction/tests/test_clients.py` - Simbli tests

## PDF Download Workflow (Tested in Previous Session)

1. Navigate to `PrintAgenda.aspx?S=36030430&MID={mid}`
2. Click Print button
3. POST to `/api/PrintAgenda/PrintAgenda` returns JSON: `{"FileUrl": "..."}`
4. GET FileUrl downloads the PDF (843KB test PDF worked)

Example MIDs discovered this session:
- 45989 (2025-12-16 meeting)
- 45982 (2025-11-18 meeting)
- 45465 (2025-10-28 meeting)
- 45464 (2025-10-14 meeting)

## Suggested Approach

1. **Add `download_agenda_pdf(meeting: SimbliMeeting) -> Optional[bytes]` method**
   - Check that `meeting.simbli_mid` is set
   - Navigate to PrintAgenda.aspx with MID
   - Click Print button to trigger PDF generation
   - POST to API endpoint and parse FileUrl from JSON response
   - GET FileUrl to download PDF bytes
   - Return PDF bytes or None if failed

2. **Handle the JavaScript-driven workflow**
   - PrintAgenda page has a Print button that triggers the API call
   - Need to either click the button or directly POST to the API
   - API returns: `{"FileUrl": "/SB_Meetings/..."}`

3. **Add tests**
   - Unit test for PDF download method (mock browser)
   - Integration test that downloads a real PDF

## Tests to Run

```bash
# Unit tests (don't hit real site)
pytest packages/civic-extraction/tests/test_clients.py -k "Simbli and not Integration" -v

# Integration test (hits real site)
pytest packages/civic-extraction/tests/test_clients.py -k "SimbliClientIntegration" -v
```

## Success Criteria

- [ ] `download_agenda_pdf(meeting)` method implemented
- [ ] Method uses simbli_mid to construct PrintAgenda URL
- [ ] PDF bytes returned successfully
- [ ] Integration test downloads real PDF
- [ ] Update pilot.json status to "ready"

## Next Item After This

Continue with school_district data pipeline - either processing downloaded PDFs or moving to other data readiness items.
