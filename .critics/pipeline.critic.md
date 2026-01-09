# Pipeline Critic

Review code changes to the ETL pipeline to ensure they maintain the 4-stage pattern and proper persistence.

## Context

The Civic pipeline follows a strict 4-stage pattern:
1. **discover** - Find available meetings from data source
2. **ingest** - Fetch and normalize meeting data
3. **store** - Persist to StorageBackend (SQLite/Postgres)
4. **index** - Build vector index from stored data

Critical invariant: Data MUST be persisted via StorageBackend BEFORE indexing. The index stage reads FROM StorageBackend, not from memory.

## Key Files

- `packages/civic-extraction/src/civic_extraction/pipeline.py` - Main Pipeline class
- `packages/civic/src/civic/storage/backend.py` - StorageBackend protocol
- `packages/civic/src/civic/storage/vector.py` - VectorBackend protocol

## Check

When reviewing changes to Pipeline or storage:

1. **4-stage sequence preserved?**
   - discover → ingest → store → index (in order)
   - No stages skipped without explicit flag
   - Failure in early stage prevents later stages

2. **Persistence before indexing?**
   - Ingested data is stored via `StorageBackend.store_meetings()`
   - Index stage reads from `StorageBackend.get_meetings()`
   - No indexing directly from in-memory data

3. **Storage gap risk?**
   - Data never "disappears" between stages
   - Ingested items tracked in `_ingested_meetings` until stored
   - Failed stores are retried or surfaced as errors

4. **Callback patterns?**
   - `on_stage_start`, `on_stage_progress`, `on_stage_complete` honored
   - `on_checkpoint` called after ingest with resume state
   - `on_error` called for stage failures

5. **Protocol compliance?**
   - Uses public StorageBackend methods, not private implementation
   - No direct `_get_connection()` calls - use protocol methods
   - Updates go through `backend.update_meeting()`, not raw SQL
   - This ensures portability across SQLite/Postgres backends

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of specific issues found"],
  "severity": "critical" | "warning" | "info",
  "suggestions": ["optional fixes or improvements"]
}
```

## Examples

### FAIL - Storage Gap
```python
# BAD: Indexing from memory, not storage
def run(self):
    meetings = self._run_ingest()
    self.index.add_meetings(meetings)  # storage gap!
```

### PASS - Proper Persistence
```python
# GOOD: Store then index from storage
def run(self):
    meetings = self._run_ingest()
    self.storage.store_meetings(self.jurisdiction_id, meetings)
    stored = self.storage.get_meetings(self.jurisdiction_id)
    self.index.add_meetings(stored)
```

### FAIL - Protocol Bypass
```python
# BAD: Accessing private method, not portable across backends
def update_agenda_url(backend, meeting_id, url):
    conn = backend._get_connection()  # Private method!
    cursor.execute("UPDATE meetings SET agenda_url = ?", ...)
```

### PASS - Protocol Compliance
```python
# GOOD: Uses public StorageBackend method
def update_agenda_url(backend, jurisdiction_id, meeting_id, url):
    backend.update_meeting(jurisdiction_id, meeting_id, {"agenda_url": url})
```
