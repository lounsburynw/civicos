# Admin Troubleshooting Guide

Common issues and solutions for Civic platform administrators. For deployment procedures, see [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md). For setup instructions, see [ADMIN_SETUP_GUIDE.md](ADMIN_SETUP_GUIDE.md).

---

## Quick Diagnostics

Run these commands to quickly assess system health:

```bash
# Check API health
curl -s https://civic-api.fly.dev/health | jq .

# Check WebSocket health
curl -s https://civic-websocket.fly.dev/health | jq .

# View recent logs
fly logs -a civic-api -n 50

# Check deployment status
fly status -a civic-api
fly status -a civic-websocket
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

**Symptom:** Container fails to start or crashes immediately.

**Check logs first:**
```bash
fly logs -a civic-api -n 100
```

**Common causes and fixes:**

| Cause | Log Pattern | Fix |
|-------|-------------|-----|
| Missing secret | `KeyError: 'OPENAI_API_KEY'` | Set the missing secret: `fly secrets set OPENAI_API_KEY=sk-... -a civic-api` |
| Invalid Python | `ModuleNotFoundError` | Rebuild image: `fly deploy -a civic-api` |
| Port conflict | `Address already in use` | Check `fly.toml` port configuration |
| Volume not mounted | `FileNotFoundError: /app/user-data` | Verify volume: `fly volumes list -a civic-api` |

### "OPENAI_API_KEY not set"

```bash
# Check if set
fly secrets list -a civic-api

# Set it
fly secrets set OPENAI_API_KEY="sk-proj-..." -a civic-api

# Redeploy to pick up new secret
fly deploy -a civic-api
```

### "CIVIC_WEB_KEY not set" (production only)

```bash
# Generate a production-grade key
fly secrets set CIVIC_WEB_KEY="$(openssl rand -hex 32)" -a civic-api

# Set same key for WebSocket server
fly secrets set CIVIC_WEB_KEY="your-key-here" -a civic-websocket
```

### Health Check Timeouts

**Symptom:** Deployment hangs at "waiting for health checks"

**Causes:**
1. App takes too long to start (cold start)
2. Health endpoint not responding
3. Incorrect port configuration

**Fixes:**

```bash
# Check if app is actually running
fly status -a civic-api

# View startup logs
fly logs -a civic-api | head -50

# Increase health check grace period in fly.toml
# [http_service]
#   grace_period = "30s"
```

---

## Authentication Issues

### 401 Unauthorized

**Symptom:** API returns `{"error": "Authentication required"}`

**Causes and fixes:**

| Cause | How to Verify | Fix |
|-------|---------------|-----|
| Missing header | Check request logs | Add `Authorization: Bearer YOUR_KEY` header |
| Wrong key | Compare key values | Use the correct CIVIC_WEB_KEY |
| Key not deployed | `fly secrets list -a civic-api` | Set secret and redeploy |

**Test authentication:**
```bash
# Should return 401
curl -s https://civic-api.fly.dev/api/events

# Should work
curl -s -H "Authorization: Bearer $CIVIC_WEB_KEY" \
  https://civic-api.fly.dev/api/events
```

### Invalid API Key

**Symptom:** OpenAI errors in logs like `AuthenticationError`

```bash
# Verify key is valid
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -c 100

# If invalid, get new key from platform.openai.com
fly secrets set OPENAI_API_KEY="sk-proj-new-key" -a civic-api
```

### CORS Errors in Browser

**Symptom:** Browser console shows `Access-Control-Allow-Origin` error

**Fix:**
```bash
# Check current setting
fly secrets list -a civic-api | grep CORS

# Set correct origins (include protocol)
fly secrets set CIVIC_CORS_ORIGINS="https://your-domain.com" -a civic-api

# Redeploy
fly deploy -a civic-api
```

**Common mistakes:**
- Missing protocol: `example.com` should be `https://example.com`
- Trailing slash: `https://example.com/` should be `https://example.com`
- HTTP vs HTTPS mismatch

---

## Database Issues

### Database Not Found

**Symptom:** `sqlite3.OperationalError: unable to open database file`

```bash
# Check user-data volume is mounted
fly ssh console -a civic-api -C "ls -la /app/user-data/"

# If empty, run migrations
fly ssh console -a civic-api -C "python scripts/migrate.py"

# Verify database exists
fly ssh console -a civic-api -C "ls -la /app/user-data/*.db"
```

### Migration Errors

**Symptom:** `no such table` or `no such column` errors

```bash
# Check migration status
fly ssh console -a civic-api -C "python scripts/migrate.py --status"

# Run pending migrations
fly ssh console -a civic-api -C "python scripts/migrate.py"
```

**If migration fails:**
1. Do NOT retry immediately
2. Check logs for specific error
3. If data corruption, restore from backup first

### Database Locked

**Symptom:** `sqlite3.OperationalError: database is locked`

**Causes:**
- Multiple processes accessing database
- Long-running query blocking writes

**Fixes:**
```bash
# Restart the application (releases locks)
fly machines restart -a civic-api

# If persistent, check for multiple machines
fly machines list -a civic-api
```

### Corrupt Database

**Symptom:** `sqlite3.DatabaseError: database disk image is malformed`

**Recovery:**
```bash
# Create safety backup of current state
fly ssh console -a civic-api -C "cp /app/user-data/civic_participation.db /app/user-data/civic_participation.db.corrupt"

# List available backups
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# Restore from backup
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_participation_YYYYMMDD.db"
```

---

## API Issues

### 500 Internal Server Error

**Symptom:** API returns 500 status code

```bash
# Check recent error logs
fly logs -a civic-api | grep -i error

# Common patterns and fixes:
# - "OpenAI API error" → Check API key and quota
# - "Database error" → Check database health
# - "File not found" → Check data paths
```

### 503 Service Unavailable

**Symptom:** API returns 503 status code

**Causes:**
- App is restarting
- Health check failing
- Dependencies unavailable

```bash
# Check app status
fly status -a civic-api

# If unhealthy, check logs
fly logs -a civic-api -n 100 | grep -i health

# Force restart
fly machines restart -a civic-api
```

### Slow API Responses

**Symptom:** Requests take > 5 seconds

**Diagnosis:**
```bash
# Check resource usage
fly ssh console -a civic-api -C "top -b -n 1"

# Check for memory issues
fly logs -a civic-api | grep -i memory
```

**Fixes:**

| Cause | Symptom | Fix |
|-------|---------|-----|
| Low memory | OOM in logs | Scale up: `fly scale memory 512 -a civic-api` |
| Cold start | First request slow | Increase min instances in fly.toml |
| Large query | Specific endpoints slow | Optimize query or add caching |
| External API | OpenAI calls slow | Check OpenAI status page |

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
# Check WebSocket server is running
fly status -a civic-websocket

# Check logs
fly logs -a civic-websocket -n 50

# Verify correct URL (use wss:// not ws:// for production)
```

### Connection Drops Frequently

**Symptom:** WebSocket disconnects every few minutes

**Causes:**
- Fly.io proxy timeout (default 1 hour)
- Client not sending keepalive
- Memory pressure on server

**Fixes:**
```bash
# Check for OOM
fly logs -a civic-websocket | grep -i memory

# Increase resources if needed
fly scale memory 512 -a civic-websocket
```

### Messages Not Received

**Symptom:** Events sent but not received by clients

**Diagnosis:**
```bash
# Check WebSocket logs for send/receive
fly logs -a civic-websocket | grep -i "event\|message"
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
# Check bundled data
fly ssh console -a civic-api -C "ls -la /app/bundled-data/events/"

# Check for your jurisdiction
fly ssh console -a civic-api -C "ls -la /app/bundled-data/events/city-san-rafael/"
```

**If data missing:**
1. Re-run extraction locally
2. Commit data files
3. Redeploy (data is bundled in image)

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
# Verify vectors exist
fly ssh console -a civic-api -C "ls -la /app/bundled-data/pilot/vectors/city-san-rafael/"
```

**If empty:**
1. Re-index documents locally
2. Commit vector files
3. Redeploy

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
CIVIC_EMBEDDING_PROVIDER=local

# Or OpenAI (requires key)
CIVIC_EMBEDDING_PROVIDER=openai
# Requires OPENAI_API_KEY
```

---

## Resource Issues

### Out of Memory

**Symptom:** Container restarts with OOM in logs

```bash
# Check current memory
fly scale show -a civic-api

# Increase memory
fly scale memory 512 -a civic-api
```

**Cost-aware alternatives:**
- Reduce concurrent requests
- Optimize memory-heavy operations
- Use smaller batch sizes

### Disk Full (Volume)

**Symptom:** Write errors, backup failures

```bash
# Check disk usage
fly ssh console -a civic-api -C "df -h /app/user-data"

# Clean old backups
fly ssh console -a civic-api -C "python scripts/backup.py --clean"

# If still full, expand volume
fly volumes extend vol_xxxxx --size 5 -a civic-api
```

**Note:** Reference data (vectors, events) is in the Docker image, not the volume.

### Docker Image Too Large

**Symptom:** Slow deploys, build failures

**Reduce image size:**
1. Clean test data before building
2. Remove unused city data
3. Use `.dockerignore` for dev files

---

## Deployment Issues

### Deploy Fails

**Symptom:** `fly deploy` exits with error

```bash
# Check build logs
fly logs -a civic-api

# Test local build
docker build -t civic-test .

# Check for resource issues
fly scale show -a civic-api
```

### Deploy Succeeds But App Fails

**Symptom:** Deploy shows green but app crashes

**Common causes:**
- New code has runtime error
- Missing environment variable
- Incompatible migration

**Fix:**
```bash
# Roll back to previous version
fly releases -a civic-api  # Find previous version
fly deploy -a civic-api --image registry.fly.io/civic-api:vN
```

### Version Mismatch Between Apps

**Symptom:** WebSocket features don't work, protocol errors

**Both apps must run compatible versions:**
```bash
# Check versions
fly releases -a civic-api | head -3
fly releases -a civic-websocket | head -3

# Deploy same version to both
fly deploy -a civic-api
fly deploy -a civic-websocket --config fly.websocket.toml
```

---

## Recovery Procedures

### Quick Rollback (Code Only)

Use when new code is broken but data is intact:

```bash
# List recent releases
fly releases -a civic-api

# Roll back (replace vN with target version)
fly deploy -a civic-api --image registry.fly.io/civic-api:vN
```

### Full Rollback (Code + Data)

Use when both code and data need recovery:

```bash
# 1. Stop traffic
fly scale count 0 -a civic-api

# 2. List backups
fly ssh console -a civic-api -C "python scripts/backup.py --list"

# 3. Restore data
fly ssh console -a civic-api -C "python scripts/backup.py --restore civic_participation_YYYYMMDD.db"

# 4. Roll back code
fly deploy -a civic-api --image registry.fly.io/civic-api:vN

# 5. Restart
fly scale count 1 -a civic-api
```

### Emergency Contact Procedures

If production is down and standard fixes don't work:

1. **Check external services:**
   - OpenAI Status: status.openai.com
   - Fly.io Status: status.fly.io

2. **Rollback to last known good:**
   ```bash
   fly releases -a civic-api | head -10
   fly deploy -a civic-api --image registry.fly.io/civic-api:vN
   ```

3. **Document the incident** for post-mortem

---

## Diagnostic Commands Reference

| Task | Command |
|------|---------|
| View logs | `fly logs -a civic-api` |
| Check status | `fly status -a civic-api` |
| SSH into container | `fly ssh console -a civic-api` |
| List secrets | `fly secrets list -a civic-api` |
| Set secret | `fly secrets set KEY=value -a civic-api` |
| Check releases | `fly releases -a civic-api` |
| Scale memory | `fly scale memory 512 -a civic-api` |
| Restart app | `fly machines restart -a civic-api` |
| Check volumes | `fly volumes list -a civic-api` |
| Run backup | `fly ssh console -a civic-api -C "python scripts/backup.py"` |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md) | Full deployment procedures |
| [ROLLBACK_PROCEDURES.md](../critical/ROLLBACK_PROCEDURES.md) | Detailed rollback steps |
| [SECRETS_MANAGEMENT.md](../critical/SECRETS_MANAGEMENT.md) | All secrets configuration |
| [ADMIN_SETUP_GUIDE.md](ADMIN_SETUP_GUIDE.md) | Initial setup instructions |
| [UPTIME_MONITORING.md](../critical/UPTIME_MONITORING.md) | Monitoring configuration |
