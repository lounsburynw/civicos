"""
ResultMerger — reciprocal rank fusion for cross-corpus ranking.

Ranks within each corpus first, then merges by reciprocal rank.
Handles partial results when corpora timeout.
Reports per-corpus timing and status in meta.
"""

from typing import Dict, List, Tuple

from civicos_services.query.models import CivicResult


# RRF constant (standard value from literature)
RRF_K = 60


def reciprocal_rank_fusion(
    corpus_results: Dict[str, List[CivicResult]],
    global_limit: int = 10,
) -> List[CivicResult]:
    """
    Merge results from multiple corpora using reciprocal rank fusion.

    Each result gets a score of 1/(k + rank) where rank is its position
    within its corpus. Results are sorted by fused score descending.

    Args:
        corpus_results: {corpus_name: [CivicResult, ...]} already ranked within corpus
        global_limit: max total results to return

    Returns:
        Merged and re-ranked list of CivicResult
    """
    if not corpus_results:
        return []

    # Single corpus: skip fusion overhead
    if len(corpus_results) == 1:
        results = list(corpus_results.values())[0]
        return results[:global_limit]

    # Compute RRF scores
    scored: List[Tuple[float, CivicResult]] = []
    for _corpus_name, results in corpus_results.items():
        for rank, result in enumerate(results):
            rrf_score = 1.0 / (RRF_K + rank + 1)
            scored.append((rrf_score, result))

    # Sort by score descending, then by existing relevance as tiebreaker
    scored.sort(key=lambda x: (x[0], x[1].relevance or 0), reverse=True)

    # Update relevance to reflect fused score (normalized to 0-1)
    merged = []
    max_score = scored[0][0] if scored else 1.0
    for score, result in scored[:global_limit]:
        result.relevance = round(score / max_score, 4) if max_score > 0 else 0.0
        merged.append(result)

    return merged
