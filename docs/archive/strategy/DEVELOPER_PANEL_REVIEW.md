# Developer Panel Review: Package Architecture

**Format**: Simulated open-source developer panel
**Focus**: Maintainability, contributor experience, operational concerns

---

## Panel Members

| Name | Archetype | Background |
|------|-----------|------------|
| **Sam** | Pragmatist | 15 years, maintains 3 popular OSS projects |
| **Priya** | API Designer | Ex-Stripe, obsessed with developer experience |
| **Marcus** | Ops/SRE | Runs infrastructure for civic tech nonprofit |
| **Kenji** | New Contributor | 2 years experience, wants to contribute |
| **Dana** | Scale Skeptic | Worked on gov.uk, seen civic tech fail at scale |
| **Alex** | Minimalist | XP practitioner, YAGNI advocate |

---

## Opening Statements

### Sam (Pragmatist)
> "I count 7 packages in the final architecture. That's 7 repos, 7 CI pipelines, 7 versioning schemes, 7 changelogs. My question before anything else: **do you have 7 maintainers?** Because in my experience, packages without dedicated owners become zombies."

### Priya (API Designer)
> "I like the query-centric surface layer. `civic-context.get_regulatory_stack()` reads like English. But I'm concerned about **cognitive load**. A new user needs to understand: context vs precedent vs engage vs coordinate. That's 4 concepts before they write a line of code. Can we get to 2?"

### Marcus (Ops)
> "The data layer concerns me. You have ChromaDB, PostgreSQL, and document storage. That's 3 different persistence layers to backup, monitor, and restore. **What's your disaster recovery story?** And who's on-call when the Municode scraper breaks at 2am?"

### Kenji (New Contributor)
> "I want to add support for my city (Austin, TX). Looking at this architecture, I need to:
> 1. Create a jurisdiction config
> 2. Maybe write a new corpus provider if Municode doesn't work
> 3. Understand the decision extraction pipeline
> 4. Test across 4 packages
>
> **That's a lot.** I was hoping I could just add a config file."

### Dana (Scale Skeptic)
> "I've seen this movie before. You build beautiful abstractions for 26 California cities, then someone wants to add New York City and **everything breaks**. NYC has 59 community boards, 5 borough presidents, a city council, AND a mayor. Your `jurisdiction` model assumes a simple city council. What's your extensibility story?"

### Alex (Minimalist)
> "Let me count the features I see:
> - Regulatory stack lookup
> - Preemption checking
> - Precedent search
> - Jurisdiction comparison
> - Commitment tracking
> - Coalition formation
> - Testimony coordination
>
> **How many of these have validated user demand?** I'd ship with 2 features and add the rest when users ask. You're building a Swiss Army knife before you know if anyone needs to cut anything."

---

## Deep Dive: Specific Concerns

### 1. Package Boundaries (Sam)

> "Your civic-context depends on civic-corpus. Civic-corpus depends on... nothing? Oh wait, it needs civic-activity for meeting data. And civic-coordinate needs civic-activity AND civic-precedent. Let me draw this:"

```
civic-context ──► civic-corpus
                      │
civic-precedent ──► civic-decisions ──► civic-activity
                      │
civic-engage ─────────┴──► civic-activity
                                │
civic-coordinate ──► civic-precedent
                 └──► civic-activity
```

> "You have a **diamond dependency**. civic-coordinate needs civic-activity both directly AND through civic-precedent. What happens when you update civic-activity? You need to update 4 packages in the right order. This is npm left-pad waiting to happen."

**Recommendation**: Consider a monorepo with internal packages, not separate repos.

---

### 2. Versioning Hell (Sam)

> "What's the versioning strategy? If civic-corpus is v2.3.1 and civic-context is v1.4.0, which combinations are compatible? You need a **compatibility matrix** or you need **lockstep versioning** (all packages same version)."

**Recommendation**: Use lockstep versioning. All packages share version number. Release together.

---

### 3. The "God Object" Risk (Priya)

> "I notice `civic-context.get_regulatory_stack()` returns federal, state, county, and municipal data. That's a **God Object** - one call that knows everything. What if I only want municipal? Am I paying the latency cost for federal lookups I don't need?"

```python
# Current design - all or nothing?
stack = ctx.get_regulatory_stack(topic="adu")

# Better - explicit levels
stack = ctx.get_regulatory_stack(
    topic="adu",
    levels=["municipal", "state"]  # Skip federal/county
)

# Or separate methods
municipal = ctx.get_municipal_code(topic="adu")
state = ctx.get_state_law(topic="adu")
```

**Recommendation**: Allow level filtering, or expose level-specific methods. Don't hide everything.

---

### 4. Configuration Sprawl (Kenji)

> "The jurisdiction config has 5 different sections:
> - Basic info
> - Municipal code source
> - General plan source
> - Activity platform
> - Decision sources
>
> **That's a lot of YAML for a new contributor to get right.** What's the minimum viable config? Can I add a city with just an ID and have sensible defaults?"

```yaml
# Ideal: minimal config with smart defaults
jurisdiction:
  id: "austin-tx"
  state: "TX"
  # Everything else auto-discovered or defaulted
```

**Recommendation**: Implement a "discovery" mode that auto-detects sources. Config only for overrides.

---

### 5. Testing Nightmare (Marcus)

> "How do I test civic-context in CI? It needs:
> - A Municode response (or mock)
> - A state codes response (or mock)
> - ChromaDB running
> - PostgreSQL running
> - Fixture data for each level
>
> **Your test matrix is N cities × M levels × P features.** At 26 cities, 4 levels, and 7 features, that's 728 test scenarios. Are you mocking everything? If so, how do you know the mocks match reality?"

**Recommendation**:
1. Contract testing between layers
2. One "golden city" with full integration tests
3. Other cities only test config parsing

---

### 6. The Extensibility Trap (Dana)

> "Your municipal code fetcher assumes Municode. But here's reality:
> - Some cities use American Legal Publishing
> - Some use Code Publishing Company
> - Some have their own systems
> - Some have **no digital code at all**
>
> And that's just municipal code. For activity tracking:
> - CivicClerk
> - Legistar
> - Granicus
> - BoardDocs
> - Custom systems
>
> **You need a provider abstraction**, not hard-coded fetchers."

```python
# Bad: hard-coded providers
class MunicipalCorpus:
    def fetch(self, jurisdiction):
        return self.municode_client.get(...)

# Better: pluggable providers
class MunicipalCorpus:
    def __init__(self, provider: CodeProvider):
        self.provider = provider

    def fetch(self, jurisdiction):
        return self.provider.get(...)

# Registry of providers
PROVIDERS = {
    "municode": MunicodeProvider,
    "american_legal": AmericanLegalProvider,
    "custom": CustomProvider,
}
```

**Recommendation**: Provider pattern from day one. Even if you only have one provider initially.

---

### 7. YAGNI Violations (Alex)

> "Let me highlight features I'd cut for v1:

| Feature | Why Cut |
|---------|---------|
| `compare_jurisdictions()` | Cool but not core. Add when requested. |
| `track_commitment()` | Complex (needs budget integration). Phase 2. |
| `form_coalition()` | Social features are hard. Prove value first. |
| `amplify()` | Same as above. |
| `check_preemption()` | Legally complex. Get it wrong = liability. |
| County level | Most users only care about their city. |

> **v1 should be:**
> - `get_applicable_law(topic, city)` - What rules apply
> - `search_decisions(query, city)` - What's been decided
> - `get_upcoming(city)` - When to show up
>
> That's it. Three functions. Ship it."

**Recommendation**: Ruthlessly cut scope. You can always add features, but you can't easily remove them from a published API.

---

## Suggested Revisions

### From the Panel's Feedback

1. **Monorepo over multi-repo** (Sam)
   ```
   civic/
   ├── packages/
   │   ├── context/
   │   ├── corpus/
   │   ├── activity/
   │   └── decisions/
   └── pyproject.toml  # Workspace root
   ```

2. **Lockstep versioning** (Sam)
   - All packages share version: `2024.11.1`
   - Release all together or none

3. **Provider abstraction** (Dana)
   - Abstract data sources from day one
   - Makes contributor onboarding easier

4. **Minimal v1 API** (Alex)
   ```python
   # The entire v1 public API
   from civic import Civic

   c = Civic("san-rafael-ca")

   c.what_applies(topic="housing")     # Regulatory stack
   c.what_happened(query="wildfire")   # Decision search
   c.whats_next(topics=["housing"])    # Upcoming meetings
   ```

5. **Smart defaults with override config** (Kenji)
   ```yaml
   # Minimal
   jurisdiction: austin-tx

   # Only override what's non-standard
   overrides:
     municipal_code:
       provider: american_legal
   ```

6. **Contract testing** (Marcus)
   - Define interfaces between layers
   - Mock at boundaries, integration test one "golden city"

---

## Revised Architecture Proposal

Based on panel feedback:

```
┌─────────────────── PUBLIC API (v1) ─────────────────────┐
│                                                          │
│  civic.what_applies(topic)    → Regulatory stack        │
│  civic.what_happened(query)   → Decision search         │
│  civic.whats_next(topics)     → Upcoming meetings       │
│                                                          │
│  (civic.coordinate deferred to v2)                      │
│                                                          │
└──────────────────────────┬───────────────────────────────┘
                           │
┌─────────────────── INTERNAL PACKAGES ───────────────────┐
│                                                          │
│  civic._corpus      Legal text (provider-abstracted)    │
│  civic._decisions   Historical decisions                │
│  civic._activity    Meetings, agendas                   │
│                                                          │
│  All internal - can refactor without breaking users     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Key Changes

| Original | Revised | Rationale |
|----------|---------|-----------|
| 4 user-facing packages | 1 package, 3 methods | Simpler mental model |
| civic-coordinate | Deferred to v2 | Social features need validation |
| Separate repos | Monorepo | Easier versioning |
| Level-specific sub-packages | Provider abstraction | Extensibility |
| County in v1 | Deferred | YAGNI - validate city-only first |

---

## Panel Vote

| Panelist | Original | Revised | Notes |
|----------|----------|---------|-------|
| Sam | 👎 | 👍 | "Monorepo saves your sanity" |
| Priya | 🤔 | 👍 | "3 methods is learnable" |
| Marcus | 👎 | 🤔 | "Still worried about ChromaDB ops" |
| Kenji | 👎 | 👍 | "I can add a city now!" |
| Dana | 🤔 | 👍 | "Provider pattern is right" |
| Alex | 👎 | 👍 | "This is shippable" |

**Consensus**: Revised architecture is shippable. Original was over-engineered for current stage.

---

## Action Items from Panel

1. [ ] Consolidate to monorepo with internal packages
2. [ ] Define minimal v1 API (3 methods)
3. [ ] Implement provider abstraction for data sources
4. [ ] Create "golden city" integration test suite
5. [ ] Build auto-discovery for jurisdiction config
6. [ ] Defer coordination features to v2
7. [ ] Defer county level to v2

---

*Panel review complete. Recommend proceeding with revised architecture.*
