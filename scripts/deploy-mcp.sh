#!/bin/bash
# CivicOS MCP Server Deployment Script
# Deploys the MCP server to Fly.io for Claude.ai and ChatGPT access
#
# Prerequisites:
#   - Fly.io CLI installed: brew install flyctl
#   - Authenticated: fly auth login
#   - DATABASE_URL available (Supabase)
#
# Usage:
#   ./scripts/deploy-mcp.sh          # Deploy to Fly.io
#   ./scripts/deploy-mcp.sh local    # Test locally on port 8099
#   ./scripts/deploy-mcp.sh ngrok    # Local + ngrok tunnel (requires ngrok)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

MODE="${1:-deploy}"

case "$MODE" in
    local)
        echo "=== Starting MCP server locally on port 8099 ==="
        source civicos-env/bin/activate
        python apps/civicos-mcp/civicos_server.py -t http -p 8099
        ;;

    ngrok)
        echo "=== Starting MCP server with ngrok tunnel ==="
        if ! command -v ngrok &> /dev/null; then
            echo "Error: ngrok not installed. Install with: brew install ngrok"
            exit 1
        fi

        # Start server in background
        source civicos-env/bin/activate
        python apps/civicos-mcp/civicos_server.py -t http -p 8099 &
        SERVER_PID=$!

        # Give server time to start
        sleep 3

        # Start ngrok
        echo "Starting ngrok tunnel..."
        ngrok http 8099

        # Cleanup on exit
        kill $SERVER_PID 2>/dev/null
        ;;

    deploy)
        echo "=== Deploying MCP server to Fly.io ==="

        # Check Fly.io CLI
        if ! command -v fly &> /dev/null; then
            echo "Error: Fly CLI not installed. Install with: brew install flyctl"
            exit 1
        fi

        # Check authentication
        if ! fly auth whoami &> /dev/null; then
            echo "Error: Not authenticated. Run: fly auth login"
            exit 1
        fi

        # Check if app exists, create if not
        if ! fly apps list | grep -q "civicos-mcp"; then
            echo "Creating Fly.io app: civicos-mcp"
            fly apps create civicos-mcp --org personal
        fi

        # Set DATABASE_URL secret if not already set
        if ! fly secrets list --app civicos-mcp 2>/dev/null | grep -q "DATABASE_URL"; then
            echo ""
            echo "DATABASE_URL secret not set. You need to set it:"
            echo "  fly secrets set DATABASE_URL='postgresql://...' --app civicos-mcp"
            echo ""
            read -p "Enter DATABASE_URL (or press Enter to skip): " DB_URL
            if [ -n "$DB_URL" ]; then
                fly secrets set DATABASE_URL="$DB_URL" --app civicos-mcp
            else
                echo "Warning: DATABASE_URL not set. Server may not function correctly."
            fi
        fi

        # Deploy
        echo "Deploying..."
        fly deploy --config fly-mcp.toml

        echo ""
        echo "=== Deployment Complete ==="
        echo "MCP Server URL: https://civicos-mcp.fly.dev/mcp"
        echo ""
        echo "To connect from ChatGPT:"
        echo "  1. Enable developer mode: Settings > Connectors > Advanced > Developer mode"
        echo "  2. Create connector: Settings > Connectors > Create"
        echo "  3. Enter URL: https://civicos-mcp.fly.dev/mcp"
        echo ""
        echo "To connect from Claude.ai:"
        echo "  1. Settings > Connectors > Add connector"
        echo "  2. Enter URL: https://civicos-mcp.fly.dev/mcp"
        echo ""
        echo "View logs: fly logs --app civicos-mcp"
        ;;

    *)
        echo "Usage: $0 [local|ngrok|deploy]"
        echo "  local  - Test locally on port 8099"
        echo "  ngrok  - Local with ngrok HTTPS tunnel"
        echo "  deploy - Deploy to Fly.io (default)"
        exit 1
        ;;
esac
