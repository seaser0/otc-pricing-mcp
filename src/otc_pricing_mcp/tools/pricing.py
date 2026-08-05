"""Pricing query tools: query_pricing, find_compute_flavor."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from otc_pricing_mcp.client import DEFAULT_BASE_URL, V2_BASE_URL, V2_ONLY_SERVICES, OTCPricingClient
from otc_pricing_mcp.models import PriceItem
from otc_pricing_mcp.normalize import extract_items
from otc_pricing_mcp.tools.discovery import list_regions

# Max concurrent HTTP requests for multi-service fan-out
MAX_CONCURRENT_REQUESTS = 5

# v2 float fields → their "amount currency" string equivalents (for parse_price compat)
_V2_PRICE_FIELD_MAP = {
    "priceAmount": "priceAmountCalculated",
    "R12": "R12Calculated",
    "R24": "R24Calculated",
    "R36": "R36Calculated",
    "RU12": "RU12Calculated",
    "RU24": "RU24Calculated",
    "RU36": "RU36Calculated",
}


def _normalize_v2_item(item: dict[str, Any]) -> dict[str, Any]:
    """Remap v2 float price fields to their string-with-currency calculated equivalents.

    The v2 API returns priceAmount as a raw float (0.09177) while the v1 parser
    and estimation.py expect "0.091770 EUR" format. The v2 payload always includes
    *Calculated string variants — use those as the canonical price fields.
    """
    out = dict(item)
    for float_key, str_key in _V2_PRICE_FIELD_MAP.items():
        if str_key in out:
            out[float_key] = out[str_key]
    return out


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
    use_v2 = service in V2_ONLY_SERVICES
    client = OTCPricingClient(base_url=V2_BASE_URL if use_v2 else DEFAULT_BASE_URL)
    try:
        if use_v2:
            # v2 uses array-style params: serviceName[0]=memo&region[0]=eu-de
            v2_params: dict[str, Any] = {
                k: v
                for k, v in params.items()
                if not k.startswith("filterBy[region]") and k != "serviceName"
            }
            v2_params["serviceName[0]"] = service
            region_val = params.get("filterBy[region]")
            if region_val:
                v2_params["region[0]"] = region_val
            response = client.get(v2_params)
            # Normalize float price fields before PriceItem parsing
            if isinstance(response.result, dict) and service in response.result:
                response.result[service] = [
                    _normalize_v2_item(it) for it in response.result[service]
                ]
            items = extract_items(response, service)
        else:
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
            'warnings': [str, ...]  (upstream errors; triggers isError=true server-side)
            'notes': [str, ...]     (informational; e.g. valid combo with zero rows)
        }

    Raises:
        ValueError: If services is empty or region is not in the known region set.

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

    # Validate region against the known set so callers get a clear failure
    # instead of a silent empty result (see issue #6).
    if region is not None:
        known_regions = list_regions()
        if region not in known_regions:
            raise ValueError(
                f"Unknown region '{region}'. Known regions: {known_regions}. "
                f"Use list_regions() to discover available regions."
            )

    # Distinguish "omitted" (default 5000) from "explicitly 0/negative".
    # Falsy-check `max_results or 5000` collapses 0 → 5000 which silently
    # returns the full default page (see #33).
    if max_results is None:
        max_results = 5000
    elif max_results < 1:
        raise ValueError(f"max_results must be >= 1 (got {max_results})")

    params: dict[str, Any] = {
        "productType": "OTC",
        "limitMax": str(max_results),
    }

    if region:
        params["filterBy[region]"] = region
        # The OTC price calculator exposes the Swiss catalog (eu-ch2, CHF) only
        # when the undocumented `client=2` query parameter is set; without it
        # eu-ch2 queries return 0 rows even for services that exist there. See #50.
        if region == "eu-ch2":
            params["client"] = "2"

    # Add additional filters
    for key, value in filters.items():
        params[f"filterBy[{key}]"] = value

    all_items: dict[str, list[PriceItem]] = {}
    total_items = 0
    currencies: dict[str, int] = {}
    regions_found: set[str] = set()
    warnings: list[str] = []
    services_with_zero_rows: list[str] = []
    services_with_error: set[str] = set()

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
                    services_with_error.add(service)
                elif items:
                    all_items[service] = items
                    total_items += len(items)
                    for item in items:
                        currencies[item.currency] = currencies.get(item.currency, 0) + 1
                        regions_found.add(item.region)
                else:
                    services_with_zero_rows.append(service)
    else:
        # Single service: fetch directly without executor overhead
        service = services[0]
        _, items, error = _fetch_service_pricing(service, params)
        if error:
            warnings.append(f"{service}: {error}")
            services_with_error.add(service)
        elif items:
            all_items[service] = items
            total_items = len(items)
            for item in items:
                currencies[item.currency] = currencies.get(item.currency, 0) + 1
                regions_found.add(item.region)
        else:
            services_with_zero_rows.append(service)

    # Surface zero-row outcomes as informational notes so callers can tell
    # "request succeeded, no rows" apart from "request silently failed" (#6).
    notes: list[str] = []
    for service in sorted(services_with_zero_rows):
        if region:
            notes.append(
                f"{service}/{region}: upstream returned 0 rows for this combination "
                f"(the region may not be exposed by the price calculator API for this service)"
            )
        else:
            notes.append(f"{service}: upstream returned 0 rows")

    return {
        "services": {k: [item.model_dump() for item in v] for k, v in all_items.items()},
        "total_items": total_items,
        "currency_breakdown": currencies,
        "regions_found": sorted(regions_found),
        "warnings": warnings if warnings else [],
        "notes": notes,
    }


_COMPACT_FLAVOR_KEYS = (
    "flavor_id",
    "flavor_name",
    "v_cpu",
    "ram",
    "os_unit",
    "gpu_type",
    "gpu_count",
    "priceUSD",
    "unit",
)


def find_compute_flavor(
    v_cpu: int,
    ram_gb: float,
    os: str | None = None,
    region: str = "eu-de",
    limit: int = 20,
    include_pricing: bool = False,
) -> dict[str, Any]:
    """Find compute (ECS) instances matching vCPU/RAM/OS criteria.

    Args:
        v_cpu: Virtual CPUs (e.g., 1, 2, 4, 8, 16).
        ram_gb: RAM in GiB (e.g., 1, 2, 4, 8, 16, 32).
        os: OS type filter (e.g., 'Linux', 'Windows', 'Oracle', 'SUSE', 'CentOS').
            If None, returns all OS types.
        region: Region (default: 'eu-de'). Options: 'eu-de', 'eu-nl', 'eu-ch2'.
        limit: Maximum number of matches to return (default 20). When the cap is
               hit, 'truncated' and 'total_matches' fields are set in the response.
        include_pricing: Return the full pricing payload per match (default False).
                         When False, only compact fields are returned
                         (flavor_id, v_cpu, ram, os_unit, gpu_type, gpu_count,
                         priceUSD, unit). Use query_pricing for full detail.

    Returns:
        {
            'matches': [<flavor records>],
            'total_matches': <int>,   # total before limit
            'truncated': <bool>,
            'warnings': [<upstream error strings>],
            'notes': [<informational strings>, e.g. zero-row notice for the region]
        }

    Raises:
        ValueError: If region is not in the known region set, or if v_cpu/ram_gb
                    are not strictly positive (a 0-cpu/0-ram instance is nonsense
                    and used to silently match EVS storage rows — see #30).
    """
    if v_cpu < 1:
        raise ValueError(f"v_cpu must be >= 1 (got {v_cpu})")
    if ram_gb <= 0:
        raise ValueError(f"ram_gb must be > 0 (got {ram_gb})")

    result = query_pricing(["ecs"], region=region, max_results=5000)
    upstream_warnings: list[str] = list(result.get("warnings", []))
    upstream_notes: list[str] = list(result.get("notes", []))

    all_matches: list[dict[str, Any]] = []
    for item_dict in result.get("services", {}).get("ecs", []):
        # The price-calculator returns EVS storage rows under serviceName=ecs
        # (with product_id_parameter='ecs' but product_family='Storage'). We
        # want compute only — see #30.
        family = str(item_dict.get("product_family", "")).strip().lower()
        if family != "compute":
            continue

        v_cpu_str = str(item_dict.get("v_cpu", "")).strip()
        ram_str = str(item_dict.get("ram", "")).strip()

        try:
            v_cpu_actual = int(v_cpu_str)
        except ValueError:
            continue

        try:
            ram_actual = float(ram_str.split()[0])
        except (ValueError, IndexError):
            continue

        if v_cpu_actual != v_cpu or abs(ram_actual - ram_gb) > 0.01:
            continue

        if os:
            os_unit = str(item_dict.get("os_unit", "")).strip()
            if os.lower() not in os_unit.lower():
                continue

        all_matches.append(item_dict)

    total = len(all_matches)
    truncated = total > limit
    page = all_matches[:limit]

    if not include_pricing:
        page = [{k: row[k] for k in _COMPACT_FLAVOR_KEYS if k in row} for row in page]

    return {
        "matches": page,
        "total_matches": total,
        "truncated": truncated,
        "warnings": upstream_warnings,
        "notes": upstream_notes,
    }
