# Admin Troubleshooting Guide

Common issues and solutions for Civic platform administrators. For deployment procedures, see [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md). For setup instructions, see [ADMIN_SETUP_GUIDE.md](ADMIN_SETUP_GUIDE.md).

---

## Quick Diagnostics

Run these commands to quickly assess system health:

```bash
# Check API health
curl -s https://san-rafael.civicosproject.org/health | jq .

# View recent logs
modal app logs civicos-mcp

# Check deployment status
modal app list
modal app show civicos-mcp
```

---

## Table of Contents

1. [Startup Issues](#startup-issues)
2. [Authentication Issues](#authentication-issues)
3. [Database Issues](#database-issues)
4. [API Issues](#api-issues)
5. [WebSocket Issues](#websocket-issues)
6. [Data Extraction Issues](#data-extraction-issues)
7. [RAG/Search Issues](#ragsearch-issues)
8. [Resource Issues](#resource-issues)
9. [Deployment Issues](#deployment-issues)
10. [Recovery Procedures](#recovery-procedures)

---

## Startup Issues

### Application Won't Start

**Symptom:** Modal app fails to deploy or crashes on invocation.

**Check logs first:**
```bash
modal app logs civicos-mcp
```

**Common causes and fixes:**

| Cause | Log Pattern | Fix |
|-------|-------------|-----|
| Missing secret | `KeyError: 'OPENAI_API_KEY'` | Update Modal secret: `modal secret create civicos-env OPENAI_API_KEY=sk-...` |
| Invalid Python | `ModuleNotFoundError` | Check `modal_app.py` image definition and redeploy |
| Missing DB connection | `Connection refused` | Verify `DATABASE_URL` in Modal secrets |

### "OPENAI_API_KEY not set"

```bash
# Check Modal secrets
modal secret list

# Update the civicos-env secret (recreate with all values)
modal secret create civicos-env \
    OPENAI_API_KEY="sk-proj-..." \
    DATABASE_URL="postgresql://..." \
    RELAY_DATABASE_URL="postgresql://..."

# Redeploy to pick up new secret
modal deploy apps/civicos-mcp/modal_app.py
```

### "CIVICOS_WEB_KEY not set" (production only)

```bash
# Add to Modal secrets (include all existing values plus the new key)
modal secret create civicos-env \
    CIVICOS_WEB_KEY="$(openssl rand -hex 32)" \
    # ... other existing secrets
```

### Health Check / Cold Start Issues

**Symptom:** First request after idle period is slow or times out.

Modal handles container lifecycle automatically. Cold starts are expected for serverless.

**Mitigations:**
- Use `keep_warm=1` in Modal app definition to reduce cold starts
- Check `modal app logs` for startup errors
- Verify the health endpoint responds: `curl https://san-rafael.civicosproject.org/health`

---

## Authentication Issues

### 401 Unauthorized

**Symptom:** API returns `{"error": "Authentication required"}`

**Causes and fixes:**

| Cause | How to Verify | Fix |
|-------|---------------|-----|
| Missing header | Check request logs | Add `Authorization: Bearer YOUR_KEY` header |
| Wrong key | Compare key values | Use the correct CIVICOS_WEB_KEY |
| Key not deployed | `modal secret list` | Update Modal secrets and redeploy |

**Test authentication:**
```bash
# Should return 401
curl -s https://san-rafael.civicosproject.org/api/events

# Should work
curl -s -H "Authorization: Bearer $CIVICOS_WEB_KEY" \
  https://san-rafael.civicosproject.org/api/events
```

### Invalid API Key

**Symptom:** OpenAI errors in logs like `AuthenticationError`

```bash
# Verify key is valid
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -c 100

# If invalid, get new key from platform.openai.com and update Modal secrets
modal secret create civicos-env OPENAI_API_KEY="sk-proj-new-key" ...
modal deploy apps/civicos-mcp/modal_app.py
```

### CORS Errors in Browser

**Symptom:** Browser console shows `Access-Control-Allow-Origin` error

**Fix:**
```bash
# Update CORS origins in Modal secrets
modal secret create civicos-env \
    CIVICOS_CORS_ORIGINS="https://your-domain.com" \
    # ... other existing secrets

# Redeploy
modal deploy apps/civicos-mcp/modal_app.py
```

**Common mistakes:**
- Missing protocol: `example.com` should be `https://example.com`
- Trailing slash: `https://example.com/` should be `https://example.com`
- HTTP vs HTTPS mismatch

---

## Database Issues

### Database Connection Issues

**Symptom:** Cannot connect to Supabase PostgreSQL

```bash
# Verify DATABASE_URL is configured
source civicos-env/bin/activate
python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('DATABASE_URL', 'NOT SET')[:30] + '...')"

# Test connection
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-san-rafael')
print(f'Backend: {type(c.storage).__name__}')
"
```

**Common causes:**
- `DATABASE_URL` not set in `.env` or Modal secrets
- Supabase project paused (check dashboard)
- Network connectivity issue

### Migration Errors

**Symptom:** `relation does not exist` or column errors

```bash
# Check migration status (run locally against Supabase)
python scripts/migrate.py --status

# Apply pending migrations
python scripts/migrate.py
```

**If migration fails:**
1. Do NOT retry immediately
2. Check logs for specific error
3. If data corruption, use Supabase PITR to restore to a point before the migration

### Database Performance

**Symptom:** Slow queries or connection timeouts

**Causes:**
- Connection pool exhaustion
- Missing indexes
- Supabase resource limits

**Fixes:**
- Check Supabase Dashboard > Database > Performance
- Review connection pool settings
- Consider upgrading Supabase plan if hitting limits

### Local SQLite Issues

For local development with SQLite:

```bash
# Check database integrity
sqlite3 data/civic_state.db "PRAGMA integrity_check;"

# If corrupt, restore from backup
cp data/civic_state.db.backup-YYYYMMDD data/civic_state.db
```

---

## API Issues

### 500 Internal Server Error

**Symptom:** API returns 500 status code

```bash
# Check recent error logs
modal app logs civicos-mcp | grep -i error

# Common patterns and fixes:
# - "OpenAI API error" → Check API key and quota
# - "Database error" → Check Supabase connection/status
# - "File not found" → Check data paths in Modal image
```

### 503 Service Unavailable

**Symptom:** API returns 503 status code

**Causes:**
- Modal container is cold-starting
- Dependencies unavailable (Supabase, OpenAI)

```bash
# Check Modal app status
modal app show civicos-mcp

# Check logs for errors
modal app logs civicos-mcp

# Redeploy if needed (Modal handles restarts automatically)
modal deploy apps/civicos-mcp/modal_app.py
```

### Slow API Responses

**Symptom:** Requests take > 5 seconds

**Diagnosis:**
```bash
# Check Modal logs for timing
modal app logs civicos-mcp
```

**Fixes:**

| Cause | Symptom | Fix |
|-------|---------|-----|
| Cold start | First request slow | Set `keep_warm=1` in Modal app definition |
| Large query | Specific endpoints slow | Optimize query or add caching |
| External API | OpenAI calls slow | Check OpenAI status page |
| DB latency | All queries slow | Check Supabase Dashboard > Performance |

### Rate Limit Exceeded

**Symptom:** 429 status code or `Rate limit exceeded` error

**For Civic API:**
```bash
# Development: disable rate limiting
ENABLE_RATE_LIMIT=false

# Production: adjust limits in .env
RATE_LIMIT_PER_MINUTE=120
RATE_LIMIT_PER_HOUR=2000
```

**For OpenAI:**
- Check usage at platform.openai.com/usage
- Upgrade tier or wait for reset
- Implement request batching

---

## WebSocket Issues

### Connection Refused

**Symptom:** WebSocket won't connect

```bash
# Check Modal app status
modal app show civicos-mcp

# Check logs
modal app logs civicos-mcp

# Verify correct URL (use wss:// not ws:// for production)
```

### Connection Drops Frequently

**Symptom:** WebSocket disconnects every few minutes

**Causes:**
- Modal container recycling (serverless lifecycle)
- Client not sending keepalive
- Network interruption

**Fixes:**
- Ensure client implements reconnection logic
- Use `keep_warm=1` in Modal app definition
- Check `modal app logs` for errors

### Messages Not Received

**Symptom:** Events sent but not received by clients

**Diagnosis:**
```bash
# Check logs for send/receive events
modal app logs civicos-mcp | grep -i "event\|message"
```

**Common issues:**
- Room/channel mismatch
- JSON serialization error
- Client handler not registered

---

## Data Extraction Issues

### No Meetings Found

**Symptom:** `whats_next()` returns empty

**Check data exists:**
```bash
# Check database for meetings (run locally)
source civicos-env/bin/activate
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-san-rafael')
meetings = c.storage.get_meetings('city-san-rafael')
print(f'Meetings in DB: {len(meetings)}')
"
```

**If data missing:**
1. Re-run extraction: `civic-extract discover --jurisdiction city-san-rafael`
2. Data is stored in Supabase PostgreSQL, not bundled in the image

### Legistar API Errors

**Symptom:** Extraction script fails with connection error

```python
# Test connection
from civic_extraction import LegistarClient
client = LegistarClient("your-city")
events = client.get_events(days_ahead=7)
print(f"Found {len(events)} events")
```

**Common issues:**

| Error | Cause | Fix |
|-------|-------|-----|
| 404 Not Found | Wrong client ID | Check city's Legistar URL |
| 403 Forbidden | IP blocked | Contact city IT |
| Timeout | Network issue | Retry with longer timeout |

### SeeClickFix API Errors

**Symptom:** Issue refresh fails

```bash
# Test API manually
curl "https://seeclickfix.com/api/v2/issues?place_url=san-rafael-ca&per_page=5"
```

**If rate limited:**
- Wait 15 minutes
- Reduce fetch frequency
- Use pagination properly

### YouTube Extraction Fails

**Symptom:** Video transcripts not available

**Common issues:**

| Error | Cause | Fix |
|-------|-------|-----|
| Video not found | Wrong video ID | Verify URL/ID |
| No captions | Video has no captions | Use AssemblyAI transcription |
| Private video | Video restricted | Contact city to make public |

---

## RAG/Search Issues

### Vector Search Returns No Results

**Symptom:** Semantic search returns empty

**Check vector store:**
```bash
# Verify vectors exist in Supabase (pgvector)
source civicos-env/bin/activate
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, VectorCoverage
c = CivicOS('city-san-rafael')
coverage = VectorCoverage(c._vectors, 'city-san-rafael')
print(coverage.summary())
"
```

**If empty:**
1. Re-index documents using `/vectors reindex`
2. Vectors are stored in Supabase pgvector, not in files

**If vectors exist but search fails:**
```python
# Test locally
from civic._internal.rag import RAGEngine
rag = RAGEngine("city-san-rafael")
print(f"Document count: {rag.document_count}")
results = rag.search("housing", top_k=5)
print(f"Results: {len(results)}")
```

### Search Returns Irrelevant Results

**Causes:**
- Query too broad
- Documents not chunked well
- Embeddings outdated

**Fixes:**
- Use more specific query terms
- Re-index with better chunking
- Rebuild embeddings if schema changed

### Embeddings Not Available

**Symptom:** `logger.warning("Embeddings not available - search disabled")`

**Check embedding provider:**
```bash
# Local embeddings (default)
CIVICOS_EMBEDDING_PROVIDER=local

# Or OpenAI (requires key)
CIVICOS_EMBEDDING_PROVIDER=openai
# Requires OPENAI_API_KEY
```

---

## Resource Issues

### Out of Memory

**Symptom:** Modal function fails with memory errors

```bash
# Check logs for OOM
modal app logs civicos-mcp | grep -i memory
```

**Fixes:**
- Increase memory in Modal function definition (e.g., `memory=512`)
- Reduce concurrent requests via `concurrency_limit`
- Optimize memory-heavy operations
- Use smaller batch sizes

### Storage Issues

Modal is stateless — there is no server-side disk to fill. All persistent data is in managed services:
- **PostgreSQL**: Supabase (managed storage)
- **Blobs**: Cloudflare R2 (object storage)

For local disk issues, see [ADMIN_DATA_MANAGEMENT.md](ADMIN_DATA_MANAGEMENT.md#storage-management).

---

## Deployment Issues

### Deploy Fails

**Symptom:** `modal deploy` exits with error

```bash
# Check build/deploy output for errors
modal deploy apps/civicos-mcp/modal_app.py

# Test locally first
modal serve apps/civicos-mcp/modal_app.py

# Verify Modal secrets are configured
modal secret list
```

### Deploy Succeeds But App Fails

**Symptom:** Deploy completes but requests fail

**Common causes:**
- New code has runtime error
- Missing environment variable in Modal secrets
- Incompatible migration

**Fix:**
```bash
# Roll back to previous git version and redeploy
git checkout v0.2.0-pilot-YYYYMMDD
modal deploy apps/civicos-mcp/modal_app.py

# Check logs for the specific error
modal app logs civicos-mcp
```

### Version Mismatch

**Symptom:** API features don't work as expected

```bash
# Check current git tag
git tag --list "v*-pilot-*" --sort=-creatordate | head -3

# Ensure deployed code matches expected version
# Modal deploys are atomic — each `modal deploy` replaces the running app
```

---

## Recovery Procedures

### Quick Rollback (Code Only)

Use when new code is broken but data is intact:

```bash
# Modal deploys are atomic — redeploy a known-good version
git checkout v0.2.0-pilot-YYYYMMDD
modal deploy apps/civicos-mcp/modal_app.py
```

### Full Rollback (Code + Data)

Use when both code and data need recovery:

```bash
# 1. Roll back code
git checkout v0.2.0-pilot-YYYYMMDD
modal deploy apps/civicos-mcp/modal_app.py

# 2. Restore data using Supabase PITR (point-in-time recovery)
# Go to: Supabase Dashboard > Settings > Backups > Restore to point in time

# 3. Verify
curl -s https://san-rafael.civicosproject.org/health | jq .
```

### Emergency Contact Procedures

If production is down and standard fixes don't work:

1. **Check external services:**
   - OpenAI Status: status.openai.com
   - Modal Status: status.modal.com
   - Supabase Status: status.supabase.com

2. **Rollback to last known good:**
   ```bash
   git tag --list "v*-pilot-*" --sort=-creatordate | head -5
   git checkout <last-known-good-tag>
   modal deploy apps/civicos-mcp/modal_app.py
   ```

3. **Document the incident** for post-mortem

---

## Diagnostic Commands Reference

| Task | Command |
|------|---------|
| View logs | `modal app logs civicos-mcp` |
| Check status | `modal app show civicos-mcp` |
| List apps | `modal app list` |
| List secrets | `modal secret list` |
| Set secrets | `modal secret create civicos-env KEY=value ...` |
| Deploy | `modal deploy apps/civicos-mcp/modal_app.py` |
| Test locally | `modal serve apps/civicos-mcp/modal_app.py` |
| Check health | `curl https://san-rafael.civicosproject.org/health` |
| Run backup | `python scripts/backup.py` (locally, connects to Supabase) |
| DB dashboard | Supabase Dashboard > Database |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md) | Full deployment procedures |
| [ROLLBACK_PROCEDURES.md](../critical/ROLLBACK_PROCEDURES.md) | Detailed rollback steps |
| [SECRETS_MANAGEMENT.md](../critical/SECRETS_MANAGEMENT.md) | All secrets configuration |
| [ADMIN_SETUP_GUIDE.md](ADMIN_SETUP_GUIDE.md) | Initial setup instructions |
| [UPTIME_MONITORING.md](../critical/UPTIME_MONITORING.md) | Monitoring configuration |
