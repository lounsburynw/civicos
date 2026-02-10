# Handoff: Fix Transcript Embedding Metadata + Commit Decision Classification

**Priority:** P0
**Date:** 2026-02-10

## What Was Done

### 1. Decision Classification — `item_type` + Correct Outcomes (COMPLETE, UNSTAGED)
Added `item_type` discriminator (action/consent/presentation/hearing/discussion) and fixed outcomes. Backfilled 44 existing decisions via LLM (gpt-4o-mini, $0.0016).

**Files modified:**
- `packages/civicos-extraction/.../retrospective_analyzer.py` — `item_type`, `extracted_outcome` on dataclass; `passed` default→`None`; 3 LLM prompts updated; 3 construction sites wired
- `packages/civicos-extraction/.../cli/decisions.py` — 7-outcome mapping replacing binary `approved/pending`; `item_type` in storage format
- `packages/civicos/.../storage/postgres_backend.py` — `item_type` column migration + index; in `store_decisions()` INSERT; `item_type` filter on `get_decisions()`
- `packages/civicos/.../storage/pgvector_backend.py` — `[item_type]` prefix in `_decision_to_text()`
- `scripts/backfill_decision_item_types.py` — NEW: LLM-based backfill (already applied: 23 actions, 15 presentations, 5 discussions, 1 hearing)

**Smoke tests: 42/42 pass.**

### 2. Fix "?" Speaker Labels (CODE DONE, ROOT CAUSE UNRESOLVED)
- `packages/civicos-services/.../context/assembler.py` — Added `_resolve_speaker()` fallback: speaker_name → role label ("Council Member"/"Staff") → empty string
- `apps/civicos-openwebui-fork/.../DecisionDetail.svelte` — `{#if}` guards hide empty speaker spans

## Unresolved: Empty Transcript Embedding Metadata

**ALL 6,521 transcript embeddings have `metadata: '{}'`** — no video_id, speaker, start_ms, speaker_role. This causes:
- No video "Watch clip" links
- "?" speaker labels (now hidden by our fix, but data is still missing)

**The code is correct.** `expand_transcripts_to_chunks()` produces full metadata (verified locally). `pgvector_backend.py` metadata construction preserves it. **The Modal deployment likely ran stale code** when indexing Feb 9-10.

Other corpus types with metadata: budget_items, elections, municipal_code, state_programs (all populated). Corpus types without: transcripts, chunks, decisions, meetings, issues, agenda_items (all empty).

### What to do:
1. **Check the ~$50 reindex cost** user mentioned — query `etl_costs` (cols: pipeline, run_date, items_processed, cost_usd, notes) and `operating_costs` (cols: timestamp, service, category, amount_usd, metadata)
2. **Redeploy Modal**: `modal deploy scripts/modal_vectors.py`
3. **Reindex transcripts only** — 6,521 embeddings, should be cheap (most cost is GPU time for embedding generation). This will populate metadata and restore video links + speaker labels
4. **Verify** after reindex: `SELECT metadata->>'video_id', metadata->>'speaker_role' FROM vector_embeddings WHERE corpus_type='transcripts' LIMIT 5`

### Commit the changes
All work is unstaged. Run `/commit`.

## Key Files
- `packages/civicos/src/civicos/_internal/meetings/transcript.py:1736` — `expand_transcripts_to_chunks()`
- `packages/civicos/src/civicos/storage/pgvector_backend.py:1046` — metadata construction
- `scripts/modal_vectors.py` — Modal vector indexing app
- `packages/civicos-services/.../context/assembler.py:391` — `_resolve_speaker()`
