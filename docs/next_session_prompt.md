# Recommended: extraction_services_layer_violation

**Priority:** P0
**Area:** data_integrity > architectural_debt
**Date:** 2026-01-05

> This is recommended context from Session 473. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 473 fixed `storage_protocol_agenda_items` (protocol conformance). This is the second architectural debt item flagged by the architecture critic in Session 472.

**Architecture rule violated:** `civic-extraction` doesn't import from `civic-services`

The extraction package (Intelligence layer) should not directly import from services package (Coordination layer). The Orchestration layer should mediate.

## Violations Found

```bash
# Run this to see all violations:
grep -r 'from civic_services' packages/civic-extraction/
```

| File | Import | What It's Using |
|------|--------|-----------------|
| `cli/agenda.py:294` | `AgendaIntegrator` | LLM-based agenda extraction |
| `cli/legislative.py` | `LegiScanClient`, `LegislativeDiscovery` | API clients |
| `cli/decisions.py` | `RetrospectiveAnalyzer` | LLM-based decision extraction |
| `cli/seeclickfix.py` | `SeeClickFixClient` | API client |

Also in scripts:
- `scripts/aggregate_agenda_from_chunks.py:206` → `get_model_for_task`

## Recommended Approach

**Option 1 (Preferred): Move modules to civic-extraction**

AgendaIntegrator and similar are extraction logic, not coordination logic. They should live in `civic-extraction`:

1. Move `civic-services/processing/agenda_integration.py` → `civic-extraction/integrators/agenda.py`
2. Move `civic-services/processing/retrospective_analyzer.py` → `civic-extraction/integrators/retrospective.py`
3. Update imports in CLI commands
4. Move `get_model_for_task` to civic-extraction or civic core

**Option 2: Dependency Injection**

Pass integrators as parameters rather than importing them. More complex, less preferred.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/agenda.py:294` - AgendaIntegrator import
- `packages/civic-services/src/civic_services/processing/agenda_integration.py` - AgendaIntegrator class
- `packages/civic-services/src/civic_services/processing/retrospective_analyzer.py` - RetrospectiveAnalyzer
- `.critics/architecture.critic.md:59` - Rule definition

## Suggested Steps

1. **Explore AgendaIntegrator** to understand its dependencies:
   ```bash
   head -50 packages/civic-services/src/civic_services/processing/agenda_integration.py
   ```

2. **Create integrators directory** in civic-extraction:
   ```bash
   mkdir -p packages/civic-extraction/src/civic_extraction/integrators
   ```

3. **Move AgendaIntegrator** and update imports

4. **Run tests** to verify nothing broke:
   ```bash
   pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
   ```

5. **Run architecture critic** to verify fix:
   ```bash
   /critic architecture
   ```

## Success Criteria

- [ ] `grep -r 'from civic_services' packages/civic-extraction/` returns no results
- [ ] Architecture critic passes
- [ ] Smoke tests pass (39 tests)
- [ ] pilot.json updated: `extraction_services_layer_violation` → ready

## Complexity Note

This may require moving multiple files and updating multiple imports. Consider scoping to just AgendaIntegrator first if the full fix is too large for one session.
