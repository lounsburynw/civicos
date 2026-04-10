# Recommended: MCP OAuth 2.0 Provider (`mcp_oauth_provider`)

**Priority:** P0
**Area:** distribution
**Date:** 2026-04-10

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

After a month of ingestion work, CivicOS has 23 jurisdictions, 10 platform clients, and 40+ MCP tools deployed on Modal. The launch checklist is 95% complete (143/151). The strategic decision (see `docs/public/decisions/distribution_pivot.md`) is to prioritize distribution over billing -- get users first, then decide billing model based on real usage data.

The MCP server is deployed and working but only accessible via manually-configured Bearer tokens. OAuth enables Claude.ai web + mobile users to connect via Settings > Connectors in 2 clicks.

## Problem

No OAuth provider on the MCP server. Users must:
1. Buy an API key (Stripe not even wired yet)
2. Copy the key into Claude Desktop config manually
3. Only works in Claude Desktop, not Claude.ai web or mobile

## Key Files

- `apps/civicos-mcp/modal_app.py` -- Modal deployment entry point (where OAuth endpoints need to live)
- `apps/civicos-mcp/server.py` -- Container/FastAPI deployment (reference for routing patterns)
- `apps/civicos-mcp/README.md:94-112` -- Existing OAuth plan and callback URL
- `apps/civicos-mcp/api_key_middleware.py` -- Existing API key auth (Bearer tokens stay alongside OAuth)
- `docs/internal/launch-readiness-spec.md:366-401` -- Auth strategy discussion
- `docs/private/decisions/privacy_preserving_billing.md` -- Billing architecture (context, not blocking)

## Suggested Approach

1. **Research current MCP OAuth spec** -- The spec is evolving. Check `modelcontextprotocol.io` for the latest on OAuth 2.1 for remote MCP servers. Claude.ai expects OAuth callback at `https://claude.ai/api/mcp/auth_callback`.

2. **Implement OAuth 2.0 provider on Modal** -- Add `/oauth/authorize`, `/oauth/token`, `/.well-known/oauth-authorization-server` endpoints to `modal_app.py`. The provider issues session tokens after OAuth flow.

3. **Map OAuth sessions to access tier** -- OAuth-authenticated users get a "free" tier (generous rate limits, e.g. 50 queries/day). Existing Bearer token API keys continue to work at their configured tiers. No Stripe needed.

4. **Deploy and test with Claude.ai** -- Add connector URL in Claude.ai Settings, verify OAuth flow end-to-end, confirm tools appear and work.

5. **Update README** -- Document the connector setup for end users.

## Design Notes

- Bearer token auth (existing) MUST continue working alongside OAuth. Don't break existing API key users.
- OAuth tokens are session-based, not tied to Stripe. Free tier only.
- Rate limiting for OAuth sessions can use the existing per-key rate limiting infrastructure with a synthetic "free-tier" key.
- The MCP spec may have specific requirements for the OAuth flow -- research before implementing.

## Success Criteria

- [ ] OAuth 2.0 endpoints added to Modal MCP deployment
- [ ] Claude.ai web connector flow works end-to-end (authorize -> tools available)
- [ ] Free-tier rate limiting applied to OAuth sessions
- [ ] Existing Bearer token auth unaffected
- [ ] README updated with connector setup instructions
- [ ] New P0 promoted

## Open PRs

None.
