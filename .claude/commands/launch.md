Launch the CivicOS development environment.

## What Gets Started

1. **REST API** on http://localhost:8001 (backend — serves civic data)
2. **WebSocket server** (optional, for real-time coordination)

## Steps

Start the API backend:

```bash
./scripts/dev.sh api
```

Optionally, start the WebSocket server in parallel:

```bash
./scripts/dev.sh ws
```

## Verify

- API health: http://localhost:8001/health
- API docs: http://localhost:8001/docs

## Environment

The `./scripts/dev.sh` script automatically:
1. Loads `.env` file
2. Sets `CIVICOS_DEV_MODE=true`
3. Sets `CIVICOS_WEB_KEY=dev_key_local`
4. Uses `civicos-env` venv Python directly

## Required API Keys in `.env`

- `GOOGLE_MAPS_API_KEY` - For address geocoding (must have Geocoding API enabled)

## Browser Extension (Primary UX Surface)

For browser extension development:

```bash
cd apps/civicos-extension && npm run dev          # Watch mode with hot reload
# Then load unpacked from apps/civicos-extension/dist in chrome://extensions
```

## Open WebUI (Secondary Surface)

```bash
cd ~/projects/civicos-openwebui && npm run dev    # Dev server at localhost:5173
```

## Notes

- The **browser extension** is the primary user surface
- The Open WebUI fork is a **separate repo** (`~/projects/civicos-openwebui`, symlinked at `apps/civicos-openwebui-fork/`)
- `apps/civicos-workspace/` is a **deprecated** Vue frontend — do not use
