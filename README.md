# 🏛️ Civic Engagement Platform

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
# - CIVIC_WEB_KEY=dev_key_local (for local development)
# - GOOGLE_MAPS_API_KEY (required for location filtering)

# Then activate the environment
source civic-env/bin/activate
```

**Note**: Frontend `.env` is only needed for production deployment. Local dev uses defaults + Vite proxy.

### 3. Start the Multi-Platform Interface
```bash
# Test multi-platform event extraction (23+ municipalities)
python src/civic_digest.py schema "https://www.ci.richmond.ca.us/Calendar.aspx"  # CivicPlus CMS
python src/civic_digest.py schema "https://berkeleyca.gov/community-recreation/events?field_event_category_tid=104"  # Berkeley
python src/legistar_client.py test oakland  # Legistar API

# Check operational status across all platforms
python src/municipal_registry.py

# Start hybrid API server (serves unified event data)
python src/civic_api_integrated.py

# Open conversational interface
open apps/civic-mcp/civic-conversational-OS.html
```

**Try asking**: "What housing meetings are happening in Richmond?" or "How can I comment on transportation planning in Berkeley?"

## 📖 Usage

### Newsletter Generation
```bash
# Send immediate digest for any meeting URL
python src/civic_digest.py scrape "meeting-url" recipient@email.com

# Test with positive control (known working URL)
python src/civic_digest.py test [recipient@email.com]

# Start weekly automation (Monday 9 AM)
python src/civic_digest.py weekly

# Generate schema-compliant data for API
python src/civic_digest.py schema "meeting-url"
```

### Conversational API
```bash
# Start the API server (default port 8001, configurable with CIVIC_API_PORT)
python src/civic_api_integrated.py

# Test conversation endpoint
curl -X POST http://localhost:8001/api/conversation \
  -H "Authorization: Bearer civic_web_key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What civic opportunities are available?",
    "city": "San Rafael",
    "state": "California"
  }'

# Access conversational interface
open apps/civic-mcp/civic-conversational-OS.html
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

**Production Pipeline:**
```
civic_digest.py → data/schema/*.json → civic_api_integrated.py → Frontend
```

**Core Components:**
- **Data Pipeline**: `civic_digest.py` (1,356 lines) - Universal AI-powered civic data extraction
- **API Server**: `civic_api_integrated.py` (1,247 lines) - Authenticated conversational endpoints  
- **Frontend**: `civic-conversational-OS.html` (4,154 lines) - Conversational interface with action buttons
- **Testing**: Comprehensive security and integration test suites (3 new files)

**Key Features:**
- Schema-driven development with `civic-app-schema.json` compliance
- OpenAI GPT-4 integration for natural language civic assistance
- Bearer token authentication with environment variable security
- XSS protection and input validation throughout
- RFC 5545 compliant calendar file generation

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
├── src/                                          # Python source code
│   ├── civic_digest.py                          # Newsletter system (1,356 lines)
│   ├── civic_api_integrated.py                  # API server with conversation endpoint (1,247 lines)
│   ├── civic_schema_adapter.py                  # Schema integration layer (629 lines)
│   ├── civic_input_validator.py                 # Security validation (556 lines)
│   ├── config.py                                # Configuration management
│   └── utils/
│       ├── session_manager.py                   # Session management
│       └── conversation_service.py              # Conversation service
├── frontend/
│   └── mcp-civic-server/
│       ├── civic-conversational-OS.html         # Conversational interface (4,154 lines)
│       └── simple_server.py                     # MCP server (1,295 lines)
├── tests/                                       # All test files
│   ├── test_conversation_api.py                 # Conversation API tests
│   ├── test_integration_e2e.py                  # End-to-end tests
│   └── test_data/                               # Test data
├── docs/                                        # Documentation
│   ├── INTEGRATION_GUIDE.md                     # Production deployment guide
│   ├── TECHNICAL_DEBT.md                        # Development roadmap & priorities
│   └── ENGAGEMENT_STRATEGY.md                   # Civic engagement strategy
├── civic-app-schema.json                        # Schema reference
├── requirements.txt                              # Dependencies
├── README.md                                    # This file
└── data/                                      # Generated digest files
    └── schema/                                  # Schema-compliant JSON data
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

This is a single-file MVP designed for simplicity. The entire system is in `civic_digest.py` - modify as needed for your city or use case.

## 📄 License

MIT License - Use for any civic good purpose.