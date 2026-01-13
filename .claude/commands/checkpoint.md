# Checkpoint

View and manage ingestion checkpoints for resumable pipeline operations.

## Usage

```
/checkpoint [action] [options]
```

**Actions:**
- `status` - Show checkpoint status for jurisdiction (default)
- `reset [source]` - Reset checkpoint to re-run from beginning
- `list` - List all checkpoint files

## Examples

```
/checkpoint                                  # Status for all jurisdictions
/checkpoint status city-san-rafael           # Status for specific jurisdiction
/checkpoint list                             # List all checkpoint files
/checkpoint reset city-san-rafael            # Reset all checkpoints for jurisdiction
/checkpoint reset city-san-rafael audio      # Reset only audio checkpoint
```

## What Are Checkpoints?

Checkpoints track progress for resumable ETL operations. When ingestion is interrupted, it resumes from the last checkpoint instead of restarting.

**Checkpoint file:** `data/checkpoints/{source}_{jurisdiction}.json`

```json
{
  "jurisdiction_id": "city-san-rafael",
  "last_video_id": "abc123",
  "items_processed": 50,
  "items_downloaded": 48,
  "items_skipped": 2,
  "items_failed": 0,
  "timestamp": "2026-01-12T20:02:01.705555"
}
```

## Steps

### 1. View Checkpoint Status

```bash
source civic-env/bin/activate && python3 -c "
import json
from pathlib import Path
from datetime import datetime

checkpoints = Path('data/checkpoints').glob('*.json')
print(f'{'Source':<30} {'Processed':<12} {'Age':<15}')
print('-' * 57)
for cp in sorted(checkpoints):
    try:
        data = json.loads(cp.read_text())
        processed = data.get('items_processed', 0)
        ts = data.get('timestamp', '')
        if ts:
            age = datetime.now() - datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0])
            age_str = f'{age.days}d {age.seconds//3600}h ago'
        else:
            age_str = 'unknown'
        print(f'{cp.stem:<30} {processed:<12} {age_str:<15}')
    except: pass
"
```

### 2. View Specific Checkpoint

```bash
cat data/checkpoints/{source}_{jurisdiction}.json | python3 -m json.tool
```

### 3. Reset Checkpoint

**WARNING:** Resetting causes full re-ingestion from source.

```bash
# Backup current checkpoint first
cp data/checkpoints/{checkpoint_file}.json \
   data/checkpoints/{checkpoint_file}.json.bak

# Remove to reset
rm data/checkpoints/{checkpoint_file}.json
```

### 4. Reset All Checkpoints for Jurisdiction

```bash
JURISDICTION="city-san-rafael"
mkdir -p data/checkpoints/backup_$(date +%Y%m%d)
mv data/checkpoints/*${JURISDICTION}*.json data/checkpoints/backup_$(date +%Y%m%d)/
```

## Checkpoint Sources

| Source | Checkpoint File | Tracks |
|--------|-----------------|--------|
| Meeting discovery | `city-{jurisdiction}.json` | Last meeting datetime |
| Audio download | `audio_{jurisdiction}.json` | Last video ID processed |
| Transcription | `transcribe_{jurisdiction}.json` | Last video transcribed |
| Agenda extraction | `agenda_{jurisdiction}.json` | Last agenda processed |
| YouTube discovery | `youtube_{jurisdiction}.json` | Last video discovered |

## When to Reset

**Reset when:**
- Source data has been corrected upstream
- Previous run had systematic errors
- Schema changes require re-extraction
- Testing full pipeline

**Don't reset when:**
- Adding new data (incremental will handle it)
- Fixing a single record (manual fix preferred)
- Recovering from transient failures (retry instead)

## Checkpoint vs Backup

| Concern | Tool | Purpose |
|---------|------|---------|
| Resume interrupted work | `/checkpoint` | Track progress position |
| Recover lost data | `/db-backup` | Restore database state |
| Audit what ran | Manifests | Track run history |

## Checkpoint Safety

Checkpoints are saved after each batch. If interrupted:
1. Data up to checkpoint is committed to database
2. Resume will skip already-processed items
3. No duplicate records created (upsert semantics)
