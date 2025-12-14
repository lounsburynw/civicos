# Deployment Guide

**Last Updated:** 2025-12-11
**Platform:** Fly.io
**Region:** SJC (San Jose - closest to San Rafael pilot)

This guide provides step-by-step instructions for deploying the Civic platform. For architecture decisions and cost analysis, see [HOSTING_DECISION.md](./HOSTING_DECISION.md).

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [First-Time Deployment](#first-time-deployment)
4. [Updating an Existing Deployment](#updating-an-existing-deployment)
5. [Post-Deployment Verification](#post-deployment-verification)
6. [Troubleshooting](#troubleshooting)
7. [Related Documentation](#related-documentation)

---

## Prerequisites

### Required Tools

```bash
# 1. Install Fly CLI
curl -L https://fly.io/install.sh | sh

# 2. Verify installation
fly version
# Expected: fly v0.x.x

# 3. Authenticate (opens browser)
fly auth login
```

### Required Accounts

| Service | Purpose | Sign Up |
|---------|---------|---------|
| Fly.io | Hosting platform | [fly.io/app/sign-up](https://fly.io/app/sign-up) |
| OpenAI | LLM API | [platform.openai.com](https://platform.openai.com) |

### Required Secrets

Before deployment, gather these values. See [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) for details.

| Secret | Required | How to Generate |
|--------|----------|-----------------|
| `OPENAI_API_KEY` | Yes | From OpenAI dashboard |
| `CIVIC_WEB_KEY` | Yes (prod) | `openssl rand -hex 32` |
| `CIVIC_CORS_ORIGINS` | Yes (prod) | Your frontend domain(s) |

---

## Pre-Deployment Checklist

Complete these steps before every deployment:

### Code Verification

- [ ] All tests pass locally: `pytest packages/civic/tests/ -q`
- [ ] No uncommitted changes: `git status`
- [ ] On correct branch: `git branch --show-current`
- [ ] Docker builds successfully: `docker build -t civic-test .`

### Backup (for updates only)

- [ ] Run pre-deployment backup:
  ```bash
  # On production server
  fly ssh console -a civic-api -C "python scripts/backup.py"

  # Download backup locally
  fly ssh sftp get /app/data/backups/latest.tar.gz ./backups/
  ```

### Secrets Verification

- [ ] Verify all secrets are configured:
  ```bash
  fly secrets list -a civic-api
  fly secrets list -a civic-websocket
  ```

---

## First-Time Deployment

Follow these steps for initial deployment only. For updates, see [Updating an Existing Deployment](#updating-an-existing-deployment).

### Step 1: Create Fly.io Apps

```bash
# Create both applications
fly apps create civic-api
fly apps create civic-websocket

# Verify creation
fly apps list
```

**Expected output:**
```
NAME            OWNER           STATUS  PLATFORM
civic-api       personal        pending machines
civic-websocket personal        pending machines
```

### Step 2: Create Persistent Volumes

Data persistence requires volumes. Both apps share data via identical volumes in the same region.

```bash
# Create volume for API server (3GB)
fly volumes create civic_data --region sjc --size 3 -a civic-api

# Create volume for WebSocket server (3GB)
fly volumes create civic_data --region sjc --size 3 -a civic-websocket
```

**Expected output:**
```
        ID: vol_xxxxxxxxxxxxx
      Name: civic_data
       App: civic-api
    Region: sjc
      Zone: xxxx
   Size GB: 3
 Encrypted: true
Created at: ...
```

**Verify volumes:**
```bash
fly volumes list -a civic-api
fly volumes list -a civic-websocket
```

### Step 3: Configure Secrets

Set required secrets for both applications:

```bash
# API server secrets
fly secrets set \
  OPENAI_API_KEY="sk-proj-..." \
  CIVIC_WEB_KEY="$(openssl rand -hex 32)" \
  CIVIC_CORS_ORIGINS="https://your-frontend-domain.com" \
  -a civic-api

# WebSocket server secrets (same values)
fly secrets set \
  OPENAI_API_KEY="sk-proj-..." \
  CIVIC_WEB_KEY="your-civic-web-key" \
  -a civic-websocket
```

**Verify secrets are set:**
```bash
fly secrets list -a civic-api
```

**Expected output:**
```
NAME                    DIGEST                  CREATED AT
CIVIC_CORS_ORIGINS      xxxxxxxx                ...
CIVIC_WEB_KEY           xxxxxxxx                ...
OPENAI_API_KEY          xxxxxxxx                ...
```

### Step 4: Deploy Applications

Deploy both applications:

```bash
# Deploy API server (uses fly.toml)
fly deploy -a civic-api

# Deploy WebSocket server (uses fly.websocket.toml)
fly deploy -a civic-websocket --config fly.websocket.toml
```

**Expected output for successful deployment:**
```
==> Building image
...
==> Pushing image
...
==> Creating release
...
==> Monitoring deployment
 1 desired, 1 placed, 1 healthy, 0 unhealthy [health checks: 1 total, 1 passing]
--> v1 deployed successfully
```

### Step 5: Initialize Database (First Time Only)

SSH into the container and run migrations:

```bash
# Connect to API server
fly ssh console -a civic-api

# Inside container: check migration status
python scripts/migrate.py --status

# Run migrations if needed
python scripts/migrate.py

# Exit container
exit
```

### Step 6: Verify Deployment

See [Post-Deployment Verification](#post-deployment-verification) for complete verification steps.

---

## Updating an Existing Deployment

For routine updates after initial deployment.

### Step 1: Pre-Update Backup

```bash
# Create backup before any changes
fly ssh console -a civic-api -C "python scripts/backup.py"

# Verify backup was created
fly ssh console -a civic-api -C "python scripts/backup.py --list"
```

### Step 2: Deploy Updates

```bash
# Deploy API server
fly deploy -a civic-api

# Deploy WebSocket server
fly deploy -a civic-websocket --config fly.websocket.toml
```

### Step 3: Monitor Deployment

Watch the deployment progress:

```bash
# Real-time logs during deployment
fly logs -a civic-api

# Check deployment status
fly status -a civic-api
```

### Step 4: Run Migrations (If Needed)

Only if schema changes are included:

```bash
fly ssh console -a civic-api -C "python scripts/migrate.py --status"
fly ssh console -a civic-api -C "python scripts/migrate.py"
```

### Step 5: Verify

See [Post-Deployment Verification](#post-deployment-verification).

---

## Post-Deployment Verification

Run these checks after every deployment.

### Check Application Status

```bash
# Check both apps are running
fly status -a civic-api
fly status -a civic-websocket
```

**Expected output:**
```
App
  Name     = civic-api
  Owner    = personal
  Hostname = civic-api.fly.dev
  Platform = machines

Machines
PROCESS ID              VERSION REGION  STATE   HEALTH CHECKS   LAST UPDATED
app     xxxxxxxxxxxxx   1       sjc     started 1 total, 1 passing ...
```

### Test Health Endpoints

```bash
# API server health
curl -s https://civic-api.fly.dev/health | jq .
# Expected: {"status": "healthy", ...}

# WebSocket server health
curl -s https://civic-websocket.fly.dev/health | jq .
# Expected: {"status": "healthy", ...}
```

### Test API Endpoints

```bash
# Test events endpoint (requires auth)
curl -s -H "Authorization: Bearer YOUR_CIVIC_WEB_KEY" \
  https://civic-api.fly.dev/api/events | jq .

# Test civic info
curl -s -H "Authorization: Bearer YOUR_CIVIC_WEB_KEY" \
  https://civic-api.fly.dev/api/civic/san-rafael | jq .
```

### Check Logs for Errors

```bash
# Recent logs (last 100 lines)
fly logs -a civic-api -n 100

# Filter for errors
fly logs -a civic-api | grep -i error
```

### Verify Data Persistence

```bash
# Check database files exist
fly ssh console -a civic-api -C "ls -la /app/data/*.db"

# Check vector store
fly ssh console -a civic-api -C "ls -la /app/data/pilot/vectors/"
```

### External Monitoring Check

If UptimeRobot is configured (see [UPTIME_MONITORING.md](./UPTIME_MONITORING.md)):
- Log into UptimeRobot dashboard
- Verify monitors show "Up" status

---

## Troubleshooting

### Deployment Fails

**Symptom:** `fly deploy` exits with error

**Solutions:**
```bash
# Check build logs
fly logs -a civic-api

# Verify Dockerfile builds locally
docker build -t civic-test .

# Check for resource issues
fly scale show -a civic-api
```

### Health Checks Failing

**Symptom:** Deployment hangs at "waiting for health checks"

**Solutions:**
```bash
# Check application logs
fly logs -a civic-api

# Verify health endpoint locally
curl http://localhost:8001/health

# Check container is starting
fly status -a civic-api
```

### Cannot Connect to Database

**Symptom:** SQLite errors in logs

**Solutions:**
```bash
# Check volume is mounted
fly ssh console -a civic-api -C "df -h /app/data"

# Check database permissions
fly ssh console -a civic-api -C "ls -la /app/data/*.db"

# Verify SQLite integrity
fly ssh console -a civic-api -C "python scripts/backup.py --status"
```

### Secrets Not Available

**Symptom:** "Environment variable not set" errors

**Solutions:**
```bash
# List current secrets
fly secrets list -a civic-api

# Re-set a secret
fly secrets set OPENAI_API_KEY="sk-proj-..." -a civic-api

# Redeploy to pick up new secrets
fly deploy -a civic-api
```

### Out of Memory

**Symptom:** Container restarts, OOM in logs

**Solutions:**
```bash
# Check current memory
fly scale show -a civic-api

# Increase memory (costs more)
fly scale memory 512 -a civic-api
```

### Volume Full

**Symptom:** Write errors, backup failures

**Solutions:**
```bash
# Check disk usage
fly ssh console -a civic-api -C "df -h /app/data"

# Clean old backups
fly ssh console -a civic-api -C "python scripts/backup.py --clean"

# Expand volume (requires downtime)
fly volumes extend vol_xxxxx --size 5 -a civic-api
```

### Rollback to Previous Version

If a deployment causes issues:

```bash
# List recent releases
fly releases -a civic-api

# Rollback to specific version
fly deploy -a civic-api --image registry.fly.io/civic-api:vN
```

For detailed rollback procedures including data restore and coordinated two-app rollback, see [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md).

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| Deploy API | `fly deploy -a civic-api` |
| Deploy WebSocket | `fly deploy -a civic-websocket --config fly.websocket.toml` |
| View logs | `fly logs -a civic-api` |
| SSH into container | `fly ssh console -a civic-api` |
| Check status | `fly status -a civic-api` |
| List secrets | `fly secrets list -a civic-api` |
| Set secret | `fly secrets set KEY=value -a civic-api` |
| Run backup | `fly ssh console -a civic-api -C "python scripts/backup.py"` |
| Check health | `curl https://civic-api.fly.dev/health` |
| View releases | `fly releases -a civic-api` |
| Check billing | `fly billing` |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [HOSTING_DECISION.md](./HOSTING_DECISION.md) | Platform selection, architecture, cost analysis |
| [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) | All secrets configuration and rotation |
| [UPTIME_MONITORING.md](./UPTIME_MONITORING.md) | External monitoring setup |
| [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md) | Detailed rollback and data restore procedures |
| [fly.toml](../../fly.toml) | API server Fly.io configuration |
| [fly.websocket.toml](../../fly.websocket.toml) | WebSocket server Fly.io configuration |
| [scripts/backup.py](../../scripts/backup.py) | Backup/restore operations |
| [scripts/migrate.py](../../scripts/migrate.py) | Database migrations |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-11 | Use Fly.io | Best cost/feature balance (<$7/mo budget) |
| 2025-12-11 | SJC region | Closest to San Rafael pilot |
| 2025-12-11 | 3GB volumes | Sufficient for SQLite + ChromaDB + growth |
| 2025-12-11 | Separate apps | Independent scaling, clearer health checks |
