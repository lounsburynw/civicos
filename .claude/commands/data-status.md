# Data Status

View schema-aware data status for a jurisdiction, showing corpus counts, vector coverage, and gaps.

## Usage

```
/data-status [jurisdiction] [options]
```

**Arguments:**
- `jurisdiction` - Target jurisdiction (default: city-san-rafael)

**Options:**
- `--gaps` - Show only corpora with gaps
- `--json` - Output as JSON for programmatic use

## Examples

```
/data-status                           # Status for city-san-rafael
/data-status city-san-rafael           # Explicit jurisdiction
/data-status --gaps                    # Show only gaps
/data-status --json                    # JSON output
```

## What This Shows

| Column | Description |
|--------|-------------|
| **Corpus** | Data type (decisions, transcripts, issues, etc.) |
| **Storage** | Documents in SQL database |
| **Indexed** | Documents with vector embeddings |
| **Gap** | Difference (negative = expanded, positive = needs indexing) |
| **Coverage** | Percent of storage docs indexed |

### Understanding Gaps

- **Positive gap** (e.g., issues: 26): Documents need vector indexing
- **Negative gap** (e.g., transcripts: -4579): Expected - documents expanded into multiple embeddings
- **Zero gap**: Fully indexed

### Expanded Corpora

Some corpus types produce multiple embeddings per document:
- **Transcripts**: Split into speaker turns/utterances
- **Municipal Code**: Chunked into smaller sections
- **Legislation**: Split by section

## Steps

### 1. Show Data Status (Default)

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()

from civic import Civic, DataStatus, format_data_status

jurisdiction = '$1' if '$1' else 'city-san-rafael'
c = Civic(jurisdiction)

status = DataStatus(c._storage, c._vectors, jurisdiction)
report = status.summary()
print(format_data_status(report))
"
```

### 2. Show Gaps Only

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()

from civic import Civic, DataStatus

jurisdiction = '$1' if '$1' else 'city-san-rafael'
c = Civic(jurisdiction)

status = DataStatus(c._storage, c._vectors, jurisdiction)
gaps = status.gaps()

if gaps:
    print('Corpora with gaps:')
    print(f'{\"Corpus\":<20} {\"Storage\":>10} {\"Indexed\":>10} {\"Gap\":>10}')
    print('-' * 54)
    for corpus, info in sorted(gaps.items(), key=lambda x: abs(x[1]['gap']), reverse=True):
        print(f'{corpus:<20} {info[\"storage\"]:>10} {info[\"indexed\"]:>10} {info[\"gap\"]:>10}')
else:
    print('No gaps - all corpora are fully indexed!')
"
```

### 3. JSON Output

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()
import json

from civic import Civic, DataStatus

jurisdiction = '$1' if '$1' else 'city-san-rafael'
c = Civic(jurisdiction)

status = DataStatus(c._storage, c._vectors, jurisdiction)
report = status.summary()
print(json.dumps(report.to_dict(), indent=2, default=str))
"
```

## Schema Reference

The diagnostics module uses `CORPUS_REGISTRY` for authoritative schema mappings:

| Corpus | SQL Table | ID Column | Date Column |
|--------|-----------|-----------|-------------|
| meetings | meetings | id | meeting_datetime |
| decisions | decisions | id | meeting_date |
| chunks | chunks | id | (via meeting_id) |
| transcripts | transcripts | id | (via video_id) |
| issues | issues | id | created_at |

**Common mistakes avoided:**
- `meeting_date` vs `meeting_datetime` (depends on table)
- `content_id` vs `meeting_id` (chunks use meeting_id)
- `embeddings` table doesn't exist (use `vector_embeddings` for pgvector)

## Related Commands

| Command | Purpose |
|---------|---------|
| `/vector-coverage` | Detailed vector index coverage |
| `/checkpoint` | Ingestion checkpoint status |
| `/db-backup` | Database backup operations |
