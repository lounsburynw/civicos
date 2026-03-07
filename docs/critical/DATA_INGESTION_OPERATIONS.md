# Data Ingestion Operations

> **Claude Code:** Run `/ingest` to orchestrate the data ingestion pipeline, `/data-status` for corpus counts and gaps, `/checkpoint` to manage resumable pipeline state, and `/ingest-audio` for YouTube audio downloads.

Operator manual for ingesting, refreshing, and managing Civic data.

## Overview

Civic manages three categories of data:

| Category | Storage | Update Frequency | Versioning |
|----------|---------|------------------|------------|
| **Meeting data** | SQLite (`civic_state.db`) | Weekly | Temporal (valid_from/valid_to) |
| **Vector indexes** | ChromaDB | On corpus change | Manifest-based |
| **User data** | SQLite (`civic_participation.db`) | Continuous | Append-only |

### Data Flow

```
Source APIs (Legistar, CivicClerk, YouTube)
    ↓
Extraction (civicos-extraction package)
    ↓
Storage (StateManager → SQLite)
    ↓
Embedding (CivicEmbeddings → ChromaDB)
    ↓
Query (Civic API)
```

---

## Initial Ingestion

### 1. Meeting Data (SQLite)

```bash
# Ensure schema is current
python scripts/migrate.py --status
python scripts/migrate.py
```

```python
from civic_extraction import LegistarClient  # or CivicClerkClient
from civic._internal.state import StateManager

# Extract meetings from source
client = LegistarClient("san-rafael")
meetings = client.get_meetings(days_ahead=90, days_past=365)

# Store in SQLite with temporal versioning
state = StateManager("data/civic_state.db")
state.update_meetings("city-san-rafael", [m.to_dict() for m in meetings])

print(f"Loaded {len(meetings)} meetings")
```

### 2. Vector Indexes (ChromaDB)

```bash
# Create directory structure
mkdir -p data/pilot/rag_corpus/city-san-rafael
mkdir -p data/pilot/vectors/city-san-rafael
```

```python
from civic._internal.meetings.embeddings import CivicEmbeddings, load_video_meeting_map

# Initialize embedder
embedder = CivicEmbeddings(
    jurisdiction_id="city-san-rafael",
    persist_directory="data/pilot/vectors/city-san-rafael"
)

# Build each corpus type as needed:

# Decisions (from extracted decisions JSON)
embedder.build_decisions_index("data/pilot/rag_corpus/city-san-rafael/decisions.json")

# PDF chunks (agendas, staff reports, minutes)
embedder.build_chunks_index("data/pilot/rag_corpus/city-san-rafael")

# Transcripts (from testimony JSON files)
video_map = load_video_meeting_map("data/pilot/san_rafael_12month_manifest.json")
embedder.build_transcripts_index(
    "data/testimony",
    detect_agenda_items=True,
    video_meeting_map=video_map
)
```

### 3. Manifest File

Create a manifest to track what's been ingested:

```json
{
  "jurisdiction_id": "city-san-rafael",
  "last_updated": "2025-12-16T10:30:00Z",
  "corpora": {
    "meetings": {
      "source": "legistar",
      "count": 52,
      "date_range": ["2024-01-01", "2025-01-15"],
      "last_ingested": "2025-12-16T10:30:00Z"
    },
    "decisions": {
      "count": 847,
      "embedding_model": "nomic-embed-text-v1.5",
      "last_indexed": "2025-12-16T10:35:00Z"
    },
    "transcripts": {
      "count": 7750,
      "embedding_model": "nomic-embed-text-v1.5",
      "with_meeting_date": 3839,
      "with_agenda_item": 7188,
      "last_indexed": "2025-12-16T11:00:00Z"
    }
  }
}
```

Save as `data/pilot/rag_corpus/city-san-rafael/ingestion_manifest.json`.

---

## Ongoing Refresh

### Weekly Meeting Refresh

```python
from civic_extraction import LegistarClient
from civic._internal.state import StateManager
from datetime import datetime

client = LegistarClient("san-rafael")
state = StateManager("data/civic_state.db")

# Fetch recent + upcoming meetings
meetings = client.get_meetings(days_ahead=30, days_past=7)

# StateManager handles temporal versioning automatically
# - New meetings: inserted with valid_from=now
# - Changed meetings: old version gets valid_to=now, new version inserted
# - Unchanged meetings: no action
state.update_meetings("city-san-rafael", [m.to_dict() for m in meetings])

# Update manifest
manifest["corpora"]["meetings"]["last_ingested"] = datetime.now().isoformat()
```

### When to Re-index Vectors

Re-index when:
- New documents added to corpus (agendas, transcripts)
- Embedding model upgraded
- Schema/metadata requirements change

```python
# Full re-index (replaces existing collection)
embedder.build_decisions_index("data/pilot/rag_corpus/city-san-rafael/decisions.json")

# Update manifest after re-indexing
manifest["corpora"]["decisions"]["last_indexed"] = datetime.now().isoformat()
```

### Incremental vs Full Re-index

| Scenario | Approach |
|----------|----------|
| New meeting added | Append to decisions.json, full re-index |
| Transcript added | Add to testimony/, full re-index transcripts |
| Embedding model change | Full re-index all corpora |
| Metadata schema change | Full re-index affected corpus |

**Note:** ChromaDB collections are rebuilt from scratch (no incremental add). This is intentional for consistency.

---

## Versioning Strategy

### Code Versioning

See `VERSIONING_STRATEGY.md`. Format: `v{major}.{minor}.{patch}-pilot-{YYYYMMDD}`

### Data Versioning

Data versions are tracked via:

1. **SQLite temporal tables** - `valid_from`/`valid_to` columns enable point-in-time queries
2. **Manifest files** - Track corpus state and last update timestamps
3. **ChromaDB collection metadata** - Stores embedding model and creation date

```python
# Query meeting state at a specific point in time
state.get_meetings("city-san-rafael", as_of="2025-01-01")

# Check collection metadata
collection = embedder._client.get_collection("city-san-rafael_decisions")
print(collection.metadata)
# {'embedding_model': 'nomic-embed-text-v1.5', 'created_at': '2025-12-16T10:35:00'}
```

### Version Compatibility

| Component | Version Source | Compatibility Check |
|-----------|---------------|---------------------|
| SQLite schema | `schema_versions` table | `migrate.py --status` |
| ChromaDB collections | Collection metadata | Check `embedding_dimension` matches model |
| Embedding model | `CivicEmbeddings.model_name` | Must match collection metadata |

---

## Rollback Procedures

### SQLite Data Rollback

```bash
# List available backups
ls -la data/backups/

# Restore from backup (creates pre-restore backup first)
python scripts/backup.py --restore data/backups/civic_state_20251215_120000.db.gz
```

### SQLite Schema Rollback

```bash
# Check current migration state
python scripts/migrate.py --status

# Rollback last migration (if down migration exists)
python scripts/migrate.py --down
```

### Vector Index Rollback

ChromaDB collections are rebuilt, not migrated. To rollback:

1. Delete current collection
2. Re-index from previous corpus version

```python
# Delete and rebuild from known-good corpus
embedder._client.delete_collection("city-san-rafael_decisions")
embedder.build_decisions_index("data/backups/decisions_20251215.json")
```

**Best practice:** Before re-indexing, backup your corpus files:
```bash
cp data/pilot/rag_corpus/city-san-rafael/decisions.json \
   data/backups/decisions_$(date +%Y%m%d).json
```

---

## Verification

### Check Meeting Data

```python
from civic._internal.state import StateManager

state = StateManager("data/civic_state.db")
meetings = state.get_meetings("city-san-rafael")
print(f"Meetings: {len(meetings)}")

# Check date range
dates = [m['meeting_date'] for m in meetings]
print(f"Range: {min(dates)} to {max(dates)}")
```

### Check Vector Indexes

```python
from civic._internal.meetings.embeddings import CivicEmbeddings

embedder = CivicEmbeddings(
    jurisdiction_id="city-san-rafael",
    persist_directory="data/pilot/vectors/city-san-rafael"
)

# List collections and counts
for name in ["decisions", "chunks", "transcripts"]:
    try:
        coll = embedder._client.get_collection(f"city-san-rafael_{name}")
        print(f"{name}: {coll.count()} vectors")
    except:
        print(f"{name}: not found")
```

### Verify Metadata Coverage

```python
import chromadb

client = chromadb.PersistentClient(path="data/pilot/vectors/city-san-rafael")
coll = client.get_collection("city-san-rafael_transcripts")

# Sample metadata
data = coll.get(limit=100, include=["metadatas"])
has_date = sum(1 for m in data["metadatas"] if m.get("meeting_date"))
has_agenda = sum(1 for m in data["metadatas"] if m.get("agenda_item"))

print(f"meeting_date coverage: {has_date}/100")
print(f"agenda_item coverage: {has_agenda}/100")
```

---

## Troubleshooting

### "Collection not found"

Collection doesn't exist or wrong persist_directory:
```python
# Check what collections exist
client = chromadb.PersistentClient(path="data/pilot/vectors/city-san-rafael")
print([c.name for c in client.list_collections()])
```

### Embedding dimension mismatch

Occurs when model changes but collection wasn't rebuilt:
```python
# Check collection's expected dimension
coll = client.get_collection("city-san-rafael_decisions")
print(coll.metadata.get("embedding_dimension"))  # e.g., 768

# Check current model dimension
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)
print(model.get_sentence_embedding_dimension())  # Must match
```

**Fix:** Delete collection and rebuild with current model.

### Migration checksum mismatch

Migration file was modified after being applied:
```bash
python scripts/migrate.py --status
# Shows checksum mismatch warning

# If intentional edit, update checksum in schema_versions table
# If accidental, restore original migration file from git
```

---

## Automation (Future)

Currently manual. Planned automation in `pilot.json` → `pipeline_automation`:

- `meeting_discovery_cron`: Weekly Legistar fetch
- `youtube_discovery_cron`: Check for new meeting videos
- `transcription_cron`: Process new videos through Whisper
- `embedding_cron`: Re-index when corpus changes
- `freshness_alerts`: Alert if data older than threshold

Until implemented, run refresh procedures manually on a weekly schedule.
