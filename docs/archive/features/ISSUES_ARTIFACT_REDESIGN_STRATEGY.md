# Issues Artifact Redesign Strategy
## Aligning with Discussion Aesthetic Excellence

**Date**: 2025-10-25
**Status**: Strategic Planning - Ready for Implementation
**Context**: Post-Discussion polish (Sessions 32-35) - Discussion aesthetic is the target

**Screenshots**:
- Target aesthetic: Discussion artifact (Screenshot 2025-10-25 at 7.08.03 AM)
- Current Issues artifact: Screenshots 7.05.46 AM, 7.06.24 AM, 7.06.39 AM, 7.06.57 AM

---

## Executive Summary

**Current State**: The Discussion artifact (ThreadArtifact.vue) has achieved professional, polished aesthetic through Sessions 32-35:
- Clean minimal borders with good whitespace
- Subtle visual hierarchy with consistent spacing
- Professional lucide-vue-next icons (no emoji clutter)
- Elegant threading with blue vertical lines
- Consistent rounded buttons and chips
- Solarized color palette throughout
- Polished collapse affordances

**Problem**: The Issues Artifact (ComplaintArtifact.vue) has significant aesthetic inconsistencies:
- Heavy blue borders (especially "PROGRESS & ACTIONS" box)
- Inconsistent button styles (filled blue, outlined, green "Following")
- Emoji indicators (⭐⭐⭐) feel unprofessional
- Clunky "System" badges look like debug UI
- Timeline icons are basic (just checkmarks)
- Card designs lack polish (meetings, similar issues)
- Action buttons grid doesn't match Discussion aesthetic
- Visual noise - everything competing for attention

**Goal**: Bring Issues Artifact up to the same aesthetic quality as Discussion artifact - professional, clean, consistent with Solarized design system.

---

## Design Principles (from Discussion Success)

### 1. **Minimal Borders**
- Use subtle dividers instead of heavy border boxes
- Let whitespace create separation
- Reserve borders for interactive elements (hover states)

### 2. **Consistent Iconography**
- lucide-vue-next icons only (no emoji)
- Consistent sizing and spacing
- Semantic color usage (base01 for muted, blue for interactive)

### 3. **Typography Hierarchy**
- Bold weights for section headers
- Medium weight for primary content
- Regular weight for metadata
- Italics for contextual information

### 4. **Solarized Color Palette**
- Blue (base0/blue) for interactive elements
- base03 for subtle backgrounds
- base01 for muted text/icons
- Green/yellow/red only for semantic status (not decorative)

### 5. **Whitespace & Rhythm**
- Consistent spacing scale (8px, 12px, 16px, 24px)
- Breathing room between sections
- Grouped related elements

### 6. **Interactive Feedback**
- Subtle hover states
- Clear active states
- Smooth transitions
- Cursor changes for draggable/clickable

---

## Issues Artifact Current Problems (Detailed Analysis)

### Section 1: Progress & Actions Box (Lines ~50-100)

**Current Issues**:
```vue
<!-- Heavy blue border box -->
<div style="border: 3px solid var(--blue); border-radius: 8px; padding: 16px;">
  <h3>🎯 PROGRESS & ACTIONS</h3>

  <!-- Status display with emoji -->
  <div>Status: Matched</div>

  <!-- Action buttons - inconsistent styling -->
  <button class="primary">📞 File 311 Report</button>
  <button class="primary">📧 Email Department</button>
  <button class="secondary">🔍 Check 311 Status</button>
  <button class="secondary">🔗 Link to Meeting</button>

  <!-- Emoji indicators -->
  <div>⭐ 3 filed 311</div>
  <div>⭐⭐ 2 emailed</div>
  <div>💬 1 discussing</div>
</div>
```

**Problems**:
1. Heavy border creates visual weight mismatch
2. Emoji in heading not scalable
3. Action buttons use emoji instead of icons
4. Grid layout doesn't prioritize actions
5. Emoji indicators feel gamified/unprofessional
6. No hierarchy - everything equally loud

### Section 2: Issue Description (Lines ~100-130)

**Current State**: This section is actually pretty good!
```vue
<h2>Issue Description</h2>
<blockquote style="border-left: 4px solid var(--blue);">
  {{ complaint.description }}
</blockquote>
```

**Minor improvements needed**:
- Consistent spacing with other sections
- Typography sizing matches Discussion

### Section 3: Coordination Chat Collapsible (Lines ~130-150)

**Current Issues**:
```vue
<div class="collapsible-header">
  💬 Coordination Chat (1 member) ▼
</div>
```

**Problems**:
1. Emoji instead of lucide icon
2. Text-based disclosure triangle
3. Doesn't match Discussion collapsible pattern

### Section 4: Relevant Civic Meetings (Lines ~150-250)

**Current Issues**:
```vue
<div class="meeting-card">
  <h4>4000% match</h4>
  <p style="font-style: italic;">
    1 keyword matches, agenda item: Contract Amendment...
  </p>
  <a href="#">View Meeting →</a>
</div>
```

**Problems**:
1. Card borders too subtle
2. Match percentage not styled as badge/chip
3. Inconsistent with Discussion thread cards
4. No hover states
5. Typography hierarchy unclear

### Section 5: Similar Issues from Neighbors (Lines ~250-300)

**Current Issues**:
```vue
<div class="similar-issue-card">
  📄 Similar Housing issue
  <a href="#">View →</a>
</div>
```

**Problems**:
1. Emoji icon
2. Too plain - no visual weight
3. No metadata (location, date, status)
4. Doesn't feel like related content

### Section 6: Government Response Timeline (Lines ~300-400)

**Current Issues**:
```vue
<div class="timeline">
  <div class="timeline-item">
    ☑️ Filed
    <p>Complaint filed</p>
    <span>14h ago</span>
  </div>

  <div class="timeline-item">
    🎯 Matched to Event
    <p>Matched to event (40% match)</p>
    <span class="system-badge">System</span>
    <span>14h ago</span>
  </div>

  <div class="timeline-item">
    🔗 Manually Linked
    <p>Automatically following matched event: *Community & Economic...</p>
    <span class="system-badge">System</span>
    <span>14h ago</span>
  </div>
</div>
```

**Problems**:
1. Emoji icons instead of professional icons
2. "System" badges are clunky debug UI
3. No visual connection between timeline items
4. Different from Discussion threading aesthetic
5. Timeline should use vertical lines like Discussion
6. Action buttons at bottom don't feel integrated

### Section 7: What You Can Do (Lines ~400-450)

**Current Issues**:
```vue
<div class="action-buttons-grid">
  <button class="primary">📅 View Upcoming Meeting</button>
  <button class="secondary">🔗 Link to Another Meeting</button>
  <button class="secondary">👥 Form Community Group</button>
  <button class="secondary">📢 Share with Neighbors</button>
</div>
```

**Problems**:
1. Emoji in buttons
2. Grid layout doesn't prioritize
3. Inconsistent with Discussion button patterns
4. All outlined buttons at top, but different style here

### Section 8: Following Button (Bottom)

**Current Issues**:
```vue
<button class="following-button" style="background: var(--green);">
  Following ✓
</button>
<span>👥 1 neighbor following this</span>
```

**Problems**:
1. Green color breaks Solarized palette
2. Checkmark emoji instead of icon
3. Should be blue to match Discussion
4. Person emoji in follower count

---

## Redesign Plan (Priority Order)

### Phase 1: Progress & Actions Section (Highest Impact)

**Goal**: Remove heavy border, clean up action hierarchy, professional icons

**Before**:
- Heavy blue border box
- Emoji indicators (⭐⭐⭐)
- Grid of action buttons with emoji
- Status display plain text

**After**:
```vue
<section class="progress-section">
  <!-- Subtle header with icon -->
  <div class="section-header">
    <Target class="section-icon" :size="20" />
    <h3>Progress & Actions</h3>
  </div>

  <!-- Status bar with subtle background -->
  <div class="status-bar">
    <div class="status-label">
      <CheckCircle2 :size="16" class="status-icon" />
      <span class="status-text">Matched to Events</span>
    </div>
    <span class="filed-date">Filed Today</span>
  </div>

  <!-- Primary actions (filled buttons) -->
  <div class="primary-actions">
    <button class="btn-primary">
      <Phone :size="16" />
      File 311 Report
    </button>
    <button class="btn-primary">
      <Mail :size="16" />
      Email Department
    </button>
  </div>

  <!-- Secondary actions (outlined) -->
  <div class="secondary-actions">
    <button class="btn-secondary">
      <Search :size="16" />
      Check 311 Status
    </button>
    <button class="btn-secondary">
      <Link :size="16" />
      Link to Meeting
    </button>
  </div>

  <!-- Community engagement stats (subtle) -->
  <div class="engagement-stats">
    <span class="stat">
      <Users :size="14" />
      3 filed 311
    </span>
    <span class="stat">
      <Mail :size="14" />
      2 emailed
    </span>
    <span class="stat">
      <MessageCircle :size="14" />
      1 discussing
    </span>
  </div>
</section>
```

**Styling**:
```css
.progress-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-icon {
  color: var(--base01);
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--base01);
  margin: 0;
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--base03);
  border-radius: 6px;
  margin-bottom: 16px;
}

.status-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-icon {
  color: var(--green);
}

.status-text {
  font-weight: 600;
  color: var(--base00);
}

.filed-date {
  font-size: 14px;
  color: var(--base01);
}

.primary-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.btn-primary {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--blue);
  color: var(--base3);
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-primary:hover {
  background: var(--blue-hover);
}

.secondary-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.btn-secondary {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  background: transparent;
  color: var(--blue);
  border: 1px solid var(--base02);
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-secondary:hover {
  background: var(--base03);
  border-color: var(--blue);
}

.engagement-stats {
  display: flex;
  gap: 16px;
  padding: 8px 0;
  border-top: 1px solid var(--base02);
}

.stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--base01);
}

.stat svg {
  color: var(--base01);
}
```

**Icons needed (lucide-vue-next)**:
- Target (section header)
- CheckCircle2 (status matched)
- Phone (file 311)
- Mail (email)
- Search (check status)
- Link (link meeting)
- Users (community stats)
- MessageCircle (discussing stat)

---

### Phase 2: Timeline Redesign (Match Discussion Quality)

**Goal**: Professional icons, vertical connection lines, remove "System" badges

**Before**:
- Emoji icons (☑️, 🎯, 🔗)
- "System" badges
- No visual connection between items
- Inconsistent with Discussion threading

**After**:
```vue
<section class="timeline-section">
  <div class="section-header">
    <Clock :size="20" class="section-icon" />
    <h3>Government Response</h3>
  </div>

  <p class="section-description">
    Track the lifecycle of your issue and any government responses.
  </p>

  <div class="timeline">
    <div class="timeline-item">
      <div class="timeline-marker">
        <CheckCircle2 :size="16" class="timeline-icon timeline-icon-success" />
      </div>
      <div class="timeline-content">
        <div class="timeline-header">
          <span class="timeline-title">Filed</span>
          <span class="timeline-time">14h ago</span>
        </div>
        <p class="timeline-description">Issue filed</p>
      </div>
    </div>

    <div class="timeline-item">
      <div class="timeline-marker">
        <Target :size="16" class="timeline-icon timeline-icon-info" />
      </div>
      <div class="timeline-content">
        <div class="timeline-header">
          <span class="timeline-title">Matched to Event</span>
          <span class="timeline-time">14h ago</span>
        </div>
        <p class="timeline-description">Matched to event (40% match)</p>
        <span class="timeline-badge">Auto-matched</span>
      </div>
    </div>

    <div class="timeline-item">
      <div class="timeline-marker">
        <Link :size="16" class="timeline-icon timeline-icon-info" />
      </div>
      <div class="timeline-content">
        <div class="timeline-header">
          <span class="timeline-title">Manually Linked</span>
          <span class="timeline-time">14h ago</span>
        </div>
        <p class="timeline-description">
          Automatically following matched event: Community & Economic Development Committee
        </p>
        <span class="timeline-badge">Auto-followed</span>
      </div>
    </div>
  </div>

  <!-- Action buttons integrated into timeline -->
  <div class="timeline-actions">
    <button class="btn-primary">
      <CheckCircle2 :size="16" />
      Mark as Resolved
    </button>
    <button class="btn-secondary">
      <AlertTriangle :size="16" />
      Escalate Issue
    </button>
  </div>
</section>
```

**Styling**:
```css
.timeline-section {
  margin-bottom: 24px;
}

.section-description {
  font-size: 14px;
  color: var(--base01);
  margin-bottom: 16px;
}

.timeline {
  position: relative;
  padding-left: 32px;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--base02);
}

.timeline-item {
  position: relative;
  padding-bottom: 24px;
}

.timeline-item:last-child {
  padding-bottom: 0;
}

.timeline-marker {
  position: absolute;
  left: -32px;
  top: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--base03);
  border-radius: 50%;
  border: 2px solid var(--base02);
}

.timeline-icon {
  color: var(--base01);
}

.timeline-icon-success {
  color: var(--green);
}

.timeline-icon-info {
  color: var(--blue);
}

.timeline-content {
  padding-left: 8px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}

.timeline-title {
  font-weight: 600;
  color: var(--base00);
}

.timeline-time {
  font-size: 12px;
  color: var(--base01);
}

.timeline-description {
  font-size: 14px;
  color: var(--base01);
  margin: 0 0 8px 0;
}

.timeline-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--base02);
  color: var(--base01);
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.timeline-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--base02);
}
```

**Icons needed**:
- Clock (section header)
- CheckCircle2 (filed, mark resolved)
- Target (matched)
- Link (manually linked)
- AlertTriangle (escalate)

---

### Phase 3: Meeting Cards Redesign (Match Discussion Thread Cards)

**Goal**: Consistent card styling with Discussion, better hierarchy, match badges

**Before**:
- Plain cards with minimal styling
- Match percentage not prominent
- Inconsistent hover states
- No visual weight

**After**:
```vue
<section class="meetings-section">
  <div class="section-header">
    <Calendar :size="20" class="section-icon" />
    <h3>Relevant Civic Meetings (2)</h3>
  </div>

  <p class="section-description">
    These civic meetings are addressing issues related to your issue.
    Attending or submitting comments can help bring attention to your concerns.
  </p>

  <div class="meeting-cards">
    <div class="meeting-card">
      <div class="meeting-header">
        <div class="match-badge match-badge-high">4000% match</div>
        <button class="meeting-view-btn">
          View Meeting
          <ArrowRight :size="14" />
        </button>
      </div>

      <p class="meeting-details">
        <span class="match-detail">1 keyword matches, agenda item:</span>
        Contract Amendment For Tenant Representa
        <span class="match-detail">, 2 keywords in agenda</span>
      </p>
    </div>

    <div class="meeting-card">
      <div class="meeting-header">
        <div class="match-badge match-badge-medium">2500% match</div>
        <button class="meeting-view-btn">
          View Meeting
          <ArrowRight :size="14" />
        </button>
      </div>

      <p class="meeting-details">
        <span class="match-detail">2 keyword matches, 1 keywords in agenda</span>
      </p>
    </div>
  </div>
</section>
```

**Styling**:
```css
.meetings-section {
  margin-bottom: 24px;
}

.meeting-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.meeting-card {
  padding: 16px;
  background: var(--base03);
  border: 1px solid var(--base02);
  border-radius: 6px;
  transition: all 0.15s;
}

.meeting-card:hover {
  border-color: var(--blue);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.meeting-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.match-badge {
  padding: 4px 10px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 4px;
}

.match-badge-high {
  background: var(--blue);
  color: var(--base3);
}

.match-badge-medium {
  background: var(--cyan);
  color: var(--base3);
}

.meeting-view-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: transparent;
  color: var(--blue);
  border: none;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s;
}

.meeting-view-btn:hover {
  color: var(--blue-hover);
}

.meeting-details {
  font-size: 14px;
  color: var(--base01);
  margin: 0;
}

.match-detail {
  font-style: italic;
  color: var(--base01);
}
```

**Icons needed**:
- Calendar (section header)
- ArrowRight (view meeting button)

---

### Phase 4: Similar Issues Cards Redesign

**Goal**: More visual weight, consistent with meeting cards, better metadata

**Before**:
- Emoji icon
- Too plain
- No metadata

**After**:
```vue
<section class="similar-issues-section">
  <div class="section-header">
    <FileText :size="20" class="section-icon" />
    <h3>Similar Issues from Neighbors (8)</h3>
  </div>

  <p class="section-description">
    Other residents in your jurisdiction have reported similar concerns.
    Consider joining forces to address this issue collectively.
  </p>

  <div class="similar-issue-cards">
    <div class="similar-issue-card">
      <div class="issue-icon">
        <FileText :size="18" />
      </div>
      <div class="issue-content">
        <span class="issue-title">Similar Housing issue</span>
        <div class="issue-meta">
          <span class="issue-location">Oakland</span>
          <span class="issue-date">3 days ago</span>
        </div>
      </div>
      <button class="issue-view-btn">
        View
        <ArrowRight :size="14" />
      </button>
    </div>

    <!-- More cards... -->
  </div>

  <button class="show-more-btn">
    Show 3 More
    <ChevronDown :size="16} />
  </button>
</section>
```

**Styling**:
```css
.similar-issues-section {
  margin-bottom: 24px;
}

.similar-issue-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.similar-issue-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--base03);
  border: 1px solid var(--base02);
  border-radius: 6px;
  transition: all 0.15s;
  cursor: pointer;
}

.similar-issue-card:hover {
  border-color: var(--blue);
  background: var(--base02);
}

.issue-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--base02);
  border-radius: 6px;
  color: var(--base01);
  flex-shrink: 0;
}

.issue-content {
  flex: 1;
  min-width: 0;
}

.issue-title {
  display: block;
  font-weight: 500;
  color: var(--base00);
  margin-bottom: 4px;
}

.issue-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--base01);
}

.issue-view-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: transparent;
  color: var(--blue);
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
}

.show-more-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 8px 16px;
  margin-top: 12px;
  background: transparent;
  color: var(--base01);
  border: 1px solid var(--base02);
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.show-more-btn:hover {
  background: var(--base03);
  border-color: var(--base01);
}
```

**Icons needed**:
- FileText (section header, issue icon)
- ArrowRight (view button)
- ChevronDown (show more)

---

### Phase 5: Coordination Chat Collapsible (Match Discussion Pattern)

**Goal**: Consistent with Discussion collapsible sections

**Before**:
- Emoji icon
- Text-based disclosure triangle

**After**:
```vue
<div class="collapsible-section" :class="{ 'is-expanded': isCoordinationExpanded }">
  <button
    class="collapsible-header"
    @click="isCoordinationExpanded = !isCoordinationExpanded"
  >
    <ChevronRight
      :size="16"
      class="collapse-icon"
      :class="{ 'is-rotated': isCoordinationExpanded }"
    />
    <MessageCircle :size="18" class="section-icon" />
    <span class="section-title">Coordination Chat</span>
    <span class="member-count">(1 member)</span>
  </button>

  <div v-if="isCoordinationExpanded" class="collapsible-content">
    <CoordinationChat :complaint-id="complaintId" />
  </div>
</div>
```

**Styling**:
```css
.collapsible-section {
  margin-bottom: 16px;
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 12px 16px;
  background: var(--base03);
  border: 1px solid var(--base02);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.collapsible-header:hover {
  background: var(--base02);
  border-color: var(--base01);
}

.collapse-icon {
  color: var(--base01);
  transition: transform 0.2s;
}

.collapse-icon.is-rotated {
  transform: rotate(90deg);
}

.section-title {
  font-weight: 600;
  color: var(--base00);
}

.member-count {
  color: var(--base01);
  font-size: 14px;
}

.collapsible-content {
  padding: 16px 0;
}
```

**Icons needed**:
- ChevronRight (collapse indicator)
- MessageCircle (coordination chat icon)

---

### Phase 6: Following Button & What You Can Do (Final Polish)

**Goal**: Blue button instead of green, consistent with Discussion, clean action hierarchy

**Following Button Before**:
- Green background (breaks Solarized)
- Emoji checkmark
- Person emoji in follower count

**Following Button After**:
```vue
<div class="following-section">
  <button
    class="btn-following"
    :class="{ 'is-following': isFollowing }"
    @click="toggleFollow"
  >
    <Check v-if="isFollowing" :size="16" />
    <Plus v-else :size="16" />
    {{ isFollowing ? 'Following' : 'Follow Issue' }}
  </button>

  <span class="follower-count">
    <Users :size="14" />
    1 neighbor following this
  </span>
</div>
```

**What You Can Do Before**:
- Grid of buttons with emoji
- Inconsistent with other action sections

**What You Can Do After**:
```vue
<section class="actions-section">
  <div class="section-header">
    <Zap :size="20" class="section-icon" />
    <h3>What You Can Do</h3>
  </div>

  <div class="action-list">
    <button class="action-item action-item-primary">
      <div class="action-icon">
        <Calendar :size="20} />
      </div>
      <div class="action-content">
        <span class="action-title">View Upcoming Meeting</span>
        <span class="action-description">Attend the next relevant city council meeting</span>
      </div>
      <ArrowRight :size="16" class="action-arrow" />
    </button>

    <button class="action-item">
      <div class="action-icon">
        <Link :size="20} />
      </div>
      <div class="action-content">
        <span class="action-title">Link to Another Meeting</span>
        <span class="action-description">Manually connect to a different civic meeting</span>
      </div>
      <ArrowRight :size="16" class="action-arrow" />
    </button>

    <button class="action-item">
      <div class="action-icon">
        <Users :size="20} />
      </div>
      <div class="action-content">
        <span class="action-title">Form Community Group</span>
        <span class="action-description">Start organizing with neighbors</span>
      </div>
      <ArrowRight :size="16" class="action-arrow" />
    </button>

    <button class="action-item">
      <div class="action-icon">
        <Share2 :size="20} />
      </div>
      <div class="action-content">
        <span class="action-title">Share with Neighbors</span>
        <span class="action-description">Spread awareness about this issue</span>
      </div>
      <ArrowRight :size="16" class="action-arrow" />
    </button>
  </div>
</section>
```

**Styling**:
```css
.following-section {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
  border-top: 1px solid var(--base02);
  margin-top: 24px;
}

.btn-following {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: transparent;
  color: var(--blue);
  border: 1px solid var(--base02);
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-following:hover {
  background: var(--base03);
  border-color: var(--blue);
}

.btn-following.is-following {
  background: var(--blue);
  color: var(--base3);
  border-color: var(--blue);
}

.btn-following.is-following:hover {
  background: var(--blue-hover);
}

.follower-count {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--base01);
}

.actions-section {
  margin-top: 24px;
}

.action-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--base03);
  border: 1px solid var(--base02);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.action-item:hover {
  border-color: var(--blue);
  background: var(--base02);
}

.action-item-primary {
  border-color: var(--blue);
  background: rgba(38, 139, 210, 0.05);
}

.action-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--base02);
  border-radius: 6px;
  color: var(--base01);
  flex-shrink: 0;
}

.action-item-primary .action-icon {
  background: var(--blue);
  color: var(--base3);
}

.action-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.action-title {
  font-weight: 600;
  color: var(--base00);
}

.action-description {
  font-size: 13px;
  color: var(--base01);
}

.action-arrow {
  color: var(--base01);
  flex-shrink: 0;
}
```

**Icons needed**:
- Check (following state)
- Plus (follow button)
- Users (follower count)
- Zap (section header)
- Calendar, Link, Share2 (action items)
- ArrowRight (action arrows)

---

## Implementation Checklist

### Preparation
- [ ] Read ComplaintArtifact.vue current implementation
- [ ] Verify lucide-vue-next imports available
- [ ] Verify Solarized CSS variables in design-system.css

### Phase 1: Progress & Actions (2-3 hours)
- [ ] Replace emoji heading with Target icon
- [ ] Remove heavy border box
- [ ] Add subtle status bar with background
- [ ] Replace emoji in buttons with lucide icons
- [ ] Reorganize button hierarchy (primary/secondary)
- [ ] Replace emoji indicators with icon + text
- [ ] Test button interactions

### Phase 2: Timeline (2-3 hours)
- [ ] Replace emoji icons with lucide icons
- [ ] Add vertical connection line (like Discussion)
- [ ] Replace "System" badges with subtle inline badges
- [ ] Add timeline marker circles with icons
- [ ] Style timeline items to match Discussion threads
- [ ] Move action buttons into timeline section
- [ ] Test timeline layout

### Phase 3: Meeting Cards (1-2 hours)
- [ ] Add card borders and hover states
- [ ] Style match percentage as badge/chip
- [ ] Add proper card spacing
- [ ] Style "View Meeting" button consistently
- [ ] Add hover transitions
- [ ] Test card interactions

### Phase 4: Similar Issues Cards (1-2 hours)
- [ ] Replace emoji with FileText icon
- [ ] Add visual weight to cards
- [ ] Add metadata (location, date)
- [ ] Style consistent with meeting cards
- [ ] Add hover states
- [ ] Implement "Show More" button
- [ ] Test card interactions

### Phase 5: Coordination Chat Collapsible (30 min)
- [ ] Replace emoji with MessageCircle icon
- [ ] Add ChevronRight collapse indicator
- [ ] Style header to match Discussion pattern
- [ ] Add rotation transition for chevron
- [ ] Test expand/collapse

### Phase 6: Following & Actions (1-2 hours)
- [ ] Change Following button from green to blue
- [ ] Replace checkmark emoji with Check icon
- [ ] Replace person emoji with Users icon
- [ ] Redesign "What You Can Do" as action list
- [ ] Add icons to each action item
- [ ] Add descriptions to action items
- [ ] Test all button states

### Final Polish (1 hour)
- [ ] Verify spacing consistency throughout
- [ ] Check typography hierarchy
- [ ] Test all hover states
- [ ] Verify color palette (Solarized only)
- [ ] Test with different content lengths
- [ ] Responsive layout check
- [ ] Compare side-by-side with Discussion artifact

---

## Complete Icon List (lucide-vue-next)

**Import statement**:
```typescript
import {
  // Section headers
  Target,          // Progress & Actions
  Clock,           // Government Response
  Calendar,        // Relevant Civic Meetings
  FileText,        // Similar Issues
  MessageCircle,   // Coordination Chat
  Zap,            // What You Can Do

  // Status & timeline
  CheckCircle2,    // Filed, Matched, Mark Resolved
  Link,           // Manually Linked, Link to Meeting
  AlertTriangle,   // Escalate

  // Actions
  Phone,          // File 311
  Mail,           // Email Department
  Search,         // Check Status

  // Community
  Users,          // Community stats, Form Group
  Share2,         // Share with Neighbors

  // UI elements
  ChevronRight,   // Collapse indicator
  ChevronDown,    // Show More
  ArrowRight,     // View buttons
  Check,          // Following state
  Plus,           // Follow button
} from 'lucide-vue-next';
```

---

## Success Criteria

Issues Artifact should feel as polished as Discussion Artifact:
1. **Visual Weight**: No heavy borders, consistent subtle styling
2. **Iconography**: Professional lucide icons throughout
3. **Color Palette**: Solarized colors only
4. **Hierarchy**: Clear visual priority (primary actions vs. secondary)
5. **Consistency**: All cards/sections feel related
6. **Interaction**: Smooth hover states, clear affordances
7. **Breathing Room**: Proper whitespace and rhythm

**Comparison Test**: Place Discussion and Issues artifacts side-by-side - they should feel like they belong to the same design system.

---

## Related Documentation

- `docs/SOCIAL_COORDINATION_REFINEMENT_STRATEGY.md` - Discussion aesthetic foundation
- `docs/SESSION_35_SOLARIZED_REFINEMENT.md` - Solarized color palette refinement
- `frontend/civic-workspace/src/design-system.css` - Design system CSS variables
- `frontend/civic-workspace/src/components/workspace/ComplaintArtifact.vue` - Current implementation
- `frontend/civic-workspace/src/components/workspace/ThreadArtifact.vue` - Target aesthetic reference
