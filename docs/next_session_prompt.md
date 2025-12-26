# Session 363: Fix Vector-SQL Sync Visualization in ERD

## Context
Session 362 added vector collection nodes to the Data Browser ERD. However, the current implementation has **accuracy issues** - the numbers are misleading and imply relationships that don't exist.

## The Core Problem

The ERD shows dashed lines connecting SQL tables to vector collections, implying a sync relationship. But:

| SQL Table | Records | Vector Collection | Docs | **Actual Relationship** |
|-----------|---------|-------------------|------|-------------------------|
| decisions | 0 | decisions | 186 | **NONE** - vectors from corpus JSON file |
| agenda_items | 0 | chunks | 724 | **NONE** - vectors from corpus JSON file |
| issues | 5 | issues | 0 | **NONE** - not indexed yet |
| meetings | 17 | transcripts | 0 | **NONE** - not indexed yet |

The vector embeddings were loaded from `data/pilot/rag_corpus/city-san-rafael/*.json` files on Dec 15th, completely independent of the SQL tables.

## What's Wrong

1. **Misleading lines** - Dashed connections imply SQL→Vector relationship that doesn't exist
2. **Confusing numbers** - "724 docs from nov17 chunks" doesn't explain the data lineage
3. **No way to verify** - Can't click to inspect what's actually in the vector store
4. **No true cardinality** - Should show "0 SQL records have embeddings" not fake coverage

## What Needs to Be Built

### 1. Investigate Actual Data Model
```python
from civic._internal.meetings.embeddings import CivicEmbeddings
embedder = CivicEmbeddings('city-san-rafael')
collection = embedder._client.get_collection('city-san-rafael_decisions')
sample = collection.peek(5)  # See document IDs and metadata
```
Questions to answer:
- What's the `document_id` format? Can it link to SQL IDs?
- What metadata is stored per document?
- Is there any FK-like relationship possible?

### 2. Fix the Visual Model
Options:
- **A**: Only draw lines when actual linkage exists
- **B**: Use different line styles (solid=linked, dotted=derived)
- **C**: Remove lines entirely, show vector collections as standalone

### 3. Add Click-to-Inspect for Vector Nodes
When clicking a vector node, show a panel with:
- Collection metadata (created_at, source file, embedding model)
- Sample documents with their IDs and metadata
- Document count and storage info

### 4. Show Accurate Sync Status
If SQL↔Vector linkage exists:
- "186/200 synced (93%)"
- "14 records missing embeddings"

If no linkage:
- "186 docs from corpus file"
- "Source: city-san-rafael_decisions.json"

## Files to Modify

**Backend** (`packages/civic-services/src/civic_services/servers/civic_api_integrated.py`):
- `serve_vector_stats()` at line ~8000 - Add document sample endpoint
- New endpoint: `GET /api/admin/vector-stats/{collection}/sample`

**Frontend** (`apps/civic-workspace/src/components/shared/`):
- `ERDDiagram.vue` - Fix visual model, add click handlers
- `DataBrowserWidget.vue` - Add vector detail panel
- New component: `VectorCollectionDetail.vue`

**Data locations**:
- SQL: `data/civic_state.db`
- Vectors: `data/pilot/vectors/city-san-rafael/chroma.sqlite3`
- Corpus: `data/pilot/rag_corpus/city-san-rafael/*.json`

## Session Goal

Make the ERD vector visualization **accurate and trustworthy**:
1. Show real relationships, not implied ones
2. Make vector data inspectable via click
3. Display honest sync status or "no linkage" clearly

## Current State
- Frontend: http://localhost:5173
- API: http://localhost:8001
- ERD has vector nodes with neutral gray FK lines and green vector lines
- Numbers displayed are accurate but relationship lines are misleading
