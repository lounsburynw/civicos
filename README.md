<p align="center">
  <img src="assets/logo-light.svg" alt="CivicOS" width="240">
</p>

# CivicOS

**Ask questions about your local government—and find others who care.**

Open civic infrastructure for AI agents. Query meetings, decisions, budgets, and municipal code. Express stances on agenda items. Coordinate across city, county, and state. No app, no lock-in.

> **Status:** Stable; not actively maintained since ~March 2026. Published as a reference / portfolio project.

## Contents

- [Try It Now](#try-it-now)
- [How It Works](#how-it-works)
- [Design Principles](#design-principles)
- [For Developers](#for-developers)
- [Add Your City](#add-your-city)
- [For Cities](#for-cities)
- [Contributing](#contributing)

---

## Try It Now

### Browser Extension (Primary)

Install the Chrome extension for a full civic dashboard:

1. Clone and build: `cd apps/civicos-extension && npm install && npm run build`
2. Go to `chrome://extensions` → Enable Developer mode
3. Click **Load unpacked** → select `apps/civicos-extension/dist`
4. Click the CivicOS icon → **Open City Pulse**

You'll see upcoming meetings, recent decisions, community issues on a map, budget breakdowns, and relevant legislation. Express support/oppose/watching on any agenda item.

**Full guide:** [Extension Setup](docs/public/extension/setup.md)

### MCP Server (AI Assistants)

Connect Claude, ChatGPT, or any MCP-compatible client to 40+ civic data tools.

**Claude (claude.ai or Claude Desktop):**
1. Go to Settings → Connectors → Add Connector
2. Enter: `https://san-rafael.civicosproject.org/mcp`
3. Ask: *"What's on the San Rafael city council agenda?"*

**ChatGPT (Plus/Team with developer mode):**
1. Settings → Connectors → Enable developer mode
2. Add connector: `https://san-rafael.civicosproject.org/mcp`
3. Ask: *"What has San Rafael decided about housing?"*

**New to this?** Once connected, say **"get started"** and the agent will walk you through what you can ask.

**Full guide:** [MCP Setup](docs/public/mcp/setup.md)

---

## How It Works

```
Browser Extension (Svelte)  /  AI Agent (via MCP)
    ├── civicos-components (UI)
    └── civicos-client (TypeScript)
              |
         ┌────┴────┐
         v         v
    REST API    Relay API
    (FastAPI)   (FastAPI)
         |         |
         v         v
    CivicOS    civicos-relay
    (queries)  (coordination)
         |         |
         v         v
    PostgreSQL  Relay DB
    + pgvector  (Supabase)
    (Supabase)
         ^
         |
    civicos-extraction
    (platform parsers)
```

Two paths through the system: **Learn** (what's happening? what applies?) flows through the CivicOS query API. **Act** (voice support, commit to action) flows through the relay, which handles voice casting, subscriptions, and relay-to-relay sync using Nostr protocol.

**Why AI agents?** Most people won't download a civic engagement app. But millions already use AI agents daily. CivicOS connects via open protocols (MCP for knowledge, Nostr for coordination)—works with Claude, ChatGPT, open source models, or any compatible system.

**Why federation?** Civic issues span jurisdictions—housing involves federal funding, state law, county planning, and city zoning. Each jurisdiction runs its own relay independently. Voice support once and it syncs everywhere relevant. No central platform controls civic participation.

### San Rafael Pilot Data

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | ~98 | ProudCity (city website) |
| Decisions | ~44 | Minutes extraction |
| Transcripts | ~19 | YouTube + AssemblyAI |
| Agenda packets | ~5,084 chunks | City agenda PDFs |
| Municipal code | ~16,175 sections | Municode |
| Community issues | ~1,730 | SeeClickFix (311) |
| Budget items | ~58 | FY25-26 budget ($180M) |
| Legislation | ~17,719 | LegiScan (CA + federal) |

All data is semantically indexed (~16,786 vector embeddings) for natural language search.

---

## Design Principles

1. **Data sovereignty** — All civic data is public record. We aggregate, we don't create walled gardens.
2. **Jurisdictions first** — Infrastructure is designed around jurisdictions (cities, counties, school districts), not arbitrary regions.
3. **Sustainable, not cheap** — Real infrastructure costs real money. Funded through foundations and municipal partnerships, not VC.
4. **AI as leverage, not replacement** — LLMs help surface relevant information and draft responses. Humans decide what to do with it.
5. **Replicable** — Adding a new city should be configuration, not code. (We're not there yet, but that's the goal.)

### What This Isn't

- **Not optimizing for engagement** — No feeds, likes, or algorithmic amplification. Success is measured in decisions influenced, not time-on-app.
- **Not a replacement for showing up** — The goal is to make participation more effective, not to automate democracy away.
- **Not complete** — This is a pilot. Things will break. Data will have gaps.

---

## For Developers

### Quick Start

```bash
git clone https://github.com/lounsburynw/civicos.git
cd civicos
python3 -m venv civicos-env && source civicos-env/bin/activate
pip install -e packages/civicos -e packages/civicos-extraction -e packages/civicos-services
cp .env.example .env  # Add your API keys
./init.sh             # Verify setup
```

### Project Structure

```
civicos/
├── packages/civicos/              # Core query API
├── packages/civicos-relay/        # Coordination relay (voice, actions, sync)
├── packages/civicos-extraction/   # Data parsers (Legistar, SeeClickFix, etc.)
├── packages/civicos-services/     # REST API, WebSocket server
├── packages/civicos-client/       # TypeScript client library
├── packages/civicos-components/   # Svelte UI components
├── apps/civicos-extension/        # Browser extension (primary UX surface)
└── apps/civicos-mcp/              # MCP server
```

### Core API

```python
from dotenv import load_dotenv
load_dotenv()

from civicos import CivicOS
c = CivicOS("city-san-rafael")

c.whats_next()                       # Upcoming meetings with agendas
c.what_happened("housing")           # Past decisions on a topic
c.what_applies("ADU")                # Municipal code + state/federal law
c.what_was_said("homelessness")      # Search meeting transcripts
c.get_public_testimony("bike lanes") # Public comment excerpts
c.budget(department="Fire")          # Budget by department
```

### Development Workflow

This project uses **Claude Code** for AI-assisted development. See `CLAUDE.md` for session protocols, slash commands, code critics, and testing strategy.

### Documentation

| Topic | Document |
|-------|----------|
| Core API reference | [docs/public/api.md](docs/public/api.md) |
| Data dictionary | [docs/public/data-dictionary.md](docs/public/data-dictionary.md) |
| Extension development | [docs/public/extension/development.md](docs/public/extension/development.md) |
| MCP server & tools | [docs/public/mcp/setup.md](docs/public/mcp/setup.md) |
| Package docs | [docs/public/packages/](docs/public/packages/) |
| Architecture decisions | [docs/public/decisions/](docs/public/decisions/) |
| Learning series | [docs/public/learning/](docs/public/learning/) — cryptography, Nostr, attestation, federation, sustainability |

---

## Add Your City

Adding a new city is configuration, not code. If your city uses a supported platform, one command gets you from zero to searchable data.

### Supported platforms

| Platform | Type | Coverage |
|----------|------|----------|
| **Legistar** | Meetings | Oakland, Berkeley, Austin, Sacramento, 1000+ cities |
| **Granicus** | Meetings | Marin County, San Anselmo, Mill Valley, many more |
| **CivicClerk** | Meetings | El Cerrito, Hayward, San Pablo |
| **ProudCity** | Meetings | San Rafael |
| **eScribe** | Meetings | National City, Canadian cities |
| **SeeClickFix** | 311 Issues | Nationwide |
| **Municode** | Legal Code | Most US cities |
| **LegiScan** | Legislation | All 50 states + federal |

### Try it (no cloud accounts needed)

```bash
# 1. Clone and install
git clone https://github.com/lounsburynw/civicos.git
cd civicos
python3 -m venv civicos-env && source civicos-env/bin/activate
pip install -r requirements.txt

# 2. Test your city with a local sandbox (SQLite, no cloud)
python scripts/onboard.py --city "Your City" --state XX --sandbox

# 3. See what you got
python3 -c "
import sqlite3
conn = sqlite3.connect('data/sandbox_city-your-city.sqlite')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM meetings')
print(f'Meetings: {cur.fetchone()[0]}')
"

# 4. Clean up
python scripts/ingest_local.py --cleanup city-your-city
python scripts/onboard.py --cleanup city-your-city
```

### Deploy to production

When you're ready to go live, set up Supabase (Postgres) and Modal (serverless compute), then run the same command without `--sandbox`:

```bash
python scripts/onboard.py --city "Your City" --state XX --county "Your County"
```

See the full [Data Ingestion Guide](docs/public/data-ingestion.md) for prerequisites, API keys, tier-by-tier costs, and the manual setup path.

---

## For Cities

Interested in deploying CivicOS for your jurisdiction? The onboarding pipeline auto-detects your city's meeting platform, generates configuration, and ingests historical data. Start with the [sandbox test](#try-it-no-cloud-accounts-needed) above, or open an issue on GitHub.

---

## Contributing

We're focused on the San Rafael pilot. Contributions welcome—see `CLAUDE.md` for development workflow.

---

## License

**Source-available under [PolyForm Noncommercial 1.0.0](LICENSE.md)**

- **Individuals, nonprofits, academic institutions**: Free to use, modify, and share
- **For-profit companies**: Commercial license required

This structure keeps civic infrastructure accessible to residents and community organizations while ensuring companies that build on this work contribute to its sustainability.
