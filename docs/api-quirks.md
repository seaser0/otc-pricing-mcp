# OTC Price Calculator API — Quirks & Filter Syntax

**Document Date**: 2026-05-06
**API Endpoint**: `https://calculator.otc-service.com/en/open-telekom-price-api/`
**Status**: Empirically verified via `scripts/probe.py`

---

## SUMMARY: The Correct Filter Syntax

### Working Form (Confirmed ✓)
```
filterBy[region]=eu-ch2
```

**Example curl**:
```bash
curl "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=apig&filterBy%5Bregion%5D=eu-ch2&limitMax=100"
```

**Result** (HTTP 200):
```json
{
  "response": {
    "stats": {
      "count": 4,
      "recordsCount": 4
    },
    "result": [
      {
        "id": "OTC_APIG_S",
        "region": "eu-ch2",
        "currency": "EUR",
        "priceAmount": "0.000000 EUR",
        ...
      },
      ...
    ]
  }
}
```

### Broken Forms (Confirmed ✗)
- `filterBy[region][]=eu-ch2` — returns 0 items
- `filterBy[region][0]=eu-ch2` — returns 0 items
- `filterBy[region]=value` with missing `[region]` key wrapper — returns 0 items

---

## Why the Original `filterBy[region][0]=eu-ch2` Failed

The probe script initially used:
```
filterBy[region][0]=eu-ch2
```

This syntax was **wrong for this API**, even though it looks valid in a URL-encoded query string context. The API's backend filter parser expects a simple key-value pair:
```
filterBy[region]=eu-ch2
```

**Hypothesis**: The API likely uses a framework (e.g., Symfony, Laravel, or similar) that parses `filterBy[region]` as a dictionary key, not an array index. The `[0]` index was interpreted as a literal string concatenation (`filterBy[region][0]`) rather than array indexing, causing the parser to look for a non-existent key.

The test on 2026-05-06 confirmed that:
- Services with eu-ch2 support (apig, coss, dnprq, dnq) return **4, 11, 1, 1 items** respectively with the correct syntax.
- The same services returned **0 items** with the `[0]` indexed form.

---

## Result Shape Quirk: Dict vs. Flat List

The API returns fundamentally different JSON structures depending on whether filters are applied. **Clients must handle both.**

### Scenario 1: No Filter (Unfiltered Request)
```bash
curl "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=ecs&limitMax=5"
```

**Response** (`result` is a dict keyed by service name):
```json
{
  "response": {
    "result": {
      "ecs": [
        {
          "id": "OTC_S3M1_LI",
          "region": "eu-de",
          "currency": "EUR",
          "priceAmount": "0.051175 EUR",
          ...
        }
      ]
    }
  }
}
```

**Extract items**: `data["response"]["result"]["ecs"]`

### Scenario 2: With Filter (Filtered Request)
```bash
curl "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=ecs&filterBy%5Bregion%5D=eu-de&limitMax=5"
```

**Response** (`result` is a flat list; service name is lost):
```json
{
  "response": {
    "result": [
      {
        "id": "OTC_S3M1_LI",
        "region": "eu-de",
        "currency": "EUR",
        "priceAmount": "0.051175 EUR",
        ...
      }
    ]
  }
}
```

**Extract items**: `data["response"]["result"]`

### Implications for Wrapper Implementation

The wrapper's `extract_items()` function must:
1. Check the type of `response.result`.
2. If `dict`, extract by service name key.
3. If `list`, use directly.
4. Normalize both to a consistent internal structure before returning to users.

```python
def extract_items(response, service):
    result = response.get("result")
    if isinstance(result, dict):
        return result.get(service, [])
    elif isinstance(result, list):
        return result
    return []
```

---

## Multi-Service Request Broken Workaround

### Problem
The API **does not** support requesting multiple services in a single call:

**Form A (repeated param)** — doesn't work:
```bash
curl "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=ecs&serviceName=evs&limitMax=10"
# Returns: only evs data (last service parameter wins)
```

**Form B (bracket notation)** — doesn't work either:
```bash
curl "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName[]=ecs&serviceName[]=evs&limitMax=10"
# Returns: only ecs data (first service parameter captured)
```

### Workaround: Fan-Out & Merge
Issue **one HTTP request per service**, then merge results client-side:

```python
def query_multiple_services(services, filters=None):
    results = {}
    for service in services:
        params = {
            "productType": "OTC",
            "serviceName": service,
            **filters or {}
        }
        response = fetch_api(params)
        items = extract_items(response, service)
        results[service] = items
    return results
```

**Performance**: For 47 services, expect 47 sequential (or parallelized) HTTP calls. Use connection pooling and thread/asyncio pools to stay within reasonable time budgets (e.g., ≤10s for all services with cache hits).

---

## Pagination Ceiling Behavior

The API has **no hard ceiling** on `limitMax`, and there is no soft pagination requirement for bulk reads.

### Observed Behavior
| limitMax | Largest Service (ECS) | Behavior |
|----------|----------------------|----------|
| 100 | 828 total | Returns 100, pagination needed |
| 500 | 828 total | Returns 500, pagination needed |
| 1000 | 828 total | Returns all 828 (hits catalog end) |
| 5000 | 828 total | Returns all 828 (exceeds catalog, capped) |

### Recommendation
- **Single-page bulk reads**: Use `limitMax=5000` to fetch all records for a service in one call.
- **Streaming reads**: If memory is constrained, paginate with `limitFrom=N&limitMax=100` and iterate until `recordsCount < limitMax`.

**Implementation example** (single-page bulk):
```python
def fetch_service_catalog(service):
    params = {
        "productType": "OTC",
        "serviceName": service,
        "limitMax": "5000"  # Fetch all in one call
    }
    return fetch_api(params)
```

---

## Locale Quirk: German Descriptions Despite `/en/` URL

The API endpoint includes `/en/` in the URL path:
```
https://calculator.otc-service.com/en/open-telekom-price-api/
```

However, the `description` field and other user-facing text are **entirely in German**, not English.

### Example
```json
{
  "description": "Virtuelle Maschine",  // "Virtual Machine" in English
  "productName": "General Purpose s3.m.1 Linux",
  "productCategory": "General Purpose vCPU:RAM 1:1 s3.*.1"
}
```

### Why
This is likely due to:
1. The API being hosted in Germany.
2. The data being sourced from a German pricing source (T-Systems).
3. No content negotiation via `Accept-Language` header (tested; no effect).

### Recommendation
**Do not attempt to translate.** Document in user-facing output that descriptions are in German. If translations are needed, implement a separate translation service or normalize step, but keep this out of the core wrapper.

---

## Price Format: Embedded Currency Strings

Prices are stored in a dual format: both embedded in a string and in a separate field.

### Example Record
```json
{
  "currency": "EUR",
  "priceAmount": "0.051175 EUR",
  "R12": "23.150000 EUR",
  "R24": "19.940000 EUR",
  "RU12": "21.500000 EUR",
  "RU24": "19.541667 EUR",
  ...
}
```

### Parser Requirement
The wrapper's **price parser** must:
1. **Never trust the embedded currency string** for multi-currency scenarios (even though all current records are EUR).
2. Extract the numeric part from `priceAmount`, `R*`, and `RU*` fields.
3. Cross-reference with the `currency` field to ensure consistency.
4. Raise an error if they disagree (e.g., field says `"23.150000 USD"` but `currency: "EUR"`).

**Implementation**:
```python
from decimal import Decimal
import re

def parse_price(price_str, currency):
    # Extract numeric part: "0.051175 EUR" → "0.051175"
    match = re.match(r'^([\d.]+)\s*\w+$', price_str.strip())
    if not match:
        raise ValueError(f"Cannot parse price: {price_str}")
    amount = Decimal(match.group(1))

    # Validate: if currency is in the string, it must match the field
    if ' ' in price_str:
        embedded_currency = price_str.split()[-1]
        if embedded_currency != currency:
            raise ValueError(
                f"Currency mismatch: field says {currency}, "
                f"string says {embedded_currency}"
            )
    return amount, currency
```

---

## Other Quirks & Observations

### 1. Swiss Region Currently EUR, Not CHF
As of 2026-05-06, the `eu-ch2` region returns `currency: "EUR"`, not `currency: "CHF"`. The Epic's initial assumption of CHF for Swiss records does not match the live API data. Clients must query the API to determine actual currency per record, not assume it by region.

### 2. Field Stability
The API returns 34+ fields per record, all documented in the Epic (§2). Future fields may be added. Clients should use Pydantic with `extra="allow"` and avoid hardcoding field lists.

### 3. Service Name Discovery
Service names must be discovered by paginating the unfiltered result without specifying `serviceName`. Each page returns a dict with service names as keys.

### 4. No Authentication
The API is public and requires **no authentication**. Bearer tokens, API keys, and basic auth are not needed.

### 5. Caching Headers
The API returns:
```
Cache-Control: private, max-age=900
```
Responses are cached for 15 minutes. Frequent polling (< 15 min) will hit the cache. This is beneficial for high-traffic clients.

### 6. User-Agent Optional
The API does not require a specific `User-Agent` header. Setting one is good practice; tested values like `otc-pricing-mcp/1.0` work fine.

---

## Testing the Filter Syntax: Step-by-Step

To verify the `filterBy[region]=` syntax on your own machine:

### Step 1: Fetch apig (which has eu-ch2 support)
```bash
curl -s "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=apig&limitMax=5" | jq '.response.result.apig[0] | {region, currency, priceAmount}'
```
**Expected output**:
```json
{
  "region": "eu-de",
  "currency": "EUR",
  "priceAmount": "0.117000 EUR"
}
```

### Step 2: Filter by eu-ch2
```bash
curl -s "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=apig&filterBy%5Bregion%5D=eu-ch2&limitMax=10" | jq '.response | {count: .stats.count, returned: .stats.recordsCount, sample: .result[0] | {region, currency}}'
```
**Expected output**:
```json
{
  "count": 4,
  "returned": 4,
  "sample": {
    "region": "eu-ch2",
    "currency": "EUR"
  }
}
```

### Step 3: Confirm old syntax fails
```bash
curl -s "https://calculator.otc-service.com/en/open-telekom-price-api/?productType=OTC&serviceName=apig&filterBy%5Bregion%5D%5B0%5D=eu-ch2&limitMax=10" | jq '.response.stats.count'
```
**Expected output**:
```
0
```

---

## Reference: Complete Curl Example (Production-Ready)

```bash
#!/bin/bash

SERVICE="apig"
REGION="eu-ch2"
LIMIT=100

curl \
  --max-time 30 \
  --silent \
  --show-error \
  --user-agent "otc-pricing-mcp/1.0" \
  "https://calculator.otc-service.com/en/open-telekom-price-api/?" \
  -G \
  -d "productType=OTC" \
  -d "serviceName=$SERVICE" \
  -d "filterBy[region]=$REGION" \
  -d "limitMax=$LIMIT" \
  | jq '.'
```

**Breakdown**:
- `--max-time 30`: 30-second timeout.
- `--silent --show-error`: Suppress progress bar, show errors.
- `--user-agent`: Identify the client.
- `-G -d`: Use GET with form-encoded parameters.
- `jq`: Pretty-print JSON (install via `apt install jq`).

---

## Recommendations for Implementation

1. **Normalize response shape** immediately upon deserialization in `extract_items()`.
2. **Cache the service catalog** (list of all service names) for 1 hour locally.
3. **Parse prices into `Decimal`** to avoid floating-point rounding errors.
4. **Parallelize multi-service requests** using a thread pool (5–10 concurrent requests).
5. **Log failed requests** with full URL and response body for debugging.
6. **Don't assume currency by region**; always trust the per-record `currency` field.
7. **Validate round-trip**: fetch → parse → serialize, ensure no data loss.

---

## Related Files

- **Catalog Inventory**: `/docs/catalog-inventory.md`
- **Probe Script**: `/scripts/probe.py`
- **Epic Context**: `/EPIC_otc-pricing-mcp_1.md` (§2 probe findings)
- **Sample Responses**: `/probe_results/filter_test_apig_eu_ch2.json` (confirmed working filter)

