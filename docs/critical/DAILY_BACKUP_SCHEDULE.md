# Daily Backup Schedule

**Status:** CONFIGURED
**Method:** GitHub Actions scheduled workflow
**Schedule:** Daily at 2:00 AM UTC (6:00 PM Pacific)

## Overview

Automated daily backups ensure data safety for the Civic platform. The backup system uses GitHub Actions to trigger backups on the Fly.io production server, with automatic retention policy enforcement and failure notifications.

## Configuration

### Schedule

| Setting | Value |
|---------|-------|
| Frequency | Daily |
| Time (UTC) | 02:00 |
| Time (Pacific) | 18:00 (6:00 PM) |
| Time (Eastern) | 21:00 (9:00 PM) |

The schedule runs during off-peak hours for San Rafael users, minimizing impact on system performance.

### Retention Policy

| Type | Retention |
|------|-----------|
| Daily backups | 7 days |
| Weekly backups | 4 weeks |

This policy balances data safety with storage costs:
- Short-term: Can restore to any day in the past week
- Long-term: Can restore to any week in the past month

### Storage Requirements

| Database | Typical Size | 11 Backups (7d+4w) |
|----------|--------------|---------------------|
| civic_state.db | ~2-5 MB | ~55 MB |
| civic_participation.db | ~1-2 MB | ~22 MB |
| **Total** | | **~77 MB** |

With gzip compression enabled, actual storage is typically 30-50% less.

## Workflow File

Location: `.github/workflows/daily-backup.yml`

### Key Features

1. **Scheduled Execution**: Cron-based trigger at 2:00 AM UTC
2. **Manual Trigger**: Can be run on-demand via GitHub Actions UI
3. **Compressed Backups**: Uses gzip compression to save space
4. **Retention Enforcement**: Automatically cleans old backups
5. **Failure Notifications**: Creates GitHub issue on failure

### Workflow Steps

```
1. Setup Fly.io CLI
2. Run backup script (both databases, compressed)
3. Verify backup integrity
4. Apply retention policy (clean old backups)
5. Report status
6. (On failure) Create/update GitHub issue
```

## Setup Requirements

### 1. FLY_API_TOKEN Secret

The workflow requires a `FLY_API_TOKEN` secret in the GitHub repository.

**To configure:**

```bash
# Generate a token (run locally)
fly tokens create deploy -a civic-api

# Add to GitHub repository secrets:
# Settings > Secrets and variables > Actions > New repository secret
# Name: FLY_API_TOKEN
# Value: (paste token)
```

### 2. Enable GitHub Actions

If not already enabled, go to repository Settings > Actions > General and ensure "Allow all actions" is selected.

### 3. Verify Fly.io Access

```bash
# Test SSH access
fly ssh console -a civic-api -C "echo 'SSH working'"

# Test backup script
fly ssh console -a civic-api -C "python scripts/backup.py --dry-run"
```

## Monitoring

### Check Workflow Status

1. Go to repository Actions tab
2. Select "Daily Backup" workflow
3. View recent runs and their status

### Verify Backups Manually

```bash
# List all backups
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# Check backup status
fly ssh console -a civic-api -C "python scripts/backup.py --status"

# Verify specific backup
fly ssh console -a civic-api -C "python scripts/backup.py --verify civic_state_20251211_020000.db.gz"
```

### Check Disk Space

```bash
fly ssh console -a civic-api -C "df -h /app/data"
fly ssh console -a civic-api -C "du -sh /app/data/backups"
```

## Failure Handling

### Automatic Notifications

When backups fail:
1. Workflow creates a GitHub issue with label `backup-failure`
2. Issue includes troubleshooting steps and workflow link
3. Subsequent failures add comments to existing open issue

### Manual Intervention

If automated backups fail repeatedly:

```bash
# 1. Check service status
fly status -a civic-api

# 2. Check logs
fly logs -a civic-api

# 3. Run backup manually
fly ssh console -a civic-api -C "python scripts/backup.py --compress"

# 4. If disk full, clean old backups
fly ssh console -a civic-api -C "python scripts/backup.py --clean"
```

### Common Issues

| Issue | Solution |
|-------|----------|
| FLY_API_TOKEN expired | Generate new token: `fly tokens create deploy -a civic-api` |
| Disk space full | Run `--clean` or increase volume size |
| Service not running | Restart: `fly apps restart civic-api` |
| SSH timeout | Check app health: `fly status -a civic-api` |

## Manual Trigger

To run backup outside the schedule:

### Via GitHub UI

1. Go to Actions > Daily Backup
2. Click "Run workflow"
3. Select branch (main)
4. Click "Run workflow"

### Via CLI

```bash
# Trigger workflow
gh workflow run daily-backup.yml

# Or run backup directly on server
fly ssh console -a civic-api -C "python scripts/backup.py --compress"
```

## Integration with Other Procedures

### Pre-Deployment Backup

Daily backups complement but do not replace pre-deployment backups:
- **Daily backups**: Automated, scheduled, for disaster recovery
- **Pre-deployment backups**: Manual, before each deploy, for rollback

See [PRE_DEPLOYMENT_BACKUP.md](PRE_DEPLOYMENT_BACKUP.md) for pre-deployment procedures.

### Rollback Procedures

To restore from a daily backup:

```bash
# 1. List available backups
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# 2. Restore (requires --force to overwrite)
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_state_20251210_020000.db.gz --force"

# 3. Restart service to pick up restored data
fly apps restart civic-api
```

See [ROLLBACK_PROCEDURES.md](ROLLBACK_PROCEDURES.md) for full rollback procedures.

## Cost Impact

**GitHub Actions:** Free for public repositories; 2,000 minutes/month for private

**Storage:** Included in Fly.io volume (3GB total, ~77MB for backups)

**Network:** Minimal - backups stay on server, only status output transferred

**Total additional cost:** $0/month

## Testing the Schedule

### Verify Cron Syntax

The cron expression `0 2 * * *` means:
- Minute: 0
- Hour: 2 (2 AM)
- Day of month: * (every)
- Month: * (every)
- Day of week: * (every)

### Test with Manual Run

1. Trigger workflow manually (see Manual Trigger above)
2. Verify backup appears in list
3. Check retention policy cleaned old backups
4. Confirm no GitHub issue created (success case)

### Simulate Failure (Optional)

To test failure notification:

```bash
# Temporarily break backup script (don't do in production!)
# Instead, review the failure notification code in the workflow
```
