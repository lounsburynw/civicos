# CIVIC DATA INGESTION STRATEGY

**Event-Centric Architecture Framework for AI-Optimized Civic Participation Platform**
*Hybrid Event-Centric + Agenda Expansion Implementation Guide*

**📚 See Also**: `docs/MUNICIPAL_PARSING_LESSONS.md` for overengineering traps and municipal agent strategy insights.

---

## Executive Summary (Updated 2025-10-05)

**Current Achievement**: 26 unique municipalities (16 operational, 1 degraded, 9 need investigation)
**Strategic Foundation**: Multi-platform resilience with 5 platform types (Legistar, CivicClerk, Granicus, HTML, Unknown)
**Technical Status**: 65 actionable items extracted, <$5/month cost
**Data Quality**: Production-ready with 65% parse rate on Legistar, 100% on HTML, 0% on CivicClerk/Granicus (expected - agenda publishing schedules)
**Recent Milestone** (2025-10-05):
- **CivicClerk deduplication**: Fixed jurisdiction_id normalization (26 unique cities, 0 duplicates)
- **Granicus temporal fix**: 30-day lookback for sporadic publishers (Campbell: 0→2 meetings)

## Production Status: Multi-Platform Infrastructure ✅

**Current Scale**: 26 unique cities (16 operational, 1 degraded, 9 need investigation), ~150 events, 65 actionable items

**Platform Distribution (2025-10-05)**:
- **6 Legistar API cities**: Hayward (11 items), Santa Rosa (15), Napa (14), Sonoma County (14), BART (6), Oakland (0*) - 65% avg parse rate ⭐
- **11 CivicClerk API cities**: El Cerrito, Los Altos, Los Altos Hills, Daly City, Milpitas, Pinole, Pittsburg, Antioch, Richmond, Pleasanton, Scotts Valley - 0% parse rate (expected - unpublished agendas)
- **2 Granicus ViewPublisher cities**: Dublin, Campbell - 0% parse rate (archive-only extraction, no future meetings)
- **1 HTML Parsing city**: San Rafael (5 items) - 100% parse rate
- **6 Unknown platform cities**: Berkeley, Concord, Pleasant Hill, San Leandro, Union City, Marin County - need investigation

*Oakland 0% from recent `--skip-agenda-parsing` test - previously operational with 56 items

**Operational Metrics**:
- **Cost Efficiency**: <$5/month (26 cities sustainable within budget)
- **Parse Rate**: 61% overall (47 meetings with agendas / 77 total events)
- **Best Platform**: Legistar (94% parse rate, 68 actionable items)

---

## Current Data Pipeline Architecture

### **Event-Centric Multi-Platform Pipeline** ✅
```
Municipal Data Sources → Agent-Based Extraction → Event Schema → API → Frontend
    ↓                       ↓                       ↓            ↓        ↓
CivicPlus CMS          civicplus_cms agent     Event JSON   civic_api  Conversational
Legistar API      →    legistar agent      →   Files    →   endpoints → Interface
HTML Sources           berkeley_cms agent      (structured)              + Actions
                       standard agent
```

### **Schema Foundation Status**
```json
{
  "Event_Core_Data": {
    "implemented": ["id", "title", "when", "location", "impact_summary", "jurisdiction", "meeting_type"],
    "status": "✅ High quality extraction across 23 municipalities"
  },
  "Participation_Mechanisms": {
    "implemented": ["email", "attend", "virtual"],
    "features": ["meeting_id parsing", "phone separation", "reference architecture"],
    "status": "✅ Production-ready with San Rafael"
  },
  "Agenda_Expansion": {
    "implemented": "San Rafael (HTML + PDF)",
    "architecture": "Reference-based via opportunity_id (no duplication)",
    "features": ["actionability detection", "project location", "is_actionable field"],
    "status": "✅ Working, ready to expand to other platforms"
  }
}
```

### **Recent Technical Achievements (2025-10-04)**

**CivicClerk Scalability Fix**:
- **Problem**: Hardcoded `jurisdiction_map` in `civicclerk_client.py:348-352` limited to 2 cities
- **Solution**: Direct subdomain extraction via regex from URL (`src/civic_digest.py:585-594`)
- **Impact**: Any CivicClerk city now works without code changes
- **Code Pattern**:
```python
# Extract subdomain directly from URL
subdomain_match = re.match(r'https?://([^.]+)\.(?:portal|api)\.civicclerk\.com', source_url)
if subdomain_match:
    civicclerk_subdomain = subdomain_match.group(1)
    client = CivicClerkClient(civicclerk_subdomain)  # Direct instantiation
```

**Next Priority**: Run batch extraction for 8 configured CivicClerk cities

### **Data Operations Commands**
```bash
# Multi-platform event extraction
python src/civic_digest.py schema "https://dalycityca.portal.civicclerk.com" # CivicClerk with agenda
python src/civic_digest.py schema "https://dublin.granicus.com/ViewPublisher.php?view_id=1" # Granicus
python src/civic_digest.py schema "https://www.cityofsanrafael.org/meetings" # HTML with agenda
python src/automated_civic_refresh.py --jurisdiction oakland --future-only # Legistar

# Batch CivicClerk extraction (8 cities configured)
for city in los_altos_hills milpitas pinole pleasanton scotts_valley pittsburg antioch richmond; do
    python src/automated_civic_refresh.py --jurisdiction $city --future-only
done

# Event file verification
ls -la data/events/events_*.json # Current extractions
python -c "import json,glob; [print(f'{f.split(\"/\")[-1]}: {len(json.load(open(f)).get(\"opportunities\",[]))} opps') for f in sorted(glob.glob('data/events/events_*.json'))[-10:]]"

# API and frontend testing
python src/civic_api_integrated.py # Serves event data
cd frontend/mcp-civic-server && python simple_server.py # Conversational interface
```

---

## Migration-Lite Strategy: Current to Target Architecture

### **Current State Analysis**

**✅ Excellent Foundation Data:**
- Accurate `title`, `when`, `location`, `impact_summary`, `jurisdiction`, `meeting_type`
- Consistent extraction across 23 municipalities
- Working multi-platform agent routing (CivicPlus, Legistar, HTML)

**🔧 Structure Enhancement Needed:**
- File organization: `data/schema/newsletter_*.json` → `data/events/events_jurisdiction_date.json`
- Participation mechanisms: Extract from existing `contact_info` and meeting data
- Schema alignment: Match documented Hybrid Event-Centric Architecture

### **Migration-Lite Implementation:**

**Phase 1: File Structure Reorganization**
```bash
# Migrate newsletter structure to event-centric organization
mkdir -p data/events data/events/archive

# Create semantic naming conversion
python -c "
import json, glob, os
files = glob.glob('data/schema/newsletter_*.json')
for f in files:
    data = json.load(open(f))
    jurisdiction = data.get('jurisdiction', {}).get('id', 'unknown')
    timestamp = f.split('_')[-1].replace('.json', '')
    date_part = timestamp[:8] if len(timestamp) >= 8 else timestamp
    new_name = f'data/events/events_{jurisdiction}_{date_part}.json'
    print(f'Migrate: {f} → {new_name}')
"
```

**Phase 2: Participation Mechanism Enhancement**
```python
# Extract participation from existing data structure
def enhance_event_participation(event_data):
    events = event_data.get('opportunities', [])

    for event in events:
        contact_info = event.get('contact_info', {})
        if contact_info.get('email'):
            # Create structured participation mechanisms
            event['participation_mechanisms'] = [
                {
                    "type": "email",
                    "contact": contact_info['email'],
                    "description": "Send written comment",
                    "deadline_guidance": "Check meeting agenda for deadline"
                },
                {
                    "type": "attend",
                    "location": event.get('location', ''),
                    "when": event.get('when', ''),
                    "description": "Attend meeting for public comment"
                }
            ]
    return event_data
```

## Participation Mechanisms Architecture

### Event-Level Mechanisms (Primary)
Participation mechanisms are primarily **event-level properties** - they describe how to participate in the meeting, not individual agenda items.

```json
{
  "event": {
    "participation_mechanisms": [
      {
        "type": "email",
        "contact": "planning@cityofsanrafael.org",
        "description": "Send written comment",
        "deadline": null
      },
      {
        "type": "attend",
        "location": "City Hall, Third Floor",
        "when": "2025-10-01T10:00:00-07:00",
        "description": "Attend meeting for public comment"
      },
      {
        "type": "virtual",
        "platform": "zoom",
        "url": "https://tinyurl.com/2025-ZA-Meeting",
        "meeting_id": "894 2390 5067",
        "phone": "(669) 444-9171",
        "description": "Join meeting virtually"
      }
    ]
  }
}
```

### Agenda Item Inheritance
Agenda items **inherit** event-level participation mechanisms unless they have item-specific overrides.

**Implementation** (`civic_digest.py:2303-2313`):
```python
# Inherit event-level virtual mechanism if available
event_virtual = None
if '_participation_mechanisms' in event:
    event_virtual = next((m for m in event['_participation_mechanisms']
                        if m['type'] == 'virtual'), None)
elif 'participation_mechanisms' in event:
    event_virtual = next((m for m in event['participation_mechanisms']
                        if m['type'] == 'virtual'), None)

if event_virtual:
    actionable_item['participation_mechanisms'].append(event_virtual.copy())
```

**Exception**: If agenda item has unique deadline or contact, add as override.

### Virtual Mechanism Structure

**Key Distinction** - URL vs Meeting ID (`civic_schema_adapter.py:1137-1140`):
```python
# Separate URL from meeting ID - livestream is URL, webinar is meeting ID
virtual_url = meeting_data.get('livestream')  # Only use livestream for URL
webinar_id = meeting_data.get('webinar') if not meeting_data.get('livestream') else None
virtual_phone = meeting_data.get('phone')
```

**Platform Detection** (`civic_schema_adapter.py:1187-1218`):
- `livestream`: Web URL for live streaming
- `webinar`: Zoom/Webex meeting ID (NOT a URL)
- `phone`: Dial-in number

**Output Structure**:
```json
{
  "type": "virtual",
  "platform": "zoom|livestream|webex|microsoft_teams|phone",
  "url": "https://... (if livestream/web URL)",
  "meeting_id": "894 2390 5067 (if Zoom/webinar ID)",
  "phone": "(669) 444-9171",
  "description": "Join meeting virtually",
  "when": "ISO datetime",
  "duration_minutes": 3
}
```

**Critical Fix**: Never treat meeting ID as URL. Meeting IDs are separate field for Zoom/Webex platforms.

### **API Integration Update**
```python
# Update civic_api_integrated.py to read from new event structure
def load_event_data():
    """Load events from new data/events/ structure"""
    import glob, json

    event_files = glob.glob('data/events/events_*.json')
    all_events = []

    for file_path in event_files:
        with open(file_path) as f:
            data = json.load(f)
            events = data.get('opportunities', [])
            # Enhance with participation mechanisms if not present
            for event in events:
                if not event.get('participation_mechanisms') and event.get('contact_info', {}).get('email'):
                    event = enhance_event_participation({'opportunities': [event]})['opportunities'][0]
            all_events.extend(events)

    return all_events
```

---

## Data Architecture Strategy: Event-Centric + Optional Agenda Expansion

### **AI-Optimized Data Schema for Civic Orchestration**

**Strategic Decision**: Adopt event-centric architecture with optional agenda expansion to optimize for LLM orchestration while maintaining municipal data source compatibility.

**Core Philosophy**: "Quality data as utility anchor" - structured participation mechanisms enable reliable AI guidance while preserving modularity for future schema evolution.

### **Agenda Integration Strategy: Conservative Expansion**

**Architecture Principle**: Event remains atomic unit, agenda items are optional enhancements that never break core functionality.

**Implementation Approach**:
- **Conservative Actionability**: Only include agenda items with clear public participation opportunities
- **Lazy Parsing**: Parse agendas on-demand to isolate complexity from event generation
- **Direct Population**: Agenda items get complete participation mechanisms (event defaults + explicit agenda overrides)
- **Schema Extension**: Additive-only changes preserve existing API compatibility

#### **Enhanced Event-Centric Architecture with Agenda Expansion**

**Foundation Layer**: Event-level consistency with optional agenda expansion
```json
{
  "id": "berkeley-city-council-2025-09-30",
  "title": "City Council Meeting",
  "when": "2025-09-30T16:00:00-07:00",
  "location": "City Hall, Berkeley CA",
  "participation_mechanisms": [
    {
      "type": "email",
      "contact": "council@berkeley.gov",
      "description": "Send written comment",
      "deadline": null,
      "duration_minutes": null
    },
    {
      "type": "attend",
      "location": "City Hall, Berkeley CA & Virtual",
      "when": "2025-09-30T16:00:00-07:00",
      "description": "Attend meeting for public comment",
      "duration_minutes": null,
      "virtual_option": "available"
    }
  ],
  "related_events": [],
  "related_projects": [],

  // Optional agenda expansion - only when available & actionable
  "agenda_expansion": {
    "available": true,
    "source_url": "https://berkeleyca.gov/agenda-packet.pdf",
    "format_hint": "pdf",
    "parsed": false,  // Lazy parsing on-demand
    "last_attempted": null
  }
}
```

**Agenda Expansion Layer**: On-demand parsing with direct population and graph-ready relationships
```json
// After lazy parsing: agenda_expansion.parsed = true
{
  "agenda_expansion": {
    "available": true,
    "parsed": true,
    "parsed_at": "2025-09-28T10:00:00Z",
    "actionable_items": [
      {
        "item_ref": "7.2",
        "title": "145-unit affordable housing project at Main & Oak",
        "actionable": true,
        "actionable_because": "Public hearing with comment period stated in agenda",
        "participation_mechanisms": [
          {
            "type": "email",
            "contact": "council@berkeley.gov",
            "description": "Send written comment",
            "deadline": "2025-09-30T16:00:00"  // Only if explicitly found in agenda
          },
          {
            "type": "attend",
            "location": "City Hall & Virtual",
            "when": "2025-09-30T16:00:00-07:00"
          }
        ],

        // Graph relationship arrays - start empty, populate when relationships detected
        "related_agenda_items": [],     // Cross-meeting project tracking
        "follows_from": null,           // Amendment/follow-up relationships
        "addresses_issues": [],         // Links to complaint/issue tracking
        "policy_chain": []             // Policy implementation progression
      }
    ]
  }
}
```

#### **AI Orchestration Optimization**

**Structured Participation Mechanisms** = **Actionable AI Responses**
- Clear deadlines enable "Submit by 5pm Tuesday" guidance
- Participation types enable "Attend, email, or call" recommendations
- Duration limits enable "Prepare 3-minute comment" instructions
- Contact information enables direct action generation

**Layered Detail Disclosure**:
- **Layer 1**: Event + participation (sufficient for 80% of users)
- **Layer 2**: Agenda summary (power user preview)
- **Layer 3**: Full agenda expansion (activist/researcher detail)

#### **Municipal Data Source Compatibility**

**Event-Driven Sources (80%)**:
- CivicPlus Calendars: Natural Schema.org Event extraction
- Legistar Calendar: Event-centric API endpoints
- Berkeley Events: Calendar with PDF agenda links

**Implementation**: Current event-level parsers maintain consistency while preserving sophisticated agenda parsing (Berkeley) as optional expansion.

**Agenda Integration**: Berkeley's agenda-specific parser cached in `berkeley_agenda_parser_legacy.py` for future agenda expansion system.

#### **Schema Evolution Strategy**

**Graph-Compatible Design**: Event-centric foundation with expansion hooks
```json
{
  "related_events": [],     // Add relationships later without breaking changes
  "related_projects": [],   // Enable cross-event tracking when needed
  "ai_confidence": 0.8,     // Add uncertainty handling incrementally
  "community_feedback": []  // Enable validation workflows progressively
}
```

**Benefits**:
- ✅ **Non-Breaking Evolution**: Add complexity without migrating existing data
- ✅ **Municipal Diversity**: Standardized participation across different CMS platforms
- ✅ **AI-Native**: Clean structured data for reliable LLM orchestration
- ✅ **User-Driven**: Progressive detail disclosure based on engagement level

#### **Critical Design Decisions**

**Event Boundaries**: Accept that most civic engagement naturally clusters around meeting events, with agenda items as optional detail expansion rather than primary organizing principle.

**Participation-First**: Prioritize structured participation mechanisms over raw agenda content to enable reliable AI action generation.

**Modular Expansion**: Preserve sophisticated parsing work (Berkeley agendas) while ensuring platform-wide consistency through event-level standardization.

#### **Edge Case Management**

**Multi-Event Projects**: Use `related_events` array to link housing projects across multiple meetings while maintaining event-centric primary structure.

**Cross-Jurisdictional Issues**: Handle through standardized participation mechanisms per jurisdiction rather than attempting to merge different municipal processes.

**Temporal Dependencies**: Track through event relationships while keeping individual events as atomic units for user interaction.

### **Agenda Integration Implementation Strategy**

#### **Phase 1: Agenda Discovery & Caching**
```python
# Enhanced event generation with optional agenda discovery
def enhance_with_agenda_discovery(event):
    """Add agenda_expansion framework during event generation"""
    source_url = event.get('source_url', '')

    # Conservative agenda detection
    agenda_url = discover_agenda_url(source_url)
    if agenda_url and looks_potentially_actionable(agenda_url):
        event['agenda_expansion'] = {
            'available': True,
            'source_url': agenda_url,
            'format_hint': detect_format(agenda_url),  # pdf, html, api
            'parsed': False,
            'last_attempted': None
        }
    return event
```

#### **Phase 2: Lazy Agenda Parsing Architecture**
```python
# On-demand agenda parsing with caching
@app.route('/api/events/<event_id>/agenda')
def get_event_agenda(event_id):
    """Parse agenda on-demand, cache results in event file"""
    event = load_event(event_id)
    expansion = event.get('agenda_expansion', {})

    if expansion.get('available') and not expansion.get('parsed'):
        try:
            # Multi-format parsing strategy
            items = parse_agenda_with_fallback(expansion['source_url'])
            actionable_items = filter_actionable_items(items)

            # Cache results in existing event file
            expansion.update({
                'parsed': True,
                'parsed_at': datetime.now().isoformat(),
                'actionable_items': actionable_items
            })
            save_event(event)

        except Exception as e:
            expansion.update({
                'parse_error': str(e),
                'last_attempted': datetime.now().isoformat()
            })

    return expansion.get('actionable_items', [])
```

#### **Phase 3: LLM-Based Conservative Actionability Filter**
```python
def llm_filter_actionable_items(agenda_content):
    """LLM-based conservative filter - only include items with clear participation opportunities"""

    prompt = f"""
    Extract ONLY actionable agenda items from this civic meeting agenda:

    {agenda_content[:3000]}

    CONSERVATIVE FILTER - only include items where residents can meaningfully participate:
    ✅ Include: Public hearings, resolutions, ordinances, development projects, zoning changes
    ❌ Exclude: Staff reports, consent calendar, informational items, closed sessions

    Return JSON array:
    [
        {{
            "item_ref": "7.2",
            "title": "145-unit housing project at Main & Oak",
            "actionable_because": "Public hearing with comment period",
            "addresses_affected": ["145 Main St", "Oak Street area"],
            "issue_categories": ["housing", "development"],
            "participation_mechanisms": [
                {{
                    "type": "email",
                    "contact": "council@berkeley.gov",
                    "description": "Send written comment",
                    "deadline": "2025-09-30T16:00:00"  // Only if explicitly found in agenda
                }}
            ],

            // Graph relationship arrays - start empty, populate when detected
            "related_agenda_items": [],
            "follows_from": null,
            "addresses_issues": [],
            "policy_chain": []
        }}
    ]
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"LLM agenda filtering failed: {e}")
        return []
```

#### **LLM-Based Agenda Discovery**
```python
def llm_discover_agenda_info(source_url, page_content):
    """Use LLM to discover agenda URLs and assess actionability"""

    prompt = f"""
    Analyze this civic meeting page to find agenda information:

    URL: {source_url}
    Content: {page_content[:2000]}...

    Tasks:
    1. Find any agenda PDF links, agenda packet links, or agenda document URLs
    2. Determine if this meeting likely has actionable items for public participation
    3. Be conservative - only mark actionable if clear public participation opportunities

    Return JSON:
    {{
        "agenda_url": "full_url_to_agenda_or_null",
        "format_hint": "pdf|html|unknown",
        "actionable_likely": true|false,
        "reasoning": "brief explanation"
    }}
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        return {
            "agenda_url": None,
            "actionable_likely": False,
            "reasoning": f"Error: {e}"
        }
```

#### **Implementation Status**

**✅ Completed**:
- Graph-ready event enhancement with virtual detection and participation framework
- Event-centric architecture operational across 23+ municipalities
- Optional agenda expansion schema designed with inheritance model
- Conservative actionability principles established

**🔧 Next Phase - Agenda Integration**:
- Implement LLM-based agenda URL discovery during event generation
- Add lazy parsing API endpoints with multi-format support
- Deploy conservative LLM-based actionability filtering
- Include graph-ready relationship arrays in agenda item schema
- Test agenda expansion across diverse municipal formats

**🔮 Future Phase - Graph Relationships**:
- Implement cross-meeting project tracking using relationship arrays
- Add policy chain detection for legislative progression tracking
- Connect agenda items to complaint/issue resolution workflows
- Enable "project progression" narratives for deeper civic engagement

**🎯 Strategic Validation**: This agenda integration strategy transforms events from "meeting announcements" to "actionable civic intelligence" while preserving the robust event-centric foundation and municipal compatibility achieved.

---

## Foundation Budget Optimization Strategy

### **Cost-Conscious Architecture**
**Target**: <$50/month operational costs supporting 23+ municipalities

**Current Metrics**:
- **Event Extraction**: $20.12/month across all platforms
- **Platform Efficiency**: CivicPlus most efficient ($0.048/opportunity)
- **Foundation Compliance**: 60% under pilot budget

**Optimization Techniques**:
1. **Agent-Based Routing**: Intelligent selection of most efficient extraction method per municipality
2. **Event-Level Consistency**: Standardized output reduces processing complexity
3. **Multi-Platform Resilience**: 67% vendor independence prevents lock-in costs
4. **Progressive Enhancement**: Add participation mechanisms without breaking existing pipeline

**Success Definition**: Foundation-funded civic infrastructure that demonstrably increases community participation through reliable, cost-effective event data extraction across diverse municipal platforms.