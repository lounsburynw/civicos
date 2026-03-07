# Admin Data Management Guide

How to manage extracted data in the Civic platform. For initial setup, see [ADMIN_SETUP_GUIDE.md](ADMIN_SETUP_GUIDE.md). For troubleshooting, see [ADMIN_TROUBLESHOOTING.md](ADMIN_TROUBLESHOOTING.md).

---

## Table of Contents

1. [Data Overview](#data-overview)
2. [Directory Structure](#directory-structure)
3. [Extraction Pipelines](#extraction-pipelines)
4. [Monitoring Pipeline Health](#monitoring-pipeline-health)
5. [Checkpoints](#checkpoints)
6. [Manual Data Operations](#manual-data-operations)
7. [Database Management](#database-management)
8. [Backup and Restore](#backup-and-restore)
9. [Data Retention](#data-retention)
10. [Storage Management](#storage-management)

---

## Data Overview

Civic manages several types of extracted data:

| Data Type | Source | Refresh Frequency | Storage |
|-----------|--------|-------------------|---------|
| Meetings | Legistar/CivicClerk | Daily | `data/events/` |
| YouTube videos | City YouTube channels | Daily | `data/youtube_audio/` |
| Transcripts | AssemblyAI | Daily | `data/testimony/` |
| Citizen issues | SeeClickFix | Daily | Database |
| Legislative context | LegiScan | Weekly | `data/legislation/` |
| Vector embeddings | Local | On re-index | `data/vectors/` |

### Data Flow

```
External APIs → Extraction CLI → JSON/Audio files → Database → Vector Index → API
```

Each pipeline:
1. Fetches data from external source
2. Saves to disk as JSON or audio
3. Writes a checkpoint for tracking
4. Database/vector updates happen on subsequent processing

---

## Directory Structure

```
data/
├── checkpoints/              # Pipeline run timestamps
│   ├── city-san-rafael.json  # Meeting discovery checkpoint
│   ├── youtube_city-san-rafael.json
│   ├── audio_city-san-rafael.json
│   ├── transcribe_city-san-rafael.json
│   ├── seeclickfix_city-san-rafael.json
│   └── legislative_california_housing.json
├── civic_state.db            # Application state (meetings, etc.)
├── civic_participation.db    # User participation data
├── events/                   # Extracted meeting data
│   ├── archive/              # Historical events
│   └── backup/               # Event backups
├── legislation/              # Legislative context
│   ├── federal/
│   ├── state/
│   └── municipal/
├── testimony/                # Extracted speaker testimony
│   └── testimony_*.json
├── vectors/                  # RAG vector embeddings
├── youtube_audio/            # Downloaded audio files
│   └── *.mp3
└── youtube_transcripts/      # YouTube caption data
    └── *.json3
```

### Size Reference (Pilot)

| Directory | Typical Size |
|-----------|--------------|
| `civic_state.db` | 2-5 MB |
| `civic_participation.db` | 1-6 MB |
| `testimony/` | 5-10 MB |
| `youtube_audio/` | 50-200 MB |
| `vectors/` | 100-500 KB |
| `checkpoints/` | < 100 KB |

---

## Extraction Pipelines

The `civic-extract` CLI manages all data extraction.

### Available Commands

| Command | Purpose | Default Schedule |
|---------|---------|------------------|
| `discover` | Find meetings from Legistar/CivicClerk | Daily |
| `youtube` | Discover YouTube videos | Daily |
| `audio` | Download audio from videos | Daily |
| `transcribe` | Transcribe audio with speakers | Daily |
| `seeclickfix` | Refresh citizen issues | Daily |
| `legislative` | Update legislative context | Weekly (Sunday) |
| `monitor` | Check pipeline health | On-demand |

### Running Pipelines Manually

```bash
# Activate environment
source civicos-env/bin/activate

# Run individual pipelines
civic-extract discover --jurisdiction city-san-rafael
civic-extract youtube --jurisdiction city-san-rafael
civic-extract audio --jurisdiction city-san-rafael
civic-extract transcribe --jurisdiction city-san-rafael
civic-extract seeclickfix --jurisdiction city-san-rafael
civic-extract legislative --state california --topic housing

# Run with verbose logging
civic-extract discover --jurisdiction city-san-rafael -v
```

### Full Pipeline Refresh

To refresh all data for a jurisdiction:

```bash
# 1. Discover meetings
civic-extract discover --jurisdiction city-san-rafael

# 2. Find videos for discovered meetings
civic-extract youtube --jurisdiction city-san-rafael

# 3. Download audio from new videos
civic-extract audio --jurisdiction city-san-rafael

# 4. Transcribe new audio
civic-extract transcribe --jurisdiction city-san-rafael

# 5. Update citizen issues
civic-extract seeclickfix --jurisdiction city-san-rafael
```

---

## Monitoring Pipeline Health

Use the `monitor` command to detect missed or failed pipeline runs.

### Check All Pipelines

```bash
civic-extract monitor --check-all
```

Output shows status for each pipeline:
```
Pipeline Status Check
=====================
discover (city-san-rafael): OK (last run 2h ago, threshold 24h)
youtube (city-san-rafael): OK (last run 3h ago, threshold 24h)
audio (city-san-rafael): OK (last run 3h ago, threshold 24h)
transcribe (city-san-rafael): OK (last run 4h ago, threshold 24h)
seeclickfix (city-san-rafael): OK (last run 5h ago, threshold 24h)
legislative (california/housing): OK (last run 2d ago, threshold 168h)
```

### Check Specific Pipeline

```bash
# Check meeting discovery
civic-extract monitor --pipeline discover --jurisdiction city-san-rafael

# Check legislative with custom threshold
civic-extract monitor --pipeline legislative --max-age 200
```

### CI/Monitoring Integration

```bash
# Exit code 1 if any pipeline is overdue (for alerting)
civic-extract monitor --check-all --exit-on-overdue

# JSON output for parsing
civic-extract monitor --check-all --format json
```

---

## Checkpoints

Checkpoints track when each pipeline last ran successfully.

### Checkpoint Format

```json
{
  "jurisdiction_id": "city-san-rafael",
  "last_meeting_id": "proudcity-city-san-rafael-city-council-january-6-2026",
  "last_meeting_datetime": "2026-01-06T00:00:00",
  "items_processed": 17,
  "checkpoint_at": "2025-12-21T19:05:36.555260"
}
```

Key fields:
- `checkpoint_at`: When the pipeline last completed
- `items_processed`: Number of items in last run
- Additional fields vary by pipeline type

### View Checkpoints

```bash
# List all checkpoints
ls -la data/checkpoints/

# View specific checkpoint
cat data/checkpoints/city-san-rafael.json
```

### Reset Checkpoint (Force Re-run)

To force a pipeline to re-fetch all data:

```bash
# Remove checkpoint file
rm data/checkpoints/city-san-rafael.json

# Next run will fetch from scratch
civic-extract discover --jurisdiction city-san-rafael
```

**Warning:** This may cause duplicate data or high API usage. Use sparingly.

---

## Manual Data Operations

### Adding a New Jurisdiction

1. Create jurisdiction override:
   ```bash
   touch data/jurisdiction_overrides/city-newcity.json
   ```

2. Run initial extraction:
   ```bash
   civic-extract discover --jurisdiction city-newcity
   civic-extract youtube --jurisdiction city-newcity
   ```

3. Verify data:
   ```bash
   ls data/checkpoints/*newcity*
   ```

### Removing a Jurisdiction

```bash
# Remove extracted data
rm -rf data/events/city-oldcity/
rm data/checkpoints/*oldcity*
rm data/testimony/testimony_*_city-oldcity.json

# Remove from database
python3 -c "
from civic._internal.state import StateManager
state = StateManager('data/civic_state.db')
state.delete_jurisdiction('city-oldcity')
"
```

### Re-indexing Vectors

After adding significant new content:

```bash
python3 -c "
from civic._internal.rag import RAGEngine
rag = RAGEngine('city-san-rafael')
rag.rebuild_index('data/pilot/rag_corpus/city-san-rafael')
"
```

---

## Database Management

### Viewing Database State

```bash
# Check meeting count
python3 -c "
from civic._internal.state import StateManager
state = StateManager('data/civic_state.db')
meetings = state.get_meetings('city-san-rafael')
print(f'Meetings: {len(meetings)}')
"

# Check database size
du -h data/civic_state.db data/civic_participation.db
```

### Running Migrations

```bash
# Check migration status
python scripts/migrate.py --status

# Apply pending migrations
python scripts/migrate.py
```

### Database Integrity Check

```bash
# SQLite integrity check
sqlite3 data/civic_state.db "PRAGMA integrity_check;"
```

---

## Backup and Restore

### Automated Backups

Daily backups run via GitHub Actions at 2:00 AM UTC. See [DAILY_BACKUP_SCHEDULE.md](../critical/DAILY_BACKUP_SCHEDULE.md).

### Manual Backup (Local)

```bash
# Simple copy
cp data/civic_state.db data/civic_state.db.backup-$(date +%Y%m%d)

# With timestamp verification
sqlite3 data/civic_state.db "SELECT COUNT(*) FROM meetings;" > /dev/null && \
  cp data/civic_state.db data/civic_state.db.backup-$(date +%Y%m%d)
```

### Manual Backup (Production)

Production data lives in Supabase PostgreSQL (managed, with automatic daily backups and PITR on Pro plan).

```bash
# Run backup script locally (connects to Supabase via DATABASE_URL)
source civicos-env/bin/activate
python scripts/backup.py --compress

# List available local backups
python scripts/backup.py --list

# Check Supabase automatic backups via dashboard:
# https://supabase.com/dashboard/project/lhtuixsynupnkejpahxk/settings/backups
```

### Restore from Backup

```bash
# Local
cp data/civic_state.db.backup-20251220 data/civic_state.db

# Production (Supabase)
# Use Supabase Dashboard > Backups > Restore to point in time (PITR)
# Or restore from a local backup:
python scripts/backup.py --restore civic_state_20251220.db.gz --force
```

---

## Data Retention

### Retention Policies

| Data Type | Retention | Notes |
|-----------|-----------|-------|
| Database backups (daily) | 7 days | Automated cleanup |
| Database backups (weekly) | 4 weeks | Automated cleanup |
| YouTube audio | Indefinite | Delete manually when unneeded |
| Transcripts | Indefinite | Archive after 1 year |
| Checkpoints | Current only | Overwritten each run |

### Cleaning Old Data

```bash
# Remove audio files older than 90 days
find data/youtube_audio -name "*.mp3" -mtime +90 -delete

# Archive old transcripts
mkdir -p data/testimony/archive
find data/testimony -name "testimony_*.json" -mtime +365 \
  -exec mv {} data/testimony/archive/ \;

# Clean old local backup files
python scripts/backup.py --clean
```

---

## Storage Management

### Checking Storage Usage

```bash
# Overall data directory
du -sh data/

# By subdirectory
du -sh data/*/

# Detailed breakdown
du -h data/ | sort -h | tail -20
```

### Reducing Storage

1. **Audio files** - Largest storage consumer
   ```bash
   # Remove audio for transcribed videos
   # (transcripts are in testimony/, audio can be re-downloaded)
   rm data/youtube_audio/*.mp3
   ```

2. **Database vacuum**
   ```bash
   sqlite3 data/civic_state.db "VACUUM;"
   sqlite3 data/civic_participation.db "VACUUM;"
   ```

3. **Clean duplicate transcripts**
   ```bash
   # Some videos may have multiple transcript versions
   ls data/testimony/testimony_*_v2.json 2>/dev/null
   ls data/testimony/testimony_*_original.json 2>/dev/null
   ```

### Storage Notes

Production uses managed services with no disk to fill:
- **PostgreSQL**: Supabase manages storage automatically (Pro plan)
- **Blobs (PDFs, audio)**: Cloudflare R2 (virtually unlimited object storage)
- **Compute**: Modal is serverless/stateless — no persistent disk

For local development storage issues:

```bash
# Check local data directory
du -sh data/*/

# Clean old local backups
python scripts/backup.py --clean

# Remove audio files (can be re-downloaded)
rm data/youtube_audio/*.mp3
```

---

## Common Tasks Reference

| Task | Command |
|------|---------|
| Check all pipelines | `civic-extract monitor --check-all` |
| Refresh meetings | `civic-extract discover --jurisdiction city-san-rafael` |
| View checkpoint | `cat data/checkpoints/city-san-rafael.json` |
| Check database size | `du -h data/*.db` |
| Run migration | `python scripts/migrate.py` |
| Backup database | `cp data/civic_state.db data/civic_state.db.backup` |
| List backups (prod) | `python scripts/backup.py --list` (local) or Supabase Dashboard |
| Clean audio files | `rm data/youtube_audio/*.mp3` |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [ADMIN_SETUP_GUIDE.md](ADMIN_SETUP_GUIDE.md) | Initial deployment |
| [ADMIN_TROUBLESHOOTING.md](ADMIN_TROUBLESHOOTING.md) | Problem resolution |
| [DAILY_BACKUP_SCHEDULE.md](../critical/DAILY_BACKUP_SCHEDULE.md) | Automated backup details |
| [ROLLBACK_PROCEDURES.md](../critical/ROLLBACK_PROCEDURES.md) | Data recovery |
