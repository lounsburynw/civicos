# Session 78: Web Search Feature Exploration

**Status**: 🚀 Ready to Start
**Estimated Time**: 2-3 hours
**Priority**: High - Enables Phase 2 Research Assistant

---

## 🎯 Goal

Enhance web search UX to enable research-driven civic engagement workflow:
```
Query → Research → Draft → Submit
```

---

## 📋 What We Already Have

### Perplexity Integration (Session 75)
- ✅ `search_web` function in civic_chat_router.py (line 835)
- ✅ Perplexity provider ($0.20-1/1M tokens)
- ✅ Real-time research capability with citations
- ✅ Inline execution (searches happen during chat)

### Current Limitations
- ❌ Not well-exposed in UX (users don't know it exists)
- ❌ No "Research this" button on artifacts
- ❌ Citations not displayed prominently
- ❌ No "Use in draft" integration for research results

---

## 🎨 Proposed Features

### 1. Expose Web Search in Focus Mode (30 min)

**Chat prompts that should trigger search:**
```
"What's the latest on SB 9?"
"Has AB 2011 been signed?"
"What happened at the last planning commission meeting?"
"What's Berkeley's housing element status?"
```

**Implementation:**
- Update Focus mode system prompt to encourage search_web usage
- Add examples to prompt showing when to search
- Test with common civic research queries

### 2. "Research This" Button on EventArtifact (45 min)

**UX:**
```
┌─ Event: Planning Commission Meeting ───────┐
│                                             │
│ [View Agenda] [Research This Event] [Draft]│
│                                             │
│ Agenda Items:                               │
│ • Item 1: Housing development...           │
│   [Research This Item]                      │
└─────────────────────────────────────────────┘
```

**Implementation:**
- Add button to EventArtifact header
- Add button to each agenda item
- Trigger search_web via chat with context
- Example: "Research this event: [event title]"

### 3. Citation Display in Chat (30 min)

**Current:**
```
Assistant: "SB 9 allows lot splits for affordable housing..."
```

**Better:**
```
Assistant: "SB 9 allows lot splits for affordable housing..."

📚 Sources:
• California Legislature - SB 9 Bill Text [link]
• Berkeley Planning - SB 9 Implementation [link]
• YIMBY Law - SB 9 Explainer [link]
```

**Implementation:**
- Parse Perplexity citations from response
- Display in separate "Sources" section
- Make sources clickable (open in new tab)

### 4. "Use This in Draft" Integration (45 min)

**Workflow:**
```
1. User: "Research SB 9 housing"
2. Assistant: [Shows research with citations]
3. UI: Shows "Use this in draft" button
4. User clicks → Opens comment draft with research pre-filled
```

**Implementation:**
- Reuse Session 50's draft research content pattern
- Add button to search results in chat
- Store research in workspace store
- Pass to CommentDraftArtifact when opened

---

## 🔧 Technical Implementation

### Backend (civic_chat_router.py)

**Current search_web handling (line 835-867):**
```python
if tool_call.name == 'search_web':
    query = tool_call.arguments.get('query', '')
    # Use Perplexity for real-time research
    search_provider = get_model_for_task('realtime_research')
    search_response = search_provider.complete(...)
    # Returns result inline
```

**Enhancements needed:**
- Extract and return citations separately
- Add metadata (sources, timestamps)
- Format response for better chat display

### Frontend

**ChatPanel.vue:**
- Enhanced message rendering for search results
- Citation display component
- "Use in draft" button for search results

**EventArtifact.vue:**
- "Research This Event" button
- "Research This Item" button per agenda item
- Trigger chat with context

**MessageBubble.vue (or new component):**
- CitationList component
- Collapsible sources section
- Link handling

---

## 🎯 Success Criteria

1. ✅ User can ask research questions in Focus mode
2. ✅ "Research This" button appears on events/items
3. ✅ Search results show citations prominently
4. ✅ "Use in draft" workflow works end-to-end
5. ✅ Cost remains low (<$1/month for typical usage)

---

## 📊 Cost Analysis

**Perplexity Pricing:**
- Sonar (cheaper): $0.20/1M tokens
- Sonar Pro (better): $1/1M tokens

**Typical search:**
- Query: ~50 tokens
- Response: ~500 tokens
- Total: ~550 tokens
- Cost: $0.00011 (Sonar) or $0.00055 (Sonar Pro)

**Monthly estimate (100 users, 2 searches each):**
- 200 searches × $0.00055 = $0.11/month

**Conclusion:** Very affordable at scale

---

## 🧪 Test Scenarios

### Research Queries
```
1. "What's the latest on SB 9?"
2. "Has Berkeley updated its housing element?"
3. "What happened at the last planning commission meeting?"
4. "What's a conditional use permit?"
```

### Research Button
```
1. Open EventArtifact
2. Click "Research This Event"
3. Verify chat shows research
4. Verify citations appear
```

### Use in Draft
```
1. Ask research question
2. Click "Use this in draft"
3. Open comment draft
4. Verify research appears in context
```

---

## 📚 Related Documentation

- Session 50: Draft Research Content pattern (`draftResearchContent`)
- Session 75: Perplexity integration
- `docs/core/CHAT_STRATEGY_ROADMAP.md` - Phase 2 Research Assistant

---

## 🚫 Out of Scope (For Later)

- **Query history** - Save past research queries
- **Research artifacts** - Dedicated research tab (vs chat inline)
- **Multi-source comparison** - Compare multiple sources
- **Saved research** - Bookmark useful research
- **Research templates** - Pre-filled research queries

---

## 💡 Future Enhancements (Session 79+)

1. **Research Artifacts**: Dedicated tab for deep research
2. **Multi-source**: Compare Wikipedia vs official docs vs news
3. **Research History**: See past searches + results
4. **Research Templates**: "Research this bill", "Research this topic"
5. **OpenRouter Integration**: Access to more models if needed

---

**Ready to start Session 78!** 🚀
