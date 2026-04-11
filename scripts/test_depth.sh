#!/bin/bash
# test_depth.sh — Phase 2: Mutation baselines + pre-existing test audit
#
# Two modes:
#   mutate   — Run mutmut on priority targets, improve tests until threshold met
#   audit    — Run mutation critic against pre-existing test files, fix anti-patterns
#
# Usage:
#   caffeinate ./scripts/test_depth.sh mutate          # Mutation baselines (P1-P4)
#   caffeinate ./scripts/test_depth.sh audit            # Audit pre-existing tests
#   caffeinate ./scripts/test_depth.sh audit civicos    # Audit one package
#   caffeinate ./scripts/test_depth.sh all              # Both (overnight)

set -euo pipefail
cd "$(dirname "$0")/.."

DATE=$(date +%Y-%m-%d)
OUTDIR="results/test_depth/$DATE"
mkdir -p "$OUTDIR"

MODE="${1:-all}"
TARGET_PKG="${2:-all}"

# ---------------------------------------------------------------------------
# Mutation baseline targets (from mutation-testing-workflow.md triage plan)
# ---------------------------------------------------------------------------
# Format: source_path|test_dir|target_score|priority_label
MUTATION_TARGETS="
packages/civicos-relay/src/civicos_relay/voice/crypto.py|packages/civicos-relay/tests|90|P1-security
packages/civicos-relay/src/civicos_relay/server/acceptance.py|packages/civicos-relay/tests|90|P1-security
packages/civicos-services/src/civicos_services/servers/middleware.py|packages/civicos-services/tests|90|P1-security
packages/civicos-services/src/civicos_services/query/verbs.py|packages/civicos-services/tests|80|P2-query
packages/civicos/src/civicos/_internal/search/unified.py|packages/civicos/tests|80|P2-query
packages/civicos/src/civicos/_internal/elections/cycles.py|packages/civicos/tests|80|P4-elections
packages/civicos/src/civicos/_internal/elections/deadlines.py|packages/civicos/tests|80|P4-elections
"

mutate_prompt() {
    local source_file="$1"
    local test_dir="$2"
    local target_score="$3"
    local label="$4"

    cat <<PROMPT
You are improving test quality for a CivicOS module to meet its mutation testing target.

## Context
- Source: \`$source_file\`
- Test directory: \`$test_dir\`
- Target mutation score: **${target_score}%**
- Priority: $label (from docs/internal/mutation-testing-workflow.md triage plan)

## Instructions
1. Read \`$source_file\` to understand the module.
2. Find existing test files that cover this module (grep for imports in \`$test_dir\`).
3. Read \`docs/internal/mutation-testing-workflow.md\` for context on mutation testing.
4. Read \`.critics/mutation.critic.md\` for test quality standards.
5. Run the current mutation baseline:
   \`\`\`
   cd packages/\$(echo "$source_file" | cut -d/ -f2)
   # Temporarily set paths_to_mutate in pyproject.toml if needed
   source ../../civicos-env/bin/activate
   mutmut run --paths-to-mutate=\$(echo "$source_file" | sed 's|packages/[^/]*/||')
   mutmut results
   \`\`\`
6. If the score is below ${target_score}%:
   a. Run \`mutmut show <id>\` on surviving mutants to understand what's not caught
   b. Add or strengthen tests to kill surviving mutants
   c. Re-run mutmut to verify improvement
   d. Repeat until score >= ${target_score}% or you've made 3 improvement passes
7. Report: module name, starting score, ending score, number of tests added/modified.

## Rules
- Improve **tests**, not source code (per the agentic workflow)
- Exception: remove genuinely dead code revealed by survivors
- Follow all 7 anti-patterns from mutation.critic.md
- Stage changed test files with git add
PROMPT
}

audit_prompt() {
    local test_file="$1"
    local pkg_src="$2"

    cat <<PROMPT
You are auditing a pre-existing test file against CivicOS test quality standards.

## Task
Audit \`$test_file\` against the 7 anti-patterns in \`.critics/mutation.critic.md\`.

## Instructions
1. Read \`.critics/mutation.critic.md\` for the 7 checks.
2. Read \`$test_file\` — examine every test function.
3. Look at the source files it imports from \`$pkg_src\` to understand what's being tested.
4. For each test function, check:
   - Mock-the-subject? (mocking the class/function under test)
   - Call-only assertions? (only mock.assert_called_* without value checks)
   - Existence-only assertions? (only \`is not None\`, \`isinstance\`, \`in\`)
   - Swallow-all exceptions? (\`except Exception: pass\`)
   - Accept-any-outcome? (assertions that always pass)
   - No assertions? (test with zero assert statements)
   - Mock-to-assert ratio >50%?
5. If ANY anti-pattern is found:
   - Fix the specific failing tests in-place
   - Run the tests to confirm they still pass:
     \`source civicos-env/bin/activate && pytest $test_file -q --override-ini="addopts="\`
   - Report what you fixed
6. If all tests pass, report PASS.

Output: Start with VERDICT: PASS or VERDICT: FIXED, then details.
Do NOT rewrite the entire file. Only fix the specific anti-pattern violations.
Stage changes with git add if you made edits.
PROMPT
}

# ---------------------------------------------------------------------------
# Mode: mutate — mutation baselines on priority targets
# ---------------------------------------------------------------------------
run_mutate() {
    echo "=== Mutation Baselines ==="
    echo ""

    local total=0
    local completed=0

    echo "$MUTATION_TARGETS" | grep -v '^$' | while IFS='|' read -r source test_dir target label; do
        total=$((total + 1))

        if [ ! -f "$source" ]; then
            echo "  ⚠ Skipping $label: $source not found"
            continue
        fi

        echo "  [$total] $label: $source (target: ${target}%)"
        safe_name=$(echo "$source" | tr '/' '_')
        log="$OUTDIR/mutate_${safe_name}.log"

        if claude -p "$(mutate_prompt "$source" "$test_dir" "$target" "$label")" \
            --output-format text \
            --allowedTools "Edit,Write,Read,Bash,Glob,Grep" \
            > "$log" 2>&1; then
            echo "       ✓ Done (see $log)"
            completed=$((completed + 1))
        else
            echo "       ✗ Failed (see $log)"
        fi

        sleep 2
    done

    echo ""
    echo "  Mutation baselines complete: $completed modules"
}

# ---------------------------------------------------------------------------
# Mode: audit — critic audit of pre-existing test files
# ---------------------------------------------------------------------------
run_audit() {
    echo "=== Pre-existing Test Audit ==="
    echo ""

    local total=0
    local fixed=0
    local passed=0

    # Package source dirs for context
    pkg_src_for() {
        case "$1" in
            packages/civicos/*)            echo "packages/civicos/src/civicos" ;;
            packages/civicos-extraction/*) echo "packages/civicos-extraction/src/civicos_extraction" ;;
            packages/civicos-services/*)   echo "packages/civicos-services/src/civicos_services" ;;
            packages/civicos-relay/*)      echo "packages/civicos-relay/src/civicos_relay" ;;
        esac
    }

    # Find test files created BEFORE the overhaul (before April 9)
    for pkg in civicos civicos-extraction civicos-services civicos-relay; do
        if [ "$TARGET_PKG" != "all" ] && [ "$TARGET_PKG" != "$pkg" ]; then
            continue
        fi

        test_dir="packages/$pkg/tests"
        if [ ! -d "$test_dir" ]; then continue; fi

        echo "--- $pkg ---"

        # Get test files that existed before the overhaul script
        find "$test_dir" -name 'test_*.py' ! -newer scripts/test_overhaul.sh -print | sort | while read -r test_file; do
            total=$((total + 1))
            pkg_src=$(pkg_src_for "$test_file")
            safe_name=$(echo "$test_file" | tr '/' '_')
            log="$OUTDIR/audit_${safe_name}.log"

            echo "  [$total] $test_file"

            if claude -p "$(audit_prompt "$test_file" "$pkg_src")" \
                --output-format text \
                --allowedTools "Edit,Write,Read,Bash,Glob,Grep" \
                > "$log" 2>&1; then
                if head -5 "$log" | grep -q "VERDICT: PASS"; then
                    echo "       ✓ PASS"
                    passed=$((passed + 1))
                else
                    echo "       ⚠ FIXED (see $log)"
                    fixed=$((fixed + 1))
                fi
            else
                echo "       ✗ Failed (see $log)"
            fi

            sleep 2
        done
    done

    echo ""
    echo "  Audit complete: $passed passed, $fixed fixed"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "=== CivicOS Test Depth Pipeline ==="
echo "Date: $DATE"
echo "Mode: $MODE"
echo "Output: $OUTDIR"
echo ""

case "$MODE" in
    mutate)
        run_mutate
        ;;
    audit)
        run_audit
        ;;
    all)
        run_mutate
        echo ""
        run_audit
        ;;
    *)
        echo "Usage: $0 [mutate|audit|all] [package]"
        exit 1
        ;;
esac

echo ""
echo "=== Done ==="
echo "Output: $OUTDIR/"
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff --stat"
echo "  2. Run tests: pytest packages/*/tests/ -q --override-ini='addopts='"
echo "  3. Commit: git add -A packages/*/tests/ && git commit"
