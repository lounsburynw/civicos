"""
Civic Services Layer - API servers, platform clients, and processing pipelines.

Sub-packages:
    servers     - API and WebSocket servers (civic_api_integrated, civic_socketio_server)
    clients     - External API clients (CDP, Legistar, LegiScan, SeeClickFix, etc.)
    providers   - LLM provider abstractions (OpenAI, Anthropic, Google, Groq, etc.)
    processing  - Data transformation pipelines (agenda, testimony, retrospective)
    storage     - State management and persistence (state_manager, issue_storage)
    legislative - Legislative enrichment and discovery
    issues      - Issue detection, matching, and handling
    chat        - Chat routing and conversation management
    monitoring  - Dashboard, refresh automation, data source management
    core        - Core infrastructure (config, logging, model registry, LLM provider)
    utils       - Utility services (content cache, session manager)
    interfaces  - Abstract interfaces (participation mechanisms)

Usage:
    from civic_services.servers.civic_api_integrated import CivicAPI
    from civic_services.clients.legistar_client import LegistarClient
    from civic_services.core.llm_provider import get_provider_for_task
"""

__version__ = "0.1.0"
