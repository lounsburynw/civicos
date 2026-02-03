# City Deployment Generalizability Audit

**Created:** Session 545 (2026-02-03)
**Purpose:** Assess what's generalizable vs San Rafael-specific in the extraction/ingestion system
**Status:** Reference for scaling phase (P3 - defer until post-E2E)

---

## Executive Summary

**Overall Generalizability Score: 3.5/5** (Moderately Generalizable)

- **Good:** Core architecture well-designed for multi-jurisdiction. Storage, pipelines, and extraction protocols are parameterized.
- **Challenge:** San Rafael-specific hardcoding in election extractors, CLI convenience functions, and HUD grantee mappings.
- **For Berkeley:** ~70-80% of code is reusable as-is. MVP in 3-5 days, full parity in 2-3 weeks.

---

## Component Scores

### Highly Generalizable (5/5)

| Component | Notes |
|-----------|-------|
| Core API (civicos) | Completely generic |
| Storage (Postgres/SQLite) | Fully parameterized by jurisdiction_id |
| Vector Indexing | Generic across all backends |
| Pipeline (discover→ingest→store→index) | Zero hardcoding |
| Legistar Client | Works for any Legistar city |
| CivicClerk Client | Works for any CivicClerk city |
| Platform Detection | Auto-detects ProudCity/Legistar/CivicClerk |

### Moderately Generalizable (3-4/5)

| Component | Score | Notes |
|-----------|-------|-------|
| ProudCity | 4/5 | Needs config; DEFAULT_ARCHIVES as fallback |
| Federal Data Sources | 4/5 | Clients generic; grantee mapping manual |
| Municipal Code | 4.5/5 | Well-designed extensibility, Berkeley already in map |
| SeeClickFix | 4/5 | Generic client, helper functions for SR |
| Google Civic | 4/5 | Generic; convenience functions for SR |
| Simbli (School Boards) | 3/5 | Generic client, SR-specific helpers |

### Not Generalizable (1/5)

| Component | Notes |
|-----------|-------|
| Marin Registrar | Completely Marin County-specific |
| San Rafael Clerk | Completely San Rafael-specific election structure |

---

## Hardcoding Inventory

| File | Location | Issue | Severity |
|------|----------|-------|----------|
| `cli.py` | L349-352 | `if jurisdiction_id in ("city-san-rafael", "san-rafael")` | LOW |
| `proudcity.py` | L48-64 | DEFAULT_ARCHIVES (San Rafael specific) | MEDIUM |
| `san_rafael_clerk.py` | L47 | `BASE_URL` hardcoded | CRITICAL |
| `san_rafael_clerk.py` | L51-56 | `DISTRICT_SCHEDULE` (2024-2030 districts) | CRITICAL |
| `marin_registrar.py` | L1-50 | Marin County URLs/logic | CRITICAL |
| `seeclickfix.py` | L158-162 | `get_san_rafael_issues()` helper | LOW |
| `simbli.py` | - | `create_srcs_simbli_client()` | MEDIUM |

---

## What Unified Config Provides vs Doesn't

```
PROVIDES (~20% of work):           DOES NOT PROVIDE (~80% of work):
├── Standardized schema            ├── Extractors for new platforms
├── Single source of truth         ├── HUD grantee research
├── CLI orchestration              ├── Election scraper code
├── Validation before deploy       ├── Data quality tuning
└── Deployment mechanics           └── Per-city configuration discovery
```

---

## Berkeley Deployment Estimate

### MVP (3-5 days)
- Create `data/extraction/berkeley.json` with Legistar config
- Test `LegistarClient("berkeley").get_events()`
- Remove hardcoded San Rafael check in CLI
- Deploy with: meetings + federal data + municipal code

### Full Parity (2-3 weeks)
- Alameda County Registrar scraper (new)
- Berkeley City Clerk scraper (new)
- OUSD/school board meeting integration
- Budget PDF extraction
- Transcription with Berkeley roster

---

## Improvements for Turnkey Deployment

| Improvement | Impact | Effort |
|-------------|--------|--------|
| Config validation schema | Catch errors early | 1-2 days |
| Auto-discover HUD grantee | Reduce research | 2-3 days |
| Onboarding wizard | Guide new city setup | 1 week |
| Generic election framework | Template-based scrapers | 2-3 weeks |

---

## Platform Extractor Status

| Platform | Status | Generalizability |
|----------|--------|------------------|
| ProudCity | Production | 4/5 - needs config |
| Legistar | Production | 5/5 - fully generic |
| CivicClerk | Production | 5/5 - fully generic |
| Granicus | Unknown | Need to verify |
| Simbli | Production | 4/5 - needs board URL |
| YouTube Boards | Research | 4/5 - needs playlist |

---

## Federal/Financial Data

### Implemented (Generic)
- HUD CDBG/HOME/ESG allocations
- FAC single audit data
- CA State Controller revenue
- USAspending.gov awards
- CAGrants portal
- SAM.gov assistance listings

### Missing Infrastructure
- **Jurisdiction → Grantee Mapping:** Manual research required per city
- **Budget PDF Extraction:** No general-purpose parser
- **Housing Authority Data:** Not integrated

---

## Recommendations

### Short-term (Before scaling)
1. Remove hardcoded San Rafael checks in CLI
2. Add config validation with helpful error messages
3. Document required fields per platform type

### Medium-term (Scaling phase)
1. Generalize `MarinRegistrarClient` → `CountyRegistrarClient`
2. Generalize `SanRafaelClerkClient` → `CityClerkClient`
3. Auto-HUD-grantee lookup via FAC API

### Long-term (True turnkey)
1. Onboarding wizard for new jurisdictions
2. Template-based election scraper framework
3. ML-assisted config generation from city website

---

## Related Files

- `data/jurisdictions/*.yaml` - Unified config (Session 545)
- `packages/civicos/src/civicos/jurisdiction_config.py` - Config loader
- `packages/civicos-extraction/src/civicos_extraction/clients/` - Platform extractors
- `pilot.json` → `city_onboarding.scaling.turnkey_city_deployment` - Tracking item
