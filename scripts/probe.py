#!/usr/bin/env python3
"""
Extended OTC Price Calculator API probe.

Discovers:
- Complete catalog of services, regions, and currencies
- Correct filterBy syntax for region-based filtering
- Currency behavior across regions
- Pagination and multi-service request patterns

Endpoint: https://calculator.otc-service.com/en/open-telekom-price-api/

Run:    python3 scripts/probe.py
Output: stdout summary + detailed JSON dumps in ./probe_results/
Deps:   stdlib only
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://calculator.otc-service.com/en/open-telekom-price-api/"
RESULTS_DIR = Path("probe_results")
TIMEOUT = 30
UA = "otc-price-api-probe/2.0"


def fetch(params: list[tuple[str, str]], label: str) -> dict[str, Any] | None:
    """GET request with params; save raw body; return parsed JSON or None."""
    qs = urlencode(params)
    url = f"{BASE_URL}?{qs}"
    print(f"\n--- {label} ---")
    print(f"  URL: {url[:120]}...")

    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=TIMEOUT) as r:
            status = r.status
            body = r.read().decode("utf-8")
        print(f"  HTTP {status}")
    except HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {status} (error response)")
    except URLError as e:
        print(f"  CONNECTION FAILED: {e}")
        return None

    out = RESULTS_DIR / f"{label}.json"
    out.write_text(body, encoding="utf-8")
    print(f"  Saved → {out.name}")

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"  Non-JSON body (first 300 chars): {body[:300]}")
        return None


def items_for(data: dict | None, service: str = "") -> list[dict]:
    """Extract items list from response, handling both dict and list shapes."""
    if not data:
        return []
    result = data.get("response", {}).get("result")
    if isinstance(result, dict):
        if service:
            return result.get(service, []) or []
        # If no service specified, merge all services
        items = []
        for svc_items in result.values():
            if isinstance(svc_items, list):
                items.extend(svc_items)
        return items
    if isinstance(result, list):
        return result
    return []


def get_all_services(data: dict | None) -> set[str]:
    """Extract all service names from response."""
    if not data:
        return set()
    result = data.get("response", {}).get("result")
    if isinstance(result, dict):
        return set(result.keys())
    return set()


# ========================== CATALOG DISCOVERY ========================== #

def discover_all_services_paginated() -> list[str]:
    """Discover all available services by paginating through results without a service filter."""
    print("\n" + "="*70)
    print("SERVICE DISCOVERY (paginated)")
    print("="*70)

    all_services = set()
    limit = 100
    offset = 0
    max_pages = 20  # Safety limit

    for page in range(1, max_pages + 1):
        params = [
            ("productType", "OTC"),
            ("limitMax", str(limit)),
            ("limitFrom", str(offset)),
        ]
        data = fetch(params, f"services_page_{page}")

        services = get_all_services(data)
        if not services:
            print(f"  Page {page}: no services (reached end)")
            break
        all_services.update(services)
        print(f"  Page {page}: found {len(services)} services")
        offset += limit

    result = sorted(all_services)
    print(f"\n  Total unique services: {len(result)}")
    return result


def fetch_service_full_catalog(service: str, max_limit: int = 5000) -> dict[str, Any] | None:
    """Fetch full catalog for a service with limitMax."""
    print(f"\n  {service:10s}", end=" ")

    data = fetch(
        [("productType", "OTC"), ("serviceName", service), ("limitMax", str(max_limit))],
        f"service_{service}_full"
    )

    if data:
        stats = data.get("response", {}).get("stats", {})
        items = items_for(data, service)

        regions = set()
        currencies = set()
        region_currency_pairs = set()

        for item in items:
            region = item.get("region")
            currency = item.get("currency")
            regions.add(region)
            currencies.add(currency)
            region_currency_pairs.add((region, currency))

        print(f"→ {len(items):4d} items | regions: {','.join(sorted(regions)):20s} | currencies: {','.join(sorted(currencies)):10s}")

        return {
            "service": service,
            "total": stats.get("count", 0),
            "returned": len(items),
            "regions": sorted(regions),
            "currencies": sorted(currencies),
            "region_currency_pairs": sorted(region_currency_pairs),
        }
    else:
        print("FAILED")
    return None


def test_filter_syntax_on_service(service: str) -> dict[str, Any]:
    """Test filterBy syntax on a service and collect working example."""
    print(f"\n  Testing {service}...")

    results = {}

    # Test the main syntax variant
    params = [
        ("productType", "OTC"),
        ("serviceName", service),
        ("filterBy[region]", "eu-ch2"),
        ("limitMax", "100"),
    ]

    data = fetch(params, f"filter_test_{service}_eu_ch2")

    if data:
        stats = data.get("response", {}).get("stats", {})
        items = items_for(data, service)

        results["service"] = service
        results["filter_syntax"] = "filterBy[region]=eu-ch2"
        results["total_matching"] = stats.get("count", 0)
        results["returned"] = len(items)
        results["sample_item"] = items[0] if items else None

    return results


def build_catalog_inventory(service_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Build comprehensive catalog inventory."""
    print("\n" + "="*70)
    print("CATALOG INVENTORY SUMMARY")
    print("="*70)

    all_regions = set()
    all_currencies = set()
    all_region_currency_pairs = set()

    for summary in service_summaries:
        for region in summary.get("regions", []):
            all_regions.add(region)
        for currency in summary.get("currencies", []):
            all_currencies.add(currency)
        for pair in summary.get("region_currency_pairs", []):
            all_region_currency_pairs.add(pair)

    total_records = sum(s['total'] for s in service_summaries)
    print(f"  Services discovered: {len(service_summaries)}")
    print(f"  Total records: {total_records}")
    print(f"  Unique regions: {sorted(all_regions)}")
    print(f"  Unique currencies: {sorted(all_currencies)}")
    print(f"  Region/Currency pairs: {sorted(all_region_currency_pairs)}")

    # Check for Swiss presence
    swiss_services = [s for s in service_summaries if 'eu-ch2' in s.get('regions', [])]
    print(f"  Services with eu-ch2: {[s['service'] for s in swiss_services]}")

    return {
        "probe_date": datetime.now().isoformat(),
        "services": service_summaries,
        "all_regions": sorted(all_regions),
        "all_currencies": sorted(all_currencies),
        "all_region_currency_pairs": sorted(all_region_currency_pairs),
    }


# ========================== MAIN ========================== #

def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    print(f"Probing: {BASE_URL}")
    print(f"Results: {RESULTS_DIR.resolve()}")
    print(f"Started: {datetime.now().isoformat()}")

    try:
        # 1. Service discovery
        services = discover_all_services_paginated()

        if not services:
            print("\nNo services discovered!")
            sys.exit(1)

        # 2. Full catalog for each service
        print("\n" + "="*70)
        print("FULL CATALOGS PER SERVICE (limitMax=5000)")
        print("="*70)
        service_summaries = []
        for service in services:
            summary = fetch_service_full_catalog(service)
            if summary:
                service_summaries.append(summary)

        # 3. Filter syntax test on a service with eu-ch2
        swiss_services = [s for s in service_summaries if 'eu-ch2' in s.get('regions', [])]
        if swiss_services:
            print("\n" + "="*70)
            print("FILTER SYNTAX VALIDATION (eu-ch2 test)")
            print("="*70)
            test_service = swiss_services[0]['service']
            filter_result = test_filter_syntax_on_service(test_service)

        # 4. Build inventory summary
        inventory = build_catalog_inventory(service_summaries)

        # 5. Save inventory as JSON
        inventory_path = RESULTS_DIR / "catalog_inventory.json"
        inventory_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        print(f"\n  Inventory saved to {inventory_path.name}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "="*70)
    print("PROBE COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
