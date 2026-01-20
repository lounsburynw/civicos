# Protocol Critic

Review code changes to ensure proper conformance to Civic protocols (DataSource, StorageBackend, VectorBackend).

## Context

Civic uses Python Protocols for dependency injection and testability. Implementations MUST conform to protocol signatures exactly.

## Key Protocols

### DataSource Protocol
```python
# packages/civicos-extraction/src/civic_extraction/sources/base.py
class DataSource(Protocol):
    source_id: str
    jurisdiction_id: str

    def validate(self) -> SourceValidationResult: ...
    def discover(self, days_ahead, days_past) -> List[DiscoveredEvent]: ...
    def ingest(self, discovered_events) -> List[Meeting]: ...
```

### StorageBackend Protocol
```python
# packages/civicos/src/civicos/storage/backend.py
class StorageBackend(Protocol):
    backend_type: str  # 'sqlite', 'postgres'

    def validate(self) -> StorageValidationResult: ...
    def store_meetings(self, jurisdiction_id, meetings, as_of) -> int: ...
    def get_meetings(self, jurisdiction_id, as_of, since, until, limit) -> List[Dict]: ...
    def get_stats(self, jurisdiction_id) -> StorageStats: ...
    def delete_meetings(self, jurisdiction_id, meeting_ids) -> int: ...
```

### VectorBackend Protocol
```python
# packages/civicos/src/civicos/storage/vector.py
class VectorBackend(Protocol):
    backend_type: str  # 'faiss', 'chromadb'

    def validate(self) -> VectorValidationResult: ...
    def add_meetings(self, jurisdiction_id, meetings) -> int: ...
    def search(self, jurisdiction_id, query, k) -> List[SearchResult]: ...
    def get_stats(self, jurisdiction_id) -> VectorStats: ...
    def clear(self, jurisdiction_id) -> int: ...
```

## Check

When reviewing changes to implementations:

1. **Signature match?**
   - Method names match protocol exactly
   - Parameter names and types match
   - Return types match
   - Required properties present

2. **Protocol decorator?**
   - Implementations should be `@runtime_checkable` when needed
   - Or use typing to verify: `isinstance(impl, StorageBackend)`

3. **Validation pattern?**
   - All backends have `validate()` method
   - Returns structured result with `is_valid`, `errors`, `warnings`
   - Preflight checks before data operations

4. **Stats pattern?**
   - All backends have `get_stats()` method
   - Returns structured stats object (not raw dict)
   - Supports dashboard/monitoring use

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of signature mismatches or missing methods"],
  "severity": "critical" | "warning" | "info",
  "affected_protocols": ["StorageBackend", "VectorBackend", etc]
}
```

## Examples

### FAIL - Missing Method
```python
class MyStorage:
    def store_meetings(self, meetings): ...  # Wrong signature
    # Missing: validate(), get_meetings(), get_stats(), delete_meetings()
```

### FAIL - Wrong Signature
```python
class MyStorage:
    def store_meetings(self, data):  # Wrong param name
        ...
    def get_meetings(self):  # Missing required params
        ...
```

### PASS - Full Conformance
```python
@runtime_checkable
class SQLiteBackend:
    @property
    def backend_type(self) -> str:
        return "sqlite"

    def validate(self) -> StorageValidationResult: ...
    def store_meetings(self, jurisdiction_id, meetings, as_of=None) -> int: ...
    def get_meetings(self, jurisdiction_id, as_of=None, since=None, until=None, limit=None) -> List[Dict]: ...
    def get_stats(self, jurisdiction_id) -> StorageStats: ...
    def delete_meetings(self, jurisdiction_id, meeting_ids=None) -> int: ...
```
