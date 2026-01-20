# SRCS R2 PDF Upload Investigation Results

## Overview
Explored Civic codebase to understand existing R2/blob storage upload patterns for meeting agendas. Task: Upload SRCS (San Rafael City Schools) agenda PDFs from Simbli to R2 for persistent storage.

## Key Files Identified

### R2 Blob Storage (Core Infrastructure)
- **Location**: `/packages/civicos/src/civicos/storage/blob.py` (lines 1-677)
- **Key Classes**:
  - `R2Backend`: Cloudflare R2 S3-compatible backend
  - `LocalBlobBackend`: Filesystem fallback for development
  - `BlobStorage` (Protocol): Common interface
  - `get_blob_storage()`: Factory function (lines 637-676)

### SRCS Ingestion Script
- **Location**: `/scripts/ingest_srcs.py` (lines 1-525)
- **Current State**: Ingests SRCS meetings from Simbli, downloads PDFs via MID, extracts chunks to PostgreSQL
- **Functions**:
  - `ingest_meetings()`: Scrapes Simbli meetings (lines 144-204)
  - `ingest_pdfs()`: Downloads PDFs, extracts chunks (lines 207-289)
  - `parse_pdf_to_chunks()`: PDF→chunks via PyMuPDF (lines 60-141)

### Simbli Client
- **Location**: `/packages/civicos-extraction/src/civic_extraction/clients/simbli.py` (lines 1+)
- **Key Data**: SimbliMeeting dataclass with `agenda_url`, `simbli_mid`, `minutes_url` fields

### PDF Handling
- **Chunk Extraction CLI**: `/packages/civicos-extraction/src/civic_extraction/cli/chunks.py`
  - Handles PDF download, validation, extraction (lines 1+)
  - `download_and_validate_pdf()`: Full validation with degenerate case detection
  - `validate_pdf_content()`: Checks for HTML vs PDF (lines 374-428)
- **PDF Parser**: `/packages/civicos/src/civic/_internal/meetings/pdf_parser.py`
  - `download_pdf()`: Simple download (lines 431-457)
  - `extract_pdf_urls_from_meeting_page()`: Scrapes HTML pages for PDF links (lines 460-586)

### Reference R2 Upload Scripts
- **CA Code Upload**: `/scripts/upload_cacode_r2.py` (lines 1-63)
- **US Code Upload**: `/scripts/upload_uscode_r2.py` (lines 1-54)
- **Pattern**: Both use `R2Backend.from_env()` → `r2.upload(key, data, content_type)`

## Current Data Flow (City Meetings - San Rafael)
1. ProudCity API discovers meetings → `agenda_url` stored in PostgreSQL
2. Modal chunk extraction reads meetings from Postgres
3. Downloads PDF from agenda_url
4. Parses PDF to text chunks
5. Stores chunks in PostgreSQL

## SRCS-Specific Differences
1. Uses Simbli (school board) instead of ProudCity (city council)
2. Has `simbli_mid` (special MID parameter) for PDF download
3. Uses `download_agenda_pdf_via_mid()` method in SimbliClient
4. Already has `parse_pdf_to_chunks()` in ingest_srcs.py

## R2 Backend Configuration
- **Environment Variables** (from blob.py lines 371-374):
  - `BLOB_STORAGE_URL`: r2://account_id/bucket_name
  - `R2_ACCESS_KEY_ID`: R2 API access key
  - `R2_SECRET_ACCESS_KEY`: R2 API secret
- **Init Method**: `R2Backend.from_env()` (lines 412-448)
- **API**: Uses boto3 S3-compatible client to `https://{account_id}.r2.cloudflarestorage.com`

## Upload Method Pattern (from blob.py lines 536-558)
```python
def upload(self, key: str, data: bytes, content_type=None, metadata=None) -> str:
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    if metadata:
        extra_args["Metadata"] = metadata
    
    self.s3.put_object(
        Bucket=self.bucket_name,
        Key=key,
        Body=data,
        **extra_args,
    )
    
    return f"r2://{self.account_id}/{self.bucket_name}/{key}"
```

## Existing Upload Code Examples
**CA Code Upload** (upload_cacode_r2.py lines 49-55):
```python
data = zip_path.read_bytes()
r2.upload(key, data, content_type="application/zip")
print(f"Uploaded to: r2://{r2.account_id}/{r2.bucket_name}/{key}")
```

**US Code Upload** (upload_uscode_r2.py lines 38-40):
```python
data = zip_path.read_bytes()
r2.upload(key, data, content_type="application/zip")
```

## Path Patterns Used in Codebase
- CA Code: `cacode/2025/pubinfo_2025.zip`
- US Code: `uscode/119-59/{filename}.zip`
- Suggested SRCS: `school-san-rafael/agendas/{meeting_id}.pdf`

## Integration Points

### PostgreSQL Meetings Table
- Has `agenda_url` column for meeting agendas
- Schema allows storing updated agenda URLs after R2 upload
- `store_chunks()` method already used by ingest_srcs.py

### Meeting Data Flow
- `ingest_srcs.py` lines 256-257: Downloads PDF via `client.download_agenda_pdf_via_mid(mid)`
- Line 263-277: Extracts chunks via `parse_pdf_to_chunks()`
- Line 271-276: Stores chunks via `backend.store_chunks()`

## Questions Answered

### 1. How do city meeting PDFs get uploaded to R2?
**Answer**: Not currently. City PDFs downloaded on-demand from agenda_url. R2 is only used for reference data (municipal code, legislation zips). School PDFs (SRCS) are not yet uploaded.

### 2. Path pattern used?
**Answer**: No existing pattern for meeting agendas. Reference: `{jurisdiction}/{document_type}/{identifier}.{ext}`

### 3. Library/client for R2 uploads?
**Answer**: `boto3` via `R2Backend` class (S3-compatible API)

### 4. How is agenda_url stored in meetings table?
**Answer**: Direct column in `meetings` table. Both city and SRCS use `agenda_url` field.

### 5. Current state of ingest_srcs.py?
**Answer**: Fully functional SRCS ingestion with:
- Meeting scraping from Simbli
- PDF download via MID
- Chunk extraction via PyMuPDF
- PostgreSQL storage
- pgvector indexing
- Dry-run and verification modes
