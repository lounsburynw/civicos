# Uptime Monitoring Configuration

**Date:** 2026-03-07
**Status:** CONFIGURED
**Platform:** Modal (serverless) + Supabase (PostgreSQL)

## Overview

Monitoring ensures that CivicOS services are accessible and alerts operators when services become unavailable. All services run on Modal (serverless) and Supabase (managed PostgreSQL), both of which provide built-in observability.

## Monitoring Layers

Modal provides built-in monitoring for all deployed apps, and Supabase provides its own dashboard monitoring for PostgreSQL. External monitoring validates end-to-end reachability for:
- DNS issues preventing external access
- CDN/proxy failures (Cloudflare Workers)
- Regional network outages
- Certificate expiration

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

### Primary: Modal App Health

All services are deployed as Modal apps with built-in health endpoints.

| Service | Monitoring | Method |
|---------|-----------|--------|
| **MCP Server** | `modal app logs civicos-mcp` | Modal dashboard + logs |
| **API Server** | `modal app logs civicos-api` | Modal dashboard + logs |
| **Relay Worker** | `modal app logs civicos-relay` | Modal dashboard + logs |
| **Vector Indexer** | On-demand (GPU) | Check after indexing runs |

```bash
# List all deployed apps and their status
modal app list

# View logs for a specific app
modal app logs civicos-mcp

# Check app details
modal app show civicos-mcp
```

### Secondary: Supabase PostgreSQL

Supabase provides built-in monitoring via its dashboard:

| Check | Method |
|-------|--------|
| **Database health** | Supabase Dashboard > Database > Health |
| **Connection pool** | Supabase Dashboard > Database > Connections |
| **Query performance** | Supabase Dashboard > Database > Query Performance |
| **Storage usage** | Supabase Dashboard > Database > Database Size |

### External: UptimeRobot (Optional)

For end-to-end reachability validation from the public internet:

| Field | Value |
|-------|-------|
| **URL** | `https://san-rafael.civicosproject.org/mcp` |
| **Method** | HTTP GET |
| **Expected Status** | 200 |
| **Check Interval** | 5 minutes |
| **Timeout** | 30 seconds |
| **Alert Contacts** | Admin email |

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
   - **Friendly Name:** CivicOS MCP Health
   - **URL:** `https://san-rafael.civicosproject.org/mcp`
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

1. Stop the Modal app (or simulate failure)
   ```bash
   modal app stop civicos-mcp
   ```
2. Wait for next check cycle (up to 5 minutes)
3. Verify alert email received
4. Redeploy service:
   ```bash
   modal deploy apps/civicos-mcp/modal_app.py
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

## Monitoring Stack

```
External Request → civicosproject.org → Cloudflare Workers → Modal App
                                                                ↓
                                                      Service endpoint
                                                                ↓
                                                      Health checks:
                                                      - Supabase PostgreSQL
                                                      - pgvector availability
                                                      - OpenAI API
                                                      - Data availability
```

The monitoring stack works in layers:

1. **Modal Built-in** (continuous)
   - Tracks app status, cold starts, errors
   - Auto-scales containers (serverless)
   - Dashboard: `modal.com` > Apps

2. **Supabase Dashboard** (continuous)
   - Database health, connections, query performance
   - Dashboard: `supabase.com` > Project > Database

3. **UptimeRobot External** (every 5 min, optional)
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

1. Check Modal app status: `modal app list`
2. Verify DNS resolution:
   ```bash
   dig san-rafael.civicosproject.org
   ```
3. Test from different network:
   ```bash
   curl -v https://san-rafael.civicosproject.org/mcp
   ```
4. Check Modal logs:
   ```bash
   modal app logs civicos-mcp
   ```

### Intermittent Failures

If monitor shows occasional failures:
- May be cold start delays (Modal serverless scaling from zero)
- Increase timeout to 60 seconds
- Check if failures correlate with deployment times
- Review Modal dashboard for container errors

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
- [Modal Documentation](https://modal.com/docs)
- [Supabase Dashboard Monitoring](https://supabase.com/docs/guides/platform/metrics)
- [Hosting Decision](./HOSTING_DECISION.md)
