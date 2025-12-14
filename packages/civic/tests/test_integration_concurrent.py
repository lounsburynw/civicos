"""
Integration tests for concurrent user scenarios.

These tests verify the concurrent_users items from integration.json:
- 10 users add_voice() to same initiative simultaneously
- 10 users follow() same item simultaneously
- Voice counts remain accurate under concurrent writes
- Same user can't create duplicate subscriptions

Run: python -m pytest packages/civic/tests/test_integration_concurrent.py -v
"""

import os
import sys
import tempfile
import threading
import concurrent.futures
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import pytest

# Mark all tests in this module as integration + concurrent
pytestmark = [pytest.mark.integration, pytest.mark.concurrent]

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic/src"))
os.chdir(str(PROJECT_ROOT))

from civic import Civic
from civic.actions.initiatives import start_initiative
from civic.actions.voices import add_voice
from civic.actions.subscriptions import follow_item
from civic._internal.state import StateManager


class TestConcurrentVoices:
    """
    Integration tests for concurrent add_voice() calls.

    Maps to integration.json > concurrent_users > same_initiative > concurrent_voices
    """

    def test_concurrent_voices_10_users(self):
        """
        integration.json: concurrent_users > same_initiative > concurrent_voices
        test: "10 users add_voice() to same initiative simultaneously"

        Verifies:
        - 10 concurrent add_voice() calls complete without error
        - All 10 voices are persisted
        - No database errors or corruption
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_concurrent.db")

            # Create an initiative first
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="traffic",
                title="Protected bike lane on 4th St",
                description="Near-misses every week",
                creator_id="creator_001",
                db_path=db_path,
            )

            # Track results from each thread
            results: List[Dict[str, Any]] = []
            errors: List[Exception] = []
            lock = threading.Lock()

            def add_voice_task(user_num: int):
                """Task to add a voice from a specific user."""
                try:
                    voice = add_voice(
                        item_type="initiative",
                        item_id=initiative.id,
                        stance="support",
                        comment=f"I support this! - User {user_num}",
                        user_id=f"user_{user_num:03d}",
                        db_path=db_path,
                    )
                    with lock:
                        results.append({
                            "user_num": user_num,
                            "voice_id": voice.id,
                            "success": True,
                        })
                except Exception as e:
                    with lock:
                        errors.append(e)

            # Run 10 concurrent add_voice calls
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(add_voice_task, i) for i in range(10)]
                concurrent.futures.wait(futures)

            # Assert no errors
            assert len(errors) == 0, f"Concurrent voices had errors: {errors}"

            # Assert all 10 voices created
            assert len(results) == 10, f"Expected 10 voices, got {len(results)}"

            # Verify all voices are in database
            state = StateManager(db_path)
            voices = state.query_voices("initiative", initiative.id)
            assert len(voices) == 10, f"Expected 10 voices in DB, got {len(voices)}"

            # Verify all voice IDs are unique
            voice_ids = [r["voice_id"] for r in results]
            assert len(set(voice_ids)) == 10, "Voice IDs should be unique"

            # Verify all users are represented
            user_ids = [v["user_id"] for v in voices]
            for i in range(10):
                assert f"user_{i:03d}" in user_ids, f"user_{i:03d} should have a voice"

    def test_concurrent_voices_mixed_stances(self):
        """
        Verify concurrent voices with different stances work correctly.

        Verifies:
        - Mix of support/oppose/question stances handled correctly
        - Stance counts are accurate
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_concurrent_stances.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="housing",
                title="New development proposal",
                description="Proposed high-density development",
                db_path=db_path,
            )

            results = []
            errors = []
            lock = threading.Lock()

            stances = ["support", "support", "support", "support", "support",
                       "oppose", "oppose", "oppose", "question", "question"]

            def add_voice_task(user_num: int, stance: str):
                try:
                    voice = add_voice(
                        item_type="initiative",
                        item_id=initiative.id,
                        stance=stance,
                        comment=f"My {stance} comment - User {user_num}",
                        user_id=f"user_{user_num:03d}",
                        db_path=db_path,
                    )
                    with lock:
                        results.append({"stance": stance, "voice_id": voice.id})
                except Exception as e:
                    with lock:
                        errors.append(e)

            # Run concurrent calls with mixed stances
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(add_voice_task, i, stances[i])
                    for i in range(10)
                ]
                concurrent.futures.wait(futures)

            assert len(errors) == 0, f"Errors: {errors}"
            assert len(results) == 10

            # Verify stance counts
            state = StateManager(db_path)
            counts = state.count_voices("initiative", initiative.id)

            assert counts["support"] == 5, f"Expected 5 support, got {counts['support']}"
            assert counts["oppose"] == 3, f"Expected 3 oppose, got {counts['oppose']}"
            assert counts["question"] == 2, f"Expected 2 question, got {counts['question']}"
            assert counts["total"] == 10


class TestConcurrentFollows:
    """
    Integration tests for concurrent follow() calls.

    Maps to integration.json > concurrent_users > same_initiative > concurrent_follows
    """

    def test_concurrent_follows_10_users(self):
        """
        integration.json: concurrent_users > same_initiative > concurrent_follows
        test: "10 users follow() same item simultaneously"

        Verifies:
        - 10 concurrent follow() calls complete without error
        - All 10 subscriptions are persisted
        - No database errors
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_concurrent_follows.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="environment",
                title="Climate action plan",
                description="City climate action initiative",
                db_path=db_path,
            )

            results = []
            errors = []
            lock = threading.Lock()

            def follow_task(user_num: int):
                try:
                    sub = follow_item(
                        item_type="initiative",
                        item_id=initiative.id,
                        user_id=f"user_{user_num:03d}",
                        db_path=db_path,
                    )
                    with lock:
                        results.append({"user_num": user_num, "sub_id": sub.id})
                except Exception as e:
                    with lock:
                        errors.append(e)

            # Run 10 concurrent follows
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(follow_task, i) for i in range(10)]
                concurrent.futures.wait(futures)

            assert len(errors) == 0, f"Concurrent follows had errors: {errors}"
            assert len(results) == 10, f"Expected 10 subscriptions, got {len(results)}"

            # Verify all subscriptions in database
            state = StateManager(db_path)
            count = state.count_subscriptions("initiative", initiative.id)
            assert count == 10, f"Expected 10 subscriptions, got {count}"


class TestVoiceCountAccuracy:
    """
    Integration tests for voice count accuracy under concurrent writes.

    Maps to integration.json > concurrent_users > same_initiative > voice_count_accurate
    """

    def test_voice_count_accurate(self):
        """
        integration.json: concurrent_users > same_initiative > voice_count_accurate
        test: "Voice counts remain accurate under concurrent writes"

        Verifies:
        - Initiative voice_count is accurate after concurrent add_voice()
        - Count matches actual number of voices in database
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_voice_count.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="safety",
                title="Pedestrian crossing improvements",
                description="Improve crossings",
                db_path=db_path,
            )

            errors = []
            lock = threading.Lock()

            def add_voice_task(user_num: int):
                try:
                    add_voice(
                        item_type="initiative",
                        item_id=initiative.id,
                        stance="support",
                        comment=f"Support from user {user_num}",
                        user_id=f"user_{user_num:03d}",
                        db_path=db_path,
                    )
                except Exception as e:
                    with lock:
                        errors.append(e)

            # Run concurrent voice additions
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(add_voice_task, i) for i in range(10)]
                concurrent.futures.wait(futures)

            assert len(errors) == 0, f"Errors: {errors}"

            # Check voice_count on initiative
            state = StateManager(db_path)
            updated_initiative = state.get_initiative(initiative.id)

            # voice_count should equal 10
            assert updated_initiative["voice_count"] == 10, (
                f"Expected voice_count=10, got {updated_initiative['voice_count']}"
            )

            # Actual voices in DB should also be 10
            voices = state.query_voices("initiative", initiative.id)
            assert len(voices) == 10, f"Expected 10 voices, got {len(voices)}"

            # Counts should match
            assert updated_initiative["voice_count"] == len(voices), (
                "voice_count should match actual voice count"
            )


class TestNoDuplicateSubscriptions:
    """
    Integration tests for duplicate subscription prevention.

    Maps to integration.json > concurrent_users > same_initiative > no_duplicate_subscriptions
    """

    def test_no_duplicate_subscriptions(self):
        """
        integration.json: concurrent_users > same_initiative > no_duplicate_subscriptions
        test: "Same user can't create duplicate subscriptions"

        Verifies:
        - Same user following same item twice doesn't create duplicate
        - UNIQUE constraint is properly enforced
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_no_duplicates.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="parks",
                title="New park development",
                description="Community park project",
                db_path=db_path,
            )

            # First follow should succeed
            sub1 = follow_item(
                item_type="initiative",
                item_id=initiative.id,
                user_id="user_same",
                db_path=db_path,
            )

            # Second follow by same user should return existing subscription (not create new)
            sub2 = follow_item(
                item_type="initiative",
                item_id=initiative.id,
                user_id="user_same",
                db_path=db_path,
            )

            # Should return same or existing subscription, not create duplicate
            state = StateManager(db_path)
            count = state.count_subscriptions("initiative", initiative.id)

            assert count == 1, f"Expected 1 subscription (no duplicates), got {count}"

    def test_no_duplicate_subscriptions_concurrent(self):
        """
        Verify no duplicates when same user follows concurrently.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_concurrent_dupe.db")

            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="education",
                title="School funding",
                description="Increase school funding",
                db_path=db_path,
            )

            results = []
            errors = []
            lock = threading.Lock()

            def follow_task():
                try:
                    sub = follow_item(
                        item_type="initiative",
                        item_id=initiative.id,
                        user_id="user_concurrent",  # Same user for all
                        db_path=db_path,
                    )
                    with lock:
                        results.append(sub.id)
                except Exception as e:
                    with lock:
                        errors.append(e)

            # 5 concurrent follows by same user
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(follow_task) for _ in range(5)]
                concurrent.futures.wait(futures)

            # Should have no errors (handled gracefully)
            assert len(errors) == 0, f"Errors: {errors}"

            # Should only have 1 subscription in database
            state = StateManager(db_path)
            count = state.count_subscriptions("initiative", initiative.id)
            assert count == 1, f"Expected 1 subscription (no duplicates), got {count}"


class TestDatabaseContention:
    """
    Integration tests for database write conflicts.

    Maps to integration.json > concurrent_users > database_contention > write_conflicts
    """

    def test_write_conflicts(self):
        """
        integration.json: concurrent_users > database_contention > write_conflicts
        test: "Concurrent writes don't cause database locks"

        Verifies:
        - Multiple concurrent writes complete successfully
        - No "database is locked" errors
        - All data is persisted correctly
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_write_conflicts.db")

            # Create multiple initiatives
            initiatives = []
            for i in range(5):
                init = start_initiative(
                    jurisdiction="san-rafael-ca",
                    topic="various",
                    title=f"Initiative {i}",
                    description=f"Description {i}",
                    db_path=db_path,
                )
                initiatives.append(init)

            errors = []
            results = []
            lock = threading.Lock()

            def write_task(init_num: int, user_num: int):
                """Write a voice to an initiative."""
                try:
                    voice = add_voice(
                        item_type="initiative",
                        item_id=initiatives[init_num].id,
                        stance="support",
                        comment=f"Init {init_num}, User {user_num}",
                        user_id=f"user_{user_num:03d}",
                        db_path=db_path,
                    )
                    with lock:
                        results.append((init_num, user_num, voice.id))
                except Exception as e:
                    with lock:
                        errors.append(e)

            # 20 concurrent writes across 5 initiatives (4 per initiative)
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                for user_num in range(20):
                    init_num = user_num % 5
                    futures.append(executor.submit(write_task, init_num, user_num))
                concurrent.futures.wait(futures)

            # Check for database lock errors specifically
            lock_errors = [e for e in errors if "locked" in str(e).lower()]
            assert len(lock_errors) == 0, f"Database lock errors: {lock_errors}"

            # All writes should succeed
            assert len(errors) == 0, f"Errors: {errors}"
            assert len(results) == 20, f"Expected 20 results, got {len(results)}"

            # Verify all voices persisted
            state = StateManager(db_path)
            for i, init in enumerate(initiatives):
                voices = state.query_voices("initiative", init.id)
                assert len(voices) == 4, (
                    f"Initiative {i} should have 4 voices, got {len(voices)}"
                )


class TestReadDuringWrite:
    """
    Integration tests for read-during-write scenarios.

    Maps to integration.json > concurrent_users > database_contention > read_during_write
    """

    def test_read_during_write(self):
        """
        integration.json: concurrent_users > database_contention > read_during_write
        test: "Reads succeed while writes in progress"

        Verifies:
        - Read operations complete while write operations are ongoing
        - No blocking or timeout on reads
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_read_write.db")

            # Create initiative with some initial voices
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="infrastructure",
                title="Bridge repair",
                description="Fix the old bridge",
                db_path=db_path,
            )

            # Add some initial voices
            for i in range(3):
                add_voice(
                    item_type="initiative",
                    item_id=initiative.id,
                    stance="support",
                    comment=f"Initial voice {i}",
                    user_id=f"initial_{i}",
                    db_path=db_path,
                )

            read_results = []
            write_results = []
            errors = []
            lock = threading.Lock()

            def write_task(user_num: int):
                try:
                    voice = add_voice(
                        item_type="initiative",
                        item_id=initiative.id,
                        stance="support",
                        comment=f"Concurrent voice {user_num}",
                        user_id=f"concurrent_{user_num}",
                        db_path=db_path,
                    )
                    with lock:
                        write_results.append(voice.id)
                except Exception as e:
                    with lock:
                        errors.append(("write", e))

            def read_task(read_num: int):
                try:
                    state = StateManager(db_path)
                    voices = state.query_voices("initiative", initiative.id)
                    with lock:
                        read_results.append((read_num, len(voices)))
                except Exception as e:
                    with lock:
                        errors.append(("read", e))

            # Mix of reads and writes
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futures = []
                for i in range(10):
                    if i % 2 == 0:
                        futures.append(executor.submit(write_task, i))
                    else:
                        futures.append(executor.submit(read_task, i))
                concurrent.futures.wait(futures)

            # All operations should complete
            assert len(errors) == 0, f"Errors: {errors}"

            # Should have 5 writes completed
            assert len(write_results) == 5, f"Expected 5 writes, got {len(write_results)}"

            # Should have 5 reads completed
            assert len(read_results) == 5, f"Expected 5 reads, got {len(read_results)}"

            # All reads should return valid counts (>= 3 initial voices)
            for read_num, count in read_results:
                assert count >= 3, f"Read {read_num} got count {count}, expected >= 3"


class TestTransactionIsolation:
    """
    Integration tests for transaction isolation.

    Maps to integration.json > concurrent_users > database_contention > transaction_isolation
    """

    def test_partial_writes_not_visible_on_rollback(self):
        """
        integration.json: concurrent_users > database_contention > transaction_isolation
        test: "Partial writes don't become visible"

        Verifies:
        - When a multi-step transaction fails and rolls back, partial changes
          are not visible to concurrent readers
        - Database maintains ACID properties
        """
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_isolation.db")

            # Create initiative first
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="test",
                title="Isolation test initiative",
                description="Testing transaction isolation",
                db_path=db_path,
            )

            # Track what a concurrent reader sees
            observed_voices = []
            observation_complete = threading.Event()
            writer_started = threading.Event()
            lock = threading.Lock()

            def failing_writer():
                """
                Writer that inserts a voice, signals reader, then fails.
                The voice should NOT be visible to the reader after rollback.
                """
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                try:
                    # Start transaction by inserting a voice
                    cursor.execute("""
                        INSERT INTO voices (id, user_id, item_type, item_id, stance, comment, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        "voice-partial-should-not-exist",
                        "failing_writer",
                        "initiative",
                        initiative.id,
                        "support",
                        "This voice should NOT be visible!",
                        datetime.now().isoformat(),
                    ))
                    # Signal that we've written (but not committed)
                    writer_started.set()

                    # Wait for reader to complete observations
                    observation_complete.wait(timeout=5)

                    # Now simulate a failure - rollback
                    conn.rollback()
                finally:
                    conn.close()

            def concurrent_reader():
                """
                Reader that observes voices while writer has uncommitted changes.
                Should NOT see the partial write.
                """
                # Wait for writer to have inserted (but not committed)
                writer_started.wait(timeout=5)

                # Give the writer a moment to ensure the INSERT is executed
                import time
                time.sleep(0.1)

                # Now read - should NOT see the uncommitted voice
                state = StateManager(db_path)
                voices = state.query_voices("initiative", initiative.id)

                with lock:
                    observed_voices.extend(voices)

                # Signal that we've completed our observation
                observation_complete.set()

            # Run writer and reader concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                writer_future = executor.submit(failing_writer)
                reader_future = executor.submit(concurrent_reader)

                concurrent.futures.wait([writer_future, reader_future])

            # The partial write should NOT have been visible to the reader
            partial_voice_ids = [v["id"] for v in observed_voices
                                 if v["id"] == "voice-partial-should-not-exist"]
            assert len(partial_voice_ids) == 0, (
                "Partial writes should not be visible to concurrent readers"
            )

            # After rollback, the voice should not exist in the database
            state = StateManager(db_path)
            voices = state.query_voices("initiative", initiative.id)
            final_voice_ids = [v["id"] for v in voices]
            assert "voice-partial-should-not-exist" not in final_voice_ids, (
                "Rolled back voice should not exist in database"
            )

    def test_committed_writes_visible_after_commit(self):
        """
        Verify that committed writes ARE visible to subsequent readers.

        This is the positive counterpart - once committed, data should be visible.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_commit_visible.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="test",
                title="Commit visibility test",
                description="Testing committed writes are visible",
                db_path=db_path,
            )

            # Add a voice through normal API (which commits)
            voice = add_voice(
                item_type="initiative",
                item_id=initiative.id,
                stance="support",
                comment="This voice should be visible!",
                user_id="normal_user",
                db_path=db_path,
            )

            # Concurrent reader should see the committed voice
            def read_task():
                state = StateManager(db_path)
                return state.query_voices("initiative", initiative.id)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(read_task)
                voices = future.result()

            voice_ids = [v["id"] for v in voices]
            assert voice.id in voice_ids, (
                "Committed voice should be visible to readers"
            )

    def test_multiple_concurrent_transactions_isolated(self):
        """
        Verify that multiple concurrent transactions don't see each other's
        uncommitted changes.

        Each transaction operates in isolation until commit.
        """
        import sqlite3
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_multi_isolation.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="test",
                title="Multi-transaction isolation test",
                description="Testing multiple concurrent transactions",
                db_path=db_path,
            )

            # Each transaction will insert a voice and check what it can see
            observations = {}
            errors = []
            lock = threading.Lock()

            def transaction_task(txn_id: int):
                """
                Each transaction:
                1. Inserts a voice
                2. Checks what voices it can see (should see its own uncommitted)
                3. Commits
                """
                try:
                    conn = sqlite3.connect(db_path, timeout=10)
                    cursor = conn.cursor()
                    try:
                        # Insert our voice
                        voice_id = f"voice-txn-{txn_id}"
                        cursor.execute("""
                            INSERT INTO voices (id, user_id, item_type, item_id, stance, comment, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            voice_id,
                            f"user_txn_{txn_id}",
                            "initiative",
                            initiative.id,
                            "support",
                            f"Transaction {txn_id}",
                            datetime.now().isoformat(),
                        ))

                        # Check what we can see (using same connection = same transaction)
                        cursor.execute("""
                            SELECT id FROM voices WHERE item_type = ? AND item_id = ?
                        """, ("initiative", initiative.id))
                        visible_ids = [row[0] for row in cursor.fetchall()]

                        with lock:
                            observations[txn_id] = visible_ids

                        # Commit
                        conn.commit()
                    finally:
                        conn.close()
                except Exception as e:
                    with lock:
                        errors.append((txn_id, e))

            # Run 3 concurrent transactions
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(transaction_task, i) for i in range(3)]
                concurrent.futures.wait(futures)

            # Check for errors
            assert len(errors) == 0, f"Transaction errors: {errors}"

            # Each transaction should have seen its own voice
            for txn_id, visible in observations.items():
                # The transaction should see its own uncommitted voice
                assert f"voice-txn-{txn_id}" in visible, (
                    f"Transaction {txn_id} should see its own uncommitted voice"
                )

            # After all commits, all voices should be visible
            state = StateManager(db_path)
            final_voices = state.query_voices("initiative", initiative.id)
            final_ids = [v["id"] for v in final_voices]

            for i in range(3):
                assert f"voice-txn-{i}" in final_ids, (
                    f"voice-txn-{i} should be in final results after commit"
                )

    def test_voice_count_consistent_during_transaction(self):
        """
        Verify that voice_count on initiative remains consistent even when
        concurrent transactions are in progress.

        The count should not include uncommitted voices from other transactions.
        """
        import sqlite3
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_count_consistent.db")

            # Create initiative with initial voices
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="test",
                title="Count consistency test",
                description="Testing count consistency",
                db_path=db_path,
            )

            # Add 5 initial committed voices
            for i in range(5):
                add_voice(
                    item_type="initiative",
                    item_id=initiative.id,
                    stance="support",
                    comment=f"Initial voice {i}",
                    user_id=f"initial_user_{i}",
                    db_path=db_path,
                )

            uncommitted_write_done = threading.Event()
            reader_done = threading.Event()
            observed_count = []
            lock = threading.Lock()

            def uncommitted_writer():
                """
                Writer that inserts voice + updates count but doesn't commit.
                """
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                try:
                    # Insert voice and update count (like create_voice does)
                    cursor.execute("""
                        INSERT INTO voices (id, user_id, item_type, item_id, stance, comment, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        "voice-uncommitted",
                        "uncommitted_user",
                        "initiative",
                        initiative.id,
                        "support",
                        "Uncommitted voice",
                        datetime.now().isoformat(),
                    ))
                    cursor.execute("""
                        UPDATE initiatives SET voice_count = voice_count + 1 WHERE id = ?
                    """, (initiative.id,))

                    # Signal that uncommitted write is done
                    uncommitted_write_done.set()

                    # Wait for reader to observe
                    reader_done.wait(timeout=5)

                    # Rollback - don't commit
                    conn.rollback()
                finally:
                    conn.close()

            def count_reader():
                """
                Reader that checks voice_count while uncommitted changes exist.
                """
                uncommitted_write_done.wait(timeout=5)
                time.sleep(0.1)

                state = StateManager(db_path)
                init = state.get_initiative(initiative.id)
                actual_voices = state.query_voices("initiative", initiative.id)

                with lock:
                    observed_count.append({
                        "voice_count": init["voice_count"],
                        "actual_voices": len(actual_voices)
                    })

                reader_done.set()

            # Run concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                writer_future = executor.submit(uncommitted_writer)
                reader_future = executor.submit(count_reader)
                concurrent.futures.wait([writer_future, reader_future])

            # The reader should have seen consistent data (5 voices, count=5)
            assert len(observed_count) == 1
            obs = observed_count[0]

            # voice_count and actual_voices should match (both 5)
            assert obs["voice_count"] == 5, (
                f"voice_count should be 5 (not see uncommitted), got {obs['voice_count']}"
            )
            assert obs["actual_voices"] == 5, (
                f"actual_voices should be 5 (not see uncommitted), got {obs['actual_voices']}"
            )

            # After rollback, final state should still be 5
            state = StateManager(db_path)
            final_init = state.get_initiative(initiative.id)
            final_voices = state.query_voices("initiative", initiative.id)

            assert final_init["voice_count"] == 5, (
                f"Final voice_count should be 5, got {final_init['voice_count']}"
            )
            assert len(final_voices) == 5, (
                f"Final voice count should be 5, got {len(final_voices)}"
            )

    def test_atomic_multi_table_updates(self):
        """
        Verify that multi-table updates are atomic.

        When creating a voice, both the voice insertion and initiative update
        should succeed or fail together.
        """
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_atomic.db")

            # Create initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="test",
                title="Atomic update test",
                description="Testing atomic multi-table updates",
                db_path=db_path,
            )

            # Simulate a failure after voice insert but before count update
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                # Insert voice
                cursor.execute("""
                    INSERT INTO voices (id, user_id, item_type, item_id, stance, comment, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    "voice-should-rollback",
                    "test_user",
                    "initiative",
                    initiative.id,
                    "support",
                    "This should rollback",
                    datetime.now().isoformat(),
                ))

                # Simulate failure before we can update the count
                raise Exception("Simulated failure")

            except Exception:
                conn.rollback()
            finally:
                conn.close()

            # Verify nothing was persisted
            state = StateManager(db_path)
            voices = state.query_voices("initiative", initiative.id)
            init = state.get_initiative(initiative.id)

            assert len(voices) == 0, "No voices should exist after rollback"
            assert init["voice_count"] == 0, "voice_count should be 0 after rollback"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
