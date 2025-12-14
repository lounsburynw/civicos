# Comment Drafting Architecture
## Structured Input → AI Generation → Civic Action

**Version**: 1.0
**Date**: 2025-10-28
**Status**: Design Document
**Session**: 39

---

## Executive Summary

The Comment Drafting System transforms passive civic browsing into active participation by making it easier to draft a quality public comment than to complain on social media. The architecture uses **structured user input** as both an AI prompt context and reusable civic data, enabling comment generation, council summaries, aggregation stats, and coordination features.

### Core Innovation

**Dual-Purpose Data Model**: User input serves two functions simultaneously:
1. **Prompt Context** → Generates personalized, contextual AI draft
2. **Structured Data** → Enables stats, summaries, coordination, impact tracking

```
User Input (Structured)
    ↓
    ├──→ AI Prompt Context (richer generation)
    └──→ Summary Card for Council (scannable)
            └──→ Aggregation Stats (sentiment, themes)
                  └──→ Coordination Signals (find allies)
                        └──→ Impact Tracking (did it work?)
```

---

## Part 1: Building Blocks

### 1.1 The Five Components of a Useful Public Comment

#### 1. Position/Stance (Required)
**Purpose**: Clear signal to council members scanning comments
**Options**: Support | Oppose | Neutral/Questions | Request Info

**Why**: Council members need to quickly gauge community sentiment. A clear position enables:
- Fast scanning during meetings
- Aggregation ("15 support, 3 oppose")
- Social coordination ("Find others who support this")

#### 2. Key Concern (Required)
**Purpose**: User's core message in their own words (1-2 sentences)
**Example**: "This will increase traffic on Main Street during school pickup hours"

**Why**: This is the gold. It becomes:
- The thesis statement for the AI-generated comment
- The summary card for council members
- The coordination signal for finding allies
- The impact tracking reference

#### 3. Personal Context (Optional, High Value)
**Purpose**: Establishes credibility and stake in the issue
**Fields**:
- **Stakes**: Homeowner, renter, parent, business owner, senior, student, etc.
- **Proximity**: Years in area, specific district/neighborhood
- **Expertise**: Professional background, community involvement

**Why**: Council members weigh comments differently based on:
- Direct impact (homeowner adjacent to project vs. renter across town)
- Duration of residency (30-year resident vs. recent arrival)
- Domain expertise (architect commenting on building design)

#### 4. AI-Generated Draft (Optional)
**Purpose**: Expand key concern into 2-3 paragraph public comment
**Input**: Position + Key Concern + Personal Context + Agenda Item Context

**Why**: Lowers the barrier from "I have an opinion" to "I have a submittable comment." Users can:
- Use as-is (low effort)
- Edit/customize (medium effort)
- Use as inspiration (high effort)

#### 5. Summary Card (Automatic)
**Purpose**: Compressed version for council scanning
**Generated From**: Structured input (not the AI draft)

**Why**: Council members don't have time to read 50 long comments. Summary cards enable:
- At-a-glance sentiment scanning
- Quick identification of patterns ("8 people mentioned traffic")
- Efficient meeting preparation

---

## Part 2: Data Model

### 2.1 Core Interface

**⚠️ NOTE**: Personal context now comes from **centralized user profiles** (see `PERSONALIZATION_SERVICE_ARCHITECTURE.md`). Comment drafts reference user_id, not embedded context.

```typescript
interface CommentDraft {
  // === Structured Input (Primary Data) ===

  // User (Required)
  userId: string              // User who created this comment

  // Position (Required)
  position: 'support' | 'oppose' | 'neutral' | 'questions'

  // Key Concern (Required)
  keyConcern: string  // 1-2 sentences, user's own words

  // Personal Context (DEPRECATED - use UserProfile)
  // personalContext is now retrieved from user_profiles table via PersonalizationService
  // See PERSONALIZATION_SERVICE_ARCHITECTURE.md for unified context model

  // === AI Generation (Secondary) ===

  // AI-generated draft (optional)
  aiDraftGenerated: boolean
  aiDraft?: string            // Full 2-3 paragraph comment

  // Final comment after user edits
  finalComment?: string       // User may edit AI draft or write from scratch

  // === Metadata ===

  // What is this comment about?
  eventId: string            // e.g., "event-berkeley-planning-2025-11-15"
  agendaItemId?: string      // e.g., "item-7.2-use-permit"
  agendaItemTitle?: string   // e.g., "2850 Telegraph Ave Use Permit"

  // Submission format
  submissionFormat: 'written' | 'oral' | 'letter' | 'email'

  // Tracking
  id: string                 // Unique comment ID
  userId?: string            // If we have user accounts
  createdAt: string          // ISO timestamp
  updatedAt?: string         // ISO timestamp
  submitted?: boolean        // Has user actually submitted to council?
  submittedAt?: string       // ISO timestamp

  // Legislative context (if enriched)
  relatedBills?: string[]    // State bill IDs
  relatedPrograms?: string[] // Federal program IDs
}
```

### 2.2 Summary Card Model

```typescript
interface CommentSummaryCard {
  // Derived from CommentDraft
  commentId: string
  position: 'support' | 'oppose' | 'neutral' | 'questions'
  keyConcern: string         // Same as comment.keyConcern

  // Compressed personal context
  stakes: string[]           // e.g., ["homeowner", "parent"]
  residency: string          // e.g., "15 years, District 3"
  expertise?: string         // e.g., "Urban planner"

  // Metadata
  submissionFormat: 'written' | 'oral' | 'letter' | 'email'
  submittedAt: string

  // Link to full comment
  fullCommentUrl?: string    // If submitted publicly
}
```

### 2.3 Aggregation Stats Model

```typescript
interface CommentStats {
  // For a specific agenda item or event
  eventId: string
  agendaItemId?: string

  // Position breakdown
  positionCounts: {
    support: number      // e.g., 15
    oppose: number       // e.g., 3
    neutral: number      // e.g., 2
    questions: number    // e.g., 1
  }

  // Total comments
  totalComments: number  // e.g., 21

  // Most common concerns (NLP analysis of keyConcerns)
  topConcerns: Array<{
    theme: string        // e.g., "traffic impact"
    count: number        // e.g., 8
    example: string      // Representative keyConcern
  }>

  // Breakdown by stake
  stakeBreakdown: {
    [stake: string]: number  // e.g., { homeowner: 12, renter: 5, parent: 8 }
  }

  // Submission formats
  formatBreakdown: {
    written: number
    oral: number
    letter: number
    email: number
  }

  // Timestamps
  firstComment: string   // ISO timestamp
  lastComment: string    // ISO timestamp

  // Impact tracking (if available)
  councilResponse?: string      // Did council address this?
  outcomeInfluence?: string     // Did comments influence decision?
}
```

---

## Part 3: UX Flow (Progressive Disclosure)

### 3.1 Entry Points

Users can draft comments from:
1. **EventArtifact** → "Draft Comment" button (general event comment)
2. **AgendaItems** → "Draft Comment" button per item (item-specific comment)
3. **IssueArtifact** → "Submit to Council" action (convert complaint → comment)
4. **Chat** → "Help me comment on this" (conversational entry)

### 3.2 Multi-Step Flow

```
Step 1: Quick Position (2 seconds)
  ┌──────────────────────────────────────┐
  │ What's your position on this item?  │
  │                                      │
  │ [●] Support  [ ] Oppose              │
  │ [ ] Neutral  [ ] Have Questions      │
  │                                      │
  │ [Next →]                             │
  └──────────────────────────────────────┘

  ↓ (Position recorded immediately)

Step 2: Key Concern (15 seconds)
  ┌──────────────────────────────────────┐
  │ What's your main concern? (1-2 sent) │
  │ ┌──────────────────────────────────┐ │
  │ │ This will increase traffic on    │ │
  │ │ Main Street during school hours  │ │
  │ └──────────────────────────────────┘ │
  │                                      │
  │ [Skip] [Next →]                      │
  └──────────────────────────────────────┘

  ↓ (Core data captured - minimum viable comment)

Step 3: Personal Context (30 seconds - optional)
  ┌──────────────────────────────────────┐
  │ Add context (optional but helpful):  │
  │                                      │
  │ I am a: [x] Homeowner [x] Parent     │
  │         [ ] Renter    [ ] Senior     │
  │                                      │
  │ Years in area: [15]                  │
  │ Neighborhood: [Rockridge__________]  │
  │                                      │
  │ [Skip] [Generate Full Comment →]     │
  └──────────────────────────────────────┘

  ↓ (Rich context for AI generation)

Step 4: AI Generation (2 seconds)
  ┌──────────────────────────────────────┐
  │ ⏳ Generating your comment...        │
  │                                      │
  │ Analyzing agenda item...             │
  │ Incorporating your concerns...       │
  │ Formatting for submission...         │
  └──────────────────────────────────────┘

  ↓ (OpenAI call with context)

Step 5: Edit & Export (1-5 minutes)
  ┌──────────────────────────────────────┐
  │ Your Draft Comment                   │
  │ ┌──────────────────────────────────┐ │
  │ │ Dear Planning Commission,         │ │
  │ │                                   │ │
  │ │ I am writing to express my concern│ │
  │ │ about the proposed use permit at  │ │
  │ │ 2850 Telegraph Ave. As a homeowner│ │
  │ │ and parent in Rockridge for 15... │ │
  │ │ [editable textarea]               │ │
  │ └──────────────────────────────────┘ │
  │                                      │
  │ [Copy] [Download] [Email to Council] │
  └──────────────────────────────────────┘
```

### 3.3 Progressive Disclosure Principles

**Minimum Viable Engagement**: User can stop at Step 1 and still provide value
- Position alone enables stats ("15 people support this")
- Shows engagement without requiring full comment

**Incremental Value**: Each step adds richness but is optional
- Step 1: Position (2 sec) → Stats
- Step 2: Key Concern (15 sec) → Coordination signals
- Step 3: Personal Context (30 sec) → Richer AI generation
- Step 4: AI Draft (2 sec) → Full comment ready
- Step 5: Edit (1-5 min) → Customized, authentic voice

**No Dead Ends**: Every partial completion has value
- Didn't generate AI draft? Still have structured position
- Didn't edit AI draft? Draft is already pretty good
- Didn't submit? We still learned about user concerns

---

## Part 4: AI Generation

### 4.1 Prompt Construction (Refactored with PersonalizationService)

**⚠️ UPDATED**: Now uses PersonalizationService to retrieve user context instead of embedded personalContext.

```python
def construct_comment_prompt(
    user_id: str,
    position: str,
    key_concern: str,
    event: Event,
    agenda_item: Optional[AgendaItem],
    personalization_service: PersonalizationService
) -> str:
    """
    Build rich prompt using centralized user profile + event context.

    Uses PersonalizationService to retrieve user demographics and civic history.
    """

    # Base prompt structure
    prompt = f"""You are helping a resident draft a public comment for their city council.

AGENDA ITEM:
- Title: {agenda_item.title if agenda_item else event.title}
- Description: {agenda_item.description if agenda_item else event.description}
- Location: {agenda_item.location if agenda_item else "N/A"}
- Project Type: {agenda_item.project_type if agenda_item else "N/A"}

RESIDENT'S POSITION: {position.upper()}

RESIDENT'S KEY CONCERN:
"{key_concern}"

PERSONAL CONTEXT:
"""

    # Get context from PersonalizationService
    context = personalization_service.get_context_for_ai(
        user_id,
        context_type='demographics'
    )

    if context:
        if context.get('stakes'):
            prompt += f"- Stakes: {', '.join(context['stakes'])}\n"
        if context.get('yearsInArea'):
            prompt += f"- Years in area: {context['yearsInArea']}\n"
        if context.get('neighborhood'):
            prompt += f"- Neighborhood: {context['neighborhood']}\n"
        if context.get('expertise'):
            prompt += f"- Expertise: {context['expertise']}\n"

    # Add legislative context if available
    if agenda_item and agenda_item.legislative_context:
        bills = agenda_item.legislative_context.get('state_bills', [])
        programs = agenda_item.legislative_context.get('federal_programs', [])

        if bills:
            prompt += f"\nRELEVANT STATE LEGISLATION:\n"
            for bill in bills[:2]:  # Limit to top 2
                prompt += f"- {bill['bill_id']}: {bill['title']}\n"

        if programs:
            prompt += f"\nRELEVANT FEDERAL PROGRAMS:\n"
            for program in programs[:2]:  # Limit to top 2
                prompt += f"- {program['name']}: {program['description'][:100]}...\n"

    # Generation instructions
    prompt += f"""

TASK:
Write a 2-3 paragraph public comment that:
1. Clearly states the resident's {draft.position} position
2. Expands on their key concern: "{draft.keyConcern}"
3. Uses their personal context to establish credibility
4. References relevant legislation/programs if helpful
5. Is professional but authentic (not overly formal)
6. Is suitable for oral delivery (if needed) or written submission

Format: Plain text, no salutation/signature (user will add).
Tone: Professional but personal, passionate but respectful.
Length: 150-250 words (2-3 paragraphs).
"""

    return prompt
```

### 4.2 Cost Optimization

**Model**: `gpt-4o-mini`
**Average Tokens**: ~1500 input, ~300 output
**Cost per Draft**: ~$0.002
**Monthly Cost** (1000 drafts): ~$2.00

**Optimization Strategies**:
1. Cache event/agenda context per session (avoid re-fetching)
2. Limit legislative context to top 2 bills + 2 programs
3. Use truncated descriptions (first 100 chars)
4. Consider batch generation for multiple agenda items

---

## Part 5: Summary Cards for Council

### 5.1 Visual Design

```
┌───────────────────────────────────────┐
│ 🟢 SUPPORT                            │
│                                       │
│ "This will increase traffic on Main   │
│ Street during school pickup hours"    │
│                                       │
│ 👤 Homeowner, Parent                  │
│ 📍 15 years, District 3, Rockridge    │
│                                       │
│ 📄 [Read Full Comment →]              │
└───────────────────────────────────────┘

┌───────────────────────────────────────┐
│ 🔴 OPPOSE                             │
│                                       │
│ "We need more affordable housing in   │
│ this neighborhood immediately"        │
│                                       │
│ 👤 Renter                             │
│ 📍 3 years, District 3                │
│ 🎓 Urban Planning Professional        │
│                                       │
│ 📄 [Read Full Comment →]              │
└───────────────────────────────────────┘
```

### 5.2 Generation Logic

```typescript
function generateSummaryCard(draft: CommentDraft): CommentSummaryCard {
  // Compress personal context
  const stakesStr = draft.personalContext?.stakes?.join(', ') || ''

  const residencyParts = []
  if (draft.personalContext?.yearsInArea) {
    residencyParts.push(`${draft.personalContext.yearsInArea} years`)
  }
  if (draft.personalContext?.district) {
    residencyParts.push(draft.personalContext.district)
  }
  if (draft.personalContext?.neighborhood) {
    residencyParts.push(draft.personalContext.neighborhood)
  }
  const residencyStr = residencyParts.join(', ')

  return {
    commentId: draft.id,
    position: draft.position,
    keyConcern: draft.keyConcern,
    stakes: draft.personalContext?.stakes || [],
    residency: residencyStr,
    expertise: draft.personalContext?.expertise,
    submissionFormat: draft.submissionFormat,
    submittedAt: draft.submittedAt || draft.createdAt,
    fullCommentUrl: draft.finalComment ? `/comments/${draft.id}` : undefined
  }
}
```

### 5.3 Council Dashboard View

Aggregated view for council members before meetings:

```
Item 7.2: 2850 Telegraph Ave Use Permit
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Community Response:
  🟢 15 Support
  🔴 3 Oppose
  ⚪ 2 Neutral/Questions

🔑 Top Concerns:
  1. Traffic impact (8 mentions)
  2. Parking availability (5 mentions)
  3. Building height (3 mentions)

👥 Stakeholder Breakdown:
  12 homeowners
  5 renters
  8 parents
  2 business owners

📄 Comments:
  [15 summary cards sorted by position]
```

---

## Part 6: Aggregation & Stats

### 6.1 Real-Time Stats Display

Show stats on event/agenda item cards:

```vue
<div class="comment-stats">
  <span class="stat support">
    <ThumbsUp :size="16" />
    15 Support
  </span>
  <span class="stat oppose">
    <ThumbsDown :size="16" />
    3 Oppose
  </span>
  <span class="stat total">
    <MessageSquare :size="16" />
    21 Total Comments
  </span>
</div>
```

### 6.2 Backend Endpoint

```python
@app.route('/api/events/<event_id>/comment-stats', methods=['GET'])
def get_comment_stats(event_id):
    """
    Get aggregated stats for all comments on this event
    """
    comments = CommentStorage.get_comments_by_event(event_id)

    # Count positions
    position_counts = {
        'support': 0,
        'oppose': 0,
        'neutral': 0,
        'questions': 0
    }

    for comment in comments:
        position_counts[comment['position']] += 1

    # Analyze key concerns for themes (simple keyword matching)
    concern_themes = analyze_concerns([c['keyConcern'] for c in comments])

    # Breakdown by stakes
    stake_counts = {}
    for comment in comments:
        for stake in comment.get('personalContext', {}).get('stakes', []):
            stake_counts[stake] = stake_counts.get(stake, 0) + 1

    return jsonify({
        'event_id': event_id,
        'position_counts': position_counts,
        'total_comments': len(comments),
        'top_concerns': concern_themes[:5],  # Top 5
        'stake_breakdown': stake_counts,
        'first_comment': comments[0]['createdAt'] if comments else None,
        'last_comment': comments[-1]['createdAt'] if comments else None
    })
```

---

## Part 7: Coordination Features

### 7.1 Find Allies

When user drafts a comment, show others with similar positions:

```
┌─────────────────────────────────────┐
│ 💬 12 others share your position    │
│                                     │
│ Top concerns among supporters:      │
│  • Traffic impact (8 people)        │
│  • Parking (5 people)               │
│  • Building height (3 people)       │
│                                     │
│ [See Discussion Thread →]           │
└─────────────────────────────────────┘
```

### 7.2 Avoid Duplication

Suggest user focus on unique angle:

```
✅ Your concern about traffic is shared by 8 others.

💡 Consider also mentioning:
  • Impact on school pickup (only 1 person mentioned)
  • Pedestrian safety (not yet mentioned)
  • Alternative parking solutions (not yet mentioned)
```

### 7.3 Collective Comments

Enable group submissions:

```
┌─────────────────────────────────────┐
│ Sign onto collective comment?       │
│                                     │
│ "We, the undersigned residents of   │
│ Rockridge, oppose this permit due   │
│ to traffic and parking concerns..." │
│                                     │
│ 12 signatures so far                │
│                                     │
│ [Add My Signature] [Write My Own]   │
└─────────────────────────────────────┘
```

---

## Part 8: Impact Tracking

### 8.1 Post-Meeting Updates

After meetings, track whether comments influenced decisions:

```typescript
interface CommentImpact {
  commentId: string
  eventId: string
  agendaItemId: string

  // Meeting outcome
  meetingDate: string
  decision: 'approved' | 'denied' | 'continued' | 'modified' | 'withdrawn'

  // Council response
  councilAcknowledged: boolean    // Did council mention this concern?
  councilResponse?: string        // What did they say?

  // Influence assessment
  influenceLevel: 'high' | 'medium' | 'low' | 'none'
  influenceNote?: string          // Why we think this

  // User engagement
  userNotified: boolean           // Did we tell the user?
  userSatisfaction?: 'satisfied' | 'neutral' | 'dissatisfied'
}
```

### 8.2 User Notification

```
┌─────────────────────────────────────┐
│ 📣 Update: Your comment was heard!  │
│                                     │
│ The Planning Commission approved    │
│ the use permit with modifications:  │
│                                     │
│ ✅ Added traffic study requirement  │
│ ✅ Reduced building height by 10ft  │
│ ⚠️  No additional parking added     │
│                                     │
│ Commissioner Lee specifically       │
│ mentioned concerns about traffic    │
│ from 8 residents like you.          │
│                                     │
│ [View Meeting Video →]              │
│ [Was this helpful? 👍 👎]           │
└─────────────────────────────────────┘
```

### 8.3 Long-Term Tracking

Build user's "civic impact portfolio":

```
Your Civic Impact (2024)
━━━━━━━━━━━━━━━━━━━━━━━

📝 15 comments submitted
🎯 12 on issues you care about (housing, transportation)
✅ 8 led to council discussion
🏆 3 influenced final decisions

Top Impact:
  "Your comments on the Telegraph Ave project
  contributed to the 10ft height reduction and
  additional traffic study requirement."

[See Full History →]
```

---

## Part 9: API Endpoints (Required)

### 9.1 Comment Storage

**POST /api/comments**
```json
{
  "eventId": "event-berkeley-planning-2025-11-15",
  "agendaItemId": "item-7.2",
  "position": "oppose",
  "keyConcern": "This will increase traffic on Main Street during school hours",
  "personalContext": {
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "district": "District 3",
    "neighborhood": "Rockridge"
  },
  "aiDraftGenerated": true,
  "finalComment": "Dear Planning Commission,\n\nI am writing to express...",
  "submissionFormat": "written"
}
```

**Response**: Returns full comment object with ID

**Error Responses**:
- `400 Bad Request`: Missing required fields (position, keyConcern), invalid enum values
- `401 Unauthorized`: Invalid or missing Bearer token
- `429 Too Many Requests`: Rate limit exceeded (5 comments/user/day)
- `500 Internal Server Error`: Database error

---

**PATCH /api/comments/:comment_id** 🆕

Update an existing comment draft (before submission).

```json
{
  "finalComment": "Updated comment text after user edits...",
  "submitted": true,
  "submittedAt": "2025-10-28T15:30:00Z"
}
```

**Response**: Returns updated comment object

**Error Responses**:
- `400 Bad Request`: Invalid field values
- `401 Unauthorized`: Invalid Bearer token or not comment owner
- `404 Not Found`: Comment not found
- `409 Conflict`: Cannot edit already-submitted comment
- `500 Internal Server Error`: Database error

**Use Cases**:
- User edits AI-generated draft → PATCH with `finalComment`
- User submits comment → PATCH with `submitted: true, submittedAt`
- User changes position before submitting → PATCH with `position`

---

**GET /api/comments/:comment_id**

Returns single comment with all fields.

**Error Responses**:
- `401 Unauthorized`: Invalid Bearer token
- `404 Not Found`: Comment not found

---

**GET /api/events/:event_id/comments**

Query params:
- `position` (optional): Filter by support/oppose/neutral/questions
- `agendaItemId` (optional): Filter by specific agenda item
- `format` (optional): summary | full (default: full)

Returns array of comments.

**Error Responses**:
- `401 Unauthorized`: Invalid Bearer token
- `404 Not Found`: Event not found
- `500 Internal Server Error`: Database error

---

### 9.2 Stats & Aggregation

**GET /api/events/:event_id/comment-stats**

Returns:
```json
{
  "event_id": "event-berkeley-planning-2025-11-15",
  "position_counts": {
    "support": 15,
    "oppose": 3,
    "neutral": 2,
    "questions": 1
  },
  "total_comments": 21,
  "top_concerns": [
    {
      "theme": "traffic impact",
      "count": 8,
      "example": "This will increase traffic on Main Street..."
    }
  ],
  "stake_breakdown": {
    "homeowner": 12,
    "renter": 5,
    "parent": 8
  }
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid Bearer token
- `404 Not Found`: Event not found
- `500 Internal Server Error`: Database error

**Caching**: Results cached for 5 minutes (stats don't need real-time accuracy)

---

**GET /api/events/:event_id/summary-cards**

Returns array of CommentSummaryCard objects for council scanning.

**Error Responses**:
- `401 Unauthorized`: Invalid Bearer token
- `404 Not Found`: Event not found
- `500 Internal Server Error`: Database error

---

### 9.3 AI Generation (REFACTORED 2025-10-29)

**POST /api/events/:event_id/draft-comment** ✅

**⚠️ REFACTORED**: Now uses centralized user profiles via PersonalizationService.

**New Approach (Recommended):**
```json
{
  "position": "oppose",
  "keyConcern": "This will increase traffic during school hours"
}
```

Context automatically loaded from user's profile via Bearer token → user_id → PersonalizationService.

**Legacy Approach (Backward Compatible):**
```json
{
  "agendaItemId": "item-7.2",
  "position": "oppose",
  "keyConcern": "This will increase traffic during school hours",
  "personalContext": {
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 15,
    "neighborhood": "Rockridge"
  }
}
```

If `personalContext` is provided, it overrides profile data (for one-time anonymous use).

**Returns:**
```json
{
  "draft": "Dear Planning Commission,\n\nI am writing to express my concern...",
  "metadata": {
    "model": "gpt-4o-mini",
    "tokens_used": 1842,
    "cost": 0.00184,
    "context_source": "user_profile"
  }
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid Bearer token or user_id not found
- `404 Not Found`: Event or agenda item not found
- `500 Internal Server Error`: OpenAI API error or database error
- `503 Service Unavailable`: OpenAI API rate limit exceeded

**Migration Note**: See `PERSONALIZATION_SERVICE_ARCHITECTURE.md` for complete refactoring guide.

---

## Part 9.4: Validation Rules & Rate Limiting

### Field Constraints

**Required Fields**:
- `position`: Must be one of: `support`, `oppose`, `neutral`, `questions`
- `key_concern`: 20-300 characters (1-2 sentences)
- `event_id`: Must reference a valid event

**Optional Fields**:
- `agenda_item_id`: Must reference valid agenda item if provided
- `personal_context.stakes`: Array max length 10
- `personal_context.yearsInArea`: 0-100
- `personal_context.neighborhood`: Max 100 characters
- `personal_context.expertise`: Max 200 characters

**Text Sanitization**:
```python
def sanitize_text(text: str) -> str:
    """Remove HTML tags and script content"""
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove script content
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    return text.strip()
```

### Rate Limiting

**Per-User Limits**:
- POST /api/comments: 5 requests per day per `user_id`
- POST /api/events/:id/draft-comment: 20 requests per hour per `user_id`
- GET endpoints: 100 requests per hour per IP

**Implementation**:
```python
from functools import wraps
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        window_start = now - window_seconds

        # Clean old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if req_time > window_start
        ]

        if len(self.requests[key]) >= max_requests:
            return False

        self.requests[key].append(now)
        return True

# Usage
rate_limiter = RateLimiter()

def rate_limit(max_requests: int, window_seconds: int):
    def decorator(f):
        @wraps(f)
        def wrapped(self, *args, **kwargs):
            user_id = get_user_id_from_request()  # Extract from token
            key = f"{f.__name__}:{user_id}"

            if not rate_limiter.is_allowed(key, max_requests, window_seconds):
                return {'error': 'Rate limit exceeded'}, 429

            return f(self, *args, **kwargs)
        return wrapped
    return decorator
```

**Response Headers**:
```
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 3
X-RateLimit-Reset: 1730134800
```

---

## Part 10: Database Schema

### 10.1 Comments Table

```sql
CREATE TABLE comments (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    event_id TEXT NOT NULL,
    agenda_item_id TEXT,

    -- Structured input
    position TEXT NOT NULL CHECK(position IN ('support', 'oppose', 'neutral', 'questions')),
    key_concern TEXT NOT NULL,

    -- Personal context (JSON)
    personal_context TEXT,  -- JSON: {stakes, yearsInArea, district, neighborhood, expertise}

    -- AI generation
    ai_draft_generated BOOLEAN DEFAULT FALSE,
    ai_draft TEXT,
    final_comment TEXT,

    -- Metadata
    submission_format TEXT CHECK(submission_format IN ('written', 'oral', 'letter', 'email')),
    submitted BOOLEAN DEFAULT FALSE,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,

    -- Legislative context
    related_bills TEXT,     -- JSON array of bill IDs
    related_programs TEXT,  -- JSON array of program IDs

    -- Note: No FK constraint on event_id - events stored as JSON files, not in database
    -- No FK constraint on user_id - user system not yet implemented
);

CREATE INDEX idx_comments_event ON comments(event_id);
CREATE INDEX idx_comments_agenda_item ON comments(agenda_item_id);
CREATE INDEX idx_comments_position ON comments(position);
CREATE INDEX idx_comments_submitted ON comments(submitted);
CREATE INDEX idx_comments_user ON comments(user_id);
```

**Field Naming Convention**: Database uses `snake_case` (e.g., `event_id`, `agenda_item_id`) to match existing SQLite tables and Python backend conventions. Frontend TypeScript may use `camelCase` internally, transforming to `snake_case` when calling APIs.

### 10.2 Comment Impact Table

```sql
CREATE TABLE comment_impact (
    id TEXT PRIMARY KEY,
    comment_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    agenda_item_id TEXT NOT NULL,

    -- Meeting outcome
    meeting_date TEXT,
    decision TEXT CHECK(decision IN ('approved', 'denied', 'continued', 'modified', 'withdrawn')),

    -- Council response
    council_acknowledged BOOLEAN DEFAULT FALSE,
    council_response TEXT,

    -- Influence assessment
    influence_level TEXT CHECK(influence_level IN ('high', 'medium', 'low', 'none')),
    influence_note TEXT,

    -- User engagement
    user_notified BOOLEAN DEFAULT FALSE,
    user_satisfaction TEXT CHECK(user_satisfaction IN ('satisfied', 'neutral', 'dissatisfied')),

    created_at TEXT NOT NULL,

    FOREIGN KEY (comment_id) REFERENCES comments(id),
    FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE INDEX idx_impact_comment ON comment_impact(comment_id);
CREATE INDEX idx_impact_event ON comment_impact(event_id);
```

---

## Part 11: Frontend Components

### 11.1 Component Hierarchy

```
CommentDraftArtifact.vue (Enhanced)
├── StructuredInputForm.vue (NEW)
│   ├── PositionSelector.vue
│   ├── KeyConcernInput.vue
│   └── PersonalContextForm.vue
│       ├── StakesCheckboxes.vue
│       ├── ResidencyInput.vue
│       └── ExpertiseInput.vue
├── DraftEditor.vue (Existing)
├── SummaryCard.vue (NEW)
├── CommentStats.vue (NEW)
└── ExportActions.vue (Existing)
```

### 11.2 Key Components

**PositionSelector.vue**
- Radio buttons or large pill buttons
- Visual: Support (green), Oppose (red), Neutral (gray), Questions (blue)
- Records position immediately (fire-and-forget analytics)

**KeyConcernInput.vue**
- Textarea with character counter (100-200 chars ideal)
- Placeholder: "What's your main concern? (1-2 sentences)"
- Real-time validation: Warn if too short (<20 chars) or too long (>300 chars)

**PersonalContextForm.vue**
- Optional, progressive disclosure ("Add context to strengthen your comment")
- Stakes: Checkbox group with common options + "Other"
- Years in area: Number input (0-80)
- Neighborhood: Text input with autocomplete (if available)
- Expertise: Text input (optional)

**SummaryCard.vue**
- Compressed display of structured input
- Show on hover/click from stats
- Used in council dashboard view

**CommentStats.vue**
- Real-time aggregation display
- Position breakdown with percentages
- Top concerns with counts
- "12 others share your position"

---

## Part 12: Implementation Roadmap

### Phase 1: Structured Input (Session 39) - 2-3 hours
- [ ] Create database schema (comments table)
- [ ] Backend: POST /api/comments endpoint
- [ ] Backend: GET /api/comments/:id endpoint
- [ ] Frontend: PositionSelector component
- [ ] Frontend: KeyConcernInput component
- [ ] Frontend: PersonalContextForm component
- [ ] Frontend: StructuredInputForm wrapper
- [ ] Integration: Add structured input before AI generation in CommentDraftArtifact
- [ ] Testing: Full flow from position → AI draft

### Phase 2: Stats & Aggregation (Session 40) - 2-3 hours
- [ ] Backend: GET /api/events/:event_id/comment-stats
- [ ] Backend: Concern theme analysis (keyword matching)
- [ ] Frontend: CommentStats component
- [ ] Integration: Show stats on EventArtifact
- [ ] Integration: Show stats on AgendaItems
- [ ] Testing: Stats update in real-time as comments added

### Phase 3: Summary Cards (Session 41) - 2 hours
- [ ] Backend: GET /api/events/:event_id/summary-cards
- [ ] Frontend: SummaryCard component
- [ ] Frontend: SummaryCardList component
- [ ] Integration: Council dashboard view (optional)
- [ ] Testing: Summary card generation from structured input

### Phase 4: Coordination (Session 42) - 2-3 hours
- [ ] Frontend: "Find Allies" panel in CommentDraftArtifact
- [ ] Frontend: "Others Share Your Position" indicator
- [ ] Frontend: Link to discussion thread (if exists)
- [ ] Integration: Suggest unique angles based on existing comments
- [ ] Testing: Coordination signals accurate

### Phase 5: Impact Tracking (Future) - 3-4 hours
- [ ] Database: comment_impact table
- [ ] Backend: POST /api/comment-impact (admin only)
- [ ] Backend: GET /api/comments/:id/impact
- [ ] Frontend: Impact notification component
- [ ] Frontend: User's civic impact portfolio
- [ ] Integration: Post-meeting update workflow
- [ ] Testing: Impact tracking accuracy

---

## Part 13: Cost Analysis

### 13.1 AI Generation Costs

**Model**: gpt-4o-mini
**Per Draft**: ~$0.002
**Scale**:
- 100 drafts/day: $0.20/day = $6/month
- 500 drafts/day: $1/day = $30/month
- 1000 drafts/day: $2/day = $60/month

**Optimization**: Cache event/agenda context to reduce input tokens

### 13.2 Storage Costs

**Per Comment**: ~2KB (structured input + AI draft)
**Scale**:
- 10,000 comments: 20MB
- 100,000 comments: 200MB
- 1,000,000 comments: 2GB

**Cost**: Negligible (<$1/month even at scale)

### 13.3 Compute Costs

**Stats Aggregation**: O(n) scan per event, cacheable for 5-10 minutes
**Theme Analysis**: Simple keyword matching, <10ms per event
**Summary Cards**: Generated on-demand, negligible cost

---

## Part 14: Success Metrics

### 14.1 Conversion Funnel

```
Event View (baseline)
  ↓ 10% click "Draft Comment"
Position Selection
  ↓ 80% complete (fire-and-forget)
Key Concern Input
  ↓ 60% complete
Personal Context
  ↓ 40% complete
AI Generation
  ↓ 90% success
Draft Edit
  ↓ 70% edit
Export/Submit
  ↓ 50% actual submission
```

**Target**: 3-5% conversion from event view → comment submission

### 14.2 Quality Metrics

- Average comment length: 150-250 words
- Edit rate: 60-80% (shows users customize, not copy-paste)
- Personal context completion: 40%+ (shows engagement)
- Reuse rate: <10% (shows authentic voice, not template spam)

### 14.3 Impact Metrics

- Comments acknowledged by council: 20%+
- Decisions influenced: 5-10%
- User return rate after first comment: 30%+
- User satisfaction after decision: 60%+

---

## Part 15: Privacy & Ethics

### 15.1 Data Privacy

**Principles**:
1. Comments are civic data (assume public)
2. Personal context is user-controlled (opt-in)
3. User identity is pseudonymous (unless submitted publicly)
4. No selling/sharing of structured data

**User Controls**:
- Option to submit anonymously (personal context hidden)
- Option to delete draft comments
- Option to hide position from public stats (private opposition)

### 15.2 AI Ethics

**Principles**:
1. AI assists, doesn't replace user voice
2. User always edits before submission
3. No "astroturfing" - each comment requires unique input
4. Transparency: Label AI-assisted comments (optional)

**Guardrails**:
- Require unique key concern (no copy-paste from other comments)
- Rate limiting: 5 comments per user per day
- Flag suspicious patterns (same concern → multiple users)

### 15.3 Council Relations

**Transparency**:
- Make structured input format available to councils
- Offer summary cards as opt-in feature (not default)
- Respect councils that prefer unfiltered comments

**Quality Over Quantity**:
- Encourage thoughtful comments, not spam
- Show stats accurately (don't inflate numbers)
- Flag coordinated campaigns (not organic)

---

## Part 16: Migration to Personalization Service (2025-10-29)

### 16.1 Architectural Shift

**Before (Session 37-38):**
- Personal context embedded in each comment (`personalContext` field)
- User fills out stakes/expertise for every comment
- No reusability across features

**After (2025-10-29):**
- Personal context stored in centralized `user_profiles` table
- User fills out profile once, reused for all comments
- PersonalizationService provides unified context API

### 16.2 Migration Path

**Step 1: Deploy Personalization Service**
See `PERSONALIZATION_SERVICE_ARCHITECTURE.md` for complete implementation guide.

**Step 2: Update Comment Drafting Endpoint**
```python
# civic_api_integrated.py
@app.route('/api/events/<event_id>/draft-comment', methods=['POST'])
def handle_draft_comment(event_id):
    user_id = get_user_id_from_token()  # Extract from Bearer token
    data = request.json

    # Backward compatibility
    if 'personalContext' in data:
        context = data['personalContext']
    else:
        context = self.personalization.get_context_for_ai(user_id, 'demographics')

    # Generate + track action
    draft = generate_comment(event_id, data['position'], data['keyConcern'], context)
    self.personalization.track_action(user_id, 'comment_drafted', 'event', event_id)

    return jsonify({'draft': draft})
```

**Step 3: Migrate Existing Comment Data (Optional)**
```sql
-- Migrate personalContext from comments to user_profiles
INSERT OR IGNORE INTO user_profiles (user_id, jurisdiction_id, stakes, years_in_area, expertise)
SELECT DISTINCT
    user_id,
    'city-berkeley' as jurisdiction_id,  -- Default, update based on event
    json_extract(personal_context, '$.stakes'),
    json_extract(personal_context, '$.yearsInArea'),
    json_extract(personal_context, '$.expertise')
FROM comments
WHERE user_id IS NOT NULL AND personal_context IS NOT NULL;
```

**Step 4: Update Frontend**
- Remove embedded `PersonalContextForm` from `CommentDraftArtifact`
- Add profile link: "Update your profile for better AI comments"
- Show profile completeness if <80%

### 16.3 Benefits of Migration

**User Experience:**
- Fill out profile once, use everywhere
- Faster comment drafting (no repeated form filling)
- Better AI generation (richer context from civic history)

**Technical:**
- Single source of truth for user context
- Reusable across all personalized features (email drafting, recommendations, etc.)
- Behavioral inference unlocks smart recommendations

**Business:**
- Profile completion drives engagement (gamification)
- Civic history enables impact tracking
- Personalization increases conversion rates

---

## Part 17: Drafts Tab Integration (Session 49) 🆕

### 17.1 Strategic Shift: From Artifacts to Tabs

**Problem Identified (Post-Session 48)**:
- CommentDraftArtifact opens as **separate tab** in workspace
- Each draft selection → **new tab** → tab proliferation
- Users **lose event context** while drafting
- Navigation overhead: event → draft → event → edit draft

**Solution (Session 49)**:
- Move drafts from **artifacts** → **EventArtifact tabs**
- EventArtifact tabs: Details | Discussion | **Drafts** (new)
- All drafts stay **within event context**
- No more tab clutter

### 17.2 New Component Architecture

**DraftWorkspace.vue** (NEW - Session 49):
```vue
<script setup lang="ts">
// Extracted from CommentDraftArtifact.vue
// Reusable inline draft editor for tabs

const props = defineProps<{
  event: CivicEvent;
  selectedAgendaItems?: ActionableItem[] | null;
  allDrafts: DraftSummary[];
}>();

const emit = defineEmits<{
  'draft-updated': [];
}>();
</script>

<template>
  <div class="draft-workspace">
    <!-- DraftPicker (inline dropdown) -->
    <DraftPicker :drafts="allDrafts" ... />

    <!-- Structured Summary Card -->
    <div class="structured-summary-card">...</div>

    <!-- Draft Editor (per-item sections or full draft) -->
    <DraftEditor v-model="draftContent" ... />

    <!-- Personal Context (collapsible) -->
    <PersonalContextForm v-model="personalContext" />

    <!-- Export Actions -->
    <div class="export-actions">
      <button @click="copyToClipboard">Copy</button>
      <button @click="downloadAsTxt">Download</button>
      <button @click="emailToClerk">Email to Clerk</button>
    </div>
  </div>
</template>
```

**EventArtifact.vue** (UPDATED - Session 49):
```vue
<script setup lang="ts">
// Add Drafts tab
const activeTab = ref<'details' | 'discussion' | 'drafts'>('details');

// Load drafts for badge count
const allDrafts = ref<DraftSummary[]>([]);
const draftCount = computed(() => allDrafts.value.length);

async function loadDrafts() {
  const response = await api.getAllDrafts(props.event.id, userId);
  allDrafts.value = response.drafts;
}

// Update "Draft Comment" button to switch tabs
function draftComment() {
  activeTab.value = 'drafts'; // Instead of opening artifact
}
</script>

<template>
  <div class="event-artifact">
    <!-- Tab Navigation -->
    <div class="tab-navigation">
      <button @click="activeTab = 'details'">Details</button>
      <button @click="activeTab = 'discussion'">Discussion</button>
      <button @click="activeTab = 'drafts'">
        Drafts
        <span v-if="draftCount > 0" class="tab-badge">{{ draftCount }}</span>
      </button>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
      <div v-if="activeTab === 'details'">...</div>
      <div v-if="activeTab === 'discussion'">...</div>
      <div v-if="activeTab === 'drafts'">
        <DraftWorkspace
          :event="event"
          :selected-agenda-items="selectedAgendaItems"
          :all-drafts="allDrafts"
          @draft-updated="loadDrafts"
        />
      </div>
    </div>
  </div>
</template>
```

### 17.3 Benefits of Tab-Based UX

**Context Preservation**:
- Selected agenda items persist across tabs
- Can view Details tab to reference agenda while drafting
- Legislative context accessible without switching artifacts
- Event metadata always visible in header

**Reduced Cognitive Load**:
- No more "Where did I put that draft?" confusion
- All event-related actions in one place
- Consistent navigation pattern (matches Discussion tab)

**Foundation for Chat Integration**:
- Session 50 will add chat research integration
- Chat can detect "user is in Drafts tab"
- Context-aware prompts: "Would you like me to research..."
- "Use this in draft" button inserts into visible draft

### 17.4 Deprecation Strategy

**CommentDraftArtifact.vue** (Sessions 37-48):
- Keep for backward compatibility
- Mark as deprecated in code comments
- workspace.ts warns if opened: "Use Drafts tab instead"
- Future: Remove after Session 52+ (give users time to adapt)

**Migration Path**:
```typescript
// workspace.ts
openArtifact(artifact: Artifact) {
  if (artifact.type === 'comment-draft') {
    console.warn('[workspace] comment-draft artifacts are deprecated. Use Drafts tab in EventArtifact instead.');

    // Redirect: open event + switch to drafts tab
    const eventId = artifact.data.event.id;
    this.openArtifact({ id: eventId, type: 'event', data: ... });
    // EventArtifact will detect and switch to drafts tab
    return;
  }

  // ... existing logic ...
}
```

### 17.5 Future Enhancements (Session 50+)

**Chat Research Integration** (Session 50):
- Chat detects activeTab === 'drafts'
- Offers context-aware research prompts
- "Use this in draft" button inserts with citations
- Draft shows research references: "📚 Research used: [CDBG data]"

**Per-Item Independent Drafting** (Session 53+):
- Each agenda item can have standalone draft
- Drafts are composable (merge multiple items)
- Hierarchical DraftPicker:
  ```
  Your Drafts (5)
  ├── General Meeting Comment
  ├── Item 3.1: Use Permit (2 drafts)
  │   ├── Draft A (support)
  │   └── Draft B (oppose)
  └── Item 3.2: Budget (1 draft)
  ```

**Email Pre-Population** (Session 51):
- Mailto links with pre-filled subject, body, recipient
- Submission tracking with confirmation dialog
- Submission history badge: "✓ Submitted 2h ago"

---

## Part 18: Context Management Integration (2025-11-01) 🆕

### 18.1 Context-Aware Draft Generation

**Problem**: Comment drafting currently operates in isolation - it doesn't leverage related artifacts the user has open (bills, other events, discussion threads).

**Solution**: Integrate with Context Management Architecture (see `CONTEXT_MANAGEMENT_ARCHITECTURE.md`).

#### Context Registry Schema for Drafts

```typescript
interface DraftContext extends BaseContextElement {
  type: 'draft';
  data: {
    draft: DraftData;
    position: string;
    keyConcern: string;
    isModified: boolean;
    wordCount: number;
    referencedBills?: string[];   // Bills user has open
    referencedEvents?: string[];  // Related events user is viewing
    researchInjected?: boolean;   // Has chat research been added
  };
}
```

#### Multi-Artifact Draft Generation

When user generates a draft with multiple artifacts open, the AI can synthesize across them:

```typescript
// User has open:
// - Event: Planning Commission - Jan 15 (activeTab: 'drafts')
// - Bill: AB 1147 - Affordable Housing
// - Thread: Discussion with 12 neighbors about traffic

async function generateDraftWithContext(
  eventId: string,
  position: string,
  keyConcern: string,
  contextRegistry: ContextElement[]
) {
  // Get related context elements
  const eventContext = contextRegistry.find(el => el.type === 'event' && el.data.event.id === eventId);
  const billContexts = contextRegistry.filter(el => el.type === 'bill');
  const threadContexts = contextRegistry.filter(el => el.type === 'thread');

  // Build enriched prompt
  const prompt = `
You are helping a resident draft a public comment for a city council meeting.

EVENT CONTEXT:
${eventContext.metadata.summary}

RELATED BILLS (user is researching):
${billContexts.map(b => `- ${b.metadata.bill.bill}: ${b.metadata.bill.title}`).join('\n')}

COMMUNITY DISCUSSION (user is participating):
${threadContexts.map(t => `- ${t.metadata.thread.participant_count} neighbors discussing: ${t.metadata.title}`).join('\n')}

USER'S POSITION: ${position}
KEY CONCERN: ${keyConcern}

TASK:
Draft a comment that:
1. References the bills the user has been researching
2. Mentions community support (${threadContexts[0]?.metadata.thread.participant_count} neighbors)
3. Stays focused on the user's key concern
`;

  // Generate with OpenAI
  const draft = await generateComment(prompt);
  return draft;
}
```

**Benefits**:
- **Richer drafts** - Synthesizes across multiple sources
- **Automatic citations** - References bills user has open
- **Community backing** - Mentions discussion participants
- **Context preservation** - User doesn't need to manually copy/paste

### 18.2 Context-Aware Chat Prompts

When user is in Drafts tab, chat can offer context-aware suggestions:

```typescript
// ChatPanel detects activeContext
if (activeContext.type === 'event' && activeContext.activeTab === 'drafts') {
  // Check for related context elements
  const billsOpen = contextRegistry.filter(el => el.type === 'bill').length;
  const threadsOpen = contextRegistry.filter(el => el.type === 'thread').length;

  // Proactive suggestion
  if (billsOpen > 0) {
    addChatSuggestion("Include AB 1147 in your draft? I can help you cite it correctly.");
  }

  if (threadsOpen > 0) {
    addChatSuggestion("Want to mention the 12 neighbors discussing this issue?");
  }
}
```

### 18.3 Migration Path

**Phase 1** (Session 51): Context indicators UI only
- Visual display of open artifacts
- No backend changes to draft generation

**Phase 2** (Session 54-56): Context registry backend
- Pinia store with ContextElement schema
- Artifacts register on mount/unmount

**Phase 3** (Session 57-60): Context-aware draft generation
- Update `POST /api/events/:event_id/draft-comment` to accept context array
- Generate drafts that synthesize across multiple sources
- Add citation tracking for referenced bills/events

**Phase 4** (Session 61+): Advanced features
- Auto-link related content (user opens event → suggest related bills)
- Context diff view (show what changed between draft generations)
- Cross-reference validation (ensure cited bills are actually relevant)

---

## Conclusion

The Comment Drafting Architecture transforms civic participation from high-effort to low-effort while maintaining authenticity and quality. By capturing **structured input** first, we create dual-purpose data that serves both AI generation and civic coordination. The progressive disclosure model meets users where they are - from quick position selection to full comment submission - while creating valuable data at every step.

**Context Management Integration** (2025-11-01): By integrating with the Context Management Architecture, drafts can now synthesize across multiple open artifacts (events, bills, threads), enabling richer, more comprehensive public comments that cite research and community backing.

**UPDATED (2025-11-01)**: Sessions 37-49 complete with unified tab-based drafting in EventArtifact. All draft features preserved (multi-draft, memoization, tags, deletion) while eliminating tab proliferation.

**Implementation Timeline**:
1. ✅ Sessions 37-40: Basic comment drafting with legislative validation
2. ✅ Sessions 41-44: Privacy tiers, metadata extraction, archetype personalization
3. ✅ Sessions 45-46: Draft persistence, autosave, multi-draft system
4. ✅ Session 47: Per-item memoized generation (67% cost savings)
5. ✅ Session 48: Draft management (tags, delete, cache monitoring, polish)
6. ✅ **Session 49**: Drafts Tab in EventArtifact (eliminated tab proliferation, unified UX)
7. **Session 50**: Chat research integration ("Use this in draft" button)
8. **Session 51**: Email pre-population + submission tracking
9. **Session 53+**: Per-item independent drafting (if user feedback warrants)

**See Also**:
- `CHAT_STRATEGY_ROADMAP.md` - Long-term chat evolution (research → coach → orchestrator)
- `PERSONALIZATION_SERVICE_ARCHITECTURE.md` - Unified user profiles for all features
- `next_session_prompt.md` - Current session implementation guide
