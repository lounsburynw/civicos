Launch the CivicOS development environment.

## What Gets Started

1. **REST API** on http://localhost:8001 (backend — serves civic data)
2. **Open WebUI** on http://localhost:5173 (primary frontend — hot reload)

## Steps

Start the API backend:

```bash
./scripts/dev.sh api
```

Then, in parallel, start the Open WebUI frontend dev server:

```bash
cd ~/projects/civicos-openwebui && npm run dev
```

## Verify

- API health: http://localhost:8001/health
- API docs: http://localhost:8001/docs
- Frontend: http://localhost:5173

## Environment

The `./scripts/dev.sh` script automatically:
1. Loads `.env` file
2. Sets `CIVICOS_DEV_MODE=true`
3. Sets `CIVICOS_WEB_KEY=dev_key_local`
4. Uses `civicos-env` venv Python directly

## Required API Keys in `.env`

- `GOOGLE_MAPS_API_KEY` - For address geocoding (must have Geocoding API enabled)

## Docker (Production Testing Only)

Only rebuild Docker when testing the production build, not for development:

```bash
cd ~/projects/civicos-openwebui
docker build -t civicos-openwebui:latest .
docker stop civicos-openwebui && docker rm civicos-openwebui
docker run -d --name civicos-openwebui -p 8080:8080 \
  --env-file .env --restart unless-stopped civicos-openwebui:latest
```

## Notes

- The Open WebUI fork is a **separate repo** (`~/projects/civicos-openwebui`, symlinked at `apps/civicos-openwebui-fork/`)
- `apps/civicos-workspace/` is a **deprecated** Vue frontend — do not use
- WebSocket server (`./scripts/dev.sh ws`) is optional for most development
