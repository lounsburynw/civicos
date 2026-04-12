# Recommended: Implement Captions Transcription Mode (`implement_captions_transcription_mode`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-11

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session completed `regional_server_deployment` (step 5/5 of the scope work sequence) in commits `561eeec0`, `20b96220`, `85ecb6ac`. Also made deployment config registry-driven and fixed the `/critic` skill to auto-discover critics. The scope sequence is fully shipped. This P0 addresses the largest remaining cost bottleneck: ~227 meetings lack transcripts because AssemblyAI costs ~$570-820 to cover them. YouTube auto-captions are free and already partially wired in `onboard.py` but the actual extraction is unimplemented.

## Recommended Task

Implement the `captions` transcription mode so `extract_transcripts()` can pull free YouTube auto-captions instead of only using AssemblyAI. The onboarding CLI already supports `--captions-only` and sets `transcript_mode=TRANSCRIPT_CAPTIONS`, but `extract_transcripts()` in `modal_ingest.py` always calls AssemblyAI regardless.

## Key Files

- `scripts/modal_ingest.py:6450-6495` — `extract_transcripts()` function (AssemblyAI only, needs captions branch)
- `scripts/onboard.py:57` — `TRANSCRIPT_CAPTIONS = "captions"` constant (already defined)
- `scripts/onboard.py:872` — `--captions-only` CLI flag (already wired)
- `scripts/onboard.py:1353-1373` — transcript_mode selection logic (already handles captions path)
- `packages/civicos-extraction/src/civicos_extraction/cli/transcribe.py:661` — `transcribe_audio_file()` (AssemblyAI wrapper)
- `packages/civicos-extraction/src/civicos_extraction/cli/youtube.py` — YouTube utilities (video ID extraction)
- `docs/internal/transcription-policy.md` — Tiered transcription model, cost reference

## Suggested Approach

1. **Add caption extraction function** — either via `youtube-transcript-api` (Python library, already on PyPI) or `yt-dlp --write-auto-subs` (already in civicos-env). `youtube-transcript-api` is simpler: `YouTubeTranscriptApi.get_transcript(video_id)` returns `[{"text": "...", "start": 0.5, "duration": 2.0}, ...]`.

2. **Convert captions to transcript schema** — the transcripts table expects: `transcript_text` (full text), `speakers` (JSON array), `processing_service` (text). For captions: join all caption segments into `transcript_text`, set `speakers` to `[]` (no diarization), set `processing_service` to `'youtube_captions'`.

3. **Add `transcript_mode` parameter to `extract_transcripts()`** — default `"assemblyai"` for backwards compat. When `"captions"`, skip audio download + R2 upload + AssemblyAI, go straight to caption fetch + store.

4. **Wire through onboard.py** — `--captions-only` flag already sets `transcript_mode=TRANSCRIPT_CAPTIONS`. Pass this through to the `extract_transcripts` call in the onboarding pipeline.

5. **Tag provenance** — existing `processing_service` field in the transcripts table should be `'youtube_captions'` so downstream queries can distinguish quality tiers.

## Tests to Run

```bash
# Smoke tests
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Transcription-related (check for existing tests first)
civicos-env/bin/python3 -m pytest packages/civicos-extraction/tests/ -k "transcript" -v --override-ini="addopts="
```

## Success Criteria

- [ ] `extract_transcripts(jurisdiction="city-san-rafael", transcript_mode="captions")` fetches YouTube auto-captions for meetings with video URLs
- [ ] Captions stored to Postgres with `processing_service='youtube_captions'` and empty `speakers` array
- [ ] `--captions-only` flag on `onboard.py` triggers captions mode end-to-end
- [ ] Existing AssemblyAI path unchanged (default behavior)
- [ ] At least one test validates caption extraction and schema conversion
- [ ] A new P0 assigned before session end

## Pre-existing test failures (NOT regressions)

- `test_coordination_tools.py`: 5 failures (broadcast_voice schema drift, registry count drift)
- `test_initiative_tools.py::test_connection_error_handled`: relay is reachable, premise broken

These are separate cleanup items — 6 pre-existing failures total, stable across sessions.

## Open PRs

None.

## Not in scope

- Speaker diarization from captions (not available in YouTube auto-captions)
- Replacing AssemblyAI for flagship cities — captions are for breadth, not depth
- Vector indexing of new transcripts (separate step, `auto_index=True` handles it)
- Regional server deployment to Modal + Cloudflare (code shipped, needs `modal deploy` + CNAME)
