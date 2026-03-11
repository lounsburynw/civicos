# What's Live

Current production status of CivicOS services and features. Updated March 2026.

## Services

| Service | Status | URL |
|---------|--------|-----|
| REST API | **Live** | Deployed on Modal |
| MCP Server | **Live** | Deployed on Modal — connect from Claude Desktop or ChatGPT |
| Relay | **Live** | Deployed on Modal — signature verification enforced on all writes |
| Browser Extension | **Live** | Chrome Web Store (San Rafael pilot) |
| Signer | **Live** | Deployed on Modal — multi-issuer attestation signing |

## Pilot: San Rafael, CA

| Corpus | Records | Source | Indexed |
|--------|---------|--------|---------|
| Meetings | ~98 | ProudCity (city website) | Yes |
| Decisions | ~44 | Minutes extraction | Yes |
| Transcripts | ~19 | YouTube + AssemblyAI | Yes |
| Agenda packets (PDF chunks) | ~5,084 | City agenda PDFs | Yes |
| Municipal code | ~16,175 | Municode | Yes |
| Community issues | ~1,730 | SeeClickFix (311) | Yes |
| Budget items | ~58 | FY25-26 budget PDF | Yes |
| Legislation | ~17,719 | LegiScan (CA + federal) | Yes |

**Total vector embeddings:** ~16,800 (semantic search across all corpora)

## Acceptance Policy (Relay Writes)

The relay enforces a tiered acceptance policy on all write endpoints:

| Tier | Status | Description |
|------|--------|-------------|
| **Rate limiting** | **Active** | Per-event-type daily limits (PostgreSQL-backed). Free tier with sybil resistance. |
| **Attestation verification** | **Stubbed** | `attestation_proof` field accepted on all requests. Verification logic designed but returns false — all writes fall through to rate limiting. |
| **Payment proof** | **Stubbed** | `payment_proof` field accepted on all requests. Verification logic designed but returns false — all writes fall through to rate limiting. |

Signature verification is **mandatory** on all write endpoints. The `coincurve` library is a hard dependency — missing it is a startup error, not a silent fallback.

## API Access

| Tier | Status | Description |
|------|--------|-------------|
| Free (rate-limited) | **Live** | 60 requests/minute, in-memory rate limiting |
| Paid (API key) | **Live** | Stripe checkout flow active. Key delivery is currently manual — automated delivery planned. |
| MCP tool-level gating | **Planned** | Tool-level tier enforcement is defined but not yet active at the MCP endpoint level. Currently all authenticated users can access all non-admin tools. |

## Features by Surface

### Browser Extension
| Feature | Status |
|---------|--------|
| Civic dashboard (meetings, decisions, budgets) | **Live** |
| Voice casting (support/oppose/watching) | **Live** |
| AI-assisted testimony drafting | **Live** |
| Community issues map | **Live** |
| Local identity (Nostr keys) | **Live** |
| Attestation code redemption | **Live** |

### MCP Server
| Feature | Status |
|---------|--------|
| 50+ read-only civic data tools | **Live** |
| Semantic search across all corpora | **Live** |
| Write tools | **Removed** — all writes go through the relay directly |

### Relay
| Feature | Status |
|---------|--------|
| Voice casting + counts | **Live** |
| Civic actions (commit/complete) | **Live** |
| Initiatives | **Live** |
| Comments | **Live** |
| Subscriptions | **Live** |
| AI Proxy (authenticated AI for residents) | **Live** (free daily allowance; credit purchase planned) |
| Federation / relay sync | **Live** |
| NIP-13 proof-of-work (sybil resistance) | **In progress** |

## Data Ingestion Platforms

Parsers that are built and tested:

| Platform | Type | Status |
|----------|------|--------|
| ProudCity | Web scraper | **Active** (San Rafael) |
| Granicus | API | **Active** (Marin County) |
| Legistar | API | **Ready** (Berkeley, Oakland, SF, Richmond, Hayward, San Pablo) |
| CivicClerk | API + OData | **Ready** (El Cerrito, Hayward, San Pablo, Richmond, Vallejo, Antioch) |
| SeeClickFix | API | **Active** (San Rafael) |
| LegiScan | API | **Active** (CA + federal) |
| Municode | Web | **Active** (San Rafael) |
| YouTube Boards | Web/API | **Active** (meeting transcripts) |
| Federal Register | API | **Ready** |
| USAspending | API | **Ready** |

**Active** = running in production for at least one jurisdiction. **Ready** = parser built, tested, awaiting jurisdiction config.

## What's Next

Current development priorities (launch phase):

- Automated API key delivery (Stripe webhook integration)
- Attestation verification enforcement (wire the stub into the acceptance policy)
- NIP-13 proof-of-work for free-tier sybil resistance
- Per-IP HTTP rate limiting on the relay
- Second jurisdiction (Berkeley) to validate replication process

See the project [GitHub repository](https://github.com/lounsburynw/civicos) for detailed progress tracking.
