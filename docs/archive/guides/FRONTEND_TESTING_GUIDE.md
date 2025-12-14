# Frontend-Backend Integration Testing Guide

This guide documents the testing approach for the Civic Conversational OS frontend-backend integration, inspired by real debugging challenges encountered during UX development.

## Background: Issues We Solved

During frontend development, we encountered several integration challenges that led to **static responses instead of dynamic AI conversation**:

1. **API URL Configuration**: `file://` protocol treated relative URLs incorrectly
2. **MCP Availability**: `mcpEnabled` was `undefined` due to response parsing issues  
3. **Response Structure**: Frontend expected `data.message.content` but API returned `data.response`
4. **Authentication**: API keys not properly configured for local development
5. **CORS Issues**: Browser blocked requests from `file://` origin
6. **Missing Functions**: `updateStatusBar` function didn't exist, causing initialization failures

## Related Testing Documentation

- **`docs/INTERACTIVE_STRESS_TESTING_GUIDE.md`** - For solo developers validating recent changes and stress testing regional scale
- **`tests/test_phase3_regional_scaling.py`** - Comprehensive automated validation of Phase 3 features
- **`docs/PHASE_3_DEPLOYMENT_GUIDE.md`** - Production deployment procedures and monitoring

## Test Suites

### 1. Python Integration Tests (`test_frontend_integration.py`)

**Run with:** `python tests/test_frontend_integration.py`

**Requirements:**
- API server running on `localhost:8001` (default, configurable with CIVIC_API_PORT)
- `CIVIC_WEB_KEY` environment variable set
- Schema data available in `data/schema/`

**Tests:**
- ✅ **API Server Health**: Verifies server is running and responds correctly
- ✅ **MCP Availability Response**: Checks `integration_status.mcp_enabled` field exists
- ✅ **API Authentication**: Tests all endpoints with Bearer token
- ✅ **CORS Headers**: Validates preflight requests for `file://` protocol
- ✅ **Data Pipeline**: Verifies civic_digest → schema → API data flow
- ✅ **Conversation API Structure**: Validates response format (`data.response`)
- ✅ **Context Injection**: Ensures AI responses include civic opportunities

### 2. Browser Console Tests (`test_frontend_browser.js`)

**Run by:**
1. Loading the frontend in browser
2. Copy/paste the entire JS file into browser console
3. Run `runFrontendTests()`

**Tests:**
- ✅ **API URL Configuration**: Checks `file://` vs `localhost` URL logic
- ✅ **API Key Availability**: Verifies `getApiKey()` returns valid key
- ✅ **MCP Status**: Ensures `mcpEnabled` is boolean (not undefined)
- ✅ **Frontend Functions**: Checks all required functions exist
- ✅ **Session Storage**: Tests localStorage/sessionStorage access
- ✅ **API Health Check**: Direct browser → API communication
- ✅ **Opportunities API**: Validates data loading
- ✅ **Conversation API**: Tests real AI conversation flow

## Debug Helpers

### Browser Console Utilities

After loading `test_frontend_browser.js`, use these debug functions:

```javascript
// Check current status
window.debugFrontend.checkMCPStatus()

// Test conversation without UI  
window.debugFrontend.testConversation("What opportunities are available?")

// Force refresh MCP availability
window.debugFrontend.recheckMCP()
```

### Quick Manual Tests

**In browser console:**
```javascript
// Test API connection
testAPI()

// Test conversation API
testConversation("Hello")

// Check MCP status  
checkMCP()

// Manual enable if needed
mcpEnabled = true
```

## Common Integration Issues & Solutions

### Issue 1: Static Responses ("Thanks for sharing that...")
**Symptom:** AI gives generic responses instead of civic-specific answers  
**Cause:** `mcpEnabled = undefined` or `false`  
**Debug:** Run `checkMCP()` in console  
**Solution:** Run `recheckMCP()` or manually set `mcpEnabled = true`

### Issue 2: 401 Unauthorized Errors
**Symptom:** API calls fail with authentication errors  
**Cause:** API key not properly set in sessionStorage  
**Debug:** Check `sessionStorage.getItem('civic_api_key')`  
**Solution:** Ensure `getApiKey()` returns valid key for `file://` protocol

### Issue 3: "Cannot read properties of undefined"
**Symptom:** JavaScript errors when parsing API responses  
**Cause:** Frontend expects different response structure than API provides  
**Debug:** Check API response structure in Network tab  
**Solution:** Update frontend parsing to match API response format

### Issue 4: CORS Blocking (file:// protocol)
**Symptom:** "Cross origin requests are only supported for protocol schemes..."  
**Cause:** Browser blocks `file://` → `http://localhost` requests  
**Debug:** Check if `API_BASE_URL` is set correctly  
**Solution:** Ensure API_BASE_URL logic handles `file://` protocol

## Test-Driven Development Approach

When adding new frontend features:

1. **Write tests first** for expected behavior
2. **Run tests** to confirm they fail appropriately  
3. **Implement feature** to make tests pass
4. **Add debug helpers** for future troubleshooting

### Example Test Addition

```python
def test_new_feature(self):
    """Test new feature integration"""
    try:
        response = requests.get(f"{self.api_base_url}/api/new-endpoint")
        # Add assertions
        self.log_test("New Feature", response.status_code == 200)
    except Exception as e:
        self.log_test("New Feature", False, str(e))
```

## Running Tests in CI/CD

### GitHub Actions Integration
```yaml
- name: Frontend Integration Tests
  run: |
    python src/civic_api_integrated.py &
    sleep 5
    python tests/test_frontend_integration.py
    kill %1
```

### Pre-commit Hooks
```bash
#!/bin/bash
# Run integration tests before commit
python tests/test_frontend_integration.py || {
    echo "Integration tests failed - fix before committing"
    exit 1
}
```

## Success Metrics

**All tests passing indicates:**
- ✅ Frontend can communicate with API server
- ✅ Authentication works across all protocols  
- ✅ MCP conversational intelligence is active
- ✅ AI responses include real civic data
- ✅ Data pipeline is functioning end-to-end
- ✅ CORS is properly configured
- ✅ API response structures match frontend expectations

## Future Enhancements

- **Automated browser testing** with Selenium/Playwright
- **Performance tests** for conversation response times
- **Error recovery tests** for network failures
- **Mobile browser compatibility** testing
- **Production environment** test variants

---

**Remember:** These tests were created from real debugging sessions. They catch the exact issues that cause frontend-backend integration failures in development.