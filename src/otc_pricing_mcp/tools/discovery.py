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

    Args:
        service: Service name (e.g., 'ecs').

    Returns:
        Dictionary with service metadata and available columns.
        Structure: {
            'service': str,
            'columns': {column_name: column_label, ...},
            'filterable_columns': [str, ...],
            'returnable_columns': [str, ...],
            'actually_used_columns': [str, ...]  # columns with real values in a sample row
        }

    Note:
        The upstream OTC API returns a global column list (the union of all
        service schemas), not a per-service projection. 'actually_used_columns'
        is derived by sampling one real row and retaining only columns that carry
        a non-empty value for this service — making it a practical filter guide.

    Raises:
        ValueError: If service is empty or not found in the catalog.
    """
    # Issue #35: reject empty/blank service names before touching the network.
    if not service or not service.strip():
        raise ValueError("service is required and must be non-empty")

    # Issue #35/#34: validate against catalog so unknown services yield a clear
    # domain error instead of a 500 that leaks the upstream URL.
    known = _load_catalog()
    if known and service not in known:
        hint = ", ".join(known[:20])
        raise ValueError(
            f"Service {service!r} not found in catalog. "
            f"Known (first 20): [{hint}]. Use list_services() for the full list."
        )

    client = OTCPricingClient()
    try:
        response = client.get({"serviceName": service, "limitMax": "1"})
        if not response.columns:
            raise ValueError(f"Service '{service}' not found or has no columns")

        # Issue #37: determine which columns are actually populated for this
        # service by inspecting the first sample row.
        actually_used: list[str] = []
        raw_rows: list[dict[str, Any]] = []
        if isinstance(response.result, dict):
            raw_rows = response.result.get(service, [])
        elif isinstance(response.result, list):
            raw_rows = response.result

        if raw_rows:
            row = raw_rows[0]
            actually_used = sorted(
                col
                for col in response.columns
                if str(row.get(col, "")).strip() not in ("", "-", "N/A")
            )

        return {
            "service": service,
            "columns": response.columns,
            "filterable_columns": sorted(response.columns.keys()),
            "returnable_columns": sorted(response.columns.keys()),
            "actually_used_columns": actually_used,
        }
    finally:
        client.close()
