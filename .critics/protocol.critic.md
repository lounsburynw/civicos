# Protocol Critic

Review code changes to ensure proper conformance to CivicOS protocols (DataSource, StorageBackend, VectorBackend).

## Context

CivicOS uses Python `Protocol` classes with `@runtime_checkable` for dependency injection and testability. Implementations MUST conform to protocol signatures exactly.

StorageBackend is a composite protocol inheriting from 6 sub-protocols. VectorBackend handles semantic search. DataSource provides read-only access for federated queries.

## Key Protocols

### StorageBackend Protocol (composite)
```python
# packages/civicos/src/civicos/storage/backend.py
@runtime_checkable
class StorageBackend(
    ContentStorage,       # meetings, decisions, chunks, agenda items, transcripts, videos
    LegislationStorage,   # legislation, municipal code, codified law, executive orders, federal rules
    FinancialStorage,     # budget items, federal awards, state passthrough, federal programs
    CommunityStorage,     # issues (SeeClickFix)
    ElectionStorage,      # elections, deadlines, contests, officials
    OperationsStorage,    # operations tracking, ETL costs, operating costs
    Protocol,
):
    backend_type: str  # 'sqlite', 'postgres'

    def validate(self) -> StorageValidationResult: ...
    def get_stats(self, jurisdiction_id: str) -> StorageStats: ...
```

Key methods from sub-protocols (most commonly used):
```python
# ContentStorage (packages/civicos/src/civicos/storage/protocols/content.py)
def store_meetings(self, jurisdiction_id, meetings, as_of=None) -> MeetingStoreResult: ...
def get_meetings(self, jurisdiction_id, as_of=None, since=None, until=None, limit=None, offset=0) -> List[Dict]: ...
def update_meeting(self, jurisdiction_id, meeting_id, updates) -> bool: ...
def delete_meetings(self, jurisdiction_id, meeting_ids=None) -> int: ...
def store_decisions(self, jurisdiction_id, decisions, as_of=None) -> int: ...
def get_decisions(self, jurisdiction_id, as_of=None, since=None, until=None, limit=None, offset=0) -> List[Dict]: ...
def store_chunks(self, jurisdiction_id, chunks, as_of=None, meeting_id=None) -> int: ...
def store_transcripts(self, jurisdiction_id, transcripts, as_of=None) -> int: ...
```

**Note:** `store_meetings()` returns `MeetingStoreResult` (not `int`). The result is int-compatible but carries reactive pipeline signals (`new_meeting_ids`, `updated_meeting_ids`, `minutes_appeared`, `video_appeared`, `agenda_appeared`).

### VectorBackend Protocol
```python
# packages/civicos/src/civicos/storage/vector.py
@runtime_checkable
class VectorBackend(Protocol):
    backend_type: str       # 'chromadb', 'pgvector'
    embedding_model: str    # e.g. 'text-embedding-3-small'
    embedding_dimension: int

    def validate(self) -> VectorValidationResult: ...
    def index_from_storage(self, storage_backend, jurisdiction_id, corpus_type='meetings',
                           batch_size=100, transcript_chunker=None, legal_chunker=None) -> int: ...
    def search(self, query, jurisdiction_id, corpus_type='meetings',
               top_k=5, min_score=None, meeting_id=None) -> List[SearchResult]: ...
    def count(self, jurisdiction_id, corpus_type='decisions') -> int: ...
    def get_stats(self, jurisdiction_id, corpus_type='meetings', storage_backend=None) -> VectorStats: ...
    def get_chunks_by_prefix(self, id_prefix, corpus_type='transcripts', limit=800) -> List[SearchResult]: ...
    def delete_index(self, jurisdiction_id, corpus_type=None) -> int: ...
```

**Common mistakes:**
- `search()` takes `query` FIRST, then `jurisdiction_id` (not reversed)
- Uses `top_k` parameter (not `k`)
- `corpus_type` is required for multi-corpus support
- `index_from_storage()` reads from StorageBackend (not memory) — enforces persistence-before-indexing
- `add_meetings()` and `clear()` do NOT exist — use `index_from_storage()` and `delete_index()`

### DataSource Protocol (read-only)
```python
# packages/civicos/src/civicos/storage/data_source.py
@runtime_checkable
class DataSource(Protocol):
    source_type: str  # 'local', 'federated', 'hybrid'

    def validate(self) -> Dict[str, Any]: ...
    def get_meetings(self, jurisdiction_id, since=None, until=None, limit=None) -> List[Dict]: ...
    def get_decisions(self, jurisdiction_id, since=None, until=None, limit=None) -> List[Dict]: ...
    def get_budget_items(self, jurisdiction_id, fiscal_year=None, department=None, limit=None) -> List[Dict]: ...
    def get_elections(self, jurisdiction_id, include_past=False, limit=None) -> List[Dict]: ...
    def get_federal_awards(self, jurisdiction_id, cfda_number=None, limit=None) -> List[Dict]: ...
    def get_stats(self, jurisdiction_id) -> StorageStats: ...
    # ... plus ~16 more query methods for all data types
```

**DataSource vs StorageBackend:** DataSource is read-only (get/search methods only). StorageBackend is read-write (store/get/update/delete). DataSource is for federation; StorageBackend is for local persistence.

## Sub-Protocol Files

All in `packages/civicos/src/civicos/storage/protocols/`:

| File | Protocol | Methods |
|------|----------|---------|
| `content.py` | ContentStorage | meetings, decisions, chunks, agenda items, transcripts, videos |
| `legislation.py` | LegislationStorage | legislation, municipal code, codified law, executive orders, federal rules, legislative events |
| `financial.py` | FinancialStorage | budget items, federal awards, state passthrough, federal programs, allocations |
| `community.py` | CommunityStorage | issues |
| `elections.py` | ElectionStorage | elections, deadlines, contests, elected officials |
| `operations.py` | OperationsStorage | operations, ETL costs, operating costs |

## Check

When reviewing changes to implementations:

1. **Signature match?**
   - Method names match protocol exactly
   - Parameter names and types match (especially parameter ORDER)
   - Return types match (`MeetingStoreResult` not `int` for `store_meetings()`)
   - Required properties present (`backend_type`, `embedding_model`, etc.)

2. **Protocol decorator?**
   - Protocols use `@runtime_checkable`
   - Implementations verified via `isinstance(impl, StorageBackend)`

3. **Validation pattern?**
   - All backends have `validate()` method
   - Returns structured result with `is_valid`, `errors`, `warnings`
   - Preflight checks before data operations

4. **Stats pattern?**
   - All backends have `get_stats()` method
   - Returns structured stats object (`StorageStats`, `VectorStats`)
   - VectorStats includes `coverage_percent` property

5. **Multi-corpus support?**
   - VectorBackend methods accept `corpus_type` parameter
   - Don't assume "meetings" — check the caller's intent

## Output

Respond with JSON:
```json
{
  "critic": "protocol",
  "pass": boolean,
  "issues": ["list of signature mismatches or missing methods"],
  "severity": "critical" | "warning" | "info",
  "affected_protocols": ["StorageBackend", "VectorBackend", "DataSource"]
}
```

## Examples

### FAIL - Wrong VectorBackend search() signature
```python
# BAD: jurisdiction_id first, wrong param name
results = vectors.search(jurisdiction_id, query, k=5)

# GOOD: query first, correct param names
results = vectors.search(query, jurisdiction_id, corpus_type='transcripts', top_k=5)
```

### FAIL - Wrong store_meetings() return type assumption
```python
# BAD: Assumes int return
count = storage.store_meetings(jurisdiction_id, meetings)
print(f"Stored {count} meetings")  # Works but misses reactive signals

# GOOD: Uses MeetingStoreResult
result = storage.store_meetings(jurisdiction_id, meetings)
if result.has_new_material:
    trigger_indexing(result.new_meeting_ids)
```

### FAIL - Using non-existent VectorBackend methods
```python
# BAD: These methods don't exist
vectors.add_meetings(jurisdiction_id, meetings)  # Use index_from_storage()
vectors.clear(jurisdiction_id)                    # Use delete_index()
```

### PASS - Full Conformance
```python
@runtime_checkable
class PostgresBackend(ContentStorage, LegislationStorage, ...):
    @property
    def backend_type(self) -> str:
        return "postgres"

    def validate(self) -> StorageValidationResult: ...
    def store_meetings(self, jurisdiction_id, meetings, as_of=None) -> MeetingStoreResult: ...
    def get_meetings(self, jurisdiction_id, as_of=None, since=None, until=None, limit=None, offset=0) -> List[Dict]: ...
    def get_stats(self, jurisdiction_id) -> StorageStats: ...
```
