# Research Capabilities Strategy
## AI-Powered Civic Intelligence for Informed Participation

**Version**: 1.0
**Date**: 2025-11-10
**Status**: Strategy Document (Session 87)
**Implementation**: Pending dedicated feature branch

---

## Executive Summary

Research capabilities transform the Civic OS from a passive information display into an **active intelligence partner** that helps residents understand complex policy, find supporting evidence, and take informed action. This document outlines the strategy for building world-class research features informed by SOTA tools (Perplexity, NotebookLM, Claude, Google DeepResearch) and validated through simulated user research.

**Core Insight**: Research must be **discoverable, credible, and actionable** to support the Complaint-to-Civic PMF strategy. Users need research to bridge the gap between "I have an opinion" and "I have an informed comment."

---

## Current State (Session 50 Implementation)

### What Exists Today

**Implementation** (ChatPanel.vue:992, MessageBubble.vue:33-44):
- "Use this in draft" button appears on assistant messages >50 chars
- Strips markdown and injects content into DraftWorkspace
- Smart placement before signature
- Visual "Research added" indicator

**Trigger Conditions**:
```typescript
canUseInDraft =
  message.role === 'assistant' &&
  activeArtifact.type === 'event' &&
  message.content.length > 50 &&
  !isNavigationMessage
```

### Critical Friction Points (Session 87 Audit)

1. **Discoverability**: No indication that research is available
   - Users don't know they can ask for research
   - "Use this in draft" button only appears after asking
   - Legislative context collapsed by default

2. **Workflow Complexity**: Multi-step process
   - Must open EventArtifact
   - Must ask chat a question
   - Must wait for response
   - Must click "Use this in draft"
   - Must switch to Drafts tab to see result

3. **No Persistence**: Research is ephemeral
   - Previous research lost in chat scroll
   - Can't revisit earlier findings
   - No way to see "I already researched this"

4. **No Guidance**: Users must know what to ask
   - No template questions
   - No suggestions based on content
   - High cognitive load to formulate queries

---

## User Research Insights (Session 87 Panel)

### Demographic Findings

**Panel**: 10 simulated users across age 19-71, varying tech literacy and civic engagement

#### Universal Needs (5+ mentions)

1. **Citations & Verifiability** (Marcus, Aisha, Robert, Mei)
   - Every AI claim needs a source
   - Link to original documents
   - Inline citations (Perplexity pattern)
   - **Quote**: "If an AI tells me 'SB 9 allows 4 units,' I need to see the actual law text" - Marcus

2. **Progressive Disclosure** (Jamal, Aisha, Carlos, Mei)
   - Quick answer first, depth optional
   - Don't overwhelm with reports
   - **Quote**: "Just answer my question, don't write me an essay" - Jamal

3. **Context Persistence** (Patricia, Aisha, Mei)
   - Remember previous research
   - Don't make users repeat themselves
   - Enable collaborative research
   - **Quote**: "A tool that remembers what I've already researched" - Patricia

4. **Plain Language** (Linda, Patricia, Carlos)
   - Explain jargon automatically
   - Translate policy to personal impact
   - **Quote**: "Don't make me feel stupid for not knowing what CDBG means" - Patricia

#### Demographic Splits

| Feature | Young (18-30) | Middle (31-55) | Older (56+) |
|---------|---------------|----------------|-------------|
| Speed priority | ⚡ Critical | ✓ Important | ~ Less so |
| Mobile-first | ⚡ Must-have | ✓ Nice to have | ~ Desktop OK |
| Social sharing | ⚡ Essential | ~ Neutral | ✗ Don't care |
| Audio summaries | ~ Neutral | ⚡ Love it | ✓ Helpful |
| Template questions | ✓ Helpful | ⚡ Critical | ⚡ Critical |

### SOTA Tool Patterns

| Tool | Pattern | Civic Application |
|------|---------|-------------------|
| **Perplexity** | Inline citations [1][2] + Sources panel | Every AI claim must link to source |
| **NotebookLM** | Audio podcast summaries | Listen to research while driving |
| **Claude** | Artifacts (side-by-side panes) | Keep research visible while drafting |
| **Google DeepResearch** | Quick answer → Full report | Progressive disclosure |
| **All** | Follow-up questions | "Ask more about..." button |

---

## Design Principles

### 1. Citation-First Architecture ⭐⭐⭐

**Every AI claim must show verifiable source**

```
Bad:  "SB 9 allows up to 4 units on single-family lots."
Good: "SB 9 allows up to 4 units on single-family lots. [📄 View Law §65852.21]"
                                                          ↑
                                                    Links to official text
```

**Implementation**:
- Extract sources from LLM responses (OpenAI citations API)
- Render inline superscripts [1][2] with Sources panel
- Fallback: Link to official legislative URLs from enriched context

### 2. Progressive Disclosure ⭐⭐⭐

**Layers of depth based on user interest**

```
Level 1 (Quick Answer):
"SB 9 streamlines housing approvals for up to 4 units"
[Tell me more]

Level 2 (Explanation):
"It allows lot splits + 2 units per parcel = 4 total.
 Applies to single-family zones, ministerial approval..."
[How can I use this in my comment?]

Level 3 (Actionable):
[Full research with citations + draft comment template]
```

### 3. Template Questions (The "Jamal Pattern") ⭐⭐⭐

**Don't make users think - suggest common queries**

When user opens EventArtifact for housing meeting:
```
💡 Common research questions:
  • What state legislation applies to this project?
  • How have neighbors engaged on similar projects?
  • What's the traffic/environmental impact analysis?
  • How do I submit an effective comment?
```

### 4. Context Persistence ⭐⭐

**Remember research across sessions**

```
Research History (Event-specific):
✓ SB 9 applicability (2 min ago)   [View] [Reuse]
✓ Traffic studies (5 min ago)      [View] [Reuse]
```

### 5. Plain Language + Jargon Explanation ⭐⭐

**Auto-explain civic terminology**

```
"This project uses CDBG funding."
         ↓
[ℹ️ CDBG = Community Development Block Grants
   Federal money cities get for affordable housing
   Berkeley has $2.67M allocated this year]
```

---

## Proposed Architecture

### Phase 1: Discoverability (MVP)

**Goal**: Make research obvious without adding UI clutter

**Implementation** (Respects current aesthetic):

```
┌────────────────────────────────────────────────────────────┐
│ EventArtifact: Housing Development at 2590 Channing Way   │
│ [Details] [Discussion] [Drafts]         + Follow      [×] │
├────────────────────────────────────────────────────────────┤
│  Take Action                                               │
│  ┌──────────────┬─────────────┬────────────────────────┐  │
│  │ 📝 Draft     │ 📅 Calendar │ 💬 Ask AI Questions    │  │ ← New button
│  └──────────────┴─────────────┴────────────────────────┘  │
│                                                            │
│  ⚖️ Relevant Legislation                       [Expand ▼] │
│  ┌────────────────────────────────────────────────────┐   │
│  │ SB 9 • Active                                      │   │
│  │ Allows up to 4 units on single-family lots        │   │
│  │ [📄 Official Text]  [💬 How can I use SB 9?]      │   │ ← Inline action
│  └────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

**Key Features**:
1. "Ask AI Questions" button in Take Action panel (generic, works for any artifact)
2. Inline "Ask about..." buttons on legislative items
3. Clicking opens chat with template questions pre-populated

**Behavior**:
```
Click "Ask AI Questions" →

┌────────────────────────────────────────────────────────────┐
│ 💬 Chat (Research Mode)                             [×]    │
├────────────────────────────────────────────────────────────┤
│ [System] I can help you research this meeting.            │
│                                                            │
│ 💡 Suggested questions:                                    │
│  • What state legislation applies to this project?        │
│  • How have neighbors engaged on similar projects?        │
│  • What precedents exist for this type of development?    │
│  • How do I write an effective comment?                   │
│                                                            │
│ [Type your own question...]                         [→]   │
└────────────────────────────────────────────────────────────┘
```

### Phase 2: Citations & Progressive Disclosure

**Citations Pattern** (Perplexity-inspired):
```
[Assistant] SB 9 allows residents to cite state law when challenging
city denials. Here's how:

1. Cite ministerial approval requirement [1]
2. Request objective standards [2]
3. Challenge subjective design reviews [1]

Sources:
[1] CA Government Code §65852.21
[2] HCD ADU and SB 9 Guidelines (2022)

[Use in Draft Comment]  [Tell me more]  [Ask follow-up]
```

**Progressive Disclosure**:
- Quick answer (2-3 bullet points)
- "Tell me more" → Full explanation with context
- "How can I use this?" → Actionable next steps + draft template

### Phase 3: Social Sharing & Advanced Features

**Shareability** (Gen Z engagement):
```
After research → "Share to Social Media"

Auto-generates:
┌────────────────────────────┐
│ 🏘️ Why This Housing Bill  │
│    Matters to Berkeley    │
│                            │
│ • Allows 4 units where 1  │
│   existed                  │
│ • Could add 10K homes by  │
│   2030                     │
│ • Learn more: civic.app   │
└────────────────────────────┘
Export as: Instagram Story, TikTok Slide, Twitter Thread
```

**Document Upload** (NotebookLM pattern):
- Upload agenda PDFs directly to chat
- "Which items relate to housing?"
- "Summarize Item 3.2 for me"

**Fact-Checking**:
- Paste news article URL
- "Is this accurate? What's the full context?"
- Cross-reference with official documents

**Audio Summaries** (NotebookLM pattern):
- "Generate audio summary of this research"
- Listen while driving to meeting
- Prioritize for older users (Linda)

---

## Use Cases & Scenarios

### Scenario 1: Casual Exploration (DeShawn, Low Engagement)

**Entry Point**: Browsing meetings, curious about housing project

**Flow**:
1. Opens EventArtifact → Sees "Ask AI Questions" button
2. Clicks → Template questions appear
3. Clicks "What's the impact on rent?" (pre-formulated)
4. Gets quick answer with sources
5. Shares to Instagram story
6. **Outcome**: Engaged briefly, might return

### Scenario 2: Drafting Comment (Mei, Moderate Engagement)

**Entry Point**: Wants to comment on architecture project

**Flow**:
1. Opens EventArtifact → Clicks "Draft Comment"
2. Sees template questions in chat panel
3. Clicks "What design standards apply?"
4. Reviews research with citations
5. Clicks "Use in Draft" → Auto-inserted with sources
6. Edits draft, includes specific code citations
7. Submits comment
8. **Outcome**: High-quality comment with legal backing

### Scenario 3: Coalition Building (Aisha, High Engagement)

**Entry Point**: Organizing neighbors around zoning issue

**Flow**:
1. Does extensive research on precedents
2. Research saved to persistent history
3. Clicks "Share Research Notebook"
4. Coalition members see same sources
5. Coordinates messaging via Discussion tab
6. All comments cite same legislative framework
7. **Outcome**: Unified, informed coalition

### Scenario 4: Fact-Checking (Robert, High Engagement, Skeptical)

**Entry Point**: Reads news article about local policy

**Flow**:
1. Pastes article URL into chat
2. "Is this claim about SB 9 accurate?"
3. AI cross-references official law text
4. Points out inaccuracy with citation
5. Robert submits corrected info to newspaper
6. **Outcome**: Misinformation corrected with sources

---

## Technical Implementation

### Backend Changes Required

**1. Citation Extraction** (`civic_chat_router.py`):
```python
# Add citations parameter to LLM calls
response = provider.generate(
    prompt=prompt,
    citations=True,  # Request inline citations
    max_tokens=500
)

# Parse citation format
# [claim text][1] → {text: "claim", source_id: 1}
```

**2. Source Registry** (new file `src/research_sources.py`):
```python
class SourceRegistry:
    """Track all sources cited in research responses"""

    def register_source(self, source_id: str, url: str, title: str):
        # Store source metadata
        pass

    def hydrate_citations(self, text: str) -> str:
        # Convert [1] → clickable link
        pass
```

**3. Research History** (extend `civic_api_integrated.py`):
```python
@app.post("/api/research/history")
def get_research_history(
    user_id: str,
    artifact_id: str,
    artifact_type: str
):
    """Retrieve past research for this artifact"""
    # Query chat history filtered by artifact context
    pass
```

### Frontend Changes Required

**1. Research Button Component** (`frontend/civic-workspace/src/components/workspace/ResearchButton.vue`):
```vue
<template>
  <button @click="openResearch" class="action-btn research-btn">
    <MessageCircle :size="16" />
    Ask AI Questions
  </button>
</template>

<script setup>
// Opens chat with template questions
function openResearch() {
  chatStore.setMode('research')
  chatStore.setTemplateQuestions(getQuestionsForArtifact())
  workspaceStore.toggleWorkspaceVisibility() // Show chat
}
</script>
```

**2. Citation Renderer** (`frontend/civic-workspace/src/components/chat/CitationLink.vue`):
```vue
<template>
  <sup class="citation-link" @click="showSource">
    [{{ sourceId }}]
  </sup>
</template>

<!-- Clicking opens source panel with full reference -->
```

**3. Template Questions** (extend `ChatPanel.vue`):
```vue
<div v-if="mode === 'research' && templateQuestions" class="template-questions">
  <p class="template-label">💡 Suggested questions:</p>
  <button
    v-for="q in templateQuestions"
    :key="q"
    @click="askQuestion(q)"
    class="template-btn"
  >
    {{ q }}
  </button>
</div>
```

---

## Implementation Roadmap

### Milestone 1: Discoverability (2-3 hours)
- ✅ Session 87: Strategy complete
- Add "Ask AI Questions" button to Take Action panel
- Add inline "Ask about..." buttons on legislative items
- Template question system in ChatPanel
- **Goal**: Make research obvious

### Milestone 2: Citations (3-4 hours)
- Backend citation extraction from LLM responses
- Frontend citation rendering with Sources panel
- Link legislative enrichment to source URLs
- **Goal**: Make research credible

### Milestone 3: Progressive Disclosure (2-3 hours)
- "Tell me more" expansion system
- Quick answer → Full explanation flow
- "How can I use this?" → Draft integration
- **Goal**: Make research actionable

### Milestone 4: Social Sharing (4-5 hours)
- Export research to image formats
- Instagram/TikTok templates
- Twitter thread generator
- **Goal**: Make research viral-capable

### Milestone 5: Advanced Features (8-10 hours)
- Document upload (PDF parsing)
- Audio summaries (TTS integration)
- Fact-checking mode
- Collaborative research notebooks
- **Goal**: Make research comprehensive

**Total Estimated Time**: 19-25 hours across 5 milestones

---

## Success Metrics

### Functional Metrics
- ✅ Research is discoverable (button visible in <2 clicks)
- ✅ Citations present on 100% of factual claims
- ✅ Template questions available for all artifact types
- ✅ Research → Draft flow takes <60 seconds

### Engagement Metrics
- % of users who discover research feature (target: 60%+)
- % of drafts that include researched content (target: 40%+)
- Average research queries per active user (target: 3+)
- Research content shared to social media (track shares)

### Quality Metrics
- Citation accuracy (target: 99%+ verifiable sources)
- User satisfaction with research results (survey)
- Reduction in misinformation in public comments (qualitative)

---

## Future Considerations

### Integration with Other Features

**Personalization** (Phase 1 complete):
- Suggest research based on user's past civic interests
- Auto-detect expertise level (explain more/less jargon)
- Track which topics user researches most

**Issues/Complaints**:
- "Research similar issues in your neighborhood"
- Auto-suggest relevant legislation when filing complaint
- Connect research to coordination threads

**Proposals** (future):
- Research to support policy proposals
- Auto-generate supporting evidence from civic data
- Track which proposals cite research

**Social Features**:
- Share research in coordination threads
- "3 neighbors researched this bill" indicators
- Collaborative research notebooks for coalitions

### External Integrations

- **Zotero**: Export research to citation managers
- **Google Docs**: Insert research directly into external drafts
- **Email**: Include research links in council emails
- **Social Platforms**: Native sharing to FB/Twitter/Instagram/TikTok

---

## Open Questions

1. **Citation Format**: Inline superscripts [1] vs. end-of-paragraph (footnotes)?
2. **Research Persistence**: Store in database or reconstruct from chat history?
3. **Template Questions**: Hand-curated vs. LLM-generated per artifact?
4. **Social Sharing**: Generate images server-side (expensive) or client-side (complex)?
5. **Fact-Checking**: Separate mode or integrated into Research mode?

---

## References

- Session 50: Original "Use this in draft" implementation
- Session 87: Research capabilities audit + user panel insights
- `docs/architecture/COMMENT_DRAFTING_ARCHITECTURE.md`: Draft system design
- `docs/core/COMMUNITY_CIVIC_PMF_STRATEGY.md`: Complaint-to-Civic strategy
- `docs/core/CHAT_STRATEGY_ROADMAP.md`: Chat mode evolution

---

**Next Steps**: Create dedicated feature branch `feature/research-capabilities` and implement Milestone 1 (Discoverability).
