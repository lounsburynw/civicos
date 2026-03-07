# CivicOS Feature Guide

CivicOS exposes 32 MCP primitives (25 tools + 5 resources + 2 prompts) through your AI agent. This guide explains what each capability does and when to use it.

For setup instructions, see [Getting Started](GETTING_STARTED.md).

---

## Query Features (Learn)

### What's Next — Upcoming Meetings

Find upcoming city council meetings and what's being decided.

**Example queries:**

- *"What meetings are coming up this month?"*
- *"What's on the agenda for the next city council meeting?"*
- *"Are there any planning commission meetings about housing?"*

**What you get:** Meeting date, time, location, agenda items, and links to staff reports and agenda packets.

---

### What Happened — Past Decisions

Search historical council decisions and voting records.

**Example queries:**

- *"What has the council decided about bike lanes?"*
- *"How did the council vote on the homeless shelter?"*
- *"What decisions were made about housing in 2025?"*

**What you get:** Council votes, outcomes, staff recommendations, meeting dates, and related context.

---

### What Was Said — Meeting Transcripts

Search what was actually said in meetings — council discussion, staff presentations, and public testimony.

**Example queries:**

- *"What did residents say about traffic on 4th Street?"*
- *"What was discussed at the last planning commission meeting?"*
- *"Has anyone testified about wildfire prevention?"*

**What you get:** Transcript excerpts with speaker identification, timestamps, and links to the video recording.

---

### What Applies — Laws & Regulations

Search the full regulatory stack: municipal code, state legislation, and federal programs.

**Example queries:**

- *"What does the municipal code say about ADUs?"*
- *"What state laws affect affordable housing?"*
- *"What federal programs fund homelessness prevention?"*

**What you get:** Relevant code sections, bill text, program descriptions, and funding amounts across all three levels of government.

---

### Who's With Me — Community Issues

Find neighbors who care about the same issues using SeeClickFix 311 data.

**Example queries:**

- *"Who else cares about traffic safety near my neighborhood?"*
- *"What are the most common complaints in 94901?"*
- *"Are there repeat issues at 4th and B Streets?"*

**What you get:** Related complaints, community sentiment, geographic patterns, and resolution statistics.

---

### Budget & Funding

Query city budget data and federal/state funding flows.

**Example queries:**

- *"How much does San Rafael spend on public safety?"*
- *"What's the parks and recreation budget?"*
- *"What federal grants does San Rafael receive for housing?"*

**What you get:** Budget line items by department, funding amounts, and intergovernmental funding flows.

---

### Agenda Packets (PDF Search)

Search the full text of agenda packet PDFs — staff reports, resolutions, environmental reviews, and attachments.

**Example queries:**

- *"Search agenda packets for 'traffic calming'"*
- *"Find staff reports about the Downtown Precise Plan"*

**What you get:** Relevant excerpts from PDF documents with page references and meeting context.

---

## 311 Analytics Suite

CivicOS includes a dedicated analytics suite for SeeClickFix/311 data with 10 specialized tools:

| Capability | Example Query |
|-----------|---------------|
| **Aggregate stats** | *"How many issues were reported last month?"* |
| **Drill-down** | *"Show me graffiti reports by neighborhood"* |
| **Trends** | *"What issue types are increasing?"* |
| **Geographic** | *"What issues are near 123 Main Street?"* |
| **Resolution** | *"How fast does the city fix potholes?"* |
| **Repeat issues** | *"Are there recurring problems at this location?"* |
| **Seasonal** | *"When do noise complaints peak?"* |
| **Neighborhood reports** | *"Give me a full report for zip code 94901"* |
| **Comparisons** | *"Compare issues in 94901 vs 94903"* |
| **Patterns** | *"Show me raw issue data for content analysis"* |

---

## Action Features (Act)

### Prepare for a Meeting

Get comprehensive preparation materials for an upcoming agenda item.

**Example queries:**

- *"Help me prepare for the bike lane agenda item"*
- *"What should I know before the housing discussion?"*

**What you get:** Background context, regulatory stack, historical decisions, talking points, and logistics (time, location, comment procedures).

---

### Draft a Public Comment

Get help writing an effective public comment.

**Example queries:**

- *"Draft a comment supporting the traffic calming proposal"*
- *"Help me write a comment opposing the rezoning"*

**What you get:** A draft comment grounded in relevant facts, regulations, and precedents. Personalize it with your own experience before submitting through the city's official channels.

!!! note
    CivicOS helps you prepare comments but does not submit them to the city. Submit via email to the city clerk or speak at the meeting.

---

### Voice Support or Opposition

Express your stance on an agenda item or community proposal within the CivicOS coordination system.

- **Support** — You're in favor
- **Oppose** — You're against
- **Question** — You want clarification without taking a side

Voices are aggregated to show community sentiment. They require [attestation](ATTESTATION_GUIDE.md).

---

### Follow Topics

Subscribe to updates on topics, meetings, or initiatives you care about. Get notified when relevant meetings are scheduled, decisions are made, or community momentum builds.

---

### Start an Initiative

Propose an idea for community backing — e.g., "Protected bike lane on 4th Street" or "Increase funding for wildfire prevention." Others can voice support, and CivicOS helps coordinate next steps when momentum builds.

---

## Resources (Browse)

CivicOS also provides browsable resources your AI agent can access:

| Resource | What It Contains |
|----------|-----------------|
| Recent meetings | Browsable list of recent meetings with agendas |
| Budget departments | City budget organized by department |
| Issue statistics | Summary of 311/SeeClickFix data |
| Corpus statistics | Data coverage across all indexed sources |
| Jurisdiction info | City metadata, contact info, meeting schedules |

---

## Guided Workflows (Prompts)

Two structured workflows are available:

### Meeting Prep

A step-by-step workflow that walks you through preparing for a specific meeting — from understanding the agenda to drafting your comment.

### Topic Research

A multi-tool research workflow that comprehensively explores a topic across meetings, decisions, legislation, issues, and budget data.

---

## What CivicOS Cannot Do

- **Predict votes** — CivicOS provides historical data, not forecasts
- **Submit comments** — You must submit through official city channels
- **Access non-public data** — All data comes from public sources
- **Represent you** — CivicOS provides information and drafts; you make the decisions
