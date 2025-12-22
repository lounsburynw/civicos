# Recommended: User Identity in Messages

**Priority:** P0 (IMMEDIATE)
**Area:** frontend_refinement > social_features
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 335 completed `changelog_maintained` - updated CHANGELOG.md with comprehensive release documentation and maintenance guide.

Next priority is showing proper user identity in coordination thread messages. Currently, MessageBubble.vue uses a simplistic `formatUserId()` that just extracts the first part before underscore/hash, and ThreadArtifact.vue has a hardcoded `userId = 'demo_user'`.

## Recommended Task

Display proper user names/display names in coordination thread messages instead of raw user IDs.

## Key Files

- `apps/civic-workspace/src/components/workspace/MessageBubble.vue:147-152` - `formatUserId()` needs real user lookup
- `apps/civic-workspace/src/components/workspace/ThreadArtifact.vue:32` - hardcoded `userId = 'demo_user'`
- `apps/civic-workspace/src/components/workspace/CoordinationChat.vue:64` - uses `formatUserId()` for reply context
- `apps/civic-workspace/src/stores/profile.ts` - profile store (may have user data)
- `apps/civic-workspace/src/composables/useAvatars.ts` - already handles avatar URLs

## Suggested Approach

1. **Check existing user profile data:**
   - Review `stores/profile.ts` for current user data
   - Review ThreadMessage type for user info in messages

2. **Implement user lookup:**
   - Option A: Add display_name to ThreadMessage from backend
   - Option B: Create a composable `useUserDisplay()` to look up/cache user names

3. **Update components:**
   - Replace `formatUserId()` with proper display name lookup
   - Ensure "You" still works for current user
   - Handle fallback gracefully for unknown users

4. **Test in running app:**
   ```bash
   ./scripts/dev.sh
   # Open http://localhost:5173, navigate to a thread
   ```

## Success Criteria

- [ ] Messages show user display names instead of raw IDs
- [ ] Current user messages still show "You"
- [ ] Avatar and name are consistent
- [ ] pilot.json updated to mark user_identity_in_messages as ready

## Pilot Progress

- 139/161 items ready (86%)
- 22 items remaining
