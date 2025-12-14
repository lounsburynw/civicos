#!/bin/bash
#
# Quarterly Legislative Context Refresh
#
# This script runs quarterly to verify legislative context freshness
# and flag issues that need human review.
#
# Setup:
#   1. Make executable: chmod +x scripts/quarterly_legislative_refresh.sh
#   2. Add to crontab: crontab -e
#   3. Add line: 0 9 1 1,4,7,10 * /path/to/civic/scripts/quarterly_legislative_refresh.sh
#      (Runs at 9am on Jan 1, Apr 1, Jul 1, Oct 1)
#
# OR use launchd on macOS:
#   See setup instructions at bottom of this file
#

set -e  # Exit on error

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/legislative_verification_$(date +%Y%m%d_%H%M%S).log"
REPORT_FILE="$PROJECT_ROOT/data/legislative_context/quarterly_verification_$(date +%Y%m%d).json"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Quarterly Legislative Context Verification"
log "=========================================="

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/civic-env" ]; then
    log "Activating virtual environment..."
    source "$PROJECT_ROOT/civic-env/bin/activate"
fi

# Run verification script
log "Running verification checks..."
cd "$PROJECT_ROOT"

if python3 scripts/quarterly_legislative_verification.py --json > "$REPORT_FILE" 2>&1; then
    log "✅ Verification passed - no critical issues found"
    exit 0
else
    log "⚠️  Verification found issues - see $REPORT_FILE"

    # Extract summary from JSON
    ISSUES=$(jq -r '.total_issues' "$REPORT_FILE" 2>/dev/null || echo "unknown")
    WARNINGS=$(jq -r '.total_warnings' "$REPORT_FILE" 2>/dev/null || echo "unknown")

    log "Issues: $ISSUES, Warnings: $WARNINGS"
    log ""
    log "ACTION REQUIRED: Review verification report and update legislative context"
    log "Report: $REPORT_FILE"
    log "Log: $LOG_FILE"

    # Send notification (optional - requires mailutils or similar)
    # echo "Legislative context verification found $ISSUES issues. See $REPORT_FILE" | \
    #     mail -s "Civic Platform: Quarterly Legislative Verification" admin@example.com

    exit 1
fi

# =============================================================================
# macOS launchd Setup Instructions
# =============================================================================
#
# 1. Create plist file at: ~/Library/LaunchAgents/com.civic.legislative-refresh.plist
#
# <?xml version="1.0" encoding="UTF-8"?>
# <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
# <plist version="1.0">
# <dict>
#     <key>Label</key>
#     <string>com.civic.legislative-refresh</string>
#
#     <key>ProgramArguments</key>
#     <array>
#         <string>/Users/YOUR_USERNAME/projects/civic/scripts/quarterly_legislative_refresh.sh</string>
#     </array>
#
#     <key>StartCalendarInterval</key>
#     <array>
#         <dict>
#             <key>Month</key>
#             <integer>1</integer>
#             <key>Day</key>
#             <integer>1</integer>
#             <key>Hour</key>
#             <integer>9</integer>
#             <key>Minute</key>
#             <integer>0</integer>
#         </dict>
#         <dict>
#             <key>Month</key>
#             <integer>4</integer>
#             <key>Day</key>
#             <integer>1</integer>
#             <key>Hour</key>
#             <integer>9</integer>
#             <key>Minute</key>
#             <integer>0</integer>
#         </dict>
#         <dict>
#             <key>Month</key>
#             <integer>7</integer>
#             <key>Day</key>
#             <integer>1</integer>
#             <key>Hour</key>
#             <integer>9</integer>
#             <key>Minute</key>
#             <integer>0</integer>
#         </dict>
#         <dict>
#             <key>Month</key>
#             <integer>10</integer>
#             <key>Day</key>
#             <integer>1</integer>
#             <key>Hour</key>
#             <integer>9</integer>
#             <key>Minute</key>
#             <integer>0</integer>
#         </dict>
#     </array>
#
#     <key>StandardOutPath</key>
#     <string>/Users/YOUR_USERNAME/projects/civic/logs/legislative-refresh.log</string>
#
#     <key>StandardErrorPath</key>
#     <string>/Users/YOUR_USERNAME/projects/civic/logs/legislative-refresh.err</string>
# </dict>
# </plist>
#
# 2. Load the plist:
#    launchctl load ~/Library/LaunchAgents/com.civic.legislative-refresh.plist
#
# 3. Verify it's loaded:
#    launchctl list | grep civic
#
# 4. Test manually:
#    launchctl start com.civic.legislative-refresh
#
# 5. Check logs:
#    tail -f ~/projects/civic/logs/legislative-refresh.log
#
# =============================================================================
