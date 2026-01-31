# Hosting Decision: Fly.io + Modal

**Decision Date:** 2025-12-11 (Fly.io), 2026-01-30 (Modal addition)
**Status:** APPROVED
**Budget Constraint:** <$25/month total operational

## Summary

CivicOS uses a **two-tier hosting strategy**:

1. **Fly.io** (~$5/mo) — Web services: REST API, WebSocket server, Vue frontend
2. **Modal** (~$5-15/mo) — Compute: Relay worker, MCP server, vector indexing

This separation reflects the different workload patterns:
- Web services need always-on, low-latency response
- Compute workloads are bursty, benefit from serverless scaling, may need GPU

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLY.IO (Web Tier)                                  │
│                           ~$7/month                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌────────┐ │
│  │   civic-api     │  │ civic-websocket │  │  civicos-mcp    │  │  Vue   │ │
│  │   (FastAPI)     │  │   (Socket.IO)   │  │   (MCP HTTP)    │  │Frontend│ │
│  │   Port 8001     │  │   Port 8002     │  │   Port 8080     │  │        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └────────┘ │
│                                                     │                       │
│                               Serves Claude.ai + ChatGPT                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Queries
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SUPABASE (Storage)                                 │
│                           Free tier                                          │
│  ┌─────────────────┐    ┌─────────────────┐                                │
│  │  Main Database  │    │ Relay Database  │                                │
│  │  (civic data)   │    │ (coordination)  │                                │
│  └─────────────────┘    └─────────────────┘                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Cron triggers
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MODAL (Compute Tier)                               │
│                           ~$5-15/month                                       │
│  ┌─────────────────┐                        ┌─────────────────┐            │
│  │  Relay Worker   │                        │ Vector Indexer  │            │
│  │  (cron: 5min)   │                        │    (GPU)        │            │
│  │  • Event emit   │                        │  • Embeddings   │            │
│  │  • Match subs   │                        │  • Re-indexing  │            │
│  │  • Deliver      │                        │                 │            │
│  └─────────────────┘                        └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Current deployment (Jan 2026):**
- MCP server: Fly.io (`https://civicos-mcp.fly.dev/mcp`) - primary
- MCP server: Modal (`apps/civicos-mcp/modal_app.py`) - alternative with full parity
- Relay worker: Modal (to be deployed)
- Vector indexing: Modal (existing)

**MCP Server Deployment Options:**

| Platform | URL | Pros | Cons |
|----------|-----|------|------|
| **Fly.io** (primary) | `civicos-mcp.fly.dev/mcp` | Always-on, consistent with web tier | ~$2/mo fixed cost |
| **Modal** (alternative) | Deploy via `modal deploy` | Serverless scaling, consolidation | Cold starts without keep_warm |

Both deployments have full feature parity (17+ tools, input validation, federation support).
To switch to Modal as primary, deploy with `modal deploy apps/civicos-mcp/modal_app.py`.

---

## Fly.io (Web Tier)

Fly.io hosts the always-on web services for the Jan 2026 San Rafael pilot.

## Why Fly.io

### Cost Analysis

| Service | Resource | Monthly Cost |
|---------|----------|--------------|
| civic-api | shared-cpu-1x, 256MB | ~$1.94 |
| civic-websocket | shared-cpu-1x, 256MB | ~$1.94 |
| Persistent volume | 3GB (SQLite + ChromaDB) | ~$0.45 |
| Data transfer | ~2GB egress | ~$0.40 |
| **Total** | | **~$4.73/month** |

This leaves ~$2.27/month buffer for traffic spikes and scaling.

### Technical Fit

1. **Docker Native** - Direct deployment from existing Dockerfile
2. **Persistent Volumes** - SQLite databases survive container restarts
3. **WebSocket Support** - Native support for Socket.IO connections
4. **Health Checks** - Built-in monitoring with our existing health endpoint
5. **Geographic Distribution** - Can deploy to regions close to San Rafael (SJC)
6. **Simple Scaling** - Scale up instances with `fly scale count`

### Comparison with Alternatives

| Platform | Est. Cost | Pros | Cons | Decision |
|----------|-----------|------|------|----------|
| **Fly.io** | $4-5/mo | Docker native, SQLite volumes, transparent pricing | Requires fly CLI learning | **SELECTED** |
| Railway | $5-8/mo | Simple UI, GitHub integration | Less transparent pricing, can spike | Too risky |
| Render | $7-10/mo | Managed PostgreSQL | Over budget, no SQLite volumes | Over budget |
| DigitalOcean | $5-8/mo | Full VPS control | More ops overhead, manual scaling | Too complex |
| Heroku | $7+/mo | Familiar to many | No free tier, ephemeral filesystem | Over budget |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Fly.io SJC Region                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │    civic-api        │    │  civic-websocket    │            │
│  │  (shared-cpu-1x)    │    │  (shared-cpu-1x)    │            │
│  │     Port 8001       │    │     Port 8002       │            │
│  │                     │    │                     │            │
│  │  /app/bundled-data  │    │  /app/bundled-data  │            │
│  │  (read-only, in     │    │  (read-only, in     │            │
│  │   Docker image)     │    │   Docker image)     │            │
│  └──────────┬──────────┘    └──────────┬──────────┘            │
│             │                          │                        │
│             └──────────┬───────────────┘                        │
│                        │                                        │
│              ┌─────────▼─────────┐                              │
│              │  Fly Volume (3GB) │                              │
│              │  /app/user-data   │                              │
│              │  ┌─────────────┐  │                              │
│              │  │civic_partic │  │                              │
│              │  │ipation.db   │  │                              │
│              │  └─────────────┘  │                              │
│              │  ┌─────────────┐  │                              │
│              │  │sessions/    │  │                              │
│              │  └─────────────┘  │                              │
│              │  ┌─────────────┐  │                              │
│              │  │backups/     │  │                              │
│              │  └─────────────┘  │                              │
│              └───────────────────┘                              │
│                                                                 │
│  Bundled Data (in Docker image, updated on deploy):            │
│  - /app/bundled-data/pilot/vectors/city-*/                     │
│  - /app/bundled-data/events/                                    │
│  - /app/bundled-data/legislative_context/                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Fly Proxy       │
                    │   (TLS/Load Bal)  │
                    │                   │
                    │ civic.fly.dev     │
                    │ api.civic.fly.dev │
                    │ ws.civic.fly.dev  │
                    └───────────────────┘
                              │
                              ▼
                         Internet
```

## Deployment Configuration

### fly.toml (civic-api)

```toml
app = "civic-api"
primary_region = "sjc"

[build]
  dockerfile = "Dockerfile"

[env]
  CIVICOS_ENV = "production"
  CIVICOS_API_PORT = "8001"

[http_service]
  internal_port = 8001
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1
  processes = ["app"]

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 256

[mounts]
  source = "civic_data"
  destination = "/app/user-data"  # Persistent user data only
```

### fly.toml (civic-websocket)

```toml
app = "civic-websocket"
primary_region = "sjc"

[build]
  dockerfile = "Dockerfile"

[env]
  CIVICOS_ENV = "production"

[http_service]
  internal_port = 8002
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 1
  processes = ["app"]

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 256

[mounts]
  source = "civic_data"
  destination = "/app/user-data"  # Persistent user data only
```

## Deployment Steps

### Initial Setup

```bash
# 1. Install Fly CLI
curl -L https://fly.io/install.sh | sh

# 2. Authenticate
fly auth login

# 3. Create apps
fly apps create civic-api
fly apps create civic-websocket

# 4. Create shared volume (3GB)
fly volumes create civic_data --region sjc --size 3 -a civic-api
fly volumes create civic_data --region sjc --size 3 -a civic-websocket

# 5. Set secrets
fly secrets set CIVICOS_WEB_KEY="..." -a civic-api
fly secrets set OPENAI_API_KEY="..." -a civic-api
fly secrets set GOOGLE_MAPS_API_KEY="..." -a civic-api
# Repeat for civic-websocket

# 6. Deploy
fly deploy -a civic-api
fly deploy -a civic-websocket --config fly.websocket.toml
```

### Data Migration

```bash
# Copy SQLite databases to volume
fly ssh console -a civic-api

# Inside container:
# Databases should be seeded via migration scripts
python scripts/migrate.py --status
python scripts/migrate.py
```

### Verify Deployment

```bash
# Check app status
fly status -a civic-api
fly status -a civic-websocket

# Check logs
fly logs -a civic-api

# Test endpoints
curl https://civic-api.fly.dev/api/events
curl https://civic-api.fly.dev/health  # Once implemented
```

## Scaling Strategy

### Pilot Phase (Jan 2026)
- 1 instance each service
- 3GB shared volume
- Single region (SJC)

### Growth Phase (5-10 cities)
- Same infrastructure
- Volume may need expansion to 5-10GB
- Monitor memory usage, scale to 512MB if needed

### Regional Expansion
- Replicate full stack per region
- Each region: ~$5/month
- Data sync via application-level replication

## Monitoring

### Built-in Fly.io Monitoring
- Machine metrics (CPU, memory, disk)
- Request metrics (latency, throughput)
- Uptime monitoring

### External Monitoring (Recommended)
- UptimeRobot (free tier) for external health checks
- Alert via email when services unavailable

## Backup Strategy

Integrate with existing backup script:

```bash
# Daily backup to local/cloud storage
fly ssh console -a civic-api -C "python scripts/backup.py backup"

# Download backup
fly ssh sftp get /app/data/backups/latest.tar.gz ./backups/
```

## Rollback Procedure

```bash
# List recent deployments
fly releases -a civic-api

# Rollback to specific version
fly deploy -a civic-api --image registry.fly.io/civic-api:v42
```

## Cost Monitoring

```bash
# Check current billing
fly billing

# Set spending limit (recommended)
fly orgs billing limits set --amount 10
```

## Domain Configuration

**Current (Pilot):** Using Fly.io auto-assigned subdomains:
- REST API: `https://civic-api.fly.dev`
- WebSocket: `https://civic-websocket.fly.dev`

Benefits of current approach:
- Zero additional cost (included with Fly.io)
- SSL certificates auto-managed by Fly.io
- No DNS configuration required
- Sufficient for pilot validation (Jan 2026)

**Future (Post-Pilot):** Custom domain can be added without breaking changes:

```bash
# Add custom domain
fly certs create civic.example.com -a civic-api

# Configure DNS (at registrar)
# CNAME civic.example.com -> civic-api.fly.dev
```

---

## Modal (Compute Tier)

Modal handles compute workloads that are bursty, need GPU, or require cron scheduling.

**Note:** MCP server is on Fly.io (already deployed). Modal is used for relay worker and vector indexing.

### Why Modal

| Feature | Benefit |
|---------|---------|
| **Serverless** | Pay only when running, ~$0.10/hr for CPU |
| **GPU access** | Vector indexing with embeddings |
| **Cron support** | Relay worker runs every 5 minutes |
| **Python-native** | Same codebase, no Docker needed |

### Cost Estimate

| Workload | Usage | Est. Cost/mo |
|----------|-------|--------------|
| Relay Worker | 5-min cron, ~10s/run | ~$1-2 |
| Vector Indexer | Weekly batch | ~$2-5 |
| Claude API | Summaries, matching | ~$5-10 |
| **Total** | | **~$8-17** |

### Deployment

```bash
# Install Modal CLI
pip install modal

# Authenticate
modal token new

# Deploy relay worker
modal deploy packages/civicos-relay/modal_worker.py

# Deploy vector indexer (if not already)
modal deploy scripts/modal_vectors.py
```

### Modal Configuration

**Relay Worker** (cron):

```python
# packages/civicos-relay/modal_worker.py
import modal

app = modal.App("civicos-relay")

@app.function(
    secrets=[modal.Secret.from_name("civicos-env")],
    schedule=modal.Cron("*/5 * * * *"),  # Every 5 minutes
)
async def relay_tick():
    """Check for events and route to subscribers."""
    from civicos_relay.worker import process_events
    await process_events()
```

### Environment Variables (Modal Secrets)

Create a secret named `civicos-env` with:

```bash
modal secret create civicos-env \
    DATABASE_URL="postgresql://..." \
    RELAY_DATABASE_URL="postgresql://..." \
    ANTHROPIC_API_KEY="..." \
    RESEND_API_KEY="..."
```

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-12-11 | Selected Fly.io | Best cost/feature balance for <$7/month |
| 2025-12-11 | SJC region | Closest to San Rafael pilot location |
| 2025-12-11 | Shared CPU | Sufficient for pilot scale traffic |
| 2025-12-11 | 3GB volume | Enough for SQLite + ChromaDB + growth |
| 2025-12-17 | Use .fly.dev subdomains | Zero cost, already working, custom domain can be added later |
| 2026-01-30 | Added Modal for compute | Serverless for relay worker, MCP server, vector indexing |

## References

- [Fly.io Pricing](https://fly.io/docs/about/pricing/)
- [Fly.io SQLite Guide](https://fly.io/docs/litefs/)
- [Modal Pricing](https://modal.com/pricing)
- [Modal Cron Functions](https://modal.com/docs/guide/cron)
- [Civic Dockerfile](../../Dockerfile)
- [Civic Docker Compose](../../docker-compose.yml)
- [Foundation Funding Thesis](./FOUNDATION_FUNDING_THESIS.md)
- [Coordination Protocol](./COORDINATION_PROTOCOL.md)
