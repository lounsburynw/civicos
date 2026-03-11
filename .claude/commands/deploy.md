# Deploy to Modal

Deploy CivicOS services to Modal with pre-flight checks.

## Usage

```
/deploy [service] [options]
```

**Services:**
- `api` - REST API (`packages/civicos-services/src/civicos_services/servers/modal_api.py`)
- `mcp` - MCP server (`apps/civicos-mcp/modal_mcp.py`)
- `relay` - Relay server (`packages/civicos-relay/src/civicos_relay/modal_relay.py`)
- `vectors` - Vector indexing job (`scripts/modal_vectors.py`)
- `usage-rollup` - Usage rollup cron (`scripts/modal_usage_rollup.py`)
- `status` - Show status of all deployed apps (no deploy)
- `all` - Deploy api + mcp + relay

## Examples

```
/deploy status                  # Check all deployed apps
/deploy api                     # Deploy REST API
/deploy mcp                     # Deploy MCP server
/deploy relay                   # Deploy relay server
/deploy all                     # Deploy all three services
```

## Steps

### 1. Pre-Flight Checks

```bash
# Verify Modal CLI is authenticated
modal token peek 2>/dev/null && echo "Modal: authenticated" || echo "ERROR: Modal not authenticated. Run: modal token set"

# Check deployed apps
echo ""
echo "=== DEPLOYED APPS ==="
modal app list 2>/dev/null | head -20

# Check secrets
echo ""
echo "=== MODAL SECRETS ==="
modal secret list 2>/dev/null | grep civicos
```

### 2. Deploy Service

Based on the argument:

**api:**
```bash
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```

**mcp:**
```bash
modal deploy apps/civicos-mcp/modal_mcp.py
```

**relay:**
```bash
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py
```

**vectors** (run, not deploy — it's a one-shot job):
```bash
modal run scripts/modal_vectors.py --stats-only
```

**usage-rollup:**
```bash
modal deploy scripts/modal_usage_rollup.py
```

**all:**
Deploy api, mcp, and relay in sequence:
```bash
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py && \
modal deploy apps/civicos-mcp/modal_mcp.py && \
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py
```

**status** (no deploy):
```bash
modal app list 2>/dev/null
```

### 3. Post-Deploy Health Check

After deploying, verify the service is healthy:

```bash
# Get the deployed URL from Modal output, then:
# API
curl -s https://civicos-api.modal.run/health | python3 -m json.tool 2>/dev/null || echo "API health check failed"

# MCP
curl -s https://civicos-mcp.modal.run/health | python3 -m json.tool 2>/dev/null || echo "MCP health check failed"

# Relay
curl -s https://civicos-relay.modal.run/health | python3 -m json.tool 2>/dev/null || echo "Relay health check failed"
```

### 4. Tail Logs (if issues)

```bash
# Tail recent logs for a service
modal app logs civicos-api 2>/dev/null | tail -30
```

## Deployment Notes

- Modal bundles code at deploy time — local edits are included automatically
- Modal Secrets (`civicos-secrets`, `civicos-platform`) store environment variables
- Never deploy to Fly.io or other platforms — Modal only
- Deployments are atomic — if deploy fails, previous version stays running
- Use `modal app stop <app-name>` to take down a service (rare)

## Required Secrets

| Secret Group | Keys | Used By |
|-------------|------|---------|
| `civicos-secrets` | DATABASE_URL, OPENAI_API_KEY, BLOB_STORAGE_URL, etc. | All services |
| `civicos-platform` | PLATFORM_DATABASE_URL | Usage logging, billing |

Check secrets:
```bash
modal secret list
```

## Troubleshooting

### Deploy fails with import error
Code has a syntax or import error. Fix locally first, then re-deploy.

### Health check fails after deploy
```bash
modal app logs <app-name> | tail -50
```
Look for startup errors (missing env vars, DB connection issues).

### Secret not found
```bash
modal secret list | grep civicos
# If missing, create:
modal secret create civicos-platform PLATFORM_DATABASE_URL=<url>
```
