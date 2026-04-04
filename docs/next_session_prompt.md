# Investigate YouTube 403s + Complete Fairfax Transcription

**Priority:** User-directed (launch.json P0 is `token_purchase_ui`, but user explicitly requested this)
**Area:** data_pipeline / transcription
**Date:** 2026-04-04

> Previous session onboarded 4 jurisdictions, built BoardDocs content extraction, and got 5/13 Fairfax transcripts. 8 videos failed with YouTube 403 errors even through the residential proxy. User wants to investigate why.

## Context

This session was a major data expansion — from 1 jurisdiction to 17, from 645 to 1,707 decisions. The transcription pipeline works (5 Fairfax videos transcribed, $12.88 AssemblyAI) but YouTube is blocking 8 of 13 downloads even through DataImpulse residential proxy. The 403s are sporadic — some videos download fine, others fail mid-stream (one got to 37.9% before cutting off).

## The Problem

```
ERROR: unable to download video data: HTTP Error 403: Forbidden
```

8 of 13 Fairfax YouTube videos failed. Pattern:
- Videos `qFBzyO0gLQM`, `htqDXoDU05o`, `kIK6hljdcUI`, `UGbygh9Nwqg`, `3wJhocXJNCY` — immediate 403
- Video `iJppJPzrAbc` — read timeout through proxy
- Video `zvOETnDPGKM` — read timeout through proxy
- Videos `yWrNkjbnG84`, `GBeEm0LYE5E`, `98dqXLh3M2U`, `TYOoRdD2o_o`, `IzsKaNksSyU` — SUCCESS

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/cli/audio.py:255` — `download_audio()`, now supports generic `video_url` parameter
- `scripts/modal_ingest.py:5200-5310` — `extract_transcripts()` Modal function, uses `civic-youtube-proxy` secret
- `data/city_fairfax_videos.json` — 13 discovered video IDs

## Investigation Areas

1. **yt-dlp version**: Modal image may have outdated yt-dlp. YouTube frequently patches extraction methods. Check `yt-dlp --version` in the Modal container vs latest release.

2. **Cookie support**: The pipeline has cookie support (`YOUTUBE_COOKIES_B64` secret) but wasn't used this session. Fresh browser cookies + proxy together may be needed.

3. **Proxy rotation**: DataImpulse supports rotating IPs. The current URL (`gw.dataimpulse.com:823`) may need country/session parameters. Check DataImpulse docs for `session` or `country` URL params.

4. **Rate limiting pattern**: The 5 successful downloads happened sequentially — YouTube may be rate-limiting after N downloads. Adding delays between downloads might help.

5. **Age-restricted/private videos**: Some failing video IDs may have restrictions. Test manually: `curl -sI "https://www.youtube.com/watch?v=qFBzyO0gLQM" | head -5`

## Suggested Approach

1. Check yt-dlp version in Modal vs latest: `pip install --upgrade yt-dlp` in the image
2. Test failed video IDs individually (are they accessible in a browser?)
3. Try with cookies: export fresh YouTube cookies, set `YOUTUBE_COOKIES_B64` Modal secret
4. Try with delay: add `--sleep-interval 5` or similar to yt-dlp opts
5. Re-run: `modal run scripts/modal_ingest.py --transcripts --jurisdiction city-fairfax`

## Also Available: Sausalito Granicus Audio

Generic video URL support was shipped this session. Sausalito has Granicus video URLs stored in the meetings table. `audio.py` now falls back to meetings table `video_url` when no videos table entry exists. yt-dlp handles Granicus URLs (verified locally). Untested in production.

## Platform State After Last Session

- **17 jurisdictions** in Postgres
- **1,492 meetings**, **54,760 chunks**, **1,707 decisions**, **51 transcripts**
- Proxy refreshed: `civic-youtube-proxy` Modal secret (DataImpulse `gw.dataimpulse.com:823`, updated 2026-04-04)
- 4 commits: `ec12190`, `ad2d3fc`, `8bc13d0`, `ef7e4d1`

## Commits This Session

- `ec12190` — Production onboard Sausalito, Fairfax, 2 school districts
- `ad2d3fc` — BoardDocs structured content extraction (chunks + agenda items from API)
- `8bc13d0` — Generic video URL support + BoardDocs decision extraction
- `ef7e4d1` — Session progress update

## Success Criteria

- [ ] Root cause identified for YouTube 403s
- [ ] Remaining 8 Fairfax videos downloaded and transcribed
- [ ] Total Fairfax transcripts: 13 (up from 5)
