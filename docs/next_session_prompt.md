# Recommended: Add Codebase Critics (Hotfix)

**Priority:** Pre-P0 hotfix
**Area:** Developer tooling
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 315 discovered the Pipeline had no persistence layer - meetings were fetched then discarded. This was caught manually through testing. We discussed embedding LLM-based critics in the codebase to catch such issues automatically.

## Recommended Task

Create a minimal `.critics/` directory with 3-4 targeted critic prompts that run before commits to catch architectural issues.

## Key Files

- `packages/civic-extraction/src/civic_extraction/pipeline.py:240-320` - The 4-stage pipeline
- `packages/civic/src/civic/storage/` - New StorageBackend/VectorBackend protocols
- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - Architecture reference
- `.claude/commands/` - Existing prompt patterns to follow

## Suggested Approach

1. Create `.critics/` directory structure:
   ```
   .critics/
   ├── README.md              → How to use critics
   ├── pipeline.critic.md     → 4-stage pattern, persistence checks
   ├── protocol.critic.md     → DataSource/StorageBackend conformance
   └── architecture.critic.md → Match against FINAL_PACKAGE_ARCHITECTURE.md
   ```

2. Each critic prompt should:
   - Take code diff or file content as input
   - Return structured pass/fail with reason
   - Be specific to Civic patterns, not generic linting

3. Add a `/critic` slash command that runs all critics on staged changes

4. Document in CLAUDE.md

## Example Critic Structure

```markdown
# Pipeline Critic

You are reviewing code changes for the Civic project's ETL pipeline.

## Check

Does any modification to Pipeline:
1. Maintain the 4-stage pattern (discover → ingest → store → index)?
2. Persist data via StorageBackend before indexing?
3. Read from StorageBackend for index stage (not memory)?

## Output

Respond with JSON:
{
  "pass": boolean,
  "issues": ["list of specific issues"],
  "severity": "critical" | "warning" | "info"
}
```

## Success Criteria

- [ ] `.critics/` directory exists with 3+ critic prompts
- [ ] `/critic` command runs critics on staged files
- [ ] README documents usage
- [ ] At least one critic would have caught the storage gap

## Also Fix

- Update `/nextsesh` and `/readnextsesh` to use `docs/next_session_prompt.md` (not `docs/core/`)

## Note

This is a lightweight addition (~2 hours). After this, continue with the P0 item in `pilot.json`.
