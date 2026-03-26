# Election Data Source Research — Bay Area Focus

**Date:** 2026-03-25
**Scope:** Research only — audit existing infrastructure, survey external sources, recommend integration path

## Current State

### Existing Infrastructure (surprisingly complete)

| Component | Status | Notes |
|-----------|--------|-------|
| Google Civic client | **Working** (elections), **Broken** (representatives) | Representatives API turned down April 2025. Elections returns only 3 nationwide — no Bay Area local races. |
| Marin Registrar scraper | **Working** | Playwright-based, Cloudflare-aware. Scrapes election schedules. |
| Representatives client | **Working** | Congress.gov (federal) + LegiScan (state). Local officials manual. |
| Simbli client | **Working** | San Rafael City Schools ingested. 45 meetings in Postgres. |
| Election storage protocol | **Complete** | Temporal versioning. Elections, deadlines, contests, officials. |
| Postgres schema | **Complete** | All 4 tables with indexes. |
| Election data models | **Complete** | ElectionType, ContestType (includes LOCAL_SCHOOL_BOARD), Candidate, BallotMeasure |
| Modal ingestion | **Complete** | `fetch_elections()`, `fetch_elected_officials()`, `scheduled_election_refresh()` |
| GitHub Actions cron | **Deployed** | Monthly 1st at 3 AM UTC |
| Existing data | **6 elections, 45 school meetings** | In Postgres for san-rafael |

### Google Civic API — Confirmed Issues

Live test results (2026-03-25):
- **Elections endpoint**: Returns 200 but only 3 results nationwide (VIP Test Election, FL special, VA special). No Bay Area data.
- **Representatives endpoint**: Returns 200 with 0 officials. API was turned down April 30, 2025.
- **Conclusion**: Usable for polling locations during major election seasons, but NOT a reliable source for local election data.

## External Data Sources Evaluated

### Tier 1: Best Options (free, structured, local coverage)

#### Democracy Works Elections API ⭐ BEST FREE SOURCE
- **Data**: Election dates, registration deadlines, early voting, candidates, ballot measures, polling locations
- **Coverage**: Federal, state, county, municipal, school board for jurisdictions >5,000 pop
- **API**: REST v2 (`api.democracy.works/v2`), JSON
- **Cost**: **UNKNOWN — sales-gated.** No public free tier. Contact partnerships@democracy.works. Their 990 shows ~$3M/year in program revenue (TikTok, Nextdoor, Perplexity are customers). Nonprofits may get discounted/free access but no guarantee. The "$0" price in their schema.org markup is misleading SEO.
- **Local coverage**: Should cover San Rafael (pop ~62K), Marin County supervisors, likely school boards
- **Published**: 14,000+ elections, 300K+ voting locations in 2024
- **Action**: Email partnerships@democracy.works asking about nonprofit civic tech access. Do not build client until pricing confirmed.

#### California Secretary of State Results API
- **Data**: Real-time election night results, historical results for statewide races
- **API**: REST at `api.sos.ca.gov`, JSON/CSV, no auth required
- **Cost**: Free
- **Coverage**: Federal + state races with county-level breakdowns. Does NOT cover city council or school board.
- **Action**: Good for state-level races. Supplement with county registrar for local.
- **Technical details**: See [CA SOS API Reference](#ca-sos-api-reference) below.

#### Marin County Past Elections Database ⭐ BEST LOCAL SOURCE
- **Data**: Historical election results 2010-2025 — candidates, vote counts, ballot measures, precinct-level breakdowns
- **URL**: `pastelections.marincounty.gov`
- **Platform**: ElectionStats by Civera (Next.js frontend, Apollo GraphQL backend, tenant `marinca`)
- **API**: **GraphQL** at `POST /api/graphql_pr` — no auth required, fully public
- **Coverage**: ALL Marin elections — city council, school board, supervisors, water/fire districts, ballot measures
- **Data volume**: 46 elections, 521 candidate contests, 380 ballot questions, 1,404 candidates, 146 precincts
- **Action**: Build GraphQL client (not CSV scraper — CSV endpoint returns 404, GraphQL gives same data structured).
- **Technical details**: See [Marin Registrar GraphQL Reference](#marin-registrar-graphql-reference) below.

### Tier 2: Supplementary (free, narrower scope)

| Source | Data | Cost | Bay Area Coverage |
|--------|------|------|-------------------|
| OpenFEC | Federal campaign finance | Free, API key | CA-02 (Marin) only |
| OpenSecrets | Federal finance summaries | Free, API key | Federal races only |
| CA CAL-ACCESS | State campaign finance | Free, bulk download | State races, daily updates |
| Vote Smart | Candidate bios, voting records | Free API | Federal + state officials |
| U.S. Vote Foundation | Election admin data (dates, deadlines) | Free for states | Good admin data, not results |
| WeVote | Aggregated ballot previews | Free, open source | Depends on upstream sources |

### NOT Recommended

| Source | Reason |
|--------|--------|
| Ballotpedia API | $1000s/month — too expensive for foundation-funded project |
| BallotReady API | Enterprise pricing, opaque |
| Democracy Works | Sales-gated pricing, no public free tier. May revisit if nonprofit access confirmed. |
| Open States / Plural | Acquired by VC, flagged in project memory — do not use |
| Vote.org | No API exists |
| USA.gov / vote.gov | No API exists |

### Principle: Prefer Primary Government Sources

Civic data aggregator APIs (Ballotpedia, BallotReady, Democracy Works, CivicEngine) consistently use non-transparent pricing behind enterprise sales funnels. Even when marketed as "free," actual access requires sales qualification. This is a structural pattern across the civic data industry, not isolated to one provider.

**CivicOS strategy**: Build scrapers and clients against primary government sources (county registrar sites, secretary of state APIs, meeting platform portals). These are free, authoritative, and won't change access terms. The aggregators add convenience but introduce pricing risk and vendor dependency.

This same principle likely applies beyond elections — permits, zoning, budget data, etc. When evaluating any new civic data API, check for self-service signup first. If it says "contact sales," deprioritize.

## School Board Platforms — Marin County

### Platform Coverage

**Two scrapers would cover ~80% of Marin school districts:**

#### Simbli/eBOARDsolutions (CivicOS already has client ✅)

| District | Site ID | Status |
|----------|---------|--------|
| San Rafael City Schools | 36030430 | **Ingested** (45 meetings) |
| Novato Unified SD | 36030351 | Ready to ingest |
| Tamalpais Union HSD | 36030468 | Ready to ingest |
| Miller Creek SD (ex-Dixie) | AgendaOnline→Simbli | Ready |
| Mill Valley SD | AgendaOnline→Simbli | Ready |
| Reed Union SD (Tiburon) | AgendaOnline→Simbli | Ready |
| Kentfield SD | AgendaOnline→Simbli | Ready |

**Key discovery**: CSBA (California School Boards Association) merged AgendaOnline into GAMUT, which runs on Simbli. Many districts that used AgendaOnline are now on Simbli infrastructure.

#### BoardDocs (client complete, extraction configs ready)

| District | Edition | App Path |
|----------|---------|----------|
| Marin County Office of Education | LT | `ca/marinschools` |
| Ross Valley SD | Pro | `ca/rova` |
| Larkspur-Corte Madera SD | Pro | `ca/lcmsd` |
| Sausalito Marin City SD | Pro | `ca/smcsd` |
| Marin Community College | Pro | `ca/marin` |

**Scraping approach**: No official API, but undocumented POST endpoints work. LT and Pro editions use identical endpoints.
- **Technical details**: See [BoardDocs API Reference](#boarddocs-api-reference) below.

#### Small/Custom Districts (low priority)

| District | Platform |
|----------|----------|
| Shoreline Unified SD | Diligent Community (new) |
| Lagunitas SD | Diligent Community (new) |
| Bolinas-Stinson Union SD | Custom website + S3 PDFs |
| Nicasio SD | Custom (1 school, tiny) |
| Ross SD | Website + archived AgendaOnline |

## Integration Model Recommendations

### 1. Elections as a corpus within existing jurisdictions

Elections should NOT be separate jurisdictions. They belong to existing jurisdiction hierarchies:
- `city-san-rafael` gets city council elections
- `county-marin` gets supervisor + county-wide measure elections
- `school-san-rafael` gets school board elections
- `state-california` gets state proposition + legislative elections

This aligns with the existing `store_elections(jurisdiction_id, ...)` pattern.

### 2. School districts as jurisdictions

Already working — `school-san-rafael` exists with 45 meetings. Pattern:
- `school-{city}` for city-level school districts
- `school-{district-name}` for union/regional districts (e.g., `school-tamalpais-union`)

### 3. Auto-detection during onboarding

Election data sources don't need auto-detection (unlike meeting platforms). Instead:
- Meeting platforms are detected per-jurisdiction (Legistar, Granicus, Simbli, etc.)
- Election data comes from jurisdiction-level queries to Democracy Works / county registrar
- The `scheduled_election_refresh()` cron already handles this

### 4. Schema changes needed

None for elections — schema is complete. For BoardDocs school boards:
- Add `boarddocs` as a `source_type` in the client factory
- BoardDocs client config: `app_path` (e.g., `ca/rova`) + `committee_id`

## Recommended Implementation Plan

### Phase 1: Marin County Registrar — Historical Results (P0, unblocked)
- Build GraphQL client for `pastelections.marincounty.gov/api/graphql_pr` (not CSV — CSV endpoint is broken)
- Authoritative source for ALL Marin local races (city council, school board, supervisors, measures)
- Three-query pattern: list elections → list contests → get precinct-level data
- Store as election results/outcomes (may need to add `votes_received` to Candidate model)
- **Effort**: ~1 session

### Phase 2: BoardDocs Client (P1, unblocked)
- Build `BoardDocsClient` based on LlamaIndex reader patterns
- Register as `boarddocs` source type in factory
- Onboard MCOE, Ross Valley, Larkspur-Corte Madera, Sausalito-Marin City
- **Effort**: ~1-2 sessions

### Phase 3: CA SOS Results API (P1, unblocked)
- Wire `api.sos.ca.gov` for state-level race results with county breakdowns
- Free, no auth required. Covers propositions, state legislature, US Congress with Marin breakdowns.
- **Effort**: ~0.5 session

### Phase 4: Democracy Works Integration (P1, BLOCKED on pricing)
- **Status**: Sales-gated. No public free tier. Email partnerships@democracy.works to inquire about nonprofit civic tech access. Do not build until pricing is confirmed.
- If accessible: Build `DemocracyWorksClient`, map to existing election models, wire into `fetch_elections()`
- If too expensive: Skip — Marin Registrar + CA SOS + existing Google Civic cover most needs
- **Effort**: ~1 session (once unblocked)

### Phase 5: Expand Simbli Coverage (P2, unblocked)
- Onboard Novato, Tamalpais Union, Miller Creek, Mill Valley, Reed Union, Kentfield
- Existing Simbli client handles these — just need jurisdiction configs
- **Effort**: ~0.5 session (config-only)

## API Keys Status

| Source | Key | Status |
|--------|-----|--------|
| Google Civic | `GOOGLE_API_KEY` | ✅ Set (limited utility now) |
| Congress.gov | `CONGRESS_GOV_API_KEY` | ✅ Set |
| LegiScan | `LEGISCAN_API_KEY` | ✅ Set |
| Democracy Works | — | ❓ Sales-gated — email partnerships@democracy.works for nonprofit pricing |
| CA SOS | — | ✅ No auth required |
| Marin Registrar | — | ✅ No auth needed (scraping) |
| BoardDocs | — | ✅ No auth needed (scraping) |

---

## Technical References

### Marin Registrar GraphQL Reference

**Endpoint:** `POST https://pastelections.marincounty.gov/api/graphql_pr`
**Auth:** None required
**Platform:** ElectionStats by Civera (tenant: `marinca`)

#### Step 1: List Elections

```graphql
query {
  searchSuggestions(filters: {
    global: { years: { from: 2010, to: 2026 } }
    voterStats: false
    specialElectionsOnly: false
    stages: []
  }) {
    events { id name group count }
  }
}
```

Returns 46 elections (June 2010 – May 2025). Election types: General, Primary, Special, Special Vote By Mail, Local, Recall, Uniform District Election.

#### Step 2: List Contests for an Election

```graphql
query {
  search(filters: {
    global: { events: [35] }
    contests: { candidates: [], divisions: [], offices: [] }
    ballotQuestions: { text: "", types: [], number: "", divisions: [] }
    voterStats: false
    specialElectionsOnly: false
    stages: []
  }, pagination: { page: 1, size: 100 }) {
    results {
      id name
      office { id name }
      division { id displayName divisionType { name } }
      event { id startDate type { name } }
      candidates {
        displayName nVotes pctCandidateVotes
        candidate { pseudocandidate }
        isWinner
        party { name }
      }
      ballotQuestionId
      ballotQuestion { questionText type { name } questionNumber }
      nSeats hasWinners
    }
  }
}
```

Pagination is 1-indexed. Filter by `events` (array of event IDs) OR `years`, not both.

**Contest record fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique contest ID |
| `office.name` | string | "Mayor", "City Council Member", "School Board Member", etc. |
| `division.displayName` | string | "City of San Rafael", "Ross Valley School District", etc. |
| `division.divisionType.name` | string | City, School District, County, Water District, etc. |
| `event.startDate` | string | Election date |
| `event.type.name` | string | General, Primary, Special, etc. |
| `nSeats` | int | Number of seats in contest |
| `hasWinners` | bool | Whether winners have been determined |

**Candidate fields (within each contest):**

| Field | Type | Description |
|-------|------|-------------|
| `displayName` | string | Candidate name |
| `nVotes` | int | Vote count |
| `pctCandidateVotes` | float | Percentage of candidate votes |
| `isWinner` | bool | Whether candidate won |
| `party.name` | string | Party (null for nonpartisan races) |
| `candidate.pseudocandidate` | string/null | Null for real candidates. `"TOTAL_VOTES"`, `"TOTAL_BALLOTS"`, `"PSEUDOCANDIDATE"` (undervotes/overvotes), or `"VOTER_STAT"` for summary rows. |

**Ballot measure fields (when `ballotQuestionId` is set):**

| Field | Type | Description |
|-------|------|-------------|
| `ballotQuestion.questionText` | string | Full measure text |
| `ballotQuestion.type.name` | string | Measure type |
| `ballotQuestion.questionNumber` | string | Measure letter/number |

Yes/No votes appear as candidates with `displayName` = "Yes"/"No".

#### Step 3: Get Precinct-Level Data

```graphql
query {
  contestGranularData(
    contestId: 585
    voteChannels: true
    splitParty: false
  ) {
    candidates {
      candidateId
      candidate { id displayName pseudocandidate }
      nVotes pctCandidateVotes isWinner
      voteChannelId
    }
    voteChannels { id name }
    divisions {
      division { id name displayName divisionTypeName }
      granularRow { candidateId voteChannelId votes pct winner }
      children {
        division { id name displayName divisionTypeName }
        granularRow { candidateId voteChannelId votes pct winner }
      }
    }
  }
}
```

- 146 precincts county-wide; San Rafael has 29 precincts (10901-10919, 20915-20920, 40918-40921)
- Vote channels: Vote Center (id=5) and Vote By Mail (id=3); `voteChannelId=0` = combined
- One API call per contest for precinct data

#### Division Types (14 total)

Board of Education, City, City Council District, College District, Community Services District, Congressional District, County Supervisor District, Fire Protection District, Sanitary District, School District, State, State Assembly District, Town of, Water District

#### Data Volume

| Metric | Count |
|--------|-------|
| Elections | 46 (June 2010 – May 2025) |
| Candidate contests | 521 |
| Ballot questions | 380 |
| Unique candidates | 1,404 |
| Precincts (county-wide) | 146 |
| San Rafael precincts | 29 |

---

### BoardDocs API Reference

**Base URL:** `https://go.boarddocs.com/{state}/{site_code}/Board.nsf`
**Auth:** None required
**Platform:** IBM Lotus Domino

LT and Pro editions use identical API endpoints. All POST requests require:

```
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
```

#### Marin County Instances

| District | Site Code | Committee ID | Meetings |
|----------|-----------|-------------|----------|
| Ross Valley SD | `ca/rova` | `AB9A2R259AF0` | ~317 |
| Marin County OE | `ca/marinschools` | `A4EP6J588C05` | ~80 |
| Larkspur-Corte Madera SD | `ca/lcmsd` | `A4EP6J588C05` | ~120 |
| Sausalito Marin City SD | `ca/smcsd` | `A4EP6J588C05` | ~258 |
| Marin Community College | `ca/marin` | (needs discovery) | — |

#### Step 1: Discover Committee IDs

**GET** the main page (`/Public` or `/vpublic?open`) and parse HTML:

```html
<a class="dropdown-item committee-trigger" committeeid="AB9A2R259AF0">Main Governing Board</a>
```

No separate API endpoint for committee listing (`BD-GetCommitteesList` returns 404).

#### Step 2: List All Meetings

**POST** `/{base}/BD-GetMeetingsList?open`
**Body:** `current_committee_id={committee_id}`

Returns JSON array (no pagination — all meetings at once, back to 2017-2018):

```json
[
  {
    "unique": "DMYPDZ643003",
    "name": "RVSD BOARD OF TRUSTEES REGULAR MEETING",
    "current": "",
    "numberdate": "20251112",
    "unid": "BF1BDD46B5A4726985258D3400643003"
  },
  ...
  {}
]
```

| Field | Type | Description |
|-------|------|-------------|
| `unique` | string | Short ID — used as meeting identifier in all subsequent calls |
| `name` | string | Meeting title |
| `current` | string | `""` or `"0"` for past, `"1"` for current/featured |
| `numberdate` | string | Date as `YYYYMMDD` |
| `unid` | string | Domino document UNID (32-char hex) |

Array ends with empty object `{}` as sentinel.

#### Step 3: Get Full Agenda (Best Single Endpoint)

**POST** `/{base}/PRINT-AgendaDetailed`
**Body:** `id={meeting_unique}&current_committee_id={committee_id}`

Returns HTML containing all agenda items with full text and file attachment links:

```html
<div id="print-top-meeting-info">
  <div class="print-meeting-date">Wednesday, November 12, 2025</div>
  <div class="print-meeting-name">RVSD BOARD OF TRUSTEES REGULAR MEETING</div>
</div>

<!-- Per category: -->
<div style="font-weight: bold; font-size: 16px; border-bottom: 2px solid #000;">
  A. CALL TO ORDER
</div>

<!-- Per item: -->
<div class="container item agendaorder">
  <dl><dt>Subject</dt><dd>1. Meeting Called to Order</dd></dl>
  <dl><dt>Type</dt><dd>Procedural</dd></dl>
  <div class="itembody"><!-- Full HTML body --></div>
  <div class="print-files">
    <div class="public-file print-file" unique="DNCUY37E4547">
      <a href="/{base}/files/DNCUY37E4547/$file/Email%20re%20SB%20707.pdf">
        Email re SB 707.pdf (109 KB)
      </a>
    </div>
  </div>
</div>
```

Action types: `Procedural`, `Action`, `Action (Consent)`, `Discussion`, `Information`, `Presentation`, `Reports`, `Closed Session`

#### Other Endpoints

| Endpoint | Method | Body | Response | Purpose |
|----------|--------|------|----------|---------|
| `/BD-GetMeeting?open` | POST | `id={meeting_unique}` | HTML | Meeting overview |
| `/BD-GetAgenda?open` | POST | `id={meeting_unique}` | HTML | Agenda item list (structured `<dl>/<li>`) |
| `/BD-GetAgendaItem?open` | POST | `id={item_unique}` | HTML | Single item detail |
| `/files/{id}/$file/{filename}` | GET | — | Binary | Download attachment |
| `/goto?open&id={unique}` | GET | — | HTML | Deep link to meeting or item |

#### Recommended Scraping Strategy

1. **GET** main page → parse committee IDs
2. **POST** `BD-GetMeetingsList` → get all meetings (no pagination)
3. **POST** `PRINT-AgendaDetailed` per meeting → everything in one call
4. Parse HTML with BeautifulSoup → extract structured data
5. **GET** file URLs for PDF downloads

Reference implementation: `pip install llama-index-readers-boarddocs`

---

### CA SOS API Reference

**Base URL:** `https://api.sos.ca.gov`
**Auth:** None required (behind AWS API Gateway + Imperva CDN)
**Output:** JSON (default) or CSV (append `?f=csv`)

#### Key Limitation

**No historical election access.** The API only serves the current/most-recent election(s). Data is overwritten when a new election is loaded. There is no date parameter or election ID selector.

Use `reportType` to distinguish: `"R"` = preliminary (election night), `"U"` = certified final.

#### Endpoints

**Statewide races:**

```
GET /returns/president
GET /returns/us-senate
GET /returns/governor
GET /returns/lieutenant-governor
GET /returns/secretary-of-state
GET /returns/controller
GET /returns/treasurer
GET /returns/attorney-general
GET /returns/insurance-commissioner
GET /returns/superintendent-of-public-instruction
```

**District races:**

```
GET /returns/us-rep/district/{N}              # N=1-52
GET /returns/state-senate/district/{N}        # N=1-40
GET /returns/state-assembly/district/{N}      # N=1-80
GET /returns/board-of-equalization/district/{N}  # N=1-4
```

**Ballot measures:**

```
GET /returns/ballot-measures                  # All measures, statewide totals
GET /returns/ballot-measures/prop/{N}         # Single proposition
```

**County breakdowns** — append `/county/{slug}` to any race endpoint:

```
GET /returns/president/county/marin
GET /returns/us-rep/district/2/county/marin
GET /returns/ballot-measures/county/marin
GET /returns/state-assembly/district/12/county/marin
```

**Status/reporting:**

```
GET /returns/status                           # All counties reporting status
GET /returns/status/general
GET /returns/status/state-special
GET /returns/status/primary
```

**Batch query** (max 10 contest IDs):

```
GET /returns/query?r=["01000000000059","19000000005059"]
```

#### Response Schemas

**Candidate race (statewide):**

```json
{
  "raceTitle": "U.S. House of Representatives District 2 - Statewide Results",
  "Reporting": "34.7% (10,492 of 30,238) precincts reporting",
  "ReportingTime": "September 16, 2024, 9:38 a.m.",
  "candidates": [
    {
      "Name": "Jared Huffman",
      "Party": "Dem",
      "Votes": "23,772",
      "Percent": "52.5",
      "incumbent": true
    }
  ]
}
```

County requests return an array of two objects: `[county_results, districtwide_results]`.

**Ballot measures:**

```json
{
  "raceTitle": "Ballot Measures - Statewide Results",
  "Reporting": "100.0% (18,399 of 18,399) precincts reporting",
  "ReportingTime": "December 5, 2025, 1:45 p.m.",
  "ballot-measures": [
    {
      "Name": "Congressional Redistricting",
      "Number": "50",
      "yesVotes": "7453339",
      "yesPercent": "64.4",
      "noVotes": "4116998",
      "noPercent": "35.6"
    }
  ]
}
```

**Data type gotcha:** All values are strings. Candidate `Votes` are comma-formatted (`"2,909,979"`), ballot measure votes are not (`"7453339"`).

**County status:**

```json
{
  "marin": {
    "county": 21,
    "reportType": "U",
    "precinctsReporting": "58",
    "precinctsTotal": "58",
    "precinctsReportingPercent": "100.0",
    "voterTurnout": "118495",
    "totalRegisteredVoters": "173896",
    "voterTurnoutPercentage": "68.1",
    "countyName": "Marin",
    "timestamp": "December 2, 2025, 10:32 a.m."
  }
}
```

#### Marin County Details

| Field | Value |
|-------|-------|
| County code | 21 |
| URL slug | `marin` |
| US House District | 2 (Jared Huffman) |
| State Assembly District | 12 (Damon Connolly) |
| State Senate District | 2 (Mike McGuire) |
| Precincts | 58 (in status) / 146 (in registrar granular data) |

#### County Slug Format

Lowercase, hyphens for multi-word: `marin`, `contra-costa`, `san-francisco`, `los-angeles`, `el-dorado`, `san-luis-obispo`
