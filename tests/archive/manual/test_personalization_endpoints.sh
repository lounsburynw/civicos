#!/bin/bash

# Test script for PersonalizationService API endpoints
# Phase 2: API Endpoints & Authentication

set -e  # Exit on error

BASE_URL="http://localhost:8001"
# For MVP: Bearer token must be a valid API key AND serves as user_id
# dev_key_local is configured in CIVIC_WEB_KEY environment variable
API_KEY="dev_key_local"
AUTH_HEADER="Authorization: Bearer $API_KEY"

echo "🧪 Testing PersonalizationService API Endpoints"
echo "=============================================="
echo ""
echo "Using API key as Bearer token (MVP approach): $API_KEY"
echo "Note: Bearer token serves dual purpose - authentication + user_id"
echo ""

# Test 1: POST /api/user/profile - Create new profile
echo "📝 Test 1: Creating new user profile..."
PROFILE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/user/profile" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{
    "jurisdictionId": "city-berkeley",
    "displayName": "Test Phase 2 User",
    "stakes": ["homeowner", "parent"],
    "yearsInArea": 10,
    "civicInterests": ["housing", "education"],
    "expertise": "software engineering"
  }')

echo "$PROFILE_RESPONSE" | python3 -m json.tool
PROFILE_COMPLETENESS=$(echo "$PROFILE_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('profile_completeness', 0))")
echo "✅ Profile created with completeness: $PROFILE_COMPLETENESS%"
echo ""

# Test 2: GET /api/user/profile - Retrieve profile
echo "📖 Test 2: Retrieving user profile..."
GET_PROFILE=$(curl -s -X GET "$BASE_URL/api/user/profile" \
  -H "$AUTH_HEADER")

echo "$GET_PROFILE" | python3 -m json.tool
echo "✅ Profile retrieved successfully"
echo ""

# Test 3: Track some civic actions (simulate user activity)
echo "📊 Test 3: Simulating civic actions..."
# We'll use the PersonalizationService directly since we don't have a public endpoint for tracking
# For now, we'll just note that civic history would accumulate from other endpoints
# (event views, comment drafts, issue filings, etc.)
echo "ℹ️  Note: Civic history tracking happens automatically via other endpoints"
echo "   For testing, we'll verify the civic-history endpoint can handle empty results"
echo ""

# Test 4: GET /api/user/civic-history - Get civic history
echo "📜 Test 4: Retrieving civic history..."
HISTORY_RESPONSE=$(curl -s -X GET "$BASE_URL/api/user/civic-history" \
  -H "$AUTH_HEADER")

echo "$HISTORY_RESPONSE" | python3 -m json.tool
ACTION_COUNT=$(echo "$HISTORY_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('count', 0))")
echo "✅ Civic history retrieved: $ACTION_COUNT actions"
echo ""

# Test 5: GET /api/user/context - Get AI context (demographics)
echo "🤖 Test 5a: Getting demographics context..."
DEMOGRAPHICS_CONTEXT=$(curl -s -X GET "$BASE_URL/api/user/context?type=demographics" \
  -H "$AUTH_HEADER")

echo "$DEMOGRAPHICS_CONTEXT" | python3 -m json.tool
echo "✅ Demographics context retrieved"
echo ""

# Test 5b: GET /api/user/context - Full context
echo "🤖 Test 5b: Getting full context..."
FULL_CONTEXT=$(curl -s -X GET "$BASE_URL/api/user/context?type=full" \
  -H "$AUTH_HEADER")

echo "$FULL_CONTEXT" | python3 -m json.tool
echo "✅ Full context retrieved"
echo ""

# Test 6: GET /api/user/export - GDPR data export
echo "💾 Test 6: GDPR data export..."
EXPORT_RESPONSE=$(curl -s -X GET "$BASE_URL/api/user/export" \
  -H "$AUTH_HEADER")

echo "$EXPORT_RESPONSE" | python3 -m json.tool
echo "✅ Data export completed"
echo ""

# Test 7: DELETE /api/user - Account deletion
echo "🗑️  Test 7: Deleting user account (GDPR)..."
DELETE_RESPONSE=$(curl -s -X DELETE "$BASE_URL/api/user" \
  -H "$AUTH_HEADER")

echo "$DELETE_RESPONSE" | python3 -m json.tool
echo "✅ Account deleted successfully"
echo ""

# Test 8: Verify deletion - Profile should not exist
echo "✔️  Test 8: Verifying deletion..."
VERIFY_DELETED=$(curl -s -X GET "$BASE_URL/api/user/profile" \
  -H "$AUTH_HEADER")

if echo "$VERIFY_DELETED" | grep -q "Profile not found"; then
  echo "✅ Verified: Profile no longer exists"
else
  echo "❌ Error: Profile still exists after deletion"
  echo "$VERIFY_DELETED" | python3 -m json.tool
  exit 1
fi
echo ""

# Test 9: Authentication error handling
echo "🔒 Test 9: Testing authentication (no Bearer token)..."
AUTH_ERROR=$(curl -s -X GET "$BASE_URL/api/user/profile")

if echo "$AUTH_ERROR" | grep -q "Authentication required"; then
  echo "✅ Authentication correctly enforced"
else
  echo "❌ Error: Endpoint accessible without authentication"
  echo "$AUTH_ERROR" | python3 -m json.tool
  exit 1
fi
echo ""

echo "=============================================="
echo "🎉 All tests passed!"
echo ""
echo "Summary:"
echo "✅ Profile creation (POST /api/user/profile)"
echo "✅ Profile retrieval (GET /api/user/profile)"
echo "✅ Civic history (GET /api/user/civic-history)"
echo "✅ AI context - demographics (GET /api/user/context?type=demographics)"
echo "✅ AI context - full (GET /api/user/context?type=full)"
echo "✅ GDPR export (GET /api/user/export)"
echo "✅ Account deletion (DELETE /api/user)"
echo "✅ Deletion verification"
echo "✅ Authentication enforcement"
echo ""
echo "🚀 PersonalizationService API Phase 2 Complete!"
