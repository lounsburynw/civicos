---
hide:
  - navigation
---

# CivicOS

**Open, permissionless civic infrastructure for AI agents.**

Query meetings, decisions, and municipal code. Find neighbors with shared concerns. Coordinate across city, county, and state. No app, no lock-in.

---

## Try It Now

The **CivicOS browser extension** (Chrome) is the primary way to use CivicOS. It adds a side panel to your browser for searching meetings, tracking decisions, and signing public comments. See the [Browser Extension Setup](public/extension/setup.md).

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

```
You  -->  Browser Extension / AI Agent (Claude, ChatGPT)
                    |
               ┌────┴────┐
               v         v
          REST API    Relay API          Data + Coordination
               |         |
               v         v
          CivicOS    civicos-relay       Query / Voice / Subscriptions
          (Python)   (coordination)
               |         |
               v         v
          PostgreSQL  Relay DB           Two Supabase projects
          + pgvector  (Supabase)
          (Supabase)
               ^
               |
          civicos-extraction             Legistar, SeeClickFix, Municode, LegiScan
          (platform parsers)
```

See [full architecture and package docs](public/README.md).

---

## San Rafael Pilot Data

*As of March 2026. Ongoing ingestion.*

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | ~98 | ProudCity (Oct 2025 - present) |
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
| **[Users — Extension Setup](public/extension/setup.md)** | Install the browser extension and start exploring civic data. |
| **[Developers — Architecture](public/README.md)** | Package structure, API reference, and data dictionary. |
| **[MCP — AI Agent Setup](public/mcp/setup.md)** | Connect Claude, ChatGPT, or any MCP client. |
| **[Learn — Modules](public/learning/README.md)** | Cryptography, Nostr, attestation, and federation. |

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
