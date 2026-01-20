# Vector Indexing

Index documents into pgvector for semantic search. **Always use Modal for GPU-accelerated compute.**

## Usage

```
/vectors [action] [options]
```

**Actions:**
- `index [corpus]` - Index corpus to pgvector (default: incremental)
- `index [corpus] --reindex` - Full rebuild (deletes existing first)
- `status` - Show vector index statistics
- `verify` - Check sync between SQL and vectors

## Examples

```
/vectors status                              # Show all corpus stats
/vectors index transcripts                   # Incremental index
/vectors index transcripts --reindex         # Full rebuild
/vectors index chunks --parallel 4           # Parallelize large corpus
/vectors index all                           # Index all corpus types
/vectors verify                              # Check sync status
```

## CRITICAL RULES

1. **NEVER run locally** - Local CPU is 100x slower than Modal GPU
   ```bash
   # WRONG - hours on CPU
   civic-extract vectors --corpus transcripts

   # CORRECT - minutes on GPU
   modal run scripts/modal_vectors.py --corpus transcripts
   ```

2. **Backup before --reindex** - Reindex deletes existing vectors first
   ```bash
   /db-backup create --label pre-reindex
   ```

3. **Prefer incremental** - Only use `--reindex` when:
   - Embedding model changed
   - Schema corruption detected
   - Source data was corrected

## Steps

### 1. Check Current Status

```bash
modal run scripts/modal_vectors.py --stats-only
```

Or locally (read-only, fast):
```bash
source civicos-env/bin/activate && civic-extract vectors \
  --jurisdiction city-san-rafael --stats
```

### 2. Incremental Index (Add New Only)

```bash
modal run scripts/modal_vectors.py \
  --corpus transcripts \
  --jurisdiction city-san-rafael
```

### 3. Full Reindex (Rebuild)

```bash
# Backup first!
/db-backup create --label pre-reindex

modal run scripts/modal_vectors.py \
  --corpus transcripts \
  --jurisdiction city-san-rafael \
  --reindex
```

### 4. Parallel Index (Large Corpora)

```bash
modal run scripts/modal_vectors.py \
  --corpus municipal_code \
  --jurisdiction city-san-rafael \
  --parallel 4
```

### 5. Index All Corpora

```bash
modal run scripts/modal_vectors.py --corpus all
```

## Corpus Types

| Corpus | Source Table | Enables |
|--------|--------------|---------|
| `transcripts` | transcripts | `what_was_said()`, testimony search |
| `chunks` | chunks | PDF/agenda content search |
| `decisions` | decisions | `what_happened()` semantic search |
| `meetings` | meetings | Meeting search |
| `municipal_code` | municipal_code | Local law search |
| `issues` | issues | `whos_with_me()` matching |
| `legislation` | legislation | Bill search |

## Modal Configuration

The Modal function uses:
- **GPU:** T4 (sufficient for embeddings)
- **Memory:** 64 GB
- **Model:** `nomic-ai/nomic-embed-text-v1.5` (768 dimensions)
- **Batch size:** 500 documents
- **Insert method:** COPY (bulk) for reindex, upsert for incremental

## Insert Methods

| Method | Speed | When Used |
|--------|-------|-----------|
| **COPY** | 10x faster | `--reindex` (table cleared first) |
| **Upsert** | Slower but safe | Incremental (preserves existing) |

## Troubleshooting

### "Already fully indexed" but data missing

Known bug: indexer compares vector count vs row count incorrectly for expanded corpora (transcripts → utterances).

**Workaround:**
```bash
/db-backup create --label pre-reindex
modal run scripts/modal_vectors.py --corpus transcripts --reindex
```

### Index taking too long

1. Check you're using Modal (not local)
2. Use `--parallel` for large corpora
3. Check Modal dashboard for errors

### Vectors out of sync

```bash
# Verify sync
civic-extract vectors --jurisdiction city-san-rafael --verify-sync

# If mismatched, reindex
modal run scripts/modal_vectors.py --corpus {corpus} --reindex
```

## Cost

- **Modal compute:** ~$0.01 per 1,000 embeddings
- **Embedding model:** Local (free, included in Modal image)
- **Storage:** Included in Supabase

## Pipeline Integration

Vector indexing is typically the final stage after data ingestion:

```
Source API → Ingest → Store → **Index Vectors**
```

After transcript ingestion:
```bash
modal run scripts/modal_ingest.py::extract_transcripts ...
modal run scripts/modal_vectors.py --corpus transcripts
```
