# Pre-Deployment Backup Procedure

> **Claude Code:** Run `/db-backup` for PostgreSQL backups (selective or full) and `/blob-backup` for R2 blob storage management.

**Last Updated:** 2026-03-07
**Time Required:** 2-5 minutes
**Related:** [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md), [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md)

This procedure should be followed before significant production deployments. With Modal (serverless) and Supabase (managed PostgreSQL), most backup concerns are handled automatically, but verifying backup state before deploying is still good practice.

## Architecture Note

CivicOS deploys on **Modal** (serverless). There is no server-side state to back up — Modal containers are stateless and ephemeral. All persistent data lives in managed services:

| Data | Service | Backup |
|------|---------|--------|
| PostgreSQL (civic data, vectors) | Supabase | Automatic daily backups (Pro plan, PITR) |
| Blob storage (PDFs, audio) | Cloudflare R2 | Managed by Cloudflare (durable object storage) |
| Source code | Git (GitHub) | Standard git history |

## Quick Reference

```bash
# 1. Run local backup script (dumps from Supabase)
python scripts/backup.py

# 2. Verify backup
python scripts/backup.py --list

# 3. Check Supabase automatic backup status
# Visit: https://supabase.com/dashboard/project/lhtuixsynupnkejpahxk/settings/backups
```

---

## Full Procedure

### Step 1: Verify Supabase Backups Are Current (1 min)

Supabase Pro plan provides automatic daily backups with point-in-time recovery (PITR).

1. Open [Supabase Dashboard > Backups](https://supabase.com/dashboard/project/lhtuixsynupnkejpahxk/settings/backups)
2. Confirm the most recent backup completed successfully
3. Note the latest backup timestamp

### Step 2: Run Local Backup (Optional, 1-2 min)

For an additional local copy before critical deployments:

```bash
# Activate environment
source civicos-env/bin/activate

# Run backup script (connects to Supabase via DATABASE_URL)
python scripts/backup.py

# List available local backups
python scripts/backup.py --list
```

### Step 3: Verify Modal App State (30 sec)

```bash
# Check current Modal deployment
modal app list

# View specific app details
modal app show civicos-mcp
```

### Step 4: Record Deployment Context

Before proceeding with deployment, note:

| Field | Value |
|-------|-------|
| Supabase backup timestamp | (from dashboard) |
| Current git tag | (from `git tag --list "v*-pilot-*" \| tail -1`) |
| Deployer | Your name |
| Deployment reason | Brief description |

This helps correlate backups with deployments if rollback is needed.

---

## Troubleshooting

### Cannot connect to Supabase

```bash
# Verify DATABASE_URL is set
source civicos-env/bin/activate
python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; print('Set' if os.getenv('DATABASE_URL') else 'NOT SET')"

# Test connection
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-san-rafael')
print(f'Backend: {type(c.storage).__name__}')
print(f'Decisions: {c.storage.get_decision_count(\"city-san-rafael\")}')
"
```

### Backup script fails

1. Check that `.env` contains a valid `DATABASE_URL`
2. Verify network connectivity to Supabase
3. Check Supabase dashboard for service status

### Modal deployment issues

```bash
# Check Modal service status
modal app list

# View deployment logs
modal app logs civicos-mcp
```

---

## Verification Checklist

Complete this checklist before every deployment:

### Pre-Deployment Backup Checklist

- [ ] **Supabase backups current:** Dashboard shows recent successful backup
- [ ] **Database accessible:** Can connect and query via `DATABASE_URL`
- [ ] **(Optional) Local backup created:** `python scripts/backup.py` completed
- [ ] **Git state clean:** All changes committed and tagged
- [ ] **Deployment context recorded:** Timestamp, tag, deployer noted

**Only proceed with deployment after all required items are checked.**

---

## Rollback Reference

If deployment fails and rollback is needed:

```bash
# Modal deployments are atomic — redeploy the previous version
git checkout v0.2.0-pilot-YYYYMMDD
modal deploy apps/civicos-mcp/modal_app.py

# For database rollback, use Supabase PITR (point-in-time recovery)
# via the Supabase Dashboard > Backups > Restore to point in time
```

For complete rollback procedures including code rollback, see [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md).

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Full deployment procedures |
| [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md) | Rollback and restore procedures |
| [scripts/backup.py](../../scripts/backup.py) | Backup script source and options |
