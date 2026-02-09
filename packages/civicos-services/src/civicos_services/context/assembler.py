"""
Context Assembly API — Core orchestration logic.

Assembles a rich context bundle for any civic item by orchestrating
existing CivicOS API methods in parallel. Each section is independently
assembled with timeout and error isolation.
"""

import asyncio
import functools
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from civicos import CivicOS

from .models import (
    AgendaItemDetails,
    BudgetRef,
    CommentStatus,
    CommunitySection,
    ContextBundle,
    ContextDepth,
    ContextItem,
    ContextMetadata,
    ContextSections,
    DecisionDetails,
    FinancialSection,
    FederalRef,
    HistorySection,
    InitiativeDetails,
    IssueDetails,
    ItemType,
    LegislationDetails,
    MeetingDetails,
    MeetingLogistics,
    MunicipalCodeRef,
    ParticipationSection,
    RegulatorySection,
    RelatedDecision,
    SimilarIssue,
    StateLegislationRef,
    TestimonyExcerpt,
    TestimonySection,
)

logger = logging.getLogger("civicos.context")

SECTION_TIMEOUT_S = 10.0
ALL_SECTION_NAMES = {"history", "regulatory", "community", "financial", "testimony", "participation"}

# project_type → department mapping for budget lookups
PROJECT_TYPE_DEPARTMENT_MAP = {
    "zoning": "Community Development",
    "housing": "Community Development",
    "land_use": "Community Development",
    "planning": "Community Development",
    "transportation": "Public Works",
    "infrastructure": "Public Works",
    "streets": "Public Works",
    "parks": "Community Services",
    "recreation": "Community Services",
    "public_safety": "Police",
    "police": "Police",
    "fire": "Fire",
    "budget": "Finance",
    "finance": "Finance",
}


# === Exceptions ===

class ItemNotFoundError(Exception):
    """Raised when a civic item cannot be found by ID."""

    def __init__(self, item_type: str, item_id: str, jurisdiction: str):
        self.item_type = item_type
        self.item_id = item_id
        self.jurisdiction = jurisdiction
        super().__init__(
            f"{item_type} '{item_id}' not found in jurisdiction '{jurisdiction}'"
        )


class SectionTimeoutError(Exception):
    """Raised when a section assembly exceeds its timeout."""

    def __init__(self, section: str, timeout: float):
        self.section = section
        self.timeout = timeout
        super().__init__(f"Section '{section}' timed out after {timeout}s")


class RelayUnavailableError(Exception):
    """Raised when the relay service is unreachable."""
    pass


# === Item Loading ===

def load_item(civic: CivicOS, item_type: ItemType, item_id: str) -> Dict[str, Any]:
    """Load a civic item by type and ID. Returns raw dict from storage."""
    storage = civic.storage
    jurisdiction = civic.jurisdiction

    if item_type == ItemType.agenda_item:
        items = storage.get_agenda_items(jurisdiction_id=jurisdiction)
        item = next((i for i in items if i["id"] == item_id), None)

    elif item_type == ItemType.decision:
        decisions = storage.get_decisions(jurisdiction)
        item = next((d for d in decisions if d["id"] == item_id), None)

    elif item_type == ItemType.issue:
        issues = storage.get_issues(jurisdiction_id=jurisdiction)
        item = next((i for i in issues if i["id"] == item_id), None)

    elif item_type == ItemType.legislation:
        # Use direct lookup — DO NOT load all 17K+ records
        state = item_id.split("-")[0].upper() if "-" in item_id else "CA"
        item = storage.get_legislation_by_bill_id(state=state, bill_id=item_id)

    elif item_type == ItemType.meeting:
        meetings = storage.get_meetings(jurisdiction)
        item = next((m for m in meetings if m["id"] == item_id), None)

    elif item_type == ItemType.initiative:
        raise RelayUnavailableError("Initiative loading requires relay integration (not yet implemented)")

    else:
        item = None

    if item is None:
        raise ItemNotFoundError(str(item_type.value), item_id, jurisdiction)

    return item


def _get_meeting_for_agenda_item(civic: CivicOS, meeting_id: str) -> Optional[Dict[str, Any]]:
    """Look up the parent meeting for an agenda item."""
    meetings = civic.storage.get_meetings(civic.jurisdiction)
    return next((m for m in meetings if m["id"] == meeting_id), None)


def build_context_item(
    item_type: ItemType, item_id: str, raw: Dict[str, Any],
    jurisdiction: str, civic: CivicOS,
) -> ContextItem:
    """Convert a raw storage dict into a typed ContextItem."""
    title = raw.get("title") or raw.get("bill_name") or ""
    description = raw.get("description") or raw.get("summary") or raw.get("abstract") or None
    why_it_matters = raw.get("why_it_matters") or None

    if item_type == ItemType.agenda_item:
        meeting = _get_meeting_for_agenda_item(civic, raw.get("meeting_id", ""))
        details = AgendaItemDetails(
            item_number=raw.get("item_number"),
            meeting_id=raw.get("meeting_id", ""),
            meeting_title=meeting["title"] if meeting else "",
            meeting_date=meeting.get("meeting_datetime") if meeting else None,
            meeting_location=meeting.get("location") if meeting else None,
            project_type=raw.get("project_type"),
            stance_eligible=bool(raw.get("stance_eligible")),
            comment_eligible=bool(raw.get("comment_eligible")),
        )

    elif item_type == ItemType.decision:
        details = DecisionDetails(
            outcome=raw.get("outcome"),
            decision_date=raw.get("meeting_date"),  # decisions store date as meeting_date
            votes=raw.get("vote_json"),
            body=raw.get("body") or raw.get("meeting_type"),
        )

    elif item_type == ItemType.issue:
        loc = raw.get("location")
        location_str = None
        if isinstance(loc, dict):
            location_str = loc.get("address") or loc.get("name")
        elif isinstance(loc, str):
            location_str = loc
        details = IssueDetails(
            issue_type=raw.get("issue_type"),
            status=raw.get("status"),
            location=location_str,
            created_at=raw.get("created_at"),
            closed_at=raw.get("closed_at"),
        )

    elif item_type == ItemType.legislation:
        kw = raw.get("keywords")
        if isinstance(kw, str):
            import json
            try:
                kw = json.loads(kw)
            except (json.JSONDecodeError, TypeError):
                kw = []
        details = LegislationDetails(
            bill_number=raw.get("bill_number"),
            state=raw.get("state"),
            status_label=raw.get("status_label"),
            keywords=kw or [],
            leverage_point=raw.get("leverage_point"),
            official_url=raw.get("official_url"),
        )

    elif item_type == ItemType.meeting:
        agenda_items = civic.storage.get_agenda_items(meeting_id=raw["id"])
        details = MeetingDetails(
            body=raw.get("meeting_type"),
            date=raw.get("meeting_datetime"),
            location=raw.get("location"),
            agenda_item_count=len(agenda_items),
        )

    elif item_type == ItemType.initiative:
        details = InitiativeDetails(
            creator_id=raw.get("creator_id"),
            created_at=raw.get("created_at"),
            location=raw.get("location"),
        )

    else:
        details = AgendaItemDetails(meeting_id="", meeting_title="")

    return ContextItem(
        type=item_type,
        id=item_id,
        title=title,
        description=description,
        why_it_matters=why_it_matters,
        jurisdiction=jurisdiction,
        item_details=details,
    )


# === Section Assemblers ===

def _run_sync(fn: Callable, *args, **kwargs) -> Any:
    """Run a synchronous function in the default executor."""
    loop = asyncio.get_running_loop()
    if kwargs:
        fn = functools.partial(fn, *args, **kwargs)
        return loop.run_in_executor(None, fn)
    if args:
        fn = functools.partial(fn, *args)
        return loop.run_in_executor(None, fn)
    return loop.run_in_executor(None, fn)


async def assemble_history(civic: CivicOS, item: ContextItem, depth: ContextDepth) -> Optional[HistorySection]:
    """Assemble history section — related past decisions."""
    title = item.title
    limit = 3 if depth == ContextDepth.minimal else 5

    decisions = await _run_sync(civic.what_happened, title)

    if not decisions:
        return HistorySection()

    related = []
    for d in decisions[:limit]:
        date_str = None
        if d.date:
            date_str = d.date.isoformat()[:10] if isinstance(d.date, datetime) else str(d.date)[:10]
        related.append(RelatedDecision(
            id=d.id,
            title=d.title,
            outcome=d.outcome,
            date=date_str,
        ))

    return HistorySection(related_decisions=related)


async def assemble_regulatory(civic: CivicOS, item: ContextItem, depth: ContextDepth) -> Optional[RegulatorySection]:
    """Assemble regulatory section — applicable laws and codes."""
    title = item.title
    stack = await _run_sync(civic.what_applies, title)

    municipal_code = []
    for entry in (stack.local or []):
        municipal_code.append(MunicipalCodeRef(
            section_number=entry.get("section_number", ""),
            section_title=entry.get("section_title", ""),
            excerpt=entry.get("excerpt") or entry.get("full_text", "")[:300] if entry.get("full_text") else None,
            relevance_score=entry.get("score"),
        ))

    state_legislation = []
    for entry in (stack.state or []):
        state_legislation.append(StateLegislationRef(
            bill_id=entry.get("bill_id"),
            bill_number=entry.get("bill_number"),
            status_label=entry.get("status_label"),
            summary=entry.get("summary"),
            leverage_point=entry.get("leverage_point"),
        ))

    federal_bills = []
    executive_orders = []
    for entry in (stack.federal or []):
        ref = FederalRef(
            title=entry.get("title"),
            summary=entry.get("summary") or entry.get("abstract"),
            official_url=entry.get("official_url") or entry.get("html_url"),
        )
        # Split EOs from legislation
        if entry.get("eo_number") or entry.get("document_number"):
            executive_orders.append(ref)
        else:
            federal_bills.append(ref)

    return RegulatorySection(
        municipal_code=municipal_code,
        state_legislation=state_legislation,
        federal=federal_bills,
        executive_orders=executive_orders,
    )


async def assemble_community(civic: CivicOS, item: ContextItem, depth: ContextDepth) -> Optional[CommunitySection]:
    """Assemble community section — similar issues and engagement.

    V1: whos_with_me() returns sparse data. We query issues directly
    for similar_issues. related_initiatives and voice_summary depend
    on relay integration (stub for now).
    """
    community = await _run_sync(civic.whos_with_me, item.title)

    similar_issues = []
    for issue in (community.recent_voices or []):
        similar_issues.append(SimilarIssue(
            id=issue.get("id", ""),
            title=issue.get("title", ""),
            issue_type=issue.get("issue_type"),
            status=issue.get("status"),
        ))

    return CommunitySection(
        similar_issues=similar_issues,
        related_initiatives=community.active_initiatives or [],
        voice_summary=None,  # Requires relay integration
    )


async def assemble_financial(civic: CivicOS, item: ContextItem, depth: ContextDepth) -> Optional[FinancialSection]:
    """Assemble financial section — relevant budget items.

    Extracts department from item metadata via project_type mapping.
    budget() takes keyword args (department, fund), not a topic string.
    """
    # Extract department from item's project_type
    department = None
    if hasattr(item.item_details, "project_type") and item.item_details.project_type:
        department = PROJECT_TYPE_DEPARTMENT_MAP.get(item.item_details.project_type)

    if not department:
        return FinancialSection()

    budget_items_raw = await _run_sync(civic.budget, department=department)

    budget_items = []
    total = 0.0
    for b in budget_items_raw:
        budget_items.append(BudgetRef(
            department=b.department,
            line_item=b.line_item,
            budgeted_dollars=b.budgeted_dollars,
            fiscal_year=b.fiscal_year,
        ))
        total += b.budgeted_dollars

    return FinancialSection(
        budget_items=budget_items,
        total_relevant_budget=total,
    )


async def assemble_testimony(civic: CivicOS, item: ContextItem, depth: ContextDepth) -> Optional[TestimonySection]:
    """Assemble testimony section — transcript excerpts."""
    title = item.title
    top_k = 3 if depth == ContextDepth.minimal else 5

    # Run both queries in parallel
    excerpts_future = _run_sync(civic.what_was_said, title, top_k)
    public_future = _run_sync(civic.get_public_testimony, title, top_k)
    all_excerpts, public_excerpts = await asyncio.gather(excerpts_future, public_future)

    def to_testimony(excerpt) -> TestimonyExcerpt:
        return TestimonyExcerpt(
            speaker=excerpt.speaker_name or excerpt.speaker,
            speaker_role=excerpt.speaker_role,
            text=excerpt.text,
            video_url=excerpt.video_url,
            start_timestamp=excerpt.start_timestamp or None,
            end_timestamp=excerpt.end_timestamp or None,
        )

    # Categorize all_excerpts by role
    public_comments = [to_testimony(e) for e in public_excerpts]
    staff_discussion = [to_testimony(e) for e in all_excerpts if e.speaker_role == "staff"]
    council_discussion = [to_testimony(e) for e in all_excerpts if e.speaker_role == "council"]

    return TestimonySection(
        public_comments=public_comments,
        staff_discussion=staff_discussion,
        council_discussion=council_discussion,
    )


def assemble_participation(item: ContextItem) -> Optional[ParticipationSection]:
    """Assemble participation section — derived from item flags.

    No async needed — purely derived from item metadata.
    """
    details = item.item_details
    actions = []

    stance_eligible = getattr(details, "stance_eligible", False)
    comment_eligible = getattr(details, "comment_eligible", False)

    if stance_eligible:
        actions.append("voice")
    if comment_eligible:
        actions.append("comment")
    actions.append("follow")  # Always available

    comment_status = None
    if comment_eligible:
        meeting_date = getattr(details, "meeting_date", None)
        comment_status = CommentStatus(
            open=True,
            closes_at=meeting_date,
            clerk_email="cityclerk@cityofsanrafael.org",
        )

    meeting_logistics = None
    meeting_date = getattr(details, "meeting_date", None) or getattr(details, "date", None)
    meeting_location = getattr(details, "meeting_location", None) or getattr(details, "location", None)
    if meeting_date:
        date_obj = meeting_date if isinstance(meeting_date, datetime) else None
        meeting_logistics = MeetingLogistics(
            date=date_obj.strftime("%a, %b %-d") if date_obj else str(meeting_date),
            time=date_obj.strftime("%-I:%M %p") if date_obj else None,
            location=meeting_location,
            how_to_attend="In person or via Zoom (link on city website)",
        )

    return ParticipationSection(
        comment_status=comment_status,
        voice_enabled=stance_eligible,
        actions_available=actions,
        meeting_logistics=meeting_logistics,
    )


# === Suggested Questions ===

QUESTION_TEMPLATES = {
    ItemType.agenda_item: [
        "What laws apply to this proposal?",
        "Has this topic come before council before?",
        "What are residents saying about this?",
        "How can I participate in this decision?",
        "What's the timeline for this item?",
    ],
    ItemType.decision: [
        "Why was this decision made?",
        "Who voted for and against?",
        "What does this decision mean going forward?",
        "What legislation is related to this?",
        "Were there public comments on this?",
    ],
    ItemType.issue: [
        "Are there similar issues nearby?",
        "How has the city responded to issues like this?",
        "Who should I contact about this?",
        "Is there related city policy?",
        "What's the typical resolution time?",
    ],
    ItemType.legislation: [
        "How does this affect our city?",
        "What are the implementation requirements?",
        "What's the timeline for this bill?",
        "Who does this legislation affect?",
        "How are other cities responding?",
    ],
    ItemType.meeting: [
        "What are the key agenda items?",
        "What has this body decided recently?",
        "How can I attend this meeting?",
        "Are there any controversial items?",
        "What public comment opportunities exist?",
    ],
    ItemType.initiative: [
        "Who started this initiative?",
        "How can I add my voice?",
        "What related decisions has the city made?",
        "Are there similar efforts elsewhere?",
        "What's the current support level?",
    ],
}


def generate_suggested_questions(item_type: ItemType) -> List[str]:
    """Generate suggested questions for an item type."""
    return QUESTION_TEMPLATES.get(item_type, [])


# === Main Orchestrator ===

async def assemble_context(
    item_type: ItemType,
    item_id: str,
    jurisdiction: str,
    sections: Optional[Set[str]] = None,
    depth: ContextDepth = ContextDepth.standard,
) -> ContextBundle:
    """
    Assemble a complete context bundle for a civic item.

    Loads the item, runs section assemblers in parallel with timeout
    and error isolation, then returns the bundle.
    """
    start_time = time.monotonic()

    # Initialize CivicOS (synchronous — runs in executor)
    loop = asyncio.get_running_loop()
    civic = await loop.run_in_executor(None, CivicOS, jurisdiction)

    # Load the focal item (synchronous)
    raw_item = await loop.run_in_executor(
        None, functools.partial(load_item, civic, item_type, item_id)
    )
    context_item = build_context_item(item_type, item_id, raw_item, jurisdiction, civic)

    # Determine which sections to assemble
    requested = sections if sections else ALL_SECTION_NAMES

    # For minimal depth, only include participation
    if depth == ContextDepth.minimal:
        requested = requested & {"participation"}

    # Participation is sync — handle it directly
    participation_result = None
    participation_status = "skipped"
    participation_time = 0
    if "participation" in requested:
        p_start = time.monotonic()
        participation_result = assemble_participation(context_item)
        participation_time = int((time.monotonic() - p_start) * 1000)
        participation_status = "ok" if participation_result else "empty"

    # Build async section tasks (with concurrency limit)
    semaphore = asyncio.Semaphore(3)
    section_assemblers = {
        "history": assemble_history,
        "regulatory": assemble_regulatory,
        "community": assemble_community,
        "financial": assemble_financial,
        "testimony": assemble_testimony,
    }

    async def run_section(name: str) -> tuple:
        """Run a section assembler with timeout and error isolation."""
        s_start = time.monotonic()
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    section_assemblers[name](civic, context_item, depth),
                    timeout=SECTION_TIMEOUT_S,
                )
            elapsed = int((time.monotonic() - s_start) * 1000)
            if result is None:
                return name, None, "empty", None, elapsed
            return name, result, "ok", None, elapsed
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - s_start) * 1000)
            logger.warning(f"Section '{name}' timed out after {SECTION_TIMEOUT_S}s")
            return name, None, "timeout", f"Timed out after {SECTION_TIMEOUT_S}s", elapsed
        except Exception as e:
            elapsed = int((time.monotonic() - s_start) * 1000)
            logger.error(f"Section '{name}' failed: {e}", exc_info=True)
            return name, None, "error", str(e), elapsed

    # Launch async sections in parallel
    async_sections = requested - {"participation"}
    tasks = [run_section(name) for name in async_sections if name in section_assemblers]
    results = await asyncio.gather(*tasks)

    # Collect results
    bundle_sections = {}
    section_status = {}
    section_errors = {}
    section_times = {}

    for name, result, status, error, elapsed in results:
        bundle_sections[name] = result
        section_status[name] = status
        section_times[name] = elapsed
        if error:
            section_errors[name] = error

    # Add participation
    if "participation" in requested:
        bundle_sections["participation"] = participation_result
        section_status["participation"] = participation_status
        section_times["participation"] = participation_time

    # Mark unrequested sections as skipped
    for s in ALL_SECTION_NAMES - requested:
        section_status[s] = "skipped"

    total_time = int((time.monotonic() - start_time) * 1000)

    metadata = ContextMetadata(
        assembled_at=datetime.now(timezone.utc),
        jurisdiction=jurisdiction,
        depth=depth.value,
        sections_included=sorted(requested),
        section_status=section_status,
        section_errors=section_errors,
        degraded=bool(section_errors),
        assembly_time_ms=total_time,
        section_times_ms=section_times,
    )

    return ContextBundle(
        item=context_item,
        sections=ContextSections(**bundle_sections),
        suggested_questions=generate_suggested_questions(item_type),
        metadata=metadata,
    )
