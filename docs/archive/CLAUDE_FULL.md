# CLAUDE.md

Guidance for Claude Code when working with the Civic Conversational OS platform.

## Project Overview

**Conversational Operating System for Local Democracy** - Foundation-funded civic infrastructure that transforms municipal data into actionable opportunities through multi-platform extraction and AI-powered agenda parsing.

**Core Positioning**: "We turn complaints into civic power" - bridging operational 311 systems to policy engagement

**Strategic Focus**: Decision Awareness (see `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md`)
- **Hypothesis**: Residents don't participate because they lack awareness of high-stakes decisions + coordination infrastructure
- **Approach**: Retrospective analysis (12 months) → Automation → Pilot validation
- **Validation**: Oct 6 Wildfire Fund case study (24 complaints → policy decision, measurable gap)
- **Phase 5 Complete**: San Rafael longitudinal analysis (1,340 complaints) identifies key corridors + 94% accountability gap
- **Moat**: Coordination infrastructure, not intelligence (see `docs/strategy/COMPETITIVE_POSITIONING.md`)
- **Model**: Foundation-funded public good ($50-100K/year/region, see `docs/strategy/FOUNDATION_FUNDING_THESIS.md`)
- **Pilot City**: San Rafael (hometown, complete SeeClickFix data, geographic corridors identified)
- **Timeline**: Technical optimization (Nov-Dec 2024) → Pilot execution (Jan 2025) - see `docs/pilot/PILOT_ROADMAP.md`

**SeeClickFix Bridge**: Operational complaints (340+ US cities) → Policy decisions → Coordinated action
- **Technical**: `src/seeclickfix_client.py` + `src/operational_agenda_matcher.py` (AI matching)
- **Case Study**: San Rafael Oct 6 Wildfire Fund (24 fire/tree complaints matched)
- **Architecture**: `docs/architecture/SEECLICKFIX_INTEGRATION_ARCHITECTURE.md`

## Production Status

**26 cities** | **~150 events** | **~65 actionable items** | **<$7/month cost**
- Event extraction: $5/month | Legislative context: $2/month
- Use `python scripts/city_status_dashboard.py` for current status
- ✅ Berkeley operational (86% parse rate)
- 🔄 Verifying remaining cities for production deployment

## Quick Start

```bash
# Setup environment
python3 -m venv civic-env
source civic-env/bin/activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your actual API keys:
# - OPENAI_API_KEY (required for chat routing)
# - OPENROUTER_API_KEY (optional - unified access to 100+ models)
# - CIVIC_WEB_KEY (required for API authentication)
# - GOOGLE_MAPS_API_KEY (optional for geocoding)

# Test extraction
python src/civic_digest.py schema "meeting-url"                        # Full (3min/city)
python src/civic_digest.py schema "meeting-url" --skip-agenda-parsing  # Fast (10sec/city)

# Automated refresh (all configured cities)
python src/automated_civic_refresh.py --future-only

# Start API server
python src/civic_api_integrated.py

# Testimony extraction (Session 111+)
python scripts/estimate_speakers_llm.py --video MpxrGRb16HQ  # Speaker count estimation
python scripts/testimony_quality_report.py --meeting san-rafael_2024-10-06_MpxrGRb16HQ  # Quality report
```

## Architecture

**Core Components**:
- `src/civic_digest.py` - Multi-platform extraction (Legistar, CivicClerk, Granicus, HTML)
- `src/seeclickfix_client.py` - **NEW (Session 90)**: SeeClickFix API v2 client for operational complaints (373 lines, 14 tests)
- `src/operational_agenda_matcher.py` - **NEW (Session 90)**: AI matching operational→policy (keyword + LLM semantic, 419 lines)
- `src/agenda_integration.py` - PDF parsing + LLM actionability assessment
- `src/legislative_enrichment.py` - Zero-cost keyword matching for state bills + federal programs
- `src/legislative_context_cache.py` - Lazy-loading cache with TTL for legislative data
- `src/personalization_service.py` - **Phase 1 COMPLETE (2025-10-29)**: Centralized user profiles, civic history tracking, behavioral inference (98% test coverage)
- `src/civic_api_integrated.py` - Schema-compliant REST API with legislative context hydration + personalization + operational issues endpoint
- `src/civic_chat_router.py` - **Chat routing with structured query planning (Session 77)** - Pydantic + Instructor for reliable OR/AND queries
- `src/civic_socketio_server.py` - WebSocket server for real-time coordination messaging (port 8002)
- `src/testimony_extraction_pipeline.py` - **NEW (Session 111)**: Production-ready testimony extraction with error handling and retry logic ($3/meeting)
- `src/testimony_quality_metrics.py` - **NEW (Session 111)**: Quality metrics tracking (speaker count accuracy, identification rate, costs)
- `frontend/civic-workspace/` - **NEW**: IDE-inspired workspace (Layer 6 Phase 2 complete)
- `frontend/mcp-civic-server/civic-conversational-OS.html` - Conversational UI (legacy)

**SeeClickFix Integration** (Sessions 89-116 - PHASE 5 ANALYSIS COMPLETE):
- **Status**: ✅ Phase 5 longitudinal analysis complete, ready for pilot
- **Positioning**: Bridge between operational 311 (SeeClickFix) and policy engagement (our platform)
- **Data Source**: 340+ US cities using SeeClickFix for pothole/graffiti/infrastructure complaints
- **San Rafael Analysis** (Phase 5 - 1,340 complaints, 2009-2025):
  - 90% from 2024-2025 (recent platform adoption)
  - 94% unresolved (massive accountability gap)
  - Key corridors: 4th St (40), 3rd St (30), Lincoln Ave (27), Mission Ave (22)
  - Peak season: May-November (2x winter volume)
  - Policy feedback: 3.4x camping complaints increase AFTER ordinances (3-6 month lag)
- **Value**: Match operational complaints → council agendas → legislative context → collective action
- **Issue Taxonomy**: Operational (read from SeeClickFix) vs. Policy (native to our system)
- **Components Built** (Session 90):
  - `src/seeclickfix_client.py` - Full API v2 client with pagination, filtering, normalization (373 lines, 14 tests)
  - `src/operational_agenda_matcher.py` - AI matching with keyword + LLM semantic (419 lines)
  - API endpoint: `GET /api/operational-issues/{jurisdiction}` with status/pagination
  - Three-tier validation: Tier 1-2 (operational) + Tier 3 (policy) balanced architecture
- **Phase 5 Analysis**: `data/pilot/PHASE5_LONGITUDINAL_ANALYSIS.md`
- **Next**: Manual pilot with 5-10 San Rafael residents (Track A)
- See `docs/architecture/SEECLICKFIX_INTEGRATION_ARCHITECTURE.md` for complete design

**Data Flow**:
- **Operational**: SeeClickFix API → seeclickfix_client.py → AI matching → Agenda items + Legislative context
- **Policy**: Platform API/HTML → civic_digest.py → schema adapter → agenda integration → **legislative enrichment** → JSON files
- **Unified**: API server (hydrates bill references + personalizes + matches operational→policy) → Frontend

**Retrospective Analysis & RAG Strategy** (Session 99+ - NEW):
- **Hybrid Approach**: Structured extraction + Vector search for scalability
- **Phase 1 (Session 100)**: Item-by-item extraction (no truncation) → SQLite with full metadata
- **Phase 2 (Session 101+)**: Generate embeddings → ChromaDB → Semantic search across 26 cities
- **Use Cases**:
  - Pattern discovery: "Which cities allocated funds for wildfire prevention?"
  - Historical precedent: "Has Berkeley funded this before?"
  - Coalition building: "Who testified on similar environmental issues?"
- **Architecture**: `docs/pilot/RETROSPECTIVE_ANALYSIS_PIPELINE.md`
- **Cost**: ChromaDB free/local, embeddings ~$0.10/1K decisions (one-time)

**Query Planning Architecture** (Session 77, Session 78):
- **Structured outputs** using Pydantic + Instructor for deterministic query parsing
- **OR/AND query support**: "housing OR transportation" → 2 separate search operations
- **Query Result Mode**: Distinct UI showing operation breakdown vs filtered view
- **99.9% reliability**: Auto-retry on validation failures (vs ~50% with parallel function calling)
- **60x cheaper**: Uses gpt-4o-mini ($0.60/1M) instead of Claude ($3/1M)
- **Provider-agnostic**: OpenAI/Anthropic/OpenRouter support + fallback to gpt-4o-mini
- **OpenRouter integration** (Session 78): Unified access to 100+ models with single API key
- **Type-safe**: Pydantic models (QueryPlan, Operation, SearchFilters) throughout codebase
- **Cost**: ~$0.000006 per OR query (10 tokens × $0.60/1M) or $0 with OpenRouter free tier
- See `docs/architecture/CHAT_ROUTING_ARCHITECTURE.md` for complete details

**LLM Provider Architecture** (Sessions 83-88 COMPLETE - 2025-11-10):
- **Status**: ✅ Full stack implementation complete with frontend model picker UI
- **Model-First Design**: Tasks auto-select optimal models (85% cost reduction vs uniform Claude usage)
- **7 Models Configured**: gpt-4o-mini, gpt-4o, claude-sonnet-4, claude-sonnet-3.5, gemini-2.0-flash, gemini-1.5-pro, deepseek-chat
- **OpenRouter Integration**: Unified API access to 100+ models with automatic fallback
- **Cost Optimization**: ~$0.000006/query for navigation, ~$0.002/comment draft (60x cheaper than original)
- **Type Safety**: 0 TypeScript errors across frontend/backend (Session 86)
- **Frontend UI** (Session 88): Developer mode model picker with "Auto" and manual override, localStorage persistence
- **Implementation**: `src/llm_provider.py` (159 lines), `frontend/civic-workspace/src/components/chat/ModelPicker.vue`
- **Provider Support**: OpenAI, Anthropic, Google AI, OpenRouter (with per-provider rate limiting)
- See `docs/core/LLM_PROVIDER_ARCHITECTURE.md` and `docs/architecture/MODEL_FIRST_ARCHITECTURE.md` for details

**MCP Integration & City Adoption Strategy** (Session 118-119):
- **Status**: 🆕 Strategy refined with city integration modes
- **Key Insight**: Foundation-funded model implies city partnerships, not scraping. Parser abstraction is low priority; focus on intelligence layer.
- **City Integration Modes**:
  - Mode 1: **Parse** (bootstrap) - Existing `*_client.py` files, no city involvement
  - Mode 2: **API Access** (privileged) - City provides API keys, better reliability
  - Mode 3: **Push** (adoption) - City pushes to `POST /api/ingest/{jurisdiction}` in civic-app-schema format
  - Mode 4: **MCP Federation** (future) - Cities run MCP servers, we aggregate
- **Why MCP**: Industry standard (Anthropic, Vercel), enables Mode 4 federation, AI portability
- **Our Moat**: Intelligence layer (enrichment, coordination) - applies to ALL integration modes
- **Investment Priority**: Intelligence > MCP Distribution > Ingestion API > StateManager >> Parser Abstraction
- **First Target**: StateManager as MCP server (`mcp_servers/civic_issues.py`)
- **Architecture**: See `docs/architecture/MCP_INTEGRATION_STRATEGY.md` (Section 9: City Integration Modes)

**LangGraph Coordination** (Session 118+ - NEW):
- **Status**: ✅ Prototype operational
- **Implementation**: `src/coordination_graph.py` (280 lines)
- **Workflow**: detect_decision → conditional → discover_residents → END
- **Scoring**: Decision types + complaint volume (threshold: 100)
- **Discovery**: Queries StateManager for affected residents by street/type
- **Checkpointing**: Memory-based for prototype, PostgreSQL for production
- **Architecture**: See `docs/architecture/COORDINATION_ORCHESTRATION_ARCHITECTURE.md`

**Personalization Layer** (Phase 1 COMPLETE 2025-10-29):
- **Status**: ✅ Database + Service Layer implemented (Phase 1 of 5)
- **User Profiles**: Demographics, civic interests, expertise stored centrally (reusable across all features)
- **Civic History**: Automatic action tracking (comments, meetings, issues) for behavioral inference
- **Inference Engine**: Learn user interests/expertise from behavior → personalized recommendations
- **Reusability**: Comment drafting, email drafting, meeting recommendations all use unified context
- **Implementation**: `src/personalization_service.py` (133 lines, 98% test coverage)
- **Next**: Phase 2 - API endpoints (Week 2), Phase 3 - Full inference (Week 3), Phase 4 - Feature integration (Week 4)
- See `docs/architecture/PERSONALIZATION_SERVICE_ARCHITECTURE.md` for complete architecture

**Schema**: All output follows `civic-app-schema.json` with complete metadata preservation

**Legislative Enrichment** (integrated 2025-10-07):
- **Automatic enrichment** during event extraction at `civic_digest.py:3279`
- **17.2% combined enrichment rate** across 3 jurisdictions (40% for Berkeley alone)
- **100% of enriched events** have both state bills AND federal programs
- **0.03ms per event** latency overhead (negligible)
- **Zero operational costs** - uses keyword matching against cached legislative data
- **State legislation**: 28 bills across 5 topics (housing, transportation, environment, budget, education)
- **Federal programs**: 9 programs across 5 topics (complete coverage)
- **Financial Context** (CDBG allocations - 2025-10-07):
  - 4 of 6 cities with event data configured: Berkeley ($2.67M), Oakland ($7.39M), San Rafael ($715K), Santa Rosa (~$1.35M)
  - $11.4M total CDBG allocation tracked
  - 2 cities pending: El Cerrito, Hayward (1 hour of research remaining)
  - Richmond override created (Urban County participant - no event data currently)
  - Complete research guide: `docs/architecture/FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md` Appendix A
- **Topic aliases**: zoning→housing, transit→transportation, climate→environment, etc.
- **Cache architecture**: Merges state + federal data via `legislative_context_cache.py`
- **API hydration**: Resolves bill/program IDs to full context at `civic_api_integrated.py:1749`

## Platform Capabilities

**Legistar API** (6 cities operational):
- ✅ Event + agenda extraction via API
- ✅ 84% parse rate (best performing platform)
- Pattern: `https://city.legistar.com/Calendar.aspx`

**CivicClerk API** (11 cities operational):
- ✅ Event + agenda extraction via API
- ✅ Subdomain-based routing with jurisdiction_id normalization
- ✅ Automatic config-based jurisdiction_id lookup (prevents duplicates)
- Pattern: `https://{subdomain}.portal.civicclerk.com`
- Code: `civic_digest.py:585-594` - regex subdomain extraction
- Code: `civic_digest.py:907-910` - jurisdiction_id normalization from config

**Granicus ViewPublisher** (2 cities operational):
- ✅ HTML table extraction + SSL redirect handling
- ✅ 30-day lookback for cities with sporadic publishing schedules
- Pattern: `https://city.granicus.com/ViewPublisher.php?view_id=N`
- Code: `granicus_client.py:43` - configurable temporal window (default: 30 days past, 90 days future)
- Code: `civic_digest.py:1008` - uses 30-day lookback

**HTML Parsing** (1 city operational):
- ✅ Custom per-city extraction (San Rafael)
- ⚠️ Not generalized - each city needs custom code

## Critical Technical Details

**CivicClerk Jurisdiction ID Normalization** (`civic_digest.py:907-910`):
```python
# Get proper jurisdiction_id from URL (not subdomain)
# This ensures we use the normalized jurisdiction_id from CITY_CONFIGS
from automated_civic_refresh import get_jurisdiction_by_url
jurisdiction_id = get_jurisdiction_by_url(source_url)
```
- Prevents duplicate extractions with variant subdomain names (e.g., `elcerritoca` vs `elcerrito`)
- Always uses the canonical `jurisdiction_id` from `CITY_CONFIGS`
- Subdomain extracted at line 585-594 is only used for API client initialization

**Granicus Temporal Window** (`granicus_client.py:43`, `civic_digest.py:1008`):
```python
# granicus_client.py - default temporal window
def get_meetings(self, days_future: int = 90, days_past: int = 30) -> List[Dict]:

# civic_digest.py - use 30-day lookback for cities that publish sporadically
meetings = client.get_meetings(days_future=90, days_past=30)
```
- 30-day lookback captures meetings from cities with irregular publishing schedules
- Prevents missing meetings when agendas are published late or sporadically
- Configurable per-city if needed

**Agenda Integration Toggle** (`civic_digest.py:2722`):
- `_enhance_with_participation_mechanisms(schema_dict, enable_agenda_parsing=True)`
- Set `enable_agenda_parsing=False` for fast event-only extraction
- CLI flag: `--skip-agenda-parsing`

**Project Type Taxonomy Consistency** (`civic_digest.py:3337-3369`, `agenda_integration.py:945-963`):
- **Unified taxonomy** across all parsers: housing, transportation, environment, budget, education, development, public_safety, community, elections, governance
- **Automatic re-classification**: PDF-extracted agenda items with non-standard project_types are re-classified by agenda integration LLM
- **Use permit classification**: Use permits, variances, conditional use permits → classified as "housing" (not "development") for proper legislative enrichment
- **Standard extraction updated** (`civic_digest.py:692`): Uses same taxonomy as agenda integration for consistency
- **Key distinction**: Land use/zoning decisions → "housing" (enrichable) vs. commercial business development → "development" (not enrichable)
- Line 3337-3369: Detects old taxonomy patterns (hyphens, spaces, underscores) and triggers re-classification
- Line 945: Housing taxonomy expanded to include "use permits, land use decisions, variance requests, conditional use permits, site plan approvals"

**Metadata Preservation**:
- Legistar: `_legistar_metadata` field preserved through entire pipeline
- CivicClerk: `_civicclerk_metadata` + `agenda_url` from API
- Granicus: `_granicus_metadata` + SSL certificate retry logic

## Adding New Cities

**Integration Mode determines approach** (see `docs/architecture/MCP_INTEGRATION_STRATEGY.md` Section 9):

**Mode 1: Parse (Bootstrap)** - For demonstrating value before partnership:
```python
# 1. Configure in automated_civic_refresh.py
CITY_CONFIGS = {
    "city_name": {
        "jurisdiction_id": "city-name",
        "agent_type": "civicclerk",  # or "legistar", "granicus", "html"
        "meeting_urls": ["https://cityname.portal.civicclerk.com"],
        "contact_email": "clerk@city.gov",
        "timezone": "America/Los_Angeles"
    }
}

# 2. Run extraction
python src/automated_civic_refresh.py --jurisdiction city_name --future-only

# 3. Verify output
ls -lh data/events/events_city-name*.json
```

**Mode 3: Push (Official Adoption)** - For partnered cities:
```bash
# City pushes directly to ingestion API (future)
POST /api/ingest/{jurisdiction_id}
# With civic-app-schema.json format
# Intelligence layer (enrichment, coordination) still applies
```

**Strategic Note**: Parser code is bootstrap infrastructure. Official city adoption (Mode 3) bypasses parsers entirely. Don't over-invest in parser abstraction; focus on intelligence layer (our moat).

## Development Commands

**Production**:
- `python src/automated_civic_refresh.py --future-only` - Refresh all configured cities
- `python src/civic_api_integrated.py` - Start API server
- `cat data/cost_monitoring.json` - Check costs

**Operational Visibility**:
- `python scripts/update_city_registry.py --incremental` - Update city status registry (incremental)
- `python scripts/update_city_registry.py` - Full registry rebuild (use after cleanup/major changes)
- `python scripts/city_status_dashboard.py` - View all cities summary
- `python scripts/city_status_dashboard.py <city>` - View single city detail
- `python scripts/city_status_dashboard.py --broken` - Show only broken cities

**Legislative Context** (NEW):
- `python src/legislative_discovery.py --topic housing --review` - Discover new housing legislation (dry-run)
- `python src/legislative_discovery.py --topic all --days 30` - Update all topics with last 30 days
- `scripts/update_legislative_context.sh` - Weekly cron job (automated discovery)

**Testimony Extraction** (Session 111+):
- `python scripts/estimate_speakers_llm.py --video MpxrGRb16HQ` - LLM speaker count estimation
- `python scripts/merge_youtube_assemblyai_speakers.py --youtube-analysis X --assemblyai-transcript Y --output Z` - Three-tier speaker name extraction
- `python scripts/testimony_quality_report.py --meeting san-rafael_2024-10-06_MpxrGRb16HQ` - Quality report for single meeting
- `python scripts/testimony_quality_report.py --jurisdiction san-rafael` - Aggregate report for jurisdiction
- See `docs/architecture/TESTIMONY_EXTRACTION_PIPELINE.md` for complete architecture

**Testing**:
- `python tests/test_phase2_automation.py` - Automation validation
- `python tests/test_all_fixes.py` - Comprehensive tests
- `python src/civic_digest.py test` - Basic newsletter test
- `python tests/test_legislative_enrichment.py` - Legislative context Phase 1.1 tests
- `python tests/test_legislative_automation.py` - Legislative automation Phase 1.3 tests
- `python -m pytest tests/test_personalization_service.py -v` - PersonalizationService Phase 1 tests (98% coverage)

**Discovery**:
- `python scripts/probe_civicclerk.py` - Find CivicClerk cities (11 discovered)
- `python scripts/validate_civicclerk_cities.py` - Validate discovered cities
- `python tests/test_legistar_discovery.py` - Validate Legistar clients

**SeeClickFix Integration** (NEW - Session 89):
- `python scripts/test_seeclickfix_api.py` - Test SeeClickFix API endpoints (spike validation)
- `python scripts/test_sanrafael_issues.py` - Fetch San Rafael-specific complaints
- `python scripts/sample_sanrafael_data.py` - Sample current operational issues

## Known Issues & Limitations

**Parse Rate Variance**:
- Legistar: 65% avg (agendas consistently published)
- CivicClerk: 0% avg (many events have `agendaId=0` - not yet published)
- Granicus: 0% avg (cities may not have future meetings published, or use alternative platforms like Escriba)
- CivicPlus: Varies by city (depends on schema.org markup quality)
- Why: Agenda availability depends on municipal publishing schedules
- **This is expected behavior** - CivicClerk parse rates improve closer to meeting dates

**Platform Detection** (RESOLVED 2025-10-05):
- Registry now checks `CITY_CONFIGS` first, falls back to event metadata
- All CivicPlus cities now correctly identified
- Remaining "Unknown": Marin County (403 errors from bot protection)

**Granicus Limitations**:
- Campbell: Uses Granicus for archives, but may use Escriba (`pub-campbell.escribemeetings.com`) for upcoming meetings
- Some Granicus cities don't publish future meetings - only historical archives available
- 30-day lookback captures recent meetings when future meetings unavailable

## Business Model

**Foundation-funded civic infrastructure**:
- **Target**: $50-100K annual foundation grants per region
- **Cost**: <$7/month operational (event extraction $5 + legislative context $2)
- **Success**: Civic participation increases + municipal efficiency gains
- **Not**: SaaS metrics or revenue optimization

**Value Proposition**: Multi-platform resilience (5 platforms), automated legislative context enrichment, scalable architecture, proven agenda extraction at regional scale.

## Frontend Workspace (NEW - 2025-10-13)

**Status**: ✅ **Sessions 1-88 Complete** - All core layers + LLM provider architecture with frontend UI operational

**Architecture**: Conversation-first workspace with intelligent multi-tab artifact system + unified event-based drafting (no tab proliferation) + collapsible sidebar with Pinia store state management

**Core Features Complete**:
- ✅ **Layers 1-5**: Design system, components, state management, tabs, legislative panel
- ✅ **Layer 6**: Issue system + community formation (event linking, following, coordination chat, response tracking)
- ✅ **Chat System**: Natural language navigation (Session 27), rich markdown, side-by-side layout, ThreadArtifact
- ✅ **Social Features**: Nested threading, discussion stats, avatars, discovery indicators
- ✅ **Comment Drafting** (Sessions 37-64):
  - Structured input (position, concern, context)
  - Legislative reference validation (99.99% accuracy, auto-corrects typos)
  - Multi-draft system with per-item memoization (67% cost savings)
  - Privacy tiers, archetype personalization, tag filtering
  - Drafts tab in EventArtifact (eliminates tab proliferation)
  - Chat research integration ("Use this in draft" button)
- ✅ **Context Management**: Mode-aware filtering (Navigation/Research/Coach/Orchestrator), visual indicators, registry backend
- ✅ **Sidebar Management**: Pinia store state management, reliable chat navigation
- ✅ **LLM Provider System** (Sessions 83-88): Provider abstraction with auto model selection, frontend UI with developer mode, TypeScript type safety

**Research Capabilities** (Session 50 implementation, Session 87 strategy):
- **Current Status**: ⚠️ Implemented but low discoverability
- **Implementation** (Session 50):
  - "Use this in draft" button on assistant messages (ChatPanel.vue:992, MessageBubble.vue:33-44)
  - Markdown stripping and content injection into DraftWorkspace
  - Smart placement before signature with visual indicators
  - Works when EventArtifact is active and message >50 chars
- **Known Friction Points** (Session 87 audit):
  - Hidden feature: No indication research is available
  - Multi-step flow: Must discover chat → ask question → click button
  - No research history: Previous research lost in chat scroll
  - Legislative context collapsed by default (EventArtifact.vue:54)
  - No proactive suggestions or template questions
- **Future Roadmap** (Session 87 strategy, pending feature branch):
  - **Citations**: Inline sources for every AI claim (Perplexity pattern)
  - **Progressive disclosure**: Quick answer → deep dive on demand
  - **Template questions**: Pre-built queries for common scenarios
  - **Shareability**: Export research to social media formats (TikTok/Instagram)
  - **Document upload**: PDF/image context (NotebookLM pattern)
  - **Fact-checking**: Verify news articles, politician claims
  - **Audio summaries**: Listen to research while driving (NotebookLM pattern)
  - **Collaborative research**: Share notebooks with coalition members
- **Design Principles** (Session 87 panel insights):
  - Citation-first architecture (verifiable sources)
  - Plain language + auto-explain jargon
  - Mobile-first for Gen Z engagement
  - Context persistence (remember previous research)
- See `docs/architecture/RESEARCH_CAPABILITIES_STRATEGY.md` for complete strategy (pending creation)

**Key Technical Details**:
- Cost: ~$0.002/draft, ~$0.30/month for 100 chat users
- Cache hit rate: 85%+ for multi-item drafts
- Migrations: 007-010 (drafts, memoization, tags, metrics)
- See `docs/core/next_session_prompt.md` for detailed status

**Development Commands**:
```bash
# Start backend REST API server (Terminal 1)
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate
export CIVIC_WEB_KEY=dev_key_local
python src/civic_api_integrated.py    # Runs on http://localhost:8001

# Start WebSocket server for real-time messaging (Terminal 2)
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate
python src/civic_socketio_server.py   # Runs on ws://localhost:8002

# Start frontend dev server (Terminal 3)
cd frontend/civic-workspace
npm run dev           # Runs on http://localhost:5173

# Type checking
npm run type-check    # Vue-tsc validation

# Production build
npm run build         # Vite production build

# Run tests
npm run test          # Vitest unit tests
```

**Backend Integration**:
- REST API: jurisdictions, events, issues, follows, legislative context, chat routing (POST /api/chat/route)
- WebSocket: Real-time coordination messaging (Socket.io, port 8002)
- OpenAI: Draft comments (gpt-4o-mini, 2000 tokens) + chat routing
- Auth: Bearer token via CIVIC_WEB_KEY

**Key Documentation**:
- `docs/core/next_session_prompt.md` - Current status + next tasks
- `docs/core/API_DOCUMENTATION.md` - Complete backend API specs
- `docs/architecture/COMMENT_DRAFTING_ARCHITECTURE.md` - 15-part drafting design
- `docs/features/LEGISLATIVE_REFERENCE_VALIDATION.md` - 99.99% accuracy safeguards
- `docs/core/CHAT_STRATEGY_ROADMAP.md` - 4-phase chat evolution
- See `docs/README.md` for complete documentation index

## Files

```
src/civic_digest.py                    # Multi-platform extraction (1356 lines)
src/civic_api_integrated.py            # REST API server with legislative enrichment + complaint/follow endpoints + chat routing + personalization
src/civic_chat_router.py               # Chat routing with OpenAI function calling (Session 26)
src/civic_socketio_server.py           # WebSocket server for real-time coordination messaging (port 8002)
src/personalization_service.py         # Unified user profiles, civic history, behavioral inference (Phase 1 COMPLETE - 133 lines, 98% coverage)
src/legislative_reference_validator.py # 99.99% factual accuracy for bill citations (Session 40 - auto-corrects typos)
src/issue_storage.py                    # Issue & community storage (IssueStorage, CommunityStorage)
src/legistar_client.py                 # Legistar API client (6 cities)
src/civicclerk_client.py               # CivicClerk API client (15 cities)
src/granicus_client.py                 # Granicus ViewPublisher client
src/seeclickfix_client.py              # SeeClickFix API v2 client (NEW - Session 89, 340+ cities potential)
src/legiscan_client.py                 # LegiScan API client (NEW - legislative discovery)
src/agenda_integration.py              # PDF parsing + LLM assessment
src/automated_civic_refresh.py         # Automated refresh script
src/legislative_context_cache.py       # Legislative + federal cache with TTL (merges state + federal)
src/legislative_enrichment.py          # Keyword-based enrichment (state bills + federal programs)
src/legislative_discovery.py           # Automated bill discovery with LLM filter (DEPRECATED)
src/testimony_extraction_pipeline.py   # Production-ready testimony extraction with error handling (Session 111)
src/testimony_quality_metrics.py       # Quality metrics tracking for testimony pipeline (Session 111)
scripts/estimate_speakers_llm.py       # LLM-based speaker count estimation (Session 108)
scripts/merge_youtube_assemblyai_speakers.py  # Three-tier speaker name extraction (Session 109, 111)
scripts/extract_wildfire_testimony.py  # Topic-specific testimony extraction (Session 110)
scripts/cross_reference_testimony_complaints.py  # Gap analysis - complaints vs testimony (Session 110)
scripts/testimony_quality_report.py    # CLI quality reports for testimony pipeline (Session 111)
scripts/update_city_registry.py        # City status registry generator
scripts/update_legislative_context.sh  # Weekly legislative updates cron job
scripts/city_status_dashboard.py       # Interactive city status CLI
scripts/automate_housing_context.py    # Perplexity-based context generation (housing)
scripts/automate_all_topics.py         # Multi-topic context generation
scripts/perplexity_federal_programs.py # Federal program query tool
frontend/mcp-civic-server/civic-conversational-OS.html  # Conversational UI (legacy)
frontend/civic-workspace/              # NEW: IDE-inspired workspace (Layer 6 Phase 2 complete)
├── src/
│   ├── design-system.css              # Solarized design system
│   ├── types/civic.ts                 # TypeScript interfaces (issues, follows, messages)
│   ├── services/
│   │   ├── api.ts                     # REST API service layer with Bearer token auth
│   │   └── socket.ts                  # Socket.io client for real-time messaging
│   ├── stores/                        # Pinia state management
│   │   ├── legislative.ts             # Legislative context store with TTL cache
│   │   └── issues.ts              # Complaint management store
│   ├── composables/
│   │   ├── useKeyboardShortcuts.ts    # Tab keyboard shortcuts
│   │   └── useCoordinationChat.ts     # Real-time chat state management
│   ├── components/
│   │   ├── sidebar/
│   │   │   ├── JurisdictionTree.vue        # Hierarchical navigation
│   │   │   ├── LegislativePanel.vue        # Legislative context browsing
│   │   │   └── MyIssuesPanel.vue           # User's issues sidebar
│   │   ├── workspace/
│   │   │   ├── TabBar.vue                  # Artifact tab management
│   │   │   ├── EventList.vue               # Event list with filtering
│   │   │   ├── EventArtifact.vue           # Event details with legislative context
│   │   │   ├── BillArtifact.vue            # State bill details
│   │   │   ├── ProgramArtifact.vue         # Federal program details
│   │   │   ├── IssueArtifact.vue       # Complaint details with coordination chat
│   │   │   ├── IssueForm.vue           # Fast complaint filing
│   │   │   ├── EventSelectionModal.vue     # Manual event linking modal
│   │   │   ├── FollowButton.vue            # Following system component
│   │   │   ├── CoordinationChat.vue        # In-app coordination messaging
│   │   │   ├── ResponseTimeline.vue        # Government response tracking
│   │   │   ├── CommentDraftArtifact.vue    # Comment drafting artifact (Sessions 37-48)
│   │   │   ├── DraftPicker.vue             # Multi-draft selector with tags/filter (Session 46-48)
│   │   │   └── DraftWorkspace.vue          # Inline draft editor for tabs (Session 49)
│   │   ├── chat/
│   │   │   ├── ChatPanel.vue               # Conversational AI interface
│   │   │   └── MessageBubble.vue           # Message display
│   │   ├── comment-drafting/
│   │   │   └── PersonalContextForm.vue     # User context input for drafts
│   └── App.vue                        # Workspace layout with tabs
data/events/*.json                     # Extracted event data
data/legislative_context/*.json        # State legislation by topic (5 topics)
data/federal_programs/*.json           # Federal programs by topic (3 topics)
data/jurisdiction_overrides/*.json     # City-specific allocations (3 cities)
data/city_status_registry.json         # Operational status tracking
data/cost_monitoring.json              # Cost tracking
data/civic_participation.db            # SQLite database (issues, follows, threads, messages)
migrations/003_add_phase2_features.sql # Complaint system tables
migrations/004_allow_null_match_score.sql # Manual event linking support
migrations/005_add_coordination_messaging.sql # Following + coordination threads + messages
migrations/006_personalization_service.sql # User profiles, civic history, inferred interests (Phase 1)
migrations/007_comment_drafts.sql # Comment drafting system (Session 45)
migrations/008_draft_memoization_cache.sql # Per-item draft caching (Session 47)
migrations/009_draft_tags.sql # Topic tags for draft filtering (Session 48)
migrations/010_cache_metrics.sql # Cache hit/miss analytics (Session 48)
migrations/011_testimony_storage.sql # Testimony extraction storage schema (Session 111)
civic-app-schema.json                  # Schema specification with legislative_context
docs/                                  # Documentation (see docs/README.md for complete index)
```

## Branch Strategy

**Current**: `feature/seeclickfix-integration` (Session 89 - SeeClickFix bridge)
**Previous**: `mcp-conversational-integration` (working main)
**Stable**: `v0.9-engagement-strategy` tag or `pre-reorganization-stable` branch

Recovery if needed:
```bash
git checkout v0.9-engagement-strategy
```

## Git Commit Guidelines

Never attribute credit to any entity in commit messages. Focus on technical changes only.

## Additional Documentation

**Core Architecture** (see `docs/README.md` for complete index):
- `docs/core/COMMUNITY_CIVIC_PMF_STRATEGY.md` - Complaint-to-civic engagement strategy
- `docs/core/CHAT_STRATEGY_ROADMAP.md` - 4-phase chat evolution (Navigation → Research → Coach → Orchestrator)
- `docs/core/FRONTEND_TECHNICAL_ARCHITECTURE.md` - IDE-inspired workspace vision
- `docs/core/next_session_prompt.md` - Current status + next tasks

**AI/LLM Systems**:
- `docs/architecture/MODEL_FIRST_ARCHITECTURE.md` - Model-centric routing (7 models, capability-based selection, 85% cost savings)
- `docs/core/LLM_PROVIDER_ARCHITECTURE.md` - Provider-agnostic architecture (swap OpenAI/Claude/Gemini, MCP-compatible)
- `docs/architecture/COMMENT_DRAFTING_ARCHITECTURE.md` - Structured comment drafting (15-part design)
- `docs/features/LEGISLATIVE_REFERENCE_VALIDATION.md` - 99.99% accuracy safeguards

**Personalization** (Phase 1 Complete 2025-10-29):
- `docs/architecture/PERSONALIZATION_SERVICE_ARCHITECTURE.md` - Unified user profiles, civic history, behavioral inference
- `docs/guides/PERSONALIZATION_IMPLEMENTATION_GUIDE.md` - Phase 1-5 implementation steps
- `docs/guides/PERSONALIZATION_AUDIT_REPORT.md` - Architecture audit (3 critical issues fixed)

**Platform Integration**:
- `docs/architecture/SEECLICKFIX_INTEGRATION_ARCHITECTURE.md` - **NEW (Session 89)**: SeeClickFix → Civic Power bridge architecture
- `docs/architecture/TESTIMONY_EXTRACTION_PIPELINE.md` - **NEW (Session 111)**: Production testimony extraction ($3/meeting, 34% identification rate)
- `docs/architecture/FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md` - Legislative enrichment architecture
- `docs/guides/LEGISLATIVE_CONTEXT_SETUP_GUIDE.md` - Setup guide (96-98% precision)
- `docs/platforms/LEGISTAR_AGENDA_INTEGRATION.md` - Legistar technical details
- `docs/features/RESILIENCE_STRATEGY.md` - Multi-platform resilience

**Pilot Validation** (Jan 2025):
- `docs/pilot/PILOT_ROADMAP.md` - **START HERE**: Timeline, phases, success criteria (Nov-Dec tech → Jan pilot)
- `docs/pilot/SESSION_96_DECISION_BRIEF.md` - Oct 6 Wildfire Fund case study analysis
- `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md` - Core hypothesis being tested
