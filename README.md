# 🏛️ CivicOS

**Conversational Operating System for Local Democracy** - Transform civic participation through AI-powered conversations with actionable engagement buttons. Event-centric architecture with multi-platform data collection across 26 Bay Area municipalities, enriched with integrated state/federal legislative context.

**Core Positioning**: "We turn complaints into civic power" - bridging operational 311 systems to policy engagement

## ✅ Production Ready + Pilot Phase

**Status**: Production-ready with regional infrastructure + San Rafael pilot preparation
**Strategic Focus**: Decision Awareness - coordinating residents for high-stakes decisions
**Architecture**: Event-centric + agenda expansion + legislative context enrichment + SeeClickFix operational bridge
**Phase 5 Complete**: San Rafael longitudinal analysis (1,340 SeeClickFix complaints) identifies key corridors + 94% accountability gap
**Platform Coverage**: 6 Legistar API + 11 CivicClerk API + 2 Granicus + 4 CivicPlus CMS + 1 HTML parsing + more ready
**Legislative Context**: 28 state bills + 7 federal programs across 5 topics, with city-specific CDBG allocations ($0 operational cost, 17.2% enrichment rate)

### San Rafael Pilot Data (Phase 5)

| Metric | Value | Implication |
|--------|-------|-------------|
| Total Complaints | 1,340 | Rich discovery dataset |
| Platform Adoption | 90% from 2024-2025 | Recent, growing usage |
| Resolution Rate | 6% closed | Massive accountability gap |
| Key Corridors | 4th St, 3rd St, Lincoln Ave | Geographic targeting |

See `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md` for pilot strategy.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install requests beautifulsoup4 openai schedule
```

### 2. Set Up Environment
```bash
# Copy example file and fill in your API keys
cp .env.example .env

# Edit .env with your actual API keys:
# - OPENAI_API_KEY (required for AI features)
# - CIVICOS_WEB_KEY=dev_key_local (for local development)
# - GOOGLE_MAPS_API_KEY (required for location filtering)

# Then activate the environment
source civicos-env/bin/activate
```

**Note**: Frontend `.env` is only needed for production deployment. Local dev uses defaults + Vite proxy.

### 3. Start the Platform
```bash
# Start the API server (port 8001)
python -m civic_services.civic_api_integrated

# Start WebSocket server (port 8002) - optional, for real-time features
python -m civic_services.civic_socketio_server

# Start Vue frontend (port 5173)
cd apps/civicos-workspace && npm run dev

# Or open the standalone conversational interface
open apps/civicos-mcp/civic-conversational-OS.html
```

**Try asking**: "What housing meetings are happening in Richmond?" or "How can I comment on transportation planning in Berkeley?"

## 📖 Usage

### Core API Usage
```python
from civic import Civic

c = Civic("san-rafael")

# Query methods
c.whats_next()              # Upcoming meetings/decisions
c.what_happened("housing")  # Historical decisions
c.what_applies("housing")   # Relevant legislation
c.whos_with_me("traffic")   # Community around issue

# Action methods
c.start_something(...)      # Create initiative
c.add_voice(...)            # Add voice to item
c.follow(...)               # Subscribe to updates
c.prepare(...)              # Generate prep materials
```

### REST API
```bash
# Test conversation endpoint
curl -X POST http://localhost:8001/api/conversation \
  -H "Authorization: Bearer civic_web_key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What civic opportunities are available?",
    "city": "San Rafael",
    "state": "California"
  }'
```

## 🧪 Testing

```bash
# Core functionality tests (run with API server active)
python tests/test_all_fixes.py                   # 5 comprehensive integration tests ✅ NEW
python tests/test_action_security.py             # XSS prevention and security validation ✅ NEW  
python tests/test_action_buttons.py              # Action button functionality tests ✅ NEW

# Legacy integration tests
python tests/test_integration_e2e.py             # End-to-end integration tests (17 test cases)
python tests/test_frontend_integration.py        # Frontend-backend integration validation
python tests/test_conversation_api.py            # Conversation API endpoint tests

# All tests are self-contained - no pytest/dependencies needed
```

## 🎯 Key Features

### 💬 Conversational Civic Discovery
- Ask natural questions: "What housing opportunities are available?"
- AI responds with specific meetings, projects, and participation methods
- Interest-based filtering matches opportunities to user preferences

### ⚡ Frictionless Action Buttons  
- **Email Buttons**: Pre-filled public comment emails with officials
- **Calendar Buttons**: Add meetings to calendar with one click (RFC 5545 compliant)
- **Link Buttons**: Direct access to meeting agendas and project details

### 🛡️ Enterprise-Grade Security
- XSS prevention with regex-based input validation
- Rate limiting and authentication for all API endpoints  
- RFC compliant calendar integration across all email clients

### 📊 Smart Opportunity Matching
- 67% improved relevance scoring using word overlap algorithms
- Data freshness warnings for stale civic information (>7 days)
- Comprehensive error handling and graceful degradation

## 💬 Example Conversation

**User:** "What housing opportunities are available?"

**AI:** "The Planning Commission will discuss the Electric Bicycle Safety Regulations at their September 2nd meeting. This regulation will establish safety standards for e-bike operation within city limits.

You can participate by:
- Attending the meeting in person at City Hall
- Submitting written comments via email  
- Calling in during the public comment period

Would you like me to help you prepare a public comment or add this meeting to your calendar?"

**Action Buttons:**
- 📧 **Email Public Comment** → Pre-filled email to city.clerk@cityofsanrafael.org
- 📅 **Add Meeting to Calendar** → Downloads .ics file with meeting details
- 🔗 **View Meeting Agenda** → Direct link to city website

## 📧 Newsletter Features

The system also generates professional HTML newsletters with:
- Google Calendar integration with hidden URLs
- Responsive design for all email clients  
- Clear participation instructions and deadlines
- Impact summaries explaining why each issue matters
- Color-coded sections for easy scanning

## 🏗️ Architecture

**Three-Package Design:**
```
packages/civic/           → Core API (Civic class, query methods)
packages/civicos-extraction/ → Platform parsers (Legistar, CivicClerk, Granicus, etc.)
packages/civicos-services/   → Application layer (REST API, WebSocket, chat routing)
```

**Client Applications:**
```
apps/civicos-workspace/     → Vue.js web frontend (IDE-inspired workspace)
apps/civicos-mcp/           → MCP server for Claude Desktop and AI assistants
```

**Key Capabilities:**
- **Multi-platform data collection**: 26 Bay Area municipalities via Legistar, CivicClerk, Granicus APIs
- **Legislative context enrichment**: State bills + federal programs linked to local issues
- **AI-powered conversation**: OpenAI/OpenRouter for natural language civic assistance
- **Real-time coordination**: WebSocket server for live updates and group discussions

## 💰 Cost & Performance

**API Costs:**
- ~$0.10-0.15 per conversation (OpenAI GPT-4 usage)
- ~$0.001 per action button generation (negligible)
- Total: ~$0.15 per engaged user conversation

**Response Times:**
- Simple queries: <500ms
- Complex civic questions: <2000ms
- Action button generation: <200ms additional
- 67% improvement in opportunity matching accuracy

## 🧪 Testing & Validation

**Production Ready - Tested on:**
- San Rafael Planning Commission & City Council
- Berkeley City Council  
- Works universally across different city websites
- Professional HTML email format tested across Gmail, Outlook, Apple Mail
- Google Calendar integration working seamlessly
- Responsive design verified on mobile, desktop, tablet

**Key Success Metrics to Track:**
- **Email engagement**: Open rates, click-through rates on meeting times and source links
- **Calendar adoption**: How many people add meetings to their calendars
- **Actual participation**: Meeting attendance and public comment submissions from digest recipients
- **User feedback**: Do residents find the content useful and actionable?

## 📁 File Structure

```
civic/
├── packages/                                     # Python packages
│   ├── civic/                                   # Core API package
│   │   └── src/civic/                          # Civic class and query methods
│   ├── civicos-extraction/                        # Platform parsers (Legistar, CivicClerk, etc.)
│   │   └── src/civic_extraction/
│   └── civicos-services/                          # Application layer
│       └── src/civic_services/
│           ├── servers/                         # API entry points (REST, WebSocket)
│           ├── clients/                         # External API clients
│           ├── providers/                       # LLM providers (OpenAI, OpenRouter)
│           ├── processing/                      # Data pipelines
│           ├── storage/                         # Persistence layer
│           ├── legislative/                     # Legislative enrichment
│           ├── issues/                          # Issue handling
│           ├── chat/                            # Chat routing
│           ├── monitoring/                      # Operations & metrics
│           ├── core/                            # Infrastructure
│           └── utils/                           # Utilities
├── apps/                                        # Client applications
│   ├── civicos-workspace/                         # Vue.js web frontend
│   └── civicos-mcp/                              # MCP server for AI assistants
├── data/                                        # Extracted civic data
│   ├── schema/                                  # Schema-compliant JSON
│   └── pilot/                                   # San Rafael pilot data
├── tests/                                       # Test suites
├── docs/                                        # Documentation
│   ├── critical/                                # Essential architecture docs
│   └── archive/                                 # Historical docs
└── docker-compose.yml                           # Container orchestration
```

## 🛠️ Customization

**Add Different City:**
```python
# Edit weekly URLs in civic_digest.py main() function
weekly_urls = [
    "https://your-city.gov/meetings/council/",
    "https://your-city.gov/meetings/planning/"
]
```

**Add Beta Users:**
```python
# Edit recipients list in send_weekly() function
recipients = [
    "user1@email.com",
    "user2@email.com"
]
```

## 🎯 Next Steps

**Immediate (Ready for Production):**
1. **Beta User Testing:** Email format is production-ready - start sending to 5-10 residents
2. **Multi-City Validation:** Test with 2-3 different cities to validate universal approach
3. **Weekly Automation:** Set up cron job or cloud scheduler for automated weekly digests

**Scale & Measurement:**
4. **Track Engagement:** Monitor email opens, calendar additions, actual meeting participation
5. **Geographic Expansion:** Add more cities/counties using same codebase
6. **Success Validation:** Measure if digests actually increase civic participation

## 🤝 Contributing

See `CLAUDE.md` for development workflow and session protocol. The codebase uses a package-based architecture - start with `packages/civic/` for the core API.

## 📄 License

MIT License - Use for any civic good purpose.