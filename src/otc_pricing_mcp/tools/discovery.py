"""Discovery tools: list_services, list_regions, get_service_schema."""

from __future__ import annotations

from typing import Any


def list_services() -> list[str]:
    """List all available services with pricing data.

    Returns:
        List of service names (e.g., ['ecs', 'evs', 'obs']).
    """
    raise NotImplementedError("Story 2 implementation pending")


def list_regions() -> list[str]:
    """List all available regions.

    Returns:
        List of region codes (e.g., ['eu-de', 'eu-nl', 'eu-ch2']).
    """
    raise NotImplementedError("Story 2 implementation pending")


def get_service_schema(service: str) -> dict[str, Any]:
    """Get the schema for a service.

    Args:
        service: Service name (e.g., 'ecs').

    Returns:
        Dictionary with 'filterable' and 'returnable' column lists.
    """
    raise NotImplementedError("Story 2 implementation pending")
