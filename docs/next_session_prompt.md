# Recommended: automated_agenda_extraction

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-05

> This is recommended context from Session 471. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Why This Is P0

Agenda item extraction is **CORE FUNCTIONALITY**. Without it, the platform can't answer:
- "What's being decided at next week's City Council?"
- "Which upcoming meetings have housing items?"
- "What can I participate in this month?"

Currently `whats_next()` returns meetings but not what's ON the agenda.

## Current State

```
BROKEN:
  agenda_items table: 44 items (just metadata like "Agenda Packet")
  Average: 1.2 items/meeting (should be ~10-15)

EXPECTED:
  ~460 actionable items from 46 meetings
  Each with: item_ref, title, description, actionable, project_types
```

## What Exists (code is written!)

| Component | Status | Location |
|-----------|--------|----------|
| AgendaIntegrator | ✅ Works | `civic-services/processing/agenda_integration.py` |
| CLI command | ✅ Works | `civic-extract agenda --jurisdiction city-san-rafael --cloud` |
| store_agenda_items() | ✅ Works | PostgresBackend |
| Modal function | ❌ Missing | `scripts/modal_ingest.py` |
| Scheduled run | ❌ Missing | Add to `scheduled_low_velocity_refresh` (weekly) |

## Implementation Plan

### Step 1: Test Existing CLI (verify it works)

```bash
# Dry run to see what would be extracted
civic-extract agenda --jurisdiction city-san-rafael --cloud --dry-run --limit 3

# Extract from 1 meeting to verify
civic-extract agenda --jurisdiction city-san-rafael --cloud --limit 1
```

### Step 2: Add Modal Function

Add to `scripts/modal_ingest.py`:

```python
@app.function(
    image=civic_image,
    secrets=[modal.Secret.from_name("civic-db"), modal.Secret.from_name("civic-llm")],
    memory=2048,
    timeout=1800,  # 30 min
)
def extract_agenda_items(jurisdiction: str = "city-san-rafael", limit: int = 0, dry_run: bool = False):
    """Extract actionable agenda items from meeting agendas using LLM."""
    from civic_extraction.cli.agenda import run_agenda_extraction

    results = run_agenda_extraction(
        jurisdiction,
        cloud=True,
        limit=limit if limit > 0 else 0,
        dry_run=dry_run,
    )

    return {
        "jurisdiction": jurisdiction,
        "meetings_processed": len(results) if results else 0,
        "status": "success" if results else "no_results",
    }
```

### Step 3: Add to Weekly Schedule

In `scheduled_low_velocity_refresh()`:

```python
# Agenda item extraction (weekly - agendas posted ~1 week before meetings)
try:
    logger.info("Extracting agenda items...")
    result = extract_agenda_items.local(
        jurisdiction="city-san-rafael",
        dry_run=False,
    )
    results["agenda_items"] = result
    logger.info(f"  Agenda items: {result.get('meetings_processed', 0)} meetings processed")
except Exception as e:
    logger.exception("Agenda item extraction failed")
    results["agenda_items"] = {"status": "failed", "error": str(e)}
```

### Step 4: Backfill Existing Meetings

```bash
# Run full backfill (~$5-25 in LLM costs)
modal run scripts/modal_ingest.py --agenda-items
```

## Cost Estimate

| Operation | Cost |
|-----------|------|
| Backfill 46 meetings | $5-25 (one-time) |
| Weekly new meetings | $1-5/week |
| Gemini 1.5 Pro | ~$0.10-0.50/meeting |

## Success Criteria

- [ ] `civic-extract agenda --cloud --dry-run` shows meetings to process
- [ ] `extract_agenda_items` Modal function added
- [ ] Added to `scheduled_low_velocity_refresh` (weekly)
- [ ] Backfill run: ~460 agenda items extracted
- [ ] `whats_next()` returns meetings WITH actionable items
- [ ] pilot.json updated: `automated_agenda_extraction` → ready

## Key Files

- `packages/civic-services/src/civic_services/processing/agenda_integration.py` - AgendaIntegrator
- `packages/civic-extraction/src/civic_extraction/cli/agenda.py` - CLI command
- `scripts/modal_ingest.py` - Add Modal function here
- `packages/civic/src/civic/storage/postgres_backend.py` - store_agenda_items()

## Verification Query

After extraction, verify with:

```python
from civic import Civic
c = Civic("san-rafael")
upcoming = c.whats_next()
for meeting in upcoming[:2]:
    print(f"{meeting['title']}")
    for item in meeting.get('agenda_items', []):
        print(f"  - {item['item_ref']}: {item['title']}")
```

## Dependencies

- ✅ `temporal_versioning_review` - Fixed in Session 471
- ⚠️ Requires `GOOGLE_API_KEY` in Modal secrets for Gemini

## Related Items

- `automated_decision_extraction` (P1) - Extract decisions from minutes (similar pattern)
- `automated_chunk_extraction` (P1) - Already in pipeline, working
