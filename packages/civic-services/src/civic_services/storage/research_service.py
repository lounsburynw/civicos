"""
Research Service for cache-first factual retrieval.

This service answers factual queries by searching cached data:
- Jurisdiction overrides (CDBG allocations, etc.)
- State legislation (28 bills)
- Federal programs (9 programs)
- Event data (meetings, agenda items)

Uses Gemini Flash by default for ultra-low-cost formatting.
"""

import os
import json
import glob
from typing import Dict, List, Optional
from ..core.llm_provider import get_provider_for_task


class ResearchService:
    """
    Cache-first research service for civic data.

    Searches local JSON files and uses LLM to format answers with citations.
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize research service.

        Args:
            data_dir: Root directory for data files
        """
        self.data_dir = data_dir
        self.provider = get_provider_for_task('research')  # Gemini Flash

    def query(self, question: str, search_scope: str = "all") -> Dict:
        """
        Answer factual query from cached data.

        Args:
            question: User's question
            search_scope: Where to search ("all", "legislative", "events", "allocations")

        Returns:
            Dict with answer, sources, and confidence
        """
        # 1. Search relevant data files
        relevant_data = self._search_data(question, search_scope)

        # 2. Format with LLM
        answer = self._format_answer(question, relevant_data)

        return {
            "answer": answer["text"],
            "sources": answer["sources"],
            "confidence": answer["confidence"],
            "search_scope": search_scope
        }

    def _search_data(self, question: str, scope: str) -> Dict:
        """Search cached data files for relevant information"""
        results = {}

        # Search jurisdiction overrides (CDBG, etc.)
        if scope in ["all", "allocations"]:
            results["allocations"] = self._search_jurisdiction_overrides(question)

        # Search legislative context
        if scope in ["all", "legislative"]:
            results["bills"] = self._search_legislative_context(question)
            results["programs"] = self._search_federal_programs(question)

        # Search events
        if scope in ["all", "events"]:
            results["events"] = self._search_events(question)

        return results

    def _search_jurisdiction_overrides(self, question: str) -> List[Dict]:
        """Search jurisdiction override files"""
        matches = []
        pattern = f"{self.data_dir}/jurisdiction_overrides/*.json"

        for filepath in glob.glob(pattern):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    # Simple keyword matching for now
                    if self._is_relevant(question, data, filepath):
                        matches.append({
                            "source": filepath,
                            "data": data
                        })
            except Exception as e:
                # Skip files that can't be read
                continue

        return matches

    def _search_legislative_context(self, question: str) -> List[Dict]:
        """Search state legislation files"""
        matches = []
        pattern = f"{self.data_dir}/legislative_context/california_*.json"

        for filepath in glob.glob(pattern):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    if self._is_relevant(question, data, filepath):
                        matches.append({
                            "source": filepath,
                            "data": data
                        })
            except Exception as e:
                continue

        return matches

    def _search_federal_programs(self, question: str) -> List[Dict]:
        """Search federal programs files"""
        matches = []
        # Exclude audit files
        pattern = f"{self.data_dir}/federal_programs/*.json"

        for filepath in glob.glob(pattern):
            # Skip audit files
            if 'audit' in filepath:
                continue
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    if self._is_relevant(question, data, filepath):
                        matches.append({
                            "source": filepath,
                            "data": data
                        })
            except Exception as e:
                continue

        return matches

    def _search_events(self, question: str) -> List[Dict]:
        """Search event data files"""
        matches = []
        pattern = f"{self.data_dir}/events/events_*.json"

        for filepath in glob.glob(pattern):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    if self._is_relevant(question, data, filepath):
                        # Limit event data to prevent overwhelming context
                        # Only include first 3 events
                        limited_data = data[:3] if isinstance(data, list) else data
                        matches.append({
                            "source": filepath,
                            "data": limited_data
                        })
            except Exception as e:
                continue

        return matches[:3]  # Limit to 3 event files max

    def _is_relevant(self, question: str, data: Dict, filepath: str) -> bool:
        """Check if data is relevant to question (simple keyword match)"""
        question_lower = question.lower()
        data_str = json.dumps(data).lower()
        filepath_lower = filepath.lower()

        # Extract keywords from question (words longer than 3 chars)
        keywords = [w for w in question_lower.split() if len(w) > 3]

        # Check if any keywords match
        for keyword in keywords:
            if keyword in data_str or keyword in filepath_lower:
                return True

        return False

    def _format_answer(self, question: str, data: Dict) -> Dict:
        """Use LLM to format answer with citations"""

        # Build context from search results
        context = self._build_context(data)

        if not context.strip():
            # No data found
            return {
                "text": "I don't have that information in the cached data.",
                "sources": [],
                "confidence": "none"
            }

        # LLM prompt
        prompt = f"""Answer this question using ONLY the provided data. Include source citations.

Question: {question}

Data:
{context}

Instructions:
- Provide a clear, concise answer based on the data
- Cite specific sources (filenames) when making claims
- If the data doesn't contain a complete answer, say what you found and what's missing
- Rate your confidence: high (complete answer), medium (partial answer), or low (limited data)

Format:
Answer: [your answer here]

Sources: [list sources used]

Confidence: [high/medium/low]
"""

        response = self.provider.complete([
            {"role": "system", "content": "You are a civic research assistant. Provide factual answers with source citations from the provided data only."},
            {"role": "user", "content": prompt}
        ])

        # Parse response
        answer_text = response.content
        sources = self._extract_sources(data)

        # Extract confidence from response (simple parsing)
        confidence = "medium"  # default
        if "confidence: high" in answer_text.lower():
            confidence = "high"
        elif "confidence: low" in answer_text.lower():
            confidence = "low"

        return {
            "text": answer_text,
            "sources": sources,
            "confidence": confidence
        }

    def _build_context(self, data: Dict) -> str:
        """Build context string from search results"""
        context_parts = []

        for category, items in data.items():
            if items:
                context_parts.append(f"\n## {category.title()}")
                for item in items[:3]:  # Limit to top 3 per category
                    context_parts.append(f"\nSource: {item['source']}")
                    # Truncate data to prevent overwhelming context
                    data_str = json.dumps(item['data'], indent=2)
                    if len(data_str) > 2000:
                        data_str = data_str[:2000] + "\n... (truncated)"
                    context_parts.append(data_str)

        return "\n".join(context_parts)

    def _extract_sources(self, data: Dict) -> List[str]:
        """Extract source file paths from search results"""
        sources = []
        for category, items in data.items():
            for item in items:
                sources.append(item['source'])
        return list(set(sources))  # Deduplicate
