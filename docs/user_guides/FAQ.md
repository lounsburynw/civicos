# Frequently Asked Questions

---

## About CivicOS

### What is CivicOS?

CivicOS is open infrastructure that connects AI agents to local government data. It lets you ask questions about meetings, decisions, municipal code, budgets, and community issues — and find neighbors who care about the same things. It works through the Model Context Protocol (MCP), so you use it from within Claude, ChatGPT, or any compatible AI client.

### Why does this exist?

Most residents learn about city council decisions after they've already been made. CivicOS bridges this gap by making civic data queryable through the AI tools people already use — no new app to download, no login required.

### Who created CivicOS?

CivicOS is a foundation-funded project building open civic infrastructure. It's not affiliated with any city government.

### Is CivicOS free?

Yes. CivicOS is free for individuals and nonprofits under the PolyForm Noncommercial license.

### How is this different from just reading the city website?

CivicOS aggregates data from multiple sources (agendas, transcripts, municipal code, SeeClickFix, state/federal legislation, budgets), indexes it for semantic search, and makes it queryable through natural language via your AI agent. Instead of clicking through Legistar, searching YouTube timestamps, and cross-referencing state bills — you ask one question and get a synthesized answer with sources.

---

## How It Works

### How do I connect?

Add the MCP connector URL in your AI client:

- **Claude:** Settings > Connectors > `https://san-rafael.civicosproject.org/mcp`
- **ChatGPT:** Settings > Connectors > same URL

Then just ask questions. See [Getting Started](GETTING_STARTED.md) for details.

### Where does the data come from?

All data comes from publicly available sources:

| Source | Data |
|--------|------|
| Legistar | Agendas, meetings, staff reports |
| YouTube + AssemblyAI | Meeting transcripts |
| SeeClickFix | 311 complaints and issues |
| LegiScan | State and federal legislation |
| Municode | Municipal code |
| OpenGov | Budget data |
| HUD / Federal | Housing programs and grants |

### How current is the data?

- **Meeting agendas**: Synced from Legistar regularly
- **Transcripts**: Processed from YouTube recordings after meetings are posted
- **SeeClickFix issues**: Updated regularly
- **State legislation**: Updated from LegiScan
- **Municipal code**: Full Municode corpus indexed

### Can I trust the AI answers?

CivicOS grounds AI responses in real civic data — the AI searches indexed records to answer your questions. It can't fabricate meeting dates or invent council votes because it's querying actual data. However, AI can misinterpret questions or miss relevant context. Treat responses as a well-researched starting point, not a legal source. When in doubt, check the original sources linked in responses.

---

## Privacy

### Is my usage private?

Yes. CivicOS does not log or store your queries. Your AI client (Claude, ChatGPT) has its own privacy policies for conversation data.

### Do I need an account?

No. You can query all civic data — meetings, decisions, transcripts, legislation, budgets, issues — without any account or registration.

### What about voice and coordination features?

Voicing support/opposition and coordination features require **attestation** — a cryptographic proof obtained by attending a local community event. This prevents automated spam while preserving privacy. See the [Attestation Guide](ATTESTATION_GUIDE.md).

### What data does CivicOS store about me?

If you only query data (ask questions): nothing.

If you use coordination features (voice, follow, subscribe): your cryptographic identity key and your public actions (voices, comments) are stored on the relay. No email, name, or personal information is required.

---

## Participating in Government

### Can CivicOS submit comments to the city council for me?

No. CivicOS helps you *prepare* comments and understand context, but it does not submit anything to the city on your behalf. To have your voice count in the official record, you should:

- Email the city clerk directly
- Attend the meeting and speak during public comment
- Submit written comments through the city's official channels

CivicOS provides clerk contact information and submission guidelines to make this easier.

### What does "voicing" mean?

Voicing is expressing support, opposition, or a question on a civic item (agenda item, initiative, etc.) within the CivicOS coordination system. It's visible to other CivicOS users and helps measure community sentiment, but it is **not** the same as an official public comment submitted to the city.

### How do I actually participate in a city council meeting?

1. **Find the meeting** — Ask CivicOS: *"When is the next city council meeting?"*
2. **Prepare** — Ask: *"Help me prepare for the [topic] agenda item"*
3. **Submit a comment** — Email the city clerk before the meeting deadline
4. **Attend** — Show up in person or join the virtual meeting link
5. **Speak** — Sign up for public comment (typically 2-3 minutes per person)

### What's an initiative?

An initiative is a community-sourced proposal within CivicOS. You create it, others voice support, and when momentum builds, CivicOS helps coordinate next steps (like petitioning for the item to be added to a council agenda). Initiatives are coordination tools, not official government actions.

---

## Technical

### What AI clients work with CivicOS?

Any client that supports the Model Context Protocol (MCP):

- Claude (claude.ai, Claude Desktop, Claude Mobile)
- ChatGPT (Plus/Team with developer mode)
- Any MCP-compatible open source client

### What cities are supported?

Currently San Rafael, California (pilot). The infrastructure is designed for multi-city federation — see the [City Onboarding Guide](CITY_ONBOARDING_GUIDE.md) if you're interested in adding your city.

### What is MCP?

The Model Context Protocol is an open standard for connecting AI assistants to external data sources. It lets CivicOS provide structured civic data to any compatible AI client without building separate integrations for each platform. Learn more at [modelcontextprotocol.io](https://modelcontextprotocol.io).

### What is federation?

CivicOS is designed so each jurisdiction runs independently while coordinating across boundaries. A housing question might involve federal funding, state law, county planning, and city zoning. Federation lets your AI agent synthesize across these levels while each jurisdiction maintains sovereignty over its own data. See the [Coordination Protocol](../critical/COORDINATION_PROTOCOL.md) for the full design.

### What is the relay?

The relay is a federation-ready server that handles coordination: routing civic events, managing subscriptions, counting voices, and syncing with peer relays across jurisdictions. It uses the [Nostr protocol](../critical/NOSTR_CIVIC_NIPS.md) with secp256k1 Schnorr signatures for cryptographic identity without centralized accounts. See the [civicos-relay package](../packages/civicos-relay.md) for details.

### How does the cryptography work?

CivicOS uses Nostr-style cryptographic identity: each user generates a secp256k1 keypair locally. Voices and actions are signed with Schnorr signatures, making them verifiable without a central authority. Attestation adds a proof-of-community-membership layer on top. The [Learning Modules](../learning/README.md) walk through this from first principles:

- [Cryptographic Foundations](../learning/01_CRYPTOGRAPHIC_FOUNDATIONS.md) — Keys, signatures, identity
- [Nostr & the Relay](../learning/02_NOSTR_AND_THE_RELAY.md) — Protocol design
- [Attestation](../learning/03_ATTESTATION_AND_THE_FULL_SYSTEM.md) — Proof of personhood
- [Relay Trust](../learning/04_RELAY_TRUST_AND_INTEGRITY.md) — Trust signals and integrity
- [Jurisdiction Scope](../learning/05_JURISDICTION_SCOPE_AND_ATTESTATION_ROLLUP.md) — Cross-jurisdiction coordination
- [Economic Model](../learning/06_ECONOMIC_MODEL_AND_SUSTAINABILITY.md) — Sustainability

---

## Get Help

- **Documentation:** [docs.civicosproject.org](https://docs.civicosproject.org)
- **Report a bug:** [GitHub Issues](https://github.com/lounsburynw/civicos/issues)
- **Feature requests:** [GitHub Issues](https://github.com/lounsburynw/civicos/issues)
