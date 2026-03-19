# Recommended: Federal Comment Submission (civic.act)

**Priority:** P0 (civic_act_federal_comment)
**Area:** multi_scale_participation
**Date:** 2026-03-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Federal comment periods are fully operational — 4,115 rules ingested, 100+ open comment periods, v2 `civic.upcoming(types=["comment_periods"])` returns them, extension Federal tab renders them with AI drafting and "Submit Official Comment" links to regulations.gov.

The missing piece is **programmatic comment submission** via `civic.act`. Currently users click through to regulations.gov manually. Adding a `submit_federal_comment` action would close the participation loop.

## What Already Exists

- `civic.act` verb dispatcher at `packages/civicos-services/src/civicos_services/query/verbs.py:864`
- Action-to-handler map at line 851: `_ACTION_TO_HANDLER` dict
- `compose_public_comment` handler at `apps/civicos-mcp/tools/handlers.py:292` (local only, San Rafael specific)
- Extension "Draft with AI" button generates prompts (client-side, `CivicReadOnlyPulse.svelte:701`)
- Extension "Submit Official Comment" is currently just `<a href={period.comment_url}>` — opens regulations.gov

## Key Files

- `packages/civicos-services/src/civicos_services/query/verbs.py:851` — `_ACTION_TO_HANDLER` map
- `apps/civicos-mcp/tools/handlers.py:292` — `compose_public_comment` (local template)
- `apps/civicos-mcp/tools/registry.py` — Tool registry for MCP
- `packages/civicos-extraction/src/civicos_extraction/clients/federal_register.py` — Federal Register client
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte:899` — Action button row

## Suggested Approach

1. **Research regulations.gov comment submission API** — `api.regulations.gov/v4/comments` with API key. Check if programmatic submission is supported (it is, but requires DEMO_KEY → production key).
2. **Add `submit_federal_comment` handler** — In handlers.py. Takes document_number, comment_text, submitter_name (optional). Calls regulations.gov API.
3. **Add `draft_federal_comment` handler** — Generates AI-assisted draft using rule context (title, abstract, agency). Similar to extension's prompt template but server-side.
4. **Wire into civic.act** — Add to `_ACTION_TO_HANDLER` map: `"submit_federal_comment": "submit_federal_comment"`, `"draft_federal_comment": "draft_federal_comment"`.
5. **Wire extension** — Replace `<a href>` with API call through `civic.act` for tracked submissions.

## Important Notes

- regulations.gov API key: Check `.env` for `REGULATIONS_GOV_API_KEY`. `DEMO_KEY` has strict rate limits.
- Comment submission may require specific fields (first_name, last_name, organization, etc.)
- Submitted comments get a tracking number — store for user reference
- Consider privacy: should CivicOS store submitted comments? User consent needed.

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="  # Smoke
cd apps/civicos-extension && npm run build  # Extension builds
```

## Success Criteria

- [ ] `civic.act(action="draft_federal_comment", ref="rule:us-federal:DOC_NUM")` returns AI draft
- [ ] `civic.act(action="submit_federal_comment", params={...})` submits to regulations.gov
- [ ] Submission returns tracking/confirmation ID
- [ ] Extension "Submit" button uses API instead of link (optional, could be next session)
