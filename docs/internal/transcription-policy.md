# Transcription Policy

## Tiered Coverage Model

Transcription is the most expensive corpus per jurisdiction (~$1.60/meeting at AssemblyAI rates). To manage costs while maintaining user value, we use a two-tier model:

### Tier 1: Full Audio Transcripts (recent)

- **Window**: Current quarter + prior quarter (rolling ~6 months, minimum 3 months)
- **What**: Full AssemblyAI transcription with speaker diarization
- **Enables**: "What was said about X?", public testimony search, meeting prep, debate context
- **Cost**: ~$7-8/jurisdiction/quarter (~10-15 meetings × $1.60/meeting)

### Tier 2: Agenda Packets + Decisions (older)

- **Window**: Everything older than Tier 1 (up to 12 months back)
- **What**: PDF agenda chunks (already extracted), decision records, vote outcomes
- **Enables**: "What happened with X?", decision search, historical context
- **Cost**: $0 incremental (agenda PDFs are already ingested)

### Not Indexed

- **Window**: Beyond 12 months
- **Rationale**: Civic information older than 12 months is rarely actionable. Users researching deep history can access archived meeting minutes directly.

## Cost Reference

| Item | Unit Cost | Notes |
|------|-----------|-------|
| AssemblyAI transcription | $0.65/hr audio | ~$1.60 per 2.5hr meeting |
| Residential proxy (YouTube) | ~$10/GB | ~$2.50 per YouTube video download |
| Granicus audio download | $0/video | Public HLS streams, no proxy needed |
| Modal compute | ~$0.10/hr | Container time for download + convert |
| R2 storage | $0.015/GB/month | Opus files ~60 MB/meeting |

## Per-Jurisdiction Onboarding Budget

| Tier | Meetings/Quarter | Cost/Quarter | Annual |
|------|-----------------|--------------|--------|
| Small city (Belvedere, Ross) | 5-10 | $8-16 | $32-64 |
| Medium city (Fairfax, Sausalito) | 15-25 | $24-40 | $96-160 |
| Large city (San Rafael, Berkeley) | 30-50 | $48-80 | $192-320 |
| County | 10-20 | $16-32 | $64-128 |

**20 Bay Area jurisdictions estimate: ~$2,400/year for transcription**

## Audio Source Routing

| Source | Proxy Required | Download Cost | Detection |
|--------|---------------|---------------|-----------|
| Granicus (HLS) | No | Free | `granicus.com` in video_url |
| Granicus (archive-video) | No | Free | `archive-video.granicus.com` in video_url |
| YouTube | Yes (from datacenter) | ~$2.50/video | `youtube.com` or videos table |
| Local download | No | Free | Residential IP, no proxy needed |

**Always prefer Granicus over YouTube when both exist** — Granicus is free, YouTube costs proxy bandwidth.

## Cost Approval Requirement

Batch operations that consume paid resources MUST show a cost estimate before execution:

```bash
# Shows estimate, blocks execution
modal run scripts/modal_ingest.py --batch-audio --jurisdictions auto

# Approve after reviewing estimate
modal run scripts/modal_ingest.py --batch-audio --jurisdictions auto --approve-cost
```

The `--approve-cost` flag is required. There is no way to bypass the estimate step.

## Ongoing Ingestion

New meetings are ingested via cron (GitHub Actions). The transcription cron should:

1. Only transcribe meetings from the current Tier 1 window
2. Skip meetings that already have transcripts
3. Log estimated cost before processing
4. Respect a per-run cost cap (default: $20/run, ~12 meetings)

## Scaling to New Regions

When onboarding a new region (e.g., East Bay, SF, Peninsula):

1. Identify video source per jurisdiction (Granicus vs YouTube vs other)
2. Run cost estimate: `modal run scripts/modal_ingest.py --batch-audio --jurisdictions "city-X,city-Y"`
3. Onboard Granicus cities first (free audio download)
4. YouTube cities require proxy budget approval
5. Start with Tier 1 window only — expand to Tier 2 after validating user demand
