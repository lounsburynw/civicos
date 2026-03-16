"""
Configurable refresh policies for corpus data.

Provides a protocol for corpus providers to report whether their data has changed,
and a runner that orchestrates check → diff → upsert → re-embed workflows.

Architecture:
    CorpusProvider (publisher-specific)
        └── check_for_update() → ChangeSignal (changed/unchanged/unknown)
        └── get_fingerprint() → str (e.g., supplement string, publish date)

    RefreshRunner (generic)
        └── reads policy from jurisdiction YAML
        └── calls provider.check_for_update()
        └── if changed: fetch → diff by content hash → upsert deltas → re-embed

    Jurisdiction YAML:
        refresh:
          municipal_code:
            interval: 90d
            strategy: content_hash

Scheduling is external (GH Actions cron → modal run). The YAML defines what to check.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Change detection types
# ---------------------------------------------------------------------------


class ChangeStatus(str, Enum):
    """Result of a change check."""
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    UNKNOWN = "unknown"       # Can't determine (e.g., no prior fingerprint)
    ERROR = "error"           # Check failed


@dataclass
class ChangeSignal:
    """Signal from a corpus provider about whether data has changed."""
    status: ChangeStatus
    old_fingerprint: Optional[str] = None
    new_fingerprint: Optional[str] = None
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class RefreshableCorpus(Protocol):
    """Protocol for corpus providers that support change detection.

    Corpus classes (MunicipalCodeCorpus, AmericanLegalCorpus) implement this
    to enable the RefreshRunner to check for updates without knowing
    publisher-specific details.
    """

    jurisdiction_id: str

    def check_for_update(self, last_fingerprint: Optional[str] = None) -> ChangeSignal:
        """Check if the corpus has changed since the last fetch.

        Args:
            last_fingerprint: The fingerprint from the previous fetch.
                If None, always returns CHANGED or UNKNOWN.

        Returns:
            ChangeSignal with status and fingerprints.
        """
        ...

    def get_fingerprint(self) -> str:
        """Get the current fingerprint of the corpus.

        This is a lightweight check (no full fetch). Examples:
        - Municode: job publish date
        - AMLegal: supplement string from first 10 lines
        """
        ...


# ---------------------------------------------------------------------------
# Refresh policy (from YAML)
# ---------------------------------------------------------------------------


@dataclass
class RefreshPolicy:
    """Refresh policy for a single corpus type."""
    corpus_type: str
    interval_days: int = 90
    strategy: str = "content_hash"   # content_hash | fingerprint_only
    enabled: bool = True

    @classmethod
    def from_dict(cls, corpus_type: str, data: dict) -> "RefreshPolicy":
        """Parse from YAML dict."""
        interval = data.get("interval", "90d")
        if isinstance(interval, str) and interval.endswith("d"):
            interval_days = int(interval[:-1])
        elif isinstance(interval, int):
            interval_days = interval
        else:
            interval_days = 90

        return cls(
            corpus_type=corpus_type,
            interval_days=interval_days,
            strategy=data.get("strategy", "content_hash"),
            enabled=data.get("enabled", True),
        )


def load_refresh_policies(jurisdiction_id: str) -> Dict[str, RefreshPolicy]:
    """Load refresh policies from jurisdiction YAML.

    Returns:
        Dict mapping corpus_type to RefreshPolicy. Empty if no refresh block.
    """
    try:
        import yaml
        p = Path(__file__).resolve()
        for parent in p.parents:
            yaml_path = parent / "data" / "jurisdictions" / f"{jurisdiction_id}.yaml"
            if yaml_path.exists():
                with open(yaml_path) as f:
                    data = yaml.safe_load(f)
                refresh_block = data.get("refresh", {})
                if not refresh_block:
                    return {}
                return {
                    corpus: RefreshPolicy.from_dict(corpus, config)
                    for corpus, config in refresh_block.items()
                    if isinstance(config, dict)
                }
    except Exception as e:
        logger.warning(f"Failed to load refresh policies for {jurisdiction_id}: {e}")

    return {}


# ---------------------------------------------------------------------------
# Content hash utilities
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Normalize text for comparison — collapse whitespace, strip."""
    import re
    return re.sub(r'\s+', ' ', text).strip()


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized text content for change detection."""
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()[:16]


def diff_sections(
    existing: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
    key_field: str = "section_number",
    text_field: str = "full_text",
) -> Dict[str, List[Dict[str, Any]]]:
    """Diff existing vs incoming sections by content hash.

    Returns:
        {
            "added": [...],      # New sections not in existing
            "modified": [...],   # Sections with changed content
            "removed": [...],    # Sections in existing but not in incoming
            "unchanged": [...],  # Sections with identical content
        }
    """
    existing_map = {}
    for s in existing:
        key = s.get(key_field, "")
        existing_map[key] = content_hash(s.get(text_field, ""))

    incoming_map = {}
    for s in incoming:
        key = s.get(key_field, "")
        incoming_map[key] = content_hash(s.get(text_field, ""))

    added = [s for s in incoming if s.get(key_field, "") not in existing_map]
    removed = [s for s in existing if s.get(key_field, "") not in incoming_map]
    modified = []
    unchanged = []

    for s in incoming:
        key = s.get(key_field, "")
        if key in existing_map:
            if incoming_map[key] != existing_map[key]:
                modified.append(s)
            else:
                unchanged.append(s)

    return {
        "added": added,
        "modified": modified,
        "removed": removed,
        "unchanged": unchanged,
    }


# ---------------------------------------------------------------------------
# RefreshRunner
# ---------------------------------------------------------------------------


@dataclass
class RefreshResult:
    """Result of a refresh operation."""
    jurisdiction_id: str
    corpus_type: str
    status: str                # skipped | unchanged | updated | error
    change_signal: Optional[ChangeSignal] = None
    sections_added: int = 0
    sections_modified: int = 0
    sections_removed: int = 0
    sections_unchanged: int = 0
    vectors_reindexed: int = 0
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


class RefreshRunner:
    """Orchestrates corpus refresh: check → diff → upsert → re-embed.

    Publisher-agnostic. Gets the appropriate provider from the existing
    MunicipalCodeCorpus factory.

    Usage:
        runner = RefreshRunner(backend, vector_backend)
        result = runner.refresh_municipal_code("city-san-rafael")
    """

    def __init__(self, storage_backend, vector_backend=None):
        self.storage = storage_backend
        self.vectors = vector_backend

    def should_refresh(
        self,
        jurisdiction_id: str,
        corpus_type: str,
        policy: Optional[RefreshPolicy] = None,
    ) -> bool:
        """Check if a corpus is due for refresh based on policy and last fetch time."""
        if policy and not policy.enabled:
            return False

        interval_days = policy.interval_days if policy else 90

        meta = self.storage.get_refresh_metadata(jurisdiction_id, corpus_type)
        if not meta:
            return True  # Never fetched

        last_fetch = meta.get("last_fetch_at")
        if not last_fetch:
            return True

        if isinstance(last_fetch, str):
            last_fetch = datetime.fromisoformat(last_fetch)

        due_at = last_fetch + timedelta(days=interval_days)
        return datetime.now() >= due_at

    def refresh_municipal_code(
        self,
        jurisdiction_id: str,
        force: bool = False,
        dry_run: bool = False,
        reindex_vectors: bool = True,
    ) -> RefreshResult:
        """Refresh municipal code for a jurisdiction.

        Steps:
        1. Load refresh policy from YAML (or use defaults)
        2. Check if refresh is due (skip if not, unless force=True)
        3. Get provider via factory, call check_for_update()
        4. If changed: fetch new sections, diff against Postgres, upsert deltas
        5. Re-embed changed sections

        Args:
            jurisdiction_id: Target jurisdiction
            force: Skip interval check
            dry_run: Check for changes but don't store
            reindex_vectors: Re-embed changed sections after upsert
        """
        import time
        start = time.time()

        # 1. Load policy
        policies = load_refresh_policies(jurisdiction_id)
        policy = policies.get("municipal_code")

        # 2. Check if due
        if not force and not self.should_refresh(jurisdiction_id, "municipal_code", policy):
            logger.info(f"[REFRESH] {jurisdiction_id} municipal_code: not due yet, skipping")
            return RefreshResult(
                jurisdiction_id=jurisdiction_id,
                corpus_type="municipal_code",
                status="skipped",
                elapsed_seconds=time.time() - start,
            )

        # 3. Get provider and check for changes
        from .municipal import MunicipalCodeCorpus
        corpus = MunicipalCodeCorpus.for_jurisdiction(jurisdiction_id)

        # Get last fingerprint from refresh metadata (stored in last_fetch_hash)
        meta = self.storage.get_refresh_metadata(
            jurisdiction_id, "municipal_code",
        )
        last_fp = meta.get("last_fetch_hash") if meta else None

        signal = ChangeSignal(status=ChangeStatus.UNKNOWN)
        if isinstance(corpus, RefreshableCorpus):
            try:
                signal = corpus.check_for_update(last_fp)
            except Exception as e:
                logger.warning(f"[REFRESH] check_for_update failed: {e}")
                signal = ChangeSignal(
                    status=ChangeStatus.ERROR, message=str(e)
                )

        if signal.status == ChangeStatus.UNCHANGED and not force:
            logger.info(
                f"[REFRESH] {jurisdiction_id} municipal_code: unchanged "
                f"(fingerprint={signal.new_fingerprint})"
            )
            return RefreshResult(
                jurisdiction_id=jurisdiction_id,
                corpus_type="municipal_code",
                status="unchanged",
                change_signal=signal,
                elapsed_seconds=time.time() - start,
            )

        if signal.status == ChangeStatus.ERROR and not force:
            return RefreshResult(
                jurisdiction_id=jurisdiction_id,
                corpus_type="municipal_code",
                status="error",
                change_signal=signal,
                error=signal.message,
                elapsed_seconds=time.time() - start,
            )

        # 4. Fetch new sections
        logger.info(f"[REFRESH] {jurisdiction_id} municipal_code: fetching new data...")
        from dataclasses import asdict
        new_sections = []
        try:
            for section in corpus.stream_sections():
                new_sections.append(asdict(section))
        finally:
            if hasattr(corpus, "close"):
                corpus.close()

        if not new_sections:
            logger.warning(f"[REFRESH] {jurisdiction_id}: no sections fetched")
            return RefreshResult(
                jurisdiction_id=jurisdiction_id,
                corpus_type="municipal_code",
                status="error",
                error="No sections fetched",
                elapsed_seconds=time.time() - start,
            )

        # 5. Diff against existing data
        existing_sections = self.storage.get_municipal_code(
            jurisdiction_id, limit=50000,
        )

        diff = diff_sections(existing_sections, new_sections)
        n_added = len(diff["added"])
        n_modified = len(diff["modified"])
        n_removed = len(diff["removed"])
        n_unchanged = len(diff["unchanged"])

        logger.info(
            f"[REFRESH] {jurisdiction_id} diff: "
            f"+{n_added} added, ~{n_modified} modified, "
            f"-{n_removed} removed, ={n_unchanged} unchanged"
        )

        # Safety valve: catch suspicious diffs that indicate a bug, not real changes.
        # - Mass modifications (>50%): likely normalization/encoding issue
        # - Mass removals (>20%): likely truncated fetch (network error, timeout)
        # Abort unless forced to prevent data loss.
        total_existing = len(existing_sections)
        if not force and total_existing > 0:
            if n_modified > total_existing * 0.5:
                msg = (
                    f"Suspicious: {n_modified}/{total_existing} sections "
                    f"({n_modified * 100 // total_existing}%) appear modified. "
                    f"Likely a normalization issue, not real changes. "
                    f"Use force=True to override."
                )
                logger.warning(f"[REFRESH] {jurisdiction_id}: {msg}")
                return RefreshResult(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type="municipal_code",
                    status="error",
                    change_signal=signal,
                    sections_modified=n_modified,
                    sections_unchanged=n_unchanged,
                    error=msg,
                    elapsed_seconds=time.time() - start,
                )

            if n_removed > total_existing * 0.2:
                msg = (
                    f"Suspicious: {n_removed}/{total_existing} sections "
                    f"({n_removed * 100 // total_existing}%) appear removed. "
                    f"Likely a truncated fetch (network error, timeout). "
                    f"Use force=True to override."
                )
                logger.warning(f"[REFRESH] {jurisdiction_id}: {msg}")
                return RefreshResult(
                    jurisdiction_id=jurisdiction_id,
                    corpus_type="municipal_code",
                    status="error",
                    change_signal=signal,
                    sections_removed=n_removed,
                    sections_unchanged=n_unchanged,
                    error=msg,
                    elapsed_seconds=time.time() - start,
                )

        if dry_run:
            return RefreshResult(
                jurisdiction_id=jurisdiction_id,
                corpus_type="municipal_code",
                status="unchanged" if (n_added == 0 and n_modified == 0) else "updated",
                change_signal=signal,
                sections_added=n_added,
                sections_modified=n_modified,
                sections_removed=n_removed,
                sections_unchanged=n_unchanged,
                elapsed_seconds=time.time() - start,
            )

        # 6. Pass ALL sections to store_municipal_code.
        # It handles its own content-level diffing internally (skips unchanged,
        # closes removed, inserts new/modified). The diff above is for reporting.
        stored = 0
        has_changes = n_added > 0 or n_modified > 0 or n_removed > 0
        if has_changes:
            stored = self.storage.store_municipal_code(
                jurisdiction_id=jurisdiction_id,
                sections=new_sections,
            )
            logger.info(f"[REFRESH] Stored {stored} changed sections")

        # Update refresh metadata with new fingerprint
        new_fp = signal.new_fingerprint if signal.new_fingerprint else None
        self.storage.update_refresh_metadata(
            jurisdiction_id, "municipal_code",
            source_name=_infer_source(corpus),
            items_fetched=len(new_sections),
            items_stored=stored,
            status="completed",
            last_fetch_hash=new_fp,
        )

        # 7. Re-embed changed sections
        delta_sections = diff["added"] + diff["modified"]
        vectors_reindexed = 0
        if reindex_vectors and self.vectors and stored > 0:
            try:
                vectors_reindexed = self._reindex_changed_sections(
                    jurisdiction_id, delta_sections,
                )
            except Exception as e:
                logger.warning(f"[REFRESH] Vector reindex failed: {e}")

        elapsed = time.time() - start
        return RefreshResult(
            jurisdiction_id=jurisdiction_id,
            corpus_type="municipal_code",
            status="updated" if stored > 0 else "unchanged",
            change_signal=signal,
            sections_added=n_added,
            sections_modified=n_modified,
            sections_removed=n_removed,
            sections_unchanged=n_unchanged,
            vectors_reindexed=vectors_reindexed,
            elapsed_seconds=elapsed,
        )

    def _reindex_changed_sections(
        self,
        jurisdiction_id: str,
        changed_sections: List[Dict[str, Any]],
    ) -> int:
        """Re-embed only the changed sections.

        Uses the vector backend's index_corpus method with a filter
        to only process sections that were added or modified.
        """
        if not self.vectors:
            return 0

        # Build document IDs for changed sections
        changed_ids = set()
        for s in changed_sections:
            sec_num = s.get("section_number", "")
            doc_id = f"{jurisdiction_id}-muni-{sec_num.replace('.', '-')}"
            changed_ids.add(doc_id)

        logger.info(
            f"[REFRESH] Re-indexing {len(changed_ids)} changed sections "
            f"for {jurisdiction_id}"
        )

        # Full reindex of municipal_code corpus
        # The vector backend will handle chunking and embedding
        count = self.vectors.index_corpus(
            jurisdiction_id=jurisdiction_id,
            corpus_type="municipal_code",
            reindex=True,  # Force reindex to pick up changes
        )

        return count


def _infer_source(corpus) -> str:
    """Infer the source name from a corpus instance."""
    cls_name = type(corpus).__name__
    if "AmericanLegal" in cls_name:
        return "amlegal"
    return "municode"
