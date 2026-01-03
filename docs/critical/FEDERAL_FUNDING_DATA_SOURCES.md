# Federal Funding Data Sources

Understanding how federal money flows to local governments, and which data sources capture what.

## External Data Sources

| Source | URL | What It Shows | Timeliness |
|--------|-----|---------------|------------|
| **USAspending.gov** | https://www.usaspending.gov | Direct federal awards | Near real-time |
| **FAC (Federal Audit Clearinghouse)** | https://app.fac.gov | Audited expenditures (SEFA) | 18-24 month lag |
| **CA Grants Portal** | https://www.grants.ca.gov | State grant programs | Varies |
| **SAM.gov** | https://sam.gov | Entity registration (UEI lookup) | Real-time |

## The Two Federal Data Sources

| Source | What It Shows | Authority |
|--------|---------------|-----------|
| **USAspending.gov** | Direct federal awards | Award amounts (allocated) |
| **FAC** | All federal expenditures | Audited spending (actual) |

## Why They Differ

Most federal funding to local governments is **pass-through**, not direct:

```
Federal Agency  →  State Agency  →  City
   (FHWA)          (Caltrans)     (San Rafael)
```

- **USAspending** records the award to Caltrans
- **FAC** records San Rafael's audited expenditure

### Example: San Rafael FY2023

**USAspending shows:**
- SLFRF COVID Relief: $16.1M (direct from Treasury)
- Port Security Grant: $905K (direct from DHS)
- Total direct awards: ~$17M

**FAC shows:**
- Medicaid: $658K (pass-through from CA DHCS)
- Highway Planning: $637K (pass-through from Caltrans)
- FEMA Disaster: $562K (via CA OES)
- Highway Safety: $86K (pass-through from CA OTS)
- CDBG: $23K (pass-through from CA HCD)
- Total expenditures: $2.0M

The $17M in direct awards are one-time COVID-era supplements. The $2M/year recurring funding is the baseline - and it's mostly pass-through.

## Which Source to Use

| Question | Use |
|----------|-----|
| "What federal money did we actually spend?" | `federal_expenditures()` (FAC) |
| "What direct federal awards do we have?" | `get_federal_awards()` (USAspending) |
| "Which budget items are grant-funded?" | Can't answer reliably - no linkage exists |

## The Budget Linkage Problem

`funding_flow()` was designed to trace: Federal Award → State Pass-through → City Budget Item

**This doesn't work because:**
1. City budget PDFs don't contain CFDA numbers
2. No structured mapping between budget line items and grants is published
3. Keyword matching (e.g., "CDBG" in budget text) produces false positives

**Current approach:**
- `federal_expenditures()` is authoritative for federal spending
- `funding_flow()` requires explicit linkages (rare in practice)
- The two data sources answer different questions

## Data Freshness

FAC audits lag because:
1. City fiscal year ends June 30
2. Audit completed by ~December
3. Filed with FAC by March (9 months after FY end)
4. So FY2024 audit → available ~March 2025

As of January 2026:
- Latest available: FY2023
- FY2024: Should be available but not yet in FAC for San Rafael
- FY2025: Won't be available until ~March 2026

## API Methods

```python
from civic import Civic
c = Civic("san-rafael")

# Authoritative audited federal spending (FAC)
c.federal_expenditures(audit_year=2023)
c.federal_expenditures_summary(audit_year=2023)

# Direct federal awards (USAspending) - incomplete for local gov
c._storage.get_federal_awards(jurisdiction_id='san-rafael')

# Budget→grant linkages - requires explicit mappings
c.funding_flow()  # Returns empty if no linkages exist
```

## Current Platform Limitations

### What We Can Answer

| Question | Method | Data Quality |
|----------|--------|--------------|
| "What federal programs did we spend on?" | `federal_expenditures()` | Authoritative (audited) |
| "How much total federal spending?" | `federal_expenditures_summary()` | Authoritative |
| "Multi-year federal spending trend?" | `federal_expenditures(audit_year=X)` | Authoritative, 7 years |
| "What direct federal awards exist?" | `get_federal_awards()` | Incomplete (direct only) |

### What We Cannot Answer (Yet)

| Question | Why Not | Data Source That Has It |
|----------|---------|------------------------|
| "Which budget line items are grant-funded?" | Not yet integrated | City CAFR grants schedule, HUD CAPER reports |
| "If CDBG is cut 20%, which programs are affected?" | Not yet integrated | [HUD Exchange CDBG Reports](https://www.hudexchange.info/programs/cdbg/cdbg-reports-program-data-and-income-limits/) - accomplishment data by city |
| "How much state funding does San Rafael receive?" | Not yet integrated | [CA State Controller](https://bythenumbers.sco.ca.gov/) - 12 years of city revenue by source |
| "What's the current year federal spending?" | FAC audits lag 18-24 months | City quarterly financial reports, mid-year budget reviews |

### High-Priority Data Source: CA State Controller

The CA State Controller's ByTheNumbers portal has **structured, queryable data** on city intergovernmental revenue:

**API Endpoint:** `https://bythenumbers.sco.ca.gov/resource/rrtv-rsj9.csv`

**San Rafael Intergovernmental Revenue (verified):**

| Year | Federal | State | County | Total |
|------|---------|-------|--------|-------|
| 2024 | $171K | $3.5M | $909K | $4.5M |
| 2023 | $817K | $3.1M | $1.4M | $5.3M |
| 2022 | $16.2M | $2.8M | $1.3M | $20.3M |
| 2021 | $209K | $2.5M | $2.2M | $4.9M |

**Why this matters:**
- **More recent than FAC** - FY2024 available (FAC only has FY2023)
- **Includes state revenue** - $3M+/year we can't get elsewhere
- **Socrata API** - Structured, queryable, no PDF parsing
- **20+ years of history** - Data back to 2003

**Integration priority:** HIGH - See `ca_state_controller_ingestion` task in pilot.json.

### Other Potential Data Sources

| Source | URL | What It Provides |
|--------|-----|------------------|
| **HUD Exchange** | https://www.hudexchange.info/programs/cdbg/cdbg-reports-program-data-and-income-limits/ | CDBG activity expenditure reports by city - shows exactly what CDBG funds |
| **HUD Open Data** | https://hudgis-hud.opendata.arcgis.com/ | CDBG grantee data via ArcGIS API |
| **Data.gov CDBG** | https://catalog.data.gov/dataset/cdbg-accomplishment-data | CDBG accomplishment data (downloadable) |
| **City CAFR** | https://www.cityofsanrafael.org/departments/finance/ | Grants schedule, revenue breakdown (PDF, would need parsing) |

### The Budget Linkage Gap

The `funding_flow()` method was designed to trace funding from federal source to city budget item. **This capability is limited because:**

1. **No CFDA in budgets**: City budget PDFs are plain text without federal program identifiers
2. **No published mapping**: Cities don't publish structured "this budget item = this grant"
3. **Keyword matching fails**: Searching for "CDBG" in budget text produces false positives
4. **Pass-through obscures source**: Federal money often arrives via state agencies with different names

**Implication for users**: We can tell you "San Rafael spent $637K on Highway Planning (20.205)" but not "that $637K funded line items X, Y, Z in the Public Works budget."

### Data Freshness Reality

| Fiscal Year | Audit Filed | Available in FAC |
|-------------|-------------|------------------|
| FY2023 (Jul 2022 - Jun 2023) | ~Mar 2024 | Yes |
| FY2024 (Jul 2023 - Jun 2024) | ~Mar 2025 | Not yet (Jan 2026) |
| FY2025 (Jul 2024 - Jun 2025) | ~Mar 2026 | Not yet |

For current-year estimates, USAspending direct awards can provide partial visibility, but misses pass-through funding which is the majority of local government federal funding.

## Session History

- Session 448: Identified keyword matching as unreliable
- Session 449: Added FAC client for authoritative expenditure data
- Session 450: Added UEI support to USAspending for precise matching
- Session 451: Documented the distinction, clarified API purposes, added limitations
