# Manual Test Guide: Archetype Integration (Session 41)

## Setup Test Archetypes in Browser

### Step 1: Open Browser Console
1. Start the frontend: `cd apps/civic-workspace && npm run dev`
2. Navigate to http://localhost:5173
3. Open browser DevTools (F12) → Console tab

### Step 2: Set Test Archetypes in localStorage
```javascript
// Set test archetypes: Green New Dealer + Regional Thinker + Labor Organizer
const testArchetypes = [
  {
    id: 'green_new_dealer',
    name: 'Green New Dealer',
    score: 0.525,
    description: 'Climate action through government jobs programs and public investment',
    icon: 'Sprout',
    iconColor: '#859900'
  },
  {
    id: 'regional_thinker',
    name: 'Regional Thinker',
    score: 0.515,
    description: 'Regional coordination, metropolitan perspective, systems thinking',
    icon: 'Network',
    iconColor: '#268bd2'
  },
  {
    id: 'labor_organizer',
    name: 'Labor Organizer',
    score: 0.510,
    description: 'Worker rights, living wages, unions, labor standards',
    icon: 'Users',
    iconColor: '#cb4b16'
  }
];

localStorage.setItem('civic-archetypes', JSON.stringify(testArchetypes));
localStorage.setItem('civic-archetypes-updated', new Date().toISOString());

// Reload to apply
location.reload();
```

### Step 3: Test Comment Drafting

#### Test A: With Archetypes (Personalized)
1. Select Oakland from jurisdictions
2. Click any event with agenda items
3. Click an agenda item
4. Click "Draft Comment" button
5. **Expected**: Comment reflects Green New Dealer values:
   - Mentions climate action, public investment, green infrastructure
   - May reference regional coordination or worker protections
   - Professional tone but values-driven framing

#### Test B: Without Archetypes (Generic)
```javascript
// Clear archetypes in console
localStorage.removeItem('civic-archetypes');
localStorage.removeItem('civic-archetypes-updated');
location.reload();
```

1. Click same agenda item
2. Click "Draft Comment"
3. **Expected**: Generic comment without specific value framing
   - Professional but neutral tone
   - Focuses on facts and general concerns
   - No climate/labor/regional emphasis

## Success Criteria

✅ **Personalized comment (with archetypes):**
- Contains climate/environmental keywords (climate, green, sustainable, etc.)
- OR contains regional/systems keywords (regional, metropolitan, coordination)
- OR contains labor/worker keywords (workers, labor, delivery riders, etc.)
- Framing aligns with at least one archetype value

✅ **Generic comment (without archetypes):**
- Professional but neutral tone
- No specific value framing
- Focuses on general civic concerns

## Code Verification Checklist

✅ Backend (`src/civic_api_integrated.py`):
- Line 2054: Accepts `archetypes` parameter from request
- Line 2107-2120: Builds archetype context string
- Line 2152-2175: System prompt includes archetype context with strong framing instructions

✅ Frontend (`apps/civic-workspace/src/services/api.ts`):
- Line 181: `archetypes` parameter in API interface

✅ Frontend (`apps/civic-workspace/src/components/workspace/CommentDraftArtifact.vue`):
- Line 164: Passes `userStore.archetypes` to API

## Backend Logs

When generating comments, you should see in backend logs:
- WITH archetypes: `✅ Using 3 civic archetypes for personalized framing`
- WITHOUT archetypes: `ℹ️  No archetypes provided - generating generic comment`

## Privacy Note

Archetypes are **Privacy Tier 1 (Browser-Only)**:
- Stored in `localStorage` only
- Never saved to database
- Passed to backend only for AI prompt construction
- Not logged or persisted server-side

This is by design to protect users from government subpoenas or data breaches.
