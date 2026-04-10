# Enable RLS on All Public Tables

Enable Row Level Security on every table in the `public` schema across both Supabase databases. **Run after any migration that adds new tables.**

## Usage

```
/rls [target]
```

**Targets:**
- `main` - Main database only (default)
- `relay` - Relay database only
- `both` - Both databases
- `status` - Check current RLS status without making changes

## What It Does

Runs `scripts/sql/enable_rls.sql` which dynamically discovers all `public.*` tables and:
1. Enables RLS on each table
2. Creates a `service_role_only` policy that denies all access via `anon`/`authenticated` roles
3. `service_role` (used by our Python backend) bypasses RLS — no impact to the app

The script is idempotent — safe to re-run anytime.

## Steps

### 1. Check Current RLS Status

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2

def check_rls(label, url_key):
    url = os.environ.get(url_key)
    if not url:
        print(f'{label}: {url_key} not set, skipping')
        return
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute('''
        SELECT tablename, rowsecurity
        FROM pg_tables
        WHERE schemaname = \'public\' AND tablename NOT LIKE \'pg_%\'
        ORDER BY tablename
    ''')
    rows = cur.fetchall()
    unprotected = [r[0] for r in rows if not r[1]]
    print(f'{label}: {len(rows)} tables, {len(unprotected)} without RLS')
    if unprotected:
        for t in unprotected:
            print(f'  ⚠ {t}')
    else:
        print('  All tables secured.')
    conn.close()

check_rls('Main DB', 'DATABASE_URL')
check_rls('Relay DB', 'RELAY_DATABASE_URL')
"
```

If the target is `status`, stop here and report the results.

### 2. Apply RLS

Read `scripts/sql/enable_rls.sql` and execute it against the target database(s).

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2

def apply_rls(label, url_key):
    url = os.environ.get(url_key)
    if not url:
        print(f'{label}: {url_key} not set, skipping')
        return
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    with open('scripts/sql/enable_rls.sql') as f:
        sql = f.read()
    cur.execute(sql)
    # Verify
    cur.execute('''
        SELECT tablename, rowsecurity
        FROM pg_tables
        WHERE schemaname = \'public\' AND tablename NOT LIKE \'pg_%\'
        ORDER BY tablename
    ''')
    rows = cur.fetchall()
    unprotected = [r[0] for r in rows if not r[1]]
    print(f'{label}: {len(rows)} tables secured, {len(unprotected)} remaining gaps')
    conn.close()

# Apply to target database(s) based on the argument
apply_rls('Main DB', 'DATABASE_URL')
# For relay: apply_rls('Relay DB', 'RELAY_DATABASE_URL')
"
```

### 3. Verify

Re-run the status check from step 1 to confirm all tables show RLS enabled.

## When to Run

- After running any `scripts/sql/add_*.sql` migration
- After `/onboard` if it creates new tables
- When Supabase dashboard shows RLS warnings
- Periodically as a hygiene check
