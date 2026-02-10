# Recommended: Expandable Decisions — Transcript Display Quality

**Priority:** P0
**Area:** expandable_decisions
**Date:** 2026-02-08

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Expandable decisions backend is **complete and committed** (`7958dcb`). The `decision_detail` MCP endpoint now:
- Exact SQL title match (fast path for dashboard)
- Structural transcript matching: decision → agenda_item → meeting_id → scoped vector search (73% of decisions resolve)
- Parent item fallback ("6.a.ii" → "6.a" → "6")
- Precision threshold (min_score=0.62) — suppresses off-topic matches
- SQL enrichment of vector results (outcome, body, votes, agenda_item)
- Backfilled meeting_datetime for all 6,223 transcript vectors

Also committed: meeting_id filter on VectorBackend.search() protocol, speaker_role fallback for is_public_comment, Modal cost optimization (64GB→8GB).

## Problem: Transcript Display Quality

The transcript text displayed in the UX is **the full chunk content**, which includes speaker labels, cross-talk, and meeting procedural text. Example for "Real Property Negotiation: 519 Fourth Street":

```
Kate Colin
[Kate Colin (Mayor)] [B] Mine still says five o'. Clock. [C] Okay. Welcome everyone.
It's the last meeting of the year. Monday, December 15th. We're going to head into
closed session on conference with real property negotiators. Property at 519 4th St.
```

This is the meeting **opening**, not the substantive discussion. The chunk is technically relevant (mentions 519 4th St) but the **displayed portion** (first 300 chars) misses the meaningful content deeper in the chunk. The `text[:300]` truncation in `decision_detail` may be cutting off the useful part.

### Root causes to investigate:
1. **Truncation**: Chunks are ~500-1000 chars. `text[:300]` may show preamble instead of substance. Consider showing the most relevant **sentence** within the chunk rather than the first 300 chars.
2. **Chunk granularity**: Transcript chunks group multiple utterances. A chunk containing "Welcome everyone... 519 4th St... Before we go into closed session" scores well on vector similarity but the actual content is just a mention, not discussion.
3. **Meeting opening bias**: Opening remarks that list all agenda items score high for every decision title. These should be deprioritized.

## Recommended Task

**Improve transcript excerpt display quality.** Two complementary approaches:

### Approach 1: Smarter text extraction (quick win)
Instead of `text[:300]`, extract the most relevant sentence(s) from the chunk:
- Split chunk text into sentences
- Score each sentence against the decision title (simple keyword overlap or embedding similarity)
- Return the top 1-2 sentences instead of first-300-chars

### Approach 2: UX-side presentation changes (Open WebUI)
- Show transcript excerpts with **video link + timestamp** (data already available: `video_url`, `start_timestamp`)
- Add a "Watch this moment" link using `https://youtube.com/watch?v={video_id}&t={start_ms/1000}s`
- Consider a **confidence/relevance slider** in the UI to let users adjust the precision threshold (currently hardcoded at 0.62)
- Display speaker role badge (public / council / staff) prominently

## Key Files

- `apps/civicos-mcp/tools/handlers.py:1374-1460` — decision_detail exact match path (where `text[:300]` truncation happens)
- `packages/civicos/src/civicos/history.py:1456-1620` — `_search_decision_transcripts_pgvector()` and `_resolve_decision_meeting_id()`
- `apps/civicos-openwebui-fork/src/lib/components/civic/` — Dashboard components that render decision detail
- `packages/civicos/src/civicos/_internal/meetings/transcript.py` — Transcript chunking logic

## Data Quality Gaps (from QC audit)

| Issue | Detail |
|-------|--------|
| All 44 outcomes are "approved" | Extraction may only capture approvals; no denied/tabled/continued |
| body is NULL for all 44 | No City Council vs Planning Commission distinction |
| vote_json is NULL for all 44 | No vote tallies |
| 10 of 44 are financial audits | Routine items crowd the decision list |
| speaker names degraded | Many "Public Speaker N" instead of real names |

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Test decision_detail handler
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
import sys; sys.path.insert(0, 'apps/civicos-mcp')
from tools.handlers import decision_detail
import logging
civic = CivicOS('city-san-rafael')
r = decision_detail(civic, 'city-san-rafael', lambda d: (True, d, None), logging.getLogger(), {'title': '25 Loch Lomond Drive - Approval of 14-Unit Residential Development'})
import json; print(json.dumps(r, indent=2, default=str))
"
```

## UX Ideas to Consider

- **Semantic threshold slider**: Let users adjust precision (0.5=more results, 0.7=fewer but precise). Currently hardcoded at 0.62 in `_search_decision_transcripts_pgvector()`.
- **Video links**: Data exists (`video_id`, `start_ms`). Format: `https://youtube.com/watch?v={video_id}&t={start_ms//1000}s`. Already constructed as `video_url` on TranscriptLink objects.
- **"No transcript available" state**: Clean empty state when precision threshold filters everything out — better than showing noise.
