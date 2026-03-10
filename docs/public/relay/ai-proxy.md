# AI Proxy

The relay provides authenticated AI access for attested residents — zero-config AI drafting and civic Q&A without requiring an API key.

## Why Route AI Through the Relay

The standard approach to AI-powered features is to have users provide their own API key or to bill them directly. Both create a privacy problem for civic participation:

**If the user provides their own API key:** Their API provider (Anthropic, OpenAI) sees both their identity (billing info) and every civic question they ask. "Who asked about the housing proposal?" is answered by the API provider's logs.

**If CivicOS bills users directly with linked identity:** CivicOS's database contains both payment identity (name, email, credit card) and query content. A single subpoena or breach exposes who asked what.

The relay solves this by separating the system that knows "who paid" from the system that knows "what they asked."

## Privacy Architecture

```
Stripe (knows identity)              Relay DB (knows queries)
  │                                     │
  │  "jane@email.com paid $5"      "pubkey abc123 asked about housing"
  │  (no query data)                (no identity data)
  │                                     │
  └── webhook ──────────────────────►  credit_ledger (pubkey + balance)
```

- **Stripe** knows who paid but never sees query content
- **The relay** knows what was asked (by pubkey) but never sees payment identity
- **The credit ledger** bridges them with only a pubkey and a balance — no Stripe customer ID, no email, no name

The join between payment identity and query content does not exist in any single database. To violate this, an attacker would need access to both Stripe's customer database and the relay's query logs. This is an architectural boundary, not just a policy.

## How It Works

### Authentication

The user's browser extension signs a Nostr event (kind 24242) using their existing secp256k1 key — the same key used for voicing. No separate account or API key needed.

The relay verifies each request in order:

1. **Replay protection** — Reject timestamps outside a 5-minute window
2. **Signature verification** — Verify the Nostr event signature
3. **Attestation check** — Confirm the user is attested for the jurisdiction
4. **Rate limiting** — Per-pubkey daily limits
5. **API key check** — Confirm the server-side AI provider key is configured

### Endpoints

**`POST /api/ai/draft`** — Single-turn text generation for drafting testimony, comments, or letters.

```json
{
  "prompt": "Draft a comment about the housing proposal on tonight's agenda",
  "system_prompt": "Optional instructions",
  "jurisdiction": "city-san-rafael",
  "public_key": "hex pubkey",
  "signature": "schnorr signature",
  "created_at": 1709865123
}
```

**`POST /api/ai/chat`** — Multi-turn civic Q&A with tool-backed search. Claude receives MCP tool definitions and can query civic data (meetings, decisions, legislation, transcripts) to ground its answers in real local data.

```json
{
  "question": "What happened with the 4th Street rezoning proposal?",
  "jurisdiction": "city-san-rafael",
  "public_key": "hex pubkey",
  "signature": "schnorr signature",
  "created_at": 1709865123
}
```

### Agentic Chat Loop

The `/ai/chat` endpoint runs an agentic loop:

1. Claude receives the user's question and civic tool definitions (fetched from the jurisdiction's MCP server at startup)
2. Claude selects and calls relevant tools (e.g., `search_meeting_history`, `get_public_testimony`)
3. Tool results are fetched via REST from the MCP server and fed back to Claude
4. Claude synthesizes a grounded answer citing specific dates, amounts, and meeting names
5. Up to 3 tool-use turns per request

### Multi-Jurisdiction Routing

The proxy routes requests to the correct MCP server based on jurisdiction. A registry maps jurisdiction IDs to MCP endpoints, so a resident in San Rafael gets civic data from San Rafael's MCP server, while a Berkeley resident gets Berkeley's.

## What Gets Logged

The relay logs the minimum needed for rate limiting and debugging:

| Logged | Not Logged |
|--------|------------|
| First 8 characters of pubkey (truncated) | Full pubkey |
| Jurisdiction | Prompt/question content |
| Tool name used (if any) | Response text |
| Number of agentic turns | User identity |
| Success/error status | |

Prompt content and AI responses are never written to logs or stored in the relay database.

## What the AI Provider Sees

| Sent to Anthropic | Not Sent to Anthropic |
|---|---|
| User's prompt/question | User's Nostr pubkey |
| System prompt | Attestation status |
| MCP tool results (civic data) | Rate limit data |
| | User's jurisdiction (used for routing, not sent in API call) |

## Rate Limiting

- **Per-pubkey:** 20 requests per day (resets at UTC midnight)
- **Chat requests** count as 2x due to multi-turn tool use

Rate limits are in-memory and reset on container restart — acceptable for pilot scale.

## Cost Model

Each AI request costs approximately $0.01-0.02 in API costs. The relay absorbs this during pilot.

### Current (Pilot)

The relay pays API costs directly. The 20 req/day limit bounds exposure. No billing or credit system is active.

### Planned (Production)

A credit-based system will allow residents to purchase additional capacity while maintaining the privacy separation described above — credits are tied to pubkey, not identity. A free daily allowance will preserve the principle that basic civic access doesn't require payment. The credit ledger, Stripe webhook integration, and global cost cap ($5/day) are designed but not yet implemented.
