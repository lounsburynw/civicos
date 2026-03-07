# Budget Extraction System

> **Partially Implemented:** Budget extraction for San Rafael FY25-26 is complete (58 line items, $180M). The architecture below describes the full system design; some components (multi-year comparison, ACFR integration) are future work.

This document describes the architecture for extracting and storing municipal budget data in CivicOS.

## Overview

Budget data is critical for answering "how much" questions about civic decisions. Unlike legislative text (large, unstructured), budget data is **small and structured** (~100-200 records per jurisdiction per year).

### Design Goals

1. **Multi-jurisdiction**: Schema supports any municipality
2. **Open-source friendly**: AI-assisted ETL templates for community contribution
3. **Full line-item detail**: Not just department totals
4. **Current FY only**: No historical backfill initially

## Schema Design

### `budget_items` Table

```sql
CREATE TABLE budget_items (
    id TEXT PRIMARY KEY,                    -- "san-rafael-fy2526-general-fund-police"
    jurisdiction_id TEXT NOT NULL,          -- FK to city_states
    fiscal_year TEXT NOT NULL,              -- "2025-2026"
    level TEXT NOT NULL,                    -- "federal" | "state" | "county" | "municipal"

    -- Categorization
    fund TEXT NOT NULL,                     -- "General Fund", "Enterprise", "Capital"
    department TEXT,                        -- "Police", "Community Development"
    program TEXT,                           -- "Homelessness Services"
    line_item TEXT,                         -- Full line item name from budget doc

    -- Amounts (cents for precision, no floating point errors)
    budgeted_cents INTEGER NOT NULL,        -- Appropriated amount
    revised_cents INTEGER,                  -- Mid-year revisions if applicable
    actual_cents INTEGER,                   -- Actual spend (when available)

    -- Context
    source_url TEXT NOT NULL,               -- PDF or data source URL
    source_page INTEGER,                    -- Page number in PDF for verification
    notes TEXT,                             -- Special conditions, caveats

    -- Temporal versioning (standard Civic pattern)
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_from TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_to TIMESTAMP,

    FOREIGN KEY (jurisdiction_id) REFERENCES city_states(jurisdiction_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- Indexes for common queries
CREATE INDEX idx_budget_jurisdiction_fy ON budget_items(jurisdiction_id, fiscal_year);
CREATE INDEX idx_budget_department ON budget_items(department);
CREATE INDEX idx_budget_fund ON budget_items(fund);
CREATE INDEX idx_budget_amount ON budget_items(budgeted_cents);
```

### ID Format

`{jurisdiction}-fy{year}-{fund-slug}-{department-slug}`

Examples:
- `san-rafael-fy2526-general-fund-police`
- `san-rafael-fy2526-enterprise-water`
- `san-rafael-fy2526-capital-parks-improvement`

### Amount Storage

All amounts stored in **cents** (integer) to avoid floating-point precision issues:
- `$1,234,567.89` → `123456789` cents
- Enables exact arithmetic for sums, comparisons
- Display formatting handled at API layer

## Three-Track Extraction Strategy

### Track 1: Municipal Budget PDF (Primary)

**Source**: Annual budget document (PDF)
**Frequency**: Once per fiscal year
**Output**: ~50-150 line items per jurisdiction

#### Process

1. Download budget PDF from city website
2. Extract using AI (Claude/Gemini) with structured prompt
3. Validate against known totals
4. Load into `budget_items` table

#### San Rafael Example

Source: [cityofsanrafael.org/city-budget/](https://www.cityofsanrafael.org/city-budget/)

Typical structure:
```
FY 2025-26 Budget ($192M total)
├── General Fund (~$80M)
│   ├── Police: $28M
│   ├── Fire: $18M
│   ├── Community Development: $8M
│   ├── Public Works: $12M
│   └── ...
├── Enterprise Funds (~$45M)
│   ├── Water: $22M
│   ├── Sewer: $18M
│   └── Parking: $5M
└── Capital Projects (~$15M)
    ├── Streets/Roads: $8M
    ├── Parks: $4M
    └── Facilities: $3M
```

### Track 2: Per-Decision Financial (Improve Existing)

**Source**: Staff reports for agenda items
**Frequency**: Per meeting (continuous)
**Enhancement**: Populate currently-empty `financial_impact_cents` field

#### Current State

```python
# staff_report.py extracts text only
financial_impact: Optional[str] = "$8 MILLION"

# agenda_items table has field but rarely populated
financial_impact_cents: Optional[int] = None  # Usually NULL
```

#### Target State

```python
# Enhanced extraction
@dataclass
class FinancialImpact:
    amount_cents: int                # 8_000_000_00 (cents)
    impact_type: str                 # "one-time" | "recurring" | "multi-year"
    fund_source: Optional[str]       # "General Fund", "Grant", "Enterprise"
    fiscal_years: list[str]          # ["2025-2026", "2026-2027"]
```

### Track 3: Federal/State Pass-Through (API)

**Source**: USASpending.gov, state transparency portals
**Frequency**: Annual or on-demand
**Output**: Federal grants, state allocations flowing to jurisdiction

#### USASpending.gov API

Free, no API key required:

```python
# Example: Find federal funding to San Rafael
GET https://api.usaspending.gov/api/v2/search/spending_by_award/
{
    "filters": {
        "recipient_locations": [
            {"country": "USA", "state": "CA", "city": "San Rafael"}
        ],
        "time_period": [
            {"start_date": "2024-10-01", "end_date": "2025-09-30"}
        ]
    },
    "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"]
}
```

Returns: CDBG grants, HUD funding, EPA grants, DOT allocations, etc.

## AI-Assisted ETL Template

For open-source scalability, we provide extraction templates that any contributor can use.

### Extraction Prompt Template

```markdown
# Municipal Budget Extraction

## Context
You are extracting structured budget data from a municipal budget document.

## Input
- Municipality: {municipality}
- State: {state}
- Fiscal Year: {fiscal_year}
- Document: [Attached PDF or text]

## Output Schema
Extract budget line items as JSON:

```json
{
  "jurisdiction_id": "city-{municipality-slug}",
  "fiscal_year": "{fiscal_year}",
  "source_url": "[document URL]",
  "items": [
    {
      "fund": "General Fund",
      "department": "Police",
      "program": null,
      "line_item": "Police Department",
      "budgeted_cents": 2800000000,
      "source_page": 45,
      "notes": null
    }
  ],
  "totals": {
    "general_fund": 8000000000,
    "enterprise_funds": 4500000000,
    "capital_projects": 1500000000,
    "total": 19200000000
  }
}
```

## Guidelines
1. Store amounts in **cents** (multiply dollars by 100)
2. Use fund/department names **exactly as shown** in document
3. Include **page numbers** for verification
4. Add **notes** for items with caveats or special conditions
5. Extract **line-item detail** where available, not just department totals
6. Include **totals** section for validation
```

### Configuration File

Each jurisdiction can have a `budget_config.yaml`:

```yaml
# data/budget/municipal/san-rafael/budget_config.yaml

jurisdiction_id: "city-san-rafael"
state: "California"

# Known budget documents
budget_documents:
  fy2526:
    url: "https://www.cityofsanrafael.org/documents/fy-2025-26-budget.pdf"
    published: "2025-06-15"
    total_budget_cents: 19228243800  # For validation

# Fund mappings (normalize variations)
fund_aliases:
  "General Fund": ["GF", "General"]
  "Enterprise - Water": ["Water Fund", "Water Enterprise"]
  "Enterprise - Sewer": ["Sewer Fund", "Sanitary Sewer"]

# Department mappings
department_aliases:
  "Police": ["Police Department", "PD", "Law Enforcement"]
  "Fire": ["Fire Department", "FD", "Fire Services"]

# Skip these (not budget line items)
exclude_patterns:
  - "Table of Contents"
  - "Organizational Chart"
  - "Budget Message"
```

## CLI Commands

```bash
# Extract budget from PDF (AI-assisted)
civic-extract budget \
  --jurisdiction city-san-rafael \
  --fy 2025-2026 \
  --source path/to/budget.pdf \
  --output data/budget/municipal/san-rafael/

# Validate extraction against totals
civic-extract budget --validate \
  --jurisdiction city-san-rafael \
  --fy 2025-2026

# Export empty template for manual extraction
civic-extract budget --template \
  --jurisdiction city-san-rafael \
  --fy 2025-2026 \
  > budget_template.json

# Load extracted JSON into database
civic-extract budget --load \
  --jurisdiction city-san-rafael \
  --input data/budget/municipal/san-rafael/fy2526.json
```

## Query API

### New `Civic.budget()` Method

```python
from civicos import CivicOS

c = CivicOS("san-rafael")

# Get all budget items for current FY
items = c.budget()

# Filter by topic (semantic match to departments/programs)
housing_budget = c.budget("housing")
# Returns: Community Development, Housing Authority, etc.

# Filter by department
police_budget = c.budget(department="Police")

# Filter by amount threshold
large_items = c.budget(min_amount=1_000_000)  # $1M+

# Filter by fund
enterprise = c.budget(fund="Enterprise")
```

### Integration with `what_applies()`

```python
# Enhanced regulatory context includes budget
result = c.what_applies("housing")

result.federal   # Federal laws/programs
result.state     # State laws
result.local     # Local ordinances
result.budget    # NEW: Relevant budget allocations

# Example budget context:
# [
#   {"department": "Community Development", "budgeted": 8_000_000, "fy": "2025-2026"},
#   {"program": "Below Market Rate Housing", "budgeted": 2_500_000, "fy": "2025-2026"},
# ]
```

## Data Directory Structure

```
data/budget/
├── municipal/
│   └── san-rafael/
│       ├── budget_config.yaml      # Configuration
│       ├── fy2526.json             # Extracted budget data
│       ├── fy2526_extraction.log   # AI extraction audit
│       └── fy2526_validation.json  # Validation results
├── county/
│   └── marin/
│       └── ...
├── state/
│   └── california/
│       └── ...                     # State allocations to localities
└── federal/
    └── usaspending/
        └── san-rafael-fy2025.json  # Federal grants
```

## Validation

### Extraction Validation

```python
def validate_budget_extraction(jurisdiction_id: str, fiscal_year: str) -> ValidationResult:
    """Validate extracted budget against known totals."""

    config = load_budget_config(jurisdiction_id)
    items = load_budget_items(jurisdiction_id, fiscal_year)

    # Sum by fund
    fund_totals = {}
    for item in items:
        fund_totals[item.fund] = fund_totals.get(item.fund, 0) + item.budgeted_cents

    # Compare to expected
    expected = config.budget_documents[fiscal_year].total_budget_cents
    actual = sum(fund_totals.values())

    variance = abs(actual - expected) / expected

    return ValidationResult(
        valid=variance < 0.01,  # Within 1%
        expected_cents=expected,
        actual_cents=actual,
        variance_pct=variance * 100,
        fund_breakdown=fund_totals,
    )
```

### Database Constraints

- `budgeted_cents` must be non-negative
- `fiscal_year` format validated (YYYY-YYYY)
- `jurisdiction_id` must exist in `city_states`
- Sum of line items should match fund totals (warning, not error)

## Implementation Phases

### Phase 1: Schema + Manual Extraction (This Sprint)
- Add `budget_items` table to backends
- Manually extract San Rafael FY 2025-26 budget
- ~2 hours total

### Phase 2: CLI + Templates (Next Sprint)
- `civic-extract budget` command
- AI extraction prompt templates
- Validation tooling

### Phase 3: API Integration (Future)
- `Civic.budget()` method
- `what_applies()` budget context
- USASpending.gov integration

## Open Source Contribution Guide

### Adding a New Jurisdiction's Budget

1. **Create config file**:
   ```bash
   mkdir -p data/budget/municipal/{city-slug}
   cp templates/budget_config.yaml data/budget/municipal/{city-slug}/
   ```

2. **Find budget document**:
   - Check city website for annual budget PDF
   - Note the fiscal year and total budget

3. **Extract using template**:
   - Use the AI extraction prompt with your preferred LLM
   - Save output to `data/budget/municipal/{city-slug}/fy{YYNN}.json`

4. **Validate**:
   ```bash
   civic-extract budget --validate --jurisdiction city-{slug}
   ```

5. **Submit PR**:
   - Include config file, extracted JSON, and validation results
   - Note any anomalies or special fund structures

## Related Documentation

- [EXTRACTOR_PROTOCOL.md](./EXTRACTOR_PROTOCOL.md) - General extraction patterns
- [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) - Data model definitions
- [docs/critical/FINAL_PACKAGE_ARCHITECTURE.md](./critical/FINAL_PACKAGE_ARCHITECTURE.md) - Package structure
