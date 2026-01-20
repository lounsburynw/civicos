# Database Backup

Create, verify, and restore PostgreSQL database backups. **Run before any destructive operation.**

## Usage

```
/db-backup [action] [options]
```

**Actions:**
- `create` - Selective backup of critical tables (default)
- `create --full` - Full backup including regenerable data
- `verify [file]` - Verify backup integrity
- `restore [file]` - Restore from backup
- `list` - List available backups
- `status` - Show current database size and backup health

## Examples

```
/db-backup                              # Selective backup (critical tables)
/db-backup create --full                # Full backup (all tables)
/db-backup create --label pre-reindex   # With label
/db-backup list                         # Show local backups
/db-backup status                       # Check sizes and health
/db-backup verify backups/civic_20260112.dump
/db-backup restore backups/civic_20260112.dump
```

## Backup Strategies

### Selective Backup (Default)

Backs up only **critical, non-regenerable** data - tables containing:
- Expensive API results (transcripts from AssemblyAI)
- User-generated content
- Historical records not available from source APIs

**Critical tables:**
```
meetings, transcripts, decisions, issues, videos, agenda_items,
budget_items, elections, elected_officials, election_contests,
etl_costs, operations
```

**Use when:** Pre-operation safety, frequent backups, fast recovery

### Full Backup

Backs up **all tables** including regenerable data:
- Vector embeddings (can rebuild with GPU compute)
- Legislation, municipal code (can re-fetch from APIs)
- Chunks (can re-extract from PDFs)

**Use when:** Quarterly snapshots, disaster recovery, migration, avoiding regeneration costs

## Steps

### 1. Check Current Database Size

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT pg_size_pretty(pg_database_size(current_database()));')
print(f'Total database size: {cur.fetchone()[0]}')
cur.execute('''
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)), n_live_tup
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;
''')
print('\\nTop 10 tables by size:')
for r in cur.fetchall(): print(f'  {r[0]}: {r[1]} ({r[2]} rows)')
"
```

**For corpus counts and coverage:** Use `/data-status` instead of raw SQL queries.

### 2. Create Selective Backup

```bash
source civicos-env/bin/activate

CRITICAL_TABLES="meetings,transcripts,decisions,issues,videos,agenda_items,budget_items,elections,elected_officials,election_contests,etl_costs,operations"
BACKUP_FILE="data/backups/civic_critical_$(date +%Y%m%d_%H%M%S).dump"

pg_dump "$DATABASE_URL" \
  -F c -v --no-owner --no-privileges \
  $(echo $CRITICAL_TABLES | tr ',' '\n' | sed 's/^/-t /') \
  -f "$BACKUP_FILE"

shasum -a 256 "$BACKUP_FILE" > "${BACKUP_FILE}.sha256"
ls -lh "$BACKUP_FILE"
```

### 3. Create Full Backup

```bash
BACKUP_FILE="data/backups/civic_full_$(date +%Y%m%d_%H%M%S).dump"

pg_dump "$DATABASE_URL" \
  -F c -v --no-owner --no-privileges \
  -f "$BACKUP_FILE"

shasum -a 256 "$BACKUP_FILE" > "${BACKUP_FILE}.sha256"
ls -lh "$BACKUP_FILE"
```

### 4. Verify Backup

```bash
# Checksum
shasum -a 256 -c "${BACKUP_FILE}.sha256"

# List contents
pg_restore -l "$BACKUP_FILE" | grep "TABLE DATA"
```

### 5. Restore Backup

```bash
# Create safety backup first
PRE_RESTORE="data/backups/pre_restore_$(date +%Y%m%d_%H%M%S).dump"
pg_dump "$DATABASE_URL" -F c -f "$PRE_RESTORE"

# Restore
pg_restore -d "$DATABASE_URL" \
  --clean --if-exists --no-owner --no-privileges -v \
  "$BACKUP_FILE"
```

### 6. Restore Single Table

```bash
pg_restore -d "$DATABASE_URL" \
  --data-only --table=transcripts --clean --if-exists \
  "$BACKUP_FILE"
```

## Critical vs Regenerable Data

Classify tables by regeneration cost:

| Category | Examples | Backup Priority |
|----------|----------|-----------------|
| **Irreplaceable** | User content, expensive API calls | Always backup |
| **Expensive to regenerate** | Transcripts (~$2-3/meeting) | Always backup |
| **Cheap to regenerate** | Vector embeddings (GPU compute) | Full backup only |
| **Free to regenerate** | API-sourced data (legislation, codes) | Full backup only |

## Backup Schedule

| Frequency | Type | Retention | Trigger |
|-----------|------|-----------|---------|
| Pre-operation | Selective | 7 days | Before destructive ops |
| Weekly | Selective | 4 weeks | Automated |
| Quarterly | Full | 1 year | Manual |

## Storage

```
data/backups/
├── civic_critical_*.dump       # Selective backups
├── civic_critical_*.dump.sha256
├── civic_full_*.dump           # Full backups (quarterly)
├── civic_full_*.dump.sha256
└── pre_restore_*.dump          # Safety backups
```

## Prerequisites

```bash
# Install PostgreSQL client (must match server version)
brew install postgresql    # macOS
apt install postgresql-client  # Ubuntu

pg_dump --version  # Verify version
```

## Supabase Automatic Backups

Supabase maintains automatic daily backups:
- Pro: 7 days retention
- Team: 14 days + point-in-time recovery
- Enterprise: 30 days + point-in-time recovery

Access via Dashboard → Settings → Database → Backups
