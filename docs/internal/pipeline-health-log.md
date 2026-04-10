# Pipeline Health Log

Running log of data pipeline issues discovered, root causes, and resolutions. Check this before debugging refresh failures or data gaps.

## 2026-04-09: Full Data Audit (Marin + Beyond)

### Platform Migrations Undetected

| Jurisdiction | Old Platform | New Platform | How Long Stale | Detection |
|---|---|---|---|---|
| city-san-anselmo | Legistar (dead Dec 2023) | Granicus | ~2.5 years | Manual audit |
| school-sausalito-marin-city | BoardDocs | Simbli (S=36030450) | ~7 months | Manual audit |
| school-larkspur-corte-madera | BoardDocs | Simbli (S=36031975) | ~6 months | Manual audit |
| school-ross-valley | BoardDocs | Diligent Community | ~5 months | Manual audit |
| school-marin-county-oe | BoardDocs | Diligent Community | ~2 months | Manual audit |

**Root cause:** Refresh cron marks "completed" even when source returns 0 new items. No alert for consecutive empty fetches.

**Resolution:** Configs updated. Simbli districts ingested. Diligent Community districts parked (no client).

**Systemic fix needed:** Health check that flags sources returning 0 items for N consecutive runs.

### Transcript Coverage Gaps

**Finding:** Transcription is not part of the cron refresh cycle. A one-time batch on 2026-04-06 transcribed ~30 meetings per jurisdiction, then stopped. New meetings with video accumulate without transcription.

| Jurisdiction | Meetings w/ Video | Transcribed | Gap |
|---|---|---|---|
| city-mill-valley | 110 | 30 | 80 |
| city-san-anselmo | 139 | 30 | 109 |
| city-sausalito | 46 | 30 | 16 |
| city-tiburon | 7 | 0 | 7 |
| county-marin | 28 | 23 | 5 |

**Resolution:** Batch transcription run for 2026 meetings. 11 new transcripts ($48.53). Tiburon now fully covered.

**Systemic fix needed:** Wire audio download + transcription into cron cadence for jurisdictions with video URLs.

### Decision Extraction Gaps

**Finding:** Sausalito Planning Commission had 21 meetings with 0 decisions. Only City Council meetings were extracted.

**Root cause:** Decision extraction was only run for meetings that already had decisions — Planning Commission was never included in a batch.

**Resolution:** Extracted 8 new decisions from Planning Commission meetings.

**Systemic fix needed:** Decision extraction should cover all meeting body types, not just the primary governing body.

### SSL Cert Failures on Modal

**Finding:** Granicus S3 PDF downloads fail from Modal with SSL hostname mismatch (`granicus_production_attachments.s3.amazonaws.com`). Works fine locally.

**Root cause:** Modal's debian-slim image had outdated CA certificates. Additionally, `retrospective_analyzer.py` lacked the SSL retry pattern that `agenda_integration.py` already had for the same URLs.

**Resolution:**
- Added `ca-certificates` + `certifi` to Modal civic_image
- Added SSL retry with `verify=False` for Granicus/S3 URLs in retrospective_analyzer.py (3 download methods), matching existing pattern in agenda_integration.py

**Lesson:** When adding SSL/proxy handling to one download path, check all download paths in the codebase.

### Simbli MeetingStoreResult Bug

**Finding:** school-novato and school-tamalpais meeting refreshes failing with `can't adapt type 'MeetingStoreResult'`.

**Root cause:** `extract_simbli_meetings_to_storage()` returned a `MeetingStoreResult` dataclass directly to `update_refresh_metadata()`, which tried to serialize it into SQL. Missing `int()` conversion.

**Resolution:** Added `int(result)` in simbli.py.

**Lesson:** `store_meetings()` returns `MeetingStoreResult` (not int). All callers must convert via `int()` before passing to SQL or refresh metadata.

### Silent Refresh Failures

**Finding:** Two school districts had `status=failed` in refresh_metadata for weeks. The data-freshness alert reports failures but doesn't escalate them distinctly from staleness.

**Systemic fix needed:** `status=failed` entries should trigger high-priority alerts, separate from staleness warnings.

### YouTube Proxy Exhausted

**Finding:** Audio download for YouTube-sourced jurisdictions (city-san-rafael, city-san-anselmo) fails with `407 TRAFFIC_EXHAUSTED`. Granicus-sourced audio downloads work fine without proxy.

**Status:** Known issue since 2026-04-04 (see memory: project_youtube_proxy.md). Blocks new transcription for YouTube-sourced meetings.

### Coverage Blind Spots

**Finding:** No tooling surfaces cross-corpus coverage gaps. Had to manually query for "meetings with video but no transcript" and "meetings with agenda but no decisions."

**Systemic fix needed:** Extend `/data-status` or data-freshness workflow to report:
- Meetings with video_url but no transcript
- Meetings with agenda_url but no decisions
- Ratio of decisions/meetings by body type
