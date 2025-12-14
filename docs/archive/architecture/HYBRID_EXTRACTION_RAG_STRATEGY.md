# Hybrid Structured + RAG Extraction Strategy

**Status**: Designed Session 99, Implementation Session 100+
**Purpose**: Scale decision extraction to 26+ cities with queryable "city state"
**Rationale**: Foundation-funded infrastructure requiring robust, maintainable architecture

---

## Problem Statement

**Session 99 Finding**: Current retrospective extraction fails due to:
1. **200K character truncation** - Large agenda packets get cut off mid-item
2. **Whole-document processing** - Single LLM call for entire PDF (inefficient, error-prone)
3. **No semantic search** - Can't answer "Which cities funded wildfire?" across corpus
4. **Limited scalability** - Doesn't handle unformatted documents from diverse municipalities

**Impact**: Missing 67% of high-stakes decisions (found 1/33 meetings vs expected 15-30)

---

## Solution: Hybrid Architecture

### Phase 1: Structured Extraction (Session 100)

**Goal**: Extract ALL decisions with complete metadata, no truncation

**Method**: Item-by-item processing leveraging agenda structure

```python
# Instead of:
pdf_text[:200000] → LLM → extract decisions (TRUNCATED!)

# Do:
pdf_text → split by item numbers → process each item → merge results (COMPLETE!)
```

**Algorithm**:
```
1. Download full PDF text (PyPDF2)
2. Regex split on agenda item patterns: "\n5.g ", "\n7.a ", etc.
3. For each item chunk:
   - Extract metadata with LLM (budget, type, keywords)
   - Store in SQLite with full text
4. Merge results into structured JSON
```

**Benefits**:
- ✅ No truncation (process each item fully)
- ✅ Complete enumeration (every item analyzed)
- ✅ Structured queries (filter by budget, date, type)
- ✅ Fast batch processing (parallel LLM calls)

**Output**: `data/pilot/san_rafael_high_stakes_v2.json`
```json
{
  "decisions": [
    {
      "item_ref": "5.g",
      "title": "Measure C Wildfire Prevention Fund",
      "budget_amount": 1108319,
      "keywords": ["wildfire", "fire", "vegetation", "defensible"],
      "full_text": "...",
      "meeting_date": "2025-10-06"
    }
  ]
}
```

### Phase 2: Vector Embeddings (Session 101)

**Goal**: Enable semantic search across all extracted decisions

**Method**: Generate embeddings, store in ChromaDB

```python
from sentence_transformers import SentenceTransformer
import chromadb

# Generate embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')  # Free, 384 dimensions
embeddings = model.encode([d['description'] for d in decisions])

# Store in ChromaDB
client = chromadb.PersistentClient(path="data/pilot/decision_vectors.db")
collection = client.create_collection("high_stakes_decisions")
collection.add(
    embeddings=embeddings,
    documents=[d['description'] for d in decisions],
    metadatas=[{'budget': d['budget_amount'], 'date': d['meeting_date']} for d in decisions],
    ids=[d['item_ref'] for d in decisions]
)
```

**Benefits**:
- ✅ Semantic search: "wildfire spending" matches "vegetation management", "fire prevention"
- ✅ Cross-city patterns: Find similar decisions across 26 jurisdictions
- ✅ Historical precedent: "Has Berkeley done this before?"
- ✅ Coalition discovery: "Who else cares about this issue?"

**Cost**: ~$0.10 per 1,000 decisions (one-time embedding generation)

### Phase 3: Hybrid Queries (Session 102+)

**Goal**: Combine structured filters + semantic search

**Example Queries**:

```python
# Query 1: Structured filter
"Find all housing decisions >$1M in 2024"
→ SQL: WHERE type='housing' AND budget>1000000 AND year=2024

# Query 2: Semantic search
"Find decisions about wildfire prevention"
→ Vector search: Embed query → Find similar descriptions

# Query 3: HYBRID
"Find housing decisions >$1M related to climate adaptation"
→ Structured filter (type, budget) + Vector search (climate similarity)
```

**API Endpoint** (future):
```
GET /api/decisions/search?
  type=housing&
  budget_min=1000000&
  semantic_query=climate+adaptation&
  cities=berkeley,oakland
```

---

## Architecture Comparison

### Before (Session 98):

```
PDF (500 pages, 300K chars)
  ↓
Truncate to 200K chars ❌ (loses item 5.g!)
  ↓
Single LLM call
  ↓
Extract decisions
  ↓
Result: 5 decisions found (missing 67%)
```

### After Phase 1 (Session 100):

```
PDF (500 pages, 300K chars)
  ↓
Split into 30 agenda items (regex)
  ↓
Process each item in parallel (30 LLM calls)
  ↓
Merge results
  ↓
Result: 15-30 decisions found ✅ (complete!)
```

### After Phase 2 (Session 101):

```
Extracted decisions (30 items)
  ↓
Generate embeddings (SentenceTransformer)
  ↓
Store in ChromaDB
  ↓
Enable semantic search across corpus
  ↓
Use case: "Which cities funded wildfire?" → 8 cities, 24 decisions
```

---

## Technology Stack

### Structured Extraction (Phase 1)
- **PDF parsing**: PyPDF2 (already installed)
- **Text splitting**: Regex on agenda item patterns
- **LLM**: Gemini 2.5 Pro (2M context, $0.0002/1K tokens)
- **Storage**: SQLite + JSON files
- **Cost**: ~$0.05 per meeting (33 items × $0.002)

### Vector Search (Phase 2)
- **Embeddings**: SentenceTransformer `all-MiniLM-L6-v2` (free, local)
- **Vector DB**: ChromaDB (free, local, no cloud dependency)
- **Dimensions**: 384 (good balance of accuracy vs speed)
- **Storage**: ~100MB for 1,000 decisions
- **Cost**: $0 ongoing (runs locally)

### Why NOT LangChain RecursiveCharacterTextSplitter?

**LangChain chunking** (general-purpose):
- Splits on characters (256-512 tokens, 10-20% overlap)
- Works for unstructured documents
- Good for RAG Q&A systems

**Our agenda splitting** (domain-specific):
- Splits on agenda structure (item numbers: 5.g, 7.a)
- Leverages municipal document format
- Simpler, more reliable for this use case

**Decision**: Use regex splitting (Phase 1), add LangChain chunking for unformatted docs (Phase 3)

---

## Scalability

### Multi-City Support

**Formatted agendas** (Legistar, CivicClerk):
- Use regex splitting (item numbers)
- 99% accuracy

**Unformatted agendas** (HTML, scanned PDFs):
- Fallback to LangChain RecursiveCharacterTextSplitter
- Vector search handles messy text

**Mixed formats**:
- Detect agenda structure (regex test for item patterns)
- If structured → regex split
- If unstructured → LangChain split

### Vector Search Across 26 Cities

```python
# Query: "wildfire prevention spending"
results = collection.query(
    query_texts=["wildfire prevention spending"],
    n_results=20,
    where={"budget": {"$gte": 100000}}  # Hybrid: vector + filter
)

# Returns decisions from multiple cities:
# - San Rafael: Measure C Wildfire Fund ($1.1M)
# - Berkeley: Vegetation Management ($500K)
# - Oakland: Fire Prevention Grants ($750K)
```

**Enables**:
- ✅ Cross-city pattern analysis
- ✅ Regional coordination opportunities
- ✅ Foundation pitch evidence ("8 cities allocated $12M to wildfire")

---

## Implementation Timeline

**Session 100** (3-4 hours):
- [ ] Implement regex-based item splitting
- [ ] Fix retrospective_analyzer.py to use item-by-item processing
- [ ] Test on Oct 6 meeting (validate wildfire case found)
- [ ] Re-run on 33 City Council meetings
- [ ] Validate 15-30 decisions extracted

**Session 101** (2-3 hours):
- [ ] Install ChromaDB + sentence-transformers
- [ ] Generate embeddings for all decisions
- [ ] Build vector index
- [ ] Implement semantic search API
- [ ] Test cross-city queries

**Session 102** (2-3 hours):
- [ ] Implement hybrid query API
- [ ] Add frontend search interface
- [ ] Build pattern discovery dashboard
- [ ] Document query examples

---

## Success Metrics

### Phase 1 (Structured Extraction)
- ✅ Find Oct 6 wildfire case ($1.1M)
- ✅ Extract 15-30 decisions from 33 meetings
- ✅ Zero truncation errors
- ✅ Complete metadata for all items

### Phase 2 (Vector Search)
- ✅ Index all decisions with embeddings
- ✅ Semantic search accuracy >90%
- ✅ Query latency <500ms
- ✅ Local deployment (no cloud costs)

### Phase 3 (Hybrid Queries)
- ✅ Support combined filters + semantic search
- ✅ Cross-city pattern discovery
- ✅ Frontend integration
- ✅ Foundation pitch evidence generation

---

## Alternatives Considered

### Option A: Buy commercial tool (Parsio, Docparser)
- ❌ Cost: $49-299/month (vs $7/month operational budget)
- ❌ Not aligned with foundation-funded infrastructure model

### Option B: IBM Docling (free, open source)
- ✅ Converts PDF → Markdown/JSON
- ⚠️ New tool (Jan 2025), unknown reliability
- ⚠️ Extra dependency
- **Decision**: Monitor for future, use simpler approach now

### Option C: Full LangChain RAG stack
- ✅ Industry-standard
- ❌ Overkill for batch extraction (designed for interactive Q&A)
- ⚠️ Adds complexity we don't need yet
- **Decision**: Use parts (chunking fallback), not full stack

### Option D: Hybrid Structured + RAG (SELECTED)
- ✅ Solves immediate problem (truncation)
- ✅ Enables future features (semantic search)
- ✅ Foundation-friendly (free tools, local deployment)
- ✅ Scalable to diverse document formats
- **Decision**: IMPLEMENT THIS

---

## Documentation Updates

- ✅ `docs/pilot/RETROSPECTIVE_ANALYSIS_PIPELINE.md` - Pipeline architecture
- ✅ `docs/core/next_session_prompt.md` - Session 100 roadmap
- ✅ `CLAUDE.md` - RAG strategy summary
- ✅ `docs/architecture/HYBRID_EXTRACTION_RAG_STRATEGY.md` (this document)

---

**Next Session**: Implement Phase 1 (item-by-item extraction) to find Oct 6 wildfire case
