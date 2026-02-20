# Recommended: Attestation Migration + Deploy, then engagement_ladder_ux

**Priority:** P0 is `engagement_ladder_ux`, but **attestation migration must run first** (5 min blocking task)
**Area:** data_architecture (migration) + frontend_refinement > city_status_dashboard (P0)
**Date:** 2026-02-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The **attestation restructure** is code-complete but the SQL migration hasn't been run yet. All code changes are committed to working tree (unstaged). The restructure embeds kind-30850 attestation events directly on voice/comment records so any relay can independently verify attestation without JOINs. This is a prerequisite for open-sourcing.

## BLOCKING: Run the SQL Migration

The migration must run before deploying, otherwise the new columns won't exist and voice/comment submission will fail.

```bash
# Connect to relay DB and run migration
source civicos-env/bin/activate
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.environ['RELAY_DATABASE_URL'])
cur = conn.cursor()
with open('scripts/sql/add_attestation_proof_to_voices.sql') as f:
    cur.execute(f.read())
conn.commit()
print('Migration complete')
# Verify backfill
cur.execute('SELECT COUNT(*) FROM coordination_voices WHERE attestation_proof IS NOT NULL')
print(f'Voices with attestation_proof: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM coordination_voices')
print(f'Total voices: {cur.fetchone()[0]}')
conn.close()
"
```

## Unstaged Changes to Commit

All attestation restructure changes are unstaged. Commit them:

### Files changed (13 modified + 1 new):
- `packages/civicos-relay/src/civicos_relay/voice/crypto.py` — `verify_attestation_proof()`
- `packages/civicos-relay/src/civicos_relay/voice/models.py` — `attestation_proof` on Voice, Comment
- `packages/civicos-relay/src/civicos_relay/storage/postgres.py` — CRUD includes attestation_proof
- `packages/civicos-relay/src/civicos_relay/sync/service.py` — Verify attestation on import
- `packages/civicos-relay/tests/test_voice.py` — 9 new attestation proof tests (all pass)
- `packages/civicos-services/src/civicos_services/servers/routers/coordination.py` — Hard gate (403/400), expiry fix, simplified read-time checks
- `packages/civicos-client/src/api.ts` — Thread attestation_proof through cast/submit
- `packages/civicos-client/src/events.ts` — Removed dead attestation helpers
- `packages/civicos-client/src/index.ts` — Removed dead re-exports
- `packages/civicos-client/src/registry.ts` — `attestation_issuer_pubkey` on RegistryServer
- `apps/civicos-registry/src/registry.ts` — `attestation_issuer_pubkey` on ServerInfo
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — Reads stored attestation, blocks unattested
- `config/registry.json` — Issuer pubkey for city-san-rafael
- `scripts/sql/add_attestation_proof_to_voices.sql` — **NEW** migration

Also unstaged from a previous session (unrelated):
- `packages/civicos-client/src/ai/manager.ts` — Chat routing fix (linter/formatter change)

## After Migration: P0 Work

The P0 item is `engagement_ladder_ux` — Phase 4b topic tagging foundation. See previous handoff context:
- Create `topicClassifier(title, summary?)` utility with keyword->topic map
- Tag agenda items, decisions, legislation by topic
- Add topic filter UI (pills) on at least one tab
- Key files: `CivicReadOnlyPulse.svelte`, `CivicAgendaView.svelte`, `civic-helpers.ts`, `SidePanel.svelte`

## Tests

```bash
# Relay tests (272 pass, includes 9 new attestation tests)
pytest packages/civicos-relay/tests/ -v --override-ini="addopts="

# Extension build
cd apps/civicos-extension && npm run build

# Client type check
cd packages/civicos-client && npx tsc --noEmit
```

## Success Criteria

- [ ] SQL migration runs successfully against relay DB
- [ ] Backfill shows existing attested voices now have `attestation_proof IS NOT NULL`
- [ ] All changes committed
- [ ] Deploy to Modal (if time permits)
- [ ] Topic tagging MVP (P0 work)
