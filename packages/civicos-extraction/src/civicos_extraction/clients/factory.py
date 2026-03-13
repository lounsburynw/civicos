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
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")
