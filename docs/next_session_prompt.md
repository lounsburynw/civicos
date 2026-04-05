# Consolidated Onboard Command

**Priority:** P0
**Area:** turnkey_onboarding
**Date:** 2026-04-05

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session optimized the audio pipeline (opus@48kbps mono, parallel downloads, Granicus HLS resolution, audio-only download) and built batch operations for audio download and transcription across jurisdictions. The pipeline now works but requires 3 separate commands: `--batch-audio`, `--batch-transcribe-flag`, and per-corpus flags. The user wants a single `--onboard` command that runs the full pipeline per jurisdiction with cost estimation and approval gates.

A tiered transcription policy was established (see `docs/internal/transcription-policy.md`):
- **Tier 1** (recent 3-6 months): Full AssemblyAI transcription (~$1.60/meeting)
- **Tier 2** (older): Agenda chunks + decisions only ($0)

## Recommended Task

Build a single `--onboard` CLI command in `scripts/modal_ingest.py` that runs the complete ingestion pipeline for one or more jurisdictions:

1. Show cost estimate (reuse `estimate_audio_costs`)
2. Require `--approve-cost`
3. Fetch meetings, issues, municipal code, agenda packets
4. Discover/download audio (Tier 1 window, route YouTube through proxy, Granicus direct)
5. Transcribe (with cost cap per jurisdiction)
6. Extract decisions, agenda items
7. Index vectors
8. Report coverage summary

## Key Files

- `scripts/modal_ingest.py:5290` — `estimate_audio_costs()` — cost estimation function
- `scripts/modal_ingest.py:5447` — `batch_audio_download()` — parallel audio orchestrator
- `scripts/modal_ingest.py:5536` — `batch_transcribe()` — parallel transcription orchestrator
- `scripts/modal_ingest.py:5610` — `extract_transcripts()` — per-jurisdiction with `since_date` + `cost_cap_usd`
- `scripts/modal_ingest.py:7370` — `main()` CLI entrypoint
- `packages/civicos-extraction/src/civicos_extraction/cli/audio.py` — Audio pipeline (opus, Granicus resolver, HLS audio-only)
- `docs/internal/transcription-policy.md` — Tiered policy, cost reference, onboarding budgets

## Current Pipeline State

- **173 audio files** in R2 across 8 jurisdictions
- **Transcription batch launched on Modal** (since Jan 2026, $50/jurisdiction cap) — check `modal app list`
- Granicus audio partially downloaded (hit 1hr timeout):
  - Berkeley: 18/66, Mill Valley: 20/105, San Anselmo: 16/129, Sausalito: 9/46, County Marin: 24/25
- YouTube complete: San Rafael 67, Fairfax 13
- Proxy status: working but bandwidth-limited ($50 spent, `407 TRAFFIC_EXHAUSTED` possible)

## Key Design Decisions

1. **Proxy only for YouTube** — Granicus is free HLS (`audio.py:438`)
2. **Audio-only HLS** — `-vn` strips video, 200 MB vs 1.8 GB per meeting (`audio.py:428`)
3. **Direct ffmpeg re-encode** — Bypass yt-dlp stream-copy, run ffmpeg with `-c:a libopus -b:a 48k -ac 1` (`audio.py:384`)
4. **Cost gate mandatory** — `--approve-cost` required for all batch operations
5. **Transcription defaults** — 6-month rolling window, $50/jurisdiction cap

## Suggested Approach

1. Read `main()` entrypoint and existing batch handlers (`--batch-audio`, `--batch-transcribe-flag`)
2. Create `onboard_jurisdiction()` Modal function that chains: meetings -> issues -> videos -> audio -> transcripts -> decisions -> chunks -> vectors
3. Create `batch_onboard()` orchestrator that spawns per-jurisdiction jobs in parallel
4. Wire `--onboard` flag in `main()` with cost estimate + `--approve-cost`
5. Test: `modal run scripts/modal_ingest.py --onboard --jurisdiction city-sausalito`
6. Test batch: `modal run scripts/modal_ingest.py --onboard --jurisdictions "city-oakland,city-alameda" --approve-cost`

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
modal run scripts/modal_ingest.py --batch-audio --jurisdictions auto --dry-run
```

## Success Criteria

- [ ] `--onboard --jurisdiction city-X` runs full pipeline with cost gate
- [ ] `--onboard --jurisdictions "X,Y,Z"` parallelizes across jurisdictions
- [ ] Transcription respects Tier 1 window and cost cap
- [ ] Works with `--detach` for fire-and-forget
- [ ] Single command replaces current 3-step workflow

## Commits This Session (10)

- `ea28c03` — Opus@48kbps mono, parallel downloads, direct ffmpeg
- `f176411` — Batch audio download parallel across jurisdictions
- `e9a8c0d` — Batch audio timeout fix (4 hours)
- `c7bb616` — Granicus player URL -> HLS stream resolution
- `ff567cc` — Audio-only HLS download (10x smaller)
- `1113ab3` — Proxy only for YouTube, not Granicus
- `e7a3697` — Cost estimation gate for batch audio
- `ce50576` — Tiered transcription policy docs
- `6353cff` — Transcription date window + cost cap enforcement
- `10f4c20` — Batch transcription parallel across jurisdictions
