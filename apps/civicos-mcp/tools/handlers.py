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
import re


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


# Legiscan progress status codes → friendly labels
LEGISCAN_STATUS = {
    "1": "Introduced",
    "2": "Engrossed",
    "3": "Enrolled",
    "4": "Passed",
    "5": "Vetoed",
    "6": "Failed",
}

# Map status labels → outcome categories for icon/color rendering
LEGISLATIVE_OUTCOME_MAP = {
    "Passed": "passed",
    "Enrolled": "passed",
    "Engrossed": "on_agenda",
    "Introduced": "on_agenda",
    "Vetoed": "failed",
    "Failed": "failed",
}


def _resolve_bill_status(bill: dict) -> tuple[str, str]:
    """Return (friendly_label, outcome_category) for a bill's status.

    Handles both Legiscan numeric codes and curated text statuses.
    """
    raw = bill.get("status", "")
    # Legiscan numeric code
    if raw in LEGISCAN_STATUS:
        label = LEGISCAN_STATUS[raw]
        return label, LEGISLATIVE_OUTCOME_MAP.get(label, "other")
    # Curated text status
    if isinstance(raw, str) and raw:
        sl = raw.lower()
        if "passed" in sl or "signed" in sl or "enacted" in sl:
            return raw, "passed"
        if "failed" in sl or "dead" in sl or "vetoed" in sl:
            return raw, "failed"
        # Active, Pending, etc.
        return raw, "on_agenda"
    return "Unknown", "other"


def _bill_date(bill: dict) -> str:
    """Best available date for a bill.

    Prefers action/enacted dates over ingestion timestamps.
    Returns empty string if only an ingestion date is available.
    """
    return (
        bill.get("last_action_date")
        or bill.get("enacted_date")
        or ""
    )


def _legislation_pulse(
    civic: CivicClient,
    jurisdiction: str,
    logger: Logger,
) -> dict:
    """Generate pulse data from legislation for state/federal servers.

    Sections:
      decisions_this_week → Topic overview (topic name, bill counts, stage breakdown)
      upcoming_items      → Key legislation (bills with leverage points, by topic)
      recent_outcomes     → Bill activity (proper status labels and dates)
    """
    now = datetime.now()
    storage = civic._storage

    # Determine state code from jurisdiction
    if jurisdiction.startswith("country-"):
        state = "US"
    elif jurisdiction.startswith("state-"):
        state = "CA"
    else:
        state = "CA"

    result = {
        "jurisdiction": jurisdiction,
        "generated_at": now.isoformat(),
        "decisions_this_week": [],
        "upcoming_items": [],
        "recent_outcomes": [],
        "community_pulse": {},
    }

    try:
        bills = storage.get_legislation(state=state, limit=500)

        # ── Resolve statuses for all bills ──
        for b in bills:
            b["_label"], b["_outcome"] = _resolve_bill_status(b)

        # ── Section 1: Topic overview ──
        # Group bills by topic and count by stage
        topic_counts: dict[str, dict] = {}
        for b in bills:
            topic = b.get("topic") or "other"
            if topic not in topic_counts:
                topic_counts[topic] = {"total": 0, "active": 0, "passed": 0, "failed": 0}
            tc = topic_counts[topic]
            tc["total"] += 1
            if b["_outcome"] == "passed":
                tc["passed"] += 1
            elif b["_outcome"] == "failed":
                tc["failed"] += 1
            else:
                tc["active"] += 1

        # Sort topics: named topics by count desc, "other"/None last
        def _topic_sort_key(item: tuple) -> tuple:
            name, counts = item
            is_other = name in (None, "other", "Other", "")
            return (is_other, -counts["total"])

        sorted_topics = sorted(topic_counts.items(), key=_topic_sort_key)
        named_topics = [(n, c) for n, c in sorted_topics
                        if n not in (None, "other", "Other", "")]

        if named_topics:
            # Show topic breakdown (categories with real names)
            for topic_name, counts in sorted_topics[:8]:
                label = topic_name.replace("_", " ").title() if topic_name else "Other"
                parts = []
                if counts["active"]:
                    parts.append(f"{counts['active']} active")
                if counts["passed"]:
                    parts.append(f"{counts['passed']} passed")
                if counts["failed"]:
                    parts.append(f"{counts['failed']} failed")
                result["decisions_this_week"].append({
                    "title": f"{label}",
                    "date": f"{counts['total']} bills",
                    "time": " · ".join(parts),
                    "location": "",
                    "meeting_datetime": now.isoformat(),
                })
        else:
            # No topic data — show stage-based overview instead
            stage_counts = Counter(b["_label"] for b in bills)
            for stage_label, count in stage_counts.most_common():
                result["decisions_this_week"].append({
                    "title": stage_label,
                    "date": f"{count} bills",
                    "time": "",
                    "location": "",
                    "meeting_datetime": now.isoformat(),
                })

        # ── Section 2: Key legislation (actionable bills) ──
        actionable = [b for b in bills if b.get("leverage_point")]
        for bill in actionable[:10]:
            topic = bill.get("topic") or ""
            topic_label = topic.replace("_", " ").title() if topic else ""
            result["upcoming_items"].append({
                "id": bill.get("bill_id", ""),
                "item_number": bill.get("bill_number", ""),
                "title": bill.get("bill_name", "Untitled Bill"),
                "project_type": topic_label,
                "stance_eligible": True,
                "comment_eligible": False,
                "description": bill.get("leverage_point", ""),
                "summary": bill.get("summary", ""),
                "status": bill["_label"],
                "official_url": bill.get("official_url", ""),
                "meeting_title": bill.get("bill_number", ""),
                "meeting_date": "",
            })

        # ── Section 3: Bill activity (resolved + notable) ──
        # Mix of resolved (passed/vetoed/failed) and notable active bills
        resolved = [b for b in bills if b["_outcome"] in ("passed", "failed")]
        active_with_lp = [b for b in bills
                          if b["_outcome"] not in ("passed", "failed")
                          and b.get("leverage_point")]

        # Sort each group by date descending (most recent first)
        def _by_date_desc(b: dict) -> str:
            return _bill_date(b) or "0000"

        resolved.sort(key=_by_date_desc, reverse=True)
        active_with_lp.sort(key=_by_date_desc, reverse=True)

        ordered = resolved[:7] + active_with_lp[:3]

        for bill in ordered:
            result["recent_outcomes"].append({
                "id": bill.get("bill_id", ""),
                "title": f"{bill.get('bill_number', '')} — {bill.get('bill_name', 'Bill')}",
                "outcome": bill["_label"],
                "is_upcoming": bill["_outcome"] == "on_agenda",
                "date": _bill_date(bill),
                "summary": bill.get("summary", ""),
                "official_url": bill.get("official_url", ""),
            })

        # ── Community pulse: topic breakdown ──
        topic_summary = {}
        for topic_name, counts in sorted_topics[:6]:
            label = topic_name.replace("_", " ").title() if topic_name else "Other"
            topic_summary[label] = counts["total"]
        result["community_pulse"] = {
            "total_issues": len(bills),
            "top_types": topic_summary,
        }

    except Exception as e:
        logger.error(f"Error in legislation_pulse: {e}")
        result["error"] = str(e)
        bills = []

    # ── Federal comment periods (open proposed rules) ──
    try:
        open_rules = storage.get_open_comment_periods(limit=10)
        if open_rules:
            comment_periods = []
            for rule in open_rules:
                close_date = rule.get("comments_close_on")
                days_remaining = None
                if close_date:
                    if hasattr(close_date, 'date'):
                        close_dt = close_date.date()
                    elif isinstance(close_date, str):
                        close_dt = datetime.strptime(close_date[:10], "%Y-%m-%d").date()
                    else:
                        close_dt = close_date
                    days_remaining = (close_dt - now.date()).days

                agency_names = rule.get("agency_names") or []
                if isinstance(agency_names, str):
                    agency_names = [agency_names]

                comment_periods.append({
                    "document_number": rule.get("document_number", ""),
                    "title": rule.get("title", ""),
                    "abstract": rule.get("abstract", ""),
                    "agency_names": agency_names,
                    "comments_close_on": str(close_date) if close_date else None,
                    "days_remaining": days_remaining,
                    "comment_url": rule.get("comment_url", ""),
                    "html_url": rule.get("html_url", ""),
                    "document_type": rule.get("document_type", ""),
                    "topics": rule.get("topics") or [],
                    "pdf_url": rule.get("pdf_url", ""),
                    "publication_date": str(rule["publication_date"]) if rule.get("publication_date") else None,
                })
            result["comment_periods"] = comment_periods
    except Exception as e:
        logger.error(f"Error fetching comment periods: {e}")

    # ── Upcoming legislative hearings ──
    try:
        hearings = storage.get_upcoming_hearings(state=state, days_ahead=30, limit=10)
        if hearings:
            upcoming_hearings = []
            for h in hearings:
                event_date = h.get("event_date")
                days_until = None
                if event_date:
                    if hasattr(event_date, 'date'):
                        event_dt = event_date.date()
                    elif isinstance(event_date, str):
                        event_dt = datetime.strptime(event_date[:10], "%Y-%m-%d").date()
                    else:
                        event_dt = event_date
                    days_until = (event_dt - now.date()).days

                upcoming_hearings.append({
                    "bill_id": h.get("bill_id", ""),
                    "bill_number": h.get("bill_number", ""),
                    "bill_name": h.get("bill_name", ""),
                    "event_type": h.get("event_type", "hearing"),
                    "event_date": str(event_date) if event_date else None,
                    "days_until": days_until,
                    "committee": h.get("committee", ""),
                    "description": h.get("description", ""),
                    "summary": h.get("bill_summary", ""),
                    "official_url": h.get("official_url", ""),
                })
            result["upcoming_hearings"] = upcoming_hearings
    except Exception as e:
        logger.error(f"Error fetching upcoming hearings: {e}")

    # ── Governor's desk (enrolled bills awaiting signature) ──
    # LegiScan status 3 = Enrolled (passed both chambers, awaiting governor)
    try:
        enrolled = storage.get_legislation(state=state, status="3", limit=20)
        if not enrolled:
            # Fallback: try text status values
            enrolled = storage.get_legislation(state=state, status="Enrolled", limit=20)
        if enrolled:
            governors_desk = []
            for bill in enrolled:
                governors_desk.append({
                    "bill_id": bill.get("bill_id", ""),
                    "bill_number": bill.get("bill_number", ""),
                    "bill_name": bill.get("bill_name", bill.get("title", "")),
                    "summary": bill.get("summary", ""),
                })
            result["governors_desk"] = governors_desk
    except Exception as e:
        logger.error(f"Error fetching governor's desk bills: {e}")

    # Clean up internal fields added during processing
    for b in bills:
        b.pop("_label", None)
        b.pop("_outcome", None)

    return result


def city_pulse(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> dict:
    """Get comprehensive civic activity snapshot. Returns meetings/decisions for
    city-level servers, legislation/bills for state/federal servers."""
    # State/federal: return legislation pulse instead of meeting-centric data
    if jurisdiction.startswith("state-") or jurisdiction.startswith("country-"):
        return _legislation_pulse(civic, jurisdiction, logger)

    days_ahead = args.get("days_ahead", 7)
    days_back = args.get("days_back", 30)

    now = datetime.now()
    storage = civic._storage

    result = {
        "jurisdiction": jurisdiction,
        "generated_at": now.isoformat(),
        "decisions_this_week": [],
        "upcoming_items": [],
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

        # Sort by date ascending (soonest meetings first so their items take priority)
        meetings = sorted(meetings, key=lambda m: m.get('meeting_datetime') or now)

        # Collect upcoming agenda items from future meetings
        upcoming_items = []
        for m in meetings:
            meeting_dt = m.get('meeting_datetime')
            if isinstance(meeting_dt, str):
                try:
                    meeting_dt = datetime.fromisoformat(meeting_dt.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    meeting_dt = None
            if meeting_dt and hasattr(meeting_dt, 'strftime') and meeting_dt > now:
                items = storage.get_agenda_items(meeting_id=m.get('id'))
                for item in items:
                    upcoming_items.append({
                        "id": item.get('id'),
                        "meeting_id": m.get('id'),
                        "item_number": item.get('item_number'),
                        "title": item.get('title', 'Agenda Item'),
                        "project_type": item.get('project_type'),
                        "stance_eligible": bool(item.get('stance_eligible')),
                        "comment_eligible": bool(item.get('comment_eligible')),
                        "description": item.get('description', ''),
                        "why_it_matters": item.get('why_it_matters', ''),
                        "meeting_title": m.get('title') or m.get('body') or 'Meeting',
                        "meeting_date": meeting_dt.strftime("%b %d"),
                    })
        # Prioritize actionable items (stance/comment eligible first), then chronological
        upcoming_items.sort(key=lambda i: (not i['stance_eligible'] and not i['comment_eligible'],))
        result["upcoming_items"] = upcoming_items[:20]

        for m in meetings[:10]:  # Limit to 10 most recent/upcoming
            meeting_dt = m.get('meeting_datetime')
            if isinstance(meeting_dt, str):
                try:
                    meeting_dt = datetime.fromisoformat(meeting_dt.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    meeting_dt = None
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
                "location": m.get('location') or '',
                "meeting_datetime": meeting_dt.isoformat() if meeting_dt and hasattr(meeting_dt, 'isoformat') else '',
            })

        # Recent decisions - get all and sort by most recent
        # Many decisions don't have dates set, so we fetch all and limit
        decisions = storage.get_decisions(jurisdiction, limit=50)

        # Sort by date if available, then limit
        decisions_with_dates = []
        for d in decisions:
            decision_date = d.get('decision_date') or d.get('meeting_datetime')
            # meeting_date is stored as "YYYY-MM-DD" string — parse it
            if decision_date is None and d.get('meeting_date'):
                try:
                    decision_date = datetime.strptime(d['meeting_date'], "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            decisions_with_dates.append((d, decision_date))

        # Sort: those with dates first (newest), then those without
        decisions_with_dates.sort(
            key=lambda x: (x[1] is None, x[1] if x[1] else now),
            reverse=True
        )

        for d, decision_date in decisions_with_dates[:10]:
            if decision_date and hasattr(decision_date, 'strftime'):
                date_str = decision_date.strftime("%b %d")
            elif d.get('meeting_date'):
                # meeting_date is stored as "YYYY-MM-DD" string
                try:
                    date_str = datetime.strptime(d['meeting_date'], "%Y-%m-%d").strftime("%b %d")
                except (ValueError, TypeError):
                    date_str = d['meeting_date']
            else:
                date_str = "Recent"

            # Determine if this is an upcoming (future) agenda item
            today = datetime.now().date()
            item_upcoming = False
            if decision_date and hasattr(decision_date, 'date'):
                item_upcoming = decision_date.date() >= today
            elif d.get('meeting_date'):
                try:
                    item_upcoming = datetime.strptime(d['meeting_date'], "%Y-%m-%d").date() >= today
                except (ValueError, TypeError):
                    pass

            raw_outcome = d.get('outcome') or d.get('status') or 'decided'
            result["recent_outcomes"].append({
                "id": d.get('id'),
                "title": d.get('title') or 'Decision',
                "outcome": "on_agenda" if item_upcoming else raw_outcome,
                "outcome_description": _describe_outcome(raw_outcome, item_upcoming),
                "is_upcoming": item_upcoming,
                "vote_tally": d.get('vote_tally') or d.get('votes'),
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

    result["clerk_email"] = "cityclerk@cityofsanrafael.org"

    # Attestation stats (optional — fails gracefully)
    try:
        import httpx
        relay_url = _resolve_relay_url(None)
        with httpx.Client(timeout=5.0) as client:
            att_response = client.get(
                f"{relay_url}/coordination/attestation/stats/{jurisdiction}"
            )
            if att_response.status_code == 200:
                att_data = att_response.json()
                if att_data.get("total_attested", 0) > 0:
                    result["attestation"] = {
                        "total_attested": att_data.get("total_attested", 0),
                        "total_codes_issued": att_data.get("total_codes_issued", 0),
                        "total_codes_redeemed": att_data.get("total_codes_redeemed", 0),
                    }
    except Exception:
        pass  # Attestation stats are optional

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


def _load_roster(jurisdiction: str):
    """Load jurisdiction roster, checking both local dev and Modal container paths."""
    from pathlib import Path
    from civicos.roster import Roster

    # Modal mounts rosters to /app/config/rosters/
    modal_path = Path("/app/config/rosters")
    if modal_path.exists():
        return Roster.load(jurisdiction, config_dir=modal_path)

    # Local dev: default path resolution (walks up from module)
    return Roster.load(jurisdiction)


def _generate_decision_summary(
    title: str,
    outcome: str,
    outcome_desc: str,
    body: str,
    testimony_texts: list[str],
    logger: Logger,
    is_upcoming: bool = False,
) -> Optional[str]:
    """Generate a 2-3 sentence plain-English summary of a council decision.

    Uses Claude Haiku for cost efficiency (~$0.001/call). Returns None on failure
    so the response degrades gracefully without a summary.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    # Build context from available data
    context_parts = [f"Agenda item: {title}" if is_upcoming else f"Decision: {title}"]
    if body:
        context_parts.append(f"Body: {body}")
    if is_upcoming:
        context_parts.append("Status: This item is on an upcoming meeting agenda and has NOT yet been discussed or voted on.")
    elif outcome:
        context_parts.append(f"Outcome: {outcome} ({outcome_desc})")
    if testimony_texts:
        context_parts.append("Discussion excerpts:" if not is_upcoming else "Related context:")
        for i, t in enumerate(testimony_texts[:5], 1):
            context_parts.append(f"  {i}. {t[:300]}")

    context = "\n".join(context_parts)

    if is_upcoming:
        prompt = f"Write a 2-3 sentence plain-text summary (no headers, no markdown, no bullets) of this upcoming city council agenda item for a resident. Use future tense — this has NOT happened yet. Cover: what will be discussed, and why a resident might care.\n\n{context}"
    else:
        prompt = f"Write a 2-3 sentence plain-text summary (no headers, no markdown, no bullets) of this city council decision for a resident who knows nothing about it. Cover: what it's about, what was decided, and why it matters.\n\n{context}"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip any markdown headers the model might add despite instructions
        text = re.sub(r"^#+\s+.*?\n+", "", text).strip()
        return text
    except Exception as e:
        if logger:
            logger.warning(f"Summary generation failed: {e}")
        return None


OUTCOME_DESCRIPTIONS = {
    "adopted": "Passed by council vote",
    "approved": "Approved by council vote",
    "received": "Heard but no vote taken",
    "denied": "Rejected by council vote",
    "continued": "Postponed to a future meeting",
    "tabled": "Postponed to a future meeting",
    "withdrawn": "Withdrawn by the sponsor",
    "filed": "Accepted into the record",
}


def _describe_outcome(outcome: str, is_upcoming: bool = False) -> str:
    """Map civic jargon outcome to plain English."""
    if is_upcoming:
        return "Scheduled for discussion — has not yet been decided"
    if not outcome:
        return "Status unknown"
    return OUTCOME_DESCRIPTIONS.get(outcome.lower(), outcome.capitalize())


def _extract_excerpt(text: str, title: str = "", max_chars: int = 400) -> str:
    """Extract the most relevant sentences from a transcript chunk.

    Instead of naive text[:400] truncation, finds complete sentences
    most relevant to the decision title via keyword overlap. When space
    remains, adds adjacent sentences for reading context rather than
    padding from the beginning.

    Handles mid-sentence chunk starts by trimming leading fragments.
    """
    # Clean speaker labels like [Kate Colin (Mayor)] [B] [C]
    cleaned = re.sub(r"\[(?:[A-Z]|[^]]{2,60})\]\s*", "", text)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Trim leading mid-sentence fragment: if text starts lowercase or with
    # a conjunction/preposition, skip to the first sentence boundary
    if cleaned and not cleaned[0].isupper():
        m = re.search(r"[.!?]\s+([A-Z])", cleaned)
        if m:
            cleaned = cleaned[m.start() + 2:]

    # Split into sentences (handle abbreviations like Mr./Mrs./Dr./St.)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", cleaned)
    sentences = [s.strip() for s in parts if s.strip() and len(s.strip()) > 15]

    if not sentences:
        return cleaned[:max_chars].rstrip()

    if not title:
        # No title to score against — return first complete sentences
        result: list[str] = []
        total = 0
        for s in sentences:
            if total + len(s) + 1 > max_chars and result:
                break
            result.append(s)
            total += len(s) + 1
        return " ".join(result)

    # Score each sentence by keyword overlap with title
    title_words = set(re.findall(r"\w{3,}", title.lower()))
    title_words -= {"the", "and", "for", "with", "from", "that", "this", "city"}

    scores: list[int] = []
    for s in sentences:
        s_words = set(re.findall(r"\w{3,}", s.lower()))
        scores.append(len(title_words & s_words))

    # Start with sentences that have keyword overlap
    selected: set[int] = set()
    selected_chars = 0
    # Sort by score desc, position asc for ties
    ranked = sorted(range(len(sentences)), key=lambda i: (-scores[i], i))
    for idx in ranked:
        if scores[idx] == 0:
            break  # Stop at irrelevant sentences
        if selected_chars + len(sentences[idx]) + 1 > max_chars and selected:
            break
        selected.add(idx)
        selected_chars += len(sentences[idx]) + 1

    # If space remains, expand with adjacent sentences for context
    if selected:
        for idx in sorted(selected):
            # Try sentence before
            if idx - 1 >= 0 and idx - 1 not in selected:
                s = sentences[idx - 1]
                if selected_chars + len(s) + 1 <= max_chars:
                    selected.add(idx - 1)
                    selected_chars += len(s) + 1
            # Try sentence after
            if idx + 1 < len(sentences) and idx + 1 not in selected:
                s = sentences[idx + 1]
                if selected_chars + len(s) + 1 <= max_chars:
                    selected.add(idx + 1)
                    selected_chars += len(s) + 1

    # Fallback: no keyword matches at all — return first sentences
    if not selected:
        total = 0
        for i, s in enumerate(sentences):
            if total + len(s) + 1 > max_chars and selected:
                break
            selected.add(i)
            total += len(s) + 1

    return " ".join(sentences[i] for i in sorted(selected))


def decision_detail(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> dict:
    """Get structured detail for a specific decision (for dashboard expansion)."""
    title = args.get("title", "")

    if not title:
        return {"found": False}

    try:
        # First: exact title match via SQL (fast, correct for dashboard expansion)
        storage = civic.storage
        all_decisions = storage.get_decisions(jurisdiction, limit=100)
        exact_match = None
        for dec in all_decisions:
            if dec.get("title") == title:
                exact_match = dec
                break

        if exact_match:
            # Build decision detail from SQL record
            decision_id = exact_match.get("id")
            decision_title = exact_match.get("title", "")
            outcome = exact_match.get("outcome") or "decided"
            meeting_date_str = exact_match.get("meeting_date", "")
            body = exact_match.get("body") or "City Council"
            votes = exact_match.get("vote_json")

            # Parse date for transcript filtering
            decision_date = None
            if meeting_date_str:
                try:
                    decision_date = datetime.strptime(meeting_date_str, "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            # Search transcripts directly for this specific decision
            # (bypasses vector-based decision search which may match wrong decision)
            from civicos.history import Decision as HistDecision, _search_decision_transcripts
            known_decision = HistDecision(
                id=decision_id,
                title=decision_title,
                date=decision_date,
                outcome=outcome,
                body=body,
                votes=votes,
                agenda_item=exact_match.get("agenda_item"),
            )
            transcript_links, _conf, _link_type = _search_decision_transcripts(
                jurisdiction=jurisdiction,
                decision=known_decision,
                top_k=10,
                vector_backend=civic._vectors,
                storage_backend=storage,
            )

            # Look up meeting video URL as fallback when transcript chunks lack video_id
            meeting_video_url = None
            meeting_id = exact_match.get("meeting_id")
            if meeting_id and storage:
                try:
                    meetings = storage.get_meetings(jurisdiction, limit=200)
                    for m in meetings:
                        if m.get("id") == meeting_id and m.get("video_url"):
                            meeting_video_url = m["video_url"]
                            break
                except Exception:
                    pass

            # Speaker resolution via core module
            from civicos.speakers import (
                extract_speaker_from_text, get_video_id_from_chunk,
                build_meeting_speaker_map, resolve_speaker,
            )
            roster = _load_roster(jurisdiction)
            video_id = ""
            for l in transcript_links:
                video_id = get_video_id_from_chunk(l.chunk_id)
                if video_id:
                    break
            meeting_speaker_map = build_meeting_speaker_map(video_id, civic._vectors, roster)

            enriched_public = []
            enriched_council = []
            seen_texts: set[str] = set()
            for l in transcript_links:
                text_speaker, text_is_public = extract_speaker_from_text(l.text)
                raw_label = l.speaker_name or l.speaker or text_speaker
                display_name, is_public = resolve_speaker(raw_label, meeting_speaker_map, roster)
                is_public = is_public or l.is_public_comment or text_is_public
                excerpt = _extract_excerpt(l.text, decision_title)
                if excerpt in seen_texts:
                    continue
                seen_texts.add(excerpt)
                # Video URL: TranscriptLink property → chunk_id extraction → meeting fallback
                chunk_video_url = l.video_url
                if not chunk_video_url:
                    vid = get_video_id_from_chunk(l.chunk_id)
                    if vid:
                        ts = f"&t={l.start_ms // 1000}s" if l.start_ms else ""
                        chunk_video_url = f"https://www.youtube.com/watch?v={vid}{ts}"
                entry = {
                    "speaker": display_name or ("Public commenter" if is_public else "Council/Staff"),
                    "text": excerpt,
                    "video_url": chunk_video_url or meeting_video_url,
                    "start_timestamp": l.start_timestamp,
                }
                if is_public:
                    enriched_public.append(entry)
                else:
                    enriched_council.append(entry)

            # Determine if this is an upcoming (future) item
            today = datetime.now().date()
            is_upcoming = decision_date.date() >= today if decision_date else False
            display_outcome = "on_agenda" if is_upcoming else outcome

            # AI summary from testimony context
            all_texts = [e["text"] for e in enriched_council + enriched_public]
            summary = _generate_decision_summary(
                decision_title, outcome, _describe_outcome(outcome, is_upcoming),
                body, all_texts, logger, is_upcoming=is_upcoming,
            )

            # Related decisions via vector search (exclude self)
            related = civic.what_happened(decision_title)[:4]
            related_decisions = [
                {
                    "title": rd.title,
                    "outcome": rd.outcome,
                    "date": str(rd.date) if rd.date else None,
                }
                for rd in related if rd.title != decision_title
            ][:3]

            result = {
                "found": True,
                "is_upcoming": is_upcoming,
                "decision": {
                    "id": decision_id,
                    "title": decision_title,
                    "outcome": display_outcome,
                    "outcome_description": _describe_outcome(outcome, is_upcoming),
                    "date": str(decision_date) if decision_date else meeting_date_str,
                    "body": body,
                    "votes": votes,
                },
                "testimony": {
                    "public_comments": enriched_public[:5],
                    "council_discussion": enriched_council[:4],
                },
                "related_decisions": related_decisions,
            }
            if summary:
                result["summary"] = summary
            return result

        # Fallback: vector search (for queries that aren't exact titles)
        results = civic.what_happened_full_context(title, top_k=1, transcript_excerpts_per_decision=10)

        if not results:
            return {"found": False}

        r = results[0]
        d = r.decision

        # Look up meeting video URL as fallback
        fallback_video_url = None
        if d.date and storage:
            try:
                date_str = d.date.strftime("%Y-%m-%d") if hasattr(d.date, "strftime") else str(d.date)
                meetings = storage.get_meetings(jurisdiction, limit=200)
                for m in meetings:
                    m_date = str(m.get("meeting_datetime", ""))[:10]
                    if m_date == date_str and m.get("video_url"):
                        fallback_video_url = m["video_url"]
                        break
            except Exception:
                pass

        # Speaker resolution via core module
        from civicos.speakers import (
            extract_speaker_from_text, get_video_id_from_chunk,
            build_meeting_speaker_map, resolve_speaker,
        )
        roster = _load_roster(jurisdiction)
        video_id = ""
        for link in r.transcript_links:
            video_id = get_video_id_from_chunk(link.chunk_id)
            if video_id:
                break
        meeting_speaker_map = build_meeting_speaker_map(video_id, civic._vectors, roster)

        enriched_public = []
        enriched_council = []
        seen_texts: set[str] = set()
        for link in r.transcript_links:
            text_speaker, text_is_public = extract_speaker_from_text(link.text)
            raw_label = link.speaker_name or link.speaker or text_speaker
            display_name, is_public = resolve_speaker(raw_label, meeting_speaker_map, roster)
            is_public = is_public or link.is_public_comment or text_is_public
            excerpt = _extract_excerpt(link.text, d.title)
            if excerpt in seen_texts:
                continue
            seen_texts.add(excerpt)
            chunk_video_url = link.video_url
            if not chunk_video_url:
                vid = get_video_id_from_chunk(link.chunk_id)
                if vid:
                    ts = f"&t={link.start_ms // 1000}s" if link.start_ms else ""
                    chunk_video_url = f"https://www.youtube.com/watch?v={vid}{ts}"
            entry = {
                "speaker": display_name or ("Public commenter" if is_public else "Council/Staff"),
                "text": excerpt,
                "video_url": chunk_video_url or fallback_video_url,
                "start_timestamp": link.start_timestamp,
            }
            if is_public:
                enriched_public.append(entry)
            else:
                enriched_council.append(entry)

        # Determine if this is an upcoming (future) item
        today = datetime.now().date()
        is_upcoming = d.date.date() >= today if d.date and hasattr(d.date, "date") else False
        display_outcome = "on_agenda" if is_upcoming else d.outcome

        # AI summary from testimony context
        all_texts = [e["text"] for e in enriched_council + enriched_public]
        summary = _generate_decision_summary(
            d.title, d.outcome, _describe_outcome(d.outcome, is_upcoming),
            d.body, all_texts, logger, is_upcoming=is_upcoming,
        )

        # Get related decisions via vector search
        related = civic.what_happened(title)[:4]
        related_decisions = [
            {"title": rd.title, "outcome": rd.outcome, "date": str(rd.date) if rd.date else None}
            for rd in related if rd.title != d.title
        ][:3]

        result = {
            "found": True,
            "is_upcoming": is_upcoming,
            "decision": {
                "id": d.id,
                "title": d.title,
                "outcome": display_outcome,
                "outcome_description": _describe_outcome(d.outcome, is_upcoming),
                "date": str(d.date) if d.date else None,
                "body": d.body,
                "votes": d.votes,
            },
            "testimony": {
                "public_comments": enriched_public[:5],
                "council_discussion": enriched_council[:4],
            },
            "related_decisions": related_decisions,
        }
        if summary:
            result["summary"] = summary
        return result

    except Exception as e:
        logger.error(f"Error in decision_detail: {e}")
        return {"found": False, "error": str(e)}


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


# ─────────── Legislation & Executive Order Handlers ───────────


def _default_legislation_states(jurisdiction: str) -> list[str]:
    """Return default state codes to search based on server jurisdiction level."""
    if jurisdiction.startswith("country-"):
        return ["US"]
    elif jurisdiction.startswith("state-"):
        return ["CA"]  # TODO: derive from jurisdiction ID
    else:
        # City-level: search both state and federal
        return ["CA", "US"]


def search_legislation(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search legislation by topic, state, and status."""
    query = args.get("query", "")
    state = args.get("state")
    status = args.get("status")
    limit = min(args.get("limit", 10), 50)

    is_valid, sanitized, error = validate_input({"query": query})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    query = sanitized.get("query", query)

    try:
        results = []

        # Determine which states to search
        states_to_search = [state.upper()] if state else _default_legislation_states(jurisdiction)

        # First: try topic-column filter (works when topics are tagged)
        for s in states_to_search:
            bills = civic.storage.get_legislation(
                state=s,
                topic=query,
                status=status,
                limit=limit,
            )
            results.extend(bills)

        # Second: keyword search across bill_name, summary, keywords
        # This catches bills where the topic column isn't set
        if len(results) < limit and query:
            query_lower = query.lower()
            for s in states_to_search:
                # Fetch a broader set to search through
                fetch_limit = max(200, limit * 20)
                all_bills = civic.storage.get_legislation(
                    state=s,
                    status=status,
                    limit=fetch_limit,
                )
                seen_ids = {b.get("bill_id") for b in results}
                for bill in all_bills:
                    if bill.get("bill_id") in seen_ids:
                        continue
                    name = (bill.get("bill_name") or "").lower()
                    summary = (bill.get("summary") or "").lower()
                    keywords = bill.get("keywords") or []
                    keyword_str = " ".join(keywords).lower() if isinstance(keywords, list) else str(keywords).lower()
                    if query_lower in name or query_lower in summary or query_lower in keyword_str:
                        results.append(bill)
                        seen_ids.add(bill.get("bill_id"))

        # Deduplicate by bill_id and limit
        seen = set()
        unique = []
        for bill in results:
            bid = bill.get("bill_id")
            if bid not in seen:
                seen.add(bid)
                unique.append(bill)
        results = unique[:limit]

        if not results:
            return f"No legislation found matching '{query}'."

        result_parts = [f"# Legislation Search: {query}", f"**{len(results)} bills found**", ""]

        for bill in results:
            bill_num = bill.get("bill_number", bill.get("bill_id", "Unknown"))
            state_code = bill.get("state", "")
            name = bill.get("bill_name", "Untitled")
            bill_status = bill.get("status", "Unknown")
            leverage = bill.get("leverage_point", "")

            result_parts.append(f"## {bill_num} ({state_code})")
            result_parts.append(f"**{name}**")
            result_parts.append(f"- Status: {bill_status}")

            if bill.get("summary"):
                result_parts.append(f"- Summary: {bill['summary'][:200]}")

            if leverage:
                result_parts.append(f"- **Citizen action:** {leverage}")

            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in search_legislation: {e}")
        return f"Error searching legislation: {str(e)}"


def get_bill_detail(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get full detail for a specific bill."""
    bill_id = args.get("bill_id", "")
    state = args.get("state")

    if not bill_id:
        return "Error: bill_id is required."

    # Infer state from bill_id prefix if not provided
    if not state:
        if bill_id.lower().startswith("ca-") or bill_id.lower().startswith("ca_"):
            state = "CA"
        elif bill_id.lower().startswith("us-") or bill_id.lower().startswith("us_"):
            state = "US"
        else:
            state = "CA"  # Default to CA

    try:
        bill = civic.storage.get_legislation_by_bill_id(state=state.upper(), bill_id=bill_id)

        if not bill:
            # Try the other state
            other = "US" if state.upper() == "CA" else "CA"
            bill = civic.storage.get_legislation_by_bill_id(state=other, bill_id=bill_id)
            if not bill:
                return f"Bill '{bill_id}' not found."

        bill_num = bill.get("bill_number", bill.get("bill_id", "Unknown"))
        name = bill.get("bill_name", "Untitled")
        state_code = bill.get("state", "")

        result_parts = [f"# {bill_num} ({state_code})", f"**{name}**", ""]

        result_parts.append(f"- **Status:** {bill.get('status', 'Unknown')}")
        if bill.get("enacted_date"):
            result_parts.append(f"- **Enacted:** {bill['enacted_date']}")
        if bill.get("official_url"):
            result_parts.append(f"- **Official URL:** {bill['official_url']}")

        if bill.get("summary"):
            result_parts.extend(["", "## Summary", bill["summary"]])

        if bill.get("leverage_point"):
            result_parts.extend([
                "", "## Citizen Action Opportunity",
                bill["leverage_point"],
            ])

        if bill.get("local_implementation_required"):
            result_parts.append("")
            result_parts.append("**Local implementation required.**")
            if bill.get("local_deadline"):
                result_parts.append(f"Deadline: {bill['local_deadline']}")

        if bill.get("keywords"):
            keywords = bill["keywords"]
            if isinstance(keywords, list):
                result_parts.extend(["", f"**Topics:** {', '.join(keywords)}"])

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_bill_detail: {e}")
        return f"Error getting bill detail: {str(e)}"


def get_leverage_points(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Find legislation with citizen action opportunities."""
    topic = args.get("topic")
    state = args.get("state")
    limit = min(args.get("limit", 10), 50)

    try:
        states_to_search = [state.upper()] if state else _default_legislation_states(jurisdiction)
        results = []

        for s in states_to_search:
            bills = civic.storage.get_legislation(
                state=s,
                topic=topic if topic else None,
                limit=200,  # Fetch more to filter
            )
            for bill in bills:
                if bill.get("leverage_point"):
                    results.append(bill)

        # If topic filter was too restrictive, also search by keyword
        if len(results) < limit and topic:
            topic_lower = topic.lower()
            for s in states_to_search:
                all_bills = civic.storage.get_legislation(state=s, limit=500)
                for bill in all_bills:
                    if not bill.get("leverage_point"):
                        continue
                    name = (bill.get("bill_name") or "").lower()
                    summary = (bill.get("summary") or "").lower()
                    leverage = (bill.get("leverage_point") or "").lower()
                    if topic_lower in name or topic_lower in summary or topic_lower in leverage:
                        if bill.get("bill_id") not in {b.get("bill_id") for b in results}:
                            results.append(bill)

        results = results[:limit]

        if not results:
            topic_msg = f" for '{topic}'" if topic else ""
            return f"No legislation with citizen action opportunities found{topic_msg}."

        result_parts = [
            "# Citizen Action Opportunities",
            f"**{len(results)} bills with leverage points**",
            "",
        ]

        for bill in results:
            bill_num = bill.get("bill_number", bill.get("bill_id", ""))
            state_code = bill.get("state", "")
            name = bill.get("bill_name", "")
            leverage = bill.get("leverage_point", "")

            result_parts.append(f"## {bill_num} ({state_code})")
            result_parts.append(f"**{name}**")
            result_parts.append(f"- Status: {bill.get('status', 'Unknown')}")
            result_parts.append(f"- **What you can do:** {leverage}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_leverage_points: {e}")
        return f"Error getting leverage points: {str(e)}"


def search_executive_orders(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search active Executive Orders by topic."""
    query = args.get("query", "")
    president = args.get("president")
    limit = min(args.get("limit", 10), 50)

    is_valid, sanitized, error = validate_input({"query": query})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    query = sanitized.get("query", query)

    try:
        orders = civic.storage.search_executive_orders(
            query=query,
            president=president,
            limit=limit,
        )

        if not orders:
            return f"No Executive Orders found matching '{query}'."

        result_parts = [
            f"# Executive Orders: {query}",
            f"**{len(orders)} orders found**",
            "",
        ]

        for order in orders:
            eo_num = order.get("eo_number", "")
            title = order.get("title", "Untitled")
            pres = order.get("president", "")
            signed = order.get("signing_date", "")

            header = f"EO {eo_num}" if eo_num else order.get("document_number", "Unknown")
            result_parts.append(f"## {header}")
            result_parts.append(f"**{title}**")
            result_parts.append(f"- President: {pres}")
            if signed:
                result_parts.append(f"- Signed: {signed}")
            if order.get("html_url"):
                result_parts.append(f"- URL: {order['html_url']}")

            preview = order.get("text_preview", "")
            if preview:
                # Strip HTML tags if present
                clean = re.sub(r'<[^>]+>', ' ', preview)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if clean:
                    result_parts.append(f"- Preview: {clean[:300]}...")

            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in search_executive_orders: {e}")
        return f"Error searching executive orders: {str(e)}"


def get_recent_executive_orders(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get recently signed Executive Orders."""
    president = args.get("president")
    limit = min(args.get("limit", 10), 50)

    try:
        orders = civic.storage.get_executive_orders(
            president=president,
            status="active",
            limit=limit,
        )

        if not orders:
            return "No recent Executive Orders found."

        result_parts = [
            "# Recent Executive Orders",
            f"**{len(orders)} orders**",
            "",
        ]

        for order in orders:
            eo_num = order.get("eo_number", "")
            title = order.get("title", "Untitled")
            pres = order.get("president", "")
            signed = order.get("signing_date", "")

            header = f"EO {eo_num}" if eo_num else order.get("document_number", "Unknown")
            result_parts.append(f"## {header}")
            result_parts.append(f"**{title}**")
            result_parts.append(f"- President: {pres}")
            if signed:
                result_parts.append(f"- Signed: {signed}")
            if order.get("html_url"):
                result_parts.append(f"- URL: {order['html_url']}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_recent_executive_orders: {e}")
        return f"Error getting recent executive orders: {str(e)}"


# ─────────── Participation Window Handlers ───────────


def get_open_comment_periods(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get federal rules with open public comment periods."""
    limit = min(args.get("limit", 10), 50)

    try:
        rules = civic.storage.get_open_comment_periods(limit=limit)

        if not rules:
            return "No federal rules with open comment periods found. Check back soon — new proposed rules are published regularly."

        result_parts = [
            "# Open Federal Comment Periods",
            f"**{len(rules)} rules accepting public comments**",
            "",
            "These are proposed rules where you can submit feedback before the deadline.",
            "",
        ]

        for rule in rules:
            title = rule.get("title", "Untitled")
            agencies = rule.get("agency_names", [])
            agency_str = ", ".join(agencies) if agencies else "Unknown agency"
            close_date = rule.get("comments_close_on", "")
            comment_url = rule.get("comment_url", "")

            # Calculate days remaining
            days_remaining = ""
            if close_date:
                try:
                    close = datetime.strptime(close_date, "%Y-%m-%d").date()
                    delta = (close - datetime.now().date()).days
                    if delta < 0:
                        days_remaining = " (CLOSED)"
                    elif delta == 0:
                        days_remaining = " (CLOSES TODAY)"
                    elif delta <= 7:
                        days_remaining = f" ({delta} days left)"
                    else:
                        days_remaining = f" ({delta} days left)"
                except ValueError:
                    pass

            result_parts.append(f"## {title[:100]}")
            result_parts.append(f"- Agency: {agency_str}")
            result_parts.append(f"- Comment deadline: {close_date}{days_remaining}")
            if comment_url:
                result_parts.append(f"- Submit comment: {comment_url}")
            if rule.get("html_url"):
                result_parts.append(f"- Full text: {rule['html_url']}")
            if rule.get("abstract"):
                result_parts.append(f"- Summary: {rule['abstract'][:300]}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_open_comment_periods: {e}")
        return f"Error getting open comment periods: {str(e)}"


def search_federal_rules(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Search federal rulemaking documents by topic."""
    query = args.get("query", "")
    document_type = args.get("document_type")
    limit = min(args.get("limit", 10), 50)

    is_valid, sanitized, error = validate_input({"query": query})
    if not is_valid:
        return f"Error: Invalid input - {error}"
    query = sanitized.get("query", query)

    try:
        rules = civic.storage.search_federal_rules(
            query=query,
            document_type=document_type,
            limit=limit,
        )

        if not rules:
            return f"No federal rules found matching '{query}'."

        type_labels = {
            "proposed_rule": "Proposed Rule",
            "final_rule": "Final Rule",
            "notice": "Notice",
        }

        result_parts = [
            f"# Federal Rules: {query}",
            f"**{len(rules)} rules found**",
            "",
        ]

        for rule in rules:
            title = rule.get("title", "Untitled")
            doc_type = type_labels.get(rule.get("document_type", ""), rule.get("document_type", ""))
            agencies = rule.get("agency_names", [])
            agency_str = ", ".join(agencies) if agencies else "Unknown"
            close_date = rule.get("comments_close_on", "")

            result_parts.append(f"## {title[:100]}")
            result_parts.append(f"- Type: {doc_type}")
            result_parts.append(f"- Agency: {agency_str}")
            if close_date:
                result_parts.append(f"- Comment deadline: {close_date}")
            if rule.get("comment_url"):
                result_parts.append(f"- Submit comment: {rule['comment_url']}")
            if rule.get("html_url"):
                result_parts.append(f"- URL: {rule['html_url']}")
            if rule.get("abstract"):
                result_parts.append(f"- Summary: {rule['abstract'][:300]}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in search_federal_rules: {e}")
        return f"Error searching federal rules: {str(e)}"


def get_upcoming_hearings(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get upcoming state legislative committee hearings."""
    state = args.get("state", "CA")
    topic = args.get("topic")
    days_ahead = args.get("days_ahead", 30)
    limit = min(args.get("limit", 20), 50)

    try:
        events = civic.storage.get_upcoming_hearings(
            state=state,
            days_ahead=days_ahead,
            limit=limit,
        )

        # If topic filter requested, filter by keyword match
        if topic and events:
            topic_lower = topic.lower()
            events = [
                e for e in events
                if topic_lower in (e.get("description", "") or "").lower()
                or topic_lower in (e.get("committee", "") or "").lower()
                or topic_lower in (e.get("bill_id", "") or "").lower()
            ]

        if not events:
            qualifier = f" on '{topic}'" if topic else ""
            return f"No upcoming hearings found{qualifier} in the next {days_ahead} days."

        result_parts = [
            f"# Upcoming Legislative Hearings ({state})",
            f"**{len(events)} hearings in next {days_ahead} days**",
            "",
            "These are committee hearings where public testimony may be accepted.",
            "",
        ]

        for event in events:
            bill_id = event.get("bill_id", "Unknown")
            event_date = event.get("event_date", "")
            committee = event.get("committee", "")
            description = event.get("description", "")

            # Calculate days until hearing
            days_until = ""
            if event_date:
                try:
                    hearing = datetime.strptime(event_date, "%Y-%m-%d").date()
                    delta = (hearing - datetime.now().date()).days
                    if delta == 0:
                        days_until = " (TODAY)"
                    elif delta == 1:
                        days_until = " (tomorrow)"
                    else:
                        days_until = f" (in {delta} days)"
                except ValueError:
                    pass

            result_parts.append(f"## {bill_id}")
            result_parts.append(f"- Hearing date: {event_date}{days_until}")
            if committee:
                result_parts.append(f"- Committee: {committee}")
            if event.get("location"):
                result_parts.append(f"- Location: {event['location']}")
            if description:
                result_parts.append(f"- Details: {description[:300]}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_upcoming_hearings: {e}")
        return f"Error getting upcoming hearings: {str(e)}"


def get_governors_desk(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get bills awaiting governor's signature (Enrolled status)."""
    state = args.get("state", "CA")
    topic = args.get("topic")
    limit = min(args.get("limit", 20), 50)

    try:
        # Status 5 = Enrolled (awaiting governor's signature)
        bills = civic.storage.get_legislation(
            state=state,
            status="Enrolled",
            limit=limit * 2,  # Fetch more to allow for topic filtering
        )

        # Also try status_id if text status doesn't work
        if not bills:
            bills = civic.storage.get_legislation(
                state=state,
                limit=200,
            )
            bills = [b for b in bills if str(b.get("status_id")) == "5" or b.get("status") == "Enrolled"]

        # Filter by topic if requested
        if topic and bills:
            topic_lower = topic.lower()
            bills = [
                b for b in bills
                if topic_lower in (b.get("bill_name", "") or "").lower()
                or topic_lower in (b.get("summary", "") or "").lower()
                or topic_lower in " ".join(b.get("keywords", []) or []).lower()
            ]

        bills = bills[:limit]

        if not bills:
            qualifier = f" on '{topic}'" if topic else ""
            return f"No bills currently on the Governor's desk{qualifier}."

        result_parts = [
            f"# Governor's Desk ({state})",
            f"**{len(bills)} bills awaiting signature**",
            "",
            "The governor has 12 days to sign or veto these bills. Constituent calls can influence the outcome.",
            "",
        ]

        for bill in bills:
            bill_num = bill.get("bill_number", bill.get("bill_id", "Unknown"))
            name = bill.get("bill_name", "Untitled")

            result_parts.append(f"## {bill_num}")
            result_parts.append(f"**{name}**")
            if bill.get("summary"):
                result_parts.append(f"- Summary: {bill['summary'][:200]}")
            result_parts.append(f"- **Action:** Call the Governor's office to express support or opposition")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error in get_governors_desk: {e}")
        return f"Error getting governor's desk bills: {str(e)}"


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
]


def _get_default_relay_url() -> str:
    """Get the default relay URL from registry, with env var overrides."""
    import os
    env_url = os.environ.get("CIVICOS_RELAY_URL") or os.environ.get("CIVICOS_API_URL")
    if env_url:
        return env_url
    # Use registry for production default, fall back to localhost for local dev
    try:
        from civicos.registry import get_relay_url
        return get_relay_url()
    except Exception:
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
        ]

        # Include attestation breakdown if available
        if data.get('attested') is not None:
            result_parts.append("")
            result_parts.append(f"**Attested:** {data.get('attested', 0)}")
            result_parts.append(f"**Unattested:** {data.get('unattested', 0)}")

        result_parts.extend([
            "",
            "_Voices are cryptographically signed. Counts can be verified by any relay with the same data._",
        ])

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


# ─────────── Context Assembly Tool ───────────


def get_item_context(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> dict:
    """
    Get comprehensive context for a civic item.

    Assembles history, regulatory, community, financial, testimony,
    and participation context from existing CivicOS data. Returns a
    structured bundle suitable for passing to an LLM conversation.
    """
    import asyncio
    import concurrent.futures

    from civicos_services.context import (
        assemble_context,
        ItemNotFoundError,
        ItemType,
        ContextDepth,
    )

    item_type_str = args.get("item_type", "")
    item_id = args.get("item_id", "")
    depth_str = args.get("depth", "standard")
    sections_str = args.get("sections")

    # Validate item_type
    try:
        item_type = ItemType(item_type_str)
    except ValueError:
        valid = ", ".join(t.value for t in ItemType)
        return {"error": f"Invalid item_type '{item_type_str}'. Valid: {valid}"}

    if not item_id:
        return {"error": "item_id is required"}

    # Parse depth
    try:
        depth = ContextDepth(depth_str)
    except ValueError:
        depth = ContextDepth.standard

    # Parse sections
    sections = None
    if sections_str:
        sections = set(s.strip() for s in sections_str.split(",") if s.strip())

    # Run async assembler in a new thread with its own event loop
    # (handlers are called from sync context within a running event loop)
    def _run_assembly():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                assemble_context(item_type, item_id, jurisdiction, sections, depth)
            )
        finally:
            loop.close()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_assembly)
            bundle = future.result(timeout=60)
        return bundle.model_dump(mode="json")
    except ItemNotFoundError as e:
        return {"error": f"Item not found: {e.item_type}/{e.item_id} in {e.jurisdiction}"}
    except concurrent.futures.TimeoutError:
        return {"error": "Context assembly timed out (>60s)"}
    except Exception as e:
        logger.error(f"Context assembly error: {e}")
        return {"error": f"Assembly failed: {str(e)}"}
