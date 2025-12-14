# Civic Conversational OS Documentation

**Welcome!** This directory contains all documentation for the Civic Conversational OS platform.

Documentation is organized into 6 tiers by purpose and priority. Start with **Core** docs, then explore other categories as needed.

---

## 🎯 Quick Start (New Developers)

**Read these 3 docs first:**

1. [`core/COMMUNITY_CIVIC_PMF_STRATEGY.md`](core/COMMUNITY_CIVIC_PMF_STRATEGY.md) - **What we're building** (complaint→civic PMF)
2. [`core/API_DOCUMENTATION.md`](core/API_DOCUMENTATION.md) - **How the backend works** (complete API reference)
3. [`core/FRONTEND_TECHNICAL_ARCHITECTURE.md`](core/FRONTEND_TECHNICAL_ARCHITECTURE.md) - **How the frontend works** (workspace architecture)

**Then check current status:**
- [`core/next_session_prompt.md`](core/next_session_prompt.md) - Current implementation status & next tasks

---

## 📚 Documentation Structure

### [`core/`](core/) - **CRITICAL** (6 docs)
**Must-read for any developer working on the platform**

- [`API_DOCUMENTATION.md`](core/API_DOCUMENTATION.md) - Complete API reference (endpoints, schemas, auth)
- [`COMMUNITY_CIVIC_PMF_STRATEGY.md`](core/COMMUNITY_CIVIC_PMF_STRATEGY.md) - Core product strategy (complaint→civic funnel)
- [`FRONTEND_TECHNICAL_ARCHITECTURE.md`](core/FRONTEND_TECHNICAL_ARCHITECTURE.md) - Frontend vision & principles
- [`LLM_PROVIDER_ARCHITECTURE.md`](core/LLM_PROVIDER_ARCHITECTURE.md) - **NEXT**: Provider abstraction layer (OpenAI/Claude/Gemini)
- [`CHAT_STRATEGY_ROADMAP.md`](core/CHAT_STRATEGY_ROADMAP.md) - 4-phase evolution (Navigation → Research → Coach → Orchestrator)
- [`next_session_prompt.md`](core/next_session_prompt.md) - **Current status** & next implementation tasks

**When to read**: Always start here. These 6 docs provide complete context.

---

### [`architecture/`](architecture/) - **SYSTEM ARCHITECTURES** (6 docs)
**Major cross-cutting architectures (multi-feature scope)**

- [`COMMENT_DRAFTING_ARCHITECTURE.md`](architecture/COMMENT_DRAFTING_ARCHITECTURE.md) - AI-powered comment generation (15-part system, Sessions 37-48)
- [`PERSONALIZATION_SERVICE_ARCHITECTURE.md`](architecture/PERSONALIZATION_SERVICE_ARCHITECTURE.md) - Unified user profiles & behavioral inference
- [`CONTEXT_MANAGEMENT_ARCHITECTURE.md`](architecture/CONTEXT_MANAGEMENT_ARCHITECTURE.md) - Chat context registry system (Sessions 51-53)
- [`CHAT_ROUTING_ARCHITECTURE.md`](architecture/CHAT_ROUTING_ARCHITECTURE.md) - OpenAI function calling router (Session 27)
- [`FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md`](architecture/FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md) - Legislative enrichment pipeline
- [`HYBRID_EXTRACTION_RAG_STRATEGY.md`](architecture/HYBRID_EXTRACTION_RAG_STRATEGY.md) - **NEW (Session 99)**: Structured + RAG extraction for scalable decision analysis

**When to read**: Working on features that touch multiple systems (chat, personalization, legislative data).

---

### [`features/`](features/) - **INDIVIDUAL FEATURES** (14 docs)
**Focused feature designs & implementation strategies**

#### Action & Engagement
- [`ACTION_BUTTONS_ARCHITECTURE.md`](features/ACTION_BUTTONS_ARCHITECTURE.md) - Email/calendar/link actions in AI responses
- [`ACTION_ORIENTATION_STRATEGY.md`](features/ACTION_ORIENTATION_STRATEGY.md) - Action-first design principles

#### Personalization & Onboarding
- [`ARCHETYPE_SYSTEM_STRATEGY.md`](features/ARCHETYPE_SYSTEM_STRATEGY.md) - Civic archetype personalization (12 archetypes)
- [`ARCHETYPE_DERIVATION_PROCESS.md`](features/ARCHETYPE_DERIVATION_PROCESS.md) - Visual guide to archetype methodology (LLM-simulated eigenspace)
- [`SWIPE_ONBOARDING_README.md`](features/SWIPE_ONBOARDING_README.md) - Tinder-style swipe onboarding (frontend complete)
- [`SWIPE_ONBOARDING_BACKEND_GUIDE.md`](features/SWIPE_ONBOARDING_BACKEND_GUIDE.md) - Backend endpoints for swipe onboarding

#### Legislative & Validation
- [`LEGISLATIVE_REFERENCE_VALIDATION.md`](features/LEGISLATIVE_REFERENCE_VALIDATION.md) - 99.99% factual accuracy for bill citations (Session 40)
- [`NAVIGATION_MODE_STRUCTURED_OUTPUTS.md`](features/NAVIGATION_MODE_STRUCTURED_OUTPUTS.md) - Structured query parser (design doc)

#### Social & Community
- [`DISCUSSION_PRIVACY_ARCHITECTURE.md`](features/DISCUSSION_PRIVACY_ARCHITECTURE.md) - Privacy tiers for discussions
- [`NESTED_THREADING_IMPLEMENTATION.md`](features/NESTED_THREADING_IMPLEMENTATION.md) - Reddit/Slack-style nested replies (Session 34)
- [`PRIVACY_ARCHITECTURE.md`](features/PRIVACY_ARCHITECTURE.md) - Platform privacy model
- [`SOCIAL_COORDINATION_REFINEMENT_STRATEGY.md`](features/SOCIAL_COORDINATION_REFINEMENT_STRATEGY.md) - Social UX refinement (icons, avatars, threading)
- [`SOCIAL_FOCAL_POINTS_STRATEGY.md`](features/SOCIAL_FOCAL_POINTS_STRATEGY.md) - Thread artifact foundation

#### UI Components
- [`ISSUES_ARTIFACT_REDESIGN_STRATEGY.md`](features/ISSUES_ARTIFACT_REDESIGN_STRATEGY.md) - Issues UX polish
- [`FRONTEND_IMPLEMENTATION_ROADMAP.md`](features/FRONTEND_IMPLEMENTATION_ROADMAP.md) - Layer-by-layer implementation status

**When to read**: Working on a specific feature area.

---

### [`guides/`](guides/) - **HOW-TO GUIDES** (9 docs)
**Setup, deployment, and implementation procedures**

#### Deployment & Integration
- [`DEPLOYMENT_GUIDE.md`](guides/DEPLOYMENT_GUIDE.md) - Production deployment checklist
- [`INTEGRATION_GUIDE.md`](guides/INTEGRATION_GUIDE.md) - System integration instructions
- [`PHASE_3_DEPLOYMENT_GUIDE.md`](guides/PHASE_3_DEPLOYMENT_GUIDE.md) - Regional scale deployment (23 municipalities)

#### Legislative Context Setup
- [`LEGISLATIVE_CONTEXT_SETUP_GUIDE.md`](guides/LEGISLATIVE_CONTEXT_SETUP_GUIDE.md) - Manual legislative context configuration (96-98% precision)
- [`OPEN_STATES_SETUP.md`](guides/OPEN_STATES_SETUP.md) - Open States API setup for legislative metadata verification

#### Personalization Implementation
- [`PERSONALIZATION_IMPLEMENTATION_GUIDE.md`](guides/PERSONALIZATION_IMPLEMENTATION_GUIDE.md) - Step-by-step personalization setup
- [`PERSONALIZATION_IMPLEMENTATION_ROADMAP.md`](guides/PERSONALIZATION_IMPLEMENTATION_ROADMAP.md) - 4-5 week timeline (Phases 1-5)
- [`PERSONALIZATION_AUDIT_REPORT.md`](guides/PERSONALIZATION_AUDIT_REPORT.md) - Architecture audit (3 critical issues fixed Oct 29)

#### Testing
- [`FRONTEND_TESTING_GUIDE.md`](guides/FRONTEND_TESTING_GUIDE.md) - Frontend testing procedures

**When to read**: Setting up, deploying, or implementing a specific subsystem.

---

### [`platforms/`](platforms/) - **PLATFORM INTEGRATIONS** (5 docs)
**Municipal platform-specific implementations**

- [`CDP_ACCESS_GUIDE.md`](platforms/CDP_ACCESS_GUIDE.md) - Council Data Project integration (video transcripts, anonymous access)
- [`GRANICUS_IMPLEMENTATION.md`](platforms/GRANICUS_IMPLEMENTATION.md) - Granicus ViewPublisher client (2 cities)
- [`LEGISTAR_AGENDA_INTEGRATION.md`](platforms/LEGISTAR_AGENDA_INTEGRATION.md) - Legistar API integration (6 cities, 65% parse rate)
- [`MUNICIPAL_PARSING_LESSONS.md`](platforms/MUNICIPAL_PARSING_LESSONS.md) - Lessons learned from municipal systems
- [`INTERACTIVE_STRESS_TESTING_GUIDE.md`](platforms/INTERACTIVE_STRESS_TESTING_GUIDE.md) - Platform stress testing procedures

**When to read**: Debugging platform-specific issues or adding new municipal platforms.

---

### [`pilot/`](pilot/) - **PILOT VALIDATION** (NEW)
**San Rafael Decision Awareness pilot planning and execution**

- [`PILOT_ROADMAP.md`](pilot/PILOT_ROADMAP.md) - **START HERE**: Timeline, phases, success criteria (Nov-Dec tech optimization → Jan pilot)
- [`SESSION_96_DECISION_BRIEF.md`](pilot/SESSION_96_DECISION_BRIEF.md) - Oct 6 Wildfire Fund case study analysis
- [`DATA_QUALITY_AUDIT.md`](pilot/DATA_QUALITY_AUDIT.md) - Retrospective data validation

**When to read**: Understanding pilot timeline, preparing for January execution, or reviewing validation strategy.

---

### [`strategy/`](strategy/) - **BUSINESS STRATEGY** (5 docs)
**High-level strategic planning**

#### **Session 94 Strategic Framework** (November 2024)
- [`COMPETITIVE_POSITIONING.md`](strategy/COMPETITIVE_POSITIONING.md) - **Why not ChatGPT?** Intelligence vs. coordination
- [`FOCAL_POINT_DECISION_AWARENESS.md`](strategy/FOCAL_POINT_DECISION_AWARENESS.md) - **Pilot strategy** (Decision Awareness hypothesis)
- [`FOUNDATION_FUNDING_THESIS.md`](strategy/FOUNDATION_FUNDING_THESIS.md) - **Why foundation-funded?** Sustainability model justification

#### Platform & Infrastructure
- [`RESILIENCE_STRATEGY.md`](strategy/RESILIENCE_STRATEGY.md) - Multi-platform resilience (5 platform types)
- [`SUSTAINABLE_BUSINESS_MODEL.md`](strategy/SUSTAINABLE_BUSINESS_MODEL.md) - Foundation funding model ($50-100K annual grants)

**When to read**: Planning long-term infrastructure or preparing grant proposals. **Start with the Session 94 framework (COMPETITIVE_POSITIONING, FOCAL_POINT, FOUNDATION_FUNDING) for current strategic direction.**

---

### [`archive/`](archive/) - **HISTORICAL REFERENCE**
**Superseded, outdated, or session-specific documentation**

- `archive/sessions/` - Session summaries (Sessions 34-60)
- `archive/analysis/` - Implementation analysis & reviews (completed work)
- `archive/outdated/` - Docs using deprecated "complaint" terminology (now "issues")
- `archive/strategy/` - Early strategy docs (superseded by current strategy)
- `archive/platforms/` - Outdated platform data (CIVIC_DATA_INGESTION_STRATEGY.md)

**When to read**: Looking for historical context or understanding past decisions.

---

## 🗂️ Documentation by Use Case

### "I'm a new developer joining the project"
1. Read [`core/COMMUNITY_CIVIC_PMF_STRATEGY.md`](core/COMMUNITY_CIVIC_PMF_STRATEGY.md) - Understand the vision
2. Read [`core/API_DOCUMENTATION.md`](core/API_DOCUMENTATION.md) - Learn the API
3. Read [`core/FRONTEND_TECHNICAL_ARCHITECTURE.md`](core/FRONTEND_TECHNICAL_ARCHITECTURE.md) - Understand the frontend
4. Check [`core/next_session_prompt.md`](core/next_session_prompt.md) - See current status

### "I'm implementing a new feature"
1. Check [`core/next_session_prompt.md`](core/next_session_prompt.md) - Avoid duplicate work
2. Browse [`features/`](features/) - Find similar features for patterns
3. Read relevant [`architecture/`](architecture/) docs - Understand cross-cutting concerns
4. Check [`guides/`](guides/) - Find setup/testing procedures

### "I'm debugging a platform integration issue"
1. Check [`platforms/`](platforms/) - Find platform-specific docs
2. Read [`platforms/MUNICIPAL_PARSING_LESSONS.md`](platforms/MUNICIPAL_PARSING_LESSONS.md) - Learn from past issues
3. See [`core/API_DOCUMENTATION.md`](core/API_DOCUMENTATION.md) - Verify API contracts

### "I'm deploying to production"
1. Read [`guides/DEPLOYMENT_GUIDE.md`](guides/DEPLOYMENT_GUIDE.md) - Deployment checklist
2. Check [`guides/PHASE_3_DEPLOYMENT_GUIDE.md`](guides/PHASE_3_DEPLOYMENT_GUIDE.md) - Regional scale guidance
3. Review [`strategy/RESILIENCE_STRATEGY.md`](strategy/RESILIENCE_STRATEGY.md) - Multi-platform resilience

### "I'm preparing a grant proposal"
1. **Start here**: [`strategy/COMPETITIVE_POSITIONING.md`](strategy/COMPETITIVE_POSITIONING.md) - Why coordination is the moat
2. Read [`strategy/FOUNDATION_FUNDING_THESIS.md`](strategy/FOUNDATION_FUNDING_THESIS.md) - Why foundation-funded (full justification)
3. Read [`strategy/FOCAL_POINT_DECISION_AWARENESS.md`](strategy/FOCAL_POINT_DECISION_AWARENESS.md) - Pilot validation strategy
4. Read [`core/COMMUNITY_CIVIC_PMF_STRATEGY.md`](core/COMMUNITY_CIVIC_PMF_STRATEGY.md) - Orchestration vision & three-tier model
5. Check [`guides/PHASE_3_DEPLOYMENT_GUIDE.md`](guides/PHASE_3_DEPLOYMENT_GUIDE.md) - Current scale metrics

---

## 📊 Documentation Statistics

- **Total active docs**: 45
- **Core (critical)**: 6 docs
- **Architecture**: 5 docs
- **Features**: 15 docs
- **Guides**: 9 docs
- **Platforms**: 5 docs
- **Strategy**: 5 docs (+3 from Session 94 strategic framework)
- **Archived**: 24 docs (historical reference)

---

## 🔍 Finding Documentation

**By topic:**
- Chat/AI: [`core/`](core/), [`architecture/CHAT_ROUTING_ARCHITECTURE.md`](architecture/CHAT_ROUTING_ARCHITECTURE.md)
- Comment drafting: [`architecture/COMMENT_DRAFTING_ARCHITECTURE.md`](architecture/COMMENT_DRAFTING_ARCHITECTURE.md)
- Legislative context: [`architecture/FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md`](architecture/FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md)
- Personalization: [`architecture/PERSONALIZATION_SERVICE_ARCHITECTURE.md`](architecture/PERSONALIZATION_SERVICE_ARCHITECTURE.md), [`guides/PERSONALIZATION_*.md`](guides/)
- Social features: [`features/SOCIAL_*.md`](features/), [`features/NESTED_THREADING_IMPLEMENTATION.md`](features/NESTED_THREADING_IMPLEMENTATION.md)
- Platforms: [`platforms/`](platforms/)

**By phase:**
- Current work: [`core/next_session_prompt.md`](core/next_session_prompt.md)
- **Pilot timeline**: [`pilot/PILOT_ROADMAP.md`](pilot/PILOT_ROADMAP.md) - Nov-Dec tech → Jan pilot
- Future roadmap: [`core/CHAT_STRATEGY_ROADMAP.md`](core/CHAT_STRATEGY_ROADMAP.md)
- Implementation timeline: [`features/FRONTEND_IMPLEMENTATION_ROADMAP.md`](features/FRONTEND_IMPLEMENTATION_ROADMAP.md)

---

## 🤝 Contributing to Documentation

When creating new documentation:

1. **Choose the right tier:**
   - Core strategy/API changes → `core/`
   - New cross-cutting architecture → `architecture/`
   - Feature-specific design → `features/`
   - Setup/deployment procedure → `guides/`
   - Platform integration → `platforms/`
   - Business/funding strategy → `strategy/`

2. **Update this README** - Add links to new docs in appropriate sections

3. **Use consistent format:**
   - Clear title & overview
   - Status/date metadata
   - Code examples where relevant
   - Cross-references to related docs

4. **Archive when superseded:**
   - Move to `archive/` with explanation
   - Update cross-references
   - Preserve git history with `git mv`

---

**Last Updated**: 2024-11-27 (Session 121 - Added pilot/ section, PILOT_ROADMAP.md)
**Documentation Version**: 2.2 (Added pilot validation section)
