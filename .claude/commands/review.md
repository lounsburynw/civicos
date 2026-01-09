# Review Code with pr-review-toolkit

Run pr-review-toolkit agents to review code quality before commit or PR creation.

## Usage

```
/review [scope]
```

**Scopes:**
- (default) - Review unstaged changes (`git diff`)
- `staged` - Review staged changes (`git diff --staged`)
- `branch` - Review all changes on current branch vs main
- `file <path>` - Review specific file

## Agents

The pr-review-toolkit plugin provides these agents (requires plugin installation):

| Agent | Purpose | Model |
|-------|---------|-------|
| **code-reviewer** | CLAUDE.md adherence, bugs, quality | opus |
| **code-simplifier** | Simplify while preserving function | inherit |
| **pr-test-analyzer** | Test coverage quality | inherit |
| **silent-failure-hunter** | Silent failures, error handling | inherit |
| **type-design-analyzer** | Type invariants, encapsulation | inherit |
| **comment-analyzer** | Comment accuracy | inherit |

## Standard Review (Before Commit)

Run `code-reviewer` on your changes:

```
Use the Task tool to launch the code-reviewer agent to review my unstaged changes.
Focus on CLAUDE.md compliance, bugs, and code quality issues.
```

## Full Review (Before PR)

For a comprehensive review before creating a PR, run multiple agents:

**Step 1: Code Quality**
```
Use the Task tool to launch the code-reviewer agent to review all changes on this branch compared to main.
```

**Step 2: Test Coverage (if tests were added/modified)**
```
Use the Task tool to launch the pr-test-analyzer agent to review test coverage for the changes on this branch.
```

**Step 3: Error Handling (if error handling was touched)**
```
Use the Task tool to launch the silent-failure-hunter agent to check for silent failures in the changes.
```

**Step 4: Type Design (if new types were added)**
```
Use the Task tool to launch the type-design-analyzer agent to review any new types added in this branch.
```

## Quick Reference

| Scenario | Agents to Run |
|----------|---------------|
| Simple bug fix | code-reviewer |
| New feature | code-reviewer, pr-test-analyzer |
| Error handling changes | code-reviewer, silent-failure-hunter |
| New data models | code-reviewer, type-design-analyzer |
| Major refactor | code-reviewer, code-simplifier, pr-test-analyzer |

## Integration with Civic Critics

The `/review` command complements `/critic`:

| Tool | Focus |
|------|-------|
| `/critic` | Civic-specific patterns (pipeline, protocol, architecture) |
| `/review` | General code quality (bugs, tests, error handling, types) |

**Recommended pre-PR workflow:**
1. `git diff` - Review your changes
2. `/critic` - Run Civic-specific critics
3. `/review` - Run pr-review-toolkit agents
4. `/commit` - Commit if all pass

## Parallel Session Usage

For secondary sessions working on feature branches:

```bash
# Before creating PR from feature branch
git diff main...HEAD           # See all changes
/critic                        # Civic patterns
/review branch                 # pr-review-toolkit
gh pr create                   # Create PR for merge
```
