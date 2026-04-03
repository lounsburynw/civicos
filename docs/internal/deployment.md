# Deployment

All production services run on Modal (serverless Python). Data lives in Supabase PostgreSQL. Blobs in Cloudflare R2.

## Services

| Service | Deploy Command | URL Pattern |
|---------|---------------|-------------|
| REST API | `modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py` | `civicos-api-*.modal.run` |
| MCP Server | `modal deploy apps/civicos-mcp/modal_mcp.py` | `civicos-mcp-*.modal.run` |
| Relay | `modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py` | `civicos-relay-*.modal.run` |
| Vector Indexing | `modal run scripts/modal_ingest.py` | (GPU job, not persistent) |

## Infrastructure

| Service | Purpose | Config |
|---------|---------|--------|
| Supabase (lhtuixsynupnkejpahxk, us-west-2) | Main DB — meetings, decisions, vectors | `DATABASE_URL` |
| Supabase (lvfikysdbdkpxemssuxa, us-west-1) | Relay DB — voices, subscriptions | `RELAY_DATABASE_URL` |
| Cloudflare R2 | Blob storage — PDFs, audio | `BLOB_STORAGE_URL` |
| Modal | Compute — API, MCP, relay, GPU jobs | Modal secrets |

Relay DB uses `db.PROJECT_REF.supabase.co:6543` pooler format (not `pooler.supabase.com`).

### Federation Test Relays (Fly.io)

| Relay | App Name | Database | Peer |
|-------|----------|----------|------|
| Mill Valley | `civicos-relay-mill-valley` | Neon (`ep-blue-base-akoamc38`) | San Anselmo |
| San Anselmo | `civicos-relay-san-anselmo` | Neon (`ep-old-term-akcsgm0j`) | Mill Valley |

Each test relay has its own Neon Postgres database (free tier) with the full coordination schema.

**Secrets per relay:** `RELAY_DATABASE_URL`, `CIVICOS_ADMIN_API_KEY`, `CIVICOS_ATTESTATION_PRIVATE_KEY`, `RELAY_PEERS`, `RELAY_SYNC_INTERVAL`

**Deploy:** `./scripts/deploy-relay.sh <jurisdiction> fly`

**Issuer setup:** `python3 scripts/setup_federation_issuers.py <generate|register|codes|status>`

Issuer configs are in `config/federation/` (gitignored — contains private keys).

## Secrets

Modal secrets are stored in the `civicos-secrets` (or jurisdiction-specific) secret group:

- `DATABASE_URL` — Supabase PostgreSQL connection string
- `RELAY_DATABASE_URL` — Relay Supabase connection string
- `OPENAI_API_KEY` — For embeddings and AI features
- `BLOB_STORAGE_URL` — R2 connection string
- `CIVICOS_ATTESTATION_PRIVATE_KEY` — For signing kind-30850 attestation events
- `GOOGLE_MAPS_API_KEY` — Geocoding (extension + API)
- `PLATFORM_DATABASE_URL` — Platform DB for usage logging and billing (in `civicos-platform` secret)
- `RELAY_ACCEPTANCE_POLICY` — Set `true` to enable rate limiting on relay writes (default: `false`)
- `RELAY_JURISDICTION` — Jurisdiction ID for per-jurisdiction rate limit policy (e.g., `city-san-rafael`)
- `RELAY_POLICY_FILE` — Override path for relay rate limit policies (see `config/relay_policies.json`)
- `TOKEN_ISSUER_SECRET` — 32-byte hex key for blind signature token issuance (in `civicos-token-issuer` secret)
- `TOKEN_ISSUER_MAX_SESSIONS` — Max concurrent nonce sessions per issuer (default: `5`, in `civicos-token-issuer` secret)
- `TOKEN_ISSUER_SESSION_TTL` — Nonce session expiry in seconds (default: `300`, in `civicos-token-issuer` secret)
- `TOKEN_ISSUER_PUBKEYS` — Comma-separated hex pubkeys of trusted token issuers for acceptance policy verification (in `civicos-env` secret)

Check secrets: `modal secret list`

## Modal Images

| Image | Used by | Size | Playwright |
|-------|---------|------|------------|
| `civic_image` | Most ingestion tasks | ~800MB | No |
| `simbli_image` | Simbli, bot-protected sites, onboarding | ~1.1GB | Yes (headless + stealth) |

The `simbli_image` includes `playwright` + `playwright-stealth` + Chromium for sites behind Cloudflare or Incapsula WAFs. Platform detection and universal adapter config generation use an escalating fetch strategy:

1. `requests` — fastest, works for ~90% of sites
2. `curl` subprocess — bypasses TLS fingerprinting
3. Playwright headless + `playwright-stealth` — bypasses Cloudflare JS challenges

**To add Playwright to a new Modal function:** use `image=simbli_image` in the `@app.function()` decorator. No display/Xvfb needed — stealth makes headless work.

**Local development:** `pip install playwright playwright-stealth && playwright install chromium`

## Monitoring

```bash
modal app list              # Running apps
modal app logs civicos-api  # Live logs
```

Health endpoints:
- API: `GET /health`
- MCP: `GET /health` (includes tool count)

## MCP Server Config

- Image: `debian_slim(python_version="3.11")`
- Memory: 4096 MB
- Timeout: 300s
- Min containers: 1 for city-san-rafael, 0 for reference jurisdictions
- Pre-builds embedding model (nomic) during image construction

## Security

- RLS enabled on Supabase via `scripts/sql/enable_rls.sql` — only service_role can access
- API key auth is optional, with usage logging
- Rate limiting: global per-client, plus stricter limits on AI (30/min) and admin (10/min) endpoints

## Never

- Deploy **production** services to Fly.io — Modal only. (Federation test relays use Fly.io intentionally for cross-platform testing.)
- Skip `load_dotenv()` when testing locally — `DATABASE_URL` won't be set
