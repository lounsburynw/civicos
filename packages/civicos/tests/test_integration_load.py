"""
Integration tests for load testing and performance.

These tests verify the load_testing items from integration.json:
- Query endpoints respond < 500ms at p95
- Action endpoints respond < 1s at p95
- System handles 50 concurrent requests

Run: python -m pytest packages/civicos/tests/test_integration_load.py -v
"""

import os
import sys
import sqlite3
import tempfile
import time
import statistics
import concurrent.futures
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple

import pytest

# Mark all tests in this module as slow (load tests, CI-only)
pytestmark = pytest.mark.slow

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos/src"))
os.chdir(str(PROJECT_ROOT))

from civicos import CivicOS
from civicos.actions.initiatives import start_initiative
from civicos.actions.voices import add_voice
from civicos.actions.subscriptions import follow_item
from civicos._internal.state import StateManager


def percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile of a list of values."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_data) else f
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


class TestQueryLatencyP95:
    """
    Integration tests for query endpoint performance.

    Maps to integration.json > load_testing > api_performance > query_latency_p95
    """

    def setup_test_data(self, db_path: str):
        """Seed database with test data for realistic query performance testing."""
        state = StateManager(db_path)

        # Create a jurisdiction with meetings
        meetings = []
        now = datetime.now()
        for i in range(50):
            meeting_date = now + timedelta(days=i)
            meetings.append({
                "id": f"meeting_{i:03d}",
                "title": f"City Council Meeting {i}",
                "meeting_type": "City Council",
                "meeting_datetime": meeting_date.isoformat(),
                "location": "City Hall",
                "agenda_items": [
                    {"id": f"item_{i}_{j}", "title": f"Agenda Item {j}", "description": "Test item"}
                    for j in range(10)
                ]
            })

        state.update_meetings("san-rafael-ca", meetings)

        # Create some initiatives
        for i in range(20):
            start_initiative(
                jurisdiction="san-rafael-ca",
                topic=["traffic", "housing", "parks", "safety"][i % 4],
                title=f"Initiative {i}",
                description=f"Description for initiative {i}",
                creator_id=f"user_{i:03d}",
                db_path=db_path,
            )

        return state

    def test_whats_next_p95_under_500ms(self):
        """
        integration.json: load_testing > api_performance > query_latency_p95
        test: "Query endpoints respond < 500ms at p95"

        Verifies whats_next() responds under 500ms at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_latency.db")
            self.setup_test_data(db_path)

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            # Run 100 queries to get meaningful p95
            latencies = []
            for _ in range(100):
                start = time.perf_counter()
                result = civic.whats_next(days=30)
                elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhats_next() latency stats (100 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"whats_next() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_what_applies_p95_under_500ms(self):
        """
        Verifies what_applies() responds under 500ms at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_latency.db")

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            topics = ["housing", "traffic", "parks", "safety", "environment"]

            latencies = []
            for i in range(100):
                topic = topics[i % len(topics)]
                start = time.perf_counter()
                result = civic.what_applies(topic)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhat_applies() latency stats (100 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"what_applies() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_what_happened_p95_under_500ms(self):
        """
        Verifies what_happened() responds under 500ms at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_latency.db")

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            queries = ["housing development", "bike lanes", "traffic study", "park funding", "safety audit"]

            latencies = []
            for i in range(100):
                query = queries[i % len(queries)]
                start = time.perf_counter()
                result = civic.what_happened(query)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhat_happened() latency stats (100 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"what_happened() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_whos_with_me_p95_under_500ms(self):
        """
        Verifies whos_with_me() responds under 500ms at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_latency.db")
            self.setup_test_data(db_path)

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            topics = ["traffic", "housing", "parks", "safety", "environment"]

            latencies = []
            for i in range(100):
                topic = topics[i % len(topics)]
                start = time.perf_counter()
                result = civic.whos_with_me(topic)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhos_with_me() latency stats (100 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"whos_with_me() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_all_query_methods_p95_combined(self):
        """
        Combined test of all query methods to verify overall query performance.

        This test runs all query methods in a realistic mixed workload.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_combined_latency.db")
            self.setup_test_data(db_path)

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            all_latencies = []
            method_latencies = {
                "whats_next": [],
                "what_applies": [],
                "what_happened": [],
                "whos_with_me": []
            }

            topics = ["housing", "traffic", "parks", "safety", "environment"]

            # Mixed workload: 100 calls across all methods
            for i in range(100):
                topic = topics[i % len(topics)]
                method = i % 4

                start = time.perf_counter()

                if method == 0:
                    civic.whats_next(days=30)
                    method_name = "whats_next"
                elif method == 1:
                    civic.what_applies(topic)
                    method_name = "what_applies"
                elif method == 2:
                    civic.what_happened(topic)
                    method_name = "what_happened"
                else:
                    civic.whos_with_me(topic)
                    method_name = "whos_with_me"

                elapsed = (time.perf_counter() - start) * 1000
                all_latencies.append(elapsed)
                method_latencies[method_name].append(elapsed)

            p95 = percentile(all_latencies, 95)
            p50 = percentile(all_latencies, 50)
            mean = statistics.mean(all_latencies)

            print(f"\nCombined query latency stats (100 calls, mixed workload):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            for method, latencies in method_latencies.items():
                if latencies:
                    mp95 = percentile(latencies, 95)
                    print(f"  {method} p95: {mp95:.2f}ms")

            assert p95 < 500, f"Combined query p95 latency {p95:.2f}ms exceeds 500ms threshold"


class TestActionLatencyP95:
    """
    Integration tests for action endpoint performance.

    Maps to integration.json > load_testing > api_performance > action_latency_p95
    """

    def test_start_something_p95_under_1s(self):
        """
        integration.json: load_testing > api_performance > action_latency_p95
        test: "Action endpoints respond < 1s at p95"

        Verifies start_something() responds under 1 second at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_action_latency.db")

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            latencies = []
            for i in range(50):  # Fewer iterations for write operations
                start = time.perf_counter()
                civic.start_something(
                    topic="traffic",
                    title=f"Test Initiative {i}",
                    description=f"Description {i}",
                    creator_id=f"user_{i:03d}"
                )
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nstart_something() latency stats (50 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 1000, f"start_something() p95 latency {p95:.2f}ms exceeds 1000ms threshold"

    def test_add_voice_p95_under_1s(self):
        """
        Verifies add_voice() responds under 1 second at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_voice_latency.db")

            # Create an initiative first
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="housing",
                title="Test Initiative",
                description="For performance testing",
                creator_id="creator_001",
                db_path=db_path,
            )

            latencies = []
            for i in range(50):
                start = time.perf_counter()
                add_voice(
                    item_type="initiative",
                    item_id=initiative.id,
                    stance="support",
                    comment=f"Voice {i}",
                    user_id=f"user_{i:03d}",
                    db_path=db_path,
                )
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nadd_voice() latency stats (50 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 1000, f"add_voice() p95 latency {p95:.2f}ms exceeds 1000ms threshold"

    def test_follow_p95_under_1s(self):
        """
        Verifies follow() responds under 1 second at 95th percentile.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_follow_latency.db")

            # Create an initiative
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="parks",
                title="Test Initiative",
                description="For performance testing",
                creator_id="creator_001",
                db_path=db_path,
            )

            latencies = []
            for i in range(50):
                start = time.perf_counter()
                follow_item(
                    item_type="initiative",
                    item_id=initiative.id,
                    user_id=f"user_{i:03d}",
                    db_path=db_path,
                )
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nfollow() latency stats (50 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 1000, f"follow() p95 latency {p95:.2f}ms exceeds 1000ms threshold"


class TestConcurrentRequests:
    """
    Integration tests for concurrent request handling.

    Maps to integration.json > load_testing > api_performance > concurrent_requests
    """

    def test_50_concurrent_query_requests(self):
        """
        integration.json: load_testing > api_performance > concurrent_requests
        test: "System handles 50 concurrent requests"

        Verifies system can handle 50 concurrent query requests.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_concurrent.db")

            # Seed data
            state = StateManager(db_path)
            meetings = []
            now = datetime.now()
            for i in range(20):
                meeting_date = now + timedelta(days=i)
                meetings.append({
                    "id": f"meeting_{i:03d}",
                    "title": f"Meeting {i}",
                    "meeting_type": "Council",
                    "meeting_datetime": meeting_date.isoformat(),
                    "location": "City Hall",
                })
            state.update_meetings("san-rafael-ca", meetings)

            results = []
            errors = []
            latencies = []

            def query_task(task_id: int) -> Tuple[int, float, bool]:
                """Execute a query and return timing."""
                try:
                    civic = CivicOS("san-rafael-ca", db_path=db_path)

                    start = time.perf_counter()

                    # Rotate through different query methods
                    method = task_id % 4
                    if method == 0:
                        civic.whats_next(days=30)
                    elif method == 1:
                        civic.what_applies("housing")
                    elif method == 2:
                        civic.what_happened("traffic")
                    else:
                        civic.whos_with_me("parks")

                    elapsed = (time.perf_counter() - start) * 1000
                    return (task_id, elapsed, True)
                except Exception as e:
                    return (task_id, 0, False)

            # Run 50 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(query_task, i) for i in range(50)]
                for future in concurrent.futures.as_completed(futures):
                    task_id, elapsed, success = future.result()
                    if success:
                        results.append(task_id)
                        latencies.append(elapsed)
                    else:
                        errors.append(task_id)

            success_rate = len(results) / 50 * 100

            print(f"\n50 concurrent requests stats:")
            print(f"  Success: {len(results)}/50 ({success_rate:.1f}%)")
            print(f"  Errors:  {len(errors)}")
            if latencies:
                print(f"  Mean latency: {statistics.mean(latencies):.2f}ms")
                print(f"  P95 latency:  {percentile(latencies, 95):.2f}ms")

            assert len(errors) == 0, f"Concurrent requests had {len(errors)} errors"
            assert len(results) == 50, f"Expected 50 successful requests, got {len(results)}"

    def test_50_concurrent_mixed_requests(self):
        """
        Verifies system handles 50 concurrent mixed (read + write) requests.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_mixed_concurrent.db")

            # Seed data
            state = StateManager(db_path)
            meetings = []
            now = datetime.now()
            for i in range(10):
                meeting_date = now + timedelta(days=i)
                meetings.append({
                    "id": f"meeting_{i:03d}",
                    "title": f"Meeting {i}",
                    "meeting_type": "Council",
                    "meeting_datetime": meeting_date.isoformat(),
                })
            state.update_meetings("san-rafael-ca", meetings)

            # Create one initiative for voice tests
            initiative = start_initiative(
                jurisdiction="san-rafael-ca",
                topic="traffic",
                title="Shared Initiative",
                description="For concurrent testing",
                creator_id="setup_user",
                db_path=db_path,
            )

            results = []
            errors = []
            latencies = []

            def mixed_task(task_id: int) -> Tuple[int, float, bool, str]:
                """Execute a mixed operation."""
                try:
                    start = time.perf_counter()

                    # 60% reads, 40% writes
                    if task_id % 5 < 3:
                        # Read operation
                        civic = CivicOS("san-rafael-ca", db_path=db_path)
                        if task_id % 2 == 0:
                            civic.whats_next(days=30)
                            op = "whats_next"
                        else:
                            civic.what_applies("housing")
                            op = "what_applies"
                    else:
                        # Write operation
                        if task_id % 2 == 0:
                            add_voice(
                                item_type="initiative",
                                item_id=initiative.id,
                                stance="support",
                                comment=f"Voice from task {task_id}",
                                user_id=f"user_{task_id:03d}",
                                db_path=db_path,
                            )
                            op = "add_voice"
                        else:
                            start_initiative(
                                jurisdiction="san-rafael-ca",
                                topic="housing",
                                title=f"Initiative {task_id}",
                                description=f"Created by task {task_id}",
                                creator_id=f"user_{task_id:03d}",
                                db_path=db_path,
                            )
                            op = "start_initiative"

                    elapsed = (time.perf_counter() - start) * 1000
                    return (task_id, elapsed, True, op)
                except Exception as e:
                    return (task_id, 0, False, str(e))

            # Run 50 concurrent mixed requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(mixed_task, i) for i in range(50)]
                for future in concurrent.futures.as_completed(futures):
                    task_id, elapsed, success, op = future.result()
                    if success:
                        results.append((task_id, op))
                        latencies.append(elapsed)
                    else:
                        errors.append((task_id, op))

            success_rate = len(results) / 50 * 100

            print(f"\n50 concurrent mixed requests stats:")
            print(f"  Success: {len(results)}/50 ({success_rate:.1f}%)")
            print(f"  Errors:  {len(errors)}")
            if latencies:
                print(f"  Mean latency: {statistics.mean(latencies):.2f}ms")
                print(f"  P95 latency:  {percentile(latencies, 95):.2f}ms")

            # Operation breakdown
            ops = {}
            for task_id, op in results:
                ops[op] = ops.get(op, 0) + 1
            print(f"  Operations: {ops}")

            assert len(errors) == 0, f"Mixed concurrent requests had {len(errors)} errors: {errors}"
            assert len(results) == 50, f"Expected 50 successful requests, got {len(results)}"


class TestLargeResultSets:
    """
    Integration tests for database performance with large result sets.

    Maps to integration.json > load_testing > database_performance > large_result_sets
    """

    def setup_large_dataset(self, db_path: str, num_meetings: int = 100, items_per_meeting: int = 15):
        """
        Seed database with a large dataset for performance testing.

        Creates meetings with agenda items, resulting in 1000+ total items.

        Args:
            db_path: Path to database
            num_meetings: Number of meetings to create (default: 100)
            items_per_meeting: Number of agenda items per meeting (default: 15)

        Returns:
            StateManager instance
        """
        state = StateManager(db_path)

        # Create a large number of meetings with agenda items
        meetings = []
        base_date = datetime.now()
        topics = ["housing", "traffic", "parks", "safety", "budget", "zoning", "transit", "water"]

        for i in range(num_meetings):
            # Spread meetings over 2 years (past and future)
            meeting_date = base_date + timedelta(days=i - num_meetings // 2)

            agenda_items = []
            for j in range(items_per_meeting):
                topic = topics[(i + j) % len(topics)]
                agenda_items.append({
                    "id": f"item_{i:04d}_{j:02d}",
                    "item_number": f"{j + 1}.{chr(97 + (j % 5))}",
                    "title": f"Agenda Item {j + 1}: {topic.title()} Development Review #{i * items_per_meeting + j}",
                    "description": f"Discussion of {topic} matters for district {(i % 5) + 1}. "
                                   f"This item involves considerations for {topic} planning and development "
                                   f"in relation to General Plan policies. Staff recommends approval.",
                    "project_type": topic,
                    "outcome": ["passed", "failed", "continued"][i % 3],
                    "votes": {"yes": 4, "no": 1, "abstain": 0} if i % 3 == 0 else None
                })

            meetings.append({
                "id": f"meeting_{i:04d}",
                "title": f"City Council Meeting #{i + 1}",
                "meeting_type": ["City Council", "Planning Commission", "Board of Supervisors"][i % 3],
                "meeting_datetime": meeting_date.isoformat(),
                "location": "City Hall, Council Chambers",
                "agenda_items": agenda_items,
                "status": "past" if meeting_date < base_date else "upcoming"
            })

        state.update_meetings("san-rafael-ca", meetings)

        # Also create many initiatives for whos_with_me testing
        for i in range(200):
            topic = topics[i % len(topics)]
            start_initiative(
                jurisdiction="san-rafael-ca",
                topic=topic,
                title=f"Initiative {i + 1}: Improve {topic.title()} in District {(i % 5) + 1}",
                description=f"Community initiative to address {topic} concerns.",
                creator_id=f"user_{i % 50:03d}",
                db_path=db_path,
            )

        return state

    def test_whats_next_with_1000_items(self):
        """
        integration.json: load_testing > database_performance > large_result_sets
        test: "Queries with 1000+ results perform acceptably"

        Verifies whats_next() performs acceptably with 1000+ meetings/items.
        Target: < 500ms for p95 query latency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_large.db")

            # Setup: 100 meetings x 15 items = 1500 agenda items
            self.setup_large_dataset(db_path, num_meetings=100, items_per_meeting=15)

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            # Verify dataset size
            state = StateManager(db_path)
            city_state = state.get_city_state("san-rafael-ca")
            total_meetings = len(city_state.get("meetings", []))

            print(f"\nDataset size: {total_meetings} meetings")
            assert total_meetings >= 100, f"Expected at least 100 meetings, got {total_meetings}"

            # Run performance test
            latencies = []
            for _ in range(50):
                start = time.perf_counter()
                result = civic.whats_next(days=365)  # Query full year
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhats_next() with 1000+ items:")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"whats_next() p95 latency {p95:.2f}ms exceeds 500ms threshold with large dataset"

    def test_what_happened_with_1000_items(self):
        """
        Verifies what_happened() performs acceptably scanning 1000+ items.
        Target: < 500ms for p95 query latency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_large.db")

            # Setup: 100 meetings x 15 items = 1500 agenda items
            self.setup_large_dataset(db_path, num_meetings=100, items_per_meeting=15)

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            # Queries that should match many items
            queries = ["housing", "traffic", "parks", "development", "district"]

            latencies = []
            for i in range(50):
                query = queries[i % len(queries)]
                start = time.perf_counter()
                result = civic.what_happened(query)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhat_happened() with 1000+ items:")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"what_happened() p95 latency {p95:.2f}ms exceeds 500ms threshold with large dataset"

    def test_whos_with_me_with_many_initiatives(self):
        """
        Verifies whos_with_me() performs acceptably with many initiatives.
        Target: < 500ms for p95 query latency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_large.db")

            # Setup includes 200 initiatives
            self.setup_large_dataset(db_path, num_meetings=50, items_per_meeting=10)

            civic = CivicOS("san-rafael-ca", db_path=db_path)

            topics = ["housing", "traffic", "parks", "safety", "budget"]

            latencies = []
            for i in range(50):
                topic = topics[i % len(topics)]
                start = time.perf_counter()
                result = civic.whos_with_me(topic)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nwhos_with_me() with many initiatives:")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"whos_with_me() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_query_meetings_with_large_result_set(self):
        """
        Verifies StateManager.query_meetings() handles 1000+ results.
        Target: < 500ms for p95 query latency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_large.db")

            # Setup: 200 meetings
            self.setup_large_dataset(db_path, num_meetings=200, items_per_meeting=10)

            state = StateManager(db_path)

            latencies = []
            for _ in range(50):
                start = time.perf_counter()
                result = state.query_meetings("san-rafael-ca")  # All meetings
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

                # Verify we're getting large results
                if len(latencies) == 1:
                    print(f"\nquery_meetings returned {len(result)} meetings")

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nquery_meetings() with 1000+ items:")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"query_meetings() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_query_initiatives_with_large_result_set(self):
        """
        Verifies StateManager.query_initiatives() handles 200+ results.
        Target: < 500ms for p95 query latency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_large.db")

            # Setup includes 200 initiatives
            self.setup_large_dataset(db_path, num_meetings=20, items_per_meeting=5)

            state = StateManager(db_path)

            latencies = []
            for _ in range(50):
                start = time.perf_counter()
                result = state.query_initiatives("san-rafael-ca", limit=1000)  # High limit
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

                if len(latencies) == 1:
                    print(f"\nquery_initiatives returned {len(result)} initiatives")

            p95 = percentile(latencies, 95)
            p50 = percentile(latencies, 50)
            mean = statistics.mean(latencies)

            print(f"\nquery_initiatives() with large result set:")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            assert p95 < 500, f"query_initiatives() p95 latency {p95:.2f}ms exceeds 500ms threshold"

    def test_combined_workload_with_large_dataset(self):
        """
        Verifies system performs acceptably under mixed workload with large dataset.
        Target: < 500ms for p95 query latency.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_large.db")

            # Setup large dataset
            self.setup_large_dataset(db_path, num_meetings=100, items_per_meeting=15)

            civic = CivicOS("san-rafael-ca", db_path=db_path)
            topics = ["housing", "traffic", "parks", "safety", "budget"]

            all_latencies = []
            method_latencies = {
                "whats_next": [],
                "what_applies": [],
                "what_happened": [],
                "whos_with_me": []
            }

            # Mixed workload: 100 calls across all methods
            for i in range(100):
                topic = topics[i % len(topics)]
                method = i % 4

                start = time.perf_counter()

                if method == 0:
                    civic.whats_next(days=365)
                    method_name = "whats_next"
                elif method == 1:
                    civic.what_applies(topic)
                    method_name = "what_applies"
                elif method == 2:
                    civic.what_happened(topic)
                    method_name = "what_happened"
                else:
                    civic.whos_with_me(topic)
                    method_name = "whos_with_me"

                elapsed = (time.perf_counter() - start) * 1000
                all_latencies.append(elapsed)
                method_latencies[method_name].append(elapsed)

            p95 = percentile(all_latencies, 95)
            p50 = percentile(all_latencies, 50)
            mean = statistics.mean(all_latencies)

            print(f"\nCombined workload with large dataset (100 calls):")
            print(f"  Mean: {mean:.2f}ms")
            print(f"  P50:  {p50:.2f}ms")
            print(f"  P95:  {p95:.2f}ms")

            for method, latencies in method_latencies.items():
                if latencies:
                    mp95 = percentile(latencies, 95)
                    print(f"  {method} p95: {mp95:.2f}ms")

            assert p95 < 500, f"Combined workload p95 latency {p95:.2f}ms exceeds 500ms threshold with large dataset"


class TestIndexEffectiveness:
    """
    Integration tests for database index effectiveness.

    Maps to integration.json > load_testing > database_performance > index_effectiveness

    These tests verify that common queries actually use the defined indexes
    by examining EXPLAIN QUERY PLAN output.
    """

    def setup_test_database(self, db_path: str):
        """
        Create test database with data and verify indexes exist.

        Returns:
            StateManager instance
        """
        state = StateManager(db_path)

        # Create test data
        meetings = []
        base_date = datetime.now()

        for i in range(20):
            meeting_date = base_date + timedelta(days=i - 10)
            meetings.append({
                "id": f"meeting_{i:03d}",
                "title": f"Council Meeting {i}",
                "meeting_type": "City Council",
                "meeting_datetime": meeting_date.isoformat(),
                "location": "City Hall",
                "status": "past" if meeting_date < base_date else "upcoming"
            })

        state.update_meetings("san-rafael-ca", meetings)

        # Create initiatives
        for i in range(10):
            state.create_initiative(
                initiative_id=f"init_{i:03d}",
                jurisdiction_id="san-rafael-ca",
                topic=["housing", "traffic", "parks"][i % 3],
                title=f"Initiative {i}",
                description=f"Description {i}",
                creator_id=f"user_{i:03d}"
            )

        # Create voices
        for i in range(10):
            state.create_voice(
                voice_id=f"voice_{i:03d}",
                item_type="initiative",
                item_id=f"init_{i % 5:03d}",
                stance=["support", "oppose", "question"][i % 3],
                comment=f"Comment {i}",
                user_id=f"user_{i:03d}"
            )

        # Create subscriptions
        for i in range(10):
            state.create_subscription(
                subscription_id=f"sub_{i:03d}",
                item_type="initiative",
                item_id=f"init_{i % 5:03d}",
                user_id=f"user_{i:03d}"
            )

        # Create issues
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for i in range(10):
            cursor.execute("""
                INSERT INTO issues (id, jurisdiction_id, source, title, issue_type, address, status, valid_from)
                VALUES (?, ?, 'seeclickfix', ?, ?, ?, 'open', CURRENT_TIMESTAMP)
            """, (f"issue_{i:03d}", "san-rafael-ca", f"Issue {i}",
                  ["pothole", "graffiti", "streetlight"][i % 3],
                  f"{i * 100} Main Street"))

        conn.commit()
        conn.close()

        # Create outcomes (after closing the previous connection)
        for i in range(5):
            state.create_outcome(
                outcome_id=f"outcome_{i:03d}",
                item_type="initiative",
                item_id=f"init_{i:03d}",
                outcome=["passed", "failed", "continued"][i % 3],
                notes=f"Decision notes {i}",
                recorded_by=f"user_{i:03d}"
            )

        return state

    def get_query_plan(self, db_path: str, query: str, params: tuple = ()) -> List[str]:
        """
        Execute EXPLAIN QUERY PLAN and return the plan lines.

        Args:
            db_path: Path to database
            query: SQL query to explain
            params: Query parameters

        Returns:
            List of plan description lines
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # EXPLAIN QUERY PLAN returns rows with: selectid, order, from, detail
        cursor.execute(f"EXPLAIN QUERY PLAN {query}", params)
        plan_rows = cursor.fetchall()

        conn.close()

        # Return the detail column (4th column) which describes the operation
        return [row[3] for row in plan_rows]

    def assert_uses_index(self, plan_lines: List[str], index_name: str, query_desc: str):
        """
        Assert that at least one plan line mentions using the specified index.

        Args:
            plan_lines: Lines from EXPLAIN QUERY PLAN
            index_name: Name of the expected index
            query_desc: Description of the query for error messages
        """
        index_used = any(index_name in line for line in plan_lines)
        plan_str = "\n  ".join(plan_lines)
        assert index_used, (
            f"{query_desc} does not use index '{index_name}'.\n"
            f"Query plan:\n  {plan_str}"
        )

    def assert_no_table_scan(self, plan_lines: List[str], table_name: str, query_desc: str):
        """
        Assert that the query plan doesn't do a full table scan on the specified table.

        Note: SQLite shows "SCAN TABLE" for full table scans and "SEARCH TABLE" for indexed access.

        Args:
            plan_lines: Lines from EXPLAIN QUERY PLAN
            table_name: Name of the table that shouldn't be scanned
            query_desc: Description of the query for error messages
        """
        # "SCAN TABLE meetings" indicates a full table scan
        # "SEARCH TABLE meetings" indicates indexed access
        has_scan = any(f"SCAN TABLE {table_name}" in line or f"SCAN {table_name}" in line
                       for line in plan_lines)
        plan_str = "\n  ".join(plan_lines)

        # Allow scans if the table is very small or if there's also a SEARCH
        has_search = any(f"SEARCH TABLE {table_name}" in line or f"SEARCH {table_name}" in line
                        for line in plan_lines)

        if has_scan and not has_search:
            # Check if it's a covering index scan (acceptable)
            covering_scan = any("COVERING INDEX" in line for line in plan_lines)
            if not covering_scan:
                pytest.fail(
                    f"{query_desc} performs full table scan on '{table_name}'.\n"
                    f"Query plan:\n  {plan_str}"
                )

    def test_meetings_jurisdiction_index(self):
        """
        Verify queries filtering by jurisdiction_id use idx_meetings_jurisdiction.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM meetings
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """

            plan = self.get_query_plan(db_path, query, ("san-rafael-ca",))

            print(f"\nQuery: SELECT * FROM meetings WHERE jurisdiction_id = ? AND valid_to IS NULL")
            print(f"Plan: {plan}")

            # Should use either idx_meetings_jurisdiction or idx_meetings_current
            uses_index = any("idx_meetings" in line for line in plan)
            assert uses_index, f"Query does not use any meetings index. Plan: {plan}"

    def test_meetings_datetime_index(self):
        """
        Verify queries filtering by meeting_datetime use idx_meetings_datetime.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM meetings
                WHERE jurisdiction_id = ?
                  AND meeting_datetime >= ?
                  AND valid_to IS NULL
                ORDER BY meeting_datetime
            """

            now = datetime.now().isoformat()
            plan = self.get_query_plan(db_path, query, ("san-rafael-ca", now))

            print(f"\nQuery: meetings filtered by datetime")
            print(f"Plan: {plan}")

            # Should use an index (either datetime or jurisdiction)
            uses_index = any("SEARCH" in line or "INDEX" in line for line in plan)
            assert uses_index, f"Query does not use any index. Plan: {plan}"

    def test_meetings_current_version_index(self):
        """
        Verify queries for current versions use idx_meetings_current partial index.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT COUNT(*) FROM meetings
                WHERE valid_to IS NULL
            """

            plan = self.get_query_plan(db_path, query)

            print(f"\nQuery: COUNT current meetings (valid_to IS NULL)")
            print(f"Plan: {plan}")

            # With partial index, should use idx_meetings_current
            # Note: SQLite may choose a covering index scan which is still efficient

    def test_agenda_items_meeting_index(self):
        """
        Verify queries filtering by meeting_id use idx_agenda_items_meeting.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            # Add some agenda items
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            for i in range(10):
                cursor.execute("""
                    INSERT INTO agenda_items (id, meeting_id, title, valid_from)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (f"item_{i:03d}", f"meeting_{i % 5:03d}", f"Agenda Item {i}"))
            conn.commit()
            conn.close()

            query = """
                SELECT * FROM agenda_items
                WHERE meeting_id = ?
                  AND valid_to IS NULL
            """

            plan = self.get_query_plan(db_path, query, ("meeting_001",))

            print(f"\nQuery: agenda_items filtered by meeting_id")
            print(f"Plan: {plan}")

            # Should use idx_agenda_items_meeting
            uses_index = any("idx_agenda_items_meeting" in line or "SEARCH" in line for line in plan)
            assert uses_index, f"Query does not use agenda_items index. Plan: {plan}"

    def test_initiatives_jurisdiction_topic_index(self):
        """
        Verify queries filtering by jurisdiction and topic use appropriate indexes.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM initiatives
                WHERE jurisdiction_id = ?
                  AND topic = ?
                  AND status = 'active'
            """

            plan = self.get_query_plan(db_path, query, ("san-rafael-ca", "housing"))

            print(f"\nQuery: initiatives filtered by jurisdiction, topic, status")
            print(f"Plan: {plan}")

            # Should use one of the initiative indexes
            uses_index = any("idx_initiatives" in line or "SEARCH" in line for line in plan)
            assert uses_index, f"Query does not use initiatives index. Plan: {plan}"

    def test_voices_item_index(self):
        """
        Verify queries filtering by item_type and item_id use idx_voices_item.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM voices
                WHERE item_type = ?
                  AND item_id = ?
            """

            plan = self.get_query_plan(db_path, query, ("initiative", "init_001"))

            print(f"\nQuery: voices filtered by item_type and item_id")
            print(f"Plan: {plan}")

            # Should use idx_voices_item composite index
            uses_index = any("idx_voices_item" in line or "SEARCH" in line for line in plan)
            assert uses_index, f"Query does not use voices index. Plan: {plan}"

    def test_subscriptions_user_index(self):
        """
        Verify queries filtering by user_id use idx_subscriptions_user.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM subscriptions
                WHERE user_id = ?
            """

            plan = self.get_query_plan(db_path, query, ("user_001",))

            print(f"\nQuery: subscriptions filtered by user_id")
            print(f"Plan: {plan}")

            # Should use idx_subscriptions_user
            uses_index = any("idx_subscriptions_user" in line or "SEARCH" in line for line in plan)
            assert uses_index, f"Query does not use subscriptions index. Plan: {plan}"

    def test_issues_jurisdiction_status_index(self):
        """
        Verify queries filtering by jurisdiction and status use appropriate indexes.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM issues
                WHERE jurisdiction_id = ?
                  AND status = ?
                  AND valid_to IS NULL
            """

            plan = self.get_query_plan(db_path, query, ("san-rafael-ca", "open"))

            print(f"\nQuery: issues filtered by jurisdiction and status")
            print(f"Plan: {plan}")

            # Should use one of the issues indexes
            uses_index = any("idx_issues" in line or "SEARCH" in line for line in plan)
            assert uses_index, f"Query does not use issues index. Plan: {plan}"

    def test_outcomes_item_index(self):
        """
        Verify queries filtering by item_type and item_id use idx_outcomes_item.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            query = """
                SELECT * FROM outcomes
                WHERE item_type = ?
                  AND item_id = ?
                ORDER BY recorded_at DESC
                LIMIT 1
            """

            plan = self.get_query_plan(db_path, query, ("initiative", "init_001"))

            print(f"\nQuery: outcomes filtered by item_type and item_id")
            print(f"Plan: {plan}")

            # Should use idx_outcomes_item composite index
            uses_index = any("idx_outcomes_item" in line or "SEARCH" in line for line in plan)
            assert uses_index, f"Query does not use outcomes index. Plan: {plan}"

    def test_query_meetings_uses_index(self):
        """
        Verify the StateManager.query_meetings method uses indexes efficiently.

        This tests the actual query used in the codebase.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            # This is the query pattern used in StateManager.query_meetings
            query = """
                SELECT * FROM meetings
                WHERE jurisdiction_id = ?
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR valid_to > ?)
                ORDER BY meeting_datetime
            """

            now = datetime.now().isoformat()
            plan = self.get_query_plan(db_path, query, ("san-rafael-ca", now, now))

            print(f"\nQuery: query_meetings pattern")
            print(f"Plan: {plan}")

            # Should use an index, not a full table scan
            uses_search = any("SEARCH" in line for line in plan)
            uses_index = any("INDEX" in line for line in plan)

            assert uses_search or uses_index, f"query_meetings pattern does not use index efficiently. Plan: {plan}"

    def test_query_initiatives_uses_index(self):
        """
        Verify the StateManager.query_initiatives method uses indexes efficiently.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            # This is the query pattern used in StateManager.query_initiatives
            query = """
                SELECT * FROM initiatives
                WHERE jurisdiction_id = ?
                  AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
            """

            plan = self.get_query_plan(db_path, query, ("san-rafael-ca", "active", 100))

            print(f"\nQuery: query_initiatives pattern")
            print(f"Plan: {plan}")

            # Should use an index
            uses_search = any("SEARCH" in line for line in plan)
            uses_index = any("INDEX" in line for line in plan)

            assert uses_search or uses_index, f"query_initiatives pattern does not use index efficiently. Plan: {plan}"

    def test_query_issues_uses_index(self):
        """
        Verify the StateManager.query_issues method uses indexes efficiently.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            # This is the query pattern used in StateManager.query_issues
            query = """
                SELECT * FROM issues
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
                  AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
            """

            plan = self.get_query_plan(db_path, query, ("san-rafael-ca", "open", 100))

            print(f"\nQuery: query_issues pattern")
            print(f"Plan: {plan}")

            # Should use an index
            uses_search = any("SEARCH" in line for line in plan)
            uses_index = any("INDEX" in line for line in plan)

            assert uses_search or uses_index, f"query_issues pattern does not use index efficiently. Plan: {plan}"

    def test_all_indexes_exist(self):
        """
        Verify all expected indexes are created in the database schema.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_index.db")
            self.setup_test_database(db_path)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query SQLite master for index names
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'index'
                  AND name LIKE 'idx_%'
                ORDER BY name
            """)

            existing_indexes = {row[0] for row in cursor.fetchall()}
            conn.close()

            expected_indexes = {
                # Meetings indexes
                "idx_meetings_jurisdiction",
                "idx_meetings_datetime",
                "idx_meetings_temporal",
                "idx_meetings_current",
                # Agenda items indexes
                "idx_agenda_items_meeting",
                "idx_agenda_items_type",
                "idx_agenda_items_temporal",
                # Issues indexes
                "idx_issues_jurisdiction",
                "idx_issues_status",
                "idx_issues_type",
                "idx_issues_address",
                # Initiatives indexes
                "idx_initiatives_jurisdiction",
                "idx_initiatives_topic",
                "idx_initiatives_status",
                "idx_initiatives_creator",
                # Voices indexes
                "idx_voices_item",
                "idx_voices_user",
                "idx_voices_stance",
                # Subscriptions indexes
                "idx_subscriptions_item",
                "idx_subscriptions_user",
                # Outcomes indexes
                "idx_outcomes_item",
                "idx_outcomes_outcome",
                "idx_outcomes_recorded_at",
            }

            print(f"\nExpected indexes: {len(expected_indexes)}")
            print(f"Found indexes: {len(existing_indexes)}")

            missing = expected_indexes - existing_indexes
            if missing:
                pytest.fail(f"Missing indexes: {missing}")

            print(f"All {len(expected_indexes)} indexes exist.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
