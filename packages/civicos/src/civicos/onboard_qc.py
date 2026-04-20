"""
Onboard quality gates — post-ingest checks for newly onboarded jurisdictions.

Encodes patterns discovered during the April 2026 jurisdiction QC walkthrough
so future onboards surface them automatically instead of requiring a human sweep.

Usage:
    from civicos.onboard_qc import run_onboard_qc

    report = run_onboard_qc(storage, "city-san-rafael")
    print(report.format())
    if report.has_failures:
        sys.exit(1)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

from .storage.backend import StorageBackend


Severity = Literal["fail", "warn", "ok"]

_VIEW_KEY_PATTERN = re.compile(r"^view_\d+$")
_PHANTOM_TITLE_PATTERNS = [
    re.compile(r"^\s*spanish audio files\s*$", re.IGNORECASE),
    re.compile(r"^\s*system test\s*$", re.IGNORECASE),
    re.compile(r"^\s*test meeting\s*$", re.IGNORECASE),
    re.compile(r"^\s*closed session\s*$", re.IGNORECASE),
]

AGENDA_URL_THRESHOLD = 0.80
CLOSING_CHUNK_THRESHOLD = 0.50
TITLE_OVERLAP_THRESHOLD = 0.70


@dataclass
class QCCheck:
    name: str
    severity: Severity
    message: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OnboardQCReport:
    jurisdiction_id: str
    checks: List[QCCheck]

    @property
    def has_failures(self) -> bool:
        return any(c.severity == "fail" for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.severity == "warn" for c in self.checks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "has_failures": self.has_failures,
            "has_warnings": self.has_warnings,
            "checks": [
                {"name": c.name, "severity": c.severity, "message": c.message, "detail": c.detail}
                for c in self.checks
            ],
        }

    def format(self) -> str:
        glyph = {"fail": "FAIL", "warn": "WARN", "ok": " OK "}
        lines = [f"Onboard QC: {self.jurisdiction_id}"]
        for c in self.checks:
            lines.append(f"  [{glyph[c.severity]}] {c.name}: {c.message}")
        return "\n".join(lines)


def check_agenda_url_coverage(
    storage: StorageBackend, jurisdiction_id: str, threshold: float = AGENDA_URL_THRESHOLD
) -> QCCheck:
    """Fail if agenda_url coverage falls below threshold.

    Catches the Simbli partial pattern (school-novato, school-tamalpais,
    school-san-rafael) where meetings ingest but chunks never do because
    the Simbli source doesn't populate agenda_url.
    """
    meetings = storage.get_meetings(jurisdiction_id)
    if not meetings:
        return QCCheck(
            "agenda_url_coverage", "warn", "No meetings ingested yet — cannot assess."
        )
    with_url = sum(1 for m in meetings if m.get("agenda_url"))
    ratio = with_url / len(meetings)
    detail = {"total": len(meetings), "with_agenda_url": with_url, "ratio": round(ratio, 3)}
    if ratio < threshold:
        return QCCheck(
            "agenda_url_coverage",
            "fail",
            f"{with_url}/{len(meetings)} ({ratio:.0%}) meetings have agenda_url "
            f"(threshold {threshold:.0%}). Chunks pipeline will be empty.",
            detail,
        )
    return QCCheck(
        "agenda_url_coverage", "ok", f"{ratio:.0%} of meetings have agenda_url.", detail
    )


def check_meeting_type_sanity(storage: StorageBackend, jurisdiction_id: str) -> QCCheck:
    """Fail if meeting_type leaks a legacy archive key or is null.

    Catches two bugs: Berkeley-style `view_2/view_5` archive keys flowing
    through as meeting_type (pre-LLM manual configs), and the universal.py
    inference bug that emits NULL when titles lack a separator.
    """
    meetings = storage.get_meetings(jurisdiction_id)
    if not meetings:
        return QCCheck("meeting_type_sanity", "warn", "No meetings to check.")
    suspicious: Counter[str] = Counter()
    for m in meetings:
        mt = m.get("meeting_type")
        if mt is None or mt == "":
            suspicious["<null>"] += 1
        elif _VIEW_KEY_PATTERN.match(str(mt)):
            suspicious[str(mt)] += 1
    if suspicious:
        total_bad = sum(suspicious.values())
        return QCCheck(
            "meeting_type_sanity",
            "fail",
            f"{total_bad}/{len(meetings)} meetings have suspicious meeting_type values: "
            f"{dict(suspicious.most_common(5))}",
            {"total": len(meetings), "bad_values": dict(suspicious)},
        )
    return QCCheck(
        "meeting_type_sanity",
        "ok",
        f"All {len(meetings)} meetings have non-null, non-leaky meeting_type.",
    )


def check_chunk_closing_ratio(
    storage: StorageBackend, jurisdiction_id: str, threshold: float = CLOSING_CHUNK_THRESHOLD
) -> QCCheck:
    """Warn when 'closing' agenda_item dominates.

    The pdf_parser used to silently label every chunk 'closing' when its
    AGENDA_ITEM_PATTERN regex failed (e.g., numbered-bullet agendas from
    Alameda). Fixed in commit 1cc27a5b but worth checking regressions.
    """
    total = storage.get_chunk_count(jurisdiction_id)
    if total == 0:
        return QCCheck("chunk_closing_ratio", "ok", "No chunks to check.")
    closing = storage.get_chunks(jurisdiction_id, agenda_item="closing")
    closing_count = len(closing)
    ratio = closing_count / total
    detail = {"total": total, "closing": closing_count, "ratio": round(ratio, 3)}
    if ratio > threshold:
        return QCCheck(
            "chunk_closing_ratio",
            "warn",
            f"{closing_count}/{total} ({ratio:.0%}) chunks labelled 'closing' "
            f"(threshold {threshold:.0%}). Likely pdf_parser fallback dominance.",
            detail,
        )
    return QCCheck(
        "chunk_closing_ratio", "ok", f"{ratio:.0%} chunks labelled 'closing'.", detail
    )


def _title_token_overlap(a: str, b: str) -> float:
    """Fraction of shorter title's tokens that appear in the longer title."""
    tokens_a = {t for t in re.findall(r"\w+", a.lower()) if len(t) > 2}
    tokens_b = {t for t in re.findall(r"\w+", b.lower()) if len(t) > 2}
    if not tokens_a or not tokens_b:
        return 0.0
    shorter, longer = sorted([tokens_a, tokens_b], key=len)
    return len(shorter & longer) / len(shorter)


def check_same_date_title_duplicates(
    storage: StorageBackend,
    jurisdiction_id: str,
    overlap_threshold: float = TITLE_OVERLAP_THRESHOLD,
) -> QCCheck:
    """Warn on same-date meeting pairs with high title overlap.

    Catches the Granicus upcoming-vs-archive dedup gap: the default view
    surfaces "City Council Meeting" and the per-body archive surfaces
    "Regular City Council Meeting - 6:00 p.m." — same meeting, different
    meeting_id, no dedup.
    """
    meetings = storage.get_meetings(jurisdiction_id)
    if len(meetings) < 2:
        return QCCheck("same_date_title_duplicates", "ok", "Too few meetings to check.")

    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for m in meetings:
        dt = m.get("meeting_datetime") or ""
        date_key = str(dt)[:10]
        if not date_key:
            continue
        by_date.setdefault(date_key, []).append(m)

    suspect_pairs = []
    for date_key, same_date in by_date.items():
        if len(same_date) < 2:
            continue
        for i in range(len(same_date)):
            for j in range(i + 1, len(same_date)):
                a, b = same_date[i], same_date[j]
                title_a = (a.get("title") or "").strip()
                title_b = (b.get("title") or "").strip()
                if not title_a or not title_b or title_a == title_b:
                    continue
                overlap = _title_token_overlap(title_a, title_b)
                if overlap >= overlap_threshold:
                    suspect_pairs.append(
                        {
                            "date": date_key,
                            "title_a": title_a,
                            "title_b": title_b,
                            "overlap": round(overlap, 2),
                            "id_a": a.get("id"),
                            "id_b": b.get("id"),
                        }
                    )

    if suspect_pairs:
        return QCCheck(
            "same_date_title_duplicates",
            "warn",
            f"{len(suspect_pairs)} same-date meeting pair(s) with ≥{overlap_threshold:.0%} "
            "title overlap — likely upcoming-vs-archive duplicates.",
            {"pairs": suspect_pairs[:10], "total_pairs": len(suspect_pairs)},
        )
    return QCCheck(
        "same_date_title_duplicates",
        "ok",
        "No suspicious same-date title duplicates.",
    )


def check_phantom_title_patterns(storage: StorageBackend, jurisdiction_id: str) -> QCCheck:
    """Warn on titles matching known phantom patterns.

    Most are filtered at extraction time (granicus.py skips Spanish Audio
    Files and System Test), but this guards against new platforms or
    pre-filter historical rows.
    """
    meetings = storage.get_meetings(jurisdiction_id)
    if not meetings:
        return QCCheck("phantom_title_patterns", "ok", "No meetings.")
    hits: List[Dict[str, Any]] = []
    for m in meetings:
        title = (m.get("title") or "").strip()
        for pat in _PHANTOM_TITLE_PATTERNS:
            if pat.match(title):
                hits.append({"id": m.get("id"), "title": title, "pattern": pat.pattern})
                break
    if hits:
        return QCCheck(
            "phantom_title_patterns",
            "warn",
            f"{len(hits)} meeting(s) match known phantom title patterns "
            "(spanish audio files, system test, test meeting, closed session).",
            {"examples": hits[:5], "total": len(hits)},
        )
    return QCCheck("phantom_title_patterns", "ok", "No phantom title patterns detected.")


def run_onboard_qc(storage: StorageBackend, jurisdiction_id: str) -> OnboardQCReport:
    """Run all onboard quality gates against a freshly-ingested jurisdiction."""
    checks = [
        check_agenda_url_coverage(storage, jurisdiction_id),
        check_meeting_type_sanity(storage, jurisdiction_id),
        check_chunk_closing_ratio(storage, jurisdiction_id),
        check_same_date_title_duplicates(storage, jurisdiction_id),
        check_phantom_title_patterns(storage, jurisdiction_id),
    ]
    return OnboardQCReport(jurisdiction_id=jurisdiction_id, checks=checks)
