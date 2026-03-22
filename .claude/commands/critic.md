# Run Codebase Critics

Run LLM-based code review on staged changes to catch architectural issues.

## Usage

- `/critic` - Run all critics on staged changes
- `/critic pipeline` - Run only pipeline critic
- `/critic protocol` - Run only protocol critic
- `/critic architecture` - Run only architecture critic
- `/critic security` - Run only security critic
- `/critic jurisdiction` - Run only jurisdiction critic
- `/critic session` - Run only session critic
- `/critic data` - Run only data critic
- `/critic refresh` - Run only refresh critic
- `/critic configuration` - Run only configuration critic
- `/critic docs` - Run only docs critic

## Steps

1. **Get staged diff:**
```bash
git diff --staged
```

2. **Check for changes:**
If no staged changes, warn the user:
```
No staged changes. Stage your changes with `git add` first.
```

3. **Dispatch critic agents:**

Use the Agent tool to spawn parallel sub-agents for each critic. This keeps critic file contents out of main context.

**IMPORTANT: Always pass the actual `git diff --staged` output to each agent.** Do not summarize or paraphrase the diff — agents need the exact code to avoid false positives from speculation about code they haven't seen.

**For each critic, spawn an Agent with this prompt pattern:**

```
You are a code critic. Analyze this staged diff against the critic rules.

CRITIC FILE: .critics/{name}.critic.md
Read the critic file first, then analyze the diff.

RULES:
- Only flag issues visible in the diff. Do not speculate about code you haven't read.
- Pre-existing patterns unchanged by the diff are out of scope.
- If you're unsure whether something is an issue, use the Read tool to check the actual file before flagging it.

STAGED DIFF:
{paste the FULL git diff --staged output here — do NOT summarize}

Respond with JSON only:
{
  "critic": "{name}",
  "pass": boolean,
  "issues": ["list of specific issues found"],
  "severity": "critical" | "warning" | "info",
  "suggestions": ["optional fixes"]
}
```

**Spawn these in parallel using multiple Agent tool calls in a single message:**
- Agent: "Run pipeline critic" → reads `.critics/pipeline.critic.md`
- Agent: "Run protocol critic" → reads `.critics/protocol.critic.md`
- Agent: "Run architecture critic" → reads `.critics/architecture.critic.md`
- Agent: "Run security critic" → reads `.critics/security.critic.md`
- Agent: "Run jurisdiction critic" → reads `.critics/jurisdiction.critic.md`
- Agent: "Run session critic" → reads `.critics/session.critic.md`
- Agent: "Run data critic" → reads `.critics/data.critic.md`
- Agent: "Run refresh critic" → reads `.critics/refresh.critic.md`
- Agent: "Run configuration critic" → reads `.critics/configuration.critic.md`
- Agent: "Run docs critic" → reads `.critics/docs.critic.md`

Use `model: "haiku"` for fast, cost-effective critic runs.

**If the diff is very large (>500 lines):** You may split it by file group and send relevant portions to each critic. But always send actual diff content, never prose summaries.

4. **Aggregate results:**

Collect JSON responses from all agents. Format as summary table:

```
## Critic Results

| Critic | Result | Severity | Issues |
|--------|--------|----------|--------|
| Pipeline | ✅ PASS | - | - |
| Protocol | ✅ PASS | - | - |
| Architecture | ⚠️ WARNING | warning | 1 issue |
| Security | ✅ PASS | - | - |
| Jurisdiction | ✅ PASS | - | - |
| Data | ✅ PASS | - | - |
| Docs | ✅ PASS | - | - |
| Session | ❌ FAIL | critical | No P0 set |

## Issues Found

### Session Critic (critical)
- No P0 item set for next session

## Summary

Critics run: 8
Passed: 7
Warnings: 0
Failed: 1

Ready to commit: No
```

## Single Critic Mode

If user specifies a single critic (e.g., `/critic session`), only spawn one agent for that critic.

## Benefits of Sub-Agent Approach

- **Context efficient**: Critic files stay out of main context
- **Parallel execution**: All critics run simultaneously
- **Isolated analysis**: Each agent focuses on one concern
- **Structured output**: JSON responses easy to aggregate

## Notes

- Critics are defined in `.critics/*.critic.md`
- Each critic outputs JSON with pass/issues/severity
- Critical failures should block commit
- Warnings are advisory
- Use haiku model for cost efficiency (~$0.001 per critic run)
