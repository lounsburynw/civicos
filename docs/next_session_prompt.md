# Recommended: Election Source Auto-Detection

**Priority:** P0 (election_source_auto_detection)
**Area:** multi_state_portability
**Date:** 2026-04-01

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session generalized the election provider system so any state with a `StateElectionConfig` auto-gets source detection during onboarding (no per-state provider files needed). All 6 configured states (CA, TX, FL, NY, PA, IL) now work. But the providers only generate placeholder source keys like `fl_sos_results` — there's no client to actually fetch election data for non-CA states, and the source detection doesn't probe what election platform a county actually uses.

The key insight: **election data is the same problem as meeting data.** Meetings have ~7 platforms (Granicus, Legistar, BoardDocs, etc.) auto-detected via `detect_platform()`. Elections have a similar set of platforms (Clarity Elections, state SOS APIs, county registrar sites) that should be auto-detected the same way. Build `detect_election_platform()` + clients, analogous to the meeting platform detection.

## What Changed This Session

- `DefaultElectionProvider` replaces per-state files (TX/FL deleted, `providers/default.py`)
- Registry-based dispatch in `election_fetch.py` via `_FETCH_HANDLERS` dict
- Missing fetch clients produce explicit "skipped" status (not silent)
- `supported_states()` exported from `civicos` public API (no `_internal` imports)
- Per-state items (FL, NY, PA, IL) marked done in launch.json
- 43 provider tests + 9 fetch tests + 212 election tests all pass

## What to Build

**Election platform auto-detection during onboarding** — detect what election reporting system a county uses, build extraction clients for the major platforms, wire into `DefaultElectionProvider`.

### Research Phase (start here)
1. Read `docs/internal/clarity-elections-research.md` — prior research on Clarity Elections (Scytl). Covers URL patterns, JSON/XML endpoints, data ephemerality, `clarify` Python library.
2. Research: what are the top 5 election reporting platforms in the US? How detectable are they? (Clarity is #1, what else?)
3. Research: which state SOS sites have machine-readable APIs? (CA does, most don't)

### Implementation Phase
4. Build `detect_election_platform(county, state)` — probes county registrar for Clarity, SOS API, etc.
5. Build `ClarityElectionsClient` implementing `ElectionExtractor` protocol
6. Register handler in `_FETCH_HANDLERS` in `election_fetch.py`
7. Update `DefaultElectionProvider.detect_election_sources()` to call detection
8. Add to `SUPPORTED_ELECTION_SOURCES` in `clients/__init__.py`

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/providers/default.py` — DefaultElectionProvider (53 lines). Currently generates `{state}_sos_results` with no probing.
- `packages/civicos-extraction/src/civicos_extraction/providers/__init__.py` — Provider registry. Auto-creates DefaultElectionProvider for any state in `supported_states()`.
- `packages/civicos-extraction/src/civicos_extraction/election_fetch.py` — Registry-based dispatch. `_FETCH_HANDLERS` dict maps source keys to handler functions.
- `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py:128` — `SUPPORTED_ELECTION_SOURCES` frozenset.
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_results.py` — CA SOS client (844 lines). Pattern for a state SOS extraction client.
- `packages/civicos-extraction/src/civicos_extraction/clients/base.py` — `ElectionExtractor` protocol.
- `docs/internal/clarity-elections-research.md` — Clarity Elections API research.
- `packages/civicos-extraction/src/civicos_extraction/onboard.py:2191` — Step 3.6 where election sources are detected.

## Analogous Meeting Pattern (follow this)

- `packages/civicos-extraction/src/civicos_extraction/platform_detection.py` — `detect_platform()` probes multiple meeting platforms. Election detection should follow this pattern.
- Onboarding step 2 calls `detect_platform()` -> returns platform + config -> step 3 runs platform-specific discovery. Election detection should mirror this flow.

## Tests to Run

```bash
# Provider tests
pytest packages/civicos-extraction/tests/test_election_providers.py -q --override-ini="addopts="

# Election fetch tests
pytest packages/civicos-extraction/tests/test_election_fetch.py -q --override-ini="addopts="

# All election tests
pytest packages/civicos-extraction/tests/ -k election -q --override-ini="addopts="

# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Research complete: top election reporting platforms identified with detection methods
- [ ] `detect_election_platform(county, state)` probes at least Clarity Elections
- [ ] `ClarityElectionsClient` fetches election results from Clarity JSON/XML endpoints
- [ ] Handler registered in `_FETCH_HANDLERS` — dispatch works end-to-end
- [ ] Onboarding a FL city produces actual election data (not "skipped")
- [ ] Existing CA election pipeline unchanged (no regressions)
