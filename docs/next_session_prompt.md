# Recommended: Data Path Resolver

**Priority:** P0 (IMMEDIATE)
**Area:** data_architecture > configuration_management
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 344 completed `jurisdiction_registry_consolidation` - created a centralized `JurisdictionRegistry` class that consolidates all jurisdiction configuration (149/173 items ready, 86.1%). The next priority item is centralizing file path generation which currently blocks containerized deployment.

**The problem:** Hardcoded paths throughout the codebase make it impossible to run in containers or alternate environments:
- `data/civic_state.db` (15+ references)
- `data/pilot/vectors/` (embeddings.py)
- `data/checkpoints/` (pipeline.py)

## Recommended Task

Create a `DataPathResolver` class that reads `CIVIC_DATA_ROOT` from environment and generates all file paths:

1. Create `DataPathResolver` class in `packages/civic/src/civic/paths.py`
2. Support environment variable `CIVIC_DATA_ROOT` with fallback to `data/`
3. Provide methods for all common paths:
   - `state_db()` -> civic_state.db path
   - `vectors_dir()` -> vectors directory
   - `checkpoints_dir()` -> checkpoints directory
4. Refactor files with hardcoded paths to use resolver

## Key Files to Investigate

Use Explore agent to find hardcoded paths:
```
grep -r "data/civic_state.db" packages/
grep -r "data/pilot/vectors" packages/
grep -r "data/checkpoints" packages/
```

## Suggested Approach

1. **Create DataPathResolver class**:
   ```python
   import os
   from pathlib import Path

   class DataPathResolver:
       def __init__(self, root: str = None):
           self.root = Path(root or os.environ.get('CIVIC_DATA_ROOT', 'data'))

       def state_db(self) -> Path:
           return self.root / 'civic_state.db'

       def vectors_dir(self) -> Path:
           return self.root / 'pilot' / 'vectors'

       def checkpoints_dir(self) -> Path:
           return self.root / 'checkpoints'

   # Module-level default resolver
   _default_resolver = None
   def get_resolver() -> DataPathResolver:
       global _default_resolver
       if _default_resolver is None:
           _default_resolver = DataPathResolver()
       return _default_resolver
   ```

2. **Refactor files** to use resolver instead of hardcoded paths

3. **Add tests** for path resolution with different CIVIC_DATA_ROOT values

## Tests to Run

```bash
# Smoke tests (core API)
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# If you add tests for DataPathResolver
pytest packages/civic/tests/test_paths.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] DataPathResolver class in packages/civic/src/civic/paths.py
- [ ] CIVIC_DATA_ROOT environment variable support
- [ ] Hardcoded paths replaced in major files
- [ ] Existing tests still pass
- [ ] pilot.json `data_path_resolver` marked as ready

## Pilot Progress

- 149/173 items ready (86.1%)
- 24 items remaining
- P0: data_path_resolver (this item)
