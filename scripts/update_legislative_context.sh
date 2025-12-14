#!/bin/bash
#
# Weekly Legislative Context Update
# Discovers new locally-relevant legislation using LegiScan API + LLM
#
# Setup cron job (runs every Monday at 9am):
#   crontab -e
#   0 9 * * 1 /path/to/civic/scripts/update_legislative_context.sh >> /path/to/civic/logs/legislative_updates.log 2>&1
#
# Requirements:
#   - LEGISCAN_API_KEY environment variable (get from https://legiscan.com/)
#   - OPENAI_API_KEY environment variable
#   - Python 3.8+ with openai package installed

set -e

# Change to project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check required API keys
if [ -z "$LEGISCAN_API_KEY" ]; then
    echo "ERROR: LEGISCAN_API_KEY not set"
    echo "Register at https://legiscan.com/ for free API access (30,000 queries/month)"
    exit 1
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY not set"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs

LOG_FILE="logs/legislative_updates_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee "$LOG_FILE"
echo "Legislative Context Update" | tee -a "$LOG_FILE"
echo "$(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Activate virtual environment if it exists
if [ -d "civic-env" ]; then
    source civic-env/bin/activate
fi

# Run discovery for all topics
# Use --review flag to enable dry-run mode for manual review
python src/legislative_discovery.py --topic all --days 30 --review | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Update complete. Review output above." | tee -a "$LOG_FILE"
echo "To apply changes, re-run without --review flag:" | tee -a "$LOG_FILE"
echo "  python src/legislative_discovery.py --topic <topic> --days 30" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Keep only last 10 log files
cd logs
ls -t legislative_updates_*.log | tail -n +11 | xargs rm -f
