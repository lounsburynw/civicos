# Rollback Procedures

## Modal Services

Modal keeps previous deployments. To rollback:

```bash
# List recent deployments
modal app list

# Redeploy from a previous commit
git checkout <commit-hash>
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
git checkout main
```

## Database

If a migration goes wrong:

1. Restore from the pre-deployment backup:
   ```bash
   psql "$DATABASE_URL" < backup.sql
   ```

2. Or use Supabase's point-in-time recovery (Pro plan).

## Vector Embeddings

Vectors are derived from source data. Re-index from scratch:

```bash
modal run scripts/modal_ingest.py
```

## Extension

The extension is loaded unpacked (no auto-update). To rollback:

```bash
git checkout <commit-hash>
cd apps/civicos-extension && npm run build
# Reload in chrome://extensions
```
