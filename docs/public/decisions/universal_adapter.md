# ADR: Universal Adapter for Municipal Data Extraction

**Status:** Accepted
**Date:** 2026-03-13

## Decision

Introduce a **declarative extraction config** interpreted by a generic `UniversalExtractor` client. An LLM generates the config at onboard time by inspecting sample HTML; extraction itself is deterministic — no LLM calls at runtime. Platform-specific clients remain for platforms with stable APIs (Legistar, CivicClerk, eScribe). The universal adapter targets HTML-rendered platforms that lack APIs: custom municipal sites, Simbli variants, and the long tail.

## Context

CivicOS has 6 platform-specific extraction clients covering the major meeting platforms:

| Client | Approach | Stability |
|--------|----------|-----------|
| Legistar | REST API (OData) | High — structured API |
| CivicClerk | REST API (OData) | High — structured API |
| eScribe | JSON API (AJAX) | High — structured API |
| Granicus | HTML scraping + LLM column map | Medium — LLM generates config once |
| Simbli | Playwright + hardcoded regex/CSS | Low — brittle to DOM changes |
| ProudCity | HTML scraping (bespoke) | Medium — custom selectors |

**The problem:** Adding a new platform requires writing a new client class. Major cities like NYC run custom platforms. Simbli's regex-based parsing breaks across districts. We need a way to onboard arbitrary HTML-based meeting pages without writing bespoke code each time.

**Existing proof of concept:** Granicus's `generate_column_map()` already uses an LLM to infer table structure from sample HTML, then extracts deterministically using the inferred mapping. The universal adapter generalizes this pattern beyond tables.

## Architecture

### Overview

```
┌─────────────────────────────────────────────────┐
│                   Onboard Time                   │
│                                                  │
│  URL → fetch HTML → LLM infers config → validate │
│         (Playwright)    (structured output)       │
│                          │                        │
│                          ▼                        │
│               ExtractionConfig.metadata           │
│               {                                   │
│                 "adapter": { ... }                │
│               }                                   │
└─────────────────────────────────────────────────┘
                       │
                       │  saved to data/extraction/{jurisdiction}.json
                       ▼
┌─────────────────────────────────────────────────┐
│                 Extraction Time                   │
│                                                  │
│  URL → fetch HTML → apply config → Meeting[]     │
│         (Playwright    (CSS selectors,            │
│          or requests)   date parsing,             │
│                         pagination)               │
│                                                  │
│  No LLM calls. Deterministic. Auditable.         │
└─────────────────────────────────────────────────┘
```

### Adapter Config Schema

The LLM generates a declarative config stored in `ExtractionConfig.metadata["adapter"]`:

```json
{
  "adapter": {
    "version": 1,
    "page_type": "table" | "list" | "card",
    "listing": {
      "url_template": "https://example.gov/meetings?page={page}",
      "container": "table.meetings-list",
      "row": "tbody tr",
      "fields": {
        "title": { "selector": "td:nth-child(1)", "extract": "text" },
        "date": { "selector": "td:nth-child(2)", "extract": "text", "date_format": "%B %d, %Y" },
        "time": { "selector": "td:nth-child(3)", "extract": "text" },
        "agenda_url": { "selector": "td:nth-child(4) a", "extract": "href" },
        "minutes_url": { "selector": "td:nth-child(5) a", "extract": "href" },
        "video_url": { "selector": "td:nth-child(6) a", "extract": "href" }
      }
    },
    "pagination": {
      "type": "none" | "next_link" | "page_param" | "load_more",
      "next_selector": "a.next-page",
      "max_pages": 10
    },
    "detail": {
      "url_field": "agenda_url",
      "fields": {
        "title": { "selector": "h1", "extract": "text" },
        "time": { "selector": "time.datetime", "extract": "text" },
        "location": { "selector": "strong", "extract": "text" },
        "video_url": { "selector": "a[href*='youtube.com']", "extract": "href" }
      }
    },
    "requires_javascript": false,
    "provenance": {
      "sample_url": "https://example.gov/meetings",
      "sample_html_hash": "sha256:abc123...",
      "generated_at": "2026-03-13T10:00:00Z",
      "prompt_version": "universal_adapter/v2"
    }
  }
}
```

**Required fields:** `title` and `date` in the listing. All others optional.

**Two-level extraction:** Many municipal sites have thin listing pages (just links) with rich detail pages. The optional `detail` section tells the adapter to follow each listing link and extract additional fields (time, location, video). The LLM generates both configs at onboard time by sampling one listing page and one detail page. Extraction remains deterministic.

**`extract` modes:**
- `"text"` — `.get_text(strip=True)`
- `"href"` — `["href"]`, resolved to absolute URL
- `"attr:NAME"` — arbitrary attribute
- `"html"` — inner HTML (for rich content)

**`page_type` variants:**
- `"table"` — Standard HTML table (`container` is `<table>`, `row` is `<tr>`)
- `"list"` — `<ul>/<ol>` or `<div>` list (`container` is wrapper, `row` is list item)
- `"card"` — Repeated `<div>` cards (common in modern CMS platforms)

### UniversalExtractor Class

```python
class UniversalExtractor(BaseExtractor):
    """
    Generic extractor driven by a declarative adapter config.

    Does not contain platform-specific logic. All extraction behavior
    comes from the config generated at onboard time.
    """

    def __init__(self, jurisdiction_id: str, config: dict):
        super().__init__(jurisdiction_id)
        self.adapter = config  # The "adapter" dict from ExtractionConfig

    @property
    def platform_name(self) -> str:
        return "universal"

    def get_events(self, days_ahead=90, days_past=0):
        # 1. Fetch page(s) using url_template + pagination config
        # 2. Select container → rows using CSS selectors
        # 3. Extract fields per row using selector + extract mode
        # 4. Parse dates using date_format
        # 5. Filter by date range
        # 6. Return raw dicts
        ...

    def normalize_event(self, event):
        # Map extracted fields to Meeting dataclass
        ...
```

### LLM Config Generation (Onboard Time)

Extends the Granicus `generate_column_map()` pattern:

```python
def generate_adapter_config(url: str) -> dict:
    """
    Fetch a municipal meeting page and use LLM to infer extraction config.

    Returns adapter config dict with provenance.
    Raises RuntimeError if LLM cannot produce a valid config.
    """
    # 1. Fetch page (Playwright if JS-heavy, requests otherwise)
    html = fetch_page(url)

    # 2. Truncate to relevant section (largest table/list)
    sample = extract_sample(html, max_tokens=4000)

    # 3. Ask LLM to produce adapter config
    config = llm_infer_config(sample)

    # 4. Validate: required fields present, selectors parse, dates extract
    validate_adapter_config(config, html)

    # 5. Test extraction: run config against the sample page
    test_results = test_extract(config, html)
    if len(test_results) == 0:
        raise RuntimeError("Config produced 0 results on sample page")

    return config
```

**Validation steps (critical):**
1. JSON schema validation — all required fields, correct types
2. Selector validation — each CSS selector parses without error
3. Smoke extraction — run against the sample page, require ≥1 result
4. Date parsing — at least one extracted date parses with the given format
5. Title check — extracted titles are non-empty strings

If validation fails, the LLM is re-prompted once with the error. If it fails again, onboarding falls back to manual config or raises an error for human review.

### Integration with Factory

```python
# In factory.py
def create_source(config: ExtractionConfig) -> DataSource:
    if config.source_type == "legistar":
        return LegistarClient(...)
    elif config.source_type == "granicus":
        return GranicusSource(...)
    # ... existing platforms ...
    elif config.source_type == "universal":
        return UniversalExtractor(
            config.jurisdiction_id,
            config.metadata["adapter"]
        )
```

### Integration with Platform Detection

When existing platform detectors all return negative, the discovery chain falls through to:

```python
def _detect_universal(url: str) -> Optional[PlatformDetection]:
    """
    Last-resort detection: check if page has meeting-like content.

    Returns a detection with platform='universal' and lower confidence
    than specific platform detections.
    """
    # Heuristic: page contains date patterns + meeting-related keywords
    # Confidence: 0.30-0.50 (always lower than specific platform detections)
```

This ensures specific platforms are always preferred, with the universal adapter as a fallback.

## Failure Modes

The universal adapter must fail **explicitly**, never silently return 0 results.

### Detection: Config Drift

Meeting pages change over time — selectors break. Detection strategy:

| Signal | Meaning | Response |
|--------|---------|----------|
| 0 rows extracted | Selector completely broken | Raise `ExtractionError`, log alert |
| Row count drops >50% vs. last run | Partial breakage | Warn, return partial results with flag |
| Date parsing failures >30% | Format changed | Warn, return what parses, flag rest |
| HTTP error on listing URL | Page moved/removed | Raise `ExtractionError` |

### Mitigation: Health Checks

`UniversalExtractor.health()` runs the config against the live page and checks:
- Container selector matches ≥1 element
- Row selector matches ≥1 element within container
- At least 1 title and 1 date extract successfully

Failed health checks trigger re-generation of the adapter config (with human approval).

### Versus Current Silent Failures

Current Simbli behavior when selectors break:
```python
# Returns [] silently — indistinguishable from "no meetings scheduled"
meetings = simbli.get_events()  # len(meetings) == 0
```

Universal adapter behavior:
```python
# Raises with diagnostics
ExtractionError(
    "Container selector 'table.meetings-list' matched 0 elements. "
    "Page may have changed. Last successful: 2026-03-10. "
    "Re-run config generation or inspect page manually."
)
```

## Migration Path

### Phase 1: New Platforms (immediate)

Use the universal adapter for cities with no existing client. Portland OR is the first test case — it uses a custom layout at `portland.gov/council/agenda/all`.

### Phase 2: Simbli Migration (after validation)

Simbli is the first existing client to migrate:
1. Generate adapter config for SRCS Simbli instance
2. Run both old and new extractors in parallel, compare outputs
3. When output matches for 2+ weeks, switch to universal adapter
4. Delete Simbli-specific regex/selector code

### Phase 3: Other HTML Clients (as needed)

ProudCity and any other HTML-scraping clients can migrate if the universal adapter proves reliable. API-based clients (Legistar, CivicClerk, eScribe) stay as-is — they have stable, structured interfaces that don't benefit from this pattern.

## Rationale

### Why onboard-time LLM, not extraction-time?

| Factor | Onboard-time | Extraction-time |
|--------|-------------|-----------------|
| **Cost** | 1 LLM call per platform | 1 LLM call per extraction run |
| **Determinism** | Config is fixed, results reproducible | Results vary by LLM mood |
| **Latency** | Extraction is pure HTML parsing | Each run waits for LLM |
| **Auditability** | Config is inspectable JSON | Must log every LLM interaction |
| **Failure mode** | Config drift is detectable | Failures are intermittent |

Onboard-time wins on every axis. This matches the proven Granicus pattern.

### Why declarative config, not generated code?

Generated code (e.g., LLM writes a Python scraper) is harder to validate, harder to sandbox, and creates maintenance burden. A declarative config is:
- **Inspectable** — humans can read and fix it
- **Validatable** — JSON schema + smoke test
- **Sandboxed** — no arbitrary code execution
- **Versionable** — config changes are diffable

### Why keep platform-specific clients?

API-based platforms (Legistar, CivicClerk, eScribe) have stable, documented interfaces. A universal HTML scraper adds complexity without benefit for these. The universal adapter targets specifically:
- Platforms with no API (HTML-only)
- Platforms where the HTML structure varies across instances (Simbli)
- Custom municipal sites with no shared platform

## Alternatives Considered

### 1. LLM at Extraction Time (Adaptive Parsing)

Send each page to the LLM for parsing on every run. Rejected: expensive ($0.01-0.05 per page × hundreds of jurisdictions × daily runs), non-deterministic, high latency.

### 2. Generated Python Scrapers

Have the LLM write a Python scraper class per platform. Rejected: arbitrary code execution risk, harder to validate than declarative config, maintenance burden when pages change.

### 3. Third-party Scraping Services (Firecrawl, Jina Reader)

Use external services for HTML-to-structured-data. Rejected: adds external dependency, cost per request, data leaves our infrastructure, less control over extraction quality.

### 4. One Bespoke Client Per City

Continue writing platform-specific clients. Rejected for the long tail: works for 6 platforms, does not scale to hundreds of custom municipal sites. Still the right choice for stable API platforms.

### 5. Community-Contributed Configs

Publish the config schema and let civic tech volunteers contribute configs for their cities. Not rejected — this is a future possibility enabled by the declarative config approach, but not part of initial implementation.

## Implementation Notes

- `UniversalExtractor` lives in `clients/universal.py`
- Config generation lives in `clients/universal_config.py`
- Factory dispatch: `source_type == "universal"` → `UniversalExtractor`
- Playwright is used for JS-heavy pages (`requires_javascript: true`), `requests` otherwise
- Config schema validation uses `jsonschema` (already a dependency)
- Provenance tracking follows the Granicus pattern: sample HTML hash, prompt version, raw LLM response

## References

- `clients/granicus.py:108-221` — Existing LLM config generation pattern
- `clients/simbli.py` — Brittle extraction to migrate
- `clients/base.py:413-468` — BaseExtractor interface
- [Granicus column map prompt](../../../packages/civicos-extraction/src/civicos_extraction/clients/granicus.py) — Lines 161-175
