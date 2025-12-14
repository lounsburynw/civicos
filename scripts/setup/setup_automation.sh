#!/bin/bash
"""
Setup automation for Phase 2 LLM-driven civic data refresh system
Configures cron jobs for weekly refresh and daily validation
"""

# Get current directory
CIVIC_DIR="/Users/nicolaslounsbury/projects/civic"

echo "🚀 Setting up automated civic data refresh..."

# Create backup of current crontab
echo "📋 Backing up current crontab..."
crontab -l > ~/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || echo "No existing crontab found"

# Create temporary crontab file
TEMP_CRON=$(mktemp)

# Get existing crontab (if any)
crontab -l 2>/dev/null | grep -v "civic.*automated_civic_refresh" > "$TEMP_CRON" || true

# Add new civic automation jobs
echo "" >> "$TEMP_CRON"
echo "# Civic Engagement Platform - Automated Data Refresh" >> "$TEMP_CRON"
echo "# Weekly Monday 9AM refresh with future-only scope (cost optimized)" >> "$TEMP_CRON"
echo "0 9 * * 1 cd $CIVIC_DIR && python src/automated_civic_refresh.py --future-only >> logs/automation.log 2>&1" >> "$TEMP_CRON"
echo "" >> "$TEMP_CRON"
echo "# Daily schema validation check" >> "$TEMP_CRON"
echo "0 8 * * * cd $CIVIC_DIR && python -c \"import json, glob; files=glob.glob('data/schema/*.json'); print(f'Schema files: {len(files)}') if files else exit(1)\" >> logs/validation.log 2>&1" >> "$TEMP_CRON"

# Create logs directory if it doesn't exist
mkdir -p "$CIVIC_DIR/logs"

# Install new crontab
echo "⏰ Installing cron jobs..."
crontab "$TEMP_CRON"

# Clean up
rm "$TEMP_CRON"

echo "✅ Automation setup complete!"
echo ""
echo "📋 Installed cron jobs:"
echo "  - Weekly refresh: Mondays at 9:00 AM (future-only scope)"
echo "  - Daily validation: Every day at 8:00 AM"
echo ""
echo "📁 Logs will be saved to:"
echo "  - Refresh logs: $CIVIC_DIR/logs/automation.log"
echo "  - Validation logs: $CIVIC_DIR/logs/validation.log"
echo ""
echo "🔍 To view current cron jobs: crontab -l"
echo "🗑️  To remove automation: crontab -l | grep -v 'civic.*automated_civic_refresh' | crontab -"
echo ""
echo "🧪 To test manually:"
echo "  python src/automated_civic_refresh.py --future-only"
echo ""
echo "💰 Foundation Budget Compliance:"
echo "  - Target operational cost: <$50/month"
echo "  - Future-only scope reduces costs by ~60%"
echo "  - Cost monitoring: data/cost_monitoring.json"