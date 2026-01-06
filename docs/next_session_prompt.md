# Recommended: chatgpt_gpt

**Priority:** P0
**Area:** pilot_validation > distribution_channels
**Date:** 2026-01-06

> This is recommended context from Session 484. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 484 completed `extraction_versioning` - all extracted records now track which version of civic-extraction produced them (enables selective re-extraction when extractors improve).

The next P0 is `chatgpt_gpt` - creating a Custom GPT in ChatGPT's GPT store for the San Rafael pilot demo. This is the primary distribution channel for demonstrating Civic to the city clerk.

## Recommended Task

Create a ChatGPT Custom GPT called "Civic San Rafael" that uses Actions to call the Civic API. The GPT should answer questions about San Rafael city council meetings, decisions, and municipal code.

## Key Files

- `packages/civic-services/src/civic_services/api/civic_api_integrated.py` - REST API server
- `apps/civic-mcp/` - MCP server (pattern reference for tool definitions)
- `docs/critical/MCP_INTEGRATION_STRATEGY.md` - API design guidance
- `.env` - API keys and configuration

## Suggested Approach

1. **Verify Civic API is accessible:**
   ```bash
   ./scripts/dev.sh api  # Start API server
   curl http://localhost:8001/health
   ```

2. **Create OpenAPI spec for GPT Actions:**
   - Define endpoints: `/whats_next`, `/what_happened`, `/what_applies`
   - Include authentication (API key header)
   - Document response schemas

3. **Write GPT system prompt:**
   - Focus on San Rafael city government
   - Emphasize accuracy - cite sources, link to original documents
   - Avoid speculation on political outcomes
   - Direct users to web frontend for detailed analysis

4. **Create Custom GPT in ChatGPT:**
   - Go to https://chat.openai.com/gpts/editor
   - Configure Actions with OpenAPI spec
   - Add system prompt
   - Set conversation starters

5. **Test thoroughly:**
   - Ask about upcoming meetings
   - Query past decisions on housing
   - Check for hallucinations
   - Verify links work

## Dependencies

Per pilot.json, this item has dependencies:
- OpenAPI spec for Civic API endpoints
- GPT system prompt
- Example conversations

## Tests to Run

```bash
# Ensure API works before creating GPT
./scripts/dev.sh api
curl -X POST http://localhost:8001/whats_next -H "Content-Type: application/json" -d '{"jurisdiction_id": "city-san-rafael"}'
```

## Success Criteria

- [ ] Custom GPT "Civic San Rafael" created and accessible
- [ ] GPT can answer "What's happening this week at San Rafael City Council?"
- [ ] GPT can answer "What decisions were made about housing in the last 6 months?"
- [ ] GPT cites sources and provides links to original documents
- [ ] No obvious hallucinations in standard queries
- [ ] Demo-ready for city clerk presentation
- [ ] pilot.json updated: chatgpt_gpt -> ready
