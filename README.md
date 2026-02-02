<p align="center">
  <img src="assets/logo-light.svg" alt="CivicOS" width="240">
</p>

# CivicOS

**Ask questions about your local government—and find others who care.**

Open, permissionless civic infrastructure for AI agents. Query meetings, decisions, and municipal code. Find neighbors with shared concerns. Coordinate across city, county, and state. No app, no lock-in.

## Contents

- [Try It Now](#try-it-now)
- [Example Questions](#example-questions)
- [How It Works](#how-it-works)
- [Design Principles](#design-principles)
- [For Developers](#for-developers)
- [For Cities](#for-cities)
- [Contributing](#contributing)

---

## Try It Now

CivicOS provides an MCP server. Connect via Claude, ChatGPT, or any MCP-compatible client.

**Claude (claude.ai or Claude Desktop):**
1. Go to Settings → Connectors → Add Connector
2. Enter: `https://san-rafael.civicosproject.org/mcp`
3. Ask: *"What's on the San Rafael city council agenda?"*

**ChatGPT (Plus/Team with developer mode):**
1. Settings → Connectors → Enable developer mode
2. Add connector: `https://san-rafael.civicosproject.org/mcp`
3. Ask: *"What has San Rafael decided about housing?"*

**New to this?** Once connected, just say **"get started"** and the agent will walk you through what you can ask.

---

## Example Questions

| You | CivicOS | Via |
|-----|---------|-----|
| *"What's happening with the 4th St rezoning?"* | Agenda status, past decisions, state density bonus law | MCP Server |
| *"Who else cares about traffic on Lincoln?"* | 23 neighbors filed complaints, 8 voiced support | MCP + Relay |
| *"What did people say about homelessness at the last meeting?"* | Public testimony from transcripts | MCP Server |
| *"I support the bike lane proposal"* | Voice recorded. You're one of 34 supporters. | AI Agent → Relay |
| *"I'll attend Monday's meeting"* | Committed. 11 others plan to attend. | AI Agent → Relay |
| *"Help me prepare to speak"* | Context, talking points, then "Ready to commit?" | AI Agent → MCP → Relay |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   You ──► Your AI Agent ──► CivicOS                            │
│                                     │                               │
│                          ┌──────────┴──────────┐                   │
│                          ▼                     ▼                    │
│                       Learn                   Act                   │
│                   What's happening?      Voice support.             │
│                   Who else cares?        Commit to action.          │
│                                                                     │
│   ─────────────────────────────────────────────────────────────    │
│   Federated: Each city runs independently. Coordination syncs      │
│   across boundaries—city, county, state. No central platform.      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Why AI agents?** Most people won't download a civic engagement app. But millions already use AI agents daily. CivicOS connects via open protocols (MCP for knowledge, Nostr for coordination)—works with Claude, ChatGPT, open source models, or any compatible system. No lock-in.

**Why federation?** Civic issues span jurisdictions—housing involves federal funding, state law, county planning, and city zoning. CivicOS runs at each level. Your AI agent synthesizes across boundaries while you voice support once and it syncs everywhere relevant. No single platform controls civic participation. See [Coordination Protocol](docs/critical/COORDINATION_PROTOCOL.md) for details.

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
├── packages/civicos-relay/       # Federation relay (voice, actions, sync)
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
