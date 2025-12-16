# Pilot User Identification Guide

This guide documents how to identify and recruit pilot users for the January 2026 San Rafael pilot.

## Overview

**Goal**: Identify 5-10 San Rafael residents who have demonstrated interest in civic issues and would benefit from coordinated participation in a high-stakes city council decision.

**Timeline**:
- User identification: Week of January 6, 2026
- Outreach: January 6-10, 2026
- Pre-meeting coordination: January 13-17, 2026
- Council meeting participation: Week of January 20, 2026

## User Identification Criteria

### Primary Data Sources

1. **SeeClickFix Complaints** (1,437 complaints available)
   - Residents who filed complaints matching the decision topic
   - Data: `data/pilot/seeclickfix_sanrafael_complete.json`
   - Fields: reporter info, location, issue type, timestamps

2. **Geographic Proximity**
   - Residents within impact radius of the decision
   - Use address field from SeeClickFix data
   - Typical radius: 500m-1km from decision location

3. **Issue Type Matching**
   - Use `whos_with_me()` API to find residents with related complaints
   - Semantic matching finds related topics (e.g., "traffic" matches "speeding", "pedestrian safety")

### Secondary Data Sources (Future)

4. **Platform Followers**
   - Users who followed related topics in the Civic app
   - Requires: Platform adoption during pilot

5. **Past Testimony**
   - Residents who spoke at previous council meetings
   - Source: Meeting transcript analysis

## Identification Process

### Step 1: Select High-Stakes Decision

Reference: `data/pilot/san_rafael_high_stakes_validated.json`

Criteria for decision selection:
- Budget allocation >$100K, OR
- Development >50 units, OR
- Broad policy change affecting multiple neighborhoods
- 7+ days lead time (time for coordination)
- Clear affected population

Example decisions from data:
- Illegal Dumping Mitigation Services ($100K) - citywide
- Street repaving programs - pothole complainants
- Housing developments - geographic neighbors

### Step 2: Query Related Complaints

```python
from civic import Civic

c = Civic("san-rafael")

# Find residents who care about the topic
community = c.whos_with_me("illegal dumping")

# Returns:
# - follower_count: Number of related complaints
# - issue_types: Matched SeeClickFix categories
# - geographic_clusters: Where complaints are concentrated
```

### Step 3: Filter by Location (for geographic decisions)

For decisions with a specific location (e.g., new development):

```python
import json
from math import radians, sin, cos, sqrt, atan2

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in meters"""
    R = 6371000  # Earth's radius in meters
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

# Load complaints
with open('data/pilot/seeclickfix_sanrafael_complete.json') as f:
    complaints = json.load(f)

# Filter by proximity to decision location
decision_lat, decision_lon = 37.9735, -122.5311  # Example: downtown SR
radius_m = 500  # 500 meter radius

nearby = [
    c for c in complaints
    if c.get('location', {}).get('lat') and
    haversine_distance(
        c['location']['lat'], c['location']['lng'],
        decision_lat, decision_lon
    ) < radius_m
]

print(f"Found {len(nearby)} complaints within {radius_m}m")
```

### Step 4: Score and Rank Candidates

Prioritize residents based on:

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Topic relevance | 3x | Direct complaint match = most affected |
| Recency | 2x | Recent complainants more likely engaged |
| Geographic proximity | 2x | Closer = more directly impacted |
| Complaint count | 1x | Multiple complaints = engaged citizen |

### Step 5: Extract Contact Information

SeeClickFix data includes:
- `reporter.name` - Display name (often anonymous)
- `reporter.id` - Internal user ID
- `html_url` - Link to original complaint

**Note**: Direct contact info (email/phone) not available from SeeClickFix API. Outreach options:
1. Comment on their SeeClickFix complaint (public)
2. Use SeeClickFix messaging (if available)
3. Nextdoor/community forums for geographic areas
4. Physical neighborhood canvassing (last resort)

## Target User Profile

Ideal pilot users are:

1. **Affected by the decision** - Have filed relevant complaint or live near impact area
2. **Previously engaged** - Demonstrated willingness to report issues
3. **Reachable** - Can be contacted through available channels
4. **Available** - Free for pre-meeting coordination and council meeting

### User Personas

**Persona A: Direct Complainant**
- Filed SeeClickFix complaint directly related to decision topic
- Example: Pothole complainant for street repaving decision
- Motivation: Their specific issue may be addressed

**Persona B: Geographic Neighbor**
- Lives within impact radius of development/project
- May not have filed related complaint
- Motivation: Neighborhood impact awareness

**Persona C: Serial Reporter**
- Multiple complaints across various topics
- Demonstrates civic engagement pattern
- Motivation: General civic participation

## Sample Identification Workflow

For a $500K street repair budget decision:

```bash
# 1. Load SeeClickFix data
python3 -c "
import json

with open('data/pilot/seeclickfix_sanrafael_complete.json') as f:
    complaints = json.load(f)

# 2. Filter for road/pothole related
keywords = ['pothole', 'road', 'street', 'pavement', 'asphalt', 'crack']
road_complaints = [
    c for c in complaints
    if any(k in (c.get('title', '') + c.get('description', '')).lower()
           for k in keywords)
]

print(f'Road-related complaints: {len(road_complaints)}')

# 3. Group by reporter (find engaged residents)
from collections import Counter
reporters = Counter(c['reporter']['name'] for c in road_complaints)

print('\\nTop reporters:')
for name, count in reporters.most_common(10):
    print(f'  {name}: {count} complaints')

# 4. Get recent complaints (last 6 months)
from datetime import datetime, timedelta
cutoff = (datetime.now() - timedelta(days=180)).isoformat()
recent = [c for c in road_complaints if c['created_at'] > cutoff]

print(f'\\nRecent (6mo): {len(recent)} complaints')
"
```

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Candidates identified | 20-30 | Number of relevant residents found |
| Reachable via available channels | 15-20 | Can be contacted somehow |
| Respond to outreach | 8-12 | Reply to initial message |
| Commit to coordination | 5-10 | Agree to participate |

## Next Steps After Identification

1. **Outreach** - Contact identified residents (see Outreach Templates below)
2. **Onboarding** - Brief them on Civic platform and pilot goals
3. **Coordination** - Facilitate pre-meeting strategy session
4. **Participation** - Support council meeting attendance
5. **Feedback** - Collect empowerment survey responses

---

## Outreach Templates

### Template 1: SeeClickFix Comment (Public)

```
Hi [Name],

I noticed you reported [issue type] at [location] - thank you for being engaged
with our city!

The San Rafael City Council is voting on [decision] on [date], which could
address issues like the one you reported. A group of us are coordinating to
share our perspectives at the meeting.

Would you be interested in joining a 1-hour virtual prep session on [date]?
No pressure - just neighbors helping neighbors make our voices heard.

Reply here or reach out if interested!
```

### Template 2: Initial Email (When Available)

Subject: San Rafael neighbors coordinating on [decision topic]

```
Hi [Name],

I'm reaching out because you reported [issue] on SeeClickFix, and there's an
upcoming City Council decision that relates to your concern.

**The decision**: [Title]
**When**: [Date and time]
**Why it matters**: [Brief impact description]

A few of us who care about this issue are meeting virtually on [date] to:
- Learn about the decision context
- Coordinate our feedback (so we're not all saying the same thing)
- Prepare anyone who wants to speak at the meeting

You don't need to speak publicly if you don't want to - showing up counts.

Interested? Reply to this email or RSVP at [link].

Thanks for being an engaged neighbor,
[Your name]
```

### Template 3: Follow-Up (No Response)

Subject: Re: San Rafael neighbors coordinating on [decision topic]

```
Hi [Name],

Following up on my message about the [decision] vote on [date].

Quick summary:
- Pre-meeting coordination session: [Date, Time]
- City Council vote: [Date, Time]
- Your [issue type] complaint at [location] is directly related

If the timing doesn't work, no worries - let me know if you'd like to be
notified about future decisions that affect your neighborhood.

Best,
[Your name]
```

### Template 4: Confirmation (Committed Participant)

Subject: Confirmed: Pre-meeting coordination for [decision]

```
Thanks for signing up, [Name]!

Here are the details:

**Pre-meeting coordination session**
- Date: [Date]
- Time: [Time]
- Link: [Zoom/Google Meet link]
- Duration: ~60 minutes

**What to expect**:
1. Overview of the decision and why it matters
2. Relevant state/federal context
3. Strategy discussion (who says what)
4. Talking points for those who want to speak

**City Council meeting**
- Date: [Date]
- Time: [Time]
- Location: [Address] OR virtual attendance at [link]

Questions? Just reply to this email.

See you soon,
[Your name]
```

---

## Privacy and Ethics

1. **No data scraping** - Only use publicly available complaint data
2. **Opt-in participation** - Never pressure or repeatedly contact
3. **Clear purpose** - Always explain pilot goals and data usage
4. **Anonymity respected** - Don't expose anonymous complainants
5. **No political agenda** - Facilitate coordination, not advocacy

## Related Resources

- High-stakes decisions: `data/pilot/san_rafael_high_stakes_validated.json`
- SeeClickFix data: `data/pilot/seeclickfix_sanrafael_complete.json`
- API documentation: `docs/user_guides/GETTING_STARTED.md`
- Pilot roadmap: `docs/critical/PILOT_ROADMAP.md`

---

*Created: Session 271 (2025-12-15)*
*Status: Ready for January 2026 pilot*
