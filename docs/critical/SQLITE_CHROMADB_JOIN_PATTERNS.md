# SQLite-ChromaDB Join Patterns

This document specifies the ID patterns and join strategies enabling correlation between Civic's relational (SQLite) and vector (ChromaDB) data stores.

## Overview

Civic uses a dual-storage architecture:
- **SQLite** (`civic_state.db`): Relational data (meetings, agenda items, issues, initiatives)
- **ChromaDB** (`vectors/{jurisdiction_id}/`): Vector embeddings for semantic search

Documents in ChromaDB can be joined with SQLite records using carefully structured IDs and metadata.

---

## ID Patterns by Corpus Type

### 1. Decisions

| Property | Value |
|----------|-------|
| **Collection** | `{jurisdiction_id}_decisions` |
| **ID Format** | `{YYYYMMDD}-item-{agenda_item}` |
| **Example** | `20251117-item-6a` |
| **Source** | `decision.py:289` |

**Generation Logic** (decision.py:287-289):
```python
date_part = meeting_date.replace("-", "")  # "2025-11-17" → "20251117"
item_part = item_number.replace(".", "-")  # "6.a" → "6-a"
decision_id = f"{date_part}-item-{item_part}"
```

**SQLite Join Strategy**:
```sql
-- ChromaDB decision_id: "20251117-item-6a"
-- SQLite meeting_id format: "{jurisdiction_id}-{YYYY-MM-DD}"

-- Parse date from decision_id
SELECT m.*, a.*
FROM meetings m
JOIN agenda_items a ON a.meeting_id = m.id
WHERE m.id = 'city-san-rafael-2025-11-17'  -- Derive from jurisdiction + date
  AND a.item_number = '6.a'                 -- Derive from item part
  AND m.valid_to IS NULL;                   -- Current version only
```

**Metadata Fields for Joining**:
- `meeting_date` (ISO format: "2025-11-17")
- `agenda_item` (e.g., "6.a")

---

### 2. Chunks (PDF Document Chunks)

| Property | Value |
|----------|-------|
| **Collection** | `{jurisdiction_id}_chunks` |
| **ID Format** | `chunk-{index}` |
| **Example** | `chunk-42` |
| **Source** | `embeddings.py:675` |

**Generation Logic** (embeddings.py:675):
```python
ids = [f"chunk-{i + j}" for j in range(len(batch))]  # Positional within batch
```

**SQLite Join Strategy**:
Chunks use **metadata-based correlation** rather than direct ID joins:

```sql
-- No direct ID join possible; use metadata fields
-- ChromaDB metadata: agenda_item="6.a", agenda_title="..."

-- Correlate via agenda_item metadata
SELECT a.*
FROM agenda_items a
JOIN meetings m ON a.meeting_id = m.id
WHERE m.jurisdiction_id = 'city-san-rafael'
  AND a.item_number = '6.a'  -- From chunk metadata
  AND m.valid_to IS NULL;
```

**Metadata Fields for Joining**:
- `agenda_item` (e.g., "6.a")
- `page_start`, `page_end` (source document location)
- `chunk_index` (position in sequence)

**Note**: Chunk IDs are positional (batch index), not globally unique. For cross-corpus linkage, use the `agenda_item` metadata field.

---

### 3. Transcripts (Video Meeting Transcripts)

| Property | Value |
|----------|-------|
| **Collection** | `{jurisdiction_id}_transcripts` |
| **ID Format** | `transcript-{video_id}-{chunk_index}` |
| **Example** | `transcript-ABC123xyz-42` |
| **Source** | `embeddings.py:777` |

**Generation Logic** (embeddings.py:777):
```python
ids = [f"transcript-{video_id}-{chunk.chunk_index}" for chunk in batch]
```

**SQLite Join Strategy**:
```sql
-- ChromaDB transcript_id: "transcript-ABC123xyz-42"
-- Extract video_id from ID or use metadata

-- Join via meeting video_url
SELECT m.*, a.*
FROM meetings m
LEFT JOIN agenda_items a ON a.meeting_id = m.id
WHERE m.video_url LIKE '%ABC123xyz%'  -- YouTube video ID
  AND m.valid_to IS NULL;
```

**Metadata Fields for Joining**:
- `video_id` (YouTube video ID)
- `meeting_date` (ISO format, if provided during indexing)
- `agenda_item` (if detected during processing)
- `speaker`, `speaker_role`, `speaker_name`
- `start_ms`, `end_ms` (video timestamps)

**Video Timestamp URL Generation** (history.py:117-122):
```python
youtube_url = f"https://www.youtube.com/watch?v={video_id}&t={start_seconds}s"
```

---

### 4. Issues (SeeClickFix Reports)

| Property | Value |
|----------|-------|
| **Collection** | `{jurisdiction_id}_issues` |
| **ID Format** | `{jurisdiction_id}-scf-{source_id}` |
| **Example** | `city-san-rafael-scf-20575290` |
| **Source** | `embeddings.py:1611-1622` |

**Generation Logic** (embeddings.py:1611-1622):
```python
def _issue_to_id(self, issue: Dict) -> str:
    source_id = issue.get("source_id", issue.get("id", "unknown"))
    if isinstance(source_id, str) and source_id.startswith("scf-"):
        source_id = source_id[4:]
    return f"{self.jurisdiction_id}-scf-{source_id}"
```

**SQLite Join Strategy**:
```sql
-- ChromaDB issue_id: "city-san-rafael-scf-20575290"
-- SQLite issues.id uses same format

-- Direct ID join (most reliable pattern)
SELECT i.*
FROM issues i
WHERE i.id = 'city-san-rafael-scf-20575290'
  AND i.valid_to IS NULL;

-- Or via source_id
SELECT i.*
FROM issues i
WHERE i.jurisdiction_id = 'city-san-rafael'
  AND i.source_id = '20575290'
  AND i.valid_to IS NULL;
```

**Metadata Fields for Joining**:
- `issue_id` (full ID, matches SQLite `issues.id`)
- `source_id` (numeric SeeClickFix ID)
- `latitude`, `longitude` (for geo queries)
- `status` (open/acknowledged/closed)

**Note**: Issues have the **most reliable** SQLite join pattern because the ChromaDB document ID directly matches the SQLite primary key.

---

### 5. Municipal Code (Future)

| Property | Value |
|----------|-------|
| **Collection** | `{jurisdiction_id}_municipal_code` |
| **ID Format** | `{jurisdiction_id}-muni-{chapter}-{section}` |
| **Example** | `city-san-rafael-muni-19-02-050` |
| **Source** | VECTOR_RAG_SCHEMA.md:268-277 |

**SQLite Join Strategy** (planned):
```sql
-- ChromaDB muni_code_id: "city-san-rafael-muni-19-02-050"
-- Future table: code_sections

SELECT cs.*
FROM code_sections cs
WHERE cs.id = 'city-san-rafael-muni-19-02-050';
```

**Metadata Fields for Joining**:
- `chapter`, `section`
- `chapter_title`, `section_title`
- `effective_date`, `amended_date`
- `related_statutes` (CSV of state law references)

---

## Cross-Corpus Join Patterns

### Decision → Transcript Linkage

Link decisions with corresponding video testimony:

```sql
-- Given a decision_id "20251117-item-6a"
-- Find transcript chunks for the same agenda item

-- Step 1: Extract meeting date from decision_id
-- date = "2025-11-17" (from "20251117")

-- Step 2: Query transcripts collection with filters
-- ChromaDB query:
--   where: {"meeting_date": "2025-11-17", "agenda_item": "6a"}
```

**Python Implementation**:
```python
# Find transcripts for a specific decision
results = embeddings.search_transcripts(
    query="",  # Can be empty for pure filter
    where={"meeting_date": "2025-11-17", "agenda_item": "6a"}
)
```

### Decision → Chunk Linkage

Link decisions with source PDF chunks:

```python
# Find PDF chunks for a specific agenda item
results = embeddings.search_chunks(
    query="housing development",
    where={"agenda_item": "6.a"}
)
```

### Hybrid Search (PDF + Video)

Search across both PDF chunks and transcripts simultaneously:

```python
# embeddings.py:1380-1460
results = embeddings.search_hybrid_pdf_video(
    query="affordable housing requirements",
    agenda_item="6.a",  # Optional filter
    top_k=10
)
# Returns interleaved results sorted by relevance score
```

---

## SQLite Schema Reference

### meetings Table
```sql
CREATE TABLE meetings (
    id TEXT NOT NULL,              -- "{jurisdiction_id}-{YYYY-MM-DD}"
    jurisdiction_id TEXT NOT NULL,
    meeting_datetime TIMESTAMP NOT NULL,
    video_url TEXT,                -- Contains YouTube video ID
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,            -- NULL = current version
    PRIMARY KEY (id, valid_from)
);
```

### agenda_items Table
```sql
CREATE TABLE agenda_items (
    id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,      -- FK to meetings.id
    item_number TEXT,              -- "6.a", "4", etc.
    title TEXT NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP,
    PRIMARY KEY (id, valid_from)
);
```

### issues Table
```sql
CREATE TABLE issues (
    id TEXT PRIMARY KEY,           -- "{jurisdiction_id}-scf-{source_id}"
    jurisdiction_id TEXT NOT NULL,
    source TEXT NOT NULL,          -- "seeclickfix"
    source_id TEXT,                -- Numeric SeeClickFix ID
    latitude REAL,
    longitude REAL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP
);
```

---

## Implementation Notes

### Design vs. Actual ID Formats

The VECTOR_RAG_SCHEMA.md documents **target** ID formats that differ from current implementation:

| Corpus | Documented Format | Actual Format |
|--------|-------------------|---------------|
| Decisions | `city-san-rafael-2025-11-17-6a` | `20251117-item-6a` |
| Chunks | `city-san-rafael-2025-11-17-chunk-042` | `chunk-42` |

The actual formats work but require metadata-based joins rather than pure ID parsing.

### ChromaDB Type Restrictions

ChromaDB metadata supports only flat types:
- `str`, `int`, `float`, `bool`
- No nested objects or arrays
- Arrays stored as comma-separated strings (e.g., `"housing,zoning,traffic"`)

### Temporal Queries

SQLite uses temporal versioning (`valid_from`, `valid_to`). Always filter for current records:

```sql
WHERE valid_to IS NULL  -- Current version only
```

---

## Code Locations

| Component | File | Key Lines |
|-----------|------|-----------|
| Decision ID generation | `decision.py` | 287-289 |
| Chunk ID generation | `embeddings.py` | 675 |
| Transcript ID generation | `embeddings.py` | 777 |
| Issue ID generation | `embeddings.py` | 1611-1622 |
| Decision metadata | `embeddings.py` | 1556-1598 |
| Chunk metadata | `embeddings.py` | 1600-1609 |
| Transcript metadata | `embeddings.py` | 796-849 |
| Issue metadata | `embeddings.py` | 1652-1685 |
| SQLite schema | `manager.py` | 77-200 |
| Hybrid search | `embeddings.py` | 1380-1460 |
| UnifiedSearchResult | `history.py` | 47-229 |

---

*Created: Session 277 (2025-12-15)*
*Related: VECTOR_RAG_SCHEMA.md (full schema reference)*
