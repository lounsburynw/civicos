"""
Handler factory for CivicOS MCP server.

Returns handlers with jurisdiction configuration support.
Uses config-driven handlers where available, falls back to
original handlers.py implementations otherwise.
"""

from typing import Callable, Any

# Import original handlers
from ..tools import handlers as original_handlers

# Import config-driven handlers
from .jurisdiction import engagement

# Import tool categorization
from .loader import (
    JurisdictionConfig,
    load_jurisdiction_config,
    get_tools_for_level,
    TOOL_LEVELS,
)

# Type alias for handler function
HandlerFunc = Callable[..., str]


# Map of tools to config-driven handler replacements
CONFIG_DRIVEN_HANDLERS = {
    "compose_public_comment": engagement.compose_public_comment,
    "get_comment_guidelines": engagement.get_comment_guidelines,
    "get_comment_template": engagement.get_comment_template,
}


def get_handler(tool_name: str, use_config: bool = True) -> HandlerFunc | None:
    """
    Get the handler function for a tool.

    Args:
        tool_name: Name of the tool
        use_config: If True, use config-driven handlers where available

    Returns:
        Handler function or None if not found
    """
    # Check for config-driven replacement first
    if use_config and tool_name in CONFIG_DRIVEN_HANDLERS:
        return CONFIG_DRIVEN_HANDLERS[tool_name]

    # Fall back to original handler
    return getattr(original_handlers, tool_name, None)


def get_all_handlers(use_config: bool = True) -> dict[str, HandlerFunc]:
    """
    Get all handler functions.

    Args:
        use_config: If True, use config-driven handlers where available

    Returns:
        Dict mapping tool name to handler function
    """
    handlers = {}

    # Get all handler names from original module
    handler_names = [
        name for name in dir(original_handlers)
        if not name.startswith("_") and callable(getattr(original_handlers, name))
    ]

    for name in handler_names:
        handler = get_handler(name, use_config=use_config)
        if handler:
            handlers[name] = handler

    return handlers


def get_filtered_handlers(
    jurisdiction_id: str,
    use_config: bool = True,
) -> dict[str, HandlerFunc]:
    """
    Get handlers filtered by jurisdiction level.

    Only returns handlers for tools enabled at this jurisdiction's level.

    Args:
        jurisdiction_id: Jurisdiction identifier
        use_config: If True, use config-driven handlers where available

    Returns:
        Dict mapping tool name to handler function (filtered by level)
    """
    config = load_jurisdiction_config(jurisdiction_id)
    enabled_tools = config.get_enabled_tools()

    all_handlers = get_all_handlers(use_config=use_config)

    return {
        name: handler
        for name, handler in all_handlers.items()
        if name in enabled_tools
    }


def bind_handlers_to_registry(
    registry,
    jurisdiction_id: str,
    civic_client: Any,
    validate_input: Callable,
    logger: Any,
    use_config: bool = True,
):
    """
    Bind handlers to a tool registry with jurisdiction context.

    This is a convenience function for server.py to bind all handlers
    with the appropriate context.

    Args:
        registry: ToolRegistry instance
        jurisdiction_id: Jurisdiction identifier
        civic_client: CivicOS client instance
        validate_input: Input validation function
        logger: Logger instance
        use_config: If True, use config-driven handlers

    Returns:
        Dict mapping tool names to bound handlers
    """
    handlers = get_filtered_handlers(jurisdiction_id, use_config=use_config)

    bound_handlers = {}
    for tool_name, handler_func in handlers.items():
        # Create a closure that binds the context
        def make_bound_handler(handler):
            def bound_handler(args: dict) -> str:
                return handler(
                    civic_client,
                    jurisdiction_id,
                    validate_input,
                    logger,
                    args,
                )
            return bound_handler

        bound = make_bound_handler(handler_func)
        bound_handlers[tool_name] = bound

        # Bind to registry if it has the method
        if hasattr(registry, 'bind_handler'):
            try:
                registry.bind_handler(tool_name, bound)
            except ValueError:
                # Tool not in registry, skip
                pass

    return bound_handlers
