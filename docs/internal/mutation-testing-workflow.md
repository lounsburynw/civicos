# Mutation Testing Workflow

Design doc for formalizing mutation testing as the quality gate for AI-generated code in CivicOS.

## Premise

When an AI agent writes both implementation and tests, traditional coverage metrics are meaningless. An agent can achieve 100% line coverage with tests that assert nothing useful. The question isn't "was this line executed?" but "if this line were wrong, would the tests catch it?"

Mutation testing answers that question mechanically: mutate the source, run the tests, see if they break. Tests that don't break on mutations are theater.

## How Mutation Testing Works

A mutation testing tool:

1. Parses source code and generates **mutants** — small, systematic changes:
   - Arithmetic: `+` to `-`, `*` to `/`
   - Comparison: `>` to `>=`, `==` to `!=`
   - Boolean: `True` to `False`, `and` to `or`
   - Return values: `return x` to `return None`
   - Statement removal: delete a line entirely
   - Boundary: `0` to `1`, `[]` to `[None]`

2. Runs the test suite against each mutant

3. Classifies results:
   - **Killed** — tests failed (good: they caught the defect)
   - **Survived** — tests still passed (bad: they missed the defect)
   - **Timeout** — tests hung (usually killed, counted as caught)
   - **Incompetent** — mutant caused a syntax/import error (ignored)

4. Reports a **mutation score**: `killed / (killed + survived)`

A mutation score of 80% means "if you randomly broke one line of code, there's an 80% chance your tests would catch it."

## Tooling: mutmut

[mutmut](https://github.com/boxed/mutmut) is the standard Python mutation testing tool. It's lightweight, integrates with pytest, and supports incremental runs (only re-test mutants that previously survived).

### Installation

```bash
pip install mutmut
```

Add to dev dependencies in `packages/civicos/pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "mutmut>=3.0.0",
]
```

### Configuration

Create `packages/civicos/pyproject.toml` section:

```toml
[tool.mutmut]
paths_to_mutate = "src/civicos/"
tests_dir = "tests/"
runner = "python -m pytest -x -q --override-ini='addopts=' --tb=no"
```

Key settings:
- `-x` stops on first failure (fast — we only need to know the mutant was caught)
- `--tb=no` suppresses tracebacks (speed)
- `--override-ini='addopts='` prevents xdist from interfering

### Usage

```bash
# Full run (slow — do this in CI, not locally)
cd packages/civicos && mutmut run

# Scoped to specific module (fast — do this during dev)
mutmut run --paths-to-mutate=src/civicos/query/verbs.py

# View surviving mutants
mutmut results

# Show a specific surviving mutant
mutmut show 42

# HTML report
mutmut html
```

## The Agentic Workflow

This is the core workflow for AI-assisted development with mutation testing as the quality gate.

### Loop

```
 1. TASK        Human defines what to build (spec, issue, verbal)
 2. IMPLEMENT   AI writes implementation
 3. TEST        AI writes tests
 4. MUTATE      mutmut runs on changed source files
 5. EVALUATE    Check mutation score
                  >= threshold → proceed to step 6
                  < threshold  → AI rewrites tests (back to step 3)
 6. REVIEW      Human reviews TESTS (the spec), not the implementation
 7. COMMIT      Tests are the proof; implementation is the artifact
```

### Why the human reviews tests, not code

The implementation is a function of the tests. If the tests are:
- **Correct** — they specify the right behavior
- **Strong** — mutation testing proves they catch defects
- **Complete** — they cover the important cases

...then the implementation is trustworthy by construction. The human's job is to verify intent ("do these tests describe what I actually want?"), not mechanics ("is this loop off by one?").

### What the AI must NOT do

When mutation score is below threshold, the AI must improve **tests**, not **code**. The temptation is to simplify the implementation to make it easier to test. That's backwards — the implementation should be whatever solves the problem; the tests should be strong enough to validate it.

Exception: if a surviving mutant reveals genuinely dead code or an unreachable branch, removing it from the implementation is correct.

## Integration with Existing Infrastructure

### Relationship to coverage

Coverage (`pytest-cov`) and mutation testing are complementary:

| Metric | Answers | Weakness |
|--------|---------|----------|
| Line coverage | "Was this code executed during tests?" | Executed != validated |
| Branch coverage | "Were both sides of conditions tested?" | Both sides can pass with weak assertions |
| Mutation score | "Would tests catch a defect here?" | Slower, doesn't tell you what's missing |

Keep coverage. Add mutation testing on top. A line with 100% coverage but 0% mutation score is the exact line to worry about.

### Relationship to critics

Critics (`.critics/`) catch **architectural** issues — wrong abstraction layer, missing storage call, protocol violation. Mutation testing catches **behavioral** issues — wrong comparison, off-by-one, missing validation. They don't overlap.

| Tool | Catches | Misses |
|------|---------|--------|
| Critics | Structural/architectural defects | Logic bugs within correct structure |
| Mutation testing | Logic bugs, weak tests | Architectural violations |
| Both together | Full spectrum | Nothing critical |

### New critic: mutation.critic.md

Add a critic that flags test anti-patterns at review time (before mutation testing even runs):

**Flags as FAIL:**
- Test function with zero `assert` statements
- Test that only calls `assert_called_once()` / `assert_called_with()` without also asserting return values or side effects
- Test that mocks the module under test (mocking what you're testing)
- Test with `except Exception: pass` or similar swallow patterns
- Test that asserts only `is not None` or `isinstance()` on a return value

**Flags as WARNING:**
- Test file where >50% of assertions are mock call assertions
- Test with no value-specific assertions (only existence/type checks)
- Test that uses `assertIn` on a list of all possible values (always passes)

This is cheaper than running mutmut and catches the most egregious issues immediately.

### CI integration

Add a mutation testing job to `.github/workflows/tests.yml`:

```yaml
mutation:
  name: Mutation Testing
  runs-on: ubuntu-latest
  needs: [unit]  # Only run if unit tests pass
  if: github.event_name == 'pull_request'  # PRs only, not every push
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.12"

    - name: Install dependencies
      run: |
        pip install -e packages/civicos[dev]
        pip install mutmut

    - name: Identify changed source files
      id: changed
      run: |
        FILES=$(git diff --name-only origin/main...HEAD \
          | grep '^packages/civicos/src/' \
          | grep '\.py$' \
          | grep -v '__pycache__' \
          | tr '\n' ',')
        echo "files=$FILES" >> $GITHUB_OUTPUT

    - name: Run mutation tests on changed files
      if: steps.changed.outputs.files != ''
      run: |
        cd packages/civicos
        for file in $(echo "${{ steps.changed.outputs.files }}" | tr ',' '\n'); do
          # Convert to relative path from packages/civicos/
          rel=$(echo "$file" | sed 's|packages/civicos/||')
          echo "::group::Mutating $rel"
          mutmut run --paths-to-mutate="$rel" || true
          echo "::endgroup::"
        done
        mutmut results | tee mutation-report.txt

    - name: Check mutation score
      run: |
        cd packages/civicos
        # Parse killed/survived from mutmut results
        KILLED=$(mutmut results 2>/dev/null | grep -c "Killed" || echo 0)
        SURVIVED=$(mutmut results 2>/dev/null | grep -c "Survived" || echo 0)
        TOTAL=$((KILLED + SURVIVED))
        if [ "$TOTAL" -gt 0 ]; then
          SCORE=$((KILLED * 100 / TOTAL))
          echo "Mutation score: $SCORE% ($KILLED killed, $SURVIVED survived)"
          if [ "$SCORE" -lt "$THRESHOLD" ]; then
            echo "::warning::Mutation score $SCORE% is below threshold $THRESHOLD%"
          fi
        fi
      env:
        THRESHOLD: 60  # Start low, raise over time

    - name: Upload mutation report
      uses: actions/upload-artifact@v4
      with:
        name: mutation-report
        path: packages/civicos/mutation-report.txt
```

**Phase-in strategy for CI:**

| Phase | Gate | Threshold | Timeline |
|-------|------|-----------|----------|
| 1. Reporting | Warning only | — | Immediate |
| 2. Soft gate | Warning on PR, comment with surviving mutants | 50% | After baseline |
| 3. Hard gate | Block merge below threshold | 70% | After triage |

### /test integration

Extend the `/test` slash command to support mutation mode:

```bash
/test mutation                    # Run mutmut on staged changes
/test mutation verbs.py           # Run mutmut on specific file
```

## Triage Plan for Existing Tests

The audit found ~74% of tests are theater (mock-heavy, trivial assertions, manual scripts). Fixing all of them at once is impractical. Triage by value.

### Priority 1: Security-critical paths

**Source modules:**
- `civicos_relay/voice/crypto.py`
- `civicos_relay/acceptance/`
- `civicos_services/servers/middleware.py`

**Why first:** Bugs here are exploits. Existing crypto tests are strong (known test vectors), but verification integration paths may have surviving mutants.

**Target mutation score:** 90%+

### Priority 2: Query layer (user-facing)

**Source modules:**
- `civicos_services/query/verbs.py`
- `civicos_services/query/adapters/`
- `civicos/search.py`

**Why second:** This is what users interact with. Wrong query results erode trust.

**Target mutation score:** 80%+

### Priority 3: Storage protocols

**Source modules:**
- `civicos/storage/postgres.py`
- `civicos/storage/sqlite.py`
- `civicos/vectors/`

**Why third:** Data integrity. Existing protocol conformance tests are decent but may have surviving mutants in edge cases.

**Target mutation score:** 75%+

### Priority 4: Everything else

**Source modules:** Extraction clients, config, diagnostics

**Target mutation score:** 60%+

### What to do with theater tests

| Theater Type | Action |
|-------------|--------|
| Mock-only assertions | Add real output assertions alongside mock assertions, or replace entirely |
| Trivial (existence/type checks) | Add specific value assertions for known inputs |
| Manual scripts | Convert to pytest or delete (they aren't running in CI anyway) |
| Catch-all exception handlers | Replace with specific exception types |
| Tests that accept any output | Pin expected outputs for known inputs |

**Do not delete tests without replacing them.** Even weak tests occasionally catch something. Strengthen first, then remove the mock scaffolding once real assertions exist.

## Metrics and Tracking

### What to track

| Metric | Where | Frequency |
|--------|-------|-----------|
| Mutation score per module | CI artifact | Every PR |
| Surviving mutant count | CI artifact | Every PR |
| Mutation score trend | Monthly snapshot in `claude-progress.txt` | Monthly |

### Healthy vs. unhealthy signals

| Signal | Healthy | Unhealthy |
|--------|---------|-----------|
| Mutation score trending up | Tests getting stronger | — |
| Mutation score trending down | — | New code with weak tests |
| Many surviving mutants in one file | — | File needs test attention |
| Score > 80% with low coverage | Tests are precise but narrow | Need more test cases |
| Score < 50% with high coverage | — | Classic coverage theater |

## Scope Boundaries

### What to mutate

- `packages/civicos/src/civicos/` — core library
- `packages/civicos-services/src/civicos_services/query/` — query layer
- `packages/civicos-relay/src/civicos_relay/voice/` — trust-critical paths

### What NOT to mutate

- Test files themselves (mutmut won't, but be explicit)
- Generated code, migration scripts
- Configuration/YAML parsing (better served by integration tests)
- Third-party wrappers with no logic (thin API clients)
- `__init__.py` files (usually just imports)

### Performance budget

mutmut is slow. A full run on `packages/civicos/src/civicos/` could take 30-60 minutes depending on test suite speed and number of mutants.

Mitigations:
- **Scope to changed files** in CI (see workflow above)
- **Use `-x` flag** in test runner (stop on first failure per mutant)
- **Cache results** — mutmut stores state in `.mutmut-cache/`, survives across runs
- **Skip slow-marked tests** — add to runner args: `-m "not slow"`
- **Run locally only on targeted modules** — never full-suite locally

## Appendix: Example Surviving Mutant

Source (`verbs.py`):
```python
def search(request):
    if request.limit > 100:
        request.limit = 100
    results = backend.search(request.query, limit=request.limit)
    return results
```

Mutant (changes `>` to `>=`):
```python
def search(request):
    if request.limit >= 100:  # MUTATED
        request.limit = 100
    ...
```

If tests pass with this mutant, it means no test sends `limit=100` and checks that it's preserved (not clamped to 100). The fix is a test, not a code change:

```python
def test_search_limit_boundary():
    request = SearchRequest(query="housing", limit=100)
    result = search(request)
    assert request.limit == 100  # Should NOT be clamped

    request = SearchRequest(query="housing", limit=101)
    result = search(request)
    assert request.limit == 100  # Should be clamped
```

This test kills both the original mutant and its inverse.
