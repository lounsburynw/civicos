# Secrets Management Guide

This document provides a comprehensive reference for all secrets and API keys used by the Civic platform, including how to obtain them, security best practices, and environment-specific configurations.

## Quick Reference

### Required Secrets

| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `OPENAI_API_KEY` | LLM completions, embeddings (if using OpenAI) | [OpenAI Platform](https://platform.openai.com/api-keys) | Pay-per-use |
| `CIVICOS_WEB_KEY` | API authentication | Generate: `openssl rand -hex 32` | Free |
| `CIVICOS_CORS_ORIGINS` | Security - allowed origins | Configure based on deployment | Free |

### Optional Secrets by Category

#### Alternative LLM Providers
| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `ANTHROPIC_API_KEY` | Claude API access | [Anthropic Console](https://console.anthropic.com/) | Pay-per-use |
| `GOOGLE_API_KEY` | Gemini API access | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | Pay-per-use |
| `GROQ_API_KEY` | Fast inference | [Groq Console](https://console.groq.com) | Free tier available |
| `PERPLEXITY_API_KEY` | Research/search mode | [Perplexity Settings](https://www.perplexity.ai/settings/api) | Pay-per-use |
| `OPENROUTER_API_KEY` | Unified model access | [OpenRouter Keys](https://openrouter.ai/keys) | Pay-per-use |

#### Database Connections
| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `DATABASE_URL` | Main Supabase Postgres (civic data) | [Supabase Dashboard](https://supabase.com/dashboard) > Connect | Free tier available |
| `RELAY_DATABASE_URL` | Relay Supabase Postgres (coordination data) | Separate Supabase project > Connect | Free tier available |

#### External Data Services
| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `LEGISCAN_API_KEY` | State/federal legislative data | [LegiScan](https://legiscan.com/legiscan) | Free tier (50/day) |
| `ASSEMBLYAI_API_KEY` | Meeting transcription | [AssemblyAI](https://www.assemblyai.com/) | Pay-per-use |
| `GOOGLE_MAPS_API_KEY` | Address geocoding | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | $200 free/month |
| `IPINFO_TOKEN` | IP-based location | [IPInfo](https://ipinfo.io/) | Free tier (50k/month) |

#### PDF Parsing (Choose One Tier)
| Secret | Purpose | Where to Obtain | Cost | Tier |
|--------|---------|-----------------|------|------|
| `LLAMAPARSE_API_KEY` | Advanced PDF parsing | [LlamaCloud](https://cloud.llamaindex.ai/) | Pay-per-page | Professional |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Enterprise document parsing | [Azure Portal](https://portal.azure.com) | Pay-per-page | Enterprise |
| `MISTRAL_API_KEY` | OCR extraction | [Mistral AI](https://mistral.ai/) | Pay-per-use | Research |

#### Email & Notifications
| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `GMAIL_APP_PASSWORD` | Digest email sending | [Google App Passwords](https://myaccount.google.com/apppasswords) | Free |
| `CIVICOS_SMTP_PASSWORD` | SMTP server auth | Your email provider | Varies |

---

## Detailed Configuration

### 1. OpenAI API Key (REQUIRED)

**Purpose**: Powers LLM completions and (optionally) embeddings.

**Obtaining**:
1. Create account at https://platform.openai.com
2. Navigate to API Keys section
3. Create new secret key
4. Copy immediately (shown only once)

**Configuration**:
```bash
OPENAI_API_KEY=sk-proj-...

# Optional tuning
OPENAI_MODEL=gpt-4o-mini          # Default model
OPENAI_TEMPERATURE=0.7             # Response creativity (0-1)
OPENAI_MAX_TOKENS=2000             # Max response length
OPENAI_FALLBACK_MODEL=gpt-3.5-turbo  # Fallback if primary fails
```

**Cost Management**:
- Use `gpt-4o-mini` for most operations (10x cheaper than gpt-4)
- Set `OPENAI_MAX_TOKENS` to prevent runaway responses
- Monitor usage at https://platform.openai.com/usage

**Validation**:
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | head -c 100
```

---

### 2. Database URLs (REQUIRED)

CivicOS uses **two separate Supabase databases** — one for civic read data, one for coordination/relay data.

| Env Var | Purpose | Data |
|---------|---------|------|
| `DATABASE_URL` | Jurisdiction data (read-heavy) | Meetings, decisions, vectors, legislation |
| `RELAY_DATABASE_URL` | Coordination data (write-heavy) | Voices, actions, subscriptions, sync |

These are separate by design — different access patterns, different scaling needs, and in a federated world, relays are independently deployable.

**Current (Pilot)**: One jurisdiction DB (San Rafael), one relay. Both are env vars pointing to Supabase Postgres instances.

**Future (Federation)**: N jurisdiction DBs and N relays, with a routing/registry layer mapping jurisdictions to their DB and relay URLs. The current env vars are per-deployment, not per-jurisdiction — scaling beyond one jurisdiction will require a `JURISDICTION_REGISTRY_URL` or equivalent service discovery mechanism.

#### Obtaining the URL

1. Go to Supabase Dashboard > your project > **Connect**
2. Select **Method: Transaction pooler** (NOT "Direct connection")
3. Copy the URI

#### Use the Transaction Pooler URL

The **direct connection** URL (`db.PROJECT_REF.supabase.co:5432`) has issues:
- IPv6-only without the IPv4 add-on
- Bypasses connection pooling (exhausts connections under load)

The **transaction pooler** URL format varies by project — always check the Supabase Connect dialog:

```bash
# Shared pooler host (some projects):
postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres

# Project-specific host (other projects):
postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:6543/postgres
```

The region in the pooler host **must match** the project's region (e.g., `us-west-1` for N. California, `us-west-2` for Oregon).

#### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `could not translate host name` | Wrong host or IPv6-only direct URL | Use transaction pooler URL |
| `Tenant or user not found` | Wrong region in pooler host, or project paused | Check region; restore if paused |
| `password authentication failed` | Wrong password or user format | Reset in Project Settings > Database |
| `SASL authentication failed` | Mixed up direct host with pooler port | Use exact URL from Connect dialog |

**Paused projects**: Free-tier Supabase projects auto-pause after inactivity. After restoring, the pooler may take several minutes to register the project.

#### Validation

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
for var in ['DATABASE_URL', 'RELAY_DATABASE_URL']:
    url = os.environ.get(var)
    if not url:
        print(f'{var}: NOT SET'); continue
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
        conn.cursor().execute('SELECT 1')
        conn.close()
        print(f'{var}: OK')
    except Exception as e:
        print(f'{var}: FAILED - {e}')
"
```

#### Schema Migrations

- Main DB: managed by the core CivicOS package
- Relay DB: run `scripts/sql/add_coordination_tables.sql` then `scripts/sql/add_action_events.sql`

---

### 3. CIVICOS_WEB_KEY (REQUIRED-PROD)


**Purpose**: Bearer token for API authentication.

**Generation**:
```bash
# Development (use default)
CIVICOS_WEB_KEY=dev_key_local

# Production (generate strong token)
CIVICOS_WEB_KEY=$(openssl rand -hex 32)
```

**Security Requirements**:
- Production: Must be at least 32 characters
- Never reuse across environments
- Rotate quarterly or after any suspected compromise

**Usage**:
```bash
curl -H "Authorization: Bearer $CIVICOS_WEB_KEY" \
  http://localhost:8001/api/v1/health
```

---

### 4. CIVICOS_CORS_ORIGINS (REQUIRED-PROD)

**Purpose**: Restricts which domains can make cross-origin requests.

**Configuration**:
```bash
# Development - not required (allows localhost by default)

# Staging
CIVICOS_CORS_ORIGINS=https://staging.civic.example.com

# Production
CIVICOS_CORS_ORIGINS=https://civic.example.com,https://www.civic.example.com
```

**Security Notes**:
- Never use `*` in production
- Include all legitimate frontend domains
- Update when adding new subdomains

---

### 5. Embeddings Configuration

**Default (Free)**:
Uses local `all-MiniLM-L6-v2` model - no API key required.

```bash
CIVICOS_EMBEDDING_PROVIDER=local
CIVICOS_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

**OpenAI Embeddings (Better Quality)**:
```bash
CIVICOS_EMBEDDING_PROVIDER=openai
CIVICOS_EMBEDDING_MODEL=text-embedding-3-small
# Requires OPENAI_API_KEY
```

---

### 6. PDF Parsing Tiers

The system supports tiered PDF parsing. Choose based on document complexity:

| Tier | Provider | Best For | Monthly Cost Estimate |
|------|----------|----------|----------------------|
| **Foundation** (default) | PyMuPDF | Simple PDFs, text-based | Free |
| **Professional** | LlamaParse | Complex layouts, tables | ~$10-50 |
| **Enterprise** | Azure Doc Intelligence | High-volume, compliance | ~$50-200 |
| **Research** | Mistral OCR | Scanned documents | ~$5-20 |

**Configuring Professional Tier**:
```bash
LLAMAPARSE_API_KEY=llx-...
```

**Configuring Enterprise Tier**:
```bash
AZURE_DOCUMENT_INTELLIGENCE_KEY=...
AZURE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
```

---

## Environment-Specific Setup

### Development Environment

Minimal configuration for local development:

```bash
# .env for development
CIVICOS_ENV=development
OPENAI_API_KEY=sk-proj-...
CIVICOS_WEB_KEY=dev_key_local
```

### Staging Environment

Full testing configuration:

```bash
# .env for staging
CIVICOS_ENV=staging
OPENAI_API_KEY=sk-proj-...
CIVICOS_WEB_KEY=$(openssl rand -hex 32)
CIVICOS_CORS_ORIGINS=https://staging.civic.example.com

# Rate limiting (test production behavior)
ENABLE_RATE_LIMIT=true
RATE_LIMIT_PER_MINUTE=60

# Test email sending
GMAIL_EMAIL=staging-notifications@example.com
GMAIL_APP_PASSWORD=...
```

### Production Environment

Full production configuration:

```bash
# .env for production
CIVICOS_ENV=production
OPENAI_API_KEY=sk-proj-...
CIVICOS_WEB_KEY=$(openssl rand -hex 32)
CIVICOS_CORS_ORIGINS=https://civic.example.com,https://www.civic.example.com

# Security hardening
ENABLE_RATE_LIMIT=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
RATE_LIMIT_BURST=10

# Production notifications
CIVICOS_ALERT_EMAILS=admin@example.com,ops@example.com
GMAIL_EMAIL=notifications@example.com
GMAIL_APP_PASSWORD=...

# Optional: Enhanced services
ASSEMBLYAI_API_KEY=...
LEGISCAN_API_KEY=...
```

---

## Security Best Practices

### Never Commit Secrets
```bash
# .gitignore should include:
.env
.env.local
.env.production
*.pem
*.key
```

### Use Environment Variables
Never hardcode secrets in source files. Always use `os.environ.get()`:

```python
# Good
api_key = os.environ.get("OPENAI_API_KEY")

# Bad
api_key = "sk-proj-..."
```

### Key Rotation Schedule

| Secret | Rotation Frequency | Trigger Events |
|--------|-------------------|----------------|
| `CIVICOS_WEB_KEY` | Quarterly | Team member leaves, suspected breach |
| `OPENAI_API_KEY` | Annually | Cost anomaly, suspected breach |
| `GMAIL_APP_PASSWORD` | Annually | Account compromise |
| Other API keys | Annually | Provider recommendation |

### Secrets in Container Deployments

For Docker deployments, use environment variables:

```bash
# Never bake secrets into images
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY civic-os

# Or use --env-file
docker run --env-file .env.production civic-os
```

For Kubernetes, use Secrets:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: civic-secrets
type: Opaque
stringData:
  OPENAI_API_KEY: sk-proj-...
  CIVICOS_WEB_KEY: ...
```

---

## Validation & Troubleshooting

### Startup Validation

The system validates required secrets on startup. Check logs for:

```
INFO: Environment: production
INFO: OPENAI_API_KEY: configured
INFO: CIVICOS_WEB_KEY: configured (production-grade)
INFO: CIVICOS_CORS_ORIGINS: 2 origins configured
```

### Common Errors

**"OPENAI_API_KEY not set"**
```bash
# Check if set
echo $OPENAI_API_KEY

# Verify in .env file
grep OPENAI_API_KEY .env
```

**"Invalid API key"**
```bash
# Test key directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**"CORS error in browser"**
- Check `CIVICOS_CORS_ORIGINS` includes your frontend URL
- Ensure protocol (http vs https) matches exactly

**"Rate limit exceeded"**
- Check `RATE_LIMIT_PER_MINUTE` settings
- For development, set `ENABLE_RATE_LIMIT=false`

### Validating All Secrets

Run the validation script:
```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

required = ['OPENAI_API_KEY']
required_prod = ['CIVICOS_WEB_KEY', 'CIVICOS_CORS_ORIGINS']
optional = ['ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'ASSEMBLYAI_API_KEY']

env = os.environ.get('CIVICOS_ENV', 'development')
print(f'Environment: {env}')

print('\nRequired:')
for key in required:
    val = os.environ.get(key, '')
    status = 'OK' if val else 'MISSING'
    print(f'  {key}: {status}')

print('\nRequired (Production):')
for key in required_prod:
    val = os.environ.get(key, '')
    needed = env in ('production', 'staging')
    status = 'OK' if val else ('MISSING' if needed else 'not required')
    print(f'  {key}: {status}')

print('\nOptional (configured):')
for key in optional:
    if os.environ.get(key):
        print(f'  {key}: configured')
"
```

---

## Cost Estimation

### Cost Targets

| Service | Expected Usage | Monthly Cost |
|---------|---------------|--------------|
| OpenAI (gpt-4o-mini) | ~10,000 queries | ~$1-3 |
| OpenAI Embeddings | N/A (using local) | $0 |
| AssemblyAI | ~5 meeting transcripts | ~$2-5 |
| LegiScan | Free tier | $0 |
| Google Maps | <200 queries | $0 |

**Cost Optimization Tips**:
1. Use `gpt-4o-mini` instead of `gpt-4` for most queries
2. Use local embeddings (`CIVICOS_EMBEDDING_PROVIDER=local`)
3. Cache legislative data to reduce API calls
4. Batch meeting transcriptions during off-peak

---

## Summary Checklist

Before deployment, verify:

- [ ] `OPENAI_API_KEY` is set and valid
- [ ] `CIVICOS_WEB_KEY` is production-grade (32+ chars, randomly generated)
- [ ] `CIVICOS_CORS_ORIGINS` lists all frontend domains
- [ ] `.env` file is NOT committed to git
- [ ] Secrets are rotated on regular schedule
- [ ] Team has documented where production secrets are stored
- [ ] Backup of secrets exists in secure location (not git)
