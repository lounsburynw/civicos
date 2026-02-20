# Visual Review — Browser Extension UX

Take fresh screenshots of the browser extension's CivicReadOnlyPulse component at all three jurisdiction levels and review them for UX quality.

## Usage

```
/visual-review [mode]
```

**Modes:**
- (default) - Full review: take screenshots, review UX, compare against baselines
- `review` - UX review only (no baseline comparison)
- `diff` - Baseline diff only (no subjective review)

## Instructions

### Step 1: Generate Fresh Screenshots

Run Playwright to capture current state:

```bash
cd apps/civicos-extension && npx playwright test --update-snapshots 2>&1
```

If tests fail to start, ensure the harness builds:
```bash
cd apps/civicos-extension && npm run harness  # Manual check at localhost:5199
```

### Step 2: Read Screenshots

Read all 6 screenshot images using the Read tool:

```
apps/civicos-extension/tests/visual/__screenshots__/visual.spec.ts/city-pulse.png
apps/civicos-extension/tests/visual/__screenshots__/visual.spec.ts/state-pulse.png
apps/civicos-extension/tests/visual/__screenshots__/visual.spec.ts/federal-pulse.png
apps/civicos-extension/tests/visual/__screenshots__/visual.spec.ts/state-take-action.png
apps/civicos-extension/tests/visual/__screenshots__/visual.spec.ts/federal-urgency-badges.png
apps/civicos-extension/tests/visual/__screenshots__/visual.spec.ts/city-sections.png
```

### Step 3: UX Review (skip if mode=diff)

Review each screenshot for these categories:

**Layout & Spacing**
- Card padding and margins are consistent
- Section spacing is uniform
- No content clipping at 380px width
- Breadcrumb nav fits without overflow

**Color & Contrast**
- Text readable against dark background (#171717)
- Badge colors match semantic meaning (blue=info, yellow=action, red=urgent, green=success)
- "Take Action" focal points have yellow (#f59e0b) accent consistently
- No stray colors or inconsistent styling between levels

**Typography**
- Section headers are uppercase, consistent weight
- Card titles are readable (14px, weight 500)
- Meta text is subdued but legible
- Count badges are aligned with section titles

**Component Consistency**
- Meeting cards look the same across city and state
- Voice buttons and comment threads are aligned
- Urgency badges scale correctly (urgent-critical red, urgent-soon yellow, urgent-normal blue)
- Topic tags and status tags have consistent padding

**Level-Specific Checks**
- City: Meeting cards have calendar icons, agenda items show meeting_title + project_type badge
- State: "Take Action" group with yellow trim is prominent, topic grid is 2-column, Governor's desk has leverage callout
- Federal: Comment period cards show agency, deadline badge, topic tags, "Submit Official Comment" green button

### Step 4: Baseline Diff (skip if mode=review)

Run the comparison test:

```bash
cd apps/civicos-extension && npx playwright test 2>&1
```

If tests fail, Playwright generates diff images. Read the test output and report:
- Which screenshots changed
- Whether the changes are intentional or regressions

### Step 5: Report

Output a structured report:

```
## Visual Review: Browser Extension

### Screenshot Status
- [ ] city-pulse.png — [OK/CHANGED/ISSUE]
- [ ] state-pulse.png — [OK/CHANGED/ISSUE]
- [ ] federal-pulse.png — [OK/CHANGED/ISSUE]
- [ ] state-take-action.png — [OK/CHANGED/ISSUE]
- [ ] federal-urgency-badges.png — [OK/CHANGED/ISSUE]
- [ ] city-sections.png — [OK/CHANGED/ISSUE]

### UX Issues Found
[List issues with severity: critical/minor/nit]

### Baseline Status
[PASS — all match / FAIL — N screenshots changed]

### Recommendations
[Actionable fixes if any issues found]
```

## Harness Details

The visual harness renders `CivicReadOnlyPulse` (from `@civicos/components`) with mock data at 380px width (Chrome side panel width). It uses a standalone Vite server (`vite.harness.config.ts`) separate from the extension's build-only config.

**Manual inspection:** `npm run harness` then visit:
- `http://localhost:5199/?level=city`
- `http://localhost:5199/?level=state`
- `http://localhost:5199/?level=federal`

**Mock data:** Fixed timestamp prevents drift. Located in `tests/visual/mock-data.ts`.

## When to Use

- After any CSS/style changes to CivicReadOnlyPulse or child components
- After modifying SidePanel.svelte panel chrome or breadcrumb styles
- Before committing extension UX changes
- As part of `/review` workflow for frontend track work
