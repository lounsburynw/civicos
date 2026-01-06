# Recommended: automated_decision_extraction

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-05

> This is recommended context from Session 474. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 474 fixed `extraction_services_layer_violation` - moved AgendaIntegrator, RetrospectiveAnalyzer, and API clients to civic-extraction using dependency injection. Architecture critic now passes.

The decision extraction pipeline is manual (`batch_extract_decisions.py`). Only 44 decisions exist (Oct-Dec 2025). This item adds automated decision extraction to Modal's scheduled pipeline.

## Recommended Task

Add decision extraction to Modal automated pipeline (`scripts/modal_ingest.py`). Should run weekly (not daily - meeting minutes PDFs lag behind meetings).

## Key Files

- `scripts/modal_ingest.py:470-590` - existing extract_chunks() pattern to follow
- `scripts/batch_extract_decisions.py` - current manual script
- `packages/civic-extraction/src/civic_extraction/cli/decisions.py` - run_decision_extraction()
- `packages/civic-extraction/src/civic_extraction/processing/retrospective_analyzer.py` - RetrospectiveAnalyzer (NEW location)

## Suggested Approach

1. **Review existing chunk extraction** in modal_ingest.py:
   ```bash
   grep -A 30 'def extract_chunks' scripts/modal_ingest.py
   ```

2. **Add extract_decisions() function** to modal_ingest.py:
   - Import run_decision_extraction from civic_extraction.cli.decisions
   - Similar pattern to extract_chunks() but for decisions
   - Add --decisions and --decisions-limit CLI args

3. **Note:** RetrospectiveAnalyzer now requires `provider` parameter:
   ```python
   from civic_services.core.llm_provider import get_model_for_task
   provider = get_model_for_task('long_document')
   analyzer = RetrospectiveAnalyzer(provider=provider)
   ```

4. **Add to weekly schedule** (not daily) - create separate workflow or conditional logic

5. **Test locally first:**
   ```bash
   modal run scripts/modal_ingest.py --decisions --dry-run
   ```

## Current State

- Chunks: Automated via Modal (Session 470)
- Issues: Automated via Modal
- Vectors: Automated via Modal
- **Decisions: MANUAL** ← This is what we're fixing

## Tests to Run

```bash
# Smoke test first
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Test decision extraction CLI locally
python -m civic_extraction.cli decisions extract --help
```

## Success Criteria

- [ ] `extract_decisions()` function added to modal_ingest.py
- [ ] CLI args: --decisions, --decisions-limit
- [ ] Decisions excluded from daily refresh (weekly only)
- [ ] `modal run scripts/modal_ingest.py --decisions --dry-run` works
- [ ] pilot.json updated: automated_decision_extraction → ready
