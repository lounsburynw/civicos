---
hide:
  - navigation
---

# CivicOS

**Open, permissionless civic infrastructure for AI agents.**

Query meetings, decisions, and municipal code. Find neighbors with shared concerns. Coordinate across city, county, and state. No app, no lock-in.

---

## Try It Now

CivicOS provides an MCP server. Connect via Claude, ChatGPT, or any MCP-compatible client.

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

## How It Works

```
You  -->  Your AI Agent  -->  CivicOS
                                 |
                      +----------+----------+
                      v                     v
                   Learn                   Act
               What's happening?      Voice support.
               Who else cares?        Commit to action.

--------------------------------------------------------------
Federated: Each city runs independently. Coordination syncs
across boundaries — city, county, state. No central platform.
```

**Why AI agents?** Most people won't download a civic engagement app. But millions already use AI agents daily. CivicOS connects via open protocols (MCP for knowledge, Nostr for coordination) — works with Claude, ChatGPT, open source models, or any compatible system.

**Why federation?** Civic issues span jurisdictions — housing involves federal funding, state law, county planning, and city zoning. CivicOS runs at each level. Your AI agent synthesizes across boundaries while you voice support once and it syncs everywhere relevant.

---

## San Rafael Pilot Data

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | 98 | Legistar API (Oct 2025 - Jan 2026) |
| Decisions | 44 | Extracted from meeting minutes |
| Transcripts | 29 | YouTube audio > AssemblyAI |
| Municipal Code | 16,175 sections | Municode |
| 311 Complaints | 1,730 | SeeClickFix API |
| Budget Items | 58 | FY25-26 adopted budget ($180M) |
| State/Federal Legislation | 17,719 | LegiScan API |

---

## Quick Links

<div class="grid cards" markdown>

-   :material-account-group:{ .lg .middle } **Users**

    ---

    Connect your AI agent and start asking questions about local government.

    [:octicons-arrow-right-24: Getting Started](user_guides/GETTING_STARTED.md)

-   :material-city:{ .lg .middle } **Cities**

    ---

    Deploy CivicOS for your jurisdiction. Supports Legistar, Granicus, CivicClerk, and more.

    [:octicons-arrow-right-24: City Onboarding](user_guides/CITY_ONBOARDING_GUIDE.md)

-   :material-code-braces:{ .lg .middle } **Developers**

    ---

    Explore the architecture, API, and package structure.

    [:octicons-arrow-right-24: Architecture](critical/FINAL_PACKAGE_ARCHITECTURE.md)

-   :material-book-open-variant:{ .lg .middle } **Learn**

    ---

    Self-contained modules covering cryptography, Nostr, attestation, and federation.

    [:octicons-arrow-right-24: Learning Modules](learning/README.md)

</div>

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
