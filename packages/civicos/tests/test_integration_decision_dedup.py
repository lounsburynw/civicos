"""
Integration test: store_decisions() idempotency against real Postgres.

Regression guard for launch.json:fix_decision_storage_dedup. The bug:
re-extracting the same meeting accumulated duplicate rows because decision
IDs were derived from the LLM's enumeration order. The fix: stable IDs
hashed from LLM-stable fields (item_ref, title, item_type, outcome,
budget_amount), so the temporal-versioning UPDATE in store_decisions()
matches the prior version on every re-run.

Validates the *full chain* per CLAUDE.md test policy:
1. Decision payload constructed by extraction CLI is given a stable ID
2. Postgres store_decisions() closes the prior version on re-store
3. Exactly one row remains with valid_to IS NULL after N re-stores
4. Exactly one logical decision exists in the "current" view

Requires DATABASE_URL in .env. Skipped otherwise.
"""

import os
import uuid

import pytest

# Load .env for DATABASE_URL (matches the pattern from test_integration_cron_wiring.py)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — need real Postgres for integration tests",
)


@pytest.fixture
def backend():
    """Real PostgresBackend for integration testing."""
    from civicos.storage.postgres_backend import PostgresBackend
    return PostgresBackend(DATABASE_URL)


@pytest.fixture
def test_jurisdiction(backend):
    """
    Unique test jurisdiction ID, registered in city_states (FK target) and
    cleaned up after the test.
    """
    jid = f"city-test-dedup-{uuid.uuid4().hex[:8]}"

    # Ensure schema exists, then register the jurisdiction so the
    # decisions.jurisdiction_id FK constraint can be satisfied
    import psycopg2
    from datetime import datetime, timezone

    conn = psycopg2.connect(DATABASE_URL)
    try:
        # Trigger schema creation via a real backend call
        backend._ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO city_states (jurisdiction_id, jurisdiction_name, as_of)
                VALUES (%s, %s, %s)
                ON CONFLICT (jurisdiction_id) DO NOTHING
                """,
                (jid, f"Test Dedup {jid}", datetime.now(timezone.utc).replace(tzinfo=None)),
            )
        conn.commit()
    finally:
        conn.close()

    yield jid

    # Cleanup: remove decisions then the city_states row
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM decisions WHERE jurisdiction_id = %s", (jid,))
            cur.execute("DELETE FROM city_states WHERE jurisdiction_id = %s", (jid,))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def _make_decision(item_ref: str, title: str, outcome: str = "approved", budget: float = 100_000.0) -> dict:
    """
    Build a decision payload as the extraction CLI would, with a stable ID
    computed via the same helper.
    """
    from civicos.storage.integrity import compute_stable_decision_id

    return {
        "id": compute_stable_decision_id(
            jurisdiction_id="placeholder",  # overwritten per-test below
            meeting_ref="m1",
            item_ref=item_ref,
            title=title,
            item_type="action",
            outcome=outcome,
            budget_amount=budget,
        ),
        "meeting_date": "2026-04-01",
        "agenda_item": item_ref,
        "title": title,
        "outcome": outcome,
        "item_type": "action",
        "extraction_method": "test",
    }


def _decisions_for(jurisdiction_id: str, decisions: list[dict]) -> list[dict]:
    """Re-stamp test decisions with the actual test jurisdiction in the ID."""
    from civicos.storage.integrity import compute_stable_decision_id

    out = []
    for d in decisions:
        d2 = dict(d)
        d2["id"] = compute_stable_decision_id(
            jurisdiction_id=jurisdiction_id,
            meeting_ref="m1",
            item_ref=d["agenda_item"],
            title=d["title"],
            item_type=d.get("item_type", "action"),
            outcome=d.get("outcome"),
            budget_amount=None,
        )
        out.append(d2)
    return out


def _count_open_decisions(backend, jurisdiction_id: str) -> int:
    """Count rows with valid_to IS NULL — the 'current' view."""
    conn = backend._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM decisions
                WHERE jurisdiction_id = %s AND valid_to IS NULL
                """,
                (jurisdiction_id,),
            )
            return cur.fetchone()[0]
    finally:
        backend._return_connection(conn)


def _count_all_decisions(backend, jurisdiction_id: str) -> int:
    """Count all rows including closed versions — the temporal history."""
    conn = backend._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM decisions WHERE jurisdiction_id = %s",
                (jurisdiction_id,),
            )
            return cur.fetchone()[0]
    finally:
        backend._return_connection(conn)


class TestStoreDecisionsIdempotency:
    """
    The regression guard. Without the fix_decision_storage_dedup work, calling
    store_decisions() twice with the same payload accumulates duplicate rows.
    With the fix, the prior version is closed (valid_to set) and a new version
    is inserted with the same id, so the "current" view is stable.
    """

    def test_double_store_keeps_one_open_version(self, backend, test_jurisdiction):
        """Store the same decision twice → exactly 1 open version, 1 closed version."""
        decisions = _decisions_for(
            test_jurisdiction,
            [_make_decision("5.A", "Authorize affordable housing funding")],
        )

        # First store
        backend.store_decisions(test_jurisdiction, decisions)
        assert _count_open_decisions(backend, test_jurisdiction) == 1
        assert _count_all_decisions(backend, test_jurisdiction) == 1

        # Second store with the SAME payload — this is the bug repro
        backend.store_decisions(test_jurisdiction, decisions)
        # Without the fix: 2 open versions, 2 total rows
        # With the fix: 1 open version (the new one), 1 closed version (the old one)
        assert _count_open_decisions(backend, test_jurisdiction) == 1, (
            "Re-storing the same decision must not create a second open version. "
            "If this fails, the dedup fix has regressed."
        )
        assert _count_all_decisions(backend, test_jurisdiction) == 2

    def test_triple_store_keeps_one_open_version(self, backend, test_jurisdiction):
        """Three identical stores → still 1 open version, accumulated history."""
        decisions = _decisions_for(
            test_jurisdiction,
            [_make_decision("5.A", "Authorize affordable housing funding")],
        )

        for _ in range(3):
            backend.store_decisions(test_jurisdiction, decisions)

        assert _count_open_decisions(backend, test_jurisdiction) == 1
        # 1 open + 2 closed = 3 total
        assert _count_all_decisions(backend, test_jurisdiction) == 3

    def test_reordered_batch_idempotent(self, backend, test_jurisdiction):
        """
        The actual bug condition: same set of decisions in a different order.

        Before the fix, each decision's ID came from its position in the list,
        so swapping order made all IDs shift and the temporal-versioning UPDATE
        matched the wrong rows. With stable content-derived IDs, ordering is
        irrelevant.
        """
        d_a = _make_decision("5.A", "Approve contract X", budget=100_000)
        d_b = _make_decision("5.B", "Approve contract Y", budget=200_000)
        d_c = _make_decision("5.C", "Approve contract Z", budget=300_000)

        run1 = _decisions_for(test_jurisdiction, [d_a, d_b, d_c])
        run2 = _decisions_for(test_jurisdiction, [d_c, d_a, d_b])  # different order

        backend.store_decisions(test_jurisdiction, run1)
        assert _count_open_decisions(backend, test_jurisdiction) == 3

        backend.store_decisions(test_jurisdiction, run2)
        # Still 3 logical decisions in the current view, not 6
        assert _count_open_decisions(backend, test_jurisdiction) == 3, (
            "Reordered re-store accumulated duplicates — the original bug is back."
        )
        # Each of the 3 decisions has 1 open version + 1 closed version
        assert _count_all_decisions(backend, test_jurisdiction) == 6

    def test_genuinely_different_outcome_creates_distinct_decision(
        self, backend, test_jurisdiction
    ):
        """
        Disambiguation guard: if two decisions in a meeting share item_ref+title
        but have different outcomes (e.g., a hearing approved vs. continued),
        they must hash to different IDs and persist as separate rows.
        """
        approved = _decisions_for(
            test_jurisdiction,
            [_make_decision("5.A", "Public hearing — rezoning", outcome="approved")],
        )
        continued = _decisions_for(
            test_jurisdiction,
            [_make_decision("5.A", "Public hearing — rezoning", outcome="continued")],
        )

        # IDs must differ (sanity check)
        assert approved[0]["id"] != continued[0]["id"]

        backend.store_decisions(test_jurisdiction, approved + continued)
        assert _count_open_decisions(backend, test_jurisdiction) == 2

        # Re-storing both is still idempotent
        backend.store_decisions(test_jurisdiction, approved + continued)
        assert _count_open_decisions(backend, test_jurisdiction) == 2
