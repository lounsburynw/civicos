# Action Buttons Architecture

## Overview

The Action Buttons system implements "frictionless civic engagement" by adding native action capabilities (email, calendar, links) directly to AI conversation responses. This eliminates the conversion funnel from "I care" to "I acted" by reducing friction points.

## Architecture Components

### 1. Backend Action Generation (`src/civic_api_integrated.py`)

#### Core Algorithm: Opportunity Matching
```python
def calculate_relevance_score(self, opp_title: str, ai_response: str) -> float:
    """Calculate word overlap percentage between opportunity and response"""
    title_words = set(word.lower() for word in opp_title.split() if len(word) > 2)
    response_words = set(word.lower() for word in ai_response.split() if len(word) > 2)
    
    if not title_words:
        return 0.0
    
    overlap = title_words.intersection(response_words)
    return len(overlap) / len(title_words)
```

**Key Features:**
- Word overlap scoring with 30% relevance threshold
- Filters opportunities by user interests (housing, transportation, etc.)
- Returns top 3 most relevant opportunities as action buttons
- Data freshness warnings for stale civic information (>7 days)

#### Configuration Constants
```python
# Action Button Configuration
MAX_ACTION_BUTTONS = 3
RELEVANCE_THRESHOLD = 0.3
DATA_STALENESS_DAYS = 7
ACTION_LABEL_MAX_LENGTH = 30
DEFAULT_MEETING_DURATION_HOURS = 2
```

### 2. Frontend Action Rendering (`frontend/mcp-civic-server/civic-conversational-OS.html`)

#### Action Button Types

**Email Actions** (`mailto:` links)
- Pre-filled subject lines for public comment
- Direct integration with default email client
- Example: "Email Planning Commission about Housing Project #2024-15"

**Calendar Actions** (`.ics` file generation)
- RFC 5545 compliant iCalendar format
- Automatic timezone handling (America/Los_Angeles)
- Meeting details with location and agenda links

**Link Actions** (External resources)
- Meeting agendas, project documents
- City websites and application forms
- Direct navigation to relevant civic resources

#### ICS Calendar Generation
```javascript
function generateICS(event) {
    const escapeICS = (str) => {
        if (!str) return '';
        return str
            .replace(/\\/g, '\\\\')
            .replace(/;/g, '\\;')
            .replace(/,/g, '\\,')
            .replace(/\n/g, '\\n')
            .replace(/\r/g, '\\n');
    };
    
    // RFC 5545 compliant calendar file generation
    const ics = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Civic Engagement Platform//EN',
        'BEGIN:VEVENT',
        `UID:${event.id}@civic-engagement.local`,
        `DTSTART:${formatICSDateTime(event.start)}`,
        `DTEND:${formatICSDateTime(event.end)}`,
        `SUMMARY:${escapeICS(event.title)}`,
        `DESCRIPTION:${escapeICS(event.description)}`,
        `LOCATION:${escapeICS(event.location)}`,
        'END:VEVENT',
        'END:VCALENDAR'
    ].join('\r\n');
    
    return ics;
}
```

### 3. Security Implementation

#### XSS Prevention
```python
def validate_action_input(self, text: str) -> str:
    """Validate and sanitize input for action buttons"""
    if not text or not isinstance(text, str):
        return ""
    
    # Remove potential XSS patterns
    xss_patterns = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>.*?</iframe>',
        r'<object[^>]*>.*?</object>'
    ]
    
    for pattern in xss_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    return text.strip()[:self.ACTION_LABEL_MAX_LENGTH]
```

#### Input Validation
- Regex-based XSS pattern removal
- String length limits for action labels
- HTML entity escaping for user-generated content
- Rate limiting on action button generation

### 4. API Response Format

```json
{
  "response": "The Planning Commission will discuss the Electric Bicycle Safety Regulations at their September 2nd meeting...",
  "actions": [
    {
      "type": "email",
      "label": "Email Public Comment",
      "mailto": "city.clerk@cityofsanrafael.org",
      "subject": "Public Comment: Electric Bicycle Safety Regulations"
    },
    {
      "type": "calendar", 
      "label": "Add Meeting to Calendar",
      "event": {
        "id": "a7343560-2fb2-4d1a-a2dc-a4d07f223a20",
        "title": "Planning Commission Meeting",
        "start": "2025-09-02T18:00:00-07:00",
        "end": "2025-09-02T20:00:00-07:00", 
        "location": "City Hall, 1400 5th Ave, San Rafael, CA",
        "description": "Discussion on Electric Bicycle Safety Regulations"
      }
    },
    {
      "type": "link",
      "label": "View Meeting Agenda", 
      "url": "https://www.cityofsanrafael.org/meetings/planning-commission-september-2-2025/"
    }
  ],
  "data_freshness": {
    "warning": false,
    "age_days": 1,
    "last_updated": "2025-09-08T10:30:00Z"
  }
}
```

## Data Flow Architecture

```
1. User Query → Conversation API (/api/conversation)
2. AI Response Generation (OpenAI GPT-4)
3. Opportunity Matching Algorithm
   ├── Load civic opportunities from JSON files
   ├── Calculate relevance scores
   ├── Filter by user interests 
   └── Select top 3 matches
4. Action Button Generation
   ├── Email: Pre-fill contact info + subject
   ├── Calendar: Generate ICS with meeting details
   └── Link: Direct to civic resources
5. Security Validation & XSS Prevention
6. Response Assembly & Return to Frontend
7. Frontend Rendering
   ├── Native mailto: links
   ├── ICS download functionality
   └── External link navigation
```

## Performance Characteristics

### Response Time Targets
- **Action Generation**: <200ms (after AI response)
- **ICS File Creation**: <50ms (client-side JavaScript)
- **Security Validation**: <100ms (server-side)

### Scalability Metrics
- **Concurrent Users**: 100+ (current file-based architecture)
- **Opportunities Processed**: 1000+ per request
- **Memory Usage**: ~50MB per conversation instance

### Cost Analysis
- **OpenAI API**: ~$0.10-0.15 per conversation
- **Action Button Generation**: ~$0.001 per request (negligible)
- **Total Cost**: ~$0.15 per engaged user conversation

## Error Handling & Resilience

### Graceful Degradation
```javascript
// Calendar download with error handling
function downloadICS(event) {
    try {
        const ics = generateICS(event);
        const blob = new Blob([ics], { type: 'text/calendar' });
        const url = URL.createObjectURL(blob);
        
        const link = document.createElement('a');
        link.href = url;
        link.download = `${event.title.replace(/[^a-z0-9]/gi, '_')}.ics`;
        link.click();
        
        URL.revokeObjectURL(url);
        showSuccess('Meeting added to calendar!');
    } catch (error) {
        console.error('Calendar generation failed:', error);
        showError('Unable to create calendar event. Please add manually.');
        
        // Fallback: show meeting details for manual entry
        showMeetingDetails(event);
    }
}
```

### Failure Modes
1. **No Relevant Opportunities**: Return empty actions array
2. **Stale Data**: Display warning, provide manual refresh option
3. **ICS Generation Failure**: Show manual calendar instructions
4. **Email Client Missing**: Copy email details to clipboard
5. **Security Validation Failure**: Strip problematic content, log incident

## Testing Strategy

### Test Coverage Areas
1. **Functionality Tests** (`tests/test_all_fixes.py`)
   - Opportunity matching algorithm accuracy
   - Action button generation for various scenarios
   - ICS file RFC 5545 compliance
   - Email template generation

2. **Security Tests** (`tests/test_action_security.py`)
   - XSS payload injection prevention
   - Input validation edge cases
   - HTML entity escaping verification
   - Rate limiting enforcement

3. **Integration Tests** (`tests/test_action_buttons.py`)
   - End-to-end action button workflow
   - Frontend-backend communication
   - Error handling and graceful degradation
   - Cross-browser compatibility

### Success Metrics
- **Email Click-Through Rate**: Target 25%
- **Calendar Add Rate**: Target 15%
- **Action Completion Rate**: Target 10%
- **Error Rate**: <1% of action button interactions
- **Security Incidents**: 0 XSS vulnerabilities

## Future Enhancements

### Phase 2: Social Proof Integration
- "12 neighbors are following this issue" counters
- Community engagement statistics
- Peer influence indicators

### Phase 3: Advanced Actions
- Meeting RSVP with attendance tracking
- Document annotation and comment submission
- Petition signing and advocacy campaign joining
- Neighbor coordination and carpooling

### Phase 4: Personalization
- User-specific action prioritization
- Historical engagement pattern learning
- Custom action templates and preferences
- Multi-language action button support

## Deployment Considerations

### Production Requirements
- **SSL Certificate**: Required for secure email/calendar integration
- **CORS Configuration**: Enable cross-origin requests for action buttons
- **Rate Limiting**: Prevent abuse of action generation endpoints
- **Analytics Integration**: Track action button conversion rates
- **Content Security Policy**: Prevent XSS while allowing action functionality

### Monitoring & Analytics
```javascript
// Action button analytics tracking
function trackActionClick(actionType, opportunityId) {
    analytics.track('civic_action_clicked', {
        action_type: actionType,
        opportunity_id: opportunityId,
        user_interests: userProfile.interests,
        session_id: sessionId,
        timestamp: new Date().toISOString()
    });
}
```

---

*Architecture Document Version 1.0*  
*Last Updated: September 8, 2025*  
*Next Review: September 22, 2025*