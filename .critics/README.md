# Codebase Critics

LLM-based code review prompts that catch architectural issues before they're committed.

## Overview

Critics are specialized prompts that review code changes against Civic's patterns and architecture. They're designed to catch issues that traditional linters miss, like the Session 315 storage gap bug.

## Available Critics

| Critic | Purpose | Catches |
|--------|---------|---------|
| `pipeline.critic.md` | 4-stage ETL pattern | Storage gaps, stage ordering, persistence issues |
| `protocol.critic.md` | Protocol conformance | Missing methods, signature mismatches |
| `architecture.critic.md` | Layer boundaries | Cross-layer imports, package violations |
| `session.critic.md` | Session hygiene | Missing P0, multiple P0s, incomplete handoff |
| `data.critic.md` | ETL data quality | Schema violations, type mismatches, missing fields |

## Usage

### Via /critic Command

```bash
# Run all critics on staged changes
/critic

# Run specific critic
/critic pipeline

# Run on specific files
/critic protocol packages/civic/src/civic/storage/
```

### Manual Review

1. Stage your changes: `git add .`
2. Get the diff: `git diff --staged`
3. Feed the diff to any critic prompt
4. Review JSON output for pass/fail

### Example Output

```json
{
  "pass": false,
  "issues": [
    "Index stage reads from memory, not StorageBackend",
    "Missing store_meetings() call before indexing"
  ],
  "severity": "critical",
  "suggestions": [
    "Add self.storage.store_meetings() after ingest",
    "Change index to read from self.storage.get_meetings()"
  ]
}
```

## When to Run

- **Before commits** - Run `/critic` to catch issues early
- **PR review** - Critics can be run by reviewers on PR diffs
- **Session end** - `session.critic.md` ensures P0 is set

## Adding New Critics

1. Create `{name}.critic.md` in `.critics/`
2. Follow the template:
   - **Context** - What pattern/rule this enforces
   - **Key Files** - Where the pattern is defined
   - **Check** - Specific things to verify
   - **Output** - JSON format with pass/issues/severity
   - **Examples** - FAIL and PASS cases

3. Add to the table in this README
4. Test on known good/bad code

## Design Principles

1. **Specific to Civic** - Not generic linting, but Civic patterns
2. **Structured output** - JSON for potential automation
3. **Actionable** - Suggestions for fixes, not just complaints
4. **Severity levels** - critical/warning/info for prioritization

## Origin Story

Session 315 discovered that the Pipeline had no persistence layer - meetings were fetched then discarded. The index stage read from memory, but that memory was cleared, resulting in empty results. This bug would have been caught by `pipeline.critic.md` checking "Does index stage read from StorageBackend, not memory?"

Critics exist to catch these architectural issues that are invisible to traditional tools.
