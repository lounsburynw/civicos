# Recommended: Feedback Channel for Pilot Users

**Priority:** P0
**Area:** pilot_validation > user_readiness
**Date:** 2026-03-09

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session completed `provider_api_polling` — all 7 external services (Modal, OpenAI, Google, AssemblyAI, Supabase, R2) are now instrumented for unified cost tracking with a reconciliation endpoint. Also fixed an architecture violation (cross-layer import in blob.py replaced with callback hook pattern). Pilot is at 94% completion with 21 items remaining (all P3). `feedback_channel` is set as P0 because pilot launch requires a way for San Rafael users to report issues.

## Recommended Task

Add a feedback mechanism so pilot users can report bugs and provide feedback. Options:
1. **GitHub Issues link** — simplest, add to extension UI and API responses
2. **In-app feedback form** — richer, sends to a backend endpoint
3. **Email link** — fallback if GitHub is too technical for non-dev users

The extension is the primary user surface, so the feedback mechanism should be accessible from there.

## Key Files

- `apps/civicos-extension/src/` — Browser extension source (Svelte)
- `apps/civicos-extension/src/components/` — UI components
- `packages/civicos-services/src/civicos_services/servers/routers/` — API routers
- `docs/internal/user-feedback-spec.md` — May contain a spec (untracked file exists)

## Suggested Approach

1. **Read `docs/internal/user-feedback-spec.md`** — check if a spec already exists
2. **Add feedback button to extension** — small icon/link in the extension popup or sidebar that opens a feedback form or links to GitHub Issues
3. **Optional: Add `/feedback` API endpoint** — receives feedback JSON, stores in DB or forwards to GitHub Issues via API
4. **Test in extension** — `cd apps/civicos-extension && npm run dev`, load in Chrome, verify feedback flow
5. **Update pilot.json** — mark `feedback_channel` as ready

## Tests to Run

```bash
# Extension builds
cd apps/civicos-extension && npm run build

# API smoke test (if endpoint added)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Pilot users have a visible way to report issues from the extension
- [ ] Feedback reaches maintainers (GitHub Issues, email, or stored in DB)
- [ ] Extension builds successfully with the feedback UI
- [ ] `feedback_channel` marked ready in pilot.json
