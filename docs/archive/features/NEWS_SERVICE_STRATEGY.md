# NEWS SERVICE STRATEGY
## Real-Time Local News Integration for Doom-Scrolling → Civic Engagement Conversion

**Version**: 1.0
**Date**: 2025-11-05
**Status**: Strategic Design Document
**Authors**: Multi-expert strategy session

---

## 1. Executive Summary

### Core Value Proposition

**Transform doom-scrolling into civic action** by intercepting local news consumption and connecting it directly to actionable opportunities (events, bills, discussion threads, comment drafting).

**Strategic Hook**: "You're already reading about housing crises on Twitter. What if you could **do something about it** in 30 seconds?"

### Key Integration Points

1. **ResearchService** (Session 66) - Perplexity provider + cache-first factual retrieval
2. **Comment Drafting** (Sessions 37-49) - Natural insertion point for news-driven comments
3. **Chat Panel** (Sessions 27-64) - Primary UI surface for news discovery
4. **Context Management** (Sessions 51-53) - News as contextual artifact type

### Success Metrics

- **Primary**: News consumption → meeting attendance conversion (target: 5-10%)
- **Secondary**: News → comment draft → submission (target: 15-20%)
- **Retention**: Users who engage with news feature return 2x more frequently

### Cost Targets

- **Development**: 40-50 hours over 4-6 weeks
- **Operational**: <$5/month additional (stays within $10/month foundation budget)
- **Per-query**: $0.005-0.01 (Perplexity API + Gemini formatting)

---

## 2. Architecture Design

### 2.1 Service Layer Architecture

**Three-service orchestration pattern** (follows existing ResearchService design from Session 66):

```
┌─────────────────────────────────────────────────────┐
│                  NewsService                        │
│  - Query Perplexity for local news                 │
│  - Extract entities (locations, issues, actors)    │
│  - Score relevance to user's location              │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────┐
│              ResearchService                        │
│  - Query CDBG allocations                          │
│  - Query state legislation                          │
│  - Query federal programs                           │
│  - Provide factual context                          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────────────┐
│              MatchingService                        │
│  - Find related civic events (AI + keyword)        │
│  - Find related bills (legislative cache)          │
│  - Find related threads (discussion similarity)     │
│  - Score match quality                              │
└─────────────────────────────────────────────────────┘
```

### 2.2 API Endpoints Design

**New Endpoints** (add to `civic_api_integrated.py`):

```python
# POST /api/news/query
{
  "query": "housing development Berkeley",
  "location": {"lat": 37.8715, "lng": -122.2730},
  "recency": "week",
  "user_id": "user-123"
}
→ Returns: News articles + matched events + bills + context

# GET /api/news/feed
?user_id=user-123&limit=10
→ Returns: Personalized news feed based on user interests

# POST /api/news/:article_id/draft-comment
{
  "event_id": "event-456",  # From matched event
  "position": "support",
  "key_concern": "Extracted from article + user input"
}
→ Returns: AI-generated draft referencing news article
```

### 2.3 Integration with ResearchService (Cross-Talk Patterns)

**Orchestration flow** (Session 66 foundation):

```python
# news_service.py
class NewsService:
    def __init__(self, research_service: ResearchService):
        self.research = research_service
        self.perplexity = get_llm_provider('perplexity')
        self.matcher = MatchingService()

    def enrich_news_article(self, article: Dict) -> Dict:
        """
        Enrich news with civic context.

        Flow:
        1. Extract entities from article (LLM)
        2. Query ResearchService for CDBG/bills
        3. Match to civic events (MatchingService)
        4. Format enriched response
        """
        # Extract civic entities
        entities = self._extract_entities(article['content'])

        # Query factual context (no hallucination)
        context = {}
        if 'CDBG' in entities['topics']:
            context['cdbg'] = self.research.query(
                f"What is {entities['jurisdiction']}'s CDBG allocation?",
                scope='allocations'
            )

        # Match to events
        events = self.matcher.find_related_events(
            article['content'],
            entities['jurisdiction'],
            entities['topics']
        )

        # Match to bills
        bills = self.matcher.find_related_bills(
            entities['topics'],
            entities['location']
        )

        return {
            'article': article,
            'matched_events': events,
            'matched_bills': bills,
            'context': context,
            'enrichment_quality': self._score_enrichment(events, bills, context)
        }
```

---

## 3. News-to-Event Matching

### 3.1 Algorithm Design (Hybrid Approach)

**Three-layer matching strategy** (decreasing cost, increasing speed):

```
Layer 1: Keyword Matching (Free, <1ms)
  - Extract location names, issue types from article
  - Match against event metadata (jurisdiction, project_type)
  - Score: 0.0-0.4 (low confidence)

Layer 2: Semantic Similarity (Cached embeddings, ~5ms)
  - Embed article summary (cache for 24h)
  - Compare to event embeddings (pre-computed daily)
  - Score: 0.4-0.8 (medium confidence)

Layer 3: LLM Verification ($0.001 per match, ~500ms)
  - Only if Layer 1+2 score > 0.5
  - LLM confirms relevance with explanation
  - Score: 0.8-1.0 (high confidence)
```

**Implementation** (build on existing legislative_enrichment.py pattern):

```python
# matching_service.py
class MatchingService:
    def find_related_events(
        self,
        article_text: str,
        jurisdiction: str,
        topics: List[str]
    ) -> List[Dict]:
        """
        Three-layer hybrid matching.

        Returns:
            [
                {
                    'event_id': 'event-123',
                    'match_score': 0.85,
                    'match_reason': 'Article mentions Telegraph Ave use permit, event is Planning Commission reviewing same project',
                    'match_type': 'llm_verified'
                }
            ]
        """
        # Layer 1: Keyword filter
        keyword_matches = self._keyword_filter(
            jurisdiction=jurisdiction,
            topics=topics
        )

        # Layer 2: Semantic similarity
        semantic_scores = self._semantic_similarity(
            article_text=article_text,
            candidate_events=keyword_matches
        )

        # Layer 3: LLM verification (only high-potential matches)
        verified_matches = []
        for event in semantic_scores:
            if event['score'] > 0.5:
                verification = self._llm_verify(article_text, event)
                if verification['relevant']:
                    event['match_score'] = verification['score']
                    event['match_reason'] = verification['reason']
                    event['match_type'] = 'llm_verified'
                    verified_matches.append(event)

        return sorted(verified_matches, key=lambda x: x['match_score'], reverse=True)[:5]

    def _llm_verify(self, article_text: str, event: Dict) -> Dict:
        """Use Gemini Flash for cost-effective verification"""
        llm = get_provider_for_task('research')  # Gemini Flash from Session 65

        prompt = f"""Is this news article relevant to this civic event?

News: {article_text[:500]}...

Event: {event['title']} - {event['description'][:200]}...

Respond with JSON:
{{
    "relevant": true/false,
    "score": 0.0-1.0,
    "reason": "1-sentence explanation"
}}
"""

        response = llm.complete([
            {"role": "system", "content": "You are a civic relevance classifier. Be precise."},
            {"role": "user", "content": prompt}
        ])

        return json.loads(response.content)
```

### 3.2 Relevance Scoring

**Scoring factors** (weighted combination):

```python
match_score = (
    0.3 * keyword_match_score +      # Location + topic alignment
    0.3 * semantic_similarity_score +  # Embedding cosine similarity
    0.4 * llm_verification_score       # LLM confidence + reasoning
)
```

**Quality thresholds**:
- **0.8-1.0**: "Directly relevant" (show prominently, enable draft)
- **0.6-0.8**: "Possibly relevant" (show as suggestion)
- **0.4-0.6**: "Tangentially related" (background context)
- **<0.4**: Filter out (noise)

### 3.3 Verification Workflow

**Human-in-the-loop validation** (phased approach):

**Phase 1 (MVP)**: Admin review dashboard
- All matches >0.6 logged to review queue
- Admin confirms/rejects matches
- Feedback improves LLM prompts

**Phase 2 (After 100+ matches)**: Community validation
- Users can report "Not relevant"
- Upvote/downvote match quality
- Aggregate signals improve matching

**Phase 3 (After 1000+ matches)**: Automated fine-tuning
- Train lightweight classifier on validated data
- Replace Layer 3 LLM with fine-tuned model
- Cost drops 90%, speed increases 10x

### 3.4 Error Handling

**Graceful degradation**:

```python
try:
    matched_events = matching_service.find_related_events(...)
except Exception as e:
    logger.error(f"[news] Matching failed: {e}")
    matched_events = []  # Empty list, not crash

# Always return partial results
return {
    'article': article,  # Always present
    'matched_events': matched_events or [],  # Empty if failed
    'matched_bills': matched_bills or [],
    'error': str(e) if e else None
}
```

---

## 4. User Experience Flow

### 4.1 Entry Points (Where does news appear?)

**Three discovery surfaces** (progressive disclosure):

1. **Chat Panel** (Primary) - Sessions 27-64 foundation
   ```
   User: "What's happening with housing in Berkeley?"

   Chat: "📰 Recent news: Berkeley Council approves 200-unit development
          📅 Related event: Planning Commission meeting Nov 15
          💬 Want to draft a comment?"
   ```

2. **EventArtifact Details Tab** (Secondary) - Contextual enrichment
   ```
   [User viewing Planning Commission event]

   📰 Related News (2 articles):
   - Berkeleyside: "Neighbors oppose Telegraph Ave project" (Nov 3)
   - Daily Cal: "Berkeley housing shortage worsens" (Nov 1)

   [Read full article] [Use in draft]
   ```

3. **Sidebar News Panel** (Tertiary) - Opt-in discovery
   ```
   ▶ NEWS (3 updates)
     📰 Housing development approved [2 events, 1 bill]
     📰 CDBG funding decisions [1 event]
     📰 Transit plan delayed [0 events]
   ```

### 4.2 Enrichment UX (How to show verified data + bills + meetings)

**Card-based design** (matches existing EventCard pattern):

```vue
<!-- NewsCard.vue -->
<div class="news-card">
  <!-- Article Summary -->
  <div class="news-header">
    <span class="news-source">Berkeleyside</span>
    <span class="news-date">2 days ago</span>
  </div>

  <h3 class="news-title">
    Berkeley Council approves 200-unit housing development
  </h3>

  <p class="news-excerpt">
    The Berkeley City Council voted 6-3 to approve a controversial 200-unit
    development on Telegraph Ave, citing the city's $2.67M CDBG allocation...
  </p>

  <!-- Enrichment Section -->
  <div class="news-enrichment">
    <!-- Matched Events -->
    <div class="enrichment-section" v-if="matchedEvents.length">
      <h4>📅 Related Meetings ({{ matchedEvents.length }})</h4>
      <EventCard
        v-for="event in matchedEvents"
        :key="event.event_id"
        :event="event"
        :match-score="event.match_score"
      />
    </div>

    <!-- Matched Bills -->
    <div class="enrichment-section" v-if="matchedBills.length">
      <h4>🏛️ Related Legislation ({{ matchedBills.length }})</h4>
      <BillChip
        v-for="bill in matchedBills"
        :key="bill.bill_id"
        :bill="bill"
      />
    </div>

    <!-- Factual Context -->
    <div class="enrichment-section" v-if="context.cdbg">
      <h4>💰 Financial Context</h4>
      <p>{{ context.cdbg.answer }}</p>
      <cite>{{ context.cdbg.sources[0] }}</cite>
    </div>
  </div>

  <!-- Actions -->
  <div class="news-actions">
    <button @click="openEvent(matchedEvents[0])" v-if="matchedEvents.length">
      View Meeting
    </button>
    <button @click="draftComment" v-if="matchedEvents.length">
      Draft Comment
    </button>
    <button @click="readFullArticle">
      Read Full Article →
    </button>
  </div>
</div>
```

### 4.3 Call-to-Action Patterns

**Three-tier engagement ladder** (from passive to active):

```
Tier 1: Consume (Low effort)
  → "Read full article" (external link)
  → "View related meeting" (opens EventArtifact)

Tier 2: Connect (Medium effort)
  → "Join discussion" (opens ThreadArtifact)
  → "Follow this issue" (FollowButton)

Tier 3: Act (High effort)
  → "Draft comment" (opens Drafts tab with news context pre-filled)
  → "Email council" (pre-populated email with article citation)
```

**Context-aware prompts** (based on chat mode - Session 53):

```javascript
// Chat mode determines prompts
if (chatMode === 'navigation') {
  // Show discovery prompts
  prompt = "Want to see upcoming meetings about this?"
}

if (chatMode === 'research') {
  // Show deep-dive prompts
  prompt = "I can research CDBG allocations mentioned in this article"
}

if (activeTab === 'drafts') {
  // Show draft integration prompts
  prompt = "Want to cite this article in your comment?"
}
```

### 4.4 Mobile vs Desktop

**Responsive strategy** (mobile-first for news consumption):

**Mobile** (70% of news consumption):
- Stacked vertical cards
- Swipeable news feed
- Bottom sheet for enrichment details
- Persistent "Draft" FAB button

**Desktop** (30% of news consumption):
- Side-by-side layout (news 40%, enrichment 60%)
- Hover states for match quality indicators
- Keyboard shortcuts (N = next article, D = draft)
- Multi-select for batch operations

---

## 5. Data & Caching

### 5.1 News Freshness (Real-time vs Daily Digests)

**Hybrid approach** (balances cost and freshness):

**Real-time** (user-triggered):
- User searches: "housing news Berkeley" → instant Perplexity query
- Cost: $0.005 per query
- Latency: ~2 seconds

**Daily digests** (proactive):
- Cron job runs at 6am daily for all active users
- Query Perplexity for personalized topics × locations
- Cache results for 24 hours
- Cost: $0.005 × active users × 2 topics = ~$1-2/month for 200 users
- Benefit: Instant load when user opens app

**Smart refresh** (triggered updates):
- Breaking news: Webhook from Perplexity (if available)
- User-specific: Refresh on app open if >12 hours stale
- Event-driven: Refresh when new civic event published

### 5.2 Caching Strategy

**Three-layer cache** (Redis-style TTLs):

```python
# Layer 1: Raw article cache (24 hours)
cache_key = f"news:raw:{article_hash}"
ttl = 24 * 3600  # 24 hours

# Layer 2: Enrichment cache (7 days)
# Enriched articles rarely change (events/bills static)
cache_key = f"news:enriched:{article_id}"
ttl = 7 * 24 * 3600  # 7 days

# Layer 3: Match cache (30 days)
# Match scores stable after verification
cache_key = f"news:match:{article_id}:{event_id}"
ttl = 30 * 24 * 3600  # 30 days
```

**Invalidation triggers**:
- New civic event published → invalidate Layer 2 for related articles
- User reports "Not relevant" → invalidate Layer 3 match
- Admin corrects match → invalidate + re-enrich

### 5.3 Storage Requirements

**Estimates** (100 users, 10 articles/user/week):

```
Articles:
- Raw HTML: 50KB/article × 1000 articles/week = 50MB/week
- Summaries: 500 bytes × 1000 = 500KB/week
- Metadata: 1KB × 1000 = 1MB/week

Enrichments:
- Matched events: 2KB × 1000 = 2MB/week
- Matched bills: 1KB × 1000 = 1MB/week
- Context: 500 bytes × 1000 = 500KB/week

Total: ~55MB/week × 4 weeks (retention) = 220MB storage
```

**Cost**: $0.02/month for S3 storage (negligible)

### 5.4 Cost Optimization

**Query batching**:

```python
# BAD: Query Perplexity for each user separately
for user in active_users:
    news = perplexity.query(f"{user.topics} {user.location}")
    # Cost: $0.005 × 100 users = $0.50

# GOOD: Batch queries by location + topic
topics_locations = aggregate_user_preferences(active_users)
for (topic, location) in topics_locations:
    news = perplexity.query(f"{topic} {location}")
    distribute_to_users(news, topic, location)
    # Cost: $0.005 × 20 unique combos = $0.10
```

**Smart expiry**:

```python
# Don't refresh if user hasn't opened app in 7 days
if user.last_active < 7 days ago:
    skip_refresh(user)

# Cost savings: 30-40% reduction (inactive users)
```

---

## 6. Trust & Verification

### 6.1 Fact-Checking Workflow (ResearchService Integration)

**Two-stage verification** (prevent hallucination):

**Stage 1: Article extraction** (LLM parsing)
```python
entities = llm.extract_entities(article_html)
# Extract: locations, dollar amounts, bill references, quotes
```

**Stage 2: Fact verification** (ResearchService cross-check)
```python
for entity in entities:
    if entity.type == 'bill_reference':
        # Cross-check against legislative cache
        verified = research_service.query(
            f"What is {entity.bill_id}?",
            scope='legislative'
        )
        if not verified:
            entity.verified = False
            entity.warning = "Bill not found in official records"

    if entity.type == 'dollar_amount' and 'CDBG' in entity.context:
        # Cross-check against jurisdiction overrides
        verified = research_service.query(
            f"What is {entity.jurisdiction}'s CDBG allocation?",
            scope='allocations'
        )
        if abs(verified.allocation - entity.amount) > 0.1:
            entity.verified = False
            entity.warning = "Amount doesn't match official HUD data"
```

**User-facing indicators**:

```vue
<div class="fact-check">
  <span v-if="entity.verified" class="verified">
    ✓ Verified: $2.67M matches HUD records
  </span>
  <span v-else class="unverified">
    ⚠️ Could not verify: $2.5M cited in article
    Official allocation: $2.67M (source)
  </span>
</div>
```

### 6.2 Citation Display

**Three-level attribution** (clear provenance):

```
Level 1: Article source
  → "Berkeleyside, Nov 3, 2025"

Level 2: Original claim
  → "Berkeley Council approves..." [Read full article →]

Level 3: Verification source
  → ✓ Verified against:
    - City Council minutes (Nov 3, 2025)
    - HUD CDBG allocation data (FY2025)
    - AB 2011 text (Chaptered 2024)
```

**Inline citations** (when used in drafts):

```
Draft: "...given Berkeley's $2.67M CDBG allocation¹ and recent
Council approval of 200 units², this project should prioritize..."

¹ Source: HUD FY2025 CDBG Allocations
² Source: Berkeleyside, "Berkeley Council approves...", Nov 3, 2025
```

### 6.3 Conflict Resolution (News vs Cached Data)

**Priority hierarchy** (when sources disagree):

```
1. Official government records (civic events, meeting minutes)
2. Federal/state data (HUD allocations, bill text)
3. Verified news (established outlets, multiple sources)
4. Unverified claims (flag as "Unconfirmed")
```

**Resolution UI**:

```vue
<div class="conflict-warning" v-if="hasConflict">
  <h4>⚠️ Conflicting Information Detected</h4>

  <div class="source-comparison">
    <div class="source">
      <strong>News article says:</strong>
      <p>"Berkeley allocated $2.5M for housing"</p>
      <cite>Berkeleyside, Nov 3</cite>
    </div>

    <div class="source official">
      <strong>Official records say:</strong>
      <p>"Berkeley allocated $2.67M for community development"</p>
      <cite>HUD FY2025 CDBG Data</cite>
      <span class="badge">✓ Verified</span>
    </div>
  </div>

  <p class="resolution">
    We'll use the official $2.67M figure in your draft.
    The article may be citing a subset of the total allocation.
  </p>
</div>
```

### 6.4 Source Credibility

**Outlet scoring** (based on track record):

```javascript
const SOURCE_CREDIBILITY = {
  // Tier 1: Official government sources
  'city_website': 1.0,
  'state_legislature': 1.0,
  'hud_data': 1.0,

  // Tier 2: Established local news
  'berkeleyside': 0.9,
  'sfchronicle': 0.9,
  'mercury_news': 0.85,

  // Tier 3: Community news
  'local_blogs': 0.7,
  'nextdoor': 0.6,

  // Tier 4: Social media
  'twitter': 0.4,
  'facebook': 0.3
}
```

**Display credibility**:

```vue
<div class="source-credibility">
  <span class="credibility-badge" :class="credibilityClass">
    {{ sourceName }}
  </span>
  <span class="credibility-score">
    Credibility: {{ Math.round(credibility * 100) }}%
  </span>
</div>
```

---

## 7. Implementation Phases

### Phase 1: MVP (Weeks 1-2, 20 hours)

**Goal**: News query + basic matching + draft integration

**Deliverables**:
1. `news_service.py` - Perplexity query wrapper (6h)
2. `matching_service.py` - Keyword + semantic matching (8h)
3. `POST /api/news/query` endpoint (3h)
4. Frontend: NewsCard component (3h)

**Validation**:
- User searches "housing Berkeley" → returns 5 articles with matched events
- Click "Draft comment" → opens Drafts tab with article context
- Match quality >0.6 for 80%+ of results

**Cost**: $0.005 per query (on-demand only)

---

### Phase 2: Enrichment (Weeks 3-4, 15 hours)

**Goal**: Add verification + legislative context + factual cross-checks

**Deliverables**:
1. ResearchService integration (4h)
2. Fact-checking workflow (5h)
3. LLM verification layer (3h)
4. Frontend: enrichment UI (3h)

**Validation**:
- Factual claims verified against official records
- Citations display correctly
- Conflicts flagged and resolved

**Cost**: +$0.001 per article (LLM verification)

---

### Phase 3: Personalization (Weeks 5-6, 10 hours)

**Goal**: Daily digests + user interest tracking + feed curation

**Deliverables**:
1. Daily digest cron job (3h)
2. User interest inference (from PersonalizationService - already built!)
3. `GET /api/news/feed` endpoint (3h)
4. Frontend: news feed UI (4h)

**Validation**:
- Daily digest costs <$2/month for 200 users
- Users see 80%+ relevant articles
- Engagement increases 2x vs manual search

**Cost**: ~$2/month (batch queries for active users)

---

### Phase 4: Advanced (Weeks 7+, 10-15 hours - Optional)

**Goal**: Push notifications, email digests, ML matching

**Deliverables** (pick 1-2 based on PMF signals):
1. Push notifications (5h) - Web Push API
2. Email digests (4h) - Weekly summary emails
3. Fine-tuned matcher (6h) - Train on validated matches

**Validation** (per feature):
- Push notifications: 20%+ click-through rate
- Email digests: 15%+ open rate, 5%+ click rate
- ML matcher: 95%+ accuracy, 10x faster, 90% cheaper

**Cost**:
- Push: Free (Web Push API)
- Email: $0.50/month (SendGrid free tier)
- ML: $0-5 one-time training, $0/month inference

---

## 8. Open Questions

### User Testing / Validation Needed

1. **Discovery preference**: Do users prefer news in chat vs sidebar vs feed?
   - **Test**: A/B test 3 entry points with 50 users each
   - **Metric**: Which generates most engagement?

2. **Match quality threshold**: Is 0.6 too low? Too high?
   - **Test**: Show matches at 0.5, 0.6, 0.7 to different cohorts
   - **Metric**: User feedback + "Not relevant" reports

3. **Enrichment overload**: Is full enrichment (events + bills + context) overwhelming?
   - **Test**: Progressive disclosure (show events first, expand for details)
   - **Metric**: Time-on-page + "View more" clicks

4. **Comment integration**: Do users want article auto-cited in drafts?
   - **Test**: Auto-insert vs manual "Use this" button
   - **Metric**: Draft completion rate + edit behavior

### Technical Unknowns

5. **Perplexity rate limits**: How many queries/minute allowed?
   - **Research**: Check Perplexity docs + test with burst load
   - **Mitigation**: Implement queue + retry logic

6. **Embedding model choice**: OpenAI vs Sentence Transformers vs Cohere?
   - **Test**: Benchmark accuracy + cost + latency
   - **Decision**: Prioritize cost (Sentence Transformers free)

7. **Cache storage**: Local JSON vs Redis vs PostgreSQL?
   - **Research**: Estimate query patterns + data size
   - **Decision**: Start with JSON (simple), migrate to Redis if >1000 users

### Product Decisions Needed

8. **News sources**: Perplexity only vs integrate RSS feeds?
   - **Trade-off**: Perplexity = $0.005/query but comprehensive. RSS = free but limited.
   - **Recommendation**: Start Perplexity, add RSS for high-volume outlets (Berkeleyside)

9. **Real-time vs batch**: On-demand queries vs daily digests?
   - **Trade-off**: Real-time = instant but costly. Batch = affordable but stale.
   - **Recommendation**: Hybrid (batch for feed, real-time for search)

10. **Moderation**: Who verifies match quality before public release?
    - **Options**: Admin review, community voting, automated threshold
    - **Recommendation**: Admin review for Phase 1, community voting Phase 2

---

## 9. Cost Analysis

### Per-Query Costs

```
News retrieval (Perplexity):       $0.005
Entity extraction (Gemini Flash):  $0.0001
Semantic matching (embeddings):    $0 (cached)
LLM verification (Gemini Flash):   $0.001
Total per article:                 $0.0061
```

### Monthly Costs (100 active users)

**Phase 1 (On-demand only)**:
- 100 users × 10 searches/month = 1000 queries
- 1000 × $0.0061 = **$6.10/month**

**Phase 3 (Daily digests)**:
- 100 users × 2 topics × 30 days = 6000 queries
- But: Batch by topic+location reduces to ~600 unique queries
- 600 × $0.0061 = **$3.66/month**

**Phase 4 (With ML fine-tuning)**:
- Replace LLM verification with fine-tuned model
- New cost: $0.005 (Perplexity) + $0.0001 (extraction) = **$0.0051/article**
- Monthly: 600 queries × $0.0051 = **$3.06/month**

### Total Operational Cost Impact

**Current platform**: ~$7/month (event extraction $5 + legislative $2)
**With NewsService Phase 3**: ~$11/month (+$4/month)
**Foundation budget**: $50-100K grants → **<0.02% of budget**

### Cost Optimization Strategies

1. **Batch queries by location+topic** (saves 80%)
2. **Cache aggressively** (7-day enrichment TTL)
3. **Skip inactive users** (saves 30-40%)
4. **Use Gemini Flash** (13x cheaper than Sonnet)
5. **Fine-tune matcher Phase 4** (saves 90% on verification)

---

## 10. Success Criteria

### User Engagement Metrics

**Primary (PMF validation)**:
- News view → meeting attendance: **5-10%** (vs 1-2% baseline)
- News view → comment draft: **15-20%** (vs 3-5% baseline)
- News view → thread join: **10-15%** (community formation)

**Secondary (retention)**:
- Users engaging with news return **2x more frequently**
- Time-to-action reduced by **50%** (doom-scrolling → draft in 2 min vs 5 min)
- Weekly active users increase **30%** (new discovery surface)

### Conversion: News View → Meeting Attendance

**Funnel** (Phase 3 targets):

```
1000 news views (100 users × 10 articles)
  ↓ 40% click enrichment (400)
  ↓ 50% view matched event (200)
  ↓ 30% add to calendar (60)
  ↓ 50% actually attend (30)

Conversion: 30 / 1000 = 3% (vs 1% baseline)
```

**Optimization levers**:
- Improve match quality (Layer 3 LLM verification)
- Better CTAs ("Draft comment in 30 sec")
- Personalization (show news matching past interests)
- Social proof ("12 neighbors discussing this")

### Retention Impact

**Hypothesis**: News discovery drives habit formation

**Measurement**:
- Weekly active users (WAU) with news vs without
- Day 7 retention with news vs without
- Average session frequency with news vs without

**Target**: 30% increase in WAU + 20% increase in D7 retention

### Cost Sustainability

**Thresholds** (foundation funding model):

- ✅ **Sustainable**: <$10/month total operational cost
- ⚠️ **Review needed**: $10-20/month
- ❌ **Unsustainable**: >$20/month (requires monetization)

**Phase 3 projection**: $11/month (within sustainable range)

**Scaling** (200 users): ~$7-8/month (batch efficiency improves)

---

## Conclusion

The NewsService represents a **strategic opportunity** to intercept doom-scrolling behavior and redirect it toward civic action. By leveraging the existing ResearchService foundation (Session 66), provider-agnostic LLM architecture (Session 65), and comment drafting workflows (Sessions 37-49), we can build a robust, cost-effective system that drives the complaint-to-civic PMF strategy.

### Key Advantages

1. **Builds on proven architecture** - ResearchService pattern + provider abstraction
2. **Integrates seamlessly** - Chat panel + EventArtifact + Drafts tab
3. **Cost-effective** - <$5/month additional, stays within foundation budget
4. **Verifiable** - Fact-checking via ResearchService prevents hallucination
5. **Actionable** - Every news article connects to events/bills/drafts

### Strategic Fit

**Complaint-to-Civic PMF**: News → frustration → comment → meeting → community
**Action-Oriented**: Not passive consumption, always path to action
**Trust-Focused**: Verification + citations + conflict resolution
**Foundation-Aligned**: Enhances existing civic infrastructure

### Recommended Next Steps

1. **Validate hypothesis** - User interviews: "Would you use local news integrated with civic meetings?"
2. **Prototype Phase 1** - 20 hours over 2 weeks
3. **Test with 20 users** - Measure conversion: news → meeting attendance
4. **Iterate on matching** - Refine algorithm based on feedback
5. **Scale to Phase 3** - Daily digests if PMF proven

### Risk Mitigation

- **Start small**: On-demand queries only (Phase 1)
- **Test cheaply**: Use Gemini Flash for all LLM tasks
- **Validate early**: 20-user pilot before full launch
- **Graceful degradation**: News optional, core platform still works

---

**Document Status**: Ready for stakeholder review + technical feasibility assessment

**Next Action**: Schedule strategy session to review with product + engineering teams
