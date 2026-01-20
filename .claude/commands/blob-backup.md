# Blob Storage Backup (R2)

Manage Cloudflare R2 blob storage for audio files, PDFs, and other binary assets.

## Usage

```
/blob-backup [action] [options]
```

**Actions:**
- `status` - Show R2 storage statistics
- `list [prefix]` - List files in R2
- `sync` - Sync R2 to local backup
- `verify` - Verify blob integrity

## Examples

```
/blob-backup status                          # Storage stats
/blob-backup list city-san-rafael/audio/     # List audio files
/blob-backup sync city-san-rafael            # Backup to local
/blob-backup verify city-san-rafael          # Check integrity
```

## R2 Storage Structure

```
civic-bucket/
├── city-san-rafael/
│   ├── audio/
│   │   ├── {video_id}.mp3          # Meeting audio files
│   │   └── ...
│   ├── pdfs/
│   │   ├── {agenda_id}.pdf         # Agenda packets
│   │   └── ...
│   └── thumbnails/
│       └── ...
├── school-san-rafael/
│   └── ...
└── manifests/
    └── ...
```

## Steps

### 1. Check R2 Status

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
import boto3

# R2 uses S3-compatible API
s3 = boto3.client('s3',
    endpoint_url=os.environ['BLOB_STORAGE_URL'].rsplit('/', 1)[0],
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY')
)

# List buckets
response = s3.list_buckets()
for bucket in response['Buckets']:
    print(f\"Bucket: {bucket['Name']}\")
"
```

### 2. List Files by Prefix

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
import boto3

s3 = boto3.client('s3',
    endpoint_url=os.environ['BLOB_STORAGE_URL'].rsplit('/', 1)[0],
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY')
)

bucket = 'civic'  # Adjust bucket name
prefix = 'city-san-rafael/audio/'

paginator = s3.get_paginator('list_objects_v2')
total_size = 0
count = 0

for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
    for obj in page.get('Contents', []):
        total_size += obj['Size']
        count += 1

print(f'Files: {count}')
print(f'Total size: {total_size / 1024 / 1024:.1f} MB')
"
```

### 3. Sync to Local Backup

```bash
# Using rclone (recommended for large syncs)
rclone sync r2:civic/city-san-rafael data/backups/r2/city-san-rafael \
  --progress \
  --checksum

# Or using AWS CLI with R2 endpoint
aws s3 sync s3://civic/city-san-rafael data/backups/r2/city-san-rafael \
  --endpoint-url $BLOB_STORAGE_URL
```

### 4. Verify Integrity

```bash
# Compare local manifest with R2
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
import json
from pathlib import Path

# Load local manifest
manifest_path = Path('data/youtube_audio/city_san_rafael_manifest.json')
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text())
    print(f'Local manifest: {len(manifest)} files')
else:
    print('No local manifest found')

# Compare with R2 (would need boto3 implementation)
"
```

## Backup Strategy

| Data Type | Size | Regenerable? | Backup Priority |
|-----------|------|--------------|-----------------|
| Audio files | ~100MB/meeting | Yes (re-download) | Low |
| PDFs | ~5MB/agenda | Yes (re-download) | Low |
| Transcripts | In PostgreSQL | Expensive ($2/meeting) | **High** |

**Key insight:** R2 stores source files that can be re-downloaded. The expensive asset (transcripts) is stored in PostgreSQL.

## R2 Versioning

Cloudflare R2 supports object versioning:

```bash
# Enable versioning on bucket (one-time)
# Via Cloudflare Dashboard: R2 → Bucket → Settings → Versioning

# List object versions
aws s3api list-object-versions \
  --bucket civic \
  --prefix city-san-rafael/audio/ \
  --endpoint-url $BLOB_STORAGE_URL
```

## Cost

| Operation | Cost |
|-----------|------|
| Storage | $0.015/GB/month |
| Class A (write) | $4.50/million |
| Class B (read) | $0.36/million |
| Egress | Free |

**Current estimate:** ~$1-2/month for San Rafael pilot data

## Recovery Scenarios

### Audio File Missing

```bash
# Re-download from YouTube
/ingest-audio city-san-rafael 1  # Will re-download if missing from R2
```

### PDF Missing

```bash
# Re-fetch from source
civic-extract chunks --jurisdiction city-san-rafael --refetch
```

### Full R2 Recovery

If R2 bucket is lost:
1. Audio: Re-download from YouTube (free, ~1 hour)
2. PDFs: Re-fetch from ProudCity/Legistar (~30 min)
3. Transcripts: Safe in PostgreSQL (not in R2)

## Prerequisites

```bash
# Install rclone for efficient syncs
brew install rclone

# Configure rclone for R2
rclone config
# → New remote → name: r2 → type: s3 → provider: Cloudflare
# → access_key_id: from Cloudflare R2 API tokens
# → secret_access_key: from Cloudflare R2 API tokens
# → endpoint: https://{account_id}.r2.cloudflarestorage.com
```
