# Emergency Session Save

Write a session handoff when context is running low. Captures the current state, what's broken, and exact debug steps so the next session can pick up immediately.

## Usage

`/save` — writes to `docs/next_session_prompt.md` (default, for primary sessions)
`/save inline` — appends to `claude-progress.txt` (for parallel sessions)

The argument `$ARGUMENTS` controls the mode:
- Empty or "official": writes `docs/next_session_prompt.md`
- "inline" or "parallel": appends to `claude-progress.txt`

## Steps

1. **Determine output mode:**

If `$ARGUMENTS` contains "inline" or "parallel", set mode to INLINE. Otherwise set mode to OFFICIAL.

2. **Gather context automatically** (read these files, do NOT ask the user):

```bash
# Current branch and uncommitted changes
git branch --show-current
git status --short
git diff --stat

# Recent progress
tail -40 claude-progress.txt
```

3. **Write the handoff document** with this structure:

```markdown
## Session Save — [date] — [brief title of what was being worked on]

**Status:** [BROKEN / IN PROGRESS / BLOCKED]
**Branch:** [current branch]
**Uncommitted changes:** [yes/no, summary]

### What was done this session
- [Bullet list of changes made, with file paths]

### Current problem
[2-3 sentences: what's broken or incomplete, and the symptoms]

### Root cause analysis
[What you've figured out so far about why it's broken]

### Exact debug steps for next session
1. [First thing to try — be specific with file:line references]
2. [Second thing to try]
3. [Third thing to try]

### Key files
- `path/to/file.ts:123` — [what's there and why it matters]

### Build & test
```bash
[exact commands to rebuild/test]
```
```

4. **Write to the appropriate location:**

- **OFFICIAL mode**: Write to `docs/next_session_prompt.md` (read existing content first to avoid clobbering)
- **INLINE mode**: Append to `claude-progress.txt` (prepend before existing entries)

5. **Confirm the write:**

```bash
# Show what was written
if [[ "$MODE" == "OFFICIAL" ]]; then
    echo "=== Handoff written to docs/next_session_prompt.md ==="
    head -30 docs/next_session_prompt.md
else
    echo "=== Handoff appended to claude-progress.txt ==="
    head -30 claude-progress.txt
fi
```

## Key principles

- **Be specific, not vague.** "Clear stale `civicos_relay_url` from chrome.storage" not "fix the storage issue"
- **Include file:line references.** The next session has no memory.
- **State the symptoms.** "Blank UX in side panel" not "it doesn't work"
- **Prioritize the fix.** Put the most likely fix first in debug steps.
- **Skip the P0 ceremony.** Unlike `/nextsesh`, this is an emergency save — don't block on launch.json validation.
