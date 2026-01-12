# Federal Programs Parser Strategy

Research findings and implementation plan for authoritative federal program data ingestion.

## Problem Statement

Currently, federal program descriptions (CDBG, HOME, etc.) are generated via Perplexity AI queries. While this provides synthesized information quickly, it has limitations:

- No source verification (potential hallucinations)
- No authoritative allocation amounts
- Stale information risk
- No direct linkage to official program rules

This document outlines a strategy to replace Perplexity-sourced program data with authoritative federal sources.

## Current State

### Existing Federal Data Clients

| Client | Source | Data Type | Method |
|--------|--------|-----------|--------|
| `FederalAuditClearinghouseClient` | api.fac.gov | Audited expenditures (SEFA) | REST API |
| `USAspendingClient` | usaspending.gov | Direct federal awards | REST API |

### Current Program Coverage (Perplexity-sourced)

| Topic | Programs |
|-------|----------|
| Housing | CDBG, HOME, Section 8 HCV, LIHTC |
| Transportation | FTA Formula Grants, TAP |
| Environment | EPA EJ Grants, DOE EECBG |
| Education | Title I Part A |

## Authoritative Data Sources

### HUD Exchange (hudexchange.info)

**URL:** https://www.hudexchange.info/grantees/allocations-awards/

**Data Available:**
- CDBG, HOME, ESG, HOPWA, HTF, RHP, CoC, NSP allocations
- Per-grantee amounts by fiscal year
- Historical data back to FY 1975
- Grantee type (entitlement vs. state-administered)

**Access Method:** Web scraping (no public API)
- JavaScript-rendered content requires Playwright
- Pagination for search results
- Session/cookie handling may be needed

**Alternative:** Annual Excel download from hud.gov/hud-partners/community-budget-25

### SAM.gov Assistance Listings

**URL:** https://sam.gov/assistance-listings

**Data Available:**
- Authoritative program definitions (formerly CFDA)
- Assistance Listing Numbers (ALN)
- Eligibility requirements
- Application procedures
- Compliance requirements

**Access Method:** REST API via GSA Open Technology
- Endpoint: https://open.gsa.gov/api/
- Authentication: API key (free from api.data.gov)
- Replaces Perplexity for program catalog metadata

### HUD GIS Open Data

**URL:** https://hudgis-hud.opendata.arcgis.com/

**Data Available:**
- CDBG grantee area boundaries
- Geographic identifiers for jurisdictions
- Mapping data for entitlement communities

**Access Method:** ArcGIS REST API
- Standard GeoJSON/Shapefile downloads
- Query by location or jurisdiction name

### Other Federal Sources

| Source | URL | Data Type |
|--------|-----|-----------|
| FTA Grants | transit.dot.gov/grants | Transit allocations |
| EPA Grants | epa.gov/grants | Environmental program data |
| FHWA Apportionments | fhwa.dot.gov | Highway formula funds |
| Grants.gov | grants.gov | Open opportunities |

## Recommended Parsers

### Tier 1: High Priority (Pre-Pilot)

#### 1. HUDExchangeClient

**Purpose:** Authoritative CDBG/HOME/ESG/HOPWA allocation data per jurisdiction

**Implementation:**
```python
class HUDExchangeClient:
    """
    HUD Exchange allocation data scraper using Playwright.

    Extracts per-jurisdiction allocations for CPD formula programs.
    """

    BASE_URL = "https://www.hudexchange.info"

    def get_allocations(
        self,
        jurisdiction_name: str,
        program: str,  # "CDBG", "HOME", "ESG", "HOPWA", "HTF"
        fiscal_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get allocations for a specific jurisdiction and program."""
        ...

    def get_grantee_profile(
        self,
        jurisdiction_name: str,
    ) -> Dict[str, Any]:
        """Get grantee metadata (type, programs, contact info)."""
        ...

    def search_allocations(
        self,
        state: str = "CA",
        program: str = "CDBG",
        fiscal_year: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search allocations by state and program."""
        ...
```

**Data Flow:**
```
HUD Exchange → HUDExchangeClient → PostgreSQL (federal_program_allocations)
                                 → pgvector (semantic search)
```

**Challenges:**
- No public API (requires Playwright for JS rendering)
- Rate limiting considerations
- Pagination handling
- Data normalization (jurisdiction name matching)

#### 2. SAMAssistanceClient

**Purpose:** Authoritative program definitions (replace Perplexity)

**Implementation:**
```python
class SAMAssistanceClient:
    """
    SAM.gov Assistance Listings API client.

    Retrieves authoritative federal program definitions.
    """

    BASE_URL = "https://api.sam.gov"

    def get_program(
        self,
        assistance_listing_number: str,  # e.g., "14.218" for CDBG
    ) -> Dict[str, Any]:
        """Get program details by ALN (formerly CFDA number)."""
        ...

    def search_programs(
        self,
        keyword: str,
        agency: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search programs by keyword or agency."""
        ...

    def get_program_eligibility(
        self,
        assistance_listing_number: str,
    ) -> Dict[str, Any]:
        """Get detailed eligibility and compliance requirements."""
        ...
```

**Data Flow:**
```
SAM.gov API → SAMAssistanceClient → PostgreSQL (federal_programs)
                                  → pgvector (semantic search)
```

**Benefits:**
- REST API (no scraping)
- Free API key from api.data.gov
- Authoritative source (replaces Perplexity)
- Includes compliance requirements, eligible activities

### Tier 2: Medium Priority (Post-Pilot)

#### 3. FTAGrantsClient

**Purpose:** Federal Transit Administration formula and discretionary grants

**Programs:**
- Section 5307 (Urbanized Area Formula)
- Section 5310 (Enhanced Mobility)
- Section 5311 (Rural Area Formula)
- CMAQ (Congestion Mitigation)

#### 4. EPAGrantsClient

**Purpose:** EPA environmental program allocations

**Programs:**
- CWSRF (Clean Water State Revolving Fund)
- DWSRF (Drinking Water State Revolving Fund)
- Brownfields Grants
- Environmental Justice Grants

### Tier 3: Future (As Needed)

- FEMAGrantsClient (BRIC, HMGP, PDM)
- FHWAClient (STBG, NHPP apportionments)
- GrantsGovClient (open opportunities)

## Program Coverage Expansion

### HUD CPD Programs (Add to federal_programs)

| Program | ALN | FY2025 Allocation | San Rafael Relevance |
|---------|-----|-------------------|----------------------|
| CDBG | 14.218 | $3.3B (59.4%) | Already covered |
| HOME | 14.239 | $1.26B (22.7%) | Already covered |
| ESG | 14.231 | $289M (5.2%) | Homelessness prevention |
| HOPWA | 14.241 | $456M (8.2%) | HIV/AIDS housing |
| HTF | 14.275 | $222M (4.0%) | Extremely low-income |
| CoC | 14.267 | ~$3B | Homelessness services |

### Transportation Programs (Add)

| Program | Agency | Relevance |
|---------|--------|-----------|
| CMAQ | FHWA | Air quality, active transport |
| STBG | FHWA | Flexible transportation |
| Section 5307 | FTA | Transit operations |
| Section 5310 | FTA | Paratransit, seniors |
| RAISE | DOT | Major infrastructure |

### EPA Programs (Add)

| Program | Relevance |
|---------|-----------|
| CWSRF | Wastewater infrastructure |
| DWSRF | Drinking water infrastructure |
| Brownfields | Contaminated site cleanup |
| Clean School Bus | School bus electrification |

### FEMA Programs (Add)

| Program | Relevance |
|---------|-----------|
| BRIC | Pre-disaster resilience |
| HMGP | Post-disaster mitigation |
| FMA | Flood mitigation |

## Implementation Plan

### Phase 1: HUD Exchange Parser (Pre-Pilot)

1. **Create HUDExchangeClient** with Playwright
   - Implement allocation search and retrieval
   - Handle pagination and rate limiting
   - Normalize jurisdiction names

2. **Ingest San Rafael allocations**
   - CDBG, HOME, ESG historical allocations
   - Store in federal_program_allocations table

3. **Create vector embeddings**
   - Add to pgvector corpus
   - Enable "what federal money is available?" queries

### Phase 2: SAM.gov Integration (Pre-Pilot)

1. **Create SAMAssistanceClient**
   - REST API integration
   - Program definition retrieval

2. **Replace Perplexity program data**
   - Migrate existing programs to SAM.gov source
   - Add ALN (CFDA) numbers to all programs

3. **Expand program catalog**
   - Add ESG, HOPWA, HTF, CoC definitions
   - Add transportation and EPA programs

### Phase 3: Additional Parsers (Post-Pilot)

1. FTA allocations client
2. EPA grants client
3. FEMA mitigation grants client

## Data Model Integration

### federal_programs table

```sql
-- Already exists (Session 505)
-- Add columns for SAM.gov integration:
ALTER TABLE federal_programs ADD COLUMN IF NOT EXISTS
    assistance_listing_number TEXT;  -- ALN (formerly CFDA)
```

### federal_program_allocations table

```sql
-- Already exists (Session 505)
-- HUD Exchange data maps directly to existing schema
```

## Success Metrics

| Metric | Target |
|--------|--------|
| Programs with authoritative source | 100% (replace all Perplexity) |
| San Rafael allocations ingested | All CDBG/HOME/ESG historical |
| Semantic search accuracy | "what federal housing money?" returns accurate results |
| Data freshness | Updated within 30 days of HUD publication |

## References

- [HUD Exchange Awards & Allocations](https://www.hudexchange.info/grantees/allocations-awards/)
- [SAM.gov Assistance Listings](https://sam.gov/assistance-listings)
- [GSA Open APIs](https://open.gsa.gov/api/)
- [HUD GIS Open Data](https://hudgis-hud.opendata.arcgis.com/)
- [FY2025 CPD Allocations](https://www.hud.gov/hud-partners/community-budget-25)
- [Federal Grants to Local Governments (CRS)](https://www.congress.gov/crs-product/R40638)
