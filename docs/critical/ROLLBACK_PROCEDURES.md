# Rollback Procedures

**Last Updated:** 2025-12-11
**Platform:** Fly.io
**Related:** [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)

This guide provides step-by-step rollback procedures for the Civic platform. Use this when a deployment causes issues that require reverting to a previous state.

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [When to Roll Back](#when-to-roll-back)
3. [Quick Rollback (Code Only)](#quick-rollback-code-only)
4. [Full Rollback (Code + Data)](#full-rollback-code--data)
5. [Coordinated Two-App Rollback](#coordinated-two-app-rollback)
6. [Data-Only Restore](#data-only-restore)
7. [Post-Rollback Verification](#post-rollback-verification)
8. [Rollback Scenarios](#rollback-scenarios)
9. [Prevention Checklist](#prevention-checklist)

---

## Quick Reference

| Scenario | Time | Procedure |
|----------|------|-----------|
| Code bug, data OK | 5-10 min | [Quick Rollback](#quick-rollback-code-only) |
| Code + data corrupted | 15-20 min | [Full Rollback](#full-rollback-code--data) |
| Both apps affected | 10-15 min | [Coordinated Rollback](#coordinated-two-app-rollback) |
| Only data corrupted | 10-15 min | [Data-Only Restore](#data-only-restore) |

**Emergency commands:**
```bash
# List recent releases to find rollback target
fly releases -a civic-api

# Immediate rollback to previous version (vN = previous version number)
fly deploy -a civic-api --image registry.fly.io/civic-api:vN
```

---

## When to Roll Back

### Roll Back Immediately If:

- Health checks failing after deployment
- API returning 500 errors on critical endpoints
- WebSocket connections not establishing
- Database errors in logs (corruption, migration failures)
- Users reporting complete inability to use system

### Investigate Before Rolling Back If:

- Intermittent errors (may be transient)
- Performance degradation (may need scaling, not rollback)
- Single feature broken (may be quicker to hotfix)
- Errors existed before deployment (rollback won't help)

### Do Not Roll Back If:

- Issue is in external service (OpenAI, network)
- Issue is configuration/secrets (fix secrets instead)
- Data is corrupted but code is fine (use data restore only)

---

## Quick Rollback (Code Only)

Use when the new code is problematic but data is intact.

**Time estimate:** 5-10 minutes

### Step 1: Identify Target Version

```bash
# List recent releases
fly releases -a civic-api
```

**Example output:**
```
VERSION STABLE  TYPE     STATUS    DESCRIPTION              USER        DATE
v5      true    release  complete  Deploy image             you@...     1h ago
v4      true    release  complete  Deploy image             you@...     2d ago
v3      true    release  complete  Deploy image             you@...     5d ago
```

**Note:** Roll back to the most recent "complete" version before the problem started.

### Step 2: Deploy Previous Version

```bash
# Replace v4 with your target version
fly deploy -a civic-api --image registry.fly.io/civic-api:v4
```

**Expected output:**
```
==> Using image registry.fly.io/civic-api:v4
...
--> v6 deployed successfully
```

### Step 3: Verify Rollback

```bash
# Check health
curl -s https://civic-api.fly.dev/health | jq .

# Check logs for errors
fly logs -a civic-api -n 50
```

### Step 4: Document the Rollback

```bash
# Note what happened for post-mortem
echo "$(date): Rolled back from v5 to v4 due to [REASON]" >> rollback-log.txt
```

---

## Full Rollback (Code + Data)

Use when both code and data need to be reverted (e.g., bad migration corrupted data).

**Time estimate:** 15-20 minutes

**Prerequisites:**
- A known-good backup exists (check with `--list`)
- You know which code version matches that backup

### Step 1: Stop Traffic (Optional but Recommended)

```bash
# Scale down to prevent new writes during restore
fly scale count 0 -a civic-api
fly scale count 0 -a civic-websocket
```

### Step 2: List Available Backups

```bash
fly ssh console -a civic-api -C "python scripts/backup.py --list"
```

**Example output:**
```
Available backups:
  civic_state_20251211_143052.db (2.1 MB) - 2 hours ago
  civic_state_20251210_120000.db (2.0 MB) - 1 day ago
  civic_participation_20251211_143052.db (1.5 MB) - 2 hours ago
```

### Step 3: Verify Backup Integrity

```bash
# Verify the backup you want to restore
fly ssh console -a civic-api -C "python scripts/backup.py --verify civic_state_20251210_120000.db"
```

**Expected output:**
```
Verifying backup: civic_state_20251210_120000.db
  File exists: Yes
  Checksum valid: Yes
  SQLite integrity: OK
Backup is valid and can be restored.
```

### Step 4: Restore Data

```bash
# Restore databases (creates safety backup automatically)
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_20251210_120000.db"
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_participation_20251210_120000.db"
```

### Step 5: Roll Back Code Version

```bash
# Deploy the code version that matches your backup
fly deploy -a civic-api --image registry.fly.io/civic-api:v4
fly deploy -a civic-websocket --image registry.fly.io/civic-websocket:v4 --config fly.websocket.toml
```

### Step 6: Restart Services

```bash
# If you scaled down in Step 1
fly scale count 1 -a civic-api
fly scale count 1 -a civic-websocket
```

### Step 7: Verify

See [Post-Rollback Verification](#post-rollback-verification).

---

## Coordinated Two-App Rollback

The Civic platform runs two apps (civic-api and civic-websocket) that must stay in sync.

**Critical:** Both apps share a data volume and must run compatible versions.

### Step 1: Identify Compatible Versions

```bash
# Check releases for both apps
fly releases -a civic-api
fly releases -a civic-websocket
```

**Match by timestamp:** Deployments done together will have similar timestamps.

### Step 2: Create Safety Backup

```bash
fly ssh console -a civic-api -C "python scripts/backup.py"
```

### Step 3: Roll Back Both Apps

Execute these commands in sequence (not parallel) to avoid race conditions:

```bash
# Roll back API first
fly deploy -a civic-api --image registry.fly.io/civic-api:v4

# Wait for API to be healthy
fly status -a civic-api
# Confirm: "1 total, 1 passing"

# Then roll back WebSocket
fly deploy -a civic-websocket --image registry.fly.io/civic-websocket:v4 --config fly.websocket.toml
```

### Step 4: Verify Both Apps

```bash
# Check both health endpoints
curl -s https://civic-api.fly.dev/health | jq .status
curl -s https://civic-websocket.fly.dev/health | jq .status

# Check both are running
fly status -a civic-api
fly status -a civic-websocket
```

---

## Data-Only Restore

Use when code is fine but data was corrupted (e.g., by a bug that's now fixed).

**Time estimate:** 10-15 minutes

### Step 1: Create Safety Backup of Current State

```bash
# Even if corrupted, keep a copy for analysis
fly ssh console -a civic-api -C "python scripts/backup.py"
```

### Step 2: List and Select Backup

```bash
fly ssh console -a civic-api -C "python scripts/backup.py --list"
```

### Step 3: Restore Specific Database

```bash
# Restore state database
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_20251210_120000.db"

# Restore participation database
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_participation_20251210_120000.db"
```

### Step 4: Re-run Migrations (If Needed)

If the backup is from an older schema version:

```bash
fly ssh console -a civic-api -C "python scripts/migrate.py --status"
fly ssh console -a civic-api -C "python scripts/migrate.py"
```

**Note:** Migrations are idempotent and safe to re-run.

### Step 5: Verify Data

```bash
# Check databases are accessible
fly ssh console -a civic-api -C "python -c \"import sqlite3; print(sqlite3.connect('/app/data/civic_state.db').execute('SELECT COUNT(*) FROM events').fetchone())\""
```

---

## Post-Rollback Verification

Run these checks after any rollback.

### Health Checks

```bash
# Both apps healthy
curl -s https://civic-api.fly.dev/health | jq .
curl -s https://civic-websocket.fly.dev/health | jq .
```

**Expected:**
```json
{"status": "healthy", ...}
```

### API Functionality

```bash
# Test core endpoint (requires auth)
curl -s -H "Authorization: Bearer $CIVICOS_WEB_KEY" \
  https://civic-api.fly.dev/api/civic/san-rafael | jq .status
```

### Log Check

```bash
# Check for errors in recent logs
fly logs -a civic-api -n 100 | grep -i error

# Should return empty or only expected errors
```

### Database Integrity

```bash
fly ssh console -a civic-api -C "python scripts/backup.py --status"
```

**Expected:**
```
Database status:
  civic_state.db: OK (X records)
  civic_participation.db: OK (Y records)
Last backup: YYYY-MM-DD HH:MM:SS
```

### Monitoring Check

If UptimeRobot is configured:
- Verify monitors show "Up" status
- Check response time is normal

---

## Rollback Scenarios

### Scenario 1: Broken Migration

**Symptoms:**
- Deployment succeeds but app crashes
- Logs show "no such column" or "table already exists"
- Database errors on startup

**Solution:**
1. Do NOT re-run migrations
2. Restore from pre-deployment backup
3. Roll back code to version without migration
4. Fix migration script
5. Test migration locally before re-deploying

```bash
# 1. Identify backup taken before deployment
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# 2. Restore data
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_YYYYMMDD_HHMMSS.db"

# 3. Roll back code
fly deploy -a civic-api --image registry.fly.io/civic-api:vPREVIOUS
```

### Scenario 2: Memory/Performance Issue

**Symptoms:**
- Container restarts frequently
- OOM (Out of Memory) in logs
- Slow response times

**Solution:**
1. Roll back code first
2. Then investigate memory usage

```bash
# Quick rollback
fly deploy -a civic-api --image registry.fly.io/civic-api:vPREVIOUS

# After stable, check memory
fly scale show -a civic-api
fly logs -a civic-api | grep -i memory
```

### Scenario 3: API/WebSocket Version Mismatch

**Symptoms:**
- WebSocket connections fail
- "Protocol mismatch" errors
- Features work in API but not real-time

**Solution:**
Use [Coordinated Two-App Rollback](#coordinated-two-app-rollback) to ensure both apps are on compatible versions.

### Scenario 4: Data Corruption from Bug

**Symptoms:**
- Incorrect data in responses
- Users report missing or wrong information
- Database queries return unexpected results

**Solution:**
1. Fix or roll back the code causing corruption
2. Identify when corruption started
3. Restore from backup before corruption
4. Re-run migrations if schema changed

```bash
# 1. Roll back code
fly deploy -a civic-api --image registry.fly.io/civic-api:vPREVIOUS

# 2. Find clean backup
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# 3. Restore
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_YYYYMMDD_HHMMSS.db"
```

---

## Prevention Checklist

Before each deployment, reduce rollback risk:

### Code Review
- [ ] All tests pass: `pytest packages/civic/tests/ -q`
- [ ] Migration tested locally (if any)
- [ ] No breaking API changes (or coordinated with frontend)

### Backup
- [ ] Pre-deployment backup created:
  ```bash
  fly ssh console -a civic-api -C "python scripts/backup.py"
  ```
- [ ] Backup verified:
  ```bash
  fly ssh console -a civic-api -C "python scripts/backup.py --list"
  ```

### Deployment
- [ ] Know your current version: `fly releases -a civic-api | head -3`
- [ ] Deploy API first, verify, then WebSocket
- [ ] Watch logs during deployment: `fly logs -a civic-api`

### Post-Deployment
- [ ] Health checks passing
- [ ] Test key functionality
- [ ] Monitor for 10-15 minutes before declaring success

---

## Command Reference

| Task | Command |
|------|---------|
| List releases | `fly releases -a civic-api` |
| Roll back code | `fly deploy -a civic-api --image registry.fly.io/civic-api:vN` |
| Create backup | `fly ssh console -a civic-api -C "python scripts/backup.py"` |
| List backups | `fly ssh console -a civic-api -C "python scripts/backup.py --list"` |
| Verify backup | `fly ssh console -a civic-api -C "python scripts/backup.py --verify FILENAME"` |
| Restore backup | `fly ssh console -a civic-api -C "python scripts/backup.py --restore FILENAME"` |
| Check status | `fly status -a civic-api` |
| View logs | `fly logs -a civic-api -n 100` |
| Scale down | `fly scale count 0 -a civic-api` |
| Scale up | `fly scale count 1 -a civic-api` |

---

## Schema Migration Rollback

When a schema migration causes issues, you may need to reverse it. The migration system supports downgrade scripts.

### Migration File Convention

For reversible migrations, create paired files:

```
migrations/
  011_add_feature_x.sql           # Forward (up) migration
  011_add_feature_x.down.sql      # Reverse (down) migration
```

### Rollback a Schema Migration

**Step 1: Identify the migration to roll back**

```bash
python scripts/migrate.py --status
```

**Step 2: Create a backup before rolling back**

```bash
fly ssh console -a civic-api -C "python scripts/backup.py --compress"
```

**Step 3: Roll back the migration**

```bash
# Roll back the last N migrations
python scripts/migrate.py --rollback 1

# Or roll back to a specific version
python scripts/migrate.py --rollback-to 010
```

**Step 4: Verify the rollback**

```bash
python scripts/migrate.py --status
# Check that the migration is now marked as "pending" again
```

### Writing Reversible Migrations

**Good pattern - reversible:**
```sql
-- 011_add_voice_count.sql (forward)
ALTER TABLE issues ADD COLUMN voice_count INTEGER DEFAULT 0;
CREATE INDEX idx_issues_voice_count ON issues(voice_count);

-- 011_add_voice_count.down.sql (reverse)
DROP INDEX IF EXISTS idx_issues_voice_count;
ALTER TABLE issues DROP COLUMN voice_count;
```

**Caution - data-destructive:**
```sql
-- Dropping a column loses data! Consider:
-- 1. Rename to _deprecated instead of dropping
-- 2. Ensure backup exists before applying
-- 3. Document data loss in migration comments
```

### Migrations Without Downgrade Scripts

If a migration doesn't have a `.down.sql` file:

1. **Check if data can be restored from backup**
   ```bash
   fly ssh console -a civic-api -C "python scripts/backup.py --list"
   ```

2. **Roll back code to pre-migration version**
   ```bash
   fly deploy -a civic-api --image registry.fly.io/civic-api:vPREVIOUS
   ```

3. **Restore database from backup**
   ```bash
   fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_YYYYMMDD.db.gz --force"
   ```

4. **Verify migration status matches restored data**
   ```bash
   fly ssh console -a civic-api -C "python scripts/migrate.py --status"
   ```

### Temporal Data Recovery

The Civic schema uses **temporal versioning** for data safety:

- Tables have `valid_from` and `valid_to` columns
- Updates don't overwrite; they close old versions and insert new
- Point-in-time queries can recover historical state

**Query historical state:**
```python
# Get data as of a specific datetime
from civicos import CivicOS
c = CivicOS("san-rafael")
c.what_happened("housing", as_of="2025-12-01T12:00:00")
```

**Direct SQL recovery:**
```sql
-- Find all versions of meetings before a date
SELECT * FROM meetings
WHERE valid_from <= '2025-12-01'
  AND (valid_to IS NULL OR valid_to > '2025-12-01');
```

### ChromaDB/Vector Index Rollback

Vector indices don't support migration rollback directly. To recover:

1. **Delete the collection:**
   ```python
   import chromadb
   client = chromadb.PersistentClient(path="data/chroma")
   client.delete_collection("legal_documents")
   ```

2. **Re-index from storage:**
   ```python
   from civic._internal.legal.embeddings import LegalEmbeddingsStore
   store = LegalEmbeddingsStore(persist_directory="data/chroma")
   store.index_from_storage()  # Rebuilds from SQLite source data
   ```

### Best Practices

1. **Always create backup before migrations**
   ```bash
   python scripts/backup.py --compress
   python scripts/migrate.py
   ```

2. **Test migrations locally first**
   ```bash
   cp data/civic_state.db data/civic_state.db.backup
   python scripts/migrate.py --dry-run
   python scripts/migrate.py
   ```

3. **Write downgrade scripts for destructive changes**
   - Column drops
   - Table drops
   - Index removals on large tables

4. **Keep migrations idempotent**
   - Use `IF NOT EXISTS` for creates
   - Use `IF EXISTS` for drops
   - Check before inserting seed data

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Deployment procedures |
| [HOSTING_DECISION.md](./HOSTING_DECISION.md) | Architecture and platform decisions |
| [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) | Secrets configuration |
| [scripts/backup.py](../../scripts/backup.py) | Backup/restore implementation |
| [scripts/migrate.py](../../scripts/migrate.py) | Database migrations |
