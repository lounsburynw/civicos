Launch the Civic development servers.

## Quick Start

Run the dev launch script:

```bash
./scripts/dev.sh
```

This starts all three services:
- **REST API** on http://localhost:8001
- **WebSocket** on http://localhost:8002
- **Frontend** on http://localhost:5173

## Individual Services

Start services individually if needed:

```bash
./scripts/dev.sh api       # REST API only
./scripts/dev.sh ws        # WebSocket only
./scripts/dev.sh frontend  # Vue frontend only
```

## Environment Requirements

The script automatically:
1. Loads `.env` file
2. Sets `CIVIC_DEV_MODE=true`
3. Sets `CIVIC_WEB_KEY=dev_key_local` (matches frontend)
4. Activates the `civicos-env` virtual environment

## Required API Keys in `.env`

- `GOOGLE_MAPS_API_KEY` - For address geocoding (must have Geocoding API enabled)
- `OPENAI_API_KEY` - For AI conversation features (optional for basic testing)

## Open WebUI Frontend (Primary UX Surface)

The Open WebUI fork is a **separate repo** (`~/projects/civicos-openwebui`). For frontend iteration, run its Vite dev server directly — do NOT rebuild Docker for every change:

```bash
cd ~/projects/civicos-openwebui && npm run dev   # localhost:5173, hot reload
```

Only rebuild Docker for production testing:

```bash
cd ~/projects/civicos-openwebui
docker build -t civicos-openwebui:latest .
docker stop civicos-openwebui && docker rm civicos-openwebui
docker run -d --name civicos-openwebui -p 8080:8080 \
  --env-file .env --restart unless-stopped civicos-openwebui:latest
```

## Troubleshooting

If you see module import errors, ensure you're using `./scripts/dev.sh` which sets up the PYTHONPATH correctly.

If geocoding fails, verify your Google Maps API key has the Geocoding API enabled at:
https://console.cloud.google.com/apis/library/geocoding-backend.googleapis.com
