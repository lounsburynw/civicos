# Uptime Monitoring Configuration

**Date:** 2025-12-11
**Status:** CONFIGURED
**Provider:** UptimeRobot (Free Tier)

## Overview

External uptime monitoring ensures that Civic services are accessible from the internet and alerts operators when services become unavailable. This is critical for the Jan 2026 pilot to maintain reliability expectations.

## Why External Monitoring

Fly.io provides internal health checks that restart unhealthy containers, but these don't detect:
- DNS issues preventing external access
- CDN/proxy failures
- Regional network outages
- Certificate expiration

External monitoring validates end-user reachability.

## Provider Selection

| Provider | Free Tier | Check Interval | Alert Methods | Decision |
|----------|-----------|----------------|---------------|----------|
| **UptimeRobot** | 50 monitors, 5-min intervals | 5 minutes | Email, webhook | **SELECTED** |
| Pingdom | 1 monitor | 1 minute | Email | Too limited |
| Freshping | 50 monitors | 1 minute | Email | Good alternative |
| StatusCake | 10 monitors | 5 minutes | Email | Adequate |

UptimeRobot selected for:
- Generous free tier (50 monitors)
- 5-minute check interval sufficient for pilot
- Simple email alerts
- No credit card required

## Monitored Endpoints

### Primary: REST API Health

| Field | Value |
|-------|-------|
| **URL** | `https://civic-api.fly.dev/health` |
| **Method** | HTTP GET |
| **Expected Status** | 200 |
| **Check Interval** | 5 minutes |
| **Timeout** | 30 seconds |
| **Alert Contacts** | Admin email |

The `/health` endpoint performs comprehensive checks:
- Database connectivity (SQLite)
- ChromaDB vector store availability
- External service configuration (OpenAI, Legistar)
- Data availability

Returns JSON with status: `healthy`, `degraded`, or `unhealthy`.

### Secondary: WebSocket Server

| Field | Value |
|-------|-------|
| **URL** | `https://civic-websocket.fly.dev/health` |
| **Method** | HTTP GET |
| **Expected Status** | 200 |
| **Check Interval** | 5 minutes |
| **Timeout** | 30 seconds |

The WebSocket server exposes a `/health` endpoint that returns:
```json
{"status": "healthy", "service": "civic-websocket"}
```

## Setup Instructions

### Step 1: Create UptimeRobot Account

1. Go to https://uptimerobot.com/
2. Click "Sign Up Free"
3. Enter email and create password
4. Verify email address

### Step 2: Create API Monitor

1. Click "Add New Monitor"
2. Configure:
   - **Monitor Type:** HTTP(s)
   - **Friendly Name:** Civic API Health
   - **URL:** `https://civic-api.fly.dev/health`
   - **Monitoring Interval:** 5 minutes
3. Under "Alert Contacts":
   - Add your email address
   - Toggle to receive alerts
4. Click "Create Monitor"

### Step 3: Verify Monitor is Working

1. Wait 5 minutes for first check
2. Dashboard should show green "Up" status
3. Verify response time is reasonable (<2 seconds)

### Step 4: Test Alert Delivery

1. Stop the Civic API service (or simulate failure)
   ```bash
   fly machines stop --app civic-api
   ```
2. Wait for next check cycle (up to 5 minutes)
3. Verify alert email received
4. Restart service:
   ```bash
   fly machines start --app civic-api
   ```
5. Verify "Up" notification received

## Alert Configuration

### Email Alerts

Default configuration sends:
- **Down Alert:** When monitor fails 2 consecutive checks (~10 minutes)
- **Up Alert:** When monitor recovers after being down

### Alert Escalation (Future)

For production, consider:
- Slack/Discord webhook for team notification
- SMS for critical alerts
- PagerDuty integration for on-call rotation

## Integration with Fly.io Health Checks

```
External Request → civic-api.fly.dev → Fly.io Proxy → Container
                                                        ↓
                                              /health endpoint
                                                        ↓
                                              Health checks:
                                              - Database
                                              - ChromaDB
                                              - Services
                                              - Data
```

The monitoring stack works in layers:

1. **Fly.io Internal** (every 30s)
   - Checks `/health` from within Fly network
   - Restarts unhealthy containers
   - Config: `fly.toml` `[checks]` section

2. **UptimeRobot External** (every 5 min)
   - Checks from external internet
   - Validates end-to-end reachability
   - Sends alerts to operators

## Status Page (Optional)

UptimeRobot provides a free public status page:

1. In UptimeRobot dashboard, go to "My Settings"
2. Click "Public Status Pages"
3. Create new page with:
   - **Name:** Civic Status
   - **Monitors:** Select Civic API Health
4. Share URL with pilot participants if desired

## Troubleshooting

### Monitor Shows "Down" but Service is Running

1. Check Fly.io status: https://status.fly.io/
2. Verify DNS resolution:
   ```bash
   dig civic-api.fly.dev
   ```
3. Test from different network:
   ```bash
   curl -v https://civic-api.fly.dev/health
   ```
4. Check Fly logs:
   ```bash
   fly logs -a civic-api
   ```

### Intermittent Failures

If monitor shows occasional failures:
- May be cold start delays (auto_stop_machines enabled)
- Increase timeout to 60 seconds
- Check if failures correlate with deployment times
- Review Fly.io metrics for memory/CPU issues

### False Positives

If getting alerts but service is actually fine:
- Increase consecutive failures before alert (default: 2)
- Check if UptimeRobot IP is being rate-limited
- Verify health endpoint doesn't have authentication issues

## Cost Impact

- UptimeRobot free tier: $0/month
- Total monitoring cost: $0/month
- Within budget constraint

## Verification Checklist

Before marking `uptime_monitoring` as ready:

- [ ] UptimeRobot account created
- [ ] Monitor configured for `/health` endpoint
- [ ] Alert contact configured (email)
- [ ] First successful check recorded
- [ ] Test alert delivery verified
- [ ] Documentation reviewed

## Related Items

| Item | Status | Relationship |
|------|--------|--------------|
| `api_health_endpoint` | READY | Provides endpoint to monitor |
| `structured_logging` | READY | Logs for debugging alerts |
| `alert_channel` | NOT_READY | Where alerts are sent (P2) |
| `error_alerts` | NOT_READY | Application-level alerts (P2) |

## References

- [UptimeRobot Documentation](https://uptimerobot.com/help/)
- [Fly.io Health Checks](https://fly.io/docs/reference/configuration/#the-checks-section)
- [Civic Health Endpoint](../../packages/civicos-services/src/civic_services/servers/civic_api_integrated.py)
- [Hosting Decision](./HOSTING_DECISION.md)
