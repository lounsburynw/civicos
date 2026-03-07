---
hide:
  - navigation
---

# CivicOS

**Open, permissionless civic infrastructure for AI agents.**

Query meetings, decisions, and municipal code. Find neighbors with shared concerns. Coordinate across city, county, and state. No app, no lock-in.

---

## Try It Now

The **CivicOS browser extension** (Chrome) is the primary way to use CivicOS. It adds a side panel to your browser for searching meetings, tracking decisions, and signing public comments. See the [Browser Extension Setup Guide](user_guides/BROWSER_EXTENSION_SETUP.md).

CivicOS also provides an MCP server. Connect via Claude, ChatGPT, or any MCP-compatible client.

=== "Claude"

    1. Go to **Settings > Connectors > Add Connector**
    2. Enter: `https://san-rafael.civicosproject.org/mcp`
    3. Ask: *"What's on the San Rafael city council agenda?"*

=== "ChatGPT"

    1. **Settings > Connectors > Enable developer mode**
    2. Add connector: `https://san-rafael.civicosproject.org/mcp`
    3. Ask: *"What has San Rafael decided about housing?"*

!!! tip "New to this?"
    Once connected, just say **"get started"** and the agent will walk you through what you can ask.

---

## What Can You Ask?

| You | CivicOS | Via |
|-----|---------|-----|
| *"What's happening with the 4th St rezoning?"* | Agenda status, past decisions, state density bonus law | MCP Server |
| *"Who else cares about traffic on Lincoln?"* | 23 neighbors filed complaints, 8 voiced support | MCP + Relay |
| *"What did people say about homelessness at the last meeting?"* | Public testimony from transcripts | MCP Server |
| *"I support the bike lane proposal"* | Voice recorded. You're one of 34 supporters. | AI Agent > Relay |
| *"Help me prepare to speak"* | Context, talking points, then "Ready to commit?" | AI Agent > MCP > Relay |

---

## Architecture

CivicOS is built in layers, connected by open protocols:

```
You  -->  Your AI Agent (Claude, ChatGPT, etc.)
               |
               v
          MCP Server                32 tools, 5 resources, 2 prompts
               |
          +----+----+
          v         v
      Core API   Relay              Query data / Coordinate action
       (civicos)  (civicos-relay)
          |         |
          v         v
      Storage    Nostr Protocol     PostgreSQL + pgvector / secp256k1 Schnorr
          |
          v
      Extraction                    Legistar, SeeClickFix, Municode, LegiScan
       (civicos-extraction)
```

**MCP Server** — Exposes civic data to any AI agent via the [Model Context Protocol](https://modelcontextprotocol.io). 32 primitives covering meetings, decisions, transcripts, legislation, budget, 311 issues, and coordination. See [MCP Integration Strategy](critical/MCP_INTEGRATION_STRATEGY.md).

**Core API** — The `CivicOS` class: `what_happened()`, `whats_next()`, `what_applies()`, `whos_with_me()`, `prepare()`, and more. Semantic search over 16,000+ vector embeddings. See [Package Architecture](critical/FINAL_PACKAGE_ARCHITECTURE.md).

**Relay** — Federation-ready coordination server using [Nostr protocol](critical/NOSTR_CIVIC_NIPS.md) with secp256k1 Schnorr signatures. Handles voices, subscriptions, and cross-jurisdiction sync. See [Coordination Protocol](critical/COORDINATION_PROTOCOL.md).

**Extraction** — Platform parsers that normalize data from Legistar, CivicClerk, Granicus, SeeClickFix, Municode, and more into a unified schema. See [Extractor Protocol](critical/EXTRACTOR_PROTOCOL.md).

**Why AI agents?** Most people won't download a civic engagement app. But millions already use AI agents daily. CivicOS connects via open protocols (MCP for knowledge, Nostr for coordination) — works with Claude, ChatGPT, open source models, or any compatible system.

**Why federation?** Civic issues span jurisdictions — housing involves federal funding, state law, county planning, and city zoning. CivicOS runs at each level. Your AI agent synthesizes across boundaries while you voice support once and it syncs everywhere relevant.

!!! info "Want to understand the cryptography and protocol design?"
    The [Learning Modules](learning/README.md) are self-contained deep dives: from [cryptographic foundations](learning/01_CRYPTOGRAPHIC_FOUNDATIONS.md) through [Nostr and the relay](learning/02_NOSTR_AND_THE_RELAY.md) to [economic sustainability](learning/06_ECONOMIC_MODEL_AND_SUSTAINABILITY.md).

---

## San Rafael Pilot Data

*As of March 2026. Ongoing ingestion.*

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | ~98 | Legistar API (Oct 2025 - present) |
| Decisions | ~44 | Extracted from meeting minutes |
| Transcripts | ~19 | YouTube audio > AssemblyAI |
| Agenda Chunks | ~5,084 | Agenda packet PDFs |
| Municipal Code | ~16,175 sections | Municode |
| 311 Complaints | ~1,730 | SeeClickFix API |
| Budget Items | ~58 | FY25-26 adopted budget ($180M) |
| State/Federal Legislation | ~17,719 | LegiScan API |

---

## Quick Links

| | |
|---|---|
| **[Users — Getting Started](user_guides/GETTING_STARTED.md)** | Connect your AI agent and start asking questions about local government. |
| **[Cities — Onboarding Guide](user_guides/CITY_ONBOARDING_GUIDE.md)** | Deploy CivicOS for your jurisdiction. Supports Legistar, Granicus, CivicClerk, and more. |
| **[Developers — Architecture](critical/FINAL_PACKAGE_ARCHITECTURE.md)** | Explore the architecture, API, and package structure. |
| **[Learn — Modules](learning/README.md)** | Self-contained modules covering cryptography, Nostr, attestation, and federation. |

---

## Design Principles

1. **Data sovereignty** — All civic data is public record. We aggregate, we don't create walled gardens.
2. **Jurisdictions first** — Infrastructure is designed around jurisdictions (cities, counties, school districts), not arbitrary regions.
3. **Sustainable, not cheap** — Real infrastructure costs real money. Funded through foundations and municipal partnerships, not VC.
4. **AI as leverage, not replacement** — LLMs help surface relevant information. Humans decide what to do with it.
5. **Replicable** — Adding a new city should be configuration, not code.

---

## License

Source-available under [PolyForm Noncommercial 1.0.0](https://github.com/lounsburynw/civicos/blob/main/LICENSE.md). Free for individuals, nonprofits, and academic institutions. Commercial license required for for-profit companies.
