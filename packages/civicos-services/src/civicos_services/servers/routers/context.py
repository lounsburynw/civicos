"""
Context Assembly router — GET /api/context/{item_type}/{item_id}

Returns a rich context bundle for any civic item. Surface-agnostic:
Open WebUI, MCP, browser extensions, and widgets all use this endpoint.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .dependencies import verify_auth
from ...context import (
    assemble_context,
    ItemNotFoundError,
    RelayUnavailableError,
    ContextBundle,
    ContextDepth,
    ItemType,
)

logger = logging.getLogger("civicos.context.router")

router = APIRouter()

# Valid section names for request validation
VALID_SECTIONS = {"history", "regulatory", "financial", "testimony", "participation"}


@router.get(
    "/context/{item_type}/{item_id}",
    response_model=ContextBundle,
    summary="Assemble context for a civic item",
    responses={
        404: {"description": "Item not found"},
        422: {"description": "Invalid item_type or section name"},
        503: {"description": "Relay service unavailable (initiative items)"},
    },
)
async def get_context(
    item_type: ItemType,
    item_id: str,
    jurisdiction: str = Query(..., description="Jurisdiction ID (e.g., city-san-rafael)"),
    sections: Optional[str] = Query(None, description="Comma-separated sections to include (omit for all)"),
    depth: ContextDepth = Query(ContextDepth.standard, description="Context depth: minimal, standard, or deep"),
    _token: str = Depends(verify_auth),
):
    """
    Assemble a rich context bundle for any civic item.

    Given an item type and ID, returns the item details plus contextual
    sections (history, regulatory, financial, testimony, participation) assembled from existing CivicOS data.

    Sections are assembled in parallel with per-section timeout and
    error isolation. Failed sections return null with error details
    in metadata.section_status.
    """
    # Parse and validate section names
    requested_sections = None
    if sections:
        requested_sections = set(s.strip() for s in sections.split(",") if s.strip())
        invalid = requested_sections - VALID_SECTIONS
        if invalid:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Invalid section names",
                    "invalid": sorted(invalid),
                    "valid": sorted(VALID_SECTIONS),
                },
            )

    try:
        bundle = await assemble_context(
            item_type=item_type,
            item_id=item_id,
            jurisdiction=jurisdiction,
            sections=requested_sections,
            depth=depth,
        )
    except ItemNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Item not found",
                "message": str(e),
                "item_type": e.item_type,
                "item_id": e.item_id,
            },
        )
    except RelayUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Relay unavailable",
                "message": str(e),
            },
        )

    return bundle
