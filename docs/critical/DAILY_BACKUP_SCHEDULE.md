# Daily Backup Schedule

**Status:** CONFIGURED
**Strategy:** Managed services (Supabase, Cloudflare R2, Git) + re-indexable vectors

## Overview

CivicOS runs entirely on managed serverless infrastructure (Modal, Supabase, Cloudflare R2). There are no server volumes or local state to back up. Each data layer has its own backup strategy aligned with its managed service.

## Backup Strategy by Data Layer

### 1. PostgreSQL (Supabase) — Automatic

| Setting | Value |
|---------|-------|
| **Provider** | Supabase (Pro plan) |
| **Method** | Automatic daily backups with point-in-time recovery (PITR) |
| **Retention** | 7 days (PITR), daily snapshots retained per Supabase plan |
| **Scope** | All tables: meetings, decisions, transcripts, chunks, issues, budget_items, municipal_code, legislation, vector_embeddings, coordination tables |
| **Action required** | None — fully managed |

**To access backups:**
1. Go to Supabase Dashboard > Project > Database > Backups
2. Select a restoration point
3. Supabase handles the restore

**Manual export (optional):**
```bash
# Export via pg_dump for offline archive
pg_dump "$DATABASE_URL" --no-owner --no-acl -F c -f civicos_backup_$(date +%Y%m%d).dump
```

### 2. Blob Storage (Cloudflare R2) — Durable

| Setting | Value |
|---------|-------|
| **Provider** | Cloudflare R2 |
| **Content** | PDFs, audio files, agenda packets |
| **Durability** | 99.999999999% (11 nines, S3-compatible) |
| **Action required** | None — R2 is inherently durable storage |

R2 does not provide automatic versioning by default, but the data is source-of-record. If needed, enable bucket versioning in Cloudflare dashboard.

### 3. Vector Embeddings — Re-indexable

| Setting | Value |
|---------|-------|
| **Storage** | Supabase pgvector (backed up with PostgreSQL above) |
| **Recovery method** | Re-index from source data on Modal GPU |
| **Time to rebuild** | ~15-30 minutes for full re-index |

Vectors are derived data. If embeddings are lost or corrupted, they can be regenerated:
```bash
# Re-index all vectors on Modal GPU
modal run scripts/modal_ingest.py --jurisdiction city-san-rafael --vectors-only
```

### 4. Application Code — Git

| Setting | Value |
|---------|-------|
| **Provider** | GitHub |
| **Method** | Git version control |
| **Action required** | None — Modal is serverless, no server-side state |

Modal deploys are stateless and built from the Git repo at deploy time. There is no persistent server state to back up.

## Monitoring Backups

### Check Supabase Backup Status

1. Go to Supabase Dashboard > Project > Database > Backups
2. Verify most recent backup completed successfully
3. Check PITR availability window

### Check R2 Storage

```bash
# Use the /blob-backup command for R2 management
/blob-backup status
```

### Verify Data Integrity

```bash
# Run data status check
source civicos-env/bin/activate
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, DataStatus, format_data_status
c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(format_data_status(status.summary()))
"
```

## Disaster Recovery

| Scenario | Recovery Method | RTO |
|----------|----------------|-----|
| Database corruption | Supabase PITR restore | ~10 minutes |
| Vector embedding loss | Re-index on Modal GPU | ~30 minutes |
| Blob storage loss | Extremely unlikely (11 nines durability) | N/A |
| Full re-deploy needed | `modal deploy` from Git | ~5 minutes |

## Integration with Other Procedures

### Pre-Deployment

No pre-deployment backup needed — Modal deployments are stateless and Supabase data is unaffected by code deploys.

See [PRE_DEPLOYMENT_BACKUP.md](PRE_DEPLOYMENT_BACKUP.md) for historical reference.

### Rollback Procedures

See [ROLLBACK_PROCEDURES.md](ROLLBACK_PROCEDURES.md) for full rollback procedures.

## Cost Impact

| Component | Cost |
|-----------|------|
| Supabase backups | Included in Pro plan ($25/month) |
| R2 durability | Included in R2 pricing (~$5/month) |
| Vector re-indexing | Modal GPU cost if needed (~$1-2 per full re-index) |
| **Total additional cost** | **$0/month** (included in existing services) |
