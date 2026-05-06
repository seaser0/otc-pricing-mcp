"""Discovery tools: list_services, list_regions, get_service_schema."""

from __future__ import annotations

from typing import Any

from otc_pricing_mcp.client import OTCPricingClient

# Service catalog (populated at module load)
_SERVICES_CACHE: list[str] | None = None
_REGIONS_CACHE: set[str] | None = None
_SERVICE_SCHEMAS_CACHE: dict[str, dict[str, Any]] | None = None


def _load_catalog() -> tuple[list[str], set[str]]:
    """Load service and region lists from API (cached after first call)."""
    global _SERVICES_CACHE, _REGIONS_CACHE

    if _SERVICES_CACHE is not None and _REGIONS_CACHE is not None:
        return (_SERVICES_CACHE, _REGIONS_CACHE)

    services: list[str] = []
    regions: set[str] = set()

    # Fetch all known OTC services with a minimal limit
    # We'll discover services by trying common ones + any found in the API response
    known_services = [
        "ecs",
        "evs",
        "obs",
        "rds",
        "dds",
        "vpcep",
        "nat",
        "elb",
        "lb",
        "apig",
        "dns",
        "cce",
        "cce-addon",
        "bms",
        "dms",
        "dli",
        "mlss",
        "modelarts",
        "iam",
        "kms",
        "ces",
        "lts",
        "aom",
        "dws",
        "gaussdb",
        "ctsdb",
        "dgraph",
        "dis",
        "mpc",
        "ges",
        "cts",
        "smn",
        "dcs",
        "dcaas",
        "dew",
        "cse",
    ]

    client = OTCPricingClient()
    try:
        for service in known_services:
            try:
                response = client.get({"serviceName": service, "limitMax": "1"})
                if response.result and isinstance(response.result, dict):
                    if service in response.result and response.result[service]:
                        services.append(service)
                        # Extract regions from result
                        for item in response.result[service]:
                            if "region" in item:
                                regions.add(item["region"])
                elif response.result and isinstance(response.result, list):
                    services.append(service)
                    for item in response.result:
                        if "region" in item:
                            regions.add(item["region"])
            except Exception:
                continue
    finally:
        client.close()

    _SERVICES_CACHE = services
    _REGIONS_CACHE = regions
    return (services, regions)


def list_services() -> list[str]:
    """List all available services with pricing data.

    Returns:
        List of service names (e.g., ['ecs', 'evs', 'obs']).
    """
    services, _ = _load_catalog()
    return sorted(services)


def list_regions() -> list[str]:
    """List all available regions.

    Returns:
        List of region codes (e.g., ['eu-de', 'eu-nl', 'eu-ch2']).
    """
    _, regions = _load_catalog()
    return sorted(regions)


def get_service_schema(service: str) -> dict[str, Any]:
    """Get the schema (columns) for a service.

    Args:
        service: Service name (e.g., 'ecs').

    Returns:
        Dictionary with service metadata and available columns.
        Structure: {
            'service': str,
            'columns': {column_name: column_label, ...},
            'filterable_columns': [str, ...],
            'returnable_columns': [str, ...]
        }

    Raises:
        ValueError: If service not found.
    """
    client = OTCPricingClient()
    try:
        response = client.get({"serviceName": service, "limitMax": "1"})
        if not response.columns:
            raise ValueError(f"Service '{service}' not found or has no columns")

        return {
            "service": service,
            "columns": response.columns,
            "filterable_columns": sorted(response.columns.keys()),
            "returnable_columns": sorted(response.columns.keys()),
        }
    finally:
        client.close()
