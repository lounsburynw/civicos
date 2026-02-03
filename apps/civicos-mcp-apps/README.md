# CivicOS MCP Apps

Interactive widgets for civic coordination, rendered directly in AI hosts (Claude.ai, ChatGPT, etc).

## The Vision

When someone asks their AI assistant about a local issue, they don't just get information—they see **coordination happening in real-time**:

- How many neighbors care about this issue
- Whether momentum is building ("+5 voices in the last hour")
- A one-click way to add their voice

This is **Edge Intelligence** in action: your personal AI agent helping you coordinate with your community.

## Quick Start

```bash
# Install dependencies
npm install

# Build widgets + start server
npm run dev

# In another terminal, create a tunnel for Claude.ai testing
npm run tunnel
```

Then add the cloudflared URL as a custom connector in Claude.ai.

## Architecture

```
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│   AI Host        │     │  MCP Apps Server    │     │  Jurisdiction    │
│  (Claude.ai)     │◄───►│  (this package)     │◄───►│  MCP (Python)    │
├──────────────────┤     ├─────────────────────┤     ├──────────────────┤
│  Sandboxed       │     │  • voice_interface  │     │  Civic data      │
│  iframe with     │     │  • meeting_prep     │     │  Voice counts    │
│  Vue widgets     │     │  • issue_card       │     │  Relay broadcast │
└──────────────────┘     └─────────────────────┘     └──────────────────┘
```

**Key insight:** After initial load, widget ↔ server communication bypasses the LLM entirely. This enables real-time updates without burning tokens.

## Widgets

### Voice Widget (`voice_interface`)

Cast your voice on civic decisions, initiatives, or issues.

```
User: "Show me the voice interface for the 4th Street bike lane proposal"

┌─────────────────────────────────────────────────┐
│  4th Street Bike Lane Proposal                  │
│  decision:city-san-rafael:2026-01-15:item-5a    │
│                                                 │
│  ┌─────────────────────────────────────────┐    │
│  │  47 people have voiced                  │    │
│  │  +5 in the last hour                 🟢 │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  [👍 Support: 32] [👎 Oppose: 8] [👀 Watch: 7]  │
│                                                 │
│  (○ Anonymous) (● Verified)                     │
│  [        Cast Support        ]                 │
└─────────────────────────────────────────────────┘
```

### Planned Widgets

- **Meeting Prep** - Interactive agenda with decision history
- **Issue Card** - Follow 311 issues, see similar complaints nearby
- **Initiative Dashboard** - Create and track community initiatives

## Development

### Adding a New Widget

1. Create `src/widgets/{name}.html` - the widget UI
2. Create `src/widgets/{name}/register.ts` - tool + resource registration
3. Import in `server.ts`

Widgets are auto-discovered by Vite and bundled as single HTML files.

### Testing

```bash
# Run tests
npm test

# Test with MCP Apps basic-host
git clone https://github.com/modelcontextprotocol/ext-apps
cd ext-apps/examples/basic-host
SERVERS='["http://localhost:3002/mcp"]' npm start
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3002` | Server port |
| `JURISDICTION_MCP_URL` | `https://san-rafael.civicosproject.org/mcp` | Backend MCP server |
| `RELAY_URL` | `https://api.civicosproject.org` | Voice relay server |
| `PERSONAL_MCP_URL` | - | Optional: Personal MCP for identity |

## Deployment

### Modal

```bash
modal deploy modal_app.py
```

### Docker

```bash
docker build -t civicos-mcp-apps .
docker run -p 3002:3002 civicos-mcp-apps
```

## How It Works

1. **User asks** about a civic matter
2. **LLM calls** `voice_interface` tool with entity ID
3. **Server returns** current voice counts + widget HTML
4. **Host renders** widget in sandboxed iframe
5. **Widget polls** for real-time updates (no LLM involved)
6. **User clicks** Support/Oppose/Watch
7. **Widget signs** locally with WebAuthn or ephemeral key
8. **Widget broadcasts** to relay via server tool
9. **Widget updates** display and notifies LLM of action

The LLM is only involved in steps 2-3 and receives a context update in step 9. Everything else is direct widget ↔ server communication.
