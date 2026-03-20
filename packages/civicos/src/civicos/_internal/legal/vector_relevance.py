"""
Vector+LLM relevance pipeline for federal rules.

3-stage pipeline that replaces heuristic-only scoring:
1. Policy query vectors — averaged from municipal_code embeddings per policy area
2. Vector candidate retrieval — pgvector cosine similarity narrows rules to candidates
3. LLM confirmation — gpt-4o-mini scores candidates with local impact summary

Designed to run:
- Full backfill: score all existing rules (~$0.05 for ~300 candidates)
- Incremental: score newly ingested rules after embedding
"""

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Policy areas with description keywords for bootstrapping from municipal_code embeddings.
# Each key is a policy area; value is a list of keywords to match against
# municipal_code content for building representative query vectors.
POLICY_AREAS: dict[str, list[str]] = {
    "housing": ["housing", "residential", "dwelling", "tenant", "rent", "affordable"],
    "zoning": ["zoning", "land use", "setback", "density", "parcel", "lot"],
    "transportation": ["transportation", "traffic", "parking", "bicycle", "pedestrian", "transit"],
    "water": ["water", "stormwater", "sewer", "drainage", "flood", "watershed"],
    "environment": ["environment", "conservation", "tree", "habitat", "pollution", "emissions"],
    "climate": ["climate", "sustainability", "energy", "solar", "greenhouse", "carbon"],
    "public_safety": ["fire", "police", "emergency", "hazard", "safety", "alarm"],
    "infrastructure": ["infrastructure", "utility", "road", "bridge", "construction", "building"],
    "health": ["health", "sanitation", "food", "nuisance", "noise"],
    "budget": ["budget", "fee", "tax", "assessment", "revenue", "appropriation"],
    "labor": ["employment", "wage", "worker", "contractor", "license"],
    "education": ["school", "education", "youth", "library"],
}

# Minimum similarity threshold for candidate retrieval
CANDIDATE_SIMILARITY_THRESHOLD = 0.45

# Number of candidates per policy area
CANDIDATES_PER_POLICY = 40

# LLM batch size for confirmation
LLM_BATCH_SIZE = 25


def build_policy_vectors(
    pgvector_backend,
    jurisdiction_id: str = "city-san-rafael",
) -> dict[str, Any]:
    """Stage 1: Build policy query vectors from municipal_code embeddings.

    For each policy area, searches municipal_code embeddings for relevant sections
    and averages their embeddings to create a representative query vector.

    Args:
        pgvector_backend: PgVectorBackend instance with connection pool
        jurisdiction_id: Jurisdiction to source municipal_code from

    Returns:
        Dict mapping policy area name to numpy array (768-dim embedding)
    """
    import numpy as np

    conn = pgvector_backend._get_connection()
    cursor = conn.cursor()

    table = pgvector_backend.TABLE_NAME
    model = pgvector_backend._embedding_model
    # Also match normalized model name for compatibility
    normalized = model.split("/")[-1] if "/" in model else model

    policy_vectors = {}

    for area, keywords in POLICY_AREAS.items():
        # Build parameterized ILIKE conditions
        keyword_conditions = " OR ".join(
            "content ILIKE %s" for _ in keywords
        )
        keyword_params = [f"%{kw}%" for kw in keywords]

        sql = f"""
            SELECT embedding
            FROM {table}
            WHERE jurisdiction_id = %s
              AND corpus_type = 'municipal_code'
              AND (embedding_model = %s OR embedding_model = %s OR embedding_model = 'unknown')
              AND ({keyword_conditions})
            LIMIT 50
        """
        cursor.execute(sql, (jurisdiction_id, model, normalized, *keyword_params))
        rows = cursor.fetchall()

        if not rows:
            logger.warning(f"No municipal_code embeddings found for policy area: {area}")
            continue

        # Parse embeddings (pgvector returns strings like "[1.0,2.0,...]")
        def _parse_embedding(val):
            if isinstance(val, str):
                return np.fromstring(val.strip("[]"), sep=",")
            return np.array(val)

        embeddings = np.array([_parse_embedding(row[0]) for row in rows])
        centroid = embeddings.mean(axis=0)

        # Normalize to unit vector for cosine similarity
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        policy_vectors[area] = centroid
        logger.info(f"  Policy vector '{area}': averaged {len(rows)} municipal_code embeddings")

    pgvector_backend._return_connection(conn)
    logger.info(f"Built {len(policy_vectors)} policy vectors from {jurisdiction_id} municipal_code")
    return policy_vectors


def retrieve_candidates(
    pgvector_backend,
    policy_vectors: dict[str, Any],
    jurisdiction_id: str = "federal-US",
    similarity_threshold: float = CANDIDATE_SIMILARITY_THRESHOLD,
    per_policy_limit: int = CANDIDATES_PER_POLICY,
) -> dict[str, dict[str, Any]]:
    """Stage 2: Retrieve candidate federal rules via vector similarity.

    For each policy vector, searches federal_rules embeddings and collects
    candidates above the similarity threshold. Deduplicates across policy areas,
    keeping the highest similarity and all matching policy areas.

    Args:
        pgvector_backend: PgVectorBackend instance
        policy_vectors: Output of build_policy_vectors()
        jurisdiction_id: Jurisdiction of federal rules embeddings
        similarity_threshold: Minimum cosine similarity to include
        per_policy_limit: Max candidates per policy area

    Returns:
        Dict keyed by document_number with:
            similarity: best similarity score
            policy_areas: list of matching policy areas
            content: embedded text content
    """
    conn = pgvector_backend._get_connection()
    cursor = conn.cursor()

    table = pgvector_backend.TABLE_NAME
    model = pgvector_backend._embedding_model
    normalized = model.split("/")[-1] if "/" in model else model

    candidates: dict[str, dict[str, Any]] = {}

    for area, query_vector in policy_vectors.items():
        sql = f"""
            SELECT
                id,
                content,
                metadata,
                1 - (embedding <=> %s::vector) as similarity
            FROM {table}
            WHERE jurisdiction_id = %s
              AND corpus_type = 'federal_rules'
              AND (embedding_model = %s OR embedding_model = %s OR embedding_model = 'unknown')
              AND (1 - (embedding <=> %s::vector)) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = [
            query_vector.tolist(), jurisdiction_id, model, normalized,
            query_vector.tolist(), similarity_threshold,
            query_vector.tolist(), per_policy_limit,
        ]
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        area_count = 0
        for row in rows:
            doc_id, content, metadata_raw, similarity = row

            # Parse metadata to extract document_number
            if isinstance(metadata_raw, dict):
                metadata = metadata_raw
            elif metadata_raw:
                metadata = json.loads(metadata_raw)
            else:
                metadata = {}

            # Extract document_number from metadata or ID
            doc_num = metadata.get("document_number") or metadata.get("doc_number")
            if not doc_num:
                # ID format is typically "rule-{document_number}"
                if doc_id and doc_id.startswith("rule-"):
                    doc_num = doc_id[5:]
                else:
                    doc_num = doc_id

            if not doc_num:
                continue

            if doc_num in candidates:
                # Update if higher similarity
                if similarity > candidates[doc_num]["similarity"]:
                    candidates[doc_num]["similarity"] = float(similarity)
                if area not in candidates[doc_num]["policy_areas"]:
                    candidates[doc_num]["policy_areas"].append(area)
            else:
                candidates[doc_num] = {
                    "document_number": doc_num,
                    "similarity": float(similarity),
                    "policy_areas": [area],
                    "content": content,
                }
                area_count += 1

        logger.info(f"  '{area}': {len(rows)} hits, {area_count} new candidates")

    pgvector_backend._return_connection(conn)
    logger.info(
        f"Stage 2 complete: {len(candidates)} unique candidates "
        f"from {len(policy_vectors)} policy areas "
        f"(threshold={similarity_threshold})"
    )
    return candidates


def score_candidates_with_llm(
    candidates: dict[str, dict[str, Any]],
    rules_by_docnum: dict[str, dict[str, Any]],
    jurisdiction_label: str = "San Rafael, CA (Marin County)",
    batch_size: int = LLM_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Stage 3: LLM confirmation scoring on candidates.

    Sends candidates to gpt-4o-mini in batches for relevance scoring
    and local impact summary generation.

    Args:
        candidates: Output of retrieve_candidates()
        rules_by_docnum: Dict of full rule records keyed by document_number
            (from postgres_backend.get_federal_rules())
        jurisdiction_label: Human-readable jurisdiction name for the prompt
        batch_size: Rules per LLM API call

    Returns:
        List of dicts with:
            document_number, score (0.0-1.0), summary (str), reasons (list)
    """
    import openai

    client = openai.OpenAI()
    results = []
    total_tokens = 0
    doc_nums = list(candidates.keys())

    logger.info(f"Stage 3: Scoring {len(doc_nums)} candidates with gpt-4o-mini...")

    for i in range(0, len(doc_nums), batch_size):
        batch_nums = doc_nums[i:i + batch_size]
        batch_items = []

        for doc_num in batch_nums:
            candidate = candidates[doc_num]
            rule = rules_by_docnum.get(doc_num, {})

            title = rule.get("title") or ""
            abstract = rule.get("abstract") or ""
            agencies = rule.get("agency_names") or []
            if isinstance(agencies, str):
                agencies = [agencies]

            # Truncate abstract to save tokens
            if len(abstract) > 300:
                abstract = abstract[:300] + "..."

            batch_items.append({
                "document_number": doc_num,
                "title": title,
                "abstract": abstract,
                "agencies": ", ".join(agencies) if agencies else "Unknown",
                "policy_areas": candidate["policy_areas"],
                "vector_similarity": round(candidate["similarity"], 3),
            })

        prompt = f"""Score each federal rule's relevance to {jurisdiction_label} local government.

Consider: Does this rule affect local agencies, residents, or infrastructure?
Would local officials need to implement, comply with, or inform constituents about it?

For each rule, return:
- score: 0.0 to 1.0 (0=no local relevance, 1=directly impacts local government)
- summary: One sentence (max 50 words) explaining the specific local impact
- relevant: true if score >= 0.3, false otherwise

Return JSON: {{"results": [{{"document_number": "...", "score": 0.7, "summary": "...", "relevant": true}}]}}

Rules:
{json.dumps(batch_items, indent=2)}"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert in federal regulatory analysis for local governments. "
                            "Score federal rules by their practical impact on a specific municipality. "
                            "Be precise: a rule about ocean shipping has low relevance to an inland city, "
                            "but a rule about stormwater permits is highly relevant to any city. "
                            "Return only valid JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            usage = response.usage
            if usage:
                total_tokens += usage.total_tokens

            result_text = response.choices[0].message.content
            parsed = json.loads(result_text)
            batch_results = parsed.get("results", [])

            for item in batch_results:
                doc_num = item.get("document_number")
                if not doc_num or doc_num not in candidates:
                    continue

                score = float(item.get("score", 0))
                summary = item.get("summary", "")
                candidate = candidates[doc_num]

                # Build reasons combining vector + LLM signals
                reasons = [f"vector:{a}" for a in candidate["policy_areas"]]
                reasons.append(f"llm_score:{score:.2f}")
                reasons.append(f"sim:{candidate['similarity']:.3f}")

                results.append({
                    "document_number": doc_num,
                    "score": round(score, 3),
                    "summary": summary,
                    "reasons": reasons,
                })

            logger.info(
                f"  Batch {i // batch_size + 1}/{(len(doc_nums) + batch_size - 1) // batch_size}: "
                f"scored {len(batch_results)} rules"
            )

        except Exception as e:
            logger.error(f"  LLM batch failed at offset {i}: {e}")
            # Continue with remaining batches
            continue

    logger.info(
        f"Stage 3 complete: {len(results)} rules scored, "
        f"{total_tokens} total tokens"
    )

    return results, total_tokens


def run_vector_llm_pipeline(
    storage_backend,
    pgvector_backend,
    jurisdiction_id: str = "city-san-rafael",
    federal_jurisdiction: str = "federal-US",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the full 3-stage vector+LLM relevance pipeline.

    Args:
        storage_backend: PostgresBackend instance for reading/writing rules
        pgvector_backend: PgVectorBackend instance for vector operations
        jurisdiction_id: Source jurisdiction for policy vectors (e.g., "city-san-rafael")
        federal_jurisdiction: Jurisdiction ID for federal rules embeddings
        dry_run: If True, run stages 1-3 but don't write results

    Returns:
        Pipeline results dict with counts and costs
    """
    start_time = time.time()

    # Stage 1: Build policy vectors
    logger.info("=" * 60)
    logger.info("STAGE 1: Building policy vectors from municipal_code")
    logger.info("=" * 60)
    policy_vectors = build_policy_vectors(pgvector_backend, jurisdiction_id)

    if not policy_vectors:
        return {"error": "No policy vectors built — check municipal_code embeddings"}

    # Stage 2: Retrieve candidates
    logger.info("")
    logger.info("=" * 60)
    logger.info("STAGE 2: Retrieving candidates via vector similarity")
    logger.info("=" * 60)
    candidates = retrieve_candidates(
        pgvector_backend, policy_vectors, federal_jurisdiction,
    )

    if not candidates:
        return {"error": "No candidates found — check federal_rules embeddings"}

    # Load full rule records for LLM context
    logger.info(f"\nLoading full rule records for {len(candidates)} candidates...")
    all_rules = storage_backend.get_federal_rules(limit=10000)
    rules_by_docnum = {r["document_number"]: r for r in all_rules}

    # Stage 3: LLM scoring
    logger.info("")
    logger.info("=" * 60)
    logger.info("STAGE 3: LLM confirmation scoring")
    logger.info("=" * 60)
    scored_results, total_tokens = score_candidates_with_llm(
        candidates, rules_by_docnum,
    )

    # Write results
    updates_written = 0
    if scored_results and not dry_run:
        logger.info(f"\nWriting {len(scored_results)} relevance scores to database...")
        updates = []
        for result in scored_results:
            updates.append({
                "document_number": result["document_number"],
                "local_relevance_score": result["score"],
                "relevance_reasons": result["reasons"],
                "local_relevance_summary": result["summary"],
            })
        updates_written = storage_backend.update_federal_rules_relevance(updates)
        logger.info(f"Updated {updates_written} federal rules")
    elif dry_run:
        logger.info(f"\nDry run — would update {len(scored_results)} rules")
        # Show top 10 for review
        sorted_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)
        logger.info("\nTop 10 by LLM score:")
        for r in sorted_results[:10]:
            rule = rules_by_docnum.get(r["document_number"], {})
            title = (rule.get("title") or "")[:80]
            logger.info(f"  {r['score']:.2f} | {r['document_number']} | {title}")
            if r.get("summary"):
                logger.info(f"         {r['summary']}")

    elapsed = time.time() - start_time

    # Cost tracking
    try:
        from civicos_services.core.cost_tracking import log_llm_cost
        log_llm_cost(
            model="gpt-4o-mini",
            usage={"total_tokens": total_tokens},
            task="vector_llm_relevance",
            jurisdiction_id=federal_jurisdiction,
            metadata={
                "candidates": len(candidates),
                "scored": len(scored_results),
                "policy_areas": len(policy_vectors),
            },
        )
    except Exception:
        logger.debug("Cost tracking unavailable — skipping")

    result = {
        "task": "vector_llm_relevance_pipeline",
        "policy_areas": len(policy_vectors),
        "candidates_retrieved": len(candidates),
        "candidates_scored": len(scored_results),
        "updates_written": updates_written,
        "total_tokens": total_tokens,
        "elapsed_seconds": round(elapsed, 1),
        "dry_run": dry_run,
    }

    logger.info(f"\nPipeline complete: {json.dumps(result, indent=2)}")
    return result
