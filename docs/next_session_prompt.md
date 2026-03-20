# Recommended: Vector-LLM Relevance Pipeline

**Priority:** P0 (vector_llm_relevance_pipeline)
**Area:** multi_scale_participation
**Date:** 2026-03-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session completed `local_impact_relevance` — heuristic scoring (agency mapping, geographic text, CFR parts) for federal rules. It works but only 20/4,115 rules scored "high" because most federal rules don't explicitly mention local geographies. User review identified this gap and we validated that **vector similarity search already solves it**: using San Rafael's municipal_code embeddings as query vectors against federal_rules embeddings returns genuinely relevant results (0.69 similarity for housing, 0.68 for water) that heuristics miss entirely.

## What Needs to Be Done

Build a 3-stage pipeline that replaces heuristic-only scoring with vector retrieval + LLM confirmation:

**Stage 1: Policy Vector Queries** — Define 10-15 policy area descriptions for San Rafael and embed them (or reuse existing municipal_code embeddings as proxies — already tested and works). Policy areas: housing/zoning, water/stormwater, transportation, climate/environment, public safety, education, budget, land use, labor, infrastructure, health.

**Stage 2: Vector Candidate Retrieval** — For each policy vector, run pgvector cosine similarity against the 3,606 embedded federal rules. Pull top 30-50 per policy area, deduplicate. Expected yield: ~200-400 candidates from 4,115 total.

**Stage 3: LLM Confirmation** — Send candidates to gpt-4o-mini in batches of 20-30. Prompt: "Rate this federal rule's relevance to San Rafael, CA (Marin County) on 0-1 scale. One sentence explaining local impact." Store `local_relevance_score` and new `local_relevance_summary` column.

## Key Files

- `packages/civicos/src/civicos/_internal/legal/relevance.py` — Current heuristic scorer. `score_federal_rule()` returns (score, reasons). `build_jurisdiction_config()` has San Rafael policy areas. Extend or replace with vector+LLM pipeline.
- `packages/civicos/src/civicos/storage/postgres_backend.py:6310` — `store_federal_rules()` already computes heuristic score on ingest. Will need to trigger vector+LLM scoring for new rules.
- `packages/civicos/src/civicos/storage/postgres_backend.py:6384` — `get_federal_rules()` already returns `local_relevance_score` and `relevance_reasons`.
- `packages/civicos-extraction/src/civicos_extraction/cli/classify_topics.py` — **Existing batch LLM pattern** to follow. Uses gpt-4o-mini, batches of 25-30, response_format=json_object, temperature=0.1, cost tracking via `log_llm_cost()`.
- `packages/civicos/src/civicos/cost.py` — `log_llm_cost()` for cost tracking. Already supports gpt-4o-mini pricing.
- `scripts/sql/add_federal_rules_relevance.sql` — Existing migration. Add `local_relevance_summary TEXT` column here.

## Validated Vector Similarity Results

Tested in this session — these queries work right now against pgvector:

```sql
-- Using a San Rafael municipal_code embedding about housing/zoning as query vector:
-- Returns HUD housing rules at 0.69 similarity (correct!)

-- Using a municipal_code embedding about water/stormwater:
-- Returns Bureau of Reclamation water rules (0.687), EPA stormwater permits (0.685),
-- FEMA flood hazard determinations (0.660) — all locally relevant, all missed by heuristics
```

The vector_embeddings table schema: `id, jurisdiction_id, corpus_type, content, embedding (768-dim), metadata (JSONB)`.

## Suggested Approach

1. **Add DB column** — `ALTER TABLE federal_rules ADD COLUMN IF NOT EXISTS local_relevance_summary TEXT`
2. **Build candidate retrieval function** — Query pgvector with policy area embeddings. Can either (a) embed new policy descriptions via OpenAI, or (b) reuse existing municipal_code embeddings filtered by topic keywords (cheaper, already proven).
3. **Build LLM scoring function** — Follow `classify_topics.py` pattern. Batch candidates, call gpt-4o-mini, parse JSON response with score + summary.
4. **Run full pipeline** — Retrieve candidates, LLM-score, write back to federal_rules. Log costs.
5. **Wire into ingest** — When new rules are ingested weekly, after they're embedded, run vector similarity + LLM scoring on new rules only.

## Infrastructure Notes

- **Embeddings**: 3,606/4,115 federal rules already embedded (88%). Model: nomic-embed-text-v1.5, 768 dimensions.
- **Cost**: ~$0.05 for full corpus LLM scoring (~300 candidates x ~150 tokens each). Pennies/week ongoing.
- **Existing columns**: `local_relevance_score FLOAT`, `relevance_reasons JSONB` already exist and are populated with heuristic scores. The pipeline will overwrite these with LLM-derived values for candidates, keeping heuristic scores as fallback for non-candidates.
- **Cost tracking**: Use `log_llm_cost(model='gpt-4o-mini', task='vector_llm_relevance', ...)` after each batch.

## Success Criteria

- [ ] Policy vectors defined for San Rafael's 10-15 active policy areas
- [ ] Vector candidate retrieval returns ~200-400 plausible federal rules
- [ ] LLM scoring produces score + one-sentence local impact summary for each candidate
- [ ] `local_relevance_summary` column added and populated
- [ ] Full pipeline cost logged and under $0.10
- [ ] New rules scored automatically on weekly ingest (after embedding)
- [ ] Spot-check: top 10 scored rules are genuinely locally relevant
