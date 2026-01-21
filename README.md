# CivicOS

**An open infrastructure for local civic intelligence.**

CivicOS aggregates public civic data—meetings, decisions, municipal code, complaints, budgets, legislation—into a queryable system that helps residents, staff, and organizers understand what's happening in local government and how to participate effectively.

## Status: Pilot (Jan 2026)

This is an active pilot focused on **San Rafael, California**. The infrastructure is designed to be replicable to other jurisdictions, but we're validating the core thesis with one city first.

**What we're testing:** Can structured civic data + AI assistance meaningfully increase resident participation in local decisions?

## Try It Now

CivicOS works through AI assistants you already use. No app to download.

**Claude (claude.ai or Claude Desktop):**
1. Go to Settings → Connectors → Add Connector
2. Enter: `https://civicos-mcp.fly.dev/mcp`
3. Ask: *"What's on the San Rafael city council agenda?"*

**ChatGPT (Plus/Team with developer mode):**
1. Settings → Connectors → Enable developer mode
2. Add connector: `https://civicos-mcp.fly.dev/mcp`
3. Ask: *"What has San Rafael decided about housing?"*

**New to this?** Once connected, just say **"get started"** and the assistant will walk you through what you can ask.

### Example Questions

| You | CivicOS can answer |
|-----|-------------------|
| *"What's happening with the downtown parking garage?"* | Upcoming agenda items, past decisions, related complaints |
| *"Who else is concerned about traffic on Lincoln Ave?"* | Neighbors who filed similar 311 complaints |
| *"What did people say about homelessness at the last meeting?"* | Public testimony from transcripts |
| *"Help me prepare to speak at Monday's meeting"* | Relevant context, past decisions, talking points |
| *"How do I submit a public comment?"* | Email address, deadlines, tips for effective comments |

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│              How People Access CivicOS                          │
│                                                                 │
│   "What's on the         ┌─────────────┐                       │
│    city council    ────► │ Claude.ai   │ ──┐                   │
│    agenda?"              └─────────────┘   │                   │
│                          ┌─────────────┐   │   ┌─────────────┐ │
│                          │ ChatGPT     │ ──┼──►│ MCP Server  │ │
│                          └─────────────┘   │   │ (25 tools)  │ │
│                          ┌─────────────┐   │   └──────┬──────┘ │
│                          │ Claude App  │ ──┘          │        │
│                          └─────────────┘              ▼        │
│                                              ┌─────────────┐   │
│                          ┌─────────────┐     │ CivicOS     │   │
│   civicos.app      ────► │ Web App     │ ───►│ Core        │   │
│                          └─────────────┘     └──────┬──────┘   │
│                                                     │          │
│                                                     ▼          │
│                                              ┌─────────────┐   │
│                                              │ Civic Data  │   │
│                                              │ (PostgreSQL │   │
│                                              │  + vectors) │   │
│                                              └─────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Why AI assistants?** Most people won't download a civic engagement app. But millions already use Claude and ChatGPT daily. CivicOS meets people where they are.

## San Rafael Pilot Data

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | 98 | Legistar API (Oct 2025 - Jan 2026) |
| Decisions | 44 | Extracted from meeting minutes |
| Transcripts | 29 | YouTube audio → AssemblyAI |
| Municipal Code | 16,175 sections | Municode |
| 311 Complaints | 1,730 | SeeClickFix API |
| Budget Items | 58 | FY25-26 adopted budget ($180M) |
| State Legislation | 17,719 | LegiScan API |
| Federal Programs | 22 | HUD, EPA, DOT programs |
| Executive Orders | 1,506 | Federal Register |

All data is indexed for semantic search (~17K vector embeddings).

## Design Principles

**1. Data sovereignty** — All civic data is public record. We aggregate, we don't create walled gardens.

**2. Jurisdictions first** — Infrastructure is designed around jurisdictions (cities, counties, school districts), not arbitrary regions.

**3. Sustainable, not cheap** — Real infrastructure costs real money. We're transparent about costs and fund through appropriate channels (foundations, municipal partnerships), not VC.

**4. AI as leverage, not replacement** — LLMs help surface relevant information and draft responses. Humans decide what to do with it.

**5. Replicable** — Adding a new city should be configuration, not code. (We're not there yet, but that's the goal.)

## What This Isn't

- **Not optimizing for engagement** — No feeds, likes, or algorithmic amplification. Success is measured in decisions influenced, not time-on-app.
- **Not a replacement for showing up** — The goal is to make participation more effective, not to automate democracy away.
- **Not complete** — This is a pilot. Things will break. Data will have gaps.

---

## For Developers

### Project Structure

```
civicos/
├── packages/civicos/             # Core query API
├── packages/civicos-extraction/  # Data parsers (Legistar, SeeClickFix, municipal code, etc.)
├── packages/civicos-services/    # REST API, WebSocket server, LLM routing
├── apps/civicos-workspace/       # Vue frontend
└── apps/civicos-mcp/             # MCP server (primary distribution)
```

### Core API

```python
from civicos import CivicOS

c = CivicOS("city-san-rafael")

c.whats_next()                      # Upcoming meetings with agendas
c.what_happened("housing")          # Past decisions on a topic
c.what_applies("ADU")               # Municipal code + state/federal law
c.whos_with_me("traffic on 4th")    # Neighbors with similar complaints
c.prepare(meeting_id="...")         # Background, context, talking points
```

### Running Locally

```bash
# Clone and setup
git clone https://github.com/lounsburynw/civicos.git
cd civicos
python3 -m venv civicos-env
source civicos-env/bin/activate
pip install -e packages/civicos
pip install -e packages/civicos-extraction
pip install -e packages/civicos-services

# Copy environment template
cp .env.example .env
# Add your API keys (OpenAI, Google Maps, etc.)

# Run verification
./init.sh

# Start the development servers
./scripts/dev.sh
```

The app runs at `http://localhost:5173` (frontend) with API at `:8001`.

### MCP Server

The MCP server (`apps/civicos-mcp/`) exposes 25 tools for AI assistants:

| Category | Tools |
|----------|-------|
| **Search** | `search_meeting_history`, `search_regulatory_stack`, `search_agenda_packets`, `find_similar_issues` |
| **Query** | `get_upcoming_meetings`, `get_public_testimony`, `get_voting_record`, `get_decision_context` |
| **311 Analysis** | `get_issue_analytics`, `query_issue_data`, `get_issue_sample`, `detect_trends`, `get_seasonal_patterns` |
| **311 Geo/Reports** | `find_issues_near_address`, `compare_zip_codes`, `generate_neighborhood_report` |
| **311 Accountability** | `get_issue_resolution_stats`, `find_repeat_issues` |
| **Budget** | `search_budget`, `get_funding_flow`, `get_federal_expenditures`, `get_intergovernmental_revenue` |
| **Action** | `compose_public_comment`, `prepare_for_meeting`, `get_comment_template` |
| **Onboarding** | `get_started` — returns example questions tailored to user type |

```bash
# Run MCP server locally (stdio for Claude Desktop)
python apps/civicos-mcp/civicos_server.py

# Run with HTTP transport (for Claude.ai, ChatGPT)
python apps/civicos-mcp/civicos_server.py -t http -p 8080
```

### Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Distribution Layer                        │
│   MCP Server (Claude, ChatGPT) │ REST API │ Vue Frontend    │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      CivicOS Core                           │
│   whats_next() │ what_happened() │ what_applies()           │
│   whos_with_me() │ prepare() │ coordinate()                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                            │
│   PostgreSQL (Supabase) │ pgvector │ Cloudflare R2 (PDFs)   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Ingestion Pipeline                        │
│   Modal (serverless compute) │ Scheduled refreshes          │
│   Legistar │ SeeClickFix │ Municode │ YouTube │ LegiScan    │
└─────────────────────────────────────────────────────────────┘
```

### Operating Costs

Real operational costs for an active jurisdiction:

| Service | Monthly Cost | What It Does |
|---------|-------------|--------------|
| Supabase | $25-50 | PostgreSQL + pgvector |
| AssemblyAI | $50-150 | Meeting transcription (~$0.37/min) |
| Modal | $20-50 | Serverless compute for pipelines |
| AI providers | $30-100 | Embeddings, extraction, LLM calls |
| Fly.io | $5 | MCP + API hosting |
| **Total** | **$150-350/mo** | Per active jurisdiction |

Costs scale sub-linearly with additional cities (shared infrastructure, bulk discounts).

### Extending to Other Cities

The extraction layer supports multiple platforms:

| Platform | Cities Using It | Status |
|----------|----------------|--------|
| Legistar API | Oakland, Berkeley, SF, many more | Working |
| CivicClerk API | Various | Working |
| Granicus | Various | Working |
| SeeClickFix | Any city on platform | Working |
| Municode | Most CA cities | Working |

To add a city, create a config in `data/extraction/{city-name}.json`. See `docs/user_guides/CITY_ONBOARDING_GUIDE.md`.

## Contributing

We're focused on the San Rafael pilot through Q1 2026. If you're interested in contributing or replicating for another city, open an issue.

Development workflow is documented in `CLAUDE.md`.

## License

**Source-available under [PolyForm Noncommercial 1.0.0](LICENSE.md)**

- **Individuals, nonprofits, academic institutions**: Free to use, modify, and share
- **For-profit companies**: Commercial license required

This structure keeps civic infrastructure accessible to residents and community organizations while ensuring companies that build on this work contribute to its sustainability. See [LICENSE.md](LICENSE.md) for details.
