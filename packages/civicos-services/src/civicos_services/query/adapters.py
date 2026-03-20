"""
Per-corpus adapters — translate shared filter vocabulary into corpus-specific
backend calls and normalize results into CivicResult format.

Each adapter:
  1. Declares supported filters
  2. Calls storage/vector backends directly (no CivicOS middleman)
  3. Normalizes raw results into CivicResult (envelope + essential details)
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from civicos_services.query.models import CivicResult

logger = logging.getLogger(__name__)


class CorpusAdapter(ABC):
    """Base class for corpus adapters."""

    corpus_name: str  # Domain vocabulary name
    supported_filters: Set[str] = set()  # {"since", "until", "location", "query"}

    @abstractmethod
    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        """Execute search and return normalized results.

        Args:
            storage: StorageBackend instance
            vectors: Optional VectorBackend instance
            jurisdiction: Jurisdiction ID (e.g., "city-san-rafael")
            query: Search query string
            limit: Maximum results to return
            offset: Skip this many results before returning (for pagination).
        """
        ...

    def _make_ref(self, corpus_type: str, jurisdiction: str, item_id: str) -> str:
        """Build opaque ref string, avoiding doubled prefixes."""
        prefix = f"{corpus_type}:{jurisdiction}:"
        if item_id.startswith(prefix):
            return item_id  # ID already has the full ref prefix
        return f"{prefix}{item_id}"


class DecisionsAdapter(CorpusAdapter):
    corpus_name = "decisions"
    supported_filters = {"query", "since"}

    # Minimum cosine similarity to include in results (filters noise).
    # Nonsense queries score ~0.42-0.45; real queries score 0.50+ at top.
    MIN_RELEVANCE = 0.45

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        from civicos.history import search_decisions

        since = filters.get("since")
        decisions = search_decisions(
            state_manager=None,
            jurisdiction=jurisdiction,
            query=query,
            since=since,
            vector_backend=vectors,
            storage_backend=storage,
        )
        results = []
        for i, d in enumerate(decisions[offset:offset + limit]):
            # Use semantic similarity score from vector search when available
            if d.score is not None:
                relevance = max(0.0, min(1.0, d.score))
                if relevance < self.MIN_RELEVANCE:
                    continue  # Filter out low-relevance noise
            else:
                # Fallback for non-vector search paths (e.g., keyword-only)
                relevance = max(0.0, 1.0 - i * 0.05)
            results.append(CivicResult(
                type="decision",
                ref=self._make_ref("decision", jurisdiction, d.id),
                title=d.title,
                date=d.date.isoformat() if d.date else None,
                summary=f"{d.outcome} — {d.body}" if d.outcome else d.body,
                relevance=relevance,
                details={
                    "outcome": d.outcome,
                    "vote_summary": _format_votes(d.votes) if d.votes else None,
                    "body": d.body,
                },
            ))
        return results


class TestimonyAdapter(CorpusAdapter):
    corpus_name = "testimony"
    supported_filters = {"query"}

    def __init__(self, sub_corpus: Optional[str] = None):
        """sub_corpus: None (all), 'public', 'council', 'staff'"""
        self._sub_corpus = sub_corpus
        if sub_corpus:
            self.corpus_name = f"testimony:{sub_corpus}"

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        from civicos.history import search_transcripts

        fetch_count = offset + limit
        public_only = self._sub_corpus == "public"
        excerpts = search_transcripts(
            jurisdiction=jurisdiction,
            query=query,
            top_k=fetch_count,
            public_comment_only=public_only,
        )

        # Post-filter by sub-corpus if needed
        if self._sub_corpus and self._sub_corpus != "public":
            excerpts = [e for e in excerpts if e.speaker_role == self._sub_corpus]

        results = []
        for i, e in enumerate(excerpts[offset:offset + limit]):
            video_url = getattr(e, "video_url", None)
            results.append(CivicResult(
                type="testimony",
                ref=self._make_ref("testimony", jurisdiction, e.id),
                title=f"{e.speaker}: {e.text[:80]}..." if len(e.text) > 80 else f"{e.speaker}: {e.text}",
                date=None,  # Transcripts don't carry standalone dates
                summary=e.text[:300] if len(e.text) > 300 else e.text,
                relevance=max(0.0, min(1.0, e.score)) if e.score else max(0.0, 1.0 - i * 0.05),
                details={
                    "speaker": e.speaker,
                    "speaker_role": e.speaker_role,
                    "video_url": video_url,
                },
            ))
        return results


class LegislationAdapter(CorpusAdapter):
    corpus_name = "legislation"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        reg_stack = _get_regulatory_context(jurisdiction, query, storage, vectors, max_results=offset + limit)

        results = []
        # Combine state + federal legislation
        all_bills = []
        for bill in reg_stack.state:
            bill["_level"] = "state"
            all_bills.append(bill)
        for bill in reg_stack.federal:
            bill["_level"] = "federal"
            all_bills.append(bill)

        for i, bill in enumerate(all_bills[offset:offset + limit]):
            bill_number = bill.get("bill_number", "")
            bill_id = bill.get("bill_id", bill_number)
            status = bill.get("status_label", bill.get("status", ""))
            state = bill.get("state", "")

            results.append(CivicResult(
                type="legislation",
                ref=self._make_ref("legislation", jurisdiction, bill_id),
                title=bill.get("bill_name") or bill.get("title") or bill_number,
                date=bill.get("enacted_date"),
                summary=bill.get("summary", "")[:300] if bill.get("summary") else None,
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "bill_number": bill_number,
                    "status": status,
                    "state": state,
                },
            ))
        return results


class IssuesAdapter(CorpusAdapter):
    corpus_name = "issues"
    supported_filters = {"query", "location"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=offset + limit)

        # Client-side text filter (storage doesn't support query search)
        if query:
            q_lower = query.lower()
            issues = [
                iss for iss in issues
                if q_lower in (iss.get("summary", "") + " " + iss.get("description", "")).lower()
            ]

        results = []
        for i, issue in enumerate(issues[offset:offset + limit]):
            results.append(CivicResult(
                type="issue",
                ref=self._make_ref("issue", jurisdiction, issue.get("id", "")),
                title=issue.get("summary", issue.get("description", "")[:100]),
                date=issue.get("created_at"),
                summary=issue.get("description", "")[:300] if issue.get("description") else None,
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "status": issue.get("status"),
                    "category": issue.get("issue_type"),
                    "address": issue.get("address"),
                },
            ))
        return results


class MeetingsAdapter(CorpusAdapter):
    corpus_name = "meetings"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        # Query storage directly — wide window to capture recent meetings
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=365)
        meetings_data = storage.get_meetings(jurisdiction_id=jurisdiction, since=since)

        # Text filter on meeting titles/bodies
        if query:
            q_lower = query.lower()
            meetings_data = [
                m for m in meetings_data
                if q_lower in (m.get("title", "") + " " + m.get("body", "")).lower()
            ]

        results = []
        for i, m in enumerate(meetings_data[offset:offset + limit]):
            meeting_date = m.get("meeting_datetime") or m.get("date")
            if isinstance(meeting_date, str):
                date_str = meeting_date[:10]
            elif isinstance(meeting_date, datetime):
                date_str = meeting_date.isoformat()[:10]
            else:
                date_str = None

            results.append(CivicResult(
                type="meeting",
                ref=self._make_ref("meeting", jurisdiction, m.get("id", "")),
                title=m.get("title", ""),
                date=date_str,
                summary=m.get("body", ""),
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "agenda_item_count": len(m.get("agenda_items", [])),
                    "has_transcript": False,
                    "location": m.get("location", ""),
                },
            ))
        return results


class BudgetAdapter(CorpusAdapter):
    corpus_name = "budget"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        items = storage.get_budget_items(
            jurisdiction_id=jurisdiction,
            department=query if query else None,
            limit=offset + limit,
        )
        results = []
        for i, item in enumerate(items[offset:offset + limit]):
            # Budget items from storage are dicts; amounts in cents
            budgeted_cents = item.get("budgeted_cents", 0)
            budgeted_dollars = budgeted_cents / 100.0 if budgeted_cents else 0.0
            results.append(CivicResult(
                type="budget",
                ref=self._make_ref("budget", jurisdiction, item.get("id", "")),
                title=item.get("line_item", ""),
                date=None,
                summary=f"{item.get('department', '')} — {item.get('fund', '')}",
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "amount": budgeted_dollars,
                    "department": item.get("department", ""),
                    "fiscal_year": item.get("fiscal_year", ""),
                },
            ))
        return results


class MunicipalCodeAdapter(CorpusAdapter):
    corpus_name = "municipal_code"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        reg_stack = _get_regulatory_context(jurisdiction, query, storage, vectors, max_results=offset + limit)
        results = []
        for i, section in enumerate(reg_stack.local[offset:offset + limit]):
            results.append(CivicResult(
                type="municipal_code",
                ref=self._make_ref("municipal_code", jurisdiction, section.get("id", section.get("section_number", ""))),
                title=section.get("section_title", section.get("title", "")),
                date=None,
                summary=section.get("excerpt", section.get("text", ""))[:300] if section.get("excerpt") or section.get("text") else None,
                relevance=section.get("relevance_score", max(0.0, 1.0 - i * 0.05)),
                details={
                    "section_number": section.get("section_number"),
                    "chapter": section.get("chapter"),
                },
            ))
        return results


class PacketsAdapter(CorpusAdapter):
    corpus_name = "packets"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        from civicos.history import search_hybrid

        hybrid_results = search_hybrid(
            jurisdiction=jurisdiction,
            query=query,
            top_k=offset + limit,
            vector_backend=vectors,
        )
        results = []
        for i, hr in enumerate(hybrid_results[offset:offset + limit]):
            if hr.source_type == "pdf":
                results.append(CivicResult(
                    type="packet",
                    ref=self._make_ref("packet", jurisdiction, hr.id),
                    title=hr.agenda_item or f"Staff report: {query}",
                    date=None,
                    summary=hr.text[:300] if hr.text else None,
                    relevance=min(1.0, hr.score) if hr.score else max(0.0, 1.0 - i * 0.05),
                    details={
                        "source_type": "pdf",
                        "agenda_item": hr.agenda_item,
                        "page_start": hr.page_start,
                        "page_end": hr.page_end,
                    },
                ))
        return results


class CongressionalVotesAdapter(CorpusAdapter):
    corpus_name = "congressional_votes"
    supported_filters = {"query", "bioguide_id", "bill_id", "chamber"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        bioguide_id = filters.get("bioguide_id")
        bill_id = filters.get("bill_id")
        chamber = filters.get("chamber")

        # If query looks like a bill ID (e.g., "HR3424", "S 1947"), treat it as bill_id filter
        if query and not bill_id:
            q_upper = query.strip().upper().replace(".", "").replace(" ", "")
            if q_upper.startswith(("HR", "S", "HRES", "SRES", "HJRES", "SJRES", "HCONRES", "SCONRES")):
                bill_id = q_upper

        votes = storage.get_congressional_votes(
            bioguide_id=bioguide_id,
            bill_id=bill_id,
            chamber=chamber,
            limit=offset + limit,
        )

        # Client-side text filter when query is a topic keyword (not a bill ID)
        if query and not bill_id:
            q_lower = query.lower()
            votes = [
                v for v in votes
                if q_lower in (v.get("bill_title", "") + " " + v.get("vote_question", "")).lower()
            ]

        results = []
        for i, v in enumerate(votes[offset:offset + limit]):
            vote_id = v.get("vote_id", "")
            member = v.get("member_name", v.get("bioguide_id", ""))
            position = v.get("vote_position", "")
            bill_title = v.get("bill_title", "")
            vote_question = v.get("vote_question", "")

            title_parts = []
            if member:
                title_parts.append(member)
            title_parts.append(f"voted {position}")
            if bill_title:
                title_parts.append(f"on {bill_title[:60]}")

            results.append(CivicResult(
                type="congressional_vote",
                ref=self._make_ref("congressional_vote", jurisdiction, vote_id),
                title=" ".join(title_parts),
                date=v.get("vote_date"),
                summary=vote_question or bill_title,
                relevance=max(0.0, 1.0 - i * 0.03),
                details={
                    "vote_position": position,
                    "member_name": member,
                    "member_party": v.get("member_party"),
                    "chamber": v.get("chamber"),
                    "bill_id": v.get("bill_id"),
                    "bill_title": bill_title,
                    "roll_call_number": v.get("roll_call_number"),
                    "vote_result": v.get("vote_result"),
                },
            ))
        return results


class FederalAwardsAdapter(CorpusAdapter):
    corpus_name = "federal_awards"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        awards = storage.get_federal_awards(jurisdiction_id=jurisdiction, limit=offset + limit)

        if query:
            q_lower = query.lower()
            awards = [
                a for a in awards
                if q_lower in (a.get("description", "") + " " + a.get("awarding_agency_name", "")).lower()
            ]

        results = []
        for i, a in enumerate(awards[offset:offset + limit]):
            amount_cents = a.get("total_obligation_cents", 0)
            amount_dollars = amount_cents / 100.0 if amount_cents else 0.0
            results.append(CivicResult(
                type="federal_award",
                ref=self._make_ref("federal_award", jurisdiction, a.get("award_id", "")),
                title=a.get("description", "")[:100] or a.get("award_id", ""),
                date=a.get("start_date"),
                summary=f"{a.get('awarding_agency_name', '')} — ${amount_dollars:,.0f}",
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "amount": amount_dollars,
                    "agency": a.get("awarding_agency_name"),
                    "cfda_number": a.get("cfda_number"),
                },
            ))
        return results


class OrdersAdapter(CorpusAdapter):
    corpus_name = "orders"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        reg_stack = _get_regulatory_context(jurisdiction, query, storage, vectors, max_results=offset + limit)
        results = []
        for i, item in enumerate(reg_stack.federal[offset:offset + limit]):
            if "executive order" in (item.get("title", "") + item.get("type", "")).lower():
                results.append(CivicResult(
                    type="order",
                    ref=self._make_ref("order", jurisdiction, item.get("id", item.get("document_number", ""))),
                    title=item.get("title", ""),
                    date=item.get("signing_date") or item.get("publication_date"),
                    summary=item.get("abstract", item.get("summary", ""))[:300],
                    relevance=max(0.0, 1.0 - i * 0.05),
                    details={
                        "eo_number": item.get("eo_number"),
                        "president": item.get("president"),
                        "status": item.get("status"),
                    },
                ))
        return results


class RulesAdapter(CorpusAdapter):
    corpus_name = "rules"
    supported_filters = {"query"}

    def search(self, storage, vectors, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        reg_stack = _get_regulatory_context(jurisdiction, query, storage, vectors, max_results=offset + limit)
        results = []
        for i, item in enumerate(reg_stack.federal[offset:offset + limit]):
            if "executive order" not in (item.get("title", "") + item.get("type", "")).lower():
                results.append(CivicResult(
                    type="rule",
                    ref=self._make_ref("rule", jurisdiction, item.get("id", "")),
                    title=item.get("title", ""),
                    date=item.get("publication_date"),
                    summary=item.get("summary", "")[:300] if item.get("summary") else None,
                    relevance=max(0.0, 1.0 - i * 0.05),
                    details={
                        "agency": item.get("agency") or item.get("federal_agency"),
                        "document_type": item.get("type", "rule"),
                        "effective_date": item.get("effective_date"),
                    },
                ))
        return results


# === Adapter Registry ===

def _build_adapter_registry() -> Dict[str, CorpusAdapter]:
    """Build the corpus adapter registry."""
    adapters = {}
    for adapter_cls in [
        DecisionsAdapter,
        LegislationAdapter,
        IssuesAdapter,
        MeetingsAdapter,
        BudgetAdapter,
        MunicipalCodeAdapter,
        PacketsAdapter,
        OrdersAdapter,
        RulesAdapter,
        CongressionalVotesAdapter,
        FederalAwardsAdapter,
    ]:
        instance = adapter_cls()
        adapters[instance.corpus_name] = instance

    # Testimony sub-corpora
    adapters["testimony"] = TestimonyAdapter()
    adapters["testimony:public"] = TestimonyAdapter(sub_corpus="public")
    adapters["testimony:council"] = TestimonyAdapter(sub_corpus="council")
    adapters["testimony:staff"] = TestimonyAdapter(sub_corpus="staff")

    return adapters


ADAPTER_REGISTRY: Dict[str, CorpusAdapter] = _build_adapter_registry()


def get_adapter(corpus_name: str) -> Optional[CorpusAdapter]:
    """Get adapter for a corpus name."""
    return ADAPTER_REGISTRY.get(corpus_name)


def list_corpus_names() -> List[str]:
    """List all supported corpus names."""
    return sorted(ADAPTER_REGISTRY.keys())


def _get_regulatory_context(jurisdiction, topic, storage, vectors, max_results=30):
    """Helper to call get_regulatory_context with storage/vector backends."""
    from civicos.context import get_regulatory_context
    return get_regulatory_context(
        jurisdiction=jurisdiction,
        topic=topic,
        storage=storage,
        vectors=vectors,
        max_results=max_results,
    )


def _format_votes(votes: Optional[dict]) -> Optional[str]:
    """Format vote dict into summary string."""
    if not votes:
        return None
    yes = votes.get("yes", votes.get("Yes", 0))
    no = votes.get("no", votes.get("No", 0))
    return f"{yes}-{no}"
