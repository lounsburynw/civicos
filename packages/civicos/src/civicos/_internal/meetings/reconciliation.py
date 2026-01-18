"""
Decision-Transcript Reconciliation Module.

Links decisions (from official minutes) to transcript chunks (from video recordings)
using a consensus approach that combines:
1. Structural matching (agenda_item metadata)
2. Semantic matching (embedding similarity)

When both signals agree, confidence is high. When they disagree, anomalies are flagged.
This enables both query enrichment and data validation use cases.

Usage:
    from civicos._internal.meetings.reconciliation import DecisionTranscriptReconciler

    reconciler = DecisionTranscriptReconciler("city-san-rafael", embeddings_client)
    result = reconciler.reconcile_meeting(
        meeting_date="2024-10-06",
        decisions=decisions_list,
    )
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AgendaItemTag:
    """Rich tagging model for agenda items in transcript segments."""
    item_number: str          # "5.a", "consent", "public_hearing"
    confidence: float         # 0.0-1.0 detection confidence
    tag_type: str            # "primary", "secondary", "mentioned", "transition"
    detection_source: str    # "structural", "semantic", "consensus", "inherited"
    span_coverage: float = 1.0  # 0.0-1.0 how much of chunk is about this item

    def to_metadata_str(self) -> str:
        """Serialize for ChromaDB (which requires flat types)."""
        return f"{self.item_number}:{self.confidence:.2f}:{self.tag_type}:{self.detection_source}"

    @classmethod
    def from_metadata_str(cls, s: str) -> "AgendaItemTag":
        """Deserialize from ChromaDB metadata string."""
        parts = s.split(":")
        return cls(
            item_number=parts[0],
            confidence=float(parts[1]) if len(parts) > 1 else 0.5,
            tag_type=parts[2] if len(parts) > 2 else "unknown",
            detection_source=parts[3] if len(parts) > 3 else "stored",
            span_coverage=1.0
        )


@dataclass
class MatchSignal:
    """A single matching signal between decision and transcript chunk."""
    chunk_id: str
    signal_type: str  # "structural", "semantic"
    score: float      # 0.0-1.0
    details: str      # Human-readable explanation


@dataclass
class ReconciliationLink:
    """A single link between a decision and transcript chunks."""
    decision_id: str
    chunk_ids: List[str]
    confidence: float  # Overall link confidence
    link_type: str     # "consensus", "structural_only", "semantic_only", "inferred"

    # Individual signal scores
    structural_score: float = 0.0   # Based on agenda_item match
    semantic_score: float = 0.0     # Based on embedding similarity
    agreement_bonus: float = 0.0    # Bonus when signals agree

    # Validation scores (secondary signals)
    title_overlap_score: float = 0.0
    timing_score: float = 0.0
    speaker_role_score: float = 0.0

    # Edge case flags
    is_out_of_order: bool = False
    is_revisited: bool = False
    is_multi_item: bool = False
    is_consent_calendar: bool = False
    signals_disagree: bool = False  # Flag when structural != semantic

    # Metadata
    meeting_date: str = ""
    agenda_item: str = ""
    decision_title: str = ""
    transcript_text_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "decision_id": self.decision_id,
            "chunk_ids": self.chunk_ids,
            "confidence": self.confidence,
            "link_type": self.link_type,
            "structural_score": self.structural_score,
            "semantic_score": self.semantic_score,
            "agreement_bonus": self.agreement_bonus,
            "title_overlap_score": self.title_overlap_score,
            "timing_score": self.timing_score,
            "speaker_role_score": self.speaker_role_score,
            "is_out_of_order": self.is_out_of_order,
            "is_revisited": self.is_revisited,
            "is_multi_item": self.is_multi_item,
            "is_consent_calendar": self.is_consent_calendar,
            "signals_disagree": self.signals_disagree,
            "meeting_date": self.meeting_date,
            "agenda_item": self.agenda_item,
            "decision_title": self.decision_title,
            "transcript_text_preview": self.transcript_text_preview,
        }


@dataclass
class Anomaly:
    """An anomaly detected during reconciliation."""
    anomaly_type: str  # "signal_disagreement", "missing_transcript", "semantic_mismatch", etc.
    description: str
    decision_id: Optional[str] = None
    chunk_ids: List[str] = field(default_factory=list)
    severity: str = "warning"  # "info", "warning", "error"
    structural_item: Optional[str] = None  # What structural match said
    semantic_item: Optional[str] = None    # What semantic match suggested

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "description": self.description,
            "decision_id": self.decision_id,
            "chunk_ids": self.chunk_ids,
            "severity": self.severity,
            "structural_item": self.structural_item,
            "semantic_item": self.semantic_item,
        }


@dataclass
class ReconciliationResult:
    """Result of reconciling one meeting."""
    meeting_date: str
    meeting_id: str

    # Links
    links: List[ReconciliationLink] = field(default_factory=list)

    # Link type breakdown
    consensus_links: int = 0      # Both signals agree
    structural_only_links: int = 0  # Only structural match
    semantic_only_links: int = 0    # Only semantic match
    disagreement_links: int = 0     # Signals disagree

    # Unmatched items
    unmatched_decisions: List[str] = field(default_factory=list)
    unmatched_chunks: List[str] = field(default_factory=list)

    # Quality metrics
    overall_confidence: float = 0.0
    coverage_decisions: float = 0.0
    coverage_transcripts: float = 0.0

    # Anomalies detected
    anomalies: List[Anomaly] = field(default_factory=list)

    # Processing metadata
    processing_time_ms: int = 0
    decisions_count: int = 0
    chunks_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meeting_date": self.meeting_date,
            "meeting_id": self.meeting_id,
            "links": [link.to_dict() for link in self.links],
            "consensus_links": self.consensus_links,
            "structural_only_links": self.structural_only_links,
            "semantic_only_links": self.semantic_only_links,
            "disagreement_links": self.disagreement_links,
            "unmatched_decisions": self.unmatched_decisions,
            "unmatched_chunks": self.unmatched_chunks,
            "overall_confidence": self.overall_confidence,
            "coverage_decisions": self.coverage_decisions,
            "coverage_transcripts": self.coverage_transcripts,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "processing_time_ms": self.processing_time_ms,
            "decisions_count": self.decisions_count,
            "chunks_count": self.chunks_count,
        }


@dataclass
class BatchReconciliationResult:
    """Result of reconciling multiple meetings."""
    jurisdiction_id: str
    meeting_results: List[ReconciliationResult] = field(default_factory=list)

    # Aggregate metrics
    total_decisions: int = 0
    total_chunks: int = 0
    total_links: int = 0

    # Link type breakdown
    total_consensus: int = 0
    total_structural_only: int = 0
    total_semantic_only: int = 0
    total_disagreements: int = 0

    # Confidence breakdown
    high_confidence_links: int = 0
    medium_confidence_links: int = 0
    low_confidence_links: int = 0

    # Meeting status
    meetings_fully_reconciled: int = 0
    meetings_partial: int = 0
    meetings_failed: int = 0

    # Aggregate coverage
    overall_decision_coverage: float = 0.0
    overall_transcript_coverage: float = 0.0

    def compute_aggregates(self):
        """Compute aggregate metrics from meeting results."""
        if not self.meeting_results:
            return

        total_decisions_with_links = 0
        total_chunks_with_links = 0

        for result in self.meeting_results:
            self.total_decisions += result.decisions_count
            self.total_chunks += result.chunks_count
            self.total_links += len(result.links)

            self.total_consensus += result.consensus_links
            self.total_structural_only += result.structural_only_links
            self.total_semantic_only += result.semantic_only_links
            self.total_disagreements += result.disagreement_links

            for link in result.links:
                if link.confidence >= 0.8:
                    self.high_confidence_links += 1
                elif link.confidence >= 0.5:
                    self.medium_confidence_links += 1
                else:
                    self.low_confidence_links += 1

            linked_decisions = len(set(l.decision_id for l in result.links))
            linked_chunks = len(set(cid for l in result.links for cid in l.chunk_ids))
            total_decisions_with_links += linked_decisions
            total_chunks_with_links += linked_chunks

            if result.coverage_decisions >= 0.9:
                self.meetings_fully_reconciled += 1
            elif result.coverage_decisions > 0:
                self.meetings_partial += 1
            else:
                self.meetings_failed += 1

        if self.total_decisions > 0:
            self.overall_decision_coverage = total_decisions_with_links / self.total_decisions
        if self.total_chunks > 0:
            self.overall_transcript_coverage = total_chunks_with_links / self.total_chunks

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "meeting_results": [r.to_dict() for r in self.meeting_results],
            "total_decisions": self.total_decisions,
            "total_chunks": self.total_chunks,
            "total_links": self.total_links,
            "total_consensus": self.total_consensus,
            "total_structural_only": self.total_structural_only,
            "total_semantic_only": self.total_semantic_only,
            "total_disagreements": self.total_disagreements,
            "high_confidence_links": self.high_confidence_links,
            "medium_confidence_links": self.medium_confidence_links,
            "low_confidence_links": self.low_confidence_links,
            "meetings_fully_reconciled": self.meetings_fully_reconciled,
            "meetings_partial": self.meetings_partial,
            "meetings_failed": self.meetings_failed,
            "overall_decision_coverage": self.overall_decision_coverage,
            "overall_transcript_coverage": self.overall_transcript_coverage,
        }

    def to_report(self) -> str:
        """Generate human-readable quality report."""
        lines = [
            f"=== Reconciliation Report: {self.jurisdiction_id} ===",
            f"",
            f"Meetings: {len(self.meeting_results)} total",
            f"  - Fully reconciled (>=90%): {self.meetings_fully_reconciled}",
            f"  - Partial: {self.meetings_partial}",
            f"  - Failed: {self.meetings_failed}",
            f"",
            f"Coverage:",
            f"  - Decisions with transcript links: {self.overall_decision_coverage:.1%}",
            f"  - Transcript chunks with decisions: {self.overall_transcript_coverage:.1%}",
            f"",
            f"Links: {self.total_links} total",
            f"  - Consensus (both signals agree): {self.total_consensus}",
            f"  - Structural only: {self.total_structural_only}",
            f"  - Semantic only: {self.total_semantic_only}",
            f"  - Signals disagree: {self.total_disagreements}",
            f"",
            f"Confidence distribution:",
            f"  - High (>=0.8): {self.high_confidence_links}",
            f"  - Medium (0.5-0.8): {self.medium_confidence_links}",
            f"  - Low (<0.5): {self.low_confidence_links}",
        ]
        return "\n".join(lines)


# =============================================================================
# Edge Case Handlers
# =============================================================================

class EdgeCaseHandler:
    """Handle special cases in agenda item alignment."""

    OUT_OF_ORDER_PATTERN = re.compile(
        r"let'?s\s+take\s+item\s+(\d+[.-]?[a-zA-Z]?)\s+(?:before|first|now)",
        re.IGNORECASE
    )

    REVISIT_PATTERN = re.compile(
        r"(?:going\s+back|return(?:ing)?|back)\s+to\s+item\s+(\d+[.-]?[a-zA-Z]?)",
        re.IGNORECASE
    )

    MULTI_ITEM_PATTERN = re.compile(
        r"(?:comparing|both|together|along\s+with)\s+(?:items?\s+)?(\d+[.-]?[a-zA-Z]?)\s+(?:and|with)\s+(\d+[.-]?[a-zA-Z]?)",
        re.IGNORECASE
    )

    CONSENT_CALENDAR_PATTERN = re.compile(
        r"consent\s+(?:calendar|agenda)(?:\s+items?)?\s*(?:(\d+[.-]?[a-zA-Z]?)\s+through\s+(\d+[.-]?[a-zA-Z]?))?",
        re.IGNORECASE
    )

    PULLED_ITEM_PATTERN = re.compile(
        r"(?:pull(?:ed|ing)?|remove[d]?|separate)\s+item\s+(\d+[.-]?[a-zA-Z]?)",
        re.IGNORECASE
    )

    @classmethod
    def detect_edge_case(cls, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text indicates an edge case."""
        match = cls.OUT_OF_ORDER_PATTERN.search(text)
        if match:
            return {"type": "out_of_order", "item": cls._normalize_item(match.group(1))}

        match = cls.REVISIT_PATTERN.search(text)
        if match:
            return {"type": "revisit", "item": cls._normalize_item(match.group(1))}

        match = cls.MULTI_ITEM_PATTERN.search(text)
        if match:
            return {
                "type": "multi_item",
                "items": [cls._normalize_item(match.group(1)), cls._normalize_item(match.group(2))],
            }

        match = cls.CONSENT_CALENDAR_PATTERN.search(text)
        if match:
            result = {"type": "consent_calendar"}
            if match.group(1) and match.group(2):
                result["range_start"] = cls._normalize_item(match.group(1))
                result["range_end"] = cls._normalize_item(match.group(2))
            return result

        match = cls.PULLED_ITEM_PATTERN.search(text)
        if match:
            return {"type": "pulled_item", "item": cls._normalize_item(match.group(1))}

        return None

    @classmethod
    def _normalize_item(cls, item: str) -> str:
        """Normalize agenda item format to lowercase with period separator."""
        if not item:
            return item
        item = item.lower().replace("-", ".")
        if len(item) >= 2 and item[-1].isalpha() and item[-2].isdigit():
            item = item[:-1] + "." + item[-1]
        return item


def normalize_agenda_item(item: str) -> str:
    """Normalize agenda item format for consistent matching."""
    return EdgeCaseHandler._normalize_item(item)


# =============================================================================
# Main Reconciler
# =============================================================================

class DecisionTranscriptReconciler:
    """
    Reconciles decisions with transcript chunks using consensus of signals.

    Combines:
    1. Structural matching (agenda_item metadata from pattern detection)
    2. Semantic matching (embedding similarity between decision and chunks)

    When signals agree → high confidence
    When signals disagree → flag anomaly, use weighted combination
    """

    # Weights for consensus scoring
    STRUCTURAL_WEIGHT = 0.4
    SEMANTIC_WEIGHT = 0.4
    AGREEMENT_BONUS = 0.2  # Bonus when both signals point to same chunks

    # Thresholds
    SEMANTIC_THRESHOLD = 0.5     # Minimum semantic similarity to consider
    STRUCTURAL_THRESHOLD = 0.7  # Minimum structural confidence to consider
    DISAGREEMENT_THRESHOLD = 0.3  # If difference > this, flag as disagreement

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        embeddings_client=None,
        semantic_top_k: int = 5,
    ):
        """
        Initialize the reconciler.

        Args:
            jurisdiction_id: Jurisdiction identifier
            embeddings_client: CivicEmbeddings instance for semantic search
            semantic_top_k: Number of top semantic matches to consider per decision
        """
        self.jurisdiction_id = jurisdiction_id
        self.embeddings_client = embeddings_client
        self.semantic_top_k = semantic_top_k
        self.edge_handler = EdgeCaseHandler()

    def reconcile_meeting(
        self,
        meeting_date: str,
        decisions: List[Dict[str, Any]],
        transcript_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> ReconciliationResult:
        """
        Reconcile a meeting using consensus of structural and semantic signals.

        Args:
            meeting_date: ISO date (YYYY-MM-DD)
            decisions: List of decision dicts
            transcript_chunks: Optional pre-loaded chunks (will query if not provided)

        Returns:
            ReconciliationResult with consensus-based links
        """
        import time
        start_time = time.time()

        meeting_id = f"{self.jurisdiction_id}-{meeting_date}"
        result = ReconciliationResult(
            meeting_date=meeting_date,
            meeting_id=meeting_id,
            decisions_count=len(decisions),
        )

        if not decisions:
            result.anomalies.append(Anomaly(
                anomaly_type="no_decisions",
                description=f"No decisions found for meeting {meeting_date}",
                severity="warning",
            ))
            return result

        # Load transcript chunks if not provided
        if transcript_chunks is None:
            transcript_chunks = self._load_transcript_chunks(meeting_date)

        result.chunks_count = len(transcript_chunks)

        if not transcript_chunks:
            result.anomalies.append(Anomaly(
                anomaly_type="no_transcript",
                description=f"No transcript chunks found for meeting {meeting_date}",
                severity="warning",
            ))
            result.unmatched_decisions = [d.get("decision_id", "") for d in decisions]
            return result

        # Build structural index (chunks by agenda_item)
        structural_index = self._build_structural_index(transcript_chunks)

        # Process each decision
        linked_decision_ids: Set[str] = set()
        linked_chunk_ids: Set[str] = set()

        for decision in decisions:
            link = self._reconcile_decision(
                decision=decision,
                meeting_date=meeting_date,
                transcript_chunks=transcript_chunks,
                structural_index=structural_index,
            )

            if link:
                result.links.append(link)
                linked_decision_ids.add(link.decision_id)
                linked_chunk_ids.update(link.chunk_ids)

                # Categorize link type
                if link.link_type == "consensus":
                    result.consensus_links += 1
                elif link.link_type == "structural_only":
                    result.structural_only_links += 1
                elif link.link_type == "semantic_only":
                    result.semantic_only_links += 1

                if link.signals_disagree:
                    result.disagreement_links += 1
            else:
                result.unmatched_decisions.append(decision.get("decision_id", ""))

        # Find unmatched chunks
        all_chunk_ids = set(self._get_chunk_id(c) for c in transcript_chunks)
        result.unmatched_chunks = list(all_chunk_ids - linked_chunk_ids)

        # Calculate coverage
        if result.decisions_count > 0:
            result.coverage_decisions = len(linked_decision_ids) / result.decisions_count
        if result.chunks_count > 0:
            result.coverage_transcripts = len(linked_chunk_ids) / result.chunks_count

        # Overall confidence
        if result.links:
            result.overall_confidence = sum(l.confidence for l in result.links) / len(result.links)

        result.processing_time_ms = int((time.time() - start_time) * 1000)
        return result

    def _reconcile_decision(
        self,
        decision: Dict[str, Any],
        meeting_date: str,
        transcript_chunks: List[Dict[str, Any]],
        structural_index: Dict[str, List[Dict]],
    ) -> Optional[ReconciliationLink]:
        """
        Reconcile a single decision using consensus approach.

        Returns:
            ReconciliationLink or None if no match found
        """
        decision_id = decision.get("decision_id", "")
        agenda_item = decision.get("agenda_item", "")
        title = decision.get("title", "")
        summary = decision.get("summary", "")

        # === Signal 1: Structural match (agenda_item) ===
        structural_chunks: List[Dict] = []
        structural_score = 0.0

        if agenda_item:
            normalized_item = normalize_agenda_item(agenda_item)
            structural_chunks = structural_index.get(normalized_item, [])
            if structural_chunks:
                structural_score = 0.9  # High confidence if exact match

        # === Signal 2: Semantic match (embedding similarity) ===
        semantic_chunks: List[Tuple[Dict, float]] = []  # (chunk, similarity_score)
        semantic_score = 0.0

        if self.embeddings_client and (title or summary):
            query_text = f"{title} {summary}".strip()
            semantic_chunks = self._semantic_search(
                query_text=query_text,
                meeting_date=meeting_date,
                top_k=self.semantic_top_k,
            )
            if semantic_chunks:
                # Use average of top matches
                semantic_score = sum(s for _, s in semantic_chunks) / len(semantic_chunks)

        # === Consensus scoring ===
        structural_chunk_ids = set(self._get_chunk_id(c) for c in structural_chunks)
        semantic_chunk_ids = set(self._get_chunk_id(c) for c, _ in semantic_chunks)

        # Check agreement
        overlap_ids = structural_chunk_ids & semantic_chunk_ids
        agreement_bonus = 0.0
        signals_disagree = False

        if structural_chunk_ids and semantic_chunk_ids:
            if overlap_ids:
                # Signals agree - bonus
                overlap_ratio = len(overlap_ids) / max(len(structural_chunk_ids), len(semantic_chunk_ids))
                agreement_bonus = self.AGREEMENT_BONUS * overlap_ratio
            elif abs(structural_score - semantic_score) > self.DISAGREEMENT_THRESHOLD:
                # Signals disagree significantly
                signals_disagree = True

        # Determine final chunks and link type
        final_chunk_ids: List[str] = []
        link_type = "none"

        if structural_score >= self.STRUCTURAL_THRESHOLD and semantic_score >= self.SEMANTIC_THRESHOLD:
            if overlap_ids:
                link_type = "consensus"
                final_chunk_ids = list(structural_chunk_ids | semantic_chunk_ids)
            else:
                link_type = "consensus"  # Both found matches, even if different
                final_chunk_ids = list(structural_chunk_ids | semantic_chunk_ids)
        elif structural_score >= self.STRUCTURAL_THRESHOLD:
            link_type = "structural_only"
            final_chunk_ids = list(structural_chunk_ids)
        elif semantic_score >= self.SEMANTIC_THRESHOLD:
            link_type = "semantic_only"
            final_chunk_ids = list(semantic_chunk_ids)

        if not final_chunk_ids:
            return None

        # Calculate final confidence
        confidence = (
            self.STRUCTURAL_WEIGHT * structural_score +
            self.SEMANTIC_WEIGHT * semantic_score +
            agreement_bonus
        )

        # Penalty for disagreement
        if signals_disagree:
            confidence *= 0.8

        # Get chunk details for additional validation
        matched_chunks = [c for c in transcript_chunks if self._get_chunk_id(c) in final_chunk_ids]

        # Detect edge cases
        is_consent = "consent" in normalize_agenda_item(agenda_item).lower() if agenda_item else False
        is_out_of_order = False
        is_revisited = False
        is_multi_item = False

        for chunk in matched_chunks:
            text = chunk.get("text", "")
            edge_case = self.edge_handler.detect_edge_case(text)
            if edge_case:
                if edge_case["type"] == "out_of_order":
                    is_out_of_order = True
                elif edge_case["type"] == "revisit":
                    is_revisited = True
                elif edge_case["type"] == "multi_item":
                    is_multi_item = True
                elif edge_case["type"] == "consent_calendar":
                    is_consent = True

        # Calculate secondary validation scores
        title_overlap = self._calculate_title_overlap(title, matched_chunks)
        timing_score = self._calculate_timing_score(matched_chunks)
        speaker_score = self._calculate_speaker_score(matched_chunks)

        return ReconciliationLink(
            decision_id=decision_id,
            chunk_ids=final_chunk_ids,
            confidence=min(confidence, 1.0),
            link_type=link_type,
            structural_score=structural_score,
            semantic_score=semantic_score,
            agreement_bonus=agreement_bonus,
            title_overlap_score=title_overlap,
            timing_score=timing_score,
            speaker_role_score=speaker_score,
            is_out_of_order=is_out_of_order,
            is_revisited=is_revisited,
            is_multi_item=is_multi_item,
            is_consent_calendar=is_consent,
            signals_disagree=signals_disagree,
            meeting_date=meeting_date,
            agenda_item=agenda_item,
            decision_title=title[:100] if title else "",
            transcript_text_preview=matched_chunks[0].get("text", "")[:200] if matched_chunks else "",
        )

    def _build_structural_index(
        self,
        chunks: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict]]:
        """Build index of chunks by normalized agenda_item."""
        index: Dict[str, List[Dict]] = {}
        for chunk in chunks:
            agenda_item = chunk.get("agenda_item") or chunk.get("metadata", {}).get("agenda_item")
            if agenda_item:
                normalized = normalize_agenda_item(agenda_item)
                if normalized not in index:
                    index[normalized] = []
                index[normalized].append(chunk)
        return index

    def _semantic_search(
        self,
        query_text: str,
        meeting_date: str,
        top_k: int,
    ) -> List[Tuple[Dict, float]]:
        """
        Search for semantically similar transcript chunks.

        Returns:
            List of (chunk_dict, similarity_score) tuples
        """
        if not self.embeddings_client:
            return []

        try:
            # Use the embeddings client to search transcripts
            results = self.embeddings_client.search_transcripts(
                query=query_text,
                top_k=top_k * 2,  # Get more, filter by date
                where={"meeting_date": meeting_date} if meeting_date else None,
            )

            # Convert SearchResult objects to (dict, score) tuples
            return [
                (
                    {"id": r.document_id, "text": r.text, **r.metadata},
                    r.score
                )
                for r in results[:top_k]
            ]
        except Exception as e:
            logger.debug(f"Semantic search failed: {e}")
            return []

    def _load_transcript_chunks(self, meeting_date: str) -> List[Dict[str, Any]]:
        """Load transcript chunks for a meeting from ChromaDB."""
        if not self.embeddings_client:
            return []

        try:
            collection = self.embeddings_client._client.get_collection(
                self.embeddings_client.transcripts_collection_name
            )
            results = collection.get(
                where={"meeting_date": meeting_date},
                include=["documents", "metadatas"],
            )

            chunks = []
            if results and results.get("ids"):
                for i, chunk_id in enumerate(results["ids"]):
                    chunk = {"id": chunk_id}
                    if results.get("documents"):
                        chunk["text"] = results["documents"][i]
                    if results.get("metadatas"):
                        chunk.update(results["metadatas"][i])
                    chunks.append(chunk)

            return chunks
        except Exception as e:
            logger.debug(f"Failed to load transcript chunks: {e}")
            return []

    def _get_chunk_id(self, chunk: Dict) -> str:
        """Get or generate chunk ID."""
        return chunk.get("id") or f"chunk-{chunk.get('chunk_index', 0)}"

    def _calculate_title_overlap(self, title: str, chunks: List[Dict]) -> float:
        """Calculate keyword overlap between decision title and transcript."""
        if not title or not chunks:
            return 0.0

        stopwords = {"the", "and", "for", "with", "this", "that", "from", "will", "have", "been", "city", "council"}
        title_words = set(
            w.lower() for w in re.findall(r'\w+', title)
            if len(w) > 3 and w.lower() not in stopwords
        )

        if not title_words:
            return 0.5

        transcript_text = " ".join(c.get("text", "") for c in chunks).lower()
        matches = sum(1 for w in title_words if w in transcript_text)
        return matches / len(title_words)

    def _calculate_timing_score(self, chunks: List[Dict]) -> float:
        """Calculate timing consistency score."""
        if not chunks:
            return 0.0
        has_timestamps = any(c.get("start_ms") for c in chunks)
        return 0.7 if has_timestamps else 0.5

    def _calculate_speaker_score(self, chunks: List[Dict]) -> float:
        """Calculate speaker role consistency score."""
        if not chunks:
            return 0.0

        staff_present = any(c.get("speaker_role", "").lower() == "staff" for c in chunks)
        council_present = any(c.get("speaker_role", "").lower() == "council" for c in chunks)
        public_present = any(c.get("speaker_role", "").lower() == "public" for c in chunks)

        if staff_present or council_present:
            return 0.8
        elif public_present:
            return 0.6
        return 0.5

    def reconcile_all(
        self,
        decisions_path: Union[str, Path],
        meeting_dates: Optional[List[str]] = None,
    ) -> BatchReconciliationResult:
        """
        Reconcile all meetings from a decisions file.

        Args:
            decisions_path: Path to decisions JSON file
            meeting_dates: Optional list of specific dates to process

        Returns:
            BatchReconciliationResult
        """
        with open(decisions_path) as f:
            all_decisions = json.load(f)

        # Group by meeting date
        decisions_by_date: Dict[str, List[Dict]] = {}
        for decision in all_decisions:
            date = decision.get("meeting_date", "")
            if date:
                if date not in decisions_by_date:
                    decisions_by_date[date] = []
                decisions_by_date[date].append(decision)

        if meeting_dates:
            decisions_by_date = {d: decisions_by_date[d] for d in meeting_dates if d in decisions_by_date}

        batch_result = BatchReconciliationResult(jurisdiction_id=self.jurisdiction_id)

        for meeting_date, decisions in decisions_by_date.items():
            result = self.reconcile_meeting(meeting_date, decisions)
            batch_result.meeting_results.append(result)

        batch_result.compute_aggregates()
        return batch_result


# =============================================================================
# Utility Functions
# =============================================================================

def reconcile_jurisdiction(
    jurisdiction_id: str,
    decisions_path: Union[str, Path],
    embeddings_client,
    meeting_dates: Optional[List[str]] = None,
) -> BatchReconciliationResult:
    """
    Convenience function to reconcile an entire jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction identifier
        decisions_path: Path to decisions JSON
        embeddings_client: CivicEmbeddings instance
        meeting_dates: Optional specific dates to process

    Returns:
        BatchReconciliationResult
    """
    reconciler = DecisionTranscriptReconciler(
        jurisdiction_id=jurisdiction_id,
        embeddings_client=embeddings_client,
    )

    return reconciler.reconcile_all(
        decisions_path=decisions_path,
        meeting_dates=meeting_dates,
    )
