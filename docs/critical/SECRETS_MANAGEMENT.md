# Secrets Management Guide

This document provides a comprehensive reference for all secrets and API keys used by the Civic platform, including how to obtain them, security best practices, and environment-specific configurations.

## Quick Reference

### Required Secrets

| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `OPENAI_API_KEY` | LLM completions, embeddings (if using OpenAI) | [OpenAI Platform](https://platform.openai.com/api-keys) | Pay-per-use |
| `CIVIC_WEB_KEY` | API authentication | Generate: `openssl rand -hex 32` | Free |
| `CIVIC_CORS_ORIGINS` | Security - allowed origins | Configure based on deployment | Free |

### Optional Secrets by Category

#### Alternative LLM Providers
| Secret | Purpose | Where to Obtain | Cost |
|--------|---------|-----------------|------|
| `ANTHROPIC_API_KEY` | Claude API access | [Anthropic Console](https://console.anthropic.com/) | Pay-per-use |
| `GOOGLE_API_KEY` | Gemini API access | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) | Pay-per-use |
| `GROQ_API_KEY` | Fast inference | [Groq Console](https://console.groq.com) | Free tier available |
| `PERPLEXITY_API_KEY` | Research/search mode | [Perplexity Settings](https://www.perplexity.ai/settings/api) | Pay-per-use |
| `OPENROUTER_API_KEY` | Unified model access | [OpenRouter Keys](https://openrouter.ai/keys) | Pay-per-use |

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
| `CIVIC_SMTP_PASSWORD` | SMTP server auth | Your email provider | Varies |

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

### 2. CIVIC_WEB_KEY (REQUIRED-PROD)

**Purpose**: Bearer token for API authentication.

**Generation**:
```bash
# Development (use default)
CIVIC_WEB_KEY=dev_key_local

# Production (generate strong token)
CIVIC_WEB_KEY=$(openssl rand -hex 32)
```

**Security Requirements**:
- Production: Must be at least 32 characters
- Never reuse across environments
- Rotate quarterly or after any suspected compromise

**Usage**:
```bash
curl -H "Authorization: Bearer $CIVIC_WEB_KEY" \
  http://localhost:8001/api/v1/health
```

---

### 3. CIVIC_CORS_ORIGINS (REQUIRED-PROD)

**Purpose**: Restricts which domains can make cross-origin requests.

**Configuration**:
```bash
# Development - not required (allows localhost by default)

# Staging
CIVIC_CORS_ORIGINS=https://staging.civic.example.com

# Production
CIVIC_CORS_ORIGINS=https://civic.example.com,https://www.civic.example.com
```

**Security Notes**:
- Never use `*` in production
- Include all legitimate frontend domains
- Update when adding new subdomains

---

### 4. Embeddings Configuration

**Default (Free)**:
Uses local `all-MiniLM-L6-v2` model - no API key required.

```bash
CIVIC_EMBEDDING_PROVIDER=local
CIVIC_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

**OpenAI Embeddings (Better Quality)**:
```bash
CIVIC_EMBEDDING_PROVIDER=openai
CIVIC_EMBEDDING_MODEL=text-embedding-3-small
# Requires OPENAI_API_KEY
```

---

### 5. PDF Parsing Tiers

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
CIVIC_ENV=development
OPENAI_API_KEY=sk-proj-...
CIVIC_WEB_KEY=dev_key_local
```

### Staging Environment

Full testing configuration:

```bash
# .env for staging
CIVIC_ENV=staging
OPENAI_API_KEY=sk-proj-...
CIVIC_WEB_KEY=$(openssl rand -hex 32)
CIVIC_CORS_ORIGINS=https://staging.civic.example.com

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
CIVIC_ENV=production
OPENAI_API_KEY=sk-proj-...
CIVIC_WEB_KEY=$(openssl rand -hex 32)
CIVIC_CORS_ORIGINS=https://civic.example.com,https://www.civic.example.com

# Security hardening
ENABLE_RATE_LIMIT=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
RATE_LIMIT_BURST=10

# Production notifications
CIVIC_ALERT_EMAILS=admin@example.com,ops@example.com
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
| `CIVIC_WEB_KEY` | Quarterly | Team member leaves, suspected breach |
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
  CIVIC_WEB_KEY: ...
```

---

## Validation & Troubleshooting

### Startup Validation

The system validates required secrets on startup. Check logs for:

```
INFO: Environment: production
INFO: OPENAI_API_KEY: configured
INFO: CIVIC_WEB_KEY: configured (production-grade)
INFO: CIVIC_CORS_ORIGINS: 2 origins configured
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
- Check `CIVIC_CORS_ORIGINS` includes your frontend URL
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
required_prod = ['CIVIC_WEB_KEY', 'CIVIC_CORS_ORIGINS']
optional = ['ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'ASSEMBLYAI_API_KEY']

env = os.environ.get('CIVIC_ENV', 'development')
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

### Target: <$7/month operational

| Service | Expected Usage | Monthly Cost |
|---------|---------------|--------------|
| OpenAI (gpt-4o-mini) | ~10,000 queries | ~$1-3 |
| OpenAI Embeddings | N/A (using local) | $0 |
| AssemblyAI | ~5 meeting transcripts | ~$2-5 |
| LegiScan | Free tier | $0 |
| Google Maps | <200 queries | $0 |

**Cost Optimization Tips**:
1. Use `gpt-4o-mini` instead of `gpt-4` for most queries
2. Use local embeddings (`CIVIC_EMBEDDING_PROVIDER=local`)
3. Cache legislative data to reduce API calls
4. Batch meeting transcriptions during off-peak

---

## Summary Checklist

Before deployment, verify:

- [ ] `OPENAI_API_KEY` is set and valid
- [ ] `CIVIC_WEB_KEY` is production-grade (32+ chars, randomly generated)
- [ ] `CIVIC_CORS_ORIGINS` lists all frontend domains
- [ ] `.env` file is NOT committed to git
- [ ] Secrets are rotated on regular schedule
- [ ] Team has documented where production secrets are stored
- [ ] Backup of secrets exists in secure location (not git)
