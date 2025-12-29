# Recommended: chunks_extraction_reliability

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-28

> This is recommended context from Session 392. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 392 fixed the chunks PDF extraction bug (HTML meeting pages -> actual PDFs). The fix works: extracted 4,115 chunks from 27 meetings. However, extraction **stalled at meeting 36/46** (23MB PDF) and **full extraction takes 2+ hours locally**. These reliability/performance issues must be addressed before chunks_e2e_cloud can be marked ready.

## Current Cloud Data Status

| Data Type | Cloud Count | Status |
|-----------|-------------|--------|
| Meetings | 46 | ready |
| Issues | 1,330 | ready |
| Agenda Items | 44 | ready |
| Decisions | 44 | ready |
| **Chunks** | **4,115 (27/46 meetings)** | **PARTIAL** |
| Transcripts | 0 | not_ready |

## Problems to Address

1. **Large PDF timeout/hang**: Meeting 36 (23MB PDF) caused extraction to stall indefinitely
2. **Slow extraction**: 2+ hours for 46 meetings is too slow for production
3. **No graceful failure**: When a PDF hangs, the whole pipeline stops

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/chunks.py:448-574` - PDF extraction logic
- `packages/civic-extraction/src/civic_extraction/cli/chunks.py:618-800` - extract_chunks_from_meeting()
- `packages/civic/_internal/meetings/pdf_parser.py` - AgendaPacketParser (the slow part)

## Suggested Approach

### Option A: Add timeout handling (quick fix)
```python
# In extract_chunks_from_meeting(), wrap PDF parsing with timeout
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("PDF parsing timed out")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(300)  # 5 minute timeout per PDF
try:
    chunks = parser.parse_to_chunks(temp_path, ...)
finally:
    signal.alarm(0)
```

### Option B: Evaluate remote compute (longer term)
- Modal.com: Serverless Python, pay-per-use
- Render background workers
- Fly.io machines
- AWS Lambda (may have memory limits for large PDFs)

### Option C: Parallelization
- Python multiprocessing for PDF parsing
- Async download while parsing previous

## Tests to Run

```bash
# Test single large PDF extraction
source civic-env/bin/activate
python3 -c "
from civic_extraction.cli.chunks import extract_chunks_from_meeting
meeting = {'id': 'test', 'meeting_date': '2025-12-09', 'agenda_url': 'https://www.cityofsanrafael.org/meetings/planning-commission-december-9-2025/'}
result = extract_chunks_from_meeting(meeting, '/tmp/test', 'city-san-rafael', cloud=False)
print(f'Status: {result.status}, Chunks: {result.chunks_count}')
"
```

## Success Criteria

- [ ] Extraction handles 23MB+ PDFs without hanging (timeout or success)
- [ ] Full 46-meeting extraction completes in <30 minutes
- [ ] Failed/timed-out meetings are logged and skipped gracefully
- [ ] All 46 meetings processed (chunks or documented failure)

## Notes

- The PDF parser (`AgendaPacketParser`) uses pdfplumber - memory/CPU intensive for large files
- Some meetings legitimately have no PDFs (cancelled meetings)
- Consider tracking which meetings failed for manual review
