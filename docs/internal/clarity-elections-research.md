# Clarity Elections Research — Non-Civera CA Counties

**Date:** 2026-03-30
**Item:** `non_civera_local_race_research`
**Status:** Research complete

## Executive Summary

9 of 58 CA counties have Clarity Elections ENR pages. Of these, 7 are net-new (2 overlap with Civera). Clarity provides XML/JSON election results with precinct-level detail including city councils, school boards, and ballot measures. However, the data is **ephemeral** — old elections can be purged at any time. A `clarify` Python library (MIT, by OpenElections) handles discovery and parsing. Building a client is feasible but lower-value than Civera due to ephemeral data and discovery complexity.

## Clarity Elections Overview

- **Platform:** Election Night Reporting (ENR) — hosted SPA for publishing real-time results
- **Owner:** COMITIA MSA (acquired Scytl in June 2024; Scytl acquired SOE Software in 2012)
- **URL pattern:** `results.enr.clarityelections.com/CA/{County}/{election_id}/{version}/`
- **NOT the same as CivicPlus** — completely separate companies

## CA Counties with Clarity (Probed 2026-03-30)

| County | Clarity | Civera | Net New? |
|--------|---------|--------|----------|
| Butte | Yes | No | **Yes** |
| Contra Costa | Yes | No | **Yes** |
| Madera | Yes | No | **Yes** |
| Marin | Yes | Yes | No (Civera is better) |
| Merced | Yes | No | **Yes** |
| Santa Clara | Yes | No | **Yes** |
| Shasta | Yes | No | **Yes** |
| Sonoma | Yes | Yes | No (Civera is better) |
| Ventura | Yes | No | **Yes** |

**7 net-new counties** would gain local race data from a Clarity client.

## Data Access (Verified)

### Working Endpoints

| Endpoint | Format | Purpose |
|----------|--------|---------|
| `/{eid}/current_ver.txt` | Text | Get current version string |
| `/{eid}/{ver}/json/en/summary.json` | JSON | Contest summary with vote totals |
| `/{eid}/{ver}/reports/detailxml.zip` | ZIP/XML | Full precinct-level results |
| `/{eid}/{ver}/reports/summary.zip` | ZIP | Summary data |

### Data Quality (Ventura Nov 2024 General)

- **99 contests** total (federal + state + local)
- **85 local races** including: city councils (Fillmore, Ojai, Oxnard, etc.), school boards, community college districts, ballot measures, water districts
- Precinct-level vote counts with voter turnout
- Candidate names and vote totals

### XML Schema

```xml
<ElectionResult>
  <ElectionName>E145 December 30, 2025 Runoff</ElectionName>
  <ElectionDate>12/17/2025</ElectionDate>
  <Region>Santa Clara</Region>
  <VoterTurnout totalVoters="1071024" ballotsCast="220541" voterTurnout="20.59">
    <Precincts>
      <Precinct name="0002001" totalVoters="68" ballotsCast="22" voterTurnout="32.35" />
    </Precincts>
  </VoterTurnout>
  <Contest text="Assessor" isQuestion="false">
    <Choice text="Neysa Fligor" totalVotes="123456">
      <VoteType name="Election Day" votes="45678" />
      <VoteType name="Vote by Mail" votes="77778" />
    </Choice>
  </Contest>
</ElectionResult>
```

## Critical Limitations

### 1. Ephemeral Data
- Ventura's Nov 2024 XML: **404** (already purged as of March 2026)
- Ventura's Nov 2024 JSON summary: **still available** (lighter resource, kept longer)
- Santa Clara's Dec 2025 runoff: **still available** (more recent)
- **Implication:** Must archive on first fetch. Cannot backfill historical data.

### 2. Election ID Discovery
- IDs are opaque integers (e.g., 125819), not sequential
- Landing pages are JS SPAs — no static election list
- `elections.json` endpoint returns **empty arrays** between election periods
- **Implication:** Need either the `clarify` library's page scraping or a maintained ID registry.

### 3. No Historical Archive
- Civera: permanent searchable archive back to 1997
- Clarity: current/recent elections only, actively purged
- **Implication:** Clarity is election-night-first, not a research platform. We can only capture data going forward.

## `clarify` Library Assessment

- **Package:** `pip install clarify` (MIT license)
- **Maintained by:** OpenElections project
- **Capabilities:** URL discovery, version tracking, XML parsing
- **API:**
  ```python
  import clarify
  j = clarify.Jurisdiction(url='https://results.enr.clarityelections.com/CA/Santa_Clara/125819/367736/', level='county')
  xml_url = j.report_url('xml')  # Get download URL
  p = clarify.Parser()
  p.parse("detail.xml")
  p.contests  # List of Contest objects
  p.results   # Vote counts per candidate per precinct
  ```
- **Limitation:** Handles parsing but not downloading. We'd still need download + archive logic.

## Comparison: Civera vs. Clarity

| Dimension | Civera ElectionStats | Clarity Elections |
|-----------|---------------------|-------------------|
| API | GraphQL, no auth | XML/JSON, no auth |
| Historical data | 1997-present, permanent | Current election only, purged |
| Discovery | Consistent `/api/graphql_pr` | Opaque IDs, JS SPA |
| CA counties | 4 | 9 (7 net-new) |
| Data granularity | Contest + candidate + precinct | Contest + candidate + precinct |
| Local races | Yes | Yes |
| Effort to build | Done | Moderate (~1-2 sessions) |
| Ongoing reliability | High (permanent archive) | Low (data disappears) |

## Remaining 49 CA Counties

Counties without Civera or Clarity have diverse, fragmented systems:

| Platform | Counties | Feasibility |
|----------|----------|-------------|
| Custom county websites | Alameda, Sacramento, San Francisco, Los Angeles, Orange, San Mateo, etc. | Per-county scraping (high effort) |
| Hart LiveVoterTurnout | San Diego, possibly other Hart counties | No API, JS/Mapbox (high effort) |
| PDF-only | Small/rural counties | OCR extraction (very high effort) |
| CA SOS API | All 58 (statewide races only) | Already implemented (no local races) |

**Key insight:** No single platform covers a large number of the remaining 49 counties. The cost-per-county is high for anything beyond Civera (4) and Clarity (7).

## Recommendations

### Build (recommended)

1. **Clarity client** (~1-2 sessions) — Covers 7 new counties with rich local race data. Use `clarify` library for parsing. Must implement archive-on-fetch since data is ephemeral.

2. **Clarity discovery script** (~0.5 session) — Similar to `probe_civera_counties.py`. Probe all 58 counties quarterly. Output to `data/extraction/clarity_instances.json`.

3. **Archive strategy** — On each election cycle:
   - Detect new election IDs (probe during election season: Oct-Dec)
   - Download XML immediately, store in R2
   - Parse and store in Postgres (same schema as Civera elections/contests)

### Defer

4. **Custom county scrapers** — Not cost-effective until Civera + Clarity are fully exploited. Per-county effort is 0.5-1 session each.

5. **Hart LiveVoterTurnout** — No API, would require headed Playwright. Only covers a few counties.

### Implementation Priority

| Step | Item | Sessions | Counties Added |
|------|------|----------|---------------|
| 1 | Clarity discovery script | 0.5 | — |
| 2 | Clarity extraction client | 1-2 | +7 (total 11) |
| 3 | Archive-on-fetch pipeline | 0.5 | — |
| **Total** | | **2-3** | **11/58 CA counties with local race data** |

After steps 1-3, local race coverage goes from 4/58 (7%) to 11/58 (19%) CA counties. The next 47 counties require per-county custom work with diminishing returns.
