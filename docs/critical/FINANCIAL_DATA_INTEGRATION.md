# Financial Data Integration

**Status**: Proposed
**Date**: 2026-01-03
**Builds On**: `CIVICOS_DATA_INGESTION_STRATEGY.md`, `civic_extraction.clients.base`

## Summary

This document describes how to integrate **financial data sources** into the existing extraction infrastructure. It does NOT replace existing architecture—it extends it.

## Existing Infrastructure (DO NOT DUPLICATE)

The following already exists and should be reused:

| Component | Location | Purpose |
|-----------|----------|---------|
| `ExtractionConfig` | `clients/base.py:98-150` | City config schema |
| `DataSource` protocol | `clients/base.py:152-198` | Standard extractor interface |
| `platform_detection.py` | `civic_extraction/` | Auto-detect meeting platforms |
| `IngestionManifest` | `manifest.py` | Provenance tracking |
| `data/extraction/*.json` | Config files | Per-city configurations |

## New: Financial Data Sources

Financial data sources differ from meeting sources:
- **Homogeneous**: Same API for all jurisdictions (SCO, FAC, USAspending)
- **No per-city config needed**: Just jurisdiction identifier
- **Different update cadence**: Annual/quarterly vs daily/weekly

### Currently Implemented Financial Clients

| Client | File | Data | Coverage |
|--------|------|------|----------|
| `CAStateControllerClient` | `clients/ca_state_controller.py` | Intergovernmental revenue | All CA cities |
| `FACClient` | `clients/fac.py` | Federal expenditures | All US entities |
| `USAspendingClient` | `clients/usaspending.py` | Federal awards | All US entities |

### Gap: Financial Clients Don't Follow DataSource Protocol

Current financial clients are standalone—they don't implement `DataSource.health()` or `DataSource.validate()`.

**Recommendation**: Extend existing clients to implement `DataSource` protocol for unified monitoring.

```python
# Example: Extend CAStateControllerClient to implement DataSource
class CAStateControllerClient(DataSource):
    @property
    def source_id(self) -> str:
        return f"sco-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "ca_state_controller"

    def health(self) -> HealthStatus:
        # Test API availability, return standardized status
        ...

    def validate(self) -> ValidationResult:
        # Validate jurisdiction exists in SCO data
        ...
```

## New: Budget/ACFR Extraction

Budget and ACFR extraction is heterogeneous (PDF-based, AI-assisted).

### Current State

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/extract_san_rafael_budget.py` | Budget PDF extraction | Working |
| `scripts/extract_acfr_funding_mapping.py` | ACFR extraction | Working (new) |

### Gap: No Canonical Schema for Budget Data

Meeting data has `Meeting` dataclass in `base.py`. Budget data has `BudgetLineItem` in `prompts/budget_extraction.py` but it's not integrated with the extraction config system.

**Recommendation**: Add budget schemas to `base.py` and create `BudgetExtractor` protocol.

## Proposed: City Financial Config Extension

Extend existing `ExtractionConfig` to include financial source hints:

```json
// data/extraction/san-rafael.json (extended)
{
  "source_id": "proudcity-san-rafael",
  "source_type": "proudcity",
  "jurisdiction_id": "city-san-rafael",
  "base_url": "https://www.cityofsanrafael.org",
  "archives": { ... },

  // Financial config (minimal for now - complex lookups happen at runtime)
  "financial": {
    "state": "CA",
    "county": "Marin"
    // Future: entity identifiers for automated lookups
    // "sco_city_name": "San Rafael",
    // "fac_uei": "...",
    // "budget_pdf_pattern": "https://cityofsanrafael.org/documents/budget-{fy}.pdf",
    // "acfr_pdf_pattern": "https://cityofsanrafael.org/documents/acfr-{fy}.pdf",
    // "fiscal_year_start": "07-01"
  }
}
```

## Priority: What to Build

### Immediate (integrate with existing)
1. Add `DataSource` implementation to `CAStateControllerClient`
2. Add `DataSource` implementation to `FACClient`
3. Add `DataSource` implementation to `USAspendingClient`
4. Add `financial` section to San Rafael extraction config

### Near-term (new capability)
1. Create `BudgetExtractor` protocol in `base.py`
2. Integrate budget extraction with `IngestionManifest`
3. Add budget data to unified health dashboard

### Not Needed (already exists)
- ❌ New city config schema (use `ExtractionConfig`)
- ❌ New platform detection (use `platform_detection.py`)
- ❌ New manifest system (use `IngestionManifest`)
- ❌ Data snapshot versioning (use `DataSnapshot`)

## Source Data Provenance

All financial data must track provenance for auditability.

### Required Provenance Fields

| Field | Purpose | Example |
|-------|---------|---------|
| `source_url` | Original data location | `https://bythenumbers.sco.ca.gov/api/...` |
| `fetch_timestamp` | When data was retrieved | `2026-01-03T12:00:00Z` |
| `source_version` | API version or file date | `FY24`, `v2.1` |
| `checksum` | SHA-256 of raw response | `a3f2b1c...` |
| `transformation` | Processing applied | `json_extract`, `pdf_ocr` |

### Implementation

Financial extractions must create `IngestionManifest` entries:

```python
from civic_extraction.manifest import IngestionManifest, save_manifest

manifest = IngestionManifest.create(
    jurisdiction_id="city-san-rafael",
    run_type="financial_refresh"
)
manifest.add_checksum("sco_response", response_bytes)
manifest.metadata["source_url"] = api_url
manifest.metadata["fiscal_year"] = "FY24"
save_manifest(manifest)
```

### Why This Matters

1. **Reproducibility** - Can re-fetch and verify data unchanged
2. **Debugging** - Trace errors to specific source versions
3. **Auditing** - Prove where numbers came from
4. **Freshness** - Know when data was last updated

## Manual Input Fallback Pattern

Some financial mappings cannot be reliably automated:
- Grant-to-program mappings (naming conventions vary)
- CFDA program descriptions (requires federal database join)
- Budget line item → external source linkage (heterogeneous naming)

**Principle**: Automate first, manual fallback when needed.

### Schema for Manual Data

```
data/manual/{jurisdiction_id}/
├── grant_mappings.json      # Grant name → program/source
├── budget_linkages.json     # Budget line → funding source
└── _metadata.json           # Curator, last_updated, confidence
```

### Manual Entry Schema

```json
{
  "entries": [
    {
      "id": "sr-grant-001",
      "budget_line_item": "Pickleweed Childcare Grant",
      "funding_source": "CA Dept of Education - CCTR",
      "cfda_number": null,
      "confidence": "high",
      "source": "City staff confirmation",
      "curator": "human",
      "created": "2026-01-03",
      "last_verified": "2026-01-03"
    }
  ],
  "_metadata": {
    "jurisdiction_id": "city-san-rafael",
    "last_updated": "2026-01-03",
    "entry_count": 1
  }
}
```

### Key Requirements

1. **Structured** - JSON schema, not freeform notes
2. **Versioned** - Track when created/verified
3. **Attributed** - Mark as `curator: "human"` vs `curator: "automated"`
4. **Queryable** - Can be loaded alongside automated data
5. **Auditable** - Source field explains provenance

## References

- `docs/archive/platforms/CIVICOS_DATA_INGESTION_STRATEGY.md` - Full ingestion strategy
- `packages/civic-extraction/src/civic_extraction/clients/base.py` - Base protocols
- `packages/civic-extraction/src/civic_extraction/manifest.py` - Provenance tracking
