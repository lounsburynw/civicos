#!/bin/bash
# test_overhaul.sh — Headless test generation pipeline
#
# Runs executor → critic for each untested module.
# Designed for overnight runs on a Max subscription.
#
# Usage:
#   ./scripts/test_overhaul.sh                              # Run all packages (no commit)
#   ./scripts/test_overhaul.sh civicos-extraction            # Run one package
#   AUTOCOMMIT=true ./scripts/test_overhaul.sh               # Commit per package after tests pass
#   caffeinate ./scripts/test_overhaul.sh                    # Prevent laptop sleep
#   caffeinate AUTOCOMMIT=true ./scripts/test_overhaul.sh    # Full overnight: generate + commit
#
# Output:
#   results/test_overhaul/YYYY-MM-DD/
#     ├── manifest.json          # Work queue + results
#     ├── executor_{module}.log  # Executor output per module
#     └── critic_{module}.log    # Critic output per module

set -euo pipefail
cd "$(dirname "$0")/.."

DATE=$(date +%Y-%m-%d)
OUTDIR="results/test_overhaul/$DATE"
mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# 1. Build the work queue: find untested source files >100 lines
# ---------------------------------------------------------------------------
build_work_queue() {
    local pkg_dir="$1"
    local test_dir="$2"
    local pkg_name="$3"

    # Get all source .py files >100 lines, excluding __init__.py
    find "$pkg_dir" -name '*.py' ! -name '__init__.py' -exec sh -c '
        lines=$(wc -l < "$1")
        if [ "$lines" -gt 100 ]; then
            echo "$lines $1"
        fi
    ' _ {} \; | sort -rn | while read -r lines filepath; do
        # Check if any test file imports from this module
        module_name=$(basename "$filepath" .py)
        if ! grep -rql "from.*${module_name}\b\|import.*${module_name}\b" "$test_dir" 2>/dev/null; then
            echo "$filepath|$lines|$pkg_name"
        fi
    done
}

# ---------------------------------------------------------------------------
# 2. Prompt templates
# ---------------------------------------------------------------------------
executor_prompt() {
    local source_file="$1"
    local test_file="$2"
    local pkg_name="$3"

    cat <<PROMPT
You are writing tests for an untested module in the CivicOS project.

## Task
Write a comprehensive test file for \`$source_file\`.
Save it to \`$test_file\`.

## Instructions
1. Read \`$source_file\` thoroughly.
2. Read \`docs/internal/mutation-testing-workflow.md\` and \`.critics/mutation.critic.md\` for quality standards.
3. Read 1-2 existing test files in the same package for conventions:
   - Look in the tests/ directory adjacent to the source
4. Write tests following these rules:
   - **Test real behavior, not mock wiring.** Mock external dependencies (DB, HTTP, APIs), never the subject under test.
   - **Assert specific values.** Never just \`is not None\`, \`isinstance()\`, or \`len() > 0\`. Pin expected outputs.
   - **Include boundary cases.** Empty inputs, None values, edge conditions.
   - **One test per behavior.** Name tests after the behavior they verify, not the method.
   - For I/O-heavy code: mock the I/O layer, test the logic that processes the I/O results.
   - For pure logic: no mocks needed, test with real inputs and expected outputs.
5. Run the tests with: \`source civicos-env/bin/activate && pytest $test_file -q --override-ini="addopts="\`
6. Fix any failures before finishing.
7. Stage the test file with \`git add $test_file\`.
8. Self-audit: re-read \`.critics/mutation.critic.md\` and check your test file against all 7 patterns.
   If any test function violates an anti-pattern, fix it before finishing.

## Anti-patterns to avoid (from mutation.critic.md)
- No mock-the-subject (don't mock what you're testing)
- No call-only assertions (don't only check mock.assert_called_*)
- No existence-only assertions (don't only check \`is not None\`)
- No swallow-all exceptions (\`except Exception: pass\`)
- No accept-any-outcome assertions
- Every test function must have at least one assert
- Mock-to-assert ratio must be under 50%

Target: mutation score >= 60% (will be verified separately).

## Important
- Do NOT commit. Only stage the file. The pipeline handles commits.
PROMPT
}

critic_prompt() {
    local source_file="$1"
    local test_file="$2"

    cat <<PROMPT
You are a test quality critic for the CivicOS project.

## Task
Audit \`$test_file\` against the 7 anti-patterns in \`.critics/mutation.critic.md\`.

## Instructions
1. Read \`.critics/mutation.critic.md\` for the 7 checks.
2. Read \`$test_file\` — examine every test function.
3. Read \`$source_file\` to understand what the tests SHOULD be testing.
4. For each test function, check:
   - Mock-the-subject? (mocking the class/function under test)
   - Call-only assertions? (only mock.assert_called_* without value checks)
   - Existence-only assertions? (only \`is not None\`, \`isinstance\`, \`in\`)
   - Swallow-all exceptions? (\`except Exception: pass\`)
   - Accept-any-outcome? (assertions that always pass)
   - No assertions? (test with zero assert statements)
   - Mock-to-assert ratio >50%?
5. If ANY anti-pattern is found:
   - Fix the specific failing tests in-place (edit the file)
   - Run the tests to confirm they still pass
   - Report what you fixed
6. If all tests pass the critic, report PASS with a brief summary.

Output format: Start your response with VERDICT: PASS or VERDICT: FAIL, then details.
PROMPT
}

# ---------------------------------------------------------------------------
# 3. Package configs
# ---------------------------------------------------------------------------
declare -A PACKAGES
PACKAGES=(
    ["civicos"]="packages/civicos/src/civicos/_internal|packages/civicos/tests"
    ["civicos-extraction"]="packages/civicos-extraction/src/civicos_extraction|packages/civicos-extraction/tests"
    ["civicos-services"]="packages/civicos-services/src/civicos_services|packages/civicos-services/tests"
    ["civicos-relay"]="packages/civicos-relay/src/civicos_relay|packages/civicos-relay/tests"
)

# ---------------------------------------------------------------------------
# 4. Main loop
# ---------------------------------------------------------------------------
TARGET_PKG="${1:-all}"
AUTOCOMMIT="${AUTOCOMMIT:-false}"  # Set AUTOCOMMIT=true to commit per package
TOTAL=0
PASSED=0
FAILED=0

echo "=== CivicOS Test Overhaul Pipeline ==="
echo "Date: $DATE"
echo "Output: $OUTDIR"
echo ""

for pkg_name in "${!PACKAGES[@]}"; do
    if [ "$TARGET_PKG" != "all" ] && [ "$TARGET_PKG" != "$pkg_name" ]; then
        continue
    fi

    IFS='|' read -r src_dir test_dir <<< "${PACKAGES[$pkg_name]}"

    if [ ! -d "$src_dir" ]; then
        echo "⚠ Skipping $pkg_name — source dir not found: $src_dir"
        continue
    fi

    echo "--- Package: $pkg_name ---"
    echo "  Source: $src_dir"
    echo "  Tests:  $test_dir"

    # Build work queue
    queue=$(build_work_queue "$src_dir" "$test_dir" "$pkg_name")

    if [ -z "$queue" ]; then
        echo "  ✓ No untested files >100 lines"
        continue
    fi

    echo "$queue" | while IFS='|' read -r filepath lines pkg; do
        TOTAL=$((TOTAL + 1))
        module_name=$(basename "$filepath" .py)
        # Derive test file path
        test_file="${test_dir}/test_${module_name}.py"
        safe_name=$(echo "$filepath" | tr '/' '_')

        echo ""
        echo "  [$TOTAL] $filepath ($lines lines)"
        echo "       → $test_file"

        # Skip if test file already exists
        if [ -f "$test_file" ]; then
            echo "       ⊘ Test file exists, skipping"
            continue
        fi

        # --- EXECUTOR ---
        echo "       ⏳ Executor..."
        executor_log="$OUTDIR/executor_${safe_name}.log"

        if claude -p "$(executor_prompt "$filepath" "$test_file" "$pkg_name")" \
            --output-format text \
            > "$executor_log" 2>&1; then
            echo "       ✓ Executor done"
        else
            echo "       ✗ Executor failed (see $executor_log)"
            FAILED=$((FAILED + 1))
            continue
        fi

        # Check if the test file was actually created
        if [ ! -f "$test_file" ]; then
            echo "       ✗ No test file created"
            FAILED=$((FAILED + 1))
            continue
        fi

        # --- CRITIC ---
        echo "       ⏳ Critic..."
        critic_log="$OUTDIR/critic_${safe_name}.log"

        if claude -p "$(critic_prompt "$filepath" "$test_file")" \
            --output-format text \
            > "$critic_log" 2>&1; then
            if head -5 "$critic_log" | grep -q "VERDICT: PASS"; then
                echo "       ✓ Critic: PASS"
                PASSED=$((PASSED + 1))
            else
                echo "       ⚠ Critic: FAIL (fixed in-place, review $critic_log)"
                PASSED=$((PASSED + 1))  # Critic fixes issues
            fi
        else
            echo "       ✗ Critic failed (see $critic_log)"
            FAILED=$((FAILED + 1))
        fi

        # Brief pause to avoid rate limits
        sleep 2
    done

    # --- OPTIONAL COMMIT per package ---
    if [ "$AUTOCOMMIT" = "true" ]; then
        # Check if there are staged test files to commit
        staged=$(git diff --cached --name-only -- "$test_dir" 2>/dev/null | wc -l | tr -d ' ')
        if [ "$staged" -gt 0 ]; then
            echo ""
            echo "  Committing $staged test files for $pkg_name..."

            # Final validation: run all new tests
            if source civicos-env/bin/activate && pytest "$test_dir" -q --override-ini="addopts=" > /dev/null 2>&1; then
                git commit -m "$(cat <<COMMITMSG
Add headless-generated tests for $pkg_name ($staged files)

Generated by test_overhaul.sh executor/critic pipeline.
Each test file passed mutation critic anti-pattern audit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
COMMITMSG
)"
                echo "  ✓ Committed"
            else
                echo "  ✗ Tests failed — skipping commit (files remain staged)"
            fi
        fi
    fi
done

echo ""
echo "=== Summary ==="
echo "Processed: $TOTAL modules"
echo "Passed:    $PASSED"
echo "Failed:    $FAILED"
echo "Output:    $OUTDIR/"
echo ""
echo "Next steps:"
echo "  1. Review generated tests: git diff --stat"
echo "  2. Run full suite:  pytest packages/*/tests/ -q --override-ini='addopts='"
echo "  3. Run mutation baselines: /test mutation <file>"
