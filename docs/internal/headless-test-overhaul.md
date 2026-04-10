# Headless Test Overhaul Pipeline

Automated test generation using Claude Code headless mode with executor/critic pattern.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Work Queue  │───▶│  Executor   │───▶│   Critic    │
│  (find gaps) │    │ (write tests)│    │ (audit+fix) │
└─────────────┘    └─────────────┘    └─────────────┘
       │                                      │
       │           ┌─────────────┐            │
       └──────────▶│   mutmut    │◀───────────┘
                   │ (validate)  │
                   └─────────────┘
```

**Why two agents?** The executor optimizes for completion and will unconsciously cut corners (existence-only assertions, mock-heavy tests). A separate critic with fresh context catches what the executor rationalizes away. This was validated empirically — first-pass tests had a 50% failure rate against the mutation critic.

## Usage

```bash
# Run all packages (recommended: overnight)
caffeinate ./scripts/test_overhaul.sh

# Run one package at a time
./scripts/test_overhaul.sh civicos-extraction

# Available packages: civicos, civicos-extraction, civicos-services, civicos-relay
```

## What It Does

For each untested source file >100 lines (excluding `__init__.py`):

1. **Executor** (`claude -p`): Reads the source file + testing guidelines, writes a test file
2. **Critic** (`claude -p`): Audits against 7 anti-patterns from `.critics/mutation.critic.md`, fixes issues in-place
3. Logs everything to `results/test_overhaul/YYYY-MM-DD/`

## What It Doesn't Do

- Run mutation testing (too slow for batch; do manually with `/test mutation <file>`)
- Decide which files are worth testing (it skips `__init__.py` and files <100 lines)
- Replace human review (you review the tests, not the code — per the agentic workflow)

## Cost

Runs on your Max subscription — no API credits needed. Each module takes ~3-5 minutes (executor + critic). A full run across all 4 packages takes ~2-3 hours.

## After the Run

```bash
# 1. Review what was generated
git diff --stat

# 2. Run all tests
source civicos-env/bin/activate
pytest packages/*/tests/ -q --override-ini="addopts="

# 3. Spot-check a few test files against the critic
/critic mutation

# 4. Run mutation baselines on key files
/test mutation packages/civicos-extraction/src/civicos_extraction/some_module.py

# 5. Commit the good ones
git add packages/*/tests/test_*.py
git commit -m "Add tests from headless overhaul pipeline"
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Rate limited | Add `sleep 10` between modules in the script |
| Laptop sleeps | Use `caffeinate` (macOS) to prevent sleep |
| Test file not created | Check executor log — usually a read failure or import error |
| Critic says FAIL | It fixes in-place, but review the fixes manually |
| Tests fail on run | The executor runs them, but env differences can cause issues. Fix manually. |
