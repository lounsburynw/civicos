"""
Query templates for municipal funding research.

Templates use Python format strings with these placeholders:
- {municipality}: City name (e.g., "San Rafael")
- {state}: State name (e.g., "California")
- {year}: Current year
- {year_range}: Recent year range (e.g., "2020-2024")

Municipalities can override templates via research_config.yaml.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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


# Default query templates for housing topic
HOUSING_QUERY_TEMPLATES: list[QueryTemplate] = [
    QueryTemplate(
        key="trust_fund",
        template="{municipality} {state} affordable housing trust fund funding allocation resolution",
        description="Search for housing trust fund details",
        program_type="affordable_housing_trust_fund",
        priority=1,
    ),
    QueryTemplate(
        key="inclusionary_fees",
        template="{municipality} {state} inclusionary housing in-lieu fee per unit {year}",
        description="Search for inclusionary housing fee amounts",
        program_type="inclusionary_housing_program",
        priority=1,
    ),
    QueryTemplate(
        key="inclusionary_ordinance",
        template="{municipality} {state} inclusionary housing ordinance municipal code requirements",
        description="Search for inclusionary housing ordinance details",
        program_type="inclusionary_housing_program",
        priority=2,
    ),
    QueryTemplate(
        key="commercial_linkage",
        template="{municipality} {state} commercial linkage fee per square foot office retail",
        description="Search for commercial linkage fee rates",
        program_type="commercial_linkage_fee",
        priority=1,
    ),
    QueryTemplate(
        key="ballot_measures",
        template="{municipality} {state} housing parcel tax ballot measure {year_range}",
        description="Search for housing-related ballot measures",
        program_type="ballot_measure",
        priority=1,
    ),
    QueryTemplate(
        key="cdbg_home",
        template="{municipality} {state} CDBG HOME federal funding allocation cooperative agreement",
        description="Search for federal pass-through funding",
        program_type="cdbg_home_passthrough",
        priority=1,
    ),
    QueryTemplate(
        key="bmr_rental",
        template="{municipality} {state} below market rate BMR rental housing program",
        description="Search for BMR rental program details",
        program_type="bmr_rental_program",
        priority=2,
    ),
    QueryTemplate(
        key="housing_element",
        template="{municipality} {state} housing element {year} affordable housing goals",
        description="Search for housing element information",
        program_type="housing_element",
        priority=3,
    ),
]

# Query templates by topic
QUERY_TEMPLATES_BY_TOPIC: dict[str, list[QueryTemplate]] = {
    "housing": HOUSING_QUERY_TEMPLATES,
    # Future: transportation, environment templates
}


def get_templates_for_topic(topic: str) -> list[QueryTemplate]:
    """Get query templates for a topic."""
    return QUERY_TEMPLATES_BY_TOPIC.get(topic, HOUSING_QUERY_TEMPLATES)


def format_template(
    template: QueryTemplate,
    municipality: str,
    state: str,
    year: Optional[int] = None,
    year_range: Optional[str] = None,
) -> str:
    """
    Format a query template with values.

    Args:
        template: The query template to format.
        municipality: City name.
        state: State name.
        year: Year for {year} placeholder. Defaults to current year.
        year_range: Year range for {year_range}. Defaults to "2020-{current_year}".

    Returns:
        Formatted query string.
    """
    if year is None:
        year = datetime.now().year
    if year_range is None:
        year_range = f"2020-{year}"

    return template.template.format(
        municipality=municipality,
        state=state,
        year=year,
        year_range=year_range,
    )


def build_queries_from_templates(
    templates: list[QueryTemplate],
    municipality: str,
    state: str,
    *,
    max_priority: int = 3,
) -> list[tuple[str, QueryTemplate]]:
    """
    Build query strings from templates.

    Args:
        templates: List of query templates.
        municipality: City name.
        state: State name.
        max_priority: Only include templates with priority <= this value.

    Returns:
        List of (query_string, template) tuples, sorted by priority.
    """
    queries = []
    for template in templates:
        if template.priority <= max_priority:
            query = format_template(template, municipality, state)
            queries.append((query, template))

    # Sort by priority
    queries.sort(key=lambda x: x[1].priority)
    return queries
