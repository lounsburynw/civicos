# Backup Procedures

## Database (PostgreSQL)

Use the `/db-backup` slash command or run manually:

```bash
# Selective backup (specific tables)
pg_dump "$DATABASE_URL" -t meetings -t decisions -t transcripts > backup.sql

# Full backup
pg_dump "$DATABASE_URL" > full_backup.sql
```

### Pre-Deployment Backup

Before any Modal deploy, back up affected data:

```bash
/db-backup selective  # Tables that the deploy might affect
```

### Daily Schedule

Supabase provides automatic daily backups (Pro plan). For additional safety:
- Weekly full pg_dump to local storage
- Before any schema migration, full backup

## Blob Storage (R2)

Use the `/blob-backup` slash command for R2 operations:

```bash
/blob-backup status   # Check R2 contents
/blob-backup sync     # Sync to local backup
```

R2 stores: agenda PDFs, audio files, transcripts.

## Vector Embeddings

Vectors can be re-generated from source data, so they don't need separate backup. Re-index with:

```bash
modal run scripts/modal_ingest.py
```

Or use `/vectors reindex`.
