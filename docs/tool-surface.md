# Tool Reference: otc-pricing-mcp

Full reference for all 7 MCP tools exposed by the OTC Pricing MCP server.

All tool names and parameter names match what is registered in `src/otc_pricing_mcp/server.py`. Do not pass undocumented parameters — they will be silently ignored.

**Currency note**: every monetary value is in the currency carried by the per-record `currency` field (`EUR` for `eu-de`/`eu-nl`, `CHF` for `eu-ch2`). The server never converts currencies.

---

## Tool Index

| Tool | Purpose |
|------|---------|
| [`list_services`](#list_services) | Catalog of services with pricing data |
| [`list_regions`](#list_regions) | Available regions across all services |
| [`get_service_schema`](#get_service_schema) | Filterable/returnable columns for a service |
| [`query_pricing`](#query_pricing) | Flexible raw pricing query (services × filters) |
| [`find_compute_flavor`](#find_compute_flavor) | Convenience search for VMs by vCPU/RAM/OS |
| [`estimate_monthly_cost`](#estimate_monthly_cost) | Itemized monthly cost from a list of resources |
| [`compare_billing_models`](#compare_billing_models) | PAYG vs Reserved 12/24/36 side-by-side |

---

## `list_services`

Returns the list of OTC services that have pricing data available in the catalog.

### Input parameters

This tool takes no input parameters.

### Return shape

```json
["ecs", "evs", "obs", "rds", ...]
```

| Field | Type | Description |
|-------|------|-------------|
| *(root)* | `string[]` | Sorted list of service name strings (e.g., `"ecs"`, `"evs"`, `"obs"`) |

### Example

**Call:**
```json
{
  "name": "list_services",
  "arguments": {}
}
```

**Response (truncated):**
```json
["apig", "bms", "cce", "dcs", "dds", "dis", "dli", "dms", "dns", "dws",
 "ecs", "elb", "evs", "gaussdb", "iam", "kms", "lts", "mlss", "nat",
 "obs", "rds", "smn", "vpcep"]
```

---

## `list_regions`

Returns all region codes found across the OTC pricing catalog.

### Input parameters

This tool takes no input parameters.

### Return shape

```json
["eu-ch2", "eu-de", "eu-nl"]
```

| Field | Type | Description |
|-------|------|-------------|
| *(root)* | `string[]` | Sorted list of region code strings |

Known regions as of 2026-05-06:

| Region | Currency | Location |
|--------|----------|---------|
| `eu-de` | EUR | Germany (Frankfurt) |
| `eu-nl` | EUR | Netherlands (Amsterdam) |
| `eu-ch2` | CHF | Switzerland (Biere) |

### Example

**Call:**
```json
{
  "name": "list_regions",
  "arguments": {}
}
```

**Response:**
```json
["eu-ch2", "eu-de", "eu-nl"]
```

---

## `get_service_schema`

Returns the available columns for a given service — useful for understanding what fields can be used as filters or returned in `query_pricing`.

### Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `service` | `string` | Yes | — | Service name (e.g., `"ecs"`, `"evs"`, `"obs"`) |

### Return shape

```json
{
  "service": "ecs",
  "columns": {"vCpu": "vCPU", "ram": "RAM", ...},
  "filterable_columns": ["isMRC", "opiFlavour", "osUnit", ...],
  "returnable_columns": ["isMRC", "opiFlavour", "osUnit", ...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `service` | `string` | The requested service name |
| `columns` | `object` | Map of `column_name → display_label` for all columns in this service |
| `filterable_columns` | `string[]` | Sorted list of column names usable as filters in `query_pricing` |
| `returnable_columns` | `string[]` | Sorted list of column names present in price item records |

**Error**: raises `ValueError` if the service is not found or has no columns.

### Example

**Call:**
```json
{
  "name": "get_service_schema",
  "arguments": {"service": "ecs"}
}
```

**Response:**
```json
{
  "service": "ecs",
  "columns": {
    "id": "ID",
    "productName": "Product Name",
    "region": "Region",
    "vCpu": "vCPU",
    "ram": "RAM",
    "osUnit": "OS",
    "opiFlavour": "Flavor",
    "priceAmount": "Price (PAYG)",
    "R12": "Reserved 12m",
    "R24": "Reserved 24m",
    "R36": "Reserved 36m",
    "currency": "Currency"
  },
  "filterable_columns": ["id", "opiFlavour", "osUnit", "productName", "region", "vCpu"],
  "returnable_columns": ["id", "opiFlavour", "osUnit", "productName", "priceAmount", "R12", "R24", "R36", "ram", "region", "vCpu"]
}
```

---

## `query_pricing`

Queries raw pricing records for one or more OTC services with optional filters. This is the most flexible tool — use it when you need the raw data or when the other convenience tools are too narrow.

Multi-service requests are fanned out as parallel HTTP calls (up to 5 concurrent). Partial failures are reported in `warnings` without blocking results from other services.

### Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `services` | `string[]` | Yes | — | One or more service names (e.g., `["ecs"]`, `["ecs", "evs", "obs"]`) |
| `region` | `string` | No | *(all regions)* | Filter results to a specific region: `"eu-de"`, `"eu-nl"`, or `"eu-ch2"` |
| `max_results` | `integer` | No | `5000` | Maximum number of records to return per service. The OTC catalog has at most a few thousand records per service, so `5000` effectively fetches the full catalog in one call. |

### Return shape

```json
{
  "services": {
    "ecs": [
      {
        "id": "string",
        "productId": "string",
        "productName": "string",
        "productCategory": "string",
        "productFamily": "string",
        "opiFlavour": "string",
        "serviceType": "string",
        "osUnit": "string",
        "vCpu": "string",
        "ram": "string",
        "region": "string",
        "unit": "string",
        "isMRC": "string",
        "priceAmount": "string",
        "currency": "string",
        "R12": "string",
        "R24": "string",
        "R36": "string",
        "RU12": "string",
        "RU24": "string",
        "RU36": "string"
      }
    ]
  },
  "total_items": 828,
  "currency_breakdown": {"EUR": 600, "CHF": 228},
  "regions_found": ["eu-ch2", "eu-de", "eu-nl"],
  "warnings": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `services` | `object` | Map of `service_name → [price_item, ...]`. Each item is a full PriceItem record. |
| `services[*][*].id` | `string` | Unique item identifier (e.g., `"OTC_S3M1_LI"`) |
| `services[*][*].priceAmount` | `string` | PAYG price string (e.g., `"0.051175 EUR"` or `"0.058000 CHF"`) |
| `services[*][*].currency` | `string` | ISO 4217 currency code for this record (`"EUR"` or `"CHF"`) |
| `services[*][*].R12` | `string` | Monthly reserved price at 12-month commitment (e.g., `"37.230000 EUR"`) |
| `services[*][*].R24` | `string` | Monthly reserved price at 24-month commitment |
| `services[*][*].R36` | `string` | Monthly reserved price at 36-month commitment |
| `services[*][*].RU12` | `string` | Upfront reserved price at 12-month commitment |
| `services[*][*].RU24` | `string` | Upfront reserved price at 24-month commitment |
| `services[*][*].RU36` | `string` | Upfront reserved price at 36-month commitment |
| `services[*][*].region` | `string` | Region code for this record |
| `services[*][*].vCpu` | `string` | vCPU count as a string (ECS only, e.g., `"4"`) |
| `services[*][*].ram` | `string` | RAM as a string with unit (ECS only, e.g., `"8 GiB"`) |
| `services[*][*].osUnit` | `string` | OS identifier (ECS only, e.g., `"Linux"`, `"Windows"`) |
| `total_items` | `integer` | Total record count across all services |
| `currency_breakdown` | `object` | Map of `currency_code → count` |
| `regions_found` | `string[]` | Sorted list of regions present in the results |
| `warnings` | `string[]` | List of per-service error messages when a service fetch failed. Empty on full success. |

**Note on price strings**: All price fields (`priceAmount`, `R12`, `R24`, `R36`, `RU12`, `RU24`, `RU36`) are raw strings from the OTC API in the format `"<amount> <currency>"` (e.g., `"0.051175 EUR"`). Use `estimate_monthly_cost` or `compare_billing_models` to get numeric values.

### Examples

**Single service:**
```json
{
  "name": "query_pricing",
  "arguments": {"services": ["ecs"]}
}
```

**Multiple services with region filter (parallel fan-out):**
```json
{
  "name": "query_pricing",
  "arguments": {"services": ["ecs", "evs", "obs"], "region": "eu-de"}
}
```

**With result limit:**
```json
{
  "name": "query_pricing",
  "arguments": {"services": ["ecs"], "max_results": 50}
}
```

**Response shape (abbreviated):**
```json
{
  "services": {
    "ecs": [
      {
        "id": "OTC_ECS_C3NE_8C64G_LI",
        "productName": "c3ne.2xlarge.8",
        "opiFlavour": "c3ne.2xlarge.8",
        "vCpu": "8",
        "ram": "64 GiB",
        "osUnit": "Linux",
        "region": "eu-de",
        "priceAmount": "0.341000 EUR",
        "currency": "EUR",
        "R12": "208.530000 EUR",
        "R24": "186.290000 EUR",
        "R36": "171.430000 EUR",
        "RU12": "0.000000 EUR",
        "RU24": "0.000000 EUR",
        "RU36": "0.000000 EUR"
      }
    ]
  },
  "total_items": 1,
  "currency_breakdown": {"EUR": 1},
  "regions_found": ["eu-de"],
  "warnings": []
}
```

---

## `find_compute_flavor`

Convenience wrapper around `query_pricing` for searching ECS (compute) instances by vCPU count, RAM size, and optional OS type. Returns only records that exactly match the requested vCPU and RAM.

### Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `v_cpu` | `integer` | Yes | — | Virtual CPU count (e.g., `1`, `2`, `4`, `8`, `16`, `32`) |
| `ram_gb` | `number` | Yes | — | RAM in GiB (e.g., `1`, `2`, `4`, `8`, `16`, `32`, `64`) |
| `os` | `string` | No | *(all OS types)* | OS type filter. Case-insensitive substring match against the `osUnit` field. Common values: `"Linux"`, `"Windows"`, `"Oracle"`, `"SUSE"`, `"CentOS"` |
| `region` | `string` | No | `"eu-de"` | Region to search. Options: `"eu-de"`, `"eu-nl"`, `"eu-ch2"` |

### Return shape

Returns a list of matching ECS price item records (same structure as items inside `query_pricing`'s `services.ecs` array). Returns an empty list if no matches are found.

```json
[
  {
    "id": "string",
    "productName": "string",
    "opiFlavour": "string",
    "vCpu": "string",
    "ram": "string",
    "osUnit": "string",
    "region": "string",
    "priceAmount": "string",
    "currency": "string",
    "R12": "string",
    "R24": "string",
    "R36": "string",
    "RU12": "string",
    "RU24": "string",
    "RU36": "string"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| *(root)* | `object[]` | List of matching ECS price item records |
| `[*].id` | `string` | Unique product ID usable in `estimate_monthly_cost` and `compare_billing_models` |
| `[*].productName` | `string` | Human-readable flavor name (e.g., `"s3.medium.2"`) |
| `[*].opiFlavour` | `string` | API flavor identifier |
| `[*].vCpu` | `string` | vCPU count as string |
| `[*].ram` | `string` | RAM with unit (e.g., `"4 GiB"`) |
| `[*].osUnit` | `string` | OS identifier (e.g., `"Linux"`) |
| `[*].region` | `string` | Region code |
| `[*].priceAmount` | `string` | PAYG hourly price string (e.g., `"0.051175 EUR"`) |
| `[*].currency` | `string` | ISO 4217 currency code |
| `[*].R12`–`[*].R36` | `string` | Monthly reserved price strings at 12/24/36 months |
| `[*].RU12`–`[*].RU36` | `string` | Upfront reserved price strings at 12/24/36 months |

### Examples

**4-core, 8 GiB Linux instances in eu-de:**
```json
{
  "name": "find_compute_flavor",
  "arguments": {"v_cpu": 4, "ram_gb": 8, "os": "Linux", "region": "eu-de"}
}
```

**All 2-core, 4 GiB instances (any OS) in eu-nl:**
```json
{
  "name": "find_compute_flavor",
  "arguments": {"v_cpu": 2, "ram_gb": 4, "region": "eu-nl"}
}
```

**Swiss region Windows instances:**
```json
{
  "name": "find_compute_flavor",
  "arguments": {"v_cpu": 8, "ram_gb": 16, "os": "Windows", "region": "eu-ch2"}
}
```

**Response:**
```json
[
  {
    "id": "OTC_ECS_S3_2C4G_LI",
    "productName": "s3.medium.4",
    "opiFlavour": "s3.medium.4",
    "vCpu": "2",
    "ram": "4 GiB",
    "osUnit": "Linux",
    "region": "eu-de",
    "priceAmount": "0.051175 EUR",
    "currency": "EUR",
    "R12": "31.210000 EUR",
    "R24": "27.880000 EUR",
    "R36": "25.650000 EUR",
    "RU12": "0.000000 EUR",
    "RU24": "0.000000 EUR",
    "RU36": "0.000000 EUR"
  }
]
```

---

## `estimate_monthly_cost`

Calculates an itemized monthly cost estimate for a list of OTC resources. Accepts product IDs (use `find_compute_flavor` or `query_pricing` to discover IDs) and returns PAYG and reserved costs for each item plus totals.

Fails loudly (raises `ValueError`) on unknown product IDs — this prevents silently returning zero costs for mistyped IDs.

### Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `items` | `object[]` | Yes | — | List of resource specifications. Must contain at least one item. |
| `items[*].id` | `string` | Yes | — | Product ID (e.g., `"OTC_S3M1_LI"`). Obtain from `query_pricing` or `find_compute_flavor`. |
| `items[*].quantity` | `number` | No | `1` | Number of units (e.g., `3` for 3 identical VMs) |
| `items[*].hours_per_month` | `number` | No | `730` | Usage hours per month. `730` ≈ 24 h/day × 30.4 days (full month). Use `168` for business-hours-only usage (5 days × 8 h × 4.2 weeks). |

### Return shape

```json
{
  "total_payg": 37.46,
  "total_reserved_12m": 31.21,
  "total_reserved_24m": 27.88,
  "total_reserved_36m": 25.65,
  "total_reserved_upfront_12m": 0.0,
  "total_reserved_upfront_24m": 0.0,
  "total_reserved_upfront_36m": 0.0,
  "currency": "EUR",
  "items": [
    {
      "id": "OTC_ECS_S3_2C4G_LI",
      "quantity": 1.0,
      "hours_per_month": 730.0,
      "payg": 37.46,
      "reserved_12m": 31.21,
      "reserved_24m": 27.88,
      "reserved_36m": 25.65,
      "reserved_upfront_12m": 0.0,
      "reserved_upfront_24m": 0.0,
      "reserved_upfront_36m": 0.0,
      "currency": "EUR"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_payg` | `float` | Total monthly PAYG cost across all items (`priceAmount` × `hours_per_month` × `quantity`) |
| `total_reserved_12m` | `float` | Total monthly reserved cost at 12-month commitment |
| `total_reserved_24m` | `float` | Total monthly reserved cost at 24-month commitment |
| `total_reserved_36m` | `float` | Total monthly reserved cost at 36-month commitment |
| `total_reserved_upfront_12m` | `float` | Total upfront reserved cost at 12-month commitment |
| `total_reserved_upfront_24m` | `float` | Total upfront reserved cost at 24-month commitment |
| `total_reserved_upfront_36m` | `float` | Total upfront reserved cost at 36-month commitment |
| `currency` | `string` | ISO 4217 currency code of the last processed item. Mix currencies only if you mix `eu-ch2` (CHF) and other regions (EUR); totals will be wrong across currencies — query one region at a time if mixed-currency accuracy matters. |
| `items` | `object[]` | Per-item cost breakdown |
| `items[*].id` | `string` | Product ID |
| `items[*].quantity` | `float` | Quantity used for calculation |
| `items[*].hours_per_month` | `float` | Hours per month used for calculation |
| `items[*].payg` | `float` | Monthly PAYG cost for this item |
| `items[*].reserved_12m` | `float` | Monthly reserved cost (12 months) for this item |
| `items[*].reserved_24m` | `float` | Monthly reserved cost (24 months) for this item |
| `items[*].reserved_36m` | `float` | Monthly reserved cost (36 months) for this item |
| `items[*].reserved_upfront_12m` | `float` | Upfront reserved cost (12 months) for this item |
| `items[*].reserved_upfront_24m` | `float` | Upfront reserved cost (24 months) for this item |
| `items[*].reserved_upfront_36m` | `float` | Upfront reserved cost (36 months) for this item |
| `items[*].currency` | `string` | Currency for this item |

### Examples

**Single resource, default hours:**
```json
{
  "name": "estimate_monthly_cost",
  "arguments": {
    "items": [{"id": "OTC_ECS_S3_2C4G_LI"}]
  }
}
```

**Multiple resources with custom quantities and hours:**
```json
{
  "name": "estimate_monthly_cost",
  "arguments": {
    "items": [
      {"id": "OTC_ECS_S3_2C4G_LI", "quantity": 3},
      {"id": "OTC_EVS_SSD_LI", "quantity": 500, "hours_per_month": 730},
      {"id": "OTC_OBS_S3M1_LI", "quantity": 1, "hours_per_month": 168}
    ]
  }
}
```

---

## `compare_billing_models`

Compares PAYG and reserved billing for a single product. Returns the effective monthly cost and savings percentage for each reservation length (12, 24, 36 months), including upfront costs amortized into a monthly equivalent.

This tool calls `estimate_monthly_cost` internally and adds savings calculations on top. Use it for cost optimization decisions.

### Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `product_id` | `string` | Yes | — | Product ID (e.g., `"OTC_ECS_S3_2C4G_LI"`). Obtain from `query_pricing` or `find_compute_flavor`. |
| `quantity` | `number` | No | `1` | Number of units |
| `hours_per_month` | `number` | No | `730` | Usage hours per month. `730` ≈ 24/7 operation. |

### Return shape

```json
{
  "product_id": "OTC_ECS_S3_2C4G_LI",
  "currency": "EUR",
  "quantity": 1.0,
  "hours_per_month": 730.0,
  "payg": {
    "monthly_cost": 37.46,
    "hourly_rate": 0.05132
  },
  "reserved_12m": {
    "monthly_cost": 31.21,
    "upfront_cost": 0.0,
    "total_cost": 374.52,
    "monthly_equivalent": 31.21,
    "savings_percent": 16.69
  },
  "reserved_24m": {
    "monthly_cost": 27.88,
    "upfront_cost": 0.0,
    "total_cost": 669.12,
    "monthly_equivalent": 27.88,
    "savings_percent": 25.58
  },
  "reserved_36m": {
    "monthly_cost": 25.65,
    "upfront_cost": 0.0,
    "total_cost": 923.40,
    "monthly_equivalent": 25.65,
    "savings_percent": 31.53
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `product_id` | `string` | The requested product ID |
| `currency` | `string` | ISO 4217 currency code |
| `quantity` | `float` | Quantity used for calculation |
| `hours_per_month` | `float` | Hours per month used for calculation |
| `payg.monthly_cost` | `float` | Monthly PAYG cost (`priceAmount` × `hours_per_month` × `quantity`) |
| `payg.hourly_rate` | `float` | Per-hour PAYG rate (`monthly_cost` ÷ `hours_per_month`) |
| `reserved_NNm.monthly_cost` | `float` | Monthly recurring charge under the NN-month commitment |
| `reserved_NNm.upfront_cost` | `float` | One-time upfront payment at commitment start (`RUnn` field) |
| `reserved_NNm.total_cost` | `float` | Total cost over the commitment period (`monthly_cost × months + upfront_cost`) |
| `reserved_NNm.monthly_equivalent` | `float` | Total cost amortized per month (`total_cost ÷ months`) — comparable to `payg.monthly_cost` |
| `reserved_NNm.savings_percent` | `float` | Percentage savings vs PAYG based on `monthly_equivalent`. Floored at `0` (never negative). |

**Error**: raises `ValueError` if `product_id` is not found in the catalog.

### Examples

**Compare billing for single unit at full uptime:**
```json
{
  "name": "compare_billing_models",
  "arguments": {"product_id": "OTC_ECS_S3_2C4G_LI"}
}
```

**Compare billing for 5 units at business hours only:**
```json
{
  "name": "compare_billing_models",
  "arguments": {
    "product_id": "OTC_ECS_S3_2C4G_LI",
    "quantity": 5,
    "hours_per_month": 168
  }
}
```
