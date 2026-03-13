"""
Per-corpus adapters — translate shared filter vocabulary into corpus-specific API calls
and normalize results into CivicResult format.

Each adapter:
  1. Declares supported filters
  2. Translates filters into CivicOS API call params
  3. Normalizes raw results into CivicResult (envelope + essential details)
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from civicos_services.query.models import CivicResult

logger = logging.getLogger(__name__)


class CorpusAdapter(ABC):
    """Base class for corpus adapters."""

    corpus_name: str  # Domain vocabulary name
    supported_filters: Set[str] = set()  # {"since", "until", "location", "query"}

    @abstractmethod
    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        """Execute search and return normalized results.

        Args:
            offset: Skip this many results before returning (for pagination).
        """
        ...

    def _make_ref(self, corpus_type: str, jurisdiction: str, item_id: str) -> str:
        """Build opaque ref string."""
        return f"{corpus_type}:{jurisdiction}:{item_id}"


class DecisionsAdapter(CorpusAdapter):
    corpus_name = "decisions"
    supported_filters = {"query", "since"}

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        kwargs = {}
        if filters.get("since"):
            kwargs["since"] = filters["since"]

        decisions = civic.what_happened(query, **kwargs)
        results = []
        for i, d in enumerate(decisions[offset:offset + limit]):
            results.append(CivicResult(
                type="decision",
                ref=self._make_ref("decision", jurisdiction, d.id),
                title=d.title,
                date=d.date.isoformat() if d.date else None,
                summary=f"{d.outcome} — {d.body}" if d.outcome else d.body,
                relevance=max(0.0, 1.0 - i * 0.05),  # rank-based
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

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        fetch_count = offset + limit
        if self._sub_corpus == "public":
            excerpts = civic.get_public_testimony(query, top_k=fetch_count)
        else:
            excerpts = civic.what_was_said(query, top_k=fetch_count)

        # Post-filter by sub-corpus if needed
        if self._sub_corpus and self._sub_corpus != "public":
            excerpts = [e for e in excerpts if e.speaker_role == self._sub_corpus]

        results = []
        for i, e in enumerate(excerpts[offset:offset + limit]):
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
                    "video_url": e.video_url,
                },
            ))
        return results


class LegislationAdapter(CorpusAdapter):
    corpus_name = "legislation"
    supported_filters = {"query"}

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        reg_stack = civic.what_applies(query, max_results=offset + limit)

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

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        issues = civic.search_issues(query, limit=offset + limit)
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

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        # Use public whats_next API — CivicOS is already jurisdiction-scoped
        meetings = civic.whats_next(days=365)  # wide window to capture recent meetings

        # Text filter on meeting titles/bodies
        if query:
            q_lower = query.lower()
            meetings = [
                m for m in meetings
                if q_lower in (m.title + " " + m.body).lower()
                or any(q_lower in (a.get("title", "")).lower() for a in m.agenda_items)
            ]

        results = []
        for i, m in enumerate(meetings[offset:offset + limit]):
            results.append(CivicResult(
                type="meeting",
                ref=self._make_ref("meeting", jurisdiction, m.id),
                title=m.title,
                date=m.date.isoformat()[:10] if m.date else None,
                summary=m.body,
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "agenda_item_count": len(m.agenda_items),
                    "has_transcript": False,
                    "location": m.location,
                },
            ))
        return results


class BudgetAdapter(CorpusAdapter):
    corpus_name = "budget"
    supported_filters = {"query"}

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        items = civic.budget(department=query, limit=offset + limit)
        results = []
        for i, item in enumerate(items[offset:offset + limit]):
            results.append(CivicResult(
                type="budget",
                ref=self._make_ref("budget", jurisdiction, item.id),
                title=item.line_item,
                date=None,
                summary=f"{item.department} — {item.fund}",
                relevance=max(0.0, 1.0 - i * 0.05),
                details={
                    "amount": item.budgeted_dollars,
                    "department": item.department,
                    "fiscal_year": item.fiscal_year,
                },
            ))
        return results


class MunicipalCodeAdapter(CorpusAdapter):
    corpus_name = "municipal_code"
    supported_filters = {"query"}

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        # Municipal code is searched via what_applies (local component)
        reg_stack = civic.what_applies(query, max_results=offset + limit)
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

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        # Agenda packets via what_happened_with_discussion — returns HybridSearchResult
        hybrid_results = civic.what_happened_with_discussion(query, top_k=offset + limit)
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


class OrdersAdapter(CorpusAdapter):
    corpus_name = "orders"
    supported_filters = {"query"}

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        # Executive orders from what_applies federal component
        reg_stack = civic.what_applies(query, max_results=offset + limit)
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

    def search(self, civic, jurisdiction: str, query: str, limit: int, offset: int = 0, **filters) -> List[CivicResult]:
        # Federal rules — use what_applies if available
        reg_stack = civic.what_applies(query, max_results=offset + limit)
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


def _format_votes(votes: Optional[dict]) -> Optional[str]:
    """Format vote dict into summary string."""
    if not votes:
        return None
    yes = votes.get("yes", votes.get("Yes", 0))
    no = votes.get("no", votes.get("No", 0))
    return f"{yes}-{no}"
