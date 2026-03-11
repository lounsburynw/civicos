"""
Bridge between CivicOS ToolRegistry and FastMCP.

Creates a FastMCP server from our existing ToolRegistry by generating
typed wrapper functions with injected signatures. This lets FastMCP
introspect parameters for its Streamable HTTP transport while keeping
all 39 tool handlers unchanged.
"""

import inspect
from typing import Optional

from fastmcp import FastMCP
from fastmcp.tools import Tool

# Map JSON Schema types to Python types for signature injection
JSON_TO_PYTHON = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def create_fastmcp_server(registry, jurisdiction_config, auth=None):
    """Create a FastMCP server from a ToolRegistry with bound handlers."""
    mcp = FastMCP(
        name=f"CivicOS ({jurisdiction_config.display_name})",
        auth=auth,
    )

    for tool_name, tool_def in registry.tools.items():
        if "handler" not in tool_def:
            continue
        _register_tool(mcp, tool_name, tool_def, registry)

    return mcp


def _register_tool(mcp, name, tool_def, registry):
    """Register a single tool with FastMCP using signature injection."""
    schema = tool_def.get("inputSchema", {})
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Build typed parameters from JSON Schema, required params first
    params = []
    for pname in sorted(properties, key=lambda p: p not in required):
        pdef = properties[pname]
        py_type = JSON_TO_PYTHON.get(pdef.get("type", "string"), str)
        if pname in required:
            default = inspect.Parameter.empty
        else:
            # Optional params: use schema default if present, else None
            default = pdef.get("default")
            py_type = Optional[py_type]
        params.append(inspect.Parameter(
            pname,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=default,
            annotation=py_type,
        ))

    sig = inspect.Signature(params, return_annotation=str)

    # Create wrapper that converts kwargs back to dict for registry.call_tool
    def make_wrapper(tool_name):
        def wrapper(**kwargs):
            # Filter out None values so handlers see missing keys, not None
            args = {k: v for k, v in kwargs.items() if v is not None}
            return registry.call_tool(tool_name, args)
        wrapper.__name__ = tool_name
        wrapper.__doc__ = tool_def.get("description", "")
        wrapper.__signature__ = sig
        wrapper.__annotations__ = {p.name: p.annotation for p in params}
        wrapper.__annotations__["return"] = str
        return wrapper

    fn = make_wrapper(name)
    tool = Tool.from_function(fn, name=name, description=tool_def.get("description", ""))
    mcp.add_tool(tool)
