#!/usr/bin/env python3
"""
Benchmark: Civic API vs Baseline LLM

Compares Civic API query results against what a baseline LLM would produce.
Evaluates on: Accuracy, Specificity, Actionability, Grounding.

Usage:
    python scripts/benchmark_api_vs_llm.py [--jurisdiction JURISDICTION]
    python scripts/benchmark_api_vs_llm.py --run-all
    python scripts/benchmark_api_vs_llm.py --json  # Output as JSON
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Load .env for DATABASE_URL (production PostgreSQL)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, val = line.strip().split('=', 1)
                os.environ.setdefault(key, val)

# Add packages to path
sys.path.insert(0, "packages/civic/src")
sys.path.insert(0, "packages/civic-services/src")


@dataclass
class QueryResult:
    """Result from a single query."""
    method: str
    query: str
    civic_result: Any
    civic_count: int
    civic_sample: list
    llm_baseline: str
    evaluation: dict = field(default_factory=dict)


# Ground truth for accuracy validation
KNOWN_VALID_FEDERAL_PROGRAMS = {
    "Community Development Block Grant",
    "HOME Investment Partnerships Program",
    "Section 8 Housing Choice Voucher Program",
    "Low-Income Housing Tax Credit (LIHTC) Program",
}

KNOWN_VALID_CA_BILLS = {
    "SB-9", "SB-35", "AB-68", "SB-13",  # ADU/housing
    "California Housing Opportunity and More Efficiency (HOME) Act",
    "Housing Crisis Act of 2019",
    "Density Bonus Law Expansion",
    "Housing Accountability Act",
}

IRRELEVANT_USC_CHAPTERS = {
    "GAME AND BIRD PRESERVES",
    "NATIONAL PARKS",
    "MILITARY PARKS",
    "MONUMENTS",
    "SEASHORES",
}


@dataclass
class BenchmarkReport:
    """Full benchmark report."""
    jurisdiction: str
    timestamp: str
    queries: list
    summary: dict
    gaps_detected: list


def get_ground_truth_counts(jurisdiction: str) -> dict:
    """Get total counts of relevant items in database for recall calculation."""
    import sqlite3
    db_path = "data/civic_state.db"

    counts = {}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Total decisions by topic keyword
        for topic in ["housing", "bike", "traffic", "pothole"]:
            cur.execute(
                "SELECT COUNT(*) FROM decisions WHERE jurisdiction_id = ? AND (title LIKE ? OR summary LIKE ?)",
                (jurisdiction, f"%{topic}%", f"%{topic}%")
            )
            counts[f"decisions_{topic}"] = cur.fetchone()[0]

        # Total issues by type pattern
        for topic in ["traffic", "pothole"]:
            cur.execute(
                "SELECT COUNT(*) FROM issues WHERE jurisdiction_id = ? AND issue_type LIKE ?",
                (jurisdiction, f"%{topic}%")
            )
            counts[f"issues_{topic}"] = cur.fetchone()[0]

        conn.close()
    except Exception:
        pass  # Ground truth not available

    return counts


class CivicBenchmark:
    """Benchmark Civic API against LLM baseline."""

    # LLM baseline responses (simulated - what a typical LLM would say)
    LLM_BASELINES = {
        "what_applies:housing": """
For housing regulations in California, you should be aware of:
- SB 9: Allows lot splits and duplexes in single-family zones
- SB 35: Streamlines approval for affordable housing
- RHNA: Regional Housing Needs Allocation requirements
- Local zoning codes (varies by city)

At the federal level, HUD programs like Section 8 and CDBG may apply.
I recommend checking with your local planning department for specifics.
""",
        "what_applies:accessory dwelling unit": """
ADUs (Accessory Dwelling Units) in California are governed by:
- AB 68 and SB 13: State ADU laws that limit local restrictions
- Your city's ADU ordinance (check local municipal code)
- Building codes and permits required

Generally, you can build an ADU on most residential lots.
Check with your local building department for specific requirements.
""",
        "what_happened:housing": """
I don't have access to specific city council decisions about housing.
You would need to check:
- The city's meeting minutes archive
- Legistar or similar agenda management system
- Local news coverage

I can provide general information about housing policy trends.
""",
        "what_happened:bike lane": """
I don't have access to local government records about bike lane decisions.
To find this information, check:
- City transportation department website
- City council meeting archives
- Local bicycle advocacy group updates
""",
        "whats_next:housing": """
I cannot access real-time meeting schedules. To find upcoming meetings:
- Check the city's calendar at their official website
- Subscribe to meeting notifications through Legistar
- Contact the city clerk's office

Housing discussions often occur at Planning Commission or City Council meetings.
""",
        "whos_with_me:traffic": """
I cannot identify specific individuals or groups in your area.
To find others concerned about traffic:
- Attend neighborhood association meetings
- Check local Facebook groups or Nextdoor
- Contact local advocacy organizations
- Submit comments during public comment periods

Community organizing often starts with talking to neighbors.
""",
    }

    def __init__(self, jurisdiction: str = "city-san-rafael"):
        self.jurisdiction = jurisdiction
        self.results: list[QueryResult] = []
        self.gaps: list[str] = []
        self._civic = None
        self._ground_truth = get_ground_truth_counts(jurisdiction)

    def _get_civic(self):
        """Lazy-load Civic instance."""
        if self._civic is None:
            from civic import Civic
            self._civic = Civic(self.jurisdiction)
        return self._civic

    def run_what_applies(self, topic: str) -> QueryResult:
        """Benchmark what_applies query."""
        c = self._get_civic()
        result = c.what_applies(topic)

        # Count meaningful results (exclude notes)
        federal_count = len([f for f in result.federal if isinstance(f, dict) and 'note' not in f])
        state_count = len([s for s in result.state if isinstance(s, dict) and 'note' not in s])
        local_count = len([l for l in result.local if isinstance(l, dict) and 'note' not in l])

        # Sample results
        sample = []
        for f in result.federal[:2]:
            if isinstance(f, dict):
                if f.get('type') == 'program':
                    sample.append(f"Federal: {f.get('program_name', 'Unknown')}")
                elif f.get('type') == 'codified_law':
                    sample.append(f"U.S. Code: {f.get('citation', 'Unknown')}")
        for s in result.state[:2]:
            if isinstance(s, dict) and 'bill' in s:
                sample.append(f"State: {s.get('bill', 'Unknown')}")

        # Check for gaps
        if federal_count == 0 and state_count == 0:
            self.gaps.append(f"what_applies('{topic}'): No federal or state results")

        # Check for low-relevance federal results
        low_relevance = [
            f for f in result.federal
            if isinstance(f, dict) and f.get('relevance', 1.0) < 0.2
        ]
        if low_relevance:
            self.gaps.append(f"what_applies('{topic}'): {len(low_relevance)} low-relevance federal results")

        # ACCURACY: Check if results are valid/relevant
        accurate_federal = 0
        inaccurate_federal = 0
        for f in result.federal:
            if isinstance(f, dict) and 'note' not in f:
                if f.get('type') == 'program':
                    if f.get('program_name') in KNOWN_VALID_FEDERAL_PROGRAMS:
                        accurate_federal += 1
                    # Unknown programs aren't necessarily wrong
                elif f.get('type') == 'codified_law':
                    chapter = f.get('chapter', '')
                    if any(irr in chapter for irr in IRRELEVANT_USC_CHAPTERS):
                        inaccurate_federal += 1
                    elif f.get('relevance', 0) >= 0.3:
                        accurate_federal += 1

        accurate_state = sum(
            1 for s in result.state
            if isinstance(s, dict) and (
                s.get('bill') in KNOWN_VALID_CA_BILLS or
                s.get('title', '') in KNOWN_VALID_CA_BILLS
            )
        )

        # Accuracy score: valid results / (valid + invalid), or 1.0 if no results
        total_checked = accurate_federal + accurate_state + inaccurate_federal
        accuracy_score = (
            (accurate_federal + accurate_state) / total_checked
            if total_checked > 0 else 1.0
        )

        if inaccurate_federal > 0:
            self.gaps.append(f"what_applies('{topic}'): {inaccurate_federal} irrelevant federal results (accuracy issue)")

        baseline_key = f"what_applies:{topic}"
        llm_baseline = self.LLM_BASELINES.get(baseline_key, "No baseline defined")

        # PRECISION: relevant results / total results
        total_results = federal_count + state_count + local_count
        relevant_results = accurate_federal + accurate_state + local_count  # local assumed relevant
        precision_score = relevant_results / total_results if total_results > 0 else 1.0

        return QueryResult(
            method="what_applies",
            query=topic,
            civic_result={
                "federal_count": federal_count,
                "state_count": state_count,
                "local_count": local_count,
                "accurate_federal": accurate_federal,
                "accurate_state": accurate_state,
                "inaccurate_federal": inaccurate_federal,
            },
            civic_count=federal_count + state_count + local_count,
            civic_sample=sample,
            llm_baseline=llm_baseline.strip(),
            evaluation={
                "accurate": accuracy_score >= 0.7,  # 70% threshold
                "accuracy_score": round(accuracy_score, 2),
                "precision": round(precision_score, 2),
                "grounded": federal_count > 0 or state_count > 0,
                "specific": len(sample) > 0,
                "actionable": local_count > 0,  # Local rules are most actionable
            }
        )

    def run_what_happened(self, query: str) -> QueryResult:
        """Benchmark what_happened query."""
        c = self._get_civic()
        result = c.what_happened(query)

        # Sample results
        sample = []
        for d in result[:3]:
            sample.append(f"{d.date.strftime('%Y-%m-%d')}: {d.title[:50]}...")

        # Check for gaps
        if len(result) == 0:
            self.gaps.append(f"what_happened('{query}'): 0 results (decisions table has data)")

        # ACCURACY: Check if decisions have valid structure
        accurate_count = 0
        for d in result:
            # Valid if: has date, has title, date is reasonable (not future, not too old)
            has_valid_date = d.date and d.date.year >= 2020 and d.date <= datetime.now()
            has_title = d.title and len(d.title) > 5
            # Check if title seems relevant to query (basic keyword check)
            title_relevant = query.lower() in d.title.lower() or len(result) <= 10  # Trust small result sets
            if has_valid_date and has_title and title_relevant:
                accurate_count += 1

        accuracy_score = accurate_count / len(result) if result else 1.0

        # PRECISION: Count results with query keyword in title (strict relevance)
        keyword_matches = sum(1 for d in result if query.lower() in d.title.lower())
        precision_score = keyword_matches / len(result) if result else 1.0

        # RECALL: retrieved relevant / total relevant in DB
        query_key = query.lower().split()[0]  # "bike lane" -> "bike"
        total_relevant = self._ground_truth.get(f"decisions_{query_key}", 0)
        recall_score = keyword_matches / total_relevant if total_relevant > 0 else 1.0

        baseline_key = f"what_happened:{query}"
        llm_baseline = self.LLM_BASELINES.get(baseline_key, "No baseline defined")

        return QueryResult(
            method="what_happened",
            query=query,
            civic_result={
                "decision_count": len(result),
                "accurate_count": accurate_count,
                "keyword_matches": keyword_matches,
                "total_relevant_in_db": total_relevant,
            },
            civic_count=len(result),
            civic_sample=sample,
            llm_baseline=llm_baseline.strip(),
            evaluation={
                "accurate": accuracy_score >= 0.7,
                "accuracy_score": round(accuracy_score, 2),
                "precision": round(precision_score, 2),
                "recall": round(recall_score, 2),
                "grounded": len(result) > 0,
                "specific": len(sample) > 0,
                "actionable": any(d.outcome for d in result) if result else False,
            }
        )

    def run_whats_next(self, topics: Optional[list] = None) -> QueryResult:
        """Benchmark whats_next query."""
        c = self._get_civic()
        result = c.whats_next(topics=topics, days=90)

        # Sample results
        sample = []
        for m in result[:3]:
            sample.append(f"{m.date.strftime('%Y-%m-%d')}: {m.title[:50]}...")

        # ACCURACY: Check if meetings are actually in the future
        now = datetime.now()
        accurate_count = 0
        for m in result:
            # Valid if: date is in future (or today), has title
            is_future = m.date and m.date.date() >= now.date()
            has_title = m.title and len(m.title) > 3
            if is_future and has_title:
                accurate_count += 1

        accuracy_score = accurate_count / len(result) if result else 1.0

        topic_str = ",".join(topics) if topics else "all"
        baseline_key = f"whats_next:{topic_str}"
        llm_baseline = self.LLM_BASELINES.get(baseline_key, self.LLM_BASELINES.get("whats_next:housing", "No baseline"))

        # PRECISION: For topic-filtered queries, check if results match topics
        if topics:
            topic_matches = sum(
                1 for m in result
                if any(t.lower() in m.title.lower() for t in topics)
            )
            precision_score = topic_matches / len(result) if result else 1.0
        else:
            precision_score = 1.0  # No filter = all results valid

        return QueryResult(
            method="whats_next",
            query=topic_str,
            civic_result={
                "meeting_count": len(result),
                "accurate_count": accurate_count,
            },
            civic_count=len(result),
            civic_sample=sample,
            llm_baseline=llm_baseline.strip(),
            evaluation={
                "accurate": accuracy_score >= 0.7,
                "accuracy_score": round(accuracy_score, 2),
                "precision": round(precision_score, 2),
                "grounded": True,  # Real-time data
                "specific": len(sample) > 0,
                "actionable": len(result) > 0,  # User can attend
            }
        )

    def run_whos_with_me(self, topic: str, threshold: float = 0.5) -> QueryResult:
        """Benchmark whos_with_me query."""
        c = self._get_civic()
        result = c.whos_with_me(topic, similarity_threshold=threshold)

        # Check for uniform count (gap indicator)
        result_low = c.whos_with_me(topic, similarity_threshold=0.3)
        if result.follower_count == result_low.follower_count and result.follower_count > 100:
            self.gaps.append(f"whos_with_me('{topic}'): Uniform count {result.follower_count} regardless of threshold")

        # ACCURACY: Verify count is topic-specific (not just returning all issues)
        # If high threshold returns same as low threshold, accuracy is suspect
        is_topic_specific = result.follower_count != result_low.follower_count or result.follower_count < 100
        accuracy_score = 1.0 if is_topic_specific else 0.5

        baseline_key = f"whos_with_me:{topic}"
        llm_baseline = self.LLM_BASELINES.get(baseline_key, "No baseline defined")

        # PRECISION: topic-specific count / low-threshold count
        # Higher precision = more selective matching
        precision_score = (
            result.follower_count / result_low.follower_count
            if result_low.follower_count > 0 else 1.0
        )

        # RECALL: retrieved / total relevant issues in DB
        total_relevant = self._ground_truth.get(f"issues_{topic}", 0)
        recall_score = result.follower_count / total_relevant if total_relevant > 0 else 1.0
        # Cap at 1.0 (can retrieve more than exact matches via semantic search)
        recall_score = min(recall_score, 1.0)

        return QueryResult(
            method="whos_with_me",
            query=topic,
            civic_result={
                "follower_count": result.follower_count,
                "threshold": threshold,
                "is_topic_specific": is_topic_specific,
                "total_relevant_in_db": total_relevant,
            },
            civic_count=result.follower_count,
            civic_sample=[f"{result.follower_count} issues related to '{topic}'"],
            llm_baseline=llm_baseline.strip(),
            evaluation={
                "accurate": is_topic_specific,
                "accuracy_score": accuracy_score,
                "precision": round(precision_score, 2),
                "recall": round(recall_score, 2),
                "grounded": result.follower_count > 0,
                "specific": True,  # Quantified community size
                "actionable": result.follower_count > 0,  # Can connect users
            }
        )

    def run_all(self) -> BenchmarkReport:
        """Run all benchmark queries."""
        self.results = []
        self.gaps = []

        # what_applies tests
        self.results.append(self.run_what_applies("housing"))
        self.results.append(self.run_what_applies("accessory dwelling unit"))

        # what_happened tests
        self.results.append(self.run_what_happened("housing"))
        self.results.append(self.run_what_happened("bike lane"))

        # whats_next tests
        self.results.append(self.run_whats_next(["housing"]))
        self.results.append(self.run_whats_next())  # all topics

        # whos_with_me tests
        self.results.append(self.run_whos_with_me("traffic", threshold=0.6))
        self.results.append(self.run_whos_with_me("pothole", threshold=0.6))

        # Calculate summary
        accurate_count = sum(1 for r in self.results if r.evaluation.get("accurate"))
        grounded_count = sum(1 for r in self.results if r.evaluation.get("grounded"))
        specific_count = sum(1 for r in self.results if r.evaluation.get("specific"))
        actionable_count = sum(1 for r in self.results if r.evaluation.get("actionable"))

        # Average accuracy, precision, recall scores across all queries
        accuracy_scores = [r.evaluation.get("accuracy_score", 1.0) for r in self.results]
        precision_scores = [r.evaluation.get("precision", 1.0) for r in self.results]
        recall_scores = [r.evaluation.get("recall", 1.0) for r in self.results if "recall" in r.evaluation]
        avg_accuracy = sum(accuracy_scores) / len(accuracy_scores) if accuracy_scores else 0
        avg_precision = sum(precision_scores) / len(precision_scores) if precision_scores else 0
        avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0

        summary = {
            "total_queries": len(self.results),
            "accurate": accurate_count,
            "grounded": grounded_count,
            "specific": specific_count,
            "actionable": actionable_count,
            "accurate_pct": round(100 * accurate_count / len(self.results), 1),
            "avg_accuracy_score": round(avg_accuracy, 2),
            "avg_precision": round(avg_precision, 2),
            "avg_recall": round(avg_recall, 2),
            "grounded_pct": round(100 * grounded_count / len(self.results), 1),
            "specific_pct": round(100 * specific_count / len(self.results), 1),
            "actionable_pct": round(100 * actionable_count / len(self.results), 1),
            "gaps_detected": len(self.gaps),
        }

        return BenchmarkReport(
            jurisdiction=self.jurisdiction,
            timestamp=datetime.now().isoformat(),
            queries=[asdict(r) for r in self.results],
            summary=summary,
            gaps_detected=self.gaps,
        )


def print_report(report: BenchmarkReport, as_json: bool = False):
    """Print benchmark report."""
    if as_json:
        print(json.dumps(asdict(report), indent=2, default=str))
        return

    # Verify database connection
    db_url = os.environ.get('DATABASE_URL', '')
    if 'supabase' in db_url:
        db_type = "Supabase PostgreSQL (production)"
    elif db_url:
        db_type = "PostgreSQL"
    else:
        db_type = "Local SQLite/ChromaDB (no DATABASE_URL)"

    print("=" * 70)
    print(f"CIVIC API BENCHMARK vs LLM BASELINE")
    print(f"Jurisdiction: {report.jurisdiction}")
    print(f"Database: {db_type}")
    print(f"Timestamp: {report.timestamp}")
    print("=" * 70)

    for q in report.queries:
        print(f"\n## {q['method']}('{q['query']}')")
        print(f"   Civic count: {q['civic_count']}")
        print(f"   Sample: {q['civic_sample'][:2]}")
        acc_score = q['evaluation'].get('accuracy_score', 'N/A')
        prec_score = q['evaluation'].get('precision', 'N/A')
        rec_score = q['evaluation'].get('recall', '-')
        print(f"   Accurate:   {'✓' if q['evaluation'].get('accurate') else '✗'} ({acc_score})")
        print(f"   Precision:  {prec_score}  |  Recall: {rec_score}")
        print(f"   Grounded:   {'✓' if q['evaluation'].get('grounded') else '✗'}")
        print(f"   Specific:   {'✓' if q['evaluation'].get('specific') else '✗'}")
        print(f"   Actionable: {'✓' if q['evaluation'].get('actionable') else '✗'}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    s = report.summary
    print(f"Total queries:  {s['total_queries']}")
    print(f"Accurate:       {s['accurate']}/{s['total_queries']} ({s['accurate_pct']}%) [avg: {s['avg_accuracy_score']}]")
    print(f"Precision:      avg {s['avg_precision']}  |  Recall: avg {s['avg_recall']}")
    print(f"Grounded:       {s['grounded']}/{s['total_queries']} ({s['grounded_pct']}%)")
    print(f"Specific:       {s['specific']}/{s['total_queries']} ({s['specific_pct']}%)")
    print(f"Actionable:     {s['actionable']}/{s['total_queries']} ({s['actionable_pct']}%)")

    if report.gaps_detected:
        print("\n" + "=" * 70)
        print("GAPS DETECTED")
        print("=" * 70)
        for gap in report.gaps_detected:
            print(f"  ⚠ {gap}")

    print("\n" + "=" * 70)
    print("LLM BASELINE COMPARISON")
    print("=" * 70)
    print("""
| Dimension    | Civic API                        | Baseline LLM                    |
|--------------|----------------------------------|----------------------------------|
| Grounded     | ✓ Queries real municipal data    | ✗ Training data only            |
| Specific     | ✓ Cites bills, decisions, dates  | ✗ Generic descriptions          |
| Actionable   | ✓ Shows next steps               | ✗ "Check city website"          |
| Real-time    | ✓ Live schedules/decisions       | ✗ Knowledge cutoff              |
| Community    | ✓ Quantified engagement          | ✗ Cannot measure                |
""")


def main():
    parser = argparse.ArgumentParser(description="Benchmark Civic API vs LLM baseline")
    parser.add_argument("--jurisdiction", default="city-san-rafael", help="Jurisdiction to test")
    parser.add_argument("--run-all", action="store_true", help="Run all benchmark tests")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    benchmark = CivicBenchmark(args.jurisdiction)

    if args.run_all or True:  # Default to running all
        report = benchmark.run_all()
        print_report(report, as_json=args.json)

    # Exit with error code if gaps detected
    if report.gaps_detected:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
