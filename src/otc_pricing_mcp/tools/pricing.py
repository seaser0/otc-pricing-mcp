"""Pricing query tools: query_pricing, find_compute_flavor."""

from __future__ import annotations

from typing import Any


def query_pricing(
    services: list[str],
    region: str | None = None,
    max_results: int | None = None,
    **filters: Any,
) -> dict[str, Any]:
    """Query pricing data with flexible filtering.

    Args:
        services: List of service names (e.g., ['ecs', 'evs']).
        region: Optional region filter (e.g., 'eu-de', 'eu-nl', 'eu-ch2').
        max_results: Maximum number of results per service (default: 5000).
        **filters: Additional API filter parameters (e.g., productFamily, category).

    Returns:
        Dictionary with service names as keys and lists of price items as values.
    """
    raise NotImplementedError("Story 2 implementation pending")


def find_compute_flavor(
    v_cpu: int,
    ram_gb: float,
    os: str | None = None,
    region: str = "eu-de",
) -> list[dict[str, Any]]:
    """Find compute (ECS) instances matching vCPU/RAM/OS criteria.

    Args:
        v_cpu: Virtual CPUs.
        ram_gb: RAM in GiB.
        os: OS type (Linux, Windows, etc.). If None, returns all OS types.
        region: Region (default: eu-de).

    Returns:
        List of matching compute flavor records.
    """
    raise NotImplementedError("Story 2 implementation pending")
