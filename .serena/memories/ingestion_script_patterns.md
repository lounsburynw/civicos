# Ingestion Script Patterns

## StorageBackend Protocol for Scripts

When writing scripts in `scripts/` that need to update meeting records (e.g., setting `agenda_url`, `minutes_url`, `video_url` after uploading to R2), **always use the StorageBackend protocol methods**.

### ✅ CORRECT Pattern

```python
from civic.storage.postgres_backend import PostgresBackend

backend = PostgresBackend(database_url)

# Use the public protocol method
backend.update_meeting(
    jurisdiction_id="school-san-rafael",
    meeting_id="srcs-2025-12-16",
    updates={"agenda_url": "r2://bucket/path/file.pdf"}
)
```

### ❌ INCORRECT Pattern (Do NOT do this)

```python
# BAD: Accessing private method, not portable
conn = backend._get_connection()
cursor = conn.cursor()
cursor.execute("UPDATE meetings SET agenda_url = %s WHERE id = %s", ...)
```

### Why This Matters

1. **Portability**: `update_meeting()` works with both `PostgresBackend` and `SQLiteBackend`
2. **Field validation**: Only allowed fields can be updated (prevents accidental content changes)
3. **Temporal versioning**: Metadata updates don't create new temporal versions
4. **Scaling**: When adding new jurisdictions (other cities, school districts), the same pattern works

### Allowed Fields for `update_meeting()`

- `agenda_url` - Link to agenda PDF (typically R2 URL)
- `minutes_url` - Link to minutes PDF
- `video_url` - Link to video recording
- `source_url` - Original source URL
- `virtual_url` - Virtual meeting link
- `location` - Physical location
- `status` - Meeting status

### Reference Implementation

See `scripts/ingest_srcs.py` for the canonical example of:
1. Downloading PDFs via client
2. Uploading to R2 blob storage
3. Updating meeting record via `backend.update_meeting()`

### Critics

The `pipeline.critic.md` and `architecture.critic.md` will flag protocol violations. If you see a critic failure about `_get_connection()` or protocol bypass, use `update_meeting()` instead.
