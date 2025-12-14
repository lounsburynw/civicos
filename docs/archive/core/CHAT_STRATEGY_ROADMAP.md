# Chat Strategy Roadmap: Evolution of Conversational Civic Interface

**Version**: 1.1
**Date**: 2025-11-02 (Updated)
**Status**: Strategic Vision
**Sessions**: 27 (Current) → 80+ (Future)

---

## 🔄 Mode System Revision (Session 56)

**Original modes** (Session 53): Navigation, Research, Coach, Orchestrator
**Revised modes** (Session 56): **Navigation, Focus, Compare**

**Why the change**:
1. **Task-based naming**: Users think "I want to find meetings" (navigation), not abstract modes
2. **Phase alignment**: Focus on Phase 2 capabilities we've actually built
3. **Clearer use cases**: Navigation (search/find), Focus (understand one thing), Compare (analyze multiple things)
4. **Practical limits**: Navigation shows 5 results, Focus deep-dives 1 item, Compare handles 2-4 items

**Future**: Phase 3 will add **Draft** mode for comment composition (Sessions 60+)

**Session 56.5 Refactor**: Navigation mode being upgraded to **Structured Outputs** for guaranteed schema compliance.
See `NAVIGATION_MODE_STRUCTURED_OUTPUTS.md` for complete architecture.

See `frontend/civic-workspace/src/config/chatModes.ts` for implementation.

---

## Executive Summary

The chat interface is evolving from a **navigation helper** (Session 27) to a comprehensive **civic engagement orchestrator**. This roadmap outlines 4 phases over 50+ sessions, each unlocking new capabilities while maintaining simplicity and reliability.

### Current State (Session 27) ✅
Chat as **smart command palette** - navigate to artifacts using natural language.

### Future Vision (Session 80+) 🚀
Chat as **workflow orchestrator** - drive entire civic participation lifecycle through conversation.

---

## Design Principles

1. **Progressive Complexity**: Start simple (navigation), add capabilities incrementally
2. **Reliability First**: Each phase must be rock-solid before moving to next
3. **User Control**: Chat assists, never replaces user agency
4. **Context Awareness**: Chat knows what artifact is open, what user is doing
5. **Provenance Tracking**: All AI-generated content cites sources

---

## Phase 1: Navigation Helper (Sessions 27) ✅ COMPLETE

### **Philosophy**: Chat as VSCode Command Palette

**Capabilities**:
- Navigate to artifacts (events, bills, programs)
- Search/filter events by topic, jurisdiction, date
- Open issues/threads
- Show legislative context

**Implementation**: `src/civic_chat_router.py`
- OpenAI function calling with gpt-4o-mini
- 6 action types: `navigate_to_event`, `search_events`, `open_issue`, `show_legislative_context`, `open_thread`, `show_help`
- Cost: ~$0.30/month for 100 users

**Example Interactions**:
```
User: "Show me housing meetings in Berkeley"
→ Opens EventList filtered to housing + Berkeley

User: "Open the planning commission meeting on Nov 15"
→ Opens specific EventArtifact

User: "What's AB 2011 about?"
→ Opens BillArtifact for AB 2011
```

**Success Metrics**:
- ✅ Chat routes 80%+ navigation requests correctly
- ✅ <500ms response time for routing
- ✅ Zero hallucinated artifact IDs
- ✅ User feedback: "This is faster than clicking"

**Limitations**:
- Cannot answer factual questions (only navigation)
- No memory across messages (stateless)
- No integration with draft/email workflows

---

## Phase 2: Research Assistant + Draft Integration (Sessions 50-55) 🚧 IN PROGRESS

### **Philosophy**: Chat as Knowledge Navigator

**Status**: Sessions 50-53 complete (research integration, context management), Sessions 54-55 pending

**Foundation**: Provider-agnostic LLM architecture enables A/B testing across OpenAI, Claude, Gemini for optimal cost/quality. See `docs/core/LLM_PROVIDER_ARCHITECTURE.md` for complete architecture.

**Goal**: Bridge the research → drafting gap. Enable users to ask questions, get answers, and use those answers in drafts.

### Session 50: Basic Research Integration ✅ COMPLETE

**Completed**: 2025-11-01

**Capabilities Implemented**:
- Answer factual questions about events, bills, allocations
- Provide sources/citations for answers
- "Use this in draft" button on research responses
- Context-aware prompts when Drafts tab is open

**Implementation**:

**Backend** (`civic_chat_router.py`):
```python
# New action type: research_question
{
  'action': 'research_question',
  'parameters': {
    'query': 'What is Berkeley\'s CDBG allocation?',
    'context': {
      'artifact_type': 'event',
      'artifact_id': 'event-berkeley-planning-2025-11-15',
      'tab': 'drafts'  # Context-aware
    }
  }
}

# Implementation
def handle_research_question(query: str, context: dict) -> dict:
    """
    Answer factual questions using:
    1. Legislative context cache (bills, programs, allocations)
    2. Event data (agenda items, descriptions)
    3. Meeting history (future: RAG over minutes)
    """
    # Query legislative cache
    if 'CDBG' in query or 'allocation' in query:
        jurisdiction = extract_jurisdiction(context)
        allocation = get_cdbg_allocation(jurisdiction)
        return {
            'answer': f"{jurisdiction} receives ${allocation}M in CDBG funding for 2024.",
            'sources': ['HUD 2024 CDBG Allocation Data'],
            'insertable': True,  # Can be inserted into draft
            'source_id': 'cdbg-berkeley-2024'
        }

    # Query bill data
    if 'AB' in query or 'SB' in query:
        bill_id = extract_bill_id(query)
        bill = get_bill_by_id(bill_id)
        return {
            'answer': bill['summary'],
            'sources': [f"{bill['bill_id']}: {bill['title']}"],
            'insertable': True,
            'source_id': bill['bill_id']
        }

    # Fallback: use LLM with event context
    return {
        'answer': '[LLM-generated answer]',
        'sources': ['AI inference - verify independently'],
        'insertable': False  # Don't allow insertion of unverified content
    }
```

**Frontend** (`ChatPanel.vue`):
```typescript
// Context-aware prompt suggestions
const contextSuggestions = computed(() => {
  const artifact = workspaceStore.activeArtifact;

  if (artifact?.type === 'event' && artifact.tab === 'drafts') {
    return [
      'What is this event about?',
      'What are the CDBG allocations?',
      'Which state bills relate to this?',
      'What did the council decide last time?'
    ];
  }

  return defaultSuggestions;
});

// Render research response with insert button
function renderResearchResponse(response: ResearchResponse) {
  return `
    <div class="research-response">
      <p>${response.answer}</p>
      <div class="sources">
        <span>Sources:</span>
        ${response.sources.map(s => `<cite>${s}</cite>`).join(', ')}
      </div>
      ${response.insertable ? `
        <button @click="insertIntoDraft('${response.source_id}')">
          Use this in draft
        </button>
      ` : ''}
    </div>
  `;
}
```

**Draft Integration** (`DraftWorkspace.vue`):
```typescript
// Insert research into draft
async function insertResearch(sourceId: string, content: string) {
  // Add to draft with citation
  const citation = `\n\n${content}¹\n\n¹ Source: [${sourceId}]`;

  // Insert after intro or at cursor position
  draftContent.value += citation;

  // Track provenance
  researchRefs.value.push({ sourceId, content, insertedAt: new Date() });
}

// Show research references in draft
<div class="research-refs" v-if="researchRefs.length > 0">
  <span>📚 Research used:</span>
  <button
    v-for="ref in researchRefs"
    :key="ref.sourceId"
    @click="openChatMessage(ref.sourceId)"
  >
    {{ ref.sourceId }}
  </button>
</div>
```

**Example Flow**:
```
[User opens EventArtifact → Drafts tab]

Chat: "I noticed you're drafting a comment on the use permit.
       Would you like me to research:
       • CDBG allocations for Berkeley?
       • Similar permit decisions?
       • AB 2011 impacts on this permit?"

User: "Yes, CDBG allocations"

Chat: "Berkeley receives $2.67M in CDBG funding for 2024.
       Sources: HUD 2024 CDBG Allocation Data
       [Use this in draft]"

User: [Clicks "Use this in draft"]

→ Draft editor updates:
"...given Berkeley's $2.67M CDBG allocation¹, this project should prioritize affordable housing..."

¹ Source: HUD 2024 CDBG Allocation Data
```

**Success Metrics**:
- Research requests answered with <2s latency
- 90%+ of answers cite verifiable sources
- Users insert research into drafts 30%+ of the time
- No hallucinated facts (validate against cache)

**Cost Analysis**:
- Research queries: ~500 tokens input, ~200 tokens output
- Cost per query: ~$0.0007 (gpt-4o-mini)
- 100 users × 10 queries/month = ~$0.70/month

---

### Session 51-52: Meeting History RAG (Optional)

**Goal**: Enable chat to search past meeting minutes/decisions.

**Capabilities**:
- "What did the council decide about this last year?"
- "Has this been discussed before?"
- "Who opposed similar projects in the past?"

**Implementation**:
- Vector database (ChromaDB/Pinecone) for meeting minutes
- PDF extraction of past agendas (already have parser)
- Semantic search over historical decisions

**Cost**: TBD (depends on vector DB choice)

---

### Session 53-55: Multi-Source Research

**Goal**: Integrate web search for broader context.

**Capabilities**:
- "What are community concerns about this project?" → Search local news
- "What's the city's housing plan?" → Search city website
- "How does this compare to other cities?" → Search comparable jurisdictions

**Implementation**:
- Web search API (Tavily, Perplexity, or Google Custom Search)
- Result curation to avoid low-quality sources
- Clear labeling: "From web search" vs. "From city data"

**Cost**: ~$5-10/month for web search API

---

## Phase 3: Civic Coach (Sessions 60-70)

### **Philosophy**: Chat as Engagement Guide

**Goal**: Help users navigate civic processes, understand impact, find allies.

### Session 60-62: Conversational Comment Drafting

**Alternative to form-based drafting**: Natural language onboarding.

**Capabilities**:
```
User: "I want to comment but don't know what to say"

Chat: "Let's start with your position. Do you support or oppose the use permit?"

User: "I oppose it"

Chat: "What's your main concern? (e.g., traffic, parking, building height)"

User: "Traffic during school pickup"

Chat: "Got it. Are you a homeowner, parent, or other stakeholder?"

User: "Both - homeowner and parent"

Chat: "Perfect. Let me draft a comment for you..."
→ Generates draft using structured input
```

**Implementation**:
- Multi-turn conversation state management
- Conversation → structured input mapping
- Handoff to existing draft generation endpoint

**Success Metrics**:
- 40%+ of users prefer conversational vs. form-based
- Conversation → submission rate matches/exceeds form
- <5 messages to complete structured input

---

### Session 63-65: Impact Tracking Insights

**Goal**: Show users their civic impact over time.

**Capabilities**:
```
User: "Did my comment matter?"

Chat: "Your comment on the Telegraph Ave project was one of 8 mentioning traffic.
       The commission required a traffic study before approval.
       This is consistent with 40% of comments in Berkeley leading to modifications."

User: "What should I focus on next?"

Chat: "Based on your past comments (housing, transportation), these upcoming items match your interests:
       • Item 3.1: Use permit (housing) - Meeting Nov 15
       • Item 4.2: Transit plan (transportation) - Meeting Nov 20"
```

**Implementation**:
- Impact tracking database (comment → decision linkage)
- User civic history aggregation
- Behavioral inference from past actions

**Requirements**:
- PersonalizationService Phase 3 (behavioral inference)
- Manual impact tagging (admin workflow)
- Meeting outcome extraction (from minutes)

---

### Session 66-68: Coordination Suggestions

**Goal**: Connect users with others who share concerns.

**Capabilities**:
```
User: "I'm worried about this project"

Chat: "12 people are also discussing this item.
       Top concerns: traffic (8), parking (5), height (3)
       Want to join their discussion thread?"

User: "Yes"

Chat: [Opens ThreadArtifact with 12 participants]
```

**Implementation**:
- Real-time discussion stats
- Smart matching (similar positions/concerns)
- Proactive suggestions when user drafts comment

---

## Phase 4: Workflow Orchestrator (Sessions 80+)

### **Philosophy**: Chat as Primary Interface

**Goal**: Users drive entire civic workflow with natural language. UI follows chat.

### Capabilities:

**Multi-Step Task Execution**:
```
User: "I want to attend the planning meeting and comment on item 3.1"

Chat:
1. ✓ Added meeting to calendar
2. ✓ Opened draft for item 3.1
3. ⏳ Researching item 3.1 background...
4. ✓ Found: 3 related bills, $2.67M CDBG allocation, 2 past similar permits
5. [ ] Ready to draft?

User: "Yes"

Chat: [Opens Drafts tab with pre-filled context]
      "I've started your draft with research on CDBG allocations and AB 2011.
      What's your main concern about this permit?"
```

**Proactive Suggestions**:
```
Chat: "The planning meeting is in 2 days. You have:
       • 1 unfinished draft (Item 3.1)
       • 12 people discussing this item
       • New research available on CDBG allocations
       Want to finalize your comment?"
```

**Email/Calendar Integrations**:
```
User: "Send my draft to the clerk"

Chat:
1. ✓ Formatted comment for email
2. ✓ Added clerk email (clerk@cityname.gov)
3. ✓ Generated subject line
4. [ ] Ready to send?

User: "Yes"

Chat: [Opens email client with pre-filled content]
      ✓ Email sent
      ✓ Marked draft as submitted
      ✓ Added reminder to check meeting outcome
```

**Implementation Challenges**:
- Multi-step action sequencing (error handling, rollback)
- State persistence across sessions
- User expectations management (chat isn't magic)
- Calendar/email permissions (OAuth)

**Success Metrics**:
- Users complete 60%+ of workflows through chat
- <5% action failure rate
- NPS score 8+ for chat experience

---

## Cost Projections

**Phase 1 (Current)**: $0.30/month for 100 users
- Navigation routing only

**Phase 2 (Sessions 50-55)**: $5-10/month for 100 users
- Research queries: $0.70/month
- Web search API: $5-10/month (optional)
- Meeting history RAG: TBD

**Phase 3 (Sessions 60-70)**: $15-20/month for 100 users
- Conversational drafting: +$5/month (longer conversations)
- Impact insights: +$2/month (aggregation queries)
- Coordination matching: negligible

**Phase 4 (Sessions 80+)**: $30-40/month for 100 users
- Multi-step orchestration: +$10/month (complex prompts)
- Proactive suggestions: +$5/month (background processing)
- Email/calendar integrations: negligible

**Foundation funding model**: At $50-100K grants, these costs are negligible (<0.1% of budget).

---

## Risk Analysis

### Technical Risks

**1. Hallucination / Inaccurate Information**
- **Risk**: Chat provides wrong bill ID, incorrect allocation, or made-up facts
- **Mitigation**:
  - Always cite sources (legislative cache, not LLM memory)
  - Flag AI-inferred content as "verify independently"
  - Don't allow insertion of unverified research into drafts
  - Validate against structured data before displaying

**2. Action Execution Failures**
- **Risk**: Multi-step workflows fail partway through (Phase 4)
- **Mitigation**:
  - Idempotent actions (safe to retry)
  - Clear error messages ("Calendar integration failed - try adding manually")
  - Graceful degradation (fail open, not closed)

**3. Context Window Overflow**
- **Risk**: Long conversations exceed LLM context limits
- **Mitigation**:
  - Summarize conversation history after N messages
  - Prioritize recent context over old
  - Reset conversation when artifact changes

### User Experience Risks

**4. Overreliance on Chat**
- **Risk**: Users expect chat to do everything, get frustrated when it can't
- **Mitigation**:
  - Clear communication of capabilities ("I can help with research, but you'll need to...")
  - Progressive disclosure of features (don't advertise Phase 4 in Phase 2)
  - Always provide manual alternative ("Or click here to...")

**5. Privacy Concerns**
- **Risk**: Users worry about conversation data being stored/sold
- **Mitigation**:
  - Clear privacy policy: "Conversations stored locally, never sold"
  - Option to disable chat entirely
  - No conversation data sent to third parties (except OpenAI for processing)

### Business Risks

**6. Cost Scaling**
- **Risk**: Chat costs scale faster than anticipated
- **Mitigation**:
  - Cache common queries (CDBG allocations, bill summaries)
  - Rate limiting (10 queries/minute per user)
  - Degrade to cheaper models (Haiku) for simple queries
  - Monitor costs per user, set alerts

---

## Integration with Other Features

### Context Management (Sessions 52-60) 🆕
- **Phase 1**: Visual context indicators (what's "in context")
- **Phase 2**: Context registry with mode-aware filtering
- **Phase 3**: Multi-artifact context for complex workflows
- **Phase 4**: Semantic retrieval with vector embeddings
- See `CONTEXT_MANAGEMENT_ARCHITECTURE.md` for complete design

### Comment Drafting (Sessions 37-49)
- **Phase 2**: Insert research into drafts
- **Phase 3**: Conversational drafting as alternative to forms
- **Phase 4**: End-to-end workflow (research → draft → submit)
- **Context Integration**: Draft generation uses context registry to access event details, bills, related discussions

### Personalization (Sessions 46+)
- **Phase 2**: Use user profile for context ("You're a homeowner in Berkeley")
- **Phase 3**: Behavioral inference ("Based on your past comments...")
- **Phase 4**: Proactive suggestions ("This matches your interests")

### Discussions/Coordination (Sessions 32-35)
- **Phase 3**: Suggest relevant threads ("12 people discussing this")
- **Phase 4**: Auto-create threads when user comments

### Legislative Context (Sessions 10-13)
- **Phase 2**: Answer questions about bills/programs
- **Phase 3**: Suggest relevant legislation for drafts
- **Phase 4**: Monitor new legislation matching user interests

---

## Success Indicators (Per Phase)

### Phase 1 ✅
- [x] 80%+ routing accuracy
- [x] <500ms response time
- [x] Zero hallucinated IDs
- [x] User feedback: "Faster than clicking"

### Phase 2 (Target: Session 55)
- [ ] 70%+ research questions answered accurately
- [ ] 30%+ insertion rate (research → draft)
- [ ] <2s research latency
- [ ] User feedback: "Chat saves me time researching"

### Phase 3 (Target: Session 70)
- [ ] 40%+ use conversational drafting
- [ ] Impact insights viewed 60%+ after submission
- [ ] Coordination suggestions accepted 30%+
- [ ] User feedback: "Chat helps me be more effective"

### Phase 4 (Target: Session 90)
- [ ] 60%+ workflows completed via chat
- [ ] <5% action failure rate
- [ ] NPS 8+ for chat experience
- [ ] User feedback: "I can't imagine using this without chat"

---

## Decision Points

At each phase transition, evaluate:

1. **User Adoption**: Are users actually using the new capabilities?
2. **Cost Trajectory**: Is cost per user sustainable?
3. **Technical Stability**: Is reliability >95%?
4. **User Feedback**: NPS >7 for this phase?

**Go/No-Go Criteria**:
- If any metric fails, iterate on current phase before advancing
- If costs exceed $1/user/month, optimize before expanding
- If user feedback <7 NPS, redesign interactions

---

## Alternatives Considered

### Alternative 1: No Chat (Pure UI)
**Pros**: Simpler, no LLM costs, no hallucination risk
**Cons**: Higher learning curve, less accessible, more clicks
**Verdict**: Rejected - chat enables fundamentally better UX

### Alternative 2: Full Chatbot (No UI)
**Pros**: Ultimate simplicity - just text
**Cons**: Hard to show complex data, no visual artifacts
**Verdict**: Rejected - hybrid (chat + UI) is best

### Alternative 3: Command Bar Only (No Conversational)
**Pros**: Cheaper (no LLM), predictable behavior
**Cons**: Requires learning syntax, less accessible
**Verdict**: Rejected - natural language is critical for accessibility

### Alternative 4: Third-Party Chatbot (Intercom, ChatGPT Plugin)
**Pros**: Don't build chat infrastructure
**Cons**: No integration with artifacts, no action execution, data privacy
**Verdict**: Rejected - need tight integration with workspace

---

## Appendix A: Chat Router Architecture Evolution

### Session 27 (Current):
```
User Message
    ↓
OpenAI Function Calling (gpt-4o-mini)
    ↓
Extract action + parameters
    ↓
Execute action (navigate, search, open)
    ↓
Return artifact ID to frontend
    ↓
Frontend opens artifact
```

### Session 50-55 (Phase 2):
```
User Message
    ↓
Classify intent (navigation vs. research)
    ↓
If research:
    Query legislative cache / event data
    ↓
    Format answer with sources
    ↓
    Return with insertable flag
Else:
    Existing navigation flow
```

### Session 52-56 (Context Management Integration):
```
User Message + Context Registry Snapshot
    ↓
Context-Aware Intent Classification
    ↓
Active Context Elements:
  - event-123 (Details tab) [primary]
  - bill-ab1147 [secondary]
  - draft-789 (in progress) [reference]
    ↓
If research:
    Query with context filters
    ↓
    Format answer citing open artifacts
    ↓
    "Based on the event you're viewing..."
Else:
    Context-aware navigation
    ↓
    "Switching to your draft for this event..."
```

### Session 60-70 (Phase 3):
```
User Message
    ↓
Load conversation history (last 10 messages)
    ↓
Classify intent (navigation / research / coaching)
    ↓
If coaching:
    Multi-turn conversation state machine
    ↓
    Guide user through structured input
    ↓
    Generate draft when complete
Else:
    Existing flows
```

### Session 80+ (Phase 4):
```
User Message
    ↓
Load full context:
    - Conversation history
    - Open artifacts
    - User profile
    - Civic history
    ↓
Classify intent (navigation / research / coaching / orchestration)
    ↓
If orchestration:
    Generate action sequence (plan)
    ↓
    Execute actions sequentially
    ↓
    Handle errors / rollback
    ↓
    Report progress to user
Else:
    Existing flows
```

---

## Appendix B: Research Query Examples

**Factual Queries** (Phase 2 - Session 50):
- "What is Berkeley's CDBG allocation?" → Query cache
- "What does AB 2011 say?" → Query bill database
- "When is the next planning meeting?" → Query event data

**Historical Queries** (Phase 2 - Session 51-52):
- "What did the council decide last time?" → RAG over minutes
- "Has this been discussed before?" → Semantic search
- "Who opposed similar projects?" → Parse historical comments

**Comparative Queries** (Phase 2 - Session 53-55):
- "How does this compare to Oakland?" → Multi-jurisdiction query
- "What are community concerns?" → Web search local news
- "What's the city's housing plan?" → Search city website

**Coaching Queries** (Phase 3):
- "How do I write an effective comment?" → Provide guidance
- "Did my comment matter?" → Impact tracking analysis
- "Who else cares about this?" → Coordination matching

**Orchestration Queries** (Phase 4):
- "I want to comment on this meeting" → Multi-step workflow
- "Remind me to follow up after the meeting" → Calendar integration
- "Send my draft to the clerk" → Email automation

---

## Appendix C: LLM Provider Architecture (2025-11-05)

**Status**: Architecture proposal complete
**Document**: `docs/LLM_PROVIDER_ARCHITECTURE.md`

**Key Capabilities**:
- **Provider Abstraction Layer**: Swap OpenAI, Claude, Gemini via `LLM_PROVIDER` environment variable
- **Tool Registry System**: MCP-compatible tool definitions enable third-party extensions
- **Research Mode Foundation**: Cache-first factual queries with zero hallucination
- **Cost Optimization**: Smart routing saves 50-70% (Haiku for simple, Sonnet for complex queries)
- **Future-Proof**: Compatible with Claude Code agentic workflows, Anthropic Contextual Retrieval, RAG

**Why This Matters for Chat Evolution**:
- **Phase 2** (Research): A/B test providers for research quality (Claude may be better at synthesis)
- **Phase 3** (Coach): Use Claude Sonnet for conversational drafting (superior writing quality)
- **Phase 4** (Orchestrator): Use Claude Sonnet for multi-step reasoning (best planning capabilities)
- **All Phases**: Reduce costs 50-70% via smart provider routing

**Migration Path**: 30 hours over 3 weeks to implement provider abstraction + tool registry

---

**END OF ROADMAP**

This roadmap will be updated quarterly based on user feedback, technical feasibility, and strategic priorities.
