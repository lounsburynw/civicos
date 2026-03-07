# Getting Started with CivicOS

CivicOS connects your AI agent to local government data — meetings, decisions, municipal code, budgets, legislation, and community issues. Ask questions in natural language and get answers grounded in real civic data.

---

## Connect in 60 Seconds

CivicOS works through the Model Context Protocol (MCP). Connect from any compatible AI client:

=== "Claude (claude.ai or Desktop)"

    1. Go to **Settings > Connectors > Add Connector**
    2. Enter: `https://san-rafael.civicosproject.org/mcp`
    3. Ask: *"What's on the San Rafael city council agenda?"*

=== "ChatGPT (Plus/Team)"

    1. **Settings > Connectors > Enable developer mode**
    2. Add connector: `https://san-rafael.civicosproject.org/mcp`
    3. Ask: *"What has San Rafael decided about housing?"*

Once connected, say **"get started"** and the agent will walk you through what's available.

---

## What You Can Ask

### Upcoming Meetings & Agendas

> *"What's being decided about housing this month?"*
> *"When is the next city council meeting?"*
> *"What's on the agenda for the planning commission?"*

Returns meeting dates, agenda items, and links to staff reports and agenda packets.

### Past Decisions & Voting History

> *"What has the council decided about bike lanes?"*
> *"How did the council vote on the homeless shelter?"*
> *"What happened with the 4th Street rezoning?"*

Returns council votes, outcomes, staff recommendations, and related context.

### Public Testimony & Meeting Transcripts

> *"What did residents say about traffic on 4th Street?"*
> *"What was discussed at the last planning commission meeting?"*

Returns excerpts from meeting transcripts with speaker identification and timestamps.

### Laws & Regulations

> *"What laws apply to ADUs in San Rafael?"*
> *"What state bills affect affordable housing?"*
> *"What does the municipal code say about noise ordinances?"*

Searches across municipal code, California state legislation, and federal programs.

### Community Issues (311 / SeeClickFix)

> *"Who else cares about traffic safety in my neighborhood?"*
> *"What are the most common complaints in 94901?"*
> *"Are there repeat issues at the intersection of 4th and B?"*

Returns SeeClickFix complaints, trends, geographic patterns, and resolution statistics.

### Budget & Funding

> *"How much does San Rafael spend on public safety?"*
> *"What federal grants fund homelessness prevention?"*
> *"What's the city budget for parks and recreation?"*

Returns budget line items, department spending, and federal/state funding flows.

### Meeting Preparation

> *"Help me prepare for the bike lane agenda item."*
> *"Draft a public comment supporting the traffic calming proposal."*

Generates background context, talking points, regulatory context, and draft comments.

---

## Voice & Coordination

Beyond querying data, CivicOS supports civic coordination:

- **Voice support or opposition** on agenda items and proposals
- **Find allies** — see how many others share your position
- **Follow topics** — get updates when meetings or decisions match your interests
- **Start initiatives** — propose ideas for community backing

Voice and coordination features require **attestation** — a cryptographic proof that you're a real community member. See the [Attestation Guide](ATTESTATION_GUIDE.md) for details.

---

## Data Sources

All information comes from publicly available sources:

| Source | What You Get |
|--------|-------------|
| **Legistar** | City council agendas, meeting schedules, staff reports |
| **YouTube / AssemblyAI** | Meeting transcripts from video recordings |
| **SeeClickFix** | Resident-reported issues (potholes, graffiti, noise, etc.) |
| **LegiScan** | California state and federal legislation |
| **HUD / Federal** | Federal housing programs, grants, regulations |
| **Municode** | San Rafael municipal code |
| **OpenGov** | City budget data |

CivicOS aggregates and indexes this data for semantic search. It does not create or editorialize content.

---

## Tips

- **Use natural language.** Ask questions like you'd ask a neighbor: *"What's happening with the new housing development on Lincoln?"*
- **Start with what's next.** Upcoming decisions are the most actionable — ones you can still influence.
- **Be specific.** *"Housing on Lincoln Avenue"* gets better results than just *"housing"*.
- **Ask follow-ups.** The AI remembers conversation context: *"Tell me more about that"* or *"When was that decided?"*

---

## Privacy

- **Your queries are private.** CivicOS does not log or store your questions.
- **Public actions are public.** Voices and comments become part of the coordination record, similar to speaking at a public meeting.
- **No account required to browse.** You can query all civic data without registration. Voice and coordination features require attestation.

---

## Get Help

- **Report an issue:** [GitHub Issues](https://github.com/lounsburynw/civicos/issues)
- **Documentation:** [docs.civicosproject.org](https://docs.civicosproject.org)
