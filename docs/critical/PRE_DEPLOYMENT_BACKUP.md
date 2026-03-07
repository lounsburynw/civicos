# Pre-Deployment Backup Procedure

> **Claude Code:** Run `/db-backup` for PostgreSQL backups (selective or full) and `/blob-backup` for R2 blob storage management.

**Last Updated:** 2025-12-11
**Time Required:** 5-10 minutes
**Related:** [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md), [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md)

This procedure must be followed before every production deployment. It ensures you have a known-good backup to restore from if the deployment causes issues.

## Quick Reference

```bash
# 1. Create backup
fly ssh console -a civic-api -C "python scripts/backup.py"

# 2. Verify backup exists
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# 3. Verify backup integrity
fly ssh console -a civic-api -C "python scripts/backup.py --verify FILENAME"

# 4. (Optional) Download locally
fly ssh sftp get /app/data/backups/FILENAME ./backups/
```

---

## Full Procedure

### Step 1: Pre-Backup Checks (1 min)

Before creating a backup, verify the environment:

```bash
# Verify you can access production
fly status -a civic-api
```

**Expected:** App shows "started" state with passing health checks.

```bash
# Check current disk usage (ensure space for backup)
fly ssh console -a civic-api -C "df -h /app/data"
```

**Expected:** Less than 80% disk usage. If higher, run `python scripts/backup.py --clean` first.

```bash
# Verify databases are healthy
fly ssh console -a civic-api -C "python scripts/backup.py --status"
```

**Expected:** Both databases show "OK" status.

### Step 2: Create Backup (1-2 min)

```bash
fly ssh console -a civic-api -C "python scripts/backup.py"
```

**Expected output:**
```
Creating backup...
  Backing up civic_state.db... OK
  Backing up civic_participation.db... OK
Backup complete:
  civic_state_20251211_143052.db (2.1 MB)
  civic_participation_20251211_143052.db (1.5 MB)
```

**Record the backup filenames** for reference during deployment.

### Step 3: Verify Backup Created (30 sec)

```bash
fly ssh console -a civic-api -C "python scripts/backup.py --list"
```

**Verify:**
- [ ] New backup files appear at top of list
- [ ] Timestamps match current time
- [ ] File sizes are reasonable (>100KB for populated databases)

### Step 4: Verify Backup Integrity (30 sec)

```bash
# Verify state database backup
fly ssh console -a civic-api -C "python scripts/backup.py --verify civic_state_YYYYMMDD_HHMMSS.db"

# Verify participation database backup
fly ssh console -a civic-api -C "python scripts/backup.py --verify civic_participation_YYYYMMDD_HHMMSS.db"
```

**Expected output for each:**
```
Verifying backup: civic_state_YYYYMMDD_HHMMSS.db
  File exists: Yes
  Checksum valid: Yes
  SQLite integrity: OK
Backup is valid and can be restored.
```

**All three checks must pass:**
- [ ] File exists: Yes
- [ ] Checksum valid: Yes
- [ ] SQLite integrity: OK

### Step 5: (Optional) Download Local Copy (1-2 min)

For critical deployments or if you want an off-server backup:

```bash
# Create local backups directory if needed
mkdir -p ./backups

# Download both backup files
fly ssh sftp get /app/data/backups/civic_state_YYYYMMDD_HHMMSS.db ./backups/
fly ssh sftp get /app/data/backups/civic_participation_YYYYMMDD_HHMMSS.db ./backups/

# Download checksum files
fly ssh sftp get /app/data/backups/civic_state_YYYYMMDD_HHMMSS.db.sha256 ./backups/
fly ssh sftp get /app/data/backups/civic_participation_YYYYMMDD_HHMMSS.db.sha256 ./backups/
```

**Verify local checksums:**
```bash
cd backups
sha256sum -c civic_state_YYYYMMDD_HHMMSS.db.sha256
sha256sum -c civic_participation_YYYYMMDD_HHMMSS.db.sha256
```

### Step 6: Record Deployment Context

Before proceeding with deployment, note:

| Field | Value |
|-------|-------|
| Backup timestamp | YYYYMMDD_HHMMSS |
| Current release version | (from `fly releases -a civic-api | head -2`) |
| Deployer | Your name |
| Deployment reason | Brief description |

This helps correlate backups with deployments if rollback is needed.

---

## Troubleshooting

### "Permission denied" accessing files

```bash
# Check volume is mounted
fly ssh console -a civic-api -C "ls -la /app/data/"
```

If `/app/data/` is empty, the volume may not be mounted. Check `fly.toml` volume configuration.

### "Disk full" error

```bash
# Check disk usage
fly ssh console -a civic-api -C "df -h /app/data"

# Clean old backups per retention policy
fly ssh console -a civic-api -C "python scripts/backup.py --clean"
```

### Backup integrity check fails

If checksum validation fails:

1. Re-run the backup: `python scripts/backup.py`
2. If repeated failures, check disk health:
   ```bash
   fly ssh console -a civic-api -C "dmesg | tail -20"
   ```
3. Consider expanding volume if near capacity

### Cannot SSH to production

```bash
# Verify app is running
fly status -a civic-api

# Check your fly.io authentication
fly auth whoami

# Try restarting the machine
fly machine restart -a civic-api
```

---

## Verification Checklist

Complete this checklist before every deployment:

### Pre-Deployment Backup Checklist

- [ ] **Environment accessible:** `fly status -a civic-api` shows healthy
- [ ] **Disk space available:** Less than 80% used on `/app/data`
- [ ] **Databases healthy:** `--status` shows OK for both databases
- [ ] **Backup created:** `python scripts/backup.py` completed successfully
- [ ] **Backup listed:** New files visible in `--list` output
- [ ] **Integrity verified:** Both `--verify` checks passed
- [ ] **Backup filenames recorded:** Noted for rollback reference
- [ ] **(Optional) Local copy downloaded:** If critical deployment

**Only proceed with deployment after all required items are checked.**

---

## Rollback Reference

If deployment fails and rollback is needed:

```bash
# Quick restore command (replace with your recorded filenames)
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_YYYYMMDD_HHMMSS.db"
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_participation_YYYYMMDD_HHMMSS.db"
```

For complete rollback procedures including code rollback, see [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md).

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Full deployment procedures |
| [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md) | Rollback and restore procedures |
| [scripts/backup.py](../../scripts/backup.py) | Backup script source and options |
