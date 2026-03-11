# Health Check

Quick health check of all deployed CivicOS services and infrastructure.

## Usage

```
/health [target]
```

**Targets:**
- (default) - Check all services
- `api` - REST API only
- `mcp` - MCP server only
- `relay` - Relay server only
- `db` - Database connectivity
- `infra` - Modal apps + secrets status

## Steps

### 1. Check All Deployed Services

```bash
echo "=== CivicOS Health Check ==="
echo ""

# API
echo -n "API (civicos-api):     "
API_RESP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://civicos-api.modal.run/health 2>/dev/null)
if [ "$API_RESP" = "200" ]; then echo "OK ($API_RESP)"; else echo "FAIL ($API_RESP)"; fi

# MCP
echo -n "MCP (civicos-mcp):     "
MCP_RESP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://civicos-mcp.modal.run/health 2>/dev/null)
if [ "$MCP_RESP" = "200" ]; then echo "OK ($MCP_RESP)"; else echo "FAIL ($MCP_RESP)"; fi

# Relay
echo -n "Relay (civicos-relay): "
RELAY_RESP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://civicos-relay.modal.run/health 2>/dev/null)
if [ "$RELAY_RESP" = "200" ]; then echo "OK ($RELAY_RESP)"; else echo "FAIL ($RELAY_RESP)"; fi
```

### 2. Check Database Connectivity

```bash
echo ""
echo "=== Database ==="
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()
import os

# Main DB
try:
    import psycopg2
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=5)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM meetings')
    count = cur.fetchone()[0]
    conn.close()
    print(f'Main DB:  OK ({count} meetings)')
except Exception as e:
    print(f'Main DB:  FAIL ({e})')

# Relay DB
relay_url = os.environ.get('RELAY_DATABASE_URL')
if relay_url:
    try:
        conn = psycopg2.connect(relay_url, connect_timeout=5)
        cur = conn.cursor()
        cur.execute('SELECT 1')
        conn.close()
        print(f'Relay DB: OK')
    except Exception as e:
        print(f'Relay DB: FAIL ({e})')
else:
    print('Relay DB: NOT CONFIGURED (no RELAY_DATABASE_URL)')

# Platform DB
platform_url = os.environ.get('PLATFORM_DATABASE_URL')
if platform_url:
    try:
        conn = psycopg2.connect(platform_url, connect_timeout=5)
        cur = conn.cursor()
        cur.execute('SELECT 1')
        conn.close()
        print(f'Platform DB: OK')
    except Exception as e:
        print(f'Platform DB: FAIL ({e})')
else:
    print('Platform DB: NOT CONFIGURED (no PLATFORM_DATABASE_URL)')
"
```

### 3. Check Modal Infrastructure

```bash
echo ""
echo "=== Modal Infrastructure ==="
echo "Apps:"
modal app list 2>/dev/null | grep -E "civicos|NAME" || echo "  (unable to list apps)"
echo ""
echo "Secrets:"
modal secret list 2>/dev/null | grep -E "civicos|NAME" || echo "  (unable to list secrets)"
```

### 4. Summary

After running checks, output a summary table:

```
=== Summary ===

| Service      | Status |
|--------------|--------|
| API          | OK/FAIL |
| MCP          | OK/FAIL |
| Relay        | OK/FAIL |
| Main DB      | OK/FAIL |
| Relay DB     | OK/FAIL |
| Platform DB  | OK/FAIL |

Overall: [ALL HEALTHY / N issues found]
```

## When to Use

- Before deploying new code (verify current state)
- After deploying (verify nothing broke)
- When debugging user-reported issues
- During `/start` if services are involved in your work item
- Quick sanity check during launch phase work
