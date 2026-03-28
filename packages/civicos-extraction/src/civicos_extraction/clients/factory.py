"""
Source factory: create platform-specific source/client from ExtractionConfig.

Extracted from validate.py to allow reuse by the onboarding pipeline.
"""


def create_source(config):
    """Create platform-specific source/client from ExtractionConfig.

    Args:
        config: ExtractionConfig instance with source_type, metadata, etc.

    Returns:
        Platform-specific source object (GranicusSource, ProudCitySource, etc.)

    Raises:
        ValueError: If source_type is not supported.
    """
    source_type = config.source_type

    if source_type == "granicus":
        from civicos_extraction.clients.granicus import GranicusSource
        return GranicusSource(config)
    elif source_type == "proudcity":
        from civicos_extraction.clients.proudcity import ProudCitySource
        return ProudCitySource(config)
    elif source_type == "legistar":
        from civicos_extraction.clients.legistar import LegistarClient
        client_name = config.metadata.get("client_name", config.jurisdiction_id)
        return LegistarClient(client_name, config.jurisdiction_id)
    elif source_type == "civicclerk":
        from civicos_extraction.clients.civicclerk import CivicClerkClient
        subdomain = config.metadata.get("subdomain", config.jurisdiction_id)
        return CivicClerkClient(subdomain, config.jurisdiction_id)
    elif source_type == "escribe":
        from civicos_extraction.clients.escribe import EScribeClient
        instance_name = config.metadata.get("instance_name", config.base_url)
        return EScribeClient(instance_name, config.jurisdiction_id)
    elif source_type == "simbli":
        from civicos_extraction.clients.simbli import SimbliClient
        board_url = config.metadata.get("board_url", config.base_url)
        return SimbliClient(board_url, config.jurisdiction_id)
    elif source_type == "boarddocs":
        from civicos_extraction.clients.boarddocs import BoardDocsClient
        app_path = config.metadata.get("app_path", "")
        committee_id = config.metadata.get("committee_id")
        return BoardDocsClient(app_path, config.jurisdiction_id, committee_id=committee_id)
    elif source_type == "universal":
        from civicos_extraction.clients.universal import UniversalSource
        return UniversalSource(config)
    # Election source types
    elif source_type == "civera_election_stats":
        from civicos_extraction.clients.civera_election_stats import CiveraElectionStatsClient
        county_slug = config.metadata.get("county_slug", "")
        graphql_url = config.metadata.get("graphql_url", "")
        if county_slug and not graphql_url:
            return CiveraElectionStatsClient.from_county(county_slug, jurisdiction_id=config.jurisdiction_id)
        return CiveraElectionStatsClient(
            jurisdiction_id=config.jurisdiction_id,
            graphql_url=graphql_url,
            county_slug=county_slug,
        )
    elif source_type == "marin_registrar_results":
        from civicos_extraction.clients.marin_registrar import MarinRegistrarResultsClient
        return MarinRegistrarResultsClient(jurisdiction_id=config.jurisdiction_id)
    elif source_type == "ca_sos_results":
        from civicos_extraction.clients.ca_sos_results import CASOSResultsClient
        return CASOSResultsClient(
            jurisdiction_id=config.jurisdiction_id,
        )
    elif source_type == "ca_sos_ballot_preview":
        from civicos_extraction.clients.ca_sos_ballot_preview import CASOSBallotPreviewClient
        return CASOSBallotPreviewClient(
            election_slug=config.metadata.get("election_slug", ""),
            election_date=config.metadata.get("election_date", ""),
            election_type=config.metadata.get("election_type", "primary"),
        )
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")
