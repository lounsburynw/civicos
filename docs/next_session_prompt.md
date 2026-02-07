# Next Session: Build Chat Action Card for Comment Posting (Option 1)

## What Was Done (2026-02-06)

### 1. Finalized Comment Board Handoff
- Ran SQL migration `scripts/sql/add_comments.sql` on relay DB (coordination_comments table)
- Committed all Kind 30803 comment code (models, crypto, storage, endpoints, migration)
- Commit: `206fb13`

### 2. Fixed Comment Modal Z-Index Bug
- Modal was trapped in sidebar stacking context, chat elements bled through
- Replaced custom overlay with Open WebUI's `Modal` component (portals to `document.body`, z-9999)

### 3. Added Comment Viewing
- Added `getComments()` API function in `civic.ts` (GET /comments/{entity})
- Added `Comment` interface to civic.ts
- Modal showed existing comments above textarea

### 4. Replaced Modal with Inline Collapsible Thread
- Per user feedback, replaced modal with forum-style inline thread under each agenda item
- Uses `svelte/transition:slide` for collapse/expand animation
- "Comment" button toggles thread open/closed, shows count when comments exist
- Thread loads comments on expand, has inline compose textarea + "Post" button
- Per-entity state tracked in Maps/Sets (openThreads, threadComments, threadDrafts, etc.)

### 5. Added Comment Endpoints to Coordination Router (for Modal deployment)
- **Root cause of "count flashes then disappears"**: Modal relay uses `coordination.py` router from civicos-services, NOT relay's `app.py`
- Added to `packages/civicos-services/src/civicos_services/servers/routers/coordination.py`:
  - `_get_comment_storage()` helper
  - `POST /coordination/comment` (submit signed comment)
  - `GET /coordination/comments/{entity}` (list comments)
  - `GET /coordination/comment/counts/{entity}` (get count)
  - Request/response models: SubmitCommentRequest, CommentResponse, CommentCountResponse
- Redeployed relay: `modal deploy apps/civicos-relay/modal_relay.py` - verified working

### 6. Renamed "Write Comment" to "Draft Public Comment"
- Renamed handler to `handleDraftComment()`
- Opening thread + sending AI prompt simultaneously

### 7. Designed Chat Action Card (Option 1) - NOT YET BUILT
- Ran simulated user panel - unanimous preference for chat-driven comment posting
- Explored Open WebUI rendering pipeline thoroughly (see below)
- Was in plan mode designing implementation when context ran out

## REMAINING WORK: Build Option 1 (Chat Action Card)

### Concept
When AI drafts a public comment, it outputs a ` ```civic-comment ` code block with JSON. The frontend intercepts this and renders a PostCommentCard with a "Post to Comment Board" button. User reviews and clicks Post - card handles client-side signing and submission.

### Rendering Pipeline (verified)
```
ResponseMessage.svelte → ContentRenderer.svelte → Markdown.svelte
  → MarkdownTokens.svelte (line 104-129) → CodeBlock.svelte
```

### Hook Point
`MarkdownTokens.svelte` line 104: intercept `token.lang === 'civic-comment'` before CodeBlock dispatch.

### Implementation Steps

1. **Create `PostCommentCard.svelte`** in `~/projects/civicos-openwebui/src/lib/components/civic/`
   - Parse JSON from code block: `{ entity, text, item_title, item_number, meeting, stance? }`
   - Render: item title/number, comment text preview, stance badge, "Post to Comment Board" button
   - On click: call `submitComment()` from `civic.ts` (handles signing)
   - States: idle → posting → posted/error
   - Dark mode support

2. **Modify `MarkdownTokens.svelte`** (minimal change)
   - Import PostCommentCard
   - Add branch before CodeBlock: `{:else if token.type === 'code' && token?.lang === 'civic-comment'}`
   - Render `<PostCommentCard data={token.text} />`

3. **Update `handleDraftComment()` in `CityPulse.svelte`**
   - Modify the AI prompt to instruct output in civic-comment code block format:
     ```
     Output your draft as a civic-comment block:
     ```civic-comment
     {"entity": "agenda-item:ID", "text": "...", "item_title": "...", "item_number": "...", "meeting": "..."}
     ```
     ```

4. **Cross-component count update** (optional, can defer)
   - After posting from chat card, CityPulse comment counts should update
   - Could use a Svelte writable store that both components subscribe to

### Key Files
| File | Repo | Action |
|------|------|--------|
| `src/lib/components/civic/PostCommentCard.svelte` | civicos-openwebui | CREATE |
| `src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte` | civicos-openwebui | EDIT (add if-branch at line 104) |
| `src/lib/components/civic/CityPulse.svelte` | civicos-openwebui | EDIT (update prompt in handleDraftComment) |
| `src/lib/apis/civic.ts` | civicos-openwebui | Already has submitComment() - reuse as-is |

### Signing Flow (reuse from civic.ts)
`submitComment(entityId, commentText, jurisdiction, stance)` handles:
1. Gets/creates keypair from localStorage (`@noble/secp256k1`)
2. Builds Nostr Kind 30803 event with tags [d, j, stance?]
3. SHA-256 hash → BIP-340 Schnorr sign
4. POST to relay

### Reference: Existing Patterns
- Citation rendering in `MarkdownInlineTokens.svelte` (line 111-116) - custom token → custom component
- `DecisionCard.svelte` - existing civic card component pattern
- `Modal.svelte` - shows how Open WebUI components portal/interact

## Uncommitted Changes

### civicos repo (this repo)
- `packages/civicos-services/src/civicos_services/servers/routers/coordination.py` - comment endpoints added (UNCOMMITTED)

### civicos-openwebui repo (~/projects/civicos-openwebui)
- `src/lib/apis/civic.ts` - Comment interface, getComments()
- `src/lib/components/civic/CityPulse.svelte` - inline thread, Draft Public Comment, Modal removed
- ALL UNCOMMITTED - commit both repos before starting new work

## P0 Status
- `civic_dashboard_mvp` remains P0 in pilot.json
- The chat action card is part of dashboard MVP (engagement ladder: awareness → participation)
- After building the card, the remaining dashboard work is visualization primitives (calendar heatmap, decision flow, issue geography)
