#!/usr/bin/env python3
"""
OTC Price Calculator API probe.

Discovers schema, filter syntax, currency behavior, pagination ceiling,
and multi-service request form for the Open Telekom Cloud Price Calculator.

Endpoint: https://calculator.otc-service.com/en/open-telekom-price-api/
(The trailing slash and /en/ segment matter — other forms return errors.)

Run:    python3 otc_price_api_probe.py
Output: stdout summary + raw JSON dumps in ./probe_results/
Deps:   stdlib only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://calculator.otc-service.com/en/open-telekom-price-api/"
RESULTS_DIR = Path("probe_results")
TIMEOUT = 30
UA = "otc-price-api-probe/1.0"


def fetch(params: Iterable, label: str) -> dict[str, Any] | None:
    """GET request with params; save raw body; return parsed JSON or None."""
    qs = urlencode(list(params), doseq=True)
    url = f"{BASE_URL}?{qs}"
    print(f"\n--- {label} ---")
    print(f"  URL: {url}")

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
    print(f"  Saved raw → {out}")

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"  Non-JSON body (first 300 chars): {body[:300]}")
        return None


def keys_matching(item: dict, *tokens: str) -> dict:
    """Subset of a dict whose keys (lowercased) contain any of the tokens."""
    return {k: v for k, v in item.items() if any(t in k.lower() for t in tokens)}


def items_for(data: dict | None, service: str) -> list[dict]:
    """Extract items list from response.

    The API returns `result` as either:
      - dict keyed by service name: {"ecs": [...], "evs": [...]}   (no filter)
      - flat list:                  [...]                          (with filterBy)
    This helper normalizes both into a single list.
    """
    if not data:
        return []
    result = data.get("response", {}).get("result")
    if isinstance(result, dict):
        return result.get(service, []) or []
    if isinstance(result, list):
        return result
    return []


def describe_result(data: dict | None) -> str:
    """One-line description of the `result` shape, for diagnostics."""
    if not data:
        return "no data"
    result = data.get("response", {}).get("result")
    if isinstance(result, dict):
        return f"dict with keys={list(result.keys())}"
    if isinstance(result, list):
        return f"flat list of {len(result)} items"
    return f"{type(result).__name__}: {result!r}"


# ----------------------------- tests ----------------------------- #

def test_1_schema() -> None:
    print("\n[1] SCHEMA DISCOVERY (service=ecs, limit=5)")
    data = fetch(
        [("productType", "OTC"), ("serviceName", "ecs"), ("limitMax", "5")],
        "01_schema",
    )
    if not data:
        return
    stats = data.get("response", {}).get("stats", {})
    items = items_for(data, "ecs")
    print(f"  Total ECS records reported: {stats.get('count')}")
    print(f"  Returned in this page:      {stats.get('recordsCount')}")
    if items:
        sample = items[0]
        print(f"  First-item fields ({len(sample)}):")
        for k in sorted(sample):
            v = str(sample[k])[:80]
            print(f"    {k}: {v}")


def test_2_regions() -> None:
    print("\n[2] REGION-LIKE FIELDS (broad sample)")
    data = fetch(
        [("productType", "OTC"), ("serviceName", "ecs"), ("limitMax", "100")],
        "02_regions",
    )
    items = items_for(data, "ecs")
    if not items:
        print("  No items returned.")
        return
    fields = set()
    for it in items:
        for k in it.keys():
            if any(t in k.lower() for t in ("region", "az", "zone", "location")):
                fields.add(k)
    print(f"  Candidate region-like fields: {sorted(fields)}")
    for f in sorted(fields):
        vals = sorted({str(it.get(f)) for it in items if it.get(f) is not None})
        print(f"  Distinct values in '{f}': {vals}")


def test_3_swiss_filter() -> None:
    print("\n[3] SWISS REGION FILTER (filterBy[region][0]=eu-ch2)")
    print("  NOTE: assumes column is literally named 'region'.")
    print("        If [2] reveals a different name (e.g. 'azCode'), rerun with that key.")
    data = fetch(
        [
            ("productType", "OTC"),
            ("serviceName", "ecs"),
            ("filterBy[region][0]", "eu-ch2"),
            ("limitMax", "10"),
        ],
        "03_swiss_filter",
    )
    if not data:
        return
    print(f"  Result shape: {describe_result(data)}")
    stats = data.get("response", {}).get("stats", {})
    items = items_for(data, "ecs")
    print(f"  Matching records: {stats.get('count')}")
    print(f"  Returned items:   {len(items)}")
    if items:
        relevant = keys_matching(items[0], "region", "az", "price", "currency", "cost", "fee")
        print(f"  Relevant fields in first match:")
        for k, v in sorted(relevant.items()):
            print(f"    {k}: {v}")


def test_4_currency() -> None:
    print("\n[4] CURRENCY: DE vs CH SAMPLES")
    de = fetch(
        [("productType", "OTC"), ("serviceName", "ecs"),
         ("filterBy[region][0]", "eu-de"), ("limitMax", "1")],
        "04a_currency_de",
    )
    ch = fetch(
        [("productType", "OTC"), ("serviceName", "ecs"),
         ("filterBy[region][0]", "eu-ch2"), ("limitMax", "1")],
        "04b_currency_ch",
    )

    def show(label: str, data: dict | None) -> None:
        items = items_for(data, "ecs")
        if not items:
            print(f"  {label}: no items returned")
            return
        relevant = keys_matching(items[0], "price", "cost", "currency", "fee", "rate", "amount")
        print(f"  {label} price/currency-related fields:")
        for k, v in sorted(relevant.items()):
            print(f"    {k}: {v}")

    show("DE (eu-de)", de)
    show("CH (eu-ch2)", ch)


def test_5_pagination() -> None:
    print("\n[5] PAGINATION CEILING (limitMax sweep)")
    for limit in (25, 50, 100, 250, 500, 1000, 2500, 5000):
        params = {"productType": "OTC", "serviceName": "ecs", "limitMax": str(limit)}
        url = f"{BASE_URL}?{urlencode(params)}"
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT) as r:
                data = json.loads(r.read())
        except HTTPError as e:
            print(f"  limitMax={limit:>5}: HTTP {e.code}")
            continue
        except (URLError, json.JSONDecodeError) as e:
            print(f"  limitMax={limit:>5}: ERROR {e}")
            continue
        stats = data.get("response", {}).get("stats", {})
        rpp = stats.get("recordsPerPage", "?")
        rc = stats.get("recordsCount", "?")
        cnt = stats.get("count", "?")
        print(f"  limitMax={limit:>5}: recordsPerPage={rpp}, recordsCount={rc}, total={cnt}")


def test_6_multi_service() -> None:
    print("\n[6] MULTI-SERVICE REQUEST FORMS")
    print("  Form A: repeated 'serviceName' parameter")
    a = fetch(
        [("productType", "OTC"), ("serviceName", "ecs"),
         ("serviceName", "evs"), ("limitMax", "2")],
        "06a_multi_repeated",
    )
    if a:
        print(f"  → {describe_result(a)}")

    print("  Form B: 'serviceName[]' bracket syntax")
    b = fetch(
        [("productType", "OTC"), ("serviceName[]", "ecs"),
         ("serviceName[]", "evs"), ("limitMax", "2")],
        "06b_multi_brackets",
    )
    if b:
        print(f"  → {describe_result(b)}")


# ----------------------------- main ----------------------------- #

def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    print(f"Probing: {BASE_URL}")
    print(f"Raw dumps: {RESULTS_DIR.resolve()}")
    try:
        test_1_schema()
        test_2_regions()
        test_3_swiss_filter()
        test_4_currency()
        test_5_pagination()
        test_6_multi_service()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)

    print("\n" + "=" * 60)
    print("KEY QUESTIONS TO ANSWER FROM THE OUTPUT ABOVE:")
    print("=" * 60)
    print("  [1] Real field names — is there a 'region' column, or different?")
    print("  [2] Does 'eu-ch2' appear in the unfiltered sample at all?")
    print("  [3] Did filterBy[region][0]=eu-ch2 actually narrow the result?")
    print("  [4] Do CH prices show CHF, or only EUR? Different field name?")
    print("  [5] Highest limitMax where recordsPerPage echoes back unchanged?")
    print("  [6] Which multi-service form is accepted (or both)?")


if __name__ == "__main__":
    main()
