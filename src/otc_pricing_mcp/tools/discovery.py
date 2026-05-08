"""Discovery tools: list_services, list_regions, get_service_schema."""

from __future__ import annotations

from typing import Any

from otc_pricing_mcp.client import OTCPricingClient

# All three OTC regions, confirmed against the live API.
# eu-ch2 (Swiss OTC, CHF) only carries a subset of services (obs, kms, lts,
# hss, ito, apig, etc.) and never appears in per-service probes with small
# limitMax values, so region discovery must not rely on service sampling.
_KNOWN_REGIONS = ["eu-ch2", "eu-de", "eu-nl"]

# Service catalog (populated on first call)
_SERVICES_CACHE: list[str] | None = None


def _load_catalog() -> list[str]:
    """Discover available services from the API (cached after first call).

    Makes two requests:
    1. limitMax=1 (no serviceName) to read stats.count — total items in catalog.
    2. limitMax=stats.count to fetch the full catalog; the response dict keys
       are the service names.
    """
    global _SERVICES_CACHE

    if _SERVICES_CACHE is not None:
        return _SERVICES_CACHE

    services: list[str] = []
    client = OTCPricingClient()
    try:
        # Step 1: get total item count from a cheap probe.
        probe = client.get({"limitMax": "1"})
        total = probe.stats.count if probe.stats else 6000

        # Step 2: fetch the full catalog so every service appears as a dict key.
        response = client.get({"limitMax": str(total)})
        if isinstance(response.result, dict):
            services = sorted(k for k, v in response.result.items() if v)
        elif isinstance(response.result, list):
            seen: set[str] = set()
            for item in response.result:
                svc = item.get("serviceName", "")
                if svc and svc not in seen:
                    services.append(svc)
                    seen.add(svc)
            services = sorted(services)
    except Exception:
        pass
    finally:
        client.close()

    _SERVICES_CACHE = services
    return services


def list_services() -> list[str]:
    """List all available services with pricing data.

    Returns:
        Sorted list of service names (e.g., ['ecs', 'evs', 'obs']).
    """
    return _load_catalog()


def list_regions() -> list[str]:
    """List all available OTC regions.

    Returns:
        ['eu-ch2', 'eu-de', 'eu-nl']
    """
    return _KNOWN_REGIONS


def get_service_schema(service: str) -> dict[str, Any]:
    """Get the schema (columns) for a service.

    The upstream OTC API returns the same generic catalog schema for every
    service — the per-service projection is approximated here by sampling
    one row of the service and tagging which columns actually carry a value
    (`actually_used_columns`). See #37.

    Args:
        service: Service name (e.g., 'ecs').

    Returns:
        Dictionary with service metadata and available columns. Structure:
        {
            'service': str,
            'columns': {column_name: column_label, ...},  # full upstream catalog
            'filterable_columns': [str, ...],             # all columns the API accepts as filterBy
            'returnable_columns': [str, ...],             # all columns ever returned
            'actually_used_columns': [str, ...],          # subset that has a non-empty value on a sample row
            'note': str,                                  # warning that columns is the global catalog
        }

    Raises:
        ValueError: If service is empty/missing or not in the known catalog (#35).
    """
    if not service or not service.strip():
        raise ValueError("service is required and must be a non-empty string")
    known = list_services()
    if known and service not in known:
        # Show only a small sample so the error message stays readable.
        sample = known[:20]
        raise ValueError(
            f"Service {service!r} not found in catalog. "
            f"Known (first {len(sample)} of {len(known)}): {sample}. "
            f"Use list_services() for the full list."
        )

    client = OTCPricingClient()
    try:
        response = client.get({"serviceName": service, "limitMax": "1"})
        if not response.columns:
            raise ValueError(f"Service '{service}' not found or has no columns")

        # Best-effort actually_used projection: look at the first returned row.
        actually_used: list[str] = []
        sample_row: dict[str, Any] | None = None
        if isinstance(response.result, dict):
            rows = response.result.get(service) or []
            if rows:
                sample_row = rows[0]
        elif isinstance(response.result, list) and response.result:
            sample_row = response.result[0]
        if isinstance(sample_row, dict):
            actually_used = sorted(
                k for k, v in sample_row.items() if v not in ("", None, [], {}, "0")
            )

        return {
            "service": service,
            "columns": response.columns,
            "filterable_columns": sorted(response.columns.keys()),
            "returnable_columns": sorted(response.columns.keys()),
            "actually_used_columns": actually_used,
            "note": (
                "`columns` is the upstream API's GLOBAL catalog — every service "
                "shares the same schema. Filter on `actually_used_columns` for "
                "fields that are populated for THIS service (sample of 1 row)."
            ),
        }
    finally:
        client.close()
