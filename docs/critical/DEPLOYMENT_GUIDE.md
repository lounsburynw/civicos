# Deployment Guide

> **Claude Code:** Run `/launch` to start dev servers locally, `/db-backup` before any destructive operation, and `/commit` to run critics before committing.

**Last Updated:** 2026-03-07

This guide provides step-by-step instructions for deploying the CivicOS platform on Modal. For architecture decisions and cost analysis, see [HOSTING_DECISION.md](./HOSTING_DECISION.md).

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [First-Time Deployment](#first-time-deployment)
5. [Updating Deployments](#updating-deployments)
6. [Data Operations](#data-operations)
7. [Post-Deployment Verification](#post-deployment-verification)
8. [Troubleshooting](#troubleshooting)
9. [Quick Reference Commands](#quick-reference-commands)
10. [Related Documentation](#related-documentation)

---

## Architecture Overview

CivicOS runs entirely on serverless infrastructure. There are no containers to manage, no volumes to provision, and no persistent disks.

```
                        CivicOS Production Architecture

 ┌──────────────────────────────────────────────────────────────────────┐
 │                          Modal (Serverless)                          │
 │                                                                      │
 │  civicos-api          HTTP API server (FastAPI)                      │
 │  civicos-mcp          MCP server (Model Context Protocol)            │
 │  civicos-relay        Coordination relay (voice, actions, sync)      │
 │  civicos-websocket    WebSocket server (real-time updates)           │
 │  civicos-vectors      GPU vector indexing (on-demand)                │
 │                                                                      │
 └──────────────┬──────────────────────┬────────────────────────────────┘
                │                      │
                ▼                      ▼
 ┌──────────────────────┐   ┌──────────────────────┐
 │  Supabase PostgreSQL  │   │   Cloudflare R2      │
 │                       │   │                      │
 │  - Civic data (SQL)   │   │  - PDFs (agendas)    │
 │  - pgvector embeddings│   │  - Audio (meetings)  │
 │  - Relay/coordination │   │  - Static assets     │
 │  - Automatic backups  │   │                      │
 └──────────────────────┘   └──────────────────────┘
```

### Data Layer

| Data | Storage | Details |
|------|---------|---------|
| Meetings, decisions, transcripts | Supabase PostgreSQL | Main database |
| Vector embeddings | Supabase pgvector | Semantic search |
| Coordination (voices, actions) | Supabase PostgreSQL | Relay database |
| PDFs, audio files | Cloudflare R2 | Blob storage |
| Secrets / env vars | Modal Secrets | Encrypted, injected at runtime |

### Benefits

- No infrastructure to manage -- Modal scales to zero when idle
- GPU access for vector indexing without provisioning machines
- Database backups handled by Supabase automatically
- Deployments are instant re-deploys of Python functions

---

## Prerequisites

### Required Tools

```bash
# 1. Install Modal CLI
pip install modal

# 2. Authenticate (opens browser)
modal setup

# 3. Verify installation
modal --version
```

### Required Accounts

| Service | Purpose | Sign Up |
|---------|---------|---------|
| [Modal](https://modal.com) | Serverless compute (API, relay, GPU) | modal.com |
| [Supabase](https://supabase.com) | PostgreSQL + pgvector database | supabase.com |
| [Cloudflare](https://cloudflare.com) | R2 blob storage | cloudflare.com |
| [OpenAI](https://platform.openai.com) | LLM API | platform.openai.com |

### Required Secrets

All secrets are stored in Modal as a single secret group called `civicos-secrets`. See [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) for rotation procedures.

| Secret | Required | Description |
|--------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection string (main DB) |
| `RELAY_DATABASE_URL` | Yes | Supabase PostgreSQL connection string (relay DB) |
| `BLOB_STORAGE_URL` | Yes | Cloudflare R2 endpoint |
| `CIVICOS_WEB_KEY` | Yes (prod) | API authentication key (`openssl rand -hex 32`) |
| `CIVICOS_CORS_ORIGINS` | Yes (prod) | Allowed frontend origins |

---

## Pre-Deployment Checklist

Complete these steps before every deployment.

### Code Verification

- [ ] All tests pass: `pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="`
- [ ] No uncommitted changes: `git status`
- [ ] On correct branch: `git branch --show-current`

### Backup (for updates only)

- [ ] Run database backup via `/db-backup` or:
  ```bash
  source civicos-env/bin/activate
  python scripts/db_backup.py --action selective
  ```

### Secrets Verification

- [ ] Verify all secrets are configured:
  ```bash
  modal secret list
  ```
- [ ] Confirm `civicos-secrets` appears in the list

---

## First-Time Deployment

Follow these steps for initial deployment. For updates, see [Updating Deployments](#updating-deployments).

### Step 1: Create Supabase Projects

1. Create **main database** project (civic data):
   - Enable pgvector extension: `CREATE EXTENSION IF NOT EXISTS vector;`
   - Note the connection string for `DATABASE_URL`

2. Create **relay database** project (coordination data):
   - Note the connection string for `RELAY_DATABASE_URL`
   - Use `db.PROJECT_REF.supabase.co:6543` pooler format

3. Run schema migrations:
   ```bash
   source civicos-env/bin/activate
   python scripts/migrate.py
   ```

### Step 2: Create Modal Secrets

```bash
modal secret create civicos-secrets \
  OPENAI_API_KEY="sk-proj-..." \
  DATABASE_URL="postgresql://..." \
  RELAY_DATABASE_URL="postgresql://..." \
  BLOB_STORAGE_URL="https://..." \
  CIVICOS_WEB_KEY="$(openssl rand -hex 32)" \
  CIVICOS_CORS_ORIGINS="https://your-frontend-domain.com"
```

Verify:
```bash
modal secret list
```

### Step 3: Deploy All Services

```bash
# Deploy API server
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py

# Deploy MCP server
modal deploy apps/civicos-mcp/modal_mcp.py

# Deploy relay
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py

# Deploy WebSocket server
modal deploy packages/civicos-services/src/civicos_services/servers/modal_websocket.py
```

Each command outputs the public URL for the deployed service.

### Step 4: Run Initial Vector Indexing

Vector indexing runs on Modal GPUs:

```bash
modal run scripts/modal_ingest.py
```

### Step 5: Verify Deployment

See [Post-Deployment Verification](#post-deployment-verification).

---

## Updating Deployments

Updating a Modal deployment is a single command per service. Modal handles zero-downtime rollover automatically.

### Deploy a Single Service

```bash
# Just re-run the deploy command for the changed service
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

### Deploy All Services

```bash
# API
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py

# MCP
modal deploy apps/civicos-mcp/modal_mcp.py

# Relay
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py

# WebSocket
modal deploy packages/civicos-services/src/civicos_services/servers/modal_websocket.py
```

### Update Secrets

```bash
# Update a specific secret value
modal secret create civicos-secrets \
  OPENAI_API_KEY="sk-proj-new-key..." \
  DATABASE_URL="postgresql://..." \
  RELAY_DATABASE_URL="postgresql://..." \
  BLOB_STORAGE_URL="https://..." \
  CIVICOS_WEB_KEY="existing-key" \
  CIVICOS_CORS_ORIGINS="https://your-domain.com"

# Re-deploy services to pick up new secrets
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

Note: `modal secret create` replaces the entire secret group. Include all values, not just the one you are changing.

---

## Data Operations

All data lives in Supabase PostgreSQL and Cloudflare R2. Data operations run via Modal or locally.

### Ingestion Pipeline

Use the `/ingest` command or run directly:

```bash
# Run ingestion pipeline on Modal (GPU-accelerated)
modal run scripts/modal_ingest.py

# Check ingestion status
source civicos-env/bin/activate
python -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, DataStatus, format_data_status
c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(format_data_status(status.summary()))
"
```

### Vector Indexing (GPU)

Vector embeddings are computed on Modal GPUs and stored in Supabase pgvector:

```bash
# Full re-index
modal run scripts/modal_ingest.py

# Check vector coverage
# Use /vector-coverage command or:
source civicos-env/bin/activate
python -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, VectorCoverage
c = CivicOS('city-san-rafael')
vc = VectorCoverage(c.storage, c._vectors, 'city-san-rafael')
print(vc.summary())
"
```

### Adding a New Jurisdiction

```bash
# 1. Run extraction for the new jurisdiction
source civicos-env/bin/activate
python -m civicos_extraction.scraper --jurisdiction city-new-name

# 2. Ingest data into PostgreSQL
python scripts/ingest.py --jurisdiction city-new-name

# 3. Generate vector embeddings on Modal GPU
modal run scripts/modal_ingest.py --jurisdiction city-new-name

# 4. Verify
python -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-new-name')
print(f'Decisions: {c.storage.get_decision_count(\"city-new-name\")}')
"
```

### Database Backups

Supabase provides automatic daily backups. For manual backups:

```bash
# Selective backup (specific tables)
python scripts/db_backup.py --action selective

# Full backup
python scripts/db_backup.py --action full
```

---

## Post-Deployment Verification

Run these checks after every deployment.

### Check Running Apps

```bash
modal app list
```

Expected: `civicos-api`, `civicos-mcp`, `civicos-relay`, `civicos-websocket` all showing as deployed.

### View Logs

```bash
# View logs for a specific app
modal app logs civicos-api

# Follow logs in real-time
modal app logs civicos-api --follow
```

### Test Health Endpoints

```bash
# API server health (URL from deploy output)
curl -s https://YOUR-MODAL-URL/health | jq .
# Expected: {"status": "healthy", ...}
```

### Test API Endpoints

```bash
# Test civic query
curl -s -H "Authorization: Bearer YOUR_CIVICOS_WEB_KEY" \
  https://YOUR-MODAL-URL/api/civic/city-san-rafael/whats-next | jq .
```

### Verify Database Connectivity

```bash
source civicos-env/bin/activate
python -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-san-rafael')
print(f'Backend: {type(c.storage).__name__}')
print(f'Decisions: {c.storage.get_decision_count(\"city-san-rafael\")}')
print(f'Meetings: {len(c.storage.get_meetings(\"city-san-rafael\"))}')
"
```

Expected: `Backend: PostgresBackend` with non-zero counts.

### External Monitoring

If UptimeRobot is configured (see [UPTIME_MONITORING.md](./UPTIME_MONITORING.md)):
- Verify monitors show "Up" status
- Check Supabase dashboard for database health

---

## Troubleshooting

### Deployment Fails

**Symptom:** `modal deploy` exits with an error.

**Solutions:**
```bash
# Check for Python import errors locally
source civicos-env/bin/activate
python -c "import civicos_services"

# Verify Modal CLI is authenticated
modal profile current

# Check Modal status page
# https://status.modal.com
```

### Service Not Responding

**Symptom:** Deployed URL returns errors or timeouts.

**Solutions:**
```bash
# Check app logs for errors
modal app logs civicos-api

# Verify the app is listed
modal app list

# Re-deploy
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

### Database Connection Errors

**Symptom:** "connection refused" or timeout errors in logs.

**Solutions:**
```bash
# Verify DATABASE_URL is in Modal secrets
modal secret list

# Test connection locally
source civicos-env/bin/activate
python -c "
from dotenv import load_dotenv; load_dotenv()
import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
print('Connected successfully')
conn.close()
"

# Re-create secrets if needed
modal secret create civicos-secrets ...
```

Common causes:
- Supabase project is paused (free tier pauses after inactivity)
- Connection string uses wrong pooler format
- Relay DB must use `db.PROJECT_REF.supabase.co:6543` format

### Secrets Not Available

**Symptom:** "Environment variable not set" errors in logs.

**Solutions:**
```bash
# List current secrets
modal secret list

# Re-create the secret group with all values
modal secret create civicos-secrets \
  OPENAI_API_KEY="..." \
  DATABASE_URL="..." \
  ...

# Re-deploy to pick up new secrets
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

### Vector Indexing Fails

**Symptom:** `modal run scripts/modal_ingest.py` errors out.

**Solutions:**
```bash
# Check logs for the run
modal app logs civicos-vectors

# Verify GPU availability (Modal handles this, but check for quota issues)
modal profile current

# Run with smaller batch for debugging
modal run scripts/modal_ingest.py --limit 10
```

### Rollback

Modal keeps previous deployments. To rollback:

```bash
# Re-deploy from a previous git commit
git checkout <previous-commit>
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
git checkout main
```

For detailed rollback procedures including database restore, see [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md).

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| Deploy API | `modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py` |
| Deploy MCP | `modal deploy apps/civicos-mcp/modal_mcp.py` |
| Deploy Relay | `modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py` |
| Deploy WebSocket | `modal deploy packages/civicos-services/src/civicos_services/servers/modal_websocket.py` |
| Run vector indexing | `modal run scripts/modal_ingest.py` |
| List running apps | `modal app list` |
| View logs | `modal app logs civicos-api` |
| List secrets | `modal secret list` |
| Create/update secrets | `modal secret create civicos-secrets KEY=value ...` |
| Check Modal auth | `modal profile current` |
| Database backup | `python scripts/db_backup.py --action selective` |
| Data status | `/data-status city-san-rafael` |
| Vector coverage | `/vector-coverage city-san-rafael` |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [HOSTING_DECISION.md](./HOSTING_DECISION.md) | Platform selection, architecture, cost analysis |
| [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) | All secrets configuration and rotation |
| [UPTIME_MONITORING.md](./UPTIME_MONITORING.md) | External monitoring setup |
| [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md) | Detailed rollback and data restore procedures |
| [PRE_DEPLOYMENT_BACKUP.md](./PRE_DEPLOYMENT_BACKUP.md) | Backup before deploy |
| [DAILY_BACKUP_SCHEDULE.md](./DAILY_BACKUP_SCHEDULE.md) | Ongoing backup schedule |
| [DATA_INGESTION_OPERATIONS.md](./DATA_INGESTION_OPERATIONS.md) | ETL operations |
| [VECTOR_RAG_SCHEMA.md](./VECTOR_RAG_SCHEMA.md) | Vector storage schema |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-11 | Use Fly.io | Initial choice for cost/feature balance |
| 2025-12-11 | SJC region | Closest to San Rafael pilot |
| 2025-12-16 | Hybrid data model | Bundle reference data in image, user data on volume |
| 2026-02 | Migrate to Modal | Serverless, GPU access for vectors, simpler than Fly.io |
| 2026-02 | Supabase PostgreSQL | Managed DB with pgvector, automatic backups, eliminates local SQLite/volumes |
