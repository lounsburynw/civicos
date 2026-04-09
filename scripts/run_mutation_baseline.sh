#!/bin/bash
# Run mutation testing baseline for a specific source file + test file pair.
# Usage: ./scripts/run_mutation_baseline.sh <source_path> <test_path>
#
# Example:
#   ./scripts/run_mutation_baseline.sh src/civicos/_internal/elections/cycles.py tests/test_election_calendar.py

set -e

SOURCE="$1"
TESTS="$2"

if [ -z "$SOURCE" ] || [ -z "$TESTS" ]; then
    echo "Usage: $0 <source_path_relative_to_packages/civicos> <test_path_relative_to_packages/civicos>"
    exit 1
fi

cd "$(dirname "$0")/../packages/civicos"
PYPROJECT="pyproject.toml"
MUTMUT="../../civicos-env/bin/mutmut"

# Save original config
cp "$PYPROJECT" "${PYPROJECT}.bak"

# Swap paths_to_mutate and tests_dir
python3 -c "
import re, sys
with open('$PYPROJECT', 'r') as f:
    content = f.read()
content = re.sub(r'paths_to_mutate = \[.*?\]', 'paths_to_mutate = [\"$SOURCE\"]', content)
content = re.sub(r'tests_dir = \[.*?\]', 'tests_dir = [\"$TESTS\"]', content)
with open('$PYPROJECT', 'w') as f:
    f.write(content)
"

# Clean and run
rm -rf mutants .mutmut-cache
echo "=== Mutating $SOURCE (tests: $TESTS) ==="
$MUTMUT run 2>&1 | tail -5

echo ""
echo "=== Results ==="
$MUTMUT results 2>&1 | head -30

# Count
KILLED=$($MUTMUT results 2>&1 | grep -c "killed" || echo 0)
SURVIVED=$($MUTMUT results 2>&1 | grep -c "survived" || echo 0)
TOTAL=$((KILLED + SURVIVED))
if [ "$TOTAL" -gt 0 ]; then
    SCORE=$((KILLED * 100 / TOTAL))
    echo ""
    echo "=== Score: $SCORE% ($KILLED killed, $SURVIVED survived out of $TOTAL) ==="
fi

# Restore
mv "${PYPROJECT}.bak" "$PYPROJECT"
rm -rf mutants .mutmut-cache
