# LLM Provider Architecture - Implementation Plan Review

**Date**: 2025-11-05
**Reviewers**: [Team Members]
**Status**: AWAITING APPROVAL
**Timeline**: 4 weeks (Sessions 65-70), 2-month buffer before pilot

---

## Executive Summary

**Problem**: Chat can only navigate to artifacts, cannot answer factual questions like "What's Berkeley's CDBG allocation?" This breaks the research → drafting flow and limits user value.

**Solution**: Implement provider-agnostic LLM architecture with research endpoint enabling cache-first factual retrieval + LLM synthesis.

**Strategic Value**:
- ✅ **Completes intelligence backend** before email PMF features
- ✅ **Cost optimization**: 60% savings via provider routing (Haiku for simple, Sonnet for complex)
- ✅ **Future-proofs platform**: Easy A/B testing across OpenAI/Claude/Gemini
- ✅ **Enables research mode**: Foundation for Phase 2 (CHAT_STRATEGY_ROADMAP.md)

**Risk Mitigation**:
- ✅ **Feature flags**: Can disable with single env var
- ✅ **Feature branch**: Work in isolation, merge only when validated
- ✅ **Zero breaking changes**: New modules only, existing chat untouched
- ✅ **Rollback ready**: Tagged recovery points, 3 rollback strategies

---

## Current State Analysis

### What Works ✅
| Capability | Status | Implementation |
|------------|--------|----------------|
| Chat routing | ✅ Complete | OpenAI function calling (Session 27) |
| Navigate to artifacts | ✅ Complete | 6 action types, 80%+ accuracy |
| Comment drafting | ✅ Complete | Structured input → AI generation (Sessions 37-48) |
| CDBG pattern matching | ✅ Complete | Shallow routing fix (Session 64) |

### What's Missing ❌
| Capability | Impact | Workaround |
|------------|--------|-----------|
| Factual Q&A | HIGH | Users must Google externally |
| Cache retrieval | HIGH | Can't query local data files |
| Source citations | MEDIUM | No provenance tracking |
| Provider flexibility | MEDIUM | Locked to OpenAI, higher costs |

### User Pain Points (from Session 64 testing)
```
User: "What's Berkeley's CDBG allocation?"
Current: Opens legislative panel (wrong action)
Expected: "$2.67M for FY2025" with source citation

User: "Tell me about AB 2011"
Current: Opens BillArtifact (navigation only)
Expected: Summary with legislative context

User: Drafting comment, needs to research topic
Current: Must leave app to Google
Expected: Research in chat → "Use this in draft"
```

---

## Proposed Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│                      LLM Provider Layer                          │
│  (New - Provider-agnostic interface for all LLM operations)     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   OpenAI     │  │  Anthropic   │  │   Gemini     │         │
│  │  Provider    │  │   Provider   │  │  Provider    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                 │
│         └──────────────────┴──────────────────┘                 │
│                            │                                     │
│         ┌──────────────────▼──────────────────┐                │
│         │   Provider Factory (routes calls)   │                │
│         └──────────────────┬──────────────────┘                │
│                            │                                     │
│    ┌───────────────────────┴───────────────────────┐           │
│    │                                                 │           │
│    ▼                                                 ▼           │
│ Chat Router                                  Research Service   │
│ (navigation)                                 (factual Q&A)      │
│ [Existing - untouched]                       [NEW]              │
└─────────────────────────────────────────────────────────────────┘
```

### New Modules (Zero Breaking Changes)

**Created Files** (no modifications to existing code):
```
src/llm_provider.py              # Provider factory + routing logic
src/providers/
  ├── base.py                    # Abstract base class (interface)
  ├── openai_provider.py         # Wraps existing OpenAI logic
  ├── anthropic_provider.py      # Claude Sonnet 4 implementation
  └── gemini_provider.py         # Future (placeholder)
src/research_service.py          # Cache-first retrieval + LLM synthesis
src/tool_registry.py             # MCP-compatible tool definitions

migrations/012_research_cache.sql # Optional: Cache research responses
```

**Modified Files** (additive only):
```
src/civic_api_integrated.py     # Add POST /api/chat/research endpoint
frontend/civic-workspace/src/components/chat/
  ├── ChatPanel.vue              # Detect research vs navigation queries
  └── MessageBubble.vue          # Enhanced "Use this in draft" for research
```

### Feature Flags (Safety Controls)

```bash
# .env configuration
LLM_PROVIDER=openai              # Default: existing behavior
ENABLE_RESEARCH_MODE=false       # Default: research disabled
ENABLE_ANTHROPIC=false           # Gradual provider rollout
RESEARCH_CACHE_TTL=3600          # Cache responses (1 hour)

# Backward compatibility guarantee:
# If all flags = default → existing behavior unchanged
```

---

## Implementation Roadmap

### Session 65: Provider Abstraction Layer (6-8h)
**Goal**: Create provider interface without breaking existing chat

**Deliverables**:
1. **Base Provider Interface** (`src/providers/base.py`, ~80 lines)
   ```python
   class LLMProvider(ABC):
       @abstractmethod
       def complete(self, messages: List[dict], tools: List[dict] = None) -> dict:
           """Unified completion interface"""

       @abstractmethod
       def stream_complete(self, messages: List[dict], tools: List[dict] = None):
           """Streaming interface"""

       @abstractmethod
       def parse_tool_call(self, response: dict) -> ToolCall:
           """Extract tool calls from provider-specific format"""
   ```

2. **OpenAI Provider** (`src/providers/openai_provider.py`, ~120 lines)
   - Extract existing OpenAI logic from `civic_chat_router.py`
   - Wrap in provider interface
   - 100% backward compatible

3. **Anthropic Provider** (`src/providers/anthropic_provider.py`, ~150 lines)
   - Claude Sonnet 4 client
   - Tool use via Anthropic API
   - Beta header handling

4. **Provider Factory** (`src/llm_provider.py`, ~60 lines)
   ```python
   def get_provider(provider_name: str = None) -> LLMProvider:
       provider_name = provider_name or os.getenv('LLM_PROVIDER', 'openai')

       if provider_name == 'openai':
           return OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY'))
       elif provider_name == 'anthropic':
           if not os.getenv('ENABLE_ANTHROPIC', 'false') == 'true':
               raise ValueError("Anthropic provider not enabled")
           return AnthropicProvider(api_key=os.getenv('ANTHROPIC_API_KEY'))
       else:
           raise ValueError(f"Unknown provider: {provider_name}")
   ```

**Testing Strategy**:
- Unit tests for each provider
- Integration test: Same query through OpenAI vs Claude
- Backward compatibility: Disable feature flags → verify existing chat works

**Success Criteria**:
- ✅ Existing chat navigation unchanged
- ✅ Can switch providers via env var
- ✅ Both OpenAI and Claude providers functional
- ✅ <100ms provider abstraction overhead

---

### Session 66: Research Endpoint + Cache Integration (4-5h)
**Goal**: Enable factual Q&A with cache-first retrieval

**Deliverables**:
1. **Research Service** (`src/research_service.py`, ~200 lines)
   ```python
   class ResearchService:
       def __init__(self):
           self.caches = {
               'jurisdictions': self._load_jurisdiction_overrides(),
               'bills': self._load_legislative_context(),
               'programs': self._load_federal_programs(),
               'events': self._load_events()
           }

       def query(self, question: str, context: dict = None) -> ResearchResult:
           # Step 1: Cache-first retrieval
           cache_results = self._search_caches(question)

           if cache_results and cache_results.confidence > 0.8:
               return ResearchResult(
                   answer=self._format_answer(cache_results),
                   sources=cache_results.sources,
                   confidence="high",
                   method="cache",
                   insertable=True
               )

           # Step 2: LLM synthesis with retrieved context
           provider = get_provider()

           system_prompt = RESEARCH_SYSTEM_PROMPT.format(
               cache_context=cache_results.text if cache_results else "No cache results"
           )

           response = provider.complete([
               {"role": "system", "content": system_prompt},
               {"role": "user", "content": question}
           ])

           return ResearchResult(
               answer=response['content'],
               sources=self._extract_sources(response),
               confidence="medium",
               method="llm",
               insertable=True
           )
   ```

2. **Cache Search Logic** (~150 lines)
   - Keyword matching for CDBG allocations
   - Fuzzy matching for bill numbers (AB 2011, AB2011, AB-2011)
   - Topic-based retrieval for federal programs
   - Event agenda search

3. **Research Endpoint** (`src/civic_api_integrated.py`, ~80 lines)
   ```python
   @app.post("/api/chat/research")
   async def research_endpoint(request: Request):
       # Feature flag check
       if not os.getenv('ENABLE_RESEARCH_MODE', 'false') == 'true':
           return {"error": "Research mode disabled", "status": 403}, 403

       # Authentication (existing)
       if not authenticate_request():
           return {"error": "Unauthorized"}, 401

       body = await request.json()

       # Validate input
       if 'query' not in body:
           return {"error": "Missing query parameter"}, 400

       # Execute research
       service = ResearchService()
       result = service.query(
           question=body['query'],
           context=body.get('context', {})
       )

       # Log for analytics
       log_research_query(body['query'], result.method, result.confidence)

       return result.to_dict()
   ```

**Testing Strategy**:
- Cache retrieval tests (CDBG, bills, programs)
- LLM synthesis tests (questions with no cache hits)
- Source citation validation
- Performance benchmarks (<500ms for cache hits, <2s for LLM)

**Success Criteria**:
- ✅ "What's Berkeley's CDBG?" → "$2.67M for FY2025" (cache hit)
- ✅ "Tell me about AB 2011" → Bill summary with source
- ✅ "Compare housing policies in Oakland vs Berkeley" → LLM synthesis
- ✅ All responses include source citations

---

### Session 67: Frontend Research Integration (3-4h)
**Goal**: Add research UI without breaking navigation

**Deliverables**:
1. **Query Classification** (`ChatPanel.vue`, ~40 lines)
   ```typescript
   function classifyQuery(message: string): 'navigation' | 'research' {
     const researchPatterns = [
       /what (is|are|was|were)/i,
       /how (much|many)/i,
       /tell me about/i,
       /compare/i,
       /explain/i
     ];

     const navigationPatterns = [
       /show (me)?/i,
       /open/i,
       /find/i,
       /search for/i
     ];

     // Research takes precedence if enabled
     if (config.ENABLE_RESEARCH_MODE &&
         researchPatterns.some(p => p.test(message))) {
       return 'research';
     }

     return 'navigation';
   }
   ```

2. **Research Response Component** (new, ~100 lines)
   ```vue
   <template>
     <div class="research-response">
       <div class="research-answer">
         {{ message.answer }}
       </div>

       <div class="research-sources">
         <span class="source-label">Sources:</span>
         <span v-for="source in message.sources"
               :key="source.path"
               class="source-chip">
           📎 {{ source.name }}
         </span>
       </div>

       <div class="research-confidence"
            :class="`confidence-${message.confidence}`">
         Confidence: {{ message.confidence }}
       </div>

       <button v-if="message.insertable && activeTab === 'drafts'"
               @click="handleUseInDraft"
               class="btn-secondary">
         <Edit3 :size="16" /> Use this in draft
       </button>
     </div>
   </template>
   ```

3. **Enhanced Draft Injection** (`DraftWorkspace.vue`, ~30 lines)
   - Handle research responses (not just plain text)
   - Format with source citations in draft
   - Auto-save after injection

**Testing Strategy**:
- Navigation queries still work (backward compatibility)
- Research queries route to new endpoint
- "Use this in draft" with research data
- UI matches Solarized design system

**Success Criteria**:
- ✅ Navigation commands unchanged ("show housing meetings")
- ✅ Research questions work ("what's CDBG?")
- ✅ Source citations displayed correctly
- ✅ Draft injection with formatted research

---

### Session 68: Tool Registry + MCP Compatibility (3-4h)
**Goal**: Foundation for extensibility

**Deliverables**:
1. **Tool Registry** (`src/tool_registry.py`, ~180 lines)
   ```python
   class ToolRegistry:
       def __init__(self):
           self.tools: Dict[str, Tool] = {}

       def register(self,
                    name: str,
                    description: str,
                    parameters: dict,
                    handler: callable):
           """Register MCP-compatible tool"""
           self.tools[name] = Tool(
               name=name,
               description=description,
               parameters=parameters,  # JSON Schema
               handler=handler
           )

       def get_openai_format(self) -> List[dict]:
           """Convert to OpenAI function calling format"""
           return [{
               "name": tool.name,
               "description": tool.description,
               "parameters": tool.parameters
           } for tool in self.tools.values()]

       def get_anthropic_format(self) -> List[dict]:
           """Convert to Anthropic tool use format"""
           return [{
               "name": tool.name,
               "description": tool.description,
               "input_schema": tool.parameters
           } for tool in self.tools.values()]

       def execute(self, tool_name: str, params: dict) -> dict:
           """Execute registered tool"""
           if tool_name not in self.tools:
               raise ValueError(f"Unknown tool: {tool_name}")

           return self.tools[tool_name].handler(params)
   ```

2. **Built-in Tools** (~100 lines)
   ```python
   # Initialize registry with existing tools
   registry = ToolRegistry()

   registry.register(
       name="search_events",
       description="Search civic events by topic, jurisdiction, date",
       parameters={
           "type": "object",
           "properties": {
               "topic": {"type": "string"},
               "jurisdiction": {"type": "string"},
               "date_range": {"type": "string"}
           }
       },
       handler=search_events_handler
   )

   registry.register(
       name="query_cdbg",
       description="Get CDBG allocation for a jurisdiction",
       parameters={
           "type": "object",
           "properties": {
               "jurisdiction": {"type": "string", "required": True}
           }
       },
       handler=query_cdbg_handler
   )
   ```

3. **Provider Tool Mapping** (update providers, ~60 lines)
   - Providers query registry for available tools
   - Convert to provider-specific format
   - Parse provider-specific tool call responses

**Testing Strategy**:
- Tool registration and execution
- Format conversion (OpenAI vs Anthropic)
- Third-party tool simulation

**Success Criteria**:
- ✅ All navigation tools registered
- ✅ Providers use registry tools
- ✅ Easy to add new tools
- ✅ MCP-compatible format

---

## Risk Assessment & Mitigation

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| Breaking existing chat | LOW | CRITICAL | Feature flags, zero modifications to existing code |
| Provider API changes | MEDIUM | MEDIUM | Abstract interfaces isolate provider-specific code |
| Cost increase | LOW | MEDIUM | Default to OpenAI, monitor costs, disable if needed |
| Performance degradation | LOW | MEDIUM | Cache-first architecture, <100ms overhead target |
| LLM hallucinations | MEDIUM | HIGH | Cache-first reduces hallucinations, cite sources always |

### Rollback Strategies

**Level 1 - Feature Flag (instant)**:
```bash
export ENABLE_RESEARCH_MODE=false
export LLM_PROVIDER=openai
# Restart server → existing behavior restored
```

**Level 2 - Git Revert (1 minute)**:
```bash
git checkout main
git revert <commit-range>
git push
```

**Level 3 - Tag Rollback (1 minute)**:
```bash
git reset --hard v2.35.0-pre-llm-architecture
git push --force
```

**Level 4 - Feature Branch Abandon (1 minute)**:
```bash
git checkout main
git branch -D feature/llm-provider-architecture
# Continue work on main without LLM architecture
```

### Validation Gates

**Gate 1 (Session 65)**: Provider abstraction working
- ✅ Existing chat navigation unchanged with default flags
- ✅ Can switch between OpenAI/Claude via env var
- ✅ Both providers handle tool use correctly
- **Decision**: Proceed to Session 66 or rollback?

**Gate 2 (Session 66)**: Research endpoint functional
- ✅ Cache retrieval works (CDBG, bills, programs)
- ✅ LLM synthesis works for complex queries
- ✅ Source citations accurate
- **Decision**: Proceed to Session 67 or rollback?

**Gate 3 (Session 67)**: Frontend integration
- ✅ UI correctly classifies navigation vs research
- ✅ Research responses display properly
- ✅ "Use this in draft" works with research data
- **Decision**: Proceed to Session 68 or rollback?

**Gate 4 (Session 68)**: Tool registry complete
- ✅ All tools registered and executable
- ✅ Provider-agnostic tool format working
- ✅ Ready for third-party extensions
- **Decision**: Merge to main or continue iteration?

---

## Cost Analysis (2-Month Pilot)

### Current Costs (OpenAI only)
```
100 users × 2 months:
- Navigation: 100 users × 10 queries/user × $0.0015 = $1.50
- Comment drafting: 50 drafts × $0.002 = $0.10
Total: ~$1.60/month × 2 months = $3.20
```

### With Provider Architecture
```
100 users × 2 months:
- Navigation (Haiku): 100 users × 10 queries × $0.0001 = $0.10
- Research (Sonnet): 100 users × 5 queries × $0.003 = $1.50
- Comment drafting (Haiku): 50 drafts × $0.0008 = $0.04
Total: ~$1.64/month × 2 months = $3.28
```

### Cost Comparison
- **Current**: $3.20 (2 months)
- **With architecture**: $3.28 (2 months)
- **Difference**: +$0.08 (2.5% increase)

**But**: Unlocks research mode (new capability) + future optimization potential

### Scale Economics (1000 users)
- **Current (OpenAI only)**: $32/month
- **With provider routing**: $16.40/month
- **Savings at scale**: ~50% reduction

---

## Timeline & Resource Allocation

### Week 1 (Nov 5-12)
- **Session 65**: Provider abstraction (6-8h)
  - Nicolas: Implementation
  - Team: Code review
- **Session 66**: Research endpoint (4-5h)
  - Nicolas: Backend implementation
  - Team: Testing validation

**Deliverable**: Backend research working

---

### Week 2 (Nov 13-19)
- **Session 67**: Frontend integration (3-4h)
  - Nicolas: UI implementation
  - Team: UX validation
- **Session 68**: Tool registry (3-4h)
  - Nicolas: Registry implementation
  - Team: Architecture review

**Deliverable**: End-to-end research flow working

---

### Week 3-4 (Nov 20 - Dec 3)
- User testing with research mode
- Bug fixes and refinements
- Documentation updates
- Performance tuning

**Deliverable**: Research mode production-ready

---

### Week 5-6 (Dec 4-17)
- **Session 69**: Email pre-population (3-4h)
- **Session 70**: Submission tracking (3-4h)
- Integration testing

**Deliverable**: Complete PMF flow (research → draft → email → track)

---

### Week 7-8 (Dec 18 - Jan 1)
- Pilot preparation
- Final polish
- Team training
- Documentation finalization

**Deliverable**: Pilot-ready platform

---

### Buffer (Jan 2 - Jan 31)
- 4 weeks buffer before pilot
- Contingency for unexpected issues
- Beta testing with small user group
- Iteration based on feedback

---

## Success Metrics

### Technical Metrics
- ✅ **Backward compatibility**: 100% of existing chat navigation works
- ✅ **Response time**: <500ms cache hits, <2s LLM synthesis
- ✅ **Accuracy**: >95% factual accuracy for cache-based answers
- ✅ **Uptime**: <100ms provider abstraction overhead
- ✅ **Cost efficiency**: ≤10% cost increase vs current

### User Experience Metrics
- ✅ **Research adoption**: >30% of users try research queries
- ✅ **Draft integration**: >50% of research results used in drafts
- ✅ **Confidence**: >80% of research responses marked "high confidence"
- ✅ **Source trust**: Users cite research sources in final comments

### Development Metrics
- ✅ **Code coverage**: >80% test coverage for new modules
- ✅ **Documentation**: All new endpoints documented
- ✅ **Rollback time**: <5 minutes from detection to recovery
- ✅ **Team velocity**: Sessions stay within estimated time

---

## Dependencies & Prerequisites

### External Dependencies
```json
{
  "anthropic": "^0.7.0",          // Claude API client
  "google-generativeai": "^0.1.0" // Gemini (future)
}
```

### Environment Variables
```bash
# Required (existing)
OPENAI_API_KEY=sk-...
CIVIC_WEB_KEY=dev_key_local

# Required (new)
ANTHROPIC_API_KEY=sk-ant-...     # Claude API key

# Optional (new)
LLM_PROVIDER=openai              # Default provider
ENABLE_RESEARCH_MODE=false       # Enable research endpoint
ENABLE_ANTHROPIC=false           # Enable Claude provider
RESEARCH_CACHE_TTL=3600          # Cache TTL (seconds)
```

### Team Prerequisites
- ✅ Git branch reorganization complete
- ✅ Feature branch ready (`feature/llm-provider-architecture`)
- ✅ Anthropic API access secured
- ✅ Team capacity allocated (6-8h/session × 4 sessions = 20-30h total)

---

## Open Questions for Review

### 1. Architecture Decisions
- **Q**: Should we implement Gemini provider in Session 68 or defer to future?
- **Recommendation**: Defer - focus on OpenAI + Claude first, add Gemini once validated

### 2. Feature Flags
- **Q**: Should research mode be opt-in (default disabled) or opt-out (default enabled)?
- **Recommendation**: Opt-in for pilot, opt-out after validation

### 3. Cost Controls
- **Q**: Should we implement per-user rate limiting for research queries?
- **Recommendation**: Yes - 20 research queries/hour per user (same as comment drafting)

### 4. Provider Selection
- **Q**: Should provider selection be automatic (cost-based routing) or manual (env var)?
- **Recommendation**: Manual for pilot (stability), automatic after validation

### 5. Cache Strategy
- **Q**: Should we persist research responses to database or memory-only cache?
- **Recommendation**: Memory-only for pilot (simpler), database if adoption >50%

---

## Review Checklist

Please review and approve/reject each section:

### Strategic Alignment
- [ ] **Approved**: Problem statement accurately describes user pain
- [ ] **Approved**: Solution aligns with 2-month pilot timeline
- [ ] **Approved**: Priorities correct (intelligence > email PMF)
- [ ] **Concerns**: _[List any concerns]_

### Technical Architecture
- [ ] **Approved**: Provider abstraction design is sound
- [ ] **Approved**: Module boundaries are clean (no coupling)
- [ ] **Approved**: Feature flags provide adequate safety
- [ ] **Concerns**: _[List any concerns]_

### Risk Mitigation
- [ ] **Approved**: Rollback strategies are sufficient
- [ ] **Approved**: Validation gates catch issues early
- [ ] **Approved**: Cost analysis is realistic
- [ ] **Concerns**: _[List any concerns]_

### Timeline & Resources
- [ ] **Approved**: 4-week timeline is achievable
- [ ] **Approved**: Session time estimates are realistic
- [ ] **Approved**: 4-week buffer provides adequate contingency
- [ ] **Concerns**: _[List any concerns]_

### Implementation Plan
- [ ] **Approved**: Session 65 scope is clear
- [ ] **Approved**: Session 66 scope is clear
- [ ] **Approved**: Session 67 scope is clear
- [ ] **Approved**: Session 68 scope is clear
- [ ] **Concerns**: _[List any concerns]_

---

## Approval Decision

**Recommendation**:
- [ ] **APPROVE** - Proceed with Session 65 (Provider Abstraction)
- [ ] **APPROVE WITH CHANGES** - _[List required changes]_
- [ ] **DEFER** - _[Reason for deferral]_
- [ ] **REJECT** - _[Reason for rejection]_

**Reviewer Signatures**:
- [ ] Team Member 1: _________________ Date: _______
- [ ] Team Member 2: _________________ Date: _______
- [ ] Project Lead: ___________________ Date: _______

---

## Next Steps (If Approved)

1. **Immediate** (Day 1):
   - Create feature branch: `feature/llm-provider-architecture`
   - Tag current state: `v2.35.0-pre-llm-architecture`
   - Set up Anthropic API access

2. **Session 65** (Week 1):
   - Implement provider abstraction layer
   - Code review with team
   - Gate 1 validation

3. **Sessions 66-68** (Weeks 1-2):
   - Research endpoint + frontend + tool registry
   - Continuous validation at each gate
   - Team testing throughout

4. **Merge Decision** (End of Week 2):
   - Review all success metrics
   - Team vote on merge to main
   - If approved → merge, tag, document

---

## References

- `docs/core/LLM_PROVIDER_ARCHITECTURE.md` - Complete architectural vision
- `docs/core/CHAT_STRATEGY_ROADMAP.md` - Phase 2 research strategy
- `docs/core/COMMUNITY_CIVIC_PMF_STRATEGY.md` - Product strategy context
- `docs/core/API_DOCUMENTATION.md` - Current API reference
- `docs/core/next_session_prompt.md` - Current implementation status

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Owner**: Nicolas Lounsbury
**Review Deadline**: 2025-11-08 (3 days)
