# Recommended: Onboard Mill Valley

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The acceptance policy stack is now complete: rate limiting, PoW mining, attestation verification, monitoring, and 402 handling in the extension. All relay write paths (voice, comment, commit, complete, withdraw) return structured `WriteResult` with rejection details, and the UI surfaces user-friendly error messages.

The next milestone is federation validation. Mill Valley is the first additional jurisdiction to onboard — same county (Marin), same platform (Granicus) as San Rafael. This tests the onboarding pipeline end-to-end and surfaces friction points before cross-county work.

## Recommended Task

Run `/onboard` for Mill Valley (city-mill-valley, Granicus platform, Marin County). Document every manual step, friction point, and failure. The goal is both to get Mill Valley data flowing AND to build the onboarding checklist for future operators.

## Key Files

- `scripts/onboard.py` (or `/onboard` skill) — onboarding automation
- `config/registry/` — jurisdiction registry (add Mill Valley entry)
- `packages/civicos-extraction/` — Granicus parser (already works for San Rafael)
- `data/checkpoints/` — ingestion checkpoints
- `launch.json:346` — P0 item with full description

## Suggested Approach

1. Run `/onboard mill-valley` and follow the guided process
2. Add Mill Valley to the jurisdiction registry (`config/registry/`)
3. Configure Granicus extraction for Mill Valley's specific meeting types
4. Run data ingestion: meetings, decisions, agendas
5. Verify with `/data-status city-mill-valley`
6. Document every manual step and friction point in a friction log

## Tests to Run

```bash
# Smoke test after onboarding
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Verify data access for new jurisdiction
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-mill-valley')
print(f'Backend: {type(c.storage).__name__}')
print(f'Meetings: {c.storage.get_meeting_count(\"city-mill-valley\")}')
"
```

## Success Criteria

- [ ] Mill Valley added to jurisdiction registry
- [ ] Granicus extraction configured and running for Mill Valley
- [ ] Meetings, decisions, and/or agendas ingested into PostgreSQL
- [ ] `/data-status city-mill-valley` shows non-zero counts
- [ ] Friction log documenting manual steps and pain points
- [ ] No regressions in San Rafael data

## Recent Completions

- **Extension 402 handling** (this session) — All relay write methods return `WriteResult` with rejection details. UI shows rate limit and verification messages. Centralized `parseWriteResult()` helper.
- **Acceptance policy monitoring** (prev session) — `coordination_acceptance_logs` table, fire-and-forget logging, admin stats endpoint
- **NIP-13 PoW mining** — Client-side proof-of-work for unattested writes
- **Billing deferred** — Stripe items moved to P3, need usage data first
