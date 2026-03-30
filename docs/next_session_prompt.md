# Recommended: StateElectionProvider ABC + CA Provider

**Priority:** P0 (state_election_provider)
**Area:** multi_state_portability
**Date:** 2026-03-29

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed two items: `ballot_measure_content` (CA voter guide extraction client, model extensions, explore display) and the first two phases of the multi-state election portability roadmap (`state_election_config` + `deadline_generalization`). Election cycles and deadlines are now config-driven via `StateElectionConfig` — configs exist for CA, TX, FL, NY, PA, IL. All 72 election tests pass.

The next step is the **provider abstraction** — extracting CA-specific election source detection from `onboard.py` into a `CaliforniaElectionProvider` class, behind an ABC that contributors implement per state. This is the key piece that makes adding a new state a well-defined, isolated task.

## What Needs to Be Done

Create the `StateElectionProvider` ABC and extract California's election source detection logic into `providers/california.py`. Refactor `onboard.py:detect_election_sources()` to dispatch to the provider registry.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/onboard.py:687-757` — `detect_election_sources()` has `if state == "CA"` guard + Civera lookup + Marin registrar legacy key. This is what gets extracted.
- `packages/civicos/src/civicos/_internal/elections/state_config.py` — `StateElectionConfig` dataclass + `STATE_CONFIGS` for 6 states (created this session)
- `packages/civicos/src/civicos/_internal/elections/cycles.py` — Already refactored to use config (this session)
- `packages/civicos/src/civicos/_internal/elections/deadlines.py` — Already generalized (this session)
- `packages/civicos-extraction/src/civicos_extraction/clients/civera_election_stats.py:32-49` — `CIVERA_INSTANCES` registry (3 CA counties)
- `packages/civicos-extraction/src/civicos_extraction/clients/factory.py` — Client factory dispatch

## Suggested Approach

1. **Create `providers/__init__.py`** at `packages/civicos/src/civicos/_internal/elections/providers/__init__.py`:
   - `StateElectionProvider` ABC with `config` property, `detect_election_sources()` abstract method, and default `generate_deadlines()` / `get_primary_date()` methods
   - `get_provider(state_code)` registry function
   - `_create_provider(state_code)` factory with lazy imports

2. **Create `providers/california.py`**:
   - `CaliforniaElectionProvider(StateElectionProvider)`
   - Move body of `onboard.py:detect_election_sources()` lines 707-757 into `detect_election_sources()`
   - Includes: CA SOS detection, Civera instance lookup, Marin registrar legacy key, division filter inference

3. **Refactor `onboard.py:detect_election_sources()`**:
   - Replace with ~5-line dispatcher: `get_provider(state)` → `provider.detect_election_sources(...)`
   - Unsupported states return `{}` (federal reps still work via Congress.gov)

4. **Write tests**:
   - Provider registry dispatch test
   - CA provider returns same results as current implementation
   - Unsupported state returns empty dict

## Tests to Run

```bash
# Election calendar (regression — 72 tests)
pytest packages/civicos/tests/test_election_calendar.py -v --override-ini="addopts="
# Explore ballot (regression)
pytest packages/civicos/tests/test_explore_ballot.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `StateElectionProvider` ABC defined with `detect_election_sources()` abstract method
- [ ] `CaliforniaElectionProvider` implements the ABC with current CA logic
- [ ] `onboard.py:detect_election_sources()` dispatches via provider registry
- [ ] Unsupported states return `{}` instead of crashing
- [ ] All existing tests pass (no behavior change for CA)
- [ ] Adding a new state requires only: config entry + provider file + factory registration

## Architecture Reference

The plan file at `~/.claude/plans/iterative-snuggling-stream.md` has the full multi-state portability design including file layout, contributor workflow, and phasing. This is Phase 3 of 6.

## Session Summary

This session made 3 commits:
1. `61d9674` — Ballot measure content: model extensions, CA voter guide client, explore display (37 tests)
2. `5ec6238` — Added `multi_state_portability` category to launch.json (9 items)
3. `6c15f58` — StateElectionConfig + cycles/deadlines refactor for 6 states (26 new tests)

All 10 codebase critics pass. 72 election tests + 20 smoke tests green.
