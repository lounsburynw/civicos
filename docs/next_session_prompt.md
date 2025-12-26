# Recommended: blob_storage_abstraction

**Priority:** P0
**Area:** deployment_artifacts > cloud_storage
**Date:** 2025-12-26

> This is recommended context from Session 369. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 369 completed **postgres_backend** - PostgresBackend now has full parity with SQLiteBackend (meetings, operations, decisions, chunks). Also extended StorageBackend protocol and added `get_storage_backend()` factory for transparent backend selection via DATABASE_URL.

**Next step:** Blob storage for large files (PDFs, audio, transcripts).

## Recommended Task: blob_storage_abstraction

Create a `BlobStorage` protocol and `R2Backend` implementation for offloading large files to Cloudflare R2.

**Why R2:**
- 10GB free tier with zero egress fees
- S3-compatible API (boto3 works out of box)
- Offloads PDFs/audio from local disk and Fly.io volumes

## Key Files

- `packages/civic/src/civic/storage/backend.py` - StorageBackend protocol pattern
- `packages/civic/src/civic/storage/__init__.py` - Export location
- `.env.example:124-142` - DATABASE section as pattern for R2 config

## Suggested Approach

1. **Define BlobStorage protocol** in `packages/civic/src/civic/storage/blob.py`:
   ```python
   @runtime_checkable
   class BlobStorage(Protocol):
       @property
       def backend_type(self) -> str: ...

       def upload(self, key: str, data: bytes, content_type: str = None) -> str: ...
       def download(self, key: str) -> bytes: ...
       def exists(self, key: str) -> bool: ...
       def delete(self, key: str) -> bool: ...
       def list_keys(self, prefix: str = "") -> List[str]: ...
   ```

2. **Create R2Backend** implementing BlobStorage:
   ```python
   class R2Backend:
       def __init__(self, account_id: str, access_key_id: str,
                    secret_access_key: str, bucket_name: str):
           # Use boto3 with R2 endpoint
           self.s3 = boto3.client('s3',
               endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
               aws_access_key_id=access_key_id,
               aws_secret_access_key=secret_access_key
           )
   ```

3. **Add LocalBlobBackend** for development (filesystem-based)

4. **Add factory function**:
   ```python
   def get_blob_storage(url: str = None) -> BlobStorage:
       url = url or os.getenv("BLOB_STORAGE_URL")
       if url and url.startswith("r2://"):
           return R2Backend.from_url(url)
       return LocalBlobBackend("data/blobs")
   ```

5. **Environment configuration** in `.env.example`:
   ```
   # Blob Storage (for PDFs, audio, transcripts)
   # BLOB_STORAGE_URL=r2://account_id/bucket_name
   # R2_ACCESS_KEY_ID=...
   # R2_SECRET_ACCESS_KEY=...
   ```

## Install Dependencies

```bash
pip install boto3
```

## Tests to Run

```bash
pytest packages/civic/tests/test_storage_protocols.py -v
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `BlobStorage` protocol defined in storage/blob.py
- [ ] `R2Backend` implements BlobStorage with boto3
- [ ] `LocalBlobBackend` for local development
- [ ] `get_blob_storage()` factory function
- [ ] Environment variables documented in .env.example
- [ ] Basic tests for upload/download/list
