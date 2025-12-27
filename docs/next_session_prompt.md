# Session 375 Handoff

## P0: Set Up Supabase (Postgres + pgvector) - User has no local disk space

### Why Cloud-First
User doesn't have local disk space, so we need full cloud storage:
- **SQL**: Supabase Postgres (free 500MB)
- **Vectors**: Supabase pgvector (included)
- **Blobs**: Cloudflare R2 ✅ Done

### Task 1: Create Supabase Project
1. Go to https://supabase.com and sign up (free)
2. Create new project (name: `civic-pilot`, region: US West)
3. Get connection string from Settings → Database → Connection string (URI)
4. Add to `.env`: `DATABASE_URL=postgresql://...`

### Task 2: Implement PgVectorBackend
Currently a stub at `packages/civic/src/civic/storage/postgres_backend.py`.
Need to add pgvector support for embeddings.

Alternative: Use Qdrant Cloud free tier (1GB) if pgvector is too much work.

### Task 3: Migrate Data to Cloud
```bash
# After Supabase is configured
python scripts/migrate_storage.py \
  --target-postgres "$DATABASE_URL" \
  --target-r2 "r2://2bdd8aed2560f0a2632f4178adfe6d9f/civic-pilot"
```

### Cloud Config (R2 already in .env)
```
R2_ACCESS_KEY_ID=0eeaaf1f463636b068b2c78dad0af05c
R2_SECRET_ACCESS_KEY=***
BLOB_STORAGE_URL=r2://2bdd8aed2560f0a2632f4178adfe6d9f/civic-pilot
# Add after Supabase setup:
DATABASE_URL=postgresql://...
```

### Session 374 Accomplishments
1. Created `scripts/migrate_storage.py` for cloud migration
2. Fixed CLI pipeline bug (wasn't persisting to SQLite)
3. Set up Cloudflare R2 and verified connection
4. Tested end-to-end pipeline ingestion (17 meetings)

### Current Data (needs migration)
- 17 meetings, 186 decisions in SQLite
- 1340 issues
- Vectors not yet indexed
