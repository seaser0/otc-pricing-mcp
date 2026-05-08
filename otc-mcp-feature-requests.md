# OTC Pricing MCP — Feature Requests

**Verfasser:** optimus (Claude) für seaser
**Datum:** 2026-05-08
**Server unter Test:** `https://mcp-otc-pricing.nevit.ch` — `otc-pricing-mcp v1.27.0`

---

## Kontext

Aktueller Status: Server läuft, MCP-Handshake funktioniert, 7 Tool-Schemas sind definiert, **alle Tool-Implementierungen geben `"Not yet implemented"` zurück**. Param-Validierung greift sauber — heißt: Skeleton steht, Backend-Logik fehlt komplett.

**Use-Case** (FinOps Price-Compare Projekt): Daily 02:00-UTC-Ingestion in ein `raw_prices`-Sheet. n8n-Workflow ruft den MCP auf, holt **alle aktuellen OTC-Preise** und schreibt sie long-format ans Worksheet. Parallel zu Azure Retail API + AWS Bulk JSON. Die manuelle Excel-Übergabe (aktueller Workaround) soll dadurch entfallen.

---

## Cross-cutting requirement: Public OTC vs Swiss OTC

**Kritisch und vorab zu klären:** Alle Tools brauchen eine klare Unterscheidung zwischen **Public OTC** (eu-de, eu-nl, EUR) und **Swiss OTC** (eigene Region, vermutlich CHF, eingeschränktes Service-Inventar). Empfehlung: ein expliziter Parameter `cloud: "public-otc" | "swiss-otc"` an jedem Tool, **nicht** über Region implizit.

Begründung: Auf Swiss OTC existieren z.B. nur ECS S3, EVS High-I/O + Ultra-High-I/O, OBS, NAT, EIP, ELB usw. — viele Services sind explizit nicht verfügbar. Der MCP muss in der Lage sein, „swiss-otc hat das nicht" sauber zurückzugeben statt zu raten.

---

## P0 — blockt die Ingestion

### 1. `query_pricing` — vollständig implementieren

**Wichtigstes Tool.** Muss als Bulk-Snapshot-Endpoint funktionieren.

**Request:**
```json
{
  "cloud": "public-otc" | "swiss-otc",
  "services": ["ecs", "evs", "obs"],   // optional, default = all
  "region": "eu-de",                    // optional, default = all
  "max_results": 5000                   // optional, paginierung via cursor
}
```

**Response (acceptance criteria):**
- Long-format-Zeilen, eine Zeile pro `(service, sku, region, billing_model)`-Tupel
- Pflichtfelder pro Zeile:
  - `service` (z.B. `"ecs"`)
  - `sku` / `product_id` (z.B. `"s3.medium.4"`)
  - `region` (z.B. `"eu-de"`, `"swiss-otc"`)
  - `cloud` (`"public-otc"` / `"swiss-otc"`)
  - `unit` (z.B. `"hour"`, `"GB-month"`, `"GB"`)
  - `unit_price` (decimal, nicht string)
  - `currency` (`"EUR"` / `"CHF"`)
  - `billing_model` (`"payg"` / `"reserved-12m"` / `"reserved-24m"` / `"reserved-36m"`)
  - `price_valid_from` (ISO 8601 timestamp)
- Stabile, idempotente IDs — gleiche `(service, sku, region, billing_model)`-Kombi muss bei wiederholtem Aufruf identisch sein. Wird für Mapping zu `canonical_id` im `product_map` benötigt.
- Pagination via `next_cursor` im Response, nicht via Offset.

**Performance:** Kompletter Public-OTC-Snapshot in <30s, Swiss-OTC-Snapshot in <10s. Wenn nicht möglich → klare Pagination dokumentieren.

---

### 2. `list_services` — implementieren

**Request:** `{"cloud": "public-otc" | "swiss-otc"}`

**Response:** Array von Services mit Metadaten:
```json
[
  {"service": "ecs", "name": "Elastic Cloud Server",
   "category": "compute", "available_regions": ["eu-de","eu-nl","swiss-otc"]},
  {"service": "evs", "name": "Elastic Volume Service",
   "category": "storage", "available_regions": ["eu-de","eu-nl","swiss-otc"]}
]
```

Brauche das für Service-Discovery in der Ingestion und für das Audit „welche neuen Services sind seit letztem Run aufgetaucht".

---

### 3. `list_regions` — implementieren

**Request:** `{"cloud": "public-otc" | "swiss-otc"}`

**Response:**
```json
[
  {"region": "eu-de", "name": "Frankfurt", "currency": "EUR"},
  {"region": "eu-nl", "name": "Amsterdam", "currency": "EUR"},
  {"region": "swiss-otc", "name": "Switzerland", "currency": "CHF"}
]
```

Wichtig: `currency` pro Region — wird gebraucht, um zu wissen welche FX-Conversion fällig wird.

---

### 4. Data-Freshness-Endpoint (NEU)

Aktuell nicht im Tool-Set, **dringend benötigt**:

```
get_data_freshness(cloud) → {
  "cloud": "public-otc",
  "last_updated": "2026-05-08T01:30:00Z",
  "source": "huawei-website-scrape" | "t-systems-excel" | "...",
  "services_covered": 23
}
```

Begründung: Die Ingestion-Pipeline muss wissen, ob die Daten frisch sind, sonst pollen wir blind. Ohne das ist keine sinnvolle Coverage-Alarmierung möglich.

---

## P1 — blockt vollständige Feature-Parität

### 5. `get_service_schema` — implementieren

**Response:** Pro Service die Liste filterbarer Spalten + zurückgebbarer Spalten:
```json
{
  "service": "ecs",
  "filterable": ["flavor_family", "vcpu", "ram_gb", "gpu", "os", "region"],
  "returnable": ["sku", "flavor_name", "vcpu", "ram_gb", "gpu_count", "gpu_model",
                 "storage_type", "network_perf", "unit_price", "currency"]
}
```

Brauche das für UI/Reporting: welche Filter-Dimensionen sind verfügbar.

---

### 6. `find_compute_flavor` — implementieren

Schema steht (`v_cpu`, `ram_gb`, optional `os`, `region`). Implementierung muss:

- Zurückgeben: alle ECS-Flavors die ≥ den Anforderungen entsprechen, sortiert nach Preis aufsteigend
- Mit Spec-Match-Confidence: `"exact"` | `"oversized"` (next-bigger)
- Pro Match: `sku`, `vcpu`, `ram_gb`, `gpu`, `unit_price_payg`, `unit_price_reserved_36m`, `currency`, `region`, `cloud`

Use-case: User will wissen „welche OTC-Instanz für 8 vCPU / 32 GB RAM ist am günstigsten" → Vergleich gegen AWS/Azure-Pendants.

---

### 7. `compare_billing_models` — implementieren

Schema: `product_id` + optional `quantity`, `hours_per_month`.

**Response:**
```json
{
  "product_id": "ecs.s3.medium.4",
  "currency": "EUR",
  "quantity": 1,
  "hours_per_month": 730,
  "models": [
    {"model": "payg",         "monthly_cost": 42.34, "annual_cost": 508.08, "discount_vs_payg": 0},
    {"model": "reserved-12m", "monthly_cost": 33.87, "annual_cost": 406.40, "discount_vs_payg": 0.20},
    {"model": "reserved-36m", "monthly_cost": 25.40, "annual_cost": 304.80, "discount_vs_payg": 0.40}
  ]
}
```

---

## P2 — Nice-to-have / spätere Phase

### 8. `estimate_monthly_cost`

Item-Liste rein → Total raus. Kann der Client eigentlich auch selbst aus `query_pricing` zusammenbauen, daher P2.

```json
{
  "items": [
    {"service":"ecs","sku":"s3.medium.4","quantity":2,"hours":730},
    {"service":"evs","sku":"sas-evs","quantity":1,"size_gb":500},
    {"service":"obs","sku":"obs-standard","size_gb":1000}
  ],
  "cloud":"public-otc","region":"eu-de"
}
```

→ `{"total_monthly":198.50,"currency":"EUR","breakdown":[...]}`

### 9. `get_price_history` (NEU)

Optional, aber wertvoll für Trend-Reporting:
```
get_price_history(service, sku, region, since_date) → [
  {"date":"2026-01-01","unit_price":0.058},
  {"date":"2026-04-01","unit_price":0.055}
]
```

---

## Architectural concerns für den Entwickler

1. **Datenquelle deklarieren.** Excel-Scrape von t-systems? Manuelles Pflegen? Dynamische API? Bestimmt Refresh-Cadence + Freshness-SLA.
2. **Reserved-Instance-Pricing** ist auf der OTC-Website pro Region/Term unterschiedlich verfügbar. Falls eine Region kein Reserved hat → `models` einfach kürzer zurückgeben, nicht `null` werfen.
3. **Stabile SKUs.** Wenn upstream OTC eine Flavor umbenennt — bitte Aliase pflegen, nicht den Key brechen. Sonst zerschießt es das Mapping zu `canonical_id`.
4. **Rate Limits / Caching.** Falls upstream gescraped wird: serverseitiges Caching mit TTL ≥ 24h, weil Preise sich realistischerweise nicht stündlich ändern.
5. **Error Shape.** Heute: Plain-Text `"Not yet implemented"`. Future: strukturierte MCP-Errors mit `code` + `message` + ggf. `details.upstream_error`. Damit die n8n-Pipeline retry-/alert-Logik bauen kann.
6. **MCP-Notifications nutzen.** Der AWS-Server schickt z.B. `notifications/message` mit `level:"info"` während langer Calls. Sehr nützlich — bitte dasselbe Muster für Bulk-`query_pricing`.

---

## Priorisierte Reihenfolge für den Entwickler

Wenn nur Zeit für eines: **`query_pricing` mit `cloud`-Parameter** — das alleine entblockt 80% des Ingestion-Use-Cases. Danach `list_services` + `list_regions` + `get_data_freshness`. Der Rest kann iterativ.

---

## Referenz: Aktueller Tool-Bestand (Schemas)

| Tool                     | Required          | Optional                              | Status                  |
|--------------------------|-------------------|---------------------------------------|-------------------------|
| `list_services`          | —                 | —                                     | Stub                    |
| `list_regions`           | —                 | —                                     | Stub                    |
| `get_service_schema`     | `service`         | —                                     | Stub                    |
| `query_pricing`          | `services`        | `region`, `max_results`               | Stub                    |
| `find_compute_flavor`    | `v_cpu`, `ram_gb` | `os`, `region`                        | Stub (Validation works) |
| `estimate_monthly_cost`  | `items`           | —                                     | Stub                    |
| `compare_billing_models` | `product_id`      | `quantity`, `hours_per_month`         | Stub                    |
