# Mass Ingest Cost Ceiling

Hard spend limits for the 15-jurisdiction mass ingest. Written after the $50 proxy surprise on 2026-04-05 (a single Fairfax batch). Scaling to 15 jurisdictions without written limits risks a much larger surprise.

**Scope:** 11 Marin cities + county-marin + city-san-francisco + city-berkeley + county-alameda

## Per-Service Spend Caps

| Service | Per-Run Cap | Daily Cap | Weekly Cap | Enforcement |
|---------|------------|-----------|------------|-------------|
| AssemblyAI (transcription) | $50/jurisdiction | $100 | $400 | `--cost-cap-usd` flag (code) |
| YouTube proxy | $0 (prefer Granicus) | $20 | $50 | Manual — avoid YouTube sources |
| Modal compute (CPU) | — | $30 | $150 | Free credits ($30/mo); monitor via daily digest |
| Modal compute (GPU) | — | $10 | $50 | Vector indexing only; short runs |
| OpenAI / Gemini (LLM) | — | $5 | $25 | Per-meeting cost < $0.15; negligible at this scale |
| **Aggregate** | — | **$100** | **$500** | Daily cost digest alerts at $5/day |

**Hard ceiling: $500/week for the entire mass ingest.** If weekly spend approaches this, stop and reassess.

## Per-Jurisdiction Cost Estimates

Based on current meeting counts and audio source types. Costs are for **incremental** work (meetings without transcripts).

| Jurisdiction | Meetings | W/ Video | Transcripts | Remaining | Source | Est. Audio Cost | Est. Transcription | Est. Total |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| city-belvedere | 26 | 0 | 0 | 0 | proudcity | $0 | $0 | $0 |
| city-corte-madera | 18 | 11 | 0 | 11 | civicplus | $0* | $5.06 | $6 |
| city-fairfax | 100 | 16 | 13 | 3 | proudcity | $7.50† | $1.38 | $10 |
| city-larkspur | 16 | 0 | 0 | 0 | civicplus | $0 | $0 | $0 |
| city-ross | 19 | 0 | 0 | 0 | playwright_llm | $0 | $0 | $0 |
| city-tiburon | 11 | 7 | 7 | 0 | granicus | $0 | $0 | $0 |
| city-novato | 19 | 16 | 13 | 3 | granicus | $0 | $1.38 | $2 |
| city-mill-valley | 118 | 109 | 30 | 79 | granicus | $0 | $36.34 | $37 |
| city-san-anselmo | 177 | 136 | 30 | 106 | granicus | $0 | $48.76 | $50 |
| city-sausalito | 55 | 46 | 30 | 16 | granicus | $0 | $7.36 | $8 |
| county-marin | 134 | 27 | 27 | 0 | granicus | $0 | $0 | $0 |
| city-san-rafael | 111 | 31 | 44 | 0‡ | proudcity | $0 | $0 | $0 |
| city-san-francisco | 102 | 65 | 39 | 26 | granicus | $0 | $11.96 | $13 |
| city-berkeley | 80 | 72 | 30 | 42 | granicus | $0 | $19.32 | $20 |
| county-alameda | 265 | 257 | 61 | 196 | granicus | $0 | $90.16 | $91 |
| **TOTAL** | **1,251** | **793** | **324** | **482** | | **$7.50** | **$221.72** | **$237** |

*Assumptions:* 2 hrs avg meeting duration × $0.23/hr (AssemblyAI + diarization). Granicus audio is free. LLM extraction adds ~$1/jurisdiction.

\* Corte Madera: YouTube source — proxy cost if no Granicus alternative, but only 11 videos.
† Fairfax: YouTube proxy expired (407 NO_USER since 2026-04-04). 3 remaining videos need proxy fix or skip.
‡ San Rafael: 44 transcripts covers current meetings; some older meetings with video lack transcripts but are outside Tier 1 window.

### Cost Drivers

1. **county-alameda** ($91) — 196 untranscribed meetings with video. Largest single cost. Run in batches of 50.
2. **city-san-anselmo** ($50) — 106 remaining. Hits per-jurisdiction cap. Run in 2 batches.
3. **city-mill-valley** ($37) — 79 remaining.
4. **city-berkeley** ($20) — 42 remaining.
5. Everything else is under $15/jurisdiction.

## Unit Costs (Reference)

From `docs/public/cost_registry.yaml` (verified 2026-03-09):

| Service | Unit | Cost | Notes |
|---------|------|------|-------|
| AssemblyAI Universal-3 Pro | per hour audio | $0.21 | Primary transcription |
| AssemblyAI diarization | per hour audio | $0.02 | Speaker labels add-on |
| **Transcription total** | **per hour audio** | **$0.23** | **$0.46 per 2-hour meeting** |
| YouTube residential proxy | per GB | ~$10 | ~$2.50 per video (~250 MB) |
| Granicus audio (HLS/MP3) | per video | $0.00 | Public streams, no proxy |
| Modal CPU | per core-second | $0.0000131 | Covered by $30/mo free credits |
| Modal T4 GPU | per second | $0.000164 | Vector indexing: 5-15 min/run |
| OpenAI gpt-4o-mini | per 1M tokens | $0.15 | Mode detection, extraction |
| Gemini 2.0 Flash | per 1M tokens | $0.075 | Routing, decision extraction |
| R2 storage | per GB/month | $0.015 | Opus audio ~60 MB/meeting |

## Monitoring & Alerting

### Daily Cost Digest (deployed)

- **Schedule:** Daily at 9:00 AM UTC via GitHub Actions (`daily-cost-digest.yml`)
- **Thresholds:** $5/day warning, $50/month warning
- **Channels:** Email (SMTP), ntfy.sh push, Slack webhook (optional)
- **Data source:** `platform_usage_logs` table in Supabase

### Usage Logging

- All API and ingestion costs are logged to `platform_usage_logs` (hourly resolution)
- `modal_usage_rollup.py` aggregates logs >90 days into `platform_usage_daily`
- Query recent spend:
  ```sql
  SELECT service, SUM(cost_usd) as total
  FROM platform_usage_logs
  WHERE created_at > NOW() - INTERVAL '7 days'
  GROUP BY service ORDER BY total DESC;
  ```

### Code-Level Controls

| Control | Location | Default |
|---------|----------|---------|
| `--cost-cap-usd` | `scripts/modal_ingest.py:6143` | $50/jurisdiction |
| `--approve-cost` | `scripts/modal_ingest.py:6029` | Required (blocks without approval) |
| Cost estimate display | `estimate_audio_costs()` at line 5890 | Always shown before batch ops |
| Meeting limit from cap | Line 6609: `int(cost_cap_usd / 2.60)` | ~19 meetings at $50 cap |

## Kill-Switch Procedure

When spend is approaching limits or something looks wrong, follow these steps in order:

### 1. Stop In-Flight Modal Jobs (immediate)

```bash
# List running jobs
modal job list

# Stop a specific job
modal job stop <job-id>

# Nuclear: stop ALL running Modal apps
modal app list | grep RUNNING
modal app stop <app-name>
```

### 2. Disable Cron Pipelines

Cron jobs run via GitHub Actions, not Modal. Disable by:

**Option A — Disable specific workflow (recommended):**
```bash
# Disable the high-velocity refresh (most likely to trigger ingestion)
gh workflow disable "cron-high-velocity-refresh.yml"
gh workflow disable "cron-low-velocity-refresh.yml"
gh workflow disable "cron-meetings-poll.yml"

# Re-enable when ready
gh workflow enable "cron-high-velocity-refresh.yml"
```

**Option B — Emergency: disable ALL cron workflows:**
```bash
for wf in .github/workflows/cron-*.yml; do
  gh workflow disable "$(basename $wf)"
done
```

### 3. Verify Nothing Is Running

```bash
# Check Modal
modal job list

# Check GitHub Actions
gh run list --workflow=cron-high-velocity-refresh.yml --status=in_progress
gh run list --workflow=cron-low-velocity-refresh.yml --status=in_progress
```

### 4. Post-Incident Review

1. Export spend data:
   ```bash
   source civicos-env/bin/activate
   python3 -c "
   from dotenv import load_dotenv; load_dotenv()
   import psycopg2, os
   conn = psycopg2.connect(os.environ['DATABASE_URL'])
   cur = conn.cursor()
   cur.execute('''
     SELECT service, SUM(cost_usd), COUNT(*)
     FROM platform_usage_logs
     WHERE created_at > NOW() - INTERVAL '24 hours'
     GROUP BY service ORDER BY SUM(cost_usd) DESC
   ''')
   for row in cur.fetchall():
       print(f'{row[0]:20s}  \${row[1]:.2f}  ({row[2]} calls)')
   "
   ```
2. Identify which jurisdiction/service caused the spike
3. Update this document with the incident and any adjusted thresholds

## Recommended Execution Order

Run the mass ingest in priority order, pausing to verify costs between batches:

### Batch 1: Low-cost / already-done (verify existing coverage)
- city-belvedere, city-larkspur, city-ross — no video URLs, $0
- city-tiburon, county-marin, city-san-rafael — already fully transcribed, $0

### Batch 2: Small remainder ($0-15/jurisdiction)
```bash
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-novato --cost-cap-usd 10
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-corte-madera --cost-cap-usd 10
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-sausalito --cost-cap-usd 15
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-san-francisco --cost-cap-usd 15
```
**Batch 2 estimate: ~$29.** Verify before proceeding.

### Batch 3: Medium ($15-50/jurisdiction)
```bash
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-berkeley --cost-cap-usd 25
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-mill-valley --cost-cap-usd 40
modal run scripts/modal_ingest.py --transcripts --jurisdiction city-san-anselmo --cost-cap-usd 50
```
**Batch 3 estimate: ~$107.** Verify before proceeding.

### Batch 4: Large (county-alameda, $91)
```bash
# Run in sub-batches of 50 meetings
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --cost-cap-usd 25 --limit 50
# Verify, then continue
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --cost-cap-usd 25 --limit 50
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --cost-cap-usd 25 --limit 50
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --cost-cap-usd 25 --limit 50
```
**Batch 4 estimate: ~$91.** Largest single jurisdiction.

### Batch 5: Vector indexing (after all transcripts complete)
```bash
# Index all new transcript vectors
modal run scripts/modal_ingest.py --vectors --jurisdiction auto --corpus-type transcripts
```
**Batch 5 estimate: ~$5-10 total** (GPU time is cheap with fastembed).

**Total estimated mass ingest cost: ~$237** (well under the $500/week hard ceiling).

## Known Gaps

| Gap | Mitigation | Status |
|-----|-----------|--------|
| No real-time per-service spend enforcement | Daily digest + manual kill-switch | Acceptable for 15-jurisdiction scale |
| YouTube proxy expired (407) | Fairfax has only 3 remaining videos; skip or fix proxy | Low priority |
| No automatic circuit-breaker per jurisdiction | `--cost-cap-usd` limits per run; operator must sequence batches | Acceptable |
| Daily digest thresholds ($5/day) are low for mass ingest | Temporarily raise to $100/day during batch runs, reset after | Document when raising |
| Belvedere, Larkspur, Ross have no video URLs | Audio not available on their platforms; transcripts not possible | Accept gap |

## Incident Log

| Date | Service | Amount | Cause | Resolution |
|------|---------|--------|-------|------------|
| 2026-04-05 | YouTube proxy | ~$50 | Fairfax batch audio download through residential proxy | Proxy credentials expired shortly after. Switched to Granicus where possible. |

---

*Last updated: 2026-04-10. Cross-reference: `docs/public/cost_registry.yaml` for unit prices, `docs/internal/transcription-policy.md` for tiered model.*
