"""Pricing query tools: query_pricing, find_compute_flavor."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from otc_pricing_mcp.client import OTCPricingClient
from otc_pricing_mcp.models import PriceItem
from otc_pricing_mcp.normalize import extract_items

# Max concurrent HTTP requests for multi-service fan-out
MAX_CONCURRENT_REQUESTS = 5


def _fetch_service_pricing(
    service: str,
    params: dict[str, Any],
) -> tuple[str, list[PriceItem], str | None]:
    """Fetch pricing data for a single service (worker function for parallel execution).

    Args:
        service: Service name
        params: Query parameters (including productType, limitMax, filters)

    Returns:
        Tuple of (service, items, error_message)
        error_message is None on success, or error string on failure.
    """
    client = OTCPricingClient()
    try:
        service_params = {**params, "serviceName": service}
        response = client.get(service_params)
        items = extract_items(response, service)
        return (service, items, None)
    except Exception as e:
        return (service, [], str(e))
    finally:
        client.close()


def query_pricing(
    services: list[str],
    region: str | None = None,
    max_results: int | None = None,
    **filters: Any,
) -> dict[str, Any]:
    """Query pricing data with flexible filtering and column selection.

    This tool returns priced product entries for one or more OTC services.
    Filters use exact match on column values; column names come from get_service_schema.
    Each item carries its own currency (EUR or CHF depending on region).
    Pagination is automatic — the tool returns up to max_results items unless constrained.

    Multi-service requests are fanned out internally with up to 5 concurrent HTTP calls.
    Partial failures are reported in the warnings list.

    Args:
        services: List of service names (e.g., ['ecs', 'evs']). Required.
        region: Optional region filter (e.g., 'eu-de', 'eu-nl', 'eu-ch2').
                If provided, filters results to that region only.
        max_results: Maximum number of results to return (default: 5000).
        **filters: Additional filter parameters as column=value pairs
                   (e.g., productFamily="Compute", category="General Purpose").

    Returns:
        Dictionary with structure:
        {
            'services': {service_name: [item, ...], ...},
            'total_items': int,
            'currency_breakdown': {currency: count, ...},
            'regions_found': [region, ...],
            'warnings': [str, ...] (if any service failed)
        }

    Examples:
        # Single service, no filter
        >>> query_pricing(['ecs'])

        # Multiple services with region filter (parallel fan-out)
        >>> query_pricing(['ecs', 'evs'], region='eu-de')

        # With limit
        >>> query_pricing(['ecs'], max_results=100)
    """
    if not services:
        raise ValueError("At least one service name is required")

    max_results = max_results or 5000

    params: dict[str, Any] = {
        "productType": "OTC",
        "limitMax": str(max_results),
    }

    if region:
        params["filterBy[region]"] = region

    # Add additional filters
    for key, value in filters.items():
        params[f"filterBy[{key}]"] = value

    all_items: dict[str, list[PriceItem]] = {}
    total_items = 0
    currencies: dict[str, int] = {}
    regions_found: set[str] = set()
    warnings: list[str] = []

    # Use ThreadPoolExecutor for multi-service requests (with max concurrency)
    if len(services) > 1:
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            # Submit all service requests in parallel
            futures = {
                executor.submit(_fetch_service_pricing, service, params): service
                for service in services
            }

            # Collect results as they complete
            for future in as_completed(futures):
                service, items, error = future.result()
                if error:
                    warnings.append(f"{service}: {error}")
                elif items:
                    all_items[service] = items
                    total_items += len(items)
                    for item in items:
                        currencies[item.currency] = currencies.get(item.currency, 0) + 1
                        regions_found.add(item.region)
    else:
        # Single service: fetch directly without executor overhead
        service = services[0]
        _, items, error = _fetch_service_pricing(service, params)
        if error:
            warnings.append(f"{service}: {error}")
        elif items:
            all_items[service] = items
            total_items = len(items)
            for item in items:
                currencies[item.currency] = currencies.get(item.currency, 0) + 1
                regions_found.add(item.region)

    return {
        "services": {k: [item.model_dump() for item in v] for k, v in all_items.items()},
        "total_items": total_items,
        "currency_breakdown": currencies,
        "regions_found": sorted(regions_found),
        "warnings": warnings if warnings else [],
    }


def find_compute_flavor(
    v_cpu: int,
    ram_gb: float,
    os: str | None = None,
    region: str = "eu-de",
) -> list[dict[str, Any]]:
    """Find compute (ECS) instances matching vCPU/RAM/OS criteria.

    This is a convenience wrapper around query_pricing specifically for ECS instances.
    Searches for instances matching the requested vCPU and RAM specifications.

    Args:
        v_cpu: Virtual CPUs (e.g., 1, 2, 4, 8, 16).
        ram_gb: RAM in GiB (e.g., 1, 2, 4, 8, 16, 32).
        os: OS type filter (e.g., 'Linux', 'Windows', 'Oracle', 'SUSE', 'CentOS').
            If None, returns all OS types.
        region: Region (default: 'eu-de'). Options: 'eu-de', 'eu-nl', 'eu-ch2'.

    Returns:
        List of matching compute flavor records, each with pricing and specs.
        Empty list if no matches found.

    Examples:
        # Find 4-core, 8GB Linux instances in eu-de
        >>> find_compute_flavor(v_cpu=4, ram_gb=8, os='Linux', region='eu-de')

        # Find all 2-core, 4GB instances (any OS) in eu-nl
        >>> find_compute_flavor(v_cpu=2, ram_gb=4, region='eu-nl')
    """
    result = query_pricing(
        ["ecs"],
        region=region,
        max_results=5000,
    )

    matches: list[dict[str, Any]] = []
    for item_dict in result.get("services", {}).get("ecs", []):
        # Parse vCpu and ram fields
        v_cpu_str = item_dict.get("vCpu", "").strip()
        ram_str = item_dict.get("ram", "").strip()

        try:
            v_cpu_actual = int(v_cpu_str)
        except ValueError:
            continue

        # Parse RAM (e.g., "8 GiB" → 8)
        try:
            ram_actual = float(ram_str.split()[0])
        except (ValueError, IndexError):
            continue

        # Match vCPU and RAM
        if v_cpu_actual != v_cpu or abs(ram_actual - ram_gb) > 0.01:
            continue

        # Match OS if specified
        if os:
            os_unit = item_dict.get("osUnit", "").strip()
            if os.lower() not in os_unit.lower():
                continue

        matches.append(item_dict)

    return matches
