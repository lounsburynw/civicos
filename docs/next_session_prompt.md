# Recommended: Free Tier Rate Limiting (`free_tier_rate_limiting`)

**Priority:** P0
**Area:** distribution
**Date:** 2026-04-11

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session completed `implement_captions_transcription_mode` (commits `c41b23d3`, `e1e001e0`). YouTube auto-captions now work as a free transcription alternative to AssemblyAI. The distribution pivot (see memory) prioritizes getting users onto the platform. OAuth is already deployed and working (`mcp_oauth_provider` is done), but OAuth sessions have no per-session rate limiting — they fall through to global IP-based limits. This item adds per-session quotas so the free tier is well-defined and usage patterns can be collected before billing decisions.

## Recommended Task

Implement per-OAuth-session rate limiting for the MCP server free tier. OAuth-authenticated users should get a generous daily quota (e.g., 50 queries/day) tracked per session, distinct from the per-minute IP-based limits that already exist.

## Key Files

- `apps/civicos-mcp/modal_mcp.py:571-648` — `BearerAuthMiddleware` handles auth. Line 611-614 sets `_mcp_request_tier` to `"free"` for OAuth tokens but does NOT call rate limiter
- `apps/civicos-mcp/api_key_middleware.py:26-59` — `SlidingWindowRateLimiter` (in-memory sliding window). Per-key limits already work for API keys
- `apps/civicos-mcp/api_key_middleware.py:140-180` — Rate limit check for API keys, uses `f"key:{key_info.key_id}"` as limiter key
- `apps/civicos-mcp/oauth.py` — OAuth provider, stateless `cos_*` tokens (HMAC-signed, 7-day TTL)
- `apps/civicos-mcp/api_keys.py:23-30` — Tier rate limit constants (open=30/min, free=60/min)
- `apps/civicos-mcp/tests/test_oauth.py` — Existing OAuth tests

## Suggested Approach

1. **Add daily quota tracking** — Extend `SlidingWindowRateLimiter` or add a `DailyQuotaLimiter` that tracks per-session daily counts. Key: `f"oauth:{session_id}"` (extract from `cos_*` token). In-memory dict with daily reset is fine for now (Modal containers restart frequently).

2. **Wire into MCP request path** — The rate limiter currently only gates REST API paths, not MCP tool calls. Add rate limit check in `BearerAuthMiddleware` or in `_wrap_handler` (the tool call wrapper in `modal_mcp.py`) for OAuth-authenticated requests.

3. **Define free tier limits** — Something like 50 queries/day + 10 req/min burst. The exact numbers aren't critical — the goal is collecting usage patterns, not blocking users. Log when limits are approached.

4. **Return proper rate limit response** — MCP protocol should return an error result when rate limited, not silently drop. Include retry-after hint.

5. **Usage logging** — Log per-session query counts for billing model analysis. This is the primary value — understanding usage patterns.

## Tests to Run

```bash
# Existing OAuth tests
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_oauth.py -v --override-ini="addopts="

# Smoke tests
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] OAuth sessions have per-session daily quota (e.g., 50/day)
- [ ] Rate limit enforced in MCP tool call path, not just REST
- [ ] Proper error returned when rate limited (not silent drop)
- [ ] Usage counts logged per session for billing analysis
- [ ] Existing API key rate limiting unchanged
- [ ] OAuth tests updated to cover rate limiting
- [ ] A new P0 assigned before session end

## Pre-existing test failures (NOT regressions)

- `test_coordination_tools.py`: 5 failures (broadcast_voice schema drift, registry count drift)
- `test_initiative_tools.py::test_connection_error_handled`: relay is reachable, premise broken

These are separate cleanup items — 6 pre-existing failures total, stable across sessions.

## Open PRs

None.

## Not in scope

- Stripe billing integration (deferred per distribution pivot)
- Token purchase UI (parked)
- Persistent rate limit storage (in-memory is fine for now)
- Admin dashboard for usage metrics (future item)
