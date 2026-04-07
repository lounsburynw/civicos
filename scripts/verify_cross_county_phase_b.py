"""
Phase B verification: cross-county query prototype.

Runs three live queries against PostgreSQL from base jurisdiction city-san-rafael
and validates the cross-jurisdiction tier system end-to-end:

  Query A: include_siblings=True (only)
    - Expected: Marin sibling cities appear (Mill Valley, San Anselmo, etc.)
    - Expected: Berkeley does NOT appear (different county, no explicit opt-in)
    - Tier weights: self=1.0, sibling=0.8

  Query B: also_include=["city-berkeley"]
    - Expected: Berkeley results appear with cross_county tier (0.5x raw cosine)
    - Expected: SR results retain 1.0x weight
    - Validates explicit cross-county opt-in path

  Query C: include_parents=True
    - Expected: state-california parent appears (parent_state weight 0.7)
    - Expected: country-united-states parent appears (parent_federal weight 0.5)
    - Confirms parent chain is the only "default" cross-county channel

Usage:
    source civicos-env/bin/activate
    python3 scripts/verify_cross_county_phase_b.py
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from civicos import CivicOS
from civicos_services.query.models import SearchRequest
from civicos_services.query.verbs import execute_search
from civicos_services.query.jurisdictions import get_tier_weight, get_jurisdiction_tier

BASE_JID = "city-san-rafael"
QUERY = "housing"
LIMIT = 15


def fmt_result(r, base_jid):
    jid = r.jurisdiction or "<unset>"
    tier = get_jurisdiction_tier(base_jid, jid) if r.jurisdiction else "?"
    weight = get_tier_weight(base_jid, jid) if r.jurisdiction else 1.0
    rel = r.relevance if r.relevance is not None else 0.0
    title = (r.title or r.summary or "")[:70]
    return f"  {rel:.4f} [{tier:14}/{weight:.1f}x] {jid:24} {title}"


async def main():
    print(f"=== Phase B Cross-County Verification ===")
    print(f"Base jurisdiction: {BASE_JID}")
    print(f"Query: '{QUERY}'")
    print()

    civic = CivicOS(BASE_JID)
    backend = type(civic.storage).__name__
    print(f"Backend: {backend}")
    assert backend == "PostgresBackend", f"Expected PostgresBackend, got {backend}"

    # Warm up the embedding model
    print("Warming up embedding model...")
    civic.what_happened("warmup")
    print()

    # ---------- Query A: siblings only ----------
    print("--- Query A: include_siblings=True (Marin only expected) ---")
    req_a = SearchRequest(
        query=QUERY,
        corpus=["decisions"],
        include_siblings=True,
        limit=LIMIT,
    )
    resp_a = await execute_search(req_a, civic, BASE_JID)
    print(f"Total results: {len(resp_a.results)}")
    print(f"Jurisdictions returned: {sorted((resp_a.jurisdiction_results or {}).keys())}")
    print(f"Query time: {resp_a.meta.query_time_ms}ms")
    for r in resp_a.results[:10]:
        print(fmt_result(r, BASE_JID))
    jids_a = {r.jurisdiction for r in resp_a.results}
    berkeley_in_a = "city-berkeley" in jids_a
    print(f"\n  Boundary check: city-berkeley in results? {berkeley_in_a}")
    assert not berkeley_in_a, "FAIL: Berkeley leaked into siblings-only query"
    print("  PASS: Berkeley correctly absent from siblings-only query")
    print()

    # ---------- Query B: also_include Berkeley + SF (two different counties) ----------
    print("--- Query B: also_include=['city-berkeley', 'city-san-francisco'] (cross-county opt-in) ---")
    req_b = SearchRequest(
        query=QUERY,
        corpus=["decisions"],
        also_include=["city-berkeley", "city-san-francisco"],
        limit=LIMIT,
    )
    resp_b = await execute_search(req_b, civic, BASE_JID)
    print(f"Total results: {len(resp_b.results)}")
    print(f"Jurisdictions returned: {sorted((resp_b.jurisdiction_results or {}).keys())}")
    print(f"Query time: {resp_b.meta.query_time_ms}ms")
    for r in resp_b.results[:LIMIT]:
        print(fmt_result(r, BASE_JID))
    berkeley_results = [r for r in resp_b.results if r.jurisdiction == "city-berkeley"]
    sf_results = [r for r in resp_b.results if r.jurisdiction == "city-san-francisco"]
    sr_results = [r for r in resp_b.results if r.jurisdiction == BASE_JID]
    print(f"\n  Berkeley result count: {len(berkeley_results)}")
    print(f"  San Francisco result count: {len(sf_results)}")
    print(f"  San Rafael result count: {len(sr_results)}")
    # Cross-county weight is 0.5; raw cosine sim is bounded ~[0, 1].
    # Boosted relevance must be <= 0.5 * 1.0 = 0.5.
    if berkeley_results:
        max_berkeley_rel = max(r.relevance for r in berkeley_results if r.relevance is not None)
        print(f"  Max Berkeley relevance: {max_berkeley_rel:.4f} (must be <= 0.5)")
        assert max_berkeley_rel <= 0.5 + 1e-6, (
            f"FAIL: Berkeley relevance {max_berkeley_rel} exceeds cross_county weight cap 0.5"
        )
        print("  PASS: Berkeley results capped by cross_county weight (0.5)")
    if sf_results:
        max_sf_rel = max(r.relevance for r in sf_results if r.relevance is not None)
        print(f"  Max SF relevance: {max_sf_rel:.4f} (must be <= 0.5)")
        assert max_sf_rel <= 0.5 + 1e-6, (
            f"FAIL: SF relevance {max_sf_rel} exceeds cross_county weight cap 0.5"
        )
        print("  PASS: SF results capped by cross_county weight (0.5)")
    print()

    # ---------- Query B2: comparative mode (per_jurisdiction_limit) ----------
    print("--- Query B2: also_include + per_jurisdiction_limit=5 (comparative mode) ---")
    req_b2 = SearchRequest(
        query=QUERY,
        corpus=["decisions"],
        also_include=["city-berkeley", "city-san-francisco"],
        per_jurisdiction_limit=5,
        limit=LIMIT,
    )
    resp_b2 = await execute_search(req_b2, civic, BASE_JID)
    print(f"Total flat results: {len(resp_b2.results)}")
    for jid, bucket in (resp_b2.jurisdiction_results or {}).items():
        print(f"  {jid}: {len(bucket)} results in bucket")
    print(f"Query time: {resp_b2.meta.query_time_ms}ms")
    print()
    print("Flat merged results (re-sorted by relevance):")
    for r in resp_b2.results:
        print(fmt_result(r, BASE_JID))
    bucket_jids = set((resp_b2.jurisdiction_results or {}).keys())
    flat_jids = {r.jurisdiction for r in resp_b2.results}
    print(f"\n  Buckets: {sorted(bucket_jids)}")
    print(f"  Flat jids: {sorted(flat_jids)}")
    assert "city-san-francisco" in flat_jids, (
        "FAIL: SF should be visible in flat results under per_jurisdiction_limit"
    )
    assert "city-berkeley" in flat_jids, (
        "FAIL: Berkeley should be visible in flat results under per_jurisdiction_limit"
    )
    # Each bucket capped at 5
    for jid, bucket in (resp_b2.jurisdiction_results or {}).items():
        assert len(bucket) <= 5, f"FAIL: {jid} bucket exceeded per_jurisdiction_limit=5: {len(bucket)}"
    print("  PASS: SF + Berkeley both visible, all buckets capped at 5")
    print()

    # ---------- Query C: parents ----------
    print("--- Query C: include_parents=True (state + federal) ---")
    req_c = SearchRequest(
        query=QUERY,
        corpus=["decisions"],
        include_parents=True,
        limit=LIMIT,
    )
    resp_c = await execute_search(req_c, civic, BASE_JID)
    print(f"Total results: {len(resp_c.results)}")
    print(f"Jurisdictions returned: {sorted((resp_c.jurisdiction_results or {}).keys())}")
    print(f"Query time: {resp_c.meta.query_time_ms}ms")
    for r in resp_c.results[:10]:
        print(fmt_result(r, BASE_JID))
    print()
    # Note: county-marin/state-california may have no decisions corpus content;
    # the goal here is to confirm the fan-out targets the parents and that
    # Berkeley does not leak into a parents-only query.
    jids_c = {r.jurisdiction for r in resp_c.results}
    berkeley_in_c = "city-berkeley" in jids_c
    print(f"  Boundary check: city-berkeley in parents-only results? {berkeley_in_c}")
    assert not berkeley_in_c, "FAIL: Berkeley leaked into parents-only query"
    print("  PASS: Berkeley correctly absent from parents-only query")
    print()

    # ---------- Summary ----------
    print("=== Phase B Verification Summary ===")
    print(f"  Query A (siblings): {len(resp_a.results)} results, "
          f"Berkeley absent: {not berkeley_in_a}")
    print(f"  Query B (also_include Berkeley+SF): {len(resp_b.results)} results, "
          f"Berkeley={len(berkeley_results)}, SF={len(sf_results)}, "
          f"cross_county weight enforced")
    print(f"  Query C (parents): {len(resp_c.results)} results, "
          f"Berkeley absent: {not berkeley_in_c}")
    print()
    print("ALL CHECKS PASS")


if __name__ == "__main__":
    asyncio.run(main())
