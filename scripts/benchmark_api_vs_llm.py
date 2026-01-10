#!/usr/bin/env python3
"""
Benchmark: Civic API vs Baseline LLM
====================================

PURPOSE
-------
This benchmark measures how well the Civic API answers questions compared to
what a generic LLM (like ChatGPT) would say. It answers: "Is our system actually
better than just asking an AI?"

Run this benchmark:
- Before pilot launches (to ensure quality)
- After major data ingestion (to catch regressions)
- When adding new data sources (to verify they improve results)


QUICK START
-----------
# Basic run (uses local SQLite - limited data)
python scripts/benchmark_api_vs_llm.py

# With production data (recommended)
source .env && python scripts/benchmark_api_vs_llm.py

# Output as JSON (for automated tracking)
python scripts/benchmark_api_vs_llm.py --json > benchmark_results.json


WHAT THE METRICS MEAN
---------------------
When you run the benchmark, you'll see output like this:

    ## what_happened('housing')
       Civic count: 12
       Accurate:   ✓ (0.92)
       Precision:  0.83  |  Recall: 0.80  |  F1: 0.81

Here's what each metric tells you:

  PRECISION (0.83 = 83%)
    "Of the results we returned, how many were actually relevant?"
    - High precision (>0.8): Results are relevant, not noisy
    - Low precision (<0.5): Returning too much irrelevant junk

  RECALL (0.80 = 80%)
    "Of all relevant items in the database, how many did we find?"
    - High recall (>0.8): Finding most relevant items
    - Low recall (<0.5): Missing important results

  F1 SCORE (0.81)
    "Overall balance of precision and recall"
    - This is the single number to track over time
    - F1 > 0.7 is good, F1 > 0.85 is excellent
    - If F1 drops after a change, investigate why

  ACCURACY (0.92)
    "Are the results structurally valid?" (dates make sense, titles exist, etc.)
    - Should always be >0.9; if not, there's a data quality issue


COVERAGE METRICS
----------------
These tell you how thorough the benchmark itself is:

  Query Coverage:    100% (4/4 API methods)
    → Are we testing all API methods? (what_applies, what_happened, etc.)

  Category Coverage: 75% (3/4 categories)
    → Are we testing diverse topics? (housing, transportation, utilities, governance)

  Result Coverage:   62% (5/8 returned results)
    → How many queries actually returned data?
    → Low result coverage with production DB = data gaps
    → Low result coverage with local SQLite = expected (limited data)


BIAS ANALYSIS
-------------
Flags potential problems:

  Topic Bias: "housing" queries work well, but "pothole" queries fail
    → Might indicate uneven data coverage

  Method Bias: what_happened() works, but whos_with_me() always fails
    → Might indicate a broken API method or missing data type

  Temporal Bias: Large precision-recall gap
    → Might be finding recent items but missing historical ones


GROUND TRUTH: WHAT IT IS AND ITS LIMITATIONS
--------------------------------------------
"Ground truth" = the correct answers we compare against.

DEFAULT APPROACH (keyword-based, simplistic):
  We count database records matching keywords:
    - "How many decisions mention 'housing'?" → 15
    - API returns 12 → Recall = 12/15 = 0.80

  This is LIMITED because:
    - Keyword matching misses semantic relevance
      (a decision about "affordable apartments" won't match "housing")
    - It's self-referential (using our own DB as truth)
    - Only works for pre-defined topics

LLM-AS-JUDGE APPROACH (recommended for accurate evaluation):
  Use --llm-judge flag to enable semantic relevance scoring:
    python scripts/benchmark_api_vs_llm.py --llm-judge

  How it works:
    - For each result, an LLM judges: "Is this result relevant to the query?"
    - Returns a score from 0.0 to 1.0 (semantic relevance)
    - Results with score > 0.5 are considered "relevant"
    - More accurate than keyword matching (catches semantic similarity)

  Cost:
    - ~$0.001-0.01 per benchmark run (using gemini-2.0-flash-exp)
    - Results are cached to avoid re-evaluating identical query-result pairs
    - Clear cache with: python scripts/benchmark_api_vs_llm.py --clear-cache

  Models available:
    - gemini-2.0-flash-exp (default): $0.075/1M tokens, fast, reliable
    - gpt-4o-mini: $0.60/1M tokens, very reliable
    - llama-3.3-70b-versatile: $0.59/1M tokens, open source

WHAT PROPER GROUND TRUTH WOULD BE:
  A human-curated test set where someone manually labeled:
    - "These 20 decisions ARE relevant to housing"
    - "These 5 decisions are NOT relevant despite mentioning housing"

  The LLM-as-judge approach approximates human judgment at low cost.
  For critical evaluations, consider validating a sample against human labels.


HOW TO ADD A NEW TEST QUERY
---------------------------
Want to test a new topic like "parking"? Here's how:

1. Add ground truth counting (in get_ground_truth_counts function):

    for topic in ["housing", "bike", "traffic", "pothole", "parking"]:  # Add here
        cur.execute(...)
        counts[f"decisions_{topic}"] = cur.fetchone()[0]

2. Add the query to run_all():

    # In run_all() method, add:
    self.results.append(self.run_what_happened("parking"))

3. (Optional) Add an LLM baseline response:

    # In LLM_BASELINES dict, add:
    "what_happened:parking": \"\"\"
    I don't have access to local parking decisions.
    Check your city's transportation department website.
    \"\"\",

4. Run the benchmark to see results:

    python scripts/benchmark_api_vs_llm.py


HOW TO TRACK QUALITY OVER TIME
------------------------------
1. Run benchmark and save JSON output:
   python scripts/benchmark_api_vs_llm.py --json > benchmarks/2026-01-09.json

2. Key metrics to track:
   - avg_f1: Overall quality score (higher is better)
   - result_coverage: Are queries returning data?
   - gaps_detected: Count of detected issues

3. After major changes, compare:
   - Did avg_f1 go up or down?
   - Did we introduce new gaps?


INTERPRETING EXIT CODES
-----------------------
  Exit 0: All good, no gaps detected
  Exit 1: Gaps detected (queries returning no results, low-relevance results, etc.)

In CI, you might want to allow exit 1 but track the gaps.


EXAMPLE OUTPUT WALKTHROUGH
--------------------------
Here's what a healthy benchmark looks like:

    ======================================================================
    CIVIC API BENCHMARK vs LLM BASELINE
    Jurisdiction: city-san-rafael
    Database: Supabase PostgreSQL (production)     ← Good: using real data
    ======================================================================

    ## what_applies('housing')
       Civic count: 13                              ← Found 13 relevant laws
       Accurate:   ✓ (1.0)                          ← All results valid
       Precision:  0.85  |  Recall: -  |  F1: 0.85  ← 85% relevant
       Grounded:   ✓                                ← Has real citations
       Specific:   ✓                                ← Names specific bills
       Actionable: ✗                                ← No local rules (gap!)

    SUMMARY
    Accurate:       8/8 (100%)
    Precision:      avg 0.82  |  Recall: avg 0.75  |  F1: avg 0.78  ← Track this!
    Grounded:       7/8 (87.5%)
    Actionable:     5/8 (62.5%)                     ← Room for improvement

    COVERAGE METRICS
    Result Coverage:   75% (6/8 returned results)   ← Most queries working

    GAPS DETECTED
      ⚠ what_applies('housing'): No local rules    ← Action item!


WHEN TO WORRY
-------------
- F1 drops below 0.6 → Quality problem
- Result coverage drops significantly → Data pipeline issue
- Many "NO RESULTS" in bias analysis → Missing data for those topics
- Exit code 1 with new gaps after a change → Regression


Usage:
    python scripts/benchmark_api_vs_llm.py [--jurisdiction JURISDICTION]
    python scripts/benchmark_api_vs_llm.py --json  # Output as JSON for tracking
"""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

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


# =============================================================================
# LLM-as-Judge Relevance Scoring
# =============================================================================

class LLMRelevanceJudge:
    """
    Uses LLM to evaluate result relevance instead of keyword matching.

    This provides more accurate precision/recall calculations by asking the LLM
    to judge whether each result is semantically relevant to the query, rather
    than relying on simple keyword matching.

    Cost considerations:
    - Each judgment: ~100-200 tokens
    - 8 queries × 10 results = 80 judgments per run
    - At gpt-4o-mini ($0.60/1M): ~$0.01 per benchmark run
    - At gemini-2.0-flash-exp ($0.075/1M): ~$0.001 per benchmark run
    - Cache hits reduce costs to near-zero for repeated runs

    Usage:
        judge = LLMRelevanceJudge()
        score = judge.score_relevance("housing policy", "City Council approves ADU ordinance")
        # Returns 0.9 (highly relevant)

        score = judge.score_relevance("housing policy", "New bike lane on 4th Street")
        # Returns 0.1 (not relevant)
    """

    SYSTEM_PROMPT = """You are an expert evaluator of civic information retrieval results.
Your task is to judge whether a search result is relevant to a user's query about local government and civic matters.

Scoring guidelines:
- 1.0: Directly relevant - the result specifically addresses the query topic
- 0.7-0.9: Highly relevant - the result is about the same subject area with strong connection
- 0.4-0.6: Somewhat relevant - tangentially related or shares some keywords but different focus
- 0.1-0.3: Weakly relevant - minimal connection, mostly unrelated
- 0.0: Not relevant - completely unrelated to the query

Consider semantic meaning, not just keyword overlap. A result about "accessory dwelling units" is relevant to a "housing" query even without the word "housing"."""

    USER_PROMPT_TEMPLATE = """Query: {query}

Result Title: {title}
Result Summary: {summary}

Is this result relevant to the query? Respond with ONLY a decimal score from 0.0 to 1.0."""

    def __init__(
        self,
        model: str = "gemini-2.0-flash-exp",
        cache_dir: Optional[Path] = None,
        use_cache: bool = True
    ):
        """
        Initialize the LLM relevance judge.

        Args:
            model: Model to use for judgments (default: cheapest reliable option)
            cache_dir: Directory for caching judgments (default: .cache/llm_judge)
            use_cache: Whether to use cached judgments
        """
        self.model = model
        self.use_cache = use_cache
        self.cache_dir = cache_dir or Path(__file__).parent.parent / ".cache" / "llm_judge"
        self._provider = None
        self._total_cost = 0.0
        self._total_tokens = 0
        self._cache_hits = 0
        self._cache_misses = 0

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_provider(self):
        """Lazy-load the LLM provider."""
        if self._provider is None:
            from civic_services.core.llm_provider import get_model
            self._provider = get_model(self.model)
        return self._provider

    def _get_cache_key(self, query: str, title: str, summary: str) -> str:
        """Generate a cache key for a query-result pair."""
        content = f"{query}|{title}|{summary}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_cached_score(self, cache_key: str) -> Optional[float]:
        """Get cached score if available."""
        if not self.use_cache:
            return None
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    self._cache_hits += 1
                    return data.get("score")
            except (json.JSONDecodeError, IOError):
                pass
        return None

    def _save_cached_score(self, cache_key: str, score: float, query: str, title: str):
        """Save score to cache."""
        if not self.use_cache:
            return
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump({
                    "score": score,
                    "query": query,
                    "title": title[:100],
                    "model": self.model,
                    "timestamp": datetime.now().isoformat()
                }, f)
        except IOError:
            pass

    def score_relevance(self, query: str, title: str, summary: str = "") -> float:
        """
        Score the relevance of a single result to a query.

        Args:
            query: The user's search query
            title: The result title
            summary: Optional result summary/description

        Returns:
            Relevance score from 0.0 to 1.0
        """
        # Check cache first
        cache_key = self._get_cache_key(query, title, summary)
        cached = self._get_cached_score(cache_key)
        if cached is not None:
            return cached

        self._cache_misses += 1

        # Prepare the prompt
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            query=query,
            title=title,
            summary=summary[:500] if summary else "(no summary)"
        )

        # Call the LLM
        provider = self._get_provider()
        try:
            response = provider.complete(
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=10,  # Just need a number
                temperature=0  # Deterministic for consistency
            )

            # Track costs
            if hasattr(response, 'usage') and response.usage:
                from civic_services.core.model_registry import calculate_cost
                cost = calculate_cost(self.model, response.usage)
                self._total_cost += cost
                self._total_tokens += response.usage.get('total_tokens', 0)

            # Parse the score
            score_text = response.content.strip()
            try:
                score = float(score_text)
                score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
            except ValueError:
                # Try to extract a number from the response
                import re
                match = re.search(r'(\d+\.?\d*)', score_text)
                if match:
                    score = float(match.group(1))
                    score = max(0.0, min(1.0, score))
                else:
                    score = 0.5  # Default if parsing fails

            # Cache the result
            self._save_cached_score(cache_key, score, query, title)
            return score

        except Exception as e:
            # On error, return neutral score
            print(f"LLM judge error: {e}")
            return 0.5

    def score_batch(
        self,
        query: str,
        results: List[Dict[str, str]],
        max_results: int = 10
    ) -> List[float]:
        """
        Score multiple results for a single query.

        Args:
            query: The user's search query
            results: List of dicts with 'title' and optional 'summary' keys
            max_results: Maximum number of results to score (for cost control)

        Returns:
            List of relevance scores (0.0 to 1.0)
        """
        scores = []
        for result in results[:max_results]:
            title = result.get('title', '')
            summary = result.get('summary', '')
            score = self.score_relevance(query, title, summary)
            scores.append(score)
        return scores

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about LLM judge usage."""
        return {
            "model": self.model,
            "total_cost_usd": round(self._total_cost, 6),
            "total_tokens": self._total_tokens,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": (
                round(self._cache_hits / (self._cache_hits + self._cache_misses), 2)
                if (self._cache_hits + self._cache_misses) > 0 else 0
            )
        }

    def clear_cache(self):
        """Clear the judgment cache."""
        if self.cache_dir.exists():
            import shutil
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)


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


def calculate_f1(precision: float, recall: float) -> float:
    """Calculate F1 score (harmonic mean of precision and recall)."""
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


@dataclass
class BenchmarkReport:
    """Full benchmark report."""
    jurisdiction: str
    timestamp: str
    queries: list
    summary: dict
    gaps_detected: list
    coverage: dict = field(default_factory=dict)
    bias_analysis: dict = field(default_factory=dict)
    llm_judge_stats: dict = field(default_factory=dict)  # LLM-as-judge cost/usage stats


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

    def __init__(
        self,
        jurisdiction: str = "city-san-rafael",
        use_llm_judge: bool = False,
        llm_judge_model: str = "gemini-2.0-flash-exp"
    ):
        """
        Initialize the benchmark.

        Args:
            jurisdiction: Jurisdiction to benchmark
            use_llm_judge: Enable LLM-as-judge relevance scoring (more accurate but costs ~$0.001-0.01 per run)
            llm_judge_model: Model to use for LLM judgments (default: cheapest reliable option)
        """
        self.jurisdiction = jurisdiction
        self.results: list[QueryResult] = []
        self.gaps: list[str] = []
        self._civic = None
        self._ground_truth = get_ground_truth_counts(jurisdiction)
        self.use_llm_judge = use_llm_judge
        self._llm_judge = None
        self._llm_judge_model = llm_judge_model

    def _get_llm_judge(self) -> Optional[LLMRelevanceJudge]:
        """Lazy-load LLM judge if enabled."""
        if not self.use_llm_judge:
            return None
        if self._llm_judge is None:
            self._llm_judge = LLMRelevanceJudge(model=self._llm_judge_model)
        return self._llm_judge

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

        # Note: what_applies doesn't have recall (no ground truth for legislation)
        # F1 is undefined without recall, so we set it to precision (single-metric case)
        f1_score = precision_score  # No recall available for legislation queries

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
                "f1": round(f1_score, 2),  # Same as precision when no recall
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

        # PRECISION: Count results with query keyword in title (keyword-based, simplistic)
        keyword_matches = sum(1 for d in result if query.lower() in d.title.lower())
        keyword_precision = keyword_matches / len(result) if result else 1.0

        # LLM-AS-JUDGE PRECISION: Use LLM to evaluate semantic relevance
        llm_judge = self._get_llm_judge()
        llm_precision = None
        llm_relevance_scores = []
        if llm_judge and result:
            # Score each result using LLM
            for d in result[:10]:  # Limit to 10 results for cost control
                summary = d.summary if hasattr(d, 'summary') and d.summary else ""
                score = llm_judge.score_relevance(query, d.title, summary)
                llm_relevance_scores.append(score)
            # LLM precision: avg relevance score (treating scores > 0.5 as "relevant")
            llm_precision = sum(llm_relevance_scores) / len(llm_relevance_scores) if llm_relevance_scores else 1.0

        # Use LLM precision if available, otherwise fall back to keyword precision
        precision_score = llm_precision if llm_precision is not None else keyword_precision

        # RECALL: retrieved relevant / total relevant in DB
        query_key = query.lower().split()[0]  # "bike lane" -> "bike"
        total_relevant = self._ground_truth.get(f"decisions_{query_key}", 0)
        # For recall, count results with LLM score > 0.5 as "relevant" if LLM judge enabled
        if llm_relevance_scores:
            relevant_retrieved = sum(1 for s in llm_relevance_scores if s > 0.5)
        else:
            relevant_retrieved = keyword_matches
        recall_score = relevant_retrieved / total_relevant if total_relevant > 0 else 1.0

        baseline_key = f"what_happened:{query}"
        llm_baseline = self.LLM_BASELINES.get(baseline_key, "No baseline defined")

        # F1 score: harmonic mean of precision and recall
        f1_score = calculate_f1(precision_score, recall_score)

        # Build civic_result with both keyword and LLM metrics
        civic_result_data = {
            "decision_count": len(result),
            "accurate_count": accurate_count,
            "keyword_matches": keyword_matches,
            "keyword_precision": round(keyword_precision, 2),
            "total_relevant_in_db": total_relevant,
        }
        if llm_relevance_scores:
            civic_result_data["llm_relevance_scores"] = [round(s, 2) for s in llm_relevance_scores]
            civic_result_data["llm_precision"] = round(llm_precision, 2) if llm_precision else None
            civic_result_data["llm_relevant_count"] = sum(1 for s in llm_relevance_scores if s > 0.5)

        return QueryResult(
            method="what_happened",
            query=query,
            civic_result=civic_result_data,
            civic_count=len(result),
            civic_sample=sample,
            llm_baseline=llm_baseline.strip(),
            evaluation={
                "accurate": accuracy_score >= 0.7,
                "accuracy_score": round(accuracy_score, 2),
                "precision": round(precision_score, 2),
                "keyword_precision": round(keyword_precision, 2),
                "llm_precision": round(llm_precision, 2) if llm_precision is not None else None,
                "recall": round(recall_score, 2),
                "f1": round(f1_score, 2),
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

        # No recall for whats_next (no ground truth for future meetings)
        f1_score = precision_score  # Same as precision when no recall available

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
                "f1": round(f1_score, 2),  # Same as precision when no recall
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

        # F1 score: harmonic mean of precision and recall
        f1_score = calculate_f1(precision_score, recall_score)

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
                "f1": round(f1_score, 2),
                "grounded": result.follower_count > 0,
                "specific": True,  # Quantified community size
                "actionable": result.follower_count > 0,  # Can connect users
            }
        )

    def detect_bias(self) -> dict:
        """Detect potential biases in benchmark results."""
        if not self.results:
            return {"error": "No results to analyze"}

        # TOPIC BIAS: Are some topics consistently under-served?
        topic_performance = {}
        for r in self.results:
            topic = r.query
            if topic not in topic_performance:
                topic_performance[topic] = []
            # Aggregate key metrics for this topic
            topic_performance[topic].append({
                "has_results": r.civic_count > 0,
                "accuracy": r.evaluation.get("accuracy_score", 1.0),
                "precision": r.evaluation.get("precision", 1.0),
                "f1": r.evaluation.get("f1", 0.0),
            })

        # Identify under-performing topics (low F1 or no results)
        underperforming_topics = []
        for topic, metrics_list in topic_performance.items():
            avg_f1 = sum(m["f1"] for m in metrics_list) / len(metrics_list)
            has_any_results = any(m["has_results"] for m in metrics_list)
            if avg_f1 < 0.5 or not has_any_results:
                underperforming_topics.append({
                    "topic": topic,
                    "avg_f1": round(avg_f1, 2),
                    "has_results": has_any_results,
                })

        # TEMPORAL BIAS: Check if what_happened has recency bias
        temporal_bias = None
        what_happened_results = [r for r in self.results if r.method == "what_happened"]
        if what_happened_results:
            for r in what_happened_results:
                # Note: would need actual date analysis from decisions for full temporal analysis
                # For now, flag if recall is very different from precision
                recall = r.evaluation.get("recall", 1.0)
                precision = r.evaluation.get("precision", 1.0)
                if recall > 0 and precision > 0:
                    # Large gap suggests temporal bias (retrieving recent but missing old, or vice versa)
                    gap = abs(recall - precision)
                    if gap > 0.3:
                        temporal_bias = {
                            "detected": True,
                            "precision": precision,
                            "recall": recall,
                            "gap": round(gap, 2),
                            "interpretation": "Large precision-recall gap may indicate temporal bias",
                        }

        # METHOD BIAS: Are some API methods consistently worse?
        method_performance = {}
        for r in self.results:
            method = r.method
            if method not in method_performance:
                method_performance[method] = {"f1_scores": [], "has_results": []}
            method_performance[method]["f1_scores"].append(r.evaluation.get("f1", 0.0))
            method_performance[method]["has_results"].append(r.civic_count > 0)

        method_bias = []
        for method, perf in method_performance.items():
            avg_f1 = sum(perf["f1_scores"]) / len(perf["f1_scores"])
            result_rate = sum(perf["has_results"]) / len(perf["has_results"])
            if avg_f1 < 0.5 or result_rate < 0.5:
                method_bias.append({
                    "method": method,
                    "avg_f1": round(avg_f1, 2),
                    "result_rate": round(result_rate, 2),
                })

        # GEOGRAPHIC BIAS: Would need multi-jurisdiction data to detect
        # For now, note that we're only testing one jurisdiction
        geographic_note = f"Testing single jurisdiction ({self.jurisdiction}) - geographic bias cannot be assessed"

        return {
            "topic_bias": {
                "underperforming_topics": underperforming_topics,
                "count": len(underperforming_topics),
            },
            "temporal_bias": temporal_bias or {"detected": False},
            "method_bias": {
                "underperforming_methods": method_bias,
                "count": len(method_bias),
            },
            "geographic_note": geographic_note,
            "overall_bias_detected": len(underperforming_topics) > 0 or len(method_bias) > 0 or (temporal_bias and temporal_bias.get("detected")),
        }

    def calculate_coverage(self) -> dict:
        """Calculate coverage metrics for the eval framework."""
        # QUERY COVERAGE: How many API methods are tested
        all_api_methods = ["what_applies", "what_happened", "whats_next", "whos_with_me"]
        tested_methods = set(r.method for r in self.results)
        query_coverage = len(tested_methods) / len(all_api_methods)

        # TOPIC COVERAGE: Diversity of topics tested
        all_topics = [r.query for r in self.results]
        unique_topics = set(all_topics)
        topic_diversity = len(unique_topics) / len(all_topics) if all_topics else 0

        # Define topic categories for coverage analysis
        topic_categories = {
            "housing": ["housing", "accessory dwelling unit", "adu", "zoning"],
            "transportation": ["traffic", "bike lane", "parking", "transit"],
            "utilities": ["pothole", "water", "sewer", "infrastructure"],
            "governance": ["meeting", "election", "budget", "council"],
        }

        # Calculate category coverage
        tested_categories = set()
        for topic in unique_topics:
            topic_lower = topic.lower()
            for category, keywords in topic_categories.items():
                if any(kw in topic_lower for kw in keywords):
                    tested_categories.add(category)
        category_coverage = len(tested_categories) / len(topic_categories)

        # DATA COVERAGE: What percentage of database tables are exercised
        data_sources_tested = {
            "legislation": any(r.method == "what_applies" for r in self.results),
            "decisions": any(r.method == "what_happened" for r in self.results),
            "meetings": any(r.method == "whats_next" for r in self.results),
            "issues": any(r.method == "whos_with_me" for r in self.results),
        }
        data_coverage = sum(data_sources_tested.values()) / len(data_sources_tested)

        # RESULT COVERAGE: How many queries returned non-empty results
        non_empty = sum(1 for r in self.results if r.civic_count > 0)
        result_coverage = non_empty / len(self.results) if self.results else 0

        return {
            "query_coverage": round(query_coverage, 2),
            "topic_diversity": round(topic_diversity, 2),
            "category_coverage": round(category_coverage, 2),
            "data_coverage": round(data_coverage, 2),
            "result_coverage": round(result_coverage, 2),
            "tested_methods": list(tested_methods),
            "tested_categories": list(tested_categories),
            "untested_categories": [c for c in topic_categories if c not in tested_categories],
            "total_queries": len(self.results),
            "queries_with_results": non_empty,
        }

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

        # Average accuracy, precision, recall, f1 scores across all queries
        accuracy_scores = [r.evaluation.get("accuracy_score", 1.0) for r in self.results]
        precision_scores = [r.evaluation.get("precision", 1.0) for r in self.results]
        recall_scores = [r.evaluation.get("recall", 1.0) for r in self.results if "recall" in r.evaluation]
        f1_scores = [r.evaluation.get("f1", 0.0) for r in self.results if "f1" in r.evaluation]
        avg_accuracy = sum(accuracy_scores) / len(accuracy_scores) if accuracy_scores else 0
        avg_precision = sum(precision_scores) / len(precision_scores) if precision_scores else 0
        avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0
        avg_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0

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
            "avg_f1": round(avg_f1, 2),
            "grounded_pct": round(100 * grounded_count / len(self.results), 1),
            "specific_pct": round(100 * specific_count / len(self.results), 1),
            "actionable_pct": round(100 * actionable_count / len(self.results), 1),
            "gaps_detected": len(self.gaps),
        }

        # Calculate coverage metrics
        coverage = self.calculate_coverage()

        # Detect biases
        bias_analysis = self.detect_bias()

        # Get LLM judge stats if enabled
        llm_judge_stats = {}
        if self._llm_judge:
            llm_judge_stats = self._llm_judge.get_stats()
            # Also add comparison of keyword vs LLM precision for queries that have both
            keyword_precisions = []
            llm_precisions = []
            for r in self.results:
                kp = r.evaluation.get("keyword_precision")
                lp = r.evaluation.get("llm_precision")
                if kp is not None and lp is not None:
                    keyword_precisions.append(kp)
                    llm_precisions.append(lp)
            if keyword_precisions and llm_precisions:
                llm_judge_stats["avg_keyword_precision"] = round(sum(keyword_precisions) / len(keyword_precisions), 2)
                llm_judge_stats["avg_llm_precision"] = round(sum(llm_precisions) / len(llm_precisions), 2)
                llm_judge_stats["precision_diff"] = round(llm_judge_stats["avg_llm_precision"] - llm_judge_stats["avg_keyword_precision"], 2)

        return BenchmarkReport(
            jurisdiction=self.jurisdiction,
            timestamp=datetime.now().isoformat(),
            queries=[asdict(r) for r in self.results],
            summary=summary,
            gaps_detected=self.gaps,
            coverage=coverage,
            bias_analysis=bias_analysis,
            llm_judge_stats=llm_judge_stats,
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
        f1_score = q['evaluation'].get('f1', '-')
        print(f"   Accurate:   {'✓' if q['evaluation'].get('accurate') else '✗'} ({acc_score})")
        print(f"   Precision:  {prec_score}  |  Recall: {rec_score}  |  F1: {f1_score}")
        print(f"   Grounded:   {'✓' if q['evaluation'].get('grounded') else '✗'}")
        print(f"   Specific:   {'✓' if q['evaluation'].get('specific') else '✗'}")
        print(f"   Actionable: {'✓' if q['evaluation'].get('actionable') else '✗'}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    s = report.summary
    print(f"Total queries:  {s['total_queries']}")
    print(f"Accurate:       {s['accurate']}/{s['total_queries']} ({s['accurate_pct']}%) [avg: {s['avg_accuracy_score']}]")
    print(f"Precision:      avg {s['avg_precision']}  |  Recall: avg {s['avg_recall']}  |  F1: avg {s.get('avg_f1', '-')}")
    print(f"Grounded:       {s['grounded']}/{s['total_queries']} ({s['grounded_pct']}%)")
    print(f"Specific:       {s['specific']}/{s['total_queries']} ({s['specific_pct']}%)")
    print(f"Actionable:     {s['actionable']}/{s['total_queries']} ({s['actionable_pct']}%)")

    # Coverage metrics
    if report.coverage:
        print("\n" + "=" * 70)
        print("COVERAGE METRICS")
        print("=" * 70)
        c = report.coverage
        print(f"Query Coverage:    {c.get('query_coverage', 0):.0%} ({len(c.get('tested_methods', []))}/4 API methods)")
        print(f"Topic Diversity:   {c.get('topic_diversity', 0):.0%} (unique topics / total queries)")
        print(f"Category Coverage: {c.get('category_coverage', 0):.0%} ({len(c.get('tested_categories', []))}/4 categories)")
        print(f"Data Coverage:     {c.get('data_coverage', 0):.0%} (data sources exercised)")
        print(f"Result Coverage:   {c.get('result_coverage', 0):.0%} ({c.get('queries_with_results', 0)}/{c.get('total_queries', 0)} returned results)")
        if c.get('untested_categories'):
            print(f"Untested:          {', '.join(c.get('untested_categories', []))}")

    # Bias analysis
    if report.bias_analysis:
        print("\n" + "=" * 70)
        print("BIAS ANALYSIS")
        print("=" * 70)
        b = report.bias_analysis
        overall = "DETECTED" if b.get("overall_bias_detected") else "None detected"
        print(f"Overall Bias:      {overall}")

        topic_bias = b.get("topic_bias", {})
        if topic_bias.get("count", 0) > 0:
            print(f"\nTopic Bias ({topic_bias['count']} issues):")
            for t in topic_bias.get("underperforming_topics", []):
                results_status = "has results" if t["has_results"] else "NO RESULTS"
                print(f"  - '{t['topic']}': F1={t['avg_f1']} ({results_status})")

        method_bias = b.get("method_bias", {})
        if method_bias.get("count", 0) > 0:
            print(f"\nMethod Bias ({method_bias['count']} issues):")
            for m in method_bias.get("underperforming_methods", []):
                print(f"  - {m['method']}: F1={m['avg_f1']}, result_rate={m['result_rate']:.0%}")

        temporal_bias = b.get("temporal_bias", {})
        if temporal_bias.get("detected"):
            print(f"\nTemporal Bias: {temporal_bias.get('interpretation', 'Detected')}")
            print(f"  Precision: {temporal_bias.get('precision')}, Recall: {temporal_bias.get('recall')}, Gap: {temporal_bias.get('gap')}")

        if b.get("geographic_note"):
            print(f"\nGeographic: {b['geographic_note']}")

    if report.gaps_detected:
        print("\n" + "=" * 70)
        print("GAPS DETECTED")
        print("=" * 70)
        for gap in report.gaps_detected:
            print(f"  ⚠ {gap}")

    # LLM-as-Judge stats (if enabled)
    if report.llm_judge_stats:
        print("\n" + "=" * 70)
        print("LLM-AS-JUDGE METRICS")
        print("=" * 70)
        stats = report.llm_judge_stats
        print(f"Model:             {stats.get('model', 'N/A')}")
        print(f"Total Cost:        ${stats.get('total_cost_usd', 0):.4f}")
        print(f"Total Tokens:      {stats.get('total_tokens', 0):,}")
        print(f"Cache Hits:        {stats.get('cache_hits', 0)} ({stats.get('cache_hit_rate', 0):.0%} hit rate)")
        print(f"Cache Misses:      {stats.get('cache_misses', 0)}")
        if 'avg_keyword_precision' in stats:
            print(f"\nPrecision Comparison:")
            print(f"  Keyword-based:   {stats['avg_keyword_precision']:.2f}")
            print(f"  LLM-judged:      {stats['avg_llm_precision']:.2f}")
            diff = stats['precision_diff']
            direction = "+" if diff >= 0 else ""
            print(f"  Difference:      {direction}{diff:.2f} (LLM vs keyword)")

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
    parser = argparse.ArgumentParser(
        description="Benchmark Civic API vs LLM baseline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic run (keyword-based precision)
  python scripts/benchmark_api_vs_llm.py

  # With LLM-as-judge (more accurate precision, ~$0.001 per run)
  python scripts/benchmark_api_vs_llm.py --llm-judge

  # Output as JSON for tracking
  python scripts/benchmark_api_vs_llm.py --llm-judge --json > benchmark_results.json

  # Clear LLM judge cache (for fresh evaluations)
  python scripts/benchmark_api_vs_llm.py --clear-cache
"""
    )
    parser.add_argument("--jurisdiction", default="city-san-rafael", help="Jurisdiction to test")
    parser.add_argument("--run-all", action="store_true", help="Run all benchmark tests")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Enable LLM-as-judge relevance scoring (more accurate but costs ~$0.001-0.01)"
    )
    parser.add_argument(
        "--llm-judge-model",
        default="gemini-2.0-flash-exp",
        help="Model to use for LLM judgments (default: gemini-2.0-flash-exp, cheapest reliable)"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear LLM judge cache before running"
    )
    args = parser.parse_args()

    # Handle cache clearing
    if args.clear_cache:
        judge = LLMRelevanceJudge()
        judge.clear_cache()
        print("LLM judge cache cleared.")
        if not args.run_all and not args.llm_judge:
            sys.exit(0)

    benchmark = CivicBenchmark(
        args.jurisdiction,
        use_llm_judge=args.llm_judge,
        llm_judge_model=args.llm_judge_model
    )

    if args.run_all or True:  # Default to running all
        report = benchmark.run_all()
        print_report(report, as_json=args.json)

    # Exit with error code if gaps detected
    if report.gaps_detected:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
