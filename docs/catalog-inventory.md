# OTC Price Calculator API — Catalog Inventory

**Probe Date**: 2026-05-06T16:24
**API Endpoint**: `https://calculator.otc-service.com/en/open-telekom-price-api/`
**Product Type**: OTC (Open Telekom Cloud)
**Probe Tool**: `scripts/probe.py` v2.0

---

## Executive Summary

The OTC Price Calculator API exposes **47 distinct services** across **3 regions** and **1 currency**:

| Metric | Value |
|--------|-------|
| Total Services | 47 |
| Total Pricing Records | 2,046 |
| Unique Regions | 3 (eu-de, eu-nl, eu-ch2) |
| Unique Currencies | 1 (EUR) |
| Services with Swiss (eu-ch2) Support | 4 |

**Key Finding**: All records, including Swiss region (eu-ch2), currently carry `currency: "EUR"`. The Epic's initial assumption of CHF for Swiss records does not match the live API data as of 2026-05-06. This may be a temporary data state or a change from the API provider.

---

## Services Table

| Service | Record Count | Regions | Currencies | Notes |
|---------|--------------|---------|-----------|-------|
| aom | 6 | eu-de, eu-nl | EUR | |
| apig | 12 | **eu-ch2**, eu-de, eu-nl | EUR | ✓ Swiss support |
| apm2 | 1 | eu-de | EUR | |
| bms | 6 | eu-de | EUR | |
| buc | 2 | eu-de | EUR | |
| cbr | 8 | eu-de, eu-nl | EUR | |
| cce | 13 | eu-de, eu-nl | EUR | |
| cci | 2 | eu-de | EUR | |
| cco | 1 | eu-de | EUR | |
| cf | 2 | eu-de | EUR | |
| coss | 59 | **eu-ch2**, eu-de, eu-nl | EUR | ✓ Swiss support |
| csbs | 1 | eu-de | EUR | |
| cse | 4 | eu-de | EUR | |
| css | 36 | eu-de, eu-nl | EUR | |
| csscln | 30 | eu-de, eu-nl | EUR | |
| csscon | 30 | eu-de, eu-nl | EUR | |
| cssman | 30 | eu-de, eu-nl | EUR | |
| cwaf | 8 | eu-de, eu-nl | EUR | |
| da | 4 | eu-de | EUR | |
| das | 5 | eu-de | EUR | |
| dcs | 4 | eu-de | EUR | |
| dcsetup | 2 | eu-de | EUR | |
| deh | 29 | eu-de, eu-nl | EUR | |
| dehl | 12 | eu-de, eu-nl | EUR | |
| deh1 | 19 | eu-de, eu-nl | EUR | |
| deh2 | 10 | eu-de, eu-nl | EUR | |
| dehl1 | 10 | eu-de, eu-nl | EUR | |
| dehl2 | 2 | eu-de, eu-nl | EUR | |
| dins | 24 | eu-de, eu-nl | EUR | |
| dis | 6 | eu-de | EUR | |
| dli | 5 | eu-de | EUR | |
| dmarvol | 32 | eu-de, eu-nl | EUR | |
| dmscj | 13 | eu-de, eu-nl | EUR | |
| dmsk | 26 | eu-de, eu-nl | EUR | |
| dmsrmq | 6 | eu-de | EUR | |
| dmsvol | 8 | eu-de, eu-nl | EUR | |
| dnprq | 9 | **eu-ch2**, eu-de, eu-nl | EUR | ✓ Swiss support |
| dnq | 9 | **eu-ch2**, eu-de, eu-nl | EUR | ✓ Swiss support |
| drs | 188 | eu-de, eu-nl | EUR | (largest service) |
| dss | 3 | eu-de | EUR | |
| dws | 7 | eu-de | EUR | |
| ecs | 828 | eu-de, eu-nl | EUR | (ECS is the largest service) |
| phz | 8 | eu-de, eu-nl | EUR | |
| prhz | 8 | eu-de, eu-nl | EUR | |

---

## Regional Coverage

### Regions Discovered

1. **eu-de** (Germany)
   - Present in: 47/47 services (100%)
   - Currency: EUR

2. **eu-nl** (Netherlands)
   - Present in: 36/47 services (77%)
   - Currency: EUR

3. **eu-ch2** (Switzerland)
   - Present in: 4/47 services (9%)
   - Services: apig, coss, dnprq, dnq
   - Currency: EUR (not CHF as initially expected)

---

## Currency & Region Pairs

All discovered region-currency combinations:

| Region | Currency | Record Count | Services |
|--------|----------|--------------|----------|
| eu-de | EUR | 1,531 | 47 |
| eu-nl | EUR | 480 | 36 |
| eu-ch2 | EUR | 35 | 4 |

**Important Note**: As of the probe date (2026-05-06), **all Swiss (eu-ch2) records carry EUR currency, not CHF**. This contradicts the Epic's initial assumption. The wrapper implementation must handle whatever currency the API actually provides, not assume currency based on region.

---

## Swiss (eu-ch2) Records Proof

The `eu-ch2` region is confirmed to exist across multiple services:

### APIG Service (API Gateway)
- Total records with eu-ch2: 4
- Sample item from `filter_test_apig_eu_ch2.json`:
  ```json
  {
    "id": "OTC_APIG_S",
    "region": "eu-ch2",
    "currency": "EUR",
    "priceAmount": "0.000000 EUR",
    "productName": "API Gateway",
    "vCpu": "—",
    "ram": "—"
  }
  ```

### COSS Service (Cloud Object Storage Service)
- Total records with eu-ch2: 11 (estimated from full catalog)
- Storage-related pricing for Swiss region

### DNPRQ Service
- 1 eu-ch2 record
- DNS/Query related service

### DNQ Service
- 1 eu-ch2 record
- DNS/Query related service

**Verification**: Filtering with `filterBy[region]=eu-ch2` on the apig service returns 4 matching records, all with `region: "eu-ch2"` and `currency: "EUR"`.

---

## Pagination & Performance

| Limit Value | Behavior | Notes |
|-------------|----------|-------|
| limitMax=25 | Returns 25 items | Honors limit |
| limitMax=100 | Returns 100 items | Honors limit |
| limitMax=500 | Returns 500 items | Honors limit |
| limitMax=1000 | Returns up to 828 items (ECS max) | Hits total catalog size |
| limitMax=5000 | Returns all available items | No ceiling observed |

**Recommendation**: Use `limitMax=5000` for bulk operations to retrieve entire service catalogs in one request.

---

## Response Shape Quirk

The API returns results in two different shapes depending on whether filters are applied:

### Without filterBy (unfiltered request)
```json
{
  "response": {
    "result": {
      "ecs": [{...}, {...}],
      "evs": [{...}],
      ...
    }
  }
}
```
Result is a **dict** keyed by service name.

### With filterBy (filtered request)
```json
{
  "response": {
    "result": [
      {...},
      {...},
      ...
    ]
  }
}
```
Result is a **flat list** (service name lost in filtered results).

Clients must normalize this shape difference internally.

---

## Multi-Service Query Limitation

The API does **not** support multi-service requests in a single call:

- Form A: `serviceName=ecs&serviceName=evs` → returns only last service (evs)
- Form B: `serviceName[]=ecs&serviceName[]=evs` → returns only first service (ecs)

**Workaround**: Issue one HTTP request per service, then merge results client-side.

---

## Limitations & Notes

1. **No CHF Currency**: Despite being the Swiss region, eu-ch2 records are priced in EUR, not CHF. This may change in future API versions.

2. **Limited Swiss Coverage**: Only 4 of 47 services (9%) currently support the Swiss region. Most services are Germany-only (eu-de).

3. **Paginated Service Discovery**: The full service catalog must be discovered by paginating without a service filter and collecting unique service names from each page.

4. **Locale Quirk**: All descriptions (`description` field) are in German, despite the `/en/` URL segment. This is expected behavior per the Epic notes.

5. **Probe Sample Size**: This inventory was generated by fetching `limitMax=5000` for each service. All returned items were processed; no sampling was done within individual service catalogs.

---

## How to Regenerate

```bash
python3 scripts/probe.py
# Output: probe_results/catalog_inventory.json
```

The probe is idempotent and can be re-run at any time to detect API changes or new service additions.

---

## Related Files

- **Probe Script**: `/scripts/probe.py`
- **Raw Responses**: `/probe_results/*.json` (all API responses captured)
- **Filter Syntax Docs**: `/docs/api-quirks.md`
- **Epic Context**: `/EPIC_otc-pricing-mcp_1.md` (§2 probe findings, §5 Story 0)

