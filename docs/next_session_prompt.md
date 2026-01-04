# Recommended: scheduled_data_tests

**Priority:** P0
**Area:** test_infrastructure > test_categorization
**Date:** 2026-01-03

> This is recommended context from Session 466. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 466 completed `voting_record_api` - the API method that connects elections to decisions. The test infrastructure now has all heavy tests marked with `@pytest.mark.slow`, but they only run locally. Need a scheduled CI workflow to run these weekly without blocking PRs.

**Current state:**
- Main CI (`tests.yml`) runs smoke + full suite on push/PR (~15 min)
- Heavy tests marked with `@pytest.mark.slow`:
  - `test_seed_san_rafael.py` - Real data seeding (35MB PDFs)
  - `test_deployment_rollback.py` - Rollback procedures
  - `test_e2e_verification.py` - End-to-end flows
  - `test_integration_load.py` - Load testing
  - `test_integration_extraction_failures.py` - Failure handling
- These tests skip in CI because they need large test data

## Recommended Task

Create a GitHub Actions workflow for weekly scheduled data tests:

1. **Create `.github/workflows/data-tests.yml`:**
   ```yaml
   name: Data Tests (Weekly)

   on:
     schedule:
       - cron: '0 6 * * 0'  # 6am UTC every Sunday
     workflow_dispatch:  # Manual trigger

   jobs:
     data-tests:
       runs-on: ubuntu-latest
       timeout-minutes: 60

       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.11'
             cache: 'pip'

         - name: Install dependencies
           run: |
             pip install torch --index-url https://download.pytorch.org/whl/cpu
             pip install -e packages/civic[all]
             pip install -e packages/civic-extraction

         - name: Download test data
           run: |
             # Download San Rafael PDFs and transcripts
             # (Need to set up data download step)

         - name: Run slow tests
           run: |
             pytest packages/civic/tests/ -m slow -v --tb=short
   ```

2. **Set up test data download:**
   - Store test corpus in R2 or GCS (35MB compressed)
   - Download script in workflow
   - Cache between runs

3. **Add notification on failure:**
   - GitHub Actions notification or Slack webhook

## Key Files

- `.github/workflows/tests.yml` - Existing CI workflow (pattern to follow)
- `.github/workflows/daily-backup.yml` - Example of scheduled workflow
- `packages/civic/tests/test_seed_san_rafael.py:34` - Slow marker example
- `packages/civic/pyproject.toml` - pytest markers config

## Tests to Run

```bash
# Check which tests are marked slow
pytest packages/civic/tests/ -m slow --collect-only

# Run slow tests locally (to verify they work)
pytest packages/civic/tests/ -m slow -v --tb=short
```

## Success Criteria

- [ ] `.github/workflows/data-tests.yml` created
- [ ] Workflow runs on weekly schedule (Sundays)
- [ ] Workflow can be triggered manually (workflow_dispatch)
- [ ] Runs all `@pytest.mark.slow` tests
- [ ] Test data download/cache strategy documented
- [ ] Workflow tested via manual trigger

## Dependencies

- Test data needs to be accessible (may need to upload to R2 first)
- Slow tests must pass locally before adding to CI
