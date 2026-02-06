"""
Shared tool handler implementations for CivicOS MCP server.

These handlers are standalone functions that can be used by both:
- civicos_server.py (FastMCP)
- modal_app.py (Modal)

Each handler takes the same signature:
    handler(civic, jurisdiction, validate_input, logger, args) -> str

The server implementation is responsible for binding these handlers
with the appropriate context (civic client, validator, logger).
"""

from datetime import datetime, timedelta
from collections import Counter
from typing import Any, Callable, Optional
import math
import os
import random


# Type alias for CivicOS client (to avoid import dependency)
CivicClient = Any
ValidateInput = Callable[[dict], tuple[bool, dict, str | None]]
Logger = Any


# ─────────── Geocoding Utilities ───────────


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points in meters.

    Uses the Haversine formula for accuracy at small distances.
    """
    R = 6371000  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def _geocode_address(address: str, logger: Logger) -> Optional[tuple[float, float]]:
    """
    Geocode an address to lat/lng using Google Maps API.

    Returns (lat, lng) tuple or None if geocoding fails or API key not configured.
    """
    # Check both env var names for compatibility
    api_key = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.debug("GOOGLE_MAPS_API_KEY/GOOGLE_API_KEY not set, falling back to text matching")
        return None

    try:
        import httpx

        params = {
            "address": address,
            "key": api_key,
        }
        response = httpx.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            return (location["lat"], location["lng"])

        logger.warning(f"Geocoding failed: {data.get('status')}")
        return None

    except Exception as e:
        logger.warning(f"Geocoding error: {e}")
        return None


# ─────────── Core Civic Tools ───────────


def search_meeting_history(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search past city council meetings and decisions."""
    query = args.get("query", "")
    include_transcripts = args.get("include_transcripts", True)
    limit = args.get("limit", 10)

    is_valid, sanitized, error = validate_input({"query": query})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    query = sanitized.get("query", query)

    result_parts = [f"# Meeting History: {query}", ""]

    try:
        decisions = civic.what_happened(query)

        result_parts.append(f"## Decisions ({jurisdiction})")
        if decisions:
            for d in decisions[:limit]:
                result_parts.append(f"### {d.title}")
                result_parts.append(f"- Date: {d.date}")
                result_parts.append(f"- Outcome: {d.outcome or 'N/A'}")
                result_parts.append(f"- Body: {d.body or 'N/A'}")
                if d.votes:
                    result_parts.append(f"- Votes: {d.votes}")
                result_parts.append("")
        else:
            result_parts.append("No decisions found matching this query.")

        if include_transcripts:
            result_parts.append("## What Was Said (Transcript Excerpts)")
            excerpts = civic.what_was_said(query, top_k=limit)
            if excerpts:
                for ex in excerpts:
                    speaker = ex.speaker_name or ex.speaker or "Unknown"
                    result_parts.append(f"### {speaker}")
                    result_parts.append(f"> {ex.text[:500]}...")
                    result_parts.append("")
            else:
                result_parts.append("No transcript excerpts found.")

    except Exception as e:
        logger.error(f"Error in search_meeting_history: {e}")
        return f"Error searching meeting history: {str(e)}"

    return "\n".join(result_parts)


def get_upcoming_meetings(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get upcoming city council meetings."""
    days = args.get("days", 30)

    try:
        meetings = civic.whats_next(days=days)

        result_parts = [f"# Upcoming Meetings (next {days} days)", ""]

        if meetings:
            for m in meetings:
                title = getattr(m, 'title', str(m))
                date = getattr(m, 'meeting_datetime', getattr(m, 'date', 'TBD'))
                result_parts.append(f"- **{title}** - {date}")
        else:
            result_parts.append("No upcoming meetings found.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_upcoming_meetings: {e}")
        return f"Error getting upcoming meetings: {str(e)}"


def find_similar_issues(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Find community issues related to a topic."""
    topic = args.get("topic", "")
    semantic = args.get("semantic", True)
    limit = args.get("limit", 20)

    is_valid, sanitized, error = validate_input({"topic": topic})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    topic = sanitized.get("topic", topic)

    try:
        result_parts = [f"# Community Issues: {topic}", ""]

        if semantic and civic._vectors is not None:
            results = civic._vectors.search(
                topic,
                jurisdiction,
                'issues',
                top_k=limit,
            )
            result_parts.append(f"**Related issues found:** {len(results)}")
            result_parts.append("")

            for r in results:
                content = r.content[:200] if r.content else "No description"
                score = r.score if hasattr(r, 'score') else None
                if score:
                    result_parts.append(f"- **[{score:.0%} match]** {content}...")
                else:
                    result_parts.append(f"- {content}...")
        else:
            result_parts.append("Semantic search unavailable.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in find_similar_issues: {e}")
        return f"Error finding similar issues: {str(e)}"


def search_regulatory_stack(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search regulatory stack for a topic."""
    topic = args.get("topic", "")

    is_valid, sanitized, error = validate_input({"topic": topic})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    topic = sanitized.get("topic", topic)

    try:
        stack = civic.what_applies(topic)

        result_parts = [f"# Regulatory Stack: {stack.topic}", ""]

        # Federal
        result_parts.append("## Federal")
        if stack.federal:
            for item in stack.federal[:5]:
                if isinstance(item, dict):
                    result_parts.append(f"- {item.get('title', str(item))}")
                else:
                    result_parts.append(f"- {item}")
        else:
            result_parts.append("No federal regulations found.")
        result_parts.append("")

        # State
        result_parts.append("## State")
        if stack.state:
            for item in stack.state[:5]:
                if isinstance(item, dict):
                    bill = item.get('bill_number', '')
                    name = item.get('bill_name', '')
                    result_parts.append(f"- **{bill}**: {name}" if bill else f"- {name}")
                else:
                    result_parts.append(f"- {item}")
        else:
            result_parts.append("No state regulations found.")
        result_parts.append("")

        # Local
        result_parts.append("## Local")
        if stack.local:
            for item in stack.local[:5]:
                if isinstance(item, dict):
                    section = item.get('section_number', '')
                    name = item.get('section_name', '')
                    result_parts.append(f"- **{section}**: {name}" if section else f"- {str(item)[:200]}")
                else:
                    result_parts.append(f"- {str(item)[:200]}")
        else:
            result_parts.append("No local regulations found.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in search_regulatory_stack: {e}")
        return f"Error searching regulatory stack: {str(e)}"


def compose_public_comment(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get context for writing a public comment."""
    item_title = args.get("item_title", "")
    topic = args.get("topic") or item_title

    is_valid, sanitized, error = validate_input({"item_title": item_title, "topic": topic})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    result_parts = [f"# Public Comment Context: {item_title}", ""]

    result_parts.append("## Submission Guidelines")
    result_parts.append("")
    result_parts.append("**San Rafael City Council:**")
    result_parts.append("- Email: clerk@cityofsanrafael.org")
    result_parts.append("- Subject line: \"Public Comment - [Agenda Item Title]\"")
    result_parts.append("- Deadline: 5:00 PM day of meeting for written record")
    result_parts.append("- In-person: 3 minutes max, sign up before meeting")
    result_parts.append("")

    # Past testimony
    try:
        testimony = civic.get_public_testimony(topic, top_k=3)
        if testimony:
            result_parts.append("## What Others Have Said")
            for t in testimony[:3]:
                speaker = getattr(t, 'speaker_name', 'Resident')
                text = getattr(t, 'text', str(t))[:200]
                result_parts.append(f"**{speaker}:** \"{text}...\"")
                result_parts.append("")
    except Exception as e:
        logger.warning(f"Could not fetch testimony: {e}")

    result_parts.append("## Tips for Effective Comments")
    result_parts.append("")
    result_parts.append("1. State your position clearly in the first sentence")
    result_parts.append("2. Be specific - reference the agenda item by name")
    result_parts.append("3. Share personal impact - how does this affect you?")
    result_parts.append("4. Propose alternatives if opposing")
    result_parts.append("5. Be respectful - address \"Mayor and Council Members\"")
    result_parts.append("6. Include your address to show you're a resident")

    return "\n".join(result_parts)


def city_pulse(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> dict:
    """Get comprehensive city activity snapshot."""
    days_ahead = args.get("days_ahead", 7)
    days_back = args.get("days_back", 30)

    now = datetime.now()
    storage = civic._storage

    result = {
        "jurisdiction": jurisdiction,
        "generated_at": now.isoformat(),
        "decisions_this_week": [],
        "recent_outcomes": [],
        "community_pulse": {},
    }

    try:
        # Recent and upcoming meetings (look back 3 days to catch "today" in different timezones)
        # This ensures we show recent activity even when meetings are stored in UTC
        meetings = storage.get_meetings(
            jurisdiction,
            since=now - timedelta(days=3),
            until=now + timedelta(days=days_ahead),
            limit=20
        )

        # Sort by date and take most recent/upcoming
        meetings = sorted(meetings, key=lambda m: m.get('meeting_datetime') or now, reverse=True)

        for m in meetings[:10]:  # Limit to 10 most recent/upcoming
            meeting_dt = m.get('meeting_datetime')
            if meeting_dt and hasattr(meeting_dt, 'strftime'):
                date_str = meeting_dt.strftime("%a, %b %d")
                time_str = meeting_dt.strftime("%I:%M %p").lstrip('0')
            else:
                date_str = str(meeting_dt)[:10] if meeting_dt else "TBD"
                time_str = ""

            result["decisions_this_week"].append({
                "title": m.get('title') or m.get('body') or 'Meeting',
                "date": date_str,
                "time": time_str,
            })

        # Recent decisions - get all and sort by most recent
        # Many decisions don't have dates set, so we fetch all and limit
        decisions = storage.get_decisions(jurisdiction, limit=50)

        # Sort by decision_date if available, then limit
        decisions_with_dates = []
        for d in decisions:
            decision_date = d.get('decision_date') or d.get('meeting_datetime')
            decisions_with_dates.append((d, decision_date))

        # Sort: those with dates first (newest), then those without
        decisions_with_dates.sort(
            key=lambda x: (x[1] is None, x[1] if x[1] else now),
            reverse=True
        )

        for d, decision_date in decisions_with_dates[:10]:
            if decision_date and hasattr(decision_date, 'strftime'):
                date_str = decision_date.strftime("%b %d")
            else:
                date_str = "Recent"

            result["recent_outcomes"].append({
                "title": d.get('title') or 'Decision',
                "outcome": d.get('outcome') or d.get('status') or 'decided',
                "date": date_str,
            })

        # Community pulse (issues)
        issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=500)
        if issues:
            type_counts = Counter(i.get('issue_type', 'Other') for i in issues)
            result["community_pulse"] = {
                "total_issues": len(issues),
                "top_types": dict(type_counts.most_common(5)),
            }

    except Exception as e:
        logger.error(f"Error in city_pulse: {e}")
        result["error"] = str(e)

    return result


def get_issue_analytics(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get aggregate 311 issue statistics."""
    try:
        issues = civic._storage.get_issues(
            jurisdiction_id=jurisdiction, limit=5000
        )

        if not issues:
            return f"No 311 issues found for {jurisdiction}."

        by_status = Counter(i.get('status', 'unknown') for i in issues)
        by_type = Counter(i.get('issue_type', 'Unknown') for i in issues)

        closed = sum(1 for i in issues if i.get('status', '').lower() in {'closed', 'resolved'})
        resolution_rate = (closed / len(issues) * 100) if issues else 0

        result_parts = [
            f"# 311 Issue Analytics: {jurisdiction}",
            f"**Total Issues:** {len(issues):,}",
            f"**Resolution Rate:** {resolution_rate:.1f}%",
            "",
            "## By Status",
        ]
        for status, count in by_status.most_common():
            result_parts.append(f"- {status}: {count}")

        result_parts.extend(["", "## By Type"])
        for itype, count in by_type.most_common(10):
            result_parts.append(f"- {itype}: {count}")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting issue analytics: {str(e)}"


def get_issue_trends(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Analyze trends in 311 issues over time."""
    return "Issue trends analysis: Use get_issue_analytics for current data."


def geo_search_issues(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search issues by geographic area."""
    area = args.get("area", "")

    try:
        issues = civic._storage.get_issues(
            jurisdiction_id=jurisdiction, limit=2000
        )

        area_lower = area.lower()
        matched = [
            i for i in issues
            if area_lower in (i.get('address', '') or '').lower()
        ]

        result_parts = [
            f"# Issues near: {area}",
            f"**Found:** {len(matched)} issues",
            "",
        ]

        for i in matched[:20]:
            result_parts.append(f"- {i.get('issue_type', 'Issue')}: {i.get('address', 'Unknown')}")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error searching issues: {str(e)}"


def search_budget(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search city budget data."""
    query = args.get("query", "")

    try:
        budget_items = civic._storage.get_budget_items(jurisdiction)

        if not budget_items:
            return "No budget data available."

        query_lower = query.lower() if query else ""
        matched = [
            b for b in budget_items
            if not query or query_lower in (b.get('department', '') or '').lower()
            or query_lower in (b.get('category', '') or '').lower()
        ]

        result_parts = [f"# Budget Search: {query or 'All'}", ""]

        for b in matched[:20]:
            dept = b.get('department', 'Unknown')
            amount = b.get('amount', 0)
            result_parts.append(f"- **{dept}**: ${amount:,.0f}")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error searching budget: {str(e)}"


def get_public_testimony(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get public testimony excerpts."""
    topic = args.get("topic", "")
    limit = args.get("limit", 5)

    try:
        testimony = civic.get_public_testimony(topic, top_k=limit)

        result_parts = [f"# Public Testimony: {topic}", ""]

        if testimony:
            for t in testimony:
                speaker = getattr(t, 'speaker_name', 'Resident')
                text = getattr(t, 'text', str(t))[:300]
                result_parts.append(f"**{speaker}:**")
                result_parts.append(f"> {text}...")
                result_parts.append("")
        else:
            result_parts.append("No public testimony found.")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting testimony: {str(e)}"


def search_agenda_packets(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search agenda packets and staff reports."""
    query = args.get("query", "")
    limit = args.get("limit", 10)

    try:
        if civic._vectors:
            results = civic._vectors.search(
                query, jurisdiction, 'chunks', top_k=limit
            )

            result_parts = [f"# Agenda Packet Search: {query}", ""]

            for r in results:
                result_parts.append(f"- {r.content[:200]}...")

            return "\n".join(result_parts)
        else:
            return "Agenda packet search unavailable."

    except Exception as e:
        return f"Error searching agenda packets: {str(e)}"


def get_comment_guidelines(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get public comment guidelines."""
    return """
San Rafael Public Comment Guidelines:

EMAIL SUBMISSION:
- Send to: clerk@cityofsanrafael.org
- Subject: "Public Comment - [Agenda Item Title]"
- Include your name and San Rafael address
- Submit by 5:00 PM day of meeting for inclusion in official record

IN-PERSON COMMENTS:
- Sign up before meeting starts
- 3 minutes maximum per speaker
- Address comments to Mayor and Council
- No personal attacks or off-topic remarks

CONTACT INFO:
- City Clerk: clerk@cityofsanrafael.org
- Council meetings: First and third Monday, 7:00 PM
- City Hall: 1400 Fifth Avenue, San Rafael CA 94901
    """.strip()


def get_started(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get overview of local government activity."""
    pulse = city_pulse(civic, jurisdiction, validate_input, logger, {})

    result_parts = [f"# Welcome to {jurisdiction.replace('city-', '').title()}", ""]

    # Upcoming meetings
    meetings = pulse.get("decisions_this_week", [])
    if meetings:
        result_parts.append("## Coming Up")
        for m in meetings[:3]:
            result_parts.append(f"- **{m['title']}** - {m['date']}")
        result_parts.append("")

    # Recent decisions
    decisions = pulse.get("recent_outcomes", [])
    if decisions:
        result_parts.append("## Recently Decided")
        for d in decisions[:3]:
            result_parts.append(f"- {d['title']} ({d['outcome']})")
        result_parts.append("")

    result_parts.append("## What Can I Help With?")
    result_parts.append("- Search past council decisions")
    result_parts.append("- Find upcoming meetings")
    result_parts.append("- Discover community issues")
    result_parts.append("- Get help writing public comments")

    return "\n".join(result_parts)


# ─────────── 311 Analysis Handlers ───────────


def query_issue_data(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Query 311 issue data with flexible grouping and filtering."""
    group_by = args.get("group_by", "type")
    filter_type = args.get("filter_type")
    filter_status = args.get("filter_status")
    filter_street = args.get("filter_street")
    limit = args.get("limit", 50)

    try:
        issues = civic._storage.get_issues(
            jurisdiction_id=jurisdiction,
            status=filter_status,
            limit=5000,
        )

        if not issues:
            return f"No issues found for {jurisdiction}."

        # Apply filters
        if filter_type:
            filter_type_lower = filter_type.lower()
            issues = [i for i in issues if filter_type_lower in (i.get('issue_type', '') or '').lower()]

        if filter_street:
            filter_street_lower = filter_street.lower()
            issues = [i for i in issues if filter_street_lower in (i.get('address', '') or '').lower()]

        if not issues:
            return "No issues match the specified filters."

        # Group data
        def extract_street(addr):
            if not addr:
                return "Unknown"
            parts = addr.split(',')[0].split()
            if parts and parts[0].isdigit():
                parts = parts[1:]
            return ' '.join(parts[:3]) if parts else "Unknown"

        grouped = Counter()
        for issue in issues:
            if group_by == "type":
                key = issue.get('issue_type', 'Unknown')
            elif group_by == "status":
                key = issue.get('status', 'unknown')
            elif group_by == "street":
                key = extract_street(issue.get('address'))
            else:
                key = issue.get('issue_type', 'Unknown')
            grouped[key] += 1

        result_parts = [
            f"# Issue Query Results",
            f"**Grouped by:** {group_by}",
            f"**Total matching issues:** {len(issues):,}",
            "",
            f"## Results by {group_by.title()}",
        ]

        for key, count in grouped.most_common(limit):
            pct = count / len(issues) * 100
            result_parts.append(f"- **{key}:** {count:,} ({pct:.1f}%)")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error querying issue data: {str(e)}"


def get_issue_resolution_stats(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get resolution statistics for 311 issues."""
    issue_type = args.get("issue_type")
    zip_code = args.get("zip_code")

    try:
        issues = civic._storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if not issues:
            return f"No issues found for {jurisdiction}."

        # Apply filters
        if issue_type:
            issue_type_lower = issue_type.lower()
            issues = [i for i in issues if issue_type_lower in (i.get('issue_type', '') or '').lower()]

        if zip_code:
            issues = [i for i in issues if zip_code in (i.get('address', '') or '')]

        if not issues:
            return "No issues match the specified filters."

        total = len(issues)
        closed_statuses = {'closed', 'resolved', 'archived'}
        resolved = [i for i in issues if i.get('status', '').lower() in closed_statuses]
        resolved_count = len(resolved)
        resolution_rate = (resolved_count / total * 100) if total > 0 else 0

        result_parts = [
            f"# Issue Resolution Statistics",
            f"**Total Issues:** {total:,}",
            "",
            "## Overall Resolution",
            f"- **Resolved:** {resolved_count:,} ({resolution_rate:.1f}%)",
            f"- **Still Open:** {total - resolved_count:,}",
        ]

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting resolution stats: {str(e)}"


def detect_trends(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Detect significant trends in 311 issue patterns."""
    lookback_months = args.get("lookback_months", 6)
    min_change_pct = args.get("min_change_pct", 20.0)
    zip_code = args.get("zip_code")

    try:
        issues = civic._storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if zip_code:
            issues = [i for i in issues if zip_code in (i.get('address', '') or '')]

        if not issues:
            return "No issues found for analysis."

        now = datetime.now()
        recent_start = now - timedelta(days=lookback_months * 30)
        previous_start = recent_start - timedelta(days=lookback_months * 30)

        recent_issues = []
        previous_issues = []

        for issue in issues:
            created = issue.get('created_at')
            if not created:
                continue
            try:
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00')).replace(tzinfo=None)
                else:
                    dt = created
                if dt >= recent_start:
                    recent_issues.append(issue)
                elif dt >= previous_start:
                    previous_issues.append(issue)
            except:
                continue

        if not recent_issues and not previous_issues:
            return "Not enough historical data to detect trends."

        recent_counts = Counter(i.get('issue_type', 'Unknown') for i in recent_issues)
        previous_counts = Counter(i.get('issue_type', 'Unknown') for i in previous_issues)

        changes = []
        all_types = set(recent_counts.keys()) | set(previous_counts.keys())
        for issue_type in all_types:
            recent = recent_counts.get(issue_type, 0)
            previous = previous_counts.get(issue_type, 0)
            if previous > 0:
                pct_change = ((recent - previous) / previous) * 100
            elif recent > 0:
                pct_change = 100
            else:
                continue
            if abs(pct_change) >= min_change_pct and (recent >= 3 or previous >= 3):
                changes.append({'type': issue_type, 'recent': recent, 'previous': previous, 'change': pct_change})

        increasing = sorted([c for c in changes if c['change'] > 0], key=lambda x: -x['change'])
        decreasing = sorted([c for c in changes if c['change'] < 0], key=lambda x: x['change'])

        result_parts = [
            f"# Issue Trends Analysis",
            f"**Period:** Last {lookback_months} months vs previous {lookback_months} months",
            f"**Recent:** {len(recent_issues):,} issues | **Previous:** {len(previous_issues):,} issues",
            "",
        ]

        if increasing:
            result_parts.append("## Increasing Issues")
            for c in increasing[:7]:
                result_parts.append(f"- **{c['type']}:** {c['previous']} -> {c['recent']} (+{c['change']:.0f}%)")
            result_parts.append("")

        if decreasing:
            result_parts.append("## Decreasing Issues")
            for c in decreasing[:7]:
                result_parts.append(f"- **{c['type']}:** {c['previous']} -> {c['recent']} ({c['change']:.0f}%)")

        if not increasing and not decreasing:
            result_parts.append("No significant trends detected.")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error detecting trends: {str(e)}"


def get_issue_sample(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get a sample of raw 311 issues for pattern analysis."""
    sample_size = min(args.get("sample_size", 30), 50)
    filter_type = args.get("filter_type")
    filter_status = args.get("filter_status")
    filter_street = args.get("filter_street")
    random_sample = args.get("random_sample", True)

    try:
        issues = civic._storage.get_issues(
            jurisdiction_id=jurisdiction,
            status=filter_status,
            limit=5000,
        )

        if not issues:
            return f"No issues found for {jurisdiction}."

        # Apply filters
        if filter_type:
            filter_type_lower = filter_type.lower()
            issues = [i for i in issues if filter_type_lower in (i.get('issue_type', '') or '').lower()]

        if filter_street:
            filter_street_lower = filter_street.lower()
            issues = [i for i in issues if filter_street_lower in (i.get('address', '') or '').lower()]

        if not issues:
            return "No issues match the specified filters."

        # Sample
        if random_sample and len(issues) > sample_size:
            sample = random.sample(issues, sample_size)
        else:
            sample = issues[:sample_size]

        result_parts = [
            f"# Issue Sample",
            f"**Sample size:** {len(sample)} of {len(issues)} matching issues",
            "",
        ]

        for i, issue in enumerate(sample, 1):
            result_parts.append(f"## Issue {i}")
            result_parts.append(f"- **Type:** {issue.get('issue_type', 'Unknown')}")
            result_parts.append(f"- **Status:** {issue.get('status', 'Unknown')}")
            result_parts.append(f"- **Address:** {issue.get('address', 'N/A')}")
            desc = (issue.get('description') or '')[:300]
            if desc:
                result_parts.append(f"- **Description:** {desc}...")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting issue sample: {str(e)}"


def find_issues_near_address(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Find 311 issues near a specific address using geocoding."""
    address = args.get("address", "")
    issue_type = args.get("issue_type")
    radius_blocks = args.get("radius_blocks", 2)

    is_valid, sanitized, error = validate_input({"address": address})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    # Convert blocks to meters (approx 100m per city block)
    radius_meters = radius_blocks * 100

    try:
        issues = civic._storage.get_issues(
            jurisdiction_id=jurisdiction, limit=2000
        )

        # Try geocoding first
        coords = _geocode_address(address, logger)
        use_geocoding = coords is not None

        if use_geocoding:
            target_lat, target_lng = coords
            logger.info(f"Geocoded '{address}' to ({target_lat:.4f}, {target_lng:.4f})")

            # Find issues within radius using haversine distance
            matched = []
            for i in issues:
                issue_lat = i.get("latitude")
                issue_lng = i.get("longitude")

                if issue_lat is not None and issue_lng is not None:
                    distance = _haversine_distance(
                        target_lat, target_lng,
                        float(issue_lat), float(issue_lng)
                    )
                    if distance <= radius_meters:
                        i["_distance_m"] = round(distance)
                        matched.append(i)

            # Sort by distance
            matched.sort(key=lambda x: x.get("_distance_m", 0))
            search_method = f"geocoded ({radius_blocks} block radius)"

        else:
            # Fallback to text matching
            address_lower = address.lower()
            address_parts = address_lower.split()

            matched = []
            for i in issues:
                issue_addr = (i.get('address', '') or '').lower()
                # Match if any part of search address appears in issue address
                if any(part in issue_addr for part in address_parts if len(part) > 2):
                    matched.append(i)

            search_method = "text match (geocoding unavailable)"

        # Filter by type if specified
        if issue_type:
            issue_type_lower = issue_type.lower()
            matched = [i for i in matched if issue_type_lower in (i.get('issue_type', '') or '').lower()]

        result_parts = [
            f"# Issues Near: {address}",
            f"**Found:** {len(matched)} issues",
            f"**Method:** {search_method}",
            "",
        ]

        for i in matched[:30]:
            distance_str = ""
            if use_geocoding and "_distance_m" in i:
                distance_str = f" ({i['_distance_m']}m away)"

            result_parts.append(
                f"- **{i.get('issue_type', 'Issue')}**: {i.get('address', 'Unknown')}{distance_str}"
            )
            desc = (i.get('description') or '')[:100]
            if desc:
                result_parts.append(f"  > {desc}...")

        if not matched:
            if use_geocoding:
                result_parts.append(f"No issues found within {radius_blocks} blocks of this address.")
                result_parts.append("Try increasing radius_blocks or searching a nearby intersection.")
            else:
                result_parts.append("No issues matched this address text.")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error finding nearby issues: {str(e)}"


def find_repeat_issues(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Find locations with repeated issues."""
    issue_type = args.get("issue_type")
    min_occurrences = args.get("min_occurrences", 3)

    try:
        issues = civic._storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if issue_type:
            issue_type_lower = issue_type.lower()
            issues = [i for i in issues if issue_type_lower in (i.get('issue_type', '') or '').lower()]

        # Group by address
        address_counts = Counter(i.get('address', 'Unknown') for i in issues if i.get('address'))
        repeats = [(addr, count) for addr, count in address_counts.items() if count >= min_occurrences]
        repeats.sort(key=lambda x: -x[1])

        result_parts = [
            f"# Repeat Issue Locations",
            f"**Minimum occurrences:** {min_occurrences}",
            f"**Found:** {len(repeats)} locations with repeat issues",
            "",
        ]

        for addr, count in repeats[:20]:
            result_parts.append(f"- **{addr}**: {count} issues")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error finding repeat issues: {str(e)}"


def get_seasonal_patterns(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Analyze seasonal patterns in 311 issues."""
    issue_type = args.get("issue_type")

    try:
        issues = civic._storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if issue_type:
            issue_type_lower = issue_type.lower()
            issues = [i for i in issues if issue_type_lower in (i.get('issue_type', '') or '').lower()]

        by_month = Counter()
        for issue in issues:
            created = issue.get('created_at')
            if created:
                try:
                    if isinstance(created, str):
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    else:
                        dt = created
                    by_month[dt.strftime('%B')] += 1
                except:
                    continue

        result_parts = [
            f"# Seasonal Patterns",
            f"**Issue type:** {issue_type or 'All'}",
            "",
            "## Issues by Month",
        ]

        month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December']
        for month in month_order:
            count = by_month.get(month, 0)
            if count > 0:
                result_parts.append(f"- **{month}:** {count}")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error analyzing seasonal patterns: {str(e)}"


def compare_zip_codes(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Compare 311 issue patterns between zip codes."""
    zip_codes = args.get("zip_codes", [])

    if not zip_codes or len(zip_codes) < 2:
        return "Please provide at least 2 zip codes to compare."

    try:
        issues = civic._storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        result_parts = [f"# Zip Code Comparison", ""]

        for zip_code in zip_codes[:5]:
            zip_issues = [i for i in issues if zip_code in (i.get('address', '') or '')]
            type_counts = Counter(i.get('issue_type', 'Unknown') for i in zip_issues)

            result_parts.append(f"## {zip_code}")
            result_parts.append(f"**Total issues:** {len(zip_issues)}")
            for itype, count in type_counts.most_common(5):
                result_parts.append(f"- {itype}: {count}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error comparing zip codes: {str(e)}"


def neighborhood_report(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Generate neighborhood report."""
    neighborhood = args.get("neighborhood", "")

    issues_result = geo_search_issues(civic, jurisdiction, validate_input, logger, {"area": neighborhood})

    return f"# Neighborhood Report: {neighborhood}\n\n{issues_result}"


# ─────────── Council/Voting Handlers ───────────


def get_voting_record(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get an elected official's voting record."""
    official_name = args.get("official_name", "")
    topic = args.get("topic")
    since = args.get("since")

    is_valid, sanitized, error = validate_input({"official_name": official_name})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    try:
        record = civic.get_voting_record(
            official_name=official_name,
            topic=topic,
            since=since,
        )

        result_parts = [
            f"# Voting Record: {record.official_name}",
            "",
            "## Summary",
            f"- **Total Votes:** {record.total_votes}",
            f"- **Yes Votes:** {record.yes_votes} ({record.yes_percentage:.0f}%)",
            f"- **No Votes:** {record.no_votes} ({record.no_percentage:.0f}%)",
            "",
        ]

        if record.decisions:
            result_parts.append("## Recent Votes")
            for d in record.decisions[:10]:
                vote_emoji = {"yes": "Y", "no": "N", "absent": "-"}.get(d.get('vote'), "?")
                result_parts.append(f"- [{vote_emoji}] {d.get('title', 'Item')[:60]} ({d.get('date', 'N/A')})")

        return "\n".join(result_parts)

    except ValueError as e:
        return f"Official not found: {official_name}"
    except Exception as e:
        return f"Error getting voting record: {str(e)}"


def get_decision_context(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get decisions with linked transcript excerpts."""
    query = args.get("query", "")
    limit = args.get("limit", 5)

    is_valid, sanitized, error = validate_input({"query": query})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    try:
        results = civic.what_happened_full_context(query, top_k=limit)

        result_parts = [f"# Decisions with Context: {query}", ""]

        if not results:
            return "No decisions found matching this query."

        for r in results:
            d = r.decision
            result_parts.append(f"## {d.title}")
            result_parts.append(f"- **Date:** {d.date}")
            result_parts.append(f"- **Outcome:** {d.outcome or 'N/A'}")
            result_parts.append("")

            if r.transcript_links:
                public_comments = [l for l in r.transcript_links if l.is_public_comment]
                if public_comments:
                    result_parts.append("### Public Testimony")
                    for link in public_comments[:3]:
                        speaker = link.speaker_name or "Resident"
                        result_parts.append(f"**{speaker}:** {link.text[:200]}...")
                        result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting decision context: {str(e)}"


# ─────────── Financial Handlers ───────────


def get_funding_flow(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Trace intergovernmental funding flow."""
    program = args.get("program")
    cfda_number = args.get("cfda_number")

    try:
        flows = civic.funding_flow(program=program, cfda_number=cfda_number)

        result_parts = [
            "# Intergovernmental Funding Flow",
            f"**Program:** {program or 'All'}" if program else "",
            "",
        ]

        if not flows:
            result_parts.append("No funding flows found matching criteria.")
            result_parts.append("Use search_budget() for budget data.")
            return "\n".join(result_parts)

        total = sum(f.budget_dollars for f in flows)
        result_parts.append(f"**Total Linked Budget:** ${total:,.0f}")
        result_parts.append("")

        for flow in flows[:10]:
            result_parts.append(f"## {flow.budget_description}")
            result_parts.append(f"- **Department:** {flow.department or 'N/A'}")
            result_parts.append(f"- **Budget:** ${flow.budget_dollars:,.0f}")
            if flow.federal_program_name:
                result_parts.append(f"- **Federal Source:** {flow.federal_program_name}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting funding flow: {str(e)}"


def get_federal_expenditures(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get audited federal expenditures from Single Audit."""
    audit_year = args.get("audit_year")

    try:
        summary = civic.federal_expenditures_summary(audit_year=audit_year)

        result_parts = [
            "# Federal Expenditures (Single Audit)",
            f"**Audit Year:** {summary.get('audit_year', 'N/A')}",
            f"**Total Federal Spending:** ${summary.get('total_dollars', 0):,.0f}",
            "",
        ]

        programs = summary.get('programs', [])
        if programs:
            result_parts.append("## By Program")
            for p in programs[:15]:
                result_parts.append(f"- **{p.get('cfda', 'N/A')}:** ${p.get('dollars', 0):,.0f}")
                if p.get('program_name'):
                    result_parts.append(f"  *{p.get('program_name')}*")
        else:
            result_parts.append("No federal expenditure data found.")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting federal expenditures: {str(e)}"


def get_intergovernmental_revenue(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get intergovernmental revenue from CA State Controller."""
    fiscal_year = args.get("fiscal_year")
    source = args.get("source")

    try:
        revenue = civic.intergovernmental_revenue(fiscal_year=fiscal_year, source=source)

        result_parts = [
            "# Intergovernmental Revenue",
            f"**Entity:** {revenue.entity_name}",
            f"**Fiscal Year:** {revenue.fiscal_year}",
            f"**Total Revenue:** ${revenue.total_dollars:,.0f}",
            "",
            "## By Source",
            f"- **Federal:** ${revenue.federal_total_dollars:,.0f}",
            f"- **State:** ${revenue.state_total_dollars:,.0f}",
            f"- **County:** ${revenue.county_total_dollars:,.0f}",
        ]

        if revenue.undetermined_total_dollars > 0:
            result_parts.append(f"- **Undetermined:** ${revenue.undetermined_total_dollars:,.0f}")

        # Show top details if available
        if revenue.details:
            result_parts.extend(["", "## Top Line Items"])
            for detail in revenue.details[:10]:
                desc = detail.line_description or detail.category or "Unknown"
                result_parts.append(
                    f"- {desc}: ${detail.amount_dollars:,.0f} ({detail.source})"
                )

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting intergovernmental revenue: {str(e)}"


# ─────────── Action Handlers ───────────


def get_comment_template(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get a fill-in-the-blank public comment template."""
    item_title = args.get("item_title", "")
    stance = args.get("stance")
    key_points = args.get("key_points")

    parts = [
        f"Re: {item_title}",
        "",
        "Dear Mayor and Council Members,",
        "",
    ]

    if stance:
        stance_text = {
            "support": "I am writing to express my support for this agenda item.",
            "oppose": "I am writing to express my concerns about this agenda item.",
            "question": "I am writing to request clarification about this agenda item.",
            "neutral": "I am writing to provide input on this agenda item."
        }
        parts.append(stance_text.get(stance.lower(), "I am writing to provide input on this agenda item."))
    else:
        parts.append("I am writing to provide input on this agenda item.")

    parts.append("")

    if key_points:
        parts.append("Key points:")
        for point in key_points.split("\n"):
            if point.strip():
                parts.append(f"- {point.strip()}")
    else:
        parts.append("Please consider the following:")
        parts.append("- [Your specific concerns or suggestions here]")
        parts.append("- [Impact on residents/community]")
        parts.append("- [Alternatives or modifications to consider]")

    parts.extend([
        "",
        "Thank you for your consideration and service to our community.",
        "",
        "Sincerely,",
        "[Your Name]",
        "[Your Address in San Rafael]",
    ])

    return "\n".join(parts)


def prepare_for_meeting(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get preparation materials for a city council meeting."""
    agenda_item_id = args.get("agenda_item_id", "")

    is_valid, sanitized, error = validate_input({"agenda_item_id": agenda_item_id})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    try:
        prep = civic.prepare(agenda_item_id)

        result_parts = [
            f"# Meeting Preparation",
            f"**Agenda Item:** {prep.agenda_item_id}",
            "",
            "## Logistics",
        ]

        if prep.logistics:
            if prep.logistics.get('meeting_title'):
                result_parts.append(f"- **Meeting:** {prep.logistics['meeting_title']}")
            if prep.logistics.get('meeting_datetime'):
                result_parts.append(f"- **When:** {prep.logistics['meeting_datetime']}")
            if prep.logistics.get('location'):
                result_parts.append(f"- **Where:** {prep.logistics['location']}")
        result_parts.append("")

        result_parts.append("## Talking Points")
        if prep.talking_points:
            for point in prep.talking_points:
                result_parts.append(f"- {point}")
        else:
            result_parts.append("- Introduce yourself and state your position")
            result_parts.append("- Explain why this matters to you")
            result_parts.append("- Request a specific action from the council")

        return "\n".join(result_parts)

    except ValueError:
        return f"Agenda item not found: {agenda_item_id}. Use get_upcoming_meetings() to find valid agenda item IDs."
    except Exception as e:
        return f"Error preparing for meeting: {str(e)}"


# ─────────── Coordination Handlers ───────────
#
# These handlers implement a permissionless coordination protocol.
# Key principles:
# - Users can specify their own relay (relay_url parameter)
# - Default relay is provided for convenience, not lock-in
# - Voices are cryptographically signed - signatures are the authority
# - Two-step voice flow: prepare_voice -> sign locally -> broadcast_voice

# Known relays in the CivicOS network
KNOWN_RELAYS = [
    {
        "name": "CivicOS Primary",
        "url": "https://api.civicosproject.org",
        "description": "Official CivicOS relay. Operated by the CivicOS project.",
        "default": True,
    },
    # Future: community relays can be added here
    # {
    #     "name": "Community Relay",
    #     "url": "https://relay.example.org",
    #     "description": "Community-operated relay.",
    #     "default": False,
    # },
]


def _get_default_relay_url() -> str:
    """Get the default relay URL."""
    import os
    # Allow override via environment for development
    env_url = os.environ.get("CIVICOS_RELAY_URL")
    if env_url:
        return env_url
    # Fall back to API URL for backwards compatibility
    api_url = os.environ.get("CIVICOS_API_URL")
    if api_url:
        return api_url
    # Default to localhost relay port for local dev
    return "http://localhost:8003"


def _save_voice_receipt(payload: dict, relay_urls: list, logger) -> None:
    """Save a local receipt of the signed voice before broadcasting."""
    import json
    import os
    import time
    from pathlib import Path

    receipts_dir = Path.home() / ".civicos"
    receipts_file = receipts_dir / "voice_receipts.jsonl"

    try:
        receipts_dir.mkdir(exist_ok=True)
        receipt = {
            **payload,
            "target_relays": relay_urls,
            "saved_at": int(time.time()),
        }
        with open(receipts_file, "a") as f:
            f.write(json.dumps(receipt) + "\n")
    except Exception as e:
        logger.warning(f"Failed to save voice receipt: {e}")


def _resolve_relay_url(relay_url: str | None) -> str:
    """Resolve relay URL, using default if not specified."""
    if relay_url:
        # Normalize URL (remove trailing slash)
        return relay_url.rstrip("/")
    return _get_default_relay_url()


def get_voice_counts(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get community voice counts for a civic entity from a relay."""
    import httpx

    entity = args.get("entity", "")
    relay_url = _resolve_relay_url(args.get("relay_url"))

    is_valid, sanitized, error = validate_input({"entity": entity})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    entity = sanitized.get("entity", entity)

    try:
        url = f"{relay_url}/coordination/voice/counts/{entity}"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)

            if response.status_code == 503:
                return f"Relay at {relay_url} is not available. Try a different relay or check if the service is running."

            if response.status_code != 200:
                logger.warning(f"Voice counts from {relay_url} returned {response.status_code}: {response.text}")
                return f"Unable to get voice counts from relay: {response.text}"

            data = response.json()

        result_parts = [
            f"# Voice Counts: {entity}",
            f"**Relay:** {relay_url}",
            "",
            f"**Support:** {data.get('support', 0)}",
            f"**Oppose:** {data.get('oppose', 0)}",
            f"**Watching:** {data.get('watching', 0)}",
            f"**Total voices:** {data.get('total', 0)}",
            "",
            "_Voices are cryptographically signed. Counts can be verified by any relay with the same data._",
        ]

        return "\n".join(result_parts)

    except httpx.ConnectError:
        return f"Unable to connect to relay at {relay_url}. The relay may be offline or the URL may be incorrect."
    except Exception as e:
        logger.error(f"Error getting voice counts: {e}")
        return f"Error getting voice counts: {str(e)}"


def subscribe_to_topic(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Subscribe to email notifications about civic topics via a relay."""
    import httpx

    topics = args.get("topics", [])
    email = args.get("email", "")
    relay_url = _resolve_relay_url(args.get("relay_url"))

    # Validate email format
    if not email or "@" not in email:
        return "Error: Invalid email address"

    if not topics:
        return "Error: Must provide at least one topic to subscribe to"

    is_valid, sanitized, error = validate_input({"email": email})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    try:
        url = f"{relay_url}/coordination/subscribe"

        payload = {
            "jurisdiction": jurisdiction,
            "topics": topics,
            "email": email,
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload)

            if response.status_code == 503:
                return f"Relay at {relay_url} is not available. Try a different relay."

            if response.status_code != 200:
                logger.warning(f"Subscribe to {relay_url} returned {response.status_code}: {response.text}")
                return f"Unable to create subscription: {response.text}"

            data = response.json()

        result_parts = [
            "# Subscription Created",
            f"**Relay:** {relay_url}",
            "",
            f"**Subscription ID:** {data.get('id', 'N/A')}",
            f"**Jurisdiction:** {data.get('jurisdiction', jurisdiction)}",
            f"**Topics:** {', '.join(topics)}",
            f"**Email:** {email}",
            "",
            "You will receive notifications from this relay when there are updates related to these topics.",
            "",
            "_Your subscription is stored at this relay. You can switch relays or run your own._",
            f"_To unsubscribe, contact the relay with subscription ID: {data.get('id', 'N/A')}_",
        ]

        return "\n".join(result_parts)

    except httpx.ConnectError:
        return f"Unable to connect to relay at {relay_url}. The relay may be offline or the URL may be incorrect."
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        return f"Error creating subscription: {str(e)}"


def prepare_voice(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """
    Prepare a voice payload for signing.

    Returns the exact message to sign with your private key.
    This is step 1 of the two-step voice casting process.
    """
    entity = args.get("entity", "")
    stance = args.get("stance", "")

    is_valid, sanitized, error = validate_input({"entity": entity, "stance": stance})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    entity = sanitized.get("entity", entity)
    stance = sanitized.get("stance", stance)

    # Validate stance
    valid_stances = ["support", "oppose", "watching"]
    if stance not in valid_stances:
        return f"Error: Invalid stance '{stance}'. Must be one of: {', '.join(valid_stances)}"

    # Generate timestamp (UTC, timezone-aware)
    from datetime import timezone
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Construct the canonical message to sign
    # Format: civicos:voice:v1:{entity}:{stance}:{timestamp}
    message = f"civicos:voice:v1:{entity}:{stance}:{timestamp}"

    result_parts = [
        "# Voice Payload Ready for Signing",
        "",
        "## What You're Signing",
        f"**Entity:** {entity}",
        f"**Stance:** {stance}",
        f"**Timestamp:** {timestamp}",
        "",
        "## Message to Sign",
        "Sign this exact string with your ECDSA P-256 private key:",
        "",
        "```",
        message,
        "```",
        "",
        "## How to Sign",
        "",
        "**Using OpenSSL (command line):**",
        "```bash",
        f'echo -n "{message}" | openssl dgst -sha256 -sign your_private_key.pem | xxd -p -c 256',
        "```",
        "",
        "**Using Python:**",
        "```python",
        "from cryptography.hazmat.primitives import hashes",
        "from cryptography.hazmat.primitives.asymmetric import ec",
        f'message = b"{message}"',
        "signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))",
        "print(signature.hex())",
        "```",
        "",
        "## Next Step",
        "After signing, use `broadcast_voice` with:",
        f"- entity: {entity}",
        f"- stance: {stance}",
        "- public_key: (your public key, hex-encoded)",
        "- signature: (the signature you just created, hex-encoded)",
        "",
        "_Your private key never leaves your device. Only the signature is broadcast._",
    ]

    return "\n".join(result_parts)


def broadcast_voice(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """
    Broadcast a signed voice to relay node(s).

    This is step 2 of the two-step voice casting process.
    The signature proves you authorized this voice without revealing your private key.
    """
    import httpx

    entity = args.get("entity", "")
    stance = args.get("stance", "")
    public_key = args.get("public_key", "")
    signature = args.get("signature", "")
    created_at = args.get("created_at")
    voice_jurisdiction = args.get("jurisdiction", "")
    relay_urls = args.get("relay_urls", [])

    # Validate required fields
    if not entity:
        return "Error: entity is required"
    if not stance:
        return "Error: stance is required"
    if not public_key:
        return "Error: public_key is required"
    if not signature:
        return "Error: signature is required"
    if created_at is None:
        return "Error: created_at is required (Unix timestamp from signed Nostr event)"

    is_valid, sanitized, error = validate_input({
        "entity": entity,
        "stance": stance,
        "public_key": public_key,
    })
    if not is_valid:
        return f"Error: Invalid input - {error}"

    # Validate stance
    valid_stances = ["support", "oppose", "watching"]
    if stance not in valid_stances:
        return f"Error: Invalid stance '{stance}'. Must be one of: {', '.join(valid_stances)}"

    # Use default relay if none specified
    if not relay_urls:
        relay_urls = [_get_default_relay_url()]

    # Broadcast to all specified relays
    results = []
    payload = {
        "entity": entity,
        "stance": stance,
        "public_key": public_key,
        "signature": signature,
        "created_at": created_at,
    }
    if voice_jurisdiction:
        payload["jurisdiction"] = voice_jurisdiction

    # Save local receipt before broadcasting
    _save_voice_receipt(payload, relay_urls, logger)

    for relay_url in relay_urls:
        relay_url = relay_url.rstrip("/")
        try:
            url = f"{relay_url}/coordination/voice"

            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)

                if response.status_code == 200:
                    results.append({"relay": relay_url, "status": "success"})
                elif response.status_code == 400:
                    error_detail = response.json().get("detail", response.text)
                    results.append({"relay": relay_url, "status": "rejected", "error": error_detail})
                elif response.status_code == 503:
                    results.append({"relay": relay_url, "status": "unavailable"})
                else:
                    results.append({"relay": relay_url, "status": "error", "error": response.text})

        except httpx.ConnectError:
            results.append({"relay": relay_url, "status": "unreachable"})
        except Exception as e:
            logger.error(f"Error broadcasting to {relay_url}: {e}")
            results.append({"relay": relay_url, "status": "error", "error": str(e)})

    # Format results
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] != "success"]

    result_parts = [
        "# Voice Broadcast Results",
        "",
        f"**Entity:** {entity}",
        f"**Stance:** {stance}",
        f"**Public Key:** {public_key[:16]}...{public_key[-8:]}",
        "",
    ]

    if successes:
        result_parts.append(f"## Accepted by {len(successes)} relay(s)")
        for r in successes:
            result_parts.append(f"- {r['relay']}")
        result_parts.append("")

    if failures:
        result_parts.append(f"## Failed on {len(failures)} relay(s)")
        for r in failures:
            error_msg = r.get("error", r["status"])
            result_parts.append(f"- {r['relay']}: {error_msg}")
        result_parts.append("")

    if successes:
        result_parts.extend([
            "_Your voice is now recorded. The cryptographic signature proves you authorized it._",
            "_Other relays can verify the signature and replicate your voice._",
        ])
    else:
        result_parts.extend([
            "**No relays accepted the voice.** Check the error messages above.",
            "Common issues:",
            "- Invalid signature (message didn't match what you signed)",
            "- Malformed public key or signature (should be hex-encoded)",
            "- Relay is offline or unreachable",
        ])

    return "\n".join(result_parts)


def list_relays(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """List known relay nodes in the CivicOS network."""
    result_parts = [
        "# Known CivicOS Relays",
        "",
        "These are relay nodes that participate in the CivicOS coordination network.",
        "You can use any of these, or run your own relay.",
        "",
    ]

    for relay in KNOWN_RELAYS:
        default_marker = " **(default)**" if relay.get("default") else ""
        result_parts.extend([
            f"## {relay['name']}{default_marker}",
            f"**URL:** {relay['url']}",
            f"**Description:** {relay['description']}",
            "",
        ])

    result_parts.extend([
        "## Running Your Own Relay",
        "",
        "The relay protocol is open. To run your own:",
        "1. Deploy the civicos-relay package",
        "2. Configure your database (PostgreSQL with pgvector)",
        "3. Announce your relay URL to peers",
        "",
        "Your relay will validate signatures and can replicate voices from other relays.",
        "",
        "_In a permissionless network, no single relay is authoritative._",
        "_Cryptographic signatures are the source of truth._",
    ])

    return "\n".join(result_parts)


# === Initiative Tools ===


def _generate_initiative_id(jurisdiction: str, title: str) -> str:
    """Generate deterministic initiative ID."""
    import hashlib
    from datetime import date

    today = date.today().isoformat()
    title_hash = hashlib.sha256(title.encode()).hexdigest()[:8]
    return f"initiative:{jurisdiction}:{today}:{title_hash}"


def _create_initiative_message(
    initiative_id: str, topic: str, title: str, timestamp: str
) -> str:
    """Create the message that must be signed for initiative creation."""
    import hashlib

    title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
    return f"civicos:initiative:v1:{initiative_id}:{topic}:{title_hash}:{timestamp}"


def prepare_initiative(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """
    Prepare an initiative payload for signing.

    Returns the exact message to sign with your private key.
    This is step 1 of the two-step initiative creation process.
    """
    topic = args.get("topic", "")
    title = args.get("title", "")
    description = args.get("description", "")
    location = args.get("location")

    # Validate required fields
    is_valid, sanitized, error = validate_input({
        "topic": topic,
        "title": title,
        "description": description,
    })
    if not is_valid:
        return f"Error: Invalid input - {error}"

    topic = sanitized.get("topic", topic)
    title = sanitized.get("title", title)
    description = sanitized.get("description", description)

    if not topic or not title or not description:
        return "Error: topic, title, and description are required"

    # Generate initiative ID and timestamp
    from datetime import timezone

    initiative_id = _generate_initiative_id(jurisdiction, title)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Construct the canonical message to sign
    message = _create_initiative_message(initiative_id, topic, title, timestamp)

    result_parts = [
        "# Initiative Payload Ready for Signing",
        "",
        "## Your Initiative",
        f"**ID:** {initiative_id}",
        f"**Jurisdiction:** {jurisdiction}",
        f"**Topic:** {topic}",
        f"**Title:** {title}",
        f"**Description:** {description}",
    ]
    if location:
        result_parts.append(f"**Location:** {location}")

    result_parts.extend([
        f"**Timestamp:** {timestamp}",
        "",
        "## Message to Sign",
        "Sign this exact string with your ECDSA P-256 private key:",
        "",
        "```",
        message,
        "```",
        "",
        "## How to Sign",
        "",
        "**Using Python:**",
        "```python",
        "from cryptography.hazmat.primitives import hashes",
        "from cryptography.hazmat.primitives.asymmetric import ec",
        f'message = b"{message}"',
        "signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))",
        "print(signature.hex())",
        "```",
        "",
        "## Next Step",
        "After signing, use `broadcast_initiative` with:",
        f"- topic: {topic}",
        f"- title: {title}",
        f"- description: {description}",
    ])
    if location:
        result_parts.append(f"- location: {location}")
    result_parts.extend([
        "- public_key: YOUR_PUBLIC_KEY_HEX",
        "- signature: YOUR_SIGNATURE_HEX",
        "",
        "_Your private key never leaves your device._",
        "_The signature cryptographically proves you authorized this initiative._",
    ])

    return "\n".join(result_parts)


def broadcast_initiative(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """
    Broadcast a signed initiative to relay(s).

    This is step 2 of the two-step initiative creation process.
    The initiative must be signed by the creator's private key.
    """
    topic = args.get("topic", "")
    title = args.get("title", "")
    description = args.get("description", "")
    location = args.get("location")
    public_key = args.get("public_key", "")
    signature = args.get("signature", "")
    relay_urls = args.get("relay_urls", [])

    # Validate required fields
    is_valid, sanitized, error = validate_input({
        "topic": topic,
        "title": title,
        "description": description,
        "public_key": public_key,
        "signature": signature,
    })
    if not is_valid:
        return f"Error: Invalid input - {error}"

    topic = sanitized.get("topic", topic)
    title = sanitized.get("title", title)
    description = sanitized.get("description", description)
    public_key = sanitized.get("public_key", public_key)
    signature = sanitized.get("signature", signature)

    if not all([topic, title, description, public_key, signature]):
        return "Error: topic, title, description, public_key, and signature are required"

    # Use default relay if none specified
    if not relay_urls:
        relay_urls = [_get_default_relay_url()]

    import httpx

    # Broadcast to all specified relays
    results = []
    payload = {
        "jurisdiction": jurisdiction,
        "topic": topic,
        "title": title,
        "description": description,
        "location": location,
        "public_key": public_key,
        "signature": signature,
    }

    for relay_url in relay_urls:
        relay_url = relay_url.rstrip("/")
        try:
            url = f"{relay_url}/coordination/initiative"

            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)

                if response.status_code == 200:
                    data = response.json()
                    results.append({
                        "relay": relay_url,
                        "status": "success",
                        "initiative_id": data.get("id"),
                    })
                elif response.status_code == 400:
                    error_detail = response.json().get("detail", response.text)
                    results.append({"relay": relay_url, "status": "rejected", "error": error_detail})
                elif response.status_code == 409:
                    error_detail = response.json().get("detail", "Initiative already exists")
                    results.append({"relay": relay_url, "status": "duplicate", "error": error_detail})
                elif response.status_code == 503:
                    results.append({"relay": relay_url, "status": "unavailable"})
                else:
                    results.append({"relay": relay_url, "status": "error", "error": response.text})

        except httpx.ConnectError:
            results.append({"relay": relay_url, "status": "unreachable"})
        except Exception as e:
            logger.error(f"Error broadcasting to {relay_url}: {e}")
            results.append({"relay": relay_url, "status": "error", "error": str(e)})

    # Format results
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] != "success"]

    result_parts = [
        "# Initiative Broadcast Results",
        "",
        f"**Title:** {title}",
        f"**Topic:** {topic}",
        f"**Jurisdiction:** {jurisdiction}",
        f"**Creator:** {public_key[:16]}...{public_key[-8:]}",
        "",
    ]

    if successes:
        result_parts.append(f"## Created on {len(successes)} relay(s)")
        for r in successes:
            result_parts.append(f"- {r['relay']}")
            result_parts.append(f"  **ID:** {r.get('initiative_id', 'N/A')}")
        result_parts.append("")

    if failures:
        result_parts.append(f"## Failed on {len(failures)} relay(s)")
        for r in failures:
            error_msg = r.get("error", r["status"])
            result_parts.append(f"- {r['relay']}: {error_msg}")
        result_parts.append("")

    if successes:
        initiative_id = successes[0].get("initiative_id", "N/A")
        result_parts.extend([
            f"_Your initiative is now live. People can voice on it using entity: {initiative_id}_",
            "_The cryptographic signature proves you created it._",
            "_Other relays can verify the signature and replicate your initiative._",
        ])
    else:
        result_parts.extend([
            "**No relays accepted the initiative.** Check the error messages above.",
            "Common issues:",
            "- Invalid signature (message didn't match what you signed)",
            "- Initiative already exists (same title on same day)",
            "- Relay is offline or unreachable",
        ])

    return "\n".join(result_parts)


def list_initiatives(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """
    List initiatives from a relay node.

    Query community-created initiatives for a jurisdiction.
    """
    topic = args.get("topic")
    status = args.get("status")
    relay_url = args.get("relay_url")
    limit = args.get("limit", 20)

    # Use default relay if none specified
    if not relay_url:
        relay_url = _get_default_relay_url()

    relay_url = relay_url.rstrip("/")

    import httpx

    try:
        # Build query params
        params = {}
        if topic:
            params["topic"] = topic
        if status:
            params["status"] = status
        if limit:
            params["limit"] = min(int(limit), 100)

        url = f"{relay_url}/coordination/initiatives/{jurisdiction}"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)

            if response.status_code != 200:
                return f"Error querying relay: {response.text}"

            initiatives = response.json()

        if not initiatives:
            result_parts = [
                "# No Initiatives Found",
                "",
                f"**Jurisdiction:** {jurisdiction}",
                f"**Relay:** {relay_url}",
            ]
            if topic:
                result_parts.append(f"**Topic filter:** {topic}")
            if status:
                result_parts.append(f"**Status filter:** {status}")
            result_parts.extend([
                "",
                "No initiatives match your query.",
                "",
                "_Use `prepare_initiative` to create a new initiative._",
            ])
            return "\n".join(result_parts)

        result_parts = [
            f"# Initiatives in {jurisdiction}",
            "",
            f"**Relay:** {relay_url}",
        ]
        if topic:
            result_parts.append(f"**Topic filter:** {topic}")
        if status:
            result_parts.append(f"**Status filter:** {status}")
        result_parts.extend([
            f"**Found:** {len(initiatives)} initiative(s)",
            "",
        ])

        for i in initiatives:
            voice_count = i.get("voice_count", 0)
            status_badge = f"[{i.get('status', 'active').upper()}]"
            result_parts.extend([
                f"## {i.get('title', 'Untitled')} {status_badge}",
                f"**ID:** `{i.get('id', 'N/A')}`",
                f"**Topic:** {i.get('topic', 'N/A')}",
                f"**Voices:** {voice_count}",
                f"**Creator:** {i.get('public_key', 'N/A')[:16]}...",
                f"**Created:** {i.get('timestamp', 'N/A')}",
                "",
                i.get("description", "")[:200] + ("..." if len(i.get("description", "")) > 200 else ""),
                "",
            ])

        result_parts.extend([
            "---",
            "_Voice on an initiative using `prepare_voice` with the initiative ID as the entity._",
            "_Create your own initiative using `prepare_initiative`._",
        ])

        return "\n".join(result_parts)

    except httpx.ConnectError:
        return f"Unable to connect to relay at {relay_url}. The relay may be offline."
    except Exception as e:
        logger.error(f"Error listing initiatives: {e}")
        return f"Error listing initiatives: {str(e)}"
