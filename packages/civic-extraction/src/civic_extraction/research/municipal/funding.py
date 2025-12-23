"""
Municipal funding program researcher.

Researches municipal funding programs using AI-powered search providers
and structures the results for use in the Civic platform.

Supports:
- Single-query research (fast, less comprehensive)
- Ensemble research (multiple focused queries, more comprehensive)
- Municipality-specific configuration via research_config.yaml
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from ..providers import SearchProvider, SearchResult, get_provider
from .query_templates import (
    QueryTemplate,
    build_queries_from_templates,
    get_templates_for_topic,
)
from .schemas import (
    BallotMeasure,
    ContactInfo,
    FundingProgram,
    MunicipalFundingPrograms,
)


@dataclass
class MunicipalityConfig:
    """Configuration for municipality-specific research."""

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
class QueryResult:
    """Result from a single query in an ensemble."""

    query: str
    template_key: Optional[str]
    program_type: Optional[str]
    response: SearchResult
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ResearchResult:
    """Result from municipal funding research."""

    municipality: str
    state: str
    topic: str
    raw_response: SearchResult
    parsed_data: Optional[MunicipalFundingPrograms] = None
    audit_file: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EnsembleResearchResult:
    """Result from ensemble municipal funding research."""

    municipality: str
    state: str
    topic: str
    query_results: list[QueryResult] = field(default_factory=list)
    """Results from individual queries."""

    merged_data: Optional[MunicipalFundingPrograms] = None
    """Merged and deduplicated data from all queries."""

    audit_file: Optional[str] = None
    total_cost: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


class MunicipalFundingResearcher:
    """
    Researches municipal funding programs using web search.

    This class orchestrates the research process:
    1. Constructs structured prompts for comprehensive funding research
    2. Executes searches via the configured provider
    3. Saves audit trails for reproducibility
    4. Parses results into structured schemas

    Example:
        researcher = MunicipalFundingResearcher()
        result = researcher.research("San Rafael", "California")

        # Access raw response
        print(result.raw_response.content)
        print(result.raw_response.citations)

        # Access parsed data (if parsing succeeded)
        if result.parsed_data:
            for program_id, program in result.parsed_data.programs.items():
                print(f"{program.program_name}: {program.description}")
    """

    # Topic-specific context for prompts
    TOPIC_CONTEXT = {
        "housing": (
            "affordable housing, housing trust funds, inclusionary housing, "
            "in-lieu fees, below market rate programs, and housing assistance"
        ),
        "transportation": (
            "local transit, bicycle infrastructure, pedestrian improvements, "
            "traffic calming, and transportation funding"
        ),
        "environment": (
            "climate action, sustainability programs, green building incentives, "
            "and environmental initiatives"
        ),
    }

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

    def research(
        self,
        municipality: str,
        state: str,
        topic: str = "housing",
        *,
        save_audit: bool = True,
    ) -> ResearchResult:
        """
        Research municipal funding programs.

        Args:
            municipality: City name (e.g., "San Rafael").
            state: State name (e.g., "California").
            topic: Topic area to research (housing, transportation, environment).
            save_audit: Whether to save audit trail to disk.

        Returns:
            ResearchResult with raw response and parsed data.
        """
        # Build the research prompt
        prompt = self._build_prompt(municipality, state, topic)

        # Execute search
        search_result = self._provider.search(prompt)

        # Create result object
        result = ResearchResult(
            municipality=municipality,
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
        municipality: str,
        state: str,
        topic: str = "housing",
        *,
        save_audit: bool = True,
        max_workers: int = 3,
        delay_between_queries: float = 1.0,
        max_priority: int = 2,
    ) -> EnsembleResearchResult:
        """
        Research municipal funding programs using multiple focused queries.

        This method runs multiple targeted queries in parallel, then merges
        the results for more comprehensive coverage.

        Args:
            municipality: City name (e.g., "San Rafael").
            state: State name (e.g., "California").
            topic: Topic area to research.
            save_audit: Whether to save audit trail to disk.
            max_workers: Maximum parallel queries.
            delay_between_queries: Delay between queries (rate limiting).
            max_priority: Only run queries with priority <= this value.

        Returns:
            EnsembleResearchResult with merged data from all queries.
        """
        # Load municipality config
        config = self._load_municipality_config(municipality)

        # Build queries from templates + config
        queries = self._build_ensemble_queries(
            municipality, state, topic, config, max_priority
        )

        # Execute queries
        query_results = self._execute_queries(
            queries, max_workers, delay_between_queries
        )

        # Create result
        result = EnsembleResearchResult(
            municipality=municipality,
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

    def _load_municipality_config(self, municipality: str) -> MunicipalityConfig:
        """Load municipality-specific configuration if available."""
        slug = municipality.lower().replace(" ", "-")
        config_path = self._data_dir / slug / "research_config.yaml"
        return MunicipalityConfig.from_yaml(config_path)

    def _build_ensemble_queries(
        self,
        municipality: str,
        state: str,
        topic: str,
        config: MunicipalityConfig,
        max_priority: int,
    ) -> list[tuple[str, Optional[QueryTemplate]]]:
        """
        Build list of queries from templates and config.

        Returns list of (query_string, template_or_none) tuples.
        """
        queries = []

        # Get base templates for topic
        templates = get_templates_for_topic(topic)

        # Filter and apply overrides
        for template in templates:
            if template.key in config.skip_queries:
                continue
            if template.priority > max_priority:
                continue

            # Check for override
            if template.key in config.query_overrides:
                query = config.query_overrides[template.key].format(
                    municipality=municipality,
                    state=state,
                    year=datetime.now().year,
                )
            else:
                query = template.template.format(
                    municipality=municipality,
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
            query = f"{municipality} {state} {program}"
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

    def _save_ensemble_audit(self, result: EnsembleResearchResult) -> str:
        """Save ensemble audit trail to disk."""
        slug = result.municipality.lower().replace(" ", "-")
        municipality_dir = self._data_dir / slug
        municipality_dir.mkdir(parents=True, exist_ok=True)

        audit_file = municipality_dir / f"{result.topic}_ensemble_audit.json"

        # Build audit data
        audit_data = {
            "municipality": result.municipality,
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

    def _merge_results(
        self, result: EnsembleResearchResult
    ) -> Optional[MunicipalFundingPrograms]:
        """Merge results from multiple queries into unified structure."""
        try:
            slug = result.municipality.lower().replace(" ", "-")

            # Collect all citations
            all_citations = []
            for qr in result.query_results:
                all_citations.extend(qr.response.citations)
            all_citations = list(set(all_citations))  # Dedupe

            # Create base structure
            merged = MunicipalFundingPrograms(
                jurisdiction=f"city-{slug}",
                jurisdiction_type="municipal",
                topic=result.topic,
                last_updated=result.timestamp,
                data_sources=[
                    f"{self._provider.name} (ensemble, {len(result.query_results)} queries)",
                    "NEEDS HUMAN VERIFICATION",
                ],
                verification_status="DRAFT - NOT VERIFIED",
                source_citations=all_citations,
            )

            # Extract and merge programs from each query result
            for qr in result.query_results:
                content = qr.response.content
                programs = self._extract_programs_from_content(
                    content, result.municipality, qr.program_type
                )

                # Merge programs (newer overwrites older, or merge fields)
                for prog_id, program in programs.items():
                    if prog_id in merged.programs:
                        # Merge: keep more complete data
                        merged.programs[prog_id] = self._merge_programs(
                            merged.programs[prog_id], program
                        )
                    else:
                        merged.programs[prog_id] = program

                # Extract ballot measures
                measures = self._extract_ballot_measures_from_content(content)
                merged.ballot_measures.update(measures)

                # Extract contact info
                contacts = self._extract_contact_info(content)
                merged.contact_information.update(contacts)

            return merged

        except Exception:
            return None

    def _extract_programs_from_content(
        self,
        content: str,
        municipality: str,
        expected_type: Optional[str] = None,
    ) -> dict[str, FundingProgram]:
        """Extract programs from query response content."""
        programs = {}

        # Try structured extraction first
        structured = self._extract_programs_structured(content, municipality)
        if structured:
            programs.update(structured)

        # Also do keyword-based extraction for prose responses
        prose = self._extract_programs_from_prose(content, municipality, expected_type)
        for prog_id, program in prose.items():
            if prog_id not in programs:
                programs[prog_id] = program

        return programs

    def _extract_programs_from_prose(
        self,
        content: str,
        municipality: str,
        expected_type: Optional[str] = None,
    ) -> dict[str, FundingProgram]:
        """Extract programs from unstructured prose content."""
        programs = {}
        content_lower = content.lower()

        # Define extraction patterns
        patterns = [
            ("affordable_housing_trust_fund", r"housing trust fund|affordable housing fund", "Affordable Housing Trust Fund"),
            ("inclusionary_housing_program", r"inclusionary housing|in-lieu fee", "Inclusionary Housing Program"),
            ("commercial_linkage_fee", r"commercial linkage|linkage fee", "Commercial Linkage Fee Program"),
            ("bmr_rental_program", r"below market rate|bmr rental", "Below Market Rate Rental Program"),
            ("cdbg_home_passthrough", r"cdbg|community development block grant|home investment", "CDBG/HOME Pass-Through"),
        ]

        for prog_id, pattern, name in patterns:
            if re.search(pattern, content_lower):
                # Extract relevant paragraph(s)
                description = self._extract_relevant_text(content, pattern)

                programs[prog_id] = FundingProgram(
                    program_name=f"{municipality} {name}",
                    administering_agency="City Housing Division",
                    description=description or f"Municipal {name} program.",
                    keywords=prog_id.split("_"),
                )

        return programs

    def _extract_relevant_text(self, content: str, pattern: str) -> str:
        """Extract sentences containing the pattern."""
        sentences = re.split(r'(?<=[.!?])\s+', content)
        relevant = []
        for sentence in sentences:
            if re.search(pattern, sentence, re.IGNORECASE):
                relevant.append(sentence.strip())
        return " ".join(relevant[:3])  # First 3 relevant sentences

    def _extract_ballot_measures_from_content(self, content: str) -> dict[str, BallotMeasure]:
        """Extract ballot measures from content."""
        # Use the existing structured extraction
        return self._extract_ballot_measures_structured(content)

    def _merge_programs(
        self, existing: FundingProgram, new: FundingProgram
    ) -> FundingProgram:
        """Merge two programs, preferring more complete data."""
        # Prefer longer/more complete descriptions
        description = existing.description
        if len(new.description) > len(existing.description):
            description = new.description

        # Merge lists
        activities = list(set(existing.eligible_activities + new.eligible_activities))
        input_opps = list(set(existing.resident_input_opportunities + new.resident_input_opportunities))
        resolutions = list(set(existing.governing_resolutions + new.governing_resolutions))
        keywords = list(set(existing.keywords + new.keywords))

        # Merge requirements
        requirements = {**existing.eligibility_requirements, **new.eligibility_requirements}

        # Prefer non-None values
        return FundingProgram(
            program_name=new.program_name or existing.program_name,
            administering_agency=new.administering_agency or existing.administering_agency,
            description=description,
            eligible_activities=activities,
            eligibility_requirements=requirements,
            annual_funding_available=new.annual_funding_available or existing.annual_funding_available,
            local_compliance_required=existing.local_compliance_required,
            annual_reporting=existing.annual_reporting,
            resident_input_opportunities=input_opps,
            leverage_point=new.leverage_point or existing.leverage_point,
            official_url=new.official_url or existing.official_url,
            governing_ordinance=new.governing_ordinance or existing.governing_ordinance,
            governing_resolutions=resolutions,
            keywords=keywords,
        )

    def save_ensemble_data(
        self,
        result: EnsembleResearchResult,
        output_file: Optional[str] = None,
    ) -> str:
        """Save merged ensemble data to structured JSON file."""
        if result.merged_data is None:
            raise ValueError(
                "No merged data available. Raw responses saved to audit file: "
                f"{result.audit_file}"
            )

        if output_file is None:
            slug = result.municipality.lower().replace(" ", "-")
            output_file = str(
                self._data_dir / slug / f"{result.topic}_programs.json"
            )

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(result.merged_data.model_dump(mode="json"), f, indent=2)

        return output_file

    def _build_prompt(self, municipality: str, state: str, topic: str) -> str:
        """Build the research prompt for the given municipality and topic."""
        topic_desc = self.TOPIC_CONTEXT.get(topic, topic)

        return f"""Research the City of {municipality}, {state}'s municipal funding programs related to {topic_desc}.

Return a structured response using EXACTLY this format for each program found. Use "NOT_FOUND" for any field where data is unavailable.

---
PROGRAM: Affordable Housing Trust Fund
program_name: [Official name]
administering_agency: [City department name]
description: [2-3 sentence description]
fund_sources: [List sources: in-lieu fees, general fund, grants, etc.]
annual_funding_available: [Dollar amount or NOT_FOUND]
eligible_activities:
- [Activity 1]
- [Activity 2]
- [Activity 3]
application_process: [Description of how to apply]
application_deadline: [Date or "Rolling" or NOT_FOUND]
affordability_period_years: [Number or NOT_FOUND]
governing_resolution: [Resolution number or NOT_FOUND]
official_url: [URL or NOT_FOUND]
contact_phone: [Phone or NOT_FOUND]
contact_email: [Email or NOT_FOUND]
resident_input_opportunities:
- [Opportunity 1]
- [Opportunity 2]
leverage_point: [How residents can influence this program]

---
PROGRAM: Inclusionary Housing Program
program_name: [Official name]
administering_agency: [City department]
description: [2-3 sentence description]
affordable_percentage_required: [e.g., "5%" or NOT_FOUND]
project_threshold: [e.g., "10+ units" or NOT_FOUND]
in_lieu_fee_current_amount: [Dollar amount per unit]
in_lieu_fee_effective_date: [Date]
fee_adjustment_method: [e.g., "California Construction Cost Index" or NOT_FOUND]
compliance_options:
- [Option 1: on-site units]
- [Option 2: off-site units]
- [Option 3: in-lieu fee]
governing_ordinance: [Municipal code section, e.g., "Section 14.16.030"]
governing_resolutions: [Resolution numbers]
official_url: [URL or NOT_FOUND]
resident_input_opportunities:
- [Opportunity 1]
leverage_point: [How residents can influence]

---
PROGRAM: Commercial Linkage Fee
program_name: [Official name]
administering_agency: [City department]
description: [2-3 sentence description]
fee_rates:
- office_per_sqft: [Dollar amount]
- retail_per_sqft: [Dollar amount]
- hotel_per_sqft: [Dollar amount]
exemption_threshold_sqft: [e.g., "2500" or NOT_FOUND]
effective_date: [Date]
nexus_study: [Study name and year or NOT_FOUND]
governing_ordinance: [Municipal code section]
official_url: [URL or NOT_FOUND]

---
PROGRAM: Ballot Measure [Letter]
measure_name: [e.g., "Measure P"]
full_title: [Official ballot title]
election_date: [Date]
status: [passed/failed]
description: [What it funds]
tax_rate: [e.g., "$0.145 per sqft" or NOT_FOUND]
annual_revenue: [Dollar amount or NOT_FOUND]
duration_years: [Number or NOT_FOUND]
exemptions:
- [Exemption 1]
official_url: [URL or NOT_FOUND]

---
PROGRAM: CDBG/HOME Pass-Through
program_name: [Official name]
administering_agency: [City department + county partner if applicable]
description: [2-3 sentence description]
cdbg_allocation: [Dollar amount or NOT_FOUND]
home_allocation: [Dollar amount or NOT_FOUND]
cooperative_agreement: [Description of county relationship or NOT_FOUND]
application_deadline: [Date or NOT_FOUND]
official_url: [URL or NOT_FOUND]
resident_input_opportunities:
- [Opportunity 1]

---
PROGRAM: Below Market Rate Rental Program
program_name: [Official name or NOT_FOUND if no dedicated program]
administering_agency: [City department]
description: [Description or NOT_FOUND]
income_limits: [e.g., "80% AMI" or NOT_FOUND]
official_url: [URL or NOT_FOUND]

---

Include ALL programs you find evidence of. If a program category doesn't exist for this city, write:
PROGRAM: [Category]
status: NOT_FOUND

Cite official .gov sources whenever possible. Be precise with dollar amounts, dates, and ordinance numbers."""

    def _save_audit(self, result: ResearchResult) -> str:
        """Save audit trail to disk."""
        # Create municipality directory
        slug = result.municipality.lower().replace(" ", "-")
        municipality_dir = self._data_dir / slug
        municipality_dir.mkdir(parents=True, exist_ok=True)

        # Audit file path
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
                "municipality": result.municipality,
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

        # Save
        with open(audit_file, "w") as f:
            json.dump(audit_data, f, indent=2)

        return str(audit_file)

    def _parse_response(self, result: ResearchResult) -> Optional[MunicipalFundingPrograms]:
        """
        Parse the raw response into structured data.

        Parses the structured YAML-like format from the prompt.
        """
        try:
            slug = result.municipality.lower().replace(" ", "-")

            # Create base structure
            data = MunicipalFundingPrograms(
                jurisdiction=f"city-{slug}",
                jurisdiction_type="municipal",
                topic=result.topic,
                last_updated=result.timestamp,
                data_sources=[
                    f"{self._provider.name} ({result.raw_response.model})",
                    "NEEDS HUMAN VERIFICATION",
                ],
                verification_status="DRAFT - NOT VERIFIED",
                source_citations=result.raw_response.citations,
            )

            # Extract programs from structured response
            content = result.raw_response.content
            data.programs = self._extract_programs_structured(content, result.municipality)
            data.ballot_measures = self._extract_ballot_measures_structured(content)

            # Extract contact info
            data.contact_information = self._extract_contact_info(content)

            return data

        except Exception:
            # Parsing failed, return None - raw data is still available
            return None

    def _extract_programs_structured(
        self, content: str, municipality: str
    ) -> dict[str, FundingProgram]:
        """Extract funding programs from structured response."""
        programs = {}

        # Split by program sections
        sections = re.split(r'\n---\s*\n', content)

        for section in sections:
            if not section.strip():
                continue

            # Check if this section has a PROGRAM header
            program_match = re.search(r'PROGRAM:\s*(.+?)(?:\n|$)', section)
            if not program_match:
                continue

            program_type = program_match.group(1).strip()

            # Skip NOT_FOUND programs
            if "status: NOT_FOUND" in section:
                continue

            # Generate program ID
            program_id = self._slugify(program_type)

            # Extract fields
            program = self._parse_program_section(section, program_type, municipality)
            if program:
                programs[program_id] = program

        return programs

    def _parse_program_section(
        self, section: str, program_type: str, municipality: str
    ) -> Optional[FundingProgram]:
        """Parse a single program section into a FundingProgram."""
        def extract_field(pattern: str, default: str = "") -> str:
            match = re.search(pattern, section, re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value and value != "NOT_FOUND" and not value.startswith("["):
                    return value
            return default

        def extract_list(pattern: str) -> list[str]:
            # Find the field and extract bullet points after it
            match = re.search(pattern + r'.*?(?:\n((?:- .+\n?)+))', section, re.MULTILINE)
            if match:
                items = re.findall(r'^- (.+)$', match.group(1), re.MULTILINE)
                return [item.strip() for item in items if item.strip() and item.strip() != "NOT_FOUND" and not item.startswith("[")]
            return []

        def extract_dollar(pattern: str) -> Optional[float]:
            match = re.search(pattern, section, re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value and value != "NOT_FOUND":
                    # Extract numeric value from strings like "$250,000" or "$1.5M"
                    num_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*([MmKk])?', value)
                    if num_match:
                        num = float(num_match.group(1).replace(',', ''))
                        multiplier = num_match.group(2)
                        if multiplier and multiplier.upper() == 'M':
                            num *= 1_000_000
                        elif multiplier and multiplier.upper() == 'K':
                            num *= 1_000
                        return num
            return None

        program_name = extract_field(r'^program_name:\s*(.+)$')
        if not program_name:
            program_name = f"{municipality} {program_type}"

        return FundingProgram(
            program_name=program_name,
            administering_agency=extract_field(r'^administering_agency:\s*(.+)$', "City Housing Division"),
            description=extract_field(r'^description:\s*(.+)$', f"Municipal {program_type} program."),
            eligible_activities=extract_list(r'^eligible_activities:') or extract_list(r'^compliance_options:'),
            eligibility_requirements=self._extract_requirements(section),
            annual_funding_available=extract_dollar(r'^annual_funding_available:\s*(.+)$') or extract_dollar(r'^cdbg_allocation:\s*(.+)$'),
            local_compliance_required=True,
            annual_reporting=True,
            resident_input_opportunities=extract_list(r'^resident_input_opportunities:'),
            leverage_point=extract_field(r'^leverage_point:\s*(.+)$'),
            official_url=extract_field(r'^official_url:\s*(.+)$') or None,
            governing_ordinance=extract_field(r'^governing_ordinance:\s*(.+)$') or None,
            governing_resolutions=self._extract_resolutions(section),
            keywords=self._generate_keywords(program_type),
        )

    def _extract_requirements(self, section: str) -> dict[str, str]:
        """Extract eligibility requirements from section."""
        requirements = {}

        # Look for specific requirement fields
        patterns = [
            (r'^affordable_percentage_required:\s*(.+)$', 'affordable_percentage'),
            (r'^project_threshold:\s*(.+)$', 'project_threshold'),
            (r'^in_lieu_fee_current_amount:\s*(.+)$', 'in_lieu_fee'),
            (r'^affordability_period_years:\s*(.+)$', 'affordability_period'),
            (r'^income_limits:\s*(.+)$', 'income_limits'),
            (r'^exemption_threshold_sqft:\s*(.+)$', 'exemption_threshold'),
        ]

        for pattern, key in patterns:
            match = re.search(pattern, section, re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value and value != "NOT_FOUND" and not value.startswith("["):
                    requirements[key] = value

        return requirements

    def _extract_resolutions(self, section: str) -> list[str]:
        """Extract resolution numbers from section."""
        resolutions = []

        # Look for Resolution patterns
        matches = re.findall(r'Resolution\s+(\d+)', section, re.IGNORECASE)
        resolutions.extend([f"Resolution {num}" for num in matches])

        # Also check governing_resolutions field
        match = re.search(r'^governing_resolutions?:\s*(.+)$', section, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if value and value != "NOT_FOUND":
                # Split by comma or semicolon
                parts = re.split(r'[,;]', value)
                for part in parts:
                    part = part.strip()
                    if part and not part.startswith("["):
                        resolutions.append(part)

        return list(set(resolutions))  # Dedupe

    def _extract_ballot_measures_structured(self, content: str) -> dict[str, BallotMeasure]:
        """Extract ballot measures from structured response."""
        measures = {}

        # Split by program sections
        sections = re.split(r'\n---\s*\n', content)

        for section in sections:
            if "PROGRAM: Ballot Measure" not in section:
                continue

            if "status: NOT_FOUND" in section:
                continue

            # Extract measure letter
            letter_match = re.search(r'measure_name:\s*Measure\s+([A-Z])', section)
            if not letter_match:
                # Try from header
                letter_match = re.search(r'PROGRAM: Ballot Measure\s+([A-Z])', section)

            if letter_match:
                letter = letter_match.group(1)
                measure_id = f"measure_{letter.lower()}"

                def extract_field(pattern: str, default: str = "") -> str:
                    match = re.search(pattern, section, re.MULTILINE)
                    if match:
                        value = match.group(1).strip()
                        if value and value != "NOT_FOUND" and not value.startswith("["):
                            return value
                    return default

                def extract_int(pattern: str) -> Optional[int]:
                    match = re.search(pattern, section, re.MULTILINE)
                    if match:
                        value = match.group(1).strip()
                        if value and value != "NOT_FOUND":
                            num_match = re.search(r'(\d+)', value)
                            if num_match:
                                return int(num_match.group(1))
                    return None

                def extract_dollar(pattern: str) -> Optional[float]:
                    match = re.search(pattern, section, re.MULTILINE)
                    if match:
                        value = match.group(1).strip()
                        if value and value != "NOT_FOUND":
                            num_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*([MmKk])?', value)
                            if num_match:
                                num = float(num_match.group(1).replace(',', ''))
                                multiplier = num_match.group(2)
                                if multiplier and multiplier.upper() == 'M':
                                    num *= 1_000_000
                                elif multiplier and multiplier.upper() == 'K':
                                    num *= 1_000
                                return num
                    return None

                measures[measure_id] = BallotMeasure(
                    measure_name=f"Measure {letter}",
                    title=extract_field(r'^full_title:\s*(.+)$', f"Local Measure {letter}"),
                    description=extract_field(r'^description:\s*(.+)$', "See audit trail for details."),
                    election_date=extract_field(r'^election_date:\s*(.+)$') or None,
                    status=extract_field(r'^status:\s*(.+)$', "unknown"),
                    annual_revenue=extract_dollar(r'^annual_revenue:\s*(.+)$'),
                    duration_years=extract_int(r'^duration_years:\s*(.+)$'),
                    tax_rate=extract_field(r'^tax_rate:\s*(.+)$') or None,
                    exemptions=self._extract_list_field(section, r'^exemptions:'),
                    official_url=extract_field(r'^official_url:\s*(.+)$') or None,
                )

        return measures

    def _extract_list_field(self, section: str, pattern: str) -> list[str]:
        """Extract a list field from section."""
        match = re.search(pattern + r'.*?(?:\n((?:- .+\n?)+))', section, re.MULTILINE)
        if match:
            items = re.findall(r'^- (.+)$', match.group(1), re.MULTILINE)
            return [item.strip() for item in items if item.strip() and item.strip() != "NOT_FOUND" and not item.startswith("[")]
        return []

    def _extract_contact_info(self, content: str) -> dict[str, ContactInfo]:
        """Extract contact information from content."""
        contacts = {}

        # Look for phone numbers
        phone_match = re.search(r'contact_phone:\s*(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})', content)
        email_match = re.search(r'contact_email:\s*([\w.+-]+@[\w-]+\.[\w.-]+)', content)

        if phone_match or email_match:
            contacts["housing_division"] = ContactInfo(
                name="Housing Division",
                phone=phone_match.group(1) if phone_match else None,
                email=email_match.group(1) if email_match else None,
            )

        return contacts

    def _slugify(self, text: str) -> str:
        """Convert text to a slug identifier."""
        # Remove special characters, lowercase, replace spaces with underscores
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[-\s]+', '_', slug)
        return slug.strip('_')

    def _generate_keywords(self, program_type: str) -> list[str]:
        """Generate keywords from program type."""
        # Split on spaces and common separators
        words = re.split(r'[\s/]+', program_type.lower())
        # Filter out common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'to', 'in'}
        return [w for w in words if w and w not in stopwords]

    def save_structured_data(
        self,
        result: ResearchResult,
        output_file: Optional[str] = None,
    ) -> str:
        """
        Save parsed data to structured JSON file.

        Args:
            result: Research result with parsed data.
            output_file: Output file path. If None, uses default location.

        Returns:
            Path to the saved file.

        Raises:
            ValueError: If result has no parsed data.
        """
        if result.parsed_data is None:
            raise ValueError(
                "No parsed data available. Raw response saved to audit file: "
                f"{result.audit_file}"
            )

        if output_file is None:
            slug = result.municipality.lower().replace(" ", "-")
            output_file = str(
                self._data_dir / slug / f"{result.topic}_programs.json"
            )

        # Ensure directory exists
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        # Save as JSON
        with open(output_file, "w") as f:
            json.dump(result.parsed_data.model_dump(mode="json"), f, indent=2)

        return output_file
