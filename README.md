<p align="center">
  <img src="assets/logo-light.svg" alt="CivicOS" width="240">
</p>

# CivicOS

**Ask questions about your local government in plain English.**

CivicOS indexes public meetings, decisions, municipal code, 311 complaints, and budgets—then exposes them through AI assistants you already use. No app to download.

## Contents

- [Try It Now](#try-it-now)
- [Example Questions](#example-questions)
- [How It Works](#how-it-works)
- [Design Principles](#design-principles)
- [For Developers](#for-developers)
- [For Cities](#for-cities)
- [Contributing](#contributing)

---

## Status: Pilot (Jan 2026)

Active pilot focused on **San Rafael, California**. We're validating one city before expanding.

**What we're testing:** Can structured civic data + AI assistance meaningfully increase resident participation in local decisions?

---

## Try It Now

CivicOS works through AI assistants you already use.

**Claude (claude.ai or Claude Desktop):**
1. Go to Settings → Connectors → Add Connector
2. Enter: `https://san-rafael.civicosproject.org/mcp`
3. Ask: *"What's on the San Rafael city council agenda?"*

**ChatGPT (Plus/Team with developer mode):**
1. Settings → Connectors → Enable developer mode
2. Add connector: `https://san-rafael.civicosproject.org/mcp`
3. Ask: *"What has San Rafael decided about housing?"*

**New to this?** Once connected, just say **"get started"** and the assistant will walk you through what you can ask.

---

## Example Questions

| You | CivicOS can answer |
|-----|-------------------|
| *"What's happening with the downtown parking garage?"* | Upcoming agenda items, past decisions, related complaints |
| *"Who else is concerned about traffic on Lincoln Ave?"* | Neighbors who filed similar 311 complaints |
| *"What did people say about homelessness at the last meeting?"* | Public testimony from transcripts |
| *"Help me prepare to speak at Monday's meeting"* | Relevant context, past decisions, talking points |
| *"How do I submit a public comment?"* | Email address, deadlines, tips for effective comments |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   "What's on the         ┌─────────────┐                           │
│    city council    ────► │ Claude.ai   │ ──┐                       │
│    agenda?"              └─────────────┘   │                       │
│                          ┌─────────────┐   │   ┌─────────────────┐ │
│   "Who else cares        │ ChatGPT     │ ──┼──►│ CivicOS         │ │
│    about this?"          └─────────────┘   │   │ MCP Server      │ │
│                          ┌─────────────┐   │   └────────┬────────┘ │
│                          │ Claude App  │ ──┘            │          │
│                          └─────────────┘                ▼          │
│                                              ┌─────────────────┐   │
│                                              │   Civic Data    │   │
│                                              │   (PostgreSQL)  │   │
│                                              └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**Why AI assistants?** Most people won't download a civic engagement app. But millions already use Claude and ChatGPT daily. CivicOS meets people where they are.

**Why federation?** Each jurisdiction runs independently while sharing coordination signals across boundaries. No single platform controls civic participation—your AI agent reasons locally, civic knowledge flows openly. See [Coordination Protocol](docs/critical/COORDINATION_PROTOCOL.md) for details.

### San Rafael Pilot Data

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | 98 | Legistar API (Oct 2025 - Jan 2026) |
| Decisions | 44 | Extracted from meeting minutes |
| Transcripts | 29 | YouTube audio → AssemblyAI |
| Municipal Code | 16,175 sections | Municode |
| 311 Complaints | 1,730 | SeeClickFix API |
| Budget Items | 58 | FY25-26 adopted budget ($180M) |
| State/Federal Legislation | 17,719 | LegiScan API |

---

## Design Principles

1. **Data sovereignty** — All civic data is public record. We aggregate, we don't create walled gardens.

2. **Jurisdictions first** — Infrastructure is designed around jurisdictions (cities, counties, school districts), not arbitrary regions.

3. **Sustainable, not cheap** — Real infrastructure costs real money. We're transparent about costs and fund through appropriate channels (foundations, municipal partnerships), not VC.

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
./scripts/dev.sh      # Start dev servers (localhost:5173)
```

### Project Structure

```
civicos/
├── packages/civicos/             # Core query API
├── packages/civicos-relay/       # Federation relay (voice, sync)
├── packages/civicos-extraction/  # Data parsers (Legistar, SeeClickFix, etc.)
├── packages/civicos-services/    # REST API, WebSocket server
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

### Development Workflow

This project uses **Claude Code** for AI-assisted development. See `CLAUDE.md` for:
- Session protocols and slash commands (`/start`, `/commit`, `/test`)
- Code critics that catch architectural issues before commit
- Testing strategy (smoke tests locally, full suite in CI)
- Storage backend configuration (PostgreSQL vs SQLite)

### Further Reading

| Topic | Document |
|-------|----------|
| Architecture | [docs/critical/FINAL_PACKAGE_ARCHITECTURE.md](docs/critical/FINAL_PACKAGE_ARCHITECTURE.md) |
| Federation & Coordination | [docs/critical/COORDINATION_PROTOCOL.md](docs/critical/COORDINATION_PROTOCOL.md) |
| MCP Tools (30 tools) | [apps/civicos-mcp/README.md](apps/civicos-mcp/README.md) |
| Operating Costs | [docs/OPERATING_COSTS.md](docs/OPERATING_COSTS.md) |
| Deployment | [docs/critical/DEPLOYMENT_GUIDE.md](docs/critical/DEPLOYMENT_GUIDE.md) |

---

## For Cities

Interested in deploying CivicOS for your jurisdiction?

The extraction layer supports common civic platforms:
- **Legistar** (Oakland, Berkeley, SF, many more)
- **CivicClerk**, **Granicus** (various)
- **SeeClickFix** (any city on platform)
- **Municode** (most CA cities)

**Get started:** [City Onboarding Guide](docs/user_guides/CITY_ONBOARDING_GUIDE.md)

**Operating costs:** ~$130-400/month per active jurisdiction. See [Operating Costs](docs/OPERATING_COSTS.md) for breakdown.

**Questions?** Open an issue or reach out via the onboarding guide.

---

## Contributing

We're focused on the San Rafael pilot through Q1 2026. Contributions welcome—see `CLAUDE.md` for development workflow.

---

## License

**Source-available under [PolyForm Noncommercial 1.0.0](LICENSE.md)**

- **Individuals, nonprofits, academic institutions**: Free to use, modify, and share
- **For-profit companies**: Commercial license required

This structure keeps civic infrastructure accessible to residents and community organizations while ensuring companies that build on this work contribute to its sustainability.
