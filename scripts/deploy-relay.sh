#!/usr/bin/env bash
#
# Deploy a CivicOS relay instance.
#
# Usage:
#   ./scripts/deploy-relay.sh <jurisdiction> <platform>
#
# Examples:
#   ./scripts/deploy-relay.sh city-san-rafael modal     # Production (Modal)
#   ./scripts/deploy-relay.sh city-mill-valley fly       # Federation test (Fly.io)
#   ./scripts/deploy-relay.sh city-san-anselmo fly       # Federation test (Fly.io)
#   ./scripts/deploy-relay.sh city-mill-valley docker     # Local Docker test
#
# Platforms:
#   modal   - Deploy via Modal (production)
#   fly     - Deploy via Fly.io (federation testing)
#   docker  - Build and run locally via Docker

set -euo pipefail

JURISDICTION="${1:?Usage: $0 <jurisdiction> <platform>}"
PLATFORM="${2:?Usage: $0 <jurisdiction> <platform>}"

# Derive app name from jurisdiction
if [ "$JURISDICTION" = "city-san-rafael" ]; then
    RELAY_APP="civicos-relay"
else
    SUFFIX="${JURISDICTION#*-}"  # Strip level prefix (city-, county-, etc.)
    RELAY_APP="civicos-relay-${SUFFIX}"
fi

echo "Deploying relay: ${RELAY_APP}"
echo "  Jurisdiction: ${JURISDICTION}"
echo "  Platform:     ${PLATFORM}"
echo ""

case "$PLATFORM" in
    modal)
        CIVICOS_JURISDICTION="$JURISDICTION" modal deploy apps/civicos-relay/modal_relay.py
        ;;

    fly)
        # Generate fly.toml in repo root (paths must resolve relative to config)
        FLYFILE=".fly-${RELAY_APP}.toml"
        sed \
            -e "s|^app = .*|app = \"${RELAY_APP}\"|" \
            -e "s|CIVICOS_JURISDICTION = .*|CIVICOS_JURISDICTION = \"${JURISDICTION}\"|" \
            apps/civicos-relay/fly.toml > "$FLYFILE"

        echo "Generated config: ${FLYFILE}"
        echo ""

        # Check if app exists, create if not
        if ! fly status -a "$RELAY_APP" &>/dev/null; then
            echo "Creating Fly app: ${RELAY_APP}"
            fly apps create "$RELAY_APP" --org personal
        fi

        fly deploy -c "$FLYFILE"

        # Clean up generated config
        rm -f "$FLYFILE"
        ;;

    docker)
        docker build -f apps/civicos-relay/Dockerfile -t "$RELAY_APP" .
        echo ""
        echo "Run with:"
        echo "  docker run -p 8003:8003 --env-file .env -e CIVICOS_JURISDICTION=${JURISDICTION} ${RELAY_APP}"
        ;;

    *)
        echo "Unknown platform: ${PLATFORM}"
        echo "Supported: modal, fly, docker"
        exit 1
        ;;
esac

echo ""
echo "Done."
