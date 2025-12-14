# Civic Engagement Platform API Documentation

## Overview

The Civic API provides authenticated endpoints for conversational civic engagement, serving real-time civic opportunities with actionable engagement buttons. Built on Flask with OpenAI integration for natural language civic assistance.

**Base URL**: `http://localhost:8001` (development)  
**Authentication**: Bearer token required for all endpoints  
**Response Format**: JSON  

## Authentication

### Bearer Token Authentication
All API endpoints require a Bearer token in the Authorization header.

```http
Authorization: Bearer dev_key_local
```

**Development Token**: `dev_key_local`  
**Production Tokens**: Set via `CIVIC_WEB_KEY` environment variable

### Token Validation
```python
def authenticate_request(self):
    """Validate Bearer token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    
    token = auth_header.split(' ')[1]
    return token == self.api_key
```

## Core Endpoints

### GET /api/jurisdictions ✅ NEW (2025-10-13)

Returns aggregated jurisdiction data for navigation sidebar with event counts, issue counts, and CDBG allocations.

#### Request Format
```http
GET /api/jurisdictions HTTP/1.1
Host: localhost:8001
Authorization: Bearer your_api_key
```

#### Response Format
```json
{
  "jurisdictions": [
    {
      "id": "city-oakland",
      "name": "Oakland",
      "type": "city",
      "event_count": 15,
      "issue_count": 5,
      "cdbg_allocation": "$7.40M"
    },
    {
      "id": "city-berkeley",
      "name": "Berkeley",
      "type": "city",
      "event_count": 10,
      "issue_count": 12,
      "cdbg_allocation": "$2.67M"
    }
  ],
  "metadata": {
    "total_jurisdictions": 23,
    "total_events": 170,
    "total_issues": 48
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `jurisdictions` | array | List of jurisdictions with counts |
| `jurisdictions[].id` | string | Jurisdiction identifier (e.g., "city-berkeley") |
| `jurisdictions[].name` | string | Display name (e.g., "Berkeley") |
| `jurisdictions[].type` | string | Jurisdiction type: "city", "county", "transit_agency" |
| `jurisdictions[].event_count` | number | Number of civic events |
| `jurisdictions[].issue_count` | number | Number of filed complaints/issues |
| `jurisdictions[].cdbg_allocation` | string | CDBG funding amount (e.g., "$2.67M") or null |
| `metadata` | object | Summary statistics |

#### Data Sources
- Event data: Aggregated from `data/events/events_*.json` files
- Issue counts: Queried from `civic_participation.db` via ComplaintStorage
- CDBG allocations: Loaded from `data/jurisdiction_overrides/{jurisdiction_id}.json`
- Jurisdiction metadata: Mapped via `CITY_CONFIGS` in `automated_civic_refresh.py`

#### Implementation
- File: `src/civic_api_integrated.py:623-770`
- Method: `serve_jurisdictions()`

---

### GET /api/complaints ✅ NEW (2025-10-13)

Returns all complaints filed by a specific user with matched events and related complaints.

#### Request Format
```http
GET /api/complaints?user_id=test_user HTTP/1.1
Host: localhost:8001
Authorization: Bearer your_api_key
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | string | Yes | User identifier (query parameter) |

#### Response Format
```json
{
  "complaints": [
    {
      "id": "complaint-uuid",
      "user_id": "test_user",
      "description": "There is a huge pothole on Main Street that needs fixing",
      "issue_type": "infrastructure",
      "jurisdiction_id": "city-berkeley",
      "status": "open",
      "created_at": "2025-10-13T10:00:00",
      "updated_at": "2025-10-13T11:00:00",
      "matched_events": [
        {
          "event_id": "event-123",
          "match_score": 0.85,
          "match_reason": "Transportation topic + Main St location"
        }
      ],
      "related_complaints": ["complaint-uuid-2"],
      "discussion_group_id": null,
      "location": {
        "address": "Main St & 5th Ave",
        "latitude": 37.8715,
        "longitude": -122.2730
      }
    }
  ],
  "metadata": {
    "total_complaints": 1,
    "matched_count": 0,
    "open_count": 1
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `complaints` | array | List of user's filed complaints |
| `complaints[].id` | string | Complaint UUID |
| `complaints[].user_id` | string | User identifier |
| `complaints[].description` | string | Complaint description text |
| `complaints[].issue_type` | string | Issue category (housing, transportation, etc.) |
| `complaints[].jurisdiction_id` | string | City/county where issue occurred |
| `complaints[].status` | string | "open" or "closed" (lifecycle only, see closed_reason for closure type) |
| `complaints[].closed_reason` | string | "resolved", "duplicate", "not-actionable", "abandoned" (when closed) |
| `complaints[].closed_at` | string | ISO 8601 timestamp when closed |
| `complaints[].closed_note` | string | Optional note about closure |
| `complaints[].matched_events` | array | Civic meetings related to this complaint |
| `complaints[].related_complaints` | array | Similar complaints from other users |
| `complaints[].discussion_group_id` | string | Group ID if community formed (null in Phase 1) |
| `complaints[].location` | object | Optional address and coordinates |
| `metadata` | object | Summary statistics |

#### Data Sources
- Complaints: Queried from `civic_participation.db` via `ComplaintStorage.get_user_complaints(user_id)`
- Matched events: Retrieved via `complaint_matcher.py`
- Related complaints: Found via `find_similar_complaints()` (issue_type + jurisdiction matching)

#### Implementation
- File: `src/civic_api_integrated.py:772-849`
- Method: `serve_user_complaints(user_id)`
- Storage: `src/complaint_storage.py:140-200` (`get_user_complaints()` method)

#### Example Usage
```bash
# Get complaints for a user
curl -H "Authorization: Bearer ${CIVIC_WEB_KEY}" \
  "http://localhost:8001/api/complaints?user_id=test_user" | jq

# Returns empty list for new users
{
  "complaints": [],
  "metadata": {
    "total_complaints": 0,
    "matched_count": 0,
    "open_count": 0
  }
}
```

---

### GET /api/legislative/state ✅ NEW (2025-10-13)

Returns state legislation bills by topic for legislative context browsing.

#### Request Format
```http
GET /api/legislative/state?topic=housing HTTP/1.1
Host: localhost:8001
Authorization: Bearer your_api_key
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `topic` | string | Yes | Topic filter: "housing", "transportation", "environment", "budget", "education" |

#### Response Format
```json
{
  "state_bills": [
    {
      "bill": "AB 1319",
      "title": "Housing Accountability Act",
      "status": "Active",
      "leverage_point": "Cite when local governments delay housing approvals",
      "official_url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240AB1319",
      "summary": "Requires local governments to approve housing projects meeting zoning requirements",
      "keywords": ["housing", "zoning", "approval"]
    }
  ],
  "metadata": {
    "topic": "housing",
    "total_bills": 28,
    "cache_timestamp": "2025-10-13T12:00:00Z"
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `state_bills` | array | List of state bills for the requested topic |
| `state_bills[].bill` | string | Bill identifier (e.g., "AB 1319") |
| `state_bills[].title` | string | Bill title |
| `state_bills[].status` | string | Current legislative status |
| `state_bills[].leverage_point` | string | How to use this bill in civic engagement |
| `state_bills[].official_url` | string | Link to official bill text |
| `state_bills[].summary` | string | Brief bill description |
| `state_bills[].keywords` | array | Topic tags for filtering |
| `metadata` | object | Response metadata |

#### Data Sources
- Legislative data: Loaded from `data/legislative_context/california_{topic}.json`
- Cache: Managed via `legislative_context_cache.py` with TTL
- Topics: housing, transportation, environment, budget, education

#### Implementation
- File: `src/civic_api_integrated.py:899-979`
- Method: `serve_state_legislative_context(topic)`

---

### GET /api/legislative/federal ✅ NEW (2025-10-13)

Returns federal programs by topic for legislative context browsing.

#### Request Format
```http
GET /api/legislative/federal?topic=housing HTTP/1.1
Host: localhost:8001
Authorization: Bearer your_api_key
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `topic` | string | Yes | Topic filter: "housing", "transportation", "environment", "budget", "education" |

#### Response Format
```json
{
  "federal_programs": [
    {
      "program_name": "Community Development Block Grant (CDBG)",
      "agency": "HUD",
      "leverage_point": "Annual allocation for community projects with flexible use",
      "fy2025_allocation": "$2.67M",
      "info_url": "https://www.hud.gov/program_offices/comm_planning/cdbg",
      "description": "Federal funding for community development and housing projects",
      "keywords": ["housing", "community development", "funding"]
    }
  ],
  "metadata": {
    "topic": "housing",
    "total_programs": 9,
    "cache_timestamp": "2025-10-13T12:00:00Z"
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `federal_programs` | array | List of federal programs for the requested topic |
| `federal_programs[].program_name` | string | Program name |
| `federal_programs[].agency` | string | Federal agency (e.g., "HUD", "DOT") |
| `federal_programs[].leverage_point` | string | How to use this program in civic engagement |
| `federal_programs[].fy2025_allocation` | string | Fiscal year allocation (if available) |
| `federal_programs[].info_url` | string | Link to program information |
| `federal_programs[].description` | string | Program description |
| `federal_programs[].keywords` | array | Topic tags for filtering |
| `metadata` | object | Response metadata |

#### Data Sources
- Program data: Loaded from `data/federal_programs/{topic}.json`
- Allocations: Merged from `data/jurisdiction_overrides/{jurisdiction_id}.json`
- Cache: Managed via `legislative_context_cache.py` with TTL
- Topics: housing, transportation, environment, budget, education

#### Implementation
- File: `src/civic_api_integrated.py:981-1061`
- Method: `serve_federal_legislative_context(topic)`

---

### POST /api/conversation

Main conversational endpoint that processes user queries and returns AI responses with civic action buttons. Also handles automatic complaint detection and filing.

#### Request Format
```json
{
  "message": "What housing opportunities are available?",
  "city": "San Rafael",
  "state": "California", 
  "county": "Marin County",
  "interests": ["housing", "development"]
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | User's question or civic inquiry |
| `city` | string | Yes | User's city for relevant opportunities |
| `state` | string | Yes | User's state |
| `county` | string | No | User's county (for additional filtering) |
| `interests` | array | No | User interests for opportunity matching |

#### Response Format
```json
{
  "response": "The Planning Commission will discuss the Electric Bicycle Safety Regulations at their September 2nd meeting. This regulation will establish safety standards for e-bike operation within city limits.\n\nYou can participate by:
- Attending the meeting in person at City Hall
- Submitting written comments via email
- Calling in during the public comment period\n\nWould you like me to help you prepare a public comment or add this meeting to your calendar?",
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
        "title": "Planning Commission Meeting - Electric Bicycle Safety",
        "start": "2025-09-02T18:00:00-07:00",
        "end": "2025-09-02T20:00:00-07:00",
        "location": "City Hall, 1400 5th Ave, San Rafael, CA",
        "description": "Discussion on Electric Bicycle Safety Regulations. Public comment period included."
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
  },
  "processing_metadata": {
    "opportunities_considered": 5,
    "actions_generated": 3,
    "relevance_threshold_met": true,
    "response_time_ms": 1247
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | AI-generated response to user query |
| `actions` | array | Action buttons for civic engagement |
| `data_freshness` | object | Data staleness information |
| `processing_metadata` | object | Performance and processing details |

#### Action Button Types

**Email Actions**
```json
{
  "type": "email",
  "label": "Email Public Comment",
  "mailto": "city.clerk@cityofsanrafael.org", 
  "subject": "Public Comment: Housing Development Project #2024-15"
}
```

**Calendar Actions**  
```json
{
  "type": "calendar",
  "label": "Add Meeting to Calendar",
  "event": {
    "id": "unique-opportunity-id",
    "title": "City Council Meeting",
    "start": "2025-09-02T18:00:00-07:00",
    "end": "2025-09-02T20:00:00-07:00", 
    "location": "City Hall, 1400 5th Ave, San Rafael, CA",
    "description": "Meeting description with agenda details"
  }
}
```

**Link Actions**
```json
{
  "type": "link",
  "label": "View Project Details",
  "url": "https://www.cityofsanrafael.org/projects/housing-development-2024/"
}
```

#### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | Success | Request processed successfully |
| 400 | Bad Request | Missing required parameters |
| 401 | Unauthorized | Invalid or missing Bearer token |
| 429 | Rate Limited | Too many requests |
| 500 | Server Error | Internal processing error |

#### Error Response Format
```json
{
  "error": "Missing required parameter: message",
  "code": "INVALID_REQUEST",
  "timestamp": "2025-09-08T15:30:00Z"
}
```

---

### POST /api/events/:event_id/draft-comment ✅ NEW (2025-10-28)

Generate AI-powered public comment draft using structured user input. Accepts position, key concern, and personal context to generate contextual, personalized comment.

#### Request Format
```json
{
  "agendaItemId": "item-7.2",
  "position": "oppose",
  "keyConcern": "This will increase traffic on Main Street during school pickup hours",
  "personalContext": {
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "district": "District 3",
    "neighborhood": "Rockridge",
    "expertise": "Transportation planner"
  }
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agendaItemId` | string | No | Specific agenda item ID (if commenting on individual item) |
| `position` | string | No | User's position: "support", "oppose", "neutral", "questions" |
| `keyConcern` | string | No | User's main concern (1-2 sentences) |
| `personalContext` | object | No | Personal context to establish credibility |
| `personalContext.stakes` | array | No | User's stakes: "homeowner", "renter", "parent", "business_owner", etc. |
| `personalContext.yearsInArea` | number | No | Years of residency |
| `personalContext.district` | string | No | District or neighborhood |
| `personalContext.neighborhood` | string | No | Specific neighborhood name |
| `personalContext.expertise` | string | No | Relevant professional expertise |

**Note**: All parameters are optional. With no parameters, generates a generic comment. With structured input, generates personalized, contextual comment.

#### Response Format
```json
{
  "draft": "I am writing to express my concern about the proposed use permit at 2850 Telegraph Ave. As a homeowner and parent in Rockridge for 15 years, I am deeply worried about the traffic impact this project will have on Main Street during school pickup hours.\n\nThe intersection of Main Street and Telegraph Avenue is already congested between 2:30-3:30 PM on weekdays. Adding 20 new residential units without additional parking or traffic mitigation will exacerbate safety issues for children walking to and from school. As a transportation planner, I've seen similar projects create dangerous conditions in other neighborhoods.\n\nI urge the Planning Commission to require a comprehensive traffic study and implement pedestrian safety improvements before approving this permit. Our children's safety must be the priority.",
  "metadata": {
    "model": "gpt-4o-mini",
    "tokens_used": 1842,
    "cost": 0.00184,
    "generation_time_ms": 1247
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `draft` | string | AI-generated comment draft (2-3 paragraphs, 150-250 words) |
| `metadata` | object | Generation metadata |
| `metadata.model` | string | AI model used for generation |
| `metadata.tokens_used` | number | Total tokens consumed |
| `metadata.cost` | number | Cost in USD |
| `metadata.generation_time_ms` | number | Generation time in milliseconds |

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 404 | Not Found - Event or agenda item not found |
| 429 | Too Many Requests - Rate limit exceeded (20 drafts per hour) |
| 500 | Internal Server Error - Database or OpenAI API error |
| 503 | Service Unavailable - OpenAI API rate limit exceeded |

#### Implementation
- File: `src/civic_api_integrated.py:1946-2116`
- Method: `handle_draft_comment()`
- Model: gpt-4o-mini
- Cost: ~$0.002 per draft
- Rate Limit: 20 requests per hour per user

---

### POST /api/comments ✅ NEW (2025-10-28)

Store structured comment data with position, key concern, personal context, and optional AI-generated draft.

#### Request Format
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "agendaItemId": "item-7.2",
  "position": "oppose",
  "keyConcern": "This will increase traffic on Main Street during school pickup hours",
  "personalContext": {
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "district": "District 3",
    "neighborhood": "Rockridge",
    "expertise": "Transportation planner"
  },
  "aiDraftGenerated": true,
  "aiDraft": "I am writing to express my concern...",
  "finalComment": "Dear Planning Commission,\n\nI am writing to express...",
  "submissionFormat": "written"
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `eventId` | string | Yes | Event ID this comment is for |
| `agendaItemId` | string | No | Specific agenda item ID (optional) |
| `position` | string | Yes | User's position: "support", "oppose", "neutral", "questions" |
| `keyConcern` | string | Yes | User's main concern (1-2 sentences) |
| `personalContext` | object | No | Personal context object |
| `aiDraftGenerated` | boolean | No | Whether AI draft was generated (default: false) |
| `aiDraft` | string | No | AI-generated draft text |
| `finalComment` | string | No | Final comment after user edits |
| `submissionFormat` | string | No | Format: "written", "oral", "letter", "email" (default: "written") |

#### Response Format
```json
{
  "id": "comment-abc123",
  "eventId": "event-berkeley-planning-2025-11-15",
  "agendaItemId": "item-7.2",
  "position": "oppose",
  "keyConcern": "This will increase traffic on Main Street during school pickup hours",
  "personalContext": {
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "district": "District 3",
    "neighborhood": "Rockridge",
    "expertise": "Transportation planner"
  },
  "aiDraftGenerated": true,
  "finalComment": "Dear Planning Commission,\n\nI am writing to express...",
  "submissionFormat": "written",
  "submitted": false,
  "createdAt": "2025-10-28T14:30:00Z",
  "updatedAt": "2025-10-28T14:30:00Z"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Missing required fields (eventId, position, keyConcern) or invalid enum values |
| 401 | Unauthorized - Invalid or missing Bearer token |
| 429 | Too Many Requests - Rate limit exceeded (5 comments per user per day) |
| 500 | Internal Server Error - Database error |

#### Implementation
- Database: `civic_participation.db` table `comments`
- Storage: SQLite with JSON fields for structured data
- Schema: See `COMMENT_DRAFTING_ARCHITECTURE.md` Part 10.1
- Rate Limit: 5 comments per user per day

---

### GET /api/comments/:comment_id ✅ NEW (2025-10-28)

Retrieve a single comment by ID.

#### Response Format
```json
{
  "id": "comment-abc123",
  "eventId": "event-berkeley-planning-2025-11-15",
  "position": "oppose",
  "keyConcern": "This will increase traffic on Main Street during school pickup hours",
  "personalContext": { "..." },
  "finalComment": "Dear Planning Commission...",
  "submissionFormat": "written",
  "submitted": false,
  "createdAt": "2025-10-28T14:30:00Z"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 404 | Not Found - Comment not found |
| 500 | Internal Server Error - Database error |

---

### PATCH /api/comments/:comment_id ✅ NEW (2025-10-28)

Update an existing comment draft (before submission).

Update an existing comment draft (before submission).

#### Request Format
```json
{
  "finalComment": "Updated comment text after user edits...",
  "submitted": true,
  "submittedAt": "2025-10-28T15:30:00Z"
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `finalComment` | string | No | Updated comment text |
| `position` | string | No | Updated position |
| `keyConcern` | string | No | Updated key concern |
| `submitted` | boolean | No | Mark as submitted to council |
| `submittedAt` | string | No | ISO timestamp of submission |

**Note**: All fields are optional. Only provided fields will be updated.

#### Response Format
```json
{
  "id": "comment-abc123",
  "eventId": "event-berkeley-planning-2025-11-15",
  "position": "oppose",
  "keyConcern": "This will increase traffic on Main Street during school pickup hours",
  "personalContext": { "..." },
  "finalComment": "Updated comment text...",
  "submissionFormat": "written",
  "submitted": true,
  "submittedAt": "2025-10-28T15:30:00Z",
  "createdAt": "2025-10-28T14:30:00Z",
  "updatedAt": "2025-10-28T15:30:00Z"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Invalid field values |
| 401 | Unauthorized - Invalid Bearer token or not comment owner |
| 404 | Not Found - Comment not found |
| 409 | Conflict - Cannot edit already-submitted comment |
| 500 | Internal Server Error - Database error |

#### Use Cases
- User edits AI-generated draft → PATCH with `finalComment`
- User submits comment → PATCH with `submitted: true, submittedAt`
- User changes position before submitting → PATCH with `position`

---

### GET /api/events/:event_id/comments ✅ NEW (2025-10-28)

Retrieve all comments for a specific event, with optional filtering.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `position` | string | No | Filter by position: "support", "oppose", "neutral", "questions" |
| `agendaItemId` | string | No | Filter by specific agenda item |
| `format` | string | No | Response format: "summary" or "full" (default: "full") |

#### Response Format (Full)
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "totalComments": 21,
  "comments": [
    {
      "id": "comment-abc123",
      "position": "oppose",
      "keyConcern": "Traffic impact on Main Street",
      "personalContext": { "..." },
      "finalComment": "Dear Planning Commission...",
      "createdAt": "2025-10-28T14:30:00Z"
    }
  ]
}
```

#### Response Format (Summary)
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "totalComments": 21,
  "summaryCards": [
    {
      "commentId": "comment-abc123",
      "position": "oppose",
      "keyConcern": "Traffic impact on Main Street",
      "stakes": ["homeowner", "parent"],
      "residency": "15 years, District 3, Rockridge",
      "expertise": "Transportation planner",
      "submissionFormat": "written",
      "submittedAt": "2025-10-28T14:30:00Z"
    }
  ]
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 404 | Not Found - Event not found |
| 500 | Internal Server Error - Database error |

---

### GET /api/events/:event_id/comment-stats ✅ NEW (2025-10-28)

Get aggregated statistics for all comments on an event, including position breakdown, top concerns, and stakeholder analysis.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agendaItemId` | string | No | Filter stats to specific agenda item |

#### Response Format
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "agendaItemId": null,
  "positionCounts": {
    "support": 15,
    "oppose": 3,
    "neutral": 2,
    "questions": 1
  },
  "totalComments": 21,
  "topConcerns": [
    {
      "theme": "traffic impact",
      "count": 8,
      "example": "This will increase traffic on Main Street during school pickup hours"
    },
    {
      "theme": "parking availability",
      "count": 5,
      "example": "The project doesn't provide adequate parking for residents"
    },
    {
      "theme": "building height",
      "count": 3,
      "example": "The proposed 4-story building is out of character with the neighborhood"
    }
  ],
  "stakeBreakdown": {
    "homeowner": 12,
    "renter": 5,
    "parent": 8,
    "business_owner": 2,
    "senior": 1
  },
  "formatBreakdown": {
    "written": 18,
    "oral": 2,
    "letter": 1,
    "email": 0
  },
  "timeline": {
    "firstComment": "2025-10-15T09:00:00Z",
    "lastComment": "2025-10-28T14:30:00Z"
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `eventId` | string | Event ID |
| `agendaItemId` | string | Agenda item ID (null if all items) |
| `positionCounts` | object | Breakdown of support/oppose/neutral/questions |
| `totalComments` | number | Total number of comments |
| `topConcerns` | array | Most common themes mentioned (NLP keyword matching) |
| `stakeBreakdown` | object | Count of comments by stakeholder type |
| `formatBreakdown` | object | Count of comments by submission format |
| `timeline` | object | First and last comment timestamps |

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 404 | Not Found - Event not found |
| 500 | Internal Server Error - Database error |

#### Implementation
- Analysis: Keyword matching for concern themes
- Caching: 5 minutes (Cache-Control: public, max-age=300)
- Performance: O(n) scan, optimized with database indexes
- Cache invalidation: On new comment POST

---

## 6. User Profile & Personalization ✅ Phase 2 Complete (2025-10-29)

The Personalization Service provides centralized user context management, civic history tracking, and behavioral inference.

**Implementation Status**:
- ✅ **Phase 1 Complete**: Database schema + PersonalizationService class (98% test coverage)
- ✅ **Phase 2 Complete**: REST API endpoints + authentication (all 6 endpoints operational)
- ⏳ **Phase 3 Planned**: Full behavioral inference + recommendation scoring (Week 3)
- ⏳ **Phase 4 Planned**: Comment drafting integration + frontend (Week 4)

**Authentication**: All personalization endpoints require Bearer token authentication. For MVP, the Bearer token serves dual purpose: authentication AND user identification.

**MVP Authentication Model**:
```http
Authorization: Bearer dev_key_local
```
In this model:
- Bearer token must be a valid API key (configured via CIVIC_WEB_KEY)
- Bearer token IS the user_id (simple authentication + identification)
- Production upgrade: Use JWT with user_id in payload, validated against database

**See Also**: `docs/PERSONALIZATION_SERVICE_ARCHITECTURE.md` for complete architecture

### Quick Start: Testing with curl

```bash
# Set Bearer token (use valid API key)
TOKEN="dev_key_local"

# 1. Create user profile
curl -X POST http://localhost:8001/api/user/profile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jurisdictionId": "city-berkeley",
    "displayName": "Jane Doe",
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "civicInterests": ["housing", "education"]
  }'

# 2. Get user profile
curl -X GET http://localhost:8001/api/user/profile \
  -H "Authorization: Bearer $TOKEN"

# 3. Get civic history
curl -X GET http://localhost:8001/api/user/civic-history \
  -H "Authorization: Bearer $TOKEN"

# 4. Get AI context (for comment drafting)
curl -X GET "http://localhost:8001/api/user/context?type=demographics" \
  -H "Authorization: Bearer $TOKEN"

# 5. Export all data (GDPR)
curl -X GET http://localhost:8001/api/user/export \
  -H "Authorization: Bearer $TOKEN"

# 6. Delete account (GDPR)
curl -X DELETE http://localhost:8001/api/user \
  -H "Authorization: Bearer $TOKEN"
```

For automated testing, see: `test_personalization_endpoints.sh`

---

### POST /api/user/profile

Create or update user profile with demographics and civic context.

#### Request Format
```json
{
  "displayName": "Jane Doe",
  "stakes": ["homeowner", "parent"],
  "yearsInArea": 15,
  "district": "District 3",
  "neighborhood": "Rockridge",
  "jurisdictionId": "city-berkeley",
  "expertise": "Urban planning",
  "civicInterests": ["housing", "transportation"],
  "notificationPreferences": {
    "email": true,
    "sms": false,
    "frequency": "weekly"
  },
  "privacySettings": {
    "profileVisibility": "public",
    "showCivicHistory": true,
    "allowBehavioralInference": true
  }
}
```

#### Response Format
```json
{
  "userId": "user-abc123",
  "profileCompleteness": 85,
  "createdAt": "2025-10-29T10:00:00Z",
  "updatedAt": "2025-10-29T10:00:00Z"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Missing required fields (userId, jurisdictionId) |
| 401 | Unauthorized - Invalid Bearer token |
| 500 | Internal Server Error - Database error |

---

### GET /api/user/profile

Get user profile with completeness score and improvement suggestions.

#### Response Format
```json
{
  "profile": {
    "userId": "user-abc123",
    "displayName": "Jane Doe",
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "neighborhood": "Rockridge",
    "jurisdictionId": "city-berkeley",
    "civicInterests": ["housing"],
    "profileCompleteness": 65
  },
  "suggestions": [
    {
      "field": "expertise",
      "benefit": "Improves AI comment quality by 40%",
      "weight": 15
    },
    {
      "field": "civicInterests",
      "benefit": "Get 2x more relevant meeting recommendations",
      "weight": 20
    }
  ]
}
```

---

### GET /api/user/civic-history

Get user's civic action history with filtering options.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action_types` | string | No | Comma-separated action types to filter |
| `since` | string | No | ISO timestamp (default: 90 days ago) |
| `limit` | number | No | Max results (default: 100) |

#### Response Format
```json
{
  "actions": [
    {
      "actionId": "action-123",
      "actionType": "comment_drafted",
      "entityType": "event",
      "entityId": "event-berkeley-planning-2025-11-15",
      "metadata": {
        "position": "oppose",
        "topic": "housing"
      },
      "createdAt": "2025-10-28T14:30:00Z"
    }
  ],
  "metadata": {
    "total_actions": 47,
    "date_range": {
      "start": "2025-07-30T00:00:00Z",
      "end": "2025-10-29T00:00:00Z"
    }
  }
}
```

---

### GET /api/user/context

Get personalized context for AI features (comment drafting, recommendations). User ID extracted from Bearer token.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `type` | string | No | Context type: `demographics`, `interests`, `history`, `full` (default: `full`) |

#### Context Types

- **demographics**: Stakes, years in area, expertise (for comment drafting)
- **interests**: Civic interests + inferred topics from behavioral history
- **history**: Recent civic actions (last 10)
- **full**: All of the above combined

#### Response Format (type=full)
```json
{
  "stakes": ["homeowner", "parent"],
  "yearsInArea": 15,
  "district": "District 3",
  "neighborhood": "Rockridge",
  "expertise": "Urban planning",
  "civicInterests": ["housing", "transportation"],
  "inferredInterests": {
    "housing": 0.92,
    "transportation": 0.45
  },
  "recentActions": [
    {
      "type": "event_clicked",
      "topic": "housing",
      "date": "2025-10-28T14:30:00Z"
    }
  ]
}
```

#### Response Format (type=demographics)
```json
{
  "stakes": ["homeowner", "parent"],
  "yearsInArea": 15,
  "district": "District 3",
  "neighborhood": "Rockridge",
  "expertise": "Urban planning"
}
```

#### Use Cases
- **Comment Drafting**: Use `type=demographics` for personalized AI comment generation
- **Recommendations**: Use `type=interests` for event scoring
- **Analytics**: Use `type=full` for comprehensive user understanding

#### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Bad Request - Invalid context type |
| 401 | Unauthorized - Invalid Bearer token |
| 404 | Not Found - User profile not found |
| 503 | Service Unavailable - PersonalizationService not available |

---

### GET /api/user/export

**GDPR Compliance**: Export all user data in machine-readable JSON format. User ID extracted from Bearer token.

#### Response Format
```json
{
  "export_date": "2025-10-29T13:21:20.760243",
  "user_id": "dev_key_local",
  "profile": {
    "user_id": "dev_key_local",
    "display_name": "Jane Doe",
    "stakes": ["homeowner", "parent"],
    "years_in_area": 15,
    "jurisdiction_id": "city-berkeley",
    "civic_interests": ["housing", "education"],
    "profile_completeness": 65,
    "created_at": "2025-10-29 20:21:20"
  },
  "civic_history": [
    {
      "action_id": "action-123",
      "action_type": "comment_drafted",
      "entity_type": "event",
      "entity_id": "event-berkeley-planning-123",
      "metadata": {"topic": "housing"},
      "created_at": "2025-10-28T14:30:00"
    }
  ],
  "inferred_interests": {
    "housing": 0.92,
    "transportation": 0.45
  }
}
```

#### Data Included
- Complete user profile with all fields
- Full civic history (up to 10,000 actions)
- Behavioral inference results (inferred interests with confidence scores)
- Export metadata (timestamp, user_id)

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 503 | Service Unavailable - PersonalizationService not available |

---

### DELETE /api/user

**GDPR Compliance**: Permanently delete user account and all associated data. User ID extracted from Bearer token.

#### Response Format
```json
{
  "success": true,
  "message": "User account deleted successfully",
  "user_id": "dev_key_local",
  "deleted_count": {
    "profile": 1,
    "civic_history": 42,
    "inferred_interests": 5
  }
}
```

#### Data Deleted
- User profile from `user_profiles` table
- All civic history records from `civic_history` table
- All inferred interests from `inferred_interests` table
- User removed from PersonalizationService cache

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 503 | Service Unavailable - PersonalizationService not available |

---

### GET /api/user/civic-metrics ⏳ Phase 3 (Planned)

Get aggregated civic impact metrics and engagement statistics.

#### Response Format
```json
{
  "engagementTier": "participant",
  "totalActions": 47,
  "actionsLast30Days": 12,
  "commentsDrafted": 8,
  "issuesFiled": 3,
  "meetingsAttended": 2,
  "emailsSent": 5,
  "topicBreakdown": {
    "housing": 28,
    "transportation": 12,
    "environment": 7
  },
  "currentStreak": 5,
  "longestStreak": 12,
  "issuesResolved": 2
}
```

#### Engagement Tiers

| Tier | Criteria |
|------|----------|
| `observer` | 0-5 total actions |
| `participant` | 6-20 actions |
| `organizer` | 21-50 actions |
| `leader` | 50+ actions |

---

### GET /api/user/inferred-interests ⏳ Phase 3 (Planned)

Get behavioral inference of user's civic interests and expertise.

**Note**: Basic inference is available via `/api/user/context?type=interests`. This endpoint will provide extended inference with confidence scores and jurisdictional affinity.

#### Response Format
```json
{
  "interests": {
    "housing": 0.92,
    "transportation": 0.45,
    "environment": 0.12
  },
  "inferredExpertise": "Housing/Urban Planning",
  "jurisdictionAffinity": ["city-berkeley", "city-oakland"],
  "confidence": "high",
  "actionsAnalyzed": 47,
  "lastComputedAt": "2025-10-29T08:00:00Z"
}
```

#### Interest Confidence Scores

| Score | Interpretation |
|-------|----------------|
| 0.8-1.0 | Very engaged (80%+ actions in this topic) |
| 0.5-0.79 | Moderately engaged |
| 0.1-0.49 | Minimal engagement |
| <0.1 | Filtered out (noise) |

---

### GET /api/user/recommended-events ⏳ Phase 3 (Planned)

Get personalized event recommendations based on profile and behavior.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | number | No | Max events to return (default: 10) |

#### Response Format
```json
{
  "recommended_events": [
    {
      "eventId": "event-123",
      "title": "Housing Element Update",
      "date": "2025-11-15T18:00:00-08:00",
      "jurisdictionId": "city-berkeley",
      "recommendationScore": 0.92,
      "matchReasons": [
        "Housing (your top interest - 28 interactions)",
        "Berkeley (your primary jurisdiction)",
        "Meeting (you've attended 2 similar meetings)"
      ]
    }
  ],
  "personalization_factors": {
    "interests": {
      "housing": 0.92,
      "transportation": 0.45
    },
    "jurisdictions": ["city-berkeley", "city-oakland"]
  }
}
```

#### Recommendation Scoring

Scoring factors (0-1 scale):
- **Topic match** (40%): Alignment with inferred interests
- **Jurisdiction match** (30%): User's primary/secondary cities
- **Event type preference** (15%): Based on past attendance patterns
- **Recency & urgency** (15%): Upcoming meetings weighted higher

---

### POST /api/user/track-action ⏳ Phase 3 (Internal - Planned)

Track civic action for behavioral inference. Called internally by other endpoints.

**Note**: Currently tracked via direct PersonalizationService.track_action() calls from other endpoints (comment drafting, event views, etc.).

#### Request Format
```json
{
  "actionType": "comment_drafted",
  "entityType": "event",
  "entityId": "event-berkeley-planning-2025-11-15",
  "metadata": {
    "position": "oppose",
    "topic": "housing",
    "aiGenerated": true
  }
}
```

#### Response Format
```json
{
  "actionId": "action-abc123",
  "tracked": true,
  "inferenceUpdated": false
}
```

**Note**: Inference cache updates asynchronously (doesn't block request).

- All follows/subscriptions
- All filed issues
- All draft comments

#### Error Responses

| Status | Description |
|--------|-------------|
| 401 | Unauthorized - Invalid Bearer token |
| 404 | Not Found - User profile not found |
| 500 | Internal Server Error |

**Warning**: This operation is **irreversible**. All user data will be permanently deleted.

---

## Data Processing Pipeline

### 1. Input Processing
```python
def process_conversation_request(self):
    data = request.get_json()
    
    # Validate required fields
    if not data or 'message' not in data:
        return {'error': 'Missing required parameter: message'}, 400
    
    # Security validation
    message = self.validate_action_input(data['message'])
    interests = data.get('interests', [])
    
    return self.generate_civic_response(message, interests)
```

### 2. Opportunity Matching Algorithm
```python
def find_relevant_opportunities(self, ai_response: str, interests: list) -> list:
    """Find civic opportunities relevant to user interests and AI response"""
    opportunities = self.load_civic_opportunities()
    scored_opportunities = []
    
    for opp in opportunities:
        # Interest-based filtering
        if interests and opp.get('project_type') not in interests:
            continue
            
        # Relevance scoring based on word overlap
        score = self.calculate_relevance_score(opp['title'], ai_response)
        
        if score >= self.RELEVANCE_THRESHOLD:
            scored_opportunities.append((opp, score))
    
    # Return top matches
    scored_opportunities.sort(key=lambda x: x[1], reverse=True)
    return [opp for opp, score in scored_opportunities[:self.MAX_ACTION_BUTTONS]]
```

### 3. Action Button Generation
```python
def generate_action_buttons(self, opportunities: list) -> list:
    """Generate action buttons for civic opportunities"""
    actions = []
    
    for opp in opportunities:
        # Email action
        if opp.get('contact_info', {}).get('email'):
            actions.append({
                'type': 'email',
                'label': f"Email about {opp['title'][:20]}...",
                'mailto': opp['contact_info']['email'],
                'subject': f"Public Comment: {opp['title']}"
            })
        
        # Calendar action
        if opp.get('when'):
            actions.append({
                'type': 'calendar',
                'label': 'Add Meeting to Calendar',
                'event': self.format_calendar_event(opp)
            })
        
        # Link action
        if opp.get('source_url'):
            actions.append({
                'type': 'link',
                'label': 'View Details',
                'url': opp['source_url']
            })
    
    return actions[:self.MAX_ACTION_BUTTONS]
```

## Security Features

### Input Validation & XSS Prevention
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

### Rate Limiting
```python
class RateLimiter:
    def __init__(self, max_requests=100, window_seconds=3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def allow_request(self, client_id: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id] 
            if req_time > window_start
        ]
        
        if len(self.requests[client_id]) >= self.max_requests:
            return False
            
        self.requests[client_id].append(now)
        return True
```

## Data Sources

### Civic Opportunities Schema
The API loads civic opportunities from JSON files in `data/schema/` following this format:

```json
{
  "id": "unique-opportunity-id",
  "title": "Electric Bicycle Safety Regulations",
  "description": "Regulates the operation of electric mobility devices within city limits.",
  "when": "2025-09-02T18:00:00-07:00",
  "deadline": "2025-09-02T23:59:59-07:00",
  "engagement_info": "Attend the meeting in person or submit comments via email.",
  "impact_summary": "Will establish safety standards affecting all e-bike users in the city.",
  "source_url": "https://www.cityofsanrafael.org/meetings/planning-commission-september-2-2025/",
  "location": "San Rafael",
  "meeting_type": "planning_commission",
  "project_type": "transportation",
  "engagement_tier": "quick_action",
  "contact_info": {
    "email": "city.clerk@cityofsanrafael.org",
    "name": "City Clerk",
    "phone": "(415) 485-3066"
  },
  "created_at": "2025-09-08T10:30:00Z",
  "scraped_from": "https://www.cityofsanrafael.org/meetings/"
}
```

## Configuration

### Environment Variables
```bash
# Required
OPENAI_API_KEY=your-openai-api-key
CIVIC_WEB_KEY=your-production-api-key

# Optional
PORT=8001
DEBUG=true
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
DATA_DIRECTORY=data/schema
LOG_LEVEL=INFO
```

### Configuration Constants
```python
# API Configuration
DEFAULT_PORT = 8001
API_TIMEOUT_SECONDS = 30
MAX_MESSAGE_LENGTH = 1000

# Action Button Configuration
MAX_ACTION_BUTTONS = 3
RELEVANCE_THRESHOLD = 0.3
ACTION_LABEL_MAX_LENGTH = 30

# Data Configuration
DATA_STALENESS_DAYS = 7
DEFAULT_MEETING_DURATION_HOURS = 2
MAX_OPPORTUNITIES_PROCESSED = 100

# Security Configuration
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW_SECONDS = 3600
VALID_API_KEY_LENGTH = 8
```

## Performance Characteristics

### Response Times (Target)
- **Simple Queries**: <500ms
- **Complex Civic Questions**: <2000ms  
- **Action Button Generation**: <200ms additional
- **Cold Start**: <5000ms (first request)

### Throughput
- **Concurrent Users**: 50+ (development server)
- **Requests per Hour**: 1000+ per API key
- **Peak Response Time**: <5000ms under load

### Resource Usage
- **Memory**: ~100MB base + 50MB per active conversation
- **CPU**: Moderate (primarily I/O bound)
- **Storage**: Minimal (file-based civic data)

## Error Handling

### Common Error Scenarios

**Missing Authentication**
```json
{
  "error": "Authorization header required",
  "code": "MISSING_AUTH",
  "timestamp": "2025-09-08T15:30:00Z"
}
```

**Invalid Request Format**
```json
{
  "error": "Invalid JSON in request body", 
  "code": "INVALID_JSON",
  "timestamp": "2025-09-08T15:30:00Z"
}
```

**Rate Limit Exceeded**
```json
{
  "error": "Rate limit exceeded. Try again in 60 seconds.",
  "code": "RATE_LIMITED",
  "retry_after": 60,
  "timestamp": "2025-09-08T15:30:00Z"
}
```

**OpenAI API Error**
```json
{
  "error": "AI service temporarily unavailable",
  "code": "AI_SERVICE_ERROR", 
  "timestamp": "2025-09-08T15:30:00Z"
}
```

### Graceful Degradation
When action button generation fails, the API returns the AI response without actions:

```json
{
  "response": "AI response here...",
  "actions": [],
  "data_freshness": {...},
  "warning": "Action buttons temporarily unavailable"
}
```

## Testing

### Integration Testing
```bash
# Start API server
python src/civic_api_integrated.py &

# Run comprehensive test suite
python tests/test_all_fixes.py
python tests/test_action_security.py  
python tests/test_action_buttons.py
```

### Manual API Testing
```bash
# Test conversation endpoint
curl -X POST http://localhost:8001/api/conversation \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev_key_local" \
  -d '{
    "message": "What housing opportunities are available?",
    "city": "San Rafael",
    "state": "California",
    "interests": ["housing"]
  }'
```

### Load Testing
```bash
# Using Apache Bench
ab -n 1000 -c 10 -H "Authorization: Bearer dev_key_local" \
   -T "application/json" \
   -p test_payload.json \
   http://localhost:8001/api/conversation
```

## Deployment

### Production Setup
```bash
# Install dependencies
pip install flask requests openai

# Set environment variables
export OPENAI_API_KEY="your-production-key"
export CIVIC_WEB_KEY="your-secure-api-key"
export PORT=8001

# Start server
python src/civic_api_integrated.py
```

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
COPY data/ ./data/
EXPOSE 8001
CMD ["python", "src/civic_api_integrated.py"]
```

### Health Check Endpoint
The API includes a basic health check:

```bash
curl http://localhost:8001/health
# Returns: {"status": "healthy", "timestamp": "2025-09-08T15:30:00Z"}
```

## Monitoring & Analytics

### Key Metrics to Track
- **Request Volume**: Total API calls per hour/day
- **Response Times**: P95/P99 latency percentiles
- **Error Rates**: 4xx/5xx error percentages
- **Action Button Engagement**: Click-through rates by type
- **OpenAI API Costs**: Token usage and cost per conversation
- **User Interests Distribution**: Most requested civic topics

### Logging Format
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Example log entries
# 2025-09-08 15:30:00 - civic_api - INFO - Conversation request processed in 1247ms
# 2025-09-08 15:30:01 - civic_api - INFO - Generated 3 action buttons for housing query
# 2025-09-08 15:30:02 - civic_api - WARN - Data staleness warning: 8 days old
```

---

### POST /api/chat/route ✅ NEW (2025-10-22)

Routes conversational chat messages to appropriate functions using OpenAI function calling.

#### Request Format
```http
POST /api/chat/route HTTP/1.1
Host: localhost:8001
Authorization: Bearer your_api_key
Content-Type: application/json
```

```json
{
  "message": "Show me housing meetings in Berkeley",
  "conversation_id": "optional-session-id",
  "context": {
    "current_artifact": "event-123",
    "current_jurisdiction": "city-berkeley"
  }
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | User's chat message |
| `conversation_id` | string | No | Session identifier for conversation continuity |
| `context` | object | No | Current UI context (active artifact, jurisdiction, etc.) |

#### Response Format (Function Call)
```json
{
  "action": "search_events",
  "parameters": {
    "query": "housing",
    "jurisdiction": "Berkeley"
  },
  "reasoning": "I'll search for housing-related meetings in Berkeley.",
  "conversation_id": "abc-123",
  "usage": {
    "prompt_tokens": 450,
    "completion_tokens": 180,
    "total_tokens": 630
  }
}
```

#### Response Format (Conversational)
```json
{
  "action": "respond",
  "message": "Sure! Let me explain how city council meetings work...",
  "conversation_id": "abc-123",
  "usage": {
    "prompt_tokens": 400,
    "completion_tokens": 200,
    "total_tokens": 600
  }
}
```

#### Available Actions

**Navigation Actions**:
- `search_events` - Search for civic meetings/events
- `view_legislative_context` - Browse state bills or federal programs
- `explain_event` - Get detailed explanation of a specific event

**User Actions**:
- `file_complaint` - Report a local issue
- `draft_comment` - Generate public comment for a meeting
- `view_my_complaints` - Show user's filed complaints

**Conversational**:
- `respond` - General conversational response (no function call)

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | Function to execute or "respond" for conversation |
| `parameters` | object | Extracted parameters for the function (if action ≠ respond) |
| `message` | string | Conversational response text (if action = respond) |
| `reasoning` | string | LLM's explanation of why it chose this action |
| `conversation_id` | string | Session ID for conversation continuity |
| `usage` | object | Token usage metrics (prompt, completion, total) |

#### Implementation

- **Backend**: `src/civic_chat_router.py` - ChatRouter class with OpenAI function calling
- **Integration**: `src/civic_api_integrated.py` - Route endpoint with conversation storage
- **Model**: `gpt-4o-mini` - Fast, cost-effective function calling
- **Cost**: ~$0.0003 per message turn (~$0.003 per 10-turn conversation)

#### Example Usage

**Search for Events**:
```bash
curl -X POST http://localhost:8001/api/chat/route \
  -H "Authorization: Bearer dev_key_local" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me housing meetings in Berkeley"
  }'

# Response:
{
  "action": "search_events",
  "parameters": {
    "query": "housing",
    "jurisdiction": "Berkeley"
  },
  "reasoning": "Searching for housing meetings in Berkeley",
  "conversation_id": "abc-123"
}
```

**File Complaint**:
```bash
curl -X POST http://localhost:8001/api/chat/route \
  -H "Authorization: Bearer dev_key_local" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Report a pothole on Main Street"
  }'

# Response:
{
  "action": "file_complaint",
  "parameters": {
    "description": "pothole on Main Street",
    "address": "Main Street",
    "category": "infrastructure"
  },
  "conversation_id": "def-456"
}
```

**Conversational Query**:
```bash
curl -X POST http://localhost:8001/api/chat/route \
  -H "Authorization: Bearer dev_key_local" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do city council meetings work?"
  }'

# Response:
{
  "action": "respond",
  "message": "City council meetings are the primary way local governments make decisions...",
  "conversation_id": "ghi-789"
}
```

#### Error Handling

**Missing message**:
```json
{
  "error": "Missing 'message' field",
  "code": "INVALID_REQUEST"
}
```

**OpenAI API error**:
```json
{
  "action": "respond",
  "message": "I'm sorry, I encountered an error processing your request. Please try again.",
  "error": "OpenAI API timeout"
}
```

#### Documentation

See `docs/CHAT_ROUTING_ARCHITECTURE.md` for comprehensive architecture documentation including:
- Function catalog with all available actions
- Frontend integration guide
- Best practices for adding new functions
- Testing strategy

---

## 7. Context Management (Phase 2 - Planned) 🔮

Context management provides explicit tracking of what artifacts are "in context" for chat interactions. This enables context-aware responses, multi-artifact workflows, and prepares for semantic retrieval.

**Implementation Status**:
- ✅ **Phase 1 Complete** (Session 51): Visual context indicators (frontend only)
- ⏳ **Phase 2 Planned** (Sessions 54-56): Context registry backend (Pinia store)
- ⏳ **Phase 3 Planned** (Sessions 57-60): Mode-aware context filtering
- 🔮 **Phase 5 Future**: Semantic retrieval with vector embeddings

**See Also**: `docs/CONTEXT_MANAGEMENT_ARCHITECTURE.md` for complete architecture

### Context Element Schema (Phase 2)

```typescript
interface ContextElement {
  // Identity
  id: string;
  content_version: string;
  content_hash: string;

  // Core metadata
  type: 'event' | 'bill' | 'program' | 'thread' | 'draft' | 'issue';
  artifact_id: string;

  // Temporal tracking
  created_at: Date;
  updated_at: Date;
  accessed_at: Date;

  // Priority & relationships
  priority: 'primary' | 'secondary' | 'reference' | 'background';
  relationships: {
    parent?: string;
    children?: string[];
    related?: string[];
  };

  // Rich metadata (for semantic retrieval)
  metadata: {
    title: string;
    summary: string;
    keywords: string[];
    topics: string[];
    jurisdiction: string;
  };

  // Full data
  data: ContextData;

  // Future: Vector embeddings (additive)
  embeddings?: {
    summary_embedding?: number[];
    model: string;
  };
}
```

### GET /api/context/active ⏳ Phase 2 (Planned)

Get active context elements for current user session.

**Query Parameters**:
- `mode`: Chat mode filter ("navigation" | "research" | "coach" | "orchestrator")
- `limit`: Max elements to return (default: 5)

**Response Format**:
```json
{
  "active_context": [
    {
      "id": "ctx-123",
      "type": "event",
      "priority": "primary",
      "metadata": {
        "title": "Planning Commission - Jan 15",
        "summary": "Discussion of housing development",
        "topics": ["housing"]
      },
      "accessed_at": "2025-11-01T14:30:00Z"
    }
  ],
  "metadata": {
    "mode": "research",
    "total_elements": 3,
    "filters_applied": ["primary", "secondary"]
  }
}
```

### POST /api/context/register ⏳ Phase 2 (Planned)

Register artifact as context element.

**Request Format**:
```json
{
  "type": "event",
  "artifact_id": "event-123",
  "priority": "primary",
  "metadata": {
    "title": "Planning Commission",
    "summary": "Housing discussion"
  },
  "data": { /* full event object */ }
}
```

**Response**:
```json
{
  "context_id": "ctx-abc123",
  "registered": true,
  "deduplicated": false
}
```

### DELETE /api/context/:context_id ⏳ Phase 2 (Planned)

Remove context element from registry.

---

*API Documentation Version 1.3*
*Last Updated: November 1, 2025*
*Server Implementation: `src/civic_api_integrated.py`, `src/personalization_service.py`*

**Version 1.3 Changes (2025-11-01)**:
- Added Context Management section (Phase 2 planned)
- Updated chat routing to be context-aware
- See `CONTEXT_MANAGEMENT_ARCHITECTURE.md` for complete design

**Version 1.2 Changes (2025-10-29)**:
- Added User Profile & Personalization endpoints
- Added PersonalizationService integration
- Updated comment drafting to use centralized profiles
- See `PERSONALIZATION_SERVICE_ARCHITECTURE.md` for migration guide