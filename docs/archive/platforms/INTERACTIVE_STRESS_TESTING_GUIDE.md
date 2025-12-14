# Interactive Stress Testing Guide

**For Solo Developers Validating Agentic-Created Code**

This guide helps developers interactively validate and stress test recent changes to the civic engagement platform, particularly useful when returning to code created by AI agents or other team members.

## Pre-Testing Setup

### 1. Environment Validation
```bash
# Check git status to understand what changed
git status
git diff HEAD --name-only

# Verify environment setup
echo $OPENAI_API_KEY  # Should be set
echo $CIVIC_WEB_KEY   # Should be 'dev_key_local' for testing

# Check Python dependencies
python -c "import sqlite3, smtplib, requests, json" # Should not error
```

### 2. Baseline Health Check
```bash
# Verify core automation still works
python src/automated_civic_refresh.py --future-only

# Expected: 4 jurisdictions processed, cost ~$0.38-0.50
# Red flag: Import errors, >$2.00 cost, timeout failures
```

## Interactive Testing Progression

### Level 1: Core System Validation

#### Test 1.1: Multi-Jurisdiction Automation
```bash
# Test regional scale automation
python src/automated_civic_refresh.py --future-only

# What to verify:
# ✅ Processes: san_rafael, berkeley, marin_county, santa_rosa
# ✅ Total cost: <$1.00 per run
# ✅ No Python exceptions
# ✅ Creates/updates data/cost_monitoring.json

# Interactive validation:
cat data/cost_monitoring.json | tail -10
# Should show recent entries for all 4 jurisdictions
```

#### Test 1.2: Cost Monitoring System
```bash
# Check cost accumulation over multiple runs
for i in {1..3}; do
  echo "=== Run $i ==="
  python src/automated_civic_refresh.py --future-only
  python -c "
import json
with open('data/cost_monitoring.json') as f:
    data = json.load(f)
total_cost = sum(entry['estimated_cost'] for entry in data if '2025-09-20' in entry['timestamp'])
print(f'Total cost today: \${total_cost:.2f}')
  "
  sleep 10
done

# Expected: Incremental cost growth, total <$5.00 for 12 jurisdiction calls
```

### Level 2: New Components Testing

#### Test 2.1: Monitoring Dashboard
```bash
# Start with safe text report
python src/monitoring_dashboard.py --report

# Verify output contains:
# - "SYSTEM HEALTH OVERVIEW"
# - Budget usage percentage
# - All 4 jurisdictions listed
# - Foundation compliance status

# Test web dashboard (if text report works)
python src/monitoring_dashboard.py --web --port 8003 &
DASHBOARD_PID=$!

# Open http://localhost:8003 in browser
# Interactive checks:
# ✅ Page loads without errors
# ✅ Metrics update every 30 seconds
# ✅ Jurisdiction status shows current data
# ✅ Budget usage displays correctly

# Cleanup
kill $DASHBOARD_PID
```

#### Test 2.2: Civic Participation Metrics
```bash
# Test database creation and metrics
python src/civic_participation_metrics.py --demo-data

# Verify database created
ls -la data/civic_participation.db

# Test metrics generation
python src/civic_participation_metrics.py --foundation-summary

# Expected output format:
# Total Cost: $X.XX
# Civic Actions: N
# Cost per Action: $X.XX
# Retention Rate: XX.X%

# Validate database structure
sqlite3 data/civic_participation.db "
SELECT name FROM sqlite_master WHERE type='table';
"
# Should show: civic_actions, engagement_sessions, user_profiles, community_connections, foundation_reports
```

### Level 3: Stress Testing & Edge Cases

#### Test 3.1: Error Handling Validation
```bash
# Test with invalid jurisdiction temporarily
# Backup current config
cp src/automated_civic_refresh.py src/automated_civic_refresh.py.bak

# Add invalid URL to test error handling
python -c "
import re
with open('src/automated_civic_refresh.py', 'r') as f:
    content = f.read()
# Add invalid URL to San Rafael config
modified = re.sub(
    r'(\"https://www\.cityofsanrafael\.org/meetings\")',
    r'\1,\n            \"https://invalid-test-url.fake\"',
    content
)
with open('src/automated_civic_refresh.py', 'w') as f:
    f.write(modified)
"

# Test error handling
python src/automated_civic_refresh.py --future-only

# Verify:
# ✅ Script completes despite invalid URL
# ✅ Error logged in data/system_failures.json
# ✅ Other jurisdictions still process successfully

# Restore original
mv src/automated_civic_refresh.py.bak src/automated_civic_refresh.py

# Check error log
cat data/system_failures.json | tail -5
```

#### Test 3.2: Load Testing Regional Scale
```bash
# Simulate high-frequency usage
echo "Starting load test..."
start_time=$(date +%s)

for i in {1..5}; do
  echo "Load test iteration $i/5"
  timeout 120 python src/automated_civic_refresh.py --future-only
  if [ $? -eq 124 ]; then
    echo "⚠️  Timeout on iteration $i"
  fi
done

end_time=$(date +%s)
duration=$((end_time - start_time))
echo "Load test completed in ${duration} seconds"

# Analyze cost impact
python -c "
import json
from datetime import datetime, timedelta

with open('data/cost_monitoring.json') as f:
    data = json.load(f)

recent = [
    entry for entry in data
    if datetime.fromisoformat(entry['timestamp']) > datetime.now() - timedelta(minutes=30)
]

total_cost = sum(entry['estimated_cost'] for entry in recent)
print(f'Load test cost: \${total_cost:.2f}')
print(f'Entries created: {len(recent)}')

if total_cost > 5.0:
    print('⚠️  High cost detected')
else:
    print('✅ Cost within acceptable range')
"
```

### Level 4: Integration Testing

#### Test 4.1: End-to-End API Integration
```bash
# Start API server for integration testing
python src/civic_api_integrated.py &
API_PID=$!
sleep 5

# Test API endpoints
curl -H "Authorization: Bearer dev_key_local" \
     http://localhost:8001/api/health

# Test conversation endpoint
curl -X POST \
     -H "Authorization: Bearer dev_key_local" \
     -H "Content-Type: application/json" \
     -d '{"message": "What meetings are happening this week?", "city": "San Rafael"}' \
     http://localhost:8001/api/conversation

# Cleanup
kill $API_PID
```

#### Test 4.2: Comprehensive Test Suite
```bash
# Run automated test suites
echo "Running Phase 2 tests..."
python tests/test_phase2_automation.py

echo -e "\nRunning Phase 3 tests..."
python tests/test_phase3_regional_scaling.py

# Expected results:
# Phase 2: 6/6 tests passed
# Phase 3: 5/6 tests passed (civic_participation_metrics may fail in clean environment)
```

## Stress Testing Scenarios

### Scenario 1: Network Resilience
```bash
# Test behavior during network issues
# 1. Start automation
python src/automated_civic_refresh.py --future-only &
AUTOMATION_PID=$!

# 2. Simulate network issues (if on macOS/Linux)
# sudo ifconfig en0 down
# sleep 30
# sudo ifconfig en0 up

# 3. Check if automation recovered
wait $AUTOMATION_PID
echo "Exit code: $?"

# 4. Verify graceful degradation
ls data/schema/ | tail -5  # Should show cached data usage
```

### Scenario 2: Concurrent Access
```bash
# Test concurrent automation runs
python src/automated_civic_refresh.py --future-only &
python src/monitoring_dashboard.py --report &
python src/civic_participation_metrics.py --foundation-summary &

wait

# Verify no database locks or file conflicts
echo "All processes completed successfully"
```

## Red Flags & Troubleshooting

### Critical Issues (Stop Testing)
- **Import errors**: Missing dependencies, broken installs
- **Cost explosion**: >$10 in cost_monitoring.json
- **Database corruption**: SQLite errors, missing tables
- **API timeouts**: Consistent >300 second responses

### Warning Signs (Investigate)
- **Gradual cost increase**: >$0.15 per jurisdiction per run
- **Memory growth**: Python processes >1GB RAM
- **Slow responses**: Individual jurisdiction processing >60 seconds
- **Missing data**: Empty data/schema/ directory after runs

### Quick Fixes
```bash
# Reset cost monitoring if corrupted
mv data/cost_monitoring.json data/cost_monitoring.json.bak
echo "[]" > data/cost_monitoring.json

# Reset civic participation database
rm -f data/civic_participation.db

# Clear temporary files
rm -f data/system_failures.json data/alert_log.json
```

## Validation Checklist

### ✅ Core Functionality
- [ ] Multi-jurisdiction automation completes successfully
- [ ] Cost remains <5% of $50 foundation budget
- [ ] All 4 jurisdictions process without errors
- [ ] Schema data generated in data/schema/

### ✅ New Features (Phase 3)
- [ ] Monitoring dashboard generates reports
- [ ] Web dashboard loads and updates
- [ ] Civic participation database creates successfully
- [ ] Foundation metrics calculate correctly

### ✅ Production Readiness
- [ ] Error handling prevents crashes
- [ ] Graceful degradation works with cached data
- [ ] Cost monitoring alerts at appropriate thresholds
- [ ] Test suites pass 5/6 or better

### ✅ Regional Scale
- [ ] 4+ jurisdictions operational
- [ ] Cost scales linearly with jurisdiction count
- [ ] Performance acceptable across regions
- [ ] Foundation reporting functional

## Emergency Rollback

If critical issues discovered:
```bash
# Use safety nets from CLAUDE.md
git checkout v0.9-engagement-strategy          # Git tag recovery
git checkout pre-reorganization-stable         # Named branch recovery

# Or hard reset if needed
git reset --hard pre-reorganization-stable
```

## Integration with Existing Testing

This guide complements:
- `docs/FRONTEND_TESTING_GUIDE.md` - Frontend-specific testing
- `tests/test_phase2_automation.py` - Automated Phase 2 validation
- `tests/test_phase3_regional_scaling.py` - Automated Phase 3 validation
- `docs/PHASE_3_DEPLOYMENT_GUIDE.md` - Production deployment procedures

Use this guide for **interactive validation** after code changes, especially when returning to agentic-created code or validating new regional scaling features.