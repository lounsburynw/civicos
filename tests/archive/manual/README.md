# Manual Test Archive

This directory contains ad-hoc test scripts and manual testing documentation from development sessions.

## Contents

- `test_*.py` - Manual integration test scripts for specific features
- `test_*.sh` - Shell scripts for manual endpoint testing
- `test_*.json` - Test data fixtures
- `MANUAL_TEST_*.md` - Manual testing guides
- `WEEK*_*.md` - Weekly implementation status notes

## Why Archived?

These files served their purpose during active development but are no longer needed in the root directory. They are preserved here for:

1. **Historical reference** - Understanding how features were tested during development
2. **Debugging** - Reproducing issues from specific development sessions
3. **Migration guidance** - Examples of manual tests that could be automated

## Current Testing Strategy

See `tests/` directory for automated test suites:
- `tests/test_*.py` - Automated pytest test suites
- `tests/test_all_fixes.py` - Comprehensive integration tests
- `tests/test_legislative_*.py` - Legislative context tests
- `tests/test_personalization_service.py` - Personalization service tests (98% coverage)
