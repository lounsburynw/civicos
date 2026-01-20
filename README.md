# CivicOS

**An open infrastructure for local civic intelligence.**

CivicOS aggregates public civic data—meetings, decisions, municipal code, complaints, budgets, legislation—into a queryable system that helps residents, staff, and organizers understand what's happening in local government and how to participate effectively.

## Status: Pilot (Jan 2026)

This is an active pilot focused on **San Rafael, California**. The infrastructure is designed to be replicable to other jurisdictions, but we're validating the core thesis with one city first.

**What we're testing:** Can structured civic data + AI assistance meaningfully increase resident participation in local decisions?

## What's in the box

```
civicos/
├── packages/civicos/          # Core query API
├── packages/civicos-extraction/  # Data parsers (Legistar, SeeClickFix, municipal code, etc.)
├── packages/civicos-services/    # REST API, WebSocket server, LLM routing
├── apps/civicos-workspace/       # Vue frontend
└── apps/civicos-mcp/             # MCP server for Claude Desktop / AI assistants
```

## Core API

```python
from civicos import CivicOS

c = CivicOS("city-san-rafael")

# What's coming up?
c.whats_next()  # Upcoming meetings with agendas

# What happened?
c.what_happened("housing")  # Past decisions on a topic

# What law applies?
c.what_applies("ADU")  # Municipal code + state/federal law

# Who else cares about this?
c.whos_with_me("traffic on 4th street")  # Neighbors with similar complaints

# Prepare for a meeting
c.prepare(meeting_id="...")  # Background, relevant context, talking points
```

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

## Example Queries

**Resident:**
> "What's happening with the downtown parking garage project?"

**City Staff:**
> "Show me all public testimony about homelessness from the last 6 months"

**Organizer:**
> "Who complained about traffic on Lincoln Ave? Are any of them near the proposed bike lane?"

**Policy Researcher:**
> "What federal housing programs is San Rafael eligible for, and what's the application deadline?"

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Query Interface                         │
│   REST API │ MCP Server │ Vue Frontend │ CLI                │
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

## Running Locally

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

## Operating Costs

Real operational costs for an active jurisdiction (with transcription, embeddings, and scheduled ingestion):

| Service | Monthly Cost | What It Does |
|---------|-------------|--------------|
| Supabase | $25-50 | PostgreSQL + pgvector |
| AssemblyAI | $50-150 | Meeting transcription (~$0.37/min) |
| Modal | $20-50 | Serverless compute for pipelines |
| AI providers | $30-100 | Embeddings, extraction, LLM calls |
| Fly.io | $5 | API hosting |
| **Total** | **$150-350/mo** | Per active jurisdiction |

Costs scale sub-linearly with additional cities (shared infrastructure, bulk discounts).

## Design Principles

**1. Data sovereignty** — All civic data is public record. We aggregate, we don't create walled gardens.

**2. Jurisdictions first** — Infrastructure is designed around jurisdictions (cities, counties, school districts), not arbitrary regions.

**3. Sustainable, not cheap** — Real infrastructure costs real money. We're transparent about costs and fund through appropriate channels (foundations, municipal partnerships), not VC.

**4. AI as leverage, not replacement** — LLMs help surface relevant information and draft responses. Humans decide what to do with it.

**5. Replicable** — Adding a new city should be configuration, not code. (We're not there yet, but that's the goal.)

## Extending to Other Cities

The extraction layer supports multiple platforms:

| Platform | Cities Using It | Status |
|----------|----------------|--------|
| Legistar API | Oakland, Berkeley, SF, many more | Working |
| CivicClerk API | Various | Working |
| Granicus | Various | Working |
| SeeClickFix | Any city on platform | Working |
| Municode | Most CA cities | Working |

To add a city, create a config in `data/extraction/{city-name}.json`. See `docs/user_guides/CITY_ONBOARDING_GUIDE.md`.

## What This Isn't

- **Not optimizing for engagement** — No feeds, likes, or algorithmic amplification. Success is measured in decisions influenced, not time-on-app.
- **Not a replacement for showing up** — The goal is to make participation more effective, not to automate democracy away.
- **Not complete** — This is a pilot. Things will break. Data will have gaps.

## Contributing

We're focused on the San Rafael pilot through Q1 2026. If you're interested in contributing or replicating for another city, open an issue.

Development workflow is documented in `CLAUDE.md`.

## License

**Source-available under [PolyForm Noncommercial 1.0.0](LICENSE.md)**

- **Individuals, nonprofits, academic institutions**: Free to use, modify, and share
- **For-profit companies**: Commercial license required

This structure keeps civic infrastructure accessible to residents and community organizations while ensuring companies that build on this work contribute to its sustainability. See [LICENSE.md](LICENSE.md) for details.