# Test Queries for Pure Function-Calling Architecture (Session 76)

**Backend**: http://localhost:8001 ✅ Running
**Frontend**: http://localhost:5173 (run `cd frontend/civic-workspace && npm run dev`)

---

## 🎯 Test Categories

### 1. Simple Navigation Queries (search_events)
**Expected**: LLM calls `search_events()` function with appropriate parameters

```
Test 1.1: Topic + Jurisdiction
→ "Show me housing meetings in Berkeley"
   Expected: search_events(jurisdiction="city-berkeley", topic="housing")

Test 1.2: Topic only (uses user's city from context)
→ "Find transportation meetings"
   Expected: search_events(jurisdiction="city-berkeley", topic="transportation")
   (Berkeley from user context)

Test 1.3: All jurisdictions
→ "Show all housing meetings across the Bay Area"
   Expected: search_events(jurisdiction="all", topic="housing")

Test 1.4: Synonym handling
→ "Find zoning meetings in Oakland"
   Expected: search_events(jurisdiction="city-oakland", topic="housing")
   (zoning → housing normalization)

Test 1.5: Time-based query
→ "What meetings are happening this week?"
   Expected: search_events(jurisdiction="city-berkeley", dateRange="this-week")

Test 1.6: Specific search
→ "Find meetings about park renovation"
   Expected: search_events(searchQuery="park renovation")
```

---

### 2. Legislative Context Queries (view_legislative_context)
**Expected**: LLM calls `view_legislative_context()` or provides conversational answer

```
Test 2.1: State legislation
→ "Show me housing bills"
   Expected: view_legislative_context(topic="housing", level="state")

Test 2.2: Federal programs
→ "What federal programs exist for transportation?"
   Expected: view_legislative_context(topic="transportation", level="federal")

Test 2.3: Both levels
→ "Show me all environment legislation"
   Expected: view_legislative_context(topic="environment", level="both")

Test 2.4: Synonym normalization
→ "What bills are there about climate change?"
   Expected: view_legislative_context(topic="environment", level="state")
   (climate change → environment)
```

---

### 3. Definition/Research Queries (search_web via Perplexity)
**Expected**: LLM calls `search_web()` for factual questions or provides direct answer

```
Test 3.1: Civic definition
→ "What is CDBG?"
   Expected: search_web(query="What is CDBG Community Development Block Grant")
   OR: Direct conversational answer if LLM knows

Test 3.2: Budget question
→ "How much CDBG funding does Berkeley get?"
   Expected: search_web(query="Berkeley CDBG allocation 2024")

Test 3.3: Current status
→ "What's the status of AB 2011?"
   Expected: search_web(query="California AB 2011 status")

Test 3.4: Process question
→ "How does a planning commission work?"
   Expected: Direct conversational answer (general knowledge)
```

---

### 4. Complaint Filing (file_complaint)
**Expected**: LLM calls `file_complaint()` function

```
Test 4.1: Action verb filing
→ "Report a pothole on Main Street"
   Expected: file_complaint(title="pothole", ...)

Test 4.2: Explicit filing
→ "I want to file a complaint about graffiti"
   Expected: file_complaint(title="graffiti", ...)

Test 4.3: Submit verb
→ "Submit an issue about broken streetlight"
   Expected: file_complaint(title="broken streetlight", ...)
```

---

### 5. My Complaints (view_my_complaints)
**Expected**: LLM calls `view_my_complaints()` function

```
Test 5.1: Basic query
→ "Show my complaints"
   Expected: view_my_complaints()

Test 5.2: Following filter
→ "Show issues I'm following"
   Expected: view_my_complaints(ownership="following")

Test 5.3: Status filter
→ "Show my open complaints"
   Expected: view_my_complaints(status="open")

Test 5.4: Combined filters
→ "Show my closed issues in Berkeley"
   Expected: view_my_complaints(status="closed", jurisdiction="city-berkeley")
```

---

### 6. Follow-up Queries (Context Preservation)
**Expected**: LLM preserves context from previous query

```
Test 6.1: Location change
Query 1: "Find housing meetings in Berkeley"
Query 2: "What about Oakland?"
   Expected: search_events(jurisdiction="city-oakland", topic="housing")
   (Preserves "housing" from first query)

Test 6.2: Topic change
Query 1: "Show transportation meetings in Oakland"
Query 2: "What about housing?"
   Expected: search_events(jurisdiction="city-oakland", topic="housing")
   (Preserves "Oakland" from first query)

Test 6.3: Implicit reference
Query 1: "Find housing meetings"
Query 2: "Show more"
   Expected: Repeats search_events with same parameters
```

---

### 7. OR Queries (Multiple Function Calls)
**Expected**: LLM calls function multiple times for OR conditions

```
Test 7.1: Two-city OR query
→ "Find housing in Berkeley OR transportation in Oakland"
   Expected:
   - search_events(jurisdiction="city-berkeley", topic="housing")
   - search_events(jurisdiction="city-oakland", topic="transportation")

Test 7.2: Multiple topics
→ "Show me housing OR transportation meetings"
   Expected:
   - search_events(topic="housing")
   - search_events(topic="transportation")

Test 7.3: Three-way OR
→ "Find housing in Berkeley OR Oakland OR San Rafael"
   Expected: Three search_events calls with different jurisdictions
```

---

### 8. Mode Detection Tests
**Expected**: Correct mode detected, appropriate system prompt used

```
Test 8.1: Navigation mode (should stay concise)
→ "Find meetings"
   Expected: mode="navigation", brief response

Test 8.2: Focus mode (should be detailed)
Context: User viewing an event artifact
→ "What does this mean?"
   Expected: mode="focus", detailed explanation

Test 8.3: Compare mode (should be analytical)
Context: User has multiple bills open
→ "Compare these bills"
   Expected: mode="compare", systematic comparison

Test 8.4: Uncertain mode
→ "Help"
   Expected: mode="uncertain", shows options menu
```

---

### 9. Edge Cases
**Expected**: Graceful handling of ambiguous/edge cases

```
Test 9.1: Ambiguous jurisdiction
→ "Show meetings"
   Expected: Uses user's city from context OR asks for clarification

Test 9.2: Unknown city
→ "Find meetings in Palo Alto"
   Expected: Infers "city-palo-alto" pattern

Test 9.3: Typo handling
→ "Find meetings in Berkely"
   Expected: Corrects to "city-berkeley"

Test 9.4: Mixed query type
→ "What is CDBG and show me housing meetings"
   Expected: Handles both (search_web + search_events) OR sequential responses
```

---

### 10. Function Combination Tests
**Expected**: LLM chains multiple functions when appropriate

```
Test 10.1: Research then search
→ "What is AB 2011 and which cities are discussing it?"
   Expected:
   - search_web(query="AB 2011") OR direct answer
   - search_events(searchQuery="AB 2011")

Test 10.2: Legislative context with examples
→ "Show me housing bills and related meetings"
   Expected:
   - view_legislative_context(topic="housing")
   - search_events(topic="housing")
```

---

## 🧪 Quick Test Script

Run this to test programmatically:

```bash
python tests/test_pure_function_calling.py
```

Or test individual queries via curl:

```bash
# Test simple search
curl -X POST http://localhost:8001/api/chat/route \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev_key_local" \
  -d '{
    "message": "Show me housing meetings in Berkeley",
    "context": {"user_city": "Berkeley"},
    "mode": "navigation"
  }' | jq .

# Test OR query
curl -X POST http://localhost:8001/api/chat/route \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev_key_local" \
  -d '{
    "message": "Find housing in Berkeley OR transportation in Oakland",
    "context": {"user_city": "Berkeley"},
    "mode": "navigation"
  }' | jq .

# Test definition query
curl -X POST http://localhost:8001/api/chat/route \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev_key_local" \
  -d '{
    "message": "What is CDBG?",
    "context": {"user_city": "Berkeley"},
    "mode": "focus"
  }' | jq .
```

---

## 📊 Expected Results Summary

**Pure Function-Calling Behavior**:
- ✅ All queries use function calling (no `operations` array)
- ✅ OR queries → Multiple function calls in response
- ✅ Mode detection → System prompt customization only
- ✅ Context preservation → Follow-up queries work correctly
- ✅ Synonym normalization → Backend handles (zoning→housing)
- ✅ Graceful degradation → Unclear queries get conversational response

**What Changed from Session 75**:
- ❌ No more `NAVIGATION_SCHEMA` structured outputs
- ❌ No more `operations` array in responses
- ✅ All modes use same function-calling path
- ✅ LLM has more agency to chain/combine functions
- ✅ ~400 fewer lines of routing code

---

## 🎯 Success Criteria

For Session 76 to be considered successful:

1. **All navigation queries** → `search_events()` function called ✅
2. **Legislative queries** → `view_legislative_context()` called ✅
3. **Definition queries** → `search_web()` or conversational answer ✅
4. **OR queries** → Multiple function calls in single response ✅
5. **Mode detection** → Works but doesn't change routing logic ✅
6. **No operations array** → Only function calls in responses ✅
7. **Context preservation** → Follow-ups work correctly ✅
8. **Zero cost increase** → Same LLM calls as before ✅

---

**Status**: Ready for testing! 🚀

Run queries via:
- **Frontend UI**: http://localhost:5173
- **Direct API**: `curl` examples above
- **Test suite**: `python tests/test_pure_function_calling.py`
