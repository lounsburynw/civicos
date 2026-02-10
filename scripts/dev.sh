#!/bin/bash
# CivicOS Development Server Launcher
# Usage: ./scripts/dev.sh [api|api-fastapi|ws|frontend|all]
#
# Starts the development servers with proper environment configuration.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Development environment overrides
export CIVICOS_DEV_MODE=true
export CIVICOS_WEB_KEY="${CIVICOS_WEB_KEY:-dev_key_local}"

# Use venv Python/uvicorn directly (source activate doesn't persist in all shells)
VENV="$PROJECT_ROOT/civicos-env/bin"

start_api() {
    echo "Starting FastAPI server on http://localhost:8001..."
    echo "  - OpenAPI docs at http://localhost:8001/docs"
    echo "  - ReDoc at http://localhost:8001/redoc"
    "$VENV/uvicorn" civicos_services.servers.api:app --host 0.0.0.0 --port 8001 --reload
}

start_websocket() {
    echo "Starting WebSocket server on http://localhost:8002..."
    "$VENV/python" -m civicos_services.servers.civic_socketio_server
}

start_frontend() {
    echo "Starting frontend on http://localhost:5173..."
    cd "$PROJECT_ROOT/apps/civicos-workspace"
    npm run dev
}

start_all() {
    echo "Starting all CivicOS services..."
    echo ""

    # Start FastAPI server in background
    "$VENV/uvicorn" civicos_services.servers.api:app --host 0.0.0.0 --port 8001 &
    API_PID=$!
    echo "API server started (PID: $API_PID)"

    # Start WebSocket in background
    "$VENV/python" -m civicos_services.servers.civic_socketio_server &
    WS_PID=$!
    echo "WebSocket server started (PID: $WS_PID)"

    # Give servers time to start
    sleep 2

    # Start frontend (foreground)
    cd "$PROJECT_ROOT/apps/civicos-workspace"
    npm run dev

    # Cleanup on exit
    kill $API_PID $WS_PID 2>/dev/null
}

show_help() {
    echo "CivicOS Development Server Launcher"
    echo ""
    echo "Usage: ./scripts/dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  api          Start FastAPI server only (port 8001, with /docs)"
    echo "  ws           Start WebSocket server only (port 8002)"
    echo "  frontend     Start Vue frontend only (port 5173)"
    echo "  all          Start all servers (default)"
    echo "  help         Show this help message"
    echo ""
    echo "Environment:"
    echo "  CIVICOS_DEV_MODE=true"
    echo "  CIVICOS_WEB_KEY=dev_key_local (or from .env)"
    echo "  GOOGLE_MAPS_API_KEY (from .env)"
    echo ""
    echo "API Documentation:"
    echo "  OpenAPI: http://localhost:8001/docs"
    echo "  ReDoc:   http://localhost:8001/redoc"
}

case "${1:-all}" in
    api)
        start_api
        ;;
    ws)
        start_websocket
        ;;
    frontend)
        start_frontend
        ;;
    all)
        start_all
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
