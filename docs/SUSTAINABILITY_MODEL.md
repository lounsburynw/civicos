# Civic Sustainability Model

**Status:** Strategic exploration (Session 481, Jan 2026)

## Core Insight

Sustainable funding is a feature of the mission, not a betrayal of it. The false dichotomy of "free and virtuous" vs "paid and extractive" ignores the reality that unfunded projects die or get acquired by entities that don't share the mission (see: Open States → SAI360, Dec 2025).

## Lessons from Open States

```
Sunlight Foundation (nonprofit) → shutdown 2016
         ↓
Open States (independent nonprofit)
         ↓
Merged with Plural (VC-backed, 2021)
         ↓
Plural raises $10M Series A (2023)
         ↓
SAI360 acquisition (PE-backed, Dec 2025)
```

The VC path led to PE acquisition. "Self-sustainable business" didn't prevent adversarial takeover—it made the company attractive to acquirers. VCs need exits.

## Actual Costs (Single Municipality)

| Service | Est. Cost/mo | Notes |
|---------|-------------|-------|
| Supabase | $25+ | Pro tier for production |
| AssemblyAI | $50-150 | ~$0.37/min transcription |
| Modal | $20-50 | Compute for jobs |
| AI providers | $30-100 | Embeddings, LLM calls |
| LegiScan | $0 | Free tier (30k queries/mo) |
| Dev tooling | $20 | Claude Code, etc. |
| **Total** | **$150-350/mo** | Per municipality |

At 10 cities with economies of scale: ~$500-1000/mo. Bootstrappable but real money.

## Funding Model Options

| Model | Pros | Failure Mode |
|-------|------|--------------|
| Foundation grants | Mission-aligned, no monetization pressure | Grant cycles, foundation pivots |
| VC → for-profit | Growth capital | Exit pressure → acquisition |
| Municipal contracts | Aligned incentives | Slow procurement, political cycles |
| Citizen subscriptions | Self-sustaining, aligned | Requires genuine value prop |
| Cooperative/membership | Community ownership | Hard to bootstrap |

## Recommended Approach: Freemium

### Free Tier (Civic Right)

Information access should not be paywalled. The free tier ensures information asymmetry doesn't worsen.

- **Discovery:** What's happening (meetings, decisions, issues)
- **Representation:** Who represents me at all levels
- **Search:** Basic search and discovery
- **Records:** Public record access
- **Core API:** `whats_next()`, `what_happened()`, `what_applies()`

### Paid Tier (Civic Power)

The paid tier funds infrastructure and rewards the work of making civic data *actionable*.

- **Preparation:** `prepare()` - testimony drafting, meeting prep materials
- **Coordination:** `whos_with_me()` - coalition finding, ally discovery
- **Alerts:** Notifications on specific properties, topics, or officials
- **Priority:** Expedited transcription requests
- **API Access:** Higher rate limits for advocacy organizations
- **Professional:** Tools for lobbyists, developers, lawyers who already pay for this data

### Pricing Ideas (TBD)

- Individual: $10/mo or pay-per-use ($2-5 per `prepare()` call)
- Professional: $50-100/mo (advocacy orgs, law firms)
- Municipal license: $500-2000/mo (city deploys for all residents)

## What Would Citizens Pay For?

Civic engagement is a "should" not a "want." But some features cross over:

| Feature | Who Pays | Why They'd Pay |
|---------|----------|----------------|
| Property/street alerts | Homeowners | Protect investment |
| Development opposition/support tools | NIMBYs, YIMBYs | High stakes |
| Public comment drafting | Anyone testifying | Saves time, reduces anxiety |
| Neighbor coalition finding | Issue advocates | Coordination is genuinely hard |
| Permit navigation | Contractors, homeowners | Saves lawyer fees |

The key insight: people pay when they have **skin in the game**. A $500k property, a proposed development next door, a business permit—these create motivation to pay for tools that help.

## Strategic Principles

1. **Free tier is non-negotiable.** Basic civic information is a right, not a product.

2. **Paid features must deliver real value.** Not artificial scarcity—genuine capability that costs money to provide (AI, compute, curation).

3. **Avoid VC if possible.** Exit pressure corrupts mission. Bootstrap or seek aligned capital (foundations, municipal contracts, cooperative membership).

4. **Price for sustainability, not extraction.** Cover costs + modest margin. This isn't a unicorn play.

5. **Municipal contracts as anchor.** If San Rafael pilot succeeds, city contracts provide stable base revenue. Citizen subscriptions provide growth.

## Open Questions

- What's the minimum viable paid feature that proves willingness to pay?
- Can `prepare()` be good enough that someone would pay $5 to use it before a hearing?
- Is there a cooperative/membership model that works? (Patreon for civic infra?)
- How do we handle the "I'd pay but I'm broke" equity concern?

## Next Steps

1. Validate: Interview 5-10 people who've testified at city council. Would they pay for prep help?
2. Prototype: Build a standalone `prepare()` flow with clear value prop
3. Test: Offer it for $5 during a contentious San Rafael hearing
4. Learn: Did anyone pay? Why or why not?

---

*This document captures strategic thinking from Session 481. It's a living document, not a final plan.*
