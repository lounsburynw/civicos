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

## Open Source Strategy

### Code: PolyForm Noncommercial 1.0.0

The codebase is source-available under PolyForm Noncommercial:
- Full transparency builds trust (critical for civic infrastructure)
- Individuals, nonprofits, and academic institutions can use freely
- For-profit companies require commercial license
- Moat is operations and data freshness, not code secrecy
- Revenue from commercial licenses funds free tier sustainability

### The WordPress Model (Adapted)

WordPress is GPL. We use PolyForm Noncommercial which is more restrictive—companies must license commercially. But the core dynamic is similar: code transparency builds trust, but operating the service well is the real value.

```
Code (source-available) →  Free for individuals/nonprofits, licensed for companies
Data curation           →  Ongoing operational cost
Hosted service          →  The paid product
```

### Contributor Model: The Scaling Strategy

**The original vision:** Open source community contributes municipal-specific parsers (Legistar, Granicus, custom formats). This scales Civic to many cities without building every parser internally.

**The tension:** "Why contribute free labor if Civic profits?"

**The social contract:**

| Contributor Gives | Contributor Gets |
|-------------------|------------------|
| Municipal parser (Oakland, Austin, etc.) | Free premium access for that city |
| Bug fixes, core improvements | Recognition + platform access |
| Data quality feedback | Their city works better |
| Documentation, guides | Community standing |

**Why this works:**

1. **Parsers are infrastructure, not product.** The product is fresh, reliable, *operated* data. A parser extracts data once; operating it forever is the hard part.

2. **Contributors benefit from network effects.** Your Oakland parser connects to state legislation, federal data, cross-city patterns. That's the platform value.

3. **The Wikipedia dynamic.** Editors contribute freely because content is freely available and the organization is mission-aligned. Contributors aren't exploited when the mission is genuine.

4. **Self-interest alignment.** If I want Civic for my city, I can either pay or contribute. Both are fair exchanges.

### Corporate Structure: Public Benefit Corporation

To credibly promise contributors their work won't be strip-mined by PE in 5 years, the corporate structure matters.

**Public Benefit Corporation (PBC):**
- Legally required to balance profit with public benefit
- Directors can prioritize mission over shareholder returns
- Signals long-term alignment to contributors and users
- Examples: Kickstarter, Patagonia, Allbirds

This isn't just idealism—it's a competitive advantage for recruiting contributors who've seen what happened to Open States.

## Capital Strategy

### The Goal
Raise enough to build and operate without exit pressure or mission drift.

### The Portfolio Approach

No single funding source. Diversified, resilient:

| Source | Amount/yr | Stage | Exit Pressure |
|--------|-----------|-------|---------------|
| OpenCollective | $20-50k | Now | None |
| Foundation PRIs | $50-100k | Now | None |
| Revenue-share financing | $50-200k | With revenue | Low (capped) |
| Municipal contracts | $50-200k | Post-pilot | None |
| Citizen subscriptions | TBD | Post-validation | None |
| Strategic angels | $25-100k | Seed | Low (if aligned) |

### OpenCollective

Transparent community fundraising for open source. All transactions public.

**Why it fits:**
- Radical transparency aligns with civic trust mission
- No equity, no exit pressure
- Corporate sponsors (cities, advocacy orgs, civic companies)
- Fiscal host (Open Collective Foundation) = 501c3 tax-deductible

**Realistic range:** $20-50k/year once community exists. Complement, not sole source.

**Examples:** webpack (~$400k/yr), Babel, Vue.js

### Revenue-Based Financing

Pay back as % of revenue until capped multiple returned.

**Providers:** Earnest Capital, Calm Company Fund, Clearco, Lighter Capital

**Structure:** e.g., 5% of monthly revenue until 1.5-3x returned

**Why it works:** No equity, no board seats, no exit pressure. Aligned with sustainable growth.

**Requirement:** Need revenue first (post-freemium validation).

### Program-Related Investments (PRIs)

Foundation investments expecting capital return (not market return).

**Potential sources:**
- Knight Foundation (journalism, civic tech)
- Omidyar Network (civic tech, governance)
- Luminate (civic empowerment)
- Democracy Fund
- Craig Newmark Philanthropies

**Terms:** Often 0-2% interest, 5-10 year horizon, very patient.

**Fit:** Civic is exactly what these foundations fund.

### Community Round (Wefunder/Republic)

Crowdfunded equity from many small investors.

**Pros:**
- No single investor can force exit
- Community ownership (aligned with mission)
- Builds advocates

**Cons:**
- Regulatory overhead
- Still equity (some exit expectation)
- Need compelling story

**Range:** $50k-$1M typical for civic tech.

### Strategic Angels

Individuals who care about civic tech, not just returns.

**Examples of civic-aligned angels:**
- Craig Newmark (craigslist founder, funds civic tech)
- Esther Dyson (civic tech investor)
- Local civic leaders who believe in the mission

**Why better than VC:** No LP pressure, can be patient forever, often want to help not control.

### What NOT to Take

- Traditional VC expecting 10x+ returns and exit in 5-7 years
- Investors who don't understand "sustainable, not unicorn"
- Money with board seats / veto rights over mission
- Capital that requires hypergrowth to justify

### Legal Protection

All of the above is strengthened by:

**Public Benefit Corporation (PBC):**
- Directors legally must balance profit with mission
- Acquirers can't strip-mine without liability
- Signals to all investors: "this isn't a flip"

## Open Questions

- What's the minimum viable paid feature that proves willingness to pay?
- Can `prepare()` be good enough that someone would pay $5 to use it before a hearing?
- Is there a cooperative/membership model that works? (Patreon for civic infra?)
- How do we handle the "I'd pay but I'm broke" equity concern?
- What's the right contributor recognition system? (GitHub-style contributions graph? Contributor tiers?)

## Next Steps

1. Validate: Interview 5-10 people who've testified at city council. Would they pay for prep help?
2. Prototype: Build a standalone `prepare()` flow with clear value prop
3. Test: Offer it for $5 during a contentious San Rafael hearing
4. Learn: Did anyone pay? Why or why not?

---

*This document captures strategic thinking from Session 481. It's a living document, not a final plan.*
