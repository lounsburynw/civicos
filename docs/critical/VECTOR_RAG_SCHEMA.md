# Vector RAG Schema

This document defines the organizing principles, schema, and naming conventions for Civic's vector database and RAG infrastructure.

## Overview

Civic uses vector embeddings to enable semantic search over meeting documents, decisions, and transcripts. The infrastructure is designed to:

1. Support **multi-jurisdiction** deployment (starting with San Rafael pilot, scaling to 26+ cities)
2. Maintain **cost efficiency** (local embeddings meet foundation budget constraints)
3. Integrate with existing **civic-state SQLite** schema (relational data layer)
4. Enable the **what_happened()** query method with semantic understanding

---

## Organizing Principle: Jurisdiction-First

All vector data is organized by **jurisdiction_id** (same identifier used in civic-state SQLite).

### Why Jurisdiction-First?

1. **Alignment with existing schema**: The civic-state manager uses `jurisdiction_id` as the primary key
2. **Multi-tenant isolation**: Each city's data is logically separated
3. **Query scope**: Most queries are scoped to a single jurisdiction
4. **Data sovereignty**: Clear boundaries for data retention/deletion

### Jurisdiction Identifiers

| Format | Example | Notes |
|--------|---------|-------|
| `city-{name}` | `city-san-rafael` | Standard city identifier |
| `county-{name}` | `county-marin` | County-level (future) |
| `state-{abbrev}` | `state-ca` | State-level (legislative context) |

---

## Directory Structure

```
data/
├── civic_state.db           # SQLite (existing relational data)
├── pilot/
│   └── vectors/
│       └── {jurisdiction_id}/
│           ├── chroma.sqlite3       # ChromaDB persistent storage
│           └── {collection_uuid}/   # ChromaDB internal directories
└── production/               # (future production deployment)
    └── vectors/
        └── {jurisdiction_id}/
            └── chroma.sqlite3
```

### Directory Structure (Migrated)

Current structure (jurisdiction naming):
```
data/pilot/vectors/city-san-rafael/    # Vector DB for San Rafael
data/pilot/rag_corpus/city-san-rafael/ # RAG source documents
data/pilot/vectors_test/city-san-rafael/ # Test vector DB (cleaned after tests)
```

---

## ChromaDB Collections

### Collection Naming Convention

Collections follow the pattern: **`{scope}_{corpus_type}`**

| Scope Type | Description | Example |
|------------|-------------|---------|
| Jurisdiction | City/county-specific data | `city-san-rafael_decisions` |
| Shared/Global | Cross-jurisdiction resources | `legal_documents` |

#### Jurisdiction-Scoped Collections (Primary Pattern)

```
{jurisdiction_id}_{corpus_type}

Examples:
- city-san-rafael_decisions   # Meeting decisions
- city-san-rafael_chunks      # Document chunks
- city-san-rafael_transcripts # Video transcripts
- city-berkeley_decisions
- county-marin_decisions
```

#### Shared Collections (State/Regional Resources)

Some corpora are shared across jurisdictions (e.g., California legislation):

```
{corpus_type}                  # For single shared corpus
{scope}_{corpus_type}          # For scoped shared corpus

Examples:
- legal_documents              # California legislative corpus (shared)
- state-ca_bills               # (future: state-scoped pattern)
```

### Collection Registry

| Collection Pattern | Corpus Type | Scope | Purpose | Storage Location |
|-------------------|-------------|-------|---------|------------------|
| `{jurisdiction_id}_decisions` | decisions | Jurisdiction | Structured decision records | `data/pilot/vectors/{jurisdiction_id}/` |
| `{jurisdiction_id}_chunks` | chunks | Jurisdiction | Raw document chunks from PDFs | `data/pilot/vectors/{jurisdiction_id}/` |
| `{jurisdiction_id}_transcripts` | transcripts | Jurisdiction | Video meeting transcripts | `data/pilot/vectors/{jurisdiction_id}/` |
| `legal_documents` | legal | Shared | California legislative corpus | `data/vectors/legal/` |

**Future Collections** (pilot phase):
| Collection Pattern | Corpus Type | Scope | Purpose | Schema Status |
|-------------------|-------------|-------|---------|---------------|
| `{jurisdiction_id}_municipal_code` | municipal_code | Jurisdiction | City municipal code sections | **Defined** (see Municipal Code Documents) |
| `{jurisdiction_id}_issues` | issues | Jurisdiction | SeeClickFix citizen reports | **Defined** (see SeeClickFix Issues Documents) |

### Collection Metadata

Each collection includes metadata for traceability:

```json
{
  "description": "City of San Rafael council decisions for RAG",
  "jurisdiction_id": "city-san-rafael",
  "embedding_model": "nomic-embed-text-v1.5",
  "embedding_dimension": 768,
  "created_at": "2025-12-05T10:00:00Z",
  "source_corpus": "data/pilot/rag_corpus/city-san-rafael",
  "civic_version": "0.1.0"
}
```

---

## Document Schemas

### Decision Documents (decisions collection)

Decision documents are derived from meeting records and represent formal council/board actions.

#### Source Files

- `{jurisdiction_id}_decisions.json` - Extracted from meeting minutes, votes, staff reports

#### Text Representation (for embedding)

Each decision is converted to a searchable text block:

```
Title: {title}
Summary: {summary}
Meeting Date: {meeting_date}
Agenda Item: {agenda_item}
Topics: {topics}
Outcome: {outcome}
Vote: {vote_count}
Department: {department}
Financial Impact: {financial_impact}
Recommendation: {recommendation_snippet}
Public Speakers: {speaker_count}
Legal Instruments: {instrument_types}
```

#### Decision Metadata

ChromaDB metadata fields (all flat types - string, int, float, bool):

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `decision_id` | string | Unique decision identifier | `"city-san-rafael-2025-11-17-6a"` |
| `meeting_date` | string | ISO date of meeting | `"2025-11-17"` |
| `agenda_item` | string | Agenda item number | `"6.a"` |
| `title` | string | Decision title (truncated 500 chars) | `"Declaration of Shelter Crisis..."` |
| `outcome` | string | Decision outcome | `"approved"`, `"denied"`, `"continued"` |
| `topics` | string | Comma-separated topics | `"housing,homelessness,budget"` |
| `vote_passed` | bool | Whether vote passed | `true` |
| `vote_unanimous` | bool | Whether unanimous | `true` |
| `vote_count` | string | Vote tally | `"5-0"` |
| `department` | string | Responsible department | `"City Manager"` |
| `financial_impact` | string | Dollar amount if any | `"$8,000,000"` |
| `speaker_count` | int | Number of public speakers | `78` |

#### Decision ID Format

```
{jurisdiction_id}-{meeting_date}-{agenda_item}

Examples:
- city-san-rafael-2025-11-17-6a
- city-san-rafael-2025-11-17-4f
- city-berkeley-2025-10-15-12b
```

### Chunk Documents (chunks collection)

Chunks are raw text segments from source documents, preserving source context.

#### Source Files

- `{meeting_id}_chunks.json` - Parsed from agenda packets, staff reports, PDFs

#### Chunk Metadata

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `chunk_id` | string | Unique chunk identifier | `"city-san-rafael-2025-11-17-chunk-042"` |
| `meeting_id` | string | Source meeting | `"city-san-rafael-2025-11-17"` |
| `agenda_item` | string | Related agenda item | `"6.a"` |
| `agenda_title` | string | Item title (truncated) | `"Declaration of Shelter..."` |
| `document_type` | string | Source document type | `"agenda_packet"`, `"staff_report"`, `"minutes"` |
| `page_start` | int | Starting page in source | `207` |
| `page_end` | int | Ending page in source | `208` |
| `chunk_index` | int | Position in chunk sequence | `42` |
| `total_chunks` | int | Total chunks from source | `724` |

#### Chunk ID Format

```
{meeting_id}-chunk-{index:03d}

Examples:
- city-san-rafael-2025-11-17-chunk-042
- city-san-rafael-2025-11-17-chunk-530
```

### Municipal Code Documents (municipal_code collection)

Municipal code documents represent city ordinances and regulations, organized hierarchically by chapter and section.

#### Source Files

- Scraped from Municode or local municipal code source
- Organized by chapter/section hierarchy
- `{jurisdiction_id}_municipal_code.json` - Extracted code sections

#### Text Representation (for embedding)

Each code section is converted to a searchable text block:

```
Chapter: {chapter} - {chapter_title}
Section: {section_number}
Title: {section_title}
Full Text: {full_text}
Topics: {topics}
Related Laws: {related_statutes}
Effective Date: {effective_date}
```

#### Municipal Code Metadata

ChromaDB metadata fields (all flat types - string, int, float, bool):

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `muni_code_id` | string | Unique code section identifier | `"city-san-rafael-muni-19-1"` |
| `chapter` | string | Chapter number | `"19"` |
| `section` | string | Section number/identifier | `"19.1"` or `"19.02.050"` |
| `chapter_title` | string | Chapter name (truncated 500 chars) | `"Homeless and Encampments"` |
| `section_title` | string | Section title (truncated 200 chars) | `"Definitions"` |
| `jurisdiction_id` | string | Jurisdiction identifier | `"city-san-rafael"` |
| `topics` | string | Comma-separated relevant topics | `"homelessness,shelter,safety"` |
| `effective_date` | string | ISO date when section became effective | `"2025-11-17"` |
| `amended_date` | string | ISO date of last amendment | `"2025-11-17"` |
| `related_statutes` | string | Comma-separated related state laws | `"Gov Code 8698,8698.4"` |
| `legal_authority` | string | Legal basis for section | `"California Government Code"` |
| `hierarchy_level` | int | Depth in chapter hierarchy (1=chapter, 2=section, 3=subsection) | `2` |

#### Municipal Code ID Format

```
{jurisdiction_id}-muni-{chapter}-{section}

Examples:
- city-san-rafael-muni-19-1       # Chapter 19, Section 1
- city-san-rafael-muni-19-02-050  # Chapter 19, Section 02.050
- city-san-rafael-muni-23-2-5     # Chapter 23, Section 2.5
```

**Rationale**:
- Prefix `muni-` distinguishes from other document types (decisions, chunks)
- Jurisdiction-scoped for multi-tenant isolation
- Hierarchical structure preserves chapter/section relationship
- Enables pattern matching: `city-san-rafael-muni-19-*` for all Chapter 19 sections

#### Key Differences from Decision Schema

| Aspect | Decisions | Municipal Code |
|--------|-----------|-----------------|
| **ID Scope** | Meeting-specific (date + agenda item) | Hierarchy-based (chapter + section) |
| **Update Frequency** | Per meeting (~24/year) | As amended (irregular) |
| **Temporal Context** | Meeting date is primary | Effective/amended dates track history |
| **Hierarchy** | Flat agenda items | Multi-level (chapter > section > subsection) |
| **Cross-reference** | Staff reports, votes | Related state statutes, legal authority |
| **Chunking Strategy** | Page-based chunks | Section-based (preserve legal boundaries) |

#### Collection Metadata

```json
{
  "description": "San Rafael Municipal Code for RAG",
  "jurisdiction_id": "city-san-rafael",
  "embedding_model": "nomic-embed-text-v1.5",
  "embedding_dimension": 768,
  "source": "municode.com or local PDF",
  "created_at": "2025-12-10T00:00:00Z",
  "total_sections": 523,
  "chapters": 25,
  "last_updated": "2025-12-10T00:00:00Z",
  "civic_version": "0.1.0"
}
```

#### SQLite Integration (Future)

Municipal code sections can join with a future `code_sections` SQLite table:

```sql
-- Municipal code ID enables joining
-- ChromaDB: city-san-rafael-muni-19-1
-- SQLite code_sections.id: city-san-rafael-muni-19-1

SELECT cs.section_title, cs.full_text
FROM code_sections cs
WHERE cs.chapter = '19'
  AND cs.jurisdiction_id = 'city-san-rafael';
```

#### Usage in API Methods

| Method | Municipal Code Role |
|--------|---------------------|
| `what_applies(topic)` | Primary query target - returns relevant code sections |
| `what_happened(topic)` | Cross-reference with decisions that cite code |
| `prepare(meeting)` | Include relevant code context for agenda items |

### SeeClickFix Issues Documents (issues collection)

SeeClickFix issues represent citizen-reported problems and requests, enabling semantic search over community concerns.

#### Source Files

- SeeClickFix API data stored in SQLite `issues` table
- Raw JSON: `data/pilot/seeclickfix_{jurisdiction_id}_*.json`

#### Text Representation (for embedding)

Each issue is converted to a searchable text block:

```
Issue Type: {issue_type}
Title: {title}
Description: {description}
Location: {address}
Status: {status}
```

#### Issues Metadata

ChromaDB metadata fields (all flat types - string, int, float, bool):

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `issue_id` | string | Unique issue identifier | `"city-san-rafael-scf-20575290"` |
| `source_id` | string | External SeeClickFix ID | `"20575290"` |
| `issue_type` | string | Category from SeeClickFix | `"Traffic/ Traffic Signal / Tránsito/Señal"` |
| `address` | string | Location address (truncated 200 chars) | `"103 West St San Rafael, CA 94901"` |
| `status` | string | Current status | `"open"`, `"acknowledged"`, `"closed"` |
| `latitude` | float | Latitude coordinate | `37.973281` |
| `longitude` | float | Longitude coordinate | `-122.540769` |
| `created_at` | string | ISO date of creation | `"2025-12-10"` |
| `updated_at` | string | ISO date of last update | `"2025-12-10"` |

#### Issue ID Format

```
{jurisdiction_id}-scf-{external_id}

Examples:
- city-san-rafael-scf-20575290
- city-san-rafael-scf-20574832
- city-berkeley-scf-12345678
```

**Rationale**:
- Prefix `scf-` distinguishes from other document types (decisions, chunks)
- Uses external SeeClickFix ID for traceability back to source
- Jurisdiction-scoped for multi-tenant isolation

#### Key Differences from Other Schemas

| Aspect | Decisions | Issues |
|--------|-----------|--------|
| **ID Scope** | Meeting-specific (date + agenda) | External source ID |
| **Update Frequency** | Per meeting (~24/year) | Continuous (daily) |
| **Temporal Context** | Meeting date is primary | Created/updated timestamps |
| **Geo Data** | None | Latitude/longitude for location filtering |
| **Hierarchy** | Agenda item structure | Flat (single issue) |

#### Collection Metadata

```json
{
  "description": "San Rafael SeeClickFix issues for RAG",
  "jurisdiction_id": "city-san-rafael",
  "embedding_model": "nomic-embed-text-v1.5",
  "embedding_dimension": 768,
  "source": "seeclickfix.com API",
  "created_at": "2025-12-10T00:00:00Z",
  "total_issues": 1340,
  "civic_version": "0.1.0"
}
```

#### Usage in API Methods

| Method | Issues Role |
|--------|-------------|
| `whos_with_me(topic)` | Search for issues matching topic semantically |
| `what_happened(topic)` | Cross-reference with related civic issues |
| `suggestions()` | Identify patterns in community reports |

---

## Embedding Configuration

### Primary Model: SentenceTransformer (Local)

| Model | Dimensions | Size | Context | Latency | Cost |
|-------|------------|------|---------|---------|------|
| `nomic-embed-text-v1.5` | 768 | 274MB | 8192 tokens | ~40ms | $0 |

**Rationale**: Foundation funding constraint favors low operational cost. Local model meets latency requirements (<500ms) while incurring zero API costs. The 8192 token context supports longer documents without truncation.

### Alternative: OpenAI (Future)

| Model | Dimensions | Size | Latency | Cost |
|-------|------------|------|---------|------|
| `text-embedding-3-small` | 1536 | API | ~100ms | $0.02/1M tokens |

**Use case**: If budget allows or higher quality needed for specific use cases.

### Configuration

```python
# Environment variable controls embedding provider
CIVICOS_EMBEDDING_PROVIDER = "local"  # or "openai"

# Provider-specific settings
CIVICOS_EMBEDDING_MODEL = "nomic-embed-text-v1.5"  # or "text-embedding-3-small"
```

---

## Relationship to Civic-State SQLite

The vector database **complements** (not replaces) the civic-state SQLite database.

### Data Flow

```
                    ┌─────────────────────┐
                    │  External Sources   │
                    │  (ProudCity, PDFs)  │
                    └──────────┬──────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │     Extraction Pipeline        │
              │  (civicos-extraction package)    │
              └───────────┬────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
          ▼                               ▼
┌─────────────────────┐      ┌─────────────────────┐
│    civic_state.db   │      │    Vector Store     │
│      (SQLite)       │      │     (ChromaDB)      │
├─────────────────────┤      ├─────────────────────┤
│ - meetings          │      │ - decisions         │
│ - agenda_items      │      │ - chunks            │
│ - initiatives       │      │                     │
│ - voices            │      │ Semantic search     │
│ - subscriptions     │◄────►│ (what_happened)     │
│                     │      │                     │
│ Relational queries  │      │                     │
│ (whats_next)        │      │                     │
└─────────────────────┘      └─────────────────────┘
```

### Query Routing

| Method | Primary Store | Fallback |
|--------|--------------|----------|
| `whats_next()` | SQLite (meetings) | - |
| `what_applies()` | SQLite + embeddings (future) | SQLite keyword |
| `what_happened()` | ChromaDB (decisions) | SQLite keyword |
| `whos_with_me()` | SQLite (issues) | - |

---

## Semantic Search Patterns

This section documents ranking strategies and search patterns for semantic queries across corpus types.

### Corpus Structure Classification

Corpus types fall into two categories that inform search behavior:

| Category | Corpus Types | Structure | Ranking Consideration |
|----------|--------------|-----------|----------------------|
| **Hierarchical** | legislation, municipal_code, chunks, transcripts | Chunks belong to parent entity | Group by parent, limit chunks per parent |
| **Flat** | decisions, meetings, issues | Each document standalone | Direct ranking by similarity score |

### Hierarchical Search Pattern

For corpus types where chunks belong to a parent entity:

```
legislation:     chunks → bills (parent_field: bill_id)
municipal_code:  sections → chapters (parent_field: chapter)
chunks:          pages → meetings (parent_field: meeting_id)
transcripts:     segments → meetings (parent_field: meeting_id)
```

**Standard algorithm:**
1. Search chunks with generous `top_k` (e.g., 100)
2. Group chunks by parent_id
3. Keep top N chunks per parent (e.g., 3)
4. Rank parents by max chunk score
5. Return top M parents (e.g., 30)

**Key parameters:**
```python
CHUNK_TOP_K = 100      # Initial chunk retrieval
CHUNKS_PER_PARENT = 3  # Relevant sections per parent
MAX_PARENTS = 30       # Final result limit
MIN_SCORE = 0.4        # Similarity floor
```

### Ranking Modes

Two ranking modes are supported for hierarchical corpus types:

| Mode | Behavior | Best For |
|------|----------|----------|
| **chunk_first** | Order by when chunks first appear (preserves semantic relevance) | Broad topic queries ("housing policy") |
| **parent_first** | Order by max chunk score per parent, with boosting | Specific entity queries ("SB9 law") |

**Auto-detection heuristic:** If query contains identifiable entity patterns (bill numbers, section numbers, dates), use `parent_first` with boosting.

### ID Boosting

When a query explicitly mentions an entity ID, boost that entity's ranking:

| Corpus | ID Pattern | Example Query | Boost |
|--------|------------|---------------|-------|
| legislation | `[SAH]B\d+`, `HR\d+` | "SB9 duplex law" | +0.1 |
| municipal_code | `Section [\d.]+` | "Section 14.12.020 parking" | +0.1 |
| decisions | `Resolution \d+`, `Ordinance \d+` | "Resolution 14823" | +0.1 |
| meetings | `\d{4}-\d{2}-\d{2}` | "January 15 2024 meeting" | +0.1 |
| issues | `#\d+` | "issue #12345" | +0.1 |

**Implementation (legislation example):**
```python
BILL_PATTERN = re.compile(r'\b(SB|AB|HR|HB|S\.?)\s*\d+\b', re.IGNORECASE)

def _extract_mentioned_ids(query: str) -> set:
    """Extract bill numbers for boosting."""
    matches = re.findall(r'\b((?:SB|AB|HR|HB|S\.?)\s*\d+)\b', query, re.IGNORECASE)
    return {m.replace(" ", "").replace(".", "").upper() for m in matches}

# During ranking, boost mentioned entities
if entity_id in mentioned_ids:
    sort_score = base_score + 0.1
```

### Tiered Response Structure

All semantic search results include a tier field for pagination support:

```python
{
    "id": "ca-sb9",
    "relevance_score": 0.673,
    "tier": "primary",      # Top 10 results
    # ... other fields
}

{
    "id": "ca-sb130",
    "relevance_score": 0.620,
    "tier": "secondary",    # Results 11-30
    # ... other fields
}
```

**Tier assignment:**
- `primary`: Rank 1-10 (high confidence, show by default)
- `secondary`: Rank 11-30 (additional context, expandable)

### Score Distribution Characteristics

Empirical observations from legislation corpus (generalizes to other corpus types):

| Observation | Implication |
|-------------|-------------|
| Scores cluster in 0.6-0.8 range | 0.4 floor rarely triggers |
| Score gaps are small (0.003-0.015) | Gap-based cutoffs unreliable |
| Broad queries: very flat distribution | Tiering more useful than filtering |
| Narrow queries: slightly more variance | ID boosting essential for precision |

### Configurable Parameters

All semantic search methods should expose:

```python
def search_corpus(
    query: str,
    *,
    ranking_mode: Literal["chunk_first", "parent_first", "auto"] = "auto",
    max_results: int = 30,
    min_score: float = 0.4,
) -> List[dict]:
```

**Parameter guidelines:**
- `ranking_mode="auto"`: Detect based on query content (recommended default)
- `max_results`: Adjustable per use case (research: 50+, casual: 10)
- `min_score`: Keep at 0.4 as safety floor (rarely triggers)

### Implementation Status

| Corpus | Hierarchical Grouping | ID Boosting | Tiered Response | Configurable Params |
|--------|----------------------|-------------|-----------------|---------------------|
| legislation | ✅ Implemented | ✅ Implemented | ✅ Implemented | ✅ Implemented |
| municipal_code | ❌ Uses top_k=5 | ❌ Not implemented | ❌ Not implemented | ❌ Hardcoded |
| decisions | N/A (flat) | ❌ Not implemented | ❌ Not implemented | ❌ Hardcoded |
| transcripts | ❌ Not implemented | ❌ Not implemented | ❌ Not implemented | ❌ Hardcoded |
| chunks | ❌ Not implemented | ❌ Not implemented | ❌ Not implemented | ❌ Hardcoded |
| issues | N/A (flat) | ❌ Not implemented | ❌ Not implemented | ❌ Hardcoded |

**Next corpus to implement:** decisions (Resolution number boosting is high-value)

---

### Foreign Key Alignment

Decision IDs in ChromaDB can be joined with SQLite:

```sql
-- Decision ID format enables joining
-- ChromaDB: city-san-rafael-2025-11-17-6a
-- SQLite meetings.id: city-san-rafael-2025-11-17

SELECT m.title, a.description
FROM meetings m
JOIN agenda_items a ON a.meeting_id = m.id
WHERE m.id = 'city-san-rafael-2025-11-17'
  AND a.item_number = '6.a';
```

---

## Implementation Roadmap

### Phase 1: Rename Infrastructure (Current)

| Task | Files | Status |
|------|-------|--------|
| Rename class | `MerrydaleEmbeddings` → `CivicEmbeddings` | done |
| Add jurisdiction param | `CivicEmbeddings(jurisdiction_id)` | done |
| Rename directories | `merrydale_vectors/` → `vectors/city-san-rafael/` | done |
| Update collection names | `merrydale_*` → `city-san-rafael_*` | done |
| Regenerate index | Rebuild with new naming | pending |

### Phase 2: Provider Abstraction

| Task | Description | Status |
|------|-------------|--------|
| EmbeddingProvider protocol | Abstract interface with `encode()` | not_tested |
| SentenceTransformerProvider | Local implementation | not_tested |
| OpenAIProvider | API implementation | not_tested |
| Configuration system | Env var selection | not_tested |

### Phase 3: Multi-Jurisdiction

| Task | Description | Status |
|------|-------------|--------|
| Test with second city | Add Berkeley or Oakland | not_tested |
| Cross-jurisdiction search | Query multiple cities | not_tested |
| Index management | Rebuild/update per jurisdiction | not_tested |

---

## Cost Analysis

### Storage (ChromaDB)

| Component | Per Jurisdiction | 26 Cities |
|-----------|-----------------|-----------|
| Decisions (~100/year) | 50 KB | 1.3 MB |
| Chunks (~1000/meeting) | 500 KB | 13 MB |
| Total per year | ~5 MB | ~130 MB |

### Embedding Generation (Local)

| Component | Time | Cost |
|-----------|------|------|
| Initial index build | ~5 min | $0 |
| Incremental updates | ~30 sec | $0 |

**Conclusion**: Well within foundation budget constraints.

---

## Schema Validation Tests

Test file: `packages/civicos/tests/test_integration_rag_schema.py`

```python
class TestVectorSchemaCompliance:
    """Verify vector store follows schema conventions."""

    def test_collection_naming(self):
        """Collections follow {jurisdiction}_decisions format."""
        pass

    def test_decision_metadata_fields(self):
        """Decision metadata has required fields."""
        pass

    def test_chunk_metadata_fields(self):
        """Chunk metadata has required fields."""
        pass

    def test_id_format_compliance(self):
        """IDs follow {jurisdiction}-{date}-{item} format."""
        pass

    def test_sqlite_joinability(self):
        """Decision IDs can join with SQLite meetings."""
        pass
```

---

## References

- `packages/civicos/src/civicos/context.py` - Legislation semantic search implementation (ranking modes, boosting)
- `packages/civicos/src/civicos/storage/corpus_types.py` - Corpus type registry
- `docs/hot_session_semantic_search_critique.md` - Analysis of search patterns with empirical data
- `packages/civicos/src/civicos/_internal/state/manager.py` - SQLite schema
- `packages/civicos/src/civicos/_internal/meetings/embeddings.py` - Current embeddings (to refactor)
- `integration.json` - architecture_cleanup section
- `data/pilot/san_rafael_shelter_scenario.json` - Test corpus context

---

*Created: Session 191 (2025-12-05)*
*Updated: Session 233 (2025-12-10) - Added SeeClickFix Issues Documents schema*
*Updated: 2026-01-23 - Added Semantic Search Patterns section (ranking modes, ID boosting, tiering)*
*Schema Version: 1.3*
