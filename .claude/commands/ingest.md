# Ingest

Orchestrate data ingestion pipeline with proper safeguards.

## Usage

```
/ingest [source] [options]
```

**Sources:**
- `transcripts` - Full transcript pipeline (audio → transcribe → vectors)
- `meetings` - Meeting discovery and extraction
- `agendas` - Agenda PDF extraction
- `issues` - SeeClickFix/311 issues
- `legislation` - State/federal bills

## Examples

```
/ingest transcripts --jurisdiction city-san-rafael --limit 10
/ingest meetings --jurisdiction city-san-rafael
/ingest agendas --jurisdiction city-san-rafael --dry-run
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    4-Stage ETL Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stage 1: DISCOVER                                               │
│  └─ Query source APIs for available data                        │
│  └─ Check what's new since last checkpoint                      │
│                                                                  │
│  Stage 2: INGEST                                                 │
│  └─ Fetch & normalize data                                       │
│  └─ Validate against schema                                      │
│  └─ Save checkpoint after each batch                            │
│                                                                  │
│  Stage 3: STORE                                                  │
│  └─ Persist to PostgreSQL via StorageBackend                    │
│  └─ Temporal versioning (valid_from/valid_to)                   │
│  └─ Content hashing for integrity                               │
│                                                                  │
│  Stage 4: INDEX                                                  │
│  └─ Build vector embeddings (on Modal GPU)                      │
│  └─ Store in pgvector                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Critical invariant:** Data MUST be stored (Stage 3) BEFORE indexing (Stage 4). Index reads from storage, not memory.

## Pre-Ingestion Checklist

Before running any ingestion:

1. **Check checkpoint status**
   ```bash
   /checkpoint status {jurisdiction}
   ```

2. **Backup critical data** (if modifying existing)
   ```bash
   /db-backup create --label pre-ingest
   ```

3. **Verify storage space**
   ```bash
   /db-backup status
   ```

## Transcript Pipeline

Full pipeline for meeting transcripts:

### Step 1: Download Audio (Local with Cookies)

```bash
# Requires YouTube cookies for bot detection bypass
/ingest-audio {jurisdiction} {limit}
```

### Step 2: Transcribe + Store (Modal)

```bash
modal run scripts/modal_ingest.py::extract_transcripts \
  --jurisdiction {jurisdiction} \
  --meeting-type planning_commission \
  --limit 10
```

### Step 3: Index Vectors (Modal)

```bash
modal run scripts/modal_vectors.py \
  --corpus transcripts \
  --jurisdiction {jurisdiction}
```

### Step 4: Verify

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM transcripts WHERE jurisdiction_id = %s', ('{jurisdiction}',))
print(f'Transcripts: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM vector_embeddings WHERE jurisdiction_id = %s AND corpus_type = %s', ('{jurisdiction}', 'transcripts'))
print(f'Transcript vectors: {cur.fetchone()[0]}')
"
```

## Meeting Pipeline

```bash
# Discover meetings from ProudCity/Legistar
source civicos-env/bin/activate && civic-extract discover \
  --jurisdiction {jurisdiction}

# Extract agenda items
civic-extract agenda --jurisdiction {jurisdiction}

# Extract decisions
civic-extract decisions --jurisdiction {jurisdiction}
```

## Legislation Pipeline

```bash
# Bulk ingest legislation from LegiScan with leverage point enrichment
civic-extract legislative --state california --bulk --cloud --enrich

# Or run enrichment separately (backfill existing bills)
civic-extract enrich-leverage --state CA
civic-extract enrich-leverage --state US

# Check coverage
civic-extract enrich-leverage --state CA --stats
```

Pipeline stages for legislation:
1. **Discover/Ingest**: LegiScan API fetches bills
2. **Store**: `store_legislation()` persists to PostgreSQL
3. **Enrich** (Stage 3.5): AI generates leverage points for actionable bills
4. **Index**: Vector embeddings for semantic search

## Issues Pipeline (SeeClickFix)

```bash
civic-extract seeclickfix --jurisdiction {jurisdiction}
```

## Cost Tracking

All ETL operations log costs to the `etl_costs` table:

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('''
SELECT operation_type, SUM(cost_usd), COUNT(*)
FROM etl_costs
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY operation_type
ORDER BY SUM(cost_usd) DESC
''')
for row in cur.fetchall():
    print(f'{row[0]}: \${row[1]:.2f} ({row[2]} runs)')
"
```

## Error Recovery

### Pipeline Interrupted Mid-Run

1. Check checkpoint: `/checkpoint status {jurisdiction}`
2. Resume automatically - pipeline continues from checkpoint
3. If checkpoint corrupted: `/checkpoint reset {jurisdiction}`

### Data Integrity Error

1. Check hashes: Query `content_hash` column
2. Soft delete bad records
3. Re-run ingestion for affected items

### Storage Full

1. Check database size: `/db-backup status`
2. Consider archiving old vectors (regenerable)
3. Upgrade Supabase plan if needed

## Safeguards

| Safeguard | Implementation |
|-----------|----------------|
| **Resumability** | Checkpoints saved after each batch |
| **Idempotency** | Upsert semantics prevent duplicates |
| **Versioning** | Temporal tables track all changes |
| **Integrity** | Content hashing detects corruption |
| **Soft deletes** | Data recoverable after delete |
| **Audit trail** | Manifests log each run |
