"""
Abstract base classes for research orchestration.

This module provides the foundation for topic-specific researchers:
- BaseResearcher: Abstract class with common orchestration logic
- Generic result types that can be extended for specific topics

Subclasses implement topic-specific prompt building, parsing, and merging.

Example:
    class HousingResearcher(BaseResearcher):
        def _build_prompt(self, jurisdiction, state, **kwargs) -> str:
            return "Housing-specific prompt..."

        def _parse_response(self, result) -> Optional[BaseModel]:
            return MunicipalFundingPrograms(...)
"""

import json
import re
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import yaml
from pydantic import BaseModel

from .providers import SearchProvider, SearchResult, get_provider


# Type variable for parsed data models
T = TypeVar("T", bound=BaseModel)


@dataclass
class MunicipalityConfig:
    """Configuration for municipality-specific research.

    Can be loaded from a research_config.yaml file in the municipality's
    data directory. Allows customizing queries for specific jurisdictions.
    """

    known_programs: list[str] = field(default_factory=list)
    """Known program names to search for specifically."""

    custom_queries: list[str] = field(default_factory=list)
    """Custom queries specific to this municipality."""

    query_overrides: dict[str, str] = field(default_factory=dict)
    """Override default query templates."""

    skip_queries: list[str] = field(default_factory=list)
    """Query keys to skip."""

    @classmethod
    def from_yaml(cls, path: Path) -> "MunicipalityConfig":
        """Load config from YAML file."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(
            known_programs=data.get("known_programs", []),
            custom_queries=data.get("custom_queries", []),
            query_overrides=data.get("query_overrides", {}),
            skip_queries=data.get("skip_queries", []),
        )


@dataclass
class QueryTemplate:
    """A query template with metadata."""

    key: str
    """Unique identifier for this query type."""

    template: str
    """Query template with {placeholders}."""

    description: str
    """What this query searches for."""

    program_type: str
    """Type of program this query targets (for result merging)."""

    priority: int = 1
    """Priority for rate limiting (1=high, 3=low)."""


@dataclass
class QueryResult:
    """Result from a single query in an ensemble."""

    query: str
    template_key: Optional[str]
    program_type: Optional[str]
    response: SearchResult
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ResearchResult:
    """Result from single-query research."""

    jurisdiction: str
    state: str
    topic: str
    raw_response: SearchResult
    parsed_data: Optional[Any] = None  # Topic-specific model
    audit_file: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EnsembleResearchResult:
    """Result from ensemble research with multiple queries."""

    jurisdiction: str
    state: str
    topic: str
    query_results: list[QueryResult] = field(default_factory=list)
    """Results from individual queries."""

    merged_data: Optional[Any] = None  # Topic-specific model
    """Merged and deduplicated data from all queries."""

    audit_file: Optional[str] = None
    total_cost: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


class BaseResearcher(ABC):
    """
    Abstract base class for topic-specific researchers.

    Provides common orchestration for:
    - Single-query research
    - Ensemble research with parallel queries
    - Rate limiting and error handling
    - Audit trail persistence
    - Municipality-specific configuration

    Subclasses implement:
    - _get_topic(): Return the topic identifier
    - _get_query_templates(): Return templates for this topic
    - _build_prompt(): Build the research prompt
    - _parse_response(): Parse response into topic-specific model
    - _merge_results(): Merge ensemble results

    Example:
        class HousingResearcher(BaseResearcher):
            def _get_topic(self) -> str:
                return "housing"

            def _build_prompt(self, jurisdiction, state, **kwargs) -> str:
                return f"Research {jurisdiction}'s housing programs..."
    """

    def __init__(
        self,
        provider: Optional[SearchProvider] = None,
        data_dir: str = "data/funding/municipal",
    ):
        """
        Initialize the researcher.

        Args:
            provider: Search provider to use. If None, uses default from env.
            data_dir: Base directory for saving research data.
        """
        self._provider = provider or get_provider()
        self._data_dir = Path(data_dir)

    @property
    def provider(self) -> SearchProvider:
        """The search provider being used."""
        return self._provider

    # =========================================================================
    # Abstract methods - subclasses must implement
    # =========================================================================

    @abstractmethod
    def _get_topic(self) -> str:
        """
        Return the topic identifier for this researcher.

        Returns:
            Topic string (e.g., "housing", "transportation", "environment").
        """
        ...

    @abstractmethod
    def _get_query_templates(self) -> list[QueryTemplate]:
        """
        Return the query templates for this topic.

        Returns:
            List of QueryTemplate objects for ensemble research.
        """
        ...

    @abstractmethod
    def _build_prompt(self, jurisdiction: str, state: str, **kwargs: Any) -> str:
        """
        Build the research prompt for single-query research.

        Args:
            jurisdiction: City/county name.
            state: State name.
            **kwargs: Additional topic-specific parameters.

        Returns:
            Formatted prompt string for the search provider.
        """
        ...

    @abstractmethod
    def _parse_response(self, result: ResearchResult) -> Optional[T]:
        """
        Parse the raw response into a topic-specific model.

        Args:
            result: ResearchResult with raw_response populated.

        Returns:
            Parsed data model or None if parsing fails.
        """
        ...

    @abstractmethod
    def _merge_results(self, result: EnsembleResearchResult) -> Optional[T]:
        """
        Merge ensemble results into unified topic-specific model.

        Args:
            result: EnsembleResearchResult with query_results populated.

        Returns:
            Merged data model or None if merging fails.
        """
        ...

    # =========================================================================
    # Template methods - subclasses can override
    # =========================================================================

    def _get_topic_context(self) -> dict[str, str]:
        """
        Return topic context descriptions for prompts.

        Override to provide topic-specific context.
        Default returns an empty dict.
        """
        return {}

    def _get_output_schema(self) -> Optional[type[BaseModel]]:
        """
        Return the Pydantic model class for output.

        Override to enable type-safe output handling.
        """
        return None

    # =========================================================================
    # Core research methods - use common orchestration
    # =========================================================================

    def research(
        self,
        jurisdiction: str,
        state: str,
        *,
        save_audit: bool = True,
        **kwargs: Any,
    ) -> ResearchResult:
        """
        Research using a single comprehensive query.

        Args:
            jurisdiction: City/county name (e.g., "San Rafael").
            state: State name (e.g., "California").
            save_audit: Whether to save audit trail to disk.
            **kwargs: Additional topic-specific parameters.

        Returns:
            ResearchResult with raw response and parsed data.
        """
        topic = self._get_topic()

        # Build the research prompt
        prompt = self._build_prompt(jurisdiction, state, **kwargs)

        # Execute search
        search_result = self._provider.search(prompt)

        # Create result object
        result = ResearchResult(
            jurisdiction=jurisdiction,
            state=state,
            topic=topic,
            raw_response=search_result,
        )

        # Save audit trail
        if save_audit:
            result.audit_file = self._save_audit(result)

        # Attempt to parse into structured format
        result.parsed_data = self._parse_response(result)

        return result

    def research_ensemble(
        self,
        jurisdiction: str,
        state: str,
        *,
        save_audit: bool = True,
        max_workers: int = 3,
        delay_between_queries: float = 1.0,
        max_priority: int = 2,
        **kwargs: Any,
    ) -> EnsembleResearchResult:
        """
        Research using multiple focused queries in parallel.

        This method runs multiple targeted queries, then merges
        the results for more comprehensive coverage.

        Args:
            jurisdiction: City/county name (e.g., "San Rafael").
            state: State name (e.g., "California").
            save_audit: Whether to save audit trail to disk.
            max_workers: Maximum parallel queries.
            delay_between_queries: Delay between queries (rate limiting).
            max_priority: Only run queries with priority <= this value.
            **kwargs: Additional topic-specific parameters.

        Returns:
            EnsembleResearchResult with merged data from all queries.
        """
        topic = self._get_topic()

        # Load municipality config
        config = self._load_municipality_config(jurisdiction)

        # Build queries from templates + config
        queries = self._build_ensemble_queries(
            jurisdiction, state, config, max_priority
        )

        # Execute queries
        query_results = self._execute_queries(
            queries, max_workers, delay_between_queries
        )

        # Create result
        result = EnsembleResearchResult(
            jurisdiction=jurisdiction,
            state=state,
            topic=topic,
            query_results=query_results,
            total_cost=sum(qr.response.cost for qr in query_results),
        )

        # Save audit trail
        if save_audit:
            result.audit_file = self._save_ensemble_audit(result)

        # Merge results
        result.merged_data = self._merge_results(result)

        return result

    # =========================================================================
    # Common orchestration methods
    # =========================================================================

    def _load_municipality_config(self, jurisdiction: str) -> MunicipalityConfig:
        """Load municipality-specific configuration if available."""
        slug = self._slugify(jurisdiction)
        config_path = self._data_dir / slug / "research_config.yaml"
        return MunicipalityConfig.from_yaml(config_path)

    def _build_ensemble_queries(
        self,
        jurisdiction: str,
        state: str,
        config: MunicipalityConfig,
        max_priority: int,
    ) -> list[tuple[str, Optional[QueryTemplate]]]:
        """
        Build list of queries from templates and config.

        Returns list of (query_string, template_or_none) tuples.
        """
        queries = []

        # Get base templates for topic
        templates = self._get_query_templates()

        # Filter and apply overrides
        for template in templates:
            if template.key in config.skip_queries:
                continue
            if template.priority > max_priority:
                continue

            # Check for override
            if template.key in config.query_overrides:
                query = config.query_overrides[template.key].format(
                    municipality=jurisdiction,
                    state=state,
                    year=datetime.now().year,
                )
            else:
                query = template.template.format(
                    municipality=jurisdiction,
                    state=state,
                    year=datetime.now().year,
                    year_range=f"2020-{datetime.now().year}",
                )

            queries.append((query, template))

        # Add custom queries from config
        for custom_query in config.custom_queries:
            queries.append((custom_query, None))

        # Add known program searches
        for program in config.known_programs:
            query = f"{jurisdiction} {state} {program}"
            queries.append((query, None))

        return queries

    def _execute_queries(
        self,
        queries: list[tuple[str, Optional[QueryTemplate]]],
        max_workers: int,
        delay: float,
    ) -> list[QueryResult]:
        """Execute queries with rate limiting."""
        results = []

        def execute_single(query_tuple: tuple[str, Optional[QueryTemplate]]) -> QueryResult:
            query, template = query_tuple
            response = self._provider.search(query)
            return QueryResult(
                query=query,
                template_key=template.key if template else None,
                program_type=template.program_type if template else None,
                response=response,
            )

        # Execute with thread pool for parallelism
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, query_tuple in enumerate(queries):
                # Submit with staggered start for rate limiting
                if i > 0:
                    time.sleep(delay)
                future = executor.submit(execute_single, query_tuple)
                futures.append(future)

            # Collect results
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # Log error but continue with other queries
                    print(f"Query failed: {e}")

        return results

    def _save_audit(self, result: ResearchResult) -> str:
        """Save audit trail to disk."""
        slug = self._slugify(result.jurisdiction)
        municipality_dir = self._data_dir / slug
        municipality_dir.mkdir(parents=True, exist_ok=True)

        audit_file = municipality_dir / f"{result.topic}_perplexity_audit.json"

        # Load existing or create new
        if audit_file.exists():
            with open(audit_file) as f:
                audit_data = json.load(f)
        else:
            audit_data = {"queries": []}

        # Add this query
        audit_data["queries"].append(
            {
                "jurisdiction": result.jurisdiction,
                "state": result.state,
                "topic": result.topic,
                "response": result.raw_response.content,
                "citations": result.raw_response.citations,
                "model": result.raw_response.model,
                "cost": result.raw_response.cost,
                "timestamp": result.timestamp.isoformat(),
                "provider": self._provider.name,
            }
        )

        with open(audit_file, "w") as f:
            json.dump(audit_data, f, indent=2)

        return str(audit_file)

    def _save_ensemble_audit(self, result: EnsembleResearchResult) -> str:
        """Save ensemble audit trail to disk."""
        slug = self._slugify(result.jurisdiction)
        municipality_dir = self._data_dir / slug
        municipality_dir.mkdir(parents=True, exist_ok=True)

        audit_file = municipality_dir / f"{result.topic}_ensemble_audit.json"

        audit_data = {
            "jurisdiction": result.jurisdiction,
            "state": result.state,
            "topic": result.topic,
            "timestamp": result.timestamp.isoformat(),
            "total_cost": result.total_cost,
            "provider": self._provider.name,
            "queries": [
                {
                    "query": qr.query,
                    "template_key": qr.template_key,
                    "program_type": qr.program_type,
                    "response": qr.response.content,
                    "citations": qr.response.citations,
                    "cost": qr.response.cost,
                    "timestamp": qr.timestamp.isoformat(),
                }
                for qr in result.query_results
            ],
        }

        with open(audit_file, "w") as f:
            json.dump(audit_data, f, indent=2)

        return str(audit_file)

    def save_data(
        self,
        result: ResearchResult | EnsembleResearchResult,
        output_file: Optional[str] = None,
    ) -> str:
        """
        Save parsed/merged data to JSON file.

        Args:
            result: Research result with parsed_data or merged_data.
            output_file: Output file path. If None, uses default location.

        Returns:
            Path to the saved file.

        Raises:
            ValueError: If result has no parsed data.
        """
        # Get the data from either result type
        if isinstance(result, EnsembleResearchResult):
            data = result.merged_data
        else:
            data = result.parsed_data

        if data is None:
            raise ValueError(
                "No parsed data available. Raw responses saved to audit file: "
                f"{result.audit_file}"
            )

        if output_file is None:
            slug = self._slugify(result.jurisdiction)
            output_file = str(
                self._data_dir / slug / f"{result.topic}_programs.json"
            )

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        # Handle Pydantic models or raw dicts
        if hasattr(data, "model_dump"):
            json_data = data.model_dump(mode="json")
        else:
            json_data = data

        with open(output_file, "w") as f:
            json.dump(json_data, f, indent=2)

        return output_file

    # =========================================================================
    # Utility methods
    # =========================================================================

    def _slugify(self, text: str) -> str:
        """Convert text to a slug identifier."""
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[-\s]+', '_', slug)
        return slug.strip('_')

    def _generate_keywords(self, text: str) -> list[str]:
        """Generate keywords from text."""
        words = re.split(r'[\s/]+', text.lower())
        stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'to', 'in'}
        return [w for w in words if w and w not in stopwords]

    def _extract_relevant_text(self, content: str, pattern: str) -> str:
        """Extract sentences containing the pattern."""
        sentences = re.split(r'(?<=[.!?])\s+', content)
        relevant = []
        for sentence in sentences:
            if re.search(pattern, sentence, re.IGNORECASE):
                relevant.append(sentence.strip())
        return " ".join(relevant[:3])  # First 3 relevant sentences
